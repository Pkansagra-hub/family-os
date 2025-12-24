"""Create st_device_keys table (Device Key Management).

Revision ID: 0015
Revises: 0014
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.4 - Issue 2.1.4.2)

The st_device_keys table tracks signing keys per device.
Supports key rotation with version tracking and grace periods.

Columns: 10
Indexes: 2
Foreign Keys: 1 (device_id -> st_devices.device_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0015"
down_revision: str = "0014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_device_keys table with composite primary key and foreign key."""
    op.create_table(
        "st_device_keys",
        # Composite primary key: device_id + key_version
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("key_version", sa.Integer, nullable=False),
        # Public verification key
        sa.Column("verify_key", sa.Text, nullable=False),
        # Key state machine
        sa.Column("key_state", sa.String(16), nullable=False, server_default="active"),
        # Lifecycle timestamps
        sa.Column(
            "registered_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("activated_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_expires_ts", sa.DateTime(timezone=True), nullable=True),
        # Revocation reason
        sa.Column("revocation_reason", sa.Text, nullable=True),
        # Define composite primary key
        sa.PrimaryKeyConstraint("device_id", "key_version", name="pk_st_device_keys"),
        # Foreign key constraint with CASCADE delete
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["st_devices.device_id"],
            name="fk_device_keys_device",
            ondelete="CASCADE",
        ),
    )

    # Create indexes for key state queries
    op.create_index("ix_st_device_keys_state", "st_device_keys", ["key_state"])
    op.create_index(
        "ix_st_device_keys_revoked",
        "st_device_keys",
        ["revoked_ts"],
        postgresql_where=sa.text("revoked_ts IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_device_keys table and all indexes."""
    op.drop_index("ix_st_device_keys_revoked", table_name="st_device_keys")
    op.drop_index("ix_st_device_keys_state", table_name="st_device_keys")
    op.drop_table("st_device_keys")
