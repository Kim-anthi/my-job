"""Lever-hosted company boards (``jobs.lever.co/<company>``)."""
from __future__ import annotations

from ..dates import parse_date
from ..http import get_json
from ..models import Job

API = "https://api.lever.co/v0/postings/{company}"


def fetch(settings: dict) -> list[Job]:
    handle = settings.get("company")
    if not handle:
        raise ValueError("lever source needs a company handle")

    payload = get_json(API.format(company=handle), params={"mode": "json"})
    if not isinstance(payload, list):
        return []

    display_name = settings.get("name") or handle
    jobs: list[Job] = []
    for entry in payload:
        if not isinstance(entry, dict) or not entry.get("text"):
            continue
        categories = entry.get("categories") or {}
        tags = [
            str(value)
            for key, value in categories.items()
            if key in {"team", "department", "commitment"} and value
        ]
        jobs.append(
            Job(
                source=f"lever:{handle}",
                external_id=str(entry.get("id", "")),
                title=str(entry.get("text", "")),
                company=display_name,
                url=str(entry.get("hostedUrl") or entry.get("applyUrl") or ""),
                description=str(entry.get("descriptionPlain") or entry.get("description") or ""),
                location=str(categories.get("location") or ""),
                tags=tags,
                salary=str((entry.get("salaryRange") or {}).get("currency") or ""),
                posted_at=parse_date(entry.get("createdAt")),
            )
        )
    return jobs
