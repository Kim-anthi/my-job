"""Generic RSS 2.0 / Atom reader, parsed with the stdlib XML module.

Covers We Work Remotely, Working Nomads, Hacker News "who is hiring" mirrors,
and any company blog-style feed. Many boards encode the company in the title
(``Company: Senior Flutter Engineer``), so ``title_format`` tells the reader how
to split it.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ..dates import parse_date
from ..http import get_text
from ..models import Job

ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
DC = "{http://purl.org/dc/elements/1.1/}"


def fetch(settings: dict) -> list[Job]:
    url = settings.get("url")
    if not url:
        raise ValueError("rss source needs a url")

    root = ET.fromstring(get_text(url).lstrip())
    items = root.findall(".//item") or root.findall(f".//{ATOM}entry")

    label = settings.get("name") or url
    title_format = settings.get("title_format", "title")
    default_company = settings.get("company", "")

    jobs: list[Job] = []
    for item in items:
        raw_title = _text(item, "title", f"{ATOM}title")
        if not raw_title:
            continue
        title, company = _split_title(raw_title, title_format, default_company)
        link = _text(item, "link", f"{ATOM}id") or _atom_link(item)
        tags = [
            (element.text or "").strip()
            for element in list(item.findall("category")) + list(item.findall(f"{ATOM}category"))
            if (element.text or "").strip()
        ]
        tags += [tag for tag in [_text(item, "region", "type")] if tag]

        jobs.append(
            Job(
                source=f"rss:{label}",
                external_id=_text(item, "guid", f"{ATOM}id") or link,
                title=title,
                company=company,
                url=link,
                description=_text(
                    item, "description", f"{CONTENT}encoded", f"{ATOM}summary", f"{ATOM}content"
                ),
                location=_text(item, "region", "location") or settings.get("location", ""),
                tags=tags,
                posted_at=parse_date(
                    _text(item, "pubDate", f"{DC}date", f"{ATOM}published", f"{ATOM}updated")
                ),
            )
        )
    return jobs


def _text(item: ET.Element, *names: str) -> str:
    for name in names:
        element = item.find(name)
        if element is not None and (element.text or "").strip():
            return (element.text or "").strip()
    return ""


def _atom_link(item: ET.Element) -> str:
    for element in item.findall(f"{ATOM}link"):
        href = element.get("href")
        if href and element.get("rel", "alternate") == "alternate":
            return href
    return ""


def _split_title(raw: str, title_format: str, default_company: str) -> tuple[str, str]:
    """Pull the company out of the title when the feed packs it in there."""
    if title_format == "company: title" and ":" in raw:
        company, _, title = raw.partition(":")
        return title.strip(), company.strip()
    if title_format == "title at company" and " at " in raw:
        title, _, company = raw.rpartition(" at ")
        return title.strip(), company.strip()
    return raw.strip(), default_company
