"""M3-X1..M3-X9 live-kernel Fabric + ModelHub cross-component probes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_FAILED,
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_LEARNING_SIGNAL,
    TOPIC_OUTPUT_VALIDATION_FAILED,
)
from k1.fabric.types import (
    AgentContract,
    Availability,
    CapabilityContract,
    CapabilityRequest,
    CapabilityResult,
    InputSpec,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
    ProviderType,
    SafetyBand,
    Tier,
)
from k1.kernel.service import KernelConfig, KernelService
from k1.memory_writer.types import CompressedTurn, ExtractionContext
from k1.model_hub.events import (
    TOPIC_CIRCUIT_STATE,
    TOPIC_FALLBACK_TRIGGERED,
    TOPIC_PROVIDER_FAILURE,
    TOPIC_REQUEST_RECEIVED,
    TOPIC_RESPONSE_COMPLETE,
)
from k1.model_hub.manifest import ModelSpec, PlacementConfig, ProviderManifest
from k1.model_hub.plugins.base import NormalizedRequest, ProviderResponse
from k1.model_hub.types import CapabilityType as MHCapabilityType
from k1.model_hub.types import (
    ChatPayload,
    CircuitState,
    FinishReason,
    HubRequest,
    Message,
    ModelTier,
    PlacementType,
    RequestConstraints,
)
from k1.planner.types import PlannerConstraints, PlannerLLMRequest

pytestmark = pytest.mark.integration

_TOPIC_MH_COMPLETED = "k1.model_hub.request.completed.v1"
_TOPIC_MH_FAILED = "k1.model_hub.request.failed.v1"
_TOPIC_MH_BUDGET_ALERT = "k1.model_hub.budget.alert.v1"
_STUB_PROVIDER_ID = "stub"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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
    session_id: str | None = None,
) -> None:
    if session_id is not None and session_id in svc._sessions:
        await svc.destroy_session(session_id)
    if svc.is_running:
        await svc.shutdown()
    await _assert_no_task_leaks(baseline_tasks)


def _raw_bus(bus: Any) -> Any:
    return getattr(bus, "inner", bus)


def _decode_payload(envelope: Any) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


async def _flush_bus_tasks(bus: Any) -> None:
    raw = _raw_bus(bus)
    for _ in range(5):
        await asyncio.sleep(0)
        if hasattr(raw, "flush"):
            assert raw.flush(timeout_ms=5_000)


async def _wait_until(predicate: Callable[[], bool], description: str) -> None:
    for _ in range(50):
        if predicate():
            return
        await asyncio.sleep(0)
    assert predicate(), description


def _make_contract(
    name: str,
    provider_id: str,
    *,
    provider_type: str = ProviderType.LOCAL_STUB.value,
    output_schema: dict[str, Any] | None = None,
) -> CapabilityContract:
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["M3_X_LIVE"],
        description=f"Live M3-X probe contract for {name}",
        capabilities=["m3_x_probe"],
        limitations=[],
        required_inputs=[InputSpec(name="input_a", type="STRING", description="Probe input")],
        required_context=[],
        output=output_schema or {"type": "object"},
        provider_type=provider_type,
        provider_id=provider_id,
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
    )


def _make_agent_contract(name: str, provider_id: str) -> AgentContract:
    return AgentContract(
        name=name,
        version="1.0.0",
        domain=["M3_X_LIVE"],
        description=f"Live M3-X agent probe contract for {name}",
        capabilities=["m3_x_agent_probe"],
        limitations=[],
        required_inputs=[InputSpec(name="input_a", type="STRING", description="Probe input")],
        required_context=[],
        output={"type": "object"},
        provider_type=ProviderType.AGENT.value,
        provider_id=provider_id,
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
        prompt_template="Return a short deterministic probe response.",
        tools_granted=[],
        llm_budget_tokens=256,
        max_tool_calls=0,
        max_execution_time_ms=5_000,
    )


def _register_contract_with_provider(fabric: Any, contract: CapabilityContract) -> None:
    fabric.register(contract)
    provider_registry = fabric.facade._resolver._provider_matcher._provider_registry
    provider_id = contract.provider_id
    if not provider_registry.contains(provider_id):
        provider_registry.register_provider(
            provider_id,
            ProviderConfig(
                provider_id=provider_id,
                provider_type=contract.provider_type,
                endpoint=f"local://{provider_id}",
                max_execution_ms=30_000,
            ),
        )


def _make_request(capability_name: str, session_id: str, trace_id: str) -> CapabilityRequest:
    return CapabilityRequest(
        capability_name=capability_name,
        params={"input_a": "live m3-x probe"},
        tier=Tier.LOW.value,
        caller="m3-x-live-test",
        caller_id="m3-x-live-test",
        safety_band=SafetyBand.GREEN.value,
        trace_id=trace_id,
        session_id=session_id,
    )


def _make_hub_chat_request(
    trace_id: str,
    *,
    consumer_id: str = "m3-x-live-test",
    cost_limit: float | None = None,
) -> HubRequest:
    return HubRequest(
        capability=MHCapabilityType.CHAT,
        payload=ChatPayload(messages=[Message(role="user", content=f"hello {trace_id}")]),
        constraints=RequestConstraints(
            consumer_id=consumer_id,
            cost_limit=cost_limit,
        ),
        trace_id=trace_id,
    )


class _FailingFabricProvider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id

    async def execute(
        self,
        request: CapabilityRequest,
        context: Any,
        trace_id: str,
    ) -> CapabilityResult:
        return CapabilityResult.failure_result(
            request_id=request.request_id,
            error_code="m3_x_provider_failure",
            error_message="controlled M3-X provider failure",
            retriable=False,
            provider_id=self.provider_id,
            trace_id=trace_id,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.provider_id, status=ProviderStatus.HEALTHY.value)

    def capabilities(self) -> list[str]:
        return []


class _BadOutputProvider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id

    async def execute(
        self,
        request: CapabilityRequest,
        context: Any,
        trace_id: str,
    ) -> CapabilityResult:
        return CapabilityResult.success_result(
            request_id=request.request_id,
            data={"unexpected": "shape"},
            provider_id=self.provider_id,
            trace_id=trace_id,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.provider_id, status=ProviderStatus.HEALTHY.value)

    def capabilities(self) -> list[str]:
        return []


class _FailingMHPlugin:
    async def initialize(self, manifest: ProviderManifest) -> None:
        return None

    def supports(self, capability: MHCapabilityType) -> bool:
        return capability == MHCapabilityType.CHAT

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        raise RuntimeError("controlled M3-X ModelHub provider failure")

    async def close(self) -> None:
        return None


class _SuccessfulMHPlugin:
    async def initialize(self, manifest: ProviderManifest) -> None:
        return None

    def supports(self, capability: MHCapabilityType) -> bool:
        return capability == MHCapabilityType.CHAT

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(
            text="fallback OK",
            prompt_tokens=7,
            completion_tokens=3,
            model_id=request.model_id or "m3-x-success-model",
            finish_reason=FinishReason.STOP,
        )

    async def close(self) -> None:
        return None


def _mh_manifest(provider_id: str, model_id: str) -> ProviderManifest:
    return ProviderManifest(
        provider_id=provider_id,
        display_name=provider_id,
        capabilities=[MHCapabilityType.CHAT],
        models=[
            ModelSpec(
                id=model_id,
                capabilities=[MHCapabilityType.CHAT],
                max_context=8_192,
                max_output=1_024,
                tier=ModelTier.FAST,
            )
        ],
        placement=PlacementConfig(type=PlacementType.LOCAL_CPU),
    )


def _open_stub_circuit(svc: KernelService) -> None:
    circuit_mgr = svc._model_hub._router._dispatcher._circuit_mgr
    for _ in range(3):
        circuit_mgr.record_failure(_STUB_PROVIDER_ID)
    assert circuit_mgr.get_state(_STUB_PROVIDER_ID) == CircuitState.OPEN


# ---------------------------------------------------------------------------
# M3-X1 -- Fabric AGENT execute also produces ModelHub response.complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_x1_llm_backed_fabric_execute_emits_fabric_and_modelhub_events(
    tmp_path: Path,
) -> None:
    session_id = "m3x1"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        fabric = session.fabric

        capability_name = "agent.execute.m3_x1_llm_trace"
        provider_id = "m3-x1-agent-provider"
        _register_contract_with_provider(fabric, _make_agent_contract(capability_name, provider_id))

        fabric_events: list[Any] = []
        mh_events: list[Any] = []
        shared_bus = _raw_bus(svc._bus)
        handles = [
            session.bus.subscribe(TOPIC_CAPABILITY_COMPLETED, fabric_events.append),
            shared_bus.subscribe(TOPIC_RESPONSE_COMPLETE, mh_events.append),
        ]
        try:
            trace_id = "trace-m3-x1"
            result = await fabric.execute(_make_request(capability_name, session_id, trace_id))
            await _flush_bus_tasks(session.bus)
            await _flush_bus_tasks(svc._bus)

            assert result.success is True
            await _wait_until(lambda: len(fabric_events) == 1, "Fabric completed event missing")
            await _wait_until(lambda: len(mh_events) == 1, "ModelHub response.complete missing")

            fabric_payload = _decode_payload(fabric_events[0])
            mh_payload = _decode_payload(mh_events[0])
            assert fabric_payload["cognitive_trace_id"] == trace_id
            assert mh_payload["trace_id"] == trace_id
            assert mh_payload["capability"] == MHCapabilityType.CHAT.value
        finally:
            for handle in handles:
                try:
                    session.bus.unsubscribe(handle)
                except Exception:
                    shared_bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, baseline_tasks, session_id)


# ---------------------------------------------------------------------------
# M3-X2 -- Fabric learning signal emitted after success and failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_x2_fabric_learning_signal_emitted_after_success_and_failure(
    tmp_path: Path,
) -> None:
    session_id = "m3x2"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        fabric = session.fabric

        success_name = "tool.execute.m3_x2_success"
        success_provider_id = "m3-x2-success-provider"
        _register_contract_with_provider(fabric, _make_contract(success_name, success_provider_id))

        captured: list[Any] = []
        handle = session.bus.subscribe(TOPIC_LEARNING_SIGNAL, captured.append)
        try:
            ok = await fabric.execute(_make_request(success_name, session_id, "trace-m3-x2-ok"))

            fail_name = "tool.execute.m3_x2_failure"
            fail_provider_id = "m3-x2-failing-provider"
            failing_provider = _FailingFabricProvider(fail_provider_id)
            fabric.facade._provider_factory.register_handler(
                ProviderType.LOCAL_STUB.value,
                lambda _config, **_deps: failing_provider,
            )
            _register_contract_with_provider(fabric, _make_contract(fail_name, fail_provider_id))

            bad = await fabric.execute(_make_request(fail_name, session_id, "trace-m3-x2-bad"))
            await _flush_bus_tasks(session.bus)

            assert ok.success is True
            assert bad.success is False
            await _wait_until(lambda: len(captured) == 2, "learning signals missing")

            payloads = [_decode_payload(envelope) for envelope in captured]
            by_trace = {payload["cognitive_trace_id"]: payload for payload in payloads}
            assert by_trace["trace-m3-x2-ok"]["success"] is True
            assert by_trace["trace-m3-x2-bad"]["success"] is False
            assert by_trace["trace-m3-x2-bad"]["error_code"] == "m3_x_provider_failure"
        finally:
            session.bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, baseline_tasks, session_id)


# ---------------------------------------------------------------------------
# M3-X3 -- ModelHub circuit.state on CB transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_x3_modelhub_circuit_state_events_for_all_transitions(tmp_path: Path) -> None:
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        captured: list[Any] = []
        shared_bus = _raw_bus(svc._bus)
        handle = shared_bus.subscribe(TOPIC_CIRCUIT_STATE, captured.append)
        try:
            circuit_mgr = svc._model_hub._router._dispatcher._circuit_mgr
            circuit = circuit_mgr._circuits[_STUB_PROVIDER_ID]

            for _ in range(circuit.config.failure_threshold):
                circuit_mgr.record_failure(_STUB_PROVIDER_ID)
            assert circuit_mgr.get_state(_STUB_PROVIDER_ID) == CircuitState.OPEN

            circuit.opened_at -= circuit.config.cooldown_s + 1
            assert circuit_mgr.get_state(_STUB_PROVIDER_ID) == CircuitState.HALF_OPEN

            circuit_mgr.record_success(_STUB_PROVIDER_ID)
            assert circuit_mgr.get_state(_STUB_PROVIDER_ID) == CircuitState.CLOSED

            await _flush_bus_tasks(svc._bus)
            await _wait_until(lambda: len(captured) == 3, "circuit transition events missing")

            transitions = [
                (_decode_payload(envelope)["old_state"], _decode_payload(envelope)["new_state"])
                for envelope in captured
            ]
            assert transitions == [
                (CircuitState.CLOSED.value, CircuitState.OPEN.value),
                (CircuitState.OPEN.value, CircuitState.HALF_OPEN.value),
                (CircuitState.HALF_OPEN.value, CircuitState.CLOSED.value),
            ]
        finally:
            shared_bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, baseline_tasks)


# ---------------------------------------------------------------------------
# M3-X4 -- Provider failure fallback event cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_x4_modelhub_provider_failure_fallback_response_order(tmp_path: Path) -> None:
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        _open_stub_circuit(svc)

        svc._model_hub.register_plugin(
            _mh_manifest("m3-x4-failing-provider", "m3-x4-failing-model"),
            _FailingMHPlugin(),
        )
        svc._model_hub.register_plugin(
            _mh_manifest("m3-x4-success-provider", "m3-x4-success-model"),
            _SuccessfulMHPlugin(),
        )

        captured: list[Any] = []
        shared_bus = _raw_bus(svc._bus)
        handles = [
            shared_bus.subscribe(TOPIC_PROVIDER_FAILURE, captured.append),
            shared_bus.subscribe(TOPIC_FALLBACK_TRIGGERED, captured.append),
            shared_bus.subscribe(TOPIC_RESPONSE_COMPLETE, captured.append),
        ]
        try:
            trace_id = "trace-m3-x4"
            response = await svc._model_hub.execute(_make_hub_chat_request(trace_id))
            await _flush_bus_tasks(svc._bus)

            assert response.metadata.provider_id == "m3-x4-success-provider"
            await _wait_until(lambda: len(captured) == 3, "fallback cascade events missing")
            assert [envelope.topic for envelope in captured] == [
                TOPIC_PROVIDER_FAILURE,
                TOPIC_FALLBACK_TRIGGERED,
                TOPIC_RESPONSE_COMPLETE,
            ]

            failure_payload = _decode_payload(captured[0])
            fallback_payload = _decode_payload(captured[1])
            complete_payload = _decode_payload(captured[2])
            assert failure_payload["will_fallback"] is True
            assert fallback_payload["from_provider"] == "m3-x4-failing-provider"
            assert fallback_payload["to_provider"] == "m3-x4-success-provider"
            assert complete_payload["provider_id"] == "m3-x4-success-provider"
            assert {
                failure_payload["trace_id"],
                fallback_payload["trace_id"],
                complete_payload["trace_id"],
            } == {trace_id}
        finally:
            for handle in handles:
                shared_bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, baseline_tasks)


# ---------------------------------------------------------------------------
# M3-X5 -- Fabric output validation failure topic and result shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_x5_malformed_output_emits_validation_failed_and_result_failure(
    tmp_path: Path,
) -> None:
    session_id = "m3x5"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        fabric = session.fabric

        capability_name = "tool.execute.m3_x5_bad_output"
        provider_id = "m3-x5-bad-output-provider"
        bad_provider = _BadOutputProvider(provider_id)
        fabric.facade._provider_factory.register_handler(
            ProviderType.LOCAL_STUB.value,
            lambda _config, **_deps: bad_provider,
        )
        _register_contract_with_provider(
            fabric,
            _make_contract(
                capability_name,
                provider_id,
                output_schema={
                    "type": "object",
                    "required": ["expected"],
                    "properties": {"expected": {"type": "string"}},
                    "additionalProperties": False,
                },
            ),
        )

        captured: list[Any] = []
        captured_payloads: list[dict[str, Any]] = []
        shared_bus = _raw_bus(svc._bus)
        raw_handles = [
            session.bus.subscribe(TOPIC_OUTPUT_VALIDATION_FAILED, captured.append),
            shared_bus.subscribe(TOPIC_OUTPUT_VALIDATION_FAILED, captured.append),
        ]
        event_port_handle = fabric.event_port.subscribe(
            TOPIC_OUTPUT_VALIDATION_FAILED,
            lambda _topic, payload: captured_payloads.append(payload),
        )
        try:
            result = await fabric.execute(_make_request(capability_name, session_id, "trace-m3-x5"))
            await _flush_bus_tasks(session.bus)
            await _flush_bus_tasks(svc._bus)

            assert result.success is False
            assert result.error is not None
            assert result.error.code == "output_validation_failed"
            await _wait_until(
                lambda: len(captured) + len(captured_payloads) >= 1,
                "output validation failed event missing",
            )
            payload_candidates = [
                *captured_payloads,
                *[_decode_payload(envelope) for envelope in captured],
            ]
            payload = next(
                (
                    candidate
                    for candidate in payload_candidates
                    if candidate.get("capability_name") == capability_name
                ),
                None,
            )
            assert payload is not None, payload_candidates
            assert payload["capability_name"] == capability_name
            assert payload["provider_id"] == provider_id
            assert payload["cognitive_trace_id"] == "trace-m3-x5"
            assert payload["rejection_reason"]
        finally:
            for handle in raw_handles:
                try:
                    session.bus.unsubscribe(handle)
                except Exception:
                    shared_bus.unsubscribe(handle)
            fabric.event_port.unsubscribe(event_port_handle)
    finally:
        await _cleanup_service(svc, baseline_tasks, session_id)


# ---------------------------------------------------------------------------
# M3-X6 -- Planner LLM call emits request.received with planner consumer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_x6_planner_llm_call_emits_modelhub_received_no_capability_topics(
    tmp_path: Path,
) -> None:
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        captured: list[Any] = []
        capability_events: list[Any] = []
        shared_bus = _raw_bus(svc._bus)
        handles = [
            shared_bus.subscribe(TOPIC_REQUEST_RECEIVED, captured.append),
            shared_bus.subscribe(TOPIC_CAPABILITY_INVOKED, capability_events.append),
            shared_bus.subscribe(TOPIC_CAPABILITY_COMPLETED, capability_events.append),
            shared_bus.subscribe(TOPIC_CAPABILITY_FAILED, capability_events.append),
        ]
        try:
            llm_port = svc._planner._pipeline._sketch._llm_port
            request = PlannerLLMRequest(
                capability="CHAT",
                payload={"messages": [{"role": "user", "content": "planner probe"}]},
                constraints=PlannerConstraints(max_tokens=64, timeout_ms=5_000),
                trace_id="trace-m3-x6-planner",
            )
            response = await llm_port.execute(request)
            await _flush_bus_tasks(svc._bus)

            assert response.result
            await _wait_until(lambda: len(captured) == 1, "planner request.received missing")
            payload = _decode_payload(captured[0])
            assert payload["trace_id"] == "trace-m3-x6-planner"
            assert payload["consumer_id"] == "planner"
            assert payload["capability"] == MHCapabilityType.CHAT.value
            assert capability_events == []
        finally:
            for handle in handles:
                shared_bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, baseline_tasks)


# ---------------------------------------------------------------------------
# M3-X7 -- MemoryWriter LLM call emits request.received with MW consumer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_x7_memory_writer_llm_call_emits_modelhub_received(
    tmp_path: Path,
) -> None:
    session_id = "m3x7"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        captured: list[Any] = []
        shared_bus = _raw_bus(svc._bus)
        handle = shared_bus.subscribe(TOPIC_REQUEST_RECEIVED, captured.append)
        try:
            writer_agent = session.memory_writer._pipeline._writer_agent
            context = ExtractionContext(
                current_turn=CompressedTurn(
                    turn_id="turn-m3-x7",
                    role="user",
                    text="remember that I like quiet dinners",
                    timestamp_ms=1,
                    turn_number=1,
                ),
                session_id=session_id,
                conversation_turn=1,
            )
            await writer_agent.extract(context, "trace-m3-x7-mw")
            await _flush_bus_tasks(svc._bus)

            await _wait_until(lambda: len(captured) == 1, "MW request.received missing")
            payload = _decode_payload(captured[0])
            assert payload["consumer_id"] == "memory_writer"
            assert payload["capability"] == MHCapabilityType.CHAT.value
        finally:
            shared_bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, baseline_tasks, session_id)


# ---------------------------------------------------------------------------
# M3-X8 -- Undocumented request.completed and request.failed are emitted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_x8_undocumented_completed_and_failed_topics_are_emitted(tmp_path: Path) -> None:
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        completed: list[Any] = []
        failed: list[Any] = []
        shared_bus = _raw_bus(svc._bus)
        handles = [
            shared_bus.subscribe(_TOPIC_MH_COMPLETED, completed.append),
            shared_bus.subscribe(_TOPIC_MH_FAILED, failed.append),
        ]
        try:
            ok_trace = "trace-m3-x8-ok"
            ok = await svc._model_hub.execute(_make_hub_chat_request(ok_trace))
            assert ok is not None

            _open_stub_circuit(svc)
            fail_trace = "trace-m3-x8-failed"
            with pytest.raises(Exception):
                await svc._model_hub.execute(_make_hub_chat_request(fail_trace))

            await _flush_bus_tasks(svc._bus)
            await _wait_until(lambda: len(completed) == 1, "request.completed missing")
            await _wait_until(lambda: len(failed) == 1, "request.failed missing")

            assert _decode_payload(completed[0])["trace_id"] == ok_trace
            assert _decode_payload(failed[0])["trace_id"] == fail_trace
        finally:
            for handle in handles:
                shared_bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, baseline_tasks)


# ---------------------------------------------------------------------------
# M3-X9 -- budget.alert is still a diagram-only topic (strict xfail)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="M3-X9 GAP: budget.alert.v1 is still diagram-only; router has no budget enforcer.",
)
async def test_m3_x9_budget_alert_topic_emitted_when_budget_rejected(tmp_path: Path) -> None:
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        captured: list[Any] = []
        shared_bus = _raw_bus(svc._bus)
        handle = shared_bus.subscribe(_TOPIC_MH_BUDGET_ALERT, captured.append)
        try:
            await svc._model_hub.execute(
                _make_hub_chat_request(
                    "trace-m3-x9-budget",
                    consumer_id="budget-probe",
                    cost_limit=0.0,
                )
            )
            await _flush_bus_tasks(svc._bus)

            assert captured, "desired future behavior: cost_limit=0 emits budget.alert.v1"
        finally:
            shared_bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, baseline_tasks)
