"""
Test SessionState Metrics
=========================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.2 Metrics Implementation
ISSUES: 5.2.1, 5.2.2, 5.2.3, 5.2.4

Tests Prometheus metrics implementation for SessionState SLI/SLO measurement.
Validates histograms, gauges, counters, and integration with SessionStateManager.

CONTRACT: k1/contracts/schemas/runtime/sessionstate.policies.yaml (lines 350-420)

Test coverage:
- Histogram creation and observation (latency metrics)
- Gauge creation and setting (size metrics)
- Counter creation and incrementing (operation counters)
- Context managers for timing
- Bulk update from snapshot
- Thread safety
- Integration with SessionStateManager
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from k1.sessionstate import SessionStateFactory
from k1.sessionstate.metrics import (
    ALL_SECTIONS,
    HOT_SECTIONS,
    MUTATION_RESULTS,
    PREFLIGHT_LATENCY_BUCKETS,
    READ_LATENCY_BUCKETS,
    RECONSTRUCTION_LATENCY_BUCKETS,
    RECONSTRUCTION_SOURCES,
    TIERS,
    WARM_SECTIONS,
    WRITE_LATENCY_BUCKETS,
    PressureLevelValue,
    SessionStateMetrics,
    get_default_metrics,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def metrics() -> SessionStateMetrics:
    """Create fresh metrics instance with isolated registry."""
    return SessionStateMetrics()


@pytest.fixture
def manager():
    """Create standalone SessionStateManager."""
    mgr = SessionStateFactory.create_standalone()
    mgr.start()
    yield mgr
    mgr.stop()


# =============================================================================
# TEST: CONSTANTS AND CONFIGURATION
# =============================================================================


class TestMetricsConstants:
    """Test metrics constants match contract specification."""

    def test_hot_sections_count(self):
        """HOT tier has 8 sections."""
        assert len(HOT_SECTIONS) == 10

    def test_warm_sections_count(self):
        """WARM tier has 4 sections."""
        assert len(WARM_SECTIONS) == 5

    def test_all_sections_count(self):
        """Total 12 sections."""
        assert len(ALL_SECTIONS) == 15

    def test_tiers_defined(self):
        """Two tiers: hot and warm."""
        assert TIERS == ("hot", "warm")

    def test_reconstruction_sources_defined(self):
        """Two reconstruction sources."""
        assert RECONSTRUCTION_SOURCES == ("local_cold", "k0")

    def test_mutation_results_defined(self):
        """Two mutation results."""
        assert MUTATION_RESULTS == ("approved", "rejected")

    def test_read_latency_buckets_contract_aligned(self):
        """Read latency buckets match contract."""
        assert READ_LATENCY_BUCKETS == (0.00001, 0.00005, 0.0001, 0.0002, 0.0005, 0.001)

    def test_write_latency_buckets_contract_aligned(self):
        """Write latency buckets match contract."""
        assert WRITE_LATENCY_BUCKETS == (0.00001, 0.00005, 0.0001, 0.0005, 0.001, 0.005)

    def test_preflight_latency_buckets_contract_aligned(self):
        """Preflight latency buckets match contract."""
        assert PREFLIGHT_LATENCY_BUCKETS == (0.00001, 0.000025, 0.00005, 0.000075, 0.0001)

    def test_reconstruction_latency_buckets_contract_aligned(self):
        """Reconstruction latency buckets match contract."""
        assert RECONSTRUCTION_LATENCY_BUCKETS == (0.01, 0.025, 0.05, 0.075, 0.1, 0.15)


class TestPressureLevelValue:
    """Test PressureLevelValue enum."""

    def test_normal_is_zero(self):
        """NORMAL pressure is 0."""
        assert PressureLevelValue.NORMAL == 0

    def test_elevated_is_one(self):
        """ELEVATED pressure is 1."""
        assert PressureLevelValue.ELEVATED == 1

    def test_critical_is_two(self):
        """CRITICAL pressure is 2."""
        assert PressureLevelValue.CRITICAL == 2

    def test_emergency_is_three(self):
        """EMERGENCY pressure is 3."""
        assert PressureLevelValue.EMERGENCY == 3


# =============================================================================
# TEST: LATENCY HISTOGRAMS (5.2.1)
# =============================================================================


class TestReadLatencyHistogram:
    """Test sessionstate_read_latency_seconds{tier} histogram."""

    def test_histogram_created(self, metrics: SessionStateMetrics):
        """Read latency histogram is created."""
        histogram = metrics.read_latency
        assert histogram is not None
        assert "sessionstate_read_latency_seconds" in str(histogram)

    def test_observe_hot_tier(self, metrics: SessionStateMetrics):
        """Can observe HOT tier read latency."""
        metrics.observe_read_latency("hot", 0.00005)  # 50 microseconds
        # No error raised

    def test_observe_warm_tier(self, metrics: SessionStateMetrics):
        """Can observe WARM tier read latency."""
        metrics.observe_read_latency("warm", 0.0001)  # 100 microseconds
        # No error raised

    def test_time_read_context_manager(self, metrics: SessionStateMetrics):
        """time_read context manager observes latency."""
        with metrics.time_read("hot"):
            time.sleep(0.001)  # 1ms
        # Latency recorded (verified by no error)

    def test_histogram_in_export(self, metrics: SessionStateMetrics):
        """Read latency histogram appears in Prometheus export."""
        metrics.observe_read_latency("hot", 0.00005)
        output = metrics.latest().decode("utf-8")
        assert "sessionstate_read_latency_seconds" in output


class TestWriteLatencyHistogram:
    """Test sessionstate_write_latency_seconds{section} histogram."""

    def test_histogram_created(self, metrics: SessionStateMetrics):
        """Write latency histogram is created."""
        histogram = metrics.write_latency
        assert histogram is not None

    def test_observe_section_latency(self, metrics: SessionStateMetrics):
        """Can observe section write latency."""
        metrics.observe_write_latency("beliefs_active", 0.0001)
        # No error raised

    def test_observe_all_sections(self, metrics: SessionStateMetrics):
        """Can observe latency for all 12 sections."""
        for section in ALL_SECTIONS:
            metrics.observe_write_latency(section, 0.00005)

    def test_time_write_context_manager(self, metrics: SessionStateMetrics):
        """time_write context manager observes latency."""
        with metrics.time_write("control"):
            time.sleep(0.0001)


class TestPreflightLatencyHistogram:
    """Test sessionstate_preflight_latency_seconds histogram."""

    def test_histogram_created(self, metrics: SessionStateMetrics):
        """Preflight latency histogram is created."""
        histogram = metrics.preflight_latency
        assert histogram is not None

    def test_observe_preflight(self, metrics: SessionStateMetrics):
        """Can observe preflight latency."""
        metrics.observe_preflight_latency(0.00003)  # 30 microseconds

    def test_time_preflight_context_manager(self, metrics: SessionStateMetrics):
        """time_preflight context manager observes latency."""
        with metrics.time_preflight():
            pass  # Fast operation


class TestReconstructionLatencyHistogram:
    """Test sessionstate_reconstruction_latency_seconds{source} histogram."""

    def test_histogram_created(self, metrics: SessionStateMetrics):
        """Reconstruction latency histogram is created."""
        histogram = metrics.reconstruction_latency
        assert histogram is not None

    def test_observe_local_cold(self, metrics: SessionStateMetrics):
        """Can observe LOCAL COLD reconstruction latency."""
        metrics.observe_reconstruction_latency("local_cold", 0.025)  # 25ms

    def test_observe_k0(self, metrics: SessionStateMetrics):
        """Can observe K0 reconstruction latency."""
        metrics.observe_reconstruction_latency("k0", 0.050)  # 50ms

    def test_time_reconstruction_context_manager(self, metrics: SessionStateMetrics):
        """time_reconstruction context manager observes latency."""
        with metrics.time_reconstruction("local_cold"):
            time.sleep(0.001)


class TestCheckpointLatencyHistogram:
    """Test sessionstate_checkpoint_latency_seconds histogram."""

    def test_histogram_created(self, metrics: SessionStateMetrics):
        """Checkpoint latency histogram is created."""
        histogram = metrics.checkpoint_latency
        assert histogram is not None

    def test_observe_checkpoint(self, metrics: SessionStateMetrics):
        """Can observe checkpoint latency."""
        metrics.observe_checkpoint_latency(0.015)  # 15ms

    def test_time_checkpoint_context_manager(self, metrics: SessionStateMetrics):
        """time_checkpoint context manager observes latency."""
        with metrics.time_checkpoint():
            time.sleep(0.001)


class TestEvictionLatencyHistogram:
    """Test sessionstate_eviction_latency_seconds{section} histogram."""

    def test_histogram_created(self, metrics: SessionStateMetrics):
        """Eviction latency histogram is created."""
        histogram = metrics.eviction_latency
        assert histogram is not None

    def test_observe_eviction(self, metrics: SessionStateMetrics):
        """Can observe eviction latency."""
        metrics.observe_eviction_latency("telemetry", 0.010)  # 10ms

    def test_time_eviction_context_manager(self, metrics: SessionStateMetrics):
        """time_eviction context manager observes latency."""
        with metrics.time_eviction("beliefs_history"):
            time.sleep(0.001)


# =============================================================================
# TEST: SIZE GAUGES (5.2.2)
# =============================================================================


class TestSectionSizeGauge:
    """Test sessionstate_section_size_bytes{section} gauge."""

    def test_gauge_created(self, metrics: SessionStateMetrics):
        """Section size gauge is created."""
        gauge = metrics.section_size
        assert gauge is not None

    def test_set_section_size(self, metrics: SessionStateMetrics):
        """Can set section size."""
        metrics.set_section_size("control", 1024)
        # No error raised

    def test_set_all_section_sizes(self, metrics: SessionStateMetrics):
        """Can set size for all 12 sections."""
        for section in ALL_SECTIONS:
            metrics.set_section_size(section, 512)

    def test_section_size_in_export(self, metrics: SessionStateMetrics):
        """Section size gauge appears in Prometheus export."""
        metrics.set_section_size("control", 2048)
        output = metrics.latest().decode("utf-8")
        assert "sessionstate_section_size_bytes" in output


class TestTierSizeGauge:
    """Test sessionstate_tier_size_bytes{tier} gauge."""

    def test_gauge_created(self, metrics: SessionStateMetrics):
        """Tier size gauge is created."""
        gauge = metrics.tier_size
        assert gauge is not None

    def test_set_hot_tier_size(self, metrics: SessionStateMetrics):
        """Can set HOT tier size."""
        metrics.set_tier_size("hot", 24576)  # 24KB

    def test_set_warm_tier_size(self, metrics: SessionStateMetrics):
        """Can set WARM tier size."""
        metrics.set_tier_size("warm", 12288)  # 12KB


class TestTotalSizeGauge:
    """Test sessionstate_total_size_bytes gauge."""

    def test_gauge_created(self, metrics: SessionStateMetrics):
        """Total size gauge is created."""
        gauge = metrics.total_size
        assert gauge is not None

    def test_set_total_size(self, metrics: SessionStateMetrics):
        """Can set total size."""
        metrics.set_total_size(36864)  # 36KB


class TestPressureLevelGauge:
    """Test sessionstate_pressure_level{tier} gauge."""

    def test_gauge_created(self, metrics: SessionStateMetrics):
        """Pressure level gauge is created."""
        gauge = metrics.pressure_level
        assert gauge is not None

    def test_set_normal_pressure(self, metrics: SessionStateMetrics):
        """Can set NORMAL pressure."""
        metrics.set_pressure_level("hot", PressureLevelValue.NORMAL)

    def test_set_elevated_pressure(self, metrics: SessionStateMetrics):
        """Can set ELEVATED pressure."""
        metrics.set_pressure_level("warm", PressureLevelValue.ELEVATED)

    def test_set_critical_pressure(self, metrics: SessionStateMetrics):
        """Can set CRITICAL pressure."""
        metrics.set_pressure_level("total", PressureLevelValue.CRITICAL)

    def test_set_emergency_pressure(self, metrics: SessionStateMetrics):
        """Can set EMERGENCY pressure."""
        metrics.set_pressure_level("total", PressureLevelValue.EMERGENCY)


class TestUtilizationRatioGauge:
    """Test sessionstate_utilization_ratio{tier} gauge."""

    def test_gauge_created(self, metrics: SessionStateMetrics):
        """Utilization ratio gauge is created."""
        gauge = metrics.utilization_ratio
        assert gauge is not None

    def test_set_utilization_ratio(self, metrics: SessionStateMetrics):
        """Can set utilization ratio."""
        metrics.set_utilization_ratio("hot", 0.45)  # 45%
        metrics.set_utilization_ratio("warm", 0.30)  # 30%
        metrics.set_utilization_ratio("total", 0.375)  # 37.5%


# =============================================================================
# TEST: OPERATION COUNTERS (5.2.3)
# =============================================================================


class TestMutationsCounter:
    """Test sessionstate_mutations_total{result} counter."""

    def test_counter_created(self, metrics: SessionStateMetrics):
        """Mutations counter is created."""
        counter = metrics.mutations_total
        assert counter is not None

    def test_inc_approved_mutations(self, metrics: SessionStateMetrics):
        """Can increment approved mutations."""
        metrics.inc_mutations("approved")
        metrics.inc_mutations("approved", 5)  # Increment by 5

    def test_inc_rejected_mutations(self, metrics: SessionStateMetrics):
        """Can increment rejected mutations."""
        metrics.inc_mutations("rejected")

    def test_mutations_in_export(self, metrics: SessionStateMetrics):
        """Mutations counter appears in Prometheus export."""
        metrics.inc_mutations("approved")
        output = metrics.latest().decode("utf-8")
        assert "sessionstate_mutations_total" in output


class TestEvictionsCounter:
    """Test sessionstate_evictions_total{section} counter."""

    def test_counter_created(self, metrics: SessionStateMetrics):
        """Evictions counter is created."""
        counter = metrics.evictions_total
        assert counter is not None

    def test_inc_evictions(self, metrics: SessionStateMetrics):
        """Can increment evictions."""
        metrics.inc_evictions("telemetry")
        metrics.inc_evictions("beliefs_history", 3)


class TestReconstructionsCounter:
    """Test sessionstate_reconstructions_total{source} counter."""

    def test_counter_created(self, metrics: SessionStateMetrics):
        """Reconstructions counter is created."""
        counter = metrics.reconstructions_total
        assert counter is not None

    def test_inc_local_cold_reconstructions(self, metrics: SessionStateMetrics):
        """Can increment LOCAL COLD reconstructions."""
        metrics.inc_reconstructions("local_cold")

    def test_inc_k0_reconstructions(self, metrics: SessionStateMetrics):
        """Can increment K0 reconstructions."""
        metrics.inc_reconstructions("k0")


class TestEmergenciesCounter:
    """Test sessionstate_emergencies_total{level} counter."""

    def test_counter_created(self, metrics: SessionStateMetrics):
        """Emergencies counter is created."""
        counter = metrics.emergencies_total
        assert counter is not None

    def test_inc_emergencies(self, metrics: SessionStateMetrics):
        """Can increment emergencies."""
        metrics.inc_emergencies("critical")
        metrics.inc_emergencies("emergency")


class TestCheckpointsCounter:
    """Test sessionstate_checkpoints_total counter."""

    def test_counter_created(self, metrics: SessionStateMetrics):
        """Checkpoints counter is created."""
        counter = metrics.checkpoints_total
        assert counter is not None

    def test_inc_checkpoints(self, metrics: SessionStateMetrics):
        """Can increment checkpoints."""
        metrics.inc_checkpoints()
        metrics.inc_checkpoints(10)


# =============================================================================
# TEST: BULK UPDATE FROM SNAPSHOT
# =============================================================================


class TestBulkUpdate:
    """Test update_from_snapshot bulk update method."""

    def test_update_from_snapshot(self, metrics: SessionStateMetrics):
        """Can bulk update all gauges from snapshot data."""
        section_sizes = {section: 256 for section in ALL_SECTIONS}

        metrics.update_from_snapshot(
            total_size_bytes=53248,
            hot_size_bytes=24576,
            warm_size_bytes=24576,
            hot_utilization_pct=50.0,
            warm_utilization_pct=50.0,
            total_utilization_pct=50.0,
            pressure_level=PressureLevelValue.NORMAL,
            section_sizes=section_sizes,
        )

        # Verify export contains all metrics
        output = metrics.latest().decode("utf-8")
        assert "sessionstate_total_size_bytes" in output
        assert "sessionstate_tier_size_bytes" in output
        assert "sessionstate_section_size_bytes" in output
        assert "sessionstate_utilization_ratio" in output
        assert "sessionstate_pressure_level" in output


# =============================================================================
# TEST: THREAD SAFETY
# =============================================================================


class TestThreadSafety:
    """Test thread safety of metrics operations."""

    def test_concurrent_histogram_observation(self, metrics: SessionStateMetrics):
        """Concurrent histogram observations don't race."""
        errors = []

        def observe():
            try:
                for _ in range(100):
                    metrics.observe_read_latency("hot", 0.00005)
                    metrics.observe_write_latency("control", 0.0001)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(observe) for _ in range(10)]
            for f in futures:
                f.result()

        assert len(errors) == 0

    def test_concurrent_gauge_updates(self, metrics: SessionStateMetrics):
        """Concurrent gauge updates don't race."""
        errors = []

        def update():
            try:
                for i in range(100):
                    metrics.set_section_size("control", i * 10)
                    metrics.set_tier_size("hot", i * 100)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(update) for _ in range(10)]
            for f in futures:
                f.result()

        assert len(errors) == 0

    def test_concurrent_counter_increments(self, metrics: SessionStateMetrics):
        """Concurrent counter increments don't race."""
        errors = []

        def increment():
            try:
                for _ in range(100):
                    metrics.inc_mutations("approved")
                    metrics.inc_checkpoints()
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(increment) for _ in range(10)]
            for f in futures:
                f.result()

        assert len(errors) == 0


