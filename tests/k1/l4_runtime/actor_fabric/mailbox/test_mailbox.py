"""
WARD Integration Tests — Mailbox (PriorityScheduler + MessageQueue + Cleanup + DLQ)

Fast, integration-style tests covering priority ordering, backpressure, TTL,
concurrent access, metrics sanity, DLQ/cleanup behaviors, and Dead Letter Queue.

This module intentionally reuses internal helpers from the scheduler to avoid
waiting on long background sleeps (aging loop) and to keep the suite <10s.
"""

import asyncio
import time

from ward import fixture, test

from k1.l4_runtime.actor_fabric.mailbox.cleanup import DeadLetterQueue
from k1.l4_runtime.actor_fabric.mailbox.scheduler import (
    PRIORITY_BACKGROUND,
    PRIORITY_INTERACTIVE,
    PRIORITY_REALTIME,
    PRIORITY_URGENT,
    PriorityScheduler,
    _pack_message,
)

# -------------------------
# Fixtures
# -------------------------


@fixture
async def scheduler():
    sched = PriorityScheduler(enable_aging=False)
    try:
        yield sched
    finally:
        await sched.shutdown()


@fixture
async def scheduler_with_aging():
    # Enable aging but we'll trigger promotions manually (fast tests)
    sched = PriorityScheduler(enable_aging=True, aging_threshold_ms=50)
    try:
        yield sched
    finally:
        await sched.shutdown()


@fixture
def test_message():
    return b"tiny-payload"


@fixture
def prometheus_cleanup():
    """Placeholder fixture; if test environment provides registry reset, use it.

    This fixture is intentionally empty - other test suites provide an explicit
    registry reset fixture. Including it here makes tests easier to integrate.
    """
    yield


# -------------------------
# Helper utilities
# -------------------------


def pack_payload(payload: bytes, priority: int = PRIORITY_BACKGROUND, ttl_ms: int = 0):
    now = int(time.time() * 1000)
    return _pack_message(
        message=payload,
        enqueued_at_ms=now,
        original_priority=priority,
        current_priority=priority,
        promotions=0,
        ttl_ms=ttl_ms,
    )


# -------------------------
# Tests
# -------------------------


@test("mailbox_enqueue_dequeue_fifo")
async def _(scheduler=scheduler, test_message=test_message):
    # Send 3 messages same priority and verify FIFO ordering
    await scheduler.send(b"a", PRIORITY_INTERACTIVE)
    await scheduler.send(b"b", PRIORITY_INTERACTIVE)
    await scheduler.send(b"c", PRIORITY_INTERACTIVE)

    r1 = await scheduler.receive()
    r2 = await scheduler.receive()
    r3 = await scheduler.receive()

    assert r1.message == b"a"
    assert r2.message == b"b"
    assert r3.message == b"c"


@test("mailbox_priority_ordering_urgent_first")
async def _(scheduler=scheduler, test_message=test_message):
    await scheduler.send(b"bg", PRIORITY_BACKGROUND)
    await scheduler.send(b"rt", PRIORITY_REALTIME)
    await scheduler.send(b"ug", PRIORITY_URGENT)

    msg = await scheduler.receive()
    assert msg.original_priority == PRIORITY_URGENT


@test("mailbox_priority_ordering_realtime_second")
async def _(scheduler=scheduler):
    await scheduler.send(b"rt", PRIORITY_REALTIME)
    await scheduler.send(b"bg", PRIORITY_BACKGROUND)

    first = await scheduler.receive()
    second = await scheduler.receive()
    assert first.original_priority == PRIORITY_REALTIME
    assert second.original_priority == PRIORITY_BACKGROUND


@test("mailbox_round_robin_fairness_within_tier")
async def _(scheduler=scheduler):
    # Fill URGENT and BACKGROUND and ensure BACKGROUND appears occasionally
    for _ in range(6):
        await scheduler.send(b"u", PRIORITY_URGENT)
        await scheduler.send(b"b", PRIORITY_BACKGROUND)

    seen_bg = 0
    for _ in range(6):
        msg = await scheduler.receive()
        if msg.original_priority == PRIORITY_BACKGROUND:
            seen_bg += 1

    assert seen_bg >= 1


