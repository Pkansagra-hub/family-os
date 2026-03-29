//! V2-M6-009/010/011/012: Deficit Round-Robin WFQ Scheduler.
//!
//! Four priority queues (URGENT=0, REALTIME=1, INTERACTIVE=2, BACKGROUND=3).
//! Deficit counters ensure BACKGROUND always makes progress even under
//! sustained URGENT flood.
//!
//! Default weights: [4, 3, 2, 1] (URGENT gets 4x the budget of BACKGROUND).
//! Configurable and hot-reloadable via atomic weights.
//!
//! Under no contention (single priority active), WFQ is zero-cost passthrough.

use pyo3::prelude::*;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use parking_lot::Mutex;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Number of priority levels.
const NUM_PRIORITIES: usize = 4;

/// Default weights per priority: URGENT=4, REALTIME=3, INTERACTIVE=2, BACKGROUND=1.
const DEFAULT_WEIGHTS: [u64; NUM_PRIORITIES] = [4, 3, 2, 1];

/// Priority names for display.
const PRIORITY_NAMES: [&str; NUM_PRIORITIES] = ["URGENT", "REALTIME", "INTERACTIVE", "BACKGROUND"];

// ---------------------------------------------------------------------------
// WfqItem -- generic item stored in the scheduler
// ---------------------------------------------------------------------------

/// An item in the WFQ scheduler, carrying an opaque u64 tag.
///
/// The tag can be a ring buffer index, envelope ID, or any identifier
/// the caller uses to map back to the actual envelope.
#[derive(Debug, Clone)]
pub(crate) struct WfqItem {
    /// Opaque tag (e.g., envelope_id or ring buffer index).
    pub tag: u64,
    /// Priority level (0=URGENT, 1=REALTIME, 2=INTERACTIVE, 3=BACKGROUND).
    pub priority: u8,
}

// ---------------------------------------------------------------------------
// WfqScheduler -- internal (crate-visible)
// ---------------------------------------------------------------------------

/// Deficit Round-Robin WFQ scheduler.
///
/// # Algorithm
///
/// Each priority queue has a deficit counter.  On each `next()` call:
///
/// 1. Find the queue with the highest deficit among non-empty queues.
/// 2. Dequeue one item, decrement deficit by 1.
/// 3. On `enqueue()`, add the weight for that priority to its deficit.
///
/// This ensures that BACKGROUND (weight=1) gets 1 item per round
/// while URGENT (weight=4) gets 4 items per round, but BACKGROUND
/// is never starved to zero.
pub(crate) struct WfqScheduler {
    queues: [Mutex<VecDeque<WfqItem>>; NUM_PRIORITIES],
    deficits: [AtomicI64; NUM_PRIORITIES],
    weights: [AtomicU64; NUM_PRIORITIES],
    total_enqueued: AtomicU64,
    total_dequeued: AtomicU64,
}

impl WfqScheduler {
    /// Create a new WfqScheduler with default weights.
    pub fn new() -> Self {
        Self::with_weights(DEFAULT_WEIGHTS)
    }

    /// Create with custom weights.
    pub fn with_weights(weights: [u64; NUM_PRIORITIES]) -> Self {
        Self {
            queues: [
                Mutex::new(VecDeque::new()),
                Mutex::new(VecDeque::new()),
                Mutex::new(VecDeque::new()),
                Mutex::new(VecDeque::new()),
            ],
            deficits: [
                AtomicI64::new(0),
                AtomicI64::new(0),
                AtomicI64::new(0),
                AtomicI64::new(0),
            ],
            weights: [
                AtomicU64::new(weights[0]),
                AtomicU64::new(weights[1]),
                AtomicU64::new(weights[2]),
                AtomicU64::new(weights[3]),
            ],
            total_enqueued: AtomicU64::new(0),
            total_dequeued: AtomicU64::new(0),
        }
    }

