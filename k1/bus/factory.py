"""
k1.bus.factory -- Bus factory for production and testing configurations.

Usage::

    # Production (default settings, no timing chain)
    bus = BusFactory.create_local()

    # Production with timing chain (ordering enforcement)
    bus = BusFactory.create_local_ordered()

    # Testing (capture mode -- all envelopes recorded)
    bus = BusFactory.create_for_testing()
    bus.publish(Envelope(topic="k1.test", payload=b"data"))
    assert len(bus.captured) == 1

    # Testing with timing chain
    bus = BusFactory.create_for_testing(ordered=True)

The factory centralizes LocalBus construction so callers never import
the impl package directly.  kernel.py calls BusFactory and injects
the returned IBus into modules.
"""

from __future__ import annotations

from typing import Optional

from k1.bus.impl.local_bus import LocalBus
from k1.bus.impl.local_mailbox import LocalMailboxRouter
from k1.bus.middleware import Middleware, MiddlewareChain
from k1.bus.timing.timing_chain import TimingChain
from k1.bus.timing.timing_config import TimingConfig


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
    """

    @staticmethod
    def create_local(
        *,
        capture: bool = False,
        timing_chain: Optional[TimingChain] = None,
        middleware: list[Middleware] | MiddlewareChain | None = None,
    ) -> LocalBus:
        """
        Create an in-process LocalBus.

        Args:
            capture:       If True, record all published envelopes
                           (accessible via bus.captured).
            timing_chain:  Optional pre-built TimingChain.  Pass this when
                           you need a custom TimingConfig.
            middleware:     Optional middleware chain or list of Middleware.
                           Runs after stamping, before dispatch.

        Returns:
            A ready-to-use LocalBus instance.
        """
        mw_chain = _to_chain(middleware)
        return LocalBus(capture=capture, timing_chain=timing_chain, middleware=mw_chain)

    @staticmethod
    def create_local_ordered(
        *,
        config: Optional[TimingConfig] = None,
        timeout_ms: int = 5000,
        capture: bool = False,
        middleware: list[Middleware] | MiddlewareChain | None = None,
    ) -> LocalBus:
        """
        Create a LocalBus with ordering enforcement (TimingChain).

        Uses the default K1 prefix rules if no config is provided.

        Args:
            config:     Custom TimingConfig, or None for defaults.
            timeout_ms: Safety-net timeout for buffered envelopes.
            capture:    If True, record all published envelopes.
            middleware: Optional middleware chain or list of Middleware.

        Returns:
            LocalBus wired with a TimingChain.
        """
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
    ) -> LocalBus:
        """
        Create a LocalBus configured for testing.

        All published envelopes are recorded in bus.captured.
        Use bus.drain() to retrieve and clear.

        Args:
            ordered:    If True, include a TimingChain with default config
                        for testing ordering behavior.
            middleware: Optional middleware chain or list of Middleware.

        Returns:
            LocalBus with capture mode enabled.
        """
        mw_chain = _to_chain(middleware)
        if ordered:
            from k1.bus.timing.defaults import default_timing_config

            chain = TimingChain(
                config=default_timing_config(),
                timeout_ms=5000,
            )
            return LocalBus(capture=True, timing_chain=chain, middleware=mw_chain)

        return LocalBus(capture=True, middleware=mw_chain)

    @staticmethod
    def create_mailbox_router() -> LocalMailboxRouter:
        """
        Create an in-process mailbox router for point-to-point actor messaging.

        Returns:
            A ready-to-use LocalMailboxRouter instance.
        """
        return LocalMailboxRouter()
