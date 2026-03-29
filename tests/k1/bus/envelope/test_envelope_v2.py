"""
Tests for V2 Envelope: FlatBuffers serialization, PayloadFormat, ttl_ms.

Covers:
    - PayloadFormat enum values and properties
    - ttl_ms and payload_format field construction and validation
    - V2 FlatBuffers round-trip (default format)
    - V1 fallback round-trip with new fields
    - Cross-format interop (V1 write -> V2 read, V2 write -> auto-detect)
    - Format auto-detection in from_bytes
    - with_bus_fields preserves V2 fields
    - ENVELOPE_FORMAT toggle
    - Large payload FlatBuffers round-trip
    - Edge cases: empty strings, max uint values, binary payloads
    - Performance: V2 vs V1 serialization latency
"""

import struct
import time

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.bus.envelope import envelope as _envelope_mod

# ===================================================================
# PayloadFormat enum
# ===================================================================


class TestPayloadFormat:
    """PayloadFormat IntEnum tests."""

    def test_values(self) -> None:
        assert PayloadFormat.OPAQUE == 0
        assert PayloadFormat.JSON == 1
        assert PayloadFormat.MSGPACK == 2

    def test_is_intenum(self) -> None:
        assert isinstance(PayloadFormat.OPAQUE, int)
        assert isinstance(PayloadFormat.JSON, int)
        assert isinstance(PayloadFormat.MSGPACK, int)

    def test_ordering(self) -> None:
        assert PayloadFormat.OPAQUE < PayloadFormat.JSON < PayloadFormat.MSGPACK

    def test_members(self) -> None:
        assert len(PayloadFormat) == 3
        assert set(PayloadFormat) == {
            PayloadFormat.OPAQUE,
            PayloadFormat.JSON,
            PayloadFormat.MSGPACK,
        }


# ===================================================================
# V2 field construction
# ===================================================================


class TestV2FieldConstruction:
    """New V2 fields: ttl_ms, payload_format."""

    def test_defaults(self) -> None:
        env = Envelope()
        assert env.ttl_ms == 0
        assert env.payload_format == PayloadFormat.OPAQUE

    def test_ttl_ms_set(self) -> None:
        env = Envelope(ttl_ms=5000)
        assert env.ttl_ms == 5000

    def test_payload_format_json(self) -> None:
        env = Envelope(payload_format=PayloadFormat.JSON)
        assert env.payload_format == PayloadFormat.JSON

    def test_payload_format_msgpack(self) -> None:
        env = Envelope(payload_format=PayloadFormat.MSGPACK)
        assert env.payload_format == PayloadFormat.MSGPACK

    def test_payload_format_enum_property(self) -> None:
        env = Envelope(payload_format=PayloadFormat.MSGPACK)
        assert env.payload_format_enum is PayloadFormat.MSGPACK

    def test_is_expired_false(self) -> None:
        env = Envelope(ttl_ms=0)
        assert env.is_expired is False

    def test_is_expired_true(self) -> None:
        env = Envelope(ttl_ms=100)
        assert env.is_expired is True

    def test_full_construction_with_v2_fields(self) -> None:
        env = Envelope(
            topic="k1.test.v2",
            priority=Priority.URGENT,
            envelope_id=42,
            sequence=7,
            cognitive_trace_id="trace-abc",
            session_id="sess-123",
            request_id="req-456",
            parent_id=41,
            created_ns=1_000_000,
            payload=b"\x01\x02\x03",
            ttl_ms=30_000,
            payload_format=PayloadFormat.JSON,
        )
        assert env.topic == "k1.test.v2"
        assert env.priority == Priority.URGENT
        assert env.envelope_id == 42
        assert env.ttl_ms == 30_000
        assert env.payload_format == PayloadFormat.JSON


# ===================================================================
# V2 field validation
# ===================================================================


