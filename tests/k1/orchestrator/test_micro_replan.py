"""
Tests for MicroReplanCheckpoint (Issue 3.2.5 / ORCH-13).

Test classes:
  TestExtractDiscoveries            -- _extract_discoveries() unit tests.
  TestCheckParamOverlap             -- _check_param_overlap() heuristic tests.
  TestMicroReplanInit               -- Constructor, reset, properties.
  TestMicroReplanNoDiscoveries      -- No discoveries -> CONTINUE.
  TestMicroReplanNoRemaining        -- No remaining steps -> CONTINUE.
  TestMicroReplanNoOverlap          -- Discoveries but no overlap -> CONTINUE.
  TestMicroReplanBudgetExhausted    -- Max replans reached -> CONTINUE.
  TestMicroReplanSuccess            -- Planner returns plan -> CONTINUE+metadata.
  TestMicroReplanPlannerNone        -- Planner returns None -> CONTINUE.
  TestMicroReplanTimeout            -- Planner times out -> CONTINUE.
  TestMicroReplanPlannerError       -- Planner raises -> CONTINUE.
  TestMicroReplanMultiWave          -- Accumulation across waves.
  TestMicroReplanDiscoveryParsing   -- Edge cases in discovery extraction.
  TestMicroReplanOverlapHeuristic   -- Substring/exact match combinations.
  TestMicroReplanRepr               -- __repr__ coverage.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.types import CapabilityResult
from k1.orchestrator.orchestration.guards import DAGGuard, MicroReplanCheckpoint
from k1.orchestrator.orchestration.guards.micro_replan import (
    _check_param_overlap,
    _extract_discoveries,
)
from k1.orchestrator.types import (
    CommittedPlan,
    Discovery,
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

# ===========================================================================
# Fake Planner
# ===========================================================================


class FakePlanner:
    """Configurable stand-in for IPlannerPort in guard tests."""

    def __init__(
        self,
        return_plan: Optional[CommittedPlan] = None,
        raise_exc: Optional[Exception] = None,
        delay_s: float = 0.0,
    ) -> None:
        self.return_plan = return_plan
        self.raise_exc = raise_exc
        self.delay_s = delay_s
        self.call_count = 0
        self.last_request: Optional[MicroReplanRequest] = None

    async def micro_replan(self, request: MicroReplanRequest) -> Optional[CommittedPlan]:
        self.call_count += 1
        self.last_request = request
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        if self.raise_exc:
            raise self.raise_exc
        return self.return_plan

    async def request_plan(self, request: PlanRequest) -> PlanAck:
        """Stub -- not used by MicroReplanCheckpoint."""
        return PlanAck(request_id=request.request_id, status="ACCEPTED")

    async def cancel_plan(self, request_id: str) -> None:
        """Stub -- not used by MicroReplanCheckpoint."""


# ===========================================================================
# Helpers
# ===========================================================================


def _make_step(
    step_id: str = "s1",
    capability: str = "cap.test",
    params: Optional[Dict[str, Any]] = None,
) -> PlanStep:
    """Create a minimal PlanStep."""
    return PlanStep(
        id=step_id,
        capability=capability,
        params=params or {"key": "val"},
        deps=[],
    )


def _make_cap_result(
    data: Optional[Dict[str, Any]] = None,
    success: bool = True,
) -> CapabilityResult:
    """Create a CapabilityResult."""
    return CapabilityResult(
        request_id="req-1",
        trace_id="t1",
        success=success,
        data=data,
        provider_id="test-provider",
        duration_ms=10,
    )


def _make_step_result(
    step_id: str = "s1",
    capability: str = "cap.test",
    status: StepStatus = StepStatus.COMPLETED,
    data: Optional[Dict[str, Any]] = None,
) -> StepResult:
    """Create a StepResult wrapping a CapabilityResult."""
    cap_result = None
    if data is not None or status == StepStatus.COMPLETED:
        cap_result = _make_cap_result(data=data, success=(status == StepStatus.COMPLETED))
    return StepResult(
        step_id=step_id,
        capability_name=capability,
        status=status,
        duration_ms=10,
        result=cap_result,
    )


def _make_wave_result(
    step_results: Optional[List[StepResult]] = None,
    wave_index: int = 0,
) -> WaveResult:
    """Create a WaveResult."""
    return WaveResult(
        wave_index=wave_index,
        step_results=step_results or [_make_step_result()],
        duration_ms=10,
    )


def _make_ctx(
    trace_id: str = "trace-1",
    dag_id: str = "dag-1",
) -> ProcessingContext:
    """Create a minimal ProcessingContext."""
    return ProcessingContext(
        trace_id=trace_id,
        request_id="req-1",
        tier="standard",
        dag_id=dag_id,
    )


def _make_committed_plan(
    plan_id: str = "plan-new",
    steps: Optional[List[PlanStep]] = None,
) -> CommittedPlan:
    """Create a CommittedPlan for micro-replan results."""
    s = steps or [_make_step("new-s1", "cap.new", {"x": 1})]
    return CommittedPlan(
        plan_id=plan_id,
        request_id="req-1",
        intent="replanned",
        steps=s,
        trace_id="trace-1",
    )


def _discovery_data(
    field_name: str = "has_room",
    value: Any = True,
    source_step_id: str = "s1",
) -> Dict[str, Any]:
    """Build a discovery dict for embedding in CapabilityResult.data."""
    return {"field": field_name, "value": value, "source_step_id": source_step_id}


def _make_step_result_with_discoveries(
    step_id: str = "s1",
    discoveries: Optional[List[Dict[str, Any]]] = None,
) -> StepResult:
    """Create a StepResult whose CapabilityResult.data has discoveries."""
    disc = discoveries or [_discovery_data()]
    data = {"output": "ok", "discoveries": disc}
    return _make_step_result(step_id=step_id, data=data)


# ===========================================================================
# TestExtractDiscoveries -- _extract_discoveries() unit tests
# ===========================================================================


class TestExtractDiscoveries:
    """Unit tests for _extract_discoveries helper."""

    def test_empty_wave_result(self) -> None:
        wr = WaveResult(wave_index=0, step_results=[], duration_ms=0)
        assert _extract_discoveries(wr) == []

    def test_no_result_on_step(self) -> None:
        sr = StepResult(
            step_id="s1",
            capability_name="c",
            status=StepStatus.FAILED,
            duration_ms=0,
            result=None,
        )
        wr = _make_wave_result(step_results=[sr])
        assert _extract_discoveries(wr) == []

    def test_no_data_on_result(self) -> None:
        sr = _make_step_result(data=None)
        wr = _make_wave_result(step_results=[sr])
        # CapabilityResult exists but data is None
        # Actually for COMPLETED + data=None, our helper creates cap_result with data=None
        assert _extract_discoveries(wr) == []

    def test_no_discoveries_key(self) -> None:
        sr = _make_step_result(data={"output": "ok"})
        wr = _make_wave_result(step_results=[sr])
        assert _extract_discoveries(wr) == []

    def test_discoveries_not_list(self) -> None:
        sr = _make_step_result(data={"discoveries": "not-a-list"})
        wr = _make_wave_result(step_results=[sr])
        assert _extract_discoveries(wr) == []

    def test_single_discovery(self) -> None:
        sr = _make_step_result_with_discoveries(
            discoveries=[_discovery_data("venue_type", "indoor", "s1")]
        )
        wr = _make_wave_result(step_results=[sr])
        result = _extract_discoveries(wr)
        assert len(result) == 1
        assert result[0].field == "venue_type"
        assert result[0].value == "indoor"
        assert result[0].source_step_id == "s1"

    def test_multiple_discoveries_same_step(self) -> None:
        sr = _make_step_result_with_discoveries(
            discoveries=[
                _discovery_data("f1", "v1", "s1"),
                _discovery_data("f2", "v2", "s1"),
            ]
        )
        wr = _make_wave_result(step_results=[sr])
        result = _extract_discoveries(wr)
        assert len(result) == 2
        assert {d.field for d in result} == {"f1", "f2"}

    def test_discoveries_across_steps(self) -> None:
        sr1 = _make_step_result_with_discoveries(
            step_id="s1",
            discoveries=[_discovery_data("f1", "v1", "s1")],
        )
        sr2 = _make_step_result_with_discoveries(
            step_id="s2",
            discoveries=[_discovery_data("f2", "v2", "s2")],
        )
        wr = _make_wave_result(step_results=[sr1, sr2])
        result = _extract_discoveries(wr)
        assert len(result) == 2

    def test_discovery_missing_field_key(self) -> None:
        sr = _make_step_result(data={"discoveries": [{"value": 42}]})
        wr = _make_wave_result(step_results=[sr])
        assert _extract_discoveries(wr) == []

    def test_discovery_empty_field(self) -> None:
        sr = _make_step_result(data={"discoveries": [{"field": "", "value": 42}]})
        wr = _make_wave_result(step_results=[sr])
        assert _extract_discoveries(wr) == []

    def test_discovery_not_dict(self) -> None:
        sr = _make_step_result(data={"discoveries": ["not-a-dict", 42]})
        wr = _make_wave_result(step_results=[sr])
        assert _extract_discoveries(wr) == []

    def test_discovery_defaults_source_step_id_to_step(self) -> None:
        """If discovery dict lacks source_step_id, use the step's ID."""
        sr = _make_step_result(
            step_id="alpha",
            data={"discoveries": [{"field": "x"}]},
        )
        wr = _make_wave_result(step_results=[sr])
        result = _extract_discoveries(wr)
        assert len(result) == 1
        assert result[0].source_step_id == "alpha"

    def test_discovery_field_coerced_to_str(self) -> None:
        sr = _make_step_result(data={"discoveries": [{"field": 123, "value": "v"}]})
        wr = _make_wave_result(step_results=[sr])
        result = _extract_discoveries(wr)
        assert result[0].field == "123"

    def test_mixed_valid_invalid_discoveries(self) -> None:
        sr = _make_step_result(
            data={
                "discoveries": [
                    {"field": "valid", "value": 1},
                    "bad",
                    {"no_field": True},
                    {"field": "also_valid"},
                ]
            }
        )
        wr = _make_wave_result(step_results=[sr])
        result = _extract_discoveries(wr)
        assert len(result) == 2
        assert result[0].field == "valid"
        assert result[1].field == "also_valid"


