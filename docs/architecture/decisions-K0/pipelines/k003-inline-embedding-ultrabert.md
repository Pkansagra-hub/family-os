---
adr_number: 'K003'
affected_layers:
- layer3_cognition
- layer4_runtime
affected_modules:
- k0.runtime.ultrabert_adapter
- k0.modules.builders.embedding_queue_write
- k0.modules.embedding.extract_from_cache
- k0.modules.builders.embedding_write
- k0.pipelines.p02_write
- k0.pipelines.p08_embedding
authors:
- K0 Architecture Team
concerns:
- performance
- architecture-simplification
- latency
- resource-efficiency
date_created: '2025-12-13'
date_updated: '2025-12-13'
implementation_date: null
implementation_phase: 'P03 Implementation'
implementation_status: ACCEPTED
propagation:
  affected_adrs:
  - k009.2-embedding-queue-writer
  affected_contracts:
  - k0/contracts/pipelines/p02_write.v1.yaml
  - k0/contracts/pipelines/p08_embedding_management.v1.yaml
  - k0/contracts/modules/embedding.extract_from_cache.v1.yaml
  - k0/contracts/modules/builders.embedding_write.v1.yaml
  - k0/contracts/modules/embedding.faiss_indexer.v1.yaml
  - k0/contracts/modules/embedding.backfill.v1.yaml
  affected_tests:
  - tests/k0/pipelines/test_p02_inline_embedding.py
  - tests/k0/modules/embedding/test_extract_from_cache.py
  - tests/k0/modules/builders/test_embedding_write.py
  triggers:
  - UltraBERT provides 768-dim embeddings in single forward pass
  - P08 async pipeline adds unnecessary latency for embedding availability
  - P03 consolidation requires embeddings for semantic similarity
related_adrs:
- k009.2-embedding-queue-writer
related_contracts:
- k0/contracts/pipelines/p02_write.v1.yaml
- k0/runtime/ultrabert_adapter.py
related_diagrams:
- architecture_diagrams/k0/p02_write_driver_architecture.mmd
research_citations:
- 'UltraBERT v2.1.0 - Single Model Multi-Task Architecture'
- 'BERT Sentence Embeddings (Reimers & Gurevych, 2019)'
status: PROPOSED
superseded_by: []
supersedes:
- k009.2-embedding-queue-writer (partially)
title: Inline Embedding Generation via UltraBERT Single-Pass Cache
---

# ADR-K003: Inline Embedding Generation via UltraBERT Single-Pass Cache

**Status**: Accepted

**Date**: 2025-12-13

**Authors**: @K0-Architecture-Team

## Context

### Current Architecture (Async Embedding via P08)

The current embedding pipeline uses a two-phase approach:

1. **P02 Write Pipeline** (synchronous, ~171ms P95):
   - M02 `semantic_project` calls UltraBERT for entity extraction
   - M04 `affect.analyze` calls UltraBERT for sentiment/emotions/safety
   - M10 `ingress_classify` calls UltraBERT for intent/routing
   - M14 `embedding_queue_write` enqueues job to `st_embedding_queue` with `status=PENDING`
   - Emits `cognitive.embedding.enqueued.v1` topic (DEPRECATED)

2. **P08 Embedding Pipeline** (asynchronous, ~100ms per job):
   - Subscribes to `cognitive.embedding.enqueued.v1` (DEPRECATED)
   - Claims PENDING job from `st_embedding_queue`
   - Loads `sentence-transformers` (all-MiniLM-L6-v2) - **separate model from UltraBERT**
   - Computes 384-dimensional embedding
   - Writes to `st_vec` / `st_embeddings`
   - Updates `st_hipp_events.embedding_status = READY`
   - Optionally indexes in FAISS

### Pain Points

1. **Wasted Computation**: UltraBERT already computes 768-dim embeddings during its single forward pass, but this embedding is discarded. P08 then loads a completely different model (MiniLM) to recompute embeddings.

2. **Embedding Availability Delay**: P03 consolidation pipeline needs embeddings for semantic similarity scoring. With async P08, embeddings may not be available when P03 runs, forcing fallback to Jaccard text similarity.

3. **Resource Inefficiency**:
   - UltraBERT: ~500MB memory, 30ms latency, 768-dim embedding
   - MiniLM: ~250MB additional memory, 100ms latency, 384-dim embedding
   - Total: 750MB memory for embeddings vs 500MB if using UltraBERT inline

4. **Complexity**: P08 pipeline adds operational complexity (queue management, retry logic, failure handling) for a capability that is already available "for free" in the P02 hot path.

