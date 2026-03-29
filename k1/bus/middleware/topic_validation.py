"""
k1.bus.middleware.topic_validation -- Topic registry and validation middleware.

Validates that envelope topics are registered (known) before dispatch.
Uses SOFT validation: unknown topics produce a log warning but are NEVER
dropped.  This preserves bus liveness while giving operators visibility
into misconfigured or rogue publishers.

TopicRegistry supports:
    - Exact topic registration:    "k1.capability.completed.v1"
    - Prefix registration:         "k1.agent."  (matches any topic starting with prefix)
    - Wildcard registration:       "k1.agent.*.delta.*" (segment wildcards)

Usage::

    from k1.bus.middleware.topic_validation import (
        TopicRegistry,
        TopicValidationMiddleware,
    )

    registry = TopicRegistry()
    registry.register("k1.capability.completed.v1")   # exact
    registry.register_prefix("k1.agent.")              # prefix
    registry.register("k1.orchestration.*.v1")         # wildcard

    mw = TopicValidationMiddleware(registry)
    result = mw.process(envelope)  # Always returns envelope; logs if unknown
"""

from __future__ import annotations

import fnmatch
import logging
import threading
from typing import Optional

from k1.bus.envelope import Envelope

logger = logging.getLogger(__name__)


class TopicRegistry:
    """
    Registry of known bus topics.

    Supports three registration modes:
        1. Exact:    ``register("k1.capability.completed.v1")``
        2. Prefix:   ``register_prefix("k1.agent.")``
        3. Wildcard: ``register("k1.agent.*.delta.*")`` (uses fnmatch glob)

    Validation order (short-circuit on first match):
        1. Exact set lookup (O(1))
        2. Prefix scan (O(n) over registered prefixes)
        3. Wildcard fnmatch (O(n) over registered patterns)

    Thread-safe: uses RLock for registration, lookup is safe with GIL.
    """

    __slots__ = ("_exact", "_prefixes", "_wildcards", "_lock")

    def __init__(self) -> None:
        self._exact: set[str] = set()
        self._prefixes: list[str] = []
        self._wildcards: list[str] = []
        self._lock = threading.RLock()

    def register(self, topic: str) -> None:
        """
        Register an exact topic or wildcard pattern.

        If the topic contains ``*`` or ``?``, it is treated as a wildcard.
        Otherwise it is registered as an exact match.

        Args:
            topic: Topic string or glob pattern.
        """
        with self._lock:
            if "*" in topic or "?" in topic:
                if topic not in self._wildcards:
                    self._wildcards.append(topic)
            else:
                self._exact.add(topic)

    def register_prefix(self, prefix: str) -> None:
        """
        Register a topic prefix.

        Any topic starting with this prefix is considered known.

        Args:
            prefix: Topic prefix (e.g. "k1.agent.").
        """
        with self._lock:
            if prefix not in self._prefixes:
                self._prefixes.append(prefix)

    def is_known(self, topic: str) -> bool:
        """
        Check if a topic is registered (known).

        Returns True if the topic matches any:
            1. Exact registered topic
            2. Any registered prefix
            3. Any registered wildcard pattern

        Args:
            topic: Topic string to validate.

        Returns:
            True if the topic is known.
        """
        # 1. Exact match (fastest)
        if topic in self._exact:
            return True

        # 2. Prefix match
        for prefix in self._prefixes:
            if topic.startswith(prefix):
                return True

        # 3. Wildcard match (fnmatch uses shell-style globs)
        for pattern in self._wildcards:
            if fnmatch.fnmatch(topic, pattern):
                return True

        return False

    def unregister(self, topic: str) -> bool:
        """
        Remove a topic from the registry.

        Args:
            topic: Exact topic, prefix, or wildcard to remove.

        Returns:
            True if the topic was found and removed.
        """
        with self._lock:
            if topic in self._exact:
                self._exact.discard(topic)
                return True
            if topic in self._prefixes:
                self._prefixes.remove(topic)
                return True
            if topic in self._wildcards:
                self._wildcards.remove(topic)
                return True
        return False

    @property
    def size(self) -> int:
        """Total number of registrations (exact + prefix + wildcard)."""
        return len(self._exact) + len(self._prefixes) + len(self._wildcards)

    def clear(self) -> None:
        """Remove all registrations."""
        with self._lock:
            self._exact.clear()
            self._prefixes.clear()
            self._wildcards.clear()

    def __repr__(self) -> str:
        return (
            f"TopicRegistry(exact={len(self._exact)}, "
            f"prefixes={len(self._prefixes)}, "
            f"wildcards={len(self._wildcards)})"
        )


class TopicValidationMiddleware:
    """
    Soft topic validation middleware for the K1 bus.

    Checks that envelope topics are registered in the TopicRegistry.
    Unknown topics produce a WARNING log but are NEVER dropped.

    This is intentionally soft validation:
        - In development: warnings catch misconfigured topics early
        - In production: unknown topics still flow (bus liveness > strictness)
        - Operators monitor warning rate for anomaly detection

    Thread-safe: TopicRegistry handles its own synchronization.
    """

    __slots__ = ("_registry", "_warn_count")

    def __init__(self, registry: TopicRegistry) -> None:
        """
        Create a TopicValidationMiddleware.

        Args:
            registry: TopicRegistry containing known topics.
        """
        self._registry = registry
        self._warn_count = 0

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        """
        Validate envelope topic against the registry.

        SOFT validation: always returns the envelope.  Unknown topics
        produce a warning log but are never dropped.

        Args:
            envelope: Stamped bus envelope.

        Returns:
            The same envelope, always (never None).
        """
        if not self._registry.is_known(envelope.topic):
            self._warn_count += 1
            logger.warning(
                "Unknown topic on bus: topic=%s envelope_id=%d "
                "(topic not in registry, delivering anyway)",
                envelope.topic,
                envelope.envelope_id,
            )

        return envelope

    @property
    def registry(self) -> TopicRegistry:
        """Access the underlying TopicRegistry."""
        return self._registry

    @property
    def warning_count(self) -> int:
        """Number of unknown-topic warnings emitted."""
        return self._warn_count

    def __repr__(self) -> str:
        return (
            f"TopicValidationMiddleware("
            f"registry={self._registry}, "
            f"warnings={self._warn_count})"
        )


__all__ = ["TopicRegistry", "TopicValidationMiddleware"]
