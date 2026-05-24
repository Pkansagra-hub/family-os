"""P3.4b: ToolDispatcher tier collapse tests (k1 mirror of POC P3.2).

Verifies that:
- Canonical 'simple' / 'plan' / 'crisis' buckets match the old LOW/MEDIUM/HIGH membership.
- Legacy tier strings (LOW/MEDIUM/HIGH/CRISIS) alias correctly.
- Budget limits reflect the 2-bucket collapse.
- Factory functions accept legacy strings without error.
"""

from __future__ import annotations

import pytest

from k1.concierge.tools.dispatcher import (
    _TIER_ALIAS,
    BUDGET_LIMITS,
    FRONT_TIER_ALLOWLISTS,
    create_back_dispatcher,
    create_front_dispatcher,
)
from k1.concierge.tools.schemas_back import BACK_TIER_ALLOWLISTS

# =========================================================================
# Front allowlist membership
# =========================================================================


class TestFrontAllowlists:
    """FRONT_TIER_ALLOWLISTS canonical bucket membership."""

    def test_simple_front_matches_old_low(self):
        expected = {
            "update_beliefs",
            "update_scoreboard",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "recall_memory",
            "summarize_context",
            "dispatch_task",
            "discover_capabilities",
            "invoke_capability",
        }
        assert set(FRONT_TIER_ALLOWLISTS["simple"]) == expected

    def test_plan_front_adds_promote_belief(self):
        assert "promote_belief" in FRONT_TIER_ALLOWLISTS["plan"]
        assert "promote_belief" not in FRONT_TIER_ALLOWLISTS["simple"]

    def test_plan_front_is_superset_of_simple(self):
        assert set(FRONT_TIER_ALLOWLISTS["simple"]) < set(FRONT_TIER_ALLOWLISTS["plan"])

    def test_crisis_front_is_empty(self):
        assert len(FRONT_TIER_ALLOWLISTS["crisis"]) == 0

    def test_legacy_low_equals_simple(self):
        assert set(FRONT_TIER_ALLOWLISTS["LOW"]) == set(FRONT_TIER_ALLOWLISTS["simple"])

    def test_legacy_medium_equals_plan(self):
        assert set(FRONT_TIER_ALLOWLISTS["MEDIUM"]) == set(FRONT_TIER_ALLOWLISTS["plan"])

    def test_legacy_high_equals_plan(self):
        assert set(FRONT_TIER_ALLOWLISTS["HIGH"]) == set(FRONT_TIER_ALLOWLISTS["plan"])

    def test_legacy_crisis_is_empty(self):
        assert len(FRONT_TIER_ALLOWLISTS["CRISIS"]) == 0


# =========================================================================
# Back allowlist membership
# =========================================================================


class TestBackAllowlists:
    """BACK_TIER_ALLOWLISTS canonical bucket membership (k1: incl. batch_invoke_capabilities)."""

    def test_simple_back_matches_old_low(self):
        expected = {
            "recall_memory",
            "discover_capabilities",
            "invoke_capability",
            "batch_invoke_capabilities",
            "submit_result",
        }
        assert set(BACK_TIER_ALLOWLISTS["simple"]) == expected

    def test_plan_back_adds_fabric_tools(self):
        assert "spawn_via_fabric" in BACK_TIER_ALLOWLISTS["plan"]
        assert "execute_workflow" in BACK_TIER_ALLOWLISTS["plan"]
        assert "spawn_via_fabric" not in BACK_TIER_ALLOWLISTS["simple"]

    def test_plan_back_is_superset_of_simple(self):
        assert set(BACK_TIER_ALLOWLISTS["simple"]) < set(BACK_TIER_ALLOWLISTS["plan"])

    def test_legacy_low_equals_simple_back(self):
        assert set(BACK_TIER_ALLOWLISTS["LOW"]) == set(BACK_TIER_ALLOWLISTS["simple"])

    def test_legacy_medium_equals_plan_back(self):
        assert set(BACK_TIER_ALLOWLISTS["MEDIUM"]) == set(BACK_TIER_ALLOWLISTS["plan"])

    def test_legacy_high_equals_plan_back(self):
        assert set(BACK_TIER_ALLOWLISTS["HIGH"]) == set(BACK_TIER_ALLOWLISTS["plan"])


# =========================================================================
# Budget limits
# =========================================================================


class TestBudgetLimits:
    """BUDGET_LIMITS 2-bucket values."""

    def test_simple_budget(self):
        assert BUDGET_LIMITS["simple"] == 400

    def test_plan_budget(self):
        assert BUDGET_LIMITS["plan"] == 400

    def test_crisis_budget(self):
        assert BUDGET_LIMITS["crisis"] == 400

    def test_legacy_low_budget(self):
        assert BUDGET_LIMITS["LOW"] == BUDGET_LIMITS["simple"]

    def test_legacy_medium_budget(self):
        assert BUDGET_LIMITS["MEDIUM"] == BUDGET_LIMITS["plan"]

    def test_legacy_high_budget_equals_medium(self):
        assert BUDGET_LIMITS["HIGH"] == BUDGET_LIMITS["plan"]


# =========================================================================
# Alias map
# =========================================================================


class TestTierAliasMap:
    """_TIER_ALIAS routing."""

    def test_low_maps_to_simple(self):
        assert _TIER_ALIAS["LOW"] == "simple"

    def test_medium_maps_to_plan(self):
        assert _TIER_ALIAS["MEDIUM"] == "plan"

    def test_high_maps_to_plan(self):
        assert _TIER_ALIAS["HIGH"] == "plan"

    def test_crisis_maps_to_crisis(self):
        assert _TIER_ALIAS["CRISIS"] == "crisis"

    def test_canonical_simple_passes_through(self):
        assert _TIER_ALIAS["simple"] == "simple"

    def test_canonical_plan_passes_through(self):
        assert _TIER_ALIAS["plan"] == "plan"


# =========================================================================
# Factory backward-compat
# =========================================================================


class TestFactoryBackwardCompat:
    """create_front_dispatcher and create_back_dispatcher accept legacy tier strings."""

    def _ctx(self):
        from unittest.mock import MagicMock

        from k1.concierge.tools.implementations import ToolContext

        return ToolContext(session_manager=MagicMock())

    @pytest.mark.parametrize("tier", ["LOW", "MEDIUM", "HIGH", "simple", "plan"])
    def test_front_dispatcher_created_for_tier(self, tier):
        d = create_front_dispatcher(tier=tier, ctx=self._ctx())
        assert d.actor == "front"
        assert d.tier == tier

    @pytest.mark.parametrize("tier", ["LOW", "MEDIUM", "HIGH", "simple", "plan"])
    def test_back_dispatcher_created_for_tier(self, tier):
        d = create_back_dispatcher(tier=tier, ctx=self._ctx())
        assert d.actor == "back"

    def test_front_low_allowlist_matches_simple(self):
        d_low = create_front_dispatcher(tier="LOW", ctx=self._ctx())
        d_simple = create_front_dispatcher(tier="simple", ctx=self._ctx())
        assert d_low.allowlist == d_simple.allowlist

    def test_front_medium_allowlist_matches_plan(self):
        d_med = create_front_dispatcher(tier="MEDIUM", ctx=self._ctx())
        d_plan = create_front_dispatcher(tier="plan", ctx=self._ctx())
        assert d_med.allowlist == d_plan.allowlist

    def test_front_high_allowlist_matches_plan(self):
        d_high = create_front_dispatcher(tier="HIGH", ctx=self._ctx())
        d_plan = create_front_dispatcher(tier="plan", ctx=self._ctx())
        assert d_high.allowlist == d_plan.allowlist
