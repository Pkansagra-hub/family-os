"""
Grounding Signal Collector -- Build training data from P03 phase outputs.

Implements ADR-K025: R3 reconciliation-based grounding signals for the
ImportanceWeightLearner. Extracts features from P03EventState and maps
R3 reconciliation actions to binary grounding labels.

Issue 5.W.2.2: Grounding signal collector
Issue 5.W.2.3: Wire grounding signals to TrainingBatch construction

Training Flow:
    P03 Cycle:
      R0 -> R1 (score events) -> R2 (cluster) -> R3 (reconcile)
      -> [THIS MODULE: extract features + grounding labels]
      -> build TrainingBatch -> learner.train_step()

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

from k0.modules.consolidation.algorithms.importance_weight_learner import (
    TrainingBatch,
    TrainingSample,
)

if TYPE_CHECKING:
    from k0.pipelines.p03.event_state import P03EventState

logger = logging.getLogger(__name__)


# =============================================================================
# Grounding Signal Configuration
# =============================================================================


# R3 reconciliation action -> (is_grounded, confidence)
# Per ADR-K025 Table
RECONCILIATION_GROUNDING: Dict[str, tuple] = {
    "REINFORCE": (True, 0.8),
    "EXTEND": (True, 0.7),
    "CREATE": (True, 0.5),
    "EVOLVE": (True, 0.6),
    "CONTRADICT": (True, 0.4),
    "SKIP": (False, 0.9),
    "PRUNE": (False, 0.8),
    # PENDING is excluded -- not yet decided
}

# Novelty categorical -> numeric (mirrors ImportanceScorer.NOVELTY_MAP)
NOVELTY_MAP: Dict[str, float] = {
    "ROUTINE": 0.10,
    "EXPECTED": 0.30,
    "NOVEL": 0.70,
    "SURPRISING": 1.00,
}

# Intimacy level -> scale factor (mirrors ImportanceScorer.INTIMACY_SCALE)
INTIMACY_SCALE: Dict[str, float] = {
    "HIGH": 1.2,
    "MEDIUM": 1.0,
    "MED": 1.0,
    "LOW": 0.8,
}

# log2(10) for social factor normalization
LOG2_10 = math.log2(10)

# Recency decay rate (hours^-1) -- same as scorer
RECENCY_DECAY_RATE = 0.005


# =============================================================================
# Grounding Signal Data
# =============================================================================


@dataclass
class GroundingSignal:
    """
    Grounding label for a single event.

    Attributes:
        event_id: Event identifier
        was_grounded: Binary label for training
        confidence: Signal reliability [0, 1]
        source: Signal source identifier
        action: Original R3 reconciliation action
    """

    event_id: str
    was_grounded: bool
    confidence: float
    source: str = "r3_reconciliation"
    action: str = ""


# =============================================================================
# Feature Extraction
# =============================================================================


def extract_features(event: "P03EventState", now_ms: Optional[int] = None) -> TrainingSample:
    """
    Extract 8 CONFIG_B features from P03EventState for weight learner training.

    Maps raw P03EventState fields to normalized [0, 1] feature values
    using the same transforms as ImportanceScorer (ADR-K024/K025).

    Args:
        event: P03EventState after R3 (must have reconciliation_action set)
        now_ms: Current time in milliseconds (defaults to time.time() * 1000)

    Returns:
        TrainingSample with 8 features and grounding label
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    # 1. Sentiment: abs(sentiment_score) [0, 1]
    sentiment = min(1.0, abs(event.sentiment_score))

    # 2. Affect: abs(affect_valence) [0, 1]
    affect = min(1.0, abs(event.affect_valence))

    # 3. Arousal: direct [0, 1]
    arousal = max(0.0, min(1.0, event.affect_arousal))

    # 4. Surprise: direct [0, 1]
    surprise = max(0.0, min(1.0, event.surprise_level))

    # 5. Novelty: categorical -> numeric via NOVELTY_MAP
    novelty_cat = getattr(event, "novelty", "")
    if novelty_cat and novelty_cat.upper() in NOVELTY_MAP:
        novelty = NOVELTY_MAP[novelty_cat.upper()]
    else:
        # Fallback to salience_score or novelty_score
        novelty = max(0.0, min(1.0, getattr(event, "salience_score", 0.0)))

    # 6. Social: log2(participants)/log2(10) * intimacy_scale
    num_p = getattr(event, "num_participants", 0)
    if num_p > 1:
        log_factor = min(1.0, math.log2(num_p) / LOG2_10)
        intimacy_key = getattr(event, "social_intimacy", "")
        if intimacy_key:
            intimacy_key = intimacy_key.upper()
        intimacy = INTIMACY_SCALE.get(intimacy_key, 1.0)
        social = min(1.0, log_factor * intimacy)
    else:
        social = 0.0

    # 7. Identity: direct [0, 1]
    identity = max(0.0, min(1.0, getattr(event, "identity_relevance", 0.0)))

    # 8. Recency: exp(-0.005 * hours_ago)
    if event.timestamp > 0 and now_ms > event.timestamp:
        hours_ago = (now_ms - event.timestamp) / (3600 * 1000)
        recency = math.exp(-RECENCY_DECAY_RATE * hours_ago)
    else:
        recency = 1.0  # Unknown timestamp -> treat as recent

    # Grounding label from R3 reconciliation
    action_name = (
        event.reconciliation_action.value
        if hasattr(event.reconciliation_action, "value")
        else str(event.reconciliation_action)
    )

    grounding = RECONCILIATION_GROUNDING.get(action_name)
    if grounding is not None:
        was_grounded = grounding[0]
    else:
        # PENDING or unknown -> default to not grounded
        was_grounded = False

    # Days ago for sample weighting
    if event.timestamp > 0 and now_ms > event.timestamp:
        days_ago = (now_ms - event.timestamp) / (86400 * 1000)
    else:
        days_ago = 0.0

    return TrainingSample(
        sentiment_score=sentiment,
        affect_score=affect,
        arousal_score=arousal,
        surprise_score=surprise,
        novelty_score=novelty,
        social_score=social,
        identity_score=identity,
        recency_score=recency,
        was_grounded=was_grounded,
        days_ago=days_ago,
    )


