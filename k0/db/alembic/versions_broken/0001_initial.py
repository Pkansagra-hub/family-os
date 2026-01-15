"""Initial baseline revision.

Revision ID: 0001
Revises: None
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 1.1.2)

This is a placeholder revision to establish the migration baseline.
It creates no tables - actual table creation begins with 0002_st_wal.py.

The alembic_version table is created automatically by Alembic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers used by Alembic
revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Establish migration baseline.

    This is an empty migration that marks the starting point
    for PostgreSQL schema migrations. The alembic_version table
    is created automatically by Alembic.

    Subsequent migrations will create the actual K0 tables:
    - 0002: st_wal (write-ahead log)
    - 0003: st_outbox (outbox pattern)
    - 0004: st_dlq (dead letter queue)
    - etc.
    """
    pass


def downgrade() -> None:
    """Revert to pre-migration state.

    WARNING: This is destructive and should only be used in development.
    Dropping the baseline is not supported in production.
    """
    # Intentionally empty - dropping baseline is not supported
    pass
