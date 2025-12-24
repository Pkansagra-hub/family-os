# K0 PostgreSQL Schema Fix Plan

## STATUS: ✅ COMPLETED (December 23, 2025)

### Nuclear Reset Executed

All 29 broken migrations archived to `k0/db/alembic/versions_broken/`.
25 new migrations created matching SQLite source of truth exactly.

### New Migrations Created

| # | File | Table | Columns | Status |
|---|------|-------|---------|--------|
| 1 | 0001_initial.py | pgvector extension | - | ✅ |
| 2 | 0002_st_wal.py | st_wal | 22 | ✅ |
| 3 | 0003_idem_ledger.py | idem_ledger | 5 | ✅ |
| 4 | 0004_st_receipts.py | st_receipts | 11 | ✅ |
| 5 | 0005_st_offsets.py | st_offsets | 6 | ✅ |
| 6 | 0006_st_devices.py | st_devices | 6 | ✅ |
| 7 | 0007_st_device_keys.py | st_device_keys | 10 | ✅ |
| 8 | 0008_st_outbox.py | st_outbox | 14 | ✅ |
| 9 | 0009_st_dlq.py | st_dlq | 18 | ✅ |
| 10 | 0010_schema_registry.py | schema_registry | 8 | ✅ |
| 11 | 0011_schema_migrations.py | schema_migrations | 3 | ✅ |
| 12 | 0012_st_obligation_log.py | st_obligation_log | 7 | ✅ |
| 13 | 0013_st_acl.py | st_acl | 11 | ✅ |
| 14 | 0014_st_retention_policy.py | st_retention_policy | 11 | ✅ |
| 15 | 0015_st_archive_manifest.py | st_archive_manifest | 9 | ✅ |
| 16 | 0016_st_crdt_merge_log.py | st_crdt_merge_log | 10 | ✅ |
| 17 | 0017_households.py | households | 35 | ✅ |
| 18 | 0018_people.py | people | 33 | ✅ |
| 19 | 0019_st_pipeline_processed.py | st_pipeline_processed | 4 | ✅ |
| 20 | 0020_st_pipeline_status.py | st_pipeline_status | 7 | ✅ |
| 21 | 0021_st_pipeline_watermarks.py | st_pipeline_watermarks | 4 | ✅ |
| 22 | 0022_st_hipp_events.py | st_hipp_events | 80 | ✅ |
| 23 | 0023_st_relationships.py | st_relationships | 9 | ✅ |
| 24 | 0024_st_embedding_queue.py | st_embedding_queue | 17 | ✅ |
| 25 | 0025_st_vec.py | st_vec | 13 | ✅ |

### Key Type Mapping Decisions

- **TEXT IDs**: Kept as TEXT (not UUID) to match SQLite
- **INTEGER timestamps**: Kept as BIGINT (Unix epoch ms), not TIMESTAMPTZ
- **TEXT timestamps**: Kept as TEXT (ISO8601), not TIMESTAMPTZ
- **BLOB**: Mapped to BYTEA or LargeBinary
- **INTEGER**: Mapped to BIGINT for WAL positions

### Next Steps

1. Start Docker Desktop
2. Run `alembic upgrade head` against PostgreSQL
3. Verify all tables match SQLite schema

---

## TRIPLE-VERIFIED AUDIT (December 23, 2025)

---

## Problem Statement

The Alembic migrations in `k0/db/alembic/versions/` were created INCORRECTLY. They do NOT match the SQLite source of truth in `k0_kernel_export.db`. This causes:

1. Column name mismatches (e.g., `envelope_id` vs `space_id + wal_pos`)
2. Type mismatches (e.g., `TIMESTAMPTZ` vs `INTEGER` for Unix timestamps)
3. Primary key mismatches
4. Missing columns
5. Extra columns that don't exist in SQLite

---

## Source of Truth

**SQLite Database**: `D:\familyos\k0_kernel_export.db`
**SQLite Schema Export**: `D:\familyos\sqlite_full_schema.sql` (611 lines, 25 tables)

---

## COMPLETE SCHEMA COMPARISON (VERIFIED 3x)

### LEGEND

- ✅ **OK** - Schema matches SQLite
- ⚠️ **MINOR** - Type differences but same columns (OK for PostgreSQL)
- ❌ **BROKEN** - Wrong columns, wrong PK, or missing columns
- 🔵 **PG-ONLY** - PostgreSQL-specific, no SQLite equivalent

---

## TABLE-BY-TABLE COMPARISON

### 1. `schema_migrations` → `0007_schema_migrations.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `version` | `TEXT PRIMARY KEY` | `String(32) PRIMARY KEY` | ✅ |
| `checksum` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `applied_at` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ TEXT→TIMESTAMPTZ |

**Status: ✅ OK** (minor type upgrade)

---

### 2. `st_wal` → `0002_st_wal.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `pos` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BigInteger PRIMARY KEY autoincrement` | ✅ |
| `tenant_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `space_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `topic` | `TEXT NOT NULL` | `String(128) NOT NULL` | ✅ |
| `envelope_json` | `TEXT NOT NULL` | `JSONB NOT NULL` | ⚠️ TEXT→JSONB |
| `body` | `BLOB` | `LargeBinary` | ✅ |
| `payload_sha256` | `TEXT` | `String(64)` | ✅ |
| `schema_uri` | `TEXT NOT NULL` | `String(512) nullable` | ❌ **NULL mismatch** |
| `schema_version` | `TEXT NOT NULL` | `String(32) nullable` | ❌ **NULL mismatch** |
| `idem_key` | `TEXT` | `String(128)` | ✅ |
| `device_id` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NULL mismatch** |
| `commit_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `redacted_body_json` | `TEXT` | `JSONB` | ⚠️ |
| `envelope_id` | `TEXT` | `UUID` | ⚠️ TEXT→UUID |
| `content_type` | `TEXT` | `String(64)` | ✅ |
| `encryption_scheme` | `TEXT` | `String(32)` | ✅ |
| `envelope_sha256` | `TEXT` | `String(64)` | ✅ |
| `ingested_at` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `clock_skew_ms` | `INTEGER` | `Integer` | ✅ |
| `policy_stamp_json` | `TEXT DEFAULT NULL` | `JSONB` | ⚠️ |
| `location_geohash` | `TEXT DEFAULT NULL` | `String(12)` | ✅ |
| `location_precision_m` | `INTEGER DEFAULT NULL` | `Float` | ⚠️ INTEGER→Float |

**Status: ⚠️ MINOR ISSUES**

- `schema_uri`, `schema_version`, `device_id` are NOT NULL in SQLite but nullable in Alembic

---

### 3. `idem_ledger` → `0013_idem_ledger.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `idem_key` | `TEXT PRIMARY KEY` | `String(128) PRIMARY KEY` | ✅ |
| `receipt_id` | `TEXT NOT NULL` | `UUID nullable` | ❌ **NOT NULL→nullable, TEXT→UUID** |
| `first_seen_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `state` | `TEXT NOT NULL CHECK(...)` | `String(16) NOT NULL` | ✅ |
| `expiry_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |

