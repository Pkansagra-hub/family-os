"""
ImportanceScorer - Compute importance scores for hippocampal event selection.

This module implements the importance scoring algorithm that determines which
events should be prioritized for memory consolidation. Based on cognitive
neuroscience principles (McGaugh, 2004) showing emotional memories are more
strongly encoded due to amygdala-hippocampus interaction.

Spec Reference:
    - Dossier §2.4: Scientific Formulas - Importance Score
    - Dossier Appendix C.2.1: Algorithm Specification
    - M4_EXECUTION.md Issue 4.1.1

Formula:
    importance = (emotional + novelty + social) × event_type_multiplier

Where:
    - emotional = sentiment_weight × |sentiment| + affect_weight × |affect|
    - novelty = novelty_weight × novelty_score
    - social = social_weight × log2(participants) / 3.32

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

    Default values from Dossier C.2.1:
        - sentiment: 0.25 (sentiment analysis contribution)
        - affect: 0.30 (emotional valence/arousal contribution)
        - novelty: 0.25 (information novelty contribution)
        - social: 0.20 (social context contribution)
    """

    sentiment_weight: float = 0.25
    affect_weight: float = 0.30
    novelty_weight: float = 0.25
    social_weight: float = 0.20

    def total(self) -> float:
        """Sum of all weights (should be 1.0 for normalization)."""
        return self.sentiment_weight + self.affect_weight + self.novelty_weight + self.social_weight

    def as_dict(self) -> Dict[str, float]:
        """Return weights as dictionary for serialization."""
        return {
            "sentiment": self.sentiment_weight,
            "affect": self.affect_weight,
            "novelty": self.novelty_weight,
            "social": self.social_weight,
        }


