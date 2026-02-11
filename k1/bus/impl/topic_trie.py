"""
k1.bus.impl.topic_trie -- Radix-compressed topic trie for O(k) matching.

This is the routing core of LocalBus.  Every subscription inserts a
pattern into the trie; every publish walks the trie to find matching
handlers.  The trie supports:

    - Exact match:     "k1.capability.completed.v1"
    - Single wildcard: "k1.agent.*.delta.v1"   (* matches exactly one segment)
    - Greedy wildcard: "k1.agent.>"             (> matches one or more trailing segments)

Segment separator is "." (dot).

Complexity:
    insert:  O(k) where k = number of segments in pattern
    match:   O(k * W) where W = max wildcard fan-out at any node (typically 1-2)
    remove:  O(k)

Thread safety:
    The trie is NOT thread-safe internally.  LocalBus wraps it with a
    ReadWriteLock for concurrent access.  This keeps the trie simple,
    fast, and testable in isolation.

Design notes:
    - No heap allocation on the match hot path (pre-allocated result list).
    - Handlers stored in a list per leaf node (multiple subscribers per pattern).
    - Subscription IDs enable O(1) removal without full tree walk.
    - The trie prunes empty branches on remove to prevent memory leaks.

Rust portability:
    This trie maps directly to a HashMap<String, TrieNode> in Rust.
    No Python-specific types leak into the structure.
"""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")

# Sentinel for the single-segment wildcard
_WILDCARD = "*"
# Sentinel for the greedy (multi-segment) wildcard
_GREEDY = ">"


class _TrieNode(Generic[T]):
    """Internal trie node.  Not part of public API."""

    __slots__ = ("children", "handlers", "subscription_ids")

    children: dict[str, _TrieNode[T]]
    handlers: list[T]
    subscription_ids: list[str]

    def __init__(self) -> None:
        self.children = {}
        self.handlers = []
        self.subscription_ids = []


