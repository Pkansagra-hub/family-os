"""
CompositeDistance - Semantic + temporal distance for episodic clustering.

This module implements the composite distance metric that combines
semantic similarity (cosine) and temporal proximity for DBSCAN clustering.

Spec Reference:
    - Dossier Appendix C.3.1: DBSCAN algorithm
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

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence

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
class DBSCANParams:
    """
    Parameters for DBSCAN clustering.

    Defaults optimized for UltraBERT L2-normalized 768-dim embeddings:
        - eps: 0.15 (max composite distance to cluster - tighter for L2-normalized embeddings)
        - min_samples: 2 (minimum events for core point)
        - temporal_weight: 0.3 (how much time affects distance)
        - max_temporal_gap_hours: 4.0 (hard limit - events further apart cannot cluster)

    Note: UltraBERT produces L2-normalized embeddings with typical cosine distances
    in the range 0.10-0.30 for different topics. With temporal_weight=0.3, composite
    distances are ~0.07-0.21, so eps=0.15 creates meaningful clusters.

    Configuration Keys (from M4_EXECUTION.md):
        - P03_DBSCAN_EPS: [0.10, 0.40] range
        - P03_DBSCAN_TEMPORAL_WEIGHT: [0.1, 0.5] range
        - P03_DBSCAN_MAX_TEMPORAL_GAP_HOURS: [1.0, 8.0] range
    """

    eps: float = 0.15  # Tighter default for UltraBERT L2-normalized embeddings
    min_samples: int = 2
    temporal_weight: float = 0.3
    max_temporal_gap_hours: float = 4.0

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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "eps": self.eps,
            "min_samples": self.min_samples,
            "temporal_weight": self.temporal_weight,
            "max_temporal_gap_hours": self.max_temporal_gap_hours,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DBSCANParams":
        """Create from dictionary."""
        return cls(
            eps=data.get("eps", 0.25),
            min_samples=data.get("min_samples", 2),
            temporal_weight=data.get("temporal_weight", 0.3),
            max_temporal_gap_hours=data.get("max_temporal_gap_hours", 4.0),
        )


# =============================================================================
# Event Protocol
# =============================================================================


class EventLike(Protocol):
    """
    Protocol for event objects usable with CompositeDistance.

    Minimal interface needed for distance computation.
    P03EventState implements this implicitly.
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


# =============================================================================
# CompositeDistance Class
# =============================================================================


class CompositeDistance:
    """
    Composite distance for episodic clustering.

    Combines semantic similarity (cosine) and temporal proximity
    to create a unified distance metric for DBSCAN.

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
        params = DBSCANParams(eps=0.25, temporal_weight=0.3)
        distance = CompositeDistance(params)

        dist = distance.compute(event_a, event_b)
        matrix = distance.build_distance_matrix(events)
    """

    def __init__(self, params: Optional[DBSCANParams] = None):
        """
        Initialize CompositeDistance.

        Args:
            params: DBSCAN parameters. Uses defaults if None.
        """
        self.params = params or DBSCANParams()
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

        Formula: min(1.0, time_diff_ms / max_temporal_gap_ms)

        Args:
            time_diff_ms: Absolute time difference in milliseconds

        Returns:
            Normalized distance in [0.0, 1.0]
        """
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
