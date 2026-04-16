"""PipelineController -- top-level pipeline orchestrator [F03].

Owns stage sequencing, budget injection, cancel checking between stages,
delta emission, and micro-replan routing.

Design decisions
----------------
- PipelineController is a Layer 5 component (SS30.6).  It imports from
  Layer 1 (ports) and Layer 0 (types, plan_fsm, config, events).
- Stage services (SketchService, ExpandService, ValidateService,
  CommitService) are injected via constructor -- NOT created here.
  PipelineController does NOT instantiate services; that is
  PlannerFactory's responsibility (M6).
- PipelineController owns the PlanStateMachine instance and provides
  the ``_on_fsm_transition`` callback for delta/log emission.
- Direct I/O is limited to IDeltaEmitPort.emit() and
  IEventPort.emit() ONLY.  PipelineController does NOT perform LLM
  calls, tool discovery, or HIL interaction.

Invariants enforced
-------------------
- PLAN-03: CommitService is last stage; no LLM call in commit path.
- PLAN-04: Checks elapsed time at each stage transition (45s default).
- PLAN-11: Injects per-stage budget into PlannerLLMRequest.constraints.
- PLAN-12: Wraps execute() in try/except; uncaught -> FAILED + emit.

Import graph (Layer 5)
----------------------
k1.planner.pipeline_controller
  -> k1.planner.types        (DeltaPayload, StagePhase, PlannerError,
                               PlanCancelledError, PLANNER_AGENT_ID,
                               DELTA_STAGE_TRANSITION, SECTION_PIPELINE)
  -> k1.planner.plan_fsm     (PlanStateMachine, PlanState)
  -> k1.planner.config       (PlannerConfig)
  -> k1.planner.events       (TOPIC_PLAN_FAILED, TOPIC_PLAN_CANCELLED)
  -> k1.planner.ports        (IDeltaEmitPort, IEventPort)
  -> typing

NEVER import from planner_agent.py or factory.py (higher layers).

References
----------
- planner.md Section 5.2   (26-Step Pipeline Flow)
- planner.md Section 10    (Micro-Replan)
- planner.md Section 13.3  (Budget Injection)
- planner.md Section 17.2  (PipelineController ~80 tests)
- planner.md Section 23.2  (PLAN_START lifecycle)
- planner.md Section 23.3  (STAGE_TRANSITION lifecycle)
- planner.md Section 30.5.1 F03
- planner.md Section 30.6  (Dependency Layers)
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Set

from k1.planner.config import PlannerConfig
from k1.planner.events import (
    TOPIC_MICRO_REPLAN_READY,
    TOPIC_PLAN_CANCELLED,
    TOPIC_PLAN_FAILED,
    PlanCancelledPayload,
    PlanFailedPayload,
)
from k1.planner.plan_fsm import PlanState, PlanStateMachine
from k1.planner.ports.delta_emit_port import IDeltaEmitPort
from k1.planner.ports.event_port import IEventPort
from k1.planner.tracing import create_stage_context
from k1.planner.types import (
    DELTA_MICRO_REPLAN,
    DELTA_PLAN_CANCELLED,
    DELTA_PLAN_END,
    DELTA_STAGE_TRANSITION,
    PLANNER_AGENT_ID,
    SECTION_PIPELINE,
    VERDICT_APPROVED,
    VERDICT_REJECT,
    VERDICT_REVISE,
    DeltaPayload,
    ExpandedPlan,
    PlanCancelledError,
    PlannerConstraints,
    PlannerError,
    StageContext,
    StagePhase,
    ValidateRejectedError,
)

logger = logging.getLogger(__name__)


class PipelineController:
    """Top-level pipeline orchestrator (Section 17.2, SS30.5.1 F03).

    Owns stage sequencing, budget injection, cancel checking between
    stages, delta emission, and micro-replan routing.

    Constructor
    -----------
    Accepts 4 stage services (injected, not created), 2 port references,
    and the PlannerConfig.  Creates a ``PlanStateMachine`` with the
    ``_on_fsm_transition`` callback for delta/log emission.

    Per-plan state is reset via ``reset()`` at the start of each plan
    (PLAN_START, Section 23.2 step 4).

    Parameters
    ----------
    sketch : SketchService
        Stage 1 service (injected).
    expand : ExpandService
        Stage 2 service (injected).
    validate : ValidateService
        Stage 3 service (injected).
    commit : CommitService
        Stage 4 service (injected).
    delta_port : IDeltaEmitPort
        Fire-and-forget delta emission port.
    event_port : IEventPort
        Bidirectional event pub/sub port.
    config : PlannerConfig
        Planner configuration (budgets, timeouts, temperatures).

    Notes
    -----
    Stage services are typed as ``Any`` because concrete service classes
    (SketchService, ExpandService, ValidateService, CommitService) are
    implemented in later milestones.  When those classes exist, the type
    annotations will be updated to use the concrete types or their
    Protocols.  The constructor validates that all injected dependencies
    are not None.
    """

    __slots__ = (
        "_sketch",
        "_expand",
        "_validate",
        "_commit",
        "_delta_port",
        "_event_port",
        "_config",
        "_fsm",
        "_stage_token_usage",
        "_stage_cost",
        "_stage_latency",
        "_total_plan_tokens",
        "_tool_call_count",
        "_hil_round_count",
        "_current_request",
        "_plan_start_time",
        "_revise_count",
        "_active_cancel_check",
    )

    def __init__(
        self,
        sketch: Any,
        expand: Any,
        validate: Any,
        commit: Any,
        delta_port: IDeltaEmitPort,
        event_port: IEventPort,
        config: PlannerConfig,
    ) -> None:
        # -- Validate injected dependencies --
        if sketch is None:
            raise ValueError("PipelineController: sketch service must not be None")
        if expand is None:
            raise ValueError("PipelineController: expand service must not be None")
        if validate is None:
            raise ValueError("PipelineController: validate service must not be None")
        if commit is None:
            raise ValueError("PipelineController: commit service must not be None")
        if delta_port is None:
            raise ValueError("PipelineController: delta_port must not be None")
        if event_port is None:
            raise ValueError("PipelineController: event_port must not be None")
        if config is None:
            raise ValueError("PipelineController: config must not be None")

        # -- Service references (injected, not created) --
        self._sketch: Any = sketch
        self._expand: Any = expand
        self._validate: Any = validate
        self._commit: Any = commit

        # -- Port references --
        self._delta_port: IDeltaEmitPort = delta_port
        self._event_port: IEventPort = event_port

        # -- Configuration --
        self._config: PlannerConfig = config

        # -- FSM (owned, with callback wiring) --
        self._fsm: PlanStateMachine = PlanStateMachine(
            on_transition=self._on_fsm_transition,
        )

        # -- Per-plan state (reset per plan via reset()) --
        self._stage_token_usage: Dict[str, int] = {}
        self._stage_cost: Dict[str, float] = {}
        self._stage_latency: Dict[str, int] = {}
        self._total_plan_tokens: int = 0
        self._tool_call_count: int = 0
        self._hil_round_count: int = 0
        self._current_request: Any = None  # PlanRequest (set at plan start)
        self._plan_start_time: Optional[float] = None
        self._revise_count: int = 0
        self._active_cancel_check: Callable[[], bool] = lambda: False

    # -- Properties --

    @property
    def current_state(self) -> PlanState:
        """Current FSM state (read-only for external consumers).

        PlannerAgent reads this for lifecycle decisions.
        """
        return self._fsm.current_state

    @property
    def config(self) -> PlannerConfig:
        """Planner configuration (read-only)."""
        return self._config

    @property
    def stage_token_usage(self) -> Dict[str, int]:
        """Per-stage token usage (read-only copy).

        Returns a shallow copy to prevent external mutation.
        """
        return dict(self._stage_token_usage)

    @property
    def total_plan_tokens(self) -> int:
        """Total tokens consumed across all stages in current plan."""
        return self._total_plan_tokens

    @property
    def tool_call_count(self) -> int:
        """Tool calls consumed in current plan."""
        return self._tool_call_count

    @property
    def hil_round_count(self) -> int:
        """HIL interaction rounds consumed in current plan."""
        return self._hil_round_count

    @property
    def revise_count(self) -> int:
        """EXPAND revise loops consumed in current plan."""
        return self._revise_count

    @property
    def plan_start_time(self) -> Optional[float]:
        """Monotonic timestamp when current plan started (None if idle)."""
        return self._plan_start_time

    @property
    def current_request(self) -> Any:
        """Current PlanRequest being processed (None if idle)."""
        return self._current_request

    # -- reset() (Section 23.2 step 4, PLAN_START) --

    def reset(self) -> None:
        """Reset all per-plan state and FSM to IDLE.

        Called at PLAN_START (Section 23.2 step 4) before beginning
        a new plan.  Also called at PLAN_END (Section 23.4 step 3)
        after a plan reaches terminal state.

        FSM must be in a terminal state (COMPLETED, FAILED, CANCELLED)
        or IDLE before calling reset.  For first-plan case, FSM is
        already IDLE so reset is a no-op on the FSM.

        After reset:
          - ``_stage_token_usage`` = {SKETCH: 0, EXPAND: 0, VALIDATE: 0, COMMIT: 0}
          - ``_stage_cost`` = {SKETCH: 0.0, EXPAND: 0.0, VALIDATE: 0.0, COMMIT: 0.0}
          - ``_stage_latency`` = {SKETCH: 0, EXPAND: 0, VALIDATE: 0, COMMIT: 0}
          - ``_total_plan_tokens`` = 0
          - ``_tool_call_count`` = 0
          - ``_hil_round_count`` = 0
          - ``_current_request`` = None
          - ``_plan_start_time`` = None
          - ``_revise_count`` = 0
          - FSM state = IDLE
        """
        # Reset FSM if in terminal state (skip if already IDLE)
        if self._fsm.current_state != PlanState.IDLE:
            self._fsm.reset()

        # Reset per-plan counters (Section 23.2 step 4)
        self._stage_token_usage = {
            StagePhase.SKETCH.value: 0,
            StagePhase.EXPAND.value: 0,
            StagePhase.VALIDATE.value: 0,
            StagePhase.COMMIT.value: 0,
        }
        self._stage_cost = {
            StagePhase.SKETCH.value: 0.0,
            StagePhase.EXPAND.value: 0.0,
            StagePhase.VALIDATE.value: 0.0,
            StagePhase.COMMIT.value: 0.0,
        }
        self._stage_latency = {
            StagePhase.SKETCH.value: 0,
            StagePhase.EXPAND.value: 0,
            StagePhase.VALIDATE.value: 0,
            StagePhase.COMMIT.value: 0,
        }
        self._total_plan_tokens = 0
        self._tool_call_count = 0
        self._hil_round_count = 0
        self._current_request = None
        self._plan_start_time = None
        self._revise_count = 0
        self._active_cancel_check = lambda: False

    # -- FSM callback (Section 17.2, delta/log emission) --

    def _on_fsm_transition(
        self,
        from_state: PlanState,
        to_state: PlanState,
        trigger: str,
    ) -> None:
        """Callback invoked by PlanStateMachine after each transition.

        Emits a stage_transition delta via IDeltaEmitPort and logs the
        transition.  Wrapped in try/except so delta emission failures
        never block pipeline execution.

        Parameters
        ----------
        from_state : PlanState
            State before the transition.
        to_state : PlanState
            State after the transition.
        trigger : str
            Description of what caused the transition.
        """
        try:
            # Build trace_id from current request if available
            trace_id = ""
            if self._current_request is not None:
                trace_id = getattr(self._current_request, "trace_id", "")

            # Emit stage_transition delta (fire-and-forget)
            delta = DeltaPayload(
                agent_id=PLANNER_AGENT_ID,
                delta_type=DELTA_STAGE_TRANSITION,
                section=SECTION_PIPELINE,
                data={
                    "from_state": from_state.value,
                    "to_state": to_state.value,
                    "trigger": trigger,
                },
                trace_id=trace_id or "unknown",
            )
            self._delta_port.emit(delta)

            # Structured log (Section 22.2.1)
            logger.info(
                "fsm.transition",
                extra={
                    "from_state": from_state.value,
                    "to_state": to_state.value,
                    "trigger": trigger,
                    "trace_id": trace_id,
                    "request_id": (
                        getattr(self._current_request, "request_id", "")
                        if self._current_request is not None
                        else ""
                    ),
                },
            )
        except Exception:
            # Delta emission MUST NOT block pipeline execution.
            # Log the failure and continue silently.
            logger.warning(
                "fsm.transition_callback_failed",
                exc_info=True,
                extra={
                    "from_state": from_state.value if from_state else "",
                    "to_state": to_state.value if to_state else "",
                    "trigger": trigger,
                },
            )

    # -- execute() (Section 5.2 steps 4-26, Issue 2.2.2) --

    async def execute(
        self,
        request: Any,
        cancel_check: Callable[[], bool],
    ) -> Any:
        """Run the full 4-stage pipeline: SKETCH -> EXPAND -> VALIDATE -> COMMIT.

        Implements the 14-step orchestration loop defined in Section 5.2
        (steps 4-26) and the implementation plan Issue 2.2.2.

        Parameters
        ----------
        request : PlanRequest
            Incoming plan request from Orchestrator (typed as ``Any``
            because concrete PlanRequest lives in ``k1.orchestrator.types``).
        cancel_check : Callable[[], bool]
            Cooperative cancel flag.  Returns True when the request has
            been cancelled by Orchestrator via ``send_cancel()``.

        Returns
        -------
        CommittedPlan
            Successfully committed plan (typed as ``Any``).

        Raises
        ------
        PlanCancelledError
            If ``cancel_check()`` returns True between stages.
        ValidateRejectedError
            If validation rejects the plan after retry.
        PlannerError
            If the pipeline times out (PLAN-04 defense-in-depth).
        Exception
            Any uncaught exception is wrapped by PLAN-12 error handling
            (``force_failed()`` + ``plan.failed.v1``) then re-raised.
        """
        try:
            # -- Step 1: Reset per-plan state (Section 23.2 step 4) --
            self.reset()

            # -- Step 2: Initialise plan --
            self._current_request = request
            self._plan_start_time = time.monotonic()
            self._active_cancel_check = cancel_check

            # FSM IDLE -> SKETCHING
            self._fsm.transition(
                PlanState.SKETCHING,
                trigger="plan_start",
            )

            # -- Step 3: SKETCH --
            ctx = self._create_stage_context(StagePhase.SKETCH)
            sketch_result = await self._sketch.execute(request, ctx)

            # -- Step 4: Cancel + timeout check --
            self._check_cancel(cancel_check, StagePhase.SKETCH.value)
            self._check_timeout(StagePhase.SKETCH.value)

            # -- Step 5: FSM SKETCHING -> EXPANDING --
            self._fsm.transition(
                PlanState.EXPANDING,
                trigger="sketch_complete",
            )

            # -- Steps 6-10: EXPAND + VALIDATE loop (revise routing) --
            expanded_plan: Any = None
            verdict: Any = None

            while True:
                # -- Step 6: EXPAND --
                ctx = self._create_stage_context(StagePhase.EXPAND)
                expanded_plan = await self._expand.execute(sketch_result, ctx)

                # -- Step 7: Cancel + timeout check --
                self._check_cancel(cancel_check, StagePhase.EXPAND.value)
                self._check_timeout(StagePhase.EXPAND.value)

                # -- Step 8: FSM EXPANDING -> VALIDATING --
                self._fsm.transition(
                    PlanState.VALIDATING,
                    trigger="expand_complete",
                )

                # -- Step 9: VALIDATE --
                ctx = self._create_stage_context(StagePhase.VALIDATE)
                verdict = await self._validate.execute(expanded_plan, ctx)

                # -- Step 10: Verdict routing (Section 5.2 step 15) --
                verdict_status = getattr(verdict, "status", None)

                if verdict_status == VERDICT_APPROVED:
                    break  # proceed to COMMIT

                if verdict_status in (VERDICT_REVISE, VERDICT_REJECT) and self._revise_count < 1:
                    # First revise/reject: retry EXPAND once
                    self._revise_count += 1
                    self._fsm.transition(
                        PlanState.EXPANDING,
                        trigger=f"verdict_{verdict_status}",
                    )
                    continue

                if verdict_status == VERDICT_REVISE:
                    # Second revise: treat as approved (best-effort)
                    break  # proceed to COMMIT

                # Second reject (or unexpected status) -> FAILED
                self._fsm.force_failed(
                    trigger=f"verdict_{verdict_status}_final",
                )
                raise ValidateRejectedError(
                    f"Plan rejected after retry: {verdict_status}",
                    stage=StagePhase.VALIDATE.value,
                    request_id=getattr(request, "request_id", ""),
                    trace_id=getattr(request, "trace_id", ""),
                )

            # -- Step 10b: Cancel + timeout check (checkpoint 4) --
            self._check_cancel(cancel_check, StagePhase.VALIDATE.value)
            self._check_timeout(StagePhase.VALIDATE.value)

            # -- Step 11: FSM VALIDATING -> COMMITTING --
            self._fsm.transition(
                PlanState.COMMITTING,
                trigger="verdict_approved",
            )

            # -- Step 12: COMMIT --
            ctx = self._create_stage_context(StagePhase.COMMIT)
            committed = await self._commit.execute(
                expanded_plan,
                verdict,
                ctx,
            )

            # -- Step 13: FSM COMMITTING -> COMPLETED --
            self._fsm.transition(
                PlanState.COMPLETED,
                trigger="commit_complete",
            )

            # -- Step 14: Emit plan_end delta --
            self._emit_plan_end_delta()

            return committed

        except PlanCancelledError:
            # Cancel already handled: FSM transitioned to CANCELLED
            # by _check_cancel.  Re-raise without plan.failed.v1.
            raise
        except Exception as exc:
            # PLAN-12: uncaught -> force_failed + plan.failed.v1 + re-raise
            if not self._fsm.current_state.is_terminal:
                self._fsm.force_failed(trigger="uncaught_error")
            if not getattr(exc, "_plan_failed_emitted", False):
                self._emit_plan_failed(exc)
            raise

    async def micro_replan(
        self,
        request: Any,
        cancel_check: Callable[[], bool],
    ) -> Optional[Any]:
        """Run abbreviated micro-replan pipeline (Epic 5.1).

        Abbreviated flow (Section 10.3):
          MICRO_SKETCH -> MICRO_EXPAND -> MICRO_VALIDATE -> COMMIT

        Key differences from full pipeline (Section 10.3.1):
          - 10s total (vs 45s), ~2K tokens (vs ~3.5K)
          - up to 3 tool calls (vs 6)
          - no HIL interaction (PLAN-12, Section 10.5.4)
          - no revise loop (Section 10.6.2)
          - verdict "revise" treated as "approved" (best-effort)
          - verdict "reject" returns ``None``
          - ALL failures -> returns ``None`` (no ``plan.failed.v1``)
          - delivery is synchronous return (not event bus)
          - PLAN-12: replacement steps only (completed steps frozen)

        Parameters
        ----------
        request : MicroReplanRequest
            Mid-execution replan request with completed results,
            remaining steps, discoveries, and optional failure context.
        cancel_check : Callable[[], bool]
            Cooperative cancel closure over PlannerAgent cancel set.

        Returns
        -------
        Optional[CommittedPlan]
            Committed replacement plan on success, else ``None``.
            Orchestrator continues original plan when None returned.
        """
        try:
            # -- Step 1: Validate MicroReplanRequest (defense-in-depth) --
            original_plan_id = getattr(request, "original_plan_id", "")
            remaining_steps = getattr(request, "remaining_steps", [])
            trace_id = getattr(request, "trace_id", "")

            if not original_plan_id or not remaining_steps or not trace_id:
                logger.warning(
                    "pipeline.micro_replan_invalid_request",
                    extra={
                        "has_original_plan_id": bool(original_plan_id),
                        "remaining_step_count": len(remaining_steps),
                        "has_trace_id": bool(trace_id),
                    },
                )
                return None

            # -- Step 2: Reset per-plan state --
            self.reset()

            # -- Step 3: Initialise micro plan context --
            self._current_request = request
            self._plan_start_time = time.monotonic()
            self._active_cancel_check = cancel_check

            # -- Step 4: Overlap heuristic revalidation (advisory) --
            self._validate_overlap(request)

            # FSM IDLE -> MICRO_SKETCH
            self._fsm.transition(
                PlanState.MICRO_SKETCH,
                trigger="micro_replan_start",
            )

            # -- Step 5: Emit micro_replan_started delta --
            self._emit_micro_replan_started_delta(request)

            # -- Step 6: MICRO_SKETCH --
            self._check_micro_timeout("MICRO_SKETCH")
            sketch_ctx = self._build_micro_stage_context(
                cancel_check,
                StagePhase.SKETCH,
            )
            micro_sketch_result = await self._sketch.micro_execute(
                request,
                sketch_ctx,
            )

            # -- Step 7: Cancel + timeout check -> transition --
            self._check_cancel(cancel_check, "MICRO_SKETCH")
            self._check_micro_timeout("MICRO_SKETCH")
            self._fsm.transition(
                PlanState.MICRO_EXPAND,
                trigger="micro_sketch_complete",
            )

            # -- Step 8: MICRO_EXPAND --
            expand_ctx = self._build_micro_stage_context(
                cancel_check,
                StagePhase.EXPAND,
            )
            completed_results = getattr(request, "completed_results", {})
            micro_expanded = await self._expand.micro_execute(
                micro_sketch_result,
                completed_results,
                expand_ctx,
            )

            # -- Step 9: PLAN-12 enforcement --
            completed_ids = set(completed_results.keys())
            micro_expanded = self._enforce_plan12(
                micro_expanded,
                completed_ids,
            )

            # -- Step 10: Cancel + timeout check -> transition --
            self._check_cancel(cancel_check, "MICRO_EXPAND")
            self._check_micro_timeout("MICRO_EXPAND")
            self._fsm.transition(
                PlanState.MICRO_VALIDATE,
                trigger="micro_expand_complete",
            )

            # -- Step 11: MICRO_VALIDATE --
            validate_ctx = self._build_micro_stage_context(
                cancel_check,
                StagePhase.VALIDATE,
            )
            verdict = await self._validate.micro_execute(
                micro_expanded,
                validate_ctx,
                completed_step_ids=completed_ids,
            )
            verdict_status = getattr(verdict, "status", None)

            if verdict_status == VERDICT_REJECT:
                self._fsm.force_failed(trigger="micro_verdict_reject")
                return None

            if verdict_status not in (VERDICT_APPROVED, VERDICT_REVISE):
                self._fsm.force_failed(
                    trigger=f"micro_verdict_{verdict_status}",
                )
                return None

            # "approved" or "revise" (treated as approved) -> COMMIT
            self._fsm.transition(
                PlanState.COMMITTING,
                trigger=f"micro_verdict_{verdict_status}",
            )

            # -- Step 12: COMMIT (shared CommitService) --
            commit_ctx = self._build_micro_stage_context(
                cancel_check,
                StagePhase.COMMIT,
            )
            committed = await self._commit.execute(
                micro_expanded,
                verdict,
                commit_ctx,
            )

            self._fsm.transition(
                PlanState.COMPLETED,
                trigger="micro_commit_complete",
            )

            # -- Step 13: Telemetry-only event (Learning Loop) --
            self._emit_micro_replan_telemetry(committed)

            self._emit_plan_end_delta()
            return committed

        except PlanCancelledError:
            # Best-effort path for micro-replan: return None on cancel.
            return None
        except Exception:
            # Best-effort path for micro-replan: no plan.failed.v1 emission.
            if not self._fsm.current_state.is_terminal:
                self._fsm.force_failed(trigger="micro_uncaught_error")
            logger.warning(
                "pipeline.micro_replan_failed",
                exc_info=True,
            )
            return None

    # -- Private helpers (2.2.2 basic implementations) --

    def _elapsed_ms(self) -> int:
        """Compute elapsed milliseconds since plan start.

        Returns 0 if ``_plan_start_time`` is None (plan not yet started).
        """
        if self._plan_start_time is None:
            return 0
        return int((time.monotonic() - self._plan_start_time) * 1000)

    def _check_cancel(
        self,
        cancel_check: Callable[[], bool],
        stage: str,
    ) -> None:
        """Check cooperative cancel flag between stages (Issue 2.2.4).

        If ``cancel_check()`` returns True:
          1. FSM -> CANCELLED via ``force_cancelled()``.
          2. Emit ``plan.cancelled.v1`` event with PlanCancelledPayload.
          3. Emit delta ``{type: "plan_cancelled", request_id, reason}``.
          4. Raise ``PlanCancelledError`` to unwind the pipeline.

        5 cancel checkpoints (Section 24.2.2):
          (1) pre-execution at mailbox dequeue (PlannerAgent, before lock)
          (2) between SKETCH and EXPAND
          (3) between EXPAND and VALIDATE
          (4) between VALIDATE and COMMIT
          (5) before WAL persist in CommitService

        PipelineController handles checkpoints 2, 3, 4.  Checkpoints 1
        and 5 are the responsibility of PlannerAgent and CommitService
        respectively.

        Cancel timing (Section 24.2.1): cooperative, NOT preemptive.
        If an LLM call is in flight, cancel is not checked until the
        LLM returns (or times out).

        Parameters
        ----------
        cancel_check : Callable[[], bool]
            Returns True if the request has been cancelled.
        stage : str
            Current stage name (for error attribution).

        Raises
        ------
        PlanCancelledError
            If ``cancel_check()`` returns True.
        """
        if cancel_check():
            request_id = (
                getattr(self._current_request, "request_id", "")
                if self._current_request is not None
                else ""
            )
            trace_id = (
                getattr(self._current_request, "trace_id", "")
                if self._current_request is not None
                else ""
            )

            # 1. FSM -> CANCELLED
            self._fsm.force_cancelled(
                trigger=f"cancelled_between_{stage}",
            )

            # 2. Emit plan.cancelled.v1 event (fire-and-forget)
            try:
                payload = PlanCancelledPayload(
                    request_id=request_id or "unknown",
                    reason="cancelled_between_stages",
                    stage=stage,
                    trace_id=trace_id or "unknown",
                )
                self._event_port.emit(TOPIC_PLAN_CANCELLED, payload)
            except Exception:
                logger.warning(
                    "pipeline.plan_cancelled_event_failed",
                    exc_info=True,
                )

            # 3. Emit plan_cancelled delta (fire-and-forget)
            try:
                delta = DeltaPayload(
                    agent_id=PLANNER_AGENT_ID,
                    delta_type=DELTA_PLAN_CANCELLED,
                    section=SECTION_PIPELINE,
                    data={
                        "request_id": request_id,
                        "reason": "cancelled_between_stages",
                        "stage": stage,
                    },
                    trace_id=trace_id or "unknown",
                )
                self._delta_port.emit(delta)
            except Exception:
                logger.warning(
                    "pipeline.plan_cancelled_delta_failed",
                    exc_info=True,
                )

            # 4. Raise to unwind the pipeline
            raise PlanCancelledError(
                f"Plan cancelled between stages at {stage}",
                stage=stage,
                request_id=request_id,
                trace_id=trace_id,
            )

    def _check_timeout(self, stage: str) -> None:
        """Check pipeline timeout (PLAN-04 defense-in-depth).

        Basic implementation for Issue 2.2.2.  Enhanced in Issue 2.2.6
        with ``plan.failed.v1`` event emission.

        Parameters
        ----------
        stage : str
            Current stage name (for error attribution).

        Raises
        ------
        PlannerError
            If elapsed time exceeds ``config.pipeline_timeout_ms``.
        """
        elapsed_ms = self._elapsed_ms()
        if elapsed_ms > self._config.pipeline_timeout_ms:
            self._fsm.force_failed(trigger="pipeline_timeout")

            request_id = (
                getattr(self._current_request, "request_id", "")
                if self._current_request is not None
                else ""
            )
            trace_id = (
                getattr(self._current_request, "trace_id", "")
                if self._current_request is not None
                else ""
            )
            error_message = (
                f"Pipeline exceeded {self._config.pipeline_timeout_ms}ms "
                f"(elapsed: {elapsed_ms}ms)"
            )

            # Issue 2.2.6: emit timeout-specific plan.failed payload immediately.
            try:
                payload = PlanFailedPayload(
                    request_id=request_id or "unknown",
                    stage=stage or "unknown",
                    error_code="PIPELINE_TIMEOUT",
                    error_message=error_message,
                    tokens_used=self._total_plan_tokens,
                    duration_ms=elapsed_ms,
                    trace_id=trace_id or "unknown",
                )
                self._event_port.emit(TOPIC_PLAN_FAILED, payload)
            except Exception:
                logger.warning(
                    "pipeline.timeout_plan_failed_event_failed",
                    exc_info=True,
                )

            err = PlannerError(
                error_message,
                stage=stage,
                request_id=request_id,
                trace_id=trace_id,
            )
            # Signal outer PLAN-12 wrapper to avoid double-emitting plan.failed.
            setattr(err, "_plan_failed_emitted", True)
            raise err

    # -- Budget injection (Issue 2.2.3, Section 13.3, PLAN-11) --

    def _get_stage_budget(
        self,
        stage: StagePhase,
    ) -> Optional[PlannerConstraints]:
        """Return per-stage LLM budget from PlannerConfig (PLAN-11).

        Returns ``PlannerConstraints`` for LLM-calling stages (SKETCH,
        EXPAND, VALIDATE) and ``None`` for COMMIT (PLAN-03: no LLM calls
        in commit path).

        The budget values are read from PlannerConfig, not hardcoded.
        Stage services MUST use the injected budget.

        Parameters
        ----------
        stage : StagePhase
            Pipeline stage to look up budget for.

        Returns
        -------
        Optional[PlannerConstraints]
            Per-stage LLM constraints, or ``None`` for COMMIT.

        References
        ----------
        - planner.md Section 13.3.1 (PipelineController Budget Injection)
        - planner.md Section 13.3 Budget Table
        """
        cfg = self._config
        if stage == StagePhase.SKETCH:
            return PlannerConstraints(
                max_tokens=cfg.sketch_max_tokens,
                timeout_ms=cfg.sketch_timeout_ms,
                temperature=cfg.sketch_temperature,
            )
        if stage == StagePhase.EXPAND:
            return PlannerConstraints(
                max_tokens=cfg.expand_max_tokens,
                timeout_ms=cfg.expand_timeout_ms,
                temperature=cfg.expand_temperature,
            )
        if stage == StagePhase.VALIDATE:
            return PlannerConstraints(
                max_tokens=cfg.validate_max_tokens,
                timeout_ms=cfg.validate_timeout_ms,
                temperature=cfg.validate_temperature,
            )
        # COMMIT: no LLM calls (PLAN-03)
        return None

    def _get_micro_stage_budget(
        self,
        stage: StagePhase,
    ) -> Optional[PlannerConstraints]:
        """Return per-stage LLM budget for micro-replan (Section 10.3.6).

        Micro-replan uses a separate, tighter budget table.  Temperatures
        match the full pipeline (same creative/precision trade-offs).

        Parameters
        ----------
        stage : StagePhase
            Micro-replan stage (SKETCH/EXPAND/VALIDATE).

        Returns
        -------
        Optional[PlannerConstraints]
            Per-stage micro-replan constraints, or ``None`` for COMMIT.
        """
        cfg = self._config
        if stage == StagePhase.SKETCH:
            return PlannerConstraints(
                max_tokens=cfg.micro_sketch_max_tokens,
                timeout_ms=cfg.micro_sketch_timeout_ms,
                temperature=cfg.sketch_temperature,
            )
        if stage == StagePhase.EXPAND:
            return PlannerConstraints(
                max_tokens=cfg.micro_expand_max_tokens,
                timeout_ms=cfg.micro_expand_timeout_ms,
                temperature=cfg.expand_temperature,
            )
        if stage == StagePhase.VALIDATE:
            return PlannerConstraints(
                max_tokens=cfg.micro_validate_max_tokens,
                timeout_ms=cfg.micro_validate_timeout_ms,
                temperature=cfg.validate_temperature,
            )
        # COMMIT: no LLM calls (PLAN-03)
        return None

    def _record_llm_call(
        self,
        stage: StagePhase,
        response: Any,
    ) -> None:
        """Record token usage from an LLM response (Section 13.3.3).

        Updates ``_stage_token_usage``, ``_total_plan_tokens``, and
        ``_stage_latency`` from the PlannerLLMResponse metadata.

        Expected metadata structure (dict):
            ``{"usage": {"total_tokens": int}, "latency_ms": int}``

        Parameters
        ----------
        stage : StagePhase
            The pipeline stage that made the LLM call.
        response : PlannerLLMResponse
            Model Hub response containing ``metadata`` dict with
            ``usage.total_tokens`` and ``latency_ms``.
        """
        metadata = getattr(response, "metadata", None)
        if metadata is None:
            return

        # PlannerLLMResponse.metadata is Dict[str, Any]
        if isinstance(metadata, dict):
            usage = metadata.get("usage", {})
            total_tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
            latency_ms = metadata.get("latency_ms", 0)
        else:
            # Defensive: handle attribute-style metadata
            usage = getattr(metadata, "usage", None)
            total_tokens = getattr(usage, "total_tokens", 0) if usage is not None else 0
            latency_ms = getattr(metadata, "latency_ms", 0)

        stage_key = stage.value
        self._stage_token_usage[stage_key] = (
            self._stage_token_usage.get(stage_key, 0) + total_tokens
        )
        self._total_plan_tokens += total_tokens
        self._stage_latency[stage_key] = self._stage_latency.get(stage_key, 0) + latency_ms

    def _create_stage_context(
        self,
        stage: StagePhase,
    ) -> StageContext:
        """Create StageContext for full pipeline stage execution (Issue 2.2.7).

        This method constructs a *fresh* StageContext at each stage boundary
        so remaining timeout and token budget shrink as the pipeline advances.
        A reusable helper (`k1.planner.tracing.create_stage_context`) computes
        common fields; this method injects per-stage budget metadata.
        """
        base_ctx = create_stage_context(
            request=self._current_request,
            config=self._config,
            elapsed_ms=self._elapsed_ms(),
            tokens_used=self._total_plan_tokens,
            cancel_check=self._active_cancel_check,
        )
        return replace(
            base_ctx,
            stage_budget=self._get_stage_budget(stage),
        )

    def _build_stage_context(
        self,
        cancel_check: Callable[[], bool],
        stage: StagePhase,
    ) -> StageContext:
        """Backward-compatible wrapper around ``_create_stage_context``.

        New code should call ``_create_stage_context(stage)`` directly.
        This wrapper remains to preserve existing test and callsite
        compatibility while Issue 2.2.7 migrates stage-context plumbing.

        Parameters
        ----------
        cancel_check : Callable[[], bool]
            Cooperative cancel flag forwarded to StageContext.
        stage : StagePhase
            Pipeline stage for which to build context.

        Returns
        -------
        StageContext
            Context with remaining time, token budget, stage budget, and
            cancel flag.
        """
        self._active_cancel_check = cancel_check
        return self._create_stage_context(stage)

    def _build_micro_stage_context(
        self,
        cancel_check: Callable[[], bool],
        stage: StagePhase,
    ) -> StageContext:
        """Build StageContext for micro-replan with micro budgets.

        Uses micro timeout/token envelopes from PlannerConfig:
        ``micro_replan_timeout_ms`` and ``micro_replan_max_tokens``.
        """
        elapsed_ms = self._elapsed_ms()
        remaining_ms = max(1, self._config.micro_replan_timeout_ms - elapsed_ms)
        remaining_tokens = max(
            0,
            self._config.micro_replan_max_tokens - self._total_plan_tokens,
        )
        return StageContext(
            request_id=(
                getattr(self._current_request, "request_id", "")
                if self._current_request is not None
                else "unknown"
            ),
            trace_id=(
                getattr(self._current_request, "trace_id", "")
                if self._current_request is not None
                else "unknown"
            ),
            timeout_remaining_ms=remaining_ms,
            token_budget_remaining=remaining_tokens,
            cancel_check=cancel_check,
            stage_budget=self._get_micro_stage_budget(stage),
        )

    # -- Micro-replan helpers (Epic 5.1) --

    def _check_micro_timeout(self, stage: str) -> None:
        """Check micro-replan timeout budget (defense-in-depth).

        The outer 10s timeout is enforced by the caller
        (``asyncio.wait_for``).  This is a defence-in-depth check:
        if ``timeout_remaining_ms <= 0`` before a stage starts, skip
        remaining stages by returning ``None`` (via raising PlannerError).

        Parameters
        ----------
        stage : str
            Current micro stage name (for logging).

        Raises
        ------
        PlannerError
            If elapsed time exceeds ``micro_replan_timeout_ms``.
        """
        elapsed_ms = self._elapsed_ms()
        if elapsed_ms > self._config.micro_replan_timeout_ms:
            raise PlannerError(
                f"Micro-replan budget exhausted before {stage} "
                f"(elapsed: {elapsed_ms}ms, budget: "
                f"{self._config.micro_replan_timeout_ms}ms)",
                stage=stage,
                request_id=(
                    getattr(self._current_request, "request_id", "")
                    if self._current_request is not None
                    else ""
                ),
                trace_id=(
                    getattr(self._current_request, "trace_id", "")
                    if self._current_request is not None
                    else ""
                ),
            )

    def _validate_overlap(self, request: Any) -> bool:
        """Revalidate discovery-overlap heuristic (Section 10.2.2).

        Defense-in-depth check: the Orchestrator's MicroReplanCheckpoint
        already validated overlap before calling micro_replan.  We
        re-check here as advisory logging -- mismatch is logged but
        does NOT block execution (trust caller).

        Algorithm (3-way field match):
          For each discovery.field vs each step.params key:
            1. exact match (case-insensitive)
            2. substring forward (discovery.field in param_name)
            3. substring reverse (param_name in discovery.field)

        Returns
        -------
        bool
            True if overlap detected, False otherwise.
        """
        discoveries: List[Any] = getattr(request, "discoveries", []) or []
        remaining_steps: List[Any] = getattr(request, "remaining_steps", []) or []

        if not discoveries:
            logger.info(
                "micro_replan.no_discoveries_for_overlap_check",
                extra={
                    "request_id": getattr(request, "request_id", ""),
                },
            )
            return False

        for disc in discoveries:
            disc_field = getattr(disc, "field", "")
            if not disc_field:
                continue
            disc_lower = disc_field.lower()

            for step in remaining_steps:
                params: Dict[str, Any] = getattr(step, "params", {}) or {}
                for param_name in params:
                    param_lower = param_name.lower()
                    # 3-way match
                    if (
                        disc_lower == param_lower
                        or disc_lower in param_lower
                        or param_lower in disc_lower
                    ):
                        logger.info(
                            "micro_replan.overlap_detected",
                            extra={
                                "discovery_field": disc_field,
                                "step_id": getattr(step, "id", ""),
                                "param_name": param_name,
                                "request_id": getattr(request, "request_id", ""),
                            },
                        )
                        return True

        logger.info(
            "micro_replan.no_overlap_on_recheck",
            extra={
                "request_id": getattr(request, "request_id", ""),
                "discovery_count": len(discoveries),
                "remaining_step_count": len(remaining_steps),
            },
        )
        return False

    def _enforce_plan12(
        self,
        replacement_plan: ExpandedPlan,
        completed_ids: Set[str],
    ) -> ExpandedPlan:
        """Enforce PLAN-12: replacement steps only (Section 10.5.1).

        Validates:
          (a) No replacement step.id overlaps with any completed step_id.
          (b) Replacement step deps referencing completed step_ids are
              valid (those steps exist in completed_results).

        On violation: log error, strip offending references, return
        cleaned plan (defense-in-depth -- should not happen if prompt
        instructs correctly).

        Parameters
        ----------
        replacement_plan : ExpandedPlan
            Expanded plan from micro-EXPAND (replacement steps only).
        completed_ids : Set[str]
            Step IDs that have already completed (frozen).

        Returns
        -------
        ExpandedPlan
            Cleaned plan with offending references removed (may be
            identical to input if no violations found).
        """
        violations_found = False
        cleaned_steps = []

        for step in replacement_plan.steps:
            step_id = getattr(step, "id", "")
            if step_id in completed_ids:
                # Violation (a): replacement step overlaps completed step
                logger.error(
                    "plan12.replacement_step_overlaps_completed",
                    extra={
                        "step_id": step_id,
                        "request_id": (
                            getattr(self._current_request, "request_id", "")
                            if self._current_request is not None
                            else ""
                        ),
                    },
                )
                violations_found = True
                continue  # Strip offending step
            cleaned_steps.append(step)

        if not cleaned_steps:
            # All steps violated PLAN-12 -- edge case
            logger.error("plan12.all_replacement_steps_stripped")
            return replacement_plan  # Return original for caller to handle

        # Validate dependency references
        replacement_ids = {getattr(s, "id", "") for s in cleaned_steps}
        cleaned_deps: Dict[str, List[str]] = {}

        for step_id, dep_list in replacement_plan.dependencies.items():
            if step_id not in replacement_ids:
                continue  # Stripped step
            valid_deps = []
            for dep in dep_list:
                if dep in replacement_ids:
                    # Dep to another replacement step -- always valid
                    valid_deps.append(dep)
                elif dep in completed_ids:
                    # Cross-boundary dep to completed step -- valid
                    # semantically but ExpandedPlan only stores
                    # intra-plan deps.  Orchestrator tracks cross-
                    # boundary deps separately.  Log for telemetry.
                    logger.info(
                        "plan12.cross_boundary_dep_acknowledged",
                        extra={
                            "step_id": step_id,
                            "dep_to_completed": dep,
                        },
                    )
                else:
                    logger.error(
                        "plan12.dangling_dependency_stripped",
                        extra={
                            "step_id": step_id,
                            "dangling_dep": dep,
                        },
                    )
                    violations_found = True
            cleaned_deps[step_id] = valid_deps

        if not violations_found:
            return replacement_plan

        # Rebuild ExpandedPlan with cleaned data.
        # Use __class__ constructor to respect frozen dataclass.
        return ExpandedPlan(
            steps=cleaned_steps,
            dependencies=cleaned_deps,
            tool_mappings={
                sid: replacement_plan.tool_mappings[sid]
                for sid in replacement_ids
                if sid in replacement_plan.tool_mappings
            },
            rationale=replacement_plan.rationale,
        )

    def _emit_micro_replan_started_delta(self, request: Any) -> None:
        """Emit micro_replan_started delta at the beginning of micro-replan.

        Contains original_plan_id, remaining_step_count, discovery_count
        and trigger type for observability.

        Fire-and-forget: failure is logged but does NOT block execution.
        """
        try:
            trace_id = getattr(request, "trace_id", "") or "unknown"
            original_plan_id = getattr(request, "original_plan_id", "")
            remaining_steps = getattr(request, "remaining_steps", []) or []
            discoveries = getattr(request, "discoveries", []) or []
            failure_ctx = getattr(request, "failure_context", None)
            trigger = "failure" if failure_ctx is not None else "discovery"

            delta = DeltaPayload(
                agent_id=PLANNER_AGENT_ID,
                delta_type=DELTA_MICRO_REPLAN,
                section=SECTION_PIPELINE,
                data={
                    "type": "micro_replan_started",
                    "original_plan_id": original_plan_id,
                    "remaining_step_count": len(remaining_steps),
                    "discovery_count": len(discoveries),
                    "trigger": trigger,
                },
                trace_id=trace_id,
            )
            self._delta_port.emit(delta)
        except Exception:
            logger.warning(
                "pipeline.micro_replan_started_delta_failed",
                exc_info=True,
            )

    def _emit_micro_replan_telemetry(self, committed: Any) -> None:
        """Emit ``k1.planner.micro_replan.ready.v1`` telemetry event.

        TELEMETRY-ONLY: consumed by Learning Loop, NOT by Orchestrator.
        Orchestrator receives the CommittedPlan via the synchronous
        return value of ``micro_replan()``.

        Fire-and-forget: failure does NOT block execution.
        """
        try:
            trace_id = ""
            if self._current_request is not None:
                trace_id = getattr(self._current_request, "trace_id", "")

            payload = {
                "plan_id": getattr(committed, "plan_id", ""),
                "request_id": getattr(committed, "request_id", ""),
                "original_plan_id": (
                    getattr(self._current_request, "original_plan_id", "")
                    if self._current_request is not None
                    else ""
                ),
                "step_count": len(getattr(committed, "steps", [])),
                "duration_ms": self._elapsed_ms(),
                "total_tokens": self._total_plan_tokens,
                "trace_id": trace_id or "unknown",
            }
            self._event_port.emit(TOPIC_MICRO_REPLAN_READY, payload)
        except Exception:
            logger.warning(
                "pipeline.micro_replan_telemetry_failed",
                exc_info=True,
            )

    def _emit_plan_end_delta(self) -> None:
        """Emit plan_end delta after successful pipeline completion.

        Includes per-stage token usage breakdown (Section 13.3.3) and
        latency data for observability.

        Fire-and-forget: failure is logged but does NOT block the caller.
        """
        try:
            trace_id = ""
            if self._current_request is not None:
                trace_id = getattr(self._current_request, "trace_id", "")
            delta = DeltaPayload(
                agent_id=PLANNER_AGENT_ID,
                delta_type=DELTA_PLAN_END,
                section=SECTION_PIPELINE,
                data={
                    "status": "completed",
                    "total_tokens": self._total_plan_tokens,
                    "duration_ms": self._elapsed_ms(),
                    "revise_count": self._revise_count,
                    "stage_token_usage": dict(self._stage_token_usage),
                    "stage_latency": dict(self._stage_latency),
                },
                trace_id=trace_id or "unknown",
            )
            self._delta_port.emit(delta)
        except Exception:
            logger.warning(
                "pipeline.plan_end_delta_failed",
                exc_info=True,
            )

    def _emit_plan_failed(self, exc: Exception) -> None:
        """Emit ``plan.failed.v1`` event for PLAN-12 error handling.

        Fire-and-forget: failure is logged but does NOT block the caller.

        Parameters
        ----------
        exc : Exception
            The exception that caused the pipeline failure.
        """
        try:
            request_id = (
                getattr(self._current_request, "request_id", "")
                if self._current_request is not None
                else ""
            )
            trace_id = (
                getattr(self._current_request, "trace_id", "")
                if self._current_request is not None
                else ""
            )

            # Use stage from PlannerError if available, else FSM state
            stage = self._fsm.current_state.value
            if isinstance(exc, PlannerError) and exc.stage:
                stage = exc.stage

            payload = PlanFailedPayload(
                request_id=request_id or "unknown",
                stage=stage or "unknown",
                error_code=type(exc).__name__,
                error_message=str(exc),
                tokens_used=self._total_plan_tokens,
                duration_ms=self._elapsed_ms(),
                trace_id=trace_id or "unknown",
            )
            self._event_port.emit(TOPIC_PLAN_FAILED, payload)
        except Exception:
            logger.warning(
                "pipeline.plan_failed_event_failed",
                exc_info=True,
            )


__all__ = ["PipelineController"]
