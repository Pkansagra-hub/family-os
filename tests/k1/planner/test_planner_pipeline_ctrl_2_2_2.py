"""Tests for PipelineController.execute() stage orchestration loop (Issue 2.2.2).

Tests cover:
  - Happy-path 4-stage sequencing (SKETCH -> EXPAND -> VALIDATE -> COMMIT)
  - Verdict routing: approved, revise-then-approved, revise-twice-approved,
    reject-then-approved, reject-twice-failed
  - PLAN-12 error handling: uncaught exceptions -> force_failed + plan.failed.v1
  - Cancel between stages (basic cooperative cancellation)
  - Timeout enforcement (basic PLAN-04 defense-in-depth)
  - FSM transition sequence verification
  - Delta emission per transition and plan_end
  - Plan.failed.v1 event emission on error
  - StageContext construction and propagation
  - Helper methods: _elapsed_ms, _check_cancel, _check_timeout,
    _build_stage_context, _emit_plan_end_delta, _emit_plan_failed

References
----------
- planner.md Section 5.2   (26-Step Pipeline Flow)
- planner.md Section 13.3  (Budget Injection per stage)
- planner.md Section 17.2  (PipelineController ~80 tests)
- planner.md Section 18.4  (Transition Table)
- planner.md Section 23.2  (PLAN_START lifecycle -- reset())
- planner.md Section 24.2  (Cancel protocol)
- planner.md Section 30.5.1 F03 (pipeline_controller.py spec)
- docs/plans/planner-implementation-plan.md Issue 2.2.2
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import pytest

from k1.planner.config import PlannerConfig
from k1.planner.events import TOPIC_PLAN_FAILED, PlanFailedPayload
from k1.planner.pipeline_controller import PipelineController
from k1.planner.plan_fsm import PlanState
from k1.planner.types import (
    DELTA_PLAN_END,
    DELTA_STAGE_TRANSITION,
    PLANNER_AGENT_ID,
    SECTION_PIPELINE,
    VERDICT_APPROVED,
    VERDICT_REJECT,
    VERDICT_REVISE,
    DeltaPayload,
    PlanCancelledError,
    PlannerError,
    StageContext,
    StagePhase,
    ValidateRejectedError,
    ValidationIssue,
    ValidationVerdict,
)

# ---------------------------------------------------------------------------
# Test helpers -- fake services and ports
# ---------------------------------------------------------------------------


@dataclass
class FakePlanRequest:
    """Minimal stand-in for PlanRequest (from k1.orchestrator.types)."""

    request_id: str = "req-001"
    trace_id: str = "trace-abc"
    intent: str = "test intent"


@dataclass
class FakeCommittedPlan:
    """Minimal stand-in for CommittedPlan (from k1.orchestrator.types)."""

    plan_id: str = "plan-001"
    request_id: str = "req-001"
    intent: str = "test intent"
    trace_id: str = "trace-abc"


class FakeSketchService:
    """Fake SketchService that records calls and returns configurable results."""

    def __init__(
        self,
        result: Any = None,
        error: Optional[Exception] = None,
    ) -> None:
        self._result = result if result is not None else {"rough_steps": ["step1"]}
        self._error = error
        self.call_count: int = 0
        self.calls: List[Tuple[Any, StageContext]] = []

    async def execute(self, request: Any, ctx: StageContext) -> Any:
        self.call_count += 1
        self.calls.append((request, ctx))
        if self._error is not None:
            raise self._error
        return self._result


class FakeExpandService:
    """Fake ExpandService that records calls and returns configurable results."""

    def __init__(
        self,
        result: Any = None,
        error: Optional[Exception] = None,
    ) -> None:
        self._result = result if result is not None else {"steps": ["expanded_step1"]}
        self._error = error
        self.call_count: int = 0
        self.calls: List[Tuple[Any, StageContext]] = []

    async def execute(self, sketch_result: Any, ctx: StageContext) -> Any:
        self.call_count += 1
        self.calls.append((sketch_result, ctx))
        if self._error is not None:
            raise self._error
        return self._result


class FakeValidateService:
    """Fake ValidateService that returns verdicts from a configurable list.

    On the Nth call, returns verdicts[N-1].  If N exceeds the list length,
    returns the last verdict.
    """

    def __init__(
        self,
        verdicts: Optional[List[Any]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self._verdicts = verdicts or [
            _make_verdict(VERDICT_APPROVED),
        ]
        self._error = error
        self.call_count: int = 0
        self.calls: List[Tuple[Any, StageContext]] = []

    async def execute(self, expanded_plan: Any, ctx: StageContext) -> Any:
        self.call_count += 1
        self.calls.append((expanded_plan, ctx))
        if self._error is not None:
            raise self._error
        idx = min(self.call_count - 1, len(self._verdicts) - 1)
        return self._verdicts[idx]


class FakeCommitService:
    """Fake CommitService that records calls and returns configurable results."""

    def __init__(
        self,
        result: Any = None,
        error: Optional[Exception] = None,
    ) -> None:
        self._result = result if result is not None else FakeCommittedPlan()
        self._error = error
        self.call_count: int = 0
        self.calls: List[Tuple[Any, Any, StageContext]] = []

    async def execute(
        self,
        expanded_plan: Any,
        verdict: Any,
        ctx: StageContext,
    ) -> Any:
        self.call_count += 1
        self.calls.append((expanded_plan, verdict, ctx))
        if self._error is not None:
            raise self._error
        return self._result


class FakeDeltaPort:
    """Minimal IDeltaEmitPort that records emitted deltas."""

    def __init__(self, *, fail: bool = False) -> None:
        self.emitted: List[DeltaPayload] = []
        self._fail = fail

    def emit(self, delta: DeltaPayload) -> None:
        if self._fail:
            raise RuntimeError("Delta bus unavailable")
        self.emitted.append(delta)


class FakeEventPort:
    """Minimal IEventPort that records emitted events."""

    def __init__(self, *, fail: bool = False) -> None:
        self.emitted: List[Tuple[str, Any]] = []
        self._fail = fail

    def emit(self, topic: str, payload: Any) -> None:
        if self._fail:
            raise RuntimeError("Event bus unavailable")
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Any) -> Any:
        return f"sub-{topic}"

    def unsubscribe(self, handle: Any) -> bool:
        return True


# ---------------------------------------------------------------------------
# Verdict factory helpers
# ---------------------------------------------------------------------------


def _make_verdict(
    status: str,
    *,
    rationale: str = "test rationale",
    confidence: float = 0.9,
) -> ValidationVerdict:
    """Create a valid ValidationVerdict for testing."""
    issues: List[ValidationIssue] = []
    if status in (VERDICT_REVISE, VERDICT_REJECT):
        severity = "error" if status == VERDICT_REJECT else "warning"
        issues = [
            ValidationIssue(
                check_name="test_check",
                severity=severity,
                detail="test issue",
            ),
        ]
    return ValidationVerdict(
        status=status,
        issues=issues,
        confidence=confidence,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Controller factory helper
# ---------------------------------------------------------------------------


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
    """Build PipelineController with sensible test defaults."""
    return PipelineController(
        sketch=sketch if sketch is not None else FakeSketchService(),
        expand=expand if expand is not None else FakeExpandService(),
        validate=validate if validate is not None else FakeValidateService(),
        commit=commit if commit is not None else FakeCommitService(),
        delta_port=delta_port if delta_port is not None else FakeDeltaPort(),
        event_port=event_port if event_port is not None else FakeEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


def _never_cancel() -> bool:
    """Cancel check that never cancels."""
    return False


# ===========================================================================
# 1. Happy-path 4-stage sequencing
# ===========================================================================


class TestExecuteHappyPath:
    """Full pipeline: SKETCH -> EXPAND -> VALIDATE(approved) -> COMMIT."""

    @pytest.mark.asyncio
    async def test_returns_committed_plan(self) -> None:
        committed = FakeCommittedPlan(plan_id="plan-happy")
        ctrl = _make_controller(commit=FakeCommitService(result=committed))
        result_ = await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert result_ is committed

    @pytest.mark.asyncio
    async def test_sketch_called_once(self) -> None:
        sketch = FakeSketchService()
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert sketch.call_count == 1

    @pytest.mark.asyncio
    async def test_expand_called_once(self) -> None:
        expand = FakeExpandService()
        ctrl = _make_controller(expand=expand)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert expand.call_count == 1

    @pytest.mark.asyncio
    async def test_validate_called_once(self) -> None:
        validate = FakeValidateService()
        ctrl = _make_controller(validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert validate.call_count == 1

    @pytest.mark.asyncio
    async def test_commit_called_once(self) -> None:
        commit = FakeCommitService()
        ctrl = _make_controller(commit=commit)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert commit.call_count == 1

    @pytest.mark.asyncio
    async def test_fsm_ends_completed(self) -> None:
        ctrl = _make_controller()
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.COMPLETED

    @pytest.mark.asyncio
    async def test_sketch_receives_request(self) -> None:
        sketch = FakeSketchService()
        req = FakePlanRequest(request_id="req-999")
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(req, _never_cancel)
        assert sketch.calls[0][0] is req

    @pytest.mark.asyncio
    async def test_expand_receives_sketch_result(self) -> None:
        sketch_result = {"my": "sketch"}
        sketch = FakeSketchService(result=sketch_result)
        expand = FakeExpandService()
        ctrl = _make_controller(sketch=sketch, expand=expand)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert expand.calls[0][0] is sketch_result

    @pytest.mark.asyncio
    async def test_validate_receives_expanded_plan(self) -> None:
        expanded = {"my": "plan"}
        expand = FakeExpandService(result=expanded)
        validate = FakeValidateService()
        ctrl = _make_controller(expand=expand, validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert validate.calls[0][0] is expanded

    @pytest.mark.asyncio
    async def test_commit_receives_expanded_and_verdict(self) -> None:
        expanded = {"my": "plan"}
        verdict = _make_verdict(VERDICT_APPROVED)
        expand = FakeExpandService(result=expanded)
        validate = FakeValidateService(verdicts=[verdict])
        commit = FakeCommitService()
        ctrl = _make_controller(
            expand=expand,
            validate=validate,
            commit=commit,
        )
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert commit.calls[0][0] is expanded
        assert commit.calls[0][1] is verdict

    @pytest.mark.asyncio
    async def test_services_called_sequentially(self) -> None:
        """Stages called in order: sketch, expand, validate, commit."""
        call_order: List[str] = []

        class OrderedSketch(FakeSketchService):
            async def execute(self, r: Any, c: Any) -> Any:
                call_order.append("sketch")
                return await super().execute(r, c)

        class OrderedExpand(FakeExpandService):
            async def execute(self, r: Any, c: Any) -> Any:
                call_order.append("expand")
                return await super().execute(r, c)

        class OrderedValidate(FakeValidateService):
            async def execute(self, r: Any, c: Any) -> Any:
                call_order.append("validate")
                return await super().execute(r, c)

        class OrderedCommit(FakeCommitService):
            async def execute(self, e: Any, v: Any, c: Any) -> Any:
                call_order.append("commit")
                return await super().execute(e, v, c)

        ctrl = _make_controller(
            sketch=OrderedSketch(),
            expand=OrderedExpand(),
            validate=OrderedValidate(verdicts=[_make_verdict(VERDICT_APPROVED)]),
            commit=OrderedCommit(),
        )
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert call_order == ["sketch", "expand", "validate", "commit"]

    @pytest.mark.asyncio
    async def test_current_request_set(self) -> None:
        req = FakePlanRequest(request_id="req-set")
        ctrl = _make_controller()
        await ctrl.execute(req, _never_cancel)
        assert ctrl.current_request is req

    @pytest.mark.asyncio
    async def test_plan_start_time_set(self) -> None:
        ctrl = _make_controller()
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.plan_start_time is not None

    @pytest.mark.asyncio
    async def test_revise_count_zero_on_happy_path(self) -> None:
        ctrl = _make_controller()
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.revise_count == 0


# ===========================================================================
# 2. FSM transition sequence verification
# ===========================================================================


class TestFSMTransitions:
    """Verify correct FSM transition sequences during execute()."""

    @pytest.mark.asyncio
    async def test_happy_path_transitions(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)

        # Capture transitions from delta emissions
        await ctrl.execute(FakePlanRequest(), _never_cancel)

        # Extract from_state -> to_state from emitted deltas
        stage_deltas = [d for d in dp.emitted if d.delta_type == DELTA_STAGE_TRANSITION]
        transition_pairs = [(d.data["from_state"], d.data["to_state"]) for d in stage_deltas]
        expected = [
            ("IDLE", "SKETCHING"),
            ("SKETCHING", "EXPANDING"),
            ("EXPANDING", "VALIDATING"),
            ("VALIDATING", "COMMITTING"),
            ("COMMITTING", "COMPLETED"),
        ]
        assert transition_pairs == expected

    @pytest.mark.asyncio
    async def test_revise_loop_transitions(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(
            validate=FakeValidateService(
                verdicts=[
                    _make_verdict(VERDICT_REVISE),
                    _make_verdict(VERDICT_APPROVED),
                ]
            ),
            delta_port=dp,
        )
        await ctrl.execute(FakePlanRequest(), _never_cancel)

        stage_deltas = [d for d in dp.emitted if d.delta_type == DELTA_STAGE_TRANSITION]
        pairs = [(d.data["from_state"], d.data["to_state"]) for d in stage_deltas]
        expected = [
            ("IDLE", "SKETCHING"),
            ("SKETCHING", "EXPANDING"),
            ("EXPANDING", "VALIDATING"),
            ("VALIDATING", "EXPANDING"),  # revise loop
            ("EXPANDING", "VALIDATING"),
            ("VALIDATING", "COMMITTING"),
            ("COMMITTING", "COMPLETED"),
        ]
        assert pairs == expected


# ===========================================================================
# 3. Verdict routing
# ===========================================================================


class TestVerdictRouting:
    """Section 5.2 step 15 verdict routing logic."""

    @pytest.mark.asyncio
    async def test_approved_direct_to_commit(self) -> None:
        ctrl = _make_controller(
            validate=FakeValidateService(
                verdicts=[
                    _make_verdict(VERDICT_APPROVED),
                ]
            ),
        )
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.COMPLETED
        assert ctrl.revise_count == 0

    @pytest.mark.asyncio
    async def test_revise_once_then_approved(self) -> None:
        """First verdict=revise, retry EXPAND, second verdict=approved."""
        expand = FakeExpandService()
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_APPROVED),
            ]
        )
        ctrl = _make_controller(expand=expand, validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.COMPLETED
        assert ctrl.revise_count == 1
        assert expand.call_count == 2
        assert validate.call_count == 2

    @pytest.mark.asyncio
    async def test_revise_twice_treated_as_approved(self) -> None:
        """First verdict=revise, retry, second verdict=revise -> treat as approved."""
        expand = FakeExpandService()
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_REVISE),
            ]
        )
        ctrl = _make_controller(expand=expand, validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.COMPLETED
        assert ctrl.revise_count == 1
        assert expand.call_count == 2
        assert validate.call_count == 2

    @pytest.mark.asyncio
    async def test_reject_once_then_approved(self) -> None:
        """First verdict=reject, retry EXPAND, second verdict=approved."""
        expand = FakeExpandService()
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REJECT),
                _make_verdict(VERDICT_APPROVED),
            ]
        )
        ctrl = _make_controller(expand=expand, validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.COMPLETED
        assert ctrl.revise_count == 1
        assert expand.call_count == 2

    @pytest.mark.asyncio
    async def test_reject_once_then_revise_treated_as_approved(self) -> None:
        """First verdict=reject, retry, second verdict=revise -> treat as approved."""
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REJECT),
                _make_verdict(VERDICT_REVISE),
            ]
        )
        ctrl = _make_controller(validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.COMPLETED
        assert ctrl.revise_count == 1

    @pytest.mark.asyncio
    async def test_reject_twice_fails(self) -> None:
        """First verdict=reject, retry, second verdict=reject -> FAILED."""
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REJECT),
                _make_verdict(VERDICT_REJECT),
            ]
        )
        ctrl = _make_controller(validate=validate)
        with pytest.raises(ValidateRejectedError) as exc_info:
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED
        assert "rejected after retry" in str(exc_info.value).lower()
        assert ctrl.revise_count == 1

    @pytest.mark.asyncio
    async def test_reject_twice_emits_plan_failed(self) -> None:
        """Reject after retry -> plan.failed.v1 event emitted."""
        ep = FakeEventPort()
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REJECT),
                _make_verdict(VERDICT_REJECT),
            ]
        )
        ctrl = _make_controller(validate=validate, event_port=ep)
        with pytest.raises(ValidateRejectedError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        # plan.failed.v1 emitted by PLAN-12 handler
        failed_events = [(t, p) for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed_events) == 1
        payload = failed_events[0][1]
        assert isinstance(payload, PlanFailedPayload)
        assert payload.error_code == "ValidateRejectedError"

    @pytest.mark.asyncio
    async def test_reject_twice_sets_stage_validate(self) -> None:
        ep = FakeEventPort()
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REJECT),
                _make_verdict(VERDICT_REJECT),
            ]
        )
        ctrl = _make_controller(validate=validate, event_port=ep)
        with pytest.raises(ValidateRejectedError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        failed_events = [(t, p) for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert failed_events[0][1].stage == StagePhase.VALIDATE.value

    @pytest.mark.asyncio
    async def test_revise_then_reject_fails(self) -> None:
        """First verdict=revise, retry, second verdict=reject -> FAILED."""
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_REJECT),
            ]
        )
        ctrl = _make_controller(validate=validate)
        with pytest.raises(ValidateRejectedError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED
        assert ctrl.revise_count == 1

    @pytest.mark.asyncio
    async def test_revise_count_not_incremented_on_approved(self) -> None:
        ctrl = _make_controller()
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.revise_count == 0

    @pytest.mark.asyncio
    async def test_max_one_revise_loop(self) -> None:
        """Even with many potential revises, only one retry occurs."""
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_REVISE),  # never reached
            ]
        )
        ctrl = _make_controller(validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert validate.call_count == 2


# ===========================================================================
# 4. PLAN-12 error handling (uncaught exceptions)
# ===========================================================================


class TestPLAN12ErrorHandling:
    """Outer try/except wraps execute() body -- PLAN-12 compliance."""

    @pytest.mark.asyncio
    async def test_sketch_error_forces_failed(self) -> None:
        sketch = FakeSketchService(error=RuntimeError("sketch boom"))
        ctrl = _make_controller(sketch=sketch)
        with pytest.raises(RuntimeError, match="sketch boom"):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED

    @pytest.mark.asyncio
    async def test_expand_error_forces_failed(self) -> None:
        expand = FakeExpandService(error=RuntimeError("expand boom"))
        ctrl = _make_controller(expand=expand)
        with pytest.raises(RuntimeError, match="expand boom"):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED

    @pytest.mark.asyncio
    async def test_validate_error_forces_failed(self) -> None:
        validate = FakeValidateService(error=RuntimeError("validate boom"))
        ctrl = _make_controller(validate=validate)
        with pytest.raises(RuntimeError, match="validate boom"):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED

    @pytest.mark.asyncio
    async def test_commit_error_forces_failed(self) -> None:
        commit = FakeCommitService(error=RuntimeError("commit boom"))
        ctrl = _make_controller(commit=commit)
        with pytest.raises(RuntimeError, match="commit boom"):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED

    @pytest.mark.asyncio
    async def test_uncaught_emits_plan_failed_event(self) -> None:
        ep = FakeEventPort()
        sketch = FakeSketchService(error=ValueError("bad input"))
        ctrl = _make_controller(sketch=sketch, event_port=ep)
        with pytest.raises(ValueError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        failed_events = [(t, p) for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed_events) == 1
        payload = failed_events[0][1]
        assert isinstance(payload, PlanFailedPayload)
        assert payload.error_code == "ValueError"
        assert "bad input" in payload.error_message

    @pytest.mark.asyncio
    async def test_uncaught_plan_failed_has_request_id(self) -> None:
        ep = FakeEventPort()
        sketch = FakeSketchService(error=RuntimeError("boom"))
        req = FakePlanRequest(request_id="req-fail-id")
        ctrl = _make_controller(sketch=sketch, event_port=ep)
        with pytest.raises(RuntimeError):
            await ctrl.execute(req, _never_cancel)
        payload = [p for t, p in ep.emitted if t == TOPIC_PLAN_FAILED][0]
        assert payload.request_id == "req-fail-id"

    @pytest.mark.asyncio
    async def test_uncaught_plan_failed_has_trace_id(self) -> None:
        ep = FakeEventPort()
        sketch = FakeSketchService(error=RuntimeError("boom"))
        req = FakePlanRequest(trace_id="trace-fail")
        ctrl = _make_controller(sketch=sketch, event_port=ep)
        with pytest.raises(RuntimeError):
            await ctrl.execute(req, _never_cancel)
        payload = [p for t, p in ep.emitted if t == TOPIC_PLAN_FAILED][0]
        assert payload.trace_id == "trace-fail"

    @pytest.mark.asyncio
    async def test_uncaught_plan_failed_has_duration(self) -> None:
        ep = FakeEventPort()
        sketch = FakeSketchService(error=RuntimeError("boom"))
        ctrl = _make_controller(sketch=sketch, event_port=ep)
        with pytest.raises(RuntimeError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        payload = [p for t, p in ep.emitted if t == TOPIC_PLAN_FAILED][0]
        assert payload.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_uncaught_reraises_original_exception(self) -> None:
        original_err = TypeError("original error")
        sketch = FakeSketchService(error=original_err)
        ctrl = _make_controller(sketch=sketch)
        with pytest.raises(TypeError) as exc_info:
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert exc_info.value is original_err

    @pytest.mark.asyncio
    async def test_planner_error_stage_attribution(self) -> None:
        """PlannerError subclass stage is used in plan.failed.v1 payload."""
        ep = FakeEventPort()
        err = PlannerError("stage-specific", stage="SKETCH")
        sketch = FakeSketchService(error=err)
        ctrl = _make_controller(sketch=sketch, event_port=ep)
        with pytest.raises(PlannerError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        payload = [p for t, p in ep.emitted if t == TOPIC_PLAN_FAILED][0]
        assert payload.stage == "SKETCH"

    @pytest.mark.asyncio
    async def test_plan_failed_event_port_failure_does_not_block(self) -> None:
        """If event_port.emit raises, the original error is still raised."""
        ep = FakeEventPort(fail=True)
        sketch = FakeSketchService(error=RuntimeError("boom"))
        ctrl = _make_controller(sketch=sketch, event_port=ep)
        with pytest.raises(RuntimeError, match="boom"):
            await ctrl.execute(FakePlanRequest(), _never_cancel)

    @pytest.mark.asyncio
    async def test_validate_rejected_emits_plan_failed(self) -> None:
        """ValidateRejectedError (from reject-after-retry) also emits plan.failed.v1."""
        ep = FakeEventPort()
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REJECT),
                _make_verdict(VERDICT_REJECT),
            ]
        )
        ctrl = _make_controller(validate=validate, event_port=ep)
        with pytest.raises(ValidateRejectedError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        failed_events = [t for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed_events) == 1

    @pytest.mark.asyncio
    async def test_force_failed_not_called_when_already_terminal(self) -> None:
        """If FSM is already in terminal state (e.g. from reject routing),
        force_failed is not called again."""
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REJECT),
                _make_verdict(VERDICT_REJECT),
            ]
        )
        ctrl = _make_controller(validate=validate)
        with pytest.raises(ValidateRejectedError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        # FSM should be FAILED, not double-transitioned
        assert ctrl.current_state == PlanState.FAILED


# ===========================================================================
# 5. Cancel between stages
# ===========================================================================


class TestCancelBetweenStages:
    """Basic cooperative cancellation (Issue 2.2.2 baseline)."""

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_raises_cancelled(self) -> None:
        call_count = 0

        def cancel_after_sketch() -> bool:
            # sketch runs, then cancel
            return call_count > 0

        class CountingSketch(FakeSketchService):
            async def execute(self, r: Any, c: Any) -> Any:
                nonlocal call_count
                call_count += 1
                return await super().execute(r, c)

        ctrl = _make_controller(sketch=CountingSketch())
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel_after_sketch)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_after_expand_raises_cancelled(self) -> None:
        stage_count = 0

        def cancel_after_expand() -> bool:
            return stage_count >= 2  # cancel after expand

        class CountingSketch(FakeSketchService):
            async def execute(self, r: Any, c: Any) -> Any:
                nonlocal stage_count
                stage_count += 1
                return await super().execute(r, c)

        class CountingExpand(FakeExpandService):
            async def execute(self, r: Any, c: Any) -> Any:
                nonlocal stage_count
                stage_count += 1
                return await super().execute(r, c)

        ctrl = _make_controller(
            sketch=CountingSketch(),
            expand=CountingExpand(),
        )
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel_after_expand)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_does_not_emit_plan_failed(self) -> None:
        """PlanCancelledError is NOT caught by PLAN-12 handler (no plan.failed.v1)."""
        ep = FakeEventPort()

        def always_cancel() -> bool:
            return True

        # Cancel happens at the first check (after sketch, but sketch
        # needs to run first -- cancel_check is checked AFTER service call)
        # Actually, cancel is checked after sketch completes. But the
        # first call to _build_stage_context passes cancel to StageContext.
        # The pipeline checks cancel_check() explicitly between stages.
        # With always_cancel=True, the check after sketch will trigger.
        ctrl = _make_controller(event_port=ep)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), always_cancel)
        failed_events = [t for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed_events) == 0

    @pytest.mark.asyncio
    async def test_cancel_error_has_stage_info(self) -> None:
        def always_cancel() -> bool:
            return True

        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(FakePlanRequest(), always_cancel)
        assert exc_info.value.stage == StagePhase.SKETCH.value

    @pytest.mark.asyncio
    async def test_cancel_error_has_request_id(self) -> None:
        def always_cancel() -> bool:
            return True

        req = FakePlanRequest(request_id="req-cancel")
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(req, always_cancel)
        assert exc_info.value.request_id == "req-cancel"


# ===========================================================================
# 6. Timeout enforcement (basic PLAN-04)
# ===========================================================================


class TestTimeoutEnforcement:
    """Basic pipeline timeout check (Issue 2.2.2, enhanced in 2.2.6)."""

    @pytest.mark.asyncio
    async def test_timeout_raises_planner_error(self) -> None:
        """Pipeline exceeding timeout raises PlannerError."""
        config = PlannerConfig(pipeline_timeout_ms=1)  # 1ms timeout

        class SlowSketch(FakeSketchService):
            async def execute(self, r: Any, c: Any) -> Any:
                await asyncio.sleep(0.01)  # 10ms > 1ms timeout
                return await super().execute(r, c)

        ctrl = _make_controller(sketch=SlowSketch(), config=config)
        with pytest.raises(PlannerError, match="exceeded"):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED

    @pytest.mark.asyncio
    async def test_timeout_emits_plan_failed(self) -> None:
        ep = FakeEventPort()
        config = PlannerConfig(pipeline_timeout_ms=1)

        class SlowSketch(FakeSketchService):
            async def execute(self, r: Any, c: Any) -> Any:
                await asyncio.sleep(0.01)
                return await super().execute(r, c)

        ctrl = _make_controller(
            sketch=SlowSketch(),
            config=config,
            event_port=ep,
        )
        with pytest.raises(PlannerError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        failed_events = [t for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed_events) == 1

    @pytest.mark.asyncio
    async def test_no_timeout_within_budget(self) -> None:
        """Pipeline within timeout completes normally."""
        config = PlannerConfig(pipeline_timeout_ms=60_000)  # 60s
        ctrl = _make_controller(config=config)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.COMPLETED


# ===========================================================================
# 7. Delta emission
# ===========================================================================


class TestDeltaEmission:
    """Delta payloads emitted at each transition and plan_end."""

    @pytest.mark.asyncio
    async def test_stage_transition_deltas_emitted(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        stage_deltas = [d for d in dp.emitted if d.delta_type == DELTA_STAGE_TRANSITION]
        # 5 transitions: IDLE->SKETCHING, SKETCHING->EXPANDING,
        # EXPANDING->VALIDATING, VALIDATING->COMMITTING, COMMITTING->COMPLETED
        assert len(stage_deltas) == 5

    @pytest.mark.asyncio
    async def test_plan_end_delta_emitted(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        end_deltas = [d for d in dp.emitted if d.delta_type == DELTA_PLAN_END]
        assert len(end_deltas) == 1

    @pytest.mark.asyncio
    async def test_plan_end_delta_data(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        end_delta = [d for d in dp.emitted if d.delta_type == DELTA_PLAN_END][0]
        assert end_delta.data["status"] == "completed"
        assert end_delta.data["revise_count"] == 0
        assert end_delta.data["total_tokens"] == 0
        assert end_delta.data["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_plan_end_delta_has_trace_id(self) -> None:
        dp = FakeDeltaPort()
        req = FakePlanRequest(trace_id="trace-end")
        ctrl = _make_controller(delta_port=dp)
        await ctrl.execute(req, _never_cancel)
        end_delta = [d for d in dp.emitted if d.delta_type == DELTA_PLAN_END][0]
        assert end_delta.trace_id == "trace-end"

    @pytest.mark.asyncio
    async def test_all_deltas_have_planner_agent_id(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        for delta in dp.emitted:
            assert delta.agent_id == PLANNER_AGENT_ID

    @pytest.mark.asyncio
    async def test_all_deltas_have_pipeline_section(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        for delta in dp.emitted:
            assert delta.section == SECTION_PIPELINE

    @pytest.mark.asyncio
    async def test_delta_port_failure_does_not_block_execute(self) -> None:
        dp = FakeDeltaPort(fail=True)
        ctrl = _make_controller(delta_port=dp)
        # Should still complete despite delta emission failures
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.COMPLETED

    @pytest.mark.asyncio
    async def test_revise_loop_emits_extra_deltas(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(
            validate=FakeValidateService(
                verdicts=[
                    _make_verdict(VERDICT_REVISE),
                    _make_verdict(VERDICT_APPROVED),
                ]
            ),
            delta_port=dp,
        )
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        stage_deltas = [d for d in dp.emitted if d.delta_type == DELTA_STAGE_TRANSITION]
        # 7 transitions with revise loop (see TestFSMTransitions)
        assert len(stage_deltas) == 7

    @pytest.mark.asyncio
    async def test_no_plan_end_delta_on_failure(self) -> None:
        dp = FakeDeltaPort()
        sketch = FakeSketchService(error=RuntimeError("boom"))
        ctrl = _make_controller(sketch=sketch, delta_port=dp)
        with pytest.raises(RuntimeError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        end_deltas = [d for d in dp.emitted if d.delta_type == DELTA_PLAN_END]
        assert len(end_deltas) == 0


# ===========================================================================
# 8. StageContext construction
# ===========================================================================


class TestStageContextConstruction:
    """_build_stage_context creates valid StageContext for each stage."""

    @pytest.mark.asyncio
    async def test_sketch_receives_stage_context(self) -> None:
        sketch = FakeSketchService()
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        ctx = sketch.calls[0][1]
        assert isinstance(ctx, StageContext)

    @pytest.mark.asyncio
    async def test_context_has_request_id(self) -> None:
        sketch = FakeSketchService()
        req = FakePlanRequest(request_id="req-ctx")
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(req, _never_cancel)
        ctx = sketch.calls[0][1]
        assert ctx.request_id == "req-ctx"

    @pytest.mark.asyncio
    async def test_context_has_trace_id(self) -> None:
        sketch = FakeSketchService()
        req = FakePlanRequest(trace_id="trace-ctx")
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(req, _never_cancel)
        ctx = sketch.calls[0][1]
        assert ctx.trace_id == "trace-ctx"

    @pytest.mark.asyncio
    async def test_context_has_positive_timeout(self) -> None:
        sketch = FakeSketchService()
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        ctx = sketch.calls[0][1]
        assert ctx.timeout_remaining_ms > 0

    @pytest.mark.asyncio
    async def test_context_has_nonnegative_token_budget(self) -> None:
        sketch = FakeSketchService()
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        ctx = sketch.calls[0][1]
        assert ctx.token_budget_remaining >= 0

    @pytest.mark.asyncio
    async def test_context_cancel_check_is_callable(self) -> None:
        sketch = FakeSketchService()
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        ctx = sketch.calls[0][1]
        assert callable(ctx.cancel_check)

    @pytest.mark.asyncio
    async def test_context_cancel_check_forwards_to_cancel_arg(self) -> None:
        sketch = FakeSketchService()
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        ctx = sketch.calls[0][1]
        assert ctx.cancel_check() is False

    @pytest.mark.asyncio
    async def test_expand_receives_stage_context(self) -> None:
        expand = FakeExpandService()
        ctrl = _make_controller(expand=expand)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        ctx = expand.calls[0][1]
        assert isinstance(ctx, StageContext)

    @pytest.mark.asyncio
    async def test_validate_receives_stage_context(self) -> None:
        validate = FakeValidateService()
        ctrl = _make_controller(validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        ctx = validate.calls[0][1]
        assert isinstance(ctx, StageContext)

    @pytest.mark.asyncio
    async def test_commit_receives_stage_context(self) -> None:
        commit = FakeCommitService()
        ctrl = _make_controller(commit=commit)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        ctx = commit.calls[0][2]  # (expanded_plan, verdict, ctx)
        assert isinstance(ctx, StageContext)

    @pytest.mark.asyncio
    async def test_timeout_remaining_decreases_across_stages(self) -> None:
        """Later stages get less remaining time than earlier ones."""

        class SlowSketch(FakeSketchService):
            async def execute(self, r: Any, c: Any) -> Any:
                await asyncio.sleep(0.005)  # 5ms
                return await super().execute(r, c)

        sketch = SlowSketch()
        expand = FakeExpandService()
        ctrl = _make_controller(sketch=sketch, expand=expand)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        sketch_timeout = sketch.calls[0][1].timeout_remaining_ms
        expand_timeout = expand.calls[0][1].timeout_remaining_ms
        # Expand should have less remaining time
        assert expand_timeout <= sketch_timeout


# ===========================================================================
# 9. Reset at plan start
# ===========================================================================


class TestResetAtPlanStart:
    """execute() calls reset() at the start of each plan."""

    @pytest.mark.asyncio
    async def test_reset_called_before_pipeline(self) -> None:
        """After a previous plan (simulated via manual FSM), execute resets."""
        ctrl = _make_controller()
        # Simulate a previous plan
        ctrl._stage_token_usage = {"SKETCH": 100}
        ctrl._total_plan_tokens = 100
        ctrl._tool_call_count = 5
        ctrl._revise_count = 1

        await ctrl.execute(FakePlanRequest(), _never_cancel)

        # Token usage should be reset (initial reset values from reset())
        assert ctrl._stage_token_usage == {
            "SKETCH": 0,
            "EXPAND": 0,
            "VALIDATE": 0,
            "COMMIT": 0,
        }
        assert ctrl.revise_count == 0

    @pytest.mark.asyncio
    async def test_second_execute_resets_state(self) -> None:
        """Consecutive execute() calls each start fresh."""
        committed1 = FakeCommittedPlan(plan_id="plan-1")
        committed2 = FakeCommittedPlan(plan_id="plan-2")
        commit_results = [committed1, committed2]
        call_idx = 0

        class MultiCommit(FakeCommitService):
            async def execute(self, e: Any, v: Any, c: Any) -> Any:
                nonlocal call_idx
                result = commit_results[call_idx]
                call_idx += 1
                return result

        ctrl = _make_controller(commit=MultiCommit())

        result1 = await ctrl.execute(FakePlanRequest(), _never_cancel)
        # Reset FSM for second call (normally PlannerAgent handles this)
        ctrl._fsm.reset()
        result2 = await ctrl.execute(
            FakePlanRequest(request_id="req-002"),
            _never_cancel,
        )

        assert result1 is committed1
        assert result2 is committed2
        assert ctrl.current_request.request_id == "req-002"


# ===========================================================================
# 10. Helper method unit tests
# ===========================================================================


class TestElapsedMs:
    """_elapsed_ms() helper."""

    def test_returns_zero_when_no_start_time(self) -> None:
        ctrl = _make_controller()
        assert ctrl._elapsed_ms() == 0

    def test_returns_positive_after_start(self) -> None:
        ctrl = _make_controller()
        ctrl._plan_start_time = time.monotonic() - 0.1  # 100ms ago
        elapsed = ctrl._elapsed_ms()
        assert elapsed >= 90  # at least ~90ms (accounting for timing variance)

    def test_returns_integer(self) -> None:
        ctrl = _make_controller()
        ctrl._plan_start_time = time.monotonic()
        assert isinstance(ctrl._elapsed_ms(), int)


class TestCheckCancel:
    """_check_cancel() helper."""

    def test_no_cancel_returns_none(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        # Should not raise
        ctrl._check_cancel(_never_cancel, "SKETCH")

    def test_cancel_raises_plan_cancelled_error(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        # Manually set FSM to an active state
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlanCancelledError):
            ctrl._check_cancel(lambda: True, "SKETCH")

    def test_cancel_sets_fsm_cancelled(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlanCancelledError):
            ctrl._check_cancel(lambda: True, "SKETCH")
        assert ctrl.current_state == PlanState.CANCELLED

    def test_cancel_error_has_stage(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlanCancelledError) as exc_info:
            ctrl._check_cancel(lambda: True, "SKETCH")
        assert exc_info.value.stage == "SKETCH"

    def test_cancel_error_has_request_id(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest(request_id="req-cc")
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlanCancelledError) as exc_info:
            ctrl._check_cancel(lambda: True, "SKETCH")
        assert exc_info.value.request_id == "req-cc"


class TestCheckTimeout:
    """_check_timeout() helper."""

    def test_no_timeout_within_budget(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        # Should not raise
        ctrl._check_timeout("SKETCH")

    def test_timeout_raises_planner_error(self) -> None:
        config = PlannerConfig(pipeline_timeout_ms=1)
        ctrl = _make_controller(config=config)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic() - 1.0  # 1000ms ago > 1ms
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlannerError, match="exceeded"):
            ctrl._check_timeout("SKETCH")

    def test_timeout_sets_fsm_failed(self) -> None:
        config = PlannerConfig(pipeline_timeout_ms=1)
        ctrl = _make_controller(config=config)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic() - 1.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlannerError):
            ctrl._check_timeout("SKETCH")
        assert ctrl.current_state == PlanState.FAILED

    def test_no_start_time_does_not_raise(self) -> None:
        """If _plan_start_time is None, elapsed is 0 -> no timeout."""
        config = PlannerConfig(pipeline_timeout_ms=1)
        ctrl = _make_controller(config=config)
        ctrl._current_request = FakePlanRequest()
        # _plan_start_time is None by default
        ctrl._check_timeout("SKETCH")


class TestBuildStageContext:
    """_build_stage_context() helper."""

    def test_returns_stage_context(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert isinstance(ctx, StageContext)

    def test_request_id_from_current_request(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest(request_id="req-bsc")
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.request_id == "req-bsc"

    def test_trace_id_from_current_request(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest(trace_id="trace-bsc")
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.trace_id == "trace-bsc"

    def test_timeout_remaining_positive(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.timeout_remaining_ms > 0

    def test_token_budget_from_config(self) -> None:
        config = PlannerConfig(total_token_budget=5000)
        ctrl = _make_controller(config=config)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.token_budget_remaining == 5000

    def test_token_budget_decreases_with_usage(self) -> None:
        config = PlannerConfig(total_token_budget=5000)
        ctrl = _make_controller(config=config)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctrl._total_plan_tokens = 1000
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.EXPAND)
        assert ctx.token_budget_remaining == 4000

    def test_cancel_check_forwarded(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.cancel_check is _never_cancel

    def test_timeout_remaining_never_below_one(self) -> None:
        """Even if elapsed > budget, timeout_remaining_ms is at least 1."""
        config = PlannerConfig(pipeline_timeout_ms=1)
        ctrl = _make_controller(config=config)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic() - 10.0  # way past timeout
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.timeout_remaining_ms >= 1

    def test_token_budget_never_below_zero(self) -> None:
        config = PlannerConfig(total_token_budget=3500)
        ctrl = _make_controller(config=config)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctrl._total_plan_tokens = 5000  # over budget
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.token_budget_remaining == 0

    def test_unknown_request_id_when_no_request(self) -> None:
        ctrl = _make_controller()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.request_id == "unknown"

    def test_unknown_trace_id_when_no_request(self) -> None:
        ctrl = _make_controller()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.trace_id == "unknown"


# ===========================================================================
# 11. Plan.failed.v1 event emission
# ===========================================================================


class TestEmitPlanFailed:
    """_emit_plan_failed() helper."""

    def test_emits_topic_plan_failed(self) -> None:
        ep = FakeEventPort()
        ctrl = _make_controller(event_port=ep)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        exc = RuntimeError("test error")
        ctrl._emit_plan_failed(exc)
        assert len(ep.emitted) == 1
        assert ep.emitted[0][0] == TOPIC_PLAN_FAILED

    def test_payload_has_correct_error_code(self) -> None:
        ep = FakeEventPort()
        ctrl = _make_controller(event_port=ep)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctrl._emit_plan_failed(ValueError("bad"))
        payload = ep.emitted[0][1]
        assert payload.error_code == "ValueError"

    def test_payload_has_error_message(self) -> None:
        ep = FakeEventPort()
        ctrl = _make_controller(event_port=ep)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctrl._emit_plan_failed(RuntimeError("msg123"))
        payload = ep.emitted[0][1]
        assert "msg123" in payload.error_message

    def test_uses_planner_error_stage(self) -> None:
        ep = FakeEventPort()
        ctrl = _make_controller(event_port=ep)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        exc = PlannerError("pg error", stage="EXPAND")
        ctrl._emit_plan_failed(exc)
        payload = ep.emitted[0][1]
        assert payload.stage == "EXPAND"

    def test_event_port_failure_does_not_raise(self) -> None:
        ep = FakeEventPort(fail=True)
        ctrl = _make_controller(event_port=ep)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        # Should not raise
        ctrl._emit_plan_failed(RuntimeError("boom"))


# ===========================================================================
# 12. Plan_end delta emission
# ===========================================================================


class TestEmitPlanEndDelta:
    """_emit_plan_end_delta() helper."""

    def test_emits_plan_end_delta(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctrl._emit_plan_end_delta()
        assert len(dp.emitted) == 1
        assert dp.emitted[0].delta_type == DELTA_PLAN_END

    def test_delta_has_completed_status(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctrl._emit_plan_end_delta()
        assert dp.emitted[0].data["status"] == "completed"

    def test_delta_has_revise_count(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctrl._revise_count = 1
        ctrl._emit_plan_end_delta()
        assert dp.emitted[0].data["revise_count"] == 1

    def test_delta_port_failure_does_not_raise(self) -> None:
        dp = FakeDeltaPort(fail=True)
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        # Should not raise
        ctrl._emit_plan_end_delta()


# ===========================================================================
# 13. Edge cases and integration scenarios
# ===========================================================================


class TestEdgeCases:
    """Edge cases for execute() orchestration."""

    @pytest.mark.asyncio
    async def test_cancel_check_called_between_sketch_and_expand(self) -> None:
        """cancel_check is called at every inter-stage checkpoint."""
        cancel_calls: List[bool] = []
        call_count = 0

        def tracking_cancel() -> bool:
            nonlocal call_count
            call_count += 1
            cancel_calls.append(False)
            return False

        ctrl = _make_controller()
        await ctrl.execute(FakePlanRequest(), tracking_cancel)
        # cancel_check called in StageContext.cancel_check + explicit checks
        # At minimum: 2 explicit checks (after sketch, after expand)
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_verdict_routing_reject_after_revise_retry(self) -> None:
        """revise -> re-EXPAND -> reject -> FAILED."""
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_REJECT),
            ]
        )
        ctrl = _make_controller(validate=validate)
        with pytest.raises(ValidateRejectedError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert ctrl.current_state == PlanState.FAILED
        assert ctrl.revise_count == 1  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_commit_receives_latest_expanded_plan(self) -> None:
        """On revise, commit gets the re-expanded plan."""
        expand_results = [{"v": 1}, {"v": 2}]
        expand_idx = 0

        class MultiExpand(FakeExpandService):
            async def execute(self, r: Any, c: Any) -> Any:
                nonlocal expand_idx
                result = expand_results[expand_idx]
                expand_idx += 1
                self.call_count += 1
                self.calls.append((r, c))
                return result

        commit = FakeCommitService()
        ctrl = _make_controller(
            expand=MultiExpand(),
            validate=FakeValidateService(
                verdicts=[
                    _make_verdict(VERDICT_REVISE),
                    _make_verdict(VERDICT_APPROVED),
                ]
            ),
            commit=commit,
        )
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        # Commit should receive the SECOND expanded plan
        assert commit.calls[0][0] == {"v": 2}

    @pytest.mark.asyncio
    async def test_commit_receives_latest_verdict(self) -> None:
        """On revise, commit gets the second (approved) verdict."""
        verdict_approved = _make_verdict(VERDICT_APPROVED, rationale="second pass")
        commit = FakeCommitService()
        ctrl = _make_controller(
            validate=FakeValidateService(
                verdicts=[
                    _make_verdict(VERDICT_REVISE),
                    verdict_approved,
                ]
            ),
            commit=commit,
        )
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert commit.calls[0][1] is verdict_approved

    @pytest.mark.asyncio
    async def test_multiple_rapid_executions(self) -> None:
        """Multiple sequential executions each produce correct results."""
        results = []
        for i in range(3):
            committed = FakeCommittedPlan(plan_id=f"plan-{i}")
            ctrl = _make_controller(
                commit=FakeCommitService(result=committed),
            )
            result = await ctrl.execute(
                FakePlanRequest(request_id=f"req-{i}"),
                _never_cancel,
            )
            results.append(result)
        assert [r.plan_id for r in results] == [
            "plan-0",
            "plan-1",
            "plan-2",
        ]
