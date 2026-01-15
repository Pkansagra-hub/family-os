"""
EpisodicDBSCAN - DBSCAN clustering for episodic memory formation.

This module implements modified DBSCAN clustering that uses composite
distance (semantic + temporal) to group events into coherent episodes.

Spec Reference:
    - Dossier Appendix C.3.1: DBSCAN (Density-Based Clustering)
    - M4_EXECUTION.md Issue 4.2.3

Output: List[EpisodeCluster] where each cluster becomes a candidate st_epi record.

DBSCAN Labels:
    - -1: Noise (singleton) → micro-episode, is_noise=True
    - 0+: Cluster ID → group into episode

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence

import numpy as np
from sklearn.cluster import DBSCAN

from k0.modules.consolidation.algorithms.composite_distance import CompositeDistance, DBSCANParams
from k0.pipelines.p03.phase_outputs import EpisodeCluster

logger = logging.getLogger(__name__)


# =============================================================================
# Event Protocol
# =============================================================================


class ClusterableEvent(Protocol):
    """
    Protocol for event objects usable with EpisodicDBSCAN.

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
    def sentiment_score(self) -> float:
        """Sentiment score for dominant sentiment calculation."""
        ...

    @property
    def importance_score(self) -> float:
        """Importance score for weighting."""
        ...


# =============================================================================
# Clustering Result
# =============================================================================


@dataclass
class ClusteringResult:
    """
    Complete result from DBSCAN clustering.

    Contains clusters, metrics, and event assignments.
    """

    clusters: List[EpisodeCluster]
    """List of episode clusters (including noise clusters)."""

    total_events: int
    """Total events processed."""

    cluster_count: int
    """Number of non-noise clusters formed."""

    noise_count: int
    """Number of noise/singleton events."""

    labels: List[int]
    """DBSCAN labels for each input event (same order as input)."""

    @property
    def singleton_rate(self) -> float:
        """Ratio of noise events to total events."""
        if self.total_events == 0:
            return 0.0
        return self.noise_count / self.total_events


# =============================================================================
# EpisodicDBSCAN Class
# =============================================================================


