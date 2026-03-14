"""
CompositeDistance - Semantic + temporal distance for episodic clustering.

This module implements the composite distance metric that combines
semantic similarity (cosine) and temporal proximity for density-based clustering.

Spec Reference:
    - Dossier Appendix C.3.1: Clustering distance algorithm
    - M4_EXECUTION.md Issue 4.2.1

Formula:
    distance = (1 - temporal_weight) × cosine_distance(emb_a, emb_b)
             + temporal_weight × normalized_time_distance(ts_a, ts_b)

Where:
    - cosine_distance = 1 - cosine_similarity
    - normalized_time_distance = min(1.0, abs(ts_a - ts_b) / max_temporal_gap_ms)
    - max_temporal_gap_ms = 4 hours = 14,400,000 ms

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Milliseconds in one hour
MS_PER_HOUR = 3_600_000

# Default max temporal gap (4 hours in ms)
DEFAULT_MAX_TEMPORAL_GAP_MS = 4 * MS_PER_HOUR  # 14,400,000

# Expected embedding dimension
EMBEDDING_DIM = 768


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class ClusteringDistanceParams:
    """
    Parameters for density-based clustering distance computation.

    Defaults optimized for UltraBERT L2-normalized 768-dim embeddings:
        - eps: 0.15 (max composite distance to cluster - tighter for L2-normalized embeddings)
        - min_samples: 2 (minimum events for core point)
        - temporal_weight: 0.3 (how much time affects distance)
        - max_temporal_gap_hours: 4.0 (hard limit - events further apart cannot cluster)

    Note: UltraBERT produces L2-normalized embeddings with typical cosine distances
    in the range 0.10-0.30 for different topics. With temporal_weight=0.3, composite
    distances are ~0.07-0.21, so eps=0.15 creates meaningful clusters.

    Epic 3.2.1: Log-temporal compression option. When use_log_temporal=True, the
    temporal distance uses d = log(1 + diff/tau) / log(1 + max_gap/tau) instead
    of the linear min(1.0, diff/max_gap). This compresses far gaps and
    differentiates near-time events more meaningfully.

    Configuration Keys:
        - P03_CLUSTERING_EPS: [0.10, 0.40] range
        - P03_CLUSTERING_TEMPORAL_WEIGHT: [0.1, 0.5] range
        - P03_CLUSTERING_MAX_TEMPORAL_GAP_HOURS: [1.0, 8.0] range
    """

    eps: float = 0.15  # Tighter default for UltraBERT L2-normalized embeddings
    min_samples: int = 2
    temporal_weight: float = 0.3
    max_temporal_gap_hours: float = 4.0

    # Epic 3.2.1: Log-temporal compression
    use_log_temporal: bool = True
    log_temporal_tau_ms: int = 1_800_000  # 30 min half-life (from research)

    @property
    def max_temporal_gap_ms(self) -> int:
        """Max temporal gap in milliseconds."""
        return int(self.max_temporal_gap_hours * MS_PER_HOUR)

    @property
    def semantic_weight(self) -> float:
        """Weight for semantic (cosine) distance component."""
        return 1.0 - self.temporal_weight

    def validate(self) -> None:
        """Validate parameter ranges."""
        if not 0.0 < self.eps <= 2.0:
            raise ValueError(f"eps must be in (0, 2], got {self.eps}")
        if self.min_samples < 1:
            raise ValueError(f"min_samples must be >= 1, got {self.min_samples}")
        if not 0.0 <= self.temporal_weight <= 1.0:
            raise ValueError(f"temporal_weight must be in [0, 1], got {self.temporal_weight}")
        if self.max_temporal_gap_hours <= 0:
            raise ValueError(
                f"max_temporal_gap_hours must be > 0, got {self.max_temporal_gap_hours}"
            )
        if self.log_temporal_tau_ms <= 0:
            raise ValueError(f"log_temporal_tau_ms must be > 0, got {self.log_temporal_tau_ms}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "eps": self.eps,
            "min_samples": self.min_samples,
            "temporal_weight": self.temporal_weight,
            "max_temporal_gap_hours": self.max_temporal_gap_hours,
            "use_log_temporal": self.use_log_temporal,
            "log_temporal_tau_ms": self.log_temporal_tau_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClusteringDistanceParams":
        """Create from dictionary."""
        return cls(
            eps=data.get("eps", 0.15),
            min_samples=data.get("min_samples", 2),
            temporal_weight=data.get("temporal_weight", 0.3),
            max_temporal_gap_hours=data.get("max_temporal_gap_hours", 4.0),
            use_log_temporal=data.get("use_log_temporal", True),
            log_temporal_tau_ms=data.get("log_temporal_tau_ms", 1_800_000),
        )


# Backward-compatibility alias (will be removed after Epic 2.1.5)
DBSCANParams = ClusteringDistanceParams


# =============================================================================
# Ensemble Distance Configuration (Epic 3.1 -- Issue 3.1.1)
# =============================================================================


class FallbackPolicy(Enum):
    """Policy for handling missing dimension signals.

    REDISTRIBUTE: confidence=0 removes dimension from denominator (bagging).
    NEUTRAL: contribute neutral distance (0.5) with configured confidence.
    """

    REDISTRIBUTE = "redistribute"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class EnsembleDistanceConfig:
    """Confidence-weighted 6D ensemble distance configuration.

    Proven defaults from R2 Phase 3 Research (ens_fuzzy_narrative_v10):
        w_semantic=0.45, w_temporal=0.25, w_narrative=0.30
        w_spatial=0.0, w_social=0.0, w_affective=0.0

    Core formula:
        d = sum(w_i * conf_i * d_i) / sum(w_i * conf_i)

    When a dimension has confidence=0, its weight is redistributed
    to dimensions with real signals (bagging principle).

    Spec Reference:
        - R2_EPISODIC_INTEGRATION_EPIC_PLAN.md Epic 3.1
        - R2_RESEARCH_FINAL.md Section 2.2
    """

    # --- Dimension weights (active weights should sum to ~1.0) ---
    w_semantic: float = 0.45
    w_temporal: float = 0.25
    w_narrative: float = 0.30
    w_spatial: float = 0.0
    w_social: float = 0.0
    w_affective: float = 0.0

    # --- Temporal ---
    use_log_temporal: bool = True
    log_temporal_tau_ms: int = 1_800_000  # 30 min half-life
    max_temporal_gap_ms: int = 14_400_000  # 4 hours
    hard_temporal_cutoff: bool = True

    # --- Narrative fallback chain (Issue 3.1.5) ---
    thread_exact_confidence: float = 1.0
    thread_semantic_same_threshold: float = 0.78
    thread_semantic_fuzzy_threshold: float = 0.60
    thread_fuzzy_confidence: float = 0.7
    thread_diff_confidence: float = 0.9
    goal_exact_confidence: float = 0.6
    goal_diff_confidence: float = 0.4
    goal_one_missing_confidence: float = 0.2
    narrative_miss_confidence: float = 0.0
    narrative_same_thread: float = 0.0
    narrative_fuzzy_thread: float = 0.15
    narrative_diff_thread: float = 1.0
    narrative_same_goal: float = 0.1
    narrative_diff_goal: float = 0.85
    narrative_one_missing_goal: float = 0.5
    narrative_miss_distance: float = 0.5

    # --- Narrative short-circuit (Issue 3.1.5) ---
    shortcircuit: bool = True
    shortcircuit_cap: float = 0.20
    shortcircuit_min_confidence: float = 0.7

    # --- Semantic micro-adjustment ---
    activity_type_micro_adjust: bool = False
    activity_same_factor: float = 0.85
    activity_diff_factor: float = 1.10

    # --- Spatial (Issue 3.1.2) ---
    spatial_same_place: float = 0.0
    spatial_diff_place: float = 1.0
    spatial_same_confidence: float = 0.9
    spatial_diff_confidence: float = 0.9
    spatial_hierarchy_confidence: float = 0.5
    spatial_miss_confidence: float = 0.0

    # --- Social (Issue 3.1.3) ---
    social_jaccard_confidence: float = 0.8
    social_context_confidence: float = 0.5
    social_solo_confidence: float = 0.4
    social_miss_confidence: float = 0.0

    # --- Affective (Issue 3.1.4) ---
    affective_present_confidence: float = 0.6
    affective_miss_confidence: float = 0.0

    # --- Fallback policy ---
    fallback_policy: FallbackPolicy = FallbackPolicy.REDISTRIBUTE

    # --- Temporal quality tiers (Epic 3.2.2) ---
    # Confidence for temporal dimension based on timestamp provenance.
    # Conservative defaults: all >= 0.5 until empirical data available.
    # tq_unknown = 1.0: when no temporal_source is set, assume high quality
    # (backward-compatible with pre-3.2.2 events that lack temporal_source).
    tq_mw_resolved: float = 1.0
    tq_conversation_anchor_ms: float = 1.0
    tq_event_time_utc: float = 0.9
    tq_created_at: float = 0.7
    tq_envelope_ts: float = 0.5
    tq_unknown: float = 1.0

    @property
    def weight_sum(self) -> float:
        """Sum of all dimension weights."""
        return (
            self.w_semantic
            + self.w_temporal
            + self.w_narrative
            + self.w_spatial
            + self.w_social
            + self.w_affective
        )

    def validate(self) -> None:
        """Validate configuration ranges."""
        for name, val in [
            ("w_semantic", self.w_semantic),
            ("w_temporal", self.w_temporal),
            ("w_narrative", self.w_narrative),
            ("w_spatial", self.w_spatial),
            ("w_social", self.w_social),
            ("w_affective", self.w_affective),
        ]:
            if val < 0.0:
                raise ValueError(f"{name} must be >= 0, got {val}")
        if self.weight_sum <= 0:
            raise ValueError(f"At least one dimension weight must be > 0, sum={self.weight_sum}")
        if self.max_temporal_gap_ms <= 0:
            raise ValueError(f"max_temporal_gap_ms must be > 0, got {self.max_temporal_gap_ms}")
        if not 0.0 <= self.shortcircuit_cap <= 1.0:
            raise ValueError(f"shortcircuit_cap must be in [0, 1], got {self.shortcircuit_cap}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "w_semantic": self.w_semantic,
            "w_temporal": self.w_temporal,
            "w_narrative": self.w_narrative,
            "w_spatial": self.w_spatial,
            "w_social": self.w_social,
            "w_affective": self.w_affective,
            "use_log_temporal": self.use_log_temporal,
            "log_temporal_tau_ms": self.log_temporal_tau_ms,
            "max_temporal_gap_ms": self.max_temporal_gap_ms,
            "hard_temporal_cutoff": self.hard_temporal_cutoff,
            "shortcircuit": self.shortcircuit,
            "shortcircuit_cap": self.shortcircuit_cap,
            "shortcircuit_min_confidence": self.shortcircuit_min_confidence,
            "fallback_policy": self.fallback_policy.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnsembleDistanceConfig":
        """Deserialize from dictionary."""
        data = dict(data)  # shallow copy to avoid mutating caller
        policy_str = data.pop("fallback_policy", "redistribute")
        policy = FallbackPolicy(policy_str) if isinstance(policy_str, str) else policy_str
        return cls(fallback_policy=policy, **data)


# =============================================================================
# Event Protocol (Extended for 6D -- Issue 3.1.0)
# =============================================================================


class EventLike(Protocol):
    """
    Protocol for event objects usable with distance computation.

    Core fields (required for all distance modes):
        event_id, timestamp, embedding_768

    Extended fields (Optional, for 6D ensemble distance -- Epic 3.1):
        Spatial: place_id, geohash_6, location_hierarchy_json
        Social: participants_json, social_context, social_intimacy,
                num_participants, is_solo_event
        Affective: affect_valence, affect_arousal, affect_dominance,
                   surprise_level
        Narrative: narrative_thread_id, goal_context, intent_type
        Support: activity_type, sentiment_score

    All Optional fields return None when the signal is unavailable.
    Distance functions handle None via confidence-weighted fallback chains.

    Implementations: P03EventState, EventAdapter, ClusterableEvent.
    """

    @property
    def event_id(self) -> str:
        """Unique event identifier."""
        ...

    @property
    def timestamp(self) -> int:
        """Event timestamp in milliseconds since epoch."""
        ...

    @property
    def embedding_768(self) -> Optional[List[float]]:
        """768-dimensional embedding vector."""
        ...

    # --- Spatial (Issue 3.1.2) ---

    @property
    def place_id(self) -> Optional[str]: ...

    @property
    def geohash_6(self) -> Optional[str]: ...

    @property
    def location_hierarchy_json(self) -> Optional[str]: ...

    # --- Social (Issue 3.1.3) ---

    @property
    def participants_json(self) -> Optional[str]: ...

    @property
    def social_context(self) -> Optional[str]: ...

    @property
    def social_intimacy(self) -> Optional[float]: ...

    @property
    def num_participants(self) -> Optional[int]: ...

    @property
    def is_solo_event(self) -> Optional[bool]: ...

    # --- Affective (Issue 3.1.4) ---

    @property
    def affect_valence(self) -> Optional[float]: ...

    @property
    def affect_arousal(self) -> Optional[float]: ...

    @property
    def affect_dominance(self) -> Optional[float]: ...

    @property
    def surprise_level(self) -> Optional[float]: ...

    # --- Narrative (Issue 3.1.5) ---

    @property
    def narrative_thread_id(self) -> Optional[str]: ...

    @property
    def goal_context(self) -> Optional[str]: ...

    @property
    def intent_type(self) -> Optional[str]: ...

    # --- Support signals ---

    @property
    def activity_type(self) -> Optional[str]: ...

    @property
    def sentiment_score(self) -> Optional[float]: ...

    # --- Temporal quality (Epic 3.2.2) ---

    @property
    def temporal_source(self) -> Optional[str]: ...

    # --- Temporal context (Epic 3.6.0) ---

    @property
    def temporal_links_json(self) -> Optional[str]: ...

    @property
    def time_of_day_bucket(self) -> Optional[str]: ...

    @property
    def circadian_slot(self) -> Optional[str]: ...

    @property
    def is_weekend(self) -> Optional[bool]: ...

    @property
    def extraction_sequence(self) -> int: ...


# =============================================================================
# CompositeDistance Class (Legacy 2D)
# =============================================================================


class CompositeDistance:
    """
    Composite distance for episodic clustering.

    Combines semantic similarity (cosine) and temporal proximity
    to create a unified distance metric for density-based clustering.

    Lower distance = more similar = should cluster together.

    Distance Interpretation (from Dossier C.3.1):
        - 0.0: Identical (same embedding, same time)
        - 0.0-0.25: Very similar (default eps threshold)
        - 0.25-0.50: Moderately similar
        - 0.50-1.0: Dissimilar
        - >1.0: Very different
        - inf: Exceeds temporal gap (cannot cluster)

    Scientific Basis:
        Temporal binding in episodic memory (Tulving, 2002):
        Events occurring close together in time are more likely
        to be part of the same episode.

    Usage:
        params = ClusteringDistanceParams(eps=0.25, temporal_weight=0.3)
        distance = CompositeDistance(params)

        dist = distance.compute(event_a, event_b)
        matrix = distance.build_distance_matrix(events)
    """

    def __init__(self, params: Optional[ClusteringDistanceParams] = None):
        """
        Initialize CompositeDistance.

        Args:
            params: Clustering distance parameters. Uses defaults if None.
        """
        self.params = params or ClusteringDistanceParams()
        self.params.validate()

    def compute(
        self,
        event_a: EventLike,
        event_b: EventLike,
    ) -> float:
        """
        Compute composite distance between two events.

        Formula:
            distance = (1 - temporal_weight) × cosine_distance
                     + temporal_weight × normalized_time_distance

        Args:
            event_a: First event with embedding_768 and timestamp
            event_b: Second event with embedding_768 and timestamp

        Returns:
            Distance in [0.0, inf). Events >max_gap apart return inf.

        Raises:
            ValueError: If either event lacks embedding_768
        """
        # Step 1: Check temporal hard limit
        time_diff_ms = abs(event_a.timestamp - event_b.timestamp)
        if time_diff_ms > self.params.max_temporal_gap_ms:
            return float("inf")  # Cannot cluster

        # Step 2: Validate embeddings exist
        if event_a.embedding_768 is None:
            raise ValueError(f"Event {event_a.event_id} has no embedding_768")
        if event_b.embedding_768 is None:
            raise ValueError(f"Event {event_b.event_id} has no embedding_768")

        # Step 3: Compute semantic distance (1 - cosine similarity)
        semantic_dist = self._cosine_distance(event_a.embedding_768, event_b.embedding_768)

        # Step 4: Compute normalized temporal distance
        temporal_dist = self._normalized_time_distance(time_diff_ms)

        # Step 5: Weighted combination
        composite = (
            self.params.semantic_weight * semantic_dist
            + self.params.temporal_weight * temporal_dist
        )

        return float(composite)

    def compute_from_arrays(
        self,
        embedding_a: np.ndarray,
        embedding_b: np.ndarray,
        timestamp_a: int,
        timestamp_b: int,
    ) -> float:
        """
        Compute composite distance from raw arrays and timestamps.

        Optimized path for batch processing that avoids object creation.

        Args:
            embedding_a: First embedding as numpy array
            embedding_b: Second embedding as numpy array
            timestamp_a: First timestamp (ms)
            timestamp_b: Second timestamp (ms)

        Returns:
            Distance in [0.0, inf)
        """
        # Temporal hard limit check
        time_diff_ms = abs(timestamp_a - timestamp_b)
        if time_diff_ms > self.params.max_temporal_gap_ms:
            return float("inf")

        # Semantic distance
        semantic_dist = self._cosine_distance_arrays(embedding_a, embedding_b)

        # Temporal distance
        temporal_dist = self._normalized_time_distance(time_diff_ms)

        # Weighted combination
        return float(
            self.params.semantic_weight * semantic_dist
            + self.params.temporal_weight * temporal_dist
        )

    def _cosine_distance(
        self,
        emb_a: List[float],
        emb_b: List[float],
    ) -> float:
        """
        Compute cosine distance between two embeddings.

        cosine_distance = 1 - cosine_similarity

        Assumes embeddings are L2-normalized (as UltraBERT produces).

        Args:
            emb_a: First embedding (768-dim)
            emb_b: Second embedding (768-dim)

        Returns:
            Cosine distance in [0.0, 2.0]
        """
        arr_a = np.asarray(emb_a, dtype=np.float32)
        arr_b = np.asarray(emb_b, dtype=np.float32)
        return self._cosine_distance_arrays(arr_a, arr_b)

    def _cosine_distance_arrays(
        self,
        arr_a: np.ndarray,
        arr_b: np.ndarray,
    ) -> float:
        """
        Compute cosine distance from numpy arrays.

        Args:
            arr_a: First embedding array
            arr_b: Second embedding array

        Returns:
            Cosine distance in [0.0, 2.0]
        """
        # Compute norms
        norm_a = np.linalg.norm(arr_a)
        norm_b = np.linalg.norm(arr_b)

        # Handle zero vectors
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 1.0  # Treat as orthogonal

        # Cosine similarity
        cosine_similarity = np.dot(arr_a, arr_b) / (norm_a * norm_b)

        # Clamp to [-1, 1] to handle floating point errors
        cosine_similarity = max(-1.0, min(1.0, cosine_similarity))

        # Distance = 1 - similarity
        return 1.0 - cosine_similarity

    def _normalized_time_distance(self, time_diff_ms: int) -> float:
        """
        Compute normalized temporal distance.

        Epic 3.2.1: Supports log-compressed and linear modes.

        Log-compressed (default):
            d = log(1 + diff/tau) / log(1 + max_gap/tau)
            Differentiates near-time events more than linear; compresses far gaps.

        Linear (legacy):
            d = min(1.0, diff / max_gap)

        Args:
            time_diff_ms: Absolute time difference in milliseconds

        Returns:
            Normalized distance in [0.0, 1.0]
        """
        if self.params.use_log_temporal:
            tau = self.params.log_temporal_tau_ms
            max_gap = self.params.max_temporal_gap_ms
            if max_gap <= 0 or tau <= 0:
                return 0.5
            d = math.log(1.0 + time_diff_ms / tau) / math.log(1.0 + max_gap / tau)
            return max(0.0, min(1.0, d))

        return min(1.0, time_diff_ms / self.params.max_temporal_gap_ms)

    def build_distance_matrix(
        self,
        events: Sequence[EventLike],
    ) -> np.ndarray:
        """
        Build pairwise distance matrix for DBSCAN.

        Complexity: O(n² × d) where n = events, d = embedding dim

        The matrix is symmetric: matrix[i,j] == matrix[j,i]
        Diagonal is zero: matrix[i,i] == 0.0

        Args:
            events: List of events with embedding_768 and timestamp

        Returns:
            n×n symmetric distance matrix (numpy array)

        Raises:
            ValueError: If any event lacks embedding_768
        """
        n = len(events)
        if n == 0:
            return np.zeros((0, 0), dtype=np.float32)

        # Pre-extract embeddings and timestamps for efficiency
        embeddings: List[np.ndarray] = []
        timestamps: List[int] = []

        for event in events:
            if event.embedding_768 is None:
                raise ValueError(f"Event {event.event_id} has no embedding_768")
            embeddings.append(np.asarray(event.embedding_768, dtype=np.float32))
            timestamps.append(event.timestamp)

        # Build symmetric distance matrix
        distances = np.zeros((n, n), dtype=np.float32)

        for i in range(n):
            for j in range(i + 1, n):
                dist = self.compute_from_arrays(
                    embeddings[i],
                    embeddings[j],
                    timestamps[i],
                    timestamps[j],
                )
                distances[i, j] = dist
                distances[j, i] = dist

        return distances

    def get_semantic_distance(
        self,
        event_a: EventLike,
        event_b: EventLike,
    ) -> float:
        """
        Get only the semantic (cosine) distance component.

        Useful for debugging and analysis.

        Args:
            event_a: First event
            event_b: Second event

        Returns:
            Cosine distance in [0.0, 2.0]
        """
        if event_a.embedding_768 is None or event_b.embedding_768 is None:
            return float("inf")
        return self._cosine_distance(event_a.embedding_768, event_b.embedding_768)

    def get_temporal_distance(
        self,
        event_a: EventLike,
        event_b: EventLike,
    ) -> float:
        """
        Get only the temporal distance component.

        Useful for debugging and analysis.

        Args:
            event_a: First event
            event_b: Second event

        Returns:
            Normalized temporal distance in [0.0, 1.0] or inf if beyond limit
        """
        time_diff_ms = abs(event_a.timestamp - event_b.timestamp)
        if time_diff_ms > self.params.max_temporal_gap_ms:
            return float("inf")
        return self._normalized_time_distance(time_diff_ms)

    def would_cluster(
        self,
        event_a: EventLike,
        event_b: EventLike,
    ) -> bool:
        """
        Check if two events would cluster together with current eps.

        Args:
            event_a: First event
            event_b: Second event

        Returns:
            True if distance <= eps, False otherwise
        """
        dist = self.compute(event_a, event_b)
        return dist <= self.params.eps


# =============================================================================
# Thread Embedding Cache (Epic 3.1 -- Issue 3.1.5)
# =============================================================================


def _fuzzy_thread_similarity(a: str, b: str) -> float:
    """Combined fuzzy match: max(SequenceMatcher ratio, token Jaccard)."""
    seq_ratio = SequenceMatcher(None, a, b).ratio()
    tokens_a = set(a.lower().replace("_", " ").split())
    tokens_b = set(b.lower().replace("_", " ").split())
    union = tokens_a | tokens_b
    token_jaccard = len(tokens_a & tokens_b) / len(union) if union else 0.0
    return max(seq_ratio, token_jaccard)


class ThreadEmbeddingCache:
    """Lazy embedding cache for narrative thread ID slugs.

    Converts thread_id slugs to natural language phrases and embeds them
    using UltraBERT. Cached per process for efficiency.

    Falls back to fuzzy string matching when UltraBERT is unavailable.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Optional[List[float]]] = {}
        self._embed_fn: Any = None
        self._checked = False

    def _get_embed_fn(self) -> Any:
        if not self._checked:
            self._checked = True
            try:
                from k0.runtime.ultrabert_adapter import get_embedding, is_ultrabert_available

                if is_ultrabert_available():
                    self._embed_fn = get_embedding
            except Exception:
                pass
        return self._embed_fn

    @staticmethod
    def _slug_to_phrase(slug: str) -> str:
        return slug.replace("_", " ").strip()

    def get_embedding(self, thread_id: str) -> Optional[List[float]]:
        if thread_id not in self._cache:
            fn = self._get_embed_fn()
            if fn is None:
                self._cache[thread_id] = None
            else:
                self._cache[thread_id] = fn(self._slug_to_phrase(thread_id))
        return self._cache[thread_id]

    def similarity(self, a: str, b: str) -> float:
        """Cosine similarity between two thread slugs. Returns [0, 1]."""
        emb_a = self.get_embedding(a)
        emb_b = self.get_embedding(b)
        if emb_a is None or emb_b is None:
            return _fuzzy_thread_similarity(a, b)

        dot = sum(va * vb for va, vb in zip(emb_a, emb_b))
        norm_a = math.sqrt(sum(v * v for v in emb_a))
        norm_b = math.sqrt(sum(v * v for v in emb_b))
        if norm_a <= 1e-10 or norm_b <= 1e-10:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))


