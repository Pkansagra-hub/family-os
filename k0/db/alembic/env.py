"""Alembic migration environment for K0 kernel.

Part of Milestone 1.1.2 - Issue 1.1.2.1: Initialize Alembic Structure.

This module configures the Alembic migration environment for:
- Async migrations with asyncpg
- PostgreSQL-native operations
- Proper connection handling via asyncpg pool

Usage:
    alembic upgrade head      # Apply all pending migrations
    alembic downgrade -1      # Revert one migration
    alembic current           # Show current revision
    alembic history           # Show migration history
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from k0.config.postgres import get_postgres_settings

# Alembic Config object for access to .ini file values
config = context.config

# Configure Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemy MetaData for 'autogenerate' support
# Import your models' metadata here for autogenerate to detect changes
# from k0.db.models import Base
# target_metadata = Base.metadata
target_metadata = None  # Set to None until we have SQLAlchemy models


def get_url() -> str:
    """Get database URL from K0 configuration.

    Returns:
        PostgreSQL+asyncpg DSN for SQLAlchemy async engine.
    """
    settings = get_postgres_settings()
    # Convert postgresql:// to postgresql+asyncpg:// for SQLAlchemy async
    dsn = settings.dsn
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In offline mode, Alembic generates SQL scripts without connecting
    to the database. Useful for reviewing migrations before applying.

    Usage:
        alembic upgrade head --sql > migration.sql
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations within a connection context.

    Args:
        connection: SQLAlchemy connection object.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine.

    Uses SQLAlchemy async engine for PostgreSQL compatibility.
    Connection pooling is disabled (NullPool) since Alembic
    runs single-shot migrations.
    """
    # Build configuration with database URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    # Create async engine without connection pooling
    # statement_cache_size=0 required for pgbouncer transaction pooling mode
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"statement_cache_size": 0},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    This is the normal execution path when running:
        alembic upgrade head
    """
    asyncio.run(run_async_migrations())


# Determine which mode to run in
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
