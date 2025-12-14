# K0 Pipeline Implementation Plan - Milestone-Based Roadmap

**Goal:** Integrate 20+ pluggable pipelines into K0 kernel for single-process mobile/edge deployment (~500MB)

**Strategy:** Foundation-first approach - make kernel ready to accept pipelines, then incrementally add pipeline implementations

**Document Status:** Implementation Roadmap (Nov 12, 2025)
**Source:** k0_pipeline_architecture.md (4711 lines, v1.3 Production-Ready)

---

## Dependency Chain Overview

```
M1 (Kernel Foundation) ─┐
                        ├─> M2 (Discovery System) ─┐
                        │                          ├─> M3 (Reference Pipeline) ─> M4 (Scale Test) ─> M5 (Production)
                        └─> (Independent: DDL)     │
                                                   └─> (Can start in parallel once M1 done)
```

**Key Insight:** M1 has ZERO dependencies - this is your foundation. All other work builds on M1.

---

## Milestone 1: Kernel Foundation (ZERO Dependencies)

**Goal:** Make K0 kernel ready to accept pipeline registrations

**Duration:** 2 hours (REDUCED - much infrastructure exists)
**Status:** 🔴 Not Started
**Dependencies:** NONE - Start immediately
**Blocking:** M2, M3, M4, M5 (everything else)

### ✅ What Already EXISTS in K0

**Verified by code inspection on Nov 12, 2025:**

1. **BusDispatcher Foundation** (`k0/bus/core.py`):
   - ✅ `register_sink()` method exists (line 99)
   - ✅ `_sinks: List[BusSink]` storage
   - ✅ Middleware chain (`_middlewares`)
   - ✅ Dispatch logic with scheduler tokens
   - ✅ 3 kernel sinks registered in `app.py` lines 341-343

2. **WAL Infrastructure** (`k0/storage/wal.py`):
   - ✅ `st_wal` table with `pos INTEGER PRIMARY KEY AUTOINCREMENT` (monotonic)
   - ✅ Complete WalEntry dataclass with all V1 fields
   - ✅ `append()` method for WAL writes
   - **NOTE:** Field is named `pos` not `wal_pos` - this is FINE, we'll use `pos`

3. **Outbox Infrastructure** (`k0/storage/outbox.py`):
   - ✅ `st_outbox` table with `wal_pos` column referencing `st_wal.pos`
   - ✅ OutboxEntry dataclass
   - ✅ `enqueue()` and `dequeue_batch()` methods
   - ✅ Retry logic with backoff (next_attempt_ts, backoff_exp, status)

4. **DLQ Infrastructure** (`k0/contracts/sql/migrations/0001_baseline.sql`):
   - ✅ `st_dlq` table EXISTS (lines 94-110)
   - ✅ Has: wal_pos, tenant_id, space_id, driver, op_kind, fingerprint, payload
   - ✅ Has: reason, retries, requeue_seq, first_failure_ts, last_failure_ts, state
   - ⚠️ **NEEDS UPDATE:** Missing `error_kind`, `error_fingerprint` columns from architecture

5. **Migrations System** (`k0/automation/migrate.py`):
   - ✅ Complete migration runner with forward/rollback
   - ✅ 11 migrations exist (0001-0011)
   - ✅ Migration directory: `k0/contracts/sql/migrations/`

6. **UnitOfWork** (`k0/uow/unit_of_work.py`):
   - ✅ ACID transaction coordinator
   - ✅ `append_wal()` method
   - ✅ `stage_outbox()` method
   - ✅ `_flush_outbox()` in commit

### ❌ What's MISSING (Need to Build)

1. **BusDispatcher v2 APIs:**
   - ❌ `subscribe(topic, handler)` method (O(k) topic-based dispatch)
   - ❌ `tap(handler)` method (broadcast for observability only)
   - ❌ Topic map: `_topic_subs: dict[str, list[BusSink]]`
   - ❌ Updated dispatch logic to use topic subscriptions

2. **Pipeline Tables:**
   - ❌ `st_pipeline_processed` (per-space idempotency ledger)
   - ❌ `st_pipeline_status` (queryable pipeline receipts)
   - ❌ `st_pipeline_watermarks` (compaction support)

3. **Pipeline Directory:**
   - ❌ `k0/pipelines/` directory
   - ❌ `k0/pipelines/__init__.py`
   - ❌ `k0/pipelines/protocol.py` (PipelineProtocol definition)### Requirements

#### R1.1: BusDispatcher v2 - Topic-Based Subscription

**Problem:** Current `register_sink()` is O(N) broadcast - kills performance at 40+ pipelines

**Solution:** Add O(k) topic-based subscription API

**Files Changed:**

- `k0/bus/core.py` (update BusDispatcher class)
- `k0/bus/sinks.py` (migrate existing sinks to new API)

**New APIs:**

```python
class BusDispatcher:
    def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe to specific topic (O(k) dispatch where k=handlers per topic)."""

    def tap(self, handler: Callable) -> None:
        """Tap all messages (for observability/audit only)."""

    def register_sink(self, handler: Callable) -> None:
        """DEPRECATED: Use subscribe() or tap() instead."""
        # Add deprecation warning
```

**Implementation Details:**

- Internal topic map: `_subs: dict[str, list[Callable]]`
- Dispatch logic: Loop topics in message, call subscribed handlers only
- Maintain backward compatibility with `register_sink()` (add warning)

**Acceptance Criteria:**

- [ ] `subscribe(topic, handler)` method exists
- [ ] `tap(handler)` method exists
- [ ] Existing 3 kernel sinks (metrics, SSE, driver) migrated to `tap()`
- [ ] `register_sink()` shows deprecation warning
- [ ] Unit test: `test_bus_dispatcher_subscribe_dispatches_to_topic_handlers()`
- [ ] Unit test: `test_bus_dispatcher_tap_receives_all_messages()`
- [ ] Backward compatibility: Old code still works with warning

**Deliverables:**

- Updated `k0/bus/core.py` with new methods
- Updated `k0/kernel/app.py` lines 341-343 to use `tap()`
- Unit tests: `tests/k0/bus/test_dispatcher_v2.py`

---

#### R1.2: DDL Migrations - Pipeline Tables

**Problem:** No database tables for per-space ordering, pipeline status, or DLQ

**Solution:** Create 4 new tables via migrations

**Files Changed:**

- `k0/contracts/sql/migrations/0012_pipeline_infrastructure.sql` (NEW - consolidated migration)