# ===========================================================================
# TestCheckParamOverlap -- _check_param_overlap() tests
# ===========================================================================


class TestCheckParamOverlap:
    """Unit tests for _check_param_overlap heuristic."""

    def test_empty_discoveries(self) -> None:
        steps = [_make_step(params={"venue_type": "x"})]
        assert _check_param_overlap([], steps) is False

    def test_empty_remaining_steps(self) -> None:
        disc = [Discovery(field="venue_type")]
        assert _check_param_overlap(disc, []) is False

    def test_exact_match(self) -> None:
        disc = [Discovery(field="venue_type")]
        steps = [_make_step(params={"venue_type": "indoor"})]
        assert _check_param_overlap(disc, steps) is True

    def test_no_match(self) -> None:
        disc = [Discovery(field="weather")]
        steps = [_make_step(params={"venue_type": "indoor"})]
        assert _check_param_overlap(disc, steps) is False

    def test_case_insensitive(self) -> None:
        disc = [Discovery(field="Venue_Type")]
        steps = [_make_step(params={"venue_type": "indoor"})]
        assert _check_param_overlap(disc, steps) is True

    def test_substring_field_in_param(self) -> None:
        disc = [Discovery(field="venue")]
        steps = [_make_step(params={"venue_type": "indoor"})]
        assert _check_param_overlap(disc, steps) is True

    def test_substring_param_in_field(self) -> None:
        disc = [Discovery(field="preferred_venue_type_override")]
        steps = [_make_step(params={"venue": "x"})]
        assert _check_param_overlap(disc, steps) is True

    def test_multiple_steps_overlap_in_second(self) -> None:
        disc = [Discovery(field="budget")]
        steps = [
            _make_step("s1", params={"name": "x"}),
            _make_step("s2", params={"budget": 100}),
        ]
        assert _check_param_overlap(disc, steps) is True

    def test_multiple_discoveries_one_matches(self) -> None:
        disc = [
            Discovery(field="weather"),
            Discovery(field="budget"),
        ]
        steps = [_make_step(params={"budget": 100})]
        assert _check_param_overlap(disc, steps) is True

    def test_no_params_in_step(self) -> None:
        disc = [Discovery(field="venue")]
        steps = [_make_step(params={})]
        assert _check_param_overlap(disc, steps) is False

    def test_overlap_across_multiple_steps(self) -> None:
        disc = [Discovery(field="size")]
        steps = [
            _make_step("s1", params={"color": "red"}),
            _make_step("s2", params={"font_size": 12}),
        ]
        # "size" is substring of "font_size"
        assert _check_param_overlap(disc, steps) is True


