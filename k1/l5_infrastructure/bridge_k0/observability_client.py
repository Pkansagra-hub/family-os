"""K0 Bridge Observability Client.

This module implements the K1 → K0 observability bridge responsible for
forwarding metrics and structured logs to the K0 observability port.

Primary ADRs:
- ADR-0001a: K0 Bridge Architecture (observability port wiring, HTTP/2 transport)
- ADR-0086h: Agent Metrics & Observability (metric emission, batching cadence)

Contracts:
- k1/contracts/k0_bridge/protocols/json_envelope_spec.yml (observability port)
- k1/contracts/observability/*.yaml (structured logging & metrics schema)

Performance Budget:
- Metrics push: <20ms P95 (10s cadence)
- Log push: <20ms P95 (5s cadence)

The client keeps two async tasks:
1. Metric snapshot push every ``metrics_interval_sec`` (default: 10s)
2. Structured log batch push every ``logs_interval_sec`` (default: 5s)

Both payloads are POSTed to ``{endpoint}/k0/obs.emit`` with JSON envelopes
matching the observability contract. K0 currently returns HTTP 501 until the
observability port is fully implemented; the client treats that response as a
soft success so that downstream code can be enabled before the server exists.

Implementation Notes:
- HTTP client uses ``httpx`` with HTTP/2 enabled and pooled connections.
- Metric snapshots use Prometheus text format via ``MetricsExporter.latest``.
- Log batching relies on a lightweight in-memory handler that buffers records
  harvested from Python's logging subsystem.
- Observability metrics are exported under the ``k1_intelligence`` namespace.

No artificial delays are introduced; ``asyncio.sleep`` is only used to honour
the contract cadences.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Deque, Dict, Iterable, List, Mapping, cast

import httpx
from opentelemetry.trace import SpanKind

from k0.obs.metrics import MetricsExporter
from k0.obs.tracing import TracerFactory
from k1.l5_infrastructure.observability import get_metrics

logger: Any
try:
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)
except ImportError:  # pragma: no cover - structlog optional
    logger = logging.getLogger(__name__)


_metrics = get_metrics()

_push_total = _metrics.counter(
    "observability_push_total",
    "Count of observability payload pushes to K0",
    labelnames=["kind", "status"],
)

_push_latency_ms = _metrics.histogram(
    "observability_push_latency_ms",
    "Latency in milliseconds for observability pushes",
    labelnames=["kind"],
    buckets=[1, 5, 10, 20, 50, 100, 200],
)

_log_queue_size = _metrics.gauge(
    "observability_log_queue_size",
    "Pending structured log records awaiting push",
    labelnames=["queue"],
)


_RESERVED_LOG_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }
)


def _iso_utc(ts: float) -> str:
    """Return an ISO-8601 UTC timestamp for *ts* (seconds since epoch)."""

    return (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )


def _serialise(value: Any) -> Any:
    """Convert *value* to a JSON-serialisable structure."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[Any, Any], value)
        return {str(key): _serialise(val) for key, val in mapping.items()}
    if isinstance(value, (list, tuple, set)):
        iterable = cast(Iterable[Any], value)
        return [_serialise(item) for item in iterable]
    return str(value)


