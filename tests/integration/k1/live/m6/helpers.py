"""Shared helpers for M6 live-kernel integration probes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService


def active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def recipe_a(tmp_path: Path, **overrides: Any) -> KernelConfig:
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


def recipe_b_hil(tmp_path: Path) -> KernelConfig:
    return recipe_a(
        tmp_path,
        enable_hitl=True,
        enable_hil_service=True,
        hil_approval_timeout_ms=5_000,
    )


def recipe_c_selfmodel(tmp_path: Path, **overrides: Any) -> KernelConfig:
    values: dict[str, Any] = {
        "enable_self_model": True,
        "selfmodel_projection_db_path": str(tmp_path / "selfmodel.db"),
        "selfmodel_space_id": "family:m6",
    }
    values.update(overrides)
    return recipe_a(tmp_path, **values)


def recipe_c_selfmodel_hil(tmp_path: Path) -> KernelConfig:
    return recipe_c_selfmodel(
        tmp_path,
        enable_hitl=True,
        enable_hil_service=True,
        hil_approval_timeout_ms=5_000,
    )


async def assert_no_task_leaks(baseline_tasks: set[asyncio.Task[object]]) -> None:
    await asyncio.sleep(0)
    leaked = active_task_snapshot() - baseline_tasks
    assert leaked == set(), f"Leaked tasks: {[task.get_name() for task in leaked]}"


async def cleanup_service(
    svc: KernelService,
    baseline_tasks: set[asyncio.Task[object]],
) -> None:
    if svc.is_running:
        await svc.shutdown()
    await assert_no_task_leaks(baseline_tasks)


def fabric_state_reader(fabric: Any) -> Any:
    return fabric.facade._context_builder._state_reader
