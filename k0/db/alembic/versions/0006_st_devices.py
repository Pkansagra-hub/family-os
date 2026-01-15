"""Create st_devices table (Device Registry).

Revision ID: 0006
Revises: 0005
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_devices (
  device_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  mls_group_id TEXT NOT NULL,
  provisioned_ts TEXT NOT NULL,
  hmac_secret BLOB
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0006"
down_revision: str = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_devices table matching SQLite schema."""
    op.create_table(
        "st_devices",
        # Primary key - device ID string
        sa.Column("device_id", sa.Text, primary_key=True),
        # Tenant/space association - NOT NULL per SQLite
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # MLS group membership - NOT NULL per SQLite
        sa.Column("mls_group_id", sa.Text, nullable=False),
        # Provisioning timestamp as TEXT
        sa.Column("provisioned_ts", sa.Text, nullable=False),
        # HMAC secret for signing - nullable per SQLite
        sa.Column("hmac_secret", sa.LargeBinary, nullable=True),
    )

    # Create index matching SQLite
    op.create_index(
        "idx_devices_hmac_secret",
        "st_devices",
        ["device_id"],
        postgresql_where=sa.text("hmac_secret IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_devices table and all indexes."""
    op.drop_index("idx_devices_hmac_secret", table_name="st_devices")
    op.drop_table("st_devices")