class EpisodicDBSCAN:
    """
    Modified DBSCAN for episodic memory clustering.

    Uses composite distance (semantic + temporal) instead of spatial distance.
    Wraps scikit-learn DBSCAN with precomputed distance matrix.

    Spec: Dossier Appendix C.3.1

    Output Interpretation:
        - Semantically similar + temporally proximate events cluster together
        - Noise events (label=-1) become individual micro-episodes
        - Each cluster becomes a candidate st_epi record

    Usage:
        params = DBSCANParams(eps=0.15, min_samples=2)  # eps=0.15 for UltraBERT
        dbscan = EpisodicDBSCAN(params)

        result = dbscan.cluster(events)
        for cluster in result.clusters:
            print(f"Episode {cluster.cluster_id}: {cluster.event_count} events")
    """

    def __init__(self, params: Optional[DBSCANParams] = None):
        """
        Initialize EpisodicDBSCAN.

        Args:
            params: DBSCAN parameters. Uses defaults if None.
        """
        self.params = params or DBSCANParams()
        self.params.validate()
        self.distance_calculator = CompositeDistance(self.params)

    def cluster(
        self,
        events: Sequence[ClusterableEvent],
    ) -> ClusteringResult:
        """
        Run DBSCAN clustering on events.

        Args:
            events: List of events (pre-split by EpisodeSplitter)

        Returns:
            ClusteringResult with clusters and metadata

        Raises:
            ValueError: If any event lacks embedding_768
        """
        if len(events) == 0:
            return ClusteringResult(
                clusters=[],
                total_events=0,
                cluster_count=0,
                noise_count=0,
                labels=[],
            )

        # Check if enough events for clustering
        if len(events) < self.params.min_samples:
            # Not enough events - all become noise
            return self._create_all_noise_result(events)

        # Step 1: Build distance matrix using CompositeDistance
        distances = self.distance_calculator.build_distance_matrix(list(events))

        # Step 1b: Cap infinity values to a finite value (sklearn can't handle inf)
        # Using a large value that is certainly > eps to ensure events won't cluster
        max_finite_distance = 1e10
        distances = np.clip(distances, 0.0, max_finite_distance)

        # Step 2: Run scikit-learn DBSCAN with precomputed distances
        sklearn_dbscan = DBSCAN(
            eps=self.params.eps,
            min_samples=self.params.min_samples,
            metric="precomputed",
        )
        sklearn_dbscan.fit(distances)

        labels = sklearn_dbscan.labels_.tolist()

        # Step 3: Group events by cluster label
        label_to_events: Dict[int, List[ClusterableEvent]] = {}
        for idx, label in enumerate(labels):
            if label not in label_to_events:
                label_to_events[label] = []
            label_to_events[label].append(events[idx])

        # Step 4: Create EpisodeCluster objects
        clusters: List[EpisodeCluster] = []
        cluster_count = 0
        noise_count = 0

        for label, cluster_events in label_to_events.items():
            cluster = self._create_cluster(cluster_events, label)
            clusters.append(cluster)

            if label == -1:
                # Noise: each event is its own micro-episode
                noise_count += len(cluster_events)
            else:
                cluster_count += 1

        return ClusteringResult(
            clusters=clusters,
            total_events=len(events),
            cluster_count=cluster_count,
            noise_count=noise_count,
            labels=labels,
        )

    def cluster_and_update_events(
        self,
        events: List[Any],
    ) -> ClusteringResult:
        """
        Cluster events AND update their clustering fields in-place.

        This method mutates the event objects to set:
            - cluster_id
            - cluster_label
            - is_noise
            - centroid_distance

        Args:
            events: List of mutable event objects with assign_cluster() method

        Returns:
            ClusteringResult with clusters and metadata
        """
        result = self.cluster(events)

        # Build cluster_id lookup
        cluster_id_by_label: Dict[int, str] = {}
        for cluster in result.clusters:
            # For noise, each event gets its own cluster_id, so we handle differently
            if not any(
                eid in [e.event_id for e in events if hasattr(e, "event_id")]
                for eid in cluster.member_event_ids
            ):
                continue
            # Find the label for this cluster
            for idx, event in enumerate(events):
                if event.event_id in cluster.member_event_ids:
                    label = result.labels[idx]
                    cluster_id_by_label[label] = cluster.cluster_id
                    break

        # Update each event
        for idx, event in enumerate(events):
            label = result.labels[idx]
            is_noise = label == -1

            # Find the cluster this event belongs to
            for cluster in result.clusters:
                if event.event_id in cluster.member_event_ids:
                    cluster_id = cluster.cluster_id
                    break
            else:
                cluster_id = f"noise-{uuid.uuid4().hex[:26]}"

            # Update event if it has assign_cluster method
            if hasattr(event, "assign_cluster"):
                event.assign_cluster(
                    cluster_id=cluster_id,
                    label=label,
                    distance=0.0,  # Centroid distance computed later by CentroidCalculator
                )
            elif hasattr(event, "mark_as_noise") and is_noise:
                event.mark_as_noise()

        return result

    def _create_cluster(
        self,
        events: List[ClusterableEvent],
        label: int,
    ) -> EpisodeCluster:
        """
        Create EpisodeCluster from grouped events.

        Args:
            events: Events belonging to this cluster
            label: DBSCAN label (-1 for noise)

        Returns:
            EpisodeCluster with computed properties
        """
        is_noise = label == -1

        # Generate cluster ID (26-char hex similar to ULID length)
        if is_noise:
            # For noise, we create a single cluster containing all noise events
            # Each noise event conceptually is its own micro-episode, but we group for efficiency
            cluster_id = f"noise-{uuid.uuid4().hex[:26]}"
        else:
            cluster_id = uuid.uuid4().hex[:26]

        # Temporal bounds (milliseconds)
        timestamps = [e.timestamp for e in events]
        temporal_start = min(timestamps)
        temporal_end = max(timestamps)

        # Dominant sentiment (average)
        sentiments = [
            getattr(e, "sentiment_score", 0.0) for e in events if hasattr(e, "sentiment_score")
        ]
        dominant_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        # Cohesion score (intra-cluster similarity)
        cohesion = self._compute_cohesion(events)

        return EpisodeCluster(
            cluster_id=cluster_id,
            member_event_ids=[e.event_id for e in events],
            dominant_sentiment=dominant_sentiment,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            cohesion_score=cohesion,
        )

    def _compute_cohesion(
        self,
        events: List[ClusterableEvent],
    ) -> float:
        """
        Compute intra-cluster similarity (cohesion).

        Average pairwise cosine similarity within cluster.
        Returns 1.0 for singleton clusters.

        Args:
            events: Events in the cluster

        Returns:
            Cohesion score in [0.0, 1.0] where 1.0 = perfect similarity
        """
        if len(events) < 2:
            return 1.0

        # Collect embeddings
        embeddings: List[np.ndarray] = []
        for event in events:
            if event.embedding_768 is not None:
                embeddings.append(np.asarray(event.embedding_768, dtype=np.float32))

        if len(embeddings) < 2:
            return 1.0

        # Compute pairwise cosine similarities
        total_sim = 0.0
        count = 0

        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                # Cosine similarity
                norm_i = np.linalg.norm(embeddings[i])
                norm_j = np.linalg.norm(embeddings[j])

                if norm_i > 1e-10 and norm_j > 1e-10:
                    sim = np.dot(embeddings[i], embeddings[j]) / (norm_i * norm_j)
                    total_sim += max(0.0, min(1.0, sim))  # Clamp to [0, 1]
                    count += 1

        return total_sim / count if count > 0 else 1.0

    def _create_all_noise_result(
        self,
        events: Sequence[ClusterableEvent],
    ) -> ClusteringResult:
        """
        Create result where all events are noise (below min_samples).

        Args:
            events: Events to mark as noise

        Returns:
            ClusteringResult with all noise
        """
        clusters: List[EpisodeCluster] = []
        labels: List[int] = []

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

        return ClusteringResult(
            clusters=clusters,
            total_events=len(events),
            cluster_count=0,
            noise_count=len(events),
            labels=labels,
        )

    def get_cluster_stats(
        self,
        result: ClusteringResult,
    ) -> Dict[str, Any]:
        """
        Get detailed statistics from clustering result.

        Useful for observability and debugging.

        Args:
            result: ClusteringResult from cluster() call

        Returns:
            Dictionary with statistics
        """
        if not result.clusters:
            return {
                "total_events": 0,
                "cluster_count": 0,
                "noise_count": 0,
                "singleton_rate": 0.0,
                "avg_cluster_size": 0.0,
                "min_cluster_size": 0,
                "max_cluster_size": 0,
                "avg_cohesion": 0.0,
            }

        # Non-noise clusters only for size stats
        non_noise = [c for c in result.clusters if not c.cluster_id.startswith("noise-")]
        cluster_sizes = [c.event_count for c in non_noise] if non_noise else [0]
        cohesions = [c.cohesion_score for c in non_noise] if non_noise else [0.0]

        return {
            "total_events": result.total_events,
            "cluster_count": result.cluster_count,
            "noise_count": result.noise_count,
            "singleton_rate": result.singleton_rate,
            "avg_cluster_size": sum(cluster_sizes) / len(cluster_sizes) if cluster_sizes else 0.0,
            "min_cluster_size": min(cluster_sizes) if cluster_sizes else 0,
            "max_cluster_size": max(cluster_sizes) if cluster_sizes else 0,
            "avg_cohesion": sum(cohesions) / len(cohesions) if cohesions else 0.0,
        }
