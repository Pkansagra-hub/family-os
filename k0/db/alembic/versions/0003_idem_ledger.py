"""Create idem_ledger table (Idempotency Tracking).

Revision ID: 0003
Revises: 0002
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE idem_ledger (
  idem_key TEXT PRIMARY KEY,
  receipt_id TEXT NOT NULL,
  first_seen_ts TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('COMMITTED','REJECTED')),
  expiry_ts TEXT
);
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
    """Create idem_ledger table matching SQLite schema."""
    op.create_table(
        "idem_ledger",
        # Primary key - idempotency key string
        sa.Column("idem_key", sa.Text, primary_key=True),
        # Associated receipt - NOT NULL per SQLite
        sa.Column("receipt_id", sa.Text, nullable=False),
        # Timestamps as TEXT (ISO8601 strings)
        sa.Column("first_seen_ts", sa.Text, nullable=False),
        # State with CHECK constraint
        sa.Column("state", sa.Text, nullable=False),
        # TTL expiry
        sa.Column("expiry_ts", sa.Text, nullable=True),
        # CHECK constraint
        sa.CheckConstraint("state IN ('COMMITTED', 'REJECTED')", name="ck_idem_ledger_state"),
    )


def downgrade() -> None:
    """Drop idem_ledger table."""
    op.drop_table("idem_ledger")