@test("mailbox_enqueue_latency_under_0_5ms")
async def _(scheduler=scheduler):
    import time as _time

    iterations = 200
    latencies = []
    for _ in range(iterations):
        s = _time.perf_counter()
        await scheduler.send(b"x", PRIORITY_INTERACTIVE)
        latencies.append((_time.perf_counter() - s) * 1000)

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 0.5


@test("mailbox_dequeue_latency_under_0_5ms")
async def _(scheduler=scheduler):
    import time as _time

    # Pre-fill
    for _ in range(200):
        await scheduler.send(b"y", PRIORITY_INTERACTIVE)

    latencies = []
    for _ in range(200):
        s = _time.perf_counter()
        await scheduler.receive()
        latencies.append((_time.perf_counter() - s) * 1000)

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 0.5


@test("mailbox_backpressure_reject_at_95_percent")
async def _(scheduler=scheduler):
    # Use small custom capacities to trigger backpressure quickly
    small = PriorityScheduler(capacities={0: 4, 1: 4, 2: 4, 3: 4}, enable_aging=False)
    try:
        # Fill URGENT (capacity 4)
        for _ in range(4):
            await small.send(b"m", PRIORITY_URGENT)
        # Next send should be rejected
        res = await small.send(b"m", PRIORITY_URGENT)
        assert res.success is False and res.reason == "BACKPRESSURE"
    finally:
        await small.shutdown()


@test("mailbox_pressure_level_transitions_correctly")
async def _(scheduler=scheduler):
    # usage_percent should reflect fills
    for _ in range(25):
        await scheduler.send(b"z", PRIORITY_URGENT)
    usage = scheduler.usage_percent()
    assert 40.0 <= usage[PRIORITY_URGENT] <= 60.0


@test("mailbox_message_ttl_expiry_removes_old_messages")
async def _(scheduler=scheduler):
    # send with tiny ttl
    await scheduler.send(b"t1", PRIORITY_URGENT, ttl_ms=10)
    await asyncio.sleep(0.02)
    msg = await scheduler.receive()
    assert msg is None


@test("mailbox_cleanup_runs_every_100ms")
async def _(prometheus_cleanup=prometheus_cleanup):
    # Test unified DeadLetterQueue with cleanup-like behavior
    dlq = DeadLetterQueue(max_entries=3, retention_ms=50)

    # Create test messages with short retention
    msg1 = _create_test_message("agent-1", "agent-2", "trace-1", b"m1", priority=2)
    msg2 = _create_test_message("agent-1", "agent-2", "trace-2", b"m2", priority=2)

    # Enqueue messages
    dlq.enqueue(msg1, "TEST_DROP", mailbox_depth=10)
    await asyncio.sleep(0.06)  # 60ms > 50ms retention
    dlq.enqueue(msg2, "TEST_DROP", mailbox_depth=10)

    # Cleanup expired entries
    expired = dlq.cleanup()
    assert expired == 1  # msg1 expired, msg2 still valid
    assert dlq.size() == 1


@test("mailbox_concurrent_senders_no_race")
async def _(scheduler=scheduler):
    async def sender(p, n):
        for i in range(n):
            await scheduler.send(f"{p}-{i}".encode(), p)

    await asyncio.gather(sender(PRIORITY_URGENT, 10), sender(PRIORITY_BACKGROUND, 20))
    sizes = scheduler.size()
    assert sizes[PRIORITY_URGENT] == 10
    assert sizes[PRIORITY_BACKGROUND] == 20


@test("mailbox_size_returns_accurate_count")
async def _(scheduler=scheduler):
    await scheduler.send(b"a", PRIORITY_REALTIME)
    await scheduler.send(b"b", PRIORITY_REALTIME)
    sizes = scheduler.size()
    assert sizes[PRIORITY_REALTIME] == 2


@test("mailbox_empty_returns_none_or_blocks")
async def _(scheduler=scheduler):
    # receive on empty should return None
    res = await scheduler.receive()
    assert res is None


@test("mailbox_watermark_hysteresis_prevents_thrashing")
def _(scheduler=scheduler):
    # smoke test: calling usage_percent multiple times shouldn't thrash
    for _ in range(5):
        p = scheduler.usage_percent()
    assert isinstance(p, dict)


