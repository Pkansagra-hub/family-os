"""Create st_procedural (Habits & Routines) table.

Revision ID: 0029
Revises: 0028
Create Date: 2026-01-01

P03 Consolidation Pipeline - M2 Storage Migration

Brain Analog: Basal Ganglia (Procedural Memory)
Role: Recurring behavioral patterns, habits, skills
Written by: P03 R7

Dossier Reference: Section 6.5 st_procedural
Schema: 27 columns, 3 indexes
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0029"
down_revision: str = "0028"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_procedural table for habits and routines storage."""
    op.create_table(
        "st_procedural",
        # ============================================================
        # Identity (4 columns)
        # ============================================================
        sa.Column("routine_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Text, nullable=False),  # Who performs this routine
        # ============================================================
        # Versioning / Immutability (3 columns)
        # ============================================================
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.Text, nullable=True),
        sa.Column("is_canonical", sa.Boolean, server_default="TRUE"),
        # ============================================================
        # Routine Definition (2 columns)
        # ============================================================
        sa.Column("routine_name", sa.Text, nullable=False),
        sa.Column("routine_category", sa.Text, nullable=True),  # MORNING, EXERCISE, etc.
        # ============================================================
        # Temporal Pattern (4 columns)
        # ============================================================
        sa.Column("temporal_anchor", sa.Text, nullable=True),  # Time of day: "07:30"
        sa.Column("day_pattern", sa.Text, nullable=True),  # WEEKDAYS, WEEKENDS, DAILY
        sa.Column("frequency", sa.Text, nullable=True),  # DAILY, WEEKLY, MONTHLY
        sa.Column("regularity_score", sa.Float, nullable=True),  # [0-1] How consistent
        # ============================================================
        # Action Sequence (2 columns)
        # ============================================================
        sa.Column("action_sequence_json", sa.Text, nullable=True),  # Ordered list of actions
        sa.Column("typical_duration_minutes", sa.Integer, nullable=True),
        # ============================================================
        # Source Episodes (2 columns)
        # ============================================================
        sa.Column("source_episodes_json", sa.Text, nullable=False),
        sa.Column("source_episode_count", sa.Integer, nullable=False),
        # ============================================================
        # Truth Tracking (6 columns)
        # ============================================================
        sa.Column("observation_count", sa.Integer, server_default="1"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("last_observed_at", sa.BigInteger, nullable=True),
        sa.Column("streak_count", sa.Integer, server_default="0"),  # Consecutive occurrences
        sa.Column("streak_broken_at", sa.BigInteger, nullable=True),  # When streak was broken
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
        # CHECK Constraints
        # ============================================================
        sa.CheckConstraint(
            "archival_status IN ('ACTIVE', 'ARCHIVED', 'TOMBSTONE')",
            name="ck_procedural_archival_status",
        ),
    )

    # ============================================================
    # Indexes (3 indexes from dossier §6.5)
    # ============================================================
    op.create_index(
        "idx_procedural_actor",
        "st_procedural",
        ["actor_id", "is_canonical"],
    )
    op.create_index(
        "idx_procedural_category",
        "st_procedural",
        ["routine_category"],
        postgresql_where=sa.text("routine_category IS NOT NULL"),
    )
    op.create_index(
        "idx_procedural_regularity",
        "st_procedural",
        [sa.text("regularity_score DESC")],
        postgresql_where=sa.text("is_canonical = TRUE"),
    )


def downgrade() -> None:
    """Drop st_procedural table and all indexes."""
    op.drop_index("idx_procedural_regularity", table_name="st_procedural")
    op.drop_index("idx_procedural_category", table_name="st_procedural")
    op.drop_index("idx_procedural_actor", table_name="st_procedural")
    op.drop_table("st_procedural")
