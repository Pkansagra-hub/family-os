# P08: Embedding Lifecycle - Development Dossier

**Status**: Architecture Complete - Ready for Implementation
**Last Updated**: 2025-01-XX
**Architecture**: YAML Pipeline (Kernel Boundary Compliant)

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | YAML Pipeline | Maintains kernel boundary integrity |
| Entry Mechanism | Topic subscription | Same pattern as P02/P03 |
| Storage Access | Syscalls only | Capability-gated, auditable |
| Batching | None for K0 | <100 evt/sec throughput |
| Container | Same K0 process | No inter-process overhead |

---

## Purpose

P08 is the **background embedding lifecycle pipeline inside K0** for vector generation.

P08 runs **AFTER P02 has committed to st_hipp_events and st_embedding_queue**:

1. **P02 Write Path** (~171ms):
   - Hippocampus enrichment (DG, CA1, affect, space, social)
   - Atomic write to `st_hipp_events` (enriched event)
   - Insert job to `st_embedding_queue` (status=PENDING)
   - Emit `p02.embedding.enqueued.v1` event via BusDispatcher

2. **P08 Pipeline Processing** (~200ms per embedding):
   - BusDispatcher routes `p02.embedding.enqueued.v1` to P08 PipelineProtocol handler
   - P08 DAG executes: claim -> compute -> store -> index -> update
   - All storage via capability-gated syscalls
   - Emit `p08.embedding.complete.v1` on success

> P08 = "From p02.embedding.enqueued.v1 -> compute vector -> FAISS index -> p08.embedding.complete.v1"

---

## Kernel Boundary Compliance

### Why P08 MUST Be a Pipeline (Not Outbox Driver)

The K0 kernel has a clear boundary defined in `k0_source_of_truth.mmd`:

```
LAYER 1-5: KERNEL CORE (Authoritative)
  Ports, Gate, Policy, UoW, Storage, QoS

LAYER 6: EVENT BUS - THE BOUNDARY
  BusDispatcher
  Pipelines ATTACH here via PipelineProtocol

LAYER 7-8: EXTERNAL
  Query Drivers, Driver SPI
```

**If P08 were an outbox driver (WRONG):**
- Kernel directly invokes driver code via `_outbox_worker_loop`
- No capability enforcement (drivers bypass syscalls)
- No contract validation (no YAML spec)
- Kernel bloat at scale (200 pipelines = 200 driver invocations in kernel)

**As a proper pipeline (CORRECT):**
- Clean separation via `PipelineProtocol.handle(msg)`
- Capability enforcement via `context.syscalls.*`
- Contract validation via YAML spec
- Scalable architecture (kernel stays lean)

### Before vs After Architecture

```
BEFORE (Wrong - Outbox Driver Pattern):

  kernel/app.py                     drivers/
  _outbox_worker_loop()  ---------> EmbeddingQueueDriver.apply()
        |                                  |
        | BREACHES BOUNDARY               | Direct DB access
        v                                  v
  st_outbox polling              st_embedding_queue updates

AFTER (Correct - YAML Pipeline Pattern):

  bus/dispatcher.py                 pipelines/p08_embedding/
  BusDispatcher  -----------------> P08Pipeline.handle(msg)
        |                                  |
        | PipelineProtocol                | Via syscalls
        v                                  v
  Topic subscription             Capability-gated storage
```

---

## Scope & Assumptions

- **P02 emits `p02.embedding.enqueued.v1`** after writing to `st_embedding_queue`
- P08 subscribes to this topic via **BusDispatcher** (same pattern as P02/P03)
- **Single-event processing** for K0 edge devices (no batching needed for <100 evt/sec)
- **Same K0 kernel container** - embedding model loaded in same process
- P08 is **idempotent** - duplicate messages handled gracefully via embedding_id claim
- **sentence-transformers** model: `all-MiniLM-L6-v2` (384-dim vectors)
- P03 depends on P08 completion to query embeddings for semantic search

---

## Inputs/Outputs

### Entry Mechanism (Topic Subscription)

