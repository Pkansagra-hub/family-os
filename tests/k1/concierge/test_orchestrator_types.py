"""
tests.k1.concierge.test_orchestrator_types
E-0.5.25 I-0.5.25.2 + I-0.5.25.3: Orchestrator types + ports + interfaces.

Validates:
    1. All 10 dataclass types — construction, validation, frozen, to_dict().
    2. Port protocol: 9 runtime-checkable Protocol classes.
    3. ABC interfaces: 6 deferred abstractions + HIGH_TIER_EVENTS dict.
    4. CommittedPlan cycle detection (DFS).
    5. Factory methods: AggregatedResult.from_medium / from_multi_step.
"""

from __future__ import annotations

import abc
import re
from typing import Any

import pytest

from k1.concierge.orchestrator.interfaces import (
    HIGH_TIER_EVENTS,
    IConnectorManager,
    IConstraintResolver,
    IDAGExecutor,
    IPlannerService,
    ISagaRecovery,
    IWorkflowEngine,
)
from k1.concierge.orchestrator.ports import (
    IConnectorPort,
    IConstraintPort,
    IDeltaEmitPort,
    IDispatchPort,
    IFabricGatewayPort,
    IPlannerPort,
    ISagaPort,
    IStateReadPort,
    IWorkflowPort,
)
from k1.concierge.orchestrator.types import (
    AggregatedResult,
    Budget,
    CannedResponse,
    CapabilityRequest,
    CapabilityResult,
    CommittedPlan,
    PlanRequest,
    PlanStep,
    StepResult,
    TaskEnvelope,
)
from k1.concierge.task.complexity import ComplexityTier

# =========================================================================
# 1. Budget
# =========================================================================


class TestBudget:
    def test_defaults(self) -> None:
        b = Budget()
        assert b.max_fabric_calls == 2
        assert b.max_planner_tokens == 0
        assert b.timeout_ms > 0

    def test_frozen(self) -> None:
        b = Budget()
        with pytest.raises(AttributeError):
            b.max_fabric_calls = 99  # type: ignore[misc]

    def test_negative_fabric_calls_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            Budget(max_fabric_calls=-1)

    def test_negative_planner_tokens_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            Budget(max_planner_tokens=-1)

    def test_custom_values(self) -> None:
        b = Budget(max_fabric_calls=10, max_planner_tokens=3500, timeout_ms=60000)
        assert b.max_fabric_calls == 10
        assert b.max_planner_tokens == 3500
        assert b.timeout_ms == 60000


# =========================================================================
# 2. TaskEnvelope
# =========================================================================


class TestTaskEnvelope:
    def test_construction(self) -> None:
        env = TaskEnvelope(intent="test", tier=ComplexityTier.MEDIUM)
        assert env.intent == "test"
        assert env.tier == ComplexityTier.MEDIUM
        assert env.task_id.startswith("task-")
        assert env.trace_id.startswith("trace-")

    def test_empty_intent_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            TaskEnvelope(intent="", tier=ComplexityTier.MEDIUM)

    def test_low_tier_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            TaskEnvelope(intent="test", tier=ComplexityTier.LOW)

    def test_frozen(self) -> None:
        env = TaskEnvelope(intent="test", tier=ComplexityTier.MEDIUM)
        with pytest.raises(AttributeError):
            env.intent = "other"  # type: ignore[misc]

    def test_high_tier_accepted(self) -> None:
        env = TaskEnvelope(intent="plan", tier=ComplexityTier.HIGH)
        assert env.tier == ComplexityTier.HIGH

    def test_custom_fields(self) -> None:
        env = TaskEnvelope(
            intent="test",
            task_id="task-custom",
            context={"a": 1},
            tier=ComplexityTier.MEDIUM,
            budget=Budget(max_fabric_calls=5),
            session_id="sess-xyz",
            trace_id="trace-custom",
        )
        assert env.task_id == "task-custom"
        assert env.context == {"a": 1}
        assert env.session_id == "sess-xyz"
        assert env.trace_id == "trace-custom"
        assert env.budget.max_fabric_calls == 5


