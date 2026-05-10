"""Tests for PlannerAgent Issues 2.3.5, 2.3.6, 2.3.7.

Covers:
  - Issue 2.3.5: INIT lifecycle phase (start())
    - Subscribes to 4 event topics using TOPIC_* constants
    - pipeline.reset() called at INIT step 4
    - _running set to True before entering _run_loop
    - _crash_recovery() called before _run_loop
    - Event handlers: _on_plan_request enqueues, _on_plan_cancel adds
      to cancel_set, _on_hil_* are V1 stubs
  - Issue 2.3.6: SHUTDOWN lifecycle phase (stop())
    - _running set to False
    - Mailbox drained, cancelled events emitted for each
    - In-flight plan cancelled via cancel_set
    - Grace period wait for in-flight plan
    - Sentinel injected to unblock dequeue
    - All subscriptions unsubscribed
    - Clean shutdown with no lock held
  - Issue 2.3.7: CRASH_RECOVERY lifecycle phase
    - V1: no-op, pipeline already reset to IDLE

References
----------
- planner.md Section 23.1   (INIT Lifecycle)
- planner.md Section 23.5   (SHUTDOWN Lifecycle)
- planner.md Section 23.6   (CRASH_RECOVERY Lifecycle)
- planner.md Section 24.1   (V1 Single Plan)
- planner.md Section 28     (Event Catalog)
- docs/plans/planner-implementation-plan.md Issues 2.3.5, 2.3.6, 2.3.7
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.types import PlanRequest
from k1.planner.config import PlannerConfig
from k1.planner.events import (
    TOPIC_PLAN_CANCEL,
    TOPIC_PLAN_CANCELLED,
    TOPIC_PLAN_REQUEST,
    PlanCancelledPayload,
)
from k1.planner.pipeline_controller import PipelineController
from k1.planner.planner_agent import PlannerAgent
from k1.planner.types import PlannerError

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class FakeDeltaPort:
    """Minimal IDeltaEmitPort implementation."""

    def __init__(self) -> None:
        self.emitted: List[Any] = []

    def emit(self, delta: Any) -> None:
        self.emitted.append(delta)


class RecordingEventPort:
    """IEventPort implementation that records subscriptions and emissions."""

    def __init__(self) -> None:
        self.emitted: List[Tuple[str, Any]] = []
        self.subscriptions: List[Tuple[str, Any]] = []
        self._sub_counter: int = 0
        self._handlers: Dict[str, List[Any]] = {}

    def emit(self, topic: str, payload: Any) -> None:
        self.emitted.append((topic, payload))
        # Dispatch to handlers (like a real event bus)
        for handler in self._handlers.get(topic, []):
            handler(topic, payload)

    def subscribe(self, topic: str, handler: Any) -> SubscriptionHandle:
        self._sub_counter += 1
        sub_id = f"sub-{self._sub_counter}"
        self.subscriptions.append((topic, handler))
        self._handlers.setdefault(topic, []).append(handler)
        return SubscriptionHandle(subscription_id=sub_id, topic=topic)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        handlers = self._handlers.get(handle.topic, [])
        # Remove matching handler
        for i, h in enumerate(handlers):
            for _, sub_handler in self.subscriptions:
                if sub_handler is h:
                    handlers.pop(i)
                    return True
        return False


class QueueMailboxPort:
    """IMailboxPort with asyncio.Queue for dequeue + drain support."""

    def __init__(self, max_depth: int = 5) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_depth)
        self.enqueued: List[Any] = []
        self.cancelled: List[str] = []

    async def dequeue(self) -> Any:
        return await self._queue.get()

    async def enqueue(self, request: Any) -> None:
        self.enqueued.append(request)
        await self._queue.put(request)

    async def send_cancel(self, request_id: str) -> None:
        self.cancelled.append(request_id)

    def drain(self) -> list:
        """Non-blocking drain: return all queued items."""
        items = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    async def micro_replan(self, request: Any) -> Any:
        return None

    def put_nowait(self, request: Any) -> None:
        """Helper: put a request directly into the queue."""
        self._queue.put_nowait(request)


class FakeService:
    """Minimal stub for stage services."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name


