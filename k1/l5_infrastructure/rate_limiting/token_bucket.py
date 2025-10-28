"""
Token Bucket - Distributed Rate Limiting with Redis

Layer: L5 Infrastructure
Component: Rate Limiting
Priority: 🟡 MEDIUM (Flow Control, Feature-Flagged)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

⚠️ FEATURE FLAG CONTROLLED:
    - Flag: ENABLE_RATE_LIMITING (default: False)
    - Config: k1/config/kernel.yaml: rate_limiting.enabled
    - Behavior: When False, all rate limits PASS (allow all requests)
    - Phase 1 (Today): OFF (no rate limiting, free-for-all)
    - Phase 2 (Production): ON (enforce quotas)

Architecture Decision Records:
    - ADR-0030: Rate Limiting Strategy (token bucket algorithm)
    - ADR-0028d: Local In-Memory Cache (Redis alternative for local mode)
    - ADR-0015: K0 Bus Architecture (state persistence)

Token Bucket Philosophy:
    - Distributed state: Redis-backed for multi-instance K1
    - Atomic operations: Lua scripts for race-free consumption
    - Burst capacity: Allow accumulated tokens for bursty traffic
    - Precise refills: Millisecond-precision token refills
    - Graceful degradation: If Redis down, ALLOW requests (fail open)

Token Bucket Algorithm:
    - Capacity: Maximum tokens in bucket (burst capacity)
    - Refill rate: Tokens added per second (e.g., 16.67 for 1000 req/min)
    - Consumption: Each request consumes 1+ tokens
    - Refill logic: tokens = min(current + elapsed * rate, capacity)
    - Atomic: Redis Lua script ensures race-free operations

Example Configuration:
    - 1,000 requests/minute → 16.67 tokens/second, capacity 100 (burst)
    - 10,000 requests/minute → 166.67 tokens/second, capacity 1000 (burst)
    - 100 requests/minute → 1.67 tokens/second, capacity 10 (burst)

Rate Limit Tiers:
    - Free: 100 req/min (1.67/s, burst 10)
    - Standard: 1,000 req/min (16.67/s, burst 100)
    - Professional: 10,000 req/min (166.67/s, burst 1000)
    - Enterprise: 100,000 req/min (1666.67/s, burst 10000)

Feature Flag Integration:
    - Check ENABLE_RATE_LIMITING flag on every consume()
    - If False: Return True immediately (allow all)
    - If True: Execute token bucket algorithm
    - Metrics: Track feature_flag_bypasses_total

Dependencies:
    Internal:
        - k1.config (Feature flag: rate_limiting.enabled)
        - k1.telemetry.metrics (Prometheus metrics)
    External (Optional):
        - redis (distributed state, graceful degradation if unavailable)
        - None (can use local mode with K0 bus as fallback)

Connects To:
    Upstream:
        - k1.api.gateway (Rate limit API requests)
        - k1.l2_orchestration.orchestrator (Rate limit orchestration calls)
        - k1.l3_execution.agents (Rate limit agent operations)
    Downstream:
        - Redis (distributed token bucket state)
        - k0.bus (fallback local state)

Performance Budgets:
    - consume(): <5ms P95 (Redis + Lua script)
    - is_allowed(): <5ms P95 (Redis read)
    - consume_many(): <5ms P95 (atomic multi-token consumption)
    - Feature flag bypass: <0.1ms (immediate return)

Observability:
    - Metrics: k1_rate_limit_requests_total{result} (allowed/rejected)
    - Metrics: k1_rate_limit_consume_duration_seconds (histogram)
    - Metrics: k1_rate_limit_tokens_available{bucket_key} (gauge)
    - Metrics: k1_rate_limit_feature_flag_bypasses_total (counter)
    - Traces: Span rate_limit.consume, rate_limit.is_allowed
    - Logs: INFO rate limit exceeded, DEBUG token consumed

References:
    - Whiteboard: docs/whiteboard.md (Section: Rate Limiting)
    - Planning: docs/planning/stub_generation_plan_layer5.md (Milestone 10, Epic 10.1)
    - Test: tests/k1/l5_infrastructure/rate_limiting/test_token_bucket.py
"""

