"""
M1 E1.2.4 -- Ledger Replay Test: reconstruct session from ledger and verify.

Source: v3_milestones.md E1.2.4
Source: v3_whiteboard.md Section 9 (success criterion: "Replay of ledger
        reconstructs session behavior accurately")

Tests:
    1. Append canonical events to ledger writer with idempotency.
    2. Run projections on ledger event stream.
    3. Verify projected state matches expected state.
    4. Verify idempotency (re-append same event -> same seq, no dup).
    5. Verify projections are pure (same input -> same output).

This test exercises the full E1.2 stack:
    - LedgerWriter + InMemoryLedgerStore (E1.2.1)
    - project_history, project_task_states, project_pending_results (E1.2.2)
    - Canonical event construction via _build_canonical_event (E1.2.3)

The test uses scripted canonical events (not the full controller) to
isolate ledger/projection behavior from FSM routing complexity.
"""

from __future__ import annotations

import uuid
from collections import deque
from typing import Any

import pytest

from poc.k1_poc.events.conversation import UserInputReceived
from poc.k1_poc.events.hitl import HILRequested, HILResolved, TaskResumed, TaskSuspended
from poc.k1_poc.events.task import TaskCancelled, TaskCompleted, TaskCreated, TaskFailed
from poc.k1_poc.events.weave import WeaveCandidateArrived, WeaveEmitted
from poc.k1_poc.ledger.projections import (
    project_history,
    project_pending_results,
    project_task_states,
)
from poc.k1_poc.ledger.store import InMemoryLedgerStore, LedgerEntry
from poc.k1_poc.ledger.writer import LedgerWriter
from poc.k1_poc.protocols.hitl_persistence import TaskStatus

# =========================================================================
# Helpers
# =========================================================================

SESSION_ID = "test-session-001"
CORRELATION_ID = "corr-001"


def _make_writer() -> LedgerWriter:
    """Create a LedgerWriter backed by InMemoryLedgerStore."""
    store = InMemoryLedgerStore()
    return LedgerWriter(store, session_id=SESSION_ID)


def _base_meta(**overrides: Any) -> dict[str, Any]:
    """Build common metadata kwargs for canonical event construction."""
    meta: dict[str, Any] = {
        "session_id": SESSION_ID,
        "correlation_id": CORRELATION_ID,
        "causation_id": "",
        "actor": "fsm",
    }
    meta.update(overrides)
    return meta


# =========================================================================
# E1.2.1 -- LedgerWriter + InMemoryLedgerStore tests
# =========================================================================


class TestLedgerStore:
    """Tests for InMemoryLedgerStore basic operations."""

    def test_append_assigns_monotonic_seq(self) -> None:
        store = InMemoryLedgerStore()
        e1 = LedgerEntry(
            seq=0,
            event_id="ev-1",
            event_type="task.created",
            session_id=SESSION_ID,
            payload={"task_id": "t1"},
            written_at_utc="2024-01-01T00:00:00+00:00",
        )
        e2 = LedgerEntry(
            seq=0,
            event_id="ev-2",
            event_type="task.completed",
            session_id=SESSION_ID,
            payload={"task_id": "t1"},
            written_at_utc="2024-01-01T00:00:01+00:00",
        )
        s1 = store.append(e1)
        s2 = store.append(e2)
        assert s1 == 1
        assert s2 == 2
        assert store.count() == 2

    def test_read_filters_by_session(self) -> None:
        store = InMemoryLedgerStore()
        e1 = LedgerEntry(
            seq=0,
            event_id="ev-1",
            event_type="task.created",
            session_id="session-A",
            payload={},
            written_at_utc="2024-01-01T00:00:00+00:00",
        )
        e2 = LedgerEntry(
            seq=0,
            event_id="ev-2",
            event_type="task.created",
            session_id="session-B",
            payload={},
            written_at_utc="2024-01-01T00:00:01+00:00",
        )
        store.append(e1)
        store.append(e2)
        result = store.read("session-A")
        assert len(result) == 1
        assert result[0].event_id == "ev-1"

    def test_read_by_type(self) -> None:
        store = InMemoryLedgerStore()
        for i, etype in enumerate(["task.created", "task.completed", "task.created"]):
            store.append(
                LedgerEntry(
                    seq=0,
                    event_id=f"ev-{i}",
                    event_type=etype,
                    session_id=SESSION_ID,
                    payload={},
                    written_at_utc="2024-01-01T00:00:00+00:00",
                )
            )
        result = store.read_by_type(SESSION_ID, "task.created")
        assert len(result) == 2

    def test_exists(self) -> None:
        store = InMemoryLedgerStore()
        store.append(
            LedgerEntry(
                seq=0,
                event_id="ev-1",
                event_type="test",
                session_id=SESSION_ID,
                payload={},
                written_at_utc="2024-01-01T00:00:00+00:00",
            )
        )
        assert store.exists("ev-1") is True
        assert store.exists("ev-999") is False

    def test_read_seq_range(self) -> None:
        store = InMemoryLedgerStore()
        for i in range(5):
            store.append(
                LedgerEntry(
                    seq=0,
                    event_id=f"ev-{i}",
                    event_type="test",
                    session_id=SESSION_ID,
                    payload={},
                    written_at_utc="2024-01-01T00:00:00+00:00",
                )
            )
        result = store.read(SESSION_ID, from_seq=2, to_seq=4)
        assert len(result) == 3
        assert [e.seq for e in result] == [2, 3, 4]


