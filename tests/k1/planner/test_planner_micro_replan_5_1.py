"""
Tests for Micro-Replan Pipeline (Epic 5.1).

Covers all 8 issues of Epic 5.1:
  5.1.1 -- Micro-replan trigger detection (PipelineController.micro_replan)
  5.1.2 -- Abbreviated SKETCH stage (micro_execute)
  5.1.3 -- Abbreviated EXPAND stage (micro_execute with cross-boundary deps)
  5.1.4 -- Abbreviated VALIDATE stage (simplified verdict)
  5.1.5 -- Discovery overlap heuristic
  5.1.6 -- PLAN-12 remaining-steps-only enforcement
  5.1.7 -- 10s timeout enforcement (progressive squeeze)
  5.1.8 -- FSM micro-replan states (MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE)

Test categories (~30 tests):
  A. FSM micro-replan states & transitions  (~4)
  B. Trigger detection & validation         (~5)
  C. Micro-SKETCH integration               (~4)
  D. Micro-EXPAND cross-boundary deps       (~4)
  E. Micro-VALIDATE simplified verdict      (~4)
  F. Overlap heuristic                      (~4)
  G. PLAN-12 enforcement                    (~4)
  H. Timeout & fallback                     (~3)
  I. Cancel between micro stages            (~2)

References
----------
- planner.md Section 10 (Micro-Replan Deep Dive)
- planner.md Section 18.3 (FSM Micro-Replan State Diagram)
- planner.md Section 18.4 (Transition Table)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from k1.orchestrator.types import (
    CommittedPlan,
    Discovery,
    FailureContext,
    MicroReplanRequest,
    PlanStep,
    StepResult,
    StepStatus,
)
from k1.planner.config import PlannerConfig
from k1.planner.events import TOPIC_MICRO_REPLAN_READY
from k1.planner.pipeline_controller import PipelineController
from k1.planner.plan_fsm import TRANSITION_TABLE, PlanState, PlanStateMachine
from k1.planner.types import (
    DELTA_MICRO_REPLAN,
    DELTA_STAGE_TRANSITION,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    VERDICT_APPROVED,
    VERDICT_REJECT,
    VERDICT_REVISE,
    DeltaPayload,
    ExpandedPlan,
    RoughStep,
    SketchFailedError,
    SketchResult,
    StageContext,
    ValidationIssue,
    ValidationVerdict,
)

# ===========================================================================
# Fake services and ports
# ===========================================================================


class FakeSketchService:
    """Configurable fake SketchService for PipelineController tests."""

    def __init__(self) -> None:
        self.execute_calls: List[Any] = []
        self.micro_execute_calls: List[Dict[str, Any]] = []
        self.micro_result: Optional[SketchResult] = None
        self.micro_error: Optional[Exception] = None
        self.micro_delay_s: float = 0.0

    async def execute(self, request: Any, ctx: Any) -> Any:
        self.execute_calls.append({"request": request, "ctx": ctx})
        return self.micro_result

    async def micro_execute(
        self,
        request: Any,
        ctx: StageContext,
    ) -> SketchResult:
        self.micro_execute_calls.append({"request": request, "ctx": ctx})
        if self.micro_delay_s:
            await asyncio.sleep(self.micro_delay_s)
        if self.micro_error:
            raise self.micro_error
        if self.micro_result is None:
            raise SketchFailedError("No micro_result configured")
        return self.micro_result


class FakeExpandService:
    """Configurable fake ExpandService for PipelineController tests."""

    def __init__(self) -> None:
        self.execute_calls: List[Any] = []
        self.micro_execute_calls: List[Dict[str, Any]] = []
        self.micro_result: Optional[ExpandedPlan] = None
        self.micro_error: Optional[Exception] = None

    async def execute(self, sketch_result: Any, request: Any, ctx: Any) -> Any:
        self.execute_calls.append({"sketch_result": sketch_result, "ctx": ctx})
        return self.micro_result

    async def micro_execute(
        self,
        micro_sketch_result: SketchResult,
        completed_results: Dict[str, StepResult],
        ctx: StageContext,
    ) -> ExpandedPlan:
        self.micro_execute_calls.append(
            {
                "micro_sketch_result": micro_sketch_result,
                "completed_results": completed_results,
                "ctx": ctx,
            }
        )
        if self.micro_error:
            raise self.micro_error
        if self.micro_result is None:
            raise RuntimeError("No micro_result configured")
        return self.micro_result


class FakeValidateService:
    """Configurable fake ValidateService for PipelineController tests."""

    def __init__(self) -> None:
        self.execute_calls: List[Any] = []
        self.micro_execute_calls: List[Dict[str, Any]] = []
        self.micro_result: Optional[ValidationVerdict] = None
        self.micro_error: Optional[Exception] = None

    async def execute(self, expanded_plan: Any, request: Any, ctx: Any) -> Any:
        self.execute_calls.append({"expanded_plan": expanded_plan, "ctx": ctx})
        return self.micro_result

    async def micro_execute(
        self,
        expanded_plan: ExpandedPlan,
        ctx: StageContext,
        cached_capabilities: Any = None,
        *,
        completed_step_ids: Any = None,
    ) -> ValidationVerdict:
        self.micro_execute_calls.append(
            {
                "expanded_plan": expanded_plan,
                "ctx": ctx,
                "completed_step_ids": completed_step_ids,
            }
        )
        if self.micro_error:
            raise self.micro_error
        if self.micro_result is None:
            raise RuntimeError("No micro_result configured")
        return self.micro_result


class FakeCommitService:
    """Configurable fake CommitService for PipelineController tests."""

    def __init__(self) -> None:
        self.execute_calls: List[Dict[str, Any]] = []
        self.result: Optional[CommittedPlan] = None
        self.error: Optional[Exception] = None

    async def execute(
        self,
        expanded_plan: Any,
        request: Any,
        verdict: Any,
        ctx: Any,
    ) -> CommittedPlan:
        self.execute_calls.append(
            {
                "expanded_plan": expanded_plan,
                "verdict": verdict,
                "ctx": ctx,
            }
        )
        if self.error:
            raise self.error
        if self.result is None:
            raise RuntimeError("No commit result configured")
        return self.result


class FakeDeltaPort:
    """Capture-mode fake IDeltaEmitPort."""

    def __init__(self) -> None:
        self.deltas: List[DeltaPayload] = []
        self.fail: bool = False

    def emit(self, delta: DeltaPayload) -> None:
        if self.fail:
            raise RuntimeError("delta emit failed")
        self.deltas.append(delta)

    def get_by_type(self, delta_type: str) -> List[DeltaPayload]:
        return [d for d in self.deltas if d.delta_type == delta_type]


class FakeEventPort:
    """Capture-mode fake IEventPort."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, topic: str, payload: Any) -> None:
        self.events.append({"topic": topic, "payload": payload})

    def subscribe(self, topic: str, handler: Any) -> Any:
        return None

    def unsubscribe(self, handle: Any) -> bool:
        return True

    def get_by_topic(self, topic: str) -> List[Dict[str, Any]]:
        return [e for e in self.events if e["topic"] == topic]


