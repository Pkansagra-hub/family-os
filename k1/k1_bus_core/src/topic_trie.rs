//! Rust TopicTrie with subscription cache for O(1) repeat-topic matches.
//!
//! This is the Rust port of `k1.bus.impl.topic_trie.TopicTrie`. It provides
//! identical semantics:
//!   - Exact segment matching
//!   - `*` single-segment wildcard (matches exactly one segment)
//!   - `>` greedy wildcard (matches one or more trailing segments, must be last)
//!   - O(k) insert/remove (k = number of segments)
//!   - O(k * W) match (W = wildcard fan-out, typically 1-2)
//!
//! ## Subscription Cache
//!
//! A `DashMap<String, CacheEntry>` caches concrete-topic -> handler-IDs.
//! A global `generation: AtomicU64` is bumped on every `insert` or `remove`.
//! Cache entries are tagged with the generation at creation time and are
//! discarded when stale.  This gives O(1) cached matches for repeat topics.
//!
//! ## Thread Safety
//!
//! The trie uses `parking_lot::RwLock` for the node tree and `DashMap` for
//! the cache.  Multiple readers can match concurrently; writes are exclusive.
//!
//! ## Python Interop
//!
//! The `TopicTrie` is exposed as a `#[pyclass]` with `insert`, `match_topic`,
//! `remove`, `clear`, and `len` methods.  Handler objects are stored as
//! `Py<PyAny>` keyed by auto-incrementing `u64` IDs internally.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};

use dashmap::DashMap;
use parking_lot::RwLock;
use pyo3::prelude::*;
use pyo3::types::PyList;

// ─── Internal trie node ─────────────────────────────────────────────

/// Trie node mirroring the Python `_TrieNode`.
struct TrieNode {
    children: HashMap<String, TrieNode>,
    /// (handler_id, subscription_id) pairs.  Tombstoned entries have handler_id = 0.
    entries: Vec<(u64, String)>,
}

impl TrieNode {
    fn new() -> Self {
        Self {
            children: HashMap::new(),
            entries: Vec::new(),
        }
    }

    /// Collect non-tombstoned handler IDs from this node.
    fn live_handler_ids(&self) -> Vec<u64> {
        self.entries
            .iter()
            .filter(|(hid, _)| *hid != 0)
            .map(|(hid, _)| *hid)
            .collect()
    }

    /// Compact tombstoned entries if >50% are dead.
    fn maybe_compact(&mut self) {
        if self.entries.is_empty() {
            return;
        }
        let tombstones = self.entries.iter().filter(|(hid, _)| *hid == 0).count();
        if tombstones > self.entries.len() / 2 {
            self.entries.retain(|(hid, _)| *hid != 0);
        }
    }
}

// ─── Cache entry ────────────────────────────────────────────────────

struct CacheEntry {
    handler_ids: Vec<u64>,
    generation: u64,
}

// ─── TopicTrie (Rust-internal, not PyO3) ────────────────────────────

/// Internal trie logic, usable from Rust tests without Python.
pub(crate) struct TopicTrieInner {
    root: TrieNode,
    /// subscription_id -> (pattern_segments, handler_id)
    sub_index: HashMap<String, (Vec<String>, u64)>,
    pub(crate) size: usize,
    next_handler_id: u64,
}

impl TopicTrieInner {
    pub(crate) fn new() -> Self {
        Self {
            root: TrieNode::new(),
            sub_index: HashMap::new(),
            size: 0,
            next_handler_id: 1, // 0 is reserved for tombstone
        }
    }

    fn alloc_handler_id(&mut self) -> u64 {
        let id = self.next_handler_id;
        self.next_handler_id += 1;
        id
    }

