"""Create st_learned_weights table (Adaptive parameters).

Revision ID: 0040
Revises: 0039
Create Date: 2025-01-01

Central storage for all learned hyperparameters across P03 formulas.
Single source of truth for adaptive parameters that learn from feedback.
Per-space isolation with hierarchical fallbacks.

Spec Reference: Dossier §6.17 st_learned_weights

Schema Features:
- 17 columns matching dossier specification
- CHECK constraints for param_scope, confidence, sample_count
- UNIQUE constraint for (space_id, param_key, param_scope, scope_id)
- 3 indexes for fast lookups
- RLS policy for multi-tenant isolation
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0040"
down_revision: str = "0039"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Valid param_scope values from dossier §6.17
PARAM_SCOPES = (
    "global",
    "space",
    "entity_type",
    "entity",
)


def upgrade() -> None:
    """Create st_learned_weights table with all columns and indexes."""
    op.create_table(
        "st_learned_weights",
        # Primary key - UUID
        sa.Column(
            "param_id",
            sa.Text,
            primary_key=True,
            comment="UUID primary key",
        ),
        # Parameter identification
        sa.Column(
            "param_key",
            sa.Text,
            nullable=False,
            comment="e.g., 'importance_emotional', 'decay_lambda_PERSON'",
        ),
        sa.Column(
            "param_scope",
            sa.Text,
            nullable=False,
            comment="Scope level: global, space, entity_type, entity",
        ),
        sa.Column(
            "scope_id",
            sa.Text,
            nullable=True,
            comment="space_id, entity_type, or entity_id (NULL for global)",
        ),
        # Space isolation
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="Isolation (always set)",
        ),
        # Parameter values
        sa.Column(
            "current_value",
            sa.Float,
            nullable=False,
            comment="Current learned value",
        ),
        sa.Column(
            "prior_value",
            sa.Float,
            nullable=False,
            comment="Initial/default value",
        ),
        # Learning metrics
        sa.Column(
            "confidence",
            sa.Float,
            nullable=False,
            server_default="0.0",
            comment="Learning confidence [0-1]",
        ),
        sa.Column(
            "sample_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Number of feedback samples",
        ),
        # Timestamps
        sa.Column(
            "last_updated_at",
            sa.BigInteger,
            nullable=False,
            comment="Timestamp (ms since epoch)",
        ),
        # Versioning
        sa.Column(
            "version",
            sa.Integer,
            nullable=False,
            server_default="1",
            comment="For parameter history/rollback",
        ),
        sa.Column(
            "previous_value",
            sa.Float,
            nullable=True,
            comment="Value before last update",
        ),
        # Quality tracking
        sa.Column(
            "quality_at_update",
            sa.Float,
            nullable=True,
            comment="Quality metric when last updated",
        ),
        sa.Column(
            "rollback_eligible",
            sa.Boolean,
            nullable=False,
            server_default="true",
            comment="Can be rolled back?",
        ),
        # Audit timestamps
        sa.Column(
            "created_at",
            sa.BigInteger,
            nullable=False,
            comment="Creation timestamp (Unix ms)",
        ),
        sa.Column(
            "updated_at",
            sa.BigInteger,
            nullable=False,
            comment="Last update timestamp (Unix ms)",
        ),
        # CHECK constraints
        sa.CheckConstraint(
            f"param_scope IN ({', '.join(repr(s) for s in PARAM_SCOPES)})",
            name="ck_param_scope",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_confidence_range",
        ),
        sa.CheckConstraint(
            "sample_count >= 0",
            name="ck_sample_count_nonneg",
        ),
        # UNIQUE constraint
        sa.UniqueConstraint(
            "space_id",
            "param_key",
            "param_scope",
            "scope_id",
            name="uq_learned_weights",
        ),
    )

    # Index 1: Fast lookup by space and key
    op.create_index(
        "idx_learned_weights_space_key",
        "st_learned_weights",
        ["space_id", "param_key"],
    )

    # Index 2: Scope-based queries
    op.create_index(
        "idx_learned_weights_scope",
        "st_learned_weights",
        ["space_id", "param_scope", "scope_id"],
    )

    # Index 3: Confidence-based filtering
    op.create_index(
        "idx_learned_weights_confidence",
        "st_learned_weights",
        [sa.text("confidence DESC")],
    )

    # RLS for multi-tenant isolation
    op.execute("ALTER TABLE st_learned_weights ENABLE ROW LEVEL SECURITY;")

    op.execute(
        """
        CREATE POLICY learned_weights_isolation ON st_learned_weights
            FOR ALL USING (space_id = current_setting('app.current_space_id', true)::text)
        """
    )


def downgrade() -> None:
    """Drop st_learned_weights table and all indexes."""
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS learned_weights_isolation ON st_learned_weights;")
    op.execute("ALTER TABLE st_learned_weights DISABLE ROW LEVEL SECURITY;")

    op.drop_index("idx_learned_weights_confidence", table_name="st_learned_weights")
    op.drop_index("idx_learned_weights_scope", table_name="st_learned_weights")
    op.drop_index("idx_learned_weights_space_key", table_name="st_learned_weights")
    op.drop_table("st_learned_weights")
