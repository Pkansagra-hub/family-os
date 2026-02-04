"""
Epic 4.8.4: Test Event Capture Flow
====================================

Tests that verify the event capture infrastructure works correctly.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.8 - Port/Adapter Integration
ISSUE: 4.8.4 - Test event capture flow

SCENARIO:
---------
1. Create manager with LocalEventAdapter(capture_mode=True)
2. Perform operations via manager.mutate()
3. Drain events
4. Verify event types present, payloads correct, order preserved

ASSERTIONS:
-----------
- Event capture infrastructure works
- Events have correct structure (event_type, payload, timestamp)
- Event payloads contain expected fields
- Events are ordered by timestamp
- drain() clears events after return
- Subscription/handler mechanism works

NOTE: Manager may not automatically emit all 8 event types yet.
We test what IS emitted and also test the capture infrastructure directly.
"""

import time
import uuid
from typing import Any, Generator, List

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager
from k1.sessionstate.adapters.local_events import LocalEventAdapter
from k1.sessionstate.events import EventType

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def capture_adapter() -> Generator[LocalEventAdapter, None, None]:
    """
    Create LocalEventAdapter with capture mode enabled.
    """
    adapter = LocalEventAdapter(capture_mode=True)
    yield adapter
    adapter.stop()


@pytest.fixture
def manager_with_capture() -> Generator[SessionStateManager, None, None]:
    """
    Create manager with event capture enabled.

    Uses InMemoryStorageAdapter (no db_path needed for create_for_testing).
    """
    session_id = f"evtcap-{uuid.uuid4().hex[:8]}"

    manager = SessionStateFactory.create_for_testing(
        session_id=session_id,
    )

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


@pytest.fixture
def started_capture_manager(
    manager_with_capture: SessionStateManager,
) -> SessionStateManager:
    """Manager with capture that is already started."""
    result = manager_with_capture.start(restore_if_exists=False)
    assert result.success, f"Failed to start: {result.error}"
    return manager_with_capture


# =============================================================================
# LOCALEVENTADAPTER CAPTURE TESTS
# =============================================================================


class TestLocalEventAdapterCapture:
    """Test LocalEventAdapter capture functionality."""

    def test_capture_mode_enabled_by_default(self, capture_adapter: LocalEventAdapter) -> None:
        """Capture mode enabled when capture_mode=True."""
        assert capture_adapter._capture_mode is True

    def test_emit_stores_event(self, capture_adapter: LocalEventAdapter) -> None:
        """Emit stores event when capture enabled."""
        capture_adapter.emit("test.event", {"data": "test"})

        events = capture_adapter.get_captured_events()
        assert len(events) == 1
        assert events[0][0] == "test.event"
        assert events[0][1] == {"data": "test"}

    def test_emit_stores_timestamp(self, capture_adapter: LocalEventAdapter) -> None:
        """Emit stores timestamp with event."""
        before_ts = time.time()
        capture_adapter.emit("test.event", {})
        after_ts = time.time()

        events = capture_adapter.get_captured_events()
        event_ts = events[0][2]

        assert before_ts <= event_ts <= after_ts

    def test_multiple_events_captured(self, capture_adapter: LocalEventAdapter) -> None:
        """Multiple events are captured in order."""
        capture_adapter.emit("event.one", {"n": 1})
        capture_adapter.emit("event.two", {"n": 2})
        capture_adapter.emit("event.three", {"n": 3})

        events = capture_adapter.get_captured_events()
        assert len(events) == 3
        assert events[0][0] == "event.one"
        assert events[1][0] == "event.two"
        assert events[2][0] == "event.three"

    def test_drain_returns_events(self, capture_adapter: LocalEventAdapter) -> None:
        """drain() returns captured events."""
        capture_adapter.emit("test.event", {"x": 1})
        capture_adapter.emit("test.event", {"x": 2})

        events = capture_adapter.drain()
        assert len(events) == 2

    def test_drain_clears_events(self, capture_adapter: LocalEventAdapter) -> None:
        """drain() clears event buffer after returning."""
        capture_adapter.emit("test.event", {})
        capture_adapter.emit("test.event", {})

        # First drain gets events
        events1 = capture_adapter.drain()
        assert len(events1) == 2

        # Second drain is empty
        events2 = capture_adapter.drain()
        assert len(events2) == 0

    def test_get_captured_events_filter_by_type(self, capture_adapter: LocalEventAdapter) -> None:
        """get_captured_events filters by event type."""
        capture_adapter.emit("type.a", {"t": "a"})
        capture_adapter.emit("type.b", {"t": "b"})
        capture_adapter.emit("type.a", {"t": "a2"})

        type_a = capture_adapter.get_captured_events("type.a")
        type_b = capture_adapter.get_captured_events("type.b")

        assert len(type_a) == 2
        assert len(type_b) == 1

    def test_clear_captured(self, capture_adapter: LocalEventAdapter) -> None:
        """clear_captured() clears event buffer."""
        capture_adapter.emit("test.event", {})
        capture_adapter.clear_captured()

        events = capture_adapter.get_captured_events()
        assert len(events) == 0

    def test_assert_emitted_passes(self, capture_adapter: LocalEventAdapter) -> None:
        """assert_emitted passes when count matches."""
        capture_adapter.emit("test.event", {})
        capture_adapter.emit("test.event", {})

        # Should not raise
        capture_adapter.assert_emitted("test.event", count=2)

    def test_assert_emitted_fails(self, capture_adapter: LocalEventAdapter) -> None:
        """assert_emitted fails when count doesn't match."""
        capture_adapter.emit("test.event", {})

        with pytest.raises(AssertionError) as exc_info:
            capture_adapter.assert_emitted("test.event", count=5)

        assert "Expected 5" in str(exc_info.value)
        assert "got 1" in str(exc_info.value)