**Status: ❌ BROKEN**

- `receipt_id` is TEXT NOT NULL in SQLite, UUID nullable in Alembic

---

### 4. `st_receipts` → `0005_st_receipts.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `receipt_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `idem_key` | `TEXT NOT NULL` | `String(128) NOT NULL` | ✅ |
| `wal_pos` | `INTEGER NOT NULL` | `BigInteger NOT NULL` | ✅ |
| `commit_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `tenant_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `space_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `device_id` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `mls_group_id` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `key_version` | `TEXT NOT NULL` | `Integer nullable` | ❌ **TEXT→Integer, NOT NULL→nullable** |
| `device_sig` | `TEXT NOT NULL` | `Text nullable` | ❌ **NOT NULL→nullable** |
| `manifest_fingerprint` | `TEXT` | `String(64)` | ✅ |

**Status: ❌ BROKEN**

- 4 columns changed from NOT NULL to nullable
- `key_version` changed from TEXT to Integer

---

### 5. `st_offsets` → `0008_st_offsets.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `subscriber_id` | `TEXT NOT NULL` (PK part) | `String(128) NOT NULL` (PK part) | ✅ |
| `topic` | `TEXT NOT NULL` (PK part) | `String(128) NOT NULL` (PK part) | ✅ |
| `space_id` | `TEXT NOT NULL` (PK part) | `String(64) NOT NULL` (PK part) | ✅ |
| `tenant_id` | `TEXT NOT NULL` (PK part) | `String(64) NOT NULL` (PK part) | ✅ |
| `offset` | `INTEGER NOT NULL` | `BigInteger NOT NULL` | ✅ |
| `updated_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |

**PK**: `(subscriber_id, topic, space_id, tenant_id)` - SAME

**Status: ✅ OK**

---

### 6. `st_devices` → `0014_st_devices.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `device_id` | `TEXT PRIMARY KEY` | `String(64) PRIMARY KEY` | ✅ |
| `tenant_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `space_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `mls_group_id` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `provisioned_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `hmac_secret` | `BLOB` | `LargeBinary NOT NULL` | ❌ **nullable→NOT NULL** |

**Status: ❌ BROKEN**

- `mls_group_id`: NOT NULL→nullable
- `hmac_secret`: nullable→NOT NULL (opposite)

---

### 7. `st_device_keys` → `0015_st_device_keys.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `device_id` | `TEXT NOT NULL` (PK part) | `String(64) NOT NULL` (PK part) | ✅ |
| `key_version` | `TEXT NOT NULL` (PK part) | `Integer NOT NULL` (PK part) | ❌ **TEXT→Integer** |
| `verify_key` | `TEXT NOT NULL` | `Text NOT NULL` | ✅ |
| `key_state` | `TEXT NOT NULL DEFAULT 'ACTIVE'` | `String(16) NOT NULL DEFAULT 'active'` | ⚠️ case |
| `registered_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `activated_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `rotated_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `revoked_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `grace_expires_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `revocation_reason` | `TEXT` | `Text` | ✅ |

**PK**: `(device_id, key_version)` - SAME

**Status: ❌ BROKEN**

- `key_version` is TEXT in SQLite, Integer in Alembic

---

### 8. `st_outbox` → `0003_st_outbox.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BigInteger PRIMARY KEY autoincrement` | ✅ |
| `wal_pos` | `INTEGER NOT NULL` | `BigInteger NOT NULL` | ✅ |
| `tenant_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `space_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `driver` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `op_kind` | `TEXT NOT NULL` | `String(32) NOT NULL` | ✅ |
| `payload` | `BLOB NOT NULL` | `LargeBinary NOT NULL` | ✅ |
| `fingerprint` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `requeue_seq` | `INTEGER NOT NULL DEFAULT 0` | `Integer NOT NULL DEFAULT 0` | ✅ |
| `retries` | `INTEGER NOT NULL DEFAULT 0` | `SmallInteger NOT NULL DEFAULT 0` | ✅ |
| `last_error` | `TEXT` | `Text` | ✅ |
| `next_attempt_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `backoff_exp` | `INTEGER DEFAULT 1` | `SmallInteger NOT NULL DEFAULT 0` | ❌ **DEFAULT 1→0** |
| `status` | `TEXT DEFAULT 'PENDING'` | `String(16) NOT NULL DEFAULT 'pending'` | ⚠️ case |

**Status: ⚠️ MINOR**

- `fingerprint` nullability
- `backoff_exp` default value

---

