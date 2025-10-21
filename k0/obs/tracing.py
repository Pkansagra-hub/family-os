"""Tracing utilities built on OpenTelemetry."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

from opentelemetry import baggage, context, propagate, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Tracer

__all__ = [
    "COGNITIVE_TRACE_BAGGAGE_KEY",
    "TracerFactory",
]


LOGGER = logging.getLogger(__name__)
COGNITIVE_TRACE_BAGGAGE_KEY = "cognitive_trace_id"

_PROVIDER_LOCK = threading.Lock()


@dataclass(frozen=True)
class _ProviderSignature:
    service_name: str
    service_version: str
    environment: str
    otlp_endpoint: str | None
    sample_ratio: float


def _configure_provider(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    otlp_endpoint: str | None,
    otlp_headers: Mapping[str, str] | None,
    sample_ratio: float,
) -> TracerProvider:
    """Configure (or reuse) a global tracer provider."""

    signature = _ProviderSignature(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        otlp_endpoint=otlp_endpoint,
        sample_ratio=sample_ratio,
    )

    with _PROVIDER_LOCK:
        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider) and getattr(
            provider, "_k0_configured", False
        ):
            previous = getattr(provider, "_k0_signature", signature)
            if previous == signature:
                return provider

            try:
                provider.shutdown()
            except Exception:  # pragma: no cover - best-effort shutdown
                LOGGER.exception("Failed to shut down existing tracer provider")

        resource = Resource(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": environment,
            }
        )

        sampler = ParentBased(TraceIdRatioBased(sample_ratio))
        provider = TracerProvider(
            resource=resource,
            sampler=sampler,
            id_generator=RandomIdGenerator(),
        )

        if otlp_endpoint:
            try:
                exporter = OTLPSpanExporter(
                    endpoint=otlp_endpoint,
                    headers=dict(otlp_headers or {}),
                )
                provider.add_span_processor(BatchSpanProcessor(exporter))
                LOGGER.info(
                    "Configured OTLP span exporter for endpoint %s", otlp_endpoint
                )
            except Exception:  # pragma: no cover - defensive fallback
                LOGGER.exception(
                    "Failed to initialise OTLP exporter at %s; falling back to console exporter",
                    otlp_endpoint,
                )
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        else:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        provider._k0_configured = True  # type: ignore[attr-defined]
        provider._k0_signature = signature  # type: ignore[attr-defined]

        trace.set_tracer_provider(provider)
        return provider


class TracerFactory:
    """Factory exposing helpers around the global OpenTelemetry tracer."""

    def __init__(
        self,
        *,
        service_name: str,
        service_version: str,
        environment: str,
        otlp_endpoint: str | None = None,
        otlp_headers: Mapping[str, str] | None = None,
        sample_ratio: float = 1.0,
    ) -> None:
        if not 0.0 <= sample_ratio <= 1.0:
            msg = "sample_ratio must be between 0.0 and 1.0"
            raise ValueError(msg)

        _configure_provider(
            service_name=service_name,
            service_version=service_version,
            environment=environment,
            otlp_endpoint=otlp_endpoint,
            otlp_headers=otlp_headers,
            sample_ratio=sample_ratio,
        )

        self._service_name = service_name
        self._service_version = service_version
        self._environment = environment
        self._tracer: Tracer = trace.get_tracer(service_name, service_version)

    def get_tracer(self) -> Tracer:
        """Return the underlying OpenTelemetry tracer."""

        return self._tracer

    def span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Mapping[str, Any] | None = None,
        context_override: Context | None = None,
    ):
        """Start a span as a context manager."""

        return self._tracer.start_as_current_span(
            name,
            kind=kind,
            attributes=dict(attributes or {}),
            context=context_override,
        )

    def new_trace_id(self) -> str:
        """Return a freshly generated cognitive trace identifier."""
        return uuid.uuid4().hex

    def attach_cognitive_trace(self, trace_id: str) -> object:
        """Attach the cognitive trace identifier to the current context."""

        baggage_ctx = baggage.set_baggage(COGNITIVE_TRACE_BAGGAGE_KEY, trace_id)
        return context.attach(baggage_ctx)

    @staticmethod
    def detach(token: Any) -> None:
        """Detach a previously attached context token."""

        context.detach(token)

    @staticmethod
    def current_cognitive_trace_id() -> str | None:
        """Fetch the cognitive trace identifier from the current context, if any."""

        value = baggage.get_baggage(COGNITIVE_TRACE_BAGGAGE_KEY)
        if value is None:
            return None
        return str(value)

    @staticmethod
    def extract(headers: Mapping[str, str]):
        """Extract a context from HTTP headers."""

        return propagate.extract(headers)

    @staticmethod
    def inject(headers: MutableMapping[str, str]) -> None:
        """Inject the current context into HTTP headers."""

        propagate.inject(headers)
