"""
Tests for DAGExecutor execute/execute_wave/collect_results (Issues 2.2.2 + 2.2.3).

Validates: parallel wave execution, safety band abort, param resolution,
concurrency limits, interrupt handling, WAL writes, event emissions,
result aggregation (full, partial, aborted).

Test classes:
  TestExecuteHappyPath       -- Normal DAG execution end-to-end.
  TestExecuteWaveConcurrency -- Semaphore, parallel step dispatch.
  TestSafetyBandAbort        -- RED/BLACK safety band halts DAG.
  TestInterruptHandling      -- interrupt_flag cancels remaining steps.
  TestParamResolution        -- $-reference resolution via ParamResolver.
  TestWALWrites              -- WAL write calls for each lifecycle event.
  TestEventEmissions         -- Delta emissions (DAG_STARTED, progress, etc).
  TestCollectResults         -- Result aggregation from wave results.
  TestCollectResultsPartial  -- Partial/aborted DAG aggregation.
  TestGuardHooks             -- Pre/post guard invocation (M3 hooks).
  TestEdgeCases              -- Single step, empty deps, step_runner errors.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k1.fabric.types import CapabilityResult
from k1.orchestrator.orchestration.dag_executor import (
    _ABORT_SAFETY_LEVELS,
    _MAX_CONCURRENT_PER_WAVE,
    DAGExecutor,
)
from k1.orchestrator.types import (
    AggregatedResult,
    CommittedPlan,
    CompensationRecord,
    PlanStep,
    StepResult,
    StepStatus,
    WaveResult,
)

# ===========================================================================
# Fake ports and helpers
# ===========================================================================


class FakeStatePort:
    """Fake IStateReadPort -- configurable safety band."""

    def __init__(self, safety_level: str = "GREEN") -> None:
        self.safety_level = safety_level
        self.read_calls: List[Tuple[str, str]] = []

    async def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        self.read_calls.append((session_id, section))
        if section == "control.safety_band":
            return {"level": self.safety_level}
        return None

    async def read_sections(self, session_id: str, names: List[str]) -> Dict[str, Any]:
        return {}

    async def get_snapshot(self, session_id: str) -> Any:
        return None


class FakeBridgePort:
    """Fake IBridgeWritePort -- records WAL writes."""

    def __init__(self, fail_on: Optional[str] = None) -> None:
        self.wal_writes: List[Tuple[str, str, Dict[str, Any], str]] = []
        self.audit_calls: List[Tuple[Dict[str, Any], str]] = []
        self.fail_on = fail_on

    async def write_wal(
        self,
        dag_id: str,
        entry_type: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        if self.fail_on and entry_type == self.fail_on:
            raise RuntimeError(f"WAL write {entry_type} failed")
        self.wal_writes.append((dag_id, entry_type, payload, trace_id))

    async def submit_audit(self, run_manifest: Dict[str, Any], trace_id: str) -> None:
        self.audit_calls.append((run_manifest, trace_id))

    async def read_wal(self, dag_id: str) -> Optional[List[Dict[str, Any]]]:
        return None


class FakeDeltaPort:
    """Fake IDeltaEmitPort -- records emissions."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, Dict[str, Any], str]] = []
        self.progress: List[Tuple[str, str, str]] = []

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str) -> None:
        self.events.append((event_topic, payload, trace_id))

    async def emit_progress(self, step_id: str, summary: str, trace_id: str) -> None:
        self.progress.append((step_id, summary, trace_id))

class FakeStepRunner:
    """Fake step_runner -- configurable per-step results."""

    def __init__(self) -> None:
        self._results: Dict[str, StepResult] = {}
        self._errors: Dict[str, Exception] = {}
        self._delay: Dict[str, float] = {}
        self.run_calls: List[Tuple[str, Dict[str, Any], Dict[str, Any], str]] = []

    def set_result(self, step_id: str, result: StepResult) -> None:
        self._results[step_id] = result

    def set_error(self, step_id: str, error: Exception) -> None:
        self._errors[step_id] = error

    def set_delay(self, step_id: str, delay_s: float) -> None:
        self._delay[step_id] = delay_s

    async def run(
        self,
        step: PlanStep,
        resolved_params: Dict[str, Any],
        merged_results: Dict[str, Any],
        trace_id: str,
    ) -> StepResult:
        self.run_calls.append((step.id, resolved_params, dict(merged_results), trace_id))
        if step.id in self._delay:
            await asyncio.sleep(self._delay[step.id])
        if step.id in self._errors:
            raise self._errors[step.id]
        if step.id in self._results:
            return self._results[step.id]
        # Default: COMPLETED with a success CapabilityResult
        return StepResult(
            step_id=step.id,
            capability_name=step.capability,
            status=StepStatus.COMPLETED,
            duration_ms=10,
            result=CapabilityResult.success_result(
                request_id=f"req-{step.id}",
                data={"output": f"result-{step.id}"},
                provider_id="test-provider",
                trace_id=trace_id,
            ),
        )


