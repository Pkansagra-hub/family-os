"""
Integration tests for RoutineDetector with historical episode data — M2-E3-I2

Tests RoutineDetector's ability to detect patterns in merged episode data
simulating real-world scenarios with current + accumulated episodes.
"""

import pytest

from k0.modules.consolidation.dream.dream_explorer import DreamExplorer
from k0.modules.consolidation.dream.models import DreamExplorerInput
from k0.pipelines.p03.phase_outputs import EpisodeCluster


class TestRoutineDetectorHistoricalIntegration:
    """Integration tests for RoutineDetector with merged historical data."""

    @pytest.mark.asyncio
    async def test_routine_detection_with_merged_episodes(self):
        """Verify RoutineDetector finds patterns in merged historical data."""

        # Simulate 100+ episodes: current + accumulated from PostgreSQL
        episodes = []

        # Create strong pattern: coffee at starbucks at 8am (20 occurrences)
        base_time = 1705000000000  # 2024-01-11 22:26:40 UTC
        for i in range(20):
            episodes.append(
                EpisodeCluster(
                    cluster_id=f"coffee_{i}",
                    activity_type="coffee",
                    location_hint="starbucks",
                    temporal_start=base_time + (i * 24 * 60 * 60 * 1000),  # Daily at same time
                    temporal_end=base_time
                    + (i * 24 * 60 * 60 * 1000)
                    + (60 * 60 * 1000),  # +1 hour
                    summary="Morning coffee routine",
                )
            )

        # Create another strong pattern: gym at 6pm (15 occurrences)
        gym_time = base_time + (10 * 60 * 60 * 1000)  # 6pm same day
        for i in range(15):
            episodes.append(
                EpisodeCluster(
                    cluster_id=f"gym_{i}",
                    activity_type="exercise",
                    location_hint="fitness_center",
                    temporal_start=gym_time + (i * 24 * 60 * 60 * 1000),  # Daily at 6pm
                    temporal_end=gym_time
                    + (i * 24 * 60 * 60 * 1000)
                    + (90 * 60 * 1000),  # +1.5 hours
                    summary="Evening gym routine",
                )
            )

        # Create weaker pattern: lunch at office (8 occurrences)
        lunch_time = base_time + (12 * 60 * 60 * 1000)  # Noon
        for i in range(8):
            episodes.append(
                EpisodeCluster(
                    cluster_id=f"lunch_{i}",
                    activity_type="meal",
                    location_hint="office",
                    temporal_start=lunch_time + (i * 24 * 60 * 60 * 1000),  # Daily at noon
                    temporal_end=lunch_time
                    + (i * 24 * 60 * 60 * 1000)
                    + (30 * 60 * 1000),  # +30 min
                    summary="Lunch break",
                )
            )

        # Create noise episodes (60 random episodes)
        import random

        activities = ["work", "meeting", "shopping", "reading", "walking", "cooking"]
        locations = ["home", "office", "store", "park", "restaurant", "library"]

        for i in range(60):
            episodes.append(
                EpisodeCluster(
                    cluster_id=f"noise_{i}",
                    activity_type=random.choice(activities),
                    location_hint=random.choice(locations),
                    temporal_start=base_time
                    + random.randint(0, 30 * 24 * 60 * 60 * 1000),  # Random time
                    temporal_end=base_time
                    + random.randint(0, 30 * 24 * 60 * 60 * 1000)
                    + random.randint(30 * 60 * 1000, 4 * 60 * 60 * 1000),  # Random duration
                    summary=f"Random activity {i}",
                )
            )

        # Create DreamExplorer and test
        explorer = DreamExplorer()
        input_data = DreamExplorerInput(
            cycle_id="test_historical_integration",
            tenant_id="test_tenant",
            space_id="test_space",
            recent_episodes=episodes,
        )

        candidates = await explorer._run_routine_detector(input_data, "test_historical_integration")

        # Should detect at least the strong patterns (coffee and gym)
        assert len(candidates) >= 2, f"Expected at least 2 routines, got {len(candidates)}"

        # Verify coffee routine detected with high confidence
        coffee_routines = [c for c in candidates if "coffee" in c.routine_name.lower()]
        assert len(coffee_routines) >= 1, "Coffee routine should be detected"
        coffee_routine = coffee_routines[0]
        assert (
            coffee_routine.source_episode_count >= 15
        ), f"Coffee routine should have at least 15 episodes, got {coffee_routine.source_episode_count}"
        assert (
            coffee_routine.habit_strength > 0.5
        ), f"Coffee routine should have high habit strength, got {coffee_routine.habit_strength}"
        assert (
            "starbucks" in coffee_routine.routine_name.lower()
        ), f"Coffee routine should mention starbucks, got: {coffee_routine.routine_name}"

        # Verify gym routine detected
        gym_routines = [
            c
            for c in candidates
            if "gym" in c.routine_name.lower() or "exercise" in c.routine_name.lower()
        ]
        assert len(gym_routines) >= 1, "Gym routine should be detected"
        gym_routine = gym_routines[0]
        assert (
            gym_routine.source_episode_count >= 10
        ), f"Gym routine should have at least 10 episodes, got {gym_routine.source_episode_count}"

        # Verify lunch routine might be detected (weaker pattern)
        lunch_routines = [
            c
            for c in candidates
            if "lunch" in c.routine_name.lower() or "meal" in c.routine_name.lower()
        ]
        # Lunch might not be detected due to min_occurrences=3 and noise, so we don't assert

        # Verify all detected routines have reasonable properties
        for candidate in candidates:
            assert (
                candidate.source_episode_count >= 3
            ), f"Routine should have at least 3 episodes, got {candidate.source_episode_count}"
            assert (
                0.0 <= candidate.habit_strength <= 1.0
            ), f"Habit strength should be between 0-1, got {candidate.habit_strength}"
            assert (
                0.0 <= candidate.confidence_score <= 1.0
            ), f"Confidence should be between 0-1, got {candidate.confidence_score}"
            assert candidate.routine_name, "Routine name should not be empty"

    @pytest.mark.asyncio
    async def test_routine_detection_with_empty_historical_data(self):
        """Verify RoutineDetector handles cases with no historical patterns."""

        # Create only noise episodes (no strong patterns)
        episodes = []
        base_time = 1705000000000

        activities = ["work", "meeting", "shopping", "reading", "walking"]
        locations = ["home", "office", "store", "park", "restaurant"]

        for i in range(50):
            episodes.append(
                EpisodeCluster(
                    cluster_id=f"noise_{i}",
                    activity_type=activities[i % len(activities)],
                    location_hint=locations[i % len(locations)],
                    temporal_start=base_time + (i * 60 * 60 * 1000),  # Every hour
                    temporal_end=base_time + (i * 60 * 60 * 1000) + (30 * 60 * 1000),  # +30 min
                    summary=f"Noise activity {i}",
                )
            )

        explorer = DreamExplorer()
        input_data = DreamExplorerInput(
            cycle_id="test_no_patterns",
            tenant_id="test_tenant",
            space_id="test_space",
            recent_episodes=episodes,
        )

        candidates = await explorer._run_routine_detector(input_data, "test_no_patterns")

        # With random noise, might detect some weak patterns or none
        # Just verify it doesn't crash and returns reasonable results
        assert isinstance(candidates, list), "Should return a list"
        for candidate in candidates:
            assert (
                candidate.source_episode_count >= 3
            ), "Any detected routine should meet minimum threshold"

    @pytest.mark.asyncio
    async def test_routine_detection_scalability(self):
        """Verify RoutineDetector handles large episode sets efficiently."""

        # Create 500 episodes (realistic scale for accumulated + current)
        episodes = []
        base_time = 1705000000000

        # Strong pattern: morning coffee (50 occurrences)
        for i in range(50):
            episodes.append(
                EpisodeCluster(
                    cluster_id=f"coffee_{i}",
                    activity_type="coffee",
                    location_hint="kitchen",
                    temporal_start=base_time + (i * 24 * 60 * 60 * 1000),
                    temporal_end=base_time + (i * 24 * 60 * 60 * 1000) + (60 * 60 * 1000),
                    summary="Morning coffee",
                )
            )

        # Fill remaining with noise
        activities = ["work", "meeting", "shopping", "reading", "walking", "cooking"]
        locations = ["home", "office", "store", "park", "restaurant", "library"]

        for i in range(450):
            episodes.append(
                EpisodeCluster(
                    cluster_id=f"noise_{i}",
                    activity_type=activities[i % len(activities)],
                    location_hint=locations[i % len(locations)],
                    temporal_start=base_time + (i * 30 * 60 * 1000),  # Every 30 min
                    temporal_end=base_time + (i * 30 * 60 * 1000) + (15 * 60 * 1000),  # +15 min
                    summary=f"Noise {i}",
                )
            )

        explorer = DreamExplorer()
        input_data = DreamExplorerInput(
            cycle_id="test_scalability",
            tenant_id="test_tenant",
            space_id="test_space",
            recent_episodes=episodes,
        )

        import time

        start_time = time.time()
        candidates = await explorer._run_routine_detector(input_data, "test_scalability")
        duration = time.time() - start_time

        # Should complete in reasonable time (< 5 seconds for 500 episodes)
        assert duration < 5.0, f"Routine detection took too long: {duration:.2f}s"

        # Should detect the strong coffee pattern
        coffee_routines = [c for c in candidates if "coffee" in c.routine_name.lower()]
        assert len(coffee_routines) >= 1, "Should detect coffee routine in large dataset"
        assert (
            coffee_routines[0].source_episode_count >= 40
        ), "Coffee routine should have most episodes"
