from __future__ import annotations

from types import SimpleNamespace

from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.events.conversation import UserInputReceived
from k1.concierge.events.hitl import HILRequested
from k1.concierge.events.task import TaskCreated
from k1.concierge.events.weave import WeaveEmitted
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.ledger.recovery import CrashRecoveryOrchestrator
from k1.concierge.ledger.store import InMemoryLedgerStore
from k1.concierge.ledger.writer import LedgerWriter
from k1.concierge.protocols.hitl_persistence import TaskStatus

SESSION_ID = "m5-full-recovery"


def _writer() -> LedgerWriter:
    return LedgerWriter(InMemoryLedgerStore(), session_id=SESSION_ID)


def _controller() -> ConciergeController:
    return ConciergeController(bus=create_poc_bus(capture=True), router=create_poc_router())


def test_recovery_rebuilds_history_cache_without_writing_ledger() -> None:
    writer = _writer()
    writer.append_sync(UserInputReceived(session_id=SESSION_ID, text="hello", actor="user"))
    writer.append_sync(
        WeaveEmitted(
            session_id=SESSION_ID,
            response_text_preview="hi there",
            actor="front",
        )
    )
    before = writer.store.count(SESSION_ID)

    fsm = _controller()
    report = CrashRecoveryOrchestrator().recover(fsm, writer.store, SESSION_ID)

    assert report.recovered is True
    assert report.history_entries == 2
    assert len(fsm.history) == 2
    assert fsm.history[0].entry_type == "user"
    assert fsm.history[1].entry_type == "assistant_response"
    assert writer.store.count(SESSION_ID) == before


def test_recovery_restores_pending_unified_hil_into_task_state() -> None:
    writer = _writer()
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

    fsm = _controller()
    report = CrashRecoveryOrchestrator().recover(fsm, writer.store, SESSION_ID)

    task = fsm.task_bridge.get_task("hil:h1")
    assert report.recovered is True
    assert report.hitl_pending_restored == 1
    assert task is not None
    assert task.pending_hil_data["hil_request_id"] == "h1"
    assert fsm._has_pending_hitl() is True
    assert report._details["coherence_anomalies"] == []


def test_recovery_records_coherence_anomalies_without_raising() -> None:
    recovery = CrashRecoveryOrchestrator()
    fsm = SimpleNamespace(
        _suspension_manager=SimpleNamespace(has_context=lambda _task_id: False),
        _task_bridge=SimpleNamespace(get_task=lambda _task_id: None),
    )
    task_states = {"task-1": SimpleNamespace(status=TaskStatus.SUSPENDED)}

    anomalies = recovery._check_recovery_coherence(
        fsm,
        task_states,
        pending_results=[],
        pending_hil={},
        active_task_ids={"task-1"},
    )

    assert anomalies == ["suspended_task_without_pending_hil:task-1"]


def test_recovery_applies_active_task_ids_cache() -> None:
    writer = _writer()
    writer.append_sync(
        TaskCreated(
            session_id=SESSION_ID,
            task_id="task-1",
            action="search",
            actor="fsm",
        )
    )

    fsm = _controller()
    report = CrashRecoveryOrchestrator().recover(fsm, writer.store, SESSION_ID)

    assert report.active_task_count == 1
    assert fsm.active_task_ids == {"task-1"}
