"""Add tsvector columns for full-text search.

Revision ID: 0028
Revises: 0027
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.2.2 - Issue 2.2.2.4)

This migration adds TSVECTOR columns to st_hipp_events for
PostgreSQL full-text search capabilities.

Columns added:
- text_search_vector: Generated from text + text_normalized
- entities_search_vector: Updated via trigger from entities_json

Also creates a trigger to maintain entities_search_vector on INSERT/UPDATE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0028"
down_revision: str = "0027"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add tsvector columns and trigger for full-text search."""
    # Add generated tsvector column for text search
    # Combines text (weight A) and text_normalized (weight B)
    op.execute(
        """
        ALTER TABLE st_hipp_events
        ADD COLUMN text_search_vector TSVECTOR
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', COALESCE(text, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(text_normalized, '')), 'B')
        ) STORED
        """
    )

    # Add column for entities search vector (updated via trigger)
    op.add_column(
        "st_hipp_events",
        sa.Column("entities_search_vector", postgresql.TSVECTOR, nullable=True),
    )

    # Create trigger function to update entities_search_vector from JSONB
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_entities_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.entities_search_vector := to_tsvector('english',
                COALESCE(NEW.entities_json::text, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    # Create trigger on INSERT/UPDATE of entities_json
    op.execute(
        """
        CREATE TRIGGER trg_update_entities_search
        BEFORE INSERT OR UPDATE OF entities_json ON st_hipp_events
        FOR EACH ROW EXECUTE FUNCTION update_entities_search_vector()
        """
    )


def downgrade() -> None:
    """Remove tsvector columns and trigger."""
    # Drop trigger first
    op.execute("DROP TRIGGER IF EXISTS trg_update_entities_search ON st_hipp_events")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_entities_search_vector()")

    # Drop columns
    op.drop_column("st_hipp_events", "entities_search_vector")
    op.drop_column("st_hipp_events", "text_search_vector")
