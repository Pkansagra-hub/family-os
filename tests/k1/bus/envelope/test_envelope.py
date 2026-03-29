"""
Tests for k1.bus.envelope -- Envelope, Priority, DeliveryMode.

Coverage targets:
    - Envelope construction with defaults
    - Envelope construction with all fields
    - Frozen immutability
    - Field validation (bad types, out-of-range values)
    - to_bytes / from_bytes round-trip
    - from_bytes error paths (truncated, malformed)
    - with_bus_fields builder
    - Priority enum weights
    - DeliveryMode enum values
    - payload_len property
    - is_root property
"""

import pytest

from k1.bus.envelope import DeliveryMode, Envelope, Priority

# ===================================================================
# Priority enum
# ===================================================================


class TestPriority:
    """Priority IntEnum tests."""

    def test_values(self) -> None:
        assert Priority.URGENT == 0
        assert Priority.REALTIME == 1
        assert Priority.INTERACTIVE == 2
        assert Priority.BACKGROUND == 3

    def test_weights(self) -> None:
        assert Priority.URGENT.weight == 4
        assert Priority.REALTIME.weight == 3
        assert Priority.INTERACTIVE.weight == 2
        assert Priority.BACKGROUND.weight == 1

    def test_ordering(self) -> None:
        assert Priority.URGENT < Priority.BACKGROUND
        assert sorted(Priority) == [
            Priority.URGENT,
            Priority.REALTIME,
            Priority.INTERACTIVE,
            Priority.BACKGROUND,
        ]


# ===================================================================
# DeliveryMode enum
# ===================================================================


class TestDeliveryMode:
    """DeliveryMode IntEnum tests."""

    def test_values(self) -> None:
        assert DeliveryMode.STRICT == 0
        assert DeliveryMode.RELAXED == 1
        assert DeliveryMode.BEST_EFFORT == 2

    def test_is_intenum(self) -> None:
        assert isinstance(DeliveryMode.STRICT, int)


# ===================================================================
# Envelope construction
# ===================================================================


class TestEnvelopeConstruction:
    """Envelope creation and defaults."""

    def test_defaults(self) -> None:
        env = Envelope()
        assert env.topic == ""
        assert env.priority == Priority.INTERACTIVE
        assert env.envelope_id == 0
        assert env.sequence == 0
        assert env.cognitive_trace_id == ""
        assert env.session_id == ""
        assert env.request_id == ""
        assert env.parent_id == 0
        assert env.created_ns == 0
        assert env.payload == b""

    def test_all_fields(self) -> None:
        payload = b"\x01\x02\x03"
        env = Envelope(
            topic="k1.test.event.v1",
            priority=Priority.URGENT,
            envelope_id=42,
            sequence=7,
            cognitive_trace_id="trace-abc",
            session_id="sess-123",
            request_id="req-456",
            parent_id=41,
            created_ns=1_000_000,
            payload=payload,
        )
        assert env.topic == "k1.test.event.v1"
        assert env.priority == Priority.URGENT
        assert env.envelope_id == 42
        assert env.sequence == 7
        assert env.cognitive_trace_id == "trace-abc"
        assert env.session_id == "sess-123"
        assert env.request_id == "req-456"
        assert env.parent_id == 41
        assert env.created_ns == 1_000_000
        assert env.payload == payload

    def test_frozen_immutability(self) -> None:
        env = Envelope(topic="k1.test")
        with pytest.raises(AttributeError):
            env.topic = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            env.payload = b"nope"  # type: ignore[misc]


# ===================================================================
# Envelope validation
# ===================================================================


class TestEnvelopeValidation:
    """Envelope __post_init__ validation."""

    def test_bad_topic_type(self) -> None:
        with pytest.raises(TypeError, match="topic must be str"):
            Envelope(topic=123)  # type: ignore[arg-type]

    def test_bad_payload_type(self) -> None:
        with pytest.raises(TypeError, match="payload must be bytes"):
            Envelope(payload="not bytes")  # type: ignore[arg-type]

    def test_bad_priority_value(self) -> None:
        with pytest.raises(ValueError, match="priority must be 0-3"):
            Envelope(priority=99)

    def test_negative_envelope_id(self) -> None:
        with pytest.raises(ValueError, match="envelope_id must be >= 0"):
            Envelope(envelope_id=-1)

    def test_negative_sequence(self) -> None:
        with pytest.raises(ValueError, match="sequence must be >= 0"):
            Envelope(sequence=-1)

    def test_negative_parent_id(self) -> None:
        with pytest.raises(ValueError, match="parent_id must be >= 0"):
            Envelope(parent_id=-1)


# ===================================================================
# Envelope properties
# ===================================================================