# ===========================================================================
# TestMicroReplanInit -- constructor, reset, properties
# ===========================================================================


class TestMicroReplanInit:
    """Constructor, reset, and property tests."""

    def test_default_max_replans(self) -> None:
        guard = MicroReplanCheckpoint(planner=FakePlanner())
        assert guard._max_replans == 1
        assert guard.replans_used == 0

    def test_custom_max_replans(self) -> None:
        guard = MicroReplanCheckpoint(planner=FakePlanner(), max_replans=3)
        assert guard._max_replans == 3

    def test_is_dag_guard(self) -> None:
        guard = MicroReplanCheckpoint(planner=FakePlanner())
        assert isinstance(guard, DAGGuard)

    def test_reset_clears_state(self) -> None:
        guard = MicroReplanCheckpoint(planner=FakePlanner())
        guard._replans_used = 2
        guard._completed_results = {"s1": _make_step_result()}
        guard.reset()
        assert guard.replans_used == 0
        assert guard._completed_results == {}

    def test_replans_used_property(self) -> None:
        guard = MicroReplanCheckpoint(planner=FakePlanner())
        assert guard.replans_used == 0
        guard._replans_used = 1
        assert guard.replans_used == 1


# ===========================================================================
# TestMicroReplanNoDiscoveries -- CONTINUE when no discoveries
# ===========================================================================


