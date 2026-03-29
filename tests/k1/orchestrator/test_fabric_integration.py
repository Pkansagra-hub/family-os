"""Epic 7.5.1 -- Orchestrator + real Fabric integration tests.

These tests wire a real Fabric instance via FabricGatewayAdapter while
keeping all non-Fabric ports as in-memory test adapters.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from k1.fabric.events.fabric_events import TOPIC_CAPABILITY_COMPLETED, TOPIC_CAPABILITY_INVOKED
from k1.fabric.factory import FabricFactory
from k1.fabric.types import Availability, CapabilityContract, InputSpec, SafetyBand
from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.adapters.test_workflow_storage_adapter import TestWorkflowStorageAdapter
from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_TASK_ACCEPTED, PLAN_READY
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import PlanStep, ProcessResult, TaskEnvelope
from tests.k1.fabric.helpers import register_contract_with_provider


def _make_contract(name: str, *, provider_id: str | None = None) -> CapabilityContract:
    effective_provider = provider_id or f"provider-{name.replace('.', '-')[:32]}"
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["ORCH_TEST"],
        description=f"Contract for {name}",
        capabilities=["invoke"],
        limitations=[],
        required_inputs=[InputSpec(name="q", type="STRING", description="query")],
        output={"type": "object"},
        provider_type="MCP",
        provider_id=effective_provider,
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
    )


def _register_contracts(fabric, *capability_names: str) -> None:
    for capability_name in capability_names:
        register_contract_with_provider(fabric, _make_contract(capability_name))


async def _wait_until(predicate, *, timeout_s: float = 2.0, step_s: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for asynchronous condition")


async def _make_service_with_real_fabric():
    real_fabric = FabricFactory.create_for_testing(capture_events=True)
    fabric_adapter = FabricGatewayAdapter(real_fabric)

    mailbox = TestMailboxAdapter()
    planner = MockPlannerAdapter()
    state = MockStateReadAdapter()
    delta = TestDeltaAdapter()
    bridge = MockBridgeAdapter()
    event = TestEventAdapter()
    storage = TestWorkflowStorageAdapter()

    service = await OrchestratorFactory.create_with_ports(
        mailbox=mailbox,
        fabric=fabric_adapter,
        planner=planner,
        state=state,
        delta=delta,
        bridge=bridge,
        event=event,
        storage=storage,
    )
    await service.init()

    return service, real_fabric, planner, delta, event


def _medium_envelope(*, capabilities: list[str], trace_id: str | None = None) -> TaskEnvelope:
    return TaskEnvelope(
        intent="fabric-integration-medium",
        trace_id=trace_id or str(uuid4()),
        tier="MEDIUM",
        capabilities=capabilities,
        params={cap: {"q": cap} for cap in capabilities},
        context={"session_id": "s-fabric-int-medium"},
    )


def _high_envelope(*, trace_id: str | None = None) -> TaskEnvelope:
    return TaskEnvelope(
        intent="fabric-integration-high",
        trace_id=trace_id or str(uuid4()),
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": "s-fabric-int-high"},
    )


class TestOrchestratorFabricIntegration:
    @pytest.mark.asyncio
    async def test_medium_tier_uses_real_fabric_and_emits_fabric_and_orchestrator_events(
        self,
    ) -> None:
        service, fabric, _, delta, _ = await _make_service_with_real_fabric()
        try:
            cap_a = "tool.execute.orchfabric_mediuma"
            cap_b = "tool.execute.orchfabric_mediumb"
            _register_contracts(fabric, cap_a, cap_b)

            trace_id = str(uuid4())
            result = await service.process(
                _medium_envelope(capabilities=[cap_a, cap_b], trace_id=trace_id)
            )

            assert result == ProcessResult.COMPLETED
            delta.assert_emitted(ORCH_TASK_ACCEPTED, count=1)
            delta.assert_emitted(ORCH_DAG_COMPLETED, count=1)
            assert delta.get_emitted(ORCH_DAG_COMPLETED)[0]["trace_id"] == trace_id

            captured = fabric.event_port.get_captured()
            invoked = [payload for topic, payload in captured if topic == TOPIC_CAPABILITY_INVOKED]
            completed = [
                payload for topic, payload in captured if topic == TOPIC_CAPABILITY_COMPLETED
            ]

            assert len(invoked) >= 2
            assert len(completed) >= 2
            assert {p["capability_name"] for p in invoked} >= {cap_a, cap_b}
            assert {p["capability_name"] for p in completed} >= {cap_a, cap_b}
            assert all(p.get("cognitive_trace_id") == trace_id for p in invoked + completed)
        finally:
            await service.shutdown()
            await fabric.shutdown()

    @pytest.mark.asyncio
    async def test_high_tier_plan_ready_executes_dag_through_real_fabric(self) -> None:
        service, fabric, planner, delta, event = await _make_service_with_real_fabric()
        try:
            cap_1 = "tool.execute.orchfabric_high1"
            cap_2 = "tool.execute.orchfabric_high2"
            _register_contracts(fabric, cap_1, cap_2)

            trace_id = str(uuid4())
            phase1 = await service.process(_high_envelope(trace_id=trace_id))
            assert phase1 == ProcessResult.DEFERRED

            request_id = planner.request_log[-1].request_id
            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            event.fire(
                PLAN_READY,
                {
                    "plan_id": f"plan-{uuid4()}",
                    "request_id": request_id,
                    "intent": "fabric-integration-high",
                    "steps": [
                        PlanStep(id="s1", capability=cap_1),
                        PlanStep(id="s2", capability=cap_2),
                    ],
                    "trace_id": trace_id,
                    "dependencies": {"s2": ["s1"]},
                },
            )

            await _wait_until(lambda: len(delta.get_emitted(ORCH_DAG_COMPLETED)) > baseline)
            payload = delta.get_emitted(ORCH_DAG_COMPLETED)[-1]
            assert payload["success"] is True
            assert payload["trace_id"] == trace_id

            captured = fabric.event_port.get_captured()
            invoked = [payload for topic, payload in captured if topic == TOPIC_CAPABILITY_INVOKED]
            assert {p["capability_name"] for p in invoked} >= {cap_1, cap_2}
            assert all(p.get("cognitive_trace_id") == trace_id for p in invoked)
        finally:
            await service.shutdown()
            await fabric.shutdown()

    @pytest.mark.asyncio
    async def test_missing_capability_fails_before_execution_with_real_registry_lookup(
        self,
    ) -> None:
        service, fabric, _, delta, _ = await _make_service_with_real_fabric()
        try:
            existing = "tool.execute.orchfabric_exists"
            missing = "tool.execute.orchfabric_missing"
            _register_contracts(fabric, existing)

            trace_id = str(uuid4())
            result = await service.process(
                _medium_envelope(capabilities=[existing, missing], trace_id=trace_id)
            )

            assert result == ProcessResult.FAILED
            delta.assert_emitted(ORCH_TASK_ACCEPTED, count=1)
            assert delta.get_emitted(ORCH_DAG_COMPLETED) == []

            # dispatch_medium validates registry first, so no capability invocation should occur.
            captured = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
            assert not any(payload.get("cognitive_trace_id") == trace_id for _, payload in captured)
        finally:
            await service.shutdown()
            await fabric.shutdown()
