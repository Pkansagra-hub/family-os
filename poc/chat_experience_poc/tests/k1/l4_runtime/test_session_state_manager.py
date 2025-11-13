"""
Integration tests for SessionStateManager with DeltaBus

Validates:
- SessionState creation and updates
- DeltaBus event publishing on updates
- Event payload structure
- FIFO ordering per session
- Concurrent sessions
- Performance budgets (<1ms per update)

References:
- docs/plans/chat_experience_poc_plan.md - Issue 2.2.2
- tests/test_deltabus_integration.py - TestSubscriber class
"""

import time
from typing import Any, Dict, List

import pytest
from l4_runtime.deltabus.deltabus import DeltaBusEvent, EventType, get_deltabus
from l4_runtime.session_state import SessionStateManager


class TestSubscriber:
    """Test helper - validates event structure and tracks deliveries"""

    def __init__(self, name: str = "test_subscriber"):
        self.name = name
        self.events: List[DeltaBusEvent] = []
        self.events_by_type: Dict[str, List[DeltaBusEvent]] = {}
        self.events_by_session: Dict[str, List[DeltaBusEvent]] = {}
        self.validation_errors: List[str] = []

    def callback(self, event: DeltaBusEvent):
        """Event handler - logs and validates events"""
        self.events.append(event)

        # Index by type
        if event.event_type not in self.events_by_type:
            self.events_by_type[event.event_type] = []
        self.events_by_type[event.event_type].append(event)

        # Index by session
        if event.session_id not in self.events_by_session:
            self.events_by_session[event.session_id] = []
        self.events_by_session[event.session_id].append(event)

        # Validate event structure
        self._validate_event(event)

    def _validate_event(self, event: DeltaBusEvent):
        """Check required fields"""
        if not event.event_id:
            self.validation_errors.append(f"Missing event_id: {event}")
        if not event.session_id:
            self.validation_errors.append(f"Missing session_id: {event}")
        if not event.event_type:
            self.validation_errors.append(f"Missing event_type: {event}")
        if not event.timestamp:
            self.validation_errors.append(f"Missing timestamp: {event}")
        if not event.trace_id:
            self.validation_errors.append(f"Missing trace_id: {event}")

    def get_event_count(self) -> int:
        """Total events received"""
        return len(self.events)

    def get_events_by_type(self, event_type: str) -> List[DeltaBusEvent]:
        """Filter by type"""
        return self.events_by_type.get(event_type, [])

    def get_events_by_session(self, session_id: str) -> List[DeltaBusEvent]:
        """Filter by session"""
        return self.events_by_session.get(session_id, [])

    def clear(self):
        """Reset all tracking"""
        self.events.clear()
        self.events_by_type.clear()
        self.events_by_session.clear()
        self.validation_errors.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Summary statistics"""
        return {
            "total_events": len(self.events),
            "events_by_type": {k: len(v) for k, v in self.events_by_type.items()},
            "events_by_session": {k: len(v) for k, v in self.events_by_session.items()},
            "validation_errors": len(self.validation_errors),
        }


@pytest.fixture
def deltabus():
    """Fresh DeltaBus instance per test"""
    bus = get_deltabus()
    bus._subscribers.clear()
    bus._delivery_tasks.clear()
    bus._events_published = 0
    bus._events_delivered = 0
    bus._events_dropped = 0
    bus._delivery_times.clear()
    yield bus
    # Cleanup
    bus._subscribers.clear()


@pytest.fixture
def session_state_manager(deltabus):
    """SessionStateManager with DeltaBus"""
    return SessionStateManager(deltabus=deltabus)


def test_create_session(session_state_manager, deltabus):
    """
    Test session creation publishes session.created event
    """
    subscriber = TestSubscriber("create_test")
    deltabus.subscribe("session.*", subscriber.callback)

    # Create session
    session = session_state_manager.create_session(user_id="user_123")

    # Wait for event delivery
    time.sleep(0.05)

    # Verify event published
    events = subscriber.get_events_by_type(EventType.SESSION_CREATED.value)
    assert len(events) == 1, "Should publish session.created event"

    event = events[0]
    assert event.session_id == session.session_id
    assert event.payload["user_id"] == "user_123"
    assert event.payload["cognitive_trace_id"] == session.cognitive_trace_id
    assert event.trace_id == session.cognitive_trace_id

    # Verify session stored
    retrieved = session_state_manager.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id


def test_update_section_beliefs(session_state_manager, deltabus):
    """
    Test updating beliefs section publishes session.delta event
    """
    subscriber = TestSubscriber("beliefs_test")
    deltabus.subscribe("session.*", subscriber.callback)

    # Create session
    session = session_state_manager.create_session(user_id="user_456")
    time.sleep(0.05)
    subscriber.clear()  # Clear session.created event

    # Update beliefs
    updates = {
        "user_name": "Alice",
        "user_location": "Seattle",
        "preferred_language": "en",
    }
    changes = session_state_manager.update_section(
        session_id=session.session_id,
        section_name="beliefs",
        updates=updates,
        origin="concierge_agent",
    )

    # Wait for event delivery
    time.sleep(0.05)

    # Verify deltas computed
    assert len(changes) == 3, "Should compute 3 changes"
    assert changes["user_name"]["new"] == "Alice"
    assert changes["user_location"]["new"] == "Seattle"

    # Verify delta event published
    events = subscriber.get_events_by_type(EventType.SESSION_DELTA.value)
    assert len(events) == 1, "Should publish session.delta event"

    event = events[0]
    assert event.session_id == session.session_id
    assert event.payload["section"] == "beliefs"
    assert event.payload["origin"] == "concierge_agent"
    assert event.payload["deltas"] == changes
    assert event.trace_id == session.cognitive_trace_id


def test_update_section_scoreboard(session_state_manager, deltabus):
    """
    Test updating scoreboard section
    """
    subscriber = TestSubscriber("scoreboard_test")
    deltabus.subscribe("session.delta", subscriber.callback)

    # Create session
    session = session_state_manager.create_session(user_id="user_789")
    time.sleep(0.05)

    # Update scoreboard
    updates = {
        "current_topic": "weather",
        "qud": "What's the weather in Seattle?",
    }
    session_state_manager.update_section(
        session_id=session.session_id,
        section_name="scoreboard",
        updates=updates,
    )

    time.sleep(0.05)

    # Verify event
    assert len(subscriber.events) == 1
    event = subscriber.events[0]
    assert event.payload["section"] == "scoreboard"
    assert "current_topic" in event.payload["deltas"]


def test_get_section(session_state_manager, deltabus):
    """
    Test reading section without updates
    """
    # Create session
    session = session_state_manager.create_session(user_id="user_999")

    # Update beliefs
    session_state_manager.update_section(
        session_id=session.session_id,
        section_name="beliefs",
        updates={"test_key": "test_value"},
    )

    # Get section
    beliefs = session_state_manager.get_section(session.session_id, "beliefs")
    assert beliefs is not None
    assert beliefs["test_key"] == "test_value"

    # Get non-existent session
    result = session_state_manager.get_section("invalid_session", "beliefs")
    assert result is None


def test_multiple_updates_same_session(session_state_manager, deltabus):
    """
    Test multiple updates to same session maintain FIFO ordering
    """
    subscriber = TestSubscriber("fifo_test")
    deltabus.subscribe("session.delta", subscriber.callback)

    # Create session
    session = session_state_manager.create_session(user_id="user_fifo")
    time.sleep(0.05)

    # Multiple updates
    for i in range(10):
        session_state_manager.update_section(
            session_id=session.session_id,
            section_name="beliefs",
            updates={f"key_{i}": f"value_{i}"},
        )

    time.sleep(0.1)

    # Verify all events delivered
    assert len(subscriber.events) == 10, "Should deliver 10 delta events"

    # Verify FIFO ordering (keys should be in order)
    for i in range(10):
        event = subscriber.events[i]
        assert f"key_{i}" in event.payload["deltas"]


def test_concurrent_sessions(session_state_manager, deltabus):
    """
    Test multiple concurrent sessions
    """
    subscriber = TestSubscriber("concurrent_test")
    deltabus.subscribe("session.*", subscriber.callback)

    # Create 5 sessions
    sessions = []
    for i in range(5):
        session = session_state_manager.create_session(user_id=f"user_{i}")
        sessions.append(session)

    time.sleep(0.1)

    # Update all sessions (2 sections each)
    for i, session in enumerate(sessions):
        session_state_manager.update_section(
            session_id=session.session_id,
            section_name="beliefs",
            updates={"session_index": i},
        )
        session_state_manager.update_section(
            session_id=session.session_id,
            section_name="scoreboard",
            updates={"topic": f"topic_{i}"},
        )

    time.sleep(0.1)

    # Verify events: 5 session.created + 10 session.delta (5 sessions * 2 updates)
    created_events = subscriber.get_events_by_type(EventType.SESSION_CREATED.value)
    delta_events = subscriber.get_events_by_type(EventType.SESSION_DELTA.value)

    assert len(created_events) == 5, "Should have 5 session.created events"
    assert len(delta_events) == 10, "Should have 10 session.delta events"


def test_delta_event_payloads(session_state_manager, deltabus):
    """
    Test delta event payloads match SessionState changes
    """
    subscriber = TestSubscriber("payload_test")
    deltabus.subscribe("session.delta", subscriber.callback)

    # Create session
    session = session_state_manager.create_session(user_id="user_payload")
    time.sleep(0.05)

    # Update with multiple keys
    updates = {
        "key_a": "value_a",
        "key_b": 123,
        "key_c": {"nested": "dict"},
    }
    session_state_manager.update_section(
        session_id=session.session_id,
        section_name="control",
        updates=updates,
    )

    time.sleep(0.05)

    # Verify payload
    assert len(subscriber.events) == 1
    event = subscriber.events[0]
    deltas = event.payload["deltas"]

    assert deltas["key_a"]["new"] == "value_a"
    assert deltas["key_b"]["new"] == 123
    assert deltas["key_c"]["new"] == {"nested": "dict"}


def test_performance_1000_updates(session_state_manager, deltabus):
    """
    Test 1000 updates deliver all events with <1ms per update
    """
    subscriber = TestSubscriber("perf_test")
    deltabus.subscribe("session.delta", subscriber.callback)

    # Create session
    session = session_state_manager.create_session(user_id="user_perf")
    time.sleep(0.05)
    subscriber.clear()  # Clear session.created event

    # 1000 rapid updates
    start = time.time()
    for i in range(1000):
        session_state_manager.update_section(
            session_id=session.session_id,
            section_name="beliefs",
            updates={f"key_{i}": f"value_{i}"},
        )
    end = time.time()

    # Wait for all events to deliver
    time.sleep(0.2)

    # Verify all events delivered
    assert len(subscriber.events) == 1000, "Should deliver all 1000 delta events"
    assert len(subscriber.validation_errors) == 0, "No validation errors"

    # Performance check
    elapsed_ms = (end - start) * 1000
    avg_per_update_ms = elapsed_ms / 1000
    print(f"\n1000 updates in {elapsed_ms:.2f}ms (avg: {avg_per_update_ms:.3f}ms per update)")

    # Verify budget (1ms per update)
    assert avg_per_update_ms < 1.0, f"Average {avg_per_update_ms:.3f}ms exceeds 1ms budget"


def test_archive_session(session_state_manager, deltabus):
    """
    Test archiving session publishes session.archived event
    """
    subscriber = TestSubscriber("archive_test")
    deltabus.subscribe("session.*", subscriber.callback)

    # Create session
    session = session_state_manager.create_session(user_id="user_archive")
    time.sleep(0.05)
    subscriber.clear()

    # Archive session
    result = session_state_manager.archive_session(session.session_id, reason="manual")
    assert result is True, "Archive should succeed"

    time.sleep(0.05)

    # Verify event
    archived_events = subscriber.get_events_by_type(EventType.SESSION_ARCHIVED.value)
    assert len(archived_events) == 1, "Should publish session.archived event"

    event = archived_events[0]
    assert event.session_id == session.session_id
    assert event.payload["reason"] == "manual"
    assert event.payload["user_id"] == "user_archive"

    # Verify session removed
    retrieved = session_state_manager.get_session(session.session_id)
    assert retrieved is None, "Session should be removed"


def test_stats_tracking(session_state_manager, deltabus):
    """
    Test SessionStateManager tracks statistics
    """
    # Create 2 sessions
    session1 = session_state_manager.create_session(user_id="user_stats_1")
    session2 = session_state_manager.create_session(user_id="user_stats_2")

    # Update sections
    session_state_manager.update_section(session1.session_id, "beliefs", {"key": "value"})
    session_state_manager.update_section(session1.session_id, "scoreboard", {"topic": "test"})
    session_state_manager.update_section(session2.session_id, "control", {"lease": "agent_1"})

    time.sleep(0.1)

    # Get stats
    stats = session_state_manager.get_stats()

    assert stats["active_sessions"] == 2
    assert stats["sessions_created"] == 2
    assert stats["delta_events_published"] == 3
    assert stats["updates_per_section"]["beliefs"] == 1
    assert stats["updates_per_section"]["scoreboard"] == 1
    assert stats["updates_per_section"]["control"] == 1

    # Archive one session
    session_state_manager.archive_session(session1.session_id)
    time.sleep(0.05)

    stats = session_state_manager.get_stats()
    assert stats["active_sessions"] == 1
    assert stats["sessions_archived"] == 1
