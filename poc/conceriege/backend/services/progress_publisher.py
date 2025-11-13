"""
ProgressPublisher - Progress Event Streaming Service

Manages progress event subscriptions for tasks, allowing consumers (like CLI)
to stream progress updates in real-time.

**Architecture:**
- Uses list of asyncio.Queue per task_id for multiple subscribers
- Each subscriber gets own queue for event buffering
- Publisher broadcasts to all subscriber queues
- Auto-cleanup when task completes

**Usage:**
```python
# Publisher side (agent):
publisher = ProgressPublisher()
publisher.publish(task_id, ProgressEvent(...))

# Subscriber side (CLI):
async for event in publisher.subscribe(task_id):
    print(f"[{event.percent}%] {event.message}")
    if event.milestone == 5:
        break
```

**PoC Philosophy:**
- Simple queue-based pub/sub
- No external dependencies (Redis, etc.)
- In-memory only (sufficient for PoC)
"""

import asyncio
from typing import AsyncGenerator, Dict, List

from backend.models.progress_event import ProgressEvent


class ProgressPublisher:
    """
    Progress event publisher for streaming task progress.

    Manages per-task subscriber queues.
    """

    def __init__(self):
        """Initialize progress publisher."""
        # task_id -> List[asyncio.Queue] mapping
        # Each subscriber gets their own queue
        self._subscriber_queues: Dict[str, List[asyncio.Queue]] = {}

    async def subscribe(self, task_id: str) -> AsyncGenerator[ProgressEvent, None]:
        """
        Subscribe to progress events for a task.

        Can be called BEFORE task starts - will buffer events.
        Each subscriber gets their own queue.

        Args:
            task_id: Task identifier

        Yields:
            ProgressEvent: Progress events as they arrive

        Example:
            ```python
            async for event in publisher.subscribe("task_123"):
                print(f"Progress: {event.percent}%")
                if event.milestone == 5:
                    break
            ```
        """
        # Create new queue for this subscriber
        queue = asyncio.Queue()

        # Add to subscriber list for this task
        if task_id not in self._subscriber_queues:
            self._subscriber_queues[task_id] = []
        self._subscriber_queues[task_id].append(queue)

        try:
            while True:
                # Wait for next event
                event = await queue.get()

                # Check for completion sentinel
                if event is None:
                    break

                yield event

                # Check if this is the final event (milestone 5)
                # Handle both dict events and ProgressEvent objects
                if hasattr(event, "milestone") and event.milestone == 5:
                    break
        finally:
            # Cleanup subscription
            if task_id in self._subscriber_queues:
                if queue in self._subscriber_queues[task_id]:
                    self._subscriber_queues[task_id].remove(queue)

                # If last subscriber, clean up task entry
                if len(self._subscriber_queues[task_id]) == 0:
                    del self._subscriber_queues[task_id]

    def publish(self, task_id: str, event: ProgressEvent) -> None:
        """
        Publish a progress event to all subscribers.

        Broadcasts to all subscriber queues for this task.

        Args:
            task_id: Task identifier
            event: Progress event to publish

        Example:
            ```python
            event = ProgressEvent(
                task_id="task_123",
                milestone=1,
                percent=20,
                message="Starting analysis..."
            )
            publisher.publish("task_123", event)
            ```
        """
        # Get all subscriber queues for this task
        if task_id not in self._subscriber_queues:
            # No subscribers yet, create empty list
            self._subscriber_queues[task_id] = []

        # Broadcast event to all subscribers
        for queue in self._subscriber_queues[task_id]:
            queue.put_nowait(event)

        # If this is the final event, send completion sentinel
        # Handle both dict events and ProgressEvent objects
        if hasattr(event, "milestone") and event.milestone == 5:
            # Send None to signal completion
            for queue in self._subscriber_queues[task_id]:
                queue.put_nowait(None)

    async def emit_event(self, task_id_or_event, event=None) -> None:
        """
        Emit a progress event (async alias for publish).

        This method matches the interface expected by concierge_v2.py.

        Args:
            task_id_or_event: Either a task_id string or an event dict (for backward compatibility)
            event: Progress event to emit (optional, for new style calls)

        Example:
            ```python
            # New style (task_id + event)
            await publisher.emit_event("task_123", event)

            # Old style (dict only) - used by concierge_v2.py
            await publisher.emit_event({
                "type": "background_analysis_started",
                "specialist_type": "nutritionist"
            })
            ```
        """
        # Handle backward compatibility: if task_id_or_event is a dict, broadcast to all active sessions
        if isinstance(task_id_or_event, dict):
            # Old style call with just a dict - broadcast to ALL active subscribers
            # This allows real-time events to reach all connected clients
            for task_id in list(self._subscriber_queues.keys()):
                for queue in self._subscriber_queues[task_id]:
                    try:
                        queue.put_nowait(task_id_or_event)
                    except asyncio.QueueFull:
                        # Skip if queue is full (shouldn't happen with unbounded Queue)
                        pass
            return

        # New style call with task_id and event
        if event:
            self.publish(task_id_or_event, event)

    def unsubscribe(self, task_id: str) -> None:
        """
        Manually unsubscribe all subscribers from task progress.

        Usually not needed (auto-cleanup in subscribe), but provided
        for explicit cleanup scenarios.

        Args:
            task_id: Task identifier
        """
        if task_id in self._subscriber_queues:
            # Send completion sentinel to all subscribers
            for queue in self._subscriber_queues[task_id]:
                queue.put_nowait(None)
            del self._subscriber_queues[task_id]

    def get_active_tasks(self) -> list[str]:
        """
        Get list of active task IDs.

        Returns:
            List of task IDs with active subscriptions
        """
        return list(self._subscriber_queues.keys())

    def get_subscriber_count(self, task_id: str) -> int:
        """
        Get number of active subscribers for a task.

        Args:
            task_id: Task identifier

        Returns:
            Number of active subscribers (0 if none)
        """
        if task_id not in self._subscriber_queues:
            return 0
        return len(self._subscriber_queues[task_id])
        return len(self._subscriber_queues[task_id])
