"""Create households table (Domain Entity).

Revision ID: 0017
Revises: 0016
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite has 35 columns for households table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0017"
down_revision: str = "0016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create households table matching SQLite schema."""
    op.create_table(
        "households",
        # IDENTITY - TEXT PRIMARY KEY per SQLite
        sa.Column("household_id", sa.Text, primary_key=True),
        sa.Column("cognitive_trace_id", sa.Text, nullable=False),
        # HOUSEHOLD INFO
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("household_type", sa.Text, nullable=True, server_default="family"),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("timezone", sa.Text, nullable=True, server_default="UTC"),
        # MEMBERS
        sa.Column("member_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("adult_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("child_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("primary_contact_person_id", sa.Text, nullable=True),
        # POLICY CONFIGURATION
        sa.Column("policy_profile", sa.Text, nullable=True, server_default="balanced"),
        sa.Column("retention_defaults", sa.Text, nullable=True),
        sa.Column("privacy_defaults", sa.Text, nullable=True),
        # RATE LIMITS & QUOTAS
        sa.Column("rate_limits", sa.Text, nullable=True),
        sa.Column("storage_quota_gb", sa.Integer, nullable=True, server_default="100"),
        sa.Column("storage_used_gb", sa.Float, nullable=True, server_default="0.0"),
        # SUBSCRIPTION & BILLING
        sa.Column("subscription_tier", sa.Text, nullable=True, server_default="free"),
        sa.Column("subscription_status", sa.Text, nullable=True, server_default="active"),
        sa.Column("subscription_expires_at", sa.Text, nullable=True),
        sa.Column("billing_email", sa.Text, nullable=True),
        # FEATURE FLAGS
        sa.Column("features_enabled", sa.Text, nullable=True),
        sa.Column("experimental_features", sa.Text, nullable=True),
        # EXTERNAL INTEGRATIONS
        sa.Column("connected_services", sa.Text, nullable=True),
        sa.Column("connector_count", sa.Integer, nullable=True, server_default="0"),
        # ACCESS CONTROL - tenant_id and visible_to are NOT NULL per SQLite
        sa.Column("tenant_id", sa.Text, nullable=False, unique=True),
        sa.Column("privacy_band", sa.Text, nullable=False, server_default="AMBER"),
        sa.Column("visible_to", sa.Text, nullable=False),
        # SYNC (CRDT) - vector_clock and lamport are NOT NULL per SQLite
        sa.Column("crdt_vector_clock", sa.Text, nullable=False),
        sa.Column("crdt_tombstone", sa.Integer, nullable=True, server_default="0"),
        sa.Column("crdt_lamport", sa.BigInteger, nullable=False),
        # LIFECYCLE - created_at and updated_at are NOT NULL per SQLite
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("onboarded_at", sa.Text, nullable=True),
        sa.Column("last_active_at", sa.Text, nullable=True),
        sa.Column("deactivated_at", sa.Text, nullable=True),
        # CHECK constraint
        sa.CheckConstraint(
            "privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')",
            name="ck_households_privacy_band",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_households_tenant", "households", ["tenant_id"])
    op.create_index("idx_households_label", "households", ["label"])
    op.create_index(
        "idx_households_subscription",
        "households",
        ["subscription_tier", "subscription_status"],
    )
    op.create_index(
        "idx_households_primary_contact",
        "households",
        ["primary_contact_person_id"],
        postgresql_where=sa.text("primary_contact_person_id IS NOT NULL"),
    )
    op.create_index("idx_households_crdt_tombstone", "households", ["crdt_tombstone", "tenant_id"])
    op.create_index("idx_households_last_active", "households", ["last_active_at"])


def downgrade() -> None:
    """Drop households table and all indexes."""
    op.drop_index("idx_households_last_active", table_name="households")
    op.drop_index("idx_households_crdt_tombstone", table_name="households")
    op.drop_index("idx_households_primary_contact", table_name="households")
    op.drop_index("idx_households_subscription", table_name="households")
    op.drop_index("idx_households_label", table_name="households")
    op.drop_index("idx_households_tenant", table_name="households")
    op.drop_table("households")
