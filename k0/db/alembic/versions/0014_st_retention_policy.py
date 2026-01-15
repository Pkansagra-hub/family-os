"""Create st_retention_policy table (Data Retention).

Revision ID: 0014
Revises: 0013
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_retention_policy (
  policy_id TEXT PRIMARY KEY,
  policy_name TEXT NOT NULL UNIQUE,
  resource_type TEXT NOT NULL,
  privacy_band TEXT,
  retention_days INTEGER NOT NULL,
  archive_enabled BOOLEAN DEFAULT 1,
  archive_after_days INTEGER,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  updated_at TEXT,
  enabled BOOLEAN DEFAULT 1,
  CHECK(privacy_band IN ('GREEN', 'AMBER', 'RED') OR privacy_band IS NULL)
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0014"
down_revision: str = "0013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_retention_policy table matching SQLite schema."""
    op.create_table(
        "st_retention_policy",
        # Primary key - TEXT per SQLite
        sa.Column("policy_id", sa.Text, primary_key=True),
        # Policy name (unique)
        sa.Column("policy_name", sa.Text, nullable=False, unique=True),
        # Targeting - privacy_band is nullable per SQLite
        sa.Column("resource_type", sa.Text, nullable=False),
        sa.Column("privacy_band", sa.Text, nullable=True),
        # Retention settings
        sa.Column("retention_days", sa.Integer, nullable=False),
        sa.Column("archive_enabled", sa.Boolean, nullable=True, server_default="true"),
        sa.Column("archive_after_days", sa.Integer, nullable=True),
        # Audit - created_by is NOT NULL per SQLite
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=True),
        # Status
        sa.Column("enabled", sa.Boolean, nullable=True, server_default="true"),
        # CHECK constraint
        sa.CheckConstraint(
            "privacy_band IN ('GREEN', 'AMBER', 'RED') OR privacy_band IS NULL",
            name="ck_retention_privacy_band",
        ),
    )

    # Create index matching SQLite
    op.create_index(
        "idx_retention_resource", "st_retention_policy", ["resource_type", "privacy_band"]
    )


def downgrade() -> None:
    """Drop st_retention_policy table and all indexes."""
    op.drop_index("idx_retention_resource", table_name="st_retention_policy")
    op.drop_table("st_retention_policy")
