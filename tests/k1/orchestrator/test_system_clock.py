"""
Tests for k1.orchestrator.workflows.system_clock (Issue 4.2.2).

Verifies:
  - SystemClock returns real timestamps (monotonic sanity).
  - FrozenClock returns deterministic fixed values.
  - device_local_time respects timezone parameter.
  - utc_today format is YYYY-MM-DD.
  - utc_now_datetime is timezone-aware UTC.
"""

from __future__ import annotations

import time
from datetime import datetime
from datetime import timezone as tz

from k1.orchestrator.workflows.system_clock import FrozenClock, SystemClock

# ---------------------------------------------------------------------------
# SystemClock
# ---------------------------------------------------------------------------


class TestSystemClockUtcNow:
    """utc_now() returns a reasonable float timestamp."""

    def test_returns_float(self) -> None:
        clock = SystemClock()
        result = clock.utc_now()
        assert isinstance(result, float)

    def test_monotonic_sanity(self) -> None:
        clock = SystemClock()
        t1 = clock.utc_now()
        t2 = clock.utc_now()
        assert t2 >= t1

    def test_close_to_time_time(self) -> None:
        clock = SystemClock()
        before = time.time()
        result = clock.utc_now()
        after = time.time()
        assert before <= result <= after


class TestSystemClockUtcToday:
    """utc_today() returns current date in YYYY-MM-DD format."""

    def test_format(self) -> None:
        clock = SystemClock()
        today = clock.utc_today()
        # Must parse without error
        parsed = datetime.strptime(today, "%Y-%m-%d")
        assert parsed.year >= 2024

    def test_matches_utc_date(self) -> None:
        clock = SystemClock()
        expected = datetime.now(tz.utc).strftime("%Y-%m-%d")
        assert clock.utc_today() == expected


class TestSystemClockDeviceLocalTime:
    """device_local_time() converts to named timezone."""

    def test_utc_default(self) -> None:
        clock = SystemClock()
        result = clock.device_local_time("UTC")
        assert result.tzinfo is not None
        assert str(result.tzinfo) == "UTC"

    def test_named_timezone(self) -> None:
        clock = SystemClock()
        result = clock.device_local_time("US/Eastern")
        assert result.tzinfo is not None

    def test_returns_datetime(self) -> None:
        clock = SystemClock()
        result = clock.device_local_time()
        assert isinstance(result, datetime)


class TestSystemClockUtcNowDatetime:
    """utc_now_datetime() returns timezone-aware UTC datetime."""

    def test_returns_datetime(self) -> None:
        clock = SystemClock()
        result = clock.utc_now_datetime()
        assert isinstance(result, datetime)

    def test_timezone_aware(self) -> None:
        clock = SystemClock()
        result = clock.utc_now_datetime()
        assert result.tzinfo is not None
        assert result.tzinfo == tz.utc


# ---------------------------------------------------------------------------
# FrozenClock
# ---------------------------------------------------------------------------

FROZEN_TS = 1700000000.0  # 2023-11-14T22:13:20 UTC


class TestFrozenClockUtcNow:
    """FrozenClock.utc_now() returns the fixed timestamp."""

    def test_returns_fixed(self) -> None:
        clock = FrozenClock(FROZEN_TS)
        assert clock.utc_now() == FROZEN_TS

    def test_stable_across_calls(self) -> None:
        clock = FrozenClock(FROZEN_TS)
        assert clock.utc_now() == clock.utc_now()


class TestFrozenClockUtcToday:
    """FrozenClock.utc_today() returns the date of the frozen timestamp."""

    def test_returns_correct_date(self) -> None:
        clock = FrozenClock(FROZEN_TS)
        assert clock.utc_today() == "2023-11-14"


class TestFrozenClockDeviceLocalTime:
    """FrozenClock.device_local_time() uses frozen timestamp."""

    def test_utc(self) -> None:
        clock = FrozenClock(FROZEN_TS)
        result = clock.device_local_time("UTC")
        assert result.year == 2023
        assert result.month == 11
        assert result.day == 14


class TestFrozenClockUtcNowDatetime:
    """FrozenClock.utc_now_datetime() returns frozen datetime."""

    def test_returns_frozen(self) -> None:
        clock = FrozenClock(FROZEN_TS)
        result = clock.utc_now_datetime()
        assert result.year == 2023
        assert result.tzinfo == tz.utc


class TestFrozenClockIsSubclass:
    """FrozenClock inherits from SystemClock for injection compatibility."""

    def test_isinstance(self) -> None:
        clock = FrozenClock(FROZEN_TS)
        assert isinstance(clock, SystemClock)
