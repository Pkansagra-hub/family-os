"""
Event Schema Compliance Contract Tests
========================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.4 Contract Tests
ISSUE: 4.4.2

CONTRACTS:
- Event payloads: k1/sessionstate/events.py
- EventType enum: 8 required event types

PURPOSE:
    Validate all 8 event payloads:
    1. Have correct event_type values
    2. Can serialize to dict (for JSON)
    3. Include all required fields
    4. Follow naming conventions

TEST PHILOSOPHY:
    NO MOCKS - Real event dataclass instances only.
    Contract-first validation.

Run with: pytest tests/k1/sessionstate/test_event_schemas.py -v
"""

import pytest

from k1.sessionstate.events import (
    EmergencyActivatedEvent,
    EmergencyLevel,
    EmergencyResolvedEvent,
    EventType,
    EvictionCompletedEvent,
    EvictionTriggeredEvent,
    MutationApprovedEvent,
    MutationRejectedEvent,
    MutationRequestedEvent,
    PressureLevel,
    ReconstructionStartedEvent,
)

# =============================================================================
# EVENT TYPE ENUM TESTS
# =============================================================================


class TestEventTypeEnum:
    """Test EventType enum has all 8 required types."""

    def test_has_8_event_types(self):
        """EventType enum has exactly 8 values."""
        assert len(EventType) == 8

    def test_mutation_requested_value(self):
        """MUTATION_REQUESTED has correct value."""
        assert EventType.MUTATION_REQUESTED.value == "sessionstate.mutation.requested"

    def test_mutation_approved_value(self):
        """MUTATION_APPROVED has correct value."""
        assert EventType.MUTATION_APPROVED.value == "sessionstate.mutation.approved"

    def test_mutation_rejected_value(self):
        """MUTATION_REJECTED has correct value."""
        assert EventType.MUTATION_REJECTED.value == "sessionstate.mutation.rejected"

    def test_eviction_triggered_value(self):
        """EVICTION_TRIGGERED has correct value."""
        assert EventType.EVICTION_TRIGGERED.value == "sessionstate.eviction.triggered"

    def test_eviction_completed_value(self):
        """EVICTION_COMPLETED has correct value."""
        assert EventType.EVICTION_COMPLETED.value == "sessionstate.eviction.completed"

    def test_emergency_activated_value(self):
        """EMERGENCY_ACTIVATED has correct value."""
        assert EventType.EMERGENCY_ACTIVATED.value == "sessionstate.emergency.activated"

    def test_emergency_resolved_value(self):
        """EMERGENCY_RESOLVED has correct value."""
        assert EventType.EMERGENCY_RESOLVED.value == "sessionstate.emergency.resolved"

    def test_reconstruction_started_value(self):
        """RECONSTRUCTION_STARTED has correct value."""
        assert EventType.RECONSTRUCTION_STARTED.value == "sessionstate.reconstruction.started"

    def test_all_values_follow_naming_convention(self):
        """All event types follow sessionstate.{category}.{action} convention."""
        for event_type in EventType:
            value = event_type.value
            assert value.startswith(
                "sessionstate."
            ), f"{event_type} should start with 'sessionstate.'"
            parts = value.split(".")
            assert len(parts) == 3, f"{event_type} should have 3 parts: {value}"


# =============================================================================
# BASE EVENT TESTS
# =============================================================================


class TestBaseEvent:
    """Test BaseEvent has all required fields."""

    def test_has_event_id(self):
        """BaseEvent has event_id field with auto-generated UUID."""
        event = MutationRequestedEvent()
        assert event.event_id is not None
        assert len(event.event_id) == 36  # UUID length

    def test_has_event_type(self):
        """BaseEvent has event_type field."""
        event = MutationRequestedEvent()
        assert event.event_type == EventType.MUTATION_REQUESTED.value

    def test_has_session_id(self):
        """BaseEvent has session_id field."""
        event = MutationRequestedEvent(session_id="test-session")
        assert event.session_id == "test-session"

    def test_has_cognitive_trace_id(self):
        """BaseEvent has cognitive_trace_id field."""
        event = MutationRequestedEvent(cognitive_trace_id="trace-123")
        assert event.cognitive_trace_id == "trace-123"

    def test_has_timestamp_ms(self):
        """BaseEvent has timestamp_ms field with auto-generated value."""
        event = MutationRequestedEvent()
        assert event.timestamp_ms > 0

    def test_to_dict_includes_base_fields(self):
        """to_dict() includes all base fields."""
        event = MutationRequestedEvent(
            session_id="sess-1",
            cognitive_trace_id="trace-1",
        )
        d = event.to_dict()
        assert "event_id" in d
        assert "event_type" in d
        assert "session_id" in d
        assert "cognitive_trace_id" in d
        assert "timestamp_ms" in d


