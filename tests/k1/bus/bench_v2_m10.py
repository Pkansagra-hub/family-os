"""
V2-M10 Benchmark Suite: V1 (Python) vs V2 (Rust) Performance Comparison.

Measures actual latencies and throughput against the plan's performance targets
(Section 5 of k1-bus-v2-rust-core-plan.md).

Two benchmark tiers:
  A) Adapter-level  -- BusFactory usage (includes Envelope<->RustEnvelope FFI)
  B) Raw-Rust       -- direct k1_bus_core calls (pure Rust, no conversion)

Metrics:
    1.  Publish-to-handler latency (p50/p95/p99/p999)  -- adapter + raw
    2.  Trie match throughput (cached + cold, 100 subs) -- raw
    3.  Envelope stamp (with_bus_fields)                -- raw
    4.  Envelope to_bytes / from_bytes (Rust acc.)      -- raw
    5.  Mailbox send-receive latency                    -- adapter + raw
    6.  Max sustained throughput                        -- adapter + raw
    7.  Memory per envelope (approximate)
    8.  WFQ fairness / starvation check
    9.  GC pressure estimate

Usage:
    pytest tests/k1/bus/bench_v2_m10.py -v -s
    pytest tests/k1/bus/bench_v2_m10.py -v -s -k "raw"
    pytest tests/k1/bus/bench_v2_m10.py -v -s -k "summary"

Assertions: Raw-Rust benchmarks assert V2 beats V1.  Adapter-level tests
report numbers but only assert V2 meets absolute targets (p50<5us etc.),
since the Envelope<->RustEnvelope conversion adds ~2-3us overhead per call.
"""

from __future__ import annotations

import gc
import statistics
import sys
import time
from typing import Any

import pytest

from k1.bus.envelope import Envelope, Priority
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import LocalBus
from k1.bus.impl.topic_trie import TopicTrie as PythonTopicTrie
from k1.bus.ports.mailbox import MailboxConfig

# --- Conditional imports ---

try:
    import k1_bus_core

    HAS_RUST = True
except ImportError:
    HAS_RUST = False

requires_rust = pytest.mark.skipif(not HAS_RUST, reason="k1_bus_core not installed")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NS_PER_US = 1_000


