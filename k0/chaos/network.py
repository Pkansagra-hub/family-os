"""
Network chaos transport for httpx client with latency injection.

CRITICAL: Uses time.sleep() for intentional latency injection - this is
acceptable chaos engineering practice, not simulation code.
"""

import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from k0.kernel.config import ChaosSettings
    from k0.obs.metrics import MetricsExporter


class ChaosTransport(httpx.BaseTransport):
    """
    httpx transport wrapper that injects network latency.

    Wraps an existing transport and adds configurable delay before
    each request to simulate network degradation.

    Example:
        >>> base = httpx.HTTPTransport()
        >>> chaos = ChaosTransport(base, chaos_config, metrics)
        >>> client = httpx.Client(transport=chaos)
    """

    def __init__(
        self,
        base_transport: httpx.BaseTransport,
        chaos_config: "ChaosSettings",
        metrics_exporter: "MetricsExporter | None" = None,
    ):
        """
        Initialize chaos transport wrapper.

        Args:
            base_transport: Underlying httpx transport to wrap
            chaos_config: Chaos configuration with network_latency_ms
            metrics_exporter: Optional metrics exporter for telemetry
        """
        self._base = base_transport
        self._config = chaos_config
        self._metrics = metrics_exporter

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """
        Handle HTTP request with optional latency injection.

        Args:
            request: httpx request to execute

        Returns:
            httpx.Response from underlying transport

        Raises:
            Any exceptions from base transport
        """
        from k0.chaos.toggles import get_network_delay_ms

        delay_ms = get_network_delay_ms(self._config)

        if delay_ms > 0:
            delay_seconds = delay_ms / 1000.0

            # INTENTIONAL delay injection (not simulation)
            time.sleep(delay_seconds)

            if self._metrics:
                self._metrics.histogram(
                    "k0_chaos_network_delay_seconds",
                    help_text="Injected network latency in seconds",
                ).observe(delay_seconds)

        return self._base.handle_request(request)

    def close(self) -> None:
        """Close underlying transport."""
        self._base.close()
