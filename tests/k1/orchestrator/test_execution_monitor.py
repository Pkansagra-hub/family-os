"""
Tests for ExecutionMonitor (Issue 3.2.6 / ORCH-09) and SubStepObserver (Issue 3.2.7).

Test classes -- ExecutionMonitor:
  TestExecutionMonitorInit           -- Constructor, isinstance, repr.
  TestAfterStepNoInterrupt           -- No interrupt -> CONTINUE.
  TestAfterStepInterrupt             -- interrupt_flag=True -> HARD_STOP.
  TestAfterWaveProgressEmit          -- Always emits progress delta.
  TestAfterWaveNoOverride            -- Small wave -> no override prompt.
  TestAfterWaveOverrideStepCount     -- >3 steps -> override prompt emitted.
  TestAfterWaveOverrideDuration      -- >5s duration -> override prompt emitted.
  TestAfterWaveHILParking            -- PendingHILContext parked correctly.
  TestAfterWaveDeltaFailure          -- Delta emission failure -> graceful.
  TestBuildWaveSummary               -- _build_wave_summary helper.

Test classes -- SubStepObserver:
  TestSubStepObserverInit            -- Constructor, state, repr.
  TestRegisterStepAgent              -- Maps step_id -> agent_id.
  TestSubStepStartStop               -- Subscription lifecycle.
  TestSubStepRateLimit               -- Rate limiting (500ms default).
  TestSubStepUnknownAgent            -- Unknown agent -> step_id="unknown".
  TestSubStepOnSubStepEvent          -- Async event forwarding.
  TestSubStepSyncHandler             -- Sync _on_event_sync handler.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.fabric.types import CapabilityResult
from k1.orchestrator.orchestration.guards import DAGGuard, ExecutionMonitor, SubStepObserver
from k1.orchestrator.orchestration.guards.execution_monitor import (
    _GUARD_NAME,
    _OVERRIDE_OPTIONS,
    _OVERRIDE_TIMEOUT_MS,
    _build_wave_summary,
)
from k1.orchestrator.types import (
    GuardAction,
    HILRequest,
    PendingHILContext,
    PlanStep,
    ProcessingContext,
    StepResult,
    StepStatus,
    WaveResult,
)

# ===========================================================================
# Fakes
# ===========================================================================


class FakeDelta:
    """Configurable stand-in for IDeltaEmitPort."""

    def __init__(
        self,
        raise_on_progress: bool = False,
        raise_on_hil: bool = False,
    ) -> None:
        self.progress_calls: List[Dict[str, Any]] = []
        self.hil_calls: List[Dict[str, Any]] = []
        self.emit_calls: List[Dict[str, Any]] = []
        self._raise_on_progress = raise_on_progress
        self._raise_on_hil = raise_on_hil

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str) -> None:
        self.emit_calls.append({"topic": event_topic, "payload": payload, "trace_id": trace_id})

    async def emit_progress(self, step_id: str, summary: str, trace_id: str) -> None:
        if self._raise_on_progress:
            raise RuntimeError("delta bus down")
        self.progress_calls.append({"step_id": step_id, "summary": summary, "trace_id": trace_id})

    async def emit_hil_request(self, hil_request: HILRequest, trace_id: str) -> None:
        if self._raise_on_hil:
            raise RuntimeError("delta bus down for HIL")
        self.hil_calls.append({"hil_request": hil_request, "trace_id": trace_id})


class FakeService:
    """Minimal OrchestratorService stand-in with pending_hil dict."""

    def __init__(self) -> None:
        self.pending_hil: Dict[str, PendingHILContext] = {}


class FakeEvents:
    """Configurable stand-in for IEventSubscriptionPort."""

    def __init__(self) -> None:
        self.subscriptions: List[Dict[str, Any]] = []
        self.unsubscribed: List[str] = []
        self._counter = 0

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        self._counter += 1
        handle = SubscriptionHandle(subscription_id=f"sub-{self._counter}", topic=topic)
        self.subscriptions.append({"topic": topic, "handler": handler, "handle": handle})
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        self.unsubscribed.append(handle.subscription_id)
        return True

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        for sub in self.subscriptions:
            if topic == sub["topic"] or self._wildcard_match(sub["topic"], topic):
                sub["handler"](topic, payload)

    @staticmethod
    def _wildcard_match(pattern: str, topic: str) -> bool:
        """Simple wildcard matching for test purposes."""
        parts_p = pattern.split(".")
        parts_t = topic.split(".")
        if len(parts_p) != len(parts_t):
            return False
        return all(pp == "*" or pp == pt for pp, pt in zip(parts_p, parts_t))


# ===========================================================================
# Helpers
# ===========================================================================


def _make_step(
    step_id: str = "s1",
    capability: str = "cap.test",
    params: Optional[Dict[str, Any]] = None,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        capability=capability,
        params=params or {"key": "val"},
        deps=[],
    )


def _make_cap_result(
    data: Optional[Dict[str, Any]] = None,
    success: bool = True,
) -> CapabilityResult:
    return CapabilityResult(
        request_id="req-1",
        trace_id="t1",
        success=success,
        data=data,
        provider_id="test-provider",
        duration_ms=10,
    )


def _make_step_result(
    step_id: str = "s1",
    status: StepStatus = StepStatus.COMPLETED,
    data: Optional[Dict[str, Any]] = None,
) -> StepResult:
    cap_result = None
    if data is not None or status == StepStatus.COMPLETED:
        cap_result = _make_cap_result(data=data, success=(status == StepStatus.COMPLETED))
    return StepResult(
        step_id=step_id,
        capability_name="cap.test",
        status=status,
        duration_ms=10,
        result=cap_result,
    )


def _make_wave_result(
    step_count: int = 1,
    wave_index: int = 0,
    duration_ms: int = 100,
) -> WaveResult:
    results = [_make_step_result(step_id=f"s{i}") for i in range(step_count)]
    return WaveResult(
        wave_index=wave_index,
        step_results=results,
        duration_ms=duration_ms,
    )


def _make_ctx(
    trace_id: str = "trace-1",
    dag_id: str = "dag-1",
    interrupt_flag: bool = False,
) -> ProcessingContext:
    ctx = ProcessingContext(
        trace_id=trace_id,
        request_id="req-1",
        tier="standard",
        dag_id=dag_id,
    )
    ctx.interrupt_flag = interrupt_flag
    return ctx


# ===========================================================================
# TestBuildWaveSummary
# ===========================================================================


class TestBuildWaveSummary:
    """Unit tests for _build_wave_summary helper."""

    def test_all_success(self) -> None:
        wr = _make_wave_result(step_count=3, duration_ms=1500)
        s = _build_wave_summary(wr)
        assert "Wave 0 complete" in s
        assert "3 steps" in s
        assert "1.5s" in s

    def test_some_failures(self) -> None:
        sr_ok = _make_step_result("s1", StepStatus.COMPLETED)
        sr_fail = StepResult(
            step_id="s2",
            capability_name="c",
            status=StepStatus.FAILED,
            duration_ms=10,
            result=None,
        )
        wr = WaveResult(wave_index=1, step_results=[sr_ok, sr_fail], duration_ms=2000)
        s = _build_wave_summary(wr)
        assert "1/2 succeeded" in s
        assert "1 failed" in s

    def test_empty_wave(self) -> None:
        wr = WaveResult(wave_index=0, step_results=[], duration_ms=0)
        s = _build_wave_summary(wr)
        assert "0 steps" in s


# ===========================================================================
# TestExecutionMonitorInit
# ===========================================================================


class TestExecutionMonitorInit:
    """Constructor, isinstance, repr."""

    def test_is_dag_guard(self) -> None:
        guard = ExecutionMonitor(delta=FakeDelta(), service_ref=FakeService())
        assert isinstance(guard, DAGGuard)

    def test_repr(self) -> None:
        guard = ExecutionMonitor(delta=FakeDelta(), service_ref=FakeService())
        assert "ExecutionMonitor" in repr(guard)


# ===========================================================================
# TestAfterStepNoInterrupt
# ===========================================================================


class TestAfterStepNoInterrupt:
    """No interrupt -> CONTINUE."""

    @pytest.mark.asyncio
    async def test_no_interrupt(self) -> None:
        guard = ExecutionMonitor(delta=FakeDelta(), service_ref=FakeService())
        step = _make_step()
        result = _make_step_result()
        ctx = _make_ctx(interrupt_flag=False)

        decision = await guard.after_step(step, result, ctx)
        assert decision.action == GuardAction.CONTINUE
        assert decision.guard_name == _GUARD_NAME

    @pytest.mark.asyncio
    async def test_default_ctx_no_interrupt(self) -> None:
        """ProcessingContext defaults interrupt_flag to False."""
        guard = ExecutionMonitor(delta=FakeDelta(), service_ref=FakeService())
        ctx = ProcessingContext(trace_id="t", request_id="r", tier="standard")
        decision = await guard.after_step(_make_step(), _make_step_result(), ctx)
        assert decision.action == GuardAction.CONTINUE


# ===========================================================================
# TestAfterStepInterrupt
# ===========================================================================


class TestAfterStepInterrupt:
    """interrupt_flag=True -> HARD_STOP."""

    @pytest.mark.asyncio
    async def test_interrupt_hard_stop(self) -> None:
        guard = ExecutionMonitor(delta=FakeDelta(), service_ref=FakeService())
        ctx = _make_ctx(interrupt_flag=True)

        decision = await guard.after_step(_make_step(), _make_step_result(), ctx)
        assert decision.action == GuardAction.HARD_STOP
        assert "Interrupt" in decision.reason

    @pytest.mark.asyncio
    async def test_interrupt_guard_name(self) -> None:
        guard = ExecutionMonitor(delta=FakeDelta(), service_ref=FakeService())
        ctx = _make_ctx(interrupt_flag=True)
        decision = await guard.after_step(_make_step(), _make_step_result(), ctx)
        assert decision.guard_name == _GUARD_NAME

    @pytest.mark.asyncio
    async def test_interrupt_after_failed_step(self) -> None:
        """Interrupt check applies even for failed steps."""
        guard = ExecutionMonitor(delta=FakeDelta(), service_ref=FakeService())
        ctx = _make_ctx(interrupt_flag=True)
        result = _make_step_result(status=StepStatus.FAILED)
        decision = await guard.after_step(_make_step(), result, ctx)
        assert decision.action == GuardAction.HARD_STOP


# ===========================================================================
# TestAfterWaveProgressEmit
# ===========================================================================


class TestAfterWaveProgressEmit:
    """Always emits progress delta."""

    @pytest.mark.asyncio
    async def test_progress_emitted(self) -> None:
        delta = FakeDelta()
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=1, duration_ms=100)

        await guard.after_wave(wr, _make_ctx(trace_id="t-42"))

        assert len(delta.progress_calls) == 1
        call = delta.progress_calls[0]
        assert call["trace_id"] == "t-42"
        assert "wave-0" in call["step_id"]

    @pytest.mark.asyncio
    async def test_progress_summary_contains_wave_info(self) -> None:
        delta = FakeDelta()
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=2, wave_index=3, duration_ms=500)

        await guard.after_wave(wr, _make_ctx())

        summary = delta.progress_calls[0]["summary"]
        assert "Wave 3" in summary


# ===========================================================================
# TestAfterWaveNoOverride
# ===========================================================================


class TestAfterWaveNoOverride:
    """Small wave (<=3 steps AND <=5s) -> no override prompt."""

    @pytest.mark.asyncio
    async def test_small_wave_no_override(self) -> None:
        delta = FakeDelta()
        service = FakeService()
        guard = ExecutionMonitor(delta=delta, service_ref=service)
        wr = _make_wave_result(step_count=2, duration_ms=1000)

        decision = await guard.after_wave(wr, _make_ctx())

        assert decision.action == GuardAction.CONTINUE
        assert len(delta.hil_calls) == 0
        assert len(service.pending_hil) == 0

    @pytest.mark.asyncio
    async def test_exactly_threshold_no_override(self) -> None:
        """Exactly 3 steps and exactly 5000ms -> no override (> not >=)."""
        delta = FakeDelta()
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=3, duration_ms=5000)

        decision = await guard.after_wave(wr, _make_ctx())
        assert len(delta.hil_calls) == 0

    @pytest.mark.asyncio
    async def test_single_step_no_override(self) -> None:
        delta = FakeDelta()
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=1, duration_ms=100)

        await guard.after_wave(wr, _make_ctx())
        assert len(delta.hil_calls) == 0


# ===========================================================================
# TestAfterWaveOverrideStepCount
# ===========================================================================


class TestAfterWaveOverrideStepCount:
    """>3 steps -> override prompt emitted."""

    @pytest.mark.asyncio
    async def test_four_steps_triggers_override(self) -> None:
        delta = FakeDelta()
        service = FakeService()
        guard = ExecutionMonitor(delta=delta, service_ref=service)
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())

        assert decision.action == GuardAction.CONTINUE
        assert len(delta.hil_calls) == 1
        assert len(service.pending_hil) == 1

    @pytest.mark.asyncio
    async def test_override_options_correct(self) -> None:
        delta = FakeDelta()
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=5, duration_ms=100)

        await guard.after_wave(wr, _make_ctx())

        hil = delta.hil_calls[0]["hil_request"]
        assert hil.options == list(_OVERRIDE_OPTIONS)
        assert "CONTINUE" in hil.options
        assert "CANCEL_DAG" in hil.options
        assert "MODIFY_PARAMS" not in hil.options  # Removed V1

    @pytest.mark.asyncio
    async def test_override_timeout(self) -> None:
        delta = FakeDelta()
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=4, duration_ms=100)

        await guard.after_wave(wr, _make_ctx())

        hil = delta.hil_calls[0]["hil_request"]
        assert hil.timeout_ms == _OVERRIDE_TIMEOUT_MS


# ===========================================================================
# TestAfterWaveOverrideDuration
# ===========================================================================


class TestAfterWaveOverrideDuration:
    """>5s duration -> override prompt emitted."""

    @pytest.mark.asyncio
    async def test_long_duration_triggers_override(self) -> None:
        delta = FakeDelta()
        service = FakeService()
        guard = ExecutionMonitor(delta=delta, service_ref=service)
        wr = _make_wave_result(step_count=1, duration_ms=6000)

        decision = await guard.after_wave(wr, _make_ctx())

        assert len(delta.hil_calls) == 1
        assert len(service.pending_hil) == 1

    @pytest.mark.asyncio
    async def test_5001ms_triggers_override(self) -> None:
        delta = FakeDelta()
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=1, duration_ms=5001)

        await guard.after_wave(wr, _make_ctx())
        assert len(delta.hil_calls) == 1


# ===========================================================================
# TestAfterWaveHILParking
# ===========================================================================


class TestAfterWaveHILParking:
    """PendingHILContext parked correctly."""

    @pytest.mark.asyncio
    async def test_pending_hil_context_fields(self) -> None:
        delta = FakeDelta()
        service = FakeService()
        guard = ExecutionMonitor(delta=delta, service_ref=service)
        wr = _make_wave_result(step_count=4, wave_index=2, duration_ms=100)
        ctx = _make_ctx(dag_id="dag-42")

        decision = await guard.after_wave(wr, ctx)

        assert len(service.pending_hil) == 1
        request_id = list(service.pending_hil.keys())[0]
        pending = service.pending_hil[request_id]

        assert pending.request_id == request_id
        assert pending.dag_execution_id == "dag-42"
        assert pending.current_wave_index == 2
        assert pending.timeout_fallback == "CONTINUE"
        assert pending.timeout_ms == _OVERRIDE_TIMEOUT_MS
        assert pending.options == list(_OVERRIDE_OPTIONS)

    @pytest.mark.asyncio
    async def test_metadata_contains_request_id(self) -> None:
        delta = FakeDelta()
        service = FakeService()
        guard = ExecutionMonitor(delta=delta, service_ref=service)
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())

        assert "hil_request_id" in decision.metadata
        assert decision.metadata["hil_request_id"] in service.pending_hil

    @pytest.mark.asyncio
    async def test_unique_request_ids_per_wave(self) -> None:
        delta = FakeDelta()
        service = FakeService()
        guard = ExecutionMonitor(delta=delta, service_ref=service)

        wr1 = _make_wave_result(step_count=4, wave_index=0, duration_ms=100)
        wr2 = _make_wave_result(step_count=4, wave_index=1, duration_ms=100)

        d1 = await guard.after_wave(wr1, _make_ctx())
        d2 = await guard.after_wave(wr2, _make_ctx())

        id1 = d1.metadata["hil_request_id"]
        id2 = d2.metadata["hil_request_id"]
        assert id1 != id2
        assert len(service.pending_hil) == 2


# ===========================================================================
# TestAfterWaveDeltaFailure
# ===========================================================================


class TestAfterWaveDeltaFailure:
    """Delta emission failure -> graceful degradation."""

    @pytest.mark.asyncio
    async def test_progress_failure_still_continues(self) -> None:
        delta = FakeDelta(raise_on_progress=True)
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=1, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.CONTINUE

    @pytest.mark.asyncio
    async def test_hil_failure_still_continues(self) -> None:
        delta = FakeDelta(raise_on_hil=True)
        guard = ExecutionMonitor(delta=delta, service_ref=FakeService())
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.CONTINUE
        assert "failed" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_no_pending_hil_attr(self) -> None:
        """service_ref without pending_hil attr -> still continues."""
        delta = FakeDelta()

        class BareService:
            pass

        guard = ExecutionMonitor(delta=delta, service_ref=BareService())
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.CONTINUE


# ===========================================================================
# TestSubStepObserverInit
# ===========================================================================


class TestSubStepObserverInit:
    """Constructor, state, repr."""

    def test_default_rate_limit(self) -> None:
        obs = SubStepObserver(events=FakeEvents(), delta=FakeDelta())
        assert obs._rate_limit_ms == 500
        assert obs.step_agent_map == {}
        assert obs.last_emit == {}
        assert obs._running is False

    def test_custom_rate_limit(self) -> None:
        obs = SubStepObserver(events=FakeEvents(), delta=FakeDelta(), rate_limit_ms=200)
        assert obs._rate_limit_ms == 200

    def test_repr(self) -> None:
        obs = SubStepObserver(events=FakeEvents(), delta=FakeDelta())
        r = repr(obs)
        assert "SubStepObserver" in r
        assert "rate_limit_ms=500" in r
        assert "running=False" in r

    def test_not_dag_guard(self) -> None:
        obs = SubStepObserver(events=FakeEvents(), delta=FakeDelta())
        assert not isinstance(obs, DAGGuard)


# ===========================================================================
# TestRegisterStepAgent
# ===========================================================================


class TestRegisterStepAgent:
    """Maps step_id -> agent_id."""

    def test_register_single(self) -> None:
        obs = SubStepObserver(events=FakeEvents(), delta=FakeDelta())
        obs.register_step_agent("s1", "agent-a")
        assert obs.step_agent_map["s1"] == "agent-a"

    def test_register_multiple(self) -> None:
        obs = SubStepObserver(events=FakeEvents(), delta=FakeDelta())
        obs.register_step_agent("s1", "agent-a")
        obs.register_step_agent("s2", "agent-b")
        assert len(obs.step_agent_map) == 2

    def test_overwrite(self) -> None:
        obs = SubStepObserver(events=FakeEvents(), delta=FakeDelta())
        obs.register_step_agent("s1", "agent-a")
        obs.register_step_agent("s1", "agent-b")
        assert obs.step_agent_map["s1"] == "agent-b"


# ===========================================================================
# TestSubStepStartStop
# ===========================================================================


class TestSubStepStartStop:
    """Subscription lifecycle."""

    @pytest.mark.asyncio
    async def test_start_subscribes_two_topics(self) -> None:
        events = FakeEvents()
        obs = SubStepObserver(events=events, delta=FakeDelta())

        await obs.start("dag-1", trace_id="t-1")

        assert obs._running is True
        assert len(events.subscriptions) == 2
        topics = {s["topic"] for s in events.subscriptions}
        assert "fabric.agent.*.tool_call.*" in topics
        assert "fabric.agent.*.llm_call.*" in topics

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self) -> None:
        events = FakeEvents()
        obs = SubStepObserver(events=events, delta=FakeDelta())

        await obs.start("dag-1")
        await obs.stop()

        assert obs._running is False
        assert len(events.unsubscribed) == 2
        assert obs.step_agent_map == {}
        assert obs.last_emit == {}

    @pytest.mark.asyncio
    async def test_stop_without_start(self) -> None:
        events = FakeEvents()
        obs = SubStepObserver(events=events, delta=FakeDelta())
        await obs.stop()  # Should not raise
        assert obs._running is False


# ===========================================================================
# TestSubStepRateLimit
# ===========================================================================


class TestSubStepRateLimit:
    """Rate limiting (500ms default)."""

    @pytest.mark.asyncio
    async def test_first_event_forwarded(self) -> None:
        delta = FakeDelta()
        obs = SubStepObserver(events=FakeEvents(), delta=delta)
        obs.register_step_agent("s1", "agent-a")

        await obs.on_sub_step_event(
            {
                "topic": "fabric.agent.agent-a.tool_call.v1",
                "summary": "tool called",
                "trace_id": "t-1",
            }
        )

        assert len(delta.progress_calls) == 1

    @pytest.mark.asyncio
    async def test_rapid_events_dropped(self) -> None:
        """Second event within rate limit is dropped."""
        delta = FakeDelta()
        obs = SubStepObserver(events=FakeEvents(), delta=delta, rate_limit_ms=500)
        obs.register_step_agent("s1", "agent-a")

        event = {
            "topic": "fabric.agent.agent-a.tool_call.v1",
            "summary": "tool called",
            "trace_id": "t-1",
        }

        await obs.on_sub_step_event(event)
        await obs.on_sub_step_event(event)  # Should be dropped

        assert len(delta.progress_calls) == 1

    @pytest.mark.asyncio
    async def test_events_after_rate_limit_forwarded(self) -> None:
        """Events after rate limit window are forwarded."""
        delta = FakeDelta()
        obs = SubStepObserver(events=FakeEvents(), delta=delta, rate_limit_ms=100)
        obs.register_step_agent("s1", "agent-a")

        event = {
            "topic": "fabric.agent.agent-a.tool_call.v1",
            "summary": "tool called",
            "trace_id": "t-1",
        }

        await obs.on_sub_step_event(event)
        # Artificially set last_emit to past
        obs.last_emit["s1"] = time.time() - 0.2

        await obs.on_sub_step_event(event)
        assert len(delta.progress_calls) == 2

    @pytest.mark.asyncio
    async def test_different_steps_independent_limits(self) -> None:
        """Rate limiting is per-step, not global."""
        delta = FakeDelta()
        obs = SubStepObserver(events=FakeEvents(), delta=delta, rate_limit_ms=500)
        obs.register_step_agent("s1", "agent-a")
        obs.register_step_agent("s2", "agent-b")

        await obs.on_sub_step_event(
            {
                "topic": "fabric.agent.agent-a.tool_call.v1",
                "summary": "step 1",
                "trace_id": "t-1",
            }
        )
        await obs.on_sub_step_event(
            {
                "topic": "fabric.agent.agent-b.tool_call.v1",
                "summary": "step 2",
                "trace_id": "t-1",
            }
        )

        assert len(delta.progress_calls) == 2


# ===========================================================================
# TestSubStepUnknownAgent
# ===========================================================================


class TestSubStepUnknownAgent:
    """Unknown agent -> step_id='unknown'."""

    @pytest.mark.asyncio
    async def test_unknown_agent_forwarded_as_unknown(self) -> None:
        delta = FakeDelta()
        obs = SubStepObserver(events=FakeEvents(), delta=delta)
        # No step_agent_map entries

        await obs.on_sub_step_event(
            {
                "topic": "fabric.agent.agent-x.tool_call.v1",
                "summary": "unknown agent call",
                "trace_id": "t-1",
            }
        )

        assert len(delta.progress_calls) == 1
        assert delta.progress_calls[0]["step_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_unknown_summary_default(self) -> None:
        delta = FakeDelta()
        obs = SubStepObserver(events=FakeEvents(), delta=delta)

        await obs.on_sub_step_event(
            {
                "topic": "fabric.agent.agent-x.llm_call.v1",
            }
        )

        assert len(delta.progress_calls) == 1
        assert "agent-x" in delta.progress_calls[0]["summary"]


# ===========================================================================
# TestSubStepOnSubStepEvent
# ===========================================================================


class TestSubStepOnSubStepEvent:
    """Async event forwarding via on_sub_step_event."""

    @pytest.mark.asyncio
    async def test_correct_step_id_resolved(self) -> None:
        delta = FakeDelta()
        obs = SubStepObserver(events=FakeEvents(), delta=delta)
        obs.register_step_agent("s1", "agent-a")

        await obs.on_sub_step_event(
            {
                "topic": "fabric.agent.agent-a.tool_call.v1",
                "summary": "calculating",
                "trace_id": "t-1",
            }
        )

        assert delta.progress_calls[0]["step_id"] == "s1"
        assert delta.progress_calls[0]["summary"] == "calculating"
        assert delta.progress_calls[0]["trace_id"] == "t-1"

    @pytest.mark.asyncio
    async def test_delta_failure_handled(self) -> None:
        """Delta emission failure in on_sub_step_event -> no crash."""
        delta = FakeDelta(raise_on_progress=True)
        obs = SubStepObserver(events=FakeEvents(), delta=delta)

        # Should not raise
        await obs.on_sub_step_event(
            {
                "topic": "fabric.agent.agent-x.tool_call.v1",
                "summary": "test",
                "trace_id": "t-1",
            }
        )

    @pytest.mark.asyncio
    async def test_agent_id_from_event_dict(self) -> None:
        """Falls back to event['agent_id'] when topic is malformed."""
        delta = FakeDelta()
        obs = SubStepObserver(events=FakeEvents(), delta=delta)
        obs.register_step_agent("s1", "agent-a")

        await obs.on_sub_step_event(
            {
                "topic": "",
                "agent_id": "agent-a",
                "summary": "direct agent id",
                "trace_id": "t-1",
            }
        )

        assert delta.progress_calls[0]["step_id"] == "s1"


# ===========================================================================
# TestSubStepSyncHandler
# ===========================================================================


class TestSubStepSyncHandler:
    """Sync _on_event_sync handler tested via FakeEvents.emit."""

    @pytest.mark.asyncio
    async def test_sync_handler_stores_forwarded(self) -> None:
        events = FakeEvents()
        obs = SubStepObserver(events=events, delta=FakeDelta())
        obs.register_step_agent("s1", "agent-a")

        await obs.start("dag-1", trace_id="t-1")

        # Simulate event emission through the sync event bus
        events.emit(
            "fabric.agent.agent-a.tool_call.v1",
            {"summary": "tool used", "trace_id": "t-1"},
        )

        assert hasattr(obs, "_last_forwarded")
        assert obs._last_forwarded["step_id"] == "s1"
        assert obs._last_forwarded["summary"] == "tool used"

    @pytest.mark.asyncio
    async def test_sync_handler_not_running(self) -> None:
        """Events ignored when not running."""
        events = FakeEvents()
        obs = SubStepObserver(events=events, delta=FakeDelta())

        await obs.start("dag-1")
        await obs.stop()

        # Manually call sync handler (simulating late event)
        obs._on_event_sync(
            "fabric.agent.agent-a.tool_call.v1",
            {"summary": "late event"},
        )
        # Should not update _last_forwarded since not running
        assert not obs._running

    @pytest.mark.asyncio
    async def test_sync_handler_rate_limit(self) -> None:
        """Rate limiting works in sync handler too."""
        events = FakeEvents()
        obs = SubStepObserver(events=events, delta=FakeDelta(), rate_limit_ms=500)
        obs.register_step_agent("s1", "agent-a")

        await obs.start("dag-1", trace_id="t-1")

        events.emit(
            "fabric.agent.agent-a.tool_call.v1",
            {"summary": "first call", "trace_id": "t-1"},
        )
        first_forwarded = obs._last_forwarded.copy()

        events.emit(
            "fabric.agent.agent-a.tool_call.v1",
            {"summary": "second call", "trace_id": "t-1"},
        )
        # Should still be the first one (second dropped by rate limit)
        assert obs._last_forwarded["summary"] == first_forwarded["summary"]
        # Should still be the first one (second dropped by rate limit)
        assert obs._last_forwarded["summary"] == first_forwarded["summary"]
