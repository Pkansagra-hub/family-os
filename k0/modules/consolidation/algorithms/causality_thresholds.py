"""
AdaptiveCausalityThresholds - Per-category thresholds for causal inference.

This module implements adaptive causality thresholds based on decision stakes:
- Health/Medical: High stakes, require strong evidence (0.85)
- Financial: Important but reversible, moderate evidence (0.80)
- Social/Routine: Lower stakes, relationship patterns (0.70)
- Preference/Habit: Personal patterns, flexible (0.65)

Spec Reference:
    - Dossier §4.5.4.1: Adaptive Causality Thresholds
    - M4_EXECUTION.md Issue 4.4.10

Human Memory Model:
    We're more cautious about medical causation ("Does X cause my symptoms?")
    than social patterns ("Do I usually call Mom on Sundays?").
    Stakes vary by domain.

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


class CausalityCategory(Enum):
    """Categories for causality threshold lookup."""

    HEALTH_MEDICAL = "Health/Medical"
    FINANCIAL = "Financial"
    SOCIAL_ROUTINE = "Social/Routine"
    PREFERENCE_HABIT = "Preference/Habit"


@dataclass(frozen=True)
class CategoryThresholdBounds:
    """
    Threshold bounds for a causality category.

    Attributes:
        default: Default threshold value
        min_value: Minimum allowed threshold (looser)
        max_value: Maximum allowed threshold (stricter)
    """

    default: float
    min_value: float
    max_value: float

    def validate(self) -> None:
        """Validate bounds are consistent."""
        if not 0.0 < self.min_value < self.max_value <= 1.0:
            raise ValueError(f"Invalid bounds: min={self.min_value}, max={self.max_value}")
        if not self.min_value <= self.default <= self.max_value:
            raise ValueError(f"Default {self.default} not in [{self.min_value}, {self.max_value}]")


# =============================================================================
# Category Keywords
# =============================================================================


# Category keyword sets for classification (from Dossier §4.5.4.1)
CATEGORY_KEYWORDS: Dict[CausalityCategory, Set[str]] = {
    CausalityCategory.HEALTH_MEDICAL: {
        "medication",
        "symptom",
        "treatment",
        "doctor",
        "health",
        "pain",
        "illness",
        "diagnosis",
        "therapy",
        "exercise",
        "hospital",
        "medicine",
        "prescription",
        "allergy",
        "condition",
        "sick",
        "medical",
        "nurse",
        "clinic",
        "pharmacy",
    },
    CausalityCategory.FINANCIAL: {
        "money",
        "budget",
        "spending",
        "purchase",
        "cost",
        "expense",
        "payment",
        "transaction",
        "bill",
        "salary",
        "bank",
        "investment",
        "loan",
        "credit",
        "income",
        "tax",
        "savings",
        "debt",
        "price",
        "financial",
    },
    CausalityCategory.SOCIAL_ROUTINE: {
        "call",
        "visit",
        "meeting",
        "conversation",
        "message",
        "friend",
        "family",
        "colleague",
        "social",
        "gathering",
        "party",
        "dinner",
        "lunch",
        "appointment",
        "schedule",
        "mom",
        "dad",
        "parent",
        "child",
        "spouse",
    },
}


# =============================================================================
# Utility Functions
# =============================================================================


def now_ms() -> int:
    """Current time in milliseconds since Unix epoch."""
    return int(time.time() * 1000)


def generate_ulid() -> str:
    """Generate a ULID for new records."""
    import secrets

    timestamp_ms = now_ms()
    time_bytes = timestamp_ms.to_bytes(6, byteorder="big")
    random_bytes = secrets.token_bytes(10)
    ulid_bytes = time_bytes + random_bytes

    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    result = []
    value = int.from_bytes(ulid_bytes, byteorder="big")

    for _ in range(26):
        result.append(alphabet[value & 31])
        value >>= 5

    return "".join(reversed(result))


# =============================================================================
# CausalCategoryClassifier
# =============================================================================


class CausalCategoryClassifier:
    """
    Classify relationship into causality category.

    Spec: Dossier §4.5.4.1

    Uses keyword matching on entity names and relationship type
    to determine which category (and thus threshold) applies.
    """

    def classify(
        self,
        source_entity_name: str,
        target_entity_name: str,
        relationship_type: str = "causal",
    ) -> CausalityCategory:
        """
        Determine causality category for relationship.

        Checks categories in priority order (highest stakes first):
        1. Health/Medical - highest stakes
        2. Financial - high stakes
        3. Social/Routine - moderate stakes
        4. Preference/Habit - lowest stakes (default)

        Args:
            source_entity_name: Name of source entity
            target_entity_name: Name of target entity
            relationship_type: Type of relationship

        Returns:
            CausalityCategory enum value
        """
        # Combine text for keyword matching
        text = f"{source_entity_name} {target_entity_name} {relationship_type}".lower()

        # Check categories in priority order (highest stakes first)
        if any(kw in text for kw in CATEGORY_KEYWORDS[CausalityCategory.HEALTH_MEDICAL]):
            return CausalityCategory.HEALTH_MEDICAL

        if any(kw in text for kw in CATEGORY_KEYWORDS[CausalityCategory.FINANCIAL]):
            return CausalityCategory.FINANCIAL

        if any(kw in text for kw in CATEGORY_KEYWORDS[CausalityCategory.SOCIAL_ROUTINE]):
            return CausalityCategory.SOCIAL_ROUTINE

        # Default: personal preference/habit patterns
        return CausalityCategory.PREFERENCE_HABIT


# =============================================================================
# AdaptiveCausalityThresholds
# =============================================================================


class AdaptiveCausalityThresholds:
    """
    Per-category causality thresholds with learning.

    Spec: Dossier §4.5.4.1

    Features:
    - Per-category default thresholds based on decision stakes
    - Learning from prediction outcomes (feedback-driven adjustment)
    - Bounded adjustment range per category
    - Persistence to st_learned_weights

    Default Thresholds (from Dossier):
    - Health/Medical: 0.85 (high stakes, strong evidence required)
    - Financial: 0.80 (important but reversible)
    - Social/Routine: 0.70 (lower stakes)
    - Preference/Habit: 0.65 (personal, flexible)
    """

    # Default thresholds by category (from Dossier §4.5.4.1)
    DEFAULT_THRESHOLDS: Dict[CausalityCategory, CategoryThresholdBounds] = {
        CausalityCategory.HEALTH_MEDICAL: CategoryThresholdBounds(0.85, 0.80, 0.95),
        CausalityCategory.FINANCIAL: CategoryThresholdBounds(0.80, 0.75, 0.90),
        CausalityCategory.SOCIAL_ROUTINE: CategoryThresholdBounds(0.70, 0.60, 0.80),
        CausalityCategory.PREFERENCE_HABIT: CategoryThresholdBounds(0.65, 0.55, 0.75),
    }

    # Learning adjustments by feedback signal (from Dossier §4.5.4.1)
    LEARNING_ADJUSTMENTS: Dict[str, float] = {
        "CAUSAL_PREDICTION_CONFIRMED": 0.0,  # Correct, no change
        "CAUSAL_PREDICTION_WRONG": +0.02,  # FP: stricter
        "USER_REJECTS_CAUSATION": +0.05,  # Strong FP: much stricter
        "MISSED_CAUSATION": -0.03,  # FN: looser
    }

    def __init__(
        self,
        classifier: Optional[CausalCategoryClassifier] = None,
        learned_thresholds: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize adaptive thresholds.

        Args:
            classifier: Category classifier instance
            learned_thresholds: Pre-loaded learned thresholds (key → value)
        """
        self.classifier = classifier or CausalCategoryClassifier()
        self._learned: Dict[str, float] = learned_thresholds or {}

    def get_threshold(self, category: CausalityCategory) -> float:
        """
        Get current threshold for category.

        Checks learned overrides first, falls back to default.

        Args:
            category: CausalityCategory to look up

        Returns:
            Current threshold value
        """
        key = self._threshold_key(category)
        if key in self._learned:
            return self._learned[key]
        return self.DEFAULT_THRESHOLDS[category].default

    def get_bounds(self, category: CausalityCategory) -> CategoryThresholdBounds:
        """Get bounds for a category."""
        return self.DEFAULT_THRESHOLDS[category]

    def should_create_causal_edge(
        self,
        source_entity_name: str,
        target_entity_name: str,
        precedence_ratio: float,
        observation_count: int = 0,
    ) -> Tuple[bool, float, CausalityCategory]:
        """
        Determine if causal edge should be created.

        Classifies the relationship into a category, applies the
        category-specific threshold, and computes confidence.

        Args:
            source_entity_name: Name of source entity
            target_entity_name: Name of target entity
            precedence_ratio: Temporal precedence ratio [0, 1]
            observation_count: Number of observations (unused, for future)

        Returns:
            Tuple of (should_create, confidence, category)
        """
        # Classify relationship category
        category = self.classifier.classify(
            source_entity_name,
            target_entity_name,
            relationship_type="causal",
        )

        # Get learned threshold for category
        threshold = self.get_threshold(category)

        # Check if precedence ratio exceeds threshold
        if precedence_ratio >= threshold:
            # Compute confidence based on margin above threshold
            margin = precedence_ratio - threshold
            confidence = min(1.0, 0.70 + (margin * 2.0))
            logger.debug(
                f"Causal edge approved: {source_entity_name} → {target_entity_name} "
                f"({category.value}, ratio={precedence_ratio:.2f} >= {threshold:.2f})"
            )
            return (True, confidence, category)
        else:
            logger.debug(
                f"Causal edge rejected: {source_entity_name} → {target_entity_name} "
                f"({category.value}, ratio={precedence_ratio:.2f} < {threshold:.2f})"
            )
            return (False, 0.0, category)

    def adjust_threshold(
        self,
        category: CausalityCategory,
        feedback_signal: str,
    ) -> float:
        """
        Adjust threshold based on feedback.

        Applies learning adjustment and clamps to category bounds.

        Args:
            category: Category to adjust
            feedback_signal: Feedback signal type

        Returns:
            New threshold value (clamped to bounds)
        """
        current = self.get_threshold(category)
        bounds = self.DEFAULT_THRESHOLDS[category]

        adjustment = self.LEARNING_ADJUSTMENTS.get(feedback_signal, 0.0)
        new_threshold = current + adjustment

        # Clamp to category bounds
        new_threshold = max(bounds.min_value, min(bounds.max_value, new_threshold))

        # Store learned threshold
        key = self._threshold_key(category)
        self._learned[key] = new_threshold

        logger.info(
            f"Adjusted {category.value} threshold: {current:.2f} → {new_threshold:.2f} "
            f"(signal={feedback_signal})"
        )

        return new_threshold

    async def persist_threshold(
        self,
        category: CausalityCategory,
        db_conn,
    ) -> None:
        """
        Persist learned threshold to st_learned_weights.

        Args:
            category: Category to persist
            db_conn: Database connection
        """
        key = self._threshold_key(category)
        value = self._learned.get(key)
        if value is None:
            return

        await db_conn.execute(
            """
            INSERT INTO st_learned_weights (
                param_id, param_key, param_scope, current_value, updated_at
            ) VALUES ($1, $2, 'global', $3, $4)
            ON CONFLICT (param_key, param_scope, COALESCE(scope_id, ''))
            DO UPDATE SET
                current_value = $3,
                prior_value = st_learned_weights.current_value,
                updated_at = $4
            """,
            generate_ulid(),
            key,
            value,
            now_ms(),
        )

        logger.debug(f"Persisted threshold {key}={value}")

    @classmethod
    async def load_from_database(
        cls,
        db_conn,
        classifier: Optional[CausalCategoryClassifier] = None,
    ) -> "AdaptiveCausalityThresholds":
        """
        Load learned thresholds from database.

        Args:
            db_conn: Database connection
            classifier: Optional classifier instance

        Returns:
            AdaptiveCausalityThresholds with loaded thresholds
        """
        rows = await db_conn.fetch(
            """
            SELECT param_key, current_value FROM st_learned_weights
            WHERE param_key LIKE 'causality_threshold_%'
              AND param_scope = 'global'
            """
        )

        learned = {row["param_key"]: row["current_value"] for row in rows}
        return cls(classifier=classifier, learned_thresholds=learned)

    def _threshold_key(self, category: CausalityCategory) -> str:
        """Generate storage key for category threshold."""
        return f"causality_threshold_{category.value.replace('/', '_')}"

    def get_all_thresholds(self) -> Dict[CausalityCategory, float]:
        """Get all current thresholds (learned or default)."""
        return {cat: self.get_threshold(cat) for cat in CausalityCategory}
