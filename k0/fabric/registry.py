"""
Capability Registry - Maps capability names to providers.

This module provides the core registry for capability-based lookups,
enabling modules and pipelines to discover providers by capability name
rather than concrete implementation.

Part of the Capability Mesh Architecture (ADR-K004).
Layer 2: CapabilityFabric

Related:
- k0/runtime/schemas.py: CapabilityProvider, ProviderType
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from k0.runtime.schemas import CapabilityProvider

logger = logging.getLogger(__name__)


class ResolutionStrategy(str, Enum):
    """How to resolve multiple providers for a capability."""

    FIRST = "first"  # First matching provider
    PRIORITY = "priority"  # Highest priority matching (default)
    ROUND_ROBIN = "round_robin"  # Distribute across providers


@dataclass
class RegisteredProvider:
    """
    A provider registered for a capability.

    Tracks the provider configuration, optional handler function,
    and runtime metrics for observability.
    """

    capability: str
    provider: "CapabilityProvider"
    handler: Callable[..., Any] | None = None  # Resolved handler function

    # Runtime metrics
    call_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0

    @property
    def provider_id(self) -> str:
        """Get the provider identifier (module_id or pipeline_id)."""
        return self.provider.module_id or self.provider.pipeline_id or "unknown"

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency across all calls."""
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count