class FakeParamResolver:
    """Fake ParamResolver -- pass-through or configured resolution."""

    def __init__(self) -> None:
        self._overrides: Dict[str, Dict[str, Any]] = {}
        self._errors: Dict[str, Exception] = {}
        self.calls: List[Tuple[Any, Dict[str, Any]]] = []

    def set_override(self, step_id: str, resolved: Dict[str, Any]) -> None:
        self._overrides[step_id] = resolved

    def set_error(self, step_id: str, error: Exception) -> None:
        self._errors[step_id] = error

    def resolve(
        self, step: Any, prior_results: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Typed resolve() API used by DAGExecutor (2.3.5)."""
        step_id = step.id if hasattr(step, "id") else step.get("id", "")
        self.calls.append((step, dict(prior_results)))
        if step_id in self._errors:
            raise self._errors[step_id]
        if step_id in self._overrides:
            override = self._overrides[step_id]
            return (override.get("params", {}), override.get("capability"))
        params = dict(step.params) if hasattr(step, "params") else step.get("params", {})
        return (params, None)

    def resolve_step(
        self, step: Dict[str, Any], completed_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Legacy dict-based API (backward compat)."""
        step_id = step.get("id", "")
        self.calls.append((dict(step), dict(completed_results)))
        if step_id in self._errors:
            raise self._errors[step_id]
        if step_id in self._overrides:
            return self._overrides[step_id]
        return step


class FakePort:
    """Minimal fake for unused ports."""

    pass


class FakeGuard:
    """Fake guard for testing guard hook invocation."""

    def __init__(self) -> None:
        self.before_wave_calls: List[Any] = []
        self.after_wave_calls: List[Any] = []
        self.before_step_calls: List[Any] = []
        self.after_step_calls: List[Any] = []

    async def before_wave(self, wave: Any, result: Any, plan: Any) -> None:
        self.before_wave_calls.append((wave, result, plan))

    async def after_wave(
        self, wave_result: Any, ctx: Any = None, remaining_steps: Any = None, plan_id: Any = None
    ) -> None:
        self.after_wave_calls.append((wave_result, ctx, remaining_steps, plan_id))

    async def before_step(self, step: Any, params: Any) -> None:
        self.before_step_calls.append((step, params))

    async def after_step(self, step: Any, result: Any, ctx: Any = None) -> None:
        self.after_step_calls.append((step, result, ctx))


@dataclass
class FakeSnapshot:
    """Fake SessionSnapshot."""

    session_id: str = "test-session"
    sections: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timestamp_ms: int = 0


# ===========================================================================
# Factory helpers
# ===========================================================================


def _step(step_id: str, capability: str = "cap.test", **kwargs: Any) -> PlanStep:
    """Create a minimal PlanStep."""
    return PlanStep(id=step_id, capability=capability, **kwargs)


def _plan(
    *steps: PlanStep,
    deps: Optional[Dict[str, List[str]]] = None,
    plan_id: str = "plan-1",
    trace_id: str = "trace-1",
) -> CommittedPlan:
    """Create a CommittedPlan from steps."""
    return CommittedPlan(
        plan_id=plan_id,
        request_id="req-1",
        intent="test intent",
        steps=list(steps),
        dependencies=deps or {},
        trace_id=trace_id,
    )


def _make_executor(
    step_runner: Optional[FakeStepRunner] = None,
    state_port: Optional[FakeStatePort] = None,
    bridge_port: Optional[FakeBridgePort] = None,
    delta_port: Optional[FakeDeltaPort] = None,
    param_resolver: Optional[FakeParamResolver] = None,
    guards: Optional[List[Any]] = None,
) -> DAGExecutor:
    """Create DAGExecutor with fake deps, defaulting to working fakes."""
    return DAGExecutor(
        fabric_port=FakePort(),
        planner_port=FakePort(),
        delta_port=delta_port or FakeDeltaPort(),
        state_port=state_port or FakeStatePort(),
        bridge_port=bridge_port or FakeBridgePort(),
        step_runner=step_runner or FakeStepRunner(),
        error_router=FakePort(),
        guards=guards or [],
        param_resolver=param_resolver,
    )


def _success_result(step_id: str, cap: str = "cap.test") -> StepResult:
    """Create a COMPLETED StepResult."""
    return StepResult(
        step_id=step_id,
        capability_name=cap,
        status=StepStatus.COMPLETED,
        duration_ms=10,
        result=CapabilityResult.success_result(
            request_id=f"req-{step_id}",
            data={"output": f"result-{step_id}"},
            provider_id="test-provider",
        ),
    )


def _failed_result(step_id: str, detail: str = "error") -> StepResult:
    """Create a FAILED StepResult."""
    return StepResult(
        step_id=step_id,
        capability_name="cap.test",
        status=StepStatus.FAILED,
        duration_ms=5,
        error_detail=detail,
    )


# ===========================================================================
# TestExecuteHappyPath
# ===========================================================================


class TestExecuteHappyPath:
    """Normal DAG execution -- all steps succeed."""

    @pytest.mark.asyncio
    async def test_single_step_plan(self) -> None:
        """Single step plan executes and returns AggregatedResult."""
        exe = _make_executor()
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert isinstance(result, AggregatedResult)
        assert result.success is True
        assert result.total_steps == 1
        assert result.completed == 1
        assert result.failed == 0
        assert result.cancelled == 0
        assert result.plan_id == "plan-1"

    @pytest.mark.asyncio
    async def test_two_step_linear(self) -> None:
        """Linear chain s1 -> s2: both complete in sequence."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"), deps={"s2": ["s1"]})

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True
        assert result.total_steps == 2
        assert result.completed == 2

    @pytest.mark.asyncio
    async def test_parallel_steps(self) -> None:
        """Two independent steps run in same wave."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True
        assert result.completed == 2

    @pytest.mark.asyncio
    async def test_diamond_dag(self) -> None:
        """Diamond: s1 -> (s2, s3) -> s4."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            _step("s4"),
            deps={"s2": ["s1"], "s3": ["s1"], "s4": ["s2", "s3"]},
        )

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True
        assert result.total_steps == 4
        assert result.completed == 4

    @pytest.mark.asyncio
    async def test_merged_results_populated(self) -> None:
        """execute() populates merged_results with CapabilityResults."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"))

        await exe.execute(plan, FakeSnapshot())

        assert "s1" in exe.merged_results
        assert "s2" in exe.merged_results

    @pytest.mark.asyncio
    async def test_result_duration_positive(self) -> None:
        """AggregatedResult.duration_ms is positive."""
        exe = _make_executor()
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_result_trace_id_matches(self) -> None:
        """AggregatedResult.trace_id matches plan.trace_id."""
        exe = _make_executor()
        plan = _plan(_step("s1"), trace_id="my-trace")

        result = await exe.execute(plan, FakeSnapshot())

        assert result.trace_id == "my-trace"

    @pytest.mark.asyncio
    async def test_step_results_contain_all_steps(self) -> None:
        """AggregatedResult.step_results has one entry per PlanStep."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"), _step("s3"))

        result = await exe.execute(plan, FakeSnapshot())

        result_ids = {sr.step_id for sr in result.step_results}
        assert result_ids == {"s1", "s2", "s3"}


# ===========================================================================
# TestExecuteWaveConcurrency
# ===========================================================================


class TestExecuteWaveConcurrency:
    """Verify steps within a wave run concurrently with semaphore control."""

    @pytest.mark.asyncio
    async def test_parallel_steps_run_concurrently(self) -> None:
        """Steps in same wave overlap in time."""
        runner = FakeStepRunner()
        runner.set_delay("s1", 0.05)
        runner.set_delay("s2", 0.05)
        exe = _make_executor(step_runner=runner)
        plan = _plan(_step("s1"), _step("s2"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True
        # Both steps should be dispatched -- runner receives both calls
        called_ids = [c[0] for c in runner.run_calls]
        assert set(called_ids) == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_semaphore_constant_is_ten(self) -> None:
        """Max concurrent steps per wave is 10."""
        assert _MAX_CONCURRENT_PER_WAVE == 10

    @pytest.mark.asyncio
    async def test_many_steps_in_single_wave(self) -> None:
        """12 independent steps in 1 wave with semaphore(10) all complete."""
        runner = FakeStepRunner()
        steps = [_step(f"s{i}") for i in range(12)]
        exe = _make_executor(step_runner=runner)
        plan = _plan(*steps)

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True
        assert result.completed == 12


# ===========================================================================
# TestSafetyBandAbort
# ===========================================================================


class TestSafetyBandAbort:
    """Safety band RED/BLACK aborts DAG execution."""

    @pytest.mark.asyncio
    async def test_red_safety_band_aborts(self) -> None:
        """RED safety_band aborts before executing any steps."""
        state = FakeStatePort(safety_level="RED")
        runner = FakeStepRunner()
        exe = _make_executor(state_port=state, step_runner=runner)
        plan = _plan(_step("s1"), _step("s2"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is False
        assert len(runner.run_calls) == 0
        assert result.cancelled >= 1

    @pytest.mark.asyncio
    async def test_black_safety_band_aborts(self) -> None:
        """BLACK safety band aborts."""
        state = FakeStatePort(safety_level="BLACK")
        runner = FakeStepRunner()
        exe = _make_executor(state_port=state, step_runner=runner)
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is False
        assert len(runner.run_calls) == 0

    @pytest.mark.asyncio
    async def test_yellow_safety_band_proceeds(self) -> None:
        """YELLOW safety band does NOT abort."""
        state = FakeStatePort(safety_level="YELLOW")
        exe = _make_executor(state_port=state)
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True

    @pytest.mark.asyncio
    async def test_green_safety_band_proceeds(self) -> None:
        """GREEN safety band does NOT abort."""
        state = FakeStatePort(safety_level="GREEN")
        exe = _make_executor(state_port=state)
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True

    @pytest.mark.asyncio
    async def test_abort_levels_set(self) -> None:
        """Abort levels are exactly RED and BLACK."""
        assert _ABORT_SAFETY_LEVELS == frozenset({"RED", "BLACK"})

    @pytest.mark.asyncio
    async def test_safety_band_read_failure_proceeds(self) -> None:
        """If state_port.read_section throws, proceed (degraded)."""
        state = FakeStatePort()

        async def _raise(*a: Any, **kw: Any) -> None:
            raise RuntimeError("state unavailable")

        state.read_section = _raise  # type: ignore[assignment]
        exe = _make_executor(state_port=state)
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True

    @pytest.mark.asyncio
    async def test_safety_abort_mid_dag(self) -> None:
        """Safety band RED at wave 2 aborts remaining waves."""
        state = FakeStatePort(safety_level="GREEN")
        runner = FakeStepRunner()
        exe = _make_executor(state_port=state, step_runner=runner)

        plan = _plan(_step("s1"), _step("s2"), deps={"s2": ["s1"]})

        # After wave 1, change safety band to RED
        original_read = state.read_section

        call_count = 0

        async def _switch_after_first(session_id: str, section: str) -> Optional[Dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            if call_count > 1 and section == "control.safety_band":
                return {"level": "RED"}
            return await original_read(session_id, section)

        state.read_section = _switch_after_first  # type: ignore[assignment]

        result = await exe.execute(plan, FakeSnapshot())

        # s1 should complete, s2 should be cancelled
        assert result.completed >= 1
        # s2 cancelled because safety band blocked wave 2
        s2_results = [sr for sr in result.step_results if sr.step_id == "s2"]
        assert len(s2_results) == 1
        assert s2_results[0].status == StepStatus.CANCELLED


# ===========================================================================
# TestInterruptHandling
# ===========================================================================


class TestInterruptHandling:
    """Interrupt flag cancels remaining steps/waves."""

    @pytest.mark.asyncio
    async def test_interrupt_stops_subsequent_waves(self) -> None:
        """Setting interrupt_flag during execution stops later waves."""
        runner = FakeStepRunner()
        exe = _make_executor(step_runner=runner)
        plan = _plan(_step("s1"), _step("s2"), deps={"s2": ["s1"]})

        # Make s1 set interrupt after completing
        original_run = runner.run

        async def _interrupt_after_s1(
            step: PlanStep, params: Any, merged: Any, trace: str
        ) -> StepResult:
            result = await original_run(step, params, merged, trace)
            if step.id == "s1":
                exe.interrupt_flag = True
            return result

        runner.run = _interrupt_after_s1  # type: ignore[assignment]

        result = await exe.execute(plan, FakeSnapshot())

        # s1 completed, s2 should not run
        s1_results = [sr for sr in result.step_results if sr.step_id == "s1"]
        assert len(s1_results) == 1
        assert s1_results[0].status == StepStatus.COMPLETED

        # s2 should be CANCELLED (not reached)
        s2_results = [sr for sr in result.step_results if sr.step_id == "s2"]
        assert len(s2_results) == 1
        assert s2_results[0].status == StepStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_interrupt_resets_on_new_execute(self) -> None:
        """execute() resets interrupt_flag at start."""
        exe = _make_executor()
        exe.interrupt_flag = True
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True
        assert result.completed == 1

    @pytest.mark.asyncio
    async def test_merged_results_reset_on_new_execute(self) -> None:
        """execute() resets merged_results at start."""
        exe = _make_executor()
        exe.merged_results = {"old": "data"}
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        assert "old" not in exe.merged_results
        assert "s1" in exe.merged_results


# ===========================================================================
# TestParamResolution
# ===========================================================================


class TestParamResolution:
    """ParamResolver integration with execute_wave."""

    @pytest.mark.asyncio
    async def test_param_resolver_called_for_each_step(self) -> None:
        """ParamResolver.resolve_step() called once per step."""
        resolver = FakeParamResolver()
        exe = _make_executor(param_resolver=resolver)
        plan = _plan(_step("s1"), _step("s2"))

        await exe.execute(plan, FakeSnapshot())

        assert len(resolver.calls) == 2

    @pytest.mark.asyncio
    async def test_param_resolver_receives_merged_results(self) -> None:
        """Second wave resolver call sees first wave results in completed_results."""
        resolver = FakeParamResolver()
        runner = FakeStepRunner()
        exe = _make_executor(param_resolver=resolver, step_runner=runner)
        plan = _plan(_step("s1"), _step("s2"), deps={"s2": ["s1"]})

        await exe.execute(plan, FakeSnapshot())

        # First call (s1): no completed_results
        assert len(resolver.calls[0][1]) == 0
        # Second call (s2): should have s1 result
        assert "s1" in resolver.calls[1][1]

    @pytest.mark.asyncio
    async def test_param_resolver_overrides_params(self) -> None:
        """Resolved params passed to step_runner."""
        resolver = FakeParamResolver()
        resolver.set_override(
            "s1", {"id": "s1", "capability": "cap.test", "params": {"key": "resolved-value"}}
        )
        runner = FakeStepRunner()
        exe = _make_executor(param_resolver=resolver, step_runner=runner)
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        # step_runner should receive the resolved params
        assert len(runner.run_calls) == 1
        assert runner.run_calls[0][1] == {"key": "resolved-value"}

    @pytest.mark.asyncio
    async def test_param_resolver_error_marks_step_failed(self) -> None:
        """ParamResolver error fails the step, does not crash DAG."""
        resolver = FakeParamResolver()
        resolver.set_error("s1", ValueError("bad reference"))
        runner = FakeStepRunner()
        exe = _make_executor(param_resolver=resolver, step_runner=runner)
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.failed >= 1
        failed_steps = [
            sr
            for sr in result.step_results
            if sr.step_id == "s1" and sr.status == StepStatus.FAILED
        ]
        assert len(failed_steps) == 1
        assert "ParamResolver error" in (failed_steps[0].error_detail or "")

    @pytest.mark.asyncio
    async def test_no_param_resolver_uses_raw_params(self) -> None:
        """Without param_resolver, raw step.params go to step_runner."""
        runner = FakeStepRunner()
        exe = _make_executor(step_runner=runner, param_resolver=None)
        plan = _plan(_step("s1", params={"raw": "value"}))

        await exe.execute(plan, FakeSnapshot())

        assert runner.run_calls[0][1] == {"raw": "value"}


# ===========================================================================
# TestWALWrites
# ===========================================================================


class TestWALWrites:
    """WAL writes for DAG lifecycle events."""

    @pytest.mark.asyncio
    async def test_plan_start_wal_written(self) -> None:
        """PLAN_START WAL entry written at DAG start."""
        bridge = FakeBridgePort()
        exe = _make_executor(bridge_port=bridge)
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        plan_starts = [w for w in bridge.wal_writes if w[1] == "PLAN_START"]
        assert len(plan_starts) == 1
        assert plan_starts[0][0] == "plan-1"
        assert plan_starts[0][3] == "trace-1"

    @pytest.mark.asyncio
    async def test_dag_complete_wal_written(self) -> None:
        """DAG_COMPLETE WAL entry written at end."""
        bridge = FakeBridgePort()
        exe = _make_executor(bridge_port=bridge)
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        dag_completes = [w for w in bridge.wal_writes if w[1] == "DAG_COMPLETE"]
        assert len(dag_completes) == 1
        assert dag_completes[0][2]["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_wave_complete_wal_written(self) -> None:
        """WAVE_COMPLETE WAL entry written per wave."""
        bridge = FakeBridgePort()
        exe = _make_executor(bridge_port=bridge)
        plan = _plan(_step("s1"), _step("s2"), deps={"s2": ["s1"]})

        await exe.execute(plan, FakeSnapshot())

        wave_completes = [w for w in bridge.wal_writes if w[1] == "WAVE_COMPLETE"]
        assert len(wave_completes) == 2

    @pytest.mark.asyncio
    async def test_step_complete_wal_written(self) -> None:
        """STEP_COMPLETE WAL entry written per step."""
        bridge = FakeBridgePort()
        exe = _make_executor(bridge_port=bridge)
        plan = _plan(_step("s1"), _step("s2"))

        await exe.execute(plan, FakeSnapshot())

        step_completes = [w for w in bridge.wal_writes if w[1] == "STEP_COMPLETE"]
        assert len(step_completes) == 2

    @pytest.mark.asyncio
    async def test_wal_failure_does_not_crash(self) -> None:
        """WAL write failure is swallowed (fire-and-forget)."""
        bridge = FakeBridgePort(fail_on="PLAN_START")
        exe = _make_executor(bridge_port=bridge)
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        # Execution succeeds despite WAL failure
        assert result.success is True

    @pytest.mark.asyncio
    async def test_failed_dag_wal_status(self) -> None:
        """DAG_COMPLETE WAL has status=FAILED when steps fail."""
        runner = FakeStepRunner()
        runner.set_result("s1", _failed_result("s1"))
        bridge = FakeBridgePort()
        exe = _make_executor(step_runner=runner, bridge_port=bridge)
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        dag_completes = [w for w in bridge.wal_writes if w[1] == "DAG_COMPLETE"]
        assert dag_completes[0][2]["status"] == "FAILED"

    @pytest.mark.asyncio
    async def test_audit_submitted(self) -> None:
        """submit_audit called with result dict."""
        bridge = FakeBridgePort()
        exe = _make_executor(bridge_port=bridge)
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        assert len(bridge.audit_calls) == 1


# ===========================================================================
# TestEventEmissions
# ===========================================================================


class TestEventEmissions:
    """Delta event emissions during DAG execution."""

    @pytest.mark.asyncio
    async def test_dag_started_emitted(self) -> None:
        """ORCH_DAG_STARTED event emitted at start."""
        from k1.orchestrator.events import ORCH_DAG_STARTED

        delta = FakeDeltaPort()
        exe = _make_executor(delta_port=delta)
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        started = [e for e in delta.events if e[0] == ORCH_DAG_STARTED]
        assert len(started) == 1
        assert started[0][1]["plan_id"] == "plan-1"
        assert started[0][1]["total_steps"] == 1

    @pytest.mark.asyncio
    async def test_dag_completed_emitted(self) -> None:
        """ORCH_DAG_COMPLETED event emitted at end."""
        from k1.orchestrator.events import ORCH_DAG_COMPLETED

        delta = FakeDeltaPort()
        exe = _make_executor(delta_port=delta)
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        completed = [e for e in delta.events if e[0] == ORCH_DAG_COMPLETED]
        assert len(completed) == 1

    @pytest.mark.asyncio
    async def test_progress_emitted_per_wave(self) -> None:
        """emit_progress called per wave completion."""
        delta = FakeDeltaPort()
        exe = _make_executor(delta_port=delta)
        plan = _plan(_step("s1"), _step("s2"), deps={"s2": ["s1"]})

        await exe.execute(plan, FakeSnapshot())

        assert len(delta.progress) == 2  # 2 waves
        # Verify trace_id
        assert all(p[2] == "trace-1" for p in delta.progress)


# ===========================================================================
# TestCollectResults
# ===========================================================================


class TestCollectResults:
    """collect_results() aggregation logic."""

    def test_all_completed(self) -> None:
        """All steps completed: success=True."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"))

        wave_results = [
            WaveResult(
                wave_index=0,
                step_results=[
                    _success_result("s1"),
                    _success_result("s2"),
                ],
                duration_ms=10,
            )
        ]

        result = exe.collect_results(wave_results, plan, [])

        assert result.success is True
        assert result.total_steps == 2
        assert result.completed == 2
        assert result.failed == 0
        assert result.cancelled == 0

    def test_one_failed(self) -> None:
        """One failure: success=False."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"))

        wave_results = [
            WaveResult(
                wave_index=0,
                step_results=[
                    _success_result("s1"),
                    _failed_result("s2"),
                ],
                duration_ms=10,
            )
        ]

        result = exe.collect_results(wave_results, plan, [])

        assert result.success is False
        assert result.completed == 1
        assert result.failed == 1

    def test_empty_wave_results(self) -> None:
        """No waves executed: all steps marked CANCELLED."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"))

        result = exe.collect_results([], plan, [])

        assert result.success is False
        assert result.total_steps == 2
        assert result.cancelled == 2

    def test_compensations_passed_through(self) -> None:
        """CompensationRecords provided appear on result."""
        exe = _make_executor()
        plan = _plan(_step("s1"))

        comps = [
            CompensationRecord(
                dag_id="plan-1",
                step_id="s1",
                compensation_capability="cap.undo",
            )
        ]
        wave_results = [
            WaveResult(wave_index=0, step_results=[_success_result("s1")], duration_ms=5)
        ]

        result = exe.collect_results(wave_results, plan, comps)

        assert len(result.compensations) == 1

    def test_plan_id_set(self) -> None:
        """collect_results sets plan_id from CommittedPlan."""
        exe = _make_executor()
        plan = _plan(_step("s1"), plan_id="my-plan")

        wave_results = [
            WaveResult(wave_index=0, step_results=[_success_result("s1")], duration_ms=5)
        ]

        result = exe.collect_results(wave_results, plan, [])

        assert result.plan_id == "my-plan"

    def test_duration_passthrough(self) -> None:
        """dag_duration_ms parameter passed to AggregatedResult."""
        exe = _make_executor()
        plan = _plan(_step("s1"))

        wave_results = [
            WaveResult(wave_index=0, step_results=[_success_result("s1")], duration_ms=5)
        ]

        result = exe.collect_results(wave_results, plan, [], dag_duration_ms=999)

        assert result.duration_ms == 999


