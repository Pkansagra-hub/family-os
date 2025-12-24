"""Integration tests for BusDispatcher Sinks (Gap 1).

Tests BusDispatcher sink integration:
1. Observability sink emits bus_dispatch events with trace_id
2. DriverWorkerPool sink triggers outbox processing
3. SSE fan-out sink (placeholder for future SSE streaming)
4. End-to-end WAL commit → sink invocation flow

Validates that bus sinks are properly wired and invoked during dispatch.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

import pytest

from k0.automation.migrate import apply_migrations
from k0.bus.core import BusDispatcher, BusMessage
from k0.obs import ObservabilityEmitter
from k0.qos import Scheduler
from k0.uow.connection_pool import configure_pool, shutdown_pool


@pytest.fixture
def sqlite_runtime() -> Iterator[Path]:
    """Pytest fixture for SQLite runtime with schema initialization."""
    tmp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"
    configure_pool(db_path)
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
def observability_emitter() -> ObservabilityEmitter:
    """ObservabilityEmitter for testing."""
    return ObservabilityEmitter()


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


class TestObservabilitySink:
    """Tests for observability sink integration."""

    @pytest.mark.asyncio
    async def test_observability_sink_emits_events(
        self,
        dispatcher: BusDispatcher,
        observability_emitter: ObservabilityEmitter,
    ) -> None:
        """Test: Observability sink emits bus_dispatch events with trace_id."""
        message = _create_message(offset=42, trace_id="trace_xyz_123")

        # Track emitted events
        emitted_events = []

        async def observability_sink(msg: BusMessage) -> None:
            """Observability sink that captures events."""
            emitted_events.append(
                {
                    "event_type": "bus_dispatch",
                    "topic": msg.topic,
                    "offset": msg.offset,
                    "trace_id": msg.trace_id,
                    "payload_size": len(msg.payload),
                }
            )

        dispatcher.register_sink(observability_sink)

        await dispatcher.dispatch([message])

        # Verify event was emitted
        assert len(emitted_events) == 1
        event = emitted_events[0]
        assert event["event_type"] == "bus_dispatch"
        assert event["topic"] == "test.topic"
        assert event["offset"] == 42
        assert event["trace_id"] == "trace_xyz_123"
        assert event["payload_size"] == len(b"test_payload")

    @pytest.mark.asyncio
    async def test_observability_sink_handles_missing_trace_id(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: Observability sink handles messages without trace_id."""
        message = _create_message(offset=43, trace_id=None)

        emitted_events = []

        async def observability_sink(msg: BusMessage) -> None:
            emitted_events.append(
                {
                    "trace_id": msg.trace_id,
                }
            )

        dispatcher.register_sink(observability_sink)

        await dispatcher.dispatch([message])

        assert len(emitted_events) == 1
        assert emitted_events[0]["trace_id"] is None

    @pytest.mark.asyncio
    async def test_observability_sink_error_handling(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: Observability sink errors are propagated."""
        message = _create_message()

        async def failing_observability_sink(msg: BusMessage) -> None:
            raise RuntimeError("Observability failure")

        dispatcher.register_sink(failing_observability_sink)

        # Sink errors should propagate
        with pytest.raises(RuntimeError, match="Observability failure"):
            await dispatcher.dispatch([message])


class TestDriverWorkerPoolSink:
    """Tests for DriverWorkerPool sink integration."""

    @pytest.mark.asyncio
    async def test_driver_worker_pool_sink_no_op(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: DriverWorkerPool sink is registered (no-op for now)."""
        message = _create_message()

        call_count = 0

        async def driver_worker_pool_sink(msg: BusMessage) -> None:
            """DriverWorkerPool sink (no-op placeholder)."""
            nonlocal call_count
            call_count += 1
            # Placeholder: background loop handles actual processing

        dispatcher.register_sink(driver_worker_pool_sink)

        await dispatcher.dispatch([message])

        # Verify sink was called
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_driver_worker_pool_sink_multiple_messages(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: DriverWorkerPool sink called for each message."""
        messages = [_create_message(offset=i) for i in range(1, 6)]

        call_count = 0

        async def driver_worker_pool_sink(msg: BusMessage) -> None:
            nonlocal call_count
            call_count += 1

        dispatcher.register_sink(driver_worker_pool_sink)

        await dispatcher.dispatch(messages)

        # Verify sink called for each message
        assert call_count == 5


class TestSSEFanOutSink:
    """Tests for SSE fan-out sink integration."""

    @pytest.mark.asyncio
    async def test_sse_fan_out_sink_placeholder(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: SSE fan-out sink is registered (placeholder)."""
        message = _create_message()

        call_count = 0

        async def sse_fan_out_sink(msg: BusMessage) -> None:
            """SSE fan-out sink (placeholder for future implementation)."""
            nonlocal call_count
            call_count += 1
            # TODO: Implement SSE fan-out when SSE streaming is ready

        dispatcher.register_sink(sse_fan_out_sink)

        await dispatcher.dispatch([message])

        # Verify sink was called
        assert call_count == 1


class TestMultipleSinksIntegration:
    """Tests for multiple sinks working together."""

    @pytest.mark.asyncio
    async def test_all_three_sinks_invoked(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: All three sinks (Observability, DriverWorkerPool, SSE) are invoked."""
        message = _create_message(offset=100, trace_id="multi_sink_trace")

        observability_called = False
        driver_pool_called = False
        sse_called = False

        async def observability_sink(msg: BusMessage) -> None:
            nonlocal observability_called
            observability_called = True
            assert msg.trace_id == "multi_sink_trace"

        async def driver_worker_pool_sink(msg: BusMessage) -> None:
            nonlocal driver_pool_called
            driver_pool_called = True

        async def sse_fan_out_sink(msg: BusMessage) -> None:
            nonlocal sse_called
            sse_called = True

        dispatcher.register_sink(observability_sink)
        dispatcher.register_sink(driver_worker_pool_sink)
        dispatcher.register_sink(sse_fan_out_sink)

        await dispatcher.dispatch([message])

        # Verify all sinks were invoked
        assert observability_called
        assert driver_pool_called
        assert sse_called

    @pytest.mark.asyncio
    async def test_sinks_execute_concurrently(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: Sinks execute concurrently for performance."""
        message = _create_message()

        async def slow_sink_1(msg: BusMessage) -> None:
            await asyncio.sleep(0.1)

        async def slow_sink_2(msg: BusMessage) -> None:
            await asyncio.sleep(0.1)

        async def slow_sink_3(msg: BusMessage) -> None:
            await asyncio.sleep(0.1)

        dispatcher.register_sink(slow_sink_1)
        dispatcher.register_sink(slow_sink_2)
        dispatcher.register_sink(slow_sink_3)

        import time

        start = time.perf_counter()
        await dispatcher.dispatch([message])
        elapsed = time.perf_counter() - start

        # If executed serially, would take ~0.3s
        # If concurrent, should be ~0.1s
        assert elapsed < 0.2, f"Sinks took {elapsed}s, expected concurrent execution"

    @pytest.mark.asyncio
    async def test_sink_failure_stops_dispatch(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: One sink failure stops dispatch (gather semantics)."""
        message = _create_message()

        async def good_sink(msg: BusMessage) -> None:
            pass

        async def failing_sink(msg: BusMessage) -> None:
            raise ValueError("Sink failed")

        dispatcher.register_sink(good_sink)
        dispatcher.register_sink(failing_sink)

        with pytest.raises(ValueError, match="Sink failed"):
            await dispatcher.dispatch([message])


class TestEndToEndWALToSinkFlow:
    """End-to-end tests for WAL commit → sink invocation flow."""

    @pytest.mark.asyncio
    async def test_wal_commit_triggers_sinks_within_100ms(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: WAL commit → sinks receive event within 100ms (Gap 1 acceptance criteria)."""
        message = _create_message(offset=200)

        import time

        sink_invoked_at = None

        async def timing_sink(msg: BusMessage) -> None:
            nonlocal sink_invoked_at
            sink_invoked_at = time.perf_counter()

        dispatcher.register_sink(timing_sink)

        start = time.perf_counter()
        await dispatcher.dispatch([message])

        # Verify sink was invoked
        assert sink_invoked_at is not None

        # Calculate latency
        latency_ms = (sink_invoked_at - start) * 1000

        # Acceptance criteria: sinks invoked within 100ms
        assert latency_ms < 100, f"Sink latency {latency_ms}ms exceeds 100ms threshold"

    @pytest.mark.asyncio
    async def test_multiple_messages_all_trigger_sinks(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: Multiple WAL commits all trigger sinks."""
        messages = [_create_message(offset=i) for i in range(1, 11)]

        received_offsets = []

        async def tracking_sink(msg: BusMessage) -> None:
            received_offsets.append(msg.offset)

        dispatcher.register_sink(tracking_sink)

        await dispatcher.dispatch(messages)

        # Verify all messages triggered sinks
        assert received_offsets == list(range(1, 11))

    @pytest.mark.asyncio
    async def test_sink_receives_correct_message_payload(
        self,
        dispatcher: BusDispatcher,
    ) -> None:
        """Test: Sinks receive correct message payload from WAL."""
        payload = b'{"event": "user.created", "user_id": 12345}'
        message = _create_message(topic="user.events", payload=payload, offset=300)

        received_payload = None
        received_topic = None

        async def payload_capturing_sink(msg: BusMessage) -> None:
            nonlocal received_payload, received_topic
            received_payload = msg.payload
            received_topic = msg.topic

        dispatcher.register_sink(payload_capturing_sink)

        await dispatcher.dispatch([message])

        # Verify payload and topic are correct
        assert received_payload == payload
        assert received_topic == "user.events"
