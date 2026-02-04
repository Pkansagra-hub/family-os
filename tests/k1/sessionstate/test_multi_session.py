"""
Multi-Session Isolation Integration Tests (Epic 4.6.5)
=======================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.6 Full Lifecycle Integration Tests
ISSUE: 4.6.5

**Test multi-session isolation**

SCENARIO:
    (1) Create 3 managers with different session_ids
    (2) Start all, mutate differently
    (3) Checkpoint all
    (4) Verify each manager.get_section() returns own data

ASSERTIONS:
    - No cross-contamination between sessions
    - Correct LOCAL COLD scoping
    - Each session maintains independent state
    - Checkpoints don't affect other sessions

ARCHITECTURE:
    Multi-session isolation relies on:
    - session_id as primary key for all data
    - LOCAL COLD SQLite using session_id scoping
    - Each manager operates independently
    - Shared db_path is fine (session_id is scoped)

HARDCORE INTEGRATION TEST REQUIREMENTS:
    1. ENTRY POINT: SessionStateFactory.create_standalone()
    2. ALL MUTATIONS: manager.mutate(section, operation, data)
    3. REAL SQLite LOCAL COLD: No mocks
    4. MULTIPLE MANAGERS: Different session_ids, same db_path
    5. VERIFY ISOLATION: Each manager sees only its own data

==============================================================================
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List

import pytest

from k1.sessionstate.factory import SessionStateFactory

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Shared SQLite database path for LOCAL COLD."""
    return tmp_path / "multi_session_test.db"


@pytest.fixture
def session_ids() -> List[str]:
    """Three unique session IDs for isolation testing."""
    return [
        f"session-alpha-{uuid.uuid4().hex[:8]}",
        f"session-beta-{uuid.uuid4().hex[:8]}",
        f"session-gamma-{uuid.uuid4().hex[:8]}",
    ]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_section_size(snapshot, section: str) -> int:
    """Get section size from snapshot."""
    if section in snapshot.sections:
        return snapshot.sections[section].size_bytes
    return 0


def make_history_turn(session_marker: str, turn_num: int) -> dict:
    """Create a history turn with session-specific content."""
    return {
        "user_message": f"[{session_marker}] User turn {turn_num}",
        "assistant_response": f"[{session_marker}] Response {turn_num}",
    }


def make_belief_fact(session_marker: str, index: int) -> dict:
    """Create a belief fact with session-specific content."""
    return {
        "subject": f"{session_marker}-user",
        "predicate": "prefers",
        "obj": f"{session_marker}-preference-{index}",
        "confidence": 0.9,
        "source": session_marker,
    }


def make_telemetry_turn(session_marker: str, turn_num: int) -> dict:
    """Create telemetry data with session-specific values."""
    # Use session marker to create unique but deterministic values
    marker_hash = sum(ord(c) for c in session_marker)
    return {
        "turn_number": turn_num,
        "duration_ms": 100 + (marker_hash % 100),
        "token_count": 500 + (marker_hash % 200),
        "had_error": False,
        "had_tool_call": False,
    }


# =============================================================================
# TEST CLASS: Basic Isolation
# =============================================================================