# =============================================================================
# MUTATION EVENTS
# =============================================================================


class TestMutationRequestedEvent:
    """Test MutationRequestedEvent payload."""

    def test_event_type_is_correct(self):
        """event_type is sessionstate.mutation.requested."""
        event = MutationRequestedEvent()
        assert event.event_type == "sessionstate.mutation.requested"

    def test_has_section_field(self):
        """Has section field."""
        event = MutationRequestedEvent(section="history_active")
        assert event.section == "history_active"

    def test_has_operation_field(self):
        """Has operation field."""
        event = MutationRequestedEvent(operation="append")
        assert event.operation == "append"

    def test_has_estimated_bytes_field(self):
        """Has estimated_bytes field."""
        event = MutationRequestedEvent(estimated_bytes=1024)
        assert event.estimated_bytes == 1024

    def test_has_writer_id_field(self):
        """Has writer_id field."""
        event = MutationRequestedEvent(writer_id="concierge")
        assert event.writer_id == "concierge"

    def test_to_dict_includes_all_fields(self):
        """to_dict() includes all mutation request fields."""
        event = MutationRequestedEvent(
            session_id="sess-1",
            section="beliefs_active",
            operation="set",
            estimated_bytes=512,
            writer_id="concierge",
        )
        d = event.to_dict()
        assert d["section"] == "beliefs_active"
        assert d["operation"] == "set"
        assert d["estimated_bytes"] == 512
        assert d["writer_id"] == "concierge"


class TestMutationApprovedEvent:
    """Test MutationApprovedEvent payload."""

    def test_event_type_is_correct(self):
        """event_type is sessionstate.mutation.approved."""
        event = MutationApprovedEvent()
        assert event.event_type == "sessionstate.mutation.approved"

    def test_has_previous_size_bytes(self):
        """Has previous_size_bytes field."""
        event = MutationApprovedEvent(previous_size_bytes=1000)
        assert event.previous_size_bytes == 1000

    def test_has_new_size_bytes(self):
        """Has new_size_bytes field."""
        event = MutationApprovedEvent(new_size_bytes=1500)
        assert event.new_size_bytes == 1500

    def test_has_tier_utilization_pct(self):
        """Has tier_utilization_pct field."""
        event = MutationApprovedEvent(tier_utilization_pct=45.5)
        assert event.tier_utilization_pct == 45.5

    def test_has_total_utilization_pct(self):
        """Has total_utilization_pct field."""
        event = MutationApprovedEvent(total_utilization_pct=23.5)
        assert event.total_utilization_pct == 23.5

    def test_to_dict_includes_all_fields(self):
        """to_dict() includes all mutation approved fields."""
        event = MutationApprovedEvent(
            section="history_active",
            operation="append",
            previous_size_bytes=1000,
            new_size_bytes=1500,
            tier_utilization_pct=45.5,
            total_utilization_pct=23.5,
        )
        d = event.to_dict()
        assert d["previous_size_bytes"] == 1000
        assert d["new_size_bytes"] == 1500
        assert d["tier_utilization_pct"] == 45.5
        assert d["total_utilization_pct"] == 23.5


class TestMutationRejectedEvent:
    """Test MutationRejectedEvent payload."""

    def test_event_type_is_correct(self):
        """event_type is sessionstate.mutation.rejected."""
        event = MutationRejectedEvent()
        assert event.event_type == "sessionstate.mutation.rejected"

    def test_has_reason_field(self):
        """Has reason field."""
        event = MutationRejectedEvent(reason="budget_exceeded")
        assert event.reason == "budget_exceeded"

    def test_has_section_available_bytes(self):
        """Has section_available_bytes field."""
        event = MutationRejectedEvent(section_available_bytes=100)
        assert event.section_available_bytes == 100

    def test_has_tier_available_bytes(self):
        """Has tier_available_bytes field."""
        event = MutationRejectedEvent(tier_available_bytes=500)
        assert event.tier_available_bytes == 500

    def test_has_total_available_bytes(self):
        """Has total_available_bytes field."""
        event = MutationRejectedEvent(total_available_bytes=1000)
        assert event.total_available_bytes == 1000


# =============================================================================
# EVICTION EVENTS
# =============================================================================