    fn validate_pattern(pattern: &str) -> Result<Vec<String>, String> {
        if pattern.is_empty() {
            return Err("Topic pattern must not be empty".to_string());
        }
        let segments: Vec<String> = pattern.split('.').map(|s| s.to_string()).collect();
        for (i, seg) in segments.iter().enumerate() {
            if seg.is_empty() {
                return Err(format!(
                    "Topic pattern has empty segment at position {i}: {pattern:?}"
                ));
            }
            if seg == ">" && i != segments.len() - 1 {
                return Err(format!(
                    "Greedy wildcard '>' must be the last segment: {pattern:?}"
                ));
            }
        }
        Ok(segments)
    }

    pub(crate) fn insert(
        &mut self,
        pattern: &str,
        subscription_id: &str,
    ) -> Result<u64, String> {
        let segments = Self::validate_pattern(pattern)?;
        let handler_id = self.alloc_handler_id();

        let mut node = &mut self.root;
        for seg in &segments {
            node = node.children.entry(seg.clone()).or_insert_with(TrieNode::new);
        }
        node.entries.push((handler_id, subscription_id.to_string()));
        self.sub_index.insert(
            subscription_id.to_string(),
            (segments, handler_id),
        );
        self.size += 1;
        Ok(handler_id)
    }

    /// Remove a subscription. Returns the handler_id if found, None otherwise.
    pub(crate) fn remove(&mut self, subscription_id: &str) -> Option<u64> {
        let entry = self.sub_index.remove(subscription_id);
        if entry.is_none() {
            return None;
        }
        let (segments, handler_id) = entry.unwrap();

        // Walk down the trie to find the node
        let mut node = &mut self.root;
        for seg in &segments {
            match node.children.get_mut(seg.as_str()) {
                Some(child) => node = child,
                None => return None, // trie structure lost -- shouldn't happen
            }
        }

        // Tombstone: set handler_id to 0
        for entry in &mut node.entries {
            if entry.0 == handler_id {
                entry.0 = 0;
                entry.1.clear();
                break;
            }
        }
        node.maybe_compact();
        self.size -= 1;
        Some(handler_id)
    }

    pub(crate) fn match_topic(&self, topic: &str) -> Vec<u64> {
        if topic.is_empty() {
            return vec![];
        }
        let segments: Vec<&str> = topic.split('.').collect();
        let mut result = Vec::new();
        Self::match_recursive(&self.root, &segments, 0, &mut result);
        result
    }

    fn match_recursive(
        node: &TrieNode,
        segments: &[&str],
        depth: usize,
        result: &mut Vec<u64>,
    ) {
        if depth == segments.len() {
            // Reached end of topic -- collect handlers at this node
            for (hid, _) in &node.entries {
                if *hid != 0 {
                    result.push(*hid);
                }
            }
            return;
        }

        let seg = segments[depth];

        // 1. Exact match
        if let Some(child) = node.children.get(seg) {
            Self::match_recursive(child, segments, depth + 1, result);
        }

        // 2. Single wildcard "*" matches exactly one segment
        if let Some(wild_child) = node.children.get("*") {
            Self::match_recursive(wild_child, segments, depth + 1, result);
        }

        // 3. Greedy wildcard ">" matches one or more remaining segments
        if let Some(greedy_child) = node.children.get(">") {
            for (hid, _) in &greedy_child.entries {
                if *hid != 0 {
                    result.push(*hid);
                }
            }
        }
    }

    pub(crate) fn clear(&mut self) {
        self.root = TrieNode::new();
        self.sub_index.clear();
        self.size = 0;
        // Don't reset next_handler_id to avoid stale cache hits
    }
}

// ─── PyO3 wrapper ───────────────────────────────────────────────────

/// Concurrent TopicTrie exposed to Python.
///
/// Handlers are stored as `Py<PyAny>` Python objects keyed by internal u64 IDs.
/// The trie itself only works with u64 IDs -- Python objects are resolved at
/// match time by looking up the ID map.
#[pyclass(name = "TopicTrie")]
pub struct PyTopicTrie {
    inner: RwLock<TopicTrieInner>,
    /// handler_id -> Python handler object
    handlers: RwLock<HashMap<u64, Py<PyAny>>>,
    /// Subscription cache: concrete topic -> cached handler IDs
    cache: DashMap<String, CacheEntry>,
    /// Incremented on every insert/remove.  Cache entries with older generation are stale.
    generation: AtomicU64,
}

