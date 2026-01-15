"""
MinSamplesAdjuster — Adaptive min_samples learning based on singleton rate.

Issue 4.2.6: Implement adaptive min_samples learning

Spec Reference:
    - Dossier Appendix C.3.1.2 (Adaptive min_samples) — lines 21480-21560
    - st_learned_weights migration 0040 — storage for dbscan_min_samples

Problem Statement:
    Fixed `min_samples=2` creates issues:
    - Noisy spaces (many singleton events): Too many micro-episodes → K1 cluttered
    - Sparse spaces (few events): min_samples=2 prevents any clustering

Adjustment Rules:
    | Singleton Rate | Diagnosis           | Action            | New min_samples   |
    |----------------|---------------------|-------------------|-------------------|
    | > 20%          | Too noisy           | Increase threshold| min_samples + 1   |
    | < 5%           | Too strict          | Decrease threshold| min_samples - 1   |
    | 5-20%          | Good balance        | No change         | Keep current      |

Bounds: min_samples ∈ [2, 5]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class MinSamplesConfig:
    """
    Configuration for adaptive min_samples learning.

    Spec: Dossier Appendix C.3.1.2

    Attributes:
        min_samples_min: Lower bound (2 — allows pairs to cluster)
        min_samples_max: Upper bound (5 — requires 5+ events per cluster)
        noise_threshold_high: Above this = too noisy, increase threshold (0.20)
        noise_threshold_low: Below this = too strict, decrease threshold (0.05)
    """

    min_samples_min: int = 2
    min_samples_max: int = 5
    noise_threshold_high: float = 0.20
    noise_threshold_low: float = 0.05

    def validate(self) -> None:
        """Validate configuration ranges."""
        if not 1 <= self.min_samples_min < self.min_samples_max <= 10:
            raise ValueError(
                f"min_samples_min ({self.min_samples_min}) must be < "
                f"min_samples_max ({self.min_samples_max}) and both in [1, 10]"
            )
        if not 0.0 <= self.noise_threshold_low < self.noise_threshold_high <= 1.0:
            raise ValueError(
                f"noise_threshold_low ({self.noise_threshold_low}) must be < "
                f"noise_threshold_high ({self.noise_threshold_high}) and both in [0, 1]"
            )


# =============================================================================
# MinSamplesAdjustmentResult
# =============================================================================


@dataclass
class MinSamplesAdjustmentResult:
    """
    Result of a min_samples adjustment attempt.

    Attributes:
        previous_min_samples: Value before adjustment
        new_min_samples: Value after adjustment (may be same if no change)
        adjusted: Whether an adjustment was made
        reason: Human-readable explanation
        singleton_rate: Input singleton rate that triggered decision
        direction: "increase", "decrease", or "none"
    """

    previous_min_samples: int
    new_min_samples: int
    adjusted: bool
    reason: str
    singleton_rate: float = 0.0
    direction: str = "none"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "previous_min_samples": self.previous_min_samples,
            "new_min_samples": self.new_min_samples,
            "adjusted": self.adjusted,
            "reason": self.reason,
            "singleton_rate": round(self.singleton_rate, 4),
            "direction": self.direction,
        }


# =============================================================================
# Database Protocol
# =============================================================================


@runtime_checkable
class AsyncDBConnection(Protocol):
    """Protocol for async database connection (asyncpg-compatible)."""

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Fetch single row."""
        ...

    async def execute(self, query: str, *args: Any) -> str:
        """Execute query."""
        ...


# =============================================================================
# MinSamplesAdjuster Class
# =============================================================================