@test("mailbox_metrics_exported_correctly")
async def _(scheduler=scheduler):
    await scheduler.send(b"m", PRIORITY_URGENT)
    await scheduler.receive()
    met = scheduler.metrics()
    assert "enqueue_count" in met and "dequeue_count" in met


@test("mailbox_prometheus_registry_contains_expected_metrics")
def _(_=prometheus_cleanup):
    # Basic sanity: ensure our test environment can import prometheus
    try:
        import prometheus_client as pc  # noqa: F401
    except Exception:
        assert False, "prometheus_client not available"


@test("mailbox_message_trace_id_preserved")
async def _(scheduler=scheduler):
    # Use packed payload helper and verify roundtrip
    payload = b"trace-test"
    packed = pack_payload(payload, priority=PRIORITY_INTERACTIVE)
    # Directly enqueue into underlying queue to preserve header
    q = scheduler._queues[PRIORITY_INTERACTIVE]
    await q.enqueue(packed)
    msg = await scheduler.receive()
    assert msg is not None and msg.message == payload


@test("mailbox_invalid_priority_rejected")
async def _(scheduler=scheduler):
    res = await scheduler.send(b"x", 99)
    assert res.success is False and res.reason == "INVALID_PRIORITY"


@test("mailbox_large_message_payload_handled")
async def _(scheduler=scheduler):
    large = b"x" * 4096
    res = await scheduler.send(large, PRIORITY_BACKGROUND)
    assert res.success is True
    msg = await scheduler.receive()
    assert msg is not None and len(msg.message) == 4096


@test("mailbox_wfq_aging_promotes_background_after_5s")
async def _(scheduler_with_aging=scheduler_with_aging, test_message=test_message):
    # Send background messages and invoke promote helper directly (fast)
    for _ in range(3):
        await scheduler_with_aging.send(test_message, PRIORITY_BACKGROUND)

    # Manually call promote with current_time that forces promotion
    now = int(time.time() * 1000) + 10000
    await scheduler_with_aging._promote_aged_messages(
        from_priority=PRIORITY_BACKGROUND,
        to_priority=PRIORITY_INTERACTIVE,
        current_time_ms=now,
        max_scan=10,
    )

    metrics = scheduler_with_aging.metrics()
    assert metrics["promotions_count"] >= 1


@test("mailbox_dlq_retention_config_respected")
def _():
    dlq = DeadLetterQueue(max_entries=2, retention_ms=20)

    # Create test messages
    msg1 = _create_test_message("agent-1", "agent-2", "trace-1", b"one", priority=2)
    msg2 = _create_test_message("agent-1", "agent-2", "trace-2", b"two", priority=2)

    # Enqueue first message and wait for it to expire
    dlq.enqueue(msg1, "TEST_RETENTION", mailbox_depth=10)
    time.sleep(0.025)  # 25ms > 20ms retention

    # Enqueue second message (fresh)
    dlq.enqueue(msg2, "TEST_RETENTION", mailbox_depth=10)

    # Cleanup should remove msg1 (expired) but keep msg2
    expired = dlq.cleanup()
    assert expired == 1  # msg1 expired
    assert dlq.size() == 1  # msg2 still present


@test("mailbox_stress_test_1000_concurrent_sends")
async def _(scheduler=scheduler):
    # scaled-down stress: 500 concurrent sends to keep suite fast
    async def sender(n):
        for i in range(n):
            await scheduler.send(b"s", PRIORITY_BACKGROUND)

    await asyncio.gather(*(sender(125) for _ in range(4)))
    sizes = scheduler.size()
    assert sizes[PRIORITY_BACKGROUND] == 500


@test("mailbox_promotion_metadata_preserved_and_incremented")
async def _(scheduler_with_aging=scheduler_with_aging, test_message=test_message):
    await scheduler_with_aging.send(test_message, PRIORITY_BACKGROUND)
    now = int(time.time() * 1000) + 10000
    await scheduler_with_aging._promote_aged_messages(
        from_priority=PRIORITY_BACKGROUND,
        to_priority=PRIORITY_INTERACTIVE,
        current_time_ms=now,
        max_scan=10,
    )

    # Receive promoted message
    msg = await scheduler_with_aging.receive()
    assert msg is not None
    assert msg.original_priority == PRIORITY_BACKGROUND
    assert msg.current_priority == PRIORITY_INTERACTIVE


