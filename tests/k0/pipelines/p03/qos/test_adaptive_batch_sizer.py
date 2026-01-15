"""Tests for P03 Adaptive Batch Sizer.

Issue 6.4.3: Adaptive batch sizing for P03 operations.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.qos.adaptive_batch_sizer import (
    BATCH_SIZE_PROFILES,
    DEFAULT_MAX_BATCH_SIZE,
    DEFAULT_MEMORY_BUDGET_MB,
    DEFAULT_MIN_BATCH_SIZE,
    DEFAULT_TIME_BUDGET_SECONDS,
    BatchSizeCategory,
    BatchSizeResult,
    P03AdaptiveBatchSizer,
)


class TestBatchSizeProfiles:
    """Test batch size profile definitions."""

    def test_profiles_defined(self) -> None:
        """All three profiles defined."""
        assert BatchSizeCategory.SMALL in BATCH_SIZE_PROFILES
        assert BatchSizeCategory.MEDIUM in BATCH_SIZE_PROFILES
        assert BatchSizeCategory.LARGE in BATCH_SIZE_PROFILES

    def test_small_profile(self) -> None:
        """Small profile matches dossier."""
        profile = BATCH_SIZE_PROFILES[BatchSizeCategory.SMALL]
        assert profile.size == 100
        assert profile.latency_seconds == 5.0
        assert profile.memory_mb == 50
        assert profile.token_cost == 10

    def test_medium_profile(self) -> None:
        """Medium profile matches dossier."""
        profile = BATCH_SIZE_PROFILES[BatchSizeCategory.MEDIUM]
        assert profile.size == 1000
        assert profile.latency_seconds == 30.0
        assert profile.memory_mb == 200
        assert profile.token_cost == 100

    def test_large_profile(self) -> None:
        """Large profile matches dossier."""
        profile = BATCH_SIZE_PROFILES[BatchSizeCategory.LARGE]
        assert profile.size == 10000
        assert profile.latency_seconds == 300.0
        assert profile.memory_mb == 1024
        assert profile.token_cost == 1000


class TestP03AdaptiveBatchSizer:
    """Test adaptive batch sizer logic."""

    @pytest.fixture
    def batch_sizer(self) -> P03AdaptiveBatchSizer:
        """Create batch sizer without scheduler."""
        return P03AdaptiveBatchSizer()

    @pytest.fixture
    def mock_scheduler_integration(self) -> MagicMock:
        """Create mock scheduler integration."""
        mock = MagicMock()
        mock.get_contention_factor.return_value = 1.0
        return mock

    def test_default_bounds(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Default bounds match constants."""
        assert batch_sizer.min_batch_size == DEFAULT_MIN_BATCH_SIZE
        assert batch_sizer.max_batch_size == DEFAULT_MAX_BATCH_SIZE

    def test_custom_bounds(self) -> None:
        """Custom bounds accepted."""
        sizer = P03AdaptiveBatchSizer(min_batch_size=50, max_batch_size=5000)
        assert sizer.min_batch_size == 50
        assert sizer.max_batch_size == 5000

    def test_compute_default_no_constraints(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Default batch size with no constraints."""
        result = batch_sizer.compute_optimal_batch_size(
            pending_count=5000,
            memory_budget_mb=DEFAULT_MEMORY_BUDGET_MB,
            time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        )
        assert isinstance(result, BatchSizeResult)
        assert result.size == 1000  # Medium profile baseline
        assert result.contention_factor == 1.0

    def test_compute_capped_by_pending(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Batch size capped by pending count."""
        result = batch_sizer.compute_optimal_batch_size(
            pending_count=50,  # Less than min
            memory_budget_mb=DEFAULT_MEMORY_BUDGET_MB,
            time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        )
        # Should clamp to min_batch_size, not below
        assert result.size == DEFAULT_MIN_BATCH_SIZE

    def test_compute_capped_by_pending_above_min(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Batch size capped by pending count above minimum."""
        result = batch_sizer.compute_optimal_batch_size(
            pending_count=500,
            memory_budget_mb=DEFAULT_MEMORY_BUDGET_MB,
            time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        )
        assert result.size == 500
        assert "Capped to pending" in result.reason

    def test_compute_memory_constrained(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Batch size reduced by memory constraint."""
        result = batch_sizer.compute_optimal_batch_size(
            pending_count=5000,
            memory_budget_mb=100,  # Half of medium (200MB)
            time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        )
        assert result.memory_constrained
        assert result.size < 1000

    def test_compute_time_constrained(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Batch size reduced by time constraint."""
        result = batch_sizer.compute_optimal_batch_size(
            pending_count=5000,
            memory_budget_mb=DEFAULT_MEMORY_BUDGET_MB,
            time_budget_seconds=15.0,  # Half of medium (30s)
        )
        assert result.time_constrained
        assert result.size < 1000

    def test_compute_contention_high(self, mock_scheduler_integration: MagicMock) -> None:
        """High contention reduces batch size."""
        mock_scheduler_integration.get_contention_factor.return_value = 0.5
        sizer = P03AdaptiveBatchSizer(scheduler_integration=mock_scheduler_integration)

        result = sizer.compute_optimal_batch_size(
            pending_count=5000,
            memory_budget_mb=DEFAULT_MEMORY_BUDGET_MB,
            time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        )
        assert result.contention_factor == 0.5
        assert result.size == 500  # 1000 * 0.5

    def test_compute_contention_medium(self, mock_scheduler_integration: MagicMock) -> None:
        """Medium contention reduces batch size."""
        mock_scheduler_integration.get_contention_factor.return_value = 0.75
        sizer = P03AdaptiveBatchSizer(scheduler_integration=mock_scheduler_integration)

        result = sizer.compute_optimal_batch_size(
            pending_count=5000,
            memory_budget_mb=DEFAULT_MEMORY_BUDGET_MB,
            time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        )
        assert result.contention_factor == 0.75
        assert result.size == 750  # 1000 * 0.75

    def test_get_profile_for_size_small(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Get profile for small batch size."""
        profile = batch_sizer.get_profile_for_size(50)
        assert profile.size == 100

    def test_get_profile_for_size_medium(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Get profile for medium batch size."""
        profile = batch_sizer.get_profile_for_size(500)
        assert profile.size == 1000

    def test_get_profile_for_size_large(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Get profile for large batch size."""
        profile = batch_sizer.get_profile_for_size(5000)
        assert profile.size == 10000

    def test_estimate_batch_count(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Batch count estimation."""
        assert batch_sizer.estimate_batch_count(1000, 100) == 10
        assert batch_sizer.estimate_batch_count(1050, 100) == 11  # Rounds up
        assert batch_sizer.estimate_batch_count(100, 100) == 1
        assert batch_sizer.estimate_batch_count(0, 100) == 0

    def test_estimate_batch_count_zero_size(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Zero batch size returns zero."""
        assert batch_sizer.estimate_batch_count(1000, 0) == 0

    def test_result_expected_metrics(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Result includes expected latency and memory."""
        result = batch_sizer.compute_optimal_batch_size(
            pending_count=5000,
            memory_budget_mb=DEFAULT_MEMORY_BUDGET_MB,
            time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        )
        assert result.expected_latency_seconds > 0
        assert result.expected_memory_mb > 0


class TestBatchSizeResult:
    """Test BatchSizeResult dataclass."""

    def test_result_immutable(self) -> None:
        """Result is frozen dataclass."""
        result = BatchSizeResult(
            size=100,
            reason="Test",
            contention_factor=1.0,
            memory_constrained=False,
            time_constrained=False,
            expected_latency_seconds=5.0,
            expected_memory_mb=50,
        )
        with pytest.raises(AttributeError):
            result.size = 200  # type: ignore[misc]


class TestResourceEstimation:
    """Test resource estimation interpolation."""

    @pytest.fixture
    def batch_sizer(self) -> P03AdaptiveBatchSizer:
        """Create batch sizer."""
        return P03AdaptiveBatchSizer()

    def test_estimate_small_boundary(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Estimation at small profile boundary."""
        latency, memory = batch_sizer._estimate_resources(100)
        assert latency == 5.0
        assert memory == 50

    def test_estimate_medium_boundary(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Estimation at medium profile boundary."""
        latency, memory = batch_sizer._estimate_resources(1000)
        assert latency == 30.0
        assert memory == 200

    def test_estimate_large_boundary(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Estimation at large profile boundary."""
        latency, memory = batch_sizer._estimate_resources(10000)
        assert latency == 300.0
        assert memory == 1024

    def test_estimate_interpolated_small_to_medium(
        self, batch_sizer: P03AdaptiveBatchSizer
    ) -> None:
        """Interpolation between small and medium."""
        latency, memory = batch_sizer._estimate_resources(550)  # Midpoint
        assert 5.0 < latency < 30.0
        assert 50 < memory < 200

    def test_estimate_interpolated_medium_to_large(
        self, batch_sizer: P03AdaptiveBatchSizer
    ) -> None:
        """Interpolation between medium and large."""
        latency, memory = batch_sizer._estimate_resources(5500)  # Midpoint
        assert 30.0 < latency < 300.0
        assert 200 < memory < 1024

    def test_estimate_below_small(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Below small uses small profile."""
        latency, memory = batch_sizer._estimate_resources(50)
        assert latency == 5.0
        assert memory == 50

    def test_estimate_above_large(self, batch_sizer: P03AdaptiveBatchSizer) -> None:
        """Above large uses large profile."""
        latency, memory = batch_sizer._estimate_resources(20000)
        assert latency == 300.0
        assert memory == 1024
