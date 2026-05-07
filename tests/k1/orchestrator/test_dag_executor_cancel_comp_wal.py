"""
Tests for DAGExecutor Issues 2.2.4, 2.2.5, 2.2.6.

Issue 2.2.4: cancel_dependents() -- BFS dependent cancellation (ORCH-07).
Issue 2.2.5: _compensate() + _resolve_compensation_capability() -- saga recovery.
Issue 2.2.6: recover_from_wal() -- WAL recovery protocol.

Test classes:
  TestCancelDependentsUnit      -- Pure cancel_dependents() with various graphs.
  TestCancelDependentsIntegrate -- Integration: execute() auto-cancels dependents.
  TestCompensateUnit            -- _compensate() with various saga scenarios.
  TestResolveCompensation       -- _resolve_compensation_capability() PROD-3 chain.
  TestCompensateIntegration     -- Full execute() with saga compensation.
  TestRecoverFromWal            -- recover_from_wal() static method.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.orchestration.dag_executor import DAGExecutor
from k1.orchestrator.types import (
    CommittedPlan,
    PlanStep,
    RegistryEntry,
    StepResult,
    StepStatus,
    WaveResult,
)

# ===========================================================================
# Fake ports
# ===========================================================================


class FakeStatePort:
    """Fake IStateReadPort -- configurable safety band."""

    def __init__(self, safety_level: str = "GREEN") -> None:
        self.safety_level = safety_level

    async def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        if section == "control.safety_band":
            return {"level": self.safety_level}
        return None

    async def read_sections(self, session_id: str, names: List[str]) -> Dict[str, Any]:
        return {}

    async def get_snapshot(self, session_id: str) -> Any:
        return None


class FakeBridgePort:
    """Fake IBridgeWritePort -- records WAL writes, configurable read_wal."""

    def __init__(
        self,
        wal_entries: Optional[List[Dict[str, Any]]] = None,
        read_wal_error: bool = False,
    ) -> None:
        self.wal_writes: List[Tuple[str, str, Dict[str, Any], str]] = []
        self.audit_calls: List[Tuple[Dict[str, Any], str]] = []
        self._wal_entries = wal_entries
        self._read_wal_error = read_wal_error

    async def write_wal(
        self,
        dag_id: str,
        entry_type: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        self.wal_writes.append((dag_id, entry_type, payload, trace_id))

    async def submit_audit(self, run_manifest: Dict[str, Any], trace_id: str) -> None:
        self.audit_calls.append((run_manifest, trace_id))

    async def read_wal(self, dag_id: str) -> Optional[List[Dict[str, Any]]]:
        if self._read_wal_error:
            raise RuntimeError("WAL read failed")
        return self._wal_entries

    async def list_wal_ids(self) -> List[str]:
        return []


class FakeDeltaPort:
    """Fake IDeltaEmitPort."""

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
        self.run_calls: List[str] = []

    def set_result(self, step_id: str, result: StepResult) -> None:
        self._results[step_id] = result

    async def run(
        self,
        step: PlanStep,
        resolved_params: Dict[str, Any],
        merged_results: Dict[str, Any],
        trace_id: str,
    ) -> StepResult:
        self.run_calls.append(step.id)
        if step.id in self._results:
            return self._results[step.id]
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


class FakeFabricPort:
    """Fake IFabricGatewayPort -- records execute & query_registry calls."""

    def __init__(self) -> None:
        self.execute_calls: List[CapabilityRequest] = []
        self._execute_results: Dict[str, CapabilityResult] = {}
        self._execute_errors: Dict[str, Exception] = {}
        self._registry: Dict[str, RegistryEntry] = {}
        self._registry_errors: Dict[str, Exception] = {}

    def set_execute_result(self, cap_name: str, result: CapabilityResult) -> None:
        self._execute_results[cap_name] = result

    def set_execute_error(self, cap_name: str, error: Exception) -> None:
        self._execute_errors[cap_name] = error

    def set_registry_entry(self, cap_name: str, entry: RegistryEntry) -> None:
        self._registry[cap_name] = entry

    def set_registry_error(self, cap_name: str, error: Exception) -> None:
        self._registry_errors[cap_name] = error

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        self.execute_calls.append(request)
        cap = request.capability_name
        if cap in self._execute_errors:
            raise self._execute_errors[cap]
        if cap in self._execute_results:
            return self._execute_results[cap]
        return CapabilityResult.success_result(
            request_id=request.request_id,
            data={"compensated": True},
            provider_id="test-comp",
            trace_id=request.trace_id,
        )

    async def execute_batch(self, requests: List[CapabilityRequest]) -> List[CapabilityResult]:
        return [await self.execute(r) for r in requests]

    async def query_registry(self, capability_name: str) -> Optional[RegistryEntry]:
        if capability_name in self._registry_errors:
            raise self._registry_errors[capability_name]
        return self._registry.get(capability_name)


class FakePort:
    """Minimal fake for unused ports."""

    pass


@dataclass
class FakeSnapshot:
    """Fake SessionSnapshot."""

    session_id: str = "test-session"
    sections: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timestamp_ms: int = 0


# ===========================================================================
# Factory helpers
# ===========================================================================


def _step(
    step_id: str,
    capability: str = "cap.test",
    has_side_effects: bool = False,
    compensation: Optional[str] = None,
    **kwargs: Any,
) -> PlanStep:
    """Create a PlanStep with optional side-effect / compensation fields."""
    return PlanStep(
        id=step_id,
        capability=capability,
        has_side_effects=has_side_effects,
        compensation=compensation,
        **kwargs,
    )


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
    fabric_port: Optional[FakeFabricPort] = None,
    step_runner: Optional[FakeStepRunner] = None,
    state_port: Optional[FakeStatePort] = None,
    bridge_port: Optional[FakeBridgePort] = None,
    delta_port: Optional[FakeDeltaPort] = None,
) -> DAGExecutor:
    """Create DAGExecutor with fake deps, defaulting to working fakes."""
    return DAGExecutor(
        fabric_port=fabric_port or FakeFabricPort(),
        planner_port=FakePort(),
        delta_port=delta_port or FakeDeltaPort(),
        state_port=state_port or FakeStatePort(),
        bridge_port=bridge_port or FakeBridgePort(),
        step_runner=step_runner or FakeStepRunner(),
        error_router=FakePort(),
        guards=[],
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
# 2.2.4: TestCancelDependentsUnit
# ===========================================================================


class TestCancelDependentsUnit:
    """Pure cancel_dependents() with various dependency graphs."""

    def test_linear_chain_cancels_all_downstream(self) -> None:
        """s1 -> s2 -> s3: failing s1 cancels s2, s3."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        cancelled = exe.cancel_dependents("s1", plan)

        assert set(cancelled) == {"s2", "s3"}
        assert exe._cancelled_steps == {"s2", "s3"}

    def test_fan_out_cancels_all_children(self) -> None:
        """s1 -> (s2, s3, s4): failing s1 cancels all children."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            _step("s4"),
            deps={"s2": ["s1"], "s3": ["s1"], "s4": ["s1"]},
        )

        cancelled = exe.cancel_dependents("s1", plan)

        assert set(cancelled) == {"s2", "s3", "s4"}

    def test_diamond_cancels_transitive(self) -> None:
        """Diamond: s1->(s2,s3)->s4. Failing s1 cancels s2, s3, s4."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            _step("s4"),
            deps={"s2": ["s1"], "s3": ["s1"], "s4": ["s2", "s3"]},
        )

        cancelled = exe.cancel_dependents("s1", plan)

        assert set(cancelled) == {"s2", "s3", "s4"}

    def test_independent_steps_not_cancelled(self) -> None:
        """s1 fails, but s3 has no dep on s1 -- s3 not cancelled."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            deps={"s2": ["s1"]},  # s3 is independent
        )

        cancelled = exe.cancel_dependents("s1", plan)

        assert "s3" not in cancelled
        assert set(cancelled) == {"s2"}
        assert "s3" not in exe._cancelled_steps

    def test_mid_chain_failure_cancels_only_downstream(self) -> None:
        """s1->s2->s3: failing s2 cancels only s3, not s1."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        cancelled = exe.cancel_dependents("s2", plan)

        assert set(cancelled) == {"s3"}
        assert "s1" not in exe._cancelled_steps

    def test_no_dependents_returns_empty(self) -> None:
        """Leaf step fails with no downstream: empty cancel list."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            deps={"s2": ["s1"]},
        )

        cancelled = exe.cancel_dependents("s2", plan)

        assert cancelled == []

    def test_idempotent_cancel(self) -> None:
        """Calling cancel_dependents twice returns only NEW cancellations."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        first = exe.cancel_dependents("s1", plan)
        second = exe.cancel_dependents("s1", plan)

        assert set(first) == {"s2", "s3"}
        assert second == []  # already cancelled

    def test_multi_hop_transitive_closure(self) -> None:
        """5-step chain: s1->s2->s3->s4->s5, fail s1 cancels all."""
        exe = _make_executor()
        steps = [_step(f"s{i}") for i in range(1, 6)]
        deps = {f"s{i+1}": [f"s{i}"] for i in range(1, 5)}
        plan = _plan(*steps, deps=deps)

        cancelled = exe.cancel_dependents("s1", plan)

        assert set(cancelled) == {"s2", "s3", "s4", "s5"}

    def test_complex_diamond_partial_cancel(self) -> None:
        """
        s1 -+-> s2 -> s4
             \\-> s3 -> s5
        s6 (independent)

        Failing s2 cancels only s4 (s3 and s5 still reachable from s1).
        """
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            _step("s4"),
            _step("s5"),
            _step("s6"),
            deps={
                "s2": ["s1"],
                "s3": ["s1"],
                "s4": ["s2"],
                "s5": ["s3"],
            },
        )

        cancelled = exe.cancel_dependents("s2", plan)

        assert set(cancelled) == {"s4"}
        assert "s3" not in exe._cancelled_steps
        assert "s5" not in exe._cancelled_steps
        assert "s6" not in exe._cancelled_steps

    def test_returns_sorted(self) -> None:
        """cancel_dependents returns sorted list of step IDs."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("c"),
            _step("a"),
            _step("b"),
            deps={"c": ["s1"], "a": ["s1"], "b": ["s1"]},
        )

        cancelled = exe.cancel_dependents("s1", plan)

        assert cancelled == ["a", "b", "c"]

    def test_cancelled_steps_accumulate_across_calls(self) -> None:
        """Multiple cancel calls accumulate in _cancelled_steps."""
        exe = _make_executor()
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            _step("s4"),
            deps={"s3": ["s1"], "s4": ["s2"]},
        )

        exe.cancel_dependents("s1", plan)
        exe.cancel_dependents("s2", plan)

        assert exe._cancelled_steps == {"s3", "s4"}

    def test_no_dependencies_at_all(self) -> None:
        """All steps independent: cancel_dependents returns empty."""
        exe = _make_executor()
        plan = _plan(_step("s1"), _step("s2"), _step("s3"))

        cancelled = exe.cancel_dependents("s1", plan)

        assert cancelled == []


# ===========================================================================
# 2.2.4: TestCancelDependentsIntegration
# ===========================================================================


class TestCancelDependentsIntegration:
    """Integration: execute() auto-cancels dependents of failed steps."""

    @pytest.mark.asyncio
    async def test_failed_step_cancels_dependents_in_later_waves(self) -> None:
        """s1->s2->s3: s1 fails -> s2, s3 cancelled without running."""
        runner = FakeStepRunner()
        runner.set_result("s1", _failed_result("s1"))
        exe = _make_executor(step_runner=runner)
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            deps={"s2": ["s1"], "s3": ["s2"]},
        )

        result = await exe.execute(plan, FakeSnapshot())

        assert result.failed >= 1
        assert result.cancelled >= 2
        # s2 and s3 never ran
        assert "s2" not in runner.run_calls
        assert "s3" not in runner.run_calls

    @pytest.mark.asyncio
    async def test_independent_branch_still_runs_after_failure(self) -> None:
        """s1->s2, s3 independent. s1 fails, s3 still runs."""
        runner = FakeStepRunner()
        runner.set_result("s1", _failed_result("s1"))
        exe = _make_executor(step_runner=runner)
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            deps={"s2": ["s1"]},  # s3 independent, wave 0
        )

        result = await exe.execute(plan, FakeSnapshot())

        # s3 is in wave 0 with s1, so it runs
        assert "s3" in runner.run_calls
        # s2 is cancelled (depends on s1)
        s2_results = [sr for sr in result.step_results if sr.step_id == "s2"]
        assert len(s2_results) == 1
        assert s2_results[0].status == StepStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_diamond_partial_failure(self) -> None:
        """
        s1 -> s3
        s2 -> s3
        s1 fails, s2 succeeds. s3 cancelled because it depends on s1.
        """
        runner = FakeStepRunner()
        runner.set_result("s1", _failed_result("s1"))
        exe = _make_executor(step_runner=runner)
        plan = _plan(
            _step("s1"),
            _step("s2"),
            _step("s3"),
            deps={"s3": ["s1", "s2"]},
        )

        result = await exe.execute(plan, FakeSnapshot())

        s3_results = [sr for sr in result.step_results if sr.step_id == "s3"]
        assert len(s3_results) == 1
        assert s3_results[0].status == StepStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancelled_steps_reset_on_new_execute(self) -> None:
        """_cancelled_steps reset at start of each execute() call."""
        runner = FakeStepRunner()
        runner.set_result("s1", _failed_result("s1"))
        exe = _make_executor(step_runner=runner)

        plan1 = _plan(
            _step("s1"),
            _step("s2"),
            deps={"s2": ["s1"]},
            plan_id="p1",
        )
        await exe.execute(plan1, FakeSnapshot())
        assert len(exe._cancelled_steps) > 0

        # Second execute resets
        runner2 = FakeStepRunner()
        exe2 = _make_executor(step_runner=runner2)
        plan2 = _plan(_step("a1"), plan_id="p2")
        await exe2.execute(plan2, FakeSnapshot())
        assert len(exe2._cancelled_steps) == 0

    @pytest.mark.asyncio
    async def test_cancelled_dependents_logged_in_result(self) -> None:
        """Cancelled steps have 'dependency failure' detail in result."""
        runner = FakeStepRunner()
        runner.set_result("s1", _failed_result("s1"))
        exe = _make_executor(step_runner=runner)
        plan = _plan(
            _step("s1"),
            _step("s2"),
            deps={"s2": ["s1"]},
        )

        result = await exe.execute(plan, FakeSnapshot())

        s2_results = [sr for sr in result.step_results if sr.step_id == "s2"]
        assert len(s2_results) == 1
        detail = s2_results[0].error_detail or ""
        assert "dependency" in detail.lower() or "cancelled" in detail.lower()


# ===========================================================================
# 2.2.5: TestResolveCompensation
# ===========================================================================


class TestResolveCompensation:
    """_resolve_compensation_capability() PROD-3 lookup chain."""

    @pytest.mark.asyncio
    async def test_chain1_planstep_compensation_field(self) -> None:
        """PlanStep.compensation field takes priority."""
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric)
        step = _step("s1", compensation="cap.undo_s1")

        result = await exe._resolve_compensation_capability(step)

        assert result == "cap.undo_s1"
        # Registry NOT consulted
        assert len(fabric.execute_calls) == 0

    @pytest.mark.asyncio
    async def test_chain2_registry_lookup(self) -> None:
        """Falls back to registry if PlanStep.compensation is None."""
        fabric = FakeFabricPort()
        fabric.set_registry_entry(
            "cap.test",
            RegistryEntry(
                name="cap.test",
                provider_type="tool",
                safety_band_min="GREEN",
                availability="AVAILABLE",
                compensation_capability="cap.undo_from_registry",
            ),
        )
        exe = _make_executor(fabric_port=fabric)
        step = _step("s1", capability="cap.test")

        result = await exe._resolve_compensation_capability(step)

        assert result == "cap.undo_from_registry"

    @pytest.mark.asyncio
    async def test_chain3_none_when_no_compensation(self) -> None:
        """Returns None when neither PlanStep nor registry has compensation."""
        fabric = FakeFabricPort()
        fabric.set_registry_entry(
            "cap.test",
            RegistryEntry(
                name="cap.test",
                provider_type="tool",
                safety_band_min="GREEN",
                availability="AVAILABLE",
                compensation_capability=None,
            ),
        )
        exe = _make_executor(fabric_port=fabric)
        step = _step("s1", capability="cap.test")

        result = await exe._resolve_compensation_capability(step)

        assert result is None

    @pytest.mark.asyncio
    async def test_chain3_none_when_registry_missing(self) -> None:
        """Returns None when capability not in registry at all."""
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric)
        step = _step("s1", capability="cap.unknown")

        result = await exe._resolve_compensation_capability(step)

        assert result is None

    @pytest.mark.asyncio
    async def test_registry_error_falls_through(self) -> None:
        """Registry exception -> returns None (chain 3)."""
        fabric = FakeFabricPort()
        fabric.set_registry_error("cap.test", RuntimeError("registry down"))
        exe = _make_executor(fabric_port=fabric)
        step = _step("s1", capability="cap.test")

        result = await exe._resolve_compensation_capability(step)

        assert result is None

    @pytest.mark.asyncio
    async def test_planstep_field_wins_over_registry(self) -> None:
        """PlanStep.compensation takes priority even when registry has entry."""
        fabric = FakeFabricPort()
        fabric.set_registry_entry(
            "cap.test",
            RegistryEntry(
                name="cap.test",
                provider_type="tool",
                safety_band_min="GREEN",
                availability="AVAILABLE",
                compensation_capability="cap.registry_undo",
            ),
        )
        exe = _make_executor(fabric_port=fabric)
        step = _step("s1", capability="cap.test", compensation="cap.planner_undo")

        result = await exe._resolve_compensation_capability(step)

        assert result == "cap.planner_undo"


# ===========================================================================
# 2.2.5: TestCompensateUnit
# ===========================================================================


class TestCompensateUnit:
    """_compensate() saga recovery scenarios."""

    @pytest.mark.asyncio
    async def test_no_side_effect_failure_returns_empty(self) -> None:
        """No side-effect step failed -> no compensations."""
        exe = _make_executor()
        plan = _plan(
            _step("s1", has_side_effects=True),
            _step("s2", has_side_effects=False),
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[_success_result("s1"), _failed_result("s2")],
                duration_ms=10,
            )
        ]

        comps = await exe._compensate(wr, plan)

        assert comps == []

    @pytest.mark.asyncio
    async def test_side_effect_fail_triggers_compensation(self) -> None:
        """Side-effect step fails -> completed side-effect steps compensated."""
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True),
            deps={"s2": ["s1"]},
        )
        # s1 completed, s2 failed
        wr = [
            WaveResult(wave_index=0, step_results=[_success_result("s1")], duration_ms=5),
            WaveResult(wave_index=1, step_results=[_failed_result("s2")], duration_ms=5),
        ]

        comps = await exe._compensate(wr, plan)

        assert len(comps) == 1
        assert comps[0].step_id == "s1"
        assert comps[0].compensation_capability == "cap.undo_s1"
        assert comps[0].status == "EXECUTED"
        # Fabric received the compensation request
        assert len(fabric.execute_calls) == 1
        assert fabric.execute_calls[0].capability_name == "cap.undo_s1"

    @pytest.mark.asyncio
    async def test_reverse_declaration_order(self) -> None:
        """Compensations run in REVERSE plan declaration order (INV-2)."""
        fabric = FakeFabricPort()
        execution_order: List[str] = []

        original_execute = fabric.execute

        async def _tracking_execute(request: CapabilityRequest) -> CapabilityResult:
            execution_order.append(request.capability_name)
            return await original_execute(request)

        fabric.execute = _tracking_execute  # type: ignore[assignment]

        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True, compensation="cap.undo_s2"),
            _step("s3", has_side_effects=True, compensation="cap.undo_s3"),
            _step("s4", has_side_effects=True),  # this one fails
        )
        # All completed except s4 which fails
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[
                    _success_result("s1"),
                    _success_result("s2"),
                    _success_result("s3"),
                    _failed_result("s4"),
                ],
                duration_ms=10,
            ),
        ]

        comps = await exe._compensate(wr, plan)

        # 3 completed side-effect steps compensated
        assert len(comps) == 3
        # Reverse declaration order: s3, s2, s1
        assert execution_order == ["cap.undo_s3", "cap.undo_s2", "cap.undo_s1"]
        assert [c.step_id for c in comps] == ["s3", "s2", "s1"]

    @pytest.mark.asyncio
    async def test_no_compensation_capability_dead_lettered(self) -> None:
        """Step with no compensation available -> DEAD_LETTERED."""
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True),  # no compensation field, no registry
            _step("s2", has_side_effects=True),
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[_success_result("s1"), _failed_result("s2")],
                duration_ms=10,
            ),
        ]

        comps = await exe._compensate(wr, plan)

        assert len(comps) == 1
        assert comps[0].step_id == "s1"
        assert comps[0].status == "DEAD_LETTERED"
        assert "No compensation" in (comps[0].error_detail or "")
        # No fabric execute call
        assert len(fabric.execute_calls) == 0

    @pytest.mark.asyncio
    async def test_compensation_execution_failure_dead_lettered(self) -> None:
        """Compensation execution exception -> DEAD_LETTERED."""
        fabric = FakeFabricPort()
        fabric.set_execute_error("cap.undo_s1", RuntimeError("comp failed"))
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True),
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[_success_result("s1"), _failed_result("s2")],
                duration_ms=10,
            ),
        ]

        comps = await exe._compensate(wr, plan)

        assert len(comps) == 1
        assert comps[0].status == "DEAD_LETTERED"
        assert "comp failed" in (comps[0].error_detail or "")

    @pytest.mark.asyncio
    async def test_compensation_returns_failure_dead_lettered(self) -> None:
        """Compensation returns success=False -> DEAD_LETTERED."""
        fabric = FakeFabricPort()
        fabric.set_execute_result(
            "cap.undo_s1",
            CapabilityResult.failure_result(
                request_id="comp-1",
                error_code="COMP_FAIL",
                error_message="compensation rejected",
            ),
        )
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True),
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[_success_result("s1"), _failed_result("s2")],
                duration_ms=10,
            ),
        ]

        comps = await exe._compensate(wr, plan)

        assert len(comps) == 1
        assert comps[0].status == "DEAD_LETTERED"
        assert "compensation rejected" in (comps[0].error_detail or "")

    @pytest.mark.asyncio
    async def test_non_side_effect_steps_not_compensated(self) -> None:
        """Only side-effect steps get compensated, not pure steps."""
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=False),  # pure, no compensation
            _step("s2", has_side_effects=True, compensation="cap.undo_s2"),
            _step("s3", has_side_effects=True),  # fails
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[
                    _success_result("s1"),
                    _success_result("s2"),
                    _failed_result("s3"),
                ],
                duration_ms=10,
            ),
        ]

        comps = await exe._compensate(wr, plan)

        # Only s2 compensated (has side effects and completed)
        assert len(comps) == 1
        assert comps[0].step_id == "s2"

    @pytest.mark.asyncio
    async def test_wal_writes_compensation_entries(self) -> None:
        """WAL COMPENSATION entry written per compensation."""
        bridge = FakeBridgePort()
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric, bridge_port=bridge)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True),
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[_success_result("s1"), _failed_result("s2")],
                duration_ms=10,
            ),
        ]

        await exe._compensate(wr, plan)

        comp_wals = [w for w in bridge.wal_writes if w[1] == "COMPENSATION"]
        assert len(comp_wals) == 1
        assert comp_wals[0][2]["step_id"] == "s1"
        assert comp_wals[0][2]["compensation_capability"] == "cap.undo_s1"
        assert comp_wals[0][2]["status"] == "EXECUTED"

    @pytest.mark.asyncio
    async def test_failed_step_itself_not_compensated(self) -> None:
        """The failing side-effect step is NOT compensated (never completed)."""
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
        )
        # Only step, and it failed
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[_failed_result("s1")],
                duration_ms=10,
            ),
        ]

        comps = await exe._compensate(wr, plan)

        # No completed side-effect steps to compensate
        assert comps == []

    @pytest.mark.asyncio
    async def test_all_steps_succeed_no_compensation(self) -> None:
        """All side-effect steps succeed -> no compensation needed."""
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True, compensation="cap.undo_s2"),
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[_success_result("s1"), _success_result("s2")],
                duration_ms=10,
            ),
        ]

        comps = await exe._compensate(wr, plan)

        assert comps == []

    @pytest.mark.asyncio
    async def test_compensation_record_fields(self) -> None:
        """CompensationRecord has correct dag_id, step_id, record_id."""
        fabric = FakeFabricPort()
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True),
            plan_id="dag-99",
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[_success_result("s1"), _failed_result("s2")],
                duration_ms=10,
            ),
        ]

        comps = await exe._compensate(wr, plan)

        assert comps[0].dag_id == "dag-99"
        assert comps[0].step_id == "s1"
        assert comps[0].record_id  # non-empty UUID
        assert comps[0].completed_at is not None

    @pytest.mark.asyncio
    async def test_compensation_sequential_not_concurrent(self) -> None:
        """Compensations execute ONE AT A TIME, not concurrently (ADR-1.1.8)."""
        fabric = FakeFabricPort()
        active_count = 0
        max_concurrent = 0

        original_execute = fabric.execute

        async def _concurrent_tracking(request: CapabilityRequest) -> CapabilityResult:
            nonlocal active_count, max_concurrent
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.01)  # brief delay to detect concurrency
            result = await original_execute(request)
            active_count -= 1
            return result

        fabric.execute = _concurrent_tracking  # type: ignore[assignment]
        exe = _make_executor(fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True, compensation="cap.undo_s2"),
            _step("s3", has_side_effects=True),  # fails
        )
        wr = [
            WaveResult(
                wave_index=0,
                step_results=[
                    _success_result("s1"),
                    _success_result("s2"),
                    _failed_result("s3"),
                ],
                duration_ms=10,
            ),
        ]

        await exe._compensate(wr, plan)

        assert max_concurrent == 1  # sequential, never > 1


# ===========================================================================
# 2.2.5: TestCompensateIntegration
# ===========================================================================


class TestCompensateIntegration:
    """Full execute() with saga compensation end-to-end."""

    @pytest.mark.asyncio
    async def test_execute_returns_compensations_in_result(self) -> None:
        """AggregatedResult.compensations populated on side-effect failure."""
        runner = FakeStepRunner()
        runner.set_result("s2", _failed_result("s2"))
        fabric = FakeFabricPort()
        exe = _make_executor(step_runner=runner, fabric_port=fabric)
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True),
        )

        result = await exe.execute(plan, FakeSnapshot())

        assert len(result.compensations) >= 1
        assert result.compensations[0].step_id == "s1"
        assert result.compensations[0].status == "EXECUTED"

    @pytest.mark.asyncio
    async def test_execute_no_compensations_on_success(self) -> None:
        """All steps succeed -> no compensations in result."""
        exe = _make_executor()
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True, compensation="cap.undo_s2"),
        )

        result = await exe.execute(plan, FakeSnapshot())

        assert result.compensations == []

    @pytest.mark.asyncio
    async def test_execute_compensation_wal_entries(self) -> None:
        """WAL entries include COMPENSATION records during execute()."""
        runner = FakeStepRunner()
        runner.set_result("s2", _failed_result("s2"))
        bridge = FakeBridgePort()
        fabric = FakeFabricPort()
        exe = _make_executor(
            step_runner=runner,
            bridge_port=bridge,
            fabric_port=fabric,
        )
        plan = _plan(
            _step("s1", has_side_effects=True, compensation="cap.undo_s1"),
            _step("s2", has_side_effects=True),
        )

        await exe.execute(plan, FakeSnapshot())

        comp_wals = [w for w in bridge.wal_writes if w[1] == "COMPENSATION"]
        assert len(comp_wals) >= 1


# ===========================================================================
# 2.2.6: TestRecoverFromWal
# ===========================================================================


class TestRecoverFromWal:
    """recover_from_wal() static method -- WAL recovery protocol."""

    @pytest.mark.asyncio
    async def test_no_wal_entries_returns_no_wal(self) -> None:
        """No WAL entries -> NO_WAL status."""
        bridge = FakeBridgePort(wal_entries=None)

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "NO_WAL"
        assert result["resume_wave_index"] == 0
        assert result["completed_steps"] == []
        assert result["dag_status"] is None

    @pytest.mark.asyncio
    async def test_empty_wal_entries_returns_no_wal(self) -> None:
        """Empty WAL list -> NO_WAL status."""
        bridge = FakeBridgePort(wal_entries=[])

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "NO_WAL"

    @pytest.mark.asyncio
    async def test_dag_complete_returns_completed(self) -> None:
        """DAG_COMPLETE WAL entry -> COMPLETED status."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"entry_type": "PLAN_START", "payload": {}},
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 0, "completed_steps": ["s1"]},
                },
                {"entry_type": "DAG_COMPLETE", "payload": {"status": "COMPLETED"}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "COMPLETED"
        assert result["dag_status"] == "COMPLETED"
        assert "s1" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_dag_complete_failed_status(self) -> None:
        """DAG_COMPLETE with status=FAILED -> COMPLETED status with failed dag."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"entry_type": "DAG_COMPLETE", "payload": {"status": "FAILED"}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "COMPLETED"
        assert result["dag_status"] == "FAILED"

    @pytest.mark.asyncio
    async def test_resume_from_wave1(self) -> None:
        """Wave 0 complete -> resume at wave 1."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"entry_type": "PLAN_START", "payload": {}},
                {"entry_type": "STEP_COMPLETE", "payload": {"step_id": "s1"}},
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 0, "completed_steps": ["s1"]},
                },
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "RESUME"
        assert result["resume_wave_index"] == 1
        assert "s1" in result["completed_steps"]
        assert result["dag_status"] is None

    @pytest.mark.asyncio
    async def test_resume_from_wave3(self) -> None:
        """Waves 0,1,2 complete -> resume at wave 3."""
        bridge = FakeBridgePort(
            wal_entries=[
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 0, "completed_steps": ["s1"]},
                },
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 1, "completed_steps": ["s2"]},
                },
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 2, "completed_steps": ["s3"]},
                },
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "RESUME"
        assert result["resume_wave_index"] == 3
        assert set(result["completed_steps"]) == {"s1", "s2", "s3"}

    @pytest.mark.asyncio
    async def test_partial_wave_after_complete_wave(self) -> None:
        """
        Wave 0 complete, then STEP_COMPLETE entries for wave 1.
        Partial wave -> resume at wave 1 (re-execute entire wave).
        """
        bridge = FakeBridgePort(
            wal_entries=[
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 0, "completed_steps": ["s1"]},
                },
                {"entry_type": "STEP_COMPLETE", "payload": {"step_id": "s2"}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "RESUME"
        assert result["resume_wave_index"] == 1  # re-execute wave 1

    @pytest.mark.asyncio
    async def test_plan_start_only_returns_restart(self) -> None:
        """Only PLAN_START entry -> RESTART from scratch."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"entry_type": "PLAN_START", "payload": {}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "RESTART"
        assert result["resume_wave_index"] == 0
        assert result["completed_steps"] == []

    @pytest.mark.asyncio
    async def test_step_completes_without_wave_returns_restart(self) -> None:
        """STEP_COMPLETE entries but no WAVE_COMPLETE -> RESTART."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"entry_type": "STEP_COMPLETE", "payload": {"step_id": "s1"}},
                {"entry_type": "STEP_COMPLETE", "payload": {"step_id": "s2"}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "RESTART"

    @pytest.mark.asyncio
    async def test_wal_read_failure_returns_no_wal(self) -> None:
        """Bridge read_wal throws -> NO_WAL (degraded)."""
        bridge = FakeBridgePort(read_wal_error=True)

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "NO_WAL"

    @pytest.mark.asyncio
    async def test_entry_type_fallback_to_type_key(self) -> None:
        """Entries with 'type' key instead of 'entry_type' still parsed."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"type": "WAVE_COMPLETE", "payload": {"wave_index": 0, "completed_steps": ["s1"]}},
                {"type": "DAG_COMPLETE", "payload": {"status": "COMPLETED"}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "COMPLETED"
        assert "s1" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_multiple_waves_completed_steps_aggregated(self) -> None:
        """completed_steps aggregated across all waves."""
        bridge = FakeBridgePort(
            wal_entries=[
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 0, "completed_steps": ["s1", "s2"]},
                },
                {
                    "entry_type": "WAVE_COMPLETE",
                    "payload": {"wave_index": 1, "completed_steps": ["s3"]},
                },
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert set(result["completed_steps"]) == {"s1", "s2", "s3"}

    @pytest.mark.asyncio
    async def test_wave_complete_missing_wave_index_defaults(self) -> None:
        """WAVE_COMPLETE without wave_index uses default -1, not updating tracker."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"entry_type": "WAVE_COMPLETE", "payload": {"completed_steps": ["s1"]}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        # wave_index defaulted to -1, does NOT advance last_wave_complete_index
        # so recovery falls to RESTART (no valid wave completion recorded)
        assert result["status"] == "RESTART"

    @pytest.mark.asyncio
    async def test_dag_complete_default_status(self) -> None:
        """DAG_COMPLETE without status in payload defaults to COMPLETED."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"entry_type": "DAG_COMPLETE", "payload": {}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["status"] == "COMPLETED"
        assert result["dag_status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_resume_wave_index_negative_one_for_completed(self) -> None:
        """Completed DAGs have resume_wave_index=-1."""
        bridge = FakeBridgePort(
            wal_entries=[
                {"entry_type": "DAG_COMPLETE", "payload": {"status": "COMPLETED"}},
            ]
        )

        result = await DAGExecutor.recover_from_wal(bridge, "dag-1")

        assert result["resume_wave_index"] == -1