#[pymethods]
impl PyTopicTrie {
    #[new]
    fn new() -> Self {
        Self {
            inner: RwLock::new(TopicTrieInner::new()),
            handlers: RwLock::new(HashMap::new()),
            cache: DashMap::new(),
            generation: AtomicU64::new(0),
        }
    }

    /// Insert a handler for a topic pattern.
    ///
    /// Args:
    ///     pattern: Dot-separated topic pattern (e.g. "k1.agent.*.delta.v1")
    ///     handler: Python callable to invoke on match
    ///     subscription_id: Unique subscription identifier for removal
    ///
    /// Raises:
    ///     ValueError: If pattern is empty, has empty segments, or ">" is not last.
    fn insert(
        &self,
        pattern: &str,
        handler: Py<PyAny>,
        subscription_id: &str,
    ) -> PyResult<()> {
        let handler_id = {
            let mut inner = self.inner.write();
            inner
                .insert(pattern, subscription_id)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?
        };
        self.handlers.write().insert(handler_id, handler);
        // Bump generation to invalidate cache
        self.generation.fetch_add(1, Ordering::Release);
        Ok(())
    }

    /// Find all handlers matching a concrete topic.
    ///
    /// Returns a list of Python handler objects.  Uses the subscription cache
    /// for O(1) repeat-topic lookups.
    ///
    /// This is the primary match method, also aliased as `match()` for
    /// compatibility with the Python TopicTrie API.
    fn match_topic(&self, py: Python<'_>, topic: &str) -> PyResult<Py<PyList>> {
        self._match_impl(py, topic)
    }

    /// Alias for `match_topic()` -- compatible with Python TopicTrie.match().
    #[pyo3(name = "match")]
    fn match_py(&self, py: Python<'_>, topic: &str) -> PyResult<Py<PyList>> {
        self._match_impl(py, topic)
    }

    /// Remove a subscription by ID.
    ///
    /// Returns True if found and removed, False if not found.
    fn remove(&self, subscription_id: &str) -> bool {
        let handler_id_opt = {
            let mut inner = self.inner.write();
            inner.remove(subscription_id)
        };
        if let Some(handler_id) = handler_id_opt {
            self.handlers.write().remove(&handler_id);
            self.generation.fetch_add(1, Ordering::Release);
            true
        } else {
            false
        }
    }

    /// Remove all subscriptions.
    fn clear(&self) {
        self.inner.write().clear();
        self.handlers.write().clear();
        self.cache.clear();
        self.generation.fetch_add(1, Ordering::Release);
    }

    /// Return the number of active subscriptions.
    #[getter]
    fn size(&self) -> usize {
        self.inner.read().size
    }

    fn __len__(&self) -> usize {
        self.inner.read().size
    }

    fn __repr__(&self) -> String {
        let size = self.inner.read().size;
        format!("TopicTrie(subscriptions={size})")
    }

    /// Return current cache generation (for testing/debugging).
    #[getter]
    fn cache_generation(&self) -> u64 {
        self.generation.load(Ordering::Acquire)
    }

    /// Return number of cached topic entries (for testing/debugging).
    #[getter]
    fn cache_size(&self) -> usize {
        self.cache.len()
    }
}

// ─── Private impl (non-PyO3) ────────────────────────────────────────

