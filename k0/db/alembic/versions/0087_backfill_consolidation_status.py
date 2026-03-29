"""Backfill consolidation_status for legacy orphan events (Epic 6.6.3).

Revision ID: 0087
Revises: 0086
Create Date: 2026-03-10

Milestone 6 Epic 6.6 Issue 6.6.3: Orphan Event Rescue

266 events (20% of the 1,360-event corpus) have NULL consolidation_status
because they were processed before the R7 _writeback_status() mechanism
was added. These orphan events cause the drain loop to re-process them
on every run, potentially creating duplicate episodes.

Root cause analysis:
  1. Events processed before R7 writeback existed (most common)
  2. Events whose embedding_status was not READY at consolidation time
  3. Events with wal_pos below the committed offset (skipped permanently)

Resolution: Set orphan events that already appear in st_epi
(via source_events_json) to 'CONSOLIDATED'. Events not in any episode
are set to 'PENDING' so the next drain cycle can attempt processing.

This migration is idempotent: it only updates rows where
consolidation_status IS NULL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0087"
down_revision: str = "0086"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Backfill consolidation_status for orphan events.

    Two-pass approach:
    1. Events referenced in st_epi.source_events_json -> CONSOLIDATED
    2. Remaining NULL events with embedding_status = 'READY' -> PENDING
       (so they get re-processed in the next drain cycle)
    """
    # Pass 1: Mark events that are already in episodes as CONSOLIDATED.
    # st_epi.source_events_json contains JSON arrays of event IDs.
    # We use a lateral join to extract event IDs from the JSON array.
    op.execute(
        """
        UPDATE st_hipp_events h
        SET consolidation_status = 'CONSOLIDATED',
            consolidation_cycle_id = 'backfill-0087',
            consolidated_at = EXTRACT(EPOCH FROM NOW()) * 1000,
            reconciliation_reason = 'Backfill 0087: event found in st_epi episode'
        FROM (
            SELECT DISTINCT jsonb_array_elements_text(
                source_events_json::jsonb
            ) AS event_id
            FROM st_epi
            WHERE source_events_json IS NOT NULL
              AND source_events_json != '[]'
              AND source_events_json != ''
        ) epi_events
        WHERE h.event_id = epi_events.event_id
          AND h.consolidation_status IS NULL
        """
    )

    # Pass 2: Remaining orphans with ready embeddings -> PENDING
    # These will be picked up by the next R0 drain cycle.
    op.execute(
        """
        UPDATE st_hipp_events
        SET consolidation_status = 'PENDING',
            reconciliation_reason = 'Backfill 0087: orphan event, pending re-processing'
        WHERE consolidation_status IS NULL
          AND embedding_status = 'READY'
        """
    )


def downgrade() -> None:
    """Revert backfill by clearing the fields we set."""
    op.execute(
        """
        UPDATE st_hipp_events
        SET consolidation_status = NULL,
            consolidated_at = NULL,
            reconciliation_reason = NULL
        WHERE consolidation_cycle_id = 'backfill-0087'
        """
    )
    op.execute(
        """
        UPDATE st_hipp_events
        SET consolidation_status = NULL,
            reconciliation_reason = NULL
        WHERE reconciliation_reason = 'Backfill 0087: orphan event, pending re-processing'
        """
    )
