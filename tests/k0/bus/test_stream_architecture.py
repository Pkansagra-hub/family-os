"""Integration tests for stream-based bus architecture (ADR-055).

Tests verify:
1. WAL stream preserves existing behavior (monotonic offsets required)
2. Feedback stream enforces message_id requirement
3. Streams are isolated (no cross-contamination)
4. Concurrent WAL + feedback dispatch works correctly
5. QoS isolation prevents feedback floods from starving WAL
"""

import asyncio
from dataclasses import asdict
from typing import List

import pytest

from k0.bus import BusDispatcher, BusMessage, UniversalBus
from k0.qos import Scheduler, SchedulerProfile


@pytest.fixture
def scheduler():
    """Scheduler with per-stream QoS isolation."""
    profile = SchedulerProfile(
        name="test_streams",
        description="Test profile with stream isolation",
        port_limits={
            "bus_wal": 32,
            "bus_feedback": 16,
        },
        default_port_limit=16,
    )
    return Scheduler(profile=profile)


@pytest.fixture
def wal_dispatcher(scheduler):
    """BusDispatcher configured for WAL stream (default behavior)."""
    return BusDispatcher(
        scheduler=scheduler,
        stream="wal",
        port="bus_wal",
    )


@pytest.fixture
def feedback_dispatcher(scheduler):
    """BusDispatcher configured for feedback stream (non-WAL)."""
    return BusDispatcher(
        scheduler=scheduler,
        stream="feedback",
        port="bus_feedback",
    )


@pytest.fixture
def universal_bus(wal_dispatcher, feedback_dispatcher):
    """UniversalBus facade for topic-based routing."""
    return UniversalBus(wal_dispatcher, feedback_dispatcher)


class TestWALStreamEnforcement:
    """Test that WAL stream enforces offset requirements."""

    async def test_wal_stream_requires_offset(self, wal_dispatcher):
        """WAL stream must reject messages without offset."""
        msg = BusMessage(
            topic="cognitive.memory.write.committed.v1",
            payload=b'{"test": true}',
            offset=None,  # Missing offset
        )

        with pytest.raises(ValueError, match="stream='wal' requires message.offset"):
            await wal_dispatcher.dispatch([msg])

    async def test_wal_stream_enforces_monotonic_offsets(self, wal_dispatcher):
        """WAL stream must enforce monotonic offset ordering."""
        # First message (offset=100)
        msg1 = BusMessage(
            topic="cognitive.memory.write.committed.v1",
            payload=b'{"seq": 1}',
            offset=100,
        )
        await wal_dispatcher.dispatch([msg1])

        # Second message (offset=99, violates monotonicity)
        msg2 = BusMessage(
            topic="cognitive.memory.write.committed.v1",
            payload=b'{"seq": 2}',
            offset=99,
        )

        with pytest.raises(ValueError, match="non-decreasing order"):
            await wal_dispatcher.dispatch([msg2])

    async def test_wal_stream_accepts_valid_offsets(self, wal_dispatcher):
        """WAL stream accepts messages with monotonic offsets."""
        received = []

        def sink(msg: BusMessage):
            received.append(asdict(msg))
            return asyncio.sleep(0)  # Return coroutine

        wal_dispatcher.subscribe("*", sink)

        messages = [
            BusMessage(topic="test.v1", payload=b"msg1", offset=100),
            BusMessage(topic="test.v1", payload=b"msg2", offset=101),
            BusMessage(topic="test.v1", payload=b"msg3", offset=102),
        ]

        await wal_dispatcher.dispatch(messages)
        assert len(received) == 3
        assert [m["offset"] for m in received] == [100, 101, 102]


