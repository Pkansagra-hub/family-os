"""M5-X1..M5-X5 live-kernel subscription and SessionState identity probes."""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from k1.concierge.adapters.ssm_state import SSMStateAdapter
from k1.concierge.bus.topics import (
    FRONT_SUBSCRIPTIONS,
    TOPIC_TURN_COMPLETED,
    TOPIC_USER_INPUT,
)
from k1.concierge.config.kernel import KernelConfig
from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_REGISTERED,
    TOPIC_CAPABILITY_UNREGISTERED,
    TOPIC_MCP_TOOL_DISCOVERED,
    TOPIC_VERSION_CONFLICT,
)
from k1.kernel.service import KernelService
from k1.memory_writer.adapters.session_read_adapter import SessionReadAdapter
from k1.memory_writer.context.session_reader import MWSessionReader
from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter

pytestmark = pytest.mark.integration


FABRIC_GAP_TOPICS = {
    TOPIC_CAPABILITY_REGISTERED,
    TOPIC_CAPABILITY_UNREGISTERED,
    TOPIC_VERSION_CONFLICT,
    TOPIC_MCP_TOOL_DISCOVERED,
}


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


def _subscription_topic_counts(bus: Any) -> Counter[str]:
    return Counter(topic for topic, _handler in bus.list_subscriptions())


def _bus_subscription_ids(bus: Any) -> set[str]:
    return set(_raw_bus(bus)._sub_patterns.keys())


def _component_subscription_ids(session: Any) -> set[str]:
    concierge = session.concierge
    ids = {handle.subscription_id for handle in concierge._fsm._subscription_handles}
    ids.update(handle.subscription_id for handle in concierge._front_subscriptions)
    ids.add(concierge._input_port._handle.subscription_id)
    ids.add(session.memory_writer._dispatcher._subscription.subscription_id)
    ids.update(
        handle.subscription_id for handle in session.fabric.event_port._subscriptions.values()
    )
    return ids


@pytest.mark.asyncio
async def test_m5_x1_live_session_bus_has_expected_owned_subscription_topology(
    tmp_path: Path,
) -> None:
    """After P1..P6, every live subscription is owned by the component that created it."""
    session_id = "m5x1"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        topic_counts = _subscription_topic_counts(session.bus)

        assert sum(topic_counts.values()) == 28
        assert topic_counts[TOPIC_USER_INPUT] == 2
        assert topic_counts[TOPIC_TURN_COMPLETED] == 1
        for topic in FRONT_SUBSCRIPTIONS:
            assert topic_counts[topic] == 1
        for topic in FABRIC_GAP_TOPICS:
            assert topic_counts[topic] == 1

        assert _bus_subscription_ids(session.bus) == _component_subscription_ids(session)
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x2_destroy_session_removes_all_bus_subscriptions(
    tmp_path: Path,
) -> None:
    """After destroy_session, the bus retains no subscription handlers or handles."""
    session_id = "m5x2"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        bus = session.bus

        assert sum(_subscription_topic_counts(bus).values()) == 28

        await svc.destroy_session(session_id)

        assert session_id not in svc._sessions
        assert bus.list_subscriptions() == []
        assert bus.subscription_count == 0
        assert _raw_bus(bus)._sub_patterns == {}
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x4_concierge_state_ports_use_session_ssm_identity(
    tmp_path: Path,
) -> None:
    """Concierge read/write state adapters point at the live session SSM."""
    session_id = "m5x4"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        state_port = session.concierge._session_state
        assert isinstance(state_port, SSMStateAdapter)
        assert state_port._ss is session.session_state
        assert session.concierge._fsm._ss is state_port
        assert session.front_ctx.session_manager is state_port
        assert session.back_ctx.session_manager is state_port

        writer_port = session.front_ctx.writer_port
        assert writer_port is session.back_ctx.writer_port
        assert writer_port is session.session_state._writer_port
        assert isinstance(writer_port, DirectWriterAdapter)
        assert writer_port._manager is session.session_state
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m5_x5_memory_writer_session_read_port_uses_session_ssm_identity(
    tmp_path: Path,
) -> None:
    """MemoryWriter session reader reaches the same live session SSM as the kernel container."""
    session_id = "m5x5"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        session_reader = session.memory_writer._pipeline._session_reader
        assert isinstance(session_reader, MWSessionReader)
        adapter = session_reader._port
        assert isinstance(adapter, SessionReadAdapter)
        assert adapter._manager is session.session_state
        assert adapter._cold_archive is session.session_state.get_local_cold_archive()
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)
