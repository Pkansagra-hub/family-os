"""
HistoryActiveSection Tests - Comprehensive Test Suite
======================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.4 (history_active)

Test Coverage:
- ISection protocol compliance
- Turn management (add, get, remove, demote)
- Capacity management (is_full, should_demote, overflow)
- FlatBuffer serialization/deserialization
- Search and query functionality
- Statistics and formatting
- Legacy API compatibility
- Edge cases and error handling
"""

import time

import pytest

from k1.sessionstate.sections.history_active import HistoryActiveSection, Turn, TurnMetadata

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def section():
    """Create a fresh HistoryActiveSection for each test."""
    return HistoryActiveSection(session_id="test-session")


@pytest.fixture
def section_with_turns():
    """Create section with 5 turns."""
    s = HistoryActiveSection(session_id="test-session")
    for i in range(5):
        s.add_turn(
            user_message=f"User message {i + 1}",
            assistant_response=f"Assistant response {i + 1}",
            turn_id=f"turn-{i + 1}",
        )
    return s


@pytest.fixture
def full_section():
    """Create section at max capacity (10 turns)."""
    s = HistoryActiveSection(session_id="test-session")
    for i in range(10):
        s.add_turn(
            user_message=f"User message {i + 1}",
            assistant_response=f"Assistant response {i + 1}",
            turn_id=f"turn-{i + 1}",
        )
    return s


@pytest.fixture
def turn_with_metadata():
    """Create a turn with full metadata."""
    return TurnMetadata(
        intent="weather.query",
        entities=["entity-1", "entity-2"],
        emotion="curious",
        confidence=0.95,
        processing_time_ms=150,
    )


# =============================================================================
# CLASS: TestISection - Protocol Compliance
# =============================================================================


class TestISection:
    """Tests for ISection protocol implementation."""

    def test_name_property(self, section):
        """Section has correct name."""
        assert section.name == "history_active"

    def test_tier_property(self, section):
        """Section is in HOT tier."""
        assert section.tier == "hot"

    def test_budget_bytes_property(self, section):
        """Section has 8KB budget."""
        assert section.budget_bytes == 8192

    def test_can_evict_property(self, section):
        """Section cannot be evicted (items demote instead)."""
        assert section.can_evict is False

    def test_get_size_bytes_empty(self, section):
        """Empty section has minimal size."""
        size = section.get_size_bytes()
        assert size > 0
        assert size < 200  # Just overhead

    def test_get_size_bytes_with_turns(self, section_with_turns):
        """Size increases with turns."""
        size = section_with_turns.get_size_bytes()
        assert size > 200

    def test_clear(self, section_with_turns):
        """Clear removes all turns."""
        assert section_with_turns.count() == 5
        section_with_turns.clear()
        assert section_with_turns.count() == 0
        assert section_with_turns.current_turn_number == 0

    def test_get_metadata(self, section):
        """Metadata contains expected keys."""
        meta = section.get_metadata()
        assert meta["name"] == "history_active"
        assert meta["tier"] == "hot"
        assert meta["budget_bytes"] == 8192
        assert "current_size_bytes" in meta
        assert "utilization_pct" in meta
        assert "turn_count" in meta
        assert "max_turns" in meta


# =============================================================================
# CLASS: TestTurnDataclass
# =============================================================================


