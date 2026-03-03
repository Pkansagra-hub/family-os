"""Add 16 MW v2 signal columns to st_hipp_events (Epic 3.9).

Revision ID: 0073
Revises: 0072
Create Date: 2026-01-28

Epic 3.9 -- Migration 0066: 16 New st_hipp_events Columns
Pre-production: no backward compatibility needed, tables can be rebuilt.
Contract Reference: k0/contracts/schemas/st_hipp_events_v2.columns.yaml

Copied from k0/db/migrations/versions/0066_st_hipp_events_mw_v2_columns.py
Renumbered to fit alembic chain (0071 -> 0072 -> 0073).

New columns by group:
  Narrative Context (3): narrative_thread_id, narrative_arc_position,
                         narrative_is_goal_event
  Affect Extension  (1): affect_dominance
  Entity Salience   (1): entity_salience_json
  Temporal Ext.     (3): temporal_mentioned_time, temporal_resolved_epoch_ms,
                         temporal_orientation
  Cognitive Dims.   (6): intent_type, goal_context, source_type, novelty,
                         elaboration_depth, identity_domains_json
  Signal Provenance (2): participant_relationships_json, k1_signal_version

New indexes (3):
  idx_hipp_narrative_thread      -- partial on narrative_thread_id
  idx_hipp_temporal_orientation  -- partial on FUTURE_COMMITMENT
  idx_hipp_k1_signal_version     -- full on k1_signal_version

CHECK constraints enforced in application layer (M13 validation):
  - affect_dominance: 0.0..1.0
  - narrative_arc_position: EXPOSITION | RISING_ACTION | CLIMAX | RESOLUTION
  - temporal_orientation: PAST | ONGOING | FUTURE_COMMITMENT
  - source_type: user_stated | user_implied | device_observed | system_inferred
  - novelty: ROUTINE | EXPECTED | NOVEL | SURPRISING
  - elaboration_depth: MENTION | DISCUSSED | ELABORATED | DEEPLY_PROCESSED
"""

from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add 16 MW v2 signal columns and 3 indexes to st_hipp_events."""
    # ------------------------------------------------------------------
    # Narrative Context (3 columns) -- Group 14
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN narrative_thread_id TEXT")
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN narrative_arc_position TEXT")
    op.execute(
        "ALTER TABLE st_hipp_events"
        " ADD COLUMN narrative_is_goal_event BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # ------------------------------------------------------------------
    # Affect Extension (1 column) -- Group 11
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN affect_dominance FLOAT")

    # ------------------------------------------------------------------
    # Entity Salience (1 column) -- Group 11
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE st_hipp_events" " ADD COLUMN entity_salience_json TEXT NOT NULL DEFAULT '{}'"
    )

    # ------------------------------------------------------------------
    # Temporal Extensions (3 columns) -- Group 5
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN temporal_mentioned_time TEXT")
    op.execute("ALTER TABLE st_hipp_events" " ADD COLUMN temporal_resolved_epoch_ms BIGINT")
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN temporal_orientation TEXT")

    # ------------------------------------------------------------------
    # Cognitive Dimensions (6 columns) -- Group 15
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN intent_type TEXT")
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN goal_context TEXT")
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN source_type TEXT")
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN novelty TEXT")
    op.execute("ALTER TABLE st_hipp_events ADD COLUMN elaboration_depth TEXT")
    op.execute(
        "ALTER TABLE st_hipp_events" " ADD COLUMN identity_domains_json TEXT NOT NULL DEFAULT '[]'"
    )

    # ------------------------------------------------------------------
    # Signal Provenance (2 columns) -- Groups 7 & 13
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE st_hipp_events"
        " ADD COLUMN participant_relationships_json TEXT NOT NULL DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE st_hipp_events" " ADD COLUMN k1_signal_version TEXT NOT NULL DEFAULT '2.0'"
    )

    # ------------------------------------------------------------------
    # Indexes (3) for downstream consumers (P03/R5)
    # ------------------------------------------------------------------
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hipp_narrative_thread"
        " ON st_hipp_events(narrative_thread_id)"
        " WHERE narrative_thread_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hipp_temporal_orientation"
        " ON st_hipp_events(temporal_orientation)"
        " WHERE temporal_orientation = 'FUTURE_COMMITMENT'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hipp_k1_signal_version"
        " ON st_hipp_events(k1_signal_version)"
    )

    # ------------------------------------------------------------------
    # CHECK constraints -- SQLite does not support ADD CONSTRAINT.
    # Enforced in application layer (M13 validation, Epic 3.18).
    #
    # ck_hipp_affect_dominance:
    #   affect_dominance IS NULL
    #   OR (affect_dominance >= 0.0 AND affect_dominance <= 1.0)
    #
    # ck_hipp_narrative_arc_position:
    #   narrative_arc_position IS NULL
    #   OR narrative_arc_position IN (
    #       'EXPOSITION','RISING_ACTION','CLIMAX','RESOLUTION')
    #
    # ck_hipp_temporal_orientation:
    #   temporal_orientation IS NULL
    #   OR temporal_orientation IN ('PAST','ONGOING','FUTURE_COMMITMENT')
    #
    # ck_hipp_source_type:
    #   source_type IS NULL
    #   OR source_type IN (
    #       'user_stated','user_implied','device_observed','system_inferred')
    #
    # ck_hipp_novelty:
    #   novelty IS NULL
    #   OR novelty IN ('ROUTINE','EXPECTED','NOVEL','SURPRISING')
    #
    # ck_hipp_elaboration_depth:
    #   elaboration_depth IS NULL
    #   OR elaboration_depth IN (
    #       'MENTION','DISCUSSED','ELABORATED','DEEPLY_PROCESSED')
    # ------------------------------------------------------------------


def downgrade() -> None:
    """Remove MW v2 columns and indexes from st_hipp_events.

    Requires SQLite >= 3.35.0 for ALTER TABLE DROP COLUMN support.
    Pre-production: DROP TABLE + re-run all migrations is also acceptable.
    """
    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_hipp_k1_signal_version")
    op.execute("DROP INDEX IF EXISTS idx_hipp_temporal_orientation")
    op.execute("DROP INDEX IF EXISTS idx_hipp_narrative_thread")

    # Drop columns in reverse order (Signal Provenance)
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN k1_signal_version")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN participant_relationships_json")

    # Cognitive Dimensions
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN identity_domains_json")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN elaboration_depth")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN novelty")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN source_type")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN goal_context")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN intent_type")

    # Temporal Extensions
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN temporal_orientation")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN temporal_resolved_epoch_ms")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN temporal_mentioned_time")

    # Entity Salience
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN entity_salience_json")

    # Affect Extension
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN affect_dominance")

    # Narrative Context
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN narrative_is_goal_event")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN narrative_arc_position")
    op.execute("ALTER TABLE st_hipp_events DROP COLUMN narrative_thread_id")
