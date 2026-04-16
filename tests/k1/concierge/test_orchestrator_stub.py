"""
tests.k1.concierge.test_orchestrator_stub
E-0.5.25 I-0.5.25.1: OrchestratorStub + routing tests.

Validates:
    1. OrchestratorStub.handle_task() 6-step flow (emit acceptance, read,
       resolve, execute, aggregate, emit completion).
    2. OrchestratorStub.handle_multi_step() with 1-2 capabilities.
    3. Budget enforcement (ORCH-10): BudgetExceededError on overflow.
    4. Structural invariants (ORCH-01..04): no write, no LLM, no tools.
    5. route_task / route_task_sync: LOW/MEDIUM/HIGH dispatch records.
    6. route_task_with_degradation: CB cascade HIGH→MED→LOW→canned.
    7. get_effective_tier: tier downgrade logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from k1.concierge.orchestrator.ports import IDeltaEmitPort, IFabricGatewayPort, IStateReadPort
from k1.concierge.orchestrator.stub import BudgetExceededError, OrchestratorStub
from k1.concierge.orchestrator.types import (
    AggregatedResult,
    Budget,
    CapabilityRequest,
    CapabilityResult,
    TaskEnvelope,
)
from k1.concierge.task.complexity import ComplexityTier

# =========================================================================
# Test adapters implementing port protocols
# =========================================================================


class FakeFabricGateway:
    """Minimal IFabricGatewayPort that records calls and returns canned result."""

    def __init__(self, result: CapabilityResult | None = None) -> None:
        self.calls: list[CapabilityRequest] = []
        self._result = result or CapabilityResult(
            success=True,
            data={"answer": "42"},
            capability_name="test_cap",
            duration_ms=10,
        )

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        self.calls.append(request)
        return self._result

    async def execute_batch(self, requests: list[CapabilityRequest]) -> list[CapabilityResult]:
        results = []
        for r in requests:
            results.append(await self.execute(r))
        return results


class FakeStateRead:
    """Minimal IStateReadPort returning empty snapshots."""

    def __init__(self, snapshot_data: dict | None = None) -> None:
        self._data = snapshot_data or {}
        self.snapshot_calls: list[list[str]] = []

    async def snapshot(self, sections: list[str]) -> dict[str, Any]:
        self.snapshot_calls.append(sections)
        return {s: self._data.get(s, {}) for s in sections}

    async def read_section(self, session_id: str, section: str) -> dict | None:
        return self._data.get(section)


class FakeDeltaEmit:
    """Minimal IDeltaEmitPort that records emitted events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Any, str]] = []

    async def emit(self, event_topic: str, payload: Any, trace_id: str = "") -> None:
        self.events.append((event_topic, payload, trace_id))


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def fabric() -> FakeFabricGateway:
    return FakeFabricGateway()


@pytest.fixture
def state() -> FakeStateRead:
    return FakeStateRead()


@pytest.fixture
def delta() -> FakeDeltaEmit:
    return FakeDeltaEmit()


@pytest.fixture
def stub(fabric: FakeFabricGateway, state: FakeStateRead, delta: FakeDeltaEmit) -> OrchestratorStub:
    return OrchestratorStub(fabric_gateway=fabric, state_read=state, delta_emit=delta)


@pytest.fixture
def medium_envelope() -> TaskEnvelope:
    return TaskEnvelope(
        intent="book_hotel",
        task_id="task-test001",
        context={"params": {"city": "Paris"}},
        tier=ComplexityTier.MEDIUM,
        budget=Budget(max_fabric_calls=2),
        session_id="sess-1",
        trace_id="trace-001",
    )


# =========================================================================
# 1. OrchestratorStub — handle_task 6-step flow
# =========================================================================


