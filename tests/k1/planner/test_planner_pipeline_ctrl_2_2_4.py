"""Tests for PipelineController cancel-between-stages protocol (Issue 2.2.4).

Tests cover:
  - Enhanced _check_cancel: FSM transitions, event emission, delta emission
  - Cancel at each inter-stage checkpoint (SKETCH->EXPAND, EXPAND->VALIDATE,
    VALIDATE->COMMIT)
  - Cancel semantics: cooperative, NOT preemptive (cancel only detected at
    checkpoints, not mid-stage)
  - Side effects: plan.cancelled.v1 event with PlanCancelledPayload,
    plan_cancelled delta with request_id and reason
  - Edge cases: cancel with no current_request, fire-and-forget event/delta
    failure tolerance, cancel after revise loop
  - PlanCancelledError attributes (stage, request_id, trace_id)
  - FSM ends in CANCELLED state
  - No plan.failed.v1 emitted on cancel (only plan.cancelled.v1)

5 cancel checkpoints (Section 24.2.2):
  (1) pre-execution at mailbox dequeue (PlannerAgent -- not tested here)
  (2) between SKETCH and EXPAND (PipelineController)
  (3) between EXPAND and VALIDATE (PipelineController)
  (4) between VALIDATE and COMMIT (PipelineController)
  (5) before WAL persist in CommitService (not tested here)

References
----------
- planner.md Section 18.5.3 (Cancel semantics)
- planner.md Section 24.2   (Cancellation protocol)
- planner.md Section 24.2.1 (Cancel timing -- cooperative)
- planner.md Section 24.2.2 (5 cancel checkpoints)
- planner.md Section 30.5.1 F03 (pipeline_controller.py spec)
- docs/plans/planner-implementation-plan.md Issue 2.2.4
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import pytest

from k1.planner.config import PlannerConfig
from k1.planner.events import TOPIC_PLAN_CANCELLED, TOPIC_PLAN_FAILED, PlanCancelledPayload
from k1.planner.pipeline_controller import PipelineController
from k1.planner.plan_fsm import PlanState
from k1.planner.types import (
    DELTA_PLAN_CANCELLED,
    DELTA_STAGE_TRANSITION,
    PLANNER_AGENT_ID,
    SECTION_PIPELINE,
    VERDICT_APPROVED,
    VERDICT_REJECT,
    VERDICT_REVISE,
    DeltaPayload,
    PlanCancelledError,
    StageContext,
    StagePhase,
    ValidationIssue,
    ValidationVerdict,
)

# ---------------------------------------------------------------------------
# Test helpers -- fake services and ports
# ---------------------------------------------------------------------------


@dataclass
class FakePlanRequest:
    """Minimal stand-in for PlanRequest (from k1.orchestrator.types)."""

    request_id: str = "req-cancel-001"
    trace_id: str = "trace-cancel-abc"
    intent: str = "test cancel intent"


@dataclass
class FakeCommittedPlan:
    """Minimal stand-in for CommittedPlan."""

    plan_id: str = "plan-001"
    request_id: str = "req-cancel-001"
    intent: str = "test cancel intent"
    trace_id: str = "trace-cancel-abc"


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

    async def execute(self, sketch_result: Any, request: Any, ctx: StageContext) -> Any:
        self.call_count += 1
        self.calls.append((sketch_result, ctx))
        if self._error is not None:
            raise self._error
        return self._result


class FakeValidateService:
    """Fake ValidateService that returns verdicts from a configurable list."""

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

    async def execute(self, expanded_plan: Any, request: Any, ctx: StageContext) -> Any:
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
        request: Any,
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


def _always_cancel() -> bool:
    """Cancel check that always cancels."""
    return True


# ---------------------------------------------------------------------------
# Stateful cancel triggers
# ---------------------------------------------------------------------------


class CancelAfterN:
    """Cancel check that returns True after N calls.

    First N calls return False; subsequent calls return True.
    """

    def __init__(self, n: int) -> None:
        self._n = n
        self.call_count: int = 0

    def __call__(self) -> bool:
        self.call_count += 1
        return self.call_count > self._n


class CancelAtStage:
    """Cancel check that returns True only when called with a specific stage.

    Works as a closure: PipelineController calls ``cancel_check()`` (no args),
    so this tracks call count and maps expected counts to True/False.

    Usage: Determine which call number corresponds to the desired checkpoint
    and set ``cancel_at_call`` accordingly.
    """

    def __init__(self, cancel_at_call: int) -> None:
        self._cancel_at_call = cancel_at_call
        self.call_count: int = 0

    def __call__(self) -> bool:
        self.call_count += 1
        return self.call_count >= self._cancel_at_call


# ===========================================================================
# 1. _check_cancel direct tests (unit-level)
# ===========================================================================


class TestCheckCancelDirect:
    """Direct tests of _check_cancel() method behaviour."""

    @pytest.mark.asyncio
    async def test_no_cancel_does_nothing(self) -> None:
        """When cancel_check returns False, no action taken."""
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        # Should not raise
        ctrl._check_cancel(_never_cancel, StagePhase.SKETCH.value)
        assert ctrl.current_state == PlanState.SKETCHING

    @pytest.mark.asyncio
    async def test_cancel_transitions_fsm_to_cancelled(self) -> None:
        """When cancel_check returns True, FSM transitions to CANCELLED."""
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlanCancelledError):
            ctrl._check_cancel(_always_cancel, StagePhase.SKETCH.value)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_raises_plan_cancelled_error(self) -> None:
        """PlanCancelledError raised with correct attributes."""
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = FakePlanRequest(
            request_id="req-X",
            trace_id="trace-Y",
        )
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        ctrl._fsm.transition(PlanState.EXPANDING, trigger="test")
        with pytest.raises(PlanCancelledError) as exc_info:
            ctrl._check_cancel(_always_cancel, StagePhase.EXPAND.value)
        err = exc_info.value
        assert err.stage == StagePhase.EXPAND.value
        assert err.request_id == "req-X"
        assert err.trace_id == "trace-Y"

    @pytest.mark.asyncio
    async def test_cancel_emits_plan_cancelled_event(self) -> None:
        """plan.cancelled.v1 event emitted with PlanCancelledPayload."""
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        ctrl.reset()
        ctrl._current_request = FakePlanRequest(
            request_id="req-E",
            trace_id="trace-E",
        )
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlanCancelledError):
            ctrl._check_cancel(_always_cancel, StagePhase.SKETCH.value)
        # Find the plan.cancelled.v1 event
        cancelled_events = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled_events) == 1
        topic, payload = cancelled_events[0]
        assert topic == TOPIC_PLAN_CANCELLED
        assert isinstance(payload, PlanCancelledPayload)
        assert payload.request_id == "req-E"
        assert payload.reason == "cancelled_between_stages"
        assert payload.stage == StagePhase.SKETCH.value
        assert payload.trace_id == "trace-E"

    @pytest.mark.asyncio
    async def test_cancel_emits_plan_cancelled_delta(self) -> None:
        """plan_cancelled delta emitted with request_id, reason, stage."""
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        ctrl.reset()
        ctrl._current_request = FakePlanRequest(
            request_id="req-D",
            trace_id="trace-D",
        )
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        ctrl._fsm.transition(PlanState.EXPANDING, trigger="test")
        ctrl._fsm.transition(PlanState.VALIDATING, trigger="test")
        with pytest.raises(PlanCancelledError):
            ctrl._check_cancel(_always_cancel, StagePhase.VALIDATE.value)
        # Find plan_cancelled deltas
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert len(cancelled_deltas) == 1
        d = cancelled_deltas[0]
        assert d.agent_id == PLANNER_AGENT_ID
        assert d.section == SECTION_PIPELINE
        assert d.data["request_id"] == "req-D"
        assert d.data["reason"] == "cancelled_between_stages"
        assert d.data["stage"] == StagePhase.VALIDATE.value
        assert d.trace_id == "trace-D"

    @pytest.mark.asyncio
    async def test_cancel_fsm_trigger_contains_stage(self) -> None:
        """FSM force_cancelled trigger includes the stage name."""
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        ctrl._fsm.transition(PlanState.EXPANDING, trigger="test")
        with pytest.raises(PlanCancelledError):
            ctrl._check_cancel(_always_cancel, StagePhase.EXPAND.value)
        # The FSM transition callback should have fired with the trigger
        transition_deltas = [
            d for d in delta_port.emitted if d.delta_type == DELTA_STAGE_TRANSITION
        ]
        # Find the one that goes to CANCELLED
        cancel_transitions = [
            d for d in transition_deltas if d.data.get("to_state") == PlanState.CANCELLED.value
        ]
        assert len(cancel_transitions) == 1
        assert "cancelled_between_EXPAND" in cancel_transitions[0].data["trigger"]


# ===========================================================================
# 2. Cancel at each inter-stage checkpoint via execute()
# ===========================================================================


class TestCancelBetweenSketchAndExpand:
    """Checkpoint 2: Cancel between SKETCH and EXPAND."""

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_raises(self) -> None:
        """Cancel detected after SKETCH completes raises PlanCancelledError."""
        # cancel_check returns True on 1st call (after SKETCH)
        cancel = CancelAfterN(0)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(FakePlanRequest(), cancel)
        assert exc_info.value.stage == StagePhase.SKETCH.value

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_fsm_cancelled(self) -> None:
        """FSM ends in CANCELLED state."""
        cancel = CancelAfterN(0)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_expand_not_called(self) -> None:
        """EXPAND service never called when cancel detected after SKETCH."""
        cancel = CancelAfterN(0)
        expand = FakeExpandService()
        ctrl = _make_controller(expand=expand)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert expand.call_count == 0

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_emits_cancelled_event(self) -> None:
        """plan.cancelled.v1 emitted with stage=SKETCH."""
        cancel = CancelAfterN(0)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1
        assert cancelled[0][1].stage == StagePhase.SKETCH.value

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_emits_cancelled_delta(self) -> None:
        """plan_cancelled delta emitted with stage=SKETCH."""
        cancel = CancelAfterN(0)
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert len(cancelled_deltas) == 1
        assert cancelled_deltas[0].data["stage"] == StagePhase.SKETCH.value

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_no_plan_failed_event(self) -> None:
        """No plan.failed.v1 event should be emitted on cancel."""
        cancel = CancelAfterN(0)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        failed_events = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed_events) == 0

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_sketch_completed(self) -> None:
        """SKETCH service was called before cancel detected."""
        cancel = CancelAfterN(0)
        sketch = FakeSketchService()
        ctrl = _make_controller(sketch=sketch)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert sketch.call_count == 1


class TestCancelBetweenExpandAndValidate:
    """Checkpoint 3: Cancel between EXPAND and VALIDATE."""

    @pytest.mark.asyncio
    async def test_cancel_after_expand_raises(self) -> None:
        """Cancel detected after EXPAND completes raises PlanCancelledError."""
        # 1st cancel_check (after SKETCH) -> False
        # 2nd cancel_check (after EXPAND) -> True
        cancel = CancelAfterN(1)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(FakePlanRequest(), cancel)
        assert exc_info.value.stage == StagePhase.EXPAND.value

    @pytest.mark.asyncio
    async def test_cancel_after_expand_fsm_cancelled(self) -> None:
        cancel = CancelAfterN(1)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_after_expand_validate_not_called(self) -> None:
        """VALIDATE service never called when cancel after EXPAND."""
        cancel = CancelAfterN(1)
        validate = FakeValidateService()
        ctrl = _make_controller(validate=validate)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert validate.call_count == 0

    @pytest.mark.asyncio
    async def test_cancel_after_expand_sketch_and_expand_called(self) -> None:
        """Both SKETCH and EXPAND were called before cancel."""
        cancel = CancelAfterN(1)
        sketch = FakeSketchService()
        expand = FakeExpandService()
        ctrl = _make_controller(sketch=sketch, expand=expand)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert sketch.call_count == 1
        assert expand.call_count == 1

    @pytest.mark.asyncio
    async def test_cancel_after_expand_emits_cancelled_event(self) -> None:
        cancel = CancelAfterN(1)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1
        assert cancelled[0][1].stage == StagePhase.EXPAND.value
        assert cancelled[0][1].reason == "cancelled_between_stages"

    @pytest.mark.asyncio
    async def test_cancel_after_expand_emits_cancelled_delta(self) -> None:
        cancel = CancelAfterN(1)
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert len(cancelled_deltas) == 1
        assert cancelled_deltas[0].data["stage"] == StagePhase.EXPAND.value

    @pytest.mark.asyncio
    async def test_cancel_after_expand_no_plan_failed_event(self) -> None:
        cancel = CancelAfterN(1)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        failed = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed) == 0


class TestCancelBetweenValidateAndCommit:
    """Checkpoint 4: Cancel between VALIDATE and COMMIT."""

    @pytest.mark.asyncio
    async def test_cancel_after_validate_raises(self) -> None:
        """Cancel detected after VALIDATE completes raises PlanCancelledError."""
        # 1st cancel_check (after SKETCH) -> False
        # 2nd cancel_check (after EXPAND) -> False
        # 3rd cancel_check (after VALIDATE) -> True
        cancel = CancelAfterN(2)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(FakePlanRequest(), cancel)
        assert exc_info.value.stage == StagePhase.VALIDATE.value

    @pytest.mark.asyncio
    async def test_cancel_after_validate_fsm_cancelled(self) -> None:
        cancel = CancelAfterN(2)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_after_validate_commit_not_called(self) -> None:
        """COMMIT service never called when cancel after VALIDATE."""
        cancel = CancelAfterN(2)
        commit = FakeCommitService()
        ctrl = _make_controller(commit=commit)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert commit.call_count == 0

    @pytest.mark.asyncio
    async def test_cancel_after_validate_all_prior_stages_called(self) -> None:
        """SKETCH, EXPAND, VALIDATE all called before cancel."""
        cancel = CancelAfterN(2)
        sketch = FakeSketchService()
        expand = FakeExpandService()
        validate = FakeValidateService()
        ctrl = _make_controller(
            sketch=sketch,
            expand=expand,
            validate=validate,
        )
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert sketch.call_count == 1
        assert expand.call_count == 1
        assert validate.call_count == 1

    @pytest.mark.asyncio
    async def test_cancel_after_validate_emits_cancelled_event(self) -> None:
        cancel = CancelAfterN(2)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1
        assert cancelled[0][1].stage == StagePhase.VALIDATE.value
        assert cancelled[0][1].reason == "cancelled_between_stages"

    @pytest.mark.asyncio
    async def test_cancel_after_validate_emits_cancelled_delta(self) -> None:
        cancel = CancelAfterN(2)
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert len(cancelled_deltas) == 1
        assert cancelled_deltas[0].data["stage"] == StagePhase.VALIDATE.value

    @pytest.mark.asyncio
    async def test_cancel_after_validate_no_plan_failed_event(self) -> None:
        cancel = CancelAfterN(2)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        failed = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed) == 0


# ===========================================================================
# 3. PlanCancelledPayload attribute verification
# ===========================================================================


class TestPlanCancelledPayloadAttributes:
    """Verify PlanCancelledPayload fields in emitted events."""

    @pytest.mark.asyncio
    async def test_payload_request_id_matches(self) -> None:
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        req = FakePlanRequest(request_id="req-payload-test")
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(req, _always_cancel)
        cancelled = [p for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert cancelled[0].request_id == "req-payload-test"

    @pytest.mark.asyncio
    async def test_payload_trace_id_matches(self) -> None:
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        req = FakePlanRequest(trace_id="trace-payload-test")
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(req, _always_cancel)
        cancelled = [p for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert cancelled[0].trace_id == "trace-payload-test"

    @pytest.mark.asyncio
    async def test_payload_reason_is_cancelled_between_stages(self) -> None:
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        cancelled = [p for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert cancelled[0].reason == "cancelled_between_stages"

    @pytest.mark.asyncio
    async def test_payload_stage_matches_cancel_location(self) -> None:
        """Stage in payload matches where cancel was detected."""
        # Cancel after EXPAND (checkpoint 3)
        cancel = CancelAfterN(1)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled = [p for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert cancelled[0].stage == StagePhase.EXPAND.value


# ===========================================================================
# 4. Delta payload verification
# ===========================================================================


class TestCancelDeltaPayload:
    """Verify plan_cancelled delta fields."""

    @pytest.mark.asyncio
    async def test_delta_agent_id_is_planner(self) -> None:
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert cancelled_deltas[0].agent_id == PLANNER_AGENT_ID

    @pytest.mark.asyncio
    async def test_delta_section_is_pipeline(self) -> None:
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert cancelled_deltas[0].section == SECTION_PIPELINE

    @pytest.mark.asyncio
    async def test_delta_data_contains_request_id(self) -> None:
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        req = FakePlanRequest(request_id="req-delta-test")
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(req, _always_cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert cancelled_deltas[0].data["request_id"] == "req-delta-test"

    @pytest.mark.asyncio
    async def test_delta_data_contains_reason(self) -> None:
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert cancelled_deltas[0].data["reason"] == "cancelled_between_stages"

    @pytest.mark.asyncio
    async def test_delta_data_contains_stage(self) -> None:
        delta_port = FakeDeltaPort()
        cancel = CancelAfterN(2)  # cancel after VALIDATE
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert cancelled_deltas[0].data["stage"] == StagePhase.VALIDATE.value

    @pytest.mark.asyncio
    async def test_delta_trace_id_matches_request(self) -> None:
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        req = FakePlanRequest(trace_id="trace-delta-verify")
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(req, _always_cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert cancelled_deltas[0].trace_id == "trace-delta-verify"


# ===========================================================================
# 5. Cooperative cancel semantics
# ===========================================================================


class TestCooperativeCancelSemantics:
    """Verify cancel is cooperative: detected at checkpoints, not mid-stage."""

    @pytest.mark.asyncio
    async def test_sketch_completes_before_cancel_detected(self) -> None:
        """SKETCH runs to completion even if cancel becomes True during it."""
        sketch = FakeSketchService()
        # Cancel is True from the start, but SKETCH still completes
        ctrl = _make_controller(sketch=sketch)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        # SKETCH completed (called once) before cancel was checked
        assert sketch.call_count == 1

    @pytest.mark.asyncio
    async def test_expand_completes_before_cancel_detected(self) -> None:
        """EXPAND runs to completion before checkpoint 3 detects cancel."""
        expand = FakeExpandService()
        cancel = CancelAfterN(1)  # False for checkpoint 2, True for 3
        ctrl = _make_controller(expand=expand)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        # EXPAND called once, completed, then cancel detected
        assert expand.call_count == 1

    @pytest.mark.asyncio
    async def test_validate_completes_before_cancel_detected(self) -> None:
        """VALIDATE runs to completion before checkpoint 4 detects cancel."""
        validate = FakeValidateService()
        cancel = CancelAfterN(2)  # False for 2,3; True for 4
        ctrl = _make_controller(validate=validate)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert validate.call_count == 1

    @pytest.mark.asyncio
    async def test_no_cancel_full_pipeline_succeeds(self) -> None:
        """Pipeline completes normally when cancel never fires."""
        committed = FakeCommittedPlan(plan_id="full-ok")
        ctrl = _make_controller(commit=FakeCommitService(result=committed))
        result = await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert result.plan_id == "full-ok"
        assert ctrl.current_state == PlanState.COMPLETED


# ===========================================================================
# 6. Cancel after revise loop
# ===========================================================================


class TestCancelAfterRevise:
    """Cancel detected after a revise loop iteration."""

    @pytest.mark.asyncio
    async def test_cancel_after_revise_expand_raises(self) -> None:
        """Cancel during second EXPAND iteration (after revise verdict)."""
        # Flow: SKETCH -> cancel_check(1:F) -> EXPAND -> cancel_check(2:F) ->
        #        VALIDATE(revise) -> EXPAND(retry) -> cancel_check(3:T) -> CANCEL
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_APPROVED),
            ],
        )
        cancel = CancelAfterN(2)  # 3rd call triggers cancel
        ctrl = _make_controller(validate=validate)
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(FakePlanRequest(), cancel)
        assert exc_info.value.stage == StagePhase.EXPAND.value

    @pytest.mark.asyncio
    async def test_cancel_after_revise_validate_raises(self) -> None:
        """Cancel after second VALIDATE in the revise loop."""
        # Flow: SKETCH -> check(1:F) -> EXPAND -> check(2:F) ->
        #        VALIDATE(revise) -> EXPAND -> check(3:F) ->
        #        VALIDATE -> check(4:T) -> CANCEL
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_APPROVED),
            ],
        )
        cancel = CancelAfterN(3)  # 4th call triggers cancel
        ctrl = _make_controller(validate=validate)
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(FakePlanRequest(), cancel)
        assert exc_info.value.stage == StagePhase.VALIDATE.value

    @pytest.mark.asyncio
    async def test_cancel_after_revise_emits_cancelled_event(self) -> None:
        """plan.cancelled.v1 emitted even when cancel follows a revise."""
        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_APPROVED),
            ],
        )
        cancel = CancelAfterN(2)
        event_port = FakeEventPort()
        ctrl = _make_controller(validate=validate, event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1


# ===========================================================================
# 7. Fire-and-forget: event/delta emission failure tolerance
# ===========================================================================


class TestCancelEmissionFailureTolerance:
    """Verify that event/delta emission failures don't block cancellation."""

    @pytest.mark.asyncio
    async def test_event_port_failure_still_raises_cancel(self) -> None:
        """If event_port.emit fails, PlanCancelledError still raised."""
        event_port = FakeEventPort(fail=True)
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_delta_port_failure_still_raises_cancel(self) -> None:
        """If delta_port.emit fails, PlanCancelledError still raised."""
        delta_port = FakeDeltaPort(fail=True)
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_both_ports_fail_still_raises_cancel(self) -> None:
        """Both ports failing still raises PlanCancelledError."""
        event_port = FakeEventPort(fail=True)
        delta_port = FakeDeltaPort(fail=True)
        ctrl = _make_controller(
            event_port=event_port,
            delta_port=delta_port,
        )
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    async def test_event_port_failure_delta_still_emitted(self) -> None:
        """If event_port fails, delta_port still receives the delta."""
        event_port = FakeEventPort(fail=True)
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(
            event_port=event_port,
            delta_port=delta_port,
        )
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert len(cancelled_deltas) == 1

    @pytest.mark.asyncio
    async def test_delta_port_failure_event_still_emitted(self) -> None:
        """If delta_port fails, event_port still receives the event."""
        event_port = FakeEventPort()
        delta_port = FakeDeltaPort(fail=True)
        ctrl = _make_controller(
            event_port=event_port,
            delta_port=delta_port,
        )
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), _always_cancel)
        cancelled = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1