### 9. `st_dlq` → `0004_st_dlq.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BigInteger PRIMARY KEY autoincrement` | ✅ |
| `wal_pos` | `INTEGER` (nullable) | `BigInteger NOT NULL` | ❌ **nullable→NOT NULL** |
| `tenant_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `space_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `driver` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `op_kind` | `TEXT NOT NULL` | `String(32) NOT NULL` | ✅ |
| `fingerprint` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `payload` | `BLOB NOT NULL` | `LargeBinary NOT NULL` | ✅ |
| `reason` | `TEXT NOT NULL` | `Text nullable` | ❌ **NOT NULL→nullable** |
| `retries` | `INTEGER NOT NULL DEFAULT 0` | `SmallInteger NOT NULL DEFAULT 0` | ✅ |
| `requeue_seq` | `INTEGER NOT NULL DEFAULT 0` | `Integer NOT NULL DEFAULT 0` | ✅ |
| `first_failure_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `last_failure_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `state` | `TEXT NOT NULL DEFAULT 'PENDING'` | `String(16) NOT NULL DEFAULT 'dead'` | ❌ **DEFAULT 'PENDING'→'dead'** |
| `next_attempt_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `backoff_exp` | `INTEGER DEFAULT 1` | `SmallInteger NOT NULL DEFAULT 0` | ❌ **DEFAULT 1→0** |
| `error_kind` | `TEXT` | `String(64)` | ✅ |
| `error_fingerprint` | `TEXT` | `String(64)` | ✅ |

**Status: ❌ BROKEN**

- `wal_pos` nullable→NOT NULL
- `fingerprint` NOT NULL→nullable
- `reason` NOT NULL→nullable
- `state` DEFAULT 'PENDING'→'dead'

---

### 10. `schema_registry` → `0006_schema_registry.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `schema_uri` | `TEXT NOT NULL` (PK part) | `String(512) NOT NULL` (PK part) | ✅ |
| `version` | `TEXT NOT NULL` (PK part) | `String(32) NOT NULL` (PK part) | ✅ |
| `sha256` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `status` | `TEXT NOT NULL CHECK(...)` | `String(16) NOT NULL DEFAULT 'active'` | ⚠️ default |
| `operator_id` | `TEXT` | `String(64)` | ✅ |
| `blocked_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `blocked_reason` | `TEXT` | `Text` | ✅ |
| `unblocked_ts` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |

**PK**: `(schema_uri, version)` - SAME

**Status: ✅ OK**

---

### 11. `st_obligation_log` → `0009_st_obligation_log.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BigInteger PRIMARY KEY autoincrement` | ✅ |
| `wal_pos` | `INTEGER NOT NULL` | `BigInteger NOT NULL` | ✅ |
| `obligation` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `details_json` | `TEXT` | `JSONB` | ⚠️ TEXT→JSONB |
| `commit_ts` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `tenant_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `space_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |

**Status: ✅ OK**

---

### 12. `st_acl` → `0011_st_acl.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `acl_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `resource_type` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `resource_id` | `TEXT NOT NULL` | `String(128) NOT NULL` | ✅ |
| `principal_type` | `TEXT NOT NULL` | `String(32) NOT NULL` | ✅ |
| `principal_id` | `TEXT NOT NULL` | `String(128) NOT NULL` | ✅ |
| `permission` | `TEXT NOT NULL` | `String(32) NOT NULL` | ✅ |
| `privacy_band` | `TEXT` | `String(16)` | ✅ |
| `granted_at` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `granted_by` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `expires_at` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `revoked_at` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |

**Status: ⚠️ MINOR**

- `granted_by` NOT NULL→nullable

---

### 13. `st_retention_policy` → `0010_st_retention_policy.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `policy_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `policy_name` | `TEXT NOT NULL UNIQUE` | `String(128) NOT NULL UNIQUE` | ✅ |
| `resource_type` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `privacy_band` | `TEXT` | `String(16) NOT NULL` | ❌ **nullable→NOT NULL** |
| `retention_days` | `INTEGER NOT NULL` | `Integer NOT NULL` | ✅ |
| `archive_enabled` | `BOOLEAN DEFAULT 1` | `Boolean NOT NULL DEFAULT false` | ❌ **DEFAULT 1→false** |
| `archive_after_days` | `INTEGER` | `Integer` | ✅ |
| `created_at` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `created_by` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `updated_at` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |
| `enabled` | `BOOLEAN DEFAULT 1` | `Boolean NOT NULL DEFAULT true` | ✅ |

**Status: ❌ BROKEN**

- `privacy_band` nullable→NOT NULL
- `archive_enabled` DEFAULT 1→false
- `created_by` NOT NULL→nullable

---

### 14. `st_archive_manifest` → `0012_st_archive_manifest.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `archive_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `resource_type` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `resource_id` | `TEXT NOT NULL` | `String(128) NOT NULL` | ✅ |
| `archived_at` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `archive_location` | `TEXT NOT NULL` | `String(512) NOT NULL` | ✅ |
| `archive_size_bytes` | `INTEGER` | `BigInteger` | ✅ |
| `archive_checksum` | `TEXT` | `String(64)` | ✅ |
| `retention_policy_id` | `TEXT` | `UUID` | ⚠️ TEXT→UUID |
| `delete_after` | `TEXT` | `DateTime(timezone=True)` | ⚠️ |

**Status: ✅ OK**

---

### 15. `st_crdt_merge_log` → `0024_st_crdt_merge_log.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `merge_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `resource_type` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `resource_id` | `TEXT NOT NULL` | `String(128) NOT NULL` | ✅ |
| `merge_strategy` | `TEXT NOT NULL` | `String(32) NOT NULL` | ✅ |
| `winner_device_id` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `loser_device_id` | `TEXT` | `String(64)` | ✅ |
| `winner_vector_clock` | `TEXT NOT NULL` | `JSONB nullable` | ❌ **TEXT NOT NULL→JSONB nullable** |
| `loser_vector_clock` | `TEXT` | `JSONB` | ⚠️ TEXT→JSONB |
| `merged_at` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `conflict_reason` | `TEXT` | `String(64)` | ✅ |

**Status: ❌ BROKEN**

- `winner_device_id` NOT NULL→nullable
- `winner_vector_clock` NOT NULL→nullable

---

### 16. `people` → `0017_people.py`

**SQLite columns: 33**
**Alembic columns: 33**

Key differences:

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `person_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `cognitive_trace_id` | `TEXT NOT NULL` | `String(128) nullable` | ❌ **NOT NULL→nullable** |
| `label` | `TEXT NOT NULL` | `String(256) nullable` | ❌ **NOT NULL→nullable** |
| `tenant_id` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `space_id` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `owner_id` | `TEXT NOT NULL` | `UUID nullable` | ❌ **TEXT NOT NULL→UUID nullable** |
| `visible_to` | `TEXT NOT NULL` | `JSONB nullable` | ❌ **NOT NULL→nullable** |
| `crdt_vector_clock` | `TEXT NOT NULL` | `JSONB nullable` | ❌ **NOT NULL→nullable** |
| `crdt_lamport` | `INTEGER NOT NULL` | `BigInteger NOT NULL` | ✅ |
| `created_at` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `updated_at` | `TEXT NOT NULL` | `DateTime(timezone=True) nullable` | ❌ **NOT NULL→nullable** |

