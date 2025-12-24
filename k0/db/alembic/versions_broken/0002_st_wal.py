"""Create st_wal table (Write-Ahead Log).

Revision ID: 0002
Revises: 0001
Create Date: 2024-12-23

Part of K0 PostgreSQL Migration (Milestone 2.1.1 - Issue 2.1.1.1)

The st_wal table is the core event store for K0 kernel.
It stores all ingested envelopes with full audit trail.

Columns: 22
Indexes: 9
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0002"
down_revision: str = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_wal table with all columns and indexes."""
    op.create_table(
        "st_wal",
        # Primary key - auto-incrementing position
        sa.Column("pos", sa.BigInteger, primary_key=True, autoincrement=True),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        # Event metadata
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("envelope_json", postgresql.JSONB, nullable=False),
        sa.Column("body", sa.LargeBinary, nullable=True),
        # Content hashes
        sa.Column("payload_sha256", sa.String(64), nullable=True),
        sa.Column("envelope_sha256", sa.String(64), nullable=True),
        # Schema tracking
        sa.Column("schema_uri", sa.String(512), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=True),
        # Idempotency
        sa.Column("idem_key", sa.String(128), nullable=True),
        # Device tracking
        sa.Column("device_id", sa.String(64), nullable=True),
        # Timestamps
        sa.Column(
            "commit_ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("clock_skew_ms", sa.Integer, nullable=True),
        # Envelope metadata
        sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_type", sa.String(64), nullable=True),
        sa.Column("encryption_scheme", sa.String(32), nullable=True),
        # Redaction support
        sa.Column("redacted_body_json", postgresql.JSONB, nullable=True),
        # Policy
        sa.Column("policy_stamp_json", postgresql.JSONB, nullable=True),
        # Location (optional)
        sa.Column("location_geohash", sa.String(12), nullable=True),
        sa.Column("location_precision_m", sa.Float, nullable=True),
    )

    # Create indexes for common query patterns
    op.create_index("ix_st_wal_tenant_space", "st_wal", ["tenant_id", "space_id"])
    op.create_index("ix_st_wal_topic", "st_wal", ["topic"])
    op.create_index(
        "ix_st_wal_idem_key",
        "st_wal",
        ["idem_key"],
        unique=True,
        postgresql_where=sa.text("idem_key IS NOT NULL"),
    )
    op.create_index("ix_st_wal_device_id", "st_wal", ["device_id"])
    op.create_index("ix_st_wal_commit_ts", "st_wal", ["commit_ts"])
    op.create_index("ix_st_wal_envelope_id", "st_wal", ["envelope_id"])
    op.create_index("ix_st_wal_schema_uri", "st_wal", ["schema_uri"])
    op.create_index("ix_st_wal_payload_sha256", "st_wal", ["payload_sha256"])
    op.create_index("ix_st_wal_geohash", "st_wal", ["location_geohash"])


def downgrade() -> None:
    """Drop st_wal table and all indexes."""
    op.drop_index("ix_st_wal_geohash", table_name="st_wal")
    op.drop_index("ix_st_wal_payload_sha256", table_name="st_wal")
    op.drop_index("ix_st_wal_schema_uri", table_name="st_wal")
    op.drop_index("ix_st_wal_envelope_id", table_name="st_wal")
    op.drop_index("ix_st_wal_commit_ts", table_name="st_wal")
    op.drop_index("ix_st_wal_device_id", table_name="st_wal")
    op.drop_index("ix_st_wal_idem_key", table_name="st_wal")
    op.drop_index("ix_st_wal_topic", table_name="st_wal")
    op.drop_index("ix_st_wal_tenant_space", table_name="st_wal")
    op.drop_table("st_wal")
