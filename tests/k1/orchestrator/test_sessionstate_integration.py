"""Epic 7.5.2 -- Orchestrator + real SessionState integration tests.

These tests replace only the Orchestrator state port with a real SessionState
reader path while keeping all other ports as in-memory test adapters.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from k1.fabric.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.adapters.test_workflow_storage_adapter import TestWorkflowStorageAdapter
from k1.orchestrator.events import ORCH_DAG_COMPLETED, PLAN_READY
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import PlanStep, ProcessResult, RegistryEntry, TaskEnvelope
from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.sections.control import PrivacyBand


async def _wait_until(predicate, *, timeout_s: float = 2.0, step_s: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for asynchronous condition")


def _register_capability(fabric: MockFabricAdapter, *names: str) -> None:
    for name in names:
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


def _high_envelope(*, trace_id: str | None = None, session_id: str = "default") -> TaskEnvelope:
    return TaskEnvelope(
        intent="sessionstate-integration-high",
        trace_id=trace_id or str(uuid4()),
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": session_id},
    )


def _medium_envelope(
    *, capabilities: list[str], trace_id: str | None = None, session_id: str = "default"
) -> TaskEnvelope:
    return TaskEnvelope(
        intent="sessionstate-integration-medium",
        trace_id=trace_id or str(uuid4()),
        tier="MEDIUM",
        capabilities=capabilities,
        params={cap: {"q": cap} for cap in capabilities},
        context={"session_id": session_id},
    )


async def _make_service_with_real_sessionstate(session_id: str = "default"):
    # Real SessionState path.
    manager = SessionStateFactory.create_for_testing(session_id=session_id)
    start_result = manager.start()
    assert start_result.success, f"SessionState start failed: {start_result.error}"

    reader = SessionStateReaderAdapter(manager=manager, session_id=session_id)
    state_port = StateReadAdapter(reader)

    # All other ports remain test adapters.
    mailbox = TestMailboxAdapter()
    fabric = MockFabricAdapter()
    planner = MockPlannerAdapter()
    delta = TestDeltaAdapter()
    bridge = MockBridgeAdapter()
    event = TestEventAdapter()
    storage = TestWorkflowStorageAdapter()

    service = await OrchestratorFactory.create_with_ports(
        mailbox=mailbox,
        fabric=fabric,
        planner=planner,
        state=state_port,
        delta=delta,
        bridge=bridge,
        event=event,
        storage=storage,
    )
    await service.init()

    return service, manager, fabric, planner, delta, event


class TestOrchestratorSessionStateIntegration:
    @pytest.mark.asyncio
    async def test_high_dispatch_reads_real_snapshot_for_planner_context(self) -> None:
        service, manager, _, planner, _, _ = await _make_service_with_real_sessionstate("default")
        try:
            # Pre-populate real SessionState sections.
            persona = manager.get_section("persona")
            persona.set_interaction_style(persona.get_interaction_style())
            persona.set_warmth(0.82)

            beliefs = manager.get_section("beliefs_active")
            beliefs.add_fact(subject="user", predicate="likes", obj="tea", confidence=0.9)

            trace_id = str(uuid4())
            result = await service.process(_high_envelope(trace_id=trace_id, session_id="default"))

            assert result == ProcessResult.DEFERRED
            assert planner.request_log
            snapshot = planner.request_log[-1].context
            assert snapshot is not None
            assert "persona" in snapshot.sections
            assert "beliefs_active" in snapshot.sections
        finally:
            await service.shutdown()
            stop_result = manager.stop()
            assert stop_result.success

    @pytest.mark.asyncio
    async def test_wave_boundary_safety_reread_aborts_when_control_is_red(self) -> None:
        service, manager, fabric, planner, delta, event = (
            await _make_service_with_real_sessionstate("default")
        )
        try:
            _register_capability(fabric, "tool.state.wave.a", "tool.state.wave.b")

            # Escalate real SessionState safety band before phase-2 execution.
            control = manager.get_section("control")
            control.escalate_safety(PrivacyBand.RED, reason="test escalation")

            trace_id = str(uuid4())
            phase1 = await service.process(_high_envelope(trace_id=trace_id, session_id="default"))
            assert phase1 == ProcessResult.DEFERRED

            request_id = planner.request_log[-1].request_id
            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            event.fire(
                PLAN_READY,
                {
                    "plan_id": f"plan-{uuid4()}",
                    "request_id": request_id,
                    "intent": "sessionstate-integration-high",
                    "steps": [
                        PlanStep(id="s1", capability="tool.state.wave.a"),
                        PlanStep(id="s2", capability="tool.state.wave.b"),
                    ],
                    "trace_id": trace_id,
                    "dependencies": {"s2": ["s1"]},
                },
            )

            await _wait_until(lambda: len(delta.get_emitted(ORCH_DAG_COMPLETED)) > baseline)
            payload = delta.get_emitted(ORCH_DAG_COMPLETED)[-1]
            assert payload["success"] is False
            assert payload["cancelled"] >= 1
            assert len(fabric.call_log) == 0
        finally:
            await service.shutdown()
            stop_result = manager.stop()
            assert stop_result.success

    @pytest.mark.asyncio
    async def test_fresh_session_gracefully_handles_empty_snapshot(self) -> None:
        service, manager, fabric, _, _, _ = await _make_service_with_real_sessionstate("default")
        try:
            _register_capability(fabric, "tool.state.empty.ok")

            result = await service.process(
                _medium_envelope(capabilities=["tool.state.empty.ok"], session_id="default")
            )

            assert result == ProcessResult.COMPLETED
            fabric.assert_called("tool.state.empty.ok", times=1)
        finally:
            await service.shutdown()
            stop_result = manager.stop()
            assert stop_result.success