class TestHandleTask:
    """OrchestratorStub.handle_task() executes the 6-step MEDIUM flow."""

    async def test_returns_aggregated_result(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope
    ) -> None:
        result = await stub.handle_task(medium_envelope)
        assert isinstance(result, AggregatedResult)

    async def test_result_is_successful(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope
    ) -> None:
        result = await stub.handle_task(medium_envelope)
        assert result.success is True
        assert result.total_steps == 1
        assert result.completed == 1
        assert result.failed == 0

    async def test_emits_acceptance_event(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope, delta: FakeDeltaEmit
    ) -> None:
        await stub.handle_task(medium_envelope)
        acceptance = delta.events[0]
        assert acceptance[0] == "k1.orchestration.task.accepted"
        assert acceptance[1]["task_id"] == "task-test001"
        assert acceptance[1]["tier"] == "MEDIUM"

    async def test_emits_completion_event(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope, delta: FakeDeltaEmit
    ) -> None:
        await stub.handle_task(medium_envelope)
        completion = delta.events[-1]
        assert completion[0] == "k1.orchestration.dag.completed"
        assert completion[1]["task_id"] == "task-test001"
        assert completion[1]["success"] is True

    async def test_reads_context_snapshot(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope, state: FakeStateRead
    ) -> None:
        await stub.handle_task(medium_envelope)
        assert len(state.snapshot_calls) == 1
        assert "beliefs_active" in state.snapshot_calls[0]
        assert "task_artifacts" in state.snapshot_calls[0]

    async def test_executes_via_fabric(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope, fabric: FakeFabricGateway
    ) -> None:
        await stub.handle_task(medium_envelope)
        assert len(fabric.calls) == 1
        assert fabric.calls[0].name == "book_hotel"
        assert fabric.calls[0].params == {"city": "Paris"}
        assert fabric.calls[0].session_id == "sess-1"
        assert fabric.calls[0].trace_id == "trace-001"

    async def test_fabric_call_count_tracked(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope
    ) -> None:
        assert stub.fabric_call_count == 0
        await stub.handle_task(medium_envelope)
        assert stub.fabric_call_count == 1

    async def test_handles_fabric_failure(self, state: FakeStateRead, delta: FakeDeltaEmit) -> None:
        fail_result = CapabilityResult(
            success=False, error="Fabric timeout", capability_name="book_hotel", duration_ms=5000
        )
        fabric = FakeFabricGateway(result=fail_result)
        stub = OrchestratorStub(fabric_gateway=fabric, state_read=state, delta_emit=delta)
        envelope = TaskEnvelope(
            intent="book_hotel",
            tier=ComplexityTier.MEDIUM,
            budget=Budget(max_fabric_calls=2),
        )
        result = await stub.handle_task(envelope)
        assert result.success is False
        assert result.failed == 1
        assert result.completed == 0

    async def test_result_trace_id_matches(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope
    ) -> None:
        result = await stub.handle_task(medium_envelope)
        assert result.trace_id == "trace-001"

    async def test_result_has_step_results(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope
    ) -> None:
        result = await stub.handle_task(medium_envelope)
        assert len(result.step_results) == 1
        assert result.step_results[0].capability_name == "test_cap"
        assert result.step_results[0].status == "COMPLETED"


# =========================================================================
# 2. OrchestratorStub — handle_multi_step
# =========================================================================


class TestHandleMultiStep:
    """OrchestratorStub.handle_multi_step() executes multiple Fabric calls."""

    async def test_two_capabilities(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope, fabric: FakeFabricGateway
    ) -> None:
        result = await stub.handle_multi_step(medium_envelope, ["search", "book"])
        assert result.total_steps == 2
        assert result.completed == 2
        assert result.success is True
        assert len(fabric.calls) == 2

    async def test_single_capability(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope
    ) -> None:
        result = await stub.handle_multi_step(medium_envelope, ["search"])
        assert result.total_steps == 1
        assert result.completed == 1

    async def test_budget_exceeded_raises(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope
    ) -> None:
        with pytest.raises(BudgetExceededError) as exc_info:
            await stub.handle_multi_step(medium_envelope, ["a", "b", "c"])
        assert exc_info.value.max_calls == 2
        assert exc_info.value.attempted == 3

    async def test_emits_acceptance_and_completion(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope, delta: FakeDeltaEmit
    ) -> None:
        await stub.handle_multi_step(medium_envelope, ["search", "book"])
        topics = [e[0] for e in delta.events]
        assert topics[0] == "k1.orchestration.task.accepted"
        assert topics[-1] == "k1.orchestration.dag.completed"

    async def test_partial_failure(self, state: FakeStateRead, delta: FakeDeltaEmit) -> None:
        """Second call fails — result reflects mixed success/failure."""
        call_count = 0

        async def alternating_execute(request: CapabilityRequest) -> CapabilityResult:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return CapabilityResult(success=False, error="oops", capability_name=request.name)
            return CapabilityResult(success=True, data={"ok": True}, capability_name=request.name)

        fabric = FakeFabricGateway()
        fabric.execute = alternating_execute  # type: ignore[assignment]
        stub = OrchestratorStub(fabric_gateway=fabric, state_read=state, delta_emit=delta)
        envelope = TaskEnvelope(
            intent="multi",
            tier=ComplexityTier.MEDIUM,
            budget=Budget(max_fabric_calls=2),
        )
        result = await stub.handle_multi_step(envelope, ["cap1", "cap2"])
        assert result.total_steps == 2
        assert result.completed == 1
        assert result.failed == 1
        assert result.success is False


