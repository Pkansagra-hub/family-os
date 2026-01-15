"""Create st_prospective (Intentions & Goals) table.

Revision ID: 0031
Revises: 0030
Create Date: 2026-01-01

P03 Consolidation Pipeline - M2 Storage Migration

Brain Analog: Prefrontal Cortex (Future Thinking)
Role: Future-oriented patterns, goals, intentions, reminders
Written by: P03 R7 (from R5 forward simulation)

Dossier Reference: Section 6.7 st_prospective
Schema: 23 columns, 2 CHECK constraints
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0031"
down_revision: str = "0030"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_prospective table for intentions and goals storage."""
    op.create_table(
        "st_prospective",
        # ============================================================
        # Identity (4 columns)
        # ============================================================
        sa.Column("intention_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Text, nullable=False),
        # ============================================================
        # Versioning / Immutability (3 columns)
        # ============================================================
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.Text, nullable=True),
        sa.Column("is_canonical", sa.Boolean, server_default="TRUE"),
        # ============================================================
        # Intention Type (1 column)
        # ============================================================
        sa.Column("intention_type", sa.Text, nullable=False),
        # ============================================================
        # Content (3 columns)
        # ============================================================
        sa.Column("intention_description", sa.Text, nullable=False),
        sa.Column("target_date", sa.BigInteger, nullable=True),  # When to complete
        sa.Column("target_context", sa.Text, nullable=True),  # Triggering context
        # ============================================================
        # Status (1 column)
        # ============================================================
        sa.Column("status", sa.Text, server_default="'ACTIVE'"),
        # ============================================================
        # Inference Source (2 columns)
        # ============================================================
        sa.Column("inferred_from_json", sa.Text, nullable=True),  # Source patterns/episodes
        sa.Column("inference_confidence", sa.Float, nullable=True),
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
        # CHECK Constraints (per dossier §6.7)
        # ============================================================
        sa.CheckConstraint(
            "intention_type IN ('GOAL', 'PLAN', 'REMINDER', 'COMMITMENT', 'WISH')",
            name="ck_prosp_intention_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'ABANDONED', 'DEFERRED')",
            name="ck_prosp_status",
        ),
        sa.CheckConstraint(
            "archival_status IN ('ACTIVE', 'ARCHIVED', 'TOMBSTONE')",
            name="ck_prosp_archival_status",
        ),
    )

    # ============================================================
    # Indexes (2 indexes for intention queries)
    # ============================================================
    op.create_index(
        "idx_prosp_actor_type",
        "st_prospective",
        ["actor_id", "intention_type"],
    )
    op.create_index(
        "idx_prosp_status",
        "st_prospective",
        ["status", "target_date"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    """Drop st_prospective table and all indexes."""
    op.drop_index("idx_prosp_status", table_name="st_prospective")
    op.drop_index("idx_prosp_actor_type", table_name="st_prospective")
    op.drop_table("st_prospective")