class TestLedgerWriter:
    """Tests for LedgerWriter with idempotency."""

    @pytest.mark.asyncio
    async def test_append_returns_seq(self) -> None:
        writer = _make_writer()
        event = UserInputReceived(text="hello", **_base_meta(actor="user"))
        seq = await writer.append(event)
        assert seq == 1
        assert writer.store.count() == 1

    @pytest.mark.asyncio
    async def test_idempotency_same_event_id(self) -> None:
        writer = _make_writer()
        event = UserInputReceived(text="hello", **_base_meta(actor="user"))
        s1 = await writer.append(event)
        s2 = await writer.append(event)  # Same event_id
        assert s1 == s2
        assert writer.store.count() == 1  # No duplicate

    @pytest.mark.asyncio
    async def test_different_events_get_different_seqs(self) -> None:
        writer = _make_writer()
        e1 = UserInputReceived(text="hello", **_base_meta(actor="user"))
        e2 = TaskCreated(action="search", task_id="t1", **_base_meta(actor="fsm"))
        s1 = await writer.append(e1)
        s2 = await writer.append(e2)
        assert s1 != s2
        assert writer.store.count() == 2

    def test_append_sync(self) -> None:
        writer = _make_writer()
        event = UserInputReceived(text="hello", **_base_meta(actor="user"))
        seq = writer.append_sync(event)
        assert seq == 1
        assert writer.store.count() == 1

    def test_append_sync_idempotency(self) -> None:
        writer = _make_writer()
        event = UserInputReceived(text="hello", **_base_meta(actor="user"))
        s1 = writer.append_sync(event)
        s2 = writer.append_sync(event)
        assert s1 == s2
        assert writer.store.count() == 1

    @pytest.mark.asyncio
    async def test_session_id_scoping(self) -> None:
        store = InMemoryLedgerStore()
        w1 = LedgerWriter(store, session_id="sess-A")
        w2 = LedgerWriter(store, session_id="sess-B")
        e1 = UserInputReceived(text="a", **_base_meta(actor="user"))
        e2 = UserInputReceived(text="b", **_base_meta(actor="user"))
        await w1.append(e1)
        await w2.append(e2)
        assert store.count("sess-A") == 1
        assert store.count("sess-B") == 1


# =========================================================================
# E1.2.2 -- Projection tests
# =========================================================================