class TestEvictionTriggeredEvent:
    """Test EvictionTriggeredEvent payload."""

    def test_event_type_is_correct(self):
        """event_type is sessionstate.eviction.triggered."""
        event = EvictionTriggeredEvent()
        assert event.event_type == "sessionstate.eviction.triggered"

    def test_has_tier_field(self):
        """Has tier field defaulting to 'warm'."""
        event = EvictionTriggeredEvent()
        assert event.tier == "warm"

    def test_has_target_reduction_bytes(self):
        """Has target_reduction_bytes field."""
        event = EvictionTriggeredEvent(target_reduction_bytes=5000)
        assert event.target_reduction_bytes == 5000

    def test_has_pressure_level(self):
        """Has pressure_level field."""
        event = EvictionTriggeredEvent(pressure_level=PressureLevel.CRITICAL.value)
        assert event.pressure_level == "critical"

    def test_has_candidates_list(self):
        """Has candidates list field."""
        event = EvictionTriggeredEvent(candidates=["telemetry", "beliefs_history"])
        assert event.candidates == ["telemetry", "beliefs_history"]


class TestEvictionCompletedEvent:
    """Test EvictionCompletedEvent payload."""

    def test_event_type_is_correct(self):
        """event_type is sessionstate.eviction.completed."""
        event = EvictionCompletedEvent()
        assert event.event_type == "sessionstate.eviction.completed"

    def test_has_sections_evicted(self):
        """Has sections_evicted list field."""
        event = EvictionCompletedEvent(sections_evicted=["telemetry"])
        assert event.sections_evicted == ["telemetry"]

    def test_has_bytes_freed(self):
        """Has bytes_freed field."""
        event = EvictionCompletedEvent(bytes_freed=4096)
        assert event.bytes_freed == 4096

    def test_has_bytes_archived(self):
        """Has bytes_archived field."""
        event = EvictionCompletedEvent(bytes_archived=3000)
        assert event.bytes_archived == 3000

    def test_has_new_pressure_level(self):
        """Has new_pressure_level field."""
        event = EvictionCompletedEvent(new_pressure_level=PressureLevel.NORMAL.value)
        assert event.new_pressure_level == "normal"

    def test_has_duration_ms(self):
        """Has duration_ms field."""
        event = EvictionCompletedEvent(duration_ms=15.5)
        assert event.duration_ms == 15.5


# =============================================================================
# EMERGENCY EVENTS
# =============================================================================


class TestEmergencyActivatedEvent:
    """Test EmergencyActivatedEvent payload."""

    def test_event_type_is_correct(self):
        """event_type is sessionstate.emergency.activated."""
        event = EmergencyActivatedEvent()
        assert event.event_type == "sessionstate.emergency.activated"

    def test_has_level_field(self):
        """Has level field (warning or critical)."""
        event = EmergencyActivatedEvent(level=EmergencyLevel.CRITICAL.value)
        assert event.level == "critical"

    def test_has_total_size_bytes(self):
        """Has total_size_bytes field."""
        event = EmergencyActivatedEvent(total_size_bytes=90000)
        assert event.total_size_bytes == 90000

    def test_has_hot_size_bytes(self):
        """Has hot_size_bytes field."""
        event = EmergencyActivatedEvent(hot_size_bytes=45000)
        assert event.hot_size_bytes == 45000

    def test_has_warm_size_bytes(self):
        """Has warm_size_bytes field."""
        event = EmergencyActivatedEvent(warm_size_bytes=45000)
        assert event.warm_size_bytes == 45000

    def test_has_utilization_pct(self):
        """Has utilization_pct field."""
        event = EmergencyActivatedEvent(utilization_pct=95.5)
        assert event.utilization_pct == 95.5

    def test_has_writes_blocked(self):
        """Has writes_blocked field."""
        event = EmergencyActivatedEvent(writes_blocked=True)
        assert event.writes_blocked is True


class TestEmergencyResolvedEvent:
    """Test EmergencyResolvedEvent payload."""

    def test_event_type_is_correct(self):
        """event_type is sessionstate.emergency.resolved."""
        event = EmergencyResolvedEvent()
        assert event.event_type == "sessionstate.emergency.resolved"

    def test_has_previous_level(self):
        """Has previous_level field."""
        event = EmergencyResolvedEvent(previous_level=EmergencyLevel.CRITICAL.value)
        assert event.previous_level == "critical"

    def test_has_resolution_method(self):
        """Has resolution_method field."""
        event = EmergencyResolvedEvent(resolution_method="eviction")
        assert event.resolution_method == "eviction"

    def test_has_new_utilization_pct(self):
        """Has new_utilization_pct field."""
        event = EmergencyResolvedEvent(new_utilization_pct=75.0)
        assert event.new_utilization_pct == 75.0


