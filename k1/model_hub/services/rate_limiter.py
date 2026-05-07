"""Per-provider token bucket rate limiter [F49].

Manages per-provider request rate (RPM) and token rate (TPM)
using token bucket algorithm with manifest-driven config and
configurable headroom.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.rate_limiter
  -> k1.model_hub.manifest    (Layer 0: RateLimitConfig)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: RateLimiter service
- Invariant MH-12: Rate limiting per provider with 80% headroom
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional

# ===========================================================================
# Rate Decision
# ===========================================================================


@dataclass(frozen=True)
class RateDecision:
    """Result of a rate limit check."""

    allowed: bool
    provider_id: str
    tokens_remaining: int = 0
    requests_remaining: int = 0
    retry_after_s: float = 0.0


# ===========================================================================
# Token Bucket
# ===========================================================================


class _TokenBucket:
    """Simple token bucket for rate limiting.

    Supports both request-per-minute (RPM) and tokens-per-minute (TPM).
    """

    def __init__(self, capacity: int, refill_rate: float) -> None:
        """Initialize token bucket.

        Args:
            capacity: Maximum bucket size.
            refill_rate: Tokens added per second.
        """
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def try_consume(self, amount: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        self._refill()
        if self._tokens >= amount:
            self._tokens -= amount
            return True
        return False

    @property
    def available(self) -> int:
        """Current available tokens."""
        self._refill()
        return int(self._tokens)

    @property
    def capacity(self) -> int:
        """Maximum bucket capacity."""
        return self._capacity

    def retry_after(self, amount: int = 1) -> float:
        """Seconds until `amount` tokens are available."""
        self._refill()
        deficit = amount - self._tokens
        if deficit <= 0:
            return 0.0
        return deficit / self._refill_rate if self._refill_rate > 0 else float("inf")


# ===========================================================================
# Per-provider rate state
# ===========================================================================


@dataclass
class _ProviderRate:
    """Per-provider rate limiting state."""

    rpm_bucket: _TokenBucket
    tpm_bucket: _TokenBucket
    headroom_pct: float = 0.80


# ===========================================================================
# RateLimiter
# ===========================================================================


class RateLimiter:
    """Per-provider token bucket rate limiter (MH-12).

    Two buckets per provider:
      - RPM bucket: requests per minute.
      - TPM bucket: tokens per minute.

    Headroom: Only allows usage up to headroom_pct of capacity.
    Default headroom: 80% (from manifest.rate_limits.headroom_pct).

    Implements IRateLimiterQuery protocol from capability_router.
    """

    def __init__(self, *, default_headroom_pct: float = 0.80) -> None:
        """Initialize RateLimiter.

        Args:
            default_headroom_pct: Default headroom percentage (0-1).
        """
        self._providers: Dict[str, _ProviderRate] = {}
        self._default_headroom_pct = default_headroom_pct

    # -- Registration ----------------------------------------------------------

    def register_provider(
        self,
        provider_id: str,
        rpm: int = 60,
        tpm: int = 100000,
        headroom_pct: Optional[float] = None,
    ) -> None:
        """Register a provider with rate limit config from manifest.

        Args:
            provider_id: Provider identifier.
            rpm: Requests per minute limit.
            tpm: Tokens per minute limit.
            headroom_pct: Override headroom (0-1). Uses default if None.
        """
        hp = headroom_pct if headroom_pct is not None else self._default_headroom_pct
        effective_rpm = int(rpm * hp)
        effective_tpm = int(tpm * hp)

        self._providers[provider_id] = _ProviderRate(
            rpm_bucket=_TokenBucket(effective_rpm, effective_rpm / 60.0),
            tpm_bucket=_TokenBucket(effective_tpm, effective_tpm / 60.0),
            headroom_pct=hp,
        )

    def unregister_provider(self, provider_id: str) -> None:
        """Remove a provider's rate limit state."""
        self._providers.pop(provider_id, None)

    # -- IRateLimiterQuery protocol --------------------------------------------

    def has_capacity(self, provider_id: str, token_estimate: int) -> bool:
        """Check if provider has rate limit capacity.

        Implements IRateLimiterQuery.has_capacity().
        Returns True for unknown providers.
        """
        rate = self._providers.get(provider_id)
        if rate is None:
            return True

        # Check both RPM and TPM buckets
        return rate.rpm_bucket.available >= 1 and rate.tpm_bucket.available >= max(
            token_estimate, 1
        )

    # -- Acquire ---------------------------------------------------------------

    def acquire(self, provider_id: str, token_estimate: int = 1) -> RateDecision:
        """Acquire rate limit capacity for a request.

        Consumes 1 from RPM bucket and token_estimate from TPM bucket.
        Both must succeed or neither is consumed.

        Args:
            provider_id: Provider identifier.
            token_estimate: Estimated tokens for this request.

        Returns:
            RateDecision with allowed status and remaining capacity.
        """
        rate = self._providers.get(provider_id)
        if rate is None:
            return RateDecision(
                allowed=True,
                provider_id=provider_id,
                tokens_remaining=0,
                requests_remaining=0,
            )

        tokens_needed = max(token_estimate, 1)

        # Check both buckets before consuming
        rpm_ok = rate.rpm_bucket.available >= 1
        tpm_ok = rate.tpm_bucket.available >= tokens_needed

        if rpm_ok and tpm_ok:
            rate.rpm_bucket.try_consume(1)
            rate.tpm_bucket.try_consume(tokens_needed)
            return RateDecision(
                allowed=True,
                provider_id=provider_id,
                tokens_remaining=rate.tpm_bucket.available,
                requests_remaining=rate.rpm_bucket.available,
            )

        # Compute retry_after from whichever bucket is the bottleneck
        retry_rpm = rate.rpm_bucket.retry_after(1) if not rpm_ok else 0.0
        retry_tpm = rate.tpm_bucket.retry_after(tokens_needed) if not tpm_ok else 0.0

        return RateDecision(
            allowed=False,
            provider_id=provider_id,
            tokens_remaining=rate.tpm_bucket.available,
            requests_remaining=rate.rpm_bucket.available,
            retry_after_s=max(retry_rpm, retry_tpm),
        )

    # -- Query -----------------------------------------------------------------

    def is_registered(self, provider_id: str) -> bool:
        """Check if a provider has rate limit state."""
        return provider_id in self._providers

    def get_remaining(self, provider_id: str) -> tuple[int, int]:
        """Get (requests_remaining, tokens_remaining) for a provider.

        Returns (0, 0) for unknown providers.
        """
        rate = self._providers.get(provider_id)
        if rate is None:
            return (0, 0)
        return (rate.rpm_bucket.available, rate.tpm_bucket.available)


__all__ = [
    "RateDecision",
    "RateLimiter",
]
