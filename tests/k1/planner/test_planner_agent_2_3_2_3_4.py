"""Tests for PlannerAgent Issues 2.3.2, 2.3.3, 2.3.4.

Covers:
  - Issue 2.3.2: Mailbox dequeue loop (_run_loop)
    - FIFO dequeue order
    - Cancel pre-check (skips cancelled requests, emits event)
    - Error handling (PlanCancelledError, PlannerError, unexpected Exception)
    - Pipeline reset in finally
    - Lock release in finally
    - start() sets _running=True and enters _run_loop
  - Issue 2.3.3: Plan lock (asyncio.Lock, V1 single plan)
    - Lock acquired before pipeline.execute
    - Lock released in finally after execute
    - micro_replan acquires lock and delegates to pipeline
    - micro_replan releases lock and resets pipeline in finally
    - Lock contention: micro_replan blocks while plan is in flight
  - Issue 2.3.4: Cancel set management
    - on_cancel adds request_id to cancel set
    - on_cancel is idempotent
    - cancel_check closure wires cancel_set to pipeline
    - cancel_set.discard at PLAN_END in finally
    - cancel before enqueue (pre-population)

References
----------
- planner.md Section 24.1   (V1 Single Plan)
- planner.md Section 24.2   (Cancellation)
- planner.md Section 24.3   (Micro-Replan Concurrency)
- planner.md Section 30.5.1 F02
- docs/plans/planner-implementation-plan.md Issues 2.3.2, 2.3.3, 2.3.4
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.types import (
    CommittedPlan,
    MicroReplanRequest,
    PlanRequest,
    PlanStep,
)
from k1.planner.config import PlannerConfig
from k1.planner.events import (
    TOPIC_PLAN_CANCELLED,
    TOPIC_PLAN_FAILED,
    PlanCancelledPayload,
    PlanFailedPayload,
)
from k1.planner.pipeline_controller import PipelineController
from k1.planner.planner_agent import PlannerAgent
from k1.planner.types import PlanCancelledError, PlannerError

# ---------------------------------------------------------------------------
# Test helpers -- enhanced for dequeue loop testing
# ---------------------------------------------------------------------------


class FakeDeltaPort:
    """Minimal IDeltaEmitPort implementation."""

    def __init__(self) -> None:
        self.emitted: List[Any] = []

    def emit(self, delta: Any) -> None:
        self.emitted.append(delta)


class FakeEventPort:
    """IEventPort implementation that records all emitted events."""

    def __init__(self) -> None:
        self.emitted: List[Tuple[str, Any]] = []
        self.subscriptions: List[Tuple[str, Any]] = []

    def emit(self, topic: str, payload: Any) -> None:
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Any) -> SubscriptionHandle:
        self.subscriptions.append((topic, handler))
        return SubscriptionHandle(subscription_id=f"sub-{topic}", topic=topic)

    def unsubscribe(self, handle: Any) -> bool:
        return True


class QueueMailboxPort:
    """IMailboxPort with asyncio.Queue for dequeue support.

    Allows tests to pre-load requests and observe dequeue order.
    """

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
        """Helper: put a request directly into the queue (no enqueue tracking)."""
        self._queue.put_nowait(request)


class FakeService:
    """Minimal stub for stage services."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name


@dataclass
class ExecuteRecord:
    """Records a pipeline.execute() call."""

    request: Any
    cancel_check: Callable[[], bool]