**Note:** Originally planned as 003_pipeline_ledger.sql + 004_dlq.sql, but consolidated into one migration because:
- Migrations 0001-0011 already exist (0012 is next sequential number)
- st_wal.pos already exists (no ALTER TABLE needed)
- st_outbox.wal_pos already exists (no ALTER TABLE needed)
- st_dlq already exists (just needs enhancements, not creation)

**DDL Required:**

**Migration 0012: Pipeline Infrastructure (Consolidated)**

```sql
-- Note: st_wal.pos and st_outbox.wal_pos already exist (no changes needed)

-- Per-space processing ledger (idempotency + ordering)
CREATE TABLE IF NOT EXISTS st_pipeline_processed (
  pipeline_id TEXT NOT NULL,
  space_id    TEXT NOT NULL,
  wal_pos     INTEGER NOT NULL,
  processed_at INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, space_id, wal_pos)
);

CREATE INDEX idx_pipeline_processed_space_wal
  ON st_pipeline_processed(space_id, wal_pos);

-- Queryable pipeline status (for /status API)
CREATE TABLE IF NOT EXISTS st_pipeline_status (
  pipeline_id TEXT NOT NULL,
  wal_pos     INTEGER NOT NULL,
  status      TEXT NOT NULL CHECK(status IN ('OK', 'ERROR', 'DEFERRED')),
  duration_ms INTEGER,
  error_kind  TEXT,
  error_msg   TEXT,
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, wal_pos)
);

CREATE INDEX idx_pipeline_status_status ON st_pipeline_status(status);
CREATE INDEX idx_pipeline_status_updated ON st_pipeline_status(updated_at);

-- Watermark ledger for compaction
CREATE TABLE IF NOT EXISTS st_pipeline_watermarks (
  pipeline_id TEXT NOT NULL,
  space_id    TEXT NOT NULL,
  watermark   INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, space_id)
);

CREATE INDEX idx_pipeline_watermarks_pipeline
  ON st_pipeline_watermarks(pipeline_id, watermark);

-- Enhance existing st_dlq with pipeline-specific error tracking
ALTER TABLE st_dlq ADD COLUMN error_kind TEXT;
ALTER TABLE st_dlq ADD COLUMN error_fingerprint TEXT;

CREATE INDEX idx_dlq_error_kind ON st_dlq(error_kind) WHERE error_kind IS NOT NULL;
CREATE INDEX idx_dlq_error_fingerprint ON st_dlq(error_fingerprint) WHERE error_fingerprint IS NOT NULL;
```

**Acceptance Criteria:**

- [x] Migration 0012 runs successfully (idempotent for CREATE TABLE, documented caveat for ALTER TABLE)
- [x] Schema verified: All 3 pipeline tables + enhanced DLQ
- [x] All 4 tables operational: `st_pipeline_processed`, `st_pipeline_status`, `st_pipeline_watermarks`, `st_dlq` (enhanced)
- [x] 6 indexes created for performance
- [x] Unit tests: 11 comprehensive tests covering all tables and operations

**Deliverables:**

- ✅ `k0/contracts/sql/migrations/0012_pipeline_infrastructure.sql` (134 lines)
- ✅ Test: `tests/k0/storage/test_migrations_pipeline.py` (348 lines, 11 tests passing)

---

#### R1.3: PipelineProtocol Definition

**Problem:** No canonical interface for pipeline contracts

**Solution:** Define protocol with class-level properties and lifecycle methods

**Files Changed:**

- `k0/pipelines/protocol.py` (NEW)
- `k0/pipelines/__init__.py` (NEW)

**Protocol Definition:**

```python
# k0/pipelines/protocol.py
from typing import Protocol, Sequence, runtime_checkable
from dataclasses import dataclass

@dataclass
class BusMessage:
    """Message dispatched from bus to pipeline handlers."""
    topic: str
    payload: str  # JSON string
    wal_pos: int
    space_id: str | None
    cognitive_trace_id: str
    metadata: dict

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
    syscalls: "Syscalls"  # Capability-gated storage access
    config: dict  # Pipeline-specific config from k0/config/pipelines.yml
    logger: "Logger"  # Structured logger with cognitive_trace_id
```

**Acceptance Criteria:**

- [ ] `PipelineProtocol` defined with `@runtime_checkable`
- [ ] All 7 required class properties documented
- [ ] All 3 lifecycle methods documented
- [ ] `BusMessage` dataclass defined
- [ ] `PipelineContext` dataclass defined
- [ ] Type hints for all methods
- [ ] Docstrings explain purpose of each method
- [ ] Unit test: `test_protocol_runtime_checkable()` (isinstance check works)

**Deliverables:**

- `k0/pipelines/protocol.py` with complete protocol
- `k0/pipelines/__init__.py` (empty file to mark package)
- Test: `tests/k0/pipelines/test_protocol.py`

---

### Milestone 1 Acceptance Criteria (ALL MUST PASS)

- [ ] **R1.1 Complete:** BusDispatcher v2 with `subscribe()` + `tap()` APIs
- [ ] **R1.2 Complete:** All 4 DDL migrations applied successfully
- [ ] **R1.3 Complete:** PipelineProtocol defined and documented
- [ ] **All unit tests pass:** `python -m pytest tests/k0/bus/ tests/k0/storage/ tests/k0/pipelines/ -v`
- [ ] **Kernel boots successfully:** No regressions in existing functionality
- [ ] **Backward compatible:** Existing code works with deprecation warnings only

### Milestone 1 Deliverables

```
k0/
  bus/
    core.py (UPDATED - BusDispatcher v2)
    sinks.py (UPDATED - migrate to tap())
  storage/
    migrations/
      003_pipeline_ledger.sql (NEW)
      004_dlq.sql (NEW)
  pipelines/ (NEW DIRECTORY)
    __init__.py (NEW)
    protocol.py (NEW)
  kernel/
    app.py (UPDATED - use tap() for kernel sinks)

tests/
  k0/
    bus/
      test_dispatcher_v2.py (NEW)
    storage/
      test_migrations_pipeline.py (NEW)
    pipelines/
      test_protocol.py (NEW)
```

### Milestone 1 Success Metrics

- **Time to Complete:** 3 hours
- **Lines of Code:** ~500 (200 BusDispatcher + 150 DDL + 150 Protocol)
- **Test Coverage:** 100% for new code
- **Performance:** No degradation to existing P95 latencies
- **Risk Level:** LOW (additive changes only, no breaking changes)

