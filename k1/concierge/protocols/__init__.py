"""
k1.concierge.protocols -- Task lifecycle protocols for cooperative cancellation,
suspension, weave batching, and human-in-the-loop (HITL) coordination.

V2 Design Ref: Section 4 (FSM states: CANCELLING, CLARIFYING_WORKER)
V2 Design Ref: Section 5 (FSMTurnState: cancelled_tasks, cancellation_requested)
V2 Design Ref: Section 5 (TaskStateEntry: status SUSPENDED/CANCELLED, pending_hil)
V2 Design Ref: Section 5 (Resume Context: findings_so_far, tool_history, resolution)
V2 Design Ref: Section 9 (HITL Protocol: closed cycle, safety bands, invariants)

This package implements the cooperative protocols that the FSM uses to
coordinate between Front and Back during non-linear task execution:

    Cancellation:
        CancellationToken      -- cooperative cancel flag for Back tasks
        CancelReason           -- why a task was cancelled
        TaskCancelledError     -- raised at tool boundary when cancelled

    Cancellation Events:
        TaskCancelEvent        -- Front -> FSM: user requests cancel
        TaskFailedCancelledEvent -- Back -> FSM: aborted due to cancel

    Cancellation Handler:
        CancellationHandler    -- FSM-side lifecycle management

    Suspension:
        SuspensionType         -- why task suspended (clarification/approval/selection)
        SuspensionRequest      -- Back -> FSM: needs human input
        SuspensionResolution   -- Front -> FSM: user answered
        SuspensionLimitExceeded -- max suspensions exceeded
        SuspensionTimeoutError  -- user did not respond in time

    Suspension Events:
        TaskSuspendedEvent     -- bus event for suspension
        TaskResumeEvent        -- bus event for resume

    Suspension Manager:
        SuspensionManager      -- FSM-side suspension lifecycle

    Weave Batcher (Epic 12.4):
        WeaveBatcher           -- 500ms batch window for task results
        WeaveResult            -- completed task result dataclass
        WEAVE_BATCH_WINDOW_MS  -- batch window constant (500)

    Weave State Table (Epic 12.5):
        WeaveAction            -- FSM weave decision enum
        PendingResult          -- queued result dataclass
        PendingResultsQueue    -- FIFO queue for pending results
        get_weave_action       -- state -> action lookup
        STATE_ACTION_TABLE     -- full state-to-action mapping

    HITL Types (Epic 13.1):
        SafetyBand             -- GREEN/AMBER/RED execution gating
        HILRequest             -- structured HITL request from Back
        HILResponse            -- structured HITL response from Front
        HIL_TIMEOUTS           -- REMOVED (V3 E0.2.1, use config accessor)
        escalate_safety_band   -- safety band escalation logic

    HITL Coordinator (Epic 13.2):
        HILCoordinator         -- FSM-side HITL orchestration
        HILCoordinatorConfig   -- coordinator configuration
        HIL_TO_SUSPENSION      -- hil_type -> SuspensionType mapping

    HITL Flow Helpers (Epic 13.3):
        HILFlowType            -- clarification/approval/selection enum
        ClarificationContext   -- missing-param context builder
        ApprovalContext        -- side-effect context builder
        SelectionContext       -- multi-result context builder
        build_clarification_request  -- factory for clarification HILRequest
        build_approval_request       -- factory for approval HILRequest
        build_selection_request      -- factory for selection HILRequest
        parse_clarification_resolution  -- parse clarification answer
        parse_approval_resolution       -- parse approval answer
        parse_selection_resolution      -- parse selection answer

    HITL Pipeline (Epic 13.4 + 13.5):
        detect_approval_required       -- check if capability needs approval
        apply_approval_modifications   -- merge user modifications into params
        process_approval_response      -- full approval resolution pipeline
        ApprovalResult                 -- approval outcome dataclass
        SelectionResult                -- selection outcome dataclass
        resolve_selection_to_params    -- map selection to concrete option data
        build_resume_params_from_selection -- merge selection into resume params

    HITL Persistence (Epic 13.6):
        TaskStatus             -- task lifecycle status enum
        TaskStateEntry         -- persistence model with HITL fields
        HILTimeoutEvent        -- bus event for HITL timeout
        CrashRecoveryReport    -- recovery scan summary
        scan_for_recovery      -- scan task_state for suspended tasks
        build_timeout_events   -- build timeout events for timed-out tasks

    HITL Wiring (Epic 13.7 + 13.8 + 13.9):
        ResumeContext          -- structured context for Back resume
        RESUME_INSTRUCTIONS    -- per-type resume instruction text
        build_resume_context   -- assemble resume context from response + state
        HILModeConfig          -- complete config snapshot for a HITL mode
        get_hitl_relay_config  -- full HITL_RELAY mode configuration
        get_hitl_resolve_config -- full HITL_RESOLVE mode configuration
        validate_hitl_wiring   -- cross-layer consistency checks

    Constants:
        SUSPENSION_TIMEOUTS         -- REMOVED (V3 E0.2.1, use config accessor)
        MAX_SUSPENSIONS_PER_TASK    -- hard limit (2, backward-compat only)
        MAX_CONCURRENT_SUSPENSIONS  -- per-task concurrency limit (1)
"""

from k1.concierge.protocols.cancel_events import (
    TaskCancelEvent,
    TaskFailedCancelledEvent,
)
from k1.concierge.protocols.cancel_handler import CancellationHandler
from k1.concierge.protocols.cancellation import (
    CancellationToken,
    CancelReason,
    TaskCancelledError,
)
from k1.concierge.protocols.hitl import (
    HILRequest,
    HILResponse,
    SafetyBand,
    escalate_safety_band,
)