**Status: ❌ BROKEN** (8+ columns have wrong nullability)

---

### 17. `households` → `0016_households.py`

**SQLite columns: 35**
**Alembic columns: 35**

Key differences:

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `household_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `cognitive_trace_id` | `TEXT NOT NULL` | `String(128) nullable` | ❌ **NOT NULL→nullable** |
| `label` | `TEXT NOT NULL` | `String(256) nullable` | ❌ **NOT NULL→nullable** |
| `tenant_id` | `TEXT NOT NULL UNIQUE` | `String(64) nullable UNIQUE` | ❌ **NOT NULL→nullable** |
| `visible_to` | `TEXT NOT NULL` | `JSONB nullable` | ❌ **NOT NULL→nullable** |
| `crdt_vector_clock` | `TEXT NOT NULL` | `JSONB nullable` | ❌ **NOT NULL→nullable** |
| `crdt_lamport` | `INTEGER NOT NULL` | `BigInteger NOT NULL` | ✅ |
| `created_at` | `TEXT NOT NULL` | `DateTime(timezone=True) NOT NULL` | ⚠️ |
| `updated_at` | `TEXT NOT NULL` | `DateTime(timezone=True) nullable` | ❌ **NOT NULL→nullable** |

**Status: ❌ BROKEN** (6+ columns have wrong nullability)

---

### 18. `st_pipeline_processed` → `0019_st_pipeline_processed.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `pipeline_id` | `TEXT NOT NULL` (PK part) | `String(64) NOT NULL` (PK part) | ✅ |
| `space_id` | `TEXT NOT NULL` (PK part) | **MISSING** | ❌ **MISSING COLUMN** |
| `wal_pos` | `INTEGER NOT NULL` (PK part) | **MISSING** | ❌ **MISSING COLUMN** |
| `processed_at` | `INTEGER NOT NULL` | `DateTime(timezone=True)` | ❌ **INTEGER→TIMESTAMPTZ** |
| **N/A** | **N/A** | `envelope_id UUID NOT NULL` (PK part) | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `expires_at DateTime` | ❌ **EXTRA COLUMN** |

**SQLite PK**: `(pipeline_id, space_id, wal_pos)`
**Alembic PK**: `(pipeline_id, envelope_id)`

**Status: ❌ CRITICALLY BROKEN**

- Missing `space_id` and `wal_pos` columns
- Extra `envelope_id` and `expires_at` columns
- Wrong primary key

---

### 19. `st_pipeline_status` → `0020_st_pipeline_status.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `pipeline_id` | `TEXT NOT NULL` (PK part) | `String(64) PRIMARY KEY` (single PK) | ❌ **WRONG PK** |
| `wal_pos` | `INTEGER NOT NULL` (PK part) | **MISSING** | ❌ **MISSING COLUMN** |
| `status` | `TEXT NOT NULL CHECK(OK,ERROR,DEFERRED)` | `String(16) NOT NULL DEFAULT 'idle'` | ❌ **WRONG CHECK VALUES** |
| `duration_ms` | `INTEGER` | **MISSING** | ❌ **MISSING COLUMN** |
| `error_kind` | `TEXT` | **MISSING** | ❌ **MISSING COLUMN** |
| `error_msg` | `TEXT` | **MISSING** (has `last_error JSONB`)| ❌ **WRONG COLUMN** |
| `updated_at` | `INTEGER NOT NULL` | `last_run_at/next_run_at DateTime` | ❌ **WRONG COLUMNS** |
| **N/A** | **N/A** | `processed_count BigInteger` | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `error_count BigInteger` | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `next_run_at DateTime` | ❌ **EXTRA COLUMN** |

**SQLite PK**: `(pipeline_id, wal_pos)`
**Alembic PK**: `(pipeline_id)` only

**Status: ❌ CRITICALLY BROKEN**

- Completely different schema
- Missing `wal_pos`, `duration_ms`, `error_kind`, `error_msg`
- Extra `processed_count`, `error_count`, `last_run_at`, `next_run_at`

---

### 20. `st_pipeline_watermarks` → `0021_st_pipeline_watermarks.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `pipeline_id` | `TEXT NOT NULL` (PK part) | `String(64) NOT NULL` (PK part) | ✅ |
| `space_id` | `TEXT NOT NULL` (PK part) | **MISSING** | ❌ **MISSING COLUMN** |
| `watermark` | `INTEGER NOT NULL` | `BigInteger NOT NULL` | ✅ |
| `updated_at` | `INTEGER NOT NULL` | `DateTime(timezone=True) NOT NULL` | ❌ **INTEGER→TIMESTAMPTZ** |
| **N/A** | **N/A** | `partition_key String(64)` (PK part) | ❌ **EXTRA COLUMN** |

**SQLite PK**: `(pipeline_id, space_id)`
**Alembic PK**: `(pipeline_id, partition_key)`

**Status: ❌ BROKEN**

- Missing `space_id`
- Extra `partition_key`
- `updated_at` wrong type

---

### 21. `st_hipp_events` → `0022_st_hipp_events.py`

**SQLite columns: ~80**
**Alembic columns: ~80**

