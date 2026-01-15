"""Create schema_registry table.

Revision ID: 0006
Revises: 0005
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.2 - Issue 2.1.2.1)

The schema_registry table tracks JSON schema versions for envelope validation.
Schemas can be blocked by operators for security/compliance.

Columns: 8
Indexes: 1
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0006"
down_revision: str = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create schema_registry table with composite primary key."""
    op.create_table(
        "schema_registry",
        # Composite primary key: schema URI + version
        sa.Column("schema_uri", sa.String(512), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        # Content hash for integrity
        sa.Column("sha256", sa.String(64), nullable=False),
        # Status tracking
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        # Operator actions
        sa.Column("operator_id", sa.String(64), nullable=True),
        sa.Column("blocked_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("unblocked_ts", sa.DateTime(timezone=True), nullable=True),
        # Define composite primary key
        sa.PrimaryKeyConstraint("schema_uri", "version", name="pk_schema_registry"),
    )

    # Create index for hash lookups
    op.create_index("ix_schema_registry_sha256", "schema_registry", ["sha256"])


def downgrade() -> None:
    """Drop schema_registry table and all indexes."""
    op.drop_index("ix_schema_registry_sha256", table_name="schema_registry")
    op.drop_table("schema_registry")
