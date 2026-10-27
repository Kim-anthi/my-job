"""Date parsing shared by every source (they all disagree on format)."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def parse_date(value: object) -> datetime | None:
    """Best-effort parsing across ISO 8601, unix epochs (s or ms) and RFC 822."""
    if value in (None, "", 0):
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(
                value / 1000 if value > 1e11 else value, tz=timezone.utc
            )
        except (OverflowError, OSError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    text = value.strip()
    if text.isdigit():
        return parse_date(int(text))

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
