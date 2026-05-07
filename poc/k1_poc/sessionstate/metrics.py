"""
SessionState Metrics - Prometheus Metrics for SLI/SLO Measurement
=================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.2 Metrics Implementation
ISSUES: 5.2.1, 5.2.2, 5.2.3, 5.2.4

CONTRACT: k1/contracts/schemas/runtime/sessionstate.policies.yaml (lines 350-420)

This module implements Prometheus metrics for SessionState SLI measurement:
- Latency histograms (read, write, preflight, reconstruction)
- Size gauges (section, tier, total)
- Operation counters (mutations, evictions, reconstructions, emergencies)
- Pressure indicators (per tier and total)

All metrics follow the naming convention: sessionstate_<metric_name>
Labels align with contract specification for consistent observability.

Usage:
    from poc.k1_poc.sessionstate.metrics import SessionStateMetrics

    metrics = SessionStateMetrics()

    # Record latency
    metrics.observe_read_latency("hot", 0.00005)  # 50 microseconds
    metrics.observe_write_latency("beliefs_active", 0.0001)

    # Update gauges
    metrics.set_section_size("control", 1024)
    metrics.set_tier_size("hot", 24576)
    metrics.set_total_size(49152)

    # Increment counters
    metrics.inc_mutations("approved")
    metrics.inc_evictions("telemetry")

    # Update pressure
    metrics.set_pressure_level("hot", 0)  # NORMAL
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from enum import IntEnum
from time import perf_counter
from typing import TYPE_CHECKING, Iterator, Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "CONTENT_TYPE_LATEST",
    "PressureLevelValue",
    "SessionStateMetrics",
    "get_default_metrics",
]

logger = logging.getLogger(__name__)


# =============================================================================
# PRESSURE LEVEL ENUM (numeric values for gauge)
# =============================================================================


class PressureLevelValue(IntEnum):
    """Numeric pressure level values for Prometheus gauge."""

    NORMAL = 0
    ELEVATED = 1
    CRITICAL = 2
    EMERGENCY = 3


# =============================================================================
# BUCKET DEFINITIONS (from contract)
# =============================================================================
# Source: k1/contracts/schemas/runtime/sessionstate.policies.yaml metrics.histograms

# Read latency buckets: 10μs to 1ms (for HOT/WARM tier reads)
READ_LATENCY_BUCKETS = (0.00001, 0.00005, 0.0001, 0.0002, 0.0005, 0.001)

# Write latency buckets: 10μs to 5ms (mutations)
WRITE_LATENCY_BUCKETS = (0.00001, 0.00005, 0.0001, 0.0005, 0.001, 0.005)

# Preflight latency buckets: 10μs to 100μs (very fast checks)
PREFLIGHT_LATENCY_BUCKETS = (0.00001, 0.000025, 0.00005, 0.000075, 0.0001)

# Reconstruction latency buckets: 10ms to 150ms (LOCAL COLD and K0)
RECONSTRUCTION_LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.075, 0.1, 0.15)

# Checkpoint latency buckets: 5ms to 75ms
CHECKPOINT_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075)

# Eviction latency buckets: 1ms to 50ms
EVICTION_LATENCY_BUCKETS = (0.001, 0.005, 0.01, 0.015, 0.025, 0.05)


# =============================================================================
# SECTION AND TIER CONSTANTS
# =============================================================================

HOT_SECTIONS = frozenset(
    {
        "control",
        "scoreboard",
        "meta",
        "history_active",
        "narrative_active",
        "beliefs_active",
        "clarifications",
        "affective_now",
        "task_state",
        "task_artifacts",
            }
)

WARM_SECTIONS = frozenset(
    {
        "telemetry",
        "history_recent",
        "beliefs_history",
        "persona",
        "artifacts_warm",
    }
)

ALL_SECTIONS = HOT_SECTIONS | WARM_SECTIONS

TIERS = ("hot", "warm")

RECONSTRUCTION_SOURCES = ("local_cold", "k0")

MUTATION_RESULTS = ("approved", "rejected")


# =============================================================================
# SESSIONSTATE METRICS CLASS
# =============================================================================


class SessionStateMetrics:
    """
    Prometheus metrics exporter for SessionState SLI/SLO measurement.

    Thread-safe implementation using lazy metric creation with RLock protection.
    Metrics follow the contract specification in sessionstate.policies.yaml.

    Attributes:
        namespace: Metric namespace prefix (default: empty for sessionstate_*)
        registry: Prometheus CollectorRegistry (default: auto-created)

    Example:
        metrics = SessionStateMetrics()

        # Time an operation
        with metrics.time_read("hot"):
            data = manager.get_section("control")

        # Or manual observation
        start = time.perf_counter()
        data = manager.get_section("control")
        metrics.observe_read_latency("hot", time.perf_counter() - start)
    """

    __slots__ = (
        "_registry",
        "_namespace",
        "_lock",
        # Histograms
        "_read_latency",
        "_write_latency",
        "_preflight_latency",
        "_reconstruction_latency",
        "_checkpoint_latency",
        "_eviction_latency",
        # Gauges
        "_section_size",
        "_tier_size",
        "_total_size",
        "_pressure_level",
        "_utilization_ratio",
        # Counters
        "_mutations_total",
        "_evictions_total",
        "_reconstructions_total",
        "_emergencies_total",
        "_checkpoints_total",
    )

    def __init__(
        self,
        *,
        namespace: str = "",
        registry: Optional[CollectorRegistry] = None,
    ) -> None:
        """
        Initialize SessionStateMetrics.

        Args:
            namespace: Optional namespace prefix for metrics
            registry: Optional custom CollectorRegistry
        """
        self._registry = registry or CollectorRegistry(auto_describe=True)
        self._namespace = namespace
        self._lock = threading.RLock()

        # Lazy initialization - metrics created on first use
        self._read_latency: Optional[Histogram] = None
        self._write_latency: Optional[Histogram] = None
        self._preflight_latency: Optional[Histogram] = None
        self._reconstruction_latency: Optional[Histogram] = None
        self._checkpoint_latency: Optional[Histogram] = None
        self._eviction_latency: Optional[Histogram] = None

        self._section_size: Optional[Gauge] = None
        self._tier_size: Optional[Gauge] = None
        self._total_size: Optional[Gauge] = None
        self._pressure_level: Optional[Gauge] = None
        self._utilization_ratio: Optional[Gauge] = None

        self._mutations_total: Optional[Counter] = None
        self._evictions_total: Optional[Counter] = None
        self._reconstructions_total: Optional[Counter] = None
        self._emergencies_total: Optional[Counter] = None
        self._checkpoints_total: Optional[Counter] = None

    @property
    def registry(self) -> CollectorRegistry:
        """Get the Prometheus registry."""
        return self._registry

    # =========================================================================
    # HISTOGRAM PROPERTIES (lazy creation)
    # =========================================================================

    @property
    def read_latency(self) -> Histogram:
        """Histogram: sessionstate_read_latency_seconds{tier}."""
        with self._lock:
            if self._read_latency is None:
                self._read_latency = Histogram(
                    "sessionstate_read_latency_seconds",
                    "Read latency by tier",
                    labelnames=["tier"],
                    buckets=READ_LATENCY_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._read_latency

    @property
    def write_latency(self) -> Histogram:
        """Histogram: sessionstate_write_latency_seconds{section}."""
        with self._lock:
            if self._write_latency is None:
                self._write_latency = Histogram(
                    "sessionstate_write_latency_seconds",
                    "Write/mutation latency by section",
                    labelnames=["section"],
                    buckets=WRITE_LATENCY_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._write_latency

    @property
    def preflight_latency(self) -> Histogram:
        """Histogram: sessionstate_preflight_latency_seconds."""
        with self._lock:
            if self._preflight_latency is None:
                self._preflight_latency = Histogram(
                    "sessionstate_preflight_latency_seconds",
                    "Preflight check latency",
                    buckets=PREFLIGHT_LATENCY_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._preflight_latency

    @property
    def reconstruction_latency(self) -> Histogram:
        """Histogram: sessionstate_reconstruction_latency_seconds{source}."""
        with self._lock:
            if self._reconstruction_latency is None:
                self._reconstruction_latency = Histogram(
                    "sessionstate_reconstruction_latency_seconds",
                    "Reconstruction latency by source",
                    labelnames=["source"],
                    buckets=RECONSTRUCTION_LATENCY_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._reconstruction_latency

    @property
    def checkpoint_latency(self) -> Histogram:
        """Histogram: sessionstate_checkpoint_latency_seconds."""
        with self._lock:
            if self._checkpoint_latency is None:
                self._checkpoint_latency = Histogram(
                    "sessionstate_checkpoint_latency_seconds",
                    "Checkpoint creation latency",
                    buckets=CHECKPOINT_LATENCY_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._checkpoint_latency

    @property
    def eviction_latency(self) -> Histogram:
        """Histogram: sessionstate_eviction_latency_seconds{section}."""
        with self._lock:
            if self._eviction_latency is None:
                self._eviction_latency = Histogram(
                    "sessionstate_eviction_latency_seconds",
                    "Eviction latency by section",
                    labelnames=["section"],
                    buckets=EVICTION_LATENCY_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._eviction_latency

    # =========================================================================
    # GAUGE PROPERTIES (lazy creation)
    # =========================================================================

    @property
    def section_size(self) -> Gauge:
        """Gauge: sessionstate_section_size_bytes{section}."""
        with self._lock:
            if self._section_size is None:
                self._section_size = Gauge(
                    "sessionstate_section_size_bytes",
                    "Current size of each section",
                    labelnames=["section"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._section_size

    @property
    def tier_size(self) -> Gauge:
        """Gauge: sessionstate_tier_size_bytes{tier}."""
        with self._lock:
            if self._tier_size is None:
                self._tier_size = Gauge(
                    "sessionstate_tier_size_bytes",
                    "Current size of each tier",
                    labelnames=["tier"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._tier_size

    @property
    def total_size(self) -> Gauge:
        """Gauge: sessionstate_total_size_bytes."""
        with self._lock:
            if self._total_size is None:
                self._total_size = Gauge(
                    "sessionstate_total_size_bytes",
                    "Total session size",
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._total_size

    @property
    def pressure_level(self) -> Gauge:
        """Gauge: sessionstate_pressure_level{tier}."""
        with self._lock:
            if self._pressure_level is None:
                self._pressure_level = Gauge(
                    "sessionstate_pressure_level",
                    "Current pressure level (0=NORMAL, 1=ELEVATED, 2=CRITICAL, 3=EMERGENCY)",
                    labelnames=["tier"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._pressure_level

    @property
    def utilization_ratio(self) -> Gauge:
        """Gauge: sessionstate_utilization_ratio{tier}."""
        with self._lock:
            if self._utilization_ratio is None:
                self._utilization_ratio = Gauge(
                    "sessionstate_utilization_ratio",
                    "Current utilization ratio (0.0-1.0)",
                    labelnames=["tier"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._utilization_ratio

    # =========================================================================
    # COUNTER PROPERTIES (lazy creation)
    # =========================================================================

    @property
    def mutations_total(self) -> Counter:
        """Counter: sessionstate_mutations_total{result}."""
        with self._lock:
            if self._mutations_total is None:
                self._mutations_total = Counter(
                    "sessionstate_mutations_total",
                    "Total mutations by result (approved/rejected)",
                    labelnames=["result"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._mutations_total

    @property
    def evictions_total(self) -> Counter:
        """Counter: sessionstate_evictions_total{section}."""
        with self._lock:
            if self._evictions_total is None:
                self._evictions_total = Counter(
                    "sessionstate_evictions_total",
                    "Total evictions by section",
                    labelnames=["section"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._evictions_total

    @property
    def reconstructions_total(self) -> Counter:
        """Counter: sessionstate_reconstructions_total{source}."""
        with self._lock:
            if self._reconstructions_total is None:
                self._reconstructions_total = Counter(
                    "sessionstate_reconstructions_total",
                    "Total reconstructions by source (local_cold/k0)",
                    labelnames=["source"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._reconstructions_total

    @property
    def emergencies_total(self) -> Counter:
        """Counter: sessionstate_emergencies_total{level}."""
        with self._lock:
            if self._emergencies_total is None:
                self._emergencies_total = Counter(
                    "sessionstate_emergencies_total",
                    "Total emergency mode activations",
                    labelnames=["level"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._emergencies_total

    @property
    def checkpoints_total(self) -> Counter:
        """Counter: sessionstate_checkpoints_total."""
        with self._lock:
            if self._checkpoints_total is None:
                self._checkpoints_total = Counter(
                    "sessionstate_checkpoints_total",
                    "Total checkpoints created",
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._checkpoints_total

    # =========================================================================
    # HISTOGRAM OBSERVATION METHODS
    # =========================================================================

    def observe_read_latency(self, tier: str, latency_seconds: float) -> None:
        """
        Record read latency for a tier.

        Args:
            tier: Tier name ("hot" or "warm")
            latency_seconds: Latency in seconds
        """
        self.read_latency.labels(tier=tier).observe(latency_seconds)

    def observe_write_latency(self, section: str, latency_seconds: float) -> None:
        """
        Record write/mutation latency for a section.

        Args:
            section: Section name (e.g., "control", "beliefs_active")
            latency_seconds: Latency in seconds
        """
        self.write_latency.labels(section=section).observe(latency_seconds)

    def observe_preflight_latency(self, latency_seconds: float) -> None:
        """
        Record preflight check latency.

        Args:
            latency_seconds: Latency in seconds
        """
        self.preflight_latency.observe(latency_seconds)

    def observe_reconstruction_latency(self, source: str, latency_seconds: float) -> None:
        """
        Record reconstruction latency.

        Args:
            source: Source of reconstruction ("local_cold" or "k0")
            latency_seconds: Latency in seconds
        """
        self.reconstruction_latency.labels(source=source).observe(latency_seconds)

    def observe_checkpoint_latency(self, latency_seconds: float) -> None:
        """
        Record checkpoint creation latency.

        Args:
            latency_seconds: Latency in seconds
        """
        self.checkpoint_latency.observe(latency_seconds)

    def observe_eviction_latency(self, section: str, latency_seconds: float) -> None:
        """
        Record eviction latency for a section.

        Args:
            section: Section name
            latency_seconds: Latency in seconds
        """
        self.eviction_latency.labels(section=section).observe(latency_seconds)

    # =========================================================================
    # CONTEXT MANAGERS FOR TIMING
    # =========================================================================

    @contextmanager
    def time_read(self, tier: str) -> Iterator[None]:
        """
        Context manager to time read operations.

        Args:
            tier: Tier name ("hot" or "warm")

        Example:
            with metrics.time_read("hot"):
                data = manager.get_section("control")
        """
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_read_latency(tier, perf_counter() - start)

    @contextmanager
    def time_write(self, section: str) -> Iterator[None]:
        """
        Context manager to time write/mutation operations.

        Args:
            section: Section name

        Example:
            with metrics.time_write("beliefs_active"):
                manager.mutate("beliefs_active", "add", data)
        """
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_write_latency(section, perf_counter() - start)

    @contextmanager
    def time_preflight(self) -> Iterator[None]:
        """
        Context manager to time preflight checks.

        Example:
            with metrics.time_preflight():
                guard.preflight(section, operation, size)
        """
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_preflight_latency(perf_counter() - start)

    @contextmanager
    def time_reconstruction(self, source: str) -> Iterator[None]:
        """
        Context manager to time reconstruction operations.

        Args:
            source: Source of reconstruction ("local_cold" or "k0")

        Example:
            with metrics.time_reconstruction("local_cold"):
                manager.restore_from_checkpoint()
        """
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_reconstruction_latency(source, perf_counter() - start)

    @contextmanager
    def time_checkpoint(self) -> Iterator[None]:
        """
        Context manager to time checkpoint creation.

        Example:
            with metrics.time_checkpoint():
                manager.checkpoint()
        """
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_checkpoint_latency(perf_counter() - start)

    @contextmanager
    def time_eviction(self, section: str) -> Iterator[None]:
        """
        Context manager to time eviction operations.

        Args:
            section: Section being evicted

        Example:
            with metrics.time_eviction("telemetry"):
                eviction_engine.evict_section("telemetry")
        """
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_eviction_latency(section, perf_counter() - start)

    # =========================================================================
    # GAUGE SETTER METHODS
    # =========================================================================

    def set_section_size(self, section: str, size_bytes: int) -> None:
        """
        Set current size for a section.

        Args:
            section: Section name
            size_bytes: Current size in bytes
        """
        self.section_size.labels(section=section).set(size_bytes)

    def set_tier_size(self, tier: str, size_bytes: int) -> None:
        """
        Set current size for a tier.

        Args:
            tier: Tier name ("hot" or "warm")
            size_bytes: Current size in bytes
        """
        self.tier_size.labels(tier=tier).set(size_bytes)

    def set_total_size(self, size_bytes: int) -> None:
        """
        Set total session size.

        Args:
            size_bytes: Total size in bytes
        """
        self.total_size.set(size_bytes)

    def set_pressure_level(self, tier: str, level: int) -> None:
        """
        Set pressure level for a tier.

        Args:
            tier: Tier name ("hot", "warm", or "total")
            level: Pressure level (0=NORMAL, 1=ELEVATED, 2=CRITICAL, 3=EMERGENCY)
        """
        self.pressure_level.labels(tier=tier).set(level)

    def set_utilization_ratio(self, tier: str, ratio: float) -> None:
        """
        Set utilization ratio for a tier.

        Args:
            tier: Tier name ("hot", "warm", or "total")
            ratio: Utilization ratio (0.0-1.0)
        """
        self.utilization_ratio.labels(tier=tier).set(ratio)

    # =========================================================================
    # COUNTER INCREMENT METHODS
    # =========================================================================

    def inc_mutations(self, result: str, count: int = 1) -> None:
        """
        Increment mutation counter.

        Args:
            result: Mutation result ("approved" or "rejected")
            count: Number to increment by (default 1)
        """
        self.mutations_total.labels(result=result).inc(count)

    def inc_evictions(self, section: str, count: int = 1) -> None:
        """
        Increment eviction counter.

        Args:
            section: Section that was evicted
            count: Number to increment by (default 1)
        """
        self.evictions_total.labels(section=section).inc(count)

    def inc_reconstructions(self, source: str, count: int = 1) -> None:
        """
        Increment reconstruction counter.

        Args:
            source: Source of reconstruction ("local_cold" or "k0")
            count: Number to increment by (default 1)
        """
        self.reconstructions_total.labels(source=source).inc(count)

    def inc_emergencies(self, level: str, count: int = 1) -> None:
        """
        Increment emergency counter.

        Args:
            level: Emergency level ("critical" or "emergency")
            count: Number to increment by (default 1)
        """
        self.emergencies_total.labels(level=level).inc(count)

    def inc_checkpoints(self, count: int = 1) -> None:
        """
        Increment checkpoint counter.

        Args:
            count: Number to increment by (default 1)
        """
        self.checkpoints_total.inc(count)

    # =========================================================================
    # BULK UPDATE METHODS
    # =========================================================================

    def update_from_snapshot(
        self,
        *,
        total_size_bytes: int,
        hot_size_bytes: int,
        warm_size_bytes: int,
        hot_utilization_pct: float,
        warm_utilization_pct: float,
        total_utilization_pct: float,
        pressure_level: int,
        section_sizes: dict[str, int],
    ) -> None:
        """
        Bulk update all gauges from a SessionSnapshot.

        Args:
            total_size_bytes: Total session size
            hot_size_bytes: HOT tier size
            warm_size_bytes: WARM tier size
            hot_utilization_pct: HOT tier utilization (0-100)
            warm_utilization_pct: WARM tier utilization (0-100)
            total_utilization_pct: Total utilization (0-100)
            pressure_level: Overall pressure level (0-3)
            section_sizes: Dict mapping section names to sizes

        Example:
            snapshot = manager.get_snapshot()
            metrics.update_from_snapshot(
                total_size_bytes=snapshot.total_size_bytes,
                hot_size_bytes=snapshot.hot_size_bytes,
                warm_size_bytes=snapshot.warm_size_bytes,
                hot_utilization_pct=snapshot.hot_utilization_pct,
                warm_utilization_pct=snapshot.warm_utilization_pct,
                total_utilization_pct=snapshot.total_utilization_pct,
                pressure_level=PRESSURE_MAP[snapshot.pressure],
                section_sizes={s: info.size_bytes for s, info in snapshot.sections.items()},
            )
        """
        # Update sizes
        self.set_total_size(total_size_bytes)
        self.set_tier_size("hot", hot_size_bytes)
        self.set_tier_size("warm", warm_size_bytes)

        # Update utilization (convert from percentage to ratio)
        self.set_utilization_ratio("hot", hot_utilization_pct / 100.0)
        self.set_utilization_ratio("warm", warm_utilization_pct / 100.0)
        self.set_utilization_ratio("total", total_utilization_pct / 100.0)

        # Update pressure
        self.set_pressure_level("total", pressure_level)

        # Update section sizes
        for section, size in section_sizes.items():
            self.set_section_size(section, size)

    # =========================================================================
    # EXPORT
    # =========================================================================

    def latest(self) -> bytes:
        """
        Serialize metrics using Prometheus text exposition format.

        Returns:
            bytes: Prometheus text format metrics
        """
        return generate_latest(self._registry)


# =============================================================================
# DEFAULT SINGLETON
# =============================================================================

_default_metrics: Optional[SessionStateMetrics] = None
_default_lock = threading.Lock()


def get_default_metrics() -> SessionStateMetrics:
    """
    Get the default SessionStateMetrics singleton.

    Thread-safe lazy initialization.

    Returns:
        SessionStateMetrics: The default metrics instance
    """
    global _default_metrics
    if _default_metrics is None:
        with _default_lock:
            if _default_metrics is None:
                _default_metrics = SessionStateMetrics()
    return _default_metrics
