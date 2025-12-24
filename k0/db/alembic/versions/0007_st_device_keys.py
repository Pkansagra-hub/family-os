"""Create st_device_keys table (Device Key Management).

Revision ID: 0007
Revises: 0006
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_device_keys (
  device_id TEXT NOT NULL,
  key_version TEXT NOT NULL,
  verify_key TEXT NOT NULL,
  key_state TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK(key_state IN ('PENDING','ACTIVE','ROTATING','REVOKED')),
  registered_ts TEXT NOT NULL,
  activated_ts TEXT,
  rotated_ts TEXT,
  revoked_ts TEXT,
  grace_expires_ts TEXT,
  revocation_reason TEXT,
  PRIMARY KEY(device_id, key_version),
  FOREIGN KEY(device_id) REFERENCES st_devices(device_id)
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0007"
down_revision: str = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_device_keys table matching SQLite schema."""
    op.create_table(
        "st_device_keys",
        # Composite primary key: device_id + key_version (both TEXT)
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("key_version", sa.Text, nullable=False),
        # Public verification key
        sa.Column("verify_key", sa.Text, nullable=False),
        # Key state machine with CHECK constraint
        sa.Column(
            "key_state",
            sa.Text,
            nullable=False,
            server_default="ACTIVE",
        ),
        # Lifecycle timestamps as TEXT
        sa.Column("registered_ts", sa.Text, nullable=False),
        sa.Column("activated_ts", sa.Text, nullable=True),
        sa.Column("rotated_ts", sa.Text, nullable=True),
        sa.Column("revoked_ts", sa.Text, nullable=True),
        sa.Column("grace_expires_ts", sa.Text, nullable=True),
        # Revocation reason
        sa.Column("revocation_reason", sa.Text, nullable=True),
        # Define composite primary key
        sa.PrimaryKeyConstraint("device_id", "key_version", name="pk_st_device_keys"),
        # Foreign key constraint
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["st_devices.device_id"],
            name="fk_device_keys_device",
            ondelete="CASCADE",
        ),
        # CHECK constraint
        sa.CheckConstraint(
            "key_state IN ('PENDING', 'ACTIVE', 'ROTATING', 'REVOKED')",
            name="ck_device_keys_state",
        ),
    )

    # Create index matching SQLite
    op.create_index("idx_device_keys_state", "st_device_keys", ["device_id", "key_state"])


def downgrade() -> None:
    """Drop st_device_keys table and all indexes."""
    op.drop_index("idx_device_keys_state", table_name="st_device_keys")
    op.drop_table("st_device_keys")
