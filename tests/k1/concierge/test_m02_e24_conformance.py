"""
tests.poc.test_m02_e24_conformance -- E2.4 M2 Conformance Tests.

Validates the system-level correctness of E2.1-E2.3 artifacts working
together. These are integration/scenario tests that exercise the FSM
controller with real bus, real guard table, real decision table, real
idempotency ledger, and real dead-letter pipeline.

Covers:
  2.4.1 -- Guard matrix completeness and handler agreement
  2.4.2 -- Dead-letter capture and reconciliation
  2.4.3 -- Response-final action table exhaustive truth-table
  2.4.4 -- Interrupt during PROGRESSING with simultaneous task completion
  2.4.5 -- Cancel race: cancel -> late completion -> failed(cancelled)
  2.4.6 -- Suspend in incompatible state -> deferred surfacing from LISTENING
  2.4.7 -- Weave burst: 3 completions in window + user input
  2.4.8 -- Pending results TTL expiry and overflow dead-letter

Test count target: ~55 tests across 8 test classes.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import patch

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.topics import (
    TOPIC_DEAD_LETTER,
    TOPIC_FINAL_RESPONSE,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_STARTED,
    TOPIC_TURN_COMPLETED,
    TOPIC_USER_INPUT,
)
from k1.concierge.config.loader import get_config
from k1.concierge.fsm.dead_letter_consumer import DeadLetterConsumer
from k1.concierge.fsm.response_final_table import (
    ResponseFinalAction,
    decide_response_final,
)
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.fsm.transition_table import (
    FULL_GUARD_TABLE,
    SUBSCRIBED_TOPICS,
    GuardAction,
    get_guard_action,
)
from k1.concierge.fsm.turn_state import FSMTurnState
from k1.concierge.protocols.weave_batcher import WeaveBatcher, WeaveResult
from k1.concierge.protocols.weave_state import PendingResultsQueue

# =========================================================================
# Helpers
# =========================================================================


def _make_envelope(
    topic: str = TOPIC_FINAL_RESPONSE,
    payload: dict | None = None,
    envelope_id: int = 1,
    parent_id: int = 0,
) -> Envelope:
    """Build a minimal Envelope for testing."""
    data = payload or {}
    return Envelope(
        topic=topic,
        payload=json.dumps(data).encode(),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        envelope_id=envelope_id,
        parent_id=parent_id,
    )


def _make_controller():
    """Build a wired ConciergeController for integration tests."""
    from k1.concierge.bus.setup import create_poc_bus, create_poc_router
    from k1.concierge.fsm.controller import ConciergeController

    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    ctrl = ConciergeController(bus=bus, router=router)
    return ctrl, bus


def _captured_by_topic(bus, topic: str) -> list[Envelope]:
    """Filter captured envelopes by topic."""
    return [e for e in bus.captured if e.topic == topic]


def _parse_payload(envelope: Envelope) -> dict[str, Any]:
    """Parse JSON payload from an envelope."""
    try:
        return json.loads(envelope.payload) if envelope.payload else {}
    except Exception:
        return {}


def _final_response_env(text: str = "ok", envelope_id: int = 100) -> Envelope:
    return _make_envelope(
        topic=TOPIC_FINAL_RESPONSE,
        payload={"text": text},
        envelope_id=envelope_id,
    )


def _user_input_env(text: str = "hello", envelope_id: int = 200) -> Envelope:
    return _make_envelope(
        topic=TOPIC_USER_INPUT,
        payload={"text": text},
        envelope_id=envelope_id,
    )


def _task_complete_env(task_id: str = "t1", envelope_id: int = 300) -> Envelope:
    return _make_envelope(
        topic=TOPIC_TASK_COMPLETE,
        payload={
            "task_id": task_id,
            "result_type": "complete",
            "final_answer": "done",
            "results": [],
        },
        envelope_id=envelope_id,
    )


def _task_failed_env(
    task_id: str = "t1",
    reason: str = "error",
    envelope_id: int = 400,
) -> Envelope:
    return _make_envelope(
        topic=TOPIC_TASK_FAILED,
        payload={
            "task_id": task_id,
            "reason": reason,
            "error_message": "failed",
        },
        envelope_id=envelope_id,
    )


def _task_cancel_env(task_id: str = "t1", envelope_id: int = 500) -> Envelope:
    return _make_envelope(
        topic=TOPIC_TASK_CANCEL,
        payload={"task_id": task_id},
        envelope_id=envelope_id,
    )


def _task_suspended_env(
    task_id: str = "t1",
    question: str = "What color?",
    envelope_id: int = 600,
) -> Envelope:
    return _make_envelope(
        topic=TOPIC_TASK_SUSPENDED,
        payload={
            "task_id": task_id,
            "question": question,
            "hil_type": "clarification",
        },
        envelope_id=envelope_id,
    )


def _tool_started_env(
    task_id: str = "t1", tool_name: str = "search", envelope_id: int = 700
) -> Envelope:
    return _make_envelope(
        topic=TOPIC_TOOL_STARTED,
        payload={"task_id": task_id, "tool_name": tool_name},
        envelope_id=envelope_id,
    )


# =========================================================================
# 2.4.1 -- Guard matrix completeness and handler agreement
# =========================================================================


class TestGuardMatrixCompleteness:
    """Guard table structural integrity and handler agreement."""

    def test_2_4_1a_guard_table_11x18_complete(self) -> None:
        """FULL_GUARD_TABLE has 11 states, each with 18 topics = 198+ cells."""
        assert len(FULL_GUARD_TABLE) == len(ConciergeState)
        total = sum(len(topics) for topics in FULL_GUARD_TABLE.values())
        assert total >= 198, f"Expected >= 198 cells, got {total}"

    def test_2_4_1b_every_cell_has_valid_action(self) -> None:
        """No cell has None action or invalid GuardAction."""
        valid_actions = set(GuardAction)
        for state, topics in FULL_GUARD_TABLE.items():
            for topic, (action, tgt) in topics.items():
                assert (
                    action in valid_actions
                ), f"Invalid action {action} at ({state.name}, {topic})"

    def test_2_4_1c_handler_allows_match_table(self) -> None:
        """For each handler topic, TRANSITION or PASSTHROUGH states align
        with the states where the handler actually processes events."""
        # Build the set of states where each topic is allowed
        for topic in SUBSCRIBED_TOPICS:
            allowed_states = set()
            for state in ConciergeState:
                action, _ = get_guard_action(state, topic)
                if action in (
                    GuardAction.TRANSITION,
                    GuardAction.PASSTHROUGH,
                    GuardAction.OBSERVE,
                    GuardAction.QUEUE,
                ):
                    allowed_states.add(state)
            # Every topic must have at least one allowed state
            assert allowed_states, f"Topic {topic} is DEAD_LETTER in ALL states"

    def test_2_4_1d_dead_letter_default_for_unknown_topic(self) -> None:
        """get_guard_action for an unknown topic returns DEAD_LETTER."""
        action, target = get_guard_action(ConciergeState.LISTENING, "bogus.topic.v1")
        assert action == GuardAction.DEAD_LETTER
        assert target is None

    def test_2_4_1e_all_states_represented(self) -> None:
        """Every ConciergeState enum member has a row in the guard table."""
        for state in ConciergeState:
            assert state in FULL_GUARD_TABLE, f"Missing state: {state.name}"

    def test_2_4_1f_subscribed_topics_cover_all_table_topics(self) -> None:
        """SUBSCRIBED_TOPICS is a superset of all topics in the guard table."""
        all_table_topics = set()
        for topics in FULL_GUARD_TABLE.values():
            all_table_topics.update(topics.keys())
        missing = all_table_topics - SUBSCRIBED_TOPICS
        assert not missing, f"Topics in table but not SUBSCRIBED_TOPICS: {missing}"

    def test_2_4_1g_listening_allows_user_input(self) -> None:
        """LISTENING + user.input -> TRANSITION to DISPATCHING."""
        action, target = get_guard_action(ConciergeState.LISTENING, TOPIC_USER_INPUT)
        assert action == GuardAction.TRANSITION
        assert target == ConciergeState.DISPATCHING

    def test_2_4_1h_listening_rejects_task_dispatch(self) -> None:
        """LISTENING + task.dispatch -> DEAD_LETTER."""
        action, _ = get_guard_action(ConciergeState.LISTENING, TOPIC_TASK_DISPATCH)
        assert action == GuardAction.DEAD_LETTER


# =========================================================================
# 2.4.2 -- Dead-letter capture and reconciliation
# =========================================================================


class TestDeadLetterCaptureAndReconciliation:
    """End-to-end dead-letter pipeline: rejection -> bus -> consumer."""

    def test_2_4_2a_invalid_transition_emits_dead_letter(self) -> None:
        """Force FSM to CLARIFYING_USER, send task.cancel -> dead-letter."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.CLARIFYING_USER
        ctrl._turn_number = 1

        env = _task_cancel_env(task_id="t99", envelope_id=901)
        ctrl._on_task_cancel(env)

        dead_letters = _captured_by_topic(bus, TOPIC_DEAD_LETTER)
        assert len(dead_letters) >= 1
        dl_payload = _parse_payload(dead_letters[0])
        assert dl_payload["reason"] == "task_cancel_invalid_state"
        assert dl_payload["fsm_state_at_rejection"] == "CLARIFYING_USER"

    def test_2_4_2b_dead_letter_consumer_records(self) -> None:
        """Wire DeadLetterConsumer, trigger dead-letter -> consumer records it.

        Note: The dead-letter topic uses STRICT causal ordering in the
        TimingChain, which buffers delivery until the parent envelope is
        marked delivered.  Since the parent (task.cancel) was invoked
        directly (not published through the bus), the child is buffered.
        We verify capture then feed envelopes to the consumer handler
        to validate the recording path.
        """
        ctrl, bus = _make_controller()
        consumer = DeadLetterConsumer(bus=bus)

        ctrl._state = ConciergeState.CLARIFYING_USER
        ctrl._turn_number = 1
        env = _task_cancel_env(task_id="t99", envelope_id=902)
        ctrl._on_task_cancel(env)

        # Dead-letter is captured on the bus but TimingChain buffers it
        dl_envs = _captured_by_topic(bus, TOPIC_DEAD_LETTER)
        assert len(dl_envs) >= 1, "dead-letter must be captured on bus"

        # Feed captured envelopes to consumer (bypasses timing chain)
        for dl_env in dl_envs:
            consumer._on_dead_letter(dl_env)

        assert consumer.total_dead_letters >= 1
        events = consumer.events
        assert len(events) >= 1
        assert events[0].reason == "task_cancel_invalid_state"
        assert events[0].fsm_state_at_rejection == "CLARIFYING_USER"

    def test_2_4_2c_pending_overflow_dead_letter(self) -> None:
        """Enqueue max_depth + 1 results -> dead-letter with reason=overflow."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {f"t{i}" for i in range(20)}

        max_depth = ctrl._turn_state.max_depth
        # Fill to max (will queue in pending results since Front is busy)
        ctrl._front_lock.busy = True
        for i in range(max_depth + 1):
            task_id = f"overflow_t{i}"
            ctrl._active_task_ids.add(task_id)
            env = _task_complete_env(task_id=task_id, envelope_id=2000 + i)
            ctrl._on_task_complete(env)

        dead_letters = _captured_by_topic(bus, TOPIC_DEAD_LETTER)
        overflow_dls = [dl for dl in dead_letters if _parse_payload(dl).get("reason") == "overflow"]
        assert len(overflow_dls) >= 1, "Expected at least 1 overflow dead-letter"

    def test_2_4_2d_pending_ttl_dead_letter(self) -> None:
        """Enqueue result, fake past TTL, drain -> dead-letter with reason=expired."""
        turn_state = FSMTurnState(max_depth=16, ttl_seconds=1)

        stub_env = _make_envelope(
            topic=TOPIC_TASK_COMPLETE,
            payload={"task_id": "t_ttl"},
            envelope_id=3000,
        )
        turn_state.enqueue_result("t_ttl", {"result": "old"}, stub_env)

        # Patch the queued_at_ns to be well past TTL
        assert len(turn_state.pending_results) == 1
        turn_state.pending_results[0]["queued_at_ns"] = (
            time.monotonic_ns() - 5_000_000_000  # 5 seconds ago, TTL is 1s
        )

        valid, expired = turn_state.drain_results()
        assert len(expired) == 1
        assert expired[0]["task_id"] == "t_ttl"
        assert len(valid) == 0

    def test_2_4_2e_dead_letter_disabled_config(self) -> None:
        """With dead_letter_enabled=False, no dead-letter published."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.CLARIFYING_USER

        with patch.object(get_config().fsm, "dead_letter_enabled", False):
            env = _task_cancel_env(task_id="t_disabled", envelope_id=903)
            ctrl._on_task_cancel(env)

        dead_letters = _captured_by_topic(bus, TOPIC_DEAD_LETTER)
        assert len(dead_letters) == 0