@dataclass
class CapabilityRegistry:
    """
    Registry for capability-based lookups.

    Thread-safe registry that maps capability names to ordered
    lists of providers. Supports hot-reload of providers without
    restart.

    Example:
        registry = CapabilityRegistry()
        registry.register("score_salience", provider, handler_fn)

        registered = registry.resolve("score_salience")
        if registered and registered.handler:
            result = registered.handler(**kwargs)
    """

    _providers: dict[str, list[RegisteredProvider]] = field(default_factory=dict)
    _round_robin_index: dict[str, int] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def register(
        self,
        capability: str,
        provider: "CapabilityProvider",
        handler: Callable[..., Any] | None = None,
    ) -> None:
        """
        Register a provider for a capability.

        Providers are sorted by priority (lower = higher priority).
        Multiple providers can be registered for the same capability
        for failover or load balancing.

        Args:
            capability: Capability name (e.g., "score_salience")
            provider: Provider configuration from schema
            handler: Resolved handler function (optional, can bind later)
        """
        with self._lock:
            if capability not in self._providers:
                self._providers[capability] = []
                self._round_robin_index[capability] = 0

            registered = RegisteredProvider(
                capability=capability,
                provider=provider,
                handler=handler,
            )

            # Insert sorted by priority (lower = higher priority)
            providers = self._providers[capability]
            insert_idx = len(providers)  # Default: append at end

            for i, p in enumerate(providers):
                if provider.priority < p.provider.priority:
                    insert_idx = i
                    break

            providers.insert(insert_idx, registered)

            provider_id = provider.module_id or provider.pipeline_id
            logger.info(
                "Registered provider for %s: %s (priority=%d)",
                capability,
                provider_id,
                provider.priority,
            )

    def unregister(self, capability: str, provider_id: str) -> bool:
        """
        Unregister a provider from a capability.

        Args:
            capability: Capability name
            provider_id: Module ID or pipeline ID to unregister

        Returns:
            True if provider was found and removed
        """
        with self._lock:
            if capability not in self._providers:
                return False

            providers = self._providers[capability]
            for i, p in enumerate(providers):
                pid = p.provider.module_id or p.provider.pipeline_id
                if pid == provider_id:
                    providers.pop(i)
                    logger.info(
                        "Unregistered provider for %s: %s",
                        capability,
                        provider_id,
                    )
                    return True

            return False

    def resolve(
        self,
        capability: str,
        strategy: ResolutionStrategy = ResolutionStrategy.PRIORITY,
    ) -> RegisteredProvider | None:
        """
        Resolve a capability to a provider.

        Args:
            capability: Capability name to resolve
            strategy: Resolution strategy (PRIORITY, FIRST, ROUND_ROBIN)

        Returns:
            RegisteredProvider or None if not found
        """
        with self._lock:
            providers = self._providers.get(capability, [])
            if not providers:
                return None

            if strategy == ResolutionStrategy.FIRST:
                return providers[0]

            if strategy == ResolutionStrategy.PRIORITY:
                # Already sorted by priority, return first
                return providers[0]

            if strategy == ResolutionStrategy.ROUND_ROBIN:
                idx = self._round_robin_index.get(capability, 0)
                provider = providers[idx % len(providers)]
                self._round_robin_index[capability] = (idx + 1) % len(providers)
                return provider

            # Default fallback
            return providers[0]

    def list_capabilities(self) -> list[str]:
        """List all registered capability names."""
        with self._lock:
            return list(self._providers.keys())

    def list_providers(self, capability: str) -> list[RegisteredProvider]:
        """List all providers for a capability."""
        with self._lock:
            return list(self._providers.get(capability, []))

    def has_capability(self, capability: str) -> bool:
        """Check if a capability is registered."""
        with self._lock:
            return capability in self._providers and len(self._providers[capability]) > 0

    def bind_handler(
        self,
        capability: str,
        provider_id: str,
        handler: Callable[..., Any],
    ) -> bool:
        """
        Bind a handler function to a registered provider.

        Used for late-binding when handlers aren't available at registration.

        Args:
            capability: Capability name
            provider_id: Module ID or pipeline ID
            handler: Handler function to bind

        Returns:
            True if provider found and handler bound
        """
        with self._lock:
            providers = self._providers.get(capability, [])
            for p in providers:
                pid = p.provider.module_id or p.provider.pipeline_id
                if pid == provider_id:
                    p.handler = handler
                    logger.debug(
                        "Bound handler for %s: %s",
                        capability,
                        provider_id,
                    )
                    return True
            return False

    def record_call(
        self,
        capability: str,
        provider_id: str,
        latency_ms: float,
        error: bool = False,
        status: str | None = None,
        caller_id: str | None = None,
        trace_id: str | None = None,
        strategy: str | None = None,
    ) -> None:
        """
        Record metrics for a capability call.

        Args:
            capability: Capability that was invoked
            provider_id: Provider that handled the call
            latency_ms: Call latency in milliseconds
            error: Whether the call resulted in an error
            status: Response status (success/error/timeout) - for richer metrics
            caller_id: Caller module/pipeline ID - for richer metrics
            trace_id: Distributed trace ID - for linking
            strategy: Resolution strategy used - for analytics
        """
        with self._lock:
            providers = self._providers.get(capability, [])
            for p in providers:
                pid = p.provider.module_id or p.provider.pipeline_id
                if pid == provider_id:
                    p.call_count += 1
                    p.total_latency_ms += latency_ms
                    if error:
                        p.error_count += 1
                    break

        # Log rich metrics for observability systems (structured logging)
        if trace_id or caller_id:
            logger.debug(
                "Capability call recorded: %s via %s [status=%s, latency=%.2fms, caller=%s, trace=%s, strategy=%s]",
                capability,
                provider_id,
                status or ("error" if error else "success"),
                latency_ms,
                caller_id,
                trace_id,
                strategy,
            )

    def get_stats(self) -> dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with registry stats
        """
        with self._lock:
            total_providers = sum(len(p) for p in self._providers.values())
            total_calls = sum(
                p.call_count for providers in self._providers.values() for p in providers
            )
            total_errors = sum(
                p.error_count for providers in self._providers.values() for p in providers
            )

            return {
                "capabilities_count": len(self._providers),
                "providers_count": total_providers,
                "total_calls": total_calls,
                "total_errors": total_errors,
                "capabilities": list(self._providers.keys()),
            }

    def clear(self) -> None:
        """Clear all registered providers."""
        with self._lock:
            self._providers.clear()
            self._round_robin_index.clear()
            logger.info("Capability registry cleared")

    # -------------------------------------------------------------------------
    # Async-safe methods for asyncio contexts
    # -------------------------------------------------------------------------

    async def register_async(
        self,
        capability: str,
        provider: "CapabilityProvider",
        handler: Callable[..., Any] | None = None,
    ) -> None:
        """
        Thread-safe async registration.

        Wraps synchronous register() to run in executor,
        preventing asyncio event loop blocking.

        Args:
            capability: Capability name
            provider: Provider configuration
            handler: Handler function (optional)
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self.register(capability, provider, handler),
        )

    def resolve_safe(
        self,
        capability: str,
        strategy: ResolutionStrategy = ResolutionStrategy.PRIORITY,
    ) -> RegisteredProvider | None:
        """
        Thread-safe resolution that returns a copy.

        Returns a copy of the provider to prevent mutation
        during iteration in async contexts.

        Args:
            capability: Capability name to resolve
            strategy: Resolution strategy

        Returns:
            Copy of RegisteredProvider or None
        """
        with self._lock:
            providers = list(self._providers.get(capability, []))
            if not providers:
                return None

            if strategy == ResolutionStrategy.FIRST:
                return providers[0]

            if strategy == ResolutionStrategy.PRIORITY:
                return providers[0]

            if strategy == ResolutionStrategy.ROUND_ROBIN:
                idx = self._round_robin_index.get(capability, 0)
                provider = providers[idx % len(providers)]
                self._round_robin_index[capability] = (idx + 1) % len(providers)
                return provider

            return providers[0]

    async def record_call_async(
        self,
        capability: str,
        provider_id: str,
        latency_ms: float,
        error: bool = False,
    ) -> None:
        """
        Thread-safe async metrics recording.

        Wraps synchronous record_call() to run in executor,
        preventing asyncio event loop blocking.

        Args:
            capability: Capability that was invoked
            provider_id: Provider that handled the call
            latency_ms: Call latency in milliseconds
            error: Whether the call resulted in an error
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self.record_call(capability, provider_id, latency_ms, error),
        )


# -----------------------------------------------------------------------------
# Global Registry Singleton
# -----------------------------------------------------------------------------

_capability_registry: Optional[CapabilityRegistry] = None
_registry_lock = threading.Lock()


def get_capability_registry() -> CapabilityRegistry:
    """
    Get the global capability registry singleton.

    Returns:
        CapabilityRegistry instance
    """
    global _capability_registry
    if _capability_registry is None:
        with _registry_lock:
            # Double-check after acquiring lock
            if _capability_registry is None:
                _capability_registry = CapabilityRegistry()
    return _capability_registry


def reset_capability_registry() -> None:
    """
    Reset the global registry (for testing).

    This clears the singleton instance, allowing a fresh
    registry to be created on next access.
    """
    global _capability_registry
    with _registry_lock:
        if _capability_registry is not None:
            _capability_registry.clear()
        _capability_registry = None
        logger.debug("Capability registry reset")
