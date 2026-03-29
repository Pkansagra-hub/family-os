"""
Tests for Epic 4.4 -- Fabric Concurrency Model (FAB-003 decision).

Covers:
  4.4.1 FabricDispatcher -- async dispatcher with bounded parallelism
  4.4.2 TimeoutGuard + backpressure -- deadline enforcement + load shedding

Per FAB-003 (Accepted): No FABRIC_MAILBOX. Uses asyncio.Semaphore
for backpressure, TimeoutGuard for deadlines, FabricDispatcher for
async dispatching.

Test structure:
  TestBackpressureLevel -- Enum values and ordering
  TestFabricDispatcherConfig -- Config construction and validation
  TestDispatchResult -- Result dataclass
  TestDispatcherHealth -- Health snapshot and serialization
  TestDispatcherExceptions -- Exception hierarchy and attributes
  TestFabricDispatcherConstruction -- Construction and initial state
  TestFabricDispatcherDispatchSuccess -- Successful dispatch path
  TestFabricDispatcherBackpressure -- Backpressure levels and shedding
  TestFabricDispatcherEvents -- Backpressure event emission
  TestFabricDispatcherShutdown -- Graceful shutdown
  TestFabricDispatcherHealth -- Health snapshot
  TestFabricDispatcherPriorityTracking -- Per-priority in-flight tracking
  TestTimeoutGuardConfig -- Config construction and validation
  TestDeadlineExceededError -- Exception attributes
  TestTimeoutGuardConstruction -- Construction and initial state
  TestTimeoutGuardResolveTimeout -- Timeout resolution logic
  TestTimeoutGuardExecuteWithGuard -- Deadline enforcement (raises)
  TestTimeoutGuardExecuteSafe -- Deadline enforcement (returns failure)
  TestTimeoutGuardStats -- Observability stats
  TestConcurrencyExports -- Module __all__ validation
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

import pytest

from k1.fabric.concurrency import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_SHEDDING_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    PRESSURE_SHEDDING_TOPIC,
    PRESSURE_WARNING_TOPIC,
    BackpressureLevel,
    DeadlineExceededError,
    DispatcherError,
    DispatcherHealth,
    DispatcherOverloadedError,
    DispatcherShutdownError,
    DispatchResult,
    FabricDispatcher,
    FabricDispatcherConfig,
    TimeoutGuard,
    TimeoutGuardConfig,
)
from k1.fabric.types import CapabilityRequest, CapabilityResult, WFQPriority

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request(
    name: str = "tool.test",
    priority: str = WFQPriority.INTERACTIVE.value,
    timeout_ms: int = 30000,
    caller: str = "test",
) -> CapabilityRequest:
    """Create a minimal valid CapabilityRequest."""
    return CapabilityRequest(
        capability_name=name,
        wfq_priority=priority,
        timeout_ms=timeout_ms,
        caller=caller,
        trace_id="trace-test-001",
    )


async def _instant_success(request: CapabilityRequest) -> CapabilityResult:
    """Execute function that returns success immediately."""
    return CapabilityResult.success_result(
        request_id=request.request_id,
        data={"ok": True},
        provider_id="test-provider",
        trace_id=request.trace_id,
    )


async def _slow_success(request: CapabilityRequest) -> CapabilityResult:
    """Execute function that takes 200ms to complete."""
    await asyncio.sleep(0.2)
    return CapabilityResult.success_result(
        request_id=request.request_id,
        data={"slow": True},
        provider_id="test-provider",
        trace_id=request.trace_id,
    )


async def _very_slow_success(request: CapabilityRequest) -> CapabilityResult:
    """Execute function that takes 2s (will timeout in most test configs)."""
    await asyncio.sleep(2.0)
    return CapabilityResult.success_result(
        request_id=request.request_id,
        data={"very_slow": True},
        provider_id="test-provider",
        trace_id=request.trace_id,
    )


async def _failing_execute(request: CapabilityRequest) -> CapabilityResult:
    """Execute function that raises an exception."""
    raise RuntimeError("provider exploded")


class EventCapture:
    """Captures events emitted by FabricDispatcher."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, Dict[str, Any]]] = []

    def __call__(self, topic: str, payload: Dict[str, Any]) -> None:
        self.events.append((topic, payload))


# =========================================================================
# BackpressureLevel enum
# =========================================================================