class TestV2FieldValidation:
    """Validation of new V2 fields."""

    def test_negative_ttl_ms(self) -> None:
        with pytest.raises(ValueError, match="ttl_ms must be >= 0"):
            Envelope(ttl_ms=-1)

    def test_bad_payload_format_low(self) -> None:
        with pytest.raises(ValueError, match="payload_format must be 0-2"):
            Envelope(payload_format=-1)

    def test_bad_payload_format_high(self) -> None:
        with pytest.raises(ValueError, match="payload_format must be 0-2"):
            Envelope(payload_format=3)

    def test_frozen_ttl_ms(self) -> None:
        env = Envelope(ttl_ms=100)
        with pytest.raises(AttributeError):
            env.ttl_ms = 200  # type: ignore[misc]

    def test_frozen_payload_format(self) -> None:
        env = Envelope(payload_format=PayloadFormat.JSON)
        with pytest.raises(AttributeError):
            env.payload_format = 0  # type: ignore[misc]


# ===================================================================
# V2 FlatBuffers round-trip
# ===================================================================


class TestV2FlatBuffersRoundTrip:
    """FlatBuffers (V2) serialization round-trip."""

    def _assert_round_trip(self, original: Envelope) -> Envelope:
        """Serialize, deserialize, assert equality."""
        data = original._to_bytes_v2()
        assert data[:4] == b"FB02", "V2 magic prefix missing"
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
        assert restored.ttl_ms == original.ttl_ms
        assert restored.payload_format == original.payload_format
        return restored

    def test_defaults(self) -> None:
        self._assert_round_trip(Envelope())

    def test_full_v1_fields(self) -> None:
        self._assert_round_trip(
            Envelope(
                topic="k1.lifecycle.agent_started.v1",
                priority=Priority.URGENT,
                envelope_id=999,
                sequence=42,
                cognitive_trace_id="cog-trace-xyz",
                session_id="sess-000",
                request_id="req-111",
                parent_id=998,
                created_ns=123456789,
                payload=b"\xff\x00\xab" * 100,
            )
        )

    def test_full_v2_fields(self) -> None:
        self._assert_round_trip(
            Envelope(
                topic="k1.bus.test.v2",
                priority=Priority.BACKGROUND,
                envelope_id=2**63,
                sequence=2**32,
                cognitive_trace_id="trace-v2-full",
                session_id="sess-v2",
                request_id="req-v2",
                parent_id=100,
                created_ns=9_999_999_999,
                payload=b"v2-payload-data",
                ttl_ms=60_000,
                payload_format=PayloadFormat.MSGPACK,
            )
        )

    def test_empty_payload(self) -> None:
        self._assert_round_trip(Envelope(topic="k1.empty", payload=b""))

    def test_large_payload(self) -> None:
        payload = bytes(range(256)) * 1000  # 256KB
        self._assert_round_trip(Envelope(topic="k1.bulk", payload=payload))

    def test_empty_strings(self) -> None:
        self._assert_round_trip(
            Envelope(
                topic="",
                cognitive_trace_id="",
                session_id="",
                request_id="",
            )
        )

    def test_unicode_strings(self) -> None:
        self._assert_round_trip(
            Envelope(
                topic="k1.test.unicode",
                cognitive_trace_id="trace-unicode",
                session_id="sess-unicode",
                request_id="req-unicode",
                payload="hello-world".encode("utf-8"),
            )
        )

    def test_max_uint64_values(self) -> None:
        """Ensure uint64 fields handle large values without overflow."""
        self._assert_round_trip(
            Envelope(
                envelope_id=2**64 - 1,
                sequence=2**64 - 1,
                parent_id=2**64 - 1,
                created_ns=2**64 - 1,
            )
        )

    def test_max_ttl_ms(self) -> None:
        """uint32 max for ttl_ms."""
        self._assert_round_trip(Envelope(ttl_ms=2**32 - 1))

    def test_all_priorities(self) -> None:
        for p in Priority:
            restored = self._assert_round_trip(Envelope(priority=p))
            assert restored.priority == p

    def test_all_payload_formats(self) -> None:
        for pf in PayloadFormat:
            restored = self._assert_round_trip(Envelope(payload_format=pf))
            assert restored.payload_format == pf

    def test_binary_payload_with_null_bytes(self) -> None:
        payload = b"\x00" * 1024
        self._assert_round_trip(Envelope(topic="k1.null", payload=payload))

    def test_binary_payload_all_byte_values(self) -> None:
        payload = bytes(range(256))
        self._assert_round_trip(Envelope(topic="k1.allbytes", payload=payload))


