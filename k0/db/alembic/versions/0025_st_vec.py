"""Create st_vec table (Vector Embeddings).

Revision ID: 0025
Revises: 0024
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite has 13 columns for st_vec table.
For PostgreSQL, we use pgvector for the vector column.
All timestamps are INTEGER (Unix epoch).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0025"
down_revision: str = "0024"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_vec table matching SQLite schema.

    SQLite stores vectors as BLOB. PostgreSQL uses pgvector.
    """
    op.create_table(
        "st_vec",
        # IDENTITY
        sa.Column("embedding_id", sa.Text, primary_key=True),
        # LINKAGE TO EVENT
        sa.Column("event_id", sa.Text, nullable=False),
        # TENANT/SPACE CONTEXT
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # VECTOR DATA - BLOB in SQLite, pgvector in PostgreSQL
        # Using LargeBinary to match SQLite BLOB, will cast at query time
        sa.Column("vector", sa.LargeBinary, nullable=False),
        sa.Column("vector_dim", sa.Integer, nullable=False, server_default="768"),
        # MODEL METADATA
        sa.Column("model_id", sa.Text, nullable=False, server_default="'ultrabert_v2.1.0'"),
        # STATUS TRACKING
        sa.Column("status", sa.Text, nullable=False, server_default="'READY'"),
        # TRACING
        sa.Column("cognitive_trace_id", sa.Text, nullable=True),
        # TIMESTAMPS (INTEGER Unix epoch)
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        # FAISS INDEX TRACKING
        sa.Column("faiss_id", sa.Integer, nullable=True),
        sa.Column("indexed_at", sa.BigInteger, nullable=True),
        # CHECK CONSTRAINT
        sa.CheckConstraint(
            "status IN ('READY', 'INDEXED', 'FAILED')",
            name="ck_st_vec_status",
        ),
        # FOREIGN KEY
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["st_hipp_events.event_id"],
            name="fk_st_vec_event",
            ondelete="CASCADE",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_vec_event_id", "st_vec", ["event_id"])
    op.create_index("idx_vec_tenant_space", "st_vec", ["tenant_id", "space_id"])
    op.create_index("idx_vec_model_id", "st_vec", ["model_id"])
    op.create_index(
        "idx_vec_status_created",
        "st_vec",
        ["status", "created_at"],
        postgresql_where=sa.text("status = 'READY'"),
    )
    op.create_index("idx_vec_faiss_id", "st_vec", ["faiss_id"])


def downgrade() -> None:
    """Drop st_vec table."""
    op.drop_index("idx_vec_faiss_id", table_name="st_vec")
    op.drop_index("idx_vec_status_created", table_name="st_vec")
    op.drop_index("idx_vec_model_id", table_name="st_vec")
    op.drop_index("idx_vec_tenant_space", table_name="st_vec")
    op.drop_index("idx_vec_event_id", table_name="st_vec")
    op.drop_table("st_vec")
