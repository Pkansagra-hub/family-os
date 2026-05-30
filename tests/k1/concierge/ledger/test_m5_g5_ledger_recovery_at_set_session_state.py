"""M5 G5 -- Ledger-driven crash recovery during ``set_session_state``.

These tests pin the production wiring added in milestone M5 acceptance:

* ``ConciergeConfig.enable_ledger_recovery`` toggles ``ConciergeFactory``
  into calling ``fsm.enable_ledger_recovery_on_attach()`` after
  ``set_ledger`` and before ``set_session_state``.
* When the flag is on AND a ``LedgerWriter`` is attached, the controller
  runs ``CrashRecoveryOrchestrator.recover(...)`` inside
  ``set_session_state`` BEFORE its own ``_recover_hitl_on_startup``
  scan, then short-circuits that scan via ``mark_ledger_recovery_done``.
* When the flag is off, behavior is unchanged: no replay happens at
  attach, ``_ledger_recovery_done`` stays False, and the controller's
  history cache remains empty.
"""

from __future__ import annotations

from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.events.conversation import UserInputReceived
from k1.concierge.events.hitl import HILRequested
from k1.concierge.events.task import TaskCreated
from k1.concierge.events.weave import WeaveEmitted
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.ledger.store import InMemoryLedgerStore
from k1.concierge.ledger.writer import LedgerWriter
from k1.sessionstate.factory import SessionStateFactory

SESSION_ID = "m5-g5-session"


def _seed_ledger_store() -> InMemoryLedgerStore:
    """Pre-populate a ledger store as if a prior boot wrote four events."""
    store = InMemoryLedgerStore()
    writer = LedgerWriter(store=store, session_id=SESSION_ID)
    writer.append_sync(UserInputReceived(session_id=SESSION_ID, text="hello", actor="user"))
    writer.append_sync(
        TaskCreated(
            session_id=SESSION_ID,
            task_id="task-1",
            action="search",
            actor="fsm",
        )
    )
    writer.append_sync(
        HILRequested(
            session_id=SESSION_ID,
            task_id="hil:h1",
            hil_request_id="h1",
            kind="clarification",
            caller_key="planner:p1",
            hil_type="clarification",
            question="Which city?",
            timeout_ms=60_000,
        )
    )
    writer.append_sync(
        WeaveEmitted(
            session_id=SESSION_ID,
            response_text_preview="hi there",
            actor="front",
        )
    )
    return store


def _fresh_controller_with_ledger(
    store: InMemoryLedgerStore,
) -> tuple[ConciergeController, LedgerWriter]:
    fsm = ConciergeController(bus=create_poc_bus(capture=True), router=create_poc_router())
    writer = LedgerWriter(store=store, session_id=SESSION_ID)
    fsm.set_ledger(writer)
    return fsm, writer


def test_set_session_state_runs_ledger_recovery_when_opted_in() -> None:
    """G5 happy path -- replay restores history, tasks, HITL state."""
    store = _seed_ledger_store()
    fsm, _writer = _fresh_controller_with_ledger(store)

    # Pre-condition: a freshly built controller has empty history/tasks.
    assert fsm.history == []
    assert fsm.active_task_ids == set()
    assert fsm._ledger_recovery_done is False

    fsm.enable_ledger_recovery_on_attach()
    ss = SessionStateFactory.create_for_testing()
    ss.start()
    try:
        fsm.set_session_state(ss)

        # Recovery ran and claimed authority.
        assert fsm._ledger_recovery_done is True

        # History cache restored from WeaveEmitted + UserInputReceived.
        history_types = [entry.entry_type for entry in fsm.history]
        assert "user" in history_types
        assert "assistant_response" in history_types

        # Active task projection landed in TaskBridge through rebind.
        assert "task-1" in fsm.active_task_ids
        assert fsm.task_bridge.is_rebound

        # HITL pending suspension restored into unified task state.
        hil_task = fsm.task_bridge.get_task("hil:h1")
        assert hil_task is not None
        assert hil_task.pending_hil_data["hil_request_id"] == "h1"
        assert fsm._has_pending_hitl() is True
    finally:
        ss.stop()


def test_set_session_state_skips_replay_when_flag_off() -> None:
    """Default-off: no recovery runs even with a populated ledger."""
    store = _seed_ledger_store()
    fsm, _writer = _fresh_controller_with_ledger(store)

    # Deliberately DO NOT call enable_ledger_recovery_on_attach.
    ss = SessionStateFactory.create_for_testing()
    ss.start()
    try:
        fsm.set_session_state(ss)

        assert fsm._ledger_recovery_done is False
        # History cache untouched -- controller did not replay events.
        assert fsm.history == []
        # No active task projected from the ledger.
        assert fsm.active_task_ids == set()
    finally:
        ss.stop()


def test_recover_hitl_on_startup_short_circuits_after_ledger_recovery() -> None:
    """G5 invariant: HITL scan no-ops once ledger replay owns recovery."""
    store = _seed_ledger_store()
    fsm, _writer = _fresh_controller_with_ledger(store)

    fsm.enable_ledger_recovery_on_attach()
    ss = SessionStateFactory.create_for_testing()
    ss.start()
    try:
        fsm.set_session_state(ss)
        assert fsm._ledger_recovery_done is True

        # Calling the scan a second time must remain a no-op -- it must
        # not re-publish hitl.timed_out.v1 or re-register HILSubTasks.
        pending_before = dict(fsm._pending_hil_subtasks)
        fsm._recover_hitl_on_startup()
        assert fsm._pending_hil_subtasks == pending_before
    finally:
        ss.stop()
