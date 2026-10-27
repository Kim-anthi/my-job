"""Dedup and queue behaviour - the part that stops duplicate notifications."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobradar import runner  # noqa: E402
from jobradar.models import Job  # noqa: E402
from jobradar.store import Store  # noqa: E402

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)

CONFIG = {
    "match": {"min_score": 3, "max_age_days": 0},
    "include": {"title_any": ["flutter"], "anywhere_any": ["flutter"]},
    "exclude": {"title_any": [], "anywhere_any": []},
    "notify": {"max_per_run": 2},
    "sources": {},
}


class Recorder:
    """A notifier that remembers what it was asked to send."""

    name = "recorder"

    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.jobs: list[Job] = []
        self.texts: list[str] = []

    def send_job(self, job: Job) -> bool:
        self.jobs.append(job)
        return self.succeed

    def send_text(self, text: str) -> bool:
        self.texts.append(text)
        return self.succeed


def make_job(title: str, company: str = "Acme", source: str = "boardA", ident: str = "") -> Job:
    return Job(
        source=source,
        external_id=ident or f"{source}-{title}",
        title=title,
        company=company,
        url=f"https://example.com/{ident or title}",
        description="Flutter and Dart",
        posted_at=NOW,
    )


def run_with(tmp_path: Path, jobs: list[Job], notifier: Recorder, **kwargs: object):
    """Run the pipeline against a fixed job list instead of live sources."""
    import jobradar.sources as sources_module

    original_build = sources_module.build
    original_fetch = sources_module.fetch_all
    sources_module.build = lambda _config: [("fake", lambda _s: jobs, {})]  # type: ignore[assignment]
    sources_module.fetch_all = lambda _sources: (jobs, [])  # type: ignore[assignment]
    store = Store(tmp_path / "radar.db")  # left open; the caller asserts against it
    try:
        return runner.run(CONFIG, store, [notifier], **kwargs), store
    finally:
        sources_module.build = original_build
        sources_module.fetch_all = original_fetch


def test_same_job_notifies_once_across_runs(tmp_path):
    job = make_job("Flutter Engineer")
    notifier = Recorder()

    stats, _ = run_with(tmp_path, [job], notifier)
    assert stats.notified == 1

    stats, _ = run_with(tmp_path, [job], notifier)
    assert stats.fresh == 0
    assert stats.notified == 0
    assert len(notifier.jobs) == 1


def test_same_posting_on_two_boards_notifies_once(tmp_path):
    notifier = Recorder()
    first = make_job("Senior Flutter Engineer", source="boardA", ident="a1")
    second = make_job("Senior Flutter Engineer (Remote)", source="boardB", ident="b9")

    stats, store = run_with(tmp_path, [first, second], notifier)
    assert stats.notified == 1
    assert stats.cross_source_duplicates == 1
    assert store.counts().duplicates == 1


def test_cap_defers_the_rest_to_the_next_run(tmp_path):
    notifier = Recorder()
    jobs = [make_job(f"Flutter Engineer {i}", ident=str(i)) for i in range(5)]

    stats, _ = run_with(tmp_path, jobs, notifier)
    assert stats.notified == 2
    assert stats.deferred == 3
    assert notifier.texts  # told the user more are queued

    stats, _ = run_with(tmp_path, jobs, notifier)
    assert stats.fresh == 0
    assert stats.notified == 2  # worked through the queue


def test_failed_push_stays_queued(tmp_path):
    failing = Recorder(succeed=False)
    job = make_job("Flutter Engineer")

    stats, store = run_with(tmp_path, [job], failing)
    assert stats.notified == 0
    assert store.counts().pending == 1

    working = Recorder()
    stats, _ = run_with(tmp_path, [job], working)
    assert stats.notified == 1
    assert len(working.jobs) == 1


def test_dry_run_writes_nothing(tmp_path):
    notifier = Recorder()
    stats, store = run_with(tmp_path, [make_job("Flutter Engineer")], notifier, dry_run=True)
    assert stats.matched == 1
    assert store.counts().total == 0


def test_export_json_shape(tmp_path):
    notifier = Recorder()
    _, store = run_with(tmp_path, [make_job("Flutter Engineer")], notifier)
    import json

    target = store.export_json(tmp_path / "latest.json")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["jobs"][0]["title"] == "Flutter Engineer"
    assert payload["jobs"][0]["status"] == "notified"


def test_summary_is_stored_and_exported(tmp_path):
    notifier = Recorder()
    _, store = run_with(tmp_path, [make_job("Flutter Engineer")], notifier)
    import json

    payload = json.loads(
        store.export_json(tmp_path / "latest.json").read_text(encoding="utf-8")
    )
    assert payload["jobs"][0]["summary"] == "Flutter and Dart"


def test_summary_is_trimmed(tmp_path):
    from jobradar.models import SUMMARY_LIMIT

    job = make_job("Flutter Engineer")
    job.description = "Flutter " * 400
    with Store(tmp_path / "radar.db") as store:
        store.record(job)
        stored = store.recent(1)[0].description
    # Trimmed to the cap (a trailing space is then stripped on read-back).
    assert SUMMARY_LIMIT - 1 <= len(stored) <= SUMMARY_LIMIT
    assert len(stored) < len(job.description)


def test_opens_a_database_created_before_the_summary_column(tmp_path):
    """CI restores the database from a cache, so schema changes must migrate."""
    import sqlite3

    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE jobs (
            key TEXT PRIMARY KEY, alt_key TEXT NOT NULL, source TEXT NOT NULL,
            external_id TEXT, title TEXT NOT NULL, company TEXT, url TEXT,
            location TEXT, tags TEXT, salary TEXT, posted_at TEXT,
            score INTEGER NOT NULL DEFAULT 0, reasons TEXT,
            status TEXT NOT NULL DEFAULT 'new', first_seen TEXT NOT NULL,
            notified_at TEXT
        );
        INSERT INTO jobs (key, alt_key, source, title, first_seen, status)
        VALUES ('old-key', 'acme|old-job', 'boardA', 'Old Job',
                '2026-01-01T00:00:00+00:00', 'notified');
        """
    )
    legacy.commit()
    legacy.close()

    with Store(path) as store:
        assert "old-key" in store.known_keys(), "dedup history must survive"
        store.record(make_job("Flutter Engineer"))
        assert store.recent(1)[0].description == "Flutter and Dart"