class TestBackpressureLevel:
    """Tests for BackpressureLevel enum."""

    def test_values(self) -> None:
        assert BackpressureLevel.NORMAL.value == "NORMAL"
        assert BackpressureLevel.WARNING.value == "WARNING"
        assert BackpressureLevel.SHEDDING.value == "SHEDDING"
        assert BackpressureLevel.SATURATED.value == "SATURATED"

    def test_member_count(self) -> None:
        assert len(BackpressureLevel) == 4

    def test_string_enum(self) -> None:
        assert isinstance(BackpressureLevel.NORMAL, str)
        assert BackpressureLevel.NORMAL == "NORMAL"


# =========================================================================
# FabricDispatcherConfig
# =========================================================================


class TestFabricDispatcherConfig:
    """Tests for FabricDispatcherConfig construction and validation."""

    def test_defaults(self) -> None:
        cfg = FabricDispatcherConfig()
        assert cfg.max_concurrent == 10
        assert cfg.warning_threshold == 0.80
        assert cfg.shedding_threshold == 0.95
        assert cfg.emit_events is True

    def test_custom_values(self) -> None:
        cfg = FabricDispatcherConfig(
            max_concurrent=20,
            warning_threshold=0.70,
            shedding_threshold=0.90,
            emit_events=False,
        )
        assert cfg.max_concurrent == 20
        assert cfg.warning_threshold == 0.70
        assert cfg.shedding_threshold == 0.90
        assert cfg.emit_events is False

    def test_frozen(self) -> None:
        cfg = FabricDispatcherConfig()
        with pytest.raises(AttributeError):
            cfg.max_concurrent = 99  # type: ignore[misc]

    def test_max_concurrent_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
            FabricDispatcherConfig(max_concurrent=0)

    def test_max_concurrent_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
            FabricDispatcherConfig(max_concurrent=-5)

    def test_warning_threshold_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="warning_threshold must be in"):
            FabricDispatcherConfig(warning_threshold=0.0)

    def test_warning_threshold_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="warning_threshold must be in"):
            FabricDispatcherConfig(warning_threshold=1.0)

    def test_shedding_threshold_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="shedding_threshold must be in"):
            FabricDispatcherConfig(shedding_threshold=0.0)

    def test_shedding_must_exceed_warning(self) -> None:
        with pytest.raises(ValueError, match="shedding_threshold.*must be >.*warning_threshold"):
            FabricDispatcherConfig(warning_threshold=0.80, shedding_threshold=0.80)

    def test_shedding_below_warning_rejected(self) -> None:
        with pytest.raises(ValueError, match="shedding_threshold.*must be >"):
            FabricDispatcherConfig(warning_threshold=0.90, shedding_threshold=0.50)


# =========================================================================
# DispatchResult
# =========================================================================


class TestDispatchResult:
    """Tests for DispatchResult dataclass."""

    def test_defaults(self) -> None:
        dr = DispatchResult()
        assert dr.wait_ms == 0
        assert dr.backpressure_at_entry == BackpressureLevel.NORMAL.value
        assert dr.dispatched is True

    def test_with_values(self) -> None:
        result = CapabilityResult.success_result(
            request_id="r1", data={"ok": True}, provider_id="p1"
        )
        dr = DispatchResult(
            result=result,
            wait_ms=5,
            backpressure_at_entry=BackpressureLevel.WARNING.value,
            dispatched=True,
        )
        assert dr.result.success is True
        assert dr.wait_ms == 5
        assert dr.backpressure_at_entry == "WARNING"

    def test_frozen(self) -> None:
        dr = DispatchResult()
        with pytest.raises(AttributeError):
            dr.wait_ms = 99  # type: ignore[misc]


# =========================================================================
# DispatcherHealth
# =========================================================================


class TestDispatcherHealth:
    """Tests for DispatcherHealth dataclass."""

    def test_defaults(self) -> None:
        h = DispatcherHealth()
        assert h.in_flight == 0
        assert h.max_concurrent == DEFAULT_MAX_CONCURRENT
        assert h.utilization == 0.0
        assert h.backpressure_level == BackpressureLevel.NORMAL.value
        assert h.total_dispatched == 0
        assert h.total_rejected == 0
        assert h.total_completed == 0
        assert h.is_shutdown is False

    def test_to_dict(self) -> None:
        h = DispatcherHealth(in_flight=3, max_concurrent=10, utilization=0.3)
        d = h.to_dict()
        assert d["in_flight"] == 3
        assert d["max_concurrent"] == 10
        assert d["utilization"] == 0.3
        assert "backpressure_level" in d

    def test_frozen(self) -> None:
        h = DispatcherHealth()
        with pytest.raises(AttributeError):
            h.in_flight = 99  # type: ignore[misc]


