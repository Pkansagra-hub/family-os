"""
k1.fabric.events.event_emitter -- EventEmitter wrapper (5.4.2).

Wraps IEventPort with Fabric-specific event emission methods.
Enforces cognitive_trace_id on every event (FAB-09).

All Fabric subsystems emit events through EventEmitter, never directly
through IEventPort.  This ensures consistent event structure, trace
propagation, and topic naming.

Event Topics Emitted (13 total):
  k1.capability.invoked.v1                    -- Before execution starts
  k1.capability.completed.v1                  -- After successful execution
  k1.capability.failed.v1                     -- After failed execution
  k1.fabric.learning.signal.v1                -- After every result (K0 P09)
  k1.fabric.capability.registered.v1          -- On capability registration
  k1.fabric.capability.unregistered.v1        -- On capability unregistration
  k1.fabric.capability.version.conflict.v1    -- On version conflict
  k1.fabric.contract.validation.failed.v1     -- On contract validation failure
  k1.fabric.output.validation.failed.v1       -- On output validation failure
  k1.fabric.provider.health.changed.v1        -- On provider health change
  k1.fabric.capability.contract_updated.v1    -- On contract update
  k1.fabric.pressure.warning.v1               -- Backpressure warning
  k1.fabric.pressure.shedding.v1              -- Load shedding active

References:
  - fabric_discussion.md Section 20 (Event Bus Integration)
  - Epic 5.4.2 in fabric-implementation-plan.md
  - FAB-09 invariant (cognitive_trace_id on every event)
  - Topic constants defined in fabric_events.py (5.4.1)

Exports:
  EventEmitter -- Fabric event emission wrapper
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Protocol

from k1.fabric.events.fabric_events import (
    TOPIC_AGENT_CREATED,
    TOPIC_AGENT_EXPIRED,
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_FAILED,
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_CAPABILITY_REGISTERED,
    TOPIC_CAPABILITY_UNREGISTERED,
    TOPIC_CONTRACT_UPDATED,
    TOPIC_CONTRACT_VALIDATION_FAILED,
    TOPIC_LEARNING_SIGNAL,
    TOPIC_MCP_TOOL_DISCOVERED,
    TOPIC_META_OP_BLOCKED,
    TOPIC_OUTPUT_VALIDATION_FAILED,
    TOPIC_PRESSURE_SHEDDING,
    TOPIC_PRESSURE_WARNING,
    TOPIC_PROVIDER_HEALTH_CHANGED,
    TOPIC_VERSION_CONFLICT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event port protocol (duck-typed to avoid circular imports)
# ---------------------------------------------------------------------------


class EventPort(Protocol):
    """Minimal event bus interface for emit."""

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# Topic constants -- re-exported from fabric_events.py (canonical source)
# ---------------------------------------------------------------------------

# All TOPIC_* constants are imported above from fabric_events.py.
# Re-export for backward compatibility with existing consumers.

__all__ = [
    "EventEmitter",
    "EventPort",
    "ProactiveGapDetector",
    "TOPIC_AGENT_CREATED",
    "TOPIC_AGENT_EXPIRED",
    "TOPIC_CAPABILITY_INVOKED",
    "TOPIC_CAPABILITY_COMPLETED",
    "TOPIC_CAPABILITY_FAILED",
    "TOPIC_LEARNING_SIGNAL",
    "TOPIC_CAPABILITY_REGISTERED",
    "TOPIC_CAPABILITY_UNREGISTERED",
    "TOPIC_CONTRACT_UPDATED",
    "TOPIC_META_OP_BLOCKED",
    "TOPIC_OUTPUT_VALIDATION_FAILED",
    "TOPIC_VERSION_CONFLICT",
    "TOPIC_CONTRACT_VALIDATION_FAILED",
    "TOPIC_PROVIDER_HEALTH_CHANGED",
    "TOPIC_PRESSURE_WARNING",
    "TOPIC_PRESSURE_SHEDDING",
]


# ---------------------------------------------------------------------------
# 5.4.2 -- EventEmitter
# ---------------------------------------------------------------------------


class EventEmitter:
    """
    Fabric event emission wrapper.

    Wraps IEventPort and enforces cognitive_trace_id (FAB-09) on every
    emitted event.  Provides typed emission methods for each Fabric
    event type.

    Constructed by FabricFactory (5.3.1) with the IEventPort injected.
    Used by FabricFacade.execute() and registry operations.

    If no event_port is provided, all emissions are silently dropped
    (graceful degradation for standalone mode without event capture).

    Thread Safety:
        Stateless -- safe for concurrent calls.
    """

    __slots__ = ("_event_port",)

    def __init__(self, event_port: Optional[EventPort] = None) -> None:
        """
        Args:
            event_port: Event bus for publishing events.
                If None, all emissions are silently dropped.
        """
        self._event_port = event_port

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def has_event_port(self) -> bool:
        """Whether an event port is connected."""
        return self._event_port is not None

    # ------------------------------------------------------------------
    # Execution lifecycle events
    # ------------------------------------------------------------------

    def emit_invoked(
        self,
        capability_name: str,
        request_id: str,
        trace_id: str,
        caller: str = "",
        session_id: str = "",
        priority: str = "",
    ) -> None:
        """
        Emit k1.capability.invoked.v1 before execution starts.

        Args:
            capability_name: Name of the capability being invoked.
            request_id: Unique request identifier.
            trace_id: Cognitive trace ID (FAB-09).
            caller: Who initiated the request.
            session_id: Session context.
            priority: WFQ priority class.
        """
        self._emit(
            TOPIC_CAPABILITY_INVOKED,
            {
                "capability_name": capability_name,
                "request_id": request_id,
                "caller": caller,
                "session_id": session_id,
                "priority": priority,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_completed(
        self,
        capability_name: str,
        request_id: str,
        trace_id: str,
        provider_id: str = "",
        duration_ms: int = 0,
    ) -> None:
        """
        Emit k1.capability.completed.v1 after successful execution.

        Args:
            capability_name: Name of the capability that completed.
            request_id: Unique request identifier.
            trace_id: Cognitive trace ID (FAB-09).
            provider_id: Which provider handled the request.
            duration_ms: Total execution duration.
        """
        self._emit(
            TOPIC_CAPABILITY_COMPLETED,
            {
                "capability_name": capability_name,
                "request_id": request_id,
                "provider_id": provider_id,
                "duration_ms": duration_ms,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_failed(
        self,
        capability_name: str,
        request_id: str,
        trace_id: str,
        error_code: str = "",
        error_message: str = "",
        provider_id: str = "",
        duration_ms: int = 0,
    ) -> None:
        """
        Emit k1.capability.failed.v1 after failed execution.

        Args:
            capability_name: Name of the capability that failed.
            request_id: Unique request identifier.
            trace_id: Cognitive trace ID (FAB-09).
            error_code: Machine-readable error code.
            error_message: Human-readable error description.
            provider_id: Which provider (if resolved).
            duration_ms: Duration until failure.
        """
        self._emit(
            TOPIC_CAPABILITY_FAILED,
            {
                "capability_name": capability_name,
                "request_id": request_id,
                "provider_id": provider_id,
                "error_code": error_code,
                "error_message": error_message,
                "duration_ms": duration_ms,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_learning_signal(
        self,
        capability_name: str,
        provider_id: str,
        success: bool,
        duration_ms: int,
        trace_id: str,
        error_code: Optional[str] = None,
        context_quality_score: float = 0.0,
    ) -> None:
        """
        Emit k1.fabric.learning.signal.v1 after every execution result.

        Consumed by K0 feedback pipeline P09 (Learning Loop).

        Args:
            capability_name: Which capability was executed.
            provider_id: Which provider handled it.
            success: Whether execution succeeded.
            duration_ms: Total execution time.
            trace_id: Cognitive trace ID (FAB-09).
            error_code: Error code if failed.
            context_quality_score: Quality score of the assembled context.
        """
        self._emit(
            TOPIC_LEARNING_SIGNAL,
            {
                "capability_name": capability_name,
                "provider_id": provider_id,
                "success": success,
                "duration_ms": duration_ms,
                "error_code": error_code,
                "context_quality_score": context_quality_score,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # Registry lifecycle events
    # ------------------------------------------------------------------

    def emit_registered(
        self,
        capability_name: str,
        trace_id: str = "",
        version: str = "",
        domain: Any = "",
        provider_type: str = "",
    ) -> None:
        """Emit k1.fabric.capability.registered.v1 on registration."""
        self._emit(
            TOPIC_CAPABILITY_REGISTERED,
            {
                "capability_name": capability_name,
                "version": version,
                "domain": domain if domain else "",
                "provider_type": provider_type,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_unregistered(
        self,
        capability_name: str,
        trace_id: str = "",
        reason: str = "",
    ) -> None:
        """Emit k1.fabric.capability.unregistered.v1 on unregistration."""
        self._emit(
            TOPIC_CAPABILITY_UNREGISTERED,
            {
                "capability_name": capability_name,
                "reason": reason,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_contract_updated(
        self,
        capability_name: str,
        old_version: str = "",
        new_version: str = "",
        breaking_change: bool = False,
        trace_id: str = "",
    ) -> None:
        """Emit k1.fabric.capability.contract_updated.v1 for proactive gap detection."""
        self._emit(
            TOPIC_CONTRACT_UPDATED,
            {
                "capability_name": capability_name,
                "old_version": old_version,
                "new_version": new_version,
                "breaking_change": breaking_change,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_version_conflict(
        self,
        capability_name: str,
        existing_version: str = "",
        incoming_version: str = "",
        resolution: str = "",
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.capability.version.conflict.v1 on version conflict.

        Args:
            capability_name: Capability with the version conflict.
            existing_version: The version already registered.
            incoming_version: The version that caused the conflict.
            resolution: How the conflict was resolved
                ("replaced", "rejected", "merged").
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_VERSION_CONFLICT,
            {
                "capability_name": capability_name,
                "existing_version": existing_version,
                "incoming_version": incoming_version,
                "resolution": resolution,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # Validation events
    # ------------------------------------------------------------------

    def emit_contract_validation_failed(
        self,
        file_path: str = "",
        capability_name: str = "",
        validation_errors: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.contract.validation.failed.v1 on schema validation failure.

        Args:
            file_path: Path of the contract file that failed validation.
            capability_name: Capability name (if extractable).
            validation_errors: List of validation error messages.
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_CONTRACT_VALIDATION_FAILED,
            {
                "file_path": file_path,
                "capability_name": capability_name,
                "validation_errors": validation_errors or [],
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_output_validation_failed(
        self,
        capability_name: str = "",
        request_id: str = "",
        provider_id: str = "",
        validation_tier: str = "",
        rejection_reason: str = "",
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.output.validation.failed.v1 on output validation failure.

        Args:
            capability_name: Which capability produced the invalid output.
            request_id: Request being validated.
            provider_id: Which provider generated the output.
            validation_tier: "structural", "schema", or "semantic".
            rejection_reason: Why validation failed.
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_OUTPUT_VALIDATION_FAILED,
            {
                "capability_name": capability_name,
                "request_id": request_id,
                "provider_id": provider_id,
                "validation_tier": validation_tier,
                "rejection_reason": rejection_reason,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # Health & infrastructure events
    # ------------------------------------------------------------------

    def emit_health_changed(
        self,
        provider_id: str,
        old_state: str = "",
        new_state: str = "",
        reason: str = "",
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.provider.health.changed.v1 on health state transition.

        Args:
            provider_id: Provider that changed state.
            old_state: Previous health state ("HEALTHY", "DEGRADED", "UNHEALTHY").
            new_state: New health state.
            reason: Why the transition occurred.
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_PROVIDER_HEALTH_CHANGED,
            {
                "provider_id": provider_id,
                "old_state": old_state,
                "new_state": new_state,
                "reason": reason,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_pressure_warning(
        self,
        current_depth: int = 0,
        max_depth: int = 0,
        backpressure_level: str = "",
        in_flight: int = 0,
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.pressure.warning.v1 on backpressure warning (80% depth).

        Args:
            current_depth: Current mailbox depth.
            max_depth: Maximum mailbox depth.
            backpressure_level: "WARNING", "SHEDDING", or "SATURATED".
            in_flight: Number of in-flight requests.
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_PRESSURE_WARNING,
            {
                "current_depth": current_depth,
                "max_depth": max_depth,
                "backpressure_level": backpressure_level,
                "in_flight": in_flight,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_pressure_shedding(
        self,
        current_depth: int = 0,
        max_depth: int = 0,
        backpressure_level: str = "",
        rejected_priority: str = "",
        in_flight: int = 0,
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.pressure.shedding.v1 when load shedding is active (95% depth).

        Args:
            current_depth: Current mailbox depth.
            max_depth: Maximum mailbox depth.
            backpressure_level: "SHEDDING" or "SATURATED".
            rejected_priority: Priority class being shed (e.g., "BACKGROUND").
            in_flight: Number of in-flight requests.
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_PRESSURE_SHEDDING,
            {
                "current_depth": current_depth,
                "max_depth": max_depth,
                "backpressure_level": backpressure_level,
                "rejected_priority": rejected_priority,
                "in_flight": in_flight,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # 4.5.7 -- Agent creation lifecycle event emitters
    # ------------------------------------------------------------------

    def emit_agent_created(
        self,
        agent_name: str = "",
        created_by: str = "",
        tools_granted: List[str] | None = None,
        domain: List[str] | None = None,
        prompt_template: str = "",
        ephemeral: bool = True,
        session_id: str = "",
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.agent.created.v1 after successful agent creation.

        Called by BuildAgentHandler (4.5.2) step 7.  Satisfies the
        EmitterForBuildLike protocol defined in agent_builder.py.

        Args:
            agent_name: Name of the newly created agent.
            created_by: Identifier of the requesting agent/user.
            tools_granted: List of capability names granted to the agent.
            domain: Domain tags for the new agent.
            prompt_template: System prompt template used.
            ephemeral: Whether the agent is session-scoped.
            session_id: Session that owns the agent.
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_AGENT_CREATED,
            {
                "agent_name": agent_name,
                "created_by": created_by,
                "tools_granted": list(tools_granted or []),
                "domain": list(domain or []),
                "prompt_template": prompt_template,
                "ephemeral": ephemeral,
                "session_id": session_id,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_agent_expired(
        self,
        agent_name: str = "",
        created_at_iso: str = "",
        expired_at_iso: str = "",
        invocations: int = 0,
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.agent.expired.v1 when a runtime agent is removed.

        Called by session cleanup or Registry.remove_expired_agents().

        Args:
            agent_name: Name of the expired agent.
            created_at_iso: ISO timestamp when agent was created.
            expired_at_iso: ISO timestamp when agent was expired.
            invocations: Total invocations during agent lifetime.
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_AGENT_EXPIRED,
            {
                "agent_name": agent_name,
                "created_at_iso": created_at_iso,
                "expired_at_iso": expired_at_iso,
                "invocations": invocations,
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    def emit_meta_blocked(
        self,
        operation: str = "",
        violation_type: str = "",
        requested_by: str = "",
        details: Dict[str, str] | None = None,
        trace_id: str = "",
    ) -> None:
        """
        Emit k1.fabric.meta.operation.blocked.v1 on security violation.

        Called by MetaOperationValidator (4.5.5) when a meta-operation
        is rejected by one of the 5 hard gates.

        Args:
            operation: Operation attempted (e.g., 'create_agent').
            violation_type: Type of violation (e.g., 'budget_exceeded').
            requested_by: Identifier of the requester.
            details: Additional context about the violation.
            trace_id: Cognitive trace ID (FAB-09).
        """
        self._emit(
            TOPIC_META_OP_BLOCKED,
            {
                "operation": operation,
                "violation_type": violation_type,
                "requested_by": requested_by,
                "details": dict(details or {}),
                "timestamp_ms": _now_ms(),
            },
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # Internal: emit with trace_id enforcement
    # ------------------------------------------------------------------

    def _emit(
        self,
        topic: str,
        payload: Dict[str, Any],
        trace_id: str = "",
    ) -> None:
        """
        Emit an event with cognitive_trace_id enforcement (FAB-09).

        If no event_port is connected, the call is silently dropped.
        Exceptions from the event port are caught and logged.
        """
        if self._event_port is None:
            return

        # FAB-09: Every event carries cognitive_trace_id
        payload["cognitive_trace_id"] = trace_id

        try:
            self._event_port.emit(topic, payload)
        except Exception:
            logger.warning(
                "EventEmitter failed to emit %s",
                topic,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# 5.4.4 -- ProactiveGapDetector
# ---------------------------------------------------------------------------


class SubscribableEventPort(Protocol):
    """Event port extended with subscribe capability."""

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None: ...

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> Any: ...


class ModuleLoaderPort(Protocol):
    """Minimal ModuleLoader interface for programmatic registration."""

    def register_from_dict(
        self,
        contract_dict: Dict[str, Any],
        *,
        contract_type: Optional[str] = None,
        skip_validation: bool = False,
    ) -> Any: ...


class ProactiveGapDetector:
    """
    5.4.4 -- Proactive gap detection via event subscriptions.

    Subscribes to registry change events (register, unregister, version
    conflict) and re-emits ``k1.fabric.capability.contract_updated.v1``
    through EventEmitter so that Orchestrator's Workflow Engine can
    invalidate affected frozen workflows and trigger re-validation.

    Also subscribes to ``k1.mcp.tool.discovered.v1`` from Orchestrator
    MCP Tool Discovery and converts discovered tools into capability
    contracts via ModuleLoader.register_from_dict() (Issue 2.3.4).

    Lifecycle:
      1. Created by FabricFactory after EventEmitter and ModuleLoader.
      2. ``wire_subscriptions()`` called during bootstrap (Step 20).
      3. Subscriptions remain active until Fabric shutdown.

    Thread Safety:
        Stateless handlers; safe for concurrent event delivery.

    References:
        - fabric_discussion.md Section 20 (Event Bus Integration)
        - Epic 5.4.4 in fabric-implementation-plan.md
    """

    __slots__ = (
        "_event_port",
        "_event_emitter",
        "_module_loader",
        "_subscription_handles",
    )

    def __init__(
        self,
        event_port: SubscribableEventPort,
        event_emitter: EventEmitter,
        module_loader: Optional[ModuleLoaderPort] = None,
    ) -> None:
        """
        Args:
            event_port: Event bus with subscribe capability.
            event_emitter: EventEmitter for re-emitting contract_updated.
            module_loader: ModuleLoader for MCP tool registration.
                If None, MCP tool discovery subscription is skipped.
        """
        self._event_port = event_port
        self._event_emitter = event_emitter
        self._module_loader = module_loader
        self._subscription_handles: List[Any] = []

    # ------------------------------------------------------------------
    # Public: Wire all subscriptions
    # ------------------------------------------------------------------

    def wire_subscriptions(self) -> None:
        """
        Subscribe to all registry change and MCP discovery events.

        Called once during FabricFactory bootstrap (Step 20).
        Idempotent: subsequent calls add duplicate subscriptions,
        so call only once.
        """
        # Subscribe to registry lifecycle events
        self._subscribe(
            TOPIC_CAPABILITY_REGISTERED,
            self._on_capability_registered,
        )
        self._subscribe(
            TOPIC_CAPABILITY_UNREGISTERED,
            self._on_capability_unregistered,
        )
        self._subscribe(
            TOPIC_VERSION_CONFLICT,
            self._on_version_conflict,
        )

        # Subscribe to MCP tool discovery from Orchestrator
        if self._module_loader is not None:
            self._subscribe(
                TOPIC_MCP_TOOL_DISCOVERED,
                self._on_mcp_tool_discovered,
            )

        logger.info(
            "ProactiveGapDetector wired %d subscriptions",
            len(self._subscription_handles),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def subscription_count(self) -> int:
        """Number of active event subscriptions."""
        return len(self._subscription_handles)

    def stop(self) -> None:
        """Unsubscribe all event subscriptions wired by this detector."""
        for handle in list(self._subscription_handles):
            try:
                self._event_port.unsubscribe(handle)
            except Exception:
                logger.debug("ProactiveGapDetector unsubscribe failed", exc_info=True)
        self._subscription_handles.clear()

    # ------------------------------------------------------------------
    # Handlers: Registry change events -> contract_updated emission
    # ------------------------------------------------------------------

    def _on_capability_registered(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Handle k1.fabric.capability.registered.v1.

        Emits contract_updated with new_version, breaking_change=False.
        This allows Orchestrator to re-validate workflows that depend
        on the newly registered capability.
        """
        capability_name = payload.get("capability_name", payload.get("name", ""))
        version = payload.get("version", "")
        trace_id = payload.get("cognitive_trace_id", "")

        self._event_emitter.emit_contract_updated(
            capability_name=capability_name,
            old_version="",
            new_version=version,
            breaking_change=False,
            trace_id=trace_id,
        )

        logger.debug(
            "Gap detector: emitted contract_updated for registered '%s' v%s",
            capability_name,
            version,
        )

    def _on_capability_unregistered(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Handle k1.fabric.capability.unregistered.v1.

        Emits contract_updated with breaking_change=True (capability
        removed = workflows depending on it are broken).
        """
        capability_name = payload.get("capability_name", payload.get("name", ""))
        trace_id = payload.get("cognitive_trace_id", "")

        self._event_emitter.emit_contract_updated(
            capability_name=capability_name,
            old_version="",
            new_version="",
            breaking_change=True,  # removal is always breaking
            trace_id=trace_id,
        )

        logger.debug(
            "Gap detector: emitted contract_updated (breaking) for unregistered '%s'",
            capability_name,
        )

    def _on_version_conflict(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Handle k1.fabric.capability.version.conflict.v1.

        Emits contract_updated with both versions and breaking_change
        based on resolution strategy.
        """
        capability_name = payload.get("capability_name", payload.get("name", ""))
        existing_version = payload.get("existing_version", payload.get("old_version", ""))
        incoming_version = payload.get("incoming_version", payload.get("new_version", ""))
        resolution = payload.get("resolution", "")
        trace_id = payload.get("cognitive_trace_id", "")

        # Version conflict with replacement is potentially breaking
        breaking = resolution in ("replaced", "rejected")

        self._event_emitter.emit_contract_updated(
            capability_name=capability_name,
            old_version=existing_version,
            new_version=incoming_version,
            breaking_change=breaking,
            trace_id=trace_id,
        )

        logger.debug(
            "Gap detector: emitted contract_updated for version conflict '%s' "
            "(%s -> %s, resolution=%s)",
            capability_name,
            existing_version,
            incoming_version,
            resolution,
        )

    # ------------------------------------------------------------------
    # Handler: MCP tool discovery -> programmatic registration
    # ------------------------------------------------------------------

    def _on_mcp_tool_discovered(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Handle k1.mcp.tool.discovered.v1 from Orchestrator.

        Converts the MCP tool manifest into a CapabilityContract dict
        and registers it via ModuleLoader.register_from_dict() (2.3.4).

        Payload expected:
            tool_name: str
            tool_description: str
            input_schema: dict
            output_schema: dict
            server_id: str
            server_name: str
        """
        if self._module_loader is None:
            logger.warning(
                "MCP tool discovered but no module_loader available: %s",
                payload.get("tool_name", "unknown"),
            )
            return

        tool_name = payload.get("tool_name", "")
        if not tool_name:
            logger.warning("MCP tool discovered with empty tool_name, skipping")
            return

        # Convert MCP tool manifest to capability contract dict format
        contract_dict = _mcp_tool_to_contract_dict(payload)

        try:
            self._module_loader.register_from_dict(
                contract_dict,
                contract_type="tool_contract",
                skip_validation=False,
            )
            logger.info(
                "MCP tool registered as capability: %s (server=%s)",
                tool_name,
                payload.get("server_name", "unknown"),
            )
        except Exception:
            logger.warning(
                "Failed to register MCP tool '%s' as capability",
                tool_name,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Private: subscribe helper
    # ------------------------------------------------------------------

    def _subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        """Subscribe and track handle."""
        try:
            handle = self._event_port.subscribe(topic, handler)
            self._subscription_handles.append(handle)
        except Exception:
            logger.warning(
                "ProactiveGapDetector failed to subscribe to %s",
                topic,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# MCP tool manifest -> contract dict converter
# ---------------------------------------------------------------------------


def _mcp_tool_to_contract_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert MCP tool discovery payload to CapabilityContract dict.

    This creates a tool_contract body dict suitable for
    ModuleLoader.register_from_dict(contract_type="tool_contract").

    The resulting dict follows the CapabilityContract schema (1.2.1).
    """
    tool_name = payload.get("tool_name", "")
    description = payload.get("tool_description", "")
    input_schema = payload.get("input_schema", {})
    output_schema = payload.get("output_schema", {})
    server_id = payload.get("server_id", "")
    server_name = payload.get("server_name", "")

    # Build required_inputs from JSON Schema properties
    required_inputs = []
    if isinstance(input_schema, dict):
        properties = input_schema.get("properties", {})
        required_names = set(input_schema.get("required", []))
        for prop_name, prop_def in properties.items():
            required_inputs.append(
                {
                    "name": prop_name,
                    "type": prop_def.get("type", "string"),
                    "required": prop_name in required_names,
                    "description": prop_def.get("description", ""),
                }
            )

    # Canonical capability name from MCP tool name
    # Format: tool.execute.mcp.<tool_name>  (4 segments, valid per updated FAB-11)
    # e.g. "get_weather" -> "tool.execute.mcp.get_weather"
    canonical_name = f"tool.execute.mcp.{tool_name}"

    return {
        "name": canonical_name,
        "version": "1.0.0",
        "description": description or f"MCP tool: {tool_name}",
        "domain": ["mcp"],
        "provider_type": "MCP",
        "provider_id": server_id or server_name or tool_name,
        "required_inputs": required_inputs,
        "output": output_schema if output_schema else {"type": "object"},
        "safety_band_min": "GREEN",
        "availability": "ONLINE",
        "tags": [f"mcp_server:{server_name}"] if server_name else ["mcp"],
    }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    """Current epoch time in milliseconds."""
    return int(time.time() * 1000)
