"""Add location_hierarchy_json column to st_hipp_events.

Revision ID: 0081
Revises: 0080
Create Date: 2026-03-05

Epic 4.2 (GAP-002): Spatial hierarchy signal.

New column:

  location_hierarchy_json  TEXT  NULLABLE DEFAULT NULL
      JSON array of spatial hierarchy levels from most specific to most general.
      Example: '["kitchen", "home", "Seattle"]'
"""

from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add location_hierarchy_json TEXT column."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            ADD COLUMN IF NOT EXISTS location_hierarchy_json TEXT DEFAULT NULL;
    """
    )


def downgrade() -> None:
    """Remove location_hierarchy_json column."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            DROP COLUMN IF EXISTS location_hierarchy_json;
    """
    )
