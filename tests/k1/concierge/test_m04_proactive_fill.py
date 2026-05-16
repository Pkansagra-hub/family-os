from __future__ import annotations

from dataclasses import replace
from typing import Any

from k1.bus.envelope import Envelope
from k1.concierge.actors.front import _extract_scenario_data
from k1.concierge.bus.builders import build_proactive_fill
from k1.concierge.bus.setup import ACTOR_FRONT, create_poc_bus
from k1.concierge.bus.topics import TOPIC_PROACTIVE_FILL
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.prompt.mode import PromptMode, determine_mode
from k1.concierge.protocols.weave_policy import UserActivityTracker


class RecordingRouter:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, Envelope]] = []

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        self.deliveries.append((actor_id, envelope))


class AffectSessionState:
    def __init__(self, affect: dict[str, Any]) -> None:
        self._affect = affect

    def get_section(self, name: str) -> Any:
        if name == "affective_now":
            return self._affect
        return None


def _controller() -> tuple[ConciergeController, RecordingRouter]:
    bus = create_poc_bus(capture=True)
    router = RecordingRouter()
    ctrl = ConciergeController(bus=bus, router=router)  # type: ignore[arg-type]
    ctrl.set_activity_tracker(UserActivityTracker())
    return ctrl, router


def _fill_env(task_id: str = "task-1", message: str = "Working on the search...") -> Envelope:
    env = build_proactive_fill(
        payload={
            "task_id": task_id,
            "message": message,
            "style": "informational",
            "show_progress": True,
        },
        parent_id=20,
    )
    return replace(env, envelope_id=200)


def test_proactive_fill_topic_resolves_to_present_mode() -> None:
    assert determine_mode("LISTENING", TOPIC_PROACTIVE_FILL) == PromptMode.PRESENT


def test_proactive_fill_scenario_data_preserves_fill_payload_for_front_voice() -> None:
    env = _fill_env(message="Working on the restaurant search...")

    data = _extract_scenario_data(PromptMode.PRESENT, env, ss=None)

    assert data["proactive_fill_message"] == "Working on the restaurant search..."
    assert data["proactive_fill_style"] == "informational"
    assert data["proactive_fill_show_progress"] is True
    assert "restaurant search" in data["task_result_summary"]


def test_on_proactive_fill_delivers_to_front_not_raw_final_text() -> None:
    ctrl, router = _controller()
    env = _fill_env()

    ctrl._on_proactive_fill(env)

    assert router.deliveries == [(ACTOR_FRONT, env)]


def test_on_proactive_fill_suppresses_pending_hitl() -> None:
    ctrl, router = _controller()
    ctrl._pending_hil_subtasks["hitl-task"] = object()  # type: ignore[assignment]

    ctrl._on_proactive_fill(_fill_env())

    assert router.deliveries == []


def test_on_proactive_fill_suppresses_crisis_gate() -> None:
    ctrl, router = _controller()
    ctrl._ss = AffectSessionState({"current_emotion": "crisis", "safety_band": "RED"})

    ctrl._on_proactive_fill(_fill_env())

    assert router.deliveries == []


def test_on_proactive_fill_suppresses_clarifying_worker_state() -> None:
    ctrl, router = _controller()
    ctrl._state = ConciergeState.CLARIFYING_WORKER

    ctrl._on_proactive_fill(_fill_env())

    assert router.deliveries == []


def test_on_proactive_fill_rate_limits_same_task_and_kind() -> None:
    ctrl, router = _controller()
    env = _fill_env(task_id="task-rate")

    ctrl._on_proactive_fill(env)
    ctrl._on_proactive_fill(replace(env, envelope_id=201))

    assert router.deliveries == [(ACTOR_FRONT, env)]
    assert ctrl.front_lock.queue_depth == 0
