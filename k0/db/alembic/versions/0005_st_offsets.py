"""Create st_offsets table (Consumer Offsets).

Revision ID: 0005
Revises: 0004
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_offsets (
  subscriber_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  space_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  offset INTEGER NOT NULL,
  updated_ts TEXT NOT NULL,
  PRIMARY KEY(subscriber_id, topic, space_id, tenant_id)
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0005"
down_revision: str = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_offsets table matching SQLite schema."""
    op.create_table(
        "st_offsets",
        # Composite primary key: subscriber + topic + space + tenant
        sa.Column("subscriber_id", sa.Text, nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("tenant_id", sa.Text, nullable=False),
        # Current offset position
        sa.Column("offset", sa.BigInteger, nullable=False),
        # Last update timestamp as TEXT
        sa.Column("updated_ts", sa.Text, nullable=False),
        # Define composite primary key
        sa.PrimaryKeyConstraint(
            "subscriber_id", "topic", "space_id", "tenant_id", name="pk_st_offsets"
        ),
    )


def downgrade() -> None:
    """Drop st_offsets table."""
    op.drop_table("st_offsets")
