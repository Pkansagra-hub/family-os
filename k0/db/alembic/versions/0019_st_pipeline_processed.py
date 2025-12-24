"""Create st_pipeline_processed table.

Revision ID: 0019
Revises: 0018
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

CRITICAL: This was completely WRONG before!
Old schema had wrong columns (space_id INTEGER, event_id, envelope_id)
SQLite has: pipeline_id (TEXT), space_id (TEXT), wal_pos (INTEGER), processed_at (TEXT)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0019"
down_revision: str = "0018"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_pipeline_processed table matching SQLite schema.

    SQLite schema:
    CREATE TABLE st_pipeline_processed (
        pipeline_id TEXT NOT NULL,
        space_id TEXT NOT NULL,
        wal_pos INTEGER NOT NULL,
        processed_at TEXT NOT NULL,
        PRIMARY KEY (pipeline_id, space_id, wal_pos)
    );
    """
    op.create_table(
        "st_pipeline_processed",
        sa.Column("pipeline_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        sa.Column("processed_at", sa.BigInteger, nullable=False),
        sa.PrimaryKeyConstraint("pipeline_id", "space_id", "wal_pos"),
    )

    # Create indexes matching SQLite
    op.create_index(
        "idx_pipeline_processed_space_wal",
        "st_pipeline_processed",
        ["space_id", "wal_pos"],
    )


def downgrade() -> None:
    """Drop st_pipeline_processed table."""
    op.drop_index("idx_pipeline_processed_space_wal", table_name="st_pipeline_processed")
    op.drop_table("st_pipeline_processed")
