"""
Cross-Batch Episode Extension Matching (Epic 6.4).

Post-clustering matcher that identifies newly-formed episodes which should
EXTEND existing episodes from previous consolidation batches rather than
creating duplicate entries.

Research basis:
    - R2_RESEARCH_FINAL.md Section 2.2.3.3
    - r2_final_pipeline.py _reconcile_cluster()
    - 531->260 final episodes after correction + merge + extend
    - EXTEND_SIM_THRESHOLD = 0.60 + same_thread required

Algorithm:
    1. For each newly-built EpisodeCandidate (with computed centroid):
        a. Determine its dominant narrative thread from member events
        b. Compare centroid to each existing episode centroid (cosine similarity)
        c. If sim >= threshold AND same dominant thread AND temporal gap within limit:
           -> Mark as EXTEND with target episode_id
        d. Otherwise -> remains CREATE (default)
    2. Return annotated candidates + stats

Scope note:
    This module defines MATCHING LOGIC only. The actual _update_extend()
    write path is defined in M9 (universal reconciliation framework).

Spec Reference:
    - R2_EPISODIC_INTEGRATION_EPIC_PLAN.md Epic 6.4
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Protocols
# =============================================================================


class ExtendableEvent(Protocol):
    """Event protocol for cross-batch extend (thread determination)."""

    @property
    def event_id(self) -> str: ...

    @property
    def narrative_thread_id(self) -> Optional[str]: ...


class ExtendableCandidate(Protocol):
    """Episode candidate with centroid for cross-batch matching."""

    @property
    def cluster_id(self) -> str: ...

    @property
    def event_ids(self) -> List[str]: ...

    @property
    def centroid_embedding(self) -> Optional[List[float]]: ...

    @property
    def temporal_start(self) -> int: ...

    @property
    def temporal_end(self) -> int: ...


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class CrossBatchExtendConfig:
    """Configuration for cross-batch episode extension matching.

    Proven defaults from research pipeline (r2_final_pipeline.py).
    """

    centroid_sim_threshold: float = 0.60
    require_same_thread: bool = True
    max_temporal_gap_ms: int = 7 * 24 * 3_600_000  # 7 days
    max_episode_duration_ms: int = 24 * 3_600_000  # 24h hard cap on extended episode span


# =============================================================================
# Stats
# =============================================================================


@dataclass
class CrossBatchExtendStats:
    """Observability stats from cross-batch extension matching."""

    candidates_checked: int = 0
    candidates_extended: int = 0
    candidates_new: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "candidates_checked": self.candidates_checked,
            "candidates_extended": self.candidates_extended,
            "candidates_new": self.candidates_new,
        }


# =============================================================================
# Match result
# =============================================================================


@dataclass
class ExtendMatch:
    """Result of matching a candidate to an existing episode."""

    target_episode_id: str
    similarity: float
    target_version: int


# =============================================================================
# Helpers
# =============================================================================


def _cosine_sim_lists(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two float lists."""
    dot = sum(va * vb for va, vb in zip(a, b))
    na = sum(v * v for v in a) ** 0.5
    nb = sum(v * v for v in b) ** 0.5
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _cosine_sim_np(a: Any, b: List[float]) -> float:
    """Cosine similarity accepting numpy array for first arg."""
    try:
        import numpy as np

        a_arr = np.asarray(a, dtype=np.float64).ravel()
        b_arr = np.asarray(b, dtype=np.float64).ravel()
        dot = float(np.dot(a_arr, b_arr))
        na = float(np.linalg.norm(a_arr))
        nb = float(np.linalg.norm(b_arr))
        if na < 1e-10 or nb < 1e-10:
            return 0.0
        return max(0.0, min(1.0, dot / (na * nb)))
    except Exception:
        # Fallback to list-based
        a_list = list(a) if not isinstance(a, list) else a
        return _cosine_sim_lists(a_list, b)


