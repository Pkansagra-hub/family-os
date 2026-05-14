"""M5-L1..M5-L6 live-kernel Bus + SessionState + MemoryWriter probes."""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from k1.bus.envelope import Envelope
from k1.concierge.bus.builders import build_turn_completed
from k1.concierge.bus.topics import TOPIC_TURN_COMPLETED
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.memory_writer.events import TOPIC_TURN_COMPLETE as MW_TOPIC_TURN_COMPLETE
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.pipeline.session_batch_dispatcher import SessionBatchDispatcher
from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher
from k1.memory_writer.place_resolver import GEOHASH_SENTINEL
from k1.sessionstate.ports.writer import MutationRequest
from k1.sessionstate.sections.beliefs_active import BeliefsActiveSection

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


def _turn_payload(session_id: str, *, turn_id: str = "turn-1") -> TurnCompletePayload:
    return TurnCompletePayload(
        turn_id=f"{session_id}:{turn_id}",
        session_id=session_id,
        cognitive_trace_id=f"trace-{turn_id}",
        user_message="We had dinner at Olive Garden.",
        assistant_response="Noted.",
        timestamp_ms=1_700_000_000_000,
        turn_number=1,
        mentioned_location_raw="Olive Garden",
        mentioned_location_type="restaurant",
        mentioned_location_entity_id="loc-olive-garden",
        mentioned_location_confidence=0.96,
    )


@pytest.mark.asyncio
async def test_m5_l1_concierge_turn_completed_topic_matches_live_mw_subscription(
    tmp_path: Path,
) -> None:
    """MW01 killer test: publisher topic, MW constants, and live subscription agree."""
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session("m5l1")
        session = svc._sessions["m5l1"]
        dispatcher = session.memory_writer._dispatcher

        assert isinstance(dispatcher, SessionBatchDispatcher)
        assert TOPIC_TURN_COMPLETED == "k1.session.turn.completed.v1"
        assert MW_TOPIC_TURN_COMPLETE == TOPIC_TURN_COMPLETED
        assert TurnDispatcher.TOPIC == TOPIC_TURN_COMPLETED
        assert dispatcher.TOPIC == TOPIC_TURN_COMPLETED
        assert dispatcher._subscription is not None
        assert dispatcher._subscription.topic == TOPIC_TURN_COMPLETED

        envelope = build_turn_completed(
            payload={
                "turn_id": "m5l1:1",
                "session_id": "m5l1",
                "cognitive_trace_id": "trace-m5-l1",
                "user_message": "hello",
                "assistant_response": "world",
                "timestamp_ms": 1,
                "turn_number": 1,
            }
        )
        assert envelope.topic == dispatcher.TOPIC

        subscriptions = session.bus.list_subscriptions()
        topic_subscriptions = [item for item in subscriptions if item[0] == TOPIC_TURN_COMPLETED]
        assert len(topic_subscriptions) == 1

        await session.memory_writer.stop()
        assert TOPIC_TURN_COMPLETED not in {topic for topic, _ in session.bus.list_subscriptions()}
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_task_leaks(baseline_tasks)


