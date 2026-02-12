"""
k1.orchestrator.connectors.connector_lifecycle -- ConnectorLifecycleManager (5.1.3).

The ONLY Orchestrator entry point for MCP connector operations.
Orchestrates discovery, registration, lifecycle monitoring, refresh,
and teardown for MCP tool connectors.

What this class owns:
  - Coordinating MCPToolDiscovery (5.1.1) and MCPRegistrationBridge (5.1.2).
  - Tracking which capability_ids belong to which server_id.
  - Subscribing to Fabric health events and triggering re-discovery
    on provider recovery.
  - Refresh (unregister stale + re-discover + re-register) per server.
  - Unregister all capabilities for a server.

What this class does NOT own (Fabric owns these):
  - Provider instances / ProviderFactory.
  - Circuit breaker state / HealthChecker.
  - Availability tracking / output validation.
  - Health check scheduling.

State:
  server_capabilities: dict[str, list[str]]
    Maps server_id -> list of registered capability_ids.
    Used for refresh (unregister old, re-register new) and
    teardown (unregister all for a server).

Constructor:
  ConnectorLifecycleManager(discovery, registrar, events, delta)

References:
  - Issue 5.1.3 in orchestrator-implementation-plan.md
  - Fabric event: k1.fabric.provider.health.changed.v1
  - ProviderHealthChangedEvent (fabric_events.py)

Exports:
  ConnectorLifecycleManager
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from k1.orchestrator.connectors.mcp_discovery import DiscoveredTool, MCPToolDiscovery
from k1.orchestrator.connectors.mcp_registrar import (
    MCPRegistrationBridge,
    RegistrationResult,
    build_capability_id,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fabric topic consumed by lifecycle monitoring
# ---------------------------------------------------------------------------

_TOPIC_PROVIDER_HEALTH_CHANGED = "k1.fabric.provider.health.changed.v1"


# ---------------------------------------------------------------------------
# 5.1.3 -- ConnectorLifecycleManager
# ---------------------------------------------------------------------------


class ConnectorLifecycleManager:
    """
    Single entry point for MCP connector operations.

    Orchestrates:
      1. ``discover_and_register()`` -- full discovery + registration cycle.
      2. ``start_lifecycle_monitoring()`` -- subscribe to Fabric health
         events for automatic re-discovery on provider recovery.
      3. ``refresh(server_id)`` -- unregister stale + re-discover + re-register.
      4. ``unregister_server(server_id)`` -- remove all capabilities for server.

    Constructor Args:
        discovery: MCPToolDiscovery instance for tool enumeration.
        registrar: MCPRegistrationBridge instance for Fabric registration.
        events: IEventSubscriptionPort for subscribing to health events.
        delta: IDeltaEmitPort for emitting lifecycle events.

    Thread Safety:
        NOT thread-safe -- ``server_capabilities`` is not guarded.
        Orchestrator runs single-threaded per asyncio event loop.
    """

    __slots__ = (
        "_discovery",
        "_registrar",
        "_events",
        "_delta",
        "server_capabilities",
        "_health_handle",
        "_pending_refresh",
    )

    def __init__(
        self,
        discovery: MCPToolDiscovery,
        registrar: MCPRegistrationBridge,
        events: Any,  # IEventSubscriptionPort
        delta: Any,  # IDeltaEmitPort
    ) -> None:
        self._discovery = discovery
        self._registrar = registrar
        self._events = events
        self._delta = delta

        # server_id -> list of registered capability_ids
        self.server_capabilities: Dict[str, List[str]] = {}

        # Handle for health event subscription (for cleanup)
        self._health_handle: Optional[Any] = None

        # Pending refresh requests from health event handler
        self._pending_refresh: List[str] = []

    # ==================================================================
    # Public API
    # ==================================================================

    async def discover_and_register(self) -> RegistrationResult:
        """
        Full discovery + registration cycle.

        Steps:
          1. ``discovery.discover_all()`` -- enumerate tools from all servers.
          2. ``registrar.register_tools(tools)`` -- emit events to Fabric.
          3. Update ``server_capabilities`` mapping with new capability_ids.

        Returns:
            RegistrationResult with registered / skipped / error counts.
        """
        discovery_result = await self._discovery.discover_all()

        if not discovery_result.tools:
            logger.info(
                "No tools discovered (servers_ok=%d, servers_failed=%d)",
                discovery_result.servers_ok,
                discovery_result.servers_failed,
            )
            errors = list(discovery_result.errors) if discovery_result.errors else []
            return RegistrationResult(registered=0, skipped=0, errors=errors)

        result = await self._registrar.register_tools(discovery_result.tools)

        # Update server_capabilities mapping
        self._update_server_mapping(discovery_result.tools)

        logger.info(
            "Discovery+registration complete: registered=%d, skipped=%d, errors=%d",
            result.registered,
            result.skipped,
            len(result.errors),
        )
        return result

    def start_lifecycle_monitoring(self) -> None:
        """
        Subscribe to Fabric provider health events.

        Listens to ``k1.fabric.provider.health.changed.v1``.
        On provider recovery (state transition to ``"HEALTHY"``
        for an MCP-type provider whose server_id is known):
        triggers ``refresh(server_id)`` to re-discover tools
        (server may have new/removed tools after recovery).

        Idempotent: calling twice re-subscribes (old handle is
        unsubscribed first).
        """
        if self._health_handle is not None:
            self._events.unsubscribe(self._health_handle)

        self._health_handle = self._events.subscribe(
            _TOPIC_PROVIDER_HEALTH_CHANGED,
            self._on_provider_health_changed,
        )
        logger.info("Lifecycle monitoring started (health event subscription active)")

    def stop_lifecycle_monitoring(self) -> None:
        """
        Unsubscribe from Fabric provider health events.

        Idempotent: safe to call if not currently subscribed.
        """
        if self._health_handle is not None:
            self._events.unsubscribe(self._health_handle)
            self._health_handle = None
            logger.info("Lifecycle monitoring stopped")

    async def refresh(self, server_id: str) -> RegistrationResult:
        """
        Refresh tools for a specific server.

        Steps:
          1. Unregister old capabilities for this server.
          2. Re-discover tools from the server.
          3. Re-register discovered tools.
          4. Update server_capabilities mapping.

        Active workflows using removed tools fail at ConstraintResolver
        -> ProactiveGap.

        Args:
            server_id: The MCP server to refresh.

        Returns:
            RegistrationResult from the re-registration step.
        """
        # Step 1: unregister old capabilities
        old_cap_ids = self.server_capabilities.get(server_id, [])
        if old_cap_ids:
            unregistered = await self._registrar.unregister_tools(old_cap_ids)
            logger.debug(
                "Unregistered %d old capabilities for server '%s'",
                unregistered,
                server_id,
            )

        # Remove from mapping before re-discovery
        self.server_capabilities.pop(server_id, None)

        # Step 2: re-discover tools for this server
        server_config = self._find_server_config(server_id)
        if server_config is None:
            logger.warning(
                "Cannot refresh server '%s': not found in config",
                server_id,
            )
            return RegistrationResult(
                errors=[f"Server '{server_id}' not found in config"],
            )

        try:
            tools = await self._discovery.discover_server(server_config)
        except Exception as exc:
            msg = f"Re-discovery failed for server '{server_id}': {exc}"
            logger.warning(msg)
            return RegistrationResult(errors=[msg])

        # Step 3: re-register
        if not tools:
            logger.info(
                "No tools found during refresh for server '%s'",
                server_id,
            )
            return RegistrationResult()

        result = await self._registrar.register_tools(tools)

        # Step 4: update mapping
        self._update_server_mapping(tools)

        logger.info(
            "Refresh complete for server '%s': registered=%d, skipped=%d",
            server_id,
            result.registered,
            result.skipped,
        )
        return result

    async def unregister_server(self, server_id: str) -> int:
        """
        Remove all registered capabilities for a server.

        Emits unregister events via the registrar and removes the
        server from the capabilities mapping.

        Args:
            server_id: The MCP server to unregister.

        Returns:
            Number of capabilities unregistered.
        """
        cap_ids = self.server_capabilities.pop(server_id, [])
        if not cap_ids:
            logger.debug("No capabilities to unregister for server '%s'", server_id)
            return 0

        count = await self._registrar.unregister_tools(cap_ids)
        logger.info(
            "Unregistered %d capabilities for server '%s'",
            count,
            server_id,
        )
        return count

    def get_server_ids(self) -> List[str]:
        """Return list of known server IDs with registered capabilities."""
        return list(self.server_capabilities.keys())

    def get_capabilities(self, server_id: str) -> List[str]:
        """Return registered capability_ids for a server (empty if unknown)."""
        return list(self.server_capabilities.get(server_id, []))

    # ==================================================================
    # Internal
    # ==================================================================

    def _update_server_mapping(self, tools: List[DiscoveredTool]) -> None:
        """
        Update server_capabilities mapping from a list of discovered tools.

        Adds capability_ids for each tool, grouped by server_id.
        """
        for tool in tools:
            cap_id = build_capability_id(tool)
            server_tools = self.server_capabilities.setdefault(tool.server_id, [])
            if cap_id not in server_tools:
                server_tools.append(cap_id)

    def _find_server_config(self, server_id: str) -> Any:
        """
        Find MCPServerConfig for a server_id by re-reading config.

        Returns None if server not found or config cannot be read.
        """
        try:
            configs = self._discovery.load_config()
        except (FileNotFoundError, ValueError) as exc:
            logger.warning("Cannot load config for refresh: %s", exc)
            return None

        for cfg in configs:
            if cfg.id == server_id:
                return cfg
        return None

    def _on_provider_health_changed(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Handle ``k1.fabric.provider.health.changed.v1`` events.

        On provider recovery (status transition to HEALTHY for a
        known MCP server): schedules a refresh for that server.

        The handler is synchronous (per IEventSubscriptionPort contract).
        It schedules the async refresh via a fire-and-forget pattern.
        """
        provider_id = payload.get("provider_id", "")
        new_state = payload.get("new_state", "")
        old_state = payload.get("old_state", "")

        # Only react to recovery transitions -> HEALTHY
        if new_state != "HEALTHY":
            return

        # Only react if the old state was degraded/unhealthy
        if old_state not in ("DEGRADED", "UNHEALTHY"):
            return

        # Check if provider_id matches a known server_id
        # Provider IDs from Fabric may not exactly match server_ids,
        # so we check if any known server_id is a substring or match.
        target_server_id = self._resolve_server_id(provider_id)
        if target_server_id is None:
            logger.debug(
                "Health recovery for provider '%s' -- not a known MCP server",
                provider_id,
            )
            return

        logger.info(
            "Provider '%s' recovered (%s -> %s), scheduling refresh for server '%s'",
            provider_id,
            old_state,
            new_state,
            target_server_id,
        )

        # Schedule async refresh.  The handler is sync, so we
        # record the pending refresh for the orchestrator loop to pick up.
        # In the actual runtime, OrchestratorService would call
        # refresh() in its event loop.  We store the intent here.
        self._pending_refresh.append(target_server_id)

    def _resolve_server_id(self, provider_id: str) -> Optional[str]:
        """
        Map a Fabric provider_id to a known server_id.

        Returns the server_id if found, None otherwise.
        Matching strategies:
          1. Exact match: provider_id == server_id
          2. Suffix match: provider_id ends with server_id
             (Fabric may prefix with ``mcp.`` etc.)
        """
        for server_id in self.server_capabilities:
            if server_id == provider_id:
                return server_id
            if provider_id.endswith(f".{server_id}"):
                return server_id
            if provider_id.endswith(f"_{server_id}"):
                return server_id
        return None

    def get_pending_refreshes(self) -> List[str]:
        """
        Return and clear pending refresh requests from health events.

        Called by the Orchestrator event loop to execute async
        refreshes that were triggered by sync health event handlers.

        Returns:
            List of server_ids that need refresh.
        """
        pending = getattr(self, "_pending_refresh", [])
        self._pending_refresh = []
        return list(pending)
