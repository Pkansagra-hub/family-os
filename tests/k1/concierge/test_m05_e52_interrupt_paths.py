"""
tests.poc.test_m05_e52_interrupt_paths -- E5.2 FSM Interrupt Path Replacement
=============================================================================

Issue coverage:
  5.2.1 -- Wire Arbiter into _on_user_input (COMPANIONING/PROGRESSING)
  5.2.2 -- Handle CANCEL classification (target task selection, CANCELLING)
  5.2.3 -- Handle MODIFY_INFLIGHT (emit task.modify, stay COMPANIONING)
  5.2.4 -- Handle DEFER classification (acknowledge, stay COMPANIONING)
"""

from __future__ import annotations

import json

from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import (
    TOPIC_FINAL_RESPONSE,
    TOPIC_INTENT_ARBITRATED,
    TOPIC_STATE_UPDATED,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_MODIFY,
    TOPIC_TURN_STARTED,
)
from k1.concierge.fsm.arbiter import ArbiterDecision
from k1.concierge.fsm.states import ConciergeState

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


def _captured_topics(bus) -> list[str]:
    """Return list of topic strings from captured envelopes."""
    return [e.topic for e in bus.captured]


def _captured_by_topic(bus, topic: str) -> list:
    """Return captured envelopes matching a specific topic."""
    return [e for e in bus.captured if e.topic == topic]


def _payload(envelope) -> dict:
    """Parse JSON payload from a captured envelope."""
    try:
        return json.loads(envelope.payload) if envelope.payload else {}
    except Exception:
        return {}


# ===================================================================
# 5.2.1 -- Wire Arbiter into _on_user_input (COMPANIONING/PROGRESSING)
# ===================================================================


class TestArbiterWiring:
    """Arbiter replaces InterruptClassifier for COMPANIONING/PROGRESSING."""

    def test_arbiter_exists_on_controller(self) -> None:
        """Controller has _arbiter attribute."""
        fsm, _ = _make_fsm()
        assert hasattr(fsm, "_arbiter")
        from k1.concierge.fsm.arbiter import ConversationArbiter

        assert isinstance(fsm._arbiter, ConversationArbiter)

    def test_handle_interrupt_method_exists(self) -> None:
        """_handle_interrupt is still present (backward compat)."""
        fsm, _ = _make_fsm()
        assert hasattr(fsm, "_handle_interrupt")
        assert callable(fsm._handle_interrupt)

    def test_companioning_user_input_goes_through_arbiter(self) -> None:
        """COMPANIONING + user input emits intent.arbitrated (Arbiter path)."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "what is the weather"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) >= 1, "intent.arbitrated must be emitted"

    def test_progressing_user_input_goes_through_arbiter(self) -> None:
        """PROGRESSING + user input emits intent.arbitrated (Arbiter path)."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.PROGRESSING
        env = build_user_input({"text": "how about now"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) >= 1, "intent.arbitrated must be emitted"

    def test_intent_arbitrated_emitted_before_state_transition(self) -> None:
        """intent.arbitrated is published BEFORE any FSM state change."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "tell me a joke"})
        fsm._on_user_input(env)
        topics = _captured_topics(bus)
        arb_idx = next(
            (i for i, t in enumerate(topics) if t == TOPIC_INTENT_ARBITRATED),
            None,
        )
        state_idx = next(
            (i for i, t in enumerate(topics) if t == TOPIC_STATE_UPDATED),
            None,
        )
        assert arb_idx is not None, "intent.arbitrated must exist"
        assert state_idx is not None, "state.updated must exist"
        assert arb_idx < state_idx, "intent.arbitrated must precede state.updated"

    def test_intent_arbitrated_payload_has_decision(self) -> None:
        """intent.arbitrated envelope carries decision, confidence, inflight count."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "what time is it"})
        fsm._on_user_input(env)
        arb = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)[0]
        payload = _payload(arb)
        assert "decision" in payload
        assert "confidence" in payload
        assert "inflight_task_count" in payload
        assert "routing_metadata" in payload


