"""
Two-Way Concierge Loop
=======================

Wraps the ConciergeFSM to enable concurrent operation:
- User conversation continues normally
- Background tasks run independently
- Notifications delivered at appropriate moments
- Graceful interruption when urgent

This is the main integration point between:
- ConciergeFSM (conversation handling)
- TaskQueue (background processing)
- NotificationQueue (proactive messages)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from poc.session_state_demo.anniversary_demo.background.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationType,
    get_notification_queue,
)
from poc.session_state_demo.anniversary_demo.background.registry import TaskRegistry, get_registry
from poc.session_state_demo.anniversary_demo.background.task_queue import (
    BackgroundTask,
    TaskPriority,
    TaskQueue,
    create_task_queue,
)

if TYPE_CHECKING:
    from poc.session_state_demo.concierge.fsm import ConciergeFSM
    from poc.session_state_demo.concierge.states import TurnResult


@dataclass
class ConciergeResponse:
    """
    Response from the two-way concierge.

    May include both conversation response and background notifications.
    """

    # Main conversation response
    response: str
    needs_clarification: bool = False
    clarification_question: Optional[str] = None

    # Background notifications to deliver
    notifications: List[Notification] = field(default_factory=list)
    has_notifications: bool = False

    # Proactive suggestion (from background analysis)
    proactive_message: Optional[str] = None

    # Metadata
    turn_result: Optional["TurnResult"] = None
    background_tasks_active: int = 0


class TwoWayConcierge:
    """
    Two-way concierge that handles both user conversation and background tasks.

    Features:
    - Wraps ConciergeFSM for conversation handling
    - Manages TaskQueue for background processing
    - Delivers notifications at appropriate moments
    - Supports graceful interruption for urgent alerts

    Usage:
        concierge = TwoWayConcierge(fsm=my_fsm)
        await concierge.start()

        # Normal conversation
        response = await concierge.process_input("Plan a trip")

        # Check for background notifications
        if response.has_notifications:
            for notif in response.notifications:
                print(f"Alert: {notif.message}")

        # Start a background monitor
        task_id = await concierge.start_monitor(
            "weather",
            location="Sonoma",
            check_interval=60
        )
    """

    def __init__(
        self,
        fsm: "ConciergeFSM",
        task_queue: Optional[TaskQueue] = None,
        notification_queue: Optional[NotificationQueue] = None,
        task_registry: Optional[TaskRegistry] = None,
        on_notification: Optional[Callable[[Notification], None]] = None,
    ):
        self._fsm = fsm
        self._task_queue = task_queue or create_task_queue()
        self._notification_queue = notification_queue or get_notification_queue()
        self._task_registry = task_registry or get_registry()

        # Connect task queue to registry
        self._task_registry.set_queue(self._task_queue)

        # Set up callbacks
        self._on_notification = on_notification
        self._task_queue.on_notification = self._handle_task_notification
        self._notification_queue.on_urgent = self._handle_urgent_notification

        # State
        self._running = False
        self._pending_interrupt: Optional[Notification] = None

    async def start(self) -> None:
        """Start the two-way concierge (task queue and notifications)."""
        if self._running:
            return

        self._running = True
        await self._task_queue.start()
        await self._notification_queue.start()

    async def stop(self) -> None:
        """Stop all background processing."""
        self._running = False
        await self._task_queue.stop()
        await self._notification_queue.stop()

    async def process_input(self, user_input: str) -> ConciergeResponse:
        """
        Process user input through the concierge.

        This handles:
        1. Marking conversation as active
        2. Processing through FSM
        3. Collecting any pending notifications
        4. Checking for proactive suggestions
        """
        # Mark conversation as active (pauses non-urgent notifications)
        self._notification_queue.set_conversation_active(True)

        try:
            # Process through FSM
            turn_result = await self._fsm.process_input(user_input)

            # Build response
            response = ConciergeResponse(
                response=turn_result.response or "",
                needs_clarification=turn_result.needs_clarification,
                clarification_question=turn_result.clarification_question,
                turn_result=turn_result,
                background_tasks_active=len(self._task_registry.get_active()),
            )

            # Check for pending high-priority notifications
            high_priority = self._notification_queue.get_next_high_priority()
            if high_priority:
                notif = self._notification_queue.pop_for_delivery()
                if notif:
                    response.notifications.append(notif)
                    response.has_notifications = True

            # Check for pending interrupt (urgent notification during processing)
            if self._pending_interrupt:
                response.notifications.insert(0, self._pending_interrupt)
                response.has_notifications = True
                response.proactive_message = self._pending_interrupt.message
                self._pending_interrupt = None

            return response

        finally:
            # Mark conversation as inactive
            self._notification_queue.set_conversation_active(False)

    async def get_pending_notifications(self) -> List[Notification]:
        """Get all pending notifications without processing input."""
        notifications = []

        while True:
            notif = self._notification_queue.pop_for_delivery()
            if notif is None:
                break
            notifications.append(notif)

        return notifications

    # =========================================================================
    # BACKGROUND TASK MANAGEMENT
    # =========================================================================

    async def start_monitor(
        self,
        monitor_type: str,
        check_interval: float = 60.0,
        max_runs: Optional[int] = None,
        **params: Any,
    ) -> str:
        """
        Start a background monitor.

        Args:
            monitor_type: Type of monitor (weather, price, etc.)
            check_interval: Seconds between checks
            max_runs: Maximum number of checks (None = unlimited)
            **params: Monitor-specific parameters

        Returns:
            task_id for tracking
        """
        handler = self._get_monitor_handler(monitor_type)

        task = BackgroundTask.create(
            name=f"{monitor_type}_monitor",
            task_type=f"monitor_{monitor_type}",
            handler=handler,
            params=params,
            priority=TaskPriority.NORMAL,
            is_recurring=True,
            interval_seconds=check_interval,
            max_runs=max_runs,
            metadata={"monitor_type": monitor_type},
        )

        return await self._task_registry.register_and_submit(task)

    async def stop_monitor(self, task_id: str) -> bool:
        """Stop a running monitor."""
        return await self._task_registry.cancel(task_id)

    async def schedule_task(
        self,
        name: str,
        handler: Callable,
        params: Optional[Dict[str, Any]] = None,
        delay_seconds: float = 0,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> str:
        """
        Schedule a one-time background task.

        Args:
            name: Task name
            handler: Async function to execute
            params: Parameters to pass to handler
            delay_seconds: Delay before execution
            priority: Task priority

        Returns:
            task_id for tracking
        """
        # Wrap handler with delay if needed
        if delay_seconds > 0:
            original_handler = handler

            async def delayed_handler(**kwargs: Any) -> Any:
                await asyncio.sleep(delay_seconds)
                return await original_handler(**kwargs)

            handler = delayed_handler

        task = BackgroundTask.create(
            name=name,
            task_type="scheduled",
            handler=handler,
            params=params,
            priority=priority,
        )

        return await self._task_registry.register_and_submit(task)

    async def schedule_notification(
        self,
        message: str,
        delay_seconds: float,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        notification_type: NotificationType = NotificationType.REMINDER,
    ) -> str:
        """Schedule a notification to be delivered after a delay."""

        async def send_notification() -> None:
            await asyncio.sleep(delay_seconds)
            self._notification_queue.create_and_enqueue(
                message=message,
                priority=priority,
                notification_type=notification_type,
            )

        task = BackgroundTask.create(
            name="scheduled_notification",
            task_type="notification",
            handler=send_notification,
            priority=TaskPriority.NORMAL,
        )

        return await self._task_registry.register_and_submit(task)

    def get_active_tasks(self) -> List[BackgroundTask]:
        """Get all currently active background tasks."""
        return self._task_registry.get_active()

    def get_task_summary(self) -> Dict[str, Any]:
        """Get summary of background task state."""
        summary = self._task_registry.get_summary()
        return {
            "total": summary.total_tasks,
            "active": summary.pending + summary.running,
            "completed": summary.completed,
            "failed": summary.failed,
            "by_type": summary.by_type,
            "pending_notifications": self._notification_queue.get_pending_count(),
        }

    # =========================================================================
    # MONITOR HANDLERS
    # =========================================================================

    def _get_monitor_handler(self, monitor_type: str) -> Callable:
        """Get the handler function for a monitor type."""
        handlers = {
            "weather": self._weather_monitor_handler,
            "price": self._price_monitor_handler,
            "checkin": self._checkin_monitor_handler,
        }

        if monitor_type not in handlers:
            raise ValueError(f"Unknown monitor type: {monitor_type}")

        return handlers[monitor_type]

    async def _weather_monitor_handler(
        self,
        location: str,
        dates: Optional[List[str]] = None,
        alert_conditions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Handler for weather monitoring.

        In demo mode, this simulates weather changes.
        In production, would call real weather API.
        """
        # Simulated weather check
        import random

        conditions = ["sunny", "cloudy", "rain", "storm"]
        current = random.choice(conditions)

        # Check alert conditions
        alert_conditions = alert_conditions or ["rain", "storm"]
        if current in alert_conditions:
            self._notification_queue.create_and_enqueue(
                message=f"Weather alert for {location}: {current} expected. You may want to adjust plans.",
                priority=NotificationPriority.HIGH,
                notification_type=NotificationType.ALERT,
                data={"location": location, "condition": current},
                suggested_action="suggest_indoor_activities",
            )

        return {
            "location": location,
            "condition": current,
            "checked_at": datetime.now().isoformat(),
        }

    async def _price_monitor_handler(
        self,
        item_type: str,
        item_id: str,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Handler for price monitoring."""
        # Simulated price check
        import random

        current_price = random.uniform(50, 200)

        if threshold and current_price < threshold:
            self._notification_queue.create_and_enqueue(
                message=f"Price drop alert! {item_type} is now ${current_price:.2f} (under ${threshold})",
                priority=NotificationPriority.HIGH,
                notification_type=NotificationType.ALERT,
            )

        return {"item_type": item_type, "price": current_price}

    async def _checkin_monitor_handler(
        self,
        target: str,
        message: str,
    ) -> Dict[str, Any]:
        """Handler for scheduled check-in."""
        # Send check-in notification
        self._notification_queue.create_and_enqueue(
            message=f"Check-in reminder: {message}",
            priority=NotificationPriority.NORMAL,
            notification_type=NotificationType.REMINDER,
            data={"target": target},
        )

        return {"target": target, "sent_at": datetime.now().isoformat()}

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def _handle_task_notification(self, message: str, data: Dict[str, Any]) -> None:
        """Handle notification from task queue."""
        self._notification_queue.create_and_enqueue(
            message=message,
            notification_type=NotificationType.BACKGROUND_RESULT,
            priority=NotificationPriority.NORMAL,
            data=data,
        )

    def _handle_urgent_notification(self, notification: Notification) -> None:
        """Handle urgent notification that may need to interrupt."""
        self._pending_interrupt = notification

        if self._on_notification:
            self._on_notification(notification)


def create_two_way_concierge(
    fsm: "ConciergeFSM",
    on_notification: Optional[Callable[[Notification], None]] = None,
) -> TwoWayConcierge:
    """Create a configured two-way concierge."""
    return TwoWayConcierge(
        fsm=fsm,
        on_notification=on_notification,
    )
