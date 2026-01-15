"""Create st_decay_feedback table for decay rate learning.

Revision ID: 0050
Revises: 0049
Create Date: 2025-01-04

K0 PostgreSQL Migration - P03 Consolidation

Tracks observed access patterns and decay outcomes for Bayesian lambda estimation.
Captures inter-access intervals and resurrection events for per-space decay calibration.

Dossier Reference: Section 6.22 st_decay_feedback
Retention: 365 days rolling window (sufficient for seasonal patterns)
Isolation: RLS enforced for multi-tenant security
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0050"
down_revision: str = "0049"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Valid event types from dossier §6.22.2
EVENT_TYPES = (
    "ACCESS",
    "RESURRECTION",
    "ARCHIVE",
    "TOMBSTONE",
)


def upgrade() -> None:
    """Create st_decay_feedback table with RLS."""
    op.create_table(
        "st_decay_feedback",
        # Identity
        sa.Column(
            "feedback_id",
            sa.Text,
            primary_key=True,
            comment="Unique feedback event ID",
        ),
        sa.Column(
            "memory_id",
            sa.Text,
            nullable=False,
            comment="Entity this feedback is about",
        ),
        sa.Column(
            "layer",
            sa.Text,
            nullable=False,
            comment="st_epi, st_sem, st_kg_dom, etc.",
        ),
        # Context
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="Space isolation",
        ),
        sa.Column(
            "tenant_id",
            sa.Text,
            nullable=False,
            comment="Tenant isolation",
        ),
        # Observed behavior
        sa.Column(
            "event_type",
            sa.Text,
            nullable=False,
            comment="ACCESS, RESURRECTION, ARCHIVE, TOMBSTONE",
        ),
        sa.Column(
            "inter_access_interval",
            sa.Float,
            nullable=True,
            comment="Days since last access (NULL for first access)",
        ),
        sa.Column(
            "decay_factor_at_event",
            sa.Float,
            nullable=True,
            comment="Decay factor when event occurred",
        ),
        sa.Column(
            "expected_decay",
            sa.Float,
            nullable=True,
            comment="What decay would have been with current lambda",
        ),
        # Learning signals
        sa.Column(
            "resurrection_needed",
            sa.Boolean,
            nullable=True,
            comment="TRUE if resurrected from ARCHIVED/TOMBSTONE",
        ),
        sa.Column(
            "archival_premature",
            sa.Boolean,
            nullable=True,
            comment="TRUE if accessed shortly after archival",
        ),
        # Timestamps (Unix seconds for this table per dossier)
        sa.Column(
            "created_at",
            sa.BigInteger,
            nullable=False,
            comment="When record was created (epoch seconds)",
        ),
        sa.Column(
            "observed_at",
            sa.BigInteger,
            nullable=False,
            comment="When the access/resurrection occurred (epoch seconds)",
        ),
        # CHECK constraints
        sa.CheckConstraint(
            f"event_type IN ({', '.join(repr(e) for e in EVENT_TYPES)})",
            name="ck_decay_feedback_event_type",
        ),
        sa.CheckConstraint(
            "inter_access_interval IS NULL OR inter_access_interval >= 0.0",
            name="ck_decay_feedback_interval_nonneg",
        ),
        sa.CheckConstraint(
            "decay_factor_at_event IS NULL OR "
            "(decay_factor_at_event >= 0.0 AND decay_factor_at_event <= 1.0)",
            name="ck_decay_feedback_factor_range",
        ),
    )

    # Index 1: Space/layer/time for efficient querying
    op.create_index(
        "idx_decay_fb_space_layer",
        "st_decay_feedback",
        ["space_id", "layer", "observed_at"],
    )

    # Index 2: Memory ID for entity-specific queries
    op.create_index(
        "idx_decay_fb_memory",
        "st_decay_feedback",
        ["memory_id", "observed_at"],
    )

    # Index 3: Event type for event analysis
    op.create_index(
        "idx_decay_fb_event_type",
        "st_decay_feedback",
        ["event_type", "observed_at"],
    )

    # Index 4: Resurrection events for learning (partial index)
    op.create_index(
        "idx_decay_fb_resurrections",
        "st_decay_feedback",
        ["space_id", "layer", "observed_at"],
        postgresql_where=sa.text("resurrection_needed = TRUE"),
    )

    # Index 5: Premature archival for learning (partial index)
    op.create_index(
        "idx_decay_fb_premature",
        "st_decay_feedback",
        ["space_id", "layer", "observed_at"],
        postgresql_where=sa.text("archival_premature = TRUE"),
    )

    # Index 6: Tenant/space canonical for multi-tenant queries
    op.create_index(
        "idx_decay_fb_tenant_space",
        "st_decay_feedback",
        ["tenant_id", "space_id", "observed_at"],
    )

    # Enable Row Level Security
    op.execute("ALTER TABLE st_decay_feedback ENABLE ROW LEVEL SECURITY;")

    # RLS Policy: Users can only see decay feedback from their spaces
    op.execute(
        """
        CREATE POLICY decay_feedback_isolation ON st_decay_feedback
            FOR ALL USING (space_id = current_setting('app.current_space_id', true)::text)
        """
    )


def downgrade() -> None:
    """Drop st_decay_feedback table and all indexes."""
    # Drop RLS policy first
    op.execute("DROP POLICY IF EXISTS decay_feedback_isolation ON st_decay_feedback;")
    op.execute("ALTER TABLE st_decay_feedback DISABLE ROW LEVEL SECURITY;")

    # Drop indexes
    op.drop_index("idx_decay_fb_tenant_space", table_name="st_decay_feedback")
    op.drop_index("idx_decay_fb_premature", table_name="st_decay_feedback")
    op.drop_index("idx_decay_fb_resurrections", table_name="st_decay_feedback")
    op.drop_index("idx_decay_fb_event_type", table_name="st_decay_feedback")
    op.drop_index("idx_decay_fb_memory", table_name="st_decay_feedback")
    op.drop_index("idx_decay_fb_space_layer", table_name="st_decay_feedback")

    # Drop table
    op.drop_table("st_decay_feedback")
