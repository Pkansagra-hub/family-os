"""
k1.bus.middleware.idempotency -- Drop duplicate command envelopes (P6.12).

Command topics often carry a caller-supplied ``request_id`` so that
publishers can safely retry under network/timeouts.  Without an
idempotency check, a retry causes the command to be executed twice.

``IdempotencyMiddleware`` maintains a bounded LRU cache of recently
seen ``(topic, request_id)`` pairs.  The first envelope for a key is
delivered; duplicates within the TTL window are dropped (return None).

Design:
    - Stdlib only: ``OrderedDict`` for LRU + ``time.monotonic`` for TTL.
    - Bounded by ``max_entries`` (default 10_000) to cap memory usage.
    - ``ttl_s`` (default 300s = 5 min) discards stale entries on access.
    - Envelopes WITHOUT a ``request_id`` are passed through unchanged
      (the middleware can only deduplicate keyed messages).
    - NOT installed in the default chain; sites that publish commands
      wire it in explicitly via ``MiddlewareChain.append`` /
      ``BusFactory.create_local(middlewares=[...])``.

Recommended placement:
    Topic validation -> IdempotencyMiddleware -> Tracing -> Metrics.

Thread-safe: a single ``threading.Lock`` guards the cache.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Optional

from k1.bus.envelope import Envelope

logger = logging.getLogger(__name__)


class IdempotencyMiddleware:
    """
    Bounded LRU+TTL deduplicator keyed by ``(topic, request_id)``.

    Typical wiring::

        from k1.bus.middleware.idempotency import IdempotencyMiddleware
        idem = IdempotencyMiddleware(max_entries=10_000, ttl_s=300.0)
        bus = BusFactory.create_local(middlewares=[..., idem, ...])

    Envelopes whose ``request_id`` is empty bypass deduplication.
    """

    __slots__ = (
        "_cache",
        "_max_entries",
        "_ttl_s",
        "_lock",
        "_drop_count",
        "_pass_count",
        "_no_key_count",
    )

    def __init__(
        self,
        max_entries: int = 10_000,
        ttl_s: float = 300.0,
    ) -> None:
        if max_entries <= 0:
            raise ValueError(f"max_entries must be > 0, got {max_entries}")
        if ttl_s <= 0:
            raise ValueError(f"ttl_s must be > 0, got {ttl_s}")
        # OrderedDict[ (topic, request_id) ] -> insertion_monotonic_s
        self._cache: "OrderedDict[tuple[str, str], float]" = OrderedDict()
        self._max_entries = max_entries
        self._ttl_s = float(ttl_s)
        self._lock = threading.Lock()
        self._drop_count = 0
        self._pass_count = 0
        self._no_key_count = 0

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        """
        Drop the envelope if the (topic, request_id) was seen recently.

        Returns:
            ``envelope`` to continue the chain, or ``None`` to drop.
        """
        request_id = envelope.request_id
        if not request_id:
            self._no_key_count += 1
            return envelope

        key = (envelope.topic, request_id)
        now = time.monotonic()
        ttl = self._ttl_s

        with self._lock:
            existing = self._cache.get(key)
            if existing is not None and (now - existing) < ttl:
                # Duplicate within TTL window -- drop
                self._drop_count += 1
                # Refresh recency so the dedup window slides
                self._cache.move_to_end(key)
                self._cache[key] = now
                logger.debug(
                    "Idempotency drop: topic=%s request_id=%s envelope_id=%d",
                    envelope.topic,
                    request_id,
                    envelope.envelope_id,
                )
                return None

            # First sighting (or expired) -- record and pass through
            self._cache[key] = now
            self._cache.move_to_end(key)
            self._pass_count += 1

            # Opportunistic GC: evict expired entries from the front of
            # the OrderedDict.  Stops at the first non-expired entry
            # because order = insertion-recency.
            while self._cache:
                oldest_key = next(iter(self._cache))
                oldest_ts = self._cache[oldest_key]
                if (now - oldest_ts) >= ttl:
                    del self._cache[oldest_key]
                    continue
                break

            # Hard cap on size after GC
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

        return envelope

    @property
    def drop_count(self) -> int:
        """Number of duplicate envelopes dropped."""
        return self._drop_count

    @property
    def pass_count(self) -> int:
        """Number of envelopes admitted (first sighting)."""
        return self._pass_count

    @property
    def no_key_count(self) -> int:
        """Number of envelopes bypassed because ``request_id`` was empty."""
        return self._no_key_count

    @property
    def cache_size(self) -> int:
        """Current number of cached keys (post-GC)."""
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        """Drop all cached keys (test helper)."""
        with self._lock:
            self._cache.clear()

    def __repr__(self) -> str:
        return (
            f"IdempotencyMiddleware(max_entries={self._max_entries}, "
            f"ttl_s={self._ttl_s}, cached={self.cache_size}, "
            f"dropped={self._drop_count}, passed={self._pass_count})"
        )


__all__ = ["IdempotencyMiddleware"]
