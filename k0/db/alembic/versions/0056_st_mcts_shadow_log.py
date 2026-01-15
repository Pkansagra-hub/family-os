"""Add st_mcts_shadow_log table for shadow validation.

Revision ID: 0056
Revises: 0055
Create Date: 2026-01-12

P03 Consolidation Pipeline - MCTS Shadow Validation Log

Brain Analog: Metacognitive Validation Logging
Role: Store heuristic vs MCTS decision comparisons for shadow mode

Issue Reference: M8_EXECUTION.md Issue 8.1.14
Dossier Reference: P03 Consolidation Dossier Section 4.6.0

This table captures shadow mode comparisons between heuristic and MCTS
decisions, enabling:
- Validation of MCTS benefit before enabling in production
- Outcome tracking after 7-day evaluation window
- Promotion logic: shadow -> enabled_low based on thresholds

Shadow Mode Behavior:
1. Compute heuristic choice (fast, deterministic)
2. Run MCTS (compute-intensive, probabilistic)
3. Apply heuristic choice (MCTS is read-only)
4. Log both choices for later evaluation

Promotion Thresholds (from dossier):
- Agreement >95%: Keep disabled (MCTS not worth the compute)
- Differ >20% AND MCTS better >55%: Promote to enabled_low

Columns:
- decision_id: ULID primary key (per A.0.1 invariant - NOT UUID)
- cycle_id: Parent consolidation cycle for grouping
- decision_type: merge, causal, cluster, etc.
- heuristic_choice: Action chosen by heuristic
- mcts_choice: Action chosen by MCTS
- choices_differ: Whether heuristic != mcts
- context_json: Rich context for analysis
- applied_choice: Always heuristic in shadow mode
- outcome_heuristic: Outcome score from heuristic (evaluated after 7d)
- outcome_mcts: Predicted outcome if MCTS was applied
- mcts_better: Whether MCTS would have produced better outcome
- evaluated_at: When outcome was evaluated (7 days after creation)
- created_at: Epoch milliseconds timestamp

Indexes:
- decision_type: Filter by decision category
- created_at: Time-range queries for evaluation window
- choices_differ: Filter disagreements for analysis
- evaluated_at: Find decisions pending evaluation
- cycle_id: Group by consolidation cycle
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0056"
down_revision: str = "0055"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_mcts_shadow_log table for shadow validation."""
    # ============================================================
    # st_mcts_shadow_log - Shadow Mode Decision Comparisons
    # ============================================================
    op.create_table(
        "st_mcts_shadow_log",
        # Primary key: ULID (26 chars), NOT UUID per A.0.1
        sa.Column("decision_id", sa.Text(), primary_key=True),
        # Parent cycle for grouping
        sa.Column("cycle_id", sa.Text(), nullable=False),
        # Decision classification
        sa.Column("decision_type", sa.Text(), nullable=False),
        # Heuristic vs MCTS comparison
        sa.Column("heuristic_choice", sa.Text(), nullable=False),
        sa.Column("mcts_choice", sa.Text(), nullable=False),
        sa.Column(
            "choices_differ",
            sa.Boolean(),
            nullable=False,
        ),
        # Rich context for retrospective analysis
        sa.Column(
            "context_json",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
        # Applied choice (always heuristic in shadow mode)
        sa.Column("applied_choice", sa.Text(), nullable=False),
        # Outcome tracking (filled in after evaluation window)
        sa.Column("outcome_heuristic", sa.Float(), nullable=True),
        sa.Column("outcome_mcts", sa.Float(), nullable=True),
        sa.Column("mcts_better", sa.Boolean(), nullable=True),
        # Evaluation timestamp (7 days after creation)
        sa.Column("evaluated_at", sa.BigInteger(), nullable=True),
        # Creation timestamp: epoch milliseconds (per K0 convention)
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )

    # ============================================================
    # Indexes for efficient querying
    # ============================================================

    # Filter by decision type (merge, causal, cluster, etc.)
    op.create_index(
        "idx_shadow_log_type",
        "st_mcts_shadow_log",
        ["decision_type"],
    )

    # Time-range queries for evaluation window
    op.create_index(
        "idx_shadow_log_created",
        "st_mcts_shadow_log",
        ["created_at"],
    )

    # Filter disagreements for analysis
    op.create_index(
        "idx_shadow_log_differ",
        "st_mcts_shadow_log",
        ["choices_differ"],
        postgresql_where=sa.text("choices_differ = true"),
    )

    # Find decisions pending or completed evaluation
    op.create_index(
        "idx_shadow_log_evaluated",
        "st_mcts_shadow_log",
        ["evaluated_at"],
    )

    # Group by consolidation cycle
    op.create_index(
        "idx_shadow_log_cycle",
        "st_mcts_shadow_log",
        ["cycle_id"],
    )

    # Compound index: type + created_at for filtered time-range queries
    op.create_index(
        "idx_shadow_log_type_created",
        "st_mcts_shadow_log",
        ["decision_type", "created_at"],
    )

    # Find unevaluated decisions older than 7 days
    op.create_index(
        "idx_shadow_log_pending_eval",
        "st_mcts_shadow_log",
        ["created_at"],
        postgresql_where=sa.text("evaluated_at IS NULL"),
    )


def downgrade() -> None:
    """Drop st_mcts_shadow_log table and indexes."""
    # Drop indexes first
    op.drop_index("idx_shadow_log_pending_eval", table_name="st_mcts_shadow_log")
    op.drop_index("idx_shadow_log_type_created", table_name="st_mcts_shadow_log")
    op.drop_index("idx_shadow_log_cycle", table_name="st_mcts_shadow_log")
    op.drop_index("idx_shadow_log_evaluated", table_name="st_mcts_shadow_log")
    op.drop_index("idx_shadow_log_differ", table_name="st_mcts_shadow_log")
    op.drop_index("idx_shadow_log_created", table_name="st_mcts_shadow_log")
    op.drop_index("idx_shadow_log_type", table_name="st_mcts_shadow_log")

    # Drop table
    op.drop_table("st_mcts_shadow_log")
