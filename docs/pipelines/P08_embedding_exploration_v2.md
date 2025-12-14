# P08 Embedding Management - Architecture Exploration (Revised)

**Status**: ✅ Production - Kernel Lifespan Scheduler
**Created**: 2025-11-25
**Updated**: 2025-12-13
**Purpose**: Define P08's new role as embedding management pipeline (not primary generator)
**Architecture**: Kernel Background Task (Scheduled Batch Mode)
**ADR Reference**: [ADR-K003: Inline Embedding Generation via UltraBERT](../architecture/decisions-K0/pipelines/k003-inline-embedding-ultrabert.md)

---

## Executive Summary (Revised)

### Key Insight: UltraBERT Provides Embeddings "For Free"

UltraBERT v2.1.0 computes **12 capabilities in ONE forward pass** (~30ms), including a **768-dim embedding**:

| Capability | Used By | Notes |
|------------|---------|-------|
| sentiment | M04 affect.analyze | |
| emotions | M04 affect.analyze | |
| safety_familyos | M04 affect.analyze | |
| ner_family | M02 semantic_project | |
| ner_general | M02 semantic_project | |
| temporal | M02 semantic_project | |
| intent | M10 ingress_classify | |
| ingress | M10 ingress_classify | |
| **embedding** | **NEW M22** | **768-dim, previously discarded!** |
| ... | | |

With `K0_ULTRABERT_SINGLE_PASS=1`, all P02 modules share ONE cached forward pass via `_get_full_analysis_result()`. The embedding is computed but was being **discarded**.

### Architecture Change

**OLD (P08 as Primary Generator)**:

```
P02 → queues job → P08 → MiniLM compute (384-dim) → store → index
      ASYNC DELAY: seconds before embedding available
```

**NEW (P02 Inline + P08 Kernel Scheduler)**:

```
P02 → M22 extract from cache (0ms) → M16 atomic 3-table write → READY immediately
      P08 Kernel Scheduler → polls st_vec → adds to FAISS → INDEXED
      NO DELAY: embedding available at P02 commit
```

### Why This Matters for P03

P03 consolidation needs embeddings for CA1 semantic bridge similarity:

| Scenario | OLD Architecture | NEW Architecture |
|----------|------------------|------------------|
| Embedding available? | Maybe (async P08) | Always (P02 inline) |
| Fallback needed? | Jaccard text similarity | No fallback needed |
| Latency impact | Consolidation waits or degrades | Immediate access |

---

## P08 New Role: Embedding Lifecycle Management

### What P08 Does Now

| Responsibility | Description | Trigger |
|---------------|-------------|---------|
| **FAISS Indexing** | Add embeddings to search index | Kernel scheduler polls st_vec (300s interval, catch-up on boot) |
| **Backfill** | Process legacy records without embeddings | Scheduled/manual |
| **Model Upgrades** | Recompute when model version changes | Manual trigger |
| **Cleanup** | Remove orphaned embeddings | Event deletion |
| **Multi-Model** | Generate alternative embeddings (future) | On-demand |

### What P08 No Longer Does

| Removed Responsibility | Moved To | Reason |
|----------------------|----------|--------|
| Primary embedding generation | P02 M22 | UltraBERT cache extraction |
| Queue claiming | N/A | No queue needed |
| MiniLM inference | Removed | UltraBERT is primary model |

---

## Kernel Boundary Compliance (Unchanged)

P08 remains a **proper YAML pipeline** to maintain kernel boundary integrity:

```
LAYER 1-5: KERNEL CORE (Authoritative)
  Ports, Gate, Policy, UoW, Storage, QoS

LAYER 6: EVENT BUS - THE BOUNDARY
  BusDispatcher
  Pipelines ATTACH here via PipelineProtocol  ← P08 attaches here

LAYER 7-8: EXTERNAL
  Query Drivers, Driver SPI
```

**Pipeline benefits**:

- Clean separation via `PipelineProtocol.handle(msg)`
- Capability enforcement via `context.syscalls.*`
- Contract validation via YAML spec
- Scalable architecture (kernel stays lean)

---

## P02 Changes for Inline Embedding

### New Modules in P02

#### M22: embedding.extract_from_cache:v1

