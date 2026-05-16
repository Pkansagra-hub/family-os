from __future__ import annotations

from k1.concierge.events.hitl import HILRequested, HILResolved
from k1.concierge.events.task import TaskCompleted
from k1.concierge.ledger.projections import project_hitl_state
from k1.concierge.ledger.store import InMemoryLedgerStore
from k1.concierge.ledger.writer import LedgerWriter

SESSION_ID = "m5-hitl-projection"


def _writer() -> LedgerWriter:
    return LedgerWriter(InMemoryLedgerStore(), session_id=SESSION_ID)


def _entries(writer: LedgerWriter):
    return writer.store.read(SESSION_ID)


def test_project_hitl_state_normalizes_unified_and_legacy_rows() -> None:
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
    legacy = HILRequested(
        session_id=SESSION_ID,
        task_id="task-1",
        hil_type="approval",
        question="Proceed?",
    )
    writer.append_sync(legacy)

    pending, counts, histories = project_hitl_state(_entries(writer))

    assert pending["hil:h1"].hil_request_id == "h1"
    assert pending["hil:h1"].kind == "clarification"
    assert pending["hil:h1"].caller_key == "planner:p1"
    assert pending["task-1"].hil_request_id == legacy.event_id
    assert pending["task-1"].kind == "approval"
    assert counts == {"hil:h1": 1, "task-1": 1}
    assert histories == {}


def test_project_hitl_state_removes_resolved_request_by_hil_request_id() -> None:
    writer = _writer()
    writer.append_sync(
        HILRequested(
            session_id=SESSION_ID,
            task_id="hil:h1",
            hil_request_id="h1",
            kind="clarification",
            question="Which city?",
        )
    )
    writer.append_sync(
        HILResolved(
            session_id=SESSION_ID,
            task_id="hil:h1",
            hil_request_id="h1",
            kind="clarification",
            raw_user_text="Paris",
            resolution={"answer": "Paris"},
            resolution_type="answered",
        )
    )

    pending, counts, histories = project_hitl_state(_entries(writer))

    assert pending == {}
    assert counts == {"hil:h1": 1}
    assert histories["hil:h1"][0]["hil_request_id"] == "h1"


def test_project_hitl_state_terminal_task_clears_pending_request() -> None:
    writer = _writer()
    writer.append_sync(
        HILRequested(
            session_id=SESSION_ID,
            task_id="task-1",
            hil_request_id="h1",
            kind="needs_human",
            question="Need detail",
        )
    )
    writer.append_sync(
        TaskCompleted(
            session_id=SESSION_ID,
            task_id="task-1",
            result_data={"summary": "done"},
        )
    )

    pending, _counts, _histories = project_hitl_state(_entries(writer))

    assert pending == {}
