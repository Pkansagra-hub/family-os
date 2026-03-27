"""Micro-fragment absorption: merge tiny episodes into nearby compatible scenes.

A micro-fragment is an episode with very few events (<=absorb_max_events)
that typically represents annotation fragments rather than coherent memories.
Absorption merges these into nearby larger episodes when temporally and
semantically compatible.

POC Evidence:
  - Phase 9 reduced micro-dust from 85% to 27% of episodes
  - Absorption used temporal proximity (6h) + cosine similarity (0.50)

M9.10 Milestone: Universal Reconciliation Engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple

    from k0.modules.consolidation.algorithms.centroid_calculator import EpisodeCandidate
    from k0.pipelines.p03.phase_outputs import EpisodeCluster

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FragmentAbsorptionConfig:
    """Tunable parameters for micro-fragment absorption.

    Defaults are POC Phase 9 validated values.
    """

    absorb_max_events: int = 4
    """Fragments with <= this many events are absorption candidates."""

    absorb_max_gap_hours: float = 6.0
    """Only absorb into scenes within this temporal distance (hours)."""

    absorb_min_similarity: float = 0.50
    """Cosine similarity threshold for absorption."""

    max_absorbed_duration_ms: int = 18 * 3_600_000
    """Reject absorption if resulting episode span would exceed this (ms)."""


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


@dataclass
class FragmentAbsorptionStats:
    """Statistics from a fragment absorption run."""

    fragments_found: int = 0
    fragments_absorbed: int = 0
    fragments_orphaned: int = 0
    scenes_grew: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "fragments_found": self.fragments_found,
            "fragments_absorbed": self.fragments_absorbed,
            "fragments_orphaned": self.fragments_orphaned,
            "scenes_grew": self.scenes_grew,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    arr_a = np.array(a, dtype=np.float64)
    arr_b = np.array(b, dtype=np.float64)
    na = np.linalg.norm(arr_a)
    nb = np.linalg.norm(arr_b)
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return float(np.clip(np.dot(arr_a, arr_b) / (na * nb), 0.0, 1.0))


def _mean_centroid(embeddings: List[List[float]]) -> Optional[List[float]]:
    """Compute L2-normalized mean centroid."""
    if not embeddings:
        return None
    arr = np.array(embeddings, dtype=np.float64)
    c = arr.mean(axis=0)
    n = np.linalg.norm(c)
    if n > 1e-12:
        c = c / n
    return c.tolist()


def _dominant_thread(events: List[Any]) -> Optional[str]:
    """Return the most common narrative_thread_id, or None."""
    from collections import Counter

    threads = Counter(
        e.event.narrative_thread_id
        for e in events
        if hasattr(e, "event") and getattr(e.event, "narrative_thread_id", None)
    )
    if not threads:
        return None
    top, _ = threads.most_common(1)[0]
    return top


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def absorb_fragments(
    episode_candidates: List["EpisodeCandidate"],
    episode_clusters: List["EpisodeCluster"],
    event_lookup: Dict[str, Any],
    config: FragmentAbsorptionConfig,
) -> Tuple[
    List["EpisodeCandidate"],
    List["EpisodeCluster"],
    FragmentAbsorptionStats,
]:
    """Absorb micro-fragment episodes into nearby compatible scenes.

    A fragment is absorbed into a scene when:
    1. Fragment has <= absorb_max_events events
    2. A scene exists within absorb_max_gap_hours temporal distance
    3. Thread compatibility (same thread or one/both unthreaded)
    4. Centroid cosine similarity >= absorb_min_similarity

    Scoring: 0.6 * similarity + 0.4 * temporal_proximity_bonus

    Args:
        episode_candidates: EpisodeCandidate list.
        episode_clusters: Parallel EpisodeCluster list (same order).
        event_lookup: Dict mapping event_id -> EventAdapter.
        config: Fragment absorption config.

    Returns:
        Tuple of (new_candidates, new_clusters, stats).
    """
    import json

    from k0.modules.consolidation.algorithms.centroid_calculator import EpisodeCandidate
    from k0.pipelines.p03.phase_outputs import EpisodeCluster

    stats = FragmentAbsorptionStats()
    max_gap_ms = config.absorb_max_gap_hours * 3_600_000

    # Classify into fragments vs scenes
    fragments: List[int] = []  # indices
    scenes: List[int] = []

    for i, cand in enumerate(episode_candidates):
        if cand.event_count <= config.absorb_max_events:
            fragments.append(i)
        else:
            scenes.append(i)

    stats.fragments_found = len(fragments)

    if not fragments or not scenes:
        stats.fragments_orphaned = len(fragments)
        return episode_candidates, episode_clusters, stats

    # Precompute scene data for matching
    scene_data: List[Dict[str, Any]] = []
    for idx in scenes:
        cand = episode_candidates[idx]
        cluster = episode_clusters[idx]
        member_events = [
            event_lookup[eid] for eid in cluster.member_event_ids if eid in event_lookup
        ]
        scene_data.append(
            {
                "idx": idx,
                "centroid": cand.centroid_embedding,
                "t_start": cand.temporal_start,
                "t_end": cand.temporal_end,
                "thread": _dominant_thread(member_events),
            }
        )

    # Match each fragment to best scene
    absorb_map: Dict[int, int] = {}  # fragment_idx -> scene_idx

    for frag_idx in fragments:
        frag_cand = episode_candidates[frag_idx]
        frag_cluster = episode_clusters[frag_idx]
        frag_events = [
            event_lookup[eid] for eid in frag_cluster.member_event_ids if eid in event_lookup
        ]
        frag_thread = _dominant_thread(frag_events)

        best_score = -1.0
        best_scene_idx = -1

        for sd in scene_data:
            # Temporal proximity check
            temporal_gap = max(
                0,
                max(frag_cand.temporal_start, sd["t_start"])
                - min(frag_cand.temporal_end, sd["t_end"]),
            )
            if temporal_gap > max_gap_ms:
                continue

            # Thread compatibility
            if frag_thread is not None and sd["thread"] is not None and frag_thread != sd["thread"]:
                continue

            # Semantic similarity
            if frag_cand.centroid_embedding is None or sd["centroid"] is None:
                continue
            sim = _cosine_sim(frag_cand.centroid_embedding, sd["centroid"])
            if sim < config.absorb_min_similarity:
                continue

            # Score
            temporal_bonus = 1.0 - (temporal_gap / max_gap_ms) if max_gap_ms > 0 else 1.0
            score = sim * 0.6 + temporal_bonus * 0.4

            # Duration guard: reject if absorption would exceed cap
            projected_start = min(frag_cand.temporal_start, sd["t_start"])
            projected_end = max(frag_cand.temporal_end, sd["t_end"])
            if (projected_end - projected_start) > config.max_absorbed_duration_ms:
                continue

            if score > best_score:
                best_score = score
                best_scene_idx = sd["idx"]

        if best_scene_idx >= 0:
            absorb_map[frag_idx] = best_scene_idx
            stats.fragments_absorbed += 1
        else:
            stats.fragments_orphaned += 1

    if not absorb_map:
        stats.fragments_orphaned = len(fragments)
        return episode_candidates, episode_clusters, stats

    # Group absorptions by target scene
    scene_additions: Dict[int, List[int]] = {}  # scene_idx -> [fragment_indices]
    for frag_idx, scene_idx in absorb_map.items():
        scene_additions.setdefault(scene_idx, []).append(frag_idx)

    stats.scenes_grew = len(scene_additions)

    # Build new output lists
    absorbed_set = set(absorb_map.keys())
    new_candidates: List[EpisodeCandidate] = []
    new_clusters: List[EpisodeCluster] = []

    for i, (cand, cluster) in enumerate(zip(episode_candidates, episode_clusters)):
        if i in absorbed_set:
            continue  # Skip absorbed fragments

        if i in scene_additions:
            # Merge fragment events into this scene
            extra_event_ids: List[str] = []
            for frag_idx in scene_additions[i]:
                extra_event_ids.extend(episode_clusters[frag_idx].member_event_ids)

            merged_ids = list(cluster.member_event_ids) + extra_event_ids
            merged_events = [event_lookup[eid] for eid in merged_ids if eid in event_lookup]
            merged_events.sort(key=lambda e: e.timestamp)
            merged_ids_sorted = [e.event_id for e in merged_events]

            # Recompute centroid
            embeddings = [e.embedding_768 for e in merged_events if e.embedding_768]
            new_centroid = _mean_centroid(embeddings)

            # Recompute temporal bounds
            ts_list = [e.timestamp for e in merged_events]
            new_t_start = min(ts_list) if ts_list else cand.temporal_start
            new_t_end = max(ts_list) if ts_list else cand.temporal_end

            # Recompute cohesion
            if new_centroid and embeddings:
                centroid_arr = np.array(new_centroid, dtype=np.float64)
                dists = [float(np.linalg.norm(np.array(emb) - centroid_arr)) for emb in embeddings]
                new_variance = float(np.mean(dists)) if dists else 0.0
            else:
                new_variance = cand.variance
            new_cohesion = 1.0 / (1.0 + new_variance)

            # Recompute participants
            all_participants: set = set()
            for e in merged_events:
                try:
                    p_list = json.loads(e.event.participants_json or "[]")
                    for p in p_list:
                        if isinstance(p, str):
                            all_participants.add(p)
                        elif isinstance(p, dict):
                            name = p.get("name", p.get("id", ""))
                            if name:
                                all_participants.add(name)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Build updated candidate
            merged_cand = EpisodeCandidate(
                cluster_id=cand.cluster_id,
                space_id=cand.space_id,
                event_ids=merged_ids_sorted,
                event_count=len(merged_ids_sorted),
                centroid_embedding=new_centroid,
                temporal_start=new_t_start,
                temporal_end=new_t_end,
                cohesion_score=new_cohesion,
                variance=new_variance,
                reconciliation_action=cand.reconciliation_action,
                extend_target_episode_id=cand.extend_target_episode_id,
                extend_similarity=cand.extend_similarity,
            )
            new_candidates.append(merged_cand)

            # Build updated cluster: re-use parent with merged event IDs
            # and merge member_contexts from absorbed fragments
            extra_contexts = []
            for frag_idx in scene_additions[i]:
                extra_contexts.extend(episode_clusters[frag_idx].member_contexts)

            merged_cluster = EpisodeCluster(
                cluster_id=cluster.cluster_id,
                member_event_ids=merged_ids_sorted,
                member_contexts=list(cluster.member_contexts) + extra_contexts,
                entity_ids=list(cluster.entity_ids),
                ambiguity_score=cluster.ambiguity_score,
                centroid_embedding_id=None,
                centroid_metadata=cluster.centroid_metadata,
                dominant_sentiment=cluster.dominant_sentiment,
                dominant_emotion=cluster.dominant_emotion,
                aggregated_sentiment=cluster.aggregated_sentiment,
                aggregated_salience=cluster.aggregated_salience,
                dominant_location=cluster.dominant_location,
                dominant_social_context=cluster.dominant_social_context,
                temporal_start=new_t_start,
                temporal_end=new_t_end,
                location_hint=cluster.location_hint,
                location_type=cluster.location_type,
                participants_json=json.dumps(sorted(all_participants)),
                activity_type=cluster.activity_type,
                activity_type_ultrabert=cluster.activity_type_ultrabert,
                cohesion_score=new_cohesion,
                title=cluster.title,
                summary=cluster.summary,
            )
            new_clusters.append(merged_cluster)
        else:
            new_candidates.append(cand)
            new_clusters.append(cluster)

    if stats.fragments_absorbed > 0:
        logger.info(
            "M9.10: Fragment absorption complete",
            extra=stats.to_dict(),
        )

    return new_candidates, new_clusters, stats
