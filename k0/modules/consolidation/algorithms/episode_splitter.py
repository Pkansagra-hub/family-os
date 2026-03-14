"""
EpisodeSplitter - Pre-clustering episode segmentation (Epic 3.3).

Accumulated boundary scoring model ported from research_balanced_v1.
Replaces the original first-match-wins priority cascade with a
multi-signal penalty/bonus accumulator.

Boundary Scoring Architecture:
    Tier 1 - Hard boundaries (bypass accumulation, instant split):
        - hard_time_gap_minutes (8h silence)
        - hard_episode_span_minutes (18h total span)
        - hard_context_jump (place change + 3h gap + low semantic + different thread)

    Tier 2 - Accumulated scoring:
        Penalties (positive contribution):
            - thread_mismatch_penalty (0.35)
            - semantic_low_penalty (0.30), semantic_mid_penalty (0.15)
            - participant_zero_penalty (0.15)
            - social_change_penalty (0.10)
            - place_change_penalty (0.15)
            - activity_change_penalty (0.10)
            - medium/large/very_large gap penalties (0.10/0.20/0.30)
        Bonuses (negative contribution, resist splitting):
            - same_thread_bonus (0.45) -- narrative veto
            - strong_semantic_bonus (0.20)
            - participant_overlap_bonus (0.15)
            - same_goal_bonus (0.10)
            - same_place_short_gap_bonus (0.05)
        Split when accumulated score >= soft_split_threshold (0.45)

    Tier 3 - Weak boundaries (sub-threshold markers):
        Accumulated score between theta_soft (0.15) and soft_split_threshold
        recorded as WeakBoundary for downstream consumers.

Research Reference:
    - R2_RESEARCH_FINAL.md Section 2.1: research_balanced_v1 winner
    - Phase 1 results: 31 sequences from 1360 events, proxy=0.8068
    - Section 6.3: Event Segmentation Theory (Zacks 2007)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

MS_PER_MINUTE = 60_000
MS_PER_HOUR = 3_600_000


# =============================================================================
# Configuration (Issue 3.3.4: ported from ResearchSplitConfig)
# =============================================================================


@dataclass(frozen=True)
class SplitConfig:
    """Configuration for accumulated boundary scoring.

    All 13 research-calibrated parameters from research_balanced_v1 plus
    legacy compatibility aliases. Defaults are the empirically validated
    values from R2 Phase 1 calibration (11 splitter variants).

    Calibration source: R2_RESEARCH_FINAL.md Section 2.1
    """

    # --- Tier 1: Hard boundaries (bypass accumulation) ---
    hard_time_gap_minutes: float = 480.0  # 8h silence
    hard_episode_span_minutes: float = 1080.0  # 18h total span
    hard_context_gap_minutes: float = 180.0  # 3h for context jump
    hard_context_semantic_threshold: float = 0.55

    # --- Tier 2: Accumulated scoring ---
    soft_split_threshold: float = 0.45

    # Penalties
    thread_mismatch_penalty: float = 0.35
    partial_thread_mismatch_penalty: float = 0.10
    semantic_low_penalty: float = 0.30
    semantic_mid_penalty: float = 0.15
    participant_zero_penalty: float = 0.15
    social_change_penalty: float = 0.10
    place_change_penalty: float = 0.15
    activity_change_penalty: float = 0.10
    medium_gap_penalty: float = 0.10  # >= 90 min
    large_gap_penalty: float = 0.20  # >= 180 min
    very_large_gap_penalty: float = 0.30  # >= 360 min

    # Bonuses (resist splitting)
    same_thread_bonus: float = 0.45  # narrative veto
    strong_semantic_bonus: float = 0.20
    participant_overlap_bonus: float = 0.15
    same_goal_bonus: float = 0.10
    same_place_short_gap_bonus: float = 0.05

    # Semantic similarity band thresholds
    semantic_low_threshold: float = 0.55
    semantic_mid_threshold: float = 0.70
    semantic_strong_threshold: float = 0.86

    # Social thresholds
    participant_overlap_strong: float = 0.50
    same_place_short_gap_minutes: float = 120.0

    # Geohash distance (legacy compat)
    geohash_distance_threshold: int = 4

    # --- Tier 3: Weak boundary markers (Issue 3.3.6) ---
    theta_soft: float = 0.15

    # --- Legacy aliases (subsumed by richer config) ---

    @property
    def max_episode_hours(self) -> float:
        return self.hard_episode_span_minutes / 60.0

    @property
    def time_gap_minutes(self) -> float:
        return self.hard_time_gap_minutes

    @property
    def max_episode_ms(self) -> int:
        return int(self.hard_episode_span_minutes * MS_PER_MINUTE)

    @property
    def time_gap_ms(self) -> int:
        return int(self.hard_time_gap_minutes * MS_PER_MINUTE)

    def validate(self) -> None:
        """Validate configuration ranges."""
        if self.hard_time_gap_minutes <= 0:
            raise ValueError(f"hard_time_gap_minutes must be > 0, got {self.hard_time_gap_minutes}")
        if self.hard_episode_span_minutes <= 0:
            raise ValueError(
                f"hard_episode_span_minutes must be > 0, got {self.hard_episode_span_minutes}"
            )
        if not 0.0 < self.soft_split_threshold <= 1.0:
            raise ValueError(
                f"soft_split_threshold must be in (0, 1], got {self.soft_split_threshold}"
            )
        if not 0.0 <= self.theta_soft < self.soft_split_threshold:
            raise ValueError(
                f"theta_soft must be in [0, soft_split_threshold), got {self.theta_soft}"
            )
        if not 1 <= self.geohash_distance_threshold <= 12:
            raise ValueError(
                f"geohash_distance_threshold must be in [1, 12], got {self.geohash_distance_threshold}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hard_time_gap_minutes": self.hard_time_gap_minutes,
            "hard_episode_span_minutes": self.hard_episode_span_minutes,
            "hard_context_gap_minutes": self.hard_context_gap_minutes,
            "hard_context_semantic_threshold": self.hard_context_semantic_threshold,
            "soft_split_threshold": self.soft_split_threshold,
            "thread_mismatch_penalty": self.thread_mismatch_penalty,
            "partial_thread_mismatch_penalty": self.partial_thread_mismatch_penalty,
            "semantic_low_penalty": self.semantic_low_penalty,
            "semantic_mid_penalty": self.semantic_mid_penalty,
            "participant_zero_penalty": self.participant_zero_penalty,
            "social_change_penalty": self.social_change_penalty,
            "place_change_penalty": self.place_change_penalty,
            "activity_change_penalty": self.activity_change_penalty,
            "medium_gap_penalty": self.medium_gap_penalty,
            "large_gap_penalty": self.large_gap_penalty,
            "very_large_gap_penalty": self.very_large_gap_penalty,
            "same_thread_bonus": self.same_thread_bonus,
            "strong_semantic_bonus": self.strong_semantic_bonus,
            "participant_overlap_bonus": self.participant_overlap_bonus,
            "same_goal_bonus": self.same_goal_bonus,
            "same_place_short_gap_bonus": self.same_place_short_gap_bonus,
            "semantic_low_threshold": self.semantic_low_threshold,
            "semantic_mid_threshold": self.semantic_mid_threshold,
            "semantic_strong_threshold": self.semantic_strong_threshold,
            "participant_overlap_strong": self.participant_overlap_strong,
            "same_place_short_gap_minutes": self.same_place_short_gap_minutes,
            "geohash_distance_threshold": self.geohash_distance_threshold,
            "theta_soft": self.theta_soft,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SplitConfig":
        """Create from dictionary."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# =============================================================================
