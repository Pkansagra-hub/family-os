"""Create st_devices table (Device Registry).

Revision ID: 0014
Revises: 0013
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.4 - Issue 2.1.4.1)

The st_devices table stores registered device information.
Each device has an HMAC secret for envelope signing.

Columns: 6
Indexes: 2
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0014"
down_revision: str = "0013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_devices table."""
    op.create_table(
        "st_devices",
        # Primary key - device ID string
        sa.Column("device_id", sa.String(64), primary_key=True),
        # Tenant/space association
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        # MLS group membership
        sa.Column("mls_group_id", sa.String(64), nullable=True),
        # Provisioning timestamp
        sa.Column(
            "provisioned_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # HMAC secret for signing (encrypted at rest)
        sa.Column("hmac_secret", sa.LargeBinary, nullable=False),
    )

    # Create indexes for device lookups
    op.create_index("ix_st_devices_tenant", "st_devices", ["tenant_id"])
    op.create_index("ix_st_devices_tenant_space", "st_devices", ["tenant_id", "space_id"])


def downgrade() -> None:
    """Drop st_devices table and all indexes."""
    op.drop_index("ix_st_devices_tenant_space", table_name="st_devices")
    op.drop_index("ix_st_devices_tenant", table_name="st_devices")
    op.drop_table("st_devices")
