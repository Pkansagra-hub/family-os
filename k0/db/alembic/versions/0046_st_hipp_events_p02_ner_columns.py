"""Add P02 UltraBERT NER columns to st_hipp_events.

Revision ID: 0046
Revises: 0045
Create Date: 2026-01-03

P02 Pipeline - UltraBERT NER Storage Migration

Issue: 4.4.1 - Integrate UltraBERT NER entity extraction from P02

Adds columns needed to store UltraBERT 3-head NER output for P03 consumption:
- ner_entities_json: Raw entity list from ner_family + ner_general heads
- temporal_json: Raw temporal expressions from temporal head
- intent_category: User intent classification (from intent head)
- emotions_json: Alias for dominant_emotions_json (P03 compatibility)

Also renames existing columns for consistency:
- entities_json: Already exists, will store processed/resolved entities
- ner_entities_json: NEW - raw UltraBERT NER output (all 3 heads)

P03 Flow:
1. P02 writes raw UltraBERT output to ner_entities_json, temporal_json
2. P03 R4 reads ner_entities_json, processes with UltraBERTEntityExtractor
3. P03 R4 writes resolved entities back to entities_json (KG format)

Dossier Reference: P03 Consolidation Dossier v2, Section 4.5.1
Spec Reference: M4_EXECUTION.md, Issue 4.4.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0046"
down_revision: str = "0045"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add P02 UltraBERT NER columns to st_hipp_events."""
    # ============================================================
    # Add NER columns for P03 consolidation (Issue 4.4.1)
    # ============================================================

    # Raw UltraBERT NER output (ner_family + ner_general merged)
    # Format: {"entities": [...], "ner_family": [...], "ner_general": [...]}
    op.add_column(
        "st_hipp_events",
        sa.Column("ner_entities_json", sa.Text, nullable=True),
    )

    # Raw temporal expressions from UltraBERT temporal head
    # Format: {"entities": [{"text": "yesterday", "label": "DATE_REL", ...}]}
    op.add_column(
        "st_hipp_events",
        sa.Column("temporal_json", sa.Text, nullable=True),
    )

    # User intent classification from UltraBERT intent head
    # Values: log_memory, share_news, ask_question, request_help, etc.
    op.add_column(
        "st_hipp_events",
        sa.Column("intent_category", sa.Text, nullable=True),
    )

    # Ingress routing category from UltraBERT ingress head
    # Values: CELEBRATION, MEAL, ROUTINE, SOCIAL, TRAVEL, etc.
    op.add_column(
        "st_hipp_events",
        sa.Column("ingress_category", sa.Text, nullable=True),
    )

    # UltraBERT model version used for extraction
    op.add_column(
        "st_hipp_events",
        sa.Column("ultrabert_version", sa.Text, nullable=True),
    )

    # ============================================================
    # Add indexes for P03 NER processing
    # ============================================================

    # Index for finding events with pending NER processing
    # Note: PostgreSQL partial index where ner_entities_json IS NULL
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hipp_events_ner_pending
        ON st_hipp_events (event_time_utc DESC)
        WHERE ner_entities_json IS NULL
        """
    )


def downgrade() -> None:
    """Remove P02 UltraBERT NER columns from st_hipp_events."""
    # Drop index
    op.execute("DROP INDEX IF EXISTS idx_hipp_events_ner_pending")

    # Drop columns
    op.drop_column("st_hipp_events", "ultrabert_version")
    op.drop_column("st_hipp_events", "ingress_category")
    op.drop_column("st_hipp_events", "intent_category")
    op.drop_column("st_hipp_events", "temporal_json")
    op.drop_column("st_hipp_events", "ner_entities_json")
