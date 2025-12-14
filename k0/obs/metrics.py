"""Prometheus-backed metrics exporter utilities."""

from __future__ import annotations

import logging
import threading
from typing import Iterable, Mapping

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from .events import ObservabilityEmitter

__all__ = [
    "CONTENT_TYPE_LATEST",
    "MetricsExporter",
]


LOGGER = logging.getLogger(__name__)


class MetricsExporter:
    """Thin wrapper around Prometheus primitives with lazy metric creation."""

    def __init__(
        self,
        *,
        namespace: str = "k0_kernel",
        registry: CollectorRegistry | None = None,
        default_histogram_buckets: Iterable[float] | None = None,
        observability_emitter: ObservabilityEmitter | None = None,
    ) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)
        self.namespace = namespace
        self._default_histogram_buckets = tuple(
            default_histogram_buckets or (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
        )

        self._counters: dict[tuple[str, tuple[str, ...]], Counter] = {}
        self._gauges: dict[tuple[str, tuple[str, ...]], Gauge] = {}
        self._histograms: dict[tuple[str, tuple[str, ...]], Histogram] = {}

        self._lock = threading.RLock()
        self._observability_emitter = observability_emitter

    def attach_observability_emitter(self, emitter: ObservabilityEmitter | None) -> None:
        """Attach or replace the observability emitter used for metric updates."""

        self._observability_emitter = emitter

    def counter(
        self,
        name: str,
        description: str,
        *,
        labelnames: Iterable[str] = (),
    ) -> Counter:
        key = (name, tuple(sorted(labelnames)))
        with self._lock:
            metric = self._counters.get(key)
            if metric is not None:
                return metric
            metric = Counter(
                name,
                description,
                labelnames=tuple(sorted(labelnames)),
                namespace=self.namespace,
                registry=self.registry,
            )
            self._counters[key] = metric
            return metric

    def gauge(
        self,
        name: str,
        description: str,
        *,
        labelnames: Iterable[str] = (),
    ) -> Gauge:
        key = (name, tuple(sorted(labelnames)))
        with self._lock:
            metric = self._gauges.get(key)
            if metric is not None:
                return metric
            metric = Gauge(
                name,
                description,
                labelnames=tuple(sorted(labelnames)),
                namespace=self.namespace,
                registry=self.registry,
            )
            self._gauges[key] = metric
            return metric

    def histogram(
        self,
        name: str,
        description: str,
        *,
        labelnames: Iterable[str] = (),
        buckets: Iterable[float] | None = None,
    ) -> Histogram:
        key = (name, tuple(sorted(labelnames)))
        with self._lock:
            metric = self._histograms.get(key)
            if metric is not None:
                return metric
            LOGGER.debug(
                "Registering histogram: %s, labels=%s, buckets=%s",
                name,
                labelnames,
                buckets,
            )
            metric = Histogram(
                name,
                description,
                labelnames=tuple(sorted(labelnames)),
                namespace=self.namespace,
                registry=self.registry,
                buckets=(
                    tuple(buckets) if buckets is not None else self._default_histogram_buckets
                ),
            )
            self._histograms[key] = metric
            return metric

    def emit(self, metric_name: str, value: float = 1.0, **labels: str) -> None:
        """Increment (or create) a counter metric."""

        labelnames = tuple(sorted(labels.keys()))
        counter = self.counter(
            metric_name,
            f"Auto-generated counter for {metric_name}",
            labelnames=labelnames,
        )
        if labels:
            counter.labels(**labels).inc(value)
        else:
            counter.inc(value)
        self._emit_observability(
            operation="counter",
            metric_name=metric_name,
            value=value,
            labels=dict(labels),
        )

    def set_gauge(self, metric_name: str, value: float, **labels: str) -> None:
        """Set (or create) a gauge metric."""

        labelnames = tuple(sorted(labels.keys()))
        gauge = self.gauge(
            metric_name,
            f"Auto-generated gauge for {metric_name}",
            labelnames=labelnames,
        )
        if labelnames:
            gauge.labels(**labels).set(value)
        else:
            gauge.set(value)
        self._emit_observability(
            operation="gauge",
            metric_name=metric_name,
            value=value,
            labels=dict(labels),
        )

    def observe(
        self,
        metric_name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
        buckets: Iterable[float] | None = None,
    ) -> None:
        """Record a value for a histogram metric."""

        labels = labels or {}
        LOGGER.debug(
            "Observing histogram: %s, value=%s, labels=%s, buckets=%s",
            metric_name,
            value,
            labels,
            buckets,
        )
        histogram = self.histogram(
            metric_name,
            f"Auto-generated histogram for {metric_name}",
            labelnames=tuple(sorted(labels.keys())),
            buckets=buckets,
        )
        if labels:
            histogram.labels(**labels).observe(value)
        else:
            histogram.observe(value)
        self._emit_observability(
            operation="histogram",
            metric_name=metric_name,
            value=value,
            labels=dict(labels),
        )

    def latest(self) -> bytes:
        """Serialize metrics using Prometheus's text exposition format."""

        return generate_latest(self.registry)

    def _emit_observability(
        self,
        *,
        operation: str,
        metric_name: str,
        value: float,
        labels: Mapping[str, str],
    ) -> None:
        emitter = self._observability_emitter
        if emitter is None:
            return
        payload: dict[str, object] = {
            "event": "metric_update",
            "metric": metric_name,
            "namespace": self.namespace,
            "operation": operation,
            "value": value,
            "labels": dict(labels),
        }
        try:
            emitter.emit(payload)
        except Exception:  # pragma: no cover - defensive logging guard  # noqa: BLE001
            LOGGER.exception(
                "Failed to emit observability metric update",
                extra={"metric": metric_name, "operation": operation},
            )