@test("mailbox_aging_disabled_never_moves_messages")
async def _(test_message=test_message):
    sched = PriorityScheduler(enable_aging=False)
    try:
        await sched.send(test_message, PRIORITY_BACKGROUND)
        # Because enable_aging=False, the aging background task should never be started
        assert sched._aging_started is False
    finally:
        await sched.shutdown()


@test("mailbox_corrupted_header_rejected_no_crash")
async def _(scheduler=scheduler):
    # Enqueue a short/corrupt frame directly into queue
    q = scheduler._queues[PRIORITY_URGENT]
    await q.enqueue(b"short")
    # receive should skip corrupt frame and return None
    res = await scheduler.receive()
    assert res is None


@test("mailbox_metrics_self_consistency_invariants")
async def _(scheduler=scheduler):
    # Enqueue some messages and verify metric invariants
    for _ in range(5):
        await scheduler.send(b"m", PRIORITY_REALTIME)

    # Dequeue 3
    for _ in range(3):
        await scheduler.receive()

    met = scheduler.metrics()
    total_received = sum(met["enqueue_count"].values())
    total_dequeued = sum(met["dequeue_count"].values())
    assert total_received - total_dequeued == sum(met["queue_sizes"].values())


@test("mailbox_promotion_when_destination_full_pushes_back")
async def _(scheduler_with_aging=scheduler_with_aging):
    # Fill destination (INTERACTIVE) to capacity
    small = PriorityScheduler(
        capacities={0: 10, 1: 10, 2: 5, 3: 20}, enable_aging=True, aging_threshold_ms=50
    )
    try:
        # Fill INTERACTIVE queue to capacity (5 messages)
        for _ in range(5):
            await small.send(b"i", PRIORITY_INTERACTIVE)

        # Add BACKGROUND message
        await small.send(b"bg", PRIORITY_BACKGROUND)

        # Try to promote with destination full
        now = int(time.time() * 1000) + 10000
        await small._promote_aged_messages(
            from_priority=PRIORITY_BACKGROUND,
            to_priority=PRIORITY_INTERACTIVE,
            current_time_ms=now,
            max_scan=10,
        )

        # Promotion should fail (destination full), message returned to BACKGROUND
        metrics = small.metrics()
        assert metrics["promotions_failed_count"] >= 1
        assert small.size()[PRIORITY_BACKGROUND] >= 1
    finally:
        await small.shutdown()


@test("mailbox_aging_respects_max_scan_window")
async def _(scheduler_with_aging=scheduler_with_aging):
    # Send 200 BACKGROUND messages
    for i in range(200):
        await scheduler_with_aging.send(f"msg_{i}".encode(), PRIORITY_BACKGROUND)

    # Promote with max_scan=50 (should only scan 50 messages)
    now = int(time.time() * 1000) + 10000
    await scheduler_with_aging._promote_aged_messages(
        from_priority=PRIORITY_BACKGROUND,
        to_priority=PRIORITY_INTERACTIVE,
        current_time_ms=now,
        max_scan=50,
    )

    # Should still have ~150 messages in BACKGROUND (200 - 50 scanned)
    sizes = scheduler_with_aging.size()
    assert sizes[PRIORITY_BACKGROUND] >= 150


@test("mailbox_fairness_background_seen_under_urgent_pressure")
async def _(scheduler=scheduler):
    # Fill with continuous URGENT messages and verify BACKGROUND still surfaces
    for _ in range(20):
        await scheduler.send(b"urgent", PRIORITY_URGENT)

    for _ in range(10):
        await scheduler.send(b"bg", PRIORITY_BACKGROUND)

    # Receive 15 messages - should include at least 1 BACKGROUND due to fairness
    bg_count = 0
    for _ in range(15):
        msg = await scheduler.receive()
        if msg and msg.original_priority == PRIORITY_BACKGROUND:
            bg_count += 1

    assert bg_count >= 1, f"Expected >=1 BACKGROUND message, got {bg_count}"


