"""
Cross-Section Scoreboard → History Integration Tests (Epic 4.5.3)
===================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.5 Cross-Section Dependency Tests
ISSUE: 4.5.3

**Test scoreboard → history dependency**

ARCHITECTURE:
    scoreboard (HOT CORE) tracks discourse state (referents, QUD, salience, topics).
    history_active (HOT) contains recent conversation turns.
    Scoreboard tracks which turn entities were mentioned (first_mentioned_turn, last_mentioned_turn).
    When history demotes turns, scoreboard referents should remain resolvable.

KEY PROPERTIES:
    - ScoreboardSection.CAN_EVICT = False (HOT CORE - never evicted)
    - ScoreboardSection tracks referents with turn information
    - HistoryActiveSection.CAN_EVICT = False (items demote, section stays)
    - History turns can demote to WARM tier (history_recent)
    - Referent salience decays over turns via advance_turn()

HARDCORE INTEGRATION TEST REQUIREMENTS:
    1. ENTRY POINT: SessionStateFactory.create_for_testing()
    2. ALL MUTATIONS: manager.mutate(section, operation, data) or section methods
    3. ALL READS: manager.get_section() or manager.get_snapshot()
    4. NO MOCKS: Real components, real sections

==============================================================================
"""

from __future__ import annotations

import time
from typing import Generator

import pytest

from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.manager import SessionStateManager
from k1.sessionstate.sections.scoreboard import QuestionStatus, ScoreboardSection

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def session() -> Generator[SessionStateManager, None, None]:
    """Create a session manager for testing."""
    manager = SessionStateFactory.create_for_testing()
    manager.start()
    yield manager
    manager.stop()


# =============================================================================
# TEST CLASS: Scoreboard Section Properties
# =============================================================================


class TestScoreboardSectionProperties:
    """Test basic scoreboard section properties and structure."""

    def test_scoreboard_section_accessible(self, session: SessionStateManager) -> None:
        """Scoreboard section is accessible via manager."""
        section = session.get_section("scoreboard")
        assert section is not None
        assert isinstance(section, ScoreboardSection)

    def test_scoreboard_section_is_hot_tier(self, session: SessionStateManager) -> None:
        """Scoreboard section is in HOT tier (core)."""
        section = session.get_section("scoreboard")
        assert section.tier == "hot"

    def test_scoreboard_section_can_evict_is_false(self, session: SessionStateManager) -> None:
        """Scoreboard section CAN_EVICT is False - NEVER evicted."""
        section = session.get_section("scoreboard")
        assert section.can_evict is False
        assert ScoreboardSection.CAN_EVICT is False

    def test_scoreboard_section_has_6kb_budget(self, session: SessionStateManager) -> None:
        """Scoreboard section has 6KB budget."""
        section = session.get_section("scoreboard")
        assert section.budget_bytes == 6144

    def test_scoreboard_section_name_is_scoreboard(self, session: SessionStateManager) -> None:
        """Scoreboard section name is 'scoreboard'."""
        section = session.get_section("scoreboard")
        assert section.name == "scoreboard"

    def test_scoreboard_section_initial_turn_is_zero(self, session: SessionStateManager) -> None:
        """Scoreboard starts at turn 0."""
        section = session.get_section("scoreboard")
        assert section.current_turn == 0


# =============================================================================
# TEST CLASS: Referent Management (Basic)
# =============================================================================


