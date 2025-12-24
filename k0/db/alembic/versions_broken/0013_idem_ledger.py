"""Create idem_ledger table (Idempotency Tracking).

Revision ID: 0013
Revises: 0012
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.3 - Issue 2.1.3.4)

The idem_ledger table tracks idempotency keys for deduplication.
Prevents duplicate envelope processing within the TTL window.

Columns: 5
Indexes: 1
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0013"
down_revision: str = "0012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create idem_ledger table."""
    op.create_table(
        "idem_ledger",
        # Primary key - idempotency key string
        sa.Column("idem_key", sa.String(128), primary_key=True),
        # Associated receipt
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Timestamps
        sa.Column(
            "first_seen_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # State
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        # TTL expiry
        sa.Column("expiry_ts", sa.DateTime(timezone=True), nullable=True),
    )

    # Create index for expiry cleanup
    op.create_index(
        "ix_idem_ledger_expiry",
        "idem_ledger",
        ["expiry_ts"],
        postgresql_where=sa.text("expiry_ts IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop idem_ledger table and all indexes."""
    op.drop_index("ix_idem_ledger_expiry", table_name="idem_ledger")
    op.drop_table("idem_ledger")
