"""Scene-level episodic segmentation: split mega-episodes into human-scale scenes.

Human episodic memory (Tulving 1972, Zacks & Tversky 2007) stores scenes:
  - Temporally contiguous (minutes to a few hours, not days)
  - Bounded by context shifts (location, people, activity)
  - 5-30 events per scene typically

This module operates as a post-clustering step on (EpisodeCandidate, EpisodeCluster)
pairs, splitting oversized episodes based on temporal gaps, overnight breaks,
and place changes.

POC Evidence:
  - Phase 9 reduced 5 mega-blobs (758 events, 56% corpus) -> 105 scenes
  - 64% human-scale episodes (5-30 events), CogQ=0.71
  - Optimal config: scene_gap=4h, overnight=8h, max=35, min=3

M9.10 Milestone: Universal Reconciliation Engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

if TYPE_CHECKING:
    from k0.modules.consolidation.algorithms.centroid_calculator import EpisodeCandidate
    from k0.pipelines.p03.phase_outputs import EpisodeCluster

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneSegmentationConfig:
    """Tunable parameters for scene-level segmentation.

    Defaults are POC Phase 9 validated values (R2_RESEARCH_FINAL.md).
    """

    # Temporal scene boundary
    scene_gap_hours: float = 4.0
    """Gap >= this (hours) triggers a scene break."""

    overnight_gap_hours: float = 8.0
    """Gap >= this (hours) is a hard scene break."""

    # Scene size limits
    max_scene_events: int = 35
    """Soft cap: recursively split scenes larger than this at largest gap."""

    min_scene_events: int = 3
    """Scenes smaller than this are micro-fragment candidates."""

    # Context shift detection
    place_change_splits: bool = True
    """Split on place_id change when gap >= context_gap_hours."""

    context_gap_hours: float = 2.0
    """Gap + place change = scene break when gap >= this."""

    max_scene_duration_ms: int = 12 * 3_600_000
    """Hard duration cap (ms). Episodes exceeding this are segmented even if event count is low."""


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneBreak:
    """Detected boundary within an episode."""

    position: int
    """Index in sorted events list (break BEFORE this event)."""

    gap_hours: float
    """Gap duration in hours."""

    reason: str
    """'overnight', 'temporal_gap', 'context_shift', or 'size_cap'."""


@dataclass
class SceneSegmentationStats:
    """Statistics from a scene segmentation run."""

    input_episodes: int = 0
    episodes_split: int = 0
    scenes_created: int = 0
    output_episodes: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "input_episodes": self.input_episodes,
            "episodes_split": self.episodes_split,
            "scenes_created": self.scenes_created,
            "output_episodes": self.output_episodes,
        }


# ---------------------------------------------------------------------------
# Scene boundary detection
# ---------------------------------------------------------------------------


def _detect_scene_breaks(
    timestamps: List[int],
    place_ids: List[Optional[str]],
    config: SceneSegmentationConfig,
) -> List[SceneBreak]:
    """Find natural scene boundaries from sorted event timestamps and places.

    Args:
        timestamps: Sorted event timestamps in milliseconds.
        place_ids: Corresponding place_id per event (same order).
        config: Scene segmentation config.

    Returns:
        List of SceneBreak at detected boundaries.
    """
    if len(timestamps) < 2:
        return []

    breaks: List[SceneBreak] = []
    gap_threshold_ms = config.scene_gap_hours * 3_600_000
    overnight_ms = config.overnight_gap_hours * 3_600_000
    context_gap_ms = config.context_gap_hours * 3_600_000

    for i in range(1, len(timestamps)):
        gap_ms = timestamps[i] - timestamps[i - 1]
        gap_hours = gap_ms / 3_600_000

        if gap_ms >= overnight_ms:
            breaks.append(SceneBreak(position=i, gap_hours=gap_hours, reason="overnight"))
        elif gap_ms >= gap_threshold_ms:
            breaks.append(SceneBreak(position=i, gap_hours=gap_hours, reason="temporal_gap"))
        elif config.place_change_splits and gap_ms >= context_gap_ms:
            prev_place = place_ids[i - 1]
            curr_place = place_ids[i]
            if prev_place and curr_place and prev_place != curr_place:
                breaks.append(SceneBreak(position=i, gap_hours=gap_hours, reason="context_shift"))

    return breaks


def _split_indices_at_breaks(
    n_events: int,
    breaks: List[SceneBreak],
) -> List[Tuple[int, int]]:
    """Split an index range [0, n_events) at detected breaks.

    Returns list of (start, end) index tuples (exclusive end).
    """
    if not breaks:
        return [(0, n_events)]

    sorted_breaks = sorted(breaks, key=lambda b: b.position)
    segments: List[Tuple[int, int]] = []
    prev = 0
    for brk in sorted_breaks:
        if brk.position > prev:
            segments.append((prev, brk.position))
        prev = brk.position
    if prev < n_events:
        segments.append((prev, n_events))

    return [s for s in segments if s[1] > s[0]]


def _enforce_size_cap(
    timestamps: List[int],
    segments: List[Tuple[int, int]],
    max_events: int,
) -> List[Tuple[int, int]]:
    """Recursively split oversized segments at their largest internal gap.

    Args:
        timestamps: Full sorted timestamp list.
        segments: List of (start, end) index pairs.
        max_events: Maximum events per segment.

    Returns:
        Refined segment list where no segment exceeds max_events.
    """
    result: List[Tuple[int, int]] = []

    for start, end in segments:
        seg_len = end - start
        if seg_len <= max_events:
            result.append((start, end))
            continue

        # Find largest gap in this segment
        best_gap = 0
        best_pos = start + seg_len // 2  # fallback: middle
        for i in range(start + 1, end):
            gap = timestamps[i] - timestamps[i - 1]
            if gap > best_gap:
                best_gap = gap
                best_pos = i

        left = (start, best_pos)
        right = (best_pos, end)

        # Recurse
        result.extend(_enforce_size_cap(timestamps, [left], max_events))
        result.extend(_enforce_size_cap(timestamps, [right], max_events))

    return result


# ---------------------------------------------------------------------------
# Mean centroid computation (lightweight, no CentroidCalculator dependency)
# ---------------------------------------------------------------------------


def _compute_mean_centroid(embeddings: List[List[float]]) -> Optional[List[float]]:
    """Compute L2-normalized mean centroid from embeddings.

    Returns None if no valid embeddings provided.
    """
    if not embeddings:
        return None
    arr = np.array(embeddings, dtype=np.float64)
    centroid = arr.mean(axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 1e-12:
        centroid = centroid / norm
    return centroid.tolist()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def segment_episodes(
    episode_candidates: List["EpisodeCandidate"],
    episode_clusters: List["EpisodeCluster"],
    event_lookup: Dict[str, object],
    config: SceneSegmentationConfig,
) -> Tuple[
    List["EpisodeCandidate"],
    List["EpisodeCluster"],
    SceneSegmentationStats,
]:
    """Split oversized episodes into scene-level sub-episodes.

    Episodes at or below max_scene_events are passed through unchanged.
    Oversized episodes are split at temporal gaps, overnight breaks, and
    place changes, then recursively split at the largest gap if still
    above the size cap.

    Split scenes get new cluster_ids (``{parent_id}_s{idx:02d}``),
    recomputed centroids, and updated temporal bounds. Any EXTEND
    reconciliation action on the parent is discarded (scenes CREATE).

    Args:
        episode_candidates: EpisodeCandidate list from _build_episodes_from_clusters.
        episode_clusters: Parallel EpisodeCluster list (same order/length).
        event_lookup: Dict mapping event_id -> EventAdapter for field access.
        config: Scene segmentation configuration.

    Returns:
        Tuple of (new_candidates, new_clusters, stats).
    """
    from k0.modules.consolidation.algorithms.centroid_calculator import EpisodeCandidate

    stats = SceneSegmentationStats(input_episodes=len(episode_candidates))

    new_candidates: List[EpisodeCandidate] = []
    new_clusters: List[EpisodeCluster] = []

    for cand, cluster in zip(episode_candidates, episode_clusters):
        member_ids = list(cluster.member_event_ids)

        # Skip non-CREATE episodes (EXTEND/REINFORCE pass through intact)
        if cand.reconciliation_action != "CREATE":
            new_candidates.append(cand)
            new_clusters.append(cluster)
            continue

        # Skip small episodes that are also within duration cap
        episode_duration_ms = cluster.temporal_end - cluster.temporal_start
        if (
            len(member_ids) <= config.max_scene_events
            and episode_duration_ms <= config.max_scene_duration_ms
        ):
            new_candidates.append(cand)
            new_clusters.append(cluster)
            continue

        # Resolve member events from lookup (sorted by timestamp)
        members = [event_lookup[eid] for eid in member_ids if eid in event_lookup]
        if len(members) <= config.max_scene_events:
            new_candidates.append(cand)
            new_clusters.append(cluster)
            continue

        members.sort(key=lambda e: e.timestamp)
        sorted_ids = [e.event_id for e in members]
        sorted_ts = [e.timestamp for e in members]
        sorted_places = [getattr(e, "place_id", None) for e in members]

        # Detect breaks
        breaks = _detect_scene_breaks(sorted_ts, sorted_places, config)

        # If no breaks and within cap, keep as-is
        if not breaks and len(members) <= config.max_scene_events:
            new_candidates.append(cand)
            new_clusters.append(cluster)
            continue

        # Split at breaks, then enforce cap
        segments = _split_indices_at_breaks(len(members), breaks)
        segments = _enforce_size_cap(sorted_ts, segments, config.max_scene_events)

        # If splitting produced only one segment (no actual split), keep original
        if len(segments) <= 1:
            new_candidates.append(cand)
            new_clusters.append(cluster)
            continue

        stats.episodes_split += 1
        stats.scenes_created += len(segments)

        for idx, (seg_start, seg_end) in enumerate(segments, start=1):
            scene_ids = sorted_ids[seg_start:seg_end]
            scene_events = members[seg_start:seg_end]
            scene_ts = sorted_ts[seg_start:seg_end]

            scene_cluster_id = f"{cand.cluster_id}_s{idx:02d}"

            # Recompute centroid from scene member embeddings
            scene_embeddings = [e.embedding_768 for e in scene_events if e.embedding_768]
            scene_centroid = _compute_mean_centroid(scene_embeddings)

            # Compute cohesion for scene
            if scene_centroid and scene_embeddings:
                centroid_arr = np.array(scene_centroid, dtype=np.float64)
                dists = [
                    float(np.linalg.norm(np.array(emb) - centroid_arr)) for emb in scene_embeddings
                ]
                scene_variance = float(np.mean(dists)) if dists else 0.0
            else:
                scene_variance = cand.variance

            scene_cohesion = 1.0 / (1.0 + scene_variance)

            # Build scene EpisodeCandidate (fresh CREATE, no EXTEND inheritance)
            scene_cand = EpisodeCandidate(
                cluster_id=scene_cluster_id,
                space_id=cand.space_id,
                event_ids=scene_ids,
                event_count=len(scene_ids),
                centroid_embedding=scene_centroid,
                temporal_start=min(scene_ts),
                temporal_end=max(scene_ts),
                cohesion_score=scene_cohesion,
                variance=scene_variance,
                reconciliation_action="CREATE",
            )
            new_candidates.append(scene_cand)

            # Build scene EpisodeCluster by copying parent and overriding fields
            scene_cluster = _build_scene_cluster(
                parent=cluster,
                scene_cluster_id=scene_cluster_id,
                scene_event_ids=scene_ids,
                scene_events=scene_events,
                scene_ts=scene_ts,
                scene_cohesion=scene_cohesion,
            )
            new_clusters.append(scene_cluster)

        logger.info(
            "M9.10: Split mega-episode into scenes",
            extra={
                "parent_cluster_id": cand.cluster_id,
                "parent_event_count": len(member_ids),
                "scenes": len(segments),
                "scene_sizes": [seg_end - seg_start for seg_start, seg_end in segments],
            },
        )

    stats.output_episodes = len(new_candidates)

    if stats.episodes_split > 0:
        logger.info(
            "M9.10: Scene segmentation complete",
            extra=stats.to_dict(),
        )

    return new_candidates, new_clusters, stats


def _build_scene_cluster(
    parent: "EpisodeCluster",
    scene_cluster_id: str,
    scene_event_ids: List[str],
    scene_events: List[object],
    scene_ts: List[int],
    scene_cohesion: float,
) -> "EpisodeCluster":
    """Build a scene-level EpisodeCluster from a parent and event subset.

    Reuses parent metadata extraction patterns but scoped to the scene's
    member events. Inherits parent's member_contexts for matching events.
    """
    import json

    from k0.pipelines.p03.phase_outputs import EpisodeCluster

    temporal_start = min(scene_ts) if scene_ts else 0
    temporal_end = max(scene_ts) if scene_ts else 0

    # Sentiment: average from scene events
    sentiments = [getattr(e.event, "sentiment_score", 0.0) for e in scene_events]
    dominant_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

    # Location: vote from scene events
    locations = [
        getattr(e.event, "location_name", "")
        for e in scene_events
        if getattr(e.event, "location_name", None)
    ]
    location_hint = _vote_winner(locations)

    location_types = [
        getattr(e.event, "location_type", "")
        for e in scene_events
        if getattr(e.event, "location_type", None)
    ]
    location_type = _vote_winner(location_types)

    # Participants: union from scene events
    all_participants: set = set()
    for e in scene_events:
        try:
            p_list = json.loads(getattr(e.event, "participants_json", "[]") or "[]")
            for p in p_list:
                if isinstance(p, str):
                    all_participants.add(p)
                elif isinstance(p, dict):
                    name = p.get("name", p.get("id", ""))
                    if name:
                        all_participants.add(name)
        except (json.JSONDecodeError, TypeError):
            pass
    participants_json = json.dumps(sorted(all_participants))

    # Activity type: vote
    activity_type = _vote_winner(
        [
            getattr(e.event, "activity_type", "")
            for e in scene_events
            if getattr(e.event, "activity_type", None)
        ]
    )
    activity_type_ultrabert = _vote_winner(
        [
            getattr(e.event, "activity_type_ultrabert", "")
            for e in scene_events
            if getattr(e.event, "activity_type_ultrabert", None)
        ]
    )

    # Emotion: vote
    emotion_labels: list = []
    for e in scene_events:
        try:
            emotions = json.loads(getattr(e.event, "emotions_json", "[]") or "[]")
            for em in emotions:
                if isinstance(em, str):
                    emotion_labels.append(em)
                elif isinstance(em, dict):
                    label = em.get("label", em.get("emotion", ""))
                    if label:
                        emotion_labels.append(label)
        except (json.JSONDecodeError, TypeError):
            pass
    dominant_emotion = _vote_winner(emotion_labels)

    # Entity IDs: union from scene events NER
    entity_ids: set = set()
    for e in scene_events:
        try:
            ner_json = getattr(e.event, "ner_entities_json", "{}") or "{}"
            ner_data = json.loads(ner_json) if ner_json else {}
            if isinstance(ner_data, dict):
                for source in ["ner_family", "ner_general"]:
                    if source in ner_data and isinstance(ner_data[source], dict):
                        entities = ner_data[source].get("entities", [])
                        for ent in entities:
                            if isinstance(ent, dict) and ent.get("id"):
                                entity_ids.add(ent["id"])
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    # Member contexts: filter parent contexts to scene member IDs
    scene_id_set = set(scene_event_ids)
    member_contexts = [
        ctx for ctx in parent.member_contexts if getattr(ctx, "event_id", None) in scene_id_set
    ]

    # Aggregated context fields from scene contexts
    agg_sentiment = None
    agg_salience = None
    dom_location = None
    dom_social = None
    if member_contexts:
        sent_vals = [c.sentiment_score for c in member_contexts if c.sentiment_score is not None]
        if sent_vals:
            agg_sentiment = sum(sent_vals) / len(sent_vals)
        sal_vals = [c.salience_score for c in member_contexts if c.salience_score is not None]
        if sal_vals:
            agg_salience = sum(sal_vals) / len(sal_vals)
        loc_vals = [c.location for c in member_contexts if getattr(c, "location", None)]
        dom_location = _vote_winner(loc_vals)
        soc_vals = [c.social_context for c in member_contexts if getattr(c, "social_context", None)]
        dom_social = _vote_winner(soc_vals)

    return EpisodeCluster(
        cluster_id=scene_cluster_id,
        member_event_ids=list(scene_event_ids),
        member_contexts=member_contexts,
        entity_ids=list(entity_ids),
        ambiguity_score=parent.ambiguity_score,
        centroid_embedding_id=None,  # R7 will set
        centroid_metadata=None,  # Recomputed if needed by R7
        dominant_sentiment=dominant_sentiment,
        dominant_emotion=dominant_emotion or "",
        aggregated_sentiment=agg_sentiment,
        aggregated_salience=agg_salience,
        dominant_location=dom_location,
        dominant_social_context=dom_social,
        temporal_start=temporal_start,
        temporal_end=temporal_end,
        location_hint=location_hint,
        location_type=location_type,
        participants_json=participants_json,
        activity_type=activity_type or "",
        activity_type_ultrabert=activity_type_ultrabert or "",
        cohesion_score=scene_cohesion,
        title="",  # Will be regenerated by R2 if needed
        summary="",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vote_winner(items: List[Optional[str]]) -> Optional[str]:
    """Return the most common non-empty string, or None."""
    from collections import Counter

    filtered = [s for s in items if s]
    if not filtered:
        return None
    counts = Counter(filtered)
    winner, _ = counts.most_common(1)[0]
    return winner