def _dominant_thread_for_candidate(
    event_ids: List[str],
    event_lookup: Dict[str, ExtendableEvent],
) -> Optional[str]:
    """Determine the dominant narrative thread for a candidate's member events."""
    threads: Counter[str] = Counter()
    for eid in event_ids:
        ev = event_lookup.get(eid)
        if ev is not None and ev.narrative_thread_id:
            threads[ev.narrative_thread_id] += 1
    if not threads:
        return None
    top_thread, _ = threads.most_common(1)[0]
    return top_thread


# =============================================================================
# CrossBatchExtendMatcher
# =============================================================================


@dataclass
class CrossBatchExtendMatcher:
    """Match newly-formed episodes against existing episodes for EXTEND.

    A candidate extends an existing episode when:
        1. Centroid cosine similarity >= threshold (0.60)
        2. Same dominant narrative thread (when require_same_thread=True)
        3. Temporal gap within limit (7 days default)
    """

    config: CrossBatchExtendConfig = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = CrossBatchExtendConfig()

    def match(
        self,
        candidates: Sequence[ExtendableCandidate],
        existing_episodes: List[Dict[str, Any]],
        event_lookup: Dict[str, ExtendableEvent],
    ) -> Tuple[List[Optional[ExtendMatch]], CrossBatchExtendStats]:
        """Match candidates against existing episodes.

        Args:
            candidates: Episode candidates with computed centroids.
            existing_episodes: Existing episodes from st_epi query
                (dicts with 'episode_id', 'embedding', 'version',
                 'start_time_utc', 'end_time_utc', optionally 'narrative_thread_id').
            event_lookup: event_id -> event for thread determination.

        Returns:
            (matches, stats) where matches[i] is ExtendMatch or None for each candidate.
        """
        stats = CrossBatchExtendStats()
        matches: List[Optional[ExtendMatch]] = []

        if not existing_episodes:
            for _ in candidates:
                matches.append(None)
                stats.candidates_new += 1
            stats.candidates_checked = len(candidates)
            return matches, stats

        for candidate in candidates:
            stats.candidates_checked += 1

            if candidate.centroid_embedding is None:
                matches.append(None)
                stats.candidates_new += 1
                continue

            # Determine candidate's dominant thread
            cand_thread = _dominant_thread_for_candidate(candidate.event_ids, event_lookup)

            best_match: Optional[ExtendMatch] = None
            best_sim = 0.0

            for episode in existing_episodes:
                ep_embedding = episode.get("embedding")
                if ep_embedding is None:
                    continue

                # Centroid similarity
                sim = _cosine_sim_np(ep_embedding, candidate.centroid_embedding)
                if sim < self.config.centroid_sim_threshold:
                    continue

                # Thread matching
                if self.config.require_same_thread and cand_thread is not None:
                    ep_thread = episode.get("narrative_thread_id")
                    if ep_thread is not None and ep_thread != cand_thread:
                        continue

                # Temporal gap check
                ep_start = episode.get("start_time_utc", 0)
                ep_end = episode.get("end_time_utc", 0)
                gap = max(
                    0,
                    max(candidate.temporal_start, ep_start) - min(candidate.temporal_end, ep_end),
                )
                if gap > self.config.max_temporal_gap_ms:
                    continue

                # Duration cap: reject if extended episode would exceed max duration
                projected_start = min(candidate.temporal_start, ep_start)
                projected_end = max(candidate.temporal_end, ep_end)
                if (projected_end - projected_start) > self.config.max_episode_duration_ms:
                    continue

                # Best match by similarity
                if sim > best_sim:
                    best_sim = sim
                    best_match = ExtendMatch(
                        target_episode_id=episode["episode_id"],
                        similarity=sim,
                        target_version=episode.get("version", 1),
                    )

            matches.append(best_match)
            if best_match is not None:
                stats.candidates_extended += 1
            else:
                stats.candidates_new += 1

        return matches, stats
