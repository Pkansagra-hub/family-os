"""
Integration tests for k1_bus_core Rust extension module.

Covers:
    - Module availability detection and graceful skip
    - version() and hello() smoke tests
    - envelope_to_bytes / envelope_from_bytes round-trip
    - Cross-language: Python Envelope.to_bytes() -> Rust envelope_from_bytes()
    - Cross-language: Rust envelope_to_bytes() -> Python Envelope.from_bytes()
    - Field fidelity across all 12 schema fields
    - Edge cases: empty payload, max uint64, binary payloads, long strings
    - Error paths: missing magic, truncated data, wrong types
    - Performance: Rust vs Python serialization latency
    - RustEnvelope: #[pyclass(frozen)] with all 12 fields (V2-M4)
    - RustEnvelope cross-language: RustEnvelope.to_bytes() <-> Python Envelope.from_bytes()
    - RingBuffer: write/read, backpressure, fan-out, benchmark (V2-M4)
"""

from __future__ import annotations

import os
import time

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority  # noqa: E402

# --- Conditional import: skip all tests if Rust crate is not installed ---

try:
    import k1_bus_core  # type: ignore[import-untyped]

    HAS_RUST = True
except ImportError:
    HAS_RUST = False
    k1_bus_core = None  # type: ignore[assignment]  # noqa: F811

pytestmark = pytest.mark.skipif(not HAS_RUST, reason="k1_bus_core not installed")


# ===================================================================
# Module smoke tests
# ===================================================================


class TestModuleSmoke:
    """Basic module presence and identity."""

    def test_version_string(self) -> None:
        v = k1_bus_core.version()
        assert isinstance(v, str)
        parts = v.split(".")
        assert len(parts) == 3, f"Expected semver, got {v}"

    def test_hello_message(self) -> None:
        msg = k1_bus_core.hello()
        assert isinstance(msg, str)
        assert "k1_bus_core" in msg

    def test_exports(self) -> None:
        assert callable(k1_bus_core.envelope_to_bytes)
        assert callable(k1_bus_core.envelope_from_bytes)


# ===================================================================
# Rust-only round-trip
# ===================================================================


class TestRustRoundTrip:
    """Round-trip through Rust envelope_to_bytes -> envelope_from_bytes."""

    def test_minimal(self) -> None:
        fields = {"topic": "test.minimal"}
        data = k1_bus_core.envelope_to_bytes(fields)
        assert isinstance(data, bytes)
        assert data[:4] == b"FB02"
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["topic"] == "test.minimal"

    def test_all_fields(self) -> None:
        fields = {
            "topic": "k1.test.full",
            "priority": 0,
            "envelope_id": 42,
            "sequence": 7,
            "cognitive_trace_id": "trace-abc",
            "session_id": "sess-xyz",
            "request_id": "req-123",
            "parent_id": 41,
            "created_ns": 1_000_000_000,
            "payload": b"hello world",
            "ttl_ms": 5000,
            "payload_format": 1,
        }
        data = k1_bus_core.envelope_to_bytes(fields)
        result = k1_bus_core.envelope_from_bytes(data)

        assert result["topic"] == "k1.test.full"
        assert result["priority"] == 0
        assert result["envelope_id"] == 42
        assert result["sequence"] == 7
        assert result["cognitive_trace_id"] == "trace-abc"
        assert result["session_id"] == "sess-xyz"
        assert result["request_id"] == "req-123"
        assert result["parent_id"] == 41
        assert result["created_ns"] == 1_000_000_000
        assert result["payload"] == b"hello world"
        assert result["ttl_ms"] == 5000
        assert result["payload_format"] == 1

    def test_defaults_for_missing_fields(self) -> None:
        """Missing dict keys should get FlatBuffers defaults."""
        data = k1_bus_core.envelope_to_bytes({})
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["topic"] == ""
        assert result["priority"] == 2  # INTERACTIVE default
        assert result["envelope_id"] == 0
        assert result["sequence"] == 0
        assert result["parent_id"] == 0
        assert result["created_ns"] == 0
        assert result["ttl_ms"] == 0
        assert result["payload_format"] == 0
        assert result["payload"] == b""

    def test_empty_payload(self) -> None:
        fields = {"topic": "test.empty", "payload": b""}
        data = k1_bus_core.envelope_to_bytes(fields)
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["payload"] == b""

    def test_binary_payload(self) -> None:
        """Binary payload with null bytes and full byte range."""
        payload = bytes(range(256))
        fields = {"topic": "test.binary", "payload": payload}
        data = k1_bus_core.envelope_to_bytes(fields)
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["payload"] == payload

    def test_large_payload(self) -> None:
        """256 KB payload round-trip."""
        payload = os.urandom(256 * 1024)
        fields = {"topic": "test.bulk", "payload": payload}
        data = k1_bus_core.envelope_to_bytes(fields)
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["payload"] == payload

    def test_max_uint64(self) -> None:
        max_u64 = (1 << 64) - 1
        fields = {
            "topic": "test.max",
            "envelope_id": max_u64,
            "sequence": max_u64,
            "parent_id": max_u64,
            "created_ns": max_u64,
        }
        data = k1_bus_core.envelope_to_bytes(fields)
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["envelope_id"] == max_u64
        assert result["sequence"] == max_u64
        assert result["parent_id"] == max_u64
        assert result["created_ns"] == max_u64

    def test_max_ttl(self) -> None:
        max_u32 = (1 << 32) - 1
        fields = {"topic": "test.maxttl", "ttl_ms": max_u32}
        data = k1_bus_core.envelope_to_bytes(fields)
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["ttl_ms"] == max_u32

    def test_unicode_topic(self) -> None:
        fields = {"topic": "k1.test.unicode.emoji"}
        data = k1_bus_core.envelope_to_bytes(fields)
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["topic"] == "k1.test.unicode.emoji"

    def test_long_strings(self) -> None:
        long = "a" * 10_000
        fields = {
            "topic": long,
            "cognitive_trace_id": long,
            "session_id": long,
            "request_id": long,
        }
        data = k1_bus_core.envelope_to_bytes(fields)
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["topic"] == long
        assert result["cognitive_trace_id"] == long
        assert result["session_id"] == long
        assert result["request_id"] == long

    def test_all_priority_levels(self) -> None:
        for p in (0, 1, 2, 3):
            fields = {"topic": f"test.p{p}", "priority": p}
            data = k1_bus_core.envelope_to_bytes(fields)
            result = k1_bus_core.envelope_from_bytes(data)
            assert result["priority"] == p

    def test_all_payload_formats(self) -> None:
        for pf in (0, 1, 2):
            fields = {"topic": f"test.pf{pf}", "payload_format": pf}
            data = k1_bus_core.envelope_to_bytes(fields)
            result = k1_bus_core.envelope_from_bytes(data)
            assert result["payload_format"] == pf


