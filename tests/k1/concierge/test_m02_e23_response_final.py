"""
tests.poc.test_m02_e23_response_final -- E2.3 conformance tests.

Covers:
  2.3.1 -- ResponseFinalDecision truth table (13 branches)
  2.3.2 -- IdempotencyLedger (LRU eviction, check_and_mark)
  2.3.3 -- _topic_guard extraction (4 handlers use single method)
  2.3.4 -- _finalize_turn extraction (emit + drain combo)
  2.3.5 -- _seen_user_input_ids replaced by IdempotencyLedger

Test count target: ~55 tests across 9 test classes.
"""

from __future__ import annotations

import json

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.topics import (
    TOPIC_FINAL_RESPONSE,
    TOPIC_STATE_UPDATED,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TURN_COMPLETED,
    TOPIC_USER_INPUT,
)
from k1.concierge.fsm.idempotency import IdempotencyLedger
from k1.concierge.fsm.response_final_table import (
    ResponseFinalAction,
    decide_response_final,
)
from k1.concierge.fsm.states import ConciergeState

# =========================================================================
# Helpers
# =========================================================================


def _make_envelope(
    topic: str = TOPIC_FINAL_RESPONSE,
    payload: dict | None = None,
    envelope_id: int = 1,
    session_id: str = "unit-session",
) -> Envelope:
    """Build a minimal Envelope for testing."""
    data = payload or {}
    return Envelope(
        topic=topic,
        payload=json.dumps(data).encode(),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        envelope_id=envelope_id,
        session_id=session_id,
    )


def _make_controller():
    """Build a wired ConciergeController for integration tests."""
    from k1.concierge.bus.setup import create_poc_bus, create_poc_router
    from k1.concierge.fsm.controller import ConciergeController

    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    ctrl = ConciergeController(bus=bus, router=router)
    return ctrl, bus


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
        payload={"task_id": task_id, "result": "done"},
        envelope_id=envelope_id,
    )


# =========================================================================
# 2.3.1 -- ResponseFinalDecision truth table (13 branches)
# =========================================================================