class TestMicroReplanNoDiscoveries:
    """No discoveries in wave -> CONTINUE without calling planner."""

    @pytest.mark.asyncio
    async def test_no_discoveries_returns_continue(self) -> None:
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner)
        wr = _make_wave_result(step_results=[_make_step_result(data={"output": "ok"})])
        ctx = _make_ctx()
        remaining = [_make_step("s2", params={"budget": 100})]

        decision = await guard.after_wave(wr, ctx, remaining_steps=remaining, plan_id="p1")

        assert decision.action == GuardAction.CONTINUE
        assert "No discoveries" in decision.reason
        assert planner.call_count == 0

    @pytest.mark.asyncio
    async def test_no_data_at_all(self) -> None:
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner)
        sr = StepResult(
            step_id="s1",
            capability_name="c",
            status=StepStatus.COMPLETED,
            duration_ms=10,
            result=_make_cap_result(data=None),
        )
        wr = _make_wave_result(step_results=[sr])
        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.CONTINUE
        assert planner.call_count == 0


# ===========================================================================
# TestMicroReplanNoRemaining -- CONTINUE when remaining_steps missing
# ===========================================================================


class TestMicroReplanNoRemaining:
    """Discoveries found but no remaining steps -> CONTINUE."""

    @pytest.mark.asyncio
    async def test_remaining_steps_none(self) -> None:
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner)
        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=None)
        assert decision.action == GuardAction.CONTINUE
        assert "No remaining" in decision.reason
        assert planner.call_count == 0

    @pytest.mark.asyncio
    async def test_remaining_steps_empty(self) -> None:
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner)
        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=[])
        assert decision.action == GuardAction.CONTINUE
        assert "No remaining" in decision.reason

    @pytest.mark.asyncio
    async def test_remaining_steps_non_planstep_filtered(self) -> None:
        """Non-PlanStep objects in remaining_steps are filtered out."""
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner)
        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        # Pass non-PlanStep items
        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=["not-a-step", 42])
        assert decision.action == GuardAction.CONTINUE
        assert "No remaining" in decision.reason


