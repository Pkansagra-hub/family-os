"""
P03 Throughput Tracker.

Tracks cycle throughput metrics and validates against SLO targets
from dossier Section 15.3.2.

Dossier Reference: Section 15.3.2 Throughput Targets
K0 Reference: k0/obs/metrics.py

Issue 6.4.5: Throughput SLOs for P03 operations.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge

    from k0.obs.metrics import MetricsExporter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ThroughputTargets:
    """
    Throughput SLO targets from dossier Section 15.3.2.

    Attributes:
        events_per_cycle: Target events per consolidation cycle
        cycles_per_hour: Target cycles per hour (90s interval)
        events_per_hour: Normal throughput (events_per_cycle * cycles_per_hour)
        peak_events_per_hour: Maximum burst throughput
        cycle_interval_seconds: Target interval between cycles
    """

    events_per_cycle: int = 1000
    cycles_per_hour: int = 40
    events_per_hour: int = 40000
    peak_events_per_hour: int = 100000
    cycle_interval_seconds: float = 90.0  # 3600 / 40


# Default targets from dossier Section 15.3.2
P03_THROUGHPUT_TARGETS = ThroughputTargets()


class ThroughputComplianceLevel(Enum):
    """Throughput SLO compliance levels."""

    EXCELLENT = "excellent"  # >= 100% of target
    GOOD = "good"  # >= 80% of target
    WARNING = "warning"  # >= 60% of target
    DEGRADED = "degraded"  # < 60% of target


@dataclass(frozen=True, slots=True)
class ThroughputSnapshot:
    """
    Throughput metrics snapshot.

    Attributes:
        events_per_hour: Calculated events per hour
        cycles_per_hour: Calculated cycles per hour
        avg_events_per_cycle: Average events per cycle
        total_events: Total events tracked
        total_cycles: Total cycles tracked
        compliance_level: SLO compliance assessment
        compliance_message: Human-readable compliance status
    """

    events_per_hour: float
    cycles_per_hour: float
    avg_events_per_cycle: float
    total_events: int
    total_cycles: int
    compliance_level: ThroughputComplianceLevel
    compliance_message: str

    @property
    def is_compliant(self) -> bool:
        """Check if within SLO (GOOD or better)."""
        return self.compliance_level in (
            ThroughputComplianceLevel.EXCELLENT,
            ThroughputComplianceLevel.GOOD,
        )


@dataclass
class CycleRecord:
    """Record of a single consolidation cycle."""

    timestamp: float
    event_count: int
    duration_seconds: float


class P03ThroughputTracker:
    """
    P03 throughput tracker with SLO validation.

    Tracks events processed and cycles completed, calculates
    throughput metrics, and validates against dossier targets.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter(), MetricsExporter.gauge()

    Usage:
        metrics_exporter = MetricsExporter(namespace="p03")
        tracker = P03ThroughputTracker(metrics_exporter)

        # Record cycle completion
        tracker.record_cycle(event_count=1000, duration_seconds=30.0)

        # Get throughput snapshot
        snapshot = tracker.get_throughput_snapshot()
        print(f"Events/hour: {snapshot.events_per_hour}")
    """

    def __init__(
        self,
        metrics_exporter: MetricsExporter | None = None,
        targets: ThroughputTargets = P03_THROUGHPUT_TARGETS,
        window_size_hours: float = 1.0,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize throughput tracker.

        Args:
            metrics_exporter: K0 MetricsExporter instance (optional)
            targets: Throughput targets for SLO validation
            window_size_hours: Rolling window for throughput calculation
            pipeline_id: Pipeline identifier for labels
        """
        self._metrics = metrics_exporter
        self._targets = targets
        self._window_size_seconds = window_size_hours * 3600.0
        self._pipeline_id = pipeline_id

        # Rolling window of cycle records
        self._cycles: deque[CycleRecord] = deque()
        self._total_events: int = 0
        self._total_cycles: int = 0

        # Prometheus metrics
        self._events_total: Counter | None = None
        self._cycles_total: Counter | None = None
        self._events_per_hour_gauge: Gauge | None = None
        self._cycles_per_hour_gauge: Gauge | None = None

        if metrics_exporter is not None:
            self._init_metrics(metrics_exporter)

    def _init_metrics(self, metrics_exporter: MetricsExporter) -> None:
        """Initialize Prometheus metrics."""
        self._events_total = metrics_exporter.counter(
            name="p03_events_processed_total",
            description="Total events processed by P03 consolidation",
            labelnames=["pipeline_id"],
        )

        self._cycles_total = metrics_exporter.counter(
            name="p03_cycles_completed_total",
            description="Total consolidation cycles completed",
            labelnames=["pipeline_id"],
        )

        self._events_per_hour_gauge = metrics_exporter.gauge(
            name="p03_events_per_hour",
            description="Current events per hour throughput",
            labelnames=["pipeline_id"],
        )

        self._cycles_per_hour_gauge = metrics_exporter.gauge(
            name="p03_cycles_per_hour",
            description="Current cycles per hour rate",
            labelnames=["pipeline_id"],
        )

    @property
    def targets(self) -> ThroughputTargets:
        """Get throughput targets."""
        return self._targets

    @property
    def pipeline_id(self) -> str:
        """Get pipeline identifier."""
        return self._pipeline_id

    def record_cycle(
        self,
        event_count: int,
        duration_seconds: float,
    ) -> None:
        """
        Record a completed consolidation cycle.

        Args:
            event_count: Number of events processed in cycle
            duration_seconds: Duration of the cycle in seconds
        """
        timestamp = time.time()

        # Add to rolling window
        record = CycleRecord(
            timestamp=timestamp,
            event_count=event_count,
            duration_seconds=duration_seconds,
        )
        self._cycles.append(record)
        self._total_events += event_count
        self._total_cycles += 1

        # Update Prometheus counters
        if self._events_total is not None:
            self._events_total.labels(pipeline_id=self._pipeline_id).inc(event_count)
        if self._cycles_total is not None:
            self._cycles_total.labels(pipeline_id=self._pipeline_id).inc()

        # Prune old records and update gauges
        self._prune_old_records(timestamp)
        self._update_gauges()

        logger.debug(
            "Cycle recorded: events=%d, duration=%.2fs, total_cycles=%d",
            event_count,
            duration_seconds,
            self._total_cycles,
        )

    def record_events(self, event_count: int) -> None:
        """
        Record events without a full cycle.

        Useful for partial updates or batch event tracking.

        Args:
            event_count: Number of events to record
        """
        self._total_events += event_count

        if self._events_total is not None:
            self._events_total.labels(pipeline_id=self._pipeline_id).inc(event_count)

    def get_throughput_snapshot(self) -> ThroughputSnapshot:
        """
        Get current throughput metrics snapshot.

        Returns:
            ThroughputSnapshot with current metrics and compliance
        """
        now = time.time()
        self._prune_old_records(now)

        # Calculate metrics from rolling window
        window_cycles = list(self._cycles)
        window_events = sum(c.event_count for c in window_cycles)
        window_count = len(window_cycles)

        if window_count == 0:
            return ThroughputSnapshot(
                events_per_hour=0.0,
                cycles_per_hour=0.0,
                avg_events_per_cycle=0.0,
                total_events=self._total_events,
                total_cycles=self._total_cycles,
                compliance_level=ThroughputComplianceLevel.DEGRADED,
                compliance_message="No cycles in window",
            )

        # Calculate hourly rates
        oldest_ts = min(c.timestamp for c in window_cycles)
        window_duration = max(now - oldest_ts, 1.0)  # Avoid division by zero
        hours_in_window = window_duration / 3600.0

        events_per_hour = window_events / hours_in_window
        cycles_per_hour = window_count / hours_in_window
        avg_events_per_cycle = window_events / window_count

        # Assess compliance
        level, message = self._assess_compliance(events_per_hour, cycles_per_hour)

        return ThroughputSnapshot(
            events_per_hour=events_per_hour,
            cycles_per_hour=cycles_per_hour,
            avg_events_per_cycle=avg_events_per_cycle,
            total_events=self._total_events,
            total_cycles=self._total_cycles,
            compliance_level=level,
            compliance_message=message,
        )

    def check_cycle_rate_compliance(self) -> tuple[bool, str]:
        """
        Check if cycle rate meets SLO.

        Returns:
            Tuple of (is_compliant, message)
        """
        snapshot = self.get_throughput_snapshot()
        ratio = snapshot.cycles_per_hour / self._targets.cycles_per_hour

        if ratio >= 0.8:
            return True, f"Cycle rate OK: {snapshot.cycles_per_hour:.1f}/hr"
        else:
            return (
                False,
                f"Cycle rate low: {snapshot.cycles_per_hour:.1f}/hr (target: {self._targets.cycles_per_hour}/hr)",
            )

    def check_events_per_hour_compliance(self) -> tuple[bool, str]:
        """
        Check if events per hour meets SLO.

        Returns:
            Tuple of (is_compliant, message)
        """
        snapshot = self.get_throughput_snapshot()
        ratio = snapshot.events_per_hour / self._targets.events_per_hour

        if ratio >= 0.8:
            return True, f"Throughput OK: {snapshot.events_per_hour:.0f}/hr"
        else:
            return (
                False,
                f"Throughput low: {snapshot.events_per_hour:.0f}/hr (target: {self._targets.events_per_hour}/hr)",
            )

    def reset(self) -> None:
        """Reset all tracking counters."""
        self._cycles.clear()
        self._total_events = 0
        self._total_cycles = 0

        logger.info("Throughput tracker reset")

    def _prune_old_records(self, current_time: float) -> None:
        """Remove records older than the window."""
        cutoff = current_time - self._window_size_seconds
        while self._cycles and self._cycles[0].timestamp < cutoff:
            self._cycles.popleft()

    def _update_gauges(self) -> None:
        """Update Prometheus gauges with current rates."""
        if self._events_per_hour_gauge is None or self._cycles_per_hour_gauge is None:
            return

        snapshot = self.get_throughput_snapshot()
        self._events_per_hour_gauge.labels(pipeline_id=self._pipeline_id).set(
            snapshot.events_per_hour
        )
        self._cycles_per_hour_gauge.labels(pipeline_id=self._pipeline_id).set(
            snapshot.cycles_per_hour
        )

    def _assess_compliance(
        self,
        events_per_hour: float,
        cycles_per_hour: float,
    ) -> tuple[ThroughputComplianceLevel, str]:
        """
        Assess SLO compliance based on throughput.

        Args:
            events_per_hour: Current events per hour
            cycles_per_hour: Current cycles per hour

        Returns:
            Tuple of (compliance_level, message)
        """
        events_ratio = events_per_hour / self._targets.events_per_hour
        cycles_ratio = cycles_per_hour / self._targets.cycles_per_hour

        # Use minimum of both ratios
        overall_ratio = min(events_ratio, cycles_ratio)

        if overall_ratio >= 1.0:
            return (
                ThroughputComplianceLevel.EXCELLENT,
                f"Exceeding targets: {events_per_hour:.0f} events/hr, {cycles_per_hour:.1f} cycles/hr",
            )
        elif overall_ratio >= 0.8:
            return (
                ThroughputComplianceLevel.GOOD,
                f"Meeting targets: {events_per_hour:.0f} events/hr ({events_ratio:.0%}), {cycles_per_hour:.1f} cycles/hr ({cycles_ratio:.0%})",
            )
        elif overall_ratio >= 0.6:
            return (
                ThroughputComplianceLevel.WARNING,
                f"Below targets: {events_per_hour:.0f} events/hr ({events_ratio:.0%}), {cycles_per_hour:.1f} cycles/hr ({cycles_ratio:.0%})",
            )
        else:
            return (
                ThroughputComplianceLevel.DEGRADED,
                f"Degraded: {events_per_hour:.0f} events/hr ({events_ratio:.0%}), {cycles_per_hour:.1f} cycles/hr ({cycles_ratio:.0%})",
            )