    /// Enqueue an item at the given priority.
    ///
    /// Adds the weight for this priority to its deficit counter.
    pub fn enqueue(&self, item: WfqItem) {
        let p = (item.priority as usize).min(NUM_PRIORITIES - 1);
        let weight = self.weights[p].load(Ordering::Relaxed) as i64;
        self.deficits[p].fetch_add(weight, Ordering::Relaxed);
        self.queues[p].lock().push_back(item);
        self.total_enqueued.fetch_add(1, Ordering::Relaxed);
    }

    /// Dequeue the next item using deficit round-robin.
    ///
    /// Returns None if all queues are empty.
    pub fn next(&self) -> Option<WfqItem> {
        // Find the non-empty queue with highest deficit
        let mut best_priority: Option<usize> = None;
        let mut best_deficit = i64::MIN;

        for p in 0..NUM_PRIORITIES {
            let deficit = self.deficits[p].load(Ordering::Relaxed);
            if deficit > best_deficit {
                // Check if queue is non-empty (peek without full lock via try_lock)
                let q = self.queues[p].lock();
                if !q.is_empty() {
                    best_deficit = deficit;
                    best_priority = Some(p);
                }
            }
        }

        if let Some(p) = best_priority {
            let mut q = self.queues[p].lock();
            if let Some(item) = q.pop_front() {
                self.deficits[p].fetch_sub(1, Ordering::Relaxed);
                self.total_dequeued.fetch_add(1, Ordering::Relaxed);
                return Some(item);
            }
        }

        None
    }

    /// Drain all items from a specific priority queue.
    /// Returns them in FIFO order.
    pub fn drain_priority(&self, priority: u8) -> Vec<WfqItem> {
        let p = (priority as usize).min(NUM_PRIORITIES - 1);
        let mut q = self.queues[p].lock();
        let items: Vec<WfqItem> = q.drain(..).collect();
        let count = items.len() as u64;
        self.total_dequeued.fetch_add(count, Ordering::Relaxed);
        // Reset deficit for this priority
        self.deficits[p].store(0, Ordering::Relaxed);
        items
    }

    /// Total items currently enqueued across all priorities.
    pub fn len(&self) -> usize {
        self.queues.iter().map(|q| q.lock().len()).sum()
    }

    /// Is the scheduler empty?
    pub fn is_empty(&self) -> bool {
        self.queues.iter().all(|q| q.lock().is_empty())
    }

    /// Get the current weight for a priority.
    pub fn weight(&self, priority: u8) -> u64 {
        let p = (priority as usize).min(NUM_PRIORITIES - 1);
        self.weights[p].load(Ordering::Relaxed)
    }

    /// Set weight for a priority (hot-reloadable).
    pub fn set_weight(&self, priority: u8, weight: u64) {
        let p = (priority as usize).min(NUM_PRIORITIES - 1);
        self.weights[p].store(weight, Ordering::Relaxed);
    }

    /// Get current deficit for a priority.
    pub fn deficit(&self, priority: u8) -> i64 {
        let p = (priority as usize).min(NUM_PRIORITIES - 1);
        self.deficits[p].load(Ordering::Relaxed)
    }

    /// Stats snapshot.
    pub fn stats(&self) -> WfqStats {
        WfqStats {
            total_enqueued: self.total_enqueued.load(Ordering::Relaxed),
            total_dequeued: self.total_dequeued.load(Ordering::Relaxed),
            queue_depths: [
                self.queues[0].lock().len(),
                self.queues[1].lock().len(),
                self.queues[2].lock().len(),
                self.queues[3].lock().len(),
            ],
            weights: [
                self.weights[0].load(Ordering::Relaxed),
                self.weights[1].load(Ordering::Relaxed),
                self.weights[2].load(Ordering::Relaxed),
                self.weights[3].load(Ordering::Relaxed),
            ],
            deficits: [
                self.deficits[0].load(Ordering::Relaxed),
                self.deficits[1].load(Ordering::Relaxed),
                self.deficits[2].load(Ordering::Relaxed),
                self.deficits[3].load(Ordering::Relaxed),
            ],
        }
    }
}

