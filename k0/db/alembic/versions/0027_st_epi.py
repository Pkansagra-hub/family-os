"""Create st_epi (Episodic Memory) table.

Revision ID: 0027
Revises: 0026
Create Date: 2026-01-01

P03 Consolidation Pipeline - M2 Storage Migration

Brain Analog: Episodic Memory (Tulving)
Role: Consolidated episode clusters with temporal anchoring
Written by: P03 R7 (after R2 clustering)

Dossier Reference: Section 6.3 st_epi
Schema: 33 columns, 4 indexes
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0027"
down_revision: str = "0026"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_epi table for episodic memory storage."""
    op.create_table(
        "st_epi",
        # ============================================================
        # Identity (3 columns)
        # ============================================================
        sa.Column("episode_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # ============================================================
        # Versioning / Immutability (3 columns)
        # ============================================================
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.Text, nullable=True),
        sa.Column("is_canonical", sa.Boolean, server_default="TRUE"),
        # ============================================================
        # Episode Content (2 columns)
        # ============================================================
        sa.Column("episode_summary", sa.Text, nullable=True),
        sa.Column("episode_type", sa.Text, nullable=True),
        # ============================================================
        # Temporal Anchoring (7 columns)
        # ============================================================
        sa.Column("start_time_utc", sa.BigInteger, nullable=False),
        sa.Column("end_time_utc", sa.BigInteger, nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("temporal_bucket", sa.Text, nullable=True),
        sa.Column("day_of_week", sa.Text, nullable=True),
        sa.Column("is_recurring", sa.Boolean, nullable=True),
        sa.Column("recurrence_pattern", sa.Text, nullable=True),
        # ============================================================
        # Source Events (2 columns)
        # ============================================================
        sa.Column("source_events_json", sa.Text, nullable=False),
        sa.Column("source_event_count", sa.Integer, nullable=False),
        # ============================================================
        # Location (2 columns)
        # ============================================================
        sa.Column("primary_location", sa.Text, nullable=True),
        sa.Column("location_type", sa.Text, nullable=True),
        # ============================================================
        # Participants (2 columns)
        # ============================================================
        sa.Column("participants_json", sa.Text, nullable=True),
        sa.Column("participant_count", sa.Integer, nullable=True),
        # ============================================================
        # Embeddings (1 column)
        # ============================================================
        sa.Column("embedding_id", sa.Text, nullable=True),
        # ============================================================
        # Consolidation Metadata (3 columns)
        # ============================================================
        sa.Column("cluster_id", sa.Text, nullable=True),
        sa.Column("cluster_confidence", sa.Float, nullable=True),
        sa.Column("consolidation_cycle_id", sa.Text, nullable=True),
        # ============================================================
        # Truth Tracking (4 columns)
        # ============================================================
        sa.Column("observation_count", sa.Integer, server_default="1"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("last_observed_at", sa.BigInteger, nullable=True),
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
            name="ck_epi_archival_status",
        ),
    )

    # ============================================================
    # Indexes (4 indexes from dossier §6.3)
    # ============================================================
    op.create_index(
        "idx_epi_tenant_time",
        "st_epi",
        ["tenant_id", sa.text("start_time_utc DESC")],
    )
    op.create_index(
        "idx_epi_space_time",
        "st_epi",
        ["space_id", sa.text("start_time_utc DESC")],
    )
    op.create_index(
        "idx_epi_cluster",
        "st_epi",
        ["cluster_id"],
        postgresql_where=sa.text("cluster_id IS NOT NULL"),
    )
    op.create_index(
        "idx_epi_canonical",
        "st_epi",
        ["is_canonical", "archival_status"],
    )


def downgrade() -> None:
    """Drop st_epi table and all indexes."""
    op.drop_index("idx_epi_canonical", table_name="st_epi")
    op.drop_index("idx_epi_cluster", table_name="st_epi")
    op.drop_index("idx_epi_space_time", table_name="st_epi")
    op.drop_index("idx_epi_tenant_time", table_name="st_epi")
    op.drop_table("st_epi")