| Property | Value |
|----------|-------|
| Entry Topic | `p02.embedding.enqueued.v1` |
| Trigger | BusDispatcher routes to P08 PipelineProtocol handler |
| Pattern | Same as P02 (topic subscription, NOT polling) |

### Exit Topics

| Topic | Meaning | Consumer |
|-------|---------|----------|
| `p08.embedding.complete.v1` | Full success (computed + indexed) | P03, Observability |
| `p08.embedding.failed.v1` | Permanent failure after max retries | Alerting, DLQ |

### Required Capabilities

| Capability | Module | Purpose |
|------------|--------|---------|
| `st_embedding_queue.read` | claim, update_status | Read job metadata |
| `st_embedding_queue.write` | claim, update_status | Update status |
| `st_hipp_events.read` | compute | Read text content |
| `st_hipp_events.write` | update_status | Update embedding_status |
| `st_embeddings.write` | store | Insert vector metadata |
| `faiss.write` | index_faiss | Add vector to index |

### Syscall Mapping

All storage access via syscalls (capability-gated):

| Syscall | Module | Purpose |
|---------|--------|---------|
| `embedding_queue_claim()` | claim | Mark job IN_PROGRESS (atomic) |
| `hipp_event_read()` | compute | Get text for embedding |
| `embedding_store()` | store | Write computed vector |
| `faiss_add()` | index_faiss | Add to FAISS index |
| `embedding_queue_update_status()` | update_status | Final status update |
| `hipp_event_update_embedding_status()` | update_status | Sync hippo status |

---

## Entry Event Schema

```json
{
  "topic": "p02.embedding.enqueued.v1",
  "payload": {
    "embedding_id": "emb_abc123",
    "event_id": "evt_xyz789",
    "tenant_id": "family-smith",
    "space_id": "personal:dad",
    "vector_kind": "memory.body.text",
    "model_id": "all-MiniLM-L6-v2",
    "priority": "NORMAL"
  },
  "metadata": {
    "wal_pos": 1001,
    "trace_id": "trace_xyz",
    "timestamp": 1732550400000
  }
}
```

---

## Pipeline DAG (5 Stages)

```yaml
# k0/contracts/pipelines/p08_embedding.v1.yaml

pipeline_id: p08_embedding
version: "1"
entry_topic: p02.embedding.enqueued.v1
exit_topic: p08.embedding.complete.v1

required_caps:
  - st_embedding_queue.read
  - st_embedding_queue.write
  - st_hipp_events.read
  - st_hipp_events.write
  - st_embeddings.write
  - faiss.write

dag:
  - stage: claim
    module: embedding.claim:v1
    inputs: [payload]
    outputs: [job]
    on_error: emit_failed

  - stage: compute
    module: embedding.compute:v1
    inputs: [job]
    outputs: [vector]
    depends_on: [claim]
    on_error: retry_with_backoff

  - stage: store
    module: embedding.store:v1
    inputs: [job, vector]
    outputs: [stored]
    depends_on: [compute]
    on_error: retry_with_backoff

  - stage: index_faiss
    module: embedding.index_faiss:v1
    inputs: [job, vector, stored]
    outputs: [indexed]
    depends_on: [store]
    on_error: retry_with_backoff

  - stage: update_status
    module: embedding.update_status:v1
    inputs: [job, indexed]
    outputs: [complete]
    depends_on: [index_faiss]
    on_error: emit_failed
```

### DAG Visualization

```
p02.embedding.enqueued.v1
          |
          v
    +----------+
    |  claim   |  Mark job IN_PROGRESS (idempotent)
    +----------+
          |
          v
    +----------+
    | compute  |  sentence-transformers -> 384-dim vector
    +----------+
          |
          v
    +----------+
    |  store   |  Write vector to st_embedding_queue
    +----------+
          |
          v
    +----------+
    |index_faiss| Add to FAISS index, write st_embeddings
    +----------+
          |
          v
    +----------+
    |update_status| INDEXED status, sync hippo
    +----------+
          |
          v
p08.embedding.complete.v1
```

---

## Module Specifications

