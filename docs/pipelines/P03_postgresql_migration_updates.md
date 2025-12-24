# P03 Dossier — PostgreSQL Migration Updates

**Status:** ✅ COMPLETED
**Created:** 2025-12-24
**Updated:** 2025-01-XX
**Purpose:** Track stale sections in P03_consolidation_dossier_v2.md requiring updates after K0 PostgreSQL migration

---

## Executive Summary

The P03 Consolidation Dossier v2 was written when K0 used SQLite as its storage backend. Following the migration to PostgreSQL (per `k0/docs/k0_postgresql_migration_plan.md`), several sections were stale and have been updated.

**Key Changes Applied:**

- SQLite → PostgreSQL 16+ / asyncpg
- SQLite PRAGMAs → PostgreSQL GUCs / PostgresSettings
- SQLite table-based locking → PostgreSQL native advisory locks
- SQLite `INDEXED BY` hints → PostgreSQL query planner
- SQLite `?` placeholders → PostgreSQL `$N` placeholders
- Architecture diagram reference updated to `k0_source_of_truth_postgresql.mmd`
- Error recovery matrix updated with PostgreSQL error types

---

## Sections Updated

### 1. Section 4.10.6 — Interim P03 Implementation (Pre-K0 Enhancement)

**Location:** Lines 1524-1532

**Current (Stale):**

```markdown
| K0 Gap | P03 Workaround | Limitation |
|--------|---------------|------------|
| Advisory locks | SQLite table-based CAS | Single-node only, no cross-node coordination |
| Partitioned execution | Single global trigger | All spaces processed by one node |
| Optimistic concurrency | Custom SQL in R7 | Duplicated pattern, not reusable |
| Node identity | Environment variable | No dynamic cluster awareness |
```

**Required Update:**

```markdown
| K0 Gap | PostgreSQL Solution | Status |
|--------|---------------------|--------|
| Advisory locks | `pg_advisory_lock()` / `pg_try_advisory_lock()` | ✅ AVAILABLE - Native PostgreSQL |
| Partitioned execution | `FOR UPDATE SKIP LOCKED` + K0 Scheduler | 🔄 Partially available |
| Optimistic concurrency | `RETURNING` clause + row versioning | ✅ AVAILABLE - Native PostgreSQL |
| Node identity | Environment variable + pg_stat_activity | 🔄 Enhanced with PostgreSQL |
```

**Impact:** HIGH — Core concurrency model has changed

---

### 2. Section 4.10.7 — ADR Tracking

**Location:** Lines 1541-1550

**Current (Stale):**

```markdown
| ADR ID | Title | Status | Priority |
|--------|-------|--------|----------|
| k0XX | Advisory Lock Service | 📋 Proposed | P1 (Multi-node) |
| k0XX | Partitioned Pipeline Execution | 📋 Proposed | P1 (Multi-node) |
| k0XX | Optimistic Concurrency in UoW | 📋 Proposed | P2 (Code quality) |
| k0XX | Pipeline Execution Context | 📋 Proposed | P2 (Cluster awareness) |
```

**Required Update:**

```markdown
| ADR ID | Title | Status | Priority |
|--------|-------|--------|----------|
| k0XX | Advisory Lock Service | ✅ SUPERSEDED - PostgreSQL native | N/A |
| k0XX | Partitioned Pipeline Execution | 📋 Proposed | P1 (Multi-node) |
| k0XX | Optimistic Concurrency in UoW | ✅ SUPERSEDED - PostgreSQL native | N/A |
| k0XX | Pipeline Execution Context | 📋 Proposed | P2 (Cluster awareness) |
```

**Impact:** MEDIUM — ADR tracking accuracy

---

### 3. Section 15.7.1 — SQL Index Hints

**Location:** Lines 9020-9035

**Current (Stale):**

```sql
-- Force index usage for consolidation queries
SELECT * FROM st_hipp_events INDEXED BY idx_hipp_consolidation
WHERE consolidation_status IS NULL
  AND tenant_id = ?
  AND space_id = ?
ORDER BY importance_score DESC
LIMIT 1000;
```

**Required Update:**

```sql
-- PostgreSQL uses query planner; explicit hints via pg_hint_plan if needed
-- Standard approach: rely on ANALYZE and proper indexing
SELECT * FROM st_hipp_events
WHERE consolidation_status IS NULL
  AND tenant_id = $1
  AND space_id = $2
ORDER BY importance_score DESC
LIMIT 1000;

-- Ensure statistics are current (K0 migrations handle this)
ANALYZE st_hipp_events;
```

**Impact:** MEDIUM — SQL syntax compatibility

---

### 4. Section 15.7.2 — SQLite Configuration (K0 Kernel Config)