**Purpose**: Extract embedding from UltraBERT's single-pass cache.

**Location**: `k0/modules/embedding/extract_from_cache.py`

**Performance**: ~0ms (cache read only, no inference)

```python
"""
M22: embedding.extract_from_cache

Extracts the 768-dim embedding from UltraBERT's single-pass cache.
The embedding was already computed when M02/M04/M10 called UltraBERT.

Performance: <1ms P95 (cache read only)
"""

from k0.runtime.ultrabert_adapter import _get_full_analysis_result, get_embedding

async def execute(envelope: dict, enriched: dict, context: ModuleContext) -> dict:
    """Extract embedding from UltraBERT cache."""
    text = envelope.get("body", {}).get("text", "")

    if not text:
        return {"embedding": None, "source": "no_text"}

    # Try cached result first (should be warm from M02/M04)
    result = _get_full_analysis_result(text)
    if result and hasattr(result, 'embedding') and result.embedding:
        return {
            "embedding": result.embedding,
            "embedding_id": enriched.get("semantic_project", {}).get("embedding_id"),
            "vector_dim": 768,
            "model_id": "ultrabert_v2.1.0",
            "source": "cache_hit",
        }

    # Fallback: direct embedding call (rare, cache miss)
    embedding = get_embedding(text)
    return {
        "embedding": embedding,
        "embedding_id": enriched.get("semantic_project", {}).get("embedding_id"),
        "vector_dim": 768,
        "model_id": "ultrabert_v2.1.0",
        "source": "direct_call" if embedding else "failed",
    }
```

#### M23: builders.embedding_write:v1 ❌ DEPRECATED

**Purpose**: ~~Write embedding directly to st_vec table.~~ **MERGED INTO M16**

**Location**: `k0/modules/builders/embedding_write.py` (deprecated)

**Status**: ❌ Deprecated - Functionality merged into M16 (core.hipp_events_writer:v1.2) for atomic 3-table transaction.

**Migration**: M16 now writes st_hipp_events + st_vec + st_pipeline_processed in single atomic transaction.

### Updated P02 DAG

```yaml
# k0/contracts/pipelines/p02_write.v1.yaml (revised)

dag:
  # Stage 10: DG Pattern Separation (unchanged)
  - id: stage_10_dg_pattern_separate
    module: hippocampus.pattern_separate:v1
    after: []

  # Stage 20: CA1 Semantic Projection (calls UltraBERT, warms cache)
  - id: stage_20_ca1_semantic_project
    module: hippocampus.semantic_project:v1
    after: [stage_10_dg_pattern_separate]

  # NEW Stage 22: Extract embedding from UltraBERT cache
  - id: stage_22_embedding_extract
    module: embedding.extract_from_cache:v1
    after: [stage_20_ca1_semantic_project]
    description: Extracts 768-dim embedding from UltraBERT single-pass cache (~0ms)

  # Stages 30-43: Enrichment modules (unchanged, parallel)
  - id: stage_30_affect_analyze
    module: affect.analyze:v1
    after: [stage_20_ca1_semantic_project]

  # ... other enrichment stages ...

  # Stage 55: Salience scoring (unchanged)
  - id: stage_55_salience_score
    module: salience.score:v1
    after: [stage_30_affect_analyze, stage_32_social_resolve, stage_33_temporal_profile]

  # Stage 60: Row builder (add stage_22 to dependencies)
  - id: stage_60_build_hipp_events_row
    module: builders.hipp_events_row:v1
    after:
      - stage_10_dg_pattern_separate
      - stage_20_ca1_semantic_project
      - stage_22_embedding_extract   # NEW dependency
      - stage_30_affect_analyze
      # ... other dependencies ...
    config:
      embedding_status: READY  # No longer PENDING

  # REPLACED: stage_61 now writes embedding directly
  - id: stage_61_embedding_write
    module: builders.embedding_write:v1
    after: [stage_22_embedding_extract]
    description: Writes embedding directly to st_vec table

  # Stage 70: Atomic commit (unchanged)
  - id: stage_70_atomic_writer
    module: core.hipp_events_writer:v1
    after: [stage_60_build_hipp_events_row, stage_61_embedding_write]
```

---

## P08 Pipeline Contract (Revised)

