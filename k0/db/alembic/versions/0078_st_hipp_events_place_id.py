"""Add place_id column to st_hipp_events.

Revision ID: 0078
Revises: 0077
Create Date: 2026-03-05

Epic 3.2 (GAP-002): Spatial Identity -- stable place_id persistence.

New column:

  place_id  TEXT  NULLABLE  -- Stable place identity from K1 PlaceResolver.
      Format: place_<slug>, e.g. place_olive_garden.
      Nullable because many atoms do not resolve to a place identity.

New index:

  ix_st_hipp_events_place_id (tenant_id, place_id) partial where place_id IS NOT NULL
      Supports familiarity queries and place-based retrieval.
"""

from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add place_id column and partial index."""
    op.execute(
        """
        ALTER TABLE st_hipp_events
            ADD COLUMN IF NOT EXISTS place_id TEXT;
    """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_st_hipp_events_place_id
            ON st_hipp_events (tenant_id, place_id)
            WHERE place_id IS NOT NULL;
    """
    )


def downgrade() -> None:
    """Drop place_id partial index and column."""
    op.execute("DROP INDEX IF EXISTS ix_st_hipp_events_place_id;")
    op.execute(
        """
        ALTER TABLE st_hipp_events
            DROP COLUMN IF EXISTS place_id;
    """
    )
