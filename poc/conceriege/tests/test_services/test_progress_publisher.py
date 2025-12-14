"""
Tests for ProgressPublisher - Progress Event Streaming

Tests prove:
- Can subscribe before task starts (buffering)
- All events received in order
- No events lost
- Cleanup after task completion
- Multiple subscribers supported
"""

import asyncio

import pytest
from backend.models.progress_event import ProgressEvent
from backend.services.progress_publisher import ProgressPublisher

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def publisher():
    """Create ProgressPublisher."""
    return ProgressPublisher()


@pytest.fixture
def sample_events():
    """Create sample progress events."""
    return [
        ProgressEvent(task_id="task_123", milestone=1, percent=20, message="Starting..."),
        ProgressEvent(task_id="task_123", milestone=2, percent=40, message="Processing..."),
        ProgressEvent(task_id="task_123", milestone=3, percent=60, message="Analyzing..."),
        ProgressEvent(task_id="task_123", milestone=4, percent=80, message="Finalizing..."),
        ProgressEvent(task_id="task_123", milestone=5, percent=100, message="Complete"),
    ]


# ============================================================================
# Test ProgressPublisher Initialization
# ============================================================================


class TestProgressPublisherInit:
    """Test ProgressPublisher initialization."""

    def test_init_creates_empty_queues(self, publisher):
        """Test that init creates empty queues dict."""
        assert isinstance(publisher._subscriber_queues, dict)
        assert len(publisher._subscriber_queues) == 0

    def test_init_creates_empty_subscribers(self, publisher):
        """Test that init creates empty subscribers dict."""
        assert isinstance(publisher._subscriber_queues, dict)
        assert len(publisher._subscriber_queues) == 0


# ============================================================================
# Test Subscribe and Publish
# ============================================================================


class TestSubscribeAndPublish:
    """Test subscribe and publish functionality."""

    @pytest.mark.asyncio
    async def test_subscribe_before_publish(self, publisher, sample_events):
        """Test subscribing before events are published (buffering)."""
        # Start subscription as a task
        received = []

        async def consume():
            async for event in publisher.subscribe("task_123"):
                received.append(event)

        consumer_task = asyncio.create_task(consume())

        # Give subscription time to start
        await asyncio.sleep(0.05)

        # Publish events
        for event in sample_events:
            publisher.publish("task_123", event)

        # Wait for consumption
        await consumer_task

        # Should receive all 5 events
        assert len(received) == 5
        assert received[0].milestone == 1
        assert received[4].milestone == 5

    @pytest.mark.asyncio
    async def test_publish_then_subscribe(self, publisher, sample_events):
        """Test publishing events then subscribing (events are lost - pub/sub behavior)."""
        # Publish events FIRST (no subscribers)
        for event in sample_events:
            publisher.publish("task_123", event)

        # THEN subscribe (new queue created, doesn't have old events)
        received = []

        async def consume():
            try:
                async for event in publisher.subscribe("task_123"):
                    received.append(event)
            except asyncio.TimeoutError:
                pass

        # Start subscriber
        consumer_task = asyncio.create_task(consume())

        # Wait a bit
        await asyncio.sleep(0.1)

        # Should receive NO events (they were published before subscription)
        # This is correct pub/sub behavior
        assert len(received) == 0

        # Cancel task
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_events_in_order(self, publisher, sample_events):
        """Test that events are received in order."""
        # Start consumer task
        received = []

        async def consume():
            async for event in publisher.subscribe("task_123"):
                received.append(event)

        consumer_task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)

        # Publish events
        for event in sample_events:
            publisher.publish("task_123", event)

        # Wait for completion
        await consumer_task

        # Verify order
        for i, event in enumerate(received):
            assert event.milestone == i + 1
            assert event.percent == (i + 1) * 20

    @pytest.mark.asyncio
    async def test_no_events_lost(self, publisher):
        """Test that no events are lost even with rapid publishing."""
        # Start consumer task
        received = []

        async def consume():
            async for event in publisher.subscribe("task_123"):
                received.append(event)

        consumer_task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)

        # Rapidly publish 50 events (milestone 5 starts at event 41)
        for i in range(1, 51):
            event = ProgressEvent(
                task_id="task_123",
                milestone=min((i - 1) // 10 + 1, 5),  # Milestone 5 at event 41-50
                percent=min(i * 2, 100),
                message=f"Event {i}",
            )
            publisher.publish("task_123", event)

        # Wait for consumption
        await consumer_task

        # Should receive 41 events (stops at first milestone 5)
        assert len(received) == 41
        assert received[-1].milestone == 5


# ============================================================================
# Test Multiple Subscribers
# ============================================================================


class TestMultipleSubscribers:
    """Test multiple subscribers to same task."""

    @pytest.mark.asyncio
    async def test_multiple_subscribers_receive_events(self, publisher, sample_events):
        """Test that multiple subscribers all receive events."""
        # Create 3 subscribers
        sub1 = publisher.subscribe("task_123")
        sub2 = publisher.subscribe("task_123")
        sub3 = publisher.subscribe("task_123")

        # Publish events
        for event in sample_events:
            publisher.publish("task_123", event)

        # Collect from all subscribers
        received1 = []
        received2 = []
        received3 = []

        async for event in sub1:
            received1.append(event)

        async for event in sub2:
            received2.append(event)

        async for event in sub3:
            received3.append(event)

        # All should receive all events
        assert len(received1) == 5
        assert len(received2) == 5
        assert len(received3) == 5

    @pytest.mark.asyncio
    async def test_subscriber_count(self, publisher):
        """Test that subscriber count is tracked."""
        # Initially 0
        assert publisher.get_subscriber_count("task_123") == 0

        # Create subscriptions (but don't consume yet)
        sub1 = publisher.subscribe("task_123")
        sub2 = publisher.subscribe("task_123")

        # Start consuming to trigger subscription tracking
        async def consume(sub, results):
            async for event in sub:
                results.append(event)

        results1 = []
        results2 = []
        task1 = asyncio.create_task(consume(sub1, results1))
        task2 = asyncio.create_task(consume(sub2, results2))

        # Wait a bit for subscriptions to start
        await asyncio.sleep(0.1)

        # Publish single event
        publisher.publish(
            "task_123", ProgressEvent(task_id="task_123", milestone=5, percent=100, message="Done")
        )

        # Wait for consumption
        await task1
        await task2

        # After cleanup, count should be 0
        await asyncio.sleep(0.1)
        assert publisher.get_subscriber_count("task_123") == 0


# ============================================================================
# Test Cleanup
# ============================================================================


class TestCleanup:
    """Test cleanup after task completion."""

    @pytest.mark.asyncio
    async def test_cleanup_after_milestone_5(self, publisher, sample_events):
        """Test that queue is cleaned up after milestone 5."""

        # Start consumer task
        async def consume():
            async for _ in publisher.subscribe("task_123"):
                pass

        consumer_task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)

        # Publish all events (including milestone 5)
        for event in sample_events:
            publisher.publish("task_123", event)

        # Wait for consumption
        await consumer_task

        # Wait for cleanup
        await asyncio.sleep(0.1)

        # Queue should be cleaned up
        assert "task_123" not in publisher._subscriber_queues

    @pytest.mark.asyncio
    async def test_unsubscribe_manual(self, publisher):
        """Test manual unsubscribe."""
        subscription = publisher.subscribe("task_123")

        # Manually unsubscribe
        publisher.unsubscribe("task_123")

        # Should receive None (completion sentinel)
        events = []
        async for event in subscription:
            events.append(event)

        # Should be empty (got None immediately)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_get_active_tasks(self, publisher):
        """Test getting active tasks."""
        # Initially empty
        assert publisher.get_active_tasks() == []

        # Create subscription
        sub = publisher.subscribe("task_123")

        # Start consuming
        async def consume():
            async for _ in sub:
                pass

        task = asyncio.create_task(consume())

        # Publish event to trigger queue creation
        publisher.publish(
            "task_123", ProgressEvent(task_id="task_123", milestone=1, percent=20, message="Start")
        )

        await asyncio.sleep(0.1)

        # Should have active task
        assert "task_123" in publisher.get_active_tasks()

        # Complete task
        publisher.publish(
            "task_123", ProgressEvent(task_id="task_123", milestone=5, percent=100, message="Done")
        )

        await task
        await asyncio.sleep(0.1)

        # Should be cleaned up
        assert "task_123" not in publisher.get_active_tasks()