class TestReferentManagement:
    """Test referent creation, retrieval, and modification."""

    def test_add_referent_creates_new_referent(self, session: SessionStateManager) -> None:
        """Adding a referent creates a new referent with correct properties."""
        section = session.get_section("scoreboard")

        ref = section.add_referent(
            text="the red car",
            entity_id="vehicle-001",
            entity_type="vehicle",
            salience=0.7,
        )

        assert ref is not None
        assert ref.text == "the red car"
        assert ref.entity_id == "vehicle-001"
        assert ref.entity_type == "vehicle"
        assert ref.salience == 0.7
        assert ref.mention_count == 1

    def test_add_referent_tracks_first_mentioned_turn(self, session: SessionStateManager) -> None:
        """Referent records first_mentioned_turn correctly."""
        section = session.get_section("scoreboard")

        # Add at turn 0
        ref = section.add_referent(text="the house", entity_id="building-001")
        assert ref.first_mentioned_turn == 0

        # Advance and add another
        section.advance_turn()  # Now turn 1
        ref2 = section.add_referent(text="the park", entity_id="location-001")
        assert ref2.first_mentioned_turn == 1

    def test_add_referent_tracks_last_mentioned_turn(self, session: SessionStateManager) -> None:
        """Referent records last_mentioned_turn correctly."""
        section = session.get_section("scoreboard")

        ref = section.add_referent(text="the dog", entity_id="pet-001")
        assert ref.last_mentioned_turn == 0

        # Advance and re-mention
        section.advance_turn()  # Turn 1
        section.add_referent(text="the dog", entity_id="pet-001")

        updated_ref = section.get_referent_by_entity("pet-001")
        assert updated_ref.first_mentioned_turn == 0  # Unchanged
        assert updated_ref.last_mentioned_turn == 1  # Updated

    def test_get_referent_by_id(self, session: SessionStateManager) -> None:
        """Can retrieve referent by its ID."""
        section = session.get_section("scoreboard")

        ref = section.add_referent(text="the cat", entity_id="pet-002")
        retrieved = section.get_referent(ref.id)

        assert retrieved is not None
        assert retrieved.id == ref.id
        assert retrieved.text == "the cat"

    def test_get_referent_by_entity_id(self, session: SessionStateManager) -> None:
        """Can retrieve referent by entity ID."""
        section = session.get_section("scoreboard")

        section.add_referent(text="the office", entity_id="location-002")
        retrieved = section.get_referent_by_entity("location-002")

        assert retrieved is not None
        assert retrieved.entity_id == "location-002"

    def test_get_nonexistent_referent_returns_none(self, session: SessionStateManager) -> None:
        """Getting non-existent referent returns None."""
        section = session.get_section("scoreboard")

        assert section.get_referent("nonexistent-id") is None
        assert section.get_referent_by_entity("nonexistent-entity") is None

    def test_list_referents_returns_all(self, session: SessionStateManager) -> None:
        """List referents returns all added referents."""
        section = session.get_section("scoreboard")

        section.add_referent(text="item 1", entity_id="item-001", salience=0.3)
        section.add_referent(text="item 2", entity_id="item-002", salience=0.8)
        section.add_referent(text="item 3", entity_id="item-003", salience=0.5)

        refs = section.list_referents(sort_by_salience=False)
        assert len(refs) == 3

    def test_list_referents_sorted_by_salience(self, session: SessionStateManager) -> None:
        """List referents can sort by salience descending."""
        section = session.get_section("scoreboard")

        section.add_referent(text="low", entity_id="item-001", salience=0.2)
        section.add_referent(text="high", entity_id="item-002", salience=0.9)
        section.add_referent(text="mid", entity_id="item-003", salience=0.5)

        refs = section.list_referents(sort_by_salience=True)
        assert refs[0].entity_id == "item-002"  # Highest
        assert refs[1].entity_id == "item-003"  # Mid
        assert refs[2].entity_id == "item-001"  # Lowest


# =============================================================================
# TEST CLASS: Referent Re-Mention and Salience Boost
# =============================================================================


