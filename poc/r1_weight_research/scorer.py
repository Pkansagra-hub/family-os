"""Phase 3: R1 Importance Scoring Formula.

Standalone implementation of the proposed enhanced R1 formula from
Discovery doc Section 16.6.2. Takes an R1SignalVector + WeightConfig
and returns an importance score [0, 1].

This is a RESEARCH scorer -- no production dependencies, no database,
no pipeline context. Pure math on signal vectors.
"""

from __future__ import annotations

import math

from .config import (
    ELABORATION_BOOST,
    EVENT_TYPE_MULTIPLIERS,
    INTENT_BOOST_MULTIPLIERS,
    INTIMACY_SCALE,
    LOG2_10,
    NOVELTY_NUMERIC,
    TEMPORAL_BOOST,
    WeightConfig,
)
from .signal_derive import R1SignalVector


def compute_emotional(vec: R1SignalVector, cfg: WeightConfig) -> float:
    """Emotional component: weighted sum of |sentiment|, |valence|, arousal.

    Range: [0, cfg.emotional_total]
    """
    return (
        cfg.sentiment_w * abs(vec.sentiment_score)
        + cfg.affect_w * abs(vec.affect_valence)
        + cfg.arousal_w * vec.affect_arousal
    )


def compute_surprise(vec: R1SignalVector, cfg: WeightConfig) -> float:
    """Surprise component.

    Range: [0, cfg.surprise_w]
    """
    return cfg.surprise_w * vec.surprise_level


def compute_novelty(vec: R1SignalVector, cfg: WeightConfig) -> float:
    """Novelty component from categorical novelty -> numeric.

    Range: [0, cfg.novelty_w]
    """
    numeric = NOVELTY_NUMERIC.get(vec.novelty, 0.30)
    return cfg.novelty_w * numeric


def compute_social(vec: R1SignalVector, cfg: WeightConfig) -> float:
    """Social component: log-scaled participant count * intimacy scale.

    Uses log2(participants) / log2(10) capped at 1.0, then multiplied
    by intimacy scale (HIGH=1.2, MEDIUM=1.0, LOW=0.8).

    Range: [0, cfg.social_w * 1.2]  (can slightly exceed social_w with HIGH intimacy)
    """
    if vec.num_participants <= 1:
        participant_factor = 0.0
    else:
        participant_factor = min(1.0, math.log2(vec.num_participants) / LOG2_10)

    intimacy_mult = INTIMACY_SCALE.get(vec.social_intimacy, 1.0)
    return cfg.social_w * participant_factor * intimacy_mult


def compute_identity(vec: R1SignalVector, cfg: WeightConfig) -> float:
    """Identity component from identity_relevance [0, 1].

    Range: [0, cfg.identity_w]
    """
    return cfg.identity_w * vec.identity_relevance


def compute_recency(
    vec: R1SignalVector,
    cfg: WeightConfig,
    recency_factor: float = 1.0,
) -> float:
    """Recency component.

    recency_factor should be exp(-lambda * hours_since_event) in [0, 1].
    For this research, default is 1.0 (all events treated as fresh).
    Phase 5 will test different lambda values.

    Range: [0, cfg.recency_w]
    """
    return cfg.recency_w * recency_factor


def compute_importance(
    vec: R1SignalVector,
    cfg: WeightConfig,
    recency_factor: float = 1.0,
) -> float:
    """Full R1 importance formula from Discovery doc Section 16.6.2.

    Components (additive, sum to ~1.0):
      emotional + surprise + novelty + social + identity + recency

    Multiplicative modulators:
      elaboration_boost * temporal_boost * event_type_mult * intent_boost
      * source_reliability

    Note: goal_boost, arc_boost, memory_tier_mult are all 1.0 for this
    dataset (not derivable). They are included as no-ops for formula
    completeness.

    Returns: float in [0.0, 1.0] (clamped)
    """
    # --- Additive components ---
    base = (
        compute_emotional(vec, cfg)
        + compute_surprise(vec, cfg)
        + compute_novelty(vec, cfg)
        + compute_social(vec, cfg)
        + compute_identity(vec, cfg)
        + compute_recency(vec, cfg, recency_factor)
    )

    # --- Multiplicative modulators ---
    elab_boost = ELABORATION_BOOST.get(vec.elaboration_depth, 1.0)
    temporal_boost = TEMPORAL_BOOST.get(vec.temporal_orientation, 1.0)
    event_type_mult = EVENT_TYPE_MULTIPLIERS.get(vec.activity_type, 1.0)
    intent_boost = INTENT_BOOST_MULTIPLIERS.get(vec.intent, 1.0)

    # Constants for this dataset (no variance)
    source_reliability = vec.source_reliability  # 0.95 for all
    goal_boost = 1.0  # narrative_is_goal_event not derivable
    arc_boost = 1.0  # narrative_arc_position not derivable
    tier_mult = 1.0  # memory_tier is what we compute, not input

    importance = (
        base
        * elab_boost
        * temporal_boost
        * event_type_mult
        * intent_boost
        * source_reliability
        * goal_boost
        * arc_boost
        * tier_mult
    )

    return max(0.0, min(1.0, importance))


def score_to_tier(score: float) -> str:
    """Convert importance score to tier label using threshold bands.

    These thresholds are initial calibration targets from the discovery doc.
    The weight research will validate whether these create clean separations.
    """
    if score >= 0.80:
        return "CRITICAL"
    if score >= 0.60:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM_HIGH"
    if score >= 0.30:
        return "MEDIUM"
    if score >= 0.15:
        return "LOW_MEDIUM"
    return "LOW"
