"""Tests for Feedback Rate Limiter (Issue 6.2.11).

Tests sliding window rate limiting for feedback signals.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from k0.pipelines.p03.feedback.rate_limiter import (
    DEFAULT_MAX_SIGNALS_PER_MINUTE,
    DEFAULT_WINDOW_SIZE_SECONDS,
    FeedbackRateLimiter,
    RateLimitResult,
    create_feedback_rate_limiter,
)


class TestRateLimitResult:
    """Tests for RateLimitResult dataclass."""

    def test_create_not_exceeded(self) -> None:
        """Test creating not-exceeded result."""
        result = RateLimitResult(
            exceeded=False,
            current_count=50,
            limit=100,
            remaining=50,
            reset_at=1234567890,
            window_size=60,
        )
        assert result.exceeded is False
        assert result.remaining == 50

    def test_create_exceeded(self) -> None:
        """Test creating exceeded result."""
        result = RateLimitResult(
            exceeded=True,
            current_count=100,
            limit=100,
            remaining=0,
            reset_at=1234567890,
            window_size=60,
        )
        assert result.exceeded is True
        assert result.remaining == 0


class TestFeedbackRateLimiter:
    """Tests for FeedbackRateLimiter class."""

    @pytest.fixture
    def limiter(self) -> FeedbackRateLimiter:
        """Create limiter with defaults."""
        return FeedbackRateLimiter()

    @pytest.fixture
    def mock_connection(self) -> Mock:
        """Create mock database connection."""
        mock = Mock()
        mock.fetchrow = AsyncMock()
        return mock


class TestLimiterProperties(TestFeedbackRateLimiter):
    """Tests for limiter properties."""

    def test_max_signals_property(self, limiter: FeedbackRateLimiter) -> None:
        """Test max_signals property."""
        assert limiter.max_signals == 100

    def test_window_size_property(self, limiter: FeedbackRateLimiter) -> None:
        """Test window_size property."""
        assert limiter.window_size == 60


class TestCheckRateLimit(TestFeedbackRateLimiter):
    """Tests for check_rate_limit method."""

    @pytest.mark.asyncio
    async def test_under_limit(self, limiter: FeedbackRateLimiter, mock_connection: Mock) -> None:
        """Test check returns not exceeded when under limit."""
        mock_connection.fetchrow.return_value = {"signal_count": 50}

        result = await limiter.check_rate_limit(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert result.exceeded is False
        assert result.current_count == 50
        assert result.remaining == 50

    @pytest.mark.asyncio
    async def test_at_limit(self, limiter: FeedbackRateLimiter, mock_connection: Mock) -> None:
        """Test check returns exceeded when at limit."""
        mock_connection.fetchrow.return_value = {"signal_count": 100}

        result = await limiter.check_rate_limit(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert result.exceeded is True
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_over_limit(self, limiter: FeedbackRateLimiter, mock_connection: Mock) -> None:
        """Test check returns exceeded when over limit."""
        mock_connection.fetchrow.return_value = {"signal_count": 150}

        result = await limiter.check_rate_limit(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert result.exceeded is True
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_with_device_id(
        self, limiter: FeedbackRateLimiter, mock_connection: Mock
    ) -> None:
        """Test check with device_id filter."""
        mock_connection.fetchrow.return_value = {"signal_count": 25}

        result = await limiter.check_rate_limit(
            space_id="space-1",
            user_id="user-1",
            device_id="device-1",
            connection=mock_connection,
        )

        assert result.exceeded is False
        assert result.current_count == 25

    @pytest.mark.asyncio
    async def test_result_includes_reset_time(
        self, limiter: FeedbackRateLimiter, mock_connection: Mock
    ) -> None:
        """Test result includes reset timestamp."""
        mock_connection.fetchrow.return_value = {"signal_count": 10}

        result = await limiter.check_rate_limit(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert result.reset_at > 0
        assert result.window_size == 60


class TestGetRemainingQuota(TestFeedbackRateLimiter):
    """Tests for get_remaining_quota method."""

    @pytest.mark.asyncio
    async def test_returns_remaining_and_reset(
        self, limiter: FeedbackRateLimiter, mock_connection: Mock
    ) -> None:
        """Test returns tuple of remaining and reset_at."""
        mock_connection.fetchrow.return_value = {"signal_count": 30}

        remaining, reset_at = await limiter.get_remaining_quota(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert remaining == 70
        assert reset_at > 0


class TestGetUsageStats(TestFeedbackRateLimiter):
    """Tests for get_usage_stats method."""

    @pytest.mark.asyncio
    async def test_returns_stats_dict(
        self, limiter: FeedbackRateLimiter, mock_connection: Mock
    ) -> None:
        """Test returns stats dictionary."""
        mock_connection.fetchrow.return_value = {"signal_count": 45}

        stats = await limiter.get_usage_stats(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert stats["current"] == 45
        assert stats["limit"] == 100
        assert stats["remaining"] == 55
        assert "reset_at" in stats
        assert stats["window_size"] == 60


class TestIsAllowed(TestFeedbackRateLimiter):
    """Tests for is_allowed method."""

    @pytest.mark.asyncio
    async def test_allowed_when_under_limit(
        self, limiter: FeedbackRateLimiter, mock_connection: Mock
    ) -> None:
        """Test is_allowed returns True under limit."""
        mock_connection.fetchrow.return_value = {"signal_count": 50}

        allowed = await limiter.is_allowed(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert allowed is True

    @pytest.mark.asyncio
    async def test_not_allowed_when_at_limit(
        self, limiter: FeedbackRateLimiter, mock_connection: Mock
    ) -> None:
        """Test is_allowed returns False at limit."""
        mock_connection.fetchrow.return_value = {"signal_count": 100}

        allowed = await limiter.is_allowed(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert allowed is False


class TestCustomConfiguration(TestFeedbackRateLimiter):
    """Tests for custom configuration."""

    @pytest.mark.asyncio
    async def test_custom_max_signals(self, mock_connection: Mock) -> None:
        """Test limiter with custom max signals."""
        limiter = FeedbackRateLimiter(max_signals_per_minute=50)
        mock_connection.fetchrow.return_value = {"signal_count": 50}

        result = await limiter.check_rate_limit(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert result.exceeded is True
        assert result.limit == 50

    @pytest.mark.asyncio
    async def test_custom_window_size(self, mock_connection: Mock) -> None:
        """Test limiter with custom window size."""
        limiter = FeedbackRateLimiter(window_size_seconds=120)
        mock_connection.fetchrow.return_value = {"signal_count": 10}

        result = await limiter.check_rate_limit(
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert limiter.window_size == 120
        assert result.window_size == 120


class TestDefaults:
    """Tests for default constants."""

    def test_default_max_signals(self) -> None:
        """Test default max signals per minute."""
        assert DEFAULT_MAX_SIGNALS_PER_MINUTE == 100

    def test_default_window_size(self) -> None:
        """Test default window size."""
        assert DEFAULT_WINDOW_SIZE_SECONDS == 60


class TestCreateFeedbackRateLimiter:
    """Tests for create_feedback_rate_limiter factory."""

    def test_creates_limiter(self) -> None:
        """Test factory creates limiter."""
        limiter = create_feedback_rate_limiter()
        assert isinstance(limiter, FeedbackRateLimiter)

    def test_custom_max_signals(self) -> None:
        """Test factory accepts custom max signals."""
        limiter = create_feedback_rate_limiter(max_signals_per_minute=200)
        assert limiter.max_signals == 200

    def test_custom_window_size(self) -> None:
        """Test factory accepts custom window size."""
        limiter = create_feedback_rate_limiter(window_size_seconds=30)
        assert limiter.window_size == 30

    def test_accepts_metrics(self) -> None:
        """Test factory accepts metrics."""
        mock_metrics = Mock()
        limiter = create_feedback_rate_limiter(metrics=mock_metrics)
        assert limiter._metrics is mock_metrics