### Multi-Entry Pipeline

P08 now handles multiple entry points for different lifecycle operations:

```yaml
# k0/contracts/pipelines/p08_embedding_management.v1.yaml

pipeline_id: P08_EMBEDDING_MANAGEMENT
version: v2
name: P08 Embedding Management & Enhancement
description: |
  Background embedding lifecycle management.
  Primary generation is now inline in P02 (ADR-K003).

entry_topics:
  - p02.embedding.stored.v1
  - p08.backfill.requested.v1
  - p08.recompute.requested.v1
  - p08.cleanup.requested.v1

exit_topics:
  - p08.faiss.indexed.v1
  - p08.backfill.complete.v1
  - p08.recompute.complete.v1
  - p08.cleanup.complete.v1
  - p08.operation.failed.v1

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

## Use Cases Detailed

### Use Case 1: FAISS Indexing (Primary P08 Flow)

**Trigger**: P02 emits `p02.embedding.stored.v1` after M23 writes to st_vec

**Flow**:

```
p02.embedding.stored.v1
        ↓
+------------------+
| read_from_vec    | Read embedding from st_vec
+------------------+
        ↓
+------------------+
| faiss_add        | Add to FAISS index
+------------------+
        ↓
+------------------+
| update_metadata  | Update st_embeddings
+------------------+
        ↓
p08.faiss.indexed.v1
```

**Latency**: <50ms P95 (async, non-blocking for user)

### Use Case 2: Backfill Legacy Records

**Trigger**: Scheduled job or manual `p08.backfill.requested.v1`

**Purpose**: Process records created before ADR-K003 that have `embedding_status=PENDING`

**Flow**:

```
p08.backfill.requested.v1
        ↓
+------------------+
| query_pending    | Find events with embedding_status=PENDING
+------------------+
        ↓
+------------------+
| compute_batch    | Compute via UltraBERT (not cache)
+------------------+
        ↓
+------------------+
| store_batch      | Write to st_vec
+------------------+
        ↓
+------------------+
| faiss_add_batch  | Index batch in FAISS
+------------------+
        ↓
+------------------+
| update_status    | Set embedding_status=READY
+------------------+
        ↓
p08.backfill.complete.v1
```

### Use Case 3: Model Upgrade

**Trigger**: Manual `p08.recompute.requested.v1` after deploying new model

**Purpose**: Recompute embeddings when upgrading from ultrabert_v2.0.0 to v2.1.0

### Use Case 4: Cleanup

**Trigger**: Event deletion triggers `p08.cleanup.requested.v1`

**Purpose**: Remove orphaned embeddings and FAISS vectors

---

## Event Flow Diagram (Revised)

```
+-----------------------------------------------------------+
|                    P02 WRITE PIPELINE                      |
+-----------------------------------------------------------+
|                                                           |
| Stage 20: semantic_project → UltraBERT (warms cache)      |
|                                                           |
| Stage 22: embedding.extract_from_cache                    |
|   → Reads embedding from UltraBERT cache (~0ms)           |
|   → 768-dim vector extracted                              |
|                                                           |
| Stage 30-43: Enrichment (parallel)                        |
|                                                           |
| Stage 61: embedding_write                                 |
|   → Writes to st_vec (embedding_status=READY)             |
|   → Emits p02.embedding.stored.v1                         |
|                                                           |
| Stage 70: atomic commit                                   |
+-----------------------------------------------------------+
                          |
                          v
+-----------------------------------------------------------+
|        p02.embedding.stored.v1 EMITTED                     |
|        Embedding immediately available for queries         |
+-----------------------------------------------------------+
                          |
                          v (async, non-blocking)
