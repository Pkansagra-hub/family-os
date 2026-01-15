"""
P03 Quarantine Auto-Release Job — Issue 6.2.14.

Scheduled job that automatically releases quarantined signals after
48h retention period expires, allowing them to be processed normally.

Dossier Reference: Section 6.21.3 Auto-Release
K0 Integration: Uses k0/obs/metrics.py for emission, k0/scheduler for job scheduling
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter
    from k0.obs.tracing import TracerFactory


@dataclass(slots=True)
class AutoReleaseResult:
    """
    Result of auto-release job execution.

    Attributes:
        signals_released: Number of signals successfully released
        signals_failed: Number of signals that failed to release
        duration_ms: Total job execution time in milliseconds
        errors: List of error messages for failed releases
    """

    signals_released: int
    signals_failed: int
    duration_ms: float
    errors: list[str] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        """Get total signals processed."""
        return self.signals_released + self.signals_failed

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_processed == 0:
            return 100.0
        return (self.signals_released / self.total_processed) * 100.0


class QuarantineAutoReleaseJob:
    """
    Automatically release quarantined signals after retention period.

    Runs periodically to release signals where:
    - auto_release_at <= current_time
    - decision IS NULL (not manually reviewed)

    Updates:
    - st_feedback_quarantine: decision='RELEASE', reviewed_by='AUTO'
    - st_feedback_signals: quarantine_status='RELEASED'

    Dossier Reference: Section 6.21.3
    ADR: k010.9-capability-based-security.md
    """

    JOB_NAME = "p03_quarantine_auto_release"
    DEFAULT_BATCH_SIZE = 100
    DEFAULT_INTERVAL_SECONDS = 900  # 15 minutes
    REVIEWER_ID = "AUTO"
    DECISION_RELEASE = "RELEASE"
    STATUS_RELEASED = "RELEASED"

    def __init__(
        self,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        metrics: Optional[MetricsExporter] = None,
        tracer: Optional[TracerFactory] = None,
    ) -> None:
        """
        Initialize auto-release job.

        Args:
            batch_size: Number of signals to process per batch
            metrics: Optional metrics exporter
            tracer: Optional tracer factory
        """
        self._batch_size = batch_size
        self._metrics = metrics
        self._tracer = tracer

    @property
    def batch_size(self) -> int:
        """Get configured batch size."""
        return self._batch_size

    async def run(
        self,
        *,
        connection: "asyncpg.Connection",
    ) -> AutoReleaseResult:
        """
        Execute auto-release job.

        Processes all signals past their auto_release_at time in batches.

        Args:
            connection: Database connection

        Returns:
            AutoReleaseResult with release counts and timing.
        """
        start_time = time.monotonic()
        released_count = 0
        failed_count = 0
        errors: list[str] = []

        now = int(time.time())

        # Process in batches until no more ready signals
        while True:
            ready_signals = await self._fetch_ready_signals(now, connection)

            if not ready_signals:
                break

            for signal in ready_signals:
                try:
                    await self._release_signal(
                        quarantine_id=signal["quarantine_id"],
                        signal_id=signal["signal_id"],
                        reviewed_at=now,
                        connection=connection,
                    )
                    released_count += 1
                except Exception as e:
                    failed_count += 1
                    errors.append(f"Failed to release {signal['quarantine_id']}: {e}")

        duration_ms = (time.monotonic() - start_time) * 1000

        # Emit metrics
        self._emit_metrics(released_count, failed_count, duration_ms)

        return AutoReleaseResult(
            signals_released=released_count,
            signals_failed=failed_count,
            duration_ms=duration_ms,
            errors=errors,
        )

    async def run_single(
        self,
        quarantine_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> bool:
        """
        Force release a single quarantine entry (for testing/admin).

        Args:
            quarantine_id: ID of quarantine entry to release
            connection: Database connection

        Returns:
            True if released, False if not found or already reviewed.
        """
        now = int(time.time())

        # Get signal details
        row = await connection.fetchrow(
            """
            SELECT quarantine_id, signal_id
            FROM st_feedback_quarantine
            WHERE quarantine_id = $1 AND decision IS NULL
            """,
            quarantine_id,
        )

        if not row:
            return False

        await self._release_signal(
            quarantine_id=row["quarantine_id"],
            signal_id=row["signal_id"],
            reviewed_at=now,
            connection=connection,
        )
        return True

    async def get_pending_count(
        self,
        *,
        connection: "asyncpg.Connection",
    ) -> int:
        """
        Get count of signals pending auto-release.

        Args:
            connection: Database connection

        Returns:
            Count of signals ready for auto-release.
        """
        now = int(time.time())
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE decision IS NULL AND auto_release_at <= $1
            """,
            now,
        )
        return row["count"] if row else 0

    async def get_upcoming_count(
        self,
        hours: int = 24,
        *,
        connection: "asyncpg.Connection",
    ) -> int:
        """
        Get count of signals scheduled for release in next N hours.

        Args:
            hours: Lookahead window in hours
            connection: Database connection

        Returns:
            Count of signals scheduled for release.
        """
        now = int(time.time())
        future = now + (hours * 3600)
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE decision IS NULL
              AND auto_release_at > $1
              AND auto_release_at <= $2
            """,
            now,
            future,
        )
        return row["count"] if row else 0

    async def _fetch_ready_signals(
        self,
        now: int,
        connection: "asyncpg.Connection",
    ) -> list:
        """Fetch batch of signals ready for auto-release."""
        return await connection.fetch(
            """
            SELECT quarantine_id, signal_id, space_id
            FROM st_feedback_quarantine
            WHERE decision IS NULL
              AND auto_release_at <= $1
            ORDER BY auto_release_at ASC
            LIMIT $2
            """,
            now,
            self._batch_size,
        )

    async def _release_signal(
        self,
        quarantine_id: str,
        signal_id: str,
        reviewed_at: int,
        *,
        connection: "asyncpg.Connection",
    ) -> None:
        """Release a single quarantined signal."""
        # Update quarantine record
        await connection.execute(
            """
            UPDATE st_feedback_quarantine
            SET reviewed_at = $1,
                reviewed_by = $2,
                decision = $3
            WHERE quarantine_id = $4
              AND decision IS NULL
            """,
            reviewed_at,
            self.REVIEWER_ID,
            self.DECISION_RELEASE,
            quarantine_id,
        )

        # Update source signal status
        await connection.execute(
            """
            UPDATE st_feedback_signals
            SET quarantine_status = $1
            WHERE signal_id = $2
            """,
            self.STATUS_RELEASED,
            signal_id,
        )

    def _emit_metrics(
        self,
        released: int,
        failed: int,
        duration_ms: float,
    ) -> None:
        """Emit job execution metrics."""
        if not self._metrics:
            return

        if released > 0:
            self._metrics.emit(
                "p03_quarantine_auto_released_total",
                float(released),
            )

        if failed > 0:
            self._metrics.emit(
                "p03_quarantine_auto_release_failures_total",
                float(failed),
            )

        self._metrics.observe(
            "p03_quarantine_auto_release_duration_seconds",
            duration_ms / 1000,
        )

    @classmethod
    def create_job_config(cls) -> dict:
        """
        Get job configuration for K0 scheduler registration.

        Returns:
            Dict with job name, interval, and handler info.
        """
        return {
            "name": cls.JOB_NAME,
            "interval_seconds": cls.DEFAULT_INTERVAL_SECONDS,
            "handler": "k0.pipelines.p03.maintenance.quarantine_cleanup:QuarantineAutoReleaseJob.run",
            "enabled": True,
        }


def create_auto_release_job(
    *,
    batch_size: int = QuarantineAutoReleaseJob.DEFAULT_BATCH_SIZE,
    metrics: Optional[MetricsExporter] = None,
    tracer: Optional[TracerFactory] = None,
) -> QuarantineAutoReleaseJob:
    """
    Factory for creating QuarantineAutoReleaseJob.

    Args:
        batch_size: Number of signals to process per batch (default: 100)
        metrics: Optional metrics exporter
        tracer: Optional tracer factory

    Returns:
        Configured QuarantineAutoReleaseJob instance.
    """
    return QuarantineAutoReleaseJob(
        batch_size=batch_size,
        metrics=metrics,
        tracer=tracer,
    )