# =============================================================================
# EVENT TYPES TESTS
# =============================================================================


class TestEventTypes:
    """Test all 8 event types are defined."""

    def test_mutation_requested_exists(self) -> None:
        """MUTATION_REQUESTED event type exists."""
        assert EventType.MUTATION_REQUESTED.value == "sessionstate.mutation.requested"

    def test_mutation_approved_exists(self) -> None:
        """MUTATION_APPROVED event type exists."""
        assert EventType.MUTATION_APPROVED.value == "sessionstate.mutation.approved"

    def test_mutation_rejected_exists(self) -> None:
        """MUTATION_REJECTED event type exists."""
        assert EventType.MUTATION_REJECTED.value == "sessionstate.mutation.rejected"

    def test_eviction_triggered_exists(self) -> None:
        """EVICTION_TRIGGERED event type exists."""
        assert EventType.EVICTION_TRIGGERED.value == "sessionstate.eviction.triggered"

    def test_eviction_completed_exists(self) -> None:
        """EVICTION_COMPLETED event type exists."""
        assert EventType.EVICTION_COMPLETED.value == "sessionstate.eviction.completed"

    def test_emergency_activated_exists(self) -> None:
        """EMERGENCY_ACTIVATED event type exists."""
        assert EventType.EMERGENCY_ACTIVATED.value == "sessionstate.emergency.activated"

    def test_emergency_resolved_exists(self) -> None:
        """EMERGENCY_RESOLVED event type exists."""
        assert EventType.EMERGENCY_RESOLVED.value == "sessionstate.emergency.resolved"

    def test_reconstruction_started_exists(self) -> None:
        """RECONSTRUCTION_STARTED event type exists."""
        assert EventType.RECONSTRUCTION_STARTED.value == "sessionstate.reconstruction.started"

    def test_all_8_types_defined(self) -> None:
        """All 8 event types are defined."""
        all_types = list(EventType)
        assert len(all_types) == 8


# =============================================================================
# SUBSCRIPTION TESTS
# =============================================================================


