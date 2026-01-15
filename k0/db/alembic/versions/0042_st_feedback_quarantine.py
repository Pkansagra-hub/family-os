"""Create st_feedback_quarantine table (Suspicious signal quarantine).

Revision ID: 0042
Revises: 0041
Create Date: 2025-01-01

Hold suspicious feedback signals for human review or auto-release.
Protects learning system from adversarial or anomalous signals.

Spec Reference: Dossier §6.21 st_feedback_quarantine

Schema Features:
- 15 columns matching dossier specification
- 3 indexes with partial WHERE predicates
- RLS policy for multi-tenant isolation
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0042"
down_revision: str = "0041"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_feedback_quarantine table with all columns and indexes."""
    op.create_table(
        "st_feedback_quarantine",
        # Primary key - ULID
        sa.Column(
            "quarantine_id",
            sa.Text,
            primary_key=True,
            comment="ULID for quarantine entry",
        ),
        # Space/tenant isolation
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="User/family space",
        ),
        sa.Column(
            "tenant_id",
            sa.Text,
            nullable=False,
            comment="Multi-tenant isolation",
        ),
        # Signal reference
        sa.Column(
            "signal_id",
            sa.Text,
            nullable=False,
            comment="Reference to st_feedback_signals",
        ),
        sa.Column(
            "signal_type",
            sa.Text,
            nullable=False,
            comment="Type of feedback signal",
        ),
        sa.Column(
            "signal_payload_json",
            sa.Text,  # JSONB in PostgreSQL
            nullable=False,
            comment="Original signal payload",
        ),
        # Quarantine metadata
        sa.Column(
            "quarantine_reason",
            sa.Text,
            nullable=False,
            comment="Why quarantined",
        ),
        sa.Column(
            "anomaly_score",
            sa.Float,
            nullable=True,
            comment="Anomaly detection score",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.BigInteger,
            nullable=False,
            comment="When quarantined (Unix ms)",
        ),
        sa.Column(
            "auto_release_at",
            sa.BigInteger,
            nullable=True,
            comment="When to auto-release (NULL = manual only)",
        ),
        # Decision tracking
        sa.Column(
            "decision",
            sa.Text,
            nullable=True,
            comment="RELEASE, REJECT, or NULL (pending)",
        ),
        sa.Column(
            "decided_by",
            sa.Text,
            nullable=True,
            comment="Who made decision (system or user)",
        ),
        sa.Column(
            "decided_at",
            sa.BigInteger,
            nullable=True,
            comment="When decision was made",
        ),
        sa.Column(
            "decision_reason",
            sa.Text,
            nullable=True,
            comment="Why decision was made",
        ),
        sa.Column(
            "updated_at",
            sa.BigInteger,
            nullable=False,
            comment="Last update timestamp (Unix ms)",
        ),
    )

    # Index 1: Pending signals by space (partial index)
    op.create_index(
        "idx_quarantine_space_status",
        "st_feedback_quarantine",
        ["space_id", "decision"],
        postgresql_where=sa.text("decision IS NULL"),
    )

    # Index 2: Auto-release scan (partial index)
    op.create_index(
        "idx_quarantine_auto_release",
        "st_feedback_quarantine",
        ["auto_release_at"],
        postgresql_where=sa.text("decision IS NULL"),
    )

    # Index 3: Signal lookup
    op.create_index(
        "idx_quarantine_signal",
        "st_feedback_quarantine",
        ["signal_id"],
    )

    # RLS for multi-tenant isolation
    op.execute("ALTER TABLE st_feedback_quarantine ENABLE ROW LEVEL SECURITY;")

    op.execute(
        """
        CREATE POLICY quarantine_isolation ON st_feedback_quarantine
            FOR ALL USING (space_id = current_setting('app.current_space_id', true)::text)
        """
    )


def downgrade() -> None:
    """Drop st_feedback_quarantine table and all indexes."""
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS quarantine_isolation ON st_feedback_quarantine;")
    op.execute("ALTER TABLE st_feedback_quarantine DISABLE ROW LEVEL SECURITY;")

    op.drop_index("idx_quarantine_signal", table_name="st_feedback_quarantine")
    op.drop_index("idx_quarantine_auto_release", table_name="st_feedback_quarantine")
    op.drop_index("idx_quarantine_space_status", table_name="st_feedback_quarantine")
    op.drop_table("st_feedback_quarantine")