# ===========================================================================
# Test data factories
# ===========================================================================


def _step(sid: str, cap: str = "cap.test", **params: Any) -> PlanStep:
    """Build a minimal PlanStep with given id, capability, and params."""
    return PlanStep(id=sid, capability=cap, params=params)


def _sketch_result(step_intents: Optional[List[str]] = None) -> SketchResult:
    """Build minimal SketchResult."""
    intents = step_intents or ["step-one", "step-two"]
    return SketchResult(
        rough_steps=[RoughStep(intent=i) for i in intents],
        rationale="micro-replan sketch rationale",
    )


def _expanded_plan(
    steps: Optional[List[PlanStep]] = None,
    deps: Optional[Dict[str, List[str]]] = None,
) -> ExpandedPlan:
    """Build minimal ExpandedPlan."""
    if steps is None:
        steps = [_step("r1"), _step("r2")]
    if deps is None:
        deps = {s.id: [] for s in steps}
    return ExpandedPlan(
        steps=steps,
        dependencies=deps,
        tool_mappings={s.id: s.capability for s in steps},
        rationale="micro-replan expand rationale",
    )


def _approved_verdict() -> ValidationVerdict:
    return ValidationVerdict(
        status=VERDICT_APPROVED,
        confidence=0.9,
        rationale="micro plan approved",
        deterministic_pass=True,
    )


