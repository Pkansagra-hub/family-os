"""Add spatial_context_json column to st_hipp_events.

Revision ID: 0082
Revises: 0081
Create Date: 2026-03-05

Epic 4.3 (GAP-002): Spatial transition signal.

New column:

  spatial_context_json  TEXT  NULLABLE DEFAULT NULL
      Bundled spatial transition context.
      Example: '{"transition_from_place": "restaurant", "transition_mode": "drove"}'
"""

from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add spatial_context_json TEXT column."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            ADD COLUMN IF NOT EXISTS spatial_context_json TEXT DEFAULT NULL;
    """
    )


def downgrade() -> None:
    """Remove spatial_context_json column."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            DROP COLUMN IF EXISTS spatial_context_json;
    """
    )