# ===========================================================================
# 8. Edge case: no current_request
# ===========================================================================


class TestCancelNoCurrentRequest:
    """Edge case: _check_cancel when _current_request is None."""

    def test_cancel_with_no_request_uses_empty_strings(self) -> None:
        """If _current_request is None, request_id and trace_id are empty."""
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        ctrl.reset()
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        # Leave _current_request as None
        with pytest.raises(PlanCancelledError) as exc_info:
            ctrl._check_cancel(_always_cancel, StagePhase.SKETCH.value)
        assert exc_info.value.request_id == ""
        assert exc_info.value.trace_id == ""

    def test_cancel_with_no_request_event_uses_unknown(self) -> None:
        """Event payload uses 'unknown' for request_id when None."""
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        ctrl.reset()
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlanCancelledError):
            ctrl._check_cancel(_always_cancel, StagePhase.SKETCH.value)
        cancelled = [p for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert cancelled[0].request_id == "unknown"
        assert cancelled[0].trace_id == "unknown"

    def test_cancel_with_no_request_delta_uses_unknown_trace(self) -> None:
        """Delta uses 'unknown' for trace_id when None."""
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        ctrl.reset()
        ctrl._plan_start_time = 0.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        with pytest.raises(PlanCancelledError):
            ctrl._check_cancel(_always_cancel, StagePhase.SKETCH.value)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert cancelled_deltas[0].trace_id == "unknown"
        assert cancelled_deltas[0].data["request_id"] == ""


# ===========================================================================
# 9. FSM state sequence on cancel
# ===========================================================================


class TestFSMStateSequenceOnCancel:
    """Verify FSM transition sequence ends correctly on cancel."""

    @pytest.mark.asyncio
    async def test_cancel_after_sketch_fsm_sequence(self) -> None:
        """FSM: IDLE->SKETCHING->CANCELLED."""
        delta_port = FakeDeltaPort()
        cancel = CancelAfterN(0)
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        transitions = [d for d in delta_port.emitted if d.delta_type == DELTA_STAGE_TRANSITION]
        states = [(t.data["from_state"], t.data["to_state"]) for t in transitions]
        assert states == [
            (PlanState.IDLE.value, PlanState.SKETCHING.value),
            (PlanState.SKETCHING.value, PlanState.CANCELLED.value),
        ]

    @pytest.mark.asyncio
    async def test_cancel_after_expand_fsm_sequence(self) -> None:
        """FSM: IDLE->SKETCHING->EXPANDING->CANCELLED."""
        delta_port = FakeDeltaPort()
        cancel = CancelAfterN(1)
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        transitions = [d for d in delta_port.emitted if d.delta_type == DELTA_STAGE_TRANSITION]
        states = [(t.data["from_state"], t.data["to_state"]) for t in transitions]
        assert states == [
            (PlanState.IDLE.value, PlanState.SKETCHING.value),
            (PlanState.SKETCHING.value, PlanState.EXPANDING.value),
            (PlanState.EXPANDING.value, PlanState.CANCELLED.value),
        ]

    @pytest.mark.asyncio
    async def test_cancel_after_validate_fsm_sequence(self) -> None:
        """FSM: IDLE->SKETCHING->EXPANDING->VALIDATING->CANCELLED."""
        delta_port = FakeDeltaPort()
        cancel = CancelAfterN(2)
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        transitions = [d for d in delta_port.emitted if d.delta_type == DELTA_STAGE_TRANSITION]
        states = [(t.data["from_state"], t.data["to_state"]) for t in transitions]
        assert states == [
            (PlanState.IDLE.value, PlanState.SKETCHING.value),
            (PlanState.SKETCHING.value, PlanState.EXPANDING.value),
            (PlanState.EXPANDING.value, PlanState.VALIDATING.value),
            (PlanState.VALIDATING.value, PlanState.CANCELLED.value),
        ]


# ===========================================================================
# 10. Exactly one cancelled event per cancel
# ===========================================================================


class TestSingleCancelledEventEmission:
    """Verify exactly one plan.cancelled.v1 event and delta per cancel."""

    @pytest.mark.asyncio
    async def test_single_cancelled_event_at_checkpoint_2(self) -> None:
        event_port = FakeEventPort()
        cancel = CancelAfterN(0)
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1

    @pytest.mark.asyncio
    async def test_single_cancelled_delta_at_checkpoint_3(self) -> None:
        delta_port = FakeDeltaPort()
        cancel = CancelAfterN(1)
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert len(cancelled_deltas) == 1

    @pytest.mark.asyncio
    async def test_single_cancelled_event_at_checkpoint_4(self) -> None:
        event_port = FakeEventPort()
        cancel = CancelAfterN(2)
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1


# ===========================================================================
# 11. DELTA_PLAN_CANCELLED constant validation
# ===========================================================================


class TestDeltaPlanCancelledConstant:
    """Validate DELTA_PLAN_CANCELLED constant is valid for DeltaPayload."""

    def test_constant_value(self) -> None:
        assert DELTA_PLAN_CANCELLED == "plan_cancelled"

    def test_can_create_delta_payload_with_plan_cancelled_type(self) -> None:
        """DeltaPayload accepts plan_cancelled as a valid delta_type."""
        delta = DeltaPayload(
            agent_id=PLANNER_AGENT_ID,
            delta_type=DELTA_PLAN_CANCELLED,
            section=SECTION_PIPELINE,
            data={"request_id": "r1", "reason": "test"},
            trace_id="t1",
        )
        assert delta.delta_type == DELTA_PLAN_CANCELLED


# ===========================================================================
# 12. execute() exception handler preserves cancel path
# ===========================================================================


class TestExecuteExceptionHandlerPreservesCancel:
    """Verify PLAN-12 except clause re-raises PlanCancelledError without
    emitting plan.failed.v1."""

    @pytest.mark.asyncio
    async def test_cancel_not_caught_by_plan12(self) -> None:
        """PlanCancelledError bubbles up without plan.failed.v1."""
        event_port = FakeEventPort()
        cancel = CancelAfterN(0)
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        # No plan.failed.v1 should be emitted
        failed = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed) == 0

    @pytest.mark.asyncio
    async def test_cancel_error_propagates_stage(self) -> None:
        """PlanCancelledError retains correct stage attribute."""
        cancel = CancelAfterN(1)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(FakePlanRequest(), cancel)
        assert exc_info.value.stage == StagePhase.EXPAND.value

    @pytest.mark.asyncio
    async def test_cancel_error_propagates_request_id(self) -> None:
        cancel = CancelAfterN(0)
        ctrl = _make_controller()
        req = FakePlanRequest(request_id="req-propagate")
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(req, cancel)
        assert exc_info.value.request_id == "req-propagate"

    @pytest.mark.asyncio
    async def test_cancel_error_propagates_trace_id(self) -> None:
        cancel = CancelAfterN(0)
        ctrl = _make_controller()
        req = FakePlanRequest(trace_id="trace-propagate")
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(req, cancel)
        assert exc_info.value.trace_id == "trace-propagate"


