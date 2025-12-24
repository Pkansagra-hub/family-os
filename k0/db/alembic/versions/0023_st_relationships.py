"""Create st_relationships table.

Revision ID: 0023
Revises: 0022
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

CRITICAL: This was completely WRONG before!
Old schema had: source_person_id, target_person_id as composite PK
SQLite has: id INTEGER PRIMARY KEY AUTOINCREMENT, person_id, related_person_id
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0023"
down_revision: str = "0022"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_relationships table matching SQLite schema.

    SQLite schema:
    CREATE TABLE st_relationships (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      household_id TEXT NOT NULL,
      person_id TEXT NOT NULL,
      related_person_id TEXT NOT NULL,
      relationship_type TEXT NOT NULL CHECK(...),
      properties_json TEXT,
      source_version TEXT NOT NULL,
      hydrated_at TEXT NOT NULL,
      ttl_seconds INTEGER NOT NULL,
      FOREIGN KEY (household_id) REFERENCES households(household_id),
      FOREIGN KEY (person_id) REFERENCES people(person_id),
      FOREIGN KEY (related_person_id) REFERENCES people(person_id)
    );
    """
    op.create_table(
        "st_relationships",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("household_id", sa.Text, nullable=False),
        sa.Column("person_id", sa.Text, nullable=False),
        sa.Column("related_person_id", sa.Text, nullable=False),
        sa.Column("relationship_type", sa.Text, nullable=False),
        sa.Column("properties_json", sa.Text, nullable=True),
        sa.Column("source_version", sa.Text, nullable=False),
        sa.Column("hydrated_at", sa.Text, nullable=False),
        sa.Column("ttl_seconds", sa.Integer, nullable=False),
        sa.CheckConstraint(
            "relationship_type IN ('SPOUSE_OF', 'PARENT_OF', 'CHILD_OF', 'CARETAKER_OF', 'SIBLING_OF')",
            name="ck_relationships_type",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.household_id"],
            name="fk_relationships_household",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.person_id"],
            name="fk_relationships_person",
        ),
        sa.ForeignKeyConstraint(
            ["related_person_id"],
            ["people.person_id"],
            name="fk_relationships_related_person",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_relationships_household", "st_relationships", ["household_id"])
    op.create_index("idx_relationships_person", "st_relationships", ["person_id"])
    op.create_index("idx_relationships_type", "st_relationships", ["relationship_type"])
    op.create_index(
        "idx_relationships_person_type",
        "st_relationships",
        ["person_id", "relationship_type"],
    )


def downgrade() -> None:
    """Drop st_relationships table."""
    op.drop_index("idx_relationships_person_type", table_name="st_relationships")
    op.drop_index("idx_relationships_type", table_name="st_relationships")
    op.drop_index("idx_relationships_person", table_name="st_relationships")
    op.drop_index("idx_relationships_household", table_name="st_relationships")
    op.drop_table("st_relationships")
