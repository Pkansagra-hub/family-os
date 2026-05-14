"""M2-L10 live-kernel bridge_client PORT-IDENTITY probe.

Covers kernel sweep row M2-L10 (PORT-IDENTITY / I2.7.7):

    The bridge adapter is a Tier 1 (shared) component instantiated once at
    KernelService startup. ``svc._bridge.get_client()`` must return the same
    ``SinkBridgeClient`` instance regardless of which session asks for it and
    regardless of how many sessions exist.

Design rationale (I2.7.7)
--------------------------
``SinkBridgeAdapter`` is mounted at S4 (startup stage 4) before any session
is created. Sessions share the single outbox + client so that all enqueued
messages land in the same WAL and are drained by one DrainWorker.

Object graph asserted
----------------------
    svc._bridge                  → SinkBridgeAdapter      (Tier 1)
    svc._bridge.get_client()     → SinkBridgeClient       (Tier 1)
    repeated calls return same   → client_a is client_b   (singleton)
    two sessions, same client    → still same object identity

Test coverage
-------------
| # | Assertion | Tracing ref | Expected |
|---|-----------|-------------|---------|
| 1 | Repeated calls to ``get_client()`` return identical object | I2.7.7 | GREEN |
| 2 | Client identity is stable across two independent sessions | I2.7.7 | GREEN |
| 3 | Client identity is stable after session destroy + recreate | I2.7.7 | GREEN |
| 4 | In OFFLINE mode (Recipe A), ``get_client()`` is None for all sessions | I2.7.7 neg | GREEN |
| 5 | No asyncio task leaks | acceptance gate 3 | GREEN |
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bridge.client import SinkBridgeClient
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.adapters.bridge_adapter import OfflineBridgeAdapter, SinkBridgeAdapter
from k1.kernel.service import KernelService

pytestmark = pytest.mark.integration


# ── helpers ───────────────────────────────────────────────────────────────────


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path) -> KernelConfig:
    """Recipe A — bridge offline (bridge_enabled=False)."""
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
    """Recipe SINK — bridge_enabled=True, no k0_endpoint → SinkBridgeAdapter."""
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


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l10_get_client_returns_same_instance_on_repeated_calls(
    tmp_path: Path,
) -> None:
    """Repeated calls to get_client() return the identical SinkBridgeClient object."""
    cfg = _recipe_sink(tmp_path)
    svc = KernelService(cfg)
    await svc.startup()
    try:
        assert isinstance(svc._bridge, SinkBridgeAdapter)
        client_a = svc._bridge.get_client()
        client_b = svc._bridge.get_client()
        client_c = svc._bridge.get_client()
        assert isinstance(client_a, SinkBridgeClient)
        # Identity: all three calls return the exact same object
        assert client_a is client_b
        assert client_a is client_c
    finally:
        await svc.shutdown()


@pytest.mark.asyncio
async def test_m2_l10_bridge_client_shared_across_two_sessions(
    tmp_path: Path,
) -> None:
    """The bridge client is the same Tier 1 singleton regardless of active sessions."""
    cfg = _recipe_sink(tmp_path)
    svc = KernelService(cfg)
    await svc.startup()
    try:
        session_a = await svc.create_session("s-a")
        session_b = await svc.create_session("s-b")

        client_before_sessions = svc._bridge.get_client()
        client_after_s_a = svc._bridge.get_client()
        client_after_s_b = svc._bridge.get_client()

        # The bridge adapter is Tier 1 — sessions don't affect client identity
        assert client_before_sessions is client_after_s_a
        assert client_before_sessions is client_after_s_b
        assert isinstance(client_before_sessions, SinkBridgeClient)

        # Sanity: the two sessions themselves are distinct objects
        assert session_a is not session_b
    finally:
        await svc.shutdown()


@pytest.mark.asyncio
async def test_m2_l10_bridge_client_stable_across_session_destroy_and_recreate(
    tmp_path: Path,
) -> None:
    """Destroying a session and creating a new one must not change bridge client identity."""
    cfg = _recipe_sink(tmp_path)
    svc = KernelService(cfg)
    await svc.startup()
    try:
        client_initial = svc._bridge.get_client()

        session_x = await svc.create_session("s-x")
        client_after_create = svc._bridge.get_client()
        assert client_initial is client_after_create

        await svc.destroy_session("s-x")
        client_after_destroy = svc._bridge.get_client()
        assert client_initial is client_after_destroy

        session_y = await svc.create_session("s-y")
        client_after_recreate = svc._bridge.get_client()
        assert client_initial is client_after_recreate
        assert isinstance(client_initial, SinkBridgeClient)
    finally:
        await svc.shutdown()


@pytest.mark.asyncio
async def test_m2_l10_offline_mode_get_client_is_none_for_all_sessions(
    tmp_path: Path,
) -> None:
    """In OFFLINE/Recipe-A mode, get_client() is None — no sessions change that."""
    cfg = _recipe_a(tmp_path)
    svc = KernelService(cfg)
    await svc.startup()
    try:
        assert isinstance(svc._bridge, OfflineBridgeAdapter)
        assert svc._bridge.get_client() is None

        await svc.create_session("s-offline-1")
        await svc.create_session("s-offline-2")

        # Still None after sessions exist
        assert svc._bridge.get_client() is None
    finally:
        await svc.shutdown()


@pytest.mark.asyncio
async def test_m2_l10_no_task_leaks(tmp_path: Path) -> None:
    """Bridge client identity probe leaves zero orphaned asyncio tasks."""
    tasks_before = _active_task_snapshot()

    cfg = _recipe_sink(tmp_path)
    svc = KernelService(cfg)
    await svc.startup()
    await svc.create_session("s-leak-check")
    _ = svc._bridge.get_client()
    await svc.shutdown()

    tasks_after = _active_task_snapshot()
    leaked = tasks_after - tasks_before
    assert not leaked, f"Leaked tasks: {leaked}"
