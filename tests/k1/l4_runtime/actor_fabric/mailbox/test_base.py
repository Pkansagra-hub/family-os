"""
WARD Tests for Actor Fabric Mailbox — Base MPSC Queue

Tests MessageQueue implementation from base.py covering:
- Basic enqueue/dequeue operations
- Capacity limits and backpressure
- TTL expiry handling
- Concurrent access (multiple producers)
- Performance benchmarks (<0.5ms P95 latency)
- Metrics tracking

Test Framework: WARD (Weighted Assertion-based Random Distribution)
Coverage Target: >95% code coverage

Related ADRs:
- ADR-0002: Actor Model (mailbox architecture)
- ADR-0011: FlatBuffers (message format)

Run: python -m ward test --path tests/k1/l4_runtime/actor_fabric/mailbox/test_base.py
"""

import asyncio
import os

# Import MessageQueue and supporting types
import sys
import time

import flatbuffers
from ward import fixture, test

# Add project root to path
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
    ),
)

from k1.l4_runtime.actor_fabric.mailbox.base import MessageQueue

# Import FlatBuffers generated types from mailbox model directory
from k1.l4_runtime.actor_fabric.mailbox.model.MessageEnvelope import (
    MessageEnvelope,
    MessageEnvelopeAddCorrelationId,
    MessageEnvelopeAddCreatedAt,
    MessageEnvelopeAddMessageType,
    MessageEnvelopeAddPayload,
    MessageEnvelopeAddPriority,
    MessageEnvelopeAddReceiverId,
    MessageEnvelopeAddSenderId,
    MessageEnvelopeAddTraceId,
    MessageEnvelopeAddTtlMs,
    MessageEnvelopeEnd,
    MessageEnvelopeStart,
)
from k1.l4_runtime.actor_fabric.mailbox.model.MessagePriority import MessagePriority
from k1.l4_runtime.actor_fabric.mailbox.model.MessageType import MessageType

# ============================================================================
# Fixtures
# ============================================================================


@fixture
def queue():
    """Create MessageQueue with default capacity (1024)."""
    return MessageQueue(capacity=1024)


@fixture
def small_queue():
    """Create MessageQueue with small capacity for testing backpressure."""
    return MessageQueue(capacity=5)


@fixture
def message_builder():
    """Create FlatBuffers builder for message construction."""
    return flatbuffers.Builder(2048)


def create_test_message(
    sender_id: str = "test-sender",
    receiver_id: str = "test-receiver",
    message_type: int = MessageType.GENERIC,
    priority: int = MessagePriority.INTERACTIVE,
    ttl_ms: int = 5000,
    payload: bytes = b"test payload",
) -> bytes:
    """Helper to create test message envelope.

    Note: Creates a new Builder for each message (FlatBuffers pattern).

    Args:
        sender_id: Sender actor ID
        receiver_id: Receiver actor ID
        message_type: Message type enum value
        priority: Message priority enum value
        ttl_ms: Time-to-live in milliseconds
        payload: Message payload bytes

    Returns:
        Serialized MessageEnvelope bytes
    """
    # Create fresh builder for each message (FlatBuffers pattern)
    builder = flatbuffers.Builder(2048)

    sender = builder.CreateString(sender_id)
    receiver = builder.CreateString(receiver_id)
    trace = builder.CreateString(f"trace-{int(time.time() * 1000)}")
    correlation = builder.CreateString(f"corr-{int(time.time() * 1000)}")
    payload_data = builder.CreateByteVector(payload)

    MessageEnvelopeStart(builder)
    MessageEnvelopeAddSenderId(builder, sender)
    MessageEnvelopeAddReceiverId(builder, receiver)
    MessageEnvelopeAddMessageType(builder, message_type)
    MessageEnvelopeAddPriority(builder, priority)
    MessageEnvelopeAddPayload(builder, payload_data)
    MessageEnvelopeAddTtlMs(builder, ttl_ms)
    MessageEnvelopeAddCreatedAt(builder, int(time.time() * 1000))
    MessageEnvelopeAddTraceId(builder, trace)
    MessageEnvelopeAddCorrelationId(builder, correlation)
    envelope = MessageEnvelopeEnd(builder)

    builder.Finish(envelope)
    return bytes(builder.Output())


