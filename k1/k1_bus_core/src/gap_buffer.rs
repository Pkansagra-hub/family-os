//! V2-M6-004/005/006: Per-topic GapBuffer.
//!
//! Maintains expected next sequence per topic.  If an envelope arrives
//! with sequence > expected, it is buffered until the gap is filled.
//! When the missing sequence arrives, it and all consecutive buffered
//! successors are released in order.
//!
//! Uses `DashMap<String, TopicGapState>` for per-topic lock granularity.
//! Each `TopicGapState` uses a `BTreeMap<u64, BufferedEnvelope>` for
//! efficient range-based successor scanning.
//!
//! Per-topic buffer limit with emergency release.

use crate::causal_tracker::BufferedEnvelope;
use dashmap::DashMap;
use std::collections::BTreeMap;

// ---------------------------------------------------------------------------
// Per-topic gap state
// ---------------------------------------------------------------------------

/// State for a single topic's sequence gap tracking.
struct TopicGapState {
    /// Next expected sequence number (starts at 1).
    expected: u64,
    /// Buffered envelopes indexed by their sequence number.
    buffer: BTreeMap<u64, BufferedEnvelope>,
    /// Max entries before emergency release.
    max_buffer: usize,
}

impl TopicGapState {
    fn new(max_buffer: usize) -> Self {
        Self {
            expected: 1,
            buffer: BTreeMap::new(),
            max_buffer,
        }
    }

    /// Check if envelope is in-sequence or needs buffering.
    ///
    /// Returns (is_ready, released_successors).
    fn check_and_buffer(
        &mut self,
        envelope_id: u64,
        sequence: u64,
        topic: &str,
        parent_id: u64,
        buffered_at_ns: u64,
    ) -> (bool, Vec<BufferedEnvelope>) {
        if sequence == self.expected {
            // In-sequence: advance expected and release successors
            self.expected += 1;
            let released = self.release_successors();
            return (true, released);
        }

        if sequence < self.expected {
            // Duplicate or old: deliver anyway (idempotent)
            return (true, Vec::new());
        }

        // Gap detected: buffer
        self.buffer.insert(
            sequence,
            BufferedEnvelope {
                envelope_id,
                parent_id,
                topic: topic.to_string(),
                sequence,
                buffered_at_ns,
                ring_index: 0,
            },
        );

        // Safety: bound check
        if self.buffer.len() > self.max_buffer {
            self.force_release_oldest();
        }

        (false, Vec::new())
    }

    /// Release consecutive buffered envelopes starting from `expected`.
    fn release_successors(&mut self) -> Vec<BufferedEnvelope> {
        let mut released = Vec::new();
        while let Some(be) = self.buffer.remove(&self.expected) {
            released.push(be);
            self.expected += 1;
        }
        released
    }

    /// Find and remove timed-out entries.  Returns them in sequence order.
    fn get_timed_out(&mut self, timeout_ns: u64, now_ns: u64) -> Vec<BufferedEnvelope> {
        if now_ns < timeout_ns {
            return Vec::new();
        }
        let cutoff = now_ns - timeout_ns;
        let mut timed_out_seqs: Vec<u64> = Vec::new();

        for (&seq, be) in self.buffer.iter() {
            if be.buffered_at_ns <= cutoff {
                timed_out_seqs.push(seq);
            }
        }

        let mut released = Vec::new();
        for seq in &timed_out_seqs {
            if let Some(be) = self.buffer.remove(seq) {
                released.push(be);
            }
        }

        // Advance expected past the gap (past the highest released seq)
        if let Some(&max_seq) = timed_out_seqs.last() {
            if max_seq >= self.expected {
                self.expected = max_seq + 1;
                // Also release any consecutive successors
                let mut more = self.release_successors();
                released.append(&mut more);
            }
        }

        released
    }

