"""M4-X2..M4-X13 live-kernel Orchestrator + Planner cross probes."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Iterable

import pytest

from k1.bus.envelope import Envelope, Priority
from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.concierge.bus.topics import (
    TOPIC_ORCHESTRATION_DELTA,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_FAILED,
)
from k1.concierge.orchestrator.types import Budget as ConciergeBudget
from k1.concierge.orchestrator.types import TaskEnvelope as ConciergeTaskEnvelope
from k1.concierge.task.complexity import ComplexityTier
from k1.fabric.circuit_breaker.breaker import CircuitBreaker
from k1.fabric.types import (
    Availability,
    CapabilityContract,
    CapabilityResult,
    ProviderType,
    SafetyBand,
)
from k1.kernel.service import KernelConfig, KernelService
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
from k1.orchestrator.events import (
    ORCH_DAG_COMPLETED,
    ORCH_PLAN_REQUESTED,
    PLAN_FAILED,
    PLAN_READY,
)
from k1.orchestrator.orchestration.guards.micro_replan import MicroReplanCheckpoint
from k1.orchestrator.types import (
    CommittedPlan,
    MicroReplanRequest,
    PlanAck,
    PlanRequest,
    PlanStep,
    ProcessingContext,
    ProcessResult,
    StepResult,
    StepStatus,
    TaskEnvelope,
    TriggerType,
    WaveResult,
    WorkflowRunRequest,
)
from k1.planner.adapters.session_state_adapter import SessionStateReadAdapter
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
    session_ids: Iterable[str] = (),
) -> None:
    for session_id in tuple(session_ids):
        if session_id in svc._sessions:
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


def _make_high_envelope(
    *,
    session_id: str,
    trace_id: str,
    task_id: str,
    intent: str = "Find a family planning prompt template.",
) -> ConciergeTaskEnvelope:
    return ConciergeTaskEnvelope(
        intent=intent,
        task_id=task_id,
        context={},
        tier=ComplexityTier.HIGH,
        budget=ConciergeBudget(max_fabric_calls=10, max_planner_tokens=3500),
        session_id=session_id,
        trace_id=trace_id,
    )


def _make_capability_contract(name: str) -> CapabilityContract:
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["M4_X_LIVE"],
        description=f"Live M4 cross-component probe contract for {name}",
        capabilities=["m4_x_probe"],
        limitations=[],
        required_inputs=[],
        required_context=[],
        output={"type": "object"},
        provider_type=ProviderType.LOCAL_STUB.value,
        provider_id="m4-x-provider",
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
    )


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


class PlannerDepthSpy:
    """IPlannerPort-compatible spy that records live mailbox depth after enqueue."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.requests: list[PlanRequest] = []
        self.depths_after_enqueue: list[int] = []

    async def request_plan(self, request: PlanRequest) -> Any:
        self.requests.append(request)
        ack = await self.inner.request_plan(request)
        queue = getattr(getattr(self.inner, "_mailbox", None), "_queue", None)
        self.depths_after_enqueue.append(queue.qsize() if queue is not None else -1)
        return ack

    async def cancel_plan(self, request_id: str) -> None:
        return await self.inner.cancel_plan(request_id)

    async def micro_replan(self, request: Any) -> Any:
        return await self.inner.micro_replan(request)


async def _script_planner_for_steps(
    svc: KernelService,
    *,
    steps: list[dict[str, Any]],
    dependencies: dict[str, list[str]],
) -> Any:
    scripted = await install_scripted_plugin(svc)
    is_planner = lambda req: getattr(req, "consumer_id", "") == "planner"

    scripted.queue(
        make_text_response(
            json.dumps(
                {
                    "rough_steps": [
                        {"intent": f"Run {step['id']}", "depends_on": step.get("deps", [])}
                        for step in steps
                    ],
                    "rationale": "M4 cross-component scripted sketch.",
                    "needs_clarification": False,
                }
            )
        ),
        predicate=is_planner,
        label="planner-sketch",
    )
    scripted.queue(
        make_text_response(
            json.dumps(
                {
                    "steps": steps,
                    "dependencies": dependencies,
                    "rationale": "M4 cross-component scripted expand.",
                }
            )
        ),
        predicate=is_planner,
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
        predicate=is_planner,
        label="planner-validate",
    )
    return scripted


