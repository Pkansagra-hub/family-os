# K0 Unit of Work (UoW) Module

**Purpose:** ACID transaction coordination across WAL, receipts, offsets, and outbox with SQLite connection pooling.

---

## Part 1: Repository Files & Functions

### Core Files

#### `__init__.py`
**Purpose:** Module exports

**Exports:**
- `UnitOfWork`: Main transaction coordinator class

---

#### `connection_pool.py`
**Purpose:** Thread-safe SQLite connection pooling with metrics

**Key Classes:**

**`PoolStats`** (dataclass)
- `created: int` - Total connections created
- `available: int` - Idle connections in pool
- `in_use: int` - Active connections

**`SQLiteConnectionPool`**
- **Purpose:** Lightweight thread-safe pool for SQLite connections
- **Configuration:**
  - `database_path: Path` - SQLite database file
  - `max_size: int = 8` - Maximum pool size
  - `pragmas: Mapping[str, str | int] | None` - SQLite PRAGMA settings
  - `busy_timeout_ms: int = 5000` - Lock retry timeout
  - `metrics_exporter: MetricsExporter | None` - Metrics integration

**Key Methods:**

**Connection Management:**
- `acquire(*, timeout: float | None = None) -> sqlite3.Connection`
  - Acquires connection from pool
  - Creates new connection if pool not saturated
  - Blocks with timeout if pool exhausted
  - **Metrics:** Tracks `sqlite_pool_acquire_latency_seconds`
  - **Error Handling:** Raises `TimeoutError` after timeout expiration
  - **KeyboardInterrupt:** Re-raises immediately without leaking `_in_use` counter

- `release(connection: sqlite3.Connection) -> None`
  - Returns connection to pool
  - Rolls back any pending transaction
  - Notifies waiting threads
  - Updates pool saturation metrics

- `close() -> None`
  - Closes all idle connections
  - Prevents further acquisition
  - Thread-safe shutdown

**Introspection:**
- `stats() -> PoolStats`
  - Returns current pool statistics
  - Used for diagnostics and testing

**Metrics (Gap 45):**
- `sqlite_pool_connections_active` (gauge): Active connection count
- `sqlite_pool_saturation_ratio` (gauge): `in_use / max_size` (0.0-1.0)
- `sqlite_pool_acquire_latency_seconds` (histogram): Acquisition latency
- `sqlite_pool_acquire_timeouts_total` (counter): Timeout count

**PRAGMA Defaults:**
- `journal_mode=WAL` - Write-Ahead Logging for concurrency
- `synchronous=NORMAL` - Balance durability/performance
- `temp_store=MEMORY` - Faster temp tables
- `foreign_keys=1` - Enforce referential integrity

---

**Global Pool Management:**

**`configure_pool(...) -> None`**
- Initializes global singleton pool
- Parameters: `database_path`, `max_size`, `pragmas`, `busy_timeout_ms`, `metrics_exporter`
- Thread-safe initialization

**`shutdown_pool() -> None`**
- Closes and discards global pool
- Safe to call multiple times

**`get_pool() -> SQLiteConnectionPool`**
- Returns configured pool
- Raises `RuntimeError` if pool not configured

**`connection_scope(*, timeout: float | None = None) -> Iterator[sqlite3.Connection]`**
- Context manager yielding pooled connection
- Automatic release on exit
- Exception-safe cleanup

**Usage Example:**
```python
from k0.uow.connection_pool import configure_pool, connection_scope

# Initialize pool
configure_pool(
    Path("k0_runtime.sqlite3"),
    max_size=8,
    metrics_exporter=metrics
)

# Use connection
with connection_scope() as conn:
    conn.execute("SELECT * FROM st_wal LIMIT 10")
```

---

#### `unit_of_work.py`
**Purpose:** ACID transaction coordinator (Unit of Work pattern)

**Key Classes:**

**`UnitOfWork`** (dataclass, context manager)
- **Purpose:** Coordinates transactions across WAL, receipts, offsets, outbox
- **Pattern:** Transaction Script pattern with context manager interface

**Configuration:**
- `outbox_store: OutboxStore | None` - Outbox for async work
- `write_ahead_log: WriteAheadLog | None` - WAL for event sourcing
- `receipt_store: ReceiptStore | None` - Receipt persistence
- `offset_store: OffsetStore | None` - Offset tracking
- `metrics_emitter: MetricsEmitter | None` - Counter metrics
- `metrics_exporter: MetricsExporter | None` - Histogram metrics
- `snapshot_watermark_gauge: Callable[[float], None] | None` - WAL watermark gauge
- `on_commit: list[Callable[[], None]]` - Post-commit hooks
- `on_rollback: list[Callable[[], None]]` - Post-rollback hooks
- `wal_fsync_mode: Literal["strict", "wal_only", "disabled"]` - Durability mode

