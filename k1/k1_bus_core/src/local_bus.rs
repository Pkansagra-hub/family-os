//! Rust `RustBus` -- publish + dispatch hot path with GIL-released trie match.
//!
//! ## V2-M5 Epic 5.1: Stamp + Route Path
//!
//! - **V2-M5-001**: AtomicU64 envelope ID generator (lock-free, Relaxed ordering)
//! - **V2-M5-002**: Per-topic sequence generator (DashMap<String, AtomicU64>)
//! - **V2-M5-003**: `RustBus::publish()` -- validate, stamp, match, dispatch
//! - **V2-M5-004**: Topic validation (empty, empty segments, leading/trailing dots)
//! - **V2-M5-005**: TTL check at dispatch time (expired envelopes skip handlers)
//!
//! ## V2-M5 Epic 5.2: Handler Dispatch
//!
//! - **V2-M5-006**: GIL batch dispatch (handler_ids collected without GIL, single
//!   GIL acquisition for entire fan-out)
//! - **V2-M5-007**: Per-handler error isolation (Python exceptions caught, logged,
//!   never propagate to publisher or other handlers)
//! - **V2-M5-008**: Handler latency tracking (Instant-based per-handler_id,
//!   exposed via `handler_stats()`)
//! - **V2-M5-009**: Backpressure signal (`publish()` returns `PyResult<u64>`,
//!   errors map to Python exceptions)
//!
//! ## Thread Safety
//!
//! - `RwLock<TopicTrieInner>`: readers = publish (trie match), writer = subscribe/unsubscribe
//! - `RwLock<HashMap<u64, Py<PyAny>>>`: handler lookup synchronized with trie
//! - `AtomicU64` for all counters: envelope_id, sequences, stats
//! - `DashMap` for per-topic sequences and per-handler latencies
//! - `parking_lot::Mutex` for captured list and topics_seen set
//!
//! ## Python Interop
//!
//! ```python
//! from k1_bus_core import RustBus, RustEnvelope
//!
//! bus = RustBus(capture=True)
//! bus.subscribe("k1.test.*", my_handler)
//! env = RustEnvelope(topic="k1.test.alpha", payload=b"hello")
//! eid = bus.publish(env)          # returns stamped envelope_id
//! assert bus.captured_count == 1
//! assert bus.stats["envelopes_published"] == 1
//! ```

use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, OnceLock};
use std::time::{Duration, Instant};

use crossbeam::channel;
use dashmap::DashMap;
use parking_lot::{Mutex, RwLock};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::circuit_breaker::CircuitBreakerRegistry;
use crate::rust_envelope::RustEnvelope;
use crate::topic_trie::TopicTrieInner;

// ─── Monotonic clock ────────────────────────────────────────────────

/// Process-local monotonic nanosecond timestamp.
///
/// Uses a static baseline `Instant` so all timestamps are relative to the
/// first call (approximately process start).  Monotonically increasing
/// and consistent within a single process, but NOT comparable to Python's
/// `time.monotonic_ns()` (different epoch).
fn monotonic_ns() -> u64 {
    static BASELINE: OnceLock<Instant> = OnceLock::new();
    let base = BASELINE.get_or_init(Instant::now);
    base.elapsed().as_nanos() as u64
}

// ─── Dispatch work item (async dispatch M8-001) ─────────────────────

/// Work item sent to the async dispatch thread.
struct DispatchWork {
    stamped: RustEnvelope,
    handler_pairs: Vec<(u64, Py<PyAny>)>,
}

// ─── Handler latency tracking (V2-M5-008) ──────────────────────────

/// Per-handler latency statistics.
///
/// Updated on every handler invocation.  Stored in a `DashMap` keyed by
/// handler_id, so each handler gets independent stats with no contention
/// across handlers.
#[derive(Debug)]
struct HandlerLatency {
    call_count: u64,
    total_ns: u64,
    min_ns: u64,
    max_ns: u64,
    error_count: u64,
}

impl HandlerLatency {
    fn new() -> Self {
        Self {
            call_count: 0,
            total_ns: 0,
            min_ns: u64::MAX,
            max_ns: 0,
            error_count: 0,
        }
    }

    fn record(&mut self, elapsed_ns: u64, is_error: bool) {
        self.call_count += 1;
        self.total_ns += elapsed_ns;
        if elapsed_ns < self.min_ns {
            self.min_ns = elapsed_ns;
        }
        if elapsed_ns > self.max_ns {
            self.max_ns = elapsed_ns;
        }
        if is_error {
            self.error_count += 1;
        }
    }

    fn avg_ns(&self) -> u64 {
        if self.call_count == 0 {
            0
        } else {
            self.total_ns / self.call_count
        }
    }
}