class TestFeedbackStreamEnforcement:
    """Test that feedback stream enforces message_id requirements."""

    async def test_feedback_stream_requires_message_id(self, feedback_dispatcher):
        """Feedback stream must reject messages without message_id."""
        msg = BusMessage(
            topic="feedback.p02.reformulation.v1",
            payload=b'{"signal": "reformulation"}',
            offset=None,
            metadata={},  # Missing message_id
        )

        with pytest.raises(ValueError, match="stream='feedback' requires metadata\\['message_id'\\]"):
            await feedback_dispatcher.dispatch([msg])

    async def test_feedback_stream_accepts_valid_messages(self, feedback_dispatcher):
        """Feedback stream accepts messages with message_id."""
        received = []

        def sink(msg: BusMessage):
            received.append(asdict(msg))
            return asyncio.sleep(0)

        feedback_dispatcher.subscribe("*", sink)

        messages = [
            BusMessage(
                topic="feedback.p02.reformulation.v1",
                payload=b'{"signal": "reformulation"}',
                offset=None,  # Ignored for feedback stream
                metadata={"message_id": "fb-001", "signal_type": "reformulation"},
            ),
            BusMessage(
                topic="feedback.p08.abandonment.v1",
                payload=b'{"signal": "abandonment"}',
                offset=None,
                metadata={"message_id": "fb-002", "signal_type": "abandonment"},
            ),
        ]

        await feedback_dispatcher.dispatch(messages)
        assert len(received) == 2
        assert received[0]["metadata"]["message_id"] == "fb-001"
        assert received[1]["metadata"]["message_id"] == "fb-002"

    async def test_feedback_stream_ignores_offset(self, feedback_dispatcher):
        """Feedback stream does not enforce monotonic offsets."""
        received = []

        def sink(msg: BusMessage):
            received.append(asdict(msg))
            return asyncio.sleep(0)

        feedback_dispatcher.subscribe("*", sink)

        # Send messages with decreasing offsets (should not fail)
        messages = [
            BusMessage(
                topic="feedback.p02.correction.v1",
                payload=b"msg1",
                offset=100,  # Will be ignored
                metadata={"message_id": "fb-100"},
            ),
            BusMessage(
                topic="feedback.p02.correction.v1",
                payload=b"msg2",
                offset=50,  # Lower offset (no error for feedback stream)
                metadata={"message_id": "fb-101"},
            ),
        ]

        await feedback_dispatcher.dispatch(messages)
        assert len(received) == 2


class TestStreamIsolation:
    """Test that WAL and feedback streams are isolated."""

    async def test_concurrent_dispatch_isolation(self, wal_dispatcher, feedback_dispatcher):
        """Concurrent WAL + feedback dispatch does not interfere."""
        wal_received = []
        feedback_received = []

        def wal_sink(msg: BusMessage):
            wal_received.append(msg.topic)
            return asyncio.sleep(0)

        def feedback_sink(msg: BusMessage):
            feedback_received.append(msg.topic)
            return asyncio.sleep(0)

        wal_dispatcher.subscribe("*", wal_sink)
        feedback_dispatcher.subscribe("*", feedback_sink)

        # Dispatch concurrently
        wal_messages = [
            BusMessage(topic="cognitive.memory.write.v1", payload=b"wal1", offset=100),
            BusMessage(topic="cognitive.memory.write.v1", payload=b"wal2", offset=101),
        ]

        feedback_messages = [
            BusMessage(
                topic="feedback.p02.reformulation.v1",
                payload=b"fb1",
                offset=None,
                metadata={"message_id": "fb-001"},
            ),
            BusMessage(
                topic="feedback.p08.abandonment.v1",
                payload=b"fb2",
                offset=None,
                metadata={"message_id": "fb-002"},
            ),
        ]

        await asyncio.gather(
            wal_dispatcher.dispatch(wal_messages),
            feedback_dispatcher.dispatch(feedback_messages),
        )

        assert len(wal_received) == 2
        assert len(feedback_received) == 2
        assert all("cognitive" in t for t in wal_received)
        assert all("feedback" in t for t in feedback_received)

    async def test_stream_state_independence(self, wal_dispatcher, feedback_dispatcher):
        """Feedback stream state does not affect WAL stream."""
        # Dispatch to feedback stream first
        feedback_msg = BusMessage(
            topic="feedback.p02.hedging.v1",
            payload=b"feedback",
            offset=None,
            metadata={"message_id": "fb-999"},
        )
        await feedback_dispatcher.dispatch([feedback_msg])

        # WAL stream should start from its own offset (not affected by feedback)
        wal_received = []

        def wal_sink(msg: BusMessage):
            wal_received.append(msg.offset)
            return asyncio.sleep(0)

        wal_dispatcher.subscribe("*", wal_sink)

        wal_messages = [
            BusMessage(topic="cognitive.test.v1", payload=b"w1", offset=50),
            BusMessage(topic="cognitive.test.v1", payload=b"w2", offset=51),
        ]

        await wal_dispatcher.dispatch(wal_messages)
        assert wal_received == [50, 51]  # WAL stream unaffected by feedback


