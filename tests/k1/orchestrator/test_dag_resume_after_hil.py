"""DAG resume after HIL override response (E6 / M1.6).

Integration tests covering the new E6 semantics where ExecutionMonitor
awaits IHILPort.request_override and the OverrideResponse drives the
GuardAction:
  * choice='override' (and not timed_out) -> CONTINUE (resume)
  * choice='abort'    -> HARD_STOP        (cancel/abort)
  * timed_out=True    -> CONTINUE         (silence == proceed)
"""

from __future__ import annotations

from typing import List

import pytest

from k1.hil.types import OverrideRequest, OverrideResponse
from k1.orchestrator.orchestration.guards.execution_monitor import ExecutionMonitor
from k1.orchestrator.types import (
    CapabilityResult,
    ProcessingContext,
    StepResult,
    StepStatus,
    WaveResult,
)


class _FakeDelta:
    async def emit(self, event_topic, payload, trace_id) -> None:  # type: ignore[no-untyped-def]
        return None

    async def emit_progress(self, step_id, summary, trace_id) -> None:  # type: ignore[no-untyped-def]
        return None


class _FakeHILPort:
    def __init__(self, response: OverrideResponse) -> None:
        self.calls: List[OverrideRequest] = []
        self._response = response

    async def request_override(self, req: OverrideRequest) -> OverrideResponse:
        self.calls.append(req)
        return self._response


def _wave(step_count: int = 4, duration_ms: int = 100) -> WaveResult:
    cap = CapabilityResult(
        request_id="req-1",
        trace_id="trace-1",
        success=True,
        data={"ok": True},
        provider_id="test",
        duration_ms=10,
    )
    results = [
        StepResult(
            step_id=f"s{i}",
            capability_name="cap.x",
            status=StepStatus.COMPLETED,
            duration_ms=10,
            result=cap,
        )
        for i in range(step_count)
    ]
    return WaveResult(wave_index=0, step_results=results, duration_ms=duration_ms)


def _ctx() -> ProcessingContext:
    return ProcessingContext(
        trace_id="trace-1",
        request_id="req-1",
        tier="HIGH",
        dag_id="dag-1",
    )


@pytest.mark.asyncio
async def test_wave_with_hil_resumes_on_user_approval() -> None:
    hil = _FakeHILPort(
        OverrideResponse(hil_request_id="r1", choice="override", timed_out=False)
    )
    monitor = ExecutionMonitor(delta=_FakeDelta(), hil_port=hil)

    decision = await monitor.after_wave(_wave(), _ctx())

    assert decision.action.name == "CONTINUE"
    assert len(hil.calls) == 1


@pytest.mark.asyncio
async def test_wave_with_hil_aborts_on_user_rejection() -> None:
    hil = _FakeHILPort(
        OverrideResponse(hil_request_id="r1", choice="abort", timed_out=False)
    )
    monitor = ExecutionMonitor(delta=_FakeDelta(), hil_port=hil)

    decision = await monitor.after_wave(_wave(), _ctx())

    assert decision.action.name == "HARD_STOP"
    assert len(hil.calls) == 1


@pytest.mark.asyncio
async def test_wave_with_hil_timeout_continues() -> None:
    hil = _FakeHILPort(
        OverrideResponse(hil_request_id="r1", choice="override", timed_out=True)
    )
    monitor = ExecutionMonitor(delta=_FakeDelta(), hil_port=hil)

    decision = await monitor.after_wave(_wave(), _ctx())

    assert decision.action.name == "CONTINUE"
    assert len(hil.calls) == 1