# =========================================================================
# Dispatcher Exceptions
# =========================================================================


class TestDispatcherExceptions:
    """Tests for dispatcher exception hierarchy."""

    def test_dispatcher_error_is_exception(self) -> None:
        assert issubclass(DispatcherError, Exception)

    def test_overloaded_inherits_dispatcher_error(self) -> None:
        assert issubclass(DispatcherOverloadedError, DispatcherError)

    def test_shutdown_inherits_dispatcher_error(self) -> None:
        assert issubclass(DispatcherShutdownError, DispatcherError)

    def test_overloaded_attributes(self) -> None:
        err = DispatcherOverloadedError(
            message="saturated",
            level=BackpressureLevel.SATURATED,
            in_flight=10,
            max_concurrent=10,
            rejected_priority=WFQPriority.BACKGROUND.value,
        )
        assert str(err) == "saturated"
        assert err.level == BackpressureLevel.SATURATED
        assert err.in_flight == 10
        assert err.max_concurrent == 10
        assert err.rejected_priority == "BACKGROUND"

    def test_shutdown_message(self) -> None:
        err = DispatcherShutdownError("gone")
        assert str(err) == "gone"


# =========================================================================
# FabricDispatcher Construction
# =========================================================================


class TestFabricDispatcherConstruction:
    """Tests for FabricDispatcher initial state."""

    def test_default_construction(self) -> None:
        d = FabricDispatcher()
        assert d.in_flight == 0
        assert d.max_concurrent == DEFAULT_MAX_CONCURRENT
        assert d.utilization == 0.0
        assert d.is_shutdown is False
        assert d.backpressure_level() == BackpressureLevel.NORMAL

    def test_custom_config(self) -> None:
        cfg = FabricDispatcherConfig(max_concurrent=5)
        d = FabricDispatcher(config=cfg)
        assert d.max_concurrent == 5
        assert d.config is cfg

    def test_with_event_callback(self) -> None:
        capture = EventCapture()
        d = FabricDispatcher(event_callback=capture)
        assert d.in_flight == 0

    def test_repr_initial(self) -> None:
        d = FabricDispatcher()
        r = repr(d)
        assert "FabricDispatcher" in r
        assert "in_flight=0" in r
        assert "max=10" in r
        assert "NORMAL" in r
        assert "shutdown=False" in r

    def test_per_priority_snapshot_initial(self) -> None:
        d = FabricDispatcher()
        snap = d.per_priority_snapshot()
        assert all(v == 0 for v in snap.values())
        assert WFQPriority.INTERACTIVE.value in snap
        assert WFQPriority.BACKGROUND.value in snap


# =========================================================================
# FabricDispatcher -- Successful Dispatch
# =========================================================================


class TestFabricDispatcherDispatchSuccess:
    """Tests for successful dispatch paths."""

    async def test_dispatch_returns_result(self) -> None:
        d = FabricDispatcher()
        req = _request()
        dr = await d.dispatch(req, _instant_success)
        assert dr.dispatched is True
        assert dr.result.success is True
        assert dr.result.data == {"ok": True}
        assert dr.wait_ms >= 0

    async def test_dispatch_tracks_total_dispatched(self) -> None:
        d = FabricDispatcher()
        await d.dispatch(_request(), _instant_success)
        await d.dispatch(_request(), _instant_success)
        h = d.health()
        assert h.total_dispatched == 2
        assert h.total_completed == 2
        assert h.in_flight == 0

    async def test_dispatch_in_flight_during_execution(self) -> None:
        d = FabricDispatcher()
        observed_in_flight: List[int] = []

        async def tracking_execute(req: CapabilityRequest) -> CapabilityResult:
            observed_in_flight.append(d.in_flight)
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        await d.dispatch(_request(), tracking_execute)
        assert observed_in_flight[0] == 1
        assert d.in_flight == 0

    async def test_dispatch_execute_fn_exception_propagates(self) -> None:
        d = FabricDispatcher()
        with pytest.raises(RuntimeError, match="provider exploded"):
            await d.dispatch(_request(), _failing_execute)
        # In-flight must be decremented even on exception
        assert d.in_flight == 0
        h = d.health()
        assert h.total_dispatched == 1
        assert h.total_completed == 1

    async def test_dispatch_entry_level_normal(self) -> None:
        d = FabricDispatcher()
        dr = await d.dispatch(_request(), _instant_success)
        assert dr.backpressure_at_entry == BackpressureLevel.NORMAL.value

    async def test_concurrent_dispatch(self) -> None:
        d = FabricDispatcher(config=FabricDispatcherConfig(max_concurrent=5))
        results = await asyncio.gather(
            *[d.dispatch(_request(), _instant_success) for _ in range(5)]
        )
        assert len(results) == 5
        assert all(r.dispatched for r in results)
        assert d.in_flight == 0