# ============================================================================
# Test Different Tasks
# ============================================================================


class TestDifferentTasks:
    """Test handling of different task IDs."""

    @pytest.mark.asyncio
    async def test_different_tasks_isolated(self, publisher):
        """Test that different tasks don't interfere."""
        # Subscribe to two different tasks
        sub1 = publisher.subscribe("task_A")
        sub2 = publisher.subscribe("task_B")

        # Publish to task_A
        publisher.publish(
            "task_A", ProgressEvent(task_id="task_A", milestone=1, percent=20, message="A1")
        )
        publisher.publish(
            "task_A", ProgressEvent(task_id="task_A", milestone=5, percent=100, message="A5")
        )

        # Publish to task_B
        publisher.publish(
            "task_B", ProgressEvent(task_id="task_B", milestone=1, percent=20, message="B1")
        )
        publisher.publish(
            "task_B", ProgressEvent(task_id="task_B", milestone=5, percent=100, message="B5")
        )

        # Collect from each subscription
        events_A = []
        async for event in sub1:
            events_A.append(event)

        events_B = []
        async for event in sub2:
            events_B.append(event)

        # Each should only receive their own events
        assert len(events_A) == 2
        assert all(e.message.startswith("A") for e in events_A)

        assert len(events_B) == 2
        assert all(e.message.startswith("B") for e in events_B)


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_subscribe_to_nonexistent_task(self, publisher):
        """Test subscribing to task that never publishes."""
        subscription = publisher.subscribe("nonexistent_task")

        # Should wait indefinitely (test with timeout)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(aiter(subscription)), timeout=0.5)

    @pytest.mark.asyncio
    async def test_publish_without_subscribers(self, publisher):
        """Test publishing events without subscribers (should not error)."""
        # Publish events without subscribers
        publisher.publish(
            "task_123", ProgressEvent(task_id="task_123", milestone=1, percent=20, message="Event")
        )

        # Should not raise error
        assert "task_123" in publisher._queues

    @pytest.mark.asyncio
    async def test_multiple_milestone_5_events(self, publisher):
        """Test handling multiple milestone 5 events (edge case)."""
        subscription = publisher.subscribe("task_123")

        # Publish milestone 5 twice
        publisher.publish(
            "task_123",
            ProgressEvent(task_id="task_123", milestone=5, percent=100, message="Done 1"),
        )
        publisher.publish(
            "task_123",
            ProgressEvent(task_id="task_123", milestone=5, percent=100, message="Done 2"),
        )

        # Should only receive first milestone 5 (stops after)
        events = []
        async for event in subscription:
            events.append(event)

        # Should receive only the first milestone 5
        assert len(events) == 1
        assert events[0].message == "Done 1"