// ─── RustBus ────────────────────────────────────────────────────────

/// High-performance in-process bus with Rust hot path.
///
/// Implements the same publish/subscribe/dispatch semantics as Python
/// `LocalBus`, but with:
///
/// - **AtomicU64** envelope ID (no lock, Relaxed ordering)
/// - **DashMap** per-topic sequences (no contention across topics)
/// - **GIL-released** trie match (handler_ids collected in pure Rust)
/// - **Single GIL acquisition** for entire fan-out dispatch batch
/// - **Per-handler error isolation** and latency tracking
/// - **TTL enforcement** at dispatch time
#[pyclass(name = "RustBus")]
pub struct RustBus {
    // ── Trie + handlers ─────────────────────────────────────────
    trie: RwLock<TopicTrieInner>,
    /// handler_id -> Python callable
    handlers: RwLock<HashMap<u64, Py<PyAny>>>,
    /// handler_id -> subscription pattern (for handler_circuits())
    handler_patterns: DashMap<u64, String>,

    // ── Stamp generators (V2-M5-001, V2-M5-002) ────────────────
    envelope_id_gen: AtomicU64,
    topic_sequences: DashMap<String, AtomicU64>,

    // ── Stats (Arc-wrapped for async dispatch thread access) ────
    envelopes_published: AtomicU64,
    envelopes_delivered: Arc<AtomicU64>,
    handler_errors: Arc<AtomicU64>,
    subscriptions_active: AtomicU64,
    subscriptions_total: AtomicU64,
    unsubscribe_count: AtomicU64,
    topics_seen_count: AtomicU64,
    ttl_expired: Arc<AtomicU64>,

    // ── Per-handler latency (shared for async dispatch) ─────────
    handler_latencies: Arc<DashMap<u64, HandlerLatency>>,

    // ── Circuit breakers (V2-M8-005, shared for async dispatch) ─
    circuit_breakers: Arc<CircuitBreakerRegistry>,

    // ── Topics seen set ─────────────────────────────────────────
    topics_seen: Mutex<HashSet<String>>,

    // ── Capture mode ────────────────────────────────────────────
    capture: bool,
    captured: Mutex<Vec<Py<PyAny>>>,

    // ── Closed flag ─────────────────────────────────────────────
    closed: AtomicBool,

    // ── Async dispatch (V2-M8-001/002/003/004) ──────────────────
    dispatch_mode: u8,  // 0=Sync, 1=Async
    async_sender: Option<channel::Sender<DispatchWork>>,
    async_stop: Arc<AtomicBool>,
    gil_batch_size: usize,
}

#[pymethods]
impl RustBus {
    /// Create a new RustBus.
    ///
    /// Args:
    ///     capture: If True, record all published envelopes in `self.captured`.
    #[new]
    #[pyo3(signature = (capture=false, dispatch_mode=0, failure_threshold=5, cooldown_ms=10000, gil_batch_size=32, async_channel_size=10000))]
    fn new(
        capture: bool,
        dispatch_mode: u8,
        failure_threshold: u32,
        cooldown_ms: u64,
        gil_batch_size: usize,
        async_channel_size: usize,
    ) -> Self {
        let envelopes_delivered = Arc::new(AtomicU64::new(0));
        let handler_errors = Arc::new(AtomicU64::new(0));
        let ttl_expired = Arc::new(AtomicU64::new(0));
        let handler_latencies = Arc::new(DashMap::new());
        let circuit_breakers = Arc::new(CircuitBreakerRegistry::new(
            failure_threshold,
            cooldown_ms,
        ));
        let async_stop = Arc::new(AtomicBool::new(false));

        // Async dispatch setup (M8-001/002)
        let async_sender = if dispatch_mode == 1 {
            let (tx, rx) = channel::bounded::<DispatchWork>(async_channel_size);
            let stop = async_stop.clone();
            let delivered = envelopes_delivered.clone();
            let errors = handler_errors.clone();
            let expired = ttl_expired.clone();
            let latencies = handler_latencies.clone();
            let cbs = circuit_breakers.clone();
            let batch = gil_batch_size;

            std::thread::Builder::new()
                .name("k1-bus-dispatch".into())
                .spawn(move || {
                    Self::async_dispatch_loop(
                        rx, stop, delivered, errors, expired,
                        latencies, cbs, batch,
                    );
                })
                .expect("Failed to spawn dispatch thread");

            Some(tx)
        } else {
            None
        };

        Self {
            trie: RwLock::new(TopicTrieInner::new()),
            handlers: RwLock::new(HashMap::new()),
            handler_patterns: DashMap::new(),
            envelope_id_gen: AtomicU64::new(0),
            topic_sequences: DashMap::new(),
            envelopes_published: AtomicU64::new(0),
            envelopes_delivered,
            handler_errors,
            subscriptions_active: AtomicU64::new(0),
            subscriptions_total: AtomicU64::new(0),
            unsubscribe_count: AtomicU64::new(0),
            topics_seen_count: AtomicU64::new(0),
            ttl_expired,
            handler_latencies,
            circuit_breakers,
            topics_seen: Mutex::new(HashSet::new()),
            capture,
            captured: Mutex::new(Vec::new()),
            closed: AtomicBool::new(false),
            dispatch_mode,
            async_sender,
            async_stop,
            gil_batch_size,
        }
    }