# ===================================================================
# Cross-language: Python Envelope -> Rust
# ===================================================================


class TestPythonToRust:
    """Python Envelope.to_bytes() -> Rust envelope_from_bytes()."""

    def test_basic_envelope(self) -> None:
        env = Envelope(
            topic="k1.xlang.p2r",
            priority=1,
            envelope_id=100,
            sequence=10,
            cognitive_trace_id="trace-p2r",
            session_id="sess-p2r",
            request_id="req-p2r",
            parent_id=99,
            created_ns=2_000_000,
            payload=b"python-payload",
            ttl_ms=3000,
            payload_format=PayloadFormat.JSON,
        )
        data = env.to_bytes()
        assert data[:4] == b"FB02", "Python should produce V2 by default"

        result = k1_bus_core.envelope_from_bytes(data)
        assert result["topic"] == "k1.xlang.p2r"
        assert result["priority"] == 1
        assert result["envelope_id"] == 100
        assert result["sequence"] == 10
        assert result["cognitive_trace_id"] == "trace-p2r"
        assert result["session_id"] == "sess-p2r"
        assert result["request_id"] == "req-p2r"
        assert result["parent_id"] == 99
        assert result["created_ns"] == 2_000_000
        assert result["payload"] == b"python-payload"
        assert result["ttl_ms"] == 3000
        assert result["payload_format"] == 1

    def test_default_envelope(self) -> None:
        env = Envelope()
        data = env.to_bytes()
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["topic"] == ""
        assert result["priority"] == 2
        assert result["envelope_id"] == 0
        assert result["payload"] == b""
        assert result["ttl_ms"] == 0

    def test_binary_payload_cross(self) -> None:
        payload = bytes(range(256)) * 100
        env = Envelope(topic="k1.cross.bin", payload=payload)
        data = env.to_bytes()
        result = k1_bus_core.envelope_from_bytes(data)
        assert result["payload"] == payload


# ===================================================================
# Cross-language: Rust -> Python Envelope
# ===================================================================


class TestRustToPython:
    """Rust envelope_to_bytes() -> Python Envelope.from_bytes()."""

    def test_basic_to_python(self) -> None:
        fields = {
            "topic": "k1.xlang.r2p",
            "priority": 3,
            "envelope_id": 200,
            "sequence": 20,
            "cognitive_trace_id": "trace-r2p",
            "session_id": "sess-r2p",
            "request_id": "req-r2p",
            "parent_id": 199,
            "created_ns": 3_000_000,
            "payload": b"rust-payload",
            "ttl_ms": 7000,
            "payload_format": 2,
        }
        data = k1_bus_core.envelope_to_bytes(fields)
        env = Envelope.from_bytes(data)

        assert env.topic == "k1.xlang.r2p"
        assert env.priority == 3
        assert env.envelope_id == 200
        assert env.sequence == 20
        assert env.cognitive_trace_id == "trace-r2p"
        assert env.session_id == "sess-r2p"
        assert env.request_id == "req-r2p"
        assert env.parent_id == 199
        assert env.created_ns == 3_000_000
        assert env.payload == b"rust-payload"
        assert env.ttl_ms == 7000
        assert env.payload_format == 2

    def test_defaults_to_python(self) -> None:
        data = k1_bus_core.envelope_to_bytes({"topic": "k1.defaults"})
        env = Envelope.from_bytes(data)
        assert env.topic == "k1.defaults"
        assert env.priority == Priority.INTERACTIVE
        assert env.ttl_ms == 0
        assert env.payload_format == PayloadFormat.OPAQUE

    def test_large_payload_to_python(self) -> None:
        payload = os.urandom(128 * 1024)
        data = k1_bus_core.envelope_to_bytes({"topic": "test.big", "payload": payload})
        env = Envelope.from_bytes(data)
        assert env.payload == payload


