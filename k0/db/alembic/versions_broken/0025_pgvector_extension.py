"""Create pgvector extension for vector similarity search.

Revision ID: 0025
Revises: 0024
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.2.2 - Issue 2.2.2.1)

This migration creates the pgvector extension which enables:
- VECTOR type for embedding storage
- Distance operators (<->, <=>, <#>)
- HNSW and IVFFlat index types

Requires PostgreSQL 15+ with pgvector extension installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0025"
down_revision: str = "0024"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create pgvector extension."""
    # Note: Extension may already exist from 0001_initial.py
    # Using IF NOT EXISTS for idempotency
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Drop pgvector extension.

    WARNING: This will invalidate all VECTOR columns and indexes.
    Only run if you are removing all vector data.
    """
    op.execute("DROP EXTENSION IF EXISTS vector CASCADE")
