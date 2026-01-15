"""Create st_pruned_entities table for regret tracking.

Revision ID: 0049
Revises: 0048
Create Date: 2025-01-04

K0 PostgreSQL Migration - P03 Consolidation

Tracks entities that were pruned but may later be queried (regret detection).
Enables learning to adjust decay rates based on prune regret signals.

Dossier Reference: Section 6.19 st_pruned_entities
Retention: 14 days (matches regret tracking window)
Isolation: RLS enforced for multi-tenant security
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0049"
down_revision: str = "0048"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_pruned_entities table with RLS."""
    op.create_table(
        "st_pruned_entities",
        # Identity
        sa.Column(
            "prune_id",
            sa.Text,
            primary_key=True,
            comment="Unique prune event ID",
        ),
        sa.Column(
            "entity_id",
            sa.Text,
            nullable=False,
            comment="Original entity ID (before pruning)",
        ),
        sa.Column(
            "entity_type",
            sa.Text,
            nullable=False,
            comment="PERSON, PLACE, THING, etc.",
        ),
        # Matching data (for regret detection)
        sa.Column(
            "canonical_name",
            sa.Text,
            nullable=False,
            comment="Normalized name for fuzzy matching",
        ),
        # Note: embedding stored as TEXT (JSON array) for compatibility
        # pgvector extension required for VECTOR type
        sa.Column(
            "embedding",
            sa.Text,
            nullable=False,
            comment="Embedding as JSON array for semantic matching",
        ),
        # Context
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="Isolation by space",
        ),
        sa.Column(
            "layer_table",
            sa.Text,
            nullable=False,
            comment="Source table (st_epi_entities, st_sem_entities, etc.)",
        ),
        sa.Column(
            "decay_factor_at_prune",
            sa.Float,
            nullable=False,
            comment="What decay_factor was when pruned",
        ),
        sa.Column(
            "lambda_at_prune",
            sa.Float,
            nullable=False,
            comment="What lambda was used",
        ),
        # Timestamps (Unix ms)
        sa.Column(
            "pruned_at",
            sa.BigInteger,
            nullable=False,
            comment="When pruned (epoch ms)",
        ),
        # Regret matching columns (nullable until matched)
        sa.Column(
            "matched_query_id",
            sa.Text,
            nullable=True,
            comment="If regret detected, which query matched",
        ),
        sa.Column(
            "matched_at",
            sa.BigInteger,
            nullable=True,
            comment="When regret detected (epoch ms)",
        ),
        sa.Column(
            "match_type",
            sa.Text,
            nullable=True,
            comment="STRONG_MATCH, LIKELY_MATCH, SEMANTIC_MATCH",
        ),
        sa.Column(
            "match_confidence",
            sa.Float,
            nullable=True,
            comment="Match confidence [0, 1]",
        ),
        # CHECK constraints
        sa.CheckConstraint(
            "entity_type IN ('PERSON', 'PLACE', 'THING', 'EVENT', 'CONCEPT', "
            "'ORGANIZATION', 'ACTIVITY', 'OTHER')",
            name="ck_pruned_entity_type",
        ),
        sa.CheckConstraint(
            "match_type IS NULL OR match_type IN "
            "('STRONG_MATCH', 'LIKELY_MATCH', 'SEMANTIC_MATCH', 'NO_MATCH')",
            name="ck_pruned_match_type",
        ),
        sa.CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0.0 AND match_confidence <= 1.0)",
            name="ck_pruned_match_confidence",
        ),
        sa.CheckConstraint(
            "decay_factor_at_prune >= 0.0 AND decay_factor_at_prune <= 1.0",
            name="ck_pruned_decay_factor",
        ),
    )

    # Index 1: Entity type and space for type-based queries
    op.create_index(
        "idx_pruned_entity_type",
        "st_pruned_entities",
        ["entity_type", "space_id"],
    )

    # Index 2: Space and time for cleanup and time-based queries
    op.create_index(
        "idx_pruned_space_time",
        "st_pruned_entities",
        ["space_id", sa.text("pruned_at DESC")],
    )

    # Index 3: Cleanup index (only unmatched entities)
    op.create_index(
        "idx_pruned_cleanup",
        "st_pruned_entities",
        ["pruned_at"],
        postgresql_where=sa.text("matched_at IS NULL"),
    )

    # Index 4: Canonical name for text matching
    op.create_index(
        "idx_pruned_canonical",
        "st_pruned_entities",
        ["space_id", "canonical_name"],
    )

    # Index 5: Entity ID for lookups
    op.create_index(
        "idx_pruned_entity_id",
        "st_pruned_entities",
        ["entity_id", "space_id"],
    )

    # Enable Row Level Security
    op.execute("ALTER TABLE st_pruned_entities ENABLE ROW LEVEL SECURITY;")

    # RLS Policy: Users can only see pruned entities from their spaces
    # Uses simpler space_id matching (consistent with other P03 tables)
    op.execute(
        """
        CREATE POLICY st_pruned_entities_isolation ON st_pruned_entities
            FOR ALL USING (space_id = current_setting('app.current_space_id', true)::text)
        """
    )


def downgrade() -> None:
    """Drop st_pruned_entities table and all indexes."""
    # Drop RLS policy first
    op.execute("DROP POLICY IF EXISTS st_pruned_entities_isolation ON st_pruned_entities;")
    op.execute("ALTER TABLE st_pruned_entities DISABLE ROW LEVEL SECURITY;")

    # Drop indexes
    op.drop_index("idx_pruned_entity_id", table_name="st_pruned_entities")
    op.drop_index("idx_pruned_canonical", table_name="st_pruned_entities")
    op.drop_index("idx_pruned_cleanup", table_name="st_pruned_entities")
    op.drop_index("idx_pruned_space_time", table_name="st_pruned_entities")
    op.drop_index("idx_pruned_entity_type", table_name="st_pruned_entities")

    # Drop table
    op.drop_table("st_pruned_entities")
