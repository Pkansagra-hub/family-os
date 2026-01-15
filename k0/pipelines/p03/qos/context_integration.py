"""
P03 integration with K0 QoSContext for budget management.

Wraps K0 QoSContext to provide P03-specific budget management for
cross-event queries (fanout) and similarity search (top_k) operations.

Dossier Reference: Section 15.3 K0 QoSContext Integration
K0 Reference: k0/qos/context.py, k0/qos/policy.py

Issue 6.4.2: Fanout/top_k budget management for P03 operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from k0.qos.context import QoSContext
    from k0.qos.policy import QoSTightening
    from k0.qos.scheduler import Scheduler, SchedulerToken

logger = logging.getLogger(__name__)


# Default QoS budgets for P03 operations (from dossier Section 15.3)
P03_QOS_DEFAULTS: dict[str, int] = {
    "fanout_budget": 1000,  # Max cross-event queries per batch
    "top_k_budget": 500,  # Max similarity results per batch
}


@dataclass(frozen=True, slots=True)
class P03BudgetSnapshot:
    """
    Immutable snapshot of current budget state.

    Useful for logging, debugging, and budget planning.
    """

    fanout_remaining: int
    top_k_remaining: int
    fanout_consumed: int
    top_k_consumed: int

    @property
    def fanout_utilization(self) -> float:
        """Percentage of fanout budget consumed (0.0-1.0)."""
        total = self.fanout_remaining + self.fanout_consumed
        if total == 0:
            return 0.0
        return self.fanout_consumed / total

    @property
    def top_k_utilization(self) -> float:
        """Percentage of top_k budget consumed (0.0-1.0)."""
        total = self.top_k_remaining + self.top_k_consumed
        if total == 0:
            return 0.0
        return self.top_k_consumed / total


class P03QoSContext:
    """
    P03 integration with K0 QoSContext for budget management.

    Provides budget tracking and consumption for:
    - fanout_budget: Limits cross-event/cross-table queries during R1-R4
    - top_k_budget: Limits similarity search results from FAISS

    K0 References:
    - k0/qos/context.py: QoSContext.consume_fanout(), QoSContext.consume_top_k()
    - k0/qos/policy.py: apply_qos_obligations(), QoSTightening

    Usage:
        from k0.qos.context import QoSContext
        from k0.qos.scheduler import Scheduler

        scheduler = Scheduler()
        qos_ctx = QoSContext(scheduler=scheduler, fanout_budget=1000, top_k_budget=500)
        p03_ctx = P03QoSContext(qos_ctx)

        # Check and consume budgets
        if p03_ctx.check_fanout_budget(10):
            p03_ctx.consume_fanout(10)

        if p03_ctx.check_top_k_budget(50):
            p03_ctx.consume_top_k(50)
    """

    def __init__(
        self,
        qos_ctx: QoSContext,
        initial_fanout: int | None = None,
        initial_top_k: int | None = None,
    ) -> None:
        """
        Initialize P03 QoS context wrapper.

        Args:
            qos_ctx: K0 QoSContext instance with budgets
            initial_fanout: Override for tracking (uses qos_ctx if None)
            initial_top_k: Override for tracking (uses qos_ctx if None)
        """
        self._qos_ctx = qos_ctx
        self._initial_fanout = initial_fanout or qos_ctx.fanout_budget
        self._initial_top_k = initial_top_k or qos_ctx.top_k_budget

    @property
    def qos_ctx(self) -> QoSContext:
        """Access underlying K0 QoSContext."""
        return self._qos_ctx

    @property
    def fanout_budget(self) -> int:
        """Current remaining fanout budget."""
        return self._qos_ctx.fanout_budget

    @property
    def top_k_budget(self) -> int:
        """Current remaining top_k budget."""
        return self._qos_ctx.top_k_budget

    def check_fanout_budget(self, required: int) -> bool:
        """
        Check if fanout budget allows cross-event queries.

        Used during R1-R4 when linking events across truth layers.
        Does NOT consume budget - use consume_fanout() after check.

        Args:
            required: Number of fanout operations needed

        Returns:
            True if sufficient budget available
        """
        if required < 0:
            raise ValueError("required must be non-negative")
        return self._qos_ctx.fanout_budget >= required

    def consume_fanout(self, amount: int = 1) -> bool:
        """
        Consume fanout budget for cross-event queries.

        Args:
            amount: Number of fanout operations to consume

        Returns:
            True if consumption succeeded, False if insufficient budget

        Note:
            This is a soft failure (returns False) vs. the K0 QoSContext
            which raises QoSBudgetError. Use try_consume_fanout() for
            exception-based flow.
        """
        if amount < 0:
            raise ValueError("amount must be non-negative")
        if self._qos_ctx.fanout_budget < amount:
            logger.warning(
                "Fanout budget insufficient: required=%d, available=%d",
                amount,
                self._qos_ctx.fanout_budget,
            )
            return False

        self._qos_ctx.consume_fanout(amount)
        logger.debug(
            "Consumed fanout: amount=%d, remaining=%d",
            amount,
            self._qos_ctx.fanout_budget,
        )
        return True

    def try_consume_fanout(self, amount: int = 1) -> None:
        """
        Consume fanout budget, raising on insufficient budget.

        Args:
            amount: Number of fanout operations to consume

        Raises:
            QoSBudgetError: If insufficient budget
        """
        self._qos_ctx.consume_fanout(amount)

    def check_top_k_budget(self, required: int) -> bool:
        """
        Check if top_k budget allows similarity search.

        Used during FAISS queries for pattern matching (R2-R4).
        Does NOT consume budget - use consume_top_k() after check.

        Args:
            required: Number of similarity results needed

        Returns:
            True if sufficient budget available
        """
        if required < 0:
            raise ValueError("required must be non-negative")
        return self._qos_ctx.top_k_budget >= required

    def consume_top_k(self, amount: int = 1) -> bool:
        """
        Consume top_k budget for similarity search.

        Args:
            amount: Number of similarity results to consume

        Returns:
            True if consumption succeeded, False if insufficient budget

        Note:
            This is a soft failure (returns False) vs. the K0 QoSContext
            which raises QoSBudgetError. Use try_consume_top_k() for
            exception-based flow.
        """
        if amount < 0:
            raise ValueError("amount must be non-negative")
        if self._qos_ctx.top_k_budget < amount:
            logger.warning(
                "Top-k budget insufficient: required=%d, available=%d",
                amount,
                self._qos_ctx.top_k_budget,
            )
            return False

        self._qos_ctx.consume_top_k(amount)
        logger.debug(
            "Consumed top_k: amount=%d, remaining=%d",
            amount,
            self._qos_ctx.top_k_budget,
        )
        return True

    def try_consume_top_k(self, amount: int = 1) -> None:
        """
        Consume top_k budget, raising on insufficient budget.

        Args:
            amount: Number of similarity results to consume

        Raises:
            QoSBudgetError: If insufficient budget
        """
        self._qos_ctx.consume_top_k(amount)

    def tighten(
        self,
        *,
        fanout: int | None = None,
        top_k: int | None = None,
    ) -> None:
        """
        Tighten budgets to lower values.

        Budgets can only be reduced, not increased. Useful for
        applying policy obligations or adapting to load.

        Args:
            fanout: New fanout limit (ignored if higher than current)
            top_k: New top_k limit (ignored if higher than current)
        """
        self._qos_ctx.tighten(fanout=fanout, top_k=top_k)
        logger.debug(
            "Budgets tightened: fanout=%d, top_k=%d",
            self._qos_ctx.fanout_budget,
            self._qos_ctx.top_k_budget,
        )

    def apply_tightening(self, tightening: QoSTightening) -> None:
        """
        Apply QoS tightening from policy obligations.

        Uses K0 QoSTightening dataclass to update budgets.

        Args:
            tightening: Tightening directives from policy
        """
        if tightening.fanout is not None:
            self._qos_ctx.tighten(fanout=tightening.fanout)
        if tightening.top_k is not None:
            self._qos_ctx.tighten(top_k=tightening.top_k)
        logger.debug(
            "Applied tightening: fanout=%d, top_k=%d",
            self._qos_ctx.fanout_budget,
            self._qos_ctx.top_k_budget,
        )

    def apply_obligations(self, obligations: Sequence[Any]) -> QoSTightening:
        """
        Apply QoS tightening from a list of policy obligations.

        Uses K0 apply_qos_obligations() to extract tightening
        directives and apply them.

        Args:
            obligations: List of policy obligations

        Returns:
            QoSTightening applied (for inspection)
        """
        from k0.qos.policy import apply_qos_obligations

        tightening = apply_qos_obligations(self._qos_ctx, obligations)
        logger.debug(
            "Applied obligations: tightening=%s",
            tightening,
        )
        return tightening

    def acquire_scheduler_token(
        self,
        *,
        band: str,
        port: str,
        cost: int,
    ) -> SchedulerToken:
        """
        Delegate token acquisition to the underlying scheduler.

        Uses QoSContext.acquire() which delegates to Scheduler.acquire().

        Args:
            band: Privacy/QoS band (GREEN/AMBER/RED)
            port: Scheduler port (command/query/sse)
            cost: Token cost for the operation

        Returns:
            SchedulerToken for resource reservation
        """
        return self._qos_ctx.acquire(band=band, port=port, cost=cost)

    def get_budget_snapshot(self) -> P03BudgetSnapshot:
        """
        Get current budget state as immutable snapshot.

        Returns:
            P03BudgetSnapshot with current and consumed values
        """
        fanout_remaining = self._qos_ctx.fanout_budget
        top_k_remaining = self._qos_ctx.top_k_budget

        return P03BudgetSnapshot(
            fanout_remaining=fanout_remaining,
            top_k_remaining=top_k_remaining,
            fanout_consumed=self._initial_fanout - fanout_remaining,
            top_k_consumed=self._initial_top_k - top_k_remaining,
        )

    def get_remaining_capacity(self) -> dict[str, int]:
        """
        Get remaining budget capacity.

        Returns:
            Dict with fanout_budget and top_k_budget remaining
        """
        return {
            "fanout_budget": self._qos_ctx.fanout_budget,
            "top_k_budget": self._qos_ctx.top_k_budget,
        }


def create_p03_qos_context(
    scheduler: Scheduler,
    fanout_budget: int | None = None,
    top_k_budget: int | None = None,
) -> P03QoSContext:
    """
    Factory function to create P03QoSContext with defaults.

    Creates both the underlying K0 QoSContext and the P03 wrapper.

    Args:
        scheduler: K0 Scheduler instance
        fanout_budget: Override default fanout budget (1000)
        top_k_budget: Override default top_k budget (500)

    Returns:
        Configured P03QoSContext
    """
    from k0.qos.context import QoSContext

    fanout = fanout_budget if fanout_budget is not None else P03_QOS_DEFAULTS["fanout_budget"]
    top_k = top_k_budget if top_k_budget is not None else P03_QOS_DEFAULTS["top_k_budget"]

    qos_ctx = QoSContext(
        scheduler=scheduler,
        fanout_budget=fanout,
        top_k_budget=top_k,
    )

    return P03QoSContext(qos_ctx, initial_fanout=fanout, initial_top_k=top_k)
