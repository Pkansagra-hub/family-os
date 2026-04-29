"""Planner-internal types [F05].

Types that do NOT cross the Planner boundary.  These flow between stages
inside the pipeline but are never exposed to Orchestrator or other modules.

Design decisions
----------------
- All types frozen=True (immutable after creation).
- Pure dataclasses with NO I/O, NO port references, NO service logic.
- No async methods on dataclasses.
- Shared types (PlanRequest, CommittedPlan, PlanStep, PlanAck,
  MicroReplanRequest) live in k1/orchestrator/types.py (Section 32) --
  Planner imports them but MUST NOT redefine them.

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.planner.types
  -> k1.orchestrator.types  (PlanStep)
  -> k1.fabric.types        (ScoredCapability)
  -> stdlib only

NEVER import from any service, port, or adapter module.

References
----------
- planner.md Section 6.5   (SketchResult / RoughStep)
- planner.md Section 7.4   (ExpandedPlan)
- planner.md Section 8.3.3 (ValidationVerdict / ValidationIssue)
- planner.md Section 18.1  (PlanState -- defined in plan_fsm.py, not here)
- planner.md Section 22.4.1 (DeltaPayload)
- planner.md Section 30.5.1 F05
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from k1.fabric.types import ScoredCapability
from k1.orchestrator.types import PlanStep

# ---------------------------------------------------------------------------
# Section 6.5 -- SKETCH output types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoughStep:
    """Single step in a sketch plan (Section 6.5).

    Produced by SketchService from LLM output.  Each RoughStep is a
    high-level description of an action -- not yet fully parameterised.

    Fields
    ------
    intent : str
        Natural-language step description.  Must be non-empty.
    suggested_capability : Optional[str]
        Capability name from discovery results (if matched).
        When present, must match a name in the parent SketchResult's
        capability_candidates.
    depends_on : List[str]
        Intent strings of predecessor steps within the same sketch.
    confidence : float
        LLM self-assessed confidence for this step [0.0, 1.0].
    """

    intent: str
    suggested_capability: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.intent:
            raise ValueError("RoughStep.intent must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"RoughStep.confidence must be in [0.0, 1.0], got {self.confidence}")


@dataclass(frozen=True)
class SketchResult:
    """Full output of the SKETCH stage (Section 6.5).

    Flows: SketchService -> PipelineController -> ExpandService.

    Fields
    ------
    rough_steps : List[RoughStep]
        Ordered list of high-level plan steps.  Must be non-empty.
    capability_candidates : List[ScoredCapability]
        Full discovery results carried forward from Fabric retrieval.
    rationale : str
        LLM reasoning for the plan structure.  Must be non-empty.
    """

    rough_steps: List[RoughStep] = field(default_factory=list)
    capability_candidates: List[ScoredCapability] = field(default_factory=list)
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.rough_steps:
            raise ValueError("SketchResult.rough_steps must be non-empty")
        if not self.rationale:
            raise ValueError("SketchResult.rationale must be non-empty")
        # Validate suggested_capability references match discovery results
        candidate_names = {
            sc.contract.name for sc in self.capability_candidates if sc.contract is not None
        }
        for step in self.rough_steps:
            if step.suggested_capability and step.suggested_capability not in candidate_names:
                raise ValueError(
                    f"RoughStep.suggested_capability '{step.suggested_capability}' "
                    f"not found in capability_candidates"
                )


# ---------------------------------------------------------------------------
# Section 7.4 -- EXPAND output type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpandedPlan:
    """Full output of the EXPAND stage (Section 7.4).

    Flows: ExpandService -> PipelineController -> ValidateService -> CommitService.

    Contains fully parameterised PlanStep instances (14 fields each from
    k1/orchestrator/types.py) plus a dependency graph and tool mappings.

    Fields
    ------
    steps : List[PlanStep]
        Fully parameterised plan steps.  Must be non-empty.
        7 fields LLM-generated, 7 deterministically enriched by ExpandService.
    dependencies : Dict[str, List[str]]
        step_id -> list of predecessor step_ids.  Must form a DAG.
        Keys must be a subset of step IDs.
    tool_mappings : Dict[str, str]
        step_id -> tool/capability mapping for execution routing.
    rationale : str
        LLM reasoning for the expansion decisions.  Must be non-empty.
    """

    steps: List[PlanStep] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    tool_mappings: Dict[str, str] = field(default_factory=dict)
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("ExpandedPlan.steps must be non-empty")
        if not self.rationale:
            raise ValueError("ExpandedPlan.rationale must be non-empty")
        step_ids = {s.id for s in self.steps}
        for dep_step, dep_list in self.dependencies.items():
            if dep_step not in step_ids:
                raise ValueError(
                    f"ExpandedPlan.dependencies key '{dep_step}' " f"not in step IDs {step_ids}"
                )
            for dep in dep_list:
                if dep not in step_ids:
                    raise ValueError(
                        f"ExpandedPlan dependency '{dep}' of step "
                        f"'{dep_step}' not in step IDs {step_ids}"
                    )


# ---------------------------------------------------------------------------
# Section 8.3.3 -- VALIDATE output types
# ---------------------------------------------------------------------------

# Valid status values for ValidationVerdict
VERDICT_APPROVED = "approved"
VERDICT_REVISE = "revise"
VERDICT_REJECT = "reject"
_VALID_VERDICT_STATUSES = frozenset({VERDICT_APPROVED, VERDICT_REVISE, VERDICT_REJECT})

# Valid severity values for ValidationIssue
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
_VALID_SEVERITIES = frozenset({SEVERITY_ERROR, SEVERITY_WARNING})

# Known check names (not exhaustive -- extensible for future checks)
CHECK_DAG_CYCLE = "dag_cycle"
CHECK_CAPABILITY_MISSING = "capability_missing"
CHECK_PARAM_TYPE_MISMATCH = "param_type_mismatch"
CHECK_UNSAFE_CAPABILITY = "unsafe_capability"
CHECK_LLM_ARBITER_REJECT = "llm_arbiter_reject"
CHECK_TOOL_BUDGET_EXCEEDED = "tool_budget_exceeded"
CHECK_STEP_ID_DUPLICATE = "step_id_duplicate"
CHECK_DANGLING_DEPENDENCY = "dangling_dependency"
CHECK_SELF_REFERENCE = "self_reference"
CHECK_INTER_STEP_REF = "inter_step_ref_inconsistency"

# Valid safety assessment values for ValidationVerdict
SAFETY_SAFE = "safe"
SAFETY_CAUTION = "caution"
SAFETY_UNSAFE = "unsafe"
SAFETY_UNKNOWN = "unknown"
_VALID_SAFETY_ASSESSMENTS = frozenset({SAFETY_SAFE, SAFETY_CAUTION, SAFETY_UNSAFE, SAFETY_UNKNOWN})


@dataclass(frozen=True)
class ValidationIssue:
    """Single issue found during plan validation (Section 8.3.3).

    Fields
    ------
    check_name : str
        Name of the validation check that raised this issue.
        Known values: dag_cycle, capability_missing, param_type_mismatch,
        unsafe_capability, llm_arbiter_reject.
    severity : str
        "error" (blocks commit) or "warning" (logged, plan continues).
    step_id : Optional[str]
        The step that triggered the issue, if applicable.
    detail : str
        Human-readable description of the issue.
    """

    check_name: str
    severity: str
    step_id: Optional[str] = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.check_name:
            raise ValueError("ValidationIssue.check_name must be non-empty")
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"ValidationIssue.severity must be one of {_VALID_SEVERITIES}, "
                f"got '{self.severity}'"
            )


@dataclass(frozen=True)
class ValidationVerdict:
    """Output of the VALIDATE stage (Section 8.3.3).

    Flows: ValidateService -> PipelineController -> CommitService (if approved).

    The verdict determines the next pipeline action:
      - "approved": proceed to COMMIT stage.
      - "revise": send back to EXPAND with issues (max 1 revise loop).
      - "reject": transition to FAILED state.

    Fields
    ------
    status : str
        One of "approved", "revise", "reject".
    issues : List[ValidationIssue]
        All issues found during validation.  May be empty for "approved".
    confidence : float
        LLM arbiter confidence score [0.0, 1.0].  Maps to the arbiter's
        coherence_score dimension.
    rationale : str
        LLM reasoning for the verdict.  Must be non-empty.
    deterministic_pass : bool
        True if all deterministic checks (DAG acyclicity, capability
        existence, structural checks) passed.  False if any failed.
        PipelineController uses this for auto-approve on arbiter failure
        (Section 8.6).
    safety_assessment : str
        Arbiter's assessed safety level: "safe", "caution", "unsafe",
        or "unknown" (when arbiter unavailable).  Used by HIL approval
        trigger logic (Section 8.4.1).
    suggested_fixes : List[str]
        Actionable fix suggestions from the arbiter.  Passed to
        ExpandService.execute(arbiter_feedback=...) when status is
        "revise" (Section 8.5.1).
    """

    status: str
    issues: List[ValidationIssue] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    deterministic_pass: bool = True
    safety_assessment: str = SAFETY_UNKNOWN
    suggested_fixes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in _VALID_VERDICT_STATUSES:
            raise ValueError(
                f"ValidationVerdict.status must be one of "
                f"{_VALID_VERDICT_STATUSES}, got '{self.status}'"
            )
        if not self.rationale:
            raise ValueError("ValidationVerdict.rationale must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"ValidationVerdict.confidence must be in [0.0, 1.0], " f"got {self.confidence}"
            )
        if self.safety_assessment not in _VALID_SAFETY_ASSESSMENTS:
            raise ValueError(
                f"ValidationVerdict.safety_assessment must be one of "
                f"{_VALID_SAFETY_ASSESSMENTS}, got '{self.safety_assessment}'"
            )
        # "revise" and "reject" should have at least one issue
        if self.status in (VERDICT_REVISE, VERDICT_REJECT) and not self.issues:
            raise ValueError(
                f"ValidationVerdict with status '{self.status}' must have " f"at least one issue"
            )
        # Check for blocking errors
        has_errors = any(i.severity == SEVERITY_ERROR for i in self.issues)
        if self.status == VERDICT_APPROVED and has_errors:
            raise ValueError(
                "ValidationVerdict with status 'approved' must not have "
                "issues with severity 'error'"
            )
        # Cannot approve a structurally invalid plan
        if self.status == VERDICT_APPROVED and not self.deterministic_pass:
            raise ValueError(
                "ValidationVerdict with status 'approved' must have " "deterministic_pass=True"
            )


# ---------------------------------------------------------------------------
# Section 30.5.1 F05 -- StageContext (passed to every pipeline stage)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageContext:
    """Runtime context passed to every pipeline stage (Section 30.5.1 F05).

    Created by PipelineController at the start of each stage with updated
    remaining timeouts and budgets.  Every outbound port call uses
    ``ctx.trace_id`` for FAB-09 compliance (Section 22.1).

    Fields
    ------
    request_id : str
        Correlates with PlanRequest.request_id.
    trace_id : str
        Cognitive trace ID propagated to all port calls (FAB-09).
    timeout_remaining_ms : int
        Milliseconds remaining in the pipeline budget.  Must be > 0.
    token_budget_remaining : int
        Token budget remaining for LLM calls.  Must be >= 0.
    cancel_check : Callable[[], bool]
        Returns True if the request has been cancelled (cooperative
        cancellation via ``_cancel_set`` per Section 18.5.3).
    """

    request_id: str
    trace_id: str
    timeout_remaining_ms: int
    token_budget_remaining: int
    cancel_check: Callable[[], bool]
    stage_budget: Optional["PlannerConstraints"] = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("StageContext.request_id must be non-empty")
        if not self.trace_id:
            raise ValueError("StageContext.trace_id must be non-empty")
        if self.timeout_remaining_ms <= 0:
            raise ValueError(
                f"StageContext.timeout_remaining_ms must be > 0, "
                f"got {self.timeout_remaining_ms}"
            )
        if self.token_budget_remaining < 0:
            raise ValueError(
                f"StageContext.token_budget_remaining must be >= 0, "
                f"got {self.token_budget_remaining}"
            )
        if not callable(self.cancel_check):
            raise ValueError("StageContext.cancel_check must be callable")


# ---------------------------------------------------------------------------
# Section 12 -- HILCoordinatorLike protocol (shared by SKETCH + VALIDATE)
# ---------------------------------------------------------------------------


@runtime_checkable
class HILCoordinatorLike(Protocol):
    """Protocol for Human-in-the-Loop coordinator (Section 12).

    Shared protocol used by both SketchService (clarification) and
    ValidateService (approval).  The concrete HILCoordinator
    (k1.planner.services.hil_coordinator, Epic 4.2) will satisfy
    this structurally.

    PLAN-10: max 2 HIL rounds per plan (clarification + approval combined).
    """

    @property
    def round_count(self) -> int:
        """Current HIL round count (PLAN-10)."""
        ...  # pragma: no cover

    def reset(self) -> None:
        """Reset all HIL state (LC_PLAN_START)."""
        ...  # pragma: no cover

    async def request_clarification(
        self,
        request_id: str,
        question_context: Dict[str, Any],
    ) -> Optional[str]:
        """Trigger clarification flow (Section 12.2).

        Called by SketchService when ambiguity detected in LLM output
        (needs_clarification == true).

        Returns user response text, or None on timeout / budget
        exhaustion.  Max 2 rounds per plan (PLAN-10).  60s timeout
        per round.
        """
        ...  # pragma: no cover

    async def request_approval(
        self,
        request_id: str,
        plan_summary: str,
        side_effects: List[str],
        safety_assessment: str,
        estimated_duration_ms: int,
    ) -> str:
        """Trigger approval flow (Section 8.4).

        Called by ValidateService when plan has high-impact side effects
        and non-GREEN safety band.

        Returns one of: "approve", "modify", "reject".
        Timeout: 120s.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Section 22.4.1 -- DeltaPayload (delta envelope for observability)
