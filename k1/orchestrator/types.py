"""
Orchestrator Core Types -- Domain types for the Orchestrator module.

All Orchestrator domain types as Python dataclasses. These are the message
envelopes and data structures used across all services.

Design decisions:
  - ORCH-001: Actor-based single-mailbox architecture
  - ORCH-002: Hexagonal port/adapter with 8 ports
  - ORCH-003: DAG wave execution model
  - ORCH-010: PlanStep extensions beyond Fabric's 6-field base

References:
  - orchestrator.mmd ORCH_CORE
  - docs/whiteboard/schema_whiteboard.md (Sections 1-10)
  - k1/docs/adrs/ORCH-001 through ORCH-012

Anti-hallucination rules:
  - All types are pure dataclasses with NO I/O, NO port references, NO service logic.
  - Do NOT add async methods to dataclasses.
  - Do NOT import from k1.orchestrator.orchestration/* here.
  - Single types.py module -- do NOT split into per-service files.

Import graph:
  - k1.orchestrator.types -> k1.fabric.types (Tier, CapabilityResult)
  - k1.orchestrator.types -> k1.fabric.ports.state_reader (SessionSnapshot)
  - NEVER import from service or port modules (no circular deps)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import CapabilityResult
from k1.fabric.types import PlanStep as FabricPlanStep
from k1.fabric.types import Tier

# ===========================================================================
# Layer 1 -- Enums (1.2.9, 1.2.10, 1.2.12 partial, 1.2.24 partial)
# ===========================================================================


class StepStatus(str, Enum):
    """Lifecycle status of a single DAG step.

    PENDING  -- initial state, not yet dispatched.
    RUNNING  -- dispatched to Fabric, awaiting result.
    COMPLETED -- Fabric returned success.
    FAILED   -- Fabric returned error or retries exhausted.
    CANCELLED -- user interrupt or DAG abort.
    SKIPPED  -- conditional edge false OR dependency of failed optional step.
                Log skip reason separately in StepResult.error_detail.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class TriggerType(str, Enum):
    """Workflow trigger type.

    Independent from k1.fabric.types.TriggerType (Fabric uses lowercase).
    Drives WorkflowScheduler behavior.
    """

    CRON = "CRON"
    EVENT = "EVENT"
    MANUAL = "MANUAL"


class ProcessResult(str, Enum):
    """Return value of OrchestratorService.process().

    COMPLETED -- all steps succeeded.
    FAILED    -- one or more steps failed (no independent successes).
    DEGRADED  -- partial success (some steps failed, independent steps succeeded).
    CANCELLED -- user interrupt or external cancellation.
    DEFERRED  -- re-enqueued because DAG active (ConcurrencyGuard).
    """

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
    CANCELLED = "CANCELLED"
    DEFERRED = "DEFERRED"


class ErrorSeverity(str, Enum):
    """Error classification for ErrorRouter.

    RECOVERABLE -- transient, retry once (Mailbox, DeltaEmit, BridgeWrite, EventSub).
    DEGRADED    -- step fails but independent steps continue (Fabric, Planner, StateRead).
    TERMINAL    -- unrecoverable, abort execution.
    """

    RECOVERABLE = "RECOVERABLE"
    DEGRADED = "DEGRADED"
    TERMINAL = "TERMINAL"


class ProactiveGapStatus(str, Enum):
    """Lifecycle status of a ProactiveGap detection.

    PENDING       -- gap detected, not yet surfaced to user.
    ASKED         -- surfaced to user via IDeltaEmitPort.
    RESOLVED      -- user provided resolution.
    AUTO_RESOLVED -- system auto-filled per gap classification.
    """

    PENDING = "PENDING"
    ASKED = "ASKED"
    RESOLVED = "RESOLVED"
    AUTO_RESOLVED = "AUTO_RESOLVED"


class GuardAction(str, Enum):
    """Guard pipeline decision actions (merged superset).

    Routing-phase actions (PreDispatchGuard):
      ALLOW   -- proceed with dispatch.
      REJECT  -- stop with error.
      DEGRADE -- downgrade tier (HIGH -> MEDIUM).
      DEFER   -- re-enqueue for later.

    Execution-phase actions (PreWave/PostStep/PostWave guards):
      CONTINUE  -- proceed normally.
      RETRY     -- re-execute the step (OutputSchemaGuard).
      SKIP      -- skip the step (ConditionalEdgeEvaluator).
      HARD_STOP -- abort remaining waves.
      BYPASS    -- guard not applicable (no schema defined, etc.).
    """

    ALLOW = "ALLOW"
    REJECT = "REJECT"
    CONTINUE = "CONTINUE"
    RETRY = "RETRY"
    SKIP = "SKIP"
    HARD_STOP = "HARD_STOP"
    DEGRADE = "DEGRADE"
    DEFER = "DEFER"
    BYPASS = "BYPASS"


# ===========================================================================
# Layer 2 -- Leaf types with no internal deps
# (1.2.10, 1.2.13, 1.2.14, 1.2.15, 1.2.20 partial)
# ===========================================================================


