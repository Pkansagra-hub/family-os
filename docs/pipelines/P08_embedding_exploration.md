# P08 Embedding Pipeline - Architecture Exploration

**Status**: Architecture Complete - Ready for Implementation
**Created**: 2025-11-25
**Updated**: 2025-11-25
**Purpose**: Understand P08 implementation requirements before P03 can proceed
**Architecture**: YAML Pipeline (Kernel Boundary Compliant)

---

## Executive Summary

P08 (Embedding Lifecycle Pipeline) must be implemented **BEFORE P03** because:

1. P02 emits `p02.embedding.enqueued.v1` after writing to `st_embedding_queue`
2. P03 depends on embeddings being available in FAISS for semantic search and consolidation
3. Without P08, `st_embedding_queue` accumulates PENDING jobs indefinitely

**Architecture Decision**: P08 is a **YAML pipeline** (not outbox driver) to maintain kernel boundary integrity.

**Existing Infrastructure**:

- ✅ `st_embedding_queue` table exists (migration 0024)
- ✅ `EmbeddingQueueDriver` exists - to be **refactored to modules**
- ✅ `FaissDriver` exists - to be **refactored to modules**
- ✅ Runtime infrastructure ready (`k0/runtime/` - PipelineRunner, ModuleRegistry)
- ✅ BusDispatcher for topic subscription (`k0/bus/`)
- ⚠️ Missing: P08 YAML contract, embedding modules, new syscalls

---

## Key Architecture Decisions (Revised)

### Decision 1: YAML Pipeline Architecture (Kernel Boundary Compliant)

**Critical**: P08 MUST be a YAML pipeline to maintain kernel boundary integrity.

```
k0/
├── contracts/pipelines/
│   └── p08_embedding.v1.yaml   # Pipeline YAML spec
├── modules/embedding/          # Pure function modules
│   ├── claim.py                # M1: Atomic job claim
│   ├── compute.py              # M2: sentence-transformers
│   ├── store.py                # M3: Store vector
│   ├── index_faiss.py          # M4: FAISS indexing
│   └── update_status.py        # M5: Final status
├── bus/dispatcher.py           # Routes topics to pipelines
├── runtime/                    # PipelineRunner, ModuleRegistry
└── kernel/syscalls.py          # Capability-gated storage
```

**Why pipeline (not outbox driver)**:

- Pipelines attach to kernel via `PipelineProtocol.handle(msg)` - clean boundary
- All storage via syscalls - capability enforcement
- YAML contract - validates behavior
- Scales to 200+ pipelines without kernel bloat

### Decision 2: Same K0 Kernel Container (No New Container)

**Rationale**: P08 runs within the same K0 kernel process.

- sentence-transformers loaded into same Python process
- FAISS index is a local file accessed by same process
- Model preloading happens in kernel lifespan (`_preload_models`)
- No inter-process communication overhead

### Decision 3: No Batching for K0 Edge Devices

**Rationale**: K0 runs on edge devices (laptops, phones) with <100 events/sec throughput.

| Factor | Batching Needed? | Why |
|--------|------------------|-----|
| K0 on laptop | **No** | 100 evt/sec is ~6 texts/sec max |
| K0 on phone | **No** | Even lower throughput |
| Model loading | Yes (one-time) | Load model once at startup |
| Memory efficiency | Marginal | 384-dim vectors are tiny (1.5KB each) |

**Approach**: Process embeddings **one at a time** via topic subscription.

### Decision 4: Update st_hipp_events.embedding_status via Syscalls

P08 must update `st_hipp_events.embedding_status` from PENDING to READY via syscalls:

```python
await ctx.syscalls.hipp_event_update_embedding_status(
    embedding_id=embedding_id,
    embedding_status="READY"
)
```

**Schema columns in st_hipp_events** (migration 0024):