impl PyTopicTrie {
    /// Shared match implementation used by both `match_topic` and `match` (Python alias).
    fn _match_impl(&self, py: Python<'_>, topic: &str) -> PyResult<Py<PyList>> {
        let current_gen = self.generation.load(Ordering::Acquire);

        // Check cache first
        if let Some(entry) = self.cache.get(topic) {
            if entry.generation == current_gen {
                // Cache hit -- resolve handler IDs to Python objects
                let handlers_lock = self.handlers.read();
                let list = PyList::empty(py);
                for hid in &entry.handler_ids {
                    if let Some(h) = handlers_lock.get(hid) {
                        list.append(h)?;
                    }
                }
                return Ok(list.into());
            }
        }

        // Cache miss or stale -- perform trie match
        let handler_ids = {
            let inner = self.inner.read();
            inner.match_topic(topic)
        };

        // Build Python list and populate cache
        let handlers_lock = self.handlers.read();
        let list = PyList::empty(py);
        for hid in &handler_ids {
            if let Some(h) = handlers_lock.get(hid) {
                list.append(h)?;
            }
        }

        // Store in cache
        self.cache.insert(
            topic.to_string(),
            CacheEntry {
                handler_ids,
                generation: current_gen,
            },
        );

        Ok(list.into())
    }
}