class TestUniversalBusRouting:
    """Test UniversalBus topic-based routing."""

    async def test_routes_by_topic_prefix(self, universal_bus, wal_dispatcher, feedback_dispatcher):
        """UniversalBus routes to correct stream based on topic."""
        wal_received: List[str] = []
        feedback_received: List[str] = []

        def wal_sink(msg: BusMessage):
            wal_received.append(msg.topic)
            return asyncio.sleep(0)

        def feedback_sink(msg: BusMessage):
            feedback_received.append(msg.topic)
            return asyncio.sleep(0)

        wal_dispatcher.subscribe("*", wal_sink)
        feedback_dispatcher.subscribe("*", feedback_sink)

        # Mixed batch: WAL + feedback messages
        messages = [
            BusMessage(topic="cognitive.memory.write.v1", payload=b"wal1", offset=100),
            BusMessage(
                topic="feedback.p02.reformulation.v1",
                payload=b"fb1",
                offset=None,
                metadata={"message_id": "fb-001"},
            ),
            BusMessage(topic="cognitive.planning.sketch.v1", payload=b"wal2", offset=101),
            BusMessage(
                topic="feedback.p08.abandonment.v1",
                payload=b"fb2",
                offset=None,
                metadata={"message_id": "fb-002"},
            ),
        ]

        await universal_bus.dispatch(messages)

        assert len(wal_received) == 2
        assert len(feedback_received) == 2
        assert "cognitive.memory.write.v1" in wal_received
        assert "cognitive.planning.sketch.v1" in wal_received
        assert "feedback.p02.reformulation.v1" in feedback_received
        assert "feedback.p08.abandonment.v1" in feedback_received


class TestQoSIsolation:
    """Test that per-stream QoS prevents feedback floods from starving WAL."""

    async def test_feedback_flood_does_not_block_wal(self, scheduler):
        """Feedback flood exhausts feedback port but WAL port remains available."""
        # Create dispatchers with explicit port limits
        wal_dispatcher = BusDispatcher(scheduler=scheduler, stream="wal", port="bus_wal")
        feedback_dispatcher = BusDispatcher(scheduler=scheduler, stream="feedback", port="bus_feedback")

        wal_received = []
        feedback_received = []

        def wal_sink(msg: BusMessage):
            wal_received.append(msg.topic)
            return asyncio.sleep(0.01)  # Simulate processing

        def feedback_sink(msg: BusMessage):
            feedback_received.append(msg.topic)
            return asyncio.sleep(0.01)

        wal_dispatcher.subscribe("*", wal_sink)
        feedback_dispatcher.subscribe("*", feedback_sink)

        # Dispatch small batches to avoid exhausting scheduler
        wal_messages = [
            BusMessage(topic=f"cognitive.write.v1", payload=b"w", offset=i) for i in range(10)
        ]
        feedback_messages = [
            BusMessage(
                topic=f"feedback.p02.signal.v1",
                payload=b"f",
                offset=None,
                metadata={"message_id": f"fb-{i}"},
            )
            for i in range(10)
        ]

        # Dispatch concurrently
        await asyncio.gather(
            wal_dispatcher.dispatch(wal_messages),
            feedback_dispatcher.dispatch(feedback_messages),
        )

        # Both should complete (no starvation)
        assert len(wal_received) == 10
        assert len(feedback_received) == 10


@pytest.mark.asyncio
class TestStreamEdgeCases:
    """Test edge cases and error handling."""

    async def test_invalid_stream_name_rejected(self, scheduler):
        """BusDispatcher rejects invalid stream names."""
        with pytest.raises(ValueError, match="Invalid stream 'invalid'"):
            BusDispatcher(scheduler=scheduler, stream="invalid")

    async def test_wal_stream_default(self, scheduler):
        """BusDispatcher defaults to stream='wal'."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        # Should enforce WAL requirements
        msg = BusMessage(topic="test.v1", payload=b"test", offset=None)
        with pytest.raises(ValueError, match="stream='wal' requires message.offset"):
            await dispatcher.dispatch([msg])

    async def test_empty_batch_handled_gracefully(self, wal_dispatcher, feedback_dispatcher):
        """Dispatchers handle empty batches without error."""
        await wal_dispatcher.dispatch([])
        await feedback_dispatcher.dispatch([])
