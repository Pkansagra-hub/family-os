"""Selfmodel tracing — fail-soft OpenTelemetry adapter.

When OTel is installed and a tracer is provided, ``trace_span`` opens a
real span with the given name and trace_id attribute. When OTel is
missing OR the caller passes ``tracer=None``, the helper degrades to a
no-op contextmanager so production code never has to branch.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Optional

__all__ = ["trace_span", "OTEL_AVAILABLE"]

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import guard
    from opentelemetry import trace as _otel_trace  # type: ignore

    OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    _otel_trace = None
    OTEL_AVAILABLE = False


@contextmanager
def trace_span(
    name: str,
    *,
    tracer: Optional[Any] = None,
    trace_id: str = "",
    attributes: Optional[dict[str, Any]] = None,
):
    """Open a span if a tracer is available, otherwise no-op.

    ``trace_id`` is set as the ``cognitive_trace_id`` attribute on the
    span so it correlates with bus envelopes regardless of whether the
    process is running with full OTel propagation configured.
    """
    if tracer is None or not OTEL_AVAILABLE:
        yield None
        return
    try:
        with tracer.start_as_current_span(name) as span:
            if trace_id:
                try:
                    span.set_attribute("cognitive_trace_id", trace_id)
                except Exception:
                    pass
            if attributes:
                for k, v in attributes.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception:
                        pass
            yield span
    except Exception:
        logger.exception("trace_span  failed to open span name=%s", name)
        yield None
