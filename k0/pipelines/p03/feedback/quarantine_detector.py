"""Quarantine detection for suspicious feedback signals (Issue 6.2.10).

Detects and quarantines feedback signals based on:
- Rate limit violations
- Velocity spikes
- Anomaly patterns
- Entropy irregularities

Dossier Reference: Section 6.21 st_feedback_quarantine
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class QuarantineReason(Enum):
    """Reasons for quarantining a feedback signal."""

    RATE_LIMIT = "RATE_LIMIT"
    VELOCITY_SPIKE = "VELOCITY_SPIKE"
    ANOMALY = "ANOMALY"
    ENTROPY = "ENTROPY"


class QuarantineSeverity(Enum):
    """Severity levels for quarantined signals."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class QuarantineResult:
    """Result of quarantine operation."""

    quarantined: bool
    quarantine_id: Optional[str] = None
    reason: Optional[QuarantineReason] = None
    severity: Optional[QuarantineSeverity] = None
    auto_release_at: Optional[int] = None


# Reason → default severity mapping
REASON_SEVERITY_MAP: dict[QuarantineReason, QuarantineSeverity] = {
    QuarantineReason.RATE_LIMIT: QuarantineSeverity.LOW,
    QuarantineReason.VELOCITY_SPIKE: QuarantineSeverity.MEDIUM,
    QuarantineReason.ANOMALY: QuarantineSeverity.HIGH,
    QuarantineReason.ENTROPY: QuarantineSeverity.HIGH,
}

# Auto-release period in seconds (48 hours)
AUTO_RELEASE_SECONDS: int = 48 * 60 * 60

# Default rate limit: 100 signals per minute
DEFAULT_RATE_LIMIT_PER_MINUTE: int = 100

# Default velocity spike multiplier: 10x baseline
DEFAULT_VELOCITY_MULTIPLIER: float = 10.0


def _generate_quarantine_id() -> str:
    """Generate unique quarantine ID."""
    import uuid

    return f"quarantine_{uuid.uuid4().hex[:16]}"


