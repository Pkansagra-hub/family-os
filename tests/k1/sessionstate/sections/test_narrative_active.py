"""
Tests for NarrativeActiveSection
=================================

Comprehensive test suite for the NarrativeActiveSection class.
Tests thread management, arc tracking, FlatBuffer serialization, and apply operations.

Test coverage:
- Initialization and properties
- ISection protocol compliance
- Thread CRUD operations (create, read, update, delete)
- Thread state transitions (active, paused, resolved, archived)
- Thread switching and resumption
- Narrative arc position tracking
- Arc phase boundaries
- FlatBuffer serialization round-trip
- Apply operations for MutationGuard pattern
- Edge cases and limits
- Factory function
"""

import time

import pytest

from k1.sessionstate.sections.narrative_active import (
    MAX_PAUSED_THREADS,
    ArcPosition,
    ConversationThread,
    NarrativeActiveSection,
    NarrativeArc,
    ThreadState,
    create_narrative_active_section,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def section() -> NarrativeActiveSection:
    """Create a fresh NarrativeActiveSection."""
    return NarrativeActiveSection(session_id="test-session-123")


@pytest.fixture
def populated_section() -> NarrativeActiveSection:
    """Create a section with threads."""
    section = NarrativeActiveSection(session_id="test-session-populated")
    section.create_thread(
        title="Weather discussion",
        goal="Get weather forecast",
        turn_number=1,
        related_entities=["entity-1", "entity-2"],
        related_intents=["weather.query"],
    )
    return section


@pytest.fixture
def multi_thread_section() -> NarrativeActiveSection:
    """Create a section with multiple threads."""
    section = NarrativeActiveSection(session_id="test-session-multi")
    section.create_thread(
        title="Thread 1",
        goal="Goal 1",
        turn_number=1,
    )
    section.create_thread(
        title="Thread 2",
        goal="Goal 2",
        turn_number=5,
    )
    section.create_thread(
        title="Thread 3",
        goal="Goal 3",
        turn_number=10,
        auto_switch=False,  # This one stays paused
    )
    return section


# =============================================================================
# Initialization Tests
# =============================================================================


class TestNarrativeActiveSectionInit:
    """Test initialization behavior."""

    def test_init_with_session_id(self):
        """Should use provided session ID."""
        section = NarrativeActiveSection(session_id="my-session")
        assert section.session_id == "my-session"

    def test_init_generates_session_id(self):
        """Should generate session ID if not provided."""
        section = NarrativeActiveSection()
        assert section.session_id
        assert len(section.session_id) == 36  # UUID format

    def test_init_default_state(self):
        """Should initialize with default values."""
        section = NarrativeActiveSection()
        assert section.primary_thread is None
        assert section.paused_threads == []
        assert section.archived_thread_ids == []
        assert section.total_threads_session == 0
        assert section.current_turn == 0

    def test_init_default_arc(self):
        """Should initialize with default arc."""
        section = NarrativeActiveSection()
        assert section.arc_position == ArcPosition.EXPOSITION
        assert section.arc_progress == 0.0

    def test_init_schema_version(self):
        """Should use default schema version."""
        section = NarrativeActiveSection()
        assert section.schema_version == "1.0.0"


# =============================================================================
# ISection Protocol Tests
# =============================================================================


class TestISectionProtocol:
    """Test ISection protocol compliance."""

    def test_name(self, section):
        """Should return correct name."""
        assert section.name == "narrative_active"

    def test_tier(self, section):
        """Should return correct tier."""
        assert section.tier == "hot"

    def test_budget_bytes(self, section):
        """Should return correct budget."""
        assert section.budget_bytes == 4096

    def test_can_evict(self, section):
        """Should not be evictable."""
        assert section.can_evict is False

    def test_get_size_bytes_empty(self, section):
        """Should return size for empty section."""
        size = section.get_size_bytes()
        assert size > 0
        assert size < section.budget_bytes

    def test_get_size_bytes_populated(self, populated_section):
        """Should return larger size for populated section."""
        size = populated_section.get_size_bytes()
        assert size > 100  # More than header overhead

    def test_clear(self, populated_section):
        """Should reset to initial state."""
        populated_section.clear()
        assert populated_section.primary_thread is None
        assert populated_section.total_threads_session == 0
        assert populated_section.current_turn == 0

    def test_get_metadata(self, populated_section):
        """Should return complete metadata."""
        meta = populated_section.get_metadata()
        assert meta["name"] == "narrative_active"
        assert meta["tier"] == "hot"
        assert meta["budget_bytes"] == 4096
        assert "current_size_bytes" in meta
        assert "utilization_pct" in meta
        assert meta["session_id"] == "test-session-populated"
        assert meta["current_thread_id"] is not None
        assert meta["arc_position"] == "EXPOSITION"


# =============================================================================
# ConversationThread Tests
# =============================================================================


class TestConversationThread:
    """Test ConversationThread dataclass."""

    def test_create_thread(self):
        """Should create with required fields."""
        thread = ConversationThread(id="thread-1")
        assert thread.id == "thread-1"
        assert thread.state == ThreadState.ACTIVE
        assert thread.title == ""
        assert thread.goal == ""

    def test_create_thread_full(self):
        """Should create with all fields."""
        thread = ConversationThread(
            id="thread-1",
            title="Test Thread",
            state=ThreadState.PAUSED,
            started_turn=5,
            last_active_turn=10,
            goal="Complete task",
            is_goal_met=False,
            related_entities=["e1", "e2"],
            related_intents=["i1"],
            resumption_hint="Earlier...",
            context_summary="Summary",
        )
        assert thread.title == "Test Thread"
        assert thread.state == ThreadState.PAUSED
        assert thread.started_turn == 5
        assert thread.last_active_turn == 10
        assert thread.goal == "Complete task"
        assert len(thread.related_entities) == 2

    def test_state_checks(self):
        """Should correctly report state."""
        thread = ConversationThread(id="t1", state=ThreadState.ACTIVE)
        assert thread.is_active()
        assert not thread.is_paused()
        assert not thread.is_resolved()
        assert not thread.is_archived()

        thread.state = ThreadState.PAUSED
        assert not thread.is_active()
        assert thread.is_paused()

    def test_can_resume(self):
        """Should report resumable state."""
        thread = ConversationThread(id="t1", state=ThreadState.ACTIVE)
        assert thread.can_resume()

        thread.state = ThreadState.PAUSED
        assert thread.can_resume()

        thread.state = ThreadState.RESOLVED
        assert not thread.can_resume()

        thread.state = ThreadState.ARCHIVED
        assert not thread.can_resume()

    def test_turns_active(self):
        """Should calculate active turns."""
        thread = ConversationThread(
            id="t1",
            started_turn=5,
            last_active_turn=10,
        )
        assert thread.turns_active() == 6

    def test_state_int_conversion(self):
        """Should convert int to ThreadState enum."""
        thread = ConversationThread(id="t1", state=1)  # type: ignore
        assert thread.state == ThreadState.PAUSED


# =============================================================================
# NarrativeArc Tests
# =============================================================================


class TestNarrativeArc:
    """Test NarrativeArc dataclass."""

    def test_create_default(self):
        """Should create with defaults."""
        arc = NarrativeArc()
        assert arc.position == ArcPosition.EXPOSITION
        assert arc.exposition_end == 10
        assert arc.rising_end == 40
        assert arc.climax_end == 60
        assert arc.progress == 0.0

    def test_update_for_turn_exposition(self):
        """Should set exposition phase."""
        arc = NarrativeArc()
        arc.update_for_turn(5)
        assert arc.position == ArcPosition.EXPOSITION
        assert arc.progress == 0.5

    def test_update_for_turn_rising(self):
        """Should set rising action phase."""
        arc = NarrativeArc()
        arc.update_for_turn(25)
        assert arc.position == ArcPosition.RISING_ACTION
        assert 0.4 < arc.progress < 0.6

    def test_update_for_turn_climax(self):
        """Should set climax phase."""
        arc = NarrativeArc()
        arc.update_for_turn(50)
        assert arc.position == ArcPosition.CLIMAX

    def test_update_for_turn_resolution(self):
        """Should set resolution phase."""
        arc = NarrativeArc()
        arc.update_for_turn(100)
        assert arc.position == ArcPosition.RESOLUTION
        assert arc.progress == 1.0

    def test_set_inciting_incident(self):
        """Should record inciting incident."""
        arc = NarrativeArc()
        arc.set_inciting_incident(3)
        assert arc.inciting_incident_turn == 3

    def test_set_climax(self):
        """Should record climax and set position."""
        arc = NarrativeArc()
        arc.set_climax(45)
        assert arc.climax_turn == 45
        assert arc.position == ArcPosition.CLIMAX

    def test_progress_clamped(self):
        """Should clamp progress to [0, 1]."""
        arc = NarrativeArc(progress=1.5)
        assert arc.progress == 1.0

        arc = NarrativeArc(progress=-0.5)
        assert arc.progress == 0.0


# =============================================================================
# Thread Creation Tests
# =============================================================================


class TestThreadCreation:
    """Test thread creation operations."""

    def test_create_thread_basic(self, section):
        """Should create thread with basic info."""
        thread = section.create_thread(title="Test Thread")
        assert thread.id
        assert thread.title == "Test Thread"
        assert thread.state == ThreadState.ACTIVE
        assert section.primary_thread == thread

    def test_create_thread_with_goal(self, section):
        """Should create thread with goal."""
        thread = section.create_thread(
            title="Task Thread",
            goal="Complete the task",
        )
        assert thread.goal == "Complete the task"

    def test_create_thread_auto_turn(self, section):
        """Should auto-increment turn number."""
        thread1 = section.create_thread(title="T1")
        thread2 = section.create_thread(title="T2")
        assert thread1.started_turn == 1
        assert thread2.started_turn == 2

    def test_create_thread_explicit_turn(self, section):
        """Should use explicit turn number."""
        thread = section.create_thread(title="Test", turn_number=10)
        assert thread.started_turn == 10
        assert section.current_turn == 10

    def test_create_thread_pauses_previous(self, section):
        """Should pause previous thread."""
        thread1 = section.create_thread(title="T1")
        thread2 = section.create_thread(title="T2")
        assert thread1.state == ThreadState.PAUSED
        assert thread2.state == ThreadState.ACTIVE
        assert section.primary_thread == thread2

    def test_create_thread_no_auto_switch(self, section):
        """Should not switch if auto_switch=False."""
        thread1 = section.create_thread(title="T1")
        thread2 = section.create_thread(title="T2", auto_switch=False)
        assert thread2.state == ThreadState.PAUSED
        assert section.primary_thread == thread1

    def test_create_thread_with_entities(self, section):
        """Should attach related entities."""
        thread = section.create_thread(
            title="Test",
            related_entities=["e1", "e2"],
        )
        assert thread.related_entities == ["e1", "e2"]

    def test_create_thread_with_intents(self, section):
        """Should attach related intents."""
        thread = section.create_thread(
            title="Test",
            related_intents=["intent1"],
        )
        assert thread.related_intents == ["intent1"]

    def test_create_thread_increments_total(self, section):
        """Should increment total threads."""
        section.create_thread(title="T1")
        section.create_thread(title="T2")
        section.create_thread(title="T3")
        assert section.total_threads_session == 3

    def test_create_thread_sets_inciting_incident(self, section):
        """Should set inciting incident on first thread with goal."""
        thread = section.create_thread(title="T1", goal="Main goal")
        assert section.arc.inciting_incident_turn == thread.started_turn


# =============================================================================
# Thread Switching Tests
# =============================================================================


class TestThreadSwitching:
    """Test thread switching operations."""

    def test_switch_to_valid(self, multi_thread_section):
        """Should switch to valid thread."""
        # Get the first paused thread
        paused = multi_thread_section.paused_threads[0]
        result = multi_thread_section.switch_to(paused.id)
        assert result is True
        assert multi_thread_section.primary_thread.id == paused.id

    def test_switch_to_invalid_id(self, section):
        """Should return False for invalid ID."""
        result = section.switch_to("nonexistent")
        assert result is False

    def test_switch_to_resolved_fails(self, populated_section):
        """Should not switch to resolved thread."""
        thread_id = populated_section.primary_thread.id
        populated_section.resolve_thread(thread_id)
        result = populated_section.switch_to(thread_id)
        assert result is False

    def test_switch_pauses_current(self, multi_thread_section):
        """Should pause current thread when switching."""
        current = multi_thread_section.primary_thread
        paused = multi_thread_section.paused_threads[0]
        multi_thread_section.switch_to(paused.id)
        assert current.state == ThreadState.PAUSED

    def test_switch_updates_turn(self, multi_thread_section):
        """Should update last_active_turn."""
        paused = multi_thread_section.paused_threads[0]
        multi_thread_section.switch_to(paused.id, turn_number=20)
        assert paused.last_active_turn == 20

    def test_switch_generates_hint(self, multi_thread_section):
        """Should generate resumption hint."""
        paused = multi_thread_section.paused_threads[0]
        multi_thread_section.switch_to(paused.id)
        assert paused.resumption_hint != ""


# =============================================================================
# Thread Lifecycle Tests
# =============================================================================


class TestThreadLifecycle:
    """Test thread state transitions."""

    def test_pause_thread(self, populated_section):
        """Should pause active thread."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.pause_thread(thread_id)
        assert result is True
        assert populated_section.primary_thread is None

    def test_pause_already_paused(self, multi_thread_section):
        """Should fail to pause already paused thread."""
        paused = multi_thread_section.paused_threads[0]
        result = multi_thread_section.pause_thread(paused.id)
        assert result is False

    def test_resolve_thread(self, populated_section):
        """Should resolve thread."""
        thread = populated_section.primary_thread
        thread_id = thread.id
        result = populated_section.resolve_thread(thread_id, turn_number=15)
        assert result is True
        assert thread.state == ThreadState.RESOLVED
        assert thread.is_goal_met is True
        assert thread.resolved_turn == 15

    def test_resolve_removes_from_primary(self, populated_section):
        """Should remove from primary when resolved."""
        thread_id = populated_section.primary_thread.id
        populated_section.resolve_thread(thread_id)
        assert populated_section.primary_thread is None

    def test_archive_thread(self, populated_section):
        """Should archive thread."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.archive_thread(thread_id)
        assert result is True
        assert thread_id in populated_section.archived_thread_ids

    def test_archive_removes_from_index(self, populated_section):
        """Should remove from index."""
        thread_id = populated_section.primary_thread.id
        populated_section.archive_thread(thread_id)
        assert populated_section.get_thread(thread_id) is None


# =============================================================================
# Thread Update Tests
# =============================================================================


class TestThreadUpdate:
    """Test thread update operations."""

    def test_update_title(self, populated_section):
        """Should update title."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.update_thread(thread_id, title="New Title")
        assert result is True
        assert populated_section.primary_thread.title == "New Title"

    def test_update_goal(self, populated_section):
        """Should update goal."""
        thread_id = populated_section.primary_thread.id
        populated_section.update_thread(thread_id, goal="New Goal")
        assert populated_section.primary_thread.goal == "New Goal"

    def test_update_context_summary(self, populated_section):
        """Should update context summary."""
        thread_id = populated_section.primary_thread.id
        populated_section.update_thread(
            thread_id,
            context_summary="User was discussing X",
        )
        assert populated_section.primary_thread.context_summary == "User was discussing X"

    def test_add_related_entity(self, populated_section):
        """Should add related entity."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.add_related_entity(thread_id, "new-entity")
        assert result is True
        assert "new-entity" in populated_section.primary_thread.related_entities

    def test_add_duplicate_entity(self, populated_section):
        """Should not duplicate entity."""
        thread_id = populated_section.primary_thread.id
        populated_section.add_related_entity(thread_id, "dup")
        populated_section.add_related_entity(thread_id, "dup")
        count = populated_section.primary_thread.related_entities.count("dup")
        assert count == 1

    def test_add_related_intent(self, populated_section):
        """Should add related intent."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.add_related_intent(thread_id, "new.intent")
        assert result is True
        assert "new.intent" in populated_section.primary_thread.related_intents


# =============================================================================
# Query Operations Tests
# =============================================================================


class TestQueryOperations:
    """Test query operations."""

    def test_get_thread(self, populated_section):
        """Should get thread by ID."""
        thread_id = populated_section.primary_thread.id
        thread = populated_section.get_thread(thread_id)
        assert thread is not None
        assert thread.id == thread_id

    def test_get_thread_invalid(self, section):
        """Should return None for invalid ID."""
        thread = section.get_thread("invalid")
        assert thread is None

    def test_get_all_threads(self, multi_thread_section):
        """Should get all threads."""
        threads = multi_thread_section.get_all_threads()
        assert len(threads) >= 2  # Primary + at least one paused

    def test_get_active_threads(self, multi_thread_section):
        """Should get resumable threads."""
        threads = multi_thread_section.get_active_threads()
        for t in threads:
            assert t.can_resume()

    def test_get_threads_by_entity(self, populated_section):
        """Should find threads by entity."""
        threads = populated_section.get_threads_by_entity("entity-1")
        assert len(threads) == 1

    def test_get_threads_by_intent(self, populated_section):
        """Should find threads by intent."""
        threads = populated_section.get_threads_by_intent("weather.query")
        assert len(threads) == 1

    def test_has_active_thread(self, section, populated_section):
        """Should check for active thread."""
        assert section.has_active_thread() is False
        assert populated_section.has_active_thread() is True

    def test_has_paused_threads(self, multi_thread_section):
        """Should check for paused threads."""
        assert multi_thread_section.has_paused_threads() is True

    def test_get_suggested_resumptions(self, multi_thread_section):
        """Should return resumption suggestions."""
        suggestions = multi_thread_section.get_suggested_resumptions(max_count=2)
        assert len(suggestions) <= 2
        for s in suggestions:
            assert "thread_id" in s
            assert "title" in s
            assert "hint" in s


# =============================================================================
# Arc Operations Tests
# =============================================================================


class TestArcOperations:
    """Test narrative arc operations."""

    def test_record_turn_updates_arc(self, section):
        """Should update arc on turn."""
        section.record_turn(25)
        assert section.arc_position == ArcPosition.RISING_ACTION

    def test_set_inciting_incident(self, section):
        """Should set inciting incident."""
        section.set_inciting_incident(5)
        assert section.arc.inciting_incident_turn == 5

    def test_set_climax(self, section):
        """Should set climax."""
        section.set_climax(50)
        assert section.arc.climax_turn == 50
        assert section.arc_position == ArcPosition.CLIMAX

    def test_update_arc_boundaries(self, section):
        """Should update boundaries."""
        section.update_arc_boundaries(
            exposition_end=5,
            rising_end=20,
            climax_end=30,
        )
        assert section.arc.exposition_end == 5
        assert section.arc.rising_end == 20
        assert section.arc.climax_end == 30

    def test_is_exposition(self, section):
        """Should detect exposition phase."""
        section.record_turn(5)
        assert section.is_exposition() is True

    def test_is_rising_action(self, section):
        """Should detect rising action phase."""
        section.record_turn(25)
        assert section.is_rising_action() is True

    def test_is_climax(self, section):
        """Should detect climax phase."""
        section.record_turn(50)
        assert section.is_climax() is True

    def test_is_resolution(self, section):
        """Should detect resolution phase."""
        section.record_turn(100)
        assert section.is_resolution() is True


# =============================================================================
# Paused Limit Tests
# =============================================================================


class TestPausedLimit:
    """Test paused thread limit enforcement."""

    def test_enforce_paused_limit(self, section):
        """Should archive oldest when over limit."""
        # Create more than MAX_PAUSED_THREADS threads
        for i in range(MAX_PAUSED_THREADS + 2):
            section.create_thread(title=f"Thread {i}")

        assert section.paused_thread_count <= MAX_PAUSED_THREADS
        assert len(section.archived_thread_ids) >= 1


# =============================================================================
# FlatBuffer Serialization Tests
# =============================================================================


class TestFlatBufferSerialization:
    """Test FlatBuffer serialization."""

    def test_serialize_empty(self, section):
        """Should serialize empty section."""
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_deserialize_empty(self, section):
        """Should deserialize empty section."""
        data = section.to_flatbuffer()
        new_section = NarrativeActiveSection()
        new_section.from_flatbuffer(data)
        assert new_section.primary_thread is None

    def test_roundtrip_populated(self, populated_section):
        """Should roundtrip populated section."""
        original_thread_id = populated_section.primary_thread.id
        original_title = populated_section.primary_thread.title

        data = populated_section.to_flatbuffer()
        new_section = NarrativeActiveSection()
        new_section.from_flatbuffer(data)

        assert new_section.primary_thread is not None
        assert new_section.primary_thread.id == original_thread_id
        assert new_section.primary_thread.title == original_title

    def test_roundtrip_multi_thread(self, multi_thread_section):
        """Should roundtrip multi-thread section."""
        original_paused_count = multi_thread_section.paused_thread_count

        data = multi_thread_section.to_flatbuffer()
        new_section = NarrativeActiveSection()
        new_section.from_flatbuffer(data)

        assert new_section.primary_thread is not None
        assert new_section.paused_thread_count == original_paused_count

    def test_roundtrip_arc(self, section):
        """Should roundtrip arc state."""
        section.record_turn(25)
        section.set_inciting_incident(5)

        data = section.to_flatbuffer()
        new_section = NarrativeActiveSection()
        new_section.from_flatbuffer(data)

        assert new_section.arc_position == ArcPosition.RISING_ACTION
        assert new_section.arc.inciting_incident_turn == 5

    def test_serialize_caching(self, populated_section):
        """Should cache serialized bytes."""
        data1 = populated_section.to_flatbuffer()
        data2 = populated_section.to_flatbuffer()
        assert data1 is data2  # Same object (cached)

    def test_serialize_invalidates_on_change(self, populated_section):
        """Should invalidate cache on change."""
        data1 = populated_section.to_flatbuffer()
        populated_section.record_turn(100)
        data2 = populated_section.to_flatbuffer()
        assert data1 is not data2

    def test_serialize_alias(self, populated_section):
        """Should work with serialize() alias."""
        data = populated_section.serialize()
        assert isinstance(data, bytes)

    def test_deserialize_alias(self, populated_section):
        """Should work with deserialize() alias."""
        data = populated_section.serialize()
        new_section = NarrativeActiveSection()
        new_section.deserialize(data)
        assert new_section.primary_thread is not None


# =============================================================================
# Apply Operations Tests
# =============================================================================


class TestApplyOperations:
    """Test apply operations for MutationGuard pattern."""

    def test_apply_create_thread(self, section):
        """Should create thread via apply."""
        thread_id = section.apply(
            "create_thread",
            {"title": "Test", "goal": "Test Goal"},
        )
        assert thread_id
        assert section.primary_thread is not None

    def test_apply_switch_to(self, multi_thread_section):
        """Should switch via apply."""
        paused = multi_thread_section.paused_threads[0]
        result = multi_thread_section.apply(
            "switch_to",
            {"thread_id": paused.id},
        )
        assert result is True

    def test_apply_pause_thread(self, populated_section):
        """Should pause via apply."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.apply(
            "pause_thread",
            {"thread_id": thread_id},
        )
        assert result is True

    def test_apply_resolve_thread(self, populated_section):
        """Should resolve via apply."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.apply(
            "resolve_thread",
            {"thread_id": thread_id},
        )
        assert result is True

    def test_apply_archive_thread(self, populated_section):
        """Should archive via apply."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.apply(
            "archive_thread",
            {"thread_id": thread_id},
        )
        assert result is True

    def test_apply_update_thread(self, populated_section):
        """Should update via apply."""
        thread_id = populated_section.primary_thread.id
        result = populated_section.apply(
            "update_thread",
            {"thread_id": thread_id, "title": "Updated"},
        )
        assert result is True
        assert populated_section.primary_thread.title == "Updated"

    def test_apply_record_turn(self, section):
        """Should record turn via apply."""
        result = section.apply("record_turn", {"turn_number": 50})
        assert result is True
        assert section.current_turn == 50

    def test_apply_clear(self, populated_section):
        """Should clear via apply."""
        result = populated_section.apply("clear", {})
        assert result is True
        assert populated_section.primary_thread is None

    def test_apply_unknown_operation(self, section):
        """Should raise on unknown operation."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("invalid_op", {})


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunction:
    """Test factory function."""

    def test_create_empty(self):
        """Should create empty section."""
        section = create_narrative_active_section()
        assert section.primary_thread is None

    def test_create_with_session_id(self):
        """Should use provided session ID."""
        section = create_narrative_active_section(session_id="my-session")
        assert section.session_id == "my-session"

    def test_create_with_initial_thread(self):
        """Should create initial thread."""
        section = create_narrative_active_section(
            initial_thread_title="Initial Thread",
            initial_thread_goal="Initial Goal",
        )
        assert section.primary_thread is not None
        assert section.primary_thread.title == "Initial Thread"
        assert section.primary_thread.goal == "Initial Goal"


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and limits."""

    def test_empty_title(self, section):
        """Should handle empty title."""
        thread = section.create_thread(title="")
        assert thread.title == ""

    def test_unicode_content(self, section):
        """Should handle unicode content."""
        thread = section.create_thread(
            title="日本語テスト",
            goal="こんにちは",
        )
        assert "日本語" in thread.title

    def test_large_content(self, section):
        """Should handle large content."""
        large_goal = "x" * 1000
        thread = section.create_thread(
            title="Large Thread",
            goal=large_goal,
        )
        assert len(thread.goal) == 1000

    def test_many_entities(self, section):
        """Should handle many entities."""
        entities = [f"entity-{i}" for i in range(50)]
        thread = section.create_thread(
            title="Many Entities",
            related_entities=entities,
        )
        assert len(thread.related_entities) == 50

    def test_current_turn_consistency(self, section):
        """Should maintain turn consistency."""
        section.create_thread(title="T1", turn_number=10)
        section.create_thread(title="T2")  # Should be 11
        assert section.current_turn == 11

    def test_resumption_hint_with_summary(self, section):
        """Should prefer context_summary for hint."""
        thread = section.create_thread(title="Test")
        section.update_thread(
            thread.id,
            context_summary="you asked about weather",
        )
        section.pause_thread(thread.id)
        hint = thread.resumption_hint
        assert "weather" in hint

    def test_resumption_hint_with_goal(self, section):
        """Should use goal for hint if no summary."""
        thread = section.create_thread(
            title="Test",
            goal="book a flight",
        )
        section.pause_thread(thread.id)
        hint = thread.resumption_hint
        assert "flight" in hint


# =============================================================================
# Timestamp Tests
# =============================================================================


class TestTimestamps:
    """Test timestamp handling."""

    def test_last_updated_on_create(self, section):
        """Should update timestamp on create."""
        before = int(time.time() * 1000)
        section.create_thread(title="Test")
        after = int(time.time() * 1000)
        assert before <= section.last_updated_ms <= after

    def test_last_updated_on_switch(self, multi_thread_section):
        """Should update timestamp on switch."""
        before = int(time.time() * 1000)
        paused = multi_thread_section.paused_threads[0]
        multi_thread_section.switch_to(paused.id)
        after = int(time.time() * 1000)
        assert before <= multi_thread_section.last_updated_ms <= after
