"""Create st_learning_queue table (Gap Queue for P06 Active Learning).

Revision ID: 0037
Revises: 0036
Create Date: 2025-01-01

Gap records for P03→P06 Active Learning pipeline.
Written by P03 R8 (gap detection) or P06 (entropy scanner).

Spec Reference: Dossier §6.11 st_learning_queue

Schema Features:
- 24 columns matching dossier specification
- GENERATED STORED column for importance_score
- CHECK constraints for gap_type and status
- 3 indexes including partial index for priority queue
- FK to st_hipp_events(event_id) for related_event_id
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0037"
down_revision: str = "0036"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Valid gap types from dossier §6.11
GAP_TYPES = (
    "AMBIGUOUS_ENTITY",
    "LOW_CONFIDENCE_EDGE",
    "MISSING_ATTRIBUTE",
    "CONTRADICTION",
    "CONCEPT_DRIFT",
    "STRUCTURAL_HOLE",
    "STALE_ANCHOR",
)

# Valid status values from dossier §6.11
GAP_STATUSES = (
    "PENDING",
    "READY",
    "ASKED",
    "ANSWERED",
    "RESOLVED",
    "EXPIRED",
    "REJECTED",
    "SUPPRESSED",
)


def upgrade() -> None:
    """Create st_learning_queue table with all columns and indexes."""
    op.create_table(
        "st_learning_queue",
        # Primary key - ULID for gap record
        sa.Column(
            "id",
            sa.Text,
            primary_key=True,
            comment="ULID for gap record",
        ),
        # Multi-tenant isolation
        sa.Column(
            "tenant_id",
            sa.Text,
            nullable=False,
            comment="Multi-tenant isolation",
        ),
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="User/family space",
        ),
        # Gap classification
        sa.Column(
            "gap_type",
            sa.Text,
            nullable=False,
            comment="Gap type classification",
        ),
        # Related entities
        sa.Column(
            "entity_id",
            sa.Text,
            nullable=True,
            comment="Related entity (if applicable)",
        ),
        sa.Column(
            "related_event_id",
            sa.Text,
            sa.ForeignKey("st_hipp_events.event_id", ondelete="SET NULL"),
            nullable=True,
            comment="Source event that triggered gap",
        ),
        sa.Column(
            "related_truth_id",
            sa.Text,
            nullable=True,
            comment="Affected truth record",
        ),
        # Scoring columns
        sa.Column(
            "confidence_score",
            sa.Float,
            nullable=True,
            comment="[0-1] Current confidence",
        ),
        sa.Column(
            "entropy_score",
            sa.Float,
            nullable=True,
            comment="[0-1] Uncertainty level",
        ),
        # GENERATED STORED column for importance
        # Formula: entropy_score * (1.0 / (confidence_score + 0.1))
        sa.Column(
            "importance_score",
            sa.Float,
            sa.Computed(
                "entropy_score * (1.0 / (COALESCE(confidence_score, 0.0) + 0.1))",
                persisted=True,
            ),
            comment="Priority score: entropy * (1/(confidence+0.1))",
        ),
        # Context for question generation
        sa.Column(
            "context_json",
            sa.Text,
            nullable=True,
            comment="Rich context for question generation",
        ),
        # Status tracking
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default="PENDING",
            comment="Gap processing status",
        ),
        # Timestamps (INTEGER = milliseconds since epoch)
        sa.Column(
            "created_at",
            sa.BigInteger,
            nullable=False,
            comment="Creation timestamp (ms)",
        ),
        sa.Column(
            "expires_at",
            sa.BigInteger,
            nullable=True,
            comment="Auto-expire after this time (ms)",
        ),
        sa.Column(
            "ready_at",
            sa.BigInteger,
            nullable=True,
            comment="When context became appropriate (ms)",
        ),
        sa.Column(
            "asked_at",
            sa.BigInteger,
            nullable=True,
            comment="When question was delivered (ms)",
        ),
        sa.Column(
            "answered_at",
            sa.BigInteger,
            nullable=True,
            comment="When user responded (ms)",
        ),
        # Retry tracking
        sa.Column(
            "attempts",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="How many times asked",
        ),
        sa.Column(
            "max_attempts",
            sa.Integer,
            nullable=False,
            server_default="3",
            comment="Max retry attempts",
        ),
        sa.Column(
            "last_attempt_at",
            sa.BigInteger,
            nullable=True,
            comment="Last attempt timestamp (ms)",
        ),
        # Resolution
        sa.Column(
            "resolution_type",
            sa.Text,
            nullable=True,
            comment="USER_ANSWER, INFERRED, EXPIRED",
        ),
        sa.Column(
            "resolution_data_json",
            sa.Text,
            nullable=True,
            comment="Answer or inference result",
        ),
        # P03 cycle reference
        sa.Column(
            "consolidation_cycle_id",
            sa.Text,
            nullable=True,
            comment="Which P03 cycle detected this",
        ),
        # CHECK constraints
        sa.CheckConstraint(
            f"gap_type IN ({', '.join(repr(t) for t in GAP_TYPES)})",
            name="ck_learning_queue_gap_type",
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in GAP_STATUSES)})",
            name="ck_learning_queue_status",
        ),
    )

    # Index 1: Priority queue (partial index on PENDING)
    op.create_index(
        "idx_learning_queue_importance",
        "st_learning_queue",
        [sa.text("importance_score DESC"), "created_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    # Index 2: Status queries
    op.create_index(
        "idx_learning_queue_status",
        "st_learning_queue",
        ["status", "expires_at"],
    )

    # Index 3: Tenant filtering
    op.create_index(
        "idx_learning_queue_tenant",
        "st_learning_queue",
        ["tenant_id", "gap_type", "status"],
    )

    # Index 4: Space isolation
    op.create_index(
        "idx_learning_queue_space",
        "st_learning_queue",
        ["space_id", "created_at"],
    )


def downgrade() -> None:
    """Drop st_learning_queue table and indexes."""
    op.drop_index("idx_learning_queue_space", table_name="st_learning_queue")
    op.drop_index("idx_learning_queue_tenant", table_name="st_learning_queue")
    op.drop_index("idx_learning_queue_status", table_name="st_learning_queue")
    op.drop_index("idx_learning_queue_importance", table_name="st_learning_queue")
    op.drop_table("st_learning_queue")
