"""Create st_pipeline_watermarks table.

Revision ID: 0021
Revises: 0020
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

CRITICAL: This was completely WRONG before!
Old schema had: pipeline_id (PK), last_wal_pos, updated_at
SQLite has: pipeline_id, space_id, last_wal_pos, updated_at with composite PK
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0021"
down_revision: str = "0020"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_pipeline_watermarks table matching SQLite schema.

    SQLite schema:
    CREATE TABLE st_pipeline_watermarks (
      pipeline_id  TEXT NOT NULL,
      space_id     TEXT NOT NULL,
      watermark    INTEGER NOT NULL,
      updated_at   INTEGER NOT NULL,
      PRIMARY KEY (pipeline_id, space_id)
    );
    """
    op.create_table(
        "st_pipeline_watermarks",
        sa.Column("pipeline_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("watermark", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.PrimaryKeyConstraint("pipeline_id", "space_id"),
    )

    # Create indexes matching SQLite
    op.create_index(
        "idx_pipeline_watermarks_pipeline",
        "st_pipeline_watermarks",
        ["pipeline_id", "watermark"],
    )


def downgrade() -> None:
    """Drop st_pipeline_watermarks table."""
    op.drop_index("idx_pipeline_watermarks_pipeline", table_name="st_pipeline_watermarks")
    op.drop_table("st_pipeline_watermarks")
