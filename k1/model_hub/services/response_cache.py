"""LRU response cache with capability-aware keying [F47].

Caches HubResponse by (capability + payload_hash + model_id + temperature)
with TTL eviction and skip rules for non-cacheable capabilities.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.response_cache
  -> k1.model_hub.types    (Layer 0: CapabilityType, HubRequest, HubResponse)
  -> k1.model_hub.config   (Layer 0: ModelHubConfig)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: ResponseCache service
- Invariant MH-09: Cache TTL 5min default, LRU eviction
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.types import CapabilityType, HubRequest, HubResponse

# ===========================================================================
# Cache Entry
# ===========================================================================


@dataclass
class _CacheEntry:
    """Internal cache entry with metadata."""

    response: HubResponse
    created_at: float
    ttl_s: int
    cache_key: str
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) >= self.ttl_s

    @property
    def age_ms(self) -> int:
        return int((time.monotonic() - self.created_at) * 1000)


# ===========================================================================
# Cache Result
# ===========================================================================


@dataclass(frozen=True)
class CacheResult:
    """Result of a cache lookup."""

    hit: bool
    response: Optional[HubResponse] = None
    cache_key: str = ""
    age_ms: int = 0


# ===========================================================================
# Skip rules: capabilities that should NEVER be cached (MH-09)
# ===========================================================================

_SKIP_CAPABILITIES = frozenset(
    {
        CapabilityType.TOOL_CALL,  # Side-effect potential
        CapabilityType.BATCH,  # Batch processing
        CapabilityType.MODERATE,  # Must be fresh
    }
)

_HIGH_TEMPERATURE_THRESHOLD = 0.9


# ===========================================================================
# ResponseCache
# ===========================================================================


class ResponseCache:
    """LRU response cache with capability-aware keying (MH-09).

    Key: hash(capability + payload_hash + model_id + temperature).
    TTL: 5min default (from config.cache_ttl_s).
    Eviction: LRU with max entries (from config.cache_max_entries).

    Skip rules (never cache):
      - TOOL_CALL (side-effect potential)
      - BATCH (batch processing)
      - MODERATE (must be fresh)
      - temperature > 0.9 (high randomness)
      - streaming requests (partial data)

    Thread-safe: lock-free reads, write lock for put + eviction.
    """

    def __init__(self, config: ModelHubConfig) -> None:
        self._max_entries = config.cache_max_entries
        self._default_ttl_s = config.cache_ttl_s
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._total_hits = 0
        self._total_misses = 0

    # -- Cache Key -------------------------------------------------------------

    @staticmethod
    def build_cache_key(
        capability: CapabilityType,
        payload: Any,
        model_id: str = "",
        temperature: float = 0.7,
        session_id: str = "",
    ) -> str:
        """Build a deterministic cache key from request components.

        Key: SHA-256 of (capability + payload_repr + model_id + temperature + session_id).

        ``session_id`` is included so that two concurrent sessions cannot
        collide on cached LLM responses (3.1.1 follow-up). An empty
        ``session_id`` (the default for boot/shared traffic) keeps the
        legacy behaviour for non-session-bound requests.

        Args:
            capability: Request capability type.
            payload: Request payload (must be serializable via repr).
            model_id: Selected model ID.
            temperature: Request temperature.
            session_id: Per-request session identifier (HubRequest.session_id).

        Returns:
            Hex digest cache key.
        """
        key_parts = [
            capability.value,
            json.dumps(
                dataclasses.asdict(payload) if dataclasses.is_dataclass(payload) else payload,
                sort_keys=True,
                default=str,
            ),
            model_id,
            f"{temperature:.4f}",
            session_id,
        ]
        key_str = "|".join(key_parts)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    # -- Should Cache ----------------------------------------------------------

    @staticmethod
    def should_cache(request: HubRequest, *, streaming: bool = False) -> bool:
        """Check if a request is cacheable.

        Returns False for:
          - TOOL_CALL, BATCH, MODERATE capabilities
          - temperature > 0.9
          - streaming requests

        Args:
            request: HubRequest to check.
            streaming: Whether this is a streaming request.

        Returns:
            True if the request result should be cached.
        """
        if request.capability in _SKIP_CAPABILITIES:
            return False
        if request.constraints.temperature > _HIGH_TEMPERATURE_THRESHOLD:
            return False
        if streaming:
            return False
        return True

    # -- Get -------------------------------------------------------------------

    def get(self, cache_key: str) -> CacheResult:
        """Look up a cached response.

        LRU: moves entry to end on hit.
        Evicts expired entries on access.

        Args:
            cache_key: Cache key from build_cache_key().

        Returns:
            CacheResult with hit/miss status.
        """
        with self._lock:
            entry = self._cache.get(cache_key)

            if entry is None:
                self._total_misses += 1
                return CacheResult(hit=False, cache_key=cache_key)

            if entry.is_expired:
                del self._cache[cache_key]
                self._total_misses += 1
                return CacheResult(hit=False, cache_key=cache_key)

            # LRU: move to end
            self._cache.move_to_end(cache_key)
            entry.hit_count += 1
            self._total_hits += 1

            return CacheResult(
                hit=True,
                response=entry.response,
                cache_key=cache_key,
                age_ms=entry.age_ms,
            )

    # -- Put -------------------------------------------------------------------

    def put(
        self,
        cache_key: str,
        response: HubResponse,
        ttl_s: Optional[int] = None,
    ) -> None:
        """Store a response in the cache.

        Evicts LRU entries if cache is full.

        Args:
            cache_key: Cache key from build_cache_key().
            response: HubResponse to cache.
            ttl_s: Override TTL in seconds. Uses default if None.
        """
        effective_ttl = ttl_s if ttl_s is not None else self._default_ttl_s

        with self._lock:
            # Sweep expired entries before eviction to free space.
            self._sweep_expired_locked()

            # If key exists, remove it first (will re-add at end)
            if cache_key in self._cache:
                del self._cache[cache_key]

            # Evict LRU entries if at capacity
            while len(self._cache) >= self._max_entries:
                self._cache.popitem(last=False)  # Remove oldest

            self._cache[cache_key] = _CacheEntry(
                response=response,
                created_at=time.monotonic(),
                ttl_s=effective_ttl,
                cache_key=cache_key,
            )

    # -- Invalidate / Clear ----------------------------------------------------

    def _sweep_expired_locked(self) -> None:
        """Remove all expired entries. Must be called with self._lock held."""
        expired = [k for k, e in self._cache.items() if e.is_expired]
        for k in expired:
            del self._cache[k]

    def invalidate(self, cache_key: str) -> bool:
        """Remove a specific entry from the cache.

        Returns True if the entry was found and removed.
        """
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                return True
            return False

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._cache.clear()

    # -- Stats -----------------------------------------------------------------

    @property
    def size(self) -> int:
        """Number of entries currently in cache."""
        return len(self._cache)

    @property
    def max_entries(self) -> int:
        """Maximum cache capacity."""
        return self._max_entries

    @property
    def total_hits(self) -> int:
        """Total cache hits since creation."""
        return self._total_hits

    @property
    def total_misses(self) -> int:
        """Total cache misses since creation."""
        return self._total_misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0-1.0)."""
        total = self._total_hits + self._total_misses
        return self._total_hits / total if total > 0 else 0.0


__all__ = [
    "CacheResult",
    "ResponseCache",
]
