"""remotive.com public API: ``{"jobs": [...]}``."""
from __future__ import annotations

from ..dates import parse_date
from ..http import get_json
from ..models import Job

API = "https://remotive.com/api/remote-jobs"


def fetch(settings: dict) -> list[Job]:
    payload = get_json(
        API,
        params={
            "category": settings.get("category", "software-dev"),
            "search": settings.get("search") or None,
            "limit": settings.get("limit", 200),
        },
    )
    entries = payload.get("jobs") if isinstance(payload, dict) else None
    if not entries:
        return []

    return [
        Job(
            source="remotive",
            external_id=str(entry.get("id", "")),
            title=str(entry.get("title", "")),
            company=str(entry.get("company_name", "")),
            url=str(entry.get("url", "")),
            description=str(entry.get("description", "")),
            location=str(entry.get("candidate_required_location") or "Remote"),
            tags=[str(tag) for tag in entry.get("tags") or []],
            salary=str(entry.get("salary") or ""),
            posted_at=parse_date(entry.get("publication_date")),
        )
        for entry in entries
        if isinstance(entry, dict) and entry.get("title")
    ]
