"""
CentroidCalculator - Episode centroid embedding computation.

This module computes weighted centroids for episode clusters,
creating representative embeddings for episodic memory retrieval.

Spec Reference:
    - Dossier Appendix C.3.2: Centroid Calculation (Episode Embedding)
    - M4_EXECUTION.md Issue 4.2.4

Output: 768-dim L2-normalized centroid embedding for each episode.

Weighting Strategies (from Dossier C.3.2):
    - uniform: All events contribute equally
    - importance: Weight by importance_score
    - recency: Weight by timestamp (recent = higher)
    - hybrid: 0.7 × importance + 0.3 × recency (default)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Sequence

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Expected embedding dimension (UltraBERT 768-dim)
EMBEDDING_DIM = 768

# Minimum weight to avoid division issues
MIN_WEIGHT = 0.01


# =============================================================================
# Weighting Strategy Enum
# =============================================================================


class WeightingStrategy(str, Enum):
    """Weighting strategies for centroid calculation."""

    UNIFORM = "uniform"
    IMPORTANCE = "importance"
    RECENCY = "recency"
    HYBRID = "hybrid"


# =============================================================================
# Event Protocol
# =============================================================================


class CentroidableEvent(Protocol):
    """
    Protocol for event objects usable with CentroidCalculator.

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

    @property
    def importance_score(self) -> float:
        """Importance score for weighting."""
        ...


# =============================================================================
# Centroid Result
# =============================================================================


@dataclass
class CentroidResult:
    """
    Result from centroid computation.

    Contains centroid, variance, and weights used.
    """

    centroid: np.ndarray
    """768-dim L2-normalized centroid embedding."""

    variance: float
    """Variance from centroid (cluster cohesion measure)."""

    weights: np.ndarray
    """Weights used for each event (same order as input)."""

    strategy: str
    """Weighting strategy used."""

    event_count: int
    """Number of events with valid embeddings."""

    @property
    def centroid_list(self) -> List[float]:
        """Centroid as Python list (for serialization)."""
        return self.centroid.tolist()


# =============================================================================
# Episode Candidate (for staged writes)
# =============================================================================


@dataclass
class EpisodeCandidate:
    """
    Episode candidate for R6/R7 staged write.

    Contains all data needed to create st_epi record.
    NO database write in R2 — this is passed to R6/R7.

    Spec: Dossier C.3.2, M4_EXECUTION.md Issue 4.2.4
    """

    # Identity
    cluster_id: str
    """From EpisodeCluster."""

    space_id: str
    """Family space context."""

    # Event membership
    event_ids: List[str] = field(default_factory=list)
    """IDs of events in this episode."""

    event_count: int = 0
    """Number of events."""

    # Centroid embedding (768-dim)
    centroid_embedding: Optional[List[float]] = None
    """Weighted centroid embedding."""

    centroid_embedding_id: Optional[str] = None
    """Reference to st_vec record (set by R7)."""

    # Temporal bounds (milliseconds)
    temporal_start: int = 0
    """Start of episode (min timestamp)."""

    temporal_end: int = 0
    """End of episode (max timestamp)."""

    # Quality metrics
    cohesion_score: float = 0.0
    """Intra-cluster similarity [0, 1]."""

    variance: float = 0.0
    """Distance from centroid (lower = tighter)."""

    is_noise: bool = False
    """Singleton micro-episode."""

    # Derived attributes
    dominant_sentiment: float = 0.0
    """Average sentiment of events."""

    dominant_emotion: str = ""
    """Most common emotion."""

    location_hint: Optional[str] = None
    """Common location geohash."""

    activity_type: str = ""
    """Common activity type."""

    participants_json: str = "[]"
    """JSON array of participant IDs."""

    # Title and summary (generated or extracted)
    title: str = ""
    """Episode title."""

    summary: str = ""
    """Episode summary."""

    # Confidence for reconciliation
    confidence_score: float = 0.0
    """Confidence in episode quality."""

    @property
    def duration_ms(self) -> int:
        """Duration of episode in milliseconds."""
        return self.temporal_end - self.temporal_start