    /// Emergency release: drop oldest 10%.
    fn force_release_oldest(&mut self) {
        let count = std::cmp::max(1, self.buffer.len() / 10);
        let seqs_to_remove: Vec<u64> = self.buffer.keys().take(count).copied().collect();
        for seq in &seqs_to_remove {
            self.buffer.remove(seq);
        }
        // Advance expected to the next remaining entry (if any)
        if let Some(&next_seq) = self.buffer.keys().next() {
            if next_seq > self.expected {
                self.expected = next_seq;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// GapBuffer -- public API
// ---------------------------------------------------------------------------

/// Per-topic sequence gap buffer.
///
/// Thread-safe via DashMap: per-topic shard locking, zero cross-topic contention.
pub(crate) struct GapBuffer {
    topics: DashMap<String, TopicGapState>,
    max_per_topic: usize,
}

impl GapBuffer {
    /// Create a new GapBuffer with the given per-topic limit.
    pub fn new(max_per_topic: usize) -> Self {
        Self {
            topics: DashMap::new(),
            max_per_topic,
        }
    }

    /// Check if an envelope is in-sequence or needs buffering.
    ///
    /// Returns (is_ready, released_successors).
    pub fn check_and_buffer(
        &self,
        topic: &str,
        envelope_id: u64,
        sequence: u64,
        parent_id: u64,
        now_ns: u64,
    ) -> (bool, Vec<BufferedEnvelope>) {
        let mut entry = self
            .topics
            .entry(topic.to_string())
            .or_insert_with(|| TopicGapState::new(self.max_per_topic));
        entry.check_and_buffer(envelope_id, sequence, topic, parent_id, now_ns)
    }

    /// Find and remove timed-out envelopes for a specific topic.
    pub fn get_timed_out(&self, topic: &str, timeout_ns: u64, now_ns: u64) -> Vec<BufferedEnvelope> {
        if let Some(mut entry) = self.topics.get_mut(topic) {
            let released = entry.get_timed_out(timeout_ns, now_ns);
            // Clean up empty state
            if entry.buffer.is_empty() && entry.expected == 1 {
                drop(entry);
                // Don't remove -- expected may be > 1 even with empty buffer
            }
            released
        } else {
            Vec::new()
        }
    }

    /// Find and remove timed-out envelopes across ALL topics.
    pub fn get_all_timed_out(&self, timeout_ns: u64, now_ns: u64) -> Vec<BufferedEnvelope> {
        let topics: Vec<String> = self.topics.iter().map(|e| e.key().clone()).collect();
        let mut result = Vec::new();
        for topic in topics {
            let mut released = self.get_timed_out(&topic, timeout_ns, now_ns);
            result.append(&mut released);
        }
        result
    }

    /// Total envelopes buffered across all topics.
    pub fn total_buffered(&self) -> usize {
        self.topics.iter().map(|e| e.value().buffer.len()).sum()
    }

    /// Number of envelopes buffered for a specific topic.
    pub fn pending_for_topic(&self, topic: &str) -> usize {
        self.topics
            .get(topic)
            .map(|e| e.value().buffer.len())
            .unwrap_or(0)
    }

    /// Next expected sequence for a topic (1 if never seen).
    pub fn expected_sequence(&self, topic: &str) -> u64 {
        self.topics
            .get(topic)
            .map(|e| e.value().expected)
            .unwrap_or(1)
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_first_envelope_seq_1_is_ready() {
        let gb = GapBuffer::new(1000);
        let (ready, released) = gb.check_and_buffer("k1.test", 1, 1, 0, 100);
        assert!(ready);
        assert!(released.is_empty());
    }

    #[test]
    fn test_sequential_envelopes_all_ready() {
        let gb = GapBuffer::new(1000);
        for seq in 1..=10 {
            let (ready, _) = gb.check_and_buffer("k1.test", seq, seq, 0, 100);
            assert!(ready, "seq {} should be ready", seq);
        }
        assert_eq!(gb.expected_sequence("k1.test"), 11);
    }

    #[test]
    fn test_gap_buffers_envelope() {
        let gb = GapBuffer::new(1000);
        // Deliver seq 1
        let (ready, _) = gb.check_and_buffer("k1.test", 1, 1, 0, 100);
        assert!(ready);

        // Gap: skip seq 2, deliver seq 3
        let (ready, released) = gb.check_and_buffer("k1.test", 3, 3, 0, 200);
        assert!(!ready);
        assert!(released.is_empty());
        assert_eq!(gb.pending_for_topic("k1.test"), 1);
    }

    #[test]
    fn test_gap_fill_releases_buffered() {
        let gb = GapBuffer::new(1000);
        // Deliver seq 1
        gb.check_and_buffer("k1.test", 1, 1, 0, 100);

        // Gap: deliver seq 3 (buffered)
        let (ready, _) = gb.check_and_buffer("k1.test", 3, 3, 0, 200);
        assert!(!ready);

        // Fill gap: deliver seq 2 -> releases seq 3
        let (ready, released) = gb.check_and_buffer("k1.test", 2, 2, 0, 300);
        assert!(ready);
        assert_eq!(released.len(), 1);
        assert_eq!(released[0].sequence, 3);
        assert_eq!(gb.pending_for_topic("k1.test"), 0);
        assert_eq!(gb.expected_sequence("k1.test"), 4);
    }

    #[test]
    fn test_multiple_gap_fill() {
        let gb = GapBuffer::new(1000);
        // Deliver 1
        gb.check_and_buffer("k1.test", 1, 1, 0, 100);
        // Buffer 3, 4, 5 (gap at 2)
        gb.check_and_buffer("k1.test", 3, 3, 0, 100);
        gb.check_and_buffer("k1.test", 4, 4, 0, 100);
        gb.check_and_buffer("k1.test", 5, 5, 0, 100);
        assert_eq!(gb.pending_for_topic("k1.test"), 3);

        // Fill gap at 2 -> releases 3, 4, 5
        let (ready, released) = gb.check_and_buffer("k1.test", 2, 2, 0, 100);
        assert!(ready);
        assert_eq!(released.len(), 3);
        let seqs: Vec<u64> = released.iter().map(|be| be.sequence).collect();
        assert_eq!(seqs, vec![3, 4, 5]);
        assert_eq!(gb.expected_sequence("k1.test"), 6);
    }

    #[test]
    fn test_duplicate_sequence_still_ready() {
        let gb = GapBuffer::new(1000);
        gb.check_and_buffer("k1.test", 1, 1, 0, 100);
        gb.check_and_buffer("k1.test", 2, 2, 0, 100);

        // Duplicate seq 1: still ready (idempotent)
        let (ready, released) = gb.check_and_buffer("k1.test", 1, 1, 0, 100);
        assert!(ready);
        assert!(released.is_empty());
    }

    #[test]
    fn test_per_topic_isolation() {
        let gb = GapBuffer::new(1000);
        gb.check_and_buffer("k1.a", 1, 1, 0, 100);
        gb.check_and_buffer("k1.b", 1, 1, 0, 100);

        // Gap on topic a, not on topic b
        let (ready_a, _) = gb.check_and_buffer("k1.a", 3, 3, 0, 100);
        let (ready_b, _) = gb.check_and_buffer("k1.b", 2, 2, 0, 100);
        assert!(!ready_a); // gap
        assert!(ready_b);  // in-sequence

        assert_eq!(gb.expected_sequence("k1.a"), 2);
        assert_eq!(gb.expected_sequence("k1.b"), 3);
    }

    #[test]
    fn test_timeout_releases_buffered() {
        let gb = GapBuffer::new(1000);
        gb.check_and_buffer("k1.test", 1, 1, 0, 100);
        // Buffer seq 3 at time 200
        gb.check_and_buffer("k1.test", 3, 3, 0, 200);
        assert_eq!(gb.pending_for_topic("k1.test"), 1);

        // Timeout at cutoff = 1000 - 500 = 500, entry at 200 <= 500
        let released = gb.get_timed_out("k1.test", 500, 1000);
        assert_eq!(released.len(), 1);
        assert_eq!(released[0].sequence, 3);
        assert_eq!(gb.pending_for_topic("k1.test"), 0);
    }

    #[test]
    fn test_timeout_advances_expected() {
        let gb = GapBuffer::new(1000);
        gb.check_and_buffer("k1.test", 1, 1, 0, 100);
        // Buffer seq 3 at time 200
        gb.check_and_buffer("k1.test", 3, 3, 0, 200);
        // Buffer seq 4 at time 200
        gb.check_and_buffer("k1.test", 4, 4, 0, 200);

        // Timeout both
        let released = gb.get_timed_out("k1.test", 500, 1000);
        assert_eq!(released.len(), 2);
        // Expected should advance past 4
        assert_eq!(gb.expected_sequence("k1.test"), 5);
    }

    #[test]
    fn test_total_buffered_across_topics() {
        let gb = GapBuffer::new(1000);
        gb.check_and_buffer("k1.a", 1, 1, 0, 100);
        gb.check_and_buffer("k1.b", 1, 1, 0, 100);
        // Buffer gaps
        gb.check_and_buffer("k1.a", 3, 3, 0, 100); // +1
        gb.check_and_buffer("k1.a", 4, 4, 0, 100); // +1
        gb.check_and_buffer("k1.b", 3, 3, 0, 100); // +1
        assert_eq!(gb.total_buffered(), 3);
    }

    #[test]
    fn test_expected_sequence_unseen_topic() {
        let gb = GapBuffer::new(1000);
        assert_eq!(gb.expected_sequence("k1.unknown"), 1);
    }

    #[test]
    fn test_get_all_timed_out() {
        let gb = GapBuffer::new(1000);
        gb.check_and_buffer("k1.a", 1, 1, 0, 100);
        gb.check_and_buffer("k1.b", 1, 1, 0, 100);
        // Buffer gaps in both topics
        gb.check_and_buffer("k1.a", 3, 3, 0, 200);
        gb.check_and_buffer("k1.b", 3, 3, 0, 200);

        let released = gb.get_all_timed_out(500, 1000);
        assert_eq!(released.len(), 2);
    }
}
