"""Add evidence columns to st_kg_edges.

Revision ID: 0070
Revises: 0069
Create Date: 2026-01-24

P03 Consolidation Pipeline - R4 KG Consolidator Enhancement (GAP-007)

Adds evidence provenance columns:
- evidence_event_ids: Array of source event IDs
- evidence_episode_ids: Array of source episode IDs
- algorithm_params_json: Algorithm-specific parameters used
- inference_chain_json: For transitive closure - path taken

Dossier Reference: Epic 1.1 Issue 1.1.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0070"
down_revision: str = "0069"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add evidence columns to st_kg_edges."""

    # evidence_event_ids: Array of source event IDs that support this edge
    op.add_column(
        "st_kg_edges",
        sa.Column("evidence_event_ids", sa.ARRAY(sa.Text), nullable=True),
    )

    # evidence_episode_ids: Array of source episode IDs
    op.add_column(
        "st_kg_edges",
        sa.Column("evidence_episode_ids", sa.ARRAY(sa.Text), nullable=True),
    )

    # algorithm_params_json: Algorithm-specific parameters used to create edge
    op.add_column(
        "st_kg_edges",
        sa.Column("algorithm_params_json", sa.Text, nullable=True),
    )

    # inference_chain_json: For transitive closure - the path taken
    op.add_column(
        "st_kg_edges",
        sa.Column("inference_chain_json", sa.Text, nullable=True),
    )

    # Partial index for edges with event evidence (for efficient evidence queries)
    op.execute(
        """
        CREATE INDEX idx_kg_edges_has_evidence
        ON st_kg_edges (tenant_id, created_at DESC)
        WHERE evidence_event_ids IS NOT NULL
        """
    )


def downgrade() -> None:
    """Remove evidence columns from st_kg_edges."""

    op.execute("DROP INDEX IF EXISTS idx_kg_edges_has_evidence")
    op.drop_column("st_kg_edges", "inference_chain_json")
    op.drop_column("st_kg_edges", "algorithm_params_json")
    op.drop_column("st_kg_edges", "evidence_episode_ids")
    op.drop_column("st_kg_edges", "evidence_event_ids")
