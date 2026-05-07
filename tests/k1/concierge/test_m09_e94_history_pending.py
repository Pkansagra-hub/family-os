"""
M9 E9.4.3-4: History projection + pending results ledger tests.

Covers:
    E9.4.3 -- Active task IDs derivable from projected task states.
    E9.4.4 -- FSMTurnState ledger writes (WeaveCandidateArrived/WeaveEmitted)
              + rebuild_from_projection().

Run:
    python -m pytest tests/poc/test_m09_e94_history_pending.py -v
"""

from __future__ import annotations

from collections import deque
from typing import Any
from unittest.mock import MagicMock

from k1.concierge.fsm.turn_state import FSMTurnState
from k1.concierge.ledger.projections import project_pending_results, project_task_states
from k1.concierge.ledger.store import InMemoryLedgerStore, LedgerEntry
from k1.concierge.ledger.writer import LedgerWriter
from k1.concierge.protocols.hitl_persistence import TaskStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_writer(session_id: str = "s1") -> LedgerWriter:
    store = InMemoryLedgerStore()
    return LedgerWriter(store, session_id=session_id)


def _entries(writer: LedgerWriter) -> list[LedgerEntry]:
    return writer.store.read(writer.session_id)


def _make_ledger_entry(
    event_type: str,
    task_id: str = "",
    seq: int = 0,
    **extra: Any,
) -> LedgerEntry:
    payload: dict[str, Any] = {**extra}
    if task_id:
        payload["task_id"] = task_id
    return LedgerEntry(
        seq=seq,
        event_id=f"evt-{seq}",
        event_type=event_type,
        session_id="s1",
        payload=payload,
        written_at_utc="2025-01-01T00:00:00Z",
    )


def _make_envelope(eid: int = 1, parent: int = 0) -> MagicMock:
    env = MagicMock()
    env.envelope_id = eid
    env.parent_id = parent
    return env


# ===================================================================
# E9.4.3 -- Active task IDs from projected task states
# ===================================================================


class TestActiveTaskIdsFromProjection:
    """Verify _active_task_ids can be derived from project_task_states()."""

    def test_dispatched_task_is_active(self) -> None:
        entries = [
            _make_ledger_entry("task.created", "t1", seq=1, action="search_hotels"),
        ]
        projected = project_task_states(entries)
        active = {
            tid
            for tid, entry in projected.items()
            if entry.status in (TaskStatus.DISPATCHED, TaskStatus.IN_PROGRESS, TaskStatus.SUSPENDED)
        }
        assert active == {"t1"}

    def test_completed_task_not_active(self) -> None:
        entries = [
            _make_ledger_entry("task.created", "t1", seq=1, action="search"),
            _make_ledger_entry("task.completed", "t1", seq=2),
        ]
        projected = project_task_states(entries)
        active = {
            tid
            for tid, entry in projected.items()
            if entry.status in (TaskStatus.DISPATCHED, TaskStatus.IN_PROGRESS, TaskStatus.SUSPENDED)
        }
        assert active == set()

    def test_suspended_task_is_active(self) -> None:
        entries = [
            _make_ledger_entry("task.created", "t1", seq=1, action="book"),
            _make_ledger_entry("task.suspended", "t1", seq=2, suspension_count=1),
        ]
        projected = project_task_states(entries)
        active = {
            tid
            for tid, entry in projected.items()
            if entry.status in (TaskStatus.DISPATCHED, TaskStatus.IN_PROGRESS, TaskStatus.SUSPENDED)
        }
        assert active == {"t1"}

    def test_mixed_active_and_terminal(self) -> None:
        entries = [
            _make_ledger_entry("task.created", "t1", seq=1, action="a"),
            _make_ledger_entry("task.created", "t2", seq=2, action="b"),
            _make_ledger_entry("task.created", "t3", seq=3, action="c"),
            _make_ledger_entry("task.completed", "t1", seq=4),
            _make_ledger_entry("task.failed", "t3", seq=5, reason="timeout"),
        ]
        projected = project_task_states(entries)
        active = {
            tid
            for tid, entry in projected.items()
            if entry.status in (TaskStatus.DISPATCHED, TaskStatus.IN_PROGRESS, TaskStatus.SUSPENDED)
        }
        assert active == {"t2"}


# ===================================================================
# E9.4.4 -- FSMTurnState ledger writes
# ===================================================================


