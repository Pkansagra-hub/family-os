"""Add P03-specific columns to st_dlq for dossier compliance.

Revision ID: 0045
Revises: 0044
Create Date: 2026-01-01

P03 Consolidation Dossier Reconciliation (Issue 2.3.10)

The existing st_dlq table (migration 0009) was designed as a generic K0 DLQ
for all pipelines. The P03 dossier §13.4 specifies additional P03-specific
columns for enhanced error tracking and retry semantics.

Decision: Option C (Additive Approach)
- Keep existing generic columns for backward compatibility
- Add P03-specific columns as NULLABLE to avoid breaking existing entries
- Add CHECK constraint for error_type classification
- Add partial index for P03-specific queries

Columns Added:
- pipeline_id: TEXT (identifies source pipeline, e.g., 'p03_consolidation')
- phase: TEXT (P03 phase: R0-R8)
- event_id: TEXT (source event reference)
- entity_id: TEXT (related entity reference)
- error_type: TEXT with CHECK constraint (TRANSIENT, VALIDATION, LOGIC, FATAL)
- error_code: TEXT (structured error code)
- stack_trace: TEXT (optional stack trace)
- max_attempts: INTEGER (retry limit)
- resolved_at: BIGINT (resolution timestamp)
- resolved_by: TEXT (who resolved)
- resolution_notes: TEXT (resolution details)
- updated_at: BIGINT (last update timestamp)

Also adds 'RESOLVED', 'ABANDONED', 'MANUAL_REVIEW' to state CHECK constraint.

References:
- Dossier: docs/pipelines/P03_consolidation_dossier_v2.md §13.4
- Issue: docs/TEMP_EXECUTION_DOCS/M2_EXECUTION.md Issue 2.3.10
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0045"
down_revision: str = "0044"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add P03-specific columns to st_dlq."""
    # =========================================================================
    # ADD P03-SPECIFIC COLUMNS
    # =========================================================================

    # Pipeline identification
    op.add_column("st_dlq", sa.Column("pipeline_id", sa.Text, nullable=True))
    op.add_column("st_dlq", sa.Column("phase", sa.Text, nullable=True))

    # Event/entity references
    op.add_column("st_dlq", sa.Column("event_id", sa.Text, nullable=True))
    op.add_column("st_dlq", sa.Column("entity_id", sa.Text, nullable=True))

    # Enhanced error tracking
    op.add_column("st_dlq", sa.Column("error_type", sa.Text, nullable=True))
    op.add_column("st_dlq", sa.Column("error_code", sa.Text, nullable=True))
    op.add_column("st_dlq", sa.Column("stack_trace", sa.Text, nullable=True))

    # Extended retry tracking
    op.add_column(
        "st_dlq",
        sa.Column("max_attempts", sa.Integer, nullable=True, server_default="3"),
    )

    # Resolution tracking
    op.add_column("st_dlq", sa.Column("resolved_at", sa.BigInteger, nullable=True))
    op.add_column("st_dlq", sa.Column("resolved_by", sa.Text, nullable=True))
    op.add_column("st_dlq", sa.Column("resolution_notes", sa.Text, nullable=True))

    # Updated timestamp (dossier requirement)
    op.add_column("st_dlq", sa.Column("updated_at", sa.BigInteger, nullable=True))

    # =========================================================================
    # ADD CHECK CONSTRAINT FOR ERROR_TYPE
    # =========================================================================
    op.create_check_constraint(
        "ck_dlq_error_type",
        "st_dlq",
        "error_type IS NULL OR error_type IN ('TRANSIENT', 'VALIDATION', 'LOGIC', 'FATAL')",
    )

    # =========================================================================
    # UPDATE STATE CHECK CONSTRAINT (add new states)
    # =========================================================================
    # Drop existing constraint and recreate with expanded values
    op.drop_constraint("ck_dlq_state", "st_dlq", type_="check")
    op.create_check_constraint(
        "ck_dlq_state",
        "st_dlq",
        "state IN ('PENDING', 'REQUEUED', 'QUARANTINED', 'RESOLVED', 'ABANDONED', 'MANUAL_REVIEW', 'RETRYING')",
    )

    # =========================================================================
    # ADD P03-SPECIFIC INDEXES
    # =========================================================================

    # Index for P03 pipeline queries (partial: only P03 entries)
    op.create_index(
        "idx_dlq_p03_pipeline_phase",
        "st_dlq",
        ["pipeline_id", "phase"],
        postgresql_where=sa.text("pipeline_id IS NOT NULL"),
    )

    # Index for pending retry scan with error type
    op.create_index(
        "idx_dlq_pending_error_type",
        "st_dlq",
        ["state", "error_type"],
        postgresql_where=sa.text("state = 'PENDING' AND error_type IS NOT NULL"),
    )

    # Index for event-based lookup
    op.create_index(
        "idx_dlq_event_id",
        "st_dlq",
        ["event_id"],
        postgresql_where=sa.text("event_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove P03-specific columns from st_dlq."""
    # Drop indexes first
    op.drop_index("idx_dlq_event_id", table_name="st_dlq")
    op.drop_index("idx_dlq_pending_error_type", table_name="st_dlq")
    op.drop_index("idx_dlq_p03_pipeline_phase", table_name="st_dlq")

    # Restore original state CHECK constraint
    op.drop_constraint("ck_dlq_state", "st_dlq", type_="check")
    op.create_check_constraint(
        "ck_dlq_state",
        "st_dlq",
        "state IN ('PENDING', 'REQUEUED', 'QUARANTINED')",
    )

    # Drop error_type CHECK constraint
    op.drop_constraint("ck_dlq_error_type", "st_dlq", type_="check")

    # Drop columns in reverse order
    op.drop_column("st_dlq", "updated_at")
    op.drop_column("st_dlq", "resolution_notes")
    op.drop_column("st_dlq", "resolved_by")
    op.drop_column("st_dlq", "resolved_at")
    op.drop_column("st_dlq", "max_attempts")
    op.drop_column("st_dlq", "stack_trace")
    op.drop_column("st_dlq", "error_code")
    op.drop_column("st_dlq", "error_type")
    op.drop_column("st_dlq", "entity_id")
    op.drop_column("st_dlq", "event_id")
    op.drop_column("st_dlq", "phase")
    op.drop_column("st_dlq", "pipeline_id")
