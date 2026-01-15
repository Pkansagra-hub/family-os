"""Create st_retention_policy table (Data Retention).

Revision ID: 0010
Revises: 0009
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.3 - Issue 2.1.3.1)

The st_retention_policy table defines data retention rules per resource type.
Policies control how long data is kept and when it's archived.

Columns: 11
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
revision: str = "0010"
down_revision: str = "0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_retention_policy table."""
    op.create_table(
        "st_retention_policy",
        # Primary key - UUID
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Policy name (unique)
        sa.Column("policy_name", sa.String(128), nullable=False, unique=True),
        # Targeting
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("privacy_band", sa.String(16), nullable=False),
        # Retention settings
        sa.Column("retention_days", sa.Integer, nullable=False),
        sa.Column("archive_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("archive_after_days", sa.Integer, nullable=True),
        # Audit
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # Status
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
    )

    # Create indexes for policy lookups
    op.create_index("ix_st_retention_resource", "st_retention_policy", ["resource_type"])
    op.create_index("ix_st_retention_band", "st_retention_policy", ["privacy_band"])


def downgrade() -> None:
    """Drop st_retention_policy table and all indexes."""
    op.drop_index("ix_st_retention_band", table_name="st_retention_policy")
    op.drop_index("ix_st_retention_resource", table_name="st_retention_policy")
    op.drop_table("st_retention_policy")
