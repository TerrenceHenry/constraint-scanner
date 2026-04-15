from __future__ import annotations

from datetime import date, datetime, timezone


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def today_utc() -> date:
    """Return today's UTC date."""

    return utc_now().date()


def ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime into timezone-aware UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