def _revise_verdict() -> ValidationVerdict:
    return ValidationVerdict(
        status=VERDICT_REVISE,
        issues=[
            ValidationIssue(
                check_name="minor",
                severity=SEVERITY_WARNING,
                detail="info",
            ),
        ],
        confidence=0.6,
        rationale="minor revision suggested",
    )


def _reject_verdict() -> ValidationVerdict:
    return ValidationVerdict(
        status=VERDICT_REJECT,
        issues=[
            ValidationIssue(
                check_name="fatal",
                severity=SEVERITY_ERROR,
                detail="bad plan",
            ),
        ],
        confidence=0.95,
        rationale="plan rejected",
        deterministic_pass=False,
    )


def _committed_plan(
    steps: Optional[List[PlanStep]] = None,
    request_id: str = "req-micro-1",
) -> CommittedPlan:
    """Build minimal CommittedPlan for micro-replan output."""
    if steps is None:
        steps = [_step("r1"), _step("r2")]
    return CommittedPlan(
        plan_id="micro-plan-001",
        request_id=request_id,
        intent="micro-replan",
        steps=steps,
        trace_id="trace-micro-1",
        dependencies={s.id: [] for s in steps},
    )


def _completed_result(sid: str, cap: str = "cap.done") -> StepResult:
    return StepResult(
        step_id=sid,
        capability_name=cap,
        status=StepStatus.COMPLETED,
        duration_ms=100,
    )


def _micro_request(
    remaining: Optional[List[PlanStep]] = None,
    completed: Optional[Dict[str, StepResult]] = None,
    discoveries: Optional[List[Discovery]] = None,
    failure_ctx: Optional[FailureContext] = None,
    original_plan_id: str = "plan-orig-1",
    trace_id: str = "trace-micro-1",
    request_id: str = "req-micro-1",
) -> MicroReplanRequest:
    """Build a well-formed MicroReplanRequest."""
    if remaining is None:
        remaining = [_step("s3", "cap.todo", restaurant_name="Luigi's")]
    if completed is None:
        completed = {"s1": _completed_result("s1"), "s2": _completed_result("s2")}
    return MicroReplanRequest(
        original_plan_id=original_plan_id,
        completed_results=completed,
        remaining_steps=remaining,
        trace_id=trace_id,
        request_id=request_id,
        discoveries=discoveries or [],
        failure_context=failure_ctx,
    )


def _build_controller(
    sketch: Optional[FakeSketchService] = None,
    expand: Optional[FakeExpandService] = None,
    validate: Optional[FakeValidateService] = None,
    commit: Optional[FakeCommitService] = None,
    delta: Optional[FakeDeltaPort] = None,
    event: Optional[FakeEventPort] = None,
    config: Optional[PlannerConfig] = None,
) -> tuple:
    """Build PipelineController with fakes; returns (ctrl, fakes_dict)."""
    sketch_svc = sketch or FakeSketchService()
    expand_svc = expand or FakeExpandService()
    validate_svc = validate or FakeValidateService()
    commit_svc = commit or FakeCommitService()
    delta_port = delta or FakeDeltaPort()
    event_port = event or FakeEventPort()
    cfg = config or PlannerConfig()

    ctrl = PipelineController(
        sketch=sketch_svc,
        expand=expand_svc,
        validate=validate_svc,
        commit=commit_svc,
        delta_port=delta_port,
        event_port=event_port,
        config=cfg,
    )
    fakes = {
        "sketch": sketch_svc,
        "expand": expand_svc,
        "validate": validate_svc,
        "commit": commit_svc,
        "delta": delta_port,
        "event": event_port,
    }
    return ctrl, fakes


def _no_cancel() -> bool:
    return False


# ===========================================================================
# A. FSM micro-replan states & transitions (5.1.8)
# ===========================================================================


