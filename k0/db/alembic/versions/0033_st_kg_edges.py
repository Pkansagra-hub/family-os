"""Create st_kg_edges (Knowledge Graph Relationships) table.

Revision ID: 0033
Revises: 0032
Create Date: 2026-01-01

P03 Consolidation Pipeline - M2 Storage Migration

Brain Analog: Associative Connections
Role: Typed relationships between entities with temporal validity
Written by: P03 R7 (from R4 relationship discovery)

Dossier Reference: Section 6.9 st_kg_edges
Schema: 22 columns, 3 indexes, 2 Foreign Keys (to st_kg_dom)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0033"
down_revision: str = "0032"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_kg_edges table for knowledge graph relationships."""
    op.create_table(
        "st_kg_edges",
        # ============================================================
        # Identity (3 columns)
        # ============================================================
        sa.Column("edge_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # ============================================================
        # Relationship Endpoints (2 columns)
        # ============================================================
        sa.Column("source_entity_id", sa.Text, nullable=False),  # From entity
        sa.Column("target_entity_id", sa.Text, nullable=False),  # To entity
        # ============================================================
        # Versioning / Immutability (3 columns)
        # ============================================================
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.Text, nullable=True),
        sa.Column("is_canonical", sa.Boolean, server_default="TRUE"),
        # ============================================================
        # Relationship Type (2 columns)
        # ============================================================
        sa.Column("relation_type", sa.Text, nullable=False),  # WORKS_AT, LIVES_IN, KNOWS, etc.
        sa.Column("relation_subtype", sa.Text, nullable=True),
        # ============================================================
        # Relationship Properties (1 column)
        # ============================================================
        sa.Column("properties_json", sa.Text, nullable=True),  # Edge attributes
        # ============================================================
        # Strength & Confidence (2 columns)
        # ============================================================
        sa.Column("edge_weight", sa.Float, server_default="1.0"),  # Relationship strength
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        # ============================================================
        # Source Evidence (2 columns)
        # ============================================================
        sa.Column("source_episodes_json", sa.Text, nullable=True),
        sa.Column("co_occurrence_count", sa.Integer, server_default="1"),  # Hebbian: how often seen
        # ============================================================
        # Truth Tracking (3 columns)
        # ============================================================
        sa.Column("observation_count", sa.Integer, server_default="1"),
        sa.Column("last_observed_at", sa.BigInteger, nullable=True),
        sa.Column("decay_factor", sa.Float, server_default="1.0"),
        # ============================================================
        # Lifecycle (1 column)
        # ============================================================
        sa.Column("archival_status", sa.Text, server_default="'ACTIVE'"),
        # ============================================================
        # Timestamps + Bitemporal (4 columns)
        # ============================================================
        sa.Column("valid_from", sa.BigInteger, nullable=False),
        sa.Column("valid_to", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        # ============================================================
        # Foreign Keys (per dossier §6.9)
        # ============================================================
        sa.ForeignKeyConstraint(
            ["source_entity_id"],
            ["st_kg_dom.entity_id"],
            name="fk_kg_edges_source",
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"],
            ["st_kg_dom.entity_id"],
            name="fk_kg_edges_target",
        ),
        # ============================================================
        # CHECK Constraints
        # ============================================================
        sa.CheckConstraint(
            "archival_status IN ('ACTIVE', 'ARCHIVED', 'TOMBSTONE')",
            name="ck_kg_edges_archival_status",
        ),
    )

    # ============================================================
    # Indexes (3 indexes from dossier §6.9)
    # ============================================================
    op.create_index(
        "idx_kg_edges_source",
        "st_kg_edges",
        ["source_entity_id", "relation_type"],
    )
    op.create_index(
        "idx_kg_edges_target",
        "st_kg_edges",
        ["target_entity_id", "relation_type"],
    )
    op.create_index(
        "idx_kg_edges_canonical",
        "st_kg_edges",
        ["is_canonical", "archival_status"],
    )


def downgrade() -> None:
    """Drop st_kg_edges table and all indexes."""
    op.drop_index("idx_kg_edges_canonical", table_name="st_kg_edges")
    op.drop_index("idx_kg_edges_target", table_name="st_kg_edges")
    op.drop_index("idx_kg_edges_source", table_name="st_kg_edges")
    op.drop_table("st_kg_edges")
