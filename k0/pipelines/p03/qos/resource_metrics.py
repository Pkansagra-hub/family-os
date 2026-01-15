"""
P03 Resource Utilization Metrics.

Tracks memory, CPU, database connections, and FAISS queries
per dossier Section 15.3.3 Resource Utilization Targets.

Dossier Reference: Section 15.3.3 Resource Utilization Targets
K0 Reference: k0/obs/metrics.py

Issue 6.4.6: Resource utilization metrics for P03 operations.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge

    from k0.obs.metrics import MetricsExporter

logger = logging.getLogger(__name__)


class MemoryPressureLevel(Enum):
    """Memory pressure levels per dossier."""

    OK = 0
    WARNING = 1
    THROTTLE = 2
    CRITICAL = 3


@dataclass(frozen=True, slots=True)
class ResourceTarget:
    """
    Resource utilization target.

    Attributes:
        name: Resource identifier
        target_value: Target threshold
        alert_threshold: Alert threshold (typically 80% of target)
        unit: Unit of measurement
        description: Human-readable description
    """

    name: str
    target_value: float
    alert_threshold: float
    unit: str
    description: str


# Resource targets from dossier Section 15.3.3
P03_RESOURCE_TARGETS: dict[str, ResourceTarget] = {
    "memory_mb": ResourceTarget(
        name="memory_mb",
        target_value=512.0,
        alert_threshold=410.0,  # 80% of 512
        unit="MB",
        description="Memory per cycle",
    ),
    "cpu_cores": ResourceTarget(
        name="cpu_cores",
        target_value=2.0,
        alert_threshold=1.8,  # 90%
        unit="cores",
        description="CPU per cycle",
    ),
    "db_connections": ResourceTarget(
        name="db_connections",
        target_value=10.0,
        alert_threshold=8.0,  # 80%
        unit="connections",
        description="DB connection pool",
    ),
    "faiss_queries": ResourceTarget(
        name="faiss_queries",
        target_value=100.0,
        alert_threshold=100.0,  # No alert threshold
        unit="queries",
        description="FAISS queries per cycle",
    ),
}

# Memory thresholds for pressure levels
MEMORY_THRESHOLDS: dict[str, float] = {
    "warning_mb": 256.0,
    "throttle_mb": 384.0,
    "critical_mb": 480.0,
}


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """
    Snapshot of current resource utilization.

    Attributes:
        memory_mb: Current memory usage in MB
        cpu_utilization: CPU utilization (0.0-1.0)
        db_active: Active database connections
        db_pool_size: Total pool size
        faiss_queries: FAISS queries this cycle
        memory_pressure: Current pressure level
    """

    memory_mb: float
    cpu_utilization: float
    db_active: int
    db_pool_size: int
    faiss_queries: int
    memory_pressure: MemoryPressureLevel

    @property
    def should_throttle(self) -> bool:
        """Check if throttling is needed."""
        return self.memory_pressure in (
            MemoryPressureLevel.THROTTLE,
            MemoryPressureLevel.CRITICAL,
        )


class P03ResourceMetrics:
    """
    P03 resource utilization metrics.

    Tracks memory, CPU, database connections, and FAISS queries
    using K0 MetricsExporter.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.gauge(), counter()

    Usage:
        metrics_exporter = MetricsExporter(namespace="p03")
        resource_metrics = P03ResourceMetrics(metrics_exporter)

        # Record memory usage
        resource_metrics.record_memory_usage("R3", 256.0)

        # Check memory threshold
        level, should_throttle = resource_metrics.check_memory_threshold(400.0)
    """

    def __init__(
        self,
        metrics_exporter: MetricsExporter | None = None,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize resource metrics.

        Args:
            metrics_exporter: K0 MetricsExporter instance (optional)
            pipeline_id: Pipeline identifier for labels
        """
        self._metrics = metrics_exporter
        self._pipeline_id = pipeline_id

        # Internal tracking
        self._faiss_query_count: int = 0
        self._current_memory_mb: float = 0.0

        # Prometheus metrics
        self._memory_gauge: Gauge | None = None
        self._cpu_gauge: Gauge | None = None
        self._db_active_gauge: Gauge | None = None
        self._db_pool_gauge: Gauge | None = None
        self._faiss_counter: Counter | None = None
        self._memory_pressure_gauge: Gauge | None = None

        if metrics_exporter is not None:
            self._init_metrics(metrics_exporter)

    def _init_metrics(self, metrics_exporter: MetricsExporter) -> None:
        """Initialize Prometheus metrics."""
        self._memory_gauge = metrics_exporter.gauge(
            name="p03_memory_mb",
            description="P03 memory usage in MB",
            labelnames=["stage", "pipeline_id"],
        )

        self._cpu_gauge = metrics_exporter.gauge(
            name="p03_cpu_utilization",
            description="P03 CPU utilization (0.0-1.0)",
            labelnames=["pipeline_id"],
        )

        self._db_active_gauge = metrics_exporter.gauge(
            name="p03_db_pool_active",
            description="Active DB connections in pool",
            labelnames=["pipeline_id"],
        )

        self._db_pool_gauge = metrics_exporter.gauge(
            name="p03_db_pool_size",
            description="Total DB pool size",
            labelnames=["pipeline_id"],
        )

        self._faiss_counter = metrics_exporter.counter(
            name="p03_faiss_queries_total",
            description="Total FAISS queries executed",
            labelnames=["operation", "pipeline_id"],
        )

        self._memory_pressure_gauge = metrics_exporter.gauge(
            name="p03_memory_pressure",
            description="Memory pressure level (0=ok, 1=warning, 2=throttle, 3=critical)",
            labelnames=["pipeline_id"],
        )

    @property
    def pipeline_id(self) -> str:
        """Get pipeline identifier."""
        return self._pipeline_id

    def record_memory_usage(
        self,
        stage: str,
        memory_mb: float | None = None,
    ) -> None:
        """
        Record memory usage for a stage.

        Args:
            stage: Processing stage (R0-R8)
            memory_mb: Memory in MB (auto-detect if None)
        """
        if memory_mb is None:
            memory_mb = self._get_process_memory_mb()

        self._current_memory_mb = memory_mb

        if self._memory_gauge is not None:
            self._memory_gauge.labels(
                stage=stage,
                pipeline_id=self._pipeline_id,
            ).set(memory_mb)

        # Update pressure level
        pressure = self._compute_memory_pressure(memory_mb)
        if self._memory_pressure_gauge is not None:
            self._memory_pressure_gauge.labels(
                pipeline_id=self._pipeline_id,
            ).set(pressure.value)

        logger.debug(
            "Memory recorded: stage=%s, memory_mb=%.1f, pressure=%s",
            stage,
            memory_mb,
            pressure.name,
        )

    def record_cpu_utilization(self, utilization: float) -> None:
        """
        Record CPU utilization.

        Args:
            utilization: CPU usage (0.0-1.0)
        """
        if self._cpu_gauge is not None:
            self._cpu_gauge.labels(
                pipeline_id=self._pipeline_id,
            ).set(utilization)

    def record_db_pool_stats(
        self,
        active: int,
        pool_size: int,
    ) -> None:
        """
        Record DB connection pool stats.

        Args:
            active: Active connections
            pool_size: Total pool size
        """
        if self._db_active_gauge is not None:
            self._db_active_gauge.labels(
                pipeline_id=self._pipeline_id,
            ).set(active)

        if self._db_pool_gauge is not None:
            self._db_pool_gauge.labels(
                pipeline_id=self._pipeline_id,
            ).set(pool_size)

    def record_faiss_query(
        self,
        operation: str = "search",
        count: int = 1,
    ) -> None:
        """
        Record FAISS query execution.

        Args:
            operation: Query type (search, add, etc.)
            count: Number of queries
        """
        self._faiss_query_count += count

        if self._faiss_counter is not None:
            self._faiss_counter.labels(
                operation=operation,
                pipeline_id=self._pipeline_id,
            ).inc(count)

    def check_memory_threshold(
        self,
        memory_mb: float,
    ) -> tuple[MemoryPressureLevel, bool]:
        """
        Check if memory exceeds thresholds.

        Args:
            memory_mb: Current memory usage

        Returns:
            Tuple of (pressure_level, should_throttle)
        """
        pressure = self._compute_memory_pressure(memory_mb)
        should_throttle = pressure in (
            MemoryPressureLevel.THROTTLE,
            MemoryPressureLevel.CRITICAL,
        )
        return pressure, should_throttle

    def check_resource_compliance(
        self,
        resource: str,
        value: float,
    ) -> tuple[bool, str]:
        """
        Check if resource value meets target.

        Args:
            resource: Resource name (memory_mb, cpu_cores, etc.)
            value: Current value

        Returns:
            Tuple of (is_compliant, message)
        """
        target = P03_RESOURCE_TARGETS.get(resource)
        if target is None:
            return True, f"No target defined for {resource}"

        if value <= target.target_value:
            if value <= target.alert_threshold:
                return (
                    True,
                    f"OK: {value:.1f}{target.unit} <= {target.alert_threshold:.1f}{target.unit}",
                )
            else:
                return (
                    True,
                    f"Warning: {value:.1f}{target.unit} approaching limit ({target.target_value:.1f}{target.unit})",
                )
        else:
            return (
                False,
                f"Exceeded: {value:.1f}{target.unit} > {target.target_value:.1f}{target.unit}",
            )

    def get_snapshot(self) -> ResourceSnapshot:
        """
        Get current resource snapshot.

        Returns:
            ResourceSnapshot with current values
        """
        memory_mb = self._current_memory_mb or self._get_process_memory_mb()
        pressure = self._compute_memory_pressure(memory_mb)

        return ResourceSnapshot(
            memory_mb=memory_mb,
            cpu_utilization=0.0,  # Would need psutil for real value
            db_active=0,
            db_pool_size=0,
            faiss_queries=self._faiss_query_count,
            memory_pressure=pressure,
        )

    def reset_cycle_metrics(self) -> None:
        """Reset per-cycle metrics."""
        self._faiss_query_count = 0

    def _get_process_memory_mb(self) -> float:
        """Get current process memory in MB."""
        try:
            if sys.platform != "win32":
                import resource

                usage = resource.getrusage(resource.RUSAGE_SELF)
                return usage.ru_maxrss / 1024  # Convert KB to MB
            else:
                # Windows fallback - use tracemalloc or psutil if available
                try:
                    import psutil

                    process = psutil.Process()
                    return process.memory_info().rss / (1024 * 1024)
                except ImportError:
                    return 0.0
        except Exception:
            return 0.0

    def _compute_memory_pressure(self, memory_mb: float) -> MemoryPressureLevel:
        """Compute memory pressure level."""
        if memory_mb >= MEMORY_THRESHOLDS["critical_mb"]:
            return MemoryPressureLevel.CRITICAL
        elif memory_mb >= MEMORY_THRESHOLDS["throttle_mb"]:
            return MemoryPressureLevel.THROTTLE
        elif memory_mb >= MEMORY_THRESHOLDS["warning_mb"]:
            return MemoryPressureLevel.WARNING
        else:
            return MemoryPressureLevel.OK

    @staticmethod
    def get_all_targets() -> dict[str, ResourceTarget]:
        """Get all resource targets."""
        return dict(P03_RESOURCE_TARGETS)