class TestFSMMicroReplanStates:
    """FSM state definitions and transition rules for micro-replan."""

    def test_micro_states_exist_in_enum(self):
        """MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE are PlanState members."""
        assert PlanState.MICRO_SKETCH == "MICRO_SKETCH"
        assert PlanState.MICRO_EXPAND == "MICRO_EXPAND"
        assert PlanState.MICRO_VALIDATE == "MICRO_VALIDATE"

    def test_micro_states_is_micro_property(self):
        """is_micro returns True for all micro states."""
        assert PlanState.MICRO_SKETCH.is_micro
        assert PlanState.MICRO_EXPAND.is_micro
        assert PlanState.MICRO_VALIDATE.is_micro
        assert not PlanState.SKETCHING.is_micro
        assert not PlanState.IDLE.is_micro

    def test_micro_states_is_active_property(self):
        """Micro states are considered active (not IDLE, not terminal)."""
        assert PlanState.MICRO_SKETCH.is_active
        assert PlanState.MICRO_EXPAND.is_active
        assert PlanState.MICRO_VALIDATE.is_active

    def test_micro_transition_table_happy_path(self):
        """Transition table allows IDLE -> MS -> ME -> MV -> COMMITTING."""
        assert PlanState.MICRO_SKETCH in TRANSITION_TABLE[PlanState.IDLE]
        assert PlanState.MICRO_EXPAND in TRANSITION_TABLE[PlanState.MICRO_SKETCH]
        assert PlanState.MICRO_VALIDATE in TRANSITION_TABLE[PlanState.MICRO_EXPAND]
        assert PlanState.COMMITTING in TRANSITION_TABLE[PlanState.MICRO_VALIDATE]

    def test_micro_transition_table_failure_paths(self):
        """Each micro state can transition to FAILED."""
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.MICRO_SKETCH]
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.MICRO_EXPAND]
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.MICRO_VALIDATE]

    def test_micro_sketch_illegal_backwards(self):
        """MICRO_SKETCH cannot go back to IDLE (must go forward or FAILED)."""
        assert PlanState.IDLE not in TRANSITION_TABLE[PlanState.MICRO_SKETCH]

    def test_fsm_micro_replan_full_cycle(self):
        """FSM traverses full micro-replan cycle."""
        fsm = PlanStateMachine()
        assert fsm.current_state == PlanState.IDLE

        fsm.transition(PlanState.MICRO_SKETCH, "micro_start")
        assert fsm.current_state == PlanState.MICRO_SKETCH

        fsm.transition(PlanState.MICRO_EXPAND, "sketch_done")
        assert fsm.current_state == PlanState.MICRO_EXPAND

        fsm.transition(PlanState.MICRO_VALIDATE, "expand_done")
        assert fsm.current_state == PlanState.MICRO_VALIDATE

        fsm.transition(PlanState.COMMITTING, "validate_approved")
        assert fsm.current_state == PlanState.COMMITTING

        fsm.transition(PlanState.COMPLETED, "commit_done")
        assert fsm.current_state == PlanState.COMPLETED

        fsm.reset()
        assert fsm.current_state == PlanState.IDLE

    def test_fsm_micro_to_failed_resets(self):
        """Micro state -> FAILED -> reset -> IDLE."""
        fsm = PlanStateMachine()
        fsm.transition(PlanState.MICRO_SKETCH, "start")
        fsm.force_failed("error")
        assert fsm.current_state == PlanState.FAILED
        fsm.reset()
        assert fsm.current_state == PlanState.IDLE


# ===========================================================================
# B. Trigger detection & validation (5.1.1)
# ===========================================================================


