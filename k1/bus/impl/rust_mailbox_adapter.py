"""
k1.bus.impl.rust_mailbox_adapter -- RustMailboxRouter adapter matching LocalMailboxRouter API.

V2-M9-004: Wraps ``k1_bus_core.RustMailboxRouter`` and ``RustMailbox``
to present the same interface as ``LocalMailboxRouter`` and ``LocalMailbox``,
including Envelope <-> RustEnvelope conversion.

Usage::

    from k1.bus.impl.rust_mailbox_adapter import RustMailboxRouterAdapter

    router = RustMailboxRouterAdapter()
    mailbox = router.register("orchestrator")
    router.deliver("orchestrator", envelope)
    env = mailbox.receive(timeout_ms=100)

The adapter is used internally by BusFactory -- callers should use
``BusFactory.create_mailbox_router()`` rather than instantiating directly.
"""

from __future__ import annotations

import logging
from typing import Optional

from k1.bus.envelope import Envelope, Priority
from k1.bus.ports.mailbox import BackpressureError, MailboxConfig, UnknownActorError

logger = logging.getLogger(__name__)

# Conditional import
try:
    import k1_bus_core  # type: ignore[import-untyped]

    _HAS_RUST = True
except ImportError:
    _HAS_RUST = False
    k1_bus_core = None  # type: ignore[assignment]


def _envelope_to_rust(env: Envelope) -> object:
    """Convert Python Envelope to RustEnvelope."""
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


def _rust_to_envelope(renv: object) -> Envelope:
    """Convert RustEnvelope to Python Envelope."""
    return Envelope(
        topic=renv.topic,  # type: ignore[attr-defined]
        priority=Priority(renv.priority),  # type: ignore[attr-defined]
        envelope_id=renv.envelope_id,  # type: ignore[attr-defined]
        sequence=renv.sequence,  # type: ignore[attr-defined]
        cognitive_trace_id=renv.cognitive_trace_id,  # type: ignore[attr-defined]
        session_id=renv.session_id,  # type: ignore[attr-defined]
        request_id=renv.request_id,  # type: ignore[attr-defined]
        parent_id=renv.parent_id,  # type: ignore[attr-defined]
        created_ns=renv.created_ns,  # type: ignore[attr-defined]
        payload=bytes(renv.payload),  # type: ignore[attr-defined]
        ttl_ms=renv.ttl_ms,  # type: ignore[attr-defined]
        payload_format=renv.payload_format,  # type: ignore[attr-defined]
    )


# ---------------------------------------------------------------------------
# RustMailboxAdapter -- wraps RustMailbox
# ---------------------------------------------------------------------------


class RustMailboxAdapter:
    """
    Adapter wrapping ``RustMailbox`` to match ``LocalMailbox`` API surface.

    Translates between Python Envelope and RustEnvelope on receive.
    """

    __slots__ = ("_inner", "_actor_id", "_capacity")

    def __init__(self, inner: object, actor_id: str, capacity: int) -> None:
        self._inner = inner
        self._actor_id = actor_id
        self._capacity = capacity

    def receive(self, timeout_ms: int = 0) -> Envelope | None:
        """
        Receive the next envelope, optionally blocking.

        Args:
            timeout_ms: 0 = non-blocking, >0 = block up to N ms.

        Returns:
            Envelope or None if no envelope available.
        """
        renv = self._inner.receive(timeout_ms)  # type: ignore[attr-defined]
        if renv is None:
            return None
        return _rust_to_envelope(renv)

    def pending(self) -> int:
        """Number of envelopes waiting in the mailbox."""
        return self._inner.pending()  # type: ignore[attr-defined]

    @property
    def capacity(self) -> int:
        """Mailbox capacity."""
        return self._capacity

    @property
    def delivered_count(self) -> int:
        """Total envelopes delivered to this mailbox."""
        return self._inner.delivered_count  # type: ignore[attr-defined]

    @property
    def received_count(self) -> int:
        """Total envelopes received from this mailbox."""
        return self._inner.received_count  # type: ignore[attr-defined]

    def close(self) -> None:
        """Close the mailbox (no new deliveries, drain allowed)."""
        self._inner.close()  # type: ignore[attr-defined]

    @property
    def closed(self) -> bool:
        """True if closed."""
        return self._inner.closed  # type: ignore[attr-defined]

    @property
    def actor_id(self) -> str:
        """Actor ID for this mailbox."""
        return self._actor_id

    def __repr__(self) -> str:
        return (
            f"RustMailboxAdapter(actor={self._actor_id!r}, "
            f"pending={self.pending()}, capacity={self._capacity})"
        )


