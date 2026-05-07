"""
tests.poc.test_m05_e54_multi_device -- E5.4 Multi-Device Arbitration
====================================================================

Issue coverage:
  5.4.1 -- Device tracking in MetaSection + device_id pass-through
  5.4.2 -- Deterministic precedence rules for multi-device conflicts
  5.4.3 -- High-impact conflict detection and confirmation
  5.4.4 -- HITL wiring validation + duplicate HITL response guard
"""

from __future__ import annotations

import json

from k1.bus.envelope import Envelope
from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import TOPIC_INTENT_ARBITRATED
from k1.concierge.config import ArbiterConfig
from k1.concierge.fsm.arbiter import (
    ArbiterDecision,
    ArbiterResult,
    ConversationArbiter,
    InflightContext,
    build_inflight_context,
)
from k1.concierge.fsm.phase1 import Phase1Result
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.protocols.hitl_wiring import validate_hitl_wiring
from k1.sessionstate.sections.meta import MetaSection

# ===================================================================
# Helper: create FSM with capture bus
# ===================================================================


def _make_fsm():
    """Create a ConciergeController with capture bus and router."""
    from k1.concierge.bus.setup import create_poc_bus, create_poc_router
    from k1.concierge.fsm.controller import ConciergeController

    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    return ConciergeController(bus=bus, router=router), bus


def _captured_by_topic(bus, topic: str) -> list:
    """Return captured envelopes matching a specific topic."""
    return [e for e in bus.captured if e.topic == topic]


def _payload(envelope) -> dict:
    """Parse JSON payload from a captured envelope."""
    try:
        return json.loads(envelope.payload) if envelope.payload else {}
    except Exception:
        return {}


def _make_phase1(
    *,
    intent: str = "general",
    domain: str = "general",
    safety_band: str = "GREEN",
    entities: list[dict] | None = None,
) -> Phase1Result:
    """Build a Phase1Result for testing."""
    return Phase1Result(
        intent_classification=intent,
        domain_context=domain,
        safety_band=safety_band,
        primary_emotion="neutral",
        emotion_confidence=0.5,
        entities=entities or [],
    )


def _make_arbiter_result(
    *,
    decision: ArbiterDecision = ArbiterDecision.PARALLEL_NEW,
    confidence: float = 0.9,
    target_task_id: str | None = None,
    phase1: Phase1Result | None = None,
) -> ArbiterResult:
    """Build an ArbiterResult for testing."""
    p1 = phase1 or _make_phase1()
    return ArbiterResult(
        decision=decision,
        confidence=confidence,
        target_task_id=target_task_id,
        modification_params=None,
        routing_metadata={},
        phase1=p1,
    )


# ===================================================================
# 5.4.1 -- Device tracking in MetaSection
# ===================================================================


