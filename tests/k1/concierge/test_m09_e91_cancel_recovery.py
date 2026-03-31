"""
M9 E9.1.1-E9.1.4 -- CancellationHandler ledger integration + cancel state
projection + rebuild_from_events + late-completion dedup after crash recovery.

Validates:
    - CancellationHandler writes TaskCancelled to ledger BEFORE in-memory mutation.
    - project_cancel_state() correctly rebuilds (active, cancelled) from events.
    - rebuild_from_events() restores _tokens and _cancelled_tasks.
    - Late-completion dedup works after crash recovery (E9.1.4).
"""

from __future__ import annotations

import pytest

from k1.concierge.fsm.task_bridge import TaskBridge
from k1.concierge.ledger.projections import project_cancel_state
from k1.concierge.ledger.store import InMemoryLedgerStore
from k1.concierge.ledger.writer import LedgerWriter
from k1.concierge.protocols.cancel_handler import CancellationHandler

SESSION_ID = "test-session-m9-cancel"


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def cancel_env():
    """Create a ledger store + writer + bridge + cancel handler wired together."""
    store = InMemoryLedgerStore()
    writer = LedgerWriter(store, session_id=SESSION_ID)
    bridge = TaskBridge(ledger=writer)
    handler = CancellationHandler(ledger=writer)
    return store, writer, bridge, handler


# ------------------------------------------------------------------
# E9.1.1: CancellationHandler ledger writes
# ------------------------------------------------------------------


class TestCancelHandlerLedgerWrites:
    """CancellationHandler emits TaskCancelled to ledger before in-memory mutation."""

    def test_request_cancel_writes_event(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "book flight")
        handler.register_task("t1")
        handler.request_cancel("t1")
        entries = store.read_by_type(SESSION_ID, "task.cancelled")
        assert len(entries) == 1
        assert entries[0].payload["task_id"] == "t1"
        assert entries[0].payload["reason"] == "user_requested"

    @pytest.mark.asyncio
    async def test_cancel_task_async_writes_event(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "book flight")
        handler.register_task("t1")
        result = await handler.cancel_task("t1")
        assert result is True
        entries = store.read_by_type(SESSION_ID, "task.cancelled")
        assert len(entries) == 1

    def test_idempotent_cancel_no_duplicate_write(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "book flight")
        handler.register_task("t1")
        handler.request_cancel("t1")
        handler.request_cancel("t1")  # Second cancel is idempotent
        entries = store.read_by_type(SESSION_ID, "task.cancelled")
        assert len(entries) == 1  # Only one event

    def test_no_ledger_no_writes(self) -> None:
        handler = CancellationHandler()
        handler.register_task("t1")
        handler.request_cancel("t1")
        assert handler.is_cancelled("t1")


# ------------------------------------------------------------------
# E9.1.2: Cancel state projection
# ------------------------------------------------------------------