# ---------------------------------------------------------------------------

# Delta type constants (Section 22.4.2 / Section 28.3)
# Wire-format delta_type values used in DeltaPayload.delta_type
DELTA_STAGE_TRANSITION = "stage_transition"
DELTA_TOOL_RESULT = "tool_result"
DELTA_HIL_EVENT = "hil_event"
DELTA_PLAN_UPDATE = "plan_update"
DELTA_PLAN_END = "plan_end"
DELTA_PLAN_CANCELLED = "plan_cancelled"
DELTA_MICRO_REPLAN = "micro_replan"
DELTA_CRASH_RECOVERY = "crash_recovery"

_VALID_DELTA_TYPES = frozenset(
    {
        DELTA_STAGE_TRANSITION,
        DELTA_TOOL_RESULT,
        DELTA_HIL_EVENT,
        DELTA_PLAN_UPDATE,
        DELTA_PLAN_END,
        DELTA_PLAN_CANCELLED,
        DELTA_MICRO_REPLAN,
        DELTA_CRASH_RECOVERY,
    }
)

# Valid section values for DeltaPayload.section
SECTION_PIPELINE = "pipeline"
SECTION_PLAN = "plan"
SECTION_TOOLS = "tools"

_VALID_SECTIONS = frozenset({SECTION_PIPELINE, SECTION_PLAN, SECTION_TOOLS})