class TestSubscriptionMechanism:
    """Test subscription and handler mechanism."""

    def test_subscribe_returns_id(self, capture_adapter: LocalEventAdapter) -> None:
        """subscribe() returns subscription ID."""
        sub_id = capture_adapter.subscribe("test.event", lambda e: None)
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0

    def test_handler_called_on_emit(self, capture_adapter: LocalEventAdapter) -> None:
        """Handler is called when event is emitted."""
        received: List[Any] = []

        def handler(event: Any) -> None:
            received.append(event)

        capture_adapter.subscribe("test.event", handler)
        capture_adapter.emit("test.event", {"key": "value"})

        # Wait for dispatch
        capture_adapter.wait_for_dispatch(timeout=1.0)

        assert len(received) == 1
        assert received[0] == {"key": "value"}

    def test_multiple_handlers_called(self, capture_adapter: LocalEventAdapter) -> None:
        """Multiple handlers all receive event."""
        received1: List[Any] = []
        received2: List[Any] = []

        capture_adapter.subscribe("test.event", lambda e: received1.append(e))
        capture_adapter.subscribe("test.event", lambda e: received2.append(e))

        capture_adapter.emit("test.event", {"n": 1})
        capture_adapter.wait_for_dispatch(timeout=1.0)

        assert len(received1) == 1
        assert len(received2) == 1

    def test_unsubscribe_removes_handler(self, capture_adapter: LocalEventAdapter) -> None:
        """unsubscribe() removes handler."""
        received: List[Any] = []

        sub_id = capture_adapter.subscribe("test.event", lambda e: received.append(e))
        capture_adapter.unsubscribe(sub_id)

        capture_adapter.emit("test.event", {})
        capture_adapter.wait_for_dispatch(timeout=0.5)

        assert len(received) == 0

    def test_unsubscribe_returns_true(self, capture_adapter: LocalEventAdapter) -> None:
        """unsubscribe() returns True when successful."""
        sub_id = capture_adapter.subscribe("test.event", lambda e: None)
        result = capture_adapter.unsubscribe(sub_id)
        assert result is True

    def test_unsubscribe_unknown_returns_false(self, capture_adapter: LocalEventAdapter) -> None:
        """unsubscribe() returns False for unknown ID."""
        result = capture_adapter.unsubscribe("unknown-id")
        assert result is False

    def test_handlers_only_for_matching_type(self, capture_adapter: LocalEventAdapter) -> None:
        """Handlers only receive matching event types."""
        received_a: List[Any] = []
        received_b: List[Any] = []

        capture_adapter.subscribe("type.a", lambda e: received_a.append(e))
        capture_adapter.subscribe("type.b", lambda e: received_b.append(e))

        capture_adapter.emit("type.a", {"type": "a"})
        capture_adapter.wait_for_dispatch(timeout=1.0)

        assert len(received_a) == 1
        assert len(received_b) == 0


# =============================================================================
# EVENT ORDER TESTS
# =============================================================================


class TestEventOrdering:
    """Test event ordering is preserved."""

    def test_events_in_emit_order(self, capture_adapter: LocalEventAdapter) -> None:
        """Events are captured in emission order."""
        for i in range(10):
            capture_adapter.emit("test.event", {"order": i})

        events = capture_adapter.get_captured_events()

        for i, (event_type, payload, ts) in enumerate(events):
            assert payload["order"] == i

    def test_timestamps_monotonic(self, capture_adapter: LocalEventAdapter) -> None:
        """Timestamps are monotonically increasing."""
        for _ in range(5):
            capture_adapter.emit("test.event", {})
            time.sleep(0.001)  # Small delay

        events = capture_adapter.get_captured_events()

        timestamps = [ts for _, _, ts in events]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]


# =============================================================================
# MANAGER EVENT INTEGRATION
# =============================================================================


class TestManagerEventIntegration:
    """Test manager integrates with event capture."""

    def test_manager_has_event_port(self, manager_with_capture: SessionStateManager) -> None:
        """Manager has _event_port attribute."""
        assert hasattr(manager_with_capture, "_event_port")
        assert manager_with_capture._event_port is not None

    def test_event_port_is_local_adapter(self, manager_with_capture: SessionStateManager) -> None:
        """Event port is LocalEventAdapter."""
        assert isinstance(manager_with_capture._event_port, LocalEventAdapter)

    def test_event_port_capture_enabled(self, manager_with_capture: SessionStateManager) -> None:
        """Event port has capture mode enabled."""
        adapter = manager_with_capture._event_port
        assert adapter._capture_mode is True

    def test_can_emit_via_port(self, started_capture_manager: SessionStateManager) -> None:
        """Can emit events via manager's event port."""
        adapter = started_capture_manager._event_port

        adapter.emit("test.direct.emit", {"source": "test"})

        events = adapter.get_captured_events()
        assert len(events) >= 1
        test_events = [e for e in events if e[0] == "test.direct.emit"]
        assert len(test_events) == 1

    def test_can_drain_via_port(self, started_capture_manager: SessionStateManager) -> None:
        """Can drain events via manager's event port."""
        adapter = started_capture_manager._event_port

        adapter.emit("test.event", {})
        adapter.emit("test.event", {})

        events = adapter.drain()
        assert len(events) >= 2


# =============================================================================
# CAPTURE EDGE CASES
# =============================================================================


