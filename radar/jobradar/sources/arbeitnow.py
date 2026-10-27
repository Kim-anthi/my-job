"""arbeitnow.com job board API: ``{"data": [...], "links": {...}}``.

Paginated, newest first, no API key. ``pages`` in the config caps how deep to
walk - a couple of pages is plenty when the worker runs every few hours.
"""
from __future__ import annotations

from ..dates import parse_date
from ..http import get_json
from ..models import Job

API = "https://www.arbeitnow.com/api/job-board-api"


def fetch(settings: dict) -> list[Job]:
    pages = max(1, int(settings.get("pages", 2)))
    remote_only = bool(settings.get("remote_only", False))

    jobs: list[Job] = []
    for page in range(1, pages + 1):
        payload = get_json(API, params={"page": page})
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not entries:
            break

        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("title"):
                continue
            if remote_only and not entry.get("remote"):
                continue
            tags = [str(tag) for tag in entry.get("tags") or []]
            tags += [str(kind) for kind in entry.get("job_types") or []]
            jobs.append(
                Job(
                    source="arbeitnow",
                    external_id=str(entry.get("slug", "")),
                    title=str(entry.get("title", "")),
                    company=str(entry.get("company_name", "")),
                    url=str(entry.get("url", "")),
                    description=str(entry.get("description", "")),
                    location=str(entry.get("location") or ("Remote" if entry.get("remote") else "")),
                    tags=tags,
                    posted_at=parse_date(entry.get("created_at")),
                )
            )
    return jobs