class RecordingPipelineController(PipelineController):
    """PipelineController subclass that records calls."""

    def __init__(self, *, event_port: Any = None) -> None:
        super().__init__(
            sketch=FakeService("sketch"),
            expand=FakeService("expand"),
            validate=FakeService("validate"),
            commit=FakeService("commit"),
            delta_port=FakeDeltaPort(),
            event_port=event_port if event_port is not None else RecordingEventPort(),
            config=PlannerConfig(),
        )
        self.execute_calls: List[Any] = []
        self.micro_replan_calls: List[Any] = []
        self.reset_count: int = 0
        self._execute_error: Optional[BaseException] = None
        self._execute_hook: Optional[Callable[[], Any]] = None

    async def execute(self, request: Any, cancel_check: Callable[[], bool]) -> Any:
        self.execute_calls.append(request)
        if self._execute_hook is not None:
            await self._execute_hook()
        if self._execute_error is not None:
            raise self._execute_error
        return None

    async def micro_replan(self, request: Any, cancel_check: Callable[[], bool]) -> Any:
        self.micro_replan_calls.append(request)
        return None

    def reset(self) -> None:
        self.reset_count += 1


def _make_request(request_id: str = "req-001", intent: str = "test") -> PlanRequest:
    """Create a PlanRequest with minimal required fields."""
    return PlanRequest(
        intent=intent,
        trace_id=f"trace-{request_id}",
        request_id=request_id,
    )


