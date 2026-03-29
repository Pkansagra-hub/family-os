"""
k1.bus.timing.timing_config -- Per-topic-prefix delivery mode resolution.

The TimingConfig maps topic prefixes to DeliveryMode (STRICT / RELAXED /
BEST_EFFORT).  It determines how the TimingChain handles each envelope:

    STRICT:      Buffer on sequence gap, enforce causal parent ordering.
    RELAXED:     Deliver as-is, log reordering events (monitoring only).
    BEST_EFFORT: Deliver immediately, droppable under pressure.

Resolution algorithm:
    Longest-prefix match.  Given topic "k1.agent.abc.delta.v1":
        1. Check "k1.agent.abc.delta.v1" (exact)
        2. Check "k1.agent.abc.delta"
        3. Check "k1.agent.abc"
        4. Check "k1.agent"
        5. Check "k1"
        6. Fall back to default mode

    This is O(k) where k = number of segments.  No trie needed -- prefix
    rules are sparse (typically <20) and segment count is small (3-7).

Runtime reloadable:
    TimingConfig.reload(new_rules) replaces the entire rule set atomically.
    No code changes, no restart.  Config can come from env var, file, or
    programmatic injection.

Thread safety:
    All reads are via a snapshot reference (dict copy on reload).
    Readers never block.  reload() does a single reference swap.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from k1.bus.envelope import DeliveryMode

logger = logging.getLogger(__name__)


class TimingConfig:
    """
    Per-topic-prefix delivery mode configuration.

    Resolves a concrete topic string to its DeliveryMode using
    longest-prefix matching against a set of prefix rules.

    Usage::

        config = TimingConfig(
            rules={"k1.capability": DeliveryMode.STRICT,
                   "k1.k0.sse": DeliveryMode.BEST_EFFORT},
            default=DeliveryMode.RELAXED,
        )
        mode = config.resolve("k1.capability.completed.v1")  # STRICT
        mode = config.resolve("k1.unknown.topic")             # RELAXED (default)

    The rules dict maps topic PREFIXES (not full topics) to delivery modes.
    The longest matching prefix wins.
    """

    __slots__ = ("_rules", "_default", "_lock", "_sorted_prefixes")

    def __init__(
        self,
        rules: Optional[dict[str, DeliveryMode]] = None,
        default: DeliveryMode = DeliveryMode.RELAXED,
    ) -> None:
        """
        Create a TimingConfig.

        Args:
            rules:   Mapping of topic prefix -> DeliveryMode.
                     None = empty (everything gets default).
            default: DeliveryMode for topics matching no prefix rule.
                     Default is RELAXED (safe: deliver, log reorder).
        """
        self._default = default
        self._lock = threading.Lock()
        self._rules: dict[str, DeliveryMode] = {}
        self._sorted_prefixes: list[str] = []
        if rules:
            self._set_rules(rules)

    def resolve(self, topic: str) -> DeliveryMode:
        """
        Resolve a concrete topic to its delivery mode.

        Uses longest-prefix match against the rules.  If no rule matches,
        returns the default mode.

        Algorithm: walk the topic from full string down to first segment,
        checking each prefix against the rules dict (O(k) where k = segments).

        This is deliberately NOT the trie -- prefix rules are sparse (~20 max)
        and O(k) dict lookups on 3-7 segments is faster than trie overhead.

        Args:
            topic: Concrete topic string, e.g. "k1.capability.completed.v1"

        Returns:
            DeliveryMode for this topic.
        """
        if not topic:
            return self._default

        # Fast path: exact match on full topic
        rules = self._rules  # snapshot reference (atomic read)
        mode = rules.get(topic)
        if mode is not None:
            return mode

        # Walk down segment by segment (longest prefix first)
        parts = topic.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i])
            mode = rules.get(prefix)
            if mode is not None:
                return mode

        return self._default

    def reload(self, rules: dict[str, DeliveryMode]) -> None:
        """
        Atomically replace the entire rule set.

        Thread-safe: readers see either the old or new rules, never a
        partial update.  The lock serializes concurrent reloads (rare).

        Args:
            rules: New mapping of topic prefix -> DeliveryMode.
        """
        with self._lock:
            self._set_rules(rules)

        logger.info(
            "TimingConfig reloaded: %d rules, default=%s",
            len(self._rules),
            self._default.name,
        )

    def set_default(self, mode: DeliveryMode) -> None:
        """Change the default delivery mode for unmatched topics."""
        self._default = mode

    @property
    def default(self) -> DeliveryMode:
        """The default delivery mode for topics matching no rule."""
        return self._default

    @property
    def rules(self) -> dict[str, DeliveryMode]:
        """Read-only snapshot of current rules."""
        return dict(self._rules)

    @property
    def rule_count(self) -> int:
        """Number of active prefix rules."""
        return len(self._rules)

    def _set_rules(self, rules: dict[str, DeliveryMode]) -> None:
        """Internal: validate and set rules + sorted prefix cache."""
        validated: dict[str, DeliveryMode] = {}
        for prefix, mode in rules.items():
            if not prefix:
                raise ValueError("Empty prefix in timing rules")
            if not isinstance(mode, DeliveryMode):
                raise TypeError(
                    f"Rule value must be DeliveryMode, got {type(mode).__name__} "
                    f"for prefix {prefix!r}"
                )
            validated[prefix] = mode

        # Atomic swap (single reference assignment)
        self._rules = validated
        self._sorted_prefixes = sorted(validated.keys(), key=len, reverse=True)

    def __repr__(self) -> str:
        return f"TimingConfig(rules={len(self._rules)}, " f"default={self._default.name})"
