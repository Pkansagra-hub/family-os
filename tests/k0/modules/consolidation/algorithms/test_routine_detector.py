"""
Tests for RoutineDetector — GAP-003 Implementation.

Tests the detection of recurring behavioral patterns from episodic memory.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from k0.modules.consolidation.algorithms.routine_detector import (
    FrequencyPattern,
    RoutineCandidate,
    RoutineDetector,
    RoutineLifecycle,
)

# =============================================================================
# Test Fixtures
# =============================================================================


def make_episode(
    episode_id: str,
    activity_type: str,
    location: str,
    start_time_utc: int,
    end_time_utc: int | None = None,
    episode_summary: str = "",
) -> Dict[str, Any]:
    """Create a test episode dict."""
    return {
        "episode_id": episode_id,
        "activity_type": activity_type,
        "primary_location": location,
        "start_time_utc": start_time_utc,
        "end_time_utc": end_time_utc or start_time_utc + 3600000,  # +1 hour
        "episode_summary": episode_summary,
    }


def make_daily_episodes(
    activity: str,
    location: str,
    count: int,
    start_time_ms: int,
    interval_ms: int = 24 * 60 * 60 * 1000,  # 1 day
) -> List[Dict[str, Any]]:
    """Create a sequence of daily episodes."""
    episodes = []
    for i in range(count):
        episodes.append(
            make_episode(
                episode_id=f"ep_{activity}_{i}",
                activity_type=activity,
                location=location,
                start_time_utc=start_time_ms + (i * interval_ms),
                episode_summary=f"{activity} at {location}",
            )
        )
    return episodes


@pytest.fixture
def detector() -> RoutineDetector:
    """Provide a RoutineDetector instance."""
    return RoutineDetector()


# =============================================================================
# Test Basic Detection
# =============================================================================


class TestBasicDetection:
    """Test basic routine detection functionality."""

    def test_empty_episodes_returns_empty(self, detector: RoutineDetector) -> None:
        """Empty input returns empty result."""
        result = detector.detect([])
        assert result == []

    def test_single_episode_no_routine(self, detector: RoutineDetector) -> None:
        """Single episode doesn't form a routine."""
        episodes = [make_episode("ep1", "coffee", "starbucks", 1700000000000)]
        result = detector.detect(episodes)
        assert result == []

    def test_two_episodes_no_routine(self, detector: RoutineDetector) -> None:
        """Two episodes don't meet minimum occurrence threshold."""
        episodes = [
            make_episode("ep1", "coffee", "starbucks", 1700000000000),
            make_episode("ep2", "coffee", "starbucks", 1700086400000),
        ]
        result = detector.detect(episodes)
        assert result == []

    def test_three_episodes_forms_routine(self, detector: RoutineDetector) -> None:
        """Three similar episodes form a routine candidate."""
        base_time = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        episodes = [
            make_episode("ep1", "coffee", "starbucks", base_time),
            make_episode("ep2", "coffee", "starbucks", base_time + day_ms),
            make_episode("ep3", "coffee", "starbucks", base_time + 2 * day_ms),
        ]

        result = detector.detect(episodes)

        assert len(result) == 1
        routine = result[0]
        assert isinstance(routine, RoutineCandidate)
        assert routine.source_episode_count == 3
        assert "coffee" in routine.routine_name.lower()


class TestPatternGrouping:
    """Test episode grouping by signature."""

    def test_different_activities_separate_routines(self, detector: RoutineDetector) -> None:
        """Different activity types create separate routines."""
        base_time = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        episodes = [
            # Coffee routine (3 occurrences)
            make_episode("ep1", "coffee", "cafe", base_time),
            make_episode("ep2", "coffee", "cafe", base_time + day_ms),
            make_episode("ep3", "coffee", "cafe", base_time + 2 * day_ms),
            # Gym routine (3 occurrences)
            make_episode("ep4", "gym", "fitness_center", base_time),
            make_episode("ep5", "gym", "fitness_center", base_time + day_ms),
            make_episode("ep6", "gym", "fitness_center", base_time + 2 * day_ms),
        ]

        result = detector.detect(episodes)

        assert len(result) == 2
        routine_names = [r.routine_name.lower() for r in result]
        assert any("coffee" in name for name in routine_names)
        assert any("gym" in name for name in routine_names)

    def test_same_activity_different_locations(self, detector: RoutineDetector) -> None:
        """Same activity at different locations creates separate routines."""
        base_time = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        episodes = [
            # Coffee at Starbucks (3x)
            make_episode("ep1", "coffee", "starbucks", base_time),
            make_episode("ep2", "coffee", "starbucks", base_time + day_ms),
            make_episode("ep3", "coffee", "starbucks", base_time + 2 * day_ms),
            # Coffee at Peets (3x)
            make_episode("ep4", "coffee", "peets", base_time),
            make_episode("ep5", "coffee", "peets", base_time + day_ms),
            make_episode("ep6", "coffee", "peets", base_time + 2 * day_ms),
        ]

        result = detector.detect(episodes)

        assert len(result) == 2
        locations = [r.routine_name.lower() for r in result]
        assert any("starbucks" in loc for loc in locations)
        assert any("peets" in loc for loc in locations)


