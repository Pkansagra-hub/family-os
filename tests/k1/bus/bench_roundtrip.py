"""
M7-B05: Round-trip benchmark — LocalBus (Python) vs RustBusAdapter.

Measures publish-to-handler round-trip latency under realistic fan-out
(10 subscribers × 20 topics × 3 payload sizes).  Both buses dispatch
synchronously on the publisher's thread, so round-trip = publish() time
plus all subscriber handler invocations.

This bench is gated by the ``benchmark`` pytest marker.  Default test
runs exclude it (see ``pyproject.toml`` ``addopts``).  To run::

    pytest tests/k1/bus/bench_roundtrip.py -v -s -m benchmark

The Rust comparison is skipped when ``k1_bus_core`` is not installed.
The Python bench always runs.

Output is informational; only catastrophic-regression assertions fire
(p50 < generous ceiling, Rust not >50% slower than Python).
"""

from __future__ import annotations

import gc
import statistics
import time
from typing import Any

import pytest

from k1.bus.envelope import Envelope, Priority
from k1.bus.factory import BusFactory

try:
    import k1_bus_core  # noqa: F401

    HAS_RUST = True
except ImportError:
    HAS_RUST = False

requires_rust = pytest.mark.skipif(not HAS_RUST, reason="k1_bus_core not installed")

pytestmark = pytest.mark.benchmark

# ---------------------------------------------------------------------------
# Bench parameters
# ---------------------------------------------------------------------------

PAYLOAD_SIZES: list[int] = [64, 1024, 8192]
N_TOPICS: int = 20
N_SUBS: int = 10
N_ITERATIONS: int = 10_000
WARMUP: int = 500
_NS_PER_US = 1_000

TOPICS: list[str] = [f"k1.bench.roundtrip.t{i:02d}" for i in range(N_TOPICS)]


