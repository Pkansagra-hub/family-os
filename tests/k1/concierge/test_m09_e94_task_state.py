"""
M9 E9.4.1-E9.4.2 -- TaskBridge ledger integration + projection roundtrip tests.

Validates:
    - TaskBridge writes canonical events to ledger BEFORE in-memory mutation.
    - project_task_states() correctly rebuilds state from ledger events.
    - rebuild_from_projection() restores TaskBridge state.
    - Full roundtrip: dispatch -> ledger -> project -> rebuild == original.
"""

from __future__ import annotations

import pytest

from k1.concierge.fsm.task_bridge import TaskBridge
from k1.concierge.ledger.projections import project_task_states
from k1.concierge.ledger.store import InMemoryLedgerStore
from k1.concierge.ledger.writer import LedgerWriter
from k1.concierge.protocols.hitl_persistence import TaskStatus as HitlTaskStatus
from k1.sessionstate.sections.task_state import TaskStatus as SSTaskStatus

SESSION_ID = "test-session-m9"


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def ledger_env():
    """Create a ledger store + writer + bridge wired together."""
    store = InMemoryLedgerStore()
    writer = LedgerWriter(store, session_id=SESSION_ID)
    bridge = TaskBridge(ledger=writer)
    return store, writer, bridge


# ------------------------------------------------------------------
# E9.4.1: TaskBridge ledger writes
# ------------------------------------------------------------------


