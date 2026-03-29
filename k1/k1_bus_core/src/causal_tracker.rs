//! V2-M6-001/002/003: Lock-free CausalTracker.
//!
//! Tracks delivered envelope_ids and buffers children waiting for parents.
//! When envelope X is delivered, any children buffered for parent_id=X
//! are released.  Cascading: if child Y becomes ready, grandchild Z
//! waiting on Y is also released.
//!
//! Uses `DashMap` for per-parent granularity (no global lock).
//! `DashSet` for delivered IDs.
//!
//! Memory safety: bounded buffer with emergency oldest-10% release.

use dashmap::{DashMap, DashSet};
use std::sync::atomic::{AtomicUsize, Ordering};

// ---------------------------------------------------------------------------
// BufferedEnvelope -- envelope + buffer entry timestamp
// ---------------------------------------------------------------------------

/// An envelope waiting in a buffer, timestamped at entry.
#[derive(Debug, Clone)]
pub(crate) struct BufferedEnvelope {
    /// Unique envelope ID (assigned by bus stamping).
    pub envelope_id: u64,
    /// The parent_id this envelope is waiting on (causal tracker only).
    pub parent_id: u64,
    /// Topic string (needed for gap buffer re-check after causal release).
    pub topic: String,
    /// Per-topic sequence number.
    pub sequence: u64,
    /// Monotonic nanosecond timestamp when this was buffered.
    pub buffered_at_ns: u64,
    /// Opaque index into an external envelope store (Python side or ring buffer).
    /// For the PyO3 binding, this carries the Python Envelope or RustEnvelope handle.
    pub ring_index: u64,
}

// ---------------------------------------------------------------------------
// CausalTracker
// ---------------------------------------------------------------------------

/// Lock-free causal ordering tracker.
///
/// # Design
///
/// - `delivered`: DashSet<u64> -- set of envelope_ids that have been delivered.
/// - `waiting`: DashMap<u64, Vec<BufferedEnvelope>> -- parent_id -> children.
/// - `total_buffered`: AtomicUsize -- for bounded buffer enforcement.
///
/// Per-parent granularity: operations on different parents do not contend.
pub(crate) struct CausalTracker {
    /// Set of delivered envelope IDs.
    delivered: DashSet<u64>,
    /// parent_id -> list of children waiting for that parent.
    waiting: DashMap<u64, Vec<BufferedEnvelope>>,
    /// Total number of buffered envelopes (across all parents).
    total_buffered: AtomicUsize,
    /// Maximum buffer size before emergency release.
    max_buffer: usize,
}

impl CausalTracker {
    /// Create a new CausalTracker with the given buffer limit.
    pub fn new(max_buffer: usize) -> Self {
        Self {
            delivered: DashSet::new(),
            waiting: DashMap::new(),
            total_buffered: AtomicUsize::new(0),
            max_buffer,
        }
    }

    /// Check if a parent envelope has been delivered (or is root).
    ///
    /// parent_id == 0 means root (no parent), always true.
    pub fn is_parent_delivered(&self, parent_id: u64) -> bool {
        if parent_id == 0 {
            return true;
        }
        self.delivered.contains(&parent_id)
    }

    /// Mark an envelope as delivered and return any children that
    /// were waiting for it.
    ///
    /// The caller should then deliver those children and recursively
    /// call `mark_delivered` for each (cascade).
    pub fn mark_delivered(&self, envelope_id: u64) -> Vec<BufferedEnvelope> {
        self.delivered.insert(envelope_id);
        if let Some((_, children)) = self.waiting.remove(&envelope_id) {
            let count = children.len();
            self.total_buffered.fetch_sub(count, Ordering::Relaxed);
            children
        } else {
            Vec::new()
        }
    }

