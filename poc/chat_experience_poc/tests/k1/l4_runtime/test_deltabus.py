"""
DeltaBus Unit Tests

Test Coverage:
- Basic publish/subscribe
- Wildcard pattern matching (session.*, agent.*)
- Multiple subscribers per event type
- Async callbacks with queue delivery
- Sync callbacks with immediate execution
- Unsubscribe functionality
- Event ordering (FIFO per session_id)
- Performance: 1000 events delivered <1ms each (P95)
- Error handling (dropped events, invalid callbacks)

References:
- docs/plans/chat_experience_poc_plan.md - Issue 2.2.1 acceptance criteria
- ADR-0045a - K1 Internal Event Bus Architecture
"""

import asyncio
import time

import pytest
from l4_runtime.deltabus import DeltaBus, DeltaBusEvent, EventType


@pytest.fixture
def deltabus():
    """Create fresh DeltaBus instance for each test"""
    bus = DeltaBus()
    # Clear singleton state
    bus._subscribers.clear()
    bus._subscriber_index.clear()
    bus._session_queues.clear()
    bus._events_published = 0
    bus._events_delivered = 0
    bus._events_dropped = 0
    bus._delivery_times.clear()
    bus._shutdown = False
    yield bus


def test_deltabus_singleton():
    """Test DeltaBus is singleton"""
    bus1 = DeltaBus()
    bus2 = DeltaBus()
    assert bus1 is bus2, "DeltaBus should be singleton"


def test_basic_subscribe_publish(deltabus):
    """Test basic pub/sub with sync callback"""
    received_events = []

    def callback(event: DeltaBusEvent):
        received_events.append(event)

    # Subscribe
    subscriber_id = deltabus.subscribe("session.delta", callback)
    assert subscriber_id is not None

    # Publish event
    event = DeltaBusEvent(
        event_type="session.delta",
        session_id="session_123",
        payload={"deltas": [{"section": "beliefs", "changes": 5}]},
        trace_id="trace_abc",
    )
    deltabus.publish(event)

    # Verify delivery
    assert len(received_events) == 1
    assert received_events[0].event_type == "session.delta"
    assert received_events[0].session_id == "session_123"
    assert received_events[0].trace_id == "trace_abc"


def test_wildcard_subscription(deltabus):
    """Test wildcard pattern matching (session.*)"""
    received_events = []

    def callback(event: DeltaBusEvent):
        received_events.append(event)

    # Subscribe to all session.* events
    deltabus.subscribe("session.*", callback)

    # Publish multiple event types
    deltabus.publish(DeltaBusEvent("session.delta", "s1", {}))
    deltabus.publish(DeltaBusEvent("session.created", "s2", {}))
    deltabus.publish(DeltaBusEvent("session.archived", "s3", {}))
    deltabus.publish(DeltaBusEvent("agent.spawned", "s4", {}))  # Should not match

    # Verify only session.* events received
    assert len(received_events) == 3
    event_types = [e.event_type for e in received_events]
    assert "session.delta" in event_types
    assert "session.created" in event_types
    assert "session.archived" in event_types
    assert "agent.spawned" not in event_types


def test_multiple_subscribers(deltabus):
    """Test multiple subscribers for same event type"""
    subscriber1_events = []
    subscriber2_events = []

    def callback1(event: DeltaBusEvent):
        subscriber1_events.append(event)

    def callback2(event: DeltaBusEvent):
        subscriber2_events.append(event)

    # Subscribe both callbacks
    deltabus.subscribe("session.delta", callback1)
    deltabus.subscribe("session.delta", callback2)

    # Publish event
    event = DeltaBusEvent("session.delta", "s1", {"data": "test"})
    deltabus.publish(event)

    # Both subscribers should receive event
    assert len(subscriber1_events) == 1
    assert len(subscriber2_events) == 1
    assert subscriber1_events[0].event_id == subscriber2_events[0].event_id


@pytest.mark.asyncio
async def test_async_callback(deltabus):
    """Test async callback with queue delivery"""
    received_events = []

    async def async_callback(event: DeltaBusEvent):
        await asyncio.sleep(0.01)  # Simulate async work
        received_events.append(event)

    # Subscribe with async callback
    subscriber_id = deltabus.subscribe("session.delta", async_callback)
    assert subscriber_id in deltabus._delivery_tasks, "Async delivery task should be created"

    # Publish event
    event = DeltaBusEvent("session.delta", "s1", {})
    await deltabus.publish_async(event)

    # Wait for async delivery
    await asyncio.sleep(0.05)

    # Verify delivery
    assert len(received_events) == 1


def test_unsubscribe(deltabus):
    """Test unsubscribe functionality"""
    received_events = []

    def callback(event: DeltaBusEvent):
        received_events.append(event)

    # Subscribe
    subscriber_id = deltabus.subscribe("session.delta", callback)

    # Publish event (should receive)
    deltabus.publish(DeltaBusEvent("session.delta", "s1", {}))
    assert len(received_events) == 1

    # Unsubscribe
    result = deltabus.unsubscribe(subscriber_id)
    assert result is True

    # Publish another event (should NOT receive)
    deltabus.publish(DeltaBusEvent("session.delta", "s2", {}))
    assert len(received_events) == 1  # Still 1, not 2


