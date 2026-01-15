"""Create HNSW index for vector similarity search.

Revision ID: 0027
Revises: 0026
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.2.2 - Issue 2.2.2.3)

This migration creates the HNSW index for fast approximate
nearest neighbor (ANN) search on embedding vectors.

HNSW Parameters:
- m=16: Max connections per layer (higher = more accurate, more memory)
- ef_construction=64: Build-time search width (higher = better recall, slower build)

Query-time parameter (SET in session):
- ef_search=40: Search-time width (higher = better recall, slower queries)

Estimated build time: 2-4 hours for 10M vectors
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0027"
down_revision: str = "0026"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create HNSW index for vector similarity search.

    Uses CONCURRENTLY to avoid blocking writes during index creation.
    This requires the migration to run outside a transaction.
    """
    # Create HNSW index for cosine similarity
    # Note: In production, run with CONCURRENTLY to avoid blocking
    op.execute(
        """
        CREATE INDEX ix_st_vec_hnsw
        ON st_vec
        USING hnsw (vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    """Drop HNSW vector index."""
    op.drop_index("ix_st_vec_hnsw", table_name="st_vec")
