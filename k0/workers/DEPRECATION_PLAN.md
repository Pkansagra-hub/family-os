# k0/workers/ - Complete Deprecation Plan

## Executive Summary

**Status**: DEPRECATED - Scheduled for complete removal
**Reason**: Async workers add complexity without compelling performance benefit for current scale
**Impact**: End-to-end removal - NO backward compatibility
**Timeline**: Immediate removal in current PR

---

## Background

The `k0/workers/` module was introduced in V1.4 as a "performance optimization" to reduce commit latency from ~150ms to ~80-100ms by deferring embedding computation and FTS indexing to async background workers.

**The Problem:**

- Added significant architectural complexity (outbox pattern, worker coordination, async polling)
- Created coupling between commit path and worker infrastructure
- Introduced new failure modes (worker crashes, outbox saturation, retry logic)
- Required operational complexity (worker processes, monitoring, scaling)
- **Performance benefit not validated at current scale** - premature optimization

**The Solution:**

- Remove workers entirely - compute embeddings and FTS synchronously in commit path
- Simplify to single-phase commit (no outbox staging, no async workers)
- Re-evaluate async processing when scale demands it (10k+ events/sec)

---

## What Gets Removed

### 1. k0/workers/ Directory (Complete Deletion)

```
k0/workers/
├── __init__.py                    ❌ DELETE
├── README.md                      ❌ DELETE
├── coordinator.py                 ❌ DELETE
├── embedding_worker.py            ❌ DELETE
├── fts_worker.py                  ❌ DELETE
└── DEPRECATION_PLAN.md            ⚠️  KEEP (this document)
```

**Files to Delete:**

- `k0/workers/__init__.py`
- `k0/workers/README.md`
- `k0/workers/coordinator.py`
- `k0/workers/embedding_worker.py`
- `k0/workers/fts_worker.py`

---

### 2. WAL Schema Changes (Column Removal)

**File**: `k0/storage/wal.py`

**Remove from WalEntry dataclass:**

```python
# V1.4 NEW: Async worker status tracking
embedding_status: str | None = None  # ❌ DELETE
embedding_id: str | None = None       # ❌ DELETE
fts_status: str | None = None         # ❌ DELETE
fts_entry_id: str | None = None       # ❌ DELETE
```

**Remove from SQL queries:**

- `INSERT` statements: Remove `embedding_status, embedding_id, fts_status, fts_entry_id` columns
- `SELECT` statements: Remove these columns from projections
- Migration: ALTER TABLE to drop columns (or recreate table cleanly)

**Impact**: WAL entries will no longer track async worker status (no longer needed)

---

### 3. Outbox Store (Evaluate for Removal)

**File**: `k0/storage/outbox.py`

**Decision Point**: Is outbox used for anything OTHER than worker coordination?

**If NO (outbox ONLY for workers):**

- ❌ **DELETE** `k0/storage/outbox.py` entirely
- Remove `OutboxStore`, `OutboxEntry`, all related code
- Drop `st_outbox` table from schema

**If YES (outbox used for other features):**

- Keep outbox infrastructure
- Remove worker-specific fields/logic
- Document remaining use cases

**Action**: Audit outbox usage across codebase before removal

---

### 4. UnitOfWork Changes

**File**: `k0/uow/unit_of_work.py`

**Remove:**

```python
from k0.storage.outbox import OutboxEntry, OutboxStore  # ❌ DELETE import

outbox_store: OutboxStore | None = None                # ❌ DELETE field
_staged_outbox: list[OutboxEntry] = field(...)         # ❌ DELETE field

def stage_outbox(self, entry: OutboxEntry) -> None:    # ❌ DELETE method
    ...

def _flush_outbox(self) -> None:                        # ❌ DELETE method
    ...
```

**Impact**: UnitOfWork no longer stages outbox entries for async workers

---

### 5. Command Port Response Changes

**File**: `k0/ports/command.py`

**Remove from response models:**

```python
# V1.4 NEW: Async worker status tracking
embedding_status: str | None = Field(...)  # ❌ DELETE
embedding_id: str | None = Field(...)       # ❌ DELETE
fts_status: str | None = Field(...)         # ❌ DELETE
fts_entry_id: str | None = Field(...)       # ❌ DELETE
```

**Impact**: API responses will no longer include worker status fields

---

### 6. Test File Removal

**Delete entire test directory:**

```
tests/k0/workers/
├── test_issue_1_4_async_workers.py         ❌ DELETE
├── test_embedding_worker.py                ❌ DELETE
└── test_fts_worker.py                      ❌ DELETE
```

**Update tests that reference workers:**

