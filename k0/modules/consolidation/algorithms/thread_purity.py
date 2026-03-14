"""
Thread Purity Correction for Episodic Clustering (Epic 6.2).

Post-clustering correction that splits impure episodes containing events
from multiple narrative threads into thread-pure sub-episodes.

Research basis:
    - R2_RESEARCH_FINAL.md Section 2.2.3.1
    - r2_final_pipeline.py correct_cluster_thread_purity()
    - 53% contamination in production (260/490 episodes impure)
    - UltraBERT thread merge DISABLED (6/21 false merges at cosine>=0.78)

Algorithm:
    1. For each cluster, group member events by narrative_thread_id
    2. If all events share one thread (or have no thread signal) -> pure, skip
    3. If multiple threads detected -> split into per-thread sub-clusters
    4. Events with no thread signal -> assign to majority thread
    5. Generate new cluster_id for each split sub-cluster

Spec Reference:
    - R2_EPISODIC_INTEGRATION_EPIC_PLAN.md Epic 6.2
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol, Sequence

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

NO_THREAD = "__no_thread__"


# =============================================================================
# Protocols
# =============================================================================


class ThreadableEvent(Protocol):
    """Protocol for events that expose narrative thread identity."""

    @property
    def event_id(self) -> str: ...

    @property
    def narrative_thread_id(self) -> Optional[str]: ...

    @property
    def goal_context(self) -> Optional[str]: ...

    @property
    def timestamp(self) -> int: ...


class SplittableCluster(Protocol):
    """Protocol for clusters that can be split by thread purity."""

    @property
    def cluster_id(self) -> str: ...

    @property
    def member_event_ids(self) -> List[str]: ...

    @property
    def cohesion_score(self) -> float: ...


# =============================================================================
# Correction Stats
# =============================================================================


@dataclass
class PurityCorrectionStats:
    """Observability stats from thread purity correction."""

    clusters_before: int = 0
    clusters_after: int = 0
    clusters_split: int = 0
    clusters_pure: int = 0
    events_reassigned: int = 0
    noise_clusters_skipped: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "clusters_before": self.clusters_before,
            "clusters_after": self.clusters_after,
            "clusters_split": self.clusters_split,
            "clusters_pure": self.clusters_pure,
            "events_reassigned": self.events_reassigned,
            "noise_clusters_skipped": self.noise_clusters_skipped,
        }


# =============================================================================
# Thread Purity Corrector
# =============================================================================


def _get_thread_group(event: ThreadableEvent) -> str:
    """Return the canonical thread group for an event.

    Priority:
        1. narrative_thread_id (primary MW v2 signal)
        2. goal_context prefixed with "goal:" (secondary)
        3. "__no_thread__" sentinel
    """
    tid = event.narrative_thread_id
    if tid:
        return tid
    goal = event.goal_context
    if goal:
        return f"goal:{goal}"
    return NO_THREAD


@dataclass
class ThreadPurityCorrector:
    """
    Post-clustering correction that splits thread-impure episodes.

    Operates on EpisodeCluster objects and an event lookup dict.
    Creates new sub-clusters for each distinct thread found in an
    impure cluster. Events with no thread signal are assigned to
    the majority thread.

    UltraBERT thread merge is DISABLED: research showed 6/21 false
    merges at cosine>=0.78. Each distinct narrative_thread_id stays
    as a separate thread group.
    """

    min_split_size: int = 2  # Sub-clusters smaller than this become noise

    def correct(
        self,
        clusters: Sequence[SplittableCluster],
        event_lookup: Dict[str, ThreadableEvent],
    ) -> tuple[List[SplittableCluster], PurityCorrectionStats]:
        """
        Apply thread purity correction to a list of clusters.

        Args:
            clusters: Episode clusters from HDBSCAN (may contain impure clusters)
            event_lookup: Mapping from event_id to event object with thread info

        Returns:
            Tuple of (corrected_clusters, stats)
        """
        from k0.pipelines.p03.phase_outputs import EpisodeCluster

        corrected: List[SplittableCluster] = []
        stats = PurityCorrectionStats(clusters_before=0)

        for cluster in clusters:
            member_ids = cluster.member_event_ids

            # Skip empty or single-event clusters
            if len(member_ids) <= 1:
                corrected.append(cluster)
                continue

            # Count as a real cluster
            stats.clusters_before += 1

            # Group events by thread
            thread_groups: Dict[str, List[str]] = defaultdict(list)
            for eid in member_ids:
                event = event_lookup.get(eid)
                if event is None:
                    thread_groups[NO_THREAD].append(eid)
                    continue
                group = _get_thread_group(event)
                thread_groups[group].append(eid)

            # Count real thread signals (exclude __no_thread__)
            real_threads = {k: v for k, v in thread_groups.items() if k != NO_THREAD}

            if len(real_threads) <= 1:
                # Pure cluster (one thread or all unthreaded) -> keep as-is
                corrected.append(cluster)
                stats.clusters_pure += 1
                stats.clusters_after += 1
                continue

            # Impure cluster -> split by thread
            stats.clusters_split += 1

            # Assign unthreaded events to the majority thread
            no_thread_eids = thread_groups.get(NO_THREAD, [])
            if no_thread_eids and real_threads:
                majority_thread = max(real_threads, key=lambda t: len(real_threads[t]))
                real_threads[majority_thread] = real_threads[majority_thread] + no_thread_eids
                stats.events_reassigned += len(no_thread_eids)

            # Build member_contexts index for splitting
            ctx_index = {eid: i for i, eid in enumerate(cluster.member_event_ids)}
            has_contexts = hasattr(cluster, "member_contexts") and cluster.member_contexts

            for thread_id, thread_eids in real_threads.items():
                if len(thread_eids) < self.min_split_size:
                    stats.noise_clusters_skipped += len(thread_eids)
                    continue

                sub_id = f"ep-{thread_id[:20]}-{uuid.uuid4().hex[:6]}"

                # Subset member_contexts in order
                sub_contexts = []
                if has_contexts:
                    for eid in thread_eids:
                        idx = ctx_index.get(eid)
                        if idx is not None and idx < len(cluster.member_contexts):
                            sub_contexts.append(cluster.member_contexts[idx])

                # Compute temporal bounds from events
                timestamps = []
                for eid in thread_eids:
                    ev = event_lookup.get(eid)
                    if ev is not None:
                        timestamps.append(ev.timestamp)

                sub_cluster = EpisodeCluster(
                    cluster_id=sub_id,
                    member_event_ids=list(thread_eids),
                    member_contexts=sub_contexts,
                    cohesion_score=cluster.cohesion_score,
                    temporal_start=min(timestamps) if timestamps else 0,
                    temporal_end=max(timestamps) if timestamps else 0,
                )
                corrected.append(sub_cluster)
                stats.clusters_after += 1

        return corrected, stats