# Event Protocol (Issue 3.3.0: enriched, coordinated with EventLike)
# =============================================================================


class SplittableEvent(Protocol):
    """Protocol for event objects usable with EpisodeSplitter.

    Enriched to declare all fields needed by 7-channel boundary scoring.
    Coordinated with EventLike in composite_distance.py so both protocols
    share a consistent contract. EventAdapter satisfies both.

    All Optional fields return None when the signal is unavailable.
    Boundary channels handle None via neutral contribution (0.0).
    """

    @property
    def event_id(self) -> str: ...

    @property
    def timestamp(self) -> int: ...

    # --- Embedding (for semantic similarity) ---

    @property
    def embedding_768(self) -> Optional[List[float]]: ...

    # --- Spatial ---

    @property
    def place_id(self) -> Optional[str]: ...

    @property
    def geohash_6(self) -> Optional[str]: ...

    # --- Narrative ---

    @property
    def narrative_thread_id(self) -> Optional[str]: ...

    @property
    def goal_context(self) -> Optional[str]: ...

    # --- Social ---

    @property
    def participants_json(self) -> Optional[str]: ...

    @property
    def social_context(self) -> Optional[str]: ...

    # --- Activity ---

    @property
    def activity_type(self) -> Optional[str]: ...

    # --- Temporal context (Epic 3.6.0) ---

    @property
    def time_of_day_bucket(self) -> Optional[str]: ...

    @property
    def circadian_slot(self) -> Optional[str]: ...

    @property
    def is_weekend(self) -> Optional[bool]: ...

    @property
    def extraction_sequence(self) -> int: ...