class TestTurnDataclass:
    """Tests for Turn dataclass."""

    def test_turn_creation(self):
        """Turn can be created with required fields."""
        turn = Turn(
            turn_id="turn-1",
            turn_number=1,
            user_message="Hello",
            assistant_response="Hi there!",
        )
        assert turn.turn_id == "turn-1"
        assert turn.turn_number == 1
        assert turn.user_message == "Hello"
        assert turn.assistant_response == "Hi there!"

    def test_turn_computes_bytes(self):
        """Turn auto-computes message bytes."""
        turn = Turn(
            turn_id="turn-1",
            turn_number=1,
            user_message="Hello",
            assistant_response="Hi there!",
        )
        assert turn.user_message_bytes == len("Hello".encode("utf-8"))
        assert turn.response_bytes == len("Hi there!".encode("utf-8"))

    def test_turn_user_tokens(self):
        """Turn computes approximate user tokens."""
        turn = Turn(
            turn_id="turn-1",
            turn_number=1,
            user_message="Hello world, how are you?",  # 25 chars -> 6 tokens
            assistant_response="",
        )
        assert turn.user_tokens == 6

    def test_turn_response_tokens(self):
        """Turn computes approximate response tokens."""
        turn = Turn(
            turn_id="turn-1",
            turn_number=1,
            user_message="",
            assistant_response="I am doing well, thank you!",  # 27 chars -> 6 tokens
        )
        assert turn.response_tokens == 6

    def test_turn_with_metadata(self, turn_with_metadata):
        """Turn can include metadata."""
        turn = Turn(
            turn_id="turn-1",
            turn_number=1,
            user_message="What's the weather?",
            assistant_response="Let me check...",
            metadata=turn_with_metadata,
        )
        assert turn.metadata is not None
        assert turn.metadata.intent == "weather.query"
        assert len(turn.metadata.entities) == 2

    def test_turn_with_entities_intents(self):
        """Turn can have entities and intents."""
        turn = Turn(
            turn_id="turn-1",
            turn_number=1,
            user_message="Hello",
            assistant_response="Hi!",
            entities=["entity-1", "entity-2"],
            intents=["greeting"],
        )
        assert len(turn.entities) == 2
        assert len(turn.intents) == 1

    def test_turn_with_emotion(self):
        """Turn can have emotion."""
        turn = Turn(
            turn_id="turn-1",
            turn_number=1,
            user_message="Hello",
            assistant_response="Hi!",
            emotion="happy",
        )
        assert turn.emotion == "happy"


# =============================================================================
# CLASS: TestTurnMetadataDataclass
# =============================================================================


class TestTurnMetadataDataclass:
    """Tests for TurnMetadata dataclass."""

    def test_metadata_defaults(self):
        """Metadata has sensible defaults."""
        meta = TurnMetadata()
        assert meta.intent == ""
        assert meta.entities == []
        assert meta.emotion == ""
        assert meta.confidence == 1.0
        assert meta.processing_time_ms == 0

    def test_metadata_full(self, turn_with_metadata):
        """Metadata stores all values."""
        assert turn_with_metadata.intent == "weather.query"
        assert turn_with_metadata.entities == ["entity-1", "entity-2"]
        assert turn_with_metadata.emotion == "curious"
        assert turn_with_metadata.confidence == 0.95
        assert turn_with_metadata.processing_time_ms == 150


# =============================================================================
# CLASS: TestProperties
# =============================================================================


class TestProperties:
    """Tests for section properties."""

    def test_session_id(self, section):
        """Session ID is stored."""
        assert section.session_id == "test-session"

    def test_session_id_generated(self):
        """Session ID is generated if not provided."""
        s = HistoryActiveSection()
        assert s.session_id != ""
        assert len(s.session_id) > 0

    def test_session_start_ms(self, section):
        """Session start time is set."""
        assert section.session_start_ms > 0

    def test_last_activity_ms(self, section):
        """Last activity time is set."""
        assert section.last_activity_ms > 0

    def test_last_updated_ms(self, section):
        """Last updated time is set."""
        assert section.last_updated_ms > 0

    def test_schema_version(self, section):
        """Schema version is set."""
        assert section.schema_version == "1.0.0"

    def test_current_turn_number_empty(self, section):
        """Current turn number is 0 when empty."""
        assert section.current_turn_number == 0

    def test_current_turn_number_with_turns(self, section_with_turns):
        """Current turn number reflects latest turn."""
        assert section_with_turns.current_turn_number == 5

    def test_oldest_turn_number_empty(self, section):
        """Oldest turn number is 0 when empty."""
        assert section.oldest_turn_number == 0

    def test_oldest_turn_number_with_turns(self, section_with_turns):
        """Oldest turn number reflects first turn."""
        assert section_with_turns.oldest_turn_number == 1

    def test_total_user_tokens(self, section_with_turns):
        """Total user tokens is cumulative."""
        assert section_with_turns.total_user_tokens > 0

    def test_total_response_tokens(self, section_with_turns):
        """Total response tokens is cumulative."""
        assert section_with_turns.total_response_tokens > 0

    def test_avg_turn_duration_empty(self, section):
        """Average duration is 0 when empty."""
        assert section.avg_turn_duration_ms == 0