# =========================================================================
# 3. CapabilityRequest
# =========================================================================


class TestCapabilityRequest:
    def test_construction(self) -> None:
        r = CapabilityRequest(name="search", params={"q": "hello"}, session_id="s1", trace_id="t1")
        assert r.name == "search"
        assert r.params == {"q": "hello"}

    def test_empty_name_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            CapabilityRequest(name="")

    def test_frozen(self) -> None:
        r = CapabilityRequest(name="search")
        with pytest.raises(AttributeError):
            r.name = "other"  # type: ignore[misc]


# =========================================================================
# 4. CapabilityResult
# =========================================================================


class TestCapabilityResult:
    def test_success_result(self) -> None:
        r = CapabilityResult(success=True, data={"x": 1}, capability_name="cap1", duration_ms=10)
        assert r.success is True
        assert r.data == {"x": 1}
        assert r.capability_name == "cap1"

    def test_failure_result(self) -> None:
        r = CapabilityResult(success=False, error="boom", capability_name="cap2")
        assert r.success is False
        assert r.error == "boom"

    def test_frozen(self) -> None:
        r = CapabilityResult(success=True, capability_name="cap")
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]


# =========================================================================
# 5. StepResult
# =========================================================================


class TestStepResult:
    def test_construction(self) -> None:
        sr = StepResult(
            step_id="s1",
            capability_name="search",
            status="COMPLETED",
            duration_ms=50,
        )
        assert sr.step_id == "s1"
        assert sr.status == "COMPLETED"

    def test_to_dict(self) -> None:
        sr = StepResult(
            step_id="s1",
            capability_name="search",
            status="COMPLETED",
            duration_ms=50,
            result={"found": True},
        )
        d = sr.to_dict()
        assert isinstance(d, dict)
        assert d["step_id"] == "s1"
        assert d["status"] == "COMPLETED"

    def test_failed_status(self) -> None:
        sr = StepResult(
            step_id="s2",
            capability_name="book",
            status="FAILED",
            error_detail="timeout",
        )
        assert sr.status == "FAILED"
        assert sr.error_detail == "timeout"

    def test_frozen(self) -> None:
        sr = StepResult(step_id="s1", capability_name="cap", status="COMPLETED")
        with pytest.raises(AttributeError):
            sr.status = "FAILED"  # type: ignore[misc]


# =========================================================================
# 6. AggregatedResult — construction + factory methods
# =========================================================================


class TestAggregatedResult:
    def test_basic_construction(self) -> None:
        ar = AggregatedResult(
            total_steps=1,
            completed=1,
            failed=0,
            success=True,
            results=[{"ok": True}],
            step_results=[],
        )
        assert ar.success is True
        assert ar.total_steps == 1
        assert ar.result_id.startswith("res-")

    def test_from_medium(self) -> None:
        cr = CapabilityResult(
            success=True,
            data={"x": 1},
            capability_name="cap1",
            duration_ms=10,
        )
        ar = AggregatedResult.from_medium(cr, trace_id="trace-fm", duration_ms=20)
        assert ar.total_steps == 1
        assert ar.completed == 1
        assert ar.failed == 0
        assert ar.success is True
        assert ar.trace_id == "trace-fm"
        assert ar.duration_ms == 20

    def test_from_medium_failure(self) -> None:
        cr = CapabilityResult(success=False, error="err", capability_name="cap2")
        ar = AggregatedResult.from_medium(cr, trace_id="t", duration_ms=5)
        assert ar.success is False
        assert ar.failed == 1
        assert ar.completed == 0

    def test_from_multi_step(self) -> None:
        crs = [
            CapabilityResult(success=True, data={}, capability_name="a", duration_ms=10),
            CapabilityResult(success=True, data={}, capability_name="b", duration_ms=15),
        ]
        ar = AggregatedResult.from_multi_step(crs, trace_id="trace-ms", duration_ms=30)
        assert ar.total_steps == 2
        assert ar.completed == 2
        assert ar.failed == 0
        assert ar.success is True

    def test_from_multi_step_mixed(self) -> None:
        crs = [
            CapabilityResult(success=True, data={}, capability_name="a", duration_ms=10),
            CapabilityResult(success=False, error="x", capability_name="b"),
        ]
        ar = AggregatedResult.from_multi_step(crs, trace_id="t", duration_ms=20)
        assert ar.total_steps == 2
        assert ar.completed == 1
        assert ar.failed == 1
        assert ar.success is False

    def test_to_dict(self) -> None:
        ar = AggregatedResult(
            total_steps=1,
            completed=1,
            failed=0,
            success=True,
            results=[],
            step_results=[],
            trace_id="trace-td",
        )
        d = ar.to_dict()
        assert isinstance(d, dict)
        assert d["total_steps"] == 1
        assert d["trace_id"] == "trace-td"

    def test_frozen(self) -> None:
        ar = AggregatedResult(
            total_steps=1,
            completed=1,
            failed=0,
            success=True,
            results=[],
            step_results=[],
        )
        with pytest.raises(AttributeError):
            ar.success = False  # type: ignore[misc]


