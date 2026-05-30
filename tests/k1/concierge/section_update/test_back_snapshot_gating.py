"""M2.I6 Back snapshot gating for dispatch-critical overlays."""

from __future__ import annotations

import json

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.actors.back import _read_ss_snapshot
from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.bus.topics import TOPIC_TASK_DISPATCH
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.section_update.overlay import (
    OVERLAY_TASK_PAYLOAD_KEY,
    build_dispatch_overlay_from_plan,
    degraded_turn_state_overlay,
    summarize_task_overlay,
)
from k1.concierge.section_update.types import (
    CommitClass,
    SectionMutation,
    SectionUpdatePlan,
)
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.concierge.task.intent import TaskIntent


class _SS:
    def get_section(self, _name: str):
        return None


def _dispatch() -> TaskDispatch:
    return TaskDispatch(
        task_id="task-overlay-1",
        tier=ComplexityTier.LOW,
        intents=[TaskIntent(action="search", params={"target": "it"})],
    )


def _envelope(payload: dict, session_id: str = "session-1") -> Envelope:
    return Envelope(
        topic=TOPIC_TASK_DISPATCH,
        payload=json.dumps(payload).encode(),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        envelope_id=42,
        session_id=session_id,
        cognitive_trace_id="trace-1",
    )


def _overlay(turn_id: str = "session-1:4") -> dict:
    plan = SectionUpdatePlan(
        plan_id="plan-1",
        turn_id=turn_id,
        session_id="session-1",
        snapshot_version="snap-1",
        snapshot_source_epoch="11",
        mutations=[
            SectionMutation(
                section="scoreboard",
                operation="add_referent",
                data={"text": "it", "entity_id": "hotel-1"},
                confidence=0.9,
                reason="Back needs the referent before task start.",
                commit_class=CommitClass.DISPATCH_CRITICAL,
            )
        ],
    )
    overlay = build_dispatch_overlay_from_plan(plan, durable=False, status="timed_out")
    assert overlay is not None
    return overlay


def _captured_payload(envelope: Envelope) -> dict:
    return json.loads(envelope.payload.decode())


def test_controller_attaches_registered_overlay_before_back_delivery() -> None:
    bus = create_poc_bus(capture=True)
    ctrl = ConciergeController(bus=bus, router=create_poc_router())
    dispatch = _dispatch()
    ctrl._turn_number = 4
    ctrl.register_turn_state_overlay(_overlay())
    delivered: list[Envelope] = []
    ctrl._deliver_to_back = delivered.append

    ctrl._route_via_orchestrator(_envelope(dispatch.to_dict()), dispatch)

    payload = _captured_payload(delivered[0])
    overlay = payload[OVERLAY_TASK_PAYLOAD_KEY]
    assert overlay["turn_id"] == "session-1:4"
    assert overlay["durable"] is False
    assert overlay["sections"]["scoreboard"]["mutations"][0]["operation"] == "add_referent"
    assert summarize_task_overlay(payload)["fields_applied"] == ["scoreboard.add_referent"]


def test_controller_preserves_one_explicit_dispatch_overlay() -> None:
    bus = create_poc_bus(capture=True)
    ctrl = ConciergeController(bus=bus, router=create_poc_router())
    dispatch = _dispatch()
    explicit = degraded_turn_state_overlay(
        turn_id="session-1:4",
        degraded_reason="classifier_timeout",
    )
    raw_payload = dispatch.to_dict()
    raw_payload[OVERLAY_TASK_PAYLOAD_KEY] = explicit
    delivered: list[Envelope] = []
    ctrl._deliver_to_back = delivered.append

    ctrl._route_via_orchestrator(_envelope(raw_payload), dispatch)

    payload = _captured_payload(delivered[0])
    assert payload[OVERLAY_TASK_PAYLOAD_KEY]["degraded_reason"] == "classifier_timeout"
    assert list(key for key in payload if key == OVERLAY_TASK_PAYLOAD_KEY) == [
        OVERLAY_TASK_PAYLOAD_KEY
    ]


def test_back_snapshot_does_not_treat_overlay_as_durable_sessionstate() -> None:
    payload = _dispatch().to_dict()
    payload[OVERLAY_TASK_PAYLOAD_KEY] = _overlay()

    snapshot = _read_ss_snapshot(_SS())
    summary = summarize_task_overlay(payload)

    assert OVERLAY_TASK_PAYLOAD_KEY not in snapshot
    assert summary["present"] is True
    assert summary["durable"] is False