# =============================================================================
# CLASS: TestTurnManagement
# =============================================================================


class TestTurnManagement:
    """Tests for turn management operations."""

    def test_add_turn(self, section):
        """Add turn creates and stores turn."""
        turn = section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
        )
        assert turn is not None
        assert turn.turn_number == 1
        assert section.count() == 1

    def test_add_turn_with_id(self, section):
        """Add turn with custom ID."""
        turn = section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            turn_id="custom-id",
        )
        assert turn.turn_id == "custom-id"

    def test_add_turn_generates_id(self, section):
        """Add turn generates ID if not provided."""
        turn = section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
        )
        assert turn.turn_id != ""
        assert len(turn.turn_id) > 0

    def test_add_turn_increments_number(self, section):
        """Each turn gets sequential number."""
        t1 = section.add_turn("A", "B")
        t2 = section.add_turn("C", "D")
        t3 = section.add_turn("E", "F")
        assert t1.turn_number == 1
        assert t2.turn_number == 2
        assert t3.turn_number == 3

    def test_add_turn_with_metadata(self, section, turn_with_metadata):
        """Add turn with metadata."""
        turn = section.add_turn(
            user_message="What's the weather?",
            assistant_response="Let me check...",
            metadata=turn_with_metadata,
        )
        assert turn.metadata is not None
        assert turn.metadata.intent == "weather.query"

    def test_add_turn_with_entities(self, section):
        """Add turn with entities."""
        turn = section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            entities=["person-1", "location-2"],
        )
        assert len(turn.entities) == 2

    def test_add_turn_with_intents(self, section):
        """Add turn with intents."""
        turn = section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            intents=["greeting", "introduction"],
        )
        assert len(turn.intents) == 2

    def test_add_turn_with_emotion(self, section):
        """Add turn with emotion."""
        turn = section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            emotion="happy",
        )
        assert turn.emotion == "happy"

    def test_add_turn_with_duration(self, section):
        """Add turn with processing duration."""
        turn = section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            duration_ms=250,
        )
        assert turn.duration_ms == 250
        assert section.avg_turn_duration_ms == 250

    def test_get_turn(self, section_with_turns):
        """Get turn by ID."""
        turn = section_with_turns.get_turn("turn-3")
        assert turn is not None
        assert turn.turn_number == 3

    def test_get_turn_not_found(self, section_with_turns):
        """Get turn returns None if not found."""
        turn = section_with_turns.get_turn("nonexistent")
        assert turn is None

    def test_get_by_number(self, section_with_turns):
        """Get turn by number."""
        turn = section_with_turns.get_by_number(3)
        assert turn is not None
        assert turn.turn_id == "turn-3"

    def test_get_by_number_not_found(self, section_with_turns):
        """Get by number returns None if not found."""
        turn = section_with_turns.get_by_number(99)
        assert turn is None

    def test_get_recent(self, section_with_turns):
        """Get recent N turns."""
        recent = section_with_turns.get_recent(3)
        assert len(recent) == 3
        assert recent[0].turn_number == 3
        assert recent[1].turn_number == 4
        assert recent[2].turn_number == 5

    def test_get_recent_more_than_available(self, section_with_turns):
        """Get recent returns available if N exceeds count."""
        recent = section_with_turns.get_recent(100)
        assert len(recent) == 5

    def test_get_recent_zero(self, section_with_turns):
        """Get recent with 0 returns empty list."""
        recent = section_with_turns.get_recent(0)
        assert len(recent) == 0

    def test_get_all(self, section_with_turns):
        """Get all turns."""
        turns = section_with_turns.get_all()
        assert len(turns) == 5
        assert turns[0].turn_number == 1
        assert turns[4].turn_number == 5

    def test_count(self, section_with_turns):
        """Count returns number of turns."""
        assert section_with_turns.count() == 5

    def test_count_empty(self, section):
        """Count is 0 for empty section."""
        assert section.count() == 0

    def test_remove_turn(self, section_with_turns):
        """Remove turn by ID."""
        assert section_with_turns.count() == 5
        result = section_with_turns.remove_turn("turn-3")
        assert result is True
        assert section_with_turns.count() == 4
        assert section_with_turns.get_turn("turn-3") is None

    def test_remove_turn_not_found(self, section_with_turns):
        """Remove returns False if not found."""
        result = section_with_turns.remove_turn("nonexistent")
        assert result is False
        assert section_with_turns.count() == 5