- `tests/k0/storage/test_issue_1_7_1_8_1_9_v1_durability.py` - Remove V1.4 field tests
- Search for `embedding_status`, `fts_status`, `embedding_id`, `fts_entry_id` in tests

---

### 7. Deployment Artifacts (Complete Removal)

**Docker Images to Delete:**

```
k0/deploy/
├── Dockerfile.embedding-worker        ❌ DELETE
├── Dockerfile.fts-worker              ❌ DELETE
├── requirements.embedding-worker.txt  ❌ DELETE
└── requirements.fts-worker.txt        ❌ DELETE
```

**k0.ps1 Deployment Script Changes:**
**File**: `k0/deploy/k0.ps1`

**Remove worker image building (lines ~363-370):**

```powershell
# ❌ DELETE this block in Do-Up function
Write-Host "Building worker images..."
Write-Host "`n=== embedding-worker ===" -ForegroundColor Blue
$embeddingWorkerPresent = & docker images -q k0-embedding-worker:latest
if (-not $embeddingWorkerPresent) {
    docker compose -f $composeFile build embedding-worker
}

Write-Host "`n=== fts-worker ===" -ForegroundColor Blue
$ftsWorkerPresent = & docker images -q k0-fts-worker:latest
if (-not $ftsWorkerPresent) {
    docker compose -f $composeFile build fts-worker
}
```

**Replace with:**

```powershell
# Worker images removed - no longer needed (V1.4 deprecation)
```

**Docker Compose Changes:**
**File**: `k0/deploy/docker-compose.yml`

**Remove services:**

```yaml
# ❌ DELETE entire embedding-worker service (lines ~95-130)
embedding-worker:
  build: ...
  image: k0-embedding-worker:latest
  ...

# ❌ DELETE entire fts-worker service (lines ~132-160)
fts-worker:
  build: ...
  image: k0-fts-worker:latest
  ...
```

**Documentation to Update:**
**File**: `k0/deploy/QUICK_START.md`

**Remove sections:**

- "Embedding Worker running asynchronously" references
- "FTS Worker running asynchronously" references
- "Testing Worker Deployment" section
- "Issue: Workers not processing events" troubleshooting
- Worker container size information (~1.2GB embedding, ~600MB FTS)
- Worker log commands (`docker logs k0-embedding-worker`, etc.)

**Comments to Update:**
**File**: `k0/deploy/requirements.base.txt`

- Remove comment: "Used by ALL containers: kernel, embedding-worker, fts-worker"
- Change to: "Used by ALL containers: kernel"

**File**: `k0/deploy/requirements.dev.txt`

- Remove comment: "Note: sentence-transformers is preferred in embedding-worker"

---

### 8. SQL Migration (Rollback or New Migration)

**File**: `k0/contracts/sql/migrations/0011_v1_async_workers.sql`

**Decision Point**: Keep file as historical record OR create rollback migration?

**Option A: Keep Historical Record (Recommended)**

- Keep `0011_v1_async_workers.sql` as-is (documents what was tried)
- Create NEW migration: `0020_remove_worker_columns.sql`
- New migration drops columns, removes indexes

**Option B: Rewrite History (NOT Recommended)**

- Delete `0011_v1_async_workers.sql` entirely
- Risks breaking existing databases that ran the migration

**Recommended Approach**: Create `0020_remove_worker_columns.sql`

```sql
-- Migration 0020: Remove async worker infrastructure (deprecation)
--
-- Removes V1.4 async worker columns from st_wal table.
-- These columns were added in 0011_v1_async_workers.sql but are no longer needed
-- as embedding/FTS processing is now synchronous.
--
-- Migration Status: SAFE (drops columns, no data dependencies)
-- Rollback: Re-run 0011_v1_async_workers.sql to restore columns

BEGIN TRANSACTION;

-- Drop worker status indexes
DROP INDEX IF EXISTS idx_st_wal_embedding_status;
DROP INDEX IF EXISTS idx_st_wal_fts_status;

-- Drop worker columns (SQLite 3.35.0+ syntax)
-- For older SQLite, use table recreation approach (see template below)
ALTER TABLE st_wal DROP COLUMN embedding_status;
ALTER TABLE st_wal DROP COLUMN embedding_id;
ALTER TABLE st_wal DROP COLUMN fts_status;
ALTER TABLE st_wal DROP COLUMN fts_entry_id;

