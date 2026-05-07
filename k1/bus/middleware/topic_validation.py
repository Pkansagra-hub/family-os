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
from typing import Callable, Optional

from k1.bus.envelope import Envelope

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema validation types (P6.11)
# ---------------------------------------------------------------------------

#: Validator signature.  Receives the envelope payload bytes and the
#: envelope itself (for context like topic/envelope_id in error messages).
#: Must raise an Exception subclass on validation failure.  The exception
#: type and message are surfaced via warning logs / drop counters.
PayloadValidator = Callable[[bytes, "Envelope"], None]


class SchemaValidationError(ValueError):
    """Raised by validators when payload structure is invalid."""


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

    __slots__ = ("_exact", "_prefixes", "_wildcards", "_validators", "_lock")

    def __init__(self) -> None:
        self._exact: set[str] = set()
        self._prefixes: list[str] = []
        self._wildcards: list[str] = []
        # P6.11: per-topic payload validators (exact-topic keyed).
        # Validators registered via register(topic, validator=...) are
        # stored here.  Prefix/wildcard registrations may also store a
        # validator under their pattern string.
        self._validators: dict[str, PayloadValidator] = {}
        self._lock = threading.RLock()

    def register(
        self,
        topic: str,
        validator: PayloadValidator | None = None,
    ) -> None:
        """
        Register an exact topic or wildcard pattern.

        If the topic contains ``*`` or ``?``, it is treated as a wildcard.
        Otherwise it is registered as an exact match.

        Args:
            topic: Topic string or glob pattern.
            validator: Optional payload validator.  When set, the
                ``TopicValidationMiddleware`` invokes it with
                ``(payload, envelope)`` for every matching envelope.
                Validators MUST raise on failure (any exception type).
        """
        with self._lock:
            if "*" in topic or "?" in topic:
                if topic not in self._wildcards:
                    self._wildcards.append(topic)
            else:
                self._exact.add(topic)
            if validator is not None:
                self._validators[topic] = validator

    def register_prefix(
        self,
        prefix: str,
        validator: PayloadValidator | None = None,
    ) -> None:
        """
        Register a topic prefix.

        Any topic starting with this prefix is considered known.

        Args:
            prefix: Topic prefix (e.g. "k1.agent.").
            validator: Optional payload validator applied to every
                envelope whose topic starts with this prefix.
        """
        with self._lock:
            if prefix not in self._prefixes:
                self._prefixes.append(prefix)
            if validator is not None:
                self._validators[prefix] = validator

    def lookup_validator(self, topic: str) -> PayloadValidator | None:
        """
        Return the validator registered for ``topic``, if any.

        Resolution order mirrors ``is_known``:
            1. Exact topic
            2. Longest matching prefix
            3. First matching wildcard pattern
        """
        # 1. Exact
        v = self._validators.get(topic)
        if v is not None:
            return v
        # 2. Prefix (longest match wins)
        best_prefix: str | None = None
        for prefix in self._prefixes:
            if topic.startswith(prefix) and (
                best_prefix is None or len(prefix) > len(best_prefix)
            ):
                best_prefix = prefix
        if best_prefix is not None:
            v = self._validators.get(best_prefix)
            if v is not None:
                return v
        # 3. Wildcard
        for pattern in self._wildcards:
            if fnmatch.fnmatch(topic, pattern):
                v = self._validators.get(pattern)
                if v is not None:
                    return v
        return None

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
            removed = False
            if topic in self._exact:
                self._exact.discard(topic)
                removed = True
            elif topic in self._prefixes:
                self._prefixes.remove(topic)
                removed = True
            elif topic in self._wildcards:
                self._wildcards.remove(topic)
                removed = True
            if removed:
                self._validators.pop(topic, None)
        return removed

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
            self._validators.clear()

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

    __slots__ = ("_registry", "_warn_count", "_mode", "_schema_violations", "_schema_drops")

    def __init__(
        self,
        registry: TopicRegistry,
        schema_validation_mode: str = "permissive",
    ) -> None:
        """
        Create a TopicValidationMiddleware.

        Args:
            registry: TopicRegistry containing known topics.
            schema_validation_mode: "permissive" (default) — log + count
                schema violations but deliver the envelope anyway.
                "strict" — drop envelopes whose payload fails schema
                validation (returns None from ``process()``).
        """
        if schema_validation_mode not in ("permissive", "strict"):
            raise ValueError(
                "schema_validation_mode must be 'permissive' or 'strict', "
                f"got {schema_validation_mode!r}"
            )
        self._registry = registry
        self._warn_count = 0
        self._mode = schema_validation_mode
        self._schema_violations = 0
        self._schema_drops = 0

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        """
        Validate envelope topic and (optionally) payload schema.

        Topic validation is SOFT: unknown topics produce a warning log
        but are never dropped.

        Schema validation (P6.11) runs only when the registry has a
        validator for this topic.  In ``permissive`` mode (default),
        validation failures are logged + counted but the envelope is
        still delivered.  In ``strict`` mode, validation failures
        cause the envelope to be dropped (returns None).

        Args:
            envelope: Stamped bus envelope.

        Returns:
            The envelope to continue the chain, or None when strict
            mode rejects a schema violation.
        """
        if not self._registry.is_known(envelope.topic):
            self._warn_count += 1
            logger.warning(
                "Unknown topic on bus: topic=%s envelope_id=%d "
                "(topic not in registry, delivering anyway)",
                envelope.topic,
                envelope.envelope_id,
            )

        validator = self._registry.lookup_validator(envelope.topic)
        if validator is not None:
            try:
                validator(envelope.payload, envelope)
            except Exception as exc:  # noqa: BLE001 — validators may raise anything
                self._schema_violations += 1
                if self._mode == "strict":
                    self._schema_drops += 1
                    logger.warning(
                        "Schema validation failed (strict, DROPPING): "
                        "topic=%s envelope_id=%d error=%s: %s",
                        envelope.topic,
                        envelope.envelope_id,
                        type(exc).__name__,
                        exc,
                    )
                    return None
                logger.warning(
                    "Schema validation failed (permissive, delivering): "
                    "topic=%s envelope_id=%d error=%s: %s",
                    envelope.topic,
                    envelope.envelope_id,
                    type(exc).__name__,
                    exc,
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

    @property
    def schema_violation_count(self) -> int:
        """Total payload schema validation failures (permissive + strict)."""
        return self._schema_violations

    @property
    def schema_drop_count(self) -> int:
        """Schema validation failures that caused a drop (strict mode)."""
        return self._schema_drops

    def __repr__(self) -> str:
        return (
            f"TopicValidationMiddleware("
            f"registry={self._registry}, "
            f"mode={self._mode!r}, "
            f"warnings={self._warn_count}, "
            f"schema_violations={self._schema_violations})"
        )


__all__ = [
    "TopicRegistry",
    "TopicValidationMiddleware",
    "PayloadValidator",
    "SchemaValidationError",
]