### M1: embedding.claim:v1

**Purpose**: Atomically claim embedding job to prevent duplicate processing.

**Contract Location**: `k0/contracts/modules/embedding.claim.v1.yaml`
**Implementation**: `k0/modules/embedding/claim.py`

**Input**:
```python
@dataclass
class ClaimInput:
    embedding_id: str
    tenant_id: str
    space_id: str
```

**Output**:
```python
@dataclass
class ClaimOutput:
    job_id: int
    event_id: str
    embedding_id: str
    status: str  # Should be "IN_PROGRESS" after claim
    vector_kind: str
    model_id: str
```

**Logic**:
```python
async def claim(ctx: ModuleContext, input: ClaimInput) -> ClaimOutput:
    # Atomic claim via syscall
    result = await ctx.syscalls.embedding_queue_claim(
        embedding_id=input.embedding_id,
        expected_status="PENDING"
    )

    if result["status"] == "ALREADY_CLAIMED":
        # Idempotent: skip if already processing
        raise SkipEvent("Job already claimed")

    return ClaimOutput(
        job_id=result["job_id"],
        event_id=result["event_id"],
        embedding_id=result["embedding_id"],
        status="IN_PROGRESS",
        vector_kind=result["vector_kind"],
        model_id=result["model_id"]
    )
```

**Syscall**: `embedding_queue_claim()`
- Capability: `st_embedding_queue.read`, `st_embedding_queue.write`
- Atomicity: UPDATE with WHERE status='PENDING' (prevents race)

---

### M2: embedding.compute:v1

**Purpose**: Generate embedding vector from event text.

**Contract Location**: `k0/contracts/modules/embedding.compute.v1.yaml`
**Implementation**: `k0/modules/embedding/compute.py`

**Input**:
```python
@dataclass
class ComputeInput:
    job: ClaimOutput  # From previous stage
```

**Output**:
```python
@dataclass
class ComputeOutput:
    embedding_id: str
    vector: list[float]  # 384-dim
    model_id: str
    compute_time_ms: int
```

**Logic**:
```python
async def compute(ctx: ModuleContext, input: ComputeInput) -> ComputeOutput:
    # Read text from hippocampus
    event = await ctx.syscalls.hipp_event_read(
        event_id=input.job.event_id
    )

    if not event.get("text"):
        raise PermanentFailure("No text content for embedding")

    # Compute embedding (model preloaded in kernel)
    start = time.monotonic()
    vector = ctx.model.encode(event["text"])
    compute_time_ms = int((time.monotonic() - start) * 1000)

    return ComputeOutput(
        embedding_id=input.job.embedding_id,
        vector=vector.tolist(),
        model_id=input.job.model_id,
        compute_time_ms=compute_time_ms
    )
```

**Syscall**: `hipp_event_read()`
- Capability: `st_hipp_events.read`

**Performance Target**: <200ms P95 (CPU inference)

---

### M3: embedding.store:v1

**Purpose**: Persist computed vector to st_embedding_queue.

**Contract Location**: `k0/contracts/modules/embedding.store.v1.yaml`
**Implementation**: `k0/modules/embedding/store.py`

**Input**:
```python
@dataclass
class StoreInput:
    job: ClaimOutput
    vector: ComputeOutput
```

**Output**:
```python
@dataclass
class StoreOutput:
    embedding_id: str
    status: str  # "READY"
    vector_stored: bool
```

**Logic**:
```python
async def store(ctx: ModuleContext, input: StoreInput) -> StoreOutput:
    # Store vector via syscall
    result = await ctx.syscalls.embedding_store(
        embedding_id=input.job.embedding_id,
        vector_json=json.dumps(input.vector.vector),
        status="READY"
    )

    return StoreOutput(
        embedding_id=input.job.embedding_id,
        status="READY",
        vector_stored=True
    )
```

**Syscall**: `embedding_store()`
- Capability: `st_embedding_queue.write`

---

### M4: embedding.index_faiss:v1

**Purpose**: Add vector to FAISS index and create metadata record.

