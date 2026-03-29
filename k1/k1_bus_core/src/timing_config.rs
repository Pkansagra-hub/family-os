//! V2-M6-007/008: Per-topic-prefix delivery mode resolution via prefix trie.
//!
//! Replaces the V1 Python `TimingConfig.resolve()` which does linear
//! longest-prefix match.  This implementation uses a segment-based trie
//! for O(k) lookup where k = number of dot-separated segments.
//!
//! Runtime reloadable via `Arc<parking_lot::RwLock>` -- readers never
//! block on reload (short write window).
//!
//! DeliveryMode values match Python's IntEnum:
//!   STRICT = 0, RELAXED = 1, BEST_EFFORT = 2

use pyo3::prelude::*;
use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::Arc;

// ---------------------------------------------------------------------------
// DeliveryMode
// ---------------------------------------------------------------------------

/// Delivery mode for a topic prefix.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum DeliveryMode {
    Strict = 0,
    Relaxed = 1,
    BestEffort = 2,
}

impl DeliveryMode {
    /// Convert from integer (matching Python IntEnum values).
    pub fn from_int(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Strict),
            1 => Some(Self::Relaxed),
            2 => Some(Self::BestEffort),
            _ => None,
        }
    }

    /// Convert to integer.
    pub fn as_int(self) -> u8 {
        self as u8
    }
}

// ---------------------------------------------------------------------------
// Prefix Trie internals
// ---------------------------------------------------------------------------

/// A trie node for dot-separated topic segments.
#[derive(Debug, Default)]
struct TrieNode {
    /// Delivery mode set at this prefix (if any).
    mode: Option<DeliveryMode>,
    /// Children by segment name.
    children: HashMap<String, TrieNode>,
}

/// The prefix trie for topic -> DeliveryMode resolution.
#[derive(Debug)]
struct PrefixTrie {
    root: TrieNode,
    rule_count: usize,
}

impl PrefixTrie {
    fn new() -> Self {
        Self {
            root: TrieNode::default(),
            rule_count: 0,
        }
    }

    /// Insert a prefix rule.  The prefix is dot-separated.
    fn insert(&mut self, prefix: &str, mode: DeliveryMode) {
        let mut node = &mut self.root;
        for segment in prefix.split('.') {
            node = node
                .children
                .entry(segment.to_string())
                .or_default();
        }
        if node.mode.is_none() {
            self.rule_count += 1;
        }
        node.mode = Some(mode);
    }

    /// Resolve a concrete topic to its delivery mode using longest-prefix match.
    ///
    /// Walks the trie segment by segment, keeping track of the deepest
    /// node that has a mode set.  Returns the deepest match.
    fn resolve(&self, topic: &str, default: DeliveryMode) -> DeliveryMode {
        if topic.is_empty() {
            return default;
        }

        let mut node = &self.root;
        let mut best_match = default;

        for segment in topic.split('.') {
            match node.children.get(segment) {
                Some(child) => {
                    node = child;
                    if let Some(mode) = node.mode {
                        best_match = mode;
                    }
                }
                None => break,
            }
        }

        best_match
    }
}

// ---------------------------------------------------------------------------
// RustTimingConfig -- PyO3-exposed wrapper
// ---------------------------------------------------------------------------

/// Rust implementation of TimingConfig.
///
/// Thread-safe, runtime-reloadable prefix trie for topic -> DeliveryMode.
/// Uses `Arc<RwLock<PrefixTrie>>` so readers never block except during
/// the very brief write window of a reload.
#[pyclass]
pub(crate) struct RustTimingConfig {
    trie: Arc<RwLock<PrefixTrie>>,
    default: RwLock<DeliveryMode>,
}