```sql
-- Embeddings and Knowledge Graph (4 columns)
embedding_id TEXT NOT NULL UNIQUE,
embedding_status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/IN_PROGRESS/READY/FAILED
entities_json TEXT,       -- NER entities (populated by P02)
kg_triples_json TEXT,     -- Knowledge graph triplets (populated by P02)
```

### Decision 5: Pure Function Modules (Refactor from Drivers)

Existing drivers refactored to pure function modules:

```
k0/modules/embedding/
├── claim.py             # M1: Atomic job claim
├── compute.py           # M2: Compute single embedding
├── store.py             # M3: Store vector to st_embedding_queue
├── index_faiss.py       # M4: Add to FAISS index
└── update_status.py     # M5: Final status update
```

Future Connector Pipeline can add batch variants:

```
k0/modules/embedding/
├── compute_batch.py     # Batch compute (for Connector)
└── faiss_batch.py       # Batch FAISS insert (for Connector)
```

---

## Existing Infrastructure

### 1. Storage Tables

**st_embedding_queue** (from migration 0024):

```sql
CREATE TABLE st_embedding_queue (
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  embedding_id TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  vector_kind TEXT NOT NULL,
  model_id TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'NORMAL',
  status TEXT NOT NULL,  -- PENDING/IN_PROGRESS/READY/INDEXED/FAILED_RETRYABLE/FAILED_PERMANENT
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_ts INTEGER,
  last_error TEXT,
  vector_json TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
```

**st_embeddings** (FAISS metadata):

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
```

**st_hipp_events.embedding_status** (from migration 0024):

```sql
-- Column in st_hipp_events that P08 must update via syscalls
embedding_status TEXT NOT NULL DEFAULT 'PENDING'
  CHECK(embedding_status IN ('PENDING', 'IN_PROGRESS', 'READY', 'FAILED'))
```

### 2. Existing Drivers (To Be Refactored to Modules)

**EmbeddingQueueDriver** (`k0/drivers/embedding_queue.py`):

- Contains embedding computation logic - refactor to `embedding.compute:v1`
- Contains status update logic - refactor to `embedding.update_status:v1`
- Uses sentence-transformers (`all-MiniLM-L6-v2`, 384-dim)

**FaissDriver** (`k0/drivers/faiss.py`):

- Contains FAISS indexing logic - refactor to `embedding.index_faiss:v1`
- Maintains `st_embeddings` metadata table
- IndexFlatL2 for exact search

### 3. Runtime Infrastructure (For Pipeline Execution)

**PipelineRunner** (`k0/runtime/`):

- Implements `PipelineProtocol` - clean kernel boundary
- Executes DAG of modules with topological sort
- Handles errors per `on_error` policy

**ModuleRegistry** (`k0/runtime/`):

- Discovers modules from `k0/modules/`
- Loads by name (e.g., `embedding.compute:v1`)
- Validates contracts

**BusDispatcher** (`k0/bus/`):

- Routes topics to pipeline handlers
- Entry point: `p02.embedding.enqueued.v1` -> P08

### 4. P02 Integration Point

P02's `builders.embedding_queue_write.v1` module must:

1. Write to `st_embedding_queue` via `syscalls.embedding_enqueue()` (exists)
2. **NEW**: Emit `p02.embedding.enqueued.v1` via `syscalls.bus_emit()` to trigger P08

---

## P08 Implementation Architecture (Correct)

### Architecture: YAML Pipeline with Topic Subscription

P08 is a **proper YAML pipeline** that subscribes to topics via BusDispatcher:

```
P02 Complete
     │
     ├──→ st_embedding_queue (status=PENDING)
     └──→ BusDispatcher.emit("p02.embedding.enqueued.v1")
              │
              ▼ (topic subscription, NOT polling)