**Contract Location**: `k0/contracts/modules/embedding.index_faiss.v1.yaml`
**Implementation**: `k0/modules/embedding/index_faiss.py`

**Input**:
```python
@dataclass
class IndexInput:
    job: ClaimOutput
    vector: ComputeOutput
    stored: StoreOutput
```

**Output**:
```python
@dataclass
class IndexOutput:
    embedding_id: str
    vector_id: int  # FAISS index position
    indexed: bool
```

**Logic**:
```python
async def index_faiss(ctx: ModuleContext, input: IndexInput) -> IndexOutput:
    # Add to FAISS via syscall
    result = await ctx.syscalls.faiss_add(
        embedding_id=input.job.embedding_id,
        event_id=input.job.event_id,
        tenant_id=input.job.tenant_id,
        space_id=input.job.space_id,
        vector=input.vector.vector
    )

    return IndexOutput(
        embedding_id=input.job.embedding_id,
        vector_id=result["vector_id"],
        indexed=True
    )
```

**Syscall**: `faiss_add()`
- Capability: `faiss.write`, `st_embeddings.write`
- Actions: Add to FAISS index, insert st_embeddings metadata

**Performance Target**: <30ms P95

---

### M5: embedding.update_status:v1

**Purpose**: Final status update and hippo sync.

**Contract Location**: `k0/contracts/modules/embedding.update_status.v1.yaml`
**Implementation**: `k0/modules/embedding/update_status.py`

**Input**:
```python
@dataclass
class UpdateInput:
    job: ClaimOutput
    indexed: IndexOutput
```

**Output**:
```python
@dataclass
class UpdateOutput:
    embedding_id: str
    final_status: str  # "INDEXED"
    hippo_synced: bool
```

**Logic**:
```python
async def update_status(ctx: ModuleContext, input: UpdateInput) -> UpdateOutput:
    # Update queue status
    await ctx.syscalls.embedding_queue_update_status(
        embedding_id=input.job.embedding_id,
        status="INDEXED"
    )

    # Sync hippo status
    await ctx.syscalls.hipp_event_update_embedding_status(
        embedding_id=input.job.embedding_id,
        embedding_status="READY"
    )

    return UpdateOutput(
        embedding_id=input.job.embedding_id,
        final_status="INDEXED",
        hippo_synced=True
    )
```

**Syscalls**:
- `embedding_queue_update_status()` - Capability: `st_embedding_queue.write`
- `hipp_event_update_embedding_status()` - Capability: `st_hipp_events.write`

---

## Module Mapping Summary

| Stage | Module | Location | Syscalls |
|-------|--------|----------|----------|
| claim | `embedding.claim:v1` | `k0/modules/embedding/claim.py` | embedding_queue_claim |
| compute | `embedding.compute:v1` | `k0/modules/embedding/compute.py` | hipp_event_read |
| store | `embedding.store:v1` | `k0/modules/embedding/store.py` | embedding_store |
| index_faiss | `embedding.index_faiss:v1` | `k0/modules/embedding/index_faiss.py` | faiss_add |
| update_status | `embedding.update_status:v1` | `k0/modules/embedding/update_status.py` | embedding_queue_update_status, hipp_event_update_embedding_status |

---

## Storage Schema

### Table 1: st_embedding_queue (Migration 0024)

**Purpose**: Job queue for P08 vector generation. P02 inserts, P08 processes.

```sql
CREATE TABLE st_embedding_queue (
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  embedding_id TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  vector_kind TEXT NOT NULL DEFAULT 'memory.body.text',
  model_id TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
  priority TEXT NOT NULL DEFAULT 'NORMAL',
  status TEXT NOT NULL DEFAULT 'PENDING',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_ts INTEGER,
  last_error TEXT,
  vector_json TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_eq_status ON st_embedding_queue(status, priority, created_at);
CREATE INDEX idx_eq_embedding_id ON st_embedding_queue(embedding_id);
```

