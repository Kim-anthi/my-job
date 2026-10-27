"""remoteok.com public JSON feed.

The response is a JSON array whose *first* element is a legal notice rather
than a job - it has to be skipped, not parsed.
"""
from __future__ import annotations

from ..dates import parse_date
from ..http import get_json
from ..models import Job

API = "https://remoteok.com/api"


def fetch(settings: dict) -> list[Job]:
    payload = get_json(API, params={"tags": settings.get("tags") or None})
    if not isinstance(payload, list):
        return []

    jobs: list[Job] = []
    for entry in payload:
        if not isinstance(entry, dict) or "legal" in entry or not entry.get("position"):
            continue
        salary = ""
        if entry.get("salary_min") and entry.get("salary_max"):
            salary = f"${entry['salary_min']:,} - ${entry['salary_max']:,}"
        jobs.append(
            Job(
                source="remoteok",
                external_id=str(entry.get("id") or entry.get("slug") or ""),
                title=str(entry.get("position", "")),
                company=str(entry.get("company", "")),
                url=str(entry.get("url") or entry.get("apply_url") or ""),
                description=str(entry.get("description", "")),
                location=str(entry.get("location") or "Remote"),
                tags=[str(tag) for tag in entry.get("tags") or []],
                salary=salary,
                posted_at=parse_date(entry.get("date") or entry.get("epoch")),
            )
        )
    return jobs