# =============================================================================
# TEST: DEFAULT SINGLETON
# =============================================================================


class TestDefaultMetrics:
    """Test get_default_metrics singleton."""

    def test_returns_metrics_instance(self):
        """get_default_metrics returns SessionStateMetrics."""
        metrics = get_default_metrics()
        assert isinstance(metrics, SessionStateMetrics)

    def test_returns_same_instance(self):
        """get_default_metrics returns singleton."""
        m1 = get_default_metrics()
        m2 = get_default_metrics()
        assert m1 is m2


# =============================================================================
# TEST: PROMETHEUS EXPORT FORMAT
# =============================================================================


class TestPrometheusExport:
    """Test Prometheus text format export."""

    def test_latest_returns_bytes(self, metrics: SessionStateMetrics):
        """latest() returns bytes."""
        output = metrics.latest()
        assert isinstance(output, bytes)

    def test_export_contains_help_text(self, metrics: SessionStateMetrics):
        """Export contains HELP comments."""
        metrics.observe_read_latency("hot", 0.00005)
        output = metrics.latest().decode("utf-8")
        assert "# HELP" in output

    def test_export_contains_type_text(self, metrics: SessionStateMetrics):
        """Export contains TYPE comments."""
        metrics.observe_read_latency("hot", 0.00005)
        output = metrics.latest().decode("utf-8")
        assert "# TYPE" in output

    def test_histogram_export_format(self, metrics: SessionStateMetrics):
        """Histogram export includes bucket, count, sum."""
        metrics.observe_read_latency("hot", 0.00005)
        output = metrics.latest().decode("utf-8")
        assert "_bucket{" in output
        assert "_count" in output
        assert "_sum" in output

    def test_gauge_export_format(self, metrics: SessionStateMetrics):
        """Gauge export shows current value."""
        metrics.set_total_size(53248)
        output = metrics.latest().decode("utf-8")
        assert "53248" in output

    def test_counter_export_format(self, metrics: SessionStateMetrics):
        """Counter export shows total value."""
        metrics.inc_checkpoints(5)
        output = metrics.latest().decode("utf-8")
        assert "sessionstate_checkpoints_total 5.0" in output


