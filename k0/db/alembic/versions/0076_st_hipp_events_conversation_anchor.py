"""Add conversation_anchor_ms and temporal_source columns to st_hipp_events.

Revision ID: 0076
Revises: 0075
Create Date: 2025-06-01

Epic 1.2 (GAP-002): Conversation Anchor + Temporal Source Persistence

Two new columns for the Chain A/B temporal split:

  conversation_anchor_ms  BIGINT  NULLABLE  -- K1 MW turn timestamp (ms).
      The actual moment the user chatted. Drives R2 episode formation
      when present. NULL for pre-Epic-1.2 rows and events without K1 anchor.

  temporal_source  TEXT  NULLABLE  -- Chain A provenance tag from M08
      normalize_timestamp: conversation_anchor/event_time/envelope_ts/now.
      Persisted so R0 reads it directly instead of binary heuristic.

New indexes (1):
  idx_hipp_conversation_anchor -- partial on non-null conversation_anchor_ms
      for temporal range queries on conversation time.

Backfill (Issue 1.2.6):
  Pre-existing rows have conversation_anchor_ms=NULL and temporal_source=NULL.
  Backfill sets conversation_anchor_ms = event_time_utc * 1000 for rows where
  event_time_utc was NOT overwritten by referred time (i.e. where
  temporal_resolved_epoch_ms IS NULL or matches event_time_utc within 1h tolerance).
"""

from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add conversation_anchor_ms, temporal_source columns and partial index."""
    # ------------------------------------------------------------------
    # 2 new columns
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE st_hipp_events
            ADD COLUMN IF NOT EXISTS conversation_anchor_ms  BIGINT,
            ADD COLUMN IF NOT EXISTS temporal_source          TEXT;
    """
    )

    # ------------------------------------------------------------------
    # Partial index: conversation_anchor_ms IS NOT NULL
    # Speeds up temporal range queries on conversation time
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hipp_conversation_anchor
            ON st_hipp_events (conversation_anchor_ms)
            WHERE conversation_anchor_ms IS NOT NULL;
    """
    )

    # ------------------------------------------------------------------
    # Backfill (Issue 1.2.6): Populate conversation_anchor_ms for rows
    # where event_time_utc was NOT overwritten by referred time.
    #
    # Heuristic: if temporal_resolved_epoch_ms is NULL or the resolved
    # epoch (converted to seconds) is within 1 hour of event_time_utc,
    # then event_time_utc IS the conversation time and we can backfill.
    # Otherwise, event_time_utc was likely overwritten by the old
    # Priority 1 (mw_resolved) bug and we leave conversation_anchor_ms
    # NULL (unknown).
    # ------------------------------------------------------------------
    op.execute(
        """
        UPDATE st_hipp_events
        SET conversation_anchor_ms = event_time_utc * 1000,
            temporal_source = 'event_time'
        WHERE conversation_anchor_ms IS NULL
          AND event_time_utc IS NOT NULL
          AND event_time_utc > 0
          AND (
              temporal_resolved_epoch_ms IS NULL
              OR temporal_resolved_epoch_ms = 0
              OR ABS(event_time_utc - (temporal_resolved_epoch_ms / 1000)) < 3600
          );
    """
    )


def downgrade() -> None:
    """Remove conversation_anchor_ms, temporal_source columns and index."""
    op.execute("DROP INDEX IF EXISTS idx_hipp_conversation_anchor;")
    op.execute(
        """
        ALTER TABLE st_hipp_events
            DROP COLUMN IF EXISTS conversation_anchor_ms,
            DROP COLUMN IF EXISTS temporal_source;
    """
    )