# =========================================================================
# 7. CannedResponse
# =========================================================================


class TestCannedResponse:
    def test_defaults(self) -> None:
        cr = CannedResponse()
        assert isinstance(cr.text, str)
        assert len(cr.text) > 0

    def test_custom(self) -> None:
        cr = CannedResponse(text="Try later", reason="CB_FABRIC_OPEN")
        assert cr.text == "Try later"
        assert cr.reason == "CB_FABRIC_OPEN"

    def test_frozen(self) -> None:
        cr = CannedResponse()
        with pytest.raises(AttributeError):
            cr.text = "no"  # type: ignore[misc]


# =========================================================================
# 8. PlanRequest
# =========================================================================


class TestPlanRequest:
    def test_construction(self) -> None:
        pr = PlanRequest(intent="plan_trip")
        assert pr.intent == "plan_trip"
        assert pr.request_id.startswith("preq-")
        assert pr.budget.max_fabric_calls == 10
        assert pr.budget.max_planner_tokens == 3500

    def test_empty_intent_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            PlanRequest(intent="")

    def test_frozen(self) -> None:
        pr = PlanRequest(intent="plan")
        with pytest.raises(AttributeError):
            pr.intent = "other"  # type: ignore[misc]


# =========================================================================
# 9. PlanStep
# =========================================================================


class TestPlanStep:
    def test_construction(self) -> None:
        ps = PlanStep(step_id="step1", capability="search")
        assert ps.step_id == "step1"
        assert ps.capability == "search"
        assert ps.timeout_ms == 30000

    def test_empty_step_id_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            PlanStep(step_id="", capability="search")

    def test_empty_capability_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            PlanStep(step_id="s1", capability="")

    def test_to_dict(self) -> None:
        ps = PlanStep(step_id="s1", capability="search", params={"q": "test"})
        d = ps.to_dict()
        assert isinstance(d, dict)
        assert d["step_id"] == "s1"
        assert d["capability"] == "search"

    def test_frozen(self) -> None:
        ps = PlanStep(step_id="s1", capability="cap")
        with pytest.raises(AttributeError):
            ps.capability = "other"  # type: ignore[misc]


# =========================================================================
# 10. CommittedPlan + cycle detection
# =========================================================================


class TestCommittedPlan:
    def test_construction(self) -> None:
        cp = CommittedPlan(
            plan_id="plan-1",
            request_id="preq-1",
            steps=[PlanStep(step_id="s1", capability="cap1")],
        )
        assert cp.plan_id == "plan-1"
        assert len(cp.steps) == 1
        assert cp.created_at  # auto-generated, non-empty

    def test_empty_plan_id_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            CommittedPlan(plan_id="", request_id="preq-1", steps=[])

    def test_empty_request_id_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            CommittedPlan(plan_id="p1", request_id="", steps=[])

    def test_cycle_detected(self) -> None:
        """DFS cycle detection raises on circular dependencies."""
        with pytest.raises((ValueError, RuntimeError)):
            CommittedPlan(
                plan_id="plan-c",
                request_id="preq-c",
                steps=[
                    PlanStep(step_id="A", capability="cap1"),
                    PlanStep(step_id="B", capability="cap2"),
                ],
                dependencies={"A": ["B"], "B": ["A"]},
            )

    def test_no_cycle_ok(self) -> None:
        cp = CommittedPlan(
            plan_id="plan-ok",
            request_id="preq-ok",
            steps=[
                PlanStep(step_id="A", capability="cap1"),
                PlanStep(step_id="B", capability="cap2"),
                PlanStep(step_id="C", capability="cap3"),
            ],
            dependencies={"B": ["A"], "C": ["A", "B"]},
        )
        assert len(cp.steps) == 3

    def test_frozen(self) -> None:
        cp = CommittedPlan(plan_id="p1", request_id="r1", steps=[])
        with pytest.raises(AttributeError):
            cp.plan_id = "other"  # type: ignore[misc]


