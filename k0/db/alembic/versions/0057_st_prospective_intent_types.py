"""Extend st_prospective intention_type CHECK to include DECISION and COUNTERFACTUAL.

Revision ID: 0057
Revises: 0056
Create Date: 2026-01-12

P03 Consolidation Pipeline - Intent Routing Schema Update

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING
Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 1.1

This migration extends the intention_type CHECK constraint to support
intent-based routing from P03 R5/R6:

New intention types:
- DECISION: Created when intent_category = 'seek_advice' (pending decisions)
- COUNTERFACTUAL: Already existed in R5 forward simulation but wasn't in CHECK

Existing types (unchanged):
- GOAL: Long-term aspirations
- PLAN: Structured action plans
- REMINDER: set_reminder intent → target_date reminder
- COMMITMENT: Promises/obligations to others
- WISH: Desires without concrete plans

Intent → st_prospective Routing:
| Intent          | intention_type   |
|-----------------|------------------|
| set_reminder    | REMINDER         |
| seek_advice     | DECISION         |
| reflect         | (goes to st_sem) |
| express_feeling | (goes to st_sem) |

Dossier Reference: P03 Consolidation Dossier Section 6.7
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# Revision identifiers
revision: str = "0057"
down_revision: str = "0056"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Extend intention_type CHECK to include DECISION and COUNTERFACTUAL."""
    # Drop existing constraint
    op.execute("ALTER TABLE st_prospective DROP CONSTRAINT IF EXISTS ck_prosp_intention_type")

    # Add new constraint with extended values
    op.execute(
        """
        ALTER TABLE st_prospective ADD CONSTRAINT ck_prosp_intention_type
        CHECK (intention_type IN (
            'GOAL',
            'PLAN',
            'REMINDER',
            'COMMITMENT',
            'WISH',
            'DECISION',
            'COUNTERFACTUAL'
        ))
        """
    )


def downgrade() -> None:
    """Restore original intention_type CHECK constraint."""
    # Drop extended constraint
    op.execute("ALTER TABLE st_prospective DROP CONSTRAINT IF EXISTS ck_prosp_intention_type")

    # Restore original constraint
    op.execute(
        """
        ALTER TABLE st_prospective ADD CONSTRAINT ck_prosp_intention_type
        CHECK (intention_type IN ('GOAL', 'PLAN', 'REMINDER', 'COMMITMENT', 'WISH'))
        """
    )
