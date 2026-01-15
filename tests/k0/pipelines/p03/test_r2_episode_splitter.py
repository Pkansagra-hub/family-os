"""
Tests for EpisodeSplitter — pre-clustering episode segmentation.

Issue 4.2.2: Pre-clustering episode split

Tests:
    1. test_split_config_defaults: Default values match spec
    2. test_split_config_validation: Invalid ranges rejected
    3. test_empty_input: Empty list produces empty result
    4. test_single_event: Single event creates single episode
    5. test_no_splits_needed: Contiguous events stay together
    6. test_split_on_time_gap: Gap > 30 minutes splits
    7. test_split_on_hard_limit: Episode > 4 hours splits
    8. test_split_on_location_change: Geohash change splits
    9. test_split_on_activity_change: Activity type change splits
    10. test_split_priority_order: Location > Activity > Time > Limit
    11. test_geohash_distance_calculation: Distance computed correctly
    12. test_split_result_metadata: Metadata tracked correctly
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from k0.modules.consolidation.algorithms.episode_splitter import (
    MS_PER_HOUR,
    MS_PER_MINUTE,
    EpisodeSplitter,
    SplitConfig,
    SplitReason,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for testing."""

    event_id: str
    timestamp: int
    location_geohash: Optional[str] = None
    activity_type: Optional[str] = None


def make_events(count: int, start_ts: int, gap_ms: int = 1000) -> list[MockEvent]:
    """Create sequence of events with consistent gaps."""
    return [MockEvent(f"e{i}", start_ts + i * gap_ms) for i in range(count)]


# =============================================================================
# SplitConfig Tests
# =============================================================================


class TestSplitConfig:
    """Test SplitConfig configuration dataclass."""

    def test_split_config_defaults(self) -> None:
        """Default values match Dossier C.3.1.1 spec."""
        config = SplitConfig()

        assert config.max_episode_hours == 4.0
        assert config.time_gap_minutes == 30.0
        assert config.geohash_distance_threshold == 4

    def test_split_config_derived_properties(self) -> None:
        """Derived properties computed correctly."""
        config = SplitConfig(max_episode_hours=4.0, time_gap_minutes=30.0)

        assert config.max_episode_ms == 4 * MS_PER_HOUR
        assert config.time_gap_ms == 30 * MS_PER_MINUTE

    def test_split_config_validation_max_episode_hours(self) -> None:
        """Invalid max_episode_hours rejected."""
        with pytest.raises(ValueError, match="max_episode_hours must be > 0"):
            SplitConfig(max_episode_hours=0).validate()

    def test_split_config_validation_time_gap_minutes(self) -> None:
        """Invalid time_gap_minutes rejected."""
        with pytest.raises(ValueError, match="time_gap_minutes must be > 0"):
            SplitConfig(time_gap_minutes=0).validate()

    def test_split_config_validation_geohash_threshold(self) -> None:
        """Invalid geohash_distance_threshold rejected."""
        with pytest.raises(ValueError, match="geohash_distance_threshold must be in"):
            SplitConfig(geohash_distance_threshold=0).validate()

        with pytest.raises(ValueError, match="geohash_distance_threshold must be in"):
            SplitConfig(geohash_distance_threshold=13).validate()

    def test_split_config_serialization(self) -> None:
        """Serialization round-trip preserves values."""
        config = SplitConfig(max_episode_hours=2.0, time_gap_minutes=15.0)

        data = config.to_dict()
        restored = SplitConfig.from_dict(data)

        assert restored.max_episode_hours == config.max_episode_hours
        assert restored.time_gap_minutes == config.time_gap_minutes
        assert restored.geohash_distance_threshold == config.geohash_distance_threshold


# =============================================================================
# EpisodeSplitter Tests — Basic Cases
# =============================================================================


