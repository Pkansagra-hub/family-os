"""
ClusterQualityTracker — Closed-loop cluster quality metrics.

Issue 4.2.7: Implement closed-loop cluster quality metrics

Spec Reference:
    - Dossier §4.3.4.1 (Closed-Loop Cluster Quality) — lines 3308-3388
    - st_consolidation_audit migration 0036 — audit trail table
    - st_feedback_signals — feedback from K1/user

Problem Statement:
    No ground truth labels for clusters (unsupervised learning).
    Need proxy metrics to evaluate quality.

Quality Signals:
    | Signal           | Source              | Weight | Target | Status   | Interpretation             |
    |------------------|---------------------|--------|--------|----------|----------------------------|
    | Silhouette Score | sklearn (automated) | 0.40   | > 0.30 | LIVE     | Cluster cohesion/separation|
    | Grounding Rate   | K1 feedback         | 0.30   | > 0.6  | DORMANT  | % clusters used by K1      |
    | Correction Rate  | User feedback       | 0.20   | < 0.05 | DORMANT  | User corrections / cluster |
    | Singleton Rate   | Noise proxy         | 0.10   | < 0.20 | LIVE     | Singleton % of total       |

Composite Quality Formula:
    composite = 0.40 × silhouette + 0.30 × grounding + 0.20 × (1-correction) + 0.10 × (1-singleton)
    Range: [0, 1] where 1.0 = perfect clustering
    Target: > 0.5 for acceptable quality
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Quality Signal Weights (from Dossier §4.3.4.1)
# =============================================================================

WEIGHT_SILHOUETTE: float = 0.40
WEIGHT_GROUNDING: float = 0.30
WEIGHT_CORRECTION: float = 0.20
WEIGHT_SINGLETON: float = 0.10

# Channel liveness — which quality signals actually have data sources.
# Dormant channels are excluded from composite weight to avoid phantom quality.
# When grounding/correction pipelines go live, flip these to True.
CHANNEL_SILHOUETTE_LIVE: bool = True
CHANNEL_GROUNDING_LIVE: bool = False  # No K1 grounding feedback loop yet
CHANNEL_CORRECTION_LIVE: bool = False  # No user correction signals yet
CHANNEL_SINGLETON_LIVE: bool = True
CHANNEL_COHERENCE_LIVE: bool = True  # M4-RSCH-04: episodic coherence rho=0.4556

# Coherence weight (M4-RSCH-04: replaces phantom grounding+correction)
WEIGHT_COHERENCE: float = 0.40

# Alert thresholds
ALERT_THRESHOLD_LOW: float = 0.3
CONSECUTIVE_FAILURES_FOR_ALERT: int = 3


# =============================================================================
# ClusterQualityMetrics
# =============================================================================


@dataclass
class ClusterQualityMetrics:
    """
    Cluster quality metrics for closed-loop learning.

    Spec: Dossier §4.3.4.1

    Core metrics from various sources:
        - silhouette_score: From sklearn, measures cluster cohesion/separation [0, 1]
        - grounding_rate: From K1 feedback, fraction of clusters used in responses
        - correction_rate: From user feedback, fraction of clusters corrected
        - singleton_rate: From R2 output, fraction of noise clusters

    Derived metric:
        - composite_quality: Weighted combination, target > 0.5
    """

    # Core metrics (all in [0, 1] range)
    silhouette_score: float = 0.0
    """Silhouette score from sklearn [-1, 1]. Only meaningful when silhouette_valid is True."""

    silhouette_valid: bool = True
    """Whether silhouette_score was computed from a real sklearn.metrics.silhouette_score
    call. False when silhouette is mathematically undefined (fewer than 2 clusters,
    all noise, or insufficient data). When False, silhouette is excluded from
    the composite quality weight."""

    coherence_score: float = 0.0
    """Episodic coherence from M4-RSCH-04 (equal-weight 5-dimension mean)."""

    coherence_valid: bool = False
    """Whether coherence_score was computed from member context signals."""

    grounding_rate: float = 0.0
    """Fraction of clusters used by K1 in responses."""

    correction_rate: float = 0.0
    """Fraction of clusters corrected by users."""

    singleton_rate: float = 0.0
    """Fraction of clusters that are noise/singletons."""

    # Derived
    composite_quality: float = 0.0
    """Weighted composite quality score [0, 1]."""

    # Raw counts for rate computation
    total_clusters: int = 0
    """Total clusters formed in this cycle."""

    grounded_clusters: int = 0
    """Clusters used by K1 (CLUSTER_GROUNDED signals)."""

    corrected_clusters: int = 0
    """Clusters corrected by users (CLUSTER_WRONG signals)."""

    singleton_clusters: int = 0
    """Singleton (noise) clusters."""

    # Cycle metadata
    space_id: str = ""
    """Space these metrics belong to."""

    cycle_id: str = ""
    """Unique ID for this consolidation cycle."""

    computed_at: int = 0
    """Timestamp when metrics were computed (milliseconds)."""

    def compute_composite(self) -> float:
        """
        Compute composite quality score from live channels only.

        Formula from Dossier 4.3.4.1 with channel liveness gating:
            Only channels with CHANNEL_*_LIVE=True contribute weight.
            Dormant channels (grounding, correction) are excluded and their
            weight is redistributed across live channels.

            Current live channels: silhouette (when valid) + singleton.
            Dormant channels: grounding, correction (no feedback loop yet).

        Returns:
            Composite quality in [0, 1], higher is better.
        """
        # Build weighted terms for live channels only
        terms: list[tuple[float, float]] = []  # (weight, value)

        if CHANNEL_COHERENCE_LIVE and self.coherence_valid:
            terms.append((WEIGHT_COHERENCE, self.coherence_score))

        if CHANNEL_SILHOUETTE_LIVE and self.silhouette_valid:
            normalized_silhouette = (self.silhouette_score + 1.0) / 2.0
            terms.append((WEIGHT_SILHOUETTE, normalized_silhouette))

        if CHANNEL_GROUNDING_LIVE:
            terms.append((WEIGHT_GROUNDING, self.grounding_rate))

        if CHANNEL_CORRECTION_LIVE:
            terms.append((WEIGHT_CORRECTION, 1.0 - self.correction_rate))

        if CHANNEL_SINGLETON_LIVE:
            terms.append((WEIGHT_SINGLETON, 1.0 - self.singleton_rate))

        if not terms:
            self.composite_quality = 0.0
            return self.composite_quality

        # Renormalize weights so they sum to 1.0
        total_weight = sum(w for w, _ in terms)
        self.composite_quality = sum(w * v for w, v in terms) / total_weight

        # Clamp to [0, 1]
        self.composite_quality = max(0.0, min(1.0, self.composite_quality))

        return self.composite_quality

    def compute_rates(self) -> None:
        """
        Compute rates from raw counts.

        Must be called after setting total_clusters, grounded_clusters,
        corrected_clusters, and singleton_clusters.
        """
        if self.total_clusters > 0:
            self.grounding_rate = self.grounded_clusters / self.total_clusters
            self.correction_rate = self.corrected_clusters / self.total_clusters
            self.singleton_rate = self.singleton_clusters / self.total_clusters
        else:
            self.grounding_rate = 0.0
            self.correction_rate = 0.0
            self.singleton_rate = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "silhouette_score": round(self.silhouette_score, 4),
            "silhouette_valid": self.silhouette_valid,
            "grounding_rate": round(self.grounding_rate, 4),
            "correction_rate": round(self.correction_rate, 4),
            "singleton_rate": round(self.singleton_rate, 4),
            "composite_quality": round(self.composite_quality, 4),
            "total_clusters": self.total_clusters,
            "grounded_clusters": self.grounded_clusters,
            "corrected_clusters": self.corrected_clusters,
            "singleton_clusters": self.singleton_clusters,
            "space_id": self.space_id,
            "cycle_id": self.cycle_id,
            "computed_at": self.computed_at,
            "coherence_score": round(self.coherence_score, 4),
            "coherence_valid": self.coherence_valid,
            "channel_liveness": {
                "coherence": CHANNEL_COHERENCE_LIVE,
                "silhouette": CHANNEL_SILHOUETTE_LIVE,
                "grounding": CHANNEL_GROUNDING_LIVE,
                "correction": CHANNEL_CORRECTION_LIVE,
                "singleton": CHANNEL_SINGLETON_LIVE,
            },
        }

    @property
    def is_acceptable(self) -> bool:
        """Check if quality meets target threshold (> 0.5)."""
        return self.composite_quality > 0.5


# =============================================================================
# R2 Output Protocol (used by ClusterQualityTracker)
# =============================================================================


@runtime_checkable
class R2OutputProtocol(Protocol):
    """Protocol for R2 phase output (for type checking)."""

    batch_silhouette_score: float
    cluster_count: int
    noise_count: int
    silhouette_valid: bool


# =============================================================================
# Database Protocol
# =============================================================================


@runtime_checkable
class AsyncDBConnection(Protocol):
    """Protocol for async database connection."""

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Fetch single row."""
        ...

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Fetch single value."""
        ...

    async def execute(self, query: str, *args: Any) -> str:
        """Execute query."""
        ...


# =============================================================================
# ClusterQualityTracker
# =============================================================================


class ClusterQualityTracker:
    """
    Track and persist cluster quality metrics.

    Implements closed-loop learning by:
        1. Computing quality metrics from R2 output + feedback signals
        2. Persisting metrics to st_consolidation_audit
        3. Detecting quality degradation and raising alerts

    Spec: Dossier §4.3.4.1

    Usage:
        tracker = ClusterQualityTracker()

        # After R2 phase completes
        metrics = await tracker.compute_metrics(
            space_id="space-123",
            r2_output=r2_staged_output,
            db_conn=connection,
        )

        # Persist for historical tracking
        await tracker.persist_metrics(metrics, db_conn)

        # Check if alert needed
        alert = tracker.check_for_alert(metrics)
        if alert:
            logger.warning(alert)
    """

    def __init__(
        self,
        alert_threshold: float = ALERT_THRESHOLD_LOW,
        consecutive_failures: int = CONSECUTIVE_FAILURES_FOR_ALERT,
    ):
        """
        Initialize ClusterQualityTracker.

        Args:
            alert_threshold: Silhouette threshold for alerts (default 0.3)
            consecutive_failures: Failures needed before alert (default 3)
        """
        self.alert_threshold = alert_threshold
        self.consecutive_failures = consecutive_failures
        self._recent_scores: List[float] = []

    def compute_from_r2_output(
        self,
        space_id: str,
        r2_output: R2OutputProtocol,
        grounded_clusters: int = 0,
        corrected_clusters: int = 0,
    ) -> ClusterQualityMetrics:
        """
        Compute quality metrics from R2 output (sync version).

        Use this when feedback signal counts are already known
        (e.g., from a previous query or mock).

        Args:
            space_id: Space these metrics belong to
            r2_output: R2 phase output with silhouette, cluster counts
            grounded_clusters: Count of CLUSTER_GROUNDED signals (from feedback)
            corrected_clusters: Count of CLUSTER_WRONG signals (from feedback)

        Returns:
            ClusterQualityMetrics with all fields populated
        """
        metrics = ClusterQualityMetrics(
            space_id=space_id,
            cycle_id=str(uuid.uuid4()),
            computed_at=int(datetime.now().timestamp() * 1000),
        )

        # From R2 output
        metrics.silhouette_score = r2_output.batch_silhouette_score
        metrics.silhouette_valid = getattr(r2_output, "silhouette_valid", True)
        metrics.total_clusters = r2_output.cluster_count + r2_output.noise_count
        metrics.singleton_clusters = r2_output.noise_count

        # From feedback signals
        metrics.grounded_clusters = grounded_clusters
        metrics.corrected_clusters = corrected_clusters

        # Compute rates and composite
        metrics.compute_rates()
        metrics.compute_composite()

        return metrics

    async def compute_metrics(
        self,
        space_id: str,
        r2_output: R2OutputProtocol,
        db_conn: AsyncDBConnection,
        lookback_ms: int = 86_400_000,  # 24 hours
    ) -> ClusterQualityMetrics:
        """
        Compute quality metrics from R2 output and feedback signals.

        Queries st_feedback_signals for grounding and correction counts
        within the lookback window.

        Args:
            space_id: Space to compute metrics for
            r2_output: R2 phase output
            db_conn: Async database connection
            lookback_ms: Time window for feedback signals (default 24h)

        Returns:
            ClusterQualityMetrics with all fields populated
        """
        metrics = ClusterQualityMetrics(
            space_id=space_id,
            cycle_id=str(uuid.uuid4()),
            computed_at=int(datetime.now().timestamp() * 1000),
        )

        # From R2 output
        metrics.silhouette_score = r2_output.batch_silhouette_score
        metrics.silhouette_valid = getattr(r2_output, "silhouette_valid", True)
        metrics.total_clusters = r2_output.cluster_count + r2_output.noise_count
        metrics.singleton_clusters = r2_output.noise_count

        # Query grounded clusters from feedback signals
        try:
            grounded = await db_conn.fetchval(
                """
                SELECT COUNT(DISTINCT payload->>'epi_id') FROM st_feedback_signals
                WHERE space_id = $1 AND signal_type = 'CLUSTER_GROUNDED'
                AND created_at > (EXTRACT(EPOCH FROM NOW()) * 1000 - $2)::BIGINT
                """,
                space_id,
                lookback_ms,
            )
            metrics.grounded_clusters = grounded or 0
        except Exception as e:
            logger.warning(f"Failed to query grounded clusters: {e}")
            metrics.grounded_clusters = 0

        # Query corrected clusters from feedback signals
        try:
            corrected = await db_conn.fetchval(
                """
                SELECT COUNT(DISTINCT payload->>'epi_id') FROM st_feedback_signals
                WHERE space_id = $1 AND signal_type = 'CLUSTER_WRONG'
                AND created_at > (EXTRACT(EPOCH FROM NOW()) * 1000 - $2)::BIGINT
                """,
                space_id,
                lookback_ms,
            )
            metrics.corrected_clusters = corrected or 0
        except Exception as e:
            logger.warning(f"Failed to query corrected clusters: {e}")
            metrics.corrected_clusters = 0

        # Compute rates and composite
        metrics.compute_rates()
        metrics.compute_composite()

        logger.debug(
            f"ClusterQuality for {space_id}: "
            f"silhouette={metrics.silhouette_score:.3f}, "
            f"grounding={metrics.grounding_rate:.3f}, "
            f"correction={metrics.correction_rate:.3f}, "
            f"singleton={metrics.singleton_rate:.3f}, "
            f"composite={metrics.composite_quality:.3f}"
        )

        return metrics

    async def persist_metrics(
        self,
        metrics: ClusterQualityMetrics,
        db_conn: AsyncDBConnection,
    ) -> None:
        """
        Persist metrics to st_consolidation_audit.

        Args:
            metrics: Quality metrics to persist
            db_conn: Async database connection
        """
        try:
            await db_conn.execute(
                """
                INSERT INTO st_consolidation_audit (
                    audit_id, space_id, audit_type, action,
                    details_json, created_at
                ) VALUES (
                    gen_random_uuid(), $1, 'CLUSTER_QUALITY', 'METRICS_COMPUTED',
                    $2, $3
                )
                """,
                metrics.space_id,
                json.dumps(metrics.to_dict()),
                metrics.computed_at,
            )
            logger.debug(
                f"Persisted quality metrics for {metrics.space_id}: "
                f"composite={metrics.composite_quality:.3f}"
            )
        except Exception as e:
            logger.error(f"Failed to persist quality metrics: {e}")
            raise

    def check_for_alert(
        self,
        metrics: ClusterQualityMetrics,
    ) -> Optional[str]:
        """
        Check if alert should be raised.

        Alert when silhouette < alert_threshold for consecutive_failures cycles.
        Cycles where silhouette is invalid (< 2 clusters) are skipped — they
        do not count toward or against the consecutive-failure window.

        Args:
            metrics: Current cycle's quality metrics

        Returns:
            Alert message if triggered, None otherwise
        """
        # Skip cycles where silhouette could not be computed
        if not metrics.silhouette_valid:
            return None

        self._recent_scores.append(metrics.silhouette_score)

        # Keep only the last N scores
        if len(self._recent_scores) > self.consecutive_failures:
            self._recent_scores.pop(0)

        # Check for consecutive low scores
        if len(self._recent_scores) >= self.consecutive_failures:
            if all(s < self.alert_threshold for s in self._recent_scores):
                return (
                    f"CLUSTER_QUALITY_DEGRADED: silhouette < {self.alert_threshold} "
                    f"for {self.consecutive_failures} consecutive cycles "
                    f"(scores: {[round(s, 3) for s in self._recent_scores]})"
                )

        return None

    def reset_alert_state(self) -> None:
        """Reset alert tracking state."""
        self._recent_scores.clear()

    def get_tuning_recommendation(
        self,
        metrics: ClusterQualityMetrics,
    ) -> Dict[str, str]:
        """
        Get parameter tuning recommendation based on quality issues.

        Maps quality issues to parameter adjustments per Dossier §4.3.4.1.

        Args:
            metrics: Current cycle's quality metrics

        Returns:
            Dict with parameter recommendations
        """
        recommendations: Dict[str, str] = {}

        # Silhouette < 0.30 -> poor separation (skip when invalid)
        if metrics.silhouette_valid and metrics.silhouette_score < 0.30:
            if metrics.singleton_rate > 0.20:
                recommendations["eps"] = "INCREASE (too much noise)"
            else:
                recommendations["eps"] = "DECREASE (clusters too loose)"

        # Singleton rate > 0.20 → too much noise
        if metrics.singleton_rate > 0.20:
            recommendations["min_samples"] = "INCREASE (too many singletons)"

        # Singleton rate < 0.05 → too strict
        if metrics.singleton_rate < 0.05 and metrics.total_clusters > 0:
            recommendations["min_samples"] = "DECREASE (too strict)"

        # Correction rate > 0.05 → wrong boundaries
        if metrics.correction_rate > 0.05:
            recommendations["review"] = "HIGH_CORRECTION_RATE (check cluster boundaries)"

        # Grounding rate < 0.6 → clusters not useful
        if metrics.grounding_rate < 0.6 and metrics.grounded_clusters > 0:
            recommendations["temporal_weight"] = "INCREASE (add more context)"

        return recommendations


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "ClusterQualityMetrics",
    "ClusterQualityTracker",
    "WEIGHT_SILHOUETTE",
    "WEIGHT_GROUNDING",
    "WEIGHT_CORRECTION",
    "WEIGHT_SINGLETON",
    "CHANNEL_SILHOUETTE_LIVE",
    "CHANNEL_GROUNDING_LIVE",
    "CHANNEL_CORRECTION_LIVE",
    "CHANNEL_SINGLETON_LIVE",
    "ALERT_THRESHOLD_LOW",
    "CONSECUTIVE_FAILURES_FOR_ALERT",
]
