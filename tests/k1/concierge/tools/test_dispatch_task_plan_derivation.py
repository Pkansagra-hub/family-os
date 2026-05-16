"""P3.4c: dispatch_task plan-derivation + per-task back dispatcher tests (k1 mirror of POC P3.3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k1.concierge.tools.dispatcher import create_back_dispatcher
from k1.concierge.tools.implementations import ToolContext, execute_dispatch_task

# =========================================================================
# dispatch_task plan derivation
# =========================================================================


class TestDispatchTaskPlanDerivation:
    """`execute_dispatch_task` derives ComplexityTier from `plan: bool` + signals."""

    def _ctx(self):
        return ToolContext(session_manager=MagicMock())

    def test_default_plan_false_routes_low(self):
        result = execute_dispatch_task(
            {"intents": [{"action": "lookup"}]},
            self._ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["plan"] is False
        assert result.data["_dispatch"]["tier"] == "LOW"

    def test_explicit_plan_true_routes_medium(self):
        result = execute_dispatch_task(
            {"intents": [{"action": "lookup"}], "plan": True},
            self._ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["plan"] is True
        assert result.data["_dispatch"]["tier"] == "MEDIUM"

    def test_multi_intent_bundle_stays_low_without_plan(self):
        result = execute_dispatch_task(
            {"intents": [{"action": "search"}, {"action": "summarize"}]},
            self._ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["plan"] is False
        assert result.data["_dispatch"]["tier"] == "LOW"

    def test_explicit_high_complexity_routes_high(self):
        result = execute_dispatch_task(
            {"intents": [{"action": "research"}], "complexity": "HIGH"},
            self._ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["plan"] is True
        assert result.data["_dispatch"]["tier"] == "HIGH"

    def test_depends_on_auto_escalates_to_plan(self):
        result = execute_dispatch_task(
            {
                "intents": [{"action": "process"}],
                "depends_on": "task-abc12345",
            },
            self._ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["plan"] is True
        assert result.data["_dispatch"]["tier"] == "MEDIUM"

    def test_single_intent_no_deps_stays_low(self):
        result = execute_dispatch_task(
            {"intents": [{"action": "greet"}], "plan": False},
            self._ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["plan"] is False
        assert result.data["_dispatch"]["tier"] == "LOW"

    def test_invalid_depends_on_ignored_does_not_escalate(self):
        result = execute_dispatch_task(
            {
                "intents": [{"action": "lookup"}],
                "depends_on": "do the thing",
            },
            self._ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["plan"] is False
        assert result.data["_dispatch"]["tier"] == "LOW"

    def test_no_ss_read_on_dispatch(self):
        sm = MagicMock()
        ctx = ToolContext(session_manager=sm)
        execute_dispatch_task({"intents": [{"action": "lookup"}]}, ctx)
        sm.get_section.assert_not_called()

    def test_legacy_tier_arg_ignored(self):
        result = execute_dispatch_task(
            {"intents": [{"action": "lookup"}], "tier": "HIGH"},
            self._ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["tier"] == "LOW"
        assert result.data["_dispatch"]["plan"] is False


# =========================================================================
# Per-task back dispatcher rebind
# =========================================================================


class TestBackDispatcherRebind:
    """`_maybe_rebind_back_dispatcher` creates a fresh dispatcher per task tier."""

    def _ctx(self):
        return ToolContext(session_manager=MagicMock())

    def test_rebind_low_creates_fresh_simple_dispatcher(self):
        from k1.concierge.actors.back import _maybe_rebind_back_dispatcher

        d = create_back_dispatcher(tier="simple", ctx=self._ctx())
        rebound = _maybe_rebind_back_dispatcher(d, "LOW", bus=MagicMock())
        assert rebound is not d
        assert rebound.tier == "simple"

    def test_rebind_medium_upgrades_to_plan(self):
        from k1.concierge.actors.back import _maybe_rebind_back_dispatcher

        d = create_back_dispatcher(tier="simple", ctx=self._ctx())
        rebound = _maybe_rebind_back_dispatcher(d, "MEDIUM", bus=MagicMock())
        assert rebound is not d
        assert rebound.tier == "plan"
        assert "spawn_via_fabric" in rebound.allowlist

    def test_rebind_high_upgrades_to_plan(self):
        from k1.concierge.actors.back import _maybe_rebind_back_dispatcher

        d = create_back_dispatcher(tier="simple", ctx=self._ctx())
        rebound = _maybe_rebind_back_dispatcher(d, "HIGH", bus=MagicMock())
        assert rebound.tier == "plan"
        assert "execute_workflow" in rebound.allowlist

    def test_rebind_unknown_tier_creates_fresh_simple_dispatcher(self):
        from k1.concierge.actors.back import _maybe_rebind_back_dispatcher

        d = create_back_dispatcher(tier="simple", ctx=self._ctx())
        rebound = _maybe_rebind_back_dispatcher(d, "BOGUS", bus=MagicMock())
        assert rebound is not d
        assert rebound.tier == "simple"

    def test_rebind_preserves_ctx(self):
        from k1.concierge.actors.back import _maybe_rebind_back_dispatcher

        ctx = self._ctx()
        d = create_back_dispatcher(tier="simple", ctx=ctx)
        rebound = _maybe_rebind_back_dispatcher(d, "MEDIUM", bus=MagicMock())
        assert rebound.ctx is ctx

    def test_bind_tool_context_sets_safety_band(self):
        from k1.concierge.actors.back import _bind_tool_context

        ctx = self._ctx()
        d = create_back_dispatcher(tier="simple", ctx=ctx)
        _bind_tool_context(
            d,
            trace_id="trace-1",
            session_id="sess-1",
            task_id="task-1",
            safety_band="RED",
        )
        assert ctx.safety_band == "RED"

    def test_effective_task_safety_prefers_dispatch_payload(self):
        from k1.concierge.actors.back import _effective_task_safety_band

        assert (
            _effective_task_safety_band(
                {"safety_band": "AMBER"},
                {"safety_band": "GREEN"},
            )
            == "AMBER"
        )


# =========================================================================
# KernelConfig.tool_tier removed
# =========================================================================


class TestKernelConfigToolTierRemoved:
    """P3.4c: `tool_tier` field is gone from KernelConfig."""

    def test_kernel_config_has_no_tool_tier_field(self):
        from dataclasses import fields

        from k1.concierge.config.kernel import KernelConfig

        names = {f.name for f in fields(KernelConfig)}
        assert "tool_tier" not in names

    def test_kernel_config_rejects_tool_tier_kwarg(self):
        from k1.concierge.config.kernel import KernelConfig

        with pytest.raises(TypeError):
            KernelConfig(tool_tier="LOW")  # type: ignore[call-arg]


# =========================================================================
# DISPATCH_TASK_SCHEMA includes plan param
# =========================================================================


class TestDispatchTaskSchema:
    """`plan: bool` is exposed to the LLM via DISPATCH_TASK_SCHEMA."""

    def test_plan_param_in_schema(self):
        from k1.concierge.tools.schemas_front import DISPATCH_TASK_SCHEMA

        props = DISPATCH_TASK_SCHEMA.parameters["properties"]
        assert "plan" in props
        assert props["plan"]["type"] == "boolean"
        assert props["plan"].get("default") is False

    def test_plan_not_in_required(self):
        from k1.concierge.tools.schemas_front import DISPATCH_TASK_SCHEMA

        assert "plan" not in DISPATCH_TASK_SCHEMA.parameters["required"]