# =============================================================================
# Split Reason Constants
# =============================================================================


class SplitReason:
    """Reasons for episode split (for observability).

    Tier 1 hard boundaries:
        HARD_TIME_GAP, HARD_EPISODE_SPAN, HARD_CONTEXT_JUMP
    Tier 2 accumulated boundary:
        SOFT_BOUNDARY (accumulation exceeded threshold)
    Legacy aliases preserved for backward compatibility.
    """

    NONE = "none"

    # Tier 1 hard boundaries
    HARD_TIME_GAP = "hard_time_gap"
    HARD_EPISODE_SPAN = "hard_episode_span"
    HARD_CONTEXT_JUMP = "hard_context_jump"

    # Tier 2 accumulated
    SOFT_BOUNDARY = "soft_boundary"

    # Legacy aliases (map to the new Tier 1/2 reasons)
    LOCATION_CHANGE = "location_change"
    ACTIVITY_CHANGE = "activity_change"
    TIME_GAP = "time_gap"
    HARD_LIMIT = "hard_limit"


# =============================================================================
# Boundary Decision Output
# =============================================================================


@dataclass
class BoundaryDecision:
    """Full diagnostic output from boundary scoring."""

    split: bool
    reason: str
    score: float
    channel_contributions: Dict[str, float]
    time_gap_minutes: float
    semantic_similarity: Optional[float]
    same_thread: bool


# =============================================================================
# Weak Boundary Marker (Issue 3.3.6)
# =============================================================================


@dataclass
class WeakBoundary:
    """Sub-threshold boundary marker for downstream consumers.

    Recorded when accumulated score >= theta_soft but < soft_split_threshold.
    """

    event_index: int
    prev_event_id: str
    curr_event_id: str
    score: float
    channel_contributions: Dict[str, float]
    same_thread: bool


# =============================================================================
# SplitResult
# =============================================================================


@dataclass
class SplitResult:
    """Result from episode splitting operation."""

    episodes: List[List[SplittableEvent]]

    split_count: int

    split_reasons: Dict[str, int]

    total_events: int

    weak_boundaries: List[WeakBoundary] = field(default_factory=list)

    boundary_decisions: List[BoundaryDecision] = field(default_factory=list)

    @property
    def episode_count(self) -> int:
        return len(self.episodes)


# =============================================================================
# Helper functions (ported from research run_matrix.py)
# =============================================================================