**Status Lifecycle**:
```
PENDING (P02 creates)
    |
    v
IN_PROGRESS (P08 claim module)
    |
    +----> READY (P08 store module) ----> INDEXED (P08 update_status)
    |
    +----> FAILED_RETRYABLE (transient error, will retry)
                |
                v (after max attempts)
           FAILED_PERMANENT (DLQ)
```

### Table 2: st_embeddings (FAISS Metadata)

**Purpose**: Links FAISS vector_id to embedding_id for search filtering.

```sql
CREATE TABLE st_embeddings (
  vector_id INTEGER PRIMARY KEY,
  embedding_id TEXT NOT NULL UNIQUE,
  event_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  vector_norm REAL NOT NULL,
  indexed_at INTEGER NOT NULL
);

CREATE INDEX idx_emb_tenant_space ON st_embeddings(tenant_id, space_id);
```

### Column: st_hipp_events.embedding_status

**Purpose**: Single source of truth for embedding readiness from P03's perspective.

| Status | Set By | Meaning |
|--------|--------|---------|
| PENDING | P02 | Job created, awaiting processing |
| IN_PROGRESS | P08 claim | Currently computing |
| READY | P08 update_status | Vector computed and indexed |
| FAILED | P08 (max retries) | Permanent failure |

### FAISS Index File

| Setting | Default | Environment Variable |
|---------|---------|---------------------|
| Index Path | `./k0_faiss.index` | `K0_FAISS_INDEX_PATH` |
| Dimension | 384 | `K0_FAISS_DIMENSION` |
| Index Type | IndexFlatL2 | N/A (hardcoded for small datasets) |

---

## New Syscalls Required

### syscalls.embedding_queue_claim()

```python
async def embedding_queue_claim(
    self,
    embedding_id: str,
    expected_status: str = "PENDING",
) -> dict:
    """
    Atomically claim embedding job.

    Capability Required: st_embedding_queue.read, st_embedding_queue.write

    Returns:
        {"status": "CLAIMED", "job_id": int, ...} on success
        {"status": "ALREADY_CLAIMED"} if already processing
        {"status": "NOT_FOUND"} if job doesn't exist
    """
```

### syscalls.hipp_event_read()

```python
async def hipp_event_read(
    self,
    event_id: str,
) -> dict:
    """
    Read event from st_hipp_events.

    Capability Required: st_hipp_events.read

    Returns:
        Event dict with text, metadata, etc.
    """
```

### syscalls.embedding_store()

```python
async def embedding_store(
    self,
    embedding_id: str,
    vector_json: str,
    status: str = "READY",
) -> dict:
    """
    Store computed vector to st_embedding_queue.

    Capability Required: st_embedding_queue.write
    """
```

### syscalls.faiss_add()

```python
async def faiss_add(
    self,
    embedding_id: str,
    event_id: str,
    tenant_id: str,
    space_id: str,
    vector: list[float],
) -> dict:
    """
    Add vector to FAISS index and create st_embeddings metadata.

    Capability Required: faiss.write, st_embeddings.write

    Returns:
        {"vector_id": int, "indexed": True}
    """
```

### syscalls.embedding_queue_update_status()

```python
async def embedding_queue_update_status(
    self,
    embedding_id: str,
    status: str,
    error: str | None = None,
) -> dict:
    """
    Update st_embedding_queue status.

    Capability Required: st_embedding_queue.write
    """
```

### syscalls.hipp_event_update_embedding_status()

```python
async def hipp_event_update_embedding_status(
    self,
    embedding_id: str,
    embedding_status: str,
) -> dict:
    """
    Update st_hipp_events.embedding_status.

    Capability Required: st_hipp_events.write
    """
```

---

## Error Handling

### Retry Strategy

| Error Type | Action | Backoff |
|------------|--------|---------|
| Transient (network, load) | Retry | Exponential (1m, 2m, 4m, 8m, 16m) |
| Permanent (no text, invalid) | Fail | No retry |

### Error Flow

