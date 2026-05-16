from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import MagicMock

import pytest

from k1.bus.envelope import Envelope
from k1.concierge.bus.builders import build_task_complete
from k1.concierge.bus.setup import create_poc_bus
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.fsm.front_lock import FrontLock
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.fsm.turn_state import FSMTurnState
from k1.concierge.protocols.weave_batcher import WeaveBatcher, WeaveResult
from k1.concierge.protocols.weave_policy import UserActivityTracker, WeavePolicy


class RecordingRouter:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, Envelope]] = []

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        self.deliveries.append((actor_id, envelope))


class PacingProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def on_weave_flush(self, *, results: list[dict[str, Any]], batch_count: int) -> Any:
        self.calls.append({"results": results, "batch_count": batch_count})
        return type("Pacing", (), {"use_pacing": False})()


def _controller() -> tuple[ConciergeController, RecordingRouter]:
    bus = create_poc_bus(capture=True)
    router = RecordingRouter()
    ctrl = ConciergeController(bus=bus, router=router)  # type: ignore[arg-type]
    ctrl.set_weave_policy(WeavePolicy())
    ctrl.set_activity_tracker(UserActivityTracker())
    return ctrl, router


def _task_complete(task_id: str = "task-1") -> tuple[Envelope, dict[str, Any]]:
    payload = {
        "task_id": task_id,
        "result_type": "complete",
        "final_answer": f"done {task_id}",
        "results": [{"answer": task_id}],
    }
    env = build_task_complete(payload=payload, parent_id=10)
    return replace(env, envelope_id=100), payload


def test_typing_task_complete_defers_without_front_delivery() -> None:
    ctrl, router = _controller()
    env, payload = _task_complete("task-typing")
    ctrl._state = ConciergeState.PROGRESSING
    assert ctrl._activity_tracker is not None
    ctrl._activity_tracker.on_typing_start()

    ctrl._on_task_complete_adaptive(env, payload, "task-typing")

    assert ctrl.turn_state.depth == 0
    assert [item["task_id"] for item in ctrl.turn_state.deferred_results] == ["task-typing"]
    assert router.deliveries == []


def test_pending_hitl_task_complete_defers_non_critical_without_front_delivery() -> None:
    ctrl, router = _controller()
    env, payload = _task_complete("task-hitl")
    ctrl._state = ConciergeState.PROGRESSING
    ctrl._pending_hil_subtasks["hitl-task"] = MagicMock()

    ctrl._on_task_complete_adaptive(env, payload, "task-hitl")

    assert ctrl.turn_state.depth == 0
    assert [item["task_id"] for item in ctrl.turn_state.deferred_results] == ["task-hitl"]
    assert router.deliveries == []


def test_flush_weave_now_calls_opp_hook_once_per_flush() -> None:
    ctrl, router = _controller()
    probe = PacingProbe()
    ctrl.set_opp_pipeline(probe)
    env, payload = _task_complete("task-batch")
    ctrl.turn_state.enqueue_result("task-batch", payload, env, urgency="normal")

    ctrl._flush_weave_now(parent_id=env.envelope_id)

    assert len(probe.calls) == 1
    assert probe.calls[0]["batch_count"] == 1
    assert router.deliveries


def test_suppress_result_discards_pending_deferred_and_batcher_queues() -> None:
    ctrl, _router = _controller()
    env, payload = _task_complete("task-drop")
    ctrl.turn_state.enqueue_result("task-drop", payload, env, urgency="normal")
    ctrl.turn_state.defer_result({"task_id": "task-drop", "result": payload})
    batcher = MagicMock()
    batcher.discard_task.return_value = True
    ctrl.set_weave_batcher(batcher)

    ctrl._suppress_result("task-drop", "test")

    assert ctrl.turn_state.depth == 0
    assert ctrl.turn_state.deferred_results == []
    batcher.discard_task.assert_called_once_with("task-drop")


def test_turn_state_discard_task_removes_pending_and_deferred() -> None:
    state = FSMTurnState()
    env, payload = _task_complete("task-owned")
    state.enqueue_result("task-owned", payload, env, urgency="normal")
    state.enqueue_result("task-keep", payload, env, urgency="normal")
    state.defer_result({"task_id": "task-owned", "result": payload})
    state.defer_result({"task_id": "task-keep", "result": payload})

    removed = state.discard_task("task-owned")

    assert removed is True
    assert [item["task_id"] for item in state.pending_results] == ["task-keep"]
    assert [item["task_id"] for item in state.deferred_results] == ["task-keep"]


def test_front_lock_context_injection_capability_is_explicitly_disabled() -> None:
    lock = FrontLock()

    assert lock.is_accepting_context() is False


@pytest.mark.asyncio
async def test_weave_batcher_discard_task_removes_pending_and_queued() -> None:
    flushed: list[WeaveResult] = []

    async def flush_fn(results: list[WeaveResult]) -> None:
        flushed.extend(results)

    batcher = WeaveBatcher(flush_fn=flush_fn, batch_window_ms=5000, max_queued_depth=4)
    await batcher.on_task_complete(
        WeaveResult(task_id="pending", task_description="pending", result_data={})
    )
    batcher.set_front_busy(True)
    await batcher.on_task_complete(
        WeaveResult(task_id="queued", task_description="queued", result_data={})
    )

    assert batcher.discard_task("pending") is True
    assert batcher.pending_count == 0
    assert batcher.discard_task("queued") is True
    assert batcher.queued_count == 0
    assert flushed == []
