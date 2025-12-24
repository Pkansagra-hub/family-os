"""Create st_obligation_log table (Policy Obligations).

Revision ID: 0012
Revises: 0011
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_obligation_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  obligation TEXT NOT NULL,
  details_json TEXT,
  commit_ts TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  FOREIGN KEY(wal_pos) REFERENCES st_wal(pos)
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0012"
down_revision: str = "0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_obligation_log table matching SQLite schema."""
    op.create_table(
        "st_obligation_log",
        # Primary key
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Reference to WAL entry
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        # Obligation type
        sa.Column("obligation", sa.Text, nullable=False),
        # Additional details as TEXT (JSON)
        sa.Column("details_json", sa.Text, nullable=True),
        # Timestamp as TEXT
        sa.Column("commit_ts", sa.Text, nullable=False),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # Foreign key constraint
        sa.ForeignKeyConstraint(
            ["wal_pos"],
            ["st_wal.pos"],
            name="fk_obligation_wal",
            ondelete="CASCADE",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_obligation_log_wal", "st_obligation_log", ["wal_pos"])
    op.create_index(
        "idx_obligation_log_tenant_space",
        "st_obligation_log",
        ["tenant_id", "space_id", "commit_ts"],
    )


def downgrade() -> None:
    """Drop st_obligation_log table and all indexes."""
    op.drop_index("idx_obligation_log_tenant_space", table_name="st_obligation_log")
    op.drop_index("idx_obligation_log_wal", table_name="st_obligation_log")
    op.drop_table("st_obligation_log")
