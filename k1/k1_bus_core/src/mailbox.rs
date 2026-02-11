//! V2-M7-001/002/003/004: Rust Mailbox and MailboxRouter.
//!
//! Per-actor bounded mailbox with WFQ priority scheduling and
//! blocking receive via `parking_lot::Condvar` (GIL released from Python).
//!
//! ## Architecture
//!
//! ```text
//! +------------------+     +------------------+     +--------------+
//! | Sender           |---->| MailboxRouter    |---->| Mailbox      |
//! | (deliver(id,env))|     | (DashMap registry)|    | (bounded)    |
//! +------------------+     +------------------+     | +----------+ |
//!                                                   | | URGENT   | |
//!                                                   | | REALTIME | |
//!                                                   | | INTERACT | |
//!                                                   | | BACKGRND | |
//!                                                   | +----------+ |
//!                                                   +--------------+
//! ```
//!
//! ## WFQ Priority (M7-001)
//!
//! When `priority_wfq=true`, the mailbox maintains 4 sub-queues (one per
//! Priority level).  Dequeue uses deficit round-robin with configurable
//! weights `[4, 3, 2, 1]` (URGENT gets 4x BACKGROUND).  BACKGROUND is
//! never starved.
//!
//! When `priority_wfq=false`, a single FIFO queue is used.
//!
//! ## Blocking Receive (M7-002)
//!
//! `receive(timeout_ms)` blocks on `parking_lot::Condvar`.  The Python
//! wrapper releases the GIL via `py.allow_threads()`, allowing other
//! Python threads to call `deliver()` concurrently.
//!
//! ## Thread Safety
//!
//! - `MailboxInner`: `parking_lot::Mutex` + `Condvar` for queues.
//! - `MailboxRouterInner`: `DashMap` for lock-free actor registry lookup.
//! - Deliver and receive run concurrently from different threads.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use dashmap::DashMap;
use parking_lot::{Condvar, Mutex};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::dlq::DeadLetterQueueInner;
use crate::rust_envelope::RustEnvelope;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Number of priority levels.
const NUM_PRIORITIES: usize = 4;

/// Default mailbox capacity.
const DEFAULT_CAPACITY: usize = 256;

/// Default WFQ weights: URGENT=4, REALTIME=3, INTERACTIVE=2, BACKGROUND=1.
const DEFAULT_WEIGHTS: [u64; NUM_PRIORITIES] = [4, 3, 2, 1];

/// Priority names for display and Python dict keys.
const PRIORITY_NAMES: [&str; NUM_PRIORITIES] = [
    "URGENT", "REALTIME", "INTERACTIVE", "BACKGROUND",
];

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

/// Internal error type for mailbox operations.
#[derive(Debug, Clone)]
pub(crate) enum MailboxError {
    /// Mailbox at capacity.
    Full(String, usize),
    /// Mailbox or router is closed.
    Closed(String),
    /// Actor not registered in router.
    UnknownActor(String),
    /// Router is closed.
    RouterClosed,
    /// Empty actor_id supplied.
    EmptyActorId,
    /// Actor already registered.
    AlreadyRegistered(String),
}

impl MailboxError {
    /// Convert to a Python exception with a descriptive message.
    pub fn to_pyerr(&self) -> PyErr {
        match self {
            MailboxError::Full(actor_id, capacity) => {
                pyo3::exceptions::PyRuntimeError::new_err(format!(
                    "Mailbox for actor '{}' is full (capacity={})",
                    actor_id, capacity,
                ))
            }
            MailboxError::Closed(actor_id) => {
                pyo3::exceptions::PyValueError::new_err(format!(
                    "Mailbox for actor '{}' is closed",
                    actor_id,
                ))
            }
            MailboxError::UnknownActor(actor_id) => {
                pyo3::exceptions::PyValueError::new_err(format!(
                    "Unknown actor: '{}'",
                    actor_id,
                ))
            }
            MailboxError::RouterClosed => {
                pyo3::exceptions::PyValueError::new_err("MailboxRouter is closed")
            }
            MailboxError::EmptyActorId => {
                pyo3::exceptions::PyValueError::new_err("actor_id must not be empty")
            }
            MailboxError::AlreadyRegistered(actor_id) => {
                pyo3::exceptions::PyValueError::new_err(format!(
                    "Actor '{}' is already registered",
                    actor_id,
                ))
            }
        }
    }
}