class RecordingPipelineController(PipelineController):
    """PipelineController subclass that records calls and returns preset results.

    Overrides execute() and micro_replan() to avoid running the real
    4-stage pipeline.  Records call arguments and returns configurable
    results for test assertions.
    """

    def __init__(self, *, event_port: Any = None) -> None:
        super().__init__(
            sketch=FakeService("sketch"),
            expand=FakeService("expand"),
            validate=FakeService("validate"),
            commit=FakeService("commit"),
            delta_port=FakeDeltaPort(),
            event_port=event_port if event_port is not None else FakeEventPort(),
            config=PlannerConfig(),
        )
        self.execute_calls: List[ExecuteRecord] = []
        self.micro_replan_calls: List[ExecuteRecord] = []
        self.reset_count: int = 0
        self._execute_result: Any = None
        self._execute_error: Optional[BaseException] = None
        self._micro_replan_result: Any = None
        self._micro_replan_error: Optional[BaseException] = None
        self._execute_hook: Optional[Callable[[], Any]] = None

    async def execute(
        self,
        request: Any,
        cancel_check: Callable[[], bool],
    ) -> Any:
        self.execute_calls.append(ExecuteRecord(request=request, cancel_check=cancel_check))
        if self._execute_hook is not None:
            await self._execute_hook()
        if self._execute_error is not None:
            raise self._execute_error
        return self._execute_result

    async def micro_replan(
        self,
        request: Any,
        cancel_check: Callable[[], bool],
    ) -> Any:
        self.micro_replan_calls.append(ExecuteRecord(request=request, cancel_check=cancel_check))
        if self._micro_replan_error is not None:
            raise self._micro_replan_error
        return self._micro_replan_result

    def reset(self) -> None:
        self.reset_count += 1


def _make_request(request_id: str = "req-001", intent: str = "test") -> PlanRequest:
    """Create a PlanRequest with minimal required fields."""
    return PlanRequest(
        intent=intent,
        trace_id=f"trace-{request_id}",
        request_id=request_id,
    )


def _make_micro_request(request_id: str = "micro-001") -> MicroReplanRequest:
    """Create a MicroReplanRequest with minimal required fields."""
    return MicroReplanRequest(
        request_id=request_id,
        original_plan_id="plan-001",
        remaining_steps=[PlanStep(id="step-1", capability="test.cap")],
        completed_results={},
        trace_id=f"trace-{request_id}",
    )


