"""Create st_observations table (Holistic observation log for truth layers).

Revision ID: 0067
Revises: 0066
Create Date: 2025-01-17

Append-only observation log capturing WHEN and WITH WHAT CONTEXT
each truth layer record was observed. Enables holistic memory queries:
- Temporal: "What did I eat last summer?"
- Emotional: "What makes me anxious?"
- Social: "What do we discuss as a family?"
- Modality: "What do I say vs type?"
- Location: "What do I think about during commute?"

Architecture:
- Links to TRUTH LAYERS (permanent, 1-5 year TTL)
- Does NOT depend on st_hipp_events (20-day tombstone)
- source_event_id is OPTIONAL soft reference (degrades gracefully)

Pipeline Scope: P03 Consolidation (WRITE only)
P01 Recall reads via k0/modules/recall/observation_context_fetcher.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0067"
down_revision: str = "0066"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_observations table with all columns and indexes."""
    op.create_table(
        "st_observations",
        # ============================================================
        # Core Identity (5 columns)
        # ============================================================
        sa.Column(
            "observation_id",
            sa.Text,
            primary_key=True,
            comment="ULID for observation (provides ms-level ordering)",
        ),
        sa.Column(
            "tenant_id",
            sa.Text,
            nullable=False,
            comment="Tenant partition key",
        ),
        sa.Column(
            "layer",
            sa.Text,
            nullable=False,
            comment="Truth layer: st_epi, st_sem, st_kg_dom, st_social, st_prospective",
        ),
        sa.Column(
            "record_id",
            sa.Text,
            nullable=False,
            comment="Primary key of the truth layer record",
        ),
        sa.Column(
            "observed_at",
            sa.BigInteger,
            nullable=False,
            comment="Observation timestamp (Unix ms) - self-contained, no external dependency",
        ),
        # ============================================================
        # Observation Metadata (3 columns)
        # ============================================================
        sa.Column(
            "observation_type",
            sa.Text,
            nullable=False,
            comment="FIRST_SEEN (INSERT) or REINFORCEMENT (MERGE)",
        ),
        sa.Column(
            "source_event_id",
            sa.Text,
            nullable=True,
            comment="OPTIONAL soft reference to st_hipp_events (degrades after 20 days)",
        ),
        sa.Column(
            "observation_weight",
            sa.Float,
            nullable=False,
            server_default="1.0",
            comment="Weight of observation [0-1], default 1.0",
        ),
        # ============================================================
        # Emotional Context (5 columns)
        # ============================================================
        sa.Column(
            "sentiment_score",
            sa.Float,
            nullable=True,
            comment="Sentiment score [0-1] from st_hipp_events",
        ),
        sa.Column(
            "sentiment_label",
            sa.Text,
            nullable=True,
            comment="Sentiment label (positive, negative, neutral)",
        ),
        sa.Column(
            "affect_valence",
            sa.Float,
            nullable=True,
            comment="Affect valence [-1 to +1] from st_hipp_events",
        ),
        sa.Column(
            "affect_arousal",
            sa.Float,
            nullable=True,
            comment="Affect arousal [0-1] from st_hipp_events",
        ),
        sa.Column(
            "dominant_emotion",
            sa.Text,
            nullable=True,
            comment="Primary emotion extracted from dominant_emotions_json",
        ),
        # ============================================================
        # Salience Context (3 columns)
        # ============================================================
        sa.Column(
            "salience_score",
            sa.Float,
            nullable=True,
            comment="Salience score [0-1] from st_hipp_events",
        ),
        sa.Column(
            "novelty_score",
            sa.Float,
            nullable=True,
            comment="Novelty score [0-1] from pattern separation",
        ),
        sa.Column(
            "salience_band",
            sa.Text,
            nullable=True,
            comment="Salience band: HIGH, MED, LOW",
        ),
        # ============================================================
        # Modality Context (3 columns)
        # ============================================================
        sa.Column(
            "ingress_channel",
            sa.Text,
            nullable=True,
            comment="Input channel: voice, chat, api, etc.",
        ),
        sa.Column(
            "ingress_source",
            sa.Text,
            nullable=True,
            comment="Source application or integration",
        ),
        sa.Column(
            "device_kind",
            sa.Text,
            nullable=True,
            comment="Device type: mobile, desktop, tablet, etc.",
        ),
        # ============================================================
        # Physical Context (3 columns)
        # ============================================================
        sa.Column(
            "location_name",
            sa.Text,
            nullable=True,
            comment="Human-readable location name",
        ),
        sa.Column(
            "location_type",
            sa.Text,
            nullable=True,
            comment="Location category: home, work, transit, etc.",
        ),
        sa.Column(
            "geohash_6",
            sa.Text,
            nullable=True,
            comment="6-character geohash for location clustering",
        ),
        # ============================================================
        # Social Context (4 columns)
        # ============================================================
        sa.Column(
            "social_context",
            sa.Text,
            nullable=True,
            comment="Social setting: family, friends, work, solo",
        ),
        sa.Column(
            "social_intimacy",
            sa.Text,
            nullable=True,
            comment="Intimacy level of social context",
        ),
        sa.Column(
            "is_solo_event",
            sa.Boolean,
            nullable=True,
            comment="TRUE if user was alone",
        ),
        sa.Column(
            "num_participants",
            sa.Integer,
            nullable=True,
            comment="Number of participants in interaction",
        ),
        # ============================================================
        # Temporal Context (4 columns)
        # ============================================================
        sa.Column(
            "time_of_day_bucket",
            sa.Text,
            nullable=True,
            comment="Time bucket: morning, afternoon, evening, night",
        ),
        sa.Column(
            "circadian_slot",
            sa.Text,
            nullable=True,
            comment="Circadian rhythm slot",
        ),
        sa.Column(
            "is_weekend",
            sa.Boolean,
            nullable=True,
            comment="TRUE if observation was on weekend",
        ),
        sa.Column(
            "day_of_week",
            sa.Text,
            nullable=True,
            comment="Day of week: Monday, Tuesday, etc.",
        ),
        # ============================================================
        # Prospective Memory Context (2 columns)
        # ============================================================
        sa.Column(
            "anchor_time_utc",
            sa.BigInteger,
            nullable=True,
            comment="For prospective: when temporal expression was spoken",
        ),
        sa.Column(
            "original_temporal_expr",
            sa.Text,
            nullable=True,
            comment="For prospective: original expression ('next week', 'tomorrow')",
        ),
        # ============================================================
        # CHECK Constraints
        # ============================================================
        sa.CheckConstraint(
            "layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_social', 'st_prospective')",
            name="ck_obs_layer",
        ),
        sa.CheckConstraint(
            "observation_type IN ('FIRST_SEEN', 'REINFORCEMENT')",
            name="ck_obs_type",
        ),
        sa.CheckConstraint(
            "salience_band IS NULL OR salience_band IN ('HIGH', 'MED', 'LOW')",
            name="ck_obs_salience_band",
        ),
        # ============================================================
        # NO Foreign Keys (by design)
        # - source_event_id is soft reference (st_hipp_events has 20-day tombstone)
        # - record_id references different tables per layer (would need 5 FKs)
        # ============================================================
    )

    # ============================================================
    # Primary Query Indexes
    # ============================================================

    # Get observations for a specific truth record (most common query)
    op.create_index(
        "idx_obs_record_time",
        "st_observations",
        ["layer", "record_id", sa.text("observed_at DESC")],
    )

    # Temporal range queries: "What happened last summer?"
    op.create_index(
        "idx_obs_tenant_time",
        "st_observations",
        ["tenant_id", sa.text("observed_at DESC")],
    )

    # ============================================================
    # Holistic Context Indexes (Partial - only index non-NULL)
    # ============================================================

    # Emotional queries: "What makes me happy/anxious?"
    op.create_index(
        "idx_obs_sentiment",
        "st_observations",
        ["tenant_id", "sentiment_label", sa.text("observed_at DESC")],
        postgresql_where=sa.text("sentiment_label IS NOT NULL"),
    )

    # Salience queries: "What stood out this year?"
    op.create_index(
        "idx_obs_salience_high",
        "st_observations",
        ["tenant_id", sa.text("observed_at DESC")],
        postgresql_where=sa.text("salience_band = 'HIGH'"),
    )

    # Modality queries: "What do I say vs type?"
    op.create_index(
        "idx_obs_channel",
        "st_observations",
        ["tenant_id", "ingress_channel", sa.text("observed_at DESC")],
        postgresql_where=sa.text("ingress_channel IS NOT NULL"),
    )

    # Social queries: "What do we discuss as a family?"
    op.create_index(
        "idx_obs_social",
        "st_observations",
        ["tenant_id", "social_context", sa.text("observed_at DESC")],
        postgresql_where=sa.text("social_context IS NOT NULL"),
    )

    # Location queries: "What do I think about at work?"
    op.create_index(
        "idx_obs_location",
        "st_observations",
        ["tenant_id", "location_type", sa.text("observed_at DESC")],
        postgresql_where=sa.text("location_type IS NOT NULL"),
    )

    # ============================================================
    # Prospective Memory Index
    # ============================================================

    # Prospective queries: "What reminders did I set last week?"
    op.create_index(
        "idx_obs_anchor_time",
        "st_observations",
        ["tenant_id", sa.text("anchor_time_utc DESC")],
        postgresql_where=sa.text("layer = 'st_prospective' AND anchor_time_utc IS NOT NULL"),
    )

    # ============================================================
    # Additional Analysis Indexes
    # ============================================================

    # Circadian pattern queries: "When am I most productive?"
    op.create_index(
        "idx_obs_circadian",
        "st_observations",
        ["tenant_id", "time_of_day_bucket", "circadian_slot"],
        postgresql_where=sa.text("time_of_day_bucket IS NOT NULL"),
    )

    # Novelty analysis: "What new things captured my attention?"
    op.create_index(
        "idx_obs_high_novelty",
        "st_observations",
        ["tenant_id", sa.text("observed_at DESC")],
        postgresql_where=sa.text("novelty_score > 0.8"),
    )

    # Weekend vs weekday analysis
    op.create_index(
        "idx_obs_weekend",
        "st_observations",
        ["tenant_id", "is_weekend", sa.text("observed_at DESC")],
        postgresql_where=sa.text("is_weekend IS NOT NULL"),
    )

    # Source event lookup (optional, for provenance when available)
    op.create_index(
        "idx_obs_source_event",
        "st_observations",
        ["source_event_id"],
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )

    # Layer-specific queries with time ordering
    op.create_index(
        "idx_obs_layer_tenant_time",
        "st_observations",
        ["layer", "tenant_id", sa.text("observed_at DESC")],
    )


def downgrade() -> None:
    """Drop st_observations table and all indexes."""
    # Drop indexes in reverse order
    op.drop_index("idx_obs_layer_tenant_time", table_name="st_observations")
    op.drop_index("idx_obs_source_event", table_name="st_observations")
    op.drop_index("idx_obs_weekend", table_name="st_observations")
    op.drop_index("idx_obs_high_novelty", table_name="st_observations")
    op.drop_index("idx_obs_circadian", table_name="st_observations")
    op.drop_index("idx_obs_anchor_time", table_name="st_observations")
    op.drop_index("idx_obs_location", table_name="st_observations")
    op.drop_index("idx_obs_social", table_name="st_observations")
    op.drop_index("idx_obs_channel", table_name="st_observations")
    op.drop_index("idx_obs_salience_high", table_name="st_observations")
    op.drop_index("idx_obs_sentiment", table_name="st_observations")
    op.drop_index("idx_obs_tenant_time", table_name="st_observations")
    op.drop_index("idx_obs_record_time", table_name="st_observations")
    op.drop_table("st_observations")