class QuarantineDetector:
    """Detect and quarantine suspicious feedback signals.

    Checks signals for rate limit violations and velocity spikes,
    quarantining signals that exceed thresholds.

    Dossier Reference: Section 6.21
    """

    def __init__(
        self,
        metrics: Optional[MetricsExporter] = None,
        *,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        velocity_spike_multiplier: float = DEFAULT_VELOCITY_MULTIPLIER,
    ) -> None:
        """Initialize quarantine detector.

        Args:
            metrics: Optional metrics exporter.
            rate_limit_per_minute: Max signals per user per minute.
            velocity_spike_multiplier: Threshold for velocity spike detection.
        """
        self._metrics = metrics
        self._rate_limit = rate_limit_per_minute
        self._velocity_multiplier = velocity_spike_multiplier

    @property
    def rate_limit(self) -> int:
        """Current rate limit per minute."""
        return self._rate_limit

    @property
    def velocity_multiplier(self) -> float:
        """Current velocity spike multiplier."""
        return self._velocity_multiplier

    async def check_and_quarantine(
        self,
        signal_id: str,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> QuarantineResult:
        """Check signal for quarantine conditions and quarantine if needed.

        Args:
            signal_id: ID of the signal to check.
            space_id: Space context.
            user_id: User who created the signal.
            connection: Database connection.

        Returns:
            QuarantineResult with quarantine status and details.
        """
        # Check rate limit first (most common)
        if await self._check_rate_limit(space_id, user_id, connection=connection):
            return await self._quarantine_signal(
                signal_id,
                space_id,
                QuarantineReason.RATE_LIMIT,
                connection=connection,
            )

        # Check velocity spike (per-space)
        if await self._check_velocity_spike(space_id, connection=connection):
            return await self._quarantine_signal(
                signal_id,
                space_id,
                QuarantineReason.VELOCITY_SPIKE,
                connection=connection,
            )

        return QuarantineResult(quarantined=False)

    async def quarantine_for_anomaly(
        self,
        signal_id: str,
        space_id: str,
        *,
        reason: QuarantineReason = QuarantineReason.ANOMALY,
        severity: Optional[QuarantineSeverity] = None,
        connection: asyncpg.Connection,
    ) -> QuarantineResult:
        """Manually quarantine a signal for anomaly/entropy.

        Used by external anomaly detection.

        Args:
            signal_id: ID of the signal to quarantine.
            space_id: Space context.
            reason: Quarantine reason (ANOMALY or ENTROPY).
            severity: Override severity level.
            connection: Database connection.

        Returns:
            QuarantineResult with quarantine details.
        """
        return await self._quarantine_signal(
            signal_id,
            space_id,
            reason,
            severity=severity,
            connection=connection,
        )

    async def _check_rate_limit(
        self,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> bool:
        """Check if user has exceeded rate limit.

        Args:
            space_id: Space context.
            user_id: User to check.
            connection: Database connection.

        Returns:
            True if rate limit exceeded.
        """
        now = int(time.time())
        window_start = now - 60  # 1 minute window

        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as signal_count
            FROM st_feedback_signals
            WHERE space_id = $1
              AND user_id = $2
              AND created_at > $3
            """,
            space_id,
            user_id,
            window_start,
        )

        count = row["signal_count"] if row else 0
        exceeded = count >= self._rate_limit

        if exceeded:
            self._emit_metric("p03_rate_limit_exceeded_total", user_id=user_id[:8])

        return exceeded

    async def _check_velocity_spike(
        self,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> bool:
        """Check for sudden volume spike in feedback signals.

        Compares last 5 minutes to last hour baseline.

        Args:
            space_id: Space to check.
            connection: Database connection.

        Returns:
            True if velocity spike detected.
        """
        now = int(time.time())
        recent_window = now - (5 * 60)  # Last 5 minutes
        baseline_window = now - (60 * 60)  # Last hour

        recent = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_signals
            WHERE space_id = $1 AND created_at > $2
            """,
            space_id,
            recent_window,
        )

        baseline = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_signals
            WHERE space_id = $1 AND created_at > $2
            """,
            space_id,
            baseline_window,
        )

        recent_count = recent["count"] if recent else 0
        baseline_count = baseline["count"] if baseline else 0

        recent_rate = recent_count / 5.0  # per minute
        baseline_rate = baseline_count / 60.0  # per minute

        # Spike if 10x baseline (and baseline > 0)
        is_spike = False
        if baseline_rate > 0:
            is_spike = recent_rate > (baseline_rate * self._velocity_multiplier)

        if is_spike:
            self._emit_metric("p03_velocity_spike_total", space_id=space_id[:8])

        return is_spike

    async def _quarantine_signal(
        self,
        signal_id: str,
        space_id: str,
        reason: QuarantineReason,
        *,
        severity: Optional[QuarantineSeverity] = None,
        connection: asyncpg.Connection,
    ) -> QuarantineResult:
        """Record quarantine entry for signal.

        Args:
            signal_id: Signal to quarantine.
            space_id: Space context.
            reason: Reason for quarantine.
            severity: Override severity (or use default for reason).
            connection: Database connection.

        Returns:
            QuarantineResult with quarantine details.
        """
        severity = severity or REASON_SEVERITY_MAP[reason]
        quarantine_id = _generate_quarantine_id()
        detected_at = int(time.time())
        auto_release_at = detected_at + AUTO_RELEASE_SECONDS

        await connection.execute(
            """
            INSERT INTO st_feedback_quarantine (
                quarantine_id, signal_id, space_id, reason, severity,
                detected_at, auto_release_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            quarantine_id,
            signal_id,
            space_id,
            reason.value,
            severity.value,
            detected_at,
            auto_release_at,
        )

        self._emit_metric(
            "p03_quarantine_signals_total",
            reason=reason.value,
            severity=severity.value,
        )

        # Alert on high severity
        if severity == QuarantineSeverity.HIGH:
            self._emit_metric(
                "p03_quarantine_high_severity_total",
                reason=reason.value,
            )

        return QuarantineResult(
            quarantined=True,
            quarantine_id=quarantine_id,
            reason=reason,
            severity=severity,
            auto_release_at=auto_release_at,
        )

    async def release_signal(
        self,
        quarantine_id: str,
        reviewer_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> bool:
        """Release a quarantined signal.

        Args:
            quarantine_id: ID of quarantine record.
            reviewer_id: ID of reviewer releasing signal.
            connection: Database connection.

        Returns:
            True if signal was released.
        """
        reviewed_at = int(time.time())

        result = await connection.execute(
            """
            UPDATE st_feedback_quarantine
            SET reviewed_at = $1,
                reviewed_by = $2,
                decision = 'RELEASE'
            WHERE quarantine_id = $3
              AND decision IS NULL
            """,
            reviewed_at,
            reviewer_id,
            quarantine_id,
        )

        released = result == "UPDATE 1"
        if released:
            self._emit_metric("p03_quarantine_released_total")

        return released

    async def discard_signal(
        self,
        quarantine_id: str,
        reviewer_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> bool:
        """Discard a quarantined signal.

        Args:
            quarantine_id: ID of quarantine record.
            reviewer_id: ID of reviewer discarding signal.
            connection: Database connection.

        Returns:
            True if signal was discarded.
        """
        reviewed_at = int(time.time())

        result = await connection.execute(
            """
            UPDATE st_feedback_quarantine
            SET reviewed_at = $1,
                reviewed_by = $2,
                decision = 'DISCARD'
            WHERE quarantine_id = $3
              AND decision IS NULL
            """,
            reviewed_at,
            reviewer_id,
            quarantine_id,
        )

        discarded = result == "UPDATE 1"
        if discarded:
            self._emit_metric("p03_quarantine_discarded_total")

        return discarded

    async def get_pending_count(
        self,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> int:
        """Get count of pending quarantine reviews.

        Args:
            space_id: Space to check.
            connection: Database connection.

        Returns:
            Count of pending quarantine records.
        """
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE space_id = $1 AND decision IS NULL
            """,
            space_id,
        )
        return row["count"] if row else 0

    async def process_auto_releases(
        self,
        *,
        connection: asyncpg.Connection,
    ) -> int:
        """Process auto-release for expired quarantines.

        Releases quarantines with LOW severity past their auto_release_at time.

        Args:
            connection: Database connection.

        Returns:
            Count of auto-released records.
        """
        now = int(time.time())

        result = await connection.execute(
            """
            UPDATE st_feedback_quarantine
            SET reviewed_at = $1,
                reviewed_by = 'SYSTEM_AUTO_RELEASE',
                decision = 'RELEASE'
            WHERE auto_release_at <= $1
              AND decision IS NULL
              AND severity = 'LOW'
            """,
            now,
        )

        # Parse count from result like "UPDATE 5"
        count = 0
        if result and result.startswith("UPDATE "):
            try:
                count = int(result.split()[1])
            except (IndexError, ValueError):
                pass

        if count > 0:
            self._emit_metric("p03_quarantine_auto_released_total", count=str(count))

        return count

    def _emit_metric(self, name: str, **labels: str) -> None:
        """Emit metric with labels."""
        if self._metrics is not None:
            self._metrics.emit(name, 1.0, **labels)


def create_quarantine_detector(
    metrics: Optional[MetricsExporter] = None,
    *,
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
    velocity_spike_multiplier: float = DEFAULT_VELOCITY_MULTIPLIER,
) -> QuarantineDetector:
    """Factory function to create QuarantineDetector.

    Args:
        metrics: Optional metrics exporter.
        rate_limit_per_minute: Max signals per user per minute.
        velocity_spike_multiplier: Threshold for velocity spike detection.

    Returns:
        Configured QuarantineDetector instance.
    """
    return QuarantineDetector(
        metrics=metrics,
        rate_limit_per_minute=rate_limit_per_minute,
        velocity_spike_multiplier=velocity_spike_multiplier,
    )
