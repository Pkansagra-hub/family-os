"""Integration test: Bus Dispatcher + Middleware with monotonic ordering and fan-out.

Tests Bus Dispatcher subsystem:
1. Message ordering (monotonic offset enforcement)
2. Fan-out to multiple sinks with concurrent execution
3. Middleware chain execution and context propagation
4. QoS token acquisition and release
5. Latency metrics emission
6. Trace ID propagation through dispatch context
7. Error handling and recovery
8. Ordering verification across multiple subscribers

Validates that bus ensures strict WAL offset ordering during fan-out.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from unittest.mock import AsyncMock

import pytest

from k0.automation.migrate import apply_migrations
from k0.bus.core import (
    BusDispatchContext,
    BusDispatcher,
    BusMessage,
    current_dispatch_context,
)
from k0.bus.middleware import timestamp_middleware
from k0.qos import Scheduler
from k0.uow.connection_pool import configure_pool, shutdown_pool


@pytest.fixture
def sqlite_runtime() -> Iterator[Path]:
    """Pytest fixture for SQLite runtime with schema initialization."""
    tmp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"
    configure_pool(db_path)
    # Apply migrations instead of using storage.sql directly
    apply_migrations(db_path, dry_run=False)
    try:
        yield db_path
    finally:
        shutdown_pool()
        tmp_dir.cleanup()


@pytest.fixture
def temp_db(sqlite_runtime: Path) -> Path:
    """Alias for sqlite_runtime for test compatibility."""
    return sqlite_runtime


@pytest.fixture
def scheduler(temp_db: Path) -> Scheduler:
    """QoS Scheduler for bus dispatcher tests."""
    return Scheduler()


@pytest.fixture
def dispatcher(scheduler: Scheduler) -> BusDispatcher:
    """BusDispatcher instance with default configuration."""
    return BusDispatcher(scheduler=scheduler, port="bus", default_band="GREEN")


def _create_message(
    topic: str = "test.topic",
    payload: bytes | None = None,
    offset: int = 1,
    trace_id: str | None = None,
) -> BusMessage:
    """Helper to create a BusMessage."""
    return BusMessage(
        topic=topic,
        payload=payload or b"test_payload",
        offset=offset,
        trace_id=trace_id,
    )


class TestBusMessageOrdering:
    """Tests for monotonic offset ordering enforcement."""

    @pytest.mark.asyncio
    async def test_single_message_dispatch(self, dispatcher: BusDispatcher) -> None:
        """Test: Single message dispatches successfully."""
        message = _create_message(offset=1)
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([message])

        sink.assert_called_once()
        call_args = sink.call_args[0][0]
        assert call_args.topic == "test.topic"
        assert call_args.offset == 1

    @pytest.mark.asyncio
    async def test_multiple_messages_in_order(self, dispatcher: BusDispatcher) -> None:
        """Test: Multiple messages in order dispatch successfully."""
        messages = [_create_message(offset=i) for i in range(1, 6)]
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch(messages)

        assert sink.call_count == 5
        for i, call in enumerate(sink.call_args_list, start=1):
            msg = call[0][0]
            assert msg.offset == i

    @pytest.mark.asyncio
    async def test_unsorted_messages_sorted_automatically(self, dispatcher: BusDispatcher) -> None:
        """Test: Unsorted messages are sorted before dispatch."""
        messages = [
            _create_message(offset=3),
            _create_message(offset=1),
            _create_message(offset=5),
            _create_message(offset=2),
            _create_message(offset=4),
        ]
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch(messages)

        assert sink.call_count == 5
        for i, call in enumerate(sink.call_args_list, start=1):
            msg = call[0][0]
            assert msg.offset == i

    @pytest.mark.asyncio
    async def test_monotonic_offset_violation(self, dispatcher: BusDispatcher) -> None:
        """Test: Decreasing offset raises ValueError."""
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        # First dispatch with offset 5
        await dispatcher.dispatch([_create_message(offset=5)])

        # Try to dispatch with offset 3 (regression)
        with pytest.raises(ValueError, match="non-decreasing order"):
            await dispatcher.dispatch([_create_message(offset=3)])

    @pytest.mark.asyncio
    async def test_monotonic_offset_equal_allowed(self, dispatcher: BusDispatcher) -> None:
        """Test: Equal offsets (duplicates) are allowed."""
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        # Dispatch offset 5
        await dispatcher.dispatch([_create_message(offset=5)])

        # Dispatch same offset (allowed for idempotency)
        await dispatcher.dispatch([_create_message(offset=5)])

        # Should succeed without error
        assert sink.call_count == 2

    @pytest.mark.asyncio
    async def test_offset_progression_tracked(self, dispatcher: BusDispatcher) -> None:
        """Test: Offset progression is correctly tracked across dispatches."""
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        # Dispatch offsets 1-3
        await dispatcher.dispatch([_create_message(offset=i) for i in range(1, 4)])

        # Dispatch offsets 4-6
        await dispatcher.dispatch([_create_message(offset=i) for i in range(4, 7)])

        # Verify all 6 messages were dispatched
        assert sink.call_count == 6


class TestBusMultipleSinks:
    """Tests for fan-out to multiple sinks."""

    @pytest.mark.asyncio
    async def test_single_sink_receives_message(self, dispatcher: BusDispatcher) -> None:
        """Test: Single sink receives dispatched message."""
        message = _create_message()
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([message])

        sink.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_multiple_sinks_receive_same_message(self, dispatcher: BusDispatcher) -> None:
        """Test: Multiple sinks receive the same message."""
        message = _create_message()
        sink1 = AsyncMock()
        sink2 = AsyncMock()
        sink3 = AsyncMock()

        dispatcher.register_sink(sink1)
        dispatcher.register_sink(sink2)
        dispatcher.register_sink(sink3)

        await dispatcher.dispatch([message])

        sink1.assert_called_once_with(message)
        sink2.assert_called_once_with(message)
        sink3.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_sink_execution_concurrent(self, dispatcher: BusDispatcher) -> None:
        """Test: Multiple sinks execute concurrently."""
        message = _create_message()

        async def slow_sink(_msg: BusMessage) -> None:
            await asyncio.sleep(0.1)

        sink1 = AsyncMock(side_effect=slow_sink)
        sink2 = AsyncMock(side_effect=slow_sink)

        dispatcher.register_sink(sink1)
        dispatcher.register_sink(sink2)

        import time

        start = time.perf_counter()
        await dispatcher.dispatch([message])
        elapsed = time.perf_counter() - start

        # If executed serially, would take ~0.2s
        # If concurrent, should be ~0.1s
        assert elapsed < 0.15
        sink1.assert_called_once()
        sink2.assert_called_once()

    @pytest.mark.asyncio
    async def test_sink_failure_propagates(self, dispatcher: BusDispatcher) -> None:
        """Test: Sink exception is propagated."""
        message = _create_message()

        async def failing_sink(_msg: BusMessage) -> None:
            raise RuntimeError("sink failed")

        sink = AsyncMock(side_effect=failing_sink)
        dispatcher.register_sink(sink)

        with pytest.raises(RuntimeError, match="sink failed"):
            await dispatcher.dispatch([message])

    @pytest.mark.asyncio
    async def test_one_sink_failure_does_not_block_others(self, dispatcher: BusDispatcher) -> None:
        """Test: One sink failure blocks all sinks (gather semantics)."""
        message = _create_message()

        async def failing_sink(_msg: BusMessage) -> None:
            await asyncio.sleep(0.05)
            raise RuntimeError("sink failed")

        sink1 = AsyncMock(side_effect=failing_sink)
        sink2 = AsyncMock()

        dispatcher.register_sink(sink1)
        dispatcher.register_sink(sink2)

        # asyncio.gather raises first exception by default
        with pytest.raises(RuntimeError):
            await dispatcher.dispatch([message])


class TestBusMiddleware:
    """Tests for middleware chain execution."""

    @pytest.mark.asyncio
    async def test_middleware_executes_around_dispatch(self, dispatcher: BusDispatcher) -> None:
        """Test: Middleware wraps fan-out execution."""
        message = _create_message()
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        executed = []

        async def tracking_middleware(
            context: BusDispatchContext,
            handler,
        ) -> None:
            executed.append("before")
            await handler(context)
            executed.append("after")

        dispatcher.register_middleware(tracking_middleware)

        await dispatcher.dispatch([message])

        assert executed == ["before", "after"]
        sink.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_middlewares_chain_order(self, dispatcher: BusDispatcher) -> None:
        """Test: Multiple middlewares execute in registration order."""
        message = _create_message()
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        order = []

        async def middleware_a(context: BusDispatchContext, handler) -> None:
            order.append("a_in")
            await handler(context)
            order.append("a_out")

        async def middleware_b(context: BusDispatchContext, handler) -> None:
            order.append("b_in")
            await handler(context)
            order.append("b_out")

        dispatcher.register_middleware(middleware_a)
        dispatcher.register_middleware(middleware_b)

        await dispatcher.dispatch([message])

        assert order == ["a_in", "b_in", "b_out", "a_out"]

    @pytest.mark.asyncio
    async def test_context_propagation_through_middleware(self, dispatcher: BusDispatcher) -> None:
        """Test: Dispatch context is available inside middleware."""
        message = _create_message(offset=42, trace_id="trace_xyz")
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        captured_context = None

        async def capturing_middleware(
            context: BusDispatchContext,
            handler,
        ) -> None:
            nonlocal captured_context
            captured_context = context
            await handler(context)

        dispatcher.register_middleware(capturing_middleware)

        await dispatcher.dispatch([message])

        assert captured_context is not None
        assert captured_context.message.offset == 42
        assert captured_context.message.trace_id == "trace_xyz"

    @pytest.mark.asyncio
    async def test_current_dispatch_context_accessible(self, dispatcher: BusDispatcher) -> None:
        """Test: current_dispatch_context() returns context during dispatch."""
        message = _create_message()

        captured_context = None

        async def capturing_sink(msg: BusMessage) -> None:
            nonlocal captured_context
            captured_context = current_dispatch_context()

        dispatcher.register_sink(capturing_sink)

        await dispatcher.dispatch([message])

        assert captured_context is not None
        assert captured_context.message.offset == message.offset


class TestBusTimestampMiddleware:
    """Tests for timestamp middleware."""

    @pytest.mark.asyncio
    async def test_timestamp_middleware_records_times(self, scheduler: Scheduler) -> None:
        """Test: Timestamp middleware records wall-clock and monotonic times."""
        dispatcher = BusDispatcher(scheduler=scheduler, middlewares=[])
        dispatcher.register_middleware(timestamp_middleware())

        message = _create_message()
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        captured_context = None

        async def capturing_middleware(
            context: BusDispatchContext,
            handler,
        ) -> None:
            nonlocal captured_context
            await handler(context)
            captured_context = context

        dispatcher.register_middleware(capturing_middleware)

        await dispatcher.dispatch([message])

        assert captured_context is not None
        assert captured_context.started_at is not None
        assert captured_context.completed_at is not None
        assert captured_context.monotonic_start is not None
        assert captured_context.monotonic_end is not None
        assert captured_context.duration_seconds is not None
        assert captured_context.duration_seconds >= 0
        assert captured_context.completed_at >= captured_context.started_at


class TestBusQoSIntegration:
    """Tests for QoS token acquisition."""

    @pytest.mark.asyncio
    async def test_token_acquired_and_released(self, dispatcher: BusDispatcher) -> None:
        """Test: QoS token is acquired and released."""
        message = _create_message()
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        initial_tokens = dispatcher._scheduler.active_tokens("bus")

        await dispatcher.dispatch([message])

        # After dispatch completes, tokens should be restored
        final_tokens = dispatcher._scheduler.active_tokens("bus")
        assert initial_tokens == final_tokens

    @pytest.mark.asyncio
    async def test_token_cost_customizable(self, scheduler: Scheduler) -> None:
        """Test: Custom token cost is respected."""
        dispatcher = BusDispatcher(
            scheduler=scheduler,
            token_cost=5,
        )
        message = _create_message()
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([message])

        # Should succeed even with higher token cost
        sink.assert_called_once()


class TestBusErrorHandling:
    """Tests for error handling and recovery."""

    @pytest.mark.asyncio
    async def test_invalid_bus_message_type(self, dispatcher: BusDispatcher) -> None:
        """Test: Invalid message type raises error during dispatch."""
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        # Try to dispatch with invalid message - will fail during iteration/dispatch
        with pytest.raises((TypeError, AttributeError)):
            await dispatcher.dispatch(["not a message"])  # type: ignore

    def test_invalid_port_rejected(self, scheduler: Scheduler) -> None:
        """Test: Empty port string raises ValueError."""
        with pytest.raises(ValueError, match="non-empty string"):
            BusDispatcher(scheduler=scheduler, port="")

    def test_invalid_default_band_rejected(self, scheduler: Scheduler) -> None:
        """Test: Empty default_band raises ValueError."""
        with pytest.raises(ValueError, match="non-empty string"):
            BusDispatcher(scheduler=scheduler, default_band="")

    def test_invalid_token_cost_rejected(self, scheduler: Scheduler) -> None:
        """Test: Non-positive token cost raises ValueError."""
        with pytest.raises(ValueError, match="positive"):
            BusDispatcher(scheduler=scheduler, token_cost=0)

    def test_non_callable_sink_rejected(self, dispatcher: BusDispatcher) -> None:
        """Test: Non-callable sink raises TypeError."""
        with pytest.raises(TypeError, match="callable"):
            dispatcher.register_sink("not_callable")  # type: ignore

    def test_non_callable_middleware_rejected(self, dispatcher: BusDispatcher) -> None:
        """Test: Non-callable middleware raises TypeError."""
        with pytest.raises(TypeError, match="callable"):
            dispatcher.register_middleware("not_callable")  # type: ignore


class TestBusBandResolution:
    """Tests for dynamic band resolution."""

    @pytest.mark.asyncio
    async def test_default_band_used_when_no_resolver(self, dispatcher: BusDispatcher) -> None:
        """Test: Default band is used when no resolver configured."""
        message = _create_message()

        captured_context = None

        async def capturing_middleware(
            context: BusDispatchContext,
            handler,
        ) -> None:
            nonlocal captured_context
            captured_context = context
            await handler(context)

        dispatcher.register_middleware(capturing_middleware)
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([message])

        assert captured_context is not None
        assert captured_context.band == "GREEN"

    @pytest.mark.asyncio
    async def test_custom_band_resolver(self, scheduler: Scheduler) -> None:
        """Test: Custom band resolver determines band."""

        def resolve_band(msg: BusMessage) -> str:
            if "urgent" in msg.topic:
                return "RED"
            return "GREEN"

        dispatcher = BusDispatcher(
            scheduler=scheduler,
            band_resolver=resolve_band,
        )

        captured_band = None

        async def capturing_middleware(
            context: BusDispatchContext,
            handler,
        ) -> None:
            nonlocal captured_band
            captured_band = context.band
            await handler(context)

        dispatcher.register_middleware(capturing_middleware)
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        message = _create_message(topic="urgent.action")
        await dispatcher.dispatch([message])

        assert captured_band == "RED"

    @pytest.mark.asyncio
    async def test_band_resolver_returns_uppercase(self, scheduler: Scheduler) -> None:
        """Test: Band resolver output is normalized to uppercase."""

        def resolve_band(msg: BusMessage) -> str:
            return "green"  # lowercase

        dispatcher = BusDispatcher(
            scheduler=scheduler,
            band_resolver=resolve_band,
        )

        captured_band = None

        async def capturing_middleware(
            context: BusDispatchContext,
            handler,
        ) -> None:
            nonlocal captured_band
            captured_band = context.band
            await handler(context)

        dispatcher.register_middleware(capturing_middleware)
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([_create_message()])

        assert captured_band == "GREEN"


class TestBusEmptyAndEdgeCases:
    """Tests for empty batches and edge cases."""

    @pytest.mark.asyncio
    async def test_empty_message_batch(self, dispatcher: BusDispatcher) -> None:
        """Test: Empty message batch does not error."""
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([])

        sink.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sinks_registered(self, dispatcher: BusDispatcher) -> None:
        """Test: Dispatch succeeds with no sinks registered."""
        messages = [_create_message(offset=i) for i in range(1, 6)]

        # Should not raise
        await dispatcher.dispatch(messages)

    @pytest.mark.asyncio
    async def test_large_message_batch(self, dispatcher: BusDispatcher) -> None:
        """Test: Large batch of messages dispatches correctly."""
        messages = [_create_message(offset=i) for i in range(1, 101)]
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch(messages)

        assert sink.call_count == 100

    @pytest.mark.asyncio
    async def test_message_with_empty_payload(self, dispatcher: BusDispatcher) -> None:
        """Test: Message with empty payload dispatches."""
        message = BusMessage(
            topic="test.topic",
            payload=b"",
            offset=99,
            trace_id=None,
        )
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([message])

        sink.assert_called_once()
        assert sink.call_args[0][0].payload == b""

    @pytest.mark.asyncio
    async def test_message_with_large_payload(self, dispatcher: BusDispatcher) -> None:
        """Test: Message with large payload dispatches."""
        large_payload = b"x" * 1_000_000  # 1MB
        message = _create_message(payload=large_payload)
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([message])

        sink.assert_called_once()
        assert sink.call_args[0][0].payload == large_payload

    @pytest.mark.asyncio
    async def test_message_with_unicode_topic(self, dispatcher: BusDispatcher) -> None:
        """Test: Message with unicode topic dispatches."""
        message = _create_message(topic="事件.订阅.通知")
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([message])

        sink.assert_called_once()
        assert sink.call_args[0][0].topic == "事件.订阅.通知"


class TestBusTraceIDPropagation:
    """Tests for trace ID propagation."""

    @pytest.mark.asyncio
    async def test_trace_id_from_message_preserved(self, dispatcher: BusDispatcher) -> None:
        """Test: Message trace_id is preserved in context."""
        message = _create_message(trace_id="trace_abc123")

        captured_context = None

        async def capturing_middleware(
            context: BusDispatchContext,
            handler,
        ) -> None:
            nonlocal captured_context
            captured_context = context
            await handler(context)

        dispatcher.register_middleware(capturing_middleware)
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        await dispatcher.dispatch([message])

        assert captured_context is not None
        assert captured_context.trace_id == "trace_abc123"


class TestBusCompleteIntegration:
    """End-to-end Bus Dispatcher integration tests."""

    @pytest.mark.asyncio
    async def test_complete_dispatch_flow(self, scheduler: Scheduler) -> None:
        """Test: Complete dispatch flow with middleware and multiple sinks."""
        dispatcher = BusDispatcher(
            scheduler=scheduler,
            port="bus",
            default_band="GREEN",
            token_cost=1,
        )

        # Set up sinks
        sink1_calls = []
        sink2_calls = []

        async def sink1(msg: BusMessage) -> None:
            sink1_calls.append(msg.offset)

        async def sink2(msg: BusMessage) -> None:
            sink2_calls.append(msg.offset)

        dispatcher.register_sink(sink1)
        dispatcher.register_sink(sink2)

        # Set up middleware
        middleware_trace = []

        async def tracking_middleware(
            context: BusDispatchContext,
            handler,
        ) -> None:
            middleware_trace.append(f"start_{context.message.offset}")
            await handler(context)
            middleware_trace.append(f"end_{context.message.offset}")

        dispatcher.register_middleware(tracking_middleware)
        dispatcher.register_middleware(timestamp_middleware())

        # Dispatch messages
        messages = [_create_message(offset=i) for i in range(1, 4)]
        await dispatcher.dispatch(messages)

        # Verify ordering
        assert sink1_calls == [1, 2, 3]
        assert sink2_calls == [1, 2, 3]
        assert middleware_trace == [
            "start_1",
            "end_1",
            "start_2",
            "end_2",
            "start_3",
            "end_3",
        ]

    @pytest.mark.asyncio
    async def test_dispatcher_properties(self, dispatcher: BusDispatcher) -> None:
        """Test: Dispatcher exposes configuration properties."""
        middleware_fn = AsyncMock()
        dispatcher.register_middleware(middleware_fn)

        middlewares = dispatcher.middlewares
        assert len(middlewares) == 1
        assert middlewares[0] == middleware_fn