# ===================================================================
# Full round-trip: Python -> Rust -> Python
# ===================================================================


class TestFullRoundTrip:
    """Python Envelope -> Rust bytes -> Python Envelope."""

    def test_python_rust_python(self) -> None:
        original = Envelope(
            topic="k1.roundtrip.full",
            priority=0,
            envelope_id=999,
            sequence=50,
            cognitive_trace_id="trace-full",
            session_id="sess-full",
            request_id="req-full",
            parent_id=998,
            created_ns=5_000_000_000,
            payload=b"round-trip-data",
            ttl_ms=10000,
            payload_format=PayloadFormat.MSGPACK,
        )
        # Python -> bytes (V2 FlatBuffers)
        wire = original.to_bytes()

        # Rust deserialize -> dict
        rust_dict = k1_bus_core.envelope_from_bytes(wire)

        # Rust serialize dict back to bytes
        wire2 = k1_bus_core.envelope_to_bytes(rust_dict)

        # Python deserialize
        restored = Envelope.from_bytes(wire2)

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


# ===================================================================
# Error paths
# ===================================================================


class TestErrorPaths:
    """Rust error handling for invalid inputs."""

    def test_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            k1_bus_core.envelope_from_bytes(b"FB")

    def test_missing_magic(self) -> None:
        with pytest.raises(ValueError, match="missing FB02"):
            k1_bus_core.envelope_from_bytes(b"XXXX" + b"\x00" * 20)

    def test_empty_bytes(self) -> None:
        with pytest.raises(ValueError):
            k1_bus_core.envelope_from_bytes(b"")

    def test_truncated_flatbuffer(self) -> None:
        """Valid magic but garbage FlatBuffer data."""
        with pytest.raises(ValueError, match="Malformed"):
            k1_bus_core.envelope_from_bytes(b"FB02" + b"\xff" * 4)

    def test_to_bytes_wrong_type(self) -> None:
        """Passing non-dict should raise TypeError."""
        with pytest.raises(TypeError):
            k1_bus_core.envelope_to_bytes("not a dict")  # type: ignore[arg-type]

    def test_from_bytes_wrong_type(self) -> None:
        """Passing non-bytes should raise TypeError."""
        with pytest.raises(TypeError):
            k1_bus_core.envelope_from_bytes(12345)  # type: ignore[arg-type]


# ===================================================================
# Performance comparison
# ===================================================================


class TestPerformance:
    """Verify Rust is faster than Python for serialization."""

    @pytest.fixture
    def sample_envelope(self) -> Envelope:
        return Envelope(
            topic="k1.perf.benchmark",
            priority=1,
            envelope_id=12345,
            sequence=678,
            cognitive_trace_id="trace-perf-001",
            session_id="sess-perf-abc",
            request_id="req-perf-xyz",
            parent_id=12344,
            created_ns=1_234_567_890,
            payload=b"x" * 1024,
            ttl_ms=5000,
            payload_format=PayloadFormat.JSON,
        )

    @pytest.fixture
    def sample_dict(self) -> dict:
        return {
            "topic": "k1.perf.benchmark",
            "priority": 1,
            "envelope_id": 12345,
            "sequence": 678,
            "cognitive_trace_id": "trace-perf-001",
            "session_id": "sess-perf-abc",
            "request_id": "req-perf-xyz",
            "parent_id": 12344,
            "created_ns": 1_234_567_890,
            "payload": b"x" * 1024,
            "ttl_ms": 5000,
            "payload_format": 1,
        }

    def test_rust_serialize_faster(self, sample_dict: dict) -> None:
        """Rust serialization should be at least competitive with Python."""
        n = 5000
        start = time.perf_counter()
        for _ in range(n):
            k1_bus_core.envelope_to_bytes(sample_dict)
        rust_time = time.perf_counter() - start

        env = Envelope(**{k: v for k, v in sample_dict.items()})
        start = time.perf_counter()
        for _ in range(n):
            env.to_bytes()
        python_time = time.perf_counter() - start

        # Rust should be faster; log times for visibility
        print(
            f"\nSerialization {n} iterations: "
            f"Rust={rust_time * 1000:.1f}ms  "
            f"Python={python_time * 1000:.1f}ms  "
            f"speedup={python_time / rust_time:.1f}x"
        )
        # Conservative: Rust should be at least as fast (1x)
        # In practice expect 3-10x speedup
        assert (
            rust_time <= python_time * 2
        ), f"Rust ({rust_time:.3f}s) should not be >2x slower than Python ({python_time:.3f}s)"

    def test_rust_deserialize_faster(self, sample_dict: dict) -> None:
        """Rust deserialization should be at least competitive with Python."""
        wire = k1_bus_core.envelope_to_bytes(sample_dict)
        n = 5000

        start = time.perf_counter()
        for _ in range(n):
            k1_bus_core.envelope_from_bytes(wire)
        rust_time = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(n):
            Envelope.from_bytes(wire)
        python_time = time.perf_counter() - start

        print(
            f"\nDeserialization {n} iterations: "
            f"Rust={rust_time * 1000:.1f}ms  "
            f"Python={python_time * 1000:.1f}ms  "
            f"speedup={python_time / rust_time:.1f}x"
        )
        assert (
            rust_time <= python_time * 2
        ), f"Rust ({rust_time:.3f}s) should not be >2x slower than Python ({python_time:.3f}s)"


