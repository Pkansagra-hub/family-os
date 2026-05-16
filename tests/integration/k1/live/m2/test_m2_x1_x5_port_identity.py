"""M2-X1..M2-X5 live-kernel cross-component PORT-IDENTITY probes.

Covers the cross-component M2-X rows added to the kernel sweep tracker:

* M2-X1: per-session BridgeAwareLocalBus is the bus held by ConciergeRuntime.
* M2-X2: per-session Fabric is separate from shared Fabric but reuses registry.
* M2-X3: one SessionRoutingStateReader is shared by Fabric/Orchestrator/Planner.
* M2-X4: one ModelHub singleton is used by Fabric, Concierge, Planner, and MW.
* M2-X5: SINK bridge get_client() returns one stable SinkBridgeClient singleton.

These are live KernelService probes. They assert real object identity and do not
replace assertion subjects with mocks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from bridge.bus_guard import BridgeAwareLocalBus
from bridge.client import SinkBridgeClient
from k1.concierge.config.kernel import KernelConfig
from k1.fabric.adapters.model_gateway_bridge import ModelGatewayBridgeAdapter
from k1.kernel.adapters.bridge_adapter import SinkBridgeAdapter
from k1.kernel.adapters.model_hub_llm_bus import ModelHubRequestBus
from k1.kernel.adapters.session_routing_reader import SessionRoutingStateReader
from k1.kernel.service import KernelService
from k1.memory_writer.adapters.model_hub_adapter import ModelHubAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.planner.adapters.llm_gateway_adapter import LLMGatewayAdapter
from k1.planner.adapters.session_state_adapter import SessionStateReadAdapter

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


def _recipe_sink(tmp_path: Path) -> KernelConfig:
    return KernelConfig(
        test_mode=True,
        model_mode="test",
        ordered_bus=True,
        session_mode="standalone",
        bridge_enabled=True,
        bridge_offline_ok=True,
        k0_endpoint="",
        otel_enabled=False,
        enable_hitl=False,
        enable_hil_service=False,
        enable_self_model=False,
        enable_family_tools=False,
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "workflows.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


def _fabric_state_reader(fabric: Any) -> Any:
    return fabric.facade._context_builder._state_reader


def _fabric_model_gateway(fabric: Any) -> Any:
    return fabric.facade._provider_factory._port_deps["model_gateway_port"]


def _planner_state_adapter(svc: KernelService) -> Any:
    return svc._planner._pipeline._sketch._tool_router._state_read


def _planner_llm_adapter(svc: KernelService) -> Any:
    return svc._planner._pipeline._sketch._llm_port


def _memory_writer_model_adapter(session: Any) -> Any:
    return session.memory_writer._pipeline._writer_agent._model_hub


async def _assert_no_leaks(
    tmp_path: Path,
    baseline_tasks: set[asyncio.Task[object]],
    *,
    check_sqlite_sidecars: bool = True,
) -> None:
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert not leaked, f"Leaked tasks: {[task.get_name() for task in leaked]}"

    if not check_sqlite_sidecars:
        return

    for db_name in ("workflows.db", "bridge.db"):
        for suffix in ("-wal", "-shm"):
            sidecar = tmp_path / f"{db_name}{suffix}"
            assert not sidecar.exists(), f"SQLite sidecar not cleaned up: {sidecar}"


@pytest.mark.asyncio
async def test_m2_x1_concierge_holds_the_live_per_session_bus(tmp_path: Path) -> None:
    """M2-X1: ConciergeRuntime holds the same BridgeAwareLocalBus as SessionInstance."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        await svc.create_session("m2x1-a")
        await svc.create_session("m2x1-b")

        session_a = svc._sessions["m2x1-a"]
        session_b = svc._sessions["m2x1-b"]

        assert isinstance(session_a.bus, BridgeAwareLocalBus)
        assert isinstance(session_b.bus, BridgeAwareLocalBus)
        assert session_a.bus is not session_b.bus
        assert session_a.bus.inner is not session_b.bus.inner

        assert session_a.concierge._bus is session_a.bus
        assert session_a.concierge._router is session_a.router
        assert session_a.concierge._front_mailbox is session_a.front_mailbox
        assert session_a.concierge._back_mailbox is session_a.back_mailbox

        assert not hasattr(session_a.front_mailbox, "_bus")
        assert not hasattr(session_a.back_mailbox, "_bus")
        assert not hasattr(session_a.router, "_bus")
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_leaks(tmp_path, baseline_tasks)


