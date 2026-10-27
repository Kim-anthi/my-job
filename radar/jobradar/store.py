"""SQLite memory: which jobs have been seen, and which were already pushed.

Two dedup keys are tracked per job:

* ``key``     - identity within a source. The primary key.
* ``alt_key`` - company + normalised title, so the same posting arriving from
  RemoteOK *and* We Work Remotely only ever pings the phone once.

A job is recorded the moment it matches, with ``status='new'``, and only
flipped to ``notified`` once the push actually succeeded. That way a Telegram
outage (or the per-run message cap) leaves the job queued for the next run
instead of losing it silently.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dates import parse_date
from .models import SUMMARY_LIMIT, Job

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key         TEXT PRIMARY KEY,
    alt_key     TEXT NOT NULL,
    source      TEXT NOT NULL,
    external_id TEXT,
    title       TEXT NOT NULL,
    company     TEXT,
    url         TEXT,
    location    TEXT,
    tags        TEXT,
    salary      TEXT,
    posted_at   TEXT,
    summary     TEXT,
    score       INTEGER NOT NULL DEFAULT 0,
    reasons     TEXT,
    status      TEXT NOT NULL DEFAULT 'new',
    first_seen  TEXT NOT NULL,
    notified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_alt_key ON jobs(alt_key);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_seen    ON jobs(first_seen);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    fetched     INTEGER DEFAULT 0,
    matched     INTEGER DEFAULT 0,
    fresh       INTEGER DEFAULT 0,
    notified    INTEGER DEFAULT 0,
    errors      TEXT
);
"""


@dataclass
class Counts:
    total: int
    notified: int
    pending: int
    duplicates: int


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.db.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a database was first created.

        CI restores the database from a cache, so a schema change has to be
        survivable without wiping the dedup history.
        """
        existing = {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        for column, ddl in (("summary", "TEXT"),):
            if column not in existing:
                self.db.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- dedup ---------------------------------------------------------------

    def known_keys(self) -> set[str]:
        return {row[0] for row in self.db.execute("SELECT key FROM jobs")}

    def known_alt_keys(self) -> set[str]:
        return {row[0] for row in self.db.execute("SELECT alt_key FROM jobs")}

    # -- writes --------------------------------------------------------------

    def record(self, job: Job, status: str = "new") -> None:
        now = _now_iso()
        self.db.execute(
            """
            INSERT INTO jobs (key, alt_key, source, external_id, title, company, url,
                              location, tags, salary, posted_at, summary, score,
                              reasons, status, first_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET
                score   = excluded.score,
                reasons = excluded.reasons,
                summary = excluded.summary
            """,
            (
                job.key,
                job.alt_key,
                job.source,
                job.external_id,
                job.title,
                job.company,
                job.url,
                job.location,
                json.dumps(job.tags),
                job.salary,
                job.posted_at.isoformat() if job.posted_at else None,
                job.description[:SUMMARY_LIMIT],
                job.score,
                json.dumps(job.reasons),
                status,
                now,
            ),
        )
        self.db.commit()

    def mark_notified(self, key: str) -> None:
        self.db.execute(
            "UPDATE jobs SET status = 'notified', notified_at = ? WHERE key = ?",
            (_now_iso(), key),
        )
        self.db.commit()

    def mute(self, key: str) -> None:
        self.db.execute("UPDATE jobs SET status = 'muted' WHERE key = ?", (key,))
        self.db.commit()

    def log_run(
        self,
        *,
        started_at: datetime,
        fetched: int,
        matched: int,
        fresh: int,
        notified: int,
        errors: list[str],
    ) -> None:
        self.db.execute(
            """INSERT INTO runs (started_at, finished_at, fetched, matched, fresh,
                                 notified, errors) VALUES (?,?,?,?,?,?,?)""",
            (
                started_at.isoformat(),
                _now_iso(),
                fetched,
                matched,
                fresh,
                notified,
                "\n".join(errors) if errors else None,
            ),
        )
        self.db.commit()

    def prune(self, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = self.db.execute("DELETE FROM jobs WHERE first_seen < ?", (cutoff,))
        self.db.execute("DELETE FROM runs WHERE started_at < ?", (cutoff,))
        self.db.commit()
        return cursor.rowcount

    # -- reads ---------------------------------------------------------------

    def pending(self, limit: int = 50) -> list[Job]:
        """Matched but never pushed - the retry queue."""
        # Oldest batch first so a deferred job never starves; best score first
        # within a batch (one run writes one first_seen timestamp).
        rows = self.db.execute(
            """SELECT * FROM jobs WHERE status = 'new'
               ORDER BY first_seen ASC, score DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [row_to_job(row) for row in rows]

    def recent(self, limit: int = 20, status: str | None = None) -> list[Job]:
        query = "SELECT * FROM jobs"
        params: list[object] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY first_seen DESC LIMIT ?"
        params.append(limit)
        return [row_to_job(row) for row in self.db.execute(query, params).fetchall()]

    def counts(self) -> Counts:
        def count(where: str = "", *params: object) -> int:
            sql = "SELECT COUNT(*) FROM jobs" + (f" WHERE {where}" if where else "")
            return int(self.db.execute(sql, params).fetchone()[0])

        return Counts(
            total=count(),
            notified=count("status = 'notified'"),
            pending=count("status = 'new'"),
            duplicates=count("status = 'duplicate'"),
        )

    def export_json(self, path: str | Path, limit: int = 300) -> Path:
        """Dump the newest jobs for the Flutter app / any dashboard to read."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = self.db.execute(
            """SELECT * FROM jobs WHERE status IN ('notified', 'new')
               ORDER BY first_seen DESC, score DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        payload = {
            "generated_at": _now_iso(),
            "count": len(rows),
            "jobs": [_row_to_export(row) for row in rows],
        }
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target


def row_to_job(row: sqlite3.Row) -> Job:
    job = Job(
        source=row["source"],
        external_id=row["external_id"] or "",
        title=row["title"],
        company=row["company"] or "",
        url=row["url"] or "",
        location=row["location"] or "",
        tags=json.loads(row["tags"] or "[]"),
        description=row["summary"] or "",
        salary=row["salary"] or "",
        posted_at=parse_date(row["posted_at"]),
        score=row["score"] or 0,
        reasons=json.loads(row["reasons"] or "[]"),
    )
    return job


def _row_to_export(row: sqlite3.Row) -> dict[str, object]:
    data = row_to_job(row).to_dict()
    data["key"] = row["key"]
    data["status"] = row["status"]
    data["first_seen"] = row["first_seen"]
    data["notified_at"] = row["notified_at"]
    return data


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
