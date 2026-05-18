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


def test_after_task_cleanup_invokes_suspension_cleanup_and_coherence(monkeypatch) -> None:
    """G1: _after_task_cleanup must call cleanup_task then coherence checker."""
    fsm = _controller()

    calls: list[tuple[str, dict]] = []

    class _FakeSM:
        def cleanup_task(self, task_id: str) -> None:
            calls.append(("cleanup", {"task_id": task_id}))

    fsm._suspension_manager = _FakeSM()  # type: ignore[assignment]

    def _track_coherence(
        *, task_id: str = "", hil_request_id: str = "", context: str = ""
    ) -> list[str]:
        calls.append(
            (
                "coherence",
                {"task_id": task_id, "hil_request_id": hil_request_id, "context": context},
            )
        )
        return []

    monkeypatch.setattr(fsm, "_check_hil_state_coherence", _track_coherence)

    fsm._after_task_cleanup("hil:h4", context="task_complete")

    assert [c[0] for c in calls] == ["cleanup", "coherence"]
    assert calls[0][1] == {"task_id": "hil:h4"}
    assert calls[1][1]["context"] == "task_complete"
    assert calls[1][1]["task_id"] == "hil:h4"


def test_after_task_cleanup_swallows_suspension_failure(monkeypatch) -> None:
    """G1: helper must run coherence check even if cleanup raises."""
    fsm = _controller()

    class _BoomSM:
        def cleanup_task(self, task_id: str) -> None:  # noqa: ARG002
            raise RuntimeError("boom")

    fsm._suspension_manager = _BoomSM()  # type: ignore[assignment]

    coherence_called: list[str] = []

    def _track_coherence(
        *, task_id: str = "", hil_request_id: str = "", context: str = ""
    ) -> list[str]:  # noqa: ARG001
        coherence_called.append(context)
        return []

    monkeypatch.setattr(fsm, "_check_hil_state_coherence", _track_coherence)

    # Must not raise.
    fsm._after_task_cleanup("hil:h5", context="task_failed")

    assert coherence_called == ["task_failed"]
