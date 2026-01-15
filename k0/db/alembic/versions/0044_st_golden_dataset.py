"""Create st_golden_dataset_pairs and st_validation_results tables.

Revision ID: 0044
Revises: 0043
Create Date: 2025-01-01

Golden dataset storage for drift detection and validation.
- st_golden_dataset_pairs: Ground truth input/output pairs
- st_validation_results: Validation run results against golden pairs

Spec Reference: Dossier §6.24-6.25

Schema Features:
- st_golden_dataset_pairs: 12 columns
- st_validation_results: 12 columns with FK to pairs
- Indexes for efficient lookup
- RLS for multi-tenant isolation
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0044"
down_revision: str = "0043"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Valid difficulty levels
DIFFICULTY_LEVELS = (
    "EASY",
    "MEDIUM",
    "HARD",
)


def upgrade() -> None:
    """Create st_golden_dataset_pairs and st_validation_results tables."""
    # =========================================================================
    # st_golden_dataset_pairs - Ground truth input/output pairs
    # =========================================================================
    op.create_table(
        "st_golden_dataset_pairs",
        # Primary key - ULID
        sa.Column(
            "pair_id",
            sa.Text,
            primary_key=True,
            comment="ULID for pair",
        ),
        # Space isolation
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="User/family space",
        ),
        # Entity classification
        sa.Column(
            "entity_type",
            sa.Text,
            nullable=False,
            comment="Type of entity being tested",
        ),
        # Input/output data
        sa.Column(
            "input_json",
            sa.Text,  # JSONB in PostgreSQL
            nullable=False,
            comment="Input data for validation",
        ),
        sa.Column(
            "expected_output_json",
            sa.Text,  # JSONB in PostgreSQL
            nullable=False,
            comment="Expected ground truth output",
        ),
        sa.Column(
            "ground_truth_source",
            sa.Text,
            nullable=False,
            comment="Where ground truth came from",
        ),
        # Status
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="true",
            comment="Is this pair active?",
        ),
        # Difficulty classification
        sa.Column(
            "difficulty",
            sa.Text,
            nullable=True,
            comment="EASY, MEDIUM, HARD",
        ),
        # Tags for filtering
        sa.Column(
            "tags_json",
            sa.Text,  # JSONB in PostgreSQL
            nullable=True,
            comment="Tags for filtering",
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
        sa.Column(
            "created_by",
            sa.Text,
            nullable=False,
            comment="Who created this pair",
        ),
    )

    # Indexes for st_golden_dataset_pairs
    op.create_index(
        "idx_golden_pairs_space_type",
        "st_golden_dataset_pairs",
        ["space_id", "entity_type"],
    )

    op.create_index(
        "idx_golden_pairs_active",
        "st_golden_dataset_pairs",
        ["space_id", "is_active"],
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_index(
        "idx_golden_pairs_difficulty",
        "st_golden_dataset_pairs",
        ["difficulty"],
        postgresql_where=sa.text("difficulty IS NOT NULL"),
    )

    # RLS for st_golden_dataset_pairs
    op.execute("ALTER TABLE st_golden_dataset_pairs ENABLE ROW LEVEL SECURITY;")

    op.execute(
        """
        CREATE POLICY golden_pairs_isolation ON st_golden_dataset_pairs
            FOR ALL USING (space_id = current_setting('app.current_space_id', true)::text)
        """
    )

    # =========================================================================
    # st_validation_results - Validation run results
    # =========================================================================
    op.create_table(
        "st_validation_results",
        # Primary key - ULID
        sa.Column(
            "result_id",
            sa.Text,
            primary_key=True,
            comment="ULID for result",
        ),
        # Space isolation
        sa.Column(
            "space_id",
            sa.Text,
            nullable=False,
            comment="User/family space",
        ),
        # Reference to golden pair
        sa.Column(
            "pair_id",
            sa.Text,
            nullable=False,
            comment="Reference to st_golden_dataset_pairs",
        ),
        # Validation output
        sa.Column(
            "actual_output_json",
            sa.Text,  # JSONB in PostgreSQL
            nullable=False,
            comment="Actual output from system",
        ),
        sa.Column(
            "is_correct",
            sa.Boolean,
            nullable=False,
            comment="Did output match expected?",
        ),
        sa.Column(
            "similarity_score",
            sa.Float,
            nullable=True,
            comment="Similarity to expected [0-1]",
        ),
        # Error tracking
        sa.Column(
            "error_type",
            sa.Text,
            nullable=True,
            comment="Type of error if incorrect",
        ),
        sa.Column(
            "error_details_json",
            sa.Text,  # JSONB in PostgreSQL
            nullable=True,
            comment="Error details",
        ),
        # Version tracking
        sa.Column(
            "model_version",
            sa.Text,
            nullable=False,
            comment="Model/algorithm version used",
        ),
        sa.Column(
            "param_snapshot_json",
            sa.Text,  # JSONB in PostgreSQL
            nullable=True,
            comment="Parameters at time of test",
        ),
        # Timing
        sa.Column(
            "created_at",
            sa.BigInteger,
            nullable=False,
            comment="When validation ran (Unix ms)",
        ),
        sa.Column(
            "duration_ms",
            sa.Integer,
            nullable=True,
            comment="How long validation took",
        ),
        # Foreign key to st_golden_dataset_pairs
        sa.ForeignKeyConstraint(
            ["pair_id"],
            ["st_golden_dataset_pairs.pair_id"],
            name="fk_validation_results_pair",
            ondelete="CASCADE",
        ),
    )

    # Indexes for st_validation_results
    op.create_index(
        "idx_validation_results_pair",
        "st_validation_results",
        ["pair_id", sa.text("created_at DESC")],
    )

    op.create_index(
        "idx_validation_results_space_time",
        "st_validation_results",
        ["space_id", sa.text("created_at DESC")],
    )

    op.create_index(
        "idx_validation_results_correct",
        "st_validation_results",
        ["space_id", "is_correct"],
        postgresql_where=sa.text("is_correct = FALSE"),
    )

    op.create_index(
        "idx_validation_results_version",
        "st_validation_results",
        ["model_version", "created_at"],
    )

    # RLS for st_validation_results
    op.execute("ALTER TABLE st_validation_results ENABLE ROW LEVEL SECURITY;")

    op.execute(
        """
        CREATE POLICY validation_results_isolation ON st_validation_results
            FOR ALL USING (space_id = current_setting('app.current_space_id', true)::text)
        """
    )


def downgrade() -> None:
    """Drop st_validation_results and st_golden_dataset_pairs tables."""
    # Drop st_validation_results first (has FK to st_golden_dataset_pairs)
    op.execute("DROP POLICY IF EXISTS validation_results_isolation ON st_validation_results;")
    op.execute("ALTER TABLE st_validation_results DISABLE ROW LEVEL SECURITY;")

    op.drop_index("idx_validation_results_version", table_name="st_validation_results")
    op.drop_index("idx_validation_results_correct", table_name="st_validation_results")
    op.drop_index("idx_validation_results_space_time", table_name="st_validation_results")
    op.drop_index("idx_validation_results_pair", table_name="st_validation_results")
    op.drop_table("st_validation_results")

    # Drop st_golden_dataset_pairs
    op.execute("DROP POLICY IF EXISTS golden_pairs_isolation ON st_golden_dataset_pairs;")
    op.execute("ALTER TABLE st_golden_dataset_pairs DISABLE ROW LEVEL SECURITY;")

    op.drop_index("idx_golden_pairs_difficulty", table_name="st_golden_dataset_pairs")
    op.drop_index("idx_golden_pairs_active", table_name="st_golden_dataset_pairs")
    op.drop_index("idx_golden_pairs_space_type", table_name="st_golden_dataset_pairs")
    op.drop_table("st_golden_dataset_pairs")
