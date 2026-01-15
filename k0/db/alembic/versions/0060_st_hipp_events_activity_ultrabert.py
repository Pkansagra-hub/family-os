"""Add UltraBERT activity type and intent columns to st_hipp_events.

Revision ID: 0060
Revises: 0059
Create Date: 2026-01-13

P02 Pipeline - UltraBERT Activity & Intent Storage

Issue: Activity type granularity loss (7-type legacy loses HEALTH, EMOTIONAL, QUERY)

Problem:
- UltraBERT INGRESS head produces 12 activity types: DIARY, TASK, HEALTH, FINANCE,
  RELATIONSHIP, WORK, META, MEMORY, PLANNING, CELEBRATION, CONCERN, GRATITUDE
- Legacy system only supports 7 types: meal, conversation, routine, milestone, social, work, unknown
- Many UltraBERT types (DIARY, TASK, FINANCE, RELATIONSHIP, META, MEMORY, PLANNING,
  CONCERN, GRATITUDE) were mapped to "unknown"

Solution:
- Add activity_type_ultrabert: Store raw UltraBERT INGRESS classification (12 types)
- Add intent_ultrabert: Store UltraBERT INTENT classification (8 types)
- Preserve legacy activity_type for backward compatibility
- P03 can use activity_type_ultrabert for richer clustering/analysis

UltraBERT INGRESS Labels (12):
| ID | Label        | Description                      |
|----|--------------|----------------------------------|
| 0  | DIARY        | Personal diary/journal entries   |
| 1  | TASK         | Task/todo items                  |
| 2  | HEALTH       | Health/fitness related           |
| 3  | FINANCE      | Financial/money related          |
| 4  | RELATIONSHIP | Relationship discussions         |
| 5  | WORK         | Work/professional content        |
| 6  | META         | System/meta messages             |
| 7  | MEMORY       | Memory recall/reminiscing        |
| 8  | PLANNING     | Future planning content          |
| 9  | CELEBRATION  | Celebrations/milestones          |
| 10 | CONCERN      | Worries/concerns                 |
| 11 | GRATITUDE    | Gratitude/thankfulness           |

UltraBERT INTENT Labels (8):
| ID | Label          | Description                      |
|----|----------------|----------------------------------|
| 0  | log_memory     | Recording a memory               |
| 1  | query_memory   | Asking about past events         |
| 2  | set_reminder   | Setting a reminder               |
| 3  | express_feeling| Expressing emotions              |
| 4  | seek_advice    | Asking for advice                |
| 5  | share_news     | Sharing news/updates             |
| 6  | reflect        | Reflection/contemplation         |
| 7  | other          | Other intents                    |

Dossier Reference: P02 Write Pipeline Dossier, Section 4.5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0060"
down_revision: str = "0059"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add UltraBERT activity type and intent columns to st_hipp_events."""
    # ============================================================
    # UltraBERT INGRESS Classification (Activity Type)
    # ============================================================

    # Raw UltraBERT INGRESS classification (12 types)
    # Values: DIARY, TASK, HEALTH, FINANCE, RELATIONSHIP, WORK,
    #         META, MEMORY, PLANNING, CELEBRATION, CONCERN, GRATITUDE
    # Note: Legacy activity_type column preserved for backward compatibility
    op.add_column(
        "st_hipp_events",
        sa.Column("activity_type_ultrabert", sa.Text, nullable=True),
    )

    # Confidence score for activity classification (0.0 to 1.0)
    op.add_column(
        "st_hipp_events",
        sa.Column("activity_type_confidence", sa.Float, nullable=True),
    )

    # Check constraint for valid UltraBERT activity types
    op.execute(
        """
        ALTER TABLE st_hipp_events
        ADD CONSTRAINT ck_hipp_activity_type_ultrabert
        CHECK (activity_type_ultrabert IS NULL OR activity_type_ultrabert IN (
            'DIARY', 'TASK', 'HEALTH', 'FINANCE', 'RELATIONSHIP', 'WORK',
            'META', 'MEMORY', 'PLANNING', 'CELEBRATION', 'CONCERN', 'GRATITUDE'
        ))
        """
    )

    # ============================================================
    # UltraBERT INTENT Classification
    # ============================================================

    # UltraBERT INTENT classification (8 types)
    # Values: log_memory, query_memory, set_reminder, express_feeling,
    #         seek_advice, share_news, reflect, other
    op.add_column(
        "st_hipp_events",
        sa.Column("intent_ultrabert", sa.Text, nullable=True),
    )

    # Confidence score for intent classification (0.0 to 1.0)
    op.add_column(
        "st_hipp_events",
        sa.Column("intent_confidence", sa.Float, nullable=True),
    )

    # Check constraint for valid UltraBERT intent types
    op.execute(
        """
        ALTER TABLE st_hipp_events
        ADD CONSTRAINT ck_hipp_intent_ultrabert
        CHECK (intent_ultrabert IS NULL OR intent_ultrabert IN (
            'log_memory', 'query_memory', 'set_reminder', 'express_feeling',
            'seek_advice', 'share_news', 'reflect', 'other'
        ))
        """
    )

    # ============================================================
    # Indexes for P03 consumption
    # ============================================================

    # Index for finding health-related events
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hipp_events_activity_health
        ON st_hipp_events (event_time_utc DESC)
        WHERE activity_type_ultrabert = 'HEALTH'
        """
    )

    # Index for finding concern/emotional events
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hipp_events_activity_concern
        ON st_hipp_events (event_time_utc DESC)
        WHERE activity_type_ultrabert IN ('CONCERN', 'GRATITUDE')
        """
    )

    # Index for query events (memory retrieval patterns)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hipp_events_intent_query
        ON st_hipp_events (event_time_utc DESC)
        WHERE intent_ultrabert = 'query_memory'
        """
    )


def downgrade() -> None:
    """Remove UltraBERT activity type and intent columns from st_hipp_events."""
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_hipp_events_intent_query")
    op.execute("DROP INDEX IF EXISTS idx_hipp_events_activity_concern")
    op.execute("DROP INDEX IF EXISTS idx_hipp_events_activity_health")

    # Drop check constraints
    op.execute("ALTER TABLE st_hipp_events DROP CONSTRAINT IF EXISTS ck_hipp_intent_ultrabert")
    op.execute(
        "ALTER TABLE st_hipp_events DROP CONSTRAINT IF EXISTS ck_hipp_activity_type_ultrabert"
    )

    # Drop columns
    op.drop_column("st_hipp_events", "intent_confidence")
    op.drop_column("st_hipp_events", "intent_ultrabert")
    op.drop_column("st_hipp_events", "activity_type_confidence")
    op.drop_column("st_hipp_events", "activity_type_ultrabert")
