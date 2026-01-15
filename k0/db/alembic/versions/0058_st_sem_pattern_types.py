"""Extend st_sem pattern_type CHECK to include LESSON, EMOTIONAL_TREND, INSIGHT.

Revision ID: 0058
Revises: 0057
Create Date: 2026-01-12

P03 Consolidation Pipeline - Intent Routing Schema Update

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING
Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 1.2

This migration extends the pattern_type CHECK constraint to support
intent-based routing from P03 R5/R6:

New pattern types:
- LESSON: Created when intent_category = 'reflect' (learned insights)
- EMOTIONAL_TREND: Created when intent_category = 'express_feeling' (emotional patterns)
- INSIGHT: Related insights derived from introspection or reflection

Existing types (unchanged):
- ROUTINE: Temporal patterns (daily, weekly habits)
- PREFERENCE: Personal preferences (likes, dislikes)
- THEME: Recurring themes across episodes
- RELATIONSHIP: Relationship patterns with people
- GOAL: Goal-related patterns (moved from st_prospective for patterns)
- VALUE: Personal values and principles

Intent → st_sem Routing:
| Intent          | pattern_type      |
|-----------------|-------------------|
| reflect         | LESSON            |
| express_feeling | EMOTIONAL_TREND   |
| (introspection) | INSIGHT           |

Dossier Reference: P03 Consolidation Dossier Section 6.4
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# Revision identifiers
revision: str = "0058"
down_revision: str = "0057"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Extend pattern_type CHECK to include LESSON, EMOTIONAL_TREND, INSIGHT."""
    # Drop existing constraint
    op.execute("ALTER TABLE st_sem DROP CONSTRAINT IF EXISTS ck_sem_pattern_type")

    # Add new constraint with extended values
    op.execute(
        """
        ALTER TABLE st_sem ADD CONSTRAINT ck_sem_pattern_type
        CHECK (pattern_type IN (
            'ROUTINE',
            'PREFERENCE',
            'THEME',
            'RELATIONSHIP',
            'GOAL',
            'VALUE',
            'LESSON',
            'EMOTIONAL_TREND',
            'INSIGHT'
        ))
        """
    )


def downgrade() -> None:
    """Restore original pattern_type CHECK constraint."""
    # Drop extended constraint
    op.execute("ALTER TABLE st_sem DROP CONSTRAINT IF EXISTS ck_sem_pattern_type")

    # Restore original constraint
    op.execute(
        """
        ALTER TABLE st_sem ADD CONSTRAINT ck_sem_pattern_type
        CHECK (pattern_type IN ('ROUTINE', 'PREFERENCE', 'THEME', 'RELATIONSHIP', 'GOAL', 'VALUE'))
        """
    )
