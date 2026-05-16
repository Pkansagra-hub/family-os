"""HIL presentation dedupe regressions for the Concierge FSM."""

from __future__ import annotations

import json

from k1.bus.envelope import Envelope
from k1.concierge.bus.builders import build_task_suspended
from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.bus.topics import TOPIC_HIL_REQUEST
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.fsm.front_lock import PRIORITY_INTERACTIVE
from k1.concierge.fsm.states import ConciergeState


def _hil_request(kind: str = "capability_gate") -> Envelope:
    return Envelope(
        topic=TOPIC_HIL_REQUEST,
        envelope_id=101,
        payload=json.dumps(
            {
                "hil_request_id": "hil-gate-1",
                "kind": kind,
                "caller_key": "fabric:tool.execute.tasks.create_task",
                "trace_id": "trace-hil",
                "created_at_ms": 1,
                "timeout_ms": 120_000,
                "payload": {
                    "capability_name": "tool.execute.tasks.create_task",
                    "params_summary": "title=clean room, assigned_to=riley",
                    "contract": {"safety_band_min": "AMBER"},
                },
            }
        ).encode(),
    )


def test_inline_hil_gate_is_not_delivered_to_front(monkeypatch) -> None:
    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    ctrl = ConciergeController(bus=bus, router=router)
    ctrl._state = ConciergeState.PROGRESSING
    delivered: list[Envelope] = []
    monkeypatch.setattr(ctrl, "_deliver_to_front", delivered.append)

    ctrl._on_hil_request(_hil_request())

    assert delivered == []
    assert ctrl._state == ConciergeState.PROGRESSING
    assert ctrl._front_lock.is_idle
    assert ctrl._task_bridge.get_task("hil:hil-gate-1") is None


def test_stale_task_suspended_prompt_is_dropped_for_resumed_task() -> None:
    ctrl = ConciergeController(bus=create_poc_bus(capture=True), router=create_poc_router())
    task_id = "task-1"
    queued = build_task_suspended(
        {
            "task_id": task_id,
            "hil_type": "clarification",
            "question": "stale question",
        }
    )
    ctrl._front_lock.event_queue.append((PRIORITY_INTERACTIVE, queued))

    dropped = ctrl._drop_queued_front_hitl_for_task(task_id)

    assert dropped == 1
    assert list(ctrl._front_lock.event_queue) == []
