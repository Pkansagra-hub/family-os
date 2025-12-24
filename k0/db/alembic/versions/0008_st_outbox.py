"""Create st_outbox table (Outbox Pattern).

Revision ID: 0008
Revises: 0007
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
  payload BLOB NOT NULL,
  fingerprint TEXT NOT NULL,
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  retries INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  next_attempt_ts TEXT,
  backoff_exp INTEGER DEFAULT 1,
  status TEXT DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'PROCESSING', 'FAILED', 'DEAD'))
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0008"
down_revision: str = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_outbox table matching SQLite schema."""
    op.create_table(
        "st_outbox",
        # Primary key - auto-increment
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Reference to WAL entry
        sa.Column("wal_pos", sa.BigInteger, nullable=False),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # Driver targeting
        sa.Column("driver", sa.Text, nullable=False),
        sa.Column("op_kind", sa.Text, nullable=False),
        # Payload
        sa.Column("payload", sa.LargeBinary, nullable=False),
        sa.Column("fingerprint", sa.Text, nullable=False),
        # Retry tracking
        sa.Column("requeue_seq", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("next_attempt_ts", sa.Text, nullable=True),
        sa.Column("backoff_exp", sa.Integer, nullable=True, server_default="1"),
        # Status with CHECK constraint
        sa.Column("status", sa.Text, nullable=True, server_default="PENDING"),
        # CHECK constraint
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'FAILED', 'DEAD')",
            name="ck_outbox_status",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_outbox_space", "st_outbox", ["space_id", "requeue_seq", "id"])
    op.create_index(
        "uq_outbox_idem",
        "st_outbox",
        ["tenant_id", "space_id", "driver", "fingerprint", "requeue_seq"],
        unique=True,
    )
    op.create_index("idx_outbox_next_attempt", "st_outbox", ["next_attempt_ts", "status"])


def downgrade() -> None:
    """Drop st_outbox table and all indexes."""
    op.drop_index("idx_outbox_next_attempt", table_name="st_outbox")
    op.drop_index("uq_outbox_idem", table_name="st_outbox")
    op.drop_index("idx_outbox_space", table_name="st_outbox")
    op.drop_table("st_outbox")