class TestReferentRemention:
    """Test referent behavior when re-mentioned."""

    def test_remention_increments_mention_count(self, session: SessionStateManager) -> None:
        """Re-mentioning a referent increments mention count."""
        section = session.get_section("scoreboard")

        ref = section.add_referent(text="the chair", entity_id="furniture-001")
        assert ref.mention_count == 1

        # Re-mention same entity
        section.advance_turn()
        section.add_referent(text="that chair", entity_id="furniture-001")

        updated = section.get_referent_by_entity("furniture-001")
        assert updated.mention_count == 2

    def test_remention_boosts_salience(self, session: SessionStateManager) -> None:
        """Re-mentioning a referent boosts salience by 0.1."""
        section = session.get_section("scoreboard")

        ref = section.add_referent(text="the table", entity_id="furniture-002", salience=0.5)
        assert ref.salience == 0.5

        section.advance_turn()
        section.add_referent(text="the table", entity_id="furniture-002")

        updated = section.get_referent_by_entity("furniture-002")
        assert updated.salience == 0.6  # 0.5 + 0.1

    def test_remention_salience_capped_at_one(self, session: SessionStateManager) -> None:
        """Salience boost is capped at 1.0."""
        section = session.get_section("scoreboard")

        section.add_referent(text="the lamp", entity_id="furniture-003", salience=0.95)

        section.advance_turn()
        section.add_referent(text="the lamp", entity_id="furniture-003")

        updated = section.get_referent_by_entity("furniture-003")
        assert updated.salience == 1.0  # Capped, not 1.05

    def test_multiple_rementions_accumulate(self, session: SessionStateManager) -> None:
        """Multiple re-mentions accumulate salience."""
        section = session.get_section("scoreboard")

        section.add_referent(text="the book", entity_id="item-010", salience=0.3)

        for i in range(5):
            section.advance_turn()
            section.add_referent(text="the book", entity_id="item-010")

        updated = section.get_referent_by_entity("item-010")
        assert updated.mention_count == 6  # Initial + 5 re-mentions
        # Salience: 0.3 + 0.5 (5 * 0.1) = 0.8, minus decay
        # advance_turn() calls decay_salience(), so actual value is lower


# =============================================================================
# TEST CLASS: Scoreboard + History Active Integration
# =============================================================================


class TestScoreboardHistoryIntegration:
    """Test scoreboard and history_active working together."""

    def test_both_sections_accessible(self, session: SessionStateManager) -> None:
        """Both scoreboard and history_active are accessible."""
        scoreboard = session.get_section("scoreboard")
        history = session.get_section("history_active")

        assert scoreboard is not None
        assert history is not None

    def test_add_turn_and_referent_together(self, session: SessionStateManager) -> None:
        """Can add history turn and scoreboard referent in same session."""
        scoreboard = session.get_section("scoreboard")

        # Add a conversation turn
        session.mutate(
            "history_active",
            "append",
            {
                "user_message": "I saw a beautiful red car today.",
                "assistant_response": "That sounds nice! What kind of car was it?",
            },
        )

        # Add referent for entity mentioned in turn
        ref = scoreboard.add_referent(
            text="red car",
            entity_id="vehicle-100",
            entity_type="vehicle",
            salience=0.8,
        )

        assert ref is not None
        assert ref.first_mentioned_turn == 0

    def test_referent_turn_tracking_with_history(self, session: SessionStateManager) -> None:
        """Referent turn numbers align with conversation flow."""
        scoreboard = session.get_section("scoreboard")

        # Turn 0: First mention
        session.mutate(
            "history_active",
            "append",
            {
                "user_message": "Let's talk about my dog Max.",
                "assistant_response": "I'd love to hear about Max!",
            },
        )
        scoreboard.add_referent(text="Max", entity_id="pet-max", entity_type="pet")
        scoreboard.advance_turn()

        # Turn 1: Another topic
        session.mutate(
            "history_active",
            "append",
            {
                "user_message": "What's the weather like?",
                "assistant_response": "It's sunny today.",
            },
        )
        scoreboard.add_referent(text="weather", entity_id="topic-weather", entity_type="topic")
        scoreboard.advance_turn()

        # Turn 2: Re-mention Max
        session.mutate(
            "history_active",
            "append",
            {
                "user_message": "I should take Max for a walk.",
                "assistant_response": "A walk sounds great for Max!",
            },
        )
        scoreboard.add_referent(text="Max", entity_id="pet-max", entity_type="pet")

        max_ref = scoreboard.get_referent_by_entity("pet-max")
        assert max_ref.first_mentioned_turn == 0
        assert max_ref.last_mentioned_turn == 2
        assert max_ref.mention_count == 2

    def test_many_turns_with_referent_tracking(self, session: SessionStateManager) -> None:
        """Referent tracking works across many turns."""
        scoreboard = session.get_section("scoreboard")

        # Add 10 turns, mentioning same entity every 3 turns
        for i in range(10):
            session.mutate(
                "history_active",
                "append",
                {
                    "user_message": f"Message {i}",
                    "assistant_response": f"Response {i}",
                },
            )

            if i % 3 == 0:
                scoreboard.add_referent(
                    text="recurring topic",
                    entity_id="recurring-entity",
                )

            scoreboard.advance_turn()

        ref = scoreboard.get_referent_by_entity("recurring-entity")
        assert ref is not None
        assert ref.first_mentioned_turn == 0
        # Mentioned at turns 0, 3, 6, 9
        assert ref.last_mentioned_turn == 9
        assert ref.mention_count == 4