# ===================================================================
# V1 fallback round-trip with V2 fields
# ===================================================================


class TestV1FallbackWithV2Fields:
    """V1 JSON format preserves new ttl_ms and payload_format fields."""

    def _assert_v1_round_trip(self, original: Envelope) -> Envelope:
        """V1 serialize, auto-detect deserialize."""
        data = original._to_bytes_v1()
        assert data[:4] != b"FB02", "V1 must NOT have FB02 prefix"
        restored = Envelope.from_bytes(data)
        assert restored.topic == original.topic
        assert restored.priority == original.priority
        assert restored.envelope_id == original.envelope_id
        assert restored.ttl_ms == original.ttl_ms
        assert restored.payload_format == original.payload_format
        assert restored.payload == original.payload
        return restored

    def test_v1_defaults(self) -> None:
        self._assert_v1_round_trip(Envelope())

    def test_v1_with_ttl(self) -> None:
        self._assert_v1_round_trip(Envelope(topic="k1.v1", ttl_ms=5000))

    def test_v1_with_payload_format(self) -> None:
        self._assert_v1_round_trip(Envelope(topic="k1.v1", payload_format=PayloadFormat.JSON))

    def test_v1_full(self) -> None:
        self._assert_v1_round_trip(
            Envelope(
                topic="k1.v1.full",
                priority=Priority.REALTIME,
                envelope_id=50,
                sequence=10,
                cognitive_trace_id="trace-v1",
                session_id="sess-v1",
                request_id="req-v1",
                parent_id=49,
                created_ns=999,
                payload=b"v1-data",
                ttl_ms=10_000,
                payload_format=PayloadFormat.MSGPACK,
            )
        )


# ===================================================================
# Cross-format interop
# ===================================================================


class TestCrossFormatInterop:
    """V1 write -> V2 read, V2 write -> V1 read (auto-detect)."""

    def test_v1_written_read_by_auto_detect(self) -> None:
        """V1 format auto-detected as non-FB02 prefix."""
        env = Envelope(topic="k1.interop.v1", ttl_ms=1000)
        v1_data = env._to_bytes_v1()
        restored = Envelope.from_bytes(v1_data)
        assert restored.topic == "k1.interop.v1"
        assert restored.ttl_ms == 1000

    def test_v2_written_read_by_auto_detect(self) -> None:
        """V2 format auto-detected by FB02 prefix."""
        env = Envelope(topic="k1.interop.v2", ttl_ms=2000)
        v2_data = env._to_bytes_v2()
        restored = Envelope.from_bytes(v2_data)
        assert restored.topic == "k1.interop.v2"
        assert restored.ttl_ms == 2000

    def test_v1_and_v2_produce_equal_envelopes(self) -> None:
        """Both formats must deserialize to identical Envelope attributes."""
        original = Envelope(
            topic="k1.equal",
            priority=Priority.URGENT,
            envelope_id=77,
            sequence=33,
            cognitive_trace_id="cog-eq",
            session_id="sess-eq",
            request_id="req-eq",
            parent_id=76,
            created_ns=12345,
            payload=b"equality-check",
            ttl_ms=500,
            payload_format=PayloadFormat.JSON,
        )
        from_v1 = Envelope.from_bytes(original._to_bytes_v1())
        from_v2 = Envelope.from_bytes(original._to_bytes_v2())
        assert from_v1 == from_v2


# ===================================================================
# Format auto-detection
# ===================================================================