class TestEpisodeSplitterBasic:
    """Test EpisodeSplitter basic functionality."""

    def test_empty_input(self) -> None:
        """Empty list produces empty result."""
        splitter = EpisodeSplitter()
        result = splitter.split([])

        assert result.episodes == []
        assert result.split_count == 0
        assert result.total_events == 0

    def test_single_event(self) -> None:
        """Single event creates single episode."""
        event = MockEvent("e1", 1000)
        splitter = EpisodeSplitter()
        result = splitter.split([event])

        assert len(result.episodes) == 1
        assert len(result.episodes[0]) == 1
        assert result.episodes[0][0].event_id == "e1"
        assert result.split_count == 0

    def test_no_splits_needed(self) -> None:
        """Contiguous events within thresholds stay in one episode."""
        base_ts = 1000000000000
        # 10 events, 1 minute apart (60000 ms)
        events = make_events(10, base_ts, gap_ms=MS_PER_MINUTE)

        splitter = EpisodeSplitter()
        result = splitter.split(events)

        assert len(result.episodes) == 1
        assert len(result.episodes[0]) == 10
        assert result.split_count == 0

    def test_simplified_interface(self) -> None:
        """split_long_sequences() returns just episodes list."""
        events = make_events(5, 1000000000000, gap_ms=1000)

        splitter = EpisodeSplitter()
        episodes = splitter.split_long_sequences(events)

        assert isinstance(episodes, list)
        assert len(episodes) == 1
        assert len(episodes[0]) == 5


# =============================================================================
# EpisodeSplitter Tests — Split Conditions
# =============================================================================


class TestEpisodeSplitterSplitConditions:
    """Test EpisodeSplitter split conditions."""

    def test_split_on_time_gap(self) -> None:
        """Gap > 30 minutes causes split."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts),
            MockEvent("e2", base_ts + 5 * MS_PER_MINUTE),
            # 45 minute gap here
            MockEvent("e3", base_ts + 50 * MS_PER_MINUTE),
            MockEvent("e4", base_ts + 55 * MS_PER_MINUTE),
        ]

        config = SplitConfig(time_gap_minutes=30.0)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        assert len(result.episodes) == 2
        assert len(result.episodes[0]) == 2  # e1, e2
        assert len(result.episodes[1]) == 2  # e3, e4
        assert result.split_reasons[SplitReason.TIME_GAP] == 1

    def test_split_on_hard_limit(self) -> None:
        """Episode > max hours causes split."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts),
            MockEvent("e2", base_ts + 1 * MS_PER_HOUR),
            MockEvent("e3", base_ts + 2 * MS_PER_HOUR),
            MockEvent("e4", base_ts + 3 * MS_PER_HOUR),
            # This event is 4.5h from start, exceeds 4h limit
            MockEvent("e5", base_ts + int(4.5 * MS_PER_HOUR)),
        ]

        config = SplitConfig(max_episode_hours=4.0, time_gap_minutes=120.0)  # 2h gap allowed
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        assert len(result.episodes) == 2
        assert len(result.episodes[0]) == 4  # e1, e2, e3, e4
        assert len(result.episodes[1]) == 1  # e5
        assert result.split_reasons[SplitReason.HARD_LIMIT] == 1

    def test_split_on_location_change(self) -> None:
        """Geohash change > threshold causes split."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, location_geohash="u4pruyd"),
            MockEvent("e2", base_ts + 1000, location_geohash="u4pruyd"),
            # Different location
            MockEvent("e3", base_ts + 2000, location_geohash="gcpvj0d"),
            MockEvent("e4", base_ts + 3000, location_geohash="gcpvj0d"),
        ]

        config = SplitConfig(geohash_distance_threshold=4)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        assert len(result.episodes) == 2
        assert len(result.episodes[0]) == 2  # e1, e2
        assert len(result.episodes[1]) == 2  # e3, e4
        assert result.split_reasons[SplitReason.LOCATION_CHANGE] == 1

    def test_split_on_activity_change(self) -> None:
        """Activity type change causes split."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, activity_type="work"),
            MockEvent("e2", base_ts + 1000, activity_type="work"),
            # Different activity
            MockEvent("e3", base_ts + 2000, activity_type="exercise"),
            MockEvent("e4", base_ts + 3000, activity_type="exercise"),
        ]

        splitter = EpisodeSplitter()
        result = splitter.split(events)

        assert len(result.episodes) == 2
        assert result.split_reasons[SplitReason.ACTIVITY_CHANGE] == 1


