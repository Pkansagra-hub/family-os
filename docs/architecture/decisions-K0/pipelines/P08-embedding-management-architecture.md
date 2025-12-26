# P08 Embedding Management Pipeline - Architecture Decision Record

**Pipeline ID:** P08_EMBEDDING_MANAGEMENT
**Phase:** K0 Phase 1 (Maintenance Mode)
**Status:** ACCEPTED
**Date:** 2025-12-13
**Last Updated:** 2025-12-24
**Owner:** K0 Architecture Team

**Related ADRs:**
- K003: Inline Embedding with UltraBERT (primary generation moved to P02)
- K010.1: Atomic UoW Writer (3-table transaction includes st_vec)
- k009.2: Embedding Queue Writer (deprecated)

---

## Executive Summary

P08_EMBEDDING_MANAGEMENT has evolved through three architectural phases:

- **v1 (Original):** Primary embedding generator using MiniLM (384-dim), async P08 pipeline
- **v2 (ADR-K003):** Primary generation moved to P02 inline, P08 became FAISS indexer
- **v3 (PostgreSQL Migration):** FAISS deprecated, pgvector HNSW replaces indexing, P08 reduced to maintenance mode

The current v3 architecture retains P08 for **maintenance operations only**:
- Backfill legacy records without embeddings
- Cleanup orphaned vectors
- Integrity verification

---

## Architecture Evolution

### v1: Primary Embedding Generator (Deprecated)

```
P02 → st_hipp_events (embedding_status=PENDING)
    → st_embedding_queue (status=PENDING)
    → bus_emit("p02.embedding.enqueued.v1")
                    ↓
P08 → claim → compute (MiniLM 384-dim) → store → index → update
    → embedding_status=READY
```

**Problems:**
1. UltraBERT already computes 768-dim embeddings in P02 (discarded)
2. Double model inference (MiniLM + UltraBERT)
3. Async latency for embedding availability

### v2: FAISS Indexer (Deprecated 2025-12-24)

```
P02 → M02/M04/M10 (UltraBERT single-pass, includes embedding)
    → M22 (extract embedding from cache - 0ms)
    → M16 (atomic write: st_hipp_events + st_vec)
    → embedding immediately available (status=READY)
                    ↓
P08 (Kernel Scheduler) → FAISS indexing via background task
    → Polls st_vec for status=READY vectors (300s interval)
    → Adds to FAISS IndexIDMap, updates status=INDEXED
```

**Deprecation Reason:** PostgreSQL migration to pgvector - HNSW index auto-indexes on INSERT, no separate indexing step needed.

### v3: Maintenance Mode (Current)

```
P02 → M16 (atomic 3-table write: st_hipp_events + st_vec + st_pipeline_processed)
    → Embedding immediately searchable (pgvector HNSW auto-indexed)
                    ↓
P08 (Scheduled Maintenance) → Backfill, Cleanup, Integrity
    → Interval trigger (300s): Check for pending maintenance
    → Threshold trigger: Trigger when backlog grows
    → Manual trigger: Admin-initiated operations
```

---

## Architecture Overview

### System Context

```
┌─────────────────────────────────────────────────────────┐
│           P02 Write Pipeline (Primary Path)              │
│  M16 Atomic Commit:                                      │
│    - st_hipp_events (enriched record)                   │
│    - st_vec (768-dim embedding, pgvector VECTOR)        │
│    - st_pipeline_processed (offset tracking)            │
│                                                          │
│  pgvector HNSW Index:                                   │
│    - Auto-indexes on INSERT                              │
│    - vector_cosine_ops for similarity search            │
│    - No separate indexing step needed                   │
└─────────────────────────────────────────────────────────┘
                         ↓
              (Embedding immediately searchable)
                         ↓
┌─────────────────────────────────────────────────────────┐
│    P08 Embedding Management (Maintenance Mode - v3)      │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Trigger: Scheduled Interval (300s)                │   │
│  │ Trigger: Threshold (PENDING count > 50)           │   │
│  │ Trigger: Manual (admin-initiated)                 │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ M25: Backfill (embedding.backfill:v1)             │   │
│  │   → Query st_hipp_events WHERE status=PENDING     │   │
│  │   → Compute embedding via UltraBERT               │   │
│  │   → Write to st_vec (auto-indexed by HNSW)        │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ M27: Cleanup (embedding.cleanup:v1)               │   │
│  │   → Query orphaned embeddings (no parent event)   │   │
│  │   → Remove from st_vec                            │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Integrity Verification                            │   │
│  │   → Verify vector dimensions (768)                │   │
│  │   → Detect corruption                             │   │
│  │   → Report anomalies                              │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Decision Context

### Problem Statement

With the PostgreSQL migration to pgvector:
1. Primary embedding generation moved to P02 inline (ADR-K003)
2. FAISS indexing replaced by pgvector HNSW (auto-indexed on INSERT)
3. P08's original roles are deprecated

### Remaining Requirements

1. **Backfill:** Legacy records created before ADR-K003 may have PENDING embeddings
2. **Cleanup:** Event deletions may leave orphaned vectors in st_vec
3. **Integrity:** Vector corruption or dimension mismatches need detection
4. **Model Upgrades:** Future model version changes may require re-embedding

---

## Key Decisions

| Decision | v1 Choice | v2 Choice | v3 Choice | Rationale |
|----------|-----------|-----------|-----------|-----------|
| Primary Embedding | P08 (MiniLM) | P02 (UltraBERT) | P02 (UltraBERT) | Single forward pass, no async wait |
| Embedding Dimension | 384 | 768 | 768 | Higher quality, UltraBERT native |
| Vector Storage | st_vec (BLOB) | st_vec (BLOB) | st_vec (pgvector) | Native PostgreSQL, HNSW index |
| Indexing | MiniLM then FAISS | FAISS IndexIDMap | pgvector HNSW | Auto-indexed on INSERT |
| P08 Role | Primary generation | FAISS indexer | Maintenance only | HNSW eliminates indexing step |
| Trigger Mode | Event-driven | Event + Scheduler | Scheduler only | No events needed for maintenance |

---

## Pipeline Contract

**Contract Path:** `k0/contracts/pipelines/p08_embedding_management.v2.yaml`

```yaml
pipeline_id: P08_EMBEDDING_MANAGEMENT
version: v3
name: P08 Embedding Management (Maintenance Mode)

