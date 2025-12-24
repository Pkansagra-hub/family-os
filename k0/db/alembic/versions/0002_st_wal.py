"""Create st_wal table (Write-Ahead Log).

Revision ID: 0002
Revises: 0001
Create Date: 2024-12-23

K0 PostgreSQL Migration - Nuclear Reset
Matches SQLite schema exactly from k0_kernel_export.db

SQLite Schema:
CREATE TABLE st_wal (
  pos INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  body BLOB,
  payload_sha256 TEXT,
  schema_uri TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  idem_key TEXT,
  device_id TEXT NOT NULL,
  commit_ts TEXT NOT NULL,
  redacted_body_json TEXT,
  envelope_id TEXT,
  content_type TEXT,
  encryption_scheme TEXT,
  envelope_sha256 TEXT,
  ingested_at TEXT,
  clock_skew_ms INTEGER,
  policy_stamp_json TEXT DEFAULT NULL,
  location_geohash TEXT DEFAULT NULL,
  location_precision_m INTEGER DEFAULT NULL
);
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0002"
down_revision: str = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_wal table matching SQLite schema."""
    op.create_table(
        "st_wal",
        # Primary key - auto-incrementing position
        sa.Column("pos", sa.BigInteger, primary_key=True, autoincrement=True),
        # Tenant/space isolation
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("space_id", sa.Text, nullable=False),
        # Event metadata
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("envelope_json", sa.Text, nullable=False),
        sa.Column("body", sa.LargeBinary, nullable=True),
        # Content hashes
        sa.Column("payload_sha256", sa.Text, nullable=True),
        # Schema tracking - NOT NULL per SQLite
        sa.Column("schema_uri", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Text, nullable=False),
        # Idempotency
        sa.Column("idem_key", sa.Text, nullable=True),
        # Device tracking - NOT NULL per SQLite
        sa.Column("device_id", sa.Text, nullable=False),
        # Timestamps as TEXT (ISO8601 strings) per SQLite
        sa.Column("commit_ts", sa.Text, nullable=False),
        # Redaction support
        sa.Column("redacted_body_json", sa.Text, nullable=True),
        # Envelope metadata
        sa.Column("envelope_id", sa.Text, nullable=True),
        sa.Column("content_type", sa.Text, nullable=True),
        sa.Column("encryption_scheme", sa.Text, nullable=True),
        sa.Column("envelope_sha256", sa.Text, nullable=True),
        sa.Column("ingested_at", sa.Text, nullable=True),
        sa.Column("clock_skew_ms", sa.Integer, nullable=True),
        # Policy
        sa.Column("policy_stamp_json", sa.Text, nullable=True),
        # Location (optional)
        sa.Column("location_geohash", sa.Text, nullable=True),
        sa.Column("location_precision_m", sa.Integer, nullable=True),
    )

    # Create indexes matching SQLite
    op.create_index("idx_wal_space_pos", "st_wal", ["space_id", "pos"])
    op.create_index("idx_wal_tenant_topic", "st_wal", ["tenant_id", "topic", "pos"])
    op.create_index("idx_wal_envelope_id", "st_wal", ["envelope_id"])
    op.create_index("idx_wal_encryption", "st_wal", ["encryption_scheme", "commit_ts"])
    op.create_index(
        "idx_wal_envelope_sha256",
        "st_wal",
        ["envelope_sha256"],
        unique=True,
        postgresql_where=sa.text("envelope_sha256 IS NOT NULL"),
    )
    op.create_index("idx_wal_ingested_at", "st_wal", ["ingested_at"])
    op.create_index("idx_wal_clock_skew", "st_wal", ["clock_skew_ms"])
    op.create_index(
        "idx_st_wal_policy_stamp",
        "st_wal",
        ["tenant_id", "space_id", "policy_stamp_json"],
        postgresql_where=sa.text("policy_stamp_json IS NOT NULL"),
    )
    op.create_index(
        "idx_st_wal_location_geohash",
        "st_wal",
        ["location_geohash"],
        postgresql_where=sa.text("location_geohash IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop st_wal table and all indexes."""
    op.drop_index("idx_st_wal_location_geohash", table_name="st_wal")
    op.drop_index("idx_st_wal_policy_stamp", table_name="st_wal")
    op.drop_index("idx_wal_clock_skew", table_name="st_wal")
    op.drop_index("idx_wal_ingested_at", table_name="st_wal")
    op.drop_index("idx_wal_envelope_sha256", table_name="st_wal")
    op.drop_index("idx_wal_encryption", table_name="st_wal")
    op.drop_index("idx_wal_envelope_id", table_name="st_wal")
    op.drop_index("idx_wal_tenant_topic", table_name="st_wal")
    op.drop_index("idx_wal_space_pos", table_name="st_wal")
    op.drop_table("st_wal")
