"""
EpisodeSplitter - Pre-clustering episode segmentation.

This module implements pre-clustering sequence splitting to prevent
cross-activity clusters. It breaks long event sequences into smaller
episodes BEFORE DBSCAN clustering.

Spec Reference:
    - Dossier Appendix C.3.1.1: Pre-Clustering Episode Split
    - M4_EXECUTION.md Issue 4.2.2

Split Signals (priority order):
    1. Location Change: geohash prefix differs by >4 chars
    2. Activity Change: activity_type changes
    3. Time Gap: Gap > 30 minutes
    4. Hard Limit: Episode > 4 hours

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Time constants (milliseconds)
MS_PER_MINUTE = 60_000
MS_PER_HOUR = 3_600_000

# Default configuration values from Dossier C.3.1.1
DEFAULT_MAX_EPISODE_HOURS = 4.0
DEFAULT_TIME_GAP_MINUTES = 30.0
DEFAULT_GEOHASH_DISTANCE_THRESHOLD = 4


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class SplitConfig:
    """
    Configuration for episode splitting.

    Defaults from Dossier Appendix C.3.1.1:
        - max_episode_hours: 4.0 (hard limit on episode duration)
        - time_gap_minutes: 30.0 (gap threshold for splitting)
        - geohash_distance_threshold: 4 (location change threshold)

    Configuration Keys (from M4_EXECUTION.md):
        - P03_EPISODE_MAX_HOURS: [1.0, 8.0] range
        - P03_EPISODE_GAP_MINUTES: [10.0, 60.0] range
        - P03_EPISODE_GEOHASH_THRESHOLD: [2, 6] range
    """

    max_episode_hours: float = DEFAULT_MAX_EPISODE_HOURS
    time_gap_minutes: float = DEFAULT_TIME_GAP_MINUTES
    geohash_distance_threshold: int = DEFAULT_GEOHASH_DISTANCE_THRESHOLD

    @property
    def max_episode_ms(self) -> int:
        """Max episode duration in milliseconds."""
        return int(self.max_episode_hours * MS_PER_HOUR)

    @property
    def time_gap_ms(self) -> int:
        """Time gap threshold in milliseconds."""
        return int(self.time_gap_minutes * MS_PER_MINUTE)

    def validate(self) -> None:
        """Validate configuration ranges."""
        if self.max_episode_hours <= 0:
            raise ValueError(f"max_episode_hours must be > 0, got {self.max_episode_hours}")
        if self.time_gap_minutes <= 0:
            raise ValueError(f"time_gap_minutes must be > 0, got {self.time_gap_minutes}")
        if not 1 <= self.geohash_distance_threshold <= 12:
            raise ValueError(
                f"geohash_distance_threshold must be in [1, 12], got {self.geohash_distance_threshold}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "max_episode_hours": self.max_episode_hours,
            "time_gap_minutes": self.time_gap_minutes,
            "geohash_distance_threshold": self.geohash_distance_threshold,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SplitConfig":
        """Create from dictionary."""
        return cls(
            max_episode_hours=data.get("max_episode_hours", DEFAULT_MAX_EPISODE_HOURS),
            time_gap_minutes=data.get("time_gap_minutes", DEFAULT_TIME_GAP_MINUTES),
            geohash_distance_threshold=data.get(
                "geohash_distance_threshold", DEFAULT_GEOHASH_DISTANCE_THRESHOLD
            ),
        )


# =============================================================================
# Event Protocol
# =============================================================================


class SplittableEvent(Protocol):
    """
    Protocol for event objects usable with EpisodeSplitter.

    Minimal interface needed for episode splitting.
    P03EventState implements this implicitly (core fields).
    Optional fields (location_geohash, activity_type) are accessed via getattr.
    """

    @property
    def event_id(self) -> str:
        """Unique event identifier."""
        ...

    @property
    def timestamp(self) -> int:
        """Event timestamp in milliseconds since epoch."""
        ...


# =============================================================================
# Split Reason Enum
# =============================================================================


class SplitReason:
    """Reasons for episode split (for observability)."""

    NONE = "none"
    LOCATION_CHANGE = "location_change"
    ACTIVITY_CHANGE = "activity_change"
    TIME_GAP = "time_gap"
    HARD_LIMIT = "hard_limit"


# =============================================================================
# SplitResult
# =============================================================================


@dataclass
class SplitResult:
    """
    Result from episode splitting operation.

    Contains the split episodes and metadata for observability.
    """

    episodes: List[List[SplittableEvent]]
    """List of episodes, each episode is a list of events."""

    split_count: int
    """Number of splits performed."""

    split_reasons: Dict[str, int]
    """Count of splits by reason (location_change, activity_change, time_gap, hard_limit)."""

    total_events: int
    """Total events processed."""

    @property
    def episode_count(self) -> int:
        """Number of episodes created."""
        return len(self.episodes)


# =============================================================================
# EpisodeSplitter Class
# =============================================================================


class EpisodeSplitter:
    """
    Pre-clustering episode splitter.

    Splits long event sequences into smaller episodes to prevent
    cross-activity clusters in DBSCAN. Events within an episode
    are more likely to represent a coherent activity.

    Split Signals (checked in priority order):
        1. Location Change: geohash prefix differs significantly
        2. Activity Change: activity_type field changes
        3. Time Gap: Gap between consecutive events > threshold
        4. Hard Limit: Episode duration > max hours

    Scientific Basis:
        Event segmentation theory (Zacks & Swallow, 2007):
        People naturally segment continuous experience into discrete
        events at boundaries where prediction errors spike.

    Usage:
        config = SplitConfig(max_episode_hours=4.0, time_gap_minutes=30.0)
        splitter = EpisodeSplitter(config)

        result = splitter.split(events)
        episodes = result.episodes
        print(f"Created {result.episode_count} episodes")
    """

    def __init__(self, config: Optional[SplitConfig] = None):
        """
        Initialize EpisodeSplitter.

        Args:
            config: Split configuration. Uses defaults if None.
        """
        self.config = config or SplitConfig()
        self.config.validate()

    def split(
        self,
        events: Sequence[SplittableEvent],
    ) -> SplitResult:
        """
        Split event sequence into episodes.

        Events must be sorted by timestamp (ascending) for correct results.

        Args:
            events: List of events to split, sorted by timestamp

        Returns:
            SplitResult with episodes and metadata
        """
        if not events:
            return SplitResult(
                episodes=[],
                split_count=0,
                split_reasons={},
                total_events=0,
            )

        # Initialize result tracking
        episodes: List[List[SplittableEvent]] = []
        current_episode: List[SplittableEvent] = []
        split_reasons: Dict[str, int] = {
            SplitReason.LOCATION_CHANGE: 0,
            SplitReason.ACTIVITY_CHANGE: 0,
            SplitReason.TIME_GAP: 0,
            SplitReason.HARD_LIMIT: 0,
        }
        episode_start_ts: Optional[int] = None

        for event in events:
            # First event starts a new episode
            if not current_episode:
                current_episode.append(event)
                episode_start_ts = event.timestamp
                continue

            # Check for split condition
            prev_event = current_episode[-1]
            split_reason = self._detect_break(
                prev=prev_event,
                curr=event,
                episode_start_ts=episode_start_ts,
            )

            if split_reason != SplitReason.NONE:
                # End current episode and start new one
                episodes.append(current_episode)
                split_reasons[split_reason] += 1
                current_episode = [event]
                episode_start_ts = event.timestamp
            else:
                # Add to current episode
                current_episode.append(event)

        # Don't forget the last episode
        if current_episode:
            episodes.append(current_episode)

        total_splits = sum(split_reasons.values())

        return SplitResult(
            episodes=episodes,
            split_count=total_splits,
            split_reasons=split_reasons,
            total_events=len(events),
        )

    def split_long_sequences(
        self,
        events: Sequence[SplittableEvent],
    ) -> List[List[SplittableEvent]]:
        """
        Split long event sequences (simplified interface).

        Convenience method that returns just the episodes list.
        For full metadata, use split() instead.

        Args:
            events: List of events to split, sorted by timestamp

        Returns:
            List of episodes (each episode is a list of events)
        """
        return self.split(events).episodes

    def _detect_break(
        self,
        prev: SplittableEvent,
        curr: SplittableEvent,
        episode_start_ts: Optional[int],
    ) -> str:
        """
        Detect if a break should occur between two consecutive events.

        Checks signals in priority order (first match wins):
            1. Location Change (geohash prefix differs significantly)
            2. Activity Change (activity_type changes)
            3. Time Gap (gap > threshold)
            4. Hard Limit (episode duration > max hours)

        Args:
            prev: Previous event in sequence
            curr: Current event being considered
            episode_start_ts: Start timestamp of current episode

        Returns:
            SplitReason constant indicating why to split, or NONE
        """
        # Signal 1: Location Change (highest priority)
        prev_geohash = getattr(prev, "location_geohash", None) or getattr(prev, "geohash_6", None)
        curr_geohash = getattr(curr, "location_geohash", None) or getattr(curr, "geohash_6", None)

        if prev_geohash and curr_geohash:
            distance = self._geohash_distance(prev_geohash, curr_geohash)
            if distance > self.config.geohash_distance_threshold:
                logger.debug(
                    "Episode split: location change (distance=%d > %d)",
                    distance,
                    self.config.geohash_distance_threshold,
                )
                return SplitReason.LOCATION_CHANGE

        # Signal 2: Activity Change
        prev_activity = getattr(prev, "activity_type", None)
        curr_activity = getattr(curr, "activity_type", None)

        if prev_activity and curr_activity and prev_activity != curr_activity:
            logger.debug(
                "Episode split: activity change (%s -> %s)",
                prev_activity,
                curr_activity,
            )
            return SplitReason.ACTIVITY_CHANGE

        # Signal 3: Time Gap
        time_gap_ms = curr.timestamp - prev.timestamp
        if time_gap_ms > self.config.time_gap_ms:
            logger.debug(
                "Episode split: time gap (%d ms > %d ms threshold)",
                time_gap_ms,
                self.config.time_gap_ms,
            )
            return SplitReason.TIME_GAP

        # Signal 4: Hard Limit (episode duration)
        if episode_start_ts is not None:
            episode_duration_ms = curr.timestamp - episode_start_ts
            if episode_duration_ms > self.config.max_episode_ms:
                logger.debug(
                    "Episode split: hard limit (duration %d ms > %d ms max)",
                    episode_duration_ms,
                    self.config.max_episode_ms,
                )
                return SplitReason.HARD_LIMIT

        return SplitReason.NONE

    def _geohash_distance(
        self,
        gh1: str,
        gh2: str,
    ) -> int:
        """
        Compute geohash distance as character difference in prefixes.

        Distance = number of characters from first difference position.
        Lower distance = locations are closer.

        Examples:
            - "u4pruyd" vs "u4pruyd" -> 0 (identical)
            - "u4pruyd" vs "u4pruyc" -> 1 (differ at last char)
            - "u4pruyd" vs "u4pru00" -> 2 (differ at positions 5,6)
            - "u4pruyd" vs "gcpvj0d" -> 7 (differ from start)

        Args:
            gh1: First geohash string
            gh2: Second geohash string

        Returns:
            Distance in range [0, max(len(gh1), len(gh2))]
        """
        # Handle empty strings
        if not gh1 or not gh2:
            return max(len(gh1), len(gh2))

        # Find first difference position
        min_len = min(len(gh1), len(gh2))
        max_len = max(len(gh1), len(gh2))

        for i in range(min_len):
            if gh1[i] != gh2[i]:
                # Distance = remaining characters from this position
                return max_len - i

        # If prefixes match, distance is the length difference
        return max_len - min_len

    def get_split_stats(
        self,
        result: SplitResult,
    ) -> Dict[str, Any]:
        """
        Get detailed statistics from a split result.

        Useful for observability and debugging.

        Args:
            result: SplitResult from split() call

        Returns:
            Dictionary with statistics
        """
        if not result.episodes:
            return {
                "episode_count": 0,
                "total_events": 0,
                "split_count": 0,
                "avg_episode_size": 0.0,
                "min_episode_size": 0,
                "max_episode_size": 0,
                "split_reasons": result.split_reasons,
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
        }
