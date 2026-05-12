"""
Tests for DAGExecutor -- 7.1.2 rewritten with real adapters.

All integration tests obtain DAGExecutor from OrchestratorFactory.create_standalone()
and script behavior through real in-memory test adapters:
  - MockFabricAdapter
  - MockStateReadAdapter
  - MockBridgeAdapter
  - TestDeltaAdapter

No fake adapter classes are used.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import CapabilityResult
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_DAG_STARTED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.orchestration.dag_executor import (
    MAX_STEPS,
    MAX_WAVES,
    CycleError,
    DAGExecutor,
    StepLimitExceeded,
    WaveLimitExceeded,
)
from k1.orchestrator.types import (
    CommittedPlan,
    PlanStep,
    RegistryEntry,
    StepStatus,
    Wave,
    WaveResult,
)


async def _svc(*, disable_builtin_guards: bool = True):
    service = await OrchestratorFactory.create_standalone()
    dag: DAGExecutor = service._dag_executor  # type: ignore[assignment]
    if disable_builtin_guards:
        dag._guards = []
    fabric: MockFabricAdapter = service._fabric_port  # type: ignore[assignment]
    state: MockStateReadAdapter = service._state_port  # type: ignore[assignment]
    bridge: MockBridgeAdapter = service._bridge_port  # type: ignore[assignment]
    delta: TestDeltaAdapter = service._delta_port  # type: ignore[assignment]
    return service, dag, fabric, state, bridge, delta


def _step(
    sid: str,
    capability: Optional[str] = None,
    *,
    params: Optional[Dict[str, Any]] = None,
    has_side_effects: bool = False,
    compensation: Optional[str] = None,
) -> PlanStep:
    return PlanStep(
        id=sid,
        capability=capability or f"cap.{sid}",
        params=params or {},
        has_side_effects=has_side_effects,
        compensation=compensation,
    )


def _steps(*ids: str) -> List[PlanStep]:
    return [_step(sid) for sid in ids]


def _plan(
    steps: List[PlanStep],
    *,
    deps: Optional[Dict[str, List[str]]] = None,
    plan_id: str = "plan-1",
    request_id: str = "req-1",
    trace_id: str = "trace-1",
) -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id,
        request_id=request_id,
        intent="test-intent",
        steps=steps,
        dependencies=deps or {},
        trace_id=trace_id,
    )


def _wave_ids(w: Wave) -> List[str]:
    return [s.id for s in w.steps]


def _snapshot(session_id: str = "default") -> SessionSnapshot:
    return SessionSnapshot(session_id=session_id, sections={}, timestamp_ms=int(time.time() * 1000))


def _success_result(trace_id: str = "trace-1") -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=f"r-{uuid4()}",
        data={"ok": True},
        provider_id="mock",
        trace_id=trace_id,
    )


def _failure_result(trace_id: str = "trace-1", msg: str = "boom") -> CapabilityResult:
    return CapabilityResult.failure_result(
        request_id=f"r-{uuid4()}",
        error_code="ERR",
        error_message=msg,
        retriable=False,
        provider_id="mock",
        trace_id=trace_id,
    )


def _register_caps(fabric: MockFabricAdapter, *caps: str) -> None:
    for cap in caps:
        fabric.register_capability(
            cap,
            RegistryEntry(
                name=cap,
                provider_type="tool",
                safety_band_min="GREEN",
                availability="AVAILABLE",
            ),
        )


class _RecordingGuard:
    def __init__(self) -> None:
        self.before_step_calls: List[str] = []
        self.after_step_calls: List[str] = []
        self.after_wave_calls: List[int] = []

    async def before_step(self, step: PlanStep, resolved_params: Dict[str, Any]) -> None:
        self.before_step_calls.append(step.id)

    async def after_step(self, step: PlanStep, result: Any, ctx: Any = None) -> None:
        self.after_step_calls.append(step.id)

    async def after_wave(
        self,
        wave_result: WaveResult,
        ctx: Any = None,
        remaining_steps: Any = None,
        plan_id: Any = None,
    ) -> None:
        self.after_wave_calls.append(wave_result.wave_index)


class TestBuildWaves:
    def test_linear_three_waves(self) -> None:
        steps = _steps("s1", "s2", "s3")
        waves = DAGExecutor.build_waves(steps, {"s2": ["s1"], "s3": ["s2"]})
        assert len(waves) == 3
        assert _wave_ids(waves[0]) == ["s1"]
        assert _wave_ids(waves[1]) == ["s2"]
        assert _wave_ids(waves[2]) == ["s3"]

    def test_parallel_single_wave(self) -> None:
        steps = _steps("a", "b", "c")
        waves = DAGExecutor.build_waves(steps, {})
        assert len(waves) == 1
        assert _wave_ids(waves[0]) == ["a", "b", "c"]

    def test_diamond_three_waves(self) -> None:
        steps = _steps("s1", "s2", "s3", "s4")
        deps = {"s2": ["s1"], "s3": ["s1"], "s4": ["s2", "s3"]}
        waves = DAGExecutor.build_waves(steps, deps)
        assert len(waves) == 3
        assert _wave_ids(waves[0]) == ["s1"]
        assert _wave_ids(waves[1]) == ["s2", "s3"]
        assert _wave_ids(waves[2]) == ["s4"]

    def test_single_step(self) -> None:
        steps = _steps("only")
        waves = DAGExecutor.build_waves(steps, {})
        assert len(waves) == 1
        assert _wave_ids(waves[0]) == ["only"]

    def test_wave_indices_sequential(self) -> None:
        steps = _steps("x", "y", "z")
        waves = DAGExecutor.build_waves(steps, {"y": ["x"], "z": ["y"]})
        assert [w.wave_index for w in waves] == [0, 1, 2]

    def test_resolved_params_initially_empty(self) -> None:
        steps = _steps("a", "b")
        waves = DAGExecutor.build_waves(steps, {"b": ["a"]})
        assert all(w.resolved_params == {} for w in waves)

    def test_cycle_self_loop(self) -> None:
        with pytest.raises(CycleError):
            DAGExecutor.build_waves(_steps("s1"), {"s1": ["s1"]})

    def test_cycle_two_steps(self) -> None:
        with pytest.raises(CycleError):
            DAGExecutor.build_waves(_steps("s1", "s2"), {"s1": ["s2"], "s2": ["s1"]})

    def test_invalid_dep_key(self) -> None:
        with pytest.raises(ValueError):
            DAGExecutor.build_waves(_steps("s1"), {"ghost": ["s1"]})

    def test_invalid_dep_value(self) -> None:
        with pytest.raises(ValueError):
            DAGExecutor.build_waves(_steps("s1", "s2"), {"s2": ["missing"]})

    def test_step_limit_exceeded(self) -> None:
        ids = [f"s{i}" for i in range(MAX_STEPS + 1)]
        with pytest.raises(StepLimitExceeded):
            DAGExecutor.build_waves(_steps(*ids), {})

    def test_wave_limit_exceeded(self) -> None:
        count = MAX_WAVES + 1
        ids = [f"s{i}" for i in range(count)]
        deps = {f"s{i}": [f"s{i-1}"] for i in range(1, count)}
        with pytest.raises(WaveLimitExceeded):
            DAGExecutor.build_waves(_steps(*ids), deps)


class TestExecuteCore:
    @pytest.mark.asyncio
    async def test_linear_exec_success(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        steps = [_step("s1", "cap.s1"), _step("s2", "cap.s2"), _step("s3", "cap.s3")]
        _register_caps(fabric, "cap.s1", "cap.s2", "cap.s3")
        plan = _plan(steps, deps={"s2": ["s1"], "s3": ["s2"]})

        result = await dag.execute(plan, _snapshot())

        assert result.success is True
        assert result.completed == 3
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_parallel_exec_success(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        steps = [_step("a", "cap.a"), _step("b", "cap.b")]
        _register_caps(fabric, "cap.a", "cap.b")

        result = await dag.execute(_plan(steps), _snapshot())

        assert result.success is True
        assert result.completed == 2

    @pytest.mark.asyncio
    async def test_diamond_exec_success(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        steps = [
            _step("s1", "cap.s1"),
            _step("s2", "cap.s2"),
            _step("s3", "cap.s3"),
            _step("s4", "cap.s4"),
        ]
        _register_caps(fabric, "cap.s1", "cap.s2", "cap.s3", "cap.s4")
        deps = {"s2": ["s1"], "s3": ["s1"], "s4": ["s2", "s3"]}

        result = await dag.execute(_plan(steps, deps=deps), _snapshot())

        assert result.success is True
        assert result.completed == 4

    @pytest.mark.asyncio
    async def test_single_step_exec(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1")

        result = await dag.execute(_plan([_step("s1", "cap.s1")]), _snapshot())

        assert result.total_steps == 1
        assert result.completed == 1


class TestWaveExecutionSemantics:
    @pytest.mark.asyncio
    async def test_parallel_wave_uses_concurrency(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2")
        fabric.script_timeout("cap.s1", 0.08)
        fabric.script_timeout("cap.s2", 0.08)

        started = time.monotonic()
        result = await dag.execute(
            _plan([_step("s1", "cap.s1"), _step("s2", "cap.s2")]), _snapshot()
        )
        duration = time.monotonic() - started

        assert result.success is True
        assert duration < 0.15

    @pytest.mark.asyncio
    async def test_single_step_waves_are_sequential(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2")
        fabric.script_timeout("cap.s1", 0.06)
        fabric.script_timeout("cap.s2", 0.06)
        plan = _plan([_step("s1", "cap.s1"), _step("s2", "cap.s2")], deps={"s2": ["s1"]})

        started = time.monotonic()
        result = await dag.execute(plan, _snapshot())
        duration = time.monotonic() - started

        assert result.success is True
        assert duration >= 0.10


class TestParamResolution:
    @pytest.mark.asyncio
    async def test_resolves_step_reference_param(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.producer", "cap.consumer")
        fabric.script_result(
            "cap.producer",
            CapabilityResult.success_result(
                request_id="r1",
                data={"value": 42},
                provider_id="mock",
                trace_id="trace-1",
            ),
        )
        plan = _plan(
            [
                _step("s1", "cap.producer"),
                _step("s2", "cap.consumer", params={"x": "$s1.result.value"}),
            ],
            deps={"s2": ["s1"]},
        )

        result = await dag.execute(plan, _snapshot())

        assert result.success is True
        consumer_calls = [c for c in fabric.call_log if c.capability_name == "cap.consumer"]
        assert len(consumer_calls) == 1
        assert consumer_calls[0].params.get("x") == 42

    @pytest.mark.asyncio
    async def test_missing_reference_fails_step(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2")
        plan = _plan(
            [
                _step("s1", "cap.s1"),
                _step("s2", "cap.s2", params={"x": "$missing.result.value"}),
            ],
            deps={"s2": ["s1"]},
        )

        result = await dag.execute(plan, _snapshot())

        assert result.success is False
        s2 = [r for r in result.step_results if r.step_id == "s2"][0]
        assert s2.status == StepStatus.FAILED
        assert "ParamResolver" in (s2.error_detail or "")
        fabric.assert_called("cap.s2", times=0)


class TestGuardPipeline:
    @pytest.mark.asyncio
    async def test_before_after_step_hooks_called(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2")
        guard = _RecordingGuard()
        dag._guards = [guard]

        result = await dag.execute(
            _plan([_step("s1", "cap.s1"), _step("s2", "cap.s2")]), _snapshot()
        )

        assert result.success is True
        assert set(guard.before_step_calls) == {"s1", "s2"}
        assert set(guard.after_step_calls) == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_after_wave_called_per_wave(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2", "cap.s3")
        guard = _RecordingGuard()
        dag._guards = [guard]
        plan = _plan(
            [_step("s1", "cap.s1"), _step("s2", "cap.s2"), _step("s3", "cap.s3")],
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        result = await dag.execute(plan, _snapshot())

        assert result.success is True
        assert guard.after_wave_calls == [0, 1, 2]


class TestCancellationAndInterrupt:
    @pytest.mark.asyncio
    async def test_dependency_failure_cancels_dependents(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2", "cap.s3")
        fabric.script_result("cap.s1", _failure_result(msg="s1-failed"))
        plan = _plan(
            [
                _step("s1", "cap.s1"),
                _step("s2", "cap.s2"),
                _step("s3", "cap.s3"),
            ],
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        result = await dag.execute(plan, _snapshot())

        assert result.success is False
        assert [r for r in result.step_results if r.step_id == "s2"][
            0
        ].status == StepStatus.CANCELLED
        assert [r for r in result.step_results if r.step_id == "s3"][
            0
        ].status == StepStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_interrupt_before_next_wave_skips_remaining(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2")
        fabric.script_timeout("cap.s1", 0.05)
        plan = _plan([_step("s1", "cap.s1"), _step("s2", "cap.s2")], deps={"s2": ["s1"]})

        async def _flip_interrupt() -> None:
            await asyncio.sleep(0.02)
            dag.interrupt_flag = True

        flipper = asyncio.create_task(_flip_interrupt())
        result = await dag.execute(plan, _snapshot())
        await flipper

        assert result.success is False
        s2 = [r for r in result.step_results if r.step_id == "s2"][0]
        assert s2.status == StepStatus.CANCELLED


class TestSafetyBandAndStateReads:
    @pytest.mark.asyncio
    async def test_red_safety_band_aborts_execution(self) -> None:
        _, dag, fabric, state, _, _ = await _svc()
        _register_caps(fabric, "cap.s1")
        state.set_section("default", "control.safety_band", {"level": "RED"})

        result = await dag.execute(_plan([_step("s1", "cap.s1")]), _snapshot())

        assert result.success is False
        assert result.completed == 0

    @pytest.mark.asyncio
    async def test_safety_band_reread_each_wave(self) -> None:
        _, dag, fabric, state, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2", "cap.s3")
        state.set_section("default", "control.safety_band", {"level": "GREEN"})
        plan = _plan(
            [_step("s1", "cap.s1"), _step("s2", "cap.s2"), _step("s3", "cap.s3")],
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        result = await dag.execute(plan, _snapshot())

        assert result.success is True
        reads = [r for r in state.read_log if r == ("default", "control.safety_band")]
        assert len(reads) == 3


class TestSagaCompensation:
    @pytest.mark.asyncio
    async def test_side_effect_failure_triggers_lifo_compensation(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2", "cap.s3", "cap.undo.s1", "cap.undo.s2")

        # s3 fails; s1/s2 succeeded with side effects, so compensate s2 then s1.
        fabric.script_result("cap.s3", _failure_result(msg="fail-final"))

        steps = [
            _step("s1", "cap.s1", has_side_effects=True, compensation="cap.undo.s1"),
            _step("s2", "cap.s2", has_side_effects=True, compensation="cap.undo.s2"),
            _step("s3", "cap.s3", has_side_effects=True),
        ]
        plan = _plan(steps, deps={"s2": ["s1"], "s3": ["s2"]})

        result = await dag.execute(plan, _snapshot())

        assert result.success is False
        assert len(result.compensations) == 2
        assert [c.step_id for c in result.compensations] == ["s2", "s1"]

        comp_caps = [
            r.capability_name for r in fabric.call_log if r.capability_name.startswith("cap.undo")
        ]
        assert comp_caps == ["cap.undo.s2", "cap.undo.s1"]

    @pytest.mark.asyncio
    async def test_compensation_failure_dead_lettered(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2", "cap.undo.s1")

        fabric.script_result("cap.s2", _failure_result(msg="fail-trigger"))
        from k1.orchestrator.types import AdapterError, ErrorSeverity

        fabric.script_error(
            "cap.undo.s1",
            AdapterError(
                severity=ErrorSeverity.TERMINAL,
                adapter_name="fabric",
                operation="execute",
                error_code="UNDO_FAIL",
                error_message="undo failed",
            ),
        )

        steps = [
            _step("s1", "cap.s1", has_side_effects=True, compensation="cap.undo.s1"),
            _step("s2", "cap.s2", has_side_effects=True),
        ]

        result = await dag.execute(_plan(steps, deps={"s2": ["s1"]}), _snapshot())

        assert len(result.compensations) == 1
        assert result.compensations[0].status == "DEAD_LETTERED"

    @pytest.mark.asyncio
    async def test_no_side_effect_steps_no_compensation(self) -> None:
        _, dag, fabric, _, _, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2")
        fabric.script_result("cap.s2", _failure_result(msg="normal failure"))

        steps = [
            _step("s1", "cap.s1", has_side_effects=False),
            _step("s2", "cap.s2", has_side_effects=False),
        ]

        result = await dag.execute(_plan(steps, deps={"s2": ["s1"]}), _snapshot())

        assert result.success is False
        assert result.compensations == []


class TestWalAndDeltaIntegration:
    @pytest.mark.asyncio
    async def test_wal_plan_start_wave_complete_dag_complete_written(self) -> None:
        _, dag, fabric, _, bridge, _ = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2")
        plan = _plan([_step("s1", "cap.s1"), _step("s2", "cap.s2")], deps={"s2": ["s1"]})

        result = await dag.execute(plan, _snapshot())

        assert result.success is True
        wal = bridge.get_wal("plan-1")
        entry_types = [e["entry_type"] for e in wal]
        assert "PLAN_START" in entry_types
        assert entry_types.count("WAVE_COMPLETE") == 2
        assert "DAG_COMPLETE" in entry_types

    @pytest.mark.asyncio
    async def test_step_complete_written_per_step(self) -> None:
        _, dag, fabric, _, bridge, _ = await _svc()
        _register_caps(fabric, "cap.a", "cap.b")
        await dag.execute(_plan([_step("a", "cap.a"), _step("b", "cap.b")]), _snapshot())

        # M5.2.5: STEP_COMPLETE keyed by plan_id (was step.id) so
        # recover_from_wal(plan_id) can actually retrieve these entries.
        plan_wal = bridge.get_wal("plan-1")
        step_completes = [e for e in plan_wal if e["entry_type"] == "STEP_COMPLETE"]
        step_ids = {e["payload"]["step_id"] for e in step_completes}
        assert step_ids == {"a", "b"}
        # Confirm the legacy step-id-keyed buckets are now empty.
        assert not any(
            e["entry_type"] == "STEP_COMPLETE" for e in bridge.get_wal("a")
        )
        assert not any(
            e["entry_type"] == "STEP_COMPLETE" for e in bridge.get_wal("b")
        )

    @pytest.mark.asyncio
    async def test_dag_started_and_completed_emitted(self) -> None:
        _, dag, fabric, _, _, delta = await _svc()
        _register_caps(fabric, "cap.s1")

        await dag.execute(_plan([_step("s1", "cap.s1")]), _snapshot())

        delta.assert_emitted(ORCH_DAG_STARTED, 1)
        dag_done = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert len(dag_done) == 1
        assert dag_done[0]["success"] is True

    @pytest.mark.asyncio
    async def test_progress_emitted_per_wave(self) -> None:
        _, dag, fabric, _, _, delta = await _svc()
        _register_caps(fabric, "cap.s1", "cap.s2", "cap.s3")
        plan = _plan(
            [_step("s1", "cap.s1"), _step("s2", "cap.s2"), _step("s3", "cap.s3")],
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        await dag.execute(plan, _snapshot())

        assert len(delta.progress_log) == 3


class TestRecoverFromWal:
    @pytest.mark.asyncio
    async def test_no_wal_returns_no_wal(self) -> None:
        _, _, _, _, bridge, _ = await _svc()
        info = await DAGExecutor.recover_from_wal(bridge, "unknown")
        assert info["status"] == "NO_WAL"
        assert info["resume_wave_index"] == 0

    @pytest.mark.asyncio
    async def test_completed_wal_returns_completed(self) -> None:
        _, _, _, _, bridge, _ = await _svc()
        bridge.inject_wal(
            "dag-1",
            [
                {"entry_type": "PLAN_START", "payload": {}},
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 0, "completed_steps": ["s1"]},
                },
                {"entry_type": "DAG_COMPLETE", "payload": {"status": "COMPLETED"}},
            ],
        )

        info = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert info["status"] == "COMPLETED"
        assert info["resume_wave_index"] == -1
        assert info["dag_status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_resume_after_last_wave(self) -> None:
        _, _, _, _, bridge, _ = await _svc()
        bridge.inject_wal(
            "dag-2",
            [
                {"entry_type": "PLAN_START", "payload": {}},
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 0, "completed_steps": ["s1"]},
                },
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 1, "completed_steps": ["s2"]},
                },
            ],
        )

        info = await DAGExecutor.recover_from_wal(bridge, "dag-2")

        assert info["status"] == "RESUME"
        assert info["resume_wave_index"] == 2
        assert set(info["completed_steps"]) == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_plan_start_only_is_restart(self) -> None:
        _, _, _, _, bridge, _ = await _svc()
        bridge.inject_wal("dag-3", [{"entry_type": "PLAN_START", "payload": {}}])

        info = await DAGExecutor.recover_from_wal(bridge, "dag-3")

        assert info["status"] == "RESTART"
        assert info["resume_wave_index"] == 0