# =============================================================================
# Grounding Signal Collector
# =============================================================================


class GroundingSignalCollector:
    """
    Collects grounding signals from P03 phase outputs and builds training data.

    Primary signal source: R3 reconciliation actions (ADR-K025).
    Future sources can be registered via add_source().

    Usage:
        collector = GroundingSignalCollector()
        batch = collector.build_training_batch(event_states, now_ms=now_ms)
        if len(batch) >= learner.config.min_batch_size:
            result = learner.train_step(batch)
    """

    def __init__(self) -> None:
        """Initialize collector with R3 reconciliation as default source."""
        self._min_confidence: float = 0.0  # Accept all signals by default

    def collect_grounding_signals(
        self,
        event_states: List["P03EventState"],
    ) -> List[GroundingSignal]:
        """
        Extract grounding signals from R3 reconciliation actions.

        Only events with non-PENDING reconciliation actions are included.

        Args:
            event_states: List of P03EventState after R3 has run

        Returns:
            List of GroundingSignal for events with known grounding status
        """
        signals: List[GroundingSignal] = []

        for event in event_states:
            action_name = (
                event.reconciliation_action.value
                if hasattr(event.reconciliation_action, "value")
                else str(event.reconciliation_action)
            )

            grounding = RECONCILIATION_GROUNDING.get(action_name)
            if grounding is None:
                # PENDING or unknown action -- skip
                continue

            was_grounded, confidence = grounding

            if confidence < self._min_confidence:
                continue

            signals.append(
                GroundingSignal(
                    event_id=event.event_id,
                    was_grounded=was_grounded,
                    confidence=confidence,
                    source="r3_reconciliation",
                    action=action_name,
                )
            )

        logger.debug(
            "Collected grounding signals",
            extra={
                "total_events": len(event_states),
                "signals_collected": len(signals),
                "grounded_count": sum(1 for s in signals if s.was_grounded),
                "not_grounded_count": sum(1 for s in signals if not s.was_grounded),
            },
        )

        return signals

    def build_training_batch(
        self,
        event_states: List["P03EventState"],
        now_ms: Optional[int] = None,
    ) -> TrainingBatch:
        """
        Build a TrainingBatch from P03EventState list after R3.

        Extracts 8 CONFIG_B features from each event and maps R3
        reconciliation actions to binary grounding labels.

        Only events with non-PENDING reconciliation actions are included
        (PENDING events have no grounding signal yet).

        Args:
            event_states: List of P03EventState after R3 has run
            now_ms: Current time in milliseconds (defaults to now)

        Returns:
            TrainingBatch ready for ImportanceWeightLearner.train_step()
        """
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        samples: List[TrainingSample] = []

        for event in event_states:
            # Skip events without reconciliation decision
            action_name = (
                event.reconciliation_action.value
                if hasattr(event.reconciliation_action, "value")
                else str(event.reconciliation_action)
            )

            if action_name not in RECONCILIATION_GROUNDING:
                continue

            sample = extract_features(event, now_ms=now_ms)
            samples.append(sample)

        batch = TrainingBatch(samples=samples)

        logger.info(
            "Built training batch from grounding signals",
            extra={
                "total_events": len(event_states),
                "batch_size": len(batch),
                "grounded_count": sum(1 for s in samples if s.was_grounded),
                "not_grounded_count": sum(1 for s in samples if not s.was_grounded),
            },
        )

        return batch
