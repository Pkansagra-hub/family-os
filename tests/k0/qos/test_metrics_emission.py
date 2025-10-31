"""Test QoS metrics emission from scheduler."""

from __future__ import annotations

import pytest

from k0.obs import MetricsExporter
from k0.qos import QoSMetrics, Scheduler, SchedulerCapacityError, SchedulerProfile


@pytest.fixture
def metrics_exporter() -> MetricsExporter:
    """Create a fresh metrics exporter for each test."""
    return MetricsExporter(namespace="test_qos_metrics")


@pytest.fixture
def qos_metrics(metrics_exporter: MetricsExporter) -> QoSMetrics:
    """Create QoS metrics instrumentation."""
    return QoSMetrics(metrics_exporter)


@pytest.fixture
def scheduler_with_metrics(qos_metrics: QoSMetrics) -> Scheduler:
    """Create scheduler with metrics wired in."""
    profile = SchedulerProfile(
        name="test",
        description="Test profile",
        port_limits={"command": 4, "query": 6},
        default_port_limit=4,
    )
    scheduler = Scheduler(profile=profile, qos_metrics=qos_metrics)
    return scheduler


class TestQoSMetricsEmission:
    """Test that metrics are emitted on scheduler operations."""

    def test_scheduler_emits_acquisition_counter_on_success(
        self,
        scheduler_with_metrics: Scheduler,
        metrics_exporter: MetricsExporter,
    ) -> None:
        """Verify acquisition counter increments on successful token acquisition."""
        # Acquire a token
        token = scheduler_with_metrics.acquire(band="REALTIME", port="command", cost=2)

        # Check metric was incremented
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_token_acquisitions_total",
            {"band": "REALTIME", "port": "command"},
        )
        assert sample_value == 1.0, "Acquisition counter should be incremented"

        # Release and verify no change to acquisition counter
        token.release()
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_token_acquisitions_total",
            {"band": "REALTIME", "port": "command"},
        )
        assert sample_value == 1.0, "Release should not affect acquisition counter"

    def test_scheduler_emits_rejection_counter_on_capacity_exceeded(
        self,
        scheduler_with_metrics: Scheduler,
        metrics_exporter: MetricsExporter,
    ) -> None:
        """Verify rejection counter increments when capacity is exceeded."""
        # Fill up the port
        token1 = scheduler_with_metrics.acquire(band="AMBER", port="command", cost=2)
        token2 = scheduler_with_metrics.acquire(band="AMBER", port="command", cost=2)

        # Attempt to exceed capacity
        with pytest.raises(SchedulerCapacityError):
            scheduler_with_metrics.acquire(band="AMBER", port="command", cost=1)

        # Check rejection metric was incremented
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_rejections_capacity_total",
            {"band": "AMBER", "port": "command"},
        )
        assert sample_value == 1.0, "Rejection counter should be incremented"

        # Also check total rejections counter
        total_rejections = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_rejections_total",
            {"band": "AMBER", "port": "command", "reason": "capacity"},
        )
        assert total_rejections == 1.0, "Total rejections counter should be incremented"

        token1.release()
        token2.release()

    def test_scheduler_updates_active_tokens_gauge(
        self,
        scheduler_with_metrics: Scheduler,
        metrics_exporter: MetricsExporter,
    ) -> None:
        """Verify active tokens gauge is updated on acquire and release."""
        # Initially gauge should be 0
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_active_tokens",
            {"port": "command"},
        )
        assert sample_value in (None, 0.0), "Active tokens should start at 0"

        # Acquire token
        token = scheduler_with_metrics.acquire(band="REALTIME", port="command", cost=3)

        # Check active tokens gauge
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_active_tokens",
            {"port": "command"},
        )
        assert sample_value == 3.0, "Active tokens gauge should be 3"

        # Release token
        token.release()

        # Check active tokens gauge reset
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_active_tokens",
            {"port": "command"},
        )
        assert sample_value == 0.0, "Active tokens gauge should reset to 0"

    def test_scheduler_updates_utilization_gauge(
        self,
        scheduler_with_metrics: Scheduler,
        metrics_exporter: MetricsExporter,
    ) -> None:
        """Verify port utilization percentage is updated."""
        # Port limit is 6 for query port, acquire 3 tokens = 50% utilization
        token = scheduler_with_metrics.acquire(band="AMBER", port="query", cost=3)

        # Check utilization gauge (6 limit, 3 active = 50%)
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_port_utilization_percent",
            {"port": "query"},
        )
        assert sample_value == 50.0, "Utilization should be 50%"

        # Acquire more tokens
        token2 = scheduler_with_metrics.acquire(band="AMBER", port="query", cost=3)

        # Check utilization gauge (6 limit, 6 active = 100%)
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_port_utilization_percent",
            {"port": "query"},
        )
        assert sample_value == 100.0, "Utilization should be 100%"

        token.release()
        token2.release()

    def test_scheduler_updates_port_limit_gauge(
        self,
        scheduler_with_metrics: Scheduler,
        metrics_exporter: MetricsExporter,
    ) -> None:
        """Verify port limit gauge reflects profile limits."""
        # Acquire a token to trigger gauge update
        token = scheduler_with_metrics.acquire(band="REALTIME", port="query", cost=1)

        # Check port limit gauge
        sample_value = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_port_limit_tokens",
            {"port": "query"},
        )
        assert sample_value == 6.0, "Port limit gauge should reflect profile limit of 6"

        token.release()

    def test_metrics_isolation_between_ports(
        self,
        scheduler_with_metrics: Scheduler,
        metrics_exporter: MetricsExporter,
    ) -> None:
        """Verify metrics are isolated between ports."""
        # Acquire from command port
        token1 = scheduler_with_metrics.acquire(band="AMBER", port="command", cost=2)

        # Acquire from query port
        token2 = scheduler_with_metrics.acquire(band="AMBER", port="query", cost=3)

        # Check acquisition metrics are separate
        command_acquisitions = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_token_acquisitions_total",
            {"band": "AMBER", "port": "command"},
        )
        query_acquisitions = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_token_acquisitions_total",
            {"band": "AMBER", "port": "query"},
        )
        assert command_acquisitions == 1.0
        assert query_acquisitions == 1.0

        # Check active tokens are separate
        command_active = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_active_tokens",
            {"port": "command"},
        )
        query_active = metrics_exporter.registry.get_sample_value(
            "test_qos_metrics_qos_active_tokens",
            {"port": "query"},
        )
        assert command_active == 2.0
        assert query_active == 3.0

        token1.release()
        token2.release()