class _LogBufferHandler(logging.Handler):
    """Thread-safe handler that buffers log records for batch export."""

    def __init__(self, *, max_entries: int = 2048) -> None:
        super().__init__(level=logging.NOTSET)
        self._buffer: Deque[Dict[str, Any]] = deque()
        self._lock = Lock()
        self._max_entries = max_entries
        self._formatter = logging.Formatter()

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401 - logging API
        try:
            entry = self._convert(record)
        except Exception:  # pragma: no cover - defensive
            self.handleError(record)
            return
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > self._max_entries:
                self._buffer.popleft()

    def drain(self, limit: int | None = None) -> List[Dict[str, Any]]:
        """Return up to *limit* buffered entries (all if None)."""

        with self._lock:
            if not self._buffer:
                return []
            if limit is None or limit >= len(self._buffer):
                items = list(self._buffer)
                self._buffer.clear()
                return items
            items = [self._buffer.popleft() for _ in range(limit)]
            return items

    def pending(self) -> int:
        """Return the number of buffered log entries."""

        with self._lock:
            return len(self._buffer)

    def _convert(self, record: logging.LogRecord) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "timestamp": _iso_utc(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        trace_id = getattr(record, "cognitive_trace_id", None)
        if trace_id:
            payload["cognitive_trace_id"] = str(trace_id)

        span_id = getattr(record, "otelSpanID", None) or getattr(
            record, "span_id", None
        )
        if span_id:
            payload["span_id"] = str(span_id)

        if record.exc_info:
            payload["exception"] = self._formatter.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        extras: Dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_ATTRS or key in payload:
                continue
            extras[str(key)] = _serialise(value)

        if extras:
            payload["context"] = extras

        return payload


@dataclass(slots=True)
class ObservabilityClientConfig:
    """Configuration for :class:`ObservabilityClient`."""

    endpoint: str
    metrics_interval_sec: float = 10.0
    logs_interval_sec: float = 5.0
    http_timeout_sec: float = 5.0
    max_logs_per_batch: int = 256


class ObservabilityClient:
    """Push K1 observability telemetry to the K0 observability port."""

    def __init__(
        self,
        *,
        config: ObservabilityClientConfig,
        metrics_exporter: MetricsExporter,
        tracer_factory: TracerFactory,
    ) -> None:
        self._config = config
        self._metrics_exporter = metrics_exporter
        self._tracer_factory = tracer_factory
        self._http = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(config.http_timeout_sec),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
        )
        self._url = f"{config.endpoint.rstrip('/')}/k0/obs.emit"
        self._log_handler = _LogBufferHandler()
        self._tasks: list[asyncio.Task[None]] = []
        self._closed = False

        self._attach_log_handler()
        logger.info(
            "observability_client_initialised",
            endpoint=self._url,
            metrics_interval_sec=config.metrics_interval_sec,
            logs_interval_sec=config.logs_interval_sec,
        )

    # ---------------------------------------------------------------------
    # Lifecycle management
    # ---------------------------------------------------------------------
    async def start(self) -> None:
        """Start background tasks for metrics and log forwarding."""

        if self._closed:
            raise RuntimeError("ObservabilityClient has been closed")
        if self._tasks:
            return

        metrics_task = asyncio.create_task(
            self._loop_metrics(), name="observability-metrics-loop"
        )
        logs_task = asyncio.create_task(
            self._loop_logs(), name="observability-logs-loop"
        )
        self._tasks.extend((metrics_task, logs_task))

    async def stop(self) -> None:
        """Stop background tasks and flush remaining telemetry."""

        if not self._tasks:
            return

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        await self.flush_metrics()
        await self.flush_logs()

    async def close(self) -> None:
        """Stop tasks and release network resources."""

        await self.stop()
        if not self._closed:
            await self._http.aclose()
            self._detach_log_handler()
            self._closed = True
            logger.info("observability_client_closed")

    # ------------------------------------------------------------------
    # Public control hooks
    # ------------------------------------------------------------------
    async def flush_metrics(self) -> None:
        """Immediately push a metrics snapshot regardless of cadence."""

        await self._push_metrics()

    async def flush_logs(self) -> None:
        """Immediately push queued structured logs regardless of cadence."""

        await self._push_logs(force=True)

    # ------------------------------------------------------------------
    # Internal loops
    # ------------------------------------------------------------------
    async def _loop_metrics(self) -> None:
        try:
            while True:
                await self._push_metrics()
                await asyncio.sleep(self._config.metrics_interval_sec)
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
            return

    async def _loop_logs(self) -> None:
        try:
            while True:
                await self._push_logs()
                await asyncio.sleep(self._config.logs_interval_sec)
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
            return

    # ------------------------------------------------------------------
    # Push helpers
    # ------------------------------------------------------------------
    async def _push_metrics(self) -> None:
        start = time.perf_counter()
        snapshot_bytes = self._metrics_exporter.latest()
        snapshot = snapshot_bytes.decode("utf-8")
        if not snapshot.strip():
            return

        body = {
            "format": "prometheus_text",
            "captured_at": _iso_utc(time.time()),
            "snapshot": snapshot,
        }
        await self._push("metrics", body, start_time=start)

    async def _push_logs(self, *, force: bool = False) -> None:
        pending = self._log_handler.pending()
        _log_queue_size.labels(queue="structured_logs").set(pending)
        if not pending and not force:
            return

        batch = self._log_handler.drain(self._config.max_logs_per_batch)
        if not batch:
            return

        body: Dict[str, Any] = {
            "captured_at": _iso_utc(time.time()),
            "count": len(batch),
            "entries": batch,
        }
        await self._push("logs", body)
        _log_queue_size.labels(queue="structured_logs").set(self._log_handler.pending())

    async def _push(
        self,
        kind: str,
        body: Mapping[str, Any],
        *,
        start_time: float | None = None,
    ) -> None:
        trace_id = self._tracer_factory.new_trace_id()
        token = self._tracer_factory.attach_cognitive_trace(trace_id)
        status_label = "success"
        push_started = start_time if start_time is not None else time.perf_counter()
        latency_ms = 0.0
        try:
            with self._tracer_factory.span(
                "k1.observability.push",
                kind=SpanKind.CLIENT,
                attributes={"kind": kind},
            ):
                try:
                    headers: Dict[str, str] = {"X-Cognitive-Trace-Id": trace_id}
                    self._tracer_factory.inject(headers)
                    response = await self._http.post(
                        self._url,
                        json={"kind": kind, "body": dict(body)},
                        headers=headers,
                    )
                except httpx.RequestError as exc:
                    status_label = "network_error"
                    logger.error(
                        "observability_push_failed",
                        kind=kind,
                        error=str(exc),
                    )
                    return

                latency_ms = (time.perf_counter() - push_started) * 1000

                if response.status_code in (204, 200):
                    logger.debug(
                        "observability_push_ok",
                        kind=kind,
                        status=response.status_code,
                    )
                    return

                if response.status_code == 501:
                    status_label = "not_implemented"
                    logger.info(
                        "observability_push_not_implemented",
                        kind=kind,
                        status=response.status_code,
                    )
                    return

                status_label = f"http_{response.status_code}"
                logger.warning(
                    "observability_push_http_error",
                    kind=kind,
                    status=response.status_code,
                    body_preview=response.text[:256],
                )
        finally:
            latency_ms = (time.perf_counter() - push_started) * 1000
            _push_total.labels(kind=kind, status=status_label).inc()
            if latency_ms:
                _push_latency_ms.labels(kind=kind).observe(latency_ms)
            self._tracer_factory.detach(token)

    # ------------------------------------------------------------------
    # Logging setup helpers
    # ------------------------------------------------------------------
    def _attach_log_handler(self) -> None:
        root_logger = logging.getLogger()
        if self._log_handler not in root_logger.handlers:
            root_logger.addHandler(self._log_handler)

    def _detach_log_handler(self) -> None:
        root_logger = logging.getLogger()
        if self._log_handler in root_logger.handlers:
            root_logger.removeHandler(self._log_handler)
