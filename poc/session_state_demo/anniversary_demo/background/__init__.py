"""
Background Task System
=======================

Enables two-way concierge operation:
- Background tasks run independently
- Notifications queue for proactive messages
- Graceful interruption of conversation
"""

from poc.session_state_demo.anniversary_demo.background.concierge_loop import (
    ConciergeResponse,
    TwoWayConcierge,
    create_two_way_concierge,
)
from poc.session_state_demo.anniversary_demo.background.notifications import (
    Notification,
    NotificationBatch,
    NotificationPriority,
    NotificationQueue,
    NotificationType,
    get_notification_queue,
    notify,
)
from poc.session_state_demo.anniversary_demo.background.registry import (
    TaskRegistry,
    TaskSummary,
    create_task,
    get_registry,
)
from poc.session_state_demo.anniversary_demo.background.task_queue import (
    BackgroundTask,
    TaskPriority,
    TaskQueue,
    TaskStatus,
    create_task_queue,
)

__all__ = [
    # Task Queue
    "BackgroundTask",
    "TaskQueue",
    "TaskPriority",
    "TaskStatus",
    "create_task_queue",
    # Registry
    "TaskRegistry",
    "TaskSummary",
    "create_task",
    "get_registry",
    # Notifications
    "Notification",
    "NotificationBatch",
    "NotificationPriority",
    "NotificationQueue",
    "NotificationType",
    "get_notification_queue",
    "notify",
    # Two-Way Concierge
    "ConciergeResponse",
    "TwoWayConcierge",
    "create_two_way_concierge",
]