# =========================================================================
# 3. Budget enforcement (ORCH-10)
# =========================================================================


class TestBudgetEnforcement:
    """ORCH-10: max Fabric calls per budget."""

    async def test_single_call_within_budget(
        self, stub: OrchestratorStub, medium_envelope: TaskEnvelope
    ) -> None:
        await stub.handle_task(medium_envelope)
        assert stub.fabric_call_count == 1

    async def test_budget_exceeded_error_fields(self) -> None:
        err = BudgetExceededError(max_calls=2, attempted=3)
        assert err.max_calls == 2
        assert err.attempted == 3
        assert "ORCH-10" in str(err)

    async def test_budget_one_call_limit(self, state: FakeStateRead, delta: FakeDeltaEmit) -> None:
        """Budget with max_fabric_calls=1 blocks second call in multi-step."""
        fabric = FakeFabricGateway()
        stub = OrchestratorStub(fabric_gateway=fabric, state_read=state, delta_emit=delta)
        envelope = TaskEnvelope(
            intent="test",
            tier=ComplexityTier.MEDIUM,
            budget=Budget(max_fabric_calls=1),
        )
        with pytest.raises(BudgetExceededError):
            await stub.handle_multi_step(envelope, ["a", "b"])


# =========================================================================
# 4. Structural invariants (ORCH-01..04)
# =========================================================================


class TestStructuralInvariants:
    """Verify ORCH-01..04 are enforced structurally."""

    def test_orch01_no_write_port(self) -> None:
        """OrchestratorStub has no write port — state_read is read-only."""
        import inspect

        params = inspect.signature(OrchestratorStub.__init__).parameters
        param_names = set(params.keys()) - {"self"}
        assert param_names == {"fabric_gateway", "state_read", "delta_emit"}
        # No "state_write" or similar
        assert "state_write" not in param_names

    def test_orch02_no_llm_port(self) -> None:
        """OrchestratorStub constructor has no LLM/model port."""
        import inspect

        params = inspect.signature(OrchestratorStub.__init__).parameters
        for name in params:
            assert "model" not in name.lower()
            assert "llm" not in name.lower()

    def test_orch03_no_tool_port(self) -> None:
        """OrchestratorStub constructor has no ToolDispatcher port."""
        import inspect

        params = inspect.signature(OrchestratorStub.__init__).parameters
        for name in params:
            assert "tool" not in name.lower()
            assert "dispatcher" not in name.lower()

    def test_orch04_only_fabric_execution(self, stub: OrchestratorStub) -> None:
        """Only self.fabric exists for execution (IFabricGatewayPort)."""
        assert hasattr(stub, "fabric")
        assert hasattr(stub, "state")
        assert hasattr(stub, "delta")

    def test_port_protocol_compliance(self) -> None:
        """Test adapters satisfy port protocols."""
        fg = FakeFabricGateway()
        sr = FakeStateRead()
        de = FakeDeltaEmit()
        assert isinstance(fg, IFabricGatewayPort)
        assert isinstance(sr, IStateReadPort)
        assert isinstance(de, IDeltaEmitPort)


# =========================================================================
# 5. Routing: route_task_sync — LOW/MEDIUM/HIGH dispatch records
# =========================================================================


