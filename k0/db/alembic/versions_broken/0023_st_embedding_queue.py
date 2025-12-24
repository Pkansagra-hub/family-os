"""Create st_embedding_queue table (Embedding Job Queue).

Revision ID: 0023
Revises: 0022
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.2.1 - Issue 2.2.1.2)

The st_embedding_queue table tracks embedding generation jobs.
Supports retry logic with exponential backoff and priority scheduling.

Columns: 17
Indexes: 5
Foreign Keys: 3 (wal_pos, event_id, embedding_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0023"
down_revision: str = "0022"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_embedding_queue table."""
    op.create_table(
        "st_embedding_queue",
        # Primary key
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # References
        sa.Column("wal_pos", sa.BigInteger, nullable=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedding_id", postgresql.UUID(as_uuid=True), nullable=True, unique=True),
        # Tenant isolation
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        # Embedding configuration
        sa.Column("vector_kind", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        # Scheduling
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        # Retry logic
        sa.Column("attempt_count", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.SmallInteger, nullable=False, server_default="3"),
        sa.Column("next_attempt_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        # Result (nullable until complete)
        sa.Column("vector_json", postgresql.JSONB, nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # Foreign key constraints
        sa.ForeignKeyConstraint(
            ["wal_pos"],
            ["st_wal.pos"],
            name="fk_eq_wal",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["st_hipp_events.event_id"],
            name="fk_eq_event",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["embedding_id"],
            ["st_hipp_events.embedding_id"],
            name="fk_eq_embedding",
            ondelete="SET NULL",
        ),
    )

    # Create indexes for embedding queue queries
    op.create_index("ix_st_eq_status", "st_embedding_queue", ["status", "next_attempt_ts"])
    op.create_index("ix_st_eq_embedding", "st_embedding_queue", ["embedding_id"], unique=True)
    op.create_index("ix_st_eq_event", "st_embedding_queue", ["event_id"])
    op.create_index("ix_st_eq_tenant", "st_embedding_queue", ["tenant_id", "space_id"])
    op.create_index("ix_st_eq_priority", "st_embedding_queue", ["priority", "created_at"])


def downgrade() -> None:
    """Drop st_embedding_queue table and all indexes."""
    op.drop_index("ix_st_eq_priority", table_name="st_embedding_queue")
    op.drop_index("ix_st_eq_tenant", table_name="st_embedding_queue")
    op.drop_index("ix_st_eq_event", table_name="st_embedding_queue")
    op.drop_index("ix_st_eq_embedding", table_name="st_embedding_queue")
    op.drop_index("ix_st_eq_status", table_name="st_embedding_queue")
    op.drop_table("st_embedding_queue")
