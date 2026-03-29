"""Epic 7.3A.2 -- Error classification + severity reporting end-to-end.

Scope under test:
  - Orchestrator classifies adapter errors and returns process outcome.
  - ErrorRouter emits diagnostic deltas with adapter/severity/error_code/trace_id.
  - Concierge owns tier degradation decisions (not asserted here).

All orchestration dispatch in this suite goes through OrchestratorService.process().
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from k1.fabric.circuit_breaker.breaker import CircuitBreaker, CircuitBreakerConfig
from k1.fabric.types import CapabilityResult
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_ERROR_ROUTED, ORCH_PLAN_REQUESTED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    AdapterError,
    CommittedPlan,
    ErrorSeverity,
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TaskEnvelope,
)


class _PlannerMailboxStub:
    """Minimal mailbox stub for PlannerAdapter tests."""

    def __init__(self) -> None:
        self.enqueued: list = []
        self.cancelled: list[str] = []

    async def enqueue(self, request) -> None:
        self.enqueued.append(request)

    async def send_cancel(self, request_id: str) -> None:
        self.cancelled.append(request_id)

    async def micro_replan(self, request):
        return None


def _high_envelope(*, trace_id: str | None = None) -> TaskEnvelope:
    return TaskEnvelope(
        intent="severity-e2e",
        trace_id=trace_id or str(uuid4()),
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": "s-severity"},
    )


def _medium_envelope(*, capability: str, trace_id: str | None = None) -> TaskEnvelope:
    return TaskEnvelope(
        intent="severity-e2e-medium",
        trace_id=trace_id or str(uuid4()),
        tier="MEDIUM",
        capabilities=[capability],
        params={capability: {}},
        context={"session_id": "s-severity"},
    )


def _register_capability(fabric, name: str) -> None:
    fabric.register_capability(
        name,
        RegistryEntry(
            name=name,
            provider_type="mock",
            safety_band_min="GREEN",
            availability="AVAILABLE",
            estimated_duration_ms=100,
        ),
    )


def _single_step_plan(*, request_id: str, trace_id: str, capability: str) -> CommittedPlan:
    return CommittedPlan(
        plan_id=f"severity-plan-{uuid4()}",
        request_id=request_id,
        intent="severity-e2e",
        steps=[PlanStep(id="s1", capability=capability)],
        trace_id=trace_id,
    )


async def _wait_until(predicate, *, timeout_s: float = 2.0, step_s: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for async condition")


async def _wait_for_error_routed(delta, *, baseline: int) -> dict:
    await _wait_until(lambda: len(delta.get_emitted(ORCH_ERROR_ROUTED)) > baseline)
    return delta.get_emitted(ORCH_ERROR_ROUTED)[-1]


class TestErrorSeverityE2E:
    @pytest.mark.asyncio
    async def test_planner_cb_open_returns_failed_not_degraded(self) -> None:
        mailbox = _PlannerMailboxStub()
        cb = CircuitBreaker("planner", CircuitBreakerConfig())
        cb.trip()  # force OPEN
        planner = PlannerAdapter(mailbox, cb)

        service = await OrchestratorFactory.create_for_testing(overrides={"planner": planner})
        trace_id = str(uuid4())
        result = await service.process(_high_envelope(trace_id=trace_id))

        assert result == ProcessResult.FAILED
        assert mailbox.enqueued == []
        assert len(service._delta_port.get_emitted(ORCH_PLAN_REQUESTED)) == 0  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_fabric_circuit_open_like_error_returns_failed(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        fabric = service._fabric_port
        delta = service._delta_port

        capability = "tool.severity.fabric"
        _register_capability(fabric, capability)

        trace_id = str(uuid4())
        fabric.script_error(
            capability,
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="fabric_gateway",
                operation="execute",
                error_code="FABRIC_UNAVAILABLE",
                error_message="CB_FABRIC open",
                trace_id=trace_id,
            ),
        )

        result = await service.process(_medium_envelope(capability=capability, trace_id=trace_id))
        assert result == ProcessResult.FAILED

        completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert len(completed) == 1
        payload = completed[0]
        assert payload["failed"] == 1
        assert payload["trace_id"] == trace_id
        assert payload["step_results"][0]["error_detail"] == "CB_FABRIC open"

    @pytest.mark.asyncio
    async def test_planner_classification_diagnostic_delta_contains_concierge_fields(self) -> None:
        trace_id = str(uuid4())
        mailbox = _PlannerMailboxStub()
        cb = CircuitBreaker("planner", CircuitBreakerConfig())
        cb.trip()
        planner = PlannerAdapter(mailbox, cb)
        service = await OrchestratorFactory.create_for_testing(overrides={"planner": planner})
        delta = service._delta_port

        baseline = len(delta.get_emitted(ORCH_ERROR_ROUTED))
        assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.FAILED
        payload = await _wait_for_error_routed(delta, baseline=baseline)
        assert payload["adapter"] == "planner"
        assert payload["severity"] == "DEGRADED"
        assert payload["error_code"] == "CB_PLANNER_OPEN"
        assert payload["trace_id"] == trace_id
        assert payload["action"] == "FALLBACK"

    @pytest.mark.asyncio
    async def test_fabric_classification_diagnostic_delta_contains_concierge_fields(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        delta = service._delta_port
        fabric = service._fabric_port
        trace_id = str(uuid4())

        capability = "tool.severity.fabric.delta"
        _register_capability(fabric, capability)
        fabric.script_error(
            capability,
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="fabric_gateway",
                operation="execute",
                error_code="FABRIC_UNAVAILABLE",
                error_message="CB_FABRIC open",
                trace_id=trace_id,
            ),
        )

        baseline = len(delta.get_emitted(ORCH_ERROR_ROUTED))
        assert (
            await service.process(_medium_envelope(capability=capability, trace_id=trace_id))
            == ProcessResult.FAILED
        )
        payload = await _wait_for_error_routed(delta, baseline=baseline)

        assert payload["adapter"] == "fabric_gateway"
        assert payload["severity"] == "DEGRADED"
        assert payload["error_code"] == "FABRIC_UNAVAILABLE"
        assert payload["trace_id"] == trace_id
        assert payload["action"] == "DEGRADE"

    @pytest.mark.asyncio
    async def test_orch09_trace_id_propagated_in_error_diagnostic_deltas(self) -> None:
        trace_id = str(uuid4())

        # planner path
        mailbox = _PlannerMailboxStub()
        cb = CircuitBreaker("planner", CircuitBreakerConfig())
        cb.trip()
        planner = PlannerAdapter(mailbox, cb)
        service = await OrchestratorFactory.create_for_testing(overrides={"planner": planner})
        delta = service._delta_port
        baseline = len(delta.get_emitted(ORCH_ERROR_ROUTED))
        assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.FAILED
        await _wait_for_error_routed(delta, baseline=baseline)

        # fabric path
        capability = "tool.severity.fabric.trace"
        fabric = service._fabric_port
        _register_capability(fabric, capability)
        fabric.script_error(
            capability,
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="fabric_gateway",
                operation="execute",
                error_code="FABRIC_UNAVAILABLE",
                error_message="CB_FABRIC open",
                trace_id=trace_id,
            ),
        )
        baseline = len(delta.get_emitted(ORCH_ERROR_ROUTED))
        assert (
            await service.process(_medium_envelope(capability=capability, trace_id=trace_id))
            == ProcessResult.FAILED
        )
        await _wait_for_error_routed(delta, baseline=baseline)

        for topic, payload, emitted_trace in delta.emitted:
            if topic == ORCH_ERROR_ROUTED:
                assert payload["trace_id"] == trace_id
                assert emitted_trace == trace_id

    @pytest.mark.asyncio
    async def test_error_routing_payload_exposes_adapter_severity_and_code(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        delta = service._delta_port
        fabric = service._fabric_port
        trace_id = str(uuid4())

        capability = "tool.severity.fabric.terminal"
        _register_capability(fabric, capability)
        fabric.script_error(
            capability,
            AdapterError(
                severity=ErrorSeverity.TERMINAL,
                adapter_name="fabric_gateway",
                operation="execute",
                error_code="FABRIC_INTERNAL",
                error_message="panic",
                trace_id=trace_id,
            ),
        )

        baseline = len(delta.get_emitted(ORCH_ERROR_ROUTED))
        assert (
            await service.process(_medium_envelope(capability=capability, trace_id=trace_id))
            == ProcessResult.FAILED
        )
        payload = await _wait_for_error_routed(delta, baseline=baseline)

        assert payload["adapter"] == "fabric_gateway"
        assert payload["severity"] == "TERMINAL"
        assert payload["error_code"] == "FABRIC_INTERNAL"
        assert payload["action"] == "ABORT"

    @pytest.mark.asyncio
    async def test_planner_recovery_open_to_half_open_allows_next_request(self) -> None:
        mailbox = _PlannerMailboxStub()
        cb = CircuitBreaker("planner", CircuitBreakerConfig())
        planner = PlannerAdapter(mailbox, cb)
        service = await OrchestratorFactory.create_for_testing(overrides={"planner": planner})

        trace_1 = str(uuid4())
        cb.trip()  # OPEN -> immediate planner failure
        first = await service.process(_high_envelope(trace_id=trace_1))
        assert first == ProcessResult.FAILED
        assert mailbox.enqueued == []

        cb.allow_probe()  # OPEN -> HALF_OPEN
        trace_2 = str(uuid4())
        second = await service.process(_high_envelope(trace_id=trace_2))
        assert second == ProcessResult.DEFERRED
        assert len(mailbox.enqueued) == 1
        assert cb.state.value == "CLOSED"  # successful probe closes breaker

    @pytest.mark.asyncio
    async def test_planner_recovery_follow_up_high_request_executes_successfully(self) -> None:
        mailbox = _PlannerMailboxStub()
        cb = CircuitBreaker("planner", CircuitBreakerConfig())
        planner = PlannerAdapter(mailbox, cb)
        service = await OrchestratorFactory.create_for_testing(overrides={"planner": planner})
        fabric = service._fabric_port
        delta = service._delta_port
        event = service._event_port

        capability = "tool.severity.post_recovery"
        _register_capability(fabric, capability)
        fabric.script_result(
            capability,
            CapabilityResult.success_result(
                request_id="r-recovery",
                data={"ok": True},
                provider_id="mock",
                trace_id="t-recovery",
            ),
        )

        await service.init()
        try:
            cb.trip()
            assert (
                await service.process(_high_envelope(trace_id=str(uuid4()))) == ProcessResult.FAILED
            )

            cb.allow_probe()
            trace_id = str(uuid4())
            assert (
                await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED
            )

            request_id = mailbox.enqueued[-1].request_id
            plan = _single_step_plan(
                request_id=request_id, trace_id=trace_id, capability=capability
            )

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            event.fire(
                "k1.planner.plan.ready.v1",
                {
                    "plan_id": plan.plan_id,
                    "request_id": plan.request_id,
                    "intent": plan.intent,
                    "steps": plan.steps,
                    "trace_id": plan.trace_id,
                    "dependencies": plan.dependencies,
                },
            )
            await _wait_until(lambda: len(delta.get_emitted(ORCH_DAG_COMPLETED)) > baseline)

            completed = delta.get_emitted(ORCH_DAG_COMPLETED)[-1]
            assert completed["success"] is True
            assert completed["failed"] == 0
            assert completed["trace_id"] == trace_id
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_scope_orchestrator_reports_error_not_tier_degradation_decision(self) -> None:
        mailbox = _PlannerMailboxStub()
        cb = CircuitBreaker("planner", CircuitBreakerConfig())
        cb.trip()
        planner = PlannerAdapter(mailbox, cb)
        service = await OrchestratorFactory.create_for_testing(overrides={"planner": planner})

        result = await service.process(_high_envelope(trace_id=str(uuid4())))
        assert result == ProcessResult.FAILED

        # Orchestrator reports failure; Concierge decides HIGH->MEDIUM degradation.
        # We assert only Orchestrator-side behavior here.
        assert result != ProcessResult.DEGRADED