# =========================================================================
# FabricDispatcher -- Backpressure
# =========================================================================


class TestFabricDispatcherBackpressure:
    """Tests for backpressure levels and load shedding."""

    def test_level_normal_when_empty(self) -> None:
        d = FabricDispatcher()
        assert d.backpressure_level() == BackpressureLevel.NORMAL

    async def test_shedding_rejects_background(self) -> None:
        """At SHEDDING level (>= 95%), BACKGROUND is rejected."""
        cfg = FabricDispatcherConfig(max_concurrent=10)
        d = FabricDispatcher(config=cfg)
        barrier = asyncio.Event()
        started = asyncio.Event()
        count = 0

        async def blocking_execute(req: CapabilityRequest) -> CapabilityResult:
            nonlocal count
            count += 1
            if count >= 10:
                started.set()
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        # Fill to 10/10 (SATURATED) -- but we need 9.5+, so fill to 10
        # We need to hold 10 in-flight, then try BACKGROUND
        # Actually: fill 9 slots, then SHEDDING is 9/10=0.9 which is < 0.95
        # Fill 10 slots: 10/10=1.0 which is SATURATED
        # We need filling to exactly 95%+ but < 100%
        # With max_concurrent=20, fill 19 -> 19/20=0.95 -> SHEDDING
        cfg2 = FabricDispatcherConfig(max_concurrent=20)
        d2 = FabricDispatcher(config=cfg2)
        barrier2 = asyncio.Event()
        slot_count = 0

        async def blocking2(req: CapabilityRequest) -> CapabilityResult:
            nonlocal slot_count
            slot_count += 1
            await barrier2.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        # Fill 19 of 20 slots (95%)
        tasks = []
        for _ in range(19):
            t = asyncio.create_task(
                d2.dispatch(_request(priority=WFQPriority.INTERACTIVE.value), blocking2)
            )
            tasks.append(t)
        await asyncio.sleep(0.05)  # Let tasks start

        assert d2.in_flight == 19
        level = d2.backpressure_level()
        assert level == BackpressureLevel.SHEDDING

        # BACKGROUND request should be rejected
        bg_req = _request(priority=WFQPriority.BACKGROUND.value)
        with pytest.raises(DispatcherOverloadedError) as exc_info:
            await d2.dispatch(bg_req, _instant_success)
        assert exc_info.value.level == BackpressureLevel.SHEDDING
        assert exc_info.value.rejected_priority == "BACKGROUND"

        # Non-BACKGROUND should still be accepted (blocks on semaphore)
        # Don't test that here -- it would block

        barrier2.set()
        await asyncio.gather(*tasks)

    async def test_saturated_rejects_all(self) -> None:
        """At SATURATED level (100%), all requests are rejected."""
        cfg = FabricDispatcherConfig(max_concurrent=3)
        d = FabricDispatcher(config=cfg)
        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        # Fill all 3 slots
        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(3)]
        await asyncio.sleep(0.05)
        assert d.in_flight == 3
        assert d.backpressure_level() == BackpressureLevel.SATURATED

        # Any new request is rejected
        with pytest.raises(DispatcherOverloadedError) as exc_info:
            await d.dispatch(_request(), _instant_success)
        assert exc_info.value.level == BackpressureLevel.SATURATED

        # Tracks rejection
        h = d.health()
        assert h.total_rejected == 1

        barrier.set()
        await asyncio.gather(*tasks)

    async def test_interactive_not_shed_at_shedding(self) -> None:
        """INTERACTIVE requests are NOT shed even at SHEDDING level."""
        cfg = FabricDispatcherConfig(max_concurrent=20)
        d = FabricDispatcher(config=cfg)
        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        # Fill 19 of 20 slots
        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(19)]
        await asyncio.sleep(0.05)
        assert d.backpressure_level() == BackpressureLevel.SHEDDING

        # INTERACTIVE should NOT be rejected (it will block on semaphore
        # since only 1 slot left, but won't be rejected)
        # Actually at 19/20, should_reject returns None for INTERACTIVE
        # so it proceeds to semaphore.acquire which has 1 permit left
        int_req = _request(priority=WFQPriority.INTERACTIVE.value)
        task20 = asyncio.create_task(d.dispatch(int_req, blocking))
        await asyncio.sleep(0.05)
        assert d.in_flight == 20  # Accepted, not rejected

        barrier.set()
        await asyncio.gather(*tasks, task20)

    async def test_warning_level_computation(self) -> None:
        """WARNING level is correctly computed at >= 80%."""
        cfg = FabricDispatcherConfig(max_concurrent=10)
        d = FabricDispatcher(config=cfg)
        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        # Fill 8 of 10 slots (80%) -> WARNING
        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(8)]
        await asyncio.sleep(0.05)
        assert d.in_flight == 8
        assert d.backpressure_level() == BackpressureLevel.WARNING

        barrier.set()
        await asyncio.gather(*tasks)


