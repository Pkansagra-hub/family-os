"""k1.planner -- Planner module package facade [F01].

Re-exports shared types from k1.orchestrator.types (Section 32) so that
consumers within the planner package can import from k1.planner directly.
Planner MUST NOT redefine these shared types.

Re-exports planner-internal types from k1.planner.types [F05],
PlanState enum from k1.planner.plan_fsm [F04],
event topics/payloads from k1.planner.events [F06],
PlannerConfig from k1.planner.config [F07],
PipelineController from k1.planner.pipeline_controller [F03], and
PlannerAgent from k1.planner.planner_agent [F02].

Import graph
------------
k1.planner
  -> k1.orchestrator.types           (shared types: PlanRequest, CommittedPlan, etc.)
  -> k1.planner.types                (internal types: SketchResult, ExpandedPlan, etc.)
  -> k1.planner.plan_fsm             (PlanState enum)
  -> k1.planner.events               (topic constants, payload dataclasses)
  -> k1.planner.config               (PlannerConfig)
  -> k1.planner.pipeline_controller  (PipelineController)
  -> k1.planner.planner_agent        (PlannerAgent)
"""

# -- Shared types (Section 32 -- source of truth: k1/orchestrator/types.py) --
from k1.orchestrator.types import (  # noqa: F401
    CommittedPlan,
    MicroReplanRequest,
    PlanAck,
    PlanRequest,
    PlanStep,
)

# -- PlannerConfig (source of truth: k1/planner/config.py [F07]) --
from k1.planner.config import PlannerConfig  # noqa: F401

# -- Event topics and payloads (source of truth: k1/planner/events.py [F06]) --
from k1.planner.events import (  # noqa: F401
    TOPIC_DELTA,
    TOPIC_HIL_APPROVAL_REQ,
    TOPIC_HIL_APPROVAL_RESP,
    TOPIC_HIL_CLARIFICATION,
    TOPIC_HIL_CLARIFICATION_RESP,
    TOPIC_MICRO_REPLAN_READY,
    TOPIC_PLAN_CANCEL,
    TOPIC_PLAN_CANCELLED,
    TOPIC_PLAN_FAILED,
    TOPIC_PLAN_READY,
    TOPIC_PLAN_REQUEST,
    HILApprovalRequestPayload,
    HILClarificationPayload,
    PlanCancelledPayload,
    PlanFailedPayload,
)

# -- PlannerFactory (source of truth: k1/planner/factory.py [F08]) --
from k1.planner.factory import PlannerFactory  # noqa: F401

# -- PipelineController (source of truth: k1/planner/pipeline_controller.py [F03]) --
from k1.planner.pipeline_controller import PipelineController  # noqa: F401

# -- PlanState enum (source of truth: k1/planner/plan_fsm.py [F04]) --
from k1.planner.plan_fsm import (  # noqa: F401
    TRANSITION_TABLE,
    IllegalStateTransitionError,
    PlanState,
    PlanStateMachine,
)

# -- PlannerAgent (source of truth: k1/planner/planner_agent.py [F02]) --
from k1.planner.planner_agent import PlannerAgent  # noqa: F401

# -- Port protocols (source of truth: k1/planner/ports/ [F11-F18]) --
from k1.planner.ports import (  # noqa: F401
    IBridgePort,
    IDeltaEmitPort,
    IEventPort,
    IFabricRetrievalPort,
    ILLMPort,
    IMailboxPort,
    IStateReadPort,
)

# -- Planner-internal types (source of truth: k1/planner/types.py [F05]) --
from k1.planner.types import (  # noqa: F401
    SAFETY_CAUTION,
    SAFETY_SAFE,
    SAFETY_UNKNOWN,
    SAFETY_UNSAFE,
    BudgetExhaustedError,
    CommitFailedError,
    DeltaPayload,
    DuplicatePortError,
    ExpandedPlan,
    ExpandFailedError,
    HealthStatus,
    HILBudgetExceededError,
    HILCoordinatorLike,
    HILTimeoutError,
    HubRequest,
    HubResponse,
    InvalidConfigError,
    InvalidPortError,
    MailboxFullError,
    MissingPortError,
    PlanCancelledError,
    PlannerError,
    PlannerInitError,
    RecallResponse,
    RequestConstraints,
    RoughStep,
    SketchFailedError,
    SketchResult,
    StageContext,
    StagePhase,
    TokenUsageRecord,
    ToolCallStatus,
    UnknownToolError,
    ValidateRejectedError,
    ValidationIssue,
    ValidationVerdict,
)

__all__ = [
    # Shared types (re-exported)
    "PlanRequest",
    "CommittedPlan",
    "PlanStep",
    "PlanAck",
    "MicroReplanRequest",
    # Planner-internal types
    "SketchResult",
    "RoughStep",
    "ExpandedPlan",
    "ValidationVerdict",
    "ValidationIssue",
    "HILCoordinatorLike",
    "SAFETY_SAFE",
    "SAFETY_CAUTION",
    "SAFETY_UNSAFE",
    "SAFETY_UNKNOWN",
    "StageContext",
    "DeltaPayload",
    "RequestConstraints",
    "TokenUsageRecord",
    "HubRequest",
    "HubResponse",
    "RecallResponse",
    # Enums
    "StagePhase",
    "ToolCallStatus",
    "PlanState",
    # FSM
    "TRANSITION_TABLE",
    "IllegalStateTransitionError",
    "PlanStateMachine",
    # PipelineController
    "PipelineController",
    # PlannerAgent
    "PlannerAgent",
    # PlannerFactory
    "PlannerFactory",
    # Error hierarchy
    "PlannerError",
    "SketchFailedError",
    "ExpandFailedError",
    "ValidateRejectedError",
    "CommitFailedError",
    "BudgetExhaustedError",
    "MailboxFullError",
    "PlanCancelledError",
    "HILBudgetExceededError",
    "HILTimeoutError",
    "UnknownToolError",
    # Factory errors
    "InvalidPortError",
    "MissingPortError",
    "DuplicatePortError",
    "InvalidConfigError",
    "PlannerInitError",
    # Health
    "HealthStatus",
    # Event topics -- published
    "TOPIC_PLAN_READY",
    "TOPIC_PLAN_FAILED",
    "TOPIC_PLAN_CANCELLED",
    "TOPIC_MICRO_REPLAN_READY",
    "TOPIC_DELTA",
    "TOPIC_HIL_CLARIFICATION",
    "TOPIC_HIL_APPROVAL_REQ",
    # Event topics -- subscribed
    "TOPIC_PLAN_REQUEST",
    "TOPIC_PLAN_CANCEL",
    "TOPIC_HIL_CLARIFICATION_RESP",
    "TOPIC_HIL_APPROVAL_RESP",
    # Event payloads
    "PlanFailedPayload",
    "PlanCancelledPayload",
    "HILClarificationPayload",
    "HILApprovalRequestPayload",
    # Config
    "PlannerConfig",
    # Port protocols
    "IMailboxPort",
    "ILLMPort",
    "IFabricRetrievalPort",
    "IStateReadPort",
    "IBridgePort",
    "IDeltaEmitPort",
    "IEventPort",
]