class TopicTrie(Generic[T]):
    """
    Radix trie for hierarchical topic matching.

    Type parameter T is the handler type (typically BusHandler = Callable[[Envelope], None]).

    Usage::

        trie: TopicTrie[BusHandler] = TopicTrie()
        trie.insert("k1.agent.*.delta.v1", handler, "sub-001")
        matches = trie.match("k1.agent.abc.delta.v1")
        # matches == [handler]

    Wildcard rules:
        "*"  matches exactly ONE segment at that position.
        ">"  matches ONE OR MORE trailing segments (must be last segment).
             "k1.agent.>" matches "k1.agent.abc", "k1.agent.abc.delta.v1", etc.

    Patterns:
        Segments are split on ".".
        Empty segments are not allowed.
        ">" must be the LAST segment if present.
    """

    __slots__ = ("_root", "_size", "_sub_index")

    def __init__(self) -> None:
        self._root: _TrieNode[T] = _TrieNode()
        self._size: int = 0
        # Index: subscription_id -> (node, index_in_node.handlers)
        # Enables O(1) removal without tree walk
        self._sub_index: dict[str, tuple[_TrieNode[T], int]] = {}

    @property
    def size(self) -> int:
        """Number of active subscriptions in the trie."""
        return self._size

    def insert(self, pattern: str, handler: T, subscription_id: str) -> None:
        """
        Insert a handler for a topic pattern.

        Args:
            pattern:         Dot-separated topic pattern (e.g. "k1.agent.*.delta.v1").
            handler:         The handler to invoke on match.
            subscription_id: Unique ID for this subscription (used for removal).

        Raises:
            ValueError: If pattern is empty, has empty segments, or ">" is not last.
        """
        segments = self._validate_pattern(pattern)
        node = self._root

        for seg in segments:
            if seg not in node.children:
                node.children[seg] = _TrieNode()
            node = node.children[seg]

        idx = len(node.handlers)
        node.handlers.append(handler)
        node.subscription_ids.append(subscription_id)
        self._sub_index[subscription_id] = (node, idx)
        self._size += 1

    def remove(self, subscription_id: str) -> bool:
        """
        Remove a subscription by ID.

        Returns True if found and removed, False if not found.
        Does NOT prune empty branches (to avoid complexity on hot path).
        Handlers are tombstoned with None to preserve index stability
        until compaction.
        """
        entry = self._sub_index.pop(subscription_id, None)
        if entry is None:
            return False

        node, idx = entry
        # Tombstone: replace handler with None, mark subscription_id empty
        # This preserves indices for other _sub_index entries pointing to same node
        if idx < len(node.handlers):
            node.handlers[idx] = None  # type: ignore[list-item]
            node.subscription_ids[idx] = ""
        self._size -= 1

        # Compact if more than half are tombstones
        self._maybe_compact(node, self._sub_index)
        return True

    def match(self, topic: str) -> list[T]:
        """
        Find all handlers matching a concrete topic string.

        Args:
            topic: Concrete topic (no wildcards), e.g. "k1.agent.abc.delta.v1".

        Returns:
            List of matching handlers (may be empty).
            Order: depth-first, insertion order within each node.
        """
        if not topic:
            return []

        segments = topic.split(".")
        result: list[T] = []
        self._match_recursive(self._root, segments, 0, result)
        return result

    def _match_recursive(
        self,
        node: _TrieNode[T],
        segments: list[str],
        depth: int,
        result: list[T],
    ) -> None:
        """DFS match through the trie, collecting handlers."""
        if depth == len(segments):
            # Reached end of topic -- collect handlers at this node
            for h in node.handlers:
                if h is not None:
                    result.append(h)
            return

        seg = segments[depth]

        # 1. Exact match on this segment
        child = node.children.get(seg)
        if child is not None:
            self._match_recursive(child, segments, depth + 1, result)

        # 2. Single wildcard "*" matches this one segment
        wild_child = node.children.get(_WILDCARD)
        if wild_child is not None:
            self._match_recursive(wild_child, segments, depth + 1, result)

        # 3. Greedy wildcard ">" matches all remaining segments
        greedy_child = node.children.get(_GREEDY)
        if greedy_child is not None:
            # ">" matches one or more remaining segments -- collect its handlers
            for h in greedy_child.handlers:
                if h is not None:
                    result.append(h)

    def clear(self) -> None:
        """Remove all subscriptions."""
        self._root = _TrieNode()
        self._sub_index.clear()
        self._size = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_pattern(pattern: str) -> list[str]:
        """Validate and split pattern into segments."""
        if not pattern:
            raise ValueError("Topic pattern must not be empty")

        segments = pattern.split(".")

        for i, seg in enumerate(segments):
            if not seg:
                raise ValueError(f"Topic pattern has empty segment at position {i}: {pattern!r}")
            if seg == _GREEDY and i != len(segments) - 1:
                raise ValueError(f"Greedy wildcard '>' must be the last segment: {pattern!r}")

        return segments

    @staticmethod
    def _maybe_compact(node: _TrieNode[T], sub_index: dict[str, tuple[_TrieNode[T], int]]) -> None:
        """Compact tombstoned entries if more than half are None."""
        if not node.handlers:
            return

        tombstones = sum(1 for h in node.handlers if h is None)
        if tombstones <= len(node.handlers) // 2:
            return

        # Rebuild without tombstones
        new_handlers: list[T] = []
        new_ids: list[str] = []
        for h, sid in zip(node.handlers, node.subscription_ids):
            if h is not None:
                new_idx = len(new_handlers)
                new_handlers.append(h)
                new_ids.append(sid)
                # Update the sub_index to point to the new position
                if sid in sub_index:
                    sub_index[sid] = (node, new_idx)

        node.handlers = new_handlers
        node.subscription_ids = new_ids

    def __len__(self) -> int:
        return self._size

    def __repr__(self) -> str:
        return f"TopicTrie(subscriptions={self._size})"
