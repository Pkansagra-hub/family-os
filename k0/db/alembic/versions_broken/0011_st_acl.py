"""Create st_acl table (Access Control Lists).

Revision ID: 0011
Revises: 0010
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.3 - Issue 2.1.3.2)

The st_acl table stores access control entries for resources.
Supports principal-based permissions with expiry and revocation.

Columns: 11
Indexes: 4
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0011"
down_revision: str = "0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_acl table with all columns and indexes."""
    op.create_table(
        "st_acl",
        # Primary key - UUID
        sa.Column("acl_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Resource identification
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        # Principal identification
        sa.Column("principal_type", sa.String(32), nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        # Permission
        sa.Column("permission", sa.String(32), nullable=False),
        sa.Column("privacy_band", sa.String(16), nullable=True),
        # Grant tracking
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("granted_by", sa.String(64), nullable=True),
        # Expiry and revocation
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes for ACL lookups
    op.create_index("ix_st_acl_resource", "st_acl", ["resource_type", "resource_id"])
    op.create_index("ix_st_acl_principal", "st_acl", ["principal_type", "principal_id"])
    op.create_index("ix_st_acl_permission", "st_acl", ["permission"])
    op.create_index(
        "ix_st_acl_expires",
        "st_acl",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_acl table and all indexes."""
    op.drop_index("ix_st_acl_expires", table_name="st_acl")
    op.drop_index("ix_st_acl_permission", table_name="st_acl")
    op.drop_index("ix_st_acl_principal", table_name="st_acl")
    op.drop_index("ix_st_acl_resource", table_name="st_acl")
    op.drop_table("st_acl")