# Scheduled mode - no event subscription
entry_topic: scheduled.p08.maintenance.v1  # Placeholder for schema compliance
exit_topic: embedding.maintenance.completed.v1

triggers:
  - id: maintenance_interval
    type: interval
    interval_seconds: 300
    batch_size: 100
    catch_up_enabled: true

  - id: maintenance_threshold
    type: threshold
    table: st_vec
    condition: "status = 'PENDING'"
    threshold_count: 50

  - id: maintenance_manual
    type: manual

concurrency: 1
max_queue_depth: 1000

required_capabilities:
  - st_vec.read
  - st_vec.write
  - st_hipp_events.read
  - st_hipp_events.write
  - ultrabert.embed
```

---

## Deprecated Capabilities

| Capability | Deprecated In | Reason |
|------------|---------------|--------|
| faiss.read | v3 | pgvector HNSW replaces FAISS |
| faiss.write | v3 | pgvector HNSW replaces FAISS |
| st_embedding_queue.read | v2 | Queue eliminated (inline writes) |
| st_embedding_queue.write | v2 | Queue eliminated (inline writes) |

---

## Storage Access

### Reads

| Table | Purpose | Capability |
|-------|---------|------------|
| st_hipp_events | Find PENDING embeddings | st_hipp_events.read |
| st_vec | Find orphaned vectors | st_vec.read |

### Writes

| Table | Purpose | Capability |
|-------|---------|------------|
| st_vec | Write backfilled embeddings | st_vec.write |
| st_vec | Delete orphaned vectors | st_vec.write |
| st_hipp_events | Update embedding_status | st_hipp_events.write |

---

## Module Registry

| Module ID | Module Name | Status | Purpose |
|-----------|-------------|--------|---------|
| M22 | EmbeddingExtract | ✅ Active (P02) | Extract from UltraBERT cache |
| M24 | FAISSIndexer | ❌ Deprecated | FAISS indexing (replaced by pgvector HNSW) |
| M25 | EmbeddingBackfill | ✅ Active | Backfill PENDING embeddings |
| M26 | EmbeddingRecompute | 🎯 Planning | Model upgrade re-vectorizer |
| M27 | EmbeddingCleanup | 🎯 Planning | Orphan garbage collection |

---

## Trigger Configuration

### Interval Trigger (Primary)

```yaml
id: maintenance_interval
type: interval
interval_seconds: 300  # Every 5 minutes
batch_size: 100
catch_up_enabled: true  # Process missed work on boot
```

**Behavior:**
1. Every 300s, check for maintenance work
2. If PENDING embeddings exist, run M25 backfill
3. If orphaned vectors exist, run M27 cleanup
4. On kernel boot, catch up on any missed maintenance

### Threshold Trigger (Overflow)

```yaml
id: maintenance_threshold
type: threshold
table: st_vec
condition: "status = 'PENDING'"
threshold_count: 50
check_interval_seconds: 60
batch_size: 50
```

**Behavior:**
1. Every 60s, check PENDING count
2. If count > 50, trigger immediate maintenance
3. Prevents backlog accumulation

---

## Performance Budget

| Operation | Target P95 | Notes |
|-----------|------------|-------|
| Backfill (per record) | 100ms | UltraBERT inference + pgvector INSERT |
| Cleanup (per record) | 10ms | DELETE query |
| Batch (100 records) | 5s | Backfill latency budget |

---

## Migration Notes

### pgvector Migration (2025-12-24)

1. **st_vec Schema Change:**
   ```sql
   -- Old: embedding BYTEA
   -- New: embedding VECTOR(768)
   ALTER TABLE st_vec
   ALTER COLUMN embedding TYPE VECTOR(768)
   USING embedding::VECTOR(768);
   ```

2. **HNSW Index:**
   ```sql
   CREATE INDEX idx_st_vec_embedding_hnsw
   ON st_vec USING hnsw (embedding vector_cosine_ops)
   WITH (m = 16, ef_construction = 64);
   ```

3. **FAISS Removal:**
   - Removed faiss.read, faiss.write capabilities
   - Removed M24 FAISSIndexer from DAG
   - Removed FAISS binary files from storage

---

## Alternatives Considered

| Alternative | Rejected Reason |
|-------------|-----------------|
| Keep FAISS for specialized search | pgvector HNSW sufficient, simpler ops |
| Remove P08 entirely | Still need backfill/cleanup for data integrity |
| Event-driven maintenance | Scheduled simpler, no event overhead |

---

## Future Considerations

1. **Model Upgrades:** M26 EmbeddingRecompute for re-embedding with new UltraBERT versions
2. **Multi-Model:** Additional embedding models for specialized domains
3. **Compression:** pgvector scalar quantization for storage optimization

---

## References

- [P08 Embedding Dossier](../../../pipelines/P08_embedding_dossier_v2.md)
- [P08 Contract](../../../../k0/contracts/pipelines/p08_embedding_management.v2.yaml)
- [ADR-K003: Inline Embedding](k003-inline-embedding-ultrabert.md)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
