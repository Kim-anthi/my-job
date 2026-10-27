"""Filter engine tests - no network, these are the rules that decide your day."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobradar import filters  # noqa: E402
from jobradar.models import Job  # noqa: E402

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)

CONFIG = {
    "match": {"min_score": 4, "max_age_days": 21, "require_include_in_title": False},
    "include": {
        "title_any": ["flutter", "mobile engineer", "ios developer"],
        "anywhere_strong": ["flutter", "dart", "react native"],
        "anywhere_any": ["android", "ios", "firebase", "kotlin"],
    },
    "exclude": {
        "title_any": ["intern", "director", "java backend"],
        "anywhere_any": ["unpaid"],
    },
}
RULES = filters.Rules.from_config(CONFIG)


def make_job(title: str, **kwargs: object) -> Job:
    payload: dict = {
        "source": "test",
        "external_id": title,
        "title": title,
        "company": "Acme",
        "url": "https://example.com/1",
        "posted_at": NOW - timedelta(days=1),
    }
    payload.update(kwargs)
    return Job(**payload)  # type: ignore[arg-type]


def test_title_match_passes_on_its_own():
    result = filters.evaluate(make_job("Senior Flutter Engineer"), RULES, NOW)
    assert result.ok
    assert result.score >= filters.TITLE_HIT_POINTS
    assert "title:flutter" in result.reasons


def test_body_only_match_needs_several_hits():
    weak = filters.evaluate(
        make_job("Software Engineer", description="You will touch Android sometimes."),
        RULES,
        NOW,
    )
    assert not weak.ok

    strong = filters.evaluate(
        make_job(
            "Software Engineer",
            description="Dart and Flutter app work, Firebase backend, Android and iOS.",
        ),
        RULES,
        NOW,
    )
    assert strong.ok


def test_generic_body_hits_alone_do_not_qualify():
    """The noise case: a backend-ish role that merely mentions the mobile stack."""
    generic = filters.evaluate(
        make_job(
            "Staff Software Engineer",
            description="Our platform powers Android, iOS and Kotlin clients via Firebase.",
        ),
        RULES,
        NOW,
    )
    assert not generic.ok
    assert "below-min-score" in (generic.rejected_by or "")

    distinctive = filters.evaluate(
        make_job(
            "Staff Software Engineer",
            description="You will ship our Flutter app, written in Dart.",
        ),
        RULES,
        NOW,
    )
    assert distinctive.ok
    assert "strong:flutter" in distinctive.reasons


def test_excluded_title_keyword_rejects():
    result = filters.evaluate(make_job("Flutter Developer Intern"), RULES, NOW)
    assert not result.ok
    assert "excluded-title-keyword" in (result.rejected_by or "")


def test_exclusion_is_title_scoped():
    """'Java backend' in the body must not reject a mobile role."""
    result = filters.evaluate(
        make_job(
            "Flutter Engineer",
            description="You will integrate with our Java backend team.",
        ),
        RULES,
        NOW,
    )
    assert result.ok


def test_exclude_anywhere_rejects_from_body():
    result = filters.evaluate(
        make_job("Flutter Engineer", description="This is an unpaid position."), RULES, NOW
    )
    assert not result.ok


def test_word_boundaries_stop_false_positives():
    """'dart' must not match Dartmouth, 'ios' must not match bios."""
    result = filters.evaluate(
        make_job(
            "Research Assistant",
            company="Dartmouth College",
            description="Flash the bios on lab machines.",
        ),
        RULES,
        NOW,
    )
    assert not result.ok


def test_stale_posting_is_dropped():
    result = filters.evaluate(
        make_job("Flutter Engineer", posted_at=NOW - timedelta(days=60)), RULES, NOW
    )
    assert not result.ok
    assert "too-old" in (result.rejected_by or "")


def test_undated_posting_is_kept():
    result = filters.evaluate(make_job("Flutter Engineer", posted_at=None), RULES, NOW)
    assert result.ok


def test_require_include_in_title():
    strict = filters.Rules.from_config(
        {**CONFIG, "match": {**CONFIG["match"], "require_include_in_title": True}}
    )
    result = filters.evaluate(
        make_job("Software Engineer", description="Dart, Flutter, Firebase, Android, iOS"),
        strict,
        NOW,
    )
    assert not result.ok
    assert result.rejected_by == "no-include-keyword-in-title"


def test_apply_sorts_best_first_and_tallies_rejections():
    jobs = [
        make_job("Backend Engineer", description="python"),
        make_job("Flutter Engineer", description="Dart and Firebase"),
        make_job("Mobile Engineer, iOS Developer", description="Flutter, Dart, Android"),
    ]
    matched, rejections = filters.apply(jobs, RULES, NOW)
    assert [job.title for job in matched] == [
        "Mobile Engineer, iOS Developer",
        "Flutter Engineer",
    ]
    assert sum(rejections.values()) == 1
