---
adr_number: 'K003.2'
affected_layers:
- layer3_cognition
- layer4_runtime
affected_modules:
- k0.modules.core.hipp_events_writer
- k0.modules.embedding.extract_from_cache
- k0.modules.embedding.backfill
- k0.modules.embedding.cleanup
- k0.modules.embedding.recompute
- k0.modules.embedding.integrity_check
- k0.kernel.syscalls
- k0.pipelines.p08_embedding
- k0.db.alembic.versions.0071_st_vec_pgvector_native
authors:
- K0 Architecture Team
concerns:
- data-integrity
- architecture-simplification
- performance
- dead-code-elimination
date_created: '2026-03-01'
date_updated: '2026-03-01'
implementation_date: null
implementation_phase: 'M4 Implementation'
implementation_status: ACCEPTED
propagation:
  affected_adrs:
  - k003-inline-embedding-ultrabert
  affected_contracts:
  - k0/contracts/schemas/st_vec_v2.columns.yaml
  - k0/contracts/pipelines/p08_embedding_management.v3.yaml
  - k0/contracts/modules/embedding.backfill.v2.yaml
  - k0/contracts/modules/embedding.cleanup.v2.yaml
  - k0/contracts/modules/embedding.recompute.v2.yaml
  - k0/contracts/modules/embedding.extract_from_cache.v2.yaml
  - k0/contracts/modules/embedding.integrity_check.v1.yaml
  affected_tests:
  - tests/k0/embedding/test_migration_0071.py
  - tests/k0/embedding/test_m16_pgvector_write.py
  - tests/k0/embedding/test_hnsw_similarity_search.py
  - tests/k0/embedding/test_m25_pgvector_backfill.py
  - tests/k0/embedding/test_m27_orphan_cleanup.py
  - tests/k0/embedding/test_m28_integrity_check.py
  - tests/k0/embedding/test_p08_three_stage.py
  triggers:
  - st_vec.vector column is LargeBinary (BLOB) -- prevents pgvector HNSW indexing
  - FAISS is the only working vector index path but pgvector is the target
  - 1705 lines of deprecated embedding code creating confusion
  - Broken migrations in versions_broken/ never activated
related_adrs:
- k003-inline-embedding-ultrabert
related_contracts:
- k0/contracts/schemas/st_vec_v2.columns.yaml
- k0/contracts/pipelines/p08_embedding_management.v3.yaml
related_diagrams: []
research_citations:
- 'pgvector: Open-source vector similarity search for PostgreSQL'
- 'HNSW: Hierarchical Navigable Small World graphs (Malkov & Yashunin, 2018)'
status: ACCEPTED
superseded_by: []
supersedes:
- k003-inline-embedding-ultrabert (extends, does not replace)
title: 'pgvector Migration: VECTOR(768) Native Storage, FAISS Elimination'
---

# ADR-K003 v2.0: pgvector Migration -- VECTOR(768) Native Storage, FAISS Elimination

**Status**: Accepted

**Date**: 2026-03-01

**Supersedes**: ADR-K003 v1.2 (extends; v1.2 remains valid for inline embedding decision)

**Milestone**: M4 -- P08 Embedding Management Strengthening

## Context

ADR-K003 v1.2 decided to move primary embedding generation from the P08 async pipeline to P02 inline (M22 extract_from_cache + M16 hipp_events_writer). It deprecated M23 (embedding_write) and the async queue pattern.

However, v1.2 did not address:

1. **Broken storage layer**: Active migration `0025_st_vec.py` creates the `vector` column as `sa.LargeBinary` (raw bytes). pgvector HNSW indexing requires `VECTOR(768)` native type. The correct migration in `versions_broken/0026_st_vec.py` was never activated.

2. **FAISS still the only working path**: The P08 contract claims "pgvector HNSW auto-indexes on INSERT" and "FAISS indexing DEPRECATED" -- but the schema does not support pgvector, and FAISS via `rebuild_faiss_index.py` is the only working similarity search path.

