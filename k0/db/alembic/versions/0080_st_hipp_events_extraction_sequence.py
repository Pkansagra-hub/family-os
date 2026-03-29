"""Add extraction_sequence column to st_hipp_events.

Revision ID: 0080
Revises: 0079
Create Date: 2026-03-05

Epic 4.1 (GAP-002): Intra-turn extraction ordering.

New column:

  extraction_sequence  INTEGER  NULLABLE DEFAULT 0
      0-based ordinal of atom within a single K1 turn extraction batch.

Constraint:

  ck_extraction_sequence
      extraction_sequence IS NULL OR extraction_sequence BETWEEN 0 AND 5
"""

from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


_CHECK_NAME = "ck_extraction_sequence"


def upgrade() -> None:
    """Add extraction_sequence column with bounded check constraint."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            ADD COLUMN IF NOT EXISTS extraction_sequence INTEGER DEFAULT 0;
    """
    )

    op.execute(
        f"""
        ALTER TABLE st_hipp_events
            DROP CONSTRAINT IF EXISTS {_CHECK_NAME};
    """
    )

    op.execute(
        f"""
        ALTER TABLE st_hipp_events
            ADD CONSTRAINT {_CHECK_NAME}
            CHECK (
                extraction_sequence IS NULL OR
                extraction_sequence BETWEEN 0 AND 5
            );
    """
    )


def downgrade() -> None:
    """Drop extraction_sequence constraint and column."""
    op.execute(
        f"""
        ALTER TABLE st_hipp_events
            DROP CONSTRAINT IF EXISTS {_CHECK_NAME};
    """
    )

    op.execute(
        """
        ALTER TABLE st_hipp_events
            DROP COLUMN IF EXISTS extraction_sequence;
    """
    )
