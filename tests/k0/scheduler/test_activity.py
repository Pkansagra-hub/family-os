"""
Tests for k0/scheduler/activity.py

Tests ActivityTracker for idle detection:
- Activity recording
- Idle time calculation
- Listener registration and firing
- Lifecycle (start/stop)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from k0.scheduler.activity import ActivityTracker, get_activity_tracker, set_activity_tracker


class TestActivityTrackerCreation:
    """Tests for ActivityTracker initialization."""

    def test_activity_tracker_creation(self) -> None:
        """Test creating an activity tracker."""
        tracker = ActivityTracker()

        assert not tracker.is_running
        assert tracker.listener_count == 0

    def test_activity_tracker_custom_interval(self) -> None:
        """Test creating tracker with custom check interval."""
        tracker = ActivityTracker(check_interval=0.5)

        assert tracker._check_interval == 0.5

    def test_activity_tracker_default_interval(self) -> None:
        """Test default check interval is 1 second."""
        tracker = ActivityTracker()

        assert tracker._check_interval == 1.0


class TestActivityTrackerIdleTime:
    """Tests for idle time tracking."""

    def test_idle_seconds_initial(self) -> None:
        """Test initial idle_seconds is near zero."""
        tracker = ActivityTracker()

        # Should be very close to zero initially
        assert tracker.idle_seconds() < 0.1

    def test_record_activity_resets_idle(self) -> None:
        """Test that record_activity resets the idle timer."""
        tracker = ActivityTracker()

        # Wait a bit
        import time

        time.sleep(0.1)

        # Record activity
        tracker.record_activity()

        # Idle should be near zero again
        assert tracker.idle_seconds() < 0.05

    def test_idle_seconds_increases(self) -> None:
        """Test that idle_seconds increases over time."""
        tracker = ActivityTracker()

        import time

        initial = tracker.idle_seconds()
        time.sleep(0.1)
        later = tracker.idle_seconds()

        assert later > initial


class TestActivityTrackerLifecycle:
    """Tests for ActivityTracker start/stop."""

    @pytest.mark.asyncio
    async def test_activity_tracker_start_stop(self) -> None:
        """Test starting and stopping tracker."""
        tracker = ActivityTracker(check_interval=0.1)

        await tracker.start()
        assert tracker.is_running

        await tracker.stop()
        assert not tracker.is_running

    @pytest.mark.asyncio
    async def test_activity_tracker_double_start(self) -> None:
        """Test that double start is a no-op."""
        tracker = ActivityTracker(check_interval=0.1)

        await tracker.start()
        await tracker.start()  # Should not raise

        assert tracker.is_running

        await tracker.stop()

    @pytest.mark.asyncio
    async def test_activity_tracker_stop_when_not_running(self) -> None:
        """Test stopping tracker that's not running."""
        tracker = ActivityTracker()

        # Should not raise
        await tracker.stop()
        assert not tracker.is_running


