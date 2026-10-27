"""Source registry.

A source is a callable ``fetch(settings) -> list[Job]``. Everything is driven
from ``config.toml``, so adding a board means adding one module here plus a
table in the config - no other file needs to change.
"""
from __future__ import annotations

import logging
from typing import Callable, Iterable, NamedTuple

from ..dates import parse_date  # re-exported for convenience
from ..models import Job
from . import arbeitnow, greenhouse, lever, remoteok, remotive, rss

__all__ = ["Source", "build", "fetch_all", "parse_date"]

log = logging.getLogger(__name__)

Fetcher = Callable[[dict], list[Job]]


class Source(NamedTuple):
    name: str
    fetch: Fetcher
    settings: dict


# Simple sources: one config table each.
SINGLE: dict[str, Fetcher] = {
    "remoteok": remoteok.fetch,
    "remotive": remotive.fetch,
    "arbeitnow": arbeitnow.fetch,
}
# List sources: an array of tables, one entry per feed or company board.
MULTI: dict[str, Fetcher] = {
    "rss": rss.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
}


def build(config: dict) -> list[Source]:
    """Turn the ``[sources]`` config into an ordered list of live sources."""
    sources_config = config.get("sources", {})
    sources: list[Source] = []

    for name, fetcher in SINGLE.items():
        settings = sources_config.get(name) or {}
        if settings.get("enabled", False):
            sources.append(Source(name, fetcher, settings))

    for name, fetcher in MULTI.items():
        for entry in sources_config.get(name) or []:
            if not entry.get("enabled", True):
                continue
            label = entry.get("name") or entry.get("board") or entry.get("company") or name
            sources.append(Source(f"{name}:{label}", fetcher, entry))

    return sources


def fetch_all(sources: Iterable[Source]) -> tuple[list[Job], list[str]]:
    """Fetch every source. One broken board must not sink the whole run."""
    jobs: list[Job] = []
    errors: list[str] = []
    for source in sources:
        try:
            found = source.fetch(source.settings)
        except Exception as exc:  # noqa: BLE001 - a dead board is routine
            log.warning("source %s failed: %s", source.name, exc)
            errors.append(f"{source.name}: {exc}")
            continue
        for job in found:
            job.source = source.name
        log.info("source %-28s %3d jobs", source.name, len(found))
        jobs.extend(found)
    return jobs, errors
