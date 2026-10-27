"""The one data shape every source is normalised into."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
# Noise that differs between boards for the same posting; stripped before
# building the cross-source dedup key.
_TITLE_NOISE_RE = re.compile(
    r"\b(remote|hybrid|onsite|on-site|contract|full[\s-]?time|part[\s-]?time|"
    r"m\s*/\s*f\s*/\s*d|w\s*/\s*m\s*/\s*d|urgent|hiring|new)\b"
)

SUMMARY_LIMIT = 600

_ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&#39;": "'",
    "&rsquo;": "'",
    "&quot;": '"',
    "&mdash;": "-",
    "&ndash;": "-",
}


def clean_text(raw: str | None) -> str:
    """Strip HTML tags and collapse whitespace; feeds matching and messages."""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    for entity, replacement in _ENTITIES.items():
        text = text.replace(entity, replacement)
    return _WS_RE.sub(" ", text).strip()


def slugify(raw: str) -> str:
    return _SLUG_RE.sub("-", raw.lower()).strip("-")


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    description: str = ""
    location: str = ""
    tags: list[str] = field(default_factory=list)
    salary: str = ""
    posted_at: datetime | None = None
    # Filled in by the filter engine.
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = clean_text(self.title)
        self.company = clean_text(self.company)
        self.location = clean_text(self.location)
        self.description = clean_text(self.description)
        self.salary = clean_text(self.salary)
        self.tags = [clean_text(tag) for tag in self.tags if clean_text(tag)]
        if self.posted_at and self.posted_at.tzinfo is None:
            self.posted_at = self.posted_at.replace(tzinfo=timezone.utc)

    @property
    def key(self) -> str:
        """Stable identity within a source: the primary dedup key."""
        seed = f"{self.source}:{self.external_id or self.url}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]

    @property
    def alt_key(self) -> str:
        """Identity across sources, so one posting on three boards pings once."""
        title = _TITLE_NOISE_RE.sub(" ", self.title.lower())
        return f"{slugify(self.company)}|{slugify(title)}"

    @property
    def haystack(self) -> str:
        parts = [self.title, self.company, self.location, " ".join(self.tags), self.description]
        return " ".join(part for part in parts if part).lower()

    def age_days(self, now: datetime | None = None) -> float | None:
        if not self.posted_at:
            return None
        now = now or datetime.now(timezone.utc)
        return (now - self.posted_at).total_seconds() / 86400

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "source": self.source,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "location": self.location,
            "tags": self.tags,
            "salary": self.salary,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "score": self.score,
            "reasons": self.reasons,
            # Enough for the app's detail view without bloating the committed
            # feed; the full posting is one tap away at `url`.
            "summary": self.description[:SUMMARY_LIMIT],
        }
