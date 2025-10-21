"""Per-request QoS context tracking budgets and scheduler access."""

from __future__ import annotations

from dataclasses import dataclass

from .scheduler import Scheduler, SchedulerToken


class QoSBudgetError(RuntimeError):
    """Raised when QoS budgets are exceeded."""


@dataclass(slots=True)
class QoSContext:
    """Expose scheduler handle and mutable QoS budgets for a request."""

    scheduler: Scheduler
    fanout_budget: int
    top_k_budget: int

    def tighten(self, *, fanout: int | None = None, top_k: int | None = None) -> None:
        """Clamp budgets to tighter values without allowing increases."""

        if fanout is not None:
            self._ensure_non_negative(fanout, "fanout")
            if fanout < self.fanout_budget:
                self.fanout_budget = fanout
        if top_k is not None:
            self._ensure_non_negative(top_k, "top_k")
            if top_k < self.top_k_budget:
                self.top_k_budget = top_k

    def consume_fanout(self, amount: int = 1) -> None:
        """Consume from the fanout budget, raising if exhausted."""

        self._consume("fanout", amount)

    def consume_top_k(self, amount: int = 1) -> None:
        """Consume from the top-k budget, raising if exhausted."""

        self._consume("top_k", amount)

    def acquire(self, *, band: str, port: str, cost: int) -> SchedulerToken:
        """Delegate token acquisition to the scheduler."""

        return self.scheduler.acquire(band=band, port=port, cost=cost)

    def _consume(self, budget: str, amount: int) -> None:
        self._ensure_non_negative(amount, budget)
        attr = f"{budget}_budget"
        remaining = getattr(self, attr)
        if amount > remaining:
            raise QoSBudgetError(f"{budget} budget exceeded")
        setattr(self, attr, remaining - amount)

    @staticmethod
    def _ensure_non_negative(value: int, name: str) -> None:
        if value < 0:
            raise ValueError(f"{name} must be non-negative")


__all__ = [
    "QoSBudgetError",
    "QoSContext",
    "SchedulerToken",
]
