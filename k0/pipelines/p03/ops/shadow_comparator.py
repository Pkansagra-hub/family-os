"""P03 Shadow Mode Comparator — Baseline vs learned formula comparison.

This module provides shadow mode comparison logic for evaluating learned
formulas against baseline formulas before promotion.

Issue Reference: M6_EXECUTION.md Issue 6.1.8
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.2.6

Shadow Mode Concept:
    Feature flag controls: off → shadow → partial → full
    Shadow mode runs BOTH baseline and learned formulas, applies only baseline.
    Comparison logged for analysis before promotion.

Promotion Criteria:
    improvement_rate > 0.05 AND regression_rate < 0.02 AND sample_size > 1000

Usage:
    comparator = ShadowModeComparator()

    # Compare a single execution
    outcome = comparator.compare(
        baseline=0.75,
        learned=0.82,
        ground_truth=0.80,
    )
    # → "improvement"

    # Evaluate promotion eligibility
    eligible = comparator.evaluate_promotion_eligibility(
        improvement_rate=0.08,
        regression_rate=0.01,
        sample_size=1500,
    )
    # → True
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

__all__ = [
    "ShadowModeComparator",
    "ShadowComparisonResult",
    "ShadowOutcome",
    "LearningType",
    "PROMOTION_CRITERIA",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Comparison thresholds
AGREEMENT_TOLERANCE = 0.05  # Within 5% = agreement
IMPROVEMENT_THRESHOLD = 0.10  # 10% better = improvement

# Promotion criteria
PROMOTION_CRITERIA = {
    "min_improvement_rate": 0.05,  # > 5% improvement rate
    "max_regression_rate": 0.02,  # < 2% regression rate
    "min_sample_size": 1000,  # At least 1000 samples
}

# Rolling window for rate calculations (days)
RATE_WINDOW_DAYS = 7


# =============================================================================
# ENUMS
# =============================================================================


class ShadowOutcome(str, Enum):
    """Outcome of shadow mode comparison.

    From dossier 8.2.6:
    - AGREEMENT: Baseline and learned produce same result (within tolerance)
    - IMPROVEMENT: Learned is objectively better than baseline
    - REGRESSION: Learned is worse than baseline
    - DIVERGENCE: Different results, no ground truth to judge
    """

    AGREEMENT = "agreement"
    IMPROVEMENT = "improvement"
    REGRESSION = "regression"
    DIVERGENCE = "divergence"


class LearningType(str, Enum):
    """Types of learned formulas in P03.

    From dossier 6.5:
    - IMPORTANCE: Importance scoring weights (R1)
    - HEBBIAN: Edge weight adjustments (R4)
    - DECAY: Lambda parameter tuning (R3/R5)
    - SIMILARITY: Matching thresholds (R2)
    - THRESHOLD: Decision thresholds (R3)
    """

    IMPORTANCE = "importance"
    HEBBIAN = "hebbian"
    DECAY = "decay"
    SIMILARITY = "similarity"
    THRESHOLD = "threshold"


# =============================================================================
# RESULT DATACLASSES
# =============================================================================


@dataclass
class ShadowComparisonResult:
    """Result of a single shadow mode comparison.

    Attributes:
        learning_type: Type of learning being compared.
        baseline_value: Value from baseline formula.
        learned_value: Value from learned formula.
        ground_truth: Optional ground truth for objective comparison.
        outcome: Comparison outcome (agreement, improvement, etc.).
        divergence_magnitude: Magnitude of difference (for divergence).
        baseline_error: Error from baseline (if ground truth available).
        learned_error: Error from learned (if ground truth available).
    """

    learning_type: LearningType
    baseline_value: float
    learned_value: float
    ground_truth: Optional[float]
    outcome: ShadowOutcome
    divergence_magnitude: float = 0.0
    baseline_error: Optional[float] = None
    learned_error: Optional[float] = None


@dataclass
class ShadowRollingStats:
    """Rolling statistics for shadow mode comparisons.

    Attributes:
        learning_type: Type of learning.
        total_samples: Total samples in window.
        agreement_count: Number of agreements.
        improvement_count: Number of improvements.
        regression_count: Number of regressions.
        divergence_count: Number of divergences.
        agreement_rate: Agreement rate [0.0, 1.0].
        improvement_rate: Improvement rate [0.0, 1.0].
        regression_rate: Regression rate [0.0, 1.0].
        promotion_eligible: Whether promotion criteria are met.
    """

    learning_type: LearningType
    total_samples: int = 0
    agreement_count: int = 0
    improvement_count: int = 0
    regression_count: int = 0
    divergence_count: int = 0
    agreement_rate: float = 0.0
    improvement_rate: float = 0.0
    regression_rate: float = 0.0
    promotion_eligible: bool = False


# =============================================================================
# SHADOW MODE COMPARATOR
# =============================================================================


class ShadowModeComparator:
    """Compares baseline vs learned formula outcomes.

    Used in shadow mode to evaluate learned formulas before promotion.
    Tracks rolling statistics and evaluates promotion eligibility.

    Thread Safety:
        NOT thread-safe for in-memory stats. Use external locking or
        separate instances per thread.

    Usage:
        comparator = ShadowModeComparator()

        # Compare single execution
        result = comparator.compare_and_record(
            learning_type=LearningType.IMPORTANCE,
            baseline=0.75,
            learned=0.82,
            ground_truth=0.80,
        )

        # Get rolling stats
        stats = comparator.get_rolling_stats(LearningType.IMPORTANCE)

        # Check promotion eligibility
        if stats.promotion_eligible:
            print("Ready for promotion!")

    Spec: Dossier 8.2.6, M6_EXECUTION.md Issue 6.1.8
    """

    def __init__(
        self,
        agreement_tolerance: float = AGREEMENT_TOLERANCE,
        improvement_threshold: float = IMPROVEMENT_THRESHOLD,
        promotion_criteria: Optional[Dict[str, float]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize shadow mode comparator.

        Args:
            agreement_tolerance: Tolerance for agreement classification.
            improvement_threshold: Threshold for improvement classification.
            promotion_criteria: Override default promotion criteria.
            logger: Logger instance. Creates default if None.
        """
        self._agreement_tolerance = agreement_tolerance
        self._improvement_threshold = improvement_threshold
        self._promotion_criteria = promotion_criteria or PROMOTION_CRITERIA
        self._logger = logger or LOGGER

        # In-memory rolling stats (per learning type)
        self._stats: Dict[LearningType, List[ShadowComparisonResult]] = {
            lt: [] for lt in LearningType
        }

    def compare(
        self,
        baseline: float,
        learned: float,
        ground_truth: Optional[float] = None,
    ) -> ShadowOutcome:
        """Classify comparison outcome.

        Logic from M6_EXECUTION.md:
        1. If baseline and learned are within tolerance → agreement
        2. If ground truth available:
           - learned_error < baseline_error * 0.90 → improvement
           - learned_error > baseline_error * 1.10 → regression
        3. Otherwise → divergence

        Args:
            baseline: Value from baseline formula.
            learned: Value from learned formula.
            ground_truth: Optional ground truth for objective comparison.

        Returns:
            ShadowOutcome classification.
        """
        # Check agreement (within tolerance)
        relative_diff = abs(baseline - learned) / max(abs(baseline), 0.001)
        if relative_diff < self._agreement_tolerance:
            return ShadowOutcome.AGREEMENT

        # If ground truth available, compare errors
        if ground_truth is not None:
            baseline_error = abs(baseline - ground_truth)
            learned_error = abs(learned - ground_truth)

            # Improvement: learned error < baseline error * (1 - threshold)
            if learned_error < baseline_error * (1 - self._improvement_threshold):
                return ShadowOutcome.IMPROVEMENT

            # Regression: learned error > baseline error * (1 + threshold)
            if learned_error > baseline_error * (1 + self._improvement_threshold):
                return ShadowOutcome.REGRESSION

        # No ground truth or inconclusive → divergence
        return ShadowOutcome.DIVERGENCE

    def compare_and_record(
        self,
        learning_type: LearningType,
        baseline: float,
        learned: float,
        ground_truth: Optional[float] = None,
    ) -> ShadowComparisonResult:
        """Compare and record result for rolling statistics.

        Args:
            learning_type: Type of learning being compared.
            baseline: Value from baseline formula.
            learned: Value from learned formula.
            ground_truth: Optional ground truth for objective comparison.

        Returns:
            ShadowComparisonResult with full details.
        """
        outcome = self.compare(baseline, learned, ground_truth)

        # Calculate errors if ground truth available
        baseline_error = None
        learned_error = None
        if ground_truth is not None:
            baseline_error = abs(baseline - ground_truth)
            learned_error = abs(learned - ground_truth)

        # Calculate divergence magnitude
        divergence_magnitude = abs(baseline - learned)

        result = ShadowComparisonResult(
            learning_type=learning_type,
            baseline_value=baseline,
            learned_value=learned,
            ground_truth=ground_truth,
            outcome=outcome,
            divergence_magnitude=divergence_magnitude,
            baseline_error=baseline_error,
            learned_error=learned_error,
        )

        # Record for rolling stats
        self._stats[learning_type].append(result)

        self._logger.debug(
            "Shadow comparison: type=%s baseline=%.4f learned=%.4f " "ground_truth=%s outcome=%s",
            learning_type.value,
            baseline,
            learned,
            f"{ground_truth:.4f}" if ground_truth else "N/A",
            outcome.value,
        )

        return result

    def get_rolling_stats(
        self,
        learning_type: LearningType,
        window_size: Optional[int] = None,
    ) -> ShadowRollingStats:
        """Get rolling statistics for a learning type.

        Args:
            learning_type: Type of learning to get stats for.
            window_size: Override window size (default uses all recorded).

        Returns:
            ShadowRollingStats with counts and rates.
        """
        samples = self._stats[learning_type]
        if window_size:
            samples = samples[-window_size:]

        total = len(samples)
        if total == 0:
            return ShadowRollingStats(learning_type=learning_type)

        # Count outcomes
        agreement_count = sum(1 for s in samples if s.outcome == ShadowOutcome.AGREEMENT)
        improvement_count = sum(1 for s in samples if s.outcome == ShadowOutcome.IMPROVEMENT)
        regression_count = sum(1 for s in samples if s.outcome == ShadowOutcome.REGRESSION)
        divergence_count = sum(1 for s in samples if s.outcome == ShadowOutcome.DIVERGENCE)

        # Calculate rates
        agreement_rate = agreement_count / total
        improvement_rate = improvement_count / total
        regression_rate = regression_count / total

        # Evaluate promotion eligibility
        promotion_eligible = self.evaluate_promotion_eligibility(
            improvement_rate=improvement_rate,
            regression_rate=regression_rate,
            sample_size=total,
        )

        return ShadowRollingStats(
            learning_type=learning_type,
            total_samples=total,
            agreement_count=agreement_count,
            improvement_count=improvement_count,
            regression_count=regression_count,
            divergence_count=divergence_count,
            agreement_rate=agreement_rate,
            improvement_rate=improvement_rate,
            regression_rate=regression_rate,
            promotion_eligible=promotion_eligible,
        )

    def evaluate_promotion_eligibility(
        self,
        improvement_rate: float,
        regression_rate: float,
        sample_size: int,
    ) -> bool:
        """Evaluate whether learned formula meets promotion criteria.

        Criteria (from dossier 8.2.6):
        - improvement_rate > 0.05 (5%)
        - regression_rate < 0.02 (2%)
        - sample_size >= 1000

        Args:
            improvement_rate: Rate of improvements [0.0, 1.0].
            regression_rate: Rate of regressions [0.0, 1.0].
            sample_size: Number of samples in window.

        Returns:
            True if promotion criteria are met.
        """
        meets_improvement = improvement_rate > self._promotion_criteria["min_improvement_rate"]
        meets_regression = regression_rate < self._promotion_criteria["max_regression_rate"]
        meets_sample_size = sample_size >= self._promotion_criteria["min_sample_size"]

        return meets_improvement and meets_regression and meets_sample_size

    def get_all_rolling_stats(self) -> Dict[LearningType, ShadowRollingStats]:
        """Get rolling stats for all learning types.

        Returns:
            Dict mapping learning type to rolling stats.
        """
        return {lt: self.get_rolling_stats(lt) for lt in LearningType}

    def clear_stats(self, learning_type: Optional[LearningType] = None) -> None:
        """Clear recorded statistics.

        Args:
            learning_type: Specific type to clear. Clears all if None.
        """
        if learning_type:
            self._stats[learning_type] = []
        else:
            self._stats = {lt: [] for lt in LearningType}

    def get_divergence_magnitudes(
        self,
        learning_type: LearningType,
    ) -> List[float]:
        """Get list of divergence magnitudes for histogram emission.

        Args:
            learning_type: Type of learning.

        Returns:
            List of divergence magnitudes.
        """
        return [
            s.divergence_magnitude
            for s in self._stats[learning_type]
            if s.outcome == ShadowOutcome.DIVERGENCE
        ]
