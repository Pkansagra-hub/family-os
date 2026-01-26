"""Allow st_kg_edges as observation layer.

Revision ID: 0068
Revises: 0067
Create Date: 2026-01-24

Fixes Postgres CHECK constraint ck_obs_layer to include st_kg_edges so
truth-writer edge observations can be persisted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence


# Revision identifiers
revision: str = "0068"
down_revision: str = "0067"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Extend ck_obs_layer to include st_kg_edges."""

    op.drop_constraint("ck_obs_layer", "st_observations", type_="check")
    op.create_check_constraint(
        "ck_obs_layer",
        "st_observations",
        "layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_kg_edges', 'st_social', 'st_prospective')",
    )


def downgrade() -> None:
    """Revert ck_obs_layer to pre-0068 allowed layers."""

    op.drop_constraint("ck_obs_layer", "st_observations", type_="check")
    op.create_check_constraint(
        "ck_obs_layer",
        "st_observations",
        "layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_social', 'st_prospective')",
    )
