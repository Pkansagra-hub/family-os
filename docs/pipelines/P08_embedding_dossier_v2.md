# P08: Embedding Management & Enhancement Pipeline - Development Dossier

**Status**: ✅ Production - Kernel Lifespan Scheduler
**Last Updated**: 2025-12-13
**Architecture**: Kernel Background Task (Scheduled Batch Mode)
**ADR Reference**: [ADR-K003: Inline Embedding Generation via UltraBERT](../architecture/decisions-K0/k003-inline-embedding-ultrabert.md)

---

## Architecture Change Summary

### Before (v1): P08 as Primary Embedding Generator

```
P02 → st_hipp_events (embedding_status=PENDING)
    → st_embedding_queue (status=PENDING)
    → bus_emit("p02.embedding.enqueued.v1")
                    ↓
P08 → claim → compute (MiniLM) → store → index → update
    → embedding_status=READY
```

**Problem**: UltraBERT already computes 768-dim embeddings in its single forward pass during P02, but we discarded them and used a separate MiniLM model in P08.

### After (v2): P02 Inline + P08 for Management

```
P02 → M02/M04/M10 (UltraBERT single-pass, includes embedding)
    → M22 (extract embedding from cache - 0ms)
    → M16 (atomic 3-table write: st_hipp_events + st_vec + st_pipeline_processed)
    → st_hipp_events with embedding immediately available (status=READY)
                    ↓
P08 (KERNEL SCHEDULER) → FAISS indexing via background task
    → Polls st_vec for status=READY vectors (300s interval, catch-up on boot)
    → Adds to FAISS IndexIDMap, updates status=INDEXED
    → Manages embedding lifecycle (not generation)
```

---

## Key Decisions (Revised)

| Decision | v1 Choice | v2 Choice | Rationale |
|----------|-----------|-----------|-----------|
| Primary Embedding | P08 (async MiniLM) | P02 (inline UltraBERT) | UltraBERT already computes embedding in single pass |
| Embedding Dimension | 384 (MiniLM) | 768 (UltraBERT) | Higher quality, no extra cost |
| P08 Role | Primary generation | Kernel scheduler for FAISS | Generation moved to P02, indexing via lifespan task |
| FAISS Indexing | Synchronous in P08 | Kernel background task (300s interval) | Polls st_vec, catch-up on boot |
| Entry Topic | `p02.embedding.enqueued.v1` | N/A (polls st_vec directly) | No event subscription, scheduled batch mode |
| M23 Module | Separate vec writer | Merged into M16 | Atomic 3-table transaction |

---

## Purpose (Revised)

P08 is the **background embedding management pipeline** for:

1. **FAISS Index Management** — Add/remove vectors from search index
2. **Backfill Operations** — Process legacy records without embeddings
3. **Model Upgrade Recomputation** — Re-embed with new model versions
4. **Embedding Cleanup** — Remove orphaned vectors on event deletion
5. **Multi-Model Support** — Generate additional embeddings (multilingual, domain-specific)

> P08 = "Embedding lifecycle management: indexing, backfill, upgrades, cleanup"

**P08 is NOT responsible for primary embedding generation** — that happens inline in P02.

---

## New Data Flow

### P02 Write Path (Revised - ~171ms P95)

```
cognitive.memory.write.committed.v1
                ↓
┌─────────────────────────────────────────────────────────┐
│ P02 Write Pipeline                                       │
├─────────────────────────────────────────────────────────┤
│ Stage 10: DG pattern_separate                            │
│ Stage 20: CA1 semantic_project → UltraBERT (warms cache) │
│ Stage 22: embedding.extract_from_cache (NEW, ~0ms)       │
│   → Reads embedding from UltraBERT single-pass cache     │
│   → 768-dim vector extracted                             │
│ Stage 30-43: Enrichment (affect, social, temporal, etc.) │
│ Stage 55: salience.score                                 │
│ Stage 60: hipp_events_row builder                        │
│ Stage 61: embedding_write (NEW, replaces queue_write)    │
│   → Writes to st_vec immediately                         │
│   → embedding_status = READY                             │
│ Stage 70: atomic commit                                  │
├─────────────────────────────────────────────────────────┤
│ OUTPUT: st_hipp_events with embedding_status=READY       │
│         st_vec with 768-dim UltraBERT embedding          │
│ EMIT: p02.embedding.stored.v1 (for P08 indexing)         │
└─────────────────────────────────────────────────────────┘
```

