"""QoS-specific metrics for token bucket, rejection tracking, and port isolation."""

from __future__ import annotations

from k0.obs import MetricsExporter

__all__ = ["QoSMetrics"]


class QoSMetrics:
    """Thin wrapper around MetricsExporter for QoS counters and gauges."""

    def __init__(self, metrics_exporter: MetricsExporter) -> None:
        """Initialize QoS metrics with a Prometheus exporter.

        Args:
            metrics_exporter: Shared MetricsExporter instance
        """
        self._exporter = metrics_exporter

        # Counters: total acquisitions (successes)
        self._token_acquisitions = metrics_exporter.counter(
            name="qos_token_acquisitions_total",
            description="Total successful token acquisitions by band and port",
            labelnames=["band", "port"],
        )

        # Counters: rejection reasons
        self._rejections_capacity = metrics_exporter.counter(
            name="qos_rejections_capacity_total",
            description="Total token acquisition rejections due to capacity exceeded",
            labelnames=["band", "port"],
        )
        self._rejections_outside_hours = metrics_exporter.counter(
            name="qos_rejections_outside_hours_total",
            description="Total token acquisition rejections due to effective hours",
            labelnames=["band", "port"],
        )
        self._rejections_rate_limited = metrics_exporter.counter(
            name="qos_rejections_rate_limited_total",
            description="Total token acquisition rejections due to rate limiter",
            labelnames=["band", "port"],
        )
        self._rejections_total = metrics_exporter.counter(
            name="qos_rejections_total",
            description="Total QoS token acquisition rejections",
            labelnames=["band", "port", "reason"],
        )

        # Gauges: active tokens per port
        self._active_tokens = metrics_exporter.gauge(
            name="qos_active_tokens",
            description="Currently active tokens held by requests",
            labelnames=["port"],
        )

        # Gauges: port capacity utilization
        self._port_utilization = metrics_exporter.gauge(
            name="qos_port_utilization_percent",
            description="Port capacity utilization percentage",
            labelnames=["port"],
        )

        # Gauge: scheduler profile active limits
        self._port_limit = metrics_exporter.gauge(
            name="qos_port_limit_tokens",
            description="Current token limit for port",
            labelnames=["port"],
        )

    def record_acquisition(self, *, band: str, port: str) -> None:
        """Record successful token acquisition."""
        self._token_acquisitions.labels(band=band, port=port).inc()

    def record_rejection_capacity(self, *, band: str, port: str) -> None:
        """Record rejection due to capacity exceeded."""
        self._rejections_capacity.labels(band=band, port=port).inc()
        self._rejections_total.labels(band=band, port=port, reason="capacity").inc()

    def record_rejection_outside_hours(self, *, band: str, port: str) -> None:
        """Record rejection due to effective hours."""
        self._rejections_outside_hours.labels(band=band, port=port).inc()
        self._rejections_total.labels(band=band, port=port, reason="outside_hours").inc()

    def record_rejection_rate_limited(self, *, band: str, port: str) -> None:
        """Record rejection due to rate limiter."""
        self._rejections_rate_limited.labels(band=band, port=port).inc()
        self._rejections_total.labels(band=band, port=port, reason="rate_limited").inc()

    def set_active_tokens(self, *, port: str, count: int) -> None:
        """Update active token gauge for a port."""
        self._active_tokens.labels(port=port).set(count)

    def set_port_utilization(self, *, port: str, percent: float) -> None:
        """Update port utilization percentage gauge."""
        self._port_utilization.labels(port=port).set(max(0, min(100, percent)))

    def set_port_limit(self, *, port: str, limit: int) -> None:
        """Update port limit gauge."""
        self._port_limit.labels(port=port).set(limit)

    def update_port_metrics(self, *, port: str, active: int, limit: int) -> None:
        """Convenience: update active tokens, utilization, and limit in one call."""
        self.set_active_tokens(port=port, count=active)
        utilization = (active / limit * 100) if limit > 0 else 0.0
        self.set_port_utilization(port=port, percent=utilization)
        self.set_port_limit(port=port, limit=limit)