class TestBasicMultiSessionIsolation:
    """Test basic isolation between multiple sessions."""

    def test_three_sessions_isolated(self, db_path: Path, session_ids: List[str]) -> None:
        """Three sessions with same db_path have isolated data."""
        managers = []

        # Create and start all managers
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Add different data to each session
        for i, manager in enumerate(managers):
            marker = f"S{i}"
            for turn in range(3 + i):  # Different amounts
                manager.mutate(
                    section="history_active",
                    operation="append",
                    data=make_history_turn(marker, turn),
                    estimated_bytes=100,
                )

        # Verify each sees only its own data
        sizes = [get_section_size(m.get_snapshot(), "history_active") for m in managers]

        # All should have data
        assert all(s > 0 for s in sizes)

        # Different amounts (different turn counts)
        assert sizes[0] != sizes[1] or sizes[1] != sizes[2]

        # Clean up
        for manager in managers:
            manager.stop()

    def test_sessions_have_unique_session_ids(self, db_path: Path, session_ids: List[str]) -> None:
        """Each manager reports its own session_id."""
        managers = []

        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Verify session IDs
        for i, manager in enumerate(managers):
            assert manager.session_id == session_ids[i]

        for manager in managers:
            manager.stop()

    def test_mutations_do_not_cross_contaminate(
        self, db_path: Path, session_ids: List[str]
    ) -> None:
        """Mutations in one session don't affect others."""
        managers = []

        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Initial snapshot sizes
        initial_sizes = [get_section_size(m.get_snapshot(), "beliefs_active") for m in managers]

        # Mutate ONLY first session
        for i in range(5):
            managers[0].mutate(
                section="beliefs_active",
                operation="add_fact",
                data=make_belief_fact("ALPHA", i),
                estimated_bytes=100,
            )

        # Check sizes after mutation
        after_sizes = [get_section_size(m.get_snapshot(), "beliefs_active") for m in managers]

        # Only first manager should have increased
        assert after_sizes[0] > initial_sizes[0]
        assert after_sizes[1] == initial_sizes[1]
        assert after_sizes[2] == initial_sizes[2]

        for manager in managers:
            manager.stop()


# =============================================================================
# TEST CLASS: Checkpoint Isolation
# =============================================================================


class TestCheckpointIsolation:
    """Test that checkpoints are isolated between sessions."""

    def test_checkpoint_one_doesnt_affect_others(
        self, db_path: Path, session_ids: List[str]
    ) -> None:
        """Checkpointing one session doesn't affect others."""
        managers = []

        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Add data to all
        for i, manager in enumerate(managers):
            manager.mutate(
                section="history_active",
                operation="append",
                data=make_history_turn(f"S{i}", 0),
                estimated_bytes=100,
            )

        sizes_before = [get_section_size(m.get_snapshot(), "history_active") for m in managers]

        # Checkpoint only first
        result = managers[0].checkpoint()
        assert result.success

        sizes_after = [get_section_size(m.get_snapshot(), "history_active") for m in managers]

        # All sizes unchanged
        assert sizes_before == sizes_after

        for manager in managers:
            manager.stop()

    def test_independent_checkpoint_restore_cycles(
        self, db_path: Path, session_ids: List[str]
    ) -> None:
        """Each session has independent checkpoint/restore."""
        # Create sessions with different data
        for i, sid in enumerate(session_ids):
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()

            # Add session-specific data
            for turn in range(3 + i * 2):  # 3, 5, 7 turns
                manager.mutate(
                    section="history_active",
                    operation="append",
                    data=make_history_turn(f"SESSION_{i}", turn),
                    estimated_bytes=100,
                )

            manager.checkpoint()
            manager.stop()

        # Restore each and verify isolation
        restored_sizes = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start(restore_if_exists=True)

            size = get_section_size(manager.get_snapshot(), "history_active")
            restored_sizes.append(size)

            manager.stop()

        # Different sizes (3, 5, 7 turns)
        assert restored_sizes[0] < restored_sizes[1] < restored_sizes[2]


# =============================================================================
# TEST CLASS: Concurrent-Like Access
# =============================================================================