def _make_agent(
    *,
    mailbox: Any = None,
    pipeline: Any = None,
    event_port: Any = None,
    config: Any = None,
) -> PlannerAgent:
    """Construct PlannerAgent with defaults for unspecified params."""
    return PlannerAgent(
        mailbox=mailbox if mailbox is not None else QueueMailboxPort(),
        pipeline=pipeline if pipeline is not None else RecordingPipelineController(),
        event_port=event_port if event_port is not None else RecordingEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


async def _start_and_stop(
    agent: PlannerAgent,
    mailbox: QueueMailboxPort,
    pipeline: RecordingPipelineController,
    requests: Optional[List[PlanRequest]] = None,
) -> None:
    """Start agent, process optional requests, then stop cleanly."""
    for req in requests or []:
        mailbox.put_nowait(req)

    async def _stop_after() -> None:
        target = len(requests) if requests else 0
        while pipeline.reset_count < target:
            await asyncio.sleep(0.01)
        await agent.stop()

    stop_task = asyncio.create_task(_stop_after())
    await agent.start()
    stop_task.cancel()
    try:
        await stop_task
    except asyncio.CancelledError:
        pass


# ===========================================================================
# 1. INIT lifecycle -- subscriptions (Issue 2.3.5)
# ===========================================================================


class TestINITSubscriptions:
    """start() subscribes to exactly 4 event topics (SS23.1 step 3)."""

    @pytest.mark.asyncio
    async def test_subscribes_to_four_topics(self) -> None:
        """start() creates exactly 4 subscriptions."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        # Stop immediately after init
        async def _stop() -> None:
            await asyncio.sleep(0.05)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # Exactly 4 subscriptions were created
        assert len(ep.subscriptions) == 2

    @pytest.mark.asyncio
    async def test_subscribes_to_plan_request(self) -> None:
        """start() subscribes to TOPIC_PLAN_REQUEST."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        topics = [t for t, _ in ep.subscriptions]
        assert TOPIC_PLAN_REQUEST in topics

    @pytest.mark.asyncio
    async def test_subscribes_to_plan_cancel(self) -> None:
        """start() subscribes to TOPIC_PLAN_CANCEL."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        topics = [t for t, _ in ep.subscriptions]
        assert TOPIC_PLAN_CANCEL in topics

    # E5 (HIL Unification): tests for HIL subscription removed -- planner
    # no longer subscribes to TOPIC_HIL_CLARIFICATION_RESP / TOPIC_HIL_APPROVAL_RESP.
    # HIL coordination flows through the unified IHILPort adapter.

    @pytest.mark.asyncio
    async def test_subscriptions_stored_in_agent(self) -> None:
        """start() stores SubscriptionHandle objects in _subscriptions."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            # Don't call stop -- we want to inspect subscriptions BEFORE unsubscribe
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert len(agent._subscriptions) == 2
        for sub in agent._subscriptions:
            assert isinstance(sub, SubscriptionHandle)

    @pytest.mark.asyncio
    async def test_uses_topic_constants_not_strings(self) -> None:
        """Subscriptions use TOPIC_* constants (no hardcoded strings)."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        topics = {t for t, _ in ep.subscriptions}
        expected = {
            TOPIC_PLAN_REQUEST,
            TOPIC_PLAN_CANCEL,
        }
        assert topics == expected


# ===========================================================================
# 2. INIT lifecycle -- state setup (Issue 2.3.5)
# ===========================================================================


class TestINITState:
    """start() sets pipeline to IDLE, clears cancel_set, sets _running."""

    @pytest.mark.asyncio
    async def test_pipeline_reset_called_at_init(self) -> None:
        """pipeline.reset() is called during INIT step 4."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # reset() called at least once during INIT step 4
        assert pipeline.reset_count >= 1

    @pytest.mark.asyncio
    async def test_running_true_during_loop(self) -> None:
        """_running is True when _run_loop is active."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        running_during_loop = False

        async def capture_running() -> None:
            nonlocal running_during_loop
            running_during_loop = agent._running

        pipeline._execute_hook = capture_running
        mailbox.put_nowait(_make_request("req-001"))

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert running_during_loop is True

    @pytest.mark.asyncio
    async def test_cancel_set_cleared_at_init(self) -> None:
        """_cancel_set is cleared during INIT step 4."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        # Pre-populate cancel set
        agent._cancel_set["stale-cancel"] = time.monotonic()

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # cancel_set was cleared by start()
        assert "stale-cancel" not in agent._cancel_set

    @pytest.mark.asyncio
    async def test_in_flight_request_id_none_at_init(self) -> None:
        """_in_flight_request_id is None at INIT."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        # Corrupt state
        agent._in_flight_request_id = "stale"

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert agent._in_flight_request_id is None


# ===========================================================================
# 3. Event handlers (Issue 2.3.5)
# ===========================================================================


class TestEventHandlerPlanRequest:
    """_on_plan_request enqueues PlanRequest to mailbox."""

    @pytest.mark.asyncio
    async def test_plan_request_event_enqueues(self) -> None:
        """Emitting plan.request.v1 with a PlanRequest enqueues it."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        req = _make_request("req-via-event")
        mailbox.put_nowait(req)

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # The request was processed by the pipeline
        assert len(pipeline.execute_calls) >= 1

    @pytest.mark.asyncio
    async def test_plan_request_handler_accepts_planrequest(self) -> None:
        """_on_plan_request accepts PlanRequest objects directly."""
        mailbox = QueueMailboxPort()
        agent = _make_agent(mailbox=mailbox)
        agent._running = True

        req = _make_request("req-direct")
        agent._on_plan_request(TOPIC_PLAN_REQUEST, req)

        # Give the task a chance to run
        await asyncio.sleep(0.05)

        # Request should have been enqueued
        assert len(mailbox.enqueued) == 1
        assert mailbox.enqueued[0].request_id == "req-direct"

    @pytest.mark.asyncio
    async def test_plan_request_handler_accepts_dict(self) -> None:
        """_on_plan_request accepts dict payloads."""
        mailbox = QueueMailboxPort()
        agent = _make_agent(mailbox=mailbox)
        agent._running = True

        payload = {"intent": "test dict", "trace_id": "trace-dict", "request_id": "req-dict"}
        agent._on_plan_request(TOPIC_PLAN_REQUEST, payload)

        await asyncio.sleep(0.05)

        assert len(mailbox.enqueued) == 1
        assert mailbox.enqueued[0].request_id == "req-dict"

    @pytest.mark.asyncio
    async def test_plan_request_handler_rejects_when_not_running(self) -> None:
        """_on_plan_request drops request when _running is False."""
        mailbox = QueueMailboxPort()
        agent = _make_agent(mailbox=mailbox)
        agent._running = False

        agent._on_plan_request(TOPIC_PLAN_REQUEST, _make_request("ignored"))

        await asyncio.sleep(0.05)

        assert len(mailbox.enqueued) == 0


class TestEventHandlerPlanCancel:
    """_on_plan_cancel adds request_id to cancel set."""

    @pytest.mark.asyncio
    async def test_cancel_event_adds_to_cancel_set(self) -> None:
        """Emitting plan.cancel.v1 adds request_id to cancel_set."""
        agent = _make_agent()
        agent._on_plan_cancel(TOPIC_PLAN_CANCEL, {"request_id": "req-cancel"})
        assert "req-cancel" in agent._cancel_set

    @pytest.mark.asyncio
    async def test_cancel_event_with_object_payload(self) -> None:
        """_on_plan_cancel handles object payloads with request_id attr."""

        class CancelPayload:
            request_id = "req-obj-cancel"

        agent = _make_agent()
        agent._on_plan_cancel(TOPIC_PLAN_CANCEL, CancelPayload())
        assert "req-obj-cancel" in agent._cancel_set

    @pytest.mark.asyncio
    async def test_cancel_event_missing_request_id(self) -> None:
        """_on_plan_cancel ignores payload without request_id."""
        agent = _make_agent()
        agent._on_plan_cancel(TOPIC_PLAN_CANCEL, {"other": "data"})
        assert len(agent._cancel_set) == 0


class TestEventHandlerHILStubs:
    """E5 (HIL Unification): HIL response handlers were removed from PlannerAgent."""

    def test_hil_handlers_removed(self) -> None:
        agent = _make_agent()
        assert not hasattr(agent, "_on_hil_clarification")
        assert not hasattr(agent, "_on_hil_approval")


# ===========================================================================
# 4. CRASH_RECOVERY V1 (Issue 2.3.7)
# ===========================================================================


class TestCrashRecovery:
    """V1 crash recovery: no-op, pipeline already IDLE (SS23.6)."""

    @pytest.mark.asyncio
    async def test_crash_recovery_runs_during_init(self) -> None:
        """_crash_recovery is called during start() before _run_loop."""
        from unittest.mock import AsyncMock, patch

        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        with patch.object(type(agent), "_crash_recovery", new_callable=AsyncMock) as mock_cr:

            async def _stop() -> None:
                await asyncio.sleep(0.05)
                await agent.stop()

            stop_task = asyncio.create_task(_stop())
            await agent.start()
            stop_task.cancel()
            try:
                await stop_task
            except asyncio.CancelledError:
                pass

            mock_cr.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_crash_recovery_does_not_raise(self) -> None:
        """_crash_recovery V1 completes without error."""
        agent = _make_agent()
        # Direct call (not through start())
        await agent._crash_recovery()  # should not raise

    @pytest.mark.asyncio
    async def test_crash_recovery_is_v1_noop(self) -> None:
        """V1 crash recovery does not modify cancel_set or lock."""
        pipeline = RecordingPipelineController()
        agent = _make_agent(pipeline=pipeline)

        initial_reset = pipeline.reset_count
        await agent._crash_recovery()

        # No additional reset (pipeline was already reset in INIT step 4)
        assert pipeline.reset_count == initial_reset
        assert not agent._plan_lock.locked()
        assert len(agent._cancel_set) == 0


# ===========================================================================
# 5. SHUTDOWN -- _running & drain (Issue 2.3.6)
# ===========================================================================


class TestShutdownBasic:
    """stop() sets _running=False and drains mailbox."""

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self) -> None:
        agent = _make_agent()
        agent._running = True
        await agent.stop()
        assert agent._running is False

    @pytest.mark.asyncio
    async def test_stop_drains_queued_requests(self) -> None:
        """stop() drains all queued requests from mailbox."""
        mailbox = QueueMailboxPort()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, event_port=ep)

        # Load 3 requests into queue
        mailbox.put_nowait(_make_request("req-001"))
        mailbox.put_nowait(_make_request("req-002"))
        mailbox.put_nowait(_make_request("req-003"))

        await agent.stop()

        # All 3 should have been drained with cancelled events
        cancelled = [(t, p) for t, p in ep.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 3
        ids = {p.request_id for _, p in cancelled}
        assert ids == {"req-001", "req-002", "req-003"}

    @pytest.mark.asyncio
    async def test_drain_emits_shutdown_reason(self) -> None:
        """Drained requests get reason='shutdown'."""
        mailbox = QueueMailboxPort()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, event_port=ep)

        mailbox.put_nowait(_make_request("req-001"))
        await agent.stop()

        cancelled = [(t, p) for t, p in ep.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled) == 1
        payload = cancelled[0][1]
        assert isinstance(payload, PlanCancelledPayload)
        assert payload.reason == "shutdown"
        assert payload.stage == "QUEUED"

    @pytest.mark.asyncio
    async def test_stop_empty_mailbox(self) -> None:
        """stop() with empty mailbox succeeds without error."""
        agent = _make_agent()
        await agent.stop()  # should not raise


