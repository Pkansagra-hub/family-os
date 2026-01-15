# R7 Truth Writer — Complete Deep Dive

> **Pipeline:** P03 Consolidation
> **Phase:** R7 (Truth Writer)
> **Location:** `k0/pipelines/p03/phases/r7_truth_writer.py`
> **Last Updated:** 2026-01-09

---

## Table of Contents

1. [Overview](#1-overview)
2. [R7 in the Pipeline Context](#2-r7-in-the-pipeline-context)
3. [Core Files & Dependencies](#3-core-files--dependencies)
4. [Step-by-Step Execution Flow](#4-step-by-step-execution-flow)
5. [Data Structures](#5-data-structures)
6. [Database Tables Accessed](#6-database-tables-accessed)
7. [UnitOfWork Pattern](#7-unitofwork-pattern)
8. [DecisionRouter & Layer Writers](#8-decisionrouter--layer-writers)
9. [Optimistic Locking & Version Conflicts](#9-optimistic-locking--version-conflicts)
10. [Outbox Staging](#10-outbox-staging)
11. [Status Writeback](#11-status-writeback)
12. [Configuration](#12-configuration)
13. [Error Handling](#13-error-handling)
14. [ASCII Architecture Diagram](#14-ascii-architecture-diagram)
15. [Summary](#15-summary)

---

## 1. Overview

**R7 (Truth Writer)** is the **atomic database commit phase** of the P03 Consolidation Pipeline. It receives staged writes from R6 and persists them to truth tables within a single PostgreSQL transaction.

### Key Responsibilities

1. **Execute staged writes** from R6 within a UnitOfWork transaction
2. **Maintain dependency order** between layers (vec → kg_dom → kg_edges → epi → sem → ...)
3. **Handle optimistic locking** with version-based conflict detection
4. **Retry on version conflicts** (up to 3 attempts with exponential backoff)
5. **Stage outbox events** for R8 emission
6. **Update event status** to mark consolidation complete

### Design Principles

| Principle | Implementation |
|-----------|----------------|
| **ACID Compliance** | All writes in single PostgreSQL transaction |
| **Idempotency** | INSERT uses `ON CONFLICT DO NOTHING` |
| **Optimistic Locking** | UPDATE checks `version` column |
| **Dependency Order** | Foreign keys satisfied before dependents |
| **Durability** | Outbox pattern for event emission |

### TIMESTAMP CONVENTION (LOCKED)

All `*_ts` and `*_ms` fields use **MILLISECONDS** since Unix epoch.

---

## 2. R7 in the Pipeline Context

```
┌─────────────────────────────────────────────────────────────────┐
│                    P03 CONSOLIDATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐          │
│  │  R0  │──▶│  R1  │──▶│  R2  │──▶│  R3  │──▶│  R4  │          │
│  │BATCH │   │SCORE │   │CLUST │   │DEDUP │   │  KG  │          │
│  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘          │
│                                                 │                │
│                                                 ▼                │
│                                    ┌──────┐   ┌──────┐          │
│                                    │  R5  │──▶│  R6  │          │
│                                    │DREAM │   │STAGE │          │
│                                    └──────┘   └──────┘          │
│                                                 │                │
│                                                 ▼                │
│                                           ╔══════════╗          │
│                                           ║    R7    ║          │
│                                           ║  WRITE   ║◀── YOU   │
│                                           ╚══════════╝    HERE  │
│                                                 │                │
│                                                 ▼                │
│                                            ┌──────┐             │
│                                            │  R8  │             │
│                                            │ EMIT │             │
│                                            └──────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### Phase Execution Order

```python
# From runner_contract.py
P03PhaseId.execution_order() = (
    R0_INIT,    # Batch Selection
    R1_SCORE,   # Importance Scoring
    R2_CLUSTER, # Episodic Clustering
    R3_PRUNE,   # Dedup & Decay
    R4_KG,      # Knowledge Graph
    R5_DREAM,   # Dream Exploration (optional)
    R6_STAGE,   # Staging Table Updates
    R7_WRITE,   # Truth Writer (THIS PHASE)
    R8_EMIT,    # Event Emission
)
```

### R7 Input/Output

| Direction | Data |
|-----------|------|
| **Input** | `P03BatchEnvelope` with `staged_writes: List[StagedWrite]` from R6 |
| **Output** | `P03PhaseResult` with write statistics, modified envelope |
| **Side Effects** | Truth table rows created/updated, outbox events staged |

---

## 3. Core Files & Dependencies

### Primary File

```
k0/pipelines/p03/phases/r7_truth_writer.py (814 lines)
```

### Module Structure

```
k0/
├── pipelines/p03/phases/
│   └── r7_truth_writer.py              # Phase entry point
│
├── modules/consolidation/truth_writer/
│   ├── __init__.py
│   ├── router.py                       # DecisionRouter (M5)
│   ├── transaction.py                  # TransactionCoordinator
│   ├── result.py                       # WriteResult, LayerWriteResult
│   ├── outbox.py                       # OutboxWriter
│   └── layers/
│       ├── episodic.py                 # EpisodicLayerWriter (st_epi)
│       ├── semantic.py                 # SemanticLayerWriter (st_sem)
│       ├── procedural.py               # ProceduralLayerWriter (st_procedural)
│       ├── social.py                   # SocialLayerWriter (st_social)
│       ├── prospective.py              # ProspectiveLayerWriter (st_prospective)
│       ├── kg.py                       # KGLayerWriter (st_kg_dom, st_kg_edges)
│       └── vector.py                   # VectorLayerWriter (st_vec)
│
└── uow/
    └── unit_of_work.py                 # UnitOfWork transaction manager
```

### Direct Imports in r7_truth_writer.py

| File | Classes/Functions Imported |
|------|---------------------------|
| `k0/pipelines/p03/envelope.py` | `P03BatchEnvelope` |
| `k0/pipelines/p03/phase_interface.py` | `P03PhaseResult` |
| `k0/pipelines/p03/runner_contract.py` | `P03PhaseId` |
| `k0/pipelines/p03/staged_writes.py` | `StagedWrite`, `WriteOperation`, layer constants |
| `k0/uow/unit_of_work.py` | `UnitOfWork` |

### Feature Flags

```python
# r7_truth_writer.py
USE_M5_ROUTER = False  # Toggle for M5 DecisionRouter vs Legacy inline SQL
```

When `USE_M5_ROUTER = True`, R7 uses the modular `DecisionRouter` architecture.
When `False` (default), R7 uses the legacy inline SQL implementation for rollback safety.

---

## 4. Step-by-Step Execution Flow

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         R7 EXECUTION                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. VALIDATE INPUT                                              │
│     ├── Check envelope has staged_writes                        │
│     ├── Check envelope.cycle_id is set                          │
│     └── Skip if staged_writes is empty                          │
│                          │                                       │
│                          ▼                                       │
│  2. ACQUIRE UNIT OF WORK                                        │
│     ├── async with UnitOfWork(conn_pool) as uow:                │
│     ├── Begin PostgreSQL transaction                            │
│     └── Register commit/rollback hooks                          │
│                          │                                       │
│                          ▼                                       │
│  3. EXECUTE STAGED WRITES (Dependency Order)                    │
│     ├── st_vec (embeddings)                                     │
│     ├── st_kg_dom (entities)                                    │
│     ├── st_kg_edges (edges)                                     │
│     ├── st_epi (episodes)                                       │
│     ├── st_sem (patterns)                                       │
│     ├── st_procedural (routines)                                │
│     ├── st_social (relationships)                               │
│     ├── st_prospective (intentions)                             │
│     ├── st_learning_queue (learning)                            │
│     └── st_hipp_events (status update)                          │
│                          │                                       │
│                          ▼                                       │
│  4. STAGE OUTBOX EVENTS                                         │
│     ├── p03.truth.created.v1                                    │
│     ├── p03.truth.reinforced.v1                                 │
│     ├── p03.truth.evolved.v1                                    │
│     └── p03.embedding.created/updated.v1 (for P08)              │
│                          │                                       │
│                          ▼                                       │
│  5. UPDATE EVENT STATUS                                         │
│     ├── Set consolidation_status = 'COMPLETE'                   │
│     ├── Set consolidation_cycle_id                              │
│     └── Set consolidated_at timestamp                           │
│                          │                                       │
│                          ▼                                       │
│  6. COMMIT TRANSACTION                                          │
│     ├── UoW commits all changes atomically                      │
│     ├── Outbox entries persisted                                │
│     └── Return P03PhaseResult with statistics                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Dependency Order (Critical)

Writes must execute in dependency order to satisfy foreign key constraints:

```python
WRITE_ORDER = [
    "st_vec",           # 1. Embeddings (no dependencies)
    "st_kg_dom",        # 2. KG entities (no dependencies)
    "st_kg_edges",      # 3. KG edges (depends on st_kg_dom)
    "st_epi",           # 4. Episodes (may ref embeddings)
    "st_sem",           # 5. Patterns (may ref episodes)
    "st_procedural",    # 6. Routines
    "st_social",        # 7. Relationships
    "st_prospective",   # 8. Intentions
    "st_learning_queue",# 9. Learning queue
    "st_hipp_events",   # 10. Status update (last)
]
```

### Primary Key Mapping

```python
LAYER_PK_MAP = {
    "st_epi": "episode_id",
    "st_sem": "pattern_id",
    "st_procedural": "routine_id",
    "st_social": "relationship_id",
    "st_prospective": "intention_id",
    "st_kg_dom": "entity_id",
    "st_kg_edges": "edge_id",
    "st_vec": "embedding_id",
    "st_hipp_events": "event_id",
    "st_learning_queue": "queue_id",
}
```

---

## 5. Data Structures

### StagedWrite (from R6)

```python
@dataclass
class StagedWrite:
    """
    A single write operation staged for R7.

    Attributes:
        layer: Target table (st_epi, st_sem, etc.)
        operation: WriteOperation (INSERT, UPDATE, ARCHIVE, TOMBSTONE)
        record_id: Primary key value
        record_data: Dict with column values
        expected_version: For optimistic locking (UPDATE only)
        idempotency_key: For duplicate prevention
    """
    layer: str
    operation: WriteOperation
    record_id: str
    record_data: Dict[str, Any]
    expected_version: Optional[int] = None
    idempotency_key: Optional[str] = None
```

### WriteOperation Enum

```python
class WriteOperation(str, Enum):
    INSERT = "INSERT"      # Create new record
    UPDATE = "UPDATE"      # Modify existing record
    ARCHIVE = "ARCHIVE"    # Soft-delete (archival_status = 'ARCHIVED')
    TOMBSTONE = "TOMBSTONE"  # GDPR deletion marker
```

### WriteResult (Aggregate)

```python
@dataclass
class WriteResult:
    """
    Aggregate result of all writes in a cycle.

    Attributes:
        total_attempted: Total writes attempted
        total_succeeded: Writes that succeeded
        total_failed: Writes that failed
        by_layer: Per-layer results
        failed_decision_ids: IDs of failed records
        total_duration_ms: Total write time
    """
    total_attempted: int
    total_succeeded: int
    total_failed: int
    by_layer: Dict[str, LayerWriteResult] = field(default_factory=dict)
    failed_decision_ids: List[str] = field(default_factory=list)
    total_duration_ms: Optional[int] = None

    @property
    def is_success(self) -> bool:
        return self.total_failed == 0

    @property
    def success_rate(self) -> float:
        if self.total_attempted == 0:
            return 1.0
        return self.total_succeeded / self.total_attempted
```

### LayerWriteResult (Per-Layer)

```python
@dataclass
class LayerWriteResult:
    """
    Result of writes to a single layer.

    Attributes:
        layer: Layer name
        writes_attempted: Writes attempted for this layer
        writes_succeeded: Successful writes
        writes_failed: Failed writes
        failed_ids: IDs of failed records
        error_message: Concatenated error messages
    """
    layer: str
    writes_attempted: int = 0
    writes_succeeded: int = 0
    writes_failed: int = 0
    failed_ids: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.writes_failed == 0
```

---

## 6. Database Tables Accessed

### Truth Tables (Write Targets)

| Table | Primary Key | Description |
|-------|-------------|-------------|
| `st_epi` | `episode_id` | Episodic memories (clustered events) |
| `st_sem` | `pattern_id` | Semantic patterns (recurring themes) |
| `st_procedural` | `routine_id` | Procedural routines (habits) |
| `st_social` | `relationship_id` | Social relationships |
| `st_prospective` | `intention_id` | Future intentions/goals |
| `st_kg_dom` | `entity_id` | Knowledge graph entities |
| `st_kg_edges` | `edge_id` | Knowledge graph edges |
| `st_vec` | `embedding_id` | Embedding vectors |
| `st_learning_queue` | `queue_id` | Active learning queue |

### Status Update Table

| Table | Primary Key | Description |
|-------|-------------|-------------|
| `st_hipp_events` | `event_id` | Source events (status update) |

### Outbox Table

| Table | Primary Key | Description |
|-------|-------------|-------------|
| `st_outbox` | `id` | Transactional outbox for events |

### Common Columns in Truth Tables

| Column | Type | Description |
|--------|------|-------------|
| `version` | `INTEGER` | Optimistic lock version (starts at 1) |
| `created_at` | `BIGINT` | Creation timestamp (ms) |
| `updated_at` | `BIGINT` | Last update timestamp (ms) |
| `archival_status` | `TEXT` | NULL, 'ARCHIVED', or 'TOMBSTONE' |
| `archived_at` | `BIGINT` | Archive timestamp (ms) |
| `archived_reason` | `TEXT` | Reason for archival |

---

## 7. UnitOfWork Pattern

### Purpose

`UnitOfWork` provides **ACID transaction management** for PostgreSQL via asyncpg.

### Location

```
k0/uow/unit_of_work.py (268 lines)
```

### Key Features

| Feature | Implementation |
|---------|----------------|
| **Transaction Boundary** | Async context manager (`async with`) |
| **Auto-Commit** | On successful exit |
| **Auto-Rollback** | On exception |
| **Outbox Staging** | `stage_outbox(entry)` buffers events |
| **WAL Append** | `append_wal(record)` for audit |

### Usage Pattern

```python
async with UnitOfWork(pool) as uow:
    # All database operations here use uow.connection
    await uow.connection.execute("INSERT INTO st_epi ...")

    # Stage outbox event (written on commit)
    uow.stage_outbox(OutboxEntry(...))

    # Implicit commit on successful exit
    # Implicit rollback on exception
```

### UnitOfWork API

```python
class UnitOfWork:
    """
    Manages a single PostgreSQL transaction.

    Attributes:
        connection: asyncpg connection
    """

    async def __aenter__(self) -> UnitOfWork:
        """Start transaction, acquire connection."""
        self._conn = await self._pool.acquire()
        self._tx = self._conn.transaction()
        await self._tx.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Commit or rollback based on exception."""
        if exc_type is None:
            await self._commit()
        else:
            await self._rollback()
        await self._pool.release(self._conn)

    def stage_outbox(self, entry: OutboxEntry) -> None:
        """Buffer outbox entry for commit-time write."""
        self._outbox_entries.append(entry)

    def append_wal(self, record: dict) -> None:
        """Append to write-ahead log for audit."""
        self._wal_records.append(record)

    async def _commit(self) -> None:
        """Commit transaction and flush outbox."""
        await self._flush_outbox()  # Write buffered events
        await self._tx.commit()

    async def _rollback(self) -> None:
        """Rollback transaction, discard outbox."""
        self._outbox_entries.clear()
        await self._tx.rollback()
```

### Commit Hooks

```python
# Outbox flush happens before commit
async def _flush_outbox(self) -> None:
    for entry in self._outbox_entries:
        await self._conn.execute(
            """
            INSERT INTO st_outbox (tenant_id, space_id, driver, op_kind, payload, fingerprint)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (fingerprint) DO NOTHING
            """,
            entry.tenant_id,
            entry.space_id,
            entry.driver,
            entry.op_kind,
            entry.payload,
            entry.fingerprint,
        )
```

---

## 8. DecisionRouter & Layer Writers

### DecisionRouter (M5 Architecture)

The `DecisionRouter` routes staged writes to per-layer writers. This modular architecture is enabled when `USE_M5_ROUTER = True`.

#### Location

```
k0/modules/consolidation/truth_writer/router.py (285 lines)
```

#### WriteMode Enum

```python
class WriteMode(str, Enum):
    ATOMIC = "atomic"     # All-or-nothing: rollback on any failure
    PARTIAL = "partial"   # Continue on failure, track failed IDs
```

#### LayerWriterProtocol

```python
class LayerWriterProtocol(Protocol):
    """Protocol for layer-specific writers."""

    @property
    def layer(self) -> str:
        """Target layer name."""
        ...

    async def write(
        self,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> LayerWriteResult:
        """Execute writes for this layer."""
        ...
```

#### DecisionRouter Usage

```python
# Initialize with layer writers
router = DecisionRouter(
    writers=[
        EpisodicLayerWriter(),
        SemanticLayerWriter(),
        ProceduralLayerWriter(),
        SocialLayerWriter(),
        ProspectiveLayerWriter(),
        KGLayerWriter(),
        VectorLayerWriter(),
    ]
)

# Route writes
result = await router.route(staged_writes, uow, mode=WriteMode.ATOMIC)
```

#### Routing Logic

```python
async def route(
    self,
    writes: List[StagedWrite],
    uow: UnitOfWork,
    mode: WriteMode = WriteMode.ATOMIC,
) -> WriteResult:
    """
    Route writes to appropriate layer writers.

    Groups writes by layer, then processes each layer
    in dependency order.
    """
    grouped = self._group_by_layer(writes)
    layer_results: Dict[str, LayerWriteResult] = {}

    for layer in WRITE_ORDER:
        if layer not in grouped:
            continue

        writer = self._writers.get(layer)
        if writer is None:
            raise DecisionRouterError(f"No writer for layer: {layer}")

        result = await writer.write(grouped[layer], uow)
        layer_results[layer] = result

        # ATOMIC mode: stop on first failure
        if mode == WriteMode.ATOMIC and not result.is_success:
            raise DecisionRouterError(
                f"Atomic write failed in layer {layer}: {result.error_message}"
            )

    return WriteResult.from_layer_results(layer_results)
```

### Layer Writers

Each layer has a dedicated writer implementing `LayerWriterProtocol`:

| Writer | Layer | Location |
|--------|-------|----------|
| `EpisodicLayerWriter` | `st_epi` | `layers/episodic.py` |
| `SemanticLayerWriter` | `st_sem` | `layers/semantic.py` |
| `ProceduralLayerWriter` | `st_procedural` | `layers/procedural.py` |
| `SocialLayerWriter` | `st_social` | `layers/social.py` |
| `ProspectiveLayerWriter` | `st_prospective` | `layers/prospective.py` |
| `KGLayerWriter` | `st_kg_dom`, `st_kg_edges` | `layers/kg.py` |
| `VectorLayerWriter` | `st_vec` | `layers/vector.py` |

### Action-Based Updates

Some layers support action-based updates for semantic operations:

#### SemanticLayerWriter Actions

| Action | Effect |
|--------|--------|
| `REINFORCE` | Boost confidence by 0.05, increment observation_count |
| `EXTEND` | Append episodes to source_episodes_json |
| `EVOLVE` | Mark is_canonical=false, set parent_pattern_id |

#### ProceduralLayerWriter Actions

| Action | Effect |
|--------|--------|
| `REINFORCE` | Boost confidence ×1.1, update temporal_regularity |
| `EXTEND` | Append action sequences to action_sequence_json |

#### SocialLayerWriter Actions

| Action | Effect |
|--------|--------|
| `REINFORCE` | Boost strength ×1.1, update sentiment (EMA) |
| `EXTEND` | Add interaction types to array |
| `DECAY` | Apply decay factor (×0.95) for inactivity |

#### ProspectiveLayerWriter Actions

| Action | Effect |
|--------|--------|
| `EXTEND` | Update goal_inference_json, add trigger contexts |
| `COMPLETE` | Set status='completed', completed_at=now |
| `COUNTERFACTUAL` | Store counterfactual_json from R5 CPN |

---

## 9. Optimistic Locking & Version Conflicts

### Mechanism

All truth tables use a `version` column for optimistic concurrency control:

1. **INSERT**: Sets `version = 1` on creation
2. **UPDATE**: Checks `WHERE version = expected_version`, increments on success
3. **Conflict**: If `version` doesn't match, `UPDATE` affects 0 rows

### OptimisticLockError

```python
class OptimisticLockError(Exception):
    """Raised when version conflict detected during UPDATE."""
    pass
```

### Update Pattern

```python
async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
    result = await uow.connection.execute(
        """
        UPDATE st_sem
        SET current_confidence = $1,
            observation_count = observation_count + 1,
            version = version + 1
        WHERE pattern_id = $2
          AND version = $3
        """,
        new_confidence,
        write.record_id,
        write.expected_version,
    )

    rows_affected = _parse_rows_affected(result)
    if rows_affected == 0 and write.expected_version is not None:
        raise OptimisticLockError(f"Version conflict for st_sem:{write.record_id}")
```

### TransactionCoordinator (Retry Logic)

```python
@dataclass
class TransactionConfig:
    max_retries: int = 3
    retry_delay_ms: int = 100  # Base delay
    write_mode: WriteMode = WriteMode.ATOMIC

class TransactionCoordinator:
    """
    Coordinates writes with retry on version conflicts.

    Implements exponential backoff:
        attempt 1: 100ms
        attempt 2: 200ms
        attempt 3: 400ms
    """

    async def execute(
        self,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> TransactionResult:
        for attempt in range(1, self._config.max_retries + 1):
            try:
                result = await self._router.route(writes, uow, self._config.write_mode)
                return TransactionResult(success=True, result=result, attempts=attempt)
            except OptimisticLockError:
                if attempt < self._config.max_retries:
                    await self._backoff(attempt)
                    await self._refresh_versions(writes, uow)
                else:
                    raise

    async def _backoff(self, attempt: int) -> None:
        delay_ms = self._config.retry_delay_ms * (2 ** (attempt - 1))
        await asyncio.sleep(delay_ms / 1000)

    async def _refresh_versions(self, writes: List[StagedWrite], uow: UnitOfWork) -> None:
        """Re-fetch current versions from database for retry."""
        for write in writes:
            if write.operation == WriteOperation.UPDATE:
                current = await self._get_current_version(uow, write.layer, write.record_id)
                write.expected_version = current
```

---

## 10. Outbox Staging

### Purpose

The outbox pattern ensures events are emitted **exactly-once** with the transaction:

1. Events are staged in `st_outbox` within the R7 transaction
2. On commit, events become visible
3. A background worker polls `st_outbox` and emits to event bus
4. Fingerprint prevents duplicates on retry

### OutboxWriter

```python
class OutboxWriter:
    """
    Stages writes and events in st_outbox for durability.

    Fingerprint format:
        p03:write:{cycle_ulid}:{layer}:{record_id}
        p03:event:{event_id}
    """

    def stage_write(
        self,
        uow: UnitOfWork,
        write: StagedWrite,
        tenant_id: str,
        space_id: str,
        cycle_ulid: Optional[str] = None,
    ) -> str:
        """Stage a StagedWrite as an outbox entry."""
        fingerprint = self._generate_fingerprint(write, cycle_ulid)

        entry = OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=tenant_id,
            space_id=space_id,
            driver=write.layer,
            op_kind=write.operation.value,
            payload=json.dumps(write.record_data).encode("utf-8"),
            fingerprint=fingerprint,
            requeue_seq=0,
            retries=0,
        )

        uow.stage_outbox(entry)
        return fingerprint
```

### P08 Coordination (VectorLayerWriter)

`VectorLayerWriter` notifies P08 embedding index via outbox events:

| Event Topic | Trigger |
|-------------|---------|
| `p03.embedding.created.v1` | INSERT into st_vec |
| `p03.embedding.updated.v1` | UPDATE to st_vec |

Includes circuit breaker to prevent cascade failure if P08 is unavailable:

```python
@dataclass
class P08CircuitBreakerConfig:
    failure_threshold: int = 5
    reset_timeout_ms: int = 60000  # 1 minute
    use_cached_on_failure: bool = True

def _is_circuit_open(self) -> bool:
    if self._p08_failures < self._p08_config.failure_threshold:
        return False
    now = _now_ms()
    if now - self._last_failure_ms > self._p08_config.reset_timeout_ms:
        self._p08_failures = 0
        return False
    return True
```

---

## 11. Status Writeback

### Purpose

After successful writes, R7 updates the source events in `st_hipp_events` to mark them as consolidated.

### Status Update Query

```python
async def _writeback_status(
    self,
    uow: UnitOfWork,
    event_ids: List[str],
    cycle_id: str,
) -> None:
    now = _now_ms()
    await uow.connection.execute(
        """
        UPDATE st_hipp_events
        SET consolidation_status = 'COMPLETE',
            consolidation_cycle_id = $1,
            consolidated_at = $2
        WHERE event_id = ANY($3)
          AND consolidation_status IN ('PENDING', 'PROCESSING')
        """,
        cycle_id,
        now,
        event_ids,
    )
```

### Allowed Status Transitions

```python
ALLOWED_TRANSITIONS = {
    None: ["PENDING", "PROCESSING"],
    "PENDING": ["PROCESSING", "COMPLETE", "FAILED"],
    "PROCESSING": ["COMPLETE", "FAILED", "PENDING"],  # PENDING for retry
    "COMPLETE": [],  # Terminal state
    "FAILED": ["PENDING"],  # Retry only
}
```

| From Status | To Status | When |
|-------------|-----------|------|
| `NULL`/`PENDING` | `PROCESSING` | R0 selects event |
| `PROCESSING` | `COMPLETE` | R7 succeeds |
| `PROCESSING` | `FAILED` | R7 fails after retries |
| `FAILED` | `PENDING` | Manual retry trigger |

---

## 12. Configuration

### R7 Configuration Points

| Config | Default | Description |
|--------|---------|-------------|
| `USE_M5_ROUTER` | `False` | Enable modular DecisionRouter |
| `max_retries` | `3` | Version conflict retry attempts |
| `retry_delay_ms` | `100` | Base backoff delay |
| `write_mode` | `ATOMIC` | ATOMIC or PARTIAL |

### Per-Layer Configuration

#### VectorLayerWriter

| Config | Default | Description |
|--------|---------|-------------|
| `failure_threshold` | `5` | P08 circuit breaker threshold |
| `reset_timeout_ms` | `60000` | Circuit reset timeout (1 min) |
| `use_cached_on_failure` | `True` | Use cached embeddings if P08 down |

#### SemanticLayerWriter

| Config | Default | Description |
|--------|---------|-------------|
| `REINFORCE_BOOST` | `0.05` | Confidence boost per reinforcement |

#### ProceduralLayerWriter

| Config | Default | Description |
|--------|---------|-------------|
| `REINFORCE_FACTOR` | `1.1` | Multiplicative confidence boost |

#### SocialLayerWriter

| Config | Default | Description |
|--------|---------|-------------|
| `REINFORCE_FACTOR` | `1.1` | Multiplicative strength boost |
| `DECAY_FACTOR` | `0.95` | Decay multiplier for inactivity |
| `SENTIMENT_NEW_WEIGHT` | `0.1` | New sentiment weight in EMA |
| `SENTIMENT_OLD_WEIGHT` | `0.9` | Old sentiment weight in EMA |

---

## 13. Error Handling

### Error Categories

| Error | Cause | Handling |
|-------|-------|----------|
| `OptimisticLockError` | Version mismatch | Retry with refreshed version |
| `DecisionRouterError` | No writer for layer | Fail immediately |
| `IntegrityError` | FK constraint violation | Check dependency order |
| `DeadlockDetected` | Concurrent transactions | Retry after backoff |

### Legacy Error Handling (USE_M5_ROUTER=False)

```python
async def _execute_single_write(
    self,
    uow: UnitOfWork,
    write: StagedWrite,
) -> bool:
    """Execute a single write, return True on success."""
    try:
        if write.operation == WriteOperation.INSERT:
            await self._execute_insert(uow, write)
        elif write.operation == WriteOperation.UPDATE:
            await self._execute_update(uow, write)
        elif write.operation == WriteOperation.ARCHIVE:
            await self._execute_archive(uow, write)
        elif write.operation == WriteOperation.TOMBSTONE:
            await self._execute_tombstone(uow, write)
        return True
    except OptimisticLockError:
        # Log and continue (tracked in failed_ids)
        return False
    except Exception as e:
        # Log unexpected error
        return False
```

### M5 Error Handling (USE_M5_ROUTER=True)

```python
async def route(self, writes, uow, mode):
    for layer in WRITE_ORDER:
        result = await writer.write(grouped[layer], uow)

        if mode == WriteMode.ATOMIC and not result.is_success:
            raise DecisionRouterError(
                f"Atomic write failed in layer {layer}"
            )
        # PARTIAL mode continues, tracking failures
```

---

## 14. ASCII Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              R7 TRUTH WRITER                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                         INPUT FROM R6                                   │     │
│  │  P03BatchEnvelope.staged_writes: List[StagedWrite]                     │     │
│  │    ├── layer: "st_epi" | "st_sem" | "st_procedural" | ...              │     │
│  │    ├── operation: INSERT | UPDATE | ARCHIVE | TOMBSTONE                │     │
│  │    ├── record_id: Primary key value                                    │     │
│  │    ├── record_data: Dict[str, Any]                                     │     │
│  │    └── expected_version: Optional[int] (for UPDATE)                    │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                      │                                           │
│                                      ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                         UNIT OF WORK                                    │     │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │     │
│  │  │  PostgreSQL Transaction (BEGIN ... COMMIT/ROLLBACK)              │  │     │
│  │  │                                                                   │  │     │
│  │  │  ┌─────────────────────────────────────────────────────────────┐ │  │     │
│  │  │  │                  DECISION ROUTER (M5)                       │ │  │     │
│  │  │  │  ┌─────────────────────────────────────────────────────────┐│ │  │     │
│  │  │  │  │ DEPENDENCY ORDER:                                       ││ │  │     │
│  │  │  │  │                                                          ││ │  │     │
│  │  │  │  │  1. st_vec ────────────▶ VectorLayerWriter              ││ │  │     │
│  │  │  │  │                            └─▶ P08 outbox events        ││ │  │     │
│  │  │  │  │                                                          ││ │  │     │
│  │  │  │  │  2. st_kg_dom ─────────▶ KGLayerWriter                  ││ │  │     │
│  │  │  │  │  3. st_kg_edges ───────▶ KGLayerWriter (dual-layer)     ││ │  │     │
│  │  │  │  │                                                          ││ │  │     │
│  │  │  │  │  4. st_epi ────────────▶ EpisodicLayerWriter            ││ │  │     │
│  │  │  │  │  5. st_sem ────────────▶ SemanticLayerWriter            ││ │  │     │
│  │  │  │  │  6. st_procedural ─────▶ ProceduralLayerWriter          ││ │  │     │
│  │  │  │  │  7. st_social ─────────▶ SocialLayerWriter              ││ │  │     │
│  │  │  │  │  8. st_prospective ────▶ ProspectiveLayerWriter         ││ │  │     │
│  │  │  │  │                                                          ││ │  │     │
│  │  │  │  │  9. st_learning_queue ─▶ (inline SQL)                   ││ │  │     │
│  │  │  │  │  10. st_hipp_events ───▶ Status writeback               ││ │  │     │
│  │  │  │  └─────────────────────────────────────────────────────────┘│ │  │     │
│  │  │  └─────────────────────────────────────────────────────────────┘ │  │     │
│  │  │                                                                   │  │     │
│  │  │  ┌─────────────────────────────────────────────────────────────┐ │  │     │
│  │  │  │                 OUTBOX STAGING                              │ │  │     │
│  │  │  │  st_outbox ◀── p03.truth.created.v1                        │ │  │     │
│  │  │  │            ◀── p03.truth.reinforced.v1                     │ │  │     │
│  │  │  │            ◀── p03.truth.evolved.v1                        │ │  │     │
│  │  │  │            ◀── p03.embedding.created.v1 (P08)              │ │  │     │
│  │  │  └─────────────────────────────────────────────────────────────┘ │  │     │
│  │  └──────────────────────────────────────────────────────────────────┘  │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                      │                                           │
│                                      ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                         OUTPUT TO R8                                    │     │
│  │  P03PhaseResult                                                        │     │
│  │    ├── writes_succeeded: int                                           │     │
│  │    ├── writes_failed: int                                              │     │
│  │    ├── by_layer: Dict[str, LayerWriteResult]                          │     │
│  │    └── events_staged: int                                              │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Version Conflict Retry Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    VERSION CONFLICT HANDLING                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐                                                │
│  │  Attempt 1  │                                                │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ UPDATE st_sem SET ... WHERE pattern_id=$1 AND version=$2│    │
│  └─────────────────────────────────────────────────────────┘    │
│         │                                                        │
│         ├── rows_affected = 1 ──────▶ SUCCESS ✓                 │
│         │                                                        │
│         └── rows_affected = 0 ──────▶ OptimisticLockError       │
│                    │                                             │
│                    ▼                                             │
│              ┌───────────┐                                       │
│              │ Backoff   │ 100ms                                 │
│              │ + Refresh │ (fetch current version)               │
│              └─────┬─────┘                                       │
│                    │                                             │
│                    ▼                                             │
│  ┌─────────────┐                                                │
│  │  Attempt 2  │                                                │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ UPDATE st_sem SET ... WHERE version=$new_version        │    │
│  └─────────────────────────────────────────────────────────┘    │
│         │                                                        │
│         ├── rows_affected = 1 ──────▶ SUCCESS ✓                 │
│         │                                                        │
│         └── rows_affected = 0 ──────▶ Backoff 200ms             │
│                    │                                             │
│                    ▼                                             │
│  ┌─────────────┐                                                │
│  │  Attempt 3  │                                                │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ├── rows_affected = 1 ──────▶ SUCCESS ✓                 │
│         │                                                        │
│         └── rows_affected = 0 ──────▶ FAIL (max retries)        │
│                                       Track in failed_ids       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 15. Summary

### R7 at a Glance

| Aspect | Description |
|--------|-------------|
| **Phase** | R7 Truth Writer |
| **Purpose** | Atomic database commits for consolidation results |
| **Input** | `P03BatchEnvelope.staged_writes` from R6 |
| **Output** | `P03PhaseResult` with write statistics |
| **Tables** | st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_vec |
| **Transaction** | Single PostgreSQL transaction via UnitOfWork |
| **Concurrency** | Optimistic locking with version column |
| **Retries** | Up to 3 attempts with exponential backoff |
| **Durability** | Outbox pattern for event emission |

### Key Design Decisions

1. **Dependency Order**: Writes execute in foreign-key-safe order
2. **Idempotency**: INSERT uses `ON CONFLICT DO NOTHING`
3. **Optimistic Locking**: UPDATE checks version, increments on success
4. **ACID Compliance**: All writes in single transaction
5. **Modular Writers**: Per-layer writers for maintainability (M5)
6. **Outbox Pattern**: Events staged atomically with writes

### Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| [r7_truth_writer.py](../../k0/pipelines/p03/phases/r7_truth_writer.py) | 814 | Phase entry point |
| [unit_of_work.py](../../k0/uow/unit_of_work.py) | 268 | Transaction management |
| [router.py](../../k0/modules/consolidation/truth_writer/router.py) | 285 | M5 DecisionRouter |
| [transaction.py](../../k0/modules/consolidation/truth_writer/transaction.py) | 429 | Retry coordinator |
| [result.py](../../k0/modules/consolidation/truth_writer/result.py) | 260 | Result dataclasses |
| [outbox.py](../../k0/modules/consolidation/truth_writer/outbox.py) | ~300 | Outbox staging |
| [episodic.py](../../k0/modules/consolidation/truth_writer/layers/episodic.py) | 313 | st_epi writer |
| [semantic.py](../../k0/modules/consolidation/truth_writer/layers/semantic.py) | 490 | st_sem writer |
| [procedural.py](../../k0/modules/consolidation/truth_writer/layers/procedural.py) | 444 | st_procedural writer |
| [social.py](../../k0/modules/consolidation/truth_writer/layers/social.py) | 641 | st_social writer |
| [prospective.py](../../k0/modules/consolidation/truth_writer/layers/prospective.py) | 357 | st_prospective writer |
| [kg.py](../../k0/modules/consolidation/truth_writer/layers/kg.py) | 520 | st_kg_dom/edges writer |
| [vector.py](../../k0/modules/consolidation/truth_writer/layers/vector.py) | 448 | st_vec writer with P08 |

---

## Appendix A: Quick Reference

### StagedWrite Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `layer` | `str` | ✓ | Target table (st_epi, st_sem, ...) |
| `operation` | `WriteOperation` | ✓ | INSERT, UPDATE, ARCHIVE, TOMBSTONE |
| `record_id` | `str` | ✓ | Primary key value |
| `record_data` | `Dict[str, Any]` | ✓ | Column values |
| `expected_version` | `int` | For UPDATE | Optimistic lock version |
| `idempotency_key` | `str` | Optional | Fingerprint for dedup |

### WriteOperation Mapping

| Operation | SQL Pattern | Idempotency |
|-----------|-------------|-------------|
| INSERT | `INSERT ... ON CONFLICT DO NOTHING` | fingerprint check |
| UPDATE | `UPDATE ... WHERE version = $n` | version check |
| ARCHIVE | `UPDATE ... SET archival_status = 'ARCHIVED'` | status check |
| TOMBSTONE | `UPDATE ... SET archival_status = 'TOMBSTONE'` | always succeeds |

### Layer Writer Actions

| Layer | Actions Available |
|-------|------------------|
| st_sem | REINFORCE, EXTEND, EVOLVE |
| st_procedural | REINFORCE, EXTEND |
| st_social | REINFORCE, EXTEND, DECAY |
| st_prospective | EXTEND, COMPLETE, COUNTERFACTUAL |
| st_kg_dom | EXTEND, EVOLVE |
| st_kg_edges | (generic update only) |
| st_epi | (generic update only) |
| st_vec | (generic update only) |

---

*Document generated: 2026-01-09*
*Source: k0/pipelines/p03/phases/r7_truth_writer.py and k0/modules/consolidation/truth_writer/*
