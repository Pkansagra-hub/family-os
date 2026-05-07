"""Crash budget for MCP child supervision (MS-5 PR#2).

Extracted from the inline implementation that previously lived in
:mod:`bridge.connector.mcp_process_manager`. The budget answers a single
question: should this adapter be quarantined?

The rule is a sliding-window counter: if more than ``count`` crashes are
observed within ``window_s`` seconds, the adapter transitions to
``quarantined`` and stays there until an operator manually clears it
(via the runtime quarantine reset path documented in
``docs/runbooks``). Quarantined adapters refuse new ``invoke`` calls
with :class:`bridge.connector.contracts.AdapterQuarantinedError`.

The crash budget is per-adapter — one bad adapter cannot starve the
others. Default values match the operational contract in
``bridge/ARCHITECTURE.md`` §11.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

DEFAULT_CRASH_BUDGET_COUNT: int = 3
"""Crashes within :data:`DEFAULT_CRASH_BUDGET_WINDOW_S` that trigger quarantine."""

DEFAULT_CRASH_BUDGET_WINDOW_S: float = 60.0
"""Sliding-window length in seconds."""

# Cap deque length so a long-lived adapter cannot accumulate unbounded crash
# timestamps; the window scan only ever cares about the most recent few.
_CRASH_HISTORY_MAX: int = 32


@dataclass(slots=True)
class CrashBudget:
    """Per-adapter crash counter with sliding-window quarantine logic.

    Not thread-safe in isolation; callers must hold the supervising
    manager's lock when mutating. Time source is injectable so tests can
    drive the window deterministically without ``time.sleep``.
    """

    count: int = DEFAULT_CRASH_BUDGET_COUNT
    window_s: float = DEFAULT_CRASH_BUDGET_WINDOW_S
    _crashes: deque[float] = field(default_factory=lambda: deque(maxlen=_CRASH_HISTORY_MAX))

    def record(self, *, now: float | None = None) -> None:
        """Record a crash at ``now`` (defaults to ``time.monotonic()``)."""
        ts = time.monotonic() if now is None else now
        self._crashes.append(ts)

    def recent_count(self, *, now: float | None = None) -> int:
        """Return the number of crashes within the trailing ``window_s``."""
        ts = time.monotonic() if now is None else now
        cutoff = ts - self.window_s
        # Drop expired entries from the left so the deque stays bounded.
        while self._crashes and self._crashes[0] < cutoff:
            self._crashes.popleft()
        return len(self._crashes)

    def is_over_budget(self, *, now: float | None = None) -> bool:
        """True iff :meth:`recent_count` is at or above :attr:`count`."""
        return self.recent_count(now=now) >= self.count

    def reset(self) -> None:
        """Clear all recorded crashes (operator quarantine reset)."""
        self._crashes.clear()


__all__ = [
    "CrashBudget",
    "DEFAULT_CRASH_BUDGET_COUNT",
    "DEFAULT_CRASH_BUDGET_WINDOW_S",
]
