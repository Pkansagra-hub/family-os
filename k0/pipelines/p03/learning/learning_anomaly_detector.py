"""
P03 Learning Anomaly Detector.

Issue 6.2.17: P03LearningAnomalyDetector

Detect anomalies in P03 learning parameters:
- Parameter drift (> 20% change in 24h)
- Contradictory signals (opposing signals for same entity)
- Formula regression (quality drop > 10%)

Dossier Reference: Section 14.9 P03 Learning Anomaly Detection
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Set

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


class LearningAnomalyType(Enum):
    """Types of learning anomalies."""

    PARAMETER_DRIFT = "PARAMETER_DRIFT"
    CONTRADICTORY_SIGNALS = "CONTRADICTORY_SIGNALS"
    FORMULA_REGRESSION = "FORMULA_REGRESSION"
    QUALITY_DEGRADATION = "QUALITY_DEGRADATION"


@dataclass(frozen=True)
class FeedbackSignal:
    """Feedback signal for anomaly analysis."""

    signal_id: str
    entity_id: str
    feedback_type: str
    salience_delta: Optional[float] = None
    created_at: int = 0


@dataclass
class LearningAnomalyResult:
    """Result of learning anomaly detection.

    Captures the anomaly type, affected parameters/entities,
    and any action taken by the detector.
    """

    is_anomalous: bool
    anomaly_type: Optional[LearningAnomalyType] = None
    param_key: Optional[str] = None
    entity_id: Optional[str] = None
    details: Dict = field(default_factory=dict)
    action_taken: Optional[str] = None

    @property
    def requires_review(self) -> bool:
        """Check if this anomaly requires manual review."""
        if not self.is_anomalous:
            return False
        return self.action_taken in ("FLAGGED_FOR_REVIEW", "LEARNING_PAUSED")


class P03LearningAnomalyDetector:
    """
    Detect anomalies in P03 learning parameters.

    Checks for:
    - Parameter drift (> 20% change in 24h) -> Pause learning, alert
    - Contradictory signals (opposing signals for same entity) -> Flag for review
    - Formula regression (quality drop > 10%) -> Auto-rollback

    Dossier Reference: Section 14.9
    """

    # Default thresholds from dossier
    DEFAULT_DRIFT_THRESHOLD = 0.20  # 20% change
    DEFAULT_QUALITY_DROP_THRESHOLD = 0.10  # 10% drop
    DEFAULT_MIN_SIGNALS_FOR_CONTRADICTION = 2

    def __init__(
        self,
        *,
        drift_threshold: float = DEFAULT_DRIFT_THRESHOLD,
        quality_drop_threshold: float = DEFAULT_QUALITY_DROP_THRESHOLD,
        min_signals_for_contradiction: int = DEFAULT_MIN_SIGNALS_FOR_CONTRADICTION,
        metrics: Optional["MetricsExporter"] = None,
    ):
        """Initialize the learning anomaly detector.

        Args:
            drift_threshold: Maximum allowed parameter change in 24h (0.0-1.0)
            quality_drop_threshold: Maximum allowed quality drop before rollback
            min_signals_for_contradiction: Minimum signals needed to detect contradictions
            metrics: Optional metrics exporter for observability
        """
        self._drift_threshold = drift_threshold
        self._quality_drop_threshold = quality_drop_threshold
        self._min_signals = min_signals_for_contradiction
        self._metrics = metrics
        self._paused_params: Set[str] = set()

    @property
    def drift_threshold(self) -> float:
        """Get the drift threshold."""
        return self._drift_threshold

    @property
    def quality_drop_threshold(self) -> float:
        """Get the quality drop threshold."""
        return self._quality_drop_threshold

    async def check_parameter_drift(
        self,
        param_key: str,
        space_id: str,
        current_value: float,
        *,
        connection: "asyncpg.Connection",
    ) -> LearningAnomalyResult:
        """
        Check if parameter changed too quickly (> 20% in 24h).

        Args:
            param_key: Parameter identifier
            space_id: Space context
            current_value: New proposed value
            connection: Database connection

        Returns:
            LearningAnomalyResult with drift detection status.
        """
        now = int(time.time())
        yesterday = now - 86400  # 24 hours ago

        # Get value from 24h ago
        row = await connection.fetchrow(
            """
            SELECT current_value
            FROM st_learned_weights
            WHERE param_key = $1
              AND space_id = $2
              AND updated_at <= $3
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            param_key,
            space_id,
            yesterday * 1000,  # Convert to ms
        )

        if not row or row["current_value"] is None or row["current_value"] == 0:
            return LearningAnomalyResult(is_anomalous=False)

        previous_value = float(row["current_value"])

        # Calculate drift percentage
        if abs(previous_value) < 1e-10:
            # Avoid division by zero
            return LearningAnomalyResult(is_anomalous=False)

        drift_pct = abs(current_value - previous_value) / abs(previous_value)

        if drift_pct > self._drift_threshold:
            # Pause learning for this parameter
            await self._pause_learning(param_key, space_id, connection=connection)

            self._emit_metric(
                "p03_learning_anomaly_detected_total",
                1.0,
                type=LearningAnomalyType.PARAMETER_DRIFT.value,
            )

            return LearningAnomalyResult(
                is_anomalous=True,
                anomaly_type=LearningAnomalyType.PARAMETER_DRIFT,
                param_key=param_key,
                details={
                    "previous_value": previous_value,
                    "current_value": current_value,
                    "drift_pct": drift_pct,
                    "threshold": self._drift_threshold,
                },
                action_taken="LEARNING_PAUSED",
            )

        return LearningAnomalyResult(is_anomalous=False)

    async def check_contradictory_signals(
        self,
        entity_id: str,
        signals: List[FeedbackSignal],
    ) -> LearningAnomalyResult:
        """
        Detect opposing signals for same entity.

        Identifies when the same entity receives conflicting feedback
        (positive and negative salience deltas) within the signal window.

        Args:
            entity_id: Entity being updated
            signals: Recent signals for this entity

        Returns:
            LearningAnomalyResult with contradiction status.
        """
        if len(signals) < self._min_signals:
            return LearningAnomalyResult(is_anomalous=False)

        # Group by feedback type
        by_type: Dict[str, List[FeedbackSignal]] = defaultdict(list)
        for sig in signals:
            by_type[sig.feedback_type].append(sig)

        # Check for contradictions within each type
        for sig_type, type_signals in by_type.items():
            deltas = [s.salience_delta for s in type_signals if s.salience_delta is not None]

            if len(deltas) >= self._min_signals:
                # Check if signals have opposite signs
                has_positive = any(d > 0 for d in deltas)
                has_negative = any(d < 0 for d in deltas)

                if has_positive and has_negative:
                    self._emit_metric(
                        "p03_learning_anomaly_detected_total",
                        1.0,
                        type=LearningAnomalyType.CONTRADICTORY_SIGNALS.value,
                    )

                    return LearningAnomalyResult(
                        is_anomalous=True,
                        anomaly_type=LearningAnomalyType.CONTRADICTORY_SIGNALS,
                        entity_id=entity_id,
                        details={
                            "feedback_type": sig_type,
                            "signal_count": len(type_signals),
                            "positive_deltas": [d for d in deltas if d > 0],
                            "negative_deltas": [d for d in deltas if d < 0],
                        },
                        action_taken="FLAGGED_FOR_REVIEW",
                    )

        return LearningAnomalyResult(is_anomalous=False)

    async def check_formula_regression(
        self,
        formula_name: str,
        space_id: str,
        current_quality: float,
        *,
        connection: "asyncpg.Connection",
    ) -> LearningAnomalyResult:
        """
        Check if formula quality has regressed significantly.

        Compares current quality metric against 7-day rolling average.
        Triggers auto-rollback if drop exceeds threshold.

        Args:
            formula_name: Formula being monitored
            space_id: Space context
            current_quality: Current quality metric (0-1)
            connection: Database connection

        Returns:
            LearningAnomalyResult with regression status.
        """
        now = int(time.time())
        week_ago = (now - 7 * 86400) * 1000  # 7 days in ms

        # Get previous quality (7-day rolling average)
        row = await connection.fetchrow(
            """
            SELECT AVG(quality_metric) as avg_quality
            FROM st_formula_quality_history
            WHERE formula_name = $1
              AND space_id = $2
              AND recorded_at > $3
            """,
            formula_name,
            space_id,
            week_ago,
        )

        if not row or row["avg_quality"] is None:
            return LearningAnomalyResult(is_anomalous=False)

        previous_quality = float(row["avg_quality"])

        # Handle edge case where previous_quality is 0
        if previous_quality < 1e-10:
            return LearningAnomalyResult(is_anomalous=False)

        quality_drop = (previous_quality - current_quality) / previous_quality

        if quality_drop > self._quality_drop_threshold:
            # Trigger auto-rollback
            await self._trigger_formula_rollback(
                formula_name,
                space_id,
                reason=f"Quality regression: {quality_drop:.1%}",
                connection=connection,
            )

            self._emit_metric(
                "p03_learning_anomaly_detected_total",
                1.0,
                type=LearningAnomalyType.FORMULA_REGRESSION.value,
            )

            self._emit_metric(
                "p03_formula_auto_rollbacks_total",
                1.0,
                formula=formula_name,
            )

            return LearningAnomalyResult(
                is_anomalous=True,
                anomaly_type=LearningAnomalyType.FORMULA_REGRESSION,
                details={
                    "formula_name": formula_name,
                    "previous_quality": previous_quality,
                    "current_quality": current_quality,
                    "quality_drop": quality_drop,
                    "threshold": self._quality_drop_threshold,
                },
                action_taken="AUTO_ROLLBACK",
            )

        return LearningAnomalyResult(is_anomalous=False)

    async def check_all(
        self,
        param_key: str,
        space_id: str,
        current_value: float,
        entity_id: str,
        signals: List[FeedbackSignal],
        formula_name: str,
        current_quality: float,
        *,
        connection: "asyncpg.Connection",
    ) -> List[LearningAnomalyResult]:
        """
        Run all anomaly checks and return all detected anomalies.

        Args:
            param_key: Parameter to check for drift
            space_id: Space context
            current_value: Current parameter value
            entity_id: Entity to check for contradictions
            signals: Recent feedback signals
            formula_name: Formula to check for regression
            current_quality: Current formula quality
            connection: Database connection

        Returns:
            List of all detected anomalies (may be empty).
        """
        results = []

        # Check parameter drift
        drift_result = await self.check_parameter_drift(
            param_key, space_id, current_value, connection=connection
        )
        if drift_result.is_anomalous:
            results.append(drift_result)

        # Check contradictory signals
        contradiction_result = await self.check_contradictory_signals(entity_id, signals)
        if contradiction_result.is_anomalous:
            results.append(contradiction_result)

        # Check formula regression
        regression_result = await self.check_formula_regression(
            formula_name, space_id, current_quality, connection=connection
        )
        if regression_result.is_anomalous:
            results.append(regression_result)

        return results

    async def _pause_learning(
        self,
        param_key: str,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> None:
        """Pause learning for a parameter due to anomaly detection."""
        self._paused_params.add(f"{space_id}:{param_key}")

        await connection.execute(
            """
            UPDATE st_learned_weights
            SET learning_paused = TRUE,
                paused_at = $1,
                paused_reason = 'ANOMALY_DETECTED'
            WHERE param_key = $2 AND space_id = $3
            """,
            int(time.time() * 1000),
            param_key,
            space_id,
        )

        self._emit_metric(
            "p03_learning_paused_total",
            1.0,
            param_key=param_key[:20],
        )

    async def resume_learning(
        self,
        param_key: str,
        space_id: str,
        reviewer_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> bool:
        """
        Resume learning after manual review.

        Args:
            param_key: Parameter to resume
            space_id: Space context
            reviewer_id: ID of reviewer approving resume
            connection: Database connection

        Returns:
            True if learning was resumed, False if not paused.
        """
        key = f"{space_id}:{param_key}"
        if key in self._paused_params:
            self._paused_params.remove(key)

        result = await connection.execute(
            """
            UPDATE st_learned_weights
            SET learning_paused = FALSE,
                paused_at = NULL,
                paused_reason = NULL,
                resumed_by = $1,
                resumed_at = $2
            WHERE param_key = $3 AND space_id = $4
              AND learning_paused = TRUE
            """,
            reviewer_id,
            int(time.time() * 1000),
            param_key,
            space_id,
        )

        if result != "UPDATE 0":
            self._emit_metric(
                "p03_learning_resumed_total",
                1.0,
                param_key=param_key[:20],
            )
            return True
        return False

    def is_learning_paused(self, param_key: str, space_id: str) -> bool:
        """Check if learning is currently paused for a parameter."""
        return f"{space_id}:{param_key}" in self._paused_params

    def get_paused_params(self) -> Set[str]:
        """Get all currently paused parameter keys."""
        return self._paused_params.copy()

    async def _trigger_formula_rollback(
        self,
        formula_name: str,
        space_id: str,
        reason: str,
        *,
        connection: "asyncpg.Connection",
    ) -> None:
        """
        Trigger auto-rollback for formula parameters.

        Records the rollback event and reverts parameters to previous version.
        """
        # Record rollback event
        await connection.execute(
            """
            INSERT INTO st_formula_rollback_log (
                formula_name, space_id, reason, rolled_back_at
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING
            """,
            formula_name,
            space_id,
            reason,
            int(time.time() * 1000),
        )

        # Revert to previous version (simplified - actual implementation
        # would restore from version history)
        await connection.execute(
            """
            UPDATE st_learned_weights
            SET learning_paused = TRUE,
                paused_reason = $1
            WHERE formula_name = $2 AND space_id = $3
            """,
            f"AUTO_ROLLBACK: {reason}",
            formula_name,
            space_id,
        )

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        """Emit a metric if metrics exporter is configured."""
        if self._metrics:
            self._metrics.emit(name, value, **labels)


def create_learning_anomaly_detector(
    *,
    drift_threshold: float = P03LearningAnomalyDetector.DEFAULT_DRIFT_THRESHOLD,
    quality_drop_threshold: float = P03LearningAnomalyDetector.DEFAULT_QUALITY_DROP_THRESHOLD,
    min_signals_for_contradiction: int = P03LearningAnomalyDetector.DEFAULT_MIN_SIGNALS_FOR_CONTRADICTION,
    metrics: Optional["MetricsExporter"] = None,
) -> P03LearningAnomalyDetector:
    """Factory function for P03LearningAnomalyDetector.

    Args:
        drift_threshold: Maximum allowed parameter change in 24h (default: 0.20)
        quality_drop_threshold: Maximum allowed quality drop (default: 0.10)
        min_signals_for_contradiction: Minimum signals for contradiction check
        metrics: Optional metrics exporter

    Returns:
        Configured P03LearningAnomalyDetector instance
    """
    return P03LearningAnomalyDetector(
        drift_threshold=drift_threshold,
        quality_drop_threshold=quality_drop_threshold,
        min_signals_for_contradiction=min_signals_for_contradiction,
        metrics=metrics,
    )