class BusPlanReadyPlannerPort:
    """IPlannerPort-compatible planner that publishes a fixed CommittedPlan."""

    def __init__(
        self, bus: Any, plan_steps: list[PlanStep], dependencies: dict[str, list[str]]
    ) -> None:
        self._bus = bus
        self._plan_steps = plan_steps
        self._dependencies = dependencies
        self.requests: list[PlanRequest] = []

    async def request_plan(self, request: PlanRequest) -> PlanAck:
        self.requests.append(request)
        asyncio.create_task(self._emit_ready(request), name="m4-x-plan-ready")
        return PlanAck(request_id=request.request_id, status="ACCEPTED")

    async def _emit_ready(self, request: PlanRequest) -> None:
        await asyncio.sleep(0.05)
        plan = CommittedPlan(
            plan_id=f"plan-{request.request_id}",
            request_id=request.request_id,
            intent=request.intent,
            steps=self._plan_steps,
            trace_id=request.trace_id,
            dependencies=self._dependencies,
        )
        self._bus.publish(
            Envelope(
                topic=PLAN_READY,
                payload=json.dumps(plan.to_dict(), separators=(",", ":")).encode("utf-8"),
                cognitive_trace_id=request.trace_id,
                priority=Priority.INTERACTIVE,
            )
        )

    async def cancel_plan(self, request_id: str) -> None:
        return None

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        raise RuntimeError("not used")


def _prompt_step(step_id: str, *, deps: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": step_id,
        "capability": "tool.read.find_prompts",
        "params": {"intent": f"family planning prompt {step_id}", "top_k": 1},
        "deps": list(deps or []),
        "output_schema": {"type": "object"},
        "timeout_ms": 5000,
    }