┌─────────────────────────────────────────┐
│ P08 Pipeline Handler                    │
│                                         │
│ Stage 1: embedding.claim:v1             │
│   → syscalls.embedding_queue_claim()    │
│   → IN_PROGRESS                         │
│                                         │
│ Stage 2: embedding.compute:v1           │
│   → syscalls.hipp_event_read()          │
│   → model.encode(text)                  │
│   → 384-dim vector                      │
│                                         │
│ Stage 3: embedding.store:v1             │
│   → syscalls.embedding_store()          │
│   → READY                               │
│                                         │
│ Stage 4: embedding.index_faiss:v1       │
│   → syscalls.faiss_add()                │
│   → FAISS index + st_embeddings         │
│                                         │
│ Stage 5: embedding.update_status:v1     │
│   → syscalls.embedding_queue_update()   │
│   → syscalls.hipp_event_update()        │
│   → INDEXED                             │
└─────────────────────────────────────────┘
     │
     ▼
p08.embedding.complete.v1
     │
     ▼
P03 can now query FAISS for embeddings
```

### Why YAML Pipeline (Not Outbox Driver)

| Factor | YAML Pipeline | Outbox Driver |
|--------|---------------|---------------|
| Kernel boundary | ✅ Clean separation | ❌ Kernel invokes drivers |
| Capability enforcement | ✅ Via syscalls | ❌ Direct DB access |
| Contract validation | ✅ YAML spec | ❌ None |
| Scalability | ✅ 200+ pipelines | ❌ Kernel bloat |
| Observability | ✅ Stage-level tracing | ❌ Driver-level only |

**Decision**: Use YAML pipeline with topic subscription.

---

## Implementation Plan (Correct Architecture)

### Phase 1: Create P08 YAML Contract (Day 1)

**File**: `k0/contracts/pipelines/p08_embedding.v1.yaml`

```yaml
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
    on_error: emit_failed

  - stage: compute
    module: embedding.compute:v1
    depends_on: [claim]
    on_error: retry_with_backoff

  - stage: store
    module: embedding.store:v1
    depends_on: [compute]
    on_error: retry_with_backoff

  - stage: index_faiss
    module: embedding.index_faiss:v1
    depends_on: [store]
    on_error: retry_with_backoff

  - stage: update_status
    module: embedding.update_status:v1
    depends_on: [index_faiss]
    on_error: emit_failed
```

### Phase 2: Create Embedding Modules (Day 1-2)

**Location**: `k0/modules/embedding/`

```
k0/modules/embedding/
├── __init__.py
├── claim.py             # M1: Atomic job claim via syscall
├── compute.py           # M2: sentence-transformers embedding
├── store.py             # M3: Store vector to st_embedding_queue
├── index_faiss.py       # M4: Add to FAISS + st_embeddings
└── update_status.py     # M5: Final status + hippo sync
```

**Module Pattern** (pure functions with syscalls):

```python
# k0/modules/embedding/claim.py
async def claim(ctx: ModuleContext, input: ClaimInput) -> ClaimOutput:
    result = await ctx.syscalls.embedding_queue_claim(
        embedding_id=input.embedding_id,
        expected_status="PENDING"
    )
    if result["status"] == "ALREADY_CLAIMED":
        raise SkipEvent("Job already claimed")
    return ClaimOutput(...)
```

### Phase 3: Add New Syscalls (Day 2)

**File**: `k0/kernel/syscalls.py`

New syscalls required:

| Syscall | Capability | Purpose |
|---------|------------|--------|
| `embedding_queue_claim()` | st_embedding_queue.read/write | Atomic job claim |
| `hipp_event_read()` | st_hipp_events.read | Get text for embedding |
| `embedding_store()` | st_embedding_queue.write | Store computed vector |
| `faiss_add()` | faiss.write, st_embeddings.write | Add to FAISS index |
| `embedding_queue_update_status()` | st_embedding_queue.write | Final status |
| `hipp_event_update_embedding_status()` | st_hipp_events.write | Sync hippo |

### Phase 4: P02 Integration - Emit Topic (Day 2)

**File**: `k0/modules/builders/embedding_queue_write.py`

M14 must emit topic to trigger P08:

```python
async def run(message: Any, context: Any, **config: Any) -> dict:
    # 1. Insert job via existing syscall
    result = await context.syscalls.embedding_enqueue(...)

    # 2. NEW: Emit topic to trigger P08
    if result["inserted"]:
        await context.syscalls.bus_emit(
            topic="p02.embedding.enqueued.v1",
            payload={
                "embedding_id": embedding_id,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "vector_kind": vector_kind,
                "model_id": model_id,
                "priority": priority
            }
        )

    return {...}
