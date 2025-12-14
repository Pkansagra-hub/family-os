"""
Unit tests for ProgressEvent dataclass.

Tests:
- ProgressEvent creation
- to_dict() serialization
- is_complete() method
- Timestamp handling
"""

from datetime import datetime

import pytest
from backend.models.progress_event import ProgressEvent


class TestProgressEvent:
    """Test ProgressEvent functionality."""

    def test_progress_event_creation(self):
        """Test creating progress event."""
        event = ProgressEvent(
            task_id="task_nut_123", milestone=2, percent=40, message="🧠 Analyzing patterns..."
        )

        assert event.task_id == "task_nut_123"
        assert event.milestone == 2
        assert event.percent == 40
        assert event.message == "🧠 Analyzing patterns..."
        assert isinstance(event.timestamp, datetime)

    def test_progress_event_all_milestones(self):
        """Test creating events for all 5 milestones."""
        milestones = [
            (1, 20, "📊 Checking your diet history..."),
            (2, 40, "🧠 Analyzing patterns..."),
            (3, 60, "🔗 Finding correlations..."),
            (4, 80, "💡 Generating insights..."),
            (5, 100, "✅ Analysis complete"),
        ]

        for milestone, percent, message in milestones:
            event = ProgressEvent(
                task_id="task_123", milestone=milestone, percent=percent, message=message
            )

            assert event.milestone == milestone
            assert event.percent == percent
            assert event.message == message

    def test_progress_event_to_dict(self):
        """Test progress event serialization."""
        event = ProgressEvent(
            task_id="task_123", milestone=3, percent=60, message="Finding correlations"
        )

        data = event.to_dict()

        assert data["task_id"] == "task_123"
        assert data["milestone"] == 3
        assert data["percent"] == 60
        assert data["message"] == "Finding correlations"
        assert "timestamp" in data

    def test_progress_event_is_complete_false(self):
        """Test is_complete() returns False for incomplete events."""
        events = [
            ProgressEvent("task_123", 1, 20, "Starting"),
            ProgressEvent("task_123", 2, 40, "Working"),
            ProgressEvent("task_123", 3, 60, "Processing"),
            ProgressEvent("task_123", 4, 80, "Almost done"),
            ProgressEvent("task_123", 5, 99, "Almost complete"),
        ]

        for event in events:
            assert event.is_complete() is False

    def test_progress_event_is_complete_true(self):
        """Test is_complete() returns True for 100% events."""
        event = ProgressEvent(task_id="task_123", milestone=5, percent=100, message="✅ Complete")

        assert event.is_complete() is True

    def test_progress_event_is_complete_over_100(self):
        """Test is_complete() returns True for >100% (edge case)."""
        event = ProgressEvent(task_id="task_123", milestone=5, percent=105, message="Over complete")

        assert event.is_complete() is True

    def test_progress_event_default_timestamp(self):
        """Test that timestamp defaults to current time."""
        before = datetime.utcnow()
        event = ProgressEvent(task_id="task_123", milestone=1, percent=20, message="Starting")
        after = datetime.utcnow()

        assert before <= event.timestamp <= after

    def test_progress_event_sequential_milestones(self):
        """Test creating sequential progress events."""
        task_id = "task_nutritionist_abc"

        events = []
        for milestone in range(1, 6):
            event = ProgressEvent(
                task_id=task_id,
                milestone=milestone,
                percent=milestone * 20,
                message=f"Milestone {milestone}",
            )
            events.append(event)

        # Verify progression
        assert len(events) == 5
        assert events[0].percent == 20
        assert events[1].percent == 40
        assert events[2].percent == 60
        assert events[3].percent == 80
        assert events[4].percent == 100

        # Only last one is complete
        assert not events[0].is_complete()
        assert not events[1].is_complete()
        assert not events[2].is_complete()
        assert not events[3].is_complete()
        assert events[4].is_complete()

    def test_progress_event_serialization_preserves_data(self):
        """Test that serialization preserves all data."""
        event = ProgressEvent(
            task_id="task_nut_456", milestone=3, percent=60, message="🔗 Finding correlations..."
        )

        data = event.to_dict()

        # Verify all fields present and correct
        assert data["task_id"] == event.task_id
        assert data["milestone"] == event.milestone
        assert data["percent"] == event.percent
        assert data["message"] == event.message
        assert data["timestamp"] == event.timestamp.isoformat()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
    pytest.main([__file__, "-v"])