@dataclass(frozen=True)
class AdapterError:
    """Structured error from port adapters.

    Adapters catch raw exceptions and wrap in AdapterError before raising.
    Services never see raw exceptions from ports.
    Consumed by ErrorRouter.route_error(AdapterError).

    Classification matrix (per orchestrator.mmd):
      Mailbox errors    -> RECOVERABLE (re-enqueue once)
      Fabric errors     -> DEGRADED (step fails, independent steps continue)
      Planner errors    -> DEGRADED (degrade HIGH to MEDIUM)
      StateRead errors  -> DEGRADED (use stale/empty context)
      DeltaEmit errors  -> RECOVERABLE (retry once, then silent drop)
      BridgeWrite errors-> RECOVERABLE (retry once, then silent drop)
      EventSub errors   -> RECOVERABLE (resubscribe)
    """

    severity: ErrorSeverity
    adapter_name: str
    operation: str
    error_code: str
    error_message: str
    original_exception: Optional[Exception] = None
    fallback_action: str = ""
    trace_id: str = ""


@dataclass(frozen=True)
class ErrorAction:
    """Decision returned by ErrorRouter.route_error() (Issue 2.1.7).

    Caller executes the returned action -- ErrorRouter is decision-only.

    Actions:
      RETRY    -- transient, re-attempt the operation (retry_count times).
      FALLBACK -- degrade to alternative path (e.g. HIGH -> MEDIUM).
      DEGRADE  -- partial failure, continue with fallback_value.
      ABORT    -- unrecoverable, stop execution.
    """

    action: str  # "RETRY" | "FALLBACK" | "DEGRADE" | "ABORT"
    retry_count: int = 0
    fallback_value: Optional[Any] = None
    reason: str = ""


@dataclass
class CompensationRecord:
    """Record of a saga compensation action.

    Mutable: status transitions during compensation execution.
    Status transitions: PENDING -> EXECUTED (success) or
                        PENDING -> FAILED -> DEAD_LETTERED.
    DEAD_LETTERED means compensation itself failed and was abandoned.

    Created by saga recovery in DAGExecutor._compensate() (2.2.5).
    Stored in AggregatedResult.compensations and IBridgeWritePort for K0 audit.
    """

    dag_id: str
    step_id: str
    compensation_capability: str
    compensation_params: Dict[str, Any] = field(default_factory=dict)
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "PENDING"
    initiated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error_detail: Optional[str] = None


@dataclass(frozen=True)
class MCPServerRegistration:
    """MCP server registration record.

    Tracks which MCP servers have been discovered and which capability_ids
    were registered into Fabric. Replaces old ConnectorHealthStatus (health
    monitoring moved to Fabric).

    Used by ConnectorLifecycleManager (5.1.3) for unregister/refresh ops.
    Orchestrator does NOT duplicate health/availability/CB tracking.
    """

    server_id: str
    server_type: str  # "local" (stdio) or "remote" (SSE/HTTP)
    endpoint: str
    registered_capabilities: List[str] = field(default_factory=list)
    registered_at: float = 0.0
    critical: bool = False


@dataclass(frozen=True)
class InterruptRequest:
    """Request to interrupt a running DAG.

    Delivery: arrives via IEventSubscriptionPort on topic
    k1.orchestration.cancel_request. OrchestratorService.handle_interrupt()
    sets DAGExecutor.interrupt_flag (atomic bool). DAGExecutor checks flag
    at per-step completion (cooperative; max latency = one step execution).

    interrupt_type values:
      CANCEL_DAG -- stop execution, compensate side-effects.
      PAUSE      -- V2 only, rejected with error in V1.
    """

    target_dag_id: Optional[str] = None
    interrupt_type: str = "CANCEL_DAG"
    reason: str = ""
    trace_id: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    _ALLOWED_TYPES = frozenset({"CANCEL_DAG", "PAUSE"})

    def __post_init__(self) -> None:
        if self.interrupt_type not in self._ALLOWED_TYPES:
            raise ValueError(
                f"interrupt_type '{self.interrupt_type}' not in " f"{self._ALLOWED_TYPES}"
            )
        if not self.trace_id:
            raise ValueError("trace_id is required")


@dataclass(frozen=True)
class TriggerSpec:
    """Workflow trigger specification (nested in WorkflowSaveRequest).

    Validation rules:
      CRON   -> schedule non-empty
      EVENT  -> event_topic non-empty
      MANUAL -> both schedule and event_topic are None
    """

    type: TriggerType
    schedule: Optional[str] = None
    timezone: Optional[str] = None
    event_topic: Optional[str] = None

    def __post_init__(self) -> None:
        if self.type == TriggerType.CRON and not self.schedule:
            raise ValueError("CRON trigger requires a schedule")
        if self.type == TriggerType.EVENT and not self.event_topic:
            raise ValueError("EVENT trigger requires an event_topic")
        if self.type == TriggerType.MANUAL:
            if self.schedule is not None or self.event_topic is not None:
                raise ValueError("MANUAL trigger must have schedule=None and event_topic=None")


@dataclass(frozen=True)
class ConditionExpr:
    """Conditional edge expression for ORCH-16.

    type: one of AND, OR, NOT, EQ, NEQ, GT, LT.
    path: references prior step result e.g. "s1.status", "s1.result.data.count".
    literal: comparison value for leaf operators (EQ, NEQ, GT, LT).
    operands: sub-expressions for composite operators (AND, OR, NOT).

    V1: simple comparisons only (no function calls, per ADR-1.1.11 Q10).
    """

    type: str  # AND, OR, NOT, EQ, NEQ, GT, LT
    operands: List[Any] = field(default_factory=list)
    path: Optional[str] = None
    literal: Optional[Any] = None