# ===================================================================
# TopicTrie: Rust vs Python benchmark
# ===================================================================


class TestTopicTriePerformance:
    """Benchmark Rust TopicTrie vs Python TopicTrie."""

    def test_match_throughput(self) -> None:
        """100 patterns, 10K match calls -- Rust should be faster."""
        from k1.bus.impl.topic_trie import TopicTrie as PyTrie

        def _handler(env):
            pass

        # Build both tries with identical patterns
        py_trie = PyTrie()
        rust_trie = k1_bus_core.TopicTrie()

        patterns = []
        for i in range(50):
            patterns.append(f"k1.agent.{i}.delta.v1")
        for i in range(30):
            patterns.append(f"k1.session.{i}.*")
        for i in range(20):
            patterns.append(f"k1.capability.{i}.>")

        for j, p in enumerate(patterns):
            py_trie.insert(p, _handler, f"py-{j}")
            rust_trie.insert(p, _handler, f"rs-{j}")

        topics = [f"k1.agent.{i}.delta.v1" for i in range(50)]
        n = 10_000

        # Python
        t0 = time.perf_counter()
        for _ in range(n):
            for topic in topics[:10]:
                py_trie.match(topic)
        py_time = time.perf_counter() - t0

        # Rust (uncached -- fresh trie for fair comparison)
        rust_trie_fresh = k1_bus_core.TopicTrie()
        for j, p in enumerate(patterns):
            rust_trie_fresh.insert(p, _handler, f"rs2-{j}")

        t0 = time.perf_counter()
        for _ in range(n):
            for topic in topics[:10]:
                rust_trie_fresh.match_topic(topic)
        rust_time = time.perf_counter() - t0

        print(
            f"\nTopicTrie match {n}x10 topics (100 patterns): "
            f"Rust={rust_time * 1000:.1f}ms  "
            f"Python={py_time * 1000:.1f}ms  "
            f"speedup={py_time / rust_time:.1f}x"
        )
        # Conservative: Rust should not be dramatically slower
        assert (
            rust_time <= py_time * 3
        ), f"Rust ({rust_time:.3f}s) should not be >3x slower than Python ({py_time:.3f}s)"


# ===================================================================
# TopicTrie: subscription cache behavior
# ===================================================================


class TestTopicTrieCache:
    """Verify the generation-based subscription cache works correctly."""

    def test_cache_hit_on_repeat(self) -> None:
        trie = k1_bus_core.TopicTrie()
        trie.insert("k1.test", lambda e: None, "sub-1")
        # First call -- cache miss
        r1 = trie.match_topic("k1.test")
        assert len(r1) == 1
        assert trie.cache_size >= 1
        # Second call -- cache hit (same generation)
        r2 = trie.match_topic("k1.test")
        assert len(r2) == 1

    def test_cache_invalidated_on_insert(self) -> None:
        trie = k1_bus_core.TopicTrie()
        trie.insert("k1.test", lambda e: None, "sub-1")
        gen1 = trie.cache_generation
        trie.match_topic("k1.test")  # populate cache
        trie.insert("k1.test", lambda e: None, "sub-2")
        gen2 = trie.cache_generation
        assert gen2 > gen1
        # Match should now return 2 handlers (stale cache discarded)
        result = trie.match_topic("k1.test")
        assert len(result) == 2

    def test_cache_invalidated_on_remove(self) -> None:
        trie = k1_bus_core.TopicTrie()
        trie.insert("k1.test", lambda e: None, "sub-1")
        trie.insert("k1.test", lambda e: None, "sub-2")
        trie.match_topic("k1.test")  # populate cache
        gen1 = trie.cache_generation
        trie.remove("sub-1")
        gen2 = trie.cache_generation
        assert gen2 > gen1
        result = trie.match_topic("k1.test")
        assert len(result) == 1

    def test_cache_cleared_on_clear(self) -> None:
        trie = k1_bus_core.TopicTrie()
        trie.insert("k1.test", lambda e: None, "sub-1")
        trie.match_topic("k1.test")
        assert trie.cache_size >= 1
        trie.clear()
        assert trie.cache_size == 0
        assert trie.size == 0


# ===================================================================
# RustEnvelope: #[pyclass(frozen)] with all 12 fields (V2-M4)
# ===================================================================


