"""P03 Quarantine Metrics.

Comprehensive metrics for the feedback quarantine system to enable
monitoring, alerting, and operational visibility.

Issue 6.2.19: Quarantine Metrics Implementation
Dossier Reference: Section 6.21.5 Metrics & Monitoring
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


@dataclass
class QuarantineStats:
    """Comprehensive quarantine statistics."""

    by_reason: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_decision: Dict[str, int] = field(default_factory=dict)
    pending_count: int = 0
    avg_review_latency_seconds: float = 0.0
    auto_release_count: int = 0
    total_quarantined: int = 0


class QuarantineMetricsCollector:
    """
    Collect and emit quarantine-related metrics.

    Provides both event-driven metrics (counters) and
    scheduled gauge updates for pending reviews.

    Metrics Emitted:
    | Metric | Type | Labels | Description |
    |--------|------|--------|-------------|
    | p03_quarantine_signals_total | counter | reason, severity | Signals quarantined |
    | p03_quarantine_decisions_total | counter | decision | Review decisions |
    | p03_quarantine_auto_released_total | counter | - | Auto-released signals |
    | p03_quarantine_pending_reviews | gauge | severity | Pending review count |
    | p03_quarantine_high_severity_total | counter | reason | High severity quarantines |
    | p03_quarantine_review_latency_seconds | histogram | decision | Review latency |

    Dossier Reference: Section 6.21.5
    """

    # Metric names
    SIGNALS_TOTAL = "p03_quarantine_signals_total"
    DECISIONS_TOTAL = "p03_quarantine_decisions_total"
    AUTO_RELEASED_TOTAL = "p03_quarantine_auto_released_total"
    PENDING_REVIEWS = "p03_quarantine_pending_reviews"
    HIGH_SEVERITY_TOTAL = "p03_quarantine_high_severity_total"
    REVIEW_LATENCY = "p03_quarantine_review_latency_seconds"
    RATE_LIMIT_CHECKS = "p03_rate_limit_checks_total"
    RATE_LIMIT_EXCEEDED = "p03_rate_limit_exceeded_total"
    VELOCITY_CHECKS = "p03_velocity_checks_total"
    VELOCITY_SPIKES = "p03_velocity_spikes_total"
    VELOCITY_MULTIPLIER = "p03_velocity_spike_multiplier"
    ANOMALY_CHECKS = "p03_anomaly_checks_total"
    ANOMALIES_DETECTED = "p03_anomalies_detected_total"

    def __init__(
        self,
        metrics: Optional["MetricsExporter"] = None,
    ) -> None:
        self._metrics = metrics

    def record_quarantine(
        self,
        reason: str,
        severity: str,
    ) -> None:
        """
        Record a quarantine event.

        Args:
            reason: Quarantine reason (RATE_LIMIT, VELOCITY_SPIKE, ANOMALY, ENTROPY)
            severity: Severity level (LOW, MEDIUM, HIGH)
        """
        if self._metrics:
            self._metrics.counter(
                self.SIGNALS_TOTAL,
                1,
                reason=reason,
                severity=severity,
            )

            if severity == "HIGH":
                self._metrics.counter(
                    self.HIGH_SEVERITY_TOTAL,
                    1,
                    reason=reason,
                )

    def record_decision(
        self,
        decision: str,
        *,
        review_latency_seconds: Optional[float] = None,
    ) -> None:
        """
        Record a review decision.

        Args:
            decision: Decision made (RELEASE, DISCARD, AUTO_RELEASE)
            review_latency_seconds: Time from quarantine to decision
        """
        if self._metrics:
            self._metrics.counter(
                self.DECISIONS_TOTAL,
                1,
                decision=decision,
            )

            if decision == "AUTO_RELEASE":
                self._metrics.counter(
                    self.AUTO_RELEASED_TOTAL,
                    1,
                )

            if review_latency_seconds is not None:
                self._metrics.histogram(
                    self.REVIEW_LATENCY,
                    review_latency_seconds,
                    decision=decision,
                )

    def record_rate_limit_check(
        self,
        exceeded: bool,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Record a rate limit check.

        Args:
            exceeded: Whether the rate limit was exceeded
            user_id: User who triggered the check
        """
        if self._metrics:
            self._metrics.counter(
                self.RATE_LIMIT_CHECKS,
                1,
                exceeded=str(exceeded).lower(),
            )

            if exceeded and user_id:
                self._metrics.counter(
                    self.RATE_LIMIT_EXCEEDED,
                    1,
                    user_id=user_id[:8],  # Truncate for cardinality
                )

    def record_velocity_check(
        self,
        is_spike: bool,
        space_id: Optional[str] = None,
        spike_multiplier: Optional[float] = None,
    ) -> None:
        """
        Record a velocity check.

        Args:
            is_spike: Whether a velocity spike was detected
            space_id: Space being checked
            spike_multiplier: How many times over baseline
        """
        if self._metrics:
            self._metrics.counter(
                self.VELOCITY_CHECKS,
                1,
                is_spike=str(is_spike).lower(),
            )

            if is_spike:
                if space_id:
                    self._metrics.counter(
                        self.VELOCITY_SPIKES,
                        1,
                        space_id=space_id[:8],
                    )

                if spike_multiplier is not None:
                    self._metrics.gauge(
                        self.VELOCITY_MULTIPLIER,
                        spike_multiplier,
                    )

    def record_anomaly_check(
        self,
        is_anomalous: bool,
        anomaly_type: Optional[str] = None,
    ) -> None:
        """
        Record an anomaly check.

        Args:
            is_anomalous: Whether an anomaly was detected
            anomaly_type: Type of anomaly detected
        """
        if self._metrics:
            self._metrics.counter(
                self.ANOMALY_CHECKS,
                1,
                is_anomalous=str(is_anomalous).lower(),
            )

            if is_anomalous and anomaly_type:
                self._metrics.counter(
                    self.ANOMALIES_DETECTED,
                    1,
                    type=anomaly_type,
                )

    async def update_pending_gauge(
        self,
        *,
        connection: "asyncpg.Connection",
    ) -> Dict[str, int]:
        """
        Update pending reviews gauge (called periodically).

        Args:
            connection: Database connection

        Returns:
            Dict of counts by severity for monitoring.
        """
        rows = await connection.fetch(
            """
            SELECT severity, COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE decision IS NULL
            GROUP BY severity
            """
        )

        counts: Dict[str, int] = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
        for row in rows:
            severity = row["severity"]
            count = row["count"]
            counts[severity] = count

            if self._metrics:
                self._metrics.gauge(
                    self.PENDING_REVIEWS,
                    count,
                    severity=severity,
                )

        return counts

    async def get_quarantine_stats(
        self,
        *,
        connection: "asyncpg.Connection",
        window_hours: int = 24,
    ) -> QuarantineStats:
        """
        Get comprehensive quarantine statistics.

        Args:
            connection: Database connection
            window_hours: Time window for statistics (default: 24h)

        Returns:
            QuarantineStats with all metrics.
        """
        now = int(time.time())
        window_start = now - (window_hours * 3600)

        # Total quarantined in window
        total_row = await connection.fetchrow(
            """
            SELECT COUNT(*) as total
            FROM st_feedback_quarantine
            WHERE detected_at >= $1
            """,
            window_start,
        )
        total_quarantined = total_row["total"] if total_row else 0

        # By reason
        reason_rows = await connection.fetch(
            """
            SELECT reason, COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE detected_at >= $1
            GROUP BY reason
            """,
            window_start,
        )
        by_reason = {r["reason"]: r["count"] for r in reason_rows}

        # By severity
        severity_rows = await connection.fetch(
            """
            SELECT severity, COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE detected_at >= $1
            GROUP BY severity
            """,
            window_start,
        )
        by_severity = {r["severity"]: r["count"] for r in severity_rows}

        # By decision
        decision_rows = await connection.fetch(
            """
            SELECT decision, COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE decision IS NOT NULL
              AND detected_at >= $1
            GROUP BY decision
            """,
            window_start,
        )
        by_decision = {d["decision"]: d["count"] for d in decision_rows}

        # Average review latency
        latency_row = await connection.fetchrow(
            """
            SELECT AVG(reviewed_at - detected_at) as avg_latency_seconds
            FROM st_feedback_quarantine
            WHERE reviewed_at IS NOT NULL
              AND detected_at >= $1
            """,
            window_start,
        )
        avg_latency = latency_row["avg_latency_seconds"] if latency_row else 0
        avg_latency = avg_latency or 0

        # Pending count
        pending_counts = await self.update_pending_gauge(connection=connection)
        pending_total = sum(pending_counts.values())

        # Auto-release count
        auto_row = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE reviewed_by = 'AUTO'
              AND detected_at >= $1
            """,
            window_start,
        )
        auto_release_count = auto_row["count"] if auto_row else 0

        return QuarantineStats(
            by_reason=by_reason,
            by_severity=by_severity,
            by_decision=by_decision,
            pending_count=pending_total,
            avg_review_latency_seconds=float(avg_latency),
            auto_release_count=auto_release_count,
            total_quarantined=total_quarantined,
        )

    async def get_rate_limit_stats(
        self,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
        window_minutes: int = 60,
    ) -> Dict[str, object]:
        """
        Get rate limiting statistics for a space.

        Args:
            space_id: Space to check
            connection: Database connection
            window_minutes: Time window (default: 60 min)

        Returns:
            Dict with rate limit statistics.
        """
        now = int(time.time())
        window_start = now - (window_minutes * 60)

        # Get top users by signal count
        top_users = await connection.fetch(
            """
            SELECT user_id, COUNT(*) as signal_count
            FROM st_feedback_signals
            WHERE space_id = $1
              AND created_at >= $2
            GROUP BY user_id
            ORDER BY signal_count DESC
            LIMIT 10
            """,
            space_id,
            window_start,
        )

        # Get quarantined count
        quarantined_row = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE space_id = $1
              AND reason = 'RATE_LIMIT'
              AND detected_at >= $2
            """,
            space_id,
            window_start,
        )
        quarantined_count = quarantined_row["count"] if quarantined_row else 0

        return {
            "space_id": space_id,
            "window_minutes": window_minutes,
            "top_users": [
                {"user_id": u["user_id"][:8], "count": u["signal_count"]} for u in top_users
            ],
            "rate_limited_count": quarantined_count,
        }


