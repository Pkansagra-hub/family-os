"""Create st_kg_dom (Knowledge Graph Entities) table.

Revision ID: 0032
Revises: 0031
Create Date: 2026-01-01

P03 Consolidation Pipeline - M2 Storage Migration

Brain Analog: Semantic Memory (Concept Nodes)
Role: Canonical entities with attributes (people, places, things)
Written by: P03 R7 (from R4 entity extraction)

Dossier Reference: Section 6.8 st_kg_dom
Schema: 23 columns, 3 indexes
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0032"
down_revision: str = "0031"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_kg_dom table for knowledge graph entity storage."""
    op.create_table(
        "st_kg_dom",
        # ============================================================
        # Identity (3 columns)
        # ============================================================
        sa.Column("entity_id", sa.Text, primary_key=True),  # Canonical entity ID
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # ============================================================
        # Versioning / Immutability (3 columns)
        # ============================================================
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.Text, nullable=True),
        sa.Column("is_canonical", sa.Boolean, server_default="TRUE"),
        # ============================================================
        # Entity Type (2 columns)
        # ============================================================
        sa.Column("entity_type", sa.Text, nullable=False),  # PERSON, PLACE, ORG, THING, EVENT
        sa.Column("entity_subtype", sa.Text, nullable=True),  # More specific type
        # ============================================================
        # Entity Names (2 columns)
        # ============================================================
        sa.Column("canonical_name", sa.Text, nullable=False),  # Primary display name
        sa.Column("aliases_json", sa.Text, nullable=True),  # Alternative names/spellings
        # ============================================================
        # Attributes (1 column)
        # ============================================================
        sa.Column("attributes_json", sa.Text, nullable=True),  # Structured attributes
        # ============================================================
        # Embeddings (1 column)
        # ============================================================
        sa.Column("embedding_id", sa.Text, nullable=True),  # Entity embedding
        # ============================================================
        # Source Episodes (2 columns)
        # ============================================================
        sa.Column("source_episodes_json", sa.Text, nullable=True),
        sa.Column("first_mentioned_event_id", sa.Text, nullable=True),
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
            name="ck_kg_dom_archival_status",
        ),
    )

    # ============================================================
    # Indexes (3 indexes from dossier §6.8)
    # ============================================================
    op.create_index(
        "idx_kg_dom_tenant_type",
        "st_kg_dom",
        ["tenant_id", "entity_type"],
    )
    op.create_index(
        "idx_kg_dom_name",
        "st_kg_dom",
        ["canonical_name"],
    )
    op.create_index(
        "idx_kg_dom_canonical",
        "st_kg_dom",
        ["is_canonical", "archival_status"],
    )


def downgrade() -> None:
    """Drop st_kg_dom table and all indexes."""
    op.drop_index("idx_kg_dom_canonical", table_name="st_kg_dom")
    op.drop_index("idx_kg_dom_name", table_name="st_kg_dom")
    op.drop_index("idx_kg_dom_tenant_type", table_name="st_kg_dom")
    op.drop_table("st_kg_dom")
