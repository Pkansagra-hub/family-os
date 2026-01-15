"""
Test suite for IntentSignalDetector (Phase 2.2).

Validates intent signal detection from P03EventState list for GAP-001.

Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 2
"""

from __future__ import annotations

import json

import pytest

from k0.modules.consolidation.algorithms.intent_signal_detector import (
    IntentSignalDetector,
    detect_intent_signals,
)
from k0.modules.consolidation.dream.intent_signals import (
    DecisionSignal,
    EmotionalSignal,
    IntentSignalType,
    LessonSignal,
    MilestoneSignal,
    MilestoneType,
    QueryBoostSignal,
    ReminderSignal,
)
from k0.pipelines.p03.event_state import P03EventState

# =============================================================================
# Test Fixtures
# =============================================================================


def make_event(
    event_id: str,
    intent_label: str,
    content_text: str,
    temporal_json: str = "[]",
    emotions_json: str = "[]",
    ner_entities_json: str = "[]",
) -> P03EventState:
    """Create a P03EventState with specified fields for testing."""
    return P03EventState(
        event_id=event_id,
        intent_label=intent_label,
        content_text=content_text,
        temporal_expressions_json=temporal_json,
        emotions_json=emotions_json,
        ner_entities_json=ner_entities_json,
    )


@pytest.fixture
def detector() -> IntentSignalDetector:
    """Create IntentSignalDetector instance."""
    return IntentSignalDetector()


# =============================================================================
# Test IntentSignalDetector.detect_all()
# =============================================================================


class TestDetectAll:
    """Test detect_all() method."""

    def test_empty_event_list(self, detector: IntentSignalDetector) -> None:
        """Empty event list returns empty signal list."""
        signals = detector.detect_all([])
        assert signals == []

    def test_events_without_intent_label_skipped(self, detector: IntentSignalDetector) -> None:
        """Events without intent_label are skipped."""
        events = [
            make_event("evt_1", "", "No intent label"),
            make_event("evt_2", "set_reminder", "Remind me to call"),
        ]

        signals = detector.detect_all(events)

        assert len(signals) == 1
        assert signals[0].event_id == "evt_2"

    def test_unsupported_intent_skipped(self, detector: IntentSignalDetector) -> None:
        """Events with unsupported intent_label are skipped."""
        events = [
            make_event("evt_1", "log_memory", "Just logging this"),
            make_event("evt_2", "other", "Something else"),
        ]

        signals = detector.detect_all(events)

        assert len(signals) == 0

    def test_all_supported_intents_detected(self, detector: IntentSignalDetector) -> None:
        """All 6 supported intent types are detected."""
        events = [
            make_event("evt_1", "set_reminder", "Remind me to call"),
            make_event("evt_2", "seek_advice", "Should I do this?"),
            make_event("evt_3", "reflect", "I learned something"),
            make_event("evt_4", "express_feeling", "I feel happy"),
            make_event("evt_5", "share_news", "Good news everyone!"),
            make_event("evt_6", "query_memory", "When did we visit?"),
        ]

        signals = detector.detect_all(events)

        assert len(signals) == 6

        signal_types = {s.signal_type for s in signals}
        expected_types = {
            IntentSignalType.REMINDER,
            IntentSignalType.DECISION,
            IntentSignalType.LESSON,
            IntentSignalType.EMOTIONAL_TREND,
            IntentSignalType.MILESTONE,
            IntentSignalType.QUERY_BOOST,
        }
        assert signal_types == expected_types

    def test_intent_label_case_insensitive(self, detector: IntentSignalDetector) -> None:
        """Intent labels are matched case-insensitively."""
        events = [
            make_event("evt_1", "SET_REMINDER", "Remind me"),
            make_event("evt_2", "Set_Reminder", "Remind me again"),
            make_event("evt_3", "  set_reminder  ", "Remind with spaces"),
        ]

        signals = detector.detect_all(events)

        assert len(signals) == 3
        assert all(isinstance(s, ReminderSignal) for s in signals)


