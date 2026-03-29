"""
Test M10 Integration: TwoWayConcierge + Background Tasks
=========================================================

Tests that the runner properly integrates:
- TwoWayConcierge initialization and lifecycle
- Background monitor starting via tool calls
- Notification delivery during turn processing
"""

from poc.session_state_demo.anniversary_demo.background import (
    ConciergeResponse,
    Notification,
    NotificationPriority,
    NotificationType,
    TwoWayConcierge,
    create_two_way_concierge,
)


class TestM10Imports:
    """Test that M10 components can be imported."""

    def test_imports_from_background_module(self):
        """All required types should be importable."""
        assert ConciergeResponse is not None
        assert Notification is not None
        assert NotificationPriority is not None
        assert NotificationType is not None
        assert TwoWayConcierge is not None
        assert create_two_way_concierge is not None

    def test_concierge_response_structure(self):
        """ConciergeResponse should have expected fields."""
        response = ConciergeResponse(
            response="Hello",
            needs_clarification=False,
        )
        assert response.response == "Hello"
        assert response.needs_clarification is False
        assert response.notifications == []
        assert response.has_notifications is False
        assert response.background_tasks_active == 0

    def test_notification_priorities(self):
        """Notification priorities should be defined."""
        assert NotificationPriority.LOW
        assert NotificationPriority.NORMAL
        assert NotificationPriority.HIGH
        assert NotificationPriority.URGENT

    def test_notification_types(self):
        """Notification types should be defined."""
        assert NotificationType.INFO
        assert NotificationType.ALERT
        assert NotificationType.REMINDER


class TestRunnerImports:
    """Test that runner can import M10 components."""

    def test_runner_imports(self):
        """Runner should be importable with M10 components."""
        # This will fail if runner has import errors
        from poc.session_state_demo.anniversary_demo.runner import DemoRunner

        assert DemoRunner is not None

    def test_runner_has_two_way_concierge_field(self):
        """DemoRunner should have two_way_concierge attribute."""
        from poc.session_state_demo.anniversary_demo.runner import DemoRunner

        runner = DemoRunner(auto_mode=True)
        assert hasattr(runner, "two_way_concierge")
        assert runner.two_way_concierge is None  # Not initialized yet

    def test_runner_has_weather_monitor_id_field(self):
        """DemoRunner should have active_weather_monitor_id attribute."""
        from poc.session_state_demo.anniversary_demo.runner import DemoRunner

        runner = DemoRunner(auto_mode=True)
        assert hasattr(runner, "_active_weather_monitor_id")
        assert runner._active_weather_monitor_id is None


class TestMonitorTools:
    """Test background monitor tool integration."""

    def test_start_background_monitor_exists(self):
        """start_background_monitor tool should exist."""
        from poc.session_state_demo.anniversary_demo.tools import start_background_monitor

        assert callable(start_background_monitor)

    def test_start_weather_monitor(self):
        """Should be able to start a weather monitor."""
        from poc.session_state_demo.anniversary_demo.tools import start_background_monitor

        result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["Saturday", "Sunday"],
            alert_conditions=["rain", "storm"],
        )

        assert result["success"] is True
        assert "monitor_id" in result
        assert result["monitor_type"] == "weather"
        assert result["target"] == "Sonoma"

    def test_check_monitors_at_turn_24(self):
        """Weather monitor should generate alert at Turn 24."""
        from poc.session_state_demo.anniversary_demo.tools import (
            MonitorStore,
            check_monitors,
            start_background_monitor,
        )

        # Reset store
        MonitorStore.reset()

        # Start monitor
        start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["Saturday", "Sunday"],
            alert_conditions=["rain"],
        )

        # Check at Turn 23 (no alert)
        alerts_23 = check_monitors(demo_turn=23)
        assert len(alerts_23) == 0

        # Check at Turn 24 (should alert)
        alerts_24 = check_monitors(demo_turn=24)
        assert len(alerts_24) == 1
        assert (
            "rain" in alerts_24[0].message.lower()
            or "precipitation" in alerts_24[0].message.lower()
        )


class TestNotificationCallback:
    """Test notification callback mechanism."""

    def test_notification_callback_called(self):
        """Notification callback should be invoked for urgent notifications."""
        from poc.session_state_demo.anniversary_demo.background import NotificationQueue

        # Reset queue
        NotificationQueue._instance = None

        callback_received = []

        def on_urgent(notif):
            callback_received.append(notif)

        # Create queue with callback
        queue = NotificationQueue(on_urgent=on_urgent)

        # Set conversation active (callback is only called during active conversation)
        queue.set_conversation_active(True)

        # Create urgent notification (callback is called in create_and_enqueue)
        queue.create_and_enqueue(
            message="Urgent test",
            priority=NotificationPriority.URGENT,
            notification_type=NotificationType.ALERT,
        )

        # Callback should have been called (urgent notifications trigger immediately)
        assert len(callback_received) == 1
        assert callback_received[0].message == "Urgent test"

        # Cleanup
        NotificationQueue._instance = None


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
