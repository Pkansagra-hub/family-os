"""
P03 Velocity Anomaly Detector — Issue 6.2.12.

Detects sudden spikes in feedback signal volume that may indicate
manipulation or bot activity by comparing recent rate to baseline.

Dossier Reference: Section 6.21.4 Detection Algorithms
K0 Integration: Uses k0/obs/metrics.py for emission
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


@dataclass(frozen=True, slots=True)
class VelocityResult:
    """
    Result of velocity spike detection.

    Attributes:
        is_spike: True if velocity exceeds threshold
        recent_rate: Signals per minute (last recent_window)
        baseline_rate: Signals per minute (last baseline_window)
        spike_multiplier: How many times recent exceeds baseline
        threshold_multiplier: Configured threshold for spike detection
    """

    is_spike: bool
    recent_rate: float
    baseline_rate: float
    spike_multiplier: float
    threshold_multiplier: float


class VelocityAnomalyDetector:
    """
    Detect sudden spikes in feedback signal volume.

    Compares recent rate (last 5 minutes by default) to baseline rate
    (last hour average). Spike detected if recent > baseline * multiplier.

    Dossier Reference: Section 6.21.4
    ADR: k010.9-capability-based-security.md
    """

    # Default configuration from dossier
    DEFAULT_SPIKE_MULTIPLIER = 10.0
    DEFAULT_RECENT_WINDOW_MINUTES = 5
    DEFAULT_BASELINE_WINDOW_MINUTES = 60
    DEFAULT_MIN_BASELINE_COUNT = 10

    def __init__(
        self,
        *,
        spike_multiplier: float = DEFAULT_SPIKE_MULTIPLIER,
        recent_window_minutes: int = DEFAULT_RECENT_WINDOW_MINUTES,
        baseline_window_minutes: int = DEFAULT_BASELINE_WINDOW_MINUTES,
        min_baseline_count: int = DEFAULT_MIN_BASELINE_COUNT,
        metrics: Optional[MetricsExporter] = None,
    ) -> None:
        """
        Initialize velocity detector.

        Args:
            spike_multiplier: Factor above baseline that triggers spike
            recent_window_minutes: Window size for recent rate calculation
            baseline_window_minutes: Window size for baseline rate calculation
            min_baseline_count: Minimum signals in baseline to avoid false positives
            metrics: Optional metrics exporter
        """
        self._spike_multiplier = spike_multiplier
        self._recent_window = recent_window_minutes * 60  # Convert to seconds
        self._baseline_window = baseline_window_minutes * 60
        self._min_baseline_count = min_baseline_count
        self._metrics = metrics

    @property
    def spike_multiplier(self) -> float:
        """Get configured spike multiplier threshold."""
        return self._spike_multiplier

    @property
    def recent_window_seconds(self) -> int:
        """Get recent window in seconds."""
        return self._recent_window

    @property
    def baseline_window_seconds(self) -> int:
        """Get baseline window in seconds."""
        return self._baseline_window

    async def detect_velocity_spike(
        self,
        space_id: str,
        *,
        user_id: Optional[str] = None,
        connection: "asyncpg.Connection",
    ) -> VelocityResult:
        """
        Detect if current velocity exceeds baseline.

        Args:
            space_id: Space to check
            user_id: Optional user for user-specific detection
            connection: Database connection

        Returns:
            VelocityResult with spike status and rate details.
        """
        now = int(time.time())
        recent_start = now - self._recent_window
        baseline_start = now - self._baseline_window

        # Get counts based on whether user_id is provided
        if user_id:
            recent_count = await self._count_signals_user(
                space_id, user_id, recent_start, connection
            )
            baseline_count = await self._count_signals_user(
                space_id, user_id, baseline_start, connection
            )
        else:
            recent_count = await self._count_signals_space(space_id, recent_start, connection)
            baseline_count = await self._count_signals_space(space_id, baseline_start, connection)

        # Calculate rates (per minute)
        recent_rate = recent_count / (self._recent_window / 60.0)
        baseline_rate = baseline_count / (self._baseline_window / 60.0)

        # Determine if spike
        is_spike = False
        spike_multiplier = 0.0

        if baseline_rate > 0 and baseline_count >= self._min_baseline_count:
            spike_multiplier = recent_rate / baseline_rate
            is_spike = spike_multiplier >= self._spike_multiplier

        # Emit metrics
        self._emit_metric(
            "p03_velocity_checks_total",
            1.0,
            is_spike=str(is_spike).lower(),
        )

        if is_spike:
            self._emit_metric(
                "p03_velocity_spikes_total",
                1.0,
                space_id=space_id[:8] if len(space_id) > 8 else space_id,
            )
            self._emit_gauge(
                "p03_velocity_spike_multiplier",
                spike_multiplier,
            )

        return VelocityResult(
            is_spike=is_spike,
            recent_rate=recent_rate,
            baseline_rate=baseline_rate,
            spike_multiplier=spike_multiplier,
            threshold_multiplier=self._spike_multiplier,
        )

    async def get_current_velocity(
        self,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> float:
        """
        Get current velocity (signals per minute) for monitoring.

        Args:
            space_id: Space to check
            connection: Database connection

        Returns:
            Current velocity in signals per minute.
        """
        result = await self.detect_velocity_spike(
            space_id,
            connection=connection,
        )
        return result.recent_rate

    async def get_velocity_trend(
        self,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> tuple[float, float, float]:
        """
        Get velocity trend data for monitoring.

        Args:
            space_id: Space to check
            connection: Database connection

        Returns:
            Tuple of (recent_rate, baseline_rate, multiplier).
        """
        result = await self.detect_velocity_spike(
            space_id,
            connection=connection,
        )
        return result.recent_rate, result.baseline_rate, result.spike_multiplier

    async def _count_signals_space(
        self,
        space_id: str,
        since: int,
        connection: "asyncpg.Connection",
    ) -> int:
        """Count signals in space since timestamp."""
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_signals
            WHERE space_id = $1 AND created_at > $2
            """,
            space_id,
            since,
        )
        return row["count"] if row else 0

    async def _count_signals_user(
        self,
        space_id: str,
        user_id: str,
        since: int,
        connection: "asyncpg.Connection",
    ) -> int:
        """Count signals for user in space since timestamp."""
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_signals
            WHERE space_id = $1 AND user_id = $2 AND created_at > $3
            """,
            space_id,
            user_id,
            since,
        )
        return row["count"] if row else 0

    def _emit_metric(self, name: str, value: float, **labels: str) -> None:
        """Emit counter metric if exporter available."""
        if self._metrics:
            self._metrics.emit(name, value, **labels)

    def _emit_gauge(self, name: str, value: float) -> None:
        """Emit gauge metric if exporter available."""
        if self._metrics:
            self._metrics.set_gauge(name, value)


def create_velocity_detector(
    *,
    spike_multiplier: float = VelocityAnomalyDetector.DEFAULT_SPIKE_MULTIPLIER,
    recent_window_minutes: int = VelocityAnomalyDetector.DEFAULT_RECENT_WINDOW_MINUTES,
    baseline_window_minutes: int = VelocityAnomalyDetector.DEFAULT_BASELINE_WINDOW_MINUTES,
    min_baseline_count: int = VelocityAnomalyDetector.DEFAULT_MIN_BASELINE_COUNT,
    metrics: Optional[MetricsExporter] = None,
) -> VelocityAnomalyDetector:
    """
    Factory for creating VelocityAnomalyDetector.

    Args:
        spike_multiplier: Factor above baseline that triggers spike (default: 10.0)
        recent_window_minutes: Window for recent rate (default: 5)
        baseline_window_minutes: Window for baseline rate (default: 60)
        min_baseline_count: Minimum baseline signals (default: 10)
        metrics: Optional metrics exporter

    Returns:
        Configured VelocityAnomalyDetector instance.
    """
    return VelocityAnomalyDetector(
        spike_multiplier=spike_multiplier,
        recent_window_minutes=recent_window_minutes,
        baseline_window_minutes=baseline_window_minutes,
        min_baseline_count=min_baseline_count,
        metrics=metrics,
    )
