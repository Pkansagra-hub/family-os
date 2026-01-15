"""
EpisodicHDBSCAN - Hierarchical DBSCAN for episodic memory formation.

This module implements HDBSCAN clustering with soft noise rescue,
replacing the fixed-eps DBSCAN for more robust episode formation.

Benefits over DBSCAN:
    - Automatic multi-resolution clustering (no fixed eps required)
    - Soft cluster membership probabilities
    - Outlier scores for noise rescue
    - Handles varying density naturally

Spec Reference:
    - Dossier Appendix C.3.1: DBSCAN (now extended with HDBSCAN)
    - M4_EXECUTION.md Issue 4.2.3

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

try:
    import hdbscan

    HDBSCAN_AVAILABLE = True
except ImportError:
    HDBSCAN_AVAILABLE = False
    hdbscan = None

from sklearn.cluster import DBSCAN

from k0.modules.consolidation.algorithms.composite_distance import CompositeDistance, DBSCANParams
from k0.pipelines.p03.phase_outputs import EpisodeCluster

logger = logging.getLogger(__name__)


# =============================================================================
# HDBSCAN Parameters
# =============================================================================


@dataclass(frozen=True)
class HDBSCANParams:
    """
    Parameters for HDBSCAN clustering.

    HDBSCAN advantages:
        - No fixed eps: automatically discovers cluster structure
        - Soft membership: probabilities for each point
        - Outlier scores: rescue noise points intelligently
        - Variable density: handles clusters of different densities

    Configuration Keys:
        - min_cluster_size: Minimum events to form a cluster (2+)
        - min_samples: Density smoothing parameter (lower = less noise)
        - cluster_selection_epsilon: Optional flat cut (like DBSCAN eps)
        - cluster_selection_method: 'eom' (default) or 'leaf' (small clusters)
        - noise_rescue_threshold: Outlier score below which noise is rescued
        - temporal_weight: Weight for temporal distance [0,1]
        - max_temporal_gap_hours: Hard limit for temporal proximity
    """

    min_cluster_size: int = 2
    min_samples: int = 1  # Lower = less noise, more inclusive
    cluster_selection_epsilon: float = 0.0  # 0 = automatic, >0 = flat cut
    cluster_selection_method: str = "leaf"  # 'leaf' preserves small clusters
    noise_rescue_threshold: float = 0.5  # Rescue noise with outlier_score < this
    temporal_weight: float = 0.3
    max_temporal_gap_hours: float = 4.0
    allow_single_cluster: bool = False

    @property
    def max_temporal_gap_ms(self) -> int:
        """Max temporal gap in milliseconds."""
        return int(self.max_temporal_gap_hours * 3_600_000)

    @property
    def semantic_weight(self) -> float:
        """Weight for semantic (cosine) distance component."""
        return 1.0 - self.temporal_weight

    def validate(self) -> None:
        """Validate parameter ranges."""
        if self.min_cluster_size < 2:
            raise ValueError(f"min_cluster_size must be >= 2, got {self.min_cluster_size}")
        if self.min_samples < 1:
            raise ValueError(f"min_samples must be >= 1, got {self.min_samples}")
        if not 0.0 <= self.temporal_weight <= 1.0:
            raise ValueError(f"temporal_weight must be in [0, 1], got {self.temporal_weight}")
        if not 0.0 <= self.noise_rescue_threshold <= 1.0:
            raise ValueError(
                f"noise_rescue_threshold must be in [0, 1], got {self.noise_rescue_threshold}"
            )
        if self.cluster_selection_method not in ("eom", "leaf"):
            raise ValueError(
                f"cluster_selection_method must be 'eom' or 'leaf', got {self.cluster_selection_method}"
            )

    def to_dbscan_params(self) -> DBSCANParams:
        """Convert to DBSCANParams for CompositeDistance compatibility."""
        return DBSCANParams(
            eps=self.cluster_selection_epsilon if self.cluster_selection_epsilon > 0 else 0.15,
            min_samples=self.min_samples,
            temporal_weight=self.temporal_weight,
            max_temporal_gap_hours=self.max_temporal_gap_hours,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "min_cluster_size": self.min_cluster_size,
            "min_samples": self.min_samples,
            "cluster_selection_epsilon": self.cluster_selection_epsilon,
            "cluster_selection_method": self.cluster_selection_method,
            "noise_rescue_threshold": self.noise_rescue_threshold,
            "temporal_weight": self.temporal_weight,
            "max_temporal_gap_hours": self.max_temporal_gap_hours,
        }


# =============================================================================
# Event Protocol
# =============================================================================


class ClusterableEvent(Protocol):
    """Protocol for event objects usable with EpisodicHDBSCAN."""

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
    def sentiment_score(self) -> float:
        """Sentiment score for dominant sentiment calculation."""
        ...


# =============================================================================
# Clustering Result
# =============================================================================


@dataclass
class HDBSCANClusteringResult:
    """
    Complete result from HDBSCAN clustering.

    Extended from DBSCAN result with soft membership and outlier scores.
    """

    clusters: List[EpisodeCluster]
    """List of episode clusters (including rescued noise as weak episodes)."""

    total_events: int
    """Total events processed."""

    cluster_count: int
    """Number of non-noise clusters formed."""

    noise_count: int
    """Number of true noise events (not rescued)."""

    rescued_count: int
    """Number of noise events rescued into weak episodes."""

    labels: List[int]
    """HDBSCAN labels for each input event."""

    probabilities: List[float]
    """Cluster membership probabilities [0, 1]."""

    outlier_scores: List[float]
    """Outlier scores [0, 1] where 1 = most outlier-like."""

    @property
    def singleton_rate(self) -> float:
        """Ratio of true noise to total events."""
        if self.total_events == 0:
            return 0.0
        return self.noise_count / self.total_events

    @property
    def rescue_rate(self) -> float:
        """Ratio of rescued noise to original noise."""
        original_noise = self.noise_count + self.rescued_count
        if original_noise == 0:
            return 0.0
        return self.rescued_count / original_noise


# =============================================================================
# EpisodicHDBSCAN Class
# =============================================================================


class EpisodicHDBSCAN:
    """
    HDBSCAN clustering for episodic memory with noise rescue.

    Uses composite distance (semantic + temporal) with hierarchical
    density-based clustering. Rescues noise points with low outlier
    scores into weak episodes.

    Fallback: Uses DBSCAN if hdbscan library is not available.

    Usage:
        params = HDBSCANParams(min_cluster_size=2, noise_rescue_threshold=0.5)
        clusterer = EpisodicHDBSCAN(params)

        result = clusterer.cluster(events)
        for cluster in result.clusters:
            print(f"Episode {cluster.cluster_id}: {cluster.event_count} events")
    """

    def __init__(self, params: Optional[HDBSCANParams] = None):
        """
        Initialize EpisodicHDBSCAN.

        Args:
            params: HDBSCAN parameters. Uses defaults if None.
        """
        self.params = params or HDBSCANParams()
        self.params.validate()

        # Create CompositeDistance with equivalent DBSCANParams
        dbscan_params = self.params.to_dbscan_params()
        self.distance_calculator = CompositeDistance(dbscan_params)

        self._use_hdbscan = HDBSCAN_AVAILABLE
        if not self._use_hdbscan:
            logger.warning(
                "HDBSCAN not available, falling back to DBSCAN. "
                "Install with: pip install hdbscan"
            )

    def cluster(
        self,
        events: Sequence[ClusterableEvent],
    ) -> HDBSCANClusteringResult:
        """
        Run HDBSCAN clustering on events with noise rescue.

        Args:
            events: List of events with embeddings and timestamps

        Returns:
            HDBSCANClusteringResult with clusters, probabilities, and outlier scores
        """
        if len(events) == 0:
            return HDBSCANClusteringResult(
                clusters=[],
                total_events=0,
                cluster_count=0,
                noise_count=0,
                rescued_count=0,
                labels=[],
                probabilities=[],
                outlier_scores=[],
            )

        # Not enough events - all become noise
        if len(events) < self.params.min_cluster_size:
            return self._create_all_noise_result(events)

        # Step 1: Build distance matrix using CompositeDistance
        distances = self.distance_calculator.build_distance_matrix(list(events))

        # Cap infinity values (HDBSCAN can't handle inf)
        max_finite_distance = 1e10
        distances = np.clip(distances, 0.0, max_finite_distance)

        # Step 2: Run clustering
        if self._use_hdbscan:
            labels, probabilities, outlier_scores = self._run_hdbscan(distances)
        else:
            labels, probabilities, outlier_scores = self._run_dbscan_fallback(distances)

        # Step 3: Rescue noise points with low outlier scores
        labels, rescued_indices = self._rescue_noise(
            events, labels, probabilities, outlier_scores, distances
        )

        # Step 4: Group events by cluster label
        label_to_events: Dict[int, List[Tuple[int, ClusterableEvent]]] = {}
        for idx, label in enumerate(labels):
            if label not in label_to_events:
                label_to_events[label] = []
            label_to_events[label].append((idx, events[idx]))

        # Step 5: Create EpisodeCluster objects
        clusters: List[EpisodeCluster] = []
        cluster_count = 0
        noise_count = 0

        for label, indexed_events in label_to_events.items():
            cluster_events = [e for _, e in indexed_events]
            indices = [i for i, _ in indexed_events]
            cluster_probs = [probabilities[i] for i in indices]

            cluster = self._create_cluster(
                cluster_events, label, cluster_probs, any(i in rescued_indices for i in indices)
            )
            clusters.append(cluster)

            if label == -1:
                noise_count += len(cluster_events)
            else:
                cluster_count += 1

        return HDBSCANClusteringResult(
            clusters=clusters,
            total_events=len(events),
            cluster_count=cluster_count,
            noise_count=noise_count,
            rescued_count=len(rescued_indices),
            labels=labels,
            probabilities=probabilities,
            outlier_scores=outlier_scores,
        )

    def _run_hdbscan(self, distances: np.ndarray) -> Tuple[List[int], List[float], List[float]]:
        """Run HDBSCAN algorithm on precomputed distances."""
        # HDBSCAN requires float64 (double) dtype
        distances_f64 = distances.astype(np.float64)

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.params.min_cluster_size,
            min_samples=self.params.min_samples,
            metric="precomputed",
            cluster_selection_epsilon=self.params.cluster_selection_epsilon,
            cluster_selection_method=self.params.cluster_selection_method,
            allow_single_cluster=self.params.allow_single_cluster,
        )
        clusterer.fit(distances_f64)

        labels = clusterer.labels_.tolist()
        probabilities = clusterer.probabilities_.tolist()
        outlier_scores = clusterer.outlier_scores_.tolist()

        return labels, probabilities, outlier_scores

    def _run_dbscan_fallback(
        self, distances: np.ndarray
    ) -> Tuple[List[int], List[float], List[float]]:
        """Fallback to DBSCAN when HDBSCAN is not available."""
        # Use cluster_selection_epsilon or default
        eps = (
            self.params.cluster_selection_epsilon
            if self.params.cluster_selection_epsilon > 0
            else 0.07
        )

        sklearn_dbscan = DBSCAN(
            eps=eps,
            min_samples=self.params.min_samples,
            metric="precomputed",
        )
        sklearn_dbscan.fit(distances)

        labels = sklearn_dbscan.labels_.tolist()

        # Simulate probabilities (1.0 for clustered, 0.0 for noise)
        probabilities = [1.0 if label >= 0 else 0.0 for label in labels]

        # Simulate outlier scores based on distance to nearest cluster centroid
        outlier_scores = self._compute_outlier_scores_fallback(distances, labels)

        return labels, probabilities, outlier_scores

    def _compute_outlier_scores_fallback(
        self,
        distances: np.ndarray,
        labels: List[int],
    ) -> List[float]:
        """Compute approximate outlier scores for DBSCAN fallback."""
        n = len(labels)
        outlier_scores = []

        for i in range(n):
            if labels[i] >= 0:
                # For clustered points, outlier score based on distance to cluster members
                cluster_members = [j for j in range(n) if labels[j] == labels[i] and j != i]
                if cluster_members:
                    avg_dist = np.mean([distances[i, j] for j in cluster_members])
                    outlier_scores.append(min(1.0, avg_dist))
                else:
                    outlier_scores.append(0.5)
            else:
                # For noise, compute min distance to any clustered point
                clustered = [j for j in range(n) if labels[j] >= 0]
                if clustered:
                    min_dist = min(distances[i, j] for j in clustered)
                    # Normalize to [0, 1] - higher distance = more outlier-like
                    outlier_scores.append(min(1.0, min_dist * 2))
                else:
                    outlier_scores.append(1.0)

        return outlier_scores

    def _rescue_noise(
        self,
        events: Sequence[ClusterableEvent],
        labels: List[int],
        probabilities: List[float],
        outlier_scores: List[float],
        distances: np.ndarray,
    ) -> Tuple[List[int], List[int]]:
        """
        Rescue noise points with low outlier scores.

        Strategy:
            1. Find noise points with outlier_score < threshold
            2. Assign them to nearest cluster OR create weak episode
            3. Update labels and probabilities

        Args:
            events: All events
            labels: Current cluster labels (-1 = noise)
            probabilities: Current membership probabilities
            outlier_scores: Outlier scores from HDBSCAN
            distances: Precomputed distance matrix

        Returns:
            Tuple of (updated_labels, list of rescued indices)
        """
        threshold = self.params.noise_rescue_threshold
        n = len(labels)
        labels = list(labels)  # Make mutable copy
        rescued_indices: List[int] = []

        # Find noise points eligible for rescue
        noise_indices = [i for i in range(n) if labels[i] == -1]
        rescuable = [(i, outlier_scores[i]) for i in noise_indices if outlier_scores[i] < threshold]

        if not rescuable:
            return labels, rescued_indices

        # Sort by outlier score (rescue most confident first)
        rescuable.sort(key=lambda x: x[1])

        for idx, score in rescuable:
            # Find nearest cluster
            best_cluster = -1
            best_distance = float("inf")

            for j in range(n):
                if labels[j] >= 0:  # j is in a cluster
                    if distances[idx, j] < best_distance:
                        best_distance = distances[idx, j]
                        best_cluster = labels[j]

            if best_cluster >= 0 and best_distance < 0.3:  # Reasonable rescue distance
                # Rescue: assign to nearest cluster
                labels[idx] = best_cluster
                rescued_indices.append(idx)
                logger.debug(
                    f"Rescued event {events[idx].event_id} to cluster {best_cluster} "
                    f"(outlier_score={score:.3f}, distance={best_distance:.3f})"
                )
            else:
                # Create new weak cluster from nearby noise points
                nearby_noise = [
                    j
                    for j in noise_indices
                    if j != idx
                    and labels[j] == -1
                    and distances[idx, j] < 0.2
                    and outlier_scores[j] < threshold
                ]

                if nearby_noise:
                    # Create new cluster
                    new_cluster_id = max(labels) + 1 if max(labels) >= 0 else 0
                    labels[idx] = new_cluster_id
                    rescued_indices.append(idx)

                    for j in nearby_noise:
                        labels[j] = new_cluster_id
                        rescued_indices.append(j)

                    logger.debug(
                        f"Created weak cluster {new_cluster_id} with {len(nearby_noise) + 1} events"
                    )

        return labels, rescued_indices

    def _create_cluster(
        self,
        events: List[ClusterableEvent],
        label: int,
        probabilities: List[float],
        is_rescued: bool = False,
    ) -> EpisodeCluster:
        """Create EpisodeCluster from grouped events."""
        is_noise = label == -1

        # Generate cluster ID
        if is_noise:
            cluster_id = f"noise-{uuid.uuid4().hex[:26]}"
        elif is_rescued:
            cluster_id = f"weak-{uuid.uuid4().hex[:26]}"
        else:
            cluster_id = uuid.uuid4().hex[:26]

        # Temporal bounds (milliseconds)
        timestamps = [e.timestamp for e in events]
        temporal_start = min(timestamps)
        temporal_end = max(timestamps)

        # Dominant sentiment (weighted by membership probability)
        total_weight = sum(probabilities)
        if total_weight > 0:
            weighted_sentiment = sum(
                getattr(e, "sentiment_score", 0.0) * p for e, p in zip(events, probabilities)
            )
            dominant_sentiment = weighted_sentiment / total_weight
        else:
            sentiments = [getattr(e, "sentiment_score", 0.0) for e in events]
            dominant_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        # Average membership probability (cluster strength indicator)
        avg_probability = sum(probabilities) / len(probabilities) if probabilities else 0.0

        # Cohesion score
        cohesion = self._compute_cohesion(events)

        return EpisodeCluster(
            cluster_id=cluster_id,
            member_event_ids=[e.event_id for e in events],
            dominant_sentiment=dominant_sentiment,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            cohesion_score=cohesion * avg_probability,  # Weight by membership strength
        )

    def _compute_cohesion(self, events: List[ClusterableEvent]) -> float:
        """Compute intra-cluster similarity (cohesion)."""
        if len(events) < 2:
            return 1.0

        embeddings: List[np.ndarray] = []
        for event in events:
            if event.embedding_768 is not None:
                embeddings.append(np.asarray(event.embedding_768, dtype=np.float32))

        if len(embeddings) < 2:
            return 1.0

        total_sim = 0.0
        count = 0

        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                norm_i = np.linalg.norm(embeddings[i])
                norm_j = np.linalg.norm(embeddings[j])

                if norm_i > 1e-10 and norm_j > 1e-10:
                    sim = np.dot(embeddings[i], embeddings[j]) / (norm_i * norm_j)
                    total_sim += max(0.0, min(1.0, sim))
                    count += 1

        return total_sim / count if count > 0 else 1.0

    def _create_all_noise_result(
        self,
        events: Sequence[ClusterableEvent],
    ) -> HDBSCANClusteringResult:
        """Create result where all events are noise."""
        clusters: List[EpisodeCluster] = []
        labels: List[int] = []
        probabilities: List[float] = []
        outlier_scores: List[float] = []

        for event in events:
            cluster = EpisodeCluster(
                cluster_id=f"noise-{uuid.uuid4().hex[:26]}",
                member_event_ids=[event.event_id],
                dominant_sentiment=getattr(event, "sentiment_score", 0.0),
                temporal_start=event.timestamp,
                temporal_end=event.timestamp,
                cohesion_score=1.0,
            )
            clusters.append(cluster)
            labels.append(-1)
            probabilities.append(0.0)
            outlier_scores.append(1.0)

        return HDBSCANClusteringResult(
            clusters=clusters,
            total_events=len(events),
            cluster_count=0,
            noise_count=len(events),
            rescued_count=0,
            labels=labels,
            probabilities=probabilities,
            outlier_scores=outlier_scores,
        )

    def get_cluster_stats(self, result: HDBSCANClusteringResult) -> Dict[str, Any]:
        """Get detailed statistics from clustering result."""
        if not result.clusters:
            return {
                "total_events": 0,
                "cluster_count": 0,
                "noise_count": 0,
                "rescued_count": 0,
                "singleton_rate": 0.0,
                "rescue_rate": 0.0,
                "avg_cluster_size": 0.0,
                "avg_probability": 0.0,
                "avg_cohesion": 0.0,
            }

        non_noise = [c for c in result.clusters if not c.cluster_id.startswith("noise-")]
        cluster_sizes = [c.event_count for c in non_noise] if non_noise else [0]
        cohesions = [c.cohesion_score for c in non_noise] if non_noise else [0.0]

        return {
            "total_events": result.total_events,
            "cluster_count": result.cluster_count,
            "noise_count": result.noise_count,
            "rescued_count": result.rescued_count,
            "singleton_rate": result.singleton_rate,
            "rescue_rate": result.rescue_rate,
            "avg_cluster_size": sum(cluster_sizes) / len(cluster_sizes) if cluster_sizes else 0.0,
            "avg_probability": (
                sum(result.probabilities) / len(result.probabilities)
                if result.probabilities
                else 0.0
            ),
            "avg_cohesion": sum(cohesions) / len(cohesions) if cohesions else 0.0,
        }