class QuarantineMetricsJob:
    """
    Scheduled job to update quarantine gauge metrics.

    Runs periodically to update pending reviews gauges
    and emit summary statistics.
    """

    JOB_NAME = "p03_quarantine_metrics"
    DEFAULT_INTERVAL_SECONDS = 60  # 1 minute

    def __init__(
        self,
        collector: QuarantineMetricsCollector,
    ) -> None:
        self._collector = collector

    async def run(
        self,
        *,
        connection: "asyncpg.Connection",
    ) -> Dict[str, int]:
        """
        Execute the metrics collection job.

        Args:
            connection: Database connection

        Returns:
            Dict of pending counts by severity.
        """
        return await self._collector.update_pending_gauge(connection=connection)


# Alert threshold constants from dossier
QUARANTINE_ALERT_THRESHOLDS = {
    "high_rate_warning": 10,  # > 10 signals/min
    "high_severity_spike": 1,  # > 1 HIGH severity / 5 min
    "pending_high_reviews": 10,  # > 10 HIGH pending for 15 min
}


# Convenience functions for direct emission


def emit_quarantine_metric(
    metrics: "MetricsExporter",
    reason: str,
    severity: str,
) -> None:
    """
    Emit quarantine metric (convenience function).

    Args:
        metrics: Metrics exporter
        reason: Quarantine reason
        severity: Severity level
    """
    collector = QuarantineMetricsCollector(metrics)
    collector.record_quarantine(reason, severity)


def emit_decision_metric(
    metrics: "MetricsExporter",
    decision: str,
    review_latency_seconds: Optional[float] = None,
) -> None:
    """
    Emit decision metric (convenience function).

    Args:
        metrics: Metrics exporter
        decision: Decision made
        review_latency_seconds: Time from quarantine to decision
    """
    collector = QuarantineMetricsCollector(metrics)
    collector.record_decision(decision, review_latency_seconds=review_latency_seconds)


def create_quarantine_metrics_collector(
    metrics: Optional["MetricsExporter"] = None,
) -> QuarantineMetricsCollector:
    """
    Factory for QuarantineMetricsCollector.

    Args:
        metrics: Optional metrics exporter

    Returns:
        Configured QuarantineMetricsCollector instance.
    """
    return QuarantineMetricsCollector(metrics)


def create_quarantine_metrics_job(
    metrics: Optional["MetricsExporter"] = None,
) -> QuarantineMetricsJob:
    """
    Factory for QuarantineMetricsJob.

    Args:
        metrics: Optional metrics exporter

    Returns:
        Configured QuarantineMetricsJob instance.
    """
    collector = create_quarantine_metrics_collector(metrics)
    return QuarantineMetricsJob(collector)