# =============================================================================
# CLASS: TestCapacityManagement
# =============================================================================


class TestCapacityManagement:
    """Tests for capacity management."""

    def test_max_turns(self, section):
        """MAX_TURNS is 10."""
        assert section.MAX_TURNS == 10

    def test_is_full_empty(self, section):
        """Empty section is not full."""
        assert section.is_full() is False

    def test_is_full_partial(self, section_with_turns):
        """Partial section is not full."""
        assert section_with_turns.is_full() is False

    def test_is_full_at_max(self, full_section):
        """Section at max is full."""
        assert full_section.is_full() is True

    def test_has_overflow_empty(self, section):
        """Empty section has no overflow."""
        assert section.has_overflow() is False

    def test_has_overflow_under_max(self, section_with_turns):
        """Under max has no overflow."""
        assert section_with_turns.has_overflow() is False

    def test_has_overflow_at_max(self, full_section):
        """At max has no overflow."""
        assert full_section.has_overflow() is False

    def test_has_overflow_over_max(self, full_section):
        """Over max has overflow."""
        full_section.add_turn("Extra", "Turn")
        assert full_section.has_overflow() is True

    def test_get_overflow_empty(self, section):
        """Get overflow returns empty for under-capacity."""
        overflow = section.get_overflow()
        assert len(overflow) == 0

    def test_get_overflow_removes_excess(self, full_section):
        """Get overflow removes and returns excess turns."""
        full_section.add_turn("Extra 1", "Turn 1")
        full_section.add_turn("Extra 2", "Turn 2")
        assert full_section.count() == 12

        overflow = full_section.get_overflow()
        assert len(overflow) == 2
        assert full_section.count() == 10
        assert overflow[0].turn_number == 1
        assert overflow[1].turn_number == 2

    def test_demote_oldest(self, section_with_turns):
        """Demote oldest removes and returns turns."""
        demoted = section_with_turns.demote_oldest(2)
        assert len(demoted) == 2
        assert demoted[0].turn_number == 1
        assert demoted[1].turn_number == 2
        assert section_with_turns.count() == 3

    def test_demote_oldest_more_than_available(self, section_with_turns):
        """Demote caps at available count."""
        demoted = section_with_turns.demote_oldest(100)
        assert len(demoted) == 5
        assert section_with_turns.count() == 0

    def test_demote_oldest_zero(self, section_with_turns):
        """Demote 0 returns empty."""
        demoted = section_with_turns.demote_oldest(0)
        assert len(demoted) == 0
        assert section_with_turns.count() == 5

    def test_should_demote_empty(self, section):
        """Empty section should not demote."""
        assert section.should_demote() is False

    def test_should_demote_under_threshold(self, section_with_turns):
        """Under 90% should not demote."""
        assert section_with_turns.should_demote() is False

    def test_should_demote_at_max_turns(self, full_section):
        """At max turns should demote."""
        assert full_section.should_demote() is True

    def test_get_available_capacity(self, section_with_turns):
        """Get available capacity."""
        assert section_with_turns.get_available_capacity() == 5

    def test_get_available_capacity_full(self, full_section):
        """No capacity when full."""
        assert full_section.get_available_capacity() == 0

    def test_get_pressure_empty(self, section):
        """Empty has low pressure."""
        assert section.get_pressure() < 0.1

    def test_get_pressure_full(self, full_section):
        """Full has high pressure."""
        assert full_section.get_pressure() >= 1.0


