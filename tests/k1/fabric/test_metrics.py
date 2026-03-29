"""
Test Fabric Metrics
===================

IMPLEMENTATION PLAN REFERENCE: docs/plans/fabric-implementation-plan.md
EPIC: 7.2 Metrics Implementation
ISSUES: 7.2.1, 7.2.2, 7.2.3

Validates Fabric Prometheus metrics for SLIs/SLOs.
"""

import re
import time

import pytest

from k1.fabric.metrics import (
    CONTEXT_BUILD_DURATION_BUCKETS,
    EXECUTION_DURATION_BUCKETS,
    POLICY_EVALUATION_DURATION_BUCKETS,
    REGISTRY_LOOKUP_DURATION_BUCKETS,
    RETRIEVAL_DURATION_BUCKETS,
    FabricMetrics,
    get_default_metrics,
)
from k1.fabric.types import CapabilityType
from tests.k1.fabric.helpers import create_n_contracts


@pytest.fixture
def metrics() -> FabricMetrics:
    return FabricMetrics()


class TestMetricsConstants:
    def test_execution_buckets_defined(self) -> None:
        assert EXECUTION_DURATION_BUCKETS[0] < EXECUTION_DURATION_BUCKETS[-1]

    def test_retrieval_buckets_defined(self) -> None:
        assert RETRIEVAL_DURATION_BUCKETS[0] < RETRIEVAL_DURATION_BUCKETS[-1]

    def test_lookup_buckets_defined(self) -> None:
        assert REGISTRY_LOOKUP_DURATION_BUCKETS[0] < REGISTRY_LOOKUP_DURATION_BUCKETS[-1]

    def test_context_buckets_defined(self) -> None:
        assert CONTEXT_BUILD_DURATION_BUCKETS[0] < CONTEXT_BUILD_DURATION_BUCKETS[-1]

    def test_policy_eval_buckets_defined(self) -> None:
        assert POLICY_EVALUATION_DURATION_BUCKETS[0] < POLICY_EVALUATION_DURATION_BUCKETS[-1]


class TestHistograms:
    def test_execution_duration_histogram(self, metrics: FabricMetrics) -> None:
        metrics.observe_execution_duration("tool.execute.demo", "MCP", "LOW", 0.01)
        output = metrics.latest().decode("utf-8")
        assert "fabric_execution_duration_seconds" in output

    def test_retrieval_duration_histogram(self, metrics: FabricMetrics) -> None:
        metrics.observe_retrieval_duration("capabilities", 0.02)
        output = metrics.latest().decode("utf-8")
        assert "fabric_retrieval_duration_seconds" in output

    def test_registry_lookup_histogram(self, metrics: FabricMetrics) -> None:
        metrics.observe_registry_lookup(0.001)
        output = metrics.latest().decode("utf-8")
        assert "fabric_registry_lookup_duration_seconds" in output

    def test_context_build_histogram(self, metrics: FabricMetrics) -> None:
        metrics.observe_context_build("tool.execute.demo", 0.01)
        output = metrics.latest().decode("utf-8")
        assert "fabric_context_build_duration_seconds" in output

    def test_policy_eval_histogram(self, metrics: FabricMetrics) -> None:
        metrics.observe_policy_evaluation(0.002)
        output = metrics.latest().decode("utf-8")
        assert "fabric_policy_evaluation_duration_seconds" in output

    def test_time_execution_context_manager(self, metrics: FabricMetrics) -> None:
        with metrics.time_execution("tool.execute.demo", "MCP", "LOW"):
            time.sleep(0.001)

    def test_time_retrieval_context_manager(self, metrics: FabricMetrics) -> None:
        with metrics.time_retrieval("capabilities"):
            time.sleep(0.001)


class TestCounters:
    def test_executions_counter(self, metrics: FabricMetrics) -> None:
        metrics.inc_executions("success")
        metrics.inc_executions("failure", 2)
        output = metrics.latest().decode("utf-8")
        assert "fabric_executions_total" in output

    def test_retrievals_counter(self, metrics: FabricMetrics) -> None:
        metrics.inc_retrievals(3)
        output = metrics.latest().decode("utf-8")
        assert "fabric_retrievals_total" in output

    def test_registrations_counter(self, metrics: FabricMetrics) -> None:
        metrics.inc_registrations(2)
        output = metrics.latest().decode("utf-8")
        assert "fabric_registrations_total" in output

    def test_cb_trips_counter(self, metrics: FabricMetrics) -> None:
        metrics.inc_circuit_breaker_trips("provider-1")
        output = metrics.latest().decode("utf-8")
        assert "fabric_circuit_breaker_trips_total" in output

    def test_agent_spawns_counter(self, metrics: FabricMetrics) -> None:
        metrics.inc_agent_spawns()
        output = metrics.latest().decode("utf-8")
        assert "fabric_agent_spawns_total" in output

    def test_retries_counter(self, metrics: FabricMetrics) -> None:
        metrics.inc_retries("tool.execute.demo", 2)
        output = metrics.latest().decode("utf-8")
        assert "fabric_retries_total" in output


class TestGauges:
    def test_registry_size_gauge(self, metrics: FabricMetrics) -> None:
        metrics.set_registry_size("tool.execute", 5)
        output = metrics.latest().decode("utf-8")
        assert "fabric_registry_size" in output

    def test_cb_state_gauge(self, metrics: FabricMetrics) -> None:
        metrics.set_circuit_breaker_state("provider-1", "OPEN", 1)
        output = metrics.latest().decode("utf-8")
        assert "fabric_circuit_breaker_state" in output

    def test_agent_pool_size_gauge(self, metrics: FabricMetrics) -> None:
        metrics.set_agent_pool_size("agent.execute.demo", 3)
        output = metrics.latest().decode("utf-8")
        assert "fabric_agent_pool_size" in output

    def test_active_executions_gauge(self, metrics: FabricMetrics) -> None:
        metrics.inc_active_executions()
        metrics.dec_active_executions()
        output = metrics.latest().decode("utf-8")
        assert "fabric_active_executions" in output


class TestDefaultMetrics:
    def test_default_metrics_singleton(self) -> None:
        m1 = get_default_metrics()
        m2 = get_default_metrics()
        assert m1 is m2


class TestRegistryIntegration:
    def test_register_updates_registry_size(self, metrics: FabricMetrics, monkeypatch) -> None:
        from k1.fabric.core import registry as registry_module

        monkeypatch.setattr(registry_module, "get_default_metrics", lambda: metrics)

        registry = registry_module.CapabilityRegistry()
        contract = create_n_contracts(1)[0]
        registry.register(contract)

        type_key = CapabilityType.get_type(contract.name) or "unknown"
        output = metrics.latest().decode("utf-8")
        pattern = rf"fabric_registry_size\{{capability_type=\"{re.escape(type_key)}\"\}}"
        assert re.search(pattern, output) is not None


class TestCircuitBreakerIntegration:
    def test_cb_state_updates_metrics(self, metrics: FabricMetrics, monkeypatch) -> None:
        from k1.fabric.circuit_breaker import breaker as breaker_module

        monkeypatch.setattr(breaker_module, "get_default_metrics", lambda: metrics)

        cb = breaker_module.CircuitBreaker(
            provider_id="provider-test",
            config=breaker_module.CircuitBreakerConfig(),
        )
        cb.trip()

        output = metrics.latest().decode("utf-8")
        assert "fabric_circuit_breaker_state" in output
        assert "fabric_circuit_breaker_trips_total" in output