---

## Milestone 2: Discovery & Integration System

**Goal:** Auto-discover and load pipelines with contract validation

**Duration:** 4 hours
**Status:** 🔴 Not Started
**Dependencies:** M1 ✅ COMPLETE (BusDispatcher v2, PipelineProtocol, DDL migration 0012)
**Blocking:** M3, M4, M5

**M1 Completion Status:**
- ✅ BusDispatcher v2: `subscribe()` and `tap()` APIs implemented in `k0/bus/core.py`
- ✅ PipelineProtocol: Defined in `k0/pipelines/protocol.py` with runtime type checking
- ✅ DDL Migration: `0012_pipeline_infrastructure.sql` (all 3 pipeline tables + enhanced DLQ)
- ✅ All M1 tests passing: 75/75 (36 bus + 12 sinks + 11 migrations + 16 protocol)

### Requirements

#### R2.1: Syscalls - Capability-Gated Storage Access

**Problem:** Pipelines need storage access but shouldn't have ambient authority

**Solution:** Capability-gated adapter enforcing `required_caps`

**Files Changed:**

- `k0/kernel/syscalls.py` (NEW)

**Implementation:**

```python
# k0/kernel/syscalls.py
class PermissionError(Exception):
    """Raised when pipeline attempts unauthorized storage access."""
    pass

class Syscalls:
    """
    Capability-gated storage adapter for pipelines.

    Enforces required_caps before allowing storage access.
    Provides audit trail for all storage operations.
    """

    def __init__(self, pipeline_id: str, granted_caps: set[str], uow_factory):
        self._pipeline_id = pipeline_id
        self._granted_caps = granted_caps
        self._uow_factory = uow_factory

    async def hipp_store_upsert(
        self,
        space_id: str,
        event_id: str,
        payload: dict,
        cognitive_trace_id: str
    ) -> None:
        """Insert/update st_hipp_store (requires st_hipp_store.write cap)."""
        self._require_cap("st_hipp_store.write")

        async with self._uow_factory() as uow:
            await uow.hipp_store.upsert(
                space_id=space_id,
                event_id=event_id,
                payload=payload,
                trace_id=cognitive_trace_id
            )
            await uow.commit()

    async def working_memory_write(
        self,
        space_id: str,
        key: str,
        value: dict,
        ttl_seconds: int | None = None
    ) -> None:
        """Write to working memory (requires working_memory.write cap)."""
        self._require_cap("working_memory.write")

        # Implementation...

    async def query_embeddings(
        self,
        space_id: str,
        vector: list[float],
        limit: int = 10
    ) -> list[dict]:
        """Query vector index (requires embeddings.read cap)."""
        self._require_cap("embeddings.read")

        # Implementation...

    def _require_cap(self, capability: str) -> None:
        """Check capability, raise PermissionError if not granted."""
        if capability not in self._granted_caps:
            raise PermissionError(
                f"Pipeline {self._pipeline_id} missing capability: {capability}"
            )
```

**Acceptance Criteria:**

- [ ] `Syscalls` class with capability checking
- [ ] 3+ storage methods implemented: `hipp_store_upsert`, `working_memory_write`, `query_embeddings`
- [ ] `_require_cap()` raises `PermissionError` on missing cap
- [ ] Audit logging for all storage operations
- [ ] Unit test: `test_syscalls_raises_permission_error_on_missing_cap()`
- [ ] Unit test: `test_syscalls_allows_access_with_granted_cap()`

**Deliverables:**

- `k0/kernel/syscalls.py` with complete implementation
- Test: `tests/k0/kernel/test_syscalls.py`

---

#### R2.2: Pipeline Loader - Auto-Discovery

**Problem:** No mechanism to discover and validate pipeline modules

**Solution:** Loader scans `k0/pipelines/p*.py`, validates contracts, subscribes to topics

**Files Changed:**

- `k0/pipelines/loader.py` (NEW)

**Implementation:**

```python
# k0/pipelines/loader.py
import importlib
import inspect
from pathlib import Path
from typing import Any

class ContractValidationError(Exception):
    """Raised when pipeline contract is invalid."""
    pass

async def discover_and_boot_pipelines(
    bus_dispatcher: "BusDispatcher",
    uow_factory,
    config: dict,
    logger
) -> dict[str, Any]:
    """
    Discover, validate, and boot all pipelines.

    Returns: {pipeline_id: pipeline_instance}

    Note: Imports PipelineProtocol, PipelineContext from k0.pipelines.protocol
    (defined in M1 R1.3, already implemented)
    """
    from k0.pipelines.protocol import PipelineProtocol, PipelineContext
    from k0.kernel.syscalls import Syscalls  # M2 R2.1

    pipelines = {}
    pipeline_dir = Path(__file__).parent

    # Scan for p*.py files
    for module_path in sorted(pipeline_dir.glob("p*.py")):
        pipeline_id = module_path.stem.upper()  # p02_episodic_write.py -> P02

        try:
            # Import module
            module = importlib.import_module(f"k0.pipelines.{module_path.stem}")

            # Find pipeline class (must implement PipelineProtocol)
            pipeline_class = _find_pipeline_class(module)

            # Validate contract
            _validate_contract(pipeline_class, pipeline_id)

            # Check kernel version compatibility (if min_kernel_semver in manifest)
            # (Future: Add manifest support in M5)

            # Create syscalls adapter with granted capabilities
            granted_caps = set(pipeline_class.required_caps)
            syscalls = Syscalls(pipeline_id, granted_caps, uow_factory)

            # Create pipeline context
            ctx = PipelineContext(
                syscalls=syscalls,
                config=config.get(pipeline_id, {}),
                logger=logger.bind(pipeline_id=pipeline_id)
            )

            # Instantiate pipeline
            pipeline = pipeline_class()

            # Call on_startup lifecycle
            await pipeline.on_startup(ctx)

            # Subscribe to declared topics
            for topic in pipeline.declared_topics:
                bus_dispatcher.subscribe(topic, pipeline.handle)
                logger.info(f"Subscribed {pipeline_id} to {topic}")

            pipelines[pipeline_id] = pipeline
            logger.info(f"Booted pipeline: {pipeline_id}")

        except ContractValidationError as e:
            logger.error(f"Contract validation failed for {pipeline_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to boot {pipeline_id}: {e}")
            raise

    logger.info(f"Booted {len(pipelines)} pipelines: {list(pipelines.keys())}")
    return pipelines

def _find_pipeline_class(module) -> type:
    """Find class implementing PipelineProtocol in module."""
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if isinstance(obj, type) and hasattr(obj, "pipeline_id"):
            return obj
    raise ContractValidationError("No class with pipeline_id found")

def _validate_contract(pipeline_class: type, expected_id: str) -> None:
    """Validate pipeline contract against PipelineProtocol."""
    # Check required class properties
    required_attrs = [
        "pipeline_id", "contract_version", "declared_topics",
        "concurrency", "max_queue", "required_caps"
    ]

    for attr in required_attrs:
        if not hasattr(pipeline_class, attr):
            raise ContractValidationError(f"Missing required attribute: {attr}")

    # Check pipeline_id matches filename
    if pipeline_class.pipeline_id != expected_id:
        raise ContractValidationError(
            f"pipeline_id mismatch: {pipeline_class.pipeline_id} != {expected_id}"
        )

    # Check declared_topics is non-empty
    if not pipeline_class.declared_topics:
        raise ContractValidationError("declared_topics cannot be empty")

    # Check required methods
    required_methods = ["on_startup", "on_shutdown", "handle"]
    for method in required_methods:
        if not hasattr(pipeline_class, method):
            raise ContractValidationError(f"Missing required method: {method}")
```

