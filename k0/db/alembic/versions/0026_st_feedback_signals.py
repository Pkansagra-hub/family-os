"""Create st_feedback_signals table (Feedback Signals).

Revision ID: 0026
Revises: 0025
Create Date: 2025-12-26

Stores pipeline-agnostic feedback envelopes received via the Observe port
(`/k0/obs.emit`, kind="feedback"). Payload, correlation, provenance, and
metadata are stored as JSONB for schema-flexible evolution.

Notes:
- Keeps IDs as TEXT to match existing K0 PostgreSQL schema conventions.
- Uses JSONB with server defaults for empty objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence


# Revision identifiers
revision: str = "0026"
down_revision: str = "0025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "st_feedback_signals",
        # Identity
        sa.Column(
            "feedback_id",
            sa.Text,
            primary_key=True,
            comment="Feedback envelope id (UUID string)",
        ),
        # Routing
        sa.Column("pipeline_id", sa.Text, nullable=False),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # Classification
        sa.Column("signal_class", sa.Text, nullable=False),
        sa.Column("signal_subtype", sa.Text, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("source_component", sa.Text, nullable=True),
        # Tracing
        sa.Column("session_id", sa.Text, nullable=True),
        sa.Column("trace_id", sa.Text, nullable=False),
        # Correlation + provenance
        sa.Column(
            "correlation",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Payload
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("payload_hash", sa.Text, nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Validation status ("valid" | "invalid" | "unvalidated")
        sa.Column(
            "payload_validation_status",
            sa.Text,
            nullable=False,
            server_default="'unvalidated'",
        ),
        sa.Column("payload_validation_error", sa.Text, nullable=True),
        # Priority & timing
        sa.Column(
            "priority",
            sa.Float,
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=True),
        # Processing
        sa.Column(
            "processing_status",
            sa.Text,
            nullable=False,
            server_default="'pending'",
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.CheckConstraint(
            "signal_class IN ('OUTCOME', 'CORRECTION', 'IMPLICIT', 'EXPLICIT', 'VALIDATION')",
            name="ck_feedback_signal_class",
        ),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_feedback_processing_status",
        ),
        sa.CheckConstraint(
            "payload_validation_status IN ('valid', 'invalid', 'unvalidated')",
            name="ck_feedback_payload_validation_status",
        ),
        sa.CheckConstraint(
            "priority >= 0.0 AND priority <= 1.0",
            name="ck_feedback_priority",
        ),
    )

    # Indexes
    op.create_index(
        "idx_feedback_pipeline_received",
        "st_feedback_signals",
        ["pipeline_id", sa.text("received_at DESC")],
    )
    op.create_index(
        "idx_feedback_tenant_space",
        "st_feedback_signals",
        ["tenant_id", "space_id"],
    )
    op.create_index(
        "idx_feedback_session",
        "st_feedback_signals",
        ["session_id"],
        postgresql_where=sa.text("session_id IS NOT NULL"),
    )
    op.create_index("idx_feedback_trace", "st_feedback_signals", ["trace_id"])
    op.create_index("idx_feedback_payload_hash", "st_feedback_signals", ["payload_hash"])
    op.create_index(
        "idx_feedback_status_pending",
        "st_feedback_signals",
        ["processing_status"],
        postgresql_where=sa.text("processing_status = 'pending'"),
    )
    op.create_index(
        "idx_feedback_target_entity",
        "st_feedback_signals",
        [sa.text("(correlation->>'target_entity_id')")],
    )


def downgrade() -> None:
    op.drop_index("idx_feedback_target_entity", table_name="st_feedback_signals")
    op.drop_index("idx_feedback_status_pending", table_name="st_feedback_signals")
    op.drop_index("idx_feedback_payload_hash", table_name="st_feedback_signals")
    op.drop_index("idx_feedback_trace", table_name="st_feedback_signals")
    op.drop_index("idx_feedback_session", table_name="st_feedback_signals")
    op.drop_index("idx_feedback_tenant_space", table_name="st_feedback_signals")
    op.drop_index("idx_feedback_pipeline_received", table_name="st_feedback_signals")
    op.drop_table("st_feedback_signals")