# =============================================================================
# Test Reminder Signal Extraction
# =============================================================================


class TestReminderExtraction:
    """Test set_reminder → ReminderSignal extraction."""

    def test_reminder_action_extraction_remind_me_to(self, detector: IntentSignalDetector) -> None:
        """Extracts action from 'remind me to X' pattern."""
        event = make_event(
            "evt_reminder",
            "set_reminder",
            "Remind me to call Mom tomorrow at 3pm",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, ReminderSignal)
        assert signal.action_description == "call Mom"

    def test_reminder_action_extraction_dont_forget(self, detector: IntentSignalDetector) -> None:
        """Extracts action from "don't forget to X" pattern."""
        event = make_event(
            "evt_reminder",
            "set_reminder",
            "Don't forget to buy groceries on the way home",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, ReminderSignal)
        assert "buy groceries" in signal.action_description

    def test_reminder_fallback_to_full_text(self, detector: IntentSignalDetector) -> None:
        """Falls back to pattern extraction when pattern partially matches."""
        event = make_event(
            "evt_reminder",
            "set_reminder",
            "Just a reminder about the meeting",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, ReminderSignal)
        # Detector extracts "about the meeting" from "a reminder about" pattern
        assert "about the meeting" in signal.action_description

    def test_reminder_with_temporal_json(self, detector: IntentSignalDetector) -> None:
        """ReminderSignal is created even with temporal_json (date parsing in Phase 6)."""
        temporal = json.dumps({"entities": [{"text": "tomorrow at 3pm", "label": "TIME"}]})
        event = make_event(
            "evt_reminder",
            "set_reminder",
            "Remind me to call tomorrow at 3pm",
            temporal_json=temporal,
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, ReminderSignal)
        # target_date is None until Phase 6 TemporalParser is implemented
        assert signal.target_date is None


# =============================================================================
# Test Decision Signal Extraction
# =============================================================================


class TestDecisionExtraction:
    """Test seek_advice → DecisionSignal extraction."""

    def test_decision_with_or_options(self, detector: IntentSignalDetector) -> None:
        """Extracts options from 'should I X or Y' pattern."""
        event = make_event(
            "evt_decision",
            "seek_advice",
            "Should I take the job offer or stay at my current company?",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, DecisionSignal)
        assert len(signal.options_mentioned) == 2
        assert "take the job offer" in signal.options_mentioned
        assert "stay at my current company" in signal.options_mentioned

    def test_decision_without_options(self, detector: IntentSignalDetector) -> None:
        """DecisionSignal created even without explicit options."""
        event = make_event(
            "evt_decision",
            "seek_advice",
            "I need some advice about my career",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, DecisionSignal)
        assert signal.options_mentioned == []
        assert "advice about my career" in signal.decision_context


# =============================================================================
# Test Lesson Signal Extraction
# =============================================================================


class TestLessonExtraction:
    """Test reflect → LessonSignal extraction."""

    def test_lesson_i_learned_that_pattern(self, detector: IntentSignalDetector) -> None:
        """Extracts lesson from 'I learned that X' pattern."""
        event = make_event(
            "evt_lesson",
            "reflect",
            "I learned that patience is really important",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, LessonSignal)
        assert "patience is really important" in signal.lesson_description

    def test_lesson_with_ner_entities(self, detector: IntentSignalDetector) -> None:
        """Extracts topic entities from NER JSON."""
        ner_json = json.dumps({"ner_family": {"entities": [{"text": "Mom", "label": "KINSHIP"}]}})
        event = make_event(
            "evt_lesson",
            "reflect",
            "I realized that Mom was right about this",
            ner_entities_json=ner_json,
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, LessonSignal)
        assert "Mom" in signal.topic_entities


# =============================================================================
# Test Emotional Signal Extraction
# =============================================================================


