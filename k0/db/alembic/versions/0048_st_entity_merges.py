"""Add st_entity_merges for tracking entity merges with undo support.

Revision ID: 0048
Revises: 0047
Create Date: 2026-01-03

P03 Pipeline - Entity Merge Audit Trail

Issue: 4.4.7 - Implement entity merge cascade + undo support

Creates st_entity_merges table to track entity merge operations:
- Records each merge with full snapshots of both entities
- Stores cascade counts per affected table
- Enables undo via merge_cascade_id tracking
- Supports merge history queries

Table Purpose:
1. Audit trail for all entity merges
2. Undo support via snapshots and merge_cascade_id
3. Cascade impact tracking
4. Merge history for debugging

Also adds merge_cascade_id column to 7 cascade tables:
- st_kg_edges (entity references)
- st_hipp_events (event entities)
- st_epi (episode entities)
- st_sem (pattern entities)
- st_social (actor references)
- st_procedural (participants)
- st_vec (embedding metadata)

Dossier Reference: P03 Consolidation Dossier v2, Section 4.5.1.3
Spec Reference: M4_EXECUTION.md, Issue 4.4.7
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0048"
down_revision: str = "0047"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_entity_merges table and add merge_cascade_id to cascade tables."""
    # ============================================================
    # Create st_entity_merges table (Issue 4.4.7)
    # ============================================================

    op.create_table(
        "st_entity_merges",
        # Primary key
        sa.Column(
            "merge_id",
            sa.String(36),
            primary_key=True,
            comment="Unique merge identifier (UUID) - used for undo",
        ),
        # Tenant isolation
        sa.Column(
            "tenant_id",
            sa.String(64),
            nullable=False,
            index=True,
            comment="Tenant isolation key",
        ),
        sa.Column(
            "space_id",
            sa.String(64),
            nullable=False,
            index=True,
            comment="Space isolation key",
        ),
        # Entity references
        sa.Column(
            "primary_entity_id",
            sa.String(64),
            nullable=False,
            index=True,
            comment="Entity ID that survived the merge (has more history)",
        ),
        sa.Column(
            "secondary_entity_id",
            sa.String(64),
            nullable=False,
            index=True,
            comment="Entity ID that was merged into primary (now MERGED status)",
        ),
        # Snapshots for undo (JSONB for efficiency)
        sa.Column(
            "primary_snapshot",
            postgresql.JSONB,
            nullable=False,
            comment="Full snapshot of primary entity before merge (for audit)",
        ),
        sa.Column(
            "secondary_snapshot",
            postgresql.JSONB,
            nullable=False,
            comment="Full snapshot of secondary entity before merge (for undo)",
        ),
        # Cascade tracking
        sa.Column(
            "cascade_counts",
            postgresql.JSONB,
            nullable=False,
            comment="Rows updated per table: {kg_edges_source, kg_edges_target, hipp_events, epi, sem, social, procedural, vec, total}",
        ),
        # Audit fields
        sa.Column(
            "merge_reason",
            sa.String(512),
            nullable=False,
            comment="Reason for merge (e.g., 'Same person - user confirmed')",
        ),
        sa.Column(
            "initiated_by",
            sa.String(64),
            nullable=False,
            comment="User ID or system component that initiated merge",
        ),
        sa.Column(
            "merged_at",
            sa.BigInteger,
            nullable=False,
            index=True,
            comment="Unix timestamp (ms) when merge occurred",
        ),
        # Undo fields
        sa.Column(
            "reversed_at",
            sa.BigInteger,
            nullable=True,
            comment="Unix timestamp (ms) when merge was reversed (NULL if not reversed)",
        ),
        sa.Column(
            "reversed_by",
            sa.String(64),
            nullable=True,
            comment="User ID or system component that reversed the merge",
        ),
        # Schema versioning
        sa.Column(
            "schema_version",
            sa.SmallInteger,
            nullable=False,
            server_default="1",
            comment="Schema version for future migrations",
        ),
        # Table-level comment
        comment="Entity merge audit trail with undo support. Tracks all merges, their cascade impact, and enables reversal. Spec: M4_EXECUTION.md Issue 4.4.7",
    )

    # ============================================================
    # Add merge_cascade_id to cascade tables
    # ============================================================
    # This column tracks which rows were affected by a specific merge,
    # enabling targeted undo operations.

    # List of tables that need merge_cascade_id
    cascade_tables = [
        "st_kg_edges",
        "st_hipp_events",
        "st_epi",
        "st_sem",
        "st_social",
        "st_procedural",
        "st_vec",
    ]

    for table_name in cascade_tables:
        # Add merge_cascade_id column
        op.add_column(
            table_name,
            sa.Column(
                "merge_cascade_id",
                sa.String(36),
                nullable=True,
                index=True,
                comment="Tracks which merge operation affected this row (for undo)",
            ),
        )

    # ============================================================
    # Add merge columns to st_kg_dom (entity table)
    # ============================================================
    # These columns track merge status on the entity itself

    op.add_column(
        "st_kg_dom",
        sa.Column(
            "merged_into",
            sa.String(64),
            nullable=True,
            index=True,
            comment="Entity ID this was merged into (when archival_status=MERGED)",
        ),
    )
    op.add_column(
        "st_kg_dom",
        sa.Column(
            "merged_at",
            sa.BigInteger,
            nullable=True,
            comment="Unix timestamp (ms) when entity was merged",
        ),
    )
    op.add_column(
        "st_kg_dom",
        sa.Column(
            "merged_by",
            sa.String(64),
            nullable=True,
            comment="User/system that performed the merge",
        ),
    )

    # ============================================================
    # Create composite indexes for common queries
    # ============================================================

    # Query: Find merges by entity (either side)
    op.create_index(
        "ix_st_entity_merges_entity_lookup",
        "st_entity_merges",
        ["primary_entity_id", "secondary_entity_id"],
        unique=False,
    )

    # Query: Find active (non-reversed) merges
    op.create_index(
        "ix_st_entity_merges_active",
        "st_entity_merges",
        ["merged_at"],
        unique=False,
        postgresql_where=sa.text("reversed_at IS NULL"),
    )

    # Query: Find reversed merges (for audit)
    op.create_index(
        "ix_st_entity_merges_reversed",
        "st_entity_merges",
        ["reversed_at"],
        unique=False,
        postgresql_where=sa.text("reversed_at IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_entity_merges table and merge_cascade_id columns."""
    # Drop indexes first
    op.drop_index("ix_st_entity_merges_reversed", table_name="st_entity_merges")
    op.drop_index("ix_st_entity_merges_active", table_name="st_entity_merges")
    op.drop_index("ix_st_entity_merges_entity_lookup", table_name="st_entity_merges")

    # Remove merge columns from st_kg_dom
    op.drop_column("st_kg_dom", "merged_by")
    op.drop_column("st_kg_dom", "merged_at")
    op.drop_column("st_kg_dom", "merged_into")

    # Remove merge_cascade_id from cascade tables
    cascade_tables = [
        "st_kg_edges",
        "st_hipp_events",
        "st_epi",
        "st_sem",
        "st_social",
        "st_procedural",
        "st_vec",
    ]

    for table_name in cascade_tables:
        op.drop_column(table_name, "merge_cascade_id")

    # Drop st_entity_merges table
    op.drop_table("st_entity_merges")
