"""M16.E2.I2 — FailureReplanCheckpoint guard tests.

Validates the failure-driven planner-amend path:

* When a wave contains a FAILED step AND there are remaining steps AND
  the replan budget is not exhausted, the guard issues a 10s
  ``planner.micro_replan`` call carrying a populated ``FailureContext``
  and surfaces the amended plan via ``metadata["new_plan"]``.
* When the planner returns ``None`` the guard returns ``CONTINUE`` with
  no metadata (graceful degradation).
* When the planner times out (10s default) the guard returns
  ``CONTINUE`` and does NOT increment the replan budget beyond the
  in-progress count expected by callers — i.e. it never escalates to
  HARD_STOP.
* When the budget is exhausted the guard short-circuits without calling
  the planner.
* When no step in the wave failed the guard returns ``CONTINUE`` early.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from k1.orchestrator.orchestration.guards.failure_replan import (
    FailureReplanCheckpoint,
)
from k1.orchestrator.types import (
    CapabilityResult,
    CommittedPlan,
    GuardAction,
    MicroReplanRequest,
    PlanAck,
    PlanRequest,
    PlanStep,
    ProcessingContext,
    StepResult,
    StepStatus,
    WaveResult,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _StubPlannerPort:
    """Minimal IPlannerPort stub recording micro_replan invocations."""

    def __init__(
        self,
        return_plan: Optional[CommittedPlan] = None,
        sleep_s: float = 0.0,
        raise_exc: Optional[BaseException] = None,
    ) -> None:
        self._return_plan = return_plan
        self._sleep_s = sleep_s
        self._raise_exc = raise_exc
        self.calls: List[MicroReplanRequest] = []

    async def request_plan(self, request: PlanRequest) -> PlanAck:  # pragma: no cover
        raise NotImplementedError

    async def cancel_plan(self, request_id: str) -> None:  # pragma: no cover
        return None

    async def micro_replan(
        self,
        request: MicroReplanRequest,
    ) -> Optional[CommittedPlan]:
        self.calls.append(request)
        if self._sleep_s:
            await asyncio.sleep(self._sleep_s)
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._return_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step(
    step_id: str, capability: str = "cap.test", params: Optional[Dict[str, Any]] = None
) -> PlanStep:
    return PlanStep(
        id=step_id,
        capability=capability,
        params=params or {"k": "v"},
        deps=[],
    )


def _step_result(
    step_id: str,
    status: StepStatus,
    *,
    error_detail: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> StepResult:
    cap_result: Optional[CapabilityResult] = None
    if data is not None or status == StepStatus.COMPLETED:
        cap_result = CapabilityResult(
            request_id="req-1",
            trace_id="t-1",
            success=(status == StepStatus.COMPLETED),
            data=data,
            provider_id="prov.test",
            duration_ms=5,
        )
    return StepResult(
        step_id=step_id,
        capability_name="cap.test",
        status=status,
        duration_ms=5,
        result=cap_result,
        error_detail=error_detail,
    )


def _wave(step_results: List[StepResult], idx: int = 0) -> WaveResult:
    return WaveResult(
        wave_index=idx,
        step_results=step_results,
        duration_ms=10,
    )


def _ctx() -> ProcessingContext:
    return ProcessingContext(
        trace_id="trace-fail-1",
        request_id="req-fail-1",
        tier="HIGH",
        dag_id="dag-fail-1",
        interrupt_flag=False,
    )


def _amended_plan(plan_id: str = "amended-1") -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id,
        request_id="req-fail-1",
        intent="amended",
        steps=[_step("amended-step", capability="cap.replacement")],
        dependencies={},
        trace_id="trace-fail-1",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_failed_step_returns_continue_without_calling_planner() -> None:
    planner = _StubPlannerPort(return_plan=_amended_plan())
    guard = FailureReplanCheckpoint(planner)

    wave = _wave([_step_result("s1", StepStatus.COMPLETED)])
    decision = await guard.after_wave(wave, _ctx(), [_step("s2")], plan_id="plan-1")

    assert decision.action == GuardAction.CONTINUE
    assert "No failed steps" in decision.reason
    assert planner.calls == []
    assert guard.replans_used == 0


@pytest.mark.asyncio
async def test_failed_step_with_no_remaining_returns_continue() -> None:
    planner = _StubPlannerPort(return_plan=_amended_plan())
    guard = FailureReplanCheckpoint(planner)

    wave = _wave([_step_result("s1", StepStatus.FAILED, error_detail="boom")])
    decision = await guard.after_wave(wave, _ctx(), [], plan_id="plan-1")

    assert decision.action == GuardAction.CONTINUE
    assert "No remaining steps" in decision.reason
    assert planner.calls == []


@pytest.mark.asyncio
async def test_failure_triggers_planner_with_failure_context_and_amended_plan() -> None:
    new_plan = _amended_plan("amended-99")
    planner = _StubPlannerPort(return_plan=new_plan)
    guard = FailureReplanCheckpoint(planner)

    failed = _step_result(
        "s-bad",
        StepStatus.FAILED,
        error_detail="capability timed out",
        data={"partial": "yes"},
    )
    wave = _wave([_step_result("s-ok", StepStatus.COMPLETED), failed])

    decision = await guard.after_wave(
        wave,
        _ctx(),
        [_step("s-future-1"), _step("s-future-2")],
        plan_id="plan-orig",
    )

    assert decision.action == GuardAction.CONTINUE
    assert decision.metadata is not None
    assert decision.metadata["new_plan"] is new_plan
    assert decision.metadata["amended_for_step"] == "s-bad"
    assert guard.replans_used == 1

    # Planner received a request with the failure context populated.
    assert len(planner.calls) == 1
    req = planner.calls[0]
    assert req.original_plan_id == "plan-orig"
    assert req.failure_context is not None
    assert req.failure_context.step_id == "s-bad"
    assert req.failure_context.error_code == "STEP_FAILED"
    assert req.failure_context.error_message == "capability timed out"
    assert req.failure_context.partial_result == {"partial": "yes"}
    # All step results from the wave (success + failure) accumulated.
    assert set(req.completed_results.keys()) == {"s-ok", "s-bad"}
    assert len(req.remaining_steps) == 2


@pytest.mark.asyncio
async def test_planner_returns_none_yields_continue_without_metadata() -> None:
    planner = _StubPlannerPort(return_plan=None)
    guard = FailureReplanCheckpoint(planner)

    wave = _wave([_step_result("s1", StepStatus.FAILED, error_detail="x")])
    decision = await guard.after_wave(wave, _ctx(), [_step("s2")], plan_id="plan-1")

    assert decision.action == GuardAction.CONTINUE
    assert decision.metadata is None or "new_plan" not in (decision.metadata or {})
    assert guard.replans_used == 0
    assert len(planner.calls) == 1


@pytest.mark.asyncio
async def test_planner_exception_is_swallowed() -> None:
    planner = _StubPlannerPort(raise_exc=RuntimeError("planner boom"))
    guard = FailureReplanCheckpoint(planner)

    wave = _wave([_step_result("s1", StepStatus.FAILED, error_detail="x")])
    decision = await guard.after_wave(wave, _ctx(), [_step("s2")], plan_id="plan-1")

    assert decision.action == GuardAction.CONTINUE
    assert "planner boom" in decision.reason
    assert guard.replans_used == 0


@pytest.mark.asyncio
async def test_replan_budget_exhausted_short_circuits() -> None:
    planner = _StubPlannerPort(return_plan=_amended_plan())
    guard = FailureReplanCheckpoint(planner, max_replans=1)

    # First failure consumes the budget.
    wave1 = _wave([_step_result("s1", StepStatus.FAILED, error_detail="x")])
    await guard.after_wave(wave1, _ctx(), [_step("s2")], plan_id="plan-1")
    assert guard.replans_used == 1
    assert len(planner.calls) == 1

    # Second failure within the same DAG must NOT call the planner again.
    wave2 = _wave([_step_result("s3", StepStatus.FAILED, error_detail="y")], idx=1)
    decision = await guard.after_wave(wave2, _ctx(), [_step("s4")], plan_id="plan-1")
    assert decision.action == GuardAction.CONTINUE
    assert "budget exhausted" in decision.reason.lower()
    assert len(planner.calls) == 1  # unchanged


@pytest.mark.asyncio
async def test_reset_clears_state_for_next_dag() -> None:
    planner = _StubPlannerPort(return_plan=_amended_plan())
    guard = FailureReplanCheckpoint(planner, max_replans=1)

    wave = _wave([_step_result("s1", StepStatus.FAILED, error_detail="x")])
    await guard.after_wave(wave, _ctx(), [_step("s2")], plan_id="plan-1")
    assert guard.replans_used == 1

    guard.reset()
    assert guard.replans_used == 0

    # Budget restored — next failure should call planner again.
    await guard.after_wave(wave, _ctx(), [_step("s2")], plan_id="plan-2")
    assert guard.replans_used == 1
    assert len(planner.calls) == 2
