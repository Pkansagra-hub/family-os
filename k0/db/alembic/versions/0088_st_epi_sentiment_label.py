"""Add dominant_sentiment_label to st_epi.

Revision ID: 0088
Revises: 0087
Create Date: 2026-03-15

BUG 1: dominant_sentiment stores raw float (0.649) but callers need
the human-readable label (positive/negative/neutral). The float is kept
for CPN numeric compatibility; the new Text column stores the label
derived from the weighted score using the same thresholds as
st_hipp_events.sentiment_label.

Thresholds:
    score > 0.6  -> "positive"
    score < 0.4  -> "negative"
    else         -> "neutral"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0088"
down_revision: str = "0087"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add dominant_sentiment_label column to st_epi."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'st_epi' AND column_name = 'dominant_sentiment_label'"
        )
    )
    if result.fetchone() is None:
        op.add_column("st_epi", sa.Column("dominant_sentiment_label", sa.Text, nullable=True))


def downgrade() -> None:
    """Remove dominant_sentiment_label column from st_epi."""
    op.drop_column("st_epi", "dominant_sentiment_label")