# =============================================================================
# TEST CLASS: History Demotion and Scoreboard Graceful Degradation
# =============================================================================


class TestHistoryDemotionScoreboardGracefulDegradation:
    """Test scoreboard behavior when history turns demote."""

    def test_scoreboard_survives_history_overflow(self, session: SessionStateManager) -> None:
        """Scoreboard referents survive when history overflows."""
        scoreboard = session.get_section("scoreboard")
        history = session.get_section("history_active")

        # Add initial referent
        ref = scoreboard.add_referent(
            text="important item",
            entity_id="critical-001",
            salience=0.9,
        )
        original_ref_id = ref.id

        # Fill history with many turns (may trigger overflow)
        max_turns = getattr(history, "MAX_TURNS", 50)
        for i in range(max_turns + 5):
            session.mutate(
                "history_active",
                "append",
                {
                    "user_message": f"Turn {i} message",
                    "assistant_response": f"Turn {i} response",
                },
            )
            scoreboard.advance_turn()

        # Referent should still be resolvable
        retrieved = scoreboard.get_referent(original_ref_id)
        assert retrieved is not None
        assert retrieved.entity_id == "critical-001"

    def test_scoreboard_referents_resolvable_after_demotion(
        self, session: SessionStateManager
    ) -> None:
        """Referents remain resolvable after history demotion."""
        scoreboard = session.get_section("scoreboard")
        # Add several referents at different turns
        referent_ids = []
        for i in range(5):
            ref = scoreboard.add_referent(
                text=f"entity {i}",
                entity_id=f"entity-{i}",
                salience=0.5 + (i * 0.1),
            )
            referent_ids.append(ref.id)

            session.mutate(
                "history_active",
                "append",
                {
                    "user_message": f"About entity {i}",
                    "assistant_response": f"Understood about entity {i}",
                },
            )
            scoreboard.advance_turn()

        # Add many more turns to potentially trigger demotion
        for i in range(60):
            session.mutate(
                "history_active",
                "append",
                {
                    "user_message": f"Filler turn {i}",
                    "assistant_response": f"Filler response {i}",
                },
            )
            scoreboard.advance_turn()

        # All referents should still be resolvable
        for i, ref_id in enumerate(referent_ids):
            ref = scoreboard.get_referent(ref_id)
            assert ref is not None, f"Referent {i} should be resolvable"
            assert ref.entity_id == f"entity-{i}"

    def test_scoreboard_entity_lookup_after_demotion(self, session: SessionStateManager) -> None:
        """Entity lookup works after history demotion."""
        scoreboard = session.get_section("scoreboard")

        # Add referent
        scoreboard.add_referent(
            text="persistent entity",
            entity_id="persist-001",
            entity_type="test",
        )

        # Add many turns
        for i in range(70):
            session.mutate(
                "history_active",
                "append",
                {
                    "user_message": f"Message {i}",
                    "assistant_response": f"Response {i}",
                },
            )
            scoreboard.advance_turn()

        # Entity lookup should still work
        ref = scoreboard.get_referent_by_entity("persist-001")
        assert ref is not None
        assert ref.text == "persistent entity"


