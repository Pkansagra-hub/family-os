"""
k1.bus.factory -- Bus factory for production and testing configurations.

Usage::

    # Production (default settings, no timing chain)
    bus = BusFactory.create_local()

    # Production with Rust backend (explicit)
    bus = BusFactory.create_local(backend="rust")

    # Production with Python backend (explicit fallback)
    bus = BusFactory.create_local(backend="python")

    # Production with timing chain (ordering enforcement)
    bus = BusFactory.create_local_ordered()

    # Testing (capture mode -- all envelopes recorded)
    bus = BusFactory.create_for_testing()
    bus.publish(Envelope(topic="k1.test", payload=b"data"))
    assert len(bus.captured) == 1

    # Testing with timing chain
    bus = BusFactory.create_for_testing(ordered=True)

    # Mailbox router with Rust backend
    router = BusFactory.create_mailbox_router(backend="rust")

The factory centralizes bus construction so callers never import
the impl package directly.  kernel.py calls BusFactory and injects
the returned IBus into modules.

Backend selection (V2-M9):
    - ``"auto"`` (default): Use Rust backend if available, Python otherwise.
    - ``"rust"``:  Force Rust backend; raises ImportError if unavailable.
    - ``"python"``: Force Python backend.
"""

from __future__ import annotations

import logging
from typing import Optional, Union

from k1.bus.impl.local_bus import LocalBus
from k1.bus.impl.local_mailbox import LocalMailboxRouter
from k1.bus.middleware import Middleware, MiddlewareChain
from k1.bus.timing.timing_chain import TimingChain
from k1.bus.timing.timing_config import TimingConfig

logger = logging.getLogger(__name__)

# Probe for Rust backend once at import time
try:
    from k1.bus.impl.rust_bus_adapter import RustBusAdapter
    from k1.bus.impl.rust_mailbox_adapter import RustMailboxRouterAdapter

    _RUST_AVAILABLE = True
except ImportError:
    _RUST_AVAILABLE = False
    RustBusAdapter = None  # type: ignore[assignment,misc]
    RustMailboxRouterAdapter = None  # type: ignore[assignment,misc]

# Public type aliases for factory return types
BusType = Union[LocalBus, "RustBusAdapter"]  # type: ignore[type-arg]
MailboxRouterType = Union[LocalMailboxRouter, "RustMailboxRouterAdapter"]  # type: ignore[type-arg]

_VALID_BACKENDS = ("auto", "rust", "python")


def _resolve_backend(backend: str) -> str:
    """Resolve 'auto' to a concrete backend and validate the parameter."""
    if backend not in _VALID_BACKENDS:
        raise ValueError(f"Invalid backend {backend!r}. Must be one of {_VALID_BACKENDS!r}")
    if backend == "auto":
        return "rust" if _RUST_AVAILABLE else "python"
    if backend == "rust" and not _RUST_AVAILABLE:
        raise ImportError(
            "Rust backend requested but k1_bus_core is not installed. "
            "Install with: maturin develop --release "
            "--manifest-path k1/k1_bus_core/Cargo.toml"
        )
    return backend


def _to_chain(
    middleware: list[Middleware] | MiddlewareChain | None,
) -> MiddlewareChain | None:
    """Convert middleware input to a MiddlewareChain or None."""
    if middleware is None:
        return None
    if isinstance(middleware, MiddlewareChain):
        return middleware if middleware.size > 0 else None
    if isinstance(middleware, list):
        return MiddlewareChain(middleware) if middleware else None
    return None


