"""Add spatial_familiarity column to st_hipp_events.

Revision ID: 0079
Revises: 0078
Create Date: 2026-03-05

Epic 3.3 (GAP-002): Spatial Familiarity Tracking.

New column:

  spatial_familiarity  TEXT  NULLABLE
      Computed by K0 P02 from historical place visits.
      Allowed values: FIRST_VISIT, OCCASIONAL, REGULAR, DAILY.

Constraint:

  ck_spatial_familiarity
      spatial_familiarity IS NULL OR spatial_familiarity IN
      ('FIRST_VISIT', 'OCCASIONAL', 'REGULAR', 'DAILY')
"""

from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


_CHECK_NAME = "ck_spatial_familiarity"


def upgrade() -> None:
    """Add spatial_familiarity column with enum-style check constraint."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            ADD COLUMN IF NOT EXISTS spatial_familiarity TEXT;
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
                spatial_familiarity IS NULL OR
                spatial_familiarity IN ('FIRST_VISIT', 'OCCASIONAL', 'REGULAR', 'DAILY')
            );
    """
    )


def downgrade() -> None:
    """Drop spatial_familiarity constraint and column."""
    op.execute(
        f"""
        ALTER TABLE st_hipp_events
            DROP CONSTRAINT IF EXISTS {_CHECK_NAME};
    """
    )

    op.execute(
        """
        ALTER TABLE st_hipp_events
            DROP COLUMN IF EXISTS spatial_familiarity;
    """
    )