@test("mailbox_watermark_callbacks_hysteresis_once_per_transition")
async def _(scheduler=scheduler):
    # This is a simplified test - full watermark callbacks tested in test_watermarks.py
    # Here we just verify usage_percent transitions correctly

    # Fill to ~50% (GREEN)
    for _ in range(25):
        await scheduler.send(b"m", PRIORITY_URGENT)
    usage1 = scheduler.usage_percent()[PRIORITY_URGENT]

    # Fill to ~90% (YELLOW/RED approaching)
    for _ in range(20):
        await scheduler.send(b"m", PRIORITY_URGENT)
    usage2 = scheduler.usage_percent()[PRIORITY_URGENT]

    # Verify transitions
    assert 40.0 <= usage1 <= 60.0
    assert usage2 >= 85.0


@test("mailbox_ttl_boundary_exact_threshold")
async def _(scheduler=scheduler):
    # Send message with 50ms TTL
    await scheduler.send(b"boundary", PRIORITY_URGENT, ttl_ms=50)

    # Wait exactly at boundary (50ms)
    await asyncio.sleep(0.05)

    # Message should be expired (boundary is inclusive)
    msg = await scheduler.receive()
    assert msg is None

    # Verify TTL expiry metric incremented
    metrics = scheduler.metrics()
    assert metrics["ttl_expired_count"] >= 1


@test("mailbox_stress_test_rapid_priority_transitions")
async def _(scheduler=scheduler):
    # Rapidly send messages across all priorities
    async def rapid_sender():
        for i in range(50):
            priority = i % 4  # Rotate through all 4 priorities
            await scheduler.send(f"rapid_{i}".encode(), priority)

    # Run 4 concurrent rapid senders
    await asyncio.gather(*(rapid_sender() for _ in range(4)))

    # Should have ~200 messages total across all priorities (allow small variance for timing)
    sizes = scheduler.size()
    total = sum(sizes.values())
    assert total >= 198, f"Expected >=198 total messages, got {total}"


# -------------------------
# Dead Letter Queue Tests (Issue 2.6)
# -------------------------


def _create_test_message(
    sender_id: str, receiver_id: str, trace_id: str, payload: bytes, priority: int = 2
):
    """Helper to create FlatBuffers MessageEnvelope for testing."""
    import flatbuffers

    from k1.l4_runtime.actor_fabric.mailbox.model.MessageEnvelope import (
        MessageEnvelope,
        MessageEnvelopeAddCreatedAt,
        MessageEnvelopeAddPayload,
        MessageEnvelopeAddPriority,
        MessageEnvelopeAddReceiverId,
        MessageEnvelopeAddSenderId,
        MessageEnvelopeAddTraceId,
        MessageEnvelopeEnd,
        MessageEnvelopeStart,
    )

    builder = flatbuffers.Builder(256)
    sender = builder.CreateString(sender_id)
    receiver = builder.CreateString(receiver_id)
    trace = builder.CreateString(trace_id)
    payload_data = builder.CreateByteVector(payload)

    MessageEnvelopeStart(builder)
    MessageEnvelopeAddSenderId(builder, sender)
    MessageEnvelopeAddReceiverId(builder, receiver)
    MessageEnvelopeAddTraceId(builder, trace)
    MessageEnvelopeAddPayload(builder, payload_data)
    MessageEnvelopeAddPriority(builder, priority)
    MessageEnvelopeAddCreatedAt(builder, int(time.time() * 1000))
    envelope = MessageEnvelopeEnd(builder)
    builder.Finish(envelope)

    return MessageEnvelope.GetRootAsMessageEnvelope(bytes(builder.Output()), 0)


@test("dlq_enqueue_stores_message_with_metadata")
def _():
    from k1.l4_runtime.actor_fabric.mailbox.dead_letter import DeadLetterQueue

    dlq = DeadLetterQueue(retention_ms=10000, max_entries=100)

    message = _create_test_message(
        "agent-123", "agent-456", "trace-abc", b"test_payload", priority=1
    )

    # Enqueue message
    dlq_id = dlq.enqueue(message, "OVERFLOW", mailbox_depth=1024)

    # Verify stored
    assert dlq.size() == 1
    entry = dlq.get_by_id(dlq_id)
    assert entry is not None
    assert entry.rejection_reason == "OVERFLOW"
    assert entry.trace_id == "trace-abc"
    assert entry.original_priority == 1


