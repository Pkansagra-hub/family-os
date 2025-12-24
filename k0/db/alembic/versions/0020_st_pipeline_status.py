"""Create st_pipeline_status table.

Revision ID: 0020
Revises: 0019
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

CRITICAL: This was completely WRONG before!
Old schema had: pipeline_id, is_enabled, offset, updated_at
SQLite has: pipeline_id, wal_pos, status, error, started_at, finished_at, trace_id
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0020"
down_revision: str = "0019"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_pipeline_status table matching SQLite schema.

    SQLite schema:
    CREATE TABLE st_pipeline_status (
      pipeline_id  TEXT NOT NULL,
      wal_pos      INTEGER NOT NULL,
      status       TEXT NOT NULL CHECK(status IN ('OK', 'ERROR', 'DEFERRED')),
      duration_ms  INTEGER,
      error_kind   TEXT,
      error_msg    TEXT,
      updated_at   INTEGER NOT NULL,
      PRIMARY KEY (pipeline_id, wal_pos)
    );
    """
    op.create_table(
        "st_pipeline_status",
        sa.Column("pipeline_id", sa.Text, nullable=False),
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error_kind", sa.Text, nullable=True),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.PrimaryKeyConstraint("pipeline_id", "wal_pos"),
        sa.CheckConstraint(
            "status IN ('OK', 'ERROR', 'DEFERRED')",
            name="ck_st_pipeline_status_status",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_pipeline_status_status", "st_pipeline_status", ["status"])
    op.create_index("idx_pipeline_status_updated", "st_pipeline_status", ["updated_at"])


def downgrade() -> None:
    """Drop st_pipeline_status table."""
    op.drop_index("idx_pipeline_status_updated", table_name="st_pipeline_status")
    op.drop_index("idx_pipeline_status_status", table_name="st_pipeline_status")
    op.drop_table("st_pipeline_status")
