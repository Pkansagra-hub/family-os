"""
MinHash Locality-Sensitive Hashing for Scale (>50K Events).

Issue: 4.3.11
Spec Reference: Dossier Appendix C.4.1.3 (lines 22296-22420)

Purpose: Sub-linear duplicate detection for high-volume spaces.

Problem:
- 10K events: ~10ms per new event (acceptable)
- 50K events: ~50ms per new event (slow)
- 100K+ events: >100ms per new event (unacceptable)

Solution: MinHash LSH achieves O(log n) candidate retrieval.

Scientific Basis: Broder (1997) - Near-duplicate detection using MinHash

Auto-Switch Logic:
- < 10,000 events: SimHash pairwise O(n)
- 10K-50K events: SimHash + bucketing O(n/b)
- > 50,000 events: MinHash LSH O(log n)
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Protocol, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Constants (from Dossier Appendix C.4.1.3)
# =============================================================================


# Default MinHash parameters
DEFAULT_NUM_HASHES = 128  # Total hash functions
DEFAULT_NUM_BANDS = 32  # LSH bands
DEFAULT_SIMILARITY_THRESHOLD = 0.85  # Jaccard threshold

# Auto-switch thresholds
THRESHOLD_PAIRWISE = 10_000  # Below: O(n) pairwise
THRESHOLD_BUCKETING = 50_000  # Below: SimHash bucketing, above: MinHash LSH

# Feature flag default
DEFAULT_MINHASH_LSH_ENABLED = False  # Disabled until M4 stabilization


# =============================================================================
# Enums
# =============================================================================


class DeduplicationStrategy(Enum):
    """Deduplication strategy types."""

    SIMHASH_PAIRWISE = "simhash_pairwise"
    SIMHASH_BUCKETING = "simhash_bucketing"
    MINHASH_LSH = "minhash_lsh"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class LSHCandidate:
    """Candidate duplicate from LSH lookup.

    Attributes:
        event_id: ID of candidate event.
        bands_matched: Number of bands where signatures matched.
        estimated_similarity: Estimated Jaccard similarity from band matches.
    """

    event_id: str
    bands_matched: int
    estimated_similarity: float


@dataclass
class MinHashConfig:
    """Configuration for MinHash LSH.

    Attributes:
        num_hashes: Total hash functions (default 128).
        num_bands: Number of LSH bands (default 32).
        similarity_threshold: Jaccard similarity threshold (default 0.85).
        hash_seed: Seed for reproducible hashing (default 42).
        enabled: Whether MinHash LSH is enabled.
    """

    num_hashes: int = DEFAULT_NUM_HASHES
    num_bands: int = DEFAULT_NUM_BANDS
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    hash_seed: int = 42
    enabled: bool = DEFAULT_MINHASH_LSH_ENABLED

    def __post_init__(self) -> None:
        """Validate configuration."""
        self.validate()

    def validate(self) -> None:
        """Validate configuration values."""
        if self.num_hashes <= 0:
            raise ValueError(f"num_hashes must be positive: {self.num_hashes}")
        if self.num_bands <= 0:
            raise ValueError(f"num_bands must be positive: {self.num_bands}")
        if self.num_hashes % self.num_bands != 0:
            raise ValueError(
                f"num_hashes ({self.num_hashes}) must be divisible by "
                f"num_bands ({self.num_bands})"
            )
        if not (0.0 < self.similarity_threshold <= 1.0):
            raise ValueError(f"similarity_threshold must be in (0, 1]: {self.similarity_threshold}")

    @property
    def rows_per_band(self) -> int:
        """Number of rows per band."""
        return self.num_hashes // self.num_bands


@dataclass
class AdaptiveStrategyConfig:
    """Configuration for adaptive deduplication strategy.

    Attributes:
        pairwise_threshold: Switch to bucketing above this count.
        bucketing_threshold: Switch to LSH above this count.
        lsh_enabled: Feature flag for MinHash LSH.
    """

    pairwise_threshold: int = THRESHOLD_PAIRWISE
    bucketing_threshold: int = THRESHOLD_BUCKETING
    lsh_enabled: bool = DEFAULT_MINHASH_LSH_ENABLED

    def validate(self) -> None:
        """Validate thresholds."""
        if self.pairwise_threshold <= 0:
            raise ValueError(f"pairwise_threshold must be positive: {self.pairwise_threshold}")
        if self.bucketing_threshold <= self.pairwise_threshold:
            raise ValueError(
                f"bucketing_threshold ({self.bucketing_threshold}) must be > "
                f"pairwise_threshold ({self.pairwise_threshold})"
            )


@dataclass
class LSHIndexStats:
    """Statistics for LSH index.

    Attributes:
        event_count: Number of events indexed.
        bucket_count: Number of unique buckets.
        avg_bucket_size: Average events per bucket.
        strategy: Current deduplication strategy.
    """

    event_count: int
    bucket_count: int
    avg_bucket_size: float
    strategy: DeduplicationStrategy


# =============================================================================
# Protocols
# =============================================================================


class DeduplicatorProtocol(Protocol):
    """Protocol for deduplicator implementations."""

    async def find_duplicates(
        self,
        text: str,
        embedding: np.ndarray,
        space_id: str,
    ) -> List[Tuple[str, float]]:
        """Find duplicate candidates."""
        ...


# =============================================================================
# MinHashLSH Class
# =============================================================================


class MinHashLSH:
    """
    MinHash with Locality-Sensitive Hashing for sub-linear deduplication.

    Scientific Basis: Broder (1997) - Near-duplicate detection

    Features:
    - 128 hash functions for precision
    - 32 bands for LSH indexing
    - O(log n) candidate retrieval
    - Auto-switch based on event count

    Usage:
        lsh = MinHashLSH()
        signature = lsh.compute_minhash("Sample text")
        lsh.index_event("event_123", signature)
        candidates = lsh.find_candidates(new_signature)
    """

    def __init__(
        self,
        config: Optional[MinHashConfig] = None,
    ) -> None:
        """
        Initialize MinHashLSH.

        Args:
            config: Configuration for MinHash parameters.
        """
        self.config = config or MinHashConfig()

        # LSH index: (band_idx, band_hash) -> [event_ids]
        self._lsh_index: Dict[Tuple[int, int], List[str]] = defaultdict(list)

        # Store signatures for similarity computation
        self._signatures: Dict[str, np.ndarray] = {}

        # Metrics tracking
        self._query_count = 0
        self._total_candidates_found = 0

    def compute_minhash(self, text: str) -> np.ndarray:
        """
        Compute MinHash signature (128 hash values by default).

        Uses k-shingling with 3-grams and independent hash functions.

        Args:
            text: Input text to hash.

        Returns:
            NumPy array of hash values (uint64).
        """
        # Tokenize to 3-grams
        shingles = self._tokenize_shingles(text, k=3)

        if not shingles:
            return np.zeros(self.config.num_hashes, dtype=np.uint64)

        # Initialize signature with max uint64
        signature = np.full(
            self.config.num_hashes,
            np.iinfo(np.uint64).max,
            dtype=np.uint64,
        )

        for shingle in shingles:
            for i in range(self.config.num_hashes):
                # Different hash per position using seed
                h = self._hash_shingle(shingle, seed=i)
                signature[i] = min(signature[i], h)

        return signature

    def _tokenize_shingles(self, text: str, k: int = 3) -> Set[str]:
        """
        Extract k-gram shingles from text.

        Uses character-level 3-grams for robustness.

        Args:
            text: Input text.
            k: Shingle size (default 3).

        Returns:
            Set of k-gram strings.
        """
        text = text.lower().strip()
        if len(text) < k:
            return {text} if text else set()
        return {text[i : i + k] for i in range(len(text) - k + 1)}

    def _hash_shingle(self, shingle: str, seed: int) -> int:
        """
        Hash shingle with seed for independent hash functions.

        Uses SHA256 for consistency with existing pattern_separate.py.

        Args:
            shingle: Text shingle to hash.
            seed: Seed for this hash function.

        Returns:
            64-bit unsigned hash value.
        """
        # Combine seed and shingle for unique hash
        data = f"{self.config.hash_seed}:{seed}:{shingle}".encode("utf-8")
        h = hashlib.sha256(data).digest()
        return int.from_bytes(h[:8], byteorder="big", signed=False)

    def hash_bands(self, signature: np.ndarray) -> List[int]:
        """
        Hash signature into bands for LSH.

        Partitions signature into num_bands bands, each with rows_per_band rows.

        Args:
            signature: MinHash signature array.

        Returns:
            List of band hashes (one per band).
        """
        band_hashes: List[int] = []
        rows_per_band = self.config.rows_per_band

        for band_idx in range(self.config.num_bands):
            start = band_idx * rows_per_band
            end = start + rows_per_band
            band = signature[start:end]

            # Hash the band values together
            band_hash = hash(tuple(band.tolist()))
            band_hashes.append(band_hash)

        return band_hashes

    def index_event(self, event_id: str, signature: np.ndarray) -> None:
        """
        Add event to LSH index.

        Called when event is processed by P02/P03.

        Args:
            event_id: Unique event identifier.
            signature: MinHash signature for event.
        """
        # Store signature
        self._signatures[event_id] = signature.copy()

        # Index into bands
        band_hashes = self.hash_bands(signature)
        for band_idx, band_hash in enumerate(band_hashes):
            key = (band_idx, band_hash)
            if event_id not in self._lsh_index[key]:
                self._lsh_index[key].append(event_id)

    def find_candidates(
        self,
        signature: np.ndarray,
        exclude_event_id: Optional[str] = None,
    ) -> List[LSHCandidate]:
        """
        Find candidate duplicates using LSH.

        O(log n) complexity via band-based indexing.

        Args:
            signature: Query signature.
            exclude_event_id: Event ID to exclude from results (self).

        Returns:
            List of candidates sorted by bands matched (descending).
        """
        self._query_count += 1

        band_hashes = self.hash_bands(signature)

        # Count bands matched per event
        match_counts: Dict[str, int] = defaultdict(int)

        for band_idx, band_hash in enumerate(band_hashes):
            key = (band_idx, band_hash)
            for event_id in self._lsh_index.get(key, []):
                if event_id != exclude_event_id:
                    match_counts[event_id] += 1

        # Convert to candidates with estimated similarity
        candidates: List[LSHCandidate] = []
        for event_id, bands_matched in match_counts.items():
            estimated_sim = self._estimate_similarity(bands_matched)
            candidates.append(
                LSHCandidate(
                    event_id=event_id,
                    bands_matched=bands_matched,
                    estimated_similarity=estimated_sim,
                )
            )

        # Sort by bands matched (descending)
        candidates.sort(key=lambda c: c.bands_matched, reverse=True)

        self._total_candidates_found += len(candidates)

        return candidates

    def _estimate_similarity(self, bands_matched: int) -> float:
        """
        Estimate Jaccard similarity from band match count.

        Based on LSH probability formula:
        P(at least 1 band match) = 1 - (1 - s^r)^b
        Where s = similarity, r = rows_per_band, b = num_bands

        Args:
            bands_matched: Number of bands matched.

        Returns:
            Estimated similarity in [0, 1].
        """
        if bands_matched == 0:
            return 0.0
        if bands_matched == self.config.num_bands:
            return 1.0

        # Approximate similarity from band ratio
        ratio = bands_matched / self.config.num_bands
        # Invert the LSH probability formula approximately
        return ratio ** (1 / self.config.rows_per_band)

    def compute_exact_similarity(
        self,
        sig1: np.ndarray,
        sig2: np.ndarray,
    ) -> float:
        """
        Compute exact Jaccard similarity between two signatures.

        Used after LSH candidate retrieval for verification.

        Args:
            sig1: First MinHash signature.
            sig2: Second MinHash signature.

        Returns:
            Jaccard similarity estimate in [0, 1].
        """
        if len(sig1) != len(sig2):
            raise ValueError(f"Signature lengths must match: {len(sig1)} vs {len(sig2)}")
        matches = np.sum(sig1 == sig2)
        return float(matches / len(sig1))

    def get_stored_signature(self, event_id: str) -> Optional[np.ndarray]:
        """
        Get stored signature for an event.

        Args:
            event_id: Event identifier.

        Returns:
            Stored signature or None if not found.
        """
        return self._signatures.get(event_id)

    def remove_event(self, event_id: str) -> bool:
        """
        Remove event from LSH index.

        Called on archive/tombstone.

        Args:
            event_id: Event identifier to remove.

        Returns:
            True if event was found and removed.
        """
        if event_id not in self._signatures:
            return False

        signature = self._signatures[event_id]
        band_hashes = self.hash_bands(signature)

        for band_idx, band_hash in enumerate(band_hashes):
            key = (band_idx, band_hash)
            if event_id in self._lsh_index.get(key, []):
                self._lsh_index[key].remove(event_id)
                # Clean up empty buckets
                if not self._lsh_index[key]:
                    del self._lsh_index[key]

        del self._signatures[event_id]
        return True

    def get_stats(self) -> LSHIndexStats:
        """
        Get current index statistics.

        Returns:
            LSHIndexStats with current state.
        """
        event_count = len(self._signatures)
        bucket_count = len(self._lsh_index)

        if bucket_count > 0:
            total_entries = sum(len(v) for v in self._lsh_index.values())
            avg_bucket_size = total_entries / bucket_count
        else:
            avg_bucket_size = 0.0

        return LSHIndexStats(
            event_count=event_count,
            bucket_count=bucket_count,
            avg_bucket_size=avg_bucket_size,
            strategy=DeduplicationStrategy.MINHASH_LSH,
        )

    def clear(self) -> None:
        """Clear all indexed events."""
        self._lsh_index.clear()
        self._signatures.clear()
        self._query_count = 0
        self._total_candidates_found = 0

    @property
    def event_count(self) -> int:
        """Number of indexed events."""
        return len(self._signatures)

    @property
    def query_count(self) -> int:
        """Number of queries performed."""
        return self._query_count

    @property
    def avg_candidates_per_query(self) -> float:
        """Average candidates found per query."""
        if self._query_count == 0:
            return 0.0
        return self._total_candidates_found / self._query_count


# =============================================================================
# AdaptiveDeduplicationStrategy Class
# =============================================================================


class AdaptiveDeduplicationStrategy:
    """
    Auto-switch between deduplication strategies based on event count.

    Spec: Dossier Appendix C.4.1.3

    Thresholds:
    - < 10,000: SimHash pairwise O(n)
    - 10K-50K: SimHash bucketing O(n/b)
    - > 50,000: MinHash LSH O(log n)

    Usage:
        strategy = AdaptiveDeduplicationStrategy(
            simhash_dedup=two_stage_dedup,
            minhash_lsh=lsh_instance,
        )
        strategy.update_event_count(60000)
        assert strategy.get_strategy() == DeduplicationStrategy.MINHASH_LSH
    """

    def __init__(
        self,
        minhash_lsh: MinHashLSH,
        config: Optional[AdaptiveStrategyConfig] = None,
        simhash_dedup: Optional[DeduplicatorProtocol] = None,
    ) -> None:
        """
        Initialize AdaptiveDeduplicationStrategy.

        Args:
            minhash_lsh: MinHashLSH instance for high-volume spaces.
            config: Configuration for thresholds.
            simhash_dedup: TwoStageDeduplicator for lower volumes.
        """
        self.minhash_lsh = minhash_lsh
        self.config = config or AdaptiveStrategyConfig()
        self.simhash_dedup = simhash_dedup

        self._event_count = 0
        self._strategy_switches: List[Tuple[int, str, str]] = []

    def get_strategy(self) -> DeduplicationStrategy:
        """
        Return current strategy based on event count.

        Returns:
            Current DeduplicationStrategy.
        """
        if not self.config.lsh_enabled:
            # LSH disabled - use bucketing at high counts
            if self._event_count < self.config.pairwise_threshold:
                return DeduplicationStrategy.SIMHASH_PAIRWISE
            return DeduplicationStrategy.SIMHASH_BUCKETING

        if self._event_count < self.config.pairwise_threshold:
            return DeduplicationStrategy.SIMHASH_PAIRWISE
        elif self._event_count < self.config.bucketing_threshold:
            return DeduplicationStrategy.SIMHASH_BUCKETING
        else:
            return DeduplicationStrategy.MINHASH_LSH

    def update_event_count(self, count: int) -> Optional[Tuple[str, str]]:
        """
        Update event count and check for strategy switch.

        Args:
            count: New event count.

        Returns:
            Tuple of (old_strategy, new_strategy) if switch occurred.
        """
        old_strategy = self.get_strategy()
        self._event_count = count
        new_strategy = self.get_strategy()

        if old_strategy != new_strategy:
            logger.info(
                f"Strategy switch: {old_strategy.value} -> {new_strategy.value} "
                f"at {count} events"
            )
            self._strategy_switches.append((count, old_strategy.value, new_strategy.value))
            return (old_strategy.value, new_strategy.value)

        return None

    async def find_duplicates(
        self,
        text: str,
        embedding: np.ndarray,
        space_id: str,
        event_id: Optional[str] = None,
    ) -> List[Tuple[str, float]]:
        """
        Find duplicates using appropriate strategy.

        Args:
            text: Event text content.
            embedding: Event embedding vector.
            space_id: Space identifier.
            event_id: Current event ID (to exclude from results).

        Returns:
            List of (event_id, similarity) tuples.
        """
        strategy = self.get_strategy()

        if strategy == DeduplicationStrategy.MINHASH_LSH:
            return await self._find_with_minhash_lsh(text, event_id)
        elif self.simhash_dedup is not None:
            # Delegate to SimHash deduplicator
            return await self.simhash_dedup.find_duplicates(text, embedding, space_id)
        else:
            # No deduplicator available
            return []

    async def _find_with_minhash_lsh(
        self,
        text: str,
        exclude_event_id: Optional[str] = None,
    ) -> List[Tuple[str, float]]:
        """
        Find duplicates using MinHash LSH.

        Args:
            text: Event text.
            exclude_event_id: Event ID to exclude.

        Returns:
            List of verified (event_id, similarity) tuples.
        """
        signature = self.minhash_lsh.compute_minhash(text)
        candidates = self.minhash_lsh.find_candidates(signature, exclude_event_id=exclude_event_id)

        # Verify top candidates with exact similarity
        verified: List[Tuple[str, float]] = []
        threshold = self.minhash_lsh.config.similarity_threshold

        for candidate in candidates[:10]:  # Top 10
            stored_sig = self.minhash_lsh.get_stored_signature(candidate.event_id)
            if stored_sig is not None:
                exact_sim = self.minhash_lsh.compute_exact_similarity(signature, stored_sig)
                if exact_sim >= threshold:
                    verified.append((candidate.event_id, exact_sim))

        return verified

    @property
    def event_count(self) -> int:
        """Current event count."""
        return self._event_count

    @property
    def strategy_switches(self) -> List[Tuple[int, str, str]]:
        """History of strategy switches (count, old, new)."""
        return list(self._strategy_switches)


# =============================================================================
# Metrics Collector
# =============================================================================


class MinHashMetricsCollector:
    """Collect MinHash LSH metrics.

    Metrics (from Dossier):
    - p03_dedup_strategy_active: Current strategy
    - p03_lsh_index_size: Events in LSH index
    - p03_lsh_candidates_found: Candidates per query
    - p03_lsh_latency_ms: LSH lookup latency
    - p03_strategy_switch_count: Strategy switches
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self._strategy_switches: Dict[str, int] = {}
        self._query_latencies: List[float] = []
        self._candidates_per_query: List[int] = []

    def record_strategy_switch(self, from_strategy: str, to_strategy: str) -> None:
        """Record strategy switch."""
        key = f"{from_strategy}:{to_strategy}"
        self._strategy_switches[key] = self._strategy_switches.get(key, 0) + 1

    def record_query_latency(self, latency_ms: float) -> None:
        """Record query latency."""
        self._query_latencies.append(latency_ms)

    def record_candidates_found(self, count: int) -> None:
        """Record candidates found."""
        self._candidates_per_query.append(count)

    def get_switch_count(self, from_strategy: str, to_strategy: str) -> int:
        """Get count of specific switch."""
        key = f"{from_strategy}:{to_strategy}"
        return self._strategy_switches.get(key, 0)

    def get_avg_latency_ms(self) -> float:
        """Get average query latency."""
        if not self._query_latencies:
            return 0.0
        return sum(self._query_latencies) / len(self._query_latencies)

    def get_avg_candidates(self) -> float:
        """Get average candidates per query."""
        if not self._candidates_per_query:
            return 0.0
        return sum(self._candidates_per_query) / len(self._candidates_per_query)

    def reset(self) -> None:
        """Reset all metrics."""
        self._strategy_switches.clear()
        self._query_latencies.clear()
        self._candidates_per_query.clear()


# =============================================================================
# Utility Functions
# =============================================================================


def estimate_lsh_threshold(
    num_bands: int,
    rows_per_band: int,
    target_similarity: float = 0.85,
) -> float:
    """
    Estimate probability of match at target similarity.

    P(match) = 1 - (1 - s^r)^b
    where s = similarity, r = rows_per_band, b = num_bands

    Args:
        num_bands: Number of LSH bands.
        rows_per_band: Rows per band.
        target_similarity: Target Jaccard similarity.

    Returns:
        Probability of finding match at target similarity.
    """
    s = target_similarity
    r = rows_per_band
    b = num_bands
    return 1.0 - (1.0 - s**r) ** b


def compute_jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """
    Compute exact Jaccard similarity between two sets.

    Args:
        set1: First set.
        set2: Second set.

    Returns:
        Jaccard similarity in [0, 1].
    """
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union