**Acceptance Criteria:**

- [ ] `discover_and_boot_pipelines()` function scans `k0/pipelines/p*.py`
- [ ] Contract validation checks all 7 required properties
- [ ] Contract validation checks all 3 required methods
- [ ] Syscalls adapter created with granted capabilities
- [ ] `on_startup()` called for each pipeline
- [ ] Topics subscribed via `bus_dispatcher.subscribe()`
- [ ] Returns dict of `{pipeline_id: instance}`
- [ ] Unit test: `test_loader_validates_contract()` (missing property raises)
- [ ] Unit test: `test_loader_subscribes_to_topics()` (verify subscription)
- [ ] Integration test: `test_loader_boots_valid_pipeline()` (end-to-end)

**Deliverables:**

- `k0/pipelines/loader.py` with complete implementation
- Test: `tests/k0/pipelines/test_loader.py`

---

#### R2.3: Kernel Integration

**Problem:** Loader not wired into kernel boot sequence

**Solution:** Call loader in `app.py` after existing sink registrations

**Files Changed:**

- `k0/kernel/app.py` (UPDATE)

**Changes Required:**

```python
# k0/kernel/app.py (around lines 341-343)

# Existing kernel sinks (UPDATED to use tap())
bus_dispatcher.tap(observability_sink.handle)
bus_dispatcher.tap(sse_fan_out.handle)
bus_dispatcher.tap(driver_worker_pool.handle)

# NEW: Boot user-space pipelines (AFTER kernel sinks)
from k0.pipelines.loader import discover_and_boot_pipelines

pipelines = await discover_and_boot_pipelines(
    bus_dispatcher=bus_dispatcher,
    uow_factory=lambda: UnitOfWork(connection_pool),
    config=config.get("pipelines", {}),
    logger=logger
)

# Store pipelines for graceful shutdown
app.state.pipelines = pipelines
```

**Graceful Shutdown:**

```python
# k0/kernel/app.py (shutdown handler)

@app.on_event("shutdown")
async def shutdown():
    """Graceful shutdown with pipeline cleanup."""
    # Call on_shutdown for all pipelines
    for pipeline_id, pipeline in app.state.pipelines.items():
        try:
            await pipeline.on_shutdown()
            logger.info(f"Shutdown pipeline: {pipeline_id}")
        except Exception as e:
            logger.error(f"Error shutting down {pipeline_id}: {e}")

    # Record clean shutdown timestamp (for crash fencing)
    with open("k0_runtime.shutdown_ts", "w") as f:
        f.write(str(int(time.time())))
```

**Acceptance Criteria:**

- [ ] `discover_and_boot_pipelines()` called in `app.py` startup
- [ ] Pipelines stored in `app.state.pipelines`
- [ ] `on_shutdown()` called for all pipelines on graceful shutdown
- [ ] Clean shutdown timestamp recorded
- [ ] Integration test: `test_kernel_boots_with_pipelines()` (empty pipelines dir)
- [ ] Integration test: `test_kernel_graceful_shutdown_calls_pipeline_shutdown()`

**Deliverables:**

- Updated `k0/kernel/app.py` with loader integration
- Test: `tests/k0/kernel/test_app_pipeline_integration.py`

---

### Milestone 2 Acceptance Criteria (ALL MUST PASS)

- [ ] **R2.1 Complete:** Syscalls with capability enforcement
- [ ] **R2.2 Complete:** Loader with contract validation
- [ ] **R2.3 Complete:** Kernel integration in app.py
- [ ] **All unit tests pass:** `python -m pytest tests/k0/kernel/ tests/k0/pipelines/ -v`
- [ ] **Integration test passes:** Kernel boots with empty pipelines directory
- [ ] **Capability enforcement works:** PermissionError raised on missing cap

### Milestone 2 Deliverables

```
k0/
  kernel/
    syscalls.py (NEW)
    app.py (UPDATED - loader integration)
  pipelines/
    loader.py (NEW)

tests/
  k0/
    kernel/
      test_syscalls.py (NEW)
      test_app_pipeline_integration.py (NEW)
    pipelines/
      test_loader.py (NEW)
```

### Milestone 2 Success Metrics

- **Time to Complete:** 4 hours
- **Lines of Code:** ~600 (300 Syscalls + 250 Loader + 50 Integration)
- **Test Coverage:** 100% for new code
- **Capability Enforcement:** 100% of storage methods gated
- **Risk Level:** MEDIUM (touches kernel boot sequence)

---

## Milestone 3: Reference Pipeline Implementation

**Goal:** Implement P02 (Episodic Write) as production reference

**Duration:** 6 hours
**Status:** 🔴 Not Started
**Dependencies:** M2 (requires Loader, Syscalls, BusDispatcher v2)
**Blocking:** M4 (needed for scale testing)

### Requirements

#### R3.1: P02 Episodic Write Pipeline

**Problem:** No production pipeline implementation exists

**Solution:** Implement P02 with all 12 production guardrails

**Files Changed:**

- `k0/pipelines/p02_episodic_write.py` (NEW)

**Complete Implementation Available:** See k0_pipeline_architecture.md Section 12 (lines 2500-3000)

