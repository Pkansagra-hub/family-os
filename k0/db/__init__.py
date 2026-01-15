"""K0 Database Layer for PostgreSQL.

Part of Milestone 1.2: Core Database Layer.

This package provides the async database layer for K0 kernel,
replacing the SQLite-based storage with PostgreSQL via asyncpg.

Modules:
    pool: AsyncPgPool connection pool with pgbouncer compatibility
    connection: Async context managers for database connections
    types: Type converters for PostgreSQL
    query: Query builder utilities
    params: Parameter binding utilities

Quick Start:
    from k0.config.postgres import get_postgres_settings
    from k0.db import configure_pool, connection_scope

    # Initialize pool at startup
    settings = get_postgres_settings()
    await configure_pool(settings)

    # Use connection scope for queries
    async with connection_scope() as conn:
        rows = await conn.fetch("SELECT * FROM users")

    # Use transaction scope for writes
    async with transaction_scope() as (conn, tx):
        await conn.execute("INSERT INTO users (name) VALUES ($1)", "alice")

    # Shutdown pool at exit
    await shutdown_pool()
"""

from .advisory_lock import (
    AdvisoryLockService,
    AdvisoryLockServiceProtocol,
    LockInfo,
    LockResult,
    configure_lock_service,
    get_advisory_lock_service,
    hash_lock_key,
    make_p03_lock_key,
    reset_lock_service,
)
from .connection import connection_scope, read_only_scope, savepoint_scope, transaction_scope
from .context_helper import (
    clear_context,
    get_current_space_id,
    get_current_tenant_id,
    get_current_user_id,
    isolated_read_scope,
    isolation_scope,
    p03_isolation_scope,
    set_full_context,
    set_local_full_context,
    set_local_space_context,
    set_local_tenant_context,
    set_space_context,
    set_tenant_context,
    set_user_context,
    space_isolation_scope,
)
from .params import bind_params, bulk_params, dict_to_positional, named_to_positional
from .pool import AsyncPgPool, PoolStats, configure_pool, get_pool, shutdown_pool
from .query import QueryBuilder, convert_sqlite_query, convert_sqlite_upsert
from .types import (
    ensure_timestamp,
    ensure_uuid,
    record_to_dict,
    records_to_dicts,
    setup_type_codecs,
    text_to_timestamp,
    text_to_uuid,
    timestamp_now,
    timestamp_to_text,
    uuid_to_text,
)

__all__ = [
    # Advisory Lock
    "AdvisoryLockService",
    "AdvisoryLockServiceProtocol",
    "LockInfo",
    "LockResult",
    "configure_lock_service",
    "get_advisory_lock_service",
    "hash_lock_key",
    "make_p03_lock_key",
    "reset_lock_service",
    # Pool
    "AsyncPgPool",
    "PoolStats",
    "configure_pool",
    "get_pool",
    "shutdown_pool",
    # Connection
    "connection_scope",
    "read_only_scope",
    "savepoint_scope",
    "transaction_scope",
    # Context Helper (RLS)
    "clear_context",
    "get_current_space_id",
    "get_current_tenant_id",
    "get_current_user_id",
    "isolated_read_scope",
    "isolation_scope",
    "p03_isolation_scope",
    "set_full_context",
    "set_local_full_context",
    "set_local_space_context",
    "set_local_tenant_context",
    "set_space_context",
    "set_tenant_context",
    "set_user_context",
    "space_isolation_scope",
    # Query
    "QueryBuilder",
    "convert_sqlite_query",
    "convert_sqlite_upsert",
    # Params
    "bind_params",
    "bulk_params",
    "dict_to_positional",
    "named_to_positional",
    # Types
    "ensure_timestamp",
    "ensure_uuid",
    "record_to_dict",
    "records_to_dicts",
    "setup_type_codecs",
    "text_to_timestamp",
    "text_to_uuid",
    "timestamp_now",
    "timestamp_to_text",
    "uuid_to_text",
]
