"""Add 5 M5A cognitive signal columns to st_hipp_events.

Revision ID: 0074
Revises: 0073
Create Date: 2026-01-29

Epic 5A.1 -- Migration 0074: 5 New st_hipp_events Columns (M5A Signals)
Pre-production: no backward compatibility needed, tables can be rebuilt.

These 5 columns are NEW signals not covered by M3 Epic 3.9 (migration 0073).
They provide surprise, identity relevance, source reliability, memory tier,
and temporal anchor data for downstream P03 R1 enhanced importance scoring.

New columns:
  surprise_level        REAL     DEFAULT 0.0   -- MW surprise/unexpectedness [0.0, 1.0]
  identity_relevance    REAL     DEFAULT 0.0   -- How relevant to self-identity [0.0, 1.0]
  source_reliability    REAL     DEFAULT 1.0   -- Trustworthiness of source [0.0, 1.0]
  memory_tier           VARCHAR  DEFAULT 'routine' -- Classification: routine/notable/significant/landmark
  temporal_anchor_json  TEXT     DEFAULT '{}'  -- Resolved temporal anchor (JSON object)

New indexes (1):
  idx_hipp_memory_tier -- partial on non-routine tiers for fast retrieval
"""

from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add 5 M5A cognitive signal columns and 1 index to st_hipp_events."""
    # ------------------------------------------------------------------
    # M5A Cognitive Signals (5 columns)
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE st_hipp_events
            ADD COLUMN IF NOT EXISTS surprise_level        REAL DEFAULT 0.0,
            ADD COLUMN IF NOT EXISTS identity_relevance    REAL DEFAULT 0.0,
            ADD COLUMN IF NOT EXISTS source_reliability    REAL DEFAULT 1.0,
            ADD COLUMN IF NOT EXISTS memory_tier           VARCHAR(20) DEFAULT 'routine',
            ADD COLUMN IF NOT EXISTS temporal_anchor_json  TEXT DEFAULT '{}';
    """
    )

    # ------------------------------------------------------------------
    # Index: partial on non-routine memory tiers
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hipp_memory_tier
            ON st_hipp_events (memory_tier)
            WHERE memory_tier != 'routine';
    """
    )


def downgrade() -> None:
    """Remove M5A columns and index."""
    op.execute("DROP INDEX IF EXISTS idx_hipp_memory_tier;")
    op.execute(
        """
        ALTER TABLE st_hipp_events
            DROP COLUMN IF EXISTS surprise_level,
            DROP COLUMN IF EXISTS identity_relevance,
            DROP COLUMN IF EXISTS source_reliability,
            DROP COLUMN IF EXISTS memory_tier,
            DROP COLUMN IF EXISTS temporal_anchor_json;
    """
    )