# ===========================================================================
# TestMicroReplanNoOverlap -- CONTINUE when no param overlap
# ===========================================================================


class TestMicroReplanNoOverlap:
    """Discoveries present but no overlap with remaining step params."""

    @pytest.mark.asyncio
    async def test_no_overlap(self) -> None:
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner)
        wr = _make_wave_result(
            step_results=[
                _make_step_result_with_discoveries(
                    discoveries=[_discovery_data("weather", "sunny")],
                )
            ]
        )
        remaining = [_make_step("s2", params={"budget": 100})]
        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining)
        assert decision.action == GuardAction.CONTINUE
        assert "No param overlap" in decision.reason
        assert planner.call_count == 0


# ===========================================================================
# TestMicroReplanBudgetExhausted -- max_replans reached
# ===========================================================================


class TestMicroReplanBudgetExhausted:
    """Budget exhausted -> CONTINUE without calling planner."""

    @pytest.mark.asyncio
    async def test_budget_exhausted_default(self) -> None:
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner)
        guard._replans_used = 1  # Already used the single allowed replan

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]
        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining)
        assert decision.action == GuardAction.CONTINUE
        assert "budget exhausted" in decision.reason.lower()
        assert planner.call_count == 0

    @pytest.mark.asyncio
    async def test_budget_exhausted_custom(self) -> None:
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner, max_replans=3)
        guard._replans_used = 3

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]
        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining)
        assert decision.action == GuardAction.CONTINUE
        assert "budget exhausted" in decision.reason.lower()
        assert "3/3" in decision.reason


# ===========================================================================
# TestMicroReplanSuccess -- planner returns CommittedPlan
# ===========================================================================


class TestMicroReplanSuccess:
    """Planner returns a new CommittedPlan -> CONTINUE with metadata."""

    @pytest.mark.asyncio
    async def test_success_returns_new_plan_in_metadata(self) -> None:
        new_plan = _make_committed_plan()
        planner = FakePlanner(return_plan=new_plan)
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]
        ctx = _make_ctx()

        decision = await guard.after_wave(wr, ctx, remaining_steps=remaining, plan_id="p1")

        assert decision.action == GuardAction.CONTINUE
        assert "new_plan" in decision.metadata
        assert decision.metadata["new_plan"] is new_plan
        assert guard.replans_used == 1

    @pytest.mark.asyncio
    async def test_success_increments_replans_used(self) -> None:
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner, max_replans=3)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert guard.replans_used == 1

    @pytest.mark.asyncio
    async def test_planner_receives_correct_request(self) -> None:
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        disc_data = _discovery_data("has_room", True, "s1")
        sr = _make_step_result_with_discoveries(step_id="s1", discoveries=[disc_data])
        wr = _make_wave_result(step_results=[sr])
        remaining = [_make_step("s2", params={"has_room": True})]
        ctx = _make_ctx(trace_id="t-42", dag_id="dag-42")

        await guard.after_wave(wr, ctx, remaining_steps=remaining, plan_id="orig-plan")

        req = planner.last_request
        assert req is not None
        assert req.original_plan_id == "orig-plan"
        assert req.trace_id == "t-42"
        assert len(req.discoveries) == 1
        assert req.discoveries[0].field == "has_room"
        assert len(req.remaining_steps) == 1
        assert req.remaining_steps[0].id == "s2"
        assert "s1" in req.completed_results

    @pytest.mark.asyncio
    async def test_plan_id_fallback_to_dag_id(self) -> None:
        """When plan_id is None, uses ctx.dag_id as fallback."""
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]
        ctx = _make_ctx(dag_id="fallback-dag")

        await guard.after_wave(wr, ctx, remaining_steps=remaining, plan_id=None)

        assert planner.last_request is not None
        assert planner.last_request.original_plan_id == "fallback-dag"

    @pytest.mark.asyncio
    async def test_guard_name_in_decision(self) -> None:
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert decision.guard_name == "MicroReplanCheckpoint"

    @pytest.mark.asyncio
    async def test_reason_includes_step_count(self) -> None:
        new_steps = [
            _make_step("x1", "cap.a"),
            _make_step("x2", "cap.b"),
        ]
        planner = FakePlanner(return_plan=_make_committed_plan(steps=new_steps))
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]
        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert "2 new steps" in decision.reason


