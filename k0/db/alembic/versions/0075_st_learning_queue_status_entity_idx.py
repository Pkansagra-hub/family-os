"""Add composite index (status, entity_id) to st_learning_queue.

Revision ID: 0075
Revises: 0074
Create Date: 2025-06-01

Adds idx_learning_queue_status_entity composite index for R4 Discovery
SG-003 pattern: efficient entity-scoped gap lookups by status.

Plan Reference: PLAN_HEBBIAN_WEIGHT_LEARNER_INTEGRATION.md Issue 5.S.1.2
Spec Reference: Dossier Section 6.11 st_learning_queue
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0075"
down_revision: str = "0074"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add composite index on (status, entity_id) for entity-scoped gap queries."""
    op.create_index(
        "idx_learning_queue_status_entity",
        "st_learning_queue",
        ["status", "entity_id"],
    )


def downgrade() -> None:
    """Drop the composite index."""
    op.drop_index(
        "idx_learning_queue_status_entity",
        table_name="st_learning_queue",
    )