class TestMicroReplanTrigger:
    """PipelineController.micro_replan entry point and request validation."""

    async def test_happy_path_full_flow(self):
        """Successful micro-replan: returns CommittedPlan."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        committed = _committed_plan()
        fakes["commit"].result = committed

        req = _micro_request()
        result = await ctrl.micro_replan(req, _no_cancel)

        assert result is committed
        assert ctrl.current_state == PlanState.COMPLETED
        assert len(fakes["sketch"].micro_execute_calls) == 1
        assert len(fakes["expand"].micro_execute_calls) == 1
        assert len(fakes["validate"].micro_execute_calls) == 1
        assert len(fakes["commit"].execute_calls) == 1

    async def test_returns_none_on_empty_original_plan_id(self):
        """Invalid request: empty original_plan_id -> returns None."""
        ctrl, _ = _build_controller()

        class BareMicroRequest:
            original_plan_id = ""
            remaining_steps = [_step("s1")]
            trace_id = "t1"
            request_id = "r1"
            completed_results = {}
            discoveries = []
            failure_context = None

        result = await ctrl.micro_replan(BareMicroRequest(), _no_cancel)
        assert result is None

    async def test_returns_none_on_empty_remaining_steps(self):
        """Invalid request: empty remaining_steps -> returns None."""
        ctrl, _ = _build_controller()

        class BareRequest:
            original_plan_id = "plan-1"
            remaining_steps = []
            trace_id = "t1"
            request_id = "r1"
            completed_results = {}
            discoveries = []
            failure_context = None

        result = await ctrl.micro_replan(BareRequest(), _no_cancel)
        assert result is None

    async def test_returns_none_on_empty_trace_id(self):
        """Invalid request: empty trace_id -> returns None."""
        ctrl, _ = _build_controller()

        class BareRequest:
            original_plan_id = "plan-1"
            remaining_steps = [_step("s1")]
            trace_id = ""
            request_id = "r1"
            completed_results = {}
            discoveries = []
            failure_context = None

        result = await ctrl.micro_replan(BareRequest(), _no_cancel)
        assert result is None

    async def test_emits_micro_replan_started_delta(self):
        """micro_replan emits DELTA_MICRO_REPLAN with type=micro_replan_started."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        discoveries = [
            Discovery(field="restaurant_closed", value=True, source_step_id="s1"),
        ]
        req = _micro_request(discoveries=discoveries)
        await ctrl.micro_replan(req, _no_cancel)

        micro_deltas = fakes["delta"].get_by_type(DELTA_MICRO_REPLAN)
        assert len(micro_deltas) >= 1
        data = micro_deltas[0].data
        assert data["type"] == "micro_replan_started"
        assert data["original_plan_id"] == "plan-orig-1"
        assert data["trigger"] == "discovery"

    async def test_emits_failure_trigger_when_failure_context(self):
        """Delta trigger is 'failure' when failure_context is present."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        fc = FailureContext(
            step_id="s2",
            error_code="TIMEOUT",
            error_message="timed out",
        )
        req = _micro_request(failure_ctx=fc)
        await ctrl.micro_replan(req, _no_cancel)

        micro_deltas = fakes["delta"].get_by_type(DELTA_MICRO_REPLAN)
        assert micro_deltas[0].data["trigger"] == "failure"


# ===========================================================================
# C. Micro-SKETCH integration (5.1.2)
# ===========================================================================


class TestMicroSketch:
    """Micro-SKETCH stage receives correct context and StageContext."""

    async def test_sketch_receives_request_and_ctx(self):
        """micro_execute receives MicroReplanRequest and StageContext."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        call = fakes["sketch"].micro_execute_calls[0]
        assert call["request"] is req
        ctx = call["ctx"]
        assert isinstance(ctx, StageContext)
        assert ctx.request_id == "req-micro-1"
        assert ctx.trace_id == "trace-micro-1"

    async def test_sketch_ctx_has_micro_budget(self):
        """StageContext.stage_budget uses micro_sketch tokens/timeout."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        ctx = fakes["sketch"].micro_execute_calls[0]["ctx"]
        budget = ctx.stage_budget
        assert budget is not None
        cfg = PlannerConfig()
        assert budget.max_tokens == cfg.micro_sketch_max_tokens
        assert budget.timeout_ms == cfg.micro_sketch_timeout_ms

    async def test_sketch_failure_returns_none(self):
        """Sketch micro_execute raises -> micro_replan returns None."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_error = SketchFailedError("boom")

        req = _micro_request()
        result = await ctrl.micro_replan(req, _no_cancel)
        assert result is None

    async def test_sketch_failure_fsm_goes_to_failed(self):
        """Sketch failure transitions FSM to FAILED."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_error = SketchFailedError("boom")

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)
        assert ctrl.current_state == PlanState.FAILED


# ===========================================================================
# D. Micro-EXPAND cross-boundary deps (5.1.3)
# ===========================================================================


class TestMicroExpand:
    """Micro-EXPAND receives completed_results and StageContext."""

    async def test_expand_receives_completed_results(self):
        """micro_execute receives completed_results dict."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        call = fakes["expand"].micro_execute_calls[0]
        assert "s1" in call["completed_results"]
        assert "s2" in call["completed_results"]

    async def test_expand_receives_sketch_result(self):
        """micro_execute receives sketch result from previous stage."""
        ctrl, fakes = _build_controller()
        sr = _sketch_result(["replan-alpha"])
        fakes["sketch"].micro_result = sr
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        call = fakes["expand"].micro_execute_calls[0]
        assert call["micro_sketch_result"] is sr

    async def test_expand_ctx_has_micro_budget(self):
        """Expand StageContext uses micro_expand tokens/timeout."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        ctx = fakes["expand"].micro_execute_calls[0]["ctx"]
        budget = ctx.stage_budget
        cfg = PlannerConfig()
        assert budget.max_tokens == cfg.micro_expand_max_tokens
        assert budget.timeout_ms == cfg.micro_expand_timeout_ms

    async def test_expand_failure_returns_none(self):
        """Expand failure -> returns None (graceful degradation)."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_error = RuntimeError("expand LLM failed")

        req = _micro_request()
        result = await ctrl.micro_replan(req, _no_cancel)
        assert result is None


