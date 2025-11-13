-- K0 Kernel storage contract (baseline schema)
-- This file mirrors the authoritative DDL defined in k0/README.md §6.1.
-- Any changes here MUST be reflected in the narrative spec and migration manifests.
--
-- MIGRATION HISTORY:
-- 0001_baseline.sql - Core K0 infrastructure (WAL, receipts, outbox, DLQ, devices, schemas)
-- 0002_pem_obligations.sql - PEM obligation persistence (st_obligation_log, redacted_body_json)
-- 0003_fts_table.sql - FTS5 virtual table for WAL content search (st_fts)
-- 0004_future_proof_enhancements.sql - ACL, retention policies, FTS5 memory tables, backoff state
--
-- To apply migrations: python -m k0.automation.migrate <db_path>

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=OFF; -- Invariants enforced via Ward harness per CORRECTNESS.md

-- WAL (append-only)
CREATE TABLE IF NOT EXISTS st_wal (
  pos INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  body BLOB,
  redacted_body_json TEXT,
  payload_sha256 TEXT,
  schema_uri TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  idem_key TEXT,
  device_id TEXT NOT NULL,
  commit_ts TEXT NOT NULL
);

-- Idempotency ledger
CREATE TABLE IF NOT EXISTS idem_ledger (
  idem_key TEXT PRIMARY KEY,
  receipt_id TEXT NOT NULL,
  first_seen_ts TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('COMMITTED','REJECTED')),
  expiry_ts TEXT
);

-- Receipts
CREATE TABLE IF NOT EXISTS st_receipts (
  receipt_id TEXT PRIMARY KEY,
  idem_key TEXT NOT NULL,
  wal_pos INTEGER NOT NULL,
  commit_ts TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  mls_group_id TEXT NOT NULL,
  key_version TEXT NOT NULL,
  device_sig TEXT NOT NULL,
  manifest_fingerprint TEXT
);

-- Offsets (per topic/subscriber)
CREATE TABLE IF NOT EXISTS st_offsets (
  subscriber_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  space_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  offset INTEGER NOT NULL,
  updated_ts TEXT NOT NULL,
  PRIMARY KEY(subscriber_id, topic, space_id, tenant_id)
);

-- Provisioned devices ledger (device bindings only)
CREATE TABLE IF NOT EXISTS st_devices (
  device_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  mls_group_id TEXT NOT NULL,
  provisioned_ts TEXT NOT NULL
);

-- Device keys with rotation support (ADR 001)
CREATE TABLE IF NOT EXISTS st_device_keys (
  device_id TEXT NOT NULL,
  key_version TEXT NOT NULL,
  verify_key TEXT NOT NULL,
  key_state TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK(key_state IN ('PENDING','ACTIVE','ROTATING','REVOKED')),
  registered_ts TEXT NOT NULL,
  activated_ts TEXT,
  rotated_ts TEXT,
  revoked_ts TEXT,
  grace_expires_ts TEXT,
  revocation_reason TEXT,
  PRIMARY KEY(device_id, key_version),
  FOREIGN KEY(device_id) REFERENCES st_devices(device_id)
);

-- Outbox (async intents)
CREATE TABLE IF NOT EXISTS st_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
  payload BLOB NOT NULL,
  fingerprint TEXT NOT NULL,
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  retries INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS st_dlq (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  payload BLOB NOT NULL,
  reason TEXT NOT NULL,
  retries INTEGER NOT NULL DEFAULT 0,
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  first_failure_ts TEXT NOT NULL,
  last_failure_ts TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING'
    CHECK(state IN ('PENDING','REQUEUED','QUARANTINED'))
);

-- Schema registry with audit trail (ADR 002)
CREATE TABLE IF NOT EXISTS schema_registry (
  schema_uri TEXT NOT NULL,
  version TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('REGISTERED','ACTIVE','DEPRECATED','BLOCKED')),
  operator_id TEXT,
  blocked_ts TEXT,
  blocked_reason TEXT,
  unblocked_ts TEXT,
  PRIMARY KEY(schema_uri, version)
);

-- Indexes
DROP INDEX IF EXISTS idx_outbox_fingerprint_space;
CREATE INDEX IF NOT EXISTS idx_wal_space_pos ON st_wal(space_id, pos);
CREATE INDEX IF NOT EXISTS idx_wal_tenant_topic ON st_wal(tenant_id, topic, pos);
CREATE INDEX IF NOT EXISTS idx_receipts_space ON st_receipts(space_id, wal_pos);
CREATE INDEX IF NOT EXISTS idx_receipts_walpos ON st_receipts(wal_pos);
CREATE INDEX IF NOT EXISTS idx_receipts_manifest ON st_receipts(manifest_fingerprint);
CREATE INDEX IF NOT EXISTS idx_outbox_space ON st_outbox(space_id, requeue_seq, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_idem ON st_outbox(tenant_id, space_id, driver, fingerprint, requeue_seq);
CREATE INDEX IF NOT EXISTS idx_dlq_space ON st_dlq(space_id, first_failure_ts);
CREATE INDEX IF NOT EXISTS idx_device_keys_state ON st_device_keys(device_id, key_state);

CREATE TABLE IF NOT EXISTS st_obligation_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  obligation TEXT NOT NULL,
  details_json TEXT,
  commit_ts TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  FOREIGN KEY(wal_pos) REFERENCES st_wal(pos)
);

CREATE INDEX IF NOT EXISTS idx_obligation_log_wal ON st_obligation_log(wal_pos);
CREATE INDEX IF NOT EXISTS idx_obligation_log_tenant_space ON st_obligation_log(tenant_id, space_id, commit_ts);
