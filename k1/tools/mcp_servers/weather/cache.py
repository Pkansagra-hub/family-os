"""
k1.tools.mcp_servers.weather.cache -- Response cache with TTL eviction.

Simple in-memory cache keyed by (location, units). Entries expire
after a configurable TTL (default 300 s / 5 min).

Thread-safe for single-writer concurrent-reader access patterns.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class _CacheEntry:
    """Internal cache entry with value and insertion timestamp."""

    value: Any
    created_at: float


class WeatherCache:
    """
    TTL-based in-memory cache for weather API responses.

    Parameters
    ----------
    ttl_seconds : float
        Seconds before an entry is considered stale.  Defaults to 300 (5 min).
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._ttl = ttl_seconds
        self._store: Dict[Tuple[str, ...], _CacheEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: Tuple[str, ...]) -> Optional[Any]:
        """
        Return cached value or ``None`` if absent / expired.

        Expired entries are removed lazily on access.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            del self._store[key]
            return None
        return entry.value

    def put(self, key: Tuple[str, ...], value: Any) -> None:
        """Store *value* under *key* with the current timestamp."""
        self._store[key] = _CacheEntry(value=value, created_at=time.monotonic())

    def invalidate(self, key: Tuple[str, ...]) -> None:
        """Remove a single entry (no-op if absent)."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Drop all entries."""
        self._store.clear()

    @property
    def size(self) -> int:
        """Number of entries (including possibly-stale ones)."""
        return len(self._store)

    def purge_expired(self) -> int:
        """Remove all stale entries.  Return count of purged items."""
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now - v.created_at >= self._ttl]
        for k in expired:
            del self._store[k]
        return len(expired)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_expired(self, entry: _CacheEntry) -> bool:
        return (time.monotonic() - entry.created_at) >= self._ttl
