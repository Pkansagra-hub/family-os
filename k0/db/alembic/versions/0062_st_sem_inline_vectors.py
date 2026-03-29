"""Add inline vector and text preservation columns to st_sem.

Revision ID: 0062
Revises: 0061
Create Date: 2026-01-15

GAP-001: Cross-Layer Vector & Text Linking — Milestone 1

Problem (GAP-001):
    st_sem has pattern_description column but it's often NULL (GAP Pain Point 4).
    No mechanism to preserve source event texts that formed the semantic pattern.

Solution:
    Add inline columns to preserve source texts and store embeddings directly.
    Note: st_sem already has pattern_description but writers don't populate it.
    embedding_text will be generated from template combining source texts.

New Columns:
    source_texts_json: JSON array of source event texts that formed this pattern
    embedding_text:    Template-based pattern summary for embedding
    embedding_vector:  768-dim float32 vector as BYTEA (3072 bytes)
    embedding_model:   Model version that generated the embedding

References:
    - GAP_001_CROSS_LAYER_VECTOR_LINKING.md (Section 2.4: st_sem Analysis)
    - GAP_001_MILESTONE_1_SCHEMA_MIGRATION.md (Issue 1.2)
    - Base schema: 0028_st_sem.py
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0062"
down_revision: str = "0061"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add inline vector and text preservation columns to st_sem."""
    # ============================================================
    # source_texts_json: Preserve source event texts
    # ============================================================
    # JSON array of texts from events that contributed to this pattern
    # Example for emotional_trend: ["felt anxious about work", "stressed about deadline"]
    op.add_column(
        "st_sem",
        sa.Column(
            "source_texts_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of source event texts (pattern sources)",
        ),
    )

    # ============================================================
    # embedding_text: Template-based pattern summary
    # ============================================================
    # Generated from pattern_type + pattern_name + source texts
    # Example: "Emotional trend: Recurring anxiety about work deadlines"
    op.add_column(
        "st_sem",
        sa.Column(
            "embedding_text",
            sa.Text(),
            nullable=True,
            comment="Generated text for UltraBERT embedding (pattern summary)",
        ),
    )

    # ============================================================
    # embedding_vector: Inline 768-dim vector storage
    # ============================================================
    op.add_column(
        "st_sem",
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
        "st_sem",
        sa.Column(
            "embedding_model",
            sa.Text(),
            nullable=True,
            server_default="ultrabert-v2.1.0",
            comment="Embedding model version (e.g., ultrabert-v2.1.0)",
        ),
    )


def downgrade() -> None:
    """Remove inline vector and text preservation columns from st_sem."""
    op.drop_column("st_sem", "embedding_model")
    op.drop_column("st_sem", "embedding_vector")
    op.drop_column("st_sem", "embedding_text")
    op.drop_column("st_sem", "source_texts_json")