class TestRouteTaskSync:
    """route_task_sync produces correct dispatch records."""

    def _make_task(self, intent: str = "search") -> Any:
        from k1.concierge.task.dispatch import TaskDispatch
        from k1.concierge.task.intent import TaskIntent

        return TaskDispatch(
            intents=[TaskIntent(action=intent)],
            tier=ComplexityTier.LOW,
            task_id="task-routing01",
        )

    def test_low_tier_dispatch(self) -> None:
        from k1.concierge.orchestrator.routing import route_task_sync

        task = self._make_task()
        record = route_task_sync(task, ComplexityTier.LOW)
        assert record.tier == ComplexityTier.LOW
        assert record.topic == "k1.orchestration.task.dispatch.v1"
        assert record.payload is task
        assert record.envelope is None

    def test_medium_tier_dispatch(self) -> None:
        from k1.concierge.orchestrator.routing import route_task_sync

        task = self._make_task("book_hotel")
        record = route_task_sync(task, ComplexityTier.MEDIUM)
        assert record.tier == ComplexityTier.MEDIUM
        assert record.envelope is not None
        assert record.envelope.intent == "book_hotel"
        assert record.envelope.tier == ComplexityTier.MEDIUM
        assert record.envelope.task_id == "task-routing01"

    def test_high_tier_dispatch(self) -> None:
        from k1.concierge.orchestrator.routing import route_task_sync

        task = self._make_task("plan_trip")
        record = route_task_sync(task, ComplexityTier.HIGH)
        assert record.tier == ComplexityTier.HIGH
        assert record.envelope is not None
        assert record.envelope.intent == "plan_trip"
        assert record.envelope.tier == ComplexityTier.HIGH

    def test_medium_envelope_has_budget(self) -> None:
        from k1.concierge.orchestrator.routing import route_task_sync

        task = self._make_task()
        record = route_task_sync(task, ComplexityTier.MEDIUM)
        assert record.envelope is not None
        assert record.envelope.budget.max_fabric_calls >= 1

    def test_high_envelope_has_planner_tokens(self) -> None:
        from k1.concierge.orchestrator.routing import route_task_sync

        task = self._make_task()
        record = route_task_sync(task, ComplexityTier.HIGH)
        assert record.envelope is not None
        assert record.envelope.budget.max_planner_tokens > 0


class TestRouteTaskAsync:
    """route_task (async) calls emit_fn or dispatch_fn based on tier."""

    def _make_task(self, intent: str = "search") -> Any:
        from k1.concierge.task.dispatch import TaskDispatch
        from k1.concierge.task.intent import TaskIntent

        return TaskDispatch(
            intents=[TaskIntent(action=intent)],
            tier=ComplexityTier.LOW,
            task_id="task-routing02",
        )

    async def test_low_tier_calls_emit_fn(self) -> None:
        from k1.concierge.orchestrator.routing import route_task

        emit = AsyncMock()
        task = self._make_task()
        record = await route_task(task, ComplexityTier.LOW, emit_fn=emit)
        assert record.tier == ComplexityTier.LOW
        emit.assert_called_once()

    async def test_medium_tier_calls_dispatch_fn(self) -> None:
        from k1.concierge.orchestrator.routing import route_task

        dispatch = AsyncMock()
        task = self._make_task("book")
        record = await route_task(task, ComplexityTier.MEDIUM, dispatch_fn=dispatch)
        assert record.tier == ComplexityTier.MEDIUM
        dispatch.assert_called_once()

    async def test_low_tier_no_emit_fn_ok(self) -> None:
        from k1.concierge.orchestrator.routing import route_task

        task = self._make_task()
        record = await route_task(task, ComplexityTier.LOW)
        assert record.tier == ComplexityTier.LOW


# =========================================================================
# 6. Degradation: route_task_with_degradation
# =========================================================================


