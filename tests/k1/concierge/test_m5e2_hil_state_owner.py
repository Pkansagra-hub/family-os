from __future__ import annotations

from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.protocols.hitl_persistence import HILStateRecord
from k1.sessionstate.sections.task_state import TaskStatus


def _controller() -> ConciergeController:
    return ConciergeController(bus=create_poc_bus(capture=True), router=create_poc_router())


def test_hil_state_record_normalizes_missing_optional_fields() -> None:
    record = HILStateRecord.from_projection_payload(
        "hil:h1",
        {
            "hil_request_id": "h1",
            "kind": "clarification",
            "question": "Which city?",
        },
    )

    assert record.task_id == "hil:h1"
    assert record.pending_hil_id == "h1"
    assert record.hil_type == "clarification"
    assert record.options == []
    assert record.to_pending_hil_data()["envelope"]["hil_request_id"] == "h1"


def test_rebuild_pending_hil_from_projection_restores_unified_task_state() -> None:
    fsm = _controller()
    records = {
        "hil:h1": HILStateRecord(
            task_id="hil:h1",
            hil_request_id="h1",
            pending_hil_id="h1",
            kind="clarification",
            hil_type="clarification",
            question="Which city?",
            caller_key="planner:p1",
        )
    }

    restored = fsm.rebuild_pending_hil_from_projection(records)
    task = fsm.task_bridge.get_task("hil:h1")

    assert restored == 1
    assert task is not None
    assert task.status == TaskStatus.SUSPENDED
    assert task.pending_hil_data["hil_request_id"] == "h1"
    assert fsm._has_pending_hitl() is True


def test_has_pending_hitl_sees_suspended_task_bridge_data() -> None:
    fsm = _controller()
    fsm.task_bridge.task_state.add_task(
        action="hil:clarification",
        task_id="hil:h2",
        status=TaskStatus.SUSPENDED,
    )
    fsm.task_bridge.set_pending_hil_data(
        "hil:h2",
        {"hil_request_id": "h2", "kind": "clarification"},
    )

    assert fsm._pending_hil_subtasks == {}
    assert fsm._has_pending_hitl() is True


def test_hil_coherence_reports_mismatched_request_id() -> None:
    fsm = _controller()
    fsm.task_bridge.task_state.add_task(
        action="hil:clarification",
        task_id="hil:h3",
        status=TaskStatus.SUSPENDED,
    )
    fsm.task_bridge.set_pending_hil_data(
        "hil:h3",
        {"hil_request_id": "h3", "kind": "clarification"},
    )

    anomalies = fsm._check_hil_state_coherence(
        task_id="hil:h3",
        hil_request_id="other",
        context="test",
    )

    assert anomalies == ["task_pending_hil_id_mismatch:h3!=other"]