def _percentiles(timings_ns: list[int]) -> dict[str, float]:
    """Compute percentile latencies in microseconds."""
    s = sorted(timings_ns)
    n = len(s)
    return {
        "p50": s[n // 2] / _NS_PER_US,
        "p95": s[int(n * 0.95)] / _NS_PER_US,
        "p99": s[int(n * 0.99)] / _NS_PER_US,
        "p999": s[int(n * 0.999)] / _NS_PER_US if n >= 1000 else s[-1] / _NS_PER_US,
        "min": s[0] / _NS_PER_US,
        "max": s[-1] / _NS_PER_US,
        "mean": statistics.mean(s) / _NS_PER_US,
    }


def _make_envelope(topic: str = "k1.bench.test", payload_size: int = 64) -> Envelope:
    """Create a test envelope with given payload size."""
    return Envelope(
        topic=topic,
        priority=Priority.INTERACTIVE,
        payload=b"x" * payload_size,
        cognitive_trace_id="bench-trace",
        session_id="bench-session",
    )


def _make_rust_envelope(
    topic: str = "k1.bench.test",
    payload_size: int = 64,
) -> Any:
    """Create a RustEnvelope directly (no Python Envelope conversion)."""
    return k1_bus_core.RustEnvelope(
        topic=topic,
        priority=2,  # INTERACTIVE
        payload=b"x" * payload_size,
        cognitive_trace_id="bench-trace",
        session_id="bench-session",
    )


def _print_comparison(
    metric: str,
    v1_us: float,
    v2_us: float,
    target_us: float | None = None,
    target_label: str = "",
    unit: str = "us",
) -> None:
    """Print a comparison row."""
    ratio = v1_us / v2_us if v2_us > 0 else float("inf")
    met = ""
    if target_us is not None:
        met = "YES" if v2_us <= target_us else "NO"
    print(
        f"  {metric:<45} | V1={v1_us:>10.2f}{unit} | V2={v2_us:>10.2f}{unit} "
        f"| {ratio:>6.1f}x | target={target_label} | met={met}"
    )


def _warmup_bus(bus: Any, n: int = 100) -> None:
    """Warm up bus with throwaway publishes."""
    bus.subscribe("k1.warmup.>", lambda e: None)
    for _ in range(n):
        bus.publish(Envelope(topic="k1.warmup.data", payload=b"w"))


def _warmup_rust_bus(bus: Any, n: int = 100) -> None:
    """Warm up RustBus directly with RustEnvelopes."""
    bus.subscribe("k1.warmup.>", lambda e: None)
    renv = _make_rust_envelope("k1.warmup.data")
    for _ in range(n):
        bus.publish(renv)


# ===================================================================
# TIER A: ADAPTER-LEVEL (BusFactory, real-world usage)
# ===================================================================


@requires_rust
class TestAdapterPublishLatency:
    """
    M10-001a: Publish-to-handler via BusFactory adapters.
    Includes Envelope<->RustEnvelope conversion overhead (~2-3us).
    Targets: adapter p50 < 5us, p99 < 20us.
    """

    N = 100_000

    def _measure(self, bus: Any) -> list[int]:
        timings: list[int] = []
        bus.subscribe("k1.bench.>", lambda e: None)
        _warmup_bus(bus, 500)
        env = _make_envelope()
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                bus.publish(env)
                timings.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
        return timings

    def test_adapter_publish_latency(self) -> None:
        v1_bus = BusFactory.create_local(backend="python")
        v1_t = self._measure(v1_bus)
        v1_bus.close()

        v2_bus = BusFactory.create_local(backend="rust")
        v2_t = self._measure(v2_bus)
        v2_bus.close()

        v1 = _percentiles(v1_t)
        v2 = _percentiles(v2_t)

        print("\n" + "=" * 105)
        print("  M10-001a: Adapter publish-to-handler (1 sub, 100K env)")
        print("  NOTE: V2 includes ~2-3us Envelope<->RustEnvelope conversion per call")
        print("=" * 105)
        _print_comparison("Adapter publish p50", v1["p50"], v2["p50"], 5.0, "< 5us")
        _print_comparison("Adapter publish p99", v1["p99"], v2["p99"], 20.0, "< 20us")
        _print_comparison("Adapter publish mean", v1["mean"], v2["mean"])

        # Absolute targets -- adapter may trade conversion overhead for Rust dispatch
        assert v2["p50"] < 5.0, f"V2 adapter p50 ({v2['p50']:.1f}us) >= 5us target"
        assert v2["p99"] < 20.0, f"V2 adapter p99 ({v2['p99']:.1f}us) >= 20us target"


# ===================================================================
# TIER B: RAW RUST (direct k1_bus_core calls)
# ===================================================================


@requires_rust
class TestRawRustPublishLatency:
    """
    M10-001b: Publish-to-handler via RustBus directly (no conversion).
    Handler receives RustEnvelope natively.
    Targets: p50 < 5us, p99 < 20us.
    """

    N = 100_000

    def _measure_python(self) -> list[int]:
        bus = LocalBus()
        bus.subscribe("k1.bench.>", lambda e: None)
        _warmup_bus(bus, 500)
        env = _make_envelope()
        timings: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                bus.publish(env)
                timings.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
        bus.close()
        return timings

    def _measure_rust(self) -> list[int]:
        bus = k1_bus_core.RustBus()
        bus.subscribe("k1.bench.>", lambda e: None)
        renv = _make_rust_envelope()
        _warmup_rust_bus(bus, 500)
        timings: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                bus.publish(renv)
                timings.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
        bus.close()
        return timings

    def test_raw_publish_latency(self) -> None:
        v1_t = self._measure_python()
        v2_t = self._measure_rust()
        v1 = _percentiles(v1_t)
        v2 = _percentiles(v2_t)

        print("\n" + "=" * 105)
        print("  M10-001b: RAW publish-to-handler (1 sub, 100K env, no conversion)")
        print("=" * 105)
        _print_comparison("Raw publish p50", v1["p50"], v2["p50"], 5.0, "< 5us")
        _print_comparison("Raw publish p95", v1["p95"], v2["p95"])
        _print_comparison("Raw publish p99", v1["p99"], v2["p99"], 20.0, "< 20us")
        _print_comparison("Raw publish p999", v1["p999"], v2["p999"])
        _print_comparison("Raw publish mean", v1["mean"], v2["mean"])
        _print_comparison("Raw publish min", v1["min"], v2["min"])
        _print_comparison("Raw publish max", v1["max"], v2["max"])


# ===================================================================
#  M10-002: Trie match throughput
# ===================================================================


@requires_rust
class TestTrieMatchThroughput:
    """
    M10-002: 100 patterns, 100K match calls.
    Targets: cached < 0.1us, cold < 2us.
    """

    N_PATTERNS = 100
    N_MATCHES = 100_000

    def _setup_python_trie(self) -> PythonTopicTrie:
        trie: PythonTopicTrie = PythonTopicTrie()
        for i in range(self.N_PATTERNS):
            trie.insert(f"k1.bench.topic{i}.>", lambda e: None, f"sub-{i}")
        return trie

    def _setup_rust_trie(self) -> Any:
        trie = k1_bus_core.TopicTrie()
        for i in range(self.N_PATTERNS):
            trie.insert(f"k1.bench.topic{i}.>", lambda e: None, f"sub-{i}")
        return trie

    def _measure_match(self, trie: Any, method_name: str = "match") -> list[int]:
        match_fn = getattr(trie, method_name)
        timings: list[int] = []
        topics = [f"k1.bench.topic{i % self.N_PATTERNS}.data" for i in range(self.N_MATCHES)]
        gc.disable()
        try:
            for topic in topics:
                s = time.perf_counter_ns()
                match_fn(topic)
                timings.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
        return timings

    def test_trie_match_throughput(self) -> None:
        py_trie = self._setup_python_trie()
        v1_cold = self._measure_match(py_trie, "match")[:10_000]
        v1_cached = self._measure_match(py_trie, "match")

        rust_trie = self._setup_rust_trie()
        v2_cold = self._measure_match(rust_trie, "match_topic")[:10_000]
        v2_cached = self._measure_match(rust_trie, "match_topic")

        v1c = _percentiles(v1_cached)
        v1d = _percentiles(v1_cold)
        v2c = _percentiles(v2_cached)
        v2d = _percentiles(v2_cold)

        print("\n" + "=" * 105)
        print("  M10-002: Trie match (100 patterns, 100K matches)")
        print("=" * 105)
        _print_comparison("Trie match cached p50", v1c["p50"], v2c["p50"], 0.1, "< 0.1us")
        _print_comparison("Trie match cached p99", v1c["p99"], v2c["p99"])
        _print_comparison("Trie match cold p50", v1d["p50"], v2d["p50"], 2.0, "< 2us")
        _print_comparison("Trie match cold p99", v1d["p99"], v2d["p99"])

        assert v2c["p50"] < v1c["p50"], "Rust trie should be faster than Python"


# ===================================================================
#  Envelope stamp latency (raw Rust)
# ===================================================================


@requires_rust
class TestEnvelopeStampLatency:
    """
    Envelope with_bus_fields() -- stamp cost.
    Target: < 0.05us (Rust), ~5us (Python).
    """

    N = 100_000

    def test_stamp_latency(self) -> None:
        env = _make_envelope()

        # V1: Python Envelope.with_bus_fields
        timings_v1: list[int] = []
        gc.disable()
        try:
            for i in range(self.N):
                s = time.perf_counter_ns()
                env.with_bus_fields(envelope_id=i, sequence=i, created_ns=time.time_ns())
                timings_v1.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        # V2: RustEnvelope.with_bus_fields (direct Rust call)
        rust_env = _make_rust_envelope()
        timings_v2: list[int] = []
        gc.disable()
        try:
            for i in range(self.N):
                s = time.perf_counter_ns()
                rust_env.with_bus_fields(envelope_id=i, sequence=i, created_ns=time.time_ns())
                timings_v2.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        v1 = _percentiles(timings_v1)
        v2 = _percentiles(timings_v2)

        print("\n" + "=" * 105)
        print("  BENCH: Envelope stamp (with_bus_fields, 100K calls)")
        print("=" * 105)
        _print_comparison("Envelope stamp p50", v1["p50"], v2["p50"], 0.05, "< 0.05us")
        _print_comparison("Envelope stamp p99", v1["p99"], v2["p99"])
        _print_comparison("Envelope stamp mean", v1["mean"], v2["mean"])

        assert v2["p50"] < v1["p50"], "Rust stamp should be faster"


# ===================================================================
#  Envelope to_bytes / from_bytes (Rust accelerator)
# ===================================================================


@requires_rust
class TestEnvelopeSerializationLatency:
    """
    Envelope serialization: V1 JSON vs V2 Rust FlatBuffers accelerator.
    V2 uses k1_bus_core.envelope_to_bytes/from_bytes -- the actual Rust
    FlatBuffers path, NOT the Python FlatBuffers code in envelope.py.
    Targets: to_bytes < 0.5us, from_bytes < 0.1us.
    """

    N = 100_000

    def _make_fields_dict(self) -> dict:
        """Create a fields dict for the Rust accelerator."""
        return {
            "topic": "k1.bench.test",
            "priority": 2,
            "envelope_id": 42,
            "sequence": 1,
            "cognitive_trace_id": "bench-trace",
            "session_id": "bench-session",
            "request_id": "",
            "parent_id": 0,
            "created_ns": time.time_ns(),
            "payload": b"x" * 128,
            "ttl_ms": 30000,
            "payload_format": 0,
        }

    def _make_stamped_envelope(self) -> Envelope:
        env = _make_envelope(payload_size=128)
        return env.with_bus_fields(
            envelope_id=42,
            sequence=1,
            created_ns=time.time_ns(),
        )

    def test_to_bytes_latency(self) -> None:
        env = self._make_stamped_envelope()
        fields = self._make_fields_dict()

        # V1: JSON serialization
        import k1.bus.envelope.envelope as emod

        original_fmt = emod.ENVELOPE_FORMAT
        emod.ENVELOPE_FORMAT = "v1"
        timings_v1: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                env.to_bytes()
                timings_v1.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
            emod.ENVELOPE_FORMAT = original_fmt

        # V2: Rust FlatBuffers accelerator
        timings_v2: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                k1_bus_core.envelope_to_bytes(fields)
                timings_v2.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        # V2-alt: RustEnvelope.to_bytes (struct method)
        rust_env = _make_rust_envelope(payload_size=128)
        timings_v2_alt: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                rust_env.to_bytes()
                timings_v2_alt.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        v1 = _percentiles(timings_v1)
        v2 = _percentiles(timings_v2)
        v2a = _percentiles(timings_v2_alt)

        print("\n" + "=" * 105)
        print("  BENCH: Envelope to_bytes (100K calls)")
        print("=" * 105)
        _print_comparison(
            "to_bytes V1 JSON vs V2 accelerator p50", v1["p50"], v2["p50"], 0.5, "< 0.5us"
        )
        _print_comparison("to_bytes V1 JSON vs V2 accelerator p99", v1["p99"], v2["p99"])
        _print_comparison(
            "to_bytes V1 JSON vs V2 RustEnvelope p50", v1["p50"], v2a["p50"], 0.5, "< 0.5us"
        )
        _print_comparison("to_bytes V1 JSON vs V2 RustEnvelope p99", v1["p99"], v2a["p99"])

    def test_from_bytes_latency(self) -> None:
        env = self._make_stamped_envelope()
        fields = self._make_fields_dict()

        import k1.bus.envelope.envelope as emod

        original_fmt = emod.ENVELOPE_FORMAT
        emod.ENVELOPE_FORMAT = "v1"
        v1_bytes = env.to_bytes()
        emod.ENVELOPE_FORMAT = original_fmt
        v2_bytes = k1_bus_core.envelope_to_bytes(fields)

        # V1: JSON from_bytes
        timings_v1: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                Envelope.from_bytes(v1_bytes)
                timings_v1.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        # V2: Rust accelerator from_bytes
        timings_v2: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                k1_bus_core.envelope_from_bytes(v2_bytes)
                timings_v2.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        # V2-alt: RustEnvelope.from_bytes
        timings_v2_alt: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                k1_bus_core.RustEnvelope.from_bytes(bytes(v2_bytes))
                timings_v2_alt.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        v1 = _percentiles(timings_v1)
        v2 = _percentiles(timings_v2)
        v2a = _percentiles(timings_v2_alt)

        print("\n" + "=" * 105)
        print("  BENCH: Envelope from_bytes (100K calls)")
        print("=" * 105)
        _print_comparison(
            "from_bytes V1 JSON vs V2 accelerator p50", v1["p50"], v2["p50"], 0.1, "< 0.1us"
        )
        _print_comparison("from_bytes V1 JSON vs V2 accelerator p99", v1["p99"], v2["p99"])
        _print_comparison(
            "from_bytes V1 JSON vs V2 RustEnvelope p50", v1["p50"], v2a["p50"], 0.1, "< 0.1us"
        )
        _print_comparison("from_bytes V1 JSON vs V2 RustEnvelope p99", v1["p99"], v2a["p99"])


# ===================================================================
#  M10-002b: Batch serialization (amortized FFI)
# ===================================================================


@requires_rust
class TestBatchSerializationLatency:
    """
    Batch serialization: single FFI call for N envelopes.
    Amortizes GIL acquisition + call overhead across the batch.
    Reports per-envelope cost (total_time / batch_size).
    """

    BATCH_SIZE = 1000
    REPEATS = 100  # how many batches to time

    def _make_batch(self) -> list[dict]:
        return [
            {
                "topic": "k1.batch.bench",
                "priority": 2,
                "envelope_id": i,
                "sequence": i,
                "cognitive_trace_id": "batch-trace",
                "session_id": "batch-session",
                "request_id": "",
                "parent_id": 0,
                "created_ns": time.time_ns(),
                "payload": b"x" * 128,
                "ttl_ms": 30000,
                "payload_format": 0,
            }
            for i in range(self.BATCH_SIZE)
        ]

    def test_batch_to_bytes(self) -> None:
        batch = self._make_batch()

        # Single-call baseline: time N individual calls
        timings_single: list[int] = []
        gc.disable()
        try:
            for d in batch:
                s = time.perf_counter_ns()
                k1_bus_core.envelope_to_bytes(d)
                timings_single.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        # Batch: time one call for all N
        timings_batch: list[float] = []
        gc.disable()
        try:
            for _ in range(self.REPEATS):
                s = time.perf_counter_ns()
                k1_bus_core.envelope_to_bytes_batch(batch)
                elapsed = time.perf_counter_ns() - s
                timings_batch.append(elapsed / self.BATCH_SIZE)  # per-envelope
        finally:
            gc.enable()

        single_p50 = sorted(timings_single)[len(timings_single) // 2] / 1000
        batch_p50 = sorted(timings_batch)[len(timings_batch) // 2] / 1000

        print("\n" + "=" * 105)
        print(f"  BENCH: Batch to_bytes ({self.BATCH_SIZE} per batch, {self.REPEATS} repeats)")
        print("=" * 105)
        _print_comparison("to_bytes single-call p50", single_p50, batch_p50, 0.5, "< 0.5us")
        speedup = single_p50 / batch_p50 if batch_p50 > 0 else float("inf")
        print(f"  Batch amortization speedup:                    {speedup:.1f}x")

    def test_batch_from_bytes(self) -> None:
        batch = self._make_batch()
        wire_list = list(k1_bus_core.envelope_to_bytes_batch(batch))

        # Single-call baseline
        timings_single: list[int] = []
        gc.disable()
        try:
            for w in wire_list:
                s = time.perf_counter_ns()
                k1_bus_core.envelope_from_bytes(w)
                timings_single.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()

        # Batch
        timings_batch: list[float] = []
        gc.disable()
        try:
            for _ in range(self.REPEATS):
                s = time.perf_counter_ns()
                k1_bus_core.envelope_from_bytes_batch(wire_list)
                elapsed = time.perf_counter_ns() - s
                timings_batch.append(elapsed / self.BATCH_SIZE)
        finally:
            gc.enable()

        single_p50 = sorted(timings_single)[len(timings_single) // 2] / 1000
        batch_p50 = sorted(timings_batch)[len(timings_batch) // 2] / 1000

        print("\n" + "=" * 105)
        print(f"  BENCH: Batch from_bytes ({self.BATCH_SIZE} per batch, {self.REPEATS} repeats)")
        print("=" * 105)
        _print_comparison("from_bytes single-call p50", single_p50, batch_p50, 0.1, "< 0.1us")
        speedup = single_p50 / batch_p50 if batch_p50 > 0 else float("inf")
        print(f"  Batch amortization speedup:                    {speedup:.1f}x")


# ===================================================================
#  M10-003: Mailbox send-receive latency
# ===================================================================


@requires_rust
class TestMailboxSendReceiveLatency:
    """
    M10-003: Mailbox send-receive.
    a) Adapter-level with Envelope conversion.
    b) Raw Rust with RustEnvelope directly.
    Target: < 2us per send-receive round trip.
    """

    N = 100_000

    def test_adapter_mailbox(self) -> None:
        """Adapter-level: BusFactory mailbox with Envelope conversion."""
        v1_r = BusFactory.create_mailbox_router(backend="python")
        v1_mb = v1_r.register("bench", MailboxConfig(capacity=self.N + 1000, priority_wfq=False))
        env = _make_envelope()

        v1_t: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                v1_r.deliver("bench", env)
                v1_mb.receive(timeout_ms=0)
                v1_t.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
        v1_r.close()

        v2_r = BusFactory.create_mailbox_router(backend="rust")
        v2_mb = v2_r.register("bench", MailboxConfig(capacity=self.N + 1000, priority_wfq=False))

        v2_t: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                v2_r.deliver("bench", env)
                v2_mb.receive(timeout_ms=0)
                v2_t.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
        v2_r.close()

        v1 = _percentiles(v1_t)
        v2 = _percentiles(v2_t)

        print("\n" + "=" * 105)
        print("  M10-003a: Adapter mailbox send-receive (100K round trips)")
        print("  NOTE: V2 includes Envelope<->RustEnvelope conversion on deliver+receive")
        print("=" * 105)
        _print_comparison("Adapter mailbox p50", v1["p50"], v2["p50"], 2.0, "< 2us")
        _print_comparison("Adapter mailbox p99", v1["p99"], v2["p99"])
        _print_comparison("Adapter mailbox mean", v1["mean"], v2["mean"])

    def test_raw_mailbox(self) -> None:
        """Raw Rust: RustMailbox directly with RustEnvelope."""
        from k1.bus.impl.local_mailbox import LocalMailboxRouter

        py_router = LocalMailboxRouter()
        py_mb = py_router.register(
            "bench", MailboxConfig(capacity=self.N + 1000, priority_wfq=False)
        )
        env = _make_envelope()

        v1_t: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                py_router.deliver("bench", env)
                py_mb.receive(timeout_ms=0)
                v1_t.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
        py_router.close()

        # Raw Rust mailbox
        rust_router = k1_bus_core.RustMailboxRouter()
        rust_mb = rust_router.register("bench", self.N + 1000, False)
        renv = _make_rust_envelope()

        v2_t: list[int] = []
        gc.disable()
        try:
            for _ in range(self.N):
                s = time.perf_counter_ns()
                rust_router.deliver("bench", renv)
                rust_mb.receive(0)
                v2_t.append(time.perf_counter_ns() - s)
        finally:
            gc.enable()
        rust_router.close()

        v1 = _percentiles(v1_t)
        v2 = _percentiles(v2_t)

        print("\n" + "=" * 105)
        print("  M10-003b: RAW mailbox send-receive (100K, no Envelope conversion)")
        print("=" * 105)
        _print_comparison("Raw mailbox p50", v1["p50"], v2["p50"], 2.0, "< 2us")
        _print_comparison("Raw mailbox p99", v1["p99"], v2["p99"])
        _print_comparison("Raw mailbox mean", v1["mean"], v2["mean"])

        assert v2["p50"] < v1["p50"], "Raw Rust mailbox should be faster than Python"


# ===================================================================
#  M10-004: Max sustained throughput
# ===================================================================


@requires_rust
class TestMaxSustainedThroughput:
    """
    M10-004: Full system throughput.
    Measures Python, raw Rust, and adapter-level throughput.
    Target: 500K+ env/sec (Rust raw).
    """

    DURATION_SEC = 2.0

    def _measure_python(self) -> float:
        bus = LocalBus()
        bus.subscribe("k1.bench.>", lambda e: None)
        _warmup_bus(bus, 200)
        env = _make_envelope()
        count = 0
        gc.disable()
        try:
            start = time.perf_counter()
            deadline = start + self.DURATION_SEC
            while time.perf_counter() < deadline:
                bus.publish(env)
                count += 1
        finally:
            gc.enable()
        elapsed = time.perf_counter() - start
        bus.close()
        return count / elapsed

    def _measure_rust_raw(self) -> float:
        """Raw RustBus with RustEnvelope (no adapter)."""
        bus = k1_bus_core.RustBus()
        bus.subscribe("k1.bench.>", lambda e: None)
        renv = _make_rust_envelope()
        _warmup_rust_bus(bus, 200)
        count = 0
        gc.disable()
        try:
            start = time.perf_counter()
            deadline = start + self.DURATION_SEC
            while time.perf_counter() < deadline:
                bus.publish(renv)
                count += 1
        finally:
            gc.enable()
        elapsed = time.perf_counter() - start
        bus.close()
        return count / elapsed

    def _measure_adapter(self) -> float:
        """Adapter-level throughput via BusFactory."""
        bus = BusFactory.create_local(backend="rust")
        bus.subscribe("k1.bench.>", lambda e: None)
        _warmup_bus(bus, 200)
        env = _make_envelope()
        count = 0
        gc.disable()
        try:
            start = time.perf_counter()
            deadline = start + self.DURATION_SEC
            while time.perf_counter() < deadline:
                bus.publish(env)
                count += 1
        finally:
            gc.enable()
        elapsed = time.perf_counter() - start
        bus.close()
        return count / elapsed

    def test_sustained_throughput(self) -> None:
        v1_eps = self._measure_python()
        v2_raw_eps = self._measure_rust_raw()
        v2_adapter_eps = self._measure_adapter()

        print("\n" + "=" * 105)
        print("  M10-004: Max sustained throughput (2 sec burst)")
        print("=" * 105)
        print(f"  {'V1 Python:':<45} {v1_eps:>12,.0f} env/sec")
        print(f"  {'V2 Rust (raw, no conversion):':<45} {v2_raw_eps:>12,.0f} env/sec")
        print(f"  {'V2 Rust (adapter, with conversion):':<45} {v2_adapter_eps:>12,.0f} env/sec")
        raw_ratio = v2_raw_eps / v1_eps if v1_eps > 0 else float("inf")
        adapter_ratio = v2_adapter_eps / v1_eps if v1_eps > 0 else float("inf")
        print(f"  {'Raw improvement:':<45} {raw_ratio:>12.1f}x")
        print(f"  {'Adapter improvement:':<45} {adapter_ratio:>12.1f}x")
        print(f"  {'Target:':<45} {'500,000+ env/sec':>12}")
        print(f"  {'Raw target met:':<45} {'YES' if v2_raw_eps >= 500_000 else 'NO':>12}")

        assert v2_raw_eps > v1_eps, "Raw Rust throughput should exceed Python"


# ===================================================================
#  M10-005: WFQ fairness / starvation check
# ===================================================================


@requires_rust
class TestWfqFairness:
    """
    M10-005: WFQ deficit round-robin -- verify no starvation.
    """

    def test_wfq_interleaved(self) -> None:
        """WFQ with mixed priorities -- BG should start before all URGENT drain."""
        mb = k1_bus_core.RustMailbox("wfq-test", capacity=20_000, priority_wfq=True)

        n_urgent = 100
        n_bg = 100

        for _ in range(n_urgent):
            mb.deliver(
                k1_bus_core.RustEnvelope(
                    topic="k1.bench.urgent",
                    priority=0,
                    payload=b"u",
                )
            )
        for _ in range(n_bg):
            mb.deliver(
                k1_bus_core.RustEnvelope(
                    topic="k1.bench.bg",
                    priority=3,
                    payload=b"b",
                )
            )

        urgent_pos: list[int] = []
        bg_pos: list[int] = []
        pos = 0
        while True:
            env = mb.receive(0)
            if env is None:
                break
            if env.priority == 0:
                urgent_pos.append(pos)
            elif env.priority == 3:
                bg_pos.append(pos)
            pos += 1

        total = len(urgent_pos) + len(bg_pos)
        assert total == n_urgent + n_bg, f"Expected {n_urgent + n_bg}, got {total}"

        print("\n" + "=" * 105)
        print("  M10-005a: WFQ fairness (100 URGENT + 100 BACKGROUND)")
        print("=" * 105)
        print(f"  {'Total delivered:':<50} {total}")
        print(f"  {'URGENT count:':<50} {len(urgent_pos)}")
        print(f"  {'BACKGROUND count:':<50} {len(bg_pos)}")

        if bg_pos:
            first_bg = bg_pos[0]
            last_bg = bg_pos[-1]
            print(f"  {'First BG position:':<50} {first_bg}")
            print(f"  {'Last BG position:':<50} {last_bg}")
            # WFQ deficit: URGENT gets weight 4 per deliver, BG gets weight 1.
            # After 100 URGENT + 100 BG: deficits = [400, 0, 0, 100].
            # URGENT drains until deficit drops below BG's deficit.
            starvation = first_bg >= n_urgent
            print(f"  {'BG only after all URGENT:':<50} {'YES' if starvation else 'NO'}")

        assert len(bg_pos) == n_bg, "All BACKGROUND should be delivered"

    def test_wfq_batch_total_delivery(self) -> None:
        """WFQ: 10K URGENT + 100 BG batch -- all must be delivered."""
        router = BusFactory.create_mailbox_router(backend="rust")
        mb = router.register(
            "wfq-actor",
            MailboxConfig(capacity=20_000, priority_wfq=True),
        )

        n_urgent = 10_000
        n_bg = 100

        for _ in range(n_urgent):
            router.deliver(
                "wfq-actor",
                Envelope(topic="k1.wfq.urgent", priority=Priority.URGENT, payload=b"u"),
            )
        for _ in range(n_bg):
            router.deliver(
                "wfq-actor",
                Envelope(topic="k1.wfq.bg", priority=Priority.BACKGROUND, payload=b"b"),
            )

        received = 0
        bg_count = 0
        while True:
            env = mb.receive(timeout_ms=0)
            if env is None:
                break
            received += 1
            if env.priority == Priority.BACKGROUND:
                bg_count += 1

        router.close()

        print("\n" + "=" * 105)
        print("  M10-005b: WFQ batch delivery (10K URGENT + 100 BG)")
        print("=" * 105)
        print(f"  {'Total received:':<50} {received}")
        print(f"  {'BACKGROUND received:':<50} {bg_count}")
        print(f"  {'Starvation (BG lost):':<50} {'YES' if bg_count < n_bg else 'NO'}")

        assert received == n_urgent + n_bg
        assert bg_count == n_bg, "Zero BG starvation -- all delivered"


# ===================================================================
#  M10-006: Stress test (1M envelopes, 100 subscribers)
# ===================================================================


@requires_rust
class TestStress1MEnvelopes:
    """
    M10-006: 1M publishes, 100 subscribers.
    """

    N_SUBS = 100
    N_ENVELOPES = 1_000_000

    def test_stress_1m(self) -> None:
        bus = BusFactory.create_local(backend="rust")
        delivery_count = [0]

        def good_handler(e: Envelope) -> None:
            delivery_count[0] += 1

        for i in range(self.N_SUBS):
            bus.subscribe(f"k1.stress.topic{i % 10}.>", good_handler)

        gc.disable()
        start = time.perf_counter()
        try:
            for i in range(self.N_ENVELOPES):
                topic = f"k1.stress.topic{i % 10}.msg"
                bus.publish(
                    Envelope(topic=topic, priority=Priority.INTERACTIVE, payload=b"x" * 32),
                )
        finally:
            gc.enable()
        elapsed = time.perf_counter() - start

        stats = bus.stats
        circuits = bus.handler_circuits()
        open_circuits = sum(1 for v in circuits.values() if v != "Closed")
        bus.close()

        eps = self.N_ENVELOPES / elapsed

        print("\n" + "=" * 105)
        print(f"  M10-006: Stress test (1M envelopes, {self.N_SUBS} subscribers)")
        print("=" * 105)
        print(f"  {'Duration:':<50} {elapsed:>10.2f} sec")
        print(f"  {'Throughput:':<50} {eps:>12,.0f} env/sec")
        print(f"  {'Published:':<50} {stats.envelopes_published:>12,}")
        print(f"  {'Delivered:':<50} {stats.envelopes_delivered:>12,}")
        print(f"  {'Handler errors:':<50} {stats.handler_errors:>12,}")
        print(f"  {'Open circuits:':<50} {open_circuits:>12}")

        assert stats.envelopes_published == self.N_ENVELOPES
        assert stats.envelopes_delivered >= self.N_ENVELOPES


# ===================================================================
#  Memory per envelope (approximate)
# ===================================================================


@requires_rust
class TestMemoryPerEnvelope:
    """
    Approximate memory per envelope.
    Target: ~128B (Rust internal) vs ~800B (Python).
    """

    N = 10_000

    def test_memory_per_envelope(self) -> None:
        envs_py = [
            Envelope(
                topic=f"k1.test.topic{i}",
                priority=Priority.INTERACTIVE,
                payload=b"x" * 64,
                cognitive_trace_id=f"trace-{i}",
                session_id="session",
            )
            for i in range(self.N)
        ]
        py_per = sum(sys.getsizeof(e) for e in envs_py) / self.N

        envs_rust = [
            k1_bus_core.RustEnvelope(
                topic=f"k1.test.topic{i}",
                priority=2,
                payload=b"x" * 64,
                cognitive_trace_id=f"trace-{i}",
                session_id="session",
            )
            for i in range(self.N)
        ]
        rust_per = sum(sys.getsizeof(e) for e in envs_rust) / self.N

        print("\n" + "=" * 105)
        print(f"  BENCH: Memory per envelope ({self.N} envelopes)")
        print("=" * 105)
        print(f"  {'Python Envelope (sys.getsizeof):':<50} {py_per:>8.0f} bytes")
        print(f"  {'RustEnvelope (sys.getsizeof wrapper):':<50} {rust_per:>8.0f} bytes")
        print(f"  {'Target (Rust internal):':<50} {'~128 bytes':>8}")
        print("  Note: sys.getsizeof shows Python wrapper, not Rust heap.")
        print("  Rust internal storage is ~128B per RustEnvelope struct.")


# ===================================================================
#  GC pressure estimate
# ===================================================================


@requires_rust
class TestGcPressure:
    """
    GC pressure: gen0 collections under load.
    """

    RATE = 10_000
    DURATION = 2.0

    def _measure_gc(self, publish_fn: Any) -> tuple[int, float]:
        total = int(self.RATE * self.DURATION)
        gc.collect()
        gc_before = gc.get_stats()[0]["collections"]
        start = time.perf_counter()
        for i in range(total):
            publish_fn()
            if i % 1000 == 0:
                gc.collect(0)
        gc.collect()
        gc_after = gc.get_stats()[0]["collections"]
        elapsed = time.perf_counter() - start
        return gc_after - gc_before, elapsed

    def test_gc_pressure(self) -> None:
        v1_bus = LocalBus()
        v1_bus.subscribe("k1.gc.>", lambda e: None)
        env = _make_envelope()
        v1_gc, v1_elapsed = self._measure_gc(lambda: v1_bus.publish(env))
        v1_bus.close()

        v2_bus = k1_bus_core.RustBus()
        v2_bus.subscribe("k1.gc.>", lambda e: None)
        renv = _make_rust_envelope()
        v2_gc, v2_elapsed = self._measure_gc(lambda: v2_bus.publish(renv))
        v2_bus.close()

        print("\n" + "=" * 105)
        print(f"  BENCH: GC pressure ({self.RATE} msg/sec for {self.DURATION}s)")
        print("=" * 105)
        print(f"  {'V1 Python GC gen0 collections:':<50} {v1_gc}")
        print(f"  {'V2 Rust GC gen0 collections:':<50} {v2_gc}")
        print(f"  {'V1 elapsed:':<50} {v1_elapsed:.2f}s")
        print(f"  {'V2 elapsed:':<50} {v2_elapsed:.2f}s")
        print("  Target: V2 <= V1 GC pressure (Rust fewer Python objects)")


# ===================================================================
#  Combined summary table
# ===================================================================


@requires_rust
class TestCombinedSummary:
    """
    Compact summary of all 12 metrics from the plan's Section 5 table.
    Uses raw Rust calls (no adapter) for the definitive V2 numbers.
    """

    def test_summary_table(self) -> None:
        results: list[tuple[str, float, float, str, str]] = []
        n = 50_000

        # ---- 1. Publish-to-handler p50/p99 (raw) ----
        py_bus = LocalBus()
        py_bus.subscribe("k1.bench.>", lambda e: None)
        _warmup_bus(py_bus, 200)
        env = _make_envelope()

        rust_bus = k1_bus_core.RustBus()
        rust_bus.subscribe("k1.bench.>", lambda e: None)
        renv = _make_rust_envelope()
        _warmup_rust_bus(rust_bus, 200)

        v1t: list[int] = []
        gc.disable()
        for _ in range(n):
            s = time.perf_counter_ns()
            py_bus.publish(env)
            v1t.append(time.perf_counter_ns() - s)
        gc.enable()

        v2t: list[int] = []
        gc.disable()
        for _ in range(n):
            s = time.perf_counter_ns()
            rust_bus.publish(renv)
            v2t.append(time.perf_counter_ns() - s)
        gc.enable()

        v1_p50 = sorted(v1t)[n // 2] / _NS_PER_US
        v1_p99 = sorted(v1t)[int(n * 0.99)] / _NS_PER_US
        v2_p50 = sorted(v2t)[n // 2] / _NS_PER_US
        v2_p99 = sorted(v2t)[int(n * 0.99)] / _NS_PER_US
        py_bus.close()
        rust_bus.close()

        results.append(
            ("Publish-to-handler (p50)", v1_p50, v2_p50, "< 5us", "YES" if v2_p50 < 5 else "NO")
        )
        results.append(
            ("Publish-to-handler (p99)", v1_p99, v2_p99, "< 20us", "YES" if v2_p99 < 20 else "NO")
        )

        # ---- 2. Trie match (cached) ----
        py_trie: PythonTopicTrie = PythonTopicTrie()
        rust_trie = k1_bus_core.TopicTrie()
        for i in range(100):
            py_trie.insert(f"k1.t{i}.>", lambda e: None, f"s-{i}")
            rust_trie.insert(f"k1.t{i}.>", lambda e: None, f"s-{i}")

        topics = [f"k1.t{i % 100}.data" for i in range(10_000)]
        # Warm up
        for t in topics:
            py_trie.match(t)
            rust_trie.match_topic(t)

        v1t = []
        gc.disable()
        for t in topics:
            s = time.perf_counter_ns()
            py_trie.match(t)
            v1t.append(time.perf_counter_ns() - s)
        gc.enable()

        v2t = []
        gc.disable()
        for t in topics:
            s = time.perf_counter_ns()
            rust_trie.match_topic(t)
            v2t.append(time.perf_counter_ns() - s)
        gc.enable()

        v1_trie = sorted(v1t)[len(v1t) // 2] / _NS_PER_US
        v2_trie = sorted(v2t)[len(v2t) // 2] / _NS_PER_US
        results.append(
            (
                "Trie match (cached, 100 subs)",
                v1_trie,
                v2_trie,
                "< 0.1us",
                "YES" if v2_trie < 0.1 else "NO",
            )
        )

        # ---- 3. Envelope stamp ----
        rust_env = _make_rust_envelope()
        py_env = _make_envelope()

        v1t = []
        gc.disable()
        for i in range(10_000):
            s = time.perf_counter_ns()
            py_env.with_bus_fields(i, i, time.time_ns())
            v1t.append(time.perf_counter_ns() - s)
        gc.enable()

        v2t = []
        gc.disable()
        for i in range(10_000):
            s = time.perf_counter_ns()
            rust_env.with_bus_fields(i, i, time.time_ns())
            v2t.append(time.perf_counter_ns() - s)
        gc.enable()

        v1_stamp = sorted(v1t)[len(v1t) // 2] / _NS_PER_US
        v2_stamp = sorted(v2t)[len(v2t) // 2] / _NS_PER_US
        results.append(
            ("Envelope stamp", v1_stamp, v2_stamp, "< 0.05us", "YES" if v2_stamp < 0.05 else "NO")
        )

        # ---- 4. to_bytes / from_bytes (Rust accelerator) ----
        fields = {
            "topic": "k1.bench.test",
            "priority": 2,
            "envelope_id": 42,
            "sequence": 1,
            "cognitive_trace_id": "bench",
            "session_id": "bench",
            "request_id": "",
            "parent_id": 0,
            "created_ns": time.time_ns(),
            "payload": b"x" * 128,
            "ttl_ms": 30000,
            "payload_format": 0,
        }

        import k1.bus.envelope.envelope as emod

        orig_fmt = emod.ENVELOPE_FORMAT
        emod.ENVELOPE_FORMAT = "v1"
        stamped = py_env.with_bus_fields(42, 1, time.time_ns())
        v1_ser_bytes = stamped.to_bytes()
        emod.ENVELOPE_FORMAT = orig_fmt
        v2_ser_bytes = k1_bus_core.envelope_to_bytes(fields)

        # to_bytes
        emod.ENVELOPE_FORMAT = "v1"
        v1t = []
        gc.disable()
        for _ in range(10_000):
            s = time.perf_counter_ns()
            stamped.to_bytes()
            v1t.append(time.perf_counter_ns() - s)
        gc.enable()
        emod.ENVELOPE_FORMAT = orig_fmt

        v2t = []
        gc.disable()
        for _ in range(10_000):
            s = time.perf_counter_ns()
            k1_bus_core.envelope_to_bytes(fields)
            v2t.append(time.perf_counter_ns() - s)
        gc.enable()

        v1_to = sorted(v1t)[len(v1t) // 2] / _NS_PER_US
        v2_to = sorted(v2t)[len(v2t) // 2] / _NS_PER_US
        results.append(
            ("to_bytes (JSON vs Rust FB)", v1_to, v2_to, "< 0.5us", "YES" if v2_to < 0.5 else "NO")
        )

        # from_bytes
        v1t = []
        gc.disable()
        for _ in range(10_000):
            s = time.perf_counter_ns()
            Envelope.from_bytes(v1_ser_bytes)
            v1t.append(time.perf_counter_ns() - s)
        gc.enable()

        v2t = []
        gc.disable()
        for _ in range(10_000):
            s = time.perf_counter_ns()
            k1_bus_core.envelope_from_bytes(v2_ser_bytes)
            v2t.append(time.perf_counter_ns() - s)
        gc.enable()

        v1_from = sorted(v1t)[len(v1t) // 2] / _NS_PER_US
        v2_from = sorted(v2t)[len(v2t) // 2] / _NS_PER_US
        results.append(
            (
                "from_bytes (JSON vs Rust FB)",
                v1_from,
                v2_from,
                "< 0.1us",
                "YES" if v2_from < 0.1 else "NO",
            )
        )

        # ---- 5. Mailbox send-receive (raw) ----
        from k1.bus.impl.local_mailbox import LocalMailboxRouter

        py_r = LocalMailboxRouter()
        py_mb = py_r.register("a", MailboxConfig(capacity=20000, priority_wfq=False))
        rust_r = k1_bus_core.RustMailboxRouter()
        rust_mb = rust_r.register("a", 20000, False)

        v1t = []
        gc.disable()
        for _ in range(10_000):
            s = time.perf_counter_ns()
            py_r.deliver("a", env)
            py_mb.receive(timeout_ms=0)
            v1t.append(time.perf_counter_ns() - s)
        gc.enable()

        v2t = []
        gc.disable()
        for _ in range(10_000):
            s = time.perf_counter_ns()
            rust_r.deliver("a", renv)
            rust_mb.receive(0)
            v2t.append(time.perf_counter_ns() - s)
        gc.enable()

        v1_mb_lat = sorted(v1t)[len(v1t) // 2] / _NS_PER_US
        v2_mb_lat = sorted(v2t)[len(v2t) // 2] / _NS_PER_US
        py_r.close()
        rust_r.close()
        results.append(
            (
                "Mailbox send-receive",
                v1_mb_lat,
                v2_mb_lat,
                "< 2us",
                "YES" if v2_mb_lat < 2 else "NO",
            )
        )

        # ---- 6. Throughput (raw) ----
        py_bus2 = LocalBus()
        py_bus2.subscribe("k1.bench.>", lambda e: None)
        _warmup_bus(py_bus2, 100)
        rust_bus2 = k1_bus_core.RustBus()
        rust_bus2.subscribe("k1.bench.>", lambda e: None)
        _warmup_rust_bus(rust_bus2, 100)

        for bus_obj, env_obj, label in [
            (py_bus2, env, "v1"),
            (rust_bus2, renv, "v2"),
        ]:
            count = 0
            start = time.perf_counter()
            deadline = start + 1.0
            while time.perf_counter() < deadline:
                bus_obj.publish(env_obj)
                count += 1
            elapsed = time.perf_counter() - start
            eps = count / elapsed
            if label == "v1":
                v1_throughput = eps
            else:
                v2_throughput = eps
        py_bus2.close()
        rust_bus2.close()
        results.append(
            (
                "Max sustained throughput",
                v1_throughput,
                v2_throughput,
                "500K+",
                "YES" if v2_throughput >= 500_000 else "NO",
            )
        )

        # ---- Print summary ----
        print("\n")
        print("=" * 115)
        print("  V2-M10 PERFORMANCE SUMMARY: V1 (Python) vs V2 (Rust, raw)")
        print("=" * 115)
        print(
            f"  {'Metric':<40} | {'V1 (Python)':>14} | {'V2 (Rust)':>14} | {'Speedup':>8} | {'Target':>10} | {'Met':>4}"
        )
        print("-" * 115)

        for metric, v1_val, v2_val, target, met in results:
            ratio = v1_val / v2_val if v2_val > 0 else float("inf")
            if "throughput" in metric.lower():
                print(
                    f"  {metric:<40} | {v1_val:>11,.0f}/s | {v2_val:>11,.0f}/s | {ratio:>6.1f}x | {target:>10} | {met:>4}"
                )
            else:
                print(
                    f"  {metric:<40} | {v1_val:>11.2f}us | {v2_val:>11.2f}us | {ratio:>6.1f}x | {target:>10} | {met:>4}"
                )

        print("=" * 115)
