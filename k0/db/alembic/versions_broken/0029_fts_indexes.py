"""Create GIN indexes for full-text search.

Revision ID: 0029
Revises: 0028
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.2.2 - Issue 2.2.2.5)

This migration creates GIN (Generalized Inverted Index) indexes for:
- text_search_vector: Full-text search on event text
- entities_search_vector: Full-text search on extracted entities
- entities_json: JSONB containment queries
- obligations_json: JSONB containment queries

GIN indexes are optimized for full-text search and JSONB operators.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0029"
down_revision: str = "0028"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create GIN indexes for full-text and JSONB search."""
    # GIN index for text search vector
    op.execute(
        """
        CREATE INDEX ix_st_hipp_text_search
        ON st_hipp_events
        USING gin (text_search_vector)
        """
    )

    # GIN index for entities search vector
    op.execute(
        """
        CREATE INDEX ix_st_hipp_entities_search
        ON st_hipp_events
        USING gin (entities_search_vector)
        """
    )

    # GIN index for entities_json JSONB queries
    # Uses jsonb_path_ops for @> containment queries
    op.execute(
        """
        CREATE INDEX ix_st_hipp_entities_json
        ON st_hipp_events
        USING gin (entities_json jsonb_path_ops)
        """
    )

    # GIN index for obligations_json JSONB queries
    op.execute(
        """
        CREATE INDEX ix_st_hipp_obligations
        ON st_hipp_events
        USING gin (obligations_json jsonb_path_ops)
        """
    )


def downgrade() -> None:
    """Drop GIN indexes."""
    op.drop_index("ix_st_hipp_obligations", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_entities_json", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_entities_search", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_text_search", table_name="st_hipp_events")