// ---------------------------------------------------------------------------
// MailboxState -- mutable state guarded by Mutex
// ---------------------------------------------------------------------------

struct MailboxState {
    /// Per-priority sub-queues (used in WFQ mode).
    queues: [VecDeque<RustEnvelope>; NUM_PRIORITIES],
    /// Single FIFO queue (used when priority_wfq=false).
    single_queue: VecDeque<RustEnvelope>,
    /// Total envelopes in all queues.
    size: usize,
    /// True after close() called.
    closed: bool,
    /// Inline WFQ deficit counters (no separate lock needed).
    deficits: [i64; NUM_PRIORITIES],
    /// Per-priority weights for deficit round-robin.
    weights: [u64; NUM_PRIORITIES],
}

impl MailboxState {
    fn new(weights: [u64; NUM_PRIORITIES]) -> Self {
        Self {
            queues: [
                VecDeque::new(),
                VecDeque::new(),
                VecDeque::new(),
                VecDeque::new(),
            ],
            single_queue: VecDeque::new(),
            size: 0,
            closed: false,
            deficits: [0; NUM_PRIORITIES],
            weights,
        }
    }
}

// ---------------------------------------------------------------------------
// MailboxInner -- thread-safe, shared via Arc
// ---------------------------------------------------------------------------

/// Core mailbox state.  Shared between `RustMailbox` (Python wrapper)
/// and `MailboxRouterInner` (router registry).
pub(crate) struct MailboxInner {
    actor_id: String,
    capacity: usize,
    priority_wfq: bool,
    state: Mutex<MailboxState>,
    not_empty: Condvar,
    delivered_count: AtomicU64,
    received_count: AtomicU64,
}

impl MailboxInner {
    /// Create a new mailbox.
    pub fn new(
        actor_id: String,
        capacity: usize,
        priority_wfq: bool,
        weights: [u64; NUM_PRIORITIES],
    ) -> Self {
        Self {
            actor_id,
            capacity,
            priority_wfq,
            state: Mutex::new(MailboxState::new(weights)),
            not_empty: Condvar::new(),
            delivered_count: AtomicU64::new(0),
            received_count: AtomicU64::new(0),
        }
    }

    /// Deliver an envelope to this mailbox.
    ///
    /// Returns `MailboxError::Full` if at capacity, `Closed` if closed.
    pub fn deliver(&self, envelope: RustEnvelope) -> Result<(), MailboxError> {
        {
            let mut state = self.state.lock();

            if state.closed {
                return Err(MailboxError::Closed(self.actor_id.clone()));
            }
            if state.size >= self.capacity {
                return Err(MailboxError::Full(
                    self.actor_id.clone(),
                    self.capacity,
                ));
            }

            let priority = envelope.priority.min(3) as usize;

            if self.priority_wfq {
                state.deficits[priority] += state.weights[priority] as i64;
                state.queues[priority].push_back(envelope);
            } else {
                state.single_queue.push_back(envelope);
            }

            state.size += 1;
        } // Mutex released before condvar notify

        self.delivered_count.fetch_add(1, Ordering::Relaxed);
        self.not_empty.notify_one();

        Ok(())
    }

    /// Receive the next envelope.
    ///
    /// `timeout_ms=0`: non-blocking (return None immediately if empty).
    /// `timeout_ms>0`: block up to `timeout_ms` milliseconds.
    ///
    /// Called from Python via `py.allow_threads()` to release the GIL.
    pub fn receive(&self, timeout_ms: u64) -> Option<RustEnvelope> {
        let mut state = self.state.lock();

        // Fast path: immediate dequeue
        if let Some(env) = Self::try_dequeue(&mut state, self.priority_wfq) {
            self.received_count.fetch_add(1, Ordering::Relaxed);
            return Some(env);
        }

        if timeout_ms == 0 {
            return None;
        }

        // Block until data arrives or timeout
        let timeout = Duration::from_millis(timeout_ms);
        self.not_empty.wait_for(&mut state, timeout);

        // Re-try after wake (may be spurious or close notification)
        let env = Self::try_dequeue(&mut state, self.priority_wfq);
        if env.is_some() {
            self.received_count.fetch_add(1, Ordering::Relaxed);
        }
        env
    }

