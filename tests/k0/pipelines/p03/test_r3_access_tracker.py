"""
Tests for AccessTracker and BayesianLambdaEstimator.

Issue: 4.3.5
Spec Reference: M4_EXECUTION.md, Dossier 4.4.1
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.access_tracker import (
    DEFAULT_MAX_INTERVALS_STORED,
    DEFAULT_MIN_ACCESS_COUNT,
    DEFAULT_MIN_SPREAD_DAYS,
    LAMBDA_MAX,
    LAMBDA_MIN,
    MS_PER_DAY,
    AccessStats,
    AccessTracker,
    AccessTrackerConfig,
    BayesianLambdaEstimator,
    InMemoryAccessStore,
    clamp_lambda,
    compute_lambda_mle,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tracker() -> AccessTracker:
    """Default tracker fixture."""
    return AccessTracker()


@pytest.fixture
def estimator() -> BayesianLambdaEstimator:
    """Default estimator fixture."""
    return BayesianLambdaEstimator()


@pytest.fixture
def store() -> InMemoryAccessStore:
    """In-memory store fixture."""
    return InMemoryAccessStore()


# =============================================================================
# 4.3.5.T1: First Access Tests
# =============================================================================


class TestFirstAccess:
    """Test first access behavior."""

    @pytest.mark.asyncio
    async def test_first_access_sets_timestamps(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """first_access_at = last_access_at on first call."""
        now = 1700000000000

        stats = await tracker.record_access(
            entity_id="mem_123",
            entity_table="st_epi",
            accessed_at_ms=now,
            store=store,
        )

        assert stats.first_access_at == now
        assert stats.last_access_at == now
        assert stats.access_count == 1
        assert stats.access_intervals_ms == []
        assert stats.spread_days == 0.0
        assert stats.eligible_for_learning is False

    @pytest.mark.asyncio
    async def test_first_access_persists(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """First access is persisted to store."""
        now = 1700000000000

        await tracker.record_access(
            entity_id="mem_123",
            entity_table="st_epi",
            accessed_at_ms=now,
            store=store,
        )

        # Retrieve from store
        stats = await store.get_access_stats("mem_123", "st_epi")
        assert stats is not None
        assert stats.access_count == 1


# =============================================================================
# 4.3.5.T2: Interval Computation Tests
# =============================================================================


class TestIntervalComputation:
    """Test inter-access interval computation."""

    @pytest.mark.asyncio
    async def test_interval_computed_on_subsequent_access(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """Correct ms interval stored on second access."""
        first = 1700000000000
        second = first + (2 * MS_PER_DAY)  # 2 days later

        # First access
        await tracker.record_access(
            entity_id="mem_123",
            entity_table="st_epi",
            accessed_at_ms=first,
            store=store,
        )

        # Second access
        stats = await tracker.record_access(
            entity_id="mem_123",
            entity_table="st_epi",
            accessed_at_ms=second,
            store=store,
        )

        assert stats.access_count == 2
        assert len(stats.access_intervals_ms) == 1
        assert stats.access_intervals_ms[0] == 2 * MS_PER_DAY

    @pytest.mark.asyncio
    async def test_multiple_intervals_stored(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """Multiple intervals stored correctly."""
        base = 1700000000000

        # 5 accesses over several days
        for i in range(5):
            await tracker.record_access(
                entity_id="mem_123",
                entity_table="st_epi",
                accessed_at_ms=base + (i * MS_PER_DAY),
                store=store,
            )

        stats = await store.get_access_stats("mem_123", "st_epi")
        assert stats is not None
        assert stats.access_count == 5
        assert len(stats.access_intervals_ms) == 4  # 5 accesses = 4 intervals
        assert all(i == MS_PER_DAY for i in stats.access_intervals_ms)

    @pytest.mark.asyncio
    async def test_intervals_capped_at_10(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """Old intervals dropped when exceeding max (10)."""
        base = 1700000000000

        # 15 accesses (14 intervals, should keep only last 10)
        for i in range(15):
            await tracker.record_access(
                entity_id="mem_123",
                entity_table="st_epi",
                accessed_at_ms=base + (i * MS_PER_DAY),
                store=store,
            )

        stats = await store.get_access_stats("mem_123", "st_epi")
        assert stats is not None
        assert stats.access_count == 15
        assert len(stats.access_intervals_ms) == DEFAULT_MAX_INTERVALS_STORED  # 10

    @pytest.mark.asyncio
    async def test_spread_days_calculated(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """spread_days correctly calculated."""
        first = 1700000000000
        last = first + (10 * MS_PER_DAY)  # 10 days later

        await tracker.record_access("mem_123", "st_epi", first, store)
        stats = await tracker.record_access("mem_123", "st_epi", last, store)

        assert abs(stats.spread_days - 10.0) < 0.001


# =============================================================================
# 4.3.5.T3: Eligibility Tests
# =============================================================================


class TestEligibility:
    """Test learning eligibility criteria."""

    @pytest.mark.asyncio
    async def test_eligibility_requires_5_accesses(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """4 accesses returns eligible=False."""
        base = 1700000000000

        # 4 accesses spread over 10 days
        for i in range(4):
            stats = await tracker.record_access(
                entity_id="mem_123",
                entity_table="st_epi",
                accessed_at_ms=base + (i * 3 * MS_PER_DAY),  # 3 days apart
                store=store,
            )

        # 4 accesses, 9 days spread → not eligible (needs 5 accesses)
        assert stats.access_count == 4
        assert stats.spread_days >= 7
        assert stats.eligible_for_learning is False

    @pytest.mark.asyncio
    async def test_eligibility_requires_7_day_spread(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """5 accesses in 1 day returns eligible=False."""
        base = 1700000000000

        # 5 accesses in 1 day (1 hour apart)
        for i in range(5):
            stats = await tracker.record_access(
                entity_id="mem_123",
                entity_table="st_epi",
                accessed_at_ms=base + (i * 3600000),  # 1 hour apart
                store=store,
            )

        assert stats.access_count == 5
        assert stats.spread_days < 7  # Less than 1 day
        assert stats.eligible_for_learning is False

    @pytest.mark.asyncio
    async def test_eligibility_met(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """5 accesses over 10 days → eligible=True."""
        base = 1700000000000

        # 5 accesses, 2.5 days apart = 10 days spread
        for i in range(5):
            stats = await tracker.record_access(
                entity_id="mem_123",
                entity_table="st_epi",
                accessed_at_ms=base + int(i * 2.5 * MS_PER_DAY),
                store=store,
            )

        assert stats.access_count == 5
        assert stats.spread_days >= 7
        assert stats.eligible_for_learning is True

    def test_constants_match_spec(self) -> None:
        """Verify constants match spec values."""
        assert DEFAULT_MIN_ACCESS_COUNT == 5
        assert DEFAULT_MIN_SPREAD_DAYS == 7
        assert DEFAULT_MAX_INTERVALS_STORED == 10


# =============================================================================
# 4.3.5.T4: Lambda MLE Formula Tests
# =============================================================================


class TestLambdaMLE:
    """Test λ estimation using MLE formula."""

    def test_lambda_mle_formula(self, estimator: BayesianLambdaEstimator) -> None:
        """Verify λ = n / Σ(intervals)."""
        # 4 intervals of 5 days each = 20 total days
        # λ = 4 / 20 = 0.2 → clamped to 0.1
        intervals = [5.0, 5.0, 5.0, 5.0]

        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        # MLE would be 4/20 = 0.2, but clamped to max 0.1
        assert estimate.lambda_value == LAMBDA_MAX

    def test_lambda_mle_unclamped(self, estimator: BayesianLambdaEstimator) -> None:
        """λ in valid range not clamped."""
        # 4 intervals with total 80 days → λ = 4/80 = 0.05
        intervals = [20.0, 20.0, 20.0, 20.0]

        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        assert abs(estimate.lambda_value - 0.05) < 0.0001

    def test_lambda_requires_4_intervals(self, estimator: BayesianLambdaEstimator) -> None:
        """λ estimation requires at least 4 intervals."""
        # Only 3 intervals
        intervals = [5.0, 5.0, 5.0]

        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is None

    def test_compute_lambda_mle_utility(self) -> None:
        """Test utility function."""
        intervals = [2.0, 2.0, 2.0, 2.0]  # Total 8, n=4 → λ=0.5
        result = compute_lambda_mle(intervals)
        assert result is not None
        assert abs(result - 0.5) < 0.0001

    def test_compute_lambda_mle_insufficient(self) -> None:
        """Utility returns None for insufficient data."""
        assert compute_lambda_mle([1.0, 2.0, 3.0]) is None
        assert compute_lambda_mle([]) is None


# =============================================================================
# 4.3.5.T5: Lambda Clamping Tests
# =============================================================================


class TestLambdaClamping:
    """Test λ clamping to valid range."""

    def test_lambda_clamped_to_max(self, estimator: BayesianLambdaEstimator) -> None:
        """λ > 0.1 clamped to 0.1."""
        # Very short intervals → high λ
        intervals = [0.5, 0.5, 0.5, 0.5]  # Total 2, n=4 → λ=2.0

        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        assert estimate.lambda_value == LAMBDA_MAX  # 0.1

    def test_lambda_clamped_to_min(self, estimator: BayesianLambdaEstimator) -> None:
        """λ < 0.0001 clamped to 0.0001."""
        # Very long intervals → low λ
        intervals = [1000.0, 1000.0, 1000.0, 1000.0]  # Total 4000, n=4 → λ=0.001

        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        # 0.001 > 0.0001, so not clamped to min
        assert estimate.lambda_value == 0.001

    def test_clamp_lambda_utility(self) -> None:
        """Test clamp_lambda utility function."""
        assert clamp_lambda(0.05) == 0.05  # In range
        assert clamp_lambda(0.2) == LAMBDA_MAX  # Too high
        assert clamp_lambda(0.00001) == LAMBDA_MIN  # Too low
        assert clamp_lambda(0.0001) == LAMBDA_MIN  # At min

    def test_lambda_bounds_constants(self) -> None:
        """Verify bound constants from spec."""
        assert LAMBDA_MIN == 0.0001
        assert LAMBDA_MAX == 0.1


# =============================================================================
# 4.3.5.T6: Confidence Score Tests
# =============================================================================


class TestConfidenceScore:
    """Test confidence score calculation."""

    def test_confidence_4_samples(self, estimator: BayesianLambdaEstimator) -> None:
        """4 samples → confidence = 0.50."""
        intervals = [5.0, 5.0, 5.0, 5.0]
        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        assert estimate.confidence == 0.50

    def test_confidence_6_samples(self, estimator: BayesianLambdaEstimator) -> None:
        """6 samples → confidence = 0.65."""
        intervals = [5.0] * 6
        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        assert abs(estimate.confidence - 0.65) < 0.01

    def test_confidence_10_samples(self, estimator: BayesianLambdaEstimator) -> None:
        """10 samples → confidence = 0.85."""
        intervals = [5.0] * 10
        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        assert abs(estimate.confidence - 0.85) < 0.01

    def test_confidence_15_plus_samples(self, estimator: BayesianLambdaEstimator) -> None:
        """15+ samples → confidence = 0.95."""
        intervals = [5.0] * 20
        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        assert estimate.confidence == 0.95


# =============================================================================
# 4.3.5.T7: Lambda Persistence Tests
# =============================================================================


class TestLambdaPersistence:
    """Test λ persistence to storage."""

    @pytest.mark.asyncio
    async def test_lambda_persisted(
        self, estimator: BayesianLambdaEstimator, store: InMemoryAccessStore
    ) -> None:
        """λ persisted to store."""
        intervals = [5.0, 5.0, 5.0, 5.0]
        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None

        await estimator.persist_lambda(estimate, "space_1", store)

        # Verify persisted
        stored = store.get_lambda("mem_123", "space_1")
        assert stored is not None
        assert stored.lambda_value == estimate.lambda_value
        assert stored.confidence == estimate.confidence


# =============================================================================
# 4.3.5.T8: Half-Life Calculation Tests
# =============================================================================


class TestHalfLifeCalculation:
    """Test half-life calculation in LambdaEstimate."""

    def test_half_life_calculated(self, estimator: BayesianLambdaEstimator) -> None:
        """Half-life correctly calculated from λ."""
        intervals = [20.0, 20.0, 20.0, 20.0]  # λ = 0.05
        estimate = estimator.estimate_lambda("mem_123", "st_epi", intervals)

        assert estimate is not None
        # half_life = ln(2) / λ ≈ 0.693 / 0.05 ≈ 13.86 days
        expected_half_life = 0.693 / 0.05
        assert abs(estimate.half_life_days - expected_half_life) < 0.1

    def test_access_stats_intervals_days(self) -> None:
        """AccessStats.get_intervals_days() converts correctly."""
        stats = AccessStats(
            entity_id="test",
            entity_table="st_epi",
            access_intervals_ms=[MS_PER_DAY, 2 * MS_PER_DAY, 3 * MS_PER_DAY],
        )

        intervals_days = stats.get_intervals_days()

        assert len(intervals_days) == 3
        assert intervals_days[0] == 1.0
        assert intervals_days[1] == 2.0
        assert intervals_days[2] == 3.0


# =============================================================================
# 4.3.5.T9: Configuration Tests
# =============================================================================


class TestAccessTrackerConfig:
    """Test AccessTrackerConfig validation."""

    def test_default_config_valid(self) -> None:
        """Default config is valid."""
        config = AccessTrackerConfig()
        config.validate()  # Should not raise

    def test_min_access_count_too_low(self) -> None:
        """min_access_count < 2 raises ValueError."""
        config = AccessTrackerConfig(min_access_count=1)
        with pytest.raises(ValueError, match="min_access_count"):
            config.validate()

    def test_min_spread_days_zero(self) -> None:
        """min_spread_days <= 0 raises ValueError."""
        config = AccessTrackerConfig(min_spread_days=0)
        with pytest.raises(ValueError, match="min_spread_days"):
            config.validate()

    def test_lambda_min_zero(self) -> None:
        """lambda_min <= 0 raises ValueError."""
        config = AccessTrackerConfig(lambda_min=0)
        with pytest.raises(ValueError, match="lambda_min"):
            config.validate()

    def test_lambda_max_less_than_min(self) -> None:
        """lambda_max <= lambda_min raises ValueError."""
        config = AccessTrackerConfig(lambda_min=0.1, lambda_max=0.05)
        with pytest.raises(ValueError, match="lambda_max"):
            config.validate()


# =============================================================================
# 4.3.5.T10: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_zero_interval_ignored(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """Zero interval (same timestamp) handled gracefully."""
        now = 1700000000000

        # Two accesses at same time
        await tracker.record_access("mem_123", "st_epi", now, store)
        stats = await tracker.record_access("mem_123", "st_epi", now, store)

        # Should not add zero interval
        assert stats.access_count == 2
        assert len(stats.access_intervals_ms) == 0

    @pytest.mark.asyncio
    async def test_negative_interval_ignored(
        self, tracker: AccessTracker, store: InMemoryAccessStore
    ) -> None:
        """Negative interval (clock skew) not stored."""
        first = 1700000000000
        second = first - 1000  # Earlier timestamp (clock skew)

        await tracker.record_access("mem_123", "st_epi", first, store)
        stats = await tracker.record_access("mem_123", "st_epi", second, store)

        # Should not add negative interval
        assert stats.access_count == 2
        assert len(stats.access_intervals_ms) == 0

    def test_empty_intervals_returns_none(self, estimator: BayesianLambdaEstimator) -> None:
        """Empty intervals returns None."""
        estimate = estimator.estimate_lambda("mem_123", "st_epi", [])
        assert estimate is None

    def test_all_zero_intervals_returns_none(self, estimator: BayesianLambdaEstimator) -> None:
        """All zero intervals returns None."""
        estimate = estimator.estimate_lambda("mem_123", "st_epi", [0.0, 0.0, 0.0, 0.0])
        assert estimate is None
