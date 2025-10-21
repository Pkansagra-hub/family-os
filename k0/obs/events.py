"""Observability event utilities for the K0 kernel."""

from __future__ import annotations

import threading
from typing import Any, Mapping

from .tracing import TracerFactory


class ObservabilityEmitter:
    """Thread-safe sink used to publish observability events.

    The emitter buffers events in-memory so callers (and tests) can inspect
    the payloads. A later milestone can replace the implementation with an
    async transport that forwards events to the dedicated observability port
    without requiring changes to the call sites.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []

    def emit(self, event: Mapping[str, Any]) -> None:
        """Record an observability event.

        Parameters
        ----------
        event:
            Mapping describing the observability payload. A shallow copy is
            stored so further mutation by the caller does not affect the
            buffered state.
        """

        payload = dict(event)
        if "trace_id" not in payload and "cognitive_trace_id" not in payload:
            trace_id = TracerFactory.current_cognitive_trace_id()
            if trace_id:
                payload["trace_id"] = trace_id
        with self._lock:
            self._events.append(payload)

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a copy of the buffered events."""

        with self._lock:
            return [dict(item) for item in self._events]

    def clear(self) -> None:
        """Remove all buffered events."""

        with self._lock:
            self._events.clear()


__all__ = ["ObservabilityEmitter"]
