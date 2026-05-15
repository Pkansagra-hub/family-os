"""M1-L1/M1-L2 live-kernel Concierge wiring probes."""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from bridge.bus_guard import BridgeAwareLocalBus
from k1.concierge.adapters.bus_input import BusInputAdapter
from k1.concierge.adapters.bus_output import BusOutputAdapter
from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.concierge.adapters.ssm_state import SSMStateAdapter
from k1.concierge.bus.topics import (
    FRONT_SUBSCRIPTIONS,
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_CONCIERGE_CONFIG_UPDATE,
    TOPIC_DAG_COMPLETED,
    TOPIC_FINAL_RESPONSE,
    TOPIC_FINDINGS_READY,
    TOPIC_HIL_REQUEST,
    TOPIC_PROACTIVE_FILL,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_UI_TYPING,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
)
from k1.concierge.config.kernel import KernelConfig
from k1.concierge.tools.dispatcher import ToolDispatcher
from k1.kernel.service import KernelService

pytestmark = pytest.mark.integration


EXPECTED_FSM_TOPICS: frozenset[str] = frozenset(
    {
        TOPIC_USER_INPUT,
        TOPIC_FINAL_RESPONSE,
        TOPIC_TASK_DISPATCH,
        TOPIC_DAG_COMPLETED,
        TOPIC_TASK_COMPLETE,
        TOPIC_TASK_FAILED,
        TOPIC_TASK_CANCEL,
        TOPIC_TASK_SUSPENDED,
        TOPIC_TASK_RESUME,
        TOPIC_HIL_REQUEST,
        TOPIC_FINDINGS_READY,
        TOPIC_ARTIFACT_CREATED,
        TOPIC_AFFECT_UPDATE,
        TOPIC_PROACTIVE_FILL,
        TOPIC_TOOL_STARTED,
        TOPIC_TOOL_COMPLETED,
        TOPIC_WEAVE_BATCH,
        TOPIC_UI_TYPING,
        TOPIC_CONCIERGE_CONFIG_UPDATE,
    }
)


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
    baseline_tasks: set[asyncio.Task[object]],
) -> None:
    if svc.is_running:
        await svc.shutdown()
    await _assert_no_task_leaks(baseline_tasks)


def _subscription_topic_counts(bus: Any) -> Counter[str]:
    return Counter(topic for topic, _handler in bus.list_subscriptions())


def _assert_concierge_ports_for_session(svc: KernelService, session: Any) -> None:
    concierge = session.concierge

    assert isinstance(session.bus, BridgeAwareLocalBus)
    assert concierge._bus is session.bus
    assert concierge._router is session.router
    assert concierge._front_mailbox is session.front_mailbox
    assert concierge._back_mailbox is session.back_mailbox

    assert isinstance(concierge._input_port, BusInputAdapter)
    assert concierge._input_port._bus is session.bus
    assert concierge._input_port._handle.pattern == TOPIC_USER_INPUT

    assert isinstance(concierge._output_port, BusOutputAdapter)
    assert concierge._output_port._bus is session.bus

    assert isinstance(concierge._state_port, SSMStateAdapter)
    assert concierge._state_port is concierge._session_state
    assert concierge._state_port._ss is session.session_state
    assert concierge._fsm._ss is concierge._state_port
    assert session.front_ctx.session_manager is concierge._state_port
    assert session.back_ctx.session_manager is concierge._state_port

    assert concierge._llm_port is svc._model_hub
    assert concierge._llm_port is concierge._model

    assert isinstance(concierge._dispatch_port, FabricDispatchAdapter)
    assert concierge._dispatch_port._bus is session.bus
    assert concierge._dispatch_port._fabric is session.fabric
    assert concierge._dispatch_port._orchestrator is svc._orchestrator
    assert session.front_ctx.dispatch is concierge._dispatch_port
    assert session.back_ctx.dispatch is concierge._dispatch_port

    assert isinstance(session.front_dispatcher, ToolDispatcher)
    assert isinstance(session.back_dispatcher, ToolDispatcher)
    assert session.front_dispatcher is concierge.front_dispatcher
    assert session.back_dispatcher is concierge.back_dispatcher
    assert session.front_dispatcher.ctx is session.front_ctx
    assert session.back_dispatcher.ctx is session.back_ctx

    fsm_dispatch_adapter = concierge._orchestrator
    assert fsm_dispatch_adapter is not None
    assert fsm_dispatch_adapter._dispatch is concierge._dispatch_port


@pytest.mark.asyncio
async def test_m1_l1_concierge_runtime_preserves_live_port_identity(
    tmp_path: Path,
) -> None:
    """M1-L1: Concierge holds the live per-session bus/SSM ports and shared ModelHub."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        await svc.create_session("m1l1-a")
        await svc.create_session("m1l1-b")

        session_a = svc._sessions["m1l1-a"]
        session_b = svc._sessions["m1l1-b"]

        assert session_a.bus is not session_b.bus
        assert session_a.bus.inner is not session_b.bus.inner
        assert session_a.session_state is not session_b.session_state
        assert session_a.fabric is not session_b.fabric

        _assert_concierge_ports_for_session(svc, session_a)
        _assert_concierge_ports_for_session(svc, session_b)
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m1_l2_fsm_subscribes_exact_contract_topic_set(
    tmp_path: Path,
) -> None:
    """M1-L2: the live FSM subscribes exactly the controller-owned topic set."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        await svc.create_session("m1l2")
        session = svc._sessions["m1l2"]
        concierge = session.concierge

        fsm_handles = concierge._fsm._subscription_handles
        fsm_topics = {handle.pattern for handle in fsm_handles}

        assert len(fsm_handles) == len(EXPECTED_FSM_TOPICS)
        assert fsm_topics == EXPECTED_FSM_TOPICS

        topic_counts = _subscription_topic_counts(session.bus)
        for topic in EXPECTED_FSM_TOPICS:
            assert topic_counts[topic] >= 1

        assert {handle.pattern for handle in concierge._front_subscriptions} == set(
            FRONT_SUBSCRIPTIONS
        )
        assert EXPECTED_FSM_TOPICS.isdisjoint(FRONT_SUBSCRIPTIONS)
        assert topic_counts[TOPIC_USER_INPUT] == 2
    finally:
        await _cleanup_service(svc, baseline_tasks)
