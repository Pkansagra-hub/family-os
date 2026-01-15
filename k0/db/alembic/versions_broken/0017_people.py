"""Create people table (Domain Entity).

Revision ID: 0017
Revises: 0016
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.5 - Issue 2.1.5.2)

The people table stores person entities within households.
Contains profile, consent, device, and CRDT sync fields.

Columns: 33
Indexes: 7
Foreign Keys: 1 (household_id -> households.household_id)

Also adds deferred foreign key: households.primary_contact_person_id -> people.person_id
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0017"
down_revision: str = "0016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create people table and add household FK."""
    op.create_table(
        "people",
        # Primary key - UUID
        sa.Column("person_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Cognitive trace for AI correlation
        sa.Column("cognitive_trace_id", sa.String(128), nullable=True),
        # Display info
        sa.Column("label", sa.String(256), nullable=True),
        sa.Column("full_name", sa.String(256), nullable=True),
        sa.Column("nicknames", postgresql.JSONB, nullable=True),
        sa.Column("birth_date", sa.Date, nullable=True),
        # Relationships (JSONB for quick access)
        sa.Column("relationships", postgresql.JSONB, nullable=True),
        # Household association
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("household_role", sa.String(32), nullable=True),
        # Privacy defaults
        sa.Column("visibility_default", sa.String(16), nullable=True),
        sa.Column("band_default", sa.String(16), nullable=True),
        # Consent tracking
        sa.Column("consent_status", sa.String(16), nullable=True),
        # Merge tracking for deduplication
        sa.Column("merge_keys", postgresql.JSONB, nullable=True),
        sa.Column("canonical_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("merged_from", postgresql.JSONB, nullable=True),
        # Device associations
        sa.Column("primary_device_id", sa.String(64), nullable=True),
        sa.Column("registered_devices", postgresql.JSONB, nullable=True),
        # Preferences
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("contact_preferences", postgresql.JSONB, nullable=True),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("space_id", sa.String(64), nullable=True),
        # Privacy
        sa.Column("privacy_band", sa.String(16), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visible_to", postgresql.JSONB, nullable=True),
        # CRDT sync fields
        sa.Column("crdt_vector_clock", postgresql.JSONB, nullable=True),
        sa.Column("crdt_tombstone", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("crdt_lamport", sa.BigInteger, nullable=False, server_default="0"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        # Foreign key constraint
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.household_id"],
            name="fk_people_household",
            ondelete="SET NULL",
        ),
    )

    # Create indexes for people queries
    op.create_index("ix_people_household", "people", ["household_id"])
    op.create_index("ix_people_tenant", "people", ["tenant_id"])
    op.create_index("ix_people_label", "people", ["label"])
    op.create_index("ix_people_full_name", "people", ["full_name"])
    op.create_index("ix_people_created", "people", ["created_at"])
    op.create_index("ix_people_updated", "people", ["updated_at"])
    op.create_index(
        "ix_people_tombstone",
        "people",
        ["crdt_tombstone"],
        postgresql_where=sa.text("crdt_tombstone = true"),
    )

    # Add deferred foreign key from households to people
    # This allows circular reference between households and people
    op.create_foreign_key(
        "fk_hh_primary_contact",
        "households",
        "people",
        ["primary_contact_person_id"],
        ["person_id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    """Drop people table and all indexes, remove household FK."""
    # Remove the deferred foreign key first
    op.drop_constraint("fk_hh_primary_contact", "households", type_="foreignkey")
    # Drop indexes
    op.drop_index("ix_people_tombstone", table_name="people")
    op.drop_index("ix_people_updated", table_name="people")
    op.drop_index("ix_people_created", table_name="people")
    op.drop_index("ix_people_full_name", table_name="people")
    op.drop_index("ix_people_label", table_name="people")
    op.drop_index("ix_people_tenant", table_name="people")
    op.drop_index("ix_people_household", table_name="people")
    op.drop_table("people")
