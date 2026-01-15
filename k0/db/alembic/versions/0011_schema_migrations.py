"""Create schema_migrations table.

Revision ID: 0011
Revises: 0010
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE schema_migrations (
  version TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0011"
down_revision: str = "0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create schema_migrations table matching SQLite schema."""
    op.create_table(
        "schema_migrations",
        # Primary key - version string
        sa.Column("version", sa.Text, primary_key=True),
        # Checksum for integrity verification
        sa.Column("checksum", sa.Text, nullable=False),
        # When the migration was applied - TEXT per SQLite
        sa.Column("applied_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    """Drop schema_migrations table."""
    op.drop_table("schema_migrations")
