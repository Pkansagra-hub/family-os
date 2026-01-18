"""Add inline vector and text preservation columns to st_procedural.

Revision ID: 0063
Revises: 0062
Create Date: 2026-01-15

GAP-001: Cross-Layer Vector & Text Linking — Milestone 1

Problem (GAP-001):
    st_procedural has NO embedding support and NO text content.
    Cannot search for habits/routines by semantic similarity.

Solution:
    Add inline columns for vector storage and text preservation.
    embedding_text will be generated from routine name + description + steps.

New Columns:
    source_texts_json: JSON array of source event texts that evidence this routine
    embedding_text:    Template-based routine summary for embedding
    embedding_vector:  768-dim float32 vector as BYTEA (3072 bytes)
    embedding_model:   Model version that generated the embedding

References:
    - GAP_001_CROSS_LAYER_VECTOR_LINKING.md (Section 2.5: st_procedural Analysis)
    - GAP_001_MILESTONE_1_SCHEMA_MIGRATION.md (Issue 1.3)
    - Base schema: 0029_st_procedural.py
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0063"
down_revision: str = "0062"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add inline vector and text preservation columns to st_procedural."""
    # ============================================================
    # source_texts_json: Evidence events for routine detection
    # ============================================================
    # JSON array of event texts that evidenced this routine/habit
    # Example: ["Morning coffee at 7am", "Had espresso before work"]
    op.add_column(
        "st_procedural",
        sa.Column(
            "source_texts_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of source event texts (routine evidence)",
        ),
    )

    # ============================================================
    # embedding_text: Template-based routine summary
    # ============================================================
    # Generated from routine_name + description + temporal pattern
    # Example: "Daily routine: Morning coffee ritual at 7am, frequency: daily"
    op.add_column(
        "st_procedural",
        sa.Column(
            "embedding_text",
            sa.Text(),
            nullable=True,
            comment="Generated text for UltraBERT embedding (routine summary)",
        ),
    )

    # ============================================================
    # embedding_vector: Inline 768-dim vector storage
    # ============================================================
    op.add_column(
        "st_procedural",
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
        "st_procedural",
        sa.Column(
            "embedding_model",
            sa.Text(),
            nullable=True,
            server_default="ultrabert-v2.1.0",
            comment="Embedding model version (e.g., ultrabert-v2.1.0)",
        ),
    )


def downgrade() -> None:
    """Remove inline vector and text preservation columns from st_procedural."""
    op.drop_column("st_procedural", "embedding_model")
    op.drop_column("st_procedural", "embedding_vector")
    op.drop_column("st_procedural", "embedding_text")
    op.drop_column("st_procedural", "source_texts_json")