# =============================================================================
# CLASS: TestAggregates
# =============================================================================


class TestAggregates:
    """Tests for aggregate tracking."""

    def test_aggregates_updated_on_add(self, section):
        """Aggregates update when adding turns."""
        initial_tokens = section.total_user_tokens
        section.add_turn("Hello world!", "Hi there!", duration_ms=100)
        assert section.total_user_tokens > initial_tokens
        assert section.total_response_tokens > 0
        assert section.avg_turn_duration_ms == 100

    def test_aggregates_updated_on_demote(self, section_with_turns):
        """Aggregates update when demoting turns."""
        initial_tokens = section_with_turns.total_user_tokens
        section_with_turns.demote_oldest(2)
        assert section_with_turns.total_user_tokens < initial_tokens

    def test_aggregates_updated_on_remove(self, section_with_turns):
        """Aggregates update when removing turns."""
        initial_tokens = section_with_turns.total_user_tokens
        section_with_turns.remove_turn("turn-1")
        assert section_with_turns.total_user_tokens < initial_tokens

    def test_aggregates_updated_on_clear(self, section_with_turns):
        """Aggregates reset on clear."""
        section_with_turns.clear()
        assert section_with_turns.total_user_tokens == 0
        assert section_with_turns.total_response_tokens == 0
        assert section_with_turns.avg_turn_duration_ms == 0


# =============================================================================
# CLASS: TestFlatBufferSerialization
# =============================================================================


class TestFlatBufferSerialization:
    """Tests for FlatBuffer serialization."""

    def test_to_flatbuffer_empty(self, section):
        """Empty section serializes."""
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_to_flatbuffer_with_turns(self, section_with_turns):
        """Section with turns serializes."""
        data = section_with_turns.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_from_flatbuffer_restores_turns(self, section_with_turns):
        """Deserialization restores turns."""
        data = section_with_turns.to_flatbuffer()

        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)

        assert new_section.count() == 5
        assert new_section.current_turn_number == 5
        assert new_section.oldest_turn_number == 1

    def test_roundtrip_preserves_messages(self, section):
        """Roundtrip preserves message content."""
        section.add_turn(
            user_message="Hello world, how are you today?",
            assistant_response="I'm doing great, thank you for asking!",
            turn_id="test-turn",
        )

        data = section.to_flatbuffer()
        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)

        turn = new_section.get_turn("test-turn")
        assert turn is not None
        assert turn.user_message == "Hello world, how are you today?"
        assert turn.assistant_response == "I'm doing great, thank you for asking!"

    def test_roundtrip_preserves_entities(self, section):
        """Roundtrip preserves entities."""
        section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            turn_id="test-turn",
            entities=["person-1", "location-2"],
        )

        data = section.to_flatbuffer()
        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)

        turn = new_section.get_turn("test-turn")
        assert turn is not None
        assert "person-1" in turn.entities
        assert "location-2" in turn.entities

    def test_roundtrip_preserves_intents(self, section):
        """Roundtrip preserves intents."""
        section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            turn_id="test-turn",
            intents=["greeting", "introduction"],
        )

        data = section.to_flatbuffer()
        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)

        turn = new_section.get_turn("test-turn")
        assert turn is not None
        assert "greeting" in turn.intents
        assert "introduction" in turn.intents

    def test_roundtrip_preserves_emotion(self, section):
        """Roundtrip preserves emotion."""
        section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            turn_id="test-turn",
            emotion="happy",
        )

        data = section.to_flatbuffer()
        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)

        turn = new_section.get_turn("test-turn")
        assert turn is not None
        assert turn.emotion == "happy"

    def test_roundtrip_preserves_metadata(self, section, turn_with_metadata):
        """Roundtrip preserves metadata."""
        section.add_turn(
            user_message="What's the weather?",
            assistant_response="Let me check...",
            turn_id="test-turn",
            metadata=turn_with_metadata,
        )

        data = section.to_flatbuffer()
        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)

        turn = new_section.get_turn("test-turn")
        assert turn is not None
        assert turn.metadata is not None
        assert turn.metadata.intent == "weather.query"
        assert turn.metadata.confidence == pytest.approx(0.95, abs=0.01)
        assert turn.metadata.emotion == "curious"
        assert "entity-1" in turn.metadata.entities

    def test_roundtrip_preserves_timestamps(self, section):
        """Roundtrip preserves timestamps."""
        timestamp = int(time.time() * 1000)
        section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            turn_id="test-turn",
            timestamp_ms=timestamp,
            duration_ms=150,
        )

        data = section.to_flatbuffer()
        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)

        turn = new_section.get_turn("test-turn")
        assert turn is not None
        assert turn.timestamp_ms == timestamp
        assert turn.duration_ms == 150

    def test_roundtrip_preserves_session_timing(self, section):
        """Roundtrip preserves session timing."""
        original_start = section.session_start_ms
        original_activity = section.last_activity_ms

        section.add_turn("Hello", "Hi!")
        data = section.to_flatbuffer()

        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)

        assert new_section.session_start_ms == original_start
        # Last activity updates on add_turn
        assert new_section.last_activity_ms >= original_activity

    def test_caching_works(self, section):
        """Serialization caching works."""
        section.add_turn("Hello", "Hi!")

        data1 = section.to_flatbuffer()
        data2 = section.to_flatbuffer()

        # Both calls should return same cached bytes
        assert data1 == data2

    def test_cache_invalidated_on_change(self, section):
        """Cache invalidated on modification."""
        section.add_turn("Hello", "Hi!")
        data1 = section.to_flatbuffer()

        section.add_turn("World", "Earth!")
        data2 = section.to_flatbuffer()

        # Data should differ after modification
        assert data1 != data2

    def test_serialization_under_budget(self, full_section):
        """Full section serializes under budget."""
        data = full_section.to_flatbuffer()
        assert len(data) <= full_section.BUDGET_BYTES