# =============================================================================
# RECONSTRUCTION EVENTS
# =============================================================================


class TestReconstructionStartedEvent:
    """Test ReconstructionStartedEvent payload."""

    def test_event_type_is_correct(self):
        """event_type is sessionstate.reconstruction.started."""
        event = ReconstructionStartedEvent()
        assert event.event_type == "sessionstate.reconstruction.started"

    def test_has_source_field(self):
        """Has source field (local_cold or k0)."""
        event = ReconstructionStartedEvent(source="local_cold")
        assert event.source == "local_cold"

    def test_has_sections_requested(self):
        """Has sections_requested list field."""
        event = ReconstructionStartedEvent(sections_requested=["beliefs_active", "history_active"])
        assert event.sections_requested == ["beliefs_active", "history_active"]

    def test_has_expected_duration_ms(self):
        """Has expected_duration_ms field."""
        event = ReconstructionStartedEvent(expected_duration_ms=50.0)
        assert event.expected_duration_ms == 50.0


# =============================================================================
# ALL EVENTS SERIALIZATION
# =============================================================================


class TestAllEventsSerialization:
    """Test all 8 event types can serialize to dict."""

    @pytest.fixture
    def all_events(self):
        """Create instances of all 8 event types."""
        return [
            MutationRequestedEvent(session_id="s1", section="history_active"),
            MutationApprovedEvent(session_id="s1", section="history_active"),
            MutationRejectedEvent(session_id="s1", section="history_active"),
            EvictionTriggeredEvent(session_id="s1"),
            EvictionCompletedEvent(session_id="s1"),
            EmergencyActivatedEvent(session_id="s1"),
            EmergencyResolvedEvent(session_id="s1"),
            ReconstructionStartedEvent(session_id="s1"),
        ]

    def test_all_events_have_to_dict(self, all_events):
        """All 8 event types have to_dict() method."""
        for event in all_events:
            assert hasattr(event, "to_dict")
            d = event.to_dict()
            assert isinstance(d, dict)

    def test_all_dicts_have_required_fields(self, all_events):
        """All event dicts have required base fields."""
        required_fields = ["event_id", "event_type", "session_id", "timestamp_ms"]
        for event in all_events:
            d = event.to_dict()
            for field in required_fields:
                assert field in d, f"{type(event).__name__} missing {field}"

    def test_all_event_types_represented(self, all_events):
        """All 8 EventType values are represented."""
        event_types = {e.event_type for e in all_events}
        assert len(event_types) == 8

    def test_dicts_are_json_serializable(self, all_events):
        """All event dicts can be serialized to JSON."""
        import json

        for event in all_events:
            d = event.to_dict()
            # Should not raise
            json_str = json.dumps(d)
            assert len(json_str) > 0

    def test_event_type_matches_class(self, all_events):
        """Event type matches the expected class."""
        type_to_class = {
            "sessionstate.mutation.requested": MutationRequestedEvent,
            "sessionstate.mutation.approved": MutationApprovedEvent,
            "sessionstate.mutation.rejected": MutationRejectedEvent,
            "sessionstate.eviction.triggered": EvictionTriggeredEvent,
            "sessionstate.eviction.completed": EvictionCompletedEvent,
            "sessionstate.emergency.activated": EmergencyActivatedEvent,
            "sessionstate.emergency.resolved": EmergencyResolvedEvent,
            "sessionstate.reconstruction.started": ReconstructionStartedEvent,
        }
        for event in all_events:
            expected_class = type_to_class[event.event_type]
            assert isinstance(event, expected_class)


# =============================================================================
# PRESSURE AND EMERGENCY LEVEL ENUMS
# =============================================================================


class TestPressureLevelEnum:
    """Test PressureLevel enum."""

    def test_has_normal(self):
        """Has NORMAL level."""
        assert PressureLevel.NORMAL.value == "normal"

    def test_has_elevated(self):
        """Has ELEVATED level."""
        assert PressureLevel.ELEVATED.value == "elevated"

    def test_has_critical(self):
        """Has CRITICAL level."""
        assert PressureLevel.CRITICAL.value == "critical"


class TestEmergencyLevelEnum:
    """Test EmergencyLevel enum."""

    def test_has_warning(self):
        """Has WARNING level."""
        assert EmergencyLevel.WARNING.value == "warning"

    def test_has_critical(self):
        """Has CRITICAL level."""
        assert EmergencyLevel.CRITICAL.value == "critical"