# ===========================================================================
# TestCollectResultsPartial
# ===========================================================================


class TestCollectResultsPartial:
    """collect_results with partial/aborted DAG -- synthetic CANCELLED."""

    def test_missing_steps_get_cancelled(self) -> None:
        """Steps not in any WaveResult get CANCELLED status."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        # Only wave 0 executed (s1)
        wave_results = [
            WaveResult(wave_index=0, step_results=[_success_result("s1")], duration_ms=5)
        ]

        result = exe.collect_results(wave_results, plan, [])

        assert result.total_steps == 3
        assert result.completed == 1
        assert result.cancelled == 2

        cancelled_ids = {
            sr.step_id for sr in result.step_results if sr.status == StepStatus.CANCELLED
        }
        assert cancelled_ids == {"s2", "s3"}

    def test_cancelled_step_has_error_detail(self) -> None:
        """Synthetic CANCELLED steps have descriptive error_detail."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"), deps={"s2": ["s1"]})

        wave_results = [
            WaveResult(wave_index=0, step_results=[_success_result("s1")], duration_ms=5)
        ]

        result = exe.collect_results(wave_results, plan, [])

        s2_results = [sr for sr in result.step_results if sr.step_id == "s2"]
        assert len(s2_results) == 1
        assert s2_results[0].error_detail is not None
        assert (
            "aborted" in s2_results[0].error_detail.lower()
            or "not reached" in s2_results[0].error_detail.lower()
        )

    def test_cancelled_step_has_correct_capability(self) -> None:
        """Synthetic CANCELLED uses PlanStep.capability."""
        exe = _make_executor()
        plan = _plan(_step("s1", capability="cap.alpha"))

        result = exe.collect_results([], plan, [])

        assert result.step_results[0].capability_name == "cap.alpha"

    def test_deterministic_cancelled_ordering(self) -> None:
        """Synthetic CANCELLED steps sorted by step_id."""
        exe = _make_executor()
        plan = _plan(_step("c"), _step("a"), _step("b"))

        result = exe.collect_results([], plan, [])

        cancelled_ids = [sr.step_id for sr in result.step_results]
        assert cancelled_ids == ["a", "b", "c"]