class TestMetaDeviceTracking:
    """MetaSection multi-device tracking API (set_active_device, get_active_devices)."""

    def test_set_active_device_records_device(self) -> None:
        """set_active_device creates a device entry."""
        meta = MetaSection()
        meta.set_active_device("phone-1")
        devices = meta.get_active_devices()
        assert len(devices) == 1
        assert devices[0]["device_id"] == "phone-1"
        assert devices[0]["input_count"] == 1

    def test_set_active_device_increments_count(self) -> None:
        """Repeated calls for same device increment input_count."""
        meta = MetaSection()
        meta.set_active_device("phone-1")
        meta.set_active_device("phone-1")
        meta.set_active_device("phone-1")
        devices = meta.get_active_devices()
        assert len(devices) == 1
        assert devices[0]["input_count"] == 3

    def test_multiple_devices_tracked_independently(self) -> None:
        """Different device_ids create separate entries."""
        meta = MetaSection()
        meta.set_active_device("phone-1")
        meta.set_active_device("tablet-2")
        meta.set_active_device("phone-1")
        devices = meta.get_active_devices()
        assert len(devices) == 2
        ids = {d["device_id"] for d in devices}
        assert ids == {"phone-1", "tablet-2"}

    def test_active_device_count_property(self) -> None:
        """active_device_count returns distinct device count."""
        meta = MetaSection()
        assert meta.active_device_count == 0
        meta.set_active_device("phone-1")
        assert meta.active_device_count == 1
        meta.set_active_device("tablet-2")
        assert meta.active_device_count == 2
        meta.set_active_device("phone-1")
        assert meta.active_device_count == 2  # Still 2

    def test_get_active_devices_sorted_by_recency(self) -> None:
        """Devices sorted by last_active_ms descending (most recent first)."""
        meta = MetaSection()
        meta.set_active_device("old-device", timestamp_ms=1000)
        meta.set_active_device("new-device", timestamp_ms=5000)
        meta.set_active_device("mid-device", timestamp_ms=3000)
        devices = meta.get_active_devices()
        assert devices[0]["device_id"] == "new-device"
        assert devices[1]["device_id"] == "mid-device"
        assert devices[2]["device_id"] == "old-device"

    def test_set_active_device_updates_identity(self) -> None:
        """set_active_device also updates primary identity.device_id."""
        meta = MetaSection()
        meta.set_active_device("phone-1")
        assert meta.device_id == "phone-1"
        meta.set_active_device("tablet-2")
        assert meta.device_id == "tablet-2"

    def test_set_active_device_empty_string_noop(self) -> None:
        """Empty device_id is silently ignored."""
        meta = MetaSection()
        meta.set_active_device("")
        assert meta.active_device_count == 0
        assert meta.get_active_devices() == []

    def test_get_active_devices_empty_on_fresh_meta(self) -> None:
        """Fresh MetaSection returns empty device list."""
        meta = MetaSection()
        assert meta.get_active_devices() == []
        assert meta.active_device_count == 0


