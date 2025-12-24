"""Create st_archive_manifest table (Archive Tracking).

Revision ID: 0012
Revises: 0011
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.3 - Issue 2.1.3.3)

The st_archive_manifest table tracks archived resources.
Links archived data to retention policies for lifecycle management.

Columns: 9
Indexes: 2
Foreign Keys: 1 (retention_policy_id -> st_retention_policy.policy_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0012"
down_revision: str = "0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_archive_manifest table with foreign key."""
    op.create_table(
        "st_archive_manifest",
        # Primary key - UUID
        sa.Column("archive_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Resource identification
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        # Archive metadata
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("archive_location", sa.String(512), nullable=False),
        sa.Column("archive_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("archive_checksum", sa.String(64), nullable=True),
        # Link to retention policy
        sa.Column("retention_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Deletion schedule
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=True),
        # Foreign key constraint
        sa.ForeignKeyConstraint(
            ["retention_policy_id"],
            ["st_retention_policy.policy_id"],
            name="fk_archive_policy",
            ondelete="SET NULL",
        ),
    )

    # Create indexes for archive lookups
    op.create_index(
        "ix_st_archive_resource", "st_archive_manifest", ["resource_type", "resource_id"]
    )
    op.create_index(
        "ix_st_archive_delete",
        "st_archive_manifest",
        ["delete_after"],
        postgresql_where=sa.text("delete_after IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_archive_manifest table and all indexes."""
    op.drop_index("ix_st_archive_delete", table_name="st_archive_manifest")
    op.drop_index("ix_st_archive_resource", table_name="st_archive_manifest")
    op.drop_table("st_archive_manifest")
