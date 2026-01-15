"""
Intent Signal Models - GAP-001 Implementation.

This module defines intent signal types that are detected from P03EventState
and routed to specific truth layers during R6/R7 processing.

Intent signals bridge UltraBERT's intent classification (P02) with
layer-specific writes in P03 consolidation:
- set_reminder → st_prospective REMINDER
- seek_advice → st_prospective DECISION
- reflect → st_sem LESSON
- express_feeling → st_sem EMOTIONAL_TREND
- share_news → st_kg_dom milestone
- query_memory → st_kg_dom/edges query_count increment

Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 2
GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class IntentSignalType(str, Enum):
    """Types of intent signals routed to specific layers.

    Each signal type maps to a specific truth layer and record type:
    - REMINDER: st_prospective.intention_type = 'REMINDER'
    - DECISION: st_prospective.intention_type = 'DECISION'
    - LESSON: st_sem.pattern_type = 'LESSON'
    - EMOTIONAL_TREND: st_sem.pattern_type = 'EMOTIONAL_TREND'
    - MILESTONE: st_kg_dom.milestones_json append
    - QUERY_BOOST: st_kg_dom/st_kg_edges.query_count increment
    """

    REMINDER = "reminder"  # set_reminder → st_prospective
    DECISION = "decision"  # seek_advice → st_prospective
    LESSON = "lesson"  # reflect → st_sem
    EMOTIONAL_TREND = "emotional"  # express_feeling → st_sem
    MILESTONE = "milestone"  # share_news → st_kg_dom
    QUERY_BOOST = "query_boost"  # query_memory → st_kg_dom/edges


class MilestoneType(str, Enum):
    """Types of milestones for share_news intent."""

    ACHIEVEMENT = "ACHIEVEMENT"  # Personal accomplishment
    ANNOUNCEMENT = "ANNOUNCEMENT"  # News sharing
    TRANSITION = "TRANSITION"  # Life change (job, move, etc.)
    CELEBRATION = "CELEBRATION"  # Birthday, anniversary, etc.
    RECOGNITION = "RECOGNITION"  # Award, promotion, etc.


@dataclass
class IntentSignal:
    """
    Base intent signal detected from event.

    Intent signals are detected by IntentSignalDetector from P03EventState
    based on the intent_label field (from UltraBERT intent classification).

    Attributes:
        signal_type: Type of intent signal (determines target layer)
        event_id: Source event ID for provenance
        confidence: Detection confidence [0.0, 1.0]
        source_text: Original text for context
        created_at_ms: Detection timestamp in milliseconds
    """

    signal_type: IntentSignalType
    event_id: str
    confidence: float
    source_text: str
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def __post_init__(self) -> None:
        """Validate confidence bounds."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be [0.0, 1.0], got {self.confidence}")


@dataclass
class ReminderSignal(IntentSignal):
    """
    set_reminder intent → st_prospective REMINDER.

    Created when UltraBERT classifies intent as 'set_reminder'.
    Temporal expressions are parsed to extract target_date.

    Example: "Remind me to call Mom tomorrow at 3pm"
    - action_description: "call Mom"
    - target_date: 1736726400000 (tomorrow 3pm in ms)

    Attributes:
        action_description: What the user wants to be reminded about
        target_date: Target reminder time in Unix milliseconds (optional)
    """

    action_description: str = ""
    target_date: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate and set defaults."""
        super().__post_init__()
        # Ensure signal_type is correct
        object.__setattr__(self, "signal_type", IntentSignalType.REMINDER)


@dataclass
class DecisionSignal(IntentSignal):
    """
    seek_advice intent → st_prospective DECISION.

    Created when UltraBERT classifies intent as 'seek_advice'.
    Captures pending decisions that need future resolution.

    Example: "Should I take the job offer or stay at my current company?"
    - decision_context: "job decision"
    - options_mentioned: ["take the job offer", "stay at current company"]

    Attributes:
        decision_context: Description of the decision situation
        options_mentioned: List of options explicitly mentioned in text
    """

    decision_context: str = ""
    options_mentioned: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and set defaults."""
        super().__post_init__()
        object.__setattr__(self, "signal_type", IntentSignalType.DECISION)


@dataclass
class LessonSignal(IntentSignal):
    """
    reflect intent → st_sem LESSON.

    Created when UltraBERT classifies intent as 'reflect'.
    Captures insights or lessons learned from experiences.

    Example: "I learned that patience is really important when teaching kids"
    - lesson_description: "patience is important when teaching kids"
    - topic_entities: ["kids"]

    Attributes:
        lesson_description: The insight or lesson learned
        topic_entities: Entity IDs this lesson relates to
    """

    lesson_description: str = ""
    topic_entities: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and set defaults."""
        super().__post_init__()
        object.__setattr__(self, "signal_type", IntentSignalType.LESSON)


@dataclass
class EmotionalSignal(IntentSignal):
    """
    express_feeling intent → st_sem EMOTIONAL_TREND.

    Created when UltraBERT classifies intent as 'express_feeling'.
    Tracks emotional patterns over time for trend detection.

    Example: "I'm feeling so grateful for my family today"
    - emotion_label: "gratitude"
    - intensity: 0.8
    - target_entities: [<family_entity_id>]

    Attributes:
        emotion_label: Detected emotion (from emotions_json)
        intensity: Emotional intensity [0.0, 1.0]
        target_entities: Entity IDs the emotion is directed at
    """

    emotion_label: str = "neutral"
    intensity: float = 0.5
    target_entities: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and set defaults."""
        super().__post_init__()
        object.__setattr__(self, "signal_type", IntentSignalType.EMOTIONAL_TREND)
        if not 0.0 <= self.intensity <= 1.0:
            raise ValueError(f"intensity must be [0.0, 1.0], got {self.intensity}")


@dataclass
class MilestoneSignal(IntentSignal):
    """
    share_news intent → st_kg_dom milestone.

    Created when UltraBERT classifies intent as 'share_news'.
    Records significant life events for entity timelines.

    Example: "Emma got accepted to Stanford!"
    - milestone_type: ACHIEVEMENT
    - entity_id: <emma_entity_id>
    - milestone_description: "accepted to Stanford"

    Attributes:
        milestone_type: Category of milestone (ACHIEVEMENT, ANNOUNCEMENT, etc.)
        entity_id: Primary entity this milestone is about
        milestone_description: Brief description of the milestone
    """

    milestone_type: MilestoneType = MilestoneType.ANNOUNCEMENT
    entity_id: str = ""
    milestone_description: str = ""

    def __post_init__(self) -> None:
        """Validate and set defaults."""
        super().__post_init__()
        object.__setattr__(self, "signal_type", IntentSignalType.MILESTONE)


@dataclass
class QueryBoostSignal(IntentSignal):
    """
    query_memory intent → increment query_count.

    Created when UltraBERT classifies intent as 'query_memory'.
    Boosts entity/edge relevance based on user queries.

    Example: "When did we last visit Grandma?"
    - entity_ids: [<grandma_entity_id>]
    - edge_ids: [<visit_edge_id>]

    Attributes:
        entity_ids: Entity IDs mentioned in the query
        edge_ids: Edge IDs that would be traversed
    """

    entity_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and set defaults."""
        super().__post_init__()
        object.__setattr__(self, "signal_type", IntentSignalType.QUERY_BOOST)


# Type alias for all signal types
AnyIntentSignal = (
    ReminderSignal
    | DecisionSignal
    | LessonSignal
    | EmotionalSignal
    | MilestoneSignal
    | QueryBoostSignal
)
