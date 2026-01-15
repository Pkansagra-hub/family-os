"""Create st_pipeline_watermarks table (Pipeline Cursor Tracking).

Revision ID: 0021
Revises: 0020
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.6 - Issue 2.1.6.3)

The st_pipeline_watermarks table stores high-water marks for each
pipeline consumer. Used for resumable processing after restarts.

Columns: 4
Indexes: 2
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
    """Create st_pipeline_watermarks table."""
    op.create_table(
        "st_pipeline_watermarks",
        # Composite primary key: pipeline + partition
        sa.Column("pipeline_id", sa.String(64), nullable=False),
        sa.Column("partition_key", sa.String(64), nullable=False, server_default="default"),
        # Watermark position (sequence number or timestamp)
        sa.Column("watermark", sa.BigInteger, nullable=False, server_default="0"),
        # Last update timestamp
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Composite primary key
        sa.PrimaryKeyConstraint("pipeline_id", "partition_key", name="pk_st_pipeline_watermarks"),
    )

    # Create indexes for watermark queries
    op.create_index("ix_st_pipeline_watermarks_pipeline", "st_pipeline_watermarks", ["pipeline_id"])
    op.create_index("ix_st_pipeline_watermarks_updated", "st_pipeline_watermarks", ["updated_at"])


def downgrade() -> None:
    """Drop st_pipeline_watermarks table and all indexes."""
    op.drop_index("ix_st_pipeline_watermarks_updated", table_name="st_pipeline_watermarks")
    op.drop_index("ix_st_pipeline_watermarks_pipeline", table_name="st_pipeline_watermarks")
    op.drop_table("st_pipeline_watermarks")
