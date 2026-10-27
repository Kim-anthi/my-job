"""Greenhouse-hosted company boards.

Any company whose careers page lives at ``boards.greenhouse.io/<board>`` (or
embeds it) exposes this JSON endpoint. ``content=true`` returns the full
description, which the filter engine needs for body matching.
"""
from __future__ import annotations

from ..dates import parse_date
from ..http import get_json
from ..models import Job

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


def fetch(settings: dict) -> list[Job]:
    board = settings.get("board")
    if not board:
        raise ValueError("greenhouse source needs a board token")

    payload = get_json(API.format(board=board), params={"content": "true"})
    entries = payload.get("jobs") if isinstance(payload, dict) else None
    if not entries:
        return []

    company = settings.get("company") or board
    jobs: list[Job] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("title"):
            continue
        departments = [
            str(item.get("name", ""))
            for item in entry.get("departments") or []
            if isinstance(item, dict)
        ]
        jobs.append(
            Job(
                source=f"greenhouse:{board}",
                external_id=str(entry.get("id", "")),
                title=str(entry.get("title", "")),
                company=company,
                url=str(entry.get("absolute_url", "")),
                description=str(entry.get("content", "")),
                location=str((entry.get("location") or {}).get("name", "")),
                tags=departments,
                posted_at=parse_date(entry.get("first_published") or entry.get("updated_at")),
            )
        )
    return jobs