# ===========================================================================
# 13. Checkpoint count per pipeline path
# ===========================================================================


class TestCheckpointCount:
    """Verify the number of cancel checks in different pipeline paths."""

    @pytest.mark.asyncio
    async def test_happy_path_has_3_cancel_checks(self) -> None:
        """Full pipeline: 3 checkpoints (after SKETCH, EXPAND, VALIDATE)."""
        call_count = 0

        def counting_cancel() -> bool:
            nonlocal call_count
            call_count += 1
            return False

        ctrl = _make_controller()
        await ctrl.execute(FakePlanRequest(), counting_cancel)
        # Checkpoints: after SKETCH, after EXPAND, after VALIDATE
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_revise_path_has_extra_checks(self) -> None:
        """Revise loop adds 2 extra checkpoints (EXPAND+VALIDATE loop)."""
        call_count = 0

        def counting_cancel() -> bool:
            nonlocal call_count
            call_count += 1
            return False

        validate = FakeValidateService(
            verdicts=[
                _make_verdict(VERDICT_REVISE),
                _make_verdict(VERDICT_APPROVED),
            ],
        )
        ctrl = _make_controller(validate=validate)
        await ctrl.execute(FakePlanRequest(), counting_cancel)
        # Checkpoints: after SKETCH(1), after EXPAND(2), after 2nd EXPAND(3),
        # after 2nd VALIDATE(4)
        # Wait - let me trace through:
        # 1st iteration: SKETCH -> check(1) -> EXPAND -> check(2) -> VALIDATE(revise)
        # -> re-loop: EXPAND -> check(3) -> VALIDATE(approved) -> check(4) -> COMMIT
        assert call_count == 4


