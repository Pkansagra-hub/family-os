"""
k1.bus.envelope.envelope -- Canonical bus envelope and supporting enums.

The Envelope is the unit of data that flows through IBus and IMailboxRouter.
The bus reads ONLY the envelope header for routing and timing decisions.
The payload field is opaque bytes -- the bus never reads it.

Design decisions (from k1_bus_core.mmd header):
  1. Bus is BLIND: payload = opaque bytes.
  2. FlatBuffers envelope (V2 active). V1 JSON fallback available.
  3. envelope_id is global monotonic, sequence is per-topic monotonic.
  4. parent_id enables causal ordering (0 = root, no parent).
  5. cognitive_trace_id is the cross-K0/K1 correlation key.
  6. ttl_ms enables envelope expiry at dispatch time (0 = no expiry).
  7. payload_format hints typed deserialization (0=opaque, 1=JSON, 2=msgpack).

Serialization:
  V1 (fallback): JSON header + raw payload.  Set K1_ENVELOPE_FORMAT=v1.
  V2 (default):  FlatBuffers zero-copy.  4-byte magic b'FB02' prefix.
                  Auto-detected on from_bytes -- no config needed for reads.

Wire format detection in from_bytes():
  - Starts with b'FB02' -> V2 FlatBuffers path
  - Otherwise           -> V1 JSON path

Exports:
    Priority       -- 4-level WFQ priority enum
    DeliveryMode   -- 3-mode timing chain config enum
    PayloadFormat  -- 3-mode payload type hint enum (V2)
    Envelope       -- Frozen dataclass, the bus message unit
"""

from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass
from enum import IntEnum

import flatbuffers

from k1.bus.envelope import _fb_generated as _fb

# ---------------------------------------------------------------------------
# Priority enum (WFQ scheduling weights from F136)
# ---------------------------------------------------------------------------


class Priority(IntEnum):
    """
    WFQ priority levels for bus envelope scheduling.

    Weights (from K1_FLOWS.md F136):
        URGENT=4x, REALTIME=3x, INTERACTIVE=2x, BACKGROUND=1x

    Latency targets:
        URGENT <5ms, REALTIME <10ms, INTERACTIVE <50ms, BACKGROUND <500ms
    """

    URGENT = 0
    REALTIME = 1
    INTERACTIVE = 2
    BACKGROUND = 3

    @property
    def weight(self) -> int:
        """WFQ scheduling weight. Higher = more bandwidth."""
        return {0: 4, 1: 3, 2: 2, 3: 1}[self.value]


# ---------------------------------------------------------------------------
# Delivery mode enum (timing chain config)
# ---------------------------------------------------------------------------


class DeliveryMode(IntEnum):
    """
    Per-topic-prefix delivery mode for the timing chain.

    STRICT:      Ordered delivery, buffer on sequence gap, causal wait.
    RELAXED:     Deliver as-is, log reorder (monitoring only).
    BEST_EFFORT: Deliver immediately, drop OK under pressure.
    """

    STRICT = 0
    RELAXED = 1
    BEST_EFFORT = 2


# ---------------------------------------------------------------------------
# Payload format enum (V2 -- typed payload hints for adapters)
# ---------------------------------------------------------------------------


class PayloadFormat(IntEnum):
    """
    Payload type hint for adapter deserialization.

    The bus is BLIND to payload content.  This enum is a hint carried in the
    envelope header so that adapters (FabricBusAdapter, SessionBusAdapter)
    can skip format detection on the receive path.

    OPAQUE:  V1 behavior -- raw bytes, adapter must guess or ignore.
    JSON:    Payload is JSON-encoded UTF-8.
    MSGPACK: Payload is MessagePack-encoded.
    """

    OPAQUE = 0
    JSON = 1
    MSGPACK = 2


# ---------------------------------------------------------------------------
# Serialization format toggle
# ---------------------------------------------------------------------------