class TestActivityTrackerListeners:
    """Tests for idle listener registration and firing."""

    @pytest.mark.asyncio
    async def test_register_idle_listener(self) -> None:
        """Test registering an idle listener."""
        tracker = ActivityTracker(check_interval=0.1)
        callback = MagicMock()

        await tracker.register_idle_listener(
            listener_id="test_listener",
            callback=callback,
            threshold_seconds=0.2,
        )

        assert tracker.listener_count == 1

    @pytest.mark.asyncio
    async def test_unregister_idle_listener(self) -> None:
        """Test unregistering an idle listener."""
        tracker = ActivityTracker(check_interval=0.1)
        callback = MagicMock()

        await tracker.register_idle_listener(
            listener_id="test_listener",
            callback=callback,
            threshold_seconds=0.2,
        )
        assert tracker.listener_count == 1

        result = await tracker.unregister_idle_listener("test_listener")
        assert result is True
        assert tracker.listener_count == 0

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_listener(self) -> None:
        """Test unregistering a listener that doesn't exist."""
        tracker = ActivityTracker()

        result = await tracker.unregister_idle_listener("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_listener_fires_when_idle(self) -> None:
        """Test that listener fires when idle threshold exceeded."""
        tracker = ActivityTracker(check_interval=0.05)
        fired = []

        def callback() -> None:
            fired.append(True)

        await tracker.register_idle_listener(
            listener_id="test_listener",
            callback=callback,
            threshold_seconds=0.1,
        )

        await tracker.start()

        # Wait for listener to fire (idle threshold is 0.1s, check interval is 0.05s)
        await asyncio.sleep(0.3)

        await tracker.stop()

        # Should have fired at least once
        assert len(fired) >= 1

    @pytest.mark.asyncio
    async def test_listener_reset_on_activity(self) -> None:
        """Test that listener can fire again after activity."""
        tracker = ActivityTracker(check_interval=0.05)
        fire_count = []

        def callback() -> None:
            fire_count.append(True)

        await tracker.register_idle_listener(
            listener_id="test_listener",
            callback=callback,
            threshold_seconds=0.1,
        )

        await tracker.start()

        # Wait for first fire
        await asyncio.sleep(0.2)
        first_count = len(fire_count)
        assert first_count >= 1

        # Record activity (resets the timer and fired flag)
        tracker.record_activity()

        # Wait for second fire
        await asyncio.sleep(0.2)

        await tracker.stop()

        # Should have fired again
        assert len(fire_count) > first_count

    @pytest.mark.asyncio
    async def test_multiple_listeners(self) -> None:
        """Test multiple listeners with different thresholds."""
        tracker = ActivityTracker(check_interval=0.05)
        fast_fired = []
        slow_fired = []

        await tracker.register_idle_listener(
            listener_id="fast",
            callback=lambda: fast_fired.append(True),
            threshold_seconds=0.1,
        )
        await tracker.register_idle_listener(
            listener_id="slow",
            callback=lambda: slow_fired.append(True),
            threshold_seconds=0.3,
        )

        await tracker.start()

        # Fast should fire first
        await asyncio.sleep(0.2)
        assert len(fast_fired) >= 1
        assert len(slow_fired) == 0

        # Slow fires later
        await asyncio.sleep(0.2)
        assert len(slow_fired) >= 1

        await tracker.stop()

    @pytest.mark.asyncio
    async def test_listener_callback_error_handling(self) -> None:
        """Test that callback errors don't crash the tracker."""
        tracker = ActivityTracker(check_interval=0.05)
        good_fired = []

        def bad_callback() -> None:
            raise RuntimeError("Callback error")

        def good_callback() -> None:
            good_fired.append(True)

        await tracker.register_idle_listener(
            listener_id="bad",
            callback=bad_callback,
            threshold_seconds=0.1,
        )
        await tracker.register_idle_listener(
            listener_id="good",
            callback=good_callback,
            threshold_seconds=0.1,
        )

        await tracker.start()
        await asyncio.sleep(0.2)
        await tracker.stop()

        # Good callback should have fired despite bad callback error
        assert len(good_fired) >= 1


class TestActivityTrackerSingleton:
    """Tests for global singleton functions."""

    def test_get_activity_tracker_singleton(self) -> None:
        """Test that get_activity_tracker returns same instance."""
        # Reset singleton
        set_activity_tracker(None)

        tracker1 = get_activity_tracker()
        tracker2 = get_activity_tracker()

        assert tracker1 is tracker2

        # Clean up
        set_activity_tracker(None)

    def test_set_activity_tracker(self) -> None:
        """Test setting a custom activity tracker."""
        custom = ActivityTracker(check_interval=5.0)
        set_activity_tracker(custom)

        assert get_activity_tracker() is custom

        # Clean up
        set_activity_tracker(None)

    def test_reset_activity_tracker(self) -> None:
        """Test resetting the singleton."""
        tracker1 = get_activity_tracker()
        set_activity_tracker(None)
        tracker2 = get_activity_tracker()

        assert tracker1 is not tracker2

        # Clean up
        set_activity_tracker(None)
