"""Create st_pipeline_status table (Pipeline Run Status).

Revision ID: 0020
Revises: 0019
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.6 - Issue 2.1.6.2)

The st_pipeline_status table tracks pipeline run state and metrics.
Each pipeline has a single status row updated during processing.

Columns: 7
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
revision: str = "0020"
down_revision: str = "0019"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_pipeline_status table."""
    op.create_table(
        "st_pipeline_status",
        # Primary key: pipeline ID
        sa.Column("pipeline_id", sa.String(64), primary_key=True),
        # Current status
        sa.Column("status", sa.String(16), nullable=False, server_default="idle"),
        # Run timestamps
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        # Processing metrics
        sa.Column("processed_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("error_count", sa.BigInteger, nullable=False, server_default="0"),
        # Last error (if any)
        sa.Column("last_error", postgresql.JSONB, nullable=True),
    )

    # Create indexes for pipeline status queries
    op.create_index("ix_st_pipeline_status_status", "st_pipeline_status", ["status"])
    op.create_index("ix_st_pipeline_status_last_run", "st_pipeline_status", ["last_run_at"])
    op.create_index("ix_st_pipeline_status_next_run", "st_pipeline_status", ["next_run_at"])


def downgrade() -> None:
    """Drop st_pipeline_status table and all indexes."""
    op.drop_index("ix_st_pipeline_status_next_run", table_name="st_pipeline_status")
    op.drop_index("ix_st_pipeline_status_last_run", table_name="st_pipeline_status")
    op.drop_index("ix_st_pipeline_status_status", table_name="st_pipeline_status")
    op.drop_table("st_pipeline_status")
