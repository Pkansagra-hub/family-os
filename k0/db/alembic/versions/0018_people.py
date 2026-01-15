"""Create people table (Domain Entity).

Revision ID: 0018
Revises: 0017
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite has 33 columns for people table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0018"
down_revision: str = "0017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create people table matching SQLite schema."""
    op.create_table(
        "people",
        # IDENTITY
        sa.Column("person_id", sa.Text, primary_key=True),
        sa.Column("cognitive_trace_id", sa.Text, nullable=False),
        # PERSON INFO
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("full_name", sa.Text, nullable=True),
        sa.Column("nicknames", sa.Text, nullable=True),
        sa.Column("birth_date", sa.Text, nullable=True),
        # RELATIONSHIPS
        sa.Column("relationships", sa.Text, nullable=True),
        sa.Column("household_id", sa.Text, nullable=True),
        sa.Column("household_role", sa.Text, nullable=True),
        # SYSTEM DEFAULTS
        sa.Column("visibility_default", sa.Text, nullable=True, server_default="personal"),
        sa.Column("band_default", sa.Text, nullable=True, server_default="AMBER"),
        sa.Column("consent_status", sa.Text, nullable=True, server_default="pending"),
        # IDENTITY MERGING
        sa.Column("merge_keys", sa.Text, nullable=True),
        sa.Column("canonical_person_id", sa.Text, nullable=True),
        sa.Column("merged_from", sa.Text, nullable=True),
        # DEVICE ASSOCIATION
        sa.Column("primary_device_id", sa.Text, nullable=True),
        sa.Column("registered_devices", sa.Text, nullable=True),
        # PREFERENCES & SETTINGS
        sa.Column("timezone", sa.Text, nullable=True, server_default="UTC"),
        sa.Column("language", sa.Text, nullable=True, server_default="en"),
        sa.Column("contact_preferences", sa.Text, nullable=True),
        # ACCESS CONTROL
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("privacy_band", sa.Text, nullable=False, server_default="AMBER"),
        sa.Column("owner_id", sa.Text, nullable=False),
        sa.Column("visible_to", sa.Text, nullable=False),
        # SYNC (CRDT)
        sa.Column("crdt_vector_clock", sa.Text, nullable=False),
        sa.Column("crdt_tombstone", sa.Integer, nullable=True, server_default="0"),
        sa.Column("crdt_lamport", sa.BigInteger, nullable=False),
        # LIFECYCLE
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("onboarded_at", sa.Text, nullable=True),
        sa.Column("last_active_at", sa.Text, nullable=True),
        sa.Column("deactivated_at", sa.Text, nullable=True),
        # CHECK constraint
        sa.CheckConstraint(
            "privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')",
            name="ck_people_privacy_band",
        ),
    )

    # Add FK people.household_id -> households.household_id (nullable)
    op.create_foreign_key(
        "fk_people_household",
        "people",
        "households",
        ["household_id"],
        ["household_id"],
        ondelete="SET NULL",
    )

    # Add FK households.primary_contact_person_id -> people.person_id
    op.create_foreign_key(
        "fk_households_primary_contact",
        "households",
        "people",
        ["primary_contact_person_id"],
        ["person_id"],
        ondelete="SET NULL",
    )

    # Create indexes matching SQLite
    op.create_index("idx_people_tenant", "people", ["tenant_id"])
    op.create_index(
        "idx_people_household",
        "people",
        ["household_id"],
        postgresql_where=sa.text("household_id IS NOT NULL"),
    )
    op.create_index("idx_people_label", "people", ["label"])
    op.create_index(
        "idx_people_canonical",
        "people",
        ["canonical_person_id"],
        postgresql_where=sa.text("canonical_person_id IS NOT NULL"),
    )
    op.create_index("idx_people_privacy", "people", ["privacy_band"])
    op.create_index("idx_people_crdt_tombstone", "people", ["crdt_tombstone", "tenant_id"])
    op.create_index(
        "idx_people_last_active",
        "people",
        [sa.text("last_active_at DESC")],
    )


def downgrade() -> None:
    """Drop people table and all indexes."""
    op.drop_index("idx_people_last_active", table_name="people")
    op.drop_index("idx_people_crdt_tombstone", table_name="people")
    op.drop_index("idx_people_privacy", table_name="people")
    op.drop_index("idx_people_canonical", table_name="people")
    op.drop_index("idx_people_label", table_name="people")
    op.drop_index("idx_people_household", table_name="people")
    op.drop_index("idx_people_tenant", table_name="people")
    op.drop_foreign_key("fk_households_primary_contact", "households")
    op.drop_foreign_key("fk_people_household", "people")
    op.drop_table("people")
    op.drop_index("idx_people_email", table_name="people")
    op.drop_index("idx_people_role", table_name="people")
    op.drop_index("idx_people_display_name", table_name="people")
    op.drop_index("idx_people_tenant", table_name="people")
    op.drop_index("idx_people_household", table_name="people")
    op.drop_foreign_key("fk_households_primary_contact", "households")
    op.drop_foreign_key("fk_people_household", "people")
    op.drop_table("people")