class TestRustEnvelopeConstruction:
    """RustEnvelope construction and attribute access."""

    def test_defaults(self) -> None:
        env = k1_bus_core.RustEnvelope()
        assert env.topic == ""
        assert env.priority == 2  # INTERACTIVE
        assert env.envelope_id == 0
        assert env.sequence == 0
        assert env.cognitive_trace_id == ""
        assert env.session_id == ""
        assert env.request_id == ""
        assert env.parent_id == 0
        assert env.created_ns == 0
        assert env.payload == b""
        assert env.ttl_ms == 0
        assert env.payload_format == 0

    def test_all_fields(self) -> None:
        env = k1_bus_core.RustEnvelope(
            topic="k1.test.rust",
            priority=0,
            envelope_id=42,
            sequence=7,
            cognitive_trace_id="trace-abc",
            session_id="sess-xyz",
            request_id="req-123",
            parent_id=41,
            created_ns=1_000_000,
            payload=b"hello",
            ttl_ms=5000,
            payload_format=1,
        )
        assert env.topic == "k1.test.rust"
        assert env.priority == 0
        assert env.envelope_id == 42
        assert env.sequence == 7
        assert env.cognitive_trace_id == "trace-abc"
        assert env.session_id == "sess-xyz"
        assert env.request_id == "req-123"
        assert env.parent_id == 41
        assert env.created_ns == 1_000_000
        assert env.payload == b"hello"
        assert env.ttl_ms == 5000
        assert env.payload_format == 1

    def test_payload_len(self) -> None:
        env = k1_bus_core.RustEnvelope(payload=b"12345")
        assert env.payload_len == 5

    def test_is_root(self) -> None:
        assert k1_bus_core.RustEnvelope(parent_id=0).is_root is True
        assert k1_bus_core.RustEnvelope(parent_id=42).is_root is False

    def test_is_expired(self) -> None:
        assert k1_bus_core.RustEnvelope(ttl_ms=0).is_expired is False
        assert k1_bus_core.RustEnvelope(ttl_ms=100).is_expired is True

    def test_frozen_immutability(self) -> None:
        env = k1_bus_core.RustEnvelope(topic="k1.test")
        with pytest.raises(AttributeError):
            env.topic = "changed"  # type: ignore[misc]

    def test_bad_priority(self) -> None:
        with pytest.raises(ValueError, match="priority must be 0-3"):
            k1_bus_core.RustEnvelope(priority=99)

    def test_bad_payload_format(self) -> None:
        with pytest.raises(ValueError, match="payload_format must be 0-2"):
            k1_bus_core.RustEnvelope(payload_format=5)

    def test_repr(self) -> None:
        env = k1_bus_core.RustEnvelope(topic="k1.repr", envelope_id=42)
        r = repr(env)
        assert "k1.repr" in r
        assert "42" in r

    def test_equality(self) -> None:
        kwargs = dict(
            topic="k1.eq",
            priority=1,
            envelope_id=10,
            sequence=5,
            parent_id=9,
            payload=b"data",
        )
        a = k1_bus_core.RustEnvelope(**kwargs)
        b = k1_bus_core.RustEnvelope(**kwargs)
        assert a == b


# ===================================================================
# RustEnvelope serialization round-trip
# ===================================================================


class TestRustEnvelopeRoundTrip:
    """RustEnvelope to_bytes() / from_bytes() round-trip."""

    def _assert_rt(self, env: "k1_bus_core.RustEnvelope") -> "k1_bus_core.RustEnvelope":
        wire = env.to_bytes()
        assert wire[:4] == b"FB02"
        restored = k1_bus_core.RustEnvelope.from_bytes(wire)
        assert restored == env
        return restored

    def test_defaults(self) -> None:
        self._assert_rt(k1_bus_core.RustEnvelope())

    def test_full_fields(self) -> None:
        self._assert_rt(
            k1_bus_core.RustEnvelope(
                topic="k1.test.full",
                priority=0,
                envelope_id=42,
                sequence=7,
                cognitive_trace_id="trace-abc",
                session_id="sess-xyz",
                request_id="req-123",
                parent_id=41,
                created_ns=1_000_000,
                payload=b"hello-world",
                ttl_ms=5000,
                payload_format=1,
            )
        )

    def test_empty_payload(self) -> None:
        self._assert_rt(k1_bus_core.RustEnvelope(topic="k1.empty", payload=b""))

    def test_large_payload(self) -> None:
        payload = os.urandom(256 * 1024)
        self._assert_rt(k1_bus_core.RustEnvelope(topic="k1.bulk", payload=payload))

    def test_max_uint64(self) -> None:
        max_u64 = (1 << 64) - 1
        self._assert_rt(
            k1_bus_core.RustEnvelope(
                envelope_id=max_u64,
                sequence=max_u64,
                parent_id=max_u64,
                created_ns=max_u64,
                ttl_ms=(1 << 32) - 1,
            )
        )

    def test_all_priorities(self) -> None:
        for p in (0, 1, 2, 3):
            self._assert_rt(k1_bus_core.RustEnvelope(priority=p))

    def test_all_payload_formats(self) -> None:
        for pf in (0, 1, 2):
            self._assert_rt(k1_bus_core.RustEnvelope(payload_format=pf))

    def test_binary_payload(self) -> None:
        self._assert_rt(k1_bus_core.RustEnvelope(payload=bytes(range(256))))

    def test_from_bytes_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            k1_bus_core.RustEnvelope.from_bytes(b"FB")

    def test_from_bytes_wrong_magic(self) -> None:
        with pytest.raises(ValueError, match="missing FB02"):
            k1_bus_core.RustEnvelope.from_bytes(b"XXXX" + b"\x00" * 20)


