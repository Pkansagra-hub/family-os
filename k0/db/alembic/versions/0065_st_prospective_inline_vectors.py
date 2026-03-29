"""Add inline vector and text preservation columns to st_prospective.

Revision ID: 0065
Revises: 0064
Create Date: 2026-01-15

GAP-001: Cross-Layer Vector & Text Linking — Milestone 1

Problem (GAP-001):
    st_prospective has intention_description but no embedding support.
    Cannot search for intentions/goals by semantic similarity.

Solution:
    Add inline columns for vector storage and text preservation.
    embedding_text can use existing intention_description + context.

New Columns:
    source_texts_json: JSON array of source event texts that created this intention
    embedding_text:    Template-based intention summary for embedding
    embedding_vector:  768-dim float32 vector as BYTEA (3072 bytes)
    embedding_model:   Model version that generated the embedding

References:
    - GAP_001_CROSS_LAYER_VECTOR_LINKING.md (Section 2.7: st_prospective Analysis)
    - GAP_001_MILESTONE_1_SCHEMA_MIGRATION.md (Issue 1.5)
    - Base schema: 0031_st_prospective.py
    - Intent types: 0057_st_prospective_intent_types.py
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0065"
down_revision: str = "0064"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add inline vector and text preservation columns to st_prospective."""
    # ============================================================
    # source_texts_json: Events that triggered this intention
    # ============================================================
    # JSON array of event texts that created this intention/goal
    # Example for reminder: ["Need to call mom tomorrow", "Remind me to call Medical Center"]
    op.add_column(
        "st_prospective",
        sa.Column(
            "source_texts_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of source event texts (intention triggers)",
        ),
    )

    # ============================================================
    # embedding_text: Template-based intention summary
    # ============================================================
    # Generated from intention_type + intention_description + target_date
    # Example: "Reminder: Call Medical Center about appointment. Due: tomorrow 3pm."
    op.add_column(
        "st_prospective",
        sa.Column(
            "embedding_text",
            sa.Text(),
            nullable=True,
            comment="Generated text for UltraBERT embedding (intention summary)",
        ),
    )

    # ============================================================
    # embedding_vector: Inline 768-dim vector storage
    # ============================================================
    op.add_column(
        "st_prospective",
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
        "st_prospective",
        sa.Column(
            "embedding_model",
            sa.Text(),
            nullable=True,
            server_default="ultrabert-v2.1.0",
            comment="Embedding model version (e.g., ultrabert-v2.1.0)",
        ),
    )


def downgrade() -> None:
    """Remove inline vector and text preservation columns from st_prospective."""
    op.drop_column("st_prospective", "embedding_model")
    op.drop_column("st_prospective", "embedding_vector")
    op.drop_column("st_prospective", "embedding_text")
    op.drop_column("st_prospective", "source_texts_json")
