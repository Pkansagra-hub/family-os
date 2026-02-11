# k1_bus_core

Rust hot-path core for the K1 cognitive-architecture bus (PyO3 extension).

## Purpose

Replaces Python hot-path internals with Rust via PyO3.  Same `IBus`/`IMailboxRouter`
Python interfaces.  Zero module code changes.  Python V1 stays as permanent fallback.

## Components (planned)

| Module | Status | Description |
|--------|--------|-------------|
| `envelope` | Scaffold | FlatBuffers envelope (zero-copy read/write) |
| `topic_trie` | Planned | Lock-free trie with DashMap + subscription cache |
| `ring_buffer` | Planned | Disruptor-pattern pre-allocated ring buffer |
| `local_bus` | Planned | Stamp + route core (GIL released during match) |
| `timing_chain` | Planned | Causal + gap tracking (AtomicU64) |
| `wfq` | Planned | Deficit round-robin weighted fair queuing |
| `mailbox` | Planned | Bounded ring + WFQ per-actor mailbox |
| `circuit_breaker` | Planned | Per-handler failure tracking |
| `dlq` | Planned | Dead-letter queue (bounded ring) |
| `sweep` | Planned | Built-in sweep timer thread |

## Build

```bash
# Development build (debug, fast compile)
maturin develop

# Release build (LTO, stripped, optimized)
maturin develop --release

# Run Rust unit tests
cargo test

# Run Rust benchmarks
cargo bench
```

## Python usage

```python
try:
    from k1_bus_core import version, hello
    print(f"k1_bus_core {version()}")
except ImportError:
    print("Rust core not available, using Python fallback")
```

## Architecture

See `docs/plans/k1-bus-v2-rust-core-plan.md` for full migration plan.

```text
Python Land                          Rust Land (PyO3)
──────────                           ────────────────
k1/bus/ports/         <-- Protocol     k1_bus_core/
k1/bus/adapters/      <-- Dict/Any       src/
k1/bus/middleware/     <-- OTel/Prom       lib.rs
k1/bus/factory.py     <-- Wiring          envelope.rs (future)
                                          topic_trie.rs (future)
─ ─ ─ PyO3 FFI ─ ─ ─ ─ ─ ─              ...
```
