"""Add metadata preservation columns to st_epi (Epic 6.5).

Revision ID: 0086
Revises: 0085
Create Date: 2026-03-09

Milestone 6 Epic 6.5: Metadata Preservation In Truth Writer

R2 computes rich episode metadata that was previously discarded by the
truth writer. This migration adds columns for the 9 lost fields:

- centroid_metadata_json: M4-RSCH-02 secondary centroids (emotional_peak,
  narrative_anchor, start, end) for multi-probe retrieval (+4.9% MRR)
- ambiguity_score: M0-E2-I5 uncertainty quantification
- entity_ids_json: M0-E2-I3 NER entity references for KG linking
- dominant_sentiment: Sentiment aggregation across member events
- dominant_emotion: Most common emotion across member events
- aggregated_sentiment: Per-member sentiment synthesis
- aggregated_salience: Salience aggregation
- dominant_social_context: Social context inference
- activity_type_ultrabert: Issue 0060 12-type UltraBERT classification
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0086"
down_revision: str = "0085"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add metadata preservation columns to st_epi."""
    # M4-RSCH-02: Secondary centroid metadata (best_of_all MRR=0.9627)
    op.add_column("st_epi", sa.Column("centroid_metadata_json", sa.Text, nullable=True))
    # M0-E2-I5: Uncertainty quantification
    op.add_column("st_epi", sa.Column("ambiguity_score", sa.Float, nullable=True))
    # M0-E2-I3: NER entity references
    op.add_column("st_epi", sa.Column("entity_ids_json", sa.Text, nullable=True))
    # Affect aggregation
    op.add_column("st_epi", sa.Column("dominant_sentiment", sa.Float, nullable=True))
    op.add_column("st_epi", sa.Column("dominant_emotion", sa.Text, nullable=True))
    op.add_column("st_epi", sa.Column("aggregated_sentiment", sa.Float, nullable=True))
    op.add_column("st_epi", sa.Column("aggregated_salience", sa.Float, nullable=True))
    # Social context
    op.add_column("st_epi", sa.Column("dominant_social_context", sa.Text, nullable=True))
    # Issue 0060: 12-type UltraBERT classification
    op.add_column("st_epi", sa.Column("activity_type_ultrabert", sa.Text, nullable=True))


def downgrade() -> None:
    """Remove metadata preservation columns from st_epi."""
    op.drop_column("st_epi", "activity_type_ultrabert")
    op.drop_column("st_epi", "dominant_social_context")
    op.drop_column("st_epi", "aggregated_salience")
    op.drop_column("st_epi", "aggregated_sentiment")
    op.drop_column("st_epi", "dominant_emotion")
    op.drop_column("st_epi", "dominant_sentiment")
    op.drop_column("st_epi", "entity_ids_json")
    op.drop_column("st_epi", "ambiguity_score")
    op.drop_column("st_epi", "centroid_metadata_json")