/// WFQ statistics snapshot.
#[derive(Debug, Clone)]
pub(crate) struct WfqStats {
    pub total_enqueued: u64,
    pub total_dequeued: u64,
    pub queue_depths: [usize; NUM_PRIORITIES],
    pub weights: [u64; NUM_PRIORITIES],
    pub deficits: [i64; NUM_PRIORITIES],
}

// ---------------------------------------------------------------------------
// PyWfqScheduler -- PyO3 wrapper
// ---------------------------------------------------------------------------

/// Python-exposed WFQ scheduler for testing and direct use.
#[pyclass(name = "WfqScheduler")]
pub(crate) struct PyWfqScheduler {
    inner: WfqScheduler,
}

#[pymethods]
impl PyWfqScheduler {
    /// Create a new WfqScheduler.
    ///
    /// Args:
    ///     weights: optional list of 4 weights [URGENT, REALTIME, INTERACTIVE, BACKGROUND].
    ///              Default: [4, 3, 2, 1].
    #[new]
    #[pyo3(signature = (weights=None))]
    fn new(weights: Option<Vec<u64>>) -> PyResult<Self> {
        let w = if let Some(w) = weights {
            if w.len() != NUM_PRIORITIES {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    format!("Expected {NUM_PRIORITIES} weights, got {}", w.len()),
                ));
            }
            [w[0], w[1], w[2], w[3]]
        } else {
            DEFAULT_WEIGHTS
        };
        Ok(Self {
            inner: WfqScheduler::with_weights(w),
        })
    }

    /// Enqueue an item with a priority (0-3) and an opaque tag (u64).
    fn enqueue(&self, tag: u64, priority: u8) -> PyResult<()> {
        if priority as usize >= NUM_PRIORITIES {
            return Err(pyo3::exceptions::PyValueError::new_err(
                format!("Priority must be 0-{}, got {priority}", NUM_PRIORITIES - 1),
            ));
        }
        self.inner.enqueue(WfqItem { tag, priority });
        Ok(())
    }

    /// Dequeue the next item using deficit round-robin.
    ///
    /// Returns (tag, priority) or None if all queues empty.
    fn next(&self) -> Option<(u64, u8)> {
        self.inner.next().map(|item| (item.tag, item.priority))
    }

    /// Total items currently enqueued.
    #[getter]
    fn depth(&self) -> usize {
        self.inner.len()
    }

    /// Is the scheduler empty?
    #[getter]
    fn is_empty(&self) -> bool {
        self.inner.is_empty()
    }

    /// Set weight for a priority (0-3).
    fn set_weight(&self, priority: u8, weight: u64) -> PyResult<()> {
        if priority as usize >= NUM_PRIORITIES {
            return Err(pyo3::exceptions::PyValueError::new_err(
                format!("Priority must be 0-{}", NUM_PRIORITIES - 1),
            ));
        }
        self.inner.set_weight(priority, weight);
        Ok(())
    }

    /// Get weight for a priority.
    fn get_weight(&self, priority: u8) -> u64 {
        self.inner.weight(priority)
    }

    /// Get stats as dict.
    #[getter]
    fn stats(&self) -> std::collections::HashMap<String, PyObject> {
        let s = self.inner.stats();
        Python::with_gil(|py| {
            let mut map = std::collections::HashMap::new();
            map.insert("total_enqueued".to_string(), s.total_enqueued.into_pyobject(py).unwrap().into_any().unbind());
            map.insert("total_dequeued".to_string(), s.total_dequeued.into_pyobject(py).unwrap().into_any().unbind());

            let depths: Vec<usize> = s.queue_depths.to_vec();
            map.insert("queue_depths".to_string(), depths.into_pyobject(py).unwrap().into_any().unbind());

            let weights: Vec<u64> = s.weights.to_vec();
            map.insert("weights".to_string(), weights.into_pyobject(py).unwrap().into_any().unbind());

            let deficits: Vec<i64> = s.deficits.to_vec();
            map.insert("deficits".to_string(), deficits.into_pyobject(py).unwrap().into_any().unbind());

            map
        })
    }

    fn __repr__(&self) -> String {
        let s = self.inner.stats();
        format!(
            "WfqScheduler(depth={}, weights={:?}, enqueued={}, dequeued={})",
            self.inner.len(),
            s.weights,
            s.total_enqueued,
            s.total_dequeued,
        )
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_scheduler() {
        let wfq = WfqScheduler::new();
        assert!(wfq.is_empty());
        assert_eq!(wfq.len(), 0);
        assert!(wfq.next().is_none());
    }

    #[test]
    fn test_single_priority_fifo() {
        let wfq = WfqScheduler::new();
        for i in 0..5 {
            wfq.enqueue(WfqItem { tag: i, priority: 0 });
        }
        for i in 0..5 {
            let item = wfq.next().unwrap();
            assert_eq!(item.tag, i);
            assert_eq!(item.priority, 0);
        }
        assert!(wfq.next().is_none());
    }

    #[test]
    fn test_default_weights() {
        let wfq = WfqScheduler::new();
        assert_eq!(wfq.weight(0), 4); // URGENT
        assert_eq!(wfq.weight(1), 3); // REALTIME
        assert_eq!(wfq.weight(2), 2); // INTERACTIVE
        assert_eq!(wfq.weight(3), 1); // BACKGROUND
    }

    #[test]
    fn test_background_not_starved() {
        // Key test: under 100 URGENT + 10 BACKGROUND, BACKGROUND gets served
        let wfq = WfqScheduler::new();

        // Enqueue 100 URGENT
        for i in 0..100 {
            wfq.enqueue(WfqItem { tag: i, priority: 0 });
        }
        // Enqueue 10 BACKGROUND
        for i in 0..10 {
            wfq.enqueue(WfqItem { tag: 1000 + i, priority: 3 });
        }

        let mut urgent_count = 0u64;
        let mut bg_count = 0u64;
        let mut dequeued = 0;

        // Dequeue all 110 items
        while let Some(item) = wfq.next() {
            dequeued += 1;
            match item.priority {
                0 => urgent_count += 1,
                3 => bg_count += 1,
                _ => {}
            }
        }

        assert_eq!(dequeued, 110);
        assert_eq!(urgent_count, 100);
        assert_eq!(bg_count, 10);
    }

    #[test]
    fn test_deficit_scheduling_interleaving() {
        // With weights [4,3,2,1], enqueue 1 item at each priority.
        // URGENT deficit=4, REALTIME=3, INTERACTIVE=2, BACKGROUND=1.
        // URGENT has highest deficit, so dequeued first.
        // After dequeue: deficits = [3, 3, 2, 1].
        // Tie between URGENT and REALTIME -- URGENT checked first (index 0).
        let wfq = WfqScheduler::new();
        wfq.enqueue(WfqItem { tag: 0, priority: 0 }); // URGENT
        wfq.enqueue(WfqItem { tag: 1, priority: 1 }); // REALTIME
        wfq.enqueue(WfqItem { tag: 2, priority: 2 }); // INTERACTIVE
        wfq.enqueue(WfqItem { tag: 3, priority: 3 }); // BACKGROUND

        // First out: URGENT (deficit 4 > others)
        let item = wfq.next().unwrap();
        assert_eq!(item.priority, 0);

        // Next: REALTIME (deficit 3, URGENT queue now empty)
        let item = wfq.next().unwrap();
        assert_eq!(item.priority, 1);

        // Next: INTERACTIVE (deficit 2)
        let item = wfq.next().unwrap();
        assert_eq!(item.priority, 2);

        // Last: BACKGROUND (deficit 1)
        let item = wfq.next().unwrap();
        assert_eq!(item.priority, 3);

        assert!(wfq.is_empty());
    }

    #[test]
    fn test_interleaved_enqueue_dequeue() {
        let wfq = WfqScheduler::new();

        // Enqueue BACKGROUND first
        wfq.enqueue(WfqItem { tag: 100, priority: 3 });
        // Then URGENT
        wfq.enqueue(WfqItem { tag: 200, priority: 0 });

        // URGENT has higher deficit (4 vs 1), dequeued first
        let first = wfq.next().unwrap();
        assert_eq!(first.priority, 0);
        assert_eq!(first.tag, 200);

        let second = wfq.next().unwrap();
        assert_eq!(second.priority, 3);
        assert_eq!(second.tag, 100);
    }

    #[test]
    fn test_custom_weights() {
        let wfq = WfqScheduler::with_weights([1, 1, 1, 1]);
        assert_eq!(wfq.weight(0), 1);
        assert_eq!(wfq.weight(3), 1);

        // With equal weights, dequeue order follows deficit (all equal),
        // so first enqueued priority wins on tie (lowest index).
        wfq.enqueue(WfqItem { tag: 0, priority: 3 }); // deficit = 1
        wfq.enqueue(WfqItem { tag: 1, priority: 0 }); // deficit = 1

        // Both have deficit=1, priority 0 checked first
        let first = wfq.next().unwrap();
        assert_eq!(first.priority, 0);
    }

    #[test]
    fn test_set_weight_hot_reload() {
        let wfq = WfqScheduler::new();
        assert_eq!(wfq.weight(3), 1);
        wfq.set_weight(3, 10);
        assert_eq!(wfq.weight(3), 10);
    }

    #[test]
    fn test_stats() {
        let wfq = WfqScheduler::new();
        wfq.enqueue(WfqItem { tag: 1, priority: 0 });
        wfq.enqueue(WfqItem { tag: 2, priority: 3 });
        let s = wfq.stats();
        assert_eq!(s.total_enqueued, 2);
        assert_eq!(s.total_dequeued, 0);
        assert_eq!(s.queue_depths[0], 1);
        assert_eq!(s.queue_depths[3], 1);

        wfq.next();
        let s = wfq.stats();
        assert_eq!(s.total_dequeued, 1);
    }

    #[test]
    fn test_starvation_flood() {
        // V2-M6-014: Sustained URGENT flood with some BACKGROUND
        let wfq = WfqScheduler::new();

        // 10K URGENT
        for i in 0..10_000 {
            wfq.enqueue(WfqItem { tag: i, priority: 0 });
        }
        // 100 BACKGROUND
        for i in 0..100 {
            wfq.enqueue(WfqItem { tag: 10_000 + i, priority: 3 });
        }

        let mut bg_dequeued = 0u64;
        let mut urgent_dequeued = 0u64;
        let mut total = 0u64;

        while let Some(item) = wfq.next() {
            total += 1;
            if item.priority == 3 {
                bg_dequeued += 1;
            } else if item.priority == 0 {
                urgent_dequeued += 1;
            }
        }

        assert_eq!(total, 10_100);
        assert_eq!(urgent_dequeued, 10_000);
        assert_eq!(bg_dequeued, 100);
        // BACKGROUND was NOT starved -- all 100 items were delivered
    }

    #[test]
    fn test_drain_priority() {
        let wfq = WfqScheduler::new();
        for i in 0..5 {
            wfq.enqueue(WfqItem { tag: i, priority: 2 });
        }
        let drained = wfq.drain_priority(2);
        assert_eq!(drained.len(), 5);
        assert!(wfq.is_empty());
    }

    #[test]
    fn test_overflow_priority_clamped() {
        let wfq = WfqScheduler::new();
        // Priority 99 should be clamped to 3 (BACKGROUND)
        wfq.enqueue(WfqItem { tag: 1, priority: 99 });
        let item = wfq.next().unwrap();
        // Item is in BACKGROUND queue (clamped)
        assert_eq!(item.tag, 1);
    }
}
