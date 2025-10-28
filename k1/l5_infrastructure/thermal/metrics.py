"""
Module: k1.l5_infrastructure.thermal.metrics
Purpose: Thermal metrics collection and Prometheus export

This module provides the ThermalMetrics class for comprehensive thermal monitoring,
including temperature tracking (P50/P95/P99), power consumption, placement transitions,
thermal zone durations, and cooldown violation detection.

Architecture:
    - Temperature histograms: P50/P95/P99 latency tracking per thermal zone
    - Power histograms: Power consumption tracking per component (CPU/GPU)
    - Placement counters: Transition tracking (upgrade/downgrade/emergency)
    - Zone duration gauges: Time spent in each thermal zone
    - Cooldown violation counters: Hysteresis enforcement validation

Performance Budgets:
    - Metric recording: <100µs P95
    - Statistics calculation: <5ms P95
    - Prometheus scrape: <10ms P95

Related ADRs:
    - ADR-0026: Thermal Hysteresis Matrix Device Management
    - ADR-0026b: Hysteresis State Machine (5°C Buffer)
    - ADR-0026c: Model Placement Integration (Thermal Cascade)

Research Foundation:
    - Prometheus Best Practices: Histogram buckets for latency percentiles
    - OpenTelemetry: Multi-dimensional metrics with labels
    - SRE Golden Signals: Latency, traffic, errors, saturation

Author: K1 Infrastructure Team
Date: 2025-10-27
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram, Summary

logger = structlog.get_logger()

# ============================================================================
# Prometheus Metrics
# ============================================================================

# Temperature tracking (histogram for P50/P95/P99)
thermal_temperature_celsius = Histogram(
    "k1_thermal_temperature_celsius",
    "Device temperature in Celsius",
    ["zone"],
    buckets=[50, 55, 60, 65, 70, 72, 74, 75, 78, 80, 82, 85, 88, 90, 95, 100],
)

# Latest temperature (gauge for current value)
thermal_temperature_latest_celsius = Gauge(
    "k1_thermal_temperature_latest_celsius",
    "Latest device temperature in Celsius",
    ["zone", "component"],
)

# Power tracking (histogram for distribution)
thermal_power_watts = Histogram(
    "k1_thermal_power_watts",
    "Device power consumption in Watts",
    ["component"],
    buckets=[0, 2, 5, 8, 10, 12, 15, 18, 20, 25, 30],
)

# Latest power (gauge for current value)
thermal_power_latest_watts = Gauge(
    "k1_thermal_power_latest_watts",
    "Latest device power consumption in Watts",
    ["component"],
)

# Placement transitions (counter)
thermal_placement_changes_total = Counter(
    "k1_thermal_placement_changes_total",
    "Total placement tier transitions",
    ["from_tier", "to_tier", "reason"],
)

# Latest placement tier (gauge)
thermal_placement_latest = Gauge(
    "k1_thermal_placement_latest",
    "Current placement tier (0=NPU, 1=GPU, 2=CPU, 3=Remote)",
    ["tier"],
)

# Placement transition latency (summary)
thermal_placement_transition_latency_ms = Summary(
    "k1_thermal_placement_transition_latency_ms", "Time to execute placement transition"
)

# Thermal zone transitions (counter)
thermal_zone_changes_total = Counter(
    "k1_thermal_zone_changes_total",
    "Total thermal zone transitions",
    ["from_zone", "to_zone"],
)

# Thermal zone duration (gauge)
thermal_zone_duration_seconds = Gauge(
    "k1_thermal_zone_duration_seconds", "Time spent in thermal zone", ["zone"]
)

# Cooldown violations (counter)
thermal_placement_cooldown_violations_total = Counter(
    "k1_thermal_placement_cooldown_violations_total",
    "Cooldown period violations (attempted transition too soon)",
    ["from_tier", "to_tier"],
)

# Placement tier distribution (gauge)
thermal_placement_tier_distribution_pct = Gauge(
    "k1_thermal_placement_tier_distribution_pct",
    "Percentage of time spent on each tier",
    ["tier"],
)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ThermalStatistics:
    """Thermal statistics summary"""

    temperature_p50_c: float = 0.0
    temperature_p95_c: float = 0.0
    temperature_p99_c: float = 0.0
    power_avg_w: float = 0.0
    power_p95_w: float = 0.0
    placement_npu_pct: float = 0.0
    placement_gpu_pct: float = 0.0
    placement_cpu_pct: float = 0.0
    placement_remote_pct: float = 0.0
    transitions_total: int = 0
    transitions_per_hour: float = 0.0
    cooldown_violations_total: int = 0
    zone_cool_pct: float = 0.0
    zone_warm_pct: float = 0.0
    zone_hot_pct: float = 0.0
    zone_critical_pct: float = 0.0
    zone_emergency_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "temperature": {
                "p50_c": self.temperature_p50_c,
                "p95_c": self.temperature_p95_c,
                "p99_c": self.temperature_p99_c,
            },
            "power": {"avg_w": self.power_avg_w, "p95_w": self.power_p95_w},
            "placement": {
                "npu_pct": self.placement_npu_pct,
                "gpu_pct": self.placement_gpu_pct,
                "cpu_pct": self.placement_cpu_pct,
                "remote_pct": self.placement_remote_pct,
            },
            "transitions": {
                "total": self.transitions_total,
                "per_hour": self.transitions_per_hour,
            },
            "cooldown_violations": self.cooldown_violations_total,
            "thermal_zones": {
                "cool_pct": self.zone_cool_pct,
                "warm_pct": self.zone_warm_pct,
                "hot_pct": self.zone_hot_pct,
                "critical_pct": self.zone_critical_pct,
                "emergency_pct": self.zone_emergency_pct,
            },
        }


@dataclass
class ZoneTracking:
    """Thermal zone tracking state"""

    current_zone: str = "COOL"
    zone_entry_time_ms: float = 0.0
    zone_durations_ms: Dict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )

    def enter_zone(self, zone: str):
        """Record entry into a thermal zone"""
        now_ms = time.perf_counter() * 1000

        # Record duration in previous zone
        if self.current_zone:
            duration_ms = now_ms - self.zone_entry_time_ms
            self.zone_durations_ms[self.current_zone] += duration_ms

        # Enter new zone
        self.current_zone = zone
        self.zone_entry_time_ms = now_ms


@dataclass
class PlacementTracking:
    """Placement tier tracking state"""

    current_tier: str = "NPU"
    tier_entry_time_ms: float = 0.0
    tier_durations_ms: Dict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )
    transitions_total: int = 0

    def transition_tier(self, to_tier: str):
        """Record transition to a placement tier"""
        now_ms = time.perf_counter() * 1000

        # Record duration in previous tier
        if self.current_tier:
            duration_ms = now_ms - self.tier_entry_time_ms
            self.tier_durations_ms[self.current_tier] += duration_ms

        # Transition to new tier
        self.current_tier = to_tier
        self.tier_entry_time_ms = now_ms
        self.transitions_total += 1


# ============================================================================
# ThermalMetrics Class
# ============================================================================


class ThermalMetrics:
    """
    Thermal metrics collection and Prometheus export

    This class provides comprehensive thermal monitoring including:
    - Temperature tracking with histograms (P50/P95/P99)
    - Power consumption monitoring (CPU/GPU)
    - Placement tier transitions (upgrade/downgrade/emergency)
    - Thermal zone transitions and duration tracking
    - Cooldown violation detection (hysteresis enforcement)

    Key Features:
        - Low-overhead recording (<100µs P95)
        - Multi-dimensional Prometheus metrics with labels
        - Real-time statistics calculation (<5ms P95)
        - Hysteresis validation (cooldown violations target: 0)
        - Placement transition rate tracking (target: 68/hour)

    Prometheus Metrics:
        - k1_thermal_temperature_celsius{zone}: Temperature histogram
        - k1_thermal_power_watts{component}: Power histogram
        - k1_thermal_placement_changes_total{from_tier, to_tier, reason}: Transition counter
        - k1_thermal_zone_duration_seconds{zone}: Zone duration gauge
        - k1_thermal_placement_cooldown_violations_total: Violation counter

    Usage Example:
        metrics = ThermalMetrics()

        # Record temperature reading
        metrics.record_temperature(72.5, zone="WARM")

        # Record power consumption
        metrics.record_power(10.5, component="cpu")

        # Record placement transition
        metrics.record_placement_transition(
            from_tier="NPU",
            to_tier="GPU",
            reason="downgrade"
        )

        # Get statistics
        stats = metrics.get_statistics()
        print(f"P95 temp: {stats.temperature_p95_c}°C")
        print(f"Transitions/hour: {stats.transitions_per_hour}")

    Performance:
        - Metric recording: <100µs P95
        - Statistics calculation: <5ms P95
        - Memory overhead: ~10KB per 1000 samples

    Related ADRs:
        - ADR-0026: Thermal Hysteresis Matrix (asymmetric thresholds, cooldown)
        - ADR-0026c: Model Placement Integration (thermal cascade)
    """

    # Tier to numeric mapping for gauge (0=NPU, 1=GPU, 2=CPU, 3=Remote)
    TIER_TO_NUMERIC = {"NPU": 0, "GPU": 1, "CPU": 2, "REMOTE": 3}

    def __init__(self):
        """
        Initialize thermal metrics collection

        Sets up Prometheus metrics, tracking state, and statistics collectors.
        """
        # Zone tracking
        self.zone_tracking = ZoneTracking()

        # Placement tracking
        self.placement_tracking = PlacementTracking()

        # Cooldown violations
        self.cooldown_violations_count = 0

        # Temperature samples (for percentile calculation)
        self.temperature_samples: List[float] = []

        # Power samples (for average/percentile calculation)
        self.power_samples: List[float] = []

        # Initialization time
        self.init_time_ms = time.perf_counter() * 1000

        logger.info("thermal_metrics_initialized", init_time_ms=self.init_time_ms)

    def record_temperature(self, temperature_c: float, zone: str) -> None:
        """
        Record temperature reading

        Records temperature to Prometheus histogram (for P50/P95/P99) and gauge
        (for current value). Also tracks temperature samples for statistics.

        Args:
            temperature_c: Temperature in Celsius
            zone: Thermal zone (COOL, WARM, HOT, CRITICAL, EMERGENCY)

        Metrics Updated:
            - k1_thermal_temperature_celsius{zone}: Histogram observation
            - k1_thermal_temperature_latest_celsius{zone, component}: Gauge

        Example:
            metrics.record_temperature(72.5, zone="WARM")
            metrics.record_temperature(88.0, zone="CRITICAL")

        Performance: <100µs P95
        """
        # Record to Prometheus histogram (for percentiles)
        thermal_temperature_celsius.labels(zone=zone).observe(temperature_c)

        # Update latest temperature gauge
        thermal_temperature_latest_celsius.labels(zone=zone, component="device").set(
            temperature_c
        )

        # Store sample for statistics
        self.temperature_samples.append(temperature_c)

        # Trim samples to last 1000 (memory management)
        if len(self.temperature_samples) > 1000:
            self.temperature_samples = self.temperature_samples[-1000:]

        logger.debug("temperature_recorded", temperature_c=temperature_c, zone=zone)

    def record_power(self, power_w: float, component: str) -> None:
        """
        Record power consumption

        Records power consumption to Prometheus histogram and gauge. Tracks
        power samples for average/percentile calculation.

        Args:
            power_w: Power in Watts
            component: Component name (cpu, gpu, npu)

        Metrics Updated:
            - k1_thermal_power_watts{component}: Histogram observation
            - k1_thermal_power_latest_watts{component}: Gauge

        Example:
            metrics.record_power(10.5, component="cpu")
            metrics.record_power(18.0, component="gpu")

        Performance: <100µs P95
        """
        # Record to Prometheus histogram
        thermal_power_watts.labels(component=component).observe(power_w)

        # Update latest power gauge
        thermal_power_latest_watts.labels(component=component).set(power_w)

        # Store sample for statistics
        self.power_samples.append(power_w)

        # Trim samples to last 1000
        if len(self.power_samples) > 1000:
            self.power_samples = self.power_samples[-1000:]

        logger.debug("power_recorded", power_w=power_w, component=component)

    def record_placement_transition(
        self,
        from_tier: str,
        to_tier: str,
        reason: str,
        latency_ms: Optional[float] = None,
    ) -> None:
        """
        Record placement tier transition

        Records transition between placement tiers (NPU/GPU/CPU/Remote) with
        reason (upgrade/downgrade/emergency_jump). Tracks transition count
        for rate calculation (target: 68/hour).

        Args:
            from_tier: Source tier (NPU, GPU, CPU, REMOTE)
            to_tier: Target tier (NPU, GPU, CPU, REMOTE)
            reason: Transition reason (upgrade, downgrade, emergency_jump)
            latency_ms: Transition latency in milliseconds (optional)

        Metrics Updated:
            - k1_thermal_placement_changes_total{from_tier, to_tier, reason}: Counter
            - k1_thermal_placement_latest{tier}: Gauge
            - k1_thermal_placement_transition_latency_ms: Summary (if latency provided)

        Example:
            metrics.record_placement_transition(
                from_tier="NPU",
                to_tier="GPU",
                reason="downgrade",
                latency_ms=85.5
            )

        Performance: <100µs P95
        """
        # Increment transition counter
        thermal_placement_changes_total.labels(
            from_tier=from_tier, to_tier=to_tier, reason=reason
        ).inc()

        # Update latest placement tier gauge
        if to_tier in self.TIER_TO_NUMERIC:
            thermal_placement_latest.labels(tier=to_tier).set(
                self.TIER_TO_NUMERIC[to_tier]
            )

        # Record transition latency (if provided)
        if latency_ms is not None:
            thermal_placement_transition_latency_ms.observe(latency_ms)

        # Update placement tracking
        self.placement_tracking.transition_tier(to_tier)

        logger.info(
            "placement_transition_recorded",
            from_tier=from_tier,
            to_tier=to_tier,
            reason=reason,
            latency_ms=latency_ms,
        )

    def record_zone_transition(self, from_zone: str, to_zone: str) -> None:
        """
        Record thermal zone transition

        Records transition between thermal zones (COOL/WARM/HOT/CRITICAL/EMERGENCY).
        Tracks zone duration for distribution calculation.

        Args:
            from_zone: Source zone (COOL, WARM, HOT, CRITICAL, EMERGENCY)
            to_zone: Target zone (COOL, WARM, HOT, CRITICAL, EMERGENCY)

        Metrics Updated:
            - k1_thermal_zone_changes_total{from_zone, to_zone}: Counter
            - k1_thermal_zone_duration_seconds{zone}: Gauge

        Example:
            metrics.record_zone_transition(from_zone="WARM", to_zone="HOT")
            metrics.record_zone_transition(from_zone="HOT", to_zone="CRITICAL")

        Performance: <100µs P95
        """
        # Increment zone transition counter
        thermal_zone_changes_total.labels(from_zone=from_zone, to_zone=to_zone).inc()

        # Update zone tracking
        self.zone_tracking.enter_zone(to_zone)

        # Update zone duration gauge (convert ms to seconds)
        for zone, duration_ms in self.zone_tracking.zone_durations_ms.items():
            thermal_zone_duration_seconds.labels(zone=zone).set(duration_ms / 1000.0)

        logger.info("zone_transition_recorded", from_zone=from_zone, to_zone=to_zone)

    def record_cooldown_violation(self, from_tier: str, to_tier: str) -> None:
        """
        Record cooldown period violation

        Records attempted transition during cooldown period (hysteresis enforcement).
        Target: 0 violations (perfect hysteresis adherence).

        Args:
            from_tier: Source tier (NPU, GPU, CPU, REMOTE)
            to_tier: Target tier (NPU, GPU, CPU, REMOTE)

        Metrics Updated:
            - k1_thermal_placement_cooldown_violations_total{from_tier, to_tier}: Counter

        Example:
            metrics.record_cooldown_violation(from_tier="GPU", to_tier="NPU")
            # Attempted upgrade during 10s cooldown period

        Performance: <100µs P95
        """
        # Increment violation counter
        thermal_placement_cooldown_violations_total.labels(
            from_tier=from_tier, to_tier=to_tier
        ).inc()

        # Update local count
        self.cooldown_violations_count += 1

        logger.warning(
            "cooldown_violation_recorded",
            from_tier=from_tier,
            to_tier=to_tier,
            total_violations=self.cooldown_violations_count,
        )

    def get_statistics(self) -> ThermalStatistics:
        """
        Get thermal statistics summary

        Calculates comprehensive thermal statistics including:
        - Temperature percentiles (P50/P95/P99)
        - Power consumption (average, P95)
        - Placement tier distribution (% time on each tier)
        - Transition rate (transitions/hour, target: 68/hour)
        - Thermal zone distribution (% time in each zone)
        - Cooldown violations (target: 0)

        Returns:
            ThermalStatistics with all metrics

        Example:
            stats = metrics.get_statistics()
            print(f"P95 temp: {stats.temperature_p95_c}°C")
            print(f"NPU usage: {stats.placement_npu_pct}%")
            print(f"Transitions/hour: {stats.transitions_per_hour}")
            print(f"Cooldown violations: {stats.cooldown_violations_total}")

        Performance: <5ms P95
        """
        stats = ThermalStatistics()

        # Calculate temperature percentiles
        if self.temperature_samples:
            sorted_temps = sorted(self.temperature_samples)
            n = len(sorted_temps)

            stats.temperature_p50_c = sorted_temps[int(n * 0.50)]
            stats.temperature_p95_c = sorted_temps[int(n * 0.95)]
            stats.temperature_p99_c = sorted_temps[int(n * 0.99)]

        # Calculate power statistics
        if self.power_samples:
            stats.power_avg_w = sum(self.power_samples) / len(self.power_samples)

            sorted_power = sorted(self.power_samples)
            n = len(sorted_power)
            stats.power_p95_w = sorted_power[int(n * 0.95)]

        # Calculate placement tier distribution
        total_placement_duration_ms = sum(
            self.placement_tracking.tier_durations_ms.values()
        )
        if total_placement_duration_ms > 0:
            stats.placement_npu_pct = (
                self.placement_tracking.tier_durations_ms.get("NPU", 0.0)
                / total_placement_duration_ms
                * 100.0
            )
            stats.placement_gpu_pct = (
                self.placement_tracking.tier_durations_ms.get("GPU", 0.0)
                / total_placement_duration_ms
                * 100.0
            )
            stats.placement_cpu_pct = (
                self.placement_tracking.tier_durations_ms.get("CPU", 0.0)
                / total_placement_duration_ms
                * 100.0
            )
            stats.placement_remote_pct = (
                self.placement_tracking.tier_durations_ms.get("REMOTE", 0.0)
                / total_placement_duration_ms
                * 100.0
            )

            # Update Prometheus gauges for distribution
            thermal_placement_tier_distribution_pct.labels(tier="NPU").set(
                stats.placement_npu_pct
            )
            thermal_placement_tier_distribution_pct.labels(tier="GPU").set(
                stats.placement_gpu_pct
            )
            thermal_placement_tier_distribution_pct.labels(tier="CPU").set(
                stats.placement_cpu_pct
            )
            thermal_placement_tier_distribution_pct.labels(tier="REMOTE").set(
                stats.placement_remote_pct
            )

        # Calculate transition rate (transitions/hour)
        now_ms = time.perf_counter() * 1000
        uptime_hours = (now_ms - self.init_time_ms) / (1000.0 * 3600.0)

        stats.transitions_total = self.placement_tracking.transitions_total
        if uptime_hours > 0:
            stats.transitions_per_hour = stats.transitions_total / uptime_hours

        # Calculate thermal zone distribution
        total_zone_duration_ms = sum(self.zone_tracking.zone_durations_ms.values())
        if total_zone_duration_ms > 0:
            stats.zone_cool_pct = (
                self.zone_tracking.zone_durations_ms.get("COOL", 0.0)
                / total_zone_duration_ms
                * 100.0
            )
            stats.zone_warm_pct = (
                self.zone_tracking.zone_durations_ms.get("WARM", 0.0)
                / total_zone_duration_ms
                * 100.0
            )
            stats.zone_hot_pct = (
                self.zone_tracking.zone_durations_ms.get("HOT", 0.0)
                / total_zone_duration_ms
                * 100.0
            )
            stats.zone_critical_pct = (
                self.zone_tracking.zone_durations_ms.get("CRITICAL", 0.0)
                / total_zone_duration_ms
                * 100.0
            )
            stats.zone_emergency_pct = (
                self.zone_tracking.zone_durations_ms.get("EMERGENCY", 0.0)
                / total_zone_duration_ms
                * 100.0
            )

        # Cooldown violations
        stats.cooldown_violations_total = self.cooldown_violations_count

        logger.debug(
            "statistics_calculated",
            temperature_p95_c=stats.temperature_p95_c,
            transitions_per_hour=stats.transitions_per_hour,
            cooldown_violations=stats.cooldown_violations_total,
        )

        return stats


# ============================================================================
# WARD Test Examples
# ============================================================================

"""
WARD Test Suite for ThermalMetrics

