"""M2-L2 live-kernel planner/orchestrator cross-wire probe.

Covers kernel sweep row M2-L2:
S6b replaces the orchestrator's MockPlannerAdapter with a real PlannerAdapter
wired to the live PlannerAgent mailbox before KernelService reports running.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter

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


@pytest.mark.asyncio
async def test_m2_l2_orchestrator_uses_real_planner_adapter(tmp_path: Path) -> None:
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()

        orchestrator = svc._orchestrator
        planner = svc._planner
        assert orchestrator is not None
        assert planner is not None

        planner_port = getattr(orchestrator, "_planner_port", None)
        assert isinstance(planner_port, PlannerAdapter)
        assert not isinstance(planner_port, MockPlannerAdapter)

        planner_mailbox = planner.get_mailbox()
        assert planner_port._mailbox is planner_mailbox
        assert planner_port._mailbox is planner.mailbox
        assert getattr(planner_mailbox, "_pipeline_controller", None) is not None

        svc._verify_planner_orchestrator_crosswire()
        svc._verify_planner_mailbox_binding()
        svc._verify_planner_task_running()

        wiring = svc.describe_wiring()
        assert wiring["tier1_ports"]["orchestrator.planner_port"] == "PlannerAdapter"
        assert wiring["tier1_ports"]["planner.mailbox"] == type(planner_mailbox).__name__
        assert (
            wiring["port_identities"]["orchestrator.planner_port_is_real_planner_adapter"] is True
        )
        assert wiring["port_identities"]["orchestrator.planner_port_is_mock"] is False
        assert (
            wiring["port_identities"]["orchestrator.planner_port_mailbox_is_planner_mailbox"]
            is True
        )

        phases = [event["phase"] for event in svc.lifecycle_events()]
        assert phases.index("S6b_complete") < phases.index("S7_complete")
        assert phases.index("S7_complete") < phases.index("startup_complete")
    finally:
        if svc.is_running:
            await svc.shutdown()

    await asyncio.sleep(0)
    leaked_tasks = _active_task_snapshot() - baseline_tasks
    assert leaked_tasks == set()

    lingering_sqlite_sidecars = [
        path.name for pattern in ("*.db-wal", "*.db-shm") for path in tmp_path.glob(pattern)
    ]
    assert lingering_sqlite_sidecars == []