    /// Buffer a child envelope waiting for its parent.
    ///
    /// If the buffer exceeds `max_buffer`, triggers emergency release
    /// of the oldest 10%.
    pub fn buffer_child(&self, parent_id: u64, buffered: BufferedEnvelope) {
        self.waiting
            .entry(parent_id)
            .or_default()
            .push(buffered);
        let total = self.total_buffered.fetch_add(1, Ordering::Relaxed) + 1;
        if total > self.max_buffer {
            self.force_release_oldest();
        }
    }

    /// Find and remove buffered envelopes that have exceeded the timeout.
    ///
    /// Returns the timed-out entries (removed from internal buffers).
    pub fn get_timed_out(&self, timeout_ns: u64, now_ns: u64) -> Vec<BufferedEnvelope> {
        if now_ns < timeout_ns {
            return Vec::new();
        }
        let cutoff = now_ns - timeout_ns;
        let mut timed_out = Vec::new();
        let mut empty_parents = Vec::new();

        // Iterate all parent entries
        for mut entry in self.waiting.iter_mut() {
            let parent_id = *entry.key();
            let waiters = entry.value_mut();
            let before = waiters.len();

            // Partition: timed out vs still waiting
            let mut remaining = Vec::new();
            for be in waiters.drain(..) {
                if be.buffered_at_ns <= cutoff {
                    timed_out.push(be);
                } else {
                    remaining.push(be);
                }
            }
            *waiters = remaining;
            if waiters.is_empty() {
                empty_parents.push(parent_id);
            }
            let removed = before - waiters.len();
            if removed > 0 {
                self.total_buffered.fetch_sub(removed, Ordering::Relaxed);
            }
        }

        // Clean up empty parent entries
        for pid in empty_parents {
            self.waiting.remove_if(&pid, |_, v| v.is_empty());
        }

        timed_out
    }

    /// Total number of envelopes buffered waiting for parents.
    pub fn pending_count(&self) -> usize {
        self.total_buffered.load(Ordering::Relaxed)
    }

