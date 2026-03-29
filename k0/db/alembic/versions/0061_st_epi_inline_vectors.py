"""Add inline vector and text preservation columns to st_epi.

Revision ID: 0061
Revises: 0060
Create Date: 2026-01-15

GAP-001: Cross-Layer Vector & Text Linking — Milestone 1

Problem (GAP-001):
    st_hipp_events decays in 20 days but truth layers live 1-5 years.
    After st_hipp_events is tombstoned, original text and vector provenance is lost.

Solution:
    Add inline columns to preserve source texts and store embeddings directly
    in truth layers, eliminating st_vec dependency for consolidated memories.

New Columns:
    source_texts_json: JSON array of original source event texts (preserved before decay)
    embedding_text:    Generated text used for UltraBERT embedding (template-based summary)
    embedding_vector:  768-dim float32 vector as BYTEA (3072 bytes)
    embedding_model:   Model version that generated the embedding

References:
    - GAP_001_CROSS_LAYER_VECTOR_LINKING.md (Section 5.5: Inline Vectors)
    - GAP_001_MILESTONE_1_SCHEMA_MIGRATION.md (Issue 1.1)
    - Base schema: 0027_st_epi.py
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0061"
down_revision: str = "0060"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add inline vector and text preservation columns to st_epi."""
    # ============================================================
    # source_texts_json: Preserve original event texts before decay
    # ============================================================
    # JSON array of source event texts from st_hipp_events.text
    # Populated during R7 consolidation before events are tombstoned
    # Example: ["Had dinner with mom", "At Olive Garden restaurant"]
    op.add_column(
        "st_epi",
        sa.Column(
            "source_texts_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of source event texts (preserved before st_hipp_events decay)",
        ),
    )

    # ============================================================
    # embedding_text: Template-based summary for embedding
    # ============================================================
    # Generated text that combines source texts into embeddable format
    # Used by SummaryGenerator (M2) with templates per layer type
    # Example: "Episode: Had dinner with mom at Olive Garden. Duration: 2 hours."
    op.add_column(
        "st_epi",
        sa.Column(
            "embedding_text",
            sa.Text(),
            nullable=True,
            comment="Generated text used for UltraBERT embedding (template-based summary)",
        ),
    )

    # ============================================================
    # embedding_vector: Inline 768-dim vector storage
    # ============================================================
    # 768-dim float32 vector stored as BYTEA (3072 bytes)
    # Replaces st_vec JOIN for consolidated memories
    # Enables direct vector queries without cross-table JOINs
    op.add_column(
        "st_epi",
        sa.Column(
            "embedding_vector",
            sa.LargeBinary(),
            nullable=True,
            comment="768-dim UltraBERT embedding as BYTEA (3072 bytes)",
        ),
    )

    # ============================================================
    # embedding_model: Version tracking for model upgrades
    # ============================================================
    # Tracks which model version generated this embedding
    # Enables re-embedding when model is upgraded
    op.add_column(
        "st_epi",
        sa.Column(
            "embedding_model",
            sa.Text(),
            nullable=True,
            server_default="ultrabert-v2.1.0",
            comment="Embedding model version (e.g., ultrabert-v2.1.0)",
        ),
    )


def downgrade() -> None:
    """Remove inline vector and text preservation columns from st_epi."""
    op.drop_column("st_epi", "embedding_model")
    op.drop_column("st_epi", "embedding_vector")
    op.drop_column("st_epi", "embedding_text")
    op.drop_column("st_epi", "source_texts_json")
