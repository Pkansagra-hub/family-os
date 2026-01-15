"""Create st_dlq table (Dead Letter Queue).

Revision ID: 0009
Revises: 0008
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_dlq (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  payload BLOB NOT NULL,
  reason TEXT NOT NULL,
  retries INTEGER NOT NULL DEFAULT 0,
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  first_failure_ts TEXT NOT NULL,
  last_failure_ts TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING'
    CHECK(state IN ('PENDING','REQUEUED','QUARANTINED')),
  next_attempt_ts TEXT,
  backoff_exp INTEGER DEFAULT 1,
  error_kind TEXT,
  error_fingerprint TEXT
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0009"
down_revision: str = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_dlq table matching SQLite schema."""
    op.create_table(
        "st_dlq",
        # Primary key
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Reference to WAL entry - nullable per SQLite
        sa.Column("wal_pos", sa.BigInteger, nullable=True),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # Driver targeting
        sa.Column("driver", sa.Text, nullable=False),
        sa.Column("op_kind", sa.Text, nullable=False),
        # Content
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("payload", sa.LargeBinary, nullable=False),
        # Error info - reason is NOT NULL per SQLite
        sa.Column("reason", sa.Text, nullable=False),
        # Retry tracking
        sa.Column("retries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("requeue_seq", sa.Integer, nullable=False, server_default="0"),
        # Timestamps as TEXT
        sa.Column("first_failure_ts", sa.Text, nullable=False),
        sa.Column("last_failure_ts", sa.Text, nullable=False),
        # State machine - DEFAULT 'PENDING' per SQLite
        sa.Column("state", sa.Text, nullable=False, server_default="PENDING"),
        sa.Column("next_attempt_ts", sa.Text, nullable=True),
        sa.Column("backoff_exp", sa.Integer, nullable=True, server_default="1"),
        sa.Column("error_kind", sa.Text, nullable=True),
        sa.Column("error_fingerprint", sa.Text, nullable=True),
        # CHECK constraint
        sa.CheckConstraint(
            "state IN ('PENDING', 'REQUEUED', 'QUARANTINED')",
            name="ck_dlq_state",
        ),
    )

    # Create indexes matching SQLite
    op.create_index("idx_dlq_space", "st_dlq", ["space_id", "first_failure_ts"])
    op.create_index("idx_dlq_next_attempt", "st_dlq", ["next_attempt_ts", "state"])
    op.create_index(
        "idx_dlq_error_fingerprint",
        "st_dlq",
        ["error_fingerprint"],
        postgresql_where=sa.text("error_fingerprint IS NOT NULL"),
    )
    op.create_index(
        "idx_dlq_error_kind",
        "st_dlq",
        ["error_kind"],
        postgresql_where=sa.text("error_kind IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_dlq table and all indexes."""
    op.drop_index("idx_dlq_error_kind", table_name="st_dlq")
    op.drop_index("idx_dlq_error_fingerprint", table_name="st_dlq")
    op.drop_index("idx_dlq_next_attempt", table_name="st_dlq")
    op.drop_index("idx_dlq_space", table_name="st_dlq")
    op.drop_table("st_dlq")
