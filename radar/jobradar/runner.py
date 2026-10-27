"""One pass of the radar: fetch, filter, dedup, notify, remember."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import filters, sources
from .models import Job
from .notify import Notifier
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class RunStats:
    fetched: int = 0
    matched: int = 0
    fresh: int = 0
    cross_source_duplicates: int = 0
    notified: int = 0
    deferred: int = 0
    errors: list[str] = field(default_factory=list)
    rejections: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"fetched={self.fetched} matched={self.matched} new={self.fresh} "
            f"notified={self.notified} deferred={self.deferred} "
            f"dupes={self.cross_source_duplicates} errors={len(self.errors)}"
        )


def run(
    config: dict,
    store: Store,
    notifiers: list[Notifier],
    *,
    dry_run: bool = False,
    max_notifications: int | None = None,
) -> RunStats:
    started_at = datetime.now(timezone.utc)
    stats = RunStats()

    live_sources = sources.build(config)
    if not live_sources:
        log.warning("no sources enabled - check the [sources] tables in your config")
        return stats

    all_jobs, stats.errors = sources.fetch_all(live_sources)
    stats.fetched = len(all_jobs)

    rules = filters.Rules.from_config(config)
    matched, stats.rejections = filters.apply(all_jobs, rules, started_at)
    stats.matched = len(matched)

    known_keys = store.known_keys()
    known_alt_keys = store.known_alt_keys()

    fresh: list[Job] = []
    seen_this_run: set[str] = set()
    for job in matched:
        if job.key in known_keys or job.key in seen_this_run:
            continue
        seen_this_run.add(job.key)
        if job.alt_key in known_alt_keys:
            # Same posting, different board: remember it, but stay quiet.
            stats.cross_source_duplicates += 1
            if not dry_run:
                store.record(job, status="duplicate")
            continue
        known_alt_keys.add(job.alt_key)
        fresh.append(job)

    stats.fresh = len(fresh)

    # Record before pushing, so a failed push stays queued instead of vanishing.
    if not dry_run:
        for job in fresh:
            store.record(job, status="new")

    queue = _notification_queue(store, fresh, dry_run=dry_run)
    cap = max_notifications if max_notifications is not None else int(
        config.get("notify", {}).get("max_per_run", 12)
    )
    to_send, deferred = (queue[:cap], queue[cap:]) if cap > 0 else ([], queue)
    stats.deferred = len(deferred)

    for job in to_send:
        delivered = False
        for notifier in notifiers:
            if notifier.send_job(job):
                delivered = True
        if delivered:
            stats.notified += 1
            if not dry_run:
                store.mark_notified(job.key)
        else:
            log.error("no channel accepted %r - leaving it queued", job.title)

    if deferred and stats.notified and notifiers:
        notifiers[0].send_text(
            f"…and {len(deferred)} more match(es) queued for the next run."
        )

    if not dry_run:
        store.log_run(
            started_at=started_at,
            fetched=stats.fetched,
            matched=stats.matched,
            fresh=stats.fresh,
            notified=stats.notified,
            errors=stats.errors,
        )

    return stats


def _notification_queue(store: Store, fresh: list[Job], *, dry_run: bool) -> list[Job]:
    """Jobs still owed a push: last run's leftovers first, then this run's."""
    if dry_run:
        return fresh

    queue: list[Job] = []
    seen: set[str] = set()
    for job in store.pending(limit=200):
        if job.key not in seen:
            seen.add(job.key)
            queue.append(job)
    for job in fresh:
        if job.key not in seen:
            seen.add(job.key)
            queue.append(job)
    return queue
