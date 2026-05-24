"""No-op grounding metrics adapter."""

from __future__ import annotations

from k1.grounding.ports import IGroundingMetricsPort


class NullMetricsAdapter(IGroundingMetricsPort):
    """Accept metrics calls without recording them."""

    def incr(self, name: str, value: int = 1) -> None:
        return None

    def gauge(self, name: str, value: float) -> None:
        return None

    def timer(self, name: str, ms: int) -> None:
        return None


__all__ = ["NullMetricsAdapter"]