@pytest.mark.asyncio
async def test_m4_x2_state_reader_identity_shared_across_orch_fabric_planner(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()

        shared_reader = svc._session_routing_reader
        assert svc._orchestrator._state_port._reader is shared_reader

        planner_router = svc._planner._pipeline._sketch._tool_router
        assert svc._planner._pipeline._expand._tool_router is planner_router
        planner_state = planner_router._state_read
        assert isinstance(planner_state, SessionStateReadAdapter)
        assert planner_state._reader is shared_reader
        assert planner_state._session_id == ""

        assert svc._shared_fabric.facade._context_builder._state_reader is shared_reader
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m4_x3_session_fabric_dispatch_adapter_targets_live_orchestrator(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    session_ids = ("m4x3a", "m4x3b")

    try:
        await svc.startup()
        for session_id in session_ids:
            await svc.create_session(session_id)

        dispatches: list[FabricDispatchAdapter] = []
        for session_id in session_ids:
            concierge = svc._sessions[session_id].concierge
            for ctx in (concierge.front_ctx, concierge.back_ctx):
                assert ctx is not None
                assert isinstance(ctx.dispatch, FabricDispatchAdapter)
                assert ctx.dispatch._orchestrator is svc._orchestrator
                dispatches.append(ctx.dispatch)

        assert len({id(dispatch) for dispatch in dispatches}) == 2
    finally:
        await _cleanup_service(svc, baseline_tasks, session_ids=session_ids)


@pytest.mark.asyncio
async def test_m4_x4_high_envelope_hits_planner_mailbox_plan_ready_and_orchestrator_receive(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    session_id = "m4x4"

    try:
        await svc.startup()
        transport = _install_test_mcp_transport(svc._shared_fabric)
        await _script_planner_for_steps(
            svc,
            steps=[_prompt_step("s1")],
            dependencies={"s1": []},
        )

        planner_spy = PlannerDepthSpy(svc._orchestrator._planner_port)
        svc._orchestrator.bind_planner(planner_spy)

        await svc.create_session(session_id)
        recorder = TopicRecorder(
            svc._bus,
            topics=(ORCH_PLAN_REQUESTED, PLAN_READY, ORCH_DAG_COMPLETED),
        )
        recorder.start()
        try:
            trace_id = "trace-m4-x4"
            result = await asyncio.wait_for(
                svc._orchestrator.handle_task(
                    _make_high_envelope(
                        session_id=session_id,
                        trace_id=trace_id,
                        task_id="task-m4-x4",
                    )
                ),
                timeout=60.0,
            )

            assert result == ProcessResult.COMPLETED
            assert len(planner_spy.requests) == 1
            assert max(planner_spy.depths_after_enqueue) > 0

            plan_ready_payload = _decode_payload(recorder.by_topic(PLAN_READY)[0])
            committed = CommittedPlan.from_dict(plan_ready_payload)
            assert committed.request_id == planner_spy.requests[0].request_id
            assert committed.plan_id in svc._orchestrator._executed_plans
            assert not svc._orchestrator._pending_plans

            dag_payloads = [_decode_payload(env) for env in recorder.by_topic(ORCH_DAG_COMPLETED)]
            assert any(
                payload["trace_id"] == trace_id and payload["success"] for payload in dag_payloads
            )
            assert [call.tool_name for call in transport.drain()] == ["tool.read.find_prompts"]
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks, session_ids=(session_id,))


@pytest.mark.asyncio
async def test_m4_x5_two_wave_plan_runs_two_execute_waves_and_bridges_to_session_bus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    session_id = "m4x5"

    try:
        await svc.startup()
        _install_test_mcp_transport(svc._shared_fabric)
        svc._orchestrator.bind_planner(
            BusPlanReadyPlannerPort(
                svc._bus,
                plan_steps=[
                    PlanStep(
                        id="s1",
                        capability="tool.read.find_prompts",
                        params={"intent": "family planning prompt s1", "top_k": 1},
                    ),
                    PlanStep(
                        id="s2",
                        capability="tool.read.find_prompts",
                        params={"intent": "family planning prompt s2", "top_k": 1},
                    ),
                ],
                dependencies={"s1": [], "s2": ["s1"]},
            )
        )

        dag = svc._orchestrator._dag_executor
        wave_indices: list[int] = []
        original_execute_wave = type(dag).execute_wave

        async def execute_wave_spy(self: Any, wave: Any, plan: Any, snapshot: Any) -> Any:
            if self is dag:
                wave_indices.append(wave.wave_index)
            return await original_execute_wave(self, wave, plan, snapshot)

        monkeypatch.setattr(type(dag), "execute_wave", execute_wave_spy)

        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        recorder = TopicRecorder(
            session.bus,
            topics=(TOPIC_TASK_COMPLETE, TOPIC_TASK_FAILED),
        )
        recorder.start()
        try:
            result = await asyncio.wait_for(
                session.concierge.back_ctx.dispatch.dispatch_envelope(
                    _make_high_envelope(
                        session_id=session_id,
                        trace_id="trace-m4-x5",
                        task_id="task-m4-x5",
                    )
                ),
                timeout=60.0,
            )

            assert result == ProcessResult.COMPLETED
            assert wave_indices == [0, 1]
            assert not recorder.by_topic(TOPIC_TASK_FAILED)
            complete_payload = _decode_payload(recorder.by_topic(TOPIC_TASK_COMPLETE)[0])
            assert complete_payload["task_id"] == "task-m4-x5"
            assert complete_payload["source"] == "orchestrator"
            assert complete_payload["process_result"] == "COMPLETED"
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks, session_ids=(session_id,))


@pytest.mark.asyncio
async def test_m4_x6_planner_query_context_reads_requested_session_state(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    session_ids = ("m4x6a", "m4x6b")

    try:
        await svc.startup()
        for session_id in session_ids:
            await svc.create_session(session_id)

        svc._sessions["m4x6a"].session_state.get_section("persona").set_warmth(0.11)
        svc._sessions["m4x6b"].session_state.get_section("persona").set_warmth(0.89)

        router = svc._planner._pipeline._sketch._tool_router
        sid1_snapshot = await router.read_context("m4x6a", ["persona"])
        sid2_snapshot = await router.read_context("m4x6b", ["persona"])
        sid1_context = sid1_snapshot.sections
        sid2_context = sid2_snapshot.sections

        assert sid1_snapshot.session_id == "m4x6a"
        assert sid2_snapshot.session_id == "m4x6b"
        assert sid1_context["persona"]["personality"]["warmth"] == 0.11
        assert sid2_context["persona"]["personality"]["warmth"] == 0.89
        assert sid1_context != sid2_context
    finally:
        await _cleanup_service(svc, baseline_tasks, session_ids=session_ids)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="M4-X7 gap: CB_PLANNER OPEN currently returns FAILED, not a MED fallback.",
)
async def test_m4_x7_cb_planner_open_degrades_high_to_medium_without_enqueue(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    class MailboxProbe:
        def __init__(self) -> None:
            self.enqueued: list[PlanRequest] = []

        async def enqueue(self, request: PlanRequest) -> None:
            self.enqueued.append(request)

        async def send_cancel(self, request_id: str) -> None:
            return None

        async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
            raise RuntimeError("not used")

    try:
        await svc.startup()
        mailbox = MailboxProbe()
        cb = CircuitBreaker(provider_id="planner")
        cb.trip()
        svc._orchestrator.bind_planner(PlannerAdapter(mailbox, cb))

        result = await svc._orchestrator.process(
            TaskEnvelope(
                intent="tool.read.find_prompts",
                trace_id="trace-m4-x7",
                caller_id="m4-x7",
                context={"session_id": "m4x7"},
                tier="HIGH",
            )
        )

        assert result in (ProcessResult.COMPLETED, ProcessResult.DEGRADED)
        assert mailbox.enqueued == []
    finally:
        await _cleanup_service(svc, baseline_tasks)


class PlanFailedPlannerPort:
    """Accepts a plan request, then emits PLAN_FAILED through the live bus."""

    def __init__(self, bus: Any) -> None:
        self._bus = bus
        self.requests: list[PlanRequest] = []

    async def request_plan(self, request: PlanRequest) -> PlanAck:
        self.requests.append(request)
        asyncio.create_task(self._emit_failed(request), name="m4-x8-plan-failed")
        return PlanAck(request_id=request.request_id, status="ACCEPTED")

    async def _emit_failed(self, request: PlanRequest) -> None:
        await asyncio.sleep(0.05)
        payload = json.dumps(
            {
                "request_id": request.request_id,
                "reason": "scripted_failure",
                "error_detail": "M4-X8 probe",
                "trace_id": request.trace_id,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        self._bus.publish(
            Envelope(
                topic=PLAN_FAILED,
                payload=payload,
                cognitive_trace_id=request.trace_id,
                priority=Priority.INTERACTIVE,
            )
        )

    async def cancel_plan(self, request_id: str) -> None:
        return None

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        raise RuntimeError("not used")


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="M4-X8 gap: PLAN_FAILED event does not resolve handle_task() waiters promptly.",
)
async def test_m4_x8_plan_failed_event_returns_from_handle_task_without_timeout(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    session_id = "m4x8"

    try:
        await svc.startup()
        await svc.create_session(session_id)
        svc._orchestrator.bind_planner(PlanFailedPlannerPort(svc._bus))

        result = await asyncio.wait_for(
            svc._orchestrator.handle_task(
                _make_high_envelope(
                    session_id=session_id,
                    trace_id="trace-m4-x8",
                    task_id="task-m4-x8",
                )
            ),
            timeout=1.0,
        )
        assert result == ProcessResult.FAILED
    finally:
        await _cleanup_service(svc, baseline_tasks, session_ids=(session_id,))


@pytest.mark.asyncio
async def test_m4_x9_planner_discovery_returns_freshly_registered_capability(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        capability_name = "tool.read.m4_x9_fresh_capability"
        svc._shared_fabric.register(_make_capability_contract(capability_name))

        result = await svc._planner._pipeline._sketch._tool_router.discover(
            intent="fresh capability",
            top_k=50,
        )

        assert any(
            scored.contract is not None and scored.contract.name == capability_name
            for scored in result.capabilities
        )
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m4_x10_micro_replan_sends_remaining_steps_and_returns_partial_plan() -> None:
    remaining = [
        PlanStep(
            id="s2",
            capability="tool.read.find_prompts",
            params={"date": "unknown"},
        )
    ]
    replacement = CommittedPlan(
        plan_id="plan-m4-x10-replacement",
        request_id="request-m4-x10-replacement",
        intent="Use discovered date",
        steps=[
            PlanStep(
                id="s2r",
                capability="tool.read.find_prompts",
                params={"date": "Friday"},
            )
        ],
        trace_id="trace-m4-x10",
        dependencies={"s2r": []},
    )

    class MicroPlanner:
        def __init__(self) -> None:
            self.requests: list[MicroReplanRequest] = []

        async def request_plan(self, request: PlanRequest) -> PlanAck:
            raise RuntimeError("not used")

        async def cancel_plan(self, request_id: str) -> None:
            return None

        async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
            self.requests.append(request)
            return replacement

    planner = MicroPlanner()
    guard = MicroReplanCheckpoint(planner)
    ctx = ProcessingContext(trace_id="trace-m4-x10", request_id="request-m4-x10", tier="HIGH")
    wave_result = WaveResult(
        wave_index=0,
        step_results=[
            StepResult(
                step_id="s1",
                capability_name="tool.read.find_prompts",
                status=StepStatus.COMPLETED,
                result=CapabilityResult(
                    request_id="cap-m4-x10",
                    trace_id="trace-m4-x10",
                    success=True,
                    data={
                        "discoveries": [
                            {"field": "date", "value": "Friday", "source_step_id": "s1"}
                        ]
                    },
                ),
            )
        ],
    )

    decision = await guard.after_wave(wave_result, ctx, remaining, "plan-m4-x10")

    assert guard.replans_used == 1
    assert ctx.micro_replan_done is True
    assert decision.metadata is not None
    assert decision.metadata["new_plan"] is replacement
    assert planner.requests[0].original_plan_id == "plan-m4-x10"
    assert planner.requests[0].remaining_steps == remaining
    assert [step.id for step in replacement.steps] == ["s2r"]


@pytest.mark.asyncio
async def test_m4_x11_lifecycle_crosswire_order_is_s6_s6b_then_s7(tmp_path: Path) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        events = svc.lifecycle_events()
        by_phase = {event["phase"]: event for event in events}

        assert "S6_complete" in by_phase
        assert "S6b_complete" in by_phase
        assert "S7_complete" in by_phase
        assert "S6a_complete" not in by_phase
        assert by_phase["S6_complete"]["ts"] < by_phase["S6b_complete"]["ts"]
        assert by_phase["S6b_complete"]["ts"] < by_phase["S7_complete"]["ts"]
        assert by_phase["S6b_complete"]["component"] == "Orchestrator↔Planner"
        assert isinstance(svc._orchestrator._planner_port, PlannerAdapter)
        assert svc._orchestrator._planner_port._mailbox is svc._planner.get_mailbox()
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.xfail(
    strict=True,
    reason="M4-X12 gap: WorkflowRunRequest has no session/Back return handle.",
)
def test_m4_x12_workflow_trigger_request_carries_back_return_handle() -> None:
    request = WorkflowRunRequest(
        workflow_id="workflow-m4-x12",
        version="1",
        trigger_type=TriggerType.CRON,
        trace_id="trace-m4-x12",
    )

    assert hasattr(request, "session_id")
    assert hasattr(request, "reply_to")


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="M4-X13 gap: Orchestrator progress is emitted on kernel bus, not bridged to session bus.",
)
async def test_m4_x13_hil_progress_reaches_session_bus_and_concierge_progressing(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    session_id = "m4x13"

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        recorder = TopicRecorder(
            session.bus,
            topics=(
                "k1.hil.progress.v1",
                "k1.agent.orchestrator.delta.v1",
                TOPIC_ORCHESTRATION_DELTA,
            ),
        )
        recorder.start()
        try:
            await svc._orchestrator._delta_port.emit_progress(
                step_id="m4-x13",
                summary="M4-X13 progress",
                trace_id="trace-m4-x13",
            )
            await asyncio.sleep(0)

            assert recorder.envelopes
            assert session.concierge.state == "PROGRESSING"
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks, session_ids=(session_id,))