# =============================================================================
# CLASS: TestLegacyAPI
# =============================================================================


class TestLegacyAPI:
    """Tests for legacy API compatibility."""

    def test_serialize_alias(self, section_with_turns):
        """serialize() is alias for to_flatbuffer()."""
        data1 = section_with_turns.serialize()
        data2 = section_with_turns.to_flatbuffer()
        assert data1 == data2

    def test_deserialize_alias(self, section_with_turns):
        """deserialize() is alias for from_flatbuffer()."""
        data = section_with_turns.to_flatbuffer()

        new_section = HistoryActiveSection()
        new_section.deserialize(data)

        assert new_section.count() == 5

    def test_get_alias(self, section_with_turns):
        """get() is alias for get_turn()."""
        turn = section_with_turns.get("turn-3")
        assert turn is not None
        assert turn.turn_number == 3

    def test_append_alias(self, section):
        """append() is alias for add_turn()."""
        turn = section.append("Hello", "Hi!")
        assert turn is not None
        assert turn.turn_number == 1

    def test_touch_updates_timestamp(self, section):
        """touch() updates last_updated_ms."""
        original = section.last_updated_ms
        time.sleep(0.01)  # Small delay
        section.touch()
        assert section.last_updated_ms >= original


# =============================================================================
# CLASS: TestSearchAndQuery
# =============================================================================


