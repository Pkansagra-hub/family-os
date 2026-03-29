"""
IntentSignalDetector - GAP-001 Implementation.

Detects intent signals from P03EventState list based on UltraBERT intent
classification. Called by R5 DreamExplorer or R6 TruthWriteAssembler.

The detector routes events to specific IntentSignal types based on intent_label:
- set_reminder → ReminderSignal (with temporal parsing)
- seek_advice → DecisionSignal (with option extraction)
- reflect → LessonSignal (with lesson extraction)
- express_feeling → EmotionalSignal (with emotion parsing)
- share_news → MilestoneSignal (with entity extraction)
- query_memory → QueryBoostSignal (with entity/edge extraction)

Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 2
GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING

Performance:
- O(n) where n = number of events
- No model inference (uses pre-computed UltraBERT outputs)
- ~0.1ms per event
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

# Direct module import to avoid triggering dream/__init__.py during import
# (DreamExplorer now uses runtime import of IntentSignalDetector)
import k0.modules.consolidation.dream.intent_signals as _signals
from k0.modules.consolidation.algorithms.temporal_parser import TemporalParser
from k0.pipelines.p03.event_state import P03EventState

AnyIntentSignal = _signals.AnyIntentSignal
DecisionSignal = _signals.DecisionSignal
EmotionalSignal = _signals.EmotionalSignal
IntentSignalType = _signals.IntentSignalType
LessonSignal = _signals.LessonSignal
MilestoneSignal = _signals.MilestoneSignal
MilestoneType = _signals.MilestoneType
QueryBoostSignal = _signals.QueryBoostSignal
ReminderSignal = _signals.ReminderSignal

logger = logging.getLogger(__name__)


class IntentSignalDetector:
    """
    Detects intent signals from P03 event states.

    Uses UltraBERT intent_label and supporting fields (temporal_json,
    emotions_json, ner_entities_json) to create typed IntentSignal objects.

    Example:
        detector = IntentSignalDetector()
        signals = detector.detect_all(event_states)
        for signal in signals:
            if isinstance(signal, ReminderSignal):
                # Route to st_prospective REMINDER
                ...

    Thread Safety: Stateless, safe for concurrent use.
    """

    # Regex patterns for action extraction from reminder text
    REMINDER_PATTERNS = [
        re.compile(r"remind me to (.+?)(?:\s+(?:at|on|in|by|tomorrow|next)|$)", re.I),
        re.compile(r"don'?t forget to (.+?)(?:\s+(?:at|on|in|by)|$)", re.I),
        re.compile(r"reminder[:\s]+(.+?)(?:\s+(?:at|on|in|by)|$)", re.I),
        re.compile(r"need to (.+?)(?:\s+(?:later|soon|tomorrow)|$)", re.I),
        re.compile(r"have to (.+?)(?:\s+(?:later|soon|tomorrow)|$)", re.I),
    ]

    # Regex patterns for decision option extraction
    DECISION_OPTION_PATTERNS = [
        re.compile(r"should I (.+?) or (.+?)[?.]", re.I),
        re.compile(r"whether to (.+?) or (.+?)[?.]", re.I),
        re.compile(r"between (.+?) and (.+?)[?.]", re.I),
        re.compile(r"either (.+?) or (.+?)[?.]", re.I),
    ]

    # Regex patterns for lesson extraction
    LESSON_PATTERNS = [
        re.compile(r"I (?:learned|realized|discovered) (?:that )?(.+)", re.I),
        re.compile(r"(?:lesson|takeaway)[:\s]+(.+)", re.I),
        re.compile(r"(?:it turns out|it'?s important) (?:that )?(.+)", re.I),
        re.compile(r"(?:never|always|should|shouldn'?t) (.+)", re.I),
    ]

    # Milestone keyword indicators
    MILESTONE_KEYWORDS = {
        MilestoneType.ACHIEVEMENT: [
            "got accepted",
            "graduated",
            "won",
            "achieved",
            "passed",
            "earned",
            "completed",
            "promoted",
        ],
        MilestoneType.ANNOUNCEMENT: [
            "announced",
            "telling you",
            "news",
            "let you know",
            "wanted to share",
        ],
        MilestoneType.TRANSITION: [
            "moving to",
            "starting",
            "new job",
            "getting married",
            "engaged",
            "retiring",
            "leaving",
        ],
        MilestoneType.CELEBRATION: [
            "birthday",
            "anniversary",
            "wedding",
            "party",
            "celebrating",
        ],
        MilestoneType.RECOGNITION: [
            "award",
            "recognition",
            "honor",
            "prize",
            "certificate",
        ],
    }

    # Default confidence for detected signals (no UltraBERT confidence available)
    DEFAULT_CONFIDENCE = 0.8

    def __init__(self) -> None:
        """Initialize the IntentSignalDetector with TemporalParser."""
        self._temporal_parser = TemporalParser()

    def detect_all(
        self,
        event_states: List[P03EventState],
    ) -> List[AnyIntentSignal]:
        """
        Detect all intent signals from event states.

        Scans each event's intent_label and extracts appropriate signal type.
        Events without intent_label or with unsupported intents are skipped.

        Args:
            event_states: List of P03EventState from R0 batch

        Returns:
            List of typed IntentSignal objects for R6 routing
        """
        signals: List[AnyIntentSignal] = []

        for event in event_states:
            if not event.intent_label:
                continue

            try:
                signal = self._detect_for_event(event)
                if signal:
                    signals.append(signal)
                    logger.debug(
                        "Detected %s signal from event %s",
                        signal.signal_type.value,
                        event.event_id,
                    )
            except Exception as e:
                # Log but don't fail batch on single event error
                logger.warning(
                    "Failed to detect intent signal for event %s: %s",
                    event.event_id,
                    str(e),
                )

        logger.info(
            "Detected %d intent signals from %d events",
            len(signals),
            len(event_states),
        )

        return signals

    def _detect_for_event(
        self,
        event: P03EventState,
    ) -> Optional[AnyIntentSignal]:
        """
        Detect signal for single event based on intent_label.

        Routes to specific extraction method based on intent type.

        Args:
            event: Single P03EventState with intent_label set

        Returns:
            Typed IntentSignal or None if intent not routable
        """
        intent = event.intent_label.lower().strip()

        if intent == "set_reminder":
            return self._extract_reminder(event)
        elif intent == "seek_advice":
            return self._extract_decision(event)
        elif intent == "reflect":
            return self._extract_lesson(event)
        elif intent == "express_feeling":
            return self._extract_emotional(event)
        elif intent == "share_news":
            return self._extract_milestone(event)
        elif intent == "query_memory":
            return self._extract_query_boost(event)

        # Unsupported intent type - no signal
        return None

    def _extract_reminder(self, event: P03EventState) -> ReminderSignal:
        """
        Extract reminder signal from set_reminder event.

        Parses temporal_json for target date and extracts action description.

        Args:
            event: Event with intent_label = 'set_reminder'

        Returns:
            ReminderSignal with action and optional target_date
        """
        # Parse temporal_json for target date (GAP-002 fix: use TemporalParser)
        target_date = self._parse_temporal_date(
            event.temporal_expressions_json,
            reference_time_ms=event.timestamp,
        )

        # Extract action from text using patterns
        action = self._extract_action_from_text(event.content_text)

        return ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id=event.event_id,
            confidence=self.DEFAULT_CONFIDENCE,
            source_text=event.content_text,
            action_description=action,
            target_date=target_date,
        )

    def _extract_decision(self, event: P03EventState) -> DecisionSignal:
        """
        Extract decision signal from seek_advice event.

        Identifies decision context and any mentioned options.

        Args:
            event: Event with intent_label = 'seek_advice'

        Returns:
            DecisionSignal with context and options
        """
        # Extract options from text
        options = self._extract_decision_options(event.content_text)

        # Use full text as context (could be refined with NLP)
        context = event.content_text[:200]  # Truncate for storage

        return DecisionSignal(
            signal_type=IntentSignalType.DECISION,
            event_id=event.event_id,
            confidence=self.DEFAULT_CONFIDENCE,
            source_text=event.content_text,
            decision_context=context,
            options_mentioned=options,
        )

    def _extract_lesson(self, event: P03EventState) -> LessonSignal:
        """
        Extract lesson signal from reflect event.

        Identifies the lesson or insight and related entities.

        Args:
            event: Event with intent_label = 'reflect'

        Returns:
            LessonSignal with lesson description and topic entities
        """
        # Extract lesson description
        lesson = self._extract_lesson_from_text(event.content_text)

        # Extract related entities from NER
        entity_ids = self._extract_entity_ids(event.ner_entities_json)

        return LessonSignal(
            signal_type=IntentSignalType.LESSON,
            event_id=event.event_id,
            confidence=self.DEFAULT_CONFIDENCE,
            source_text=event.content_text,
            lesson_description=lesson,
            topic_entities=entity_ids,
        )

    def _extract_emotional(self, event: P03EventState) -> EmotionalSignal:
        """
        Extract emotional signal from express_feeling event.

        Parses emotions_json for emotion label and intensity.

        Args:
            event: Event with intent_label = 'express_feeling'

        Returns:
            EmotionalSignal with emotion, intensity, and targets
        """
        # Parse emotions_json
        emotion_label, intensity = self._parse_emotions(event.emotions_json)

        # Extract target entities (who the emotion is about)
        target_entities = self._extract_entity_ids(event.ner_entities_json)

        return EmotionalSignal(
            signal_type=IntentSignalType.EMOTIONAL_TREND,
            event_id=event.event_id,
            confidence=self.DEFAULT_CONFIDENCE,
            source_text=event.content_text,
            emotion_label=emotion_label,
            intensity=intensity,
            target_entities=target_entities,
        )

    def _extract_milestone(self, event: P03EventState) -> MilestoneSignal:
        """
        Extract milestone signal from share_news event.

        Identifies milestone type and primary entity.

        Args:
            event: Event with intent_label = 'share_news'

        Returns:
            MilestoneSignal with type, entity, and description
        """
        # Determine milestone type from keywords
        milestone_type = self._detect_milestone_type(event.content_text)

        # Get primary entity (first person mentioned)
        entity_ids = self._extract_entity_ids(event.ner_entities_json)
        primary_entity = entity_ids[0] if entity_ids else ""

        # Use content as description (truncated)
        description = event.content_text[:150]

        return MilestoneSignal(
            signal_type=IntentSignalType.MILESTONE,
            event_id=event.event_id,
            confidence=self.DEFAULT_CONFIDENCE,
            source_text=event.content_text,
            milestone_type=milestone_type,
            entity_id=primary_entity,
            milestone_description=description,
        )

    def _extract_query_boost(self, event: P03EventState) -> QueryBoostSignal:
        """
        Extract query boost signal from query_memory event.

        Identifies entities and potential edges mentioned in query.

        Args:
            event: Event with intent_label = 'query_memory'

        Returns:
            QueryBoostSignal with entity and edge IDs
        """
        # Extract entities mentioned in query
        entity_ids = self._extract_entity_ids(event.ner_entities_json)

        # Edge IDs would need graph traversal - stub for now
        # R6 will resolve entity names to actual edge IDs
        edge_ids: List[str] = []

        return QueryBoostSignal(
            signal_type=IntentSignalType.QUERY_BOOST,
            event_id=event.event_id,
            confidence=self.DEFAULT_CONFIDENCE,
            source_text=event.content_text,
            entity_ids=entity_ids,
            edge_ids=edge_ids,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_temporal_date(
        self,
        temporal_json: str,
        reference_time_ms: Optional[int] = None,
    ) -> Optional[int]:
        """
        Parse temporal_json to extract target date using TemporalParser.

        UltraBERT temporal head produces:
        {"entities": [{"text": "tomorrow at 3pm", "label": "TIME"}]}

        GAP-002 fix: Now wired to TemporalParser for actual parsing.

        Args:
            temporal_json: JSON string from st_hipp_events.temporal_json
            reference_time_ms: Reference timestamp for relative dates (event time)

        Returns:
            Unix ms timestamp or None if no parseable date
        """
        if not temporal_json or temporal_json == "[]":
            return None

        try:
            return self._temporal_parser.parse_temporal_json(
                temporal_json=temporal_json,
                reference_time=reference_time_ms,
            )
        except Exception as e:
            logger.warning(f"Temporal parsing failed: {e}")
            return None

    def _extract_action_from_text(self, text: str) -> str:
        """
        Extract action description from reminder text.

        Uses regex patterns to identify the action part of reminder phrases.

        Args:
            text: Full event text

        Returns:
            Extracted action or full text if no pattern matches
        """
        for pattern in self.REMINDER_PATTERNS:
            match = pattern.search(text)
            if match:
                action = match.group(1).strip()
                # Clean up trailing punctuation
                action = action.rstrip(".,!?")
                return action

        # Fallback: use full text (truncated)
        return text[:100].strip()

    def _extract_decision_options(self, text: str) -> List[str]:
        """
        Extract decision options from seek_advice text.

        Looks for "X or Y" patterns to identify options.

        Args:
            text: Full event text

        Returns:
            List of identified options (may be empty)
        """
        options: List[str] = []

        for pattern in self.DECISION_OPTION_PATTERNS:
            match = pattern.search(text)
            if match:
                options.append(match.group(1).strip())
                options.append(match.group(2).strip())
                break

        return options

    def _extract_lesson_from_text(self, text: str) -> str:
        """
        Extract lesson description from reflect text.

        Looks for "I learned that..." patterns.

        Args:
            text: Full event text

        Returns:
            Extracted lesson or full text if no pattern matches
        """
        for pattern in self.LESSON_PATTERNS:
            match = pattern.search(text)
            if match:
                lesson = match.group(1).strip()
                lesson = lesson.rstrip(".,!?")
                return lesson

        # Fallback: use full text (truncated)
        return text[:200].strip()

    def _extract_entity_ids(self, ner_entities_json: str) -> List[str]:
        """
        Extract entity texts from NER JSON.

        Returns entity texts as IDs - R6 will resolve to canonical entity IDs.

        Args:
            ner_entities_json: JSON string from st_hipp_events.ner_entities_json

        Returns:
            List of entity texts (for R6 resolution)
        """
        if not ner_entities_json or ner_entities_json == "[]":
            return []

        try:
            data = json.loads(ner_entities_json)
        except json.JSONDecodeError:
            return []

        entities: List[str] = []

        # UltraBERT format: {"ner_family": {"entities": [...]}, ...}
        if isinstance(data, dict):
            for head_key in ["ner_family", "ner_general"]:
                head_data = data.get(head_key, {})
                if isinstance(head_data, dict):
                    for entity in head_data.get("entities", []):
                        if isinstance(entity, dict) and "text" in entity:
                            entities.append(entity["text"])
                elif isinstance(head_data, list):
                    for entity in head_data:
                        if isinstance(entity, dict) and "text" in entity:
                            entities.append(entity["text"])
        elif isinstance(data, list):
            # Simple list format
            for entity in data:
                if isinstance(entity, dict) and "text" in entity:
                    entities.append(entity["text"])

        return entities

    def _parse_emotions(self, emotions_json: str) -> tuple[str, float]:
        """
        Parse emotions_json to extract primary emotion and intensity.

        Supports two formats:
        1. Simple array: ["joy", "excitement", "pride"] (from P02 dominant_emotions_json)
        2. Scored array: [{"emotion": "joy", "score": 0.85}, ...] (legacy format)

        Args:
            emotions_json: JSON array of emotions

        Returns:
            Tuple of (emotion_label, intensity)
        """
        if not emotions_json or emotions_json == "[]":
            return ("neutral", 0.5)

        try:
            emotions = json.loads(emotions_json)
        except json.JSONDecodeError:
            return ("neutral", 0.5)

        if not emotions or not isinstance(emotions, list):
            return ("neutral", 0.5)

        # Handle simple string array format: ["joy", "excitement", "pride"]
        # First emotion is the dominant one, score based on position
        if emotions and isinstance(emotions[0], str):
            primary_emotion = emotions[0].lower()
            # Skip "neutral" if there are other emotions
            if primary_emotion == "neutral" and len(emotions) > 1:
                primary_emotion = emotions[1].lower()
            # First emotion gets high score, score decreases for later ones
            intensity = 0.85 if len(emotions) >= 1 else 0.5
            return (primary_emotion, intensity)

        # Handle scored object array format: [{"emotion": "joy", "score": 0.85}, ...]
        best_emotion = "neutral"
        best_score = 0.5

        for emotion in emotions:
            if not isinstance(emotion, dict):
                continue
            label = emotion.get("emotion", emotion.get("label", ""))
            score = emotion.get("score", emotion.get("intensity", 0.5))

            if score > best_score:
                best_emotion = label
                best_score = score

        return (best_emotion, min(1.0, max(0.0, best_score)))

    def _detect_milestone_type(self, text: str) -> MilestoneType:
        """
        Detect milestone type from text keywords.

        Args:
            text: Full event text

        Returns:
            Detected MilestoneType or ANNOUNCEMENT as default
        """
        text_lower = text.lower()

        for milestone_type, keywords in self.MILESTONE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return milestone_type

        return MilestoneType.ANNOUNCEMENT


# Convenience function for one-liner detection
def detect_intent_signals(
    event_states: List[P03EventState],
) -> List[AnyIntentSignal]:
    """
    Convenience function to detect intent signals from event states.

    Args:
        event_states: List of P03EventState from R0 batch

    Returns:
        List of typed IntentSignal objects

    Example:
        signals = detect_intent_signals(batch.events)
    """
    return IntentSignalDetector().detect_all(event_states)