```

### Phase 5: Model Preloading (Day 3)

**File**: `k0/kernel/app.py`

```python
async def _preload_models() -> dict[str, any]:
    models = {}
    # ... existing spaCy and VADER ...

    try:
        from sentence_transformers import SentenceTransformer
        logger.info("Preloading sentence-transformers model...")
        models["sentence_transformer"] = SentenceTransformer('all-MiniLM-L6-v2')
    except Exception as e:
        logger.warning(f"Failed to preload: {e}")
        models["sentence_transformer"] = None

    return models
```

### Phase 6: Testing (Day 3-4)

```
tests/
├── contracts/p08/
│   └── test_p08_embedding_contract.py   # Contract validation
└── integration/p08/
    └── test_p08_embedding_e2e.py        # End-to-end flow
```

---

## Event Flow (Correct Architecture)

```
P02 Write Complete
       │
       ├──→ st_hipp_events (embedding_status=PENDING)
       ├──→ st_embedding_queue (status=PENDING)
       └──→ bus_emit("p02.embedding.enqueued.v1")
              │
              ▼ (BusDispatcher routes to P08)
       P08 Pipeline Handler
              │
       ┌──────┴──────────────────────────────────┐
       │ Stage 1: embedding.claim:v1             │
       │   → syscalls.embedding_queue_claim()    │
       │   → st_embedding_queue.status=IN_PROGRESS│
       ├─────────────────────────────────────────┤
       │ Stage 2: embedding.compute:v1           │
       │   → syscalls.hipp_event_read()          │
       │   → model.encode(text) → 384-dim        │
       ├─────────────────────────────────────────┤
       │ Stage 3: embedding.store:v1             │
       │   → syscalls.embedding_store()          │
       │   → st_embedding_queue.status=READY     │
       ├─────────────────────────────────────────┤
       │ Stage 4: embedding.index_faiss:v1       │
       │   → syscalls.faiss_add()                │
       │   → FAISS index + st_embeddings         │
       ├─────────────────────────────────────────┤
       │ Stage 5: embedding.update_status:v1     │
       │   → syscalls.embedding_queue_update()   │
       │   → syscalls.hipp_event_update()        │
       │   → st_embedding_queue.status=INDEXED   │
       │   → st_hipp_events.embedding_status=READY│
       └─────────────────────────────────────────┘
              │
              ▼
       p08.embedding.complete.v1
              │
              ▼
       P03 can query FAISS