**Lifecycle Methods:**

**`__enter__() -> UnitOfWork`**
- Acquires connection from pool
- Sets SQLite PRAGMAs:
  - `PRAGMA journal_mode=WAL` - Write-Ahead Logging
  - `PRAGMA synchronous=FULL` - Full durability (Issue 1.7)
  - `PRAGMA foreign_keys=ON` - Referential integrity
  - `PRAGMA temp_store=MEMORY` - Fast temp tables
  - `PRAGMA busy_timeout=5000` - 5s lock retry
- Begins `BEGIN IMMEDIATE` transaction (lock immediately)
- Registers UoW in context var (`_ACTIVE_UOW`)
- Records start time for metrics

**`__exit__(exc_type, exc, tb) -> bool`**
- Commits if no exception
- Rolls back on exception
- Runs lifecycle hooks
- Releases connection to pool
- Resets context var
- Returns `False` (does not suppress exceptions)

**Transaction Methods:**

**`stage_outbox(entry: OutboxEntry) -> None`**
- Stages outbox entry for commit
- Entry written on `_commit()`
- Used for async work (embedding, FTS)

**`append_wal(entry: WalEntry) -> int`**
- Appends entry to WAL
- Returns WAL position
- Tracks positions for fsync

**`save_receipt(receipt: Receipt) -> None`**
- Saves receipt to receipt store
- V1 receipts with envelope_sha256, Ed25519 signature

**`upsert_offset(record: Offset) -> None`**
- Upserts offset record
- Used for driver position tracking

**Hooks:**

**`add_commit_hook(hook: Callable[[], None]) -> None`**
- Registers post-commit callback
- Runs after successful commit

**`add_rollback_hook(hook: Callable[[], None]) -> None`**
- Registers post-rollback callback
- Runs after rollback

**Context Management:**

**`@classmethod current() -> UnitOfWork | None`**
- Returns active UoW from context var
- Used by nested operations

**`@property connection -> sqlite3.Connection`**
- Returns active SQLite connection
- Raises `RuntimeError` if UoW not active

**Internal Methods:**

**`_commit() -> None`**
- Flushes staged outbox entries
- Commits SQLite transaction
- Runs fsync on WAL (if configured)
- Updates snapshot watermark gauge
- Runs commit hooks
- **Metrics:**
  - `uow_commit_seconds` (histogram, outcome label)
  - `uow_commit_total` (counter, outcome label)
  - `uow_wal_fsync_seconds` (histogram, outcome label)
  - `uow_wal_fsync_total` (counter, outcome label)

**`_rollback(*, reason: str) -> None`**
- Rolls back SQLite transaction
- Clears staged outbox
- Clears WAL positions
- Runs rollback hooks
- **Metrics:**
  - `uow_rollback_total` (counter, outcome + reason labels)

**`_flush_outbox() -> None`**
- Writes staged outbox entries to database
- Called during `_commit()`

**`_fsync_wal() -> float | None`**
- Syncs WAL to disk
- Modes:
  - `strict`: Full fsync (journal + WAL)
  - `wal_only`: WAL fsync only
  - `disabled`: No fsync (testing only)
- Returns fsync duration

**`_cleanup(...) -> None`**
- Releases connection to pool (does NOT close connection)
- Exits connection scope
- Resets context var
- **Critical Fix (Gap 28):** Single `_token` reset (was 3x before)

**Usage Example:**
```python
from k0.uow import UnitOfWork
from k0.storage.wal import WalEntry, WriteAheadLog
from k0.storage.outbox import OutboxStore, OutboxEntry

# Create UoW
uow = UnitOfWork(
    write_ahead_log=WriteAheadLog(Path("wal.db")),
    outbox_store=OutboxStore(),
    metrics_emitter=emit_counter,
    metrics_exporter=metrics
)

# Use transaction
with uow:
    # Append to WAL
    pos = uow.append_wal(WalEntry(...))

    # Stage async work
    uow.stage_outbox(OutboxEntry(driver="embedding", ...))

    # Save receipt
    uow.save_receipt(Receipt(...))

    # Auto-commit on exit
```

**Durability Guarantees (Issue 1.7):**
- `PRAGMA synchronous=FULL` - fsync after each commit
- `PRAGMA journal_mode=WAL` - Concurrent reads during writes
- WAL fsync modes:
  - `strict`: Full durability (production)
  - `wal_only`: WAL durability only
  - `disabled`: No fsync (testing/benchmarking)

---

### Architecture Patterns

#### 1. Unit of Work Pattern
**Intent:** Maintain transactional consistency across multiple storage adapters

**Implementation:**
- Single SQLite connection per UoW
- All writes happen in transaction
- Commit/rollback coordinates across stores

