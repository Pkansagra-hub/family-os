"""M5-X16..M5-X19 live-kernel MW circuit and Concierge guard probes."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from k1.concierge.bus.builders import (
    build_dag_completed,
    build_final_response,
    build_turn_completed,
    build_user_input,
)
from k1.concierge.bus.topics import (
    TOPIC_DAG_COMPLETED,
    TOPIC_TASK_COMPLETE,
    TOPIC_TURN_COMPLETED,
    TOPIC_USER_INPUT,
)
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.memory_writer.adapters.test_adapters import FakeModelHubPort
from k1.memory_writer.events import TOPIC_CIRCUIT_OPEN
from k1.memory_writer.health.circuit_breaker import CircuitBreakerState

pytestmark = pytest.mark.integration


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path, **overrides: Any) -> KernelConfig:
    values: dict[str, Any] = {
        "test_mode": True,
        "model_mode": "test",
        "ordered_bus": True,
        "session_mode": "standalone",
        "bridge_enabled": False,
        "bridge_offline_ok": True,
        "otel_enabled": False,
        "enable_hitl": False,
        "enable_hil_service": False,
        "enable_self_model": False,
        "enable_family_tools": False,
        "sessionstate_db_path": str(tmp_path / "ssm.db"),
        "workflow_db_path": str(tmp_path / "workflows.db"),
        "bridge_outbox_path": str(tmp_path / "bridge.db"),
    }
    values.update(overrides)
    return KernelConfig(**values)


async def _assert_no_task_leaks(baseline_tasks: set[asyncio.Task[object]]) -> None:
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert leaked == set(), f"Leaked tasks: {[task.get_name() for task in leaked]}"


async def _cleanup_service(
    svc: KernelService,
    session_id: str,
    baseline_tasks: set[asyncio.Task[object]],
) -> None:
    if session_id in svc._sessions:
        await svc.destroy_session(session_id)
    if svc.is_running:
        await svc.shutdown()
    await _assert_no_task_leaks(baseline_tasks)


def _raw_bus(bus: Any) -> Any:
    return getattr(bus, "inner", bus)


def _decode_payload(envelope: Any) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


async def _flush_bus_tasks(bus: Any) -> None:
    assert _raw_bus(bus).flush(timeout_ms=5_000)
    for _ in range(5):
        await asyncio.sleep(0)


async def _wait_until(predicate: Callable[[], bool], description: str) -> None:
    for _ in range(50):
        if predicate():
            return
        await asyncio.sleep(0)
    assert predicate(), description


def _subscription_topic_counts(bus: Any) -> Counter[str]:
    return Counter(topic for topic, _handler in bus.list_subscriptions())


def _turn_completed_payload(
    *,
    turn_id: str,
    session_id: str,
    trace_id: str,
    turn_number: int,
) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "session_id": session_id,
        "cognitive_trace_id": trace_id,
        "user_message": f"Mira practiced piano for recital round {turn_number}.",
        "assistant_response": "I will remember the piano practice update.",
        "timestamp_ms": 1_700_000_000_000 + turn_number,
        "turn_number": turn_number,
    }


@pytest.mark.asyncio
async def test_m5_x16_three_llm_failures_open_mw_circuit_and_fourth_skips_agent(
    tmp_path: Path,
) -> None:
    """Three real MW model-edge failures open the CB; the fourth turn emits circuit.open."""
    session_id = "m5x16"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        model = FakeModelHubPort(fail=True)
        session.memory_writer._pipeline._writer_agent._model_hub = model
        session.memory_writer._dispatcher._flush_turn_threshold = 1

        circuit_open_events: list[Any] = []
        circuit_handle = session.bus.subscribe(TOPIC_CIRCUIT_OPEN, circuit_open_events.append)
        try:
            for turn_number in range(1, 4):
                payload = _turn_completed_payload(
                    turn_id=f"{session_id}:{turn_number}",
                    session_id=session_id,
                    trace_id=f"trace-m5-x16-{turn_number}",
                    turn_number=turn_number,
                )
                session.bus.publish(build_turn_completed(payload=payload))
                await _flush_bus_tasks(session.bus)
                await _wait_until(
                    lambda n=turn_number: len(model.calls) == n,
                    f"MW did not attempt failed LLM call {turn_number}",
                )

            assert session.memory_writer.circuit_breaker.state == CircuitBreakerState.OPEN
            assert len(circuit_open_events) == 0

            fourth = _turn_completed_payload(
                turn_id=f"{session_id}:4",
                session_id=session_id,
                trace_id="trace-m5-x16-4",
                turn_number=4,
            )
            session.bus.publish(build_turn_completed(payload=fourth))
            await _flush_bus_tasks(session.bus)

            await _wait_until(
                lambda: len(circuit_open_events) == 1,
                "MW did not publish k1.mw.circuit.open.v1 on the fourth turn",
            )

            assert len(model.calls) == 3
            event_payload = _decode_payload(circuit_open_events[0])
            assert event_payload["trace_id"] == "trace-m5-x16-4"
        finally:
            session.bus.unsubscribe(circuit_handle)
            await session.memory_writer.stop()
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x17_emitted_turn_ids_blocks_duplicate_turn_completed_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second same-turn finalization does not publish a duplicate turn.completed event."""
    session_id = "m5x17"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        delivered_to_front: list[str] = []

        def hold_front_delivery(envelope: Any) -> None:
            delivered_to_front.append(envelope.topic)

        monkeypatch.setattr(session.concierge._fsm, "_deliver_to_front", hold_front_delivery)

        completed: list[Any] = []
        completed_handle = session.bus.subscribe(TOPIC_TURN_COMPLETED, completed.append)
        try:
            user_text = "Please remember Mira completed her recital practice."
            session.bus.publish(
                build_user_input(payload={"text": user_text, "device_id": "device-m5-x17"})
            )
            await _flush_bus_tasks(session.bus)

            assert session.concierge.state == "DISPATCHING"
            assert delivered_to_front == [TOPIC_USER_INPUT]

            final_env = replace(
                build_final_response(payload={"text": "Got it, Mira completed practice."}),
                cognitive_trace_id="trace-m5-x17",
                session_id=session_id,
            )
            session.bus.publish(final_env)
            await _flush_bus_tasks(session.bus)

            await _wait_until(lambda: len(completed) == 1, "first turn.completed missing")
            emitted_turn_id = _decode_payload(completed[0])["turn_id"]
            assert emitted_turn_id in session.concierge._fsm._emitted_turn_ids

            session.concierge._fsm._emit_turn_completed(final_env)
            await _flush_bus_tasks(session.bus)

            assert len(completed) == 1
            assert list(session.concierge._fsm._emitted_turn_ids).count(emitted_turn_id) == 1
        finally:
            session.bus.unsubscribe(completed_handle)
            await session.memory_writer.stop()
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x18_missing_ledger_and_session_id_rejects_turn_completed_before_publish(
    tmp_path: Path,
) -> None:
    """Without ledger or envelope session id, Concierge refuses the degenerate turn:N id."""
    session_id = "m5x18"
    svc = KernelService(config=_recipe_a(tmp_path, enable_ledger=False))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        fsm = session.concierge._fsm

        assert fsm._ledger is None
        fsm._turn_number = 1
        fsm._current_turn_user_text = "Remember this should not publish without session scope."

        completed: list[Any] = []
        completed_handle = session.bus.subscribe(TOPIC_TURN_COMPLETED, completed.append)
        try:
            final_env = build_final_response(payload={"text": "No scoped session id."})
            assert final_env.session_id == ""

            fsm._emit_turn_completed(final_env)
            await _flush_bus_tasks(session.bus)

            assert completed == []
            assert "turn:1" not in fsm._emitted_turn_ids
        finally:
            session.bus.unsubscribe(completed_handle)
            await session.memory_writer.stop()
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x19_single_dag_completed_event_invokes_normalizer_once(
    tmp_path: Path,
) -> None:
    """The live FSM has one dag.completed subscription and emits one task.complete."""
    session_id = "m5x19"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        raw_bus = _raw_bus(session.bus)

        topic_counts = _subscription_topic_counts(raw_bus)
        assert topic_counts[TOPIC_DAG_COMPLETED] == 1
        assert topic_counts["k1.orchestration.dag.completed"] == 0

        task_complete: list[Any] = []
        task_complete_handle = session.bus.subscribe(TOPIC_TASK_COMPLETE, task_complete.append)
        try:
            session.bus.publish(
                build_dag_completed(
                    payload={
                        "task_id": "task-m5-x19",
                        "success": True,
                        "summary": "The DAG completed once.",
                        "step_results": [],
                        "artifacts_created": [],
                    }
                )
            )
            await _flush_bus_tasks(session.bus)

            assert len(task_complete) == 1
            payload = _decode_payload(task_complete[0])
            assert payload["task_id"] == "task-m5-x19"
            assert payload["final_answer"] == "The DAG completed once."
        finally:
            session.bus.unsubscribe(task_complete_handle)
            await session.memory_writer.stop()
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)