class TestTaskBridgeLedgerWrites:
    """TaskBridge emits canonical events to ledger before in-memory mutation."""

    def test_dispatch_writes_task_created(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        entries = store.read_all(SESSION_ID)
        assert len(entries) == 1
        assert entries[0].event_type == "task.created"
        assert entries[0].payload["task_id"] == "t1"
        assert entries[0].payload["action"] == "book flight"

    def test_activate_writes_task_progressed(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.activate_task("t1")
        entries = store.read_all(SESSION_ID)
        assert len(entries) == 2
        assert entries[1].event_type == "task.progressed"
        assert entries[1].payload["task_id"] == "t1"

    def test_suspend_writes_task_suspended(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.activate_task("t1")
        bridge.suspend_task("t1")
        entries = store.read_all(SESSION_ID)
        assert len(entries) == 3
        assert entries[2].event_type == "task.suspended"
        assert entries[2].payload["task_id"] == "t1"
        assert entries[2].payload["suspension_count"] == 1

    def test_resume_writes_task_resumed(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.activate_task("t1")
        bridge.suspend_task("t1")
        bridge.resume_task("t1")
        entries = store.read_all(SESSION_ID)
        assert len(entries) == 4
        assert entries[3].event_type == "task.resumed"

    def test_complete_writes_task_completed(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.complete_task("t1", result_data={"summary": "booked"})
        entries = store.read_all(SESSION_ID)
        assert len(entries) == 2
        assert entries[1].event_type == "task.completed"
        assert entries[1].payload["result_data"] == {"summary": "booked"}

    def test_fail_writes_task_failed(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.fail_task("t1", reason="timeout")
        entries = store.read_all(SESSION_ID)
        assert len(entries) == 2
        assert entries[1].event_type == "task.failed"
        assert entries[1].payload["reason"] == "timeout"

    def test_cancel_writes_task_cancelled(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.cancel_task("t1", reason="user_requested")
        entries = store.read_all(SESSION_ID)
        assert len(entries) == 2
        assert entries[1].event_type == "task.cancelled"
        assert entries[1].payload["reason"] == "user_requested"

    def test_no_ledger_no_writes(self) -> None:
        """Without ledger, TaskBridge works as before (no writes)."""
        bridge = TaskBridge()
        bridge.dispatch_task("t1", "book flight")
        bridge.complete_task("t1")
        # No crash -- just no ledger writes

    def test_counters_correct_after_lifecycle(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "a1")
        bridge.dispatch_task("t2", "a2")
        bridge.dispatch_task("t3", "a3")
        bridge.complete_task("t1")
        bridge.fail_task("t2")
        bridge.cancel_task("t3")
        assert bridge.total_dispatched == 3
        assert bridge.total_completed == 1
        assert bridge.total_failed == 1
        assert bridge.total_cancelled == 1


# ------------------------------------------------------------------
# E9.4.2: Projection roundtrip
# ------------------------------------------------------------------


class TestTaskStateProjectionRoundtrip:
    """project_task_states() correctly rebuilds from ledger events."""

    def test_dispatch_projects_dispatched(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        projected = project_task_states(store.read_all(SESSION_ID))
        assert "t1" in projected
        assert projected["t1"].status == HitlTaskStatus.DISPATCHED
        assert projected["t1"].action == "book flight"

    def test_full_lifecycle_roundtrip(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.activate_task("t1")
        bridge.complete_task("t1")
        projected = project_task_states(store.read_all(SESSION_ID))
        assert projected["t1"].status == HitlTaskStatus.COMPLETED

    def test_cancel_lifecycle_roundtrip(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.cancel_task("t1")
        projected = project_task_states(store.read_all(SESSION_ID))
        assert projected["t1"].status == HitlTaskStatus.CANCELLED

    def test_suspend_resume_roundtrip(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "book flight")
        bridge.activate_task("t1")
        bridge.suspend_task("t1")
        projected = project_task_states(store.read_all(SESSION_ID))
        assert projected["t1"].status == HitlTaskStatus.SUSPENDED
        bridge.resume_task("t1")
        projected = project_task_states(store.read_all(SESSION_ID))
        assert projected["t1"].status == HitlTaskStatus.IN_PROGRESS

    def test_multi_task_projection(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "a1")
        bridge.dispatch_task("t2", "a2")
        bridge.dispatch_task("t3", "a3")
        bridge.complete_task("t1")
        bridge.fail_task("t2")
        projected = project_task_states(store.read_all(SESSION_ID))
        assert projected["t1"].status == HitlTaskStatus.COMPLETED
        assert projected["t2"].status == HitlTaskStatus.FAILED
        assert projected["t3"].status == HitlTaskStatus.DISPATCHED


# ------------------------------------------------------------------
# E9.4.1: Rebuild from projection
# ------------------------------------------------------------------


class TestRebuildFromProjection:
    """TaskBridge.rebuild_from_projection() restores state."""

    def test_rebuild_restores_tasks(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "a1")
        bridge.dispatch_task("t2", "a2")
        bridge.complete_task("t1")

        # Project from ledger
        projected = project_task_states(store.read_all(SESSION_ID))

        # Create a fresh bridge and rebuild
        bridge2 = TaskBridge()
        count = bridge2.rebuild_from_projection(projected)
        assert count == 2
        assert bridge2.get_task("t1").status == SSTaskStatus.COMPLETED
        assert bridge2.get_task("t2").status == SSTaskStatus.DISPATCHED

    def test_rebuild_restores_counters(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "a1")
        bridge.dispatch_task("t2", "a2")
        bridge.dispatch_task("t3", "a3")
        bridge.complete_task("t1")
        bridge.fail_task("t2")
        bridge.cancel_task("t3")

        projected = project_task_states(store.read_all(SESSION_ID))
        bridge2 = TaskBridge()
        bridge2.rebuild_from_projection(projected)
        assert bridge2.total_dispatched == 3
        assert bridge2.total_completed == 1
        assert bridge2.total_failed == 1
        assert bridge2.total_cancelled == 1

    def test_rebuild_clears_previous_state(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "a1")

        # Bridge2 already has some tasks
        bridge2 = TaskBridge()
        bridge2.dispatch_task("old-task", "old-action")

        projected = project_task_states(store.read_all(SESSION_ID))
        bridge2.rebuild_from_projection(projected)
        assert bridge2.get_task("old-task") is None
        assert bridge2.get_task("t1") is not None

    def test_rebuild_suspended_with_hil_fields(self, ledger_env) -> None:
        store, writer, bridge = ledger_env
        bridge.dispatch_task("t1", "a1")
        bridge.activate_task("t1")
        bridge.suspend_task("t1")

        projected = project_task_states(store.read_all(SESSION_ID))
        assert projected["t1"].status == HitlTaskStatus.SUSPENDED

        bridge2 = TaskBridge()
        bridge2.rebuild_from_projection(projected)
        rebuilt = bridge2.get_task("t1")
        assert rebuilt is not None
        assert rebuilt.status == SSTaskStatus.SUSPENDED

    def test_full_crash_recovery_simulation(self, ledger_env) -> None:
        """Simulate crash recovery: write -> project -> rebuild -> verify."""
        store, writer, bridge = ledger_env

        # Phase 1: Normal operations
        bridge.dispatch_task("t1", "search hotels")
        bridge.dispatch_task("t2", "book flight")
        bridge.activate_task("t1")
        bridge.suspend_task("t1")  # HITL
        bridge.complete_task("t2")

        # Phase 2: Crash -- destroy in-memory state
        del bridge

        # Phase 3: Recovery from ledger
        entries = store.read_all(SESSION_ID)
        projected = project_task_states(entries)
        bridge_recovered = TaskBridge()
        bridge_recovered.rebuild_from_projection(projected)

        # Verify
        t1 = bridge_recovered.get_task("t1")
        t2 = bridge_recovered.get_task("t2")
        assert t1 is not None
        assert t1.status == SSTaskStatus.SUSPENDED
        assert t2 is not None
        assert t2.status == SSTaskStatus.COMPLETED
        assert bridge_recovered.total_dispatched == 2
        assert bridge_recovered.total_completed == 1