class TestEmotionalExtraction:
    """Test express_feeling → EmotionalSignal extraction."""

    def test_emotional_with_emotions_json(self, detector: IntentSignalDetector) -> None:
        """Parses emotion from emotions_json."""
        emotions = json.dumps([{"emotion": "joy", "score": 0.9}])
        event = make_event(
            "evt_emotional",
            "express_feeling",
            "I'm feeling so happy today!",
            emotions_json=emotions,
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, EmotionalSignal)
        assert signal.emotion_label == "joy"
        assert signal.intensity == 0.9

    def test_emotional_highest_scoring_emotion(self, detector: IntentSignalDetector) -> None:
        """Uses highest scoring emotion when multiple present."""
        emotions = json.dumps(
            [
                {"emotion": "sadness", "score": 0.3},
                {"emotion": "gratitude", "score": 0.8},
                {"emotion": "calm", "score": 0.5},
            ]
        )
        event = make_event(
            "evt_emotional",
            "express_feeling",
            "Mixed feelings but mostly grateful",
            emotions_json=emotions,
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, EmotionalSignal)
        assert signal.emotion_label == "gratitude"
        assert signal.intensity == 0.8

    def test_emotional_default_when_no_emotions(self, detector: IntentSignalDetector) -> None:
        """Defaults to neutral with 0.5 intensity when no emotions_json."""
        event = make_event(
            "evt_emotional",
            "express_feeling",
            "I have some feelings",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, EmotionalSignal)
        assert signal.emotion_label == "neutral"
        assert signal.intensity == 0.5


# =============================================================================
# Test Milestone Signal Extraction
# =============================================================================


class TestMilestoneExtraction:
    """Test share_news → MilestoneSignal extraction."""

    def test_milestone_achievement_detection(self, detector: IntentSignalDetector) -> None:
        """Detects ACHIEVEMENT milestone type from keywords."""
        ner_json = json.dumps({"ner_family": {"entities": [{"text": "Emma", "label": "KINSHIP"}]}})
        event = make_event(
            "evt_milestone",
            "share_news",
            "Emma got accepted to Stanford!",
            ner_entities_json=ner_json,
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, MilestoneSignal)
        assert signal.milestone_type == MilestoneType.ACHIEVEMENT
        assert signal.entity_id == "Emma"

    def test_milestone_transition_detection(self, detector: IntentSignalDetector) -> None:
        """Detects TRANSITION milestone type from keywords."""
        event = make_event(
            "evt_milestone",
            "share_news",
            "We are moving to a new city next month",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, MilestoneSignal)
        assert signal.milestone_type == MilestoneType.TRANSITION

    def test_milestone_default_announcement(self, detector: IntentSignalDetector) -> None:
        """Defaults to ANNOUNCEMENT when no keyword matches."""
        event = make_event(
            "evt_milestone",
            "share_news",
            "I have some news to share with everyone",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, MilestoneSignal)
        assert signal.milestone_type == MilestoneType.ANNOUNCEMENT


# =============================================================================
# Test Query Boost Signal Extraction
# =============================================================================


class TestQueryBoostExtraction:
    """Test query_memory → QueryBoostSignal extraction."""

    def test_query_boost_with_entities(self, detector: IntentSignalDetector) -> None:
        """Extracts entities from query_memory event."""
        ner_json = json.dumps(
            {"ner_family": {"entities": [{"text": "Grandma", "label": "KINSHIP"}]}}
        )
        event = make_event(
            "evt_query",
            "query_memory",
            "When did we last visit Grandma?",
            ner_entities_json=ner_json,
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, QueryBoostSignal)
        assert "Grandma" in signal.entity_ids

    def test_query_boost_empty_edges(self, detector: IntentSignalDetector) -> None:
        """Edge IDs are empty (resolved in R6)."""
        event = make_event(
            "evt_query",
            "query_memory",
            "What happened last week?",
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, QueryBoostSignal)
        assert signal.edge_ids == []


# =============================================================================
# Test Helper Methods
# =============================================================================


