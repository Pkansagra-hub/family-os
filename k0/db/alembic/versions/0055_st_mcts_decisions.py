"""Add st_mcts_decisions table for MCTS decision tracing.

Revision ID: 0055
Revises: 0054
Create Date: 2026-01-11

P03 Consolidation Pipeline - MCTS Decision Persistence

Brain Analog: Metacognitive Decision Logging
Role: Store MCTS decision traces for analysis and retrospective learning

Issue Reference: M8_EXECUTION.md Issue 8.1.7
Dossier Reference: P03 Consolidation Dossier Section 4.6, Appendix D

This table captures every MCTS-based decision made during R5 dream-like
exploration, enabling:
- Post-hoc analysis of decision quality
- Retrospective learning (Issue 8.1.14 shadow mode)
- Compute budget tracking per cycle
- Early termination pattern analysis

Columns:
- decision_id: ULID primary key (per A.0.1 invariant - NOT UUID)
- cycle_id: Parent consolidation cycle for budget tracking
- decision_type: merge, causal, cluster, insight_ranking, etc.
- context_json: Decision context (episode IDs, entity IDs, etc.)
- rollouts_allocated: Rollouts allocated based on decision importance
- rollouts_executed: Actual rollouts performed (may be less due to early term)
- early_termination: Whether decision terminated early
- termination_reason: clear_winner, low_uncertainty, budget_exhausted
- chosen_action: The action selected by MCTS
- value_estimate: Expected value of chosen action
- confidence_interval_width: CI width at termination
- compute_ms: Wall-clock compute time
- created_at: Epoch milliseconds timestamp

Indexes:
- decision_type: Filter by merge vs causal vs cluster decisions
- created_at: Time-range queries for analysis
- cycle_id: Group decisions by consolidation cycle
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0055"
down_revision: str = "0054"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_mcts_decisions table for decision tracing."""
    # ============================================================
    # st_mcts_decisions — MCTS Decision Traces
    # ============================================================
    op.create_table(
        "st_mcts_decisions",
        # Primary key: ULID (26 chars), NOT UUID per A.0.1
        sa.Column("decision_id", sa.Text(), primary_key=True),
        # Parent cycle for budget tracking
        sa.Column("cycle_id", sa.Text(), nullable=False),
        # Decision classification
        sa.Column("decision_type", sa.Text(), nullable=False),
        # Rich context for retrospective analysis
        sa.Column(
            "context_json",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
        # Rollout allocation and execution
        sa.Column("rollouts_allocated", sa.Integer(), nullable=True),
        sa.Column("rollouts_executed", sa.Integer(), nullable=True),
        # Early termination tracking
        sa.Column(
            "early_termination",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("termination_reason", sa.Text(), nullable=True),
        # Decision outcome
        sa.Column("chosen_action", sa.Text(), nullable=True),
        sa.Column("value_estimate", sa.Float(), nullable=True),
        sa.Column("confidence_interval_width", sa.Float(), nullable=True),
        # Performance tracking
        sa.Column("compute_ms", sa.Integer(), nullable=True),
        # Timestamp: epoch milliseconds (per K0 convention)
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )

    # ============================================================
    # Indexes for efficient querying
    # ============================================================

    # Filter by decision type (merge, causal, cluster, etc.)
    op.create_index(
        "idx_mcts_decisions_type",
        "st_mcts_decisions",
        ["decision_type"],
    )

    # Time-range queries for analysis dashboards
    op.create_index(
        "idx_mcts_decisions_created",
        "st_mcts_decisions",
        ["created_at"],
    )

    # Group decisions by cycle for budget tracking
    op.create_index(
        "idx_mcts_decisions_cycle",
        "st_mcts_decisions",
        ["cycle_id"],
    )

    # Compound index: type + created_at for filtered time-range queries
    op.create_index(
        "idx_mcts_decisions_type_created",
        "st_mcts_decisions",
        ["decision_type", "created_at"],
    )

    # Filter by early termination for pattern analysis
    op.create_index(
        "idx_mcts_decisions_early_term",
        "st_mcts_decisions",
        ["early_termination"],
        postgresql_where=sa.text("early_termination = true"),
    )


def downgrade() -> None:
    """Drop st_mcts_decisions table and indexes."""
    # Drop indexes first
    op.drop_index("idx_mcts_decisions_early_term", table_name="st_mcts_decisions")
    op.drop_index("idx_mcts_decisions_type_created", table_name="st_mcts_decisions")
    op.drop_index("idx_mcts_decisions_cycle", table_name="st_mcts_decisions")
    op.drop_index("idx_mcts_decisions_created", table_name="st_mcts_decisions")
    op.drop_index("idx_mcts_decisions_type", table_name="st_mcts_decisions")

    # Drop table
    op.drop_table("st_mcts_decisions")