import logging

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
from typing import Any, Dict, Optional

# Internal imports
# TODO(@resilience-team): Import from existing modules (Issue #L5-10.1.1)
# from redis import Redis
# from k1.config import get_config
# from k1.telemetry.metrics import (
#     k1_rate_limit_requests_total,
#     k1_rate_limit_consume_duration_seconds,
#     k1_rate_limit_tokens_available,
#     k1_rate_limit_feature_flag_bypasses_total,
# )

logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# Feature flag (Phase 1: OFF, Phase 2: ON)
DEFAULT_ENABLE_RATE_LIMITING = False

# Token bucket defaults
DEFAULT_CAPACITY = 100  # Max tokens (burst capacity)
DEFAULT_REFILL_RATE_PER_SECOND = 16.67  # 1000 req/min

# Rate limit tiers
TIER_FREE_REQUESTS_PER_MINUTE = 100
TIER_FREE_BURST_CAPACITY = 10

TIER_STANDARD_REQUESTS_PER_MINUTE = 1000
TIER_STANDARD_BURST_CAPACITY = 100

TIER_PROFESSIONAL_REQUESTS_PER_MINUTE = 10000
TIER_PROFESSIONAL_BURST_CAPACITY = 1000

TIER_ENTERPRISE_REQUESTS_PER_MINUTE = 100000
TIER_ENTERPRISE_BURST_CAPACITY = 10000

# Redis configuration
REDIS_BUCKET_KEY_PREFIX = "rate_limit:token_bucket:"
REDIS_TTL_SECONDS = 3600  # Expire inactive buckets after 1 hour

# Consumption results
CONSUME_RESULT_ALLOWED = "allowed"
CONSUME_RESULT_REJECTED = "rejected"
CONSUME_RESULT_FEATURE_FLAG_BYPASS = "feature_flag_bypass"
CONSUME_RESULT_REDIS_ERROR = "redis_error"

# =============================================================================
# SECTION 3: LUA SCRIPTS FOR ATOMIC OPERATIONS
# =============================================================================

# Lua script for atomic token consumption (race-free)
LUA_CONSUME_SCRIPT = """
-- KEYS[1]: bucket_key (e.g., "rate_limit:token_bucket:user:123")
-- ARGV[1]: current_time_ms
-- ARGV[2]: capacity (max tokens)
-- ARGV[3]: refill_rate_per_ms (tokens per millisecond)
-- ARGV[4]: tokens_to_consume (default: 1)
-- ARGV[5]: ttl_seconds (expire inactive buckets)

local bucket_key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])
local consume = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

-- Get current bucket state (tokens, last_refill)
local tokens = tonumber(redis.call('HGET', bucket_key, 'tokens') or capacity)
local last_refill = tonumber(redis.call('HGET', bucket_key, 'last_refill') or now)

-- Calculate elapsed time and refill
local elapsed = now - last_refill
local refilled = math.min(tokens + (elapsed * refill_rate), capacity)

-- Check if sufficient tokens
if refilled >= consume then
  -- Consume tokens
  redis.call('HSET', bucket_key, 'tokens', refilled - consume, 'last_refill', now)
  redis.call('EXPIRE', bucket_key, ttl)
  return {1, refilled - consume}  -- {allowed, tokens_remaining}
else
  -- Insufficient tokens (rate limited)
  redis.call('HSET', bucket_key, 'tokens', refilled, 'last_refill', now)
  redis.call('EXPIRE', bucket_key, ttl)
  return {0, refilled}  -- {rejected, tokens_available}
end
"""

# Lua script for checking token availability (non-consuming)
LUA_CHECK_SCRIPT = """
-- KEYS[1]: bucket_key
-- ARGV[1]: current_time_ms
-- ARGV[2]: capacity
-- ARGV[3]: refill_rate_per_ms

local bucket_key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])

-- Get current bucket state
local tokens = tonumber(redis.call('HGET', bucket_key, 'tokens') or capacity)
local last_refill = tonumber(redis.call('HGET', bucket_key, 'last_refill') or now)

-- Calculate current tokens (with refill)
local elapsed = now - last_refill
local refilled = math.min(tokens + (elapsed * refill_rate), capacity)

-- Return available tokens (no consumption)
return refilled
"""