@dataclass
class ImportanceBreakdown:
    """
    Component breakdown of importance score for audit logging.

    This provides transparency into how the final score was computed,
    enabling debugging and learning feedback loops.
    """

    emotional_component: float  # Combined sentiment + affect contribution
    novelty_component: float  # Novelty contribution
    social_component: float  # Social relevance contribution
    multiplier: float  # Event type multiplier applied
    final_score: float  # Final normalized score [0, 1]
    weights_source: str = "static"  # "static" or "learned"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for audit logging outputs."""
        return {
            "emotional_component": self.emotional_component,
            "novelty_component": self.novelty_component,
            "social_component": self.social_component,
            "multiplier": self.multiplier,
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

    Scoring Formula:
        importance = (emotional + novelty + social) × multiplier

        Where:
        - emotional = sentiment_weight × |sentiment| + affect_weight × |affect|
        - novelty = novelty_weight × novelty_score
        - social = social_weight × log2(participants) / 3.32

    Weight Learning:
        Initially uses static weights. After 500+ samples with outcome
        feedback, switches to learned weights from st_learned_weights.

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
                    self._cached_weights = ImportanceWeights(
                        sentiment_weight=learned.weights.get("sentiment", 0.25),
                        affect_weight=learned.weights.get("affect", 0.30),
                        novelty_weight=learned.weights.get("novelty", 0.25),
                        social_weight=learned.weights.get("social", 0.20),
                    )
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
                        self._cached_weights = ImportanceWeights(
                            sentiment_weight=space_weights.weights.get("sentiment", 0.25),
                            affect_weight=space_weights.weights.get("affect", 0.30),
                            novelty_weight=space_weights.weights.get("novelty", 0.25),
                            social_weight=space_weights.weights.get("social", 0.20),
                        )
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
                        self._cached_weights = ImportanceWeights(
                            sentiment_weight=blended.get("sentiment", 0.25),
                            affect_weight=blended.get("affect", 0.30),
                            novelty_weight=blended.get("novelty", 0.25),
                            social_weight=blended.get("social", 0.20),
                        )
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
                        self._cached_weights = ImportanceWeights(
                            sentiment_weight=global_weights.weights.get("sentiment", 0.25),
                            affect_weight=global_weights.weights.get("affect", 0.30),
                            novelty_weight=global_weights.weights.get("novelty", 0.25),
                            social_weight=global_weights.weights.get("social", 0.20),
                        )
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
                        self._cached_weights = ImportanceWeights(
                            sentiment_weight=blended.get("sentiment", 0.25),
                            affect_weight=blended.get("affect", 0.30),
                            novelty_weight=blended.get("novelty", 0.25),
                            social_weight=blended.get("social", 0.20),
                        )
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
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute emotional intensity from sentiment and affect.

        Uses absolute values because both strong positive AND strong
        negative emotions enhance memory encoding (McGaugh, 2004).

        Args:
            sentiment_score: Sentiment analysis score [-1, 1]
            affect_valence: Emotional valence [-1, 1]
            weights: Weight configuration

        Returns:
            Emotional intensity component [0, ~0.55] (unclamped)
        """
        sentiment_intensity = abs(sentiment_score)
        affect_intensity = abs(affect_valence)

        return (
            sentiment_intensity * weights.sentiment_weight
            + affect_intensity * weights.affect_weight
        )

    def compute_social_factor(
        self,
        participant_count: int,
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute social factor from participant count.

        Uses logarithmic scaling to prevent large groups from
        completely dominating importance scores.

        Scale interpretation:
            - 1 person: 0.0 (solo event, no social bonus)
            - 2 people: ~0.30 × weight
            - 5 people: ~0.70 × weight
            - 10+ people: ~1.0 × weight (capped)

        Args:
            participant_count: Number of participants in event
            weights: Weight configuration

        Returns:
            Social factor component [0, social_weight]
        """
        if participant_count <= 1:
            return 0.0  # Solo event, no social bonus

        # Log scale: log2(count) / log2(10)
        log_factor = min(1.0, math.log2(participant_count) / self.LOG2_10)
        return log_factor * weights.social_weight

    def compute_novelty_factor(
        self,
        novelty_score: float,
        weights: ImportanceWeights,
    ) -> float:
        """
        Compute novelty factor from novelty score.

        Novelty score represents how different this event is from
        existing memory clusters (computed from embedding distances).

        Args:
            novelty_score: Pre-computed novelty score [0, 1]
            weights: Weight configuration

        Returns:
            Novelty factor component [0, novelty_weight]
        """
        # Clamp input to valid range
        clamped_novelty = max(0.0, min(1.0, novelty_score))
        return clamped_novelty * weights.novelty_weight

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
    ) -> Tuple[float, ImportanceBreakdown]:
        """
        Compute importance score for a single event.

        Formula:
            importance = (emotional + novelty + social) × multiplier

        All component scores are computed using the configured weights,
        then multiplied by the event type multiplier. Final score is
        clamped to [0.0, 1.0].

        Args:
            event: P03EventState or object with required attributes
            weights: Weight configuration to use

        Returns:
            Tuple of (score, breakdown) where:
                - score: Final importance [0.0, 1.0]
                - breakdown: Component values for audit
        """
        # Extract event attributes with safe defaults
        sentiment_score = getattr(event, "sentiment_score", 0.0) or 0.0
        affect_valence = getattr(event, "affect_valence", 0.0) or 0.0
        # Issue 1 Fix: Use P02's salience_score as novelty proxy
        # salience_score = 0.50×social + 0.40×affect + 0.10×recency
        # This captures "interestingness" which novelty was meant to represent
        # novelty_score doesn't exist - it was meant to be computed by R3 (runs AFTER R1)
        novelty_score = getattr(event, "salience_score", 0.0) or 0.0
        participant_count = getattr(event, "participant_count", 1) or 1
        content_type = getattr(event, "content_type", "message") or "message"

        # Compute each component
        emotional = self.compute_emotional_intensity(
            sentiment_score=sentiment_score,
            affect_valence=affect_valence,
            weights=weights,
        )

        novelty = self.compute_novelty_factor(
            novelty_score=novelty_score,
            weights=weights,
        )

        social = self.compute_social_factor(
            participant_count=participant_count,
            weights=weights,
        )

        # Sum components for base importance
        base_importance = emotional + novelty + social

        # Apply event type multiplier
        multiplier = self.get_event_type_multiplier(content_type)
        raw_score = base_importance * multiplier

        # Apply intent-based boost (GAP-001 M8 Issue 8.2)
        # UltraBERT intent types modulate salience based on cognitive significance
        intent_label = getattr(event, "intent_label", "") or ""
        intent_boost = self.INTENT_BOOST_MULTIPLIERS.get(intent_label, 1.0)
        if intent_boost != 1.0:
            raw_score *= intent_boost
            # Combine multipliers for breakdown tracking
            multiplier *= intent_boost

        # Clamp to [0.0, 1.0]
        final_score = max(0.0, min(1.0, raw_score))

        breakdown = ImportanceBreakdown(
            emotional_component=emotional,
            novelty_component=novelty,
            social_component=social,
            multiplier=multiplier,
            final_score=final_score,
            weights_source=self._weights_source,
        )

        return final_score, breakdown

    async def score_batch(
        self,
        events: List[Any],
    ) -> List[Dict[str, Any]]:
        """
        Score all events in a batch and update P03EventState.

        This is the primary entry point for R1 phase integration.
        Each event's importance fields are updated in-place.

        Args:
            events: List of P03EventState objects

        Returns:
            List of ScoredEvent-compatible dictionaries
        """
        weights = await self.get_weights()
        scored: List[Dict[str, Any]] = []

        for event in events:
            score, breakdown = self.compute_importance_score(event, weights)

            # Update event state in-place if method exists
            if hasattr(event, "set_importance"):
                event.set_importance(
                    score=score,
                    recency=0.0,  # Reserved for future recency decay
                    affect=breakdown.emotional_component,
                    social=breakdown.social_component,
                    novelty=breakdown.novelty_component,
                )

            scored.append(
                {
                    "event_id": getattr(event, "event_id", "unknown"),
                    "importance_score": score,
                    "recency_factor": 0.0,
                    "affect_factor": breakdown.emotional_component,
                    "social_factor": breakdown.social_component,
                    "novelty_factor": breakdown.novelty_component,
                    "breakdown": breakdown,  # For audit logging
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

        Thresholds from Dossier C.2.1:
            - 0.80-1.00: CRITICAL (process immediately)
            - 0.50-0.79: HIGH (process in current cycle)
            - 0.30-0.49: MEDIUM (process if capacity allows)
            - 0.00-0.29: LOW (may be deferred)

        Args:
            score: Importance score [0, 1]

        Returns:
            Priority tier string
        """
        if score >= 0.80:
            return "CRITICAL"
        elif score >= 0.50:
            return "HIGH"
        elif score >= 0.30:
            return "MEDIUM"
        else:
            return "LOW"

    async def score_batch_with_audit(
        self,
        events: List[Any],
        audit_logger: Any,
        sample_rate: float = 1.0,
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

        Returns:
            List of ScoredEvent-compatible dictionaries

        Audit Record Fields:
            - action: AuditAction.SCORE
            - formula_used: "importance_scorer"
            - formula_version: "1.0.0"
            - inputs: sentiment_score, affect_valence, novelty_score,
                     participant_count, content_type, weights_source
            - outputs: importance_score, emotional_component, novelty_component,
                      social_component, multiplier
            - confidence: importance_score value
        """
        import random

        weights = await self.get_weights()
        scored: List[Dict[str, Any]] = []

        for event in events:
            score, breakdown = self.compute_importance_score(event, weights)

            # Update event state in-place if method exists
            if hasattr(event, "set_importance"):
                event.set_importance(
                    score=score,
                    recency=0.0,  # Reserved for future recency decay
                    affect=breakdown.emotional_component,
                    social=breakdown.social_component,
                    novelty=breakdown.novelty_component,
                )

            scored_event = {
                "event_id": getattr(event, "event_id", "unknown"),
                "importance_score": score,
                "recency_factor": 0.0,
                "affect_factor": breakdown.emotional_component,
                "social_factor": breakdown.social_component,
                "novelty_factor": breakdown.novelty_component,
                "breakdown": breakdown,
            }
            scored.append(scored_event)

            # Audit logging with sampling
            if random.random() < sample_rate:
                # Import AuditAction here to avoid circular import
                from k0.pipelines.p03.audit_logger import AuditAction

                priority_tier = self.get_priority_tier(score)

                audit_logger.log_decision(
                    memory_id=getattr(event, "event_id", "unknown"),
                    source_table="st_hipp_events",
                    action=AuditAction.SCORE,
                    formula_used="importance_scorer",
                    formula_version="1.0.0",
                    inputs={
                        "sentiment_score": getattr(event, "sentiment_score", 0.0),
                        "affect_valence": getattr(event, "affect_valence", 0.0),
                        "novelty_score": getattr(event, "novelty_score", 0.0),
                        "participant_count": getattr(event, "participant_count", 1),
                        "content_type": getattr(event, "content_type", "message"),
                        "weights_source": self._weights_source,
                    },
                    outputs={
                        "importance_score": score,
                        "emotional_component": breakdown.emotional_component,
                        "novelty_component": breakdown.novelty_component,
                        "social_component": breakdown.social_component,
                        "multiplier": breakdown.multiplier,
                        "priority_tier": priority_tier,
                    },
                    decision_id=getattr(audit_logger, "cycle_id", None),
                    confidence=score,
                    template_params={
                        "importance_score": score,
                        "priority_tier": priority_tier,
                        "emotional": breakdown.emotional_component,
                        "novelty": breakdown.novelty_component,
                        "social": breakdown.social_component,
                        "multiplier": breakdown.multiplier,
                        "weights_source": self._weights_source,
                    },
                )

        return scored
