"""Add archival_status column to st_hipp_events.

Revision ID: 0051
Revises: 0050
Create Date: 2026-01-08

Fixes P03 R0 batch selector query which expects archival_status column.
This column is used to filter out archived events from consolidation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0051"
down_revision: str = "0050"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add archival_status column to st_hipp_events."""
    op.add_column(
        "st_hipp_events",
        sa.Column("archival_status", sa.Text, nullable=True),
    )


def downgrade() -> None:
    """Remove archival_status column from st_hipp_events."""
    op.drop_column("st_hipp_events", "archival_status")