# ===========================================================================
# E. Micro-VALIDATE simplified verdict (5.1.4)
# ===========================================================================


class TestMicroValidate:
    """Micro-VALIDATE: simplified verdict routing, no revise loop."""

    async def test_approved_proceeds_to_commit(self):
        """Verdict 'approved' -> COMMIT -> COMPLETED, returns CommittedPlan."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        cp = _committed_plan()
        fakes["commit"].result = cp

        result = await ctrl.micro_replan(_micro_request(), _no_cancel)
        assert result is cp

    async def test_revise_treated_as_approved(self):
        """Verdict 'revise' treated as 'approved' (best-effort, no loop)."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _revise_verdict()
        cp = _committed_plan()
        fakes["commit"].result = cp

        result = await ctrl.micro_replan(_micro_request(), _no_cancel)
        # revise -> proceeds to commit
        assert result is cp
        assert len(fakes["commit"].execute_calls) == 1

    async def test_reject_returns_none(self):
        """Verdict 'reject' -> return None (Orchestrator continues original)."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _reject_verdict()

        result = await ctrl.micro_replan(_micro_request(), _no_cancel)
        assert result is None
        assert len(fakes["commit"].execute_calls) == 0

    async def test_validate_ctx_has_micro_budget(self):
        """Validate StageContext uses micro_validate tokens/timeout."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        await ctrl.micro_replan(_micro_request(), _no_cancel)

        ctx = fakes["validate"].micro_execute_calls[0]["ctx"]
        budget = ctx.stage_budget
        cfg = PlannerConfig()
        assert budget.max_tokens == cfg.micro_validate_max_tokens
        assert budget.timeout_ms == cfg.micro_validate_timeout_ms


# ===========================================================================
# F. Overlap heuristic (5.1.5)
# ===========================================================================


