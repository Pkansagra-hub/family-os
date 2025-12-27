"""Tests for chaos network transport with latency injection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from k0.chaos.network import ChaosTransport
from k0.kernel.config import ChaosSettings


class TestChaosTransport:
    """Tests for ChaosTransport class."""

    def test_init(self):
        """Test ChaosTransport initialization."""
        base_transport = MagicMock(spec=httpx.BaseTransport)
        chaos_config = ChaosSettings(enabled=True, network_latency_ms=100)
        metrics_exporter = MagicMock()

        transport = ChaosTransport(base_transport, chaos_config, metrics_exporter)

        assert transport._base == base_transport
        assert transport._config == chaos_config
        assert transport._metrics == metrics_exporter

    def test_init_no_metrics(self):
        """Test ChaosTransport initialization without metrics."""
        base_transport = MagicMock(spec=httpx.BaseTransport)
        chaos_config = ChaosSettings(enabled=True, network_latency_ms=100)

        transport = ChaosTransport(base_transport, chaos_config)

        assert transport._base == base_transport
        assert transport._config == chaos_config
        assert transport._metrics is None

    @patch("k0.chaos.toggles.get_network_delay_ms")
    @patch("time.sleep")
    def test_handle_request_with_delay(self, mock_sleep, mock_get_delay):
        """Test request handling with latency injection."""
        mock_get_delay.return_value = 200  # 200ms delay

        base_transport = MagicMock(spec=httpx.BaseTransport)
        mock_response = MagicMock(spec=httpx.Response)
        base_transport.handle_request.return_value = mock_response

        chaos_config = ChaosSettings(enabled=True, network_latency_ms=200)
        metrics_exporter = MagicMock()

        transport = ChaosTransport(base_transport, chaos_config, metrics_exporter)
        request = MagicMock(spec=httpx.Request)

        response = transport.handle_request(request)

        # Should call get_network_delay_ms with config
        mock_get_delay.assert_called_once_with(chaos_config)

        # Should sleep for 0.2 seconds (200ms)
        mock_sleep.assert_called_once_with(0.2)

        # Should emit metrics
        metrics_exporter.histogram.assert_called_once_with(
            "k0_chaos_network_delay_seconds", help_text="Injected network latency in seconds"
        )
        # The histogram.observe should be called on the returned histogram
        histogram_mock = metrics_exporter.histogram.return_value
        histogram_mock.observe.assert_called_once_with(0.2)

        # Should call base transport
        base_transport.handle_request.assert_called_once_with(request)

        # Should return response
        assert response == mock_response

    @patch("k0.chaos.toggles.get_network_delay_ms")
    @patch("time.sleep")
    def test_handle_request_no_delay(self, mock_sleep, mock_get_delay):
        """Test request handling with no latency injection."""
        mock_get_delay.return_value = 0  # No delay

        base_transport = MagicMock(spec=httpx.BaseTransport)
        mock_response = MagicMock(spec=httpx.Response)
        base_transport.handle_request.return_value = mock_response

        chaos_config = ChaosSettings(enabled=True, network_latency_ms=0)
        metrics_exporter = MagicMock()

        transport = ChaosTransport(base_transport, chaos_config, metrics_exporter)
        request = MagicMock(spec=httpx.Request)

        response = transport.handle_request(request)

        # Should call get_network_delay_ms with config
        mock_get_delay.assert_called_once_with(chaos_config)

        # Should not sleep
        mock_sleep.assert_not_called()

        # Should not emit metrics
        metrics_exporter.histogram.assert_not_called()

        # Should call base transport
        base_transport.handle_request.assert_called_once_with(request)

        # Should return response
        assert response == mock_response

    @patch("k0.chaos.toggles.get_network_delay_ms")
    @patch("time.sleep")
    def test_handle_request_no_metrics(self, mock_sleep, mock_get_delay):
        """Test request handling with delay but no metrics exporter."""
        mock_get_delay.return_value = 100  # 100ms delay

        base_transport = MagicMock(spec=httpx.BaseTransport)
        mock_response = MagicMock(spec=httpx.Response)
        base_transport.handle_request.return_value = mock_response

        chaos_config = ChaosSettings(enabled=True, network_latency_ms=100)

        transport = ChaosTransport(base_transport, chaos_config)  # No metrics
        request = MagicMock(spec=httpx.Request)

        response = transport.handle_request(request)

        # Should call get_network_delay_ms with config
        mock_get_delay.assert_called_once_with(chaos_config)

        # Should sleep for 0.1 seconds (100ms)
        mock_sleep.assert_called_once_with(0.1)

        # Should call base transport
        base_transport.handle_request.assert_called_once_with(request)

        # Should return response
        assert response == mock_response

    def test_handle_request_exception_propagation(self):
        """Test that exceptions from base transport are propagated."""
        base_transport = MagicMock(spec=httpx.BaseTransport)
        base_transport.handle_request.side_effect = httpx.ConnectError("Connection failed")

        chaos_config = ChaosSettings(enabled=False)  # No delay
        transport = ChaosTransport(base_transport, chaos_config)

        request = MagicMock(spec=httpx.Request)

        with pytest.raises(httpx.ConnectError, match="Connection failed"):
            transport.handle_request(request)

    def test_close(self):
        """Test transport close method."""
        base_transport = MagicMock(spec=httpx.BaseTransport)
        chaos_config = ChaosSettings(enabled=True)

        transport = ChaosTransport(base_transport, chaos_config)

        transport.close()

        # Should call close on base transport
        base_transport.close.assert_called_once()