# Planner agent_id constant (Section 16.1.6)
PLANNER_AGENT_ID = "planner"


@dataclass(frozen=True)
class DeltaPayload:
    """Delta envelope for Planner observability emissions (Section 22.4.1).

    Fire-and-forget via IDeltaEmitPort -> DeltaBusAdapter ->
    ``k1.planner.delta.v1`` topic.  PipelineController is the sole emitter.
    Delta loss is acceptable (observability signals, not control-plane).

    Fields
    ------
    agent_id : str
        Always "planner" (stamped by DeltaBusAdapter per Section 16.1.6).
    delta_type : str
        One of: stage_transition, tool_result, hil_event, plan_update,
        plan_end, micro_replan, crash_recovery.
    section : str
        One of: "pipeline", "plan", "tools".
    data : Dict[str, Any]
        Type-specific payload contents.
    trace_id : str
        Cognitive trace ID for FAB-09 observability correlation.
    """

    agent_id: str
    delta_type: str
    section: str
    data: Dict[str, Any]
    trace_id: str

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("DeltaPayload.agent_id must be non-empty")
        if self.delta_type not in _VALID_DELTA_TYPES:
            raise ValueError(
                f"DeltaPayload.delta_type must be one of "
                f"{sorted(_VALID_DELTA_TYPES)}, got '{self.delta_type}'"
            )
        if self.section not in _VALID_SECTIONS:
            raise ValueError(
                f"DeltaPayload.section must be one of "
                f"{sorted(_VALID_SECTIONS)}, got '{self.section}'"
            )
        if not self.trace_id:
            raise ValueError("DeltaPayload.trace_id must be non-empty")