class TestSearchAndQuery:
    """Tests for search and query functionality."""

    def test_find_turns_by_entity(self, section):
        """Find turns by entity."""
        section.add_turn("A", "B", turn_id="t1", entities=["person-1"])
        section.add_turn("C", "D", turn_id="t2", entities=["location-1"])
        section.add_turn("E", "F", turn_id="t3", entities=["person-1", "location-1"])

        turns = section.find_turns_by_entity("person-1")
        assert len(turns) == 2
        assert turns[0].turn_id == "t1"
        assert turns[1].turn_id == "t3"

    def test_find_turns_by_entity_not_found(self, section_with_turns):
        """Find by entity returns empty if not found."""
        turns = section_with_turns.find_turns_by_entity("nonexistent")
        assert len(turns) == 0

    def test_find_turns_by_intent(self, section):
        """Find turns by intent."""
        section.add_turn("A", "B", turn_id="t1", intents=["greeting"])
        section.add_turn("C", "D", turn_id="t2", intents=["weather"])
        section.add_turn("E", "F", turn_id="t3", intents=["greeting", "farewell"])

        turns = section.find_turns_by_intent("greeting")
        assert len(turns) == 2

    def test_find_turns_by_emotion(self, section):
        """Find turns by emotion."""
        section.add_turn("A", "B", turn_id="t1", emotion="happy")
        section.add_turn("C", "D", turn_id="t2", emotion="sad")
        section.add_turn("E", "F", turn_id="t3", emotion="happy")

        turns = section.find_turns_by_emotion("happy")
        assert len(turns) == 2

    def test_search_messages_user(self, section):
        """Search user messages."""
        section.add_turn("Hello world", "Hi there", turn_id="t1")
        section.add_turn("Goodbye world", "Bye!", turn_id="t2")
        section.add_turn("How are you", "Fine thanks", turn_id="t3")

        turns = section.search_messages("world", include_user=True, include_assistant=False)
        assert len(turns) == 2

    def test_search_messages_assistant(self, section):
        """Search assistant messages."""
        section.add_turn("Hello", "Hi there friend", turn_id="t1")
        section.add_turn("Bye", "Goodbye friend", turn_id="t2")
        section.add_turn("How", "I'm good", turn_id="t3")

        turns = section.search_messages("friend", include_user=False, include_assistant=True)
        assert len(turns) == 2

    def test_search_messages_case_insensitive(self, section):
        """Search is case insensitive."""
        section.add_turn("HELLO WORLD", "hi there", turn_id="t1")

        turns = section.search_messages("hello")
        assert len(turns) == 1


# =============================================================================
# CLASS: TestStatistics
# =============================================================================


class TestStatistics:
    """Tests for statistics functionality."""

    def test_get_statistics_empty(self, section):
        """Empty section has zero stats."""
        stats = section.get_statistics()
        assert stats["turn_count"] == 0
        assert stats["total_user_tokens"] == 0
        assert stats["total_response_tokens"] == 0
        assert stats["avg_user_tokens"] == 0
        assert stats["avg_response_tokens"] == 0

    def test_get_statistics_with_turns(self, section_with_turns):
        """Stats computed for turns."""
        stats = section_with_turns.get_statistics()
        assert stats["turn_count"] == 5
        assert stats["total_user_tokens"] > 0
        assert stats["oldest_turn"] == 1
        assert stats["newest_turn"] == 5

    def test_get_statistics_unique_entities(self, section):
        """Stats track unique entities."""
        section.add_turn("A", "B", entities=["e1", "e2"])
        section.add_turn("C", "D", entities=["e2", "e3"])

        stats = section.get_statistics()
        assert stats["unique_entities"] == 3

    def test_get_statistics_unique_intents(self, section):
        """Stats track unique intents."""
        section.add_turn("A", "B", intents=["i1"])
        section.add_turn("C", "D", intents=["i1", "i2"])

        stats = section.get_statistics()
        assert stats["unique_intents"] == 2

    def test_get_statistics_emotions(self, section):
        """Stats track emotions."""
        section.add_turn("A", "B", emotion="happy")
        section.add_turn("C", "D", emotion="sad")
        section.add_turn("E", "F", emotion="happy")

        stats = section.get_statistics()
        assert "happy" in stats["emotions"]
        assert "sad" in stats["emotions"]


# =============================================================================
# CLASS: TestFormatting
# =============================================================================