#[pymethods]
impl RustTimingConfig {
    /// Create a new RustTimingConfig.
    ///
    /// Args:
    ///     rules: dict mapping prefix string -> delivery mode int (0/1/2).
    ///     default: default delivery mode int (0=STRICT, 1=RELAXED, 2=BEST_EFFORT).
    #[new]
    #[pyo3(signature = (rules=None, default=1))]
    fn new(rules: Option<HashMap<String, u8>>, default: u8) -> PyResult<Self> {
        let default_mode = DeliveryMode::from_int(default).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid default mode: {default}"))
        })?;

        let mut trie = PrefixTrie::new();
        if let Some(rules) = rules {
            for (prefix, mode_val) in &rules {
                if prefix.is_empty() {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "Empty prefix in timing rules",
                    ));
                }
                let mode = DeliveryMode::from_int(*mode_val).ok_or_else(|| {
                    pyo3::exceptions::PyValueError::new_err(format!(
                        "Invalid mode {mode_val} for prefix {prefix}"
                    ))
                })?;
                trie.insert(prefix, mode);
            }
        }

        Ok(Self {
            trie: Arc::new(RwLock::new(trie)),
            default: RwLock::new(default_mode),
        })
    }

    /// Resolve a concrete topic string to its delivery mode (int).
    ///
    /// Returns: 0 (STRICT), 1 (RELAXED), or 2 (BEST_EFFORT).
    fn resolve(&self, topic: &str) -> u8 {
        let default = *self.default.read();
        self.trie.read().resolve(topic, default).as_int()
    }

    /// Atomically replace the entire rule set.
    ///
    /// Args:
    ///     rules: dict mapping prefix string -> delivery mode int.
    fn reload(&self, rules: HashMap<String, u8>) -> PyResult<()> {
        let mut new_trie = PrefixTrie::new();
        for (prefix, mode_val) in &rules {
            if prefix.is_empty() {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "Empty prefix in timing rules",
                ));
            }
            let mode = DeliveryMode::from_int(*mode_val).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!(
                    "Invalid mode {mode_val} for prefix {prefix}"
                ))
            })?;
            new_trie.insert(prefix, mode);
        }
        *self.trie.write() = new_trie;
        Ok(())
    }

    /// Change the default delivery mode.
    fn set_default(&self, mode: u8) -> PyResult<()> {
        let m = DeliveryMode::from_int(mode).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid mode: {mode}"))
        })?;
        *self.default.write() = m;
        Ok(())
    }

    /// The current default delivery mode (int).
    #[getter]
    fn default_mode(&self) -> u8 {
        self.default.read().as_int()
    }

    /// Number of active prefix rules.
    #[getter]
    fn rule_count(&self) -> usize {
        self.trie.read().rule_count
    }

    /// Get current rules as dict (prefix -> mode int).
    #[getter]
    fn rules(&self) -> HashMap<String, u8> {
        let trie = self.trie.read();
        let mut result = HashMap::new();
        Self::collect_rules(&trie.root, &mut String::new(), &mut result);
        result
    }

    fn __repr__(&self) -> String {
        let count = self.trie.read().rule_count;
        let default = self.default.read().as_int();
        let mode_name = match default {
            0 => "STRICT",
            1 => "RELAXED",
            2 => "BEST_EFFORT",
            _ => "UNKNOWN",
        };
        format!("RustTimingConfig(rules={count}, default={mode_name})")
    }
}

impl RustTimingConfig {
    /// Resolve internally (no PyO3 overhead).
    pub(crate) fn resolve_mode(&self, topic: &str) -> DeliveryMode {
        let default = *self.default.read();
        self.trie.read().resolve(topic, default)
    }