    /// Close the mailbox.  Prevents new deliveries.
    /// Existing envelopes can still be drained via `receive()`.
    pub fn close(&self) {
        {
            let mut state = self.state.lock();
            state.closed = true;
        }
        // Wake all blocked receivers so they can return None
        self.not_empty.notify_all();
    }

    /// Number of envelopes waiting in this mailbox.
    pub fn pending(&self) -> usize {
        self.state.lock().size
    }

    /// Is the mailbox closed?
    pub fn is_closed(&self) -> bool {
        self.state.lock().closed
    }

    /// Queue depth per priority level.
    ///
    /// Returns empty Vec when `priority_wfq=false` (FIFO mode).
    pub fn depth_by_priority(&self) -> Vec<(String, usize)> {
        if !self.priority_wfq {
            return Vec::new();
        }
        let state = self.state.lock();
        (0..NUM_PRIORITIES)
            .map(|p| (PRIORITY_NAMES[p].to_string(), state.queues[p].len()))
            .collect()
    }

    // -- Dequeue logic (called under lock) --------------------------------

    /// Try to dequeue one envelope from the mailbox.
    fn try_dequeue(
        state: &mut MailboxState,
        priority_wfq: bool,
    ) -> Option<RustEnvelope> {
        if state.size == 0 {
            return None;
        }
        if priority_wfq {
            Self::dequeue_wfq(state)
        } else {
            Self::dequeue_fifo(state)
        }
    }

    /// Deficit round-robin dequeue across 4 priority queues.
    fn dequeue_wfq(state: &mut MailboxState) -> Option<RustEnvelope> {
        let mut best: Option<usize> = None;
        let mut best_deficit = i64::MIN;

        for p in 0..NUM_PRIORITIES {
            if !state.queues[p].is_empty() && state.deficits[p] > best_deficit {
                best_deficit = state.deficits[p];
                best = Some(p);
            }
        }

        if let Some(p) = best {
            if let Some(env) = state.queues[p].pop_front() {
                state.deficits[p] -= 1;
                state.size -= 1;
                return Some(env);
            }
        }

        None
    }

    /// Simple FIFO dequeue from single queue.
    fn dequeue_fifo(state: &mut MailboxState) -> Option<RustEnvelope> {
        if let Some(env) = state.single_queue.pop_front() {
            state.size -= 1;
            return Some(env);
        }
        None
    }
}

// ---------------------------------------------------------------------------
// RustMailbox -- #[pyclass] wrapper
// ---------------------------------------------------------------------------

/// Python-exposed per-actor mailbox.
///
/// Created by `RustMailboxRouter.register()` or directly for testing.
#[pyclass(name = "RustMailbox")]
pub(crate) struct RustMailbox {
    pub(crate) inner: Arc<MailboxInner>,
}

