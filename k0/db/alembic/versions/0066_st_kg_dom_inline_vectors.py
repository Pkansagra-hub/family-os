"""Add inline vector and text preservation columns to st_kg_dom.

Revision ID: 0066
Revises: 0065
Create Date: 2026-01-15

GAP-001: Cross-Layer Vector & Text Linking — Milestone 1

Problem (GAP-001):
    st_kg_dom has embedding_id but it's disconnected (no FK, never populated).
    Entity embeddings needed for BGT-SM semantic distance in R5 Dream Stage.
    Cannot search for entities by semantic similarity.

Solution:
    Add inline columns for vector storage and text preservation.
    embedding_text will be generated from entity name + type + description.
    Note: embedding_id column already exists but is not used.

New Columns:
    source_texts_json: JSON array of source event texts mentioning this entity
    embedding_text:    Template-based entity description for embedding
    embedding_vector:  768-dim float32 vector as BYTEA (3072 bytes)
    embedding_model:   Model version that generated the embedding

References:
    - GAP_001_CROSS_LAYER_VECTOR_LINKING.md (Section 2.8: st_kg_dom Analysis)
    - GAP_001_MILESTONE_1_SCHEMA_MIGRATION.md (Issue 1.6)
    - Base schema: 0032_st_kg_dom.py
    - M9 Fix: Entity embeddings needed for R5 BGT-SM
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0066"
down_revision: str = "0065"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add inline vector and text preservation columns to st_kg_dom."""
    # ============================================================
    # source_texts_json: Events mentioning this entity
    # ============================================================
    # JSON array of event texts where this entity was mentioned/observed
    # Example for PERSON entity: ["Had lunch with Sarah", "Sarah's birthday party"]
    op.add_column(
        "st_kg_dom",
        sa.Column(
            "source_texts_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of source event texts (entity mentions)",
        ),
    )

    # ============================================================
    # embedding_text: Template-based entity description
    # ============================================================
    # Generated from canonical_name + entity_type + context
    # Example: "Person: Sarah. Type: FAMILY_MEMBER. Context: sister, lives in Austin."
    op.add_column(
        "st_kg_dom",
        sa.Column(
            "embedding_text",
            sa.Text(),
            nullable=True,
            comment="Generated text for UltraBERT embedding (entity description)",
        ),
    )

    # ============================================================
    # embedding_vector: Inline 768-dim vector storage
    # ============================================================
    # Note: st_kg_dom already has embedding_id but it's never populated.
    # This inline vector replaces the st_vec dependency.
    op.add_column(
        "st_kg_dom",
        sa.Column(
            "embedding_vector",
            sa.LargeBinary(),
            nullable=True,
            comment="768-dim UltraBERT embedding as BYTEA (3072 bytes)",
        ),
    )

    # ============================================================
    # embedding_model: Version tracking
    # ============================================================
    op.add_column(
        "st_kg_dom",
        sa.Column(
            "embedding_model",
            sa.Text(),
            nullable=True,
            server_default="ultrabert-v2.1.0",
            comment="Embedding model version (e.g., ultrabert-v2.1.0)",
        ),
    )


def downgrade() -> None:
    """Remove inline vector and text preservation columns from st_kg_dom."""
    op.drop_column("st_kg_dom", "embedding_model")
    op.drop_column("st_kg_dom", "embedding_vector")
    op.drop_column("st_kg_dom", "embedding_text")
    op.drop_column("st_kg_dom", "source_texts_json")
