"""
EpsAdjuster — Adaptive eps learning via silhouette score optimization.

Issue 4.2.5: Implement adaptive eps learning (silhouette-driven)

Spec Reference:
    - Dossier §4.3.1.1 (Adaptive Eps Learning) — lines 3247-3293
    - st_learned_weights migration 0040 — storage for clustering_eps

Algorithm:
    1. After each P03 cycle: Compute silhouette score for generated clusters.
    2. If silhouette < 0.30:
       - If avg_cluster_size > 10 → decrease eps by 0.02 (too loose)
       - If singleton_rate > 0.20 → increase eps by 0.02 (too tight)
    3. Momentum smoothing: eps_new = 0.9 × eps_old + 0.1 × eps_adjusted
    4. Bounds enforcement: eps = max(0.15, min(0.40, eps))

Cold Start:
    - New spaces use global default (0.25) until 100 clusters formed.
    - Then switch to per-space learning.

Storage Pattern (in st_learned_weights):
    | param_key      | param_scope | Default | Range        | Target Metric    |
    |----------------|-------------|---------|--------------|------------------|
    | clustering_eps | space       | 0.25    | [0.15, 0.40] | silhouette > 0.30|
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
class EpsAdjustmentConfig:
    """
    Configuration for adaptive eps learning.

    Spec: Dossier §4.3.1.1

    Attributes:
        eps_min: Lower bound for eps (0.15 — tightest clustering)
        eps_max: Upper bound for eps (0.40 — loosest clustering)
        eps_step: Adjustment increment per cycle (0.02)
        silhouette_target: Quality threshold (0.30 — real silhouette p75)
        momentum: Smoothing factor (0.9 = 90% old value, 10% new)
        cold_start_threshold: Clusters needed before learning starts (100)
    """

    eps_min: float = 0.15
    eps_max: float = 0.40
    eps_step: float = 0.02
    silhouette_target: float = 0.30
    momentum: float = 0.9
    cold_start_threshold: int = 100

    # Thresholds for adjustment direction
    avg_cluster_size_high: float = 10.0
    """Above this = clusters too loose → decrease eps."""

    singleton_rate_high: float = 0.20
    """Above this = too much noise → increase eps."""

    def validate(self) -> None:
        """Validate configuration ranges."""
        if not 0.0 < self.eps_min < self.eps_max <= 1.0:
            raise ValueError(
                f"eps_min ({self.eps_min}) must be < eps_max ({self.eps_max}) " "and both in (0, 1]"
            )
        if not 0.0 < self.eps_step <= 0.1:
            raise ValueError(f"eps_step must be in (0, 0.1], got {self.eps_step}")
        if not 0.0 <= self.momentum <= 1.0:
            raise ValueError(f"momentum must be in [0, 1], got {self.momentum}")
        if not 0.0 <= self.silhouette_target <= 1.0:
            raise ValueError(f"silhouette_target must be in [0, 1], got {self.silhouette_target}")


# =============================================================================
# EpsAdjustmentResult
# =============================================================================


@dataclass
class EpsAdjustmentResult:
    """
    Result of an eps adjustment attempt.

    Attributes:
        previous_eps: Eps value before adjustment
        new_eps: Eps value after adjustment (may be same if no change)
        adjusted: Whether an adjustment was made
        reason: Human-readable explanation
        silhouette_score: Input silhouette score
        avg_cluster_size: Input average cluster size
        singleton_rate: Input singleton rate
        cold_start: Whether still in cold start phase
    """

    previous_eps: float
    new_eps: float
    adjusted: bool
    reason: str
    silhouette_score: float = 0.0
    avg_cluster_size: float = 0.0
    singleton_rate: float = 0.0
    cold_start: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "previous_eps": round(self.previous_eps, 4),
            "new_eps": round(self.new_eps, 4),
            "adjusted": self.adjusted,
            "reason": self.reason,
            "silhouette_score": round(self.silhouette_score, 4),
            "avg_cluster_size": round(self.avg_cluster_size, 2),
            "singleton_rate": round(self.singleton_rate, 4),
            "cold_start": self.cold_start,
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
# EpsAdjuster Class
# =============================================================================


class EpsAdjuster:
    """
    Adaptive eps learning via silhouette score optimization.

    Tunes DBSCAN `eps` parameter per-space based on cluster quality
    feedback (silhouette score, cluster size, singleton rate).

    Spec: Dossier §4.3.1.1

    Problem Statement:
        Fixed `eps=0.25` doesn't suit all spaces:
        - Tight spaces (single-topic): Events cluster too broadly → need lower eps
        - Loose spaces (multi-domain): Events fail to cluster → need higher eps

    Algorithm:
        1. Skip if in cold start phase (< 100 clusters)
        2. Skip if silhouette >= 0.30 (quality is acceptable)
        3. If avg_cluster_size > 10: decrease eps (clusters too loose)
        4. If singleton_rate > 0.20: increase eps (too much noise)
        5. Apply momentum smoothing to prevent wild swings
        6. Clamp to bounds [0.15, 0.40]

    Usage:
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.25,
            silhouette_score=0.35,
            avg_cluster_size=15.0,
            singleton_rate=0.10,
            total_clusters_formed=150,
        )

        if result.adjusted:
            print(f"Eps changed: {result.previous_eps} → {result.new_eps}")
            print(f"Reason: {result.reason}")
    """

    DEFAULT_EPS: float = 0.15  # Tighter default for UltraBERT L2-normalized embeddings
    """Default eps value for new spaces."""

    def __init__(self, config: Optional[EpsAdjustmentConfig] = None):
        """
        Initialize EpsAdjuster.

        Args:
            config: Adjustment configuration (uses defaults if None)
        """
        self.config = config or EpsAdjustmentConfig()

    def adjust(
        self,
        current_eps: float,
        silhouette_score: float,
        avg_cluster_size: float,
        singleton_rate: float,
        total_clusters_formed: int,
    ) -> EpsAdjustmentResult:
        """
        Adjust eps based on cluster quality metrics.

        Algorithm (from Dossier §4.3.1.1):
            1. Cold start: Skip if < cold_start_threshold clusters formed
            2. Quality check: Skip if silhouette >= silhouette_target
            3. Direction:
               - If avg_cluster_size > 10 → decrease eps (too loose)
               - If singleton_rate > 0.20 → increase eps (too tight)
            4. Momentum: eps_new = 0.9 × eps_old + 0.1 × eps_adjusted
            5. Bounds: Clamp to [eps_min, eps_max]

        Args:
            current_eps: Current eps value
            silhouette_score: Batch silhouette score [-1, 1]
            avg_cluster_size: Average events per cluster
            singleton_rate: Noise events / total events
            total_clusters_formed: Historical cluster count for space

        Returns:
            EpsAdjustmentResult with new eps and metadata
        """
        # Cold start phase — not enough data to learn
        if total_clusters_formed < self.config.cold_start_threshold:
            return EpsAdjustmentResult(
                previous_eps=current_eps,
                new_eps=current_eps,
                adjusted=False,
                reason=f"Cold start: {total_clusters_formed} < {self.config.cold_start_threshold} clusters",
                silhouette_score=silhouette_score,
                avg_cluster_size=avg_cluster_size,
                singleton_rate=singleton_rate,
                cold_start=True,
            )

        # Quality is acceptable — no adjustment needed
        # EXCEPT: A giant single cluster with high silhouette is NOT good clustering!
        # We must still check avg_cluster_size to avoid the "one big cluster" problem.
        if silhouette_score >= self.config.silhouette_target:
            # Override if clusters are too loose (avg_size > threshold)
            if avg_cluster_size <= self.config.avg_cluster_size_high:
                return EpsAdjustmentResult(
                    previous_eps=current_eps,
                    new_eps=current_eps,
                    adjusted=False,
                    reason=f"Silhouette {silhouette_score:.3f} >= {self.config.silhouette_target} target",
                    silhouette_score=silhouette_score,
                    avg_cluster_size=avg_cluster_size,
                    singleton_rate=singleton_rate,
                )
            # Fall through to adjustment logic if avg_cluster_size is too high

        # Determine adjustment direction
        eps_adjusted = current_eps
        adjustment_reason = ""

        if avg_cluster_size > self.config.avg_cluster_size_high:
            # Clusters too loose → decrease eps (tighter clustering)
            eps_adjusted = current_eps - self.config.eps_step
            adjustment_reason = (
                f"avg_cluster_size {avg_cluster_size:.1f} > {self.config.avg_cluster_size_high} "
                "→ DECREASE eps (clusters too loose)"
            )
        elif singleton_rate > self.config.singleton_rate_high:
            # Too much noise → increase eps (looser clustering)
            eps_adjusted = current_eps + self.config.eps_step
            adjustment_reason = (
                f"singleton_rate {singleton_rate:.3f} > {self.config.singleton_rate_high} "
                "→ INCREASE eps (too much noise)"
            )
        else:
            # Neither condition met — no adjustment
            return EpsAdjustmentResult(
                previous_eps=current_eps,
                new_eps=current_eps,
                adjusted=False,
                reason=(
                    f"No adjustment: silhouette={silhouette_score:.3f} < target, "
                    f"but avg_size={avg_cluster_size:.1f} and singleton_rate={singleton_rate:.3f} in range"
                ),
                silhouette_score=silhouette_score,
                avg_cluster_size=avg_cluster_size,
                singleton_rate=singleton_rate,
            )

        # Momentum smoothing: eps_new = 0.9 × eps_old + 0.1 × eps_adjusted
        eps_smoothed = (
            self.config.momentum * current_eps + (1 - self.config.momentum) * eps_adjusted
        )

        # Clamp to bounds
        eps_clamped = max(self.config.eps_min, min(self.config.eps_max, eps_smoothed))

        # Log adjustment
        logger.info(f"EpsAdjuster: {current_eps:.4f} → {eps_clamped:.4f} | {adjustment_reason}")

        return EpsAdjustmentResult(
            previous_eps=current_eps,
            new_eps=eps_clamped,
            adjusted=True,
            reason=adjustment_reason,
            silhouette_score=silhouette_score,
            avg_cluster_size=avg_cluster_size,
            singleton_rate=singleton_rate,
        )

    async def load_eps(
        self,
        space_id: str,
        db_conn: AsyncDBConnection,
    ) -> float:
        """
        Load current eps from st_learned_weights.

        Falls back to DEFAULT_EPS (0.25) if not found.

        Args:
            space_id: Space to load eps for
            db_conn: Async database connection

        Returns:
            Current eps value for space
        """
        try:
            row = await db_conn.fetchrow(
                """
                SELECT current_value FROM st_learned_weights
                WHERE space_id = $1 AND param_key = 'clustering_eps' AND param_scope = 'space'
                """,
                space_id,
            )
            if row and row.get("current_value") is not None:
                return float(row["current_value"])
        except Exception as e:
            logger.warning(f"Failed to load eps for space {space_id}: {e}")

        return self.DEFAULT_EPS

    async def save_eps(
        self,
        space_id: str,
        new_eps: float,
        silhouette_score: float,
        db_conn: AsyncDBConnection,
    ) -> None:
        """
        Persist updated eps to st_learned_weights.

        Uses UPSERT to insert or update the value.

        Args:
            space_id: Space to save eps for
            new_eps: New eps value
            silhouette_score: Silhouette score (used as confidence proxy)
            db_conn: Async database connection
        """
        try:
            await db_conn.execute(
                """
                INSERT INTO st_learned_weights (
                    param_id, param_key, param_scope, scope_id, space_id,
                    current_value, prior_value, confidence, sample_count, last_updated_at
                ) VALUES (
                    gen_random_uuid(), 'clustering_eps', 'space', $1, $1,
                    $2, 0.25, $3, 1, (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
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
                new_eps,
                max(0.0, min(1.0, silhouette_score)),  # Clamp confidence to [0, 1]
            )
            logger.debug(
                f"Saved eps={new_eps:.4f} for space={space_id}, silhouette={silhouette_score:.3f}"
            )
        except Exception as e:
            logger.error(f"Failed to save eps for space {space_id}: {e}")
            raise


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "EpsAdjustmentConfig",
    "EpsAdjustmentResult",
    "EpsAdjuster",
]
