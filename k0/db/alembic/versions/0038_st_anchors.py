"""Create st_anchors table (Bayesian beliefs with Beta distributions).

Revision ID: 0038
Revises: 0037
Create Date: 2025-01-01

User preference modeling with Beta distributions.
Updated by P03 during consolidation, P06 entropy scanner.

Spec Reference: Dossier §6.12 st_anchors

Schema Features:
- 17 columns matching dossier specification
- Composite PK (entity_id, attribute, tenant_id)
- GENERATED STORED columns for confidence and uncertainty
- CHECK constraint on status
- 3 indexes including partial indexes for active/drift detection
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0038"
down_revision: str = "0037"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Valid status values from dossier §6.12
ANCHOR_STATUSES = (
    "ACTIVE",
    "DRIFTING",
    "STALE",
    "ARCHIVED",
)


def upgrade() -> None:
    """Create st_anchors table with all columns and indexes."""
    op.create_table(
        "st_anchors",
        # Composite primary key - (entity_id, attribute, tenant_id)
        sa.Column(
            "entity_id",
            sa.Text,
            nullable=False,
            comment="Person ID this anchor belongs to",
        ),
        sa.Column(
            "attribute",
            sa.Text,
            nullable=False,
            comment="Attribute name (e.g., 'loves_spicy_food')",
        ),
        sa.Column(
            "tenant_id",
            sa.Text,
            nullable=False,
            comment="Multi-tenant isolation",
        ),
        # Space isolation
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="User/family space",
        ),
        # Beta distribution parameters
        sa.Column(
            "alpha",
            sa.Float,
            nullable=False,
            server_default="1.0",
            comment="Beta distribution: evidence FOR",
        ),
        sa.Column(
            "beta",
            sa.Float,
            nullable=False,
            server_default="1.0",
            comment="Beta distribution: evidence AGAINST",
        ),
        # GENERATED STORED columns for computed metrics
        sa.Column(
            "confidence",
            sa.Float,
            sa.Computed("alpha / (alpha + beta)", persisted=True),
            comment="Computed: alpha / (alpha + beta)",
        ),
        sa.Column(
            "uncertainty",
            sa.Float,
            sa.Computed("1.0 / (1.0 + alpha + beta)", persisted=True),
            comment="Computed: 1.0 / (1.0 + alpha + beta)",
        ),
        # Observation tracking
        sa.Column(
            "observation_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Total observations",
        ),
        sa.Column(
            "first_observed_at",
            sa.BigInteger,
            nullable=True,
            comment="First observation timestamp (Unix ms)",
        ),
        sa.Column(
            "last_updated_at",
            sa.BigInteger,
            nullable=False,
            comment="Last update timestamp (Unix ms)",
        ),
        # Decay parameters
        sa.Column(
            "decay_rate",
            sa.Float,
            nullable=False,
            server_default="0.05",
            comment="Forgetting factor (5% per month)",
        ),
        sa.Column(
            "half_life_days",
            sa.Integer,
            nullable=False,
            server_default="180",
            comment="Days until confidence halves",
        ),
        # Drift detection
        sa.Column(
            "last_drift_check_at",
            sa.BigInteger,
            nullable=True,
            comment="Last drift check timestamp (Unix ms)",
        ),
        sa.Column(
            "drift_detected",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Concept drift detected?",
        ),
        sa.Column(
            "drift_magnitude",
            sa.Float,
            nullable=True,
            comment="Magnitude of drift",
        ),
        # Status with CHECK constraint
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default="ACTIVE",
            comment="ACTIVE, DRIFTING, STALE, ARCHIVED",
        ),
        # Composite primary key
        sa.PrimaryKeyConstraint("entity_id", "attribute", "tenant_id", name="pk_st_anchors"),
        # CHECK constraint for status
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in ANCHOR_STATUSES)})",
            name="ck_anchors_status",
        ),
    )

    # Index 1: Entity history lookup
    op.create_index(
        "idx_anchors_entity",
        "st_anchors",
        ["entity_id", sa.text("last_updated_at DESC")],
    )

    # Index 2: High-confidence lookup (partial index for ACTIVE only)
    op.create_index(
        "idx_anchors_confidence",
        "st_anchors",
        [sa.text("confidence DESC")],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # Index 3: Drift detection (partial index for drift_detected = TRUE)
    op.create_index(
        "idx_anchors_drift",
        "st_anchors",
        ["drift_detected", "status"],
        postgresql_where=sa.text("drift_detected = TRUE"),
    )

    # Index 4: Space lookup for multi-tenant queries
    op.create_index(
        "idx_anchors_space",
        "st_anchors",
        ["space_id", "status"],
    )


def downgrade() -> None:
    """Drop st_anchors table and all indexes."""
    op.drop_index("idx_anchors_space", table_name="st_anchors")
    op.drop_index("idx_anchors_drift", table_name="st_anchors")
    op.drop_index("idx_anchors_confidence", table_name="st_anchors")
    op.drop_index("idx_anchors_entity", table_name="st_anchors")
    op.drop_table("st_anchors")