class TestFormatting:
    """Tests for formatting functionality."""

    def test_format_for_prompt(self, section_with_turns):
        """Format for prompt produces readable output."""
        output = section_with_turns.format_for_prompt(n=3)
        assert "User:" in output
        assert "Assistant:" in output
        assert "User message 3" in output
        assert "User message 5" in output

    def test_format_for_prompt_with_metadata(self, section):
        """Format includes metadata when requested."""
        section.add_turn(
            "Hello",
            "Hi!",
            entities=["person-1"],
            intents=["greeting"],
            emotion="happy",
        )

        output = section.format_for_prompt(n=1, include_metadata=True)
        assert "Entities:" in output
        assert "Intents:" in output
        assert "Emotion:" in output

    def test_format_for_prompt_empty(self, section):
        """Format for empty section."""
        output = section.format_for_prompt()
        assert output == ""


# =============================================================================
# CLASS: TestEdgeCases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_unicode_messages(self, section):
        """Handles Unicode messages."""
        turn = section.add_turn(
            user_message="Hello 世界 🌍",
            assistant_response="こんにちは! 🎉",
        )
        assert "世界" in turn.user_message
        assert "こんにちは" in turn.assistant_response

        # Roundtrip
        data = section.to_flatbuffer()
        new_section = HistoryActiveSection()
        new_section.from_flatbuffer(data)
        restored = new_section.get_all()[0]
        assert "世界" in restored.user_message
        assert "こんにちは" in restored.assistant_response

    def test_empty_messages(self, section):
        """Handles empty messages."""
        turn = section.add_turn(
            user_message="",
            assistant_response="",
        )
        assert turn.user_message == ""
        assert turn.assistant_response == ""

    def test_very_long_message(self, section):
        """Handles long messages."""
        long_msg = "A" * 5000
        turn = section.add_turn(
            user_message=long_msg,
            assistant_response="Short",
        )
        assert len(turn.user_message) == 5000
        assert turn.user_message_bytes == 5000

    def test_special_characters(self, section):
        """Handles special characters."""
        turn = section.add_turn(
            user_message='Hello\n"World"\t<>&',
            assistant_response="Response\r\n\0with\bnulls",
        )
        assert "\n" in turn.user_message
        assert '"' in turn.user_message

    def test_multiple_rapid_adds(self, section):
        """Handles rapid sequential adds."""
        for i in range(100):
            section.add_turn(f"Message {i}", f"Response {i}")

        assert section.count() == 100
        assert section.current_turn_number == 100

    def test_demote_all_then_add(self, section_with_turns):
        """Can add after demoting all."""
        section_with_turns.demote_oldest(5)
        assert section_with_turns.count() == 0

        turn = section_with_turns.add_turn("New", "Turn")
        assert turn.turn_number == 6  # Continues from last number


# =============================================================================
# CLASS: TestTimestampBehavior
# =============================================================================


class TestTimestampBehavior:
    """Tests for timestamp behavior."""

    def test_last_activity_updates_on_add(self, section):
        """Last activity updates when adding turns."""
        original = section.last_activity_ms
        time.sleep(0.01)
        section.add_turn("Hello", "Hi!")
        assert section.last_activity_ms > original

    def test_last_updated_updates_on_add(self, section):
        """Last updated updates when adding turns."""
        original = section.last_updated_ms
        time.sleep(0.01)
        section.add_turn("Hello", "Hi!")
        assert section.last_updated_ms > original

    def test_last_updated_updates_on_clear(self, section_with_turns):
        """Last updated updates when clearing."""
        original = section_with_turns.last_updated_ms
        time.sleep(0.01)
        section_with_turns.clear()
        assert section_with_turns.last_updated_ms > original

    def test_last_updated_updates_on_demote(self, section_with_turns):
        """Last updated updates when demoting."""
        original = section_with_turns.last_updated_ms
        time.sleep(0.01)
        section_with_turns.demote_oldest(1)
        assert section_with_turns.last_updated_ms > original

    def test_custom_timestamp_on_turn(self, section):
        """Can set custom timestamp on turn."""
        custom_ts = 1700000000000
        turn = section.add_turn(
            user_message="Hello",
            assistant_response="Hi!",
            timestamp_ms=custom_ts,
        )
        assert turn.timestamp_ms == custom_ts
