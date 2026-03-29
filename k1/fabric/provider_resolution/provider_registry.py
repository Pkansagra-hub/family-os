"""
k1.fabric.provider_resolution.provider_registry -- Provider Registry (3.1.1).

Maps provider_id to ProviderConfig. This is a SEPARATE registry from
CapabilityRegistry (2.2.1). CapabilityRegistry maps capability names to
contracts. ProviderRegistry maps provider_id to provider configuration
(endpoint, transport, resource limits, etc.).

Thread Safety:
  All mutations guarded by RLock. Reads are concurrent-safe because
  Python dict reads are atomic at the bytecode level.

Design Decisions:
  - Populated by FabricFactory (5.3.1) at startup
  - ProviderConfig is frozen (immutable) -- updates require unregister + re-register
  - HealthChecker (3.6.1) calls health_check() on each provider periodically
  - Constructor injection for event_port (identical pattern to CapabilityRegistry)

References:
  - fabric_discussion.md Section 9 (Provider Registry internal)
  - Epic 3.1.1 in fabric-implementation-plan.md

Exports:
  ProviderRegistry -- Maps provider_id to ProviderConfig
  ProviderRegistryError -- Base exception
  DuplicateProviderError -- Duplicate provider_id
  ProviderNotFoundError -- provider_id not in registry
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from k1.fabric.types import ProviderConfig, ProviderHealth, ProviderStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event topic constants
# ---------------------------------------------------------------------------

EVENT_PROVIDER_REGISTERED = "k1.fabric.provider.registered.v1"
EVENT_PROVIDER_UNREGISTERED = "k1.fabric.provider.unregistered.v1"
EVENT_PROVIDER_HEALTH_CHANGED = "k1.fabric.provider.health.changed.v1"


# ---------------------------------------------------------------------------
# Event port protocol (duck-typed, same as CapabilityRegistry)
# ---------------------------------------------------------------------------


class EventPort(Protocol):
    """Minimal event bus interface for provider lifecycle events."""

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderRegistryError(Exception):
    """Base exception for provider registry operations."""


class DuplicateProviderError(ProviderRegistryError):
    """Raised when registering a provider_id that already exists."""

    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        super().__init__(f"Provider already registered: {provider_id}")


class ProviderNotFoundError(ProviderRegistryError):
    """Raised when a provider_id is not in the registry."""

    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        super().__init__(f"Provider not found: {provider_id}")


# ---------------------------------------------------------------------------
# 3.1.1 -- ProviderRegistry
# ---------------------------------------------------------------------------


class ProviderRegistry:
    """
    In-memory indexed catalog of provider configurations.

    Maps provider_id to ProviderConfig. Provides lookup, registration,
    unregistration, health tracking, and listing by provider type.

    This is a SEPARATE registry from CapabilityRegistry (2.2.1).
    CapabilityRegistry stores contracts (what capabilities exist).
    ProviderRegistry stores providers (how to reach them).

    Constructor Args:
        event_port: Optional event bus for emitting lifecycle events.
            If None, events are silently skipped.

    Thread Safety:
        All mutations (register_provider, unregister_provider,
        update_health) acquire self._lock (RLock).

    References:
        - fabric_discussion.md Section 9
        - Epic 3.1.1
    """

    __slots__ = (
        "_lock",
        "_event_port",
        "_providers",
        "_by_type",
        "_health_cache",
    )

    def __init__(
        self,
        *,
        event_port: Optional[EventPort] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._event_port = event_port

        # Primary index: provider_id -> ProviderConfig
        self._providers: Dict[str, ProviderConfig] = {}

        # Secondary index: provider_type -> [provider_id]
        self._by_type: Dict[str, List[str]] = {}

        # Health cache: provider_id -> ProviderHealth
        self._health_cache: Dict[str, ProviderHealth] = {}

    # ======================================================================
    # Registration
    # ======================================================================

    def register_provider(
        self,
        provider_id: str,
        config: ProviderConfig,
    ) -> None:
        """
        Register a provider configuration.

        Args:
            provider_id: Unique provider identifier.
            config: Provider configuration (frozen).

        Raises:
            DuplicateProviderError: provider_id already registered.
            ValueError: provider_id is empty.
        """
        if not provider_id:
            raise ValueError("provider_id must not be empty")

        with self._lock:
            if provider_id in self._providers:
                raise DuplicateProviderError(provider_id)

            self._providers[provider_id] = config

            # Secondary index
            ptype = config.provider_type
            if ptype not in self._by_type:
                self._by_type[ptype] = []
            self._by_type[ptype].append(provider_id)

            # Initial health: UNKNOWN
            self._health_cache[provider_id] = ProviderHealth(
                provider_id=provider_id,
                status=ProviderStatus.UNKNOWN.value,
            )

        self._emit(
            EVENT_PROVIDER_REGISTERED,
            {
                "provider_id": provider_id,
                "provider_type": config.provider_type,
                "endpoint": config.endpoint or "",
            },
        )
        logger.debug("Registered provider: %s (%s)", provider_id, config.provider_type)

    def unregister_provider(self, provider_id: str) -> bool:
        """
        Remove a provider from the registry.

        Args:
            provider_id: Provider identifier to remove.

        Returns:
            True if found and removed, False if not found.
        """
        with self._lock:
            config = self._providers.pop(provider_id, None)
            if config is None:
                return False

            # Clean secondary index
            ptype = config.provider_type
            type_list = self._by_type.get(ptype)
            if type_list is not None:
                self._by_type[ptype] = [p for p in type_list if p != provider_id]
                if not self._by_type[ptype]:
                    del self._by_type[ptype]

            # Clean health cache
            self._health_cache.pop(provider_id, None)

        self._emit(EVENT_PROVIDER_UNREGISTERED, {"provider_id": provider_id})
        logger.debug("Unregistered provider: %s", provider_id)
        return True

    # ======================================================================
    # Lookup
    # ======================================================================

    def lookup_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """
        O(1) lookup by provider_id.

        Args:
            provider_id: Provider identifier.

        Returns:
            ProviderConfig if found, None otherwise.
        """
        return self._providers.get(provider_id)

    def contains(self, provider_id: str) -> bool:
        """Check if a provider_id is registered."""
        return provider_id in self._providers

    def list_by_type(self, provider_type: str) -> List[ProviderConfig]:
        """
        Return all provider configs for a given type.

        Args:
            provider_type: Type string (e.g. "MCP", "WASM", "BRIDGE").

        Returns:
            List of ProviderConfig (may be empty).
        """
        ids = self._by_type.get(provider_type, [])
        return [self._providers[pid] for pid in ids if pid in self._providers]

    def list_all(self) -> List[ProviderConfig]:
        """Return all registered provider configs."""
        return list(self._providers.values())

    def list_ids(self) -> List[str]:
        """Return sorted list of all provider_ids."""
        return sorted(self._providers.keys())

    @property
    def size(self) -> int:
        """Number of registered providers."""
        return len(self._providers)

    # ======================================================================
    # Health
    # ======================================================================

    def health_check(self, provider_id: str) -> ProviderHealth:
        """
        Return the cached health status for a provider.

        Health is updated externally by HealthChecker (3.6.1) calling
        update_health(). This method only reads the cache.

        Args:
            provider_id: Provider identifier.

        Returns:
            ProviderHealth snapshot.

        Raises:
            ProviderNotFoundError: provider_id not in registry.
        """
        health = self._health_cache.get(provider_id)
        if health is None:
            raise ProviderNotFoundError(provider_id)
        return health

    def update_health(
        self,
        provider_id: str,
        status: str,
        latency_ms: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """
        Update the health status of a provider.

        Called by HealthChecker (3.6.1) after periodic probe.

        Args:
            provider_id: Provider identifier.
            status: New health status (HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN).
            latency_ms: Observed probe latency.
            error: Optional error message if unhealthy.

        Raises:
            ProviderNotFoundError: provider_id not in registry.
            ValueError: Invalid status value.
        """
        valid_statuses = {s.value for s in ProviderStatus}
        if status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of: {sorted(valid_statuses)}")

        with self._lock:
            if provider_id not in self._providers:
                raise ProviderNotFoundError(provider_id)

            old_health = self._health_cache.get(provider_id)
            old_status = old_health.status if old_health else ProviderStatus.UNKNOWN.value

            new_health = ProviderHealth(
                provider_id=provider_id,
                status=status,
                last_check_at=datetime.now(timezone.utc).isoformat(),
                latency_ms=latency_ms,
                error=error,
            )
            self._health_cache[provider_id] = new_health

        if old_status != status:
            self._emit(
                EVENT_PROVIDER_HEALTH_CHANGED,
                {
                    "provider_id": provider_id,
                    "old_status": old_status,
                    "new_status": status,
                },
            )
        logger.debug("Health updated: %s -> %s", provider_id, status)

    def list_healthy_providers(self) -> List[str]:
        """Return provider_ids with HEALTHY status."""
        return [
            pid
            for pid, health in self._health_cache.items()
            if health.status == ProviderStatus.HEALTHY.value
        ]

    # ======================================================================
    # Event emission
    # ======================================================================

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit an event via the event port, if available."""
        if self._event_port is not None:
            try:
                self._event_port.emit(event_type, payload)
            except Exception:
                logger.warning(
                    "Failed to emit event %s for %s",
                    event_type,
                    payload.get("provider_id", "unknown"),
                    exc_info=True,
                )
