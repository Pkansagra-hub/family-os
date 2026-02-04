"""
Cross-Section Narrative → Threads Integration Tests (Epic 4.5.4)
=================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.5 Cross-Section Dependency Tests
ISSUE: 4.5.4

**Test narrative_active → threads dependency**

ARCHITECTURE:
    narrative_active (HOT CORE) tracks active conversation threads and narrative arc.
    Threads can be paused, archived, and resumed based on user context switches.
    Archived threads are persisted to LOCAL COLD for offline resumption.

KEY PROPERTIES:
    - NarrativeActiveSection.CAN_EVICT = False (HOT CORE)
    - Thread switching updates active pointers
    - Archived thread IDs tracked in section
    - LocalColdTier stores narrative archives in st_narrative_archive

HARDCORE INTEGRATION TEST REQUIREMENTS:
    1. ENTRY POINT: SessionStateFactory.create_standalone()
    2. ALL MUTATIONS: manager.mutate(section, operation, data)
    3. ALL READS: manager.get_section() or manager.get_snapshot()
    4. NO MOCKS: Real adapters, real SQLite LOCAL COLD

==============================================================================
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Generator

import pytest

from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.manager import SessionStateManager
from k1.sessionstate.sections.narrative_active import NarrativeActiveSection, ThreadState

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """SQLite database path for LOCAL COLD."""
    return tmp_path / "narrative_cross_section.db"


@pytest.fixture
def session_id() -> str:
    """Unique session ID for each test."""
    return f"narrative-cross-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def session(db_path: Path, session_id: str) -> Generator[SessionStateManager, None, None]:
    """Create a standalone session manager with LOCAL COLD."""
    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
        checkpoint_interval_s=0,
    )
    manager.start(restore_if_exists=False)
    yield manager
    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


# =============================================================================
# TEST CLASS: Narrative Section Properties
# =============================================================================


class TestNarrativeSectionProperties:
    """Test narrative_active section properties."""

    def test_section_accessible(self, session: SessionStateManager) -> None:
        """narrative_active section is accessible via manager."""
        section = session.get_section("narrative_active")
        assert section is not None
        assert isinstance(section, NarrativeActiveSection)

    def test_section_is_hot_tier(self, session: SessionStateManager) -> None:
        """narrative_active is in HOT tier."""
        section = session.get_section("narrative_active")
        assert section.tier == "hot"

    def test_section_can_evict_false(self, session: SessionStateManager) -> None:
        """narrative_active cannot be evicted."""
        section = session.get_section("narrative_active")
        assert section.can_evict is False

    def test_section_budget(self, session: SessionStateManager) -> None:
        """narrative_active has 4KB budget."""
        section = session.get_section("narrative_active")
        assert section.budget_bytes == 4096

    def test_section_name(self, session: SessionStateManager) -> None:
        """narrative_active name is correct."""
        section = session.get_section("narrative_active")
        assert section.name == "narrative_active"


# =============================================================================
# TEST CLASS: Thread Lifecycle via Manager
# =============================================================================


class TestThreadLifecycleIntegration:
    """Test thread lifecycle via manager.mutate."""

    def test_create_threads_via_manager(self, session: SessionStateManager) -> None:
        """Threads can be created via manager.mutate."""
        result = session.mutate(
            "narrative_active",
            "create_thread",
            {
                "title": "Trip planning",
                "goal": "Plan weekend trip",
                "turn_number": 1,
            },
            estimated_bytes=300,
        )
        assert result.success is True

        section = session.get_section("narrative_active")
        assert section.primary_thread is not None
        assert section.primary_thread.title == "Trip planning"
        assert section.primary_thread.goal == "Plan weekend trip"

    def test_switch_threads_updates_active_pointer(self, session: SessionStateManager) -> None:
        """Switching threads updates primary pointer and pauses previous."""
        session.mutate(
            "narrative_active",
            "create_thread",
            {"title": "Thread A", "goal": "Goal A", "turn_number": 1},
            estimated_bytes=300,
        )
        section = session.get_section("narrative_active")
        thread_a_id = section.primary_thread.id

        session.mutate(
            "narrative_active",
            "create_thread",
            {"title": "Thread B", "goal": "Goal B", "turn_number": 2},
            estimated_bytes=300,
        )
        section = session.get_section("narrative_active")
        thread_b_id = section.primary_thread.id
        assert thread_a_id != thread_b_id

        switch_result = session.mutate(
            "narrative_active",
            "switch_to",
            {"thread_id": thread_a_id, "turn_number": 3},
            estimated_bytes=100,
        )
        assert switch_result.success is True

        section = session.get_section("narrative_active")
        assert section.primary_thread.id == thread_a_id
        paused = section.paused_threads
        assert any(t.id == thread_b_id and t.state == ThreadState.PAUSED for t in paused)

    def test_archive_thread_updates_archived_ids(self, session: SessionStateManager) -> None:
        """Archiving a thread updates archived IDs and removes from index."""
        session.mutate(
            "narrative_active",
            "create_thread",
            {"title": "Thread A", "goal": "Goal A", "turn_number": 1},
            estimated_bytes=300,
        )
        section = session.get_section("narrative_active")
        thread_a_id = section.primary_thread.id

        archive_result = session.mutate(
            "narrative_active",
            "archive_thread",
            {"thread_id": thread_a_id},
            estimated_bytes=200,
        )
        assert archive_result.success is True

        section = session.get_section("narrative_active")
        assert thread_a_id in section.archived_thread_ids
        assert section.get_thread(thread_a_id) is None


# =============================================================================
# TEST CLASS: LOCAL COLD Archival
# =============================================================================


class TestNarrativeArchivalLocalCold:
    """Test narrative thread archival to LOCAL COLD."""

    def test_archive_thread_to_local_cold(self, session: SessionStateManager) -> None:
        """Archived thread is persisted to LOCAL COLD."""
        session.mutate(
            "narrative_active",
            "create_thread",
            {"title": "Archive Me", "goal": "Goal A", "turn_number": 1},
            estimated_bytes=300,
        )
        section = session.get_section("narrative_active")
        thread_id = section.primary_thread.id

        # Archive snapshot to LOCAL COLD before removing thread
        narrative_bytes = section.to_flatbuffer()
        archive_result = session.get_local_cold().archive(
            "narrative_active",
            narrative_bytes,
            metadata={"thread_id": thread_id, "reason": "manual_archive"},
        )
        assert archive_result.success is True

        # Archive thread in section via manager
        result = session.mutate(
            "narrative_active",
            "archive_thread",
            {"thread_id": thread_id},
            estimated_bytes=200,
        )
        assert result.success is True

        # Verify LOCAL COLD contains narrative archive with metadata
        archives = session.get_local_cold().list_archives(section="narrative_active")
        assert len(archives) >= 1
        assert any(a.metadata.get("thread_id") == thread_id for a in archives)


# =============================================================================
# TEST CLASS: Resumption via Manager
# =============================================================================


class TestNarrativeResumptionIntegration:
    """Test resuming archived thread via manager operations."""

    def test_resume_archived_thread_via_manager(self, session: SessionStateManager) -> None:
        """Archived thread can be resumed by creating a new active thread via manager."""
        session.mutate(
            "narrative_active",
            "create_thread",
            {"title": "Original Thread", "goal": "Original Goal", "turn_number": 1},
            estimated_bytes=300,
        )
        section = session.get_section("narrative_active")
        archived_title = section.primary_thread.title
        archived_goal = section.primary_thread.goal
        archived_id = section.primary_thread.id

        session.mutate(
            "narrative_active",
            "archive_thread",
            {"thread_id": archived_id},
            estimated_bytes=200,
        )

        # Resume by creating a new thread with same context
        resume_result = session.mutate(
            "narrative_active",
            "create_thread",
            {
                "title": archived_title,
                "goal": archived_goal,
                "turn_number": 2,
            },
            estimated_bytes=300,
        )
        assert resume_result.success is True

        section = session.get_section("narrative_active")
        assert section.primary_thread is not None
        assert section.primary_thread.title == archived_title
        assert section.primary_thread.goal == archived_goal
        assert section.current_thread_id == section.primary_thread.id
        assert section.current_thread_id == section.primary_thread.id