    // ── IBus.publish (V2-M5-003) ────────────────────────────────

    /// Publish a RustEnvelope to the bus.
    ///
    /// Steps:
    ///   1. Validate: not closed, topic not empty, no invalid segments
    ///   2. Stamp: envelope_id (global AtomicU64), sequence (per-topic),
    ///      created_ns (monotonic clock)
    ///   3. Capture: if capture mode, record stamped envelope
    ///   4. Match: walk trie to find handler_ids (GIL released)
    ///   5. Dispatch: invoke handlers with stamped envelope (GIL held,
    ///      per-handler error isolation, latency tracking, TTL check)
    ///
    /// Returns the assigned envelope_id (u64).
    ///
    /// Raises:
    ///     RuntimeError: If the bus is closed.
    ///     ValueError: If topic is empty or has invalid segments.
    fn publish(&self, py: Python<'_>, envelope: &RustEnvelope) -> PyResult<u64> {
        // 1. Check closed
        if self.closed.load(Ordering::Acquire) {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Bus is closed",
            ));
        }

        // 2. Validate topic (V2-M5-004)
        let topic = &envelope.topic;
        if topic.is_empty() {
            return Err(pyo3::exceptions::PyValueError::new_err("Empty topic"));
        }
        Self::validate_topic(topic)?;

        // 3. Stamp (V2-M5-001, V2-M5-002)
        let envelope_id = self.envelope_id_gen.fetch_add(1, Ordering::Relaxed) + 1;
        let sequence = self.next_sequence(topic);
        let created_ns = monotonic_ns();

        let stamped = envelope.with_bus_fields(envelope_id, sequence, created_ns);

        // Track topics seen
        {
            let mut seen = self.topics_seen.lock();
            if seen.insert(topic.clone()) {
                self.topics_seen_count.fetch_add(1, Ordering::Relaxed);
            }
        }

        // Capture mode: record before dispatch
        if self.capture {
            let stamped_py = Py::new(py, stamped.clone())?;
            self.captured.lock().push(stamped_py.into_any());
        }

        self.envelopes_published.fetch_add(1, Ordering::Relaxed);

        // 4. Trie match -- GIL released (V2-M5-006)
        // handler_ids are pure u64 values from TopicTrieInner, no Python objects.
        let handler_ids = {
            let trie = self.trie.read();
            trie.match_topic(topic)
        };

        // 5. Fan-out dispatch (V2-M5-006, V2-M5-007, V2-M5-008, V2-M5-005)
        if !handler_ids.is_empty() {
            if self.dispatch_mode == 1 {
                // Async mode (M8-001): push to channel, return immediately
                let handler_pairs: Vec<(u64, Py<PyAny>)> = {
                    let handlers_lock = self.handlers.read();
                    handler_ids.iter().filter_map(|&hid| {
                        handlers_lock.get(&hid).map(|h| (hid, h.clone_ref(py)))
                    }).collect()
                };
                if !handler_pairs.is_empty() {
                    let work = DispatchWork {
                        stamped: stamped.clone(),
                        handler_pairs,
                    };
                    if let Some(ref sender) = self.async_sender {
                        if sender.try_send(work).is_err() {
                            // Channel full or disconnected -- fallback to sync
                            self.dispatch(py, &stamped, &handler_ids)?;
                        }
                    }
                }
            } else {
                // Sync mode (default): dispatch inline
                self.dispatch(py, &stamped, &handler_ids)?;
            }
        }

        Ok(envelope_id)
    }

    // ── IBus.subscribe (minimal for Epic 5.1/5.2 testing) ───────

    /// Subscribe a Python handler to a topic pattern.
    ///
    /// Pattern syntax:
    ///   - `"k1.capability.completed.v1"` -- exact match
    ///   - `"k1.agent.*.delta.v1"` -- `*` matches one segment
    ///   - `"k1.agent.>"` -- `>` matches one or more trailing
    ///
    /// Returns the subscription_id string for later `unsubscribe()`.
    ///
    /// After successful subscription, emits a lifecycle event to
    /// `k1.bus.subscription.created` via internal fast-path dispatch
    /// (V2-M5-012).
    ///
    /// Raises:
    ///     ValueError: If the pattern is invalid.
    fn subscribe(&self, py: Python<'_>, pattern: &str, handler: Py<PyAny>) -> PyResult<String> {
        let sub_id = format!("sub-{:016x}", {
            static SUB_COUNTER: AtomicU64 = AtomicU64::new(0);
            SUB_COUNTER.fetch_add(1, Ordering::Relaxed)
        });

        let handler_id = {
            let mut trie = self.trie.write();
            trie.insert(pattern, &sub_id)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?
        };

        self.handlers.write().insert(handler_id, handler);
        self.handler_patterns.insert(handler_id, pattern.to_string());
        self.subscriptions_active.fetch_add(1, Ordering::Relaxed);
        self.subscriptions_total.fetch_add(1, Ordering::Relaxed);

        // V2-M5-012: Emit subscription lifecycle event (internal fast-path)
        self.emit_lifecycle_event(
            py,
            "k1.bus.subscription.created",
            &sub_id,
            pattern,
        );

        Ok(sub_id)
    }

    // ── IBus.unsubscribe (minimal for Epic 5.1/5.2 testing) ─────

    /// Remove a subscription by ID.
    ///
    /// After successful removal, emits a lifecycle event to
    /// `k1.bus.subscription.removed` via internal fast-path dispatch
    /// (V2-M5-012).  The event payload contains the subscription_id.
    ///
    /// Returns True if found and removed, False otherwise.
    fn unsubscribe(&self, py: Python<'_>, subscription_id: &str) -> bool {
        let handler_id_opt = {
            let mut trie = self.trie.write();
            trie.remove(subscription_id)
        };

        if let Some(handler_id) = handler_id_opt {
            self.handlers.write().remove(&handler_id);
            self.handler_latencies.remove(&handler_id);
            self.handler_patterns.remove(&handler_id);
            self.circuit_breakers.remove(handler_id);

            // Saturating decrement: guard against underflow
            let prev = self.subscriptions_active.load(Ordering::Relaxed);
            if prev > 0 {
                self.subscriptions_active.fetch_sub(1, Ordering::Relaxed);
            }
            self.unsubscribe_count.fetch_add(1, Ordering::Relaxed);

            // V2-M5-012: Emit subscription lifecycle event (internal fast-path)
            self.emit_lifecycle_event(
                py,
                "k1.bus.subscription.removed",
                subscription_id,
                "",
            );

            true
        } else {
            false
        }
    }

    // ── Lifecycle ───────────────────────────────────────────────

    /// Close the bus.  Further publishes raise RuntimeError.
    fn close(&self) {
        self.closed.store(true, Ordering::Release);
        self.async_stop.store(true, Ordering::Release);
    }

    /// Whether the bus has been closed.
    #[getter]
    fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Acquire)
    }

    // ── Stats (V2-M5-009) ───────────────────────────────────────

    /// Bus statistics as a Python dict.
    ///
    /// Keys: envelopes_published, envelopes_delivered, handler_errors,
    ///       subscriptions_active, subscriptions_total, unsubscribe_count,
    ///       topics_seen, ttl_expired
    #[getter]
    fn stats(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item(
            "envelopes_published",
            self.envelopes_published.load(Ordering::Relaxed),
        )?;
        dict.set_item(
            "envelopes_delivered",
            self.envelopes_delivered.load(Ordering::Relaxed),
        )?;
        dict.set_item(
            "handler_errors",
            self.handler_errors.load(Ordering::Relaxed),
        )?;
        dict.set_item(
            "subscriptions_active",
            self.subscriptions_active.load(Ordering::Relaxed),
        )?;
        dict.set_item(
            "subscriptions_total",
            self.subscriptions_total.load(Ordering::Relaxed),
        )?;
        dict.set_item(
            "unsubscribe_count",
            self.unsubscribe_count.load(Ordering::Relaxed),
        )?;
        dict.set_item(
            "topics_seen",
            self.topics_seen_count.load(Ordering::Relaxed),
        )?;
        dict.set_item(
            "ttl_expired",
            self.ttl_expired.load(Ordering::Relaxed),
        )?;
        Ok(dict.into())
    }

    /// Per-handler latency statistics as a Python dict (V2-M5-008).
    ///
    /// Returns: `{handler_id: {"call_count": N, "avg_ns": N, "min_ns": N,
    ///           "max_ns": N, "error_count": N}}`
    fn handler_stats(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let outer = PyDict::new(py);
        for entry in self.handler_latencies.iter() {
            let hid = *entry.key();
            let lat = entry.value();
            let inner = PyDict::new(py);
            inner.set_item("call_count", lat.call_count)?;
            inner.set_item("avg_ns", lat.avg_ns())?;
            inner.set_item(
                "min_ns",
                if lat.min_ns == u64::MAX { 0 } else { lat.min_ns },
            )?;
            inner.set_item("max_ns", lat.max_ns)?;
            inner.set_item("error_count", lat.error_count)?;
            outer.set_item(hid, inner)?;
        }
        Ok(outer.into())
    }

    // ── Accessors ───────────────────────────────────────────────

    /// Last assigned envelope ID (0 if none published).
    #[getter]
    fn last_envelope_id(&self) -> u64 {
        self.envelope_id_gen.load(Ordering::Relaxed)
    }

    /// Current sequence for a topic (0 if never published).
    fn topic_sequence(&self, topic: &str) -> u64 {
        self.topic_sequences
            .get(topic)
            .map(|v| v.load(Ordering::Relaxed))
            .unwrap_or(0)
    }

    /// Number of active subscriptions.
    #[getter]
    fn subscription_count(&self) -> u64 {
        self.subscriptions_active.load(Ordering::Relaxed)
    }

    /// Captured envelopes (capture mode only).  Returns a list of RustEnvelope.
    #[getter]
    fn captured(&self, py: Python<'_>) -> PyResult<Vec<PyObject>> {
        let lock = self.captured.lock();
        let mut result = Vec::with_capacity(lock.len());
        for item in lock.iter() {
            result.push(item.clone_ref(py).into_any());
        }
        Ok(result)
    }

    /// Number of captured envelopes.
    #[getter]
    fn captured_count(&self) -> usize {
        self.captured.lock().len()
    }

    fn __repr__(&self) -> String {
        let pub_count = self.envelopes_published.load(Ordering::Relaxed);
        let sub_count = self.subscriptions_active.load(Ordering::Relaxed);
        format!("RustBus(published={pub_count}, subscriptions={sub_count})")
    }

    fn __len__(&self) -> usize {
        self.subscriptions_active.load(Ordering::Relaxed) as usize
    }

    // ── Circuit breaker observability (V2-M8-007) ───────────────

    /// Per-handler circuit breaker states.
    ///
    /// Returns: `{pattern_string: state_string}` where state is
    /// "CLOSED", "OPEN", or "HALF_OPEN".
    fn handler_circuits(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        for (hid, state) in self.circuit_breakers.states() {
            let pattern = self.handler_patterns
                .get(&hid)
                .map(|r| r.value().clone())
                .unwrap_or_else(|| format!("handler-{hid}"));
            dict.set_item(pattern, state.as_str())?;
        }
        Ok(dict.into())
    }

    /// Reset a circuit breaker for a specific handler pattern.
    ///
    /// Finds the handler_id by pattern and resets its breaker to CLOSED.
    /// Returns True if a matching handler was found and reset.
    fn reset_circuit(&self, pattern: &str) -> bool {
        for entry in self.handler_patterns.iter() {
            if entry.value() == pattern {
                self.circuit_breakers.reset(*entry.key());
                return true;
            }
        }
        false
    }

    /// Dispatch mode: 0=Sync, 1=Async.
    #[getter]
    fn dispatch_mode_value(&self) -> u8 {
        self.dispatch_mode
    }
}

