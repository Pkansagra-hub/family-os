"""Add UltraBERT relations, safety_familyos, and nli columns to st_hipp_events.

Revision ID: 0053
Revises: 0052
Create Date: 2026-01-08

P02 Pipeline - UltraBERT Full Capability Storage

Issue: P02 UltraBERT Integration - Store all 12 capabilities

Adds columns for UltraBERT outputs currently NOT stored:
- extracted_relations_json: Relationship types from UltraBERT relations head
  Example: ["parent_of"], ["spouse_of", "caretaker_of"]
  Used by P03 R4 for st_social population without inference

- safety_familyos_band: 4-band safety from UltraBERT (GREEN/AMBER/RED/CRISIS)
  This is UltraBERT's safety assessment, distinct from K1 policy_band
  Used for safety arbitration when K1 and UltraBERT disagree

- safety_familyos_subcategory: Detailed safety subcategory (12 types)
  Example: "self_harm_ideation", "stress", "none"

- nli_label: Natural language inference result
  Values: "entailment", "neutral", "contradiction"
  Used for fact checking and contradiction detection

Safety Arbitration Strategy:
- policy_band: K1's policy decision (envelope-level, from user's context)
- safety_familyos_band: UltraBERT's content analysis (text-level, 100% recall)
- When they differ: The MORE RESTRICTIVE band wins (CRISIS > RED > AMBER > GREEN)
- Example: K1 says GREEN (normal context), UltraBERT says CRISIS (text analysis)
         → Final safety = CRISIS (escalate for review)

P03 Flow:
1. P02 writes UltraBERT relations to extracted_relations_json
2. P03 R4 reads extracted_relations_json for st_social population
3. No inference needed - direct signal from UltraBERT

Dossier Reference: P02 Write Pipeline Dossier, Section 4.6
ADR Reference: docs/architecture/decisions-K0/k012-ultrabert-full-capabilities.md
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0053"
down_revision: str = "0052"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add UltraBERT full capability columns to st_hipp_events."""
    # ============================================================
    # UltraBERT Relations Output (for st_social population)
    # ============================================================

    # Extracted relationship types from UltraBERT relations head
    # Format: JSON array of relationship types
    # Example: ["parent_of"], ["spouse_of", "caretaker_of"], []
    # Maps to st_social.relationship_type without inference
    op.add_column(
        "st_hipp_events",
        sa.Column("extracted_relations_json", sa.Text, nullable=True),
    )

    # ============================================================
    # UltraBERT Safety Output (for safety arbitration)
    # ============================================================

    # 4-band safety classification from UltraBERT
    # Distinct from policy_band (K1 envelope-level decision)
    # Values: GREEN, AMBER, RED, CRISIS
    op.add_column(
        "st_hipp_events",
        sa.Column("safety_familyos_band", sa.Text, nullable=True),
    )

    # Check constraint for valid safety bands
    op.execute(
        """
        ALTER TABLE st_hipp_events
        ADD CONSTRAINT ck_hipp_safety_familyos_band
        CHECK (safety_familyos_band IS NULL OR safety_familyos_band IN ('GREEN', 'AMBER', 'RED', 'CRISIS'))
        """
    )

    # Detailed safety subcategory (12 types)
    # GREEN: none
    # AMBER: stress, mild_sadness, frustration, health_mention
    # RED: persistent_sadness, isolation, hopelessness, substance
    # CRISIS: self_harm_ideation, suicide_ideation, harm_to_others, abuse_disclosure
    op.add_column(
        "st_hipp_events",
        sa.Column("safety_familyos_subcategory", sa.Text, nullable=True),
    )

    # Effective safety band (result of arbitration between policy_band and safety_familyos_band)
    # Always the MORE RESTRICTIVE of the two
    op.add_column(
        "st_hipp_events",
        sa.Column("effective_safety_band", sa.Text, nullable=True),
    )

    # Check constraint for effective safety bands
    op.execute(
        """
        ALTER TABLE st_hipp_events
        ADD CONSTRAINT ck_hipp_effective_safety_band
        CHECK (effective_safety_band IS NULL OR effective_safety_band IN ('GREEN', 'AMBER', 'RED', 'CRISIS'))
        """
    )

    # ============================================================
    # UltraBERT NLI Output (for fact checking)
    # ============================================================

    # Natural language inference result
    # Values: entailment, neutral, contradiction
    # Used for detecting contradictions in episodic memory
    op.add_column(
        "st_hipp_events",
        sa.Column("nli_label", sa.Text, nullable=True),
    )

    # NLI confidence score
    op.add_column(
        "st_hipp_events",
        sa.Column("nli_confidence", sa.Float, nullable=True),
    )

    # ============================================================
    # Sentiment Confidence (already have sentiment_score/label)
    # ============================================================

    # Sentiment confidence from UltraBERT (0.0 to 1.0)
    op.add_column(
        "st_hipp_events",
        sa.Column("sentiment_confidence", sa.Float, nullable=True),
    )

    # ============================================================
    # Indexes for P03 consumption
    # ============================================================

    # Index for finding events with safety concerns
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hipp_events_safety_concern
        ON st_hipp_events (event_time_utc DESC)
        WHERE safety_familyos_band IN ('AMBER', 'RED', 'CRISIS')
        """
    )

    # Index for finding events with relationships for st_social
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hipp_events_has_relations
        ON st_hipp_events (event_time_utc DESC)
        WHERE extracted_relations_json IS NOT NULL AND extracted_relations_json != '[]'
        """
    )


def downgrade() -> None:
    """Remove UltraBERT full capability columns from st_hipp_events."""
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_hipp_events_has_relations")
    op.execute("DROP INDEX IF EXISTS idx_hipp_events_safety_concern")

    # Drop check constraints
    op.execute("ALTER TABLE st_hipp_events DROP CONSTRAINT IF EXISTS ck_hipp_effective_safety_band")
    op.execute("ALTER TABLE st_hipp_events DROP CONSTRAINT IF EXISTS ck_hipp_safety_familyos_band")

    # Drop columns
    op.drop_column("st_hipp_events", "sentiment_confidence")
    op.drop_column("st_hipp_events", "nli_confidence")
    op.drop_column("st_hipp_events", "nli_label")
    op.drop_column("st_hipp_events", "effective_safety_band")
    op.drop_column("st_hipp_events", "safety_familyos_subcategory")
    op.drop_column("st_hipp_events", "safety_familyos_band")
    op.drop_column("st_hipp_events", "extracted_relations_json")