```

---

## Dependencies

### Required Packages (Already in K0)

```text
sentence-transformers>=2.2.0
torch>=2.0.0
faiss-cpu>=1.7.4
numpy>=1.24.0
```

### Environment Variables

```bash
K0_EMBEDDING_MODEL=all-MiniLM-L6-v2  # Default model
K0_FAISS_INDEX_PATH=./k0_faiss.index
K0_FAISS_DIMENSION=384
```

---

## Performance Targets (Edge Device - No Batching)

| Metric | Target | Notes |
|--------|--------|-------|
| Single embedding | <200ms (CPU) | Per-event processing |
| FAISS insert | <30ms/vector | IndexFlatL2 |
| Outbox poll | 5 seconds | Configurable |
| Throughput | ~5 vectors/sec (CPU) | Adequate for <100 evt/sec |
| Model load | ~2s (one-time) | At kernel startup |

---

## P03 Integration

Once P08 is running, P03 can:

1. **Query embeddings** via syscalls:

   ```python
   # Get embeddings for tenant/space
   result = await ctx.syscalls.embeddings_query(
       tenant_id=tenant_id,
       space_id=space_id
   )
   ```

2. **Semantic search** via syscalls:

   ```python
   # Search FAISS via syscall
   result = await ctx.syscalls.faiss_search(
       query_vector=query_vector,
       k=10,
       tenant_id=tenant_id,
       space_id=space_id
   )
   event_ids = result["event_ids"]
   ```

3. **Check embedding status** via syscalls:

   ```python
   # Check if embeddings are ready
   result = await ctx.syscalls.embedding_status_check(
       tenant_id=tenant_id,
       space_id=space_id
   )
   pending_count = result["pending_count"]
   ```

---

## Implementation Timeline (Correct Architecture)

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | P08 YAML contract | `k0/contracts/pipelines/p08_embedding.v1.yaml` |
| 1-2 | Create embedding modules | 5 modules in `k0/modules/embedding/` |
| 2 | Add new syscalls | 6 syscalls in `k0/kernel/syscalls.py` |
| 2 | P02 topic emission | M14 emits `p02.embedding.enqueued.v1` |
| 3 | Model preloading | Add sentence-transformers to kernel startup |
| 3-4 | Testing | Contract tests + integration tests |
| 4 | Documentation | Update dossier, ADRs |

**Total: ~4 days** to production-ready P08

---

## Future Enhancements (Out of Scope)

### Connector Pipeline Batching

For the **Connector Pipeline** (bulk imports with high throughput), add batch modules:

```text
k0/modules/embedding/
├── compute.py           # Single embedding (for P08) ✅
├── compute_batch.py     # Batch embeddings (for Connector)
└── faiss_batch.py       # Batch FAISS insert (for Connector)
```

### GPU Acceleration

Add CUDA support for faster inference:

```python
device = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer(model_name, device=device)
```

### Multi-Model Support

Allow different embedding models per `vector_kind`:

```yaml
embedding_models:
  memory.body.text: all-MiniLM-L6-v2
  memory.title: paraphrase-MiniLM-L6-v2
  memory.summary: all-mpnet-base-v2
```

---

## Next Steps

1. ✅ **Architecture decision made**: Use YAML pipeline (not outbox driver)
2. [ ] **Create P08 contract**: `k0/contracts/pipelines/p08_embedding.v1.yaml`
3. [ ] **Create modules**: 5 modules in `k0/modules/embedding/`
4. [ ] **Add syscalls**: 6 new syscalls in `k0/kernel/syscalls.py`
5. [ ] **P02 integration**: M14 emits `p02.embedding.enqueued.v1`
6. [ ] **Testing**: Contract tests + integration tests
7. [ ] **Documentation**: Update P08 dossier with final implementation

---

## Open Questions (Resolved)

| Question | Answer |
|----------|--------|
| New container? | **No** - same K0 kernel process |
| Hippo columns? | P08 updates `embedding_status` via syscalls |
| Batching for K0? | **No** - single-event processing |
| Connector decoupling? | **Yes** - create batch modules for future Connector pipeline |
| Driver vs Pipeline? | **YAML Pipeline** - maintains kernel boundary |

---

## References

- **P08 Dossier**: `docs/pipelines/P08_embedding_dossier.md`
- **Runtime README**: `k0/runtime/README.md` - PipelineRunner, ModuleRegistry
- **P02 Reference**: `k0/contracts/pipelines/p02_write.v1.yaml`
- **Existing Drivers**: `k0/drivers/embedding_queue.py`, `k0/drivers/faiss.py` (to refactor)
- **P02 Integration**: `k0/contracts/modules/builders.embedding_queue_write.v1.yaml`
- **Storage Schema**: `k0/contracts/sql/migrations/0024_p02_episodic_write_tables.sql`