# ---------------------------------------------------------------------------
# Enums (Layer 0 -- no internal deps)
# ---------------------------------------------------------------------------


class StagePhase(str, Enum):
    """Pipeline stage phases (Section 30.5.1 F05).

    Used by PipelineController for budget injection lookup and per-stage
    token tracking.  4 phases matching the 4-stage pipeline.
    """

    SKETCH = "SKETCH"
    EXPAND = "EXPAND"
    VALIDATE = "VALIDATE"
    COMMIT = "COMMIT"


class ToolCallStatus(str, Enum):
    """Tool call result classification (Section 30.5.1 F05).

    Used by ToolCallRouter to classify the outcome of each tool call.
    """

    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


# ---------------------------------------------------------------------------
# Section 13.2.3 -- Request constraints for LLM calls
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannerConstraints:
    """Per-call LLM constraints forwarded to ModelHub (Section 13.2.3).

    Planner-local simplified constraints.  The LLMGatewayAdapter translates
    these to ``k1.model_hub.types.RequestConstraints`` before dispatching
    to the Model Hub.

    Attributes
    ----------
    max_tokens : int
        Maximum tokens for the LLM response.
    timeout_ms : int
        Request-level timeout in milliseconds.
    priority : str
        Scheduling priority hint (always ``"INTERACTIVE"`` for planner).
    temperature : float
        LLM sampling temperature in [0.0, 1.0].
    consumer_id : str
        Caller identity for billing / rate-limiting (always ``"planner"``).
    """

    max_tokens: int
    timeout_ms: int
    priority: str = "INTERACTIVE"
    temperature: float = 0.7
    consumer_id: str = "planner"

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError(
                f"RequestConstraints.max_tokens must be > 0, " f"got {self.max_tokens}"
            )
        if self.timeout_ms <= 0:
            raise ValueError(
                f"RequestConstraints.timeout_ms must be > 0, " f"got {self.timeout_ms}"
            )
        if not self.priority:
            raise ValueError("RequestConstraints.priority must be non-empty")
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError(
                f"RequestConstraints.temperature must be in [0.0, 1.0], " f"got {self.temperature}"
            )
        if not self.consumer_id:
            raise ValueError("RequestConstraints.consumer_id must be non-empty")


