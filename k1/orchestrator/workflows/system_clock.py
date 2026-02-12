"""
k1.orchestrator.workflows.system_clock -- SystemClock utility (4.2.2).

Trivial UTC clock for the workflow subsystem. Used by WorkflowCompiler
(4.1.3) for DynamicExpr resolution and WorkflowScheduler (4.2.1) for
trigger fire-time computation.

Design:
  - No deps, no constructor args.
  - Independently instantiated (per SPEC-8): Orchestrator and Concierge
    each create their own instance.
  - FrozenClock subclass for deterministic tests.

Anti-hallucination rules:
  - Use ``zoneinfo`` (stdlib Python 3.9+), NOT ``pytz``.
  - SystemClock is trivially instantiated -- no port, no injection.
  - FrozenClock is for tests only -- inject via constructor.

Exports:
  SystemClock, FrozenClock
"""

from __future__ import annotations

import time
from datetime import datetime
from datetime import timezone as tz
from zoneinfo import ZoneInfo


class SystemClock:
    """UTC clock utility for the workflow subsystem.

    Methods:
      utc_now()          -- current UTC timestamp as float.
      utc_today()        -- current UTC date as 'YYYY-MM-DD' string.
      device_local_time  -- UTC converted to a named timezone.
      utc_now_datetime() -- current UTC as datetime (for date math).
    """

    def utc_now(self) -> float:
        """Return current UTC timestamp (``time.time()``)."""
        return time.time()

    def utc_today(self) -> str:
        """Return current UTC date as ``'YYYY-MM-DD'``."""
        return datetime.now(tz.utc).strftime("%Y-%m-%d")

    def device_local_time(self, timezone: str = "UTC") -> datetime:
        """Return current time in the given timezone."""
        return datetime.now(ZoneInfo(timezone))

    def utc_now_datetime(self) -> datetime:
        """Return current UTC as a timezone-aware datetime."""
        return datetime.now(tz.utc)


class FrozenClock(SystemClock):
    """Test double: returns fixed timestamps for deterministic tests.

    Usage::

        clock = FrozenClock(1700000000.0)
        assert clock.utc_now() == 1700000000.0
    """

    def __init__(self, frozen_time: float) -> None:
        self._frozen = frozen_time

    def utc_now(self) -> float:
        return self._frozen

    def utc_today(self) -> str:
        return datetime.fromtimestamp(self._frozen, tz=tz.utc).strftime("%Y-%m-%d")

    def device_local_time(self, timezone: str = "UTC") -> datetime:
        return datetime.fromtimestamp(self._frozen, tz=ZoneInfo(timezone))

    def utc_now_datetime(self) -> datetime:
        return datetime.fromtimestamp(self._frozen, tz=tz.utc)
