"""Async connection context managers for K0 kernel.

Part of Milestone 1.2.1 - Issue 1.2.1.2: Create Connection Context Manager.

This module provides async context managers for database connections:
- connection_scope(): Basic pooled connection
- transaction_scope(): Connection with auto-commit/rollback transaction
- read_only_scope(): Read-only connection for query safety
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

from .pool import get_pool

if TYPE_CHECKING:
    from asyncpg import Connection
    from asyncpg.transaction import Transaction


@asynccontextmanager
async def connection_scope() -> AsyncIterator[Connection]:
    """Yield a pooled PostgreSQL connection.

    Replaces the sync SQLite connection_scope() for async operations.
    Connection is automatically returned to pool on exit.

    Usage:
        async with connection_scope() as conn:
            rows = await conn.fetch("SELECT * FROM users")

    Yields:
        asyncpg.Connection from the global pool
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction_scope() -> AsyncIterator[tuple[Connection, Transaction]]:
    """Yield a connection with an active transaction.

    Automatically commits on success, rolls back on exception.
    Replaces the UoW pattern for simple transactional operations.

    Usage:
        async with transaction_scope() as (conn, tx):
            await conn.execute("INSERT INTO users (name) VALUES ($1)", "alice")
            await conn.execute("INSERT INTO audit (action) VALUES ($1)", "user_created")
            # Auto-commits on exit, rolls back on exception

    Yields:
        Tuple of (asyncpg.Connection, asyncpg.Transaction)
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction() as tx:
            yield conn, tx


@asynccontextmanager
async def read_only_scope() -> AsyncIterator[Connection]:
    """Yield a read-only connection for queries.

    Sets transaction mode to READ ONLY for safety.
    Any attempt to modify data will raise an error.
    Ideal for query operations that should never modify data.

    Usage:
        async with read_only_scope() as conn:
            # Safe - only reads allowed
            rows = await conn.fetch("SELECT * FROM users")
            # This would raise: asyncpg.ReadOnlyError
            # await conn.execute("DELETE FROM users")

    Yields:
        asyncpg.Connection in read-only mode
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Start a read-only transaction
        async with conn.transaction(readonly=True):
            yield conn


@asynccontextmanager
async def savepoint_scope(
    conn: Connection,
    name: str | None = None,
) -> AsyncIterator[Transaction]:
    """Create a savepoint within an existing transaction.

    Allows partial rollback within a transaction.
    Savepoint is released on success, rolled back on exception.

    Usage:
        async with transaction_scope() as (conn, tx):
            await conn.execute("INSERT INTO users (name) VALUES ($1)", "alice")

            async with savepoint_scope(conn, "sp1") as sp:
                await conn.execute("INSERT INTO audit (action) VALUES ($1)", "test")
                raise ValueError("Oops")  # Only audit insert is rolled back

            # alice insert is preserved

    Args:
        conn: Active connection with a transaction
        name: Optional savepoint name

    Yields:
        The savepoint Transaction object
    """
    async with conn.transaction(savepoint_name=name) as sp:
        yield sp


__all__ = [
    "connection_scope",
    "read_only_scope",
    "savepoint_scope",
    "transaction_scope",
]