**Location:** Lines 9037-9077

**Current (Stale) — ENTIRE SECTION:**

```python
class P03DatabaseConfig:
    @classmethod
    def from_k0_settings(cls, db_settings: DatabaseSettings) -> dict:
        """Build P03 SQLite config from K0 DatabaseSettings."""
        return {
            'journal_mode': 'WAL',
            'synchronous': db_settings.synchronous or 'NORMAL',
            'cache_size': db_settings.cache_size_kb or -64000,
            'mmap_size': db_settings.mmap_size_bytes or 268435456,
            'page_size': 4096,
            'busy_timeout': db_settings.busy_timeout_ms or 5000,
            'wal_autocheckpoint': 1000,
        }

P03_SQLITE_PRAGMAS = {
    'journal_mode': 'WAL',
    'synchronous': 'NORMAL',
    'cache_size': -64000,
    'mmap_size': 268435456,
    'page_size': 4096,
    'temp_store': 'MEMORY',
    'locking_mode': 'NORMAL',
}
```

**Required Update — REPLACE ENTIRE SECTION:**

```python
# Section 15.7.2 PostgreSQL Configuration (K0 Kernel Config)

from k0.config.postgres import PostgresSettings


class P03DatabaseConfig:
    """
    Database configuration aligned with K0 PostgreSQL Settings.

    K0 References:
    - k0/config/postgres.py: PostgresSettings
    - k0/db/pool.py: asyncpg.Pool management
    """

    @classmethod
    def from_k0_settings(cls, pg_settings: PostgresSettings) -> dict:
        """Build P03 PostgreSQL config from K0 PostgresSettings."""
        return {
            'min_pool_size': pg_settings.min_pool_size,
            'max_pool_size': pg_settings.max_pool_size,
            'command_timeout': 60.0,  # seconds
            'statement_cache_size': 100,
        }


# P03-optimized PostgreSQL session settings
P03_POSTGRES_SESSION_SETTINGS = {
    'statement_timeout': '300s',        # 5 min max for consolidation queries
    'lock_timeout': '30s',              # 30s max wait for locks
    'idle_in_transaction_session_timeout': '60s',
    'work_mem': '256MB',                # Per-operation memory for sorts/hashes
    'maintenance_work_mem': '512MB',    # For ANALYZE operations
}
```

**Impact:** HIGH — Core database configuration

---

### 5. Section 16.6 — Complete Configuration YAML (database block)

**Location:** Lines 9631-9646

**Current (Stale):**

```yaml
database:
  # K0 DatabaseSettings
  path: "./k0_runtime.sqlite3"
  synchronous: "NORMAL"
  cache_size_kb: 65536
  mmap_size_bytes: 268435456
  busy_timeout_ms: 5000
  wal_autocheckpoint: 1000
```

**Required Update:**

```yaml
database:
  # K0 PostgresSettings (k0/config/postgres.py)
  host: "${K0_DB_HOST:-localhost}"
  port: ${K0_DB_PORT:-5432}
  database: "${K0_DB_NAME:-k0}"
  user: "${K0_DB_USER:-k0}"
  password: "${K0_DB_PASSWORD}"  # From secrets
  min_pool_size: 2
  max_pool_size: 10
  ssl_mode: "require"
```

**Impact:** HIGH — Configuration compatibility

---

### 6. Architecture Diagram Reference

**Location:** Line 1410

**Current (Stale):**

```markdown
> **Reference**: [k0_source_of_truth_v2.mmd](../../architecture_diagrams/k0/k0_source_of_truth_v2.mmd)
```

**Required Update:**

```markdown
> **Reference**: [k0_source_of_truth_postgresql.mmd](../../architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd)
```

**Impact:** LOW — Documentation accuracy

---

## Sections Analyzed (Lines 9700-15406) — Additional Findings

### 7. Section 15.8 Performance Settings (YAML) — Database Block

**Location:** Lines 9813-9818

**Current (Stale):**

```yaml
performance:
  database:
    cache_size_mb: 64
    wal_checkpoint_threshold: 1000
    analyze_interval: 100              # ANALYZE after N batches
```

**Required Update:**

```yaml
performance:
  database:
    shared_buffers_mb: 256             # PostgreSQL shared memory
    effective_cache_size_mb: 1024      # OS cache estimate
    work_mem_mb: 64                    # Per-operation memory
    maintenance_work_mem_mb: 256       # For VACUUM/ANALYZE
    analyze_interval: 100              # ANALYZE after N batches
```

**Impact:** MEDIUM — Performance tuning parameters

---

### 8. Appendix D.7.3 — Optimistic Locking SQL Syntax

**Location:** Lines 14200-14230