@dataclass(frozen=True)
class Discovery:
    """New information found during step execution.

    Triggers micro-replan evaluation via MicroReplanCheckpoint.
    """

    field: str
    value: Any = None
    source_step_id: str = ""


@dataclass(frozen=True)
class FailureContext:
    """Context for MicroReplanRequest when triggered by step failure.

    Planner needs to know what failed and any partial output.
    """

    step_id: str
    error_code: str
    error_message: str
    partial_result: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class SchemaResult:
    """Result from output schema validation (ORCH-15).

    suggestion is a human-readable hint for schema retry.
    """

    valid: bool
    errors: List[str] = field(default_factory=list)
    suggestion: Optional[str] = None


@dataclass(frozen=True)
class ValidationResult:
    """Result from ConstraintResolver validation.

    time_pressure=True when estimated critical-path duration exceeds
    the tier time budget (per BUDGET-1).
    """

    valid: bool
    issues: List[str] = field(default_factory=list)
    alternatives: Dict[str, str] = field(default_factory=dict)
    time_pressure: bool = False


@dataclass(frozen=True)
class CapabilityCheck:
    """Per-capability validation result from ConstraintResolver."""

    step_id: str
    capability: str
    exists: bool
    available: bool
    safety_band_ok: bool
    alternative: Optional[str] = None


@dataclass(frozen=True)
class ResolutionResult:
    """ConstraintResolver output after attempting auto-resolution."""

    resolved: bool
    substitutions: Dict[str, str] = field(default_factory=dict)
    remaining_issues: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RegistryEntry:
    """Capability registry entry from IFabricGatewayPort.query_registry().

    estimated_duration_ms used by BUDGET-1 time estimation.
    """

    name: str
    provider_type: str
    safety_band_min: str
    availability: str
    compensation_capability: Optional[str] = None
    estimated_duration_ms: Optional[int] = None


@dataclass(frozen=True)
class HILRequest:
    """Human-in-the-loop request emitted via IDeltaEmitPort.

    Surfaced by Concierge to the user.
    """

    request_id: str
    question: str
    options: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 120_000


@dataclass(frozen=True)
class PlanAck:
    """Immediate acknowledgment from Planner.

    status: ACCEPTED or REJECTED.
    """

    request_id: str
    status: str
    estimated_duration_ms: Optional[int] = None


@dataclass(frozen=True)
class TaskAck:
    """Immediate acknowledgment back to Concierge.

    status: ACCEPTED, DUPLICATE, or REJECTED_FULL.
    """

    envelope_id: str
    status: str
    estimated_duration_ms: Optional[int] = None


# ===========================================================================
# Layer 3 -- Core envelopes (1.2.1, 1.2.5, 1.2.18, 1.2.7)
# ===========================================================================


@dataclass(frozen=True)
class TaskEnvelope:
    """Inbound task envelope from Concierge.

    Created by Concierge DISPATCHING state, enqueued to IMailboxPort.
    Routed by OrchestratorService.process() -> route_task().

    Validation (__post_init__):
      - tier in {MEDIUM, HIGH} (LOW/CRISIS never reach Orchestrator)
      - intent non-empty
      - trace_id non-empty
      - if tier=MEDIUM: capabilities non-empty and len<=2 (ORCH-10)
      - if tier=HIGH: capabilities may be empty (Planner decides)

    Gotcha: params keyed by capability_name, e.g.
      {"tool.calendar.search": {"query": "..."}}
    Concierge pre-resolves per-capability params from user utterance.
    """

    intent: str
    trace_id: str
    caller_id: str = ""
    envelope_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context: Dict[str, Any] = field(default_factory=dict)
    tier: str = "MEDIUM"
    capabilities: List[str] = field(default_factory=list)
    params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30_000

    _VALID_TIERS = frozenset({Tier.MEDIUM.value, Tier.HIGH.value})

    def __post_init__(self) -> None:
        if self.tier not in self._VALID_TIERS:
            raise ValueError(f"tier '{self.tier}' not valid; expected one of {self._VALID_TIERS}")
        if not self.intent:
            raise ValueError("intent is required")
        if not self.trace_id:
            raise ValueError("trace_id is required")
        if self.tier == Tier.MEDIUM.value:
            if not self.capabilities:
                raise ValueError("MEDIUM tier requires non-empty capabilities list")
            if len(self.capabilities) > 2:
                raise ValueError(
                    f"MEDIUM tier allows max 2 capabilities, got "
                    f"{len(self.capabilities)} (ORCH-10)"
                )


