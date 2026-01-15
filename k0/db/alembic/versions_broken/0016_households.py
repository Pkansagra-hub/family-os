"""Create households table (Domain Entity).

Revision ID: 0016
Revises: 0015
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.5 - Issue 2.1.5.1)

The households table stores household entities - the primary
organizational unit in FamilyOS. Contains subscription, storage,
and CRDT sync fields.

Columns: 35
Indexes: 8
Foreign Keys: 1 (tenant_id -> st_devices.tenant_id) - deferred

Note: primary_contact_person_id FK is added in 0017 after people table exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0016"
down_revision: str = "0015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create households table."""
    op.create_table(
        "households",
        # Primary key - UUID
        sa.Column("household_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Cognitive trace for AI correlation
        sa.Column("cognitive_trace_id", sa.String(128), nullable=True),
        # Display info
        sa.Column("label", sa.String(256), nullable=True),
        sa.Column("household_type", sa.String(32), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        # Member counts
        sa.Column("member_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("adult_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("child_count", sa.Integer, nullable=False, server_default="0"),
        # Primary contact (FK added after people table exists)
        sa.Column("primary_contact_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Policy & Settings (JSONB)
        sa.Column("policy_profile", postgresql.JSONB, nullable=True),
        sa.Column("retention_defaults", postgresql.JSONB, nullable=True),
        sa.Column("privacy_defaults", postgresql.JSONB, nullable=True),
        sa.Column("rate_limits", postgresql.JSONB, nullable=True),
        # Storage quotas
        sa.Column("storage_quota_gb", sa.Float, nullable=True),
        sa.Column("storage_used_gb", sa.Float, nullable=False, server_default="0"),
        # Subscription
        sa.Column("subscription_tier", sa.String(32), nullable=True),
        sa.Column("subscription_status", sa.String(16), nullable=True),
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_email", sa.String(256), nullable=True),
        # Features (JSONB)
        sa.Column("features_enabled", postgresql.JSONB, nullable=True),
        sa.Column("experimental_features", postgresql.JSONB, nullable=True),
        # Connected services
        sa.Column("connected_services", postgresql.JSONB, nullable=True),
        sa.Column("connector_count", sa.Integer, nullable=False, server_default="0"),
        # Tenant link (unique per household)
        sa.Column("tenant_id", sa.String(64), nullable=True, unique=True),
        # Privacy
        sa.Column("privacy_band", sa.String(16), nullable=True),
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
    )

    # Create indexes for household queries
    op.create_index("ix_households_tenant_id", "households", ["tenant_id"], unique=True)
    op.create_index("ix_households_label", "households", ["label"])
    op.create_index("ix_households_type", "households", ["household_type"])
    op.create_index("ix_households_subscription", "households", ["subscription_status"])
    op.create_index("ix_households_created", "households", ["created_at"])
    op.create_index("ix_households_updated", "households", ["updated_at"])
    op.create_index("ix_households_active", "households", ["last_active_at"])
    op.create_index(
        "ix_households_tombstone",
        "households",
        ["crdt_tombstone"],
        postgresql_where=sa.text("crdt_tombstone = true"),
    )


def downgrade() -> None:
    """Drop households table and all indexes."""
    op.drop_index("ix_households_tombstone", table_name="households")
    op.drop_index("ix_households_active", table_name="households")
    op.drop_index("ix_households_updated", table_name="households")
    op.drop_index("ix_households_created", table_name="households")
    op.drop_index("ix_households_subscription", table_name="households")
    op.drop_index("ix_households_type", table_name="households")
    op.drop_index("ix_households_label", table_name="households")
    op.drop_index("ix_households_tenant_id", table_name="households")
    op.drop_table("households")