# =============================================================================
# EpisodeSplitter Tests — Priority Order
# =============================================================================


class TestEpisodeSplitterPriority:
    """Test EpisodeSplitter split priority order."""

    def test_location_change_beats_time_gap(self) -> None:
        """Location change has priority over time gap."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, location_geohash="u4pruyd"),
            # Both location change AND time gap
            MockEvent(
                "e2",
                base_ts + 45 * MS_PER_MINUTE,  # 45 min gap
                location_geohash="gcpvj0d",  # Different location
            ),
        ]

        config = SplitConfig(time_gap_minutes=30.0, geohash_distance_threshold=4)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        assert len(result.episodes) == 2
        # Location change should be the recorded reason (higher priority)
        assert result.split_reasons[SplitReason.LOCATION_CHANGE] == 1
        assert result.split_reasons[SplitReason.TIME_GAP] == 0

    def test_activity_change_beats_time_gap(self) -> None:
        """Activity change has priority over time gap."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, activity_type="work"),
            # Both activity change AND time gap
            MockEvent(
                "e2",
                base_ts + 45 * MS_PER_MINUTE,  # 45 min gap
                activity_type="exercise",  # Different activity
            ),
        ]

        config = SplitConfig(time_gap_minutes=30.0)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        assert len(result.episodes) == 2
        # Activity change should be the recorded reason (higher priority)
        assert result.split_reasons[SplitReason.ACTIVITY_CHANGE] == 1
        assert result.split_reasons[SplitReason.TIME_GAP] == 0

    def test_location_change_beats_activity_change(self) -> None:
        """Location change has priority over activity change."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, location_geohash="u4pruyd", activity_type="work"),
            # Both location AND activity change
            MockEvent(
                "e2",
                base_ts + 1000,
                location_geohash="gcpvj0d",  # Different location
                activity_type="exercise",  # Different activity
            ),
        ]

        config = SplitConfig(geohash_distance_threshold=4)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        assert len(result.episodes) == 2
        # Location change should be the recorded reason (highest priority)
        assert result.split_reasons[SplitReason.LOCATION_CHANGE] == 1
        assert result.split_reasons[SplitReason.ACTIVITY_CHANGE] == 0


# =============================================================================
# Geohash Distance Tests
# =============================================================================


class TestGeohashDistance:
    """Test geohash distance calculation."""

    def test_geohash_distance_identical(self) -> None:
        """Identical geohashes have distance 0."""
        splitter = EpisodeSplitter()

        assert splitter._geohash_distance("u4pruyd", "u4pruyd") == 0

    def test_geohash_distance_one_char_diff(self) -> None:
        """One character difference at end."""
        splitter = EpisodeSplitter()

        # Differ at last character
        assert splitter._geohash_distance("u4pruyd", "u4pruyc") == 1

    def test_geohash_distance_completely_different(self) -> None:
        """Completely different geohashes."""
        splitter = EpisodeSplitter()

        # Differ from first character
        assert splitter._geohash_distance("u4pruyd", "gcpvj0d") == 7

    def test_geohash_distance_empty(self) -> None:
        """Empty geohash handling."""
        splitter = EpisodeSplitter()

        assert splitter._geohash_distance("", "abc") == 3
        assert splitter._geohash_distance("abc", "") == 3
        assert splitter._geohash_distance("", "") == 0

    def test_geohash_distance_different_lengths(self) -> None:
        """Different length geohashes."""
        splitter = EpisodeSplitter()

        # Same prefix, different lengths
        assert splitter._geohash_distance("u4pruy", "u4pruyd") == 1

        # Different from start
        assert splitter._geohash_distance("u4", "gcpvj0d") == 7


# =============================================================================
# Split Result Metadata Tests
# =============================================================================


class TestSplitResultMetadata:
    """Test split result metadata tracking."""

    def test_split_result_counts(self) -> None:
        """Split result tracks counts correctly."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts),
            MockEvent("e2", base_ts + 50 * MS_PER_MINUTE),  # Split here
            MockEvent("e3", base_ts + 100 * MS_PER_MINUTE),  # Split here
            MockEvent("e4", base_ts + 110 * MS_PER_MINUTE),
        ]

        config = SplitConfig(time_gap_minutes=30.0)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        assert result.episode_count == 3
        assert result.total_events == 4
        assert result.split_count == 2
        assert result.split_reasons[SplitReason.TIME_GAP] == 2

    def test_get_split_stats(self) -> None:
        """Get detailed statistics from split result."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts),
            MockEvent("e2", base_ts + 1000),
            MockEvent("e3", base_ts + 50 * MS_PER_MINUTE),  # Split
            MockEvent("e4", base_ts + 51 * MS_PER_MINUTE),
            MockEvent("e5", base_ts + 52 * MS_PER_MINUTE),
        ]

        config = SplitConfig(time_gap_minutes=30.0)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        stats = splitter.get_split_stats(result)

        assert stats["episode_count"] == 2
        assert stats["total_events"] == 5
        assert stats["split_count"] == 1
        assert stats["avg_episode_size"] == 2.5
        assert stats["min_episode_size"] == 2
        assert stats["max_episode_size"] == 3

    def test_get_split_stats_empty(self) -> None:
        """Statistics for empty result."""
        splitter = EpisodeSplitter()
        result = splitter.split([])

        stats = splitter.get_split_stats(result)

        assert stats["episode_count"] == 0
        assert stats["total_events"] == 0
        assert stats["avg_episode_size"] == 0.0


# =============================================================================
# Edge Cases
# =============================================================================


class TestEpisodeSplitterEdgeCases:
    """Test edge cases."""

    def test_missing_geohash(self) -> None:
        """Events without geohash don't trigger location split."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, location_geohash=None),
            MockEvent("e2", base_ts + 1000, location_geohash=None),
        ]

        splitter = EpisodeSplitter()
        result = splitter.split(events)

        assert len(result.episodes) == 1
        assert result.split_reasons[SplitReason.LOCATION_CHANGE] == 0

    def test_missing_activity_type(self) -> None:
        """Events without activity_type don't trigger activity split."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, activity_type=None),
            MockEvent("e2", base_ts + 1000, activity_type=None),
        ]

        splitter = EpisodeSplitter()
        result = splitter.split(events)

        assert len(result.episodes) == 1
        assert result.split_reasons[SplitReason.ACTIVITY_CHANGE] == 0

    def test_partial_geohash_available(self) -> None:
        """One event has geohash, other doesn't — no location split."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, location_geohash="u4pruyd"),
            MockEvent("e2", base_ts + 1000, location_geohash=None),
        ]

        splitter = EpisodeSplitter()
        result = splitter.split(events)

        assert len(result.episodes) == 1

    def test_partial_activity_available(self) -> None:
        """One event has activity, other doesn't — no activity split."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, activity_type="work"),
            MockEvent("e2", base_ts + 1000, activity_type=None),
        ]

        splitter = EpisodeSplitter()
        result = splitter.split(events)

        assert len(result.episodes) == 1

    def test_geohash_6_attribute_fallback(self) -> None:
        """Fallback to geohash_6 attribute if location_geohash not present."""
        base_ts = 1000000000000

        @dataclass
        class EventWithGeohash6:
            event_id: str
            timestamp: int
            geohash_6: Optional[str] = None

        events = [
            EventWithGeohash6("e1", base_ts, geohash_6="u4pruy"),
            EventWithGeohash6("e2", base_ts + 1000, geohash_6="gcpvj0"),
        ]

        config = SplitConfig(geohash_distance_threshold=4)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)  # type: ignore

        assert len(result.episodes) == 2
        assert result.split_reasons[SplitReason.LOCATION_CHANGE] == 1