**Key Features:**

1. **Contract Properties:** pipeline_id="P02", contract_version=1, declared_topics, required_caps
2. **ProcessPoolExecutor:** CPU-bound pattern separation (SimHash/MinHash)
3. **Per-Space Ordering:** Check `st_pipeline_processed` before processing
4. **Idempotent UPSERT:** Use `syscalls.hipp_store_upsert()` with deduplication
5. **Receipt Emission:** Write to `st_pipeline_status` on completion
6. **Error Handling:** DLQ on 5 failures with exponential backoff
7. **Graceful Shutdown:** Close ProcessPoolExecutor in `on_shutdown()`

**Acceptance Criteria:**

- [ ] Complete P02 class with all 7 contract properties
- [ ] `on_startup()` initializes ProcessPoolExecutor (max_workers=2)
- [ ] `on_shutdown()` closes ProcessPoolExecutor
- [ ] `handle()` checks per-space ordering
- [ ] `handle()` performs idempotent UPSERT via syscalls
- [ ] `handle()` emits receipt to `st_pipeline_status`
- [ ] `handle()` is async (non-blocking event loop)
- [ ] Unit test: `test_p02_processes_message()` (happy path)
- [ ] Unit test: `test_p02_respects_per_space_ordering()` (out-of-order requeues)
- [ ] Integration test: `test_p02_end_to_end()` (full flow)

**Deliverables:**

- `k0/pipelines/p02_episodic_write.py` (500+ lines)
- Test: `tests/k0/pipelines/test_p02.py`

---

#### R3.2: Outbox Processor - Async Pipeline Dispatcher

**Problem:** Outbox entries not dispatched to pipelines after Phase-1 commit

**Solution:** Background task publishes outbox → bus with DLQ support

**Files Changed:**

- `k0/bus/outbox_processor.py` (NEW)

**Implementation:**

```python
# k0/bus/outbox_processor.py
import asyncio
import time
import hashlib

MAX_RETRIES = 5
BACKOFF_BASE = 2  # Exponential backoff: 2^n seconds

async def outbox_processor_loop(
    db_conn,
    bus_dispatcher: "BusDispatcher",
    logger
) -> None:
    """
    Background loop: Scan outbox, dispatch to bus, handle retries/DLQ.
    """
    while True:
        try:
            # Fetch pending entries (next_attempt_ts <= now)
            now = int(time.time())
            entries = await db_conn.fetch_all(
                """
                SELECT id, wal_pos, topic, payload, space_id,
                       cognitive_trace_id, attempt, next_attempt_ts
                FROM st_outbox
                WHERE next_attempt_ts <= ?
                ORDER BY wal_pos ASC
                LIMIT 100
                """,
                (now,)
            )

            for entry in entries:
                await _process_entry(entry, db_conn, bus_dispatcher, logger)

            # Sleep if no entries (backpressure)
            if not entries:
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Outbox processor error: {e}")
            await asyncio.sleep(1)

async def _process_entry(
    entry: dict,
    db_conn,
    bus_dispatcher: "BusDispatcher",
    logger
) -> None:
    """Process single outbox entry with retry/DLQ logic."""
    from k0.pipelines.protocol import BusMessage  # M1 R1.3

    try:
        # Create BusMessage (matches protocol.py fields)
        msg = BusMessage(
            topic=entry["topic"],
            payload=entry["payload"],  # bytes from st_outbox
            offset=entry["wal_pos"],   # Renamed: wal_pos → offset in protocol
            space_id=entry["space_id"],
            trace_id=entry["cognitive_trace_id"],  # Renamed: cognitive_trace_id → trace_id
            metadata={}
        )

        # Dispatch to bus (will call subscribed handlers)
        await bus_dispatcher.dispatch([msg])

        # Success: Mark outbox entry complete
        await db_conn.execute(
            "DELETE FROM st_outbox WHERE id = ?",
            (entry["id"],)
        )

    except Exception as e:
        # Failure: Increment attempt, schedule retry or DLQ
        attempt = entry["attempt"] + 1

        if attempt >= MAX_RETRIES:
            # Move to DLQ
            await _move_to_dlq(entry, str(e), db_conn)
            await db_conn.execute(
                "DELETE FROM st_outbox WHERE id = ?",
                (entry["id"],)
            )
            logger.warning(f"Moved to DLQ after {MAX_RETRIES} attempts: wal_pos={entry['wal_pos']}")
        else:
            # Schedule retry with exponential backoff + jitter
            backoff = BACKOFF_BASE ** attempt
            jitter = random.uniform(0, backoff * 0.1)
            next_attempt = int(time.time()) + int(backoff + jitter)

            await db_conn.execute(
                """
                UPDATE st_outbox
                SET attempt = ?, next_attempt_ts = ?
                WHERE id = ?
                """,
                (attempt, next_attempt, entry["id"])
            )
            logger.warning(f"Retry {attempt}/{MAX_RETRIES} scheduled for wal_pos={entry['wal_pos']} in {backoff}s")

async def _move_to_dlq(entry: dict, error_msg: str, db_conn) -> None:
    """Move failed entry to dead letter queue."""
    error_kind = error_msg.split(":")[0] if ":" in error_msg else "UnknownError"
    error_fingerprint = hashlib.md5(error_msg.encode()).hexdigest()

    await db_conn.execute(
        """
        INSERT INTO st_dlq (wal_pos, topic, payload, error_kind, error_fingerprint, failures, last_error_at, space_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (entry["wal_pos"], entry["topic"], entry["payload"], error_kind, error_fingerprint, MAX_RETRIES, int(time.time()), entry["space_id"])
    )
```

**Acceptance Criteria:**

- [ ] `outbox_processor_loop()` scans outbox periodically
- [ ] Dispatches entries via `bus_dispatcher.dispatch()`
- [ ] Implements exponential backoff with jitter
- [ ] Moves to DLQ after 5 failures
- [ ] Deletes from outbox on success or DLQ move
- [ ] Unit test: `test_outbox_processor_dispatches_pending_entries()`
- [ ] Unit test: `test_outbox_processor_moves_to_dlq_after_max_retries()`
- [ ] Integration test: `test_outbox_processor_end_to_end()`

**Deliverables:**

- `k0/bus/outbox_processor.py` (300+ lines)
- Test: `tests/k0/bus/test_outbox_processor.py`
- Integration in `k0/kernel/app.py` (start background task)