# ===========================================================================
# 6. SHUTDOWN -- unsubscribe (Issue 2.3.6)
# ===========================================================================


class TestShutdownUnsubscribe:
    """stop() unsubscribes all event subscriptions."""

    @pytest.mark.asyncio
    async def test_subscriptions_cleared_after_stop(self) -> None:
        """stop() clears _subscriptions list."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert len(agent._subscriptions) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_called_for_each(self) -> None:
        """stop() calls unsubscribe for each stored subscription."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()

        unsubscribed: List[str] = []

        class TrackingEventPort:
            def __init__(self) -> None:
                self._sub_counter = 0

            def emit(self, topic: str, payload: Any) -> None:
                pass

            def subscribe(self, topic: str, handler: Any) -> SubscriptionHandle:
                self._sub_counter += 1
                return SubscriptionHandle(
                    subscription_id=f"sub-{self._sub_counter}",
                    topic=topic,
                )

            def unsubscribe(self, handle: SubscriptionHandle) -> bool:
                unsubscribed.append(handle.subscription_id)
                return True

        ep = TrackingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert len(unsubscribed) == 2


# ===========================================================================
# 7. SHUTDOWN -- cancel in-flight (Issue 2.3.6)
# ===========================================================================


class TestShutdownCancelInflight:
    """stop() cancels in-flight plan via cancel_set."""

    @pytest.mark.asyncio
    async def test_inflight_cancelled_during_shutdown(self) -> None:
        """In-flight plan gets cancelled when stop() is called."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        plan_started = asyncio.Event()
        plan_can_finish = asyncio.Event()

        async def hold_plan() -> None:
            plan_started.set()
            await plan_can_finish.wait()

        pipeline._execute_hook = hold_plan

        mailbox.put_nowait(_make_request("req-inflight"))

        # Start agent in a task
        start_task = asyncio.create_task(agent.start())

        # Wait for plan to start executing
        await plan_started.wait()

        # Verify in-flight tracking
        assert agent._in_flight_request_id == "req-inflight"
        assert agent._plan_lock.locked()

        # Call stop() -- should add to cancel_set
        stop_task = asyncio.create_task(agent.stop())
        await asyncio.sleep(0.05)

        # cancel_set should contain the in-flight request
        assert "req-inflight" in agent._cancel_set

        # Release the plan so shutdown can complete
        plan_can_finish.set()
        await asyncio.sleep(0.1)

        # Cleanup
        start_task.cancel()
        stop_task.cancel()
        try:
            await start_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await stop_task
        except (asyncio.CancelledError, Exception):
            pass

    @pytest.mark.asyncio
    async def test_no_inflight_cancel_when_idle(self) -> None:
        """stop() does NOT cancel when no plan is in-flight."""
        agent = _make_agent()

        # Simulate idle state (lock not held)
        assert not agent._plan_lock.locked()
        assert agent._in_flight_request_id is None

        await agent.stop()

        # cancel_set should be empty
        assert len(agent._cancel_set) == 0

    @pytest.mark.asyncio
    async def test_lock_not_held_after_clean_stop(self) -> None:
        """Lock is not held after a clean stop() with no in-flight plan."""
        agent = _make_agent()
        await agent.stop()
        assert not agent._plan_lock.locked()


# ===========================================================================
# 8. SHUTDOWN -- grace period (Issue 2.3.6)
# ===========================================================================


class TestShutdownGracePeriod:
    """stop() waits up to grace period for in-flight plan to complete."""

    @pytest.mark.asyncio
    async def test_grace_period_waits_for_plan(self) -> None:
        """stop() waits for in-flight plan to finish within grace period."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        config = PlannerConfig(shutdown_grace_period_ms=2000)
        agent = _make_agent(
            mailbox=mailbox,
            pipeline=pipeline,
            config=config,
        )

        plan_started = asyncio.Event()

        async def quick_plan() -> None:
            plan_started.set()
            await asyncio.sleep(0.05)  # Quick -- well within grace period

        pipeline._execute_hook = quick_plan
        mailbox.put_nowait(_make_request("req-001"))

        start_task = asyncio.create_task(agent.start())
        await plan_started.wait()

        # stop() should wait for plan to finish (< 2s grace)
        await asyncio.wait_for(agent.stop(), timeout=3.0)

        start_task.cancel()
        try:
            await start_task
        except (asyncio.CancelledError, Exception):
            pass

        # Plan completed, lock released
        assert not agent._plan_lock.locked()