@pytest.mark.asyncio
async def test_m5_l2_session_bus_drops_expired_ttl_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ttl=100ms envelope is not delivered when dispatch observes age >= 200ms."""
    import k1.bus.impl.local_bus as local_bus_module

    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session("m5l2")
        session = svc._sessions["m5l2"]
        delivered: list[Envelope] = []
        session.bus.subscribe("k1.test.m5.ttl.v1", delivered.append)
        ttl_drops_before = session.bus.stats.ttl_drops

        base_ns = 5_000_000_000_000

        def fake_monotonic_ns() -> int:
            fake_monotonic_ns.calls += 1
            if fake_monotonic_ns.calls == 1:
                return base_ns
            return base_ns + 200_000_000

        fake_monotonic_ns.calls = 0  # type: ignore[attr-defined]

        with monkeypatch.context() as patch:
            patch.setattr(local_bus_module.time, "monotonic_ns", fake_monotonic_ns)
            session.bus.publish(
                Envelope(
                    topic="k1.test.m5.ttl.v1",
                    payload=b"late",
                    ttl_ms=100,
                )
            )

        assert delivered == []
        assert session.bus.stats.ttl_drops == ttl_drops_before + 1
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_task_leaks(baseline_tasks)


@pytest.mark.asyncio
async def test_m5_l3_memory_writer_stop_completes_before_ssm_stop_begins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """destroy_session awaits MW.stop fully before invoking SessionState.stop."""
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()
    order: list[str] = []

    try:
        await svc.startup()
        await svc.create_session("m5l3")
        session = svc._sessions["m5l3"]
        memory_writer = session.memory_writer
        session_state = session.session_state

        original_mw_stop = type(memory_writer).stop
        original_ssm_stop = type(session_state).stop

        async def mw_stop_spy(self: Any) -> Any:
            if self is memory_writer:
                order.append("mw_stop_begin")
            result = await original_mw_stop(self)
            if self is memory_writer:
                order.append("mw_stop_end")
            return result

        def ssm_stop_spy(self: Any, *args: Any, **kwargs: Any) -> Any:
            if self is session_state:
                order.append("ssm_stop_begin")
            result = original_ssm_stop(self, *args, **kwargs)
            if self is session_state:
                order.append("ssm_stop_end")
            return result

        monkeypatch.setattr(type(memory_writer), "stop", mw_stop_spy)
        monkeypatch.setattr(type(session_state), "stop", ssm_stop_spy)

        await svc.destroy_session("m5l3")

        assert order == ["mw_stop_begin", "mw_stop_end", "ssm_stop_begin", "ssm_stop_end"]
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_task_leaks(baseline_tasks)


@pytest.mark.asyncio
async def test_m5_l4_live_mw_place_resolver_uses_sessionstate_location_entities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live MW pipeline refreshes PlaceResolver from SSM beliefs_active entities."""
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()
    contexts: list[Any] = []

    try:
        await svc.startup()
        await svc.create_session("m5l4")
        session = svc._sessions["m5l4"]
        beliefs = session.session_state.get_section("beliefs_active")
        beliefs.add_entity(
            entity_id="loc-olive-garden",
            entity_type="LOCATION",
            display_name="Olive Garden",
            confidence=0.96,
        )

        pipeline = session.memory_writer._pipeline
        writer_agent = pipeline._writer_agent
        original_extract_session = type(writer_agent).extract_session

        async def extract_session_spy(
            self: Any,
            turns: list[TurnCompletePayload],
            context: Any,
            trace_id: str,
        ) -> list[Any]:
            if self is writer_agent:
                contexts.append(context)
                return []
            return await original_extract_session(self, turns, context, trace_id)

        monkeypatch.setattr(type(writer_agent), "extract_session", extract_session_spy)

        result = await pipeline.process_session([_turn_payload("m5l4", turn_id="l4")])

        assert result.trace_id == "trace-l4"
        assert contexts
        assert contexts[0].place_id == "place_olive_garden"
        assert pipeline._place_resolver.resolve("Olive Garden") == "place_olive_garden"
        place_id, geohash = pipeline._place_resolver.resolve_with_geohash(
            "Olive Garden",
            {"Olive Garden": "c23nb6"},
        )
        assert place_id == "place_olive_garden"
        assert geohash == "c23nb6"
        assert geohash != GEOHASH_SENTINEL
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_task_leaks(baseline_tasks)


@pytest.mark.asyncio
async def test_m5_l5_session_bus_publish_isolated_between_sessions(tmp_path: Path) -> None:
    """A subscriber on session B never sees envelopes published on session A's bus."""
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session("m5l5-a")
        await svc.create_session("m5l5-b")
        session_a = svc._sessions["m5l5-a"]
        session_b = svc._sessions["m5l5-b"]

        seen_a: list[Envelope] = []
        seen_b: list[Envelope] = []
        session_a.bus.subscribe("k1.test.m5.isolation.v1", seen_a.append)
        session_b.bus.subscribe("k1.test.m5.isolation.v1", seen_b.append)

        session_a.bus.publish(
            Envelope(
                topic="k1.test.m5.isolation.v1",
                payload=b"session-a-only",
                session_id="m5l5-a",
            )
        )

        assert len(seen_a) == 1
        assert seen_a[0].session_id == "m5l5-a"
        assert seen_b == []
        assert session_a.bus is not session_b.bus
        assert session_a.bus.inner is not session_b.bus.inner
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_task_leaks(baseline_tasks)


@pytest.mark.asyncio
async def test_m5_l6_destroy_session_flushes_pending_ss_writes_to_sqlite(
    tmp_path: Path,
) -> None:
    """Pending SSM mutations are checkpointed into SQLite during session destroy."""
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()
    db_path = tmp_path / "ssm.db"

    try:
        await svc.startup()
        await svc.create_session("m5l6")
        session = svc._sessions["m5l6"]
        writer = session.session_state._writer_port

        response = writer.request_mutation(
            MutationRequest.create(
                section="beliefs_active",
                operation="add_fact",
                data={
                    "subject": "user",
                    "predicate": "likes",
                    "obj": "green tea",
                    "confidence": 0.91,
                    "source": "m5-l6-live-probe",
                },
                writer_id="direct",
                cognitive_trace_id="trace-m5-l6",
                estimated_bytes=128,
            )
        )
        assert response.approved
        assert session.session_state.pending_writes() > 0

        await svc.destroy_session("m5l6")

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT data
                FROM st_session_checkpoints
                WHERE session_id = ?
                ORDER BY created_at_ms DESC
                LIMIT 1
                """,
                ("m5l6",),
            ).fetchone()
        assert row is not None

        checkpoint = json.loads(row[0].decode("utf-8"))
        encoded_beliefs = checkpoint["section_data"]["beliefs_active"]
        section = BeliefsActiveSection(session_id="m5l6")
        section.from_flatbuffer(base64.b64decode(encoded_beliefs))
        assert any(fact.object == "green tea" for fact in section.list_facts())
        assert "m5l6" not in svc._sessions
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_task_leaks(baseline_tasks)
