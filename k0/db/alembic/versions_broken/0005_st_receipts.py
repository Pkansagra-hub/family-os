"""Create st_receipts table (Commit Receipts).

Revision ID: 0005
Revises: 0004
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.1 - Issue 2.1.1.4)

The st_receipts table stores commit receipts for idempotency.
Each receipt proves an envelope was committed to the WAL.

Columns: 11
Indexes: 3
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0005"
down_revision: str = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_receipts table with all columns and indexes."""
    op.create_table(
        "st_receipts",
        # Primary key - UUID receipt ID
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Idempotency key
        sa.Column("idem_key", sa.String(128), nullable=False),
        # Reference to WAL entry
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        # Commit timestamp
        sa.Column("commit_ts", sa.DateTime(timezone=True), nullable=False),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        # Device info
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("mls_group_id", sa.String(64), nullable=True),
        sa.Column("key_version", sa.Integer, nullable=True),
        # Signatures
        sa.Column("device_sig", sa.Text, nullable=True),
        sa.Column("manifest_fingerprint", sa.String(64), nullable=True),
    )

    # Create indexes for receipt lookups
    op.create_index("ix_st_receipts_idem_key", "st_receipts", ["idem_key"])
    op.create_index("ix_st_receipts_wal_pos", "st_receipts", ["wal_pos"])
    op.create_index("ix_st_receipts_tenant_space", "st_receipts", ["tenant_id", "space_id"])


def downgrade() -> None:
    """Drop st_receipts table and all indexes."""
    op.drop_index("ix_st_receipts_tenant_space", table_name="st_receipts")
    op.drop_index("ix_st_receipts_wal_pos", table_name="st_receipts")
    op.drop_index("ix_st_receipts_idem_key", table_name="st_receipts")
    op.drop_table("st_receipts")