```
on_error: retry_with_backoff
    |
    v
attempt_count++
next_attempt_ts = now + (2^attempt * 60s)
status = FAILED_RETRYABLE
    |
    +----> If attempt_count >= max_attempts:
           status = FAILED_PERMANENT
           emit p08.embedding.failed.v1
```

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Embedding computation | <200ms P95 | CPU inference, single text |
| FAISS insert | <30ms P95 | IndexFlatL2, single vector |
| End-to-end latency | <500ms P95 | claim -> indexed |
| Throughput | ~5 vectors/sec (CPU) | Adequate for <100 evt/sec |
| Model load time | ~2 seconds | One-time at kernel startup |
| Model memory | ~100MB | all-MiniLM-L6-v2 |
| Vector storage | ~1.5KB/vector | 384 x float32 |

---

## Dependencies

### Required Python Packages

```text
sentence-transformers>=2.2.0    # Embedding model
torch>=2.0.0                    # Model inference
faiss-cpu>=1.7.4                # Vector indexing
numpy>=1.24.0                   # Array operations
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `K0_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `K0_FAISS_INDEX_PATH` | `./k0_faiss.index` | FAISS index file path |
| `K0_FAISS_DIMENSION` | `384` | Vector dimension |

---

## Implementation Status

### Existing Components

| Component | Location | Status |
|-----------|----------|--------|
| st_embedding_queue table | Migration 0024 | Exists |
| st_hipp_events columns | Migration 0024 | Exists |
| syscalls.embedding_enqueue | k0/kernel/syscalls.py | Exists |
| syscalls.outbox_emit_batch | k0/kernel/syscalls.py | Exists |
| EmbeddingQueueDriver | k0/drivers/embedding_queue.py | Exists (refactor to modules) |
| FaissDriver | k0/drivers/faiss.py | Exists (refactor to modules) |

### Components to Create

| Component | Location | Priority |
|-----------|----------|----------|
| P08 YAML contract | k0/contracts/pipelines/p08_embedding.v1.yaml | P0 |
| embedding.claim module | k0/modules/embedding/claim.py | P0 |
| embedding.compute module | k0/modules/embedding/compute.py | P0 |
| embedding.store module | k0/modules/embedding/store.py | P0 |
| embedding.index_faiss module | k0/modules/embedding/index_faiss.py | P0 |
| embedding.update_status module | k0/modules/embedding/update_status.py | P0 |
| syscalls.embedding_queue_claim | k0/kernel/syscalls.py | P0 |
| syscalls.hipp_event_read | k0/kernel/syscalls.py | P0 |
| syscalls.embedding_store | k0/kernel/syscalls.py | P0 |
| syscalls.faiss_add | k0/kernel/syscalls.py | P0 |
| syscalls.embedding_queue_update_status | k0/kernel/syscalls.py | P0 |
| syscalls.hipp_event_update_embedding_status | k0/kernel/syscalls.py | P0 |
| P08 contract tests | tests/contracts/p08/ | P1 |
| P08 integration tests | tests/integration/p08/ | P1 |

---

## P02 Integration

### M14 Changes Required

P02's M14 module (`builders.embedding_queue_write`) must:

1. Insert to `st_embedding_queue` via existing `syscalls.embedding_enqueue()`
2. Emit `p02.embedding.enqueued.v1` via `syscalls.bus_emit()` (NEW)

```python
# k0/modules/builders/embedding_queue_write.py

async def embedding_queue_write(ctx: ModuleContext, input: Input) -> Output:
    # 1. Insert job (existing)
    result = await ctx.syscalls.embedding_enqueue(
        embedding_id=input.embedding_id,
        event_id=input.event_id,
        ...
    )

    # 2. Emit event (NEW - triggers P08)
    await ctx.syscalls.bus_emit(
        topic="p02.embedding.enqueued.v1",
        payload={
            "embedding_id": input.embedding_id,
            "event_id": input.event_id,
            "tenant_id": input.tenant_id,
            "space_id": input.space_id,
            "vector_kind": input.vector_kind,
            "model_id": input.model_id,
            "priority": input.priority
        }
    )
```

---

## P03 Contract

P03 queries embeddings for semantic search:

```sql
-- Check if embeddings are ready
SELECT COUNT(*) as pending
FROM st_hipp_events
WHERE tenant_id = ?
  AND space_id = ?
  AND embedding_status != 'READY'
  AND created_at > ?
```