COMMIT;
```

---

### 9. Dependencies to Remove

**Root Requirements Files:**

- Check if `nltk`, `sentence-transformers`, `openai`, `tiktoken`, `httpx` are used OUTSIDE workers
- If only used by workers → remove from root `requirements.txt` or `pyproject.toml`

**Deployment Requirements:**

- `k0/deploy/requirements.embedding-worker.txt` - ❌ DELETE entirely
- `k0/deploy/requirements.fts-worker.txt` - ❌ DELETE entirely
- `k0/deploy/requirements.base.txt` - Update comments (remove worker references)
- `k0/deploy/requirements.dev.txt` - Update comments (remove worker references)

**Action**: Full dependency audit required - grep for imports in non-worker code

---

## Migration Strategy (NO Backward Compatibility)

### Phase 1: Remove Worker Code

1. Delete `k0/workers/` directory entirely
2. Remove worker imports from all files
3. Remove `OutboxStore` (if only used for workers)
4. Remove `stage_outbox()` from UnitOfWork
5. Remove worker status fields from WalEntry

### Phase 2: Schema Migration

1. Create migration script to drop WAL columns:

   ```sql
   -- If SQLite version supports DROP COLUMN (3.35.0+)
   ALTER TABLE st_wal DROP COLUMN embedding_status;
   ALTER TABLE st_wal DROP COLUMN embedding_id;
   ALTER TABLE st_wal DROP COLUMN fts_status;
   ALTER TABLE st_wal DROP COLUMN fts_entry_id;

   -- If older SQLite, recreate table without columns
   -- (see migration script template below)
   ```

2. Drop outbox table (if removing outbox):

   ```sql
   DROP TABLE IF EXISTS st_outbox;
   ```

### Phase 3: API Changes

1. Update command port response models (remove worker fields)
2. Update API documentation
3. Remove worker status from any client libraries

### Phase 4: Test Updates

1. Delete `tests/k0/workers/` directory
2. Remove worker-related assertions from other tests
3. Verify all tests pass without worker infrastructure

### Phase 5: Documentation Cleanup

1. Remove worker references from:
   - `k0/README.md`
   - Architecture diagrams
   - Performance documentation
   - Deployment guides

---

## SQLite Migration Script Template

**For SQLite versions < 3.35.0 (no DROP COLUMN support):**

```python
"""Migration: Remove worker-related columns from st_wal."""

import sqlite3
from pathlib import Path