### P08 Management Path (Revised - Async)

```
p02.embedding.stored.v1 (or scheduled triggers)
                ↓
┌─────────────────────────────────────────────────────────┐
│ P08 Embedding Management Pipeline                        │
├─────────────────────────────────────────────────────────┤
│ Use Case 1: FAISS Indexing (index_faiss flow)            │
│   → Read embedding from st_vec                           │
│   → Add to FAISS index                                   │
│   → Update st_embeddings metadata                        │
│                                                          │
│ Use Case 2: Backfill (backfill flow)                     │
│   → Query st_hipp_events WHERE embedding_status=PENDING  │
│   → Compute embedding via UltraBERT                      │
│   → Write to st_vec                                      │
│   → Update embedding_status=READY                        │
│                                                          │
│ Use Case 3: Model Upgrade (recompute flow)               │
│   → Query events with old model_id                       │
│   → Recompute with new model                             │
│   → Replace in st_vec                                    │
│   → Re-index in FAISS                                    │
│                                                          │
│ Use Case 4: Cleanup (cleanup flow)                       │
│   → Query orphaned embeddings                            │
│   → Remove from st_vec and FAISS                         │
└─────────────────────────────────────────────────────────┘
```

---

## Pipeline Contract (Revised)

```yaml
# k0/contracts/pipelines/p08_embedding_management.v1.yaml

pipeline_id: P08_EMBEDDING_MANAGEMENT
version: v2
name: P08 Embedding Management & Enhancement
description: |
  Background embedding lifecycle management pipeline.
  Primary embedding generation moved to P02 inline (ADR-K003).

  Responsibilities:
  - FAISS index management (add/remove vectors)
  - Backfill legacy records without embeddings
  - Model upgrade recomputation
  - Orphaned embedding cleanup
  - Multi-model embedding generation (future)

  NOT responsible for primary embedding generation (handled by P02).

# Multiple entry points for different use cases
entry_topics:
  - p02.embedding.stored.v1        # FAISS indexing after P02 stores embedding
  - p08.backfill.requested.v1      # Backfill trigger (scheduled or manual)
  - p08.recompute.requested.v1     # Model upgrade trigger
  - p08.cleanup.requested.v1       # Cleanup trigger

exit_topics:
  - p08.faiss.indexed.v1           # FAISS indexing complete
  - p08.backfill.complete.v1       # Backfill batch complete
  - p08.recompute.complete.v1      # Recomputation complete
  - p08.cleanup.complete.v1        # Cleanup complete
  - p08.operation.failed.v1        # Any operation failed

concurrency: 1
max_queue_depth: 256

required_capabilities:
  - st_vec.read
  - st_vec.write
  - st_hipp_events.read
  - st_hipp_events.write
  - st_embeddings.read
  - st_embeddings.write
  - faiss.read
  - faiss.write
```

---

## Use Case 1: FAISS Indexing

**Trigger**: `p02.embedding.stored.v1` (after P02 stores embedding to st_vec)

**Purpose**: Add newly stored embedding to FAISS search index.

### DAG: faiss_indexing

```yaml
dag:
  - id: stage_10_read_embedding
    module: embedding.read_from_vec:v1
    after: []
    description: Read embedding from st_vec

  - id: stage_20_index_faiss
    module: embedding.faiss_add:v1
    after: [stage_10_read_embedding]
    description: Add vector to FAISS index

  - id: stage_30_update_metadata
    module: embedding.update_index_metadata:v1
    after: [stage_20_index_faiss]
    description: Update st_embeddings with FAISS vector_id
```

### Module: embedding.read_from_vec:v1

```python
async def execute(envelope: dict, context: ModuleContext) -> dict:
    """Read embedding from st_vec table."""
    embedding_id = envelope["payload"]["embedding_id"]

    result = await context.syscalls.vec_read(embedding_id=embedding_id)

    return {
        "embedding_id": embedding_id,
        "event_id": result["event_id"],
        "tenant_id": result["tenant_id"],
        "space_id": result["space_id"],
        "vector": result["vector"],
        "vector_dim": result["vector_dim"],
        "model_id": result["model_id"],
    }
```

### Module: embedding.faiss_add:v1

