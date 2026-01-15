"""Create st_social (Relationships) table.

Revision ID: 0030
Revises: 0029
Create Date: 2026-01-01

P03 Consolidation Pipeline - M2 Storage Migration

Brain Analog: Social Brain Network
Role: Relationship tracking, interaction history, social graph
Written by: P03 R7

Dossier Reference: Section 6.6 st_social
Schema: 27 columns, UNIQUE constraint
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0030"
down_revision: str = "0029"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_social table for relationship tracking."""
    op.create_table(
        "st_social",
        # ============================================================
        # Identity (3 columns)
        # ============================================================
        sa.Column("relationship_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # ============================================================
        # Relationship Endpoints (2 columns)
        # ============================================================
        sa.Column("actor_a_id", sa.Text, nullable=False),  # First person
        sa.Column("actor_b_id", sa.Text, nullable=False),  # Second person
        # ============================================================
        # Versioning / Immutability (3 columns)
        # ============================================================
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.Text, nullable=True),
        sa.Column("is_canonical", sa.Boolean, server_default="TRUE"),
        # ============================================================
        # Relationship Type (3 columns)
        # ============================================================
        sa.Column("relationship_type", sa.Text, nullable=False),  # FAMILY, FRIEND, COLLEAGUE
        sa.Column("relationship_subtype", sa.Text, nullable=True),  # SPOUSE, SIBLING, PARENT
        sa.Column("relationship_label", sa.Text, nullable=True),  # Custom label
        # ============================================================
        # Relationship Strength (4 columns)
        # ============================================================
        sa.Column("interaction_count", sa.Integer, server_default="0"),
        sa.Column("avg_sentiment", sa.Float, nullable=True),
        sa.Column("relationship_strength", sa.Float, server_default="0.5"),  # [0-1]
        sa.Column(
            "intimacy_level", sa.Text, nullable=True
        ),  # ACQUAINTANCE, CASUAL, CLOSE, INTIMATE
        # ============================================================
        # Temporal (3 columns)
        # ============================================================
        sa.Column("first_interaction_at", sa.BigInteger, nullable=True),
        sa.Column("last_interaction_at", sa.BigInteger, nullable=True),
        sa.Column("interaction_frequency", sa.Text, nullable=True),  # DAILY, WEEKLY, MONTHLY, RARE
        # ============================================================
        # Source Episodes (1 column)
        # ============================================================
        sa.Column("source_episodes_json", sa.Text, nullable=True),
        # ============================================================
        # Truth Tracking (3 columns)
        # ============================================================
        sa.Column("observation_count", sa.Integer, server_default="1"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("decay_factor", sa.Float, server_default="1.0"),
        # ============================================================
        # Lifecycle (1 column)
        # ============================================================
        sa.Column("archival_status", sa.Text, server_default="'ACTIVE'"),
        # ============================================================
        # Timestamps + Bitemporal (4 columns)
        # ============================================================
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("valid_from", sa.BigInteger, nullable=False),
        sa.Column("valid_to", sa.BigInteger, nullable=True),
        # ============================================================
        # UNIQUE Constraint (per dossier)
        # ============================================================
        sa.UniqueConstraint(
            "tenant_id",
            "actor_a_id",
            "actor_b_id",
            "is_canonical",
            name="uq_social_canonical",
        ),
        # ============================================================
        # CHECK Constraints
        # ============================================================
        sa.CheckConstraint(
            "archival_status IN ('ACTIVE', 'ARCHIVED', 'TOMBSTONE')",
            name="ck_social_archival_status",
        ),
    )

    # ============================================================
    # Indexes (2 indexes for relationship queries)
    # ============================================================
    op.create_index(
        "idx_social_actor_a",
        "st_social",
        ["actor_a_id", "relationship_type"],
    )
    op.create_index(
        "idx_social_actor_b",
        "st_social",
        ["actor_b_id", "relationship_type"],
    )


def downgrade() -> None:
    """Drop st_social table and all indexes."""
    op.drop_index("idx_social_actor_b", table_name="st_social")
    op.drop_index("idx_social_actor_a", table_name="st_social")
    op.drop_table("st_social")
