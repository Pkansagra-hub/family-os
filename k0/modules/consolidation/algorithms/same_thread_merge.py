"""
Same-Thread Episode Merge (Epic 6.3).

Post-purity-correction merge that consolidates small same-thread episode
fragments into coherent episodes using union-find with path compression.

Research basis:
    - R2_RESEARCH_FINAL.md Section 2.2.3.2
    - r2_final_pipeline.py merge_same_thread_clusters()
    - 531->260 clusters, 271 merged in research pipeline
    - maya_fears: 183 fragments -> single coherent episode

Algorithm:
    1. Group clusters by dominant narrative thread (>=80% purity)
    2. For each thread group, compute per-cluster centroids and temporal bounds
    3. Pairwise merge candidates: centroid_sim >= 0.70 AND temporal_gap <= 4h
    4. Union-find with path compression for transitive merge closure
    5. Merge events from all clusters in a union-find group into one episode

Proven parameters:
    - centroid_sim_threshold: 0.70
    - max_temporal_gap_ms: 14_400_000 (4 hours)
    - purity_threshold: 0.80

Spec Reference:
    - R2_EPISODIC_INTEGRATION_EPIC_PLAN.md Epic 6.3
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol, Sequence, Tuple

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

NO_THREAD = "__no_thread__"


# =============================================================================
# Protocols
# =============================================================================


class MergeableEvent(Protocol):
    """Event protocol for same-thread merge (embedding + thread + timestamp)."""

    @property
    def event_id(self) -> str: ...

    @property
    def timestamp(self) -> int: ...

    @property
    def narrative_thread_id(self) -> Optional[str]: ...

    @property
    def embedding_768(self) -> Optional[List[float]]: ...


class MergeableCluster(Protocol):
    """Cluster protocol for same-thread merge."""

    @property
    def cluster_id(self) -> str: ...

    @property
    def member_event_ids(self) -> List[str]: ...

    @property
    def cohesion_score(self) -> float: ...


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class SameThreadMergeConfig:
    """Configuration for same-thread merge.

    Proven defaults from research pipeline (r2_final_pipeline.py).
    """

    centroid_sim_threshold: float = 0.70
    max_temporal_gap_ms: int = 14_400_000  # 4 hours in milliseconds
    purity_threshold: float = 0.80  # Minimum thread purity to be eligible for merge


# =============================================================================
# Stats
# =============================================================================


@dataclass
class SameThreadMergeStats:
    """Observability stats from same-thread merge."""

    clusters_before: int = 0
    clusters_after: int = 0
    clusters_merged: int = 0
    merge_groups_formed: int = 0
    largest_merged_cluster_size: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "clusters_before": self.clusters_before,
            "clusters_after": self.clusters_after,
            "clusters_merged": self.clusters_merged,
            "merge_groups_formed": self.merge_groups_formed,
            "largest_merged_cluster_size": self.largest_merged_cluster_size,
        }


# =============================================================================
# Helpers
# =============================================================================


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(va * vb for va, vb in zip(a, b))
    na = sum(v * v for v in a) ** 0.5
    nb = sum(v * v for v in b) ** 0.5
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _cluster_centroid(
    member_event_ids: List[str],
    event_lookup: Dict[str, MergeableEvent],
) -> Optional[List[float]]:
    """Mean embedding across cluster events that have embeddings."""
    vecs = []
    for eid in member_event_ids:
        ev = event_lookup.get(eid)
        if ev is not None and ev.embedding_768:
            vecs.append(ev.embedding_768)
    if not vecs:
        return None
    dim = len(vecs[0])
    centroid = [0.0] * dim
    for v in vecs:
        for i in range(dim):
            centroid[i] += v[i]
    n = len(vecs)
    return [c / n for c in centroid]


def _temporal_bounds(
    member_event_ids: List[str],
    event_lookup: Dict[str, MergeableEvent],
) -> Tuple[int, int]:
    """Return (min_ts, max_ts) for member events."""
    timestamps = []
    for eid in member_event_ids:
        ev = event_lookup.get(eid)
        if ev is not None:
            timestamps.append(ev.timestamp)
    if not timestamps:
        return (0, 0)
    return (min(timestamps), max(timestamps))


def _dominant_thread(
    member_event_ids: List[str],
    event_lookup: Dict[str, MergeableEvent],
) -> Tuple[Optional[str], float]:
    """Return (dominant_thread_id, purity_ratio) for a cluster."""
    threads: Counter[str] = Counter()
    for eid in member_event_ids:
        ev = event_lookup.get(eid)
        if ev is not None and ev.narrative_thread_id:
            threads[ev.narrative_thread_id] += 1
    if not threads:
        return (None, 0.0)
    total = sum(threads.values())
    top_thread, top_count = threads.most_common(1)[0]
    return (top_thread, top_count / total if total > 0 else 0.0)


# =============================================================================
# SameThreadMerger
# =============================================================================


@dataclass
class SameThreadMerger:
    """Post-purity-correction merger that consolidates same-thread fragments.

    Uses union-find with path compression for transitive merge closure.
    Two clusters merge if:
        1. They share the same dominant narrative thread (>=80% pure)
        2. Centroid cosine similarity >= 0.70
        3. Temporal gap between closest endpoints <= 4h
    """

    config: SameThreadMergeConfig = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = SameThreadMergeConfig()

    def merge(
        self,
        clusters: Sequence[MergeableCluster],
        event_lookup: Dict[str, MergeableEvent],
    ) -> Tuple[List[MergeableCluster], SameThreadMergeStats]:
        """Merge same-thread episode fragments.

        Args:
            clusters: Episode clusters (typically post-purity-correction).
            event_lookup: event_id -> event with embedding_768 and narrative_thread_id.

        Returns:
            (merged_clusters, stats)
        """
        from k0.pipelines.p03.phase_outputs import EpisodeCluster

        stats = SameThreadMergeStats()

        # Filter: only process multi-event clusters
        multi_event = [c for c in clusters if len(c.member_event_ids) > 1]
        single_event = [c for c in clusters if len(c.member_event_ids) <= 1]

        stats.clusters_before = len(multi_event)

        if len(multi_event) < 2:
            stats.clusters_after = stats.clusters_before
            return list(clusters), stats

        # Group clusters by dominant thread
        thread_to_indices: Dict[str, List[int]] = defaultdict(list)
        for idx, cluster in enumerate(multi_event):
            thread_id, purity = _dominant_thread(cluster.member_event_ids, event_lookup)
            if thread_id is None or purity < self.config.purity_threshold:
                thread_to_indices[NO_THREAD].append(idx)
            else:
                thread_to_indices[thread_id].append(idx)

        # Union-find
        parent: Dict[int, int] = {i: i for i in range(len(multi_event))}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # Pre-compute centroids and temporal bounds per cluster
        centroids: Dict[int, Optional[List[float]]] = {}
        time_ranges: Dict[int, Tuple[int, int]] = {}

        for thread_id, idxs in thread_to_indices.items():
            if thread_id == NO_THREAD or len(idxs) < 2:
                continue

            for idx in idxs:
                if idx not in centroids:
                    centroids[idx] = _cluster_centroid(
                        multi_event[idx].member_event_ids, event_lookup
                    )
                    time_ranges[idx] = _temporal_bounds(
                        multi_event[idx].member_event_ids, event_lookup
                    )

            # Pairwise merge within same thread
            for i, idx_a in enumerate(idxs):
                for idx_b in idxs[i + 1 :]:
                    if find(idx_a) == find(idx_b):
                        continue

                    ca, cb = centroids[idx_a], centroids[idx_b]
                    if ca is None or cb is None:
                        continue

                    sim = _cosine_sim(ca, cb)
                    if sim < self.config.centroid_sim_threshold:
                        continue

                    # Temporal gap: distance between closest endpoints
                    ta_start, ta_end = time_ranges[idx_a]
                    tb_start, tb_end = time_ranges[idx_b]
                    gap = max(0, max(ta_start, tb_start) - min(ta_end, tb_end))
                    if gap > self.config.max_temporal_gap_ms:
                        continue

                    union(idx_a, idx_b)

        # Build merge groups
        merge_groups: Dict[int, List[int]] = defaultdict(list)
        for idx in range(len(multi_event)):
            root = find(idx)
            merge_groups[root].append(idx)

        # Construct merged clusters
        result: List[MergeableCluster] = []
        for root, members in merge_groups.items():
            if len(members) == 1:
                result.append(multi_event[members[0]])
            else:
                # Merge all events
                all_event_ids: List[str] = []
                all_contexts: list = []
                best_cohesion = 0.0
                for m in members:
                    all_event_ids.extend(multi_event[m].member_event_ids)
                    if hasattr(multi_event[m], "member_contexts"):
                        all_contexts.extend(multi_event[m].member_contexts)
                    best_cohesion = max(best_cohesion, multi_event[m].cohesion_score)

                # Compute temporal bounds for merged cluster
                ts_start, ts_end = _temporal_bounds(all_event_ids, event_lookup)

                merged_id = f"merged-{multi_event[root].cluster_id[:20]}-{uuid.uuid4().hex[:6]}"
                merged_cluster = EpisodeCluster(
                    cluster_id=merged_id,
                    member_event_ids=all_event_ids,
                    member_contexts=all_contexts,
                    cohesion_score=best_cohesion,
                    temporal_start=ts_start,
                    temporal_end=ts_end,
                )
                result.append(merged_cluster)

                stats.clusters_merged += len(members) - 1
                stats.merge_groups_formed += 1
                stats.largest_merged_cluster_size = max(
                    stats.largest_merged_cluster_size, len(all_event_ids)
                )

        # Re-add single-event clusters
        result.extend(single_event)

        stats.clusters_after = len([c for c in result if len(c.member_event_ids) > 1])
        return result, stats
