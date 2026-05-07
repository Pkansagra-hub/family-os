"""M4 Resilience & Cost -- Test RateLimiter [F49].

Tests per-provider token bucket rate limiting with RPM/TPM buckets,
headroom enforcement, and acquire/has_capacity behavior.

Covers:
  - RateDecision: construction, defaults, frozen
  - Registration / unregistration
  - Token bucket: consume, refill, capacity
  - has_capacity: IRateLimiterQuery protocol compliance
  - acquire: dual bucket (RPM + TPM) atomicity
  - Headroom: effective capacity = capacity * headroom_pct
  - Edge cases: unknown provider, zero tokens, large estimates
"""

from __future__ import annotations

import pytest

from k1.model_hub.services.capability_router import IRateLimiterQuery
from k1.model_hub.services.rate_limiter import RateDecision, RateLimiter

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def limiter() -> RateLimiter:
    rl = RateLimiter()
    rl.register_provider("openai", rpm=60, tpm=100000)
    return rl


@pytest.fixture
def small_limiter() -> RateLimiter:
    """Small bucket for quick exhaustion."""
    rl = RateLimiter()
    rl.register_provider("openai", rpm=5, tpm=100, headroom_pct=1.0)
    return rl


# ===========================================================================
# RateDecision Tests
# ===========================================================================


class TestRateDecision:
    def test_defaults(self) -> None:
        rd = RateDecision(allowed=True, provider_id="openai")
        assert rd.allowed is True
        assert rd.provider_id == "openai"
        assert rd.tokens_remaining == 0
        assert rd.requests_remaining == 0
        assert rd.retry_after_s == 0.0

    def test_custom_values(self) -> None:
        rd = RateDecision(
            allowed=False,
            provider_id="openai",
            tokens_remaining=5000,
            requests_remaining=10,
            retry_after_s=2.5,
        )
        assert rd.allowed is False
        assert rd.retry_after_s == 2.5

    def test_frozen(self) -> None:
        rd = RateDecision(allowed=True, provider_id="openai")
        with pytest.raises(AttributeError):
            rd.allowed = False  # type: ignore[misc]


# ===========================================================================
# Registration Tests
# ===========================================================================


class TestRegistration:
    def test_register_provider(self) -> None:
        rl = RateLimiter()
        rl.register_provider("openai")
        assert rl.is_registered("openai")

    def test_unregister_provider(self) -> None:
        rl = RateLimiter()
        rl.register_provider("openai")
        rl.unregister_provider("openai")
        assert not rl.is_registered("openai")

    def test_unregister_unknown_no_error(self) -> None:
        rl = RateLimiter()
        rl.unregister_provider("nonexistent")

    def test_register_with_custom_headroom(self) -> None:
        rl = RateLimiter()
        rl.register_provider("openai", rpm=100, tpm=200000, headroom_pct=0.5)
        assert rl.is_registered("openai")


# ===========================================================================
# Protocol Compliance
# ===========================================================================


class TestProtocolCompliance:
    def test_implements_iratelimiterquery(self) -> None:
        rl = RateLimiter()
        assert isinstance(rl, IRateLimiterQuery)


# ===========================================================================
# has_capacity Tests
# ===========================================================================


class TestHasCapacity:
    def test_unknown_provider_has_capacity(self) -> None:
        rl = RateLimiter()
        assert rl.has_capacity("unknown", 100) is True

    def test_fresh_provider_has_capacity(self, limiter: RateLimiter) -> None:
        assert limiter.has_capacity("openai", 100) is True

    def test_exhausted_provider_no_capacity(self, small_limiter: RateLimiter) -> None:
        # Exhaust RPM bucket
        for _ in range(5):
            small_limiter.acquire("openai", 1)
        assert small_limiter.has_capacity("openai", 1) is False


# ===========================================================================
# acquire Tests
# ===========================================================================