```python
# Semantic search
distances, vector_ids = faiss_index.search(query_vector, k=10)
event_ids = await ctx.syscalls.embeddings_get_event_ids(vector_ids)
```

---

## Event Flow Diagram

```
+-----------------------------------------------------------+
|                    P02 COMPLETION                          |
+-----------------------------------------------------------+
                          |
                          v
        +------------------------------------+
        | M14: builders.embedding_queue_write |
        |                                    |
        | 1. syscalls.embedding_enqueue()    |
        |    -> INSERT st_embedding_queue    |
        |                                    |
        | 2. syscalls.bus_emit()             |
        |    -> p02.embedding.enqueued.v1    |
        +------------------------------------+
                          |
                          v
+-----------------------------------------------------------+
|                    BUS DISPATCHER                          |
|         Route p02.embedding.enqueued.v1 -> P08            |
+-----------------------------------------------------------+
                          |
                          v
        +------------------------------------+
        | P08 Pipeline Handler               |
        |                                    |
        | Stage 1: embedding.claim           |
        |   -> syscalls.embedding_queue_claim|
        |   -> IN_PROGRESS                   |
        +------------------------------------+
                          |
                          v
        +------------------------------------+
        | Stage 2: embedding.compute         |
        |   -> syscalls.hipp_event_read      |
        |   -> model.encode(text)            |
        |   -> 384-dim vector                |
        +------------------------------------+
                          |
                          v
        +------------------------------------+
        | Stage 3: embedding.store           |
        |   -> syscalls.embedding_store      |
        |   -> READY                         |
        +------------------------------------+
                          |
                          v
        +------------------------------------+
        | Stage 4: embedding.index_faiss     |
        |   -> syscalls.faiss_add            |
        |   -> FAISS index + st_embeddings   |
        +------------------------------------+
                          |
                          v
        +------------------------------------+
        | Stage 5: embedding.update_status   |
        |   -> syscalls.embedding_queue_     |
        |      update_status (INDEXED)       |
        |   -> syscalls.hipp_event_update_   |
        |      embedding_status (READY)      |
        +------------------------------------+
                          |
                          v
+-----------------------------------------------------------+
|          p08.embedding.complete.v1 EMITTED                 |
|                                                           |
|          P03 CAN NOW QUERY EMBEDDINGS                      |
+-----------------------------------------------------------+
```

---

## File Structure

```
k0/
  contracts/
    pipelines/
      p08_embedding.v1.yaml           # Pipeline YAML spec
    modules/
      embedding.claim.v1.yaml         # Module contracts
      embedding.compute.v1.yaml
      embedding.store.v1.yaml
      embedding.index_faiss.v1.yaml
      embedding.update_status.v1.yaml
  modules/
    embedding/
      __init__.py
      claim.py                        # M1
      compute.py                      # M2
      store.py                        # M3
      index_faiss.py                  # M4
      update_status.py                # M5
  kernel/
    syscalls.py                       # +6 new syscalls

tests/
  contracts/
    p08/
      test_p08_embedding_contract.py
  integration/
    p08/
      test_p08_embedding_e2e.py
```

---

## ADR Reference

**ADR-P08-001**: P08 Architecture Decision - YAML Pipeline vs Outbox Driver

- **Status**: ACCEPTED
- **Decision**: P08 implemented as YAML pipeline with topic subscription
- **Rationale**: Maintains kernel boundary integrity, scales to 200+ pipelines
- **Consequences**: Requires new syscalls, refactor drivers to modules

---

## References

- `k0/runtime/README.md` - PipelineRunner, ModuleRegistry documentation
- `k0/contracts/pipelines/p02_write.v1.yaml` - Reference YAML pipeline format
- `docs/architecture/decisions-K0/` - ADR location
- `k0/drivers/embedding_queue.py` - Existing code to refactor
- `k0/drivers/faiss.py` - Existing code to refactor
- `k0/kernel/syscalls.py` - Syscalls implementation
