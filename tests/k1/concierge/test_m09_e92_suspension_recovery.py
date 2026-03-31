"""
M9 E9.2: Suspension ledger integration + rebuild tests.

Covers:
    E9.2.1 -- SuspensionManager emits TaskSuspended/TaskResumed to ledger.
    E9.2.3 -- project_suspension_state() projection.
    E9.2.4 -- SuspensionManager.rebuild_from_events().

Run:
    python -m pytest tests/poc/test_m09_e92_suspension_recovery.py -v
"""

from __future__ import annotations

from typing import Any

import pytest

from k1.concierge.ledger.projections import project_suspension_state
from k1.concierge.ledger.store import InMemoryLedgerStore, LedgerEntry
from k1.concierge.ledger.writer import LedgerWriter
from k1.concierge.protocols.suspension import SuspensionRequest, SuspensionResolution, SuspensionType
from k1.concierge.protocols.suspension_manager import SuspensionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_writer(session_id: str = "s1") -> LedgerWriter:
    store = InMemoryLedgerStore()
    return LedgerWriter(store, session_id=session_id)


def _entries(writer: LedgerWriter) -> list[LedgerEntry]:
    return writer.store.read(writer.session_id)


def _make_request(
    task_id: str = "t1",
    s_type: SuspensionType = SuspensionType.CLARIFICATION,
    question: str = "Which one?",
) -> SuspensionRequest:
    return SuspensionRequest(
        task_id=task_id,
        suspension_type=s_type,
        question=question,
        react_history=[{"role": "user", "content": "hello"}],
    )


def _make_resolution(task_id: str = "t1") -> SuspensionResolution:
    return SuspensionResolution(
        task_id=task_id,
        resolution="option_a",
        resolution_type="selection",
    )


def _make_ledger_entry(
    event_type: str,
    task_id: str,
    seq: int = 0,
    **extra: Any,
) -> LedgerEntry:
    payload: dict[str, Any] = {"task_id": task_id, **extra}
    return LedgerEntry(
        seq=seq,
        event_id=f"evt-{seq}",
        event_type=event_type,
        session_id="s1",
        payload=payload,
        written_at_utc="2025-01-01T00:00:00Z",
    )


# ===================================================================
# E9.2.1 -- SuspensionManager ledger writes
# ===================================================================


class TestSuspensionManagerLedgerWrites:
    """Verify suspend/resolve emit canonical events to ledger."""

    @pytest.mark.asyncio
    async def test_suspend_writes_task_suspended(self) -> None:
        writer = _make_writer()
        mgr = SuspensionManager(ledger=writer)
        await mgr.suspend(_make_request("t1"))

        entries = _entries(writer)
        assert len(entries) == 1
        assert entries[0].event_type == "task.suspended"
        assert entries[0].payload["task_id"] == "t1"
        assert entries[0].payload["suspension_type"] == "clarification"
        assert entries[0].payload["suspension_count"] == 1

    @pytest.mark.asyncio
    async def test_resolve_writes_task_resumed(self) -> None:
        writer = _make_writer()
        mgr = SuspensionManager(ledger=writer)
        await mgr.suspend(_make_request("t1"))
        await mgr.resolve(_make_resolution("t1"))

        entries = _entries(writer)
        assert len(entries) == 2
        assert entries[0].event_type == "task.suspended"
        assert entries[1].event_type == "task.resumed"
        assert entries[1].payload["task_id"] == "t1"
        assert entries[1].payload["resume_instruction"] == "option_a"

    @pytest.mark.asyncio
    async def test_no_ledger_no_writes(self) -> None:
        mgr = SuspensionManager()
        await mgr.suspend(_make_request("t1"))
        # No crash, no writes -- just verifies no NPE
        assert mgr.is_suspended("t1")

    @pytest.mark.asyncio
    async def test_set_ledger_post_construction(self) -> None:
        writer = _make_writer()
        mgr = SuspensionManager()
        mgr.set_ledger(writer)
        await mgr.suspend(_make_request("t1"))
        assert len(_entries(writer)) == 1

    @pytest.mark.asyncio
    async def test_resolve_non_suspended_no_write(self) -> None:
        writer = _make_writer()
        mgr = SuspensionManager(ledger=writer)
        result = await mgr.resolve(_make_resolution("t_nonexistent"))
        assert result is None
        # Should not write a resumed event for non-suspended task
        assert len(_entries(writer)) == 0

    @pytest.mark.asyncio
    async def test_suspend_resolve_suspend_counts(self) -> None:
        """Two suspension rounds write correct counts."""
        writer = _make_writer()
        mgr = SuspensionManager(ledger=writer)

        await mgr.suspend(_make_request("t1"))
        await mgr.resolve(_make_resolution("t1"))
        await mgr.suspend(_make_request("t1"))

        entries = _entries(writer)
        assert len(entries) == 3
        # First suspension count=1, second count=2
        assert entries[0].payload["suspension_count"] == 1
        assert entries[2].payload["suspension_count"] == 2


# ===================================================================
# E9.2.3 -- project_suspension_state()
# ===================================================================


