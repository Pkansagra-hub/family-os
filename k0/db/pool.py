"""asyncpg connection pool for K0 kernel.

Part of Milestone 1.2.1 - Issue 1.2.1.1: Create asyncpg Connection Pool.
Includes Issue 1.2.1.5: pgbouncer compatibility (statement_cache_size=0).

This module provides an async connection pool wrapping asyncpg.Pool with:
- Metrics emission to Prometheus
- pgbouncer transaction-mode compatibility
- Health check support
- Graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator

import asyncpg

if TYPE_CHECKING:
    from k0.config.postgres import PostgresSettings
    from k0.obs.metrics import MetricsExporter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoolStats:
    """Introspection data describing the current pool state."""

    size: int
    free_size: int
    used_size: int
    min_size: int
    max_size: int


class AsyncPgPool:
    """Managed asyncpg connection pool with metrics and health checks.

    This pool wraps asyncpg.Pool with:
    - Prometheus metrics emission (pg_pool_connections_active, pg_pool_saturation_ratio)
    - pgbouncer compatibility (statement_cache_size=0, max_cached_statement_lifetime=0)
    - Connection lifecycle management
    - Health check endpoints

    Usage:
        settings = PostgresSettings()
        pool = AsyncPgPool(settings)
        await pool.initialize()

        async with pool.acquire() as conn:
            result = await conn.fetch("SELECT 1")

        await pool.close()
    """

    def __init__(
        self,
        settings: PostgresSettings,
        *,
        metrics_exporter: MetricsExporter | None = None,
    ) -> None:
        """Initialize pool wrapper (does not create connections yet).

        Args:
            settings: PostgreSQL connection configuration
            metrics_exporter: Optional Prometheus metrics exporter
        """
        self._settings = settings
        self._metrics = metrics_exporter
        self._pool: asyncpg.Pool | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Create the connection pool.

        Creates an asyncpg.Pool with pgbouncer-compatible settings:
        - statement_cache_size=0: Disables prepared statement caching
        - max_cached_statement_lifetime=0: Ensures no statement reuse

        These settings are CRITICAL for pgbouncer transaction mode.
        Without them, you get InvalidSQLStatementNameError when pgbouncer
        reassigns connections between sessions.

        Raises:
            asyncpg.PostgresError: If connection fails
        """
        if self._initialized:
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._settings.dsn,
            min_size=self._settings.min_pool_size,
            max_size=self._settings.max_pool_size,
            command_timeout=self._settings.command_timeout,
            # CRITICAL: Disable prepared statement caching for pgbouncer compatibility
            # Without these settings, pgbouncer transaction mode will fail with:
            # asyncpg.exceptions.InvalidSQLStatementNameError
            statement_cache_size=self._settings.statement_cache_size,
            max_cached_statement_lifetime=0,
            max_inactive_connection_lifetime=self._settings.max_inactive_connection_lifetime,
            server_settings={
                "application_name": "k0_kernel",
                "timezone": "UTC",
            },
        )
        self._initialized = True
        logger.info(
            "PostgreSQL pool initialized",
            extra={
                "dsn": self._settings.dsn_masked,
                "min_size": self._settings.min_pool_size,
                "max_size": self._settings.max_pool_size,
                "statement_cache_size": self._settings.statement_cache_size,
            },
        )

    async def close(self) -> None:
        """Close all connections in the pool.

        Gracefully closes all connections and resets pool state.
        Safe to call multiple times.
        """
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._initialized = False
            logger.info("PostgreSQL pool closed")

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        """Acquire a connection from the pool.

        Yields:
            An asyncpg.Connection that is automatically returned to pool.

        Raises:
            RuntimeError: If pool not initialized

        Example:
            async with pool.acquire() as conn:
                await conn.fetch("SELECT 1")
        """
        if self._pool is None:
            raise RuntimeError("Pool not initialized - call initialize() first")

        async with self._pool.acquire() as conn:
            self._emit_metrics()
            yield conn

    async def execute(self, query: str, *args: Any, timeout: float | None = None) -> str:
        """Execute a query without returning results.

        Args:
            query: SQL query with $1, $2 style placeholders
            *args: Query parameters
            timeout: Query timeout override

        Returns:
            Command status string (e.g., "INSERT 0 1")
        """
        async with self.acquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)

    async def fetch(
        self,
        query: str,
        *args: Any,
        timeout: float | None = None,
    ) -> list[asyncpg.Record]:
        """Execute a query and return all results.

        Args:
            query: SQL query with $1, $2 style placeholders
            *args: Query parameters
            timeout: Query timeout override

        Returns:
            List of Record objects
        """
        async with self.acquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)

    async def fetchrow(
        self,
        query: str,
        *args: Any,
        timeout: float | None = None,
    ) -> asyncpg.Record | None:
        """Execute a query and return first row.

        Args:
            query: SQL query with $1, $2 style placeholders
            *args: Query parameters
            timeout: Query timeout override

        Returns:
            First row as Record, or None if no rows
        """
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)

    async def fetchval(
        self,
        query: str,
        *args: Any,
        column: int = 0,
        timeout: float | None = None,
    ) -> Any:
        """Execute a query and return first column of first row.

        Args:
            query: SQL query with $1, $2 style placeholders
            *args: Query parameters
            column: Column index to return (default 0)
            timeout: Query timeout override

        Returns:
            Value from first column of first row, or None
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args, column=column, timeout=timeout)

    async def executemany(
        self,
        query: str,
        args: list[tuple],
        *,
        timeout: float | None = None,
    ) -> None:
        """Execute a query with multiple parameter sets.

        Args:
            query: SQL query with $1, $2 style placeholders
            args: List of parameter tuples
            timeout: Query timeout override
        """
        async with self.acquire() as conn:
            await conn.executemany(query, args, timeout=timeout)

    async def copy_records_to_table(
        self,
        table_name: str,
        *,
        records: list[tuple],
        columns: tuple[str, ...] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Bulk copy records to a table using COPY protocol.

        Much faster than executemany for large inserts.

        Args:
            table_name: Target table name
            records: List of record tuples
            columns: Optional column names
            timeout: Copy timeout override

        Returns:
            COPY status string
        """
        async with self.acquire() as conn:
            return await conn.copy_records_to_table(
                table_name,
                records=records,
                columns=columns,
                timeout=timeout,
            )

    def stats(self) -> PoolStats:
        """Get current pool statistics.

        Returns:
            PoolStats with size, free_size, used_size, min_size, max_size
        """
        if self._pool is None:
            return PoolStats(0, 0, 0, 0, 0)
        return PoolStats(
            size=self._pool.get_size(),
            free_size=self._pool.get_idle_size(),
            used_size=self._pool.get_size() - self._pool.get_idle_size(),
            min_size=self._pool.get_min_size(),
            max_size=self._pool.get_max_size(),
        )

    async def health_check(self) -> bool:
        """Check if pool can execute queries.

        Returns:
            True if pool is healthy, False otherwise
        """
        if self._pool is None:
            return False
        try:
            async with self.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception:
            logger.exception("PostgreSQL health check failed")
            return False

    def _emit_metrics(self) -> None:
        """Emit pool metrics to Prometheus."""
        if self._metrics is None or self._pool is None:
            return
        stats = self.stats()
        self._metrics.set_gauge("pg_pool_connections_active", float(stats.used_size))
        self._metrics.set_gauge("pg_pool_connections_idle", float(stats.free_size))
        self._metrics.set_gauge("pg_pool_connections_total", float(stats.size))
        self._metrics.set_gauge(
            "pg_pool_saturation_ratio",
            stats.used_size / stats.max_size if stats.max_size > 0 else 0.0,
        )


# Global pool singleton
_pool: AsyncPgPool | None = None
_pool_lock = asyncio.Lock()


async def configure_pool(
    settings: PostgresSettings,
    *,
    metrics_exporter: MetricsExporter | None = None,
) -> None:
    """Initialize the global asyncpg connection pool.

    Thread-safe initialization that closes any existing pool first.

    Args:
        settings: PostgreSQL connection configuration
        metrics_exporter: Optional Prometheus metrics exporter
    """
    global _pool
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
        _pool = AsyncPgPool(settings, metrics_exporter=metrics_exporter)
        await _pool.initialize()


async def shutdown_pool() -> None:
    """Close and discard the global pool.

    Safe to call multiple times.
    """
    global _pool
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
        _pool = None


def get_pool() -> AsyncPgPool:
    """Return the configured pool or raise if missing.

    Raises:
        RuntimeError: If pool has not been configured

    Returns:
        The global AsyncPgPool instance
    """
    if _pool is None:
        raise RuntimeError("Connection pool has not been configured - call configure_pool() first")
    return _pool


__all__ = [
    "AsyncPgPool",
    "PoolStats",
    "configure_pool",
    "get_pool",
    "shutdown_pool",
]