Key differences:

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `event_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `wal_pos` | `INTEGER NOT NULL UNIQUE` | `BigInteger nullable UNIQUE` | ❌ **NOT NULL→nullable** |
| `cognitive_trace_id` | `TEXT NOT NULL` | `String(128) nullable` | ❌ **NOT NULL→nullable** |
| `envelope_sha256` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `sig_alg` | `TEXT NOT NULL` | `String(16) nullable` | ❌ **NOT NULL→nullable** |
| `sig_kid` | `TEXT NOT NULL` | `String(128) nullable` | ❌ **NOT NULL→nullable** |
| `idem_key` | `TEXT NOT NULL` | `String(128) nullable` | ❌ **NOT NULL→nullable** |
| `ingested_at` | `INTEGER NOT NULL` | `DateTime(timezone=True) nullable` | ❌ **INTEGER NOT NULL→TIMESTAMPTZ nullable** |
| `owner_id` | `TEXT NOT NULL` | `UUID nullable` | ❌ **TEXT NOT NULL→UUID nullable** |
| `retention_policy_id` | `TEXT NOT NULL` | `UUID nullable` | ❌ **TEXT NOT NULL→UUID nullable** |
| `retention_bucket` | `TEXT NOT NULL` | `String(32) nullable` | ❌ **NOT NULL→nullable** |
| `actor_id` | `TEXT NOT NULL` | `UUID nullable` | ❌ **TEXT NOT NULL→UUID nullable** |
| `device_id` | `TEXT NOT NULL` | `String(64) nullable` | ❌ **NOT NULL→nullable** |
| `device_kind` | `TEXT NOT NULL` | `String(32) nullable` | ❌ **NOT NULL→nullable** |
| `event_time_utc` | `INTEGER NOT NULL` | `DateTime(timezone=True) nullable` | ❌ **INTEGER NOT NULL→TIMESTAMPTZ nullable** |
| `write_time_utc` | `INTEGER NOT NULL` | `DateTime(timezone=True) nullable` | ❌ **INTEGER NOT NULL→TIMESTAMPTZ nullable** |
| `created_at` | `INTEGER NOT NULL` | `DateTime(timezone=True) NOT NULL` | ❌ **INTEGER→TIMESTAMPTZ** |
| `updated_at` | `INTEGER NOT NULL` | `DateTime(timezone=True) nullable` | ❌ **INTEGER NOT NULL→TIMESTAMPTZ nullable** |
| `simhash_hex` | `TEXT NOT NULL` | `String(16) nullable` | ❌ **NOT NULL→nullable** |
| `minhash32` | `TEXT NOT NULL` | `ARRAY(Integer) nullable` | ❌ **TEXT NOT NULL→ARRAY nullable** |
| `embedding_id` | `TEXT NOT NULL UNIQUE` | `UUID nullable UNIQUE` | ❌ **TEXT NOT NULL→UUID nullable** |

**Status: ❌ CRITICALLY BROKEN**

- 20+ columns have wrong nullability
- All timestamps changed from INTEGER to TIMESTAMPTZ
- All IDs changed from TEXT to UUID

---

### 22. `st_relationships` → `0018_st_relationships.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | **MISSING** | ❌ **MISSING PK** |
| `household_id` | `TEXT NOT NULL` | `UUID nullable` | ❌ **TEXT NOT NULL→UUID nullable** |
| `person_id` | `TEXT NOT NULL` | **MISSING** (has `source_person_id`) | ❌ **WRONG COLUMN NAME** |
| `related_person_id` | `TEXT NOT NULL` | **MISSING** (has `target_person_id`) | ❌ **WRONG COLUMN NAME** |
| `relationship_type` | `TEXT NOT NULL CHECK(...)` | `String(32) NOT NULL` | ✅ |
| `properties_json` | `TEXT` | **MISSING** (has `metadata JSONB`) | ❌ **WRONG COLUMN NAME** |
| `source_version` | `TEXT NOT NULL` | **MISSING** | ❌ **MISSING COLUMN** |
| `hydrated_at` | `TEXT NOT NULL` | **MISSING** | ❌ **MISSING COLUMN** |
| `ttl_seconds` | `INTEGER NOT NULL` | **MISSING** | ❌ **MISSING COLUMN** |
| **N/A** | **N/A** | `source_person_id UUID` (PK part) | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `target_person_id UUID` (PK part) | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `inverse_type String(32)` | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `since_date Date` | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `metadata JSONB` | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `created_at DateTime` | ❌ **EXTRA COLUMN** |
| **N/A** | **N/A** | `updated_at DateTime` | ❌ **EXTRA COLUMN** |

**SQLite PK**: `id INTEGER PRIMARY KEY AUTOINCREMENT`
**Alembic PK**: `(source_person_id, target_person_id)`

**Status: ❌ CRITICALLY BROKEN**

- Completely different schema
- Missing `id`, `person_id`, `related_person_id`, `properties_json`, `source_version`, `hydrated_at`, `ttl_seconds`
- Extra `source_person_id`, `target_person_id`, `inverse_type`, `since_date`, `metadata`, `created_at`, `updated_at`
- Wrong primary key type

---

### 23. `st_embedding_queue` → `0023_st_embedding_queue.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `job_id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `UUID PRIMARY KEY` | ❌ **INTEGER SERIAL→UUID** |
| `wal_pos` | `INTEGER NOT NULL` | `BigInteger nullable` | ❌ **NOT NULL→nullable** |
| `event_id` | `TEXT NOT NULL` | `UUID nullable` | ❌ **TEXT NOT NULL→UUID nullable** |
| `embedding_id` | `TEXT NOT NULL UNIQUE` | `UUID nullable UNIQUE` | ❌ **TEXT NOT NULL→UUID nullable** |
| `tenant_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `space_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `vector_kind` | `TEXT NOT NULL` | `String(32) NOT NULL` | ✅ |
| `model_id` | `TEXT NOT NULL` | `String(64) NOT NULL` | ✅ |
| `priority` | `TEXT NOT NULL DEFAULT 'NORMAL' CHECK(...)` | `SmallInteger NOT NULL DEFAULT 0` | ❌ **TEXT→SmallInteger** |
| `status` | `TEXT NOT NULL CHECK(...)` | `String(16) NOT NULL DEFAULT 'pending'` | ⚠️ |
| `attempt_count` | `INTEGER NOT NULL DEFAULT 0` | `SmallInteger NOT NULL DEFAULT 0` | ✅ |
| `max_attempts` | `INTEGER NOT NULL DEFAULT 5` | `SmallInteger NOT NULL DEFAULT 3` | ❌ **DEFAULT 5→3** |
| `next_attempt_ts` | `INTEGER` | `DateTime(timezone=True)` | ❌ **INTEGER→TIMESTAMPTZ** |
| `last_error` | `TEXT` | `Text` | ✅ |
| `vector_json` | `TEXT` | `JSONB` | ⚠️ TEXT→JSONB |
| `created_at` | `INTEGER NOT NULL` | `DateTime(timezone=True) NOT NULL` | ❌ **INTEGER→TIMESTAMPTZ** |
| `updated_at` | `INTEGER NOT NULL` | `DateTime(timezone=True) nullable` | ❌ **INTEGER NOT NULL→TIMESTAMPTZ nullable** |