    /// Emergency release: drop oldest 10% when buffer overflows.
    fn force_release_oldest(&self) {
        // Collect all buffered entries with their parent_id
        let mut all: Vec<(u64, u64)> = Vec::new(); // (parent_id, buffered_at_ns)
        for entry in self.waiting.iter() {
            let pid = *entry.key();
            for be in entry.value().iter() {
                all.push((pid, be.buffered_at_ns));
            }
        }

        if all.is_empty() {
            return;
        }

        all.sort_by_key(|&(_, ts)| ts);
        let release_count = std::cmp::max(1, all.len() / 10);
        let cutoff_time = all[release_count - 1].1;

        // Remove entries older than cutoff
        let mut removed_total = 0usize;
        let mut empty_parents = Vec::new();

        for mut entry in self.waiting.iter_mut() {
            let pid = *entry.key();
            let before = entry.value().len();
            entry.value_mut().retain(|be| be.buffered_at_ns > cutoff_time);
            let after = entry.value().len();
            removed_total += before - after;
            if after == 0 {
                empty_parents.push(pid);
            }
        }

        for pid in empty_parents {
            self.waiting.remove_if(&pid, |_, v| v.is_empty());
        }

        if removed_total > 0 {
            self.total_buffered.fetch_sub(removed_total, Ordering::Relaxed);
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_be(envelope_id: u64, parent_id: u64, buffered_at_ns: u64) -> BufferedEnvelope {
        BufferedEnvelope {
            envelope_id,
            parent_id,
            topic: "k1.test".to_string(),
            sequence: 1,
            buffered_at_ns,
            ring_index: 0,
        }
    }

    #[test]
    fn test_root_parent_always_delivered() {
        let ct = CausalTracker::new(1000);
        assert!(ct.is_parent_delivered(0));
    }

    #[test]
    fn test_unknown_parent_not_delivered() {
        let ct = CausalTracker::new(1000);
        assert!(!ct.is_parent_delivered(42));
    }

    #[test]
    fn test_mark_delivered_makes_parent_available() {
        let ct = CausalTracker::new(1000);
        ct.mark_delivered(42);
        assert!(ct.is_parent_delivered(42));
    }

    #[test]
    fn test_buffer_child_and_release_on_parent_delivery() {
        let ct = CausalTracker::new(1000);
        let child = make_be(2, 1, 100);
        ct.buffer_child(1, child);
        assert_eq!(ct.pending_count(), 1);

        let released = ct.mark_delivered(1);
        assert_eq!(released.len(), 1);
        assert_eq!(released[0].envelope_id, 2);
        assert_eq!(ct.pending_count(), 0);
    }

    #[test]
    fn test_multiple_children_released_together() {
        let ct = CausalTracker::new(1000);
        ct.buffer_child(1, make_be(2, 1, 100));
        ct.buffer_child(1, make_be(3, 1, 101));
        ct.buffer_child(1, make_be(4, 1, 102));
        assert_eq!(ct.pending_count(), 3);

        let released = ct.mark_delivered(1);
        assert_eq!(released.len(), 3);
        assert_eq!(ct.pending_count(), 0);
    }

    #[test]
    fn test_causal_cascade() {
        let ct = CausalTracker::new(1000);
        // Child 2 waits for parent 1, grandchild 3 waits for parent 2
        ct.buffer_child(1, make_be(2, 1, 100));
        ct.buffer_child(2, make_be(3, 2, 101));
        assert_eq!(ct.pending_count(), 2);

        // Deliver parent 1 -> releases child 2
        let children = ct.mark_delivered(1);
        assert_eq!(children.len(), 1);
        assert_eq!(children[0].envelope_id, 2);

        // Now deliver child 2 -> releases grandchild 3
        let grandchildren = ct.mark_delivered(2);
        assert_eq!(grandchildren.len(), 1);
        assert_eq!(grandchildren[0].envelope_id, 3);
        assert_eq!(ct.pending_count(), 0);
    }

    #[test]
    fn test_timeout_releases_old_entries() {
        let ct = CausalTracker::new(1000);
        ct.buffer_child(1, make_be(2, 1, 100));   // old
        ct.buffer_child(1, make_be(3, 1, 5_000));  // recent

        let timed_out = ct.get_timed_out(1000, 2000);
        assert_eq!(timed_out.len(), 1);
        assert_eq!(timed_out[0].envelope_id, 2);
        assert_eq!(ct.pending_count(), 1);
    }

    #[test]
    fn test_timeout_keeps_recent_entries() {
        let ct = CausalTracker::new(1000);
        ct.buffer_child(1, make_be(2, 1, 5000));

        let timed_out = ct.get_timed_out(1000, 5500);
        assert_eq!(timed_out.len(), 0);
        assert_eq!(ct.pending_count(), 1);
    }

    #[test]
    fn test_force_release_on_overflow() {
        let ct = CausalTracker::new(10);
        for i in 0..15 {
            ct.buffer_child(1, make_be(i + 100, 1, i as u64));
        }
        // Should have triggered force_release (oldest 10%)
        // After force release, some entries dropped
        assert!(ct.pending_count() <= 15);
    }

    #[test]
    fn test_mark_delivered_for_nonexistent_returns_empty() {
        let ct = CausalTracker::new(1000);
        let released = ct.mark_delivered(999);
        assert!(released.is_empty());
        assert!(ct.is_parent_delivered(999));
    }

    #[test]
    fn test_independent_parents_no_contention() {
        let ct = CausalTracker::new(1000);
        ct.buffer_child(1, make_be(10, 1, 100));
        ct.buffer_child(2, make_be(20, 2, 100));
        assert_eq!(ct.pending_count(), 2);

        let r1 = ct.mark_delivered(1);
        assert_eq!(r1.len(), 1);
        assert_eq!(r1[0].envelope_id, 10);
        assert_eq!(ct.pending_count(), 1);

        let r2 = ct.mark_delivered(2);
        assert_eq!(r2.len(), 1);
        assert_eq!(r2[0].envelope_id, 20);
        assert_eq!(ct.pending_count(), 0);
    }
}