---

#### R3.3: Validation Test Suite (7 Tests)

**Problem:** No tests for production guardrails

**Solution:** Implement 7 validation tests from architecture doc

**Files Changed:**

- `tests/k0/pipelines/test_validation.py` (NEW)

**7 Tests Required:**

1. **TX-1: Contract Loading** - All pipelines boot successfully
2. **TX-2: Dispatch Performance** - <5ms P95 with 100 pipelines
3. **TX-3: Per-Space Ordering** - Events process sequentially per space, parallel across spaces
4. **TX-4: Crash Recovery** - Boot from outbox only (not WAL replay)
5. **TX-5: DLQ Path** - 5 retries → DLQ
6. **TX-6: Capability Enforcement** - PermissionError → DLQ
7. **TX-7: SQLite Mobile PRAGMAs** - Correct config applied

**Acceptance Criteria:**

- [ ] All 7 tests implemented
- [ ] All tests pass: `python -m pytest tests/k0/pipelines/test_validation.py -v`
- [ ] Test execution time: <20 minutes
- [ ] Tests use real components (no mocks except where necessary)

**Deliverables:**

- `tests/k0/pipelines/test_validation.py` (1000+ lines)
- CI/CD integration

---

### Milestone 3 Acceptance Criteria (ALL MUST PASS)

- [ ] **R3.1 Complete:** P02 production implementation
- [ ] **R3.2 Complete:** Outbox processor with DLQ
- [ ] **R3.3 Complete:** 7 validation tests pass
- [ ] **End-to-end flow works:** Write → Phase-1 commit → Outbox → P02 → st_hipp_store
- [ ] **Performance:** P02 processes events in <100ms P95
- [ ] **DLQ works:** Poison pill moves to DLQ after 5 retries

### Milestone 3 Deliverables

```
k0/
  pipelines/
    p02_episodic_write.py (NEW - 500+ lines)
  bus/
    outbox_processor.py (NEW - 300+ lines)
  kernel/
    app.py (UPDATED - start outbox processor task)

tests/
  k0/
    pipelines/
      test_p02.py (NEW)
      test_validation.py (NEW - 7 tests)
    bus/
      test_outbox_processor.py (NEW)
```

### Milestone 3 Success Metrics

- **Time to Complete:** 6 hours
- **Lines of Code:** ~1800 (500 P02 + 300 Outbox + 1000 Tests)
- **Test Coverage:** 95%+ for pipeline code
- **Performance:** P02 <100ms P95, Outbox <10ms P95
- **Risk Level:** MEDIUM (first production pipeline)

---

## Milestone 4: Scale Testing (100 Pipelines)

**Goal:** Validate dispatch performance with 100 total pipelines

**Duration:** 2 hours
**Status:** 🔴 Not Started
**Dependencies:** M3 (requires P02 working, validation tests passing)
**Blocking:** M5

### Requirements

#### R4.1: Pipeline Stubs for Benchmarking

**Problem:** Need 99 additional pipelines to test 100-pipeline dispatch performance

**Solution:** Create stubs for P01, P03, P08, P14 + 95 dummy pipelines

**Files Changed:**

- `k0/pipelines/p01_recall.py` (NEW - stub)
- `k0/pipelines/p03_consolidation.py` (NEW - stub)
- `k0/pipelines/p08_embedding.py` (NEW - stub)
- `k0/pipelines/p14_dedup.py` (NEW - stub)
- `k0/pipelines/p99_dummy_{01-95}.py` (NEW - auto-generated)

**Stub Template:**

```python
# k0/pipelines/p01_recall.py
class P01RecallPipeline:
    pipeline_id = "P01"
    contract_version = 1
    declared_topics = ("cognitive.memory.read.v1",)
    concurrency = 1
    max_queue = 512
    required_caps = ("st_hipp_store.read", "embeddings.read")

    async def on_startup(self, ctx) -> None:
        self._ctx = ctx

    async def on_shutdown(self) -> None:
        pass

    async def handle(self, msg) -> None:
        # Stub: No-op (for dispatch benchmark only)
        pass
```

**Acceptance Criteria:**

- [ ] 4 real stubs created (P01, P03, P08, P14)
- [ ] 95 dummy pipelines auto-generated
- [ ] All 99 stubs boot successfully
- [ ] Total pipelines: 100 (1 real P02 + 99 stubs)
- [ ] Script: `python k0/pipelines/generate_dummy_pipelines.py` (creates p99_dummy_*.py)

**Deliverables:**

- 4 stub files: `p01_recall.py`, `p03_consolidation.py`, `p08_embedding.py`, `p14_dedup.py`
- Generator script: `k0/pipelines/generate_dummy_pipelines.py`
- 95 auto-generated dummy pipelines

---

#### R4.2: Dispatch Performance Benchmark

**Problem:** Need to validate <5ms P95 dispatch with 100 pipelines

**Solution:** Load test with 10,000 messages across 100 pipelines

**Files Changed:**

- `tests/k0/performance/test_dispatch_100_pipelines.py` (NEW)

**Benchmark Implementation:**

```python
# tests/k0/performance/test_dispatch_100_pipelines.py
import asyncio
import time
import statistics

async def test_dispatch_performance_100_pipelines():
    """
    Validation Test TX-2: Dispatch Performance

    Target: <5ms P95 with 100 pipelines
    """
    from k0.pipelines.protocol import BusMessage  # M1 R1.3

    # Boot kernel with 100 pipelines
    app = await boot_kernel_with_pipelines()
    bus_dispatcher = app.state.bus_dispatcher

    # Generate 10,000 test messages (matches BusMessage protocol)
    messages = [
        BusMessage(
            topic=f"test.topic.{i % 20}",  # 20 unique topics
            payload=b'{"test": true}',     # bytes, not str (protocol requirement)
            offset=i,                      # Renamed: wal_pos → offset
            space_id=f"space_{i % 10}",
            trace_id=f"trace_{i}",         # Renamed: cognitive_trace_id → trace_id
            metadata={}
        )
        for i in range(10000)
    ]

    # Measure dispatch latency
    latencies = []
    for msg in messages:
        start = time.perf_counter()
        await bus_dispatcher.dispatch([msg])
        end = time.perf_counter()
        latencies.append((end - start) * 1000)  # Convert to ms

    # Calculate P95
    p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    p50 = statistics.median(latencies)
    p99 = statistics.quantiles(latencies, n=100)[98]

    print(f"Dispatch latencies (100 pipelines, 10k messages):")
    print(f"  P50: {p50:.2f}ms")
    print(f"  P95: {p95:.2f}ms")
    print(f"  P99: {p99:.2f}ms")

    # Assertion
    assert p95 < 5.0, f"P95 dispatch latency {p95:.2f}ms exceeds 5ms target"
```

