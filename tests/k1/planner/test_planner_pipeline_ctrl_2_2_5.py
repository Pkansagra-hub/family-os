"""Tests for PipelineController.micro_replan() routing (Issue 2.2.5).

Covers:
  - Abbreviated micro pipeline: MICRO_SKETCH -> MICRO_EXPAND ->
    MICRO_VALIDATE -> COMMIT
  - Verdict routing: approved/revise -> commit, reject -> None
  - Best-effort failure semantics: errors return None (no plan.failed.v1)
  - Cancel checks between micro stages
  - Separate micro stage context budgets and timeout/token envelopes
  - FSM transition sequence correctness for micro pipeline

References
----------
- planner.md Section 10.3   (Abbreviated micro pipeline)
- planner.md Section 10.3.6 (Micro timing/token budgets)
- planner.md Section 10.6.2 (No revise loop)
- docs/plans/planner-implementation-plan.md Issue 2.2.5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k1.orchestrator.types import (
    Discovery,
    FailureContext,
    MicroReplanRequest,
    PlanStep,
    StepResult,
    StepStatus,
)
from k1.planner.config import PlannerConfig
from k1.planner.events import TOPIC_PLAN_CANCELLED, TOPIC_PLAN_FAILED
from k1.planner.pipeline_controller import PipelineController
from k1.planner.plan_fsm import PlanState
from k1.planner.types import (
    DELTA_STAGE_TRANSITION,
    VERDICT_APPROVED,
    VERDICT_REJECT,
    VERDICT_REVISE,
    DeltaPayload,
    RequestConstraints,
    StageContext,
    StagePhase,
    ValidationIssue,
    ValidationVerdict,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeCommittedPlan:
    plan_id: str = "micro-plan-001"
    request_id: str = "micro-req-001"
    intent: str = "micro intent"


@dataclass
class FakeExpandedPlan:
    """Minimal stand-in for ExpandedPlan with the attrs _enforce_plan12 reads."""

    steps: List[Any] = field(default_factory=lambda: [_step("r1")])
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    tool_mappings: Dict[str, str] = field(default_factory=dict)
    rationale: str = "test rationale"


class FakeSketchService:
    def __init__(self, result: Any = None, error: Optional[Exception] = None) -> None:
        self._result = result if result is not None else {"replacement_steps": ["r1"]}
        self._error = error
        self.micro_call_count = 0
        self.micro_calls: List[Any] = []

    async def execute(self, request: Any, ctx: StageContext) -> Any:
        return {"rough_steps": ["unused"]}

    async def micro_execute(self, request: Any, ctx: StageContext) -> Any:
        self.micro_call_count += 1
        self.micro_calls.append(request)
        if self._error is not None:
            raise self._error
        return self._result


class FakeExpandService:
    def __init__(self, result: Any = None, error: Optional[Exception] = None) -> None:
        self._result = result if result is not None else FakeExpandedPlan()
        self._error = error
        self.micro_call_count = 0
        self.micro_calls: List[Tuple[Any, Dict[str, StepResult]]] = []

    async def execute(self, sketch_result: Any, request: Any, ctx: StageContext) -> Any:
        return {"steps": ["unused"]}

    async def micro_execute(
        self,
        micro_sketch_result: Any,
        completed_results: Dict[str, StepResult],
        ctx: StageContext,
    ) -> Any:
        self.micro_call_count += 1
        self.micro_calls.append((micro_sketch_result, completed_results))
        if self._error is not None:
            raise self._error
        return self._result


class FakeValidateService:
    def __init__(
        self, verdicts: Optional[List[Any]] = None, error: Optional[Exception] = None
    ) -> None:
        self._verdicts = verdicts or [_make_verdict(VERDICT_APPROVED)]
        self._error = error
        self.micro_call_count = 0
        self.micro_calls: List[Any] = []

    async def execute(self, expanded_plan: Any, request: Any, ctx: StageContext) -> Any:
        return _make_verdict(VERDICT_APPROVED)

    async def micro_execute(
        self,
        micro_expanded: Any,
        ctx: StageContext,
        *,
        completed_step_ids: Optional[set] = None,
    ) -> Any:
        self.micro_call_count += 1
        self.micro_calls.append(micro_expanded)
        if self._error is not None:
            raise self._error
        idx = min(self.micro_call_count - 1, len(self._verdicts) - 1)
        return self._verdicts[idx]


class FakeCommitService:
    def __init__(self, result: Any = None, error: Optional[Exception] = None) -> None:
        self._result = result if result is not None else FakeCommittedPlan()
        self._error = error
        self.call_count = 0
        self.calls: List[Tuple[Any, Any, StageContext]] = []

    async def execute(
        self, expanded_plan: Any, request: Any, verdict: Any, ctx: StageContext
    ) -> Any:
        self.call_count += 1
        self.calls.append((expanded_plan, verdict, ctx))
        if self._error is not None:
            raise self._error
        return self._result


class FakeDeltaPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.emitted: List[DeltaPayload] = []
        self._fail = fail

    def emit(self, delta: DeltaPayload) -> None:
        if self._fail:
            raise RuntimeError("delta unavailable")
        self.emitted.append(delta)


class FakeEventPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.emitted: List[Tuple[str, Any]] = []
        self._fail = fail

    def emit(self, topic: str, payload: Any) -> None:
        if self._fail:
            raise RuntimeError("event unavailable")
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Any) -> Any:
        return f"sub-{topic}"

    def unsubscribe(self, handle: Any) -> bool:
        return True


class CancelAfterN:
    """First N checks False, then True."""

    def __init__(self, n: int) -> None:
        self._n = n
        self.call_count = 0

    def __call__(self) -> bool:
        self.call_count += 1
        return self.call_count > self._n


def _make_verdict(status: str) -> ValidationVerdict:
    issues: List[ValidationIssue] = []
    if status in (VERDICT_REVISE, VERDICT_REJECT):
        sev = "warning" if status == VERDICT_REVISE else "error"
        issues = [
            ValidationIssue(
                check_name="micro_check",
                severity=sev,
                detail=f"micro_{status}",
            )
        ]
    return ValidationVerdict(
        status=status,
        issues=issues,
        confidence=0.8,
        rationale=f"micro_{status}",
    )


def _step(step_id: str, capability: str = "tool.demo") -> PlanStep:
    return PlanStep(id=step_id, capability=capability)


def _step_result(step_id: str) -> StepResult:
    return StepResult(
        step_id=step_id,
        capability_name="tool.done",
        status=StepStatus.COMPLETED,
        duration_ms=10,
    )


@dataclass(frozen=True)
class _UnexpectedVerdict:
    status: str = "unexpected"


def _micro_request(
    *,
    request_id: str = "micro-req-001",
    trace_id: str = "trace-micro-001",
) -> MicroReplanRequest:
    return MicroReplanRequest(
        request_id=request_id,
        original_plan_id="orig-plan-001",
        completed_results={"s1": _step_result("s1")},
        remaining_steps=[_step("s2"), _step("s3")],
        discoveries=[Discovery(field="venue_type", value="indoor", source_step_id="s1")],
        failure_context=FailureContext(
            step_id="s2",
            error_code="STEP_FAIL",
            error_message="failed in test",
            partial_result={"k": "v"},
        ),
        trace_id=trace_id,
    )


def _never_cancel() -> bool:
    return False


def _make_controller(
    *,
    sketch: Any = None,
    expand: Any = None,
    validate: Any = None,
    commit: Any = None,
    delta_port: Any = None,
    event_port: Any = None,
    config: Any = None,
) -> PipelineController:
    return PipelineController(
        sketch=sketch if sketch is not None else FakeSketchService(),
        expand=expand if expand is not None else FakeExpandService(),
        validate=validate if validate is not None else FakeValidateService(),
        commit=commit if commit is not None else FakeCommitService(),
        delta_port=delta_port if delta_port is not None else FakeDeltaPort(),
        event_port=event_port if event_port is not None else FakeEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


# ---------------------------------------------------------------------------
# 1) Happy path + routing
# ---------------------------------------------------------------------------


class TestMicroReplanHappyPath:
    @pytest.mark.asyncio
    async def test_returns_committed_plan_when_approved(self) -> None:
        committed = FakeCommittedPlan(plan_id="micro-ok")
        ctrl = _make_controller(commit=FakeCommitService(result=committed))
        result = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert result is committed

    @pytest.mark.asyncio
    async def test_revise_is_treated_as_approved(self) -> None:
        validate = FakeValidateService(verdicts=[_make_verdict(VERDICT_REVISE)])
        ctrl = _make_controller(validate=validate)
        result = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert result is not None

    @pytest.mark.asyncio
    async def test_reject_returns_none(self) -> None:
        validate = FakeValidateService(verdicts=[_make_verdict(VERDICT_REJECT)])
        ctrl = _make_controller(validate=validate)
        result = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_revise_loop_validate_called_once(self) -> None:
        validate = FakeValidateService(verdicts=[_make_verdict(VERDICT_REVISE)])
        ctrl = _make_controller(validate=validate)
        _ = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert validate.micro_call_count == 1

    @pytest.mark.asyncio
    async def test_reject_does_not_call_commit(self) -> None:
        validate = FakeValidateService(verdicts=[_make_verdict(VERDICT_REJECT)])
        commit = FakeCommitService()
        ctrl = _make_controller(validate=validate, commit=commit)
        _ = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert commit.call_count == 0

    @pytest.mark.asyncio
    async def test_expand_receives_completed_results_from_request(self) -> None:
        req = _micro_request()
        expand = FakeExpandService()
        ctrl = _make_controller(expand=expand)
        _ = await ctrl.micro_replan(req, _never_cancel)
        assert expand.micro_call_count == 1
        _, completed = expand.micro_calls[0]
        assert completed is req.completed_results


# ---------------------------------------------------------------------------
# 2) FSM sequencing
# ---------------------------------------------------------------------------


class TestMicroReplanFSM:
    @pytest.mark.asyncio
    async def test_success_transition_sequence(self) -> None:
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        _ = await ctrl.micro_replan(_micro_request(), _never_cancel)

        transitions = [d for d in delta_port.emitted if d.delta_type == DELTA_STAGE_TRANSITION]
        states = [(d.data["from_state"], d.data["to_state"]) for d in transitions]
        assert states == [
            (PlanState.IDLE.value, PlanState.MICRO_SKETCH.value),
            (PlanState.MICRO_SKETCH.value, PlanState.MICRO_EXPAND.value),
            (PlanState.MICRO_EXPAND.value, PlanState.MICRO_VALIDATE.value),
            (PlanState.MICRO_VALIDATE.value, PlanState.COMMITTING.value),
            (PlanState.COMMITTING.value, PlanState.COMPLETED.value),
        ]

    @pytest.mark.asyncio
    async def test_reject_ends_in_failed(self) -> None:
        validate = FakeValidateService(verdicts=[_make_verdict(VERDICT_REJECT)])
        ctrl = _make_controller(validate=validate)
        _ = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED


# ---------------------------------------------------------------------------
# 3) Best-effort failure semantics (return None, no plan.failed event)
# ---------------------------------------------------------------------------


class TestMicroReplanFailureSemantics:
    @pytest.mark.asyncio
    async def test_sketch_error_returns_none(self) -> None:
        ctrl = _make_controller(sketch=FakeSketchService(error=RuntimeError("boom")))
        result = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert result is None

    @pytest.mark.asyncio
    async def test_expand_error_returns_none(self) -> None:
        ctrl = _make_controller(expand=FakeExpandService(error=RuntimeError("boom")))
        result = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_error_returns_none(self) -> None:
        ctrl = _make_controller(validate=FakeValidateService(error=RuntimeError("boom")))
        result = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert result is None

    @pytest.mark.asyncio
    async def test_commit_error_returns_none(self) -> None:
        ctrl = _make_controller(commit=FakeCommitService(error=RuntimeError("boom")))
        result = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_plan_failed_event_on_micro_errors(self) -> None:
        event_port = FakeEventPort()
        ctrl = _make_controller(
            validate=FakeValidateService(verdicts=[_make_verdict(VERDICT_REJECT)]),
            event_port=event_port,
        )
        _ = await ctrl.micro_replan(_micro_request(), _never_cancel)
        failed = [e for e in event_port.emitted if e[0] == TOPIC_PLAN_FAILED]
        assert failed == []


# ---------------------------------------------------------------------------
# 4) Cancel checks between micro stages
# ---------------------------------------------------------------------------


class TestMicroReplanCancel:
    @pytest.mark.asyncio
    async def test_cancel_after_micro_sketch_returns_none(self) -> None:
        cancel = CancelAfterN(0)
        expand = FakeExpandService()
        ctrl = _make_controller(expand=expand)
        result = await ctrl.micro_replan(_micro_request(), cancel)
        assert result is None
        assert ctrl.current_state == PlanState.CANCELLED
        assert expand.micro_call_count == 0

    @pytest.mark.asyncio
    async def test_cancel_after_micro_expand_returns_none(self) -> None:
        cancel = CancelAfterN(1)
        validate = FakeValidateService()
        ctrl = _make_controller(validate=validate)
        result = await ctrl.micro_replan(_micro_request(), cancel)
        assert result is None
        assert ctrl.current_state == PlanState.CANCELLED
        assert validate.micro_call_count == 0

    @pytest.mark.asyncio
    async def test_cancel_emits_plan_cancelled_event(self) -> None:
        cancel = CancelAfterN(0)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        _ = await ctrl.micro_replan(_micro_request(), cancel)
        cancelled = [e for e in event_port.emitted if e[0] == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1
        assert cancelled[0][1].stage == "MICRO_SKETCH"


# ---------------------------------------------------------------------------
# 5) Micro stage context helper
# ---------------------------------------------------------------------------


class TestBuildMicroStageContext:
    def test_uses_micro_timeout_budget_envelope(self) -> None:
        cfg = PlannerConfig(micro_replan_timeout_ms=12_345)
        ctrl = _make_controller(config=cfg)
        ctrl.reset()
        ctrl._current_request = _micro_request()
        ctrl._plan_start_time = None

        ctx = ctrl._build_micro_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.timeout_remaining_ms == 12_345

    def test_uses_micro_token_budget_envelope(self) -> None:
        cfg = PlannerConfig(micro_replan_max_tokens=2345)
        ctrl = _make_controller(config=cfg)
        ctrl.reset()
        ctrl._current_request = _micro_request()
        ctrl._total_plan_tokens = 100

        ctx = ctrl._build_micro_stage_context(_never_cancel, StagePhase.EXPAND)
        assert ctx.token_budget_remaining == 2245

    def test_uses_micro_stage_budget_for_sketch(self) -> None:
        cfg = PlannerConfig(
            micro_sketch_max_tokens=777,
            micro_sketch_timeout_ms=4444,
            micro_replan_max_tokens=3000,
        )
        ctrl = _make_controller(config=cfg)
        ctrl.reset()
        ctrl._current_request = _micro_request()

        ctx = ctrl._build_micro_stage_context(_never_cancel, StagePhase.SKETCH)
        assert isinstance(ctx.stage_budget, RequestConstraints)
        assert ctx.stage_budget.max_tokens == 777
        assert ctx.stage_budget.timeout_ms == 4444

    def test_commit_micro_stage_budget_is_none(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = _micro_request()
        ctx = ctrl._build_micro_stage_context(_never_cancel, StagePhase.COMMIT)
        assert ctx.stage_budget is None


# ---------------------------------------------------------------------------
# 6) Request propagation and stage invocation contracts
# ---------------------------------------------------------------------------


class TestMicroReplanPropagation:
    @pytest.mark.asyncio
    async def test_sketch_receives_full_micro_request(self) -> None:
        sketch = FakeSketchService()
        req = _micro_request(request_id="req-xyz", trace_id="trace-xyz")
        ctrl = _make_controller(sketch=sketch)
        _ = await ctrl.micro_replan(req, _never_cancel)
        assert sketch.micro_call_count == 1
        assert sketch.micro_calls[0] is req

    @pytest.mark.asyncio
    async def test_commit_receives_micro_expanded_and_verdict(self) -> None:
        expanded = FakeExpandedPlan(steps=[_step("replacement-a")])
        expand = FakeExpandService(result=expanded)
        verdict = _make_verdict(VERDICT_APPROVED)
        validate = FakeValidateService(verdicts=[verdict])
        commit = FakeCommitService()
        ctrl = _make_controller(expand=expand, validate=validate, commit=commit)

        _ = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert commit.call_count == 1
        got_expanded, got_verdict, _ctx = commit.calls[0]
        assert got_expanded == expanded
        assert got_verdict == verdict

    @pytest.mark.asyncio
    async def test_commit_context_uses_micro_budget_envelope(self) -> None:
        cfg = PlannerConfig(
            micro_replan_timeout_ms=9000,
            micro_replan_max_tokens=2500,
        )
        commit = FakeCommitService()
        ctrl = _make_controller(config=cfg, commit=commit)

        _ = await ctrl.micro_replan(_micro_request(), _never_cancel)
        assert commit.call_count == 1
        ctx = commit.calls[0][2]
        assert ctx.timeout_remaining_ms <= 9000
        assert ctx.token_budget_remaining <= 2500


# ---------------------------------------------------------------------------
# 7) Parametrized verdict coverage
# ---------------------------------------------------------------------------


class TestMicroVerdictMatrix:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status,expect_none",
        [
            (VERDICT_APPROVED, False),
            (VERDICT_REVISE, False),
            (VERDICT_REJECT, True),
            ("unexpected", True),
        ],
        ids=["approved", "revise", "reject", "unexpected"],
    )
    async def test_verdict_routing(
        self,
        status: str,
        expect_none: bool,
    ) -> None:
        verdict = _make_verdict(status) if status != "unexpected" else _UnexpectedVerdict()
        validate = FakeValidateService(verdicts=[verdict])
        ctrl = _make_controller(validate=validate)
        result = await ctrl.micro_replan(_micro_request(), _never_cancel)
        if expect_none:
            assert result is None
        else:
            assert result is not None
