"""
ImportanceScorer - Compute importance scores for hippocampal event selection.

This module implements the importance scoring algorithm that determines which
events should be prioritized for memory consolidation. Based on cognitive
neuroscience principles (McGaugh, 2004) showing emotional memories are more
strongly encoded due to amygdala-hippocampus interaction.

Spec Reference:
    - Dossier 2.4: Scientific Formulas - Importance Score
    - Dossier Appendix C.2.1: Algorithm Specification
    - M4_EXECUTION.md Issue 4.1.1
    - P03 R1 Discovery: P03_R1_IMPORTANCE_SCORING_DISCOVERY.md

Formula (CONFIG_B, POC validated -- 562K events, 120/120 scenarios):
    base = emotional + surprise + novelty + social + identity + recency
    importance = clamp(base * elab * goal * arc * temporal
                       * type * intent * tier * reliability, 0, 1)

Where (6 additive, 8 weights summing to 1.0):
    - emotional = sent_w*|sent| + affect_w*|val| + arousal_w*arousal
    - surprise  = surprise_w * surprise_level
    - novelty   = novelty_w * NOVELTY_MAP[categorical]
    - social    = social_w * log2(participants)/3.32 * intimacy_scale
    - identity  = identity_w * identity_signal
    - recency   = recency_w * exp(-0.005 * hours_since_event)

7 multiplicative modulators:
    elab, goal, arc, temporal, type, intent, tier, reliability

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration and Types
# =============================================================================


@dataclass(frozen=True)
class ImportanceWeights:
    """
    Configurable weights for importance scoring components.

    These weights determine how much each factor contributes to
    the final importance score. They sum to 1.0 for normalization.

    CONFIG_B defaults (POC validated -- 562K events, 120/120 scenarios):
        Emotional group (0.30): sentiment=0.10, affect=0.12, arousal=0.08
        Surprise: 0.15
        Novelty: 0.15
        Social: 0.15
        Identity: 0.10
        Recency: 0.15
    """

    # Emotional group (combined = 0.30)
    sentiment_weight: float = 0.10
    affect_weight: float = 0.12
    arousal_weight: float = 0.08
    # Cognitive signals
    surprise_weight: float = 0.15
    novelty_weight: float = 0.15
    # Social + identity
    social_weight: float = 0.15
    identity_weight: float = 0.10
    # Temporal
    recency_weight: float = 0.15

    def total(self) -> float:
        """Sum of all weights (should be 1.0 for normalization)."""
        return (
            self.sentiment_weight
            + self.affect_weight
            + self.arousal_weight
            + self.surprise_weight
            + self.novelty_weight
            + self.social_weight
            + self.identity_weight
            + self.recency_weight
        )

    def as_dict(self) -> Dict[str, float]:
        """Return weights as dictionary for serialization."""
        return {
            "sentiment": self.sentiment_weight,
            "affect": self.affect_weight,
            "arousal": self.arousal_weight,
            "surprise": self.surprise_weight,
            "novelty": self.novelty_weight,
            "social": self.social_weight,
            "identity": self.identity_weight,
            "recency": self.recency_weight,
        }


@dataclass
class ImportanceBreakdown:
    """
    Component breakdown of importance score for audit logging.

    This provides full transparency into how the final score was computed,
    enabling debugging, explainability, and learning feedback loops.

    6 additive components + base_score + 7 multiplicative modulators + final.
    """

    # 6 additive components
    emotional_component: float = 0.0  # Combined sentiment + affect + arousal
    surprise_component: float = 0.0  # Cognitive surprise contribution
    novelty_component: float = 0.0  # Information novelty contribution
    social_component: float = 0.0  # Social relevance contribution
    identity_component: float = 0.0  # Self-referential identity contribution
    recency_component: float = 0.0  # Temporal freshness contribution
    # Base score (sum of 6 components, before modulators)
    base_score: float = 0.0
    # 7 multiplicative modulators
    elab_boost: float = 1.0  # Elaboration depth multiplier
    goal_boost: float = 1.0  # Narrative goal event multiplier
    arc_boost: float = 1.0  # Narrative arc position multiplier
    temporal_boost: float = 1.0  # Temporal orientation multiplier
    type_multiplier: float = 1.0  # Event type multiplier
    intent_boost: float = 1.0  # Intent classification multiplier
    tier_multiplier: float = 1.0  # Memory tier multiplier
    reliability: float = 1.0  # Source reliability (floored)
    # Final
    final_score: float = 0.0  # Final normalized score [0, 1]
    weights_source: str = "static"  # "static", "learned", "per-space", etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for audit logging outputs."""
        return {
            "emotional_component": self.emotional_component,
            "surprise_component": self.surprise_component,
            "novelty_component": self.novelty_component,
            "social_component": self.social_component,
            "identity_component": self.identity_component,
            "recency_component": self.recency_component,
            "base_score": self.base_score,
            "elab_boost": self.elab_boost,
            "goal_boost": self.goal_boost,
            "arc_boost": self.arc_boost,
            "temporal_boost": self.temporal_boost,
            "type_multiplier": self.type_multiplier,
            "intent_boost": self.intent_boost,
            "tier_multiplier": self.tier_multiplier,
            "reliability": self.reliability,
            "final_score": self.final_score,
            "weights_source": self.weights_source,
        }