# =============================================================================
# R2 Staged Output Container
# =============================================================================


@dataclass
class R2StagedOutput:
    """
    Complete R2 output for staging.

    Contains all episode candidates and batch metadata.
    NO database writes — passed to R6/R7 for commit.

    Spec: M4_EXECUTION.md Issue 4.2.4
    """

    # Episode candidates
    episode_candidates: List[EpisodeCandidate] = field(default_factory=list)
    """All episode candidates from this R2 run."""

    # Batch metadata
    cluster_count: int = 0
    """Number of non-noise clusters formed."""

    noise_count: int = 0
    """Number of noise/singleton events."""

    avg_cluster_size: float = 0.0
    """Average cluster size (non-noise only)."""

    total_events_processed: int = 0
    """Total events processed."""

    # Quality metrics
    batch_silhouette_score: float = 0.0
    """Batch-level silhouette score [−1, 1]."""

    batch_cohesion_avg: float = 0.0
    """Average cohesion across clusters."""

    def add_candidate(self, candidate: EpisodeCandidate) -> None:
        """Add episode candidate and update metadata."""
        self.episode_candidates.append(candidate)
        if candidate.is_noise:
            self.noise_count += 1
        else:
            self.cluster_count += 1
        self.total_events_processed += candidate.event_count

    def finalize(self) -> None:
        """Compute final aggregate metrics."""
        non_noise = [c for c in self.episode_candidates if not c.is_noise]
        if non_noise:
            self.avg_cluster_size = sum(c.event_count for c in non_noise) / len(non_noise)
            self.batch_cohesion_avg = sum(c.cohesion_score for c in non_noise) / len(non_noise)

    @property
    def singleton_rate(self) -> float:
        """Ratio of noise events to total events."""
        if self.total_events_processed == 0:
            return 0.0
        return self.noise_count / self.total_events_processed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "cluster_count": self.cluster_count,
            "noise_count": self.noise_count,
            "avg_cluster_size": self.avg_cluster_size,
            "total_events_processed": self.total_events_processed,
            "batch_silhouette_score": self.batch_silhouette_score,
            "batch_cohesion_avg": self.batch_cohesion_avg,
            "singleton_rate": self.singleton_rate,
            "episode_count": len(self.episode_candidates),
        }


# =============================================================================
# CentroidCalculator Class
# =============================================================================