# ===========================================================================
# TestMicroReplanPlannerNone -- planner returns None
# ===========================================================================


class TestMicroReplanPlannerNone:
    """Planner returns None -> CONTINUE gracefully."""

    @pytest.mark.asyncio
    async def test_planner_none_returns_continue(self) -> None:
        planner = FakePlanner(return_plan=None)
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")

        assert decision.action == GuardAction.CONTINUE
        assert "None" in decision.reason
        assert "new_plan" not in decision.metadata
        assert guard.replans_used == 0

    @pytest.mark.asyncio
    async def test_planner_none_does_not_exhaust_budget(self) -> None:
        planner = FakePlanner(return_plan=None)
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert guard.replans_used == 0


# ===========================================================================
# TestMicroReplanTimeout -- planner exceeds 10s timeout
# ===========================================================================


class TestMicroReplanTimeout:
    """Planner micro_replan exceeds timeout -> CONTINUE gracefully."""

    @pytest.mark.asyncio
    async def test_timeout_returns_continue(self) -> None:
        # Use a very short timeout override for test speed
        planner = FakePlanner(delay_s=0.2)
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        # Patch the timeout to something small for testing
        import k1.orchestrator.orchestration.guards.micro_replan as mod

        original_timeout = mod._MICRO_REPLAN_TIMEOUT_S
        mod._MICRO_REPLAN_TIMEOUT_S = 0.05
        try:
            decision = await guard.after_wave(
                wr, _make_ctx(), remaining_steps=remaining, plan_id="p1"
            )
        finally:
            mod._MICRO_REPLAN_TIMEOUT_S = original_timeout

        assert decision.action == GuardAction.CONTINUE
        assert "timed out" in decision.reason.lower()
        assert guard.replans_used == 0

    @pytest.mark.asyncio
    async def test_timeout_does_not_exhaust_budget(self) -> None:
        planner = FakePlanner(delay_s=0.2)
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        import k1.orchestrator.orchestration.guards.micro_replan as mod

        original_timeout = mod._MICRO_REPLAN_TIMEOUT_S
        mod._MICRO_REPLAN_TIMEOUT_S = 0.05
        try:
            await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        finally:
            mod._MICRO_REPLAN_TIMEOUT_S = original_timeout

        assert guard.replans_used == 0


# ===========================================================================
# TestMicroReplanPlannerError -- planner raises exception
# ===========================================================================


