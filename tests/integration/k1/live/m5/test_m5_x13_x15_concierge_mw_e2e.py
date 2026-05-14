"""M5-X13..M5-X15 live-kernel Concierge -> MemoryWriter probes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from k1.concierge.bus.builders import (
    build_final_response,
    build_turn_completed,
    build_user_input,
)
from k1.concierge.bus.topics import TOPIC_TURN_COMPLETED, TOPIC_USER_INPUT
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.memory_writer.adapters.test_adapters import (
    FakeBridgeCommandPort,
    FakeModelHubPort,
)
from k1.memory_writer.context.session_reader import MWSessionReader
from k1.memory_writer.pipeline.pipeline import PipelineResult

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


async def _drive_live_completed_turn(
    session: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    user_text: str,
    final_text: str,
    trace_id: str,
    device_id: str,
) -> dict[str, Any]:
    delivered_to_front: list[str] = []

    def hold_front_delivery(envelope: Any) -> None:
        delivered_to_front.append(envelope.topic)

    monkeypatch.setattr(session.concierge._fsm, "_deliver_to_front", hold_front_delivery)

    completed: list[Any] = []
    completed_handle = session.bus.subscribe(TOPIC_TURN_COMPLETED, completed.append)
    try:
        session.bus.publish(build_user_input(payload={"text": user_text, "device_id": device_id}))
        await _flush_bus_tasks(session.bus)

        assert session.concierge.state == "DISPATCHING"
        assert delivered_to_front == [TOPIC_USER_INPUT]

        final_env = replace(
            build_final_response(payload={"text": final_text}),
            cognitive_trace_id=trace_id,
            session_id=session.session_id,
        )
        session.bus.publish(final_env)
        await _flush_bus_tasks(session.bus)

        assert session.concierge.state == "LISTENING"
        await _wait_until(lambda: len(completed) == 1, "turn.completed was not published")
        return _decode_payload(completed[0])
    finally:
        session.bus.unsubscribe(completed_handle)


def _turn_completed_payload(
    *,
    turn_id: str,
    session_id: str,
    trace_id: str,
    turn_number: int = 1,
) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "session_id": session_id,
        "cognitive_trace_id": trace_id,
        "user_message": "Mira finished piano practice before dinner.",
        "assistant_response": "I will remember Mira finished piano practice.",
        "timestamp_ms": 1_700_000_000_000 + turn_number,
        "turn_number": turn_number,
    }


def _valid_extraction_json() -> str:
    return json.dumps(
        [
            {
                "text": "Mira finished piano practice before dinner.",
                "participants": ["Mira"],
                "topics": ["music", "practice"],
                "categories": ["family_event"],
                "activity_type": "HOBBY",
                "location_name": None,
                "location_type": None,
                "sentiment_label": "positive",
                "emotion_tags": ["proud"],
                "affect": {"valence": 0.6, "arousal": 0.4, "dominance": 0.6},
                "novelty": "EXPECTED",
                "elaboration_depth": "MENTION",
                "temporal_orientation": "PAST",
                "source_type": "user_stated",
                "intent_type": "log_memory",
                "social_context": "nuclear_family",
                "social_intimacy": "HIGH",
                "identity_domains": ["parent"],
                "confidence": 0.91,
                "temporal_links": [],
                "correction_signal": False,
                "contradiction_signal": False,
                "supersedes_concept": None,
                "correction_source": None,
                "narrative": None,
            }
        ]
    )


@pytest.mark.asyncio
async def test_m5_x13_live_turn_is_in_history_active_when_mw_reads_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live Concierge turn is published, then MW reads it back from SSM history_active."""
    session_id = "m5x13"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        reader = session.memory_writer._pipeline._session_reader
        original_read_snapshot_enriched = MWSessionReader.read_snapshot_enriched
        snapshots: list[dict[str, Any]] = []

        async def read_snapshot_enriched_spy(
            self: MWSessionReader,
            session_id_arg: str,
            history_limit: int | None = None,
        ) -> dict[str, Any]:
            snapshot = await original_read_snapshot_enriched(
                self,
                session_id_arg,
                history_limit=history_limit,
            )
            if self is reader:
                snapshots.append(snapshot)
            return snapshot

        monkeypatch.setattr(
            MWSessionReader,
            "read_snapshot_enriched",
            read_snapshot_enriched_spy,
        )

        user_text = "Please remember that Mira finished piano practice before dinner."
        final_text = "Got it, Mira finished piano practice before dinner."
        completed_payload = await _drive_live_completed_turn(
            session,
            monkeypatch,
            user_text=user_text,
            final_text=final_text,
            trace_id="trace-m5-x13",
            device_id="device-m5-x13",
        )

        await _wait_until(
            lambda: session.memory_writer._dispatcher.buffered_count == 1,
            "MW did not buffer the completed turn",
        )
        await session.memory_writer.stop()

        assert completed_payload["user_message"] == user_text
        assert completed_payload["assistant_response"] == final_text
        assert completed_payload["cognitive_trace_id"] == "trace-m5-x13"
        assert snapshots, "MW did not read a session snapshot during batch flush"

        history = snapshots[-1].get("history_active")
        assert isinstance(history, dict)
        turns = history.get("turns", [])
        assert any(
            turn.get("user_message") == user_text and turn.get("assistant_response") == final_text
            for turn in turns
            if isinstance(turn, dict)
        )
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x14_duplicate_turn_id_is_deduped_before_session_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate turn.completed events on the live bus produce one process_session call."""
    session_id = "m5x14"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        pipeline = session.memory_writer._pipeline
        process_calls: list[list[Any]] = []

        async def process_session_spy(turns: list[Any]) -> PipelineResult:
            process_calls.append(list(turns))
            return PipelineResult(
                atoms_extracted=len(turns),
                envelopes_submitted=0,
                trace_id=turns[-1].cognitive_trace_id if turns else "",
            )

        monkeypatch.setattr(pipeline, "process_session", process_session_spy)

        turn_id = "m5x14-ledger:1"
        payload = _turn_completed_payload(
            turn_id=turn_id,
            session_id="m5x14-ledger",
            trace_id="trace-m5-x14",
        )
        session.bus.publish(build_turn_completed(payload=payload))
        session.bus.publish(build_turn_completed(payload=payload))
        await _flush_bus_tasks(session.bus)

        await _wait_until(
            lambda: list(session.memory_writer._dispatcher._processed_ids) == [turn_id],
            "MW dispatcher did not record exactly one processed turn id",
        )
        assert session.memory_writer._dispatcher.buffered_count == 1

        await session.memory_writer.stop()

        assert len(process_calls) == 1
        assert len(process_calls[0]) == 1
        assert process_calls[0][0].turn_id == turn_id
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x15_complete_turn_submits_memory_delta_with_trace_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live completed turn reaches IBridgeCommandPort.submit_batch as memory.delta."""
    session_id = "m5x15"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        model = FakeModelHubPort(response_content=_valid_extraction_json())
        bridge = FakeBridgeCommandPort()
        session.memory_writer._pipeline._writer_agent._model_hub = model
        session.memory_writer._pipeline._emitter._bridge_port = bridge

        trace_id = "trace-m5-x15"
        completed_payload = await _drive_live_completed_turn(
            session,
            monkeypatch,
            user_text="Please remember that Mira finished piano practice before dinner.",
            final_text="Got it, Mira finished piano practice before dinner.",
            trace_id=trace_id,
            device_id="device-m5-x15",
        )

        await _wait_until(
            lambda: session.memory_writer._dispatcher.buffered_count == 1,
            "MW did not buffer the completed turn for bridge submission",
        )
        await session.memory_writer.stop()

        assert completed_payload["cognitive_trace_id"] == trace_id
        assert model.calls, "MW did not call the model edge for session extraction"
        assert len(bridge.batches) == 1

        batch = bridge.batches[0]
        assert batch
        assert {envelope["topic"] for envelope in batch} == {"memory.delta"}
        assert all(envelope["schema_uri"] == "schema://memory.delta" for envelope in batch)
        assert all(envelope["trace_id"] == trace_id for envelope in batch)
        assert all(envelope["headers"]["cognitive_trace_id"] == trace_id for envelope in batch)
        assert all(envelope["body"]["cognitive_trace_id"] == trace_id for envelope in batch)
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)