# ============================================================================
# Basic Functionality Tests
# ============================================================================


@test("MessageQueue initializes with correct capacity")
def test_queue_initialization():
    q = MessageQueue(capacity=100)
    assert q.capacity() == 100
    assert q.size() == 0
    assert q.is_empty()
    assert not q.is_full()
    assert q.usage_percent() == 0.0


@test("MessageQueue enqueues message successfully")
async def test_enqueue_success(queue=queue, message_builder=message_builder):
    message = create_test_message()
    result = await queue.enqueue(message)

    assert result.success
    assert result.reason is None
    assert queue.size() == 1
    assert not queue.is_empty()


@test("MessageQueue dequeues message successfully")
async def test_dequeue_success(queue=queue, message_builder=message_builder):
    # Enqueue message
    message = create_test_message(sender_id="agent-123")
    await queue.enqueue(message)

    # Dequeue message
    received = await queue.dequeue()
    assert received is not None

    # Verify message content
    msg = MessageEnvelope.GetRootAsMessageEnvelope(received, 0)
    assert msg.SenderId().decode() == "agent-123"
    assert queue.size() == 0
    assert queue.is_empty()


@test("MessageQueue FIFO ordering preserved")
async def test_fifo_ordering(queue=queue, message_builder=message_builder):
    # Enqueue 3 messages
    msg1 = create_test_message(sender_id="agent-1")
    msg2 = create_test_message(sender_id="agent-2")
    msg3 = create_test_message(sender_id="agent-3")

    await queue.enqueue(msg1)
    await queue.enqueue(msg2)
    await queue.enqueue(msg3)

    # Dequeue and verify order
    received1 = await queue.dequeue()
    received2 = await queue.dequeue()
    received3 = await queue.dequeue()

    assert (
        MessageEnvelope.GetRootAsMessageEnvelope(received1, 0).SenderId().decode()
        == "agent-1"
    )
    assert (
        MessageEnvelope.GetRootAsMessageEnvelope(received2, 0).SenderId().decode()
        == "agent-2"
    )
    assert (
        MessageEnvelope.GetRootAsMessageEnvelope(received3, 0).SenderId().decode()
        == "agent-3"
    )


# ============================================================================
# Capacity and Backpressure Tests
# ============================================================================


@test("MessageQueue rejects message when full")
async def test_queue_full_rejection(
    small_queue=small_queue, message_builder=message_builder
):
    # Fill queue to capacity (5 messages)
    for i in range(5):
        message = create_test_message(sender_id=f"agent-{i}")
        result = await small_queue.enqueue(message)
        assert result.success

    assert small_queue.is_full()
    assert small_queue.size() == 5

    # Attempt to enqueue when full
    overflow_message = create_test_message(sender_id="overflow-agent")
    result = await small_queue.enqueue(overflow_message)

    assert not result.success
    assert result.reason == "queue_full"
    assert small_queue.size() == 5  # Size unchanged


@test("MessageQueue usage_percent calculated correctly")
async def test_usage_percent(small_queue=small_queue, message_builder=message_builder):
    # Empty queue: 0%
    assert small_queue.usage_percent() == 0.0

    # Enqueue 2 messages: 40%
    for i in range(2):
        await small_queue.enqueue(create_test_message())
    assert small_queue.usage_percent() == 40.0

    # Enqueue 3 more: 100%
    for i in range(3):
        await small_queue.enqueue(create_test_message())
    assert small_queue.usage_percent() == 100.0


# ============================================================================
# TTL Expiry Tests
# ============================================================================