class TestMicroReplanPlannerError:
    """Planner raises exception -> CONTINUE gracefully."""

    @pytest.mark.asyncio
    async def test_exception_returns_continue(self) -> None:
        planner = FakePlanner(raise_exc=RuntimeError("planner down"))
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")

        assert decision.action == GuardAction.CONTINUE
        assert "failed" in decision.reason.lower()
        assert guard.replans_used == 0

    @pytest.mark.asyncio
    async def test_value_error_returns_continue(self) -> None:
        planner = FakePlanner(raise_exc=ValueError("bad request"))
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert decision.action == GuardAction.CONTINUE
        assert "bad request" in decision.reason


# ===========================================================================
# TestMicroReplanMultiWave -- accumulation across waves
# ===========================================================================


class TestMicroReplanMultiWave:
    """Verify state accumulation across multiple after_wave calls."""

    @pytest.mark.asyncio
    async def test_completed_results_accumulate(self) -> None:
        """Step results from prior waves are included in request."""
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        # Wave 0: no discoveries -> no planner call
        wr0 = _make_wave_result(
            step_results=[_make_step_result(step_id="s1", data={"output": "wave0"})],
            wave_index=0,
        )
        remaining0 = [
            _make_step("s2", params={"has_room": True}),
            _make_step("s3", params={"size": 10}),
        ]
        d0 = await guard.after_wave(wr0, _make_ctx(), remaining_steps=remaining0, plan_id="p1")
        assert d0.action == GuardAction.CONTINUE
        assert planner.call_count == 0

        # Wave 1: has discovery that overlaps s3 params
        wr1 = _make_wave_result(
            step_results=[
                _make_step_result_with_discoveries(
                    step_id="s2",
                    discoveries=[_discovery_data("size", 20, "s2")],
                )
            ],
            wave_index=1,
        )
        remaining1 = [_make_step("s3", params={"size": 10})]
        d1 = await guard.after_wave(wr1, _make_ctx(), remaining_steps=remaining1, plan_id="p1")

        assert d1.action == GuardAction.CONTINUE
        assert "new_plan" in d1.metadata
        assert planner.call_count == 1

        # Verify accumulated results include both waves
        req = planner.last_request
        assert req is not None
        assert "s1" in req.completed_results
        assert "s2" in req.completed_results

    @pytest.mark.asyncio
    async def test_second_replan_blocked_by_budget(self) -> None:
        """After one successful replan, budget blocks second attempt."""
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        # Wave 0: trigger replan
        wr0 = _make_wave_result(step_results=[_make_step_result_with_discoveries(step_id="s1")])
        remaining0 = [_make_step("s2", params={"has_room": True})]
        await guard.after_wave(wr0, _make_ctx(), remaining_steps=remaining0, plan_id="p1")
        assert guard.replans_used == 1
        assert planner.call_count == 1

        # Wave 1: another trigger, but budget exhausted
        wr1 = _make_wave_result(step_results=[_make_step_result_with_discoveries(step_id="s2")])
        remaining1 = [_make_step("s3", params={"has_room": True})]
        d1 = await guard.after_wave(wr1, _make_ctx(), remaining_steps=remaining1, plan_id="p1")
        assert d1.action == GuardAction.CONTINUE
        assert "budget exhausted" in d1.reason.lower()
        assert planner.call_count == 1  # Not called again

    @pytest.mark.asyncio
    async def test_reset_allows_replan_in_new_dag(self) -> None:
        """After reset, replan budget is restored."""
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        wr = _make_wave_result(step_results=[_make_step_result_with_discoveries()])
        remaining = [_make_step("s2", params={"has_room": True})]

        # First DAG: use replan
        await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert guard.replans_used == 1

        # Reset for new DAG
        guard.reset()
        assert guard.replans_used == 0
        assert guard._completed_results == {}

        # Second DAG: replan works again
        await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p2")
        assert guard.replans_used == 1
        assert planner.call_count == 2


# ===========================================================================
# TestMicroReplanDiscoveryParsing -- edge cases
# ===========================================================================