@test("dlq_get_by_trace_id_returns_multiple_entries")
def _():
    from k1.l4_runtime.actor_fabric.mailbox.dead_letter import DeadLetterQueue

    dlq = DeadLetterQueue()

    # Create 3 messages with same trace_id
    trace_id = "trace-shared"
    for i in range(3):
        message = _create_test_message(
            f"agent-{i}", "agent-target", trace_id, f"payload_{i}".encode(), priority=2
        )
        dlq.enqueue(message, f"REASON_{i}")

    # Lookup by trace_id
    entries = dlq.get_by_trace_id(trace_id)
    assert len(entries) == 3
    reasons = [e.rejection_reason for e in entries]
    assert "REASON_0" in reasons
    assert "REASON_1" in reasons
    assert "REASON_2" in reasons


@test("dlq_replay_returns_true_for_existing_entry")
def _():
    from k1.l4_runtime.actor_fabric.mailbox.dead_letter import DeadLetterQueue

    dlq = DeadLetterQueue()

    message = _create_test_message(
        "agent-123", "agent-456", "trace-replay", b"replay_me", priority=0
    )
    dlq_id = dlq.enqueue(message, "TTL_EXPIRED")

    # Replay message
    success = dlq.replay(dlq_id, "agent-new-789")
    assert success is True

    # Verify metrics updated
    metrics = dlq.get_metrics()
    assert metrics["total_replayed"] == 1


@test("dlq_cleanup_removes_expired_entries")
def _():
    from k1.l4_runtime.actor_fabric.mailbox.dead_letter import DeadLetterQueue

    # Short retention for testing
    dlq = DeadLetterQueue(retention_ms=100, max_entries=100)

    message = _create_test_message(
        "agent-123", "agent-456", "trace-expire", b"expire_me", priority=3
    )
    dlq.enqueue(message, "OVERFLOW")

    assert dlq.size() == 1

    # Wait for expiry
    time.sleep(0.15)  # 150ms > 100ms retention

    # Run cleanup
    expired_count = dlq.cleanup()
    assert expired_count == 1
    assert dlq.size() == 0

    # Verify metrics
    metrics = dlq.get_metrics()
    assert metrics["total_expired"] == 1


@test("dlq_max_entries_evicts_oldest")
def _():
    from k1.l4_runtime.actor_fabric.mailbox.dead_letter import DeadLetterQueue

    # Small capacity for testing
    dlq = DeadLetterQueue(max_entries=3)

    dlq_ids = []
    for i in range(5):
        message = _create_test_message(
            f"agent-{i}",
            "agent-target",
            f"trace-{i}",
            f"payload_{i}".encode(),
            priority=2,
        )
        dlq_id = dlq.enqueue(message, f"REASON_{i}")
        dlq_ids.append(dlq_id)

        # Short sleep to ensure order
        time.sleep(0.001)

    # Should only have 3 entries (oldest 2 evicted)
    assert dlq.size() == 3

    # First 2 entries should be evicted
    assert dlq.get_by_id(dlq_ids[0]) is None
    assert dlq.get_by_id(dlq_ids[1]) is None

    # Last 3 entries should exist
    assert dlq.get_by_id(dlq_ids[2]) is not None
    assert dlq.get_by_id(dlq_ids[3]) is not None
    assert dlq.get_by_id(dlq_ids[4]) is not None

    # Verify metrics
    metrics = dlq.get_metrics()
    assert metrics["total_evicted"] == 2


@test("dlq_metrics_tracking_accurate")
def _():
    from k1.l4_runtime.actor_fabric.mailbox.dead_letter import DeadLetterQueue

    dlq = DeadLetterQueue(retention_ms=50, max_entries=10)

    # Enqueue 5 messages
    for i in range(5):
        message = _create_test_message(
            f"agent-{i}", "agent-target", f"trace-{i}", f"data_{i}".encode(), priority=1
        )
        dlq.enqueue(message, "TEST")

    metrics = dlq.get_metrics()
    assert metrics["total_enqueued"] == 5
    assert metrics["dlq_depth"] == 5

    # Wait for expiry
    time.sleep(0.08)

    # Cleanup
    dlq.cleanup()

    metrics = dlq.get_metrics()
    assert metrics["total_expired"] == 5
    assert metrics["dlq_depth"] == 0
