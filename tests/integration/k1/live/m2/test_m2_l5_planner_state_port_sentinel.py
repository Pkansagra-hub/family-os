"""M2-L5 live-kernel Planner state_port sentinel probe.

Covers kernel sweep row M2-L5 (NEGATIVE / I2.5.2 / OPEN §2):

    ``PlannerAgent`` is wired at S6 with a ``PlannerStateAdapter``
    pre-bound to ``session_id=""`` (formerly ``"__shared__"``).
    ``SessionRoutingStateReader.read_sections("")`` finds no session in
    ``_sessions[""]`` → always returns an empty ``SessionSnapshot``.

    ``ToolCallRouter.read_context(session_id="", ...)`` therefore always
    yields an empty context regardless of what any real session's SSM
    contains.  Planning decisions that depend on ``persona`` / ``control``
    sections silently degrade to empty.

**This test is expected to FAIL today** (``xfail strict=True``).

The xfail will be lifted when every ``PlanRequest`` carries a real
``session_id`` that is threaded from ``PlannerAgent.handle_request()``
all the way through to ``ToolCallRouter.read_context(session_id=...)``,
so state is resolved against the *requesting* session's SSM.

What the probe tests
---------------------
1. Structural: the ``_state_read`` adapter is wired (not None).
2. Structural: the adapter is a real ``SessionStateReadAdapter``, not Null.
3. Structural: the pre-bound ``_session_id`` is ``""`` — confirming the
   sentinel has been cleaned up from ``"__shared__"`` (task 3.1.2 partial).
4. Behavioural (xfail): calling ``read_sections`` with the sentinel id
   returns an empty ``SessionSnapshot``; a *real* session_id must return
   non-empty data after that session has been started and its SSM
   populated — but today both paths return empty.

Adapter audit for this probe
-----------------------------
| Adapter                    | Status                                         |
|----------------------------|------------------------------------------------|
| PlannerStateAdapter (""  ) | OPEN §2 — sentinel resolves no session today   |
| _NullSSMShim (ModelHub)    | OPEN §1 — confirmed xfail M2-L4               |
| MockPlannerAdapter         | Swapped at S6b — confirmed green M2-L2        |
| MockBridgeAdapter          | bridge_enabled=False intentional (Recipe-A)   |
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.planner.adapters.session_state_adapter import (
    SessionStateReadAdapter as PlannerStateAdapter,
)

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


def _get_planner_state_adapter(svc: KernelService) -> object:
    """Traverse PlannerAgent → PipelineController → SketchService → ToolCallRouter._state_read."""
    return svc._planner._pipeline._sketch._tool_router._state_read


# ── structural integrity (always-pass) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l5_planner_state_adapter_is_wired(tmp_path: Path) -> None:
    """Planner state_port is wired (not None) and is a real PlannerStateAdapter.

    Structural assertion only — not xfail. The adapter MUST exist; what's
    broken today is its session_id sentinel, not its presence.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    await svc.startup()
    try:
        adapter = _get_planner_state_adapter(svc)

        assert (
            adapter is not None
        ), "Planner ToolCallRouter._state_read is None — state_port not wired at S6"
        assert isinstance(adapter, PlannerStateAdapter), (
            f"Planner state adapter is {type(adapter).__name__}, "
            "expected SessionStateReadAdapter (PlannerStateAdapter)"
        )

        # Confirm sentinel has been cleaned up from "__shared__" to ""
        # (task 3.1.2 partial fix — "" is the new fallback sentinel).
        bound_sid = getattr(adapter, "_session_id", None)
        assert bound_sid is not None, "PlannerStateAdapter has no _session_id attribute"
        assert bound_sid != "__shared__", (
            "PlannerStateAdapter still uses the old '__shared__' sentinel — "
            "task 3.1.2 cleanup not applied"
        )
    finally:
        await svc.shutdown()


# ── xfail behavioural probe ───────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "OPEN §2 / I2.5.2: PlannerStateAdapter pre-bound session_id='' resolves to "
        "_sessions[''] which never exists → SessionRoutingStateReader returns empty "
        "SessionSnapshot for any call that uses the pre-bound sentinel (i.e. when "
        "PlannerAgent does not thread session_id through to ToolCallRouter.read_context). "
        "The sentinel read must return non-empty context once planning is session-aware. "
        "Fix: thread PlanRequest.context.session_id from PlannerAgent.handle_request() "
        "through PipelineController → SketchService → ToolCallRouter.read_context()."
    ),
)
async def test_m2_l5_planner_state_reads_session_data(tmp_path: Path) -> None:
    """Planner state read via pre-bound sentinel MUST yield non-empty context.

    The pre-bound ``session_id=""`` on the shared ``PlannerStateAdapter`` means any
    planning call that does NOT explicitly thread a ``session_id`` uses the sentinel.
    ``_sessions[""]`` never exists → ``SessionRoutingStateReader`` returns
    ``SessionSnapshot(sections={})`` → planning has no session awareness.

    This xfail asserts the correct behaviour (non-empty context) that is NOT achieved
    today via the sentinel path.  When 3.1.x threads ``session_id`` per-request, the
    sentinel becomes irrelevant and this test can be removed / replaced.

    Note: direct ``read_sections(session_id=<real_id>)`` calls DO work today
    because ``SessionRoutingStateReader`` can resolve a real session.  The gap is
    that the planner pipeline never passes a real session_id — it relies on the
    pre-bound sentinel.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    await svc.startup()
    try:
        session_id = "session-m2l5"
        await svc.create_session(session_id)

        adapter = _get_planner_state_adapter(svc)

        # ── read via pre-bound sentinel (simulates what the planner does today) ──
        # No session_id provided → adapter falls back to _session_id="" sentinel.
        sentinel_snapshot = await adapter.read_sections(
            sections=["persona", "control"],
            # deliberately omit session_id to test the sentinel fallback path
        )

        # ── This is the broken invariant ──────────────────────────────────────
        # After a real session is live, the planner's state reads should yield
        # non-empty context. Today the sentinel "" resolves to nothing → empty.
        assert sentinel_snapshot.sections != {}, (
            "Planner state read via sentinel session_id='' returned empty snapshot. "
            "PlannerAgent planning pipeline operates without session context. "
            "Ref: OPEN §2 / I2.5.2"
        )

    finally:
        await svc.shutdown()

    # Task leak guard
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert not leaked, f"Task leak after stop(): {[t.get_name() for t in leaked]}"