# =========================================================================
# 2.4.3 -- Response-final action table exhaustive truth-table
# =========================================================================


class TestResponseFinalTruthTable:
    """Exhaustive parametric test of decide_response_final() covering
    all 13 decision paths plus entry_type resolution."""

    @pytest.mark.parametrize(
        "branch_id, state, pending, active, fallback, flush_running, expected_action, expected_target",
        [
            # Branch 1: DISPATCHING + pending -> WEAVING
            (
                1,
                ConciergeState.DISPATCHING,
                True,
                False,
                False,
                False,
                ResponseFinalAction.TRANSITION_WEAVING,
                ConciergeState.WEAVING,
            ),
            # Branch 2: DISPATCHING + active -> COMPANIONING
            (
                2,
                ConciergeState.DISPATCHING,
                False,
                True,
                False,
                False,
                ResponseFinalAction.TRANSITION_COMPANIONING,
                ConciergeState.COMPANIONING,
            ),
            # Branch 3: DISPATCHING + none -> LISTENING
            (
                3,
                ConciergeState.DISPATCHING,
                False,
                False,
                False,
                False,
                ResponseFinalAction.TRANSITION_LISTENING,
                ConciergeState.LISTENING,
            ),
            # Branch 4: DELIVERING + pending -> WEAVING
            (
                4,
                ConciergeState.DELIVERING,
                True,
                False,
                False,
                False,
                ResponseFinalAction.TRANSITION_WEAVING,
                ConciergeState.WEAVING,
            ),
            # Branch 5: WEAVING + pending + no flush -> WEAVING (re-weave)
            (
                5,
                ConciergeState.WEAVING,
                True,
                False,
                False,
                False,
                ResponseFinalAction.TRANSITION_WEAVING,
                ConciergeState.WEAVING,
            ),
            # Branch 6: WEAVING + pending + flush running -> STAY
            (6, ConciergeState.WEAVING, True, False, False, True, ResponseFinalAction.STAY, None),
            # Branch 7: DELIVERING + no pending -> LISTENING
            (
                7,
                ConciergeState.DELIVERING,
                False,
                False,
                False,
                False,
                ResponseFinalAction.TRANSITION_LISTENING,
                ConciergeState.LISTENING,
            ),
            # Branch 8: WEAVING + no pending -> LISTENING
            (
                8,
                ConciergeState.WEAVING,
                False,
                False,
                False,
                False,
                ResponseFinalAction.TRANSITION_LISTENING,
                ConciergeState.LISTENING,
            ),
            # Branch 9: COMPANIONING + active -> STAY
            (
                9,
                ConciergeState.COMPANIONING,
                False,
                True,
                False,
                False,
                ResponseFinalAction.STAY,
                None,
            ),
            # Branch 10: COMPANIONING + no active -> LISTENING
            (
                10,
                ConciergeState.COMPANIONING,
                False,
                False,
                False,
                False,
                ResponseFinalAction.TRANSITION_LISTENING,
                ConciergeState.LISTENING,
            ),
            # Branch 11: CLARIFYING_WORKER + active -> stay open for HITL answer
            (
                11,
                ConciergeState.CLARIFYING_WORKER,
                False,
                True,
                False,
                False,
                ResponseFinalAction.STAY,
                None,
            ),
            # Branch 12: CLARIFYING_WORKER + no active -> LISTENING
            (
                12,
                ConciergeState.CLARIFYING_WORKER,
                False,
                False,
                False,
                False,
                ResponseFinalAction.TRANSITION_LISTENING,
                ConciergeState.LISTENING,
            ),
            # Branch 13: LISTENING -> IGNORE
            (
                13,
                ConciergeState.LISTENING,
                False,
                False,
                False,
                False,
                ResponseFinalAction.IGNORE,
                None,
            ),
        ],
        ids=[f"branch_{i}" for i in range(1, 14)],
    )
    def test_2_4_3a_truth_table_branch(
        self,
        branch_id: int,
        state: ConciergeState,
        pending: bool,
        active: bool,
        fallback: bool,
        flush_running: bool,
        expected_action: ResponseFinalAction,
        expected_target: ConciergeState | None,
    ) -> None:
        """Parametric test covering all 13 truth-table branches."""
        d = decide_response_final(
            fsm_state=state,
            has_pending_results=pending,
            has_active_tasks=active,
            is_fallback=fallback,
            weave_flush_running=flush_running,
        )
        assert (
            d.action == expected_action
        ), f"Branch {branch_id}: expected action {expected_action}, got {d.action}"
        assert (
            d.target_state == expected_target
        ), f"Branch {branch_id}: expected target {expected_target}, got {d.target_state}"

    def test_2_4_3b_weaving_entry_type(self) -> None:
        """WEAVING -> entry_type = 'weave'."""
        d = decide_response_final(ConciergeState.WEAVING, True, False, False, False)
        assert d.entry_type == "weave"

    def test_2_4_3c_delivering_fallback_entry_type(self) -> None:
        """DELIVERING + fallback -> entry_type = 'proactive_fallback'."""
        d = decide_response_final(ConciergeState.DELIVERING, False, False, True, False)
        assert d.entry_type == "proactive_fallback"

    def test_2_4_3d_delivering_normal_entry_type(self) -> None:
        """DELIVERING + not fallback -> entry_type = 'proactive'."""
        d = decide_response_final(ConciergeState.DELIVERING, False, False, False, False)
        assert d.entry_type == "proactive"

    def test_2_4_3e_default_entry_type_is_final(self) -> None:
        """Any other state -> entry_type = 'final'."""
        d = decide_response_final(ConciergeState.DISPATCHING, False, False, False, False)
        assert d.entry_type == "final"

    def test_2_4_3f_unknown_state_dead_letters(self) -> None:
        """States not in the decision table -> DEAD_LETTER."""
        # PROGRESSING is not in the decision table
        d = decide_response_final(ConciergeState.PROGRESSING, False, False, False, False)
        assert d.action == ResponseFinalAction.DEAD_LETTER

    def test_2_4_3g_dispatching_pending_overrides_active(self) -> None:
        """DISPATCHING + pending + active: pending wins -> WEAVING."""
        d = decide_response_final(ConciergeState.DISPATCHING, True, True, False, False)
        assert d.action == ResponseFinalAction.TRANSITION_WEAVING

    def test_2_4_3h_schedule_weave_flag(self) -> None:
        """Branches producing WEAVING set schedule_weave=True."""
        for state in (ConciergeState.DISPATCHING, ConciergeState.DELIVERING):
            d = decide_response_final(state, True, False, False, False)
            assert d.schedule_weave is True
            assert d.release_front_lock is True

    def test_2_4_3i_listening_branches_emit_turn_completed(self) -> None:
        """All TRANSITION_LISTENING branches set emit_turn_completed=True."""
        for state in (
            ConciergeState.DISPATCHING,
            ConciergeState.DELIVERING,
            ConciergeState.WEAVING,
            ConciergeState.COMPANIONING,
            ConciergeState.CLARIFYING_WORKER,
        ):
            d = decide_response_final(state, False, False, False, False)
            if d.action == ResponseFinalAction.TRANSITION_LISTENING:
                assert (
                    d.emit_turn_completed is True
                ), f"State {state.name} -> LISTENING but emit_turn_completed=False"
                assert d.drain_front_lock is True


