//! V2-M7-005/006/007/008: Dead-Letter Queue.
//!
//! Bounded FIFO queue of `(RustEnvelope, DlqReason)` pairs.
//!
//! Envelopes are routed here when:
//! - Mailbox is full (BackpressureFull)
//! - Handler raises an error (HandlerError)
//! - TTL expires before delivery (TtlExpired)
//! - Circuit breaker is open (CircuitOpen)
//! - Middleware dropped the envelope (MiddlewareDropped)
//!
//! When the DLQ itself is full, the oldest entry is dropped (ring
//! buffer behavior) and `total_dropped` is incremented.
//!
//! ## Python interop
//!
//! ```python
//! from k1_bus_core import DeadLetterQueue
//!
//! dlq = DeadLetterQueue(capacity=1000)
//! dlq.push(envelope, "BackpressureFull")
//! entries = dlq.drain()         # list[(RustEnvelope, str)]
//! peeked  = dlq.peek(5)         # first 5 without removing
//! depth   = dlq.depth
//! ```

use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use parking_lot::Mutex;
use pyo3::prelude::*;

use crate::rust_envelope::RustEnvelope;

// ---------------------------------------------------------------------------
// DlqReason
// ---------------------------------------------------------------------------

/// Why an envelope ended up in the dead-letter queue.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum DlqReason {
    /// Mailbox was full when delivery was attempted.
    BackpressureFull,
    /// Handler raised an error during dispatch.
    HandlerError,
    /// Envelope TTL expired before delivery.
    TtlExpired,
    /// Per-handler circuit breaker was open.
    CircuitOpen,
    /// Middleware dropped the envelope.
    MiddlewareDropped,
}

impl DlqReason {
    /// Convert string to DlqReason.
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "BackpressureFull" => Some(Self::BackpressureFull),
            "HandlerError" => Some(Self::HandlerError),
            "TtlExpired" => Some(Self::TtlExpired),
            "CircuitOpen" => Some(Self::CircuitOpen),
            "MiddlewareDropped" => Some(Self::MiddlewareDropped),
            _ => None,
        }
    }

    /// String representation (stable, used as Python interface).
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::BackpressureFull => "BackpressureFull",
            Self::HandlerError => "HandlerError",
            Self::TtlExpired => "TtlExpired",
            Self::CircuitOpen => "CircuitOpen",
            Self::MiddlewareDropped => "MiddlewareDropped",
        }
    }
}

// ---------------------------------------------------------------------------
// DlqEntry
// ---------------------------------------------------------------------------

/// A single dead-letter queue entry.
#[derive(Debug, Clone)]
struct DlqEntry {
    envelope: RustEnvelope,
    reason: DlqReason,
    timestamp_ns: u64,
}

// ---------------------------------------------------------------------------
// DeadLetterQueueInner -- thread-safe core
// ---------------------------------------------------------------------------

/// Core DLQ state.  Shared via `Arc` with the router.
pub(crate) struct DeadLetterQueueInner {
    entries: Mutex<VecDeque<DlqEntry>>,
    capacity: usize,
    total_pushed: AtomicU64,
    total_dropped: AtomicU64,
}

impl DeadLetterQueueInner {
    pub fn new(capacity: usize) -> Self {
        Self {
            entries: Mutex::new(VecDeque::with_capacity(capacity.min(1024))),
            capacity,
            total_pushed: AtomicU64::new(0),
            total_dropped: AtomicU64::new(0),
        }
    }

    /// Push an envelope with reason.
    ///
    /// If at capacity, drops the oldest entry (ring buffer behavior).
    pub fn push(&self, envelope: RustEnvelope, reason: DlqReason) {
        let now_ns = monotonic_ns();
        let mut entries = self.entries.lock();

        if entries.len() >= self.capacity {
            entries.pop_front();
            self.total_dropped.fetch_add(1, Ordering::Relaxed);
        }

        entries.push_back(DlqEntry {
            envelope,
            reason,
            timestamp_ns: now_ns,
        });
        self.total_pushed.fetch_add(1, Ordering::Relaxed);
    }

    /// Drain all entries from the queue, returning them in FIFO order.
    pub fn drain(&self) -> Vec<(RustEnvelope, DlqReason, u64)> {
        let mut entries = self.entries.lock();
        entries
            .drain(..)
            .map(|e| (e.envelope, e.reason, e.timestamp_ns))
            .collect()
    }

    /// Peek at the first `n` entries without removing them.
    pub fn peek(&self, n: usize) -> Vec<(RustEnvelope, DlqReason, u64)> {
        let entries = self.entries.lock();
        entries
            .iter()
            .take(n)
            .map(|e| (e.envelope.clone(), e.reason, e.timestamp_ns))
            .collect()
    }