# E4.M1.4: legacy `hitl_coordinator` module deleted as part of the HIL
# unification hard cutover.  `HILCoordinator`, `HILCoordinatorConfig` and
# `HIL_TO_SUSPENSION` are no longer exported -- callers consume the
# unified HIL service from ``k1.hil`` instead.
from k1.concierge.protocols.hitl_flow import (
    ApprovalContext,
    ClarificationContext,
    HILFlowType,
    SelectionContext,
    build_approval_request,
    build_clarification_request,
    build_selection_request,
    parse_approval_resolution,
    parse_clarification_resolution,
    parse_selection_resolution,
)
from k1.concierge.protocols.hitl_persistence import (
    CrashRecoveryReport,
    HILTimeoutEvent,
    TaskStateEntry,
    TaskStatus,
    build_timeout_events,
    scan_for_recovery,
)
from k1.concierge.protocols.hitl_pipeline import (
    ApprovalResult,
    SelectionResult,
    apply_approval_modifications,
    build_resume_params_from_selection,
    detect_approval_required,
    process_approval_response,
    resolve_selection_to_params,
)
from k1.concierge.protocols.hitl_wiring import (
    RESUME_INSTRUCTIONS,
    HILModeConfig,
    ResumeContext,
    build_resume_context,
    get_hitl_relay_config,
    get_hitl_resolve_config,
    validate_hitl_wiring,
)
from k1.concierge.protocols.suspension import (
    MAX_CONCURRENT_SUSPENSIONS,
    MAX_SUSPENSIONS_PER_TASK,
    SuspensionLimitExceeded,
    SuspensionRequest,
    SuspensionResolution,
    SuspensionTimeoutError,
    SuspensionType,
)
from k1.concierge.protocols.suspension_events import TaskResumeEvent, TaskSuspendedEvent

# E4.M1.5: SuspensionManager relocated to ``k1.hil.suspension``.  No
# re-export here -- importing it through this package would create a
# circular dependency (``k1.hil.suspension`` already imports from
# ``k1.concierge.protocols.suspension``).  Update callers to import
# directly from ``k1.hil.suspension``.
from k1.concierge.protocols.weave_batcher import (
    WEAVE_BATCH_WINDOW_MS,
    WeaveBatcher,
    WeaveResult,
)
from k1.concierge.protocols.weave_state import (
    STATE_ACTION_TABLE,
    PendingResult,
    PendingResultsQueue,
    WeaveAction,
    get_weave_action,
)

__all__ = [
    # Cancellation token (Epic 12.1)
    "CancellationToken",
    "CancelReason",
    "TaskCancelledError",
    # Cancel events (Epic 12.2)
    "TaskCancelEvent",
    "TaskFailedCancelledEvent",
    # Cancel handler (Epic 12.2)
    "CancellationHandler",
    # Suspension protocol (Epic 12.3)
    "SuspensionType",
    "SuspensionRequest",
    "SuspensionResolution",
    "SuspensionLimitExceeded",
    "SuspensionTimeoutError",
    # V3 E0.2.1: SUSPENSION_TIMEOUTS removed (use config accessor)
    "MAX_SUSPENSIONS_PER_TASK",
    "MAX_CONCURRENT_SUSPENSIONS",
    # Suspension events (Epic 12.3)
    "TaskSuspendedEvent",
    "TaskResumeEvent",
    # E4.M1.5: SuspensionManager export removed -- import directly from
    # ``k1.hil.suspension`` instead.
    # Weave batcher (Epic 12.4)
    "WeaveBatcher",
    "WeaveResult",
    "WEAVE_BATCH_WINDOW_MS",
    # Weave state table (Epic 12.5)
    "WeaveAction",
    "PendingResult",
    "PendingResultsQueue",
    "get_weave_action",
    "STATE_ACTION_TABLE",
    # HITL types (Epic 13.1)
    "SafetyBand",
    "HILRequest",
    "HILResponse",
    # V3 E0.2.1: HIL_TIMEOUTS removed (use config accessor)
    "escalate_safety_band",
    # E4.M1.4: HILCoordinator / HILCoordinatorConfig / HIL_TO_SUSPENSION
    # exports removed -- the legacy coordinator was deleted in favour of
    # the unified ``HumanInTheLoopService`` (``k1.hil.service``).
    # HITL flow helpers (Epic 13.3)
    "HILFlowType",
    "ClarificationContext",
    "ApprovalContext",
    "SelectionContext",
    "build_clarification_request",
    "build_approval_request",
    "build_selection_request",
    "parse_clarification_resolution",
    "parse_approval_resolution",
    "parse_selection_resolution",
    # HITL pipeline (Epic 13.4 + 13.5)
    "detect_approval_required",
    "apply_approval_modifications",
    "process_approval_response",
    "ApprovalResult",
    "SelectionResult",
    "resolve_selection_to_params",
    "build_resume_params_from_selection",
    # HITL persistence (Epic 13.6)
    "TaskStatus",
    "TaskStateEntry",
    "HILTimeoutEvent",
    "CrashRecoveryReport",
    "scan_for_recovery",
    "build_timeout_events",
    # HITL wiring (Epic 13.7 + 13.8 + 13.9)
    "ResumeContext",
    "RESUME_INSTRUCTIONS",
    "build_resume_context",
    "HILModeConfig",
    "get_hitl_relay_config",
    "get_hitl_resolve_config",
    "validate_hitl_wiring",
]
