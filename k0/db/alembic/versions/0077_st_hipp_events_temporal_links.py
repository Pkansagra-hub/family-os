"""Add temporal_links_json column to st_hipp_events.

Revision ID: 0077
Revises: 0076
Create Date: 2025-06-02

Epic 2.4 (GAP-002): Multi-Link Temporal Model -- K0 Receiver Changes

New column:

  temporal_links_json  TEXT  NULLABLE  -- JSON array of TemporalLink objects.
      Each element: {mentioned_time, resolved_epoch_ms, uncertainty_window_ms,
      link_type, confidence}. Max 5 links per atom.
      From K1 MW v2.1 MemoryAtom.temporal_links. Stored as TEXT (JSON) for
      flexible querying. NULL for pre-v2.1 atoms.

No backfill needed: v2.0 atoms did not have temporal_links. M08 backward
compat logic constructs a single-element list from body.temporal when
temporal_links is absent, but only for NEW events going forward.
"""

from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add temporal_links_json column."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            ADD COLUMN IF NOT EXISTS temporal_links_json TEXT;
    """
    )


def downgrade() -> None:
    """Remove temporal_links_json column."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            DROP COLUMN IF EXISTS temporal_links_json;
    """
    )