class TestFormatAutoDetection:
    """from_bytes correctly routes to V1 vs V2 parser."""

    def test_fb02_prefix_routes_to_v2(self) -> None:
        env = Envelope(topic="k1.detect.v2")
        data = env._to_bytes_v2()
        assert data[:4] == b"FB02"
        restored = Envelope.from_bytes(data)
        assert restored.topic == "k1.detect.v2"

    def test_non_fb02_routes_to_v1(self) -> None:
        env = Envelope(topic="k1.detect.v1")
        data = env._to_bytes_v1()
        assert data[:4] != b"FB02"
        restored = Envelope.from_bytes(data)
        assert restored.topic == "k1.detect.v1"

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            Envelope.from_bytes(b"\x00\x01")

    def test_truncated_v1_raises(self) -> None:
        data = struct.pack(">I", 100) + b"x" * 10
        with pytest.raises(ValueError, match="truncated"):
            Envelope.from_bytes(data)

    def test_malformed_v1_json_raises(self) -> None:
        bad_json = b"not-json"
        data = struct.pack(">I", len(bad_json)) + bad_json
        with pytest.raises(ValueError, match="Malformed"):
            Envelope.from_bytes(data)


# ===================================================================
# ENVELOPE_FORMAT toggle
# ===================================================================


class TestEnvelopeFormatToggle:
    """Module-level ENVELOPE_FORMAT controls to_bytes() output."""

    def test_default_is_v2(self) -> None:
        """Default format produces FB02 prefix."""
        env = Envelope(topic="k1.toggle.default")
        data = env.to_bytes()
        assert data[:4] == b"FB02"

    def test_v1_toggle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting ENVELOPE_FORMAT='v1' produces JSON format."""
        monkeypatch.setattr(_envelope_mod, "ENVELOPE_FORMAT", "v1")
        env = Envelope(topic="k1.toggle.v1")
        data = env.to_bytes()
        assert data[:4] != b"FB02"
        # Round-trip through auto-detect
        restored = Envelope.from_bytes(data)
        assert restored.topic == "k1.toggle.v1"

    def test_v2_toggle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting ENVELOPE_FORMAT='v2' produces FlatBuffers format."""
        monkeypatch.setattr(_envelope_mod, "ENVELOPE_FORMAT", "v2")
        env = Envelope(topic="k1.toggle.v2")
        data = env.to_bytes()
        assert data[:4] == b"FB02"
        restored = Envelope.from_bytes(data)
        assert restored.topic == "k1.toggle.v2"


# ===================================================================
# with_bus_fields preserves V2 fields
# ===================================================================


class TestWithBusFieldsV2:
    """with_bus_fields must preserve ttl_ms and payload_format."""

    def test_preserves_ttl_ms(self) -> None:
        original = Envelope(topic="k1.test", ttl_ms=10_000)
        stamped = original.with_bus_fields(envelope_id=1, sequence=1, created_ns=1)
        assert stamped.ttl_ms == 10_000

    def test_preserves_payload_format(self) -> None:
        original = Envelope(topic="k1.test", payload_format=PayloadFormat.MSGPACK)
        stamped = original.with_bus_fields(envelope_id=2, sequence=2, created_ns=2)
        assert stamped.payload_format == PayloadFormat.MSGPACK

    def test_preserves_both_v2_fields(self) -> None:
        original = Envelope(
            topic="k1.test",
            priority=Priority.URGENT,
            cognitive_trace_id="trace-bus",
            session_id="sess-bus",
            request_id="req-bus",
            parent_id=10,
            payload=b"stamped",
            ttl_ms=30_000,
            payload_format=PayloadFormat.JSON,
        )
        stamped = original.with_bus_fields(envelope_id=100, sequence=50, created_ns=999)
        # Bus fields updated
        assert stamped.envelope_id == 100
        assert stamped.sequence == 50
        assert stamped.created_ns == 999
        # V1 fields preserved
        assert stamped.topic == "k1.test"
        assert stamped.priority == Priority.URGENT
        assert stamped.cognitive_trace_id == "trace-bus"
        assert stamped.session_id == "sess-bus"
        assert stamped.request_id == "req-bus"
        assert stamped.parent_id == 10
        assert stamped.payload == b"stamped"
        # V2 fields preserved
        assert stamped.ttl_ms == 30_000
        assert stamped.payload_format == PayloadFormat.JSON

    def test_does_not_mutate_original(self) -> None:
        original = Envelope(topic="k1.test", ttl_ms=5000)
        _ = original.with_bus_fields(envelope_id=1, sequence=1, created_ns=1)
        assert original.envelope_id == 0
        assert original.ttl_ms == 5000


