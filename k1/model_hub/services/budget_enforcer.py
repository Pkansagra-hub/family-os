"""Per-request / per-day budget enforcement [F46].

Enforces cost limits with 3-tier decision: ALLOW, ALLOW_DEGRADED, REJECT.
Tracks spending from HubResponse metadata.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.budget_enforcer
  -> k1.model_hub.types    (Layer 0: BudgetDecision, HubRequest, HubResponse)
  -> k1.model_hub.config   (Layer 0: ModelHubConfig)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: BudgetEnforcer service
- Invariant MH-04: HARD rejection on budget exceeded
- Invariant MH-08: $5/day default daily budget
- Invariant MH-07: Cost from manifest model cost tables
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.types import BudgetDecision, HubRequest, HubResponse

# ===========================================================================
# Budget Check Result
# ===========================================================================


@dataclass(frozen=True)
class BudgetCheckResult:
    """Result of a budget enforcement check."""

    decision: BudgetDecision
    daily_spent_usd: float
    daily_budget_usd: float
    daily_remaining_usd: float
    usage_pct: float
    reason: str = ""


# ===========================================================================
# Spending Record
# ===========================================================================


@dataclass(frozen=True)
class SpendingRecord:
    """Individual spending record from a completed request."""

    request_id: str
    cost_usd: float
    consumer_id: str = ""
    capability: str = ""
    provider_id: str = ""
    model_id: str = ""


# ===========================================================================
# BudgetEnforcer
# ===========================================================================


class BudgetEnforcer:
    """Per-request and per-day budget enforcement (MH-04, MH-08).

    Decision tiers:
      ALLOW:          Budget healthy, proceed normally.
      ALLOW_DEGRADED: Budget >= 80%, force cheapest model.
      REJECT:         Budget exceeded, hard reject (MH-04).

    Thresholds:
      >= 80% usage: ALLOW_DEGRADED (warning).
      >= 100% usage: REJECT.
      Per-request cost_limit: REJECT if estimated cost > limit.

    Daily budget resets via reset_daily().

    Constructor:
        config: ModelHubConfig for daily_budget_usd.
    """

    def __init__(self, config: ModelHubConfig) -> None:
        self._daily_budget_usd = config.daily_budget_usd
        self._daily_spent_usd: float = 0.0
        self._spending_records: List[SpendingRecord] = []

    # -- Check -----------------------------------------------------------------

    def check(self, request: HubRequest) -> BudgetCheckResult:
        """Check if a request is within budget.

        Decision logic:
          1. If daily_spent >= daily_budget -> REJECT (MH-04).
          2. If per-request cost_limit and estimated cost would breach -> REJECT.
          3. If daily_spent >= 80% of budget -> ALLOW_DEGRADED.
          4. Otherwise -> ALLOW.

        Args:
            request: HubRequest to check.

        Returns:
            BudgetCheckResult with decision and usage info.
        """
        remaining = self._daily_budget_usd - self._daily_spent_usd
        usage_pct = (
            (self._daily_spent_usd / self._daily_budget_usd * 100.0)
            if self._daily_budget_usd > 0
            else 0.0
        )

        # 1. Hard reject if budget exceeded (MH-04)
        if self._daily_spent_usd >= self._daily_budget_usd:
            return BudgetCheckResult(
                decision=BudgetDecision.REJECT,
                daily_spent_usd=self._daily_spent_usd,
                daily_budget_usd=self._daily_budget_usd,
                daily_remaining_usd=max(0.0, remaining),
                usage_pct=usage_pct,
                reason="Daily budget exceeded (MH-04)",
            )

        # 2. Per-request cost_limit check
        if request.constraints.cost_limit is not None:
            if remaining < request.constraints.cost_limit:
                return BudgetCheckResult(
                    decision=BudgetDecision.REJECT,
                    daily_spent_usd=self._daily_spent_usd,
                    daily_budget_usd=self._daily_budget_usd,
                    daily_remaining_usd=max(0.0, remaining),
                    usage_pct=usage_pct,
                    reason=f"Remaining budget ${remaining:.4f} < request cost_limit ${request.constraints.cost_limit:.4f}",
                )

        # 3. Warning threshold: >= 80% usage
        if usage_pct >= 80.0:
            return BudgetCheckResult(
                decision=BudgetDecision.ALLOW_DEGRADED,
                daily_spent_usd=self._daily_spent_usd,
                daily_budget_usd=self._daily_budget_usd,
                daily_remaining_usd=max(0.0, remaining),
                usage_pct=usage_pct,
                reason=f"Budget at {usage_pct:.1f}%, forcing cheapest model",
            )

        # 4. Healthy budget
        return BudgetCheckResult(
            decision=BudgetDecision.ALLOW,
            daily_spent_usd=self._daily_spent_usd,
            daily_budget_usd=self._daily_budget_usd,
            daily_remaining_usd=max(0.0, remaining),
            usage_pct=usage_pct,
        )

    # -- Track -----------------------------------------------------------------

    def track(self, response: HubResponse) -> None:
        """Track spending from a completed response.

        Adds the cost_usd from response metadata to daily total.

        Args:
            response: Completed HubResponse with metadata.
        """
        cost = response.metadata.cost_usd
        self._daily_spent_usd += cost
        self._spending_records.append(
            SpendingRecord(
                request_id=response.metadata.request_id,
                cost_usd=cost,
                consumer_id="",
                capability=response.metadata.capability.value,
                provider_id=response.metadata.provider_id,
                model_id=response.metadata.model_id,
            )
        )

    # -- Reset / Query ---------------------------------------------------------

    def reset_daily(self) -> None:
        """Reset daily spending counter. Called by scheduled task."""
        self._daily_spent_usd = 0.0
        self._spending_records.clear()

    @property
    def daily_spent_usd(self) -> float:
        """Current daily spending."""
        return self._daily_spent_usd

    @property
    def daily_budget_usd(self) -> float:
        """Configured daily budget."""
        return self._daily_budget_usd

    @property
    def usage_pct(self) -> float:
        """Current budget usage percentage (0-100)."""
        if self._daily_budget_usd <= 0:
            return 0.0
        return self._daily_spent_usd / self._daily_budget_usd * 100.0

    @property
    def spending_records(self) -> List[SpendingRecord]:
        """All spending records for the current period."""
        return list(self._spending_records)


__all__ = [
    "BudgetCheckResult",
    "BudgetEnforcer",
    "SpendingRecord",
]
