"""Add P03 consolidation columns to st_hipp_events.

Revision ID: 0034
Revises: 0033
Create Date: 2026-01-01

P03 Consolidation Pipeline - M2 Storage Migration

Role: Enable st_hipp_events to track consolidation lifecycle
New columns for P03 R0-R8 processing status and decisions

Dossier Reference: Section 6.2, 6.2.2
Schema: 6 new columns, 1 CHECK constraint, 1 partial index
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0034"
down_revision: str = "0033"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add P03 consolidation columns to st_hipp_events."""
    # ============================================================
    # Add consolidation columns (6 columns from dossier §6.2.2)
    # ============================================================
    op.add_column(
        "st_hipp_events",
        sa.Column("consolidation_status", sa.Text, nullable=True),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column("consolidation_cycle_id", sa.Text, nullable=True),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column("consolidated_at", sa.BigInteger, nullable=True),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column("reconciliation_decision", sa.Text, nullable=True),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column("truth_match_id", sa.Text, nullable=True),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column("truth_match_similarity", sa.Float, nullable=True),
    )

    # ============================================================
    # Add CHECK constraint (per dossier §6.2.2)
    # ============================================================
    op.create_check_constraint(
        "ck_hipp_consolidation_status",
        "st_hipp_events",
        "consolidation_status IN ('PENDING', 'IN_PROGRESS', 'CONSOLIDATED', "
        "'DUPLICATE', 'PRUNED', 'PENDING_REVIEW') OR consolidation_status IS NULL",
    )

    # ============================================================
    # Add partial index for R0 pending scan (per dossier §6.2.2)
    # ============================================================
    op.create_index(
        "idx_hipp_events_consolidation",
        "st_hipp_events",
        ["consolidation_status", sa.text("event_time_utc DESC")],
        postgresql_where=sa.text(
            "consolidation_status IS NULL OR consolidation_status = 'PENDING'"
        ),
    )


def downgrade() -> None:
    """Remove P03 consolidation columns from st_hipp_events."""
    op.drop_index("idx_hipp_events_consolidation", table_name="st_hipp_events")
    op.drop_constraint("ck_hipp_consolidation_status", "st_hipp_events", type_="check")
    op.drop_column("st_hipp_events", "truth_match_similarity")
    op.drop_column("st_hipp_events", "truth_match_id")
    op.drop_column("st_hipp_events", "reconciliation_decision")
    op.drop_column("st_hipp_events", "consolidated_at")
    op.drop_column("st_hipp_events", "consolidation_cycle_id")
    op.drop_column("st_hipp_events", "consolidation_status")
