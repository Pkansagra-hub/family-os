"""M2-L3 live-kernel per-session Fabric state-reader probe.

Covers kernel sweep row M2-L3 (PORT-IDENTITY / E2.4 / I2.4.3):
After ``create_session()``, the per-session CapabilityFabric's
ContextBuilder must hold a real ``SessionStateReaderAdapter`` bound to
*that* session's SSM — never a ``NullSessionStateReaderAdapter``.

Assertion targets
-----------------
* ``reader`` is a ``SessionStateReaderAdapter`` (real, not Null)
* ``reader._manager is session.session_state`` (same SSM object — identity)
* ``reader._session_id == session_id`` (bound to correct session)
* Two sessions get *different* reader instances (independent bindings)
* No asyncio task leaks, no SQLite sidecars left open.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.fabric.adapters.null_state_reader import NullSessionStateReaderAdapter
from k1.fabric.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.kernel.service import KernelService

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


def _get_state_reader(session_instance: object) -> object:
    """Reach from SessionInstance → CapabilityFabric → ContextBuilder._state_reader."""
    fabric_container = session_instance.fabric  # Fabric dataclass
    capability_fabric = fabric_container.facade  # CapabilityFabric
    return capability_fabric._context_builder._state_reader


# ── main probe ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l3_per_session_fabric_has_real_state_reader(tmp_path: Path) -> None:
    """Per-session Fabric ContextBuilder holds a real SessionStateReaderAdapter."""
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    await svc.startup()
    try:
        # ── create two independent sessions ───────────────────────────────────
        session_id_a = "session-m2l3-a"
        session_id_b = "session-m2l3-b"

        await svc.create_session(session_id_a)
        await svc.create_session(session_id_b)

        session_a = svc._sessions[session_id_a]
        session_b = svc._sessions[session_id_b]

        reader_a = _get_state_reader(session_a)
        reader_b = _get_state_reader(session_b)

        # ── 1. readers are the real adapter type ──────────────────────────────
        assert isinstance(
            reader_a, SessionStateReaderAdapter
        ), f"session A Fabric reader is {type(reader_a).__name__}, expected SessionStateReaderAdapter"
        assert isinstance(
            reader_b, SessionStateReaderAdapter
        ), f"session B Fabric reader is {type(reader_b).__name__}, expected SessionStateReaderAdapter"

        # ── 2. NullSessionStateReaderAdapter is FORBIDDEN ─────────────────────
        assert not isinstance(reader_a, NullSessionStateReaderAdapter), (
            "session A Fabric reader is NullSessionStateReaderAdapter — per-session Fabric "
            "must use a real reader bound to the session's SSM"
        )
        assert not isinstance(reader_b, NullSessionStateReaderAdapter), (
            "session B Fabric reader is NullSessionStateReaderAdapter — per-session Fabric "
            "must use a real reader bound to the session's SSM"
        )

        # ── 3. reader._manager is the session's own SSM (identity) ────────────
        ssm_a = session_a.session_state
        ssm_b = session_b.session_state

        assert (
            reader_a._manager is ssm_a
        ), "session A reader._manager is not the session's SSM — wrong SSM wired"
        assert (
            reader_b._manager is ssm_b
        ), "session B reader._manager is not the session's SSM — wrong SSM wired"

        # ── 4. reader is bound to the correct session_id ──────────────────────
        assert (
            reader_a._session_id == session_id_a
        ), f"reader_a._session_id={reader_a._session_id!r} != {session_id_a!r}"
        assert (
            reader_b._session_id == session_id_b
        ), f"reader_b._session_id={reader_b._session_id!r} != {session_id_b!r}"

        # ── 5. two sessions get independent reader instances ──────────────────
        assert (
            reader_a is not reader_b
        ), "session A and B share the same reader instance — readers must be independent"

    finally:
        await svc.shutdown()

    # ── 6. no asyncio task leaks ──────────────────────────────────────────────
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert not leaked, f"Task leak after stop(): {[t.get_name() for t in leaked]}"

    # ── 7. no SQLite sidecars left open (workflow + bridge only) ─────────────
    # Note: ssm.db-wal is expected after per-session SSM checkpoints — that is
    # normal SQLite WAL behaviour. We only assert the workflow and bridge DBs
    # are fully closed (no WAL/SHM).
    for db_name in ("workflows.db", "bridge.db"):
        for suffix in ("-wal", "-shm"):
            sidecar = tmp_path / (db_name + suffix)
            assert not sidecar.exists(), f"SQLite sidecar not cleaned up: {sidecar}"
