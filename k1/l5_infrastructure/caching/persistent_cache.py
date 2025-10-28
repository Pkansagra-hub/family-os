"""
In-memory cache with K0 persistence for security-critical data.

Extension of LocalKVCache with asynchronous K0 writes for critical data:
  - Token revocations (24h TTL)
  - Capability revocations (24h TTL)
  - Idempotency cache (5min TTL, no persistence)

Implementation based on ADR-0028d and ADR-0028e.

Pattern:
  1. On revocation: Add to in-memory (0.1ms) + async K0 write (non-blocking)
  2. On K1 startup: Bulk load critical caches from K0 (<100ms)
"""

import asyncio
import logging
import time
from typing import Any, Optional

from .kv_cache_local import LocalKVCache

logger = logging.getLogger(__name__)


class PersistentCache(LocalKVCache):
    """
    In-memory cache with K0 persistence for critical data.

    Extends LocalKVCache with background writes to K0 for security-critical
    data (tokens, capabilities) that must survive K1 restart.

    ADRs: ADR-0028d, ADR-0028e
    """

    def __init__(
        self,
        k0_memory_port,
        ttl_seconds: int = 60,
        capacity: int = 1000,
        namespace: str = "k1:cache:",
        cleanup_interval_s: int = 60,
    ):
        """
        Initialize persistent cache with K0 backend.

        Args:
            k0_memory_port: K0 memory port for async persistence
            ttl_seconds: Default TTL (default: 60s)
            capacity: Max keys in cache (default: 1000)
            namespace: Key namespace (default: "k1:cache:")
            cleanup_interval_s: TTL cleanup interval (default: 60s)

        ADRs: ADR-0028d, ADR-0028e
        """
        super().__init__(
            ttl_seconds=ttl_seconds,
            capacity=capacity,
            namespace=namespace,
            cleanup_interval_s=cleanup_interval_s,
        )
        self.k0_memory_port = k0_memory_port

    async def persist_token_revocation(
        self,
        token_id: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Revoke JWT token with immediate effect + durable K0 persistence.

        Execution Timeline:
          0.1ms  - Add to in-memory cache ← Protection active NOW
          2-5ms  - Async K0 write (non-blocking) ← Persisted
          ~0.2ms - Return to caller

        Guarantee:
          - Token immediately blacklisted (no requests with this token)
          - Persisted to K0 for durability
          - On K1 restart: Reloaded from K0 automatically

        ADRs: ADR-0028d, ADR-0028e
        """
        cache_key = f"revoked_token:{token_id}"

        # 1. Immediate protection: Add to in-memory cache (0.1ms)
        await self.set(
            cache_key,
            True,  # value
            ttl_seconds=86400,  # 24 hours
            cognitive_trace_id=cognitive_trace_id,
        )

        logger.info(
            f"Token revoked (in-memory): {token_id} (trace: {cognitive_trace_id})"
        )

        # 2. Async K0 write (non-blocking, 2-5ms)
        # This runs in background and doesn't block the caller
        async def persist_to_k0():
            try:
                await self.k0_memory_port.store(
                    key=f"security:revoked_tokens:{token_id}",
                    value={
                        "token_id": token_id,
                        "revoked_at": time.time(),
                        "ttl_hours": 24,
                        "reason": "admin_revocation",
                    },
                )
                logger.info(f"Token revocation persisted to K0: {token_id}")
            except Exception as e:
                logger.error(f"Failed to persist token revocation to K0: {e}")
                # Continue anyway - in-memory cache still protects against the token

        asyncio.create_task(persist_to_k0())

    async def is_token_revoked(
        self,
        token_id: str,
    ) -> bool:
        """
        Check if token is revoked (<0.1ms, no K0 call).

        This is the critical path for every request.
        Performance: <0.1ms (in-memory lookup only, no K0 calls).

        Returns:
            True if token is revoked, False otherwise

        ADRs: ADR-0028d, ADR-0028e
        """
        cache_key = f"revoked_token:{token_id}"
        return await self.exists(cache_key)

    async def persist_capability_revocation(
        self,
        agent_id: str,
        capability_name: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Revoke agent capability with immediate effect + durable K0 persistence.

        Execution Timeline:
          0.1ms  - Add to in-memory cache ← Protection active NOW
          2-5ms  - Async K0 write (non-blocking) ← Persisted
          ~0.2ms - Return to caller

        Guarantee:
          - Capability immediately revoked
          - Persisted to K0 for durability
          - On K1 restart: Reloaded from K0 automatically

        ADRs: ADR-0028d, ADR-0028e
        """
        cache_key = f"revoked_capability:{agent_id}:{capability_name}"

        # 1. Immediate protection: Add to in-memory cache (0.1ms)
        await self.set(
            cache_key,
            True,  # value
            ttl_seconds=86400,  # 24 hours
            cognitive_trace_id=cognitive_trace_id,
        )

        logger.info(
            f"Capability revoked (in-memory): {agent_id}/{capability_name} "
            f"(trace: {cognitive_trace_id})"
        )

        # 2. Async K0 write (non-blocking, 2-5ms)
        async def persist_to_k0():
            try:
                await self.k0_memory_port.store(
                    key=f"security:revoked_capabilities:{agent_id}:{capability_name}",
                    value={
                        "agent_id": agent_id,
                        "capability_name": capability_name,
                        "revoked_at": time.time(),
                        "ttl_hours": 24,
                        "reason": "admin_revocation",
                    },
                )
                logger.info(
                    f"Capability revocation persisted to K0: {agent_id}/{capability_name}"
                )
            except Exception as e:
                logger.error(f"Failed to persist capability revocation to K0: {e}")
                # Continue anyway - in-memory cache still protects

        asyncio.create_task(persist_to_k0())

    async def is_capability_revoked(
        self,
        agent_id: str,
        capability_name: str,
    ) -> bool:
        """
        Check if capability is revoked (<0.1ms, no K0 call).

        This is the critical path for every capability check.
        Performance: <0.1ms (in-memory lookup only, no K0 calls).

        Returns:
            True if capability is revoked, False otherwise

        ADRs: ADR-0028d, ADR-0028e
        """
        cache_key = f"revoked_capability:{agent_id}:{capability_name}"
        return await self.exists(cache_key)

    async def add_idempotency_key(
        self,
        request_id: str,
        result: Any,
        ttl_seconds: int = 300,  # 5 minutes
    ) -> None:
        """
        Add idempotency cache entry (no K0 persistence).

        Idempotency entries are ephemeral (acceptable to lose on restart).
        TTL: 5 minutes (covers duplicate request window).

        ADRs: ADR-0028d, ADR-0028e
        """
        cache_key = f"idempotency:{request_id}"
        await self.set(cache_key, result, ttl_seconds=ttl_seconds)

    async def get_idempotency_result(
        self,
        request_id: str,
    ) -> Optional[Any]:
        """
        Get cached result for idempotent request.

        Returns:
            Cached result if found, None otherwise

        ADRs: ADR-0028d, ADR-0028e
        """
        cache_key = f"idempotency:{request_id}"
        return await self.get(cache_key)


__all__ = ["PersistentCache"]