# =============================================================================
# SECTION 4: TOKEN BUCKET IMPLEMENTATION
# =============================================================================


class TokenBucket:
    """
    Distributed token bucket rate limiter with Redis backend.

    ⚠️ FEATURE FLAG CONTROLLED:
        - When ENABLE_RATE_LIMITING = False: ALL requests allowed (bypass)
        - When ENABLE_RATE_LIMITING = True: Enforce token bucket limits
        - Graceful: If Redis unavailable, ALLOW requests (fail open)

    Token Bucket Algorithm:
        - Capacity: Maximum tokens in bucket (burst capacity)
        - Refill rate: Tokens added per second
        - Consumption: Each request consumes 1+ tokens
        - Refill: tokens = min(current + elapsed * rate, capacity)
        - Atomic: Redis Lua script for race-free operations

    Responsibilities:
        - Maintain distributed token bucket state (Redis)
        - Calculate tokens available (based on elapsed time)
        - Consume tokens atomically (Lua script)
        - Handle burst capacity (accumulated tokens)
        - Track quota statistics (tokens remaining, reset time)
        - Graceful degradation (Redis failure → allow requests)

    Performance (P95):
        - consume(): <5ms (Redis + Lua script)
        - is_allowed(): <5ms (Redis read)
        - consume_many(): <5ms (atomic multi-token)
        - Feature flag bypass: <0.1ms (immediate return)

    Thread Safety: Yes (Redis atomic operations)
    Async Safe: Yes

    Examples:
        >>> # Standard tier: 1000 req/min (16.67/s, burst 100)
        >>> bucket = TokenBucket(
        ...     redis_client=redis,
        ...     bucket_key="user:123",
        ...     capacity=100,
        ...     refill_rate_per_second=16.67,
        ... )
        >>> allowed = await bucket.consume()
        >>> print(allowed)
        True  # Request allowed

        >>> # Feature flag OFF: All requests allowed
        >>> bucket._enable_rate_limiting = False
        >>> allowed = await bucket.consume()
        >>> print(allowed)
        True  # Bypassed (feature flag OFF)

    References:
        - ADR-0030: Rate Limiting Strategy
        - Token Bucket Algorithm: https://en.wikipedia.org/wiki/Token_bucket
    """

    def __init__(
        self,
        redis_client: Any,  # TODO: Type hint Redis
        bucket_key: str,
        capacity: int = DEFAULT_CAPACITY,
        refill_rate_per_second: float = DEFAULT_REFILL_RATE_PER_SECOND,
        enable_rate_limiting: Optional[bool] = None,
    ):
        """
        Initialize token bucket with Redis backend.

        Args:
            redis_client: Redis client (or None for local mode)
            bucket_key: Unique bucket identifier (e.g., "user:123", "tenant:org1")
            capacity: Max tokens in bucket (burst capacity)
            refill_rate_per_second: Tokens added per second
            enable_rate_limiting: Override feature flag (None = use config)

        Side Effects:
            - Stores configuration
            - Registers Lua scripts with Redis
            - Initializes bucket state (if new)

        Feature Flag:
            - If enable_rate_limiting=False: Bypass all rate limits
            - If enable_rate_limiting=True: Enforce limits
            - If None: Read from config (rate_limiting.enabled)

        ADR: ADR-0030 (Token Bucket Initialization)
        Assigned to: Issue #L5-10.1.1
        """
        # TODO(@resilience-team): Implement token bucket initialization
        # 1. Store configuration:
        #    - self._redis = redis_client
        #    - self._bucket_key = bucket_key
        #    - self._full_key = f"{REDIS_BUCKET_KEY_PREFIX}{bucket_key}"
        #    - self._capacity = capacity
        #    - self._refill_rate_per_second = refill_rate_per_second
        #    - self._refill_rate_per_ms = refill_rate_per_second / 1000.0
        # 2. Feature flag:
        #    - if enable_rate_limiting is None:
        #        self._enable_rate_limiting = get_config().get('rate_limiting.enabled', DEFAULT_ENABLE_RATE_LIMITING)
        #      else:
        #        self._enable_rate_limiting = enable_rate_limiting
        # 3. Register Lua scripts:
        #    - if self._redis:
        #        self._consume_script = self._redis.register_script(LUA_CONSUME_SCRIPT)
        #        self._check_script = self._redis.register_script(LUA_CHECK_SCRIPT)
        # 4. Statistics:
        #    - self._total_requests = 0
        #    - self._total_allowed = 0
        #    - self._total_rejected = 0
        #    - self._feature_flag_bypasses = 0
        # 5. Setup logger
        self._logger = logger
        pass

    async def consume(
        self,
        tokens: int = 1,
        cognitive_trace_id: Optional[str] = None,
    ) -> bool:
        """
        Consume tokens if available (atomic operation).

        Args:
            tokens: Number of tokens to consume (default: 1)
            cognitive_trace_id: Trace ID for observability

        Returns:
            True if tokens consumed (request allowed)
            False if insufficient tokens (rate limited)

        Performance:
            - Feature flag bypass: <0.1ms (immediate return True)
            - Redis + Lua: <5ms P95 (atomic consumption)

        Behavior (Feature Flag ON):
            1. Get current time (milliseconds)
            2. Execute Lua script (atomic refill + consume)
            3. If tokens >= required: Consume, return True
            4. If tokens < required: Return False (rate limited)

        Behavior (Feature Flag OFF):
            1. Return True immediately (all requests allowed)
            2. Increment feature_flag_bypasses metric

        Graceful Degradation:
            - If Redis unavailable: Log error, return True (fail open)
            - Metrics: Track redis_error results

        ADR: ADR-0030 (Token Consumption)
        Assigned to: Issue #L5-10.1.1
        """
        # TODO(@resilience-team): Implement token consumption
        # 1. Check feature flag:
        #    - if not self._enable_rate_limiting:
        #        self._feature_flag_bypasses += 1
        #        k1_rate_limit_feature_flag_bypasses_total.labels(bucket_key=self._bucket_key).inc()
        #        logger.debug(f"Rate limit bypassed (feature flag OFF): {self._bucket_key} (trace: {cognitive_trace_id})")
        #        return True
        # 2. Start timer:
        #    - start_time = time.perf_counter()
        # 3. Execute Lua script:
        #    - try:
        #        now_ms = int(time.time() * 1000)
        #        result = self._consume_script(
        #            keys=[self._full_key],
        #            args=[now_ms, self._capacity, self._refill_rate_per_ms, tokens, REDIS_TTL_SECONDS]
        #        )
        #        allowed = bool(result[0])
        #        tokens_remaining = result[1]
        #      except Exception as e:
        #        logger.error(f"Redis error in consume: {e} (trace: {cognitive_trace_id})")
        #        k1_rate_limit_requests_total.labels(bucket_key=self._bucket_key, result=CONSUME_RESULT_REDIS_ERROR).inc()
        #        return True  # Fail open (allow request)
        # 4. Update statistics:
        #    - self._total_requests += 1
        #    - if allowed:
        #        self._total_allowed += 1
        #        result_label = CONSUME_RESULT_ALLOWED
        #      else:
        #        self._total_rejected += 1
        #        result_label = CONSUME_RESULT_REJECTED
        # 5. Emit metrics:
        #    - duration = time.perf_counter() - start_time
        #    - k1_rate_limit_requests_total.labels(bucket_key=self._bucket_key, result=result_label).inc()
        #    - k1_rate_limit_consume_duration_seconds.labels(bucket_key=self._bucket_key).observe(duration)
        #    - k1_rate_limit_tokens_available.labels(bucket_key=self._bucket_key).set(tokens_remaining)
        # 6. Log:
        #    - if allowed:
        #        logger.debug(f"Token consumed: {self._bucket_key} ({tokens} tokens, {tokens_remaining} remaining, trace: {cognitive_trace_id})")
        #      else:
        #        logger.info(f"Rate limit exceeded: {self._bucket_key} ({tokens} tokens required, {tokens_remaining} available, trace: {cognitive_trace_id})")
        # 7. Return result
        pass

    async def is_allowed(
        self,
        tokens: int = 1,
        cognitive_trace_id: Optional[str] = None,
    ) -> bool:
        """
        Check if tokens available (non-consuming check).

        Args:
            tokens: Number of tokens to check (default: 1)
            cognitive_trace_id: Trace ID for observability

        Returns:
            True if tokens available, False otherwise

        Performance:
            - Feature flag bypass: <0.1ms (immediate return True)
            - Redis read: <5ms P95

        Behavior:
            - Calculate current tokens (refill only, no consumption)
            - Check if >= tokens required
            - Do NOT consume tokens

        Use Cases:
            - Pre-flight checks before expensive operations
            - UI display: "You have X requests remaining"
            - Health checks: "Rate limit healthy"

        ADR: ADR-0030 (Token Availability Check)
        Assigned to: Issue #L5-10.1.1
        """
        # TODO(@resilience-team): Implement availability check
        # 1. Check feature flag:
        #    - if not self._enable_rate_limiting:
        #        return True  # Bypass
        # 2. Execute Lua check script:
        #    - try:
        #        now_ms = int(time.time() * 1000)
        #        tokens_available = self._check_script(
        #            keys=[self._full_key],
        #            args=[now_ms, self._capacity, self._refill_rate_per_ms]
        #        )
        #        return tokens_available >= tokens
        #      except Exception as e:
        #        logger.error(f"Redis error in is_allowed: {e} (trace: {cognitive_trace_id})")
        #        return True  # Fail open
        pass

    async def consume_many(
        self,
        tokens: int,
        cognitive_trace_id: Optional[str] = None,
    ) -> bool:
        """
        Consume multiple tokens atomically.

        Args:
            tokens: Number of tokens to consume
            cognitive_trace_id: Trace ID for observability

        Returns:
            True if all tokens consumed, False if insufficient

        Use Cases:
            - Batch requests: 5 tokens (process 5 items)
            - Large uploads: 50 tokens (50MB upload)
            - Premium operations: 100 tokens (expensive inference)

        Performance:
            - Same as consume(): <5ms P95 (Lua script handles any token count)

        ADR: ADR-0030 (Multi-Token Consumption)
        Assigned to: Issue #L5-10.1.1
        """
        # TODO(@resilience-team): Reuse consume() with tokens parameter
        return await self.consume(tokens=tokens, cognitive_trace_id=cognitive_trace_id)

    async def get_status(
        self,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get current bucket status.

        Args:
            cognitive_trace_id: Trace ID for observability

        Returns:
            {
                "tokens_available": float,  # Current tokens (with refill)
                "capacity": int,  # Max tokens (burst capacity)
                "refill_rate_per_second": float,  # Tokens per second
                "requests_per_minute": float,  # Rate limit (req/min)
                "reset_in_seconds": float,  # Time until full refill
                "feature_flag_enabled": bool,  # ENABLE_RATE_LIMITING state
                "bucket_key": str,  # Bucket identifier
            }

        Performance:
            - Redis read: <5ms P95

        Use Cases:
            - API response headers: X-RateLimit-Remaining, X-RateLimit-Reset
            - UI display: "You have 95/100 requests remaining"
            - Monitoring: Track quota usage trends

        ADR: ADR-0030 (Bucket Status)
        Assigned to: Issue #L5-10.1.1
        """
        # TODO(@resilience-team): Implement status retrieval
        # 1. Execute Lua check script:
        #    - try:
        #        now_ms = int(time.time() * 1000)
        #        tokens_available = self._check_script(
        #            keys=[self._full_key],
        #            args=[now_ms, self._capacity, self._refill_rate_per_ms]
        #        )
        #      except Exception as e:
        #        logger.error(f"Redis error in get_status: {e} (trace: {cognitive_trace_id})")
        #        tokens_available = self._capacity  # Fail open (assume full)
        # 2. Calculate reset time:
        #    - tokens_needed = self._capacity - tokens_available
        #    - reset_in_seconds = tokens_needed / self._refill_rate_per_second
        # 3. Build status dict:
        #    - return {
        #        "tokens_available": tokens_available,
        #        "capacity": self._capacity,
        #        "refill_rate_per_second": self._refill_rate_per_second,
        #        "requests_per_minute": self._refill_rate_per_second * 60,
        #        "reset_in_seconds": reset_in_seconds,
        #        "feature_flag_enabled": self._enable_rate_limiting,
        #        "bucket_key": self._bucket_key,
        #      }
        pass

    async def reset(
        self,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Reset bucket to full capacity (admin operation).

        Args:
            cognitive_trace_id: Trace ID for observability

        Behavior:
            - Set tokens = capacity
            - Set last_refill = now
            - Clear rate limit history

        Use Cases:
            - Admin override: "Reset user quota"
            - Testing: "Reset to full capacity"
            - Quota adjustments: "Apply new tier limits"

        ADR: ADR-0030 (Bucket Reset)
        Assigned to: Issue #L5-10.1.1
        """
        # TODO(@resilience-team): Implement bucket reset
        # 1. Reset Redis state:
        #    - try:
        #        now_ms = int(time.time() * 1000)
        #        self._redis.hset(self._full_key, mapping={
        #            'tokens': self._capacity,
        #            'last_refill': now_ms,
        #        })
        #        self._redis.expire(self._full_key, REDIS_TTL_SECONDS)
        #        logger.info(f"Bucket reset: {self._bucket_key} (trace: {cognitive_trace_id})")
        #      except Exception as e:
        #        logger.error(f"Redis error in reset: {e} (trace: {cognitive_trace_id})")
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get bucket statistics (local counters).

        Returns:
            {
                "total_requests": int,
                "total_allowed": int,
                "total_rejected": int,
                "feature_flag_bypasses": int,
                "allow_rate_pct": float,
                "reject_rate_pct": float,
                "feature_flag_enabled": bool,
            }

        Performance:
            - Latency: <1ms (local counters)

        ADR: ADR-0030 (Bucket Statistics)
        Assigned to: Issue #L5-10.1.1
        """
        # TODO(@resilience-team): Implement statistics collection
        # 1. Calculate rates:
        #    - allow_rate = (self._total_allowed / self._total_requests * 100) if self._total_requests > 0 else 0
        #    - reject_rate = (self._total_rejected / self._total_requests * 100) if self._total_requests > 0 else 0
        # 2. Build statistics dict:
        #    - return {
        #        "total_requests": self._total_requests,
        #        "total_allowed": self._total_allowed,
        #        "total_rejected": self._total_rejected,
        #        "feature_flag_bypasses": self._feature_flag_bypasses,
        #        "allow_rate_pct": allow_rate,
        #        "reject_rate_pct": reject_rate,
        #        "feature_flag_enabled": self._enable_rate_limiting,
        #      }
        pass


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


def calculate_refill_rate(requests_per_minute: int) -> float:
    """
    Calculate refill rate (tokens per second) from requests per minute.

    Args:
        requests_per_minute: Desired request rate (e.g., 1000)

    Returns:
        Refill rate in tokens per second (e.g., 16.67)

    Examples:
        >>> calculate_refill_rate(1000)
        16.666666666666668
        >>> calculate_refill_rate(10000)
        166.66666666666666

    ADR: ADR-0030
    """
    return requests_per_minute / 60.0


def get_tier_config(tier: str) -> Dict[str, Any]:
    """
    Get token bucket configuration for rate limit tier.

    Args:
        tier: Rate limit tier (free/standard/professional/enterprise)

    Returns:
        {
            "requests_per_minute": int,
            "burst_capacity": int,
            "refill_rate_per_second": float,
        }

    Examples:
        >>> get_tier_config("standard")
        {"requests_per_minute": 1000, "burst_capacity": 100, "refill_rate_per_second": 16.67}

    ADR: ADR-0030
    """
    # TODO(@resilience-team): Implement tier config lookup
    # tiers = {
    #     'free': {
    #         'requests_per_minute': TIER_FREE_REQUESTS_PER_MINUTE,
    #         'burst_capacity': TIER_FREE_BURST_CAPACITY,
    #         'refill_rate_per_second': calculate_refill_rate(TIER_FREE_REQUESTS_PER_MINUTE),
    #     },
    #     'standard': {
    #         'requests_per_minute': TIER_STANDARD_REQUESTS_PER_MINUTE,
    #         'burst_capacity': TIER_STANDARD_BURST_CAPACITY,
    #         'refill_rate_per_second': calculate_refill_rate(TIER_STANDARD_REQUESTS_PER_MINUTE),
    #     },
    #     'professional': {
    #         'requests_per_minute': TIER_PROFESSIONAL_REQUESTS_PER_MINUTE,
    #         'burst_capacity': TIER_PROFESSIONAL_BURST_CAPACITY,
    #         'refill_rate_per_second': calculate_refill_rate(TIER_PROFESSIONAL_REQUESTS_PER_MINUTE),
    #     },
    #     'enterprise': {
    #         'requests_per_minute': TIER_ENTERPRISE_REQUESTS_PER_MINUTE,
    #         'burst_capacity': TIER_ENTERPRISE_BURST_CAPACITY,
    #         'refill_rate_per_second': calculate_refill_rate(TIER_ENTERPRISE_REQUESTS_PER_MINUTE),
    #     },
    # }
    # return tiers.get(tier.lower(), tiers['standard'])
    pass


# =============================================================================
# SECTION 6: MODULE EXPORTS
# =============================================================================

__all__ = [
    "TokenBucket",
    "calculate_refill_rate",
    "get_tier_config",
    "DEFAULT_ENABLE_RATE_LIMITING",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Prometheus Metrics Exported:
#
# Counters:
#   - k1_rate_limit_requests_total{bucket_key, result} (allowed/rejected/redis_error/feature_flag_bypass)
#   - k1_rate_limit_feature_flag_bypasses_total{bucket_key} (feature flag OFF bypasses)
#
# Histograms:
#   - k1_rate_limit_consume_duration_seconds{bucket_key} (consume() latency)
#
# Gauges:
#   - k1_rate_limit_tokens_available{bucket_key} (current tokens in bucket)
#
# Example Prometheus Queries:
#   - Request rate: rate(k1_rate_limit_requests_total{result="allowed"}[5m])
#   - Rejection rate: rate(k1_rate_limit_requests_total{result="rejected"}[5m])
#   - Feature flag bypasses: rate(k1_rate_limit_feature_flag_bypasses_total[5m])
#   - Consume P95 latency: histogram_quantile(0.95, k1_rate_limit_consume_duration_seconds_bucket)
#   - Tokens remaining: k1_rate_limit_tokens_available{bucket_key="user:123"}
#
# Alert Rules:
#   - name: HighRateLimitRejectionRate
#     expr: rate(k1_rate_limit_requests_total{result="rejected"}[5m]) > 100
#     for: 5m
#     labels:
#       severity: warning
#     annotations:
#       summary: "High rate limit rejection rate (users hitting quotas)"
#
#   - name: RateLimitRedisErrors
#     expr: rate(k1_rate_limit_requests_total{result="redis_error"}[5m]) > 10
#     for: 2m
#     labels:
#       severity: critical
#     annotations:
#       summary: "Redis errors in rate limiting (failing open)"
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/rate_limiting/test_token_bucket.py
#   - Test token consumption (allowed → rejected)
#   - Test refill logic (tokens increase over time)
#   - Test burst capacity (consume up to capacity instantly)
#   - Test atomic operations (concurrent consume, no race conditions)
#   - Test feature flag bypass (ENABLE_RATE_LIMITING=False → all allowed)
#   - Test graceful degradation (Redis down → fail open)
#   - Test multi-token consumption (consume_many)
#   - Test status retrieval (tokens_available, reset_in_seconds)
#   - Test bucket reset (admin override)
#
# No simulation code allowed:
#   - Use real Redis with ward fixtures (or mock Redis client)
#   - Test actual Lua scripts (not mocked behavior)
#   - Integration tests > unit tests
#
# =============================================================================
