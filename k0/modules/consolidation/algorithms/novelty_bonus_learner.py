"""
AdaptiveNoveltyBonusLearner — Learn per-space novelty bonus values from feedback.

Adapts novelty bonuses based on actual user behavior, distinguishing between
users who value novelty highly (explorers) versus those who prefer familiar
patterns (conservatives).

Scientific Basis:
- Incremental learning from feedback signals
- Per-space personalization
- Bounded adjustments to prevent extreme values

Spec Reference:
- Dossier §4.4.2.1: Adaptive Novelty Bonuses
- M4_EXECUTION.md Issue 4.3.8
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Protocol, runtime_checkable

# =============================================================================
# Constants
# =============================================================================

# Default bonus values (from Dossier §4.4.2.1)
DEFAULT_FIRST_OCCURRENCE_BONUS = 0.15
DEFAULT_MILESTONE_BONUS = 0.20
DEFAULT_RARE_PATTERN_BONUS = 0.10
DEFAULT_TEMPORAL_ANOMALY_BONUS = 0.10

# Bonus bounds (from Dossier §4.4.2.1)
BONUS_MIN = 0.05
BONUS_MAX = 0.30

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class NoveltyBonusType(Enum):
    """Types of novelty bonuses that can be learned."""

    FIRST_OCCURRENCE = "first_occurrence"
    MILESTONE = "milestone"
    RARE_PATTERN = "rare_pattern"
    TEMPORAL_ANOMALY = "temporal_anomaly"


class NoveltyFeedbackSignal(Enum):
    """Feedback signals that affect novelty bonuses."""

    NOVEL_EVENT_GROUNDED = "NOVEL_EVENT_GROUNDED"
    NOVEL_EVENT_NEVER_QUERIED = "NOVEL_EVENT_NEVER_QUERIED"
    USER_SAYS_NOT_NEW = "USER_SAYS_NOT_NEW"
    MILESTONE_GROUNDED = "MILESTONE_GROUNDED"
    RARE_PATTERN_USEFUL = "RARE_PATTERN_USEFUL"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class BonusAdjustment:
    """
    Result from bonus adjustment.

    Attributes:
        bonus_type: Type of bonus adjusted
        old_value: Value before adjustment
        new_value: Value after adjustment
        adjustment: Amount of adjustment applied
        signal_type: Signal that triggered adjustment
        clamped: True if result was clamped to bounds
    """

    bonus_type: NoveltyBonusType
    old_value: float
    new_value: float
    adjustment: float
    signal_type: str
    clamped: bool


@dataclass
class NoveltyBonusConfig:
    """
    Configuration for novelty bonus learning.

    Attributes:
        bonus_min: Minimum bonus value (floor)
        bonus_max: Maximum bonus value (ceiling)
        defaults: Default values for each bonus type
        adjustments: Adjustment amounts for each signal type
    """

    bonus_min: float = BONUS_MIN
    bonus_max: float = BONUS_MAX
    defaults: Optional[Dict[NoveltyBonusType, float]] = None
    adjustments: Optional[Dict[NoveltyFeedbackSignal, float]] = None

    def __post_init__(self) -> None:
        """Set defaults if not provided."""
        if self.defaults is None:
            self.defaults = {
                NoveltyBonusType.FIRST_OCCURRENCE: DEFAULT_FIRST_OCCURRENCE_BONUS,
                NoveltyBonusType.MILESTONE: DEFAULT_MILESTONE_BONUS,
                NoveltyBonusType.RARE_PATTERN: DEFAULT_RARE_PATTERN_BONUS,
                NoveltyBonusType.TEMPORAL_ANOMALY: DEFAULT_TEMPORAL_ANOMALY_BONUS,
            }
        if self.adjustments is None:
            self.adjustments = {
                NoveltyFeedbackSignal.NOVEL_EVENT_GROUNDED: +0.01,
                NoveltyFeedbackSignal.NOVEL_EVENT_NEVER_QUERIED: -0.02,
                NoveltyFeedbackSignal.USER_SAYS_NOT_NEW: -0.03,
                NoveltyFeedbackSignal.MILESTONE_GROUNDED: +0.01,
                NoveltyFeedbackSignal.RARE_PATTERN_USEFUL: +0.01,
            }

    def validate(self) -> None:
        """Validate configuration."""
        if self.bonus_min < 0:
            raise ValueError("bonus_min must be >= 0")
        if self.bonus_max <= self.bonus_min:
            raise ValueError("bonus_max must be > bonus_min")
        if self.defaults is None:
            raise ValueError("defaults cannot be None after init")
        if self.adjustments is None:
            raise ValueError("adjustments cannot be None after init")


# =============================================================================
# Storage Protocol
# =============================================================================


@runtime_checkable
class LearnedWeightsStoreProtocol(Protocol):
    """Protocol for learned weights storage operations."""

    async def get_weight(self, param_key: str, space_id: str) -> Optional[float]:
        """Get current weight value."""
        ...

    async def upsert_weight(
        self, param_key: str, space_id: str, value: float, prior_value: float
    ) -> None:
        """Upsert weight value."""
        ...


class InMemoryLearnedWeightsStore:
    """
    In-memory implementation for testing.

    Not for production use.
    """

    def __init__(self) -> None:
        self._weights: Dict[str, Dict[str, float]] = {}  # space_id -> param_key -> value
        self._sample_counts: Dict[str, Dict[str, int]] = {}

    async def get_weight(self, param_key: str, space_id: str) -> Optional[float]:
        """Get current weight value."""
        space_weights = self._weights.get(space_id, {})
        return space_weights.get(param_key)

    async def upsert_weight(
        self, param_key: str, space_id: str, value: float, prior_value: float  # noqa: ARG002
    ) -> None:
        """Upsert weight value."""
        if space_id not in self._weights:
            self._weights[space_id] = {}
            self._sample_counts[space_id] = {}
        self._weights[space_id][param_key] = value
        current_count = self._sample_counts[space_id].get(param_key, 0)
        self._sample_counts[space_id][param_key] = current_count + 1

    def get_sample_count(self, param_key: str, space_id: str) -> int:
        """Get sample count for testing."""
        return self._sample_counts.get(space_id, {}).get(param_key, 0)


# =============================================================================
# Signal to Bonus Mapping
# =============================================================================

# Which signal affects which bonus type
SIGNAL_TO_BONUS: Dict[NoveltyFeedbackSignal, NoveltyBonusType] = {
    NoveltyFeedbackSignal.NOVEL_EVENT_GROUNDED: NoveltyBonusType.FIRST_OCCURRENCE,
    NoveltyFeedbackSignal.NOVEL_EVENT_NEVER_QUERIED: NoveltyBonusType.FIRST_OCCURRENCE,
    NoveltyFeedbackSignal.USER_SAYS_NOT_NEW: NoveltyBonusType.FIRST_OCCURRENCE,
    NoveltyFeedbackSignal.MILESTONE_GROUNDED: NoveltyBonusType.MILESTONE,
    NoveltyFeedbackSignal.RARE_PATTERN_USEFUL: NoveltyBonusType.RARE_PATTERN,
}


# =============================================================================
# AdaptiveNoveltyBonusLearner
# =============================================================================


class AdaptiveNoveltyBonusLearner:
    """
    Learn per-space novelty bonus values from feedback.

    Stores learned bonuses in st_learned_weights with:
    - param_key = 'novelty_bonus_{bonus_type}'
    - param_scope = 'space'
    - scope_id = space_id

    Spec: Dossier §4.4.2.1
    """

    def __init__(self, config: Optional[NoveltyBonusConfig] = None) -> None:
        self._config = config or NoveltyBonusConfig()
        self._config.validate()

    @property
    def config(self) -> NoveltyBonusConfig:
        """Get current configuration."""
        return self._config

    def adjust_bonus(
        self,
        bonus_type: NoveltyBonusType,
        feedback_signal: NoveltyFeedbackSignal,
        current_bonus: float,
    ) -> BonusAdjustment:
        """
        Adjust novelty bonus based on feedback signal.

        Algorithm (from Dossier §4.4.2.1):
        1. Look up adjustment amount for signal
        2. Add adjustment to current bonus
        3. Clamp to [0.05, 0.30] range
        4. Return adjustment result

        Args:
            bonus_type: Type of bonus being adjusted
            feedback_signal: Signal triggering the adjustment
            current_bonus: Current bonus value

        Returns:
            BonusAdjustment with old/new values and metadata
        """
        assert self._config.adjustments is not None  # noqa: S101
        adjustment = self._config.adjustments.get(feedback_signal, 0.0)
        new_bonus = current_bonus + adjustment

        # Clamp to bounds
        clamped = False
        if new_bonus < self._config.bonus_min:
            new_bonus = self._config.bonus_min
            clamped = True
        elif new_bonus > self._config.bonus_max:
            new_bonus = self._config.bonus_max
            clamped = True

        return BonusAdjustment(
            bonus_type=bonus_type,
            old_value=current_bonus,
            new_value=new_bonus,
            adjustment=adjustment,
            signal_type=feedback_signal.value,
            clamped=clamped,
        )

    async def process_feedback_signal(
        self,
        signal_type: str,
        space_id: str,
        store: LearnedWeightsStoreProtocol,
    ) -> Optional[BonusAdjustment]:
        """
        Process a feedback signal and update learned bonus.

        Steps:
        1. Map signal to bonus type
        2. Fetch current bonus from store (or use default)
        3. Compute adjustment
        4. Persist updated bonus

        Args:
            signal_type: Signal type string
            space_id: Space ID for personalization
            store: Storage implementation

        Returns:
            BonusAdjustment if processed, None if unknown signal
        """
        # Parse signal type
        try:
            feedback_signal = NoveltyFeedbackSignal(signal_type)
        except ValueError:
            logger.warning(
                "Unknown novelty feedback signal",
                extra={"signal_type": signal_type},
            )
            return None

        # Map to bonus type
        bonus_type = SIGNAL_TO_BONUS.get(feedback_signal)
        if not bonus_type:
            logger.warning(
                "No bonus mapping for signal",
                extra={"signal_type": signal_type},
            )
            return None

        # Get current value
        current = await self._get_current_bonus(bonus_type, space_id, store)

        # Compute adjustment
        result = self.adjust_bonus(bonus_type, feedback_signal, current)

        # Persist if changed
        if result.new_value != result.old_value:
            await self._persist_bonus(bonus_type, space_id, result.new_value, store)

        logger.info(
            "Processed novelty feedback",
            extra={
                "signal_type": signal_type,
                "bonus_type": bonus_type.value,
                "old_value": result.old_value,
                "new_value": result.new_value,
                "adjustment": result.adjustment,
                "clamped": result.clamped,
                "space_id": space_id,
            },
        )

        return result

    async def _get_current_bonus(
        self,
        bonus_type: NoveltyBonusType,
        space_id: str,
        store: LearnedWeightsStoreProtocol,
    ) -> float:
        """Fetch current bonus from store or return default."""
        param_key = f"novelty_bonus_{bonus_type.value}"
        stored = await store.get_weight(param_key, space_id)
        if stored is not None:
            return stored
        assert self._config.defaults is not None  # noqa: S101
        return self._config.defaults.get(bonus_type, 0.15)

    async def _persist_bonus(
        self,
        bonus_type: NoveltyBonusType,
        space_id: str,
        new_value: float,
        store: LearnedWeightsStoreProtocol,
    ) -> None:
        """Persist bonus value to store."""
        param_key = f"novelty_bonus_{bonus_type.value}"
        assert self._config.defaults is not None  # noqa: S101
        prior_value = self._config.defaults.get(bonus_type, 0.15)
        await store.upsert_weight(param_key, space_id, new_value, prior_value)

    async def get_all_bonuses(
        self,
        space_id: str,
        store: LearnedWeightsStoreProtocol,
    ) -> Dict[NoveltyBonusType, float]:
        """
        Get all bonus values for a space (with defaults for missing).

        Used by DuplicateDetector to initialize with learned values.

        Args:
            space_id: Space ID
            store: Storage implementation

        Returns:
            Dict mapping bonus type to value
        """
        result = {}
        for bonus_type in NoveltyBonusType:
            result[bonus_type] = await self._get_current_bonus(bonus_type, space_id, store)
        return result

    async def get_bonuses_as_dict(
        self,
        space_id: str,
        store: LearnedWeightsStoreProtocol,
    ) -> Dict[str, float]:
        """
        Get all bonus values as string-keyed dict.

        Convenient for DuplicateDetectorConfig.from_learned_bonuses().

        Args:
            space_id: Space ID
            store: Storage implementation

        Returns:
            Dict mapping bonus name string to value
        """
        typed = await self.get_all_bonuses(space_id, store)
        return {k.value: v for k, v in typed.items()}


# =============================================================================
# Utility Functions
# =============================================================================


def clamp_bonus(value: float, min_val: float = BONUS_MIN, max_val: float = BONUS_MAX) -> float:
    """Clamp bonus value to valid range."""
    return max(min_val, min(max_val, value))


def get_default_bonus(bonus_type: NoveltyBonusType) -> float:
    """Get default bonus value for type."""
    defaults = {
        NoveltyBonusType.FIRST_OCCURRENCE: DEFAULT_FIRST_OCCURRENCE_BONUS,
        NoveltyBonusType.MILESTONE: DEFAULT_MILESTONE_BONUS,
        NoveltyBonusType.RARE_PATTERN: DEFAULT_RARE_PATTERN_BONUS,
        NoveltyBonusType.TEMPORAL_ANOMALY: DEFAULT_TEMPORAL_ANOMALY_BONUS,
    }
    return defaults.get(bonus_type, 0.15)
