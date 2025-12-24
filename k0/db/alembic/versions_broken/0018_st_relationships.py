"""Create st_relationships table (Entity Relationships).

Revision ID: 0018
Revises: 0017
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.5 - Issue 2.1.5.3)

The st_relationships table stores typed relationships between people.
Supports bi-directional relationship types (parent/child, etc).

Columns: 9
Indexes: 4
Foreign Keys: 3 (source_person, target_person, household)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0018"
down_revision: str = "0017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_relationships table."""
    op.create_table(
        "st_relationships",
        # Composite primary key
        sa.Column("source_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Relationship details
        sa.Column("relationship_type", sa.String(32), nullable=False),
        sa.Column("inverse_type", sa.String(32), nullable=True),
        # Optional household context
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Metadata
        sa.Column("since_date", sa.Date, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # Composite primary key
        sa.PrimaryKeyConstraint("source_person_id", "target_person_id", name="pk_st_relationships"),
        # Foreign key constraints
        sa.ForeignKeyConstraint(
            ["source_person_id"],
            ["people.person_id"],
            name="fk_rel_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_person_id"],
            ["people.person_id"],
            name="fk_rel_target",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.household_id"],
            name="fk_rel_household",
            ondelete="SET NULL",
        ),
    )

    # Create indexes for relationship queries
    op.create_index("ix_st_relationships_source", "st_relationships", ["source_person_id"])
    op.create_index("ix_st_relationships_target", "st_relationships", ["target_person_id"])
    op.create_index("ix_st_relationships_type", "st_relationships", ["relationship_type"])
    op.create_index("ix_st_relationships_household", "st_relationships", ["household_id"])


def downgrade() -> None:
    """Drop st_relationships table and all indexes."""
    op.drop_index("ix_st_relationships_household", table_name="st_relationships")
    op.drop_index("ix_st_relationships_type", table_name="st_relationships")
    op.drop_index("ix_st_relationships_target", table_name="st_relationships")
    op.drop_index("ix_st_relationships_source", table_name="st_relationships")
    op.drop_table("st_relationships")
