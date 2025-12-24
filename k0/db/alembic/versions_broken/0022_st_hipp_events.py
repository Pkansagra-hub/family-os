"""Create st_hipp_events table (Hippocampus Events).

Revision ID: 0022
Revises: 0021
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.2.1 - Issue 2.2.1.1)

The st_hipp_events table is the largest table (90 columns).
It stores processed hippocampus events with NLP annotations,
temporal data, location, social context, and embedding references.

Columns: 90
Indexes: 9
Foreign Keys: 1 (wal_pos -> st_wal.pos)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0022"
down_revision: str = "0021"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_hipp_events table with all 90 columns."""
    op.create_table(
        "st_hipp_events",
        # ===== Group 1: Core Identity (15 cols) =====
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wal_pos", sa.BigInteger, nullable=True, unique=True),
        sa.Column("cognitive_trace_id", sa.String(128), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("effective_space_id", sa.String(64), nullable=True),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("uow_id", sa.String(64), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=True),
        sa.Column("envelope_sha256", sa.String(64), nullable=True),
        sa.Column("sig_alg", sa.String(16), nullable=True),
        sa.Column("sig_kid", sa.String(128), nullable=True),
        sa.Column("idem_key", sa.String(128), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("clock_skew_ms", sa.Integer, nullable=True),
        # ===== Group 2: Policy & Privacy (11 cols) =====
        sa.Column("policy_decision", sa.String(16), nullable=True),
        sa.Column("policy_band", sa.String(16), nullable=True),
        sa.Column("policy_version", sa.String(32), nullable=True),
        sa.Column("obligations_json", postgresql.JSONB, nullable=True),
        sa.Column("visible_to_json", postgresql.JSONB, nullable=True),
        sa.Column("visibility_scope", sa.String(16), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("co_owners_json", postgresql.JSONB, nullable=True),
        sa.Column("retention_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retention_bucket", sa.String(32), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        # ===== Group 3: Device & Ingress (5 cols) =====
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("device_kind", sa.String(32), nullable=True),
        sa.Column("device_os", sa.String(32), nullable=True),
        sa.Column("ingress_channel", sa.String(32), nullable=True),
        # ===== Group 4: Temporal (12 cols) =====
        sa.Column("event_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("write_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("write_lag_ms", sa.Integer, nullable=True),
        sa.Column("local_date", sa.Date, nullable=True),
        sa.Column("local_time", sa.Time, nullable=True),
        sa.Column("day_of_week", sa.SmallInteger, nullable=True),
        sa.Column("is_weekend", sa.Boolean, nullable=True),
        sa.Column("time_of_day_bucket", sa.String(16), nullable=True),
        sa.Column("circadian_slot", sa.String(16), nullable=True),
        sa.Column("is_backdated", sa.Boolean, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # ===== Group 5: Location (5 cols) =====
        sa.Column("location_name", sa.String(256), nullable=True),
        sa.Column("location_type", sa.String(32), nullable=True),
        sa.Column("geohash_6", sa.String(12), nullable=True),
        sa.Column("geo_precision_external", sa.String(16), nullable=True),
        sa.Column("geo_masking_reason", sa.String(32), nullable=True),
        # ===== Group 6: Social Context (8 cols) =====
        sa.Column("participants_json", postgresql.JSONB, nullable=True),
        sa.Column("num_participants", sa.Integer, nullable=True),
        sa.Column("has_partner_present", sa.Boolean, nullable=True),
        sa.Column("has_parent_present", sa.Boolean, nullable=True),
        sa.Column("is_solo_event", sa.Boolean, nullable=True),
        sa.Column("participant_roles_json", postgresql.JSONB, nullable=True),
        sa.Column("social_context", sa.String(32), nullable=True),
        sa.Column("social_intimacy", sa.String(16), nullable=True),
        # ===== Group 7: Text Content (5 cols) =====
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("text_normalized", sa.Text, nullable=True),
        sa.Column("char_count", sa.Integer, nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        # ===== Group 8: Activity (5 cols) =====
        sa.Column("activity_type", sa.String(64), nullable=True),
        sa.Column("activity_category", sa.String(32), nullable=True),
        sa.Column("is_meal", sa.Boolean, nullable=True),
        sa.Column("is_outing", sa.Boolean, nullable=True),
        sa.Column("ingress_source", sa.String(32), nullable=True),
        # ===== Group 9: Deduplication & Clustering (10 cols) =====
        sa.Column("simhash_hex", sa.String(16), nullable=True),
        sa.Column("minhash32", postgresql.ARRAY(sa.Integer), nullable=True),
        sa.Column("novelty_score", sa.Float, nullable=True),
        sa.Column("near_duplicates_json", postgresql.JSONB, nullable=True),
        sa.Column("is_near_duplicate", sa.Boolean, nullable=True),
        sa.Column("episode_cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cluster_confidence", sa.Float, nullable=True),
        sa.Column("clustering_version", sa.String(32), nullable=True),
        sa.Column("embedding_id", postgresql.UUID(as_uuid=True), nullable=True, unique=True),
        sa.Column("embedding_status", sa.String(16), nullable=True),
        # ===== Group 10: NLP & Affect (14 cols) =====
        sa.Column("entities_json", postgresql.JSONB, nullable=True),
        sa.Column("kg_triples_json", postgresql.JSONB, nullable=True),
        sa.Column("sentiment_score", sa.Float, nullable=True),
        sa.Column("sentiment_label", sa.String(16), nullable=True),
        sa.Column("dominant_emotions_json", postgresql.JSONB, nullable=True),
        sa.Column("affect_valence", sa.Float, nullable=True),
        sa.Column("affect_arousal", sa.Float, nullable=True),
        sa.Column("affect_band", sa.String(16), nullable=True),
        sa.Column("salience_score", sa.Float, nullable=True),
        sa.Column("salience_reasons_json", postgresql.JSONB, nullable=True),
        sa.Column("salience_band", sa.String(16), nullable=True),
        sa.Column("hippocampus_api_version", sa.String(16), nullable=True),
        sa.Column("space_resolver_version", sa.String(16), nullable=True),
        sa.Column("schema_uri", sa.String(512), nullable=True),
        # ===== Foreign Key =====
        sa.ForeignKeyConstraint(
            ["wal_pos"],
            ["st_wal.pos"],
            name="fk_hipp_wal",
            ondelete="SET NULL",
        ),
    )

    # Create indexes for hippocampus event queries
    op.create_index("ix_st_hipp_wal_pos", "st_hipp_events", ["wal_pos"], unique=True)
    op.create_index("ix_st_hipp_tenant_space", "st_hipp_events", ["tenant_id", "space_id"])
    op.create_index("ix_st_hipp_topic", "st_hipp_events", ["topic"])
    op.create_index("ix_st_hipp_created", "st_hipp_events", ["created_at"])
    op.create_index("ix_st_hipp_event_time", "st_hipp_events", ["event_time_utc"])
    op.create_index("ix_st_hipp_embedding_id", "st_hipp_events", ["embedding_id"], unique=True)
    op.create_index("ix_st_hipp_cluster", "st_hipp_events", ["episode_cluster_id"])
    op.create_index("ix_st_hipp_geohash", "st_hipp_events", ["geohash_6"])
    op.create_index("ix_st_hipp_activity", "st_hipp_events", ["activity_type"])


def downgrade() -> None:
    """Drop st_hipp_events table and all indexes."""
    op.drop_index("ix_st_hipp_activity", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_geohash", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_cluster", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_embedding_id", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_event_time", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_created", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_topic", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_tenant_space", table_name="st_hipp_events")
    op.drop_index("ix_st_hipp_wal_pos", table_name="st_hipp_events")
    op.drop_table("st_hipp_events")