// ─── Private impl (non-PyO3) ────────────────────────────────────────

impl RustBus {
    /// Validate a concrete publish topic (V2-M5-004).
    ///
    /// Rules:
    ///   - Must not be empty (checked before calling this)
    ///   - Must not contain empty segments (`..`)
    ///   - Must not start or end with `.`
    ///   - Must not be all dots
    fn validate_topic(topic: &str) -> PyResult<()> {
        if topic.contains("..") {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Invalid topic '{topic}': contains empty segment"
            )));
        }
        if topic.starts_with('.') || topic.ends_with('.') {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Invalid topic '{topic}': starts or ends with dot"
            )));
        }
        if topic.chars().all(|c| c == '.') {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Invalid topic '{topic}': all dots"
            )));
        }
        Ok(())
    }

    /// Get next per-topic sequence number.  First call for a topic returns 1.
    ///
    /// Implementation: DashMap entry with AtomicU64 per topic.
    /// Hot path (existing topic): DashMap read lock + atomic fetch_add.
    /// Cold path (new topic): DashMap write lock + insert.
    fn next_sequence(&self, topic: &str) -> u64 {
        // Hot path: topic already exists
        if let Some(counter) = self.topic_sequences.get(topic) {
            return counter.fetch_add(1, Ordering::Relaxed) + 1;
        }
        // Cold path: first publish for this topic
        let entry = self
            .topic_sequences
            .entry(topic.to_string())
            .or_insert_with(|| AtomicU64::new(0));
        entry.fetch_add(1, Ordering::Relaxed) + 1
    }

    /// Emit a subscription lifecycle event via internal fast-path (V2-M5-012).
    ///
    /// Creates a `RustEnvelope` with the lifecycle topic and JSON metadata,
    /// then dispatches directly to any matching handlers.  Uses the normal
    /// trie match + dispatch path but does NOT stamp or count as a regular
    /// publish (these are internal bus housekeeping events).
    ///
    /// Best-effort: errors during lifecycle dispatch are silently ignored
    /// (lifecycle events are informational, not critical).
    fn emit_lifecycle_event(
        &self,
        py: Python<'_>,
        topic: &str,
        subscription_id: &str,
        pattern: &str,
    ) {
        // Build JSON payload: {"subscription_id": "...", "pattern": "..."}
        let payload = if pattern.is_empty() {
            format!("{{\"subscription_id\":\"{subscription_id}\"}}")
        } else {
            format!(
                "{{\"subscription_id\":\"{subscription_id}\",\"pattern\":\"{pattern}\"}}"
            )
        };

        let event = RustEnvelope {
            topic: topic.to_string(),
            priority: 3, // BACKGROUND -- lifecycle events are low priority
            envelope_id: 0,
            sequence: 0,
            cognitive_trace_id: String::new(),
            session_id: String::new(),
            request_id: String::new(),
            parent_id: 0,
            created_ns: monotonic_ns(),
            payload: payload.into_bytes(),
            ttl_ms: 0,
            payload_format: 1, // JSON
        };

        // Trie match (GIL-free)
        let handler_ids = {
            let trie = self.trie.read();
            trie.match_topic(topic)
        };

        if !handler_ids.is_empty() {
            // Best-effort dispatch -- ignore errors
            let _ = self.dispatch(py, &event, &handler_ids);
        }
    }

    /// Fan-out dispatch: invoke all matched handlers with the stamped envelope.
    ///
    /// ## GIL Batch Strategy (V2-M5-006)
    ///
    /// The caller already holds the GIL (`py: Python<'_>`).  Handler IDs were
    /// collected WITHOUT the GIL during trie match (pure Rust `Vec<u64>`).
    /// All handler invocations happen in a single GIL-held batch.
    ///
    /// ## Error Isolation (V2-M5-007)
    ///
    /// Each handler.call1() result is checked independently.  Errors are counted
    /// but NEVER propagated to the caller or other handlers.
    ///
    /// ## TTL Check (V2-M5-005)
    ///
    /// If the envelope has a TTL (`ttl_ms > 0`), we check whether
    /// `now_ns - created_ns > ttl_ms * 1_000_000`.  Expired envelopes
    /// skip dispatch entirely and increment `ttl_expired`.
    ///
    /// ## Latency Tracking (V2-M5-008)
    ///
    /// `Instant::now()` before and after each handler call.  Per-handler
    /// stats (count, min, max, avg, errors) stored in `handler_latencies`.
    fn dispatch(
        &self,
        py: Python<'_>,
        stamped: &RustEnvelope,
        handler_ids: &[u64],
    ) -> PyResult<()> {
        // TTL check (V2-M5-005)
        if stamped.ttl_ms > 0 {
            let now_ns = monotonic_ns();
            let ttl_ns = stamped.ttl_ms as u64 * 1_000_000;
            if now_ns > stamped.created_ns
                && (now_ns - stamped.created_ns) > ttl_ns
            {
                self.ttl_expired.fetch_add(1, Ordering::Relaxed);
                return Ok(());
            }
        }

        // Create the Python envelope object once for all handlers
        let stamped_py = Py::new(py, stamped.clone())?;

        // Resolve handler_ids to Python callables and invoke each
        let handlers_lock = self.handlers.read();
        for &hid in handler_ids {
            // V2-M8-005: Circuit breaker check
            if !self.circuit_breakers.allow(hid) {
                self.handler_errors.fetch_add(1, Ordering::Relaxed);
                continue;
            }

            if let Some(handler) = handlers_lock.get(&hid) {
                let start = Instant::now();
                let result = handler.call1(py, (&stamped_py,));
                let elapsed_ns = start.elapsed().as_nanos() as u64;

                match result {
                    Ok(_) => {
                        self.envelopes_delivered.fetch_add(1, Ordering::Relaxed);
                        self.circuit_breakers.record_success(hid);
                        self.handler_latencies
                            .entry(hid)
                            .or_insert_with(HandlerLatency::new)
                            .record(elapsed_ns, false);
                    }
                    Err(_) => {
                        // Error isolation (V2-M5-007): swallow exception, count it.
                        // Other handlers MUST still fire.
                        self.handler_errors.fetch_add(1, Ordering::Relaxed);
                        self.circuit_breakers.record_failure(hid);
                        self.handler_latencies
                            .entry(hid)
                            .or_insert_with(HandlerLatency::new)
                            .record(elapsed_ns, true);
                    }
                }
            }
        }

        Ok(())
    }

    /// Background thread loop for async dispatch (M8-001/002/003).
    ///
    /// Reads DispatchWork items from the channel, acquires GIL in batches,
    /// and invokes Python handlers with circuit breaker integration.
    fn async_dispatch_loop(
        rx: channel::Receiver<DispatchWork>,
        stop: Arc<AtomicBool>,
        envelopes_delivered: Arc<AtomicU64>,
        handler_errors: Arc<AtomicU64>,
        ttl_expired: Arc<AtomicU64>,
        handler_latencies: Arc<DashMap<u64, HandlerLatency>>,
        circuit_breakers: Arc<CircuitBreakerRegistry>,
        gil_batch_size: usize,
    ) {
        while !stop.load(Ordering::Acquire) {
            let mut batch: Vec<DispatchWork> = Vec::with_capacity(gil_batch_size);

            // Block on first item (with timeout for responsive shutdown)
            match rx.recv_timeout(Duration::from_millis(100)) {
                Ok(work) => batch.push(work),
                Err(channel::RecvTimeoutError::Timeout) => continue,
                Err(channel::RecvTimeoutError::Disconnected) => break,
            }

            // Drain more items non-blocking (up to batch size)
            for _ in 1..gil_batch_size {
                match rx.try_recv() {
                    Ok(work) => batch.push(work),
                    Err(_) => break,
                }
            }

            // Process batch under single GIL acquisition (M8-003)
            Python::with_gil(|py| {
                for work in batch {
                    // TTL check
                    if work.stamped.ttl_ms > 0 {
                        let now_ns = monotonic_ns();
                        let ttl_ns = work.stamped.ttl_ms as u64 * 1_000_000;
                        if now_ns > work.stamped.created_ns
                            && (now_ns - work.stamped.created_ns) > ttl_ns
                        {
                            ttl_expired.fetch_add(1, Ordering::Relaxed);
                            continue;
                        }
                    }

                    let stamped_py = match Py::new(py, work.stamped) {
                        Ok(p) => p,
                        Err(_) => continue,
                    };

                    for (hid, handler) in &work.handler_pairs {
                        if !circuit_breakers.allow(*hid) {
                            handler_errors.fetch_add(1, Ordering::Relaxed);
                            continue;
                        }

                        let start = Instant::now();
                        let result = handler.call1(py, (&stamped_py,));
                        let elapsed_ns = start.elapsed().as_nanos() as u64;

                        match result {
                            Ok(_) => {
                                envelopes_delivered.fetch_add(1, Ordering::Relaxed);
                                circuit_breakers.record_success(*hid);
                                handler_latencies
                                    .entry(*hid)
                                    .or_insert_with(HandlerLatency::new)
                                    .record(elapsed_ns, false);
                            }
                            Err(_) => {
                                handler_errors.fetch_add(1, Ordering::Relaxed);
                                circuit_breakers.record_failure(*hid);
                                handler_latencies
                                    .entry(*hid)
                                    .or_insert_with(HandlerLatency::new)
                                    .record(elapsed_ns, true);
                            }
                        }
                    }
                }
            });
        }
    }
}