+-----------------------------------------------------------+
|                    P08 MANAGEMENT                          |
+-----------------------------------------------------------+
|                                                           |
| Flow: FAISS Indexing                                      |
|   → Read from st_vec                                      |
|   → Add to FAISS index                                    |
|   → Update st_embeddings metadata                         |
|   → Emit p08.faiss.indexed.v1                             |
|                                                           |
+-----------------------------------------------------------+
```

---

## Storage Changes

### New Table: st_vec

Replaces embedding storage in st_embedding_queue:

```sql
CREATE TABLE st_vec (
  embedding_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  vector BLOB NOT NULL,              -- 768 floats packed
  vector_dim INTEGER NOT NULL DEFAULT 768,
  model_id TEXT NOT NULL DEFAULT 'ultrabert_v2.1.0',
  vector_norm REAL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
```

### Updated: st_hipp_events.embedding_status

| Status | Set By | Meaning |
|--------|--------|--------|
| PENDING | Legacy/fallback | Needs backfill (rare after ADR-K003) |
| READY | P02 M16 (atomic) | Embedding stored in st_vec |
| INDEXED | P08 Kernel Scheduler | Also in FAISS search index (faiss_id set) |
| FAILED | P02/P08 | Generation/indexing failed |

### Deprecated: st_embedding_queue

The job queue is no longer needed for primary flow. May be kept for backfill coordination.

---

## Performance Comparison

| Metric | OLD (P08 Primary) | NEW (P02 Inline) | Improvement |
|--------|-------------------|------------------|-------------|
| Embedding model | MiniLM (384-dim) | UltraBERT (768-dim) | Higher quality |
| Additional model load | ~250MB | 0MB | -250MB |
| P02 latency impact | 0ms | ~0ms (cache read) | Same |
| Embedding availability | Async (seconds) | Immediate | Instant |
| P03 can use embedding? | Maybe | Always | 100% |
| FAISS search quality | 384-dim | 768-dim | Better |

---

## Implementation Timeline

### Phase 1: P02 Inline ✅ COMPLETE

| Task | Deliverable | Status |
|------|-------------|--------|
| Create M22 | `k0/modules/embedding/extract_from_cache.py` | ✅ |
| Merge M23 into M16 | `k0/modules/core/hipp_events_writer.py` | ✅ |
| Update P02 DAG | `k0/contracts/pipelines/p02_write.v1.yaml` | ✅ |
| Create st_vec table | Migration | ✅ |
| Unit tests | `tests/k0/modules/test_embedding_*.py` | ✅ |

### Phase 2: P08 Kernel Scheduler ✅ COMPLETE

| Task | Deliverable | Status |
|------|-------------|--------|
| Kernel lifespan task | `k0/kernel/app.py:_p08_faiss_indexer_loop()` | ✅ |
| FaissIndexManager | `k0/runtime/faiss_manager.py` (IndexIDMap wrapper) | ✅ |
| Catch-up on boot | Polls READY vectors immediately on startup | ✅ |
| 300s interval loop | Scheduled batch indexing | ✅ |

### Phase 3: Migration ✅ COMPLETE

| Task | Deliverable | Status |
|------|-------------|--------|
| FAISS 768-dim | IndexFlatL2 wrapped in IndexIDMap | ✅ |
| Status transitions | READY → INDEXED with faiss_id | ✅ |
| Update env vars | `K0_FAISS_DIMENSION=768` default | ✅ |

---

## Open Questions (Resolved)

| Question | Answer |
|----------|--------|
| Should P08 still exist? | **Yes** - runs as kernel lifespan scheduler |
| What triggers FAISS indexing? | Kernel scheduler polls st_vec for READY vectors (300s interval, catch-up on boot) |
| What about legacy records? | P08 backfill flow handles them (future) |
| FAISS dimension change? | ✅ Done - 768-dim with IndexIDMap wrapper |
| Is MiniLM still needed? | **No** - UltraBERT is primary model |
| Why merge M23 into M16? | Atomic 3-table transaction (st_hipp_events + st_vec + st_pipeline_processed) |

---

## References

- **ADR-K003**: `docs/architecture/decisions-K0/pipelines/k003-inline-embedding-ultrabert.md`
- **UltraBERT Adapter**: `k0/runtime/ultrabert_adapter.py`
- **FaissIndexManager**: `k0/runtime/faiss_manager.py`
- **Kernel Scheduler**: `k0/kernel/app.py:_p08_faiss_indexer_loop()`
- **P02 Pipeline**: `k0/contracts/pipelines/p02_write.v1.yaml`
- **P08 Dossier v2**: `docs/pipelines/P08_embedding_dossier_v2.md`
- **P03 Dossier**: `docs/pipelines/P03_consolidation_dossier.md`
