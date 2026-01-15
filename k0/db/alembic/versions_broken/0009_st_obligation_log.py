"""Create st_obligation_log table (Policy Obligations).

Revision ID: 0009
Revises: 0008
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.2 - Issue 2.1.2.4)

The st_obligation_log table records policy obligations triggered by envelopes.
Used for compliance tracking and audit.

Columns: 7
Indexes: 2
Foreign Keys: 1 (wal_pos -> st_wal.pos)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0009"
down_revision: str = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_obligation_log table with foreign key to st_wal."""
    op.create_table(
        "st_obligation_log",
        # Primary key
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Reference to WAL entry
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        # Obligation type
        sa.Column("obligation", sa.String(64), nullable=False),
        # Additional details as JSONB
        sa.Column("details_json", postgresql.JSONB, nullable=True),
        # Timestamp
        sa.Column("commit_ts", sa.DateTime(timezone=True), nullable=False),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        # Foreign key constraint
        sa.ForeignKeyConstraint(
            ["wal_pos"],
            ["st_wal.pos"],
            name="fk_obligation_wal",
            ondelete="CASCADE",
        ),
    )

    # Create indexes for lookups
    op.create_index("ix_st_obligation_wal_pos", "st_obligation_log", ["wal_pos"])
    op.create_index("ix_st_obligation_tenant", "st_obligation_log", ["tenant_id", "space_id"])


def downgrade() -> None:
    """Drop st_obligation_log table and all indexes."""
    op.drop_index("ix_st_obligation_tenant", table_name="st_obligation_log")
    op.drop_index("ix_st_obligation_wal_pos", table_name="st_obligation_log")
    op.drop_table("st_obligation_log")
