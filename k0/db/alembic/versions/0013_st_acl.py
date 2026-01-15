"""Create st_acl table (Access Control Lists).

Revision ID: 0013
Revises: 0012
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_acl (
  acl_id TEXT PRIMARY KEY,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  principal_type TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  permission TEXT NOT NULL,
  privacy_band TEXT,
  granted_at TEXT NOT NULL,
  granted_by TEXT NOT NULL,
  expires_at TEXT,
  revoked_at TEXT,
  CHECK(principal_type IN ('user', 'device', 'service')),
  CHECK(permission IN ('read', 'write', 'delete', 'share')),
  CHECK(privacy_band IN ('GREEN', 'AMBER', 'RED'))
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0013"
down_revision: str = "0012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_acl table matching SQLite schema."""
    op.create_table(
        "st_acl",
        # Primary key - TEXT per SQLite
        sa.Column("acl_id", sa.Text, primary_key=True),
        # Resource identification
        sa.Column("resource_type", sa.Text, nullable=False),
        sa.Column("resource_id", sa.Text, nullable=False),
        # Principal identification
        sa.Column("principal_type", sa.Text, nullable=False),
        sa.Column("principal_id", sa.Text, nullable=False),
        # Permission
        sa.Column("permission", sa.Text, nullable=False),
        sa.Column("privacy_band", sa.Text, nullable=True),
        # Grant tracking - granted_by is NOT NULL per SQLite
        sa.Column("granted_at", sa.Text, nullable=False),
        sa.Column("granted_by", sa.Text, nullable=False),
        # Expiry and revocation
        sa.Column("expires_at", sa.Text, nullable=True),
        sa.Column("revoked_at", sa.Text, nullable=True),
        # CHECK constraints
        sa.CheckConstraint(
            "principal_type IN ('user', 'device', 'service')",
            name="ck_acl_principal_type",
        ),
        sa.CheckConstraint(
            "permission IN ('read', 'write', 'delete', 'share')",
            name="ck_acl_permission",
        ),
        sa.CheckConstraint(
            "privacy_band IN ('GREEN', 'AMBER', 'RED') OR privacy_band IS NULL",
            name="ck_acl_privacy_band",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_acl_resource", "st_acl", ["resource_type", "resource_id"])
    op.create_index("idx_acl_principal", "st_acl", ["principal_type", "principal_id"])
    op.create_index("idx_acl_permission", "st_acl", ["permission", "revoked_at"])
    op.create_index("idx_acl_privacy", "st_acl", ["privacy_band", "revoked_at"])


def downgrade() -> None:
    """Drop st_acl table and all indexes."""
    op.drop_index("idx_acl_privacy", table_name="st_acl")
    op.drop_index("idx_acl_permission", table_name="st_acl")
    op.drop_index("idx_acl_principal", table_name="st_acl")
    op.drop_index("idx_acl_resource", table_name="st_acl")
    op.drop_table("st_acl")