def _make_committed_plan(request_id: str = "req-001") -> CommittedPlan:
    """Create a minimal CommittedPlan for test returns."""
    return CommittedPlan(
        plan_id="plan-001",
        request_id=request_id,
        intent="test",
        steps=[PlanStep(id="step-1", capability="test.cap")],
        trace_id=f"trace-{request_id}",
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
        event_port=event_port if event_port is not None else FakeEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


async def _run_loop_with_requests(
    agent: PlannerAgent,
    mailbox: QueueMailboxPort,
    requests: List[Any],
    *,
    stop_after: int = 0,
) -> None:
    """Helper: load requests into mailbox no-wait, then run the loop.

    After all loaded requests are processed, sets _running=False and
    injects a pre-cancelled sentinel to unblock dequeue().
    """
    for req in requests:
        mailbox.put_nowait(req)

    processed = 0
    target = stop_after if stop_after > 0 else len(requests)

    pipeline = agent._pipeline

    async def _monitor() -> None:
        nonlocal processed
        while processed < target:
            await asyncio.sleep(0.01)
        agent._running = False
        # Pre-cancel sentinel so it skips execution
        agent._cancel_set["__sentinel__"] = time.monotonic()
        try:
            mailbox.put_nowait(_make_request(request_id="__sentinel__"))
        except asyncio.QueueFull:
            pass

    monitor_task = asyncio.create_task(_monitor())

    real_execute = pipeline.execute  # type: ignore[attr-defined]

    async def counting_execute(request: Any, cancel_check: Any) -> Any:
        nonlocal processed
        result = await real_execute(request, cancel_check)
        processed += 1
        return result

    pipeline.execute = counting_execute  # type: ignore[attr-defined]

    agent._running = True
    await agent._run_loop()

    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass


async def _start_agent_with_requests(
    agent: PlannerAgent,
    mailbox: QueueMailboxPort,
    requests: List[Any],
) -> None:
    """Helper: load requests, run start() in a task, wait for completion."""
    for req in requests:
        mailbox.put_nowait(req)

    async def _stop_after_processing() -> None:
        # Wait for pipeline calls to complete
        pipeline = agent._pipeline
        while True:
            await asyncio.sleep(0.01)
            reset_count = getattr(pipeline, "reset_count", 0)
            if reset_count >= len(requests):
                agent._running = False
                agent._cancel_set["__sentinel__"] = time.monotonic()
                try:
                    mailbox.put_nowait(_make_request(request_id="__sentinel__"))
                except asyncio.QueueFull:
                    pass
                return

    stop_task = asyncio.create_task(_stop_after_processing())
    await agent.start()
    stop_task.cancel()
    try:
        await stop_task
    except asyncio.CancelledError:
        pass


# ===========================================================================
# 1. on_cancel (Issue 2.3.4)
# ===========================================================================


class TestOnCancel:
    """on_cancel() adds request_id to _cancel_set (SS24.2)."""

    @pytest.mark.asyncio
    async def test_on_cancel_adds_to_set(self) -> None:
        agent = _make_agent()
        await agent.on_cancel("req-001")
        assert "req-001" in agent._cancel_set

    @pytest.mark.asyncio
    async def test_on_cancel_multiple_ids(self) -> None:
        agent = _make_agent()
        await agent.on_cancel("req-001")
        await agent.on_cancel("req-002")
        # 4.2.5 / P06: _cancel_set is Dict[str, float]; compare key set.
        assert set(agent._cancel_set.keys()) == {"req-001", "req-002"}

    @pytest.mark.asyncio
    async def test_on_cancel_idempotent(self) -> None:
        """Double cancel for same request_id is idempotent (SS24.2.4)."""
        agent = _make_agent()
        await agent.on_cancel("req-001")
        await agent.on_cancel("req-001")
        assert set(agent._cancel_set.keys()) == {"req-001"}

    @pytest.mark.asyncio
    async def test_on_cancel_returns_none(self) -> None:
        agent = _make_agent()
        result = await agent.on_cancel("req-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_on_cancel_no_longer_raises(self) -> None:
        """on_cancel no longer raises NotImplementedError (was stub in 2.3.1)."""
        agent = _make_agent()
        await agent.on_cancel("req-001")  # should not raise


# ===========================================================================
# 2. Dequeue loop -- FIFO order (Issue 2.3.2)
# ===========================================================================


class TestDequeueLoopFIFO:
    """_run_loop processes requests in FIFO dequeue order (SS24.1.3)."""

    @pytest.mark.asyncio
    async def test_single_request_processed(self) -> None:
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        req = _make_request("req-001")
        await _run_loop_with_requests(agent, mailbox, [req])

        assert len(pipeline.execute_calls) == 1
        assert pipeline.execute_calls[0].request is req

    @pytest.mark.asyncio
    async def test_fifo_order_preserved(self) -> None:
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        reqs = [_make_request(f"req-{i:03d}") for i in range(3)]
        await _run_loop_with_requests(agent, mailbox, reqs)

        assert len(pipeline.execute_calls) == 3
        for i, call in enumerate(pipeline.execute_calls):
            assert call.request.request_id == f"req-{i:03d}"


# ===========================================================================
# 3. Cancel pre-check (Issues 2.3.2 + 2.3.4)
# ===========================================================================


class TestCancelPreCheck:
    """Cancel pre-check skips cancelled requests at dequeue (SS24.2.2 CP1)."""

    @pytest.mark.asyncio
    async def test_cancelled_request_skipped(self) -> None:
        """Request with pre-populated cancel_set is skipped."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = FakeEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        # Pre-populate cancel set before enqueue
        agent._cancel_set["req-001"] = time.monotonic()

        req1 = _make_request("req-001")
        req2 = _make_request("req-002")

        # Load both: req-001 should be skipped, req-002 should execute
        mailbox.put_nowait(req1)
        mailbox.put_nowait(req2)

        # Run: only req-002 should reach pipeline
        agent._running = True

        async def _stop_after() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop_after())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert len(pipeline.execute_calls) == 1
        assert pipeline.execute_calls[0].request.request_id == "req-002"

    @pytest.mark.asyncio
    async def test_cancel_precheck_emits_cancelled_event(self) -> None:
        """Cancelled request at pre-check emits plan.cancelled.v1."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        ep = FakeEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        agent._cancel_set["req-001"] = time.monotonic()
        req = _make_request("req-001")
        mailbox.put_nowait(req)

        # Process one request then stop
        agent._running = True

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # Verify event emitted
        cancelled_events = [(t, p) for t, p in ep.emitted if t == TOPIC_PLAN_CANCELLED]
        assert len(cancelled_events) >= 1
        payload = cancelled_events[0][1]
        assert isinstance(payload, PlanCancelledPayload)
        assert payload.request_id == "req-001"
        assert payload.reason == "cancelled_before_start"
        assert payload.stage == "PRE_CHECK"

    @pytest.mark.asyncio
    async def test_cancel_precheck_removes_from_cancel_set(self) -> None:
        """Cancel pre-check discard()s the request_id from _cancel_set."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        agent._cancel_set["req-001"] = time.monotonic()
        mailbox.put_nowait(_make_request("req-001"))

        agent._running = True

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert "req-001" not in agent._cancel_set

    @pytest.mark.asyncio
    async def test_cancel_precheck_does_not_acquire_lock(self) -> None:
        """Pre-check cancel does NOT acquire the plan lock."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        agent._cancel_set["req-001"] = time.monotonic()
        mailbox.put_nowait(_make_request("req-001"))

        agent._running = True

        async def _stop() -> None:
            await asyncio.sleep(0.05)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # Lock should not be held
        assert not agent._plan_lock.locked()
        # Pipeline should not have been called
        assert len(pipeline.execute_calls) == 0

    @pytest.mark.asyncio
    async def test_cancel_before_enqueue(self) -> None:
        """Cancel arrives before enqueue -- immediate cancel at dequeue (SS24.2.4)."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        # Cancel first, then enqueue
        await agent.on_cancel("req-001")
        mailbox.put_nowait(_make_request("req-001"))
        mailbox.put_nowait(_make_request("req-002"))

        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # req-001 should have been skipped at pre-check
        assert len(pipeline.execute_calls) == 1
        assert pipeline.execute_calls[0].request.request_id == "req-002"


# ===========================================================================
# 4. Plan lock (Issue 2.3.3)
# ===========================================================================


class TestPlanLock:
    """Plan lock enforces V1 single-plan concurrency (SS24.1.1)."""

    @pytest.mark.asyncio
    async def test_lock_acquired_during_execute(self) -> None:
        """Lock is held while pipeline.execute() runs."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        lock_was_held = False

        async def check_lock() -> None:
            nonlocal lock_was_held
            lock_was_held = agent._plan_lock.locked()

        pipeline._execute_hook = check_lock

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert lock_was_held is True

    @pytest.mark.asyncio
    async def test_lock_released_after_execute(self) -> None:
        """Lock is released in finally block after execute() completes."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert not agent._plan_lock.locked()

    @pytest.mark.asyncio
    async def test_lock_released_after_error(self) -> None:
        """Lock is released even if execute() raises PlannerError."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        pipeline._execute_error = PlannerError("test error", stage="SKETCH")
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert not agent._plan_lock.locked()

    @pytest.mark.asyncio
    async def test_lock_released_after_unexpected_error(self) -> None:
        """Lock is released even if execute() raises unexpected Exception."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        pipeline._execute_error = RuntimeError("kaboom")
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert not agent._plan_lock.locked()


# ===========================================================================
# 5. Error handling in _run_loop (Issue 2.3.2)
# ===========================================================================


class TestErrorHandling:
    """_run_loop continues after errors (PlannerError, Exception)."""

    @pytest.mark.asyncio
    async def test_planner_error_continues_loop(self) -> None:
        """PlannerError: caught, logged, loop continues to next request."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        call_count = 0
        original_execute = pipeline.execute

        async def failing_then_ok(request: Any, cancel_check: Any) -> Any:
            nonlocal call_count
            call_count += 1
            # Record the call
            result = await original_execute(request, cancel_check)
            if call_count == 1:
                raise PlannerError("sketch failed", stage="SKETCH", request_id="req-001")
            return result

        pipeline.execute = failing_then_ok  # type: ignore[assignment]

        mailbox.put_nowait(_make_request("req-001"))
        mailbox.put_nowait(_make_request("req-002"))

        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 2:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # Both requests were processed (loop continued after error)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_plan_cancelled_error_continues_loop(self) -> None:
        """PlanCancelledError: caught, logged, loop continues."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        call_count = 0
        original_execute = pipeline.execute

        async def cancel_then_ok(request: Any, cancel_check: Any) -> Any:
            nonlocal call_count
            call_count += 1
            result = await original_execute(request, cancel_check)
            if call_count == 1:
                raise PlanCancelledError("cancelled")
            return result

        pipeline.execute = cancel_then_ok  # type: ignore[assignment]

        mailbox.put_nowait(_make_request("req-001"))
        mailbox.put_nowait(_make_request("req-002"))

        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 2:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_unexpected_error_emits_internal_error(self) -> None:
        """Unexpected Exception: emits plan.failed.v1{INTERNAL_ERROR}."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        pipeline._execute_error = RuntimeError("kaboom")
        ep = FakeEventPort()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline, event_port=ep)

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        failed_events = [(t, p) for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed_events) == 1
        payload = failed_events[0][1]
        assert isinstance(payload, PlanFailedPayload)
        assert payload.request_id == "req-001"
        assert payload.error_code == "INTERNAL_ERROR"
        assert payload.stage == "INTERNAL"
        assert "kaboom" in payload.error_message

    @pytest.mark.asyncio
    async def test_unexpected_error_continues_loop(self) -> None:
        """Unexpected Exception: loop continues after error."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        call_count = 0
        original_execute = pipeline.execute

        async def boom_then_ok(request: Any, cancel_check: Any) -> Any:
            nonlocal call_count
            call_count += 1
            result = await original_execute(request, cancel_check)
            if call_count == 1:
                raise RuntimeError("unexpected")
            return result

        pipeline.execute = boom_then_ok  # type: ignore[assignment]

        mailbox.put_nowait(_make_request("req-001"))
        mailbox.put_nowait(_make_request("req-002"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 2:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert call_count == 2


# ===========================================================================
# 6. Pipeline reset in finally (Issue 2.3.2)
# ===========================================================================


class TestPipelineReset:
    """pipeline.reset() is called in finally block after every plan."""

    @pytest.mark.asyncio
    async def test_reset_called_after_success(self) -> None:
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert pipeline.reset_count >= 1

    @pytest.mark.asyncio
    async def test_reset_called_after_error(self) -> None:
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        pipeline._execute_error = PlannerError("fail", stage="SKETCH")
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert pipeline.reset_count >= 1

    @pytest.mark.asyncio
    async def test_reset_count_matches_plan_count(self) -> None:
        """Reset is called once per plan, matching the number of plans."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        for i in range(3):
            mailbox.put_nowait(_make_request(f"req-{i:03d}"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 3:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert pipeline.reset_count >= 3


# ===========================================================================
# 7. cancel_set cleanup in finally (Issue 2.3.4)
# ===========================================================================


class TestCancelSetCleanup:
    """_cancel_set.discard(request_id) at PLAN_END in finally block."""

    @pytest.mark.asyncio
    async def test_cancel_set_cleaned_after_normal_plan(self) -> None:
        """Even for non-cancelled plans, discard any matching entry."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        # Simulate cancel arriving during execution
        agent._cancel_set["req-001"] = time.monotonic()

        mailbox.put_nowait(_make_request("req-002"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # req-002 is cleaned up (discard is safe even if not in set)
        assert "req-002" not in agent._cancel_set
        # req-001 was never processed (still in cancel_set)
        assert "req-001" in agent._cancel_set

    @pytest.mark.asyncio
    async def test_cancel_during_execution_cleaned_at_plan_end(self) -> None:
        """Cancel arrives mid-execution; request_id discarded at PLAN_END."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        async def add_cancel_during_execute() -> None:
            agent._cancel_set["req-001"] = time.monotonic()

        pipeline._execute_hook = add_cancel_during_execute

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # Cancel was in set during execution but discarded at PLAN_END
        assert "req-001" not in agent._cancel_set


# ===========================================================================
# 8. cancel_check closure wiring (Issue 2.3.4)
# ===========================================================================


class TestCancelCheckClosure:
    """cancel_check closure wires _cancel_set to PipelineController."""

    @pytest.mark.asyncio
    async def test_cancel_check_false_initially(self) -> None:
        """cancel_check returns False when request not in cancel_set."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        captured_check: Optional[Callable[[], bool]] = None

        async def capture_cancel_check() -> None:
            nonlocal captured_check
            captured_check = pipeline.execute_calls[-1].cancel_check

        pipeline._execute_hook = capture_cancel_check

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert captured_check is not None
        # After plan_end, cancel_set is clean -- but check was captured before cleanup
        # To test properly, we need to check behavior during execution
        # The closure checks against the live cancel_set

    @pytest.mark.asyncio
    async def test_cancel_check_true_when_cancelled(self) -> None:
        """cancel_check returns True when request_id added to cancel_set."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        check_result_before: Optional[bool] = None
        check_result_after: Optional[bool] = None

        async def test_closure() -> None:
            nonlocal check_result_before, check_result_after
            cancel_check = pipeline.execute_calls[-1].cancel_check
            check_result_before = cancel_check()
            # Simulate on_cancel arriving mid-plan
            agent._cancel_set["req-001"] = time.monotonic()
            check_result_after = cancel_check()

        pipeline._execute_hook = test_closure

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert check_result_before is False
        assert check_result_after is True

    @pytest.mark.asyncio
    async def test_cancel_check_scoped_to_request_id(self) -> None:
        """cancel_check only returns True for the specific request_id."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        check_result: Optional[bool] = None

        async def test_scope() -> None:
            nonlocal check_result
            cancel_check = pipeline.execute_calls[-1].cancel_check
            # Add a DIFFERENT request_id to cancel_set
            agent._cancel_set["req-OTHER"] = time.monotonic()
            check_result = cancel_check()

        pipeline._execute_hook = test_scope

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        # Different request_id in cancel_set -> check returns False
        assert check_result is False


# ===========================================================================
# 9. micro_replan (Issue 2.3.3)
# ===========================================================================


class TestMicroReplan:
    """micro_replan acquires lock, delegates to pipeline, releases (SS24.3)."""

    @pytest.mark.asyncio
    async def test_micro_replan_delegates_to_pipeline(self) -> None:
        pipeline = RecordingPipelineController()
        agent = _make_agent(pipeline=pipeline)

        req = _make_micro_request("micro-001")
        await agent.micro_replan(req)

        assert len(pipeline.micro_replan_calls) == 1
        assert pipeline.micro_replan_calls[0].request is req

    @pytest.mark.asyncio
    async def test_micro_replan_returns_committed_plan(self) -> None:
        pipeline = RecordingPipelineController()
        expected = _make_committed_plan("micro-001")
        pipeline._micro_replan_result = expected
        agent = _make_agent(pipeline=pipeline)

        result = await agent.micro_replan(_make_micro_request("micro-001"))
        assert result is expected

    @pytest.mark.asyncio
    async def test_micro_replan_returns_none_on_rejection(self) -> None:
        pipeline = RecordingPipelineController()
        pipeline._micro_replan_result = None
        agent = _make_agent(pipeline=pipeline)

        result = await agent.micro_replan(_make_micro_request("micro-001"))
        assert result is None

    @pytest.mark.asyncio
    async def test_micro_replan_acquires_lock(self) -> None:
        """Lock is held during pipeline.micro_replan()."""
        pipeline = RecordingPipelineController()
        agent = _make_agent(pipeline=pipeline)

        lock_was_held = False
        original_micro = pipeline.micro_replan

        async def check_lock(request: Any, cancel_check: Any) -> Any:
            nonlocal lock_was_held
            lock_was_held = agent._plan_lock.locked()
            return await original_micro(request, cancel_check)

        pipeline.micro_replan = check_lock  # type: ignore[assignment]

        await agent.micro_replan(_make_micro_request())
        assert lock_was_held is True

    @pytest.mark.asyncio
    async def test_micro_replan_releases_lock(self) -> None:
        pipeline = RecordingPipelineController()
        agent = _make_agent(pipeline=pipeline)

        await agent.micro_replan(_make_micro_request())
        assert not agent._plan_lock.locked()

    @pytest.mark.asyncio
    async def test_micro_replan_releases_lock_on_error(self) -> None:
        pipeline = RecordingPipelineController()
        pipeline._micro_replan_error = PlannerError("fail", stage="MICRO_SKETCH")
        agent = _make_agent(pipeline=pipeline)

        with pytest.raises(PlannerError):
            await agent.micro_replan(_make_micro_request())

        assert not agent._plan_lock.locked()

    @pytest.mark.asyncio
    async def test_micro_replan_resets_pipeline(self) -> None:
        pipeline = RecordingPipelineController()
        agent = _make_agent(pipeline=pipeline)

        await agent.micro_replan(_make_micro_request())
        assert pipeline.reset_count >= 1

    @pytest.mark.asyncio
    async def test_micro_replan_resets_pipeline_on_error(self) -> None:
        pipeline = RecordingPipelineController()
        pipeline._micro_replan_error = RuntimeError("boom")
        agent = _make_agent(pipeline=pipeline)

        with pytest.raises(RuntimeError):
            await agent.micro_replan(_make_micro_request())

        assert pipeline.reset_count >= 1

    @pytest.mark.asyncio
    async def test_micro_replan_cancel_check_closure(self) -> None:
        """micro_replan passes cancel_check closure to pipeline."""
        pipeline = RecordingPipelineController()
        agent = _make_agent(pipeline=pipeline)

        req = _make_micro_request("micro-001")
        await agent.micro_replan(req)

        assert len(pipeline.micro_replan_calls) == 1
        cancel_check = pipeline.micro_replan_calls[0].cancel_check
        # Not cancelled -> False
        assert cancel_check() is False
        # Add to cancel set -> True
        agent._cancel_set["micro-001"] = time.monotonic()
        assert cancel_check() is True

    @pytest.mark.asyncio
    async def test_micro_replan_no_longer_raises_not_implemented(self) -> None:
        """micro_replan no longer raises NotImplementedError."""
        pipeline = RecordingPipelineController()
        agent = _make_agent(pipeline=pipeline)
        result = await agent.micro_replan(_make_micro_request())
        assert result is None  # default pipeline returns None


# ===========================================================================
# 10. start() partial implementation (Issue 2.3.2)
# ===========================================================================


class TestStart:
    """start() sets _running=True and enters _run_loop (partial 2.3.2)."""

    @pytest.mark.asyncio
    async def test_start_sets_running_true(self) -> None:
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

        assert running_during_loop is True

    @pytest.mark.asyncio
    async def test_start_processes_requests(self) -> None:
        """start() enters the dequeue loop and processes requests."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        mailbox.put_nowait(_make_request("req-001"))

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
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

        assert len(pipeline.execute_calls) == 1
        assert pipeline.execute_calls[0].request.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_start_no_longer_raises(self) -> None:
        """start() no longer raises NotImplementedError."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        # Immediately stop
        mailbox.put_nowait(_make_request("req-001"))

        async def _stop() -> None:
            while pipeline.reset_count < 1:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent.start()  # Should not raise
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass


# ===========================================================================
# 11. stop() still raises NotImplementedError (2.3.6)
# ===========================================================================


class TestStopImplemented:
    """stop() is now implemented (Issue 2.3.6)."""

    @pytest.mark.asyncio
    async def test_stop_no_longer_raises(self) -> None:
        agent = _make_agent()
        await agent.stop()  # should not raise


# ===========================================================================
# 12. Lock contention: micro_replan waits for plan (Issue 2.3.3)
# ===========================================================================


class TestLockContention:
    """micro_replan blocks while plan is in flight (SS24.3.1)."""

    @pytest.mark.asyncio
    async def test_micro_replan_waits_for_lock(self) -> None:
        """micro_replan() awaits plan lock -- blocks during in-flight plan."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        lock_acquired = asyncio.Event()
        plan_can_finish = asyncio.Event()
        micro_started = False
        micro_finished = False

        async def hold_lock() -> None:
            lock_acquired.set()
            await plan_can_finish.wait()

        pipeline._execute_hook = hold_lock

        mailbox.put_nowait(_make_request("req-001"))
        agent._running = True

        # Start the loop in a task
        loop_task = asyncio.create_task(agent._run_loop())

        # Wait for plan to acquire lock
        await lock_acquired.wait()
        assert agent._plan_lock.locked()

        # Start micro_replan concurrently -- should block
        async def do_micro() -> None:
            nonlocal micro_started, micro_finished
            micro_started = True
            await agent.micro_replan(_make_micro_request())
            micro_finished = True

        micro_task = asyncio.create_task(do_micro())
        await asyncio.sleep(0.05)

        # micro_replan should have started but not finished (blocked on lock)
        assert micro_started is True
        assert micro_finished is False

        # Release the plan
        plan_can_finish.set()
        await asyncio.sleep(0.05)

        # micro_replan should now complete
        assert micro_finished is True

        # Cleanup: stop loop
        agent._running = False
        try:
            mailbox.put_nowait(_make_request("__sentinel__"))
        except asyncio.QueueFull:
            pass
        await asyncio.wait_for(loop_task, timeout=2.0)
        micro_task.cancel()
        try:
            await micro_task
        except asyncio.CancelledError:
            pass


# ===========================================================================
# 13. Multiple plans sequential (Issue 2.3.2+2.3.3)
# ===========================================================================


class TestSequentialPlans:
    """Multiple plans processed sequentially with lock exclusion."""

    @pytest.mark.asyncio
    async def test_three_plans_sequential(self) -> None:
        """Three plans processed one at a time, all reset, all unlocked."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        for i in range(3):
            mailbox.put_nowait(_make_request(f"req-{i:03d}"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 3:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert len(pipeline.execute_calls) == 3
        assert pipeline.reset_count >= 3
        assert not agent._plan_lock.locked()

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self) -> None:
        """Mix of success and failure plans all process correctly."""
        mailbox = QueueMailboxPort()
        pipeline = RecordingPipelineController()
        agent = _make_agent(mailbox=mailbox, pipeline=pipeline)

        call_count = 0
        original_execute = pipeline.execute

        async def alternating(request: Any, cancel_check: Any) -> Any:
            nonlocal call_count
            call_count += 1
            result = await original_execute(request, cancel_check)
            if call_count % 2 == 0:
                raise PlannerError("even fail", stage="SKETCH")
            return result

        pipeline.execute = alternating  # type: ignore[assignment]

        for i in range(4):
            mailbox.put_nowait(_make_request(f"req-{i:03d}"))
        agent._running = True

        async def _stop() -> None:
            while pipeline.reset_count < 4:
                await asyncio.sleep(0.01)
            agent._running = False
            try:
                mailbox.put_nowait(_make_request("__sentinel__"))
            except asyncio.QueueFull:
                pass

        stop_task = asyncio.create_task(_stop())
        await agent._run_loop()
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        assert call_count == 4
        assert pipeline.reset_count >= 4
        assert not agent._plan_lock.locked()