# ---------------------------------------------------------------------------
# RustMailboxRouterAdapter -- wraps RustMailboxRouter
# ---------------------------------------------------------------------------


class RustMailboxRouterAdapter:
    """
    Adapter wrapping ``RustMailboxRouter`` to match ``LocalMailboxRouter`` API.

    Translates between Python Envelope and RustEnvelope, and maps
    error types to the standard BackpressureError / UnknownActorError.
    """

    __slots__ = ("_router", "_configs")

    def __init__(self) -> None:
        if not _HAS_RUST:
            raise ImportError("k1_bus_core is not available")
        self._router = k1_bus_core.RustMailboxRouter()
        self._configs: dict[str, MailboxConfig] = {}

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        """
        Deliver an envelope to a specific actor's mailbox.

        Raises:
            UnknownActorError:  actor_id not registered.
            BackpressureError:  actor's mailbox is full.
            ValueError:         Router is closed.
        """
        renv = _envelope_to_rust(envelope)
        try:
            self._router.deliver(actor_id, renv)
        except ValueError as e:
            msg = str(e)
            if "Unknown actor" in msg:
                raise UnknownActorError(actor_id) from e
            if "full" in msg.lower() or "backpressure" in msg.lower():
                config = self._configs.get(actor_id, MailboxConfig())
                raise BackpressureError(actor_id, config.capacity) from e
            raise
        except RuntimeError as e:
            msg = str(e)
            if "full" in msg.lower() or "backpressure" in msg.lower():
                config = self._configs.get(actor_id, MailboxConfig())
                raise BackpressureError(actor_id, config.capacity) from e
            raise

    def register(
        self,
        actor_id: str,
        config: Optional[MailboxConfig] = None,
    ) -> RustMailboxAdapter:
        """
        Register an actor and create its mailbox.

        Returns:
            RustMailboxAdapter wrapping the Rust mailbox.
        """
        effective = config or MailboxConfig()
        try:
            rust_mb = self._router.register(
                actor_id,
                capacity=effective.capacity,
                priority_wfq=effective.priority_wfq,
            )
        except ValueError as e:
            raise ValueError(str(e)) from e

        self._configs[actor_id] = effective
        return RustMailboxAdapter(rust_mb, actor_id, effective.capacity)

    def unregister(self, actor_id: str) -> bool:
        """Remove an actor and close its mailbox."""
        self._configs.pop(actor_id, None)
        return self._router.unregister(actor_id)

    def registered_actors(self) -> list[str]:
        """Return the list of currently registered actor IDs."""
        return self._router.registered_actors()

    def close(self) -> None:
        """Close the router and all mailboxes."""
        self._router.close()

    @property
    def closed(self) -> bool:
        """True if the router has been closed."""
        return self._router.closed

    @property
    def is_closed(self) -> bool:
        """Public alias of ``closed`` to satisfy ``IMailboxRouter.is_closed``."""
        return self._router.closed

    @property
    def actor_count(self) -> int:
        """Number of registered actors."""
        return self._router.actor_count

    def mailbox_for(self, actor_id: str) -> RustMailboxAdapter | None:
        """Get the mailbox for an actor (observability/testing)."""
        rust_mb = self._router.mailbox_for(actor_id)
        if rust_mb is None:
            return None
        config = self._configs.get(actor_id, MailboxConfig())
        return RustMailboxAdapter(rust_mb, actor_id, config.capacity)

    def stats_snapshot(self) -> dict[str, dict[str, int]]:
        """Per-actor stats snapshot."""
        raw = self._router.stats_snapshot()
        return {k: dict(v) for k, v in raw.items()}

    def __repr__(self) -> str:
        return f"RustMailboxRouterAdapter(actors={self.actor_count}, " f"closed={self.closed})"