#[pymethods]
impl RustMailbox {
    /// Create a standalone mailbox (for testing).
    ///
    /// Args:
    ///     actor_id: Actor identifier (must not be empty).
    ///     capacity: Maximum queue depth (default 256).
    ///     priority_wfq: Use WFQ priority scheduling (default true).
    ///     weights: Optional [URGENT, REALTIME, INTERACTIVE, BACKGROUND] weights.
    #[new]
    #[pyo3(signature = (actor_id, capacity=256, priority_wfq=true, weights=None))]
    fn new(
        actor_id: &str,
        capacity: usize,
        priority_wfq: bool,
        weights: Option<Vec<u64>>,
    ) -> PyResult<Self> {
        if actor_id.is_empty() {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "actor_id must not be empty",
            ));
        }
        if capacity == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "capacity must be > 0",
            ));
        }
        let w = parse_weights(weights)?;
        Ok(Self {
            inner: Arc::new(MailboxInner::new(
                actor_id.to_string(),
                capacity,
                priority_wfq,
                w,
            )),
        })
    }

    /// Deliver an envelope to this mailbox.
    ///
    /// Raises RuntimeError on backpressure, ValueError if closed.
    fn deliver(&self, envelope: &RustEnvelope) -> PyResult<()> {
        self.inner
            .deliver(envelope.clone())
            .map_err(|e| e.to_pyerr())
    }

    /// Receive the next envelope.  Releases GIL during wait.
    ///
    /// Args:
    ///     timeout_ms: 0 = non-blocking.  >0 = block up to timeout_ms ms.
    ///
    /// Returns:
    ///     RustEnvelope or None.
    #[pyo3(signature = (timeout_ms=0))]
    fn receive(&self, py: Python<'_>, timeout_ms: u64) -> Option<RustEnvelope> {
        let inner = self.inner.clone();
        py.allow_threads(move || inner.receive(timeout_ms))
    }

    /// Number of envelopes waiting.
    fn pending(&self) -> usize {
        self.inner.pending()
    }

    /// Close the mailbox.
    fn close(&self) {
        self.inner.close();
    }

    /// True if the mailbox has been closed.
    #[getter]
    fn closed(&self) -> bool {
        self.inner.is_closed()
    }

    /// The actor this mailbox belongs to.
    #[getter]
    fn actor_id(&self) -> &str {
        &self.inner.actor_id
    }

    /// Maximum queue capacity.
    #[getter]
    fn capacity(&self) -> usize {
        self.inner.capacity
    }

    /// Total envelopes delivered to this mailbox (lifetime).
    #[getter]
    fn delivered_count(&self) -> u64 {
        self.inner.delivered_count.load(Ordering::Relaxed)
    }

    /// Total envelopes received from this mailbox (lifetime).
    #[getter]
    fn received_count(&self) -> u64 {
        self.inner.received_count.load(Ordering::Relaxed)
    }

    /// Queue depth per priority level.
    ///
    /// Returns empty dict `{}` when WFQ is disabled (FIFO mode).
    fn depth_by_priority(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let depths = self.inner.depth_by_priority();
        let dict = PyDict::new(py);
        for (name, count) in depths {
            dict.set_item(name, count)?;
        }
        Ok(dict.into())
    }

    fn __repr__(&self) -> String {
        let mode = if self.inner.priority_wfq { "WFQ" } else { "FIFO" };
        format!(
            "RustMailbox(actor={:?}, pending={}/{}, mode={})",
            self.inner.actor_id,
            self.inner.pending(),
            self.inner.capacity,
            mode,
        )
    }
}

// ---------------------------------------------------------------------------
// MailboxRouterInner
// ---------------------------------------------------------------------------

/// Core router state.  Wraps DashMap for lock-free actor lookup.
pub(crate) struct MailboxRouterInner {
    mailboxes: DashMap<String, Arc<MailboxInner>>,
    closed: AtomicBool,
    dlq: Mutex<Option<Arc<DeadLetterQueueInner>>>,
}

impl MailboxRouterInner {
    pub fn new() -> Self {
        Self {
            mailboxes: DashMap::new(),
            closed: AtomicBool::new(false),
            dlq: Mutex::new(None),
        }
    }

    /// Deliver an envelope to a named actor's mailbox.
    ///
    /// On backpressure: routes envelope to DLQ if attached, *then* returns
    /// the `Full` error so the caller still knows delivery was rejected.
    pub fn deliver(
        &self,
        actor_id: &str,
        envelope: RustEnvelope,
    ) -> Result<(), MailboxError> {
        if self.closed.load(Ordering::Acquire) {
            return Err(MailboxError::RouterClosed);
        }

        // Clone Arc (release DashMap shard lock before calling deliver)
        let mailbox: Arc<MailboxInner> = self
            .mailboxes
            .get(actor_id)
            .map(|r| r.value().clone())
            .ok_or_else(|| MailboxError::UnknownActor(actor_id.to_string()))?;

        match mailbox.deliver(envelope.clone()) {
            Ok(()) => Ok(()),
            Err(MailboxError::Full(ref actor, ref cap)) => {
                // Route to DLQ if attached
                if let Some(dlq) = self.dlq.lock().as_ref() {
                    dlq.push(
                        envelope,
                        crate::dlq::DlqReason::BackpressureFull,
                    );
                }
                Err(MailboxError::Full(actor.clone(), *cap))
            }
            Err(e) => Err(e),
        }
    }