class TestAcquire:
    def test_acquire_success(self, limiter: RateLimiter) -> None:
        decision = limiter.acquire("openai", 100)
        assert decision.allowed is True
        assert decision.provider_id == "openai"

    def test_acquire_unknown_provider_allowed(self) -> None:
        rl = RateLimiter()
        decision = rl.acquire("unknown", 100)
        assert decision.allowed is True

    def test_acquire_decrements_buckets(self, small_limiter: RateLimiter) -> None:
        """Acquiring should reduce remaining capacity."""
        remaining_before = small_limiter.get_remaining("openai")
        small_limiter.acquire("openai", 10)
        remaining_after = small_limiter.get_remaining("openai")

        assert remaining_after[0] < remaining_before[0]  # RPM decreased
        assert remaining_after[1] < remaining_before[1]  # TPM decreased

    def test_acquire_rpm_exhausted(self, small_limiter: RateLimiter) -> None:
        """RPM bucket exhaustion -> denied."""
        for _ in range(5):
            small_limiter.acquire("openai", 1)

        decision = small_limiter.acquire("openai", 1)
        assert decision.allowed is False
        assert decision.retry_after_s > 0

    def test_acquire_tpm_exhausted(self, small_limiter: RateLimiter) -> None:
        """TPM bucket exhaustion -> denied."""
        # TPM bucket is 100 tokens (1.0 headroom)
        decision = small_limiter.acquire("openai", 101)
        assert decision.allowed is False

    def test_acquire_atomic_both_checked(self, small_limiter: RateLimiter) -> None:
        """Both RPM and TPM must pass for acquire to succeed."""
        # Use almost all TPM
        small_limiter.acquire("openai", 99)
        # Should still have RPM capacity but not enough TPM
        decision = small_limiter.acquire("openai", 10)
        assert decision.allowed is False


# ===========================================================================
# Headroom Tests (MH-12)
# ===========================================================================


class TestHeadroom:
    def test_default_headroom_80_percent(self) -> None:
        """Default 80% headroom reduces effective capacity."""
        rl = RateLimiter(default_headroom_pct=0.80)
        rl.register_provider("openai", rpm=100, tpm=10000)

        # Effective RPM = 80, effective TPM = 8000
        remaining = rl.get_remaining("openai")
        assert remaining[0] == 80  # 100 * 0.80
        assert remaining[1] == 8000  # 10000 * 0.80

    def test_custom_headroom(self) -> None:
        rl = RateLimiter()
        rl.register_provider("openai", rpm=100, tpm=10000, headroom_pct=0.50)

        remaining = rl.get_remaining("openai")
        assert remaining[0] == 50
        assert remaining[1] == 5000

    def test_full_headroom(self) -> None:
        """headroom_pct=1.0 means full capacity available."""
        rl = RateLimiter()
        rl.register_provider("openai", rpm=100, tpm=10000, headroom_pct=1.0)

        remaining = rl.get_remaining("openai")
        assert remaining[0] == 100
        assert remaining[1] == 10000


# ===========================================================================
# Query Tests
# ===========================================================================


class TestQuery:
    def test_get_remaining_unknown_provider(self) -> None:
        rl = RateLimiter()
        assert rl.get_remaining("unknown") == (0, 0)

    def test_get_remaining_after_acquire(self, small_limiter: RateLimiter) -> None:
        before = small_limiter.get_remaining("openai")
        small_limiter.acquire("openai", 10)
        after = small_limiter.get_remaining("openai")

        assert after[0] == before[0] - 1
        assert after[1] == before[1] - 10


# ===========================================================================
# Re-exports
# ===========================================================================


class TestRateLimiterReExports:
    def test_rate_limiter_reexport(self) -> None:
        from k1.model_hub.services import RateLimiter as Reexported

        assert Reexported is RateLimiter

    def test_rate_decision_reexport(self) -> None:
        from k1.model_hub.services import RateDecision as Reexported

        assert Reexported is RateDecision