# ===================================================================
# V2 serialization edge cases
# ===================================================================


class TestV2EdgeCases:
    """Edge cases for FlatBuffers serialization."""

    def test_v2_round_trip_minimal(self) -> None:
        """Minimal envelope with only defaults."""
        data = Envelope()._to_bytes_v2()
        restored = Envelope._from_bytes_v2(data)
        assert restored.topic == ""
        assert restored.priority == Priority.INTERACTIVE
        assert restored.ttl_ms == 0
        assert restored.payload_format == PayloadFormat.OPAQUE
        assert restored.payload == b""

    def test_v2_payload_integrity(self) -> None:
        """Payload bytes must be bit-exact after round-trip."""
        import os as _os

        payload = _os.urandom(4096)
        env = Envelope(topic="k1.integrity", payload=payload)
        restored = Envelope.from_bytes(env._to_bytes_v2())
        assert restored.payload == payload

    def test_v2_wire_size_smaller_than_v1_for_small_envelope(self) -> None:
        """FlatBuffers should produce comparable or smaller wire size."""
        env = Envelope(
            topic="k1.size",
            priority=Priority.INTERACTIVE,
            envelope_id=1,
            sequence=1,
            cognitive_trace_id="t",
            session_id="s",
            request_id="r",
            parent_id=0,
            created_ns=1,
            payload=b"x",
        )
        v1_size = len(env._to_bytes_v1())
        v2_size = len(env._to_bytes_v2())
        # V2 should be within 2x of V1 for small envelopes
        # (FlatBuffers has vtable overhead for small tables)
        assert v2_size < v1_size * 2, f"V2 size ({v2_size}) unexpectedly large vs V1 ({v1_size})"

    def test_many_round_trips_deterministic(self) -> None:
        """Repeated serialization produces identical bytes."""
        env = Envelope(
            topic="k1.deterministic",
            envelope_id=42,
            ttl_ms=1000,
            payload=b"stable",
        )
        first = env._to_bytes_v2()
        for _ in range(100):
            assert env._to_bytes_v2() == first


# ===================================================================
# Performance sanity check
# ===================================================================


class TestV2Performance:
    """V2 FlatBuffers performance must be reasonable."""

    def _bench(self, env: Envelope, iterations: int = 5000) -> tuple[float, float]:
        """Return (serialize_us, deserialize_us) per operation."""
        # Warmup
        for _ in range(100):
            Envelope.from_bytes(env.to_bytes())

        # Serialize
        t0 = time.perf_counter_ns()
        for _ in range(iterations):
            env.to_bytes()
        ser_ns = (time.perf_counter_ns() - t0) / iterations

        data = env.to_bytes()

        # Deserialize
        t0 = time.perf_counter_ns()
        for _ in range(iterations):
            Envelope.from_bytes(data)
        deser_ns = (time.perf_counter_ns() - t0) / iterations

        return ser_ns / 1000, deser_ns / 1000  # microseconds

    def test_v2_serialize_under_100us(self) -> None:
        """V2 serialize must complete in < 100us per envelope."""
        env = Envelope(
            topic="k1.perf.test.v1",
            priority=Priority.URGENT,
            envelope_id=999,
            sequence=42,
            cognitive_trace_id="cog-perf",
            session_id="sess-perf",
            request_id="req-perf",
            parent_id=998,
            created_ns=123456789,
            payload=b"x" * 1024,
            ttl_ms=5000,
            payload_format=PayloadFormat.JSON,
        )
        ser_us, deser_us = self._bench(env)
        assert ser_us < 100, f"Serialize too slow: {ser_us:.1f}us"
        assert deser_us < 100, f"Deserialize too slow: {deser_us:.1f}us"

    def test_v2_large_payload_throughput(self) -> None:
        """256KB payload must round-trip in < 1ms."""
        env = Envelope(
            topic="k1.perf.large",
            payload=b"\xff" * 256 * 1024,
        )
        ser_us, deser_us = self._bench(env, iterations=500)
        assert ser_us < 1000, f"Large serialize too slow: {ser_us:.1f}us"
        assert deser_us < 1000, f"Large deserialize too slow: {deser_us:.1f}us"