class TestTemporalAnalysis:
    """Test temporal pattern analysis."""

    def test_daily_pattern_detected(self, detector: RoutineDetector) -> None:
        """Daily pattern is correctly identified."""
        episodes = make_daily_episodes(
            activity="coffee",
            location="cafe",
            count=10,
            start_time_ms=1700000000000,
            interval_ms=24 * 60 * 60 * 1000,
        )

        result = detector.detect(episodes)

        assert len(result) == 1
        routine = result[0]
        assert routine.frequency == FrequencyPattern.DAILY
        assert routine.regularity_score > 0.8

    def test_weekly_pattern_detected(self, detector: RoutineDetector) -> None:
        """Weekly pattern is correctly identified."""
        episodes = make_daily_episodes(
            activity="gym",
            location="fitness_center",
            count=8,
            start_time_ms=1700000000000,
            interval_ms=7 * 24 * 60 * 60 * 1000,  # Weekly
        )

        result = detector.detect(episodes)

        assert len(result) == 1
        routine = result[0]
        assert routine.frequency == FrequencyPattern.WEEKLY

    def test_irregular_pattern_low_regularity(self) -> None:
        """Irregular timing produces low regularity score."""
        # Use detector with no minimum consistency filter
        detector = RoutineDetector(min_consistency=0.0)

        base_time = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        # Irregular intervals
        episodes = [
            make_episode("ep1", "shopping", "mall", base_time),
            make_episode("ep2", "shopping", "mall", base_time + 2 * day_ms),
            make_episode("ep3", "shopping", "mall", base_time + 10 * day_ms),
            make_episode("ep4", "shopping", "mall", base_time + 12 * day_ms),
        ]

        result = detector.detect(episodes)

        assert len(result) == 1
        routine = result[0]
        assert routine.regularity_score < 0.5


class TestHabitStrength:
    """Test habit strength calculation."""

    def test_more_occurrences_higher_strength(self, detector: RoutineDetector) -> None:
        """More occurrences produce higher habit strength."""
        base_time = 1700000000000

        # 5 occurrences
        episodes_5 = make_daily_episodes("coffee", "cafe", 5, base_time)
        result_5 = detector.detect(episodes_5)

        # 15 occurrences
        episodes_15 = make_daily_episodes("coffee", "cafe", 15, base_time)
        result_15 = detector.detect(episodes_15)

        assert len(result_5) == 1
        assert len(result_15) == 1
        assert result_15[0].habit_strength > result_5[0].habit_strength

    def test_recent_activity_higher_strength(self, detector: RoutineDetector) -> None:
        """Recent activity produces higher habit strength."""
        now_ms = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        # Recent routine (last occurrence today)
        episodes_recent = make_daily_episodes("coffee", "cafe", 5, now_ms - 4 * day_ms)

        # Old routine (last occurrence 20 days ago)
        episodes_old = make_daily_episodes("coffee", "cafe", 5, now_ms - 24 * day_ms)

        result_recent = detector.detect(episodes_recent, reference_time_ms=now_ms)
        result_old = detector.detect(episodes_old, reference_time_ms=now_ms)

        assert len(result_recent) == 1
        assert len(result_old) == 1
        assert result_recent[0].habit_strength > result_old[0].habit_strength


class TestLifecycleState:
    """Test lifecycle state determination."""

    def test_forming_state_few_occurrences(self, detector: RoutineDetector) -> None:
        """Few occurrences result in FORMING state."""
        now_ms = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        # 3 daily occurrences ending recently
        episodes = make_daily_episodes("coffee", "cafe", 3, now_ms - 2 * day_ms)
        result = detector.detect(episodes, reference_time_ms=now_ms)

        assert len(result) == 1
        assert result[0].lifecycle_state == RoutineLifecycle.FORMING

    def test_established_state_many_occurrences(self, detector: RoutineDetector) -> None:
        """Many regular occurrences result in ESTABLISHED state."""
        now_ms = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        # 15 daily occurrences ending recently
        episodes = make_daily_episodes("coffee", "cafe", 15, now_ms - 14 * day_ms)

        result = detector.detect(episodes, reference_time_ms=now_ms)

        assert len(result) == 1
        # Should be MAINTAINED or ESTABLISHED due to high count and consistency
        assert result[0].lifecycle_state in [
            RoutineLifecycle.ESTABLISHED,
            RoutineLifecycle.MAINTAINED,
        ]

    def test_decaying_state_missed_occurrences(self, detector: RoutineDetector) -> None:
        """Missed expected occurrences result in DECAYING state."""
        now_ms = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        # Daily routine that stopped 10 days ago
        episodes = make_daily_episodes("coffee", "cafe", 10, now_ms - 20 * day_ms)

        result = detector.detect(episodes, reference_time_ms=now_ms)

        assert len(result) == 1
        assert result[0].lifecycle_state in [
            RoutineLifecycle.DECAYING,
            RoutineLifecycle.EXTINCT,
        ]