**Benefits:**
- ACID guarantees across WAL, receipts, offsets, outbox
- Clean separation of transaction logic
- Easy testing with in-memory databases

---

#### 2. Connection Pooling
**Intent:** Reduce connection overhead, limit concurrency

**Implementation:**
- Thread-safe pool with condition variable
- Bounded pool size (default: 8)
- Automatic connection creation up to limit
- Graceful degradation on exhaustion

**Benefits:**
- Amortized connection setup cost
- SQLite concurrency control (NORMAL journal mode supports concurrent reads)
- Backpressure via pool saturation

---

#### 3. Context Variable for Active UoW
**Intent:** Support nested transaction scopes

**Implementation:**
- `ContextVar` stores active UoW
- `UnitOfWork.current()` retrieves active UoW
- Safe for async contexts

**Benefits:**
- Implicit transaction context
- Avoids explicit UoW passing
- Compatible with async/await

---

## Part 2: Cross-Module Connections & Integration Points

### Upstream Dependencies

#### 1. Storage Adapters (`k0/storage/`)
**Connection:** UoW coordinates transactions across storage modules

**Integration:**
- `WriteAheadLog` (`k0/storage/wal.py`) - Event sourcing
- `OutboxStore` (`k0/storage/outbox.py`) - Async work queue
- `ReceiptStore` (`k0/storage/receipts.py`) - Receipt persistence
- `OffsetStore` (`k0/storage/offsets.py`) - Driver position tracking

**Data Flow:**
```
UoW __enter__
  ↓
BEGIN IMMEDIATE transaction
  ↓
[Operations: append_wal, save_receipt, stage_outbox, upsert_offset]
  ↓
UoW __exit__
  ↓
_commit() → flush_outbox() → SQLite COMMIT → WAL fsync
```

---

#### 2. Metrics Exporter (`k0/obs/metrics.py`)
**Connection:** Connection pool and UoW emit performance metrics

**Metrics Emitted:**
- **Connection Pool:**
  - `sqlite_pool_connections_active` (gauge)
  - `sqlite_pool_saturation_ratio` (gauge)
  - `sqlite_pool_acquire_latency_seconds` (histogram)
  - `sqlite_pool_acquire_timeouts_total` (counter)

- **UoW:**
  - `uow_commit_seconds` (histogram)
  - `uow_commit_total` (counter, outcome label)
  - `uow_rollback_total` (counter, outcome + reason labels)
  - `uow_wal_fsync_seconds` (histogram)
  - `uow_wal_fsync_total` (counter, outcome label)

**SLO Integration:**
- `uow_commit_seconds` P95 < 50ms (target)
- Alert thresholds: warning @ 100ms, critical @ 200ms

---

### Downstream Consumers

#### 1. Kernel Ports (`k0/ports/`)
**Connection:** All ports use UoW for transaction coordination

**Ports Using UoW:**
- `command_port.py` - Command submissions
- `query_port.py` - Query executions (read-only UoW)
- `sse_port.py` - SSE subscription management
- `receipt_port.py` - Receipt queries

**Pattern:**
```python
with UnitOfWork(...) as uow:
    # Port logic
    uow.append_wal(...)
    uow.stage_outbox(...)
```

---

#### 2. Bus Workers (`k0/bus/core.py`)
**Connection:** Bus workers use UoW for event processing

**Usage:**
- Workers process outbox entries in UoW
- Mark entries applied within transaction
- Append WAL entries for event replay

---

#### 3. CLI (`k0/cli/`)
**Connection:** k0ctl commands use UoW for database operations

**Commands:**
- `provision` - Creates entities with UoW
- `schema-registry` - Validates contracts with UoW
- `dlq` - Moves quarantined entries with UoW

---

#### 4. Background Workers (`k0/workers/`)
**Connection:** Embedding and FTS workers use UoW

**Pattern:**
```python
with connection_scope() as conn:
    # Process outbox entry
    result = worker.process(entry)

    # Update WAL
    conn.execute("UPDATE st_wal SET ... WHERE wal_pos=?")

    # Mark outbox applied
    outbox.mark_applied(entry.id, connection=conn)

    conn.commit()
```

**Note:** Workers use `connection_scope()` directly for fine-grained control

---

### Testing Strategy

#### 1. Connection Pool Tests (`tests/uow/test_connection_pool.py`)
**Coverage:**
- Pool initialization and configuration
- Connection acquisition and release
- Timeout behavior
- Saturation handling
- Metrics emission
- Thread safety
- KeyboardInterrupt handling (Gap 40)

**Key Test Cases:**
- `test_pool_acquire_release` - Basic lifecycle
- `test_pool_exhaustion_timeout` - Timeout on saturation
- `test_pool_stats` - Introspection accuracy
- `test_pool_metrics` - Metrics validation
- `test_pool_thread_safety` - Concurrent access