# ---------------------------------------------------------------------------
# Section 13.2 -- Model Hub request/response envelopes
# Migration note: These types should migrate to k1/model_hub/types.py when
# that module is created.  Defined locally to avoid a missing-dependency
# import error (model_hub package does not yet expose types.py).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannerLLMRequest:
    """Planner-local LLM request envelope (Section 13.2, SS15.3).

    Simplified request type used within the Planner pipeline.  The
    ``LLMGatewayAdapter`` translates this to ``k1.model_hub.types.HubRequest``
    before dispatching to the Model Hub.

    Constructed by pipeline stage services (SketchService, ExpandService,
    ValidateService, HILCoordinator) and passed through ``ILLMPort.execute()``.

    Attributes
    ----------
    capability : str
        ``"CHAT"`` or ``"STRUCTURED"`` -- the two capabilities the Planner uses.
    payload : Dict[str, Any]
        ChatPayload or StructuredOutputPayload serialised to dict.
        ChatPayload keys: ``messages``, ``temperature``.
        StructuredOutputPayload keys: ``messages``, ``output_schema``, ``temperature``.
    constraints : PlannerConstraints
        Per-call budget / timeout / temperature constraints (PLAN-11).
    trace_id : str
        Cognitive trace ID for end-to-end observability (FAB-09).
    """

    capability: str
    payload: Dict[str, Any]
    constraints: PlannerConstraints
    trace_id: str = ""

    def __post_init__(self) -> None:
        if self.capability not in ("CHAT", "STRUCTURED"):
            raise ValueError(
                f"HubRequest.capability must be 'CHAT' or 'STRUCTURED', " f"got '{self.capability}'"
            )
        if not isinstance(self.payload, dict):
            raise ValueError("HubRequest.payload must be a dict")


