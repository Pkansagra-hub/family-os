"""
k1.bus.impl.rust_bus_adapter -- RustBus adapter matching LocalBus API surface.

V2-M9-001/002/003: Wraps ``k1_bus_core.RustBus`` to present the same
interface as ``LocalBus`` so that all existing adapters (FabricBusAdapter,
SessionBusAdapter) and consumers work without modification.

Conversions:
    - Envelope <-> RustEnvelope (on publish, on handler receive)
    - SubscriptionHandle <-> str subscription_id
    - BusStats dataclass <-> dict stats
    - captured list[Envelope] <-> list[RustEnvelope]

Usage::

    from k1.bus.impl.rust_bus_adapter import RustBusAdapter

    bus = RustBusAdapter(capture=True)
    bus.publish(Envelope(topic="k1.test", payload=b"data"))
    assert len(bus.captured) == 1

The adapter is used internally by BusFactory -- callers should use the
factory rather than instantiating this directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from k1.bus.envelope import Envelope, Priority
from k1.bus.impl.local_bus import BusStats
from k1.bus.ports.bus import BusHandler, SubscriptionHandle

if TYPE_CHECKING:
    from k1.bus.middleware import MiddlewareChain
    from k1.bus.timing.timing_chain import TimingChain

logger = logging.getLogger(__name__)

# Conditional import -- this module should only be loaded when Rust is available,
# but we guard anyway for safety.
try:
    import k1_bus_core  # type: ignore[import-untyped]

    _HAS_RUST = True
except ImportError:
    _HAS_RUST = False
    k1_bus_core = None  # type: ignore[assignment]


def _envelope_to_rust(env: Envelope) -> Any:
    """Convert a Python Envelope to a RustEnvelope."""
    return k1_bus_core.RustEnvelope(
        topic=env.topic,
        priority=(env.priority.value if isinstance(env.priority, Priority) else env.priority),
        envelope_id=env.envelope_id,
        sequence=env.sequence,
        cognitive_trace_id=env.cognitive_trace_id,
        session_id=env.session_id,
        request_id=env.request_id,
        parent_id=env.parent_id,
        created_ns=env.created_ns,
        payload=env.payload,
        ttl_ms=env.ttl_ms,
        payload_format=(
            env.payload_format.value if hasattr(env.payload_format, "value") else env.payload_format
        ),
    )


def _rust_to_envelope(renv: Any) -> Envelope:
    """Convert a RustEnvelope to a Python Envelope."""
    return Envelope(
        topic=renv.topic,
        priority=Priority(renv.priority),
        envelope_id=renv.envelope_id,
        sequence=renv.sequence,
        cognitive_trace_id=renv.cognitive_trace_id,
        session_id=renv.session_id,
        request_id=renv.request_id,
        parent_id=renv.parent_id,
        created_ns=renv.created_ns,
        payload=bytes(renv.payload),
        ttl_ms=renv.ttl_ms,
        payload_format=renv.payload_format,
    )


class RustBusAdapter:
    """
    Adapter wrapping ``k1_bus_core.RustBus`` to match the ``LocalBus`` API surface.

    Implements the same public interface as ``LocalBus``:
      - ``publish(Envelope)``
      - ``subscribe(pattern, handler) -> SubscriptionHandle``
      - ``unsubscribe(handle) -> bool``
      - ``close()``, ``closed``, ``stats``, ``captured``, ``drain()``
      - ``sweep()``, ``subscription_count``, ``topic_sequence()``
      - ``last_envelope_id``, ``timing_chain``, ``middleware``

    This allows FabricBusAdapter, SessionBusAdapter, and all IBus consumers
    to work identically with either Python or Rust backend.
    """

    __slots__ = (
        "_bus",
        "_capture",
        "_sub_patterns",
        "_timing_chain",
        "_middleware",
        "_drain_offset",
    )

    def __init__(
        self,
        *,
        capture: bool = False,
        timing_chain: TimingChain | None = None,
        middleware: MiddlewareChain | None = None,
    ) -> None:
        """
        Create a RustBusAdapter.

        Args:
            capture:       If True, enable capture mode on the Rust bus.
            timing_chain:  Optional TimingChain. Stored for ``.timing_chain``
                           accessor parity with ``LocalBus``. Rust backend uses
                           its own internal ``RustTimingConfig`` for ordering;
                           the Python TimingChain is **not** invoked here
                           because Rust stamps envelopes inside ``publish()``
                           and TimingChain requires pre-stamped envelopes.
                           See ``ARCHITECTURE.md`` for the rationale.
            middleware:    Optional MiddlewareChain. P6.2 (I-19): now wired
                           into ``publish()``. Middleware sees the unstamped
                           envelope (Rust stamps internally); a returned
                           ``None`` drops the envelope before it reaches Rust,
                           matching ``LocalBus`` semantics for headers-only
                           middleware (Tracing, Metrics, TopicValidation).
        """
        if not _HAS_RUST:
            raise ImportError("k1_bus_core is not available")
        self._bus = k1_bus_core.RustBus(capture=capture)
        self._capture = capture
        self._sub_patterns: dict[str, str] = {}
        self._timing_chain = timing_chain
        self._middleware = middleware
        # P6.3 (finding A): track how many captured envelopes have already
        # been returned by ``drain()`` so subsequent drains return only
        # newly-published envelopes (matching ``LocalBus.drain()`` semantics).
        self._drain_offset: int = 0

    # ------------------------------------------------------------------
    # IBus.publish
    # ------------------------------------------------------------------

    def publish(self, envelope: Envelope) -> None:
        """Publish Envelope, converting to RustEnvelope internally.

        P6.2 (I-19): runs the configured ``MiddlewareChain`` before handing
        the envelope to Rust so observability hooks (Tracing, Metrics,
        TopicValidation) fire identically across backends. A middleware
        returning ``None`` drops the envelope and Rust never sees it.
        Middleware exceptions are logged and the envelope is dropped,
        matching ``LocalBus`` behaviour.
        """
        # P6.2: run middleware chain before Rust dispatch.
        # Note: envelope is *unstamped* here (Rust stamps inside publish()).
        # Header-only middlewares (Tracing/Metrics/TopicValidation) do not
        # depend on bus-stamped fields, so this is safe.
        if self._middleware is not None:
            try:
                result = self._middleware.process(envelope)
            except Exception:
                logger.exception(
                    "Middleware chain error for topic=%s -- envelope dropped",
                    envelope.topic,
                )
                return
            if result is None:
                return
            envelope = result

        renv = _envelope_to_rust(envelope)
        try:
            self._bus.publish(renv)
        except RuntimeError:
            # Closed bus -- match LocalBus behavior (silently drop)
            return
        except ValueError:
            # Invalid topic -- match LocalBus behavior (silently drop)
            return

    def publish_batch(self, envelopes: list[Envelope]) -> None:
        """Publish a batch of envelopes (M7.2 / B06).

        Rust core does not currently expose a native batch publish, so
        this loops through ``publish``.  Per-envelope semantics
        (middleware, Rust stamping, dispatch) are unchanged.
        """
        for envelope in envelopes:
            self.publish(envelope)

    # ------------------------------------------------------------------
    # IBus.subscribe
    # ------------------------------------------------------------------

    def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle:
        """Subscribe, wrapping handler to convert RustEnvelope -> Envelope."""

        def _adapted_handler(renv: Any) -> None:
            env = _rust_to_envelope(renv)
            handler(env)

        sub_id = self._bus.subscribe(pattern, _adapted_handler)
        self._sub_patterns[sub_id] = pattern
        return SubscriptionHandle(subscription_id=sub_id, pattern=pattern)

    # ------------------------------------------------------------------
    # IBus.unsubscribe
    # ------------------------------------------------------------------

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Unsubscribe by subscription_id."""
        self._sub_patterns.pop(handle.subscription_id, None)
        return self._bus.unsubscribe(handle.subscription_id)

    # ------------------------------------------------------------------
    # Testing helpers
    # ------------------------------------------------------------------

    @property
    def captured(self) -> list[Envelope]:
        """Captured envelopes since the last :meth:`drain` (capture mode only).

        P6.3 (finding A): semantics aligned with ``LocalBus.captured`` —
        envelopes returned by a previous ``drain()`` call are excluded.
        """
        all_captured = self._bus.captured
        if self._drain_offset:
            all_captured = all_captured[self._drain_offset :]
        return [_rust_to_envelope(r) for r in all_captured]

    def drain(self) -> list[Envelope]:
        """Return captured envelopes since last drain and reset the cursor.

        P6.3 (finding A): matches ``LocalBus.drain()`` — each call returns
        only envelopes captured since the previous drain. The Rust crate's
        underlying capture buffer cannot be cleared from Python, so we
        track a Python-side offset (``_drain_offset``) instead.
        """
        all_captured = self._bus.captured
        result = [_rust_to_envelope(r) for r in all_captured[self._drain_offset :]]
        self._drain_offset = len(all_captured)
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def sweep(self) -> int:
        """
        No-op: Rust bus handles sweep internally via SweepTimer.

        Returns 0 (no Python-side releases).
        """
        return 0

    def flush(self, timeout_ms: int = 5000) -> bool:
        """
        Phase 6 / P6.5.  No-op for the Rust backend.

        The Rust bus dispatches synchronously on the publisher's thread
        (no per-subscription mailboxes), so by the time ``publish()``
        returns, every handler has already been invoked.  Returns True
        immediately.
        """
        return True

    def close(self) -> None:
        """Close the bus."""
        self._bus.close()

    @property
    def closed(self) -> bool:
        """True if the bus has been closed."""
        return self._bus.is_closed

    @property
    def is_closed(self) -> bool:
        """Public alias of ``closed`` to satisfy ``IBus.is_closed``."""
        return self._bus.is_closed

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def stats(self) -> BusStats:
        """Convert RustBus stats dict to BusStats dataclass."""
        s = self._bus.stats
        bs = BusStats()
        bs.envelopes_published = s["envelopes_published"]
        bs.envelopes_delivered = s["envelopes_delivered"]
        bs.handler_errors = s["handler_errors"]
        bs.subscriptions_active = s["subscriptions_active"]
        bs.subscriptions_total = s["subscriptions_total"]
        bs.unsubscribe_count = s["unsubscribe_count"]
        bs.topics_seen = s["topics_seen"]
        return bs

    @property
    def subscription_count(self) -> int:
        """Number of active subscriptions."""
        return self._bus.subscription_count

    def topic_sequence(self, topic: str) -> int:
        """Current sequence for a topic (0 if never published)."""
        return self._bus.topic_sequence(topic)

    @property
    def last_envelope_id(self) -> int:
        """Last assigned global envelope ID."""
        return self._bus.last_envelope_id

    @property
    def timing_chain(self) -> TimingChain | None:
        """Access the timing chain (None if not configured)."""
        return self._timing_chain

    @property
    def middleware(self) -> MiddlewareChain | None:
        """Access the middleware chain (None if not configured)."""
        return self._middleware

    # ------------------------------------------------------------------
    # Circuit breaker (M8 passthrough)
    # ------------------------------------------------------------------

    def handler_circuits(self) -> dict[str, str]:
        """Per-handler circuit breaker states: {pattern: state_str}."""
        return dict(self._bus.handler_circuits())

    def reset_circuit(self, pattern: str) -> bool:
        """Reset a circuit breaker by handler pattern."""
        return self._bus.reset_circuit(pattern)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        tc = ", timing=ON" if self._timing_chain else ""
        mw = f", middleware={len(self._middleware)}" if self._middleware else ""
        return (
            f"RustBusAdapter(subscriptions={self.subscription_count}, "
            f"published={self.stats.envelopes_published}, "
            f"capture={self._capture}{tc}{mw})"
        )
