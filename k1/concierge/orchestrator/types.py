"""
k1.concierge.orchestrator.types -- Concierge-local orchestrator types.

V2 Design Ref: Section 11.2.1 (ComplexityTier, TaskEnvelope, Budget)
V2 Design Ref: Section 11.3 (OrchestratorStub types: CapabilityRequest, CapabilityResult)
V2 Design Ref: Section 11.4.2 (PlanRequest, CommittedPlan, PlanStep)
V2 Design Ref: Section 11.7 (AggregatedResult -- universal result type)

ARCHITECTURE NOTE (E-0.5.5 / I-0.5.5.1):
    These types are the Concierge-internal orchestrator contract layer.
    They are intentionally SEPARATE from k1.orchestrator.types because:

    1. Field differences -- POC TaskEnvelope uses task_id, budget: Budget,
       tier: ComplexityTier, session_id. Production uses envelope_id,
       timeout_ms (no Budget class), tier: str, caller_id, capabilities,
       params, constraints. NOT a drop-in replacement.

    2. Simplified Fabric types -- POC CapabilityRequest uses `name` (production
       uses `capability_name`). POC CapabilityResult.error is str (production
       is Optional[ErrorInfo]). POC CapabilityResult has capability_name
       (production does not).

    3. Factory method differences -- POC AggregatedResult.from_medium() takes
       a single CapabilityResult. Production takes List[StepResult]. POC has
       from_multi_step(); production does not.

    4. POC-only types -- Budget and CannedResponse have NO production
       equivalents.

    The boundary translation adapter (POCFabricGatewayAdapter in
    k1/concierge/kernel/bootstrap.py) correctly bridges POC→production
    types at the dispatch boundary.

    Production type locations for reference:
        TaskEnvelope      -> k1.orchestrator.types
        StepResult        -> k1.orchestrator.types (status: StepStatus enum)
        AggregatedResult  -> k1.orchestrator.types (from_medium takes List[StepResult])
        PlanRequest       -> k1.orchestrator.types (trace_id required, context: SessionSnapshot)
        PlanStep          -> k1.orchestrator.types (14 fields, id not step_id)
        CommittedPlan     -> k1.orchestrator.types (intent + trace_id required)
        CapabilityRequest -> k1.fabric.types (capability_name, 16 fields)
        CapabilityResult  -> k1.fabric.types (error: ErrorInfo, no capability_name)
        Budget            -> (no production equivalent)
        CannedResponse    -> (no production equivalent)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from k1.concierge.config import get_config
from k1.concierge.task.complexity import ComplexityTier

# =========================================================================
# Budget -- execution constraints per tier
# =========================================================================


@dataclass(frozen=True)
class Budget:
    """Execution budget constraints.

    V2 Design Ref: Section 11.2.1

    MEDIUM tier: max_fabric_calls=2, max_planner_tokens=0
    HIGH tier: max_fabric_calls=10, max_planner_tokens=3500

    Production reference: k1/orchestrator/types.py TaskEnvelope.timeout_ms
    provides a similar per-envelope budget. The POC uses a dedicated Budget
    dataclass as specified in the design doc.

    The default timeout_ms reads from config
    (orchestrator.default_budget_timeout_ms).
    """

    max_fabric_calls: int = 2
    max_planner_tokens: int = 0
    timeout_ms: int = 0  # 0 = sentinel, resolved in __post_init__

    def __post_init__(self) -> None:
        if self.timeout_ms == 0:
            object.__setattr__(
                self, "timeout_ms", get_config().orchestrator.default_budget_timeout_ms
            )
        if self.max_fabric_calls < 0:
            raise ValueError(f"Budget.max_fabric_calls must be >= 0, got {self.max_fabric_calls}")
        if self.max_planner_tokens < 0:
            raise ValueError(
                f"Budget.max_planner_tokens must be >= 0, got {self.max_planner_tokens}"
            )
        if self.timeout_ms <= 0:
            raise ValueError(f"Budget.timeout_ms must be > 0, got {self.timeout_ms}")


# =========================================================================
# TaskEnvelope -- task wrapper routed to Orchestrator (MEDIUM/HIGH)
# =========================================================================


@dataclass(frozen=True)
class TaskEnvelope:
    """Wrapper for tasks routed to the Orchestrator (MEDIUM/HIGH).

    V2 Design Ref: Section 11.2.1

    Production reference: k1/orchestrator/types.py TaskEnvelope (frozen=True,
    __post_init__ validation, tier restricted to MEDIUM/HIGH).

    Invariants:
      - intent must be non-empty
      - tier must be MEDIUM or HIGH (LOW tasks bypass the Orchestrator)
      - trace_id is auto-generated if not provided
      - task_id is auto-generated with "task-" prefix

    MEDIUM tier envelopes have Budget(max_fabric_calls=2).
    HIGH tier envelopes have Budget(max_fabric_calls=10, max_planner_tokens=3500).
    """

    intent: str
    task_id: str = field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    context: dict = field(default_factory=dict)
    tier: ComplexityTier = ComplexityTier.MEDIUM
    budget: Budget = field(default_factory=Budget)
    session_id: str = ""
    trace_id: str = field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:8]}")

    def __post_init__(self) -> None:
        if not self.intent:
            raise ValueError("TaskEnvelope.intent is required and must be non-empty")
        if self.tier == ComplexityTier.LOW:
            raise ValueError(
                "TaskEnvelope.tier must be MEDIUM or HIGH. "
                "LOW tier tasks bypass the Orchestrator entirely."
            )


# =========================================================================
# CapabilityRequest / CapabilityResult -- Fabric interaction types
# =========================================================================


@dataclass(frozen=True)
class CapabilityRequest:
    """Request to execute a capability via the Fabric gateway.

    V2 Design Ref: Section 11.3 (OrchestratorStub step 3)

    Production reference: k1/fabric/types.py CapabilityRequest.
    POC version is self-contained -- no k1.fabric imports.
    """

    name: str
    params: dict = field(default_factory=dict)
    session_id: str = ""
    trace_id: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("CapabilityRequest.name is required")


@dataclass(frozen=True)
class CapabilityResult:
    """Result from a Fabric capability execution.

    V2 Design Ref: Section 11.3 (OrchestratorStub step 4-5)

    Production reference: k1/fabric/types.py CapabilityResult.
    POC version is self-contained.
    """

    success: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    capability_name: str = ""
    duration_ms: int = 0


# =========================================================================
# StepResult -- individual step outcome (used in AggregatedResult)
# =========================================================================


@dataclass(frozen=True)
class StepResult:
    """Result of a single execution step.

    Production reference: k1/orchestrator/types.py StepResult (frozen=True,
    status enum, to_dict/from_dict methods).

    POC uses string status for simplicity:
        COMPLETED, FAILED, CANCELLED, SKIPPED
    """

    step_id: str
    capability_name: str
    status: str  # COMPLETED | FAILED | CANCELLED | SKIPPED
    duration_ms: int = 0
    result: dict = field(default_factory=dict)
    error_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for event payload."""
        return {
            "step_id": self.step_id,
            "capability_name": self.capability_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "result": self.result,
            "error_detail": self.error_detail,
        }


