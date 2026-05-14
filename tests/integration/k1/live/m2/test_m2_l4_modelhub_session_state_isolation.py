"""M2-L4 live-kernel ModelHub session-state isolation probe.

Covers kernel sweep row M2-L4 (NEGATIVE / I2.5.1 / OPEN §1):

    ``ModelHub.state_read_port`` is bound to ``_NullSSMShim`` — a
    session-blind shim that returns ``None`` for every ``get_section``
    call.  Because ``IStateReadPort.read()`` carries no ``session_id``
    parameter, the shared port has no way to route state reads to the
    correct per-session SSM.  Both sessions therefore receive an
    *identical* empty ``StateSnapshot({})`` regardless of what is
    written into their individual SSMs.

**This test is expected to FAIL today** (``xfail strict=True``).

The test will turn green (xpass → remove xfail) only when
``HubRequest.session_id`` is threaded through ``IStateReadPort`` so the
adapter can resolve the correct SSM per request (tracked as 3.1.x
follow-up work).

What this probe also confirms
------------------------------
* ``_NullSSMShim`` replaced the old ``_FirstSessionSSMShim`` (task 3.1.2).
  The old shim silently returned session-0's data for all callers.
  ``_NullSSMShim`` at least returns *empty* data and logs a WARNING,
  making the degradation explicit rather than silently wrong.
* ``MockPlannerAdapter`` is correctly replaced at S6b (already confirmed
  by M2-L2) — this probe does NOT revisit that wire.
* ``MockBridgeAdapter`` appears only when ``bridge_enabled=False``
  (Recipe-A) which is intentional; no swap needed for that path.

Null/Mock adapter audit for this probe
---------------------------------------
| Adapter                | Location              | Status                    |
|------------------------|-----------------------|---------------------------|
| ``_NullSSMShim``       | service.py S2 L~1324  | OPEN §1 — xfail until 3.1.x|
| ``MockPlannerAdapter`` | service.py S5 L~1569  | Correct; swapped at S6b   |
| ``MockBridgeAdapter``  | service.py S5 L~1582  | Correct; bridge_enabled=F |
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.model_hub.ports.state_read_port import IStateReadPort, StateSnapshot

pytestmark = pytest.mark.integration


# ── helpers ──────────────────────────────────────────────────────────────────


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


def _get_state_read_port(svc: KernelService) -> IStateReadPort:
    """Reach into ModelHub's RequestRouter to get the state_read_port."""
    return svc._model_hub._router._state_read_port


# ── structural integrity (always-pass, not xfail) ────────────────────────────


@pytest.mark.asyncio
async def test_m2_l4_modelhub_state_read_port_is_present(tmp_path: Path) -> None:
    """ModelHub's state_read_port exists and satisfies IStateReadPort protocol.

    This assertion is NOT xfail — the port must be wired.  What's broken
    today is session *routing*, not port existence.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    await svc.startup()
    try:
        port = _get_state_read_port(svc)
        assert port is not None, "ModelHub._router._state_read_port is None — not wired"
        assert isinstance(
            port, IStateReadPort
        ), f"state_read_port {type(port).__name__} does not satisfy IStateReadPort protocol"
    finally:
        await svc.shutdown()


# ── xfail isolation probe ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "OPEN §1 / I2.5.1: ModelHub.state_read_port is bound to _NullSSMShim. "
        "IStateReadPort.read() carries no session_id, so the shared port cannot "
        "route reads to the correct per-session SSM. Both sessions receive an "
        "identical empty StateSnapshot(sections={}). "
        "Fix: thread HubRequest.session_id through IStateReadPort (3.1.x follow-up)."
    ),
)
async def test_m2_l4_modelhub_state_reads_differ_per_session(tmp_path: Path) -> None:
    """Two sessions with distinct SSMs must produce different ModelHub state reads.

    Today: _NullSSMShim returns StateSnapshot(sections={}) for ALL sessions,
    so both reads are identical → strict xfail confirms the gap is real.

    When fixed (3.1.x): each session's SessionStateManager is consulted
    via a session-scoped IStateReadPort, results will differ → remove xfail.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    await svc.startup()
    try:
        session_id_a = "session-m2l4-a"
        session_id_b = "session-m2l4-b"

        await svc.create_session(session_id_a)
        await svc.create_session(session_id_b)

        # The shared state_read_port — no session_id routing capability today.
        port = _get_state_read_port(svc)

        # Read the same sections twice (once per "session context").
        # With a real per-session port these would be dispatched to different
        # SSMs; with _NullSSMShim both return empty StateSnapshot.
        snapshot_a: StateSnapshot = await port.read(["persona", "control"])
        snapshot_b: StateSnapshot = await port.read(["persona", "control"])

        # ── This is the broken invariant ──────────────────────────────────────
        # After creating two distinct sessions, state reads should reflect each
        # session's own SSM.  Today both return StateSnapshot(sections={}).
        assert snapshot_a.sections != snapshot_b.sections, (
            "ModelHub state_read_port returned identical results for two "
            "distinct sessions — IStateReadPort has no session_id parameter "
            "so _NullSSMShim cannot distinguish callers. "
            "Ref: OPEN §1 / I2.5.1"
        )

    finally:
        await svc.shutdown()

    # Task leak guard (runs even on xfail)
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert not leaked, f"Task leak after stop(): {[t.get_name() for t in leaked]}"
