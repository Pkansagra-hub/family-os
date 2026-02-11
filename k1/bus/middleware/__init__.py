"""
k1.bus.middleware -- Middleware layer for the K1 bus.

Middleware intercepts envelopes AFTER bus stamping (envelope_id, sequence,
created_ns) but BEFORE trie matching and handler dispatch.  This is the
observability and validation layer.

Design rules:
    1. Middleware sees envelope HEADER only -- NEVER reads payload.
    2. ``process()`` returns the (possibly modified) envelope, or None to drop.
    3. Middleware chain runs in order: tracing -> metrics -> topic_validation.
    4. All middleware must be fail-safe -- exceptions are caught by LocalBus.
    5. Individual middlewares degrade gracefully when optional dependencies
       (opentelemetry, prometheus_client) are not installed.

Usage::

    from k1.bus.middleware import Middleware, MiddlewareChain
    from k1.bus.middleware.tracing import TracingMiddleware
    from k1.bus.middleware.metrics import MetricsMiddleware

    chain = MiddlewareChain([TracingMiddleware(), MetricsMiddleware()])
    result = chain.process(envelope)  # None means dropped

Exports:
    Middleware       -- Protocol defining the middleware contract
    MiddlewareChain  -- Ordered pipeline of Middleware instances
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from k1.bus.envelope import Envelope


@runtime_checkable
class Middleware(Protocol):
    """
    Contract for bus middleware.

    Each middleware receives a stamped envelope (envelope_id, sequence,
    created_ns already assigned) and returns:
        - The same or modified Envelope to continue the chain
        - None to DROP the envelope (it will not be dispatched)

    Middleware MUST NOT:
        - Read or modify ``envelope.payload``
        - Block for I/O (tracing/metrics must be non-blocking)
        - Raise exceptions (LocalBus catches them, but it's bad form)

    Thread-safety: middleware instances must be safe for concurrent use
    from multiple publish threads.
    """

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        """
        Process an envelope through this middleware.

        Args:
            envelope: Stamped envelope (bus fields already assigned).

        Returns:
            Envelope to continue the chain, or None to drop.
        """
        ...


class MiddlewareChain:
    """
    Ordered pipeline of Middleware instances.

    Runs each middleware in sequence.  If any middleware returns None,
    the envelope is dropped and subsequent middlewares are skipped.

    Thread-safe: delegates to individual middleware instances which
    must themselves be thread-safe.
    """

    __slots__ = ("_middlewares",)

    def __init__(self, middlewares: list[Middleware] | None = None) -> None:
        self._middlewares: list[Middleware] = list(middlewares) if middlewares else []

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        """
        Run the envelope through all middlewares in order.

        Returns:
            Final envelope after all middlewares, or None if any dropped it.
        """
        current: Optional[Envelope] = envelope
        for mw in self._middlewares:
            if current is None:
                return None
            current = mw.process(current)
        return current

    def append(self, middleware: Middleware) -> None:
        """Add a middleware to the end of the chain."""
        self._middlewares.append(middleware)

    def prepend(self, middleware: Middleware) -> None:
        """Add a middleware to the beginning of the chain."""
        self._middlewares.insert(0, middleware)

    @property
    def size(self) -> int:
        """Number of middlewares in the chain."""
        return len(self._middlewares)

    def __len__(self) -> int:
        return len(self._middlewares)

    def __repr__(self) -> str:
        names = [type(mw).__name__ for mw in self._middlewares]
        return f"MiddlewareChain({' -> '.join(names) or 'empty'})"


__all__ = [
    "Middleware",
    "MiddlewareChain",
]
