"""DST-safe local/UTC boundary helpers for temporal windows."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


def parse_utc(value: str) -> datetime:
    """Parse an ISO instant and return a UTC-aware datetime."""

    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_local(value: str, timezone_name: str) -> datetime:
    """Parse an ISO local value and attach timezone when missing."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    zone = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def iso(dt: datetime) -> str:
    """Serialize datetime with explicit offset."""

    return dt.isoformat()


def local_midnight(day: date, timezone_name: str) -> datetime:
    """Return local midnight for the date in the requested IANA timezone."""

    return datetime.combine(day, time.min, tzinfo=ZoneInfo(timezone_name))


def local_window_to_utc(start_local: datetime, end_local: datetime) -> tuple[str, str]:
    """Convert a local window to UTC ISO boundaries."""

    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


__all__ = ["iso", "local_midnight", "local_window_to_utc", "parse_local", "parse_utc"]