# =========================================================================
# FabricDispatcher -- Event Emission
# =========================================================================


class TestFabricDispatcherEvents:
    """Tests for backpressure event emission."""

    async def test_warning_event_emitted(self) -> None:
        capture = EventCapture()
        cfg = FabricDispatcherConfig(max_concurrent=5)
        d = FabricDispatcher(config=cfg, event_callback=capture)
        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        # Fill 4/5 = 80% -> WARNING
        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(4)]
        await asyncio.sleep(0.05)

        warning_events = [e for e in capture.events if e[0] == PRESSURE_WARNING_TOPIC]
        assert len(warning_events) >= 1
        payload = warning_events[0][1]
        assert payload["level"] == "WARNING"
        assert "in_flight" in payload
        assert "utilization" in payload

        barrier.set()
        await asyncio.gather(*tasks)

    async def test_no_events_when_emit_disabled(self) -> None:
        capture = EventCapture()
        cfg = FabricDispatcherConfig(max_concurrent=5, emit_events=False)
        d = FabricDispatcher(config=cfg, event_callback=capture)
        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(4)]
        await asyncio.sleep(0.05)
        assert len(capture.events) == 0

        barrier.set()
        await asyncio.gather(*tasks)

    async def test_no_events_when_no_callback(self) -> None:
        """No crash when no event callback is set."""
        cfg = FabricDispatcherConfig(max_concurrent=5)
        d = FabricDispatcher(config=cfg)  # No callback

        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(4)]
        await asyncio.sleep(0.05)
        # Should not raise
        assert d.backpressure_level() == BackpressureLevel.WARNING

        barrier.set()
        await asyncio.gather(*tasks)

    async def test_event_callback_exception_ignored(self) -> None:
        """If event callback raises, dispatch still works."""

        def exploding_callback(topic: str, payload: Dict[str, Any]) -> None:
            raise RuntimeError("callback boom")

        cfg = FabricDispatcherConfig(max_concurrent=5)
        d = FabricDispatcher(config=cfg, event_callback=exploding_callback)
        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        # Should not crash despite failing callback
        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(4)]
        await asyncio.sleep(0.05)
        assert d.in_flight == 4

        barrier.set()
        await asyncio.gather(*tasks)


# =========================================================================
# FabricDispatcher -- Shutdown
# =========================================================================


class TestFabricDispatcherShutdown:
    """Tests for graceful shutdown."""

    async def test_shutdown_empty(self) -> None:
        d = FabricDispatcher()
        was = await d.shutdown()
        assert was == 0
        assert d.is_shutdown is True

    async def test_dispatch_after_shutdown_raises(self) -> None:
        d = FabricDispatcher()
        await d.shutdown()
        with pytest.raises(DispatcherShutdownError):
            await d.dispatch(_request(), _instant_success)

    async def test_shutdown_waits_for_inflight(self) -> None:
        cfg = FabricDispatcherConfig(max_concurrent=3)
        d = FabricDispatcher(config=cfg)
        barrier = asyncio.Event()
        completed = []

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            completed.append(req.request_id)
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(2)]
        await asyncio.sleep(0.05)
        assert d.in_flight == 2

        # Start shutdown (will block until in-flight complete)
        shutdown_task = asyncio.create_task(d.shutdown())
        await asyncio.sleep(0.05)

        # Release blocking tasks
        barrier.set()
        await asyncio.gather(*tasks)
        was = await shutdown_task
        assert was == 2
        assert len(completed) == 2

    async def test_shutdown_health_reflects_state(self) -> None:
        d = FabricDispatcher()
        await d.shutdown()
        h = d.health()
        assert h.is_shutdown is True


# =========================================================================
# FabricDispatcher -- Health
# =========================================================================