@dataclass(frozen=True)
class PlannerLLMResponse:
    """Planner-local LLM response envelope (Section 13.2, SS15.3).

    Simplified response type used within the Planner pipeline.  The
    ``LLMGatewayAdapter`` translates ``k1.model_hub.types.HubResponse``
    back into this type.

    Returned by ``ILLMPort.execute()`` after Model Hub processes the request.

    Attributes
    ----------
    result : Dict[str, Any]
        ``CapabilityResult`` serialised to dict.  Key field: ``content``
        (the LLM's text or structured output).
    metadata : Dict[str, Any]
        ``ResponseMetadata`` serialised to dict.  Key fields:
        ``usage.total_tokens``, ``latency_ms``, ``model_id``.
    """

    result: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Backward-compat aliases (E-0.5.1) — remove once all imports updated
# ---------------------------------------------------------------------------
RequestConstraints = PlannerConstraints
HubRequest = PlannerLLMRequest
HubResponse = PlannerLLMResponse

# ---------------------------------------------------------------------------
# Section 15.6 -- Bridge recall response
# The Planner's IBridgePort.recall() returns this type.  The adapter
# constructs it from BridgeCommandResult.data.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecallResponse:
    """K0 long-term memory recall response (Section 15.6).

    Returned by ``IBridgePort.recall()``.  The BridgeAdapter constructs this
    from ``BridgeCommandResult.data`` after a ``memory.recall`` query.

    Attributes
    ----------
    facts : List[Dict[str, Any]]
        Retrieved memory facts matching the recall query.
    scores : List[float]
        Similarity scores corresponding to each fact (0.0-1.0).
    trace_id : str
        Echoed trace ID for correlation.
    """

    facts: List[Dict[str, Any]] = field(default_factory=list)
    scores: List[float] = field(default_factory=list)
    trace_id: str = ""


# ---------------------------------------------------------------------------
# Section 13.3 -- Per-stage token tracking
# ---------------------------------------------------------------------------


@dataclass
class TokenUsageRecord:
    """Mutable per-stage token usage tracker (Section 13.3).

    Updated by PipelineController after each LLM call within a stage.
    NOT frozen -- accumulates usage over multiple calls within a stage.

    Attributes
    ----------
    stage : str
        Pipeline stage name (matches StagePhase value).
    prompt_tokens : int
        Cumulative prompt token count for this stage.
    completion_tokens : int
        Cumulative completion token count for this stage.
    total_tokens : int
        Cumulative total token count for this stage.
    """

    stage: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if not self.stage:
            raise ValueError("TokenUsageRecord.stage must be non-empty")
        if self.prompt_tokens < 0:
            raise ValueError(
                f"TokenUsageRecord.prompt_tokens must be >= 0, " f"got {self.prompt_tokens}"
            )
        if self.completion_tokens < 0:
            raise ValueError(
                f"TokenUsageRecord.completion_tokens must be >= 0, " f"got {self.completion_tokens}"
            )
        if self.total_tokens < 0:
            raise ValueError(
                f"TokenUsageRecord.total_tokens must be >= 0, " f"got {self.total_tokens}"
            )


# ---------------------------------------------------------------------------
# Section 30.5.1 -- Planner error hierarchy
# ---------------------------------------------------------------------------


