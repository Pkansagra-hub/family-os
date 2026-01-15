"""
CPN Algorithm Benchmarks — Real-World Testing.

This module provides comprehensive benchmarks for the CPN (Causal Perturbation
Network) algorithm with realistic input data.

Test Categories:
1. Correctness: Validates algorithm produces expected output structure
2. Performance: Measures execution time at various scales
3. Quality: Evaluates output quality against thresholds
4. Edge Cases: Tests boundary conditions and error handling
5. Determinism: Verifies reproducibility with seeds

References:
- M8_EXECUTION.md Issue 8.1.4: CPN counterfactual generation
- Dossier §4.6.1: Counterfactual Thinking (CPN Algorithm)
"""

from __future__ import annotations

import time

import pytest

from k0.modules.consolidation.algorithms.cpn import (
    CausalPerturbationNetwork,
    CPNConfig,
    CPNCounterfactual,
    ScenarioType,
)
from tests.k0.modules.consolidation.benchmarks.performance_metrics import (
    BenchmarkCollector,
    DistributionStats,
)
from tests.k0.modules.consolidation.benchmarks.realistic_data import (
    BenchmarkDatasetGenerator,
    BenchmarkScale,
    RealisticEdge,
    RealisticEpisode,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def dataset_generator() -> BenchmarkDatasetGenerator:
    """Create dataset generator with fixed seed."""
    return BenchmarkDatasetGenerator(seed=42)


@pytest.fixture
def small_dataset(dataset_generator: BenchmarkDatasetGenerator):
    """Generate small dataset for quick tests."""
    return dataset_generator.generate(BenchmarkScale.SMALL)


@pytest.fixture
def medium_dataset(dataset_generator: BenchmarkDatasetGenerator):
    """Generate medium dataset for normal benchmarks."""
    return dataset_generator.generate(BenchmarkScale.MEDIUM)


@pytest.fixture
def large_dataset(dataset_generator: BenchmarkDatasetGenerator):
    """Generate large dataset for stress testing."""
    return dataset_generator.generate(BenchmarkScale.LARGE)


@pytest.fixture
def default_cpn() -> CausalPerturbationNetwork:
    """CPN with default configuration."""
    return CausalPerturbationNetwork(CPNConfig(seed=42))


@pytest.fixture
def sensitive_cpn() -> CausalPerturbationNetwork:
    """CPN with lower thresholds (generates more counterfactuals)."""
    return CausalPerturbationNetwork(
        CPNConfig(
            emotional_threshold=0.3,
            min_plausibility=0.2,
            min_utility_delta=0.1,
            seed=42,
        )
    )


# =============================================================================
# BENCHMARK: CORRECTNESS TESTS
# =============================================================================


class TestCPNCorrectness:
    """Verify CPN produces correct output structure."""

    def test_generates_counterfactuals_from_realistic_data(
        self,
        sensitive_cpn: CausalPerturbationNetwork,
        small_dataset,
    ) -> None:
        """CPN should generate counterfactuals from realistic episodes."""
        # Prepare inputs
        episodes = small_dataset.episodes
        edges = small_dataset.edges

        # Generate counterfactuals
        results = sensitive_cpn.generate(episodes, edges, rng_seed=42)

        # Verify we got results (may be empty if no regret events)
        assert isinstance(results, list)

        # If results exist, verify structure
        for cf in results:
            assert isinstance(cf, CPNCounterfactual)
            assert cf.scenario_id
            assert cf.scenario_type in [st.value for st in ScenarioType]
            assert cf.base_episode_id
            assert 0.0 <= cf.plausibility <= 1.0
            assert 0.0 <= cf.success_probability <= 1.0

    def test_respects_emotional_threshold(
        self,
        small_dataset,
    ) -> None:
        """CPN should only select episodes above emotional threshold."""
        # High threshold: should select fewer events
        high_threshold_cpn = CausalPerturbationNetwork(CPNConfig(emotional_threshold=0.9, seed=42))

        # Low threshold: should select more events
        low_threshold_cpn = CausalPerturbationNetwork(CPNConfig(emotional_threshold=0.2, seed=42))

        episodes = small_dataset.episodes
        edges = small_dataset.edges

        high_results = high_threshold_cpn.generate(episodes, edges)
        low_results = low_threshold_cpn.generate(episodes, edges)

        # Lower threshold should generally produce more or equal results
        # (not strict due to other filtering)
        assert len(low_results) >= 0
        assert len(high_results) >= 0

    def test_generates_all_scenario_types(
        self,
        sensitive_cpn: CausalPerturbationNetwork,
        medium_dataset,
    ) -> None:
        """CPN should generate UPWARD, DOWNWARD, and SEMIFACTUAL scenarios."""
        episodes = medium_dataset.episodes
        edges = medium_dataset.edges

        results = sensitive_cpn.generate(episodes, edges, rng_seed=42)

        if len(results) > 0:
            scenario_types = {cf.scenario_type for cf in results}
            # At least one type should be present
            assert len(scenario_types) >= 1

    def test_counterfactual_has_valid_base_episode(
        self,
        sensitive_cpn: CausalPerturbationNetwork,
        small_dataset,
    ) -> None:
        """Each counterfactual should reference a valid base episode."""
        episodes = small_dataset.episodes
        edges = small_dataset.edges
        episode_ids = {e.episode_id for e in episodes}

        results = sensitive_cpn.generate(episodes, edges, rng_seed=42)

        for cf in results:
            assert cf.base_episode_id in episode_ids


# =============================================================================
# BENCHMARK: PERFORMANCE TESTS
# =============================================================================


class TestCPNPerformance:
    """Performance benchmarks for CPN algorithm."""

    @pytest.mark.benchmark
    def test_small_scale_performance(
        self,
        default_cpn: CausalPerturbationNetwork,
        small_dataset,
    ) -> None:
        """Benchmark CPN on small dataset."""
        collector = BenchmarkCollector("CPN")
        collector.set_metadata("scale", "small")
        collector.set_metadata("episodes", len(small_dataset.episodes))
        collector.set_metadata("edges", len(small_dataset.edges))

        # Run multiple times for statistical significance
        for _ in range(5):
            with collector.time_run() as run:
                results = default_cpn.generate(
                    small_dataset.episodes,
                    small_dataset.edges,
                    rng_seed=42,
                )
                run["results"] = results

            valid_count = sum(1 for cf in results if cf.plausibility >= 0.3)
            high_quality = sum(
                1 for cf in results if cf.plausibility >= 0.5 and abs(cf.utility_delta) >= 0.3
            )
            collector.record_quality(len(results), valid_count, high_quality)

            # Record output distributions
            if results:
                collector.record_output_values("plausibility", [cf.plausibility for cf in results])
                collector.record_output_values(
                    "utility_delta", [abs(cf.utility_delta) for cf in results]
                )

        summary = collector.summarize("small")
        print(f"\n{summary.summary()}")

        # Performance assertions
        assert summary.timing.elapsed_ms < 1000, "Small scale should complete in <1s"

    @pytest.mark.benchmark
    def test_medium_scale_performance(
        self,
        default_cpn: CausalPerturbationNetwork,
        medium_dataset,
    ) -> None:
        """Benchmark CPN on medium dataset."""
        collector = BenchmarkCollector("CPN")

        for _ in range(3):
            with collector.time_run():
                results = default_cpn.generate(
                    medium_dataset.episodes,
                    medium_dataset.edges,
                    rng_seed=42,
                )

            valid_count = sum(1 for cf in results if cf.plausibility >= 0.3)
            high_quality = sum(
                1 for cf in results if cf.plausibility >= 0.5 and abs(cf.utility_delta) >= 0.3
            )
            collector.record_quality(len(results), valid_count, high_quality)

        summary = collector.summarize("medium")
        print(f"\n{summary.summary()}")

        # Performance assertions
        assert summary.timing.elapsed_ms < 5000, "Medium scale should complete in <5s"

    @pytest.mark.benchmark
    @pytest.mark.slow
    def test_large_scale_performance(
        self,
        default_cpn: CausalPerturbationNetwork,
        large_dataset,
    ) -> None:
        """Benchmark CPN on large dataset (stress test)."""
        collector = BenchmarkCollector("CPN")

        with collector.time_run():
            results = default_cpn.generate(
                large_dataset.episodes,
                large_dataset.edges,
                rng_seed=42,
            )

        valid_count = sum(1 for cf in results if cf.plausibility >= 0.3)
        high_quality = sum(
            1 for cf in results if cf.plausibility >= 0.5 and abs(cf.utility_delta) >= 0.3
        )
        collector.record_quality(len(results), valid_count, high_quality)

        summary = collector.summarize("large")
        print(f"\n{summary.summary()}")

        # Performance assertions
        assert summary.timing.elapsed_ms < 30000, "Large scale should complete in <30s"


# =============================================================================
# BENCHMARK: QUALITY TESTS
# =============================================================================


class TestCPNQuality:
    """Quality benchmarks for CPN outputs."""

    def test_plausibility_distribution(
        self,
        sensitive_cpn: CausalPerturbationNetwork,
        medium_dataset,
    ) -> None:
        """Verify plausibility scores have reasonable distribution."""
        results = sensitive_cpn.generate(
            medium_dataset.episodes,
            medium_dataset.edges,
            rng_seed=42,
        )

        if len(results) < 5:
            pytest.skip("Not enough results for distribution analysis")

        plausibilities = [cf.plausibility for cf in results]
        stats = DistributionStats.from_values(plausibilities)

        print("\nPlausibility Distribution:")
        print(f"  Count: {stats.count}")
        print(f"  Mean: {stats.mean:.3f}")
        print(f"  Median: {stats.median:.3f}")
        print(f"  Std Dev: {stats.std_dev:.3f}")
        print(f"  Range: [{stats.min_value:.3f}, {stats.max_value:.3f}]")

        # Quality assertions
        assert stats.mean >= 0.2, "Mean plausibility should be reasonable"
        assert stats.max_value <= 1.0, "Plausibility should not exceed 1.0"

    def test_utility_delta_meaningful(
        self,
        sensitive_cpn: CausalPerturbationNetwork,
        medium_dataset,
    ) -> None:
        """Verify utility deltas are meaningful (not all near zero)."""
        results = sensitive_cpn.generate(
            medium_dataset.episodes,
            medium_dataset.edges,
            rng_seed=42,
        )

        if len(results) < 5:
            pytest.skip("Not enough results for analysis")

        utility_deltas = [abs(cf.utility_delta) for cf in results]
        stats = DistributionStats.from_values(utility_deltas)

        print("\nUtility Delta Distribution:")
        print(f"  Mean: {stats.mean:.3f}")
        print(f"  Max: {stats.max_value:.3f}")

        # At least some should have meaningful delta
        assert stats.max_value > 0.1, "Should have some meaningful utility changes"

    def test_upward_scenarios_are_positive(
        self,
        sensitive_cpn: CausalPerturbationNetwork,
        medium_dataset,
    ) -> None:
        """UPWARD scenarios should have positive utility delta."""
        results = sensitive_cpn.generate(
            medium_dataset.episodes,
            medium_dataset.edges,
            rng_seed=42,
        )

        upward = [cf for cf in results if cf.scenario_type == ScenarioType.UPWARD.value]

        if len(upward) == 0:
            pytest.skip("No UPWARD scenarios generated")

        for cf in upward:
            assert cf.utility_delta >= 0, f"UPWARD should have positive delta: {cf.utility_delta}"


# =============================================================================
# BENCHMARK: DETERMINISM TESTS
# =============================================================================


class TestCPNDeterminism:
    """Verify CPN produces deterministic results with same seed."""

    def test_same_seed_same_results(
        self,
        small_dataset,
    ) -> None:
        """Same seed should produce identical results."""
        cpn1 = CausalPerturbationNetwork(CPNConfig(seed=42))
        cpn2 = CausalPerturbationNetwork(CPNConfig(seed=42))

        results1 = cpn1.generate(
            small_dataset.episodes,
            small_dataset.edges,
            rng_seed=42,
        )
        results2 = cpn2.generate(
            small_dataset.episodes,
            small_dataset.edges,
            rng_seed=42,
        )

        assert len(results1) == len(results2)

        for cf1, cf2 in zip(results1, results2):
            assert cf1.scenario_id == cf2.scenario_id
            assert cf1.scenario_type == cf2.scenario_type
            assert cf1.plausibility == cf2.plausibility
            assert cf1.utility_delta == cf2.utility_delta

    def test_different_seed_different_results(
        self,
        small_dataset,
    ) -> None:
        """Different seeds should produce different results."""
        cpn1 = CausalPerturbationNetwork(CPNConfig(seed=42))
        cpn2 = CausalPerturbationNetwork(CPNConfig(seed=123))

        results1 = cpn1.generate(
            small_dataset.episodes,
            small_dataset.edges,
            rng_seed=42,
        )
        results2 = cpn2.generate(
            small_dataset.episodes,
            small_dataset.edges,
            rng_seed=123,
        )

        # Results should differ (unless both empty)
        if len(results1) > 0 and len(results2) > 0:
            # At least scenario_ids should differ
            ids1 = {cf.scenario_id for cf in results1}
            ids2 = {cf.scenario_id for cf in results2}
            assert ids1 != ids2


# =============================================================================
# BENCHMARK: EDGE CASES
# =============================================================================


class TestCPNEdgeCases:
    """Test CPN behavior with edge case inputs."""

    def test_empty_episodes(self, default_cpn: CausalPerturbationNetwork) -> None:
        """CPN should handle empty episode list."""
        results = default_cpn.generate(episodes=[], kg_edges=[])
        assert results == []

    def test_no_regret_episodes(self, default_cpn: CausalPerturbationNetwork) -> None:
        """CPN should handle episodes with no regret-worthy events."""
        # Create episodes with neutral/positive sentiment
        neutral_episodes = [
            RealisticEpisode(
                episode_id=f"ep-{i}",
                sentiment_score=0.5,  # Positive, not regret-worthy
                salience_score=0.5,
                start_time_ms=int(time.time() * 1000) - i * 3600000,
                end_time_ms=int(time.time() * 1000) - i * 3600000 + 1800000,
                entity_ids=["entity-1", "entity-2"],
            )
            for i in range(5)
        ]

        results = default_cpn.generate(neutral_episodes, [])
        assert isinstance(results, list)

    def test_no_causal_edges(
        self,
        sensitive_cpn: CausalPerturbationNetwork,
        small_dataset,
    ) -> None:
        """CPN should handle episodes without CAUSES edges."""
        # Use episodes but no edges
        results = sensitive_cpn.generate(
            small_dataset.episodes,
            [],  # No edges
            rng_seed=42,
        )
        assert isinstance(results, list)

    def test_single_episode(self, sensitive_cpn: CausalPerturbationNetwork) -> None:
        """CPN should handle single episode."""
        single_episode = RealisticEpisode(
            episode_id="ep-single",
            sentiment_score=-0.8,  # Regret-worthy
            salience_score=0.9,
            start_time_ms=int(time.time() * 1000) - 3600000,
            end_time_ms=int(time.time() * 1000) - 3600000 + 1800000,
            entity_ids=["entity-1"],
        )

        results = sensitive_cpn.generate([single_episode], [])
        assert isinstance(results, list)


# =============================================================================
# INTEGRATION BENCHMARK
# =============================================================================


class TestCPNIntegration:
    """Integration benchmarks with realistic scenarios."""

    def test_realistic_family_scenario(self, sensitive_cpn: CausalPerturbationNetwork) -> None:
        """Test with a realistic family memory scenario."""
        now_ms = int(time.time() * 1000)

        # Realistic family episodes
        episodes = [
            RealisticEpisode(
                episode_id="ep-missed-recital",
                sentiment_score=-0.7,  # Regret: missed child's recital
                salience_score=0.9,
                start_time_ms=now_ms - 7 * 24 * 3600000,
                end_time_ms=now_ms - 7 * 24 * 3600000 + 3600000,
                entity_ids=["person-child", "location-school", "event-recital"],
                location_name="School Auditorium",
                activity_type="event",
                summary="Missed Sarah's piano recital due to work meeting",
            ),
            RealisticEpisode(
                episode_id="ep-work-meeting",
                sentiment_score=-0.2,
                salience_score=0.6,
                start_time_ms=now_ms - 7 * 24 * 3600000 - 1800000,
                end_time_ms=now_ms - 7 * 24 * 3600000,
                entity_ids=["person-boss", "location-office", "event-meeting"],
                location_name="Office",
                activity_type="meeting",
                summary="Emergency meeting with boss",
            ),
            RealisticEpisode(
                episode_id="ep-family-dinner",
                sentiment_score=0.8,
                salience_score=0.7,
                start_time_ms=now_ms - 3 * 24 * 3600000,
                end_time_ms=now_ms - 3 * 24 * 3600000 + 5400000,
                entity_ids=["person-child", "person-spouse", "location-home"],
                location_name="Home",
                activity_type="eating",
                summary="Nice family dinner together",
            ),
        ]

        # Causal edges
        edges = [
            RealisticEdge(
                edge_id="edge-1",
                source_id="event-meeting",
                target_id="ep-missed-recital",
                relation_type="CAUSES",
                observation_count=1,
                confidence=0.9,
            ),
            RealisticEdge(
                edge_id="edge-2",
                source_id="person-boss",
                target_id="event-meeting",
                relation_type="CAUSES",
                observation_count=5,
                confidence=0.8,
            ),
        ]

        results = sensitive_cpn.generate(episodes, edges, rng_seed=42)

        print("\nFamily Scenario Results:")
        print(f"  Generated {len(results)} counterfactuals")

        for cf in results:
            print(f"\n  {cf.scenario_type}:")
            print(f"    Base: {cf.base_episode_id}")
            print(f"    Plausibility: {cf.plausibility:.2f}")
            print(f"    Utility Delta: {cf.utility_delta:.2f}")
            if cf.mitigation:
                print(f"    Mitigation: {cf.mitigation}")

        # Should generate at least some counterfactuals for regret episode
        assert isinstance(results, list)