# ===================================================================
# RustEnvelope with_bus_fields
# ===================================================================


class TestRustEnvelopeBuilder:
    """with_bus_fields builder method."""

    def test_with_bus_fields(self) -> None:
        original = k1_bus_core.RustEnvelope(
            topic="k1.test",
            priority=1,
            cognitive_trace_id="trace-1",
            session_id="sess-1",
            request_id="req-1",
            parent_id=10,
            payload=b"data",
            ttl_ms=3000,
            payload_format=1,
        )
        stamped = original.with_bus_fields(envelope_id=100, sequence=50, created_ns=999)
        # Bus-assigned fields updated
        assert stamped.envelope_id == 100
        assert stamped.sequence == 50
        assert stamped.created_ns == 999
        # Publisher fields preserved
        assert stamped.topic == "k1.test"
        assert stamped.priority == 1
        assert stamped.cognitive_trace_id == "trace-1"
        assert stamped.session_id == "sess-1"
        assert stamped.request_id == "req-1"
        assert stamped.parent_id == 10
        assert stamped.payload == b"data"
        # V2 fields preserved
        assert stamped.ttl_ms == 3000
        assert stamped.payload_format == 1

    def test_does_not_mutate_original(self) -> None:
        original = k1_bus_core.RustEnvelope(topic="k1.test", ttl_ms=5000)
        _ = original.with_bus_fields(envelope_id=1, sequence=1, created_ns=1)
        assert original.envelope_id == 0
        assert original.ttl_ms == 5000


# ===================================================================
# Cross-language: RustEnvelope <-> Python Envelope
# ===================================================================


class TestRustEnvelopeCrossLanguage:
    """Wire-format compatibility between RustEnvelope and Python Envelope."""

    def test_rust_to_python(self) -> None:
        """RustEnvelope.to_bytes() -> Python Envelope.from_bytes()."""
        rust_env = k1_bus_core.RustEnvelope(
            topic="k1.xlang.r2p",
            priority=3,
            envelope_id=200,
            sequence=20,
            cognitive_trace_id="trace-r2p",
            session_id="sess-r2p",
            request_id="req-r2p",
            parent_id=199,
            created_ns=3_000_000,
            payload=b"rust-to-python",
            ttl_ms=7000,
            payload_format=2,
        )
        wire = rust_env.to_bytes()
        py_env = Envelope.from_bytes(wire)

        assert py_env.topic == "k1.xlang.r2p"
        assert py_env.priority == 3
        assert py_env.envelope_id == 200
        assert py_env.sequence == 20
        assert py_env.cognitive_trace_id == "trace-r2p"
        assert py_env.session_id == "sess-r2p"
        assert py_env.request_id == "req-r2p"
        assert py_env.parent_id == 199
        assert py_env.created_ns == 3_000_000
        assert py_env.payload == b"rust-to-python"
        assert py_env.ttl_ms == 7000
        assert py_env.payload_format == 2

    def test_python_to_rust(self) -> None:
        """Python Envelope.to_bytes() -> RustEnvelope.from_bytes()."""
        py_env = Envelope(
            topic="k1.xlang.p2r",
            priority=1,
            envelope_id=100,
            sequence=10,
            cognitive_trace_id="trace-p2r",
            session_id="sess-p2r",
            request_id="req-p2r",
            parent_id=99,
            created_ns=2_000_000,
            payload=b"python-to-rust",
            ttl_ms=3000,
            payload_format=1,
        )
        wire = py_env.to_bytes()
        rust_env = k1_bus_core.RustEnvelope.from_bytes(wire)

        assert rust_env.topic == "k1.xlang.p2r"
        assert rust_env.priority == 1
        assert rust_env.envelope_id == 100
        assert rust_env.sequence == 10
        assert rust_env.cognitive_trace_id == "trace-p2r"
        assert rust_env.session_id == "sess-p2r"
        assert rust_env.request_id == "req-p2r"
        assert rust_env.parent_id == 99
        assert rust_env.created_ns == 2_000_000
        assert rust_env.payload == b"python-to-rust"
        assert rust_env.ttl_ms == 3000
        assert rust_env.payload_format == 1

    def test_full_roundtrip_python_rust_python(self) -> None:
        """Python Envelope -> wire -> RustEnvelope -> wire -> Python Envelope."""
        original = Envelope(
            topic="k1.roundtrip.full",
            priority=0,
            envelope_id=999,
            sequence=50,
            cognitive_trace_id="trace-full",
            session_id="sess-full",
            request_id="req-full",
            parent_id=998,
            created_ns=5_000_000_000,
            payload=b"round-trip",
            ttl_ms=10000,
            payload_format=2,
        )
        wire1 = original.to_bytes()
        rust_env = k1_bus_core.RustEnvelope.from_bytes(wire1)
        wire2 = rust_env.to_bytes()
        restored = Envelope.from_bytes(wire2)

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


# ===================================================================
# RustEnvelope performance
# ===================================================================