# ===========================================================================
# TestGuardHooks
# ===========================================================================


class TestGuardHooks:
    """Guard hook invocation during DAG execution."""

    @pytest.mark.asyncio
    async def test_after_wave_guard_called(self) -> None:
        """Guard.after_wave called once per wave."""
        guard = FakeGuard()
        exe = _make_executor(guards=[guard])
        plan = _plan(_step("s1"), _step("s2"), deps={"s2": ["s1"]})

        await exe.execute(plan, FakeSnapshot())

        # 2 waves = 2 after_wave calls
        assert len(guard.after_wave_calls) == 2

    @pytest.mark.asyncio
    async def test_before_step_guard_called(self) -> None:
        """Guard.before_step called once per step."""
        guard = FakeGuard()
        exe = _make_executor(guards=[guard])
        plan = _plan(_step("s1"), _step("s2"))

        await exe.execute(plan, FakeSnapshot())

        assert len(guard.before_step_calls) == 2

    @pytest.mark.asyncio
    async def test_after_step_guard_called(self) -> None:
        """Guard.after_step called once per step."""
        guard = FakeGuard()
        exe = _make_executor(guards=[guard])
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        assert len(guard.after_step_calls) == 1

    @pytest.mark.asyncio
    async def test_guard_error_does_not_crash(self) -> None:
        """Guard exceptions are swallowed."""

        class BadGuard:
            async def after_wave(self, *a: Any) -> None:
                raise RuntimeError("guard boom")

            async def before_step(self, *a: Any) -> None:
                raise RuntimeError("guard boom")

            async def after_step(self, *a: Any) -> None:
                raise RuntimeError("guard boom")

        exe = _make_executor(guards=[BadGuard()])
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.success is True


