"""Add query tracking columns to st_kg_dom and st_kg_edges.

Revision ID: 0059
Revises: 0058
Create Date: 2026-01-12

P03 Consolidation Pipeline - Intent Routing Schema Update

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING
Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 1.3

This migration adds columns needed for query-based intent routing:

st_kg_dom new columns:
- query_count: Number of times entity was queried (query_memory intent)
- last_queried_at: Timestamp of last query (Unix ms)
- milestones_json: JSON array of milestone events (share_news intent)

st_kg_edges new columns:
- query_count: Number of times edge was queried
- last_queried_at: Timestamp of last query (Unix ms)
- sentiment_avg: Average sentiment across mentions (express_feeling intent)

Intent → KG Routing:
| Intent          | KG Column Impact                |
|-----------------|---------------------------------|
| query_memory    | Increment query_count           |
| share_news      | Append to milestones_json       |
| express_feeling | Update sentiment_avg on edges   |

Query count is used for:
- Importance weighting in retrieval
- Decay adjustment (frequently queried = slower decay)
- Analytics on entity usage patterns

Dossier Reference: P03 Consolidation Dossier Section 6.8, 6.9
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0059"
down_revision: str = "0058"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add query tracking columns to st_kg_dom and st_kg_edges."""
    # ============================================================
    # st_kg_dom: Query tracking and milestone storage
    # ============================================================

    # Query count: Incremented when entity is queried (query_memory intent)
    op.add_column(
        "st_kg_dom",
        sa.Column("query_count", sa.Integer, server_default="0", nullable=False),
    )

    # Last queried timestamp: Unix milliseconds
    op.add_column(
        "st_kg_dom",
        sa.Column("last_queried_at", sa.BigInteger, nullable=True),
    )

    # Milestones JSON: Array of milestone events from share_news intent
    # Format: [{"event_id": "...", "type": "ACHIEVEMENT", "ts": ...}, ...]
    op.add_column(
        "st_kg_dom",
        sa.Column("milestones_json", sa.Text, nullable=True),
    )

    # ============================================================
    # st_kg_edges: Query tracking and sentiment
    # ============================================================

    # Query count: Incremented when edge is queried
    op.add_column(
        "st_kg_edges",
        sa.Column("query_count", sa.Integer, server_default="0", nullable=False),
    )

    # Last queried timestamp: Unix milliseconds
    op.add_column(
        "st_kg_edges",
        sa.Column("last_queried_at", sa.BigInteger, nullable=True),
    )

    # Sentiment average: Running average sentiment for express_feeling routing
    # Range: [-1.0, 1.0] where -1 = negative, 0 = neutral, 1 = positive
    op.add_column(
        "st_kg_edges",
        sa.Column("sentiment_avg", sa.Float, nullable=True),
    )

    # ============================================================
    # Indexes for efficient query count lookups
    # ============================================================

    # Index for finding frequently queried entities
    op.create_index(
        "idx_kg_dom_query_count",
        "st_kg_dom",
        [sa.text("query_count DESC")],
        postgresql_where=sa.text("query_count > 0"),
    )

    # Index for finding frequently queried edges
    op.create_index(
        "idx_kg_edges_query_count",
        "st_kg_edges",
        [sa.text("query_count DESC")],
        postgresql_where=sa.text("query_count > 0"),
    )


def downgrade() -> None:
    """Remove query tracking columns from st_kg_dom and st_kg_edges."""
    # Drop indexes first
    op.drop_index("idx_kg_edges_query_count", table_name="st_kg_edges")
    op.drop_index("idx_kg_dom_query_count", table_name="st_kg_dom")

    # Drop st_kg_edges columns
    op.drop_column("st_kg_edges", "sentiment_avg")
    op.drop_column("st_kg_edges", "last_queried_at")
    op.drop_column("st_kg_edges", "query_count")

    # Drop st_kg_dom columns
    op.drop_column("st_kg_dom", "milestones_json")
    op.drop_column("st_kg_dom", "last_queried_at")
    op.drop_column("st_kg_dom", "query_count")