@pytest.mark.asyncio
async def test_m2_x2_session_fabric_is_distinct_but_reuses_shared_registry(
    tmp_path: Path,
) -> None:
    """M2-X2: session Fabric instances are isolated shells over one registry."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        await svc.create_session("m2x2-a")
        await svc.create_session("m2x2-b")

        shared_fabric = svc._shared_fabric
        session_fabric_a = svc._sessions["m2x2-a"].fabric
        session_fabric_b = svc._sessions["m2x2-b"].fabric

        assert session_fabric_a is not shared_fabric
        assert session_fabric_b is not shared_fabric
        assert session_fabric_a is not session_fabric_b

        assert session_fabric_a.registry is shared_fabric.registry
        assert session_fabric_b.registry is shared_fabric.registry
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_leaks(tmp_path, baseline_tasks)


@pytest.mark.asyncio
async def test_m2_x3_session_routing_reader_is_shared_by_tier1_callers(
    tmp_path: Path,
) -> None:
    """M2-X3: Fabric, Orchestrator, and Planner share one routing reader."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()

        routing_reader = svc._session_routing_reader
        assert isinstance(routing_reader, SessionRoutingStateReader)

        assert _fabric_state_reader(svc._shared_fabric) is routing_reader

        orchestrator_state_port = svc._orchestrator._state_port
        assert isinstance(orchestrator_state_port, StateReadAdapter)
        assert orchestrator_state_port._reader is routing_reader

        planner_state_port = _planner_state_adapter(svc)
        assert isinstance(planner_state_port, SessionStateReadAdapter)
        assert planner_state_port._reader is routing_reader
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_leaks(tmp_path, baseline_tasks)


@pytest.mark.asyncio
async def test_m2_x4_model_hub_singleton_reaches_all_live_consumers(
    tmp_path: Path,
) -> None:
    """M2-X4: Fabric, Concierge, Planner, and MemoryWriter share one ModelHub."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        await svc.create_session("m2x4")
        session = svc._sessions["m2x4"]

        model_hub = svc._model_hub
        assert model_hub is not None

        shared_gateway = _fabric_model_gateway(svc._shared_fabric)
        session_gateway = _fabric_model_gateway(session.fabric)
        assert isinstance(shared_gateway, ModelGatewayBridgeAdapter)
        assert isinstance(session_gateway, ModelGatewayBridgeAdapter)
        assert shared_gateway._hub is model_hub
        assert session_gateway._hub is model_hub

        assert session.concierge._model is model_hub

        planner_llm = _planner_llm_adapter(svc)
        assert isinstance(planner_llm, LLMGatewayAdapter)
        assert isinstance(planner_llm._bus, ModelHubRequestBus)
        assert planner_llm._bus._hub is model_hub

        mw_model_hub = _memory_writer_model_adapter(session)
        assert isinstance(mw_model_hub, ModelHubAdapter)
        assert mw_model_hub._hub is model_hub
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_leaks(tmp_path, baseline_tasks)


@pytest.mark.asyncio
async def test_m2_x5_sink_bridge_client_is_shared_across_sessions(tmp_path: Path) -> None:
    """M2-X5: SINK mode exposes one stable bridge client singleton."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_sink(tmp_path))

    try:
        await svc.startup()
        assert isinstance(svc._bridge, SinkBridgeAdapter)

        client_before = svc._bridge.get_client()
        await svc.create_session("m2x5-a")
        await svc.create_session("m2x5-b")
        client_after = svc._bridge.get_client()

        assert isinstance(client_before, SinkBridgeClient)
        assert client_before is client_after
        assert client_before is svc._bridge.get_client()
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_leaks(tmp_path, baseline_tasks, check_sqlite_sidecars=False)