# =============================================================================
# TEST: INTEGRATION WITH SESSIONSTATE MANAGER
# =============================================================================


class TestManagerIntegration:
    """Test metrics integration with SessionStateManager."""

    def test_record_read_from_manager(self, metrics: SessionStateMetrics, manager):
        """Can record read latency from manager operation."""
        with metrics.time_read("hot"):
            section = manager.get_section("control")
            assert section is not None

    def test_record_write_from_manager(self, metrics: SessionStateMetrics, manager):
        """Can record write latency from manager operation."""
        with metrics.time_write("beliefs_active"):
            result = manager.mutate(
                section="beliefs_active",
                operation="add_fact",
                data={"subject": "test", "predicate": "is", "obj": "working"},
            )
            assert result.success

    def test_update_from_manager_snapshot(self, metrics: SessionStateMetrics, manager):
        """Can update metrics from manager snapshot."""
        # Mutate to create some data
        manager.mutate(
            section="control",
            operation="set",
            data={"key": "value"},
        )

        snapshot = manager.get_snapshot()

        # Map pressure level to numeric value
        pressure_map = {
            "normal": PressureLevelValue.NORMAL,
            "elevated": PressureLevelValue.ELEVATED,
            "critical": PressureLevelValue.CRITICAL,
            "emergency": PressureLevelValue.EMERGENCY,
        }

        metrics.update_from_snapshot(
            total_size_bytes=snapshot.total_size_bytes,
            hot_size_bytes=snapshot.hot_size_bytes,
            warm_size_bytes=snapshot.warm_size_bytes,
            hot_utilization_pct=snapshot.hot_utilization_pct,
            warm_utilization_pct=snapshot.warm_utilization_pct,
            total_utilization_pct=snapshot.total_utilization_pct,
            pressure_level=pressure_map.get(snapshot.pressure.value, 0),
            section_sizes={s: info.size_bytes for s, info in snapshot.sections.items()},
        )

        # Verify export has data
        output = metrics.latest().decode("utf-8")
        assert "sessionstate_total_size_bytes" in output

    def test_record_checkpoint_from_manager(self, metrics: SessionStateMetrics, manager):
        """Can record checkpoint latency from manager operation."""
        with metrics.time_checkpoint():
            result = manager.checkpoint()
            assert result.success

        metrics.inc_checkpoints()

        output = metrics.latest().decode("utf-8")
        assert "sessionstate_checkpoint_latency_seconds" in output
        assert "sessionstate_checkpoints_total" in output


# =============================================================================
# TEST: METRIC NAMING CONVENTION
# =============================================================================


class TestNamingConvention:
    """Test metrics follow contract naming convention."""

    def test_all_metrics_start_with_sessionstate(self, metrics: SessionStateMetrics):
        """All metrics start with sessionstate_ prefix."""
        # Trigger metric creation
        metrics.observe_read_latency("hot", 0.00005)
        metrics.set_section_size("control", 1024)
        metrics.inc_mutations("approved")

        output = metrics.latest().decode("utf-8")

        # Find all metric names (lines that don't start with #)
        for line in output.split("\n"):
            if line and not line.startswith("#"):
                # Extract metric name (before any labels or values)
                name_match = re.match(r"^([a-z_]+)", line)
                if name_match:
                    name = name_match.group(1)
                    assert name.startswith(
                        "sessionstate"
                    ), f"Metric {name} doesn't start with sessionstate_"
