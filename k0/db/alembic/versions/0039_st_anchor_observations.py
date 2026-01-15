"""Create st_anchor_observations table (Evidence log for anchor updates).

Revision ID: 0039
Revises: 0038
Create Date: 2025-01-01

Append-only evidence log explaining how anchors were updated.
Audit trail for Bayesian evidence observations.

Spec Reference: Dossier §6.13 st_anchor_observations

Schema Features:
- 9 columns matching dossier specification
- ULID primary key for observation
- FK to st_anchors composite key (entity_id, attribute, tenant_id)
- FK to st_hipp_events for source event
- Index for latest observations per anchor
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0039"
down_revision: str = "0038"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_anchor_observations table with all columns and indexes."""
    op.create_table(
        "st_anchor_observations",
        # Primary key - ULID for observation
        sa.Column(
            "id",
            sa.Text,
            primary_key=True,
            comment="ULID for observation",
        ),
        # Anchor reference (FK to st_anchors composite key)
        sa.Column(
            "entity_id",
            sa.Text,
            nullable=False,
            comment="Anchor entity",
        ),
        sa.Column(
            "attribute",
            sa.Text,
            nullable=False,
            comment="Anchor attribute",
        ),
        sa.Column(
            "tenant_id",
            sa.Text,
            nullable=False,
            comment="Anchor tenant",
        ),
        # Observation timestamp
        sa.Column(
            "observed_at",
            sa.BigInteger,
            nullable=False,
            comment="Observation timestamp (Unix ms)",
        ),
        # Source event reference
        sa.Column(
            "event_id",
            sa.Text,
            nullable=True,
            comment="Source event that triggered this observation",
        ),
        # Evidence direction
        sa.Column(
            "supports_anchor",
            sa.Boolean,
            nullable=False,
            comment="TRUE=evidence FOR, FALSE=AGAINST",
        ),
        # Observation weight
        sa.Column(
            "observation_weight",
            sa.Float,
            nullable=False,
            server_default="1.0",
            comment="Weight of observation [0-1]",
        ),
        # Context for interpretation
        sa.Column(
            "observation_context",
            sa.Text,
            nullable=True,
            comment="Why interpreted as support/oppose",
        ),
        # Foreign key to st_anchors composite key
        sa.ForeignKeyConstraint(
            ["entity_id", "attribute", "tenant_id"],
            ["st_anchors.entity_id", "st_anchors.attribute", "st_anchors.tenant_id"],
            name="fk_anchor_obs_anchor",
            ondelete="CASCADE",
        ),
        # Foreign key to st_hipp_events
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["st_hipp_events.event_id"],
            name="fk_anchor_obs_event",
            ondelete="SET NULL",
        ),
    )

    # Index: Latest observations per anchor
    op.create_index(
        "idx_anchor_obs_anchor",
        "st_anchor_observations",
        ["entity_id", "attribute", sa.text("observed_at DESC")],
    )

    # Index: Tenant lookup for multi-tenant queries
    op.create_index(
        "idx_anchor_obs_tenant",
        "st_anchor_observations",
        ["tenant_id", "observed_at"],
    )

    # Index: Event reference lookup
    op.create_index(
        "idx_anchor_obs_event",
        "st_anchor_observations",
        ["event_id"],
        postgresql_where=sa.text("event_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_anchor_observations table and all indexes."""
    op.drop_index("idx_anchor_obs_event", table_name="st_anchor_observations")
    op.drop_index("idx_anchor_obs_tenant", table_name="st_anchor_observations")
    op.drop_index("idx_anchor_obs_anchor", table_name="st_anchor_observations")
    op.drop_table("st_anchor_observations")