3. **1705 lines of deprecated code**: M23 (285 lines), M14 (422 lines), EmbeddingQueueDriver (369 lines), rebuild_faiss_index.py (~450 lines), and the M24 FAISS indexer contract (179 lines) remain in the codebase.

4. **Model dimension confusion**: EmbeddingQueueDriver uses MiniLM-L6-v2 (384 dims) while UltraBERT produces 768 dims. Config file lists multiple unused models.

5. **M16 uses struct.pack**: Packs 768 floats into 3072-byte blob. With pgvector VECTOR(768), this must change to native format.

## Decisions

### Decision 1: Migrate st_vec.vector from LargeBinary to VECTOR(768)

**Choice**: Drop and recreate st_vec with pgvector-native `VECTOR(768)` column.

**Rationale**: pgvector HNSW indexes only work on `VECTOR(n)` typed columns. LargeBinary (BLOB) cannot be indexed. Pre-production rule allows drop + recreate without data migration.

**Migration**: `0071_st_vec_pgvector_native.py` -- drops old table, creates new with VECTOR(768), adds HNSW index (m=16, ef_construction=64, vector_cosine_ops).

### Decision 2: Eliminate FAISS from K0 entirely

**Choice**: Remove all FAISS code, contracts, and scripts from K0.

**Rationale**: pgvector HNSW replaces all FAISS functionality for memory vector similarity search. HNSW auto-indexes on INSERT -- no manual index building step needed.

**Scope boundary**: K1 `embedding_index.py` uses FAISS for capability contract search (384-dim MiniLM). This is a different use case, different layer, different dimensions. M4 eliminates FAISS from K0 only. K1 FAISS usage is RETAINED and out of scope.

### Decision 3: Standardize on UltraBERT v2.1.0, 768-dim

**Choice**: UltraBERT v2.1.0 is the only active embedding model. All config, contracts, and code reference 768-dim exclusively.

**Rationale**: MiniLM-L6-v2 (384-dim) was used only by the deprecated EmbeddingQueueDriver. No active code path uses 384-dim embeddings.

### Decision 4: Delete deprecated embedding code

**Choice**: Delete 5 files (~1705 lines total).

| File | Lines | Reason |
|------|-------|--------|
| `k0/modules/builders/embedding_write.py` (M23) | 285 | FK ordering violation, merged into M16 (ADR-K003 v1.2) |
| `k0/modules/builders/embedding_queue_write.py` (M14) | 422 | Legacy async queue pattern, replaced by P02 inline |
| `k0/drivers/embedding_queue.py` (EmbeddingQueueDriver) | 369 | Uses MiniLM 384-dim, has duplicate return bug |
| `k0/scripts/rebuild_faiss_index.py` | ~450 | Manual FAISS rebuild, replaced by HNSW auto-index |
| `k0/contracts/modules/embedding.faiss_indexer.v1.yaml` (M24) | 179 | FAISS indexer contract, deprecated |

### Decision 5: M16 vector format changes to pgvector native

**Choice**: M16 passes `list[float]` to `vec_write` syscall. The syscall formats for pgvector `VECTOR(768)` INSERT. `struct.pack` is eliminated.

**Rationale**: pgvector driver (asyncpg + pgvector extension) handles float list -> VECTOR conversion natively. No manual byte packing needed.

### Decision 6: Delete broken migrations

**Choice**: Delete 3 files from `versions_broken/`:

| File | Reason |
|------|--------|
| `0025_pgvector_extension.py` | pgvector extension handled in initial setup |
| `0026_st_vec.py` | Partially correct but still has faiss_id; replaced by 0071 |
| `0027_vector_indexes.py` | HNSW index included in 0071 |

### Decision 7: st_vec schema v2

**Choice**: 11 columns (was 13). Remove `faiss_id` and `indexed_at`. Change status CHECK to `IN ('READY', 'FAILED')` -- remove `INDEXED` state. Use TIMESTAMPTZ instead of BigInteger for timestamps. Use UUID instead of Text for IDs.

### Decision 8: P08 becomes 3-stage pipeline

