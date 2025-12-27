"""Tests for chaos toggle decision functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from k0.chaos.toggles import (
    apply_scheduler_starvation,
    get_network_delay_ms,
    should_drop_telemetry,
    should_fail_fsync,
)
from k0.kernel.config import ChaosSettings
from k0.qos.scheduler import SchedulerProfile


class TestShouldFailFsync:
    """Tests for should_fail_fsync function."""

    def test_disabled_chaos(self):
        """Test fsync failure when chaos is disabled."""
        config = ChaosSettings(enabled=False, wal_fsync_fail_rate=0.5)
        metrics = MagicMock()

        result = should_fail_fsync(config, metrics)

        assert result.should_inject is False
        assert result.reason == "chaos_disabled_or_zero_rate"
        assert result.metadata is None

    def test_zero_fail_rate(self):
        """Test fsync failure when fail rate is zero."""
        config = ChaosSettings(enabled=True, wal_fsync_fail_rate=0.0)
        metrics = MagicMock()

        result = should_fail_fsync(config, metrics)

        assert result.should_inject is False
        assert result.reason == "chaos_disabled_or_zero_rate"
        assert result.metadata is None

    @patch("random.random")
    def test_injection_true(self, mock_random):
        """Test fsync failure injection when probability met."""
        mock_random.return_value = 0.3  # Below 0.5 threshold

        config = ChaosSettings(enabled=True, wal_fsync_fail_rate=0.5)
        metrics = MagicMock()

        result = should_fail_fsync(config, metrics)

        assert result.should_inject is True
        assert result.reason == "probabilistic_injection"
        assert result.metadata == {"fail_rate": 0.5}

        # Should emit metrics
        metrics.counter.assert_called_once_with(
            "chaos_fsync_injected_total", "Total WAL fsync failures injected by chaos"
        )
        # The counter.inc should be called on the returned counter
        counter_mock = metrics.counter.return_value
        counter_mock.inc.assert_called_once()

    @patch("random.random")
    def test_injection_false(self, mock_random):
        """Test fsync failure not injected when probability not met."""
        mock_random.return_value = 0.7  # Above 0.5 threshold

        config = ChaosSettings(enabled=True, wal_fsync_fail_rate=0.5)
        metrics = MagicMock()

        result = should_fail_fsync(config, metrics)

        assert result.should_inject is False
        assert result.reason == "probability_not_met"
        assert result.metadata == {"fail_rate": 0.5}

        # Should not emit metrics
        metrics.counter.assert_not_called()

    @patch("random.random")
    def test_no_metrics_exporter(self, mock_random):
        """Test fsync failure injection without metrics exporter."""
        mock_random.return_value = 0.3  # Below 0.5 threshold

        config = ChaosSettings(enabled=True, wal_fsync_fail_rate=0.5)

        result = should_fail_fsync(config)  # No metrics

        assert result.should_inject is True
        assert result.reason == "probabilistic_injection"
        assert result.metadata == {"fail_rate": 0.5}


class TestApplySchedulerStarvation:
    """Tests for apply_scheduler_starvation function."""

    def test_disabled_chaos(self):
        """Test scheduler starvation when chaos is disabled."""
        profile = SchedulerProfile(
            name="test",
            description="test profile",
            port_limits={"port1": 10, "port2": 20},
            default_port_limit=5,
        )
        config = ChaosSettings(enabled=False, scheduler_starvation_multiplier=0.5)
        metrics = MagicMock()

        result = apply_scheduler_starvation(profile, config, metrics)

        # Should return original profile unchanged
        assert result == profile

    def test_full_capacity_multiplier(self):
        """Test scheduler starvation when multiplier is 1.0 (full capacity)."""
        profile = SchedulerProfile(
            name="test",
            description="test profile",
            port_limits={"port1": 10, "port2": 20},
            default_port_limit=5,
        )
        config = ChaosSettings(enabled=True, scheduler_starvation_multiplier=1.0)
        metrics = MagicMock()

        result = apply_scheduler_starvation(profile, config, metrics)

        # Should return original profile unchanged
        assert result == profile

    def test_capacity_reduction(self):
        """Test scheduler starvation with capacity reduction."""
        profile = SchedulerProfile(
            name="test",
            description="test profile",
            port_limits={"port1": 10, "port2": 20},
            default_port_limit=5,
        )
        config = ChaosSettings(enabled=True, scheduler_starvation_multiplier=0.5)
        metrics = MagicMock()

        result = apply_scheduler_starvation(profile, config, metrics)

        # Should create new profile with reduced limits
        assert result.name == profile.name
        assert result.description == profile.description
        assert result.default_port_limit == profile.default_port_limit

        # Limits should be reduced by multiplier
        assert result.port_limits["port1"] == 5  # 10 * 0.5
        assert result.port_limits["port2"] == 10  # 20 * 0.5

        # Should emit metrics
        metrics.gauge.assert_called_once_with(
            "scheduler_throttled_multiplier",
            "Current scheduler capacity multiplier (1.0=normal, <1.0=starved)",
        )
        # The gauge.set should be called on the returned gauge
        gauge_mock = metrics.gauge.return_value
        gauge_mock.set.assert_called_once_with(0.5)

    def test_minimum_capacity_one(self):
        """Test scheduler starvation ensures minimum capacity of 1."""
        profile = SchedulerProfile(
            name="test", description="test profile", port_limits={"port1": 2}, default_port_limit=5
        )
        config = ChaosSettings(enabled=True, scheduler_starvation_multiplier=0.1)  # Very low
        metrics = MagicMock()

        result = apply_scheduler_starvation(profile, config, metrics)

        # Should ensure minimum of 1
        assert result.port_limits["port1"] == 1  # max(1, int(2 * 0.1)) = max(1, 0) = 1

    def test_no_metrics_exporter(self):
        """Test scheduler starvation without metrics exporter."""
        profile = SchedulerProfile(
            name="test", description="test profile", port_limits={"port1": 10}, default_port_limit=5
        )
        config = ChaosSettings(enabled=True, scheduler_starvation_multiplier=0.5)

        result = apply_scheduler_starvation(profile, config)  # No metrics

        # Should still apply reduction
        assert result.port_limits["port1"] == 5


class TestGetNetworkDelayMs:
    """Tests for get_network_delay_ms function."""

    def test_disabled_chaos(self):
        """Test network delay when chaos is disabled."""
        config = ChaosSettings(enabled=False, network_latency_ms=100)

        result = get_network_delay_ms(config)

        assert result == 0

    def test_enabled_chaos(self):
        """Test network delay when chaos is enabled."""
        config = ChaosSettings(enabled=True, network_latency_ms=250)

        result = get_network_delay_ms(config)

        assert result == 250

    def test_zero_delay(self):
        """Test network delay with zero delay configured."""
        config = ChaosSettings(enabled=True, network_latency_ms=0)

        result = get_network_delay_ms(config)

        assert result == 0


class TestShouldDropTelemetry:
    """Tests for should_drop_telemetry function."""

    def test_disabled_chaos(self):
        """Test telemetry dropping when chaos is disabled."""
        config = ChaosSettings(enabled=False, telemetry_outage_rate=0.5)
        metrics = MagicMock()

        result = should_drop_telemetry(config, metrics)

        assert result is False

    def test_zero_outage_rate(self):
        """Test telemetry dropping when outage rate is zero."""
        config = ChaosSettings(enabled=True, telemetry_outage_rate=0.0)
        metrics = MagicMock()

        result = should_drop_telemetry(config, metrics)

        assert result is False

    @patch("random.random")
    def test_drop_true(self, mock_random):
        """Test telemetry dropping when probability met."""
        mock_random.return_value = 0.3  # Below 0.5 threshold

        config = ChaosSettings(enabled=True, telemetry_outage_rate=0.5)
        metrics = MagicMock()

        result = should_drop_telemetry(config, metrics)

        assert result is True

        # Should emit metrics
        metrics.counter.assert_called_once_with(
            "chaos_telemetry_dropped", "Total telemetry emissions dropped by chaos"
        )
        # The counter.inc should be called on the returned counter
        counter_mock = metrics.counter.return_value
        counter_mock.inc.assert_called_once()

    @patch("random.random")
    def test_drop_false(self, mock_random):
        """Test telemetry not dropped when probability not met."""
        mock_random.return_value = 0.7  # Above 0.5 threshold

        config = ChaosSettings(enabled=True, telemetry_outage_rate=0.5)
        metrics = MagicMock()

        result = should_drop_telemetry(config, metrics)

        assert result is False

        # Should not emit metrics
        metrics.counter.assert_not_called()

    @patch("random.random")
    def test_no_metrics_exporter(self, mock_random):
        """Test telemetry dropping without metrics exporter."""
        mock_random.return_value = 0.3  # Below 0.5 threshold

        config = ChaosSettings(enabled=True, telemetry_outage_rate=0.5)

        result = should_drop_telemetry(config)  # No metrics

        assert result is True

    @patch("random.random")
    def test_metrics_exporter_exception(self, mock_random):
        """Test telemetry dropping when metrics exporter throws exception."""
        mock_random.return_value = 0.3  # Below 0.5 threshold

        config = ChaosSettings(enabled=True, telemetry_outage_rate=0.5)
        metrics = MagicMock()
        metrics.counter.side_effect = Exception("Metrics broken")

        result = should_drop_telemetry(config, metrics)

        assert result is True

        # Should attempt to emit metrics but fail silently
        metrics.counter.assert_called_once()
