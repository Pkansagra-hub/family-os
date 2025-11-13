# Milestone 1 Updated Plan - Based on Actual K0 Code Analysis

**Date:** November 12, 2025  
**Analysis:** Reviewed k0/bus/core.py, k0/storage/*.py, k0/kernel/app.py, migrations/  
**Status:** 🔄 PLAN UPDATED based on code inspection

---

## Executive Summary

**GOOD NEWS:** 🎉 Much of M1 infrastructure ALREADY EXISTS!

- ✅ **70% of M1 foundation is done** (WAL, Outbox, DLQ, migrations system)
- ⏱️ **Reduced timeline: 3 hours → 2 hours** (less to build)
- 🎯 **Focus shifted:** BusDispatcher API + 3 new tables only

---

## What Already EXISTS ✅

### 1. WAL Infrastructure (`k0/storage/wal.py`)

**Table Schema (from 0001_baseline.sql):**
```sql
CREATE TABLE st_wal (
  pos INTEGER PRIMARY KEY AUTOINCREMENT,  -- ✅ Already monotonic!
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
  commit_ts TEXT NOT NULL
);
```

**Key Findings:**
- ✅ `pos` field is PRIMARY KEY AUTOINCREMENT (already monotonic, exactly what we need)
- ✅ Architecture calls it `wal_pos` but actual field is `pos` - this is FINE, we use `pos`
- ✅ Has all V1 fields (envelope_sha256, ingested_at, clock_skew_ms, policy_stamp_json, etc.)
- ✅ WriteAheadLog class fully implemented with append() method

**Decision:** NO changes needed to st_wal table. Use existing `pos` field.

### 2. Outbox Infrastructure (`k0/storage/outbox.py`)

**Table Schema (from 0001_baseline.sql):**
```sql
CREATE TABLE st_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,  -- ✅ Already references st_wal.pos!
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
  payload BLOB NOT NULL,
  fingerprint TEXT NOT NULL,
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  retries INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  next_attempt_ts TEXT,  -- ✅ Has retry backoff fields
  backoff_exp INTEGER DEFAULT 0,  -- ✅ Has exponential backoff
  status TEXT DEFAULT 'PENDING'  -- ✅ Has status tracking
);
```

**Key Findings:**
- ✅ `wal_pos` field already exists and references st_wal.pos
- ✅ OutboxStore class fully implemented
- ✅ Has retry logic (next_attempt_ts, backoff_exp, retries)
- ✅ UnitOfWork already flushes outbox in ACID transaction

**Decision:** NO changes needed to st_outbox table. Perfect as-is.

### 3. DLQ Infrastructure (`k0/storage/dlq.py`)

**Table Schema (from 0001_baseline.sql):**
```sql
CREATE TABLE st_dlq (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER,  -- ✅ Has wal_pos reference
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
);
```

**Key Findings:**
- ✅ st_dlq table exists with most needed fields
- ⚠️ **MISSING:** `error_kind` column (architecture wants this for categorization)
- ⚠️ **MISSING:** `error_fingerprint` column (architecture wants this for deduplication)
- ⚠️ Has `reason` instead of `error_kind` - similar but different naming

**Decision:** OPTIONAL UPDATE to st_dlq in migration 0012 (add error_kind, error_fingerprint columns).

### 4. BusDispatcher Foundation (`k0/bus/core.py`)

**Current Implementation:**
```python
class BusDispatcher:
    def __init__(self, *, scheduler, sinks=None, ...):
        self._sinks: List[BusSink] = list(sinks or [])
        # ...
    
    def register_sink(self, sink: BusSink) -> None:
        """Register sink invoked for EVERY bus message."""  # ❌ O(N) broadcast
        self._sinks.append(sink)
    
    async def dispatch(self, messages: Iterable[BusMessage]) -> None:
        """Dispatch messages in WAL order."""
        # ...
        for sink in self._sinks:  # ❌ Calls ALL sinks for EVERY message
            result = sink(message)
```

**Key Findings:**
- ✅ BusDispatcher class exists with complete middleware chain
- ✅ BusMessage dataclass: topic, payload, offset, trace_id
- ✅ Scheduler integration for QoS tokens
- ✅ 3 kernel sinks registered (observability, driver_worker_pool, sse_fan_out)
- ❌ **MISSING:** Topic-based subscription (currently broadcasts to all sinks)
- ❌ **MISSING:** `subscribe(topic, handler)` method
- ❌ **MISSING:** `tap(handler)` method for observability-only sinks

**Decision:** ADD `subscribe()` and `tap()` methods, keep `register_sink()` with deprecation warning.

### 5. Migrations System (`k0/automation/migrate.py`)

**Key Findings:**
- ✅ Complete migration runner with forward/rollback support
- ✅ Checksum validation (SHA256)
- ✅ Migration directory: `k0/contracts/sql/migrations/`
- ✅ 11 migrations exist (0001-0011)
- ✅ Prometheus telemetry integration

**Decision:** Use existing system, create migration 0012 for pipeline tables.

### 6. UnitOfWork (`k0/uow/unit_of_work.py`)

**Key Methods:**
```python
class UnitOfWork:
    def append_wal(self, entry: WalEntry) -> int:
        """Append to WAL, returns position."""
        position = self.write_ahead_log.append(entry, connection=self.connection)
        self._wal_positions.append(position)
        return position
    
    def stage_outbox(self, entry: OutboxEntry) -> None:
        """Stage outbox entry for ACID commit."""
        self._staged_outbox.append(entry)
    
    def _commit(self) -> None:
        """ACID commit: WAL + Outbox + Receipts + Offsets."""
        self._flush_outbox()  # ✅ Flushes staged outbox
        self._connection.commit()
```

**Key Findings:**
- ✅ ACID transaction coordinator works perfectly
- ✅ WAL append + outbox staging in same transaction
- ✅ Receipt issuer integration
- ✅ Fsync control (strict/wal_only/disabled modes)

**Decision:** NO changes needed. Perfect for 2-phase architecture.

---

## What's MISSING ❌

### 1. BusDispatcher v2 APIs

**Need to ADD:**

```python
class BusDispatcher:
    def __init__(self, ...):
        self._sinks: List[BusSink] = []  # ✅ Already exists
        self._taps: List[BusSink] = []  # ❌ NEW - for observability
        self._topic_subs: dict[str, list[BusSink]] = {}  # ❌ NEW - topic map
    
    def subscribe(self, topic: str, handler: BusSink) -> None:
        """Subscribe to specific topic (O(k) dispatch)."""
        # ❌ NEW METHOD
        if topic not in self._topic_subs:
            self._topic_subs[topic] = []
        self._topic_subs[topic].append(handler)
    
    def tap(self, handler: BusSink) -> None:
        """Tap all messages (observability only)."""
        # ❌ NEW METHOD
        self._taps.append(handler)
    
    def register_sink(self, sink: BusSink) -> None:
        """DEPRECATED: Use subscribe() or tap()."""
        # ✅ EXISTS - add deprecation warning
        import warnings
        warnings.warn(
            "register_sink() is deprecated, use subscribe() or tap()",
            DeprecationWarning,
            stacklevel=2
        )
        self._sinks.append(sink)
    
    async def _fan_out(self, context: BusDispatchContext) -> None:
        message = context.message
        
        # ❌ NEW: Topic-based dispatch (O(k))
        topic_handlers = self._topic_subs.get(message.topic, [])
        
        # ❌ NEW: Tap handlers (observability)
        tap_handlers = self._taps
        
        # ✅ EXISTS: Legacy broadcast sinks
        legacy_handlers = self._sinks
        
        # Combine and dispatch
        all_handlers = topic_handlers + tap_handlers + legacy_handlers
        tasks = [asyncio.create_task(h(message)) for h in all_handlers]
        if tasks:
            await asyncio.gather(*tasks)
```

**Effort:** 1 hour (coding) + 30 min (tests) = 1.5 hours

### 2. Pipeline Tables (3 NEW tables)

**Migration 0012:**

```sql
-- File: k0/contracts/sql/migrations/0012_pipeline_infrastructure.sql
BEGIN;

-- Note: st_wal.pos already exists as monotonic AUTOINCREMENT
-- Note: st_outbox.wal_pos already exists and references st_wal.pos
-- No ALTER TABLE needed for existing tables!

-- Table 1: Per-space pipeline processing ledger (idempotency + ordering)
CREATE TABLE IF NOT EXISTS st_pipeline_processed (
  pipeline_id TEXT NOT NULL,
  space_id    TEXT NOT NULL,
  wal_pos     INTEGER NOT NULL,  -- References st_wal.pos
  processed_at INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, space_id, wal_pos)
);

CREATE INDEX idx_pipeline_processed_lookup 
  ON st_pipeline_processed(pipeline_id, space_id, wal_pos);

-- Table 2: Queryable pipeline status (for /status API)
CREATE TABLE IF NOT EXISTS st_pipeline_status (
  pipeline_id TEXT NOT NULL,
  wal_pos     INTEGER NOT NULL,  -- References st_wal.pos
  status      TEXT NOT NULL,  -- OK, ERROR, DEFERRED
  duration_ms INTEGER,
  error_kind  TEXT,
  error_msg   TEXT,
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, wal_pos)
);

CREATE INDEX idx_pipeline_status_query 
  ON st_pipeline_status(pipeline_id, wal_pos);

-- Table 3: Watermark ledger for compaction
CREATE TABLE IF NOT EXISTS st_pipeline_watermarks (
  pipeline_id TEXT NOT NULL,
  space_id    TEXT NOT NULL,
  watermark   INTEGER NOT NULL,  -- Max processed wal_pos before compaction
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, space_id)
);

-- OPTIONAL: Enhance st_dlq with error categorization
-- (Architecture doc wants error_kind/error_fingerprint, current has 'reason')
ALTER TABLE st_dlq ADD COLUMN error_kind TEXT;
ALTER TABLE st_dlq ADD COLUMN error_fingerprint TEXT;

CREATE INDEX IF NOT EXISTS idx_dlq_error_fingerprint ON st_dlq(error_fingerprint);

COMMIT;
```

**Effort:** 30 min (write SQL) + 15 min (test migration) = 45 min

### 3. Pipeline Directory Structure

**Need to CREATE:**

```
k0/
  pipelines/  # ❌ NEW DIRECTORY
    __init__.py  # ❌ NEW - empty file
    protocol.py  # ❌ NEW - PipelineProtocol definition
```

**`k0/pipelines/__init__.py`:**
```python
"""User-space pipeline infrastructure."""

__all__ = []
```

**`k0/pipelines/protocol.py`:**
```python
"""Pipeline protocol definition - canonical interface for K0 pipelines."""

from typing import Protocol, Sequence, runtime_checkable
from dataclasses import dataclass

@dataclass
class BusMessage:
    """Message dispatched from bus to pipeline handlers."""
    topic: str
    payload: bytes
    offset: int
    trace_id: str | None = None

@runtime_checkable
class PipelineProtocol(Protocol):
    """
    Canonical interface for K0 pipelines.
    
    All pipelines must implement this protocol for auto-discovery.
    """
    
    # CLASS-LEVEL CONTRACT (must be class properties, not instance)
    pipeline_id: str  # e.g., "P02"
    contract_version: int  # Schema version for compatibility
    declared_topics: Sequence[str]  # Topics this pipeline subscribes to
    concurrency: int  # Max concurrent handlers (default: 1)
    max_queue: int  # Max pending messages (default: 512)
    required_caps: Sequence[str]  # Capability requirements (e.g., ["st_hipp_store.write"])
    
    # LIFECYCLE METHODS
    async def on_startup(self, ctx: "PipelineContext") -> None:
        """
        Called once on kernel boot.
        
        Initialize resources (ProcessPoolExecutor, caches, etc.).
        """
        ...
    
    async def on_shutdown(self) -> None:
        """
        Called on graceful shutdown.
        
        Clean up resources (close pools, flush caches, etc.).
        """
        ...
    
    async def handle(self, msg: BusMessage) -> None:
        """
        Process single message.
        
        MUST be idempotent (may receive duplicates after crash).
        MUST check per-space ordering before processing.
        MUST emit receipt to st_pipeline_status.
        """
        ...

@dataclass
class PipelineContext:
    """Context provided to pipelines at startup."""
    syscalls: "Syscalls"  # Capability-gated storage access (M2)
    config: dict  # Pipeline-specific config from k0/config/pipelines.yml
    logger: "Logger"  # Structured logger with cognitive_trace_id
```

**Effort:** 15 min (create files) + 15 min (write protocol) = 30 min

---

## Updated Milestone 1 Requirements

### R1.1: BusDispatcher v2 - Topic-Based Subscription ⏱️ 1.5 hours

**Changes Required:**

1. Update `k0/bus/core.py`:
   - Add `_taps: List[BusSink]` attribute
   - Add `_topic_subs: dict[str, list[BusSink]]` attribute
   - Add `subscribe(topic, handler)` method
   - Add `tap(handler)` method
   - Add deprecation warning to `register_sink()`
   - Update `_fan_out()` to dispatch to topic subscribers + taps + legacy sinks

2. Update `k0/kernel/app.py` lines 341-343:
   - Change `bus_dispatcher.register_sink(observability_sink)` → `bus_dispatcher.tap(observability_sink)`
   - Change `bus_dispatcher.register_sink(driver_worker_pool_sink)` → `bus_dispatcher.tap(driver_worker_pool_sink)`
   - Change `bus_dispatcher.register_sink(sse_fan_out_sink)` → `bus_dispatcher.tap(sse_fan_out_sink)`

3. Create `tests/k0/bus/test_dispatcher_v2.py`:
   - Test `subscribe()` registers handler for topic
   - Test `tap()` receives all messages
   - Test topic dispatch only calls subscribed handlers (O(k) not O(N))
   - Test legacy `register_sink()` shows deprecation warning
   - Test backward compatibility (old code still works)

**Acceptance Criteria:**
- [ ] `subscribe(topic, handler)` method exists
- [ ] `tap(handler)` method exists
- [ ] Kernel sinks migrated to `tap()` in app.py
- [ ] `register_sink()` shows deprecation warning
- [ ] Unit test: topic dispatch only calls subscribed handlers
- [ ] Unit test: taps receive all messages
- [ ] Backward compatibility maintained

**Files:**
- `k0/bus/core.py` (UPDATE - add 2 methods, update dispatch)
- `k0/kernel/app.py` (UPDATE - 3 lines changed)
- `tests/k0/bus/test_dispatcher_v2.py` (NEW - 200 lines)

---

### R1.2: DDL Migrations - Pipeline Tables ⏱️ 45 min

**Changes Required:**

1. Create `k0/contracts/sql/migrations/0012_pipeline_infrastructure.sql`:
   - CREATE st_pipeline_processed (per-space idempotency ledger)
   - CREATE st_pipeline_status (queryable pipeline receipts)
   - CREATE st_pipeline_watermarks (compaction support)
   - OPTIONAL: ALTER st_dlq ADD error_kind, error_fingerprint

2. Test migration:
   - Run: `python -m pytest tests/k0/storage/test_migrations.py -k 0012`
   - Verify tables created
   - Verify indexes created
   - Verify idempotent (can run twice)

**Acceptance Criteria:**
- [ ] Migration 0012 file created
- [ ] All 3 tables created successfully
- [ ] Indexes created for performance
- [ ] Migration is idempotent (IF NOT EXISTS)
- [ ] Schema verified: `sqlite3 k0_runtime.sqlite3 ".schema st_pipeline_processed"`
- [ ] Test: `test_migration_0012_idempotent()` passes

**Files:**
- `k0/contracts/sql/migrations/0012_pipeline_infrastructure.sql` (NEW - 60 lines)
- `tests/k0/storage/test_migrations_pipeline.py` (NEW - 100 lines)

---

### R1.3: PipelineProtocol Definition ⏱️ 30 min

**Changes Required:**

1. Create `k0/pipelines/` directory
2. Create `k0/pipelines/__init__.py` (empty file)
3. Create `k0/pipelines/protocol.py`:
   - Define `BusMessage` dataclass
   - Define `PipelineProtocol` with `@runtime_checkable`
   - Define `PipelineContext` dataclass
   - Add docstrings for all methods

4. Create `tests/k0/pipelines/test_protocol.py`:
   - Test `isinstance()` works with `@runtime_checkable`
   - Test protocol validation (missing attributes should fail)

**Acceptance Criteria:**
- [ ] `k0/pipelines/` directory created
- [ ] `PipelineProtocol` defined with `@runtime_checkable`
- [ ] All 7 required class properties documented
- [ ] All 3 lifecycle methods documented (on_startup, on_shutdown, handle)
- [ ] `BusMessage` dataclass defined
- [ ] `PipelineContext` dataclass defined
- [ ] Type hints for all methods
- [ ] Unit test: `isinstance(obj, PipelineProtocol)` works

**Files:**
- `k0/pipelines/__init__.py` (NEW - 3 lines)
- `k0/pipelines/protocol.py` (NEW - 100 lines)
- `tests/k0/pipelines/test_protocol.py` (NEW - 50 lines)

---

## Updated Timeline

| Requirement | Old Estimate | New Estimate | Savings | Reason |
|-------------|--------------|--------------|---------|--------|
| R1.1: BusDispatcher v2 | 2h | 1.5h | -0.5h | Existing dispatcher structure |
| R1.2: DDL Migrations | 1h | 0.75h | -0.25h | No WAL/Outbox changes needed |
| R1.3: PipelineProtocol | 1h | 0.5h | -0.5h | Simpler than expected |
| **TOTAL** | **3h** | **2h** | **-1h** | **33% faster** |

---

## Milestone 1 Acceptance Criteria (ALL MUST PASS)

- [ ] **R1.1 Complete:** BusDispatcher v2 with `subscribe()` + `tap()` APIs
- [ ] **R1.2 Complete:** 3 pipeline tables created via migration 0012
- [ ] **R1.3 Complete:** PipelineProtocol defined and documented
- [ ] **All unit tests pass:** `python -m pytest tests/k0/bus/ tests/k0/storage/ tests/k0/pipelines/ -v`
- [ ] **Kernel boots successfully:** No regressions in existing functionality
- [ ] **Backward compatible:** Existing code works with deprecation warnings only
- [ ] **Migration applied:** `sqlite3 k0_runtime.sqlite3 ".tables"` shows new tables

---

## Milestone 1 Deliverables

```
k0/
  bus/
    core.py (UPDATED - add subscribe/tap, 50 lines changed)
  contracts/
    sql/
      migrations/
        0012_pipeline_infrastructure.sql (NEW - 60 lines)
  pipelines/ (NEW DIRECTORY)
    __init__.py (NEW - 3 lines)
    protocol.py (NEW - 100 lines)
  kernel/
    app.py (UPDATED - 3 lines changed to use tap())

tests/
  k0/
    bus/
      test_dispatcher_v2.py (NEW - 200 lines)
    storage/
      test_migrations_pipeline.py (NEW - 100 lines)
    pipelines/
      test_protocol.py (NEW - 50 lines)
```

**Total New Code:** ~563 lines  
**Total Changes:** 53 lines updated  
**Total Tests:** 350 lines

---

## Key Architectural Decisions

### 1. Use `st_wal.pos` (not `wal_pos`)

**Decision:** Keep existing field name `pos` instead of renaming to `wal_pos`

**Rationale:**
- Architecture doc calls it `wal_pos` but actual K0 implementation uses `pos`
- Renaming would require migration + code changes across codebase
- `pos` is already PRIMARY KEY AUTOINCREMENT (monotonic)
- st_outbox already references it as `wal_pos` column (different context)

**Impact:** None - just a naming difference. Documentation will note this.

### 2. Keep Existing DLQ Table

**Decision:** Optionally enhance st_dlq (don't recreate)

**Rationale:**
- st_dlq table already exists with 90% of needed fields
- Has: wal_pos, tenant_id, space_id, driver, payload, retries, timestamps
- Missing: error_kind, error_fingerprint (nice-to-have for categorization)
- Can add columns via ALTER TABLE (non-breaking)

**Impact:** Migration 0012 includes OPTIONAL ALTER TABLE for st_dlq enhancements.

### 3. Deprecate `register_sink()` (Don't Remove)

**Decision:** Keep `register_sink()` with deprecation warning

**Rationale:**
- Maintain backward compatibility for existing code
- Allow gradual migration to `subscribe()`/`tap()`
- Gives users time to adapt
- CI can fail if new code uses deprecated method

**Impact:** No breaking changes. Old code works but shows warnings.

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| BusDispatcher dispatch regression | LOW | HIGH | Extensive unit tests, maintain legacy path |
| Migration 0012 fails on existing DBs | LOW | MEDIUM | Test on fresh + existing DBs, use IF NOT EXISTS |
| Protocol too restrictive | MEDIUM | MEDIUM | Use Protocol (not ABC) for flexibility |
| Backward compatibility breaks | LOW | HIGH | Keep register_sink(), add deprecation warning |

---

## Next Steps After M1 Complete

1. **Verify Kernel Boots:** `python k0/kernel/app.py` (no errors)
2. **Check Tables Created:** `sqlite3 k0_runtime.sqlite3 ".tables"` (see st_pipeline_*)
3. **Run Full Test Suite:** `python -m pytest tests/k0/ -v` (all pass)
4. **Move to M2:** Start implementing Loader + Syscalls

---

## Questions for Review

1. **Do we want to rename `st_wal.pos` to `wal_pos`?**
   - Recommendation: NO (breaking change, existing name works fine)

2. **Should DLQ enhancement be mandatory or optional?**
   - Recommendation: OPTIONAL (add if needed, not blocking)

3. **Should we remove `register_sink()` completely?**
   - Recommendation: NO (deprecate only, maintain backward compatibility)

4. **Do we need config file support in M1?**
   - Recommendation: DEFER to M2 (not blocking foundation)

---

**Ready to start M1 implementation?** 🚀

The plan is now accurate, realistic, and based on actual K0 code inspection.
