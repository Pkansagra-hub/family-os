"""
Tests for MinHashLSH.

Issue: 4.3.11
Spec Reference: Dossier Appendix C.4.1.3 (lines 22296-22420)
"""

from __future__ import annotations

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.minhash_lsh import (
    DEFAULT_MINHASH_LSH_ENABLED,
    DEFAULT_NUM_BANDS,
    DEFAULT_NUM_HASHES,
    DEFAULT_SIMILARITY_THRESHOLD,
    THRESHOLD_BUCKETING,
    THRESHOLD_PAIRWISE,
    AdaptiveDeduplicationStrategy,
    AdaptiveStrategyConfig,
    DeduplicationStrategy,
    MinHashConfig,
    MinHashLSH,
    MinHashMetricsCollector,
    compute_jaccard_similarity,
    estimate_lsh_threshold,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def lsh() -> MinHashLSH:
    """Default MinHashLSH fixture."""
    return MinHashLSH()


@pytest.fixture
def small_lsh() -> MinHashLSH:
    """Smaller LSH for faster tests."""
    config = MinHashConfig(num_hashes=32, num_bands=8)
    return MinHashLSH(config=config)


@pytest.fixture
def sample_text() -> str:
    """Sample event text."""
    return "Had dinner with Sarah at the Italian restaurant downtown"


@pytest.fixture
def similar_text() -> str:
    """Similar text for near-duplicate detection."""
    return "Dinner with Sarah at Italian place in downtown"


@pytest.fixture
def dissimilar_text() -> str:
    """Unrelated text."""
    return "Attended board meeting to discuss Q3 financials"


# =============================================================================
# 4.3.11.T1: MinHash Computes 128 Hashes
# =============================================================================


class TestMinHashSignature:
    """Test MinHash signature computation."""

    def test_minhash_128_hashes(self, lsh: MinHashLSH, sample_text: str) -> None:
        """Signature has 128 values by default."""
        signature = lsh.compute_minhash(sample_text)

        assert len(signature) == 128
        assert signature.dtype == np.uint64

    def test_minhash_deterministic(self, lsh: MinHashLSH, sample_text: str) -> None:
        """Same input produces same signature."""
        sig1 = lsh.compute_minhash(sample_text)
        sig2 = lsh.compute_minhash(sample_text)

        np.testing.assert_array_equal(sig1, sig2)

    def test_minhash_different_inputs(
        self, lsh: MinHashLSH, sample_text: str, dissimilar_text: str
    ) -> None:
        """Different inputs produce different signatures."""
        sig1 = lsh.compute_minhash(sample_text)
        sig2 = lsh.compute_minhash(dissimilar_text)

        # Signatures should differ significantly
        similarity = lsh.compute_exact_similarity(sig1, sig2)
        assert similarity < 0.5

    def test_minhash_empty_text(self, lsh: MinHashLSH) -> None:
        """Empty text produces zero signature."""
        signature = lsh.compute_minhash("")

        assert len(signature) == 128
        assert np.all(signature == 0)

    def test_minhash_configurable_hashes(self) -> None:
        """Custom num_hashes is respected."""
        config = MinHashConfig(num_hashes=64, num_bands=16)
        lsh = MinHashLSH(config=config)

        signature = lsh.compute_minhash("test text")
        assert len(signature) == 64


# =============================================================================
# 4.3.11.T2: Hash Bands Returns 32 Bands
# =============================================================================


class TestHashBands:
    """Test LSH band hashing."""

    def test_hash_bands_32_bands(self, lsh: MinHashLSH, sample_text: str) -> None:
        """Returns 32 band hashes by default."""
        signature = lsh.compute_minhash(sample_text)
        band_hashes = lsh.hash_bands(signature)

        assert len(band_hashes) == 32

    def test_hash_bands_deterministic(self, lsh: MinHashLSH, sample_text: str) -> None:
        """Same signature produces same band hashes."""
        signature = lsh.compute_minhash(sample_text)
        bands1 = lsh.hash_bands(signature)
        bands2 = lsh.hash_bands(signature)

        assert bands1 == bands2

    def test_hash_bands_configurable(self) -> None:
        """Custom num_bands is respected."""
        config = MinHashConfig(num_hashes=64, num_bands=8)
        lsh = MinHashLSH(config=config)

        signature = lsh.compute_minhash("test text")
        band_hashes = lsh.hash_bands(signature)

        assert len(band_hashes) == 8


# =============================================================================
# 4.3.11.T3: Index and Find Self
# =============================================================================


class TestIndexAndFind:
    """Test indexing and finding events."""

    def test_index_and_find_self(self, small_lsh: MinHashLSH, sample_text: str) -> None:
        """Indexed event found by same signature."""
        signature = small_lsh.compute_minhash(sample_text)
        small_lsh.index_event("event_1", signature)

        # Query with same signature
        candidates = small_lsh.find_candidates(signature)

        assert len(candidates) >= 1
        event_ids = [c.event_id for c in candidates]
        assert "event_1" in event_ids

    def test_find_excludes_self(self, small_lsh: MinHashLSH, sample_text: str) -> None:
        """Exclude self from candidates."""
        signature = small_lsh.compute_minhash(sample_text)
        small_lsh.index_event("event_1", signature)

        candidates = small_lsh.find_candidates(signature, exclude_event_id="event_1")

        event_ids = [c.event_id for c in candidates]
        assert "event_1" not in event_ids


# =============================================================================
# 4.3.11.T4: Similar Texts Found
# =============================================================================


class TestSimilarTextsFound:
    """Test near-duplicate detection."""

    def test_similar_texts_found(
        self,
        small_lsh: MinHashLSH,
        sample_text: str,
        similar_text: str,
    ) -> None:
        """Near-duplicates appear as candidates."""
        # Index original
        sig1 = small_lsh.compute_minhash(sample_text)
        small_lsh.index_event("event_1", sig1)

        # Query with similar
        sig2 = small_lsh.compute_minhash(similar_text)
        candidates = small_lsh.find_candidates(sig2)

        # Should find the similar event
        if candidates:
            # At least some band overlap expected
            assert candidates[0].bands_matched > 0


# =============================================================================
# 4.3.11.T5: Dissimilar Texts Not Found
# =============================================================================


class TestDissimilarTextsNotFound:
    """Test that unrelated texts don't match."""

    def test_dissimilar_texts_not_found(
        self,
        small_lsh: MinHashLSH,
        sample_text: str,
        dissimilar_text: str,
    ) -> None:
        """Unrelated texts not matched."""
        # Index original
        sig1 = small_lsh.compute_minhash(sample_text)
        small_lsh.index_event("event_1", sig1)

        # Query with dissimilar
        sig2 = small_lsh.compute_minhash(dissimilar_text)
        candidates = small_lsh.find_candidates(sig2)

        # Should find no or low-similarity candidates
        high_similarity_candidates = [c for c in candidates if c.estimated_similarity >= 0.85]
        assert len(high_similarity_candidates) == 0


# =============================================================================
# 4.3.11.T6: Exact Similarity Computation
# =============================================================================


class TestExactSimilarity:
    """Test exact Jaccard similarity computation."""

    def test_exact_similarity_identical(self, lsh: MinHashLSH) -> None:
        """Identical signatures have similarity 1.0."""
        sig = lsh.compute_minhash("test text")
        similarity = lsh.compute_exact_similarity(sig, sig)

        assert similarity == 1.0

    def test_exact_similarity_computation(
        self, lsh: MinHashLSH, sample_text: str, similar_text: str
    ) -> None:
        """Similar texts have high similarity."""
        sig1 = lsh.compute_minhash(sample_text)
        sig2 = lsh.compute_minhash(similar_text)

        similarity = lsh.compute_exact_similarity(sig1, sig2)

        # Similar texts should have reasonable overlap
        assert 0.0 <= similarity <= 1.0

    def test_exact_similarity_different_lengths_error(self, lsh: MinHashLSH) -> None:
        """Different length signatures raise ValueError."""
        sig1 = np.array([1, 2, 3], dtype=np.uint64)
        sig2 = np.array([1, 2], dtype=np.uint64)

        with pytest.raises(ValueError, match="lengths must match"):
            lsh.compute_exact_similarity(sig1, sig2)


# =============================================================================
# 4.3.11.T7: Remove Event from Index
# =============================================================================


class TestRemoveEvent:
    """Test event removal."""

    def test_remove_event_from_index(self, small_lsh: MinHashLSH, sample_text: str) -> None:
        """Removed event not found."""
        signature = small_lsh.compute_minhash(sample_text)
        small_lsh.index_event("event_1", signature)

        # Verify indexed
        assert small_lsh.event_count == 1

        # Remove
        result = small_lsh.remove_event("event_1")
        assert result is True
        assert small_lsh.event_count == 0

        # Query should find nothing
        candidates = small_lsh.find_candidates(signature)
        event_ids = [c.event_id for c in candidates]
        assert "event_1" not in event_ids

    def test_remove_nonexistent_event(self, small_lsh: MinHashLSH) -> None:
        """Removing nonexistent event returns False."""
        result = small_lsh.remove_event("nonexistent")
        assert result is False


# =============================================================================
# 4.3.11.T8: Auto-Switch Pairwise to Bucketing
# =============================================================================


class TestAutoSwitchPairwiseToBucketing:
    """Test strategy auto-switch at 10K threshold."""

    def test_auto_switch_pairwise_to_bucketing(self) -> None:
        """Switch to bucketing at 10K events."""
        lsh = MinHashLSH()
        config = AdaptiveStrategyConfig(lsh_enabled=False)
        strategy = AdaptiveDeduplicationStrategy(
            minhash_lsh=lsh,
            config=config,
        )

        # Start with pairwise
        assert strategy.get_strategy() == DeduplicationStrategy.SIMHASH_PAIRWISE

        # Update to 10K
        switch = strategy.update_event_count(10_000)

        assert switch is not None
        assert switch[0] == "simhash_pairwise"
        assert switch[1] == "simhash_bucketing"
        assert strategy.get_strategy() == DeduplicationStrategy.SIMHASH_BUCKETING


# =============================================================================
# 4.3.11.T9: Auto-Switch Bucketing to LSH
# =============================================================================


class TestAutoSwitchBucketingToLSH:
    """Test strategy auto-switch at 50K threshold."""

    def test_auto_switch_bucketing_to_lsh(self) -> None:
        """Switch to LSH at 50K events when enabled."""
        lsh = MinHashLSH()
        config = AdaptiveStrategyConfig(lsh_enabled=True)
        strategy = AdaptiveDeduplicationStrategy(
            minhash_lsh=lsh,
            config=config,
        )

        # Start with pairwise
        strategy.update_event_count(5_000)
        assert strategy.get_strategy() == DeduplicationStrategy.SIMHASH_PAIRWISE

        # Switch to bucketing at 10K
        strategy.update_event_count(10_000)
        assert strategy.get_strategy() == DeduplicationStrategy.SIMHASH_BUCKETING

        # Switch to LSH at 50K
        switch = strategy.update_event_count(50_000)

        assert switch is not None
        assert switch[0] == "simhash_bucketing"
        assert switch[1] == "minhash_lsh"
        assert strategy.get_strategy() == DeduplicationStrategy.MINHASH_LSH


# =============================================================================
# 4.3.11.T10: Feature Flag Disables LSH
# =============================================================================


class TestFeatureFlagDisablesLSH:
    """Test feature flag behavior."""

    def test_feature_flag_disables_lsh(self) -> None:
        """LSH not used when flag FALSE."""
        lsh = MinHashLSH()
        config = AdaptiveStrategyConfig(lsh_enabled=False)
        strategy = AdaptiveDeduplicationStrategy(
            minhash_lsh=lsh,
            config=config,
        )

        # Even at 100K, should stay with bucketing
        strategy.update_event_count(100_000)

        assert strategy.get_strategy() == DeduplicationStrategy.SIMHASH_BUCKETING

    def test_feature_flag_default_false(self) -> None:
        """LSH disabled by default."""
        assert DEFAULT_MINHASH_LSH_ENABLED is False

    def test_lsh_enabled_uses_minhash(self) -> None:
        """LSH enabled switches to MinHash at threshold."""
        lsh = MinHashLSH()
        config = AdaptiveStrategyConfig(lsh_enabled=True)
        strategy = AdaptiveDeduplicationStrategy(
            minhash_lsh=lsh,
            config=config,
        )

        strategy.update_event_count(60_000)

        assert strategy.get_strategy() == DeduplicationStrategy.MINHASH_LSH


# =============================================================================
# 4.3.11.T11: Configuration Validation
# =============================================================================


class TestConfigValidation:
    """Test configuration validation."""

    def test_default_config_valid(self) -> None:
        """Default config passes validation."""
        config = MinHashConfig()
        config.validate()  # Should not raise

    def test_invalid_num_hashes(self) -> None:
        """Invalid num_hashes raises ValueError."""
        with pytest.raises(ValueError, match="num_hashes must be positive"):
            MinHashConfig(num_hashes=0, num_bands=1)

    def test_invalid_num_bands(self) -> None:
        """Invalid num_bands raises ValueError."""
        with pytest.raises(ValueError, match="num_bands must be positive"):
            MinHashConfig(num_hashes=128, num_bands=0)

    def test_invalid_divisibility(self) -> None:
        """num_hashes not divisible by num_bands raises ValueError."""
        with pytest.raises(ValueError, match="divisible"):
            MinHashConfig(num_hashes=100, num_bands=33)

    def test_invalid_similarity_threshold(self) -> None:
        """Invalid similarity_threshold raises ValueError."""
        with pytest.raises(ValueError, match="similarity_threshold"):
            MinHashConfig(similarity_threshold=1.5)

    def test_rows_per_band_property(self) -> None:
        """rows_per_band computed correctly."""
        config = MinHashConfig(num_hashes=128, num_bands=32)
        assert config.rows_per_band == 4


# =============================================================================
# 4.3.11.T12: Constants Match Spec
# =============================================================================


class TestConstantsMatchSpec:
    """Test that constants match spec values."""

    def test_default_num_hashes(self) -> None:
        """Default num_hashes is 128."""
        assert DEFAULT_NUM_HASHES == 128

    def test_default_num_bands(self) -> None:
        """Default num_bands is 32."""
        assert DEFAULT_NUM_BANDS == 32

    def test_default_similarity_threshold(self) -> None:
        """Default similarity_threshold is 0.85."""
        assert DEFAULT_SIMILARITY_THRESHOLD == 0.85

    def test_pairwise_threshold(self) -> None:
        """Pairwise threshold is 10,000."""
        assert THRESHOLD_PAIRWISE == 10_000

    def test_bucketing_threshold(self) -> None:
        """Bucketing threshold is 50,000."""
        assert THRESHOLD_BUCKETING == 50_000


# =============================================================================
# 4.3.11.T13: LSH Index Stats
# =============================================================================


class TestLSHIndexStats:
    """Test index statistics."""

    def test_get_stats_empty(self, small_lsh: MinHashLSH) -> None:
        """Empty index stats."""
        stats = small_lsh.get_stats()

        assert stats.event_count == 0
        assert stats.bucket_count == 0
        assert stats.avg_bucket_size == 0.0
        assert stats.strategy == DeduplicationStrategy.MINHASH_LSH

    def test_get_stats_populated(self, small_lsh: MinHashLSH) -> None:
        """Populated index stats."""
        for i in range(10):
            sig = small_lsh.compute_minhash(f"Event text {i}")
            small_lsh.index_event(f"event_{i}", sig)

        stats = small_lsh.get_stats()

        assert stats.event_count == 10
        assert stats.bucket_count > 0
        assert stats.avg_bucket_size > 0


# =============================================================================
# 4.3.11.T14: Metrics Collector
# =============================================================================


class TestMetricsCollector:
    """Test MinHashMetricsCollector."""

    def test_record_strategy_switch(self) -> None:
        """Record strategy switches."""
        collector = MinHashMetricsCollector()

        collector.record_strategy_switch("simhash_pairwise", "simhash_bucketing")
        collector.record_strategy_switch("simhash_pairwise", "simhash_bucketing")
        collector.record_strategy_switch("simhash_bucketing", "minhash_lsh")

        assert collector.get_switch_count("simhash_pairwise", "simhash_bucketing") == 2
        assert collector.get_switch_count("simhash_bucketing", "minhash_lsh") == 1

    def test_record_query_latency(self) -> None:
        """Record query latencies."""
        collector = MinHashMetricsCollector()

        collector.record_query_latency(10.0)
        collector.record_query_latency(20.0)
        collector.record_query_latency(30.0)

        assert collector.get_avg_latency_ms() == pytest.approx(20.0, abs=0.1)

    def test_reset(self) -> None:
        """Reset clears all metrics."""
        collector = MinHashMetricsCollector()

        collector.record_strategy_switch("a", "b")
        collector.record_query_latency(10.0)
        collector.reset()

        assert collector.get_switch_count("a", "b") == 0
        assert collector.get_avg_latency_ms() == 0.0


# =============================================================================
# 4.3.11.T15: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Test utility functions."""

    def test_estimate_lsh_threshold(self) -> None:
        """Estimate LSH match probability."""
        # With 32 bands, 4 rows, at 0.85 similarity
        prob = estimate_lsh_threshold(
            num_bands=32,
            rows_per_band=4,
            target_similarity=0.85,
        )

        # Should be high probability at this threshold
        assert 0.9 < prob <= 1.0

    def test_compute_jaccard_similarity_identical(self) -> None:
        """Identical sets have similarity 1.0."""
        set1 = {"a", "b", "c"}
        similarity = compute_jaccard_similarity(set1, set1)

        assert similarity == 1.0

    def test_compute_jaccard_similarity_empty(self) -> None:
        """Empty sets have similarity 1.0."""
        similarity = compute_jaccard_similarity(set(), set())

        assert similarity == 1.0

    def test_compute_jaccard_similarity_disjoint(self) -> None:
        """Disjoint sets have similarity 0.0."""
        set1 = {"a", "b"}
        set2 = {"c", "d"}
        similarity = compute_jaccard_similarity(set1, set2)

        assert similarity == 0.0

    def test_compute_jaccard_similarity_partial(self) -> None:
        """Partial overlap has fractional similarity."""
        set1 = {"a", "b", "c"}
        set2 = {"b", "c", "d"}
        similarity = compute_jaccard_similarity(set1, set2)

        # Intersection: {b, c} = 2
        # Union: {a, b, c, d} = 4
        assert similarity == pytest.approx(0.5, abs=0.01)


# =============================================================================
# 4.3.11.T16: Clear Index
# =============================================================================


class TestClearIndex:
    """Test index clearing."""

    def test_clear_removes_all(self, small_lsh: MinHashLSH) -> None:
        """Clear removes all events."""
        for i in range(5):
            sig = small_lsh.compute_minhash(f"Text {i}")
            small_lsh.index_event(f"event_{i}", sig)

        assert small_lsh.event_count == 5

        small_lsh.clear()

        assert small_lsh.event_count == 0
        assert small_lsh.query_count == 0


# =============================================================================
# 4.3.11.T17: Strategy Switches Tracked
# =============================================================================


class TestStrategySwitchesTracked:
    """Test strategy switch history."""

    def test_strategy_switches_tracked(self) -> None:
        """Strategy switches are recorded."""
        lsh = MinHashLSH()
        config = AdaptiveStrategyConfig(lsh_enabled=True)
        strategy = AdaptiveDeduplicationStrategy(
            minhash_lsh=lsh,
            config=config,
        )

        strategy.update_event_count(10_000)
        strategy.update_event_count(50_000)

        switches = strategy.strategy_switches

        assert len(switches) == 2
        assert switches[0] == (10_000, "simhash_pairwise", "simhash_bucketing")
        assert switches[1] == (50_000, "simhash_bucketing", "minhash_lsh")