---

#### 2. UoW Tests (`tests/uow/test_unit_of_work.py`)
**Coverage:**
- Transaction commit/rollback
- WAL append coordination
- Outbox staging and flush
- Receipt persistence
- Offset tracking
- Hook execution
- Context var management
- Metrics emission
- Fsync modes

**Key Test Cases:**
- `test_uow_commit_success` - Happy path
- `test_uow_rollback_on_exception` - Error handling
- `test_uow_outbox_staging` - Outbox coordination
- `test_uow_wal_append` - WAL integration
- `test_uow_fsync_modes` - Durability modes
- `test_uow_context_var` - Nested UoW support

---

#### 3. Integration Tests (`tests/integration/test_e2e_flows.py`)
**Coverage:**
- Full command flow with UoW
- Query flow with UoW
- Receipt generation with UoW
- Outbox processing with UoW

---

### Performance Considerations

#### 1. Connection Pool Sizing
**Guideline:** Size pool based on concurrency needs

**Recommendations:**
- Development: 4-8 connections
- Production: 8-16 connections
- High load: 16-32 connections (monitor saturation)

**Tuning:**
- Monitor `sqlite_pool_saturation_ratio` gauge
- Target < 0.8 (80%) under normal load
- Alert @ 0.9 (90%) sustained saturation

---

#### 2. Transaction Duration
**Target:** Keep UoW duration < 50ms P95

**Best Practices:**
- Minimize work inside UoW context
- Stage outbox entries instead of processing inline
- Use read-only transactions for queries
- Avoid network I/O inside UoW

---

#### 3. Fsync Modes
**Production:** `strict` (full durability)
**Development:** `wal_only` (faster, still durable)
**Testing:** `disabled` (fastest, no durability)

**Trade-offs:**
- `strict`: Slowest, safest (production default)
- `wal_only`: Faster, durable WAL only
- `disabled`: Fastest, no crash recovery (testing only)

---

### Operational Notes

#### 1. Database Initialization
**Workflow:**
1. Create database file: `touch k0_runtime.sqlite3`
2. Apply schema: `sqlite3 k0_runtime.sqlite3 < k0/contracts/sql/storage.sql`
3. Configure pool: `configure_pool(Path("k0_runtime.sqlite3"), max_size=8)`

---

#### 2. Pool Saturation Troubleshooting
**Symptoms:**
- High `sqlite_pool_acquire_latency_seconds`
- Frequent `sqlite_pool_acquire_timeouts_total` increments
- `sqlite_pool_saturation_ratio` > 0.9

**Solutions:**
1. Increase `max_size` (monitor memory usage)
2. Reduce transaction duration (profile with `py-spy`)
3. Add connection pooling metrics to dashboards

---

#### 3. Lock Contention
**Symptoms:**
- SQLite `database is locked` errors
- High `busy_timeout` retries

**Solutions:**
1. Increase `busy_timeout_ms` (default: 5000ms)
2. Switch to WAL mode (`PRAGMA journal_mode=WAL`)
3. Reduce transaction scope (minimize write operations)

---

#### 4. Context Var Leaks (Gap 28 Fix)
**Symptom:** `_ACTIVE_UOW` context var not reset after exception

**Root Cause:** Triple assignment in `_cleanup()` (fixed)

**Fix:** Single `_token` reset:
```python
if self._token is not None:
    try:
        _ACTIVE_UOW.reset(self._token)
    except Exception:
        pass  # Best-effort
    finally:
        self._token = None  # ✅ Single assignment
```

---

### Error Handling

#### 1. TimeoutError
**Cause:** Pool exhausted, timeout expired

**Recovery:**
- Retry with exponential backoff
- Increase pool size
- Reduce transaction duration

---

#### 2. RuntimeError (Pool Not Configured)
**Cause:** Calling `get_pool()` before `configure_pool()`

**Recovery:**
- Call `configure_pool()` during application startup
- Check pool initialization in tests

---

#### 3. SQLite Errors
**Cause:** Schema errors, constraint violations, disk I/O errors

**Recovery:**
- Log error with context (SQL, params)
- Rollback transaction
- Report via metrics (`uow_commit_total{outcome="failure"}`)

---

### References

- **Unit of Work Pattern:** Martin Fowler, *Patterns of Enterprise Application Architecture*
- **Connection Pooling:** PostgreSQL connection pooling best practices (adapted for SQLite)
- **Context Variables:** PEP 567 (Python 3.7+)
- **SQLite WAL Mode:** https://www.sqlite.org/wal.html
- **Durability Standards:** `.github/copilot-instructions.md` (Section 3: Development Standards)
- **Storage Contracts:** `k0/contracts/sql/storage.sql`
- **Metrics Integration:** `k0/obs/README.md`
