"""
k1.fabric.provider_resolution.provider_factory -- Provider Factory (3.1.4).

Given a ProviderConfig, instantiates the appropriate provider handler.
Uses a handler registry pattern: handler constructors are registered per
ProviderType at startup by FabricFactory (5.3.1).

Design:
  - The factory does NOT know about concrete provider classes at import time.
    MCPProvider, WASMProvider, BridgeProvider, AgentProvider, WorkflowProvider,
    ConciergeProvider are registered externally during bootstrap.
  - This avoids circular imports and keeps the resolution subsystem
    independent of Epic 3.3 (Execution Runtime).
  - Each handler constructor receives (ProviderConfig, **port_deps) and
    returns an object implementing the CapabilityProvider protocol.
  - Thread-safe: handler registry is populated at startup (single-threaded),
    then read-only during runtime.

References:
  - fabric_discussion.md Section 9 (Resolution Pipeline, step 5)
  - fabric_discussion.md Section 11 (CapabilityProvider protocol)
  - Epic 3.1.4 in fabric-implementation-plan.md

Exports:
  ProviderFactory -- Instantiates provider handlers from ProviderConfig
  ProviderFactoryError -- Base exception
  UnsupportedProviderTypeError -- No handler for provider_type
  ProviderInstantiationError -- Handler constructor failed
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from k1.fabric.providers.base_provider import CapabilityProvider
from k1.fabric.types import ProviderConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CapabilityProvider protocol (from fabric_discussion.md Section 11)
#
# Canonical location: k1/fabric/providers/base_provider.py (3.3.1).
# Re-imported here for backward compatibility and ProviderFactory typing.
# ---------------------------------------------------------------------------


# Type alias for handler constructors.
# A handler constructor takes a ProviderConfig and optional keyword
# dependencies (port injections) and returns a CapabilityProvider.
HandlerConstructor = Callable[..., CapabilityProvider]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderFactoryError(Exception):
    """Base exception for provider factory operations."""


class UnsupportedProviderTypeError(ProviderFactoryError):
    """Raised when no handler is registered for a provider_type."""

    def __init__(self, provider_type: str):
        self.provider_type = provider_type
        super().__init__(f"No handler registered for provider type: {provider_type}")


class ProviderInstantiationError(ProviderFactoryError):
    """Raised when a handler constructor fails."""

    def __init__(self, provider_id: str, provider_type: str, cause: Exception):
        self.provider_id = provider_id
        self.provider_type = provider_type
        self.cause = cause
        super().__init__(
            f"Failed to instantiate provider '{provider_id}' " f"(type={provider_type}): {cause}"
        )


# ---------------------------------------------------------------------------
# 3.1.4 -- ProviderFactory
# ---------------------------------------------------------------------------


class ProviderFactory:
    """
    Factory for instantiating CapabilityProvider handlers from ProviderConfig.

    Handler constructors are registered per ProviderType. During bootstrap,
    FabricFactory (5.3.1) calls register_handler() for each provider type.
    During resolution, Resolver (3.1.5) calls create() to instantiate the
    appropriate handler for a resolved provider.

    Constructor Args:
        port_deps: Optional keyword dependencies injected into every
            handler constructor (e.g., bridge_port, model_gateway_port).
            Handlers that don't need them simply ignore extra kwargs.

    Thread Safety:
        Handler registry is populated at startup (single-threaded).
        create() is read-only and safe for concurrent calls.

    References:
        - fabric_discussion.md Section 9 (step 5)
        - Epic 3.1.4
    """

    __slots__ = ("_handlers", "_port_deps")

    def __init__(self, **port_deps: Any) -> None:
        # provider_type string -> handler constructor
        self._handlers: Dict[str, HandlerConstructor] = {}
        # Keyword dependencies passed to every handler constructor
        self._port_deps: Dict[str, Any] = port_deps

    # ======================================================================
    # Handler Registration (startup phase)
    # ======================================================================

    def register_handler(
        self,
        provider_type: str,
        constructor: HandlerConstructor,
    ) -> None:
        """
        Register a handler constructor for a provider type.

        Called by FabricFactory (5.3.1) during bootstrap to wire
        concrete provider classes.

        Args:
            provider_type: ProviderType value (e.g., "MCP", "WASM").
            constructor: Callable that takes (ProviderConfig, **deps)
                and returns a CapabilityProvider.

        Raises:
            ValueError: provider_type is empty.
        """
        if not provider_type:
            raise ValueError("provider_type must not be empty")
        self._handlers[provider_type] = constructor
        logger.debug("Registered handler for provider type: %s", provider_type)

    def has_handler(self, provider_type: str) -> bool:
        """Check if a handler is registered for provider_type."""
        return provider_type in self._handlers

    def registered_types(self) -> List[str]:
        """Return sorted list of registered provider types."""
        return sorted(self._handlers.keys())

    # ======================================================================
    # Provider Instantiation (runtime phase)
    # ======================================================================

    def create(self, config: ProviderConfig) -> CapabilityProvider:
        """
        Instantiate a provider handler from ProviderConfig.

        Looks up the handler constructor by config.provider_type,
        then calls it with the config and port dependencies.

        Args:
            config: Provider configuration specifying type, endpoint, etc.

        Returns:
            A CapabilityProvider instance ready for execution.

        Raises:
            UnsupportedProviderTypeError: No handler for this type.
            ProviderInstantiationError: Handler constructor failed.
        """
        ptype = config.provider_type
        constructor = self._handlers.get(ptype)
        if constructor is None:
            raise UnsupportedProviderTypeError(ptype)

        try:
            provider = constructor(config, **self._port_deps)
        except Exception as exc:
            raise ProviderInstantiationError(
                provider_id=config.provider_id,
                provider_type=ptype,
                cause=exc,
            ) from exc

        logger.debug("Created provider: %s (type=%s)", config.provider_id, ptype)
        return provider
