"""Create schema_registry table.

Revision ID: 0010
Revises: 0009
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE schema_registry (
  schema_uri TEXT NOT NULL,
  version TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('REGISTERED','ACTIVE','DEPRECATED','BLOCKED')),
  operator_id TEXT,
  blocked_ts TEXT,
  blocked_reason TEXT,
  unblocked_ts TEXT,
  PRIMARY KEY(schema_uri, version)
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0010"
down_revision: str = "0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create schema_registry table matching SQLite schema."""
    op.create_table(
        "schema_registry",
        # Composite primary key: schema URI + version
        sa.Column("schema_uri", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        # Content hash for integrity
        sa.Column("sha256", sa.Text, nullable=False),
        # Status tracking with CHECK constraint
        sa.Column("status", sa.Text, nullable=False),
        # Operator actions
        sa.Column("operator_id", sa.Text, nullable=True),
        sa.Column("blocked_ts", sa.Text, nullable=True),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("unblocked_ts", sa.Text, nullable=True),
        # Define composite primary key
        sa.PrimaryKeyConstraint("schema_uri", "version", name="pk_schema_registry"),
        # CHECK constraint
        sa.CheckConstraint(
            "status IN ('REGISTERED', 'ACTIVE', 'DEPRECATED', 'BLOCKED')",
            name="ck_schema_registry_status",
        ),
    )


def downgrade() -> None:
    """Drop schema_registry table."""
    op.drop_table("schema_registry")