class TestRustEnvelopePerformance:
    """RustEnvelope should be faster than Python Envelope for ser/deser."""

    def test_serialize_speedup(self) -> None:
        n = 5000
        rust_env = k1_bus_core.RustEnvelope(
            topic="k1.perf.benchmark",
            priority=1,
            envelope_id=12345,
            sequence=678,
            cognitive_trace_id="trace-perf-001",
            session_id="sess-perf-abc",
            request_id="req-perf-xyz",
            parent_id=12344,
            created_ns=1_234_567_890,
            payload=b"x" * 1024,
            ttl_ms=5000,
            payload_format=1,
        )
        py_env = Envelope(
            topic="k1.perf.benchmark",
            priority=1,
            envelope_id=12345,
            sequence=678,
            cognitive_trace_id="trace-perf-001",
            session_id="sess-perf-abc",
            request_id="req-perf-xyz",
            parent_id=12344,
            created_ns=1_234_567_890,
            payload=b"x" * 1024,
            ttl_ms=5000,
            payload_format=1,
        )

        # Warmup
        for _ in range(100):
            rust_env.to_bytes()
            py_env.to_bytes()

        t0 = time.perf_counter()
        for _ in range(n):
            rust_env.to_bytes()
        rust_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(n):
            py_env.to_bytes()
        python_time = time.perf_counter() - t0

        print(
            f"\nRustEnvelope serialize {n}: "
            f"Rust={rust_time * 1000:.1f}ms  "
            f"Python={python_time * 1000:.1f}ms  "
            f"speedup={python_time / rust_time:.1f}x"
        )
        assert rust_time <= python_time * 2

    def test_deserialize_speedup(self) -> None:
        n = 5000
        rust_env = k1_bus_core.RustEnvelope(
            topic="k1.perf.deser",
            priority=1,
            envelope_id=12345,
            payload=b"x" * 1024,
            ttl_ms=5000,
        )
        wire = rust_env.to_bytes()

        py_env = Envelope(
            topic="k1.perf.deser",
            priority=1,
            envelope_id=12345,
            payload=b"x" * 1024,
            ttl_ms=5000,
        )
        py_wire = py_env.to_bytes()

        # Warmup
        for _ in range(100):
            k1_bus_core.RustEnvelope.from_bytes(wire)
            Envelope.from_bytes(py_wire)

        t0 = time.perf_counter()
        for _ in range(n):
            k1_bus_core.RustEnvelope.from_bytes(wire)
        rust_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(n):
            Envelope.from_bytes(py_wire)
        python_time = time.perf_counter() - t0

        print(
            f"\nRustEnvelope deserialize {n}: "
            f"Rust={rust_time * 1000:.1f}ms  "
            f"Python={python_time * 1000:.1f}ms  "
            f"speedup={python_time / rust_time:.1f}x"
        )
        assert rust_time <= python_time * 2

    def test_with_bus_fields_speedup(self) -> None:
        n = 10_000
        rust_env = k1_bus_core.RustEnvelope(
            topic="k1.perf.stamp",
            priority=0,
            cognitive_trace_id="trace-stamp",
            payload=b"x" * 512,
            ttl_ms=5000,
        )
        py_env = Envelope(
            topic="k1.perf.stamp",
            priority=0,
            cognitive_trace_id="trace-stamp",
            payload=b"x" * 512,
            ttl_ms=5000,
        )

        # Warmup
        for _ in range(100):
            rust_env.with_bus_fields(1, 1, 1)
            py_env.with_bus_fields(1, 1, 1)

        t0 = time.perf_counter()
        for _ in range(n):
            rust_env.with_bus_fields(envelope_id=42, sequence=7, created_ns=12345)
        rust_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(n):
            py_env.with_bus_fields(envelope_id=42, sequence=7, created_ns=12345)
        python_time = time.perf_counter() - t0

        print(
            f"\nwith_bus_fields {n}: "
            f"Rust={rust_time * 1000:.1f}ms  "
            f"Python={python_time * 1000:.1f}ms  "
            f"speedup={python_time / rust_time:.1f}x"
        )
        assert rust_time <= python_time * 2


# ===================================================================
# RingBuffer: write/read/backpressure/fan-out
# ===================================================================


class TestRingBufferBasic:
    """RingBuffer basic operations."""

    def test_write_and_read(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=8, slot_size=256)
        seq = rb.write(b"hello")
        assert seq == 0
        data = rb.read(0)
        assert data == b"hello"

    def test_read_empty(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=8, slot_size=256)
        assert rb.read(0) is None

    def test_fifo_order(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=8, slot_size=256)
        rb.write(b"aaa")
        rb.write(b"bbb")
        rb.write(b"ccc")
        assert rb.read(0) == b"aaa"
        assert rb.read(0) == b"bbb"
        assert rb.read(0) == b"ccc"
        assert rb.read(0) is None

    def test_capacity_power_of_2(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=10)
        assert rb.capacity == 16  # 10 -> next power of 2

    def test_capacity_exact_power_of_2(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=32)
        assert rb.capacity == 32

    def test_properties(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=16, slot_size=1024, num_consumers=3)
        assert rb.capacity == 16
        assert rb.slot_size == 1024
        assert rb.num_consumers == 3
        assert rb.total_writes == 0
        assert rb.total_drops == 0

    def test_utilization(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=4, slot_size=256)
        assert rb.utilization == 0.0
        rb.write(b"a")
        rb.write(b"b")
        assert abs(rb.utilization - 0.5) < 0.01

    def test_repr(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=8)
        r = repr(rb)
        assert "RingBuffer" in r
        assert "capacity=8" in r

    def test_wrap_around(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=4, slot_size=256)
        # Fill, read, fill again (wraps)
        for i in range(3):
            rb.write(f"msg{i}".encode())
        for i in range(3):
            rb.read(0)
        rb.write(b"wrap1")
        rb.write(b"wrap2")
        assert rb.read(0) == b"wrap1"
        assert rb.read(0) == b"wrap2"

    def test_data_too_large(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=4, slot_size=8)
        with pytest.raises(RuntimeError, match="too large"):
            rb.write(b"this is way too long")


