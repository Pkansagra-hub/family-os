"""M3-L1..M3-L4 live-kernel Fabric + ModelHub probes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from k1.fabric.circuit_breaker.breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)
from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_INVOKED,
)
from k1.fabric.types import (
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
    session_id: str,
    baseline_tasks: set[asyncio.Task[object]],
) -> None:
    if session_id in svc._sessions:
        await svc.destroy_session(session_id)
    if svc.is_running:
        await svc.shutdown()
    await _assert_no_task_leaks(baseline_tasks)


def _raw_bus(bus: Any) -> Any:
    return getattr(bus, "inner", bus)


def _decode_payload(envelope: Any) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


async def _flush_bus_tasks(bus: Any) -> None:
    assert _raw_bus(bus).flush(timeout_ms=5_000)
    for _ in range(5):
        await asyncio.sleep(0)


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
    safety_band_min: str = SafetyBand.GREEN.value,
    required_context: list[str] | None = None,
) -> CapabilityContract:
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["M3_LIVE"],
        description=f"Live M3 probe contract for {name}",
        capabilities=["m3_probe"],
        limitations=[],
        required_inputs=[InputSpec(name="input_a", type="STRING", description="Probe input")],
        required_context=list(required_context or []),
        output={"type": "object"},
        provider_type=ProviderType.LOCAL_STUB.value,
        provider_id=provider_id,
        safety_band_min=safety_band_min,
        availability=Availability.ONLINE.value,
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


def _make_request(
    capability_name: str,
    session_id: str,
    trace_id: str,
    *,
    safety_band: str = SafetyBand.GREEN.value,
) -> CapabilityRequest:
    return CapabilityRequest(
        capability_name=capability_name,
        params={"input_a": "live probe"},
        tier=Tier.LOW.value,
        caller="m3-live-test",
        caller_id="m3-live-test",
        safety_band=safety_band,
        trace_id=trace_id,
        session_id=session_id,
    )


class _SequencedProvider:
    """Provider returned by the real ProviderFactory handler for M3 CB probes."""

    def __init__(self, provider_id: str, outcomes: list[bool]) -> None:
        self.provider_id = provider_id
        self.outcomes = list(outcomes)
        self.calls = 0

    async def execute(
        self, request: CapabilityRequest, context: Any, trace_id: str
    ) -> CapabilityResult:
        self.calls += 1
        should_succeed = self.outcomes.pop(0) if self.outcomes else True
        if should_succeed:
            return CapabilityResult.success_result(
                request_id=request.request_id,
                data={"status": "ok", "provider_calls": self.calls},
                provider_id=self.provider_id,
                trace_id=trace_id,
            )
        return CapabilityResult.failure_result(
            request_id=request.request_id,
            error_code="m3_provider_failure",
            error_message="M3 controlled provider failure",
            retriable=False,
            provider_id=self.provider_id,
            trace_id=trace_id,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.provider_id, status=ProviderStatus.HEALTHY.value)

    def capabilities(self) -> list[str]:
        return []


class _ReadOnlyTrackingStateReader:
    """Read-only proxy that records reads and any attempted write-method lookup."""

    _write_prefixes = ("write", "mutate", "set", "update", "delete", "request_mutation")

    def __init__(self, wrapped: Any) -> None:
        self.wrapped = wrapped
        self.read_calls: list[tuple[str, str]] = []
        self.write_attempts: list[str] = []

    def read_section(self, session_id: str, section: str) -> Any:
        self.read_calls.append((session_id, section))
        return self.wrapped.read_section(session_id, section)

    def read_sections(self, session_id: str, names: list[str]) -> Any:
        for name in names:
            self.read_calls.append((session_id, name))
        return self.wrapped.read_sections(session_id, names)

    def get_snapshot(self, session_id: str) -> Any:
        self.read_calls.append((session_id, "*"))
        return self.wrapped.get_snapshot(session_id)

    def __getattr__(self, name: str) -> Any:
        if name.startswith(self._write_prefixes):
            self.write_attempts.append(name)
            raise AttributeError(name)
        return getattr(self.wrapped, name)


def _install_state_reader_proxy(fabric: Any, proxy: _ReadOnlyTrackingStateReader) -> None:
    facade = fabric.facade
    facade._context_builder._state_reader = proxy
    facade._provider_factory._port_deps["state_reader"] = proxy

    policy_engine = facade._resolver._policy_engine
    if policy_engine._affective is not None:
        policy_engine._affective._state_reader = proxy
    if policy_engine._cognitive is not None:
        policy_engine._cognitive._state_reader = proxy

    semantic = facade._validation_pipeline._semantic
    semantic._state_reader = proxy


@pytest.mark.asyncio
async def test_m3_l1_execute_emits_invoked_and_completed_with_matching_trace(
    tmp_path: Path,
) -> None:
    session_id = "m3l1"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        fabric = session.fabric

        capability_name = "tool.execute.m3_l1_trace"
        provider_id = "m3-l1-local-provider"
        _register_contract_with_provider(fabric, _make_contract(capability_name, provider_id))

        captured: list[Any] = []
        handles = [
            session.bus.subscribe(TOPIC_CAPABILITY_INVOKED, captured.append),
            session.bus.subscribe(TOPIC_CAPABILITY_COMPLETED, captured.append),
        ]
        try:
            trace_id = "trace-m3-l1"
            request = _make_request(capability_name, session_id, trace_id)
            result = await fabric.execute(request)
            await _flush_bus_tasks(session.bus)

            assert result.success is True
            assert result.trace_id == trace_id
            assert result.provider_id == provider_id

            await _wait_until(
                lambda: len(captured) == 2,
                "Fabric did not publish invoked and completed events",
            )
            topics = [envelope.topic for envelope in captured]
            assert topics == [TOPIC_CAPABILITY_INVOKED, TOPIC_CAPABILITY_COMPLETED]

            payloads = [_decode_payload(envelope) for envelope in captured]
            assert {payload["request_id"] for payload in payloads} == {request.request_id}
            assert {payload["cognitive_trace_id"] for payload in payloads} == {trace_id}
            assert {envelope.cognitive_trace_id for envelope in captured} == {trace_id}
            assert payloads[0]["session_id"] == session_id
            assert payloads[1]["provider_id"] == provider_id
        finally:
            for handle in handles:
                session.bus.unsubscribe(handle)
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="M3-L2 GAP: missing safety_band silently defaults to GREEN instead of rejecting",
)
async def test_m3_l2_missing_safety_band_is_rejected_instead_of_defaulting_green(
    tmp_path: Path,
) -> None:
    session_id = "m3l2"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        fabric = session.fabric

        capability_name = "tool.execute.m3_l2_missing_band"
        provider_id = "m3-l2-local-provider"
        _register_contract_with_provider(fabric, _make_contract(capability_name, provider_id))

        raw_request = {
            "capability_name": capability_name,
            "params": {"input_a": "missing safety band"},
            "tier": Tier.LOW.value,
            "caller": "m3-live-test",
            "caller_id": "m3-live-test",
            "trace_id": "trace-m3-l2",
            "session_id": session_id,
        }
        assert "safety_band" not in raw_request
        request = CapabilityRequest.from_dict(raw_request)
        assert request.safety_band == SafetyBand.GREEN.value

        result = await fabric.execute(request)
        await _flush_bus_tasks(session.bus)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "missing_safety_band"
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m3_l3_fabric_circuit_breaker_open_half_open_closed_probe(
    tmp_path: Path,
) -> None:
    session_id = "m3l3"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        fabric = session.fabric

        capability_name = "tool.execute.m3_l3_cb"
        provider_id = "m3-l3-cb-provider"
        provider = _SequencedProvider(provider_id, outcomes=[False, False, True])
        fabric.facade._provider_factory.register_handler(
            ProviderType.LOCAL_STUB.value,
            lambda _config, **_deps: provider,
        )
        _register_contract_with_provider(fabric, _make_contract(capability_name, provider_id))

        breaker = CircuitBreaker(
            provider_id,
            CircuitBreakerConfig(
                timeout_ms=1_000,
                failure_threshold=2,
                failure_window_ms=10_000,
                half_open_after_ms=60_000,
                max_retries=0,
                fallback_error_code="m3_cb_open",
            ),
        )
        fabric.facade._circuit_breakers[provider_id] = breaker

        first = await fabric.execute(_make_request(capability_name, session_id, "trace-m3-l3-1"))
        assert first.success is False
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 1

        second = await fabric.execute(_make_request(capability_name, session_id, "trace-m3-l3-2"))
        assert second.success is False
        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.failure_count == 2
        assert provider.calls == 2

        blocked = await fabric.execute(_make_request(capability_name, session_id, "trace-m3-l3-3"))
        assert blocked.success is False
        assert blocked.error is not None
        assert blocked.error.code == "m3_cb_open"
        assert provider.calls == 2

        breaker.allow_probe()
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        probe = await fabric.execute(_make_request(capability_name, session_id, "trace-m3-l3-4"))
        assert probe.success is True
        assert provider.calls == 3
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)


@pytest.mark.asyncio
async def test_m3_l4_state_reader_proxy_is_read_only_during_fabric_execute(
    tmp_path: Path,
) -> None:
    session_id = "m3l4"
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        fabric = session.fabric

        original_reader = fabric.facade._context_builder._state_reader
        proxy = _ReadOnlyTrackingStateReader(original_reader)
        _install_state_reader_proxy(fabric, proxy)

        capability_name = "tool.execute.m3_l4_read_only"
        provider_id = "m3-l4-local-provider"
        _register_contract_with_provider(
            fabric,
            _make_contract(
                capability_name,
                provider_id,
                required_context=["affective_now", "cognitive", "control"],
            ),
        )

        result = await fabric.execute(_make_request(capability_name, session_id, "trace-m3-l4"))
        await _flush_bus_tasks(session.bus)

        assert result.success is True
        assert proxy.read_calls
        assert (session_id, "affective_now") in proxy.read_calls
        assert (session_id, "cognitive") in proxy.read_calls
        assert proxy.write_attempts == []
        assert not hasattr(proxy, "write_section")
        assert not hasattr(proxy, "request_mutation")
    finally:
        await _cleanup_service(svc, session_id, baseline_tasks)