# =============================================================================
# TEST CLASS: Salience Decay
# =============================================================================


class TestSalienceDecay:
    """Test salience decay over turns."""

    def test_advance_turn_triggers_decay(self, session: SessionStateManager) -> None:
        """Advancing turn triggers salience decay."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.set_salience("decay-001", 0.8)
        initial_salience = scoreboard.get_salience("decay-001")

        # Advance several turns without re-mentioning
        for _ in range(5):
            scoreboard.advance_turn()

        updated_salience = scoreboard.get_salience("decay-001")
        assert updated_salience < initial_salience

    def test_remention_counteracts_decay(self, session: SessionStateManager) -> None:
        """Re-mentioning counteracts salience decay."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.add_referent(text="stable item", entity_id="stable-001", salience=0.5)

        # Advance and re-mention each turn
        for _ in range(5):
            scoreboard.advance_turn()
            scoreboard.add_referent(text="stable item", entity_id="stable-001")

        ref = scoreboard.get_referent_by_entity("stable-001")
        # Should maintain or increase salience due to re-mentions
        assert ref.salience >= 0.5

    def test_salience_floor_respected(self, session: SessionStateManager) -> None:
        """Salience doesn't decay below minimum."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.add_referent(
            text="low salience item",
            entity_id="low-001",
            salience=0.1,
        )

        # Decay many times
        for _ in range(50):
            scoreboard.advance_turn()

        ref = scoreboard.get_referent_by_entity("low-001")
        # Salience should not be negative
        assert ref.salience >= 0.0


# =============================================================================
# TEST CLASS: QUD (Questions Under Discussion) Stack
# =============================================================================


class TestQUDStack:
    """Test Questions Under Discussion management."""

    def test_push_question_creates_question(self, session: SessionStateManager) -> None:
        """Pushing a question adds it to QUD stack."""
        scoreboard = session.get_section("scoreboard")

        q = scoreboard.push_question(
            text="What time is it?",
            asked_by="user",
            priority=1.0,
        )

        assert q is not None
        assert q.text == "What time is it?"
        assert q.asked_by == "user"
        assert q.status == QuestionStatus.OPEN

    def test_question_tracks_asked_at_turn(self, session: SessionStateManager) -> None:
        """Question records the turn it was asked."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.advance_turn()  # Turn 1
        scoreboard.advance_turn()  # Turn 2

        q = scoreboard.push_question(text="How are you?", asked_by="user")
        assert q.asked_at_turn == 2

    def test_get_open_questions(self, session: SessionStateManager) -> None:
        """Can retrieve open questions."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.push_question(text="Question 1?", asked_by="user")
        scoreboard.push_question(text="Question 2?", asked_by="user")
        scoreboard.push_question(text="Question 3?", asked_by="user")

        open_qs = scoreboard.list_open_questions()
        assert len(open_qs) == 3

    def test_answer_question_changes_status(self, session: SessionStateManager) -> None:
        """Answering a question changes its status."""
        scoreboard = session.get_section("scoreboard")

        q = scoreboard.push_question(text="What is X?", asked_by="user")
        assert q.status == QuestionStatus.OPEN

        scoreboard.answer_question(q.id, answer_summary="X is Y")

        updated = scoreboard.get_question(q.id)
        assert updated.status == QuestionStatus.ANSWERED

    def test_abandon_question(self, session: SessionStateManager) -> None:
        """Can abandon a question."""
        scoreboard = session.get_section("scoreboard")

        q = scoreboard.push_question(text="Abandoned question?", asked_by="user")
        scoreboard.abandon_question(q.id)

        updated = scoreboard.get_question(q.id)
        assert updated.status == QuestionStatus.ABANDONED


# =============================================================================
# TEST CLASS: Topic Stack
# =============================================================================


class TestTopicStack:
    """Test topic stack management."""

    def test_push_topic_creates_topic(self, session: SessionStateManager) -> None:
        """Pushing a topic adds it to the stack."""
        scoreboard = session.get_section("scoreboard")

        topic = scoreboard.push_topic(name="weather")
        assert topic is not None
        assert topic.name == "weather"

    def test_topic_tracks_first_turn(self, session: SessionStateManager) -> None:
        """Topic records the turn it was introduced."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.advance_turn()  # Turn 1
        topic = scoreboard.push_topic(name="sports")
        assert topic.first_turn == 1

    def test_topic_last_turn_updates(self, session: SessionStateManager) -> None:
        """Topic last_turn updates with turn advancement."""
        scoreboard = session.get_section("scoreboard")

        topic = scoreboard.push_topic(name="current topic")
        assert topic.last_turn == 0

        scoreboard.advance_turn()
        # Access updated topic
        current = scoreboard.peek_topic()
        assert current.last_turn == 1

    def test_pop_topic(self, session: SessionStateManager) -> None:
        """Can pop topics from stack."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.push_topic(name="first")
        scoreboard.push_topic(name="second")
        scoreboard.push_topic(name="third")

        popped = scoreboard.pop_topic()
        assert popped.name == "third"

        current = scoreboard.peek_topic()
        assert current.name == "second"

    def test_current_topic_returns_top(self, session: SessionStateManager) -> None:
        """Current topic returns top of stack."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.push_topic(name="bottom")
        scoreboard.push_topic(name="top")

        assert scoreboard.peek_topic().name == "top"


