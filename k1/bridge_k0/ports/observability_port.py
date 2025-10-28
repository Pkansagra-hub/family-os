"""
Observability Port Adapter - K0 Observability Port (Metrics)

Layer: L5 Infrastructure
Component: K0 Bridge → Observability Port
Priority: P1 (Monitoring)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Dual Protocol (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0002d: Observability Schema (Prometheus metrics)
    - ADR-0014: JSON REST API Dual Format (content negotiation)

Dependencies:
    Internal:
        - k1.bridge_k0.http2_client.HTTP2Connection (transport)
    External:
        - prometheus_client (Prometheus metrics parsing)

Connects To:
    Upstream:
        - K0 Observability Port: GET /k0/metrics (Prometheus text format)
    Downstream:
        - K1 metrics aggregator (optional: merge K0 + K1 metrics)
        - External monitoring (Prometheus scraper)

Performance Budgets:
    - Metrics fetch: <50ms P95 (K1 → K0 /metrics)
    - Metrics parse: <10ms P95 (Prometheus text format)
    - Scrape interval: 15s (Prometheus standard)

Observability:
    Metrics:
        - k1_k0_observability_port_scrapes_total{status} (counter)
        - k1_k0_observability_port_scrape_latency_ms{p50, p95, p99} (histogram)
        - k1_k0_observability_port_metric_count{source} (gauge)
    Traces:
        - Span: k0_bridge.observability_port_scrape
        - Attributes: k0_host, metric_count
    Logs:
        - INFO: metrics scraped (metric_count, latency_ms)
        - WARNING: metrics scrape slow (latency_ms >100ms)
        - ERROR: metrics scrape failed (reason)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Whiteboard: docs/whiteboard.md (Section: K0 Observability Port)
    - Test: tests/k1/bridge_k0/ports/test_observability_port.py
"""

import logging
import time
from dataclasses import dataclass

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict, List, Optional

# Third-party imports
# from prometheus_client.parser import text_string_to_metric_families