@dataclass(frozen=True)
class StepResult:
    """Result of a single DAG step execution.

    Created by StepRunner.run() wrapping CapabilityResult + retry metadata.
    Stored in DAGExecutor.merged_results, embedded in AggregatedResult.

    Invariants:
      - COMPLETED -> result is not None and result.success is True
      - FAILED    -> error_detail is not None
      - CANCELLED or SKIPPED -> result is None

    V1 scope reduction: cost_usd, tokens_consumed, quality_retry REMOVED.
    """

    step_id: str
    capability_name: str
    status: StepStatus
    duration_ms: int = 0
    result: Optional[CapabilityResult] = None
    retry_attempts: int = 0
    schema_retry: bool = False
    error_detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "step_id": self.step_id,
            "capability_name": self.capability_name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "result": self.result.to_dict() if self.result else None,
            "retry_attempts": self.retry_attempts,
            "schema_retry": self.schema_retry,
            "error_detail": self.error_detail,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepResult":
        """Create StepResult from dictionary."""
        result_data = data.get("result")
        result = CapabilityResult.from_dict(result_data) if result_data else None
        return cls(
            step_id=data.get("step_id", ""),
            capability_name=data.get("capability_name", ""),
            status=StepStatus(data.get("status", "PENDING")),
            duration_ms=data.get("duration_ms", 0),
            result=result,
            retry_attempts=data.get("retry_attempts", 0),
            schema_retry=data.get("schema_retry", False),
            error_detail=data.get("error_detail"),
        )