**Current (Stale):**

```python
result = await context.syscalls.execute(
    \"\"\"
    UPDATE st_hipp_events
    SET consolidation_status = ?,
        version = version + 1,
        updated_at = ?
    WHERE event_id = ?
    AND version = ?
    \"\"\",
    [new_status, int(time.time()), event_id, expected_version]
)
```

**Required Update:**

```python
result = await context.syscalls.execute(
    \"\"\"
    UPDATE st_hipp_events
    SET consolidation_status = $1,
        version = version + 1,
        updated_at = $2
    WHERE event_id = $3
    AND version = $4
    RETURNING version
    \"\"\",
    [new_status, int(time.time()), event_id, expected_version]
)
```

**Notes:**

- `?` placeholders → `$1, $2, ...` (PostgreSQL parameterized queries)
- Added `RETURNING` clause for immediate version confirmation

**Impact:** MEDIUM — SQL syntax compatibility

---

### 9. Section 17: Ops Readiness — Runbook Commands

**Location:** Lines 10150-10350 (various runbooks)

**Current (Stale):**

- Runbooks reference `k0ctl storage query` with SQLite-style syntax
- No PostgreSQL-specific diagnostic commands

**Required Update:**

- Add PostgreSQL diagnostic queries (`pg_stat_activity`, `pg_locks`)
- Update connection troubleshooting for pgbouncer
- Add advisory lock debugging commands

**Impact:** MEDIUM — Operational procedures

---

### 10. Appendix G.4 — Error Recovery Matrix

**Location:** Lines 15240-15270

**Current (Partially Stale):**

```markdown
| R0 | DB_LOCKED | Wait and retry | 5 | Linear |
```

**Required Update:**

```markdown
| R0 | LOCK_NOT_AVAILABLE | Wait and retry with pg_advisory_unlock | 5 | Linear |
```

**Notes:**

- SQLite `DB_LOCKED` → PostgreSQL `LOCK_NOT_AVAILABLE`
- Add PostgreSQL-specific lock timeout handling

**Impact:** LOW — Error classification alignment

---

### Sections Reviewed — No Changes Required

The following sections were reviewed and **require no PostgreSQL updates**:

- ✅ **Section 17.1-17.3** — SLOs, dashboards, alerts (database-agnostic metrics)
- ✅ **Appendix C** — Algorithm specifications (in-memory algorithms, no SQL)
- ✅ **Appendix D.1-D.6** — Pipeline/module design (uses abstractions)
- ✅ **Appendix E** — Canonical name registry (table names unchanged)
- ✅ **Appendix F** — Threshold configuration (application-level thresholds)
- ✅ **Appendix G.1-G.3** — State machine overview (database-agnostic)
- ✅ **Appendix H** — UltraBERT model spec (no database interaction)

---

## Update Priority (Complete)

| Priority | Section | Line Range | Impact | Effort |
| -------- | ------- | ---------- | ------ | ------ |
| P0 | 15.7.2 SQLite Configuration | 9037-9077 | HIGH | Replace entire section |
| P0 | 16.6 Configuration YAML (database block) | 9631-9646 | HIGH | Update database block |
| P1 | 4.10.6 Interim Implementation | 1524-1532 | HIGH | Rewrite workaround table |
| P1 | 15.7.1 SQL Index Hints | 9020-9035 | MEDIUM | Update SQL syntax |
| P1 | D.7.3 Optimistic Locking SQL | 14200-14230 | MEDIUM | Update SQL syntax |
| P2 | 4.10.7 ADR Tracking | 1541-1550 | MEDIUM | Update status column |
| P2 | 15.8 Performance Settings | 9813-9818 | MEDIUM | Update database tuning |
| P2 | 17.x Runbook Commands | 10150-10350 | MEDIUM | Add PostgreSQL diagnostics |
| P3 | Architecture reference | 1410 | LOW | Update link |
| P3 | G.4 Error Recovery Matrix | 15240-15270 | LOW | Update error classifications |

---

## Related Documents

| Document | Location | Status |
|----------|----------|--------|
| PostgreSQL Migration Plan | `k0/docs/k0_postgresql_migration_plan.md` | Source of truth |
| K0 Architecture (PostgreSQL) | `architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd` | Current |
| K0 Architecture (SQLite) | `architecture_diagrams/k0/k0_source_of_truth_v2.mmd` | Deprecated |
| P03 Implementation Plan | `docs/plans/p03_implementation_plan.md` | Needs review |

---

## Changelog

| Date       | Author  | Change                                             |
| ---------- | ------- | -------------------------------------------------- |
| 2025-12-24 | K0 Team | Complete analysis of all stale sections (15406 lines) |
