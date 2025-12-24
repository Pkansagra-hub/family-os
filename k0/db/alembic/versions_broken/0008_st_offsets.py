"""Create st_offsets table (Consumer Offsets).

Revision ID: 0008
Revises: 0007
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.2 - Issue 2.1.2.3)

The st_offsets table tracks WAL consumption positions per subscriber.
Used for at-least-once delivery and replay from last position.

Columns: 6
Indexes: 1
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0008"
down_revision: str = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_offsets table with composite primary key."""
    op.create_table(
        "st_offsets",
        # Composite primary key: subscriber + topic + space + tenant
        sa.Column("subscriber_id", sa.String(128), nullable=False),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        # Current offset position
        sa.Column("offset", sa.BigInteger, nullable=False, server_default="0"),
        # Last update timestamp
        sa.Column(
            "updated_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Define composite primary key
        sa.PrimaryKeyConstraint(
            "subscriber_id",
            "topic",
            "space_id",
            "tenant_id",
            name="pk_st_offsets",
        ),
    )

    # Create index for updated timestamp queries
    op.create_index("ix_st_offsets_updated", "st_offsets", ["updated_ts"])


def downgrade() -> None:
    """Drop st_offsets table and all indexes."""
    op.drop_index("ix_st_offsets_updated", table_name="st_offsets")
    op.drop_table("st_offsets")
