"""Create st_learned_weights_history table (Parameter versioning).

Revision ID: 0041
Revises: 0040
Create Date: 2025-01-01

Version history for learned parameters.
Enables rollback and tracks parameter evolution over time.
Retention: Keep last 10 versions per parameter (via trigger).

Spec Reference: Dossier §6.23 st_learned_weights_history

Schema Features:
- 10 columns matching dossier specification
- FK to st_learned_weights(param_id)
- UNIQUE constraint on (param_id, version)
- 3 indexes for version and time-based queries
- RLS policy for multi-tenant isolation
- Pruning trigger to keep only last 10 versions per param_id
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0041"
down_revision: str = "0040"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_learned_weights_history table with all columns and indexes."""
    op.create_table(
        "st_learned_weights_history",
        # Primary key - ULID for history entry
        sa.Column(
            "history_id",
            sa.Text,
            primary_key=True,
            comment="ULID for history entry",
        ),
        # Reference to st_learned_weights
        sa.Column(
            "param_id",
            sa.Text,
            nullable=False,
            comment="Reference to st_learned_weights",
        ),
        # Space isolation (denormalized for RLS)
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="Isolation (denormalized for RLS)",
        ),
        # Version number at time of snapshot
        sa.Column(
            "version",
            sa.Integer,
            nullable=False,
            comment="Version number at time of snapshot",
        ),
        # Parameter value at this version
        sa.Column(
            "value",
            sa.Float,
            nullable=False,
            comment="Parameter value at this version",
        ),
        # Confidence at this version
        sa.Column(
            "confidence",
            sa.Float,
            nullable=False,
            comment="Confidence at this version",
        ),
        # Sample count at this version
        sa.Column(
            "sample_count",
            sa.Integer,
            nullable=False,
            comment="Sample count at this version",
        ),
        # Quality metric when updated
        sa.Column(
            "quality_metric",
            sa.Float,
            nullable=True,
            comment="Quality metric when updated",
        ),
        # When this version was created
        sa.Column(
            "created_at",
            sa.BigInteger,
            nullable=False,
            comment="When this version was created (Unix ms)",
        ),
        # Why parameter was updated
        sa.Column(
            "reason",
            sa.Text,
            nullable=True,
            comment="Why parameter was updated",
        ),
        # Foreign key to st_learned_weights
        sa.ForeignKeyConstraint(
            ["param_id"],
            ["st_learned_weights.param_id"],
            name="fk_weights_history_param",
            ondelete="CASCADE",
        ),
        # UNIQUE constraint on (param_id, version)
        sa.UniqueConstraint(
            "param_id",
            "version",
            name="uq_weights_history_version",
        ),
    )

    # Index 1: Latest version lookup
    op.create_index(
        "idx_weights_history_param_version",
        "st_learned_weights_history",
        ["param_id", sa.text("version DESC")],
    )

    # Index 2: Time-based rollback
    op.create_index(
        "idx_weights_history_param_time",
        "st_learned_weights_history",
        ["param_id", sa.text("created_at DESC")],
    )

    # Index 3: Space-level analysis
    op.create_index(
        "idx_weights_history_space",
        "st_learned_weights_history",
        ["space_id", sa.text("created_at DESC")],
    )

    # RLS for multi-tenant isolation
    op.execute("ALTER TABLE st_learned_weights_history ENABLE ROW LEVEL SECURITY;")

    op.execute(
        """
        CREATE POLICY weights_history_isolation ON st_learned_weights_history
            FOR ALL USING (space_id = current_setting('app.current_space_id', true)::text)
        """
    )

    # Version pruning trigger - keep only last 10 versions per param_id
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prune_weights_history()
        RETURNS TRIGGER AS $$
        BEGIN
            DELETE FROM st_learned_weights_history
            WHERE history_id IN (
                SELECT history_id FROM st_learned_weights_history
                WHERE param_id = NEW.param_id
                ORDER BY version DESC
                OFFSET 10
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_prune_weights_history
        AFTER INSERT ON st_learned_weights_history
        FOR EACH ROW EXECUTE FUNCTION prune_weights_history();
        """
    )


def downgrade() -> None:
    """Drop st_learned_weights_history table and all indexes."""
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trg_prune_weights_history ON st_learned_weights_history;")
    op.execute("DROP FUNCTION IF EXISTS prune_weights_history();")

    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS weights_history_isolation ON st_learned_weights_history;")
    op.execute("ALTER TABLE st_learned_weights_history DISABLE ROW LEVEL SECURITY;")

    op.drop_index("idx_weights_history_space", table_name="st_learned_weights_history")
    op.drop_index("idx_weights_history_param_time", table_name="st_learned_weights_history")
    op.drop_index("idx_weights_history_param_version", table_name="st_learned_weights_history")
    op.drop_table("st_learned_weights_history")
