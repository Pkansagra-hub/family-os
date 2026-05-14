"""M2-L1 live-kernel lifecycle probe.

Covers kernel sweep row M2-L1:
startup S1->S7 and shutdown S7->S1 on a real KernelService using
Recipe A hermetic configuration.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService

pytestmark = pytest.mark.integration


STARTUP_PHASES = [
    "S1_complete",
    "S2_complete",
    "S2.5_skipped",
    "S2.6_skipped",
    "S4_complete",
    "S3_complete",
    "S5_complete",
    "S6_complete",
    "S6b_complete",
    "S7_complete",
    "S8_skipped",
    "startup_complete",
]

SHUTDOWN_PHASES = [
    "sessions_destroyed",
    "S7_shutdown_complete",
    "S5_shutdown_complete",
    "S4_shutdown_complete",
    "S3_shutdown_complete",
    "S2_shutdown_complete",
    "S1_shutdown_complete",
    "shutdown_complete",
]


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _phases(events: list[dict[str, object]]) -> list[str]:
    return [str(event["phase"]) for event in events]


def _assert_monotonic_timestamps(events: list[dict[str, object]]) -> None:
    timestamps = [float(event["ts"]) for event in events]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_m2_l1_kernel_startup_shutdown_lifecycle_order(tmp_path: Path) -> None:
    cfg = KernelConfig(
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
    svc = KernelService(config=cfg)
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        assert svc.is_running is True
        assert _phases(svc.lifecycle_events()) == STARTUP_PHASES
        _assert_monotonic_timestamps(svc.lifecycle_events())
    finally:
        if svc.is_running:
            await svc.shutdown()

    events = svc.lifecycle_events()
    assert _phases(events) == STARTUP_PHASES + SHUTDOWN_PHASES
    _assert_monotonic_timestamps(events)
    assert svc.is_running is False
    assert svc.describe_wiring()["running"] is False

    await asyncio.sleep(0)
    leaked_tasks = _active_task_snapshot() - baseline_tasks
    assert leaked_tasks == set()

    lingering_sqlite_sidecars = [
        path.name for pattern in ("*.db-wal", "*.db-shm") for path in tmp_path.glob(pattern)
    ]
    assert lingering_sqlite_sidecars == []