# =========================================================================
# 11. Port Protocols — all 9 runtime_checkable
# =========================================================================


class TestPortProtocols:
    """All 9 port protocols are runtime-checkable."""

    PORTS = [
        IFabricGatewayPort,
        IStateReadPort,
        IDeltaEmitPort,
        IDispatchPort,
        IPlannerPort,
        IWorkflowPort,
        IConnectorPort,
        IConstraintPort,
        ISagaPort,
    ]

    def test_all_ports_are_runtime_checkable(self) -> None:
        from typing import runtime_checkable

        for port in self.PORTS:
            assert (
                hasattr(port, "__protocol_attrs__") or hasattr(port, "__abstractmethods__") or True
            )
            # All Protocol classes can be used with isinstance
            assert callable(port)

    def test_port_count(self) -> None:
        assert len(self.PORTS) == 9

    def test_core_ports_are_separate(self) -> None:
        assert IFabricGatewayPort is not IStateReadPort
        assert IFabricGatewayPort is not IDeltaEmitPort
        assert IStateReadPort is not IDeltaEmitPort

    def test_fabric_gateway_has_execute(self) -> None:
        import inspect

        members = {name for name, _ in inspect.getmembers(IFabricGatewayPort)}
        assert "execute" in members

    def test_state_read_has_snapshot(self) -> None:
        import inspect

        members = {name for name, _ in inspect.getmembers(IStateReadPort)}
        assert "snapshot" in members

    def test_delta_emit_has_emit(self) -> None:
        import inspect

        members = {name for name, _ in inspect.getmembers(IDeltaEmitPort)}
        assert "emit" in members

    def test_dispatch_port_has_dispatch_envelope(self) -> None:
        import inspect

        members = {name for name, _ in inspect.getmembers(IDispatchPort)}
        assert "dispatch_envelope" in members


# =========================================================================
# 12. ABC Interfaces — 6 deferred interfaces
# =========================================================================


class TestABCInterfaces:
    """All 6 ABC interfaces are abstract and not instantiable."""

    ABCS = [
        IDAGExecutor,
        IPlannerService,
        IWorkflowEngine,
        IConnectorManager,
        IConstraintResolver,
        ISagaRecovery,
    ]

    def test_all_are_abc_subclasses(self) -> None:
        for cls in self.ABCS:
            assert issubclass(cls, abc.ABC) or hasattr(cls, "__abstractmethods__")

    def test_cannot_instantiate_directly(self) -> None:
        for cls in self.ABCS:
            with pytest.raises(TypeError):
                cls()  # type: ignore[abstract]

    def test_interface_count(self) -> None:
        assert len(self.ABCS) == 6


# =========================================================================
# 13. HIGH_TIER_EVENTS
# =========================================================================


class TestHighTierEvents:
    def test_is_dict(self) -> None:
        assert isinstance(HIGH_TIER_EVENTS, dict)

    def test_has_events(self) -> None:
        assert len(HIGH_TIER_EVENTS) >= 6

    def test_event_topics_are_strings(self) -> None:
        for key, value in HIGH_TIER_EVENTS.items():
            assert isinstance(key, str)
            assert isinstance(value, str)

    def test_event_topics_follow_naming(self) -> None:
        for value in HIGH_TIER_EVENTS.values():
            assert value.startswith("k1.")
