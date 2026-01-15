"""
P03 Phase Latency Metrics.

Tracks phase-level latency using K0 MetricsExporter histograms
with SLO targets from dossier Section 15.3.1.

Dossier Reference: Section 15.3.1 Phase Latency Targets
K0 Reference: k0/obs/metrics.py

Issue 6.4.4: Phase latency targets implementation.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Iterator, Literal

if TYPE_CHECKING:
    from prometheus_client import Histogram

    from k0.obs.metrics import MetricsExporter

logger = logging.getLogger(__name__)


# Phase type - aligns with existing VALID_PHASES in observability.py
PhaseType = Literal["R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "FULL_CYCLE"]


class SLOComplianceLevel(Enum):
    """SLO compliance levels for latency checks."""

    EXCELLENT = "excellent"  # <= P50
    GOOD = "good"  # <= P95
    WARNING = "warning"  # <= P99
    BREACH = "breach"  # > P99


@dataclass(frozen=True, slots=True)
class LatencyTarget:
    """
    Latency SLO targets for a phase.

    Per dossier Section 15.3.1, each phase has P50/P95/P99 targets.

    Attributes:
        phase: Phase identifier (R0-R8, FULL_CYCLE)
        p50_ms: 50th percentile target in milliseconds
        p95_ms: 95th percentile target in milliseconds
        p99_ms: 99th percentile target in milliseconds
        description: Human-readable phase description
    """

    phase: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    description: str


# Phase latency targets from dossier Section 15.3.1
PHASE_LATENCY_TARGETS: dict[str, LatencyTarget] = {
    "R0": LatencyTarget("R0", 10, 50, 100, "Batch Select"),
    "R1": LatencyTarget("R1", 20, 100, 200, "Importance/Hebbian"),
    "R2": LatencyTarget("R2", 50, 200, 500, "Episode Clustering"),
    "R3": LatencyTarget("R3", 30, 150, 300, "Dedup/Decay/Prune"),
    "R4": LatencyTarget("R4", 100, 300, 600, "KG/Entity/Causal"),
    "R5": LatencyTarget("R5", 200, 500, 1000, "Dream Exploration"),
    "R6": LatencyTarget("R6", 10, 30, 50, "Status Update"),
    "R7": LatencyTarget("R7", 50, 150, 300, "Truth Write"),
    "R8": LatencyTarget("R8", 5, 20, 50, "Event Emit"),
    "FULL_CYCLE": LatencyTarget("FULL_CYCLE", 500, 1500, 3000, "Full Cycle"),
}

# Histogram buckets in seconds (covering 1ms to 5s)
# Aligned with dossier targets for appropriate granularity
LATENCY_BUCKETS_SECONDS: tuple[float, ...] = (
    0.001,  # 1ms
    0.005,  # 5ms
    0.01,  # 10ms
    0.02,  # 20ms
    0.03,  # 30ms
    0.05,  # 50ms
    0.1,  # 100ms
    0.15,  # 150ms
    0.2,  # 200ms
    0.3,  # 300ms
    0.5,  # 500ms
    1.0,  # 1s
    1.5,  # 1.5s
    2.0,  # 2s
    3.0,  # 3s
    5.0,  # 5s
)


@dataclass(frozen=True, slots=True)
class SLOCheckResult:
    """
    Result of SLO compliance check.

    Attributes:
        phase: Phase that was checked
        duration_ms: Observed duration in milliseconds
        level: Compliance level (EXCELLENT/GOOD/WARNING/BREACH)
        target: LatencyTarget for the phase
        message: Human-readable result message
    """

    phase: str
    duration_ms: float
    level: SLOComplianceLevel
    target: LatencyTarget
    message: str

    @property
    def is_compliant(self) -> bool:
        """Check if within SLO (P99)."""
        return self.level != SLOComplianceLevel.BREACH


class P03PhaseMetrics:
    """
    P03 phase latency metrics using K0 MetricsExporter.

    Tracks phase-level duration histograms and provides
    SLO compliance checking per dossier Section 15.3.1.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.histogram()

    Usage:
        metrics_exporter = MetricsExporter(namespace="p03")
        phase_metrics = P03PhaseMetrics(metrics_exporter)

        # Record phase duration
        phase_metrics.record_phase_duration("R0", 25.0)

        # Check SLO compliance
        result = phase_metrics.check_slo_compliance("R0", 25.0)
        print(f"Compliant: {result.is_compliant}")

        # Use context manager for automatic timing
        with phase_metrics.time_phase("R1"):
            # Process R1 phase...
            pass
    """

    def __init__(
        self,
        metrics_exporter: MetricsExporter | None = None,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize phase metrics.

        Args:
            metrics_exporter: K0 MetricsExporter instance (optional)
            pipeline_id: Pipeline identifier for labels
        """
        self._metrics = metrics_exporter
        self._pipeline_id = pipeline_id

        self._phase_duration: Histogram | None = None
        self._cycle_duration: Histogram | None = None

        if metrics_exporter is not None:
            self._init_histograms(metrics_exporter)

    def _init_histograms(self, metrics_exporter: MetricsExporter) -> None:
        """Initialize Prometheus histograms."""
        self._phase_duration = metrics_exporter.histogram(
            name="p03_phase_duration_seconds",
            description="P03 phase execution duration in seconds",
            labelnames=["phase", "pipeline_id"],
            buckets=LATENCY_BUCKETS_SECONDS,
        )

        self._cycle_duration = metrics_exporter.histogram(
            name="p03_cycle_duration_seconds",
            description="P03 full cycle duration in seconds",
            labelnames=["pipeline_id"],
            buckets=LATENCY_BUCKETS_SECONDS,
        )

    @property
    def pipeline_id(self) -> str:
        """Get pipeline identifier."""
        return self._pipeline_id

    def record_phase_duration(
        self,
        phase: PhaseType,
        duration_ms: float,
    ) -> None:
        """
        Record phase execution duration.

        Observes duration in Prometheus histogram if metrics enabled.

        Args:
            phase: Phase identifier (R0-R8 or FULL_CYCLE)
            duration_ms: Duration in milliseconds
        """
        duration_seconds = duration_ms / 1000.0

        if phase == "FULL_CYCLE":
            if self._cycle_duration is not None:
                self._cycle_duration.labels(
                    pipeline_id=self._pipeline_id,
                ).observe(duration_seconds)
        else:
            if self._phase_duration is not None:
                self._phase_duration.labels(
                    phase=phase,
                    pipeline_id=self._pipeline_id,
                ).observe(duration_seconds)

        logger.debug(
            "Phase duration recorded: phase=%s, duration_ms=%.2f",
            phase,
            duration_ms,
        )

    def check_slo_compliance(
        self,
        phase: PhaseType,
        duration_ms: float,
    ) -> SLOCheckResult:
        """
        Check if duration meets SLO targets.

        Args:
            phase: Phase identifier
            duration_ms: Observed duration in milliseconds

        Returns:
            SLOCheckResult with compliance level and details
        """
        target = PHASE_LATENCY_TARGETS.get(phase)
        if target is None:
            # No target defined - create dummy target
            target = LatencyTarget(phase, 0, 0, 0, "Unknown")
            return SLOCheckResult(
                phase=phase,
                duration_ms=duration_ms,
                level=SLOComplianceLevel.EXCELLENT,
                target=target,
                message=f"No target defined for {phase}",
            )

        if duration_ms <= target.p50_ms:
            level = SLOComplianceLevel.EXCELLENT
            message = f"Excellent: {duration_ms:.1f}ms <= P50 ({target.p50_ms}ms)"
        elif duration_ms <= target.p95_ms:
            level = SLOComplianceLevel.GOOD
            message = f"Good: {duration_ms:.1f}ms <= P95 ({target.p95_ms}ms)"
        elif duration_ms <= target.p99_ms:
            level = SLOComplianceLevel.WARNING
            message = f"Warning: {duration_ms:.1f}ms <= P99 ({target.p99_ms}ms)"
        else:
            level = SLOComplianceLevel.BREACH
            message = f"SLO breach: {duration_ms:.1f}ms > P99 ({target.p99_ms}ms)"

        return SLOCheckResult(
            phase=phase,
            duration_ms=duration_ms,
            level=level,
            target=target,
            message=message,
        )

    def get_target(self, phase: PhaseType) -> LatencyTarget | None:
        """
        Get latency target for a phase.

        Args:
            phase: Phase identifier

        Returns:
            LatencyTarget or None if not defined
        """
        return PHASE_LATENCY_TARGETS.get(phase)

    @contextmanager
    def time_phase(self, phase: PhaseType) -> Iterator[None]:
        """
        Context manager for timing a phase.

        Automatically records duration when context exits.

        Args:
            phase: Phase to time

        Yields:
            None

        Example:
            with phase_metrics.time_phase("R0"):
                # Process R0...
                pass
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000.0
            self.record_phase_duration(phase, duration_ms)

    def record_and_check(
        self,
        phase: PhaseType,
        duration_ms: float,
    ) -> SLOCheckResult:
        """
        Record duration and check SLO compliance in one call.

        Args:
            phase: Phase identifier
            duration_ms: Observed duration in milliseconds

        Returns:
            SLOCheckResult with compliance level
        """
        self.record_phase_duration(phase, duration_ms)
        return self.check_slo_compliance(phase, duration_ms)

    @staticmethod
    def get_all_phases() -> list[str]:
        """Get all defined phases."""
        return list(PHASE_LATENCY_TARGETS.keys())

    @staticmethod
    def get_all_targets() -> dict[str, LatencyTarget]:
        """Get all latency targets."""
        return dict(PHASE_LATENCY_TARGETS)
