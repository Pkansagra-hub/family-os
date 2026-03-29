"""Epic 7.3.1 -- MEDIUM tier end-to-end integration tests.

Goal:
- Validate MEDIUM tier flow strictly via OrchestratorService.process().
- Use OrchestratorFactory-created service with real in-memory test adapters.
- Assert behavior through adapter capture logs (fabric, delta/event streams).

Notes:
- Current ORCH-10 invariant enforces max 2 capabilities for MEDIUM.
  Therefore, this suite validates 1-2 capability happy/error paths and
  explicitly verifies >2 is rejected.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_TASK_ACCEPTED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    AdapterError,
    ErrorSeverity,
    ProcessResult,
    RegistryEntry,
    TaskEnvelope,
)
from tests.k1.orchestrator.helpers import cap_result


def _assert_dag_completed_payload_shape(payload: dict) -> None:
    required = {
        "trace_id",
        "success",
        "completed",
        "failed",
        "cancelled",
        "skipped",
    }
    missing = sorted(required.difference(payload.keys()))
    assert not missing, f"Missing ORCH_DAG_COMPLETED payload keys: {missing}"


async def _svc():
    """Create standalone orchestrator and return service + test adapters."""
    service = await OrchestratorFactory.create_standalone()
    fabric = service._fabric_port
    delta = service._delta_port
    event = service._event_port
    return service, fabric, delta, event


def _register_capability(fabric, *names: str) -> None:
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


def _medium_envelope(*, capabilities: list[str], trace_id: str | None = None) -> TaskEnvelope:
    tid = trace_id or str(uuid4())
    return TaskEnvelope(
        intent="medium-e2e",
        trace_id=tid,
        tier="MEDIUM",
        capabilities=capabilities,
        params={cap: {"q": cap} for cap in capabilities},
        context={"session_id": "s-medium-e2e"},
    )


def _unsafe_medium_envelope_with_3_caps(trace_id: str) -> TaskEnvelope:
    """Build intentionally invalid MEDIUM envelope (bypass dataclass validation)."""
    envelope = TaskEnvelope.__new__(TaskEnvelope)
    object.__setattr__(envelope, "intent", "medium-e2e")
    object.__setattr__(envelope, "trace_id", trace_id)
    object.__setattr__(envelope, "tier", "MEDIUM")
    object.__setattr__(envelope, "capabilities", ["cap.a", "cap.b", "cap.c"])
    object.__setattr__(envelope, "params", {"cap.a": {}, "cap.b": {}, "cap.c": {}})
    object.__setattr__(envelope, "context", {"session_id": "s-medium-e2e"})
    object.__setattr__(envelope, "constraints", {})
    object.__setattr__(envelope, "timeout_ms", 30_000)
    object.__setattr__(envelope, "caller_id", "")
    object.__setattr__(envelope, "envelope_id", str(uuid4()))
    return envelope


class TestMediumTierE2E:
    """End-to-end MEDIUM tier scenarios via process()."""

    @pytest.mark.asyncio
    async def test_single_capability_success(self) -> None:
        service, fabric, delta, _ = await _svc()
        _register_capability(fabric, "tool.medium.one")

        result = await service.process(_medium_envelope(capabilities=["tool.medium.one"]))

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("tool.medium.one", times=1)
        delta.assert_emitted(ORCH_DAG_COMPLETED, count=1)

    @pytest.mark.asyncio
    async def test_two_capability_success(self) -> None:
        service, fabric, _, _ = await _svc()
        _register_capability(fabric, "tool.medium.a", "tool.medium.b")

        result = await service.process(
            _medium_envelope(capabilities=["tool.medium.a", "tool.medium.b"])
        )

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("tool.medium.a", times=1)
        fabric.assert_called("tool.medium.b", times=1)

    @pytest.mark.asyncio
    async def test_one_of_two_fails_returns_degraded(self) -> None:
        service, fabric, delta, _ = await _svc()
        _register_capability(fabric, "tool.medium.ok", "tool.medium.fail")
        fabric.script_result("tool.medium.ok", cap_result({"ok": True}))
        fabric.script_result("tool.medium.fail", cap_result(success=False))

        result = await service.process(
            _medium_envelope(capabilities=["tool.medium.ok", "tool.medium.fail"])
        )

        assert result == ProcessResult.DEGRADED
        payload = delta.get_emitted(ORCH_DAG_COMPLETED)[0]
        _assert_dag_completed_payload_shape(payload)
        assert payload["completed"] == 1
        assert payload["failed"] == 1

    @pytest.mark.asyncio
    async def test_all_fail_returns_failed(self) -> None:
        service, fabric, delta, _ = await _svc()
        _register_capability(fabric, "tool.medium.f1", "tool.medium.f2")
        fabric.script_result("tool.medium.f1", cap_result(success=False))
        fabric.script_result("tool.medium.f2", cap_result(success=False))

        result = await service.process(
            _medium_envelope(capabilities=["tool.medium.f1", "tool.medium.f2"])
        )

        assert result == ProcessResult.FAILED
        payload = delta.get_emitted(ORCH_DAG_COMPLETED)[0]
        _assert_dag_completed_payload_shape(payload)
        assert payload["completed"] == 0
        assert payload["failed"] == 2

    @pytest.mark.asyncio
    async def test_invalid_capability_rejected_before_execute(self) -> None:
        service, fabric, _, _ = await _svc()
        _register_capability(fabric, "tool.medium.valid")

        result = await service.process(
            _medium_envelope(capabilities=["tool.medium.valid", "tool.medium.unknown"])
        )

        assert result == ProcessResult.FAILED
        # Validation fails before execution loop.
        assert len(fabric.call_log) == 0

    @pytest.mark.asyncio
    async def test_trace_id_propagates_to_fabric_and_emitted_events(self) -> None:
        service, fabric, delta, _ = await _svc()
        trace_id = str(uuid4())
        _register_capability(fabric, "tool.medium.trace")

        result = await service.process(
            _medium_envelope(capabilities=["tool.medium.trace"], trace_id=trace_id)
        )

        assert result == ProcessResult.COMPLETED
        assert len(fabric.call_log) == 1
        assert fabric.call_log[0].trace_id == trace_id

        # Emitted orchestrator events include trace_id in payload and envelope.
        accepted = delta.get_emitted(ORCH_TASK_ACCEPTED)
        completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert accepted and completed
        assert accepted[0]["trace_id"] == trace_id
        _assert_dag_completed_payload_shape(completed[0])
        assert completed[0]["trace_id"] == trace_id

        for topic, _, emitted_trace_id in delta.emitted:
            if topic in (ORCH_TASK_ACCEPTED, ORCH_DAG_COMPLETED):
                assert emitted_trace_id == trace_id

    @pytest.mark.asyncio
    async def test_task_lifecycle_events_emitted(self) -> None:
        service, fabric, delta, _ = await _svc()
        _register_capability(fabric, "tool.medium.events")

        result = await service.process(_medium_envelope(capabilities=["tool.medium.events"]))

        assert result == ProcessResult.COMPLETED
        delta.assert_emitted(ORCH_TASK_ACCEPTED, count=1)
        delta.assert_emitted(ORCH_DAG_COMPLETED, count=1)

    @pytest.mark.asyncio
    async def test_per_step_isolation_execute_error_still_attempts_other_step(self) -> None:
        service, fabric, _, _ = await _svc()
        _register_capability(fabric, "tool.medium.err", "tool.medium.ok")
        fabric.script_error(
            "tool.medium.err",
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="fabric",
                operation="execute",
                error_code="TIMEOUT",
                error_message="timeout",
            ),
        )

        result = await service.process(
            _medium_envelope(capabilities=["tool.medium.err", "tool.medium.ok"])
        )

        assert result == ProcessResult.DEGRADED
        fabric.assert_called("tool.medium.err", times=1)
        fabric.assert_called("tool.medium.ok", times=1)

    @pytest.mark.asyncio
    async def test_medium_orch10_more_than_two_capabilities_rejected(self) -> None:
        service, fabric, _, _ = await _svc()
        envelope = _unsafe_medium_envelope_with_3_caps(trace_id=str(uuid4()))

        result = await service.process(envelope)

        assert result == ProcessResult.FAILED
        assert len(fabric.call_log) == 0

    @pytest.mark.asyncio
    async def test_params_forwarded_per_capability(self) -> None:
        service, fabric, _, _ = await _svc()
        _register_capability(fabric, "tool.medium.p1", "tool.medium.p2")
        envelope = TaskEnvelope(
            intent="medium-e2e",
            trace_id=str(uuid4()),
            tier="MEDIUM",
            capabilities=["tool.medium.p1", "tool.medium.p2"],
            params={
                "tool.medium.p1": {"a": 1},
                "tool.medium.p2": {"b": 2},
            },
            context={"session_id": "s-medium-e2e"},
        )

        result = await service.process(envelope)

        assert result == ProcessResult.COMPLETED
        by_cap = {r.capability_name: r.params for r in fabric.call_log}
        assert by_cap["tool.medium.p1"] == {"a": 1}
        assert by_cap["tool.medium.p2"] == {"b": 2}
