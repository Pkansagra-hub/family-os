"""Add P03 consolidation columns to st_hipp_events.

Revision ID: 0052
Revises: 0051
Create Date: 2026-01-08

Adds columns required by P03 consolidation pipeline R6/R7 phases:
- reconciliation_action: Decision type (REINFORCE, EXTEND, CREATE, etc.)
- best_match_id: Matched truth record ID
- best_match_layer: Truth layer of match (st_epi, st_sem, etc.)
- similarity_score: Cosine similarity to best match [0, 1]
- confidence: Decision confidence [0, 1]
- reconciliation_reason: Human-readable explanation
- consolidated_at_ms: Timestamp when consolidation completed (ms)

These complement existing columns:
- reconciliation_decision (already exists)
- truth_match_id (already exists)
- truth_match_similarity (already exists)
- cluster_confidence (already exists)
- consolidated_at (already exists)
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add P03 consolidation columns to st_hipp_events."""
    # reconciliation_action: Decision type from R3/R4
    # Values: REINFORCE, EXTEND, CREATE, EVOLVE, SKIP, PRUNE, CONTRADICT, PENDING
    op.add_column(
        "st_hipp_events",
        sa.Column("reconciliation_action", sa.Text(), nullable=True),
    )

    # best_match_id: ID of matched truth record (episodic/semantic)
    op.add_column(
        "st_hipp_events",
        sa.Column("best_match_id", sa.Text(), nullable=True),
    )

    # best_match_layer: Which truth table the match is from
    # Values: st_epi (episodic), st_sem (semantic), st_kg (knowledge graph)
    op.add_column(
        "st_hipp_events",
        sa.Column("best_match_layer", sa.Text(), nullable=True),
    )

    # similarity_score: Cosine similarity to best match [0, 1]
    op.add_column(
        "st_hipp_events",
        sa.Column("similarity_score", sa.Float(), nullable=True),
    )

    # confidence: Overall decision confidence [0, 1]
    op.add_column(
        "st_hipp_events",
        sa.Column("confidence", sa.Float(), nullable=True),
    )

    # reconciliation_reason: Human-readable explanation
    op.add_column(
        "st_hipp_events",
        sa.Column("reconciliation_reason", sa.Text(), nullable=True),
    )

    # consolidated_at_ms: Timestamp when consolidation completed (milliseconds)
    # Note: consolidated_at already exists as bigint, this is an alias for clarity
    op.add_column(
        "st_hipp_events",
        sa.Column("consolidated_at_ms", sa.BigInteger(), nullable=True),
    )

    # Add index for best_match lookups
    op.create_index(
        "idx_hipp_events_best_match_id",
        "st_hipp_events",
        ["best_match_id"],
        unique=False,
        postgresql_where=sa.text("best_match_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove P03 consolidation columns from st_hipp_events."""
    op.drop_index("idx_hipp_events_best_match_id", table_name="st_hipp_events")
    op.drop_column("st_hipp_events", "consolidated_at_ms")
    op.drop_column("st_hipp_events", "reconciliation_reason")
    op.drop_column("st_hipp_events", "confidence")
    op.drop_column("st_hipp_events", "similarity_score")
    op.drop_column("st_hipp_events", "best_match_layer")
    op.drop_column("st_hipp_events", "best_match_id")
    op.drop_column("st_hipp_events", "reconciliation_action")