    /// Collect all rules from the trie into a flat HashMap.
    fn collect_rules(node: &TrieNode, prefix: &mut String, result: &mut HashMap<String, u8>) {
        if let Some(mode) = node.mode {
            result.insert(prefix.clone(), mode.as_int());
        }
        for (segment, child) in &node.children {
            let was_empty = prefix.is_empty();
            if !was_empty {
                prefix.push('.');
            }
            prefix.push_str(segment);
            Self::collect_rules(child, prefix, result);
            // Restore prefix
            let new_len = if was_empty {
                0
            } else {
                prefix.len() - segment.len() - 1
            };
            prefix.truncate(new_len);
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trie_exact_match() {
        let mut trie = PrefixTrie::new();
        trie.insert("k1.capability", DeliveryMode::Strict);
        assert_eq!(
            trie.resolve("k1.capability", DeliveryMode::Relaxed),
            DeliveryMode::Strict
        );
    }

    #[test]
    fn test_trie_prefix_match() {
        let mut trie = PrefixTrie::new();
        trie.insert("k1.capability", DeliveryMode::Strict);
        assert_eq!(
            trie.resolve("k1.capability.completed.v1", DeliveryMode::Relaxed),
            DeliveryMode::Strict
        );
    }

    #[test]
    fn test_trie_longest_prefix_wins() {
        let mut trie = PrefixTrie::new();
        trie.insert("k1", DeliveryMode::Relaxed);
        trie.insert("k1.capability", DeliveryMode::Strict);
        assert_eq!(
            trie.resolve("k1.capability.completed.v1", DeliveryMode::BestEffort),
            DeliveryMode::Strict
        );
        assert_eq!(
            trie.resolve("k1.other.stuff", DeliveryMode::BestEffort),
            DeliveryMode::Relaxed
        );
    }

    #[test]
    fn test_trie_no_match_returns_default() {
        let trie = PrefixTrie::new();
        assert_eq!(
            trie.resolve("k1.unknown.topic", DeliveryMode::Relaxed),
            DeliveryMode::Relaxed
        );
    }

    #[test]
    fn test_trie_empty_topic_returns_default() {
        let trie = PrefixTrie::new();
        assert_eq!(
            trie.resolve("", DeliveryMode::BestEffort),
            DeliveryMode::BestEffort
        );
    }

    #[test]
    fn test_trie_multiple_rules() {
        let mut trie = PrefixTrie::new();
        trie.insert("k1.capability", DeliveryMode::Strict);
        trie.insert("k1.k0.sse", DeliveryMode::BestEffort);
        trie.insert("k1.session", DeliveryMode::Relaxed);

        assert_eq!(
            trie.resolve("k1.capability.completed.v1", DeliveryMode::Relaxed),
            DeliveryMode::Strict
        );
        assert_eq!(
            trie.resolve("k1.k0.sse.events", DeliveryMode::Relaxed),
            DeliveryMode::BestEffort
        );
        assert_eq!(
            trie.resolve("k1.session.update", DeliveryMode::Strict),
            DeliveryMode::Relaxed
        );
        assert_eq!(
            trie.resolve("k1.unknown", DeliveryMode::Relaxed),
            DeliveryMode::Relaxed
        );
    }

    #[test]
    fn test_trie_rule_count() {
        let mut trie = PrefixTrie::new();
        assert_eq!(trie.rule_count, 0);
        trie.insert("k1.a", DeliveryMode::Strict);
        assert_eq!(trie.rule_count, 1);
        trie.insert("k1.b", DeliveryMode::Relaxed);
        assert_eq!(trie.rule_count, 2);
        // Overwrite: count stays same
        trie.insert("k1.a", DeliveryMode::BestEffort);
        assert_eq!(trie.rule_count, 2);
    }

    #[test]
    fn test_delivery_mode_round_trip() {
        for v in 0..=2 {
            let mode = DeliveryMode::from_int(v).unwrap();
            assert_eq!(mode.as_int(), v);
        }
        assert!(DeliveryMode::from_int(3).is_none());
    }

    #[test]
    fn test_reload_replaces_rules() {
        let mut trie = PrefixTrie::new();
        trie.insert("k1.old", DeliveryMode::Strict);
        assert_eq!(
            trie.resolve("k1.old.topic", DeliveryMode::Relaxed),
            DeliveryMode::Strict
        );

        // Replace with new trie
        let mut new_trie = PrefixTrie::new();
        new_trie.insert("k1.new", DeliveryMode::BestEffort);
        trie = new_trie;

        assert_eq!(
            trie.resolve("k1.old.topic", DeliveryMode::Relaxed),
            DeliveryMode::Relaxed, // old rule gone
        );
        assert_eq!(
            trie.resolve("k1.new.topic", DeliveryMode::Relaxed),
            DeliveryMode::BestEffort,
        );
    }
}