# Internal imports
# from k1.bridge_k0.http2_client import HTTP2Connection

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0001a)
# Assigned to: Issue #L5-1.2.4
DEFAULT_CONFIG = {
    "k0_host": "localhost",
    "k0_observability_port": 9090,  # K0 metrics port (Prometheus standard)
    "endpoint": "/metrics",  # K0 metrics endpoint
    "scrape_interval_s": 15,  # 15s scrape interval (Prometheus standard)
    "timeout_ms": 5000,  # 5s timeout for metrics requests
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


@dataclass
class MetricSample:
    """
    Prometheus metric sample.

    Fields:
        name: Metric name (e.g., "k0_wal_write_latency_ms")
        labels: Metric labels (dict, e.g., {"status": "success", "priority": "0"})
        value: Metric value (float)
        timestamp: Sample timestamp (Unix milliseconds, optional)
    """

    name: str
    labels: Dict[str, str]
    value: float
    timestamp: Optional[float] = None


@dataclass
class MetricsSnapshot:
    """
    Snapshot of K0 metrics.

    Fields:
        samples: List of metric samples
        scrape_timestamp: Timestamp when metrics were scraped
        scrape_latency_ms: Scrape latency in milliseconds
        k0_host: K0 host from which metrics were scraped
    """

    samples: List[MetricSample]
    scrape_timestamp: float
    scrape_latency_ms: float
    k0_host: str


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class ObservabilityPort:
    """
    Adapter for K0 Observability Port (Prometheus metrics).

    Purpose:
        Scrapes Prometheus metrics from K0 Observability Port, parses Prometheus
        text format, optionally aggregates with K1 metrics, exposes merged metrics
        for external Prometheus scraper.

    Responsibilities:
        1. Scrape K0 metrics (GET /k0/metrics)
        2. Parse Prometheus text format (metric families, labels, values)
        3. Optional: Merge K0 + K1 metrics (shared namespace)
        4. Expose metrics for Prometheus scraper
        5. Handle scrape failures (retries, timeout)

    Lifecycle:
        INIT → READY → [DEGRADED] → TERMINATED

    Thread Safety: Yes (async-safe)
    Async Safe: Yes (fully async/await compatible)

    Performance Budget (P95):
        - Metrics fetch: <50ms (K1 → K0 /metrics)
        - Metrics parse: <10ms (Prometheus text format)
        - Total scrape: <100ms

    Examples:
        >>> config = {'k0_host': 'localhost', 'k0_observability_port': 9090}
        >>> obs_port = ObservabilityPort(config)
        >>> await obs_port.initialize()
        >>>
        >>> # Scrape K0 metrics
        >>> snapshot = await obs_port.scrape_metrics()
        >>> print(f'Scraped {len(snapshot.samples)} metrics in {snapshot.scrape_latency_ms}ms')
        >>>
        >>> # Get specific metric
        >>> wal_latency = obs_port.get_metric('k0_wal_write_latency_ms')
        >>> print(f'WAL latency: {wal_latency.value}ms')
        >>>
        >>> await obs_port.shutdown()

    References:
        - ADR-0002d: Observability Schema (Prometheus metrics)
        - ADR-0001a: K0 Bridge Dual Protocol
        - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize ObservabilityPort adapter.

        Args:
            config: Configuration dict with K0 host, port, endpoints

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes internal state (metrics cache, scrape scheduler)
            - Does NOT scrape metrics (call initialize() to start scraping)

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.4
        """
        # TODO(@infrastructure-team): Implement initialization (ADR-0001a)
        # 1. Validate config (check k0_host, k0_observability_port, endpoint)
        # 2. Initialize state machine (INIT → READY)
        # 3. Initialize metrics cache (last snapshot)
        # 4. Initialize scrape scheduler (15s interval)
        self.config = config
        self.state = "INIT"  # State: INIT | READY | DEGRADED | TERMINATED
        self._logger = logger
        self._last_snapshot: Optional[MetricsSnapshot] = None
        pass

    async def initialize(self) -> None:
        """
        Async initialization phase - start metrics scraping.

        This method performs async setup (start scrape scheduler).

        Raises:
            RuntimeError: If initialization fails

        Lifecycle:
            Transitions: INIT → READY

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.4
        """
        # TODO(@infrastructure-team): Implement async initialization (ADR-0001a)
        # 1. Start scrape scheduler (15s interval background task)
        # 2. Perform initial scrape (populate metrics cache)
        # 3. Transition state: INIT → READY
        self.state = "READY"
        self._logger.info(
            "observability_port_initialized",
            k0_host=self.config.get("k0_host"),
            k0_port=self.config.get("k0_observability_port"),
        )
        pass

    async def scrape_metrics(self) -> MetricsSnapshot:
        """
        Scrape K0 metrics from Observability Port.

        This method fetches Prometheus metrics from K0, parses text format.

        Returns:
            MetricsSnapshot with samples, scrape timestamp, latency

        Raises:
            RuntimeError: If K0 Observability Port unavailable
            ValueError: If Prometheus text format invalid

        Performance:
            - Target: <50ms P95 (K1 → K0 /metrics)
            - Parse: <10ms P95 (Prometheus text format)

        Observability:
            - Metrics: k1_k0_observability_port_scrapes_total{status}
            - Traces: Span name: k0_bridge.observability_port_scrape
            - Logs: INFO: metrics scraped (metric_count, latency_ms)

        ADR: ADR-0002d (Observability Schema)
        Assigned to: Issue #L5-1.2.4
        """
        # TODO(@infrastructure-team): Implement scrape_metrics (ADR-0002d)
        # 1. Send HTTP GET request to K0 (GET /k0/metrics)
        # 2. Parse Prometheus text format (prometheus_client.parser)
        # 3. Extract metric samples (name, labels, value, timestamp)
        # 4. Create MetricsSnapshot (samples, scrape_timestamp, latency)
        # 5. Update metrics cache (last_snapshot)
        # 6. Record metrics (scrape latency, metric count)
        # 7. Return MetricsSnapshot
        start_time = time.time()

        self._logger.info("scrape_metrics_started", k0_host=self.config.get("k0_host"))

        # Placeholder return (MUST be replaced with actual implementation)
        snapshot = MetricsSnapshot(
            samples=[],
            scrape_timestamp=time.time() * 1000,
            scrape_latency_ms=(time.time() - start_time) * 1000,
            k0_host=self.config.get("k0_host", "localhost"),
        )

        self._last_snapshot = snapshot
        return snapshot

    def get_metric(
        self, metric_name: str, labels: Optional[Dict[str, str]] = None
    ) -> Optional[MetricSample]:
        """
        Get specific metric from last snapshot.

        Args:
            metric_name: Metric name (e.g., "k0_wal_write_latency_ms")
            labels: Optional labels filter (e.g., {"status": "success"})

        Returns:
            MetricSample if found, None otherwise

        ADR: ADR-0002d (Observability Schema)
        Assigned to: Issue #L5-1.2.4
        """
        # TODO(@infrastructure-team): Implement get_metric (ADR-0002d)
        # 1. Check last_snapshot exists
        # 2. Filter samples by metric_name
        # 3. If labels provided, filter by labels
        # 4. Return first matching sample (or None)
        pass

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Stop scrape scheduler
            - Clear metrics cache

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.4
        """
        # TODO(@infrastructure-team): Implement shutdown (ADR-0001a)
        # 1. Set state to TERMINATED
        # 2. Cancel scrape scheduler task
        # 3. Clear metrics cache
        # 4. Flush metrics (Prometheus)
        self.state = "TERMINATED"
        self._logger.info("observability_port_shutdown_complete")
        pass


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


def create_observability_port(
    config: Optional[Dict[str, Any]] = None,
) -> ObservabilityPort:
    """
    Create ObservabilityPort with default or provided configuration.

    Args:
        config: Configuration dict (default: localhost:9090)

    Returns:
        ObservabilityPort instance

    ADR: ADR-0001a (K0 Bridge Dual Protocol)
    Assigned to: Issue #L5-1.2.4
    """
    if config is None:
        config = DEFAULT_CONFIG

    return ObservabilityPort(config)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "ObservabilityPort",
    "MetricSample",
    "MetricsSnapshot",
    "create_observability_port",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_observability_port_scrapes_total{status} (counter)
#   - k1_k0_observability_port_scrape_latency_ms{p50, p95, p99} (histogram)
#   - k1_k0_observability_port_metric_count{source} (gauge: k0 metric count)
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.observability_port_scrape
#   - Attributes: k0_host, metric_count, scrape_latency_ms
#   - Links to: K0 metrics endpoint spans
#
# Logs to emit (structured logging):
#   - Level: INFO (scrape success), WARNING (slow scrape), ERROR (scrape failure)
#   - Fields: component='observability_port', k0_host, metric_count, latency_ms
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/ports/test_observability_port.py
#   - Test metrics scraping (GET /k0/metrics)
#   - Test Prometheus text format parsing
#   - Test metrics cache (last_snapshot)
#   - Test get_metric (by name and labels)
#   - Test scrape scheduler (15s interval)
#
# No simulation code allowed:
#   - Use real K0 mock server with /metrics endpoint
#   - Test Prometheus text format (counters, histograms, gauges)
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert scrape latency <50ms P95
#   - Assert parse latency <10ms P95
#   - Assert total scrape <100ms P95
#
# =============================================================================