class TestSuspensionStateProjection:
    """Verify project_suspension_state() correctly replays events."""

    def test_empty_events(self) -> None:
        active, counts = project_suspension_state([])
        assert active == {}
        assert counts == {}

    def test_suspended_task_is_active(self) -> None:
        entries = [
            _make_ledger_entry(
                "task.suspended", "t1", seq=1, suspension_type="clarification", suspension_count=1
            ),
        ]
        active, counts = project_suspension_state(entries)
        assert "t1" in active
        assert active["t1"]["suspension_type"] == "clarification"
        assert counts["t1"] == 1

    def test_resumed_task_not_active(self) -> None:
        entries = [
            _make_ledger_entry("task.suspended", "t1", seq=1, suspension_count=1),
            _make_ledger_entry("task.resumed", "t1", seq=2),
        ]
        active, counts = project_suspension_state(entries)
        assert "t1" not in active
        assert counts["t1"] == 1  # Count preserved

    def test_completed_task_clears_suspension(self) -> None:
        entries = [
            _make_ledger_entry("task.suspended", "t1", seq=1, suspension_count=1),
            _make_ledger_entry("task.completed", "t1", seq=2),
        ]
        active, counts = project_suspension_state(entries)
        assert "t1" not in active

    def test_two_suspensions_correct_count(self) -> None:
        entries = [
            _make_ledger_entry("task.suspended", "t1", seq=1, suspension_count=1),
            _make_ledger_entry("task.resumed", "t1", seq=2),
            _make_ledger_entry("task.suspended", "t1", seq=3, suspension_count=2),
        ]
        active, counts = project_suspension_state(entries)
        assert "t1" in active
        assert counts["t1"] == 2

    def test_mixed_tasks(self) -> None:
        entries = [
            _make_ledger_entry("task.suspended", "t1", seq=1, suspension_count=1),
            _make_ledger_entry("task.suspended", "t2", seq=2, suspension_count=1),
            _make_ledger_entry("task.resumed", "t1", seq=3),
        ]
        active, counts = project_suspension_state(entries)
        assert "t1" not in active
        assert "t2" in active
        assert counts["t1"] == 1
        assert counts["t2"] == 1


# ===================================================================
# E9.2.4 -- SuspensionManager.rebuild_from_events()
# ===================================================================


class TestSuspensionRebuildFromEvents:
    """Verify rebuild restores suspension state from projection."""

    def test_rebuild_active_suspension(self) -> None:
        entries = [
            _make_ledger_entry(
                "task.suspended",
                "t1",
                seq=1,
                suspension_type="approval",
                suspension_count=1,
                question="Proceed?",
                react_history=[{"role": "user", "content": "do it"}],
            ),
        ]
        mgr = SuspensionManager()
        restored = mgr.rebuild_from_events(entries)

        assert restored == 1
        assert mgr.is_suspended("t1")
        req = mgr.get_request("t1")
        assert req is not None
        assert req.suspension_type == SuspensionType.APPROVAL
        assert req.question == "Proceed?"

    def test_rebuild_resumed_task_not_active(self) -> None:
        entries = [
            _make_ledger_entry("task.suspended", "t1", seq=1, suspension_count=1),
            _make_ledger_entry("task.resumed", "t1", seq=2),
        ]
        mgr = SuspensionManager()
        restored = mgr.rebuild_from_events(entries)

        assert restored == 0
        assert not mgr.is_suspended("t1")

    def test_rebuild_preserves_suspension_counts(self) -> None:
        entries = [
            _make_ledger_entry("task.suspended", "t1", seq=1, suspension_count=1),
            _make_ledger_entry("task.resumed", "t1", seq=2),
            _make_ledger_entry("task.suspended", "t1", seq=3, suspension_count=2),
        ]
        mgr = SuspensionManager()
        mgr.rebuild_from_events(entries)

        assert mgr._suspension_counts["t1"] == 2

    def test_rebuild_clears_previous_state(self) -> None:
        """rebuild_from_events() resets all prior in-memory state."""
        mgr = SuspensionManager()
        mgr._suspension_counts["old_task"] = 5
        mgr._contexts["old_task"] = {"stale": True}

        entries = [
            _make_ledger_entry("task.suspended", "t1", seq=1, suspension_count=1),
        ]
        mgr.rebuild_from_events(entries)

        assert "old_task" not in mgr._suspension_counts
        assert "old_task" not in mgr._contexts
        assert mgr.is_suspended("t1")

    @pytest.mark.asyncio
    async def test_full_suspend_crash_rebuild_flow(self) -> None:
        """End-to-end: suspend -> crash -> rebuild -> resume succeeds."""
        writer = _make_writer()
        mgr1 = SuspensionManager(ledger=writer)
        await mgr1.suspend(_make_request("t1", SuspensionType.APPROVAL, "Confirm?"))

        # Simulate crash: create new manager, rebuild from ledger
        mgr2 = SuspensionManager()
        entries = _entries(writer)
        mgr2.rebuild_from_events(entries)

        assert mgr2.is_suspended("t1")
        req = mgr2.get_request("t1")
        assert req is not None
        assert req.suspension_type == SuspensionType.APPROVAL
