"""
k1.bus.middleware.tracing -- OpenTelemetry tracing middleware.

Creates an OpenTelemetry span for every published envelope, extracting
the span name from the topic and correlating via ``cognitive_trace_id``.

Graceful degradation: if ``opentelemetry`` is not installed, the middleware
becomes a no-op pass-through.  Zero overhead when tracing is disabled.

Span attributes:
    bus.topic              -- Full topic string
    bus.envelope_id        -- Global monotonic envelope ID
    bus.sequence           -- Per-topic sequence number
    bus.priority           -- Priority level (0-3)
    bus.cognitive_trace_id -- Cross-K0/K1 correlation key
    bus.session_id         -- Session scope (if present)
    bus.parent_id          -- Causal parent envelope_id (0 = root)

Usage::

    from k1.bus.middleware.tracing import TracingMiddleware

    # Auto-detects OpenTelemetry availability
    mw = TracingMiddleware()

    # With custom tracer name
    mw = TracingMiddleware(tracer_name="k1.bus.custom")

    # Force disabled (testing)
    mw = TracingMiddleware(enabled=False)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from k1.bus.envelope import Envelope

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional OpenTelemetry import (graceful degradation)
# ---------------------------------------------------------------------------

_tracer_api: Any = None
_HAS_OTEL = False

try:
    from opentelemetry import trace as _trace_module

    _tracer_api = _trace_module
    _HAS_OTEL = True
except ImportError:
    pass


class TracingMiddleware:
    """
    OpenTelemetry tracing middleware for the K1 bus.

    Creates a span per published envelope using the topic as span name
    and ``cognitive_trace_id`` as a span attribute for cross-system
    correlation.

    When OpenTelemetry is not installed or tracing is explicitly disabled,
    ``process()`` returns the envelope unchanged with zero overhead.

    Thread-safe: uses the OpenTelemetry tracer which is inherently thread-safe.
    """

    __slots__ = ("_tracer", "_enabled")

    def __init__(
        self,
        *,
        tracer_name: str = "k1.bus",
        enabled: bool = True,
    ) -> None:
        """
        Create a TracingMiddleware.

        Args:
            tracer_name: OpenTelemetry tracer instrument name.
            enabled:     If False, tracing is completely disabled regardless
                         of whether OpenTelemetry is installed.
        """
        self._enabled = enabled and _HAS_OTEL
        self._tracer: Any = None

        if self._enabled and _tracer_api is not None:
            self._tracer = _tracer_api.get_tracer(tracer_name)

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        """
        Create an OTel span for the envelope and return it unchanged.

        Never drops envelopes (always returns the envelope).
        Never reads payload.

        Args:
            envelope: Stamped bus envelope.

        Returns:
            The same envelope, unchanged.
        """
        if not self._enabled or self._tracer is None:
            return envelope

        # Create a span named after the topic
        span = self._tracer.start_span(
            name=f"bus.publish {envelope.topic}",
            attributes={
                "bus.topic": envelope.topic,
                "bus.envelope_id": envelope.envelope_id,
                "bus.sequence": envelope.sequence,
                "bus.priority": envelope.priority,
                "bus.parent_id": envelope.parent_id,
            },
        )

        # Add trace correlation attributes if present
        if envelope.cognitive_trace_id:
            span.set_attribute("bus.cognitive_trace_id", envelope.cognitive_trace_id)
        if envelope.session_id:
            span.set_attribute("bus.session_id", envelope.session_id)

        # End span immediately -- we're tracing the publish event, not
        # the handler execution.  Handler tracing is a separate concern.
        span.end()

        return envelope

    @property
    def enabled(self) -> bool:
        """True if tracing is active (OTel installed and not disabled)."""
        return self._enabled

    def __repr__(self) -> str:
        state = "enabled" if self._enabled else "disabled"
        return f"TracingMiddleware({state})"


__all__ = ["TracingMiddleware"]
