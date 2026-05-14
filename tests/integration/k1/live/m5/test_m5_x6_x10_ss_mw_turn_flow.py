"""M5-X6..M5-X10 live-kernel SessionState, MemoryWriter, and turn-flow probes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from k1.concierge.bus.builders import (
    build_final_response,
    build_turn_completed,
    build_user_input,
)
from k1.concierge.bus.topics import TOPIC_TURN_COMPLETED, TOPIC_USER_INPUT
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.memory_writer.adapters.session_read_adapter import SessionReadAdapter
from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
from k1.sessionstate.adapters.local_events import LocalEventAdapter
from k1.sessionstate.events import EventType
from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.manager import LifecycleError
from k1.sessionstate.ports.writer import MutationRequest, MutationStatus
from k1.sessionstate.sizetracker import WARM_SIZE_LIMIT_BYTES

pytestmark = pytest.mark.integration


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path) -> KernelConfig:
    return KernelConfig(
        test_mode=True,
        model_mode="test",
        ordered_bus=True,
        session_mode="standalone",
        bridge_enabled=False,
        bridge_offline_ok=True,
        otel_enabled=False,
        enable_hitl=False,
        enable_hil_service=False,
        enable_self_model=False,
        enable_family_tools=False,
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "workflows.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


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


def _mutation_request(
    *,
    writer_id: str = "direct",
    trace_id: str = "trace-m5-x7",
    turn_number: int = 1,
) -> MutationRequest:
    return MutationRequest.create(
        section="telemetry",
        operation="record_turn",
        data={
            "turn_number": turn_number,
            "duration_ms": 25,
            "token_count": 12,
            "had_error": False,
            "had_tool_call": False,
        },
        writer_id=writer_id,
        cognitive_trace_id=trace_id,
        estimated_bytes=128,
    )


def _turn_completed_envelope(session_id: str) -> Any:
    return build_turn_completed(
        payload={
            "turn_id": f"{session_id}:x6",
            "session_id": session_id,
            "cognitive_trace_id": "trace-m5-x6",
            "user_message": "We ate soup before rehearsal.",
            "assistant_response": "I will remember that.",
            "timestamp_ms": 1_700_000_000_001,
            "turn_number": 1,
        }
    )


@pytest.mark.asyncio
async def test_m5_x6_memory_writer_has_no_sessionstate_write_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MW receives only the SSM read adapter and never calls SessionStateManager.mutate."""
    session_id = "m5x6"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        adapter = session.memory_writer._pipeline._session_reader._port
        assert isinstance(adapter, SessionReadAdapter)
        assert adapter._manager is session.session_state
        assert not hasattr(adapter, "mutate")
        assert not hasattr(adapter, "request_mutation")
        assert not hasattr(adapter, "batch_mutations")
        assert session.session_state._writer_port is not adapter

        manager_cls = type(session.session_state)
        original_mutate = manager_cls.mutate
        mutate_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def mutate_spy(self: Any, *args: Any, **kwargs: Any) -> Any:
            if self is session.session_state:
                mutate_calls.append((args, kwargs))
            return original_mutate(self, *args, **kwargs)

        monkeypatch.setattr(manager_cls, "mutate", mutate_spy)

        session.bus.publish(_turn_completed_envelope(session_id))
        assert _raw_bus(session.bus).flush(timeout_ms=5_000)
        await asyncio.sleep(0)
        assert session.memory_writer._dispatcher.buffered_count == 1

        await session.memory_writer.stop()

        assert mutate_calls == []
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x7_direct_writer_rejects_before_start_and_accepts_after_start(
    tmp_path: Path,
) -> None:
    """DirectWriterAdapter enforces the SSM lifecycle before applying mutations."""
    prestart_manager = SessionStateFactory.create_for_testing(session_id="m5x7-prestart")
    try:
        writer = prestart_manager._writer_port
        assert isinstance(writer, DirectWriterAdapter)

        with pytest.raises(LifecycleError):
            writer.request_mutation(
                _mutation_request(writer_id=writer.writer_id, trace_id="trace-m5-x7-pre")
            )
    finally:
        event_port = prestart_manager._event_port
        if hasattr(event_port, "stop"):
            event_port.stop()

    session_id = "m5x7"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        live_writer = session.session_state._writer_port
        assert isinstance(live_writer, DirectWriterAdapter)
        assert live_writer._manager is session.session_state
        assert session.session_state.is_running

        response = live_writer.request_mutation(
            _mutation_request(
                writer_id=live_writer.writer_id,
                trace_id="trace-m5-x7-post",
                turn_number=2,
            )
        )

        assert response.status is MutationStatus.APPLIED
        assert response.approved is True
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x8_ssm_eviction_uses_local_event_adapter_not_session_bus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSM eviction emits through its LocalEventAdapter without publishing on the session bus."""
    session_id = "m5x8"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        ssm = session.session_state

        event_port = ssm._event_port
        assert isinstance(event_port, LocalEventAdapter)
        assert event_port is not session.bus
        assert event_port is not _raw_bus(session.bus)

        seed = ssm.mutate(
            section="telemetry",
            operation="record_turn",
            data={"turn_number": 1, "duration_ms": 50, "token_count": 8},
            estimated_bytes=512,
            cognitive_trace_id="trace-m5-x8-seed",
        )
        assert seed.success

        ssm._size_tracker.set_section_size("telemetry", WARM_SIZE_LIMIT_BYTES)

        emitted_types: list[str] = []
        real_emit = event_port.emit

        def emit_spy(event_type: str, payload: Any) -> None:
            emitted_types.append(event_type)
            real_emit(event_type, payload)

        monkeypatch.setattr(event_port, "emit", emit_spy)

        bus_cls = type(session.bus)
        real_publish = bus_cls.publish
        published_topics: list[str] = []

        def publish_spy(self: Any, envelope: Any) -> None:
            if self is session.bus:
                published_topics.append(envelope.topic)
            real_publish(self, envelope)

        monkeypatch.setattr(bus_cls, "publish", publish_spy)

        ssm._trigger_eviction_if_needed(trace_id="trace-m5-x8")

        assert EventType.EVICTION_TRIGGERED.value in emitted_types
        assert EventType.EVICTION_COMPLETED.value in emitted_types
        assert not any(topic.startswith("sessionstate.eviction.") for topic in published_topics)
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x9_memory_writer_cold_archive_is_ssm_local_archive_identity(
    tmp_path: Path,
) -> None:
    """The MW read adapter keeps the exact LocalColdArchive object owned by SSM."""
    session_id = "m5x9"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        adapter = session.memory_writer._pipeline._session_reader._port

        assert isinstance(adapter, SessionReadAdapter)
        assert adapter._manager is session.session_state
        assert adapter._cold_archive is session.session_state.get_local_cold_archive()
        assert adapter._cold_archive is session.session_state._local_cold_archive
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x10_live_turn_publishes_full_turn_completed_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live FSM turn emits k1.session.turn.completed.v1 with the full payload."""
    session_id = "m5x10"
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
        session.bus.subscribe(TOPIC_TURN_COMPLETED, completed.append)

        user_text = "Please remember that Mira finished piano practice."
        user_env = build_user_input(payload={"text": user_text, "device_id": "device-m5-x10"})
        session.bus.publish(user_env)
        assert _raw_bus(session.bus).flush(timeout_ms=5_000)
        await asyncio.sleep(0)

        assert session.concierge.state == "DISPATCHING"
        assert delivered_to_front == [TOPIC_USER_INPUT]

        final_text = "Got it, Mira finished piano practice."
        final_env = replace(
            build_final_response(payload={"text": final_text}),
            cognitive_trace_id="trace-m5-x10",
            session_id=session_id,
        )
        session.bus.publish(final_env)
        assert _raw_bus(session.bus).flush(timeout_ms=5_000)
        await asyncio.sleep(0)

        payloads = [_decode_payload(envelope) for envelope in completed]
        assert len(payloads) == 1
        payload = payloads[0]
        emitted_session_id = session.concierge._ledger.session_id

        assert payload["turn_id"] == f"{emitted_session_id}:1"
        assert payload["session_id"] == emitted_session_id
        assert payload["cognitive_trace_id"] == "trace-m5-x10"
        assert payload["user_message"] == user_text
        assert payload["assistant_response"] == final_text
        assert isinstance(payload["timestamp_ms"], int)
        assert payload["timestamp_ms"] > 0
        assert payload["turn_number"] == 1
        assert session.concierge.state == "LISTENING"
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)