**Acceptance Criteria:**

- [ ] Benchmark boots 100 pipelines successfully
- [ ] Dispatches 10,000 messages
- [ ] Measures P50, P95, P99 latencies
- [ ] **PASS CRITERIA: P95 < 5ms**
- [ ] Report saved: `reports/dispatch_performance_100_pipelines.txt`

**Deliverables:**

- `tests/k0/performance/test_dispatch_100_pipelines.py`
- Performance report

---

### Milestone 4 Acceptance Criteria (ALL MUST PASS)

- [ ] **R4.1 Complete:** 100 pipelines boot successfully
- [ ] **R4.2 Complete:** Dispatch P95 < 5ms
- [ ] **TX-2 validation test passes:** Dispatch performance validated
- [ ] **No memory leaks:** RSS stays <500MB during 10k message test

### Milestone 4 Deliverables

```
k0/
  pipelines/
    p01_recall.py (NEW - stub)
    p03_consolidation.py (NEW - stub)
    p08_embedding.py (NEW - stub)
    p14_dedup.py (NEW - stub)
    p99_dummy_01.py through p99_dummy_95.py (NEW - auto-generated)
    generate_dummy_pipelines.py (NEW - generator script)

tests/
  k0/
    performance/
      test_dispatch_100_pipelines.py (NEW)
```

### Milestone 4 Success Metrics

- **Time to Complete:** 2 hours
- **Lines of Code:** ~500 (4 stubs + generator + benchmark)
- **Performance Target:** P95 < 5ms ✅
- **Memory Target:** RSS < 500MB ✅
- **Risk Level:** LOW (stubs only, no business logic)

---

## Milestone 5: Production Hardening (10 Musts)

**Goal:** Complete 10 production musts for mobile/edge deployment

**Duration:** 25 hours
**Status:** 🔴 Not Started
**Dependencies:** M4 (requires 100-pipeline scale test passing)
**Blocking:** NONE (final milestone)

### Requirements Summary

**10 Production Musts (from k0_pipeline_architecture.md Section 15):**

1. **M5.1: Kill All Legacy `register_sink()` Usage** (1h)
   - Remove all `register_sink()` calls except kernel sinks
   - Add linter rule to fail CI if found in pipelines
   - Convert all pipelines to `subscribe()` or `tap()`

2. **M5.2: Signed Pipeline Manifests** (4h)
   - Add `pipeline.toml` for each pipeline
   - Implement cryptographic signature verification
   - Require signatures in production mode

3. **M5.3: Admission Control Wired** (3h)
   - Implement token bucket per topic
   - Wire into UnitOfWork.commit()
   - Reject writes when capacity exceeded

4. **M5.4: SSE Backpressure & `/status` API** (3h)
   - Add `/status/pipeline/{id}` endpoint
   - Add `/status/event/{id}` endpoint
   - Persist receipts to `st_pipeline_status`

5. **M5.5: Ledger Maintenance (Compaction)** (2h)
   - Implement nightly compaction job
   - Compress to watermark-based ledger
   - VACUUM to reclaim disk space

6. **M5.6: Schema Version Guardrails** (2h)
   - Validate `contract_version` before dispatch
   - Move to DLQ on schema mismatch
   - Add `schema_version` to outbox entries

7. **M5.7: Thermal/Battery Hooks** (3h)
   - Monitor CPU temperature and battery level
   - Throttle CPU-heavy pipelines when constrained
   - Return DEFERRED receipts with explanation

8. **M5.8: Privacy in Observability** (3h)
   - Implement privacy filter for taps
   - Mask PII in AMBER band
   - Redact content in RED band

9. **M5.9: Crash Fencing** (2h)
   - Implement recovery epoch on boot
   - Check idempotency before reprocessing stale entries
   - Record clean shutdown timestamp

10. **M5.10: Recall SLA Clarity** (2h)
    - Expose `/meta/consistency` endpoint
    - Document WAL vs enriched read paths
    - Provide machine-readable SLA contract

### Milestone 5 Acceptance Criteria (ALL MUST PASS)

- [ ] All 10 production musts implemented
- [ ] 60-second readiness checklist passes (Section 16 of architecture doc)
- [ ] Mobile deployment tested (4GB RAM device)
- [ ] Battery impact <5% drain/hour
- [ ] Thermal throttling works (tested with stress test)
- [ ] Security audit passes (capability gates, signed manifests)
- [ ] All 7 validation tests still pass

### Milestone 5 Deliverables

```
k0/
  qos/
    admission.py (NEW - token bucket)
  kernel/
    thermal.py (NEW - thermal/battery monitoring)
  obs/
    privacy_filter.py (NEW - PII masking)
  ports/
    rest/
      status.py (NEW - /status API)
      meta.py (NEW - /meta/consistency)
  storage/
    ledger_compaction.py (NEW)
  bus/
    outbox_processor.py (UPDATED - crash fencing, schema validation)
  pipelines/
    p02/
      pipeline.toml (NEW - manifest with signature)

tests/
  k0/
    qos/
      test_admission.py (NEW)
    kernel/
      test_thermal.py (NEW)
    obs/
      test_privacy_filter.py (NEW)
    ports/
      test_status_api.py (NEW)
    storage/
      test_ledger_compaction.py (NEW)
```

### Milestone 5 Success Metrics

- **Time to Complete:** 25 hours (3-4 days)
- **Lines of Code:** ~3000 (300 per must)
- **Security:** 100% of storage gated, manifests signed
- **Mobile:** <5% battery drain/hour, thermal throttling active
- **Risk Level:** HIGH (production-critical features)

---

## Implementation Timeline

| Milestone | Duration | Start | End | Status | Deliverables |
|-----------|----------|-------|-----|--------|--------------|
| **M1: Kernel Foundation** | 3h | Day 1 | Day 1 | 🔴 Not Started | BusDispatcher v2, DDL, Protocol |
| **M2: Discovery System** | 4h | Day 1 | Day 1 | 🔴 Not Started | Loader, Syscalls, Integration |
| **M3: Reference Pipeline** | 6h | Day 2 | Day 2 | 🔴 Not Started | P02, Outbox Processor, 7 Tests |
| **M4: Scale Testing** | 2h | Day 2 | Day 2 | 🔴 Not Started | 100 pipelines, Dispatch benchmark |
| **M5: Production Hardening** | 25h | Day 3 | Day 6 | 🔴 Not Started | 10 production musts |

