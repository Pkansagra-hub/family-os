"""
Rate Limiting - Token Bucket Algorithm with Feature Flag Control

⚠️ FEATURE FLAG CONTROLLED:
    - Flag: ENABLE_RATE_LIMITING (default: False)
    - Config: k1/config/kernel.yaml: rate_limiting.enabled
    - Phase 1 (Today): OFF (all requests allowed)
    - Phase 2 (Production): ON (enforce quotas)
"""

from k1.l5_infrastructure.rate_limiting.rate_limiter import (
    DEFAULT_TENANT_LIMIT_PER_MINUTE,
    DEFAULT_USER_LIMIT_PER_MINUTE,
    RateLimiter,
)
from k1.l5_infrastructure.rate_limiting.token_bucket import (
    DEFAULT_ENABLE_RATE_LIMITING,
    TokenBucket,
    calculate_refill_rate,
    get_tier_config,
)

__all__ = [
    "TokenBucket",
    "RateLimiter",
    "calculate_refill_rate",
    "get_tier_config",
    "DEFAULT_ENABLE_RATE_LIMITING",
    "DEFAULT_USER_LIMIT_PER_MINUTE",
    "DEFAULT_TENANT_LIMIT_PER_MINUTE",
]