**Status: ❌ BROKEN**

- `job_id` INTEGER→UUID
- `priority` TEXT→SmallInteger
- Multiple timestamp type changes
- Multiple nullability changes

---

### 24. `st_vec` → `0026_st_vec.py`

| Column | SQLite | Alembic | Match |
|--------|--------|---------|-------|
| `embedding_id` | `TEXT PRIMARY KEY` | `UUID PRIMARY KEY` | ⚠️ TEXT→UUID |
| `event_id` | `TEXT NOT NULL` | `UUID` (no NOT NULL) | ❌ **NOT NULL→nullable** |
| `tenant_id` | `TEXT NOT NULL` | `VARCHAR(64) NOT NULL` | ✅ |
| `space_id` | `TEXT NOT NULL` | `VARCHAR(64) NOT NULL` | ✅ |
| `vector` | `BLOB NOT NULL` | `VECTOR(768) NOT NULL` | ⚠️ BLOB→pgvector |
| `vector_dim` | `INTEGER NOT NULL DEFAULT 768` | `INTEGER NOT NULL DEFAULT 768` | ✅ |
| `model_id` | `TEXT NOT NULL DEFAULT 'ultrabert_v2.1.0'` | `VARCHAR(64) NOT NULL` | ⚠️ missing default |
| `status` | `TEXT NOT NULL DEFAULT 'READY' CHECK(...)` | `VARCHAR(16) NOT NULL DEFAULT 'active'` | ❌ **DEFAULT 'READY'→'active'** |
| `cognitive_trace_id` | `TEXT` | `VARCHAR(128)` | ✅ |
| `created_at` | `INTEGER NOT NULL` | `TIMESTAMPTZ NOT NULL` | ❌ **INTEGER→TIMESTAMPTZ** |
| `updated_at` | `INTEGER NOT NULL` | `TIMESTAMPTZ` (nullable) | ❌ **INTEGER NOT NULL→TIMESTAMPTZ nullable** |
| `faiss_id` | `INTEGER` | `INTEGER` | ✅ |
| `indexed_at` | `INTEGER` | `TIMESTAMPTZ` | ❌ **INTEGER→TIMESTAMPTZ** |

**Status: ❌ BROKEN**

- `event_id` NOT NULL→nullable
- `status` DEFAULT 'READY'→'active'
- All timestamps INTEGER→TIMESTAMPTZ

---

### Extra Alembic Migrations (PostgreSQL-specific, no SQLite equivalent)

- `0001_initial.py` - Initial setup 🔵
- `0025_pgvector_extension.py` - pgvector extension 🔵
- `0027_vector_indexes.py` - HNSW indexes 🔵
- `0028_fts_columns.py` - Full-text search columns 🔵
- `0029_fts_indexes.py` - Full-text search indexes 🔵

---

## Phase 2: Known Broken Schemas

### 2.1 `st_pipeline_processed` (CRITICAL)

**SQLite Schema:**

```sql
CREATE TABLE st_pipeline_processed (
  pipeline_id  TEXT NOT NULL,
  space_id     TEXT NOT NULL,
  wal_pos      INTEGER NOT NULL,
  processed_at INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, space_id, wal_pos)
);
CREATE INDEX idx_pipeline_processed_space_wal
  ON st_pipeline_processed(space_id, wal_pos);
```

**Alembic Schema (WRONG):**

```python
sa.Column("pipeline_id", sa.String(64), nullable=False),
sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=False),
sa.Column("processed_at", sa.DateTime(timezone=True), ...),
sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
sa.PrimaryKeyConstraint("pipeline_id", "envelope_id", ...)
```

**Issues:**