# ===========================================================================
# 9. In-flight request tracking (Issue 2.3.5/2.3.6)
# ===========================================================================


class TestInFlightTracking:
    """_in_flight_request_id tracks the current plan."""

    @pytest.mark.asyncio
    async def test_inflight_set_during_execute(self) -> None:
        """_in_flight_request_id is set while pipeline executes."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        captured_id: Optional[str] = None

        async def capture_inflight() -> None:
            nonlocal captured_id
            captured_id = agent._in_flight_request_id

        pipeline._execute_hook = capture_inflight

        mailbox.put_nowait(_make_request("req-tracked"))

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert captured_id == "req-tracked"

    @pytest.mark.asyncio
    async def test_inflight_cleared_after_execute(self) -> None:
        """_in_flight_request_id is None after plan completes."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-001"))

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert agent._in_flight_request_id is None

    @pytest.mark.asyncio
    async def test_inflight_cleared_after_error(self) -> None:
        """_in_flight_request_id is None after plan raises error."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        pipeline._execute_error = PlannerError("fail", stage="SKETCH")
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-err"))

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert agent._in_flight_request_id is None

    @pytest.mark.asyncio
    async def test_inflight_property(self) -> None:
        """in_flight_request_id property returns current value."""
        agent = _make_agent()
        assert agent.in_flight_request_id is None
        agent._in_flight_request_id = "req-prop"
        assert agent.in_flight_request_id == "req-prop"


# ===========================================================================
# 10. Full start/stop lifecycle (Issues 2.3.5 + 2.3.6)
# ===========================================================================


class TestFullLifecycle:
    """Full start() -> process -> stop() lifecycle."""

    @pytest.mark.asyncio
    async def test_start_process_stop(self) -> None:
        """Full lifecycle: start, process 2 requests, stop cleanly."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(
            mailbox=mailbox,
            pipeline=pipeline,
            event_port=ep,
        )

        mailbox.put_nowait(_make_request("req-001"))
        mailbox.put_nowait(_make_request("req-002"))

        async def _stop() -> None:
            while pipeline.reset_count < 2:
                await asyncio.sleep(0.01)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # Both requests processed
        assert len(pipeline.execute_calls) == 2
        # Clean state
        assert not agent._running
        assert not agent._plan_lock.locked()
        assert agent._in_flight_request_id is None
        assert len(agent._subscriptions) == 0

    @pytest.mark.asyncio
    async def test_stop_with_queued_and_inflight(self) -> None:
        """stop() during plan: cancels in-flight + drains remaining."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        plan_started = asyncio.Event()
        plan_can_finish = asyncio.Event()

        async def block_plan() -> None:
            plan_started.set()
            await plan_can_finish.wait()

        pipeline._execute_hook = block_plan

        # Load 3 requests: first will be in-flight, others queued
        mailbox.put_nowait(_make_request("req-inflight"))
        mailbox.put_nowait(_make_request("req-queued-1"))
        mailbox.put_nowait(_make_request("req-queued-2"))

        start_task = asyncio.create_task(agent.start())
        await plan_started.wait()

        # Now stop: should drain the 2 queued requests
        stop_task = asyncio.create_task(agent.stop())
        await asyncio.sleep(0.05)

        # In-flight should be in cancel_set
        assert "req-inflight" in agent._cancel_set

        # Release plan
        plan_can_finish.set()
        await asyncio.sleep(0.2)

        # Verify queued requests were drained with cancelled events
        cancelled = [
            (t, p)
            for t, p in ep.emitted
            if t == TOPIC_PLAN_CANCELLED and hasattr(p, "reason") and p.reason == "shutdown"
        ]
        drained_ids = {p.request_id for _, p in cancelled}
        assert "req-queued-1" in drained_ids
        assert "req-queued-2" in drained_ids

        # Cleanup
        start_task.cancel()
        stop_task.cancel()
        try:
            await start_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await stop_task
        except (asyncio.CancelledError, Exception):
            pass

    @pytest.mark.asyncio
    async def test_running_false_after_stop(self) -> None:
        """_running is False after stop() completes."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-001"))

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            await agent.stop()

        stop_task = asyncio.create_task(_stop())
        await agent.start()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert agent._running is False


