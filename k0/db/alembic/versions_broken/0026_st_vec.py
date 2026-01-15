"""Create st_vec table (Vector Store).

Revision ID: 0026
Revises: 0025
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.2.2 - Issue 2.2.2.2)

The st_vec table stores embedding vectors for similarity search.
Uses pgvector's VECTOR(768) type for 768-dimensional embeddings.

Columns: 13
Indexes: 6
Foreign Keys: 1 (event_id -> st_hipp_events.event_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0026"
down_revision: str = "0025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_vec table with pgvector column."""
    # Use raw SQL to create table with VECTOR type (avoids pgvector Python dependency)
    op.execute(
        """
        CREATE TABLE st_vec (
            embedding_id UUID PRIMARY KEY,
            event_id UUID,
            tenant_id VARCHAR(64) NOT NULL,
            space_id VARCHAR(64) NOT NULL,
            vector VECTOR(768) NOT NULL,
            vector_dim INTEGER NOT NULL DEFAULT 768,
            model_id VARCHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            cognitive_trace_id VARCHAR(128),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ,
            faiss_id INTEGER,
            indexed_at TIMESTAMPTZ,
            CONSTRAINT fk_vec_event FOREIGN KEY (event_id)
                REFERENCES st_hipp_events(event_id) ON DELETE CASCADE
        )
        """
    )

    # Create B-tree indexes for standard queries
    op.create_index("ix_st_vec_event", "st_vec", ["event_id"])
    op.create_index("ix_st_vec_tenant", "st_vec", ["tenant_id", "space_id"])
    op.create_index("ix_st_vec_model", "st_vec", ["model_id"])
    op.create_index("ix_st_vec_status", "st_vec", ["status"])
    op.create_index("ix_st_vec_created", "st_vec", ["created_at"])
    # Partial index for FAISS ID lookups
    op.execute(
        """
        CREATE INDEX ix_st_vec_faiss ON st_vec (faiss_id)
        WHERE faiss_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Drop st_vec table and all indexes."""
    op.drop_index("ix_st_vec_faiss", table_name="st_vec")
    op.drop_index("ix_st_vec_created", table_name="st_vec")
    op.drop_index("ix_st_vec_status", table_name="st_vec")
    op.drop_index("ix_st_vec_model", table_name="st_vec")
    op.drop_index("ix_st_vec_tenant", table_name="st_vec")
    op.drop_index("ix_st_vec_event", table_name="st_vec")
    op.drop_table("st_vec")