class TestFSMTurnStateLedgerWrites:
    """Verify enqueue_result/drain_results emit canonical events."""

    def test_enqueue_writes_weave_candidate(self) -> None:
        writer = _make_writer()
        ts = FSMTurnState()
        ts.set_ledger(writer)

        ts.enqueue_result(
            task_id="t1",
            result={"summary": "found 3 hotels"},
            envelope=_make_envelope(1),
        )

        entries = _entries(writer)
        assert len(entries) == 1
        assert entries[0].event_type == "conversation.weave.candidate"
        assert entries[0].payload["task_id"] == "t1"
        assert entries[0].payload["result_data"]["summary"] == "found 3 hotels"

    def test_drain_writes_weave_emitted(self) -> None:
        writer = _make_writer()
        ts = FSMTurnState()
        ts.set_ledger(writer)

        ts.enqueue_result("t1", {"data": "a"}, _make_envelope(1))
        ts.enqueue_result("t2", {"data": "b"}, _make_envelope(2))
        valid, expired = ts.drain_results()

        entries = _entries(writer)
        # 2 candidates + 1 emitted
        assert len(entries) == 3
        candidates = [e for e in entries if e.event_type == "conversation.weave.candidate"]
        emitted = [e for e in entries if e.event_type == "conversation.weave.emitted"]
        assert len(candidates) == 2
        assert len(emitted) == 1
        assert "t1" in emitted[0].payload["candidate_event_ids"]
        assert "t2" in emitted[0].payload["candidate_event_ids"]
        assert len(valid) == 2

    def test_no_ledger_no_writes(self) -> None:
        ts = FSMTurnState()
        ts.enqueue_result("t1", {"data": "x"}, _make_envelope(1))
        assert ts.has_pending_results

    def test_drain_empty_no_write(self) -> None:
        writer = _make_writer()
        ts = FSMTurnState()
        ts.set_ledger(writer)
        valid, expired = ts.drain_results()
        assert len(_entries(writer)) == 0
        assert valid == []


# ===================================================================
# E9.4.4 -- FSMTurnState.rebuild_from_projection()
# ===================================================================


class TestFSMTurnStateRebuild:
    """Verify rebuild_from_projection() restores pending results."""

    def test_rebuild_restores_pending(self) -> None:
        projected = deque(
            [
                {
                    "task_id": "t1",
                    "result": {"summary": "hello"},
                    "envelope_id": 0,
                    "parent_id": 0,
                    "queued_at_ns": 0,
                },
                {
                    "task_id": "t2",
                    "result": {"summary": "world"},
                    "envelope_id": 0,
                    "parent_id": 0,
                    "queued_at_ns": 0,
                },
            ]
        )
        ts = FSMTurnState()
        restored = ts.rebuild_from_projection(projected)

        assert restored == 2
        assert ts.has_pending_results
        assert ts.depth == 2

    def test_rebuild_clears_previous(self) -> None:
        ts = FSMTurnState()
        ts.pending_results.append({"task_id": "old"})

        projected = deque(
            [
                {
                    "task_id": "t1",
                    "result": {},
                    "envelope_id": 0,
                    "parent_id": 0,
                    "queued_at_ns": 0,
                },
            ]
        )
        ts.rebuild_from_projection(projected)

        assert ts.depth == 1
        assert ts.pending_results[0]["task_id"] == "t1"

    def test_rebuild_empty(self) -> None:
        ts = FSMTurnState()
        ts.pending_results.append({"task_id": "old"})
        restored = ts.rebuild_from_projection(deque())
        assert restored == 0
        assert not ts.has_pending_results

    def test_full_enqueue_crash_rebuild_flow(self) -> None:
        """End-to-end: enqueue -> crash -> project -> rebuild."""
        writer = _make_writer()
        ts1 = FSMTurnState()
        ts1.set_ledger(writer)

        ts1.enqueue_result("t1", {"summary": "result1"}, _make_envelope(1))
        ts1.enqueue_result("t2", {"summary": "result2"}, _make_envelope(2))

        # Simulate crash: project from ledger, rebuild new turn state
        entries = _entries(writer)
        projected = project_pending_results(entries)

        ts2 = FSMTurnState()
        restored = ts2.rebuild_from_projection(projected)

        assert restored == 2
        assert ts2.depth == 2
