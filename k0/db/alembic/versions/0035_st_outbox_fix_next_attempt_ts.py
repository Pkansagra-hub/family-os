"""Fix st_outbox.next_attempt_ts type from TEXT to BIGINT.

Revision ID: 0035
Revises: 0034
Create Date: 2025-01-15

K0 PostgreSQL Migration - P03 Consolidation

This migration corrects the column type for next_attempt_ts from TEXT to BIGINT
to match the dossier specification (Section 6.15). BIGINT enables:
- Numeric range comparisons for retry scheduling
- Efficient index scans for "next job to process" queries
- Unix epoch milliseconds storage matching kernel conventions
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0035"
down_revision: str = "0034"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Change next_attempt_ts from TEXT to BIGINT with data migration."""
    # Step 1: Add new column with correct type
    op.add_column(
        "st_outbox",
        sa.Column("next_attempt_ts_new", sa.BigInteger, nullable=True),
    )

    # Step 2: Migrate data - convert TEXT to BIGINT
    # Only convert values that are numeric strings (Unix timestamps)
    op.execute(
        """
        UPDATE st_outbox
        SET next_attempt_ts_new = CAST(next_attempt_ts AS BIGINT)
        WHERE next_attempt_ts IS NOT NULL
          AND next_attempt_ts ~ '^[0-9]+$'
    """
    )

    # Step 3: Drop old column
    op.drop_column("st_outbox", "next_attempt_ts")

    # Step 4: Rename new column to original name
    op.alter_column(
        "st_outbox",
        "next_attempt_ts_new",
        new_column_name="next_attempt_ts",
    )


def downgrade() -> None:
    """Revert next_attempt_ts back to TEXT type."""
    # Step 1: Add TEXT column
    op.add_column(
        "st_outbox",
        sa.Column("next_attempt_ts_old", sa.Text, nullable=True),
    )

    # Step 2: Migrate data - convert BIGINT to TEXT
    op.execute(
        """
        UPDATE st_outbox
        SET next_attempt_ts_old = CAST(next_attempt_ts AS TEXT)
        WHERE next_attempt_ts IS NOT NULL
    """
    )

    # Step 3: Drop BIGINT column
    op.drop_column("st_outbox", "next_attempt_ts")

    # Step 4: Rename back to original name
    op.alter_column(
        "st_outbox",
        "next_attempt_ts_old",
        new_column_name="next_attempt_ts",
    )