class TestFabricDispatcherHealth:
    """Tests for health snapshot."""

    async def test_health_after_dispatch(self) -> None:
        d = FabricDispatcher()
        await d.dispatch(_request(), _instant_success)
        h = d.health()
        assert h.total_dispatched == 1
        assert h.total_completed == 1
        assert h.in_flight == 0
        assert h.is_shutdown is False

    def test_health_initial(self) -> None:
        d = FabricDispatcher()
        h = d.health()
        assert h.in_flight == 0
        assert h.total_dispatched == 0
        assert h.total_rejected == 0
        assert h.total_completed == 0

    async def test_health_utilization(self) -> None:
        cfg = FabricDispatcherConfig(max_concurrent=10)
        d = FabricDispatcher(config=cfg)
        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        tasks = [asyncio.create_task(d.dispatch(_request(), blocking)) for _ in range(5)]
        await asyncio.sleep(0.05)
        h = d.health()
        assert h.in_flight == 5
        assert h.utilization == 0.5

        barrier.set()
        await asyncio.gather(*tasks)


# =========================================================================
# FabricDispatcher -- Per-Priority Tracking
# =========================================================================


class TestFabricDispatcherPriorityTracking:
    """Tests for per-priority in-flight tracking."""

    async def test_tracks_by_priority(self) -> None:
        d = FabricDispatcher()
        barrier = asyncio.Event()

        async def blocking(req: CapabilityRequest) -> CapabilityResult:
            await barrier.wait()
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        t1 = asyncio.create_task(d.dispatch(_request(priority=WFQPriority.URGENT.value), blocking))
        t2 = asyncio.create_task(
            d.dispatch(_request(priority=WFQPriority.INTERACTIVE.value), blocking)
        )
        await asyncio.sleep(0.05)

        snap = d.per_priority_snapshot()
        assert snap[WFQPriority.URGENT.value] == 1
        assert snap[WFQPriority.INTERACTIVE.value] == 1
        assert snap[WFQPriority.BACKGROUND.value] == 0

        barrier.set()
        await asyncio.gather(t1, t2)

        snap2 = d.per_priority_snapshot()
        assert snap2[WFQPriority.URGENT.value] == 0
        assert snap2[WFQPriority.INTERACTIVE.value] == 0


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Tests for module-level constants."""

    def test_default_max_concurrent(self) -> None:
        assert DEFAULT_MAX_CONCURRENT == 10

    def test_default_warning_threshold(self) -> None:
        assert DEFAULT_WARNING_THRESHOLD == 0.80

    def test_default_shedding_threshold(self) -> None:
        assert DEFAULT_SHEDDING_THRESHOLD == 0.95

    def test_pressure_warning_topic(self) -> None:
        assert PRESSURE_WARNING_TOPIC == "k1.fabric.pressure.warning.v1"

    def test_pressure_shedding_topic(self) -> None:
        assert PRESSURE_SHEDDING_TOPIC == "k1.fabric.pressure.shedding.v1"


# =========================================================================
# TimeoutGuardConfig
# =========================================================================


class TestTimeoutGuardConfig:
    """Tests for TimeoutGuardConfig construction and validation."""

    def test_defaults(self) -> None:
        cfg = TimeoutGuardConfig()
        assert cfg.default_timeout_ms == 30_000
        assert cfg.min_timeout_ms == 100
        assert cfg.track_active is True

    def test_custom_values(self) -> None:
        cfg = TimeoutGuardConfig(
            default_timeout_ms=5000,
            min_timeout_ms=50,
            track_active=False,
        )
        assert cfg.default_timeout_ms == 5000
        assert cfg.min_timeout_ms == 50
        assert cfg.track_active is False

    def test_frozen(self) -> None:
        cfg = TimeoutGuardConfig()
        with pytest.raises(AttributeError):
            cfg.default_timeout_ms = 99  # type: ignore[misc]

    def test_default_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="default_timeout_ms must be >= 1"):
            TimeoutGuardConfig(default_timeout_ms=0)

    def test_min_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_timeout_ms must be >= 1"):
            TimeoutGuardConfig(min_timeout_ms=0)


# =========================================================================
# DeadlineExceededError
# =========================================================================


class TestDeadlineExceededError:
    """Tests for DeadlineExceededError exception."""

    def test_attributes(self) -> None:
        err = DeadlineExceededError(
            message="timed out",
            request_id="r1",
            timeout_ms=5000,
            elapsed_ms=5100,
            trace_id="t1",
        )
        assert str(err) == "timed out"
        assert err.request_id == "r1"
        assert err.timeout_ms == 5000
        assert err.elapsed_ms == 5100
        assert err.trace_id == "t1"

    def test_is_exception(self) -> None:
        assert issubclass(DeadlineExceededError, Exception)

    def test_defaults(self) -> None:
        err = DeadlineExceededError("oops")
        assert err.request_id == ""
        assert err.timeout_ms == 0
        assert err.elapsed_ms == 0
        assert err.trace_id == ""


# =========================================================================
# TimeoutGuard -- Construction
# =========================================================================


class TestTimeoutGuardConstruction:
    """Tests for TimeoutGuard initial state."""

    def test_default_construction(self) -> None:
        g = TimeoutGuard()
        assert g.active_count == 0
        assert g.total_timeouts == 0
        assert g.config.default_timeout_ms == 30_000

    def test_custom_config(self) -> None:
        cfg = TimeoutGuardConfig(default_timeout_ms=5000)
        g = TimeoutGuard(config=cfg)
        assert g.config is cfg
        assert g.config.default_timeout_ms == 5000

    def test_repr(self) -> None:
        g = TimeoutGuard()
        r = repr(g)
        assert "TimeoutGuard" in r
        assert "active=0" in r
        assert "timeouts=0" in r
        assert "30000ms" in r


# =========================================================================
# TimeoutGuard -- Resolve Timeout
# =========================================================================


class TestTimeoutGuardResolveTimeout:
    """Tests for timeout resolution logic."""

    def test_uses_request_timeout(self) -> None:
        g = TimeoutGuard()
        req = _request(timeout_ms=5000)
        assert g.resolve_timeout_ms(req) == 5000

    def test_uses_default_when_zero(self) -> None:
        g = TimeoutGuard(config=TimeoutGuardConfig(default_timeout_ms=10000))
        req = _request(timeout_ms=0)
        assert g.resolve_timeout_ms(req) == 10000

    def test_uses_default_when_negative(self) -> None:
        g = TimeoutGuard(config=TimeoutGuardConfig(default_timeout_ms=10000))
        req = _request(timeout_ms=-1)
        assert g.resolve_timeout_ms(req) == 10000

    def test_clamps_to_minimum(self) -> None:
        g = TimeoutGuard(config=TimeoutGuardConfig(min_timeout_ms=500))
        req = _request(timeout_ms=50)  # Below minimum
        assert g.resolve_timeout_ms(req) == 500

    def test_large_timeout_passes_through(self) -> None:
        g = TimeoutGuard()
        req = _request(timeout_ms=120_000)
        assert g.resolve_timeout_ms(req) == 120_000

    def test_minimum_clamp_applies_to_default(self) -> None:
        g = TimeoutGuard(config=TimeoutGuardConfig(default_timeout_ms=50, min_timeout_ms=200))
        req = _request(timeout_ms=0)  # Falls to default=50, clamped to min=200
        assert g.resolve_timeout_ms(req) == 200


# =========================================================================
# TimeoutGuard -- execute_with_guard
# =========================================================================


class TestTimeoutGuardExecuteWithGuard:
    """Tests for deadline enforcement that raises."""

    async def test_success_within_deadline(self) -> None:
        g = TimeoutGuard()
        req = _request(timeout_ms=5000)
        result = await g.execute_with_guard(req, _instant_success)
        assert result.success is True

    async def test_raises_on_timeout(self) -> None:
        cfg = TimeoutGuardConfig(default_timeout_ms=100, min_timeout_ms=50)
        g = TimeoutGuard(config=cfg)
        req = _request(timeout_ms=100)

        with pytest.raises(DeadlineExceededError) as exc_info:
            await g.execute_with_guard(req, _very_slow_success)

        assert exc_info.value.request_id == req.request_id
        assert exc_info.value.timeout_ms == 100
        assert exc_info.value.elapsed_ms > 0
        assert exc_info.value.trace_id == req.trace_id

    async def test_timeout_increments_counter(self) -> None:
        cfg = TimeoutGuardConfig(default_timeout_ms=100, min_timeout_ms=50)
        g = TimeoutGuard(config=cfg)
        req = _request(timeout_ms=100)

        with pytest.raises(DeadlineExceededError):
            await g.execute_with_guard(req, _very_slow_success)

        assert g.total_timeouts == 1

    async def test_active_count_tracks_during_execution(self) -> None:
        g = TimeoutGuard()
        observed: List[int] = []

        async def tracking(req: CapabilityRequest) -> CapabilityResult:
            observed.append(g.active_count)
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={},
                provider_id="p",
                trace_id=req.trace_id,
            )

        await g.execute_with_guard(_request(), tracking)
        assert observed[0] == 1
        assert g.active_count == 0

    async def test_active_count_decremented_on_timeout(self) -> None:
        cfg = TimeoutGuardConfig(default_timeout_ms=100, min_timeout_ms=50)
        g = TimeoutGuard(config=cfg)

        with pytest.raises(DeadlineExceededError):
            await g.execute_with_guard(_request(timeout_ms=100), _very_slow_success)
        assert g.active_count == 0

    async def test_active_count_decremented_on_exception(self) -> None:
        g = TimeoutGuard()
        with pytest.raises(RuntimeError):
            await g.execute_with_guard(_request(), _failing_execute)
        assert g.active_count == 0


# =========================================================================
# TimeoutGuard -- execute_safe
# =========================================================================


class TestTimeoutGuardExecuteSafe:
    """Tests for deadline enforcement that returns failure."""

    async def test_success_returns_result(self) -> None:
        g = TimeoutGuard()
        result = await g.execute_safe(_request(), _instant_success)
        assert result.success is True

    async def test_timeout_returns_failure(self) -> None:
        cfg = TimeoutGuardConfig(default_timeout_ms=100, min_timeout_ms=50)
        g = TimeoutGuard(config=cfg)
        req = _request(timeout_ms=100)
        result = await g.execute_safe(req, _very_slow_success)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "deadline_exceeded"
        assert result.error.retriable is True
        assert result.request_id == req.request_id
        assert result.trace_id == req.trace_id

    async def test_timeout_safe_increments_counter(self) -> None:
        cfg = TimeoutGuardConfig(default_timeout_ms=100, min_timeout_ms=50)
        g = TimeoutGuard(config=cfg)
        await g.execute_safe(_request(timeout_ms=100), _very_slow_success)
        assert g.total_timeouts == 1

    async def test_execute_exception_propagates(self) -> None:
        """Non-timeout exceptions are NOT caught by execute_safe."""
        g = TimeoutGuard()
        with pytest.raises(RuntimeError, match="provider exploded"):
            await g.execute_safe(_request(), _failing_execute)


# =========================================================================
# TimeoutGuard -- Stats
# =========================================================================


class TestTimeoutGuardStats:
    """Tests for observability stats."""

    def test_initial_stats(self) -> None:
        g = TimeoutGuard()
        s = g.stats()
        assert s["active_count"] == 0
        assert s["total_timeouts"] == 0
        assert s["default_timeout_ms"] == 30_000
        assert s["min_timeout_ms"] == 100

    async def test_stats_after_timeout(self) -> None:
        cfg = TimeoutGuardConfig(default_timeout_ms=100, min_timeout_ms=50)
        g = TimeoutGuard(config=cfg)
        await g.execute_safe(_request(timeout_ms=100), _very_slow_success)
        s = g.stats()
        assert s["total_timeouts"] == 1
        assert s["active_count"] == 0


# =========================================================================
# Module Exports
# =========================================================================


EXPECTED_CONCURRENCY_EXPORT_COUNT = 16

EXPECTED_NEW_EXPORTS = {
    "FabricDispatcher",
    "FabricDispatcherConfig",
    "DispatchResult",
    "DispatcherHealth",
    "DispatcherError",
    "DispatcherOverloadedError",
    "DispatcherShutdownError",
    "BackpressureLevel",
    "DEFAULT_MAX_CONCURRENT",
    "DEFAULT_WARNING_THRESHOLD",
    "DEFAULT_SHEDDING_THRESHOLD",
    "PRESSURE_WARNING_TOPIC",
    "PRESSURE_SHEDDING_TOPIC",
    "TimeoutGuard",
    "TimeoutGuardConfig",
    "DeadlineExceededError",
}


class TestConcurrencyExports:
    """Tests for concurrency package __all__."""

    def test_export_count(self) -> None:
        from k1.fabric.concurrency import __all__

        assert len(__all__) == EXPECTED_CONCURRENCY_EXPORT_COUNT

    def test_new_exports_present(self) -> None:
        from k1.fabric.concurrency import __all__

        all_set = set(__all__)
        for name in EXPECTED_NEW_EXPORTS:
            assert name in all_set, f"Missing export: {name}"

    def test_all_importable(self) -> None:
        import k1.fabric.concurrency as mod

        for name in EXPECTED_NEW_EXPORTS:
            assert hasattr(mod, name), f"Cannot import: {name}"

    def test_dispatcher_importable_directly(self) -> None:
        from k1.fabric.concurrency.dispatcher import FabricDispatcher

        assert FabricDispatcher is not None

    def test_timeout_importable_directly(self) -> None:
        from k1.fabric.concurrency.timeout import TimeoutGuard

        assert TimeoutGuard is not None
