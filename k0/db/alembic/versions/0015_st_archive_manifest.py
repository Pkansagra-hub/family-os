"""Create st_archive_manifest table (Archive Tracking).

Revision ID: 0015
Revises: 0014
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_archive_manifest (
  archive_id TEXT PRIMARY KEY,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  archived_at TEXT NOT NULL,
  archive_location TEXT NOT NULL,
  archive_size_bytes INTEGER,
  archive_checksum TEXT,
  retention_policy_id TEXT,
  delete_after TEXT,
  FOREIGN KEY(retention_policy_id) REFERENCES st_retention_policy(policy_id)
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0015"
down_revision: str = "0014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_archive_manifest table matching SQLite schema."""
    op.create_table(
        "st_archive_manifest",
        # Primary key - TEXT per SQLite
        sa.Column("archive_id", sa.Text, primary_key=True),
        # Resource identification
        sa.Column("resource_type", sa.Text, nullable=False),
        sa.Column("resource_id", sa.Text, nullable=False),
        # Archive metadata
        sa.Column("archived_at", sa.Text, nullable=False),
        sa.Column("archive_location", sa.Text, nullable=False),
        sa.Column("archive_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("archive_checksum", sa.Text, nullable=True),
        # Link to retention policy
        sa.Column("retention_policy_id", sa.Text, nullable=True),
        # Deletion schedule
        sa.Column("delete_after", sa.Text, nullable=True),
        # Foreign key constraint
        sa.ForeignKeyConstraint(
            ["retention_policy_id"],
            ["st_retention_policy.policy_id"],
            name="fk_archive_policy",
            ondelete="SET NULL",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_archive_resource", "st_archive_manifest", ["resource_type", "resource_id"])
    op.create_index("idx_archive_delete", "st_archive_manifest", ["delete_after"])


def downgrade() -> None:
    """Drop st_archive_manifest table and all indexes."""
    op.drop_index("idx_archive_delete", table_name="st_archive_manifest")
    op.drop_index("idx_archive_resource", table_name="st_archive_manifest")
    op.drop_table("st_archive_manifest")
