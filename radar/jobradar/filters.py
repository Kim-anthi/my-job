"""Keyword matching: include/exclude rules plus a relevance score.

Two design notes that matter in practice:

* Exclude rules are split into title-only and anywhere. "Java backend" in a job
  description is normal for a mobile role ("you will work with our Java backend
  team"); in the *title* it means the role is not for you.
* Hits are weighted by where and what they are: a title hit outranks a
  distinctive body hit ("flutter" in the description), which outranks a generic
  one ("android", which half the industry mentions). ``min_score`` then reads as
  a policy: at 4, a title match passes, two distinctive body mentions pass, and
  a pile of generic ones does not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .models import Job

TITLE_HIT_POINTS = 4
STRONG_BODY_HIT_POINTS = 3
BODY_HIT_POINTS = 1
# Generic terms nudge the score, they never decide a job on their own: without
# this cap, a platform role listing "Android, iOS, Kotlin, Firebase" would clear
# a min_score of 4 on vocabulary alone.
GENERIC_POINTS_CAP = 2

_WORDISH_RE = re.compile(r"^[\w\s]+$")


def compile_terms(terms: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Compile keywords to word-boundary patterns.

    Word boundaries stop ``dart`` matching "Dartmouth" and ``ios`` matching
    "bios". Terms containing punctuation (c++, ci/cd, .net) fall back to a
    plain escaped substring, where boundaries would misfire.
    """
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for term in terms:
        term = term.strip()
        if not term:
            continue
        if _WORDISH_RE.match(term):
            body = r"\s+".join(re.escape(part) for part in term.split())
            pattern = re.compile(rf"\b{body}\b", re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
        compiled.append((term, pattern))
    return compiled


@dataclass
class Rules:
    include_title: list[tuple[str, re.Pattern[str]]]
    include_strong: list[tuple[str, re.Pattern[str]]]
    include_anywhere: list[tuple[str, re.Pattern[str]]]
    exclude_title: list[tuple[str, re.Pattern[str]]]
    exclude_anywhere: list[tuple[str, re.Pattern[str]]]
    require_include_in_title: bool = False
    min_score: int = 3
    max_age_days: int | None = 21

    @classmethod
    def from_config(cls, config: dict) -> "Rules":
        include = config.get("include", {})
        exclude = config.get("exclude", {})
        match = config.get("match", {})
        max_age = match.get("max_age_days", 21)
        return cls(
            include_title=compile_terms(include.get("title_any", [])),
            include_strong=compile_terms(include.get("anywhere_strong", [])),
            include_anywhere=compile_terms(include.get("anywhere_any", [])),
            exclude_title=compile_terms(exclude.get("title_any", [])),
            exclude_anywhere=compile_terms(exclude.get("anywhere_any", [])),
            require_include_in_title=bool(match.get("require_include_in_title", False)),
            min_score=int(match.get("min_score", 3)),
            max_age_days=None if max_age in (None, 0) else int(max_age),
        )


@dataclass
class Match:
    ok: bool
    score: int
    reasons: list[str]
    rejected_by: str | None = None


def evaluate(job: Job, rules: Rules, now: datetime | None = None) -> Match:
    title = job.title.lower()
    haystack = job.haystack

    for term, pattern in rules.exclude_title:
        if pattern.search(title):
            return Match(False, 0, [], f"excluded-title-keyword ({term})")

    for term, pattern in rules.exclude_anywhere:
        if pattern.search(haystack):
            return Match(False, 0, [], f"excluded-keyword ({term})")

    if rules.max_age_days is not None:
        age = job.age_days(now)
        if age is not None and age > rules.max_age_days:
            return Match(False, 0, [], f"too-old ({age:.0f}d)")

    score = 0
    reasons: list[str] = []
    title_hit = False
    for term, pattern in rules.include_title:
        if pattern.search(title):
            score += TITLE_HIT_POINTS
            reasons.append(f"title:{term}")
            title_hit = True

    for term, pattern in rules.include_strong:
        if pattern.search(haystack):
            score += STRONG_BODY_HIT_POINTS
            reasons.append(f"strong:{term}")

    generic_score = 0
    for term, pattern in rules.include_anywhere:
        if pattern.search(haystack):
            generic_score += BODY_HIT_POINTS
            reasons.append(f"body:{term}")
    score += min(generic_score, GENERIC_POINTS_CAP)

    if rules.require_include_in_title and not title_hit:
        return Match(False, score, reasons, "no-include-keyword-in-title")

    if score < rules.min_score:
        return Match(False, score, reasons, f"below-min-score ({score}/{rules.min_score})")

    return Match(True, score, reasons)


def apply(
    jobs: list[Job], rules: Rules, now: datetime | None = None
) -> tuple[list[Job], dict[str, int]]:
    """Return matching jobs (best first) and a tally of rejection reasons."""
    matched: list[Job] = []
    rejections: dict[str, int] = {}
    for job in jobs:
        result = evaluate(job, rules, now)
        if result.ok:
            job.score = result.score
            job.reasons = result.reasons
            matched.append(job)
        else:
            bucket = (result.rejected_by or "unknown").split(" (")[0]
            rejections[bucket] = rejections.get(bucket, 0) + 1

    matched.sort(
        key=lambda job: (job.score, job.posted_at.timestamp() if job.posted_at else 0.0),
        reverse=True,
    )
    return matched, rejections