File: tests/k1/l5_infrastructure/thermal/test_metrics.py

```python
from ward import test, fixture
import time

from k1.l5_infrastructure.thermal.metrics import (
    ThermalMetrics,
    ThermalStatistics
)


@fixture
def metrics():
    return ThermalMetrics()


@test("record_temperature updates histogram and gauge")
def _(m=metrics):
    m.record_temperature(72.5, zone="WARM")

    assert len(m.temperature_samples) == 1
    assert m.temperature_samples[0] == 72.5


@test("record_power updates histogram and gauge")
def _(m=metrics):
    m.record_power(10.5, component="cpu")
    m.record_power(18.0, component="gpu")

    assert len(m.power_samples) == 2
    assert m.power_samples[0] == 10.5
    assert m.power_samples[1] == 18.0


@test("record_placement_transition tracks transitions")
def _(m=metrics):
    m.record_placement_transition(
        from_tier="NPU",
        to_tier="GPU",
        reason="downgrade",
        latency_ms=85.5
    )

    assert m.placement_tracking.transitions_total == 1
    assert m.placement_tracking.current_tier == "GPU"


@test("record_zone_transition tracks zone changes")
def _(m=metrics):
    m.record_zone_transition(from_zone="COOL", to_zone="WARM")

    assert m.zone_tracking.current_zone == "WARM"


@test("record_cooldown_violation increments counter")
def _(m=metrics):
    m.record_cooldown_violation(from_tier="GPU", to_tier="NPU")

    assert m.cooldown_violations_count == 1


@test("get_statistics calculates percentiles")
def _(m=metrics):
    # Record temperature samples
    temperatures = [60, 65, 70, 72, 75, 78, 80, 85, 88, 90]
    for temp in temperatures:
        m.record_temperature(temp, zone="WARM")

    stats = m.get_statistics()

    assert stats.temperature_p50_c == 75.0  # Median
    assert stats.temperature_p95_c >= 88.0  # P95


@test("get_statistics calculates placement distribution")
def _(m=metrics):
    # Simulate placement transitions
    m.placement_tracking.tier_durations_ms["NPU"] = 6000.0  # 6s
    m.placement_tracking.tier_durations_ms["GPU"] = 4000.0  # 4s

    stats = m.get_statistics()

    assert stats.placement_npu_pct == 60.0
    assert stats.placement_gpu_pct == 40.0


@test("get_statistics calculates transition rate")
def _(m=metrics):
    # Simulate transitions
    for i in range(10):
        m.record_placement_transition(
            from_tier="NPU",
            to_tier="GPU",
            reason="downgrade"
        )
        time.sleep(0.01)

    stats = m.get_statistics()

    assert stats.transitions_total == 10
    assert stats.transitions_per_hour > 0


@test("temperature samples trimmed to last 1000")
def _(m=metrics):
    # Record 1500 samples
    for i in range(1500):
        m.record_temperature(70.0 + (i % 20), zone="WARM")

    assert len(m.temperature_samples) == 1000


@test("statistics dict serialization")
def _(m=metrics):
    m.record_temperature(72.5, zone="WARM")
    m.record_power(10.5, component="cpu")

    stats = m.get_statistics()
    stats_dict = stats.to_dict()

    assert 'temperature' in stats_dict
    assert 'power' in stats_dict
    assert 'placement' in stats_dict
    assert 'transitions' in stats_dict
```

Run tests:
    python -m ward test --path tests/k1/l5_infrastructure/thermal/test_metrics.py

Expected performance:
    - Metric recording: <100µs P95
    - Statistics calculation: <5ms P95
    - Memory overhead: ~10KB per 1000 samples
"""
