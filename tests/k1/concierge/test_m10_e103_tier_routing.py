"""
Tests for M10 E10.3 -- Tier Routing & Safety.

Covers:
  - E10.3.1: AUTO tier in dispatch_task reads from SS control
  - E10.3.2: HIGH-tier PassthroughPlannerStub (no more fail-fast)
  - E10.3.3: CRISIS short-circuit (canned response, no LLM)
  - E10.3.4: Phase1Classified and TaskRouted observability events
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from k1.concierge.bus.builders import build_phase1_classified, build_task_routed
from k1.concierge.events.conversation import Phase1Classified, TaskRouted
from k1.sessionstate.sections.control import ControlSection

# =========================================================================
# E10.3.1 -- AUTO tier from SS control
# =========================================================================


class TestAutoTierDispatch:
    """P3.4c: dispatch_task derives tier from `plan: bool` + signals (no SS read)."""

    def _tool_ctx(self) -> MagicMock:
        ctx = MagicMock()
        ctx.session_manager = MagicMock()
        return ctx

    def test_default_routes_low(self):
        from k1.concierge.tools.implementations import execute_dispatch_task

        result = execute_dispatch_task(
            {"intents": [{"action": "test"}]},
            self._tool_ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["tier"] == "LOW"
        assert result.data["_dispatch"]["plan"] is False

    def test_explicit_plan_routes_medium(self):
        from k1.concierge.tools.implementations import execute_dispatch_task

        result = execute_dispatch_task(
            {"intents": [{"action": "test"}], "plan": True},
            self._tool_ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["tier"] == "MEDIUM"
        assert result.data["_dispatch"]["plan"] is True

    def test_legacy_tier_arg_ignored(self):
        from k1.concierge.tools.implementations import execute_dispatch_task

        result = execute_dispatch_task(
            {"intents": [{"action": "test"}], "tier": "HIGH"},
            self._tool_ctx(),
        )
        assert result.status == "ok"
        assert result.data["_dispatch"]["tier"] == "LOW"


# =========================================================================
# E10.3.3 -- CRISIS short-circuit
# =========================================================================


class TestCrisisShortCircuit:
    """CRISIS safety band -> canned response, no LLM invocation."""

    def test_crisis_emits_final_response(self):
        """_deliver_crisis_response emits a final_response event."""
        from k1.concierge.fsm.controller import ConciergeController

        ctrl = object.__new__(ConciergeController)
        bus = MagicMock()
        ctrl._bus = bus

        envelope = MagicMock()
        envelope.envelope_id = 42

        ctrl._deliver_crisis_response(envelope)
        assert bus.publish.called
        published_env = bus.publish.call_args[0][0]
        assert published_env.topic == "k1.response.final.v1"

    def test_crisis_response_contains_helpline_info(self):
        import json

        from k1.concierge.fsm.controller import ConciergeController

        ctrl = object.__new__(ConciergeController)
        bus = MagicMock()
        ctrl._bus = bus

        envelope = MagicMock()
        envelope.envelope_id = 42

        ctrl._deliver_crisis_response(envelope)
        published_env = bus.publish.call_args[0][0]
        payload = json.loads(published_env.payload.decode())
        assert "988" in payload["text"]
        assert payload["source"] == "crisis_protocol"
        assert payload["safety_band"] == "CRISIS"


# =========================================================================
# E10.3.2 -- HIGH-tier PassthroughPlannerStub
# =========================================================================


class TestHighTierRouting:
    """HIGH tier no longer emits task_failed."""

    def test_high_tier_does_not_emit_task_failed(self):
        """After M10, HIGH tier should route through MEDIUM path."""
        from k1.concierge.fsm.controller import ConciergeController
        from k1.concierge.task.complexity import ComplexityTier
        from k1.concierge.task.dispatch import TaskDispatch
        from k1.concierge.task.intent import TaskIntent

        ctrl = object.__new__(ConciergeController)
        bus = MagicMock()
        router = MagicMock()
        ctrl._bus = bus
        ctrl._router = router
        ctrl._ss = None
        ctrl._active_task_ids = set()
        ctrl._control_ext = MagicMock()
        ctrl._orchestrator = None  # No orchestrator -> MEDIUM falls through to Back
        ctrl._weave_batcher = None
        ctrl._state = MagicMock(name="EXECUTING")

        dispatch = TaskDispatch(
            intents=[TaskIntent(action="test", params={})],
            tier=ComplexityTier.HIGH,
            safety_band="GREEN",
        )
        envelope = MagicMock()
        envelope.envelope_id = 99
        envelope.topic = "k1.orchestration.task.dispatch.v1"

        ctrl._route_via_orchestrator(envelope, dispatch)

        # Should NOT have emitted task_failed
        for call in bus.publish.call_args_list:
            env = call[0][0]
            assert (
                env.topic != "k1.orchestration.task.failed.v1"
            ), "HIGH tier should not emit task_failed after M10"

        # Should have delivered to back (MEDIUM fallback path)
        assert router.deliver.called


# =========================================================================
# E10.3.4 -- Observability events
# =========================================================================


class TestObservabilityEvents:
    """Phase1Classified and TaskRouted event schemas."""

    def test_phase1_classified_event_schema(self):
        evt = Phase1Classified(
            turn_number=5,
            intent_primary="log_memory",
            domain_primary="FAMILY",
            safety_band="GREEN",
            emotion_primary="joy",
            classification_latency_ms=18.5,
            is_degraded=False,
            derived_plan=True,
        )
        payload = evt.to_payload()
        assert payload["turn_number"] == 5
        assert payload["derived_plan"] is True
        assert payload["intent_primary"] == "log_memory"
        assert payload["is_degraded"] is False

    def test_task_routed_event_schema(self):
        evt = TaskRouted(
            task_id="task-123",
            assigned_tier="HIGH",
            routing_path="planner_passthrough",
            budget_limit=20,
        )
        payload = evt.to_payload()
        assert payload["task_id"] == "task-123"
        assert payload["assigned_tier"] == "HIGH"
        assert payload["routing_path"] == "planner_passthrough"
        assert payload["budget_limit"] == 20

    def test_phase1_classified_builder_produces_envelope(self):
        env = build_phase1_classified(
            payload={"derived_plan": False},
            parent_id=10,
        )
        assert env.topic == "k1.phase1.classified.v1"

    def test_task_routed_builder_produces_envelope(self):
        env = build_task_routed(
            payload={"task_id": "task-1", "assigned_tier": "MEDIUM"},
            parent_id=20,
        )
        assert env.topic == "k1.task.routed.v1"