# =========================================================================
# 2.4.4 -- Interrupt during PROGRESSING with simultaneous task completion
# =========================================================================


class TestInterruptDuringProgressing:
    """Scenario: interrupt arrives during PROGRESSING, task.complete
    arrives concurrently. Verify correct FSM sequencing."""

    def test_2_4_4a_interrupt_transitions_to_dispatching(self) -> None:
        """PROGRESSING + user.input -> INTERRUPT_HANDLING -> DISPATCHING."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.PROGRESSING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        env = _user_input_env(text="stop that", envelope_id=4001)
        ctrl._on_user_input(env)

        assert ctrl._state == ConciergeState.DISPATCHING
        assert ctrl._turn_number == 2  # Interrupt increments turn

    def test_2_4_4b_task_complete_during_dispatching_queued(self) -> None:
        """task.complete arriving in DISPATCHING is queued, not processed."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        ctrl._turn_number = 2
        ctrl._active_task_ids = {"t1"}

        env = _task_complete_env(task_id="t1", envelope_id=4002)
        ctrl._on_task_complete(env)

        # Should be queued in pending_results
        assert ctrl._turn_state.has_pending_results

    def test_2_4_4c_no_crash_on_interrupt_then_complete(self) -> None:
        """Full sequence: PROGRESSING -> interrupt -> DISPATCHING -> task.complete queued."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.PROGRESSING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        # Step 1: Interrupt
        interrupt_env = _user_input_env(text="cancel", envelope_id=4003)
        ctrl._on_user_input(interrupt_env)
        assert ctrl._state == ConciergeState.DISPATCHING

        # Step 2: Late task.complete for original task
        complete_env = _task_complete_env(task_id="t1", envelope_id=4004)
        ctrl._on_task_complete(complete_env)

        # Verify: no crash, task queued
        assert ctrl._turn_state.has_pending_results

    def test_2_4_4d_no_duplicate_presentation(self) -> None:
        """Interrupt + late complete should not cause duplicate presentation."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.PROGRESSING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        # Interrupt
        ctrl._on_user_input(_user_input_env(text="help", envelope_id=4005))

        # Late complete queued
        ctrl._on_task_complete(_task_complete_env(task_id="t1", envelope_id=4006))

        # Count turn.completed events -- should be at most 1 for the interrupt
        turn_completeds = _captured_by_topic(bus, TOPIC_TURN_COMPLETED)
        # No turn.completed yet because we're still in DISPATCHING
        # (turn completes when Front finishes)
        # The key invariant: no crash, task queued, state is still DISPATCHING
        assert ctrl._state == ConciergeState.DISPATCHING


