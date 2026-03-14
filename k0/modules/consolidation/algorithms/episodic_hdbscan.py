"""
EpisodicHDBSCAN - Hierarchical density-based clustering for episodic memory formation.

This module implements HDBSCAN clustering with soft noise rescue
for robust episode formation.

Benefits:
    - Automatic multi-resolution clustering (no fixed eps required)
    - Soft cluster membership probabilities
    - Outlier scores for noise rescue
    - Handles varying density naturally

Spec Reference:
    - Dossier Appendix C.3.1: Clustering algorithm
    - M4_EXECUTION.md Issue 4.2.3

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Set, Tuple

import hdbscan
import numpy as np

from k0.modules.consolidation.algorithms.composite_distance import (
    ClusteringDistanceParams,
    CompositeDistance,
    EnsembleDistance,
    EnsembleDistanceConfig,
)
from k0.modules.consolidation.algorithms.hebbian_boost import (
    CoOccurrenceEdge,
    HebbinaBoostConfig,
    apply_hebbian_boost,
)
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
        - rescue_max_distance: Max distance to assign noise to existing cluster
        - weak_cluster_max_distance: Max distance between noise points for weak cluster
        - rescue_context_enabled: Enable context-aware rescue scoring (Epic 3.4.2)
        - rescue_w_distance: Weight for distance component in rescue score
        - rescue_w_narrative: Weight for narrative thread match in rescue score
        - rescue_w_social: Weight for participant overlap in rescue score
        - rescue_w_spatial: Weight for place match in rescue score
        - rescue_score_threshold: Min rescue score to allow rescue
        - temporal_weight: Weight for temporal distance [0,1]
        - max_temporal_gap_hours: Hard limit for temporal proximity
    """

    min_cluster_size: int = 2
    min_samples: int = 1  # Lower = less noise, more inclusive
    cluster_selection_epsilon: float = 0.0  # 0 = automatic, >0 = flat cut
    cluster_selection_method: str = "leaf"  # 'leaf' preserves small clusters
    noise_rescue_threshold: float = 0.5  # Rescue noise with outlier_score < this
    rescue_max_distance: float = (
        0.3  # Max distance to assign noise to existing cluster (Epic 3.4.1)
    )
    weak_cluster_max_distance: float = (
        0.2  # Max distance between noise for weak cluster (Epic 3.4.1)
    )

    # Context-aware rescue scoring (Epic 3.4.2)
    rescue_context_enabled: bool = True  # Enable context-aware rescue
    rescue_w_distance: float = 0.40  # Weight for (1 - normalized_distance)
    rescue_w_narrative: float = 0.30  # Weight for narrative thread match
    rescue_w_social: float = 0.15  # Weight for participant overlap
    rescue_w_spatial: float = 0.15  # Weight for place match
    rescue_score_threshold: float = 0.35  # Min combined score to allow rescue

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
        if self.rescue_max_distance < 0.0:
            raise ValueError(f"rescue_max_distance must be >= 0, got {self.rescue_max_distance}")
        if self.weak_cluster_max_distance < 0.0:
            raise ValueError(
                f"weak_cluster_max_distance must be >= 0, got {self.weak_cluster_max_distance}"
            )
        if self.cluster_selection_method not in ("eom", "leaf"):
            raise ValueError(
                f"cluster_selection_method must be 'eom' or 'leaf', got {self.cluster_selection_method}"
            )

    def to_distance_params(self) -> ClusteringDistanceParams:
        """Convert to ClusteringDistanceParams for CompositeDistance compatibility."""
        return ClusteringDistanceParams(
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
            "rescue_max_distance": self.rescue_max_distance,
            "weak_cluster_max_distance": self.weak_cluster_max_distance,
            "rescue_context_enabled": self.rescue_context_enabled,
            "rescue_w_distance": self.rescue_w_distance,
            "rescue_w_narrative": self.rescue_w_narrative,
            "rescue_w_social": self.rescue_w_social,
            "rescue_w_spatial": self.rescue_w_spatial,
            "rescue_score_threshold": self.rescue_score_threshold,
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
# Context Profile (Epic 3.4.2)
# =============================================================================


@dataclass
class _ClusterProfile:
    """Context profile for a cluster, used during rescue scoring."""

    dominant_thread: Optional[str]
    participants: Set[str]
    dominant_place: Optional[str]
    # Mutable counters for incremental updates during rescue
    thread_counts: Dict[str, int] = None  # type: ignore[assignment]
    place_counts: Dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.thread_counts is None:
            self.thread_counts = {}
        if self.place_counts is None:
            self.place_counts = {}


def _parse_participants(raw: Any) -> Set[str]:
    """Parse participant identifiers from various formats.

    Handles JSON string, list, or already-parsed data.
    Returns empty set on failure.
    """
    if not raw:
        return set()
    if isinstance(raw, set):
        return raw
    if isinstance(raw, (list, tuple)):
        return {str(p) for p in raw if p}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return {str(p) for p in parsed if p}
        except (json.JSONDecodeError, TypeError):
            pass
    return set()


def _most_common(items: List[str]) -> Optional[str]:
    """Return the most common item, or None if empty."""
    if not items:
        return None
    counts = Counter(items)
    return counts.most_common(1)[0][0]


# =============================================================================
# Clustering Result
# =============================================================================


@dataclass
class HDBSCANClusteringResult:
    """
    Complete result from HDBSCAN clustering.

    Includes soft membership probabilities and outlier scores.
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

    distance_matrix: Optional[np.ndarray] = None
    """Precomputed distance matrix used for clustering (NxN float64).
    Retained for downstream silhouette computation. Set to None for
    degenerate cases (empty batch, too-small batch)."""

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

    Usage:
        params = HDBSCANParams(min_cluster_size=2, noise_rescue_threshold=0.5)
        clusterer = EpisodicHDBSCAN(params)

        result = clusterer.cluster(events)
        for cluster in result.clusters:
            print(f"Episode {cluster.cluster_id}: {cluster.event_count} events")
    """

    def __init__(
        self,
        params: Optional[HDBSCANParams] = None,
        ensemble_config: Optional[EnsembleDistanceConfig] = None,
        hebbian_config: Optional[HebbinaBoostConfig] = None,
    ):
        """
        Initialize EpisodicHDBSCAN.

        Args:
            params: HDBSCAN parameters. Uses defaults if None.
            ensemble_config: If provided, use 6D ensemble distance instead
                of legacy 2D composite distance. Takes precedence over params
                distance settings.
            hebbian_config: If provided, apply Hebbian co-occurrence distance
                boost after building the distance matrix. Requires a
                co-occurrence graph to be passed to cluster().
        """
        self.params = params or HDBSCANParams()
        self.params.validate()

        if ensemble_config is not None:
            self.distance_calculator = EnsembleDistance(ensemble_config)
        else:
            # Legacy 2D distance path
            distance_params = self.params.to_distance_params()
            self.distance_calculator = CompositeDistance(distance_params)

        self._hebbian_config = hebbian_config or HebbinaBoostConfig(enabled=False)

    def cluster(
        self,
        events: Sequence[ClusterableEvent],
        cooccurrence_graph: Optional[Dict[tuple, CoOccurrenceEdge]] = None,
    ) -> HDBSCANClusteringResult:
        """
        Run HDBSCAN clustering on events with noise rescue.

        Args:
            events: List of events with embeddings and timestamps
            cooccurrence_graph: Optional co-occurrence graph for Hebbian boost.
                Built by hebbian_boost.build_cooccurrence_graph().
                Only used when hebbian_config.enabled=True.

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
                distance_matrix=None,
            )

        # Not enough events - all become noise
        if len(events) < self.params.min_cluster_size:
            return self._create_all_noise_result(events)

        # Step 1: Build distance matrix using CompositeDistance
        distances = self.distance_calculator.build_distance_matrix(list(events))

        # Step 1b: Apply Hebbian co-occurrence boost (Epic 5.1)
        if self._hebbian_config.enabled and cooccurrence_graph:
            distances, _heb_diag = apply_hebbian_boost(
                distances, list(events), cooccurrence_graph, self._hebbian_config
            )

        # Cap infinity values (HDBSCAN can't handle inf)
        max_finite_distance = 1e10
        distances = np.clip(distances, 0.0, max_finite_distance)

        # Step 2: Run HDBSCAN clustering
        labels, probabilities, outlier_scores = self._run_hdbscan(distances)

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
            distance_matrix=distances,
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

    def _rescue_noise(
        self,
        events: Sequence[ClusterableEvent],
        labels: List[int],
        probabilities: List[float],
        outlier_scores: List[float],
        distances: np.ndarray,
    ) -> Tuple[List[int], List[int]]:
        """
        Rescue noise points with low outlier scores (Epic 3.4.2: context-aware).

        Strategy:
            1. Find noise points with outlier_score < threshold
            2. Compute context profiles for each existing cluster
            3. Score rescue candidates using distance + context
            4. Assign to nearest cluster if score passes OR create weak episode

        Context signals (when rescue_context_enabled):
            - narrative_thread_id match/mismatch with cluster dominant thread
            - participants_json Jaccard overlap with cluster participants
            - place_id match with cluster dominant place

        Falls back to distance-only when context fields are absent.

        Args:
            events: All events (implementing ClusterableEvent protocol)
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
        rescued_indices: set[int] = set()

        # Find noise points eligible for rescue
        noise_indices = [i for i in range(n) if labels[i] == -1]
        rescuable = [(i, outlier_scores[i]) for i in noise_indices if outlier_scores[i] < threshold]

        if not rescuable:
            return labels, rescued_indices

        # Build cluster context profiles for context-aware rescue
        cluster_profiles: Dict[int, _ClusterProfile] = {}
        if self.params.rescue_context_enabled:
            cluster_profiles = self._build_cluster_profiles(events, labels)

        # Sort by outlier score (rescue most confident first)
        rescuable.sort(key=lambda x: x[1])

        for idx, score in rescuable:
            if labels[idx] != -1:
                continue

            # Find nearest cluster and compute rescue score
            best_cluster = -1
            best_distance = float("inf")
            best_rescue_score = -1.0

            for j in range(n):
                if labels[j] >= 0:  # j is in a cluster
                    if distances[idx, j] < best_distance:
                        best_distance = distances[idx, j]
                        best_cluster = labels[j]

            if best_cluster >= 0 and best_distance < self.params.rescue_max_distance:
                if self.params.rescue_context_enabled and best_cluster in cluster_profiles:
                    best_rescue_score = self._compute_rescue_score(
                        events[idx], best_distance, cluster_profiles[best_cluster]
                    )
                    if best_rescue_score >= self.params.rescue_score_threshold:
                        labels[idx] = best_cluster
                        rescued_indices.add(idx)
                        # Update cluster profile with new member
                        self._update_cluster_profile(cluster_profiles[best_cluster], events[idx])
                        logger.debug(
                            "Rescued event %s to cluster %d "
                            "(score=%.3f, distance=%.3f, outlier=%.3f)",
                            events[idx].event_id,
                            best_cluster,
                            best_rescue_score,
                            best_distance,
                            score,
                        )
                    else:
                        logger.debug(
                            "Rejected rescue of %s to cluster %d "
                            "(score=%.3f < threshold=%.3f, distance=%.3f)",
                            events[idx].event_id,
                            best_cluster,
                            best_rescue_score,
                            self.params.rescue_score_threshold,
                            best_distance,
                        )
                else:
                    # Distance-only rescue (context disabled or no profile)
                    labels[idx] = best_cluster
                    rescued_indices.add(idx)
                    logger.debug(
                        "Rescued event %s to cluster %d "
                        "(distance-only, distance=%.3f, outlier=%.3f)",
                        events[idx].event_id,
                        best_cluster,
                        best_distance,
                        score,
                    )
            else:
                # Create new weak cluster from nearby noise points
                nearby_noise = [
                    j
                    for j in noise_indices
                    if j != idx
                    and labels[j] == -1
                    and distances[idx, j] < self.params.weak_cluster_max_distance
                    and outlier_scores[j] < threshold
                ]

                if nearby_noise:
                    # Create new cluster
                    new_cluster_id = max(labels) + 1 if max(labels) >= 0 else 0
                    labels[idx] = new_cluster_id
                    rescued_indices.add(idx)

                    for j in nearby_noise:
                        if labels[j] != -1:
                            continue
                        labels[j] = new_cluster_id
                        rescued_indices.add(j)

                    logger.debug(
                        "Created weak cluster %d with %d events",
                        new_cluster_id,
                        len(nearby_noise) + 1,
                    )

        return labels, sorted(rescued_indices)

    # -------------------------------------------------------------------------
    # Context-Aware Rescue Helpers (Epic 3.4.2)
    # -------------------------------------------------------------------------

    def _build_cluster_profiles(
        self,
        events: Sequence[ClusterableEvent],
        labels: List[int],
    ) -> Dict[int, "_ClusterProfile"]:
        """Build context profiles for each cluster.

        Extracts dominant narrative_thread, aggregated participants,
        and dominant place_id from cluster members using getattr
        for graceful fallback when fields are absent.
        """
        cluster_events: Dict[int, List[int]] = {}
        for i, label in enumerate(labels):
            if label >= 0:
                cluster_events.setdefault(label, []).append(i)

        profiles: Dict[int, _ClusterProfile] = {}
        for cluster_id, indices in cluster_events.items():
            threads: List[str] = []
            participants: Set[str] = set()
            places: List[str] = []

            for i in indices:
                evt = events[i]
                thread = getattr(evt, "narrative_thread_id", None)
                if thread:
                    threads.append(thread)

                place = getattr(evt, "place_id", None)
                if place:
                    places.append(place)

                pjson = getattr(evt, "participants_json", None)
                if pjson:
                    participants.update(_parse_participants(pjson))

            profiles[cluster_id] = _ClusterProfile(
                dominant_thread=_most_common(threads),
                participants=participants,
                dominant_place=_most_common(places),
                thread_counts=dict(Counter(threads)),
                place_counts=dict(Counter(places)),
            )

        return profiles

    def _compute_rescue_score(
        self,
        event: ClusterableEvent,
        distance: float,
        profile: "_ClusterProfile",
    ) -> float:
        """Compute context-aware rescue score for a noise event.

        Score = w_distance * distance_score
              + w_narrative * narrative_score
              + w_social * social_score
              + w_spatial * spatial_score

        Falls back to distance-only weighting when context is absent
        on either the event or the cluster profile.

        Returns:
            Score in [0, 1]. Higher = better rescue candidate.
        """
        p = self.params

        # Distance component: closer = higher score
        # Normalize: 0 distance -> 1.0, rescue_max_distance -> 0.0
        if p.rescue_max_distance > 0:
            distance_score = max(0.0, 1.0 - distance / p.rescue_max_distance)
        else:
            distance_score = 0.0

        # Context signal scores (default to neutral 0.5 when missing)
        narrative_score = 0.5
        social_score = 0.5
        spatial_score = 0.5
        context_available = False

        # Narrative: thread match
        event_thread = getattr(event, "narrative_thread_id", None)
        if event_thread and profile.dominant_thread:
            context_available = True
            if event_thread == profile.dominant_thread:
                narrative_score = 1.0  # Same thread -> strong rescue signal
            else:
                narrative_score = 0.0  # Different thread -> reject

        # Social: participant overlap (Jaccard)
        event_pjson = getattr(event, "participants_json", None)
        event_participants = _parse_participants(event_pjson) if event_pjson else set()
        if event_participants and profile.participants:
            context_available = True
            intersection = len(event_participants & profile.participants)
            union = len(event_participants | profile.participants)
            social_score = intersection / union if union > 0 else 0.5

        # Spatial: place match
        event_place = getattr(event, "place_id", None)
        if event_place and profile.dominant_place:
            context_available = True
            spatial_score = 1.0 if event_place == profile.dominant_place else 0.0

        if not context_available:
            # No context signals available -> distance-only scoring
            return distance_score

        score = (
            p.rescue_w_distance * distance_score
            + p.rescue_w_narrative * narrative_score
            + p.rescue_w_social * social_score
            + p.rescue_w_spatial * spatial_score
        )

        return score

    @staticmethod
    def _update_cluster_profile(
        profile: "_ClusterProfile",
        event: ClusterableEvent,
    ) -> None:
        """Update cluster profile after rescuing an event into it."""
        thread = getattr(event, "narrative_thread_id", None)
        if thread:
            profile.thread_counts[thread] = profile.thread_counts.get(thread, 0) + 1
            # Recompute dominant
            profile.dominant_thread = max(
                profile.thread_counts, key=profile.thread_counts.get  # type: ignore[arg-type]
            )

        pjson = getattr(event, "participants_json", None)
        if pjson:
            profile.participants.update(_parse_participants(pjson))

        place = getattr(event, "place_id", None)
        if place:
            profile.place_counts[place] = profile.place_counts.get(place, 0) + 1
            profile.dominant_place = max(
                profile.place_counts, key=profile.place_counts.get  # type: ignore[arg-type]
            )

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
            distance_matrix=None,
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