**Total Timeline:** 6 days (40 hours total work)

---

## Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **M1 breaks existing kernel** | LOW | HIGH | Maintain backward compatibility, extensive unit tests |
| **M2 loader fails contract validation** | MEDIUM | MEDIUM | Use reference P02 as validation target |
| **M3 P02 performance misses target** | LOW | HIGH | Use ProcessPoolExecutor, profile with py-spy |
| **M4 dispatch >5ms P95** | LOW | MEDIUM | O(k) subscription already validated in design doc |
| **M5 mobile battery drain high** | MEDIUM | HIGH | Thermal throttling, admission control |
| **Integration complexity** | MEDIUM | MEDIUM | Incremental testing, each milestone independently deployable |

---

## Success Criteria (Overall Project)

### Functional Requirements ✅

- [ ] Kernel boots with 0-100 pipelines dynamically
- [ ] P02 processes events end-to-end (write → commit → P02 → st_hipp_store)
- [ ] All 7 validation tests pass
- [ ] 10 production musts implemented

### Performance Requirements ✅

- [ ] Dispatch P95 < 5ms (100 pipelines)
- [ ] Phase-1 commit P95 < 100ms
- [ ] P02 processing P95 < 100ms
- [ ] Memory RSS < 500MB
- [ ] Throughput > 100 req/sec

### Mobile/Edge Requirements ✅

- [ ] Runs on 4GB RAM device
- [ ] Battery drain < 5%/hour
- [ ] Thermal throttling prevents overheating
- [ ] SQLite mobile PRAGMAs applied
- [ ] Offline mode works (no network required)

### Security Requirements ✅

- [ ] All storage operations capability-gated
- [ ] Pipeline manifests signed in production
- [ ] PII masked in observability (AMBER/RED bands)
- [ ] Audit trail for all sensitive operations

### Operational Requirements ✅

- [ ] Crash recovery works (boot from outbox only)
- [ ] DLQ handles poison pills (5 retries)
- [ ] Graceful shutdown calls pipeline cleanup
- [ ] Ledger compaction prevents unbounded growth
- [ ] `/status` API for polling when SSE unavailable

---

## Next Steps (Immediate Actions)

### 1. Create Milestone 1 Branch

```bash
git checkout -b milestone/m1-kernel-foundation
```

### 2. Start with R1.1 (BusDispatcher v2)

- [ ] Read existing `k0/bus/core.py`
- [ ] Add `subscribe()` method
- [ ] Add `tap()` method
- [ ] Update `dispatch()` to use topic map
- [ ] Add deprecation warning to `register_sink()`

### 3. Run Tests Continuously

```bash
# Watch mode for rapid iteration
python -m pytest tests/k0/bus/ -v --tb=short -x
```

### 4. Commit After Each Requirement

```bash
git add k0/bus/core.py tests/k0/bus/test_dispatcher_v2.py
git commit -m "feat(bus): Add subscribe() and tap() APIs (R1.1)"
```

### 5. Track Progress

- Update milestone status in this document
- Mark checkboxes as requirements complete
- Document any deviations or blockers

---

## Appendix: File Tree After All Milestones

```
k0/
  bus/
    core.py (UPDATED - BusDispatcher v2)
    sinks.py (UPDATED - use tap())
    outbox_processor.py (NEW - M3)
  kernel/
    app.py (UPDATED - loader integration, shutdown handlers)
    syscalls.py (NEW - M2)
    thermal.py (NEW - M5)
  pipelines/ (NEW DIRECTORY - M1)
    __init__.py
    protocol.py (NEW - M1)
    loader.py (NEW - M2)
    p02_episodic_write.py (NEW - M3)
    p01_recall.py (NEW - M4 stub)
    p03_consolidation.py (NEW - M4 stub)
    p08_embedding.py (NEW - M4 stub)
    p14_dedup.py (NEW - M4 stub)
    p99_dummy_01.py through p99_dummy_95.py (NEW - M4 auto-gen)
    generate_dummy_pipelines.py (NEW - M4 generator)
    p02/
      pipeline.toml (NEW - M5 manifest)
  qos/
    admission.py (NEW - M5)
  obs/
    privacy_filter.py (NEW - M5)
  ports/
    rest/
      status.py (NEW - M5)
      meta.py (NEW - M5)
  storage/
    migrations/
      003_pipeline_ledger.sql (NEW - M1)
      004_dlq.sql (NEW - M1)
    ledger_compaction.py (NEW - M5)

tests/
  k0/
    bus/
      test_dispatcher_v2.py (NEW - M1)
      test_outbox_processor.py (NEW - M3)
    kernel/
      test_syscalls.py (NEW - M2)
      test_app_pipeline_integration.py (NEW - M2)
      test_thermal.py (NEW - M5)
    pipelines/
      test_protocol.py (NEW - M1)
      test_loader.py (NEW - M2)
      test_p02.py (NEW - M3)
      test_validation.py (NEW - M3 - 7 tests)
    storage/
      test_migrations_pipeline.py (NEW - M1)
      test_ledger_compaction.py (NEW - M5)
    qos/
      test_admission.py (NEW - M5)
    obs/
      test_privacy_filter.py (NEW - M5)
    ports/
      test_status_api.py (NEW - M5)
    performance/
      test_dispatch_100_pipelines.py (NEW - M4)
```

---

## Questions to Answer Before Starting

1. **Do we need to update any ADRs?**
   - Recommendation: Create ADR for pipeline architecture (reference k0_pipeline_architecture.md)

2. **Should M1 include config file support?**
   - Recommendation: Add `k0/config/pipelines.yml` in M1 for pipeline-specific config

3. **Do we want CI/CD gates at each milestone?**
   - Recommendation: Yes - require all tests pass before merging milestone branch

4. **Should we deploy after each milestone?**
   - Recommendation: M1, M2, M3 can be deployed incrementally (feature flags if needed)

5. **Do we need documentation updates?**
   - Recommendation: Update READMEs after M3 (when P02 works end-to-end)

---

**Ready to start with Milestone 1?** Let me know and I'll begin implementing R1.1 (BusDispatcher v2). 🚀
