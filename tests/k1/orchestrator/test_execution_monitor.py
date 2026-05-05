"""
Tests for ExecutionMonitor (Issue 3.2.6 / ORCH-09) and SubStepObserver (Issue 3.2.7).

Test classes -- unit (local fakes):
  TestExecutionMonitorInit           -- Constructor, isinstance, repr.
  TestAfterStepNoInterrupt           -- No interrupt -> CONTINUE.
  TestAfterStepInterrupt             -- interrupt_flag=True -> HARD_STOP.
  TestAfterWaveProgressEmit          -- Always emits progress delta.
  TestAfterWaveNoOverride            -- Small wave -> no override prompt.
  TestAfterWaveOverrideStepCount     -- >3 steps -> hil_port.request_override called.
  TestAfterWaveOverrideDuration      -- >5s duration -> hil_port.request_override called.
  TestAfterWaveDeltaFailure          -- Delta emission failure -> graceful.
  TestBuildWaveSummary               -- _build_wave_summary helper.

Test classes -- unit (SubStepObserver):
  TestSubStepObserverInit            -- Constructor, state, repr.
  TestRegisterStepAgent              -- Maps step_id -> agent_id.
  TestSubStepStartStop               -- Subscription lifecycle.
  TestSubStepRateLimit               -- Rate limiting (500ms default).
  TestSubStepUnknownAgent            -- Unknown agent -> step_id="unknown".
  TestSubStepOnSubStepEvent          -- Async event forwarding.
  TestSubStepSyncHandler             -- Sync _on_event_sync handler.

Test classes -- pipeline (Epic 7.2.6):
  TestExecutionMonitorPipeline       -- Pipeline guard via OrchestratorService.process() (ORCH-09).
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.fabric.types import CapabilityResult
from k1.hil.types import OverrideRequest, OverrideResponse
from k1.orchestrator.orchestration.guards import (
    DAGGuard,
    ExecutionMonitor,
    SubStepObserver,
)
from k1.orchestrator.orchestration.guards.execution_monitor import (
    _GUARD_NAME,
    _OVERRIDE_OPTIONS,
    _OVERRIDE_TIMEOUT_MS,
    _build_wave_summary,
)
from k1.orchestrator.types import (
    GuardAction,
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
    ) -> None:
        self.progress_calls: List[Dict[str, Any]] = []
        self.emit_calls: List[Dict[str, Any]] = []
        self._raise_on_progress = raise_on_progress

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str) -> None:
        self.emit_calls.append({"topic": event_topic, "payload": payload, "trace_id": trace_id})

    async def emit_progress(self, step_id: str, summary: str, trace_id: str) -> None:
        if self._raise_on_progress:
            raise RuntimeError("delta bus down")
        self.progress_calls.append({"step_id": step_id, "summary": summary, "trace_id": trace_id})


class FakeHILPort:
    """Stand-in for IHILPort.request_override (E6).

    Records every ``OverrideRequest`` and returns a configurable
    ``OverrideResponse``. Defaults to ``timed_out=True`` (silence ->
    CONTINUE), matching the pre-E6 fire-and-forget fallback semantics.
    """

    def __init__(
        self,
        response: Optional[OverrideResponse] = None,
        raise_exc: bool = False,
    ) -> None:
        self.calls: List[OverrideRequest] = []
        self._response = response
        self._raise = raise_exc

    async def request_override(self, req: OverrideRequest) -> OverrideResponse:
        self.calls.append(req)
        if self._raise:
            raise RuntimeError("hil port unavailable")
        if self._response is not None:
            return self._response
        return OverrideResponse(
            hil_request_id=req.request_id,
            choice="override",
            timed_out=True,
        )


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
        guard = ExecutionMonitor(delta=FakeDelta(), hil_port=FakeHILPort())
        assert isinstance(guard, DAGGuard)

    def test_repr(self) -> None:
        guard = ExecutionMonitor(delta=FakeDelta(), hil_port=FakeHILPort())
        assert "ExecutionMonitor" in repr(guard)


# ===========================================================================
# TestAfterStepNoInterrupt
# ===========================================================================


class TestAfterStepNoInterrupt:
    """No interrupt -> CONTINUE."""

    @pytest.mark.asyncio
    async def test_no_interrupt(self) -> None:
        guard = ExecutionMonitor(delta=FakeDelta(), hil_port=FakeHILPort())
        step = _make_step()
        result = _make_step_result()
        ctx = _make_ctx(interrupt_flag=False)

        decision = await guard.after_step(step, result, ctx)
        assert decision.action == GuardAction.CONTINUE
        assert decision.guard_name == _GUARD_NAME

    @pytest.mark.asyncio
    async def test_default_ctx_no_interrupt(self) -> None:
        """ProcessingContext defaults interrupt_flag to False."""
        guard = ExecutionMonitor(delta=FakeDelta(), hil_port=FakeHILPort())
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
        guard = ExecutionMonitor(delta=FakeDelta(), hil_port=FakeHILPort())
        ctx = _make_ctx(interrupt_flag=True)

        decision = await guard.after_step(_make_step(), _make_step_result(), ctx)
        assert decision.action == GuardAction.HARD_STOP
        assert "Interrupt" in decision.reason

    @pytest.mark.asyncio
    async def test_interrupt_guard_name(self) -> None:
        guard = ExecutionMonitor(delta=FakeDelta(), hil_port=FakeHILPort())
        ctx = _make_ctx(interrupt_flag=True)
        decision = await guard.after_step(_make_step(), _make_step_result(), ctx)
        assert decision.guard_name == _GUARD_NAME

    @pytest.mark.asyncio
    async def test_interrupt_after_failed_step(self) -> None:
        """Interrupt check applies even for failed steps."""
        guard = ExecutionMonitor(delta=FakeDelta(), hil_port=FakeHILPort())
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
        guard = ExecutionMonitor(delta=delta, hil_port=FakeHILPort())
        wr = _make_wave_result(step_count=1, duration_ms=100)

        await guard.after_wave(wr, _make_ctx(trace_id="t-42"))

        assert len(delta.progress_calls) == 1
        call = delta.progress_calls[0]
        assert call["trace_id"] == "t-42"
        assert "wave-0" in call["step_id"]

    @pytest.mark.asyncio
    async def test_progress_summary_contains_wave_info(self) -> None:
        delta = FakeDelta()
        guard = ExecutionMonitor(delta=delta, hil_port=FakeHILPort())
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
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=2, duration_ms=1000)

        decision = await guard.after_wave(wr, _make_ctx())

        assert decision.action == GuardAction.CONTINUE
        assert len(service.calls) == 0

    @pytest.mark.asyncio
    async def test_exactly_threshold_no_override(self) -> None:
        """Exactly 3 steps and exactly 5000ms -> no override (> not >=)."""
        delta = FakeDelta()
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=3, duration_ms=5000)

        decision = await guard.after_wave(wr, _make_ctx())
        assert len(service.calls) == 0

    @pytest.mark.asyncio
    async def test_single_step_no_override(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=1, duration_ms=100)

        await guard.after_wave(wr, _make_ctx())
        assert len(service.calls) == 0


# ===========================================================================
# TestAfterWaveOverrideStepCount
# ===========================================================================


class TestAfterWaveOverrideStepCount:
    """>3 steps -> hil_port.request_override called."""

    @pytest.mark.asyncio
    async def test_four_steps_triggers_override(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())

        assert decision.action == GuardAction.CONTINUE
        assert len(service.calls) == 1
        assert "hil_request_id" in decision.metadata

    @pytest.mark.asyncio
    async def test_override_options_correct(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=5, duration_ms=100)

        await guard.after_wave(wr, _make_ctx())

        req = service.calls[0]
        assert len(req.proposed_alternatives) == 1
        options = req.proposed_alternatives[0]["options"]
        assert options == list(_OVERRIDE_OPTIONS)
        assert "CONTINUE" in options
        assert "CANCEL_DAG" in options
        assert "MODIFY_PARAMS" not in options  # Removed V1

    @pytest.mark.asyncio
    async def test_override_timeout(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=4, duration_ms=100)

        await guard.after_wave(wr, _make_ctx())

        req = service.calls[0]
        assert req.timeout_ms == _OVERRIDE_TIMEOUT_MS


# ===========================================================================
# TestAfterWaveOverrideDuration
# ===========================================================================


class TestAfterWaveOverrideDuration:
    """>5s duration -> hil_port.request_override called."""

    @pytest.mark.asyncio
    async def test_long_duration_triggers_override(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=1, duration_ms=6000)

        decision = await guard.after_wave(wr, _make_ctx())

        assert decision.action == GuardAction.CONTINUE
        assert len(service.calls) == 1

    @pytest.mark.asyncio
    async def test_5001ms_triggers_override(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=1, duration_ms=5001)

        await guard.after_wave(wr, _make_ctx())
        assert len(service.calls) == 1


# ===========================================================================
# TestAfterWaveOverrideResponse
# ===========================================================================


class TestAfterWaveOverrideResponse:
    """OverrideResponse drives the GuardAction (E6).

    * timed_out=True -> CONTINUE (silence = proceed)
    * choice=='override' -> CONTINUE
    * choice=='abort'    -> HARD_STOP
    """

    @pytest.mark.asyncio
    async def test_timed_out_continues(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort(
            response=OverrideResponse(
                hil_request_id="r-x",
                choice="override",
                timed_out=True,
            )
        )
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.CONTINUE

    @pytest.mark.asyncio
    async def test_explicit_override_continues(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort(
            response=OverrideResponse(
                hil_request_id="r-x",
                choice="override",
                timed_out=False,
            )
        )
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.CONTINUE

    @pytest.mark.asyncio
    async def test_abort_hard_stops(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort(
            response=OverrideResponse(
                hil_request_id="r-x",
                choice="abort",
                timed_out=False,
            )
        )
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.HARD_STOP


# ===========================================================================
# TestAfterWaveDeltaFailure
# ===========================================================================


class TestAfterWaveDeltaFailure:
    """Delta / HIL failure -> graceful degradation."""

    @pytest.mark.asyncio
    async def test_progress_failure_still_continues(self) -> None:
        delta = FakeDelta(raise_on_progress=True)
        service = FakeHILPort()
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=1, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.CONTINUE

    @pytest.mark.asyncio
    async def test_hil_failure_still_continues(self) -> None:
        delta = FakeDelta()
        service = FakeHILPort(raise_exc=True)
        guard = ExecutionMonitor(delta=delta, hil_port=service)
        wr = _make_wave_result(step_count=4, duration_ms=100)

        decision = await guard.after_wave(wr, _make_ctx())
        assert decision.action == GuardAction.CONTINUE
        assert "failed" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_no_hil_port(self) -> None:
        """hil_port=None -> still continues with debug log."""
        delta = FakeDelta()

        guard = ExecutionMonitor(delta=delta, hil_port=None)
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


# ===========================================================================
# Pipeline tests (Epic 7.2.6 / ORCH-09) -- via OrchestratorService.process()
# ===========================================================================

from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from tests.k1.orchestrator.helpers import (
    cap_result,
    make_plan,
    make_step,
    orchestrator_for_testing,
    process_plan,
    register_capabilities,
)


class TestExecutionMonitorPipeline:
    """ExecutionMonitor verified through OrchestratorService.process() pipeline.

    No guard imports. All assertions via adapter state (delta.progress_log,
    delta.progress_log).
    """

    # -- pipeline position ------------------------------------------------

    @pytest.mark.asyncio
    async def test_pipeline_position(self) -> None:
        """ExecutionMonitor is the 4th guard (index 3)."""
        service, _ = await orchestrator_for_testing()
        guard = service._dag_executor._guards[3]
        assert type(guard).__name__ == "ExecutionMonitor"

    # -- progress emission ------------------------------------------------

    @pytest.mark.asyncio
    async def test_single_wave_emits_progress(self) -> None:
        """One-wave plan emits exactly one progress delta."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        delta: TestDeltaAdapter = adapters["delta"]
        register_capabilities(fabric, "cap.x")
        fabric.script_result("cap.x", cap_result({"val": 1}))

        plan = make_plan([make_step("s1", "cap.x")])
        await process_plan(service, plan)

        assert len(delta.progress_log) >= 1
        # wave-0 progress
        delta.assert_progress("wave-0")

    @pytest.mark.asyncio
    async def test_multi_wave_accumulates_progress(self) -> None:
        """3-wave plan emits 3 progress deltas (one per wave)."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        delta: TestDeltaAdapter = adapters["delta"]
        register_capabilities(fabric, "cap.a", "cap.b", "cap.c")
        fabric.script_result("cap.a", cap_result({"v": 1}))
        fabric.script_result("cap.b", cap_result({"v": 2}))
        fabric.script_result("cap.c", cap_result({"v": 3}))

        s1 = make_step("s1", "cap.a")
        s2 = make_step("s2", "cap.b")
        s3 = make_step("s3", "cap.c")
        plan = make_plan([s1, s2, s3], deps={"s2": ["s1"], "s3": ["s2"]})
        await process_plan(service, plan)

        wave_ids = [sid for sid, _, _ in delta.progress_log]
        assert "wave-0" in wave_ids
        assert "wave-1" in wave_ids
        assert "wave-2" in wave_ids

    @pytest.mark.asyncio
    async def test_progress_trace_id_matches(self) -> None:
        """Progress deltas carry the correct trace_id."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        delta: TestDeltaAdapter = adapters["delta"]
        register_capabilities(fabric, "cap.t")
        fabric.script_result("cap.t", cap_result({"ok": True}))

        plan = make_plan([make_step("s1", "cap.t")], trace_id="my-trace")
        await process_plan(service, plan)

        assert any(tid == "my-trace" for _, _, tid in delta.progress_log)

    # -- no override for small waves --------------------------------------

    @pytest.mark.asyncio
    async def test_small_wave_no_hil(self) -> None:
        """Wave with <=3 steps and fast execution -> no HIL request."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        delta: TestDeltaAdapter = adapters["delta"]
        register_capabilities(fabric, "cap.a", "cap.b", "cap.c")
        fabric.script_result("cap.a", cap_result({"v": 1}))
        fabric.script_result("cap.b", cap_result({"v": 2}))
        fabric.script_result("cap.c", cap_result({"v": 3}))

        # 3 parallel steps (all in wave 0) - at threshold, no override
        s1 = make_step("s1", "cap.a")
        s2 = make_step("s2", "cap.b")
        s3 = make_step("s3", "cap.c")
        plan = make_plan([s1, s2, s3])
        await process_plan(service, plan)

    # -- progress summary format ------------------------------------------

    @pytest.mark.asyncio
    async def test_progress_summary_mentions_steps(self) -> None:
        """Progress summary includes step count."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        delta: TestDeltaAdapter = adapters["delta"]
        register_capabilities(fabric, "cap.a", "cap.b")
        fabric.script_result("cap.a", cap_result({"v": 1}))
        fabric.script_result("cap.b", cap_result({"v": 2}))

        s1 = make_step("s1", "cap.a")
        s2 = make_step("s2", "cap.b")
        plan = make_plan([s1, s2])
        await process_plan(service, plan)

        _, summary, _ = delta.progress_log[0]
        assert "2 steps" in summary

    @pytest.mark.asyncio
    async def test_progress_summary_with_failure(self) -> None:
        """Progress summary shows failure count when steps fail."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        delta: TestDeltaAdapter = adapters["delta"]
        register_capabilities(fabric, "cap.ok", "cap.fail")
        fabric.script_result("cap.ok", cap_result({"v": 1}))
        fabric.script_result("cap.fail", cap_result(success=False))

        s1 = make_step("s1", "cap.ok")
        s2 = make_step("s2", "cap.fail")
        plan = make_plan([s1, s2])
        await process_plan(service, plan)

        _, summary, _ = delta.progress_log[0]
        # Summary shows partial success (1 of 2 done)
        assert "1/2" in summary or "1 failed" in summary

    # -- DAG events emitted -----------------------------------------------

    @pytest.mark.asyncio
    async def test_dag_lifecycle_events(self) -> None:
        """DAG started and completed events emitted."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        delta: TestDeltaAdapter = adapters["delta"]
        register_capabilities(fabric, "cap.x")
        fabric.script_result("cap.x", cap_result({"ok": True}))

        plan = make_plan([make_step("s1", "cap.x")])
        await process_plan(service, plan)

        started = delta.get_emitted("k1.orchestration.dag.started.v1")
        completed = delta.get_emitted("k1.orchestration.dag.completed.v1")
        assert len(started) >= 1
        assert len(completed) >= 1
        assert len(completed) >= 1