```python
async def execute(enriched: dict, context: ModuleContext) -> dict:
    """Add vector to FAISS index."""
    vec_data = enriched["read_from_vec"]

    result = await context.syscalls.faiss_add(
        embedding_id=vec_data["embedding_id"],
        event_id=vec_data["event_id"],
        tenant_id=vec_data["tenant_id"],
        space_id=vec_data["space_id"],
        vector=vec_data["vector"],
    )

    return {
        "embedding_id": vec_data["embedding_id"],
        "vector_id": result["vector_id"],
        "indexed": True,
    }
```

---

## Use Case 2: Backfill Operations

**Trigger**: `p08.backfill.requested.v1` (scheduled job or manual trigger)

**Purpose**: Process legacy records that don't have embeddings.

### Entry Event Schema

```json
{
  "topic": "p08.backfill.requested.v1",
  "payload": {
    "tenant_id": "family-smith",
    "space_id": "personal:dad",
    "batch_size": 100,
    "created_before": "2025-12-01T00:00:00Z",
    "model_id": "ultrabert_v2.1.0"
  }
}
```

### DAG: backfill

```yaml
dag:
  - id: stage_10_query_pending
    module: embedding.query_pending:v1
    after: []
    description: Find events with embedding_status=PENDING

  - id: stage_20_compute_batch
    module: embedding.compute_batch:v1
    after: [stage_10_query_pending]
    description: Compute embeddings for batch using UltraBERT

  - id: stage_30_store_batch
    module: embedding.store_batch:v1
    after: [stage_20_compute_batch]
    description: Write embeddings to st_vec

  - id: stage_40_index_batch
    module: embedding.faiss_add_batch:v1
    after: [stage_30_store_batch]
    description: Add batch to FAISS index

  - id: stage_50_update_status_batch
    module: embedding.update_status_batch:v1
    after: [stage_40_index_batch]
    description: Update embedding_status to READY for batch
```

### Module: embedding.query_pending:v1

```python
async def execute(envelope: dict, context: ModuleContext) -> dict:
    """Query events needing embeddings."""
    payload = envelope["payload"]

    result = await context.syscalls.hipp_events_query(
        tenant_id=payload["tenant_id"],
        space_id=payload.get("space_id"),
        embedding_status="PENDING",
        limit=payload.get("batch_size", 100),
        created_before=payload.get("created_before"),
    )

    return {
        "events": result["events"],
        "count": len(result["events"]),
        "model_id": payload.get("model_id", "ultrabert_v2.1.0"),
    }
```

### Module: embedding.compute_batch:v1

```python
async def execute(enriched: dict, context: ModuleContext) -> dict:
    """Compute embeddings for batch using UltraBERT."""
    from k0.runtime.ultrabert_adapter import get_embedding

    events = enriched["query_pending"]["events"]
    model_id = enriched["query_pending"]["model_id"]

    embeddings = []
    for event in events:
        text = event.get("text", "")
        if not text:
            continue

        vector = get_embedding(text)
        if vector:
            embeddings.append({
                "event_id": event["event_id"],
                "embedding_id": event["embedding_id"],
                "tenant_id": event["tenant_id"],
                "space_id": event["space_id"],
                "vector": vector,
                "vector_dim": 768,
                "model_id": model_id,
            })

    return {
        "embeddings": embeddings,
        "computed_count": len(embeddings),
        "skipped_count": len(events) - len(embeddings),
    }
```

---

## Use Case 3: Model Upgrade Recomputation

**Trigger**: `p08.recompute.requested.v1` (after model upgrade)

**Purpose**: Recompute embeddings when upgrading to a new model version.

### Entry Event Schema

```json
{
  "topic": "p08.recompute.requested.v1",
  "payload": {
    "tenant_id": "family-smith",
    "old_model_id": "ultrabert_v2.0.0",
    "new_model_id": "ultrabert_v2.1.0",
    "batch_size": 50
  }
}
```

### DAG: recompute

```yaml
dag:
  - id: stage_10_query_old_model
    module: embedding.query_by_model:v1
    after: []
    description: Find embeddings with old model_id

  - id: stage_20_recompute
    module: embedding.compute_batch:v1
    after: [stage_10_query_old_model]
    description: Recompute with new model

  - id: stage_30_replace
    module: embedding.replace_batch:v1
    after: [stage_20_recompute]
    description: Replace old embeddings in st_vec

  - id: stage_40_reindex
    module: embedding.faiss_replace_batch:v1
    after: [stage_30_replace]
    description: Update FAISS index with new vectors
```

---

## Use Case 4: Embedding Cleanup