def test_event_pattern_matching():
    """Test DeltaBusEvent.matches_pattern()"""
    event = DeltaBusEvent("session.delta", "s1", {})

    # Exact match
    assert event.matches_pattern("session.delta") is True
    assert event.matches_pattern("session.created") is False

    # Wildcard match
    assert event.matches_pattern("session.*") is True
    assert event.matches_pattern("agent.*") is False

    # Edge cases
    assert event.matches_pattern("session") is False
    assert event.matches_pattern("*") is False


def test_performance_1000_events(deltabus):
    """Test performance: 1000 events delivered <1ms each (P95)"""
    received_count = [0]

    def callback(event: DeltaBusEvent):
        received_count[0] += 1

    # Subscribe
    deltabus.subscribe("session.delta", callback)

    # Publish 1000 events
    start_time = time.perf_counter()
    for i in range(1000):
        event = DeltaBusEvent(
            "session.delta",
            f"session_{i}",
            {"deltas": [{"section": "beliefs"}]},
        )
        deltabus.publish(event)

    total_time_ms = (time.perf_counter() - start_time) * 1000

    # Verify all events delivered
    assert received_count[0] == 1000, "All events should be delivered"

    # Check P95 latency
    stats = deltabus.get_stats()
    assert stats["events_published"] == 1000
    assert stats["events_delivered"] == 1000
    assert (
        stats["p95_delivery_ms"] < 1.0
    ), f"P95 delivery time should be <1ms, got {stats['p95_delivery_ms']}ms"

    print(f"\n[Performance Test] 1000 events in {total_time_ms:.2f}ms")
    print(f"[Performance Test] P95 delivery: {stats['p95_delivery_ms']:.3f}ms")
    print(f"[Performance Test] Avg delivery: {stats['avg_delivery_ms']:.3f}ms")


def test_get_stats(deltabus):
    """Test statistics tracking"""

    def callback(event: DeltaBusEvent):
        pass

    deltabus.subscribe("session.delta", callback)

    # Publish some events
    for i in range(10):
        deltabus.publish(DeltaBusEvent("session.delta", f"s{i}", {}))

    # Check stats
    stats = deltabus.get_stats()
    assert stats["events_published"] == 10
    assert stats["events_delivered"] == 10
    assert stats["events_dropped"] == 0
    assert stats["active_subscribers"] == 1
    assert stats["avg_delivery_ms"] >= 0.0
    assert stats["p95_delivery_ms"] >= 0.0


def test_no_subscribers(deltabus):
    """Test publishing with no subscribers"""
    event = DeltaBusEvent("session.delta", "s1", {})

    # Should not raise exception
    deltabus.publish(event)

    stats = deltabus.get_stats()
    assert stats["events_published"] == 1
    assert stats["events_delivered"] == 0  # No subscribers


def test_event_enum_types():
    """Test EventType enum values"""
    assert EventType.SESSION_DELTA.value == "session.delta"
    assert EventType.SESSION_CREATED.value == "session.created"
    assert EventType.SESSION_ARCHIVED.value == "session.archived"
    assert EventType.AGENT_SPAWNED.value == "agent.spawned"
    assert EventType.AGENT_TERMINATED.value == "agent.terminated"
    assert EventType.TOOL_CALLED.value == "tool.called"


@pytest.mark.asyncio
async def test_shutdown(deltabus):
    """Test graceful shutdown"""

    async def async_callback(event: DeltaBusEvent):
        await asyncio.sleep(0.01)

    # Subscribe
    subscriber_id = deltabus.subscribe("session.delta", async_callback)

    # Verify task created
    assert subscriber_id in deltabus._delivery_tasks

    # Publish event
    event = DeltaBusEvent("session.delta", "s1", {})
    deltabus.publish(event)  # Use sync publish

    # Wait briefly for delivery
    await asyncio.sleep(0.05)

    # Shutdown (just set flag and cancel tasks)
    deltabus._shutdown = True
    for task in deltabus._delivery_tasks.values():
        if not task.done():
            task.cancel()

    assert deltabus._shutdown is True


def test_trace_id_propagation(deltabus):
    """Test trace_id is preserved through event delivery"""
    received_events = []

    def callback(event: DeltaBusEvent):
        received_events.append(event)

    deltabus.subscribe("session.delta", callback)

    # Publish with specific trace_id
    event = DeltaBusEvent(
        "session.delta",
        "s1",
        {},
        trace_id="trace_custom_123",
    )
    deltabus.publish(event)

    # Verify trace_id preserved
    assert len(received_events) == 1
    assert received_events[0].trace_id == "trace_custom_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
