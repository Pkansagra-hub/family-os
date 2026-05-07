"""M1 Foundation -- Test Metrics Definitions [F05].

Tests MetricType, MetricDef, and the ALL_METRICS registry.

NO MOCKS.  Pure data structure tests.
"""

from __future__ import annotations

from k1.model_hub.metrics import ALL_METRICS, MetricDef, MetricType


class TestMetricType:
    def test_members(self) -> None:
        assert len(MetricType) == 3
        assert {m.value for m in MetricType} == {"counter", "histogram", "gauge"}


class TestMetricDef:
    def test_construction(self) -> None:
        d = MetricDef(
            name="test",
            type=MetricType.COUNTER,
            description="test metric",
            labels=["a"],
        )
        assert d.name == "test"
        assert d.type == MetricType.COUNTER


class TestAllMetrics:
    def test_registry_has_12_metrics(self) -> None:
        assert len(ALL_METRICS) == 12

    def test_all_names_prefixed(self) -> None:
        for name in ALL_METRICS:
            assert name.startswith("model_hub."), f"{name} missing prefix"

    def test_counters(self) -> None:
        counters = [n for n, d in ALL_METRICS.items() if d.type == MetricType.COUNTER]
        assert len(counters) == 5

    def test_histograms(self) -> None:
        histograms = [n for n, d in ALL_METRICS.items() if d.type == MetricType.HISTOGRAM]
        assert len(histograms) == 4

    def test_gauges(self) -> None:
        gauges = [n for n, d in ALL_METRICS.items() if d.type == MetricType.GAUGE]
        assert len(gauges) == 3

    def test_all_values_are_metric_def(self) -> None:
        for name, defn in ALL_METRICS.items():
            assert isinstance(defn, MetricDef), f"{name} is not MetricDef"
            assert defn.name == name

    def test_expected_counter_names(self) -> None:
        expected = {
            "model_hub.requests_total",
            "model_hub.errors_total",
            "model_hub.cache_hits_total",
            "model_hub.fallbacks_total",
            "model_hub.budget_rejections_total",
        }
        actual = {n for n, d in ALL_METRICS.items() if d.type == MetricType.COUNTER}
        assert actual == expected

    def test_expected_histogram_names(self) -> None:
        expected = {
            "model_hub.latency_ms",
            "model_hub.provider_latency_ms",
            "model_hub.tokens_used",
            "model_hub.cost_usd",
        }
        actual = {n for n, d in ALL_METRICS.items() if d.type == MetricType.HISTOGRAM}
        assert actual == expected

    def test_expected_gauge_names(self) -> None:
        expected = {
            "model_hub.active_requests",
            "model_hub.provider_circuit_state",
            "model_hub.budget_pct",
        }
        actual = {n for n, d in ALL_METRICS.items() if d.type == MetricType.GAUGE}
        assert actual == expected