def _cosine_similarity(
    left: Optional[List[float]], right: Optional[List[float]]
) -> Optional[float]:
    """Cosine similarity between two embedding vectors."""
    if not left or not right:
        return None
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for lv, rv in zip(left, right):
        dot += lv * rv
        left_norm += lv * lv
        right_norm += rv * rv
    if left_norm <= 0.0 or right_norm <= 0.0:
        return None
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def _recent_centroid(sequence: Sequence[SplittableEvent], window: int = 3) -> Optional[List[float]]:
    """Compute centroid of last N embeddings in current sequence."""
    vectors = [e.embedding_768 for e in sequence[-window:] if e.embedding_768]
    if not vectors:
        return None
    dims = len(vectors[0])
    centroid = [0.0] * dims
    for vec in vectors:
        for i, v in enumerate(vec):
            centroid[i] += v
    return [v / len(vectors) for v in centroid]


def _parse_participants(participants_json: Optional[str]) -> set:
    """Extract participant set from JSON string."""
    if not participants_json:
        return set()
    return {p.strip() for p in participants_json.split(",") if p.strip()}


def _participant_jaccard(sequence: Sequence[SplittableEvent], event: SplittableEvent) -> float:
    """Jaccard similarity of participant sets between sequence tail and event."""
    seq_participants: set = set()
    for item in sequence[-3:]:
        seq_participants.update(_parse_participants(item.participants_json))
    curr_participants = _parse_participants(event.participants_json)
    if not seq_participants and not curr_participants:
        return 1.0
    if not seq_participants or not curr_participants:
        return 0.0
    union = seq_participants | curr_participants
    if not union:
        return 1.0
    return len(seq_participants & curr_participants) / len(union)


def _dominant_thread(sequence: Sequence[SplittableEvent]) -> Optional[str]:
    """Most common narrative_thread_id in sequence."""
    counts: Counter = Counter(e.narrative_thread_id for e in sequence if e.narrative_thread_id)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _same_goal_context(sequence: Sequence[SplittableEvent], event: SplittableEvent) -> bool:
    """Whether event shares goal_context with recent sequence events."""
    if not event.goal_context:
        return False
    for item in reversed(list(sequence[-3:])):
        if item.goal_context and item.goal_context == event.goal_context:
            return True
    return False


def _recent_goal_context(sequence: Sequence[SplittableEvent], window: int = 3) -> Optional[str]:
    """Most recent goal_context from sequence tail."""
    for item in reversed(list(sequence[-window:])):
        if item.goal_context:
            return item.goal_context
    return None


def _geohash_distance(gh1: str, gh2: str) -> int:
    """Geohash distance as character difference in prefixes."""
    if not gh1 or not gh2:
        return max(len(gh1), len(gh2))
    min_len = min(len(gh1), len(gh2))
    max_len = max(len(gh1), len(gh2))
    for i in range(min_len):
        if gh1[i] != gh2[i]:
            return max_len - i
    return max_len - min_len


# =============================================================================
# EpisodeSplitter Class (Epic 3.3: Accumulated Boundary Scoring)
# =============================================================================


