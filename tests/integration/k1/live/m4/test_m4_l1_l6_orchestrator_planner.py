"""M4-L1..M4-L6 live-kernel Orchestrator + Planner probes."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Iterable

import pytest

from k1.bus.envelope import Envelope
from k1.concierge.orchestrator.types import Budget as ConciergeBudget
from k1.concierge.orchestrator.types import TaskEnvelope as ConciergeTaskEnvelope
from k1.concierge.task.complexity import ComplexityTier
from k1.fabric.retrieval import EmbeddingUnavailableError
from k1.kernel.service import KernelConfig, KernelService
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.orchestrator.events import (
    ORCH_DAG_COMPLETED,
    ORCH_PLAN_REQUESTED,
    ORCH_STEP_COMPLETED,
    PLAN_READY,
)
from k1.orchestrator.orchestration.guards.concurrency_guard import ConcurrencyGuard
from k1.orchestrator.types import CommittedPlan, PlanRequest, PlanStep, ProcessResult
from k1.planner.adapters.fabric_retrieval_adapter import FabricRetrievalAdapter
from tests.k1.integration.concierge.scripted_provider import (
    install_scripted_plugin,
    make_text_response,
)

pytestmark = pytest.mark.integration


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path, **overrides: Any) -> KernelConfig:
    values: dict[str, Any] = {
        "test_mode": True,
        "model_mode": "test",
        "ordered_bus": True,
        "session_mode": "standalone",
        "bridge_enabled": False,
        "bridge_offline_ok": True,
        "otel_enabled": False,
        "enable_hitl": False,
        "enable_hil_service": False,
        "enable_self_model": False,
        "enable_family_tools": False,
        "sessionstate_db_path": str(tmp_path / "ssm.db"),
        "workflow_db_path": str(tmp_path / "workflows.db"),
        "bridge_outbox_path": str(tmp_path / "bridge.db"),
    }
    values.update(overrides)
    return KernelConfig(**values)


async def _assert_no_task_leaks(baseline_tasks: set[asyncio.Task[object]]) -> None:
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert leaked == set(), f"Leaked tasks: {[task.get_name() for task in leaked]}"


async def _cleanup_service(
    svc: KernelService,
    baseline_tasks: set[asyncio.Task[object]],
    *,
    session_id: str = "",
) -> None:
    if session_id and session_id in svc._sessions:
        await svc.destroy_session(session_id)
    if svc.is_running:
        await svc.shutdown()
    await _assert_no_task_leaks(baseline_tasks)


def _decode_payload(envelope: Envelope) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


def _install_test_mcp_transport(fabric: Any) -> Any:
    from k1.fabric.adapters.test_mcp_transport import TestMCPTransport

    facade = getattr(fabric, "facade", None) or fabric
    provider_factory = getattr(facade, "_provider_factory", None)
    assert provider_factory is not None
    port_deps = getattr(provider_factory, "_port_deps", None)
    assert port_deps is not None
    transport = TestMCPTransport(connected=True)
    port_deps["mcp_transport"] = transport
    provider_factory._port_deps = port_deps
    return transport


class TopicRecorder:
    """Record envelopes from a fixed set of live bus topics."""

    def __init__(self, bus: Any, topics: Iterable[str]) -> None:
        self._bus = bus
        self._topics = tuple(topics)
        self._handles: list[Any] = []
        self._lock = threading.RLock()
        self.envelopes: list[Envelope] = []

    def start(self) -> None:
        for topic in self._topics:
            self._handles.append(self._bus.subscribe(topic, self._on_envelope))

    def stop(self) -> None:
        for handle in self._handles:
            try:
                self._bus.unsubscribe(handle)
            except Exception:
                pass
        self._handles.clear()

    def _on_envelope(self, envelope: Envelope) -> None:
        with self._lock:
            self.envelopes.append(envelope)

    def by_topic(self, topic: str) -> list[Envelope]:
        with self._lock:
            return [envelope for envelope in self.envelopes if envelope.topic == topic]


class PlannerPortSpy:
    """IPlannerPort-compatible spy that forwards to the live planner port."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.requests: list[PlanRequest] = []

    async def request_plan(self, request: PlanRequest) -> Any:
        self.requests.append(request)
        return await self.inner.request_plan(request)

    async def cancel_plan(self, request_id: str) -> None:
        return await self.inner.cancel_plan(request_id)

    async def micro_replan(self, request: Any) -> Any:
        return await self.inner.micro_replan(request)


