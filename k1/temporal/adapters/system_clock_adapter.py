"""System clock adapter for k1.temporal."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from k1.temporal.ports import IClockPort


class SystemClockAdapter(IClockPort):
    """Read UTC wall-clock and monotonic time from the Python runtime."""

    def now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def monotonic_ms(self) -> int:
        return time.monotonic_ns() // 1_000_000


__all__ = ["SystemClockAdapter"]
