"""
k1.concierge.fsm.ultrabert_adapter -- K1-native UltraBERT adapter.

M10 E10.4.1: Direct integration with ``familyos_ultrabert`` pip package.
Zero dependency on k0/runtime/. K1 owns singleton, cache, GPU detection,
mapping constants, and metric tracking.

Protocol for testability:
    ``UltraBERTAdapter`` protocol  -- depend on this, not the concrete class.
    ``K1UltraBERTAdapter``         -- real impl (familyos_ultrabert.Client).
    ``StubUltraBERTAdapter``       -- returns None (tests without GPU).
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping constants (K1-owned, no k0 imports)
# ---------------------------------------------------------------------------

SENTIMENT_TO_VALENCE: dict[str, float] = {
    "very_negative": -0.8,
    "negative": -0.4,
    "neutral": 0.0,
    "positive": 0.4,
    "very_positive": 0.8,
}

HIGH_AROUSAL_EMOTIONS: frozenset[str] = frozenset({"anger", "excitement", "fear", "surprise"})

LOW_AROUSAL_EMOTIONS: frozenset[str] = frozenset({"sadness", "calm", "boredom", "contentment"})

ENTITY_MIN_CONFIDENCE: float = 0.65


# ---------------------------------------------------------------------------
# LRU/TTL Cache
# ---------------------------------------------------------------------------


class _LRUTTLCache:
    """Thread-safe LRU cache with per-entry TTL expiry.

    Args:
        max_size: Maximum number of entries.
        ttl_s:    Time-to-live in seconds per entry.
    """

    def __init__(self, max_size: int = 64, ttl_s: float = 30.0) -> None:
        self._max_size = max_size
        self._ttl_s = ttl_s
        self._store: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> dict | None:
        with self._lock:
            if key in self._store:
                ts, value = self._store[key]
                if (time.monotonic() - ts) <= self._ttl_s:
                    self._store.move_to_end(key)
                    self._hits += 1
                    return value
                # Expired
                del self._store[key]
            self._misses += 1
            return None

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            if key in self._store:
                del self._store[key]
            self._store[key] = (time.monotonic(), value)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0


# ---------------------------------------------------------------------------
# UltraBERTAdapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class UltraBERTAdapter(Protocol):
    """Protocol for UltraBERT analysis -- testable abstraction."""

    def analyze(self, text: str) -> dict[str, Any] | None: ...

    def is_available(self) -> bool: ...

    def get_metrics(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# K1UltraBERTAdapter (real implementation)
# ---------------------------------------------------------------------------


class K1UltraBERTAdapter:
    """K1-native adapter. Directly imports ``familyos_ultrabert.Client``.

    No dependency on k0/runtime/. Owns its own LRU/TTL cache,
    GPU detection, singleton pattern, and metric tracking.

    The LRU cache keys on ``sha256(text)`` to avoid storing raw user
    text in memory (privacy).
    """

    _instance: K1UltraBERTAdapter | None = None
    _lock = threading.Lock()

    def __init__(
        self,
        *,
        warmup: bool = False,
        warmup_rounds: int = 3,
        lazy_load: bool = True,
        backend: str = "auto",
        device: str = "auto",
        cache_size: int = 64,
        cache_ttl_s: float = 30.0,
    ) -> None:
        self._client: Any | None = None  # Lazy init
        self._cache = _LRUTTLCache(max_size=cache_size, ttl_s=cache_ttl_s)
        self._call_count = 0
        self._total_latency_ms = 0.0
        self._fallback_count = 0
        self._available: bool | None = None
        self._backend = backend
        self._device = device
        self._warmup_rounds = warmup_rounds
        # Construct the underlying Client. We always pass warmup=False to
        # Client because K1 owns its own warmup() so that metrics
        # (call_count, latency) reflect the warmup analyze() call.
        # lazy_load=True (default) defers the ~20s familyos_ultrabert model
        # load to first analyze() call so process boot is fast.
        self._init_client(lazy_load=lazy_load)
        if warmup and self._client is not None:
            self.warmup()

    # ------------------------------------------------------------------
    # Client init
    # ------------------------------------------------------------------

    def _init_client(self, *, lazy_load: bool) -> None:
        try:
            from familyos_ultrabert import Client  # type: ignore[import-untyped]

            self._client = Client(
                backend=self._backend,
                device=self._device,
                warmup=False,  # K1 owns its own warmup() (see __init__)
                warmup_rounds=self._warmup_rounds,
                lazy_load=lazy_load,
            )
            self._available = True
            logger.info(
                "K1UltraBERTAdapter: client initialized (backend=%s, device=%s, "
                "lazy_load=%s, warmup_rounds=%d)",
                self._backend,
                self._device,
                lazy_load,
                self._warmup_rounds,
            )
        except ImportError:
            logger.warning("K1UltraBERTAdapter: familyos_ultrabert not installed")
            self._client = None
            self._available = False
        except Exception as exc:
            logger.warning("K1UltraBERTAdapter: client init failed: %s", exc)
            self._client = None
            self._available = False

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def analyze(self, text: str) -> dict[str, Any] | None:
        """Run full 12-head analysis on *text*.

        Returns dict with all head outputs or ``None`` if unavailable.
        Results are cached by content hash (LRU, TTL).
        """
        if not self._client:
            self._fallback_count += 1
            return None

        cache_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        t0 = time.perf_counter()
        try:
            result = self._client.analyze(text)
        except Exception as exc:
            logger.warning("K1UltraBERTAdapter: analyze failed: %s", exc)
            self._fallback_count += 1
            return None
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._call_count += 1
        self._total_latency_ms += elapsed_ms

        out = self._result_to_dict(result)
        self._cache.put(cache_key, out)
        return out

    @staticmethod
    def _result_to_dict(result: Any) -> dict[str, Any]:
        """Convert ``familyos_ultrabert`` result object to plain dict."""
        return {
            "sentiment": result.sentiment,
            "sentiment_confidence": result.sentiment_confidence,
            "emotions": result.emotions,
            "emotion_scores": result.emotion_scores,
            "safety": result.safety,
            "safety_confidence": result.safety_confidence,
            "entities": result.entities,
            "general_entities": result.general_entities,
            "temporal": result.temporal,
            "intent": result.intent,
            "ingress": result.ingress,
            "relations": result.relations,
            "embedding": result.embedding,
            "latency_ms": result.latency_ms,
        }

    def is_available(self) -> bool:
        """Whether the underlying ``familyos_ultrabert`` client is ready."""
        return bool(self._available)

    def warmup(self) -> None:
        """Trigger a first-pass forward to amortize model load latency."""
        if self._client is not None:
            t0 = time.perf_counter()
            self.analyze("warmup")
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("K1UltraBERTAdapter: warmup completed in %.1fms", elapsed)
        else:
            logger.warning("K1UltraBERTAdapter: warmup skipped (client unavailable)")

    def get_metrics(self) -> dict[str, Any]:
        """Return adapter-level metrics."""
        return {
            "call_count": self._call_count,
            "avg_latency_ms": (
                (self._total_latency_ms / self._call_count) if self._call_count else 0.0
            ),
            "cache_hits": self._cache.hits,
            "cache_misses": self._cache.misses,
            "fallback_count": self._fallback_count,
            "available": self.is_available(),
        }

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(
        cls,
        *,
        warmup: bool = False,
        warmup_rounds: int = 3,
        lazy_load: bool = True,
        backend: str = "auto",
        device: str = "auto",
        cache_size: int = 64,
        cache_ttl_s: float = 30.0,
    ) -> K1UltraBERTAdapter:
        """Return (or create) the module-level singleton."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(
                        warmup=warmup,
                        warmup_rounds=warmup_rounds,
                        lazy_load=lazy_load,
                        backend=backend,
                        device=device,
                        cache_size=cache_size,
                        cache_ttl_s=cache_ttl_s,
                    )
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Destroy the singleton (for testing)."""
        with cls._lock:
            cls._instance = None


# ---------------------------------------------------------------------------
# StubUltraBERTAdapter (for tests without GPU)
# ---------------------------------------------------------------------------


class StubUltraBERTAdapter:
    """Returns ``None`` for all ``analyze()`` calls.

    Used in unit tests that do not have ``familyos_ultrabert`` installed.
    """

    def analyze(self, text: str) -> dict[str, Any] | None:  # noqa: ARG002
        return None

    def is_available(self) -> bool:
        return False

    def get_metrics(self) -> dict[str, Any]:
        return {"stub": True, "available": False}


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------


def get_ultrabert_adapter(
    *,
    warmup: bool = False,
    warmup_rounds: int = 3,
    lazy_load: bool = True,
    backend: str = "auto",
    device: str = "auto",
    cache_size: int = 64,
    cache_ttl_s: float = 30.0,
) -> K1UltraBERTAdapter:
    """Singleton factory for production use."""
    return K1UltraBERTAdapter.get_instance(
        warmup=warmup,
        warmup_rounds=warmup_rounds,
        lazy_load=lazy_load,
        backend=backend,
        device=device,
        cache_size=cache_size,
        cache_ttl_s=cache_ttl_s,
    )
