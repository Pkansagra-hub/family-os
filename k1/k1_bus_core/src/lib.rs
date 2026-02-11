//! k1_bus_core -- Rust hot-path core for the K1 cognitive-architecture bus.
//!
//! This crate provides PyO3-exposed Rust implementations of the bus hot path:
//! envelope serialization, topic trie matching, ring buffer dispatch,
//! timing chain, WFQ scheduler, and mailbox routing.
//!
//! Python V1 implementations remain as permanent fallback.  The Python
//! factory (`k1.bus.factory`) uses `try: import k1_bus_core` to detect
//! whether the Rust core is available.
//!
//! # Module layout (planned)
//!
//! - `envelope`        -- FlatBuffers envelope (zero-copy)
//! - `topic_trie`      -- Lock-free trie with subscription cache
//! - `ring_buffer`     -- Disruptor-pattern dispatch buffer
//! - `local_bus`       -- Stamp + route (GIL released during match)
//! - `timing_chain`    -- Causal + gap tracking
//! - `wfq`             -- Deficit round-robin scheduler
//! - `mailbox`         -- Bounded per-actor mailbox
//! - `circuit_breaker` -- Per-handler failure state machine
//! - `dlq`             -- Dead-letter queue
//! - `sweep`           -- Built-in sweep timer

use pyo3::prelude::*;

pub mod envelope;
pub mod local_bus;
pub mod ring_buffer;
pub mod rust_envelope;
pub mod topic_trie;

// V2-M6: Timing chain + WFQ modules
pub mod causal_tracker;
pub mod gap_buffer;
pub mod timing_config;
pub mod wfq;

// V2-M7: Mailbox + Dead-Letter Queue
pub mod dlq;
pub mod mailbox;

// V2-M8: Circuit Breaker + Sweep Timer
pub mod circuit_breaker;
pub mod sweep;

// ─── Module version ──────────────────────────────────────────────────

/// Crate version from Cargo.toml.
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Return the crate version string.
#[pyfunction]
fn version() -> &'static str {
    VERSION
}

/// Smoke-test function to verify the PyO3 module loads correctly.
///
/// ```python
/// from k1_bus_core import hello
/// assert hello() == "k1_bus_core is alive"
/// ```
#[pyfunction]
fn hello() -> &'static str {
    "k1_bus_core is alive"
}

// ─── PyO3 module definition ─────────────────────────────────────────

/// Python module exposed as `k1_bus_core`.
///
/// Registers all submodule functions and classes.  New modules are added
/// here as they are implemented in subsequent milestones.
#[pymodule]
fn k1_bus_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Core functions
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(hello, m)?)?;

    // Envelope submodule functions
    m.add_function(wrap_pyfunction!(envelope::envelope_to_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(envelope::envelope_from_bytes, m)?)?;

    // TopicTrie class
    m.add_class::<topic_trie::PyTopicTrie>()?;

    // RustEnvelope class (V2-M4)
    m.add_class::<rust_envelope::RustEnvelope>()?;

    // RingBuffer class (V2-M4, testing only)
    m.add_class::<ring_buffer::PyRingBuffer>()?;

    // RustBus class (V2-M5)
    m.add_class::<local_bus::RustBus>()?;

    // V2-M6: TimingConfig and WFQ Scheduler
    m.add_class::<timing_config::RustTimingConfig>()?;
    m.add_class::<wfq::PyWfqScheduler>()?;

    // V2-M7: Mailbox + DLQ
    m.add_class::<mailbox::RustMailbox>()?;
    m.add_class::<mailbox::RustMailboxRouter>()?;
    m.add_class::<dlq::DeadLetterQueue>()?;

    // V2-M8: Sweep Timer
    m.add_class::<sweep::PySweepTimer>()?;

    Ok(())
}

// ─── Rust-native tests ──────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version_not_empty() {
        assert!(!VERSION.is_empty());
        assert!(VERSION.contains('.'), "version should be semver: {VERSION}");
    }

    #[test]
    fn test_hello() {
        assert_eq!(hello(), "k1_bus_core is alive");
    }
}
