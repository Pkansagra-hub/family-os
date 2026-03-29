"""
Tests for ScoreboardSection - Discourse State Tracking (HOT CORE)
==================================================================

Epic 2.2: HOT CORE Sections
Issue 2.2.3: ScoreboardSection

Tests cover:
- Construction and initialization
- ISection protocol compliance
- Referent management
- Question Under Discussion (QUD) management
- Salience map management
- Topic stack management
- Intent management
- Turn management
- FlatBuffer serialization round-trip
- Legacy API compatibility
- Edge cases and performance
"""

import time

import pytest

from k1.sessionstate.sections.scoreboard import (
    Question,
    QuestionStatus,
    Referent,
    SalienceEntry,
    ScoreboardSection,
    TaskStatus,
    Topic,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def section() -> ScoreboardSection:
    """Create fresh ScoreboardSection for testing."""
    return ScoreboardSection()


@pytest.fixture
def populated_section() -> ScoreboardSection:
    """Create ScoreboardSection with data."""
    section = ScoreboardSection()

    # Add referents
    section.add_referent("the car", "vehicle-123", "vehicle", salience=0.8)
    section.add_referent("John", "person-456", "person", salience=0.6)

    # Push questions
    section.push_question("What color is it?", "user", priority=1)
    section.push_question("Where should we go?", "agent-1", priority=2)

    # Set salience
    section.set_salience("vehicle-123", 0.9)
    section.set_salience("person-456", 0.7)

    # Push topics
    section.push_topic("car shopping", salience=0.8, is_primary=True)
    section.push_topic("directions", salience=0.5)

    # Set intent
    section.set_user_intent("inquiry", 0.95)

    return section


# =============================================================================
# Construction Tests
# =============================================================================


class TestScoreboardSectionConstruction:
    """Test ScoreboardSection construction."""

    def test_default_initialization(self, section):
        """Test default initialization."""
        assert section.name == "scoreboard"
        assert section.tier == "hot"
        assert section.budget_bytes == 6144
        assert section.can_evict is False

    def test_initial_state_empty(self, section):
        """Test initial state is empty."""
        assert len(section.list_referents()) == 0
        assert len(section.list_questions()) == 0
        assert len(section.list_salient_entities()) == 0
        assert len(section.list_topics()) == 0

    def test_last_updated_ms_set(self, section):
        """Test last_updated_ms is set on creation."""
        assert section.last_updated_ms > 0
        # Should be within last second
        now_ms = int(time.time() * 1000)
        assert section.last_updated_ms <= now_ms

    def test_current_turn_starts_at_zero(self, section):
        """Test current turn starts at zero."""
        assert section.current_turn == 0

    def test_schema_version(self, section):
        """Test schema version is set."""
        assert section.SCHEMA_VERSION == "1.0.0"


# =============================================================================
# ISection Protocol Tests
# =============================================================================


class TestISectionProtocol:
    """Test ISection protocol compliance."""

    def test_name_property(self, section):
        """Test name property."""
        assert section.name == "scoreboard"

    def test_tier_property(self, section):
        """Test tier property."""
        assert section.tier == "hot"

    def test_budget_bytes_property(self, section):
        """Test budget_bytes property is 6KB."""
        assert section.budget_bytes == 6144

    def test_can_evict_property(self, section):
        """Test can_evict is always False for HOT CORE."""
        assert section.can_evict is False

    def test_get_size_bytes(self, section):
        """Test get_size_bytes returns positive value."""
        size = section.get_size_bytes()
        assert size > 0
        assert size <= section.budget_bytes

    def test_get_size_bytes_increases_with_data(self, section):
        """Test size increases as data is added."""
        initial_size = section.get_size_bytes()

        # Add referents
        for i in range(5):
            section.add_referent(f"entity-{i}", f"id-{i}", "type")

        new_size = section.get_size_bytes()
        assert new_size > initial_size

    def test_clear_method(self, populated_section):
        """Test clear resets to initial state."""
        populated_section.clear()

        assert len(populated_section.list_referents()) == 0
        assert len(populated_section.list_questions()) == 0
        assert len(populated_section.list_salient_entities()) == 0
        assert len(populated_section.list_topics()) == 0
        intent, conf = populated_section.get_user_intent()
        assert intent == ""
        assert conf == 0.0

    def test_get_metadata(self, section):
        """Test get_metadata returns expected keys."""
        meta = section.get_metadata()

        assert "name" in meta
        assert "tier" in meta
        assert "budget_bytes" in meta
        assert "current_size_bytes" in meta
        assert "utilization_pct" in meta
        assert "referent_count" in meta
        assert "qud_count" in meta
        assert "salience_entry_count" in meta
        assert "topic_count" in meta
        assert meta["name"] == "scoreboard"


# =============================================================================
# Referent Management Tests
# =============================================================================


class TestReferentManagement:
    """Test referent management."""

    def test_add_referent_basic(self, section):
        """Test adding a basic referent."""
        ref = section.add_referent("the car", "vehicle-123", "vehicle")

        assert ref.id != ""
        assert ref.text == "the car"
        assert ref.entity_id == "vehicle-123"
        assert ref.entity_type == "vehicle"
        assert ref.salience == 0.5  # default

    def test_add_referent_with_salience(self, section):
        """Test adding referent with custom salience."""
        ref = section.add_referent("it", "thing-1", "thing", salience=0.9)

        assert ref.salience == 0.9

    def test_add_referent_updates_existing(self, section):
        """Test re-mentioning same entity updates referent."""
        ref1 = section.add_referent("the car", "vehicle-123", "vehicle")
        initial_count = ref1.mention_count

        # Re-mention same entity
        ref2 = section.add_referent("it", "vehicle-123", "vehicle")

        assert ref2.id == ref1.id  # Same referent
        assert ref2.mention_count == initial_count + 1

    def test_get_referent_by_id(self, section):
        """Test getting referent by ID."""
        ref = section.add_referent("John", "person-1", "person")

        retrieved = section.get_referent(ref.id)
        assert retrieved is not None
        assert retrieved.id == ref.id
        assert retrieved.text == "John"

    def test_get_referent_by_entity(self, section):
        """Test getting referent by entity ID."""
        section.add_referent("the house", "place-1", "location")

        ref = section.get_referent_by_entity("place-1")
        assert ref is not None
        assert ref.entity_id == "place-1"

    def test_get_referent_nonexistent(self, section):
        """Test getting nonexistent referent returns None."""
        assert section.get_referent("nonexistent") is None
        assert section.get_referent_by_entity("nonexistent") is None

    def test_list_referents(self, section):
        """Test listing referents."""
        section.add_referent("a", "id-a", "type", salience=0.3)
        section.add_referent("b", "id-b", "type", salience=0.9)
        section.add_referent("c", "id-c", "type", salience=0.5)

        refs = section.list_referents()
        assert len(refs) == 3

    def test_list_referents_sorted_by_salience(self, section):
        """Test referents are sorted by salience."""
        section.add_referent("low", "id-low", "type", salience=0.1)
        section.add_referent("high", "id-high", "type", salience=0.9)
        section.add_referent("mid", "id-mid", "type", salience=0.5)

        refs = section.list_referents(sort_by_salience=True)
        assert refs[0].salience == 0.9
        assert refs[1].salience == 0.5
        assert refs[2].salience == 0.1

    def test_remove_referent(self, section):
        """Test removing a referent."""
        ref = section.add_referent("remove me", "temp-1", "temp")

        result = section.remove_referent(ref.id)
        assert result is True
        assert section.get_referent(ref.id) is None

    def test_remove_referent_nonexistent(self, section):
        """Test removing nonexistent referent returns False."""
        result = section.remove_referent("nonexistent")
        assert result is False

    def test_get_most_salient_referent(self, section):
        """Test getting most salient referent."""
        section.add_referent("low", "id-low", "type", salience=0.1)
        section.add_referent("high", "id-high", "type", salience=0.9)

        ref = section.get_most_salient_referent()
        assert ref is not None
        assert ref.salience == 0.9

    def test_get_most_salient_referent_empty(self, section):
        """Test most salient referent when empty."""
        ref = section.get_most_salient_referent()
        assert ref is None


# =============================================================================
# Question Under Discussion (QUD) Tests
# =============================================================================


class TestQUDManagement:
    """Test Question Under Discussion management."""

    def test_push_question(self, section):
        """Test pushing a question."""
        q = section.push_question("What is this?", "user")

        assert q.id != ""
        assert q.text == "What is this?"
        assert q.asked_by == "user"
        assert q.status == QuestionStatus.OPEN

    def test_push_question_with_priority(self, section):
        """Test pushing question with priority."""
        q = section.push_question("Important?", "agent-1", priority=10)

        assert q.priority == 10

    def test_pop_question(self, section):
        """Test popping question from stack."""
        section.push_question("First", "user")
        section.push_question("Second", "user")

        q = section.pop_question()
        assert q.text == "Second"

        q = section.pop_question()
        assert q.text == "First"

    def test_pop_question_empty(self, section):
        """Test popping from empty stack."""
        q = section.pop_question()
        assert q is None

    def test_peek_question(self, section):
        """Test peeking at top question."""
        section.push_question("First", "user")
        section.push_question("Second", "user")

        q = section.peek_question()
        assert q.text == "Second"

        # Should still be there
        q2 = section.peek_question()
        assert q2.text == "Second"

    def test_peek_question_empty(self, section):
        """Test peeking at empty stack."""
        q = section.peek_question()
        assert q is None

    def test_get_question_by_id(self, section):
        """Test getting question by ID."""
        q = section.push_question("Find me", "user")

        found = section.get_question(q.id)
        assert found is not None
        assert found.text == "Find me"

    def test_get_question_nonexistent(self, section):
        """Test getting nonexistent question."""
        q = section.get_question("nonexistent")
        assert q is None

    def test_answer_question(self, section):
        """Test answering a question."""
        q = section.push_question("What color?", "user")

        result = section.answer_question(q.id, "It's blue")
        assert result is True

        q = section.get_question(q.id)
        assert q.status == QuestionStatus.ANSWERED
        assert q.answer_summary == "It's blue"

    def test_answer_question_nonexistent(self, section):
        """Test answering nonexistent question."""
        result = section.answer_question("nonexistent", "answer")
        assert result is False

    def test_abandon_question(self, section):
        """Test abandoning a question."""
        q = section.push_question("Forget this", "user")

        result = section.abandon_question(q.id)
        assert result is True

        q = section.get_question(q.id)
        assert q.status == QuestionStatus.ABANDONED

    def test_defer_question(self, section):
        """Test deferring a question."""
        q = section.push_question("Later", "user")

        result = section.defer_question(q.id)
        assert result is True

        q = section.get_question(q.id)
        assert q.status == QuestionStatus.DEFERRED

    def test_list_questions(self, section):
        """Test listing all questions."""
        section.push_question("Q1", "user")
        section.push_question("Q2", "user")
        section.push_question("Q3", "agent")

        questions = section.list_questions()
        assert len(questions) == 3

    def test_list_open_questions(self, section):
        """Test listing only open questions."""
        q1 = section.push_question("Open1", "user")
        q2 = section.push_question("Open2", "user")
        q3 = section.push_question("Answered", "user")
        section.answer_question(q3.id, "Done")

        open_qs = section.list_open_questions()
        assert len(open_qs) == 2

    def test_clear_answered_questions(self, section):
        """Test clearing answered/abandoned questions."""
        q1 = section.push_question("Open", "user")
        q2 = section.push_question("Answered", "user")
        q3 = section.push_question("Abandoned", "user")
        section.answer_question(q2.id, "Done")
        section.abandon_question(q3.id)

        removed = section.clear_answered_questions()
        assert removed == 2
        assert len(section.list_questions()) == 1


# =============================================================================
# Salience Map Tests
# =============================================================================


class TestSalienceMap:
    """Test salience map management."""

    def test_set_salience(self, section):
        """Test setting salience for an entity."""
        entry = section.set_salience("entity-1", 0.8)

        assert entry.entity_id == "entity-1"
        assert entry.score == 0.8

    def test_set_salience_with_decay_rate(self, section):
        """Test setting salience with custom decay rate."""
        entry = section.set_salience("entity-1", 0.8, decay_rate=0.2)

        assert entry.decay_rate == 0.2

    def test_set_salience_clamps_values(self, section):
        """Test salience values are clamped to [0, 1]."""
        entry = section.set_salience("high", 1.5)
        assert entry.score == 1.0

        entry = section.set_salience("low", -0.5)
        assert entry.score == 0.0

    def test_get_salience(self, section):
        """Test getting salience for an entity."""
        section.set_salience("entity-1", 0.75)

        score = section.get_salience("entity-1")
        assert score == 0.75

    def test_get_salience_nonexistent(self, section):
        """Test getting salience for nonexistent entity."""
        score = section.get_salience("nonexistent")
        assert score == 0.0

    def test_boost_salience(self, section):
        """Test boosting salience."""
        section.set_salience("entity-1", 0.5)

        new_score = section.boost_salience("entity-1", 0.3)
        assert new_score == 0.8

    def test_boost_salience_caps_at_one(self, section):
        """Test boost doesn't exceed 1.0."""
        section.set_salience("entity-1", 0.9)

        new_score = section.boost_salience("entity-1", 0.5)
        assert new_score == 1.0

    def test_boost_salience_creates_entry(self, section):
        """Test boosting nonexistent entity creates entry."""
        new_score = section.boost_salience("new-entity", 0.4)
        assert new_score == 0.4

        # Should exist now
        assert section.get_salience("new-entity") == 0.4

    def test_decay_salience(self, section):
        """Test decay reduces all salience values."""
        section.set_salience("entity-1", 1.0, decay_rate=0.1)
        section.set_salience("entity-2", 0.5, decay_rate=0.1)

        removed = section.decay_salience()

        # Should not remove any yet
        assert removed == 0
        # Values should be reduced
        assert section.get_salience("entity-1") == 0.9
        assert section.get_salience("entity-2") == 0.45

    def test_decay_removes_low_salience(self, section):
        """Test decay removes very low salience entities."""
        # MIN_SALIENCE is 0.01, so after decay: 0.02 * (1-0.9) = 0.002 < 0.01
        section.set_salience("fading", 0.02, decay_rate=0.9)

        removed = section.decay_salience()
        assert removed == 1
        assert section.get_salience("fading") == 0.0

    def test_list_salient_entities(self, section):
        """Test listing salient entities."""
        section.set_salience("a", 0.3)
        section.set_salience("b", 0.9)
        section.set_salience("c", 0.5)

        entries = section.list_salient_entities()
        assert len(entries) == 3
        # Should be sorted by score descending
        assert entries[0].score == 0.9
        assert entries[1].score == 0.5
        assert entries[2].score == 0.3

    def test_list_salient_entities_with_min_score(self, section):
        """Test listing with minimum score filter."""
        section.set_salience("low", 0.1)
        section.set_salience("high", 0.9)

        entries = section.list_salient_entities(min_score=0.5)
        assert len(entries) == 1
        assert entries[0].entity_id == "high"

    def test_get_most_salient_entity(self, section):
        """Test getting most salient entity."""
        section.set_salience("low", 0.2)
        section.set_salience("high", 0.95)

        entity_id = section.get_most_salient_entity()
        assert entity_id == "high"

    def test_get_most_salient_entity_empty(self, section):
        """Test most salient entity when empty."""
        entity_id = section.get_most_salient_entity()
        assert entity_id is None


# =============================================================================
# Topic Stack Tests
# =============================================================================


class TestTopicStack:
    """Test topic stack management."""

    def test_push_topic(self, section):
        """Test pushing a topic."""
        topic = section.push_topic("weather")

        assert topic.id != ""
        assert topic.name == "weather"
        assert topic.salience == 0.5  # default

    def test_push_topic_with_salience(self, section):
        """Test pushing topic with salience."""
        topic = section.push_topic("urgent", salience=0.9)

        assert topic.salience == 0.9

    def test_push_primary_topic(self, section):
        """Test pushing primary topic."""
        topic = section.push_topic("main", is_primary=True)

        assert topic.is_primary is True

    def test_push_primary_demotes_existing(self, section):
        """Test new primary demotes existing primary."""
        t1 = section.push_topic("first", is_primary=True)
        t2 = section.push_topic("second", is_primary=True)

        # Get t1 from stack to check updated state
        topics = section.list_topics()
        first = next(t for t in topics if t.id == t1.id)
        second = next(t for t in topics if t.id == t2.id)

        assert first.is_primary is False
        assert second.is_primary is True

    def test_pop_topic(self, section):
        """Test popping topic from stack."""
        section.push_topic("first")
        section.push_topic("second")

        t = section.pop_topic()
        assert t.name == "second"

        t = section.pop_topic()
        assert t.name == "first"

    def test_pop_topic_empty(self, section):
        """Test popping from empty stack."""
        t = section.pop_topic()
        assert t is None

    def test_peek_topic(self, section):
        """Test peeking at top topic."""
        section.push_topic("first")
        section.push_topic("second")

        t = section.peek_topic()
        assert t.name == "second"

        # Should still be there
        t2 = section.peek_topic()
        assert t2.name == "second"

    def test_peek_topic_empty(self, section):
        """Test peeking at empty stack."""
        t = section.peek_topic()
        assert t is None

    def test_get_primary_topic(self, section):
        """Test getting primary topic."""
        section.push_topic("not primary")
        section.push_topic("primary", is_primary=True)
        section.push_topic("also not primary")

        primary = section.get_primary_topic()
        assert primary.name == "primary"

    def test_get_primary_topic_fallback(self, section):
        """Test primary topic falls back to top of stack."""
        section.push_topic("first")
        section.push_topic("second")

        primary = section.get_primary_topic()
        assert primary.name == "second"

    def test_list_topics(self, section):
        """Test listing topics (most recent first)."""
        section.push_topic("first")
        section.push_topic("second")
        section.push_topic("third")

        topics = section.list_topics()
        assert len(topics) == 3
        assert topics[0].name == "third"
        assert topics[1].name == "second"
        assert topics[2].name == "first"

    def test_set_primary_topic(self, section):
        """Test setting a topic as primary."""
        t1 = section.push_topic("one")
        t2 = section.push_topic("two")

        result = section.set_primary_topic(t1.id)
        assert result is True

        primary = section.get_primary_topic()
        assert primary.id == t1.id


# =============================================================================
# Intent Management Tests
# =============================================================================


class TestIntentManagement:
    """Test intent management."""

    def test_set_user_intent(self, section):
        """Test setting user intent."""
        section.set_user_intent("book_flight", 0.95)

        intent, conf = section.get_user_intent()
        assert intent == "book_flight"
        assert conf == 0.95

    def test_set_user_intent_default_confidence(self, section):
        """Test default confidence is 1.0."""
        section.set_user_intent("query")

        intent, conf = section.get_user_intent()
        assert intent == "query"
        assert conf == 1.0

    def test_get_user_intent_empty(self, section):
        """Test getting intent when not set."""
        intent, conf = section.get_user_intent()
        assert intent == ""
        assert conf == 0.0


# =============================================================================
# Turn Management Tests
# =============================================================================


class TestTurnManagement:
    """Test turn management."""

    def test_current_turn_property(self, section):
        """Test current turn starts at 0."""
        assert section.current_turn == 0

    def test_advance_turn(self, section):
        """Test advancing turn."""
        new_turn = section.advance_turn()
        assert new_turn == 1
        assert section.current_turn == 1

    def test_advance_turn_applies_decay(self, section):
        """Test advance_turn applies salience decay."""
        section.set_salience("entity-1", 1.0, decay_rate=0.1)

        section.advance_turn()

        assert section.get_salience("entity-1") == 0.9

    def test_advance_turn_updates_topic(self, section):
        """Test advance_turn updates active topic."""
        topic = section.push_topic("current")
        initial_turn = topic.last_turn

        section.advance_turn()

        # The topic's last_turn should be updated
        current_topic = section.peek_topic()
        assert current_topic.last_turn == section.current_turn


# =============================================================================
# FlatBuffer Serialization Tests
# =============================================================================


class TestFlatBufferSerialization:
    """Test FlatBuffer serialization."""

    def test_empty_section_roundtrip(self, section):
        """Test empty section serializes and deserializes."""
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        assert section2.current_turn == section.current_turn

    def test_populated_section_roundtrip(self, populated_section):
        """Test populated section roundtrip."""
        data = populated_section.to_flatbuffer()

        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        assert len(section2.list_referents()) == len(populated_section.list_referents())
        assert len(section2.list_questions()) == len(populated_section.list_questions())
        assert len(section2.list_salient_entities()) == len(
            populated_section.list_salient_entities()
        )
        assert len(section2.list_topics()) == len(populated_section.list_topics())

    def test_referents_serialization(self, section):
        """Test referents serialize correctly."""
        section.add_referent("the car", "vehicle-123", "vehicle", salience=0.85)

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        refs = section2.list_referents()
        assert len(refs) == 1
        assert refs[0].text == "the car"
        assert refs[0].entity_id == "vehicle-123"
        assert refs[0].entity_type == "vehicle"
        assert abs(refs[0].salience - 0.85) < 0.01

    def test_questions_serialization(self, section):
        """Test questions serialize correctly."""
        q = section.push_question("What color?", "user", priority=5)
        section.answer_question(q.id, "Blue")

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        questions = section2.list_questions()
        assert len(questions) == 1
        assert questions[0].text == "What color?"
        assert questions[0].asked_by == "user"
        assert questions[0].priority == 5
        assert questions[0].status == QuestionStatus.ANSWERED
        assert questions[0].answer_summary == "Blue"

    def test_salience_map_serialization(self, section):
        """Test salience map serializes correctly."""
        section.set_salience("entity-1", 0.8, decay_rate=0.15)

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        entries = section2.list_salient_entities()
        assert len(entries) == 1
        assert entries[0].entity_id == "entity-1"
        assert abs(entries[0].score - 0.8) < 0.01
        assert abs(entries[0].decay_rate - 0.15) < 0.01

    def test_topics_serialization(self, section):
        """Test topics serialize correctly."""
        section.push_topic("main topic", salience=0.9, is_primary=True)

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        topics = section2.list_topics()
        assert len(topics) == 1
        assert topics[0].name == "main topic"
        assert abs(topics[0].salience - 0.9) < 0.01
        assert topics[0].is_primary is True

    def test_intent_serialization(self, section):
        """Test intent serializes correctly."""
        section.set_user_intent("inquiry", 0.95)

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        intent, conf = section2.get_user_intent()
        assert intent == "inquiry"
        assert abs(conf - 0.95) < 0.01

    def test_serialization_caching(self, section):
        """Test serialization uses caching."""
        section.add_referent("test", "id-1", "type")

        data1 = section.to_flatbuffer()
        data2 = section.to_flatbuffer()

        # Should be same bytes (cached)
        assert data1 == data2

    def test_cache_invalidation(self, section):
        """Test cache is invalidated on mutation."""
        section.add_referent("test", "id-1", "type")
        data1 = section.to_flatbuffer()

        section.add_referent("test2", "id-2", "type")
        data2 = section.to_flatbuffer()

        # Should be different (new data added)
        assert data1 != data2

    def test_serialization_size_within_budget(self, populated_section):
        """Test serialized size is within budget."""
        data = populated_section.to_flatbuffer()
        assert len(data) <= populated_section.budget_bytes


# =============================================================================
# Legacy API Tests
# =============================================================================


class TestLegacyAPI:
    """Test legacy API compatibility."""

    def test_create_task(self, section):
        """Test create_task maps to push_question."""
        task = section.create_task("Do something", owner="agent-1", priority=5)

        assert task.text == "Do something"
        assert task.asked_by == "agent-1"
        assert task.priority == 5

    def test_get_task(self, section):
        """Test get maps to get_question."""
        task = section.create_task("Find me")

        found = section.get(task.id)
        assert found is not None
        assert found.text == "Find me"

    def test_list_tasks(self, section):
        """Test list returns all questions."""
        section.create_task("Task 1")
        section.create_task("Task 2")

        tasks = section.list()
        assert len(tasks) == 2

    def test_update_status(self, section):
        """Test update_status updates question status."""
        task = section.create_task("Update me")

        # update_status expects string keys like "complete", not enum values
        result = section.update_status(task.id, "complete")
        assert result is True

        task = section.get(task.id)
        assert task.status == QuestionStatus.ANSWERED

    def test_complete_task(self, section):
        """Test complete_task marks question answered."""
        task = section.create_task("Complete me")

        result = section.complete_task(task.id)
        assert result is True

        task = section.get(task.id)
        assert task.status == QuestionStatus.ANSWERED

    def test_fail_task(self, section):
        """Test fail_task marks question abandoned."""
        task = section.create_task("Fail me")

        result = section.fail_task(task.id, "Error")
        assert result is True

        task = section.get(task.id)
        assert task.status == QuestionStatus.ABANDONED

    def test_block_task(self, section):
        """Test block_task marks question deferred."""
        task = section.create_task("Block me")

        result = section.block_task(task.id, "Waiting")
        assert result is True

        task = section.get(task.id)
        assert task.status == QuestionStatus.DEFERRED

    def test_get_active(self, section):
        """Test get_active returns open questions."""
        section.create_task("Open")
        task2 = section.create_task("Closed")
        section.complete_task(task2.id)

        active = section.get_active()
        assert len(active) == 1

    def test_serialize_deserialize(self, section):
        """Test serialize/deserialize aliases."""
        section.add_referent("test", "id-1", "type")

        data = section.serialize()
        assert isinstance(data, bytes)

        section2 = ScoreboardSection()
        section2.deserialize(data)

        assert len(section2.list_referents()) == 1

    def test_apply_push_question(self, section):
        """Test apply with push_question operation."""
        result = section.apply("push_question", {"text": "What?", "asked_by": "user"})

        assert result.text == "What?"

    def test_apply_add_referent(self, section):
        """Test apply with add_referent operation."""
        result = section.apply(
            "add_referent",
            {"text": "the car", "entity_id": "v-1", "entity_type": "vehicle"},
        )

        assert result.text == "the car"

    def test_apply_set_salience(self, section):
        """Test apply with set_salience operation."""
        section.apply("set_salience", {"entity_id": "e-1", "score": 0.8})

        assert section.get_salience("e-1") == 0.8

    def test_apply_push_topic(self, section):
        """Test apply with push_topic operation."""
        result = section.apply(
            "push_topic", {"name": "weather", "salience": 0.7, "is_primary": True}
        )

        assert result.name == "weather"
        assert result.is_primary is True

    def test_apply_set_user_intent(self, section):
        """Test apply with set_user_intent operation."""
        section.apply("set_user_intent", {"intent": "query", "confidence": 0.9})

        intent, conf = section.get_user_intent()
        assert intent == "query"

    def test_apply_unknown_operation(self, section):
        """Test apply raises on unknown operation."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown_op", {})


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_strings(self, section):
        """Test empty strings are handled."""
        ref = section.add_referent("", "", "")

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        refs = section2.list_referents()
        assert len(refs) == 1
        assert refs[0].text == ""

    def test_unicode_content(self, section):
        """Test unicode content is preserved."""
        section.add_referent("日本語", "entity-jp", "text")
        section.push_question("¿Cómo estás?", "user")
        section.push_topic("Übung macht den Meister")
        section.set_user_intent("查询")

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        refs = section2.list_referents()
        assert refs[0].text == "日本語"

        questions = section2.list_questions()
        assert questions[0].text == "¿Cómo estás?"

        topics = section2.list_topics()
        assert topics[0].name == "Übung macht den Meister"

        intent, _ = section2.get_user_intent()
        assert intent == "查询"

    def test_special_characters(self, section):
        """Test special characters are handled."""
        section.add_referent("test\nwith\nnewlines", "id-1", "type")
        section.push_question("Tab\there", "user")

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        refs = section2.list_referents()
        assert "test\nwith\nnewlines" == refs[0].text

    def test_many_referents(self, section):
        """Test handling many referents."""
        for i in range(30):  # Schema suggests max ~30
            section.add_referent(f"ref-{i}", f"entity-{i}", "type")

        refs = section.list_referents()
        assert len(refs) == 30

        data = section.to_flatbuffer()
        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)

        assert len(section2.list_referents()) == 30

    def test_many_questions(self, section):
        """Test handling many questions."""
        for i in range(10):  # Schema suggests max ~10
            section.push_question(f"Question {i}?", "user")

        questions = section.list_questions()
        assert len(questions) == 10

    def test_many_topics(self, section):
        """Test handling many topics."""
        for i in range(10):  # Schema suggests max ~10
            section.push_topic(f"Topic {i}")

        topics = section.list_topics()
        assert len(topics) == 10

    def test_referent_with_salience_map(self, section):
        """Test referent creation updates salience map."""
        section.add_referent("test", "entity-1", "type", salience=0.7)

        # Salience map should be updated automatically
        score = section.get_salience("entity-1")
        assert score == 0.7


# =============================================================================
# Performance Tests
# =============================================================================


class TestPerformance:
    """Test performance requirements."""

    def test_serialization_performance_empty(self, section):
        """Test empty serialization is fast."""
        import time

        start = time.perf_counter()
        for _ in range(100):
            section.to_flatbuffer()
            section._invalidate_cache()  # Force re-serialization
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / 100) * 1_000_000
        assert avg_us < 1000  # Less than 1ms per operation

    def test_serialization_performance_populated(self, populated_section):
        """Test populated serialization is fast."""
        import time

        start = time.perf_counter()
        for _ in range(100):
            populated_section.to_flatbuffer()
            populated_section._invalidate_cache()
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / 100) * 1_000_000
        assert avg_us < 1000  # Less than 1ms per operation

    def test_deserialization_performance(self, populated_section):
        """Test deserialization is fast."""
        import time

        data = populated_section.to_flatbuffer()

        start = time.perf_counter()
        for _ in range(100):
            section2 = ScoreboardSection()
            section2.from_flatbuffer(data)
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / 100) * 1_000_000
        assert avg_us < 1000  # Less than 1ms per operation

    def test_lookup_performance(self, section):
        """Test lookup operations are fast."""
        import time

        # Add some data
        for i in range(20):
            section.add_referent(f"ref-{i}", f"entity-{i}", "type")
            section.set_salience(f"entity-{i}", 0.5)

        start = time.perf_counter()
        for _ in range(1000):
            section.get_referent_by_entity("entity-10")
            section.get_salience("entity-10")
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / 1000) * 1_000_000
        assert avg_us < 100  # Less than 100μs per operation


# =============================================================================
# DataClass Tests
# =============================================================================


class TestDataClasses:
    """Test data class definitions."""

    def test_referent_dataclass(self):
        """Test Referent dataclass."""
        ref = Referent(
            id="ref-1",
            text="the car",
            entity_id="v-1",
            entity_type="vehicle",
            salience=0.8,
            first_mentioned_turn=0,
            last_mentioned_turn=1,
            mention_count=2,
        )

        assert ref.id == "ref-1"
        assert ref.text == "the car"
        assert ref.salience == 0.8

    def test_question_dataclass(self):
        """Test Question dataclass."""
        q = Question(
            id="q-1",
            text="What?",
            status=QuestionStatus.OPEN,
            asked_by="user",
            asked_at_turn=0,
            priority=5,
        )

        assert q.id == "q-1"
        assert q.text == "What?"
        assert q.status == QuestionStatus.OPEN

    def test_topic_dataclass(self):
        """Test Topic dataclass."""
        t = Topic(
            id="t-1",
            name="weather",
            salience=0.7,
            is_primary=True,
        )

        assert t.id == "t-1"
        assert t.name == "weather"
        assert t.is_primary is True

    def test_salience_entry_dataclass(self):
        """Test SalienceEntry dataclass."""
        entry = SalienceEntry(
            entity_id="e-1",
            score=0.8,
            decay_rate=0.1,
        )

        assert entry.entity_id == "e-1"
        assert entry.score == 0.8
        assert entry.decay_rate == 0.1

    def test_question_status_enum(self):
        """Test QuestionStatus enum values."""
        assert QuestionStatus.OPEN == 0
        assert QuestionStatus.ANSWERED == 1
        assert QuestionStatus.ABANDONED == 2
        assert QuestionStatus.DEFERRED == 3

    def test_task_status_enum(self):
        """Test TaskStatus enum (legacy)."""
        assert TaskStatus.PENDING == 0
        assert TaskStatus.IN_PROGRESS == 1
        assert TaskStatus.BLOCKED == 2
        assert TaskStatus.COMPLETE == 3
        assert TaskStatus.FAILED == 4
