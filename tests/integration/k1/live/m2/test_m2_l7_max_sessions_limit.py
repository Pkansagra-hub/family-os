"""M2-L7 live-kernel max_sessions enforcement probe.

Covers kernel sweep row M2-L7 (NEGATIVE / I2.5.3):

    ``create_session`` must raise ``RuntimeError`` when the number of active
    sessions equals ``KernelConfig.max_sessions``.

Background
----------
``KernelConfig.max_sessions: int = 100`` (default). The guard at
``service.py`` lines 789–792 enforces it:

    if len(self._sessions) >= self._config.max_sessions:
        raise RuntimeError(
            f"Maximum session limit reached ({self._config.max_sessions}). "
            "Destroy an existing session before creating a new one."
        )

I2.5.3 / OPEN §4 listed this as a GAP ("declared but never enforced").
The gap has been **closed** — the guard exists in production code. These
tests confirm the enforcement is real and correct under the live kernel.

Test coverage
-------------
| # | Assertion | Tracing ref | Expected |
|---|-----------|-------------|---------|
| 1 | 3rd create on max_sessions=2 → RuntimeError | I2.5.3 | GREEN |
| 2 | Error message contains the numeric limit | I2.5.3 | GREEN |
| 3 | ``_sessions`` still holds exactly 2 entries after rejected create | I2.5.3 | GREEN |
| 4 | After destroy one, creating a new session succeeds | I2.5.3 | GREEN |
| 5 | Duplicate-ID guard fires BEFORE max_sessions guard (raises ValueError not RuntimeError) | I2.5.3 | GREEN |
| 6 | max_sessions=0 → first create raises immediately | I2.5.3 edge | GREEN |
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService

pytestmark = pytest.mark.integration


# ── helpers ──────────────────────────────────────────────────────────────────


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path, **overrides: object) -> KernelConfig:
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
        **overrides,
    )


# ── core enforcement probe ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l7_third_session_raises_at_max_2(tmp_path: Path) -> None:
    """Creating a 3rd session when max_sessions=2 raises RuntimeError.

    Also verifies:
    - _sessions still contains exactly 2 entries (no partial state).
    - The error message includes the numeric limit.
    """
    svc = KernelService(config=_recipe_a(tmp_path, max_sessions=2))
    baseline_tasks = _active_task_snapshot()

    await svc.startup()

    await svc.create_session("m2l7-a")
    await svc.create_session("m2l7-b")

    assert len(svc._sessions) == 2, "Expected 2 sessions before third create attempt"

    with pytest.raises(RuntimeError) as exc_info:
        await svc.create_session("m2l7-c")

    # ── 1. RuntimeError raised ────────────────────────────────────────────────
    assert exc_info.type is RuntimeError

    # ── 2. Error message contains the limit ──────────────────────────────────
    assert "2" in str(
        exc_info.value
    ), f"Expected limit '2' in error message; got: {exc_info.value!r}"

    # ── 3. No partial state: _sessions still has exactly 2 entries ───────────
    assert len(svc._sessions) == 2, (
        f"_sessions has {len(svc._sessions)} entries after rejected create — "
        "zombie session was not cleaned up"
    )
    assert "m2l7-c" not in svc._sessions, "Rejected session 'm2l7-c' still present in _sessions"

    await svc.destroy_session("m2l7-a")
    await svc.destroy_session("m2l7-b")
    await svc.shutdown()

    # ── task leak check ───────────────────────────────────────────────────────
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert not leaked, f"Task leak: {[t.get_name() for t in leaked]}"


# ── release-and-recreate probe ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l7_create_succeeds_after_destroy(tmp_path: Path) -> None:
    """After destroying one session from a full pool, a new session can be created.

    Verifies that the max_sessions guard uses the live count (``len(_sessions)``)
    and not a monotonically incrementing counter.
    """
    svc = KernelService(config=_recipe_a(tmp_path, max_sessions=2))
    await svc.startup()

    await svc.create_session("m2l7-p")
    await svc.create_session("m2l7-q")

    # Pool is full — next create must fail
    with pytest.raises(RuntimeError):
        await svc.create_session("m2l7-overflow")

    # Free one slot
    await svc.destroy_session("m2l7-p")

    # Now this must succeed
    await svc.create_session("m2l7-r")
    assert "m2l7-r" in svc._sessions, "Session m2l7-r should exist after slot freed"
    assert len(svc._sessions) == 2

    await svc.shutdown()


# ── duplicate-id ordering probe ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l7_duplicate_id_raises_before_max_sessions(tmp_path: Path) -> None:
    """Duplicate-ID guard (ValueError) fires BEFORE max_sessions guard (RuntimeError).

    If the pool is also full, a duplicate-ID create still raises ValueError,
    not RuntimeError — preserving guard ordering.
    """
    svc = KernelService(config=_recipe_a(tmp_path, max_sessions=1))
    await svc.startup()

    await svc.create_session("m2l7-only")

    # Pool full (1/1) AND using an existing ID — ValueError must win
    with pytest.raises(ValueError, match="already exists"):
        await svc.create_session("m2l7-only")

    await svc.shutdown()


# ── zero limit edge probe ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l7_zero_max_sessions_rejects_first_create(tmp_path: Path) -> None:
    """max_sessions=0 means no sessions allowed at all — first create raises."""
    svc = KernelService(config=_recipe_a(tmp_path, max_sessions=0))
    await svc.startup()

    with pytest.raises(RuntimeError) as exc_info:
        await svc.create_session("m2l7-zero")

    assert "0" in str(
        exc_info.value
    ), f"Expected limit '0' in error message; got: {exc_info.value!r}"
    assert len(svc._sessions) == 0

    await svc.shutdown()
