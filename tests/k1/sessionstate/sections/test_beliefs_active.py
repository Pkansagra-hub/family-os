"""
Tests for BeliefsActiveSection (Issue 2.2.2)
=============================================

Tests the BeliefsActiveSection implementation per FlatBuffer schema:
k1/contracts/flatbuffers/sessionstate/beliefs_active_section.fbs

Test Categories:
1. Initialization and properties
2. Fact management (add, get, list, remove, find)
3. Entity management
4. Temporal context (mentioned_time)
5. Spatial context (mentioned_location)
6. Pinning and demotion
7. Turn lifecycle
8. FlatBuffer serialization roundtrip
9. ISection protocol compliance
10. Edge cases and error handling
11. Performance targets (<100μs serialization)
"""

import time

import pytest

from k1.sessionstate.sections.beliefs_active import (
    BeliefsActiveSection,
    EntityRef,
    Fact,
    MentionedLocation,
    MentionedTime,
    PrivacyBand,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def section() -> BeliefsActiveSection:
    """Create a fresh BeliefsActiveSection for testing."""
    return BeliefsActiveSection(session_id="test-session", turn_id="test-turn")


@pytest.fixture
def populated_section() -> BeliefsActiveSection:
    """Create a section with pre-populated data."""
    s = BeliefsActiveSection(session_id="test-session", turn_id="test-turn")

    # Add facts
    s.add_fact("user", "prefers", "dark mode", 0.9, "nlu")
    s.add_fact("user", "lives_in", "New York", 0.85, "nlu")
    s.add_fact("user", "owns", "iPhone", 0.95, "nlu")

    # Add entities
    s.add_entity("entity-1", "person", "John Smith", 0.9)
    s.add_entity("entity-2", "location", "New York", 0.85)

    # Set contexts
    s.set_mentioned_time("tomorrow at 3pm", 1700000000000, 0.9, True)
    s.set_mentioned_location("the kitchen", "room", "loc-123", 0.85)

    return s


# =============================================================================
# 1. Initialization Tests
# =============================================================================


class TestInitialization:
    """Test section initialization and properties."""

    def test_default_initialization(self):
        """Test default initialization generates UUIDs."""
        s = BeliefsActiveSection()
        assert s.session_id is not None
        assert s.turn_id is not None
        assert len(s.session_id) > 0
        assert len(s.turn_id) > 0

    def test_custom_initialization(self):
        """Test initialization with custom IDs."""
        s = BeliefsActiveSection(
            session_id="sess-123",
            turn_id="turn-456",
            schema_version="2.0.0",
        )
        assert s.session_id == "sess-123"
        assert s.turn_id == "turn-456"
        assert s.schema_version == "2.0.0"

    def test_class_constants(self):
        """Test class constants match schema requirements."""
        assert BeliefsActiveSection.BUDGET_BYTES == 8192
        assert BeliefsActiveSection.TIER == "hot"
        assert BeliefsActiveSection.CAN_EVICT is False
        assert BeliefsActiveSection.SECTION_NAME == "beliefs_active"
        assert BeliefsActiveSection.MAX_FACTS == 50

    def test_initial_state_empty(self, section: BeliefsActiveSection):
        """Test initial state is empty."""
        assert section.get_fact_count() == 0
        assert section.get_entity_count() == 0
        assert section.get_mentioned_time() is None
        assert section.get_mentioned_location() is None
        assert section.get_pinned_fact_ids() == []

    def test_last_updated_ms_set(self, section: BeliefsActiveSection):
        """Test last_updated_ms is set on initialization."""
        now_ms = int(time.time() * 1000)
        assert section.last_updated_ms > 0
        assert abs(section.last_updated_ms - now_ms) < 1000  # Within 1 second


# =============================================================================
# 2. Fact Management Tests
# =============================================================================


class TestFactManagement:
    """Test fact CRUD operations per schema."""

    def test_add_fact_basic(self, section: BeliefsActiveSection):
        """Test adding a basic fact in SVO format."""
        fact = section.add_fact("user", "prefers", "dark mode")

        assert fact.id is not None
        assert fact.subject == "user"
        assert fact.predicate == "prefers"
        assert fact.object == "dark mode"
        assert fact.confidence == 1.0  # Default
        assert section.get_fact_count() == 1

    def test_add_fact_with_metadata(self, section: BeliefsActiveSection):
        """Test adding fact with all metadata."""
        fact = section.add_fact(
            subject="user",
            predicate="owns",
            obj="iPhone",
            confidence=0.95,
            source="nlu-agent",
            privacy_band=PrivacyBand.AMBER,
            fact_id="custom-id-123",
        )

        assert fact.id == "custom-id-123"
        assert fact.confidence == 0.95
        assert fact.source == "nlu-agent"
        assert fact.privacy_band == PrivacyBand.AMBER
        assert fact.timestamp_ms > 0

    def test_get_fact_by_id(self, section: BeliefsActiveSection):
        """Test retrieving fact by ID."""
        fact = section.add_fact("user", "prefers", "dark mode")
        retrieved = section.get_fact(fact.id)

        assert retrieved is not None
        assert retrieved.id == fact.id
        assert retrieved.subject == "user"

    def test_get_fact_updates_access_tracking(self, section: BeliefsActiveSection):
        """Test that get_fact updates access tracking."""
        fact = section.add_fact("user", "prefers", "dark mode")
        initial_access = fact.access_count

        section.get_fact(fact.id)
        assert fact.access_count == initial_access + 1

    def test_get_fact_nonexistent(self, section: BeliefsActiveSection):
        """Test getting nonexistent fact returns None."""
        assert section.get_fact("nonexistent-id") is None

    def test_list_facts(self, section: BeliefsActiveSection):
        """Test listing all facts."""
        section.add_fact("user", "prefers", "dark mode")
        section.add_fact("user", "lives_in", "New York")

        facts = section.list_facts()
        assert len(facts) == 2

    def test_remove_fact(self, section: BeliefsActiveSection):
        """Test removing a fact."""
        fact = section.add_fact("user", "prefers", "dark mode")
        assert section.get_fact_count() == 1

        result = section.remove_fact(fact.id)
        assert result is True
        assert section.get_fact_count() == 0
        assert section.get_fact(fact.id) is None

    def test_remove_fact_nonexistent(self, section: BeliefsActiveSection):
        """Test removing nonexistent fact returns False."""
        assert section.remove_fact("nonexistent-id") is False

    def test_find_by_subject(self, populated_section: BeliefsActiveSection):
        """Test finding facts by subject."""
        facts = populated_section.find_by_subject("user")
        assert len(facts) == 3  # All facts have "user" as subject

    def test_find_by_predicate(self, populated_section: BeliefsActiveSection):
        """Test finding facts by predicate."""
        facts = populated_section.find_by_predicate("prefers")
        assert len(facts) == 1
        assert facts[0].object == "dark mode"

    def test_find_by_object(self, populated_section: BeliefsActiveSection):
        """Test finding facts by object."""
        facts = populated_section.find_by_object("New York")
        assert len(facts) == 1
        assert facts[0].predicate == "lives_in"

    def test_update_confidence(self, section: BeliefsActiveSection):
        """Test updating fact confidence."""
        fact = section.add_fact("user", "prefers", "dark mode", 0.8)
        assert fact.confidence == 0.8

        result = section.update_confidence(fact.id, 0.95)
        assert result is True
        assert section.get_fact(fact.id).confidence == 0.95

    def test_update_confidence_nonexistent(self, section: BeliefsActiveSection):
        """Test updating nonexistent fact confidence."""
        assert section.update_confidence("nonexistent", 0.9) is False


# =============================================================================
# 3. Entity Management Tests
# =============================================================================


class TestEntityManagement:
    """Test entity CRUD operations per schema."""

    def test_add_entity(self, section: BeliefsActiveSection):
        """Test adding an entity reference."""
        entity = section.add_entity(
            entity_id="entity-1",
            entity_type="person",
            display_name="John Smith",
            confidence=0.95,
        )

        assert entity.id == "entity-1"
        assert entity.type == "person"
        assert entity.display_name == "John Smith"
        assert entity.confidence == 0.95
        assert section.get_entity_count() == 1

    def test_get_entity(self, section: BeliefsActiveSection):
        """Test retrieving entity by ID."""
        section.add_entity("entity-1", "person", "John Smith")
        entity = section.get_entity("entity-1")

        assert entity is not None
        assert entity.display_name == "John Smith"

    def test_get_entity_nonexistent(self, section: BeliefsActiveSection):
        """Test getting nonexistent entity returns None."""
        assert section.get_entity("nonexistent") is None

    def test_list_entities(self, section: BeliefsActiveSection):
        """Test listing all entities."""
        section.add_entity("entity-1", "person", "John")
        section.add_entity("entity-2", "location", "NYC")

        entities = section.list_entities()
        assert len(entities) == 2

    def test_remove_entity(self, section: BeliefsActiveSection):
        """Test removing an entity."""
        section.add_entity("entity-1", "person", "John")
        assert section.get_entity_count() == 1

        result = section.remove_entity("entity-1")
        assert result is True
        assert section.get_entity_count() == 0

    def test_remove_entity_nonexistent(self, section: BeliefsActiveSection):
        """Test removing nonexistent entity returns False."""
        assert section.remove_entity("nonexistent") is False


# =============================================================================
# 4. Temporal Context Tests (mentioned_time per schema)
# =============================================================================


class TestTemporalContext:
    """Test temporal context (mentioned_time) operations."""

    def test_set_mentioned_time(self, section: BeliefsActiveSection):
        """Test setting temporal context."""
        section.set_mentioned_time(
            raw_text="tomorrow at 3pm",
            resolved_ms=1700000000000,
            confidence=0.9,
            is_relative=True,
        )

        time_ctx = section.get_mentioned_time()
        assert time_ctx is not None
        assert time_ctx.raw_text == "tomorrow at 3pm"
        assert time_ctx.resolved_ms == 1700000000000
        assert time_ctx.confidence == 0.9
        assert time_ctx.is_relative is True

    def test_set_absolute_time(self, section: BeliefsActiveSection):
        """Test setting absolute time reference."""
        section.set_mentioned_time(
            raw_text="December 25, 2024",
            resolved_ms=1735084800000,
            confidence=0.95,
            is_relative=False,
        )

        time_ctx = section.get_mentioned_time()
        assert time_ctx.is_relative is False

    def test_clear_mentioned_time(self, section: BeliefsActiveSection):
        """Test clearing temporal context."""
        section.set_mentioned_time("tomorrow", 1700000000000)
        assert section.get_mentioned_time() is not None

        section.clear_mentioned_time()
        assert section.get_mentioned_time() is None


# =============================================================================
# 5. Spatial Context Tests (mentioned_location per schema)
# =============================================================================


class TestSpatialContext:
    """Test spatial context (mentioned_location) operations."""

    def test_set_mentioned_location(self, section: BeliefsActiveSection):
        """Test setting spatial context."""
        section.set_mentioned_location(
            raw_text="the kitchen",
            location_type="room",
            entity_id="loc-123",
            confidence=0.85,
        )

        loc_ctx = section.get_mentioned_location()
        assert loc_ctx is not None
        assert loc_ctx.raw_text == "the kitchen"
        assert loc_ctx.location_type == "room"
        assert loc_ctx.entity_id == "loc-123"
        assert loc_ctx.confidence == 0.85

    def test_set_location_without_entity(self, section: BeliefsActiveSection):
        """Test setting location without resolved entity."""
        section.set_mentioned_location(
            raw_text="mom's house",
            location_type="address",
        )

        loc_ctx = section.get_mentioned_location()
        assert loc_ctx.entity_id == ""

    def test_clear_mentioned_location(self, section: BeliefsActiveSection):
        """Test clearing spatial context."""
        section.set_mentioned_location("the office", "room")
        assert section.get_mentioned_location() is not None

        section.clear_mentioned_location()
        assert section.get_mentioned_location() is None


# =============================================================================
# 6. Pinning and Demotion Tests
# =============================================================================


class TestPinningAndDemotion:
    """Test fact pinning and demotion for lifecycle management."""

    def test_pin_fact(self, section: BeliefsActiveSection):
        """Test pinning a fact."""
        fact = section.add_fact("user", "prefers", "dark mode")
        assert fact.is_pinned is False

        result = section.pin_fact(fact.id)
        assert result is True
        assert fact.is_pinned is True
        assert fact.id in section.get_pinned_fact_ids()

    def test_pin_fact_nonexistent(self, section: BeliefsActiveSection):
        """Test pinning nonexistent fact returns False."""
        assert section.pin_fact("nonexistent") is False

    def test_unpin_fact(self, section: BeliefsActiveSection):
        """Test unpinning a fact."""
        fact = section.add_fact("user", "prefers", "dark mode")
        section.pin_fact(fact.id)
        assert fact.is_pinned is True

        result = section.unpin_fact(fact.id)
        assert result is True
        assert fact.is_pinned is False
        assert fact.id not in section.get_pinned_fact_ids()

    def test_get_demotable_facts(self, section: BeliefsActiveSection):
        """Test getting facts eligible for demotion."""
        fact1 = section.add_fact("user", "prefers", "dark mode")
        fact2 = section.add_fact("user", "owns", "iPhone")
        section.pin_fact(fact1.id)

        demotable = section.get_demotable_facts()
        assert len(demotable) == 1
        assert demotable[0].id == fact2.id

    def test_get_demotable_facts_lru_order(self, section: BeliefsActiveSection):
        """Test demotable facts are in LRU order."""
        fact1 = section.add_fact("user", "prefers", "dark mode")
        fact2 = section.add_fact("user", "owns", "iPhone")

        # Manually set last_accessed_ms to ensure deterministic ordering
        # fact2 should be older (lower timestamp) so it comes first in demotable
        fact1.last_accessed_ms = 2000
        fact2.last_accessed_ms = 1000  # older access = demoted first

        demotable = section.get_demotable_facts()
        # fact2 should come first (older last access)
        assert demotable[0].id == fact2.id
        assert demotable[1].id == fact1.id

    def test_demote_facts(self, section: BeliefsActiveSection):
        """Test demoting facts (for migration to beliefs_history)."""
        section.add_fact("user", "prefers", "dark mode")
        section.add_fact("user", "owns", "iPhone")
        section.add_fact("user", "lives_in", "NYC")
        assert section.get_fact_count() == 3

        demoted = section.demote_facts(2)
        assert len(demoted) == 2
        assert section.get_fact_count() == 1

    def test_demote_facts_skips_pinned(self, section: BeliefsActiveSection):
        """Test demotion skips pinned facts."""
        fact1 = section.add_fact("user", "prefers", "dark mode")
        section.add_fact("user", "owns", "iPhone")
        section.pin_fact(fact1.id)

        demoted = section.demote_facts(2)
        assert len(demoted) == 1
        assert section.get_fact_count() == 1
        assert section.get_fact(fact1.id) is not None  # Pinned fact remains


# =============================================================================
# 7. Turn Lifecycle Tests
# =============================================================================


class TestTurnLifecycle:
    """Test turn lifecycle operations."""

    def test_start_new_turn(self, populated_section: BeliefsActiveSection):
        """Test starting a new turn clears state."""
        old_turn_id = populated_section.turn_id
        assert populated_section.get_fact_count() > 0

        new_turn_id = populated_section.start_new_turn()

        assert new_turn_id != old_turn_id
        assert populated_section.turn_id == new_turn_id
        assert populated_section.get_fact_count() == 0
        assert populated_section.get_mentioned_time() is None
        assert populated_section.get_mentioned_location() is None

    def test_start_new_turn_custom_id(self, section: BeliefsActiveSection):
        """Test starting new turn with custom ID."""
        new_turn_id = section.start_new_turn("custom-turn-id")
        assert section.turn_id == "custom-turn-id"

    def test_start_new_turn_preserves_entities(self, populated_section: BeliefsActiveSection):
        """Test starting new turn preserves entities."""
        entity_count = populated_section.get_entity_count()
        populated_section.start_new_turn()
        assert populated_section.get_entity_count() == entity_count

    def test_start_new_turn_no_clear(self, section: BeliefsActiveSection):
        """Test starting new turn without clearing facts."""
        section.add_fact("user", "prefers", "dark mode")
        section.start_new_turn(clear_facts=False)
        assert section.get_fact_count() == 1


# =============================================================================
# 8. FlatBuffer Serialization Tests
# =============================================================================


class TestFlatBufferSerialization:
    """Test FlatBuffer serialization roundtrip per schema."""

    def test_empty_section_roundtrip(self, section: BeliefsActiveSection):
        """Test empty section serialization roundtrip."""
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        assert section2.turn_id == section.turn_id
        assert section2.get_fact_count() == 0

    def test_populated_section_roundtrip(self, populated_section: BeliefsActiveSection):
        """Test populated section serialization roundtrip."""
        data = populated_section.to_flatbuffer()

        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        assert section2.turn_id == populated_section.turn_id
        assert section2.get_fact_count() == populated_section.get_fact_count()
        assert section2.get_entity_count() == populated_section.get_entity_count()

    def test_facts_serialization(self, section: BeliefsActiveSection):
        """Test fact data survives serialization."""
        section.add_fact(
            subject="user",
            predicate="prefers",
            obj="dark mode",
            confidence=0.95,
            source="nlu",
            privacy_band=PrivacyBand.AMBER,
        )

        data = section.to_flatbuffer()
        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        fact = section2.list_facts()[0]
        assert fact.subject == "user"
        assert fact.predicate == "prefers"
        assert fact.object == "dark mode"
        assert fact.confidence == pytest.approx(0.95, rel=0.01)
        assert fact.source == "nlu"
        assert fact.privacy_band == PrivacyBand.AMBER

    def test_entities_serialization(self, section: BeliefsActiveSection):
        """Test entity data survives serialization."""
        section.add_entity("entity-1", "person", "John Smith", 0.95)

        data = section.to_flatbuffer()
        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        entity = section2.get_entity("entity-1")
        assert entity is not None
        assert entity.type == "person"
        assert entity.display_name == "John Smith"
        assert entity.confidence == pytest.approx(0.95, rel=0.01)

    def test_temporal_context_serialization(self, section: BeliefsActiveSection):
        """Test temporal context survives serialization."""
        section.set_mentioned_time("tomorrow at 3pm", 1700000000000, 0.9, True)

        data = section.to_flatbuffer()
        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        time_ctx = section2.get_mentioned_time()
        assert time_ctx is not None
        assert time_ctx.raw_text == "tomorrow at 3pm"
        assert time_ctx.resolved_ms == 1700000000000
        assert time_ctx.is_relative is True

    def test_spatial_context_serialization(self, section: BeliefsActiveSection):
        """Test spatial context survives serialization."""
        section.set_mentioned_location("the kitchen", "room", "loc-123", 0.85)

        data = section.to_flatbuffer()
        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        loc_ctx = section2.get_mentioned_location()
        assert loc_ctx is not None
        assert loc_ctx.raw_text == "the kitchen"
        assert loc_ctx.location_type == "room"
        assert loc_ctx.entity_id == "loc-123"

    def test_pinned_fact_ids_serialization(self, section: BeliefsActiveSection):
        """Test pinned fact IDs survive serialization."""
        fact = section.add_fact("user", "prefers", "dark mode")
        section.pin_fact(fact.id)

        data = section.to_flatbuffer()
        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        pinned_ids = section2.get_pinned_fact_ids()
        assert fact.id in pinned_ids

        # Verify fact is marked as pinned
        recovered_fact = section2.get_fact(fact.id)
        assert recovered_fact.is_pinned is True

    def test_serialization_caching(self, section: BeliefsActiveSection):
        """Test serialization caching works."""
        section.add_fact("user", "prefers", "dark mode")

        data1 = section.to_flatbuffer()
        data2 = section.to_flatbuffer()
        assert data1 == data2

        # After modification, cache should be invalidated
        section.add_fact("user", "owns", "iPhone")
        data3 = section.to_flatbuffer()
        assert data3 != data1


# =============================================================================
# 9. ISection Protocol Compliance Tests
# =============================================================================


class TestISectionProtocol:
    """Test ISection protocol compliance."""

    def test_name_property(self, section: BeliefsActiveSection):
        """Test name property."""
        assert section.name == "beliefs_active"

    def test_tier_property(self, section: BeliefsActiveSection):
        """Test tier property."""
        assert section.tier == "hot"

    def test_budget_bytes_property(self, section: BeliefsActiveSection):
        """Test budget_bytes property."""
        assert section.budget_bytes == 8192

    def test_can_evict_property(self, section: BeliefsActiveSection):
        """Test can_evict property."""
        assert section.can_evict is False

    def test_get_size_bytes(self, section: BeliefsActiveSection):
        """Test get_size_bytes returns positive value."""
        size = section.get_size_bytes()
        assert size > 0
        assert size <= section.budget_bytes

    def test_get_size_bytes_increases_with_data(self, section: BeliefsActiveSection):
        """Test size increases as data is added."""
        size_empty = section.get_size_bytes()

        section.add_fact("user", "prefers", "dark mode")
        size_one_fact = section.get_size_bytes()
        assert size_one_fact > size_empty

        section.add_fact("user", "owns", "iPhone")
        size_two_facts = section.get_size_bytes()
        assert size_two_facts > size_one_fact

    def test_clear_method(self, populated_section: BeliefsActiveSection):
        """Test clear method resets all state."""
        assert populated_section.get_fact_count() > 0

        populated_section.clear()

        assert populated_section.get_fact_count() == 0
        assert populated_section.get_entity_count() == 0
        assert populated_section.get_mentioned_time() is None
        assert populated_section.get_mentioned_location() is None
        assert populated_section.get_pinned_fact_ids() == []

    def test_get_metadata(self, populated_section: BeliefsActiveSection):
        """Test get_metadata returns complete info."""
        metadata = populated_section.get_metadata()

        assert metadata["name"] == "beliefs_active"
        assert metadata["tier"] == "hot"
        assert metadata["budget_bytes"] == 8192
        assert "current_size_bytes" in metadata
        assert "utilization_pct" in metadata
        assert metadata["fact_count"] == 3
        assert metadata["entity_count"] == 2
        assert metadata["has_time_context"] is True
        assert metadata["has_location_context"] is True


# =============================================================================
# 10. Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_strings_in_fact(self, section: BeliefsActiveSection):
        """Test handling empty strings in fact."""
        fact = section.add_fact("", "", "")
        assert fact.subject == ""
        assert fact.predicate == ""
        assert fact.object == ""

    def test_unicode_in_fact(self, section: BeliefsActiveSection):
        """Test handling unicode in fact."""
        fact = section.add_fact("用户", "喜欢", "深色模式")

        data = section.to_flatbuffer()
        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        recovered = section2.list_facts()[0]
        assert recovered.subject == "用户"
        assert recovered.predicate == "喜欢"
        assert recovered.object == "深色模式"

    def test_special_characters(self, section: BeliefsActiveSection):
        """Test handling special characters."""
        fact = section.add_fact("user's", 'prefers "quotes"', "dark\\nmode")

        data = section.to_flatbuffer()
        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        recovered = section2.list_facts()[0]
        assert recovered.subject == "user's"
        assert recovered.predicate == 'prefers "quotes"'

    def test_max_confidence(self, section: BeliefsActiveSection):
        """Test maximum confidence value."""
        fact = section.add_fact("user", "prefers", "dark", confidence=1.0)
        assert fact.confidence == 1.0

    def test_min_confidence(self, section: BeliefsActiveSection):
        """Test minimum confidence value."""
        fact = section.add_fact("user", "prefers", "dark", confidence=0.0)
        assert fact.confidence == 0.0

    def test_all_privacy_bands(self, section: BeliefsActiveSection):
        """Test all privacy band values."""
        for band in PrivacyBand:
            fact = section.add_fact("user", "has", f"data-{band.name}", privacy_band=band)
            assert fact.privacy_band == band

    def test_remove_pinned_fact_clears_pin(self, section: BeliefsActiveSection):
        """Test removing pinned fact also clears pin."""
        fact = section.add_fact("user", "prefers", "dark mode")
        section.pin_fact(fact.id)
        assert fact.id in section.get_pinned_fact_ids()

        section.remove_fact(fact.id)
        assert fact.id not in section.get_pinned_fact_ids()


# =============================================================================
# 11. Performance Tests
# =============================================================================


class TestPerformance:
    """Test performance targets (<100μs serialization)."""

    def test_serialization_performance_empty(self, section: BeliefsActiveSection):
        """Test serialization performance with empty section."""
        # Warm up
        section.to_flatbuffer()

        start = time.perf_counter_ns()
        for _ in range(100):
            section.to_flatbuffer()
        elapsed_ns = time.perf_counter_ns() - start

        avg_us = elapsed_ns / 100 / 1000
        assert avg_us < 100, f"Serialization took {avg_us:.2f}μs, target is <100μs"

    def test_serialization_performance_populated(self, populated_section: BeliefsActiveSection):
        """Test serialization performance with populated section."""
        # Warm up
        populated_section.to_flatbuffer()

        start = time.perf_counter_ns()
        for _ in range(100):
            populated_section.to_flatbuffer()
        elapsed_ns = time.perf_counter_ns() - start

        avg_us = elapsed_ns / 100 / 1000
        assert avg_us < 100, f"Serialization took {avg_us:.2f}μs, target is <100μs"

    def test_deserialization_performance(self, populated_section: BeliefsActiveSection):
        """Test deserialization performance."""
        data = populated_section.to_flatbuffer()

        # Warm up
        section = BeliefsActiveSection()
        section.from_flatbuffer(data)

        start = time.perf_counter_ns()
        for _ in range(100):
            section = BeliefsActiveSection()
            section.from_flatbuffer(data)
        elapsed_ns = time.perf_counter_ns() - start

        avg_us = elapsed_ns / 100 / 1000
        assert avg_us < 200, f"Deserialization took {avg_us:.2f}μs, target is <200μs"

    def test_fact_lookup_performance(self, section: BeliefsActiveSection):
        """Test fact lookup performance."""
        # Add 50 facts (max per schema)
        fact_ids = []
        for i in range(50):
            fact = section.add_fact(f"subject-{i}", f"predicate-{i}", f"object-{i}")
            fact_ids.append(fact.id)

        # Warm up
        section.get_fact(fact_ids[25])

        start = time.perf_counter_ns()
        for _ in range(1000):
            section.get_fact(fact_ids[25])
        elapsed_ns = time.perf_counter_ns() - start

        avg_us = elapsed_ns / 1000 / 1000
        assert avg_us < 1, f"Lookup took {avg_us:.3f}μs, target is <1μs"


# =============================================================================
# 12. Legacy API Tests
# =============================================================================


class TestLegacyAPI:
    """Test legacy API aliases."""

    def test_serialize_alias(self, section: BeliefsActiveSection):
        """Test serialize() is alias for to_flatbuffer()."""
        section.add_fact("user", "prefers", "dark mode")
        data1 = section.to_flatbuffer()
        data2 = section.serialize()
        assert data1 == data2

    def test_deserialize_alias(self, section: BeliefsActiveSection):
        """Test deserialize() is alias for from_flatbuffer()."""
        section.add_fact("user", "prefers", "dark mode")
        data = section.to_flatbuffer()

        section2 = BeliefsActiveSection()
        section2.deserialize(data)
        assert section2.get_fact_count() == 1

    def test_get_method(self, populated_section: BeliefsActiveSection):
        """Test get() returns dictionary representation."""
        result = populated_section.get()

        assert "session_id" in result
        assert "turn_id" in result
        assert "facts" in result
        assert "entities" in result
        assert len(result["facts"]) == 3
        assert len(result["entities"]) == 2

    def test_touch_method(self, section: BeliefsActiveSection):
        """Test touch() updates timestamp."""
        old_ts = section.last_updated_ms
        time.sleep(0.01)
        section.touch()
        assert section.last_updated_ms > old_ts


# =============================================================================
# 13. Data Class Tests
# =============================================================================


class TestDataClasses:
    """Test data class behavior."""

    def test_fact_dataclass(self):
        """Test Fact dataclass."""
        fact = Fact(
            id="fact-1",
            subject="user",
            predicate="prefers",
            object="dark mode",
            confidence=0.95,
            source="nlu",
            timestamp_ms=1700000000000,
            privacy_band=PrivacyBand.GREEN,
        )

        assert fact.id == "fact-1"
        assert fact.subject == "user"
        assert fact.is_pinned is False  # Default
        assert fact.access_count == 0  # Default

    def test_entity_ref_dataclass(self):
        """Test EntityRef dataclass."""
        entity = EntityRef(
            id="entity-1",
            type="person",
            display_name="John Smith",
            confidence=0.95,
        )

        assert entity.id == "entity-1"
        assert entity.type == "person"

    def test_mentioned_time_dataclass(self):
        """Test MentionedTime dataclass."""
        time_ref = MentionedTime(
            raw_text="tomorrow",
            resolved_ms=1700000000000,
            confidence=0.9,
            is_relative=True,
        )

        assert time_ref.raw_text == "tomorrow"
        assert time_ref.is_relative is True

    def test_mentioned_location_dataclass(self):
        """Test MentionedLocation dataclass."""
        loc_ref = MentionedLocation(
            raw_text="the kitchen",
            location_type="room",
            entity_id="loc-123",
            confidence=0.85,
        )

        assert loc_ref.raw_text == "the kitchen"
        assert loc_ref.location_type == "room"

    def test_privacy_band_enum(self):
        """Test PrivacyBand enum values."""
        assert PrivacyBand.GREEN == 0
        assert PrivacyBand.AMBER == 1
        assert PrivacyBand.RED == 2
        assert PrivacyBand.BLACK == 3