# ===========================================================================
# 14. Cancel at each stage enum value (parametrized)
# ===========================================================================


class TestCancelAtEachCheckpoint:
    """Parametrized tests for cancel at each of the 3 PipelineController
    checkpoints."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cancel_after_n,expected_stage",
        [
            (0, StagePhase.SKETCH.value),
            (1, StagePhase.EXPAND.value),
            (2, StagePhase.VALIDATE.value),
        ],
        ids=["after_SKETCH", "after_EXPAND", "after_VALIDATE"],
    )
    async def test_cancel_stage_matches(
        self,
        cancel_after_n: int,
        expected_stage: str,
    ) -> None:
        cancel = CancelAfterN(cancel_after_n)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError) as exc_info:
            await ctrl.execute(FakePlanRequest(), cancel)
        assert exc_info.value.stage == expected_stage

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cancel_after_n",
        [0, 1, 2],
        ids=["checkpoint_2", "checkpoint_3", "checkpoint_4"],
    )
    async def test_fsm_cancelled_at_each_checkpoint(
        self,
        cancel_after_n: int,
    ) -> None:
        cancel = CancelAfterN(cancel_after_n)
        ctrl = _make_controller()
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        assert ctrl.current_state == PlanState.CANCELLED

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cancel_after_n",
        [0, 1, 2],
        ids=["checkpoint_2", "checkpoint_3", "checkpoint_4"],
    )
    async def test_cancelled_event_emitted_at_each_checkpoint(
        self,
        cancel_after_n: int,
    ) -> None:
        cancel = CancelAfterN(cancel_after_n)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cancel_after_n",
        [0, 1, 2],
        ids=["checkpoint_2", "checkpoint_3", "checkpoint_4"],
    )
    async def test_cancelled_delta_emitted_at_each_checkpoint(
        self,
        cancel_after_n: int,
    ) -> None:
        cancel = CancelAfterN(cancel_after_n)
        delta_port = FakeDeltaPort()
        ctrl = _make_controller(delta_port=delta_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        cancelled_deltas = [d for d in delta_port.emitted if d.delta_type == DELTA_PLAN_CANCELLED]
        assert len(cancelled_deltas) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cancel_after_n",
        [0, 1, 2],
        ids=["checkpoint_2", "checkpoint_3", "checkpoint_4"],
    )
    async def test_no_plan_failed_at_any_checkpoint(
        self,
        cancel_after_n: int,
    ) -> None:
        cancel = CancelAfterN(cancel_after_n)
        event_port = FakeEventPort()
        ctrl = _make_controller(event_port=event_port)
        with pytest.raises(PlanCancelledError):
            await ctrl.execute(FakePlanRequest(), cancel)
        failed = [(t, p) for t, p in event_port.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed) == 0