# ===================================================================
# 5.2.1 -- PARALLEL_NEW produces identical trace to old "chat" path
# ===================================================================


class TestParallelNewPath:
    """PARALLEL_NEW decision produces the same FSM trace as the old chat path."""

    def test_parallel_new_from_companioning_reaches_dispatching(self) -> None:
        """COMPANIONING + non-cancel text -> PARALLEL_NEW -> DISPATCHING."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "what is the weather today"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.DISPATCHING

    def test_parallel_new_from_progressing_reaches_dispatching(self) -> None:
        """PROGRESSING + non-cancel text -> PARALLEL_NEW -> DISPATCHING."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.PROGRESSING
        env = build_user_input({"text": "also check the news"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.DISPATCHING

    def test_parallel_new_emits_turn_started(self) -> None:
        """PARALLEL_NEW path emits turn.started (same as old chat path)."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "find me a recipe"})
        fsm._on_user_input(env)
        turn_events = _captured_by_topic(bus, TOPIC_TURN_STARTED)
        assert len(turn_events) >= 1

    def test_parallel_new_increments_turn_number(self) -> None:
        """PARALLEL_NEW increments the turn counter."""
        fsm, _ = _make_fsm()
        initial_turn = fsm._turn_number
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "tell me about space"})
        fsm._on_user_input(env)
        assert fsm._turn_number == initial_turn + 1

    def test_parallel_new_writes_history(self) -> None:
        """PARALLEL_NEW writes a user history entry."""
        fsm, _ = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "hello world"})
        fsm._on_user_input(env)
        user_entries = [h for h in fsm._history if h.entry_type == "user"]
        assert len(user_entries) >= 1
        last = user_entries[-1]
        assert last.text == "hello world"
        assert last.metadata.get("arbiter_decision") == "parallel_new"

    def test_parallel_new_phase1_runs_once(self) -> None:
        """Phase 1 runs exactly once (inside Arbiter, not again in _run_phase1)."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        # Track Phase 1 calls
        call_count = 0
        original_classify = fsm._phase1_pipeline.classify

        def counting_classify(text):
            nonlocal call_count
            call_count += 1
            return original_classify(text)

        fsm._phase1_pipeline.classify = counting_classify
        env = build_user_input({"text": "plan my vacation"})
        fsm._on_user_input(env)
        assert call_count == 1, f"Phase 1 should run exactly once, got {call_count}"

    def test_cancel_keyword_no_inflight_routes_parallel_new(self) -> None:
        """Cancel keyword with no inflight tasks -> PARALLEL_NEW (not CANCEL)."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        # No active tasks -> cancel intent with no inflight -> PARALLEL_NEW
        env = build_user_input({"text": "cancel"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.DISPATCHING
        arb = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)[0]
        assert _payload(arb)["decision"] == "parallel_new"


# ===================================================================
# 5.2.2 -- Handle CANCEL classification
# ===================================================================


class TestCancelPath:
    """CANCEL decision transitions to CANCELLING and emits task.cancel."""

    def _make_fsm_with_cancel_arbiter(self, target_task_id="task-1"):
        """Create FSM with mock arbiter that returns CANCEL for a single target."""
        from k1.concierge.fsm.arbiter import ArbiterResult

        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        fsm._active_task_ids.add(target_task_id)

        class CancelArbiter:
            def classify(self, text, phase1, inflight):
                return ArbiterResult(
                    decision=ArbiterDecision.CANCEL,
                    confidence=0.9,
                    target_task_id=target_task_id,
                    modification_params=None,
                    routing_metadata={"arbiter_reason": "cancel_intent"},
                    phase1=phase1,
                )

        fsm._arbiter = CancelArbiter()
        return fsm, bus

    def _make_fsm_cancel_all(self, task_ids=("task-1", "task-2")):
        """Create FSM with mock arbiter returning CANCEL with no target (cancel all)."""
        from k1.concierge.fsm.arbiter import ArbiterResult

        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        for tid in task_ids:
            fsm._active_task_ids.add(tid)

        class CancelAllArbiter:
            def classify(self, text, phase1, inflight):
                return ArbiterResult(
                    decision=ArbiterDecision.CANCEL,
                    confidence=0.85,
                    target_task_id=None,
                    modification_params=None,
                    routing_metadata={"arbiter_reason": "cancel_intent"},
                    phase1=phase1,
                )

        fsm._arbiter = CancelAllArbiter()
        return fsm, bus

    def test_cancel_single_inflight_transitions_to_cancelling(self) -> None:
        """CANCEL with 1 inflight task -> CANCELLING state."""
        fsm, bus = self._make_fsm_with_cancel_arbiter("task-1")
        env = build_user_input({"text": "cancel"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.CANCELLING

    def test_cancel_emits_task_cancel_event(self) -> None:
        """CANCEL decision emits task.cancel bus event."""
        fsm, bus = self._make_fsm_with_cancel_arbiter("task-1")
        env = build_user_input({"text": "stop that"})
        fsm._on_user_input(env)
        cancel_events = _captured_by_topic(bus, TOPIC_TASK_CANCEL)
        assert len(cancel_events) >= 1
        assert _payload(cancel_events[0])["task_id"] == "task-1"

    def test_cancel_no_llm_call(self) -> None:
        """CANCEL is deterministic -- no Front/Back delivery."""
        fsm, bus = self._make_fsm_with_cancel_arbiter("task-1")
        delivered = []
        original_deliver = fsm._deliver_to_front

        def tracking_deliver(env):
            delivered.append(env)
            return original_deliver(env)

        fsm._deliver_to_front = tracking_deliver
        env = build_user_input({"text": "cancel"})
        fsm._on_user_input(env)
        assert len(delivered) == 0, "CANCEL should not deliver to Front"

    def test_cancel_increments_turn(self) -> None:
        """CANCEL increments turn number."""
        fsm, _ = self._make_fsm_with_cancel_arbiter()
        initial = fsm._turn_number
        env = build_user_input({"text": "cancel"})
        fsm._on_user_input(env)
        assert fsm._turn_number == initial + 1

    def test_cancel_writes_history_with_metadata(self) -> None:
        """CANCEL writes user history entry with cancel metadata."""
        fsm, _ = self._make_fsm_with_cancel_arbiter("task-1")
        env = build_user_input({"text": "cancel"})
        fsm._on_user_input(env)
        user_entries = [h for h in fsm._history if h.entry_type == "user"]
        last = user_entries[-1]
        assert last.metadata.get("arbiter_decision") == "cancel"
        assert last.metadata.get("target_task_id") == "task-1"

    def test_cancel_all_with_multiple_tasks(self) -> None:
        """'cancel everything' cancels all active tasks."""
        fsm, bus = self._make_fsm_cancel_all(("task-1", "task-2"))
        env = build_user_input({"text": "cancel everything"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.CANCELLING
        cancel_events = _captured_by_topic(bus, TOPIC_TASK_CANCEL)
        cancelled_ids = {_payload(e)["task_id"] for e in cancel_events}
        assert "task-1" in cancelled_ids
        assert "task-2" in cancelled_ids

    def test_cancel_from_progressing(self) -> None:
        """CANCEL from PROGRESSING also transitions to CANCELLING."""
        from k1.concierge.fsm.arbiter import ArbiterResult

        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.PROGRESSING
        fsm._active_task_ids.add("task-1")

        class CancelArbiter:
            def classify(self, text, phase1, inflight):
                return ArbiterResult(
                    decision=ArbiterDecision.CANCEL,
                    confidence=0.9,
                    target_task_id="task-1",
                    modification_params=None,
                    routing_metadata={"arbiter_reason": "cancel_intent"},
                    phase1=phase1,
                )

        fsm._arbiter = CancelArbiter()
        env = build_user_input({"text": "abort"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.CANCELLING

    def test_cancel_emits_intent_arbitrated_with_cancel_decision(self) -> None:
        """intent.arbitrated payload shows cancel decision."""
        fsm, bus = self._make_fsm_with_cancel_arbiter("task-1")
        env = build_user_input({"text": "stop"})
        fsm._on_user_input(env)
        arb = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)[0]
        assert _payload(arb)["decision"] == "cancel"


# ===================================================================
# 5.2.3 -- Handle MODIFY_INFLIGHT classification
# ===================================================================


class TestModifyInflightPath:
    """MODIFY_INFLIGHT emits task.modify and stays COMPANIONING."""

    def _make_fsm_with_overlapping_task(self):
        """Create FSM with a task whose domain overlaps user input.

        Uses direct Arbiter injection to force MODIFY_INFLIGHT decision
        since the stub Phase1 always returns 'general' domain which won't
        overlap. We set up the condition and call _handle_interrupt directly.
        """
        from k1.concierge.fsm.arbiter import ArbiterResult

        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        fsm._active_task_ids.add("task-hotel")

        # Install a mock arbiter that returns MODIFY_INFLIGHT
        class ModifyArbiter:
            def classify(self, text, phase1, inflight):
                return ArbiterResult(
                    decision=ArbiterDecision.MODIFY_INFLIGHT,
                    confidence=0.85,
                    target_task_id="task-hotel",
                    modification_params={"nights": "2", "raw_text": text},
                    routing_metadata={"arbiter_reason": "domain_entity_overlap"},
                    phase1=phase1,
                )

        fsm._arbiter = ModifyArbiter()
        return fsm, bus

    def test_modify_stays_companioning(self) -> None:
        """MODIFY_INFLIGHT does not change FSM state."""
        fsm, bus = self._make_fsm_with_overlapping_task()
        env = build_user_input({"text": "make that 2 nights"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.COMPANIONING

    def test_modify_emits_task_modify_event(self) -> None:
        """MODIFY_INFLIGHT emits task.modify bus event."""
        fsm, bus = self._make_fsm_with_overlapping_task()
        env = build_user_input({"text": "make that 2 nights"})
        fsm._on_user_input(env)
        modify_events = _captured_by_topic(bus, TOPIC_TASK_MODIFY)
        assert len(modify_events) >= 1
        payload = _payload(modify_events[0])
        assert payload["task_id"] == "task-hotel"
        assert "modifications" in payload

    def test_modify_does_not_increment_turn(self) -> None:
        """MODIFY_INFLIGHT does not increment turn number."""
        fsm, _ = self._make_fsm_with_overlapping_task()
        initial = fsm._turn_number
        env = build_user_input({"text": "change to 2 nights"})
        fsm._on_user_input(env)
        assert fsm._turn_number == initial, "Turn must NOT increment for modify"

    def test_modify_writes_history_entry(self) -> None:
        """MODIFY_INFLIGHT writes a 'modify' history entry."""
        fsm, _ = self._make_fsm_with_overlapping_task()
        env = build_user_input({"text": "2 nights please"})
        fsm._on_user_input(env)
        modify_entries = [h for h in fsm._history if h.entry_type == "modify"]
        assert len(modify_entries) >= 1
        last = modify_entries[-1]
        assert last.metadata.get("arbiter_decision") == "modify_inflight"
        assert last.metadata.get("target_task_id") == "task-hotel"

    def test_modify_emits_intent_arbitrated(self) -> None:
        """MODIFY_INFLIGHT emits intent.arbitrated with modify decision."""
        fsm, bus = self._make_fsm_with_overlapping_task()
        env = build_user_input({"text": "change nights"})
        fsm._on_user_input(env)
        arb = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)[0]
        assert _payload(arb)["decision"] == "modify_inflight"

    def test_modify_does_not_deliver_to_front(self) -> None:
        """MODIFY_INFLIGHT does not invoke Front LLM."""
        fsm, bus = self._make_fsm_with_overlapping_task()
        delivered = []
        original = fsm._deliver_to_front

        def tracking(env):
            delivered.append(env)
            return original(env)

        fsm._deliver_to_front = tracking
        env = build_user_input({"text": "2 nights"})
        fsm._on_user_input(env)
        assert len(delivered) == 0

    def test_modify_no_state_updated_event(self) -> None:
        """MODIFY_INFLIGHT does not emit state.updated (no transition)."""
        fsm, bus = self._make_fsm_with_overlapping_task()
        env = build_user_input({"text": "2 nights"})
        fsm._on_user_input(env)
        state_events = _captured_by_topic(bus, TOPIC_STATE_UPDATED)
        assert len(state_events) == 0, "No state transition for modify"


# ===================================================================
# 5.2.4 -- Handle DEFER classification
# ===================================================================


class TestDeferPath:
    """DEFER decision stays COMPANIONING, no LLM call, no turn increment."""

    def _make_fsm_with_defer_arbiter(self):
        """Create FSM with mock arbiter that returns DEFER."""
        from k1.concierge.fsm.arbiter import ArbiterResult

        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        fsm._active_task_ids.add("task-1")

        class DeferArbiter:
            def classify(self, text, phase1, inflight):
                return ArbiterResult(
                    decision=ArbiterDecision.DEFER,
                    confidence=0.8,
                    target_task_id=None,
                    modification_params=None,
                    routing_metadata={"arbiter_reason": "defer_pattern"},
                    phase1=phase1,
                )

        fsm._arbiter = DeferArbiter()
        return fsm, bus

    def test_defer_stays_companioning(self) -> None:
        """DEFER does not change FSM state."""
        fsm, bus = self._make_fsm_with_defer_arbiter()
        env = build_user_input({"text": "ok keep going"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.COMPANIONING

    def test_defer_does_not_increment_turn(self) -> None:
        """DEFER does not increment turn number."""
        fsm, _ = self._make_fsm_with_defer_arbiter()
        initial = fsm._turn_number
        env = build_user_input({"text": "sure"})
        fsm._on_user_input(env)
        assert fsm._turn_number == initial, "Turn must NOT increment for defer"

    def test_defer_writes_history_entry(self) -> None:
        """DEFER writes a 'defer' history entry."""
        fsm, _ = self._make_fsm_with_defer_arbiter()
        env = build_user_input({"text": "ok"})
        fsm._on_user_input(env)
        defer_entries = [h for h in fsm._history if h.entry_type == "defer"]
        assert len(defer_entries) >= 1
        last = defer_entries[-1]
        assert last.metadata.get("arbiter_decision") == "defer"

    def test_defer_does_not_invoke_llm(self) -> None:
        """DEFER does not deliver to Front or Back."""
        fsm, bus = self._make_fsm_with_defer_arbiter()
        delivered = []
        original = fsm._deliver_to_front

        def tracking(env):
            delivered.append(env)
            return original(env)

        fsm._deliver_to_front = tracking
        env = build_user_input({"text": "keep going"})
        fsm._on_user_input(env)
        assert len(delivered) == 0

    def test_defer_emits_intent_arbitrated(self) -> None:
        """DEFER emits intent.arbitrated with defer decision."""
        fsm, bus = self._make_fsm_with_defer_arbiter()
        env = build_user_input({"text": "ok sure"})
        fsm._on_user_input(env)
        arb = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)[0]
        assert _payload(arb)["decision"] == "defer"

    def test_defer_no_ack_by_default(self) -> None:
        """Default _should_ack_defer returns False, no response.final emitted."""
        fsm, bus = self._make_fsm_with_defer_arbiter()
        env = build_user_input({"text": "sure thing"})
        fsm._on_user_input(env)
        final_events = _captured_by_topic(bus, TOPIC_FINAL_RESPONSE)
        assert len(final_events) == 0, "No ack by default"

    def test_defer_ack_when_configured(self) -> None:
        """When _should_ack_defer returns True, emit lightweight response.final."""
        fsm, bus = self._make_fsm_with_defer_arbiter()
        fsm._should_ack_defer = lambda: True
        env = build_user_input({"text": "ok"})
        fsm._on_user_input(env)
        final_events = _captured_by_topic(bus, TOPIC_FINAL_RESPONSE)
        assert len(final_events) >= 1
        payload = _payload(final_events[0])
        assert payload.get("is_ack") is True

    def test_defer_no_state_transition(self) -> None:
        """DEFER does not emit state.updated."""
        fsm, bus = self._make_fsm_with_defer_arbiter()
        env = build_user_input({"text": "ok"})
        fsm._on_user_input(env)
        state_events = _captured_by_topic(bus, TOPIC_STATE_UPDATED)
        assert len(state_events) == 0

    def test_subsequent_input_processed_normally_after_defer(self) -> None:
        """After defer, a real question is processed normally (PARALLEL_NEW)."""
        fsm, bus = self._make_fsm_with_defer_arbiter()
        env1 = build_user_input({"text": "ok"})
        fsm._on_user_input(env1)
        assert fsm._state == ConciergeState.COMPANIONING

        # Reset arbiter to default for next input
        from k1.concierge.fsm.arbiter import ConversationArbiter

        fsm._arbiter = ConversationArbiter()
        fsm._active_task_ids.clear()  # No inflight -> PARALLEL_NEW

        bus.captured.clear()
        env2 = build_user_input({"text": "what is the weather"})
        fsm._on_user_input(env2)
        assert fsm._state == ConciergeState.DISPATCHING


# ===================================================================
# Cross-cutting: builder and topic integration
# ===================================================================


class TestE52TopicAndBuilderIntegration:
    """Verify TOPIC_TASK_MODIFY and build_task_modify are properly wired."""

    def test_topic_task_modify_exists(self) -> None:
        """TOPIC_TASK_MODIFY is defined in topics module."""
        assert TOPIC_TASK_MODIFY == "k1.orchestration.task.modify.v1"

    def test_topic_task_modify_in_all_topics(self) -> None:
        """TOPIC_TASK_MODIFY is in ALL_TOPICS."""
        from k1.concierge.bus.topics import ALL_TOPICS

        assert TOPIC_TASK_MODIFY in ALL_TOPICS

    def test_build_task_modify_exists(self) -> None:
        """build_task_modify is importable and callable."""
        from k1.concierge.bus.builders import build_task_modify

        assert callable(build_task_modify)

    def test_build_task_modify_creates_envelope(self) -> None:
        """build_task_modify creates a valid Envelope."""
        from k1.concierge.bus.builders import build_task_modify

        env = build_task_modify(
            payload={"task_id": "t1", "modifications": {"x": 1}},
        )
        assert env.topic == TOPIC_TASK_MODIFY
        assert _payload(env)["task_id"] == "t1"

    def test_build_task_modify_in_builders_dict(self) -> None:
        """BUILDERS dict includes TOPIC_TASK_MODIFY."""
        from k1.concierge.bus.builders import BUILDERS

        assert TOPIC_TASK_MODIFY in BUILDERS

    def test_build_task_modify_in_registry(self) -> None:
        """get_builder_registry includes TOPIC_TASK_MODIFY."""
        from k1.concierge.bus.builders import get_builder_registry

        registry = get_builder_registry()
        assert TOPIC_TASK_MODIFY in registry

    def test_all_topics_count(self) -> None:
        """ALL_TOPICS has 31 topics (29 orig + intent_arbitrated + task_modify)."""
        from k1.concierge.bus.topics import ALL_TOPICS

        assert len(ALL_TOPICS) == 47

    def test_builders_count(self) -> None:
        """BUILDERS dict has 31 entries."""
        from k1.concierge.bus.builders import BUILDERS

        assert len(BUILDERS) == 47