# Process-level singleton -- shared across all distance calls
_thread_cache = ThreadEmbeddingCache()


# =============================================================================
# Dimension Distance Functions (Epic 3.1 -- Issues 3.1.2-3.1.5)
# =============================================================================
# Each returns (distance, confidence) where confidence [0,1] indicates
# trust in this signal for THIS event pair.
# confidence=0 -> weight redistributed to other dimensions (bagging).
# =============================================================================


def _parse_json_list(raw: Optional[str]) -> List[str]:
    """Parse a JSON string expected to be a list of strings."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _temporal_quality_confidence(
    source_a: Optional[str],
    source_b: Optional[str],
    cfg: EnsembleDistanceConfig,
) -> float:
    """Map temporal_source provenance to a confidence value.

    Uses the MINIMUM of both events' quality tiers (conservative).
    If either timestamp is low-quality, the temporal dimension contributes
    less to the ensemble and weight redistributes to other dimensions.

    Tier mapping (from R2 plan Issue 3.2.2):
        mw_resolved / conversation_anchor_ms -> highest confidence
        event_time_utc -> high confidence
        created_at -> moderate confidence
        envelope_ts / now / unknown -> conservative floor

    Args:
        source_a: temporal_source of event A (None/"" -> unknown)
        source_b: temporal_source of event B (None/"" -> unknown)
        cfg: Ensemble config with tq_* quality tier parameters

    Returns:
        Confidence in [0, 1] for the temporal dimension.
    """
    _TIER_MAP = {
        "mw_resolved": cfg.tq_mw_resolved,
        "conversation_anchor_ms": cfg.tq_conversation_anchor_ms,
        "event_time_utc": cfg.tq_event_time_utc,
        "created_at": cfg.tq_created_at,
        "envelope_ts": cfg.tq_envelope_ts,
        "now": cfg.tq_unknown,
    }

    def _lookup(src: Optional[str]) -> float:
        if not src:
            return cfg.tq_unknown
        return _TIER_MAP.get(src, cfg.tq_unknown)

    return min(_lookup(source_a), _lookup(source_b))


def _cd_semantic(
    a: EventLike,
    b: EventLike,
    cfg: EnsembleDistanceConfig,
) -> Tuple[float, float]:
    """Semantic distance with confidence. Always available if embeddings exist."""
    if a.embedding_768 is None or b.embedding_768 is None:
        return 1.0, 0.3

    arr_a = np.asarray(a.embedding_768, dtype=np.float32)
    arr_b = np.asarray(b.embedding_768, dtype=np.float32)
    norm_a = float(np.linalg.norm(arr_a))
    norm_b = float(np.linalg.norm(arr_b))

    if norm_a < 1e-10 or norm_b < 1e-10:
        return 1.0, 0.3

    cosine_sim = float(np.dot(arr_a, arr_b) / (norm_a * norm_b))
    cosine_sim = max(-1.0, min(1.0, cosine_sim))
    d = 1.0 - cosine_sim

    if cfg.activity_type_micro_adjust:
        act_a = a.activity_type
        act_b = b.activity_type
        if act_a and act_b:
            if act_a == act_b:
                d *= cfg.activity_same_factor
            else:
                d *= cfg.activity_diff_factor

    return max(0.0, min(2.0, d)), 1.0


def _cd_temporal(
    a: EventLike,
    b: EventLike,
    cfg: EnsembleDistanceConfig,
) -> Tuple[float, float]:
    """Temporal distance with confidence, attenuated by timestamp quality.

    Epic 3.2.1: Uses log-compressed formula (default) or linear fallback.
    Epic 3.2.2: Confidence is attenuated by min(quality_a, quality_b)
                based on temporal_source provenance. Low-quality timestamps
                get lower confidence -> less weight in ensemble.
    """
    diff_ms = abs(a.timestamp - b.timestamp)

    if cfg.hard_temporal_cutoff and diff_ms > cfg.max_temporal_gap_ms:
        return float("inf"), 1.0

    # Compute temporal quality confidence from provenance
    ts_a = getattr(a, "temporal_source", None)
    ts_b = getattr(b, "temporal_source", None)
    quality_conf = _temporal_quality_confidence(ts_a, ts_b, cfg)

    if cfg.use_log_temporal:
        tau = cfg.log_temporal_tau_ms
        max_gap = cfg.max_temporal_gap_ms
        if max_gap <= 0 or tau <= 0:
            return 0.5, 0.3
        d = math.log(1.0 + diff_ms / tau) / math.log(1.0 + max_gap / tau)
        return max(0.0, min(1.0, d)), quality_conf

    d = min(1.0, diff_ms / cfg.max_temporal_gap_ms) if cfg.max_temporal_gap_ms > 0 else 0.5
    return d, quality_conf


def _cd_narrative(
    a: EventLike,
    b: EventLike,
    cfg: EnsembleDistanceConfig,
) -> Tuple[float, float]:
    """Narrative distance with multi-tier fallback chain.

    Chain (from R2 Research Phase 3):
      T1: thread exact match       -> d=0.0,  conf=1.0
      T2: thread semantic same     -> d=low,  conf=0.7
      T3: thread semantic fuzzy    -> d=mid,  conf~0.45
      T4: thread definite diff     -> d=1.0,  conf=0.9
      T5: goal exact match         -> d=0.1,  conf=0.6
      T6: goal different           -> d=0.85, conf=0.4
      T7: one has goal/thread      -> d=0.5,  conf=0.2
      MISS: no narrative signal    -> d=0.5,  conf=0.0 (excluded)
    """
    tid_a = a.narrative_thread_id
    tid_b = b.narrative_thread_id

    if tid_a and tid_b:
        if tid_a == tid_b:
            return cfg.narrative_same_thread, cfg.thread_exact_confidence

        sim = _thread_cache.similarity(tid_a, tid_b)

        if sim >= cfg.thread_semantic_same_threshold:
            d = 1.0 - sim
            return d, cfg.thread_fuzzy_confidence

        if sim >= cfg.thread_semantic_fuzzy_threshold:
            d = 1.0 - sim
            return d, cfg.thread_diff_confidence * 0.5

        return cfg.narrative_diff_thread, cfg.thread_diff_confidence

    goal_a = a.goal_context
    goal_b = b.goal_context

    if goal_a and goal_b:
        if goal_a == goal_b:
            return cfg.narrative_same_goal, cfg.goal_exact_confidence
        return cfg.narrative_diff_goal, cfg.goal_diff_confidence

    has_a = bool(tid_a or goal_a)
    has_b = bool(tid_b or goal_b)
    if has_a != has_b:
        return cfg.narrative_one_missing_goal, cfg.goal_one_missing_confidence

    return cfg.narrative_miss_distance, cfg.narrative_miss_confidence


def _cd_spatial(
    a: EventLike,
    b: EventLike,
    cfg: EnsembleDistanceConfig,
) -> Tuple[float, float]:
    """Spatial distance with confidence fallback chain.

    Chain: place_id -> location_hierarchy -> geohash_6 -> MISS
    """
    pid_a = a.place_id
    pid_b = b.place_id

    if pid_a and pid_b:
        if pid_a == pid_b:
            return cfg.spatial_same_place, cfg.spatial_same_confidence
        return cfg.spatial_diff_place, cfg.spatial_diff_confidence

    hier_a = _parse_json_list(a.location_hierarchy_json)
    hier_b = _parse_json_list(b.location_hierarchy_json)

    if hier_a and hier_b:
        shared = sum(1 for la, lb in zip(hier_a, hier_b) if la == lb)
        max_depth = max(len(hier_a), len(hier_b))
        if max_depth > 0:
            d = 1.0 - shared / max_depth
            return d, cfg.spatial_hierarchy_confidence

    gh_a = a.geohash_6
    gh_b = b.geohash_6

    if gh_a and gh_b:
        shared_prefix = 0
        for ca, cb in zip(gh_a, gh_b):
            if ca == cb:
                shared_prefix += 1
            else:
                break
        max_len = max(len(gh_a), len(gh_b))
        d = 1.0 - (shared_prefix / max_len) if max_len > 0 else 0.5
        return d, cfg.spatial_hierarchy_confidence

    return 0.5, cfg.spatial_miss_confidence


def _cd_social(
    a: EventLike,
    b: EventLike,
    cfg: EnsembleDistanceConfig,
) -> Tuple[float, float]:
    """Social distance with confidence fallback chain.

    Chain: participant Jaccard -> social_context match -> solo match -> MISS
    """
    set_a = set(_parse_json_list(a.participants_json))
    set_b = set(_parse_json_list(b.participants_json))

    if set_a or set_b:
        union = set_a | set_b
        if union:
            jaccard = len(set_a & set_b) / len(union)
            return 1.0 - jaccard, cfg.social_jaccard_confidence

    ctx_a = a.social_context
    ctx_b = b.social_context

    if ctx_a and ctx_b:
        d = 0.0 if ctx_a == ctx_b else 0.8
        return d, cfg.social_context_confidence

    solo_a = a.is_solo_event
    solo_b = b.is_solo_event
    if solo_a and solo_b:
        return 0.0, cfg.social_solo_confidence

    return 0.5, cfg.social_miss_confidence


def _cd_affective(
    a: EventLike,
    b: EventLike,
    cfg: EnsembleDistanceConfig,
) -> Tuple[float, float]:
    """Affective distance: 3D VAD Euclidean, normalized to [0, 1]."""
    v_a = a.affect_valence
    v_b = b.affect_valence

    if v_a is None or v_b is None:
        return 0.5, cfg.affective_miss_confidence

    ar_a = a.affect_arousal or 0.0
    ar_b = b.affect_arousal or 0.0
    d_a = a.affect_dominance or 0.0
    d_b = b.affect_dominance or 0.0

    dv = ((v_a - v_b) / 2.0) ** 2
    da = (ar_a - ar_b) ** 2
    dd = (d_a - d_b) ** 2
    return min(1.0, math.sqrt(dv + da + dd) / math.sqrt(3.0)), cfg.affective_present_confidence


# =============================================================================
# EnsembleDistance Class (Epic 3.1 -- Issue 3.1.6)
# =============================================================================


class EnsembleDistance:
    """
    Confidence-weighted 6D ensemble distance for episodic clustering.

    Combines semantic, temporal, narrative, spatial, social, and affective
    dimensions using the bagging principle: each dimension votes with a
    (distance, confidence) tuple. The final distance is:

        d = sum(w_i * conf_i * d_i) / sum(w_i * conf_i)

    When a dimension has confidence=0, its weight is automatically
    redistributed to other voters.

    Includes narrative short-circuit override: same-thread events are
    forced to low distance regardless of other dimensions (overridden
    only by the hard temporal cutoff).

    Spec Reference:
        - R2_EPISODIC_INTEGRATION_EPIC_PLAN.md Epic 3.1
        - R2_RESEARCH_FINAL.md Section 2.2
    """

    def __init__(self, config: Optional[EnsembleDistanceConfig] = None):
        """
        Initialize EnsembleDistance.

        Args:
            config: Ensemble configuration. Uses proven defaults if None.
        """
        self.config = config or EnsembleDistanceConfig()
        self.config.validate()

    def compute(self, event_a: EventLike, event_b: EventLike) -> float:
        """
        Compute confidence-weighted ensemble distance between two events.

        Returns distance in [0.0, inf). Events beyond max_temporal_gap return inf.
        """
        cfg = self.config

        # Hard temporal cutoff (overrides everything including short-circuit)
        if cfg.hard_temporal_cutoff:
            time_diff_ms = abs(event_a.timestamp - event_b.timestamp)
            if time_diff_ms > cfg.max_temporal_gap_ms:
                return float("inf")

        voters: List[Tuple[float, float, float]] = []  # (weight, distance, confidence)
        nar_result: Optional[Tuple[float, float]] = None

        if cfg.w_semantic > 0:
            d, c = _cd_semantic(event_a, event_b, cfg)
            voters.append((cfg.w_semantic, d, c))

        if cfg.w_temporal > 0:
            d, c = _cd_temporal(event_a, event_b, cfg)
            if d == float("inf"):
                return float("inf")
            voters.append((cfg.w_temporal, d, c))

        if cfg.w_narrative > 0:
            d, c = _cd_narrative(event_a, event_b, cfg)
            nar_result = (d, c)
            voters.append((cfg.w_narrative, d, c))

        if cfg.w_spatial > 0:
            d, c = _cd_spatial(event_a, event_b, cfg)
            voters.append((cfg.w_spatial, d, c))

        if cfg.w_social > 0:
            d, c = _cd_social(event_a, event_b, cfg)
            voters.append((cfg.w_social, d, c))

        if cfg.w_affective > 0:
            d, c = _cd_affective(event_a, event_b, cfg)
            voters.append((cfg.w_affective, d, c))

        # Confidence-weighted combination
        total_wc = sum(w * c for w, _, c in voters)
        if total_wc <= 0:
            # All signals missing -- pure semantic fallback
            if event_a.embedding_768 and event_b.embedding_768:
                d_sem, _ = _cd_semantic(event_a, event_b, cfg)
                return d_sem
            return 0.5

        d = sum(w * c * dist for w, dist, c in voters) / total_wc

        # Narrative short-circuit: same-thread forces low distance
        if cfg.shortcircuit:
            if nar_result is None:
                nar_result = _cd_narrative(event_a, event_b, cfg)
            nar_d, nar_c = nar_result
            if (
                nar_d <= cfg.narrative_same_thread + 0.01
                and nar_c >= cfg.shortcircuit_min_confidence
            ):
                d = min(d, cfg.shortcircuit_cap)
            elif (
                nar_d <= cfg.narrative_fuzzy_thread + 0.01
                and nar_c >= cfg.shortcircuit_min_confidence
            ):
                d = min(d, cfg.shortcircuit_cap * 1.5)

        return max(0.0, d)

    def compute_pair_detail(
        self,
        event_a: EventLike,
        event_b: EventLike,
    ) -> Dict[str, Any]:
        """
        Compute distance with per-dimension breakdown for observability.

        Returns dict with total distance, per-dimension (distance, confidence),
        and signal availability mask.
        """
        cfg = self.config
        dimensions: Dict[str, Dict[str, float]] = {}
        availability: Dict[str, bool] = {}

        for name, weight, fn in [
            ("semantic", cfg.w_semantic, _cd_semantic),
            ("temporal", cfg.w_temporal, _cd_temporal),
            ("narrative", cfg.w_narrative, _cd_narrative),
            ("spatial", cfg.w_spatial, _cd_spatial),
            ("social", cfg.w_social, _cd_social),
            ("affective", cfg.w_affective, _cd_affective),
        ]:
            if weight > 0:
                d, c = fn(event_a, event_b, cfg)
                dimensions[name] = {"distance": d, "confidence": c, "weight": weight}
                availability[name] = c > 0
            else:
                availability[name] = False

        total = self.compute(event_a, event_b)
        return {
            "total_distance": total,
            "dimensions": dimensions,
            "signal_availability": availability,
            "shortcircuit_active": cfg.shortcircuit,
        }

    def build_distance_matrix(self, events: Sequence[EventLike]) -> np.ndarray:
        """
        Build NxN symmetric distance matrix using ensemble distance.

        Args:
            events: List of events with enriched signal fields

        Returns:
            n x n symmetric distance matrix (numpy float64)
        """
        n = len(events)
        if n == 0:
            return np.zeros((0, 0), dtype=np.float64)

        matrix = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                d = self.compute(events[i], events[j])
                matrix[i, j] = d
                matrix[j, i] = d

        return matrix