def _scripted_session_events(writer: LedgerWriter) -> list[LedgerEntry]:
    """Append a scripted multi-turn session and return the ledger entries.

    Session flow:
        Turn 1: user_input -> task_created -> task_completed
        Turn 2: user_input -> task_created -> task_suspended ->
                 hil_requested -> hil_resolved -> task_resumed -> task_completed
    """
    meta = _base_meta

    # Turn 1: simple task
    t1_input_id = str(uuid.uuid4())
    writer.append_sync(
        UserInputReceived(
            event_id=t1_input_id,
            text="What is the weather?",
            **meta(actor="user"),
        )
    )
    t1_created_id = str(uuid.uuid4())
    writer.append_sync(
        TaskCreated(
            event_id=t1_created_id,
            action="check_weather",
            task_id="task-1",
            **meta(actor="fsm", causation_id=t1_input_id),
        )
    )
    t1_completed_id = str(uuid.uuid4())
    writer.append_sync(
        TaskCompleted(
            event_id=t1_completed_id,
            action="check_weather",
            result_data={"summary": "Sunny, 72F"},
            task_id="task-1",
            **meta(actor="back", causation_id=t1_created_id),
        )
    )

    # Turn 2: task with HITL cycle
    t2_input_id = str(uuid.uuid4())
    writer.append_sync(
        UserInputReceived(
            event_id=t2_input_id,
            text="Book a restaurant",
            **meta(actor="user"),
        )
    )
    t2_created_id = str(uuid.uuid4())
    writer.append_sync(
        TaskCreated(
            event_id=t2_created_id,
            action="book_restaurant",
            task_id="task-2",
            **meta(actor="fsm", causation_id=t2_input_id),
        )
    )
    hil_req_id = str(uuid.uuid4())
    writer.append_sync(
        TaskSuspended(
            event_id=str(uuid.uuid4()),
            task_id="task-2",
            suspension_type="clarification",
            hil_request_event_id=hil_req_id,
            suspension_count=1,
            **meta(actor="fsm", causation_id=t2_created_id),
        )
    )
    writer.append_sync(
        HILRequested(
            event_id=hil_req_id,
            task_id="task-2",
            hil_type="clarification",
            question="How many guests?",
            **meta(actor="fsm", causation_id=t2_created_id),
        )
    )
    hil_res_id = str(uuid.uuid4())
    writer.append_sync(
        HILResolved(
            event_id=hil_res_id,
            task_id="task-2",
            resolution={"answer": "4"},
            resolution_type="answered",
            raw_user_text="4 guests",
            **meta(actor="user", causation_id=hil_req_id),
        )
    )
    writer.append_sync(
        TaskResumed(
            event_id=str(uuid.uuid4()),
            task_id="task-2",
            hil_resolved_event_id=hil_res_id,
            resume_instruction="User said 4 guests",
            **meta(actor="fsm", causation_id=hil_res_id),
        )
    )
    t2_completed_id = str(uuid.uuid4())
    writer.append_sync(
        TaskCompleted(
            event_id=t2_completed_id,
            action="book_restaurant",
            result_data={"summary": "Reserved for 4 at 7pm"},
            task_id="task-2",
            **meta(actor="back", causation_id=t2_created_id),
        )
    )

    # Return all entries
    store = writer.store
    return store.read_all(SESSION_ID)


