"""
DeltaBus Integration Tests

Tests DeltaBus with realistic SessionState delta scenarios.
Includes TestSubscriber class that logs all events and verifies event structure.

Test Coverage:
- TestSubscriber receives all session.* events
- Event ordering (FIFO per session_id)
- Event payloads match SessionState changes
- Performance: 1000 rapid updates, all events delivered
- Multiple concurrent sessions

References:
- docs/plans/chat_experience_poc_plan.md - Issue 2.2.3
- ADR-0045a - K1 Internal Event Bus Architecture
"""

import time
from datetime import datetime
from typing import Any, Dict, List

import pytest
from l4_runtime.deltabus import DeltaBus, DeltaBusEvent


class TestSubscriber:
    """
    Test subscriber that logs all events for verification

    Tracks:
    - All received events
    - Events by type
    - Events by session_id
    - Event ordering
    - Field validation
    """

    def __init__(self, name: str = "test_subscriber"):
        self.name = name
        self.events: List[DeltaBusEvent] = []
        self.events_by_type: Dict[str, List[DeltaBusEvent]] = {}
        self.events_by_session: Dict[str, List[DeltaBusEvent]] = {}
        self.validation_errors: List[str] = []

    def callback(self, event: DeltaBusEvent):
        """Event callback - logs and validates event"""
        # Log event
        self.events.append(event)

        # Track by type
        if event.event_type not in self.events_by_type:
            self.events_by_type[event.event_type] = []
        self.events_by_type[event.event_type].append(event)

        # Track by session
        if event.session_id not in self.events_by_session:
            self.events_by_session[event.session_id] = []
        self.events_by_session[event.session_id].append(event)

        # Validate event structure
        self._validate_event(event)

    def _validate_event(self, event: DeltaBusEvent):
        """Validate event has required fields"""
        if not event.event_type:
            self.validation_errors.append(f"Missing event_type in event {event.event_id}")
        if not event.session_id:
            self.validation_errors.append(f"Missing session_id in event {event.event_id}")
        if not event.event_id:
            self.validation_errors.append("Missing event_id")
        if not event.trace_id:
            self.validation_errors.append(f"Missing trace_id in event {event.event_id}")
        if not event.timestamp:
            self.validation_errors.append(f"Missing timestamp in event {event.event_id}")
        if not isinstance(event.payload, dict):
            self.validation_errors.append(f"Payload not dict in event {event.event_id}")

    def get_event_count(self) -> int:
        """Get total events received"""
        return len(self.events)

    def get_events_by_type(self, event_type: str) -> List[DeltaBusEvent]:
        """Get all events of specific type"""
        return self.events_by_type.get(event_type, [])

    def get_events_by_session(self, session_id: str) -> List[DeltaBusEvent]:
        """Get all events for specific session"""
        return self.events_by_session.get(session_id, [])

    def clear(self):
        """Clear all tracked events"""
        self.events.clear()
        self.events_by_type.clear()
        self.events_by_session.clear()
        self.validation_errors.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get subscriber statistics"""
        return {
            "total_events": len(self.events),
            "events_by_type": {k: len(v) for k, v in self.events_by_type.items()},
            "unique_sessions": len(self.events_by_session),
            "validation_errors": len(self.validation_errors),
        }


@pytest.fixture
def deltabus():
    """Create fresh DeltaBus instance"""
    bus = DeltaBus()
    bus._subscribers.clear()
    bus._subscriber_index.clear()
    bus._session_queues.clear()
    bus._events_published = 0
    bus._events_delivered = 0
    bus._events_dropped = 0
    bus._delivery_times.clear()
    bus._shutdown = False
    yield bus


def test_test_subscriber_basic(deltabus):
    """Test TestSubscriber receives events correctly"""
    subscriber = TestSubscriber("test")

    # Subscribe to all session events
    deltabus.subscribe("session.*", subscriber.callback)

    # Publish various events
    deltabus.publish(
        DeltaBusEvent("session.created", "session_1", {"user_id": "user_123"}, trace_id="trace_1")
    )

    deltabus.publish(
        DeltaBusEvent(
            "session.delta",
            "session_1",
            {"deltas": [{"section": "beliefs", "changes": 3}]},
            trace_id="trace_2",
        )
    )

    deltabus.publish(
        DeltaBusEvent("session.archived", "session_1", {"reason": "timeout"}, trace_id="trace_3")
    )

    # Verify all events received
    assert subscriber.get_event_count() == 3
    assert (
        len(subscriber.validation_errors) == 0
    ), f"Validation errors: {subscriber.validation_errors}"

    # Verify events by type
    assert len(subscriber.get_events_by_type("session.created")) == 1
    assert len(subscriber.get_events_by_type("session.delta")) == 1
    assert len(subscriber.get_events_by_type("session.archived")) == 1


def test_session_state_delta_simulation(deltabus):
    """Simulate SessionState delta updates"""
    subscriber = TestSubscriber("delta_test")
    deltabus.subscribe("session.delta", subscriber.callback)

    # Simulate SessionState updates for a session
    session_id = "session_abc123"

    # Update 1: Beliefs changed
    deltabus.publish(
        DeltaBusEvent(
            "session.delta",
            session_id,
            {
                "deltas": [
                    {
                        "section": "beliefs",
                        "field_path": "beliefs.b001.statement",
                        "old_value": "User is injured",
                        "new_value": "User is recovering well",
                        "timestamp": datetime.utcnow().isoformat(),
                        "origin": "healthcare_agent",
                    }
                ],
                "batch_timestamp": datetime.utcnow().isoformat(),
            },
            trace_id="trace_beliefs_update",
        )
    )

    # Update 2: Scoreboard changed
    deltabus.publish(
        DeltaBusEvent(
            "session.delta",
            session_id,
            {
                "deltas": [
                    {
                        "section": "scoreboard",
                        "field_path": "agents.healthcare.score",
                        "old_value": 0.7,
                        "new_value": 0.85,
                        "timestamp": datetime.utcnow().isoformat(),
                        "origin": "orchestrator",
                    }
                ],
                "batch_timestamp": datetime.utcnow().isoformat(),
            },
            trace_id="trace_scoreboard_update",
        )
    )

    # Update 3: Control changed
    deltabus.publish(
        DeltaBusEvent(
            "session.delta",
            session_id,
            {
                "deltas": [
                    {
                        "section": "control",
                        "field_path": "control.selected_agent",
                        "old_value": "concierge",
                        "new_value": "planner",
                        "timestamp": datetime.utcnow().isoformat(),
                        "origin": "orchestrator",
                    }
                ],
                "batch_timestamp": datetime.utcnow().isoformat(),
            },
            trace_id="trace_control_update",
        )
    )

    # Verify all deltas received
    assert subscriber.get_event_count() == 3
    assert len(subscriber.validation_errors) == 0

    # Verify event ordering (FIFO)
    events = subscriber.get_events_by_session(session_id)
    assert len(events) == 3
    assert events[0].payload["deltas"][0]["section"] == "beliefs"
    assert events[1].payload["deltas"][0]["section"] == "scoreboard"
    assert events[2].payload["deltas"][0]["section"] == "control"


def test_multiple_concurrent_sessions(deltabus):
    """Test multiple sessions publishing events concurrently"""
    subscriber = TestSubscriber("concurrent")
    deltabus.subscribe("session.*", subscriber.callback)

    # Create 5 concurrent sessions
    session_ids = [f"session_{i}" for i in range(5)]

    # Publish events from each session
    for session_id in session_ids:
        # Session created
        deltabus.publish(
            DeltaBusEvent(
                "session.created",
                session_id,
                {"user_id": f"user_{session_id}"},
            )
        )

        # Multiple deltas
        for i in range(3):
            deltabus.publish(
                DeltaBusEvent(
                    "session.delta",
                    session_id,
                    {"deltas": [{"section": "beliefs", "change_id": i}]},
                )
            )

    # Verify all events received
    assert subscriber.get_event_count() == 5 * 4  # 5 sessions × 4 events each

    # Verify each session received all its events
    for session_id in session_ids:
        session_events = subscriber.get_events_by_session(session_id)
        assert len(session_events) == 4  # 1 created + 3 deltas

        # Verify ordering within session (FIFO)
        assert session_events[0].event_type == "session.created"
        assert all(e.event_type == "session.delta" for e in session_events[1:])


def test_performance_1000_rapid_updates(deltabus):
    """Performance test: 1000 rapid SessionState updates"""
    subscriber = TestSubscriber("performance")
    deltabus.subscribe("session.delta", subscriber.callback)

    session_id = "session_perf_test"

    # Publish 1000 rapid updates
    start_time = time.perf_counter()
    for i in range(1000):
        deltabus.publish(
            DeltaBusEvent(
                "session.delta",
                session_id,
                {
                    "deltas": [
                        {
                            "section": "beliefs",
                            "field_path": f"beliefs.b{i:04d}",
                            "old_value": None,
                            "new_value": f"belief_{i}",
                            "timestamp": datetime.utcnow().isoformat(),
                            "origin": "test",
                        }
                    ]
                },
                trace_id=f"trace_{i:04d}",
            )
        )
    total_time = time.perf_counter() - start_time

    # Verify all events delivered
    assert subscriber.get_event_count() == 1000
    assert len(subscriber.validation_errors) == 0

    # Check DeltaBus stats
    stats = deltabus.get_stats()
    assert stats["events_published"] == 1000
    assert stats["events_delivered"] == 1000
    assert stats["events_dropped"] == 0
    assert (
        stats["p95_delivery_ms"] < 1.0
    ), f"P95 delivery {stats['p95_delivery_ms']}ms exceeds 1ms budget"

    print(f"\n[Performance] 1000 events in {total_time*1000:.2f}ms")
    print(f"[Performance] P95 delivery: {stats['p95_delivery_ms']:.3f}ms")
    print(f"[Performance] Avg delivery: {stats['avg_delivery_ms']:.3f}ms")
    print(f"[Performance] Throughput: {1000/total_time:.0f} events/sec")


def test_event_ordering_fifo(deltabus):
    """Test FIFO ordering guarantee per session"""
    subscriber = TestSubscriber("ordering")
    deltabus.subscribe("session.delta", subscriber.callback)

    session_id = "session_order_test"

    # Publish events with timestamps
    for i in range(100):
        deltabus.publish(
            DeltaBusEvent(
                "session.delta",
                session_id,
                {"sequence": i, "timestamp": datetime.utcnow().isoformat()},
                trace_id=f"trace_{i:03d}",
            )
        )

    # Verify ordering preserved
    events = subscriber.get_events_by_session(session_id)
    assert len(events) == 100

    # Check sequence numbers are in order
    for i, event in enumerate(events):
        assert (
            event.payload["sequence"] == i
        ), f"Event {i} has wrong sequence: {event.payload['sequence']}"


def test_agent_lifecycle_events(deltabus):
    """Test agent lifecycle event simulation"""
    subscriber = TestSubscriber("lifecycle")
    deltabus.subscribe("agent.*", subscriber.callback)

    # Simulate agent spawning
    deltabus.publish(
        DeltaBusEvent(
            "agent.spawned",
            "session_1",
            {"agent_id": "healthcare_agent_001", "agent_type": "healthcare", "status": "WARMING"},
            trace_id="trace_spawn",
        )
    )

    # Simulate agent termination
    deltabus.publish(
        DeltaBusEvent(
            "agent.terminated",
            "session_1",
            {
                "agent_id": "healthcare_agent_001",
                "reason": "idle_timeout",
                "final_status": "TERMINATED",
            },
            trace_id="trace_terminate",
        )
    )

    # Verify events received
    assert subscriber.get_event_count() == 2
    spawn_events = subscriber.get_events_by_type("agent.spawned")
    terminate_events = subscriber.get_events_by_type("agent.terminated")

    assert len(spawn_events) == 1
    assert len(terminate_events) == 1
    assert spawn_events[0].payload["agent_id"] == "healthcare_agent_001"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