class CentroidCalculator:
    """
    Computes episode centroid embedding from constituent events.

    The centroid is a weighted average of event embeddings that
    represents the episode for retrieval and similarity search.

    Spec: Dossier Appendix C.3.2

    Formula: centroid = sum(weight_i × embedding_i) for all i

    Weighting Strategies:
        - uniform: All events contribute equally
        - importance: Weight by importance_score (key moments matter more)
        - recency: Weight by timestamp (recent events matter more)
        - hybrid: 0.7 × importance + 0.3 × recency (default, balanced)

    Usage:
        calculator = CentroidCalculator()

        result = calculator.compute(events, strategy="hybrid")
        centroid = result.centroid  # 768-dim L2-normalized
        variance = result.variance  # Cluster cohesion measure
    """

    def __init__(
        self,
        default_strategy: str = "hybrid",
        normalize: bool = True,
    ):
        """
        Initialize CentroidCalculator.

        Args:
            default_strategy: Default weighting strategy
            normalize: Whether to L2-normalize centroids
        """
        self.default_strategy = default_strategy
        self.normalize = normalize

    def compute_weights(
        self,
        events: Sequence[CentroidableEvent],
        strategy: str = "hybrid",
    ) -> np.ndarray:
        """
        Compute weight for each event based on strategy.

        Strategies (from Dossier C.3.2):
            - uniform: All events contribute equally (1/n each)
            - importance: Weight by importance_score
            - recency: Weight by timestamp (recent = higher)
            - hybrid: 0.7 × importance + 0.3 × recency (default)

        Args:
            events: List of events with importance_score and timestamp
            strategy: Weighting strategy name

        Returns:
            Normalized weight array that sums to 1.0
        """
        n = len(events)
        if n == 0:
            return np.array([], dtype=np.float32)

        if strategy == WeightingStrategy.UNIFORM or strategy == "uniform":
            return np.ones(n, dtype=np.float32) / n

        elif strategy == WeightingStrategy.IMPORTANCE or strategy == "importance":
            weights = np.array(
                [getattr(e, "importance_score", 0.0) for e in events],
                dtype=np.float32,
            )
            weights = weights + MIN_WEIGHT  # Avoid zero weights
            return weights / weights.sum()

        elif strategy == WeightingStrategy.RECENCY or strategy == "recency":
            timestamps = np.array([e.timestamp for e in events], dtype=np.float64)
            if timestamps.max() == timestamps.min():
                return np.ones(n, dtype=np.float32) / n
            # Normalize to [0, 1], recent = higher
            recency = (timestamps - timestamps.min()) / (timestamps.max() - timestamps.min() + 1)
            weights = recency.astype(np.float32) + 0.1  # Ensure non-zero
            return weights / weights.sum()

        elif strategy == WeightingStrategy.HYBRID or strategy == "hybrid":
            importance = np.array(
                [getattr(e, "importance_score", 0.0) for e in events],
                dtype=np.float32,
            )
            timestamps = np.array([e.timestamp for e in events], dtype=np.float64)

            if timestamps.max() == timestamps.min():
                recency = np.ones(n, dtype=np.float32)
            else:
                recency = (timestamps - timestamps.min()) / (
                    timestamps.max() - timestamps.min() + 1
                )
                recency = recency.astype(np.float32)

            # Hybrid: 70% importance, 30% recency
            weights = 0.7 * importance + 0.3 * recency
            weights = weights + MIN_WEIGHT
            return weights / weights.sum()

        else:
            # Unknown strategy, fall back to uniform
            logger.warning("Unknown weighting strategy '%s', using uniform", strategy)
            return np.ones(n, dtype=np.float32) / n

    def compute_centroid(
        self,
        events: Sequence[CentroidableEvent],
        strategy: Optional[str] = None,
    ) -> np.ndarray:
        """
        Compute weighted centroid of event embeddings.

        Formula: centroid = sum(weight_i × embedding_i) for all i

        Args:
            events: List of events with embedding_768
            strategy: Weighting strategy (uses default if None)

        Returns:
            768-dim centroid embedding (L2-normalized if self.normalize=True)

        Raises:
            ValueError: If no events have valid embeddings
        """
        strategy = strategy or self.default_strategy

        # Filter events with valid embeddings
        valid_events = [e for e in events if e.embedding_768 is not None]
        if not valid_events:
            raise ValueError("No events with valid embeddings for centroid computation")

        # Compute weights for valid events only
        weights = self.compute_weights(valid_events, strategy)

        # Stack embeddings into matrix (n × 768)
        embeddings = np.stack([np.asarray(e.embedding_768, dtype=np.float32) for e in valid_events])

        # Weighted sum: (n,) @ (n, 768) with broadcasting
        centroid = np.sum(embeddings * weights[:, np.newaxis], axis=0)

        # L2 normalize for cosine similarity compatibility
        if self.normalize:
            norm = np.linalg.norm(centroid)
            if norm > 1e-10:
                centroid = centroid / norm

        return centroid

    def compute_variance(
        self,
        events: Sequence[CentroidableEvent],
        centroid: np.ndarray,
    ) -> float:
        """
        Compute variance from centroid (cluster cohesion).

        Low variance = tight cluster = coherent episode
        High variance = loose cluster = may need splitting

        Formula: variance = mean((1 - cos_sim)² for all events)

        Args:
            events: List of events with embedding_768
            centroid: Precomputed centroid embedding

        Returns:
            Variance in [0.0, 1.0] range (lower = tighter cluster)
        """
        # Collect valid embeddings
        embeddings: List[np.ndarray] = []
        for event in events:
            if event.embedding_768 is not None:
                embeddings.append(np.asarray(event.embedding_768, dtype=np.float32))

        if not embeddings:
            return 0.0

        # Stack into matrix
        emb_matrix = np.stack(embeddings)

        # Compute cosine distances from centroid
        # distance = 1 - cos_sim
        similarities = np.dot(emb_matrix, centroid)
        distances = 1.0 - similarities

        # Average squared distance
        variance = float(np.mean(distances**2))

        return variance

    def compute(
        self,
        events: Sequence[CentroidableEvent],
        strategy: Optional[str] = None,
    ) -> CentroidResult:
        """
        Compute centroid with full result including variance and weights.

        Convenience method that combines compute_centroid and compute_variance.

        Args:
            events: List of events with embedding_768
            strategy: Weighting strategy (uses default if None)

        Returns:
            CentroidResult with centroid, variance, and metadata
        """
        strategy = strategy or self.default_strategy

        # Filter valid events
        valid_events = [e for e in events if e.embedding_768 is not None]
        if not valid_events:
            # Return zero centroid for empty input
            return CentroidResult(
                centroid=np.zeros(EMBEDDING_DIM, dtype=np.float32),
                variance=0.0,
                weights=np.array([], dtype=np.float32),
                strategy=strategy,
                event_count=0,
            )

        weights = self.compute_weights(valid_events, strategy)
        centroid = self.compute_centroid(valid_events, strategy)
        variance = self.compute_variance(valid_events, centroid)

        return CentroidResult(
            centroid=centroid,
            variance=variance,
            weights=weights,
            strategy=strategy,
            event_count=len(valid_events),
        )

    def update_event_centroid_distances(
        self,
        events: List[Any],
        centroid: np.ndarray,
    ) -> None:
        """
        Update centroid_distance on each event in-place.

        Sets event.centroid_distance = 1 - cos_sim(event.embedding, centroid)

        Args:
            events: List of mutable events with centroid_distance attribute
            centroid: Episode centroid embedding
        """
        for event in events:
            if hasattr(event, "embedding_768") and event.embedding_768 is not None:
                emb = np.asarray(event.embedding_768, dtype=np.float32)
                norm_emb = np.linalg.norm(emb)
                norm_cent = np.linalg.norm(centroid)

                if norm_emb > 1e-10 and norm_cent > 1e-10:
                    cos_sim = np.dot(emb, centroid) / (norm_emb * norm_cent)
                    distance = 1.0 - cos_sim
                else:
                    distance = 1.0

                if hasattr(event, "centroid_distance"):
                    event.centroid_distance = float(distance)

    def create_episode_candidate(
        self,
        cluster_id: str,
        space_id: str,
        events: Sequence[CentroidableEvent],
        cohesion_score: float,
        temporal_start: int,
        temporal_end: int,
        strategy: Optional[str] = None,
        is_noise: bool = False,
    ) -> EpisodeCandidate:
        """
        Create episode candidate from cluster data.

        Computes centroid and variance, packages for R6/R7 staging.

        Args:
            cluster_id: Cluster ID from DBSCAN
            space_id: Family space context
            events: Events in this cluster
            cohesion_score: Pre-computed cohesion from DBSCAN
            temporal_start: Episode start timestamp (ms)
            temporal_end: Episode end timestamp (ms)
            strategy: Weighting strategy for centroid
            is_noise: Whether this is a noise/singleton cluster

        Returns:
            EpisodeCandidate ready for R6/R7 staging
        """
        result = self.compute(events, strategy)

        # Compute dominant sentiment
        sentiments = [
            getattr(e, "sentiment_score", 0.0) for e in events if hasattr(e, "sentiment_score")
        ]
        dominant_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        return EpisodeCandidate(
            cluster_id=cluster_id,
            space_id=space_id,
            event_ids=[e.event_id for e in events],
            event_count=len(events),
            centroid_embedding=result.centroid_list if result.event_count > 0 else None,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            cohesion_score=cohesion_score,
            variance=result.variance,
            is_noise=is_noise,
            dominant_sentiment=dominant_sentiment,
            confidence_score=cohesion_score,  # Use cohesion as confidence proxy
        )
