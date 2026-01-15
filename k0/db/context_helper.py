"""Database context helpers for Row-Level Security enforcement.

Provides functions to set application-level context variables that
RLS policies use for tenant/space isolation.

Dossier Reference: Section 14.11 Learning Data Isolation
Related Issues: 6.3.1-6.3.4 RLS Policy Implementation

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator, Optional

if TYPE_CHECKING:
    from asyncpg import Connection
    from asyncpg.transaction import Transaction

    from k0.pipelines.p03.context import P03CycleContext


async def set_space_context(
    conn: "Connection",
    space_id: str,
) -> None:
    """Set the application-level space context for RLS policies.

    This sets the PostgreSQL session variable 'app.current_space_id' which
    is used by RLS policies on tables like st_learned_weights,
    st_consolidation_audit, st_pruned_entities, st_decay_feedback.

    Args:
        conn: Active asyncpg connection
        space_id: The space ID to set for isolation

    Usage:
        async with connection_scope() as conn:
            await set_space_context(conn, "space_123")
            # Now RLS policies will filter to space_123
            rows = await conn.fetch("SELECT * FROM st_learned_weights")
    """
    await conn.execute(
        "SELECT set_config('app.current_space_id', $1, false)",
        space_id,
    )


async def set_tenant_context(
    conn: "Connection",
    tenant_id: str,
) -> None:
    """Set the application-level tenant context for RLS policies.

    This sets the PostgreSQL session variable 'app.current_tenant_id' which
    can be used by tenant-level RLS policies.

    Args:
        conn: Active asyncpg connection
        tenant_id: The tenant ID to set for isolation
    """
    await conn.execute(
        "SELECT set_config('app.current_tenant_id', $1, false)",
        tenant_id,
    )


async def set_user_context(
    conn: "Connection",
    user_id: str,
) -> None:
    """Set the application-level user context for RLS policies.

    This sets the PostgreSQL session variable 'app.current_user_id' which
    is used by user-level RLS policies (e.g., st_pruned_entities).

    Args:
        conn: Active asyncpg connection
        user_id: The user ID to set for isolation
    """
    await conn.execute(
        "SELECT set_config('app.current_user_id', $1, false)",
        user_id,
    )


async def set_full_context(
    conn: "Connection",
    space_id: str,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> None:
    """Set all application-level context variables for RLS policies.

    Convenience function to set space, tenant, and optionally user context
    in a single call.

    Args:
        conn: Active asyncpg connection
        space_id: The space ID to set for isolation
        tenant_id: The tenant ID to set for isolation
        user_id: Optional user ID to set for isolation
    """
    await set_space_context(conn, space_id)
    await set_tenant_context(conn, tenant_id)
    if user_id is not None:
        await set_user_context(conn, user_id)


async def clear_context(conn: "Connection") -> None:
    """Clear all application-level context variables.

    Resets all RLS context variables to their default empty state.
    Useful for testing or when switching contexts.

    Args:
        conn: Active asyncpg connection
    """
    await conn.execute("RESET app.current_space_id")
    await conn.execute("RESET app.current_tenant_id")
    await conn.execute("RESET app.current_user_id")


async def get_current_space_id(conn: "Connection") -> Optional[str]:
    """Get the currently set space ID from connection context.

    Args:
        conn: Active asyncpg connection

    Returns:
        The current space_id or None if not set
    """
    result = await conn.fetchval("SELECT current_setting('app.current_space_id', true)")
    return result if result else None


async def get_current_tenant_id(conn: "Connection") -> Optional[str]:
    """Get the currently set tenant ID from connection context.

    Args:
        conn: Active asyncpg connection

    Returns:
        The current tenant_id or None if not set
    """
    result = await conn.fetchval("SELECT current_setting('app.current_tenant_id', true)")
    return result if result else None


async def get_current_user_id(conn: "Connection") -> Optional[str]:
    """Get the currently set user ID from connection context.

    Args:
        conn: Active asyncpg connection

    Returns:
        The current user_id or None if not set
    """
    result = await conn.fetchval("SELECT current_setting('app.current_user_id', true)")
    return result if result else None


@asynccontextmanager
async def isolation_scope(
    conn: "Connection",
    space_id: str,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> AsyncIterator["Connection"]:
    """Context manager for RLS-scoped database operations.

    Sets all context variables on entry and clears them on exit.
    Ensures context is properly cleaned up even on exception.

    Args:
        conn: Active asyncpg connection
        space_id: The space ID for isolation
        tenant_id: The tenant ID for isolation
        user_id: Optional user ID for isolation

    Yields:
        The same connection with context set

    Usage:
        async with connection_scope() as conn:
            async with isolation_scope(conn, "space_123", "tenant_456") as scoped_conn:
                # Queries here are filtered by RLS to space_123
                rows = await scoped_conn.fetch("SELECT * FROM st_learned_weights")
            # Context is cleared after exiting
    """
    try:
        await set_full_context(conn, space_id, tenant_id, user_id)
        yield conn
    finally:
        await clear_context(conn)


@asynccontextmanager
async def space_isolation_scope(
    conn: "Connection",
    space_id: str,
) -> AsyncIterator["Connection"]:
    """Lightweight context manager for space-only isolation.

    Sets only the space context, suitable for most RLS policies that
    use space_id isolation (st_learned_weights, st_consolidation_audit, etc.)

    Args:
        conn: Active asyncpg connection
        space_id: The space ID for isolation

    Yields:
        The same connection with space context set

    Usage:
        async with connection_scope() as conn:
            async with space_isolation_scope(conn, "space_123") as scoped_conn:
                rows = await scoped_conn.fetch("SELECT * FROM st_learned_weights")
    """
    try:
        await set_space_context(conn, space_id)
        yield conn
    finally:
        await conn.execute("RESET app.current_space_id")


# =============================================================================
# P03-Specific Context Helpers (Issue 6.3.5)
# =============================================================================


async def set_local_space_context(
    conn: "Connection",
    space_id: str,
) -> None:
    """Set transaction-local space context for RLS policies.

    Uses SET LOCAL which is automatically cleared at transaction end.
    Preferred over session-level set_space_context when using transactions.

    Args:
        conn: Active asyncpg connection (must be in a transaction)
        space_id: The space ID to set for isolation
    """
    await conn.execute(
        "SET LOCAL app.current_space_id = $1",
        space_id,
    )


async def set_local_tenant_context(
    conn: "Connection",
    tenant_id: str,
) -> None:
    """Set transaction-local tenant context for RLS policies.

    Uses SET LOCAL which is automatically cleared at transaction end.

    Args:
        conn: Active asyncpg connection (must be in a transaction)
        tenant_id: The tenant ID to set for isolation
    """
    await conn.execute(
        "SET LOCAL app.current_tenant_id = $1",
        tenant_id,
    )


async def set_local_full_context(
    conn: "Connection",
    space_id: str,
    tenant_id: str,
) -> None:
    """Set transaction-local context for both space and tenant.

    Uses SET LOCAL which is automatically cleared at transaction end.

    Args:
        conn: Active asyncpg connection (must be in a transaction)
        space_id: The space ID to set for isolation
        tenant_id: The tenant ID to set for isolation
    """
    await set_local_space_context(conn, space_id)
    await set_local_tenant_context(conn, tenant_id)


# =============================================================================
# P03 Isolation Scope Context Managers (Issue 6.3.5)
# =============================================================================


@asynccontextmanager
async def p03_isolation_scope(
    ctx: "P03CycleContext",
) -> AsyncIterator[tuple["Connection", "Transaction"]]:
    """
    P03-aware transaction scope with RLS context.

    Automatically sets space_id and tenant_id from P03CycleContext
    for Row-Level Security enforcement.

    Uses SET LOCAL for transaction-scoped context that is automatically
    cleared when the transaction ends.

    Args:
        ctx: P03CycleContext with space_id and tenant_id

    Yields:
        Tuple of (asyncpg.Connection, asyncpg.Transaction) with RLS context set

    Usage:
        async with p03_isolation_scope(envelope.context) as (conn, tx):
            # All queries filtered by space_id automatically
            rows = await conn.fetch("SELECT * FROM st_learned_weights")
    """
    from k0.db.pool import get_pool

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction() as tx:
            # Set RLS context from P03CycleContext using transaction-local settings
            await conn.execute(
                "SET LOCAL app.current_space_id = $1",
                ctx.space_id,
            )
            await conn.execute(
                "SET LOCAL app.current_tenant_id = $1",
                ctx.tenant_id,
            )
            yield conn, tx


@asynccontextmanager
async def isolated_read_scope(
    ctx: "P03CycleContext",
) -> AsyncIterator["Connection"]:
    """
    P03-aware read-only scope with RLS context.

    Sets RLS context and read-only mode for safe queries.
    The read-only transaction prevents any mutations.

    Args:
        ctx: P03CycleContext with space_id and tenant_id

    Yields:
        asyncpg.Connection with RLS context set in read-only mode

    Usage:
        async with isolated_read_scope(envelope.context) as conn:
            # Read-only queries filtered by RLS
            rows = await conn.fetch("SELECT * FROM st_learned_weights")
    """
    from k0.db.pool import get_pool

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            await conn.execute(
                "SET LOCAL app.current_space_id = $1",
                ctx.space_id,
            )
            await conn.execute(
                "SET LOCAL app.current_tenant_id = $1",
                ctx.tenant_id,
            )
            yield conn