**Trigger**: `p08.cleanup.requested.v1` (scheduled or after event deletion)

**Purpose**: Remove orphaned embeddings when events are deleted.

### Entry Event Schema

```json
{
  "topic": "p08.cleanup.requested.v1",
  "payload": {
    "tenant_id": "family-smith",
    "space_id": "personal:dad",
    "event_ids": ["evt_abc123", "evt_def456"]
  }
}
```

### DAG: cleanup

```yaml
dag:
  - id: stage_10_find_orphans
    module: embedding.find_orphans:v1
    after: []
    description: Find embeddings without corresponding events

  - id: stage_20_remove_from_faiss
    module: embedding.faiss_remove_batch:v1
    after: [stage_10_find_orphans]
    description: Remove vectors from FAISS index

  - id: stage_30_delete_embeddings
    module: embedding.delete_batch:v1
    after: [stage_20_remove_from_faiss]
    description: Delete from st_vec and st_embeddings
```

---

## Storage Schema (Updated)

### Table: st_vec (NEW - replaces embedding in st_embedding_queue)

**Purpose**: Primary embedding storage. Written by P02 inline, read by P08 for indexing.

```sql
CREATE TABLE st_vec (
  embedding_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  vector BLOB NOT NULL,              -- 768 floats packed
  vector_dim INTEGER NOT NULL DEFAULT 768,
  model_id TEXT NOT NULL DEFAULT 'ultrabert_v2.1.0',
  vector_norm REAL,                  -- For cosine similarity
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);

CREATE INDEX idx_vec_tenant_space ON st_vec(tenant_id, space_id);
CREATE INDEX idx_vec_model ON st_vec(model_id);
CREATE INDEX idx_vec_event ON st_vec(event_id);
```

### Table: st_embeddings (FAISS Metadata - Unchanged)

```sql
CREATE TABLE st_embeddings (
  vector_id INTEGER PRIMARY KEY,     -- FAISS index position
  embedding_id TEXT NOT NULL UNIQUE,
  event_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  vector_norm REAL NOT NULL,
  indexed_at INTEGER NOT NULL,

  FOREIGN KEY (embedding_id) REFERENCES st_vec(embedding_id)
);

CREATE INDEX idx_emb_tenant_space ON st_embeddings(tenant_id, space_id);
```

### Column: st_hipp_events.embedding_status (Updated Values)

| Status | Set By | Meaning |
|--------|--------|--------|
| PENDING | Legacy (before ADR-K003) | Needs backfill |
| READY | P02 M16 (atomic inline) | Embedding stored in st_vec |
| INDEXED | P08 Kernel Scheduler | Also in FAISS search index (faiss_id set) |
| FAILED | P02 or P08 | Generation/indexing failed |

---

## Entry Topics Summary

| Topic | Trigger | Use Case | Priority |
|-------|---------|----------|----------|
| N/A (st_vec polling) | Kernel scheduler (300s interval) | FAISS indexing | HIGH |
| `p08.backfill.requested.v1` | Scheduled/manual | Legacy backfill | MEDIUM |
| `p08.recompute.requested.v1` | Model upgrade | Recomputation | LOW |
| `p08.cleanup.requested.v1` | Event deletion | Cleanup | LOW |

**Note**: P08 v2.1 uses kernel lifespan scheduler that polls st_vec for READY vectors, not event-driven.

---

## Syscalls Required (Revised)

### New Syscalls for P08 v2

| Syscall | Capability | Purpose |
|---------|------------|---------|
| `vec_read()` | st_vec.read | Read embedding from st_vec |
| `vec_write_batch()` | st_vec.write | Write batch to st_vec |
| `vec_delete_batch()` | st_vec.write | Delete batch from st_vec |
| `faiss_add()` | faiss.write | Add single vector to FAISS |
| `faiss_add_batch()` | faiss.write | Add batch to FAISS |
| `faiss_remove_batch()` | faiss.write | Remove batch from FAISS |
| `embeddings_query_by_model()` | st_embeddings.read | Query by model_id |
| `hipp_events_query()` | st_hipp_events.read | Query events by criteria |

### Removed Syscalls (Moved to P02)

| Syscall | Moved To | Notes |
|---------|----------|-------|
| `embedding_queue_claim()` | Deprecated | No queue needed |
| `embedding_compute()` | P02 M22 | UltraBERT cache extraction |
| `embedding_store()` | P02 M16 | Merged into atomic 3-table transaction |

---