class BusFactory:
    """
    Factory for creating bus instances.

    Why a factory instead of just LocalBus():
        1. Decouples callers from impl (import k1.bus, not k1.bus.impl)
        2. Single place to add middleware, metrics, tracing hooks later
        3. create_for_testing() gives capture mode without test-specific knowledge
        4. create_local_ordered() wires in TimingChain with default config
        5. Future: create_distributed() for multi-node deployment

    V2-M9 additions:
        6. backend= parameter selects Rust or Python impl ("auto"/"rust"/"python")
        7. create_mailbox_router() supports Rust mailbox backend
    """

    @staticmethod
    def create_local(
        *,
        capture: bool = False,
        timing_chain: Optional[TimingChain] = None,
        middleware: list[Middleware] | MiddlewareChain | None = None,
        backend: str = "auto",
    ) -> BusType:
        """
        Create an in-process bus.

        Args:
            capture:       If True, record all published envelopes
                           (accessible via bus.captured).
            timing_chain:  Optional pre-built TimingChain.  Pass this when
                           you need a custom TimingConfig.  Note: TimingChain
                           is only supported with the Python backend; if both
                           timing_chain and backend="rust" are provided,
                           Python backend is used automatically.
            middleware:     Optional middleware chain or list of Middleware.
                           Runs after stamping, before dispatch.
            backend:       "auto" (default) / "rust" / "python".

        Returns:
            A ready-to-use bus instance (LocalBus or RustBusAdapter).
        """
        resolved = _resolve_backend(backend)
        mw_chain = _to_chain(middleware)

        # TimingChain requires Python backend (Rust dispatch lacks native
        # timing-chain integration)
        if timing_chain is not None and resolved == "rust":
            logger.debug("TimingChain requested -- falling back to Python backend")
            resolved = "python"

        if resolved == "rust":
            return RustBusAdapter(
                capture=capture,
                timing_chain=None,
                middleware=mw_chain,
            )

        return LocalBus(
            capture=capture,
            timing_chain=timing_chain,
            middleware=mw_chain,
        )

    @staticmethod
    def create_local_ordered(
        *,
        config: Optional[TimingConfig] = None,
        timeout_ms: int = 5000,
        capture: bool = False,
        middleware: list[Middleware] | MiddlewareChain | None = None,
        backend: str = "python",
    ) -> LocalBus:
        """
        Create a LocalBus with ordering enforcement (TimingChain).

        Uses the default K1 prefix rules if no config is provided.

        Note: TimingChain is a Python-only feature.  backend defaults to
        "python" here.  Passing backend="rust" raises ValueError because
        the Rust dispatch loop does not support timing-chain integration.

        Args:
            config:     Custom TimingConfig, or None for defaults.
            timeout_ms: Safety-net timeout for buffered envelopes.
            capture:    If True, record all published envelopes.
            middleware: Optional middleware chain or list of Middleware.
            backend:    Must be "python" (default).  "rust" raises ValueError.

        Returns:
            LocalBus wired with a TimingChain.
        """
        if backend == "rust":
            raise ValueError(
                "TimingChain (ordered bus) is not supported with Rust backend. "
                "Use backend='python' or backend='auto'."
            )

        if config is None:
            from k1.bus.timing.defaults import default_timing_config

            config = default_timing_config()

        chain = TimingChain(config=config, timeout_ms=timeout_ms)
        mw_chain = _to_chain(middleware)
        return LocalBus(capture=capture, timing_chain=chain, middleware=mw_chain)

    @staticmethod
    def create_for_testing(
        *,
        ordered: bool = False,
        middleware: list[Middleware] | MiddlewareChain | None = None,
        backend: str = "auto",
    ) -> BusType:
        """
        Create a bus configured for testing.

        All published envelopes are recorded in bus.captured.
        Use bus.drain() to retrieve and clear.

        Args:
            ordered:    If True, include a TimingChain with default config
                        for testing ordering behavior.  Forces Python backend.
            middleware: Optional middleware chain or list of Middleware.
            backend:    "auto" (default) / "rust" / "python".

        Returns:
            Bus with capture mode enabled (LocalBus or RustBusAdapter).
        """
        mw_chain = _to_chain(middleware)

        # ordered requires Python (TimingChain)
        if ordered:
            from k1.bus.timing.defaults import default_timing_config

            chain = TimingChain(
                config=default_timing_config(),
                timeout_ms=5000,
            )
            return LocalBus(capture=True, timing_chain=chain, middleware=mw_chain)

        resolved = _resolve_backend(backend)
        if resolved == "rust":
            return RustBusAdapter(
                capture=True,
                timing_chain=None,
                middleware=mw_chain,
            )

        return LocalBus(capture=True, middleware=mw_chain)

    @staticmethod
    def create_mailbox_router(
        *,
        backend: str = "auto",
    ) -> MailboxRouterType:
        """
        Create an in-process mailbox router for point-to-point actor messaging.

        Args:
            backend: "auto" (default) / "rust" / "python".

        Returns:
            A ready-to-use mailbox router (LocalMailboxRouter or
            RustMailboxRouterAdapter).
        """
        resolved = _resolve_backend(backend)
        if resolved == "rust":
            return RustMailboxRouterAdapter()

        return LocalMailboxRouter()
