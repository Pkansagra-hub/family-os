"""PostgreSQL Advisory Lock Service for K0 kernel.

Part of Milestone 1.3 - Issue 1.3.4: Single-writer-per-space guard.

This module provides PostgreSQL advisory locks for distributed coordination:
- Session-scoped locks: persist until connection ends or explicit unlock
- Non-blocking try_lock: returns immediately
- Blocking lock with timeout: waits up to N ms
- Lock status introspection via pg_locks

Used by P03 for single-writer-per-space semantics during consolidation cycles.

References:
    - Dossier 4.10.2: K0 Enhancement: Advisory Lock Service
    - Dossier 4.10.6: P03 Implementation with PostgreSQL
    - PostgreSQL docs: https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from asyncpg import Connection

from .pool import get_pool

logger = logging.getLogger(__name__)

UTC = timezone.utc  # Add this line
# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True)
class LockResult:
    """Result of a lock acquisition attempt.

    Attributes:
        acquired: True if lock was successfully acquired
        lock_key: The original string lock key
        lock_id: The bigint hash used by PostgreSQL
        holder_id: Identifier of the lock holder (if acquired)
        error: Error message if acquisition failed
        acquired_at: Timestamp when lock was acquired (if acquired)
    """

    acquired: bool
    lock_key: str
    lock_id: int
    holder_id: str | None = None
    error: str | None = None
    acquired_at: datetime | None = None


@dataclass(frozen=True)
class LockInfo:
    """Information about a held lock.

    Attributes:
        lock_key: The original string lock key
        lock_id: The bigint hash used by PostgreSQL
        holder_id: Identifier of the lock holder
        acquired_at: When the lock was acquired
    """

    lock_key: str
    lock_id: int
    holder_id: str
    acquired_at: datetime


@dataclass
class LockState:
    """Internal state for tracking held locks on this connection.

    Used to track local lock state for proper cleanup.
    """

    lock_key: str
    lock_id: int
    holder_id: str
    acquired_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ============================================================================
# Protocol Definition
# ============================================================================


@runtime_checkable
class AdvisoryLockServiceProtocol(Protocol):
    """Protocol for advisory lock services.

    Defines the interface that all lock service implementations must follow.
    Enables dependency injection and testing with mock implementations.
    """

    async def acquire(
        self,
        lock_key: str,
        holder_id: str,
        *,
        blocking: bool = False,
        timeout_ms: int | None = None,
    ) -> LockResult:
        """Acquire an advisory lock.

        Args:
            lock_key: String lock key (e.g., "P03:tenant_1:space_1")
            holder_id: Identifier for the lock holder
            blocking: If True, wait for lock. If False, return immediately.
            timeout_ms: Timeout in milliseconds for blocking acquire

        Returns:
            LockResult with acquisition status
        """
        ...

    async def release(self, lock_key: str, holder_id: str) -> bool:
        """Release a held lock.

        Args:
            lock_key: String lock key to release
            holder_id: Identifier of the holder releasing the lock

        Returns:
            True if lock was released, False otherwise
        """
        ...

    async def is_held_globally(self, lock_key: str) -> bool:
        """Check if a lock is held by any connection.

        Args:
            lock_key: String lock key to check

        Returns:
            True if lock is held by any connection globally
        """
        ...


# ============================================================================
# Lock Key Utilities
# ============================================================================


def hash_lock_key(lock_key: str) -> int:
    """Convert string lock key to bigint for pg_advisory_lock.

    Uses first 8 bytes of SHA256 as a signed 64-bit integer.
    This ensures consistent hashing across all nodes in the cluster.

    Args:
        lock_key: String lock key (e.g., "P03:tenant_1:space_1")

    Returns:
        Signed 64-bit integer for use with pg_advisory_lock

    Example:
        >>> hash_lock_key("P03:tenant_1:space_1")
        -1234567890123456789  # Example signed bigint
    """
    h = hashlib.sha256(lock_key.encode()).digest()[:8]
    return int.from_bytes(h, byteorder="big", signed=True)


def make_p03_lock_key(tenant_id: str, space_id: str) -> str:
    """Create a P03-specific lock key.

    Args:
        tenant_id: Tenant identifier
        space_id: Space identifier

    Returns:
        Lock key in format "P03:{tenant_id}:{space_id}"

    Example:
        >>> make_p03_lock_key("tenant_1", "space_abc")
        "P03:tenant_1:space_abc"
    """
    return f"P03:{tenant_id}:{space_id}"


# ============================================================================
# PostgreSQL Advisory Lock Service
# ============================================================================


class AdvisoryLockService:
    """PostgreSQL-based advisory lock service.

    Provides distributed locking using PostgreSQL session-scoped advisory locks.
    Locks are automatically released when the database connection ends.

    Design decisions:
        - Session locks (not transaction locks) for long-running cycles
        - Non-blocking try_lock for skip semantics
        - Blocking with timeout for queue semantics
        - Local state tracking for holder verification

    Usage:
        service = get_advisory_lock_service()
        result = await service.acquire("P03:t1:s1", "node_1")
        if result.acquired:
            try:
                # Do work
                pass
            finally:
                await service.release("P03:t1:s1", "node_1")
    """

    def __init__(self) -> None:
        """Initialize the lock service.

        Does not create any connections - uses the global pool.
        """
        self._held_locks: dict[str, LockState] = {}
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        lock_key: str,
        holder_id: str,
        *,
        blocking: bool = False,
        timeout_ms: int | None = None,
    ) -> LockResult:
        """Acquire an advisory lock.

        Uses PostgreSQL pg_try_advisory_lock() for non-blocking or
        pg_advisory_lock() with statement_timeout for blocking.

        Args:
            lock_key: String lock key (e.g., "P03:tenant_1:space_1")
            holder_id: Identifier for the lock holder (e.g., node ID)
            blocking: If True, wait for lock. If False, return immediately.
            timeout_ms: Timeout in milliseconds for blocking acquire (default: 30000)

        Returns:
            LockResult with:
            - acquired: True if lock was acquired
            - lock_key: The original string key
            - lock_id: The bigint hash
            - holder_id: The holder if acquired
            - error: Error message if failed
            - acquired_at: Timestamp if acquired
        """
        lock_id = hash_lock_key(lock_key)
        effective_timeout = timeout_ms if timeout_ms is not None else 30000

        async with self._lock:
            # Check if we already hold this lock
            if lock_key in self._held_locks:
                existing = self._held_locks[lock_key]
                if existing.holder_id == holder_id:
                    # Same holder - return success (reentrant)
                    logger.debug(
                        f"Lock reentry: {lock_key} already held by {holder_id}",
                        extra={"lock_key": lock_key, "holder_id": holder_id},
                    )
                    return LockResult(
                        acquired=True,
                        lock_key=lock_key,
                        lock_id=lock_id,
                        holder_id=holder_id,
                        acquired_at=existing.acquired_at,
                    )
                # Different holder - lock is held locally
                return LockResult(
                    acquired=False,
                    lock_key=lock_key,
                    lock_id=lock_id,
                    holder_id=None,
                    error=f"Lock held by {existing.holder_id}",
                )

        pool = get_pool()
        now = datetime.now(UTC)

        try:
            async with pool.acquire() as conn:
                if blocking:
                    acquired = await self._acquire_blocking(conn, lock_id, effective_timeout)
                else:
                    acquired = await self._acquire_nonblocking(conn, lock_id)

                if acquired:
                    async with self._lock:
                        self._held_locks[lock_key] = LockState(
                            lock_key=lock_key,
                            lock_id=lock_id,
                            holder_id=holder_id,
                            acquired_at=now,
                        )
                    logger.info(
                        f"Advisory lock acquired: {lock_key}",
                        extra={
                            "lock_key": lock_key,
                            "lock_id": lock_id,
                            "holder_id": holder_id,
                            "blocking": blocking,
                        },
                    )
                    return LockResult(
                        acquired=True,
                        lock_key=lock_key,
                        lock_id=lock_id,
                        holder_id=holder_id,
                        acquired_at=now,
                    )
                else:
                    logger.debug(
                        f"Advisory lock not acquired: {lock_key}",
                        extra={
                            "lock_key": lock_key,
                            "lock_id": lock_id,
                            "blocking": blocking,
                        },
                    )
                    return LockResult(
                        acquired=False,
                        lock_key=lock_key,
                        lock_id=lock_id,
                        holder_id=None,
                        error="lock_held" if not blocking else "timeout",
                    )

        except Exception as e:
            logger.error(
                f"Advisory lock acquire failed: {lock_key} - {e}",
                extra={
                    "lock_key": lock_key,
                    "lock_id": lock_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            return LockResult(
                acquired=False,
                lock_key=lock_key,
                lock_id=lock_id,
                holder_id=None,
                error=str(e),
            )

    async def _acquire_nonblocking(self, conn: Connection, lock_id: int) -> bool:
        """Try to acquire lock without waiting.

        Args:
            conn: Database connection
            lock_id: Bigint lock ID

        Returns:
            True if lock was acquired
        """
        result = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)",
            lock_id,
        )
        return bool(result)

    async def _acquire_blocking(self, conn: Connection, lock_id: int, timeout_ms: int) -> bool:
        """Acquire lock with timeout.

        Uses statement_timeout to limit wait time.

        Args:
            conn: Database connection
            lock_id: Bigint lock ID
            timeout_ms: Maximum wait time in milliseconds

        Returns:
            True if lock was acquired within timeout
        """
        import asyncpg

        try:
            # Set statement timeout for this operation only
            await conn.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
            await conn.execute("SELECT pg_advisory_lock($1)", lock_id)
            return True
        except asyncpg.QueryCanceledError:
            # Timeout exceeded
            return False
        finally:
            # Reset statement timeout
            await conn.execute("RESET statement_timeout")

    async def release(self, lock_key: str, holder_id: str) -> bool:
        """Release a held lock.

        Only releases if the lock is held by the specified holder.

        Args:
            lock_key: String lock key to release
            holder_id: Identifier of the holder releasing the lock

        Returns:
            True if lock was released, False if not held or wrong holder
        """
        lock_id = hash_lock_key(lock_key)

        async with self._lock:
            # Check if we hold this lock
            if lock_key not in self._held_locks:
                logger.warning(
                    f"Release failed: lock not held locally: {lock_key}",
                    extra={"lock_key": lock_key, "holder_id": holder_id},
                )
                return False

            held = self._held_locks[lock_key]
            if held.holder_id != holder_id:
                logger.warning(
                    f"Release failed: wrong holder: {lock_key} "
                    f"(held by {held.holder_id}, release attempted by {holder_id})",
                    extra={
                        "lock_key": lock_key,
                        "holder_id": holder_id,
                        "actual_holder": held.holder_id,
                    },
                )
                return False

        pool = get_pool()

        try:
            async with pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT pg_advisory_unlock($1)",
                    lock_id,
                )
                released = bool(result)

                if released:
                    async with self._lock:
                        self._held_locks.pop(lock_key, None)
                    logger.info(
                        f"Advisory lock released: {lock_key}",
                        extra={
                            "lock_key": lock_key,
                            "lock_id": lock_id,
                            "holder_id": holder_id,
                        },
                    )
                else:
                    logger.warning(
                        f"PostgreSQL unlock returned false: {lock_key}",
                        extra={"lock_key": lock_key, "lock_id": lock_id},
                    )

                return released

        except Exception as e:
            logger.error(
                f"Advisory lock release failed: {lock_key} - {e}",
                extra={
                    "lock_key": lock_key,
                    "lock_id": lock_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            return False

    async def is_held_globally(self, lock_key: str) -> bool:
        """Check if a lock is held by any connection globally.

        Queries pg_locks to check lock status across all connections.

        Args:
            lock_key: String lock key to check

        Returns:
            True if lock is held by any connection
        """
        lock_id = hash_lock_key(lock_key)
        pool = get_pool()

        try:
            async with pool.acquire() as conn:
                # Query pg_locks for advisory locks
                # objid contains the lock key (for single-bigint locks)
                result = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_locks
                        WHERE locktype = 'advisory'
                          AND objid = $1
                          AND granted = true
                    )
                    """,
                    lock_id & 0xFFFFFFFF,  # Lower 32 bits for objid
                )
                return bool(result)

        except Exception as e:
            logger.error(
                f"Advisory lock check failed: {lock_key} - {e}",
                extra={
                    "lock_key": lock_key,
                    "lock_id": lock_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Fail-safe: assume held if we can't check
            return True

    def get_held_locks(self) -> dict[str, LockInfo]:
        """Get all locks held by this service instance.

        Returns:
            Dictionary of lock_key -> LockInfo for all held locks
        """
        return {
            key: LockInfo(
                lock_key=state.lock_key,
                lock_id=state.lock_id,
                holder_id=state.holder_id,
                acquired_at=state.acquired_at,
            )
            for key, state in self._held_locks.items()
        }

    async def release_all(self) -> int:
        """Release all locks held by this service instance.

        Used for cleanup on shutdown or error recovery.

        Returns:
            Number of locks released
        """
        released_count = 0
        locks_to_release = list(self._held_locks.items())

        for lock_key, state in locks_to_release:
            if await self.release(lock_key, state.holder_id):
                released_count += 1

        return released_count


# ============================================================================
# Global Service Singleton
# ============================================================================

_lock_service: AdvisoryLockService | None = None
_service_lock = asyncio.Lock()


async def configure_lock_service() -> None:
    """Initialize the global advisory lock service.

    Thread-safe initialization. Safe to call multiple times.
    """
    global _lock_service
    async with _service_lock:
        if _lock_service is None:
            _lock_service = AdvisoryLockService()
            logger.info("Advisory lock service initialized")


def get_advisory_lock_service() -> AdvisoryLockService:
    """Return the configured lock service or raise if missing.

    Raises:
        RuntimeError: If lock service has not been configured

    Returns:
        The global AdvisoryLockService instance
    """
    if _lock_service is None:
        raise RuntimeError(
            "Advisory lock service has not been configured - " "call configure_lock_service() first"
        )
    return _lock_service


async def reset_lock_service() -> None:
    """Reset the lock service (for testing).

    Releases all held locks and clears the singleton.
    """
    global _lock_service
    async with _service_lock:
        if _lock_service is not None:
            await _lock_service.release_all()
            _lock_service = None
            logger.info("Advisory lock service reset")


__all__ = [
    # Data classes
    "LockResult",
    "LockInfo",
    # Protocol
    "AdvisoryLockServiceProtocol",
    # Service
    "AdvisoryLockService",
    # Utilities
    "hash_lock_key",
    "make_p03_lock_key",
    # Factory functions
    "configure_lock_service",
    "get_advisory_lock_service",
    "reset_lock_service",
]