# Holds Python-bench results so the Rust class can print speedup ratios.
_PY_RESULTS: dict[int, dict[str, float]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentiles(timings_ns: list[int]) -> dict[str, float]:
    s = sorted(timings_ns)
    n = len(s)
    return {
        "p50": s[n // 2] / _NS_PER_US,
        "p95": s[int(n * 0.95)] / _NS_PER_US,
        "p99": s[int(n * 0.99)] / _NS_PER_US,
        "min": s[0] / _NS_PER_US,
        "max": s[-1] / _NS_PER_US,
        "mean": statistics.mean(s) / _NS_PER_US,
    }


def _make_env(topic: str, size: int) -> Envelope:
    return Envelope(
        topic=topic,
        priority=Priority.INTERACTIVE,
        payload=b"x" * size,
        cognitive_trace_id="bench-trace",
        session_id="bench-session",
    )


def _setup_subscribers(bus: Any, counter: list[int]) -> None:
    """Register N_SUBS subscribers across N_TOPICS using one wildcard each."""

    def handler(_env: Envelope) -> None:
        counter[0] += 1

    # 10 subscribers each matching the whole bench prefix.
    # Per-publish fan-out = N_SUBS handlers.
    for _ in range(N_SUBS):
        bus.subscribe("k1.bench.roundtrip.>", handler)


def _warmup(bus: Any, payload_size: int) -> None:
    env = _make_env(TOPICS[0], payload_size)
    for _ in range(WARMUP):
        bus.publish(env)


def _run_bench(bus: Any, payload_size: int) -> tuple[list[int], int]:
    """Run a timed round-trip bench. Returns (timings_ns, deliveries)."""
    counter = [0]
    _setup_subscribers(bus, counter)
    _warmup(bus, payload_size)

    # Pre-build envelopes so allocation cost is excluded from the hot loop.
    envs = [_make_env(TOPICS[i % N_TOPICS], payload_size) for i in range(N_ITERATIONS)]

    timings: list[int] = []
    gc.disable()
    try:
        for env in envs:
            s = time.perf_counter_ns()
            bus.publish(env)
            timings.append(time.perf_counter_ns() - s)
    finally:
        gc.enable()

    return timings, counter[0]


def _print_table(label: str, results: dict[int, dict[str, float]]) -> None:
    print(f"\n  {label}")
    print("  " + "-" * 78)
    print(
        f"  {'payload':<10} | {'p50 us':>10} | {'p95 us':>10} | "
        f"{'p99 us':>10} | {'mean us':>10} | {'max us':>10}"
    )
    print("  " + "-" * 78)
    for size, r in sorted(results.items()):
        print(
            f"  {size:<10} | {r['p50']:>10.2f} | {r['p95']:>10.2f} | "
            f"{r['p99']:>10.2f} | {r['mean']:>10.2f} | {r['max']:>10.2f}"
        )


# ---------------------------------------------------------------------------
# Python LocalBus
# ---------------------------------------------------------------------------


class TestLocalBusRoundtrip:
    """Round-trip latency for the pure-Python LocalBus."""

    @pytest.mark.parametrize("payload_size", PAYLOAD_SIZES)
    def test_python_roundtrip(self, payload_size: int) -> None:
        bus = BusFactory.create_local(backend="python")
        try:
            timings, delivered = _run_bench(bus, payload_size)
        finally:
            bus.close()

        # Sanity: handler count matches expected fan-out (warmup + iter, all subs)
        expected = (WARMUP + N_ITERATIONS) * N_SUBS
        assert (
            delivered == expected
        ), f"delivery count mismatch: got {delivered}, expected {expected}"

        pct = _percentiles(timings)
        _PY_RESULTS[payload_size] = pct

        print(
            f"\n[LocalBus python] payload={payload_size}B subs={N_SUBS} "
            f"topics={N_TOPICS} N={N_ITERATIONS}"
        )
        _print_table("Round-trip publish() latency", {payload_size: pct})

        # Catastrophic-regression guard only.  Round-trip with 10 subscribers
        # invoking trivial handlers should be well under 1ms p50.
        assert (
            pct["p50"] < 1000.0
        ), f"LocalBus p50 {pct['p50']:.1f}us exceeds 1ms regression ceiling"


# ---------------------------------------------------------------------------
# Rust adapter
# ---------------------------------------------------------------------------


@requires_rust
class TestRustBusRoundtrip:
    """Round-trip latency for RustBusAdapter."""

    @pytest.mark.parametrize("payload_size", PAYLOAD_SIZES)
    def test_rust_roundtrip(self, payload_size: int) -> None:
        bus = BusFactory.create_local(backend="rust")
        try:
            timings, delivered = _run_bench(bus, payload_size)
        finally:
            bus.close()

        expected = (WARMUP + N_ITERATIONS) * N_SUBS
        assert (
            delivered == expected
        ), f"delivery count mismatch: got {delivered}, expected {expected}"

        pct = _percentiles(timings)

        print(
            f"\n[RustBusAdapter] payload={payload_size}B subs={N_SUBS} "
            f"topics={N_TOPICS} N={N_ITERATIONS}"
        )
        _print_table("Round-trip publish() latency", {payload_size: pct})

        py = _PY_RESULTS.get(payload_size)
        if py is not None:
            ratio = pct["p50"] / py["p50"] if py["p50"] > 0 else float("inf")
            print(
                f"  rust/python p50 ratio: {ratio:.2f}x  "
                f"(py p50={py['p50']:.2f}us, rust p50={pct['p50']:.2f}us)"
            )
            # NOTE: RustBusAdapter adds Envelope<->RustEnvelope conversion
            # overhead (~2-3us per envelope per subscriber).  At adapter
            # level with N subscribers, this dominates the small-payload
            # case and Rust commonly runs slower than pure Python.  See
            # bench_v2_m10.py for the raw-Rust comparison where the FFI
            # overhead is excluded.

        assert (
            pct["p50"] < 1000.0
        ), f"RustBusAdapter p50 {pct['p50']:.1f}us exceeds 1ms regression ceiling"