class TestDecideResponseFinalTruthTable:
    """Exhaustive truth-table test for decide_response_final() pure function."""

    def test_branch_1_dispatching_has_pending(self):
        """DISPATCHING + has_pending -> WEAVING, schedule_weave."""
        d = decide_response_final(
            ConciergeState.DISPATCHING,
            has_pending_results=True,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_WEAVING
        assert d.target_state == ConciergeState.WEAVING
        assert d.schedule_weave is True
        assert d.emit_turn_completed is False
        assert d.release_front_lock is True

    def test_branch_2_dispatching_has_active(self):
        """DISPATCHING + active_tasks -> COMPANIONING."""
        d = decide_response_final(
            ConciergeState.DISPATCHING,
            has_pending_results=False,
            has_active_tasks=True,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_COMPANIONING
        assert d.target_state == ConciergeState.COMPANIONING
        assert d.emit_turn_completed is False
        assert d.release_front_lock is True

    def test_branch_3_dispatching_no_pending_no_active(self):
        """DISPATCHING + no pending + no active -> LISTENING, turn done."""
        d = decide_response_final(
            ConciergeState.DISPATCHING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_LISTENING
        assert d.target_state == ConciergeState.LISTENING
        assert d.emit_turn_completed is True
        assert d.drain_front_lock is True

    def test_branch_4_delivering_has_pending(self):
        """DELIVERING + has_pending -> WEAVING."""
        d = decide_response_final(
            ConciergeState.DELIVERING,
            has_pending_results=True,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_WEAVING
        assert d.target_state == ConciergeState.WEAVING
        assert d.schedule_weave is True

    def test_branch_5_weaving_has_pending_no_flush(self):
        """WEAVING + pending + no flush running -> re-weave."""
        d = decide_response_final(
            ConciergeState.WEAVING,
            has_pending_results=True,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_WEAVING
        assert d.target_state == ConciergeState.WEAVING
        assert d.schedule_weave is True

    def test_branch_6_weaving_has_pending_flush_running(self):
        """WEAVING + pending + flush running -> STAY."""
        d = decide_response_final(
            ConciergeState.WEAVING,
            has_pending_results=True,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=True,
        )
        assert d.action == ResponseFinalAction.STAY
        assert d.target_state is None
        assert d.schedule_weave is False
        assert d.release_front_lock is True

    def test_branch_7_delivering_no_pending(self):
        """DELIVERING + no pending -> LISTENING, turn done."""
        d = decide_response_final(
            ConciergeState.DELIVERING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_LISTENING
        assert d.target_state == ConciergeState.LISTENING
        assert d.emit_turn_completed is True
        assert d.drain_front_lock is True

    def test_branch_8_weaving_no_pending(self):
        """WEAVING + no pending -> LISTENING, turn done."""
        d = decide_response_final(
            ConciergeState.WEAVING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_LISTENING
        assert d.target_state == ConciergeState.LISTENING
        assert d.emit_turn_completed is True

    def test_branch_9_companioning_has_active(self):
        """COMPANIONING + active_tasks -> STAY."""
        d = decide_response_final(
            ConciergeState.COMPANIONING,
            has_pending_results=False,
            has_active_tasks=True,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.STAY
        assert d.target_state is None
        assert d.emit_turn_completed is False
        assert d.release_front_lock is True

    def test_branch_10_companioning_no_active(self):
        """COMPANIONING + no active -> LISTENING."""
        d = decide_response_final(
            ConciergeState.COMPANIONING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_LISTENING
        assert d.target_state == ConciergeState.LISTENING
        assert d.emit_turn_completed is True

    def test_branch_11_clarifying_worker_has_active(self):
        """CLARIFYING_WORKER + active_tasks -> COMPANIONING."""
        d = decide_response_final(
            ConciergeState.CLARIFYING_WORKER,
            has_pending_results=False,
            has_active_tasks=True,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_COMPANIONING
        assert d.target_state == ConciergeState.COMPANIONING
        assert d.release_front_lock is True

    def test_branch_12_clarifying_worker_no_active(self):
        """CLARIFYING_WORKER + no active -> LISTENING."""
        d = decide_response_final(
            ConciergeState.CLARIFYING_WORKER,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.TRANSITION_LISTENING
        assert d.target_state == ConciergeState.LISTENING
        assert d.emit_turn_completed is True

    def test_branch_13_listening_spurious(self):
        """LISTENING -> IGNORE (spurious final)."""
        d = decide_response_final(
            ConciergeState.LISTENING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.IGNORE
        assert d.target_state is None
        assert d.emit_turn_completed is False
        assert d.drain_front_lock is False

    def test_unknown_state_dead_letter(self):
        """States not in the table produce DEAD_LETTER."""
        d = decide_response_final(
            ConciergeState.CANCELLING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.action == ResponseFinalAction.DEAD_LETTER


class TestResponseFinalEntryType:
    """Verify entry_type resolution in decisions."""

    def test_weaving_entry_type(self):
        d = decide_response_final(
            ConciergeState.WEAVING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.entry_type == "weave"

    def test_delivering_fallback_entry_type(self):
        d = decide_response_final(
            ConciergeState.DELIVERING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=True,
            weave_flush_running=False,
        )
        assert d.entry_type == "proactive_fallback"

    def test_delivering_normal_entry_type(self):
        d = decide_response_final(
            ConciergeState.DELIVERING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.entry_type == "proactive"

    def test_dispatching_entry_type(self):
        d = decide_response_final(
            ConciergeState.DISPATCHING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        assert d.entry_type == "final"

    def test_decision_is_frozen(self):
        """ResponseFinalDecision is immutable."""
        d = decide_response_final(
            ConciergeState.LISTENING,
            has_pending_results=False,
            has_active_tasks=False,
            is_fallback=False,
            weave_flush_running=False,
        )
        with pytest.raises(AttributeError):
            d.action = ResponseFinalAction.STAY  # type: ignore[misc]


class TestResponseFinalActionEnum:
    """Verify enum completeness."""

    def test_has_6_members(self):
        assert len(ResponseFinalAction) == 6

    def test_all_values(self):
        values = {a.value for a in ResponseFinalAction}
        expected = {
            "transition_listening",
            "transition_weaving",
            "transition_companioning",
            "stay",
            "ignore",
            "dead_letter",
        }
        assert values == expected


# =========================================================================
# 2.3.1 -- Controller integration: _on_response_final uses decision table
# =========================================================================


class TestControllerResponseFinal:
    """Verify _on_response_final delegates to decide_response_final."""

    def test_dispatching_no_pending_transitions_to_listening(self):
        """DISPATCHING + no pending + no active -> LISTENING."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        ctrl._turn_number = 1
        ctrl._on_response_final(_final_response_env())
        assert ctrl._state == ConciergeState.LISTENING

    def test_dispatching_with_pending_transitions_to_weaving(self):
        """DISPATCHING + pending results -> WEAVING."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        ctrl._turn_number = 1
        ctrl._turn_state.enqueue_result("t1", {"result": "x"}, _task_complete_env())
        ctrl._on_response_final(_final_response_env())
        assert ctrl._state == ConciergeState.WEAVING

    def test_dispatching_with_active_tasks_transitions_to_companioning(self):
        """DISPATCHING + active tasks -> COMPANIONING."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        ctrl._turn_number = 1
        ctrl._active_task_ids.add("t1")
        ctrl._on_response_final(_final_response_env())
        assert ctrl._state == ConciergeState.COMPANIONING

    def test_listening_spurious_stays_listening(self):
        """LISTENING + spurious final -> stays LISTENING, no turn.completed."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.LISTENING
        ctrl._on_response_final(_final_response_env())
        assert ctrl._state == ConciergeState.LISTENING
        # No turn.completed emitted
        turn_completed = [e for e in bus.captured if e.topic == TOPIC_TURN_COMPLETED]
        assert len(turn_completed) == 0

    def test_delivering_no_pending_transitions_to_listening(self):
        """DELIVERING + no pending -> LISTENING + turn.completed."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DELIVERING
        ctrl._turn_number = 1
        ctrl._on_response_final(_final_response_env())
        assert ctrl._state == ConciergeState.LISTENING
        turn_completed = [e for e in bus.captured if e.topic == TOPIC_TURN_COMPLETED]
        assert len(turn_completed) >= 1

    def test_clarifying_worker_with_active_tasks_transitions_to_companioning(self):
        """CLARIFYING_WORKER + active tasks -> COMPANIONING."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.CLARIFYING_WORKER
        ctrl._turn_number = 1
        ctrl._active_task_ids.add("t1")
        ctrl._on_response_final(_final_response_env())
        assert ctrl._state == ConciergeState.COMPANIONING
        turn_completed = [e for e in bus.captured if e.topic == TOPIC_TURN_COMPLETED]
        assert len(turn_completed) == 0

    def test_clarifying_worker_no_active_tasks_transitions_to_listening(self):
        """CLARIFYING_WORKER + no active tasks -> LISTENING + turn.completed."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.CLARIFYING_WORKER
        ctrl._turn_number = 1
        ctrl._on_response_final(_final_response_env())
        assert ctrl._state == ConciergeState.LISTENING
        turn_completed = [e for e in bus.captured if e.topic == TOPIC_TURN_COMPLETED]
        assert len(turn_completed) >= 1

    def test_topic_guard_rejects_wrong_topic(self):
        """Envelope with wrong topic is rejected by topic guard."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        wrong_env = _make_envelope(topic=TOPIC_STATE_UPDATED, payload={"text": "x"})
        ctrl._on_response_final(wrong_env)
        # State unchanged
        assert ctrl._state == ConciergeState.DISPATCHING


# =========================================================================
# 2.3.2 -- IdempotencyLedger
# =========================================================================


class TestIdempotencyLedger:
    """Unit tests for IdempotencyLedger."""

    def test_new_event_returns_true(self):
        ledger = IdempotencyLedger(max_entries=10)
        assert ledger.check_and_mark(1, 1) is True

    def test_duplicate_returns_false(self):
        ledger = IdempotencyLedger(max_entries=10)
        ledger.check_and_mark(1, 1)
        assert ledger.check_and_mark(1, 2) is False

    def test_lru_eviction_oldest(self):
        """When at capacity, oldest entry is evicted (not all)."""
        ledger = IdempotencyLedger(max_entries=3)
        ledger.check_and_mark(1, 1)
        ledger.check_and_mark(2, 1)
        ledger.check_and_mark(3, 1)
        # Now at capacity -- adding 4 evicts 1
        ledger.check_and_mark(4, 2)
        assert ledger.size == 3
        # 1 was evicted, so it's "new" again
        assert ledger.contains(1) is False
        # 2, 3, 4 are still tracked
        assert ledger.contains(2) is True
        assert ledger.contains(3) is True
        assert ledger.contains(4) is True

    def test_size_property(self):
        ledger = IdempotencyLedger(max_entries=100)
        assert ledger.size == 0
        ledger.check_and_mark(1, 1)
        assert ledger.size == 1

    def test_max_entries_property(self):
        ledger = IdempotencyLedger(max_entries=42)
        assert ledger.max_entries == 42

    def test_contains_without_marking(self):
        ledger = IdempotencyLedger(max_entries=10)
        assert ledger.contains(1) is False
        ledger.check_and_mark(1, 1)
        assert ledger.contains(1) is True

    def test_reset_clears_all(self):
        ledger = IdempotencyLedger(max_entries=10)
        ledger.check_and_mark(1, 1)
        ledger.check_and_mark(2, 1)
        ledger.reset()
        assert ledger.size == 0
        assert ledger.check_and_mark(1, 2) is True

    def test_no_clear_all_window(self):
        """Unlike the old set-based approach, filling to capacity doesn't clear all."""
        ledger = IdempotencyLedger(max_entries=3)
        ledger.check_and_mark(1, 1)
        ledger.check_and_mark(2, 1)
        ledger.check_and_mark(3, 1)
        # At capacity -- 4 evicts only 1
        ledger.check_and_mark(4, 2)
        assert ledger.size == 3  # not 0 or 1
        # 2, 3 still tracked
        assert ledger.contains(2)
        assert ledger.contains(3)


# =========================================================================
# 2.3.2 -- Controller idempotency integration
# =========================================================================


class TestControllerIdempotency:
    """Verify IdempotencyLedger is wired into controller handlers."""

    def test_user_input_dedup(self):
        """Duplicate user.input envelope_id is silently skipped."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.LISTENING
        env = _user_input_env(envelope_id=42)
        ctrl._on_user_input(env)
        initial_state = ctrl._state
        bus_count_before = len(bus.captured)
        # Send same envelope again
        ctrl._state = ConciergeState.LISTENING
        ctrl._on_user_input(env)
        # Second call should be a no-op -- no additional bus events
        # (we check that no additional turn_started was emitted)
        turn_started_count = sum(1 for e in bus.captured if e.topic == "k1.session.turn.started.v1")
        # Only 1 turn_started from the first call
        assert turn_started_count <= 1

    def test_task_complete_dedup(self):
        """Duplicate task.complete envelope_id is silently skipped."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._active_task_ids.add("t1")
        ctrl._turn_number = 1
        env = _task_complete_env(task_id="t1", envelope_id=300)
        ctrl._on_task_complete(env)
        state_after_first = ctrl._state
        # Reset state for second attempt
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._active_task_ids.add("t1")
        ctrl._on_task_complete(env)
        # Second call is a no-op because idempotency ledger blocks it
        # Active task t1 should still be in the set (wasn't removed by second call)
        assert "t1" in ctrl._active_task_ids

    def test_task_failed_dedup(self):
        """Duplicate task.failed envelope_id is silently skipped."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._active_task_ids.add("t1")
        ctrl._turn_number = 1
        env = _make_envelope(
            topic=TOPIC_TASK_FAILED,
            payload={"task_id": "t1", "reason": "error"},
            envelope_id=400,
        )
        ctrl._on_task_failed(env)
        # Send again
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._active_task_ids.add("t1")
        ctrl._on_task_failed(env)
        # Second call is a no-op
        assert "t1" in ctrl._active_task_ids

    @pytest.mark.asyncio
    async def test_task_suspended_dedup(self):
        """Duplicate task.suspended envelope_id is silently skipped."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._turn_number = 1
        env = _make_envelope(
            topic=TOPIC_TASK_SUSPENDED,
            payload={"task_id": "t1", "question": "pick one"},
            envelope_id=500,
        )
        ctrl._on_task_suspended(env)
        state_after_first = ctrl._state
        # Send same again
        ctrl._state = ConciergeState.COMPANIONING
        ctrl._on_task_suspended(env)
        # Second call is no-op, state unchanged from reset
        assert ctrl._state == ConciergeState.COMPANIONING

    def test_idempotency_uses_config_max_entries(self):
        """IdempotencyLedger max_entries comes from config."""
        ctrl, _ = _make_controller()
        from k1.concierge.config import get_config

        expected = get_config().fsm.idempotency_ledger_max_entries
        assert ctrl._idempotency.max_entries == expected


# =========================================================================
# 2.3.3 -- _topic_guard extraction
# =========================================================================


class TestTopicGuardExtraction:
    """Verify _topic_guard is a single method used by all 4 handlers."""

    def test_topic_guard_matches(self):
        ctrl, _ = _make_controller()
        env = _make_envelope(topic=TOPIC_USER_INPUT)
        assert ctrl._topic_guard(env, TOPIC_USER_INPUT) is True

    def test_topic_guard_rejects(self):
        ctrl, _ = _make_controller()
        env = _make_envelope(topic=TOPIC_STATE_UPDATED)
        assert ctrl._topic_guard(env, TOPIC_USER_INPUT) is False

    def test_user_input_handler_uses_topic_guard(self):
        """_on_user_input rejects wrong topic via _topic_guard."""
        ctrl, _ = _make_controller()
        ctrl._state = ConciergeState.LISTENING
        wrong = _make_envelope(topic=TOPIC_STATE_UPDATED, payload={"text": "x"})
        ctrl._on_user_input(wrong)
        assert ctrl._state == ConciergeState.LISTENING

    def test_task_complete_handler_uses_topic_guard(self):
        ctrl, _ = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        wrong = _make_envelope(topic=TOPIC_STATE_UPDATED, payload={"task_id": "t1"})
        ctrl._on_task_complete(wrong)
        assert ctrl._state == ConciergeState.COMPANIONING

    def test_task_suspended_handler_uses_topic_guard(self):
        ctrl, _ = _make_controller()
        ctrl._state = ConciergeState.COMPANIONING
        wrong = _make_envelope(topic=TOPIC_STATE_UPDATED, payload={"task_id": "t1"})
        ctrl._on_task_suspended(wrong)
        assert ctrl._state == ConciergeState.COMPANIONING

    def test_response_final_handler_uses_topic_guard(self):
        ctrl, _ = _make_controller()
        ctrl._state = ConciergeState.DISPATCHING
        wrong = _make_envelope(topic=TOPIC_STATE_UPDATED, payload={"text": "x"})
        ctrl._on_response_final(wrong)
        assert ctrl._state == ConciergeState.DISPATCHING

    def test_no_copy_pasted_topic_guards_in_controller(self):
        """Verify TOPIC GUARD pattern no longer appears inline."""
        import inspect

        source = inspect.getsource(type(_make_controller()[0]))
        # The old pattern had "TOPIC GUARD --" in logger.debug
        # Now only _topic_guard should contain the guard logic
        # Count occurrences of the OLD pattern
        old_pattern_count = source.count("TOPIC GUARD --")
        assert old_pattern_count == 0, (
            f"Found {old_pattern_count} old-style 'TOPIC GUARD --' blocks; "
            "all should be replaced by _topic_guard()"
        )


# =========================================================================
# 2.3.4 -- _finalize_turn extraction
# =========================================================================


class TestFinalizeTurnExtraction:
    """Verify _finalize_turn is a single method replacing 3 combo sites."""

    def test_finalize_turn_emits_turn_completed(self):
        """_finalize_turn emits turn.completed."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.LISTENING
        ctrl._turn_number = 1
        env = _final_response_env()
        ctrl._finalize_turn(env)
        turn_completed = [e for e in bus.captured if e.topic == TOPIC_TURN_COMPLETED]
        assert len(turn_completed) >= 1

    def test_finalize_turn_drains_front_lock(self):
        """_finalize_turn calls _drain_front_lock_queue."""
        ctrl, bus = _make_controller()
        ctrl._state = ConciergeState.LISTENING
        ctrl._turn_number = 1
        # Queue something in front lock
        queued_env = _user_input_env(text="queued", envelope_id=999)
        ctrl._front_lock._enqueue(queued_env)
        ctrl._finalize_turn(_final_response_env())
        # The queued event should be drained and re-dispatched
        # Check that front_lock is empty after drain
        assert len(ctrl._front_lock.event_queue) == 0

    def test_no_bare_emit_drain_combo(self):
        """Verify no bare _emit_turn_completed + _drain_front_lock_queue sequences."""
        import inspect

        source = inspect.getsource(type(_make_controller()[0]))
        # Find lines where _emit_turn_completed is called
        lines = source.split("\n")
        for i, line in enumerate(lines):
            if "_emit_turn_completed(" in line and "def _emit_turn_completed" not in line:
                # This should only appear inside _finalize_turn definition
                # Check that it's inside _finalize_turn
                # Look backwards for the nearest def
                for j in range(i - 1, -1, -1):
                    stripped = lines[j].strip()
                    if stripped.startswith("def "):
                        method_name = stripped.split("(")[0].replace("def ", "")
                        assert method_name in (
                            "_finalize_turn",
                            "_emit_turn_completed",
                        ), f"Found bare _emit_turn_completed call in {method_name} at line {i}"
                        break


# =========================================================================
# 2.3.5 -- _seen_user_input_ids removed
# =========================================================================


class TestSeenUserInputIdsRemoved:
    """Verify _seen_user_input_ids set is fully replaced."""

    def test_no_seen_user_input_ids_attribute(self):
        """Controller should not have _seen_user_input_ids."""
        ctrl, _ = _make_controller()
        assert not hasattr(
            ctrl, "_seen_user_input_ids"
        ), "_seen_user_input_ids should be replaced by _idempotency"

    def test_has_idempotency_attribute(self):
        """Controller should have _idempotency."""
        ctrl, _ = _make_controller()
        assert hasattr(ctrl, "_idempotency")
        assert isinstance(ctrl._idempotency, IdempotencyLedger)

    def test_no_clear_all_pattern_in_source(self):
        """No '> 200: .clear()' pattern in controller source."""
        import inspect

        source = inspect.getsource(type(_make_controller()[0]))
        assert "_seen_user_input_ids" not in source
        assert "> 200" not in source


# =========================================================================
# Config integration
# =========================================================================


class TestE23ConfigIntegration:
    """Verify E2.3 config values are wired correctly."""

    def test_idempotency_ledger_max_entries_in_config(self):
        from k1.concierge.config import get_config

        cfg = get_config()
        assert cfg.fsm.idempotency_ledger_max_entries == 500

    def test_idempotency_ledger_in_defaults_yaml(self):
        import yaml

        with open("poc/k1_poc/config/defaults.yaml") as f:
            raw = yaml.safe_load(f)
        assert raw["fsm"]["idempotency_ledger_max_entries"] == 500
