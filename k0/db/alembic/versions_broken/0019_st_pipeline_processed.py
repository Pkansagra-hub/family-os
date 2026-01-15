"""Create st_pipeline_processed table (Pipeline State Tracking).

Revision ID: 0019
Revises: 0018
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.6 - Issue 2.1.6.1)

The st_pipeline_processed table tracks which envelopes have been
processed by each pipeline. Used for exactly-once semantics.

Columns: 4
Indexes: 2
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0019"
down_revision: str = "0018"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_pipeline_processed table."""
    op.create_table(
        "st_pipeline_processed",
        # Composite primary key: pipeline + envelope
        sa.Column("pipeline_id", sa.String(64), nullable=False),
        sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Processing timestamp
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # TTL for cleanup (nullable = forever)
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        # Composite primary key
        sa.PrimaryKeyConstraint("pipeline_id", "envelope_id", name="pk_st_pipeline_processed"),
    )

    # Create indexes for pipeline processed queries
    op.create_index("ix_st_pipeline_processed_envelope", "st_pipeline_processed", ["envelope_id"])
    op.create_index("ix_st_pipeline_processed_expires", "st_pipeline_processed", ["expires_at"])


def downgrade() -> None:
    """Drop st_pipeline_processed table and all indexes."""
    op.drop_index("ix_st_pipeline_processed_expires", table_name="st_pipeline_processed")
    op.drop_index("ix_st_pipeline_processed_envelope", table_name="st_pipeline_processed")
    op.drop_table("st_pipeline_processed")