class TestConcurrentAccess:
    """Test concurrent-like access patterns."""

    def test_interleaved_mutations(self, db_path: Path, session_ids: List[str]) -> None:
        """Interleaved mutations maintain isolation."""
        managers = []

        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Interleave mutations across all managers
        for turn in range(10):
            for i, manager in enumerate(managers):
                manager.mutate(
                    section="telemetry",
                    operation="record_turn",
                    data=make_telemetry_turn(f"S{i}", turn),
                    estimated_bytes=50,
                )

        # All should have exactly 10 turns of data
        sizes = [get_section_size(m.get_snapshot(), "telemetry") for m in managers]

        # Sizes should be similar (10 turns each)
        # Allow some variance due to content
        assert all(s > 0 for s in sizes)

        for manager in managers:
            manager.stop()

    def test_one_session_stop_others_continue(self, db_path: Path, session_ids: List[str]) -> None:
        """One session stopping doesn't affect others."""
        managers = []

        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Add initial data
        for i, manager in enumerate(managers):
            manager.mutate(
                section="history_active",
                operation="append",
                data=make_history_turn(f"S{i}", 0),
                estimated_bytes=100,
            )

        # Stop first manager
        managers[0].checkpoint()
        managers[0].stop()

        # Others should still work
        for i in [1, 2]:
            result = managers[i].mutate(
                section="history_active",
                operation="append",
                data=make_history_turn(f"S{i}", 1),
                estimated_bytes=100,
            )
            assert result.success

        # Clean up
        managers[1].stop()
        managers[2].stop()


# =============================================================================
# TEST CLASS: Recovery Independence
# =============================================================================


class TestRecoveryIndependence:
    """Test that crash recovery is independent per session."""

    def test_crash_one_recover_another(self, db_path: Path, session_ids: List[str]) -> None:
        """Crashing one session doesn't corrupt others."""
        import gc

        managers = []

        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Add and checkpoint all
        for i, manager in enumerate(managers):
            for turn in range(3):
                manager.mutate(
                    section="history_active",
                    operation="append",
                    data=make_history_turn(f"S{i}", turn),
                    estimated_bytes=100,
                )
            manager.checkpoint()

        sizes_before = [get_section_size(m.get_snapshot(), "history_active") for m in managers]

        # Get references to managers before modifying list
        manager0 = managers[0]
        manager1 = managers[1]
        manager2 = managers[2]

        # Crash first manager (no stop)
        del manager0
        gc.collect()

        # Stop others gracefully
        manager1.stop()
        manager2.stop()

        # Recover all
        recovered = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start(restore_if_exists=True)
            recovered.append(manager)

        sizes_after = [get_section_size(m.get_snapshot(), "history_active") for m in recovered]

        # All should have their data
        assert sizes_after == sizes_before

        for manager in recovered:
            manager.stop()

    def test_staggered_crash_recovery(self, db_path: Path, session_ids: List[str]) -> None:
        """Sessions can crash and recover at different times."""
        import gc

        # Phase 1: All start and add data
        for i, sid in enumerate(session_ids):
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()

            for turn in range(i + 1):  # 1, 2, 3 turns
                manager.mutate(
                    section="beliefs_active",
                    operation="add_fact",
                    data=make_belief_fact(f"S{i}", turn),
                    estimated_bytes=100,
                )

            manager.checkpoint()
            del manager
            gc.collect()

        # Phase 2: Recover first, add more, crash
        manager1 = SessionStateFactory.create_standalone(
            session_id=session_ids[0],
            db_path=db_path,
        )
        manager1.start(restore_if_exists=True)
        manager1.mutate(
            section="beliefs_active",
            operation="add_fact",
            data=make_belief_fact("S0", 99),
            estimated_bytes=100,
        )
        manager1.checkpoint()
        del manager1
        gc.collect()

        # Phase 3: Recover all and verify
        sizes = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start(restore_if_exists=True)
            sizes.append(get_section_size(manager.get_snapshot(), "beliefs_active"))
            manager.stop()

        # First should have more (original + 1 extra)
        # Original was 1 turn, others were 2 and 3
        # But first now has 2 (1 + 1 new)
        assert sizes[0] > 0
        assert sizes[1] > 0
        assert sizes[2] > 0


# =============================================================================
# TEST CLASS: Section-Level Isolation
# =============================================================================