class TestHelperMethods:
    """Test internal helper methods."""

    def test_extract_entity_ids_ultrabert_format(self, detector: IntentSignalDetector) -> None:
        """Parses UltraBERT nested JSON format."""
        ner_json = json.dumps(
            {
                "ner_family": {
                    "entities": [
                        {"text": "Mom", "label": "KINSHIP"},
                        {"text": "Dad", "label": "KINSHIP"},
                    ]
                },
                "ner_general": {
                    "entities": [
                        {"text": "Stanford", "label": "ORG"},
                    ]
                },
            }
        )

        entities = detector._extract_entity_ids(ner_json)

        assert "Mom" in entities
        assert "Dad" in entities
        assert "Stanford" in entities

    def test_extract_entity_ids_simple_list_format(self, detector: IntentSignalDetector) -> None:
        """Parses simple list JSON format."""
        ner_json = json.dumps(
            [
                {"text": "Emma", "label": "PERSON"},
                {"text": "San Francisco", "label": "LOCATION"},
            ]
        )

        entities = detector._extract_entity_ids(ner_json)

        assert "Emma" in entities
        assert "San Francisco" in entities

    def test_extract_entity_ids_empty_json(self, detector: IntentSignalDetector) -> None:
        """Returns empty list for empty JSON."""
        assert detector._extract_entity_ids("[]") == []
        assert detector._extract_entity_ids("") == []
        assert detector._extract_entity_ids("{}") == []

    def test_parse_emotions_alternative_keys(self, detector: IntentSignalDetector) -> None:
        """Handles alternative emotion JSON keys."""
        # Alternative: "label" instead of "emotion"
        emotions = json.dumps([{"label": "anger", "intensity": 0.7}])
        label, intensity = detector._parse_emotions(emotions)
        assert label == "anger"
        assert intensity == 0.7

    def test_detect_milestone_type_keywords(self, detector: IntentSignalDetector) -> None:
        """Detects milestone types from keywords."""
        assert (
            detector._detect_milestone_type("I graduated from college") == MilestoneType.ACHIEVEMENT
        )
        assert detector._detect_milestone_type("We're getting married!") == MilestoneType.TRANSITION
        assert detector._detect_milestone_type("Happy birthday to me") == MilestoneType.CELEBRATION
        # "won" triggers ACHIEVEMENT before RECOGNITION check
        assert detector._detect_milestone_type("I won an award today") == MilestoneType.ACHIEVEMENT


# =============================================================================
# Test Convenience Function
# =============================================================================


class TestConvenienceFunction:
    """Test detect_intent_signals() convenience function."""

    def test_detect_intent_signals_function(self) -> None:
        """Convenience function works same as detector.detect_all()."""
        events = [
            make_event("evt_1", "set_reminder", "Remind me to call"),
            make_event("evt_2", "reflect", "I learned something"),
        ]

        signals = detect_intent_signals(events)

        assert len(signals) == 2
        assert any(isinstance(s, ReminderSignal) for s in signals)
        assert any(isinstance(s, LessonSignal) for s in signals)


# =============================================================================
# Test Error Handling
# =============================================================================


class TestErrorHandling:
    """Test error handling in detection."""

    def test_malformed_json_does_not_crash(self, detector: IntentSignalDetector) -> None:
        """Malformed JSON in fields doesn't crash detection."""
        event = make_event(
            "evt_malformed",
            "express_feeling",
            "I feel happy",
            emotions_json="not valid json",
            ner_entities_json="also not valid",
        )

        signals = detector.detect_all([event])

        # Should still create signal with defaults
        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, EmotionalSignal)
        assert signal.emotion_label == "neutral"

    def test_missing_fields_handled_gracefully(self, detector: IntentSignalDetector) -> None:
        """Events with minimal fields are handled."""
        event = P03EventState(
            event_id="evt_minimal",
            intent_label="set_reminder",
            content_text="",  # Empty content
        )

        signals = detector.detect_all([event])

        assert len(signals) == 1
        assert isinstance(signals[0], ReminderSignal)