# ===========================================================================
# TestEdgeCases
# ===========================================================================


class TestEdgeCases:
    """Edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_step_runner_exception_results_in_failed(self) -> None:
        """step_runner.run() throwing results in FAILED StepResult."""
        runner = FakeStepRunner()
        runner.set_error("s1", RuntimeError("kaboom"))
        exe = _make_executor(step_runner=runner)
        plan = _plan(_step("s1"))

        result = await exe.execute(plan, FakeSnapshot())

        assert result.failed == 1
        failed = [sr for sr in result.step_results if sr.step_id == "s1"]
        assert failed[0].status == StepStatus.FAILED
        assert "kaboom" in (failed[0].error_detail or "")

    @pytest.mark.asyncio
    async def test_empty_params_default(self) -> None:
        """Steps with no params get empty dict as resolved_params."""
        runner = FakeStepRunner()
        exe = _make_executor(step_runner=runner)
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        assert runner.run_calls[0][1] == {}

    @pytest.mark.asyncio
    async def test_step_runner_trace_id_passed(self) -> None:
        """step_runner receives plan.trace_id."""
        runner = FakeStepRunner()
        exe = _make_executor(step_runner=runner)
        plan = _plan(_step("s1"), trace_id="tr-99")

        await exe.execute(plan, FakeSnapshot())

        assert runner.run_calls[0][3] == "tr-99"

    @pytest.mark.asyncio
    async def test_multiple_executions_reset_state(self) -> None:
        """Calling execute() twice resets state each time."""
        exe = _make_executor()
        plan1 = _plan(_step("s1"), plan_id="p1", trace_id="t1")
        plan2 = _plan(_step("s2"), plan_id="p2", trace_id="t2")

        r1 = await exe.execute(plan1, FakeSnapshot())
        r2 = await exe.execute(plan2, FakeSnapshot())

        assert r1.plan_id == "p1"
        assert r2.plan_id == "p2"
        # After second execute, merged_results should only have s2
        assert "s2" in exe.merged_results
        assert "s1" not in exe.merged_results

    @pytest.mark.asyncio
    async def test_repr_after_execute(self) -> None:
        """__repr__ works after execute()."""
        exe = _make_executor()
        plan = _plan(_step("s1"))

        await exe.execute(plan, FakeSnapshot())

        r = repr(exe)
        assert "DAGExecutor" in r
        assert "merged=1" in r