def migrate_wal_remove_workers(db_path: Path) -> None:
    """Remove embedding_status, embedding_id, fts_status, fts_entry_id from st_wal."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # 1. Create new table without worker columns
        conn.execute("""
            CREATE TABLE st_wal_new (
                pos INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                space_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                envelope_json TEXT NOT NULL,
                schema_uri TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                device_id TEXT NOT NULL,
                commit_ts TEXT NOT NULL,
                body BLOB,
                payload_sha256 TEXT,
                idem_key TEXT,
                redacted_body_json TEXT,
                envelope_sha256 TEXT,
                ingested_at TEXT,
                clock_skew_ms INTEGER,
                policy_stamp_json TEXT,
                location_geohash TEXT,
                location_precision_m INTEGER
            )
        """)

        # 2. Copy data (excluding worker columns)
        conn.execute("""
            INSERT INTO st_wal_new (
                pos, tenant_id, space_id, topic, envelope_json,
                schema_uri, schema_version, device_id, commit_ts,
                body, payload_sha256, idem_key, redacted_body_json,
                envelope_sha256, ingested_at, clock_skew_ms,
                policy_stamp_json, location_geohash, location_precision_m
            )
            SELECT
                pos, tenant_id, space_id, topic, envelope_json,
                schema_uri, schema_version, device_id, commit_ts,
                body, payload_sha256, idem_key, redacted_body_json,
                envelope_sha256, ingested_at, clock_skew_ms,
                policy_stamp_json, location_geohash, location_precision_m
            FROM st_wal
        """)

        # 3. Drop old table
        conn.execute("DROP TABLE st_wal")

        # 4. Rename new table
        conn.execute("ALTER TABLE st_wal_new RENAME TO st_wal")

        # 5. Recreate indexes
        conn.execute("CREATE INDEX idx_wal_space_topic ON st_wal(space_id, topic)")
        conn.execute("CREATE INDEX idx_wal_idem_key ON st_wal(idem_key) WHERE idem_key IS NOT NULL")

        conn.commit()
        print("✅ Migration complete: Removed worker columns from st_wal")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_wal_remove_workers(Path("k0_runtime.sqlite3"))
```

---

## Testing Strategy (Post-Removal)

### 1. Unit Tests

- Verify WAL writes without worker columns
- Verify UnitOfWork commits without outbox staging
- Verify command port responses without worker fields

### 2. Integration Tests

- End-to-end commit flow (no async workers)
- Performance testing (measure new commit latency)
- Verify no references to removed modules

### 3. Regression Tests

- Run full test suite
- Ensure no import errors
- Verify all features work without workers

---

## Performance Impact (Expected)

### Before (V1.4 with workers)

- Commit latency: ~80-100ms P95
- Breakdown: UoW commit (50ms) + outbox staging (30-50ms)
- Embedding/FTS: Async (deferred to workers)

### After (V1.4 without workers)

- Commit latency: ~100-150ms P95 (EXPECTED INCREASE)
- Breakdown: UoW commit (50ms) + sync embedding (30-70ms) + sync FTS (20-30ms)
- No async workers, no outbox overhead

**Trade-off**: Slightly higher commit latency for MUCH simpler architecture

**Mitigation**:

- Optimize embedding computation (use faster models, cache)
- Optimize FTS indexing (batch updates, optimize NLTK)
- Re-introduce async workers ONLY if scale demands it (10k+ events/sec)

---

## Rollback Plan

**If removal causes critical issues:**

1. **Code Rollback**: Revert PR that removed workers
2. **Schema Rollback**: Re-add worker columns via migration
3. **Dependency Rollback**: Re-add nltk, sentence-transformers
4. **Worker Restart**: Deploy worker processes

**Prevention**: Thorough testing before merge, gradual rollout via feature flag

---

## Checklist

### Phase 1: Code Removal

- [ ] Delete `k0/workers/*.py` files (keep DEPRECATION_PLAN.md)
- [ ] Remove worker imports from all files
- [ ] Remove worker-specific `stage_outbox()` calls from UnitOfWork
- [ ] Remove worker fields from WalEntry dataclass (`k0/storage/wal.py`)
- [ ] Remove worker fields from command port responses (`k0/ports/command.py`)
- [ ] Verify `OutboxStore` is ONLY used by drivers (NOT workers)

### Phase 2: Deployment Artifacts

- [ ] Delete `k0/deploy/Dockerfile.embedding-worker`
- [ ] Delete `k0/deploy/Dockerfile.fts-worker`
- [ ] Delete `k0/deploy/requirements.embedding-worker.txt`
- [ ] Delete `k0/deploy/requirements.fts-worker.txt`
- [ ] Remove worker services from `k0/deploy/docker-compose.yml`
- [ ] Update `k0/deploy/QUICK_START.md` (remove worker sections)
- [ ] Update comments in `requirements.base.txt` and `requirements.dev.txt`

### Phase 3: Schema Migration

- [ ] Create `k0/contracts/sql/migrations/0020_remove_worker_columns.sql`
- [ ] Test migration on dev database (verify column removal)
- [ ] Verify no code references removed columns
- [ ] Run migration on staging database
- [ ] Run migration on production database (if applicable)

### Phase 4: Test Updates

- [ ] Delete `tests/k0/workers/` directory entirely
- [ ] Remove worker field tests from `tests/k0/storage/test_issue_1_7_1_8_1_9_v1_durability.py`
- [ ] Search and remove all `embedding_status`, `fts_status`, `embedding_id`, `fts_entry_id` assertions
- [ ] Run full test suite - verify all passing
- [ ] Check for any remaining worker references in test fixtures

### Phase 5: Documentation Cleanup

- [ ] Update `k0/README.md` (remove worker references)
- [ ] Update architecture diagrams (remove async worker nodes)
- [ ] Update `k0/deploy/readme.md` (remove worker deployment instructions)
- [ ] Remove worker monitoring dashboards (if any)
- [ ] Update runbooks (remove worker troubleshooting)

### Phase 6: Dependency Audit

- [ ] Grep for `import nltk` outside workers → remove if unused
- [ ] Grep for `import sentence_transformers` outside workers → remove if unused
- [ ] Grep for `import openai` outside workers → remove if unused
- [ ] Update root `requirements.txt` or `pyproject.toml`
- [ ] Verify no broken imports after dependency removal

### Phase 7: Final Validation

- [ ] All tests passing (no worker references)
- [ ] No import errors (all modules load cleanly)
- [ ] Docker build succeeds (kernel only, no worker images)
- [ ] Docker Compose up succeeds (kernel + neo4j only)
- [ ] Performance acceptable (commit latency measured)
- [ ] End-to-end smoke test successful
- [ ] No orphaned worker processes in production

---

## References

- **Original Design**: V1.4 Performance Optimization
- **Deprecation Rationale**: Premature optimization, excessive complexity
- **Architecture Decision**: Simplify until proven necessary
- **Performance Target**: <200ms P95 commit latency without workers
- **Future Re-evaluation**: When scale exceeds 10k events/sec

---

## Approval Required

**Before proceeding with removal:**

- [ ] Architecture review: Confirm removal aligns with system goals
- [ ] Performance review: Confirm acceptable latency without workers
- [ ] Operations review: Confirm no deployment blockers
- [ ] Product review: Confirm no user-facing impact

**Sign-off**: _______________ Date: _______________