# V2 FlatBuffers wire format magic prefix (4 bytes).
# from_bytes() uses this for auto-detection -- no config needed for reads.
_V2_MAGIC = b"FB02"

# Controls which format to_bytes() produces.
# "v2" (default) = FlatBuffers with FB02 prefix.
# "v1"           = Legacy JSON header + raw payload.
# Override via environment variable K1_ENVELOPE_FORMAT.
ENVELOPE_FORMAT: str = os.environ.get("K1_ENVELOPE_FORMAT", "v2")


# ---------------------------------------------------------------------------
# Envelope -- the canonical bus message unit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Envelope:
    """
    Immutable bus envelope -- the unit of data flowing through IBus.

    The bus reads the header fields for routing, timing, and scheduling.
    The payload is opaque bytes -- the bus NEVER reads it.

    Attributes:
        topic:              Hierarchical topic string (e.g. "k1.capability.completed.v1")
        priority:           WFQ scheduling priority (0=URGENT .. 3=BACKGROUND)
        envelope_id:        Global monotonic ID, assigned by the bus
        sequence:           Per-topic monotonic sequence, assigned by the bus
        cognitive_trace_id: Cross-K0/K1 correlation key
        session_id:         Session scope identifier
        request_id:         Request scope within session
        parent_id:          Causal parent envelope_id (0 = root, no parent)
        created_ns:         Monotonic clock timestamp in nanoseconds, bus-assigned
        payload:            Opaque bytes -- bus never reads this
        ttl_ms:             Time-to-live in milliseconds (0 = no expiry) [V2]
        payload_format:     Payload type hint (0=OPAQUE, 1=JSON, 2=MSGPACK) [V2]
    """

    topic: str = ""
    priority: int = Priority.INTERACTIVE
    envelope_id: int = 0
    sequence: int = 0
    cognitive_trace_id: str = ""
    session_id: str = ""
    request_id: str = ""
    parent_id: int = 0
    created_ns: int = 0
    payload: bytes = b""
    # V2 additions
    ttl_ms: int = 0
    payload_format: int = PayloadFormat.OPAQUE

    def __post_init__(self) -> None:
        """Validate fields on construction."""
        if not isinstance(self.topic, str):
            raise TypeError(f"topic must be str, got {type(self.topic).__name__}")
        if not isinstance(self.payload, (bytes, bytearray)):
            raise TypeError(f"payload must be bytes, got {type(self.payload).__name__}")
        if self.priority not in (0, 1, 2, 3):
            raise ValueError(f"priority must be 0-3, got {self.priority}")
        if self.envelope_id < 0:
            raise ValueError(f"envelope_id must be >= 0, got {self.envelope_id}")
        if self.sequence < 0:
            raise ValueError(f"sequence must be >= 0, got {self.sequence}")
        if self.parent_id < 0:
            raise ValueError(f"parent_id must be >= 0, got {self.parent_id}")
        if self.ttl_ms < 0:
            raise ValueError(f"ttl_ms must be >= 0, got {self.ttl_ms}")
        if self.payload_format not in (0, 1, 2):
            raise ValueError(f"payload_format must be 0-2, got {self.payload_format}")

    @property
    def payload_len(self) -> int:
        """Payload byte count."""
        return len(self.payload)

    @property
    def priority_enum(self) -> Priority:
        """Priority as enum value."""
        return Priority(self.priority)

    @property
    def payload_format_enum(self) -> PayloadFormat:
        """PayloadFormat as enum value."""
        return PayloadFormat(self.payload_format)

    @property
    def is_root(self) -> bool:
        """True if this envelope has no causal parent."""
        return self.parent_id == 0

    @property
    def is_expired(self) -> bool:
        """True if ttl_ms > 0 (envelope has a finite lifetime)."""
        return self.ttl_ms > 0

    # ------------------------------------------------------------------
    # Serialization dispatch
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """
        Serialize envelope to bytes.

        Format is controlled by module-level ENVELOPE_FORMAT:
            "v2" (default) -> FlatBuffers with b'FB02' prefix
            "v1"           -> Legacy JSON header + raw payload

        from_bytes() auto-detects the format on read.
        """
        if ENVELOPE_FORMAT == "v1":
            return self._to_bytes_v1()
        return self._to_bytes_v2()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Envelope":
        """
        Deserialize envelope from bytes.

        Auto-detects format:
            - Starts with b'FB02' -> V2 FlatBuffers
            - Otherwise           -> V1 JSON

        Raises:
            ValueError: If data is too short or malformed.
        """
        if len(data) < 4:
            raise ValueError(f"Envelope data too short: {len(data)} bytes (need >= 4)")
        if data[:4] == _V2_MAGIC:
            return cls._from_bytes_v2(data)
        return cls._from_bytes_v1(data)

    # ------------------------------------------------------------------
    # V1 serialization (JSON header + raw payload -- legacy fallback)
    # ------------------------------------------------------------------

    def _to_bytes_v1(self) -> bytes:
        """
        V1 wire format:
            [4 bytes: header_json_len (big-endian uint32)]
            [header_json_len bytes: JSON-encoded header fields]
            [remaining bytes: raw payload]
        """
        header = {
            "topic": self.topic,
            "priority": self.priority,
            "envelope_id": self.envelope_id,
            "sequence": self.sequence,
            "cognitive_trace_id": self.cognitive_trace_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "parent_id": self.parent_id,
            "created_ns": self.created_ns,
            "ttl_ms": self.ttl_ms,
            "payload_format": self.payload_format,
        }
        header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
        header_len = struct.pack(">I", len(header_bytes))
        return header_len + header_bytes + self.payload

    @classmethod
    def _from_bytes_v1(cls, data: bytes) -> "Envelope":
        """Deserialize V1 JSON format."""
        if len(data) < 4:
            raise ValueError(f"Envelope data too short: {len(data)} bytes (need >= 4)")

        (header_len,) = struct.unpack(">I", data[:4])

        if len(data) < 4 + header_len:
            raise ValueError(
                f"Envelope data truncated: have {len(data)} bytes, "
                f"header claims {header_len} bytes"
            )

        header_bytes = data[4 : 4 + header_len]
        payload = data[4 + header_len :]

        try:
            header = json.loads(header_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Malformed envelope header: {exc}") from exc

        return cls(
            topic=header.get("topic", ""),
            priority=header.get("priority", Priority.INTERACTIVE),
            envelope_id=header.get("envelope_id", 0),
            sequence=header.get("sequence", 0),
            cognitive_trace_id=header.get("cognitive_trace_id", ""),
            session_id=header.get("session_id", ""),
            request_id=header.get("request_id", ""),
            parent_id=header.get("parent_id", 0),
            created_ns=header.get("created_ns", 0),
            payload=payload,
            ttl_ms=header.get("ttl_ms", 0),
            payload_format=header.get("payload_format", 0),
        )

    # ------------------------------------------------------------------
    # V2 serialization (FlatBuffers zero-copy)
    # ------------------------------------------------------------------

    def _to_bytes_v2(self) -> bytes:
        """
        V2 wire format:
            [4 bytes: b'FB02' magic prefix]
            [N bytes: FlatBuffers BusEnvelope table]

        FlatBuffers builder: strings and vectors are created first (they
        must be written before StartObject), then numeric fields are set
        inside the Start/End block.
        """
        builder = flatbuffers.Builder(256 + len(self.payload))

        # Pre-create variable-length fields (must precede StartObject)
        topic_off = builder.CreateString(self.topic)
        trace_off = builder.CreateString(self.cognitive_trace_id)
        session_off = builder.CreateString(self.session_id)
        request_off = builder.CreateString(self.request_id)
        payload_off = builder.CreateByteVector(self.payload)

        # Build the table
        _fb.BusEnvelopeStart(builder)
        _fb.BusEnvelopeAddEnvelopeId(builder, self.envelope_id)
        _fb.BusEnvelopeAddSequence(builder, self.sequence)
        _fb.BusEnvelopeAddParentId(builder, self.parent_id)
        _fb.BusEnvelopeAddCreatedNs(builder, self.created_ns)
        _fb.BusEnvelopeAddPriority(builder, self.priority)
        _fb.BusEnvelopeAddTtlMs(builder, self.ttl_ms)
        _fb.BusEnvelopeAddPayloadFormat(builder, self.payload_format)
        _fb.BusEnvelopeAddTopic(builder, topic_off)
        _fb.BusEnvelopeAddCognitiveTraceId(builder, trace_off)
        _fb.BusEnvelopeAddSessionId(builder, session_off)
        _fb.BusEnvelopeAddRequestId(builder, request_off)
        _fb.BusEnvelopeAddPayload(builder, payload_off)
        root = _fb.BusEnvelopeEnd(builder)

        builder.Finish(root)
        buf = bytes(builder.Output())
        return _V2_MAGIC + buf

    @classmethod
    def _from_bytes_v2(cls, data: bytes) -> "Envelope":
        """
        Deserialize V2 FlatBuffers format.

        Strips the 4-byte FB02 magic prefix, then reads the FlatBuffers
        table using zero-copy accessors.  String fields are decoded from
        UTF-8 bytes.  Payload is extracted via direct buffer slice.
        """
        fb_data = data[4:]  # strip magic prefix
        fb_env = _fb.BusEnvelope.GetRootAsBusEnvelope(fb_data, 0)

        # String fields: FlatBuffers Python returns bytes, decode to str
        raw_topic = fb_env.Topic()
        topic = raw_topic.decode("utf-8") if raw_topic is not None else ""

        raw_trace = fb_env.CognitiveTraceId()
        cognitive_trace_id = raw_trace.decode("utf-8") if raw_trace is not None else ""

        raw_session = fb_env.SessionId()
        session_id = raw_session.decode("utf-8") if raw_session is not None else ""

        raw_request = fb_env.RequestId()
        request_id = raw_request.decode("utf-8") if raw_request is not None else ""

        # Payload: direct buffer slice for performance (no per-byte calls)
        payload = fb_env.PayloadBytes()

        return cls(
            topic=topic,
            priority=fb_env.Priority(),
            envelope_id=fb_env.EnvelopeId(),
            sequence=fb_env.Sequence(),
            cognitive_trace_id=cognitive_trace_id,
            session_id=session_id,
            request_id=request_id,
            parent_id=fb_env.ParentId(),
            created_ns=fb_env.CreatedNs(),
            payload=payload,
            ttl_ms=fb_env.TtlMs(),
            payload_format=fb_env.PayloadFormat(),
        )

    # ------------------------------------------------------------------
    # Builder helpers (for bus internals that stamp envelope fields)
    # ------------------------------------------------------------------

    def with_bus_fields(
        self,
        envelope_id: int,
        sequence: int,
        created_ns: int,
    ) -> "Envelope":
        """
        Return a new Envelope with bus-assigned fields stamped.

        Used by EnvelopeBuilder inside LocalBus -- the publisher provides
        topic, priority, payload, trace IDs. The bus stamps envelope_id,
        sequence, and created_ns.

        V2 fields (ttl_ms, payload_format) are preserved from the original.
        """
        return Envelope(
            topic=self.topic,
            priority=self.priority,
            envelope_id=envelope_id,
            sequence=sequence,
            cognitive_trace_id=self.cognitive_trace_id,
            session_id=self.session_id,
            request_id=self.request_id,
            parent_id=self.parent_id,
            created_ns=created_ns,
            payload=self.payload,
            ttl_ms=self.ttl_ms,
            payload_format=self.payload_format,
        )