### UltraBERT Single-Pass Architecture

UltraBERT v2.1.0 provides **12 capabilities in ONE forward pass** (~30ms):

| Capability | Description | Used By |
|------------|-------------|---------|
| sentiment | 5-class sentiment | M04 affect.analyze |
| emotions | 44-class multi-label | M04 affect.analyze |
| safety_familyos | GREEN/AMBER/RED/CRISIS | M04 affect.analyze |
| safety_generic | Toxicity detection | M04 affect.analyze |
| ner_family | KINSHIP, FAMILY_EVENT | M02 semantic_project |
| ner_general | PERSON, ORG, LOC, DATE | M02 semantic_project |
| temporal | DATE_REL, TIME_REL | M02 semantic_project |
| intent | User intent | M10 ingress_classify |
| ingress | Routing category | M10 ingress_classify |
| relation | Relationship type | (future) |
| nli | Natural language inference | (future) |
| **embedding** | **768-dimensional** | **DISCARDED** |

With `K0_ULTRABERT_SINGLE_PASS=1`, all modules share ONE cached forward pass via `_get_full_analysis_result()`. The embedding is computed but never extracted.

### Business Drivers

- **P03 Consolidation**: Requires embeddings for CA1 semantic bridge similarity scoring
- **Latency SLA**: Immediate embedding availability eliminates async wait
- **Resource Efficiency**: Single model vs two models for embeddings
- **Architectural Simplicity**: Remove unnecessary async pipeline

## Decision

**Move embedding generation from async P08 to inline P02, extracting the embedding from UltraBERT's single-pass cache.**

### Architecture Changes

#### 1. New Module: `embedding.extract_from_cache:v1` (M22)

Insert after M02 `semantic_project` to extract embedding from UltraBERT cache:

```python
# k0/modules/embedding/extract_from_cache.py
"""
M22: embedding.extract_from_cache

Extracts the 768-dim embedding from UltraBERT's single-pass cache.
Cost: ~0ms (embedding already computed by M02/M04/M10 calls)

Performance: <1ms P95 (cache read only, no inference)
"""

from k0.runtime.ultrabert_adapter import _get_full_analysis_result, get_embedding

def execute(envelope: dict, enriched: dict) -> dict:
    """Extract embedding from UltraBERT cache or compute if cache miss."""
    text = envelope.get("body", {}).get("text", "")

    # Try cached result first (should be warm from M02/M04)
    result = _get_full_analysis_result(text)
    if result and hasattr(result, 'embedding') and result.embedding:
        return {
            "embedding": result.embedding,
            "embedding_id": enriched.get("embedding_id"),
            "vector_dim": 768,
            "model_id": "ultrabert_v2.1.0",
            "source": "cache_hit",
        }

    # Fallback: direct embedding call (rare, cache miss)
    embedding = get_embedding(text)
    return {
        "embedding": embedding,
        "embedding_id": enriched.get("embedding_id"),
        "vector_dim": 768,
        "model_id": "ultrabert_v2.1.0",
        "source": "direct_call",
    }
```

#### 2. New Module: `builders.embedding_write:v1` (M23)

Replace M14 `embedding_queue_write` with direct storage write:

```python
# k0/modules/builders/embedding_write.py
"""
M23: builders.embedding_write

Writes 768-dim embedding directly to st_vec table.
Replaces async P08 queue pattern with synchronous inline write.

Performance: <5ms P95 (single row INSERT)
"""

async def execute(envelope: dict, enriched: dict, syscalls: dict) -> dict:
    """Write embedding directly to storage."""
    embedding_data = enriched.get("embedding_extract_from_cache", {})
    embedding = embedding_data.get("embedding")

    if not embedding:
        return {"written": False, "reason": "no_embedding"}

    record = {
        "embedding_id": embedding_data.get("embedding_id"),
        "event_id": envelope.get("header", {}).get("event_id"),
        "tenant_id": envelope.get("header", {}).get("tenant_id"),
        "space_id": envelope.get("header", {}).get("space_id"),
        "vector": embedding,
        "vector_dim": 768,
        "model_id": "ultrabert_v2.1.0",
        "status": "READY",  # Immediately available (not PENDING)
        "created_at": int(time.time()),
    }

    await syscalls["st_vec.write"](record)

    return {
        "written": True,
        "embedding_id": record["embedding_id"],
        "vector_dim": 768,
        "status": "READY",
    }
```

#### 3. Updated P02 Pipeline DAG

