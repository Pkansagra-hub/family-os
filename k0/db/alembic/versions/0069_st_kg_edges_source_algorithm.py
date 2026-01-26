"""Add source_algorithm column to st_kg_edges.

Revision ID: 0069
Revises: 0068
Create Date: 2026-01-24

P03 Consolidation Pipeline - R4 KG Consolidator Enhancement (GAP-007)

Adds source_algorithm column to track which algorithm produced each edge.
Backfills existing edges with 'co_occurrence' (default Hebbian reinforcement).

Dossier Reference: Epic 1.1 Issue 1.1.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0069"
down_revision: str = "0068"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Valid source algorithm values (documented in Epic Plan)
SOURCE_ALGORITHMS = [
    "co_occurrence",  # Existing Hebbian reinforcement
    "granger_causal",  # Existing Granger causality
    "semantic_similarity",  # NEW: Embedding similarity
    "temporal_proximity",  # NEW: Time window co-occurrence
    "contextual",  # NEW: Shared context features
    "transitive_closure",  # NEW: Graph inference
    "bayesian_causal",  # NEW: Bayesian causal inference
    "weight_normalization",  # NEW: Normalization adjustments
    "manual",  # User-provided edges
]


def upgrade() -> None:
    """Add source_algorithm column with backfill and index."""

    # Add the column (nullable initially for safe migration)
    op.add_column(
        "st_kg_edges",
        sa.Column("source_algorithm", sa.Text, nullable=True),
    )

    # Backfill existing edges with co_occurrence (default algorithm)
    op.execute(
        """
        UPDATE st_kg_edges
        SET source_algorithm = 'co_occurrence'
        WHERE source_algorithm IS NULL
        """
    )

    # Create index for algorithm-based queries
    op.create_index(
        "idx_kg_edges_source_algorithm",
        "st_kg_edges",
        ["tenant_id", "source_algorithm"],
    )


def downgrade() -> None:
    """Remove source_algorithm column and index."""

    op.drop_index("idx_kg_edges_source_algorithm", table_name="st_kg_edges")
    op.drop_column("st_kg_edges", "source_algorithm")
