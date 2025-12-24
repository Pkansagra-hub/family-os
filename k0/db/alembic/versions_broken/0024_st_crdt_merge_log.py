"""Create st_crdt_merge_log table (CRDT Conflict Resolution Log).

Revision ID: 0024
Revises: 0023
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.2.1 - Issue 2.2.1.3)

The st_crdt_merge_log table records CRDT merge decisions.
Tracks conflict resolution between devices with vector clocks.

Columns: 10
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
revision: str = "0024"
down_revision: str = "0023"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_crdt_merge_log table."""
    op.create_table(
        "st_crdt_merge_log",
        # Primary key
        sa.Column("merge_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Resource identification
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        # Merge strategy
        sa.Column("merge_strategy", sa.String(32), nullable=False),
        # Device conflict details
        sa.Column("winner_device_id", sa.String(64), nullable=True),
        sa.Column("loser_device_id", sa.String(64), nullable=True),
        # Vector clocks (JSONB for flexibility)
        sa.Column("winner_vector_clock", postgresql.JSONB, nullable=True),
        sa.Column("loser_vector_clock", postgresql.JSONB, nullable=True),
        # Timestamp
        sa.Column(
            "merged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        # Conflict classification
        sa.Column("conflict_reason", sa.String(64), nullable=True),
    )

    # Create indexes for CRDT merge log queries
    op.create_index("ix_st_crdt_resource", "st_crdt_merge_log", ["resource_type", "resource_id"])
    op.create_index("ix_st_crdt_merged", "st_crdt_merge_log", ["merged_at"])
    op.create_index("ix_st_crdt_reason", "st_crdt_merge_log", ["conflict_reason"])


def downgrade() -> None:
    """Drop st_crdt_merge_log table and all indexes."""
    op.drop_index("ix_st_crdt_reason", table_name="st_crdt_merge_log")
    op.drop_index("ix_st_crdt_merged", table_name="st_crdt_merge_log")
    op.drop_index("ix_st_crdt_resource", table_name="st_crdt_merge_log")
    op.drop_table("st_crdt_merge_log")