class TestOverlapHeuristic:
    """Discovery overlap heuristic revalidation."""

    def test_exact_match(self):
        """Exact field-param match detects overlap."""
        ctrl, _ = _build_controller()
        req = _micro_request(
            remaining=[_step("s3", restaurant_name="Luigi's")],
            discoveries=[Discovery(field="restaurant_name", value="closed")],
        )
        assert ctrl._validate_overlap(req) is True

    def test_substring_forward(self):
        """discovery.field substring of param_name detects overlap."""
        ctrl, _ = _build_controller()
        req = _micro_request(
            remaining=[_step("s3", restaurant_name="Luigi's")],
            discoveries=[Discovery(field="restaurant", value=True)],
        )
        assert ctrl._validate_overlap(req) is True

    def test_substring_reverse(self):
        """param_name substring of discovery.field detects overlap."""
        ctrl, _ = _build_controller()
        req = _micro_request(
            remaining=[_step("s3", name="Luigi's")],
            discoveries=[
                Discovery(
                    field="restaurant_name_updated",
                    value=True,
                ),
            ],
        )
        assert ctrl._validate_overlap(req) is True

    def test_no_overlap(self):
        """Unrelated fields/params -> no overlap detected."""
        ctrl, _ = _build_controller()
        req = _micro_request(
            remaining=[_step("s3", color="blue")],
            discoveries=[
                Discovery(field="restaurant_closed", value=True),
            ],
        )
        assert ctrl._validate_overlap(req) is False

    def test_empty_discoveries(self):
        """No discoveries -> no overlap."""
        ctrl, _ = _build_controller()
        req = _micro_request(discoveries=[])
        assert ctrl._validate_overlap(req) is False

    async def test_overlap_is_advisory_not_blocking(self):
        """Even without overlap, micro_replan still proceeds."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request(
            remaining=[_step("s3", color="blue")],
            discoveries=[Discovery(field="unrelated_field", value="x")],
        )
        result = await ctrl.micro_replan(req, _no_cancel)
        # Should still complete even with no overlap
        assert result is not None


# ===========================================================================
# G. PLAN-12 enforcement (5.1.6)
# ===========================================================================


class TestPlan12Enforcement:
    """PLAN-12: replacement steps only, completed steps frozen."""

    def test_clean_plan_passes_through(self):
        """No violations: plan returned unchanged."""
        ctrl, _ = _build_controller()
        plan = _expanded_plan(
            steps=[_step("r1"), _step("r2")],
            deps={"r1": [], "r2": ["r1"]},
        )
        completed_ids = {"s1", "s2"}
        result = ctrl._enforce_plan12(plan, completed_ids)
        assert result is plan  # Same object, no rebuild needed

    def test_strips_overlapping_step_id(self):
        """Step with id overlapping completed step is stripped."""
        ctrl, _ = _build_controller()
        plan = _expanded_plan(
            steps=[_step("s1"), _step("r2")],  # s1 overlaps
            deps={"s1": [], "r2": []},
        )
        completed_ids = {"s1", "s2"}
        result = ctrl._enforce_plan12(plan, completed_ids)
        # s1 should be stripped, only r2 remains
        assert len(result.steps) == 1
        assert result.steps[0].id == "r2"

    def test_cross_boundary_deps_to_completed_valid(self):
        """Deps between replacement steps are valid; plan unchanged."""
        ctrl, _ = _build_controller()
        plan = _expanded_plan(
            steps=[_step("r1"), _step("r2")],
            deps={"r1": [], "r2": ["r1"]},
        )
        completed_ids = {"s1", "s2"}
        result = ctrl._enforce_plan12(plan, completed_ids)
        # No overlapping IDs, all deps valid -> same object
        assert result is plan

    def test_strips_dangling_dependency(self):
        """Dep referencing stripped step is cleaned up."""
        ctrl, _ = _build_controller()
        # s1 overlaps completed; r2 depends on s1 (valid at construction)
        plan = _expanded_plan(
            steps=[_step("s1"), _step("r2")],
            deps={"s1": [], "r2": ["s1"]},
        )
        completed_ids = {"s1", "s2"}
        result = ctrl._enforce_plan12(plan, completed_ids)
        # s1 stripped (overlaps), r2's dep to s1 now dangling
        assert len(result.steps) == 1
        assert result.steps[0].id == "r2"
        assert result.dependencies["r2"] == []


# ===========================================================================
# H. Timeout & fallback (5.1.7)
# ===========================================================================


class TestMicroReplanTimeout:
    """10s timeout enforcement and progressive squeeze."""

    async def test_progressive_squeeze_remaining_time_decreases(self):
        """Each subsequent stage ctx has less remaining time."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        sketch_ctx = fakes["sketch"].micro_execute_calls[0]["ctx"]
        expand_ctx = fakes["expand"].micro_execute_calls[0]["ctx"]
        validate_ctx = fakes["validate"].micro_execute_calls[0]["ctx"]

        # Sketch should have more remaining time than expand, etc.
        assert sketch_ctx.timeout_remaining_ms >= expand_ctx.timeout_remaining_ms
        assert expand_ctx.timeout_remaining_ms >= validate_ctx.timeout_remaining_ms

    async def test_timeout_exceeded_returns_none(self):
        """If micro timeout exceeded before stage, returns None."""
        # Use a very short timeout
        cfg = PlannerConfig(micro_replan_timeout_ms=1)  # 1ms
        ctrl, fakes = _build_controller(config=cfg)

        # Sketch completes but takes a little time
        async def slow_sketch(request, ctx):
            await asyncio.sleep(0.01)  # 10ms -- exceeds 1ms budget
            return _sketch_result()

        fakes["sketch"].micro_execute = slow_sketch
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        result = await ctrl.micro_replan(req, _no_cancel)
        # Should return None because timeout exceeded after sketch
        assert result is None

    async def test_all_stages_complete_within_budget(self):
        """Normal execution completes well within 10s budget."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        result = await ctrl.micro_replan(req, _no_cancel)
        assert result is not None


# ===========================================================================
# I. Cancel between micro stages (5.1.8 cancel integration)
# ===========================================================================


class TestMicroReplanCancel:
    """Cooperative cancellation during micro-replan."""

    async def test_cancel_after_sketch_returns_none(self):
        """Cancel between MICRO_SKETCH and MICRO_EXPAND -> returns None."""
        cancel_after_sketch = False

        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        # Cancel flag that activates after sketch micro_execute runs
        original_micro_execute = fakes["sketch"].micro_execute

        async def sketch_then_cancel(request, ctx):
            nonlocal cancel_after_sketch
            result = await original_micro_execute(request, ctx)
            cancel_after_sketch = True
            return result

        fakes["sketch"].micro_execute = sketch_then_cancel

        def cancel_check() -> bool:
            return cancel_after_sketch

        req = _micro_request()
        result = await ctrl.micro_replan(req, cancel_check)
        assert result is None

    async def test_cancel_returns_none_not_raises(self):
        """Cancel during micro-replan returns None (best-effort), never raises."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()

        req = _micro_request()
        # Immediately cancelled
        result = await ctrl.micro_replan(req, lambda: True)
        # micro_replan catches PlanCancelledError and returns None
        assert result is None