**Choice**: P08 v3 has 3 stages: backfill (M25), cleanup (M27), integrity check (M28). M24 FAISS indexer removed.

### Decision 9: K1 FAISS retained (out of scope)

**Choice**: K1 `embedding_index.py` FAISS usage is explicitly RETAINED.

**Rationale**: K1 uses FAISS for capability contract search with MiniLM 384-dim embeddings. This is a completely different use case (contract matching vs memory similarity), different layer (K1 vs K0), and different dimensions (384 vs 768). Eliminating K1 FAISS is a separate decision if ever needed.

## Consequences

### Positive

- pgvector HNSW enables native cosine similarity search without external FAISS dependency
- HNSW auto-indexes on INSERT -- zero manual indexing overhead
- 1705 lines of dead code removed -- reduced maintenance burden
- Single model (UltraBERT 768-dim) eliminates dimension confusion
- `struct.pack` elimination simplifies M16 code path
- P08 gains integrity checking (M28) that never existed before

### Negative

- All existing st_vec data is lost (acceptable: pre-production, table dropped + recreated)
- pgvector extension must be installed in PostgreSQL (standard for vector workloads)
- HNSW index adds ~10% write overhead per INSERT (acceptable for memory workload)

### Risks

- pgvector version compatibility: HNSW requires pgvector >= 0.5.0
- HNSW index build time: initial index on existing data may take minutes for large datasets
- K1 FAISS retained: future engineers may assume FAISS is fully eliminated system-wide (mitigated by explicit documentation in this ADR and K1 code comments)

## Implementation Plan

All implementation is tracked in M4 Epics 4.1-4.21 in `MASTER_IMPLEMENTATION_SKELETON.md`.

| Phase | Epics | Description |
|-------|-------|-------------|
| Part A: Contracts | 4.1-4.8 | Schema, pipeline, module contracts + this ADR |
| Part B: Implementation | 4.9-4.21 | Migration, code changes, deletions, tests |

## Files Changed

### New Files
- `k0/contracts/schemas/st_vec_v2.columns.yaml`
- `k0/contracts/pipelines/p08_embedding_management.v3.yaml`
- `k0/contracts/modules/embedding.backfill.v2.yaml`
- `k0/contracts/modules/embedding.cleanup.v2.yaml`
- `k0/contracts/modules/embedding.recompute.v2.yaml`
- `k0/contracts/modules/embedding.extract_from_cache.v2.yaml`
- `k0/contracts/modules/embedding.integrity_check.v1.yaml`
- `k0/db/alembic/versions/0071_st_vec_pgvector_native.py`
- `k0/modules/embedding/integrity_check.py`
- `docs/architecture/decisions-K0/adr-k003-v2-pgvector-migration.md`

### Modified Files
- `k0/modules/core/hipp_events_writer.py` (remove struct.pack)
- `k0/kernel/syscalls.py` (vec_write accepts list[float], new integrity syscalls)
- `k0/modules/embedding/backfill.py` (pgvector native writes)
- `k0/modules/embedding/cleanup.py` (remove FAISS references)
- `k0/config/embeddings.yml` (remove MiniLM, standardize UltraBERT)

### Deleted Files
- `k0/modules/builders/embedding_write.py`
- `k0/modules/builders/embedding_queue_write.py`
- `k0/drivers/embedding_queue.py`
- `k0/scripts/rebuild_faiss_index.py`
- `k0/contracts/modules/embedding.faiss_indexer.v1.yaml`
- `k0/db/alembic/versions_broken/0025_pgvector_extension.py`
- `k0/db/alembic/versions_broken/0026_st_vec.py`
- `k0/db/alembic/versions_broken/0027_vector_indexes.py`

### Deprecated (marked, not deleted)
- `k0/contracts/modules/embedding.backfill.v1.yaml`
- `k0/contracts/modules/embedding.cleanup.v1.yaml`
- `k0/contracts/modules/embedding.recompute.v1.yaml`
- `k0/contracts/modules/embedding.extract_from_cache.v1.yaml`
- `k0/contracts/pipelines/p08_embedding_management.v2.yaml`