## Performance Targets (Revised)

| Metric | Target | Notes |
|--------|--------|-------|
| FAISS indexing (single) | <30ms P95 | After P02 emits stored event |
| FAISS indexing (batch 100) | <500ms P95 | Backfill batch |
| Backfill throughput | ~10 events/sec | CPU-bound UltraBERT |
| Cleanup batch | <100ms P95 | Metadata-only operations |
| st_vec storage | ~3KB/vector | 768 x float32 = 3072 bytes |

---

## Environment Variables (Updated)

| Variable | Default | Description |
|----------|---------|-------------|
| `K0_FAISS_INDEX_PATH` | `./k0_faiss.index` | FAISS index file |
| `K0_FAISS_DIMENSION` | `768` | Vector dimension (was 384) |
| `K0_P08_BACKFILL_BATCH_SIZE` | `100` | Backfill batch size |
| `K0_P08_INDEXING_ENABLED` | `1` | Enable FAISS indexing |

---

## Migration from v1 to v2

### Phase 1: Deploy P02 Inline Embedding ✅ COMPLETE

1. ✅ Add M22 `embedding.extract_from_cache:v1` to P02
2. ✅ Merge M23 functionality into M16 (atomic 3-table transaction)
3. ✅ Update P02 DAG to include M22, M16 writes st_vec atomically
4. ✅ P02 now writes to st_vec with embedding_status=READY

### Phase 2: Update P08 for Kernel Scheduler ✅ COMPLETE

1. ✅ P08 v2.1 runs as kernel lifespan background task
2. ✅ Polls st_vec for READY vectors (300s interval, catch-up on boot)
3. ✅ Uses FaissIndexManager singleton with IndexIDMap wrapper
4. ✅ Updates status to INDEXED, sets faiss_id column

### Phase 3: Backfill Legacy Data (Future)

1. Trigger `p08.backfill.requested.v1` for legacy records
2. P08 processes PENDING embeddings
3. Updates st_vec and FAISS index

### Phase 4: Update FAISS Index Dimension ✅ COMPLETE

1. ✅ FAISS index uses 768-dim vectors (IndexFlatL2 wrapped in IndexIDMap)
2. ✅ FaissIndexManager handles ID mapping automatically
3. ✅ `K0_FAISS_DIMENSION=768` is default

---

## File Structure (Updated)

```
k0/
  contracts/
    pipelines/
      p08_embedding_management.v1.yaml   # Revised pipeline spec
    modules/
      embedding.read_from_vec.v1.yaml
      embedding.faiss_add.v1.yaml
      embedding.faiss_add_batch.v1.yaml
      embedding.faiss_remove_batch.v1.yaml
      embedding.query_pending.v1.yaml
      embedding.compute_batch.v1.yaml
      embedding.store_batch.v1.yaml
      embedding.update_status_batch.v1.yaml
      embedding.find_orphans.v1.yaml
      embedding.delete_batch.v1.yaml
  modules/
    embedding/
      __init__.py
      read_from_vec.py           # Read from st_vec
      faiss_add.py               # Single FAISS add
      faiss_add_batch.py         # Batch FAISS add
      faiss_remove_batch.py      # Batch FAISS remove
      query_pending.py           # Query PENDING embeddings
      compute_batch.py           # Batch compute (backfill)
      store_batch.py             # Batch store
      update_status_batch.py     # Batch status update
      find_orphans.py            # Find orphaned embeddings
      delete_batch.py            # Batch delete

tests/
  contracts/
    p08/
      test_p08_management_contract.py
  integration/
    p08/
      test_p08_faiss_indexing.py
      test_p08_backfill.py
      test_p08_cleanup.py
```

---

## ADR Reference

**ADR-K003**: Inline Embedding Generation via UltraBERT Single-Pass Cache

- **Status**: PROPOSED
- **Decision**: Move primary embedding generation to P02 inline
- **P08 Role**: Repurposed for embedding lifecycle management
- **Impact**: P08 no longer responsible for primary embedding computation

---

## References

- **ADR-K003**: `docs/architecture/decisions-K0/pipelines/k003-inline-embedding-ultrabert.md`
- **UltraBERT Adapter**: `k0/runtime/ultrabert_adapter.py`
- **P02 Pipeline**: `k0/contracts/pipelines/p02_write.v1.yaml`
- **Original P08 Dossier**: `docs/pipelines/P08_embedding_dossier.md` (deprecated)