    /// Current number of entries in the queue.
    pub fn depth(&self) -> usize {
        self.entries.lock().len()
    }
}

// ---------------------------------------------------------------------------
// Monotonic nanosecond timestamp
// ---------------------------------------------------------------------------

fn monotonic_ns() -> u64 {
    use std::time::Instant;

    // Use a thread-local cached epoch for monotonic_ns
    thread_local! {
        static EPOCH: Instant = Instant::now();
    }
    EPOCH.with(|epoch| epoch.elapsed().as_nanos() as u64)
}

// ---------------------------------------------------------------------------
// DeadLetterQueue -- #[pyclass] wrapper
// ---------------------------------------------------------------------------

/// Python-exposed dead-letter queue.
///
/// Bounded FIFO queue of `(envelope, reason)` pairs.  When full,
/// oldest entry is dropped (ring buffer behavior).
#[pyclass(name = "DeadLetterQueue")]
pub(crate) struct DeadLetterQueue {
    pub(crate) inner: Arc<DeadLetterQueueInner>,
}

#[pymethods]
impl DeadLetterQueue {
    /// Create a new dead-letter queue.
    ///
    /// Args:
    ///     capacity: Maximum number of entries (default 10000).
    #[new]
    #[pyo3(signature = (capacity=10000))]
    fn new(capacity: usize) -> PyResult<Self> {
        if capacity == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "capacity must be > 0",
            ));
        }
        Ok(Self {
            inner: Arc::new(DeadLetterQueueInner::new(capacity)),
        })
    }

    /// Push an envelope with a reason string.
    ///
    /// Valid reasons: "BackpressureFull", "HandlerError", "TtlExpired",
    /// "CircuitOpen", "MiddlewareDropped".
    fn push(&self, envelope: &RustEnvelope, reason: &str) -> PyResult<()> {
        let r = DlqReason::from_str(reason).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "Unknown DLQ reason: '{}'. Valid: BackpressureFull, HandlerError, \
                 TtlExpired, CircuitOpen, MiddlewareDropped",
                reason,
            ))
        })?;
        self.inner.push(envelope.clone(), r);
        Ok(())
    }

    /// Drain all entries.
    ///
    /// Returns list of `(RustEnvelope, reason_str)` tuples.
    fn drain(&self) -> Vec<(RustEnvelope, String)> {
        self.inner
            .drain()
            .into_iter()
            .map(|(env, reason, _ts)| (env, reason.as_str().to_string()))
            .collect()
    }

    /// Peek at the first `n` entries without removing.
    ///
    /// Returns list of `(RustEnvelope, reason_str)` tuples.
    #[pyo3(signature = (n=10))]
    fn peek(&self, n: usize) -> Vec<(RustEnvelope, String)> {
        self.inner
            .peek(n)
            .into_iter()
            .map(|(env, reason, _ts)| (env, reason.as_str().to_string()))
            .collect()
    }

    /// Current number of entries in the queue.
    #[getter]
    fn depth(&self) -> usize {
        self.inner.depth()
    }

    /// Total envelopes pushed (lifetime, including dropped).
    #[getter]
    fn total_pushed(&self) -> u64 {
        self.inner.total_pushed.load(Ordering::Relaxed)
    }

    /// Total oldest entries dropped due to capacity overflow.
    #[getter]
    fn total_dropped(&self) -> u64 {
        self.inner.total_dropped.load(Ordering::Relaxed)
    }

    /// Maximum capacity.
    #[getter]
    fn capacity(&self) -> usize {
        self.inner.capacity
    }

    fn __repr__(&self) -> String {
        format!(
            "DeadLetterQueue(depth={}/{}, pushed={}, dropped={})",
            self.inner.depth(),
            self.inner.capacity,
            self.inner.total_pushed.load(Ordering::Relaxed),
            self.inner.total_dropped.load(Ordering::Relaxed),
        )
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn env(topic: &str, payload: &[u8]) -> RustEnvelope {
        RustEnvelope {
            topic: topic.to_string(),
            priority: 2,
            envelope_id: 0,
            sequence: 0,
            cognitive_trace_id: String::new(),
            session_id: String::new(),
            request_id: String::new(),
            parent_id: 0,
            created_ns: 0,
            payload: payload.to_vec(),
            ttl_ms: 0,
            payload_format: 0,
        }
    }

    #[test]
    fn test_empty_dlq() {
        let dlq = DeadLetterQueueInner::new(100);
        assert_eq!(dlq.depth(), 0);
        assert!(dlq.drain().is_empty());
        assert!(dlq.peek(10).is_empty());
    }

    #[test]
    fn test_push_and_drain() {
        let dlq = DeadLetterQueueInner::new(100);
        dlq.push(env("t", b"one"), DlqReason::BackpressureFull);
        dlq.push(env("t", b"two"), DlqReason::HandlerError);

        assert_eq!(dlq.depth(), 2);
        assert_eq!(dlq.total_pushed.load(Ordering::Relaxed), 2);

        let entries = dlq.drain();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].0.payload, b"one");
        assert_eq!(entries[0].1, DlqReason::BackpressureFull);
        assert_eq!(entries[1].0.payload, b"two");
        assert_eq!(entries[1].1, DlqReason::HandlerError);

        assert_eq!(dlq.depth(), 0);
    }

    #[test]
    fn test_peek_does_not_remove() {
        let dlq = DeadLetterQueueInner::new(100);
        dlq.push(env("t", b"peek-me"), DlqReason::TtlExpired);

        let peeked = dlq.peek(5);
        assert_eq!(peeked.len(), 1);
        assert_eq!(peeked[0].0.payload, b"peek-me");
        assert_eq!(peeked[0].1, DlqReason::TtlExpired);

        assert_eq!(dlq.depth(), 1); // Still there
    }

    #[test]
    fn test_bounded_drops_oldest() {
        let dlq = DeadLetterQueueInner::new(3);
        dlq.push(env("t", b"a"), DlqReason::BackpressureFull);
        dlq.push(env("t", b"b"), DlqReason::BackpressureFull);
        dlq.push(env("t", b"c"), DlqReason::BackpressureFull);
        assert_eq!(dlq.depth(), 3);
        assert_eq!(dlq.total_dropped.load(Ordering::Relaxed), 0);

        // Push a 4th -- oldest ("a") should be dropped
        dlq.push(env("t", b"d"), DlqReason::HandlerError);
        assert_eq!(dlq.depth(), 3);
        assert_eq!(dlq.total_dropped.load(Ordering::Relaxed), 1);

        let entries = dlq.drain();
        assert_eq!(entries.len(), 3);
        assert_eq!(entries[0].0.payload, b"b"); // "a" was dropped
        assert_eq!(entries[1].0.payload, b"c");
        assert_eq!(entries[2].0.payload, b"d");
    }

    #[test]
    fn test_all_reasons() {
        let dlq = DeadLetterQueueInner::new(100);
        let reasons = [
            DlqReason::BackpressureFull,
            DlqReason::HandlerError,
            DlqReason::TtlExpired,
            DlqReason::CircuitOpen,
            DlqReason::MiddlewareDropped,
        ];
        for r in &reasons {
            dlq.push(env("t", b""), *r);
        }
        let entries = dlq.drain();
        assert_eq!(entries.len(), 5);
        for (i, r) in reasons.iter().enumerate() {
            assert_eq!(entries[i].1, *r);
        }
    }

    #[test]
    fn test_reason_round_trip() {
        let cases = [
            "BackpressureFull",
            "HandlerError",
            "TtlExpired",
            "CircuitOpen",
            "MiddlewareDropped",
        ];
        for s in &cases {
            let r = DlqReason::from_str(s).unwrap();
            assert_eq!(r.as_str(), *s);
        }
        assert!(DlqReason::from_str("Invalid").is_none());
    }

    #[test]
    fn test_timestamps_monotonic() {
        let dlq = DeadLetterQueueInner::new(100);
        dlq.push(env("t", b"first"), DlqReason::BackpressureFull);
        // Small sleep to ensure different timestamp
        std::thread::sleep(std::time::Duration::from_millis(1));
        dlq.push(env("t", b"second"), DlqReason::BackpressureFull);

        let entries = dlq.drain();
        assert!(entries[1].2 >= entries[0].2);
    }

    #[test]
    fn test_concurrent_push() {
        use std::thread;

        let dlq = Arc::new(DeadLetterQueueInner::new(10_000));
        let n_threads = 4;
        let n_per_thread = 250;

        let mut handles = Vec::new();
        for t in 0..n_threads {
            let dlq2 = dlq.clone();
            handles.push(thread::spawn(move || {
                for i in 0..n_per_thread {
                    dlq2.push(
                        env("t", format!("t{t}-{i}").as_bytes()),
                        DlqReason::BackpressureFull,
                    );
                }
            }));
        }

        for h in handles {
            h.join().unwrap();
        }

        assert_eq!(dlq.depth(), n_threads * n_per_thread);
        assert_eq!(
            dlq.total_pushed.load(Ordering::Relaxed),
            (n_threads * n_per_thread) as u64,
        );
    }
}