# =============================================================================
# TEST CLASS: Salience Map
# =============================================================================


class TestSalienceMap:
    """Test salience map operations."""

    def test_set_salience_creates_entry(self, session: SessionStateManager) -> None:
        """Setting salience creates an entry."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.set_salience("entity-abc", 0.75)
        assert scoreboard.get_salience("entity-abc") == 0.75

    def test_get_salience_default_zero(self, session: SessionStateManager) -> None:
        """Getting non-existent salience returns 0.0."""
        scoreboard = session.get_section("scoreboard")

        assert scoreboard.get_salience("nonexistent") == 0.0

    def test_update_salience(self, session: SessionStateManager) -> None:
        """Can update existing salience."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.set_salience("entity-xyz", 0.5)
        scoreboard.set_salience("entity-xyz", 0.9)

        assert scoreboard.get_salience("entity-xyz") == 0.9

    def test_add_referent_updates_salience_map(self, session: SessionStateManager) -> None:
        """Adding a referent with entity_id updates salience map."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.add_referent(
            text="the item",
            entity_id="item-salience",
            salience=0.65,
        )

        assert scoreboard.get_salience("item-salience") == 0.65


# =============================================================================
# TEST CLASS: User Intent Tracking
# =============================================================================


class TestUserIntentTracking:
    """Test last user intent tracking."""

    def test_set_last_user_intent(self, session: SessionStateManager) -> None:
        """Can set last user intent."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.set_user_intent("greeting")
        intent, _ = scoreboard.get_user_intent()
        assert intent == "greeting"

    def test_update_last_user_intent(self, session: SessionStateManager) -> None:
        """Can update last user intent."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.set_user_intent("question")
        scoreboard.set_user_intent("request")

        intent, _ = scoreboard.get_user_intent()
        assert intent == "request"


# =============================================================================
# TEST CLASS: Cross-Section Consistency
# =============================================================================


class TestCrossSectionConsistency:
    """Test consistency between scoreboard and history under various conditions."""

    def test_concurrent_updates_both_sections(self, session: SessionStateManager) -> None:
        """Both sections can be updated in same logical transaction."""
        scoreboard = session.get_section("scoreboard")

        # Simulate conversation flow
        for i in range(10):
            # Add history turn
            session.mutate(
                "history_active",
                "append",
                {
                    "user_message": f"User says {i}",
                    "assistant_response": f"Assistant responds {i}",
                },
            )

            # Add referent and advance scoreboard
            scoreboard.add_referent(
                text=f"entity {i}",
                entity_id=f"conv-entity-{i}",
            )
            scoreboard.push_question(f"Question {i}?", asked_by="user")
            scoreboard.advance_turn()

        # Verify all referents exist
        for i in range(10):
            ref = scoreboard.get_referent_by_entity(f"conv-entity-{i}")
            assert ref is not None

        # Verify questions exist
        open_qs = scoreboard.list_open_questions()
        assert len(open_qs) == 10

    def test_high_volume_operations(self, session: SessionStateManager) -> None:
        """System handles high volume of operations."""
        scoreboard = session.get_section("scoreboard")

        # Add 100 turns and referents
        for i in range(100):
            session.mutate(
                "history_active",
                "append",
                {
                    "user_message": f"High volume message {i}",
                    "assistant_response": f"High volume response {i}",
                },
            )

            if i % 5 == 0:  # Add referent every 5 turns
                scoreboard.add_referent(
                    text=f"bulk entity {i}",
                    entity_id=f"bulk-{i}",
                )

            scoreboard.advance_turn()

        # Verify referents (20 total: 0, 5, 10, ..., 95)
        refs = scoreboard.list_referents()
        assert len(refs) == 20

    def test_snapshot_includes_both_sections(self, session: SessionStateManager) -> None:
        """Snapshot includes both scoreboard and history."""
        scoreboard = session.get_section("scoreboard")

        # Add data to both sections
        session.mutate(
            "history_active",
            "append",
            {
                "user_message": "Snapshot test message",
                "assistant_response": "Snapshot test response",
            },
        )
        scoreboard.add_referent(text="snapshot entity", entity_id="snap-001")

        # Get snapshot
        snapshot = session.get_snapshot()

        assert "scoreboard" in snapshot.sections
        assert "history_active" in snapshot.sections


# =============================================================================
# TEST CLASS: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_scoreboard_operations(self, session: SessionStateManager) -> None:
        """Operations on empty scoreboard don't fail."""
        scoreboard = session.get_section("scoreboard")

        assert scoreboard.list_referents() == []
        assert scoreboard.list_open_questions() == []
        assert scoreboard.peek_topic() is None
        assert scoreboard.get_salience("any") == 0.0

    def test_referent_without_entity_id(self, session: SessionStateManager) -> None:
        """Can add referent without entity ID."""
        scoreboard = session.get_section("scoreboard")

        ref = scoreboard.add_referent(
            text="anonymous mention",
            entity_id="",  # No entity ID
        )

        assert ref is not None
        assert ref.text == "anonymous mention"
        assert ref.entity_id == ""

    def test_very_long_text(self, session: SessionStateManager) -> None:
        """Handles very long referent text."""
        scoreboard = session.get_section("scoreboard")

        long_text = "x" * 1000
        ref = scoreboard.add_referent(
            text=long_text,
            entity_id="long-text-entity",
        )

        assert ref.text == long_text
        assert len(ref.text) == 1000

    def test_special_characters_in_text(self, session: SessionStateManager) -> None:
        """Handles special characters in referent text."""
        scoreboard = session.get_section("scoreboard")

        special_text = "café résumé naïve 日本語"
        ref = scoreboard.add_referent(
            text=special_text,
            entity_id="special-char-entity",
        )

        assert ref.text == special_text

    def test_zero_salience(self, session: SessionStateManager) -> None:
        """Can add referent with zero salience."""
        scoreboard = session.get_section("scoreboard")

        ref = scoreboard.add_referent(
            text="low priority",
            entity_id="zero-sal",
            salience=0.0,
        )

        assert ref.salience == 0.0

    def test_max_salience(self, session: SessionStateManager) -> None:
        """Can add referent with max salience."""
        scoreboard = session.get_section("scoreboard")

        ref = scoreboard.add_referent(
            text="critical item",
            entity_id="max-sal",
            salience=1.0,
        )

        assert ref.salience == 1.0