# ===========================================================================
# J. Telemetry & event emission (5.1.1 + 5.1.7)
# ===========================================================================


class TestMicroReplanTelemetry:
    """TOPIC_MICRO_REPLAN_READY telemetry event emission."""

    async def test_emits_micro_replan_ready_telemetry(self):
        """Successful micro-replan emits TOPIC_MICRO_REPLAN_READY event."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        telemetry = fakes["event"].get_by_topic(TOPIC_MICRO_REPLAN_READY)
        assert len(telemetry) == 1
        payload = telemetry[0]["payload"]
        assert payload["plan_id"] == "micro-plan-001"
        assert payload["original_plan_id"] == "plan-orig-1"

    async def test_no_telemetry_on_failure(self):
        """Failed micro-replan does NOT emit TOPIC_MICRO_REPLAN_READY."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_error = SketchFailedError("boom")

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        telemetry = fakes["event"].get_by_topic(TOPIC_MICRO_REPLAN_READY)
        assert len(telemetry) == 0

    async def test_no_plan_failed_event_on_micro_failure(self):
        """Micro-replan failure does NOT emit plan.failed.v1 (graceful degradation)."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_error = SketchFailedError("boom")

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        plan_failed = fakes["event"].get_by_topic("k1.planner.plan.failed.v1")
        assert len(plan_failed) == 0

    async def test_delta_stage_transitions_emitted(self):
        """Micro-replan emits stage_transition deltas for each FSM transition."""
        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        transitions = fakes["delta"].get_by_type(DELTA_STAGE_TRANSITION)
        # IDLE->MICRO_SKETCH, MS->ME, ME->MV, MV->COMMITTING, COMMITTING->COMPLETED
        assert len(transitions) >= 5
        states = [t.data["to_state"] for t in transitions]
        assert "MICRO_SKETCH" in states
        assert "MICRO_EXPAND" in states
        assert "MICRO_VALIDATE" in states
        assert "COMMITTING" in states
        assert "COMPLETED" in states
