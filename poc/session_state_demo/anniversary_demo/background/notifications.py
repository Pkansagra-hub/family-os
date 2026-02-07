"""
Notification System
====================

Handles notifications from background tasks to the user.
Enables proactive messages and graceful interruption of conversation flow.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional


class NotificationType(Enum):
    """Type of notification."""

    INFO = auto()  # Informational update
    ALERT = auto()  # Important alert requiring attention
    ACTION = auto()  # Suggests an action
    REMINDER = auto()  # Scheduled reminder
    BACKGROUND_RESULT = auto()  # Result from background task


class NotificationPriority(Enum):
    """Priority for notification delivery."""

    LOW = 1  # Can wait, batch with others
    NORMAL = 2  # Show at next opportunity
    HIGH = 3  # Show soon
    URGENT = 4  # Interrupt immediately


@dataclass
class Notification:
    """
    A notification to be delivered to the user.

    Can be queued for later delivery or delivered immediately
    depending on priority and conversation state.
    """

    notification_id: str
    message: str
    notification_type: NotificationType
    priority: NotificationPriority = NotificationPriority.NORMAL
    source_task_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    delivered_at: Optional[datetime] = None
    acknowledged: bool = False
    suggested_action: Optional[str] = None
    action_params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        source_task_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        suggested_action: Optional[str] = None,
        action_params: Optional[Dict[str, Any]] = None,
    ) -> "Notification":
        """Factory method to create notification."""
        import uuid

        return cls(
            notification_id=str(uuid.uuid4())[:8],
            message=message,
            notification_type=notification_type,
            priority=priority,
            source_task_id=source_task_id,
            data=data or {},
            suggested_action=suggested_action,
            action_params=action_params or {},
        )

    @property
    def is_pending(self) -> bool:
        """Check if notification hasn't been delivered."""
        return self.delivered_at is None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "notification_id": self.notification_id,
            "message": self.message,
            "type": self.notification_type.name,
            "priority": self.priority.name,
            "source_task_id": self.source_task_id,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "acknowledged": self.acknowledged,
            "suggested_action": self.suggested_action,
        }


@dataclass
class NotificationBatch:
    """A batch of notifications to deliver together."""

    notifications: List[Notification]
    combined_message: str


class NotificationQueue:
    """
    Queue for proactive notifications.

    Features:
    - Priority-based delivery
    - Batching of low-priority notifications
    - Graceful interruption handling
    - Delivery callbacks
    """

    def __init__(
        self,
        on_deliver: Optional[Callable[[Notification], None]] = None,
        on_urgent: Optional[Callable[[Notification], None]] = None,
        max_queue_size: int = 100,
        batch_delay_seconds: float = 2.0,
    ):
        self.on_deliver = on_deliver
        self.on_urgent = on_urgent
        self.max_queue_size = max_queue_size
        self.batch_delay_seconds = batch_delay_seconds

        self._queue: deque[Notification] = deque(maxlen=max_queue_size)
        self._delivered: List[Notification] = []
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

        # Conversation state for graceful interruption
        self._conversation_active = False
        self._pending_urgent: Optional[Notification] = None

    async def start(self) -> None:
        """Start the notification queue worker."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Stop the notification queue."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    def enqueue(self, notification: Notification) -> str:
        """
        Add notification to queue.

        Returns notification_id.
        """
        # Urgent notifications bypass queue
        if notification.priority == NotificationPriority.URGENT:
            self._handle_urgent(notification)
            return notification.notification_id

        self._queue.append(notification)
        return notification.notification_id

    def create_and_enqueue(
        self,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        source_task_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        suggested_action: Optional[str] = None,
    ) -> str:
        """Create a notification and add to queue."""
        notification = Notification.create(
            message=message,
            notification_type=notification_type,
            priority=priority,
            source_task_id=source_task_id,
            data=data,
            suggested_action=suggested_action,
        )
        return self.enqueue(notification)

    def set_conversation_active(self, active: bool) -> None:
        """Set whether user is actively in conversation."""
        self._conversation_active = active

        # If conversation ended and we have pending urgent, deliver it
        if not active and self._pending_urgent:
            self._deliver(self._pending_urgent)
            self._pending_urgent = None

    def get_pending_count(self) -> int:
        """Get number of pending notifications."""
        return len(self._queue)

    def get_pending(self) -> List[Notification]:
        """Get all pending notifications."""
        return list(self._queue)

    def get_next_high_priority(self) -> Optional[Notification]:
        """Get next high priority notification if any."""
        for notif in self._queue:
            if notif.priority.value >= NotificationPriority.HIGH.value:
                return notif
        return None

    def pop_for_delivery(self) -> Optional[Notification]:
        """Pop the next notification to deliver (during conversation pause)."""
        if not self._queue:
            return None

        # Find highest priority
        highest_idx = 0
        highest_priority = self._queue[0].priority.value

        for i, notif in enumerate(self._queue):
            if notif.priority.value > highest_priority:
                highest_priority = notif.priority.value
                highest_idx = i

        # Remove and return
        notif = self._queue[highest_idx]
        del self._queue[highest_idx]
        return notif

    def batch_low_priority(self) -> Optional[NotificationBatch]:
        """Batch all low priority notifications into one."""
        low_priority = [n for n in self._queue if n.priority == NotificationPriority.LOW]

        if len(low_priority) < 2:
            return None

        # Remove from queue
        self._queue = deque(
            [n for n in self._queue if n.priority != NotificationPriority.LOW],
            maxlen=self.max_queue_size,
        )

        # Combine messages
        combined = "Quick updates:\n" + "\n".join(f"- {n.message}" for n in low_priority)

        return NotificationBatch(
            notifications=low_priority,
            combined_message=combined,
        )

    def _handle_urgent(self, notification: Notification) -> None:
        """Handle urgent notification."""
        if self._conversation_active:
            # Store for delivery at next pause
            self._pending_urgent = notification
            # Also call callback for potential interrupt
            if self.on_urgent:
                self.on_urgent(notification)
        else:
            self._deliver(notification)

    def _deliver(self, notification: Notification) -> None:
        """Mark notification as delivered and call callback."""
        notification.delivered_at = datetime.now()
        self._delivered.append(notification)

        if self.on_deliver:
            self.on_deliver(notification)

    async def _worker(self) -> None:
        """Background worker for batching and delivery."""
        while self._running:
            try:
                await asyncio.sleep(self.batch_delay_seconds)

                # Batch low priority
                batch = self.batch_low_priority()
                if batch and self.on_deliver:
                    # Deliver as single combined notification
                    combined = Notification.create(
                        message=batch.combined_message,
                        notification_type=NotificationType.INFO,
                        priority=NotificationPriority.LOW,
                    )
                    self._deliver(combined)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Notification worker error: {e}")


# Singleton queue
_notification_queue: Optional[NotificationQueue] = None


def get_notification_queue() -> NotificationQueue:
    """Get the global notification queue."""
    global _notification_queue
    if _notification_queue is None:
        _notification_queue = NotificationQueue()
    return _notification_queue


def notify(
    message: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    notification_type: NotificationType = NotificationType.INFO,
    source_task_id: Optional[str] = None,
    suggested_action: Optional[str] = None,
) -> str:
    """Convenience function to send a notification."""
    queue = get_notification_queue()
    return queue.create_and_enqueue(
        message=message,
        notification_type=notification_type,
        priority=priority,
        source_task_id=source_task_id,
        suggested_action=suggested_action,
    )