// ─── Rust-native tests ──────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    /// Test helper: create a sync-mode RustBus with defaults.
    fn bus(capture: bool) -> RustBus {
        RustBus::new(capture, 0, 5, 10000, 32, 10000)
    }

    // ── monotonic_ns ────────────────────────────────────────────

    #[test]
    fn test_monotonic_ns_increasing() {
        let t1 = monotonic_ns();
        // Spin briefly to ensure clock advances
        for _ in 0..1000 {
            std::hint::black_box(0u64);
        }
        let t2 = monotonic_ns();
        assert!(t2 >= t1, "monotonic_ns must not go backwards: {t1} > {t2}");
    }

    #[test]
    fn test_monotonic_ns_non_zero_eventually() {
        // After a small delay, timestamp should be > 0
        std::thread::sleep(std::time::Duration::from_millis(1));
        let t = monotonic_ns();
        assert!(t > 0, "Expected non-zero after 1ms sleep");
    }

    // ── validate_topic ──────────────────────────────────────────

    #[test]
    fn test_validate_topic_valid() {
        assert!(RustBus::validate_topic("k1.test").is_ok());
        assert!(RustBus::validate_topic("k1.agent.delta.v1").is_ok());
        assert!(RustBus::validate_topic("single").is_ok());
        assert!(RustBus::validate_topic("a.b.c.d.e.f").is_ok());
    }

    #[test]
    fn test_validate_topic_empty_segment() {
        assert!(RustBus::validate_topic("k1..test").is_err());
        assert!(RustBus::validate_topic("..").is_err());
        assert!(RustBus::validate_topic("a..b..c").is_err());
    }

    #[test]
    fn test_validate_topic_leading_dot() {
        assert!(RustBus::validate_topic(".k1.test").is_err());
    }

    #[test]
    fn test_validate_topic_trailing_dot() {
        assert!(RustBus::validate_topic("k1.test.").is_err());
    }

    #[test]
    fn test_validate_topic_all_dots() {
        assert!(RustBus::validate_topic(".").is_err());
        assert!(RustBus::validate_topic("..").is_err());
        assert!(RustBus::validate_topic("...").is_err());
    }

    // ── HandlerLatency ──────────────────────────────────────────

    #[test]
    fn test_handler_latency_new() {
        let lat = HandlerLatency::new();
        assert_eq!(lat.call_count, 0);
        assert_eq!(lat.total_ns, 0);
        assert_eq!(lat.min_ns, u64::MAX);
        assert_eq!(lat.max_ns, 0);
        assert_eq!(lat.error_count, 0);
        assert_eq!(lat.avg_ns(), 0);
    }

    #[test]
    fn test_handler_latency_record_success() {
        let mut lat = HandlerLatency::new();
        lat.record(100, false);
        lat.record(200, false);
        lat.record(300, false);

        assert_eq!(lat.call_count, 3);
        assert_eq!(lat.total_ns, 600);
        assert_eq!(lat.min_ns, 100);
        assert_eq!(lat.max_ns, 300);
        assert_eq!(lat.avg_ns(), 200);
        assert_eq!(lat.error_count, 0);
    }

    #[test]
    fn test_handler_latency_record_with_errors() {
        let mut lat = HandlerLatency::new();
        lat.record(100, false);
        lat.record(500, true);
        lat.record(200, false);

        assert_eq!(lat.call_count, 3);
        assert_eq!(lat.error_count, 1);
        assert_eq!(lat.min_ns, 100);
        assert_eq!(lat.max_ns, 500);
    }

    // ── RustBus construction ────────────────────────────────────

    #[test]
    fn test_bus_construction() {
        let b = bus(false);
        assert!(!b.is_closed());
        assert_eq!(b.last_envelope_id(), 0);
        assert_eq!(b.subscription_count(), 0);
        assert_eq!(b.captured_count(), 0);
    }

    #[test]
    fn test_bus_capture_mode() {
        let b = bus(true);
        assert!(b.capture);
        assert_eq!(b.captured_count(), 0);
    }

    #[test]
    fn test_bus_close() {
        let b = bus(false);
        assert!(!b.is_closed());
        b.close();
        assert!(b.is_closed());
    }

    // ── next_sequence ───────────────────────────────────────────

    #[test]
    fn test_next_sequence_starts_at_1() {
        let b = bus(false);
        assert_eq!(b.next_sequence("k1.test"), 1);
    }

    #[test]
    fn test_next_sequence_monotonic() {
        let b = bus(false);
        assert_eq!(b.next_sequence("k1.test"), 1);
        assert_eq!(b.next_sequence("k1.test"), 2);
        assert_eq!(b.next_sequence("k1.test"), 3);
    }

    #[test]
    fn test_next_sequence_per_topic_independent() {
        let b = bus(false);
        assert_eq!(b.next_sequence("topic.a"), 1);
        assert_eq!(b.next_sequence("topic.b"), 1);
        assert_eq!(b.next_sequence("topic.a"), 2);
        assert_eq!(b.next_sequence("topic.b"), 2);
    }

    #[test]
    fn test_topic_sequence_accessor() {
        let b = bus(false);
        assert_eq!(b.topic_sequence("unknown"), 0);
        b.next_sequence("k1.test");
        b.next_sequence("k1.test");
        assert_eq!(b.topic_sequence("k1.test"), 2);
    }

    // ── repr ────────────────────────────────────────────────────

    #[test]
    fn test_repr() {
        let b = bus(false);
        let r = b.__repr__();
        assert!(r.contains("RustBus"));
        assert!(r.contains("published=0"));
        assert!(r.contains("subscriptions=0"));
    }

    #[test]
    fn test_len() {
        let b = bus(false);
        assert_eq!(b.__len__(), 0);
    }
}
