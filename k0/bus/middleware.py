"""Built-in middleware utilities for bus dispatch."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Callable, Iterable

from opentelemetry.trace import SpanKind

from k0.obs.logging import bind_log_context, reset_log_context
from k0.obs.metrics import MetricsExporter
from k0.obs.tracing import TracerFactory

from .core import BusDispatchContext, BusMiddleware, BusMiddlewareHandler


def timestamp_middleware(
    *,
    clock: Callable[[], datetime] | None = None,
) -> BusMiddleware:
    """Record wall-clock and monotonic timestamps for each dispatch."""

    clock_fn = clock or (lambda: datetime.now(timezone.utc))

    async def _middleware(
        context: BusDispatchContext,
        handler: BusMiddlewareHandler,
    ) -> None:
        context.started_at = clock_fn()
        start_tick = perf_counter()
        context.monotonic_start = start_tick
        try:
            await handler(context)
        finally:
            context.completed_at = clock_fn()
            end_tick = perf_counter()
            context.monotonic_end = end_tick
            duration = context.duration_seconds or (end_tick - start_tick)
            context.duration_seconds = max(0.0, duration)

    return _middleware


def latency_metrics_middleware(
    metrics: MetricsExporter,
    *,
    buckets: Iterable[float] | None = None,
) -> BusMiddleware:
    """Emit dispatch latency samples and counters using the provided metrics exporter."""

    async def _middleware(
        context: BusDispatchContext,
        handler: BusMiddlewareHandler,
    ) -> None:
        start_tick = perf_counter()
        outcome = "success"
        try:
            await handler(context)
        except Exception:
            outcome = "failure"
            raise
        finally:
            end_tick = perf_counter()
            duration = end_tick - start_tick
            if context.monotonic_start is None:
                context.monotonic_start = start_tick
            if context.monotonic_end is None:
                context.monotonic_end = end_tick
            duration_value = context.duration_seconds or duration
            duration_value = max(0.0, duration_value)
            context.duration_seconds = duration_value

            # Histogram for latency (matches dashboard query expectations)
            metrics.observe(
                "bus_dispatch_latency_seconds",
                duration_value,
                labels={"topic": context.message.topic, "outcome": outcome},
                buckets=buckets,
            )

            # Counter for total dispatches
            metrics.emit(
                "bus_dispatch_total",
                value=1.0,
                outcome=outcome,
                topic=context.message.topic,
            )

            # Counter for failures only
            if outcome == "failure":
                metrics.emit(
                    "bus_dispatch_failures_total",
                    value=1.0,
                    topic=context.message.topic,
                )

    return _middleware


def tracing_middleware(
    *,
    tracer_factory: TracerFactory,
    span_name: str = "bus.dispatch",
    span_kind: SpanKind = SpanKind.CONSUMER,
) -> BusMiddleware:
    """Propagate cognitive trace identifiers and emit spans for bus dispatch."""

    async def _middleware(
        context: BusDispatchContext,
        handler: BusMiddlewareHandler,
    ) -> None:
        trace_id = (
            context.trace_id
            or context.message.trace_id
            or tracer_factory.new_trace_id()
        )
        context.trace_id = trace_id
        token = tracer_factory.attach_cognitive_trace(trace_id)
        log_token = bind_log_context(
            cognitive_trace_id=trace_id,
            bus_topic=context.message.topic,
            bus_offset=context.message.offset,
            bus_band=context.band,
            bus_port=context.port,
        )
        attributes: dict[str, object] = {
            "k0.bus.topic": context.message.topic,
            "k0.bus.offset": context.message.offset,
            "k0.bus.band": context.band,
            "k0.bus.port": context.port,
        }
        if context.message.trace_id is None:
            attributes["k0.bus.generated_trace"] = True

        try:
            with tracer_factory.span(
                span_name,
                kind=span_kind,
                attributes=attributes,
            ):
                await handler(context)
        finally:
            reset_log_context(log_token)
            tracer_factory.detach(token)

    return _middleware


__all__ = [
    "latency_metrics_middleware",
    "timestamp_middleware",
    "tracing_middleware",
]