@dataclass(frozen=True)
class PlanStep:
    """Orchestrator's 13-field PlanStep for DAG execution.

    Re-defined (not subclassed) from Fabric's 6-field PlanStep to avoid
    tight coupling. Map from Fabric PlanStep via from_fabric() classmethod.

    Fields 1-6: match Fabric PlanStep (id, capability, params, deps,
                prompt_template, tools_granted).
    Fields 7-13: Orchestrator extensions for DAG execution (output_schema,
                 condition, is_optional, has_side_effects, compensation,
                 timeout_ms, required_context).

    V1 scope: token_budget field REMOVED (no upstream data).

    Validation:
      - id non-empty
      - capability non-empty
      - timeout_ms > 0 if set
      - deps validated at CommittedPlan level (cross-step check)
    """

    # Fabric-aligned fields (1-6)
    id: str = ""
    capability: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    deps: List[str] = field(default_factory=list)
    prompt_template: Optional[str] = None
    tools_granted: Optional[List[str]] = None

    # Orchestrator extension fields (7-13)
    output_schema: Optional[Dict[str, Any]] = None
    condition: Optional[ConditionExpr] = None
    is_optional: bool = False
    has_side_effects: bool = False
    compensation: Optional[str] = None
    timeout_ms: Optional[int] = None
    required_context: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("PlanStep.id is required")
        if not self.capability:
            raise ValueError("PlanStep.capability is required")
        if self.timeout_ms is not None and self.timeout_ms <= 0:
            raise ValueError(f"PlanStep.timeout_ms must be > 0, got {self.timeout_ms}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event bus transport and WAL persistence."""
        result: Dict[str, Any] = {
            "id": self.id,
            "capability": self.capability,
        }
        if self.params:
            result["params"] = dict(self.params)
        if self.deps:
            result["deps"] = list(self.deps)
        if self.prompt_template is not None:
            result["prompt_template"] = self.prompt_template
        if self.tools_granted is not None:
            result["tools_granted"] = list(self.tools_granted)
        if self.output_schema is not None:
            result["output_schema"] = self.output_schema
        if self.condition is not None:
            result["condition"] = {
                "type": self.condition.type,
                "operands": self.condition.operands,
                "path": self.condition.path,
                "literal": self.condition.literal,
            }
        result["is_optional"] = self.is_optional
        result["has_side_effects"] = self.has_side_effects
        if self.compensation is not None:
            result["compensation"] = self.compensation
        if self.timeout_ms is not None:
            result["timeout_ms"] = self.timeout_ms
        if self.required_context is not None:
            result["required_context"] = list(self.required_context)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanStep":
        """Create PlanStep from dictionary."""
        condition_data = data.get("condition")
        condition = (
            ConditionExpr(
                type=condition_data.get("type", "EQ"),
                operands=condition_data.get("operands", []),
                path=condition_data.get("path"),
                literal=condition_data.get("literal"),
            )
            if condition_data
            else None
        )
        return cls(
            id=data.get("id", ""),
            capability=data.get("capability", ""),
            params=data.get("params", {}),
            deps=data.get("deps", []),
            prompt_template=data.get("prompt_template"),
            tools_granted=data.get("tools_granted"),
            output_schema=data.get("output_schema"),
            condition=condition,
            is_optional=data.get("is_optional", False),
            has_side_effects=data.get("has_side_effects", False),
            compensation=data.get("compensation"),
            timeout_ms=data.get("timeout_ms"),
            required_context=data.get("required_context"),
        )

    @classmethod
    def from_fabric(
        cls,
        fabric_step: FabricPlanStep,
        **extensions: Any,
    ) -> "PlanStep":
        """Map from Fabric's 6-field PlanStep with Orchestrator extensions.

        Args:
            fabric_step: Fabric PlanStep (id, capability, prompt_template,
                         params, tools_granted, deps).
            **extensions: Orchestrator-specific fields (output_schema,
                          condition, is_optional, has_side_effects,
                          compensation, timeout_ms, required_context).
        """
        return cls(
            id=fabric_step.id,
            capability=fabric_step.capability,
            params=dict(fabric_step.params) if fabric_step.params else {},
            deps=list(fabric_step.deps) if fabric_step.deps else [],
            prompt_template=fabric_step.prompt_template,
            tools_granted=(list(fabric_step.tools_granted) if fabric_step.tools_granted else None),
            output_schema=extensions.get("output_schema"),
            condition=extensions.get("condition"),
            is_optional=extensions.get("is_optional", False),
            has_side_effects=extensions.get("has_side_effects", False),
            compensation=extensions.get("compensation"),
            timeout_ms=extensions.get("timeout_ms"),
            required_context=extensions.get("required_context"),
        )


@dataclass
class Wave:
    """A set of independent steps executable in parallel within a DAG.

    Mutable: resolved_params populated during execution by ParamResolver.
    Internal only -- never serialized or sent over event bus.

    Invariant: all steps in a wave have zero unresolved dependencies
    (all deps completed in prior waves). wave_index is 0-based.
    """

    wave_index: int
    steps: List[PlanStep] = field(default_factory=list)
    resolved_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ===========================================================================
# Layer 4 -- Plan & result types (1.2.2, 1.2.3, 1.2.4, 1.2.8, 1.2.20 partial)
# ===========================================================================


@dataclass(frozen=True)
class WaveResult:
    """Aggregated per-wave result for DAGExecutor internal tracking.

    V1 scope reduction: tokens_consumed and cost_usd fields REMOVED.
    """

    wave_index: int
    step_results: List[StepResult] = field(default_factory=list)
    duration_ms: int = 0


@dataclass(frozen=True)
class PlanRequest:
    """Orchestrator -> Planner plan request for HIGH tier tasks.

    Derived from TaskEnvelope: dispatch_high() builds PlanRequest from
    envelope.intent, envelope.constraints, and fresh StateRead snapshot.

    request_id is NEW (not envelope_id) because one envelope could be
    retried with a new plan request.

    Key contract: Planner receives this via IPlannerPort.request_plan()
    and echoes request_id back in CommittedPlan.request_id for
    PendingPlanContext correlation.

    V1: context uses Fabric SessionSnapshot directly (no ContextSnapshot wrapper).
    """

    intent: str
    trace_id: str
    context: Optional[SessionSnapshot] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    constraints: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 45_000

    def __post_init__(self) -> None:
        if not self.intent:
            raise ValueError("PlanRequest.intent is required")
        if not self.trace_id:
            raise ValueError("PlanRequest.trace_id is required")


@dataclass(frozen=True)
class CommittedPlan:
    """Planner -> Orchestrator: validated DAG ready for execution.

    Planner Stage 4 (COMMIT) produces this. Orchestrator receive_plan()
    consumes it. The request_id MUST match the original PlanRequest.request_id
    for PendingPlanContext correlation (ADR-1.1.12 / SPEC-2).

    V1 scope reduction: token_budget_max and cost_budget_max_usd REMOVED.

    Validation:
      - plan_id, request_id non-empty
      - steps non-empty
      - dependencies keys must be subset of step IDs
      - no cycles in dependency graph (defensive validation)
    """

    plan_id: str
    request_id: str
    intent: str
    steps: List[PlanStep]
    trace_id: str
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    estimated_duration_ms: Optional[int] = None
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ValueError("CommittedPlan.plan_id is required")
        if not self.request_id:
            raise ValueError("CommittedPlan.request_id is required")
        if not self.steps:
            raise ValueError("CommittedPlan.steps must be non-empty")

        step_ids = {s.id for s in self.steps}
        for dep_step, dep_list in self.dependencies.items():
            if dep_step not in step_ids:
                raise ValueError(f"dependencies key '{dep_step}' not in step IDs {step_ids}")
            for dep in dep_list:
                if dep not in step_ids:
                    raise ValueError(
                        f"dependency '{dep}' of step '{dep_step}' not in " f"step IDs {step_ids}"
                    )

        # Cycle detection (Kahn's algorithm)
        self._check_acyclic(step_ids)

    def _check_acyclic(self, step_ids: set) -> None:
        """Verify dependency graph is acyclic using Kahn's algorithm."""
        in_degree: Dict[str, int] = {sid: 0 for sid in step_ids}
        for deps in self.dependencies.values():
            for _ in deps:
                pass  # deps are counted below via iteration
        # Build adjacency from dependencies: dep -> dependent
        adj: Dict[str, List[str]] = {sid: [] for sid in step_ids}
        for step_id, deps in self.dependencies.items():
            for dep in deps:
                adj[dep].append(step_id)
                in_degree[step_id] = in_degree.get(step_id, 0) + 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop(0)
            visited += 1
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(step_ids):
            raise ValueError("CommittedPlan dependency graph contains a cycle")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event bus transport."""
        return {
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "intent": self.intent,
            "steps": [s.to_dict() for s in self.steps],
            "dependencies": {k: list(v) for k, v in self.dependencies.items()},
            "estimated_duration_ms": self.estimated_duration_ms,
            "created_at": self.created_at,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommittedPlan":
        """Create CommittedPlan from dictionary."""
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            plan_id=data.get("plan_id", ""),
            request_id=data.get("request_id", ""),
            intent=data.get("intent", ""),
            steps=steps,
            dependencies=data.get("dependencies", {}),
            estimated_duration_ms=data.get("estimated_duration_ms"),
            created_at=data.get("created_at", 0.0),
            trace_id=data.get("trace_id", ""),
        )


@dataclass(frozen=True)
class AggregatedResult:
    """Final result of task processing (MEDIUM or HIGH tier).

    Computed: success = (failed == 0 and cancelled == 0).

    V1 scope reduction: total_tokens_consumed, total_cost_usd,
    budget_utilization REMOVED.

    Factory methods:
      from_medium() -- for MEDIUM tier (no plan, 1-2 steps).
      from_dag()    -- for HIGH tier (plan + DAG execution).

    Serialization: to_dict() for event payload on
    k1.orchestration.dag.completed.v1.
    """

    total_steps: int
    completed: int
    failed: int
    cancelled: int
    skipped: int
    step_results: List[StepResult]
    success: bool
    duration_ms: int
    trace_id: str
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: Optional[str] = None
    compensations: List[CompensationRecord] = field(default_factory=list)

    @classmethod
    def from_medium(
        cls,
        step_results: List[StepResult],
        trace_id: str,
        duration_ms: int = 0,
    ) -> "AggregatedResult":
        """Create result for MEDIUM tier (no plan, 1-2 steps)."""
        completed = sum(1 for r in step_results if r.status == StepStatus.COMPLETED)
        failed = sum(1 for r in step_results if r.status == StepStatus.FAILED)
        cancelled = sum(1 for r in step_results if r.status == StepStatus.CANCELLED)
        skipped = sum(1 for r in step_results if r.status == StepStatus.SKIPPED)
        return cls(
            total_steps=len(step_results),
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            skipped=skipped,
            step_results=step_results,
            success=(failed == 0 and cancelled == 0),
            duration_ms=duration_ms,
            trace_id=trace_id,
            plan_id=None,
        )

    @classmethod
    def from_dag(
        cls,
        plan_id: str,
        step_results: List[StepResult],
        compensations: List[CompensationRecord],
        trace_id: str,
        duration_ms: int = 0,
    ) -> "AggregatedResult":
        """Create result for HIGH tier (plan + DAG execution)."""
        completed = sum(1 for r in step_results if r.status == StepStatus.COMPLETED)
        failed = sum(1 for r in step_results if r.status == StepStatus.FAILED)
        cancelled = sum(1 for r in step_results if r.status == StepStatus.CANCELLED)
        skipped = sum(1 for r in step_results if r.status == StepStatus.SKIPPED)
        return cls(
            total_steps=len(step_results),
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            skipped=skipped,
            step_results=step_results,
            success=(failed == 0 and cancelled == 0),
            duration_ms=duration_ms,
            trace_id=trace_id,
            plan_id=plan_id,
            compensations=compensations,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event payload."""
        return {
            "result_id": self.result_id,
            "plan_id": self.plan_id,
            "total_steps": self.total_steps,
            "completed": self.completed,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "skipped": self.skipped,
            "step_results": [r.to_dict() for r in self.step_results],
            "compensations": [
                {
                    "record_id": c.record_id,
                    "dag_id": c.dag_id,
                    "step_id": c.step_id,
                    "compensation_capability": c.compensation_capability,
                    "status": c.status,
                    "error_detail": c.error_detail,
                }
                for c in self.compensations
            ],
            "success": self.success,
            "duration_ms": self.duration_ms,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True)
class MicroReplanRequest:
    """DAGExecutor -> Planner mid-execution replan request.

    Synchronous (10s timeout). Max 1 micro-replan per DAG (ORCH-13).
    MicroReplanCheckpoint (3.2.5) tracks replan_count and rejects if > 0.

    Contract: Planner receives completed_results, discoveries,
    remaining_steps, and failure_context. Returns a new CommittedPlan
    with replacement steps.
    """

    original_plan_id: str
    completed_results: Dict[str, StepResult]
    remaining_steps: List[PlanStep]
    trace_id: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    discoveries: List[Discovery] = field(default_factory=list)
    failure_context: Optional[FailureContext] = None

    def __post_init__(self) -> None:
        if not self.original_plan_id:
            raise ValueError("MicroReplanRequest.original_plan_id is required")
        if not self.remaining_steps:
            raise ValueError("MicroReplanRequest.remaining_steps must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Planner transport."""
        result: Dict[str, Any] = {
            "request_id": self.request_id,
            "original_plan_id": self.original_plan_id,
            "completed_results": {k: v.to_dict() for k, v in self.completed_results.items()},
            "remaining_steps": [s.to_dict() for s in self.remaining_steps],
            "trace_id": self.trace_id,
        }
        if self.discoveries:
            result["discoveries"] = [
                {
                    "field": d.field,
                    "value": d.value,
                    "source_step_id": d.source_step_id,
                }
                for d in self.discoveries
            ]
        if self.failure_context:
            result["failure_context"] = {
                "step_id": self.failure_context.step_id,
                "error_code": self.failure_context.error_code,
                "error_message": self.failure_context.error_message,
                "partial_result": self.failure_context.partial_result,
            }
        return result


# ===========================================================================
# Layer 5 -- Workflow types (1.2.6, 1.2.11, 1.2.12)
# ===========================================================================


@dataclass(frozen=True)
class WorkflowRunRequest:
    """Request to execute a saved workflow.

    Created by WorkflowScheduler (cron/event) or Concierge (manual).
    Routed via OrchestratorService.process() -> dispatch_workflow().

    Validation:
      - workflow_id non-empty
      - trigger_type in TriggerType enum (validated by type annotation)
    """

    workflow_id: str
    version: str
    trigger_type: TriggerType
    trace_id: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_context: Dict[str, Any] = field(default_factory=dict)
    param_overrides: Dict[str, Any] = field(default_factory=dict)
    priority: str = "INTERACTIVE"

    def __post_init__(self) -> None:
        if not self.workflow_id:
            raise ValueError("WorkflowRunRequest.workflow_id is required")


@dataclass(frozen=True)
class WorkflowSaveRequest:
    """Request to save a committed plan as a reusable workflow.

    Created by Concierge when user says "save this as a workflow" or
    "do this every Monday".

    Validation:
      - committed_plan_id non-empty
      - workflow_name non-empty
      - trigger_spec is valid TriggerSpec
    """

    committed_plan_id: str
    workflow_name: str
    trigger_spec: TriggerSpec
    trace_id: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.committed_plan_id:
            raise ValueError("WorkflowSaveRequest.committed_plan_id is required")
        if not self.workflow_name:
            raise ValueError("WorkflowSaveRequest.workflow_name is required")


@dataclass
class ProactiveGap:
    """Detected gap in a saved workflow due to contract/capability changes.

    Mutable: status transitions PENDING -> ASKED -> RESOLVED/AUTO_RESOLVED.

    gap_type values:
      SCHEMA_DRIFT       -- field added/removed/changed.
      CAPABILITY_REMOVED -- capability no longer in registry.
      PERMISSION_CHANGE  -- safety_band_min changed.

    Lifecycle:
      GapDetector creates with PENDING -> surfaces to user (ASKED) ->
      user responds (RESOLVED) or auto-filled (AUTO_RESOLVED).
    Persistence: stored via IWorkflowStoragePort.
    """

    workflow_id: str
    gap_type: str
    affected_step_id: str
    capability_name: str
    old_contract_version: str
    new_contract_version: str
    description: str
    justification: str
    gap_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    detected_at: float = field(default_factory=time.time)
    question: Optional[str] = None
    status: ProactiveGapStatus = ProactiveGapStatus.PENDING
    resolved_value: Optional[str] = None


# ===========================================================================
# Layer 6 -- Context types (1.2.19, 1.2.21)
# ===========================================================================


@dataclass
class ProcessingContext:
    """Request-scoped correlation context carried through all service calls.

    Created at OrchestratorService.process() entry point.
    Passed as parameter to every internal method for trace correlation,
    metrics attribution, and structured logging.

    Identity fields (trace_id, request_id, tier) NEVER change after creation.
    Tracking fields (dag_id, current_wave, current_step_id) updated in-place.

    NOT serialized -- never persisted to WAL or sent over event bus.
    NOT stored in pending dicts -- only trace_id is extracted into
    PendingPlanContext.trace_id.

    Thread-local equivalent: in asyncio, passed explicitly (not via
    contextvars) to maintain visibility.

    Reference: Schema Whiteboard Section 1.
    """

    trace_id: str
    request_id: str
    tier: str
    created_at: float = field(default_factory=time.time)
    deadline_ms: Optional[int] = None

    # Execution tracking (populated during DAG)
    dag_id: Optional[str] = None
    workflow_id: Optional[str] = None
    parent_trace_id: Optional[str] = None
    current_wave: Optional[int] = None
    current_step_id: Optional[str] = None

    # Session context
    session_id: Optional[str] = None
    user_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("ProcessingContext.trace_id is required")
        if not self.request_id:
            raise ValueError("ProcessingContext.request_id is required")


@dataclass
class PendingPlanContext:
    """Parked context for a HIGH tier task awaiting Planner response.

    Stored in OrchestratorService.pending_plans dict keyed by request_id.
    Created by dispatch_high(), consumed by receive_plan().
    Timeout reaper expires entries where time.time()-created_at > timeout_ms/1000.
    """

    request_id: str
    task_envelope: TaskEnvelope
    state_snapshot: SessionSnapshot
    created_at: float = field(default_factory=time.time)
    timeout_ms: int = 45_000


@dataclass
class PendingHILContext:
    """Parked DAG state awaiting human-in-the-loop response.

    Stored in OrchestratorService.pending_hil dict keyed by request_id.

    timeout_fallback:
      "CONTINUE"      -- for user override HIL (silence = proceed).
      "GRACEFUL_FAIL"  -- for constraint HIL (silence = cannot proceed safely).
    """

    request_id: str
    dag_execution_id: str
    current_wave_index: int
    completed_waves: List[WaveResult]
    remaining_waves: List[Wave]
    question: str
    options: List[str]
    timeout_fallback: str
    created_at: float = field(default_factory=time.time)
    timeout_ms: int = 120_000


# ===========================================================================
# Layer 7 -- CB, Guard, Admin types (1.2.23, 1.2.24, 1.2.25)
# ===========================================================================


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for a circuit breaker instance.

    Orchestrator owns ONLY CB_PLANNER. CB_FABRIC, CB_MCP, CB_BRIDGE
    are owned by Concierge/Fabric.
    Reference: Schema Whiteboard Section 7.
    """

    name: str
    failure_threshold: int
    reset_timeout_ms: int
    half_open_max_probes: int = 1


@dataclass
class CircuitBreakerState:
    """Mutable state of a circuit breaker instance.

    State machine:
      CLOSED   -[failure_count >= threshold]-> OPEN
      OPEN     -[recovery_timeout elapsed]->   HALF_OPEN
      HALF_OPEN -[probe succeeds]->            CLOSED
      HALF_OPEN -[probe fails]->               OPEN (reset recovery timer)

    Reference: Schema Whiteboard Section 7.
    """

    config: CircuitBreakerConfig
    state: str = "CLOSED"
    failure_count: int = 0
    last_failure_at: Optional[float] = None
    last_success_at: Optional[float] = None
    opened_at: Optional[float] = None
    _half_open_probes: int = 0

    def record_success(self) -> None:
        """Record a successful call. Resets to CLOSED."""
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_success_at = time.time()
        self.opened_at = None
        self._half_open_probes = 0

    def record_failure(self) -> None:
        """Record a failed call. May trip to OPEN."""
        self.failure_count += 1
        self.last_failure_at = time.time()
        if self.failure_count >= self.config.failure_threshold:
            self.state = "OPEN"
            self.opened_at = time.time()

    def should_allow_request(self) -> bool:
        """Check if a request should be allowed through the breaker."""
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if self.opened_at is not None and (
                time.time() - self.opened_at >= self.config.reset_timeout_ms / 1000
            ):
                self.state = "HALF_OPEN"
                self._half_open_probes = 0
                return True
            return False
        if self.state == "HALF_OPEN":
            if self._half_open_probes < self.config.half_open_max_probes:
                self._half_open_probes += 1
                return True
            return False
        return False

    def check_reset_timeout(self) -> bool:
        """Check if recovery timeout has elapsed for OPEN state."""
        if self.state != "OPEN" or self.opened_at is None:
            return False
        return time.time() - self.opened_at >= self.config.reset_timeout_ms / 1000


@dataclass(frozen=True)
class GuardDecision:
    """Decision returned by a guard in the guard pipeline.

    Per WB Section 8: each guard returns a GuardDecision; pipeline
    short-circuits on first REJECT.
    """

    guard_name: str
    action: GuardAction
    reason: str
    degraded_to: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# --- Guard Protocol classes (4 total) ---


@runtime_checkable
class PreDispatchGuard(Protocol):
    """Guard evaluated BEFORE dispatch routing (G0-G4).

    Sync check -- used by ConcurrencyGuard, TierGuard, etc.
    """

    def check(self, envelope: TaskEnvelope, ctx: ProcessingContext) -> GuardDecision: ...


@runtime_checkable
class IPreWaveGuard(Protocol):
    """Guard evaluated BEFORE each wave (G1 ConditionalEdgeEvaluator).

    Async evaluate -- may need to read prior step results.
    """

    async def evaluate_pre_wave(
        self, wave: Wave, ctx: ProcessingContext
    ) -> List[GuardDecision]: ...


@runtime_checkable
class IPostStepGuard(Protocol):
    """Guard evaluated AFTER each step (G2 OutputSchemaGuard).

    Async evaluate -- may trigger schema retry.
    """

    async def evaluate_post_step(
        self, step: PlanStep, result: StepResult, ctx: ProcessingContext
    ) -> GuardDecision: ...


@runtime_checkable
class IPostWaveGuard(Protocol):
    """Guard evaluated AFTER each wave (G3-G5).

    Async evaluate -- ExecutionMonitor, MicroReplanCheckpoint, SafetyBandReRead.
    """

    async def evaluate_post_wave(
        self, wave_result: WaveResult, ctx: ProcessingContext
    ) -> GuardDecision: ...


# --- Admin types (1.2.25) ---


@dataclass(frozen=True)
class HealthStatus:
    """Orchestrator health status for admin/monitoring.

    status values:
      HEALTHY   -- CB_PLANNER closed, mailbox < 80%.
      DEGRADED  -- CB_PLANNER open/half-open or consumed CB issues.
      UNHEALTHY -- CB_PLANNER open AND mailbox at capacity.

    Reference: Schema Whiteboard Section 5/6.
    """

    status: str
    uptime_ms: int
    active_dags: int
    mailbox_depth: int
    circuit_breakers: Dict[str, str] = field(default_factory=dict)
    last_error: Optional[str] = None


@dataclass(frozen=True)
class ActiveDAGInfo:
    """Information about the currently active DAG for admin visibility.

    Reference: Schema Whiteboard Section 5.
    """

    dag_id: str
    plan_id: str
    current_wave: int
    total_waves: int
    steps_completed: int
    steps_failed: int
    started_at: float
    trace_id: str


@dataclass(frozen=True)
class DrainResult:
    """Result of mailbox drain operation for graceful shutdown.

    drained=True when active_dags_remaining == 0 and timeout not reached.

    Reference: Schema Whiteboard Section 5.
    """

    drained: bool
    active_dags_remaining: int
    timeout_reached: bool
    duration_ms: int