class TestCategoryDetection:
    """Test routine category detection."""

    def test_meal_category(self, detector: RoutineDetector) -> None:
        """Meal activities categorized as FOOD_DRINK."""
        episodes = make_daily_episodes("lunch", "restaurant", 5, 1700000000000)
        result = detector.detect(episodes)

        assert len(result) == 1
        assert result[0].routine_category == "FOOD_DRINK"

    def test_exercise_category(self, detector: RoutineDetector) -> None:
        """Exercise activities categorized as EXERCISE."""
        episodes = make_daily_episodes("workout", "gym", 5, 1700000000000)
        result = detector.detect(episodes)

        assert len(result) == 1
        assert result[0].routine_category == "EXERCISE"

    def test_work_category(self, detector: RoutineDetector) -> None:
        """Work activities categorized as WORK."""
        episodes = make_daily_episodes("meeting", "office", 5, 1700000000000)
        result = detector.detect(episodes)

        assert len(result) == 1
        assert result[0].routine_category == "WORK"


class TestCueDetection:
    """Test triggering cue detection."""

    def test_temporal_cue_detected(self, detector: RoutineDetector) -> None:
        """Temporal cues are detected."""
        episodes = make_daily_episodes("coffee", "cafe", 5, 1700000000000)
        result = detector.detect(episodes)

        assert len(result) == 1
        cues = result[0].triggering_cues
        assert any("time:" in cue for cue in cues)

    def test_location_cue_detected(self, detector: RoutineDetector) -> None:
        """Location cues are detected for consistent locations."""
        episodes = make_daily_episodes("coffee", "starbucks", 5, 1700000000000)
        result = detector.detect(episodes)

        assert len(result) == 1
        cues = result[0].triggering_cues
        assert any("location:starbucks" in cue for cue in cues)


class TestEdgeCases:
    """Test edge cases and robustness."""

    def test_missing_activity_type(self, detector: RoutineDetector) -> None:
        """Episodes with missing activity type are handled."""
        base_time = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        episodes = [
            {"episode_id": "ep1", "primary_location": "cafe", "start_time_utc": base_time},
            {"episode_id": "ep2", "primary_location": "cafe", "start_time_utc": base_time + day_ms},
            {
                "episode_id": "ep3",
                "primary_location": "cafe",
                "start_time_utc": base_time + 2 * day_ms,
            },
        ]

        # Should not crash, may produce routine based on location only
        result = detector.detect(episodes)
        assert isinstance(result, list)

    def test_missing_location(self, detector: RoutineDetector) -> None:
        """Episodes with missing location are handled."""
        base_time = 1700000000000
        day_ms = 24 * 60 * 60 * 1000

        episodes = [
            {"episode_id": "ep1", "activity_type": "coffee", "start_time_utc": base_time},
            {"episode_id": "ep2", "activity_type": "coffee", "start_time_utc": base_time + day_ms},
            {
                "episode_id": "ep3",
                "activity_type": "coffee",
                "start_time_utc": base_time + 2 * day_ms,
            },
        ]

        # Should produce routine based on activity only
        result = detector.detect(episodes)
        assert len(result) == 1
        assert "coffee" in result[0].routine_name.lower()

    def test_custom_min_occurrences(self) -> None:
        """Custom minimum occurrences threshold works."""
        detector = RoutineDetector(min_occurrences=5)
        episodes = make_daily_episodes("coffee", "cafe", 3, 1700000000000)

        result = detector.detect(episodes)
        assert result == []  # 3 < 5 minimum

    def test_source_episodes_json_populated(self, detector: RoutineDetector) -> None:
        """Source episodes JSON contains all episode IDs."""
        episodes = make_daily_episodes("coffee", "cafe", 5, 1700000000000)
        result = detector.detect(episodes)

        assert len(result) == 1
        source_ids = json.loads(result[0].source_episodes_json)
        assert len(source_ids) == 5
        assert all("ep_coffee_" in id for id in source_ids)