    /// Register an actor and create its mailbox.
    pub fn register(
        &self,
        actor_id: &str,
        capacity: Option<usize>,
        priority_wfq: Option<bool>,
        weights: Option<[u64; NUM_PRIORITIES]>,
    ) -> Result<Arc<MailboxInner>, MailboxError> {
        if actor_id.is_empty() {
            return Err(MailboxError::EmptyActorId);
        }
        if self.closed.load(Ordering::Acquire) {
            return Err(MailboxError::RouterClosed);
        }

        let cap = capacity.unwrap_or(DEFAULT_CAPACITY);
        let wfq = priority_wfq.unwrap_or(true);
        let w = weights.unwrap_or(DEFAULT_WEIGHTS);

        let inner = Arc::new(MailboxInner::new(
            actor_id.to_string(),
            cap,
            wfq,
            w,
        ));

        use dashmap::mapref::entry::Entry;
        match self.mailboxes.entry(actor_id.to_string()) {
            Entry::Occupied(_) => {
                Err(MailboxError::AlreadyRegistered(actor_id.to_string()))
            }
            Entry::Vacant(e) => {
                e.insert(inner.clone());
                Ok(inner)
            }
        }
    }

    /// Unregister an actor and close its mailbox.
    ///
    /// Returns true if the actor was found and removed.
    pub fn unregister(&self, actor_id: &str) -> bool {
        if let Some((_, mailbox)) = self.mailboxes.remove(actor_id) {
            mailbox.close();
            true
        } else {
            false
        }
    }

    /// List of currently registered actor IDs.
    pub fn registered_actors(&self) -> Vec<String> {
        self.mailboxes.iter().map(|r| r.key().clone()).collect()
    }

    /// Close the router and all mailboxes.
    pub fn close(&self) {
        self.closed.store(true, Ordering::Release);
        for entry in self.mailboxes.iter() {
            entry.value().close();
        }
    }

    pub fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Acquire)
    }

    pub fn actor_count(&self) -> usize {
        self.mailboxes.len()
    }

    pub fn mailbox_for(&self, actor_id: &str) -> Option<Arc<MailboxInner>> {
        self.mailboxes.get(actor_id).map(|r| r.value().clone())
    }
}

// ---------------------------------------------------------------------------
// RustMailboxRouter -- #[pyclass] wrapper
// ---------------------------------------------------------------------------

/// Python-exposed mailbox router -- actor registry + delivery dispatch.
#[pyclass(name = "RustMailboxRouter")]
pub(crate) struct RustMailboxRouter {
    inner: MailboxRouterInner,
}

#[pymethods]
impl RustMailboxRouter {
    #[new]
    fn new() -> Self {
        Self {
            inner: MailboxRouterInner::new(),
        }
    }

    /// Deliver an envelope to a specific actor's mailbox.
    ///
    /// Raises ValueError for unknown actor or closed router.
    /// Raises RuntimeError for backpressure.
    fn deliver(
        &self,
        actor_id: &str,
        envelope: &RustEnvelope,
    ) -> PyResult<()> {
        self.inner
            .deliver(actor_id, envelope.clone())
            .map_err(|e| e.to_pyerr())
    }

    /// Register an actor and create its mailbox.
    ///
    /// Args:
    ///     actor_id: Unique actor identifier (must not be empty).
    ///     capacity: Queue capacity (default 256).
    ///     priority_wfq: Enable WFQ priority (default true).
    ///
    /// Returns:
    ///     RustMailbox for the actor to receive from.
    #[pyo3(signature = (actor_id, capacity=None, priority_wfq=None))]
    fn register(
        &self,
        actor_id: &str,
        capacity: Option<usize>,
        priority_wfq: Option<bool>,
    ) -> PyResult<RustMailbox> {
        let inner = self
            .inner
            .register(actor_id, capacity, priority_wfq, None)
            .map_err(|e| e.to_pyerr())?;
        Ok(RustMailbox { inner })
    }

    /// Unregister an actor and close its mailbox.
    ///
    /// Returns true if found and removed, false otherwise.
    fn unregister(&self, actor_id: &str) -> bool {
        self.inner.unregister(actor_id)
    }

    /// List of currently registered actor IDs.
    fn registered_actors(&self) -> Vec<String> {
        self.inner.registered_actors()
    }

    /// Close the router and all mailboxes.
    fn close(&self) {
        self.inner.close();
    }

    /// True if the router has been closed.
    #[getter]
    fn closed(&self) -> bool {
        self.inner.is_closed()
    }

    /// Number of registered actors.
    #[getter]
    fn actor_count(&self) -> usize {
        self.inner.actor_count()
    }

    /// Get the mailbox for an actor (observability/testing).
    fn mailbox_for(&self, actor_id: &str) -> Option<RustMailbox> {
        self.inner
            .mailbox_for(actor_id)
            .map(|inner| RustMailbox { inner })
    }

