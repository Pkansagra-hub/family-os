"""
Test suite for Intent Signal Models (Phase 2.1).

Validates IntentSignal dataclasses and type safety for GAP-001 intent routing.

Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 2
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.dream.intent_signals import (
    AnyIntentSignal,
    DecisionSignal,
    EmotionalSignal,
    IntentSignal,
    IntentSignalType,
    LessonSignal,
    MilestoneSignal,
    MilestoneType,
    QueryBoostSignal,
    ReminderSignal,
)


class TestIntentSignalType:
    """Test IntentSignalType enum."""

    def test_all_signal_types_defined(self) -> None:
        """Verify all 6 intent signal types are defined."""
        assert len(IntentSignalType) == 6

        expected = {"reminder", "decision", "lesson", "emotional", "milestone", "query_boost"}
        actual = {t.value for t in IntentSignalType}
        assert actual == expected

    def test_signal_type_string_enum(self) -> None:
        """IntentSignalType should be str enum for JSON serialization."""
        assert isinstance(IntentSignalType.REMINDER, str)
        assert IntentSignalType.REMINDER == "reminder"


class TestIntentSignalBase:
    """Test base IntentSignal dataclass."""

    def test_create_base_signal(self) -> None:
        """Can create base IntentSignal with required fields."""
        signal = IntentSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_123",
            confidence=0.85,
            source_text="Remind me to call Mom",
        )

        assert signal.signal_type == IntentSignalType.REMINDER
        assert signal.event_id == "evt_123"
        assert signal.confidence == 0.85
        assert signal.source_text == "Remind me to call Mom"
        assert signal.created_at_ms > 0

    def test_confidence_validation(self) -> None:
        """Confidence must be in [0.0, 1.0] range."""
        # Valid boundary values
        IntentSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_1",
            confidence=0.0,
            source_text="test",
        )
        IntentSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_2",
            confidence=1.0,
            source_text="test",
        )

        # Invalid values
        with pytest.raises(ValueError, match="confidence must be"):
            IntentSignal(
                signal_type=IntentSignalType.REMINDER,
                event_id="evt_3",
                confidence=-0.1,
                source_text="test",
            )

        with pytest.raises(ValueError, match="confidence must be"):
            IntentSignal(
                signal_type=IntentSignalType.REMINDER,
                event_id="evt_4",
                confidence=1.1,
                source_text="test",
            )


class TestReminderSignal:
    """Test ReminderSignal for set_reminder intent."""

    def test_create_reminder_signal(self) -> None:
        """Can create ReminderSignal with action and optional target_date."""
        signal = ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_reminder_1",
            confidence=0.9,
            source_text="Remind me to call Mom tomorrow at 3pm",
            action_description="call Mom",
            target_date=1736726400000,
        )

        assert signal.signal_type == IntentSignalType.REMINDER
        assert signal.action_description == "call Mom"
        assert signal.target_date == 1736726400000

    def test_reminder_signal_without_target_date(self) -> None:
        """ReminderSignal can be created without target_date."""
        signal = ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_reminder_2",
            confidence=0.8,
            source_text="Remind me to buy groceries",
            action_description="buy groceries",
        )

        assert signal.target_date is None

    def test_reminder_signal_type_override(self) -> None:
        """ReminderSignal should enforce REMINDER signal type."""
        signal = ReminderSignal(
            signal_type=IntentSignalType.DECISION,  # Wrong type
            event_id="evt_reminder_3",
            confidence=0.8,
            source_text="test",
            action_description="test",
        )

        # __post_init__ should override to REMINDER
        assert signal.signal_type == IntentSignalType.REMINDER


class TestDecisionSignal:
    """Test DecisionSignal for seek_advice intent."""

    def test_create_decision_signal(self) -> None:
        """Can create DecisionSignal with context and options."""
        signal = DecisionSignal(
            signal_type=IntentSignalType.DECISION,
            event_id="evt_decision_1",
            confidence=0.85,
            source_text="Should I take the job offer or stay?",
            decision_context="career decision about job offer",
            options_mentioned=["take the job offer", "stay at current company"],
        )

        assert signal.signal_type == IntentSignalType.DECISION
        assert signal.decision_context == "career decision about job offer"
        assert len(signal.options_mentioned) == 2

    def test_decision_signal_empty_options(self) -> None:
        """DecisionSignal can have empty options list."""
        signal = DecisionSignal(
            signal_type=IntentSignalType.DECISION,
            event_id="evt_decision_2",
            confidence=0.7,
            source_text="I need advice about something",
            decision_context="vague advice request",
        )

        assert signal.options_mentioned == []


class TestLessonSignal:
    """Test LessonSignal for reflect intent."""

    def test_create_lesson_signal(self) -> None:
        """Can create LessonSignal with lesson and topics."""
        signal = LessonSignal(
            signal_type=IntentSignalType.LESSON,
            event_id="evt_lesson_1",
            confidence=0.9,
            source_text="I learned that patience is important",
            lesson_description="patience is important",
            topic_entities=["patience", "personal growth"],
        )

        assert signal.signal_type == IntentSignalType.LESSON
        assert signal.lesson_description == "patience is important"
        assert "patience" in signal.topic_entities


class TestEmotionalSignal:
    """Test EmotionalSignal for express_feeling intent."""

    def test_create_emotional_signal(self) -> None:
        """Can create EmotionalSignal with emotion and targets."""
        signal = EmotionalSignal(
            signal_type=IntentSignalType.EMOTIONAL_TREND,
            event_id="evt_emotional_1",
            confidence=0.85,
            source_text="I'm feeling grateful for my family",
            emotion_label="gratitude",
            intensity=0.8,
            target_entities=["family"],
        )

        assert signal.signal_type == IntentSignalType.EMOTIONAL_TREND
        assert signal.emotion_label == "gratitude"
        assert signal.intensity == 0.8
        assert "family" in signal.target_entities

    def test_emotional_intensity_validation(self) -> None:
        """Intensity must be in [0.0, 1.0] range."""
        with pytest.raises(ValueError, match="intensity must be"):
            EmotionalSignal(
                signal_type=IntentSignalType.EMOTIONAL_TREND,
                event_id="evt_emotional_2",
                confidence=0.8,
                source_text="test",
                emotion_label="anger",
                intensity=1.5,  # Invalid
            )


class TestMilestoneSignal:
    """Test MilestoneSignal for share_news intent."""

    def test_create_milestone_signal(self) -> None:
        """Can create MilestoneSignal with type and entity."""
        signal = MilestoneSignal(
            signal_type=IntentSignalType.MILESTONE,
            event_id="evt_milestone_1",
            confidence=0.9,
            source_text="Emma got accepted to Stanford!",
            milestone_type=MilestoneType.ACHIEVEMENT,
            entity_id="entity_emma",
            milestone_description="accepted to Stanford",
        )

        assert signal.signal_type == IntentSignalType.MILESTONE
        assert signal.milestone_type == MilestoneType.ACHIEVEMENT
        assert signal.entity_id == "entity_emma"

    def test_milestone_types(self) -> None:
        """All milestone types should be defined."""
        expected_types = {"ACHIEVEMENT", "ANNOUNCEMENT", "TRANSITION", "CELEBRATION", "RECOGNITION"}
        actual_types = {t.value for t in MilestoneType}
        assert actual_types == expected_types


class TestQueryBoostSignal:
    """Test QueryBoostSignal for query_memory intent."""

    def test_create_query_boost_signal(self) -> None:
        """Can create QueryBoostSignal with entity and edge IDs."""
        signal = QueryBoostSignal(
            signal_type=IntentSignalType.QUERY_BOOST,
            event_id="evt_query_1",
            confidence=0.8,
            source_text="When did we last visit Grandma?",
            entity_ids=["entity_grandma"],
            edge_ids=["edge_visit_123"],
        )

        assert signal.signal_type == IntentSignalType.QUERY_BOOST
        assert "entity_grandma" in signal.entity_ids
        assert "edge_visit_123" in signal.edge_ids

    def test_query_boost_empty_lists(self) -> None:
        """QueryBoostSignal can have empty entity/edge lists."""
        signal = QueryBoostSignal(
            signal_type=IntentSignalType.QUERY_BOOST,
            event_id="evt_query_2",
            confidence=0.7,
            source_text="What happened recently?",
        )

        assert signal.entity_ids == []
        assert signal.edge_ids == []


class TestAnyIntentSignalType:
    """Test the AnyIntentSignal type alias."""

    def test_all_signal_types_included(self) -> None:
        """All signal types should be usable with AnyIntentSignal."""
        signals: list[AnyIntentSignal] = [
            ReminderSignal(
                signal_type=IntentSignalType.REMINDER,
                event_id="1",
                confidence=0.8,
                source_text="test",
            ),
            DecisionSignal(
                signal_type=IntentSignalType.DECISION,
                event_id="2",
                confidence=0.8,
                source_text="test",
            ),
            LessonSignal(
                signal_type=IntentSignalType.LESSON,
                event_id="3",
                confidence=0.8,
                source_text="test",
            ),
            EmotionalSignal(
                signal_type=IntentSignalType.EMOTIONAL_TREND,
                event_id="4",
                confidence=0.8,
                source_text="test",
            ),
            MilestoneSignal(
                signal_type=IntentSignalType.MILESTONE,
                event_id="5",
                confidence=0.8,
                source_text="test",
            ),
            QueryBoostSignal(
                signal_type=IntentSignalType.QUERY_BOOST,
                event_id="6",
                confidence=0.8,
                source_text="test",
            ),
        ]

        assert len(signals) == 6
        # Verify all are subclasses
        for signal in signals:
            assert isinstance(signal, IntentSignal)