# ===========================================================================
# 11. Event-driven integration (Issue 2.3.5)
# ===========================================================================


class TestEventDrivenIntegration:
    """Events flow through subscriptions to enqueue/cancel."""

    @pytest.mark.asyncio
    async def test_emit_plan_request_triggers_enqueue(self) -> None:
        """Emitting plan.request.v1 on the event bus enqueues to mailbox."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        plan_started = asyncio.Event()

        async def signal_start() -> None:
            plan_started.set()

        pipeline._execute_hook = signal_start

        # Start agent
        start_task = asyncio.create_task(agent.start())
        await asyncio.sleep(0.05)  # Let INIT complete

        # Emit a plan request via event bus
        req = _make_request("req-from-event")
        ep.emit(TOPIC_PLAN_REQUEST, req)

        # Wait for it to be processed
        try:
            await asyncio.wait_for(plan_started.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        await agent.stop()
        start_task.cancel()
        try:
            await start_task
        except (asyncio.CancelledError, Exception):
            pass

        # The request from the event bus should have been processed
        assert len(pipeline.execute_calls) >= 1

    @pytest.mark.asyncio
    async def test_emit_cancel_triggers_cancel_set(self) -> None:
        """Emitting plan.cancel.v1 on the event bus adds to cancel_set."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = RecordingEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        start_task = asyncio.create_task(agent.start())
        await asyncio.sleep(0.05)  # Let INIT complete

        # Emit a cancel via event bus
        ep.emit(TOPIC_PLAN_CANCEL, {"request_id": "req-event-cancel"})

        assert "req-event-cancel" in agent._cancel_set

        await agent.stop()
        start_task.cancel()
        try:
            await start_task
        except (asyncio.CancelledError, Exception):
            pass
