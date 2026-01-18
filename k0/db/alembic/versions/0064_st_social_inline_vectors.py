"""Add inline vector and text preservation columns to st_social.

Revision ID: 0064
Revises: 0063
Create Date: 2026-01-15

GAP-001: Cross-Layer Vector & Text Linking — Milestone 1

Problem (GAP-001):
    st_social has NO embedding support and NO text content.
    Cannot search for relationships by semantic similarity.
    Recent 0054 migration added UltraBERT enrichment columns but no embeddings.

Solution:
    Add inline columns for vector storage and text preservation.
    embedding_text will be generated from relationship context.

New Columns:
    source_texts_json: JSON array of source event texts involving this relationship
    embedding_text:    Template-based relationship summary for embedding
    embedding_vector:  768-dim float32 vector as BYTEA (3072 bytes)
    embedding_model:   Model version that generated the embedding

References:
    - GAP_001_CROSS_LAYER_VECTOR_LINKING.md (Section 2.6: st_social Analysis)
    - GAP_001_MILESTONE_1_SCHEMA_MIGRATION.md (Issue 1.4)
    - Base schema: 0030_st_social.py
    - Recent enrichment: 0054_st_social_ultrabert_enrichment.py
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0064"
down_revision: str = "0063"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add inline vector and text preservation columns to st_social."""
    # ============================================================
    # source_texts_json: Events involving this relationship
    # ============================================================
    # JSON array of event texts that involved this relationship
    # Example: ["Had lunch with Sarah", "Sarah helped with project"]
    op.add_column(
        "st_social",
        sa.Column(
            "source_texts_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of source event texts (relationship interactions)",
        ),
    )

    # ============================================================
    # embedding_text: Template-based relationship summary
    # ============================================================
    # Generated from person names + relationship type + interaction summary
    # Example: "Relationship: Close friend Sarah. Recent: lunch, project help."
    op.add_column(
        "st_social",
        sa.Column(
            "embedding_text",
            sa.Text(),
            nullable=True,
            comment="Generated text for UltraBERT embedding (relationship summary)",
        ),
    )

    # ============================================================
    # embedding_vector: Inline 768-dim vector storage
    # ============================================================
    op.add_column(
        "st_social",
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
        "st_social",
        sa.Column(
            "embedding_model",
            sa.Text(),
            nullable=True,
            server_default="ultrabert-v2.1.0",
            comment="Embedding model version (e.g., ultrabert-v2.1.0)",
        ),
    )


def downgrade() -> None:
    """Remove inline vector and text preservation columns from st_social."""
    op.drop_column("st_social", "embedding_model")
    op.drop_column("st_social", "embedding_vector")
    op.drop_column("st_social", "embedding_text")
    op.drop_column("st_social", "source_texts_json")
