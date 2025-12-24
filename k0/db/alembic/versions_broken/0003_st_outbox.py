"""Create st_outbox table (Outbox Pattern).

Revision ID: 0003
Revises: 0002
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.1 - Issue 2.1.1.2)

The st_outbox table implements the transactional outbox pattern.
Pending driver operations are queued here for reliable delivery.

Columns: 14
Indexes: 3
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0003"
down_revision: str = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_outbox table with all columns and indexes."""
    op.create_table(
        "st_outbox",
        # Primary key
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Reference to WAL entry
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        # Driver targeting
        sa.Column("driver", sa.String(64), nullable=False),
        sa.Column("op_kind", sa.String(32), nullable=False),
        # Payload
        sa.Column("payload", sa.LargeBinary, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        # Retry tracking
        sa.Column("requeue_seq", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retries", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("next_attempt_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backoff_exp", sa.SmallInteger, nullable=False, server_default="0"),
        # Status
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    )

    # Create indexes for polling and driver targeting
    op.create_index("ix_st_outbox_status_next", "st_outbox", ["status", "next_attempt_ts"])
    op.create_index("ix_st_outbox_driver", "st_outbox", ["driver"])
    op.create_index("ix_st_outbox_wal_pos", "st_outbox", ["wal_pos"])


def downgrade() -> None:
    """Drop st_outbox table and all indexes."""
    op.drop_index("ix_st_outbox_wal_pos", table_name="st_outbox")
    op.drop_index("ix_st_outbox_driver", table_name="st_outbox")
    op.drop_index("ix_st_outbox_status_next", table_name="st_outbox")
    op.drop_table("st_outbox")