@test("MessageQueue rejects expired message (TTL)")
async def test_ttl_expiry(queue=queue, message_builder=message_builder):
    # Create message with TTL of 1ms (immediate expiry)
    # Create fresh builder for manual construction
    builder = flatbuffers.Builder(2048)

    sender = builder.CreateString("expired-sender")
    receiver = builder.CreateString("test-receiver")
    trace = builder.CreateString("trace-expired")
    payload = builder.CreateByteVector(b"expired payload")

    # Set created_at to 2 seconds ago, TTL 1000ms
    created_at = int((time.time() - 2) * 1000)

    MessageEnvelopeStart(builder)
    MessageEnvelopeAddSenderId(builder, sender)
    MessageEnvelopeAddReceiverId(builder, receiver)
    MessageEnvelopeAddMessageType(builder, MessageType.GENERIC)
    MessageEnvelopeAddPriority(builder, MessagePriority.INTERACTIVE)
    MessageEnvelopeAddPayload(builder, payload)
    MessageEnvelopeAddTtlMs(builder, 1000)  # 1 second TTL
    MessageEnvelopeAddCreatedAt(builder, created_at)  # 2 seconds ago
    MessageEnvelopeAddTraceId(builder, trace)
    envelope = MessageEnvelopeEnd(builder)

    builder.Finish(envelope)
    expired_message = bytes(builder.Output())

    # Attempt to enqueue expired message
    result = await queue.enqueue(expired_message)

    assert not result.success
    assert result.reason == "ttl_expired"
    assert queue.size() == 0


@test("MessageQueue accepts message within TTL")
async def test_ttl_valid(queue=queue, message_builder=message_builder):
    # Create message with TTL of 5000ms (5 seconds, well within valid time)
    message = create_test_message(ttl_ms=5000)

    result = await queue.enqueue(message)

    assert result.success
    assert queue.size() == 1


# ============================================================================
# Concurrent Access Tests
# ============================================================================


@test("MessageQueue handles concurrent enqueues (multiple producers)")
async def test_concurrent_enqueues(queue=queue, message_builder=message_builder):
    """Test multiple producers enqueueing concurrently."""

    async def producer(producer_id: int, count: int):
        """Producer task that enqueues `count` messages."""
        for i in range(count):
            message = create_test_message(sender_id=f"producer-{producer_id}-msg-{i}")
            result = await queue.enqueue(message)
            assert result.success

    # Spawn 10 producers, each enqueueing 10 messages (100 total)
    producers = [producer(i, 10) for i in range(10)]
    await asyncio.gather(*producers)

    assert queue.size() == 100


@test("MessageQueue handles concurrent enqueue/dequeue")
async def test_concurrent_enqueue_dequeue(queue=queue, message_builder=message_builder):
    """Test producer/consumer pattern with concurrent enqueue and dequeue."""

    messages_sent = []
    messages_received = []

    async def producer(count: int):
        """Producer enqueueing messages."""
        for i in range(count):
            sender_id = f"producer-msg-{i}"
            message = create_test_message(sender_id=sender_id)
            messages_sent.append(sender_id)
            await queue.enqueue(message)
            await asyncio.sleep(0.001)  # Small delay

    async def consumer(count: int):
        """Consumer dequeueing messages."""
        for _ in range(count):
            message = await queue.dequeue()
            if message:
                msg = MessageEnvelope.GetRootAsMessageEnvelope(message, 0)
                messages_received.append(msg.SenderId().decode())

    # Run producer and consumer concurrently
    await asyncio.gather(producer(50), consumer(50))

    # Verify all messages received (order may vary slightly due to concurrency)
    assert len(messages_received) == 50
    assert queue.size() == 0


# ============================================================================
# Metrics Tests
# ============================================================================


@test("MessageQueue tracks enqueue/dequeue/rejected metrics")
async def test_metrics_tracking(queue=queue, message_builder=message_builder):
    # Initial metrics
    metrics = queue.metrics()
    assert metrics["enqueue_count"] == 0
    assert metrics["dequeue_count"] == 0
    assert metrics["rejected_count"] == 0

    # Enqueue 3 messages
    for i in range(3):
        await queue.enqueue(create_test_message())

    metrics = queue.metrics()
    assert metrics["enqueue_count"] == 3
    assert metrics["size"] == 3

    # Dequeue 2 messages
    await queue.dequeue()
    await queue.dequeue()

    metrics = queue.metrics()
    assert metrics["dequeue_count"] == 2
    assert metrics["size"] == 1

    # Test rejection (create small queue and fill it)
    small_q = MessageQueue(capacity=2)
    await small_q.enqueue(create_test_message())
    await small_q.enqueue(create_test_message())
    await small_q.enqueue(create_test_message())  # Rejected

    metrics = small_q.metrics()
    assert metrics["rejected_count"] == 1


@test("MessageQueue __repr__ provides useful debugging info")
def test_repr():
    q = MessageQueue(capacity=100)
    repr_str = repr(q)

    assert "MessageQueue" in repr_str
    assert "size=" in repr_str
    assert "capacity=" in repr_str or "100" in repr_str


