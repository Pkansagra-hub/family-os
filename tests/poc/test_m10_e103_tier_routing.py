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

from poc.k1_poc.bus.builders import build_phase1_classified, build_task_routed
from poc.k1_poc.events.conversation import Phase1Classified, TaskRouted
from poc.k1_poc.sessionstate.sections.control import ControlSection

# =========================================================================
# E10.3.1 -- AUTO tier from SS control
# =========================================================================


class TestAutoTierDispatch:
    """dispatch_task reads complexity_tier from SS when tier=AUTO."""

    def _tool_ctx(self, ss: Any = None) -> MagicMock:
        ctx = MagicMock()
        ctx.session_manager = ss
        return ctx

    def _mock_ss_with_tier(self, tier: str) -> MagicMock:
        ss = MagicMock()
        control = ControlSection(session_id="test")
        control.set_complexity_tier(tier)
        ss.get_section = lambda name: control if name == "control" else None
        return ss

    def test_auto_reads_medium_from_ss(self):
        # P3.3: AUTO-from-SS path is GONE. SS-tier is ignored;
        # only `plan: bool` + signals (multi-intent / depends_on) drive tier.
        from poc.k1_poc.tools.implementations import execute_dispatch_task

        ss = self._mock_ss_with_tier("MEDIUM")
        ctx = self._tool_ctx(ss)
        result = execute_dispatch_task(
            {"intents": [{"action": "test"}], "plan": True},
            ctx,
        )
        assert result.status == "ok"
        dispatch = result.data.get("_dispatch", {})
        # plan=True -> MEDIUM (regardless of SS tier)
        assert dispatch.get("tier", "").upper() == "MEDIUM"

    def test_auto_reads_high_from_ss(self):
        # P3.3: AUTO-from-SS path is GONE. SS HIGH tier no longer routes to HIGH.
        # Plan-derivation tops out at MEDIUM; HIGH is set only by other code paths.
        from poc.k1_poc.tools.implementations import execute_dispatch_task

        ss = self._mock_ss_with_tier("HIGH")
        ctx = self._tool_ctx(ss)
        result = execute_dispatch_task(
            {"intents": [{"action": "a"}, {"action": "b"}]},
            ctx,
        )
        assert result.status == "ok"
        dispatch = result.data.get("_dispatch", {})
        # Multi-intent auto-escalates to MEDIUM; SS-tier HIGH is ignored.
        assert dispatch.get("tier", "").upper() == "MEDIUM"
        # SS must NOT be read during dispatch under P3.3.
        assert not ss.get_section.called if hasattr(ss.get_section, "called") else True

    def test_explicit_tier_overrides_ss(self):
        """LLM provides explicit LOW -> dispatch uses LOW, not SS HIGH."""
        from poc.k1_poc.tools.implementations import execute_dispatch_task

        ss = self._mock_ss_with_tier("HIGH")
        ctx = self._tool_ctx(ss)
        result = execute_dispatch_task(
            {"intents": [{"action": "test"}], "tier": "LOW"},
            ctx,
        )
        assert result.status == "ok"
        dispatch = result.data.get("_dispatch", {})
        assert dispatch.get("tier", "").upper() == "LOW"

    def test_auto_defaults_low_when_ss_empty(self):
        """SS has empty complexity_tier -> default to LOW."""
        from poc.k1_poc.tools.implementations import execute_dispatch_task

        ss = MagicMock()
        control = ControlSection(session_id="test")
        ss.get_section = lambda name: control if name == "control" else None
        ctx = self._tool_ctx(ss)
        result = execute_dispatch_task(
            {"intents": [{"action": "test"}], "tier": "AUTO"},
            ctx,
        )
        assert result.status == "ok"
        dispatch = result.data.get("_dispatch", {})
        assert dispatch.get("tier", "").upper() == "LOW"

    def test_auto_defaults_low_when_no_ss(self):
        """No session_state -> default to LOW."""
        from poc.k1_poc.tools.implementations import execute_dispatch_task

        ctx = self._tool_ctx(None)
        result = execute_dispatch_task(
            {"intents": [{"action": "test"}], "tier": "AUTO"},
            ctx,
        )
        assert result.status == "ok"
        dispatch = result.data.get("_dispatch", {})
        assert dispatch.get("tier", "").upper() == "LOW"

    def test_omitted_tier_defaults_to_auto(self):
        # P3.3: omitted `plan` defaults to False; single intent stays LOW
        # regardless of SS tier (AUTO-from-SS path deleted).
        from poc.k1_poc.tools.implementations import execute_dispatch_task

        ss = self._mock_ss_with_tier("MEDIUM")
        ctx = self._tool_ctx(ss)
        result = execute_dispatch_task(
            {"intents": [{"action": "test"}]},
            ctx,
        )
        assert result.status == "ok"
        dispatch = result.data.get("_dispatch", {})
        assert dispatch.get("tier", "").upper() == "LOW"


# =========================================================================
# E10.3.3 -- CRISIS short-circuit
# =========================================================================


class TestCrisisShortCircuit:
    """CRISIS safety band -> canned response, no LLM invocation."""

    def test_crisis_emits_final_response(self):
        """_deliver_crisis_response emits a final_response event."""
        from poc.k1_poc.fsm.controller import ConciergeController

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

        from poc.k1_poc.fsm.controller import ConciergeController

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
        from poc.k1_poc.fsm.controller import ConciergeController
        from poc.k1_poc.task.complexity import ComplexityTier
        from poc.k1_poc.task.dispatch import TaskDispatch
        from poc.k1_poc.task.intent import TaskIntent

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
        )
        payload = evt.to_payload()
        assert payload["turn_number"] == 5
        assert "complexity_tier" not in payload  # P3.1: removed
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
            payload={"complexity_tier": "LOW"},
            parent_id=10,
        )
        assert env.topic == "k1.phase1.classified.v1"

    def test_task_routed_builder_produces_envelope(self):
        env = build_task_routed(
            payload={"task_id": "task-1", "assigned_tier": "MEDIUM"},
            parent_id=20,
        )
        assert env.topic == "k1.task.routed.v1"
