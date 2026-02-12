"""
k1.orchestrator.connectors.mcp_registrar -- MCP Registration Bridge (5.1.2).

Thin bridge between MCP Tool Discovery (5.1.1) and the Capability Fabric.
Translates discovered tools into Fabric registration events.

The Registrar does NOT:
  - Create provider instances (Fabric owns that via ProviderFactory 3.1.4).
  - Set up circuit breakers (Fabric owns that via CircuitBreaker 3.4.1).
  - Do health monitoring (Fabric owns that via HealthChecker 3.6.1).
  - Validate output (Fabric owns that via OutputValidationPipeline 3.5.1).
  - Store provider instances.

The Registrar DOES:
  - Build capability_id from DiscoveredTool per SPEC-7 naming convention.
  - Check for collisions via ``fabric.query_registry(capability_id)``.
  - Emit ``k1.mcp.tool.discovered.v1`` per tool for Fabric to register.
  - Track registration counts (registered, skipped, errors).

Event flow:
  Registrar emits ``k1.mcp.tool.discovered.v1`` (TOPIC_MCP_TOOL_DISCOVERED)
  -> Fabric's ProactiveGapDetector (5.4.4) receives the event
  -> Calls ``module_loader.register_from_dict()`` (2.3.4)
  -> CapabilityContract created and indexed in CapabilityRegistry

Constructor:
  MCPRegistrationBridge(fabric, delta)

References:
  - Issue 5.1.2 in orchestrator-implementation-plan.md
  - SPEC-7 (server_id prefix prevents naming collisions)
  - Fabric events: TOPIC_MCP_TOOL_DISCOVERED in fabric_events.py

Exports:
  MCPRegistrationBridge
  RegistrationResult
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, List

from k1.orchestrator.connectors.mcp_discovery import DiscoveredTool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event topic -- matches Fabric's consumed topic (fabric_events.py)
# ---------------------------------------------------------------------------

_TOPIC_MCP_TOOL_DISCOVERED = "k1.mcp.tool.discovered.v1"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistrationResult:
    """
    Aggregate result of ``register_tools()``.

    Attributes:
        registered: Number of tools for which events were emitted.
        skipped: Number of tools skipped (already in Fabric registry).
        errors: List of error messages from failed registrations.
    """

    registered: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool type inference
# ---------------------------------------------------------------------------

_READ_PREFIXES = ("query", "search", "list", "get", "find", "fetch", "read", "lookup")
_WRITE_PREFIXES = ("create", "update", "delete", "remove", "set", "put", "post", "patch")


def infer_type(tool: DiscoveredTool) -> str:
    """
    Infer tool type from tool name pattern.

    Returns ``"read"`` for query-like names, ``"execute"`` for write-like
    names, and ``"execute"`` as default.

    Examples:
        ``get_weather``     -> ``"read"``
        ``search_contacts`` -> ``"read"``
        ``create_event``    -> ``"execute"``
        ``run_analysis``    -> ``"execute"`` (default)
    """
    name_lower = tool.name.lower()
    for prefix in _READ_PREFIXES:
        if name_lower.startswith(prefix):
            return "read"
    for prefix in _WRITE_PREFIXES:
        if name_lower.startswith(prefix):
            return "execute"
    return "execute"


def build_capability_id(tool: DiscoveredTool) -> str:
    """
    Build the canonical capability name for a discovered tool.

    Format: ``tool.{type}.{server_id}.{name}``
    (per SPEC-7: server_id prefix prevents naming collisions).

    Examples:
        ``tool.execute.google_cal.create_event``
        ``tool.read.weather_api.get_forecast``
    """
    tool_type = infer_type(tool)
    return f"tool.{tool_type}.{tool.server_id}.{tool.name}"


# ---------------------------------------------------------------------------
# 5.1.2 -- MCPRegistrationBridge
# ---------------------------------------------------------------------------


class MCPRegistrationBridge:
    """
    Thin bridge from MCP Tool Discovery to Fabric registration.

    For each discovered tool:
      1. Build capability_id per SPEC-7 naming convention.
      2. Check Fabric registry via ``fabric.query_registry()`` for collision.
      3. If not registered: emit ``k1.mcp.tool.discovered.v1`` event.
      4. Track registered / skipped / error counts.

    Fabric's ProactiveGapDetector (5.4.4) subscribes to
    ``k1.mcp.tool.discovered.v1`` and calls ``register_from_dict()``
    to create the actual CapabilityContract.

    Constructor Args:
        fabric: IFabricGatewayPort for collision detection.
        delta: IDeltaEmitPort for event emission.

    Thread Safety:
        Stateless per call -- safe for concurrent use.
    """

    __slots__ = ("_fabric", "_delta")

    def __init__(self, fabric: Any, delta: Any) -> None:
        """
        Args:
            fabric: IFabricGatewayPort -- for query_registry() collision check.
            delta: IDeltaEmitPort -- for emitting tool discovered events.
        """
        self._fabric = fabric
        self._delta = delta

    # ==================================================================
    # Public API
    # ==================================================================

    async def register_tools(
        self,
        tools: List[DiscoveredTool],
    ) -> RegistrationResult:
        """
        Register discovered MCP tools with Fabric.

        For each tool:
          1. Build capability_id.
          2. Check collision via ``fabric.query_registry()``.
          3. Emit ``k1.mcp.tool.discovered.v1`` for Fabric to register.

        On collision: skip (keep existing), log warning.
        On error: log warning, continue to next tool.

        Args:
            tools: List of DiscoveredTool from MCPToolDiscovery.

        Returns:
            RegistrationResult with counts of registered, skipped, errors.
        """
        registered = 0
        skipped = 0
        errors: List[str] = []

        for tool in tools:
            try:
                capability_id = build_capability_id(tool)

                # Check collision
                existing = await self._fabric.query_registry(capability_id)
                if existing is not None:
                    logger.debug(
                        "Skipping already-registered capability: %s",
                        capability_id,
                    )
                    skipped += 1
                    continue

                # Emit tool discovered event for Fabric to register
                trace_id = str(uuid.uuid4())
                await self._delta.emit(
                    _TOPIC_MCP_TOOL_DISCOVERED,
                    {
                        "tool_name": tool.name,
                        "tool_description": tool.description,
                        "input_schema": tool.input_schema,
                        "output_schema": tool.output_schema or {},
                        "server_id": tool.server_id,
                        "server_name": tool.server_id,
                        "capability_id": capability_id,
                    },
                    trace_id,
                )
                registered += 1

                logger.debug(
                    "Emitted tool discovered event: %s (server=%s)",
                    capability_id,
                    tool.server_id,
                )

            except Exception as exc:
                msg = f"Registration failed for tool '{tool.name}' (server={tool.server_id}): {exc}"
                errors.append(msg)
                logger.warning(msg)

        return RegistrationResult(
            registered=registered,
            skipped=skipped,
            errors=errors,
        )

    async def unregister_tools(
        self,
        capability_ids: List[str],
    ) -> int:
        """
        Emit unregister events for a list of capability_ids.

        Used by ConnectorLifecycleManager.refresh() to remove
        stale capabilities before re-discovery.

        Args:
            capability_ids: List of capability names to unregister.

        Returns:
            Number of unregister events emitted.
        """
        count = 0
        for cap_id in capability_ids:
            try:
                trace_id = str(uuid.uuid4())
                await self._delta.emit(
                    "k1.orchestration.mcp.tool_unregistered.v1",
                    {
                        "capability_id": cap_id,
                        "reason": "refresh",
                    },
                    trace_id,
                )
                count += 1
            except Exception as exc:
                logger.warning(
                    "Failed to emit unregister for '%s': %s",
                    cap_id,
                    exc,
                )
        return count
