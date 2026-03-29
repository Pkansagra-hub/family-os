"""
k1.fabric.events.fabric_events -- Fabric event type dataclasses (5.4.1).

Defines ALL event payload schemas used by the Capability Fabric.
Each event type is a frozen dataclass with a ``to_dict()`` serializer.

Event payloads carry structured data that flows through IEventPort.
Every payload produced by Fabric includes ``cognitive_trace_id`` (FAB-09),
injected by EventEmitter at emission time (not stored in the dataclass).

Categories:
  Emitted (by Fabric):
    - CapabilityInvokedEvent        k1.capability.invoked.v1
    - CapabilityCompletedEvent      k1.capability.completed.v1
    - CapabilityFailedEvent         k1.capability.failed.v1
    - LearningSignalEvent           k1.fabric.learning.signal.v1
    - CapabilityRegisteredEvent     k1.fabric.capability.registered.v1
    - CapabilityUnregisteredEvent   k1.fabric.capability.unregistered.v1
    - VersionConflictEvent          k1.fabric.capability.version.conflict.v1
    - ContractValidationFailedEvent k1.fabric.contract.validation.failed.v1
    - OutputValidationFailedEvent   k1.fabric.output.validation.failed.v1
    - ProviderHealthChangedEvent    k1.fabric.provider.health.changed.v1
    - ContractUpdatedEvent          k1.fabric.capability.contract_updated.v1
    - PressureWarningEvent          k1.fabric.pressure.warning.v1
    - PressureSheddingEvent         k1.fabric.pressure.shedding.v1
    - AgentCreatedEvent             k1.fabric.agent.created.v1       (4.5.7)
    - AgentExpiredEvent             k1.fabric.agent.expired.v1       (4.5.7)
    - MetaOperationBlockedEvent     k1.fabric.meta.operation.blocked.v1 (4.5.7)

  Consumed (by Fabric, from external):
    - StepExecuteEvent              k1.orchestration.step.execute.v1
    - DiscoveryRequestEvent         k1.planner.discovery.request.v1
    - HealthCheckRequestEvent       k1.fabric.provider.health.check.v1
    - MCPToolDiscoveredEvent        k1.mcp.tool.discovered.v1

References:
  - fabric_discussion.md Section 20 (Event Bus Integration)
  - Epic 5.4.1 in fabric-implementation-plan.md
  - FAB-09 invariant (cognitive_trace_id injected by EventEmitter)

Exports:
  All event dataclasses + topic constants + EMITTED_TOPICS + CONSUMED_TOPICS
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ===========================================================================
# Topic constants -- canonical event topic strings
# ===========================================================================

# --- Emitted by Fabric ---
TOPIC_CAPABILITY_INVOKED = "k1.capability.invoked.v1"
TOPIC_CAPABILITY_COMPLETED = "k1.capability.completed.v1"
TOPIC_CAPABILITY_FAILED = "k1.capability.failed.v1"
TOPIC_LEARNING_SIGNAL = "k1.fabric.learning.signal.v1"
TOPIC_CAPABILITY_REGISTERED = "k1.fabric.capability.registered.v1"
TOPIC_CAPABILITY_UNREGISTERED = "k1.fabric.capability.unregistered.v1"
TOPIC_VERSION_CONFLICT = "k1.fabric.capability.version.conflict.v1"
TOPIC_CONTRACT_VALIDATION_FAILED = "k1.fabric.contract.validation.failed.v1"
TOPIC_OUTPUT_VALIDATION_FAILED = "k1.fabric.output.validation.failed.v1"
TOPIC_PROVIDER_HEALTH_CHANGED = "k1.fabric.provider.health.changed.v1"
TOPIC_CONTRACT_UPDATED = "k1.fabric.capability.contract_updated.v1"
TOPIC_PRESSURE_WARNING = "k1.fabric.pressure.warning.v1"
TOPIC_PRESSURE_SHEDDING = "k1.fabric.pressure.shedding.v1"

# --- 4.5.7: Agent creation lifecycle events ---
TOPIC_AGENT_CREATED = "k1.fabric.agent.created.v1"
TOPIC_AGENT_EXPIRED = "k1.fabric.agent.expired.v1"
TOPIC_META_OP_BLOCKED = "k1.fabric.meta.operation.blocked.v1"

# --- Consumed by Fabric (from external subsystems) ---
TOPIC_STEP_EXECUTE = "k1.orchestration.step.execute.v1"
TOPIC_DISCOVERY_REQUEST = "k1.planner.discovery.request.v1"
TOPIC_HEALTH_CHECK_REQUEST = "k1.fabric.provider.health.check.v1"
TOPIC_MCP_TOOL_DISCOVERED = "k1.mcp.tool.discovered.v1"

# --- Aggregated lists for introspection ---
EMITTED_TOPICS: List[str] = [
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_FAILED,
    TOPIC_LEARNING_SIGNAL,
    TOPIC_CAPABILITY_REGISTERED,
    TOPIC_CAPABILITY_UNREGISTERED,
    TOPIC_VERSION_CONFLICT,
    TOPIC_CONTRACT_VALIDATION_FAILED,
    TOPIC_OUTPUT_VALIDATION_FAILED,
    TOPIC_PROVIDER_HEALTH_CHANGED,
    TOPIC_CONTRACT_UPDATED,
    TOPIC_PRESSURE_WARNING,
    TOPIC_PRESSURE_SHEDDING,
    TOPIC_AGENT_CREATED,
    TOPIC_AGENT_EXPIRED,
    TOPIC_META_OP_BLOCKED,
]

CONSUMED_TOPICS: List[str] = [
    TOPIC_STEP_EXECUTE,
    TOPIC_DISCOVERY_REQUEST,
    TOPIC_HEALTH_CHECK_REQUEST,
    TOPIC_MCP_TOOL_DISCOVERED,
]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    """Current epoch time in milliseconds."""
    return int(time.time() * 1000)


# ===========================================================================
# Emitted event payloads
# ===========================================================================


# ---------------------------------------------------------------------------
# Execution lifecycle events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityInvokedEvent:
    """
    k1.capability.invoked.v1 -- Emitted BEFORE execution starts.

    Signals that a capability request has been accepted and is about
    to enter the execution pipeline.

    Consumed by: Orchestrator (request tracking), observability.
    """

    capability_name: str
    request_id: str
    caller: str = ""
    session_id: str = ""
    priority: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "request_id": self.request_id,
            "caller": self.caller,
            "session_id": self.session_id,
            "priority": self.priority,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class CapabilityCompletedEvent:
    """
    k1.capability.completed.v1 -- Emitted AFTER successful execution.

    Signals that a capability has been executed successfully, with
    timing and provider information.

    Consumed by: Orchestrator (step completion), observability.
    """

    capability_name: str
    request_id: str
    provider_id: str = ""
    duration_ms: int = 0
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "request_id": self.request_id,
            "provider_id": self.provider_id,
            "duration_ms": self.duration_ms,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class CapabilityFailedEvent:
    """
    k1.capability.failed.v1 -- Emitted AFTER failed execution.

    Includes error code, message, and optional provider info.

    Consumed by: Orchestrator (step failure handling), observability.
    """

    capability_name: str
    request_id: str
    error_code: str = ""
    error_message: str = ""
    provider_id: str = ""
    duration_ms: int = 0
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "request_id": self.request_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "provider_id": self.provider_id,
            "duration_ms": self.duration_ms,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class LearningSignalEvent:
    """
    k1.fabric.learning.signal.v1 -- Emitted AFTER every execution result.

    Full payload for K0 feedback pipeline P09 (Learning Loop).
    Carries capability name, provider, success/failure, timing, errors,
    and context quality score for adaptive routing improvements.

    Consumed by: Learning Loop, K0 feedback pipeline P09.
    """

    capability_name: str
    provider_id: str
    success: bool
    duration_ms: int
    error_code: Optional[str] = None
    context_quality_score: float = 0.0
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "provider_id": self.provider_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "context_quality_score": self.context_quality_score,
            "timestamp_ms": self.timestamp_ms,
        }


# ---------------------------------------------------------------------------
# Registry lifecycle events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityRegisteredEvent:
    """
    k1.fabric.capability.registered.v1 -- On capability registration.

    Consumed by: Orchestrator (workflow re-validation), observability.
    """

    capability_name: str
    version: str = ""
    domain: str = ""
    provider_type: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "version": self.version,
            "domain": self.domain,
            "provider_type": self.provider_type,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class CapabilityUnregisteredEvent:
    """
    k1.fabric.capability.unregistered.v1 -- On capability unregistration.

    Consumed by: Orchestrator (workflow invalidation), Planner.
    """

    capability_name: str
    version: str = ""
    reason: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "version": self.version,
            "reason": self.reason,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class VersionConflictEvent:
    """
    k1.fabric.capability.version.conflict.v1 -- On version conflict.

    Emitted when a contract registration detects a version conflict
    (e.g., same name different incompatible version).

    Consumed by: Orchestrator (workflow invalidation), observability.
    """

    capability_name: str
    existing_version: str = ""
    incoming_version: str = ""
    resolution: str = ""  # "replaced", "rejected", "merged"
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "existing_version": self.existing_version,
            "incoming_version": self.incoming_version,
            "resolution": self.resolution,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class ContractUpdatedEvent:
    """
    k1.fabric.capability.contract_updated.v1 -- Proactive gap detection.

    Emitted when capability contracts change.  Orchestrator's Workflow
    Engine consumes this to invalidate affected frozen workflows and
    trigger re-validation.

    Consumed by: Orchestrator Workflow Engine.
    """

    capability_name: str
    old_version: str = ""
    new_version: str = ""
    breaking_change: bool = False
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "breaking_change": self.breaking_change,
            "timestamp_ms": self.timestamp_ms,
        }


# ---------------------------------------------------------------------------
# Validation events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractValidationFailedEvent:
    """
    k1.fabric.contract.validation.failed.v1 -- Contract validation failure.

    Emitted by ModuleLoader when a YAML contract fails schema validation.

    Consumed by: observability, admin dashboards.
    """

    file_path: str = ""
    capability_name: str = ""
    validation_errors: List[str] = field(default_factory=list)
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "capability_name": self.capability_name,
            "validation_errors": list(self.validation_errors),
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class OutputValidationFailedEvent:
    """
    k1.fabric.output.validation.failed.v1 -- Output validation failure.

    Emitted by OutputValidationPipeline when provider output fails
    structural, schema, or semantic validation.

    Consumed by: observability, Learning Loop (quality signals).
    """

    capability_name: str = ""
    request_id: str = ""
    provider_id: str = ""
    validation_tier: str = ""  # "structural", "schema", "semantic"
    rejection_reason: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "request_id": self.request_id,
            "provider_id": self.provider_id,
            "validation_tier": self.validation_tier,
            "rejection_reason": self.rejection_reason,
            "timestamp_ms": self.timestamp_ms,
        }


# ---------------------------------------------------------------------------
# Health & infrastructure events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderHealthChangedEvent:
    """
    k1.fabric.provider.health.changed.v1 -- Provider health state change.

    Emitted by HealthChecker when a provider transitions between
    HEALTHY, DEGRADED, and UNHEALTHY states.

    Consumed by: Resolver (availability routing), observability.
    """

    provider_id: str
    old_state: str = ""  # "HEALTHY", "DEGRADED", "UNHEALTHY"
    new_state: str = ""
    reason: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "old_state": self.old_state,
            "new_state": self.new_state,
            "reason": self.reason,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class PressureWarningEvent:
    """
    k1.fabric.pressure.warning.v1 -- Backpressure warning (80% depth).

    Emitted by FabricDispatcher when mailbox depth crosses the
    warning threshold.

    Consumed by: Orchestrator (throttle new work), observability.
    """

    current_depth: int = 0
    max_depth: int = 0
    backpressure_level: str = ""  # "WARNING", "SHEDDING", "SATURATED"
    in_flight: int = 0
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_depth": self.current_depth,
            "max_depth": self.max_depth,
            "backpressure_level": self.backpressure_level,
            "in_flight": self.in_flight,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class PressureSheddingEvent:
    """
    k1.fabric.pressure.shedding.v1 -- Load shedding active (95% depth).

    Emitted when FabricDispatcher begins rejecting BACKGROUND priority
    requests.

    Consumed by: Orchestrator (defer background work), observability.
    """

    current_depth: int = 0
    max_depth: int = 0
    backpressure_level: str = ""
    rejected_priority: str = ""  # e.g., "BACKGROUND"
    in_flight: int = 0
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_depth": self.current_depth,
            "max_depth": self.max_depth,
            "backpressure_level": self.backpressure_level,
            "rejected_priority": self.rejected_priority,
            "in_flight": self.in_flight,
            "timestamp_ms": self.timestamp_ms,
        }


# ===========================================================================
# Consumed event payloads (from external subsystems)
# ===========================================================================


@dataclass(frozen=True)
class StepExecuteEvent:
    """
    k1.orchestration.step.execute.v1 -- From Orchestrator.

    Requests Fabric to execute a capability as part of a plan step.

    Produced by: Orchestrator.
    Consumed by: Fabric (triggers execute() pipeline).
    """

    capability_name: str
    request_id: str = ""
    session_id: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    priority: str = "INTERACTIVE"
    caller: str = "orchestrator"
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "params": dict(self.params),
            "trace_id": self.trace_id,
            "priority": self.priority,
            "caller": self.caller,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepExecuteEvent":
        """Deserialize from dict payload."""
        return cls(
            capability_name=data.get("capability_name", ""),
            request_id=data.get("request_id", ""),
            session_id=data.get("session_id", ""),
            params=dict(data.get("params", {})),
            trace_id=data.get("trace_id", ""),
            priority=data.get("priority", "INTERACTIVE"),
            caller=data.get("caller", "orchestrator"),
            timestamp_ms=data.get("timestamp_ms", 0),
        )


@dataclass(frozen=True)
class DiscoveryRequestEvent:
    """
    k1.planner.discovery.request.v1 -- From Planner.

    Requests Fabric to discover capabilities matching intent + domain.

    Produced by: Planner.
    Consumed by: Fabric (triggers discover_capabilities()).
    """

    intent: str = ""
    domain: List[str] = field(default_factory=list)
    safety_band: str = "GREEN"
    top_k: int = 10
    request_id: str = ""
    trace_id: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "domain": list(self.domain),
            "safety_band": self.safety_band,
            "top_k": self.top_k,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryRequestEvent":
        """Deserialize from dict payload."""
        return cls(
            intent=data.get("intent", ""),
            domain=list(data.get("domain", [])),
            safety_band=data.get("safety_band", "GREEN"),
            top_k=data.get("top_k", 10),
            request_id=data.get("request_id", ""),
            trace_id=data.get("trace_id", ""),
            timestamp_ms=data.get("timestamp_ms", 0),
        )


@dataclass(frozen=True)
class HealthCheckRequestEvent:
    """
    k1.fabric.provider.health.check.v1 -- Health check trigger.

    Requests Fabric to run a health check on a specific provider
    or all providers.

    Produced by: External monitor, K0 supervision.
    Consumed by: Fabric HealthChecker.
    """

    provider_id: str = ""  # empty = check all
    trace_id: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "trace_id": self.trace_id,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HealthCheckRequestEvent":
        """Deserialize from dict payload."""
        return cls(
            provider_id=data.get("provider_id", ""),
            trace_id=data.get("trace_id", ""),
            timestamp_ms=data.get("timestamp_ms", 0),
        )


@dataclass(frozen=True)
class MCPToolDiscoveredEvent:
    """
    k1.mcp.tool.discovered.v1 -- From Orchestrator MCP Tool Discovery.

    Signals that a new MCP tool has been discovered and should be
    programmatically registered as a capability contract.

    Fabric subscribes to this and calls register_from_dict() (2.3.4).

    Produced by: Orchestrator MCP Tool Discovery.
    Consumed by: Fabric ModuleLoader / Registry.
    """

    tool_name: str = ""
    tool_description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    server_id: str = ""
    server_name: str = ""
    trace_id: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_description": self.tool_description,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "server_id": self.server_id,
            "server_name": self.server_name,
            "trace_id": self.trace_id,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPToolDiscoveredEvent":
        """Deserialize from dict payload."""
        return cls(
            tool_name=data.get("tool_name", ""),
            tool_description=data.get("tool_description", ""),
            input_schema=dict(data.get("input_schema", {})),
            output_schema=dict(data.get("output_schema", {})),
            server_id=data.get("server_id", ""),
            server_name=data.get("server_name", ""),
            trace_id=data.get("trace_id", ""),
            timestamp_ms=data.get("timestamp_ms", 0),
        )


# ===========================================================================
# 4.5.7 -- Agent creation lifecycle events
# ===========================================================================


@dataclass(frozen=True)
class AgentCreatedEvent:
    """
    k1.fabric.agent.created.v1 -- Emitted when a runtime agent is created.

    Emitted by BuildAgentHandler (4.5.2) step 7 after successful
    agent registration.  Carries full creation metadata for audit,
    Learning Loop, and observability.

    Consumed by: K1 Event Bus subscribers, Learning Loop, audit log.
    """

    agent_name: str
    created_by: str = ""
    tools_granted: tuple[str, ...] = ()
    domain: tuple[str, ...] = ()
    prompt_template: str = ""
    ephemeral: bool = True
    session_id: str = ""
    trace_id: str = ""
    timestamp_iso: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "created_by": self.created_by,
            "tools_granted": list(self.tools_granted),
            "domain": list(self.domain),
            "prompt_template": self.prompt_template,
            "ephemeral": self.ephemeral,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "timestamp_iso": self.timestamp_iso,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class AgentExpiredEvent:
    """
    k1.fabric.agent.expired.v1 -- Emitted when a runtime agent is removed.

    Emitted by Registry.remove_expired_agents() (4.5.6) on session
    cleanup.  Carries creation timestamp for lifetime calculation.

    Consumed by: Learning Loop, audit log, observability.
    """

    agent_name: str
    created_at_iso: str = ""
    expired_at_iso: str = ""
    invocations: int = 0
    trace_id: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "created_at_iso": self.created_at_iso,
            "expired_at_iso": self.expired_at_iso,
            "invocations": self.invocations,
            "trace_id": self.trace_id,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class MetaOperationBlockedEvent:
    """
    k1.fabric.meta.operation.blocked.v1 -- Emitted on security violation.

    Emitted by MetaOperationValidator (4.5.5) when any of the 5 hard
    gates reject a meta-operation.  Carries violation details for
    security audit and incident response.

    Consumed by: K1 Event Bus subscribers, audit log, security monitoring.
    """

    operation: str = ""
    violation_type: str = ""
    requested_by: str = ""
    details: Dict[str, str] = field(default_factory=dict)
    trace_id: str = ""
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "violation_type": self.violation_type,
            "requested_by": self.requested_by,
            "details": dict(self.details),
            "trace_id": self.trace_id,
            "timestamp_ms": self.timestamp_ms,
        }