```yaml
# k0/contracts/pipelines/p02_write.v1.yaml (changes)

dag:
  # Stage 20: CA1 semantic projection (calls UltraBERT, warms cache)
  - id: stage_20_ca1_semantic_project
    module: hippocampus.semantic_project:v1
    after: [stage_10_dg_pattern_separate]

  # NEW Stage 22: Extract embedding from UltraBERT cache (0ms)
  - id: stage_22_embedding_extract
    module: embedding.extract_from_cache:v1
    after: [stage_20_ca1_semantic_project]
    description: Extracts 768-dim embedding from UltraBERT single-pass cache
    config:
      model_id: ultrabert_v2.1.0
      vector_dim: 768

  # Stage 30-43: Enrichment modules (unchanged, parallel)
  # ...

  # Stage 60: Row builder (add stage_22 to dependencies)
  - id: stage_60_build_hipp_events_row
    module: builders.hipp_events_row:v1
    after:
      - stage_10_dg_pattern_separate
      - stage_20_ca1_semantic_project
      - stage_22_embedding_extract  # NEW dependency
      # ... other stages
    config:
      embedding_status: READY  # No longer PENDING

  # REPLACED: stage_61 now writes embedding directly (not queue job)
  - id: stage_61_embedding_write
    module: builders.embedding_write:v1
    after: [stage_22_embedding_extract]
    description: Writes embedding directly to st_vec table
    config:
      table: st_vec
```

#### 4. P08 Pipeline Changes

P08 is **repurposed** as an embedding lifecycle management pipeline:

| Use Case | Trigger Topic | Purpose |
|----------|---------------|---------|
| **FAISS Indexing** | `cognitive.vector.stored.v1` | Add embeddings to search index |
| **Backfill** | `cognitive.embedding.backfill.requested.v1` | Process legacy records without embeddings |
| **Model Upgrades** | `cognitive.embedding.recompute.requested.v1` | Recompute when model version changes |
| **Cleanup** | `cognitive.embedding.cleanup.requested.v1` | Remove orphaned embeddings |

See [P08 Dossier v2](../../pipelines/P08_embedding_dossier_v2.md) for full specification.

```yaml
# k0/contracts/pipelines/p08_embedding_management.v1.yaml

pipeline_id: p08_embedding_management
version: v2
name: P08 Embedding Management
description: |
  Background embedding lifecycle management.
  Primary embedding generation moved to P02 inline (ADR-K003).

  Responsibilities:
  - FAISS index management (add/remove vectors)
  - Backfill legacy records without embeddings
  - Model upgrade recomputation
  - Orphaned embedding cleanup
```

### Data Flow Comparison

**Before (Async P08)**:

```text
P02 Complete → st_embedding_queue (PENDING) → bus_emit("cognitive.embedding.enqueued.v1") [DEPRECATED]
             → P08 claims job (async, seconds later)
             → sentence-transformers computes 384-dim embedding
             → st_vec + FAISS index
             → st_hipp_events.embedding_status = READY
```

**After (Inline P02)**:

```text
P02 M02 semantic_project → UltraBERT forward pass (caches 768-dim embedding)
P02 M22 embedding_extract → reads embedding from cache (0ms)
P02 M23 embedding_write → writes to st_vec (embedding_status = READY)
P02 Complete → embedding immediately available for P03
```

## Consequences

### Positive

1. **Zero Additional Latency**: Embedding extraction from cache is ~0ms (already computed)
2. **Immediate Availability**: P03 consolidation can use embeddings immediately (no PENDING status)
3. **Resource Savings**:
   - Eliminates MiniLM model load (~250MB memory saved)
   - Single GPU/CPU pass instead of two
4. **Higher Quality Embeddings**: 768-dim UltraBERT vs 384-dim MiniLM
5. **Simplified Architecture**: Removes P08 from critical path, reduces queue management complexity
6. **Consistent Model**: Same model for all NLP tasks (sentiment, entities, embeddings)

### Negative

1. **P02 Write Path Coupling**: Embedding failures could affect P02 commit (mitigated by try/catch with graceful degradation)
2. **768-dim Storage**: Larger vectors (768 vs 384 floats) increase storage by ~2x for embeddings
3. **FAISS Index Migration**: Existing 384-dim FAISS index must be rebuilt with 768-dim vectors

### Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Cache miss during M22 | Low | Medium | Fallback to direct `get_embedding()` call |
| Storage write failure | Low | Medium | Write embedding in same UoW as hipp_events row |
| FAISS dimension mismatch | Medium | High | Version FAISS index, rebuild during migration |
| UltraBERT unavailable | Low | High | Graceful degradation: skip embedding, set status=PENDING for P08 backfill |

