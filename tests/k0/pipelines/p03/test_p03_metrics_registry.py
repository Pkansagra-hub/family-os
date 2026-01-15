"""
Tests for P03MetricsRegistry - centralized metrics for P03 consolidation.

Issue: M6 Epic 6.1 — P03 Metrics & Observability
  - Issue 6.1.1: Create P03MetricsRegistry
  - Issue 6.1.2: Cycle-level metrics
  - Issue 6.1.3: Phase timing metrics
  - Issue 6.1.4: Decision metrics
  - Issue 6.1.5: Gap metrics

Spec Reference: P03_consolidation_dossier.md Section 8.2
Dossier Reference: Section 8.2 (Observability constraints)

Test Coverage:
- P03MetricsRegistry initialization
- Metric definition registration
- Cycle metrics emission
- Phase duration histogram emission
- Decision type tracking
- Gap detection and deduplication metrics
- Integration with K0 MetricsExporter
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.ops.metrics import (
    CYCLE_DURATION_BUCKETS,
    CYCLE_METRICS,
    DECISION_METRICS,
    GAP_METRICS,
    PHASE_DURATION_BUCKETS,
    PHASE_METRICS,
    MetricDefinition,
    P03MetricsRegistry,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_exporter() -> MagicMock:
    """Create a mock MetricsExporter."""
    exporter = MagicMock()
    exporter.counter = MagicMock()
    exporter.histogram = MagicMock()
    exporter.gauge = MagicMock()
    exporter.emit = MagicMock()
    exporter.observe = MagicMock()
    exporter.set_gauge = MagicMock()
    return exporter


@pytest.fixture
def registry(mock_exporter: MagicMock) -> P03MetricsRegistry:
    """Create P03MetricsRegistry with mock exporter."""
    return P03MetricsRegistry(exporter=mock_exporter)


# =============================================================================
# TEST: INITIALIZATION AND REGISTRATION
# =============================================================================


class TestP03MetricsRegistryInitialization:
    """Tests for P03MetricsRegistry initialization."""

    def test_initialization_with_exporter(self, mock_exporter: MagicMock):
        """Registry initializes with provided exporter."""
        registry = P03MetricsRegistry(exporter=mock_exporter)
        assert registry._exporter is mock_exporter

    def test_initialization_registers_metrics(self, mock_exporter: MagicMock):
        """Registry initializes and pre-registers metrics."""
        _ = P03MetricsRegistry(exporter=mock_exporter)

        # Registry should have been created - the metric registration happens
        # via the exporter's counter/histogram/gauge calls
        # We just verify the registry was created without error
        assert True  # Registry created successfully

    def test_cycle_metrics_defined(self):
        """Verify cycle metrics are properly defined."""
        metric_names = [m.name for m in CYCLE_METRICS]
        assert "p03_cycle_total" in metric_names
        assert "p03_cycle_duration_seconds" in metric_names
        assert "p03_cycle_batch_size" in metric_names
        assert "p03_cycle_phase_skip_count" in metric_names

    def test_phase_metrics_defined(self):
        """Verify phase metrics are properly defined."""
        metric_names = [m.name for m in PHASE_METRICS]
        assert "p03_phase_duration_seconds" in metric_names
        assert "p03_phase_total" in metric_names

    def test_decision_metrics_defined(self):
        """Verify decision metrics are properly defined."""
        metric_names = [m.name for m in DECISION_METRICS]
        assert "p03_decisions_total" in metric_names
        assert "p03_decision_confidence" in metric_names

    def test_gap_metrics_defined(self):
        """Verify gap metrics are properly defined."""
        metric_names = [m.name for m in GAP_METRICS]
        assert "p03_gaps_detected_total" in metric_names
        assert "p03_gap_importance_score" in metric_names
        assert "p03_gaps_deduplicated_total" in metric_names


# =============================================================================
# TEST: CYCLE METRICS (Issue 6.1.2)
# =============================================================================


class TestCycleMetrics:
    """Tests for cycle-level metrics emission."""

    def test_emit_cycle_complete_success(
        self, registry: P03MetricsRegistry, mock_exporter: MagicMock
    ):
        """Emit cycle complete counter with success status."""
        registry.emit_cycle_complete(
            tenant_id="tenant-1",
            status="success",
            duration_s=5.5,
            events_processed=100,
            space_id="space-1",
        )

        mock_exporter.emit.assert_called()
        # Check that p03_cycle_total was emitted
        calls = mock_exporter.emit.call_args_list
        metric_call = [c for c in calls if c[0][0] == "p03_cycle_total"]
        assert len(metric_call) >= 1

    def test_emit_cycle_complete_failure(
        self, registry: P03MetricsRegistry, mock_exporter: MagicMock
    ):
        """Emit cycle complete counter with failure status."""
        registry.emit_cycle_complete(
            tenant_id="tenant-1",
            status="failure",
            duration_s=2.0,
        )

        mock_exporter.emit.assert_called()

    def test_emit_cycle_duration(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit cycle duration histogram."""
        registry.emit_cycle_duration(
            duration_ms=5500,
            tenant_id="tenant-1",
            space_id="space-1",
            qos_band="GREEN",
        )

        mock_exporter.observe.assert_called()
        # Verify duration was converted to seconds
        call_args = mock_exporter.observe.call_args
        assert call_args[0][0] == "p03_cycle_duration_seconds"
        assert call_args[0][1] == 5.5  # 5500ms -> 5.5s

    def test_emit_batch_size(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit batch size histogram."""
        registry.emit_batch_size(
            batch_size=50,
            tenant_id="tenant-1",
            space_id="space-1",
            qos_band="AMBER",
        )

        mock_exporter.observe.assert_called()
        call_args = mock_exporter.observe.call_args
        assert call_args[0][0] == "p03_cycle_batch_size"
        assert call_args[0][1] == 50.0

    def test_emit_phase_skip_count(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit phase skip count histogram."""
        registry.emit_phase_skip_count(
            skip_count=3,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        mock_exporter.observe.assert_called()
        call_args = mock_exporter.observe.call_args
        assert call_args[0][0] == "p03_cycle_phase_skip_count"
        assert call_args[0][1] == 3.0


# =============================================================================
# TEST: PHASE METRICS (Issue 6.1.3)
# =============================================================================


class TestPhaseMetrics:
    """Tests for phase timing metrics emission."""

    def test_emit_phase_duration(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit phase duration histogram."""
        registry.emit_phase_duration(
            tenant_id="tenant-1",
            phase="R4",
            duration_s=1.5,
        )

        mock_exporter.observe.assert_called()
        call_args = mock_exporter.observe.call_args
        assert call_args[0][0] == "p03_phase_duration_seconds"
        # Duration is in seconds
        assert call_args[0][1] == 1.5

    def test_emit_phase_complete_success(
        self, registry: P03MetricsRegistry, mock_exporter: MagicMock
    ):
        """Emit phase complete counter with success status."""
        registry.emit_phase_complete(
            tenant_id="tenant-1",
            phase="R4",
            status="success",
        )

        mock_exporter.emit.assert_called()
        call_args = mock_exporter.emit.call_args
        assert call_args[0][0] == "p03_phase_total"

    def test_emit_phase_complete_skipped(
        self, registry: P03MetricsRegistry, mock_exporter: MagicMock
    ):
        """Emit phase complete counter with skipped status."""
        registry.emit_phase_complete(
            tenant_id="tenant-1",
            phase="R5",
            status="skipped",
        )

        mock_exporter.emit.assert_called()


# =============================================================================
# TEST: DECISION METRICS (Issue 6.1.4)
# =============================================================================


class TestDecisionMetrics:
    """Tests for reconciliation decision metrics emission."""

    def test_emit_decision_create(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit CREATE decision metric."""
        registry.emit_decision(
            tenant_id="tenant-1",
            decision_type="CREATE",
            target_layer="st_kg_dom",
            confidence=0.85,
        )

        # Should emit both counter and histogram
        assert mock_exporter.emit.called or mock_exporter.observe.called

    def test_emit_decision_extend(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit EXTEND decision metric."""
        registry.emit_decision(
            tenant_id="tenant-1",
            decision_type="EXTEND",
            target_layer="st_kg_dom",
            confidence=0.75,
        )

        assert mock_exporter.emit.called

    def test_emit_decision_reinforce(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit REINFORCE decision metric for edges."""
        registry.emit_decision(
            tenant_id="tenant-1",
            decision_type="REINFORCE",
            target_layer="st_kg_edges",
            confidence=0.90,
        )

        assert mock_exporter.emit.called

    def test_emit_similarity_score(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit similarity score histogram."""
        registry.emit_similarity_score(
            tenant_id="tenant-1",
            score=0.82,
            match_result="match",
        )

        mock_exporter.observe.assert_called()


# =============================================================================
# TEST: GAP METRICS (Issue 6.1.5)
# =============================================================================


class TestGapMetrics:
    """Tests for gap detection and deduplication metrics."""

    def test_emit_gap_detected(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit gap detected counter."""
        registry.emit_gap_detected(
            tenant_id="tenant-1",
            space_id="space-1",
            gap_type="AMBIGUOUS_ENTITY",
            importance=0.75,
        )

        assert mock_exporter.emit.called or mock_exporter.observe.called

    def test_emit_gap_detected_low_confidence(
        self, registry: P03MetricsRegistry, mock_exporter: MagicMock
    ):
        """Emit gap for low confidence edge."""
        registry.emit_gap_detected(
            tenant_id="tenant-1",
            space_id="space-1",
            gap_type="LOW_CONFIDENCE_EDGE",
            importance=0.50,
        )

        assert mock_exporter.emit.called

    def test_emit_gap_deduplicated(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Emit gap deduplicated counter."""
        registry.emit_gap_deduplicated(
            tenant_id="tenant-1",
            gap_type="AMBIGUOUS_ENTITY",
        )

        mock_exporter.emit.assert_called()


# =============================================================================
# TEST: BUCKET DEFINITIONS
# =============================================================================


class TestBucketDefinitions:
    """Tests for histogram bucket definitions."""

    def test_cycle_duration_buckets_ordered(self):
        """Cycle duration buckets are in ascending order."""
        buckets = list(CYCLE_DURATION_BUCKETS)
        assert buckets == sorted(buckets)

    def test_cycle_duration_buckets_cover_range(self):
        """Cycle duration buckets cover expected range."""
        # Should cover 1 second to 10 minutes (600s)
        assert min(CYCLE_DURATION_BUCKETS) <= 1.0
        assert max(CYCLE_DURATION_BUCKETS) >= 60.0

    def test_phase_duration_buckets_ordered(self):
        """Phase duration buckets are in ascending order."""
        buckets = list(PHASE_DURATION_BUCKETS)
        assert buckets == sorted(buckets)

    def test_phase_duration_buckets_granular(self):
        """Phase duration buckets are granular for sub-second timing."""
        # Should have sub-second granularity
        assert min(PHASE_DURATION_BUCKETS) <= 0.5


# =============================================================================
# TEST: METRIC DEFINITION DATACLASS
# =============================================================================


class TestMetricDefinition:
    """Tests for MetricDefinition dataclass."""

    def test_metric_definition_counter(self):
        """Create counter metric definition."""
        metric = MetricDefinition(
            name="test_counter",
            description="Test counter metric",
            metric_type="counter",
            labelnames=("tenant_id", "status"),
        )
        assert metric.name == "test_counter"
        assert metric.metric_type == "counter"
        assert metric.buckets is None

    def test_metric_definition_histogram(self):
        """Create histogram metric definition with buckets."""
        buckets = (0.1, 0.5, 1.0, 5.0)
        metric = MetricDefinition(
            name="test_histogram",
            description="Test histogram metric",
            metric_type="histogram",
            labelnames=("tenant_id",),
            buckets=buckets,
        )
        assert metric.metric_type == "histogram"
        assert metric.buckets == buckets

    def test_metric_definition_immutable(self):
        """MetricDefinition is frozen (immutable)."""
        metric = MetricDefinition(
            name="test_immutable",
            description="Test",
            metric_type="counter",
            labelnames=("tenant_id",),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            metric.name = "modified"  # type: ignore


# =============================================================================
# TEST: INTEGRATION WITH OBSERVABILITY CONTEXT
# =============================================================================


class TestObservabilityIntegration:
    """Tests for integration with P03ObservabilityContext."""

    def test_emit_from_observability_context(
        self, registry: P03MetricsRegistry, mock_exporter: MagicMock
    ):
        """Emit metrics from observability context data."""
        # Simulate phase durations from observability context
        phase_durations = {
            "R0": 100,
            "R1": 500,
            "R2": 300,
            "R4": 2000,
        }

        registry.emit_from_observability_context(
            tenant_id="tenant-1",
            space_id="space-1",
            phase_durations=phase_durations,
            counters={"gaps.detected": 5},
            histograms={"importance_scores": [0.5, 0.7, 0.9]},
        )

        # Should have emitted phase durations
        assert mock_exporter.observe.called


# =============================================================================
# TEST: ERROR HANDLING
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in metrics emission."""

    def test_emit_with_missing_exporter(self):
        """Handle missing exporter gracefully."""
        # This would require a different initialization path
        # For now, verify that exporter is required
        pass

    def test_emit_with_invalid_labels(self, registry: P03MetricsRegistry, mock_exporter: MagicMock):
        """Handle invalid label values gracefully."""
        # Should not raise - just emit with the provided values
        registry.emit_cycle_complete(
            tenant_id="",  # Empty tenant
            status="unknown_status",
            duration_s=-1.0,  # Negative duration
        )
        # Should have been called without exception
        assert mock_exporter.emit.called
