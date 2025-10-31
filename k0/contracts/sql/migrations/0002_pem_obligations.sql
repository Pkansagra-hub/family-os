-- Migration 0002: Introduce PEM obligation persistence structures.
-- KEEP IN SYNC with ../storage.sql and k0/README.md §6.1.
-- Forward-compatible: new column defaults to NULL; existing WAL rows remain valid.
-- Backward-compatible: column addition guarded; obligation log table created only if absent.

BEGIN;

ALTER TABLE st_wal
  ADD COLUMN redacted_body_json TEXT;

ALTER TABLE st_receipts
  ADD COLUMN manifest_fingerprint TEXT;

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

COMMIT;
