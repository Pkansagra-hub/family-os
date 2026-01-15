"""Create st_embedding_queue table.

Revision ID: 0024
Revises: 0023
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite has 17 columns for st_embedding_queue table.
job_id is INTEGER PRIMARY KEY AUTOINCREMENT (not UUID).
All timestamps are INTEGER (Unix epoch).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0024"
down_revision: str = "0023"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_embedding_queue table matching SQLite schema."""
    op.create_table(
        "st_embedding_queue",
        # IDENTITY - INTEGER AUTOINCREMENT per SQLite
        sa.Column("job_id", sa.BigInteger, primary_key=True, autoincrement=True),
        # LINKAGE TO EVENT AND WAL
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        sa.Column("event_id", sa.Text, nullable=False),
        sa.Column("embedding_id", sa.Text, nullable=False, unique=True),
        # TENANT/SPACE CONTEXT
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # JOB CONFIGURATION
        sa.Column("vector_kind", sa.Text, nullable=False),
        sa.Column("model_id", sa.Text, nullable=False),
        sa.Column("priority", sa.Text, nullable=False, server_default="NORMAL"),
        # EXECUTION STATE
        sa.Column("status", sa.Text, nullable=False),
        # RETRY TRACKING
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("next_attempt_ts", sa.BigInteger, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        # VECTOR STORAGE
        sa.Column("vector_json", sa.Text, nullable=True),
        # TIMESTAMPS
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        # CHECK CONSTRAINTS
        sa.CheckConstraint(
            "priority IN ('HIGH', 'NORMAL', 'LOW')",
            name="ck_embedding_queue_priority",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'IN_PROGRESS', 'READY', 'INDEXED', 'FAILED_RETRYABLE', 'FAILED_PERMANENT')",
            name="ck_embedding_queue_status",
        ),
        # FOREIGN KEYS
        sa.ForeignKeyConstraint(
            ["wal_pos"],
            ["st_wal.pos"],
            name="fk_embedding_queue_wal",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["st_hipp_events.event_id"],
            name="fk_embedding_queue_event",
        ),
        sa.ForeignKeyConstraint(
            ["embedding_id"],
            ["st_hipp_events.embedding_id"],
            name="fk_embedding_queue_embedding",
        ),
    )

    # Create indexes matching SQLite
    op.create_index(
        "idx_embedding_queue_status_time",
        "st_embedding_queue",
        ["status", "next_attempt_ts"],
    )
    op.create_index("idx_embedding_queue_event_id", "st_embedding_queue", ["event_id"])
    op.create_index("idx_embedding_queue_embedding_id", "st_embedding_queue", ["embedding_id"])
    op.create_index(
        "idx_embedding_queue_status_created",
        "st_embedding_queue",
        ["status", "created_at"],
        postgresql_where=sa.text("status IN ('READY', 'INDEXED')"),
    )


def downgrade() -> None:
    """Drop st_embedding_queue table."""
    op.drop_index("idx_embedding_queue_status_created", table_name="st_embedding_queue")
    op.drop_index("idx_embedding_queue_embedding_id", table_name="st_embedding_queue")
    op.drop_index("idx_embedding_queue_event_id", table_name="st_embedding_queue")
    op.drop_index("idx_embedding_queue_status_time", table_name="st_embedding_queue")
    op.drop_table("st_embedding_queue")
