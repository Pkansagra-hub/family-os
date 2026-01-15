"""Create st_crdt_merge_log table (CRDT Conflict Resolution).

Revision ID: 0016
Revises: 0015
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_crdt_merge_log (
  merge_id TEXT PRIMARY KEY,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  merge_strategy TEXT NOT NULL,
  winner_device_id TEXT NOT NULL,
  loser_device_id TEXT,
  winner_vector_clock TEXT NOT NULL,
  loser_vector_clock TEXT,
  merged_at TEXT NOT NULL,
  conflict_reason TEXT,
  CHECK(merge_strategy IN ('lww', 'rga', 'orset', 'mvregister'))
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0016"
down_revision: str = "0015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_crdt_merge_log table matching SQLite schema."""
    op.create_table(
        "st_crdt_merge_log",
        # Primary key - TEXT per SQLite
        sa.Column("merge_id", sa.Text, primary_key=True),
        # Resource identification
        sa.Column("resource_type", sa.Text, nullable=False),
        sa.Column("resource_id", sa.Text, nullable=False),
        # Merge strategy
        sa.Column("merge_strategy", sa.Text, nullable=False),
        # Device conflict details - winner_device_id is NOT NULL per SQLite
        sa.Column("winner_device_id", sa.Text, nullable=False),
        sa.Column("loser_device_id", sa.Text, nullable=True),
        # Vector clocks as TEXT - winner is NOT NULL per SQLite
        sa.Column("winner_vector_clock", sa.Text, nullable=False),
        sa.Column("loser_vector_clock", sa.Text, nullable=True),
        # Timestamp as TEXT
        sa.Column("merged_at", sa.Text, nullable=False),
        # Conflict classification
        sa.Column("conflict_reason", sa.Text, nullable=True),
        # CHECK constraint
        sa.CheckConstraint(
            "merge_strategy IN ('lww', 'rga', 'orset', 'mvregister')",
            name="ck_crdt_merge_strategy",
        ),
    )

    # Create indexes matching SQLite
    op.create_index(
        "idx_crdt_merge_resource", "st_crdt_merge_log", ["resource_type", "resource_id"]
    )
    op.create_index("idx_crdt_merge_device", "st_crdt_merge_log", ["winner_device_id", "merged_at"])


def downgrade() -> None:
    """Drop st_crdt_merge_log table and all indexes."""
    op.drop_index("idx_crdt_merge_device", table_name="st_crdt_merge_log")
    op.drop_index("idx_crdt_merge_resource", table_name="st_crdt_merge_log")
    op.drop_table("st_crdt_merge_log")