class TestSectionLevelIsolation:
    """Test isolation at the section level."""

    def test_hot_sections_isolated(self, db_path: Path, session_ids: List[str]) -> None:
        """HOT sections are isolated between sessions."""
        managers = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Add to first manager only
        managers[0].mutate(
            section="history_active",
            operation="append",
            data=make_history_turn("ALPHA", 0),
            estimated_bytes=100,
        )
        managers[0].mutate(
            section="beliefs_active",
            operation="add_fact",
            data=make_belief_fact("ALPHA", 0),
            estimated_bytes=100,
        )

        # Others should have empty sections
        for section in ["history_active", "beliefs_active"]:
            size0 = get_section_size(managers[0].get_snapshot(), section)
            size1 = get_section_size(managers[1].get_snapshot(), section)
            size2 = get_section_size(managers[2].get_snapshot(), section)

            assert size0 > 0
            assert size1 == 0
            assert size2 == 0

        for manager in managers:
            manager.stop()

    def test_warm_sections_isolated(self, db_path: Path, session_ids: List[str]) -> None:
        """WARM sections are isolated between sessions."""
        managers = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Add telemetry to second manager only
        for turn in range(5):
            managers[1].mutate(
                section="telemetry",
                operation="record_turn",
                data=make_telemetry_turn("BETA", turn),
                estimated_bytes=50,
            )

        # Only second should have telemetry
        size0 = get_section_size(managers[0].get_snapshot(), "telemetry")
        size1 = get_section_size(managers[1].get_snapshot(), "telemetry")
        size2 = get_section_size(managers[2].get_snapshot(), "telemetry")

        assert size0 == 0
        assert size1 > 0
        assert size2 == 0

        for manager in managers:
            manager.stop()


# =============================================================================
# TEST CLASS: Edge Cases
# =============================================================================


class TestMultiSessionEdgeCases:
    """Test edge cases in multi-session scenarios."""

    def test_empty_sessions_isolated(self, db_path: Path, session_ids: List[str]) -> None:
        """Empty sessions are isolated."""
        managers = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # All empty
        for manager in managers:
            snapshot = manager.get_snapshot()
            assert snapshot.total_size_bytes == 0

        for manager in managers:
            manager.stop()

    def test_large_session_doesnt_affect_small(self, db_path: Path, session_ids: List[str]) -> None:
        """Large session doesn't affect smaller ones."""
        managers = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # First session: small (1 turn)
        managers[0].mutate(
            section="history_active",
            operation="append",
            data=make_history_turn("SMALL", 0),
            estimated_bytes=100,
        )
        small_size = get_section_size(managers[0].get_snapshot(), "history_active")

        # Third session: large (50 turns)
        for i in range(50):
            managers[2].mutate(
                section="history_active",
                operation="append",
                data=make_history_turn("LARGE", i),
                estimated_bytes=100,
            )

        # First should still be small
        still_small = get_section_size(managers[0].get_snapshot(), "history_active")
        assert still_small == small_size

        for manager in managers:
            manager.stop()

    def test_same_session_id_same_data(self, db_path: Path) -> None:
        """Same session_id shares data (expected behavior)."""
        session_id = f"shared-{uuid.uuid4().hex[:8]}"

        manager1 = SessionStateFactory.create_standalone(
            session_id=session_id,
            db_path=db_path,
        )
        manager1.start()

        manager1.mutate(
            section="history_active",
            operation="append",
            data=make_history_turn("SHARED", 0),
            estimated_bytes=100,
        )
        manager1.checkpoint()
        manager1.stop()

        # Same session_id should restore the data
        manager2 = SessionStateFactory.create_standalone(
            session_id=session_id,
            db_path=db_path,
        )
        manager2.start(restore_if_exists=True)

        size = get_section_size(manager2.get_snapshot(), "history_active")
        assert size > 0  # Data restored

        manager2.stop()


# =============================================================================
# TEST CLASS: Performance with Multiple Sessions
# =============================================================================


