"""Create schema_migrations table (legacy compatibility).

Revision ID: 0007
Revises: 0006
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.2 - Issue 2.1.2.2)

The schema_migrations table tracks SQLite-era migrations.
For PostgreSQL, Alembic's alembic_version table replaces this.
This table is created for backward compatibility during transition.

Columns: 3
Indexes: 0
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0007"
down_revision: str = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create schema_migrations table for backward compatibility."""
    op.create_table(
        "schema_migrations",
        # Primary key - version string
        sa.Column("version", sa.String(32), primary_key=True),
        # Checksum for integrity verification
        sa.Column("checksum", sa.String(64), nullable=False),
        # When the migration was applied
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    """Drop schema_migrations table."""
    op.drop_table("schema_migrations")