class EpisodeSplitter:
    """Pre-clustering episode splitter with accumulated boundary scoring.

    Replaces the original first-match-wins priority cascade with the
    research_balanced_v1 accumulated penalty/bonus model.

    Scientific Basis:
        Event Segmentation Theory (Zacks & Swallow, 2007):
        Continuous experience is segmented at boundaries where
        prediction error spikes. The accumulated scoring model
        measures multi-signal prediction error between consecutive
        events.

    Boundary Decision Architecture:
        Tier 1: Hard boundaries bypass accumulation (instant split).
        Tier 2: Penalties accumulate; bonuses resist. Split when
                 accumulated score >= soft_split_threshold.
        Tier 3: Sub-threshold scores recorded as weak boundaries.

    Usage:
        config = SplitConfig()
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)
    """

    def __init__(self, config: Optional[SplitConfig] = None):
        self.config = config or SplitConfig()
        self.config.validate()

    def split(
        self,
        events: Sequence[SplittableEvent],
    ) -> SplitResult:
        """Split event sequence into episodes using accumulated boundary scoring.

        Issue 3.3.3: Events must be sorted by timestamp (ascending).
        An AssertionError is raised if ordering is violated.
        """
        if not events:
            return SplitResult(
                episodes=[],
                split_count=0,
                split_reasons={},
                total_events=0,
            )

        # Issue 3.3.3: Sort verification
        for i in range(len(events) - 1):
            if events[i].timestamp > events[i + 1].timestamp:
                logger.warning(
                    "EpisodeSplitter: out-of-order events detected at index %d "
                    "(event_id=%s ts=%d > event_id=%s ts=%d)",
                    i,
                    events[i].event_id,
                    events[i].timestamp,
                    events[i + 1].event_id,
                    events[i + 1].timestamp,
                )
                raise AssertionError(
                    f"Events must be sorted by timestamp: "
                    f"event[{i}].timestamp={events[i].timestamp} > "
                    f"event[{i + 1}].timestamp={events[i + 1].timestamp}"
                )

        episodes: List[List[SplittableEvent]] = []
        current_episode: List[SplittableEvent] = []
        split_reasons: Dict[str, int] = {}
        weak_boundaries: List[WeakBoundary] = []
        boundary_decisions: List[BoundaryDecision] = []

        for idx, event in enumerate(events):
            if not current_episode:
                current_episode.append(event)
                continue

            decision = self._boundary_decision(current_episode, event)
            boundary_decisions.append(decision)

            if decision.split:
                episodes.append(current_episode)
                split_reasons[decision.reason] = split_reasons.get(decision.reason, 0) + 1
                current_episode = [event]
            else:
                # Issue 3.3.6: Record weak boundary markers
                if decision.score >= self.config.theta_soft:
                    weak_boundaries.append(
                        WeakBoundary(
                            event_index=idx,
                            prev_event_id=current_episode[-1].event_id,
                            curr_event_id=event.event_id,
                            score=decision.score,
                            channel_contributions=decision.channel_contributions,
                            same_thread=decision.same_thread,
                        )
                    )
                current_episode.append(event)

        if current_episode:
            episodes.append(current_episode)

        return SplitResult(
            episodes=episodes,
            split_count=sum(split_reasons.values()),
            split_reasons=split_reasons,
            total_events=len(events),
            weak_boundaries=weak_boundaries,
            boundary_decisions=boundary_decisions,
        )

    def split_long_sequences(
        self,
        events: Sequence[SplittableEvent],
    ) -> List[List[SplittableEvent]]:
        """Simplified interface returning just the episodes list."""
        return self.split(events).episodes

    # =========================================================================
    # Core boundary decision (Issues 3.3.1, 3.3.2, 3.3.5)
    # =========================================================================

    def _boundary_decision(
        self,
        sequence: Sequence[SplittableEvent],
        event: SplittableEvent,
    ) -> BoundaryDecision:
        """Compute accumulated boundary score between sequence and next event.

        Architecture:
            1. Check Tier 1 hard boundaries (instant split)
            2. Accumulate penalties and bonuses across all channels
            3. Return split decision based on threshold comparison
        """
        cfg = self.config
        previous = sequence[-1]

        time_gap_ms = max(0, event.timestamp - previous.timestamp)
        time_gap_minutes = time_gap_ms / MS_PER_MINUTE
        sequence_span_minutes = max(0, (event.timestamp - sequence[0].timestamp) / MS_PER_MINUTE)

        # Pre-compute signals
        dominant_thread = _dominant_thread(sequence)
        same_thread = bool(
            event.narrative_thread_id
            and dominant_thread
            and event.narrative_thread_id == dominant_thread
        )

        centroid = _recent_centroid(sequence)
        semantic_similarity = _cosine_similarity(centroid, event.embedding_768)
        participant_overlap = _participant_jaccard(sequence, event)
        same_goal = _same_goal_context(sequence, event)

        prev_place = previous.place_id
        curr_place = event.place_id
        same_place = bool(prev_place and curr_place and prev_place == curr_place)
        place_changed = bool(prev_place and curr_place and prev_place != curr_place)

        # If no place_id, fall back to geohash
        if not place_changed and not same_place:
            prev_gh = previous.geohash_6
            curr_gh = event.geohash_6
            if prev_gh and curr_gh:
                gh_dist = _geohash_distance(prev_gh, curr_gh)
                if gh_dist > cfg.geohash_distance_threshold:
                    place_changed = True
                elif gh_dist == 0:
                    same_place = True

        channels: Dict[str, float] = {}

        # =====================================================================
        # Tier 1: Hard boundaries (bypass accumulation)
        # =====================================================================

        if time_gap_minutes >= cfg.hard_time_gap_minutes:
            channels["hard_time_gap"] = 1.0
            return BoundaryDecision(
                split=True,
                reason=SplitReason.HARD_TIME_GAP,
                score=1.0,
                channel_contributions=channels,
                time_gap_minutes=time_gap_minutes,
                semantic_similarity=semantic_similarity,
                same_thread=same_thread,
            )

        if sequence_span_minutes >= cfg.hard_episode_span_minutes:
            channels["hard_episode_span"] = 1.0
            return BoundaryDecision(
                split=True,
                reason=SplitReason.HARD_EPISODE_SPAN,
                score=1.0,
                channel_contributions=channels,
                time_gap_minutes=time_gap_minutes,
                semantic_similarity=semantic_similarity,
                same_thread=same_thread,
            )

        if (
            place_changed
            and time_gap_minutes >= cfg.hard_context_gap_minutes
            and not same_thread
            and semantic_similarity is not None
            and semantic_similarity < cfg.hard_context_semantic_threshold
        ):
            channels["hard_context_jump"] = 1.0
            return BoundaryDecision(
                split=True,
                reason=SplitReason.HARD_CONTEXT_JUMP,
                score=1.0,
                channel_contributions=channels,
                time_gap_minutes=time_gap_minutes,
                semantic_similarity=semantic_similarity,
                same_thread=same_thread,
            )

        # =====================================================================
        # Tier 2: Accumulated scoring (Issues 3.3.1, 3.3.2, 3.3.5)
        # =====================================================================

        score = 0.0

        # --- Narrative channel (Issue 3.3.2) ---
        if previous.narrative_thread_id and event.narrative_thread_id:
            if previous.narrative_thread_id != event.narrative_thread_id:
                score += cfg.thread_mismatch_penalty
                channels["thread_mismatch"] = cfg.thread_mismatch_penalty
        elif bool(previous.narrative_thread_id) != bool(event.narrative_thread_id):
            score += cfg.partial_thread_mismatch_penalty
            channels["partial_thread_mismatch"] = cfg.partial_thread_mismatch_penalty

        # --- Semantic channel (Issue 3.3.2) ---
        if semantic_similarity is not None:
            if semantic_similarity < cfg.semantic_low_threshold:
                score += cfg.semantic_low_penalty
                channels["semantic_low"] = cfg.semantic_low_penalty
            elif semantic_similarity < cfg.semantic_mid_threshold:
                score += cfg.semantic_mid_penalty
                channels["semantic_mid"] = cfg.semantic_mid_penalty

        # --- Social channel (Issue 3.3.2) ---
        prev_participants = _parse_participants(previous.participants_json)
        curr_participants = _parse_participants(event.participants_json)
        if participant_overlap == 0.0 and (prev_participants or curr_participants):
            score += cfg.participant_zero_penalty
            channels["participant_zero"] = cfg.participant_zero_penalty

        if (
            previous.social_context
            and event.social_context
            and previous.social_context != event.social_context
        ):
            score += cfg.social_change_penalty
            channels["social_change"] = cfg.social_change_penalty

        # --- Spatial channel (Issue 3.3.2) ---
        if place_changed:
            score += cfg.place_change_penalty
            channels["place_change"] = cfg.place_change_penalty

        # --- Activity channel (Issue 3.3.2) ---
        if (
            previous.activity_type
            and event.activity_type
            and previous.activity_type != event.activity_type
        ):
            score += cfg.activity_change_penalty
            channels["activity_change"] = cfg.activity_change_penalty

        # --- Temporal gap tiers ---
        if time_gap_minutes >= 360:
            score += cfg.very_large_gap_penalty
            channels["very_large_gap"] = cfg.very_large_gap_penalty
        elif time_gap_minutes >= 180:
            score += cfg.large_gap_penalty
            channels["large_gap"] = cfg.large_gap_penalty
        elif time_gap_minutes >= 90:
            score += cfg.medium_gap_penalty
            channels["medium_gap"] = cfg.medium_gap_penalty

        # --- Bonuses (resist splitting) ---

        # Issue 3.3.5: Narrative veto -- same_thread_bonus prevents split
        # when both events share narrative_thread_id. With threshold=0.45
        # and bonus=0.45, accumulator must exceed 0.90 to split same-thread.
        if same_thread:
            score -= cfg.same_thread_bonus
            channels["same_thread_bonus"] = -cfg.same_thread_bonus

        if semantic_similarity is not None and semantic_similarity >= cfg.semantic_strong_threshold:
            score -= cfg.strong_semantic_bonus
            channels["strong_semantic_bonus"] = -cfg.strong_semantic_bonus

        if participant_overlap >= cfg.participant_overlap_strong:
            score -= cfg.participant_overlap_bonus
            channels["participant_overlap_bonus"] = -cfg.participant_overlap_bonus

        if same_goal:
            score -= cfg.same_goal_bonus
            channels["same_goal_bonus"] = -cfg.same_goal_bonus

        if same_place and time_gap_minutes < cfg.same_place_short_gap_minutes:
            score -= cfg.same_place_short_gap_bonus
            channels["same_place_short_gap_bonus"] = -cfg.same_place_short_gap_bonus

        # --- Decision ---
        should_split = score >= cfg.soft_split_threshold
        reason = SplitReason.SOFT_BOUNDARY if should_split else SplitReason.NONE

        return BoundaryDecision(
            split=should_split,
            reason=reason,
            score=score,
            channel_contributions=channels,
            time_gap_minutes=time_gap_minutes,
            semantic_similarity=semantic_similarity,
            same_thread=same_thread,
        )

    # =========================================================================
    # Legacy compatibility
    # =========================================================================

    def _geohash_distance(self, gh1: str, gh2: str) -> int:
        """Geohash distance (delegated to module-level function)."""
        return _geohash_distance(gh1, gh2)

    def get_split_stats(self, result: SplitResult) -> Dict[str, Any]:
        """Get detailed statistics from a split result."""
        if not result.episodes:
            return {
                "episode_count": 0,
                "total_events": 0,
                "split_count": 0,
                "avg_episode_size": 0.0,
                "min_episode_size": 0,
                "max_episode_size": 0,
                "split_reasons": result.split_reasons,
                "weak_boundary_count": 0,
            }

        episode_sizes = [len(ep) for ep in result.episodes]

        return {
            "episode_count": result.episode_count,
            "total_events": result.total_events,
            "split_count": result.split_count,
            "avg_episode_size": sum(episode_sizes) / len(episode_sizes),
            "min_episode_size": min(episode_sizes),
            "max_episode_size": max(episode_sizes),
            "split_reasons": result.split_reasons,
            "weak_boundary_count": len(result.weak_boundaries),
        }
