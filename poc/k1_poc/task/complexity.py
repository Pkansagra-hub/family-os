"""
poc.k1_poc.task.complexity -- ComplexityTier enum and budget mapping.

V2 Design Ref: Section 8.2 (TaskDispatch schemas, ComplexityTier)
V2 Design Ref: Section 6.2 (BACK_MAX_ITERATIONS table)
V2 Design Ref: Section 11.2.1 (ComplexityTier enum definition)

ComplexityTier determines Back's iteration budget and tool allowlist.
Front assigns the tier during intent analysis based on:
    - Number of intents (bundled = MEDIUM+)
    - Presence of chaining ($ref params = MEDIUM+)
    - Domain complexity heuristics

Budget values from V2 Section 6.2 BACK_MAX_ITERATIONS table:
    LOW    = 4   -- Capability known, invoke -> submit. 2-3 iterations typical.
    MEDIUM = 8   -- discover + 2-3 invokes + submit. May spawn agent.
    HIGH   = 12  -- discover + workflow/spawn + multiple invokes + submit.
"""

from __future__ import annotations

from enum import Enum

from poc.k1_poc.config import get_config


class ComplexityTier(str, Enum):
    """Task complexity classification.

    Each tier maps to a budget_hint (max tool-call iterations) that
    constrains the Back ReAct loop.  Tiers are assigned by Front
    based on intent analysis.

    Values are uppercase strings matching the design doc convention
    (V2 Section 8.2, Section 11.2.1).
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ---------------------------------------------------------------------------
# Budget mapping -- V2 Section 6.2 BACK_MAX_ITERATIONS
# Kept as module-level constant for backward compatibility.
# Runtime code reads from get_config().task.tier_budget.
# ---------------------------------------------------------------------------

TIER_BUDGET: dict[ComplexityTier, int] = {
    ComplexityTier.LOW: 4,
    ComplexityTier.MEDIUM: 8,
    ComplexityTier.HIGH: 12,
}
"""Max tool-call iterations per complexity tier.

Budget prevents runaway ReAct loops:
    LOW=4   -- single-capability lookups (weather, time)
    MEDIUM=8  -- multi-intent bundles (hotel + restaurant)
    HIGH=12 -- chained workflows with intermediate lookups
"""


def budget_for_tier(tier: ComplexityTier) -> int:
    """Return the max tool-call budget for a complexity tier.

    Reads from the central config (task.tier_budget).  Falls back
    to the module-level TIER_BUDGET constant if the tier key is
    missing from config.
    """
    cfg_budget = get_config().task.tier_budget
    return cfg_budget.get(tier.value, TIER_BUDGET[tier])