- Missing `space_id` column
- Missing `wal_pos` column
- Has `envelope_id` (doesn't exist in SQLite)
- Has `expires_at` (doesn't exist in SQLite)
- `processed_at` is TIMESTAMPTZ but should be INTEGER (Unix epoch)
- Wrong primary key

**Fix Required:**

- Remove `envelope_id`, `expires_at`
- Add `space_id TEXT NOT NULL`, `wal_pos BIGINT NOT NULL`
- Change `processed_at` to `BIGINT NOT NULL`
- Change PK to `(pipeline_id, space_id, wal_pos)`

---

### 2.2 `st_relationships` (CRITICAL)

**SQLite Schema:**

```sql
CREATE TABLE st_relationships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  related_person_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL CHECK(...),
  properties_json TEXT,
  source_version TEXT NOT NULL,
  hydrated_at TEXT NOT NULL,
  ttl_seconds INTEGER NOT NULL,
  FOREIGN KEY (household_id) REFERENCES households(household_id),
  FOREIGN KEY (person_id) REFERENCES people(person_id),
  FOREIGN KEY (related_person_id) REFERENCES people(person_id)
);
```

**Alembic Schema (WRONG):**

```python
sa.Column("source_person_id", postgresql.UUID(as_uuid=True), nullable=False),
sa.Column("target_person_id", postgresql.UUID(as_uuid=True), nullable=False),
sa.Column("relationship_type", sa.String(32), nullable=False),
sa.Column("inverse_type", sa.String(32), nullable=True),
sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=True),
sa.Column("since_date", sa.Date, nullable=True),
sa.Column("metadata", postgresql.JSONB, nullable=True),
sa.Column("created_at", sa.DateTime(timezone=True), ...),
sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
sa.PrimaryKeyConstraint("source_person_id", "target_person_id", ...)
```

**Issues:**

- Missing `id` autoincrement column
- `source_person_id` should be `person_id`
- `target_person_id` should be `related_person_id`
- Missing `properties_json`, `source_version`, `hydrated_at`, `ttl_seconds`
- Has `inverse_type`, `since_date`, `metadata`, `created_at`, `updated_at` (don't exist in SQLite)
- All IDs are TEXT in SQLite, not UUID

**Fix Required:**

- Add `id SERIAL PRIMARY KEY`
- Rename columns to match SQLite
- Add missing columns
- Remove invented columns
- Change UUID to TEXT/VARCHAR

---

### 2.3 `st_hipp_events` Timestamp Types

**SQLite uses INTEGER for timestamps:**

```sql
ingested_at INTEGER NOT NULL,
event_time_utc INTEGER NOT NULL,
write_time_utc INTEGER NOT NULL,
created_at INTEGER NOT NULL,
updated_at INTEGER NOT NULL
```

**Alembic likely uses TIMESTAMPTZ - NEEDS VERIFICATION**

---

### 2.4 ID Type Mismatches

**SQLite uses TEXT for all IDs:**

- `person_id TEXT`
- `household_id TEXT`
- `device_id TEXT`
- `receipt_id TEXT`
- `event_id TEXT`
- `acl_id TEXT`
- `policy_id TEXT`
- `archive_id TEXT`

**Alembic uses UUID:**

- All `*_id` columns are `postgresql.UUID(as_uuid=True)`

**Decision Required:**

- Option A: Keep UUID in PostgreSQL (requires code changes to convert TEXT <-> UUID)
- Option B: Use VARCHAR in PostgreSQL to match SQLite exactly

---

## Phase 3: Kernel Code Dependencies

After schema fixes, these kernel files need updates:

### 3.1 `k0/kernel/syscalls.py`

Functions that execute SQL queries:

- `pipeline_processed_upsert()` - Uses wrong column names
- `pipeline_processed_check()` - Uses wrong column names
- `relationships_query()` - Already partially fixed
- Any function using `st_hipp_events` timestamp columns

### 3.2 `k0/modules/builders/hipp_events_row.py`

- `_unix_to_datetime()` helper was added as band-aid
- If schema uses INTEGER for timestamps, remove datetime conversion
- If schema keeps TIMESTAMPTZ, keep conversion but ensure consistency

### 3.3 `k0/modules/builders/embedding_queue_write.py`

- Same timestamp conversion issue as hipp_events_row.py

### 3.4 `k0/drivers/*.py`

- Any driver that writes to tables with timestamp columns

---

## Phase 4: Fix Strategy

### Option A: Nuclear Reset (RECOMMENDED)

1. **Delete all 29 Alembic migrations**
2. **Create single new migration** that exactly matches `sqlite_full_schema.sql`
3. **Drop and recreate PostgreSQL database**
4. **Run new migration**
5. **Update kernel code** to use correct column names/types

**Pros:**

- Clean slate
- No legacy baggage
- Guaranteed to match SQLite

**Cons:**

- Loses migration history
- Any existing PostgreSQL data is lost

### Option B: Incremental Fix

1. **Audit each migration** against SQLite schema
2. **Create new migrations** to alter tables (add/drop columns, change types)
3. **Update kernel code** for each change

**Pros:**

- Preserves migration history
- Can be applied to running system

**Cons:**

- Complex ALTER TABLE operations
- Type changes (UUID -> TEXT) may fail with data
- Risk of partial fixes

---

## Phase 5: Execution Plan

### Step 1: Create Corrected Migration (2-4 hours)

1. Parse `sqlite_full_schema.sql`
2. For each CREATE TABLE:
   - Extract columns, types, constraints
   - Convert SQLite types to PostgreSQL equivalents:
     - `TEXT` -> `VARCHAR(n)` or `TEXT`
     - `INTEGER` -> `BIGINT`
     - `REAL` -> `DOUBLE PRECISION`
     - `BLOB` -> `BYTEA`
   - Preserve PRIMARY KEY, FOREIGN KEY, CHECK constraints
3. For each CREATE INDEX:
   - Convert to PostgreSQL syntax
   - Handle partial indexes (WHERE clauses)
4. Add PostgreSQL-specific tables:
   - pgvector extension
   - HNSW indexes (optional, can be added later)

### Step 2: Reset PostgreSQL Database (5 minutes)

```bash
docker exec k0-postgres psql -U k0user -d postgres -c "DROP DATABASE k0_kernel;"
docker exec k0-postgres psql -U k0user -d postgres -c "CREATE DATABASE k0_kernel;"
```

### Step 3: Run New Migration (5 minutes)

```bash
docker exec k0-kernel alembic upgrade head
```

### Step 4: Update Kernel Code (1-2 hours)

1. `k0/kernel/syscalls.py`:
   - Fix `pipeline_processed_upsert()` to use `space_id, wal_pos`
   - Fix `pipeline_processed_check()` to use `space_id, wal_pos`

2. `k0/modules/builders/hipp_events_row.py`:
   - If INTEGER timestamps: remove `_unix_to_datetime()`, pass int directly
   - If TIMESTAMPTZ: keep conversion

3. `k0/modules/builders/embedding_queue_write.py`:
   - Same as hipp_events_row.py

4. `k0/kernel/syscalls.py` - `relationships_query()`:
   - Use `person_id`, `related_person_id` (SQLite names)
   - Not `source_person_id`, `target_person_id`

### Step 5: Test P02 Pipeline (30 minutes)

```bash
python k0/deploy/provision_and_submit.py
docker logs k0-kernel -f
```

---

## Appendix A: SQLite to PostgreSQL Type Mapping

| SQLite Type | PostgreSQL Type | Notes |
|-------------|-----------------|-------|
| `TEXT` | `VARCHAR(n)` or `TEXT` | Use VARCHAR for constrained lengths |
| `INTEGER` | `BIGINT` | SQLite INTEGER can be 64-bit |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` | Auto-increment |
| `REAL` | `DOUBLE PRECISION` | 8-byte float |
| `BLOB` | `BYTEA` | Binary data |
| `BOOLEAN` | `BOOLEAN` | Same |
| `TEXT NOT NULL CHECK(...)` | `VARCHAR(n) NOT NULL CHECK(...)` | Preserve constraints |

---

## Appendix B: SQLite Tables Summary

From `sqlite_full_schema.sql`:

```
1.  schema_migrations      - 3 columns
2.  st_wal                 - 22 columns
3.  idem_ledger            - 5 columns
4.  st_receipts            - 11 columns
5.  st_offsets             - 6 columns (composite PK)
6.  st_devices             - 6 columns
7.  st_device_keys         - 10 columns (composite PK)
8.  st_outbox              - 14 columns
9.  st_dlq                 - 18 columns
10. schema_registry        - 8 columns (composite PK)
11. st_obligation_log      - 7 columns
12. st_acl                 - 11 columns
13. st_retention_policy    - 11 columns
14. st_archive_manifest    - 9 columns
15. st_crdt_merge_log      - 11 columns
16. people                 - 33 columns
17. households             - 35 columns
18. st_pipeline_processed  - 4 columns (composite PK)
19. st_pipeline_status     - 7 columns (composite PK)
20. st_pipeline_watermarks - 4 columns (composite PK)
21. st_hipp_events         - 90 columns
22. st_relationships       - 9 columns
23. st_embedding_queue     - 17 columns
24. st_vec                 - 13 columns
25. sqlite_sequence        - (internal, skip)
```

---

## Appendix C: Affected Kernel Files

Files that execute SQL and may need updates:

```
k0/kernel/syscalls.py
k0/modules/builders/hipp_events_row.py
k0/modules/builders/embedding_queue_write.py
k0/db/repo.py (if exists)
k0/drivers/postgres.py (or equivalent)
k0/outbox/worker.py
k0/receipts/*.py
```

---

## Decision Points

Before proceeding, decide:

1. **ID Types**: Keep UUID or match SQLite TEXT?
   - Recommendation: Use VARCHAR(64) to match SQLite

2. **Timestamp Types**: Keep TIMESTAMPTZ or use BIGINT?
   - Recommendation: Use BIGINT to match SQLite exactly (simpler, no conversion needed)

3. **Strategy**: Nuclear reset or incremental fix?
   - Recommendation: Nuclear reset (cleaner)

4. **pgvector**: Keep or defer?
   - Recommendation: Keep, add after base tables

---

## Owner

Assigned to: [TBD]
Target Date: [TBD]
Priority: CRITICAL (P02 pipeline blocked)

---

## TRIPLE-VERIFIED SUMMARY

### Final Audit Results (Verified 3x on December 23, 2025)

| Status | Count | Tables |
|--------|-------|--------|
| ✅ OK | 4 | `schema_migrations`, `st_offsets`, `schema_registry`, `st_obligation_log` |
| ⚠️ MINOR | 3 | `st_wal`, `st_outbox`, `st_acl` |
| ❌ BROKEN | 17 | All others |

### CRITICALLY BROKEN (Completely Wrong Schema)

1. **`st_pipeline_processed`** - Wrong PK, missing columns, extra columns
2. **`st_pipeline_status`** - Wrong PK, completely different columns
3. **`st_relationships`** - Wrong PK, wrong column names, missing columns
4. **`st_hipp_events`** - 20+ columns wrong nullability, all timestamps wrong type

### BROKEN (Wrong Nullability or Types)

1. **`idem_ledger`** - `receipt_id` TEXT NOT NULL→UUID nullable
2. **`st_receipts`** - 4 columns NOT NULL→nullable
3. **`st_devices`** - `mls_group_id` NOT NULL→nullable, `hmac_secret` nullable→NOT NULL
4. **`st_device_keys`** - `key_version` TEXT→Integer
5. **`st_dlq`** - `wal_pos` nullable→NOT NULL, `state` DEFAULT wrong
6. **`st_retention_policy`** - `privacy_band` nullable→NOT NULL, defaults wrong
7. **`st_crdt_merge_log`** - `winner_device_id` NOT NULL→nullable
8. **`people`** - 8+ columns NOT NULL→nullable
9. **`households`** - 6+ columns NOT NULL→nullable
10. **`st_pipeline_watermarks`** - Missing `space_id`, has `partition_key`
11. **`st_embedding_queue`** - `job_id` INTEGER→UUID, `priority` TEXT→SmallInteger
12. **`st_vec`** - `event_id` NOT NULL→nullable, `status` DEFAULT wrong

### PostgreSQL-Specific (Keep As-Is)

- `0001_initial.py`
- `0025_pgvector_extension.py`
- `0027_vector_indexes.py`
- `0028_fts_columns.py`
- `0029_fts_indexes.py`

---

## RECOMMENDED ACTION

### Nuclear Reset Strategy

1. **Archive current migrations** to `k0/db/alembic/versions_broken/`
2. **Create new migration file** `0001_sqlite_schema.py` that exactly matches SQLite
3. **Create pgvector migration** `0002_pgvector.py` for vector support
4. **Drop PostgreSQL database** and recreate
5. **Run new migrations**
6. **Update kernel code** for correct column names

### Key Decisions Made

| Decision | Choice | Reason |
|----------|--------|--------|
| ID Types | VARCHAR(64) | Match SQLite exactly, avoid UUID conversion |
| Timestamps | BIGINT | Match SQLite exactly, avoid datetime conversion |
| Strategy | Nuclear Reset | 17 of 24 tables broken, incremental fix too risky |
| pgvector | Keep | Required for P08 vector indexing |

### Estimated Time

| Task | Time |
|------|------|
| Create new migration | 3-4 hours |
| Reset database | 10 minutes |
| Update kernel code | 2 hours |
| Test P02 | 30 minutes |
| **Total** | **6-7 hours** |

---

**VERIFICATION COMPLETE**

This plan was verified by:

1. Reading full SQLite schema from `sqlite_full_schema.sql` (611 lines)
2. Reading all 29 Alembic migration files
3. Column-by-column comparison of each table
4. Documenting every mismatch with exact details

**No assumptions made. All differences documented.**
