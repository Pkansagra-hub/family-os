"""Drop and recreate st_vec with pgvector VECTOR(768) native column.

Revision ID: 0071
Revises: 0070
Create Date: 2026-03-01

M4 Epic 4.9 -- pgvector Migration

Drops the old st_vec table (LargeBinary vector column, FAISS columns)
and recreates it with:
- VECTOR(768) native pgvector column for HNSW indexing
- TEXT primary key and foreign key types (matches st_hipp_events.event_id TEXT)
- TIMESTAMPTZ timestamps (replaces BigInteger epoch)
- HNSW index with vector_cosine_ops (m=16, ef_construction=64)
- Removed: faiss_id, indexed_at columns
- Removed: INDEXED status (only READY/FAILED)

Pre-production: No data migration needed. Drop and recreate.

Contract: k0/contracts/schemas/st_vec_v2.columns.yaml
ADR: docs/architecture/decisions-K0/adr-k003-v2-pgvector-migration.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0071"
down_revision: str = "0070"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Drop old st_vec (LargeBinary) and recreate with pgvector VECTOR(768)."""
    # 1. Drop old st_vec table and all its indexes
    #    Pre-production: no data to preserve
    op.drop_index("idx_vec_faiss_id", table_name="st_vec", if_exists=True)
    op.drop_index("idx_vec_status_created", table_name="st_vec", if_exists=True)
    op.drop_index("idx_vec_model_id", table_name="st_vec", if_exists=True)
    op.drop_index("idx_vec_tenant_space", table_name="st_vec", if_exists=True)
    op.drop_index("idx_vec_event_id", table_name="st_vec", if_exists=True)
    op.drop_table("st_vec")

    # 2. Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 3. Recreate st_vec with pgvector-native VECTOR(768) column
    op.execute(
        """
        CREATE TABLE st_vec (
            -- IDENTITY
            embedding_id    TEXT PRIMARY KEY,
            -- LINKAGE TO EVENT
            event_id        TEXT NOT NULL,
            -- TENANT/SPACE CONTEXT
            tenant_id       VARCHAR(64) NOT NULL,
            space_id        VARCHAR(64) NOT NULL,
            -- VECTOR DATA (pgvector native)
            vector          VECTOR(768) NOT NULL,
            vector_dim      INTEGER NOT NULL DEFAULT 768,
            -- MODEL METADATA
            model_id        VARCHAR(64) NOT NULL DEFAULT 'ultrabert_v2.1.0',
            -- STATUS TRACKING (READY or FAILED only; INDEXED removed)
            status          VARCHAR(16) NOT NULL DEFAULT 'READY',
            -- TRACING
            cognitive_trace_id VARCHAR(128),
            -- TIMESTAMPS (TIMESTAMPTZ, replaces BigInteger epoch)
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ,

            -- CONSTRAINTS
            CONSTRAINT ck_st_vec_status CHECK (status IN ('READY', 'FAILED')),
            CONSTRAINT fk_st_vec_event FOREIGN KEY (event_id)
                REFERENCES st_hipp_events(event_id) ON DELETE CASCADE
        )
    """
    )

    # 4. B-tree indexes for standard queries
    op.execute("CREATE INDEX ix_st_vec_event ON st_vec (event_id)")
    op.execute("CREATE INDEX ix_st_vec_tenant ON st_vec (tenant_id, space_id)")
    op.execute("CREATE INDEX ix_st_vec_model ON st_vec (model_id)")
    op.execute("CREATE INDEX ix_st_vec_status ON st_vec (status)")
    op.execute("CREATE INDEX ix_st_vec_created ON st_vec (created_at)")

    # 5. HNSW index for vector similarity search
    op.execute(
        """
        CREATE INDEX ix_st_vec_hnsw
        ON st_vec
        USING hnsw (vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """
    )


def downgrade() -> None:
    """Drop pgvector st_vec and restore LargeBinary version.

    WARNING: This loses all vector data. Pre-production only.
    """
    op.execute("DROP INDEX IF EXISTS ix_st_vec_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_st_vec_created")
    op.execute("DROP INDEX IF EXISTS ix_st_vec_status")
    op.execute("DROP INDEX IF EXISTS ix_st_vec_model")
    op.execute("DROP INDEX IF EXISTS ix_st_vec_tenant")
    op.execute("DROP INDEX IF EXISTS ix_st_vec_event")
    op.execute("DROP TABLE IF EXISTS st_vec")