@pytest.mark.asyncio
async def test_m4_l1_orchestrator_uses_live_session_routing_state_port(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()

        state_port = svc._orchestrator._state_port
        assert isinstance(state_port, StateReadAdapter)
        assert not isinstance(state_port, MockStateReadAdapter)
        assert state_port._reader is svc._session_routing_reader
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m4_l2_high_task_crosses_orchestrator_planner_fabric_to_dag_complete(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    session_id = "m4l2"

    try:
        await svc.startup()
        transport = _install_test_mcp_transport(svc._shared_fabric)
        scripted = await install_scripted_plugin(svc)

        capability = "tool.read.find_prompts"
        from k1.fabric.providers.mcp_provider import MCPResponse

        transport.add_response(
            capability,
            MCPResponse(
                success=True,
                content=[{"type": "text", "text": "[]"}],
                latency_ms=2,
            ),
        )

        scripted.queue(
            make_text_response(
                json.dumps(
                    {
                        "rough_steps": [
                            {
                                "intent": "Find a family planning prompt template.",
                                "depends_on": [],
                            }
                        ],
                        "rationale": "A single registered Fabric capability fulfils the request.",
                        "needs_clarification": False,
                    }
                )
            ),
            predicate=lambda req: getattr(req, "consumer_id", "") == "planner",
            label="planner-sketch",
        )
        scripted.queue(
            make_text_response(
                json.dumps(
                    {
                        "steps": [
                            {
                                "id": "s1",
                                "capability": capability,
                                "params": {"intent": "family planning prompt", "top_k": 1},
                                "deps": [],
                                "output_schema": {"type": "object"},
                                "timeout_ms": 5000,
                            }
                        ],
                        "dependencies": {"s1": []},
                        "rationale": "One safe read-only prompt lookup.",
                    }
                )
            ),
            predicate=lambda req: getattr(req, "consumer_id", "") == "planner",
            label="planner-expand",
        )
        scripted.queue(
            make_text_response(
                json.dumps(
                    {
                        "status": "approved",
                        "reasons": ["Plan is coherent, safe, and complete."],
                        "coherence_score": 1.0,
                        "safety_assessment": "safe",
                        "completeness": True,
                    }
                )
            ),
            predicate=lambda req: getattr(req, "consumer_id", "") == "planner",
            label="planner-validate",
        )

        planner_spy = PlannerPortSpy(svc._orchestrator._planner_port)
        svc._orchestrator.bind_planner(planner_spy)

        await svc.create_session(session_id)
        recorder = TopicRecorder(
            svc._bus,
            topics=(
                ORCH_PLAN_REQUESTED,
                PLAN_READY,
                ORCH_STEP_COMPLETED,
                ORCH_DAG_COMPLETED,
            ),
        )
        recorder.start()
        try:
            trace_id = "trace-m4-l2"
            envelope = ConciergeTaskEnvelope(
                intent="Find a family planning prompt template.",
                task_id="task-m4-l2",
                context={"params": {capability: {"intent": "family planning prompt", "top_k": 1}}},
                tier=ComplexityTier.HIGH,
                budget=ConciergeBudget(max_fabric_calls=10, max_planner_tokens=3500),
                session_id=session_id,
                trace_id=trace_id,
            )

            result = await asyncio.wait_for(svc._orchestrator.handle_task(envelope), timeout=60.0)

            assert result == ProcessResult.COMPLETED
            assert len(planner_spy.requests) == 1
            plan_request = planner_spy.requests[0]
            assert plan_request.intent == envelope.intent
            assert plan_request.trace_id == trace_id
            assert plan_request.context is not None
            assert plan_request.context.session_id == session_id

            plan_requested_payload = _decode_payload(recorder.by_topic(ORCH_PLAN_REQUESTED)[0])
            assert plan_requested_payload["request_id"] == plan_request.request_id
            assert plan_requested_payload["intent"] == envelope.intent
            assert plan_requested_payload["trace_id"] == trace_id
            assert plan_requested_payload["tier"] == "HIGH"

            plan_ready_payload = _decode_payload(recorder.by_topic(PLAN_READY)[0])
            committed = CommittedPlan.from_dict(plan_ready_payload)
            assert committed.request_id == plan_request.request_id
            assert committed.trace_id == trace_id
            assert committed.steps[0].capability == capability
            assert committed.steps[0].params == {"intent": "family planning prompt", "top_k": 1}

            step_payload = _decode_payload(recorder.by_topic(ORCH_STEP_COMPLETED)[0])
            assert step_payload["step_id"] == "s1"
            assert step_payload["capability"] == capability
            assert step_payload["status"] == "COMPLETED"
            assert step_payload["trace_id"] == trace_id

            dag_payloads = [_decode_payload(env) for env in recorder.by_topic(ORCH_DAG_COMPLETED)]
            assert dag_payloads
            assert any(
                payload["trace_id"] == trace_id and payload["success"] for payload in dag_payloads
            )

            fired_labels = [rule.label for rule in scripted.rules if rule.fired]
            assert fired_labels == ["planner-sketch", "planner-expand", "planner-validate"]
            captured = transport.drain()
            assert [call.tool_name for call in captured] == [capability]
            assert captured[0].arguments == {"intent": "family planning prompt", "top_k": 1}
            assert captured[0].trace_id == trace_id
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks, session_id=session_id)


@pytest.mark.xfail(
    strict=True,
    reason="M4-L3 gap: ConcurrencyGuard exposes only a single active flag, not a max-depth limit.",
)
def test_m4_l3_concurrency_guard_exposes_depth_limit() -> None:
    guard = ConcurrencyGuard(max_depth=2)
    assert guard.max_depth == 2


def test_m4_l4_plan_step_safety_band_min_round_trips_through_plan_ready_payload() -> None:
    step = PlanStep(
        id="s1",
        capability="tool.read.find_prompts",
        params={"intent": "family planning prompt", "top_k": 1},
        safety_band_min="YELLOW",
    )
    plan = CommittedPlan(
        plan_id="plan-m4-l4",
        request_id="request-m4-l4",
        intent="Find a family planning prompt template.",
        steps=[step],
        trace_id="trace-m4-l4",
        dependencies={"s1": []},
    )

    restored = CommittedPlan.from_dict(plan.to_dict())

    assert restored.steps[0].safety_band_min == "YELLOW"
    assert restored.to_dict()["steps"][0]["safety_band_min"] == "YELLOW"


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="M4-L5 gap: missing embedding_port is silently replaced by _StubEmbeddingPort.",
)
async def test_m4_l5_fabric_retrieval_errors_when_embedding_port_is_unwired(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        with pytest.raises(EmbeddingUnavailableError):
            await svc._shared_fabric.retrieval.discover_capabilities(
                intent="find planning prompts",
                top_k=1,
            )
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m4_l6_planner_uses_shared_fabric_retrieval_adapter(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()

        pipeline = svc._planner._pipeline
        validate_fabric = pipeline._validate._fabric_retrieval
        sketch_fabric = pipeline._sketch._tool_router._fabric_retrieval

        assert isinstance(validate_fabric, FabricRetrievalAdapter)
        assert isinstance(sketch_fabric, FabricRetrievalAdapter)
        assert validate_fabric is sketch_fabric
        assert validate_fabric._fabric is svc._shared_fabric.retrieval
    finally:
        await _cleanup_service(svc, baseline_tasks)