class TestMicroReplanDiscoveryParsing:
    """Edge cases in discovery extraction within the guard flow."""

    @pytest.mark.asyncio
    async def test_discovery_with_none_value(self) -> None:
        """Discovery with value=None still triggers overlap check."""
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        sr = _make_step_result(
            step_id="s1",
            data={"discoveries": [{"field": "has_room", "value": None}]},
        )
        wr = _make_wave_result(step_results=[sr])
        remaining = [_make_step("s2", params={"has_room": True})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert decision.action == GuardAction.CONTINUE
        assert "new_plan" in decision.metadata

    @pytest.mark.asyncio
    async def test_discovery_numeric_field(self) -> None:
        """Discovery field is numeric (coerced to string)."""
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        sr = _make_step_result(
            step_id="s1",
            data={"discoveries": [{"field": 42, "value": "x"}]},
        )
        wr = _make_wave_result(step_results=[sr])
        remaining = [_make_step("s2", params={"42": "val"})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert planner.call_count == 1
        assert "new_plan" in decision.metadata

    @pytest.mark.asyncio
    async def test_multiple_discoveries_only_one_overlaps(self) -> None:
        """One of multiple discoveries overlaps -> triggers replan."""
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        sr = _make_step_result(
            step_id="s1",
            data={
                "discoveries": [
                    {"field": "weather", "value": "sunny"},
                    {"field": "budget", "value": 500},
                ]
            },
        )
        wr = _make_wave_result(step_results=[sr])
        remaining = [_make_step("s2", params={"budget": 100})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert "new_plan" in decision.metadata

        # Both discoveries should be in the request
        req = planner.last_request
        assert req is not None
        assert len(req.discoveries) == 2


# ===========================================================================
# TestMicroReplanOverlapHeuristic -- substring/exact match in guard flow
# ===========================================================================


class TestMicroReplanOverlapHeuristic:
    """Overlap heuristic tested end-to-end within the guard."""

    @pytest.mark.asyncio
    async def test_exact_match_triggers_replan(self) -> None:
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        sr = _make_step_result_with_discoveries(
            discoveries=[_discovery_data("venue_type", "outdoor")]
        )
        wr = _make_wave_result(step_results=[sr])
        remaining = [_make_step("s2", params={"venue_type": "indoor"})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert "new_plan" in decision.metadata

    @pytest.mark.asyncio
    async def test_substring_match_triggers_replan(self) -> None:
        planner = FakePlanner(return_plan=_make_committed_plan())
        guard = MicroReplanCheckpoint(planner=planner)

        sr = _make_step_result_with_discoveries(discoveries=[_discovery_data("venue", "park")])
        wr = _make_wave_result(step_results=[sr])
        remaining = [_make_step("s2", params={"preferred_venue_option": "x"})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert "new_plan" in decision.metadata

    @pytest.mark.asyncio
    async def test_no_match_does_not_trigger(self) -> None:
        planner = FakePlanner()
        guard = MicroReplanCheckpoint(planner=planner)

        sr = _make_step_result_with_discoveries(discoveries=[_discovery_data("temperature", 72)])
        wr = _make_wave_result(step_results=[sr])
        remaining = [_make_step("s2", params={"budget": 100})]

        decision = await guard.after_wave(wr, _make_ctx(), remaining_steps=remaining, plan_id="p1")
        assert "new_plan" not in decision.metadata
        assert planner.call_count == 0


# ===========================================================================
# TestMicroReplanRepr -- __repr__ coverage
# ===========================================================================


class TestMicroReplanRepr:
    """__repr__ coverage."""

    def test_repr_default(self) -> None:
        guard = MicroReplanCheckpoint(planner=FakePlanner())
        r = repr(guard)
        assert "MicroReplanCheckpoint" in r
        assert "max_replans=1" in r
        assert "replans_used=0" in r

    def test_repr_after_replan(self) -> None:
        guard = MicroReplanCheckpoint(planner=FakePlanner(), max_replans=3)
        guard._replans_used = 2
        r = repr(guard)
        assert "max_replans=3" in r
        assert "replans_used=2" in r
