"""M2-X6..M2-X8 live-kernel lifecycle and dead-wire probes.

Covers the remaining M2 cross-component rows:

* M2-X6: S4 is complete before any per-session P-phase, and session creation
  logs P1 through P6 in order.
* M2-X7: destroy_session logs teardown in P6 -> P1 order, with MemoryWriter
  stopped before SessionState.
* M2-X8: AsyncSSMBridge is constructed at P2 but is not injected downstream.

The first two tests are live KernelService lifecycle probes. The X8 probe is a
strict-xfail static wiring assertion because proving a non-injection at runtime
would be circular; the correct future behavior is that the constructed bridge is
loaded/passed to at least one downstream component or stored on the session.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
from pathlib import Path

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService

pytestmark = pytest.mark.integration


CREATE_PHASES = [
    "P1_complete",
    "P2_complete",
    "P3_complete",
    "P4_complete",
    "P5_complete",
    "P6_complete",
]

TEARDOWN_PHASES = [
    "P6_teardown_start",
    "P5_teardown_complete",
    "P4_teardown_complete",
    "P3_teardown_complete",
    "P2_teardown_complete",
    "P1_teardown_complete",
]


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


def _phases(events: list[dict[str, object]]) -> list[str]:
    return [str(event["phase"]) for event in events]


def _session_events(svc: KernelService, session_id: str) -> list[dict[str, object]]:
    tag = f"session:{session_id}"
    return [event for event in svc.lifecycle_events() if event.get("component") == tag]


def _phase_index(events: list[dict[str, object]], phase: str) -> int:
    return _phases(events).index(phase)


def _assert_monotonic(events: list[dict[str, object]]) -> None:
    timestamps = [float(event["ts"]) for event in events]
    assert timestamps == sorted(timestamps)


async def _assert_no_task_leaks(baseline_tasks: set[asyncio.Task[object]]) -> None:
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert leaked == set(), f"Leaked tasks: {[task.get_name() for task in leaked]}"


@pytest.mark.asyncio
async def test_m2_x6_s4_precedes_session_creation_p1_to_p6(tmp_path: Path) -> None:
    """S4 bridge startup completes before P1, and session creation runs P1..P6."""
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session("m2x6")

        all_events = svc.lifecycle_events()
        session_events = _session_events(svc, "m2x6")
        session_create_phases = [phase for phase in _phases(session_events) if phase in CREATE_PHASES]

        assert session_create_phases == CREATE_PHASES
        assert _phase_index(all_events, "S4_complete") < _phase_index(all_events, "P1_complete")
        assert _phase_index(all_events, "startup_complete") < _phase_index(
            all_events,
            "P1_complete",
        )
        assert session_create_phases[0] == "P1_complete"
        assert session_create_phases[-1] == "P6_complete"
        _assert_monotonic(all_events)
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_task_leaks(baseline_tasks)


@pytest.mark.asyncio
async def test_m2_x7_destroy_session_teardown_p6_to_p1_and_mw_before_ssm(
    tmp_path: Path,
) -> None:
    """destroy_session tears down P6..P1 and logs MW completion before SSM completion."""
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session("m2x7")
        await svc.destroy_session("m2x7")

        session_events = _session_events(svc, "m2x7")
        teardown_phases = [phase for phase in _phases(session_events) if phase in TEARDOWN_PHASES]

        assert teardown_phases == TEARDOWN_PHASES
        assert teardown_phases.index("P5_teardown_complete") < teardown_phases.index(
            "P2_teardown_complete",
        )
        assert "m2x7" not in svc._sessions
        _assert_monotonic(session_events)
    finally:
        if svc.is_running:
            await svc.shutdown()

    await _assert_no_task_leaks(baseline_tasks)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "I2.X.8: AsyncSSMBridge is constructed at P2 but never loaded/passed to "
        "any downstream component. Fix by storing/injecting the async bridge, "
        "then remove this xfail."
    ),
)
def test_m2_x8_async_ssm_bridge_is_injected_after_construction() -> None:
    """Desired behavior: the P2 AsyncSSMBridge is consumed after construction."""
    source = textwrap.dedent(inspect.getsource(KernelService._create_session_tier2))
    tree = ast.parse(source)

    stores = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "async_ssm"
        and isinstance(node.ctx, ast.Store)
    ]
    loads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "async_ssm"
        and isinstance(node.ctx, ast.Load)
    ]

    assert len(stores) == 1, "Expected one P2 AsyncSSMBridge construction binding"
    assert loads, "AsyncSSMBridge is constructed but never injected or stored"