"""
Rate Limiter - Multi-Level Rate Limiting (Per-User + Per-Tenant)

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
    - ADR-0030: Rate Limiting Strategy (multi-level quotas)
    - ADR-0028d: Local In-Memory Cache (Redis alternative for local mode)
    - ADR-0015: K0 Bus Architecture (state persistence)

Multi-Level Rate Limiting Philosophy:
    - Hierarchical quotas: Tenant → User → Request
    - Stricter limit applies: min(user_quota, tenant_quota)
    - Independent buckets: User and tenant have separate token buckets
    - Coordinated enforcement: Both buckets must allow request
    - Dynamic limits: Adjust quotas per user/tenant (API or config)

Rate Limit Hierarchy:
    Tenant Quota (global limit for entire tenant):
      └─ User Quota (per-user limit within tenant):
          └─ Request (allowed/rejected based on stricter limit)

Decision Logic:
    1. Check user token bucket: user_allowed = user_bucket.consume()
    2. Check tenant token bucket: tenant_allowed = tenant_bucket.consume()
    3. Decision: allowed = user_allowed AND tenant_allowed
    4. If rejected: Refund consumed token (return to stricter bucket)

Example Scenario:
    - Tenant "acme-corp": 10,000 req/min limit, 5,000 consumed → 5,000 remaining
    - User "alice": 1,000 req/min limit, 800 consumed → 200 remaining
    - Effective limit: 200 (user is more restrictive)
    - Decision: Allow if both have tokens, reject if either exhausted

Feature Flag Integration:
    - Check ENABLE_RATE_LIMITING flag on every check_rate_limit()
    - If False: Return (True, quota_info) immediately (all requests allowed)
    - If True: Execute multi-level token bucket checks
    - Metrics: Track feature_flag_bypasses_total

Dependencies:
    Internal:
        - k1.l5_infrastructure.rate_limiting.token_bucket (TokenBucket)
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
        - k1.l5_infrastructure.rate_limiting.token_bucket (Token consumption)
        - Redis (distributed quota state)

Performance Budgets:
    - check_rate_limit(): <5ms P95 (2 token bucket checks)
    - set_user_limit(): <10ms P95 (Redis write)
    - set_tenant_limit(): <10ms P95 (Redis write)
    - get_quota_status(): <5ms P95 (Redis read)
    - Feature flag bypass: <0.1ms (immediate return)

Observability:
    - Metrics: k1_rate_limiter_requests_total{result, limit_reason} (counter)
    - Metrics: k1_rate_limiter_check_duration_seconds (histogram)
    - Metrics: k1_rate_limiter_quota_remaining{dimension, bucket_key} (gauge)
    - Metrics: k1_rate_limiter_feature_flag_bypasses_total (counter)
    - Traces: Span rate_limiter.check_rate_limit
    - Logs: INFO rate limit exceeded, DEBUG quota check

References:
    - Whiteboard: docs/whiteboard.md (Section: Rate Limiting)
    - Planning: docs/planning/stub_generation_plan_layer5.md (Milestone 10, Epic 10.2)
    - Test: tests/k1/l5_infrastructure/rate_limiting/test_rate_limiter.py
"""

import logging

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
from typing import Any, Dict, Optional, Tuple

# Internal imports
# TODO(@resilience-team): Import from existing modules (Issue #L5-10.2.1)
# from redis import Redis
# from k1.l5_infrastructure.rate_limiting.token_bucket import TokenBucket
# from k1.config import get_config
# from k1.telemetry.metrics import (
#     k1_rate_limiter_requests_total,
#     k1_rate_limiter_check_duration_seconds,
#     k1_rate_limiter_quota_remaining,
#     k1_rate_limiter_feature_flag_bypasses_total,
# )

logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# Feature flag (Phase 1: OFF, Phase 2: ON)
DEFAULT_ENABLE_RATE_LIMITING = False

# Default quotas
DEFAULT_USER_LIMIT_PER_MINUTE = 1000  # requests/minute
DEFAULT_TENANT_LIMIT_PER_MINUTE = 10000  # requests/minute

# Default burst capacities
DEFAULT_USER_BURST_CAPACITY = 100  # 10% of limit
DEFAULT_TENANT_BURST_CAPACITY = 1000  # 10% of limit

# Rate limit dimensions
DIMENSION_USER = "user"
DIMENSION_TENANT = "tenant"

# Rate limit results
RESULT_ALLOWED = "allowed"
RESULT_REJECTED_USER = "rejected_user"
RESULT_REJECTED_TENANT = "rejected_tenant"
RESULT_FEATURE_FLAG_BYPASS = "feature_flag_bypass"
RESULT_REDIS_ERROR = "redis_error"

# Limit reasons (which quota applied)
LIMIT_REASON_NONE = "none"  # Both allowed
LIMIT_REASON_USER = "user"  # User quota more restrictive
LIMIT_REASON_TENANT = "tenant"  # Tenant quota more restrictive

# =============================================================================
# SECTION 3: RATE LIMITER IMPLEMENTATION
# =============================================================================


class RateLimiter:
    """
    Multi-level rate limiter with per-user and per-tenant quotas.

    ⚠️ FEATURE FLAG CONTROLLED:
        - When ENABLE_RATE_LIMITING = False: ALL requests allowed (bypass)
        - When ENABLE_RATE_LIMITING = True: Enforce multi-level quotas
        - Graceful: If Redis unavailable, ALLOW requests (fail open)

    Quota Hierarchy:
        Tenant Quota (global limit for entire tenant):
          └─ User Quota (per-user limit within tenant):
              └─ Request (allowed/rejected based on stricter limit)

    Decision Logic:
        1. Check user token bucket: user_allowed = user_bucket.consume()
        2. Check tenant token bucket: tenant_allowed = tenant_bucket.consume()
        3. Decision: allowed = user_allowed AND tenant_allowed
        4. If rejected: Identify which limit applied (user or tenant)

    Responsibilities:
        - Enforce per-user rate limits
        - Enforce per-tenant rate limits
        - Coordinate limits (stricter limit applies)
        - Track quota usage per dimension
        - Report violations and trends
        - Support dynamic limit adjustments

    Performance (P95):
        - check_rate_limit(): <5ms (2 token bucket checks)
        - set_user_limit(): <10ms (Redis write)
        - set_tenant_limit(): <10ms (Redis write)
        - get_quota_status(): <5ms (Redis read)
        - Feature flag bypass: <0.1ms (immediate return)

    Thread Safety: Yes (token buckets use Redis atomic operations)
    Async Safe: Yes

    Examples:
        >>> limiter = RateLimiter(
        ...     redis_client=redis,
        ...     default_user_limit=1000,
        ...     default_tenant_limit=10000,
        ... )
        >>> allowed, info = await limiter.check_rate_limit(
        ...     user_id="alice",
        ...     tenant_id="acme-corp",
        ...     tokens_required=1,
        ... )
        >>> print(allowed, info['limit_reason'])
        True, 'none'  # Both quotas allowed

        >>> # Feature flag OFF: All requests allowed
        >>> limiter._enable_rate_limiting = False
        >>> allowed, info = await limiter.check_rate_limit("alice", "acme-corp")
        >>> print(allowed, info['limit_reason'])
        True, 'feature_flag_bypass'

    References:
        - ADR-0030: Rate Limiting Strategy
    """

    def __init__(
        self,
        redis_client: Any,  # TODO: Type hint Redis
        default_user_limit: int = DEFAULT_USER_LIMIT_PER_MINUTE,
        default_tenant_limit: int = DEFAULT_TENANT_LIMIT_PER_MINUTE,
        enable_rate_limiting: Optional[bool] = None,
    ):
        """
        Initialize multi-level rate limiter.

        Args:
            redis_client: Redis client (or None for local mode)
            default_user_limit: Default per-user limit (requests/minute)
            default_tenant_limit: Default per-tenant limit (requests/minute)
            enable_rate_limiting: Override feature flag (None = use config)

        Side Effects:
            - Stores configuration
            - Initializes token bucket cache
            - Sets up default quotas

        Feature Flag:
            - If enable_rate_limiting=False: Bypass all rate limits
            - If enable_rate_limiting=True: Enforce limits
            - If None: Read from config (rate_limiting.enabled)

        ADR: ADR-0030 (Rate Limiter Initialization)
        Assigned to: Issue #L5-10.2.1
        """
        # TODO(@resilience-team): Implement rate limiter initialization
        # 1. Store configuration:
        #    - self._redis = redis_client
        #    - self._default_user_limit = default_user_limit
        #    - self._default_tenant_limit = default_tenant_limit
        # 2. Feature flag:
        #    - if enable_rate_limiting is None:
        #        self._enable_rate_limiting = get_config().get('rate_limiting.enabled', DEFAULT_ENABLE_RATE_LIMITING)
        #      else:
        #        self._enable_rate_limiting = enable_rate_limiting
        # 3. Token bucket cache:
        #    - self._user_buckets: Dict[str, TokenBucket] = {}
        #    - self._tenant_buckets: Dict[str, TokenBucket] = {}
        # 4. Custom limits:
        #    - self._user_limits: Dict[str, int] = {}  # Custom per-user limits
        #    - self._tenant_limits: Dict[str, int] = {}  # Custom per-tenant limits
        # 5. Statistics:
        #    - self._total_requests = 0
        #    - self._total_allowed = 0
        #    - self._total_rejected_user = 0
        #    - self._total_rejected_tenant = 0
        #    - self._feature_flag_bypasses = 0
        # 6. Setup logger
        self._logger = logger
        pass

    async def check_rate_limit(
        self,
        user_id: str,
        tenant_id: str,
        tokens_required: int = 1,
        cognitive_trace_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request allowed under multi-level rate limits.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            tokens_required: Tokens to consume (default: 1)
            cognitive_trace_id: Trace ID for observability

        Returns:
            (allowed: bool, info: dict)
            where info contains:
                - user_quota_remaining: Tokens left for user
                - tenant_quota_remaining: Tokens left for tenant
                - reset_in_seconds: When quota resets
                - limit_reason: Which limit applied ("user", "tenant", "none", "feature_flag_bypass")

        Performance:
            - Feature flag bypass: <0.1ms (immediate return)
            - Multi-level check: <5ms P95 (2 token bucket checks)

        Flow (Feature Flag ON):
            1. Get or create user token bucket
            2. Get or create tenant token bucket
            3. Check user bucket: user_allowed = await user_bucket.consume(tokens_required)
            4. Check tenant bucket: tenant_allowed = await tenant_bucket.consume(tokens_required)
            5. If both allowed: Return (True, info with "none" reason)
            6. If user rejected: Return (False, info with "user" reason)
            7. If tenant rejected: Return (False, info with "tenant" reason)

        Flow (Feature Flag OFF):
            1. Return (True, info with "feature_flag_bypass" reason) immediately

        Graceful Degradation:
            - If Redis unavailable: Log error, return (True, info) (fail open)

        ADR: ADR-0030 (Multi-Level Rate Check)
        Assigned to: Issue #L5-10.2.1
        """
        # TODO(@resilience-team): Implement multi-level rate check
        # 1. Check feature flag:
        #    - if not self._enable_rate_limiting:
        #        self._feature_flag_bypasses += 1
        #        k1_rate_limiter_feature_flag_bypasses_total.inc()
        #        logger.debug(f"Rate limit bypassed (feature flag OFF): user={user_id}, tenant={tenant_id} (trace: {cognitive_trace_id})")
        #        return (True, {
        #            "user_quota_remaining": float('inf'),
        #            "tenant_quota_remaining": float('inf'),
        #            "reset_in_seconds": 0,
        #            "limit_reason": "feature_flag_bypass",
        #        })
        # 2. Start timer:
        #    - start_time = time.perf_counter()
        # 3. Get token buckets:
        #    - user_bucket = self._get_user_bucket(user_id)
        #    - tenant_bucket = self._get_tenant_bucket(tenant_id)
        # 4. Check user quota:
        #    - try:
        #        user_allowed = await user_bucket.consume(tokens_required, cognitive_trace_id)
        #      except Exception as e:
        #        logger.error(f"User bucket error: {e} (trace: {cognitive_trace_id})")
        #        user_allowed = True  # Fail open
        # 5. Check tenant quota:
        #    - try:
        #        tenant_allowed = await tenant_bucket.consume(tokens_required, cognitive_trace_id)
        #      except Exception as e:
        #        logger.error(f"Tenant bucket error: {e} (trace: {cognitive_trace_id})")
        #        tenant_allowed = True  # Fail open
        # 6. Determine result:
        #    - allowed = user_allowed and tenant_allowed
        #    - if not user_allowed:
        #        limit_reason = LIMIT_REASON_USER
        #        result_label = RESULT_REJECTED_USER
        #      elif not tenant_allowed:
        #        limit_reason = LIMIT_REASON_TENANT
        #        result_label = RESULT_REJECTED_TENANT
        #      else:
        #        limit_reason = LIMIT_REASON_NONE
        #        result_label = RESULT_ALLOWED
        # 7. Get quota status:
        #    - user_status = await user_bucket.get_status(cognitive_trace_id)
        #    - tenant_status = await tenant_bucket.get_status(cognitive_trace_id)
        # 8. Build info dict:
        #    - info = {
        #        "user_quota_remaining": user_status['tokens_available'],
        #        "tenant_quota_remaining": tenant_status['tokens_available'],
        #        "reset_in_seconds": min(user_status['reset_in_seconds'], tenant_status['reset_in_seconds']),
        #        "limit_reason": limit_reason,
        #      }
        # 9. Update statistics:
        #    - self._total_requests += 1
        #    - if allowed:
        #        self._total_allowed += 1
        #      elif limit_reason == LIMIT_REASON_USER:
        #        self._total_rejected_user += 1
        #      elif limit_reason == LIMIT_REASON_TENANT:
        #        self._total_rejected_tenant += 1
        # 10. Emit metrics:
        #    - duration = time.perf_counter() - start_time
        #    - k1_rate_limiter_requests_total.labels(result=result_label, limit_reason=limit_reason).inc()
        #    - k1_rate_limiter_check_duration_seconds.observe(duration)
        #    - k1_rate_limiter_quota_remaining.labels(dimension=DIMENSION_USER, bucket_key=user_id).set(user_status['tokens_available'])
        #    - k1_rate_limiter_quota_remaining.labels(dimension=DIMENSION_TENANT, bucket_key=tenant_id).set(tenant_status['tokens_available'])
        # 11. Log:
        #    - if allowed:
        #        logger.debug(f"Rate limit allowed: user={user_id}, tenant={tenant_id} (trace: {cognitive_trace_id})")
        #      else:
        #        logger.info(f"Rate limit exceeded: user={user_id}, tenant={tenant_id}, reason={limit_reason} (trace: {cognitive_trace_id})")
        # 12. Return result
        pass

    async def set_user_limit(
        self,
        user_id: str,
        requests_per_minute: int,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Set custom per-user rate limit.

        Args:
            user_id: User identifier
            requests_per_minute: New limit (requests/minute)
            cognitive_trace_id: Trace ID for observability

        Behavior:
            - Store custom limit in memory
            - Create new token bucket with new limit
            - Reset existing bucket to full capacity

        Use Cases:
            - Premium users: 10,000 req/min
            - Regular users: 1,000 req/min
            - Free users: 100 req/min

        Performance:
            - Latency: <10ms P95 (Redis write)

        ADR: ADR-0030 (User Limit Update)
        Assigned to: Issue #L5-10.2.1
        """
        # TODO(@resilience-team): Implement user limit update
        # 1. Store custom limit:
        #    - self._user_limits[user_id] = requests_per_minute
        # 2. Create new bucket:
        #    - refill_rate = requests_per_minute / 60.0
        #    - burst_capacity = int(requests_per_minute * 0.1)  # 10% burst
        #    - self._user_buckets[user_id] = TokenBucket(
        #        redis_client=self._redis,
        #        bucket_key=f"user:{user_id}",
        #        capacity=burst_capacity,
        #        refill_rate_per_second=refill_rate,
        #        enable_rate_limiting=self._enable_rate_limiting,
        #      )
        # 3. Reset bucket:
        #    - await self._user_buckets[user_id].reset(cognitive_trace_id)
        # 4. Log:
        #    - logger.info(f"User limit updated: {user_id} → {requests_per_minute} req/min (trace: {cognitive_trace_id})")
        pass

    async def set_tenant_limit(
        self,
        tenant_id: str,
        requests_per_minute: int,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Set custom per-tenant rate limit.

        Args:
            tenant_id: Tenant identifier
            requests_per_minute: New limit (requests/minute)
            cognitive_trace_id: Trace ID for observability

        Behavior:
            - Store custom limit in memory
            - Create new token bucket with new limit
            - Reset existing bucket to full capacity

        Performance:
            - Latency: <10ms P95 (Redis write)

        ADR: ADR-0030 (Tenant Limit Update)
        Assigned to: Issue #L5-10.2.1
        """
        # TODO(@resilience-team): Implement tenant limit update
        # 1. Store custom limit:
        #    - self._tenant_limits[tenant_id] = requests_per_minute
        # 2. Create new bucket:
        #    - refill_rate = requests_per_minute / 60.0
        #    - burst_capacity = int(requests_per_minute * 0.1)  # 10% burst
        #    - self._tenant_buckets[tenant_id] = TokenBucket(
        #        redis_client=self._redis,
        #        bucket_key=f"tenant:{tenant_id}",
        #        capacity=burst_capacity,
        #        refill_rate_per_second=refill_rate,
        #        enable_rate_limiting=self._enable_rate_limiting,
        #      )
        # 3. Reset bucket:
        #    - await self._tenant_buckets[tenant_id].reset(cognitive_trace_id)
        # 4. Log:
        #    - logger.info(f"Tenant limit updated: {tenant_id} → {requests_per_minute} req/min (trace: {cognitive_trace_id})")
        pass

    async def get_quota_status(
        self,
        user_id: str,
        tenant_id: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get quota status for user/tenant.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            cognitive_trace_id: Trace ID for observability

        Returns:
            {
                "user_limit_per_minute": int,  # User's limit
                "user_tokens_available": float,  # User tokens remaining
                "user_reset_in_seconds": float,  # User quota reset time
                "tenant_limit_per_minute": int,  # Tenant's limit
                "tenant_tokens_available": float,  # Tenant tokens remaining
                "tenant_reset_in_seconds": float,  # Tenant quota reset time
                "effective_limit_per_minute": int,  # min(user, tenant)
                "effective_tokens_available": float,  # min(user, tenant)
                "feature_flag_enabled": bool,  # ENABLE_RATE_LIMITING state
            }

        Performance:
            - Latency: <5ms P95 (2 token bucket status reads)

        Use Cases:
            - API response headers: X-RateLimit-Remaining, X-RateLimit-Reset
            - UI display: "You have 95/100 requests remaining"
            - Monitoring: Track quota usage trends

        ADR: ADR-0030 (Quota Status)
        Assigned to: Issue #L5-10.2.1
        """
        # TODO(@resilience-team): Implement quota status retrieval
        # 1. Get token buckets:
        #    - user_bucket = self._get_user_bucket(user_id)
        #    - tenant_bucket = self._get_tenant_bucket(tenant_id)
        # 2. Get bucket status:
        #    - try:
        #        user_status = await user_bucket.get_status(cognitive_trace_id)
        #        tenant_status = await tenant_bucket.get_status(cognitive_trace_id)
        #      except Exception as e:
        #        logger.error(f"Quota status error: {e} (trace: {cognitive_trace_id})")
        #        return {}  # Return empty dict on error
        # 3. Calculate effective limit:
        #    - effective_limit = min(user_status['requests_per_minute'], tenant_status['requests_per_minute'])
        #    - effective_tokens = min(user_status['tokens_available'], tenant_status['tokens_available'])
        # 4. Build status dict:
        #    - return {
        #        "user_limit_per_minute": int(user_status['requests_per_minute']),
        #        "user_tokens_available": user_status['tokens_available'],
        #        "user_reset_in_seconds": user_status['reset_in_seconds'],
        #        "tenant_limit_per_minute": int(tenant_status['requests_per_minute']),
        #        "tenant_tokens_available": tenant_status['tokens_available'],
        #        "tenant_reset_in_seconds": tenant_status['reset_in_seconds'],
        #        "effective_limit_per_minute": effective_limit,
        #        "effective_tokens_available": effective_tokens,
        #        "feature_flag_enabled": self._enable_rate_limiting,
        #      }
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get rate limiting statistics (local counters).

        Returns:
            {
                "total_requests": int,
                "total_allowed": int,
                "total_rejected": int,
                "total_rejected_user": int,
                "total_rejected_tenant": int,
                "feature_flag_bypasses": int,
                "allow_rate_pct": float,
                "reject_rate_pct": float,
                "user_reject_rate_pct": float,
                "tenant_reject_rate_pct": float,
                "feature_flag_enabled": bool,
            }

        Performance:
            - Latency: <1ms (local counters)

        ADR: ADR-0030 (Rate Limiter Statistics)
        Assigned to: Issue #L5-10.2.1
        """
        # TODO(@resilience-team): Implement statistics collection
        # 1. Calculate totals:
        #    - total_rejected = self._total_rejected_user + self._total_rejected_tenant
        # 2. Calculate rates:
        #    - allow_rate = (self._total_allowed / self._total_requests * 100) if self._total_requests > 0 else 0
        #    - reject_rate = (total_rejected / self._total_requests * 100) if self._total_requests > 0 else 0
        #    - user_reject_rate = (self._total_rejected_user / self._total_requests * 100) if self._total_requests > 0 else 0
        #    - tenant_reject_rate = (self._total_rejected_tenant / self._total_requests * 100) if self._total_requests > 0 else 0
        # 3. Build statistics dict:
        #    - return {
        #        "total_requests": self._total_requests,
        #        "total_allowed": self._total_allowed,
        #        "total_rejected": total_rejected,
        #        "total_rejected_user": self._total_rejected_user,
        #        "total_rejected_tenant": self._total_rejected_tenant,
        #        "feature_flag_bypasses": self._feature_flag_bypasses,
        #        "allow_rate_pct": allow_rate,
        #        "reject_rate_pct": reject_rate,
        #        "user_reject_rate_pct": user_reject_rate,
        #        "tenant_reject_rate_pct": tenant_reject_rate,
        #        "feature_flag_enabled": self._enable_rate_limiting,
        #      }
        pass

    def _get_user_bucket(self, user_id: str) -> Any:  # TODO: Type hint TokenBucket
        """
        Get or create user token bucket (internal).

        Args:
            user_id: User identifier

        Returns:
            TokenBucket for user

        ADR: ADR-0030 (User Bucket Retrieval)
        Assigned to: Issue #L5-10.2.1
        """
        # TODO(@resilience-team): Implement user bucket retrieval
        # 1. Check cache:
        #    - if user_id in self._user_buckets:
        #        return self._user_buckets[user_id]
        # 2. Get limit:
        #    - limit = self._user_limits.get(user_id, self._default_user_limit)
        # 3. Create bucket:
        #    - refill_rate = limit / 60.0
        #    - burst_capacity = int(limit * 0.1)  # 10% burst
        #    - bucket = TokenBucket(
        #        redis_client=self._redis,
        #        bucket_key=f"user:{user_id}",
        #        capacity=burst_capacity,
        #        refill_rate_per_second=refill_rate,
        #        enable_rate_limiting=self._enable_rate_limiting,
        #      )
        # 4. Cache bucket:
        #    - self._user_buckets[user_id] = bucket
        # 5. Return bucket
        pass

    def _get_tenant_bucket(self, tenant_id: str) -> Any:  # TODO: Type hint TokenBucket
        """
        Get or create tenant token bucket (internal).

        Args:
            tenant_id: Tenant identifier

        Returns:
            TokenBucket for tenant

        ADR: ADR-0030 (Tenant Bucket Retrieval)
        Assigned to: Issue #L5-10.2.1
        """
        # TODO(@resilience-team): Implement tenant bucket retrieval
        # 1. Check cache:
        #    - if tenant_id in self._tenant_buckets:
        #        return self._tenant_buckets[tenant_id]
        # 2. Get limit:
        #    - limit = self._tenant_limits.get(tenant_id, self._default_tenant_limit)
        # 3. Create bucket:
        #    - refill_rate = limit / 60.0
        #    - burst_capacity = int(limit * 0.1)  # 10% burst
        #    - bucket = TokenBucket(
        #        redis_client=self._redis,
        #        bucket_key=f"tenant:{tenant_id}",
        #        capacity=burst_capacity,
        #        refill_rate_per_second=refill_rate,
        #        enable_rate_limiting=self._enable_rate_limiting,
        #      )
        # 4. Cache bucket:
        #    - self._tenant_buckets[tenant_id] = bucket
        # 5. Return bucket
        pass


# =============================================================================
# SECTION 4: MODULE EXPORTS
# =============================================================================

__all__ = [
    "RateLimiter",
    "DEFAULT_ENABLE_RATE_LIMITING",
    "DEFAULT_USER_LIMIT_PER_MINUTE",
    "DEFAULT_TENANT_LIMIT_PER_MINUTE",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Prometheus Metrics Exported:
#
# Counters:
#   - k1_rate_limiter_requests_total{result, limit_reason} (allowed/rejected_user/rejected_tenant/feature_flag_bypass)
#   - k1_rate_limiter_feature_flag_bypasses_total (feature flag OFF bypasses)
#
# Histograms:
#   - k1_rate_limiter_check_duration_seconds (check_rate_limit() latency)
#
# Gauges:
#   - k1_rate_limiter_quota_remaining{dimension, bucket_key} (user/tenant tokens remaining)
#
# Example Prometheus Queries:
#   - Request rate: rate(k1_rate_limiter_requests_total{result="allowed"}[5m])
#   - User rejection rate: rate(k1_rate_limiter_requests_total{result="rejected_user"}[5m])
#   - Tenant rejection rate: rate(k1_rate_limiter_requests_total{result="rejected_tenant"}[5m])
#   - Feature flag bypasses: rate(k1_rate_limiter_feature_flag_bypasses_total[5m])
#   - Check P95 latency: histogram_quantile(0.95, k1_rate_limiter_check_duration_seconds_bucket)
#   - User quota remaining: k1_rate_limiter_quota_remaining{dimension="user", bucket_key="alice"}
#
# Alert Rules:
#   - name: HighUserRateLimitRejections
#     expr: rate(k1_rate_limiter_requests_total{result="rejected_user"}[5m]) > 50
#     for: 5m
#     labels:
#       severity: warning
#     annotations:
#       summary: "High user-level rate limit rejections (users hitting quotas)"
#
#   - name: HighTenantRateLimitRejections
#     expr: rate(k1_rate_limiter_requests_total{result="rejected_tenant"}[5m]) > 100
#     for: 5m
#     labels:
#       severity: warning
#     annotations:
#       summary: "High tenant-level rate limit rejections (tenants hitting quotas)"
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/rate_limiting/test_rate_limiter.py
#   - Test user quota enforcement (allowed → rejected_user)
#   - Test tenant quota enforcement (allowed → rejected_tenant)
#   - Test hierarchical enforcement (stricter limit applies)
#   - Test dynamic limit adjustments (set_user_limit, set_tenant_limit)
#   - Test feature flag bypass (ENABLE_RATE_LIMITING=False → all allowed)
#   - Test graceful degradation (Redis down → fail open)
#   - Test quota status retrieval (user/tenant tokens remaining)
#   - Test statistics collection (allow/reject rates)
#
# No simulation code allowed:
#   - Use real TokenBucket with ward fixtures
#   - Mock Redis client for testing
#   - Integration tests > unit tests
#
# =============================================================================
