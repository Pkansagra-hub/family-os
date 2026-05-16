"""M1.E1.I4: unified HIL must not double-resume through task.resume."""

from __future__ import annotations

from typing import Any

from k1.concierge.bus.builders import build_hil_response, build_task_resume
from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.fsm.transition_table import GuardAction


def test_unified_pending_hil_drops_legacy_task_resume(monkeypatch) -> None:
    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    ctrl = ConciergeController(bus=bus, router=router)
    ctrl._state = ConciergeState.CLARIFYING_WORKER

    task_id = "task-unified-hil"
    hil_request_id = "hil-unified-1"
    ctrl._task_bridge.dispatch_task(task_id, "needs a human")
    ctrl._task_bridge.activate_task(task_id)
    ctrl._task_bridge.suspend_task(task_id)
    ctrl._task_bridge.set_pending_hil_data(
        task_id,
        {
            "hil_request_id": hil_request_id,
            "envelope": {
                "hil_request_id": hil_request_id,
                "kind": "needs_human",
                "caller_key": "back:test",
                "trace_id": "trace-m1",
                "created_at_ms": 1,
                "timeout_ms": 60_000,
                "payload": {"task_id": task_id, "question": "Which city?"},
            },
        },
    )

    delivered_to_back: list[Any] = []
    monkeypatch.setattr(ctrl, "_guard_dispatch", lambda _env: GuardAction.PASSTHROUGH)
    monkeypatch.setattr(ctrl, "_deliver_to_back", delivered_to_back.append)

    bus.publish(
        build_hil_response(
            {
                "hil_request_id": hil_request_id,
                "kind": "needs_human",
                "responded_at_ms": 2,
                "payload": {"decision": "answered"},
                "timed_out": False,
            }
        )
    )
    ctrl._on_task_resume(
        build_task_resume(
            {
                "task_id": task_id,
                "resolution": {"additional_info": "Use Paris."},
            }
        )
    )

    assert delivered_to_back == []
    assert task_id not in ctrl._hitl_responded_tasks
