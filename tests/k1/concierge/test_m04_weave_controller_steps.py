from __future__ import annotations

from dataclasses import replace
from typing import Any

from k1.bus.envelope import Envelope
from k1.concierge.bus.builders import build_task_complete
from k1.concierge.bus.setup import ACTOR_FRONT, create_poc_bus
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.protocols.weave_policy import (
    UserActivityTracker,
    WeaveDecision,
    WeavePolicy,
)


class RecordingRouter:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, Envelope]] = []

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        self.deliveries.append((actor_id, envelope))


def _controller() -> tuple[ConciergeController, Any, RecordingRouter]:
    bus = create_poc_bus(capture=True)
    router = RecordingRouter()
    ctrl = ConciergeController(bus=bus, router=router)  # type: ignore[arg-type]
    ctrl.set_weave_policy(WeavePolicy())
    ctrl.set_activity_tracker(UserActivityTracker())
    return ctrl, bus, router


def _task_complete(task_id: str = "task-1") -> tuple[Envelope, dict[str, Any]]:
    payload = {
        "task_id": task_id,
        "result_type": "complete",
        "final_answer": "done",
        "results": [{"answer": "42"}],
    }
    env = build_task_complete(payload=payload, parent_id=10)
    return replace(env, envelope_id=42), payload


def test_collect_weave_signal_is_read_only_and_reports_runtime_state() -> None:
    ctrl, bus, _router = _controller()
    env, _payload = _task_complete("task-signal")
    ctrl._state = ConciergeState.PROGRESSING
    ctrl.turn_state.enqueue_result("task-signal", {"final_answer": "done"}, env, urgency="critical")

    before_publish_count = len(bus.captured)
    signal = ctrl._collect_weave_signal("task-signal")

    assert signal.fsm_state == "PROGRESSING"
    assert signal.pending_count == 1
    assert signal.has_critical is True
    assert len(bus.captured) == before_publish_count


def test_decide_weave_uses_policy_without_applying_side_effects() -> None:
    ctrl, _bus, router = _controller()
    signal = ctrl._collect_weave_signal("task-none")

    decision = ctrl._decide_weave(signal)

    assert decision.decision == WeaveDecision.BATCH
    assert router.deliveries == []


def test_apply_weave_decision_batch_delivers_through_front_lock_in_sync_path() -> None:
    ctrl, _bus, router = _controller()
    env, payload = _task_complete("task-immediate")
    ctrl._state = ConciergeState.PROGRESSING
    ctrl.turn_state.enqueue_result("task-immediate", payload, env, urgency="normal")
    decision = ctrl._decide_weave(ctrl._collect_weave_signal("task-immediate"))

    ctrl._apply_weave_decision(decision, "task-immediate", env)

    assert router.deliveries
    assert router.deliveries[-1][0] == ACTOR_FRONT