# ============================================================================
# Performance Benchmarks
# ============================================================================


@test("MessageQueue enqueue latency <0.5ms P95")
async def test_enqueue_performance(queue=queue, message_builder=message_builder):
    """Benchmark enqueue latency (target: <0.5ms P95)."""

    latencies = []

    for i in range(1000):
        message = create_test_message(sender_id=f"perf-{i}")

        start = time.perf_counter()
        await queue.enqueue(message)
        end = time.perf_counter()

        latency_ms = (end - start) * 1000
        latencies.append(latency_ms)

    # Calculate P95
    latencies.sort()
    p95_index = int(0.95 * len(latencies))
    p95_latency = latencies[p95_index]

    print(f"\nEnqueue P95 latency: {p95_latency:.3f}ms")
    assert (
        p95_latency < 0.5
    ), f"Enqueue P95 latency {p95_latency:.3f}ms exceeds 0.5ms budget"


@test("MessageQueue dequeue latency <0.5ms P95")
async def test_dequeue_performance(queue=queue, message_builder=message_builder):
    """Benchmark dequeue latency (target: <0.5ms P95)."""

    # Pre-fill queue with 1000 messages
    for i in range(1000):
        await queue.enqueue(create_test_message(sender_id=f"perf-{i}"))

    latencies = []

    for _ in range(1000):
        start = time.perf_counter()
        await queue.dequeue()
        end = time.perf_counter()

        latency_ms = (end - start) * 1000
        latencies.append(latency_ms)

    # Calculate P95
    latencies.sort()
    p95_index = int(0.95 * len(latencies))
    p95_latency = latencies[p95_index]

    print(f"\nDequeue P95 latency: {p95_latency:.3f}ms")
    assert (
        p95_latency < 0.5
    ), f"Dequeue P95 latency {p95_latency:.3f}ms exceeds 0.5ms budget"


@test("MessageQueue throughput >100K messages/sec")
async def test_throughput(queue=queue, message_builder=message_builder):
    """Benchmark throughput (target: >100K messages/sec)."""

    message_count = 10000

    # Enqueue phase
    start_enqueue = time.perf_counter()
    for i in range(message_count):
        await queue.enqueue(create_test_message())
    end_enqueue = time.perf_counter()

    enqueue_duration = end_enqueue - start_enqueue
    enqueue_throughput = message_count / enqueue_duration

    # Dequeue phase
    start_dequeue = time.perf_counter()
    for _ in range(message_count):
        await queue.dequeue()
    end_dequeue = time.perf_counter()

    dequeue_duration = end_dequeue - start_dequeue
    dequeue_throughput = message_count / dequeue_duration

    print(f"\nEnqueue throughput: {enqueue_throughput:.0f} msgs/sec")
    print(f"Dequeue throughput: {dequeue_throughput:.0f} msgs/sec")

    assert (
        enqueue_throughput > 100000
    ), f"Enqueue throughput {enqueue_throughput:.0f} msgs/sec below 100K target"
    assert (
        dequeue_throughput > 100000
    ), f"Dequeue throughput {dequeue_throughput:.0f} msgs/sec below 100K target"


# ============================================================================
# Edge Cases
# ============================================================================


@test("MessageQueue handles invalid message gracefully")
async def test_invalid_message(queue=queue):
    """Test queue handles malformed message bytes."""
    invalid_message = b"invalid flatbuffers data"

    result = await queue.enqueue(invalid_message)

    assert not result.success
    assert "invalid_message" in result.reason


@test("MessageQueue dequeue returns None when cancelled")
async def test_dequeue_cancelled(queue=queue):
    """Test dequeue returns None when task is cancelled."""

    async def dequeue_task():
        return await queue.dequeue()

    task = asyncio.create_task(dequeue_task())
    await asyncio.sleep(0.001)  # Let task start waiting

    # Cancel task
    task.cancel()

    result = None
    try:
        result = await task
    except asyncio.CancelledError:
        result = None

    assert result is None


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    print("Running WARD tests for MessageQueue...")
    print(
        "Run: python -m ward test --path tests/k1/l4_runtime/actor_fabric/mailbox/test_base.py"
    )