class TestCancelStateProjection:
    """project_cancel_state() correctly rebuilds from ledger events."""

    def test_empty_events(self) -> None:
        active, cancelled = project_cancel_state([])
        assert active == set()
        assert cancelled == set()

    def test_created_task_is_active(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        active, cancelled = project_cancel_state(store.read_all(SESSION_ID))
        assert "t1" in active
        assert "t1" not in cancelled

    def test_cancelled_task_in_cancelled_set(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        handler.register_task("t1")
        handler.request_cancel("t1")
        active, cancelled = project_cancel_state(store.read_all(SESSION_ID))
        assert "t1" in cancelled
        assert "t1" not in active

    def test_completed_task_not_active(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        bridge.complete_task("t1")
        active, cancelled = project_cancel_state(store.read_all(SESSION_ID))
        assert "t1" not in active
        assert "t1" not in cancelled

    def test_failed_task_not_active(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        bridge.fail_task("t1")
        active, cancelled = project_cancel_state(store.read_all(SESSION_ID))
        assert "t1" not in active

    def test_mixed_tasks(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        bridge.dispatch_task("t2", "a2")
        bridge.dispatch_task("t3", "a3")
        bridge.complete_task("t1")
        handler.register_task("t2")
        handler.request_cancel("t2")
        active, cancelled = project_cancel_state(store.read_all(SESSION_ID))
        assert "t1" not in active  # completed
        assert "t2" in cancelled
        assert "t3" in active


# ------------------------------------------------------------------
# E9.1.3: rebuild_from_events
# ------------------------------------------------------------------


class TestCancelRebuildFromEvents:
    """CancellationHandler.rebuild_from_events() restores state."""

    def test_rebuild_restores_cancelled_set(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        handler.register_task("t1")
        handler.request_cancel("t1")

        # Create fresh handler and rebuild
        handler2 = CancellationHandler()
        handler2.rebuild_from_events(store.read_all(SESSION_ID))
        assert handler2.is_cancelled("t1")

    def test_rebuild_restores_active_tokens(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        bridge.dispatch_task("t2", "a2")

        handler2 = CancellationHandler()
        handler2.rebuild_from_events(store.read_all(SESSION_ID))
        assert handler2.get_token("t1") is not None
        assert handler2.get_token("t2") is not None
        assert not handler2.get_token("t1").is_cancelled
        assert not handler2.get_token("t2").is_cancelled

    def test_rebuild_cancelled_tokens_are_marked(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        handler.register_task("t1")
        handler.request_cancel("t1")

        handler2 = CancellationHandler()
        handler2.rebuild_from_events(store.read_all(SESSION_ID))
        token = handler2.get_token("t1")
        assert token is not None
        assert token.is_cancelled

    def test_rebuild_completed_tasks_not_active(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "a1")
        bridge.complete_task("t1")

        handler2 = CancellationHandler()
        handler2.rebuild_from_events(store.read_all(SESSION_ID))
        # t1 completed -- not in active tokens, not in cancelled
        assert handler2.get_token("t1") is None
        assert not handler2.is_cancelled("t1")


# ------------------------------------------------------------------
# E9.1.4: Late-completion dedup after crash recovery
# ------------------------------------------------------------------


class TestLateCancelDedupAfterRecovery:
    """After crash recovery, late completions for cancelled tasks are correctly deduped."""

    def test_late_completion_detected_after_rebuild(self, cancel_env) -> None:
        """E9.1.4 core scenario:
        1. Dispatch T1
        2. User cancels T1
        3. Process crashes
        4. Restart: rebuild from ledger
        5. T1 completes in Back (late)
        6. FSM checks is_cancelled(T1) -> True -> correct dedup
        """
        store, writer, bridge, handler = cancel_env

        # Step 1-2: Normal operations
        bridge.dispatch_task("t1", "book flight")
        handler.register_task("t1")
        handler.request_cancel("t1")

        # Step 3: Crash -- destroy in-memory handler
        del handler

        # Step 4: Restart and rebuild from ledger
        handler_recovered = CancellationHandler()
        handler_recovered.rebuild_from_events(store.read_all(SESSION_ID))

        # Step 5-6: Late completion dedup
        assert handler_recovered.is_cancelled("t1")
        assert handler_recovered.handle_late_completion("t1") is True

    def test_non_cancelled_task_not_flagged(self, cancel_env) -> None:
        store, writer, bridge, handler = cancel_env
        bridge.dispatch_task("t1", "book flight")

        handler2 = CancellationHandler()
        handler2.rebuild_from_events(store.read_all(SESSION_ID))
        assert handler2.handle_late_completion("t1") is False

    def test_full_crash_recovery_cancel_flow(self, cancel_env) -> None:
        """Multi-task cancel + complete + crash + rebuild + verify."""
        store, writer, bridge, handler = cancel_env

        bridge.dispatch_task("t1", "a1")
        bridge.dispatch_task("t2", "a2")
        bridge.dispatch_task("t3", "a3")

        handler.register_task("t1")
        handler.register_task("t2")
        handler.register_task("t3")

        handler.request_cancel("t1")
        bridge.complete_task("t2")

        # Crash
        del handler

        # Recovery
        handler_r = CancellationHandler()
        handler_r.rebuild_from_events(store.read_all(SESSION_ID))

        assert handler_r.is_cancelled("t1")
        assert not handler_r.is_cancelled("t2")  # completed, not cancelled
        assert not handler_r.is_cancelled("t3")
        assert handler_r.get_token("t3") is not None  # t3 still active
        assert not handler_r.get_token("t3").is_cancelled
