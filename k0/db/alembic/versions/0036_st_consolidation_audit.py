"""Create st_consolidation_audit table for P03 decision tracking.

Revision ID: 0036
Revises: 0035
Create Date: 2025-01-15

K0 PostgreSQL Migration - P03 Consolidation

This table provides a complete audit trail for consolidation decisions,
enabling explainability, debugging, and learning analysis.

Dossier Reference: Section 6.20 st_consolidation_audit
Retention: 90 days detailed records, then aggregate to daily summaries
Isolation: RLS enforced for multi-tenant security
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0036"
down_revision: str = "0035"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_consolidation_audit table with all columns and indexes."""
    op.create_table(
        "st_consolidation_audit",
        # Primary key - ULID for audit record
        sa.Column("audit_id", sa.Text, primary_key=True),
        # Core reference columns
        sa.Column("memory_id", sa.Text, nullable=False),
        sa.Column("source_table", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        # Formula tracking
        sa.Column("formula_used", sa.Text, nullable=True),
        sa.Column("formula_version", sa.Text, nullable=True),
        # Input/output JSON for debugging
        sa.Column("inputs_json", sa.Text, nullable=True),  # JSONB stored as TEXT
        sa.Column("outputs_json", sa.Text, nullable=True),  # JSONB stored as TEXT
        # Explainability
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("decision_id", sa.Text, nullable=True),
        # Context columns
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("cycle_id", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        # Outcome tracking columns (from Section 1.4.7)
        sa.Column("threshold_used", sa.Float, nullable=True),
        sa.Column("threshold_name", sa.Text, nullable=True),
        sa.Column("outcome_evaluated", sa.Boolean, nullable=True, server_default="false"),
        sa.Column("outcome_success", sa.Boolean, nullable=True),
        sa.Column("evaluated_at", sa.BigInteger, nullable=True),
        # CHECK constraint for action values
        sa.CheckConstraint(
            "action IN ('REINFORCE', 'DECAY', 'ARCHIVE', 'MERGE', 'CREATE', "
            "'EXTEND', 'PRUNE', 'SKIP', 'CONTRADICT')",
            name="ck_audit_action",
        ),
    )

    # Create indexes per dossier Section 6.20
    # idx_audit_memory_time - Memory history queries
    op.create_index(
        "idx_audit_memory_time",
        "st_consolidation_audit",
        ["memory_id", "created_at"],
    )

    # idx_audit_action - Action analysis
    op.create_index(
        "idx_audit_action",
        "st_consolidation_audit",
        ["action", "created_at"],
    )

    # idx_audit_formula - Formula analysis
    op.create_index(
        "idx_audit_formula",
        "st_consolidation_audit",
        ["formula_used", "created_at"],
    )

    # idx_audit_decision - Outcome linkage
    op.create_index(
        "idx_audit_decision",
        "st_consolidation_audit",
        ["decision_id"],
    )

    # idx_consolidation_audit_outcome_eval - Partial index for pending evaluations
    op.create_index(
        "idx_consolidation_audit_outcome_eval",
        "st_consolidation_audit",
        ["outcome_evaluated", "created_at"],
        postgresql_where=sa.text("outcome_evaluated = FALSE"),
    )

    # Canonical lookup index
    op.create_index(
        "idx_audit_canonical",
        "st_consolidation_audit",
        ["tenant_id", "space_id", "created_at"],
    )

    # Enable Row Level Security for multi-tenant isolation
    op.execute("ALTER TABLE st_consolidation_audit ENABLE ROW LEVEL SECURITY")

    # Create RLS policy for space isolation
    op.execute(
        """
        CREATE POLICY audit_isolation ON st_consolidation_audit
            FOR ALL USING (space_id = current_setting('app.current_space_id', true))
    """
    )


def downgrade() -> None:
    """Drop st_consolidation_audit table and all indexes."""
    # Drop RLS policy first
    op.execute("DROP POLICY IF EXISTS audit_isolation ON st_consolidation_audit")

    # Drop indexes
    op.drop_index("idx_audit_canonical", table_name="st_consolidation_audit")
    op.drop_index("idx_consolidation_audit_outcome_eval", table_name="st_consolidation_audit")
    op.drop_index("idx_audit_decision", table_name="st_consolidation_audit")
    op.drop_index("idx_audit_formula", table_name="st_consolidation_audit")
    op.drop_index("idx_audit_action", table_name="st_consolidation_audit")
    op.drop_index("idx_audit_memory_time", table_name="st_consolidation_audit")

    # Drop table
    op.drop_table("st_consolidation_audit")
