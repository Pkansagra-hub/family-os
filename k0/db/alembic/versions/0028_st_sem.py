"""Create st_sem (Semantic Patterns) table.

Revision ID: 0028
Revises: 0027
Create Date: 2026-01-01

P03 Consolidation Pipeline - M2 Storage Migration

Brain Analog: Semantic Memory (Neocortex)
Role: Extracted patterns, preferences, themes from episodes
Written by: P03 R7 (after R2 pattern extraction)

Dossier Reference: Section 6.4 st_sem
Schema: 26 columns, 4 indexes
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0028"
down_revision: str = "0027"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_sem table for semantic pattern storage."""
    op.create_table(
        "st_sem",
        # ============================================================
        # Identity (4 columns)
        # ============================================================
        sa.Column("pattern_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Text, nullable=True),  # Whose pattern (NULL = shared family)
        # ============================================================
        # Versioning / Immutability (3 columns)
        # ============================================================
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.Text, nullable=True),
        sa.Column("is_canonical", sa.Boolean, server_default="TRUE"),
        # ============================================================
        # Pattern Classification (2 columns)
        # ============================================================
        sa.Column("pattern_type", sa.Text, nullable=False),
        sa.Column("pattern_subtype", sa.Text, nullable=True),
        # ============================================================
        # Pattern Content (3 columns)
        # ============================================================
        sa.Column("pattern_name", sa.Text, nullable=False),
        sa.Column("pattern_description", sa.Text, nullable=True),
        sa.Column("pattern_attributes_json", sa.Text, nullable=True),
        # ============================================================
        # Temporal Pattern (2 columns)
        # ============================================================
        sa.Column("temporal_regularity", sa.Float, nullable=True),
        sa.Column("temporal_pattern_json", sa.Text, nullable=True),
        # ============================================================
        # Source Episodes (2 columns)
        # ============================================================
        sa.Column("source_episodes_json", sa.Text, nullable=False),
        sa.Column("source_episode_count", sa.Integer, nullable=False),
        # ============================================================
        # Embeddings (1 column)
        # ============================================================
        sa.Column("embedding_id", sa.Text, nullable=True),
        # ============================================================
        # Truth Tracking (5 columns)
        # ============================================================
        sa.Column("observation_count", sa.Integer, server_default="1"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("last_observed_at", sa.BigInteger, nullable=True),
        sa.Column("first_observed_at", sa.BigInteger, nullable=True),
        sa.Column("decay_factor", sa.Float, server_default="1.0"),
        # ============================================================
        # Lifecycle (1 column)
        # ============================================================
        sa.Column("archival_status", sa.Text, server_default=sa.text("'ACTIVE'")),
        # ============================================================
        # Timestamps + Bitemporal (4 columns)
        # ============================================================
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("valid_from", sa.BigInteger, nullable=False),
        sa.Column("valid_to", sa.BigInteger, nullable=True),
        # ============================================================
        # CHECK Constraints
        # ============================================================
        sa.CheckConstraint(
            "pattern_type IN ('ROUTINE', 'PREFERENCE', 'THEME', 'RELATIONSHIP', 'GOAL', 'VALUE')",
            name="ck_sem_pattern_type",
        ),
        sa.CheckConstraint(
            "archival_status IN ('ACTIVE', 'ARCHIVED', 'TOMBSTONE')",
            name="ck_sem_archival_status",
        ),
    )

    # ============================================================
    # Indexes (4 indexes from dossier §6.4)
    # ============================================================
    op.create_index(
        "idx_sem_tenant_type",
        "st_sem",
        ["tenant_id", "pattern_type"],
    )
    op.create_index(
        "idx_sem_actor_type",
        "st_sem",
        ["actor_id", "pattern_type"],
        postgresql_where=sa.text("actor_id IS NOT NULL"),
    )
    op.create_index(
        "idx_sem_canonical",
        "st_sem",
        ["is_canonical", "archival_status"],
    )
    op.create_index(
        "idx_sem_confidence",
        "st_sem",
        [sa.text("confidence_score DESC")],
        postgresql_where=sa.text("is_canonical = TRUE"),
    )


def downgrade() -> None:
    """Drop st_sem table and all indexes."""
    op.drop_index("idx_sem_confidence", table_name="st_sem")
    op.drop_index("idx_sem_canonical", table_name="st_sem")
    op.drop_index("idx_sem_actor_type", table_name="st_sem")
    op.drop_index("idx_sem_tenant_type", table_name="st_sem")
    op.drop_table("st_sem")