// ─── Rust-native tests (no Python) ─────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exact_match() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.capability.completed.v1", "sub-1").unwrap();
        let result = trie.match_topic("k1.capability.completed.v1");
        assert_eq!(result, vec![h1]);
        assert!(trie.match_topic("k1.capability.failed.v1").is_empty());
    }

    #[test]
    fn test_single_wildcard() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.agent.*.delta.v1", "sub-1").unwrap();
        assert_eq!(trie.match_topic("k1.agent.abc.delta.v1"), vec![h1]);
        assert_eq!(trie.match_topic("k1.agent.xyz.delta.v1"), vec![h1]);
        // * doesn't match multiple segments
        assert!(trie.match_topic("k1.agent.a.b.delta.v1").is_empty());
    }

    #[test]
    fn test_greedy_wildcard() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.agent.>", "sub-1").unwrap();
        assert_eq!(trie.match_topic("k1.agent.abc"), vec![h1]);
        assert_eq!(trie.match_topic("k1.agent.abc.delta.v1"), vec![h1]);
        // > requires at least one more segment
        assert!(trie.match_topic("k1.agent").is_empty());
    }

    #[test]
    fn test_multiple_handlers_same_pattern() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.test", "sub-1").unwrap();
        let h2 = trie.insert("k1.test", "sub-2").unwrap();
        let result = trie.match_topic("k1.test");
        assert_eq!(result, vec![h1, h2]);
    }

    #[test]
    fn test_overlapping_exact_wild_greedy() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.a.b.c", "sub-1").unwrap();
        let h2 = trie.insert("k1.a.*.c", "sub-2").unwrap();
        let h3 = trie.insert("k1.a.>", "sub-3").unwrap();
        let result = trie.match_topic("k1.a.b.c");
        assert_eq!(result.len(), 3);
        assert!(result.contains(&h1));
        assert!(result.contains(&h2));
        assert!(result.contains(&h3));
    }

    #[test]
    fn test_remove() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.test", "sub-1").unwrap();
        assert_eq!(trie.match_topic("k1.test"), vec![h1]);
        assert!(trie.remove("sub-1").is_some());
        assert!(trie.match_topic("k1.test").is_empty());
        assert_eq!(trie.size, 0);
    }

    #[test]
    fn test_remove_unknown() {
        let mut trie = TopicTrieInner::new();
        assert!(trie.remove("nonexistent").is_none());
    }

    #[test]
    fn test_remove_one_of_many() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.test", "sub-1").unwrap();
        let _h2 = trie.insert("k1.test", "sub-2").unwrap();
        let h3 = trie.insert("k1.test", "sub-3").unwrap();
        trie.remove("sub-2");
        let result = trie.match_topic("k1.test");
        assert_eq!(result.len(), 2);
        assert!(result.contains(&h1));
        assert!(result.contains(&h3));
    }

    #[test]
    fn test_validation_empty() {
        let mut trie = TopicTrieInner::new();
        assert!(trie.insert("", "sub-1").is_err());
    }

    #[test]
    fn test_validation_empty_segment() {
        let mut trie = TopicTrieInner::new();
        assert!(trie.insert("k1..test", "sub-1").is_err());
    }

    #[test]
    fn test_validation_greedy_not_last() {
        let mut trie = TopicTrieInner::new();
        assert!(trie.insert("k1.>.test", "sub-1").is_err());
    }

    #[test]
    fn test_clear() {
        let mut trie = TopicTrieInner::new();
        trie.insert("a", "s1").unwrap();
        trie.insert("b", "s2").unwrap();
        trie.clear();
        assert_eq!(trie.size, 0);
        assert!(trie.match_topic("a").is_empty());
    }

    #[test]
    fn test_empty_topic_no_match() {
        let mut trie = TopicTrieInner::new();
        trie.insert("k1.test", "sub-1").unwrap();
        assert!(trie.match_topic("").is_empty());
    }

    #[test]
    fn test_greedy_at_root() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert(">", "sub-1").unwrap();
        assert_eq!(trie.match_topic("anything"), vec![h1]);
        assert_eq!(trie.match_topic("k1.deep.topic"), vec![h1]);
    }

    #[test]
    fn test_wildcard_only() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("*", "sub-1").unwrap();
        assert_eq!(trie.match_topic("anything"), vec![h1]);
        // * matches exactly one segment
        assert!(trie.match_topic("two.segments").is_empty());
    }

    #[test]
    fn test_multiple_wildcards() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.*.*.v1", "sub-1").unwrap();
        assert_eq!(trie.match_topic("k1.agent.delta.v1"), vec![h1]);
        assert_eq!(trie.match_topic("k1.foo.bar.v1"), vec![h1]);
        assert!(trie.match_topic("k1.foo.bar.v2").is_empty());
    }

    #[test]
    fn test_compaction() {
        let mut trie = TopicTrieInner::new();
        let mut ids = vec![];
        for i in 0..10 {
            ids.push(trie.insert("k1.test.topic", &format!("sub-{i}")).unwrap());
        }
        // Remove 8 of 10
        for i in 0..8 {
            trie.remove(&format!("sub-{i}"));
        }
        let result = trie.match_topic("k1.test.topic");
        assert_eq!(result.len(), 2);
        assert!(result.contains(&ids[8]));
        assert!(result.contains(&ids[9]));
        assert_eq!(trie.size, 2);
    }

    #[test]
    fn test_prefix_doesnt_match_longer() {
        let mut trie = TopicTrieInner::new();
        trie.insert("k1.test", "sub-1").unwrap();
        assert!(trie.match_topic("k1.test.deeper").is_empty());
    }

    #[test]
    fn test_longer_doesnt_match_prefix() {
        let mut trie = TopicTrieInner::new();
        trie.insert("k1.test.deeper", "sub-1").unwrap();
        assert!(trie.match_topic("k1.test").is_empty());
    }

    #[test]
    fn test_greedy_with_wildcard_before() {
        let mut trie = TopicTrieInner::new();
        let h1 = trie.insert("k1.*.>", "sub-1").unwrap();
        assert_eq!(trie.match_topic("k1.agent.delta"), vec![h1]);
        assert_eq!(trie.match_topic("k1.session.update.v1"), vec![h1]);
        assert!(trie.match_topic("k1.agent").is_empty());
    }

    #[test]
    fn test_size_tracking() {
        let mut trie = TopicTrieInner::new();
        assert_eq!(trie.size, 0);
        trie.insert("a", "s1").unwrap();
        trie.insert("b", "s2").unwrap();
        assert_eq!(trie.size, 2);
        trie.remove("s1");
        assert_eq!(trie.size, 1);
    }

    #[test]
    fn test_double_remove() {
        let mut trie = TopicTrieInner::new();
        trie.insert("k1.test", "sub-1").unwrap();
        assert!(trie.remove("sub-1").is_some());
        assert!(trie.remove("sub-1").is_none());
    }
}
