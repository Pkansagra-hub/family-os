"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Part of K0 PostgreSQL Migration (Milestone 1.1.2)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers used by Alembic
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: Sequence[str] | None = ${repr(branch_labels)}
depends_on: Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply migration changes."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert migration changes."""
    ${downgrades if downgrades else "pass"}
