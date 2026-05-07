"""
Test Two-Way Concierge
=======================

Tests concurrent operation of the two-way concierge:
- Background tasks run while user chats
- Notifications delivered at appropriate times
- Weather monitor runs independently
- Graceful interruption works
"""

import asyncio

import pytest

from poc.session_state_demo.anniversary_demo.background import (
    BackgroundTask,
    Notification,
    NotificationPriority,
    TaskPriority,
    TaskRegistry,
    create_task_queue,
)


class TestTaskQueue:
    """Test the async task queue."""

    @pytest.mark.asyncio
    async def test_task_execution(self):
        """Tasks should execute and return results."""
        queue = create_task_queue()
        await queue.start()

        async def my_task(value: int) -> int:
            return value * 2

        task = BackgroundTask.create(
            name="double",
            task_type="math",
            handler=my_task,
            params={"value": 21},
        )

        task_id = await queue.submit(task)
        await asyncio.sleep(0.2)

        result_task = queue.get_task(task_id)
        assert result_task is not None
        assert result_task.result == 42

        await queue.stop()

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Higher priority tasks should execute first."""
        execution_order = []

        async def track_task(name: str) -> None:
            execution_order.append(name)

        queue = create_task_queue(max_concurrent=1)
        await queue.start()

        # Submit low priority first
        low = BackgroundTask.create(
            name="low",
            task_type="test",
            handler=track_task,
            params={"name": "low"},
            priority=TaskPriority.LOW,
        )

        high = BackgroundTask.create(
            name="high",
            task_type="test",
            handler=track_task,
            params={"name": "high"},
            priority=TaskPriority.HIGH,
        )

        await queue.submit(low)
        await queue.submit(high)

        await asyncio.sleep(0.3)
        await queue.stop()

        # High priority should execute first
        assert execution_order[0] == "high"

    @pytest.mark.asyncio
    async def test_task_cancellation(self):
        """Tasks should be cancellable."""
        queue = create_task_queue()
        await queue.start()

        async def slow_task() -> str:
            await asyncio.sleep(10)
            return "done"

        task = BackgroundTask.create(
            name="slow",
            task_type="test",
            handler=slow_task,
        )

        task_id = await queue.submit(task)
        await asyncio.sleep(0.1)

        cancelled = await queue.cancel(task_id)
        assert cancelled is True

        result_task = queue.get_task(task_id)
        assert result_task is not None
        # Status should be CANCELLED
        from poc.session_state_demo.anniversary_demo.background import TaskStatus

        assert result_task.status == TaskStatus.CANCELLED

        await queue.stop()

    @pytest.mark.asyncio
    async def test_recurring_task(self):
        """Recurring tasks should run multiple times."""
        run_count = []

        async def counting_task() -> None:
            run_count.append(1)

        queue = create_task_queue()
        await queue.start()

        task = BackgroundTask.create(
            name="counter",
            task_type="test",
            handler=counting_task,
            is_recurring=True,
            interval_seconds=0.1,
            max_runs=3,
        )

        await queue.submit(task)
        await asyncio.sleep(0.5)

        await queue.stop()

        assert len(run_count) >= 2  # Should have run at least twice


class TestNotificationQueue:
    """Test the notification queue."""

    @pytest.mark.asyncio
    async def test_notification_delivery(self):
        """Notifications should be deliverable."""
        from poc.session_state_demo.anniversary_demo.background import NotificationQueue

        delivered = []
        queue = NotificationQueue(on_deliver=lambda n: delivered.append(n))
        await queue.start()

        queue.create_and_enqueue("Test message", priority=NotificationPriority.HIGH)

        # Pop and deliver
        notif = queue.pop_for_delivery()
        assert notif is not None
        assert notif.message == "Test message"

        await queue.stop()

    @pytest.mark.asyncio
    async def test_urgent_interruption(self):
        """Urgent notifications should trigger interrupt callback."""
        from poc.session_state_demo.anniversary_demo.background import NotificationQueue

        urgent_received = []
        queue = NotificationQueue(on_urgent=lambda n: urgent_received.append(n))
        await queue.start()

        queue.set_conversation_active(True)

        urgent = Notification.create(
            message="URGENT!",
            priority=NotificationPriority.URGENT,
        )
        queue.enqueue(urgent)

        assert len(urgent_received) == 1
        assert urgent_received[0].message == "URGENT!"

        await queue.stop()

    @pytest.mark.asyncio
    async def test_priority_pop_order(self):
        """Higher priority notifications should pop first."""
        from poc.session_state_demo.anniversary_demo.background import NotificationQueue

        queue = NotificationQueue()
        await queue.start()

        queue.create_and_enqueue("Low", priority=NotificationPriority.LOW)
        queue.create_and_enqueue("Normal", priority=NotificationPriority.NORMAL)
        queue.create_and_enqueue("High", priority=NotificationPriority.HIGH)

        first = queue.pop_for_delivery()
        assert first is not None
        assert first.message == "High"

        await queue.stop()


class TestTaskRegistry:
    """Test the task registry."""

    @pytest.mark.asyncio
    async def test_register_and_lookup(self):
        """Tasks should be registerable and retrievable."""
        registry = TaskRegistry()

        async def dummy() -> None:
            pass

        task = BackgroundTask.create(
            name="test",
            task_type="demo",
            handler=dummy,
        )

        task_id = registry.register(task)
        retrieved = registry.get(task_id)

        assert retrieved is not None
        assert retrieved.name == "test"

    @pytest.mark.asyncio
    async def test_get_by_type(self):
        """Should retrieve tasks by type."""
        registry = TaskRegistry()

        async def dummy() -> None:
            pass

        task1 = BackgroundTask.create(name="t1", task_type="weather", handler=dummy)
        task2 = BackgroundTask.create(name="t2", task_type="weather", handler=dummy)
        task3 = BackgroundTask.create(name="t3", task_type="price", handler=dummy)

        registry.register(task1)
        registry.register(task2)
        registry.register(task3)

        weather_tasks = registry.get_by_type("weather")
        assert len(weather_tasks) == 2

        price_tasks = registry.get_by_type("price")
        assert len(price_tasks) == 1

    @pytest.mark.asyncio
    async def test_summary(self):
        """Summary should reflect task states."""
        registry = TaskRegistry()

        async def dummy() -> None:
            pass

        task = BackgroundTask.create(name="t", task_type="test", handler=dummy)
        registry.register(task)

        summary = registry.get_summary()
        assert summary.total_tasks == 1
        assert summary.pending == 1


class TestConcurrentOperation:
    """Test that background tasks run while conversation continues."""

    @pytest.mark.asyncio
    async def test_task_runs_during_sleep(self):
        """Background task should complete while main coroutine sleeps."""
        completed = []

        async def background_work() -> None:
            await asyncio.sleep(0.1)
            completed.append("done")

        queue = create_task_queue()
        await queue.start()

        task = BackgroundTask.create(
            name="bg",
            task_type="work",
            handler=background_work,
        )

        await queue.submit(task)

        # Simulate conversation processing
        await asyncio.sleep(0.3)

        assert len(completed) == 1

        await queue.stop()

    @pytest.mark.asyncio
    async def test_notification_arrives_during_conversation(self):
        """Notification should be available after conversation turn."""
        from poc.session_state_demo.anniversary_demo.background import NotificationQueue

        queue = NotificationQueue()
        await queue.start()

        # Start background task that will send notification
        async def notify_later():
            await asyncio.sleep(0.1)
            queue.create_and_enqueue(
                "Background update!",
                priority=NotificationPriority.HIGH,
            )

        asyncio.create_task(notify_later())

        # Simulate conversation
        queue.set_conversation_active(True)
        await asyncio.sleep(0.2)
        queue.set_conversation_active(False)

        # Check for notification
        pending = queue.get_pending_count()
        assert pending >= 1

        await queue.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
    pytest.main([__file__, "-v"])