# =========================================================================
# AggregatedResult -- universal result type for all tiers
# =========================================================================


@dataclass(frozen=True)
class AggregatedResult:
    """Universal result type. All tiers (LOW, MEDIUM, HIGH) produce this.

    V2 Design Ref: Section 11.7 (invariant 6: all tiers emit same result event)

    Production reference: k1/orchestrator/types.py AggregatedResult (frozen=True,
    from_medium() and from_dag() factory classmethods, to_dict method).

    The FSM does not distinguish between tiers at result time. It receives
    AggregatedResult via k1.orchestration.dag.completed and transitions to
    COMPANIONING -> DELIVERING.
    """

    total_steps: int
    completed: int
    failed: int
    results: list = field(default_factory=list)
    success: bool = True
    cancelled: int = 0
    skipped: int = 0
    step_results: list = field(default_factory=list)
    duration_ms: int = 0
    trace_id: str = ""
    result_id: str = field(default_factory=lambda: f"res-{uuid.uuid4().hex[:8]}")
    plan_id: Optional[str] = None

    @classmethod
    def from_medium(
        cls,
        capability_result: CapabilityResult,
        trace_id: str = "",
        duration_ms: int = 0,
    ) -> AggregatedResult:
        """Create result for MEDIUM tier (single Fabric call).

        Production reference: k1/orchestrator/types.py AggregatedResult.from_medium()
        """
        step_result = StepResult(
            step_id=f"step-{uuid.uuid4().hex[:8]}",
            capability_name=capability_result.capability_name,
            status="COMPLETED" if capability_result.success else "FAILED",
            duration_ms=capability_result.duration_ms,
            result=capability_result.data if capability_result.success else {},
            error_detail=capability_result.error if not capability_result.success else "",
        )
        return cls(
            total_steps=1,
            completed=1 if capability_result.success else 0,
            failed=0 if capability_result.success else 1,
            results=[capability_result],
            success=capability_result.success,
            step_results=[step_result],
            duration_ms=duration_ms,
            trace_id=trace_id,
        )

    @classmethod
    def from_multi_step(
        cls,
        capability_results: list[CapabilityResult],
        trace_id: str = "",
        duration_ms: int = 0,
    ) -> AggregatedResult:
        """Create result for MEDIUM tier with multiple Fabric calls (max 2)."""
        step_results = []
        for i, cr in enumerate(capability_results):
            step_results.append(
                StepResult(
                    step_id=f"step-{i}",
                    capability_name=cr.capability_name,
                    status="COMPLETED" if cr.success else "FAILED",
                    duration_ms=cr.duration_ms,
                    result=cr.data if cr.success else {},
                    error_detail=cr.error if not cr.success else "",
                )
            )
        completed = sum(1 for r in capability_results if r.success)
        failed = sum(1 for r in capability_results if not r.success)
        return cls(
            total_steps=len(capability_results),
            completed=completed,
            failed=failed,
            results=list(capability_results),
            success=(failed == 0),
            step_results=step_results,
            duration_ms=duration_ms,
            trace_id=trace_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event payload."""
        return {
            "result_id": self.result_id,
            "plan_id": self.plan_id,
            "total_steps": self.total_steps,
            "completed": self.completed,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "skipped": self.skipped,
            "step_results": [
                r.to_dict() if hasattr(r, "to_dict") else r for r in self.step_results
            ],
            "success": self.success,
            "duration_ms": self.duration_ms,
            "trace_id": self.trace_id,
        }


# =========================================================================
# CannedResponse -- last-resort fallback when all tiers fail
# =========================================================================


@dataclass(frozen=True)
class CannedResponse:
    """Fallback response when all circuit breakers are open.

    V2 Design Ref: Section 11.6 (tier degradation cascade)

    When CB_FABRIC is open, the system cannot execute ANY capability.
    The only option is a canned response to maintain user experience.
    """

    text: str = "I'm having trouble right now. Could you try again in a moment?"
    reason: str = ""


# =========================================================================
# HIGH Tier Types (interface only -- deferred)
# =========================================================================


@dataclass(frozen=True)
class PlanRequest:
    """Request from Orchestrator to Planner (HIGH tier only).

    V2 Design Ref: Section 11.4.2

    Production reference: k1/orchestrator/types.py PlanRequest (frozen=True,
    intent and trace_id required, __post_init__ validation).

    POC: interface only. Not used in MEDIUM tier execution.
    """

    intent: str
    request_id: str = field(default_factory=lambda: f"preq-{uuid.uuid4().hex[:8]}")
    context: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)
    budget: Budget = field(
        default_factory=lambda: Budget(max_fabric_calls=10, max_planner_tokens=3500)
    )
    trace_id: str = field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:8]}")

    def __post_init__(self) -> None:
        if not self.intent:
            raise ValueError("PlanRequest.intent is required")


@dataclass(frozen=True)
class PlanStep:
    """Single step in a committed plan.

    V2 Design Ref: Section 11.4.2

    Production reference: k1/orchestrator/types.py PlanStep (frozen=True,
    14 fields, from_fabric() classmethod).

    POC: interface only. Defines the 8 core fields from design doc.
    """

    step_id: str
    capability: str
    params: dict = field(default_factory=dict)
    has_side_effects: bool = False
    compensation: Optional[str] = None
    timeout_ms: int = 30_000
    required_context: list = field(default_factory=list)
    safety_band_min: str = "GREEN"

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ValueError("PlanStep.step_id is required")
        if not self.capability:
            raise ValueError("PlanStep.capability is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "step_id": self.step_id,
            "capability": self.capability,
            "params": self.params,
            "has_side_effects": self.has_side_effects,
            "compensation": self.compensation,
            "timeout_ms": self.timeout_ms,
            "required_context": self.required_context,
            "safety_band_min": self.safety_band_min,
        }


@dataclass(frozen=True)
class CommittedPlan:
    """Planner output after 4-stage pipeline.

    V2 Design Ref: Section 11.4.2

    Production reference: k1/orchestrator/types.py CommittedPlan (frozen=True,
    cycle detection in __post_init__).

    POC: interface only. Includes cycle detection per production pattern.
    """

    plan_id: str
    request_id: str
    steps: list = field(default_factory=list)  # list[PlanStep]
    dependencies: dict = field(default_factory=dict)  # step_id -> [dep_step_ids]
    created_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ValueError("CommittedPlan.plan_id is required")
        if not self.request_id:
            raise ValueError("CommittedPlan.request_id is required")
        # Cycle detection (per production pattern)
        self._detect_cycles()

    def _detect_cycles(self) -> None:
        """Detect dependency cycles using DFS. Raises ValueError if found."""
        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(node: str) -> None:
            if node in in_stack:
                raise ValueError(f"CommittedPlan contains dependency cycle involving step '{node}'")
            if node in visited:
                return
            visited.add(node)
            in_stack.add(node)
            for dep in self.dependencies.get(node, []):
                dfs(dep)
            in_stack.discard(node)

        for step_id in self.dependencies:
            dfs(step_id)
