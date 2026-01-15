"""Add P03 consumption columns to st_feedback_signals.

Revision ID: 0043
Revises: 0042
Create Date: 2025-01-01

Add consumed_at and consumed_by columns for P03 feedback consumption tracking.
Enables exactly-once processing of feedback signals.

Spec Reference: Dossier §6.22 st_feedback_signals

Schema Changes:
- ADD COLUMN consumed_at BIGINT (when signal was consumed)
- ADD COLUMN consumed_by TEXT (which process/cycle consumed it)
- ADD partial index for unconsumed signals
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0043"
down_revision: str = "0042"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add consumed_at and consumed_by columns to st_feedback_signals."""
    # Add consumed_at column
    op.add_column(
        "st_feedback_signals",
        sa.Column(
            "consumed_at",
            sa.BigInteger,
            nullable=True,
            comment="When signal was consumed (Unix ms)",
        ),
    )

    # Add consumed_by column
    op.add_column(
        "st_feedback_signals",
        sa.Column(
            "consumed_by",
            sa.Text,
            nullable=True,
            comment="Which process/cycle consumed this signal",
        ),
    )

    # Add partial index for unconsumed signals (efficient scan for P03)
    op.create_index(
        "idx_feedback_signals_unconsumed",
        "st_feedback_signals",
        ["received_at"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )

    # Add index for space-based unconsumed lookup
    op.create_index(
        "idx_feedback_signals_space_unconsumed",
        "st_feedback_signals",
        ["space_id", "received_at"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )


def downgrade() -> None:
    """Remove consumed_at and consumed_by columns from st_feedback_signals."""
    op.drop_index("idx_feedback_signals_space_unconsumed", table_name="st_feedback_signals")
    op.drop_index("idx_feedback_signals_unconsumed", table_name="st_feedback_signals")
    op.drop_column("st_feedback_signals", "consumed_by")
    op.drop_column("st_feedback_signals", "consumed_at")
