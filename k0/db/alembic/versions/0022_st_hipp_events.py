"""Create st_hipp_events table (Hippocampus Events).

Revision ID: 0022
Revises: 0021
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite has ~80 columns for st_hipp_events table.
All INTEGER timestamps stay as BIGINT (Unix epoch milliseconds).
All TEXT ids stay as TEXT (not UUID).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0022"
down_revision: str = "0021"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_hipp_events table matching SQLite schema."""
    op.create_table(
        "st_hipp_events",
        # ============================================================
        # Identity & Trace (9 columns)
        # ============================================================
        sa.Column("event_id", sa.Text, primary_key=True),
        sa.Column("wal_pos", sa.BigInteger, nullable=False, unique=True),
        sa.Column("cognitive_trace_id", sa.Text, nullable=False),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("effective_space_id", sa.Text, nullable=True),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("uow_id", sa.Text, nullable=True),
        sa.Column("schema_version", sa.Text, nullable=False, server_default="1.0.0"),
        # ============================================================
        # Integrity & Audit (6 columns)
        # ============================================================
        sa.Column("envelope_sha256", sa.Text, nullable=False),
        sa.Column("sig_alg", sa.Text, nullable=False),
        sa.Column("sig_kid", sa.Text, nullable=False),
        sa.Column("idem_key", sa.Text, nullable=False),
        sa.Column("ingested_at", sa.BigInteger, nullable=False),
        sa.Column("clock_skew_ms", sa.Integer, nullable=True),
        # ============================================================
        # Policy & Visibility (10 columns)
        # ============================================================
        sa.Column("policy_decision", sa.Text, nullable=False),
        sa.Column("policy_band", sa.Text, nullable=False),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("obligations_json", sa.Text, nullable=True),
        sa.Column("visible_to_json", sa.Text, nullable=True),
        sa.Column("visibility_scope", sa.Text, nullable=True),
        sa.Column("owner_id", sa.Text, nullable=False),
        sa.Column("co_owners_json", sa.Text, nullable=True),
        sa.Column("retention_policy_id", sa.Text, nullable=False),
        sa.Column("retention_bucket", sa.Text, nullable=False),
        # ============================================================
        # Actor & Device (6 columns)
        # ============================================================
        sa.Column("actor_id", sa.Text, nullable=False),
        sa.Column("actor_role", sa.Text, nullable=True),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("device_kind", sa.Text, nullable=False),
        sa.Column("device_os", sa.Text, nullable=True),
        sa.Column("ingress_channel", sa.Text, nullable=True),
        # ============================================================
        # Temporal (11 columns)
        # ============================================================
        sa.Column("event_time_utc", sa.BigInteger, nullable=False),
        sa.Column("write_time_utc", sa.BigInteger, nullable=False),
        sa.Column("write_lag_ms", sa.Integer, nullable=True),
        sa.Column("local_date", sa.Text, nullable=True),
        sa.Column("local_time", sa.Text, nullable=True),
        sa.Column("day_of_week", sa.Text, nullable=True),
        sa.Column("is_weekend", sa.Boolean, nullable=True),
        sa.Column("time_of_day_bucket", sa.Text, nullable=True),
        sa.Column("circadian_slot", sa.Text, nullable=True),
        sa.Column("is_backdated", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        # ============================================================
        # Spatial & Place (5 columns)
        # ============================================================
        sa.Column("location_name", sa.Text, nullable=True),
        sa.Column("location_type", sa.Text, nullable=True),
        sa.Column("geohash_6", sa.Text, nullable=True),
        sa.Column("geo_precision_external", sa.Text, nullable=True),
        sa.Column("geo_masking_reason", sa.Text, nullable=True),
        # ============================================================
        # Social & Relationships (8 columns)
        # ============================================================
        sa.Column("participants_json", sa.Text, nullable=True),
        sa.Column("num_participants", sa.Integer, nullable=True),
        sa.Column("has_partner_present", sa.Boolean, nullable=True),
        sa.Column("has_parent_present", sa.Boolean, nullable=True),
        sa.Column("is_solo_event", sa.Boolean, nullable=True),
        sa.Column("participant_roles_json", sa.Text, nullable=True),
        sa.Column("social_context", sa.Text, nullable=True),
        sa.Column("social_intimacy", sa.Text, nullable=True),
        # ============================================================
        # Semantic & Activity (10 columns)
        # ============================================================
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("text_normalized", sa.Text, nullable=True),
        sa.Column("char_count", sa.Integer, nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("language", sa.Text, nullable=True),
        sa.Column("activity_type", sa.Text, nullable=True),
        sa.Column("activity_category", sa.Text, nullable=True),
        sa.Column("is_meal", sa.Boolean, nullable=True),
        sa.Column("is_outing", sa.Boolean, nullable=True),
        sa.Column("ingress_source", sa.Text, nullable=True),
        # ============================================================
        # Hippocampus: Pattern Separation & Novelty (8 columns)
        # ============================================================
        sa.Column("simhash_hex", sa.Text, nullable=False),
        sa.Column("minhash32", sa.Text, nullable=False),
        sa.Column("novelty_score", sa.Float, nullable=True),
        sa.Column("near_duplicates_json", sa.Text, nullable=True),
        sa.Column("is_near_duplicate", sa.Boolean, nullable=True),
        sa.Column("episode_cluster_id", sa.Text, nullable=True),
        sa.Column("cluster_confidence", sa.Float, nullable=True),
        sa.Column("clustering_version", sa.Text, nullable=True),
        # ============================================================
        # Embeddings & Knowledge Graph (4 columns)
        # ============================================================
        sa.Column("embedding_id", sa.Text, nullable=False, unique=True),
        sa.Column("embedding_status", sa.Text, nullable=False, server_default="PENDING"),
        sa.Column("entities_json", sa.Text, nullable=True),
        sa.Column("kg_triples_json", sa.Text, nullable=True),
        # ============================================================
        # Affect & Salience (9 columns)
        # ============================================================
        sa.Column("sentiment_score", sa.Float, nullable=True),
        sa.Column("sentiment_label", sa.Text, nullable=True),
        sa.Column("dominant_emotions_json", sa.Text, nullable=True),
        sa.Column("affect_valence", sa.Float, nullable=True),
        sa.Column("affect_arousal", sa.Float, nullable=True),
        sa.Column("affect_band", sa.Text, nullable=True),
        sa.Column("salience_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("salience_reasons_json", sa.Text, nullable=True),
        sa.Column("salience_band", sa.Text, nullable=True),
        # ============================================================
        # Metadata & Versioning (4 columns)
        # ============================================================
        sa.Column("hippocampus_api_version", sa.Text, nullable=True),
        sa.Column("space_resolver_version", sa.Text, nullable=True),
        sa.Column("schema_uri", sa.Text, nullable=True),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        # ============================================================
        # CHECK constraints
        # ============================================================
        sa.CheckConstraint(
            "policy_decision IN ('ALLOW', 'DENY')",
            name="ck_hipp_policy_decision",
        ),
        sa.CheckConstraint(
            "policy_band IN ('GREEN', 'AMBER', 'RED')",
            name="ck_hipp_policy_band",
        ),
        sa.CheckConstraint(
            "visibility_scope IN ('OWNER_ONLY', 'SPACE_DEFAULT', 'HOUSEHOLD_ALL', 'CUSTOM_SUBSET', 'EXTERNAL_SHARE')",
            name="ck_hipp_visibility_scope",
        ),
        sa.CheckConstraint(
            "retention_bucket IN ('STANDARD', 'SENSITIVE', 'EPHEMERAL')",
            name="ck_hipp_retention_bucket",
        ),
        sa.CheckConstraint(
            "actor_role IN ('SELF', 'AGENT', 'SYSTEM', 'DELEGATE')",
            name="ck_hipp_actor_role",
        ),
        sa.CheckConstraint(
            "affect_band IN ('GREEN', 'AMBER', 'RED')",
            name="ck_hipp_affect_band",
        ),
        sa.CheckConstraint(
            "salience_band IN ('HIGH', 'MED', 'LOW')",
            name="ck_hipp_salience_band",
        ),
        sa.CheckConstraint(
            "embedding_status IN ('PENDING', 'IN_PROGRESS', 'READY', 'FAILED')",
            name="ck_hipp_embedding_status",
        ),
    )

    # ============================================================
    # Indexes matching SQLite
    # ============================================================
    op.create_index(
        "idx_hipp_events_tenant_time",
        "st_hipp_events",
        ["tenant_id", sa.text("event_time_utc DESC")],
    )
    op.create_index(
        "idx_hipp_events_space_time",
        "st_hipp_events",
        ["space_id", sa.text("event_time_utc DESC")],
    )
    op.create_index("idx_hipp_events_simhash", "st_hipp_events", ["simhash_hex"])
    op.create_index("idx_hipp_events_embedding_id", "st_hipp_events", ["embedding_id"])
    op.create_index(
        "idx_hipp_events_band_time",
        "st_hipp_events",
        ["policy_band", sa.text("event_time_utc DESC")],
    )
    op.create_index(
        "idx_hipp_events_cluster_id",
        "st_hipp_events",
        ["episode_cluster_id"],
        postgresql_where=sa.text("episode_cluster_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_hipp_events table and all indexes."""
    op.drop_index("idx_hipp_events_cluster_id", table_name="st_hipp_events")
    op.drop_index("idx_hipp_events_band_time", table_name="st_hipp_events")
    op.drop_index("idx_hipp_events_embedding_id", table_name="st_hipp_events")
    op.drop_index("idx_hipp_events_simhash", table_name="st_hipp_events")
    op.drop_index("idx_hipp_events_space_time", table_name="st_hipp_events")
    op.drop_index("idx_hipp_events_tenant_time", table_name="st_hipp_events")
    op.drop_table("st_hipp_events")