class TestDeviceIdPassthrough:
    """device_id extracted from user input and passed to Arbiter context."""

    def test_inflight_context_stores_device_id(self) -> None:
        """InflightContext accepts active_device_id kwarg."""
        ctx = InflightContext(
            tasks=[],
            pending_results=0,
            cancelled_task_ids=set(),
            fsm_state="LISTENING",
            current_turn=1,
            active_device_id="phone-1",
        )
        assert ctx.active_device_id == "phone-1"

    def test_inflight_context_device_id_defaults_none(self) -> None:
        """InflightContext.active_device_id defaults to None."""
        ctx = InflightContext(
            tasks=[],
            pending_results=0,
            cancelled_task_ids=set(),
            fsm_state="LISTENING",
            current_turn=1,
        )
        assert ctx.active_device_id is None

    def test_build_inflight_context_passes_device_id(self) -> None:
        """build_inflight_context forwards device_id kwarg."""
        ctx = build_inflight_context(
            ss=None,
            suspension_manager=None,
            cancel_handler=None,
            turn_state=None,
            current_turn=1,
            device_id="tablet-2",
        )
        assert ctx.active_device_id == "tablet-2"

    def test_build_inflight_context_device_id_none_default(self) -> None:
        """build_inflight_context without device_id sets None."""
        ctx = build_inflight_context(
            ss=None,
            suspension_manager=None,
            cancel_handler=None,
            turn_state=None,
            current_turn=1,
        )
        assert ctx.active_device_id is None

    def test_user_input_device_id_reaches_intent_arbitrated(self) -> None:
        """device_id in user input payload flows through to intent.arbitrated event."""
        fsm, bus = _make_fsm()
        assert fsm._state == ConciergeState.LISTENING
        env = build_user_input({"text": "hello world", "device_id": "phone-1"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) >= 1, "intent.arbitrated should be emitted"

    def test_user_input_without_device_id_still_works(self) -> None:
        """User input without device_id processes normally (backward compat)."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "hello"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) >= 1


# ===================================================================
# 5.4.2 -- Deterministic precedence rules
# ===================================================================


class TestDeviceConflictPrecedence:
    """ConversationArbiter.resolve_device_conflict() precedence ordering."""

    def test_resolve_device_conflict_method_exists(self) -> None:
        """ConversationArbiter has resolve_device_conflict method."""
        arbiter = ConversationArbiter()
        assert hasattr(arbiter, "resolve_device_conflict")
        assert callable(arbiter.resolve_device_conflict)

    def test_cancel_beats_parallel_new(self) -> None:
        """CANCEL (priority 1) takes precedence over PARALLEL_NEW (priority 5)."""
        arbiter = ConversationArbiter()
        cancel = _make_arbiter_result(decision=ArbiterDecision.CANCEL)
        parallel = _make_arbiter_result(decision=ArbiterDecision.PARALLEL_NEW)

        ordered = arbiter.resolve_device_conflict(
            current_input=parallel,
            queued_inputs=[("device-B", cancel)],
        )
        assert len(ordered) == 2
        assert ordered[0].decision == ArbiterDecision.CANCEL
        assert ordered[1].decision == ArbiterDecision.PARALLEL_NEW

    def test_cancel_beats_modify(self) -> None:
        """CANCEL (priority 1) takes precedence over MODIFY_INFLIGHT (priority 4)."""
        arbiter = ConversationArbiter()
        cancel = _make_arbiter_result(decision=ArbiterDecision.CANCEL)
        modify = _make_arbiter_result(decision=ArbiterDecision.MODIFY_INFLIGHT)

        ordered = arbiter.resolve_device_conflict(
            current_input=modify,
            queued_inputs=[("device-B", cancel)],
        )
        assert ordered[0].decision == ArbiterDecision.CANCEL
        assert ordered[1].decision == ArbiterDecision.MODIFY_INFLIGHT

    def test_modify_beats_defer(self) -> None:
        """MODIFY_INFLIGHT (priority 4) takes precedence over DEFER (priority 6)."""
        arbiter = ConversationArbiter()
        modify = _make_arbiter_result(decision=ArbiterDecision.MODIFY_INFLIGHT)
        defer = _make_arbiter_result(decision=ArbiterDecision.DEFER)

        ordered = arbiter.resolve_device_conflict(
            current_input=defer,
            queued_inputs=[("device-B", modify)],
        )
        assert ordered[0].decision == ArbiterDecision.MODIFY_INFLIGHT
        assert ordered[1].decision == ArbiterDecision.DEFER

    def test_defer_is_lowest_priority(self) -> None:
        """DEFER (priority 6) is below all other decisions."""
        arbiter = ConversationArbiter()
        cancel = _make_arbiter_result(decision=ArbiterDecision.CANCEL)
        modify = _make_arbiter_result(decision=ArbiterDecision.MODIFY_INFLIGHT)
        parallel = _make_arbiter_result(decision=ArbiterDecision.PARALLEL_NEW)
        defer = _make_arbiter_result(decision=ArbiterDecision.DEFER)

        ordered = arbiter.resolve_device_conflict(
            current_input=defer,
            queued_inputs=[
                ("dev-A", parallel),
                ("dev-B", cancel),
                ("dev-C", modify),
            ],
        )
        assert ordered[0].decision == ArbiterDecision.CANCEL
        assert ordered[-1].decision == ArbiterDecision.DEFER

    def test_red_safety_band_overrides_to_priority_2(self) -> None:
        """RED safety band overrides decision priority to 2 (after CANCEL)."""
        arbiter = ConversationArbiter()
        red_parallel = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(safety_band="RED"),
        )
        normal_cancel = _make_arbiter_result(decision=ArbiterDecision.CANCEL)

        ordered = arbiter.resolve_device_conflict(
            current_input=red_parallel,
            queued_inputs=[("device-B", normal_cancel)],
        )
        # CANCEL (1) still beats RED PARALLEL_NEW (2)
        assert ordered[0].decision == ArbiterDecision.CANCEL
        assert ordered[1].decision == ArbiterDecision.PARALLEL_NEW

    def test_red_safety_band_beats_normal_modify(self) -> None:
        """RED safety band (priority 2) beats normal MODIFY_INFLIGHT (priority 4)."""
        arbiter = ConversationArbiter()
        red_defer = _make_arbiter_result(
            decision=ArbiterDecision.DEFER,
            phase1=_make_phase1(safety_band="RED"),
        )
        normal_modify = _make_arbiter_result(decision=ArbiterDecision.MODIFY_INFLIGHT)

        ordered = arbiter.resolve_device_conflict(
            current_input=normal_modify,
            queued_inputs=[("device-B", red_defer)],
        )
        # RED DEFER (priority 2) beats normal MODIFY (priority 4)
        assert ordered[0].decision == ArbiterDecision.DEFER
        assert ordered[1].decision == ArbiterDecision.MODIFY_INFLIGHT

    def test_same_priority_resolved_by_recency(self) -> None:
        """Same-priority inputs resolve by index (lower index = more recent = first)."""
        arbiter = ConversationArbiter()
        parallel_a = _make_arbiter_result(decision=ArbiterDecision.PARALLEL_NEW)
        parallel_b = _make_arbiter_result(decision=ArbiterDecision.PARALLEL_NEW)

        ordered = arbiter.resolve_device_conflict(
            current_input=parallel_a,  # index 0 = most recent
            queued_inputs=[("device-B", parallel_b)],  # index 1 = older
        )
        assert len(ordered) == 2
        # Both PARALLEL_NEW, current_input (index 0) should come first
        assert ordered[0] is parallel_a
        assert ordered[1] is parallel_b

    def test_single_input_returned_unchanged(self) -> None:
        """Single input with no queued inputs returns list of one."""
        arbiter = ConversationArbiter()
        result = _make_arbiter_result(decision=ArbiterDecision.PARALLEL_NEW)

        ordered = arbiter.resolve_device_conflict(
            current_input=result,
            queued_inputs=[],
        )
        assert len(ordered) == 1
        assert ordered[0] is result

    def test_full_priority_ordering(self) -> None:
        """Full ordering: CANCEL > RED > MODIFY > PARALLEL_NEW > DEFER."""
        arbiter = ConversationArbiter()
        cancel = _make_arbiter_result(decision=ArbiterDecision.CANCEL)
        red_new = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(safety_band="RED"),
        )
        modify = _make_arbiter_result(decision=ArbiterDecision.MODIFY_INFLIGHT)
        parallel = _make_arbiter_result(decision=ArbiterDecision.PARALLEL_NEW)
        defer = _make_arbiter_result(decision=ArbiterDecision.DEFER)

        ordered = arbiter.resolve_device_conflict(
            current_input=defer,
            queued_inputs=[
                ("dev-A", parallel),
                ("dev-B", red_new),
                ("dev-C", cancel),
                ("dev-D", modify),
            ],
        )
        decisions = [r.decision for r in ordered]
        assert decisions[0] == ArbiterDecision.CANCEL  # priority 1
        assert decisions[1] == ArbiterDecision.PARALLEL_NEW  # RED = priority 2
        assert decisions[2] == ArbiterDecision.MODIFY_INFLIGHT  # priority 4
        assert decisions[3] == ArbiterDecision.PARALLEL_NEW  # priority 5
        assert decisions[4] == ArbiterDecision.DEFER  # priority 6


# ===================================================================
# 5.4.3 -- High-impact conflict detection and confirmation
# ===================================================================


class TestHighImpactConflictDetection:
    """ConversationArbiter.detect_high_impact_conflict() behavior."""

    def test_detect_method_exists(self) -> None:
        """ConversationArbiter has detect_high_impact_conflict method."""
        arbiter = ConversationArbiter()
        assert hasattr(arbiter, "detect_high_impact_conflict")
        assert callable(arbiter.detect_high_impact_conflict)

    def test_different_devices_contradictory_is_conflict(self) -> None:
        """Different devices, one cancel + one proceed = conflict."""
        arbiter = ConversationArbiter()
        cancel_result = _make_arbiter_result(
            decision=ArbiterDecision.CANCEL,
            phase1=_make_phase1(intent="booking"),
        )
        proceed_result = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="booking"),
        )
        assert (
            arbiter.detect_high_impact_conflict(cancel_result, "phone", proceed_result, "tablet")
            is True
        )

    def test_same_device_no_conflict(self) -> None:
        """Same device never triggers high-impact conflict."""
        arbiter = ConversationArbiter()
        cancel_result = _make_arbiter_result(
            decision=ArbiterDecision.CANCEL,
            phase1=_make_phase1(intent="booking"),
        )
        proceed_result = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="booking"),
        )
        assert (
            arbiter.detect_high_impact_conflict(cancel_result, "phone", proceed_result, "phone")
            is False
        )

    def test_confirmation_disabled_no_conflict(self) -> None:
        """Disabled high_impact_confirmation_required = no conflict."""
        cfg = ArbiterConfig(high_impact_confirmation_required=False)
        arbiter = ConversationArbiter(config=cfg)
        cancel_result = _make_arbiter_result(
            decision=ArbiterDecision.CANCEL,
            phase1=_make_phase1(intent="booking"),
        )
        proceed_result = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="booking"),
        )
        assert (
            arbiter.detect_high_impact_conflict(cancel_result, "phone", proceed_result, "tablet")
            is False
        )

    def test_non_high_impact_no_conflict(self) -> None:
        """Non-high-impact actions (general intent, GREEN band) = no conflict."""
        arbiter = ConversationArbiter()
        result_a = _make_arbiter_result(
            decision=ArbiterDecision.CANCEL,
            phase1=_make_phase1(intent="general"),
        )
        result_b = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="general"),
        )
        assert arbiter.detect_high_impact_conflict(result_a, "phone", result_b, "tablet") is False

    def test_red_safety_band_is_high_impact(self) -> None:
        """RED safety band is always considered high-impact."""
        arbiter = ConversationArbiter()
        red_result = _make_arbiter_result(
            decision=ArbiterDecision.CANCEL,
            phase1=_make_phase1(intent="general", safety_band="RED"),
        )
        proceed_result = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="general"),
        )
        # One is RED (high-impact), one cancels while other proceeds
        assert (
            arbiter.detect_high_impact_conflict(red_result, "phone", proceed_result, "tablet")
            is True
        )

    def test_both_high_impact_different_intents_is_conflict(self) -> None:
        """Both high-impact with different intents = conflict."""
        arbiter = ConversationArbiter()
        booking = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="booking"),
        )
        payment = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="payment"),
        )
        assert arbiter.detect_high_impact_conflict(booking, "phone", payment, "tablet") is True

    def test_both_high_impact_same_intent_no_conflict(self) -> None:
        """Both high-impact with same intent = no conflict (not contradictory)."""
        arbiter = ConversationArbiter()
        booking_a = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="booking"),
        )
        booking_b = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="booking"),
        )
        assert arbiter.detect_high_impact_conflict(booking_a, "phone", booking_b, "tablet") is False


class TestBuildConflictClarification:
    """ConversationArbiter.build_conflict_clarification() output structure."""

    def test_build_method_exists(self) -> None:
        """ConversationArbiter has build_conflict_clarification method."""
        arbiter = ConversationArbiter()
        assert hasattr(arbiter, "build_conflict_clarification")

    def test_clarification_has_required_fields(self) -> None:
        """Clarification dict includes question, options, is_blocking, priority, source."""
        arbiter = ConversationArbiter()
        result_a = _make_arbiter_result(
            decision=ArbiterDecision.CANCEL,
            phase1=_make_phase1(intent="booking"),
        )
        result_b = _make_arbiter_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            phase1=_make_phase1(intent="payment"),
        )
        clar = arbiter.build_conflict_clarification(result_a, "phone", result_b, "tablet")
        assert "question" in clar
        assert "options" in clar
        assert clar["is_blocking"] is True
        assert clar["priority"] == "URGENT"
        assert clar["source"] == "arbiter_device_conflict"
        assert clar["device_a"] == "phone"
        assert clar["device_b"] == "tablet"

    def test_clarification_has_three_options(self) -> None:
        """Options include device_a, device_b, and cancel_both."""
        arbiter = ConversationArbiter()
        result_a = _make_arbiter_result(phase1=_make_phase1(intent="booking"))
        result_b = _make_arbiter_result(phase1=_make_phase1(intent="payment"))
        clar = arbiter.build_conflict_clarification(result_a, "phone", result_b, "tablet")
        values = [o["value"] for o in clar["options"]]
        assert "device_a" in values
        assert "device_b" in values
        assert "cancel_both" in values

    def test_clarification_question_mentions_actions(self) -> None:
        """Question text includes the intent actions from both devices."""
        arbiter = ConversationArbiter()
        result_a = _make_arbiter_result(phase1=_make_phase1(intent="booking"))
        result_b = _make_arbiter_result(phase1=_make_phase1(intent="payment"))
        clar = arbiter.build_conflict_clarification(result_a, "phone-1", result_b, "tablet-2")
        assert "booking" in clar["question"]
        assert "payment" in clar["question"]
        assert "phone-1" in clar["question"]
        assert "tablet-2" in clar["question"]


# ===================================================================
# 5.4.4 -- HITL wiring validation + duplicate HITL response guard
# ===================================================================


class TestHitlWiringMultiDeviceChecks:
    """validate_hitl_wiring() includes multi-device checks (15-17)."""

    def test_validate_hitl_wiring_passes(self) -> None:
        """validate_hitl_wiring returns no issues for multi-device checks."""
        issues = validate_hitl_wiring()
        # Filter to only multi-device related issues
        md_issues = [
            i
            for i in issues
            if "multi-device" in i.lower()
            or "resolve_device_conflict" in i
            or "detect_high_impact_conflict" in i
            or "set_active_device" in i
            or "get_active_devices" in i
            or "active_device_id" in i
        ]
        assert md_issues == [], f"Multi-device checks failed: {md_issues}"

    def test_arbiter_has_conflict_resolution_methods(self) -> None:
        """Check 15: Arbiter has resolve_device_conflict and detect_high_impact_conflict."""
        arbiter = ConversationArbiter()
        assert hasattr(arbiter, "resolve_device_conflict")
        assert hasattr(arbiter, "detect_high_impact_conflict")

    def test_meta_has_device_tracking_methods(self) -> None:
        """Check 16: MetaSection has set_active_device and get_active_devices."""
        meta = MetaSection()
        assert hasattr(meta, "set_active_device")
        assert hasattr(meta, "get_active_devices")

    def test_inflight_context_has_active_device_id(self) -> None:
        """Check 17: InflightContext accepts and stores active_device_id."""
        ctx = InflightContext(
            tasks=[],
            pending_results=0,
            cancelled_task_ids=set(),
            fsm_state="LISTENING",
            current_turn=0,
            active_device_id="test_device",
        )
        assert ctx.active_device_id == "test_device"


class TestHitlDuplicateResponseGuard:
    """Controller duplicate HITL response detection (5.4.4)."""

    def test_hitl_responded_tasks_initialized(self) -> None:
        """Controller has _hitl_responded_tasks dict on init."""
        fsm, _ = _make_fsm()
        assert hasattr(fsm, "_hitl_responded_tasks")
        assert isinstance(fsm._hitl_responded_tasks, dict)
        assert len(fsm._hitl_responded_tasks) == 0

    def test_first_hitl_response_accepted(self) -> None:
        """First HITL response for a task_id is accepted (recorded in tracker)."""
        fsm, bus = _make_fsm()
        # Put FSM into CLARIFYING_WORKER state so task.resume is accepted
        fsm._state = ConciergeState.CLARIFYING_WORKER

        # Manually simulate: dispatch and suspend a task
        task_id = "task-001"
        fsm._task_bridge.dispatch_task(task_id, "test action")
        fsm._task_bridge.suspend_task(task_id)
        fsm._suspension_manager.store_context(
            task_id,
            {
                "hil_type": "clarification",
                "react_history": [],
                "original_task": {},
                "iteration": 0,
                "total_budget": 10,
            },
        )

        env = Envelope(
            topic="k1.orchestration.task.resume.v1",
            payload=json.dumps(
                {
                    "task_id": task_id,
                    "device_id": "phone-1",
                    "resolution": {"answer": "yes"},
                }
            ).encode(),
        )
        fsm._on_task_resume(env)

        # Task was recorded in the dedup tracker
        assert task_id in fsm._hitl_responded_tasks
        assert fsm._hitl_responded_tasks[task_id] == "phone-1"

    def test_duplicate_hitl_response_discarded(self) -> None:
        """Second HITL response for same task_id is discarded."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.CLARIFYING_WORKER

        task_id = "task-002"
        fsm._task_bridge.dispatch_task(task_id, "test action")
        fsm._task_bridge.suspend_task(task_id)
        fsm._suspension_manager.store_context(
            task_id,
            {
                "hil_type": "clarification",
                "react_history": [],
                "original_task": {},
                "iteration": 0,
                "total_budget": 10,
            },
        )

        env1 = Envelope(
            topic="k1.orchestration.task.resume.v1",
            payload=json.dumps(
                {
                    "task_id": task_id,
                    "device_id": "phone-1",
                    "resolution": {"answer": "yes"},
                }
            ).encode(),
        )
        fsm._on_task_resume(env1)

        # Second response from different device for same task
        env2 = Envelope(
            topic="k1.orchestration.task.resume.v1",
            payload=json.dumps(
                {
                    "task_id": task_id,
                    "device_id": "tablet-2",
                    "resolution": {"answer": "no"},
                }
            ).encode(),
            envelope_id=env1.envelope_id + 1,
        )
        fsm._on_task_resume(env2)

        # The tracker still shows the first device
        assert fsm._hitl_responded_tasks[task_id] == "phone-1"

    def test_different_task_ids_both_accepted(self) -> None:
        """Different task_ids are tracked independently."""
        fsm, _ = _make_fsm()
        fsm._state = ConciergeState.CLARIFYING_WORKER

        for tid in ["task-A", "task-B"]:
            fsm._task_bridge.dispatch_task(tid, "test action")
            fsm._task_bridge.suspend_task(tid)
            fsm._suspension_manager.store_context(
                tid,
                {
                    "hil_type": "clarification",
                    "react_history": [],
                    "original_task": {},
                    "iteration": 0,
                    "total_budget": 10,
                },
            )

        env_a = Envelope(
            topic="k1.orchestration.task.resume.v1",
            payload=json.dumps(
                {
                    "task_id": "task-A",
                    "device_id": "phone-1",
                }
            ).encode(),
        )
        fsm._on_task_resume(env_a)

        # FSM transitions away from CLARIFYING_WORKER after first resume;
        # reset state so the second resume is accepted by the guard gate
        fsm._state = ConciergeState.CLARIFYING_WORKER

        env_b = Envelope(
            topic="k1.orchestration.task.resume.v1",
            payload=json.dumps(
                {
                    "task_id": "task-B",
                    "device_id": "tablet-2",
                }
            ).encode(),
            envelope_id=env_a.envelope_id + 1,
        )
        fsm._on_task_resume(env_b)

        assert "task-A" in fsm._hitl_responded_tasks
        assert "task-B" in fsm._hitl_responded_tasks
        assert fsm._hitl_responded_tasks["task-A"] == "phone-1"
        assert fsm._hitl_responded_tasks["task-B"] == "tablet-2"


# ===================================================================
# Integration: device_id flow through interrupt + normal paths
# ===================================================================


class TestDeviceIdFSMIntegration:
    """End-to-end device_id flow from user input through FSM paths."""

    def test_listening_path_with_device_id(self) -> None:
        """LISTENING state: device_id in payload triggers device tracking and arbiter."""
        fsm, bus = _make_fsm()
        assert fsm._state == ConciergeState.LISTENING
        env = build_user_input({"text": "book a flight", "device_id": "phone-1"})
        fsm._on_user_input(env)

        # intent.arbitrated emitted
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) >= 1

    def test_interrupt_path_with_device_id(self) -> None:
        """COMPANIONING state: device_id passes through _handle_interrupt."""
        fsm, bus = _make_fsm()

        # Drive to COMPANIONING
        env1 = build_user_input({"text": "tell me a joke"})
        fsm._on_user_input(env1)
        fsm._state = ConciergeState.COMPANIONING

        bus.captured.clear()
        env2 = build_user_input({"text": "stop that", "device_id": "tablet-2"})
        fsm._on_user_input(env2)

        # intent.arbitrated emitted from interrupt path
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) >= 1

    def test_handle_interrupt_accepts_device_id_kwarg(self) -> None:
        """_handle_interrupt signature accepts device_id keyword argument."""
        fsm, _ = _make_fsm()
        import inspect

        sig = inspect.signature(fsm._handle_interrupt)
        params = list(sig.parameters.keys())
        assert "device_id" in params

    def test_run_phase1_with_arbiter_accepts_device_id_kwarg(self) -> None:
        """_run_phase1_with_arbiter signature accepts device_id keyword argument."""
        fsm, _ = _make_fsm()
        import inspect

        sig = inspect.signature(fsm._run_phase1_with_arbiter)
        params = list(sig.parameters.keys())
        assert "device_id" in params
