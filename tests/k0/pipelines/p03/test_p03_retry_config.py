"""Tests for P03 Retry Config (Issue 6.2.4).

Tests phase-aware retry configuration and scheduling.
"""

from __future__ import annotations

import pytest

from k0.pipelines.p03.ops.retry_config import (
    PHASE_RETRY_OVERRIDES,
    P03RetryConfig,
    P03RetryScheduler,
    create_p03_retry_scheduler,
)


class TestP03RetryConfig:
    """Tests for P03RetryConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = P03RetryConfig()
        assert config.default_max_attempts == 3
        assert config.base_delay_ms == 1000
        assert config.max_delay_ms == 60000
        assert config.exponential_base == 2.0
        assert config.jitter_factor == 0.1

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = P03RetryConfig(
            default_max_attempts=10,
            base_delay_ms=500,
            max_delay_ms=120000,
            exponential_base=3.0,
            jitter_factor=0.2,
        )
        assert config.default_max_attempts == 10
        assert config.base_delay_ms == 500
        assert config.max_delay_ms == 120000
        assert config.exponential_base == 3.0
        assert config.jitter_factor == 0.2


class TestPhaseRetryOverrides:
    """Tests for PHASE_RETRY_OVERRIDES mapping."""

    def test_r0_override_exists(self) -> None:
        """Test R0 phase has override."""
        assert "R0" in PHASE_RETRY_OVERRIDES

    def test_r7_override_exists(self) -> None:
        """Test R7 phase has override."""
        assert "R7" in PHASE_RETRY_OVERRIDES

    def test_r8_override_exists(self) -> None:
        """Test R8 phase has override."""
        assert "R8" in PHASE_RETRY_OVERRIDES

    def test_r0_has_max_attempts(self) -> None:
        """Test R0 has max_attempts configured."""
        assert "max_attempts" in PHASE_RETRY_OVERRIDES["R0"]
        assert PHASE_RETRY_OVERRIDES["R0"]["max_attempts"] == 5

    def test_r7_has_max_attempts(self) -> None:
        """Test R7 has max_attempts configured."""
        assert "max_attempts" in PHASE_RETRY_OVERRIDES["R7"]
        assert PHASE_RETRY_OVERRIDES["R7"]["max_attempts"] == 10

    def test_r8_has_max_attempts(self) -> None:
        """Test R8 has max_attempts configured."""
        assert "max_attempts" in PHASE_RETRY_OVERRIDES["R8"]
        assert PHASE_RETRY_OVERRIDES["R8"]["max_attempts"] == 3


class TestP03RetryConfigMethods:
    """Tests for P03RetryConfig methods."""

    @pytest.fixture
    def config(self) -> P03RetryConfig:
        """Create default config."""
        return P03RetryConfig()

    @pytest.fixture
    def custom_config(self) -> P03RetryConfig:
        """Create custom config with no jitter for deterministic tests."""
        return P03RetryConfig(
            default_max_attempts=3,
            base_delay_ms=500,
            max_delay_ms=5000,
            exponential_base=2.0,
            jitter_factor=0.0,
        )

    def test_get_max_attempts_default(self, config: P03RetryConfig) -> None:
        """Test default max_attempts for non-overridden phases."""
        assert config.get_max_attempts("R1") == 3
        assert config.get_max_attempts("R2") == 3
        assert config.get_max_attempts("R3") == 3

    def test_get_max_attempts_r0(self, config: P03RetryConfig) -> None:
        """Test R0 phase uses override."""
        assert config.get_max_attempts("R0") == 5

    def test_get_max_attempts_r7(self, config: P03RetryConfig) -> None:
        """Test R7 phase uses override."""
        assert config.get_max_attempts("R7") == 10

    def test_get_max_attempts_r8(self, config: P03RetryConfig) -> None:
        """Test R8 phase uses override."""
        assert config.get_max_attempts("R8") == 3

    def test_get_backoff_delay_first_attempt(self, custom_config: P03RetryConfig) -> None:
        """Test first attempt uses base delay."""
        delay = custom_config.get_backoff_delay_ms(attempt=1)
        assert delay == 500

    def test_get_backoff_delay_increases(self, custom_config: P03RetryConfig) -> None:
        """Test backoff increases with attempts."""
        delay1 = custom_config.get_backoff_delay_ms(attempt=1)
        delay2 = custom_config.get_backoff_delay_ms(attempt=2)
        delay3 = custom_config.get_backoff_delay_ms(attempt=3)
        assert delay1 < delay2 < delay3

    def test_get_backoff_delay_capped(self, custom_config: P03RetryConfig) -> None:
        """Test delay capped at max_delay_ms."""
        delay = custom_config.get_backoff_delay_ms(attempt=10)
        assert delay <= 5000

    def test_add_jitter_no_jitter_when_zero(self, custom_config: P03RetryConfig) -> None:
        """Test no jitter when jitter_factor is 0."""
        delay = custom_config.add_jitter(1000)
        assert delay == 1000


class TestP03RetryScheduler:
    """Tests for P03RetryScheduler class."""

    @pytest.fixture
    def scheduler(self) -> P03RetryScheduler:
        """Create scheduler with default config."""
        return P03RetryScheduler()

    @pytest.fixture
    def custom_scheduler(self) -> P03RetryScheduler:
        """Create scheduler with custom config."""
        config = P03RetryConfig(
            default_max_attempts=3,
            base_delay_ms=500,
            max_delay_ms=5000,
            exponential_base=2.0,
            jitter_factor=0.0,
        )
        return P03RetryScheduler(config=config)

    def test_decide_returns_retry(self, scheduler: P03RetryScheduler) -> None:
        """Test decide returns retry when attempts available."""
        error = ConnectionError("test")
        result = scheduler.decide(phase="R0", attempt_count=1, error=error)

        assert result.action == "retry"

    def test_decide_returns_quarantine_when_exhausted(self, scheduler: P03RetryScheduler) -> None:
        """Test decide returns quarantine when max attempts exceeded."""
        error = TimeoutError("test")
        # R8 has max 3 attempts
        result = scheduler.decide(phase="R8", attempt_count=3, error=error)

        assert result.action == "quarantine"

    def test_decide_includes_next_attempt_ts(self, scheduler: P03RetryScheduler) -> None:
        """Test retry decision includes next_attempt_ts."""
        error = ConnectionError("test")
        result = scheduler.decide(phase="R1", attempt_count=1, error=error)

        assert result.next_attempt_ts is not None

    def test_decide_retries_incremented(self, scheduler: P03RetryScheduler) -> None:
        """Test retries field is returned correctly."""
        error = ConnectionError("test")
        result = scheduler.decide(phase="R0", attempt_count=2, error=error)

        assert result.retries == 2

    def test_r7_allows_more_retries(self, scheduler: P03RetryScheduler) -> None:
        """Test R7 allows more retries than default."""
        error = ConnectionError("test")

        # Attempt 6 should still allow retry for R7 (max 10)
        result = scheduler.decide(phase="R7", attempt_count=6, error=error)
        assert result.action == "retry"


class TestCreateP03RetryScheduler:
    """Tests for create_p03_retry_scheduler factory."""

    def test_creates_scheduler(self) -> None:
        """Test factory creates scheduler."""
        scheduler = create_p03_retry_scheduler()
        assert isinstance(scheduler, P03RetryScheduler)

    def test_uses_default_config(self) -> None:
        """Test factory uses default config values."""
        scheduler = create_p03_retry_scheduler()
        assert scheduler.config.default_max_attempts == 3
        assert scheduler.config.base_delay_ms == 1000

    def test_accepts_custom_config(self) -> None:
        """Test factory accepts custom config."""
        config = P03RetryConfig(default_max_attempts=10)
        scheduler = create_p03_retry_scheduler(config=config)
        assert scheduler.config.default_max_attempts == 10