class TestDegradationCascade:
    """route_task_with_degradation downgrades on open circuit breakers."""

    def _make_task(self) -> Any:
        from k1.concierge.task.dispatch import TaskDispatch
        from k1.concierge.task.intent import TaskIntent

        return TaskDispatch(
            intents=[TaskIntent(action="test")],
            tier=ComplexityTier.LOW,
            task_id="task-degrade01",
        )

    def _reset_cbs(self) -> None:
        from k1.concierge.orchestrator.degradation import cb_fabric, cb_orchestrator, cb_planner

        cb_planner.reset()
        cb_orchestrator.reset()
        cb_fabric.reset()

    async def test_no_degradation_when_all_closed(self) -> None:
        from k1.concierge.orchestrator.degradation import get_effective_tier

        self._reset_cbs()
        assert get_effective_tier(ComplexityTier.HIGH) == ComplexityTier.HIGH
        assert get_effective_tier(ComplexityTier.MEDIUM) == ComplexityTier.MEDIUM
        assert get_effective_tier(ComplexityTier.LOW) == ComplexityTier.LOW

    async def test_high_degrades_to_medium(self) -> None:
        from k1.concierge.orchestrator.degradation import cb_planner, get_effective_tier

        self._reset_cbs()
        cb_planner.trip()
        assert get_effective_tier(ComplexityTier.HIGH) == ComplexityTier.MEDIUM

    async def test_medium_degrades_to_low(self) -> None:
        from k1.concierge.orchestrator.degradation import cb_orchestrator, get_effective_tier

        self._reset_cbs()
        cb_orchestrator.trip()
        assert get_effective_tier(ComplexityTier.MEDIUM) == ComplexityTier.LOW

    async def test_low_degrades_to_none(self) -> None:
        from k1.concierge.orchestrator.degradation import cb_fabric, get_effective_tier

        self._reset_cbs()
        cb_fabric.trip()
        assert get_effective_tier(ComplexityTier.LOW) is None

    async def test_full_cascade_high_to_none(self) -> None:
        from k1.concierge.orchestrator.degradation import (
            cb_fabric,
            cb_orchestrator,
            cb_planner,
            get_effective_tier,
        )

        self._reset_cbs()
        cb_planner.trip()
        cb_orchestrator.trip()
        cb_fabric.trip()
        assert get_effective_tier(ComplexityTier.HIGH) is None

    async def test_route_with_degradation_returns_canned(self) -> None:
        from k1.concierge.orchestrator.degradation import cb_fabric, route_task_with_degradation
        from k1.concierge.orchestrator.types import CannedResponse

        self._reset_cbs()
        cb_fabric.trip()
        task = self._make_task()
        result = await route_task_with_degradation(task, ComplexityTier.LOW)
        assert isinstance(result, CannedResponse)
        assert result.reason == "CB_FABRIC_OPEN"

    async def test_route_with_degradation_normal_returns_record(self) -> None:
        from k1.concierge.orchestrator.degradation import route_task_with_degradation
        from k1.concierge.orchestrator.routing import DispatchRecord

        self._reset_cbs()
        emit = AsyncMock()
        task = self._make_task()
        result = await route_task_with_degradation(task, ComplexityTier.LOW, emit_fn=emit)
        assert isinstance(result, DispatchRecord)
        assert result.tier == ComplexityTier.LOW


# =========================================================================
# 7. DispatchRecord + routing constants
# =========================================================================


class TestDispatchRecord:
    """DispatchRecord data class correctness."""

    def test_default_values(self) -> None:
        from k1.concierge.orchestrator.routing import DispatchRecord

        record = DispatchRecord(tier=ComplexityTier.LOW)
        assert record.topic == ""
        assert record.envelope is None
        assert record.payload is None
        assert record.priority == "INTERACTIVE"

    def test_tier_budget_constants(self) -> None:
        from k1.concierge.orchestrator.routing import TIER_FABRIC_BUDGET, TIER_PLANNER_TOKEN_BUDGET

        assert TIER_FABRIC_BUDGET[ComplexityTier.LOW] == 1
        assert TIER_FABRIC_BUDGET[ComplexityTier.MEDIUM] == 2
        assert TIER_FABRIC_BUDGET[ComplexityTier.HIGH] == 10
        assert TIER_PLANNER_TOKEN_BUDGET[ComplexityTier.LOW] == 0
        assert TIER_PLANNER_TOKEN_BUDGET[ComplexityTier.MEDIUM] == 0
        assert TIER_PLANNER_TOKEN_BUDGET[ComplexityTier.HIGH] == 3500