class MinSamplesAdjuster:
    """
    Adaptive min_samples learning based on singleton rate.

    Tunes DBSCAN `min_samples` parameter per-space based on noise level.

    Spec: Dossier Appendix C.3.1.2

    Problem Statement:
        Fixed `min_samples=2` creates issues:
        - Noisy spaces (many singletons): Too many micro-episodes → K1 cluttered
        - Sparse spaces (few events): min_samples=2 prevents clustering

    Algorithm:
        - singleton_rate > 0.20 → increase (too noisy, need stricter threshold)
        - singleton_rate < 0.05 → decrease (too strict, relax threshold)
        - 0.05 <= singleton_rate <= 0.20 → no change (good balance)

    Bounds: min_samples ∈ [2, 5]

    Usage:
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=2,
            singleton_rate=0.25,  # 25% noise
        )

        if result.adjusted:
            print(f"min_samples: {result.previous_min_samples} → {result.new_min_samples}")
            # Output: min_samples: 2 → 3 (increased due to high noise)
    """

    DEFAULT_MIN_SAMPLES: int = 2
    """Default min_samples value for new spaces."""

    def __init__(self, config: Optional[MinSamplesConfig] = None):
        """
        Initialize MinSamplesAdjuster.

        Args:
            config: Adjustment configuration (uses defaults if None)
        """
        self.config = config or MinSamplesConfig()

    def adjust(
        self,
        current_min_samples: int,
        singleton_rate: float,
    ) -> MinSamplesAdjustmentResult:
        """
        Adjust min_samples based on singleton rate.

        Algorithm (from Dossier C.3.1.2):
            - singleton_rate > 0.20 → increase (too noisy)
            - singleton_rate < 0.05 → decrease (too strict)
            - 0.05 <= singleton_rate <= 0.20 → no change (good balance)

        Args:
            current_min_samples: Current min_samples value
            singleton_rate: Noise events / total events [0, 1]

        Returns:
            MinSamplesAdjustmentResult with new value and metadata
        """
        # High singleton rate → increase threshold (stricter clustering)
        if singleton_rate > self.config.noise_threshold_high:
            new_min_samples = min(
                self.config.min_samples_max,
                current_min_samples + 1,
            )

            if new_min_samples == current_min_samples:
                reason = (
                    f"singleton_rate {singleton_rate:.3f} > {self.config.noise_threshold_high}, "
                    f"but already at max ({self.config.min_samples_max})"
                )
                adjusted = False
            else:
                reason = (
                    f"singleton_rate {singleton_rate:.3f} > {self.config.noise_threshold_high} "
                    f"→ INCREASE min_samples (too noisy)"
                )
                adjusted = True

            logger.info(f"MinSamplesAdjuster: {current_min_samples} → {new_min_samples} | {reason}")

            return MinSamplesAdjustmentResult(
                previous_min_samples=current_min_samples,
                new_min_samples=new_min_samples,
                adjusted=adjusted,
                reason=reason,
                singleton_rate=singleton_rate,
                direction="increase" if adjusted else "none",
            )

        # Low singleton rate → decrease threshold (looser clustering)
        if singleton_rate < self.config.noise_threshold_low:
            new_min_samples = max(
                self.config.min_samples_min,
                current_min_samples - 1,
            )

            if new_min_samples == current_min_samples:
                reason = (
                    f"singleton_rate {singleton_rate:.3f} < {self.config.noise_threshold_low}, "
                    f"but already at min ({self.config.min_samples_min})"
                )
                adjusted = False
            else:
                reason = (
                    f"singleton_rate {singleton_rate:.3f} < {self.config.noise_threshold_low} "
                    f"→ DECREASE min_samples (too strict)"
                )
                adjusted = True

            logger.info(f"MinSamplesAdjuster: {current_min_samples} → {new_min_samples} | {reason}")

            return MinSamplesAdjustmentResult(
                previous_min_samples=current_min_samples,
                new_min_samples=new_min_samples,
                adjusted=adjusted,
                reason=reason,
                singleton_rate=singleton_rate,
                direction="decrease" if adjusted else "none",
            )

        # Good balance — no change
        reason = (
            f"singleton_rate {singleton_rate:.3f} in good range "
            f"[{self.config.noise_threshold_low}, {self.config.noise_threshold_high}]"
        )

        return MinSamplesAdjustmentResult(
            previous_min_samples=current_min_samples,
            new_min_samples=current_min_samples,
            adjusted=False,
            reason=reason,
            singleton_rate=singleton_rate,
            direction="none",
        )

    async def load_min_samples(
        self,
        space_id: str,
        db_conn: AsyncDBConnection,
    ) -> int:
        """
        Load current min_samples from st_learned_weights.

        Falls back to DEFAULT_MIN_SAMPLES (2) if not found.

        Args:
            space_id: Space to load min_samples for
            db_conn: Async database connection

        Returns:
            Current min_samples value for space
        """
        try:
            row = await db_conn.fetchrow(
                """
                SELECT current_value FROM st_learned_weights
                WHERE space_id = $1 AND param_key = 'dbscan_min_samples' AND param_scope = 'space'
                """,
                space_id,
            )
            if row and row.get("current_value") is not None:
                return int(row["current_value"])
        except Exception as e:
            logger.warning(f"Failed to load min_samples for space {space_id}: {e}")

        return self.DEFAULT_MIN_SAMPLES

    async def save_min_samples(
        self,
        space_id: str,
        new_min_samples: int,
        singleton_rate: float,
        db_conn: AsyncDBConnection,
    ) -> None:
        """
        Persist updated min_samples to st_learned_weights.

        Uses UPSERT to insert or update the value.

        Args:
            space_id: Space to save min_samples for
            new_min_samples: New min_samples value
            singleton_rate: Singleton rate (used for confidence calculation)
            db_conn: Async database connection
        """
        # Confidence inversely related to noise
        # Low singleton rate = high confidence in clustering
        confidence = max(0.0, min(1.0, 1.0 - singleton_rate))

        try:
            await db_conn.execute(
                """
                INSERT INTO st_learned_weights (
                    param_id, param_key, param_scope, scope_id, space_id,
                    current_value, prior_value, confidence, sample_count, last_updated_at
                ) VALUES (
                    gen_random_uuid(), 'dbscan_min_samples', 'space', $1, $1,
                    $2, 2.0, $3, 1, (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
                )
                ON CONFLICT (space_id, param_key, param_scope, scope_id)
                DO UPDATE SET
                    prior_value = st_learned_weights.current_value,
                    current_value = $2,
                    confidence = $3,
                    sample_count = st_learned_weights.sample_count + 1,
                    last_updated_at = (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
                """,
                space_id,
                float(new_min_samples),
                confidence,
            )
            logger.debug(
                f"Saved min_samples={new_min_samples} for space={space_id}, "
                f"singleton_rate={singleton_rate:.3f}, confidence={confidence:.3f}"
            )
        except Exception as e:
            logger.error(f"Failed to save min_samples for space {space_id}: {e}")
            raise


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "MinSamplesConfig",
    "MinSamplesAdjustmentResult",
    "MinSamplesAdjuster",
]