class PlannerError(Exception):
    """Base exception for all Planner errors.

    Carries structured context so that PipelineController can emit
    TOPIC_PLAN_FAILED with full attribution.

    Attributes
    ----------
    stage : str
        Pipeline stage where the error originated.
    request_id : str
        Plan request identifier.
    trace_id : str
        Distributed trace identifier.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str = "",
        request_id: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.request_id = request_id
        self.trace_id = trace_id


class SketchFailedError(PlannerError):
    """SKETCH stage failed after retries (Section 6.7)."""


class ExpandFailedError(PlannerError):
    """EXPAND stage failed after retries (Section 7.6)."""


class ValidateRejectedError(PlannerError):
    """VALIDATE stage rejected the plan (Section 8.3.4)."""


class CommitFailedError(PlannerError):
    """COMMIT stage failed (Section 9.3)."""


class BudgetExhaustedError(PlannerError):
    """Total token budget exhausted across stages (Section 13.3)."""


class MailboxFullError(PlannerError):
    """Mailbox queue at max depth, request rejected (Section 14.1)."""


class ShutdownError(PlannerError):
    """Planner is shutting down, cannot accept new requests (Section 23.5)."""


class PlanCancelledError(PlannerError):
    """Plan cancelled by Orchestrator via send_cancel() (Section 24.2)."""


class HILTimeoutError(PlannerError):
    """HIL interaction timed out waiting for user response (Section 12.4)."""


class HILBudgetExceededError(PlannerError):
    """HIL clarification round budget exhausted (PLAN-10, Section 12.2.4)."""


class LLMTimeoutError(PlannerError):
    """Model Hub timed out processing an LLM request (Section 13, SS16.1.2)."""


class AdapterException(PlannerError):
    """Production adapter infrastructure failure (SS16.1).

    Carries a ``degraded`` flag indicating whether the pipeline can
    continue in degraded mode or must abort.
    """

    def __init__(
        self,
        message: str,
        *,
        degraded: bool = True,
        stage: str = "",
        request_id: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message, stage=stage, request_id=request_id, trace_id=trace_id)
        self.degraded = degraded


class UnknownToolError(PlannerError):
    """Unknown tool name passed to ToolCallRouter (Section 11.5.2)."""


# ---------------------------------------------------------------------------
# Factory error types (Epic 6.3 -- used by PlannerFactory)
# ---------------------------------------------------------------------------


class InvalidPortError(PlannerError):
    """Port fails ``isinstance`` check against its Protocol (factory DI validation).

    Attributes
    ----------
    port_name : str
        Canonical port slot name (e.g. ``"llm_port"``).
    expected_protocol : str
        Fully-qualified name of the expected Protocol.
    actual_type : str
        ``type().__qualname__`` of the object that was passed.
    """

    def __init__(
        self,
        message: str,
        *,
        port_name: str = "",
        expected_protocol: str = "",
        actual_type: str = "",
        stage: str = "",
        request_id: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message, stage=stage, request_id=request_id, trace_id=trace_id)
        self.port_name = port_name
        self.expected_protocol = expected_protocol
        self.actual_type = actual_type


class MissingPortError(PlannerError):
    """Required port is ``None`` (factory completeness check).

    Attributes
    ----------
    port_name : str
        Canonical port slot name that was ``None``.
    """

    def __init__(
        self,
        message: str,
        *,
        port_name: str = "",
        stage: str = "",
        request_id: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message, stage=stage, request_id=request_id, trace_id=trace_id)
        self.port_name = port_name


class DuplicatePortError(PlannerError):
    """Two port slots share the same ``id()`` (factory uniqueness check).

    Attributes
    ----------
    port_a : str
        First port slot name.
    port_b : str
        Second port slot name that shares the same identity.
    """

    def __init__(
        self,
        message: str,
        *,
        port_a: str = "",
        port_b: str = "",
        stage: str = "",
        request_id: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message, stage=stage, request_id=request_id, trace_id=trace_id)
        self.port_a = port_a
        self.port_b = port_b


class InvalidConfigError(PlannerError):
    """PlannerConfig field violates validation bounds (factory config check).

    Attributes
    ----------
    field_name : str
        Config field that failed validation.
    value : object
        Actual value that was rejected.
    constraint : str
        Human-readable constraint description.
    """

    def __init__(
        self,
        message: str,
        *,
        field_name: str = "",
        value: object = None,
        constraint: str = "",
        stage: str = "",
        request_id: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message, stage=stage, request_id=request_id, trace_id=trace_id)
        self.field_name = field_name
        self.value = value
        self.constraint = constraint


class PlannerInitError(PlannerError):
    """Agent wiring or startup failed (factory post-wiring check).

    Attributes
    ----------
    detail : str
        Description of what failed during initialization.
    """

    def __init__(
        self,
        message: str,
        *,
        detail: str = "",
        stage: str = "",
        request_id: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message, stage=stage, request_id=request_id, trace_id=trace_id)
        self.detail = detail


# ---------------------------------------------------------------------------
# Health model (returned by PlannerAgent.health())
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthStatus:
    """Snapshot of planner agent health state.

    Returned by ``PlannerAgent.health()`` for factory post-wiring
    validation and runtime health checks.

    Attributes
    ----------
    status : str
        One of ``"HEALTHY"``, ``"DEGRADED"``, ``"UNHEALTHY"``.
    details : Dict[str, Any]
        Arbitrary key-value diagnostics (e.g. running state, queue depth).
    """

    status: str
    details: Dict[str, Any]