class WeightStoreProtocol(Protocol):
    """Protocol for weight storage backend."""

    async def get_weights(
        self,
        space_id: str,
        param_prefix: str,
    ) -> Optional[LearnedWeights]: ...


@dataclass
class LearnedWeights:
    """Container for learned weights from st_learned_weights."""

    weights: Dict[str, float]
    sample_count: int
    updated_at: int  # MILLISECONDS


# =============================================================================
# ImportanceScorer Class
# =============================================================================


class ImportanceScorer:
    """
    Compute importance scores for hippocampal event selection.

    Scientific Basis:
        McGaugh (2004) - Emotional memories are more strongly encoded
        due to amygdala-hippocampus interaction. Events with high
        emotional salience, novelty, or social significance are
        prioritized for consolidation.

    Scoring Formula (CONFIG_B -- POC validated 120/120 scenarios):
        base = emotional + surprise + novelty + social + identity + recency
        importance = clamp(base * elab * goal * arc * temporal
                          * type * intent * tier * reliability, 0, 1)

        Where (6 additive components, 8 weights summing to 1.0):
        - emotional = sent_w*|sent| + affect_w*|val| + arousal_w*arousal
        - surprise  = surprise_w * surprise_level
        - novelty   = novelty_w * NOVELTY_MAP[categorical]
        - social    = social_w * log2(participants)/3.32 * intimacy_scale
        - identity  = identity_w * identity_signal
        - recency   = recency_w * exp(-0.005 * hours_since_event)

    Weight Learning:
        Initially uses CONFIG_B static weights. After 500+ samples with
        outcome feedback, switches to learned weights from st_learned_weights.

    Usage:
        scorer = ImportanceScorer(space_id="sp_123", weight_store=store)
        events = [P03EventState(...), ...]
        scored = await scorer.score_batch(events)
    """

    # Static default weights (used until 500 samples for learning)
    DEFAULT_WEIGHTS = ImportanceWeights()

    # Event type multipliers from Dossier C.2.1
    # Higher multipliers boost importance for significant event types
    EVENT_TYPE_MULTIPLIERS: Dict[str, float] = {
        "message": 1.0,  # Default text messages
        "chat": 1.0,  # Chat conversations
        "photo": 1.2,  # Visual memories weighted higher
        "image": 1.2,  # Same as photo
        "video": 1.3,  # Video memories
        "milestone": 2.0,  # Birthdays, anniversaries, achievements
        "celebration": 2.0,  # Special occasions
        "routine": 0.5,  # Daily repeated events (lower priority)
        "location": 0.8,  # Check-ins and location updates
        "voice": 1.1,  # Voice memos
        "audio": 1.1,  # Same as voice
        "calendar": 0.9,  # Calendar events
        "transaction": 0.6,  # Financial transactions
    }

    # Minimum samples before using learned weights
    MIN_SAMPLES_FOR_LEARNED_WEIGHTS = 500

    # Log2(10) for social factor normalization
    LOG2_10 = 3.321928  # log2(10)

    # Intent-based boost multipliers (GAP-001 Milestone 8, Issue 8.2)
    # UltraBERT intent types affect memory salience based on cognitive significance
    # Scientific basis: Retrieval practice strengthens memory (Roediger & Karpicke, 2006)
    # Intentional actions (planning, reminders) indicate future relevance
    INTENT_BOOST_MULTIPLIERS: Dict[str, float] = {
        "query_memory": 1.20,  # Retrieval strengthens memory traces
        "share_news": 1.20,  # News-sharing events are typically significant
        "set_reminder": 1.15,  # Reminders indicate future importance
        "make_plan": 1.15,  # Planning content has intentional significance
        "seek_advice": 1.10,  # Decision-making context matters
        "reflect": 1.10,  # Reflective content often leads to semantic patterns
        "express_feeling": 1.00,  # Already captured by emotional_intensity component
        "casual_chat": 0.90,  # Routine conversation, slightly lower salience
    }

    # =========================================================================
    # CONFIG_B Constants (POC validated -- Discovery 16.6)
    # =========================================================================

    # Recency decay (POC Phase 5: lambda=0.005, half-life ~139h / ~6 days)
    RECENCY_LAMBDA: float = 0.005

    # Source reliability floor (POC Phase 5: floor=0.3)
    # Prevents total suppression -- even untrusted sources keep 30% signal
    RELIABILITY_FLOOR: float = 0.3

    # Goal event boost (Discovery 16.6 Q8: stacks with arc_boost)
    GOAL_BOOST: float = 1.15

    # Novelty categorical -> numeric (Discovery 16.3.1)
    # P03EventState.novelty is a categorical string from MW v2
    NOVELTY_MAP: Dict[str, float] = {
        "ROUTINE": 0.10,
        "EXPECTED": 0.30,
        "NOVEL": 0.70,
        "SURPRISING": 1.00,
    }

    # Elaboration depth -> multiplicative boost (Discovery 16.3.2)
    # NOT additive -- deeper elaboration amplifies base score
    ELABORATION_MAP: Dict[str, float] = {
        "MENTION": 1.00,
        "DISCUSSED": 1.05,
        "ELABORATED": 1.10,
        "DEEPLY_PROCESSED": 1.15,
    }

    # Temporal orientation -> boost (Discovery 16.3.4)
    TEMPORAL_MAP: Dict[str, float] = {
        "PAST": 1.00,
        "ONGOING": 1.05,
        "FUTURE_COMMITMENT": 1.10,
    }

    # Narrative arc position -> boost (Discovery 16.3.5)
    ARC_MAP: Dict[str, float] = {
        "EXPOSITION": 1.00,
        "RISING_ACTION": 1.05,
        "CLIMAX": 1.15,
        "RESOLUTION": 1.00,
    }

    # Memory tier -> multiplier (Discovery 16.4)
    # routine is baseline; higher tiers amplify importance
    MEMORY_TIER_MAP: Dict[str, float] = {
        "routine": 1.00,
        "notable": 1.10,
        "significant": 1.25,
        "landmark": 1.50,
    }

    # Intimacy scale multiplier for social factor (Discovery 16.6 Q6)
    # Multiplicative to social, not additive (POC validated)
    INTIMACY_SCALE: Dict[str, float] = {
        "HIGH": 1.20,
        "MEDIUM": 1.00,
        "LOW": 0.80,
    }

    # Source type -> base reliability (Discovery 16.3.3)
    # Used when event.source_reliability is not set by MW
    SOURCE_TYPE_RELIABILITY: Dict[str, float] = {
        "user_stated": 0.95,
        "system_inferred": 0.60,
        "device_observed": 0.80,
        "third_party": 0.70,
    }

    def __init__(
        self,
        space_id: str,
        weight_store: Optional[WeightStoreProtocol] = None,
    ):
        """
        Initialize ImportanceScorer for a space.

        Args:
            space_id: User/family space ID for weight lookup
            weight_store: Optional backend for learned weights.
                         If None, always uses static defaults.
        """
        self.space_id = space_id
        self.weight_store = weight_store
        self._cached_weights: Optional[ImportanceWeights] = None
        self._weights_source: str = "static"
        self._cached_sample_count: int = 0

    @staticmethod
    def _weights_from_dict(
        d: Dict[str, float],
        defaults: Optional[ImportanceWeights] = None,
    ) -> ImportanceWeights:
        """
        Construct ImportanceWeights from a dictionary.

        Uses CONFIG_B defaults for any missing keys. This avoids
        hardcoding 8 field mappings at every construction site.

        Args:
            d: Weight dictionary (keys match as_dict() output).
            defaults: Fallback ImportanceWeights (default: CONFIG_B).

        Returns:
            ImportanceWeights with values from dict + defaults.
        """
        fb = defaults or ImportanceWeights()
        return ImportanceWeights(
            sentiment_weight=d.get("sentiment", fb.sentiment_weight),
            affect_weight=d.get("affect", fb.affect_weight),
            arousal_weight=d.get("arousal", fb.arousal_weight),
            surprise_weight=d.get("surprise", fb.surprise_weight),
            novelty_weight=d.get("novelty", fb.novelty_weight),
            social_weight=d.get("social", fb.social_weight),
            identity_weight=d.get("identity", fb.identity_weight),
            recency_weight=d.get("recency", fb.recency_weight),
        )

    async def get_weights(self) -> ImportanceWeights:
        """
        Load weights, using learned weights if sufficient samples exist.

        Returns:
            ImportanceWeights with either static defaults or learned values

        Priority:
            1. Cached weights (if already loaded)
            2. Learned weights (if sample_count >= 500)
            3. Static defaults
        """
        if self._cached_weights is not None:
            return self._cached_weights

        # Try to load learned weights if store is available
        if self.weight_store is not None:
            try:
                learned = await self.weight_store.get_weights(
                    space_id=self.space_id,
                    param_prefix="importance_",
                )

                if (
                    learned is not None
                    and learned.sample_count >= self.MIN_SAMPLES_FOR_LEARNED_WEIGHTS
                ):
                    self._cached_weights = self._weights_from_dict(learned.weights)
                    self._weights_source = "learned"
                    logger.info(
                        "Using learned importance weights",
                        extra={
                            "space_id": self.space_id,
                            "sample_count": learned.sample_count,
                        },
                    )
                    return self._cached_weights

            except Exception as e:
                logger.warning(
                    "Failed to load learned weights, using static defaults",
                    extra={"space_id": self.space_id, "error": str(e)},
                )

        # Fallback to static defaults
        self._cached_weights = self.DEFAULT_WEIGHTS
        self._weights_source = "static"
        logger.debug(
            "Using static default weights",
            extra={"space_id": self.space_id},
        )
        return self._cached_weights

    async def get_weights_with_cold_start(
        self,
        global_store: Optional[WeightStoreProtocol] = None,
    ) -> Tuple[ImportanceWeights, str, int]:
        """
        Get weights with cold start fallback and progressive blending.

        Issue 4.1.6: Cold Start Strategy
        Implements 3-level fallback with progressive blending:
            1. Per-space learned weights (if available)
            2. Global learned weights (if per-space insufficient)
            3. Static priors (fallback)

        Progressive Blending Formula:
            α = sample_count / 500
            blended_weight = α × learned + (1 - α) × prior

        Blending Behavior:
            - 0-99 samples: Pure static priors (α=0)
            - 100-499 samples: Progressive blending
            - 500+ samples: Pure learned weights (α=1)

        Args:
            global_store: Optional separate store for global weights.
                         If None, uses self.weight_store for both.

        Returns:
            Tuple of:
                - ImportanceWeights: Blended or static weights
                - str: Source description ("per-space", "global-blend", "static")
                - int: Sample count used for blending
        """
        # Check cache first
        if self._cached_weights is not None:
            # Extract sample count from source if available
            sample_count = 0
            if (
                "blend" in self._weights_source
                or "per-space" in self._weights_source
                or "global" in self._weights_source
            ):
                sample_count = getattr(self, "_cached_sample_count", 0)
            return self._cached_weights, self._weights_source, sample_count

        static_priors = self.DEFAULT_WEIGHTS
        min_blend_samples = 100  # Below this, use pure static
        full_blend_samples = self.MIN_SAMPLES_FOR_LEARNED_WEIGHTS  # 500

        # Try per-space weights first
        if self.weight_store is not None:
            try:
                space_weights = await self.weight_store.get_weights(
                    space_id=self.space_id,
                    param_prefix="importance_",
                )

                if space_weights is not None and space_weights.sample_count >= min_blend_samples:
                    # Compute blend factor α = sample_count / 500
                    alpha = min(1.0, space_weights.sample_count / full_blend_samples)

                    if alpha >= 1.0:
                        # Full learned weights (500+ samples)
                        self._cached_weights = self._weights_from_dict(space_weights.weights)
                        self._weights_source = "per-space"
                        self._cached_sample_count = space_weights.sample_count
                        logger.info(
                            "Using full learned per-space weights",
                            extra={
                                "space_id": self.space_id,
                                "sample_count": space_weights.sample_count,
                                "alpha": alpha,
                            },
                        )
                        return self._cached_weights, "per-space", space_weights.sample_count
                    else:
                        # Progressive blending (100-499 samples)
                        blended = self._blend_weights(
                            learned=space_weights.weights,
                            static=static_priors.as_dict(),
                            alpha=alpha,
                        )
                        self._cached_weights = self._weights_from_dict(blended)
                        self._weights_source = f"per-space-blend-{alpha:.2f}"
                        self._cached_sample_count = space_weights.sample_count
                        logger.info(
                            "Using blended per-space weights",
                            extra={
                                "space_id": self.space_id,
                                "sample_count": space_weights.sample_count,
                                "alpha": alpha,
                                "blended_weights": blended,
                            },
                        )
                        return self._cached_weights, "per-space-blend", space_weights.sample_count

            except Exception as e:
                logger.warning(
                    "Failed to load per-space weights",
                    extra={"space_id": self.space_id, "error": str(e)},
                )

        # Try global weights fallback
        global_weight_store = global_store or self.weight_store
        if global_weight_store is not None:
            try:
                global_weights = await global_weight_store.get_weights(
                    space_id="__global__",
                    param_prefix="importance_",
                )

                if global_weights is not None and global_weights.sample_count >= min_blend_samples:
                    alpha = min(1.0, global_weights.sample_count / full_blend_samples)

                    if alpha >= 1.0:
                        self._cached_weights = self._weights_from_dict(global_weights.weights)
                        self._weights_source = "global"
                        self._cached_sample_count = global_weights.sample_count
                        logger.info(
                            "Using global learned weights (space fallback)",
                            extra={
                                "space_id": self.space_id,
                                "global_sample_count": global_weights.sample_count,
                            },
                        )
                        return self._cached_weights, "global", global_weights.sample_count
                    else:
                        blended = self._blend_weights(
                            learned=global_weights.weights,
                            static=static_priors.as_dict(),
                            alpha=alpha,
                        )
                        self._cached_weights = self._weights_from_dict(blended)
                        self._weights_source = f"global-blend-{alpha:.2f}"
                        self._cached_sample_count = global_weights.sample_count
                        logger.info(
                            "Using blended global weights",
                            extra={
                                "space_id": self.space_id,
                                "global_sample_count": global_weights.sample_count,
                                "alpha": alpha,
                            },
                        )
                        return self._cached_weights, "global-blend", global_weights.sample_count

            except Exception as e:
                logger.warning(
                    "Failed to load global weights",
                    extra={"space_id": self.space_id, "error": str(e)},
                )

        # Final fallback: static priors
        self._cached_weights = static_priors
        self._weights_source = "static"
        self._cached_sample_count = 0
        logger.debug(
            "Using static default weights (cold start)",
            extra={"space_id": self.space_id},
        )
        return self._cached_weights, "static", 0

    def _blend_weights(
        self,
        learned: Dict[str, float],
        static: Dict[str, float],
        alpha: float,
    ) -> Dict[str, float]:
        """
        Blend learned weights with static priors.

        Formula: blended = α × learned + (1 - α) × static

        Args:
            learned: Learned weight values
            static: Static prior values
            alpha: Blend factor [0, 1] (0 = pure static, 1 = pure learned)

        Returns:
            Blended weight dictionary
        """
        blended: Dict[str, float] = {}
        for key in static:
            learned_val = learned.get(key, static[key])
            static_val = static[key]
            blended[key] = alpha * learned_val + (1 - alpha) * static_val

        # Normalize to sum to 1.0
        total = sum(blended.values())
        if total > 0:
            blended = {k: v / total for k, v in blended.items()}

        return blended

    def invalidate_weight_cache(self) -> None:
        """
        Invalidate cached weights to force reload.

        Call this after Hebbian learning updates weights.
        """
        self._cached_weights = None
        self._weights_source = "static"
        self._cached_sample_count = 0

    def compute_emotional_intensity(
        self,
        sentiment_score: float,
        affect_valence: float,
        affect_arousal: float,
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute emotional intensity from sentiment, affect valence, and arousal.

        Uses absolute values for sentiment and valence because both strong
        positive AND strong negative emotions enhance memory encoding
        (McGaugh, 2004). Arousal is already [0, 1] so no abs() needed.

        CONFIG_B split: sentiment_w=0.10, affect_w=0.12, arousal_w=0.08 (total=0.30)

        Args:
            sentiment_score: Sentiment analysis score [-1, 1]
            affect_valence: Emotional valence [-1, 1]
            affect_arousal: Emotional arousal [0, 1]
            weights: Weight configuration

        Returns:
            Emotional intensity component [0, 0.30]
        """
        sentiment_intensity = abs(sentiment_score)
        affect_intensity = abs(affect_valence)
        arousal = max(0.0, min(1.0, affect_arousal))

        return (
            sentiment_intensity * weights.sentiment_weight
            + affect_intensity * weights.affect_weight
            + arousal * weights.arousal_weight
        )

    def compute_social_factor(
        self,
        num_participants: int,
        social_intimacy: str,
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute social factor from participant count and intimacy level.

        Uses logarithmic scaling multiplied by intimacy scale
        (HIGH=1.2, MEDIUM=1.0, LOW=0.8). POC validated Q6.

        Scale interpretation:
            - 1 person: 0.0 (solo event, no social bonus)
            - 2 people: ~0.30 x weight x intimacy
            - 5 people: ~0.70 x weight x intimacy
            - 10+ people: ~1.0 x weight x intimacy (capped)

        Args:
            num_participants: Number of participants in event
            social_intimacy: Intimacy level (HIGH/MEDIUM/LOW)
            weights: Weight configuration

        Returns:
            Social factor component [0, social_weight x 1.2]
        """
        if num_participants <= 1:
            return 0.0  # Solo event, no social bonus

        # Log scale: log2(count) / log2(10)
        log_factor = min(1.0, math.log2(num_participants) / self.LOG2_10)
        # Intimacy modulates social: HIGH=1.2, MED=1.0, LOW=0.8
        intimacy_key = social_intimacy.upper() if social_intimacy else ""
        intimacy = self.INTIMACY_SCALE.get(intimacy_key, 1.0)
        return log_factor * weights.social_weight * intimacy

    def compute_novelty_factor(
        self,
        novelty_categorical: str,
        salience_fallback: float,
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute novelty factor from categorical novelty level.

        Maps categorical novelty (from MW v2) to numeric:
            ROUTINE=0.10, EXPECTED=0.30, NOVEL=0.70, SURPRISING=1.00

        Falls back to salience_score if novelty categorical is empty
        (pre-MW v2 events).

        Args:
            novelty_categorical: Categorical novelty level from MW v2
            salience_fallback: P02 salience_score [0, 1] as fallback
            weights: Weight configuration

        Returns:
            Novelty factor component [0, novelty_weight]
        """
        if novelty_categorical and novelty_categorical.upper() in self.NOVELTY_MAP:
            novelty_numeric = self.NOVELTY_MAP[novelty_categorical.upper()]
        else:
            # Fallback to salience_score for pre-MW v2 events
            novelty_numeric = max(0.0, min(1.0, salience_fallback))
        return novelty_numeric * weights.novelty_weight

    def compute_surprise_factor(
        self,
        surprise_level: float,
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute surprise factor from cognitive surprise level.

        Surprise enhances memory encoding by triggering prediction-error
        signals in the hippocampus (Ranganath & Rainer, 2003).

        Args:
            surprise_level: Cognitive surprise [0, 1] from MW v2
            weights: Weight configuration

        Returns:
            Surprise factor component [0, surprise_weight]
        """
        clamped = max(0.0, min(1.0, surprise_level))
        return clamped * weights.surprise_weight

    def compute_identity_factor(
        self,
        identity_relevance: float,
        identity_domains_json: str,
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute identity factor from self-referential signals.

        Uses identity_relevance from MW v2 if available (> 0.0).
        Falls back to identity_domains count / 9.0 as proxy
        (POC validated, Discovery 16.6 Q7).

        Args:
            identity_relevance: MW v2 identity relevance [0, 1]
            identity_domains_json: JSON array of identity domain strings
            weights: Weight configuration

        Returns:
            Identity factor component [0, identity_weight]
        """
        import json as _json

        if identity_relevance > 0.0:
            signal = min(1.0, identity_relevance)
        else:
            try:
                domains = _json.loads(identity_domains_json) if identity_domains_json else []
            except (ValueError, TypeError):
                domains = []
            signal = min(1.0, len(domains) / 9.0)

        return signal * weights.identity_weight

    def compute_recency_factor(
        self,
        event_timestamp_ms: int,
        now_ms: int,
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute recency factor using exponential decay.

        Models hippocampal prioritization of fresh experiences
        (Frankland & Bontempi, 2005).

        Formula: recency_w * exp(-lambda * hours_since_event)
        Lambda: 0.005 (half-life ~139h / ~6 days, POC Phase 5)

        Args:
            event_timestamp_ms: Event time (ms since epoch)
            now_ms: Current time (ms since epoch)
            weights: Weight configuration

        Returns:
            Recency factor component [0, recency_weight]
        """
        if event_timestamp_ms <= 0 or now_ms <= 0:
            return 0.0

        hours_since = max(0.0, (now_ms - event_timestamp_ms) / 3_600_000.0)
        decay = math.exp(-self.RECENCY_LAMBDA * hours_since)
        return decay * weights.recency_weight

    def derive_source_reliability(
        self,
        source_reliability: float,
        source_type: str,
    ) -> float:
        """
        Derive source reliability for importance modulation.

        Priority:
            1. MW-provided source_reliability (if != 1.0 default)
            2. SOURCE_TYPE_RELIABILITY lookup by source_type
            3. Default 1.0 (fully trusted)

        Always applies RELIABILITY_FLOOR (0.3) to prevent total
        suppression of any event.

        Args:
            source_reliability: MW v2 source reliability [0, 1]
            source_type: Source type string for lookup fallback

        Returns:
            Floored reliability [RELIABILITY_FLOOR, 1.0]
        """
        if source_reliability < 1.0:
            raw = source_reliability
        elif source_type:
            raw = self.SOURCE_TYPE_RELIABILITY.get(source_type, 1.0)
        else:
            raw = 1.0
        return max(self.RELIABILITY_FLOOR, raw)

    def get_event_type_multiplier(self, content_type: str) -> float:
        """
        Get importance multiplier for event type.

        Args:
            content_type: Event content type (message, photo, etc.)

        Returns:
            Multiplier value (default 1.0 for unknown types)
        """
        # Normalize to lowercase for matching
        normalized_type = (content_type or "message").lower().strip()
        return self.EVENT_TYPE_MULTIPLIERS.get(normalized_type, 1.0)

    def compute_importance_score(
        self,
        event: Any,
        weights: ImportanceWeights,
        now_ms: Optional[int] = None,
    ) -> Tuple[float, ImportanceBreakdown]:
        """
        Compute importance score for a single event.

        CONFIG_B Formula (POC validated -- 562K events, 120/120 scenarios):
            base = emotional + surprise + novelty + social + identity + recency
            importance = clamp(base * elab * goal * arc * temporal
                              * type * intent * tier * reliability, 0, 1)

        Args:
            event: P03EventState or object with required attributes
            weights: Weight configuration to use
            now_ms: Current time in ms (for recency). Uses time.time() if None.

        Returns:
            Tuple of (score, breakdown) where:
                - score: Final importance [0.0, 1.0]
                - breakdown: Component values for audit
        """
        import time as _time

        if now_ms is None:
            now_ms = int(_time.time() * 1000)

        # --- Extract event attributes with safe defaults ---
        sentiment_score = getattr(event, "sentiment_score", 0.0) or 0.0
        affect_valence = getattr(event, "affect_valence", 0.0) or 0.0
        affect_arousal = getattr(event, "affect_arousal", 0.0) or 0.0
        surprise_level = getattr(event, "surprise_level", 0.0) or 0.0
        novelty_cat = getattr(event, "novelty", "") or ""
        salience_score = getattr(event, "salience_score", 0.0) or 0.0
        num_participants = getattr(event, "num_participants", 1) or 1
        social_intimacy = getattr(event, "social_intimacy", "") or ""
        identity_relevance_val = getattr(event, "identity_relevance", 0.0) or 0.0
        identity_domains_json = getattr(event, "identity_domains_json", "[]") or "[]"
        event_timestamp = getattr(event, "timestamp", 0) or 0
        elaboration_depth = getattr(event, "elaboration_depth", "") or ""
        narrative_is_goal = getattr(event, "narrative_is_goal_event", False)
        narrative_arc = getattr(event, "narrative_arc_position", "") or ""
        temporal_orientation = getattr(event, "temporal_orientation", "") or ""
        source_reliability_val = getattr(event, "source_reliability", 1.0)
        if source_reliability_val is None:
            source_reliability_val = 1.0
        source_type = getattr(event, "source_type", "") or ""
        memory_tier = getattr(event, "memory_tier", "routine") or "routine"
        content_type = getattr(event, "content_type", "message") or "message"
        # Prefer activity_type_ultrabert for type multiplier, fallback to content_type
        activity_type = getattr(event, "activity_type_ultrabert", "") or ""
        if not activity_type:
            activity_type = content_type
        # Prefer intent_ultrabert, fallback to intent_label
        intent_label = getattr(event, "intent_ultrabert", "") or ""
        if not intent_label:
            intent_label = getattr(event, "intent_label", "") or ""

        # --- 6 Additive Components ---
        emotional = self.compute_emotional_intensity(
            sentiment_score=sentiment_score,
            affect_valence=affect_valence,
            affect_arousal=affect_arousal,
            weights=weights,
        )

        surprise = self.compute_surprise_factor(
            surprise_level=surprise_level,
            weights=weights,
        )

        novelty = self.compute_novelty_factor(
            novelty_categorical=novelty_cat,
            salience_fallback=salience_score,
            weights=weights,
        )

        social = self.compute_social_factor(
            num_participants=num_participants,
            social_intimacy=social_intimacy,
            weights=weights,
        )

        identity = self.compute_identity_factor(
            identity_relevance=identity_relevance_val,
            identity_domains_json=identity_domains_json,
            weights=weights,
        )

        recency = self.compute_recency_factor(
            event_timestamp_ms=event_timestamp,
            now_ms=now_ms,
            weights=weights,
        )

        base = emotional + surprise + novelty + social + identity + recency

        # --- 7 Multiplicative Modulators ---
        elab = self.ELABORATION_MAP.get(elaboration_depth, 1.0)
        goal = self.GOAL_BOOST if narrative_is_goal else 1.0
        arc = self.ARC_MAP.get(narrative_arc, 1.0)
        temporal = self.TEMPORAL_MAP.get(temporal_orientation, 1.0)
        type_mult = self.EVENT_TYPE_MULTIPLIERS.get(activity_type.lower().strip(), 1.0)
        intent_boost_val = self.INTENT_BOOST_MULTIPLIERS.get(intent_label, 1.0)
        tier = self.MEMORY_TIER_MAP.get(memory_tier, 1.0)
        reliability_val = self.derive_source_reliability(
            source_reliability=source_reliability_val,
            source_type=source_type,
        )

        # Apply all modulators
        raw_score = (
            base
            * elab
            * goal
            * arc
            * temporal
            * type_mult
            * intent_boost_val
            * tier
            * reliability_val
        )
        final_score = max(0.0, min(1.0, raw_score))

        breakdown = ImportanceBreakdown(
            emotional_component=emotional,
            surprise_component=surprise,
            novelty_component=novelty,
            social_component=social,
            identity_component=identity,
            recency_component=recency,
            base_score=base,
            elab_boost=elab,
            goal_boost=goal,
            arc_boost=arc,
            temporal_boost=temporal,
            type_multiplier=type_mult,
            intent_boost=intent_boost_val,
            tier_multiplier=tier,
            reliability=reliability_val,
            final_score=final_score,
            weights_source=self._weights_source,
        )

        return final_score, breakdown

    async def score_batch(
        self,
        events: List[Any],
        now_ms: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Score all events in a batch and update P03EventState.

        This is the primary entry point for R1 phase integration.
        Each event's importance fields are updated in-place.

        Args:
            events: List of P03EventState objects
            now_ms: Current time in ms. If None, uses time.time().

        Returns:
            List of ScoredEvent-compatible dictionaries
        """
        import time as _time

        if now_ms is None:
            now_ms = int(_time.time() * 1000)

        weights = await self.get_weights()
        scored: List[Dict[str, Any]] = []

        for event in events:
            score, breakdown = self.compute_importance_score(event, weights, now_ms=now_ms)
            priority_tier = self.get_priority_tier(score)

            # Update event state in-place if method exists
            if hasattr(event, "set_importance"):
                event.set_importance(
                    score=score,
                    recency=breakdown.recency_component,
                    affect=breakdown.emotional_component,
                    social=breakdown.social_component,
                    novelty=breakdown.novelty_component,
                    surprise=breakdown.surprise_component,
                    identity=breakdown.identity_component,
                )

            scored.append(
                {
                    "event_id": getattr(event, "event_id", "unknown"),
                    "importance_score": score,
                    "recency_factor": breakdown.recency_component,
                    "affect_factor": breakdown.emotional_component,
                    "social_factor": breakdown.social_component,
                    "novelty_factor": breakdown.novelty_component,
                    "surprise_factor": breakdown.surprise_component,
                    "identity_factor": breakdown.identity_component,
                    "priority_tier": priority_tier,
                    "breakdown": breakdown,
                }
            )

        return scored

    def select_batch(
        self,
        scored_events: List[Any],
        batch_size: int,
    ) -> List[Any]:
        """
        Select top N events by importance for processing.

        Used to prioritize events when batch size is limited.

        Args:
            scored_events: List of scored events (dicts or objects)
            batch_size: Maximum number to select

        Returns:
            Top N events sorted by importance (descending)
        """

        # Handle both dict and object access
        def get_score(item: Any) -> float:
            if isinstance(item, dict):
                return item.get("importance_score", 0.0)
            return getattr(item, "importance_score", 0.0)

        return sorted(scored_events, key=get_score, reverse=True)[:batch_size]

    def get_priority_tier(self, score: float) -> str:
        """
        Map importance score to priority tier.

        6-tier system (POC Phase 6 validated, CONFIG_B):
            - 0.80-1.00: CRITICAL (process immediately)
            - 0.60-0.79: HIGH (process in current cycle)
            - 0.45-0.59: MEDIUM_HIGH (high-priority processing)
            - 0.30-0.44: MEDIUM (process if capacity allows)
            - 0.15-0.29: LOW_MEDIUM (low priority, may defer)
            - 0.00-0.14: LOW (defer or skip)

        Args:
            score: Importance score [0, 1]

        Returns:
            Priority tier string
        """
        if score >= 0.80:
            return "CRITICAL"
        elif score >= 0.60:
            return "HIGH"
        elif score >= 0.45:
            return "MEDIUM_HIGH"
        elif score >= 0.30:
            return "MEDIUM"
        elif score >= 0.15:
            return "LOW_MEDIUM"
        else:
            return "LOW"

    async def score_batch_with_audit(
        self,
        events: List[Any],
        audit_logger: Any,
        sample_rate: float = 1.0,
        now_ms: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Score all events with factor audit logging (Issue 4.1.2).

        This method extends score_batch() to log each scoring decision
        to st_consolidation_audit for explainability and feedback.

        Args:
            events: List of P03EventState objects
            audit_logger: P03AuditLogger instance for recording decisions
            sample_rate: Fraction of events to audit [0.0, 1.0].
                        Use 1.0 for debug (100%), 0.1 for production (10%).
            now_ms: Current time in ms. If None, uses time.time().

        Returns:
            List of ScoredEvent-compatible dictionaries
        """
        import random
        import time as _time

        if now_ms is None:
            now_ms = int(_time.time() * 1000)

        weights = await self.get_weights()
        scored: List[Dict[str, Any]] = []

        for event in events:
            score, breakdown = self.compute_importance_score(event, weights, now_ms=now_ms)
            priority_tier = self.get_priority_tier(score)

            # Update event state in-place if method exists
            if hasattr(event, "set_importance"):
                event.set_importance(
                    score=score,
                    recency=breakdown.recency_component,
                    affect=breakdown.emotional_component,
                    social=breakdown.social_component,
                    novelty=breakdown.novelty_component,
                    surprise=breakdown.surprise_component,
                    identity=breakdown.identity_component,
                )

            scored_event = {
                "event_id": getattr(event, "event_id", "unknown"),
                "importance_score": score,
                "recency_factor": breakdown.recency_component,
                "affect_factor": breakdown.emotional_component,
                "social_factor": breakdown.social_component,
                "novelty_factor": breakdown.novelty_component,
                "surprise_factor": breakdown.surprise_component,
                "identity_factor": breakdown.identity_component,
                "priority_tier": priority_tier,
                "breakdown": breakdown,
            }
            scored.append(scored_event)

            # Audit logging with sampling
            if random.random() < sample_rate:
                # Import AuditAction here to avoid circular import
                from k0.pipelines.p03.audit_logger import AuditAction

                audit_logger.log_decision(
                    memory_id=getattr(event, "event_id", "unknown"),
                    source_table="st_hipp_events",
                    action=AuditAction.SCORE,
                    formula_used="importance_scorer",
                    formula_version="2.0.0",
                    inputs={
                        "sentiment_score": getattr(event, "sentiment_score", 0.0),
                        "affect_valence": getattr(event, "affect_valence", 0.0),
                        "affect_arousal": getattr(event, "affect_arousal", 0.0),
                        "surprise_level": getattr(event, "surprise_level", 0.0),
                        "novelty": getattr(event, "novelty", ""),
                        "num_participants": getattr(event, "num_participants", 1),
                        "social_intimacy": getattr(event, "social_intimacy", ""),
                        "identity_relevance": getattr(event, "identity_relevance", 0.0),
                        "elaboration_depth": getattr(event, "elaboration_depth", ""),
                        "source_reliability": getattr(event, "source_reliability", 1.0),
                        "memory_tier": getattr(event, "memory_tier", "routine"),
                        "narrative_is_goal_event": getattr(event, "narrative_is_goal_event", False),
                        "narrative_arc_position": getattr(event, "narrative_arc_position", ""),
                        "temporal_orientation": getattr(event, "temporal_orientation", ""),
                        "content_type": getattr(event, "content_type", "message"),
                        "weights_source": self._weights_source,
                    },
                    outputs={
                        "importance_score": score,
                        "emotional_component": breakdown.emotional_component,
                        "surprise_component": breakdown.surprise_component,
                        "novelty_component": breakdown.novelty_component,
                        "social_component": breakdown.social_component,
                        "identity_component": breakdown.identity_component,
                        "recency_component": breakdown.recency_component,
                        "base_score": breakdown.base_score,
                        "elab_boost": breakdown.elab_boost,
                        "goal_boost": breakdown.goal_boost,
                        "arc_boost": breakdown.arc_boost,
                        "temporal_boost": breakdown.temporal_boost,
                        "type_multiplier": breakdown.type_multiplier,
                        "intent_boost": breakdown.intent_boost,
                        "tier_multiplier": breakdown.tier_multiplier,
                        "reliability": breakdown.reliability,
                        "priority_tier": priority_tier,
                    },
                    decision_id=getattr(audit_logger, "cycle_id", None),
                    confidence=score,
                    template_params={
                        "importance_score": score,
                        "priority_tier": priority_tier,
                        "emotional": breakdown.emotional_component,
                        "surprise": breakdown.surprise_component,
                        "novelty": breakdown.novelty_component,
                        "social": breakdown.social_component,
                        "identity": breakdown.identity_component,
                        "recency": breakdown.recency_component,
                        "base_score": breakdown.base_score,
                        "type_multiplier": breakdown.type_multiplier,
                        "weights_source": self._weights_source,
                    },
                )

        return scored
