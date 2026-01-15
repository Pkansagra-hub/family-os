"""Create st_dlq table (Dead Letter Queue).

Revision ID: 0004
Revises: 0003
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.1 - Issue 2.1.1.3)

The st_dlq table stores failed outbox operations for manual review.
Operations land here after exhausting retry attempts.

Columns: 18
Indexes: 4
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0004"
down_revision: str = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_dlq table with all columns and indexes."""
    op.create_table(
        "st_dlq",
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
        # Content
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column("payload", sa.LargeBinary, nullable=False),
        # Error info
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("error_kind", sa.String(64), nullable=True),
        sa.Column("error_fingerprint", sa.String(64), nullable=True),
        # Retry tracking
        sa.Column("retries", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("requeue_seq", sa.Integer, nullable=False, server_default="0"),
        # Timestamps
        sa.Column("first_failure_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failure_ts", sa.DateTime(timezone=True), nullable=False),
        # State machine
        sa.Column("state", sa.String(16), nullable=False, server_default="dead"),
        sa.Column("next_attempt_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backoff_exp", sa.SmallInteger, nullable=False, server_default="0"),
    )

    # Create indexes for state queries and error analysis
    op.create_index("ix_st_dlq_state", "st_dlq", ["state"])
    op.create_index("ix_st_dlq_driver", "st_dlq", ["driver"])
    op.create_index("ix_st_dlq_error_kind", "st_dlq", ["error_kind"])
    op.create_index("ix_st_dlq_wal_pos", "st_dlq", ["wal_pos"])


def downgrade() -> None:
    """Drop st_dlq table and all indexes."""
    op.drop_index("ix_st_dlq_wal_pos", table_name="st_dlq")
    op.drop_index("ix_st_dlq_error_kind", table_name="st_dlq")
    op.drop_index("ix_st_dlq_driver", table_name="st_dlq")
    op.drop_index("ix_st_dlq_state", table_name="st_dlq")
    op.drop_table("st_dlq")