## Alternatives Considered

### Alternative 1: Keep Async P08 with UltraBERT

- Description: Modify P08 to use UltraBERT instead of MiniLM, but keep async pattern
- Why rejected:
  - Still has embedding availability delay for P03
  - Still requires queue management overhead
  - No latency benefit vs inline approach

### Alternative 2: Dual Embedding (768 + 384)

- Description: Generate both UltraBERT 768-dim and MiniLM 384-dim embeddings
- Why rejected:
  - Doubles embedding storage and computation
  - No clear benefit from MiniLM if UltraBERT is available
  - Increases complexity

### Alternative 3: Lazy Embedding on P03 Access

- Description: Compute embedding only when P03 needs it (just-in-time)
- Why rejected:
  - UltraBERT cache may be cold by P03 time (TTL 30s)
  - Would require re-inference, negating single-pass benefit
  - Harder to maintain FAISS index consistency

## Implementation Notes

### Phase 1: Module Implementation (2 days)

1. Create `k0/modules/embedding/` package with `__init__.py`
2. Create `k0/modules/embedding/extract_from_cache.py` (M22) with `execute()` function
3. Create `k0/modules/builders/embedding_write.py` (M23) with `execute()` function
4. Create module contracts in `k0/contracts/modules/`:
   - `embedding.extract_from_cache.v1.yaml`
   - `builders.embedding_write.v1.yaml`
   (Naming pattern: `<module_id>.v<version>.yaml` for ModuleRegistry discovery)
5. Unit tests for both modules

### Phase 2: P02 Pipeline Update (1 day)

1. Update `k0/contracts/pipelines/p02_write.v1.yaml` with new DAG
2. Add M22 and M23 to pipeline driver
3. Integration tests for inline embedding flow

### Phase 3: Storage Migration (1 day)

1. Add `vector_dim` column to `st_vec` if not present
2. Update FAISS index to support 768-dim vectors
3. Migration script for existing 384-dim embeddings (backfill via repurposed P08)

### Phase 4: P08 Repurpose (0.5 day)

1. Update P08 contract to `p08_embedding_management.v1.yaml`
2. Pipeline name: `P08 Embedding Management`
3. Update event subscriptions to `cognitive.*` namespace:
   - Subscribe to: `cognitive.vector.stored.v1` (FAISS indexing)
   - Emit: `cognitive.vector.indexed.v1`, `cognitive.embedding.backfilled.v1`
4. Update to use UltraBERT for backfill operations

### Rollback Plan

1. Revert P02 pipeline YAML to use M14 `embedding_queue_write`
2. Re-enable P08 subscription to `p02.embedding.enqueued.v1`
3. Keep M22/M23 modules for future use

### Feature Flag

```python
# Enable inline embedding (default True after migration)
K0_EMBEDDING_INLINE = os.getenv("K0_EMBEDDING_INLINE", "1")

# If disabled, fall back to P08 queue pattern
if K0_EMBEDDING_INLINE not in {"1", "true", "True"}:
    # Use legacy M14 embedding_queue_write
    pass
```

## References

- **Architecture Diagrams**: `architecture_diagrams/k0/p02_write_driver_architecture.mmd`
- **UltraBERT Adapter**: `k0/runtime/ultrabert_adapter.py` (lines 729-751: `get_embedding()`)
- **Single-Pass Cache**: `k0/runtime/ultrabert_adapter.py` (lines 216-237: `_get_full_analysis_result()`)
- **P02 Pipeline Contract**: `k0/contracts/pipelines/p02_write.v1.yaml`
- **P08 Dossier v2**: `docs/pipelines/P08_embedding_dossier_v2.md`
- **P08 Exploration v2**: `docs/pipelines/P08_embedding_exploration_v2.md`
- **P03 Dossier**: `docs/pipelines/P03_consolidation_dossier.md` (Section 4.4: CA1 Bridge)
- **Related ADR**: `k009.2-embedding-queue-writer.md` (superseded for primary path)

## Revision History

- 2025-12-13: Initial draft (@K0-Architecture-Team)
- 2025-12-13: Status changed from PROPOSED → ACCEPTED after architecture review
  - Fixed event naming to `cognitive.*` namespace
  - Clarified P08 pipeline naming as `p08_embedding_management`
  - Added module registration/discovery implementation details
  - Aligned with k0_architecture_master.md Part 7.1 ADR Index