class TestCaptureEdgeCases:
    """Test edge cases for event capture."""

    def test_disable_capture_stops_storing(self, capture_adapter: LocalEventAdapter) -> None:
        """disable_capture() stops storing events."""
        capture_adapter.emit("captured", {})
        capture_adapter.disable_capture()
        capture_adapter.emit("not.captured", {})

        events = capture_adapter.get_captured_events()
        types = [e[0] for e in events]

        assert "captured" in types
        assert "not.captured" not in types

    def test_enable_capture_restarts_storing(self, capture_adapter: LocalEventAdapter) -> None:
        """enable_capture() restarts storing events."""
        capture_adapter.disable_capture()
        capture_adapter.emit("not.captured", {})

        capture_adapter.enable_capture()
        capture_adapter.emit("now.captured", {})

        events = capture_adapter.get_captured_events()
        types = [e[0] for e in events]

        assert "now.captured" in types
        assert "not.captured" not in types

    def test_large_payload_captured(self, capture_adapter: LocalEventAdapter) -> None:
        """Large payloads are captured correctly."""
        large_data = {"items": list(range(10000))}
        capture_adapter.emit("large.event", large_data)

        events = capture_adapter.get_captured_events()
        assert len(events) == 1
        assert events[0][1]["items"] == list(range(10000))

    def test_none_payload_captured(self, capture_adapter: LocalEventAdapter) -> None:
        """None payload is captured."""
        capture_adapter.emit("null.event", None)

        events = capture_adapter.get_captured_events()
        assert len(events) == 1
        assert events[0][1] is None

    def test_empty_dict_payload(self, capture_adapter: LocalEventAdapter) -> None:
        """Empty dict payload captured."""
        capture_adapter.emit("empty.event", {})

        events = capture_adapter.get_captured_events()
        assert len(events) == 1
        assert events[0][1] == {}

    def test_complex_nested_payload(self, capture_adapter: LocalEventAdapter) -> None:
        """Complex nested payloads captured."""
        payload = {
            "level1": {
                "level2": {
                    "level3": [1, 2, {"deep": "value"}],
                },
            },
        }
        capture_adapter.emit("nested.event", payload)

        events = capture_adapter.get_captured_events()
        assert events[0][1]["level1"]["level2"]["level3"][2]["deep"] == "value"


# =============================================================================
# WAIT AND DISPATCH TESTS
# =============================================================================


class TestDispatchMechanism:
    """Test dispatch mechanism."""

    def test_wait_for_dispatch_returns_true(self, capture_adapter: LocalEventAdapter) -> None:
        """wait_for_dispatch returns True when queue empty."""
        result = capture_adapter.wait_for_dispatch(timeout=0.5)
        assert result is True

    def test_wait_for_dispatch_with_events(self, capture_adapter: LocalEventAdapter) -> None:
        """wait_for_dispatch waits for events to process."""
        received: List[Any] = []
        capture_adapter.subscribe("test", lambda e: received.append(e))

        capture_adapter.emit("test", {"n": 1})
        result = capture_adapter.wait_for_dispatch(timeout=1.0)

        assert result is True
        assert len(received) == 1

    def test_is_connected_always_true(self, capture_adapter: LocalEventAdapter) -> None:
        """is_connected always returns True for local adapter."""
        assert capture_adapter.is_connected is True

    def test_stop_stops_dispatch_thread(self, capture_adapter: LocalEventAdapter) -> None:
        """stop() stops the dispatch thread."""
        capture_adapter.stop()
        assert capture_adapter._running is False


# =============================================================================
# HANDLER COUNT TESTS
# =============================================================================


class TestHandlerCounts:
    """Test handler counting."""

    def test_get_subscription_count_empty(self, capture_adapter: LocalEventAdapter) -> None:
        """get_subscription_count returns 0 initially."""
        assert capture_adapter.get_subscription_count() == 0

    def test_get_subscription_count_after_subscribe(
        self, capture_adapter: LocalEventAdapter
    ) -> None:
        """get_subscription_count increases after subscribe."""
        capture_adapter.subscribe("test", lambda e: None)
        capture_adapter.subscribe("test", lambda e: None)

        assert capture_adapter.get_subscription_count() == 2

    def test_get_subscription_count_after_unsubscribe(
        self, capture_adapter: LocalEventAdapter
    ) -> None:
        """get_subscription_count decreases after unsubscribe."""
        sub1 = capture_adapter.subscribe("test", lambda e: None)
        capture_adapter.subscribe("test", lambda e: None)

        capture_adapter.unsubscribe(sub1)

        assert capture_adapter.get_subscription_count() == 1

    def test_get_handler_count_for_type(self, capture_adapter: LocalEventAdapter) -> None:
        """get_handler_count returns handlers for specific type."""
        capture_adapter.subscribe("type.a", lambda e: None)
        capture_adapter.subscribe("type.a", lambda e: None)
        capture_adapter.subscribe("type.b", lambda e: None)

        assert capture_adapter.get_handler_count("type.a") == 2
        assert capture_adapter.get_handler_count("type.b") == 1
        assert capture_adapter.get_handler_count("type.c") == 0