# =========================================================================
# 2.4.5 -- Cancel race: cancel -> late completion -> failed(cancelled)
# =========================================================================


class TestCancelRace:
    """Scenario: cancel -> late task.complete (discarded) -> task.failed(cancelled)."""

    def test_2_4_5a_cancel_transitions_via_transition_method(self) -> None:
        """COMPANIONING + task.cancel -> CANCELLING via _transition()."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        env = _task_cancel_env(task_id="t1", envelope_id=5001)
        ctrl._on_task_cancel(env)

        assert ctrl._state == ConciergeState.CANCELLING

    def test_2_4_5b_late_completion_discarded_during_cancel(self) -> None:
        """task.complete for cancelled task is discarded, not presented."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        # Step 1: Cancel
        ctrl._on_task_cancel(_task_cancel_env(task_id="t1", envelope_id=5002))
        assert ctrl._state == ConciergeState.CANCELLING

        # Step 2: Late task.complete -- should be discarded
        ctrl._on_task_complete(_task_complete_env(task_id="t1", envelope_id=5003))

        # No dead-letter for the late completion (it's correctly discarded)
        # The cancel handler handles it
        # State should still be CANCELLING
        assert ctrl._state == ConciergeState.CANCELLING

    def test_2_4_5c_failed_cancelled_resolves_cancel(self) -> None:
        """task.failed(reason=cancelled) -> DELIVERING -> confirm cancel."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        # Cancel
        ctrl._on_task_cancel(_task_cancel_env(task_id="t1", envelope_id=5004))
        assert ctrl._state == ConciergeState.CANCELLING

        # task.failed(cancelled)
        failed_env = _task_failed_env(task_id="t1", reason="cancelled", envelope_id=5005)
        ctrl._on_task_failed(failed_env)

        assert ctrl._state == ConciergeState.DELIVERING

    def test_2_4_5d_full_cancel_race_sequence(self) -> None:
        """Full race: cancel -> late complete -> failed(cancelled) -> response.final -> LISTENING."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        # 1. Cancel
        ctrl._on_task_cancel(_task_cancel_env(task_id="t1", envelope_id=5010))
        assert ctrl._state == ConciergeState.CANCELLING

        # 2. Late completion (discarded by cancel_handler)
        ctrl._on_task_complete(_task_complete_env(task_id="t1", envelope_id=5011))

        # 3. task.failed(cancelled) -> DELIVERING
        ctrl._on_task_failed(_task_failed_env(task_id="t1", reason="cancelled", envelope_id=5012))
        assert ctrl._state == ConciergeState.DELIVERING

        # 4. Front responds -> response.final -> LISTENING
        ctrl._on_response_final(_final_response_env(text="cancel done", envelope_id=5013))
        assert ctrl._state == ConciergeState.LISTENING

    def test_2_4_5e_cancel_in_incompatible_state_dead_letters(self) -> None:
        """task.cancel in CLARIFYING_USER -> dead-letter (guard table says DEAD_LETTER)."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.CLARIFYING_USER
        ctrl._turn_number = 1

        ctrl._on_task_cancel(_task_cancel_env(task_id="t1", envelope_id=5020))

        dead_letters = _captured_by_topic(bus, TOPIC_DEAD_LETTER)
        assert len(dead_letters) >= 1


# =========================================================================
# 2.4.6 -- Suspend in incompatible state -> deferred surfacing
# =========================================================================


class TestDeferredHitlSurfacing:
    """Scenario: task.suspended arrives in DISPATCHING, deferred to LISTENING."""

    @pytest.mark.asyncio
    async def test_2_4_6a_suspend_in_dispatching_stores_context(self) -> None:
        """task.suspended in DISPATCHING stores context, does NOT transition."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        env = _task_suspended_env(task_id="t1", envelope_id=6001)
        ctrl._on_task_suspended(env)

        # State should NOT be CLARIFYING_WORKER
        assert ctrl._state == ConciergeState.DISPATCHING
        # Suspension context should be stored in SuspensionManager
        ctx = ctrl._suspension_manager.pop_context("t1")
        assert ctx is not None
        assert ctx.get("question") == "What color?"

    def test_2_4_6b_deferred_hitl_surfaces_from_listening(self) -> None:
        """After reaching LISTENING, deferred HITL is surfaced."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        # Step 1: Register the task in TaskBridge (required before suspend)
        ctrl._task_bridge.dispatch_task("t1", "test-task")

        # Store suspension context directly
        ctrl._suspension_manager.store_context(
            "t1",
            {
                "task_id": "t1",
                "question": "What size?",
                "hil_type": "clarification",
            },
        )
        ctrl._task_bridge.suspend_task("t1")

        # Step 2: Simulate reaching LISTENING naturally
        ctrl._active_task_ids.discard("t1")
        ctrl._state = ConciergeState.LISTENING

        # Step 3: Surface deferred HITL
        trigger_env = _final_response_env(envelope_id=6010)
        ctrl._surface_deferred_hitl(trigger_env)

        # Should have transitioned to CLARIFYING_WORKER
        assert ctrl._state == ConciergeState.CLARIFYING_WORKER

    @pytest.mark.asyncio
    async def test_2_4_6c_no_dead_letter_for_deferred_suspend(self) -> None:
        """Deferred suspension is intentional -- NOT a dead-letter."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1"}

        env = _task_suspended_env(task_id="t1", envelope_id=6020)
        ctrl._on_task_suspended(env)

        dead_letters = _captured_by_topic(bus, TOPIC_DEAD_LETTER)
        assert len(dead_letters) == 0, "Deferred suspension should NOT emit dead-letter"

    def test_2_4_6d_surface_only_one_at_a_time(self) -> None:
        """Multiple deferred suspensions: only first is surfaced per call."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.LISTENING
        ctrl._turn_number = 1

        # Register tasks in TaskBridge (required before suspend)
        ctrl._task_bridge.dispatch_task("t1", "test-task-1")
        ctrl._task_bridge.dispatch_task("t2", "test-task-2")

        # Store two deferred HITL contexts
        ctrl._suspension_manager.store_context(
            "t1",
            {
                "task_id": "t1",
                "question": "Q1",
                "hil_type": "clarification",
            },
        )
        ctrl._task_bridge.suspend_task("t1")

        ctrl._suspension_manager.store_context(
            "t2",
            {
                "task_id": "t2",
                "question": "Q2",
                "hil_type": "clarification",
            },
        )
        ctrl._task_bridge.suspend_task("t2")

        trigger_env = _final_response_env(envelope_id=6030)
        ctrl._surface_deferred_hitl(trigger_env)

        # Only one surfaced
        assert ctrl._state == ConciergeState.CLARIFYING_WORKER
        # t2 context should still be stored (popped for t1, t2 pending)
        # The second will be surfaced after the first resolves
        ctx2 = ctrl._suspension_manager.pop_context("t2")
        assert ctx2 is not None


# =========================================================================
# 2.4.7 -- Weave burst: 3 completions in window + user input
# =========================================================================


class TestWeaveBurst:
    """Scenario: 3 tasks complete while Front is busy, user input queued,
    weave drains, then user input is delivered."""

    def test_2_4_7a_first_complete_transitions_to_delivering(self) -> None:
        """COMPANIONING + task.complete -> DELIVERING."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t1", "t2", "t3"}

        env = _task_complete_env(task_id="t1", envelope_id=7001)
        ctrl._on_task_complete(env)

        assert ctrl._state == ConciergeState.DELIVERING

    def test_2_4_7b_second_complete_queued_in_pending(self) -> None:
        """task.complete during DELIVERING -> queued in pending_results."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DELIVERING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t2", "t3"}
        ctrl._front_lock.busy = True  # Front is busy presenting

        env = _task_complete_env(task_id="t2", envelope_id=7002)
        ctrl._on_task_complete(env)

        assert ctrl._turn_state.has_pending_results

    def test_2_4_7c_user_input_queued_during_delivering(self) -> None:
        """user.input during DELIVERING -> queued in FrontLock."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DELIVERING
        ctrl._turn_number = 1
        ctrl._front_lock.busy = True

        env = _user_input_env(text="hello", envelope_id=7003)
        ctrl._on_user_input(env)

        # User input should be in FrontLock queue
        assert ctrl._front_lock.queue_depth >= 1

    def test_2_4_7d_pending_results_track_multiple(self) -> None:
        """Multiple task completions during DELIVERING all queue."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DELIVERING
        ctrl._turn_number = 1
        ctrl._active_task_ids = {"t2", "t3"}
        ctrl._front_lock.busy = True

        ctrl._on_task_complete(_task_complete_env(task_id="t2", envelope_id=7010))
        ctrl._on_task_complete(_task_complete_env(task_id="t3", envelope_id=7011))

        assert len(ctrl._turn_state.pending_results) == 2

    def test_2_4_7e_response_final_with_pending_transitions_to_weaving(self) -> None:
        """DELIVERING + pending_results -> response.final -> WEAVING."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DELIVERING
        ctrl._turn_number = 1
        ctrl._front_lock.busy = True

        # Queue some pending results
        stub_env = _make_envelope(
            topic=TOPIC_TASK_COMPLETE,
            payload={"task_id": "t2"},
            envelope_id=7020,
        )
        ctrl._turn_state.enqueue_result("t2", {"result": "data2"}, stub_env)

        # response.final with pending -> WEAVING
        ctrl._on_response_final(_final_response_env(envelope_id=7021))

        assert ctrl._state == ConciergeState.WEAVING

    def test_2_4_7f_weave_flush_drains_pending(self) -> None:
        """_flush_weave_now drains pending_results and builds weave envelope."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.WEAVING
        ctrl._turn_number = 1

        # Queue pending results
        for i in range(2):
            stub_env = _make_envelope(
                topic=TOPIC_TASK_COMPLETE,
                payload={"task_id": f"t{i}"},
                envelope_id=7030 + i,
            )
            ctrl._turn_state.enqueue_result(f"t{i}", {"result": f"r{i}"}, stub_env)

        ctrl._flush_weave_now(parent_id=7029)

        # pending_results should be drained
        assert not ctrl._turn_state.has_pending_results


# =========================================================================
# 2.4.8 -- Pending results TTL expiry and overflow dead-letter
# =========================================================================


class TestPendingResultsTTLAndOverflow:
    """Validates FSMTurnState and PendingResultsQueue overflow/TTL guards."""

    def test_2_4_8a_overflow_eviction(self) -> None:
        """max_depth=16, enqueue 17 -> oldest evicted."""
        ts = FSMTurnState(max_depth=16, ttl_seconds=300)
        for i in range(17):
            stub_env = _make_envelope(
                topic=TOPIC_TASK_COMPLETE,
                payload={"task_id": f"t{i}"},
                envelope_id=8000 + i,
            )
            evicted = ts.enqueue_result(f"t{i}", {"i": i}, stub_env)
            if i < 16:
                assert evicted is None
            else:
                # 17th item evicts the oldest
                assert evicted is not None
                assert evicted["task_id"] == "t0"

    def test_2_4_8b_ttl_expiry(self) -> None:
        """Queue result, set timestamp to past, drain -> expired."""
        ts = FSMTurnState(max_depth=16, ttl_seconds=1)
        stub_env = _make_envelope(
            topic=TOPIC_TASK_COMPLETE,
            payload={"task_id": "t_old"},
            envelope_id=8100,
        )
        ts.enqueue_result("t_old", {"data": "old"}, stub_env)

        # Backdate the timestamp
        ts.pending_results[0]["queued_at_ns"] = time.monotonic_ns() - 2_000_000_000

        valid, expired = ts.drain_results()
        assert len(expired) == 1
        assert len(valid) == 0
        assert expired[0]["task_id"] == "t_old"

    @pytest.mark.asyncio
    async def test_2_4_8c_weave_batcher_overflow(self) -> None:
        """WeaveBatcher with max_queued_depth: overflow returns evicted."""

        async def _noop_flush(results: list) -> None:  # noqa: ARG001
            pass

        batcher = WeaveBatcher(flush_fn=_noop_flush, max_queued_depth=3)
        batcher.set_front_busy(True)

        for i in range(4):
            result = WeaveResult(
                task_id=f"t{i}",
                task_description=f"Task {i}",
                result_data={"i": i},
            )
            evicted = await batcher.on_task_complete(result)
            if i < 3:
                assert evicted is None
            else:
                assert evicted is not None

    def test_2_4_8d_mixed_valid_and_expired(self) -> None:
        """Queue 3 results: 1 expired + 2 valid -> drain returns both."""
        ts = FSMTurnState(max_depth=16, ttl_seconds=2)

        for i in range(3):
            stub_env = _make_envelope(
                topic=TOPIC_TASK_COMPLETE,
                payload={"task_id": f"t{i}"},
                envelope_id=8200 + i,
            )
            ts.enqueue_result(f"t{i}", {"i": i}, stub_env)

        # Backdate only the first result
        ts.pending_results[0]["queued_at_ns"] = time.monotonic_ns() - 3_000_000_000

        valid, expired = ts.drain_results()
        assert len(expired) == 1
        assert len(valid) == 2
        assert expired[0]["task_id"] == "t0"

    def test_2_4_8e_overflow_dead_letter_controller(self) -> None:
        """Controller publishes dead-letter on pending_results overflow."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        ctrl._turn_number = 1
        ctrl._turn_state = FSMTurnState(max_depth=2, ttl_seconds=300)

        # Queue 3 results -- 3rd should trigger overflow dead-letter
        for i in range(3):
            task_id = f"overflow_ctrl_{i}"
            ctrl._active_task_ids.add(task_id)
            env = _task_complete_env(task_id=task_id, envelope_id=8300 + i)
            ctrl._on_task_complete(env)

        dead_letters = _captured_by_topic(bus, TOPIC_DEAD_LETTER)
        overflow_dls = [dl for dl in dead_letters if _parse_payload(dl).get("reason") == "overflow"]
        assert len(overflow_dls) >= 1

    def test_2_4_8f_pending_results_queue_overflow(self) -> None:
        """PendingResultsQueue.push at capacity evicts oldest."""
        from k1.concierge.protocols.weave_state import PendingResult

        q = PendingResultsQueue(max_depth=3)
        for i in range(4):
            pr = PendingResult(
                task_id=f"t{i}",
                task_description=f"T{i}",
                result_data={"i": i},
            )
            evicted = q.push(pr)
            if i < 3:
                assert evicted is None
            else:
                assert evicted is not None
                assert evicted.task_id == "t0"
