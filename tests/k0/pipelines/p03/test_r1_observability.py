"""
Tests for R1 Observability (M5.O Epic 5.O.1).

Issues:
    5.O.1.1: OTel span for R1 phase
    5.O.1.2: Score distribution histogram
    5.O.1.3: Weight source counter
    5.O.1.4: Priority tier gauge
    5.O.1.5: Audit sampling rate control
    5.O.1.6: Breakdown component distribution

Test Coverage:
    - R1PhaseMetrics new fields: tier_counts, component distributions, audit counts
    - R1ImportanceScorer.run() populates R1PhaseMetrics
    - R1PhaseMetrics emitted via metrics registry
    - Component distribution histograms track per-event breakdowns
    - Tier counts match structured log values
    - Audit sampling ratio metric is correct
    - Prometheus export includes new 5.O.1 metrics
    - Merge aggregates new fields correctly
    - to_dict includes new fields
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.observability import IMPORTANCE_SCORE_BUCKETS, R1PhaseMetrics

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def empty_metrics() -> R1PhaseMetrics:
    """Fresh R1PhaseMetrics with defaults."""
    return R1PhaseMetrics()


@pytest.fixture
def populated_obs_metrics() -> R1PhaseMetrics:
    """R1PhaseMetrics with 5.O.1 fields populated."""
    m = R1PhaseMetrics()
    m.record_importance_scores([0.12, 0.35, 0.55, 0.72, 0.85])
    m.set_weight_info(
        weights={
            "sentiment": 0.10,
            "affect": 0.12,
            "arousal": 0.08,
            "surprise": 0.15,
            "novelty": 0.15,
            "social": 0.15,
            "identity": 0.10,
            "recency": 0.15,
        },
        sample_count=600,
        source="learned",
    )
    m.set_tier_counts(critical=1, high=1, medium_high=1, medium=1, low_medium=1, low=0)
    m.set_audit_counts(events_scored=5, audit_records=1)
    m.record_component_breakdown(
        emotional=0.22, surprise=0.15, novelty=0.10, social=0.18, identity=0.05, recency=0.30
    )
    m.record_component_breakdown(
        emotional=0.30, surprise=0.25, novelty=0.20, social=0.10, identity=0.08, recency=0.20
    )
    m.r1_duration_ms = 250.0
    m.importance_scoring_ms = 180.0
    return m


# =============================================================================
# MOCK HELPERS
# =============================================================================


@dataclass
class MockP03EventState:
    """Minimal event state for testing R1 phase."""

    event_id: str = "evt-001"
    sentiment_score: float = 0.6
    affect_valence: float = 0.5
    affect_arousal: float = 0.4
    surprise_level: float = 0.3
    novelty: str = "NOVEL"
    num_participants: int = 2
    social_intimacy: str = "MEDIUM"
    identity_relevance: float = 0.5
    elaboration_depth: str = "DISCUSSED"
    source_reliability: float = 0.95
    memory_tier: str = "notable"
    narrative_is_goal_event: bool = False
    narrative_arc_position: str = "RISING_ACTION"
    temporal_orientation: str = "ONGOING"
    content_type: str = "message"
    importance_computed: bool = False
    event_time_ms: int = 1700000000000
    intent_type: str = ""

    def set_importance(self, **kwargs: Any) -> None:
        self.importance_computed = True


@dataclass
class MockBatchContext:
    cycle_id: str = "cycle-obs-001"
    space_id: str = "space-obs-001"
    tenant_id: str = "tenant-obs-001"


@dataclass
class MockPhaseOutputs:
    r1_scored_events: List[Any] = field(default_factory=list)
    r1_audit_records: List[Any] = field(default_factory=list)
    r1_metrics: Any = None
    r1_hebbian_updates: List[Any] = field(default_factory=list)


@dataclass
class MockEnvelope:
    events: List[MockP03EventState] = field(default_factory=list)
    context: MockBatchContext = field(default_factory=MockBatchContext)
    phases: MockPhaseOutputs = field(default_factory=MockPhaseOutputs)


class MockSyscalls:
    """Mock syscalls that return None for weight queries."""

    async def query(self, *args: Any, **kwargs: Any) -> List[Any]:
        return []

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        pass


class MockMetricsRegistry:
    """Captures emit_r1_scoring calls."""

    def __init__(self) -> None:
        self.r1_calls: List[Dict[str, Any]] = []

    def emit_r1_scoring(self, tenant_id: str, r1_metrics: Any) -> None:
        self.r1_calls.append(
            {
                "tenant_id": tenant_id,
                "r1_metrics": r1_metrics,
            }
        )


class MockRunnerContext:
    """Minimal runner context for testing."""

    def __init__(
        self,
        syscalls: Any = None,
        metrics_registry: Any = None,
    ):
        self.syscalls = syscalls or MockSyscalls()
        self.logger = MagicMock()
        self.metrics_registry = metrics_registry
        self._config: Dict[str, Any] = {}

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)


# =============================================================================
# 5.O.1.2: SCORE DISTRIBUTION HISTOGRAM
# =============================================================================


class TestScoreDistributionHistogram:
    """Tests for importance score histogram population (5.O.1.2)."""

    def test_scores_recorded_in_metrics(self, empty_metrics: R1PhaseMetrics) -> None:
        """R1PhaseMetrics records all importance scores."""
        scores = [0.1, 0.3, 0.5, 0.7, 0.9]
        empty_metrics.record_importance_scores(scores)
        assert empty_metrics.importance_scores == scores

    def test_prometheus_export_includes_score_histogram(
        self, populated_obs_metrics: R1PhaseMetrics
    ) -> None:
        """Prometheus export includes score distribution with correct buckets."""
        prom = populated_obs_metrics.to_prometheus_metrics()
        assert "p03_importance_score_distribution" in prom
        dist = prom["p03_importance_score_distribution"]
        assert dist["buckets"] == IMPORTANCE_SCORE_BUCKETS
        assert len(dist["values"]) == 5

    def test_empty_scores_export(self, empty_metrics: R1PhaseMetrics) -> None:
        """Empty metrics export empty score histogram."""
        prom = empty_metrics.to_prometheus_metrics()
        assert prom["p03_importance_score_distribution"]["values"] == []


# =============================================================================
# 5.O.1.3: WEIGHT SOURCE COUNTER
# =============================================================================


class TestWeightSourceCounter:
    """Tests for weight source tracking (5.O.1.3)."""

    def test_default_weight_source_static(self, empty_metrics: R1PhaseMetrics) -> None:
        assert empty_metrics.importance_weight_source == "static"

    def test_set_weight_source_learned(self, empty_metrics: R1PhaseMetrics) -> None:
        empty_metrics.set_weight_info(
            weights={"sentiment": 0.10}, sample_count=600, source="learned"
        )
        assert empty_metrics.importance_weight_source == "learned"

    def test_set_weight_source_blended(self, empty_metrics: R1PhaseMetrics) -> None:
        empty_metrics.set_weight_info(
            weights={"sentiment": 0.10}, sample_count=200, source="blended"
        )
        assert empty_metrics.importance_weight_source == "blended"

    def test_prometheus_export_includes_weight_source(
        self, populated_obs_metrics: R1PhaseMetrics
    ) -> None:
        prom = populated_obs_metrics.to_prometheus_metrics()
        assert prom["p03_r1_weight_source_counter"] == "learned"


# =============================================================================
# 5.O.1.4: PRIORITY TIER GAUGE
# =============================================================================


class TestPriorityTierGauge:
    """Tests for priority tier count tracking (5.O.1.4)."""

    def test_default_tier_counts_all_zero(self, empty_metrics: R1PhaseMetrics) -> None:
        for tier in ("CRITICAL", "HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW_MEDIUM", "LOW"):
            assert empty_metrics.tier_counts[tier] == 0

    def test_set_tier_counts(self, empty_metrics: R1PhaseMetrics) -> None:
        empty_metrics.set_tier_counts(
            critical=3, high=5, medium_high=10, medium=8, low_medium=4, low=2
        )
        assert empty_metrics.tier_counts["CRITICAL"] == 3
        assert empty_metrics.tier_counts["HIGH"] == 5
        assert empty_metrics.tier_counts["MEDIUM_HIGH"] == 10
        assert empty_metrics.tier_counts["MEDIUM"] == 8
        assert empty_metrics.tier_counts["LOW_MEDIUM"] == 4
        assert empty_metrics.tier_counts["LOW"] == 2

    def test_tier_counts_sum(self, populated_obs_metrics: R1PhaseMetrics) -> None:
        """Tier counts should sum to events scored."""
        total = sum(populated_obs_metrics.tier_counts.values())
        assert total == 5  # 1+1+1+1+1+0

    def test_prometheus_export_includes_tier_counts(
        self, populated_obs_metrics: R1PhaseMetrics
    ) -> None:
        prom = populated_obs_metrics.to_prometheus_metrics()
        assert "p03_r1_tier_counts" in prom
        tier_counts = prom["p03_r1_tier_counts"]
        assert tier_counts["CRITICAL"] == 1
        assert tier_counts["HIGH"] == 1

    def test_to_dict_includes_tier_counts(self, populated_obs_metrics: R1PhaseMetrics) -> None:
        d = populated_obs_metrics.to_dict()
        assert "tier_counts" in d
        assert d["tier_counts"]["CRITICAL"] == 1


# =============================================================================
# 5.O.1.5: AUDIT SAMPLING RATE CONTROL
# =============================================================================


class TestAuditSamplingMetrics:
    """Tests for audit sampling rate metrics (5.O.1.5)."""

    def test_default_audit_counts_zero(self, empty_metrics: R1PhaseMetrics) -> None:
        assert empty_metrics.events_scored == 0
        assert empty_metrics.audit_records_generated == 0

    def test_set_audit_counts(self, empty_metrics: R1PhaseMetrics) -> None:
        empty_metrics.set_audit_counts(events_scored=100, audit_records=10)
        assert empty_metrics.events_scored == 100
        assert empty_metrics.audit_records_generated == 10

    def test_audit_sampling_ratio(self, populated_obs_metrics: R1PhaseMetrics) -> None:
        """Ratio should be ~0.20 (1 audit / 5 events)."""
        ratio = populated_obs_metrics.audit_records_generated / populated_obs_metrics.events_scored
        assert abs(ratio - 0.20) < 0.01

    def test_prometheus_export_includes_audit_metrics(
        self, populated_obs_metrics: R1PhaseMetrics
    ) -> None:
        prom = populated_obs_metrics.to_prometheus_metrics()
        assert prom["p03_r1_events_scored"] == 5
        assert prom["p03_r1_audit_records_generated"] == 1

    def test_to_dict_includes_audit_metrics(self, populated_obs_metrics: R1PhaseMetrics) -> None:
        d = populated_obs_metrics.to_dict()
        assert d["events_scored"] == 5
        assert d["audit_records_generated"] == 1


# =============================================================================
# 5.O.1.6: COMPONENT DISTRIBUTION
# =============================================================================


class TestComponentDistribution:
    """Tests for per-cycle component distribution histograms (5.O.1.6)."""

    def test_default_components_empty(self, empty_metrics: R1PhaseMetrics) -> None:
        assert empty_metrics.emotional_components == []
        assert empty_metrics.surprise_components == []
        assert empty_metrics.novelty_components == []
        assert empty_metrics.social_components == []
        assert empty_metrics.identity_components == []
        assert empty_metrics.recency_components == []

    def test_record_component_breakdown(self, empty_metrics: R1PhaseMetrics) -> None:
        empty_metrics.record_component_breakdown(
            emotional=0.22,
            surprise=0.15,
            novelty=0.10,
            social=0.18,
            identity=0.05,
            recency=0.30,
        )
        assert len(empty_metrics.emotional_components) == 1
        assert empty_metrics.emotional_components[0] == 0.22
        assert empty_metrics.recency_components[0] == 0.30

    def test_multiple_breakdowns_accumulated(self, populated_obs_metrics: R1PhaseMetrics) -> None:
        """Two breakdowns were recorded in fixture."""
        assert len(populated_obs_metrics.emotional_components) == 2
        assert len(populated_obs_metrics.surprise_components) == 2

    def test_prometheus_export_includes_6_component_histograms(
        self, populated_obs_metrics: R1PhaseMetrics
    ) -> None:
        prom = populated_obs_metrics.to_prometheus_metrics()
        for component in ("emotional", "surprise", "novelty", "social", "identity", "recency"):
            key = f"p03_r1_component_{component}"
            assert key in prom, f"Missing {key} in Prometheus export"
            assert "values" in prom[key]
            assert "buckets" in prom[key]
            assert len(prom[key]["values"]) == 2  # Two breakdowns recorded

    def test_to_dict_includes_component_distribution(
        self, populated_obs_metrics: R1PhaseMetrics
    ) -> None:
        d = populated_obs_metrics.to_dict()
        assert "component_distribution" in d
        assert d["component_distribution"]["emotional"] == 2
        assert d["component_distribution"]["recency"] == 2


# =============================================================================
# MERGE WITH NEW FIELDS
# =============================================================================


class TestMergeNewFields:
    """Tests that merge() correctly aggregates 5.O.1 fields."""

    def test_merge_tier_counts(self) -> None:
        m1 = R1PhaseMetrics()
        m1.set_tier_counts(critical=2, high=3)
        m2 = R1PhaseMetrics()
        m2.set_tier_counts(critical=1, high=2, medium=5)
        m1.merge(m2)
        assert m1.tier_counts["CRITICAL"] == 3
        assert m1.tier_counts["HIGH"] == 5
        assert m1.tier_counts["MEDIUM"] == 5

    def test_merge_component_distributions(self) -> None:
        m1 = R1PhaseMetrics()
        m1.record_component_breakdown(
            emotional=0.1,
            surprise=0.2,
            novelty=0.3,
            social=0.4,
            identity=0.5,
            recency=0.6,
        )
        m2 = R1PhaseMetrics()
        m2.record_component_breakdown(
            emotional=0.7,
            surprise=0.8,
            novelty=0.9,
            social=0.1,
            identity=0.2,
            recency=0.3,
        )
        m1.merge(m2)
        assert len(m1.emotional_components) == 2
        assert m1.emotional_components == [0.1, 0.7]
        assert len(m1.recency_components) == 2

    def test_merge_audit_counts(self) -> None:
        m1 = R1PhaseMetrics()
        m1.set_audit_counts(events_scored=50, audit_records=5)
        m2 = R1PhaseMetrics()
        m2.set_audit_counts(events_scored=30, audit_records=3)
        m1.merge(m2)
        assert m1.events_scored == 80
        assert m1.audit_records_generated == 8


# =============================================================================
# R1 RUN() INTEGRATION — METRICS POPULATION
# =============================================================================


class TestR1RunMetricsPopulation:
    """Tests that R1ImportanceScorer.run() populates R1PhaseMetrics."""

    @pytest.fixture
    def mock_envelope(self) -> MockEnvelope:
        """Create envelope with 3 events."""
        events = [
            MockP03EventState(
                event_id=f"evt-{i:03d}",
                sentiment_score=0.3 + i * 0.2,
                affect_valence=0.4 + i * 0.1,
                surprise_level=0.2 + i * 0.1,
                novelty="NOVEL" if i > 0 else "ROUTINE",
                num_participants=i + 1,
                identity_relevance=0.3 + i * 0.2,
            )
            for i in range(3)
        ]
        return MockEnvelope(events=events)

    @pytest.fixture
    def mock_ctx(self) -> MockRunnerContext:
        return MockRunnerContext(
            syscalls=MockSyscalls(),
            metrics_registry=MockMetricsRegistry(),
        )

    @pytest.mark.asyncio
    async def test_run_populates_r1_metrics(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """R1 run() should create and populate R1PhaseMetrics."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        result = await scorer.run(mock_envelope, mock_ctx)

        assert result.status.value in ("done", "DONE", "completed")
        assert mock_envelope.phases.r1_metrics is not None

    @pytest.mark.asyncio
    async def test_run_records_importance_scores(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """R1 metrics should contain one score per event."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        await scorer.run(mock_envelope, mock_ctx)

        r1_metrics = mock_envelope.phases.r1_metrics
        assert len(r1_metrics.importance_scores) == 3

    @pytest.mark.asyncio
    async def test_run_records_component_breakdowns(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """R1 metrics should contain component breakdowns for each event."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        await scorer.run(mock_envelope, mock_ctx)

        r1_metrics = mock_envelope.phases.r1_metrics
        assert len(r1_metrics.emotional_components) == 3
        assert len(r1_metrics.surprise_components) == 3
        assert len(r1_metrics.novelty_components) == 3
        assert len(r1_metrics.social_components) == 3
        assert len(r1_metrics.identity_components) == 3
        assert len(r1_metrics.recency_components) == 3

    @pytest.mark.asyncio
    async def test_run_sets_weight_source(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """R1 metrics should have weight source set (static by default)."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        await scorer.run(mock_envelope, mock_ctx)

        r1_metrics = mock_envelope.phases.r1_metrics
        assert r1_metrics.importance_weight_source == "static"

    @pytest.mark.asyncio
    async def test_run_sets_tier_counts(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """R1 metrics should have tier counts matching scored events."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        await scorer.run(mock_envelope, mock_ctx)

        r1_metrics = mock_envelope.phases.r1_metrics
        total_tiers = sum(r1_metrics.tier_counts.values())
        assert total_tiers == 3  # 3 events

    @pytest.mark.asyncio
    async def test_run_sets_audit_counts(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """R1 metrics should track events scored and audit records."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        await scorer.run(mock_envelope, mock_ctx)

        r1_metrics = mock_envelope.phases.r1_metrics
        assert r1_metrics.events_scored == 3

    @pytest.mark.asyncio
    async def test_run_sets_timing(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """R1 metrics should record duration and scoring time."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        await scorer.run(mock_envelope, mock_ctx)

        r1_metrics = mock_envelope.phases.r1_metrics
        assert r1_metrics.r1_duration_ms >= 0
        assert r1_metrics.importance_scoring_ms >= 0

    @pytest.mark.asyncio
    async def test_run_emits_to_metrics_registry(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """R1 run() should call metrics_registry.emit_r1_scoring()."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        await scorer.run(mock_envelope, mock_ctx)

        registry = mock_ctx.metrics_registry
        assert len(registry.r1_calls) == 1
        assert registry.r1_calls[0]["tenant_id"] == "tenant-obs-001"
        assert registry.r1_calls[0]["r1_metrics"] is not None

    @pytest.mark.asyncio
    async def test_run_without_metrics_registry_succeeds(self, mock_envelope: MockEnvelope) -> None:
        """R1 run() should succeed even without metrics_registry."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        ctx = MockRunnerContext(metrics_registry=None)
        scorer = R1ImportanceScorer()
        result = await scorer.run(mock_envelope, ctx)

        assert result.status.value in ("done", "DONE", "completed")

    @pytest.mark.asyncio
    async def test_run_metrics_registry_error_non_fatal(self, mock_envelope: MockEnvelope) -> None:
        """Metrics emission failure should not fail the phase."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        bad_registry = MagicMock()
        bad_registry.emit_r1_scoring.side_effect = RuntimeError("metrics broken")
        ctx = MockRunnerContext(metrics_registry=bad_registry)

        scorer = R1ImportanceScorer()
        result = await scorer.run(mock_envelope, ctx)

        assert result.status.value in ("done", "DONE", "completed")

    @pytest.mark.asyncio
    async def test_run_outputs_summary_contains_r1_metrics(
        self, mock_envelope: MockEnvelope, mock_ctx: MockRunnerContext
    ) -> None:
        """PhaseResult outputs_summary should include r1_metrics dict."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        scorer = R1ImportanceScorer()
        result = await scorer.run(mock_envelope, mock_ctx)

        assert "r1_metrics" in result.outputs_summary
        assert "tier_counts" in result.outputs_summary["r1_metrics"]
        assert "events_scored" in result.outputs_summary["r1_metrics"]


# =============================================================================
# METRICS REGISTRY EMIT METHOD
# =============================================================================


class TestMetricsRegistryEmitR1:
    """Tests for P03MetricsRegistry.emit_r1_scoring()."""

    def test_emit_r1_scoring_calls_exporter(self) -> None:
        """emit_r1_scoring should call exporter methods."""
        mock_exporter = MagicMock()
        from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

        registry = P03MetricsRegistry(mock_exporter)

        m = R1PhaseMetrics()
        m.record_importance_scores([0.3, 0.7])
        m.set_weight_info(weights={"sentiment": 0.10}, sample_count=100, source="static")
        m.set_tier_counts(critical=0, high=1, medium=1)
        m.set_audit_counts(events_scored=2, audit_records=1)
        m.record_component_breakdown(
            emotional=0.2,
            surprise=0.1,
            novelty=0.3,
            social=0.1,
            identity=0.05,
            recency=0.25,
        )
        m.r1_duration_ms = 150.0

        registry.emit_r1_scoring(tenant_id="t1", r1_metrics=m)

        # Verify exporter was called for histograms, counters, gauges
        assert mock_exporter.observe.called
        assert mock_exporter.emit.called
        assert mock_exporter.set_gauge.called

    def test_emit_r1_scoring_score_histogram_observations(self) -> None:
        """Each score should produce one observe() call."""
        mock_exporter = MagicMock()
        from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

        registry = P03MetricsRegistry(mock_exporter)

        m = R1PhaseMetrics()
        m.record_importance_scores([0.3, 0.5, 0.8])
        m.set_weight_info(weights={}, sample_count=0, source="static")
        m.set_audit_counts(events_scored=3, audit_records=0)
        m.r1_duration_ms = 50.0

        registry.emit_r1_scoring(tenant_id="t1", r1_metrics=m)

        # Collect observe calls for score distribution
        score_calls = [
            c
            for c in mock_exporter.observe.call_args_list
            if c[0][0] == "p03_r1_importance_score_distribution"
        ]
        assert len(score_calls) == 3

    def test_emit_r1_scoring_weight_source_counter(self) -> None:
        """Weight source counter incremented once per cycle."""
        mock_exporter = MagicMock()
        from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

        registry = P03MetricsRegistry(mock_exporter)

        m = R1PhaseMetrics()
        m.set_weight_info(weights={}, sample_count=600, source="learned")
        m.set_audit_counts(events_scored=0, audit_records=0)
        m.r1_duration_ms = 10.0

        registry.emit_r1_scoring(tenant_id="t1", r1_metrics=m)

        source_calls = [
            c for c in mock_exporter.emit.call_args_list if c[0][0] == "p03_r1_weight_source_total"
        ]
        assert len(source_calls) == 1
        assert source_calls[0][1]["weight_source"] == "learned"

    def test_emit_r1_scoring_tier_gauges(self) -> None:
        """Tier gauge set for all 6 tiers."""
        mock_exporter = MagicMock()
        from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

        registry = P03MetricsRegistry(mock_exporter)

        m = R1PhaseMetrics()
        m.set_tier_counts(critical=5, high=3, medium_high=2, medium=4, low_medium=1, low=0)
        m.set_weight_info(weights={}, sample_count=0, source="static")
        m.set_audit_counts(events_scored=15, audit_records=2)
        m.r1_duration_ms = 100.0

        registry.emit_r1_scoring(tenant_id="t1", r1_metrics=m)

        tier_calls = [
            c for c in mock_exporter.set_gauge.call_args_list if c[0][0] == "p03_r1_tier_count"
        ]
        assert len(tier_calls) == 6

    def test_emit_r1_scoring_component_histograms(self) -> None:
        """6 component histograms emitted with values."""
        mock_exporter = MagicMock()
        from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

        registry = P03MetricsRegistry(mock_exporter)

        m = R1PhaseMetrics()
        m.record_component_breakdown(
            emotional=0.2,
            surprise=0.1,
            novelty=0.3,
            social=0.1,
            identity=0.05,
            recency=0.25,
        )
        m.set_weight_info(weights={}, sample_count=0, source="static")
        m.set_audit_counts(events_scored=1, audit_records=0)
        m.r1_duration_ms = 20.0

        registry.emit_r1_scoring(tenant_id="t1", r1_metrics=m)

        component_names = {"emotional", "surprise", "novelty", "social", "identity", "recency"}
        component_calls = [
            c
            for c in mock_exporter.observe.call_args_list
            if any(f"p03_r1_component_{n}" in str(c) for n in component_names)
        ]
        assert len(component_calls) == 6  # 1 value per component


# =============================================================================
# R1 METRIC DEFINITIONS
# =============================================================================


class TestR1MetricDefinitions:
    """Tests for R1 metric definitions in ops/metrics.py."""

    def test_r1_metrics_tuple_exists(self) -> None:
        from k0.pipelines.p03.ops.metrics import R1_METRICS

        assert len(R1_METRICS) >= 10  # At least 10 metric definitions

    def test_r1_metrics_in_all_metrics(self) -> None:
        from k0.pipelines.p03.ops.metrics import ALL_METRICS, R1_METRICS

        all_names = {m.name for m in ALL_METRICS}
        r1_names = {m.name for m in R1_METRICS}
        assert r1_names.issubset(all_names)

    def test_r1_metric_names_prefixed(self) -> None:
        """All R1 metric names should start with p03_r1_."""
        from k0.pipelines.p03.ops.metrics import R1_METRICS

        for m in R1_METRICS:
            assert m.name.startswith("p03_r1_"), f"{m.name} missing p03_r1_ prefix"

    def test_r1_score_distribution_histogram_defined(self) -> None:
        from k0.pipelines.p03.ops.metrics import R1_METRICS

        names = {m.name for m in R1_METRICS}
        assert "p03_r1_importance_score_distribution" in names

    def test_r1_weight_source_counter_defined(self) -> None:
        from k0.pipelines.p03.ops.metrics import R1_METRICS

        names = {m.name for m in R1_METRICS}
        assert "p03_r1_weight_source_total" in names

    def test_r1_tier_gauge_defined(self) -> None:
        from k0.pipelines.p03.ops.metrics import R1_METRICS

        names = {m.name for m in R1_METRICS}
        assert "p03_r1_tier_count" in names

    def test_r1_component_histograms_defined(self) -> None:
        from k0.pipelines.p03.ops.metrics import R1_METRICS

        names = {m.name for m in R1_METRICS}
        for component in ("emotional", "surprise", "novelty", "social", "identity", "recency"):
            assert f"p03_r1_component_{component}" in names

    def test_r1_audit_metrics_defined(self) -> None:
        from k0.pipelines.p03.ops.metrics import R1_METRICS

        names = {m.name for m in R1_METRICS}
        assert "p03_r1_events_scored_total" in names
        assert "p03_r1_audit_records_total" in names
        assert "p03_r1_audit_sampling_ratio" in names