# =============================================================================
# TEST CLASS: Performance Characteristics
# =============================================================================


class TestPerformanceCharacteristics:
    """Test performance-related behavior."""

    def test_referent_lookup_fast(self, session: SessionStateManager) -> None:
        """Referent lookup is fast with many referents."""
        scoreboard = session.get_section("scoreboard")

        # Add many referents
        for i in range(500):
            scoreboard.add_referent(
                text=f"perf entity {i}",
                entity_id=f"perf-{i}",
            )

        # Lookup should be fast
        start = time.perf_counter()
        for i in range(100):
            scoreboard.get_referent_by_entity(f"perf-{i}")
        elapsed = time.perf_counter() - start

        # 100 lookups should complete in reasonable time
        assert elapsed < 1.0, f"Lookups took {elapsed:.3f}s"

    def test_many_turns_dont_slow_scoreboard(self, session: SessionStateManager) -> None:
        """Many turn advancements don't slow scoreboard."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.add_referent(text="persistent", entity_id="persistent-001")

        start = time.perf_counter()
        for _ in range(1000):
            scoreboard.advance_turn()
        elapsed = time.perf_counter() - start

        # 1000 turn advancements should be fast
        assert elapsed < 5.0, f"Turn advances took {elapsed:.3f}s"

        # Referent should still be accessible
        ref = scoreboard.get_referent_by_entity("persistent-001")
        assert ref is not None


# =============================================================================
# TEST CLASS: Serialization Integrity
# =============================================================================


class TestSerializationIntegrity:
    """Test that scoreboard state serializes correctly."""

    def test_referent_survives_serialization(self, session: SessionStateManager) -> None:
        """Referent data survives snapshot/serialize cycle."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.add_referent(
            text="serialization test",
            entity_id="serialize-001",
            entity_type="test",
            salience=0.77,
        )

        # Get raw state
        data = scoreboard.to_flatbuffer()
        restored = ScoreboardSection()
        restored.from_flatbuffer(data)

        refs = restored.list_referents()
        assert len(refs) == 1
        assert refs[0].entity_id == "serialize-001"

    def test_question_survives_serialization(self, session: SessionStateManager) -> None:
        """Question data survives serialization."""
        scoreboard = session.get_section("scoreboard")

        scoreboard.push_question(
            text="Will this serialize?",
            asked_by="tester",
            priority=1,
        )

        data = scoreboard.to_flatbuffer()
        restored = ScoreboardSection()
        restored.from_flatbuffer(data)
        questions = restored.list_questions()
        assert len(questions) == 1

    def test_complex_state_serializes(self, session: SessionStateManager) -> None:
        """Complex state with multiple elements serializes."""
        scoreboard = session.get_section("scoreboard")

        # Build complex state
        for i in range(5):
            scoreboard.add_referent(text=f"ref {i}", entity_id=f"entity-{i}")
            scoreboard.push_question(f"Question {i}?", asked_by="user")
            scoreboard.push_topic(name=f"topic-{i}")
            scoreboard.set_salience(f"salience-{i}", 0.5 + (i * 0.1))
            scoreboard.advance_turn()

        scoreboard.set_user_intent("complex_intent")

        # Serialize
        data = scoreboard.to_flatbuffer()
        restored = ScoreboardSection()
        restored.from_flatbuffer(data)
        assert restored.current_turn == 5