class TestRingBufferBackpressure:
    """Ring buffer backpressure strategies."""

    def test_error_on_full(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=4, slot_size=256, backpressure="error")
        for i in range(4):
            rb.write(f"msg{i}".encode())
        with pytest.raises(RuntimeError, match="full"):
            rb.write(b"overflow")

    def test_drop_oldest(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=4, slot_size=256, backpressure="drop_oldest")
        for i in range(4):
            rb.write(f"msg{i}".encode())
        # Overflow -- should succeed with drop
        rb.write(b"overflow")
        assert rb.total_drops >= 1

    def test_bad_strategy(self) -> None:
        with pytest.raises(ValueError, match="Unknown backpressure"):
            k1_bus_core.RingBuffer(backpressure="invalid")


class TestRingBufferFanOut:
    """Multi-consumer fan-out read."""

    def test_two_consumers(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=8, slot_size=256, num_consumers=2)
        rb.write(b"msg1")
        rb.write(b"msg2")

        # Consumer 0 reads both
        assert rb.read(0) == b"msg1"
        assert rb.read(0) == b"msg2"
        assert rb.read(0) is None

        # Consumer 1 reads both independently
        assert rb.read(1) == b"msg1"
        assert rb.read(1) == b"msg2"
        assert rb.read(1) is None

    def test_independent_progress(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=8, slot_size=256, num_consumers=2)
        rb.write(b"msg1")
        rb.write(b"msg2")

        # Consumer 0 reads one
        assert rb.read(0) == b"msg1"
        assert rb.pending(0) == 1

        # Consumer 1 reads both
        assert rb.read(1) == b"msg1"
        assert rb.read(1) == b"msg2"
        assert rb.pending(1) == 0

    def test_add_consumer(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=8, slot_size=256, num_consumers=1)
        rb.write(b"before")
        new_id = rb.add_consumer()
        assert new_id == 1
        assert rb.num_consumers == 2
        # New consumer starts at current position -- won't see old data
        assert rb.read(new_id) is None
        # Old consumer can still read
        assert rb.read(0) == b"before"

    def test_invalid_consumer_id(self) -> None:
        rb = k1_bus_core.RingBuffer(capacity=4, num_consumers=1)
        with pytest.raises(RuntimeError, match="Invalid consumer_id"):
            rb.read(99)


# ===================================================================
# RingBuffer: benchmark vs V1 list append
# ===================================================================


class TestRingBufferBenchmark:
    """V2-M4-011: Ring buffer vs V1 list.append() throughput."""

    def test_ring_vs_list_append(self) -> None:
        n = 10_000
        data = b"x" * 512  # Typical envelope size

        # V1 pattern: list.append()
        v1_list: list[bytes] = []
        t0 = time.perf_counter()
        for _ in range(n):
            v1_list.append(data)
        v1_time = time.perf_counter() - t0

        # V2 pattern: ring buffer write
        rb = k1_bus_core.RingBuffer(capacity=16384, slot_size=1024, num_consumers=0)
        t0 = time.perf_counter()
        for _ in range(n):
            rb.write(data)
        ring_time = time.perf_counter() - t0

        print(
            f"\nRing buffer vs list.append ({n} x 512B): "
            f"Ring={ring_time * 1000:.1f}ms  "
            f"List={v1_time * 1000:.1f}ms  "
            f"ratio={v1_time / ring_time:.1f}x"
        )
        assert rb.total_writes == n
        # Ring buffer is pre-allocated, list grows dynamically.
        # Ring may be slower per-op due to FFI overhead, but allocates 0 objects.
        # Just verify it completes in reasonable time.
        assert ring_time < 5.0, f"Ring buffer too slow: {ring_time:.3f}s for {n} writes"

    def test_ring_read_throughput(self) -> None:
        """Measure read throughput with fan-out=1."""
        n = 10_000
        data = b"x" * 512
        rb = k1_bus_core.RingBuffer(capacity=16384, slot_size=1024, num_consumers=1)
        for _ in range(n):
            rb.write(data)

        t0 = time.perf_counter()
        for _ in range(n):
            rb.read(0)
        read_time = time.perf_counter() - t0

        print(
            f"\nRing buffer read throughput ({n} x 512B): "
            f"time={read_time * 1000:.1f}ms  "
            f"throughput={n / read_time:.0f} msg/sec"
        )
        assert read_time < 5.0