class TestProjectHistory:
    """Tests for project_history projection."""

    def test_scripted_session_produces_correct_history_count(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        history = project_history(entries)
        # Expected: user(1), task_dispatch(1), task_complete(1),
        #           user(2), task_dispatch(2), task_suspended, hil_request,
        #           hil_response, task_resumed, task_complete(2) = 10
        assert len(history) == 10

    def test_turn_numbers_increment_on_user_input(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        history = project_history(entries)
        turns = [h["turn"] for h in history]
        # First 3 entries are turn 1, rest are turn 2
        assert turns[:3] == [1, 1, 1]
        assert all(t == 2 for t in turns[3:])

    def test_entry_types_match_expected_sequence(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        history = project_history(entries)
        types = [h["type"] for h in history]
        expected = [
            "user",
            "task_dispatch",
            "task_complete",
            "user",
            "task_dispatch",
            "task_suspended",
            "hil_request",
            "hil_response",
            "task_resumed",
            "task_complete",
        ]
        assert types == expected

    def test_roles_match_expected(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        history = project_history(entries)
        roles = [h["role"] for h in history]
        expected = [
            "user",  # user input
            "system",  # task dispatch
            "assistant",  # task complete
            "user",  # user input
            "system",  # task dispatch
            "system",  # task suspended
            "system",  # hil request
            "user",  # hil response
            "system",  # task resumed
            "assistant",  # task complete
        ]
        assert roles == expected

    def test_user_input_text_preserved(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        history = project_history(entries)
        user_entries = [h for h in history if h["type"] == "user"]
        assert user_entries[0]["text"] == "What is the weather?"
        assert user_entries[1]["text"] == "Book a restaurant"

    def test_task_id_present_on_task_events(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        history = project_history(entries)
        task_entries = [h for h in history if "task_id" in h]
        assert all(h["task_id"] in ("task-1", "task-2") for h in task_entries)

    def test_empty_ledger_returns_empty_history(self) -> None:
        assert project_history([]) == []


class TestProjectTaskStates:
    """Tests for project_task_states projection."""

    def test_scripted_session_produces_two_tasks(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        states = project_task_states(entries)
        assert len(states) == 2
        assert "task-1" in states
        assert "task-2" in states

    def test_task1_is_completed(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        states = project_task_states(entries)
        t1 = states["task-1"]
        assert t1.status == TaskStatus.COMPLETED
        assert t1.action == "check_weather"

    def test_task2_is_completed_after_hitl(self) -> None:
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        states = project_task_states(entries)
        t2 = states["task-2"]
        assert t2.status == TaskStatus.COMPLETED
        assert t2.action == "book_restaurant"
        assert t2.hil_suspensions_count == 1
        assert t2.pending_hil is None  # Cleared after resume + complete

    def test_task_cancelled_state(self) -> None:
        writer = _make_writer()
        meta = _base_meta
        writer.append_sync(
            TaskCreated(
                action="doomed_task",
                task_id="task-x",
                **meta(actor="fsm"),
            )
        )
        writer.append_sync(
            TaskCancelled(
                task_id="task-x",
                reason="user_cancel",
                **meta(actor="fsm"),
            )
        )
        entries = writer.store.read_all(SESSION_ID)
        states = project_task_states(entries)
        tx = states["task-x"]
        assert tx.status == TaskStatus.CANCELLED
        assert tx.cancel_reason == "user_cancel"

    def test_task_failed_state(self) -> None:
        writer = _make_writer()
        meta = _base_meta
        writer.append_sync(
            TaskCreated(
                action="risky_task",
                task_id="task-f",
                **meta(actor="fsm"),
            )
        )
        writer.append_sync(
            TaskFailed(
                task_id="task-f",
                reason="timeout",
                **meta(actor="back"),
            )
        )
        entries = writer.store.read_all(SESSION_ID)
        states = project_task_states(entries)
        tf = states["task-f"]
        assert tf.status == TaskStatus.FAILED
        assert tf.cancel_reason == "timeout"

    def test_empty_ledger_returns_empty_states(self) -> None:
        assert project_task_states([]) == {}


class TestProjectPendingResults:
    """Tests for project_pending_results projection."""

    def test_candidate_without_emit_stays_pending(self) -> None:
        writer = _make_writer()
        meta = _base_meta
        cand_id = str(uuid.uuid4())
        writer.append_sync(
            WeaveCandidateArrived(
                event_id=cand_id,
                task_id="task-w1",
                task_description="search",
                result_data={"answer": "42"},
                completed_at_ns=1_000_000,
                **meta(actor="fsm"),
            )
        )
        entries = writer.store.read_all(SESSION_ID)
        pending = project_pending_results(entries)
        assert len(pending) == 1
        assert pending[0]["task_id"] == "task-w1"
        assert pending[0]["result"]["answer"] == "42"

    def test_emitted_candidate_is_removed(self) -> None:
        writer = _make_writer()
        meta = _base_meta
        cand_id = str(uuid.uuid4())
        writer.append_sync(
            WeaveCandidateArrived(
                event_id=cand_id,
                task_id="task-w1",
                result_data={"answer": "42"},
                **meta(actor="fsm"),
            )
        )
        writer.append_sync(
            WeaveEmitted(
                candidate_event_ids=[cand_id],
                response_text_preview="Here is your answer",
                **meta(actor="fsm"),
            )
        )
        entries = writer.store.read_all(SESSION_ID)
        pending = project_pending_results(entries)
        assert len(pending) == 0

    def test_partial_emit_leaves_unemitted_pending(self) -> None:
        writer = _make_writer()
        meta = _base_meta
        c1_id = str(uuid.uuid4())
        c2_id = str(uuid.uuid4())
        writer.append_sync(
            WeaveCandidateArrived(
                event_id=c1_id,
                task_id="task-w1",
                result_data={"a": 1},
                **meta(actor="fsm"),
            )
        )
        writer.append_sync(
            WeaveCandidateArrived(
                event_id=c2_id,
                task_id="task-w2",
                result_data={"b": 2},
                **meta(actor="fsm"),
            )
        )
        writer.append_sync(
            WeaveEmitted(
                candidate_event_ids=[c1_id],  # Only c1 emitted
                **meta(actor="fsm"),
            )
        )
        entries = writer.store.read_all(SESSION_ID)
        pending = project_pending_results(entries)
        assert len(pending) == 1
        assert pending[0]["task_id"] == "task-w2"

    def test_empty_ledger_returns_empty_deque(self) -> None:
        pending = project_pending_results([])
        assert isinstance(pending, deque)
        assert len(pending) == 0


# =========================================================================
# E1.2.4 -- Full replay: events -> projections -> verify match
# =========================================================================


class TestLedgerReplay:
    """Full replay test: verify projections reconstruct expected state."""

    def test_replay_matches_expected_history_shape(self) -> None:
        """Replay ledger events and verify history projection structure."""
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        history = project_history(entries)

        # Verify structure of every history entry
        for h in history:
            assert "turn" in h
            assert "type" in h
            assert "role" in h
            assert "text" in h
            assert "timestamp_ms" in h
            assert "source" in h

    def test_replay_task_lifecycle_completeness(self) -> None:
        """Replay ledger and verify all task states are terminal."""
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        states = project_task_states(entries)

        for task_id, state in states.items():
            assert (
                state.status == TaskStatus.COMPLETED
            ), f"Task {task_id} should be COMPLETED but is {state.status}"

    def test_replay_hitl_cycle_integrity(self) -> None:
        """Verify HITL cycle: suspended -> resumed -> completed."""
        writer = _make_writer()
        entries = _scripted_session_events(writer)

        # Verify task-2 went through HITL
        t2_events = [e for e in entries if e.payload.get("task_id") == "task-2"]
        t2_types = [e.event_type for e in t2_events]

        assert "task.created" in t2_types
        assert "task.suspended" in t2_types
        assert "task.resumed" in t2_types
        assert "task.completed" in t2_types

        # Verify ordering: created before suspended before resumed before completed
        created_idx = t2_types.index("task.created")
        suspended_idx = t2_types.index("task.suspended")
        resumed_idx = t2_types.index("task.resumed")
        completed_idx = t2_types.index("task.completed")
        assert created_idx < suspended_idx < resumed_idx < completed_idx

    def test_replay_no_pending_results_after_full_session(self) -> None:
        """Scripted session has no weave events so no pending results."""
        writer = _make_writer()
        entries = _scripted_session_events(writer)
        pending = project_pending_results(entries)
        assert len(pending) == 0

    def test_replay_with_weave_events(self) -> None:
        """Add weave events to session and verify pending results projection."""
        writer = _make_writer()
        meta = _base_meta

        # User input -> task -> complete -> candidate -> emit
        writer.append_sync(UserInputReceived(text="go", **meta(actor="user")))
        writer.append_sync(TaskCreated(action="search", task_id="t1", **meta(actor="fsm")))
        cand_id = str(uuid.uuid4())
        writer.append_sync(
            TaskCompleted(
                action="search",
                task_id="t1",
                result_data={"answer": "found it"},
                **meta(actor="back"),
            )
        )
        writer.append_sync(
            WeaveCandidateArrived(
                event_id=cand_id,
                task_id="t1",
                result_data={"answer": "found it"},
                **meta(actor="fsm"),
            )
        )
        writer.append_sync(
            WeaveEmitted(
                candidate_event_ids=[cand_id],
                response_text_preview="Found it!",
                **meta(actor="fsm"),
            )
        )

        entries = writer.store.read_all(SESSION_ID)

        # All projections should be consistent
        history = project_history(entries)
        states = project_task_states(entries)
        pending = project_pending_results(entries)

        assert len(history) > 0
        assert "t1" in states
        assert states["t1"].status == TaskStatus.COMPLETED
        assert len(pending) == 0  # Candidate was emitted

    def test_projection_purity(self) -> None:
        """Same input -> same output (pure function property)."""
        writer = _make_writer()
        entries = _scripted_session_events(writer)

        h1 = project_history(entries)
        h2 = project_history(entries)
        assert h1 == h2

        s1 = project_task_states(entries)
        s2 = project_task_states(entries)
        # Compare by task status (TaskStateEntry doesn't have __eq__)
        assert set(s1.keys()) == set(s2.keys())
        for k in s1:
            assert s1[k].status == s2[k].status
            assert s1[k].action == s2[k].action

    @pytest.mark.asyncio
    async def test_idempotent_replay_unchanged(self) -> None:
        """Re-appending events doesn't change ledger (idempotency)."""
        writer = _make_writer()
        events = _scripted_session_events(writer)
        count_before = writer.store.count()

        # Re-read and re-append every event (simulate retry)
        for entry in events:
            # Construct a minimal event with same event_id
            from poc.k1_poc.events.base import CanonicalEventMeta

            replay_event = CanonicalEventMeta(
                event_id=entry.event_id,
                event_type=entry.event_type,
                session_id=entry.session_id,
            )
            await writer.append(replay_event)

        assert writer.store.count() == count_before


# =========================================================================
# E1.2.3 -- Controller ledger integration (smoke test)
# =========================================================================


class TestControllerLedgerIntegration:
    """Verify controller _write_history emits to ledger when attached."""

    def test_write_history_emits_user_event_to_ledger(self) -> None:
        """Controller._write_history emits UserInputReceived when ledger set."""
        from collections import defaultdict

        from k1.bus.envelope import Envelope
        from poc.k1_poc.bus.builders import build_user_input
        from poc.k1_poc.fsm.controller import ConciergeController

        # Minimal recording bus/router
        class MinBus:
            def __init__(self) -> None:
                self._handlers: dict = defaultdict(list)
                self.published: list = []

            def subscribe(self, pattern: str, handler: Any) -> int:
                return 0

            def unsubscribe(self, handle: Any) -> None:
                pass

            def publish(self, envelope: Any) -> None:
                self.published.append(envelope)

        class MinRouter:
            def deliver(self, actor_id: str, envelope: Any) -> None:
                pass

            def register(self, actor_id: str, handler: Any) -> None:
                pass

        bus = MinBus()
        router = MinRouter()
        ctrl = ConciergeController(bus=bus, router=router)  # type: ignore[arg-type]

        # Attach ledger
        writer = _make_writer()
        ctrl.set_ledger(writer)

        # Create a user_input envelope for metadata
        env = build_user_input(payload={"text": "hi"}, parent_id=0)
        stamped = Envelope(
            topic=env.topic,
            priority=env.priority,
            envelope_id=1,
            sequence=0,
            cognitive_trace_id=env.cognitive_trace_id,
            session_id="test-sess",
            request_id=env.request_id,
            parent_id=0,
            created_ns=1_000_000,
            payload=env.payload,
            ttl_ms=env.ttl_ms,
            payload_format=env.payload_format,
        )

        # Call _write_history directly with entry_type="user"
        ctrl._write_history(
            entry_type="user",
            role="user",
            text="hi",
            source="user",
            envelope=stamped,
        )

        # Verify ledger received the event
        entries = writer.store.read_all()
        assert len(entries) == 1
        assert entries[0].event_type == "conversation.user_input.received"
        assert entries[0].payload["text"] == "hi"

    def test_write_history_without_ledger_no_error(self) -> None:
        """Controller._write_history works normally without ledger."""
        from collections import defaultdict

        from poc.k1_poc.fsm.controller import ConciergeController

        class MinBus:
            def __init__(self) -> None:
                self._handlers: dict = defaultdict(list)

            def subscribe(self, pattern: str, handler: Any) -> int:
                return 0

            def unsubscribe(self, handle: Any) -> None:
                pass

            def publish(self, envelope: Any) -> None:
                pass

        class MinRouter:
            def deliver(self, actor_id: str, envelope: Any) -> None:
                pass

            def register(self, actor_id: str, handler: Any) -> None:
                pass

        bus = MinBus()
        router = MinRouter()
        ctrl = ConciergeController(bus=bus, router=router)  # type: ignore[arg-type]

        # No ledger attached -- should not error
        ctrl._write_history(
            entry_type="user",
            role="user",
            text="test",
            source="user",
        )
        assert len(ctrl.history) == 1

    def test_write_history_unmapped_entry_type_no_ledger_write(self) -> None:
        """Entry types without canonical mapping don't write to ledger."""
        from collections import defaultdict

        from poc.k1_poc.fsm.controller import ConciergeController

        class MinBus:
            def __init__(self) -> None:
                self._handlers: dict = defaultdict(list)

            def subscribe(self, pattern: str, handler: Any) -> int:
                return 0

            def unsubscribe(self, handle: Any) -> None:
                pass

            def publish(self, envelope: Any) -> None:
                pass

        class MinRouter:
            def deliver(self, actor_id: str, envelope: Any) -> None:
                pass

            def register(self, actor_id: str, handler: Any) -> None:
                pass

        bus = MinBus()
        router = MinRouter()
        ctrl = ConciergeController(bus=bus, router=router)  # type: ignore[arg-type]

        writer = _make_writer()
        ctrl.set_ledger(writer)

        # "some_custom_type" has no canonical mapping
        ctrl._write_history(
            entry_type="some_custom_type",
            role="system",
            text="internal",
            source="fsm",
        )
        assert len(ctrl.history) == 1  # History still written
        assert writer.store.count() == 0  # No ledger entry