class TestEnvelopeProperties:
    """Envelope computed properties."""

    def test_payload_len(self) -> None:
        env = Envelope(payload=b"hello")
        assert env.payload_len == 5

    def test_payload_len_empty(self) -> None:
        env = Envelope()
        assert env.payload_len == 0

    def test_priority_enum(self) -> None:
        env = Envelope(priority=Priority.REALTIME)
        assert env.priority_enum is Priority.REALTIME

    def test_is_root_true(self) -> None:
        env = Envelope(parent_id=0)
        assert env.is_root is True

    def test_is_root_false(self) -> None:
        env = Envelope(parent_id=42)
        assert env.is_root is False


# ===================================================================
# Envelope serialization round-trip
# ===================================================================


class TestEnvelopeSerialization:
    """to_bytes / from_bytes round-trip tests."""

    def test_round_trip_defaults(self) -> None:
        original = Envelope()
        data = original.to_bytes()
        restored = Envelope.from_bytes(data)
        assert restored.topic == original.topic
        assert restored.priority == original.priority
        assert restored.envelope_id == original.envelope_id
        assert restored.sequence == original.sequence
        assert restored.cognitive_trace_id == original.cognitive_trace_id
        assert restored.session_id == original.session_id
        assert restored.request_id == original.request_id
        assert restored.parent_id == original.parent_id
        assert restored.created_ns == original.created_ns
        assert restored.payload == original.payload

    def test_round_trip_full(self) -> None:
        payload = b"\xff\x00\xab" * 100
        original = Envelope(
            topic="k1.lifecycle.agent_started.v1",
            priority=Priority.URGENT,
            envelope_id=999,
            sequence=42,
            cognitive_trace_id="cog-trace-xyz",
            session_id="sess-000",
            request_id="req-111",
            parent_id=998,
            created_ns=123456789,
            payload=payload,
        )
        data = original.to_bytes()
        restored = Envelope.from_bytes(data)
        assert restored.topic == original.topic
        assert restored.priority == original.priority
        assert restored.envelope_id == original.envelope_id
        assert restored.sequence == original.sequence
        assert restored.cognitive_trace_id == original.cognitive_trace_id
        assert restored.session_id == original.session_id
        assert restored.request_id == original.request_id
        assert restored.parent_id == original.parent_id
        assert restored.created_ns == original.created_ns
        assert restored.payload == original.payload

    def test_round_trip_empty_payload(self) -> None:
        original = Envelope(topic="k1.test", payload=b"")
        restored = Envelope.from_bytes(original.to_bytes())
        assert restored.payload == b""

    def test_round_trip_large_payload(self) -> None:
        payload = bytes(range(256)) * 1000  # 256KB
        original = Envelope(topic="k1.bulk", payload=payload)
        restored = Envelope.from_bytes(original.to_bytes())
        assert restored.payload == payload

    def test_round_trip_unicode_topic(self) -> None:
        original = Envelope(topic="k1.test.unicode_payload", payload="hello".encode("utf-8"))
        restored = Envelope.from_bytes(original.to_bytes())
        assert restored.topic == original.topic

    def test_from_bytes_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            Envelope.from_bytes(b"\x00\x01")

    def test_from_bytes_truncated_header(self) -> None:
        # Header claims 100 bytes but we only give 10
        import struct

        data = struct.pack(">I", 100) + b"x" * 10
        with pytest.raises(ValueError, match="truncated"):
            Envelope.from_bytes(data)

    def test_from_bytes_malformed_json(self) -> None:
        import struct

        bad_json = b"not-json"
        data = struct.pack(">I", len(bad_json)) + bad_json
        with pytest.raises(ValueError, match="Malformed"):
            Envelope.from_bytes(data)


# ===================================================================
# Envelope builder helpers
# ===================================================================


class TestEnvelopeBuilder:
    """with_bus_fields builder method."""

    def test_with_bus_fields(self) -> None:
        original = Envelope(
            topic="k1.test",
            priority=Priority.REALTIME,
            cognitive_trace_id="trace-1",
            session_id="sess-1",
            request_id="req-1",
            parent_id=10,
            payload=b"data",
        )
        stamped = original.with_bus_fields(
            envelope_id=100,
            sequence=5,
            created_ns=999,
        )
        # Bus-assigned fields updated
        assert stamped.envelope_id == 100
        assert stamped.sequence == 5
        assert stamped.created_ns == 999
        # Publisher fields preserved
        assert stamped.topic == "k1.test"
        assert stamped.priority == Priority.REALTIME
        assert stamped.cognitive_trace_id == "trace-1"
        assert stamped.session_id == "sess-1"
        assert stamped.request_id == "req-1"
        assert stamped.parent_id == 10
        assert stamped.payload == b"data"

    def test_with_bus_fields_does_not_mutate_original(self) -> None:
        original = Envelope(topic="k1.test")
        _ = original.with_bus_fields(envelope_id=1, sequence=1, created_ns=1)
        assert original.envelope_id == 0
        assert original.sequence == 0
        assert original.created_ns == 0
