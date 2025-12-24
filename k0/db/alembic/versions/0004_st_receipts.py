"""Create st_receipts table (Commit Receipts).

Revision ID: 0004
Revises: 0003
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_receipts (
  receipt_id TEXT PRIMARY KEY,
  idem_key TEXT NOT NULL,
  wal_pos INTEGER NOT NULL,
  commit_ts TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  mls_group_id TEXT NOT NULL,
  key_version TEXT NOT NULL,
  device_sig TEXT NOT NULL,
  manifest_fingerprint TEXT
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0004"
down_revision: str = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_receipts table matching SQLite schema."""
    op.create_table(
        "st_receipts",
        # Primary key - receipt ID as TEXT
        sa.Column("receipt_id", sa.Text, primary_key=True),
        # Idempotency key
        sa.Column("idem_key", sa.Text, nullable=False),
        # Reference to WAL entry
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        # Commit timestamp as TEXT
        sa.Column("commit_ts", sa.Text, nullable=False),
        # Tenant/space isolation - all NOT NULL
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # Device info - all NOT NULL per SQLite
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("mls_group_id", sa.Text, nullable=False),
        sa.Column("key_version", sa.Text, nullable=False),
        # Signatures - NOT NULL per SQLite
        sa.Column("device_sig", sa.Text, nullable=False),
        sa.Column("manifest_fingerprint", sa.Text, nullable=True),
    )

    # Create indexes matching SQLite
    op.create_index("idx_receipts_space", "st_receipts", ["space_id", "wal_pos"])
    op.create_index("idx_receipts_walpos", "st_receipts", ["wal_pos"])


def downgrade() -> None:
    """Drop st_receipts table and all indexes."""
    op.drop_index("idx_receipts_walpos", table_name="st_receipts")
    op.drop_index("idx_receipts_space", table_name="st_receipts")
    op.drop_table("st_receipts")