    /// Per-actor stats snapshot.
    ///
    /// Returns `{actor_id: {"pending": N, "delivered": N, "received": N, "capacity": N}}`.
    fn stats_snapshot(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let outer = PyDict::new(py);
        for entry in self.inner.mailboxes.iter() {
            let actor_id = entry.key();
            let mb = entry.value();
            let inner_dict = PyDict::new(py);
            inner_dict.set_item("pending", mb.pending())?;
            inner_dict.set_item(
                "delivered",
                mb.delivered_count.load(Ordering::Relaxed),
            )?;
            inner_dict.set_item(
                "received",
                mb.received_count.load(Ordering::Relaxed),
            )?;
            inner_dict.set_item("capacity", mb.capacity)?;
            outer.set_item(actor_id.as_str(), inner_dict)?;
        }
        Ok(outer.into())
    }

    /// Attach a dead-letter queue for backpressure routing.
    fn set_dlq(&self, dlq: &crate::dlq::DeadLetterQueue) {
        *self.inner.dlq.lock() = Some(dlq.inner.clone());
    }

    fn __repr__(&self) -> String {
        format!(
            "RustMailboxRouter(actors={}, closed={})",
            self.inner.actor_count(),
            self.inner.is_closed(),
        )
    }
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

fn parse_weights(weights: Option<Vec<u64>>) -> PyResult<[u64; NUM_PRIORITIES]> {
    match weights {
        Some(w) => {
            if w.len() != NUM_PRIORITIES {
                Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Expected {} weights, got {}",
                    NUM_PRIORITIES,
                    w.len(),
                )))
            } else {
                Ok([w[0], w[1], w[2], w[3]])
            }
        }
        None => Ok(DEFAULT_WEIGHTS),
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;

    fn env(topic: &str, priority: u8, payload: &[u8]) -> RustEnvelope {
        RustEnvelope {
            topic: topic.to_string(),
            priority,
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

    // ── MailboxInner: FIFO mode ─────────────────────────────────

    #[test]
    fn test_fifo_empty_returns_none() {
        let mb = MailboxInner::new("a".into(), 10, false, DEFAULT_WEIGHTS);
        assert!(mb.receive(0).is_none());
        assert_eq!(mb.pending(), 0);
    }

    #[test]
    fn test_fifo_delivery_order() {
        let mb = MailboxInner::new("a".into(), 10, false, DEFAULT_WEIGHTS);
        for i in 0..5 {
            mb.deliver(env("t", 2, format!("msg{i}").as_bytes()))
                .unwrap();
        }
        assert_eq!(mb.pending(), 5);
        for i in 0..5 {
            let e = mb.receive(0).unwrap();
            assert_eq!(e.payload, format!("msg{i}").as_bytes());
        }
        assert!(mb.receive(0).is_none());
    }

    #[test]
    fn test_fifo_ignores_priority() {
        let mb = MailboxInner::new("a".into(), 10, false, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 3, b"bg")).unwrap();
        mb.deliver(env("t", 0, b"urg")).unwrap();

        let first = mb.receive(0).unwrap();
        assert_eq!(first.payload, b"bg"); // BACKGROUND first because FIFO
    }

    // ── MailboxInner: WFQ mode ──────────────────────────────────

    #[test]
    fn test_wfq_urgent_before_background() {
        let mb = MailboxInner::new("a".into(), 10, true, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 3, b"bg")).unwrap();
        mb.deliver(env("t", 0, b"urg")).unwrap();

        assert_eq!(mb.receive(0).unwrap().payload, b"urg");
        assert_eq!(mb.receive(0).unwrap().payload, b"bg");
    }

    #[test]
    fn test_wfq_all_four_levels() {
        let mb = MailboxInner::new("a".into(), 20, true, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 3, b"bg")).unwrap();
        mb.deliver(env("t", 2, b"int")).unwrap();
        mb.deliver(env("t", 1, b"rt")).unwrap();
        mb.deliver(env("t", 0, b"urg")).unwrap();

        let r: Vec<Vec<u8>> = (0..4)
            .map(|_| mb.receive(0).unwrap().payload.clone())
            .collect();
        assert_eq!(
            r,
            vec![
                b"urg".to_vec(),
                b"rt".to_vec(),
                b"int".to_vec(),
                b"bg".to_vec(),
            ]
        );
    }

    #[test]
    fn test_wfq_same_priority_fifo() {
        let mb = MailboxInner::new("a".into(), 10, true, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 2, b"first")).unwrap();
        mb.deliver(env("t", 2, b"second")).unwrap();
        mb.deliver(env("t", 2, b"third")).unwrap();

        let r: Vec<Vec<u8>> = (0..3)
            .map(|_| mb.receive(0).unwrap().payload.clone())
            .collect();
        assert_eq!(r, vec![b"first".to_vec(), b"second".to_vec(), b"third".to_vec()]);
    }

    #[test]
    fn test_wfq_interleaving() {
        let mb = MailboxInner::new("a".into(), 10, true, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 2, b"int1")).unwrap();
        mb.deliver(env("t", 2, b"int2")).unwrap();
        mb.deliver(env("t", 0, b"urg1")).unwrap();

        let first = mb.receive(0).unwrap();
        assert_eq!(first.payload, b"urg1"); // URGENT even though injected last
    }

    // ── Capacity / backpressure ─────────────────────────────────

    #[test]
    fn test_at_capacity_returns_full() {
        let mb = MailboxInner::new("a".into(), 3, true, DEFAULT_WEIGHTS);
        for _ in 0..3 {
            mb.deliver(env("t", 2, b"x")).unwrap();
        }
        match mb.deliver(env("t", 2, b"overflow")) {
            Err(MailboxError::Full(id, cap)) => {
                assert_eq!(id, "a");
                assert_eq!(cap, 3);
            }
            other => panic!("Expected Full, got {:?}", other),
        }
    }

    #[test]
    fn test_drain_frees_capacity() {
        let mb = MailboxInner::new("a".into(), 2, true, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 2, b"1")).unwrap();
        mb.deliver(env("t", 2, b"2")).unwrap();
        assert!(mb.deliver(env("t", 2, b"3")).is_err());
        mb.receive(0); // free one slot
        mb.deliver(env("t", 2, b"3")).unwrap();
        assert_eq!(mb.pending(), 2);
    }

    // ── Blocking receive ────────────────────────────────────────

    #[test]
    fn test_blocking_receive_wakeup() {
        let mb = Arc::new(MailboxInner::new(
            "a".into(), 10, true, DEFAULT_WEIGHTS,
        ));
        let mb2 = mb.clone();

        let handle = thread::spawn(move || mb2.receive(2000));

        thread::sleep(Duration::from_millis(20));
        mb.deliver(env("t", 2, b"wakeup")).unwrap();

        let result = handle.join().unwrap();
        assert_eq!(result.unwrap().payload, b"wakeup");
    }

    #[test]
    fn test_blocking_receive_timeout() {
        let mb = MailboxInner::new("a".into(), 10, true, DEFAULT_WEIGHTS);
        let start = std::time::Instant::now();
        let result = mb.receive(50);
        assert!(result.is_none());
        assert!(start.elapsed() >= Duration::from_millis(40));
    }

    // ── Close / lifecycle ───────────────────────────────────────

    #[test]
    fn test_close_prevents_delivery() {
        let mb = MailboxInner::new("a".into(), 10, true, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 2, b"before")).unwrap();
        mb.close();
        assert!(matches!(
            mb.deliver(env("t", 2, b"after")),
            Err(MailboxError::Closed(_))
        ));
    }

    #[test]
    fn test_close_allows_drain() {
        let mb = MailboxInner::new("a".into(), 10, true, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 2, b"drain")).unwrap();
        mb.close();
        assert_eq!(mb.receive(0).unwrap().payload, b"drain");
    }

    #[test]
    fn test_close_wakes_blockers() {
        let mb = Arc::new(MailboxInner::new(
            "a".into(), 10, true, DEFAULT_WEIGHTS,
        ));
        let mb2 = mb.clone();

        let handle = thread::spawn(move || mb2.receive(5000));

        thread::sleep(Duration::from_millis(20));
        mb.close();

        // Should return promptly, not wait 5 seconds
        let start = std::time::Instant::now();
        let result = handle.join().unwrap();
        assert!(result.is_none());
        assert!(start.elapsed() < Duration::from_secs(3));
    }

    // ── Observability ───────────────────────────────────────────

    #[test]
    fn test_depth_by_priority() {
        let mb = MailboxInner::new("a".into(), 20, true, DEFAULT_WEIGHTS);
        mb.deliver(env("t", 0, b"")).unwrap();
        mb.deliver(env("t", 0, b"")).unwrap();
        mb.deliver(env("t", 3, b"")).unwrap();

        let depths = mb.depth_by_priority();
        assert_eq!(depths.len(), 4);
        assert_eq!(depths[0], ("URGENT".to_string(), 2));
        assert_eq!(depths[1], ("REALTIME".to_string(), 0));
        assert_eq!(depths[2], ("INTERACTIVE".to_string(), 0));
        assert_eq!(depths[3], ("BACKGROUND".to_string(), 1));
    }

    #[test]
    fn test_depth_by_priority_fifo_empty() {
        let mb = MailboxInner::new("a".into(), 10, false, DEFAULT_WEIGHTS);
        assert!(mb.depth_by_priority().is_empty());
    }

    #[test]
    fn test_delivered_received_counts() {
        let mb = MailboxInner::new("a".into(), 10, true, DEFAULT_WEIGHTS);
        assert_eq!(mb.delivered_count.load(Ordering::Relaxed), 0);
        assert_eq!(mb.received_count.load(Ordering::Relaxed), 0);

        mb.deliver(env("t", 2, b"")).unwrap();
        mb.deliver(env("t", 2, b"")).unwrap();
        assert_eq!(mb.delivered_count.load(Ordering::Relaxed), 2);

        mb.receive(0);
        assert_eq!(mb.received_count.load(Ordering::Relaxed), 1);
    }

    // ── Router ──────────────────────────────────────────────────

    #[test]
    fn test_router_register_and_deliver() {
        let router = MailboxRouterInner::new();
        let mb = router
            .register("orch", Some(10), Some(true), None)
            .unwrap();

        router
            .deliver("orch", env("t", 2, b"hello"))
            .unwrap();
        let e = mb.receive(0).unwrap();
        assert_eq!(e.payload, b"hello");
    }

    #[test]
    fn test_router_unknown_actor() {
        let router = MailboxRouterInner::new();
        assert!(matches!(
            router.deliver("ghost", env("t", 2, b"")),
            Err(MailboxError::UnknownActor(_))
        ));
    }

    #[test]
    fn test_router_double_register() {
        let router = MailboxRouterInner::new();
        router.register("a", None, None, None).unwrap();
        assert!(matches!(
            router.register("a", None, None, None),
            Err(MailboxError::AlreadyRegistered(_))
        ));
    }

    #[test]
    fn test_router_unregister() {
        let router = MailboxRouterInner::new();
        let mb = router.register("a", None, None, None).unwrap();
        assert!(router.unregister("a"));
        assert!(mb.is_closed());
        assert!(!router.unregister("a"));
    }

    #[test]
    fn test_router_close() {
        let router = MailboxRouterInner::new();
        let mb = router.register("a", None, None, None).unwrap();
        router.close();
        assert!(router.is_closed());
        assert!(mb.is_closed());
        assert!(matches!(
            router.deliver("a", env("t", 2, b"")),
            Err(MailboxError::RouterClosed)
        ));
    }

    #[test]
    fn test_router_concurrent_deliver_receive() {
        let router = Arc::new(MailboxRouterInner::new());
        let mb = router.register("t", Some(5000), Some(true), None).unwrap();
        let mb2 = mb.clone();

        let n_senders = 4;
        let n_per_sender = 200;
        let total = n_senders * n_per_sender;

        let mut handles = Vec::new();

        for t in 0..n_senders {
            let r = router.clone();
            handles.push(thread::spawn(move || {
                for i in 0..n_per_sender {
                    r.deliver(
                        "t",
                        env("t", 2, format!("t{t}-{i}").as_bytes()),
                    )
                    .unwrap();
                }
            }));
        }

        let recv_handle = {
            thread::spawn(move || {
                let mut count = 0;
                loop {
                    if let Some(_) = mb2.receive(100) {
                        count += 1;
                        if count >= total {
                            break;
                        }
                    } else if mb2.is_closed() {
                        break;
                    }
                }
                count
            })
        };

        for h in handles {
            h.join().unwrap();
        }

        // Wait for receiver to drain all
        let received = recv_handle.join().unwrap();
        assert_eq!(received, total);
    }
}