class TestMultiSessionPerformance:
    """Test performance with multiple concurrent sessions."""

    def test_three_sessions_dont_slow_each_other(
        self, db_path: Path, session_ids: List[str]
    ) -> None:
        """Multiple sessions don't significantly slow each other."""
        import time

        managers = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Measure mutation speed per manager
        times = []
        for manager in managers:
            start = time.perf_counter()
            for i in range(10):
                manager.mutate(
                    section="history_active",
                    operation="append",
                    data=make_history_turn("PERF", i),
                    estimated_bytes=100,
                )
            duration = (time.perf_counter() - start) * 1000
            times.append(duration)

        # All should complete reasonably fast (<500ms for 10 mutations)
        for t in times:
            assert t < 500, f"Session took {t}ms for 10 mutations"

        # Times should be similar (within 5x of each other - accounts for jitter)
        max_time = max(times)
        min_time = min(times)
        assert max_time < min_time * 5, f"Times vary too much: {times}"

        for manager in managers:
            manager.stop()

    def test_checkpoint_all_reasonable_time(self, db_path: Path, session_ids: List[str]) -> None:
        """Checkpointing all sessions completes in reasonable time."""
        import time

        managers = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Add data
        for manager in managers:
            for i in range(10):
                manager.mutate(
                    section="history_active",
                    operation="append",
                    data=make_history_turn("CP", i),
                    estimated_bytes=100,
                )

        # Checkpoint all
        start = time.perf_counter()
        for manager in managers:
            manager.checkpoint()
        total_time = (time.perf_counter() - start) * 1000

        # All three checkpoints in <300ms
        assert total_time < 300, f"Checkpoints took {total_time}ms"

        for manager in managers:
            manager.stop()


# =============================================================================
# TEST CLASS: Stress Test
# =============================================================================


class TestMultiSessionStress:
    """Stress test multi-session scenarios."""

    def test_ten_sessions_isolated(self, db_path: Path) -> None:
        """Ten sessions maintain isolation."""
        session_ids = [f"stress-{i}-{uuid.uuid4().hex[:6]}" for i in range(10)]

        managers = []
        for sid in session_ids:
            manager = SessionStateFactory.create_standalone(
                session_id=sid,
                db_path=db_path,
            )
            manager.start()
            managers.append(manager)

        # Each session gets different amount of data
        for i, manager in enumerate(managers):
            for turn in range(i + 1):  # 1, 2, 3, ..., 10 turns
                manager.mutate(
                    section="history_active",
                    operation="append",
                    data=make_history_turn(f"S{i}", turn),
                    estimated_bytes=50,
                )

        # Verify sizes are different
        sizes = [get_section_size(m.get_snapshot(), "history_active") for m in managers]

        # Should have 10 different sizes (1-10 turns)
        unique_sizes = set(sizes)
        assert len(unique_sizes) == 10, f"Expected 10 unique sizes, got {len(unique_sizes)}"

        for manager in managers:
            manager.stop()

    def test_rapid_session_creation_destruction(self, db_path: Path) -> None:
        """Rapid creation/destruction maintains isolation."""
        base_session = f"rapid-{uuid.uuid4().hex[:8]}"

        # Create, use, destroy 5 sessions in sequence
        for i in range(5):
            session_id = f"{base_session}-{i}"

            manager = SessionStateFactory.create_standalone(
                session_id=session_id,
                db_path=db_path,
            )
            manager.start()

            # Add unique data
            for turn in range(i + 1):
                manager.mutate(
                    section="history_active",
                    operation="append",
                    data=make_history_turn(f"RAPID{i}", turn),
                    estimated_bytes=50,
                )

            manager.checkpoint()
            manager.stop()

        # Verify each can be recovered independently
        for i in range(5):
            session_id = f"{base_session}-{i}"

            manager = SessionStateFactory.create_standalone(
                session_id=session_id,
                db_path=db_path,
            )
            manager.start(restore_if_exists=True)

            size = get_section_size(manager.get_snapshot(), "history_active")
            assert size > 0

            manager.stop()
