# P02 Write Pipeline - Architecture Decision Record

**Pipeline ID:** P02_WRITE
**Phase:** K0 Phase 1 (Core Memory Formation)
**Status:** ACCEPTED
**Date:** 2025-11-10
**Last Updated:** 2025-12-24
**Owner:** K0 Architecture Team

**Related ADRs:**
- K001: Write Pipeline V1 Hardening
- K002: Idempotency TOCTOU Race Fix
- K003: Inline Embedding with UltraBERT
- k009: Pipeline Builders
- K010.1: Atomic UoW Writer

---

## Executive Summary

P02_WRITE is the K0 background pipeline responsible for transforming WAL-committed memory envelopes into enriched hippocampal records. The pipeline implements a two-phase architecture:

- **Phase 1 (Hot Path ~93ms):** Command Port validates, enforces policy, and atomically commits to WAL + outbox
- **Phase 2 (Background ~171ms P95):** P02 dequeues from outbox, enriches via hippocampus modules, and writes to `st_hipp_events` + `st_vec`

The design follows a **declarative DAG architecture** with pure async modules, capability-based security, and atomic 3-table transactions.

---

## Architecture Overview

### System Context

```
┌─────────────────────────────────────────────────────────┐
│           Command Port (Hot Path - 93ms)                 │
│  PEP → Gate → Policy → Atomic Write                     │
│  Writes: st_wal, idem_ledger, st_outbox, st_receipts    │
│  Emits: cognitive.memory.write.committed.v1             │
└─────────────────────────────────────────────────────────┘
                         ↓
              (BusDispatcher / Outbox Worker)
                         ↓
┌─────────────────────────────────────────────────────────┐
│           P02 Write Pipeline (Background - 171ms P95)    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Stage 10: DG Pattern Separation (M01)             │   │
│  │   → SimHash, MinHash fingerprints                 │   │
│  │   → Novelty detection (local only)                │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Stage 20: CA1 Semantic Projection (M02)           │   │
│  │   → Entity extraction (spaCy)                     │   │
│  │   → KG triple generation                          │   │
│  │   → UltraBERT single-pass (warms cache)           │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Stage 22: Embedding Extract (M22) - ADR-K003      │   │
│  │   → Extract 768-dim from UltraBERT cache (0ms)    │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Stages 30-43: Context Enrichment (Parallel)       │   │
│  │   → M04: Affect analysis (valence, arousal)       │   │
│  │   → M05: Space resolution (visibility)            │   │
│  │   → M07: Social graph (family relationships)      │   │
│  │   → M08-M12: Temporal, device, ingress, geo       │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Stage 55: Salience Scoring (M06)                  │   │
│  │   → Write-path salience (no novelty yet)          │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Stage 60-70: Builders + Atomic Commit             │   │
│  │   → M13: hipp_events row builder                  │   │
│  │   → M16: Atomic 3-table UoW (ADR-K010.1)          │   │
│  │     - st_hipp_events                              │   │
│  │     - st_vec (pgvector VECTOR(768))               │   │
│  │     - st_pipeline_processed                       │   │
│  │   → M17: Outbox emitter                           │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  Outputs:                                                │
│  - st_hipp_events (enriched hippocampal record)         │
│  - st_vec (768-dim embedding, pgvector HNSW indexed)    │
│  - Exit topics for downstream pipelines                  │
└─────────────────────────────────────────────────────────┘
```

---

## Decision Context

### Problem Statement

Memory write events need to be transformed from raw envelope format into structured, searchable hippocampal records with:
- Pattern separation fingerprints (for deduplication/clustering in P03)
- Semantic projections (entities, KG triples)
- Dense vector embeddings (for similarity search)
- Context enrichment (affect, social, temporal, spatial)
- Salience scoring (for attention/prioritization)

### Constraints

1. **Two-Phase Architecture:** Hot path must return 202 Accepted quickly; enrichment is background
2. **Atomicity:** Storage writes must be atomic (all-or-nothing)
3. **Idempotency:** Pipeline must handle re-processing gracefully
4. **Capability Security:** Modules only access granted storage capabilities
5. **Observability:** All operations must be traceable

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Declarative DAG + Pure Modules | Testable, composable, version-controlled |
| Entry Mechanism | Outbox worker (not event subscription) | Reliable delivery, backpressure control |
| Embedding Generation | Inline UltraBERT (ADR-K003) | Single forward pass, 768-dim, no async wait |
| Vector Storage | pgvector VECTOR(768) + HNSW | Native PostgreSQL, auto-indexed on INSERT |
| Atomic Commit | 3-table transaction (M16) | All-or-nothing for hipp_events + st_vec + processed |
| Idempotency | st_pipeline_processed offset tracking | Separate from hot-path idem_ledger |

---

## Pipeline Contract

**Contract Path:** `k0/contracts/pipelines/p02_write.v1.yaml`

```yaml
pipeline_id: P02_WRITE
version: v1
name: P02 Write - Episodic Memory Formation

entry_topic: cognitive.memory.write.committed.v1
exit_topic: p02.write.complete.v1
concurrency: 1
max_queue_depth: 512

required_capabilities:
  - st_hipp_events.write
  - st_vec.write
  - st_pipeline_processed.write
  - st_outbox.write
  - st_relationships.read
```

---

## Storage Access

### Reads

| Table | Purpose | Capability |
|-------|---------|------------|
| st_wal | Read envelope via wal_pos | (via outbox entry) |
| st_outbox | Dequeue work batch (128 events) | (work queue) |
| st_relationships | Family graph (5 relationship types) | st_relationships.read |
| households | Household metadata | (implicit) |
| people | People directory | (implicit) |
| st_devices | Device registry | (implicit) |
| st_retention_policy | Retention matrix | (implicit) |

### Writes

| Table | Purpose | Capability |
|-------|---------|------------|
| st_hipp_events | Enriched hippocampal records | st_hipp_events.write |
| st_vec | 768-dim embeddings (pgvector) | st_vec.write |
| st_pipeline_processed | P02 offset tracking | st_pipeline_processed.write |
| st_outbox | Emit downstream events | st_outbox.write |

---

## Exit Topics

| Topic | Consumer | Purpose |
|-------|----------|---------|
| p02.write.complete.v1 | Observability | Pipeline completion signal |
| cognitive.vector.stored.v1 | P08 | Vector stored (legacy, P08 maintenance mode) |
| workspace.wm.updated.v1 | P04 | Working memory update |
| core.affect.analyzed.v1 | P06 | Affect classification result |
| space.resolution.complete.v1 | P07 | Space resolution for sync |
| p02.hippocampus.pattern_separated.v1 | P03 | DG fingerprints for consolidation |

---

## Performance Budget

| Stage | Target P95 | Module |
|-------|------------|--------|
| DG Pattern Separation | 15ms | M01 |
| CA1 Semantic Projection | 50ms | M02 (UltraBERT) |
| Embedding Extract | 0ms | M22 (cache hit) |
| Affect Analysis | 10ms | M04 (Tier-0) |
| Context Enrichment | 20ms | M08-M12 (parallel) |
| Salience Scoring | 5ms | M06 |
| Atomic Commit | 30ms | M16 |
| **Total P02** | **171ms P95** | |

---

## Module Dependencies

| Module ID | Module Name | Dependencies | Emits |
|-----------|-------------|--------------|-------|
| M01 | DGPatternSeparate | - | fingerprints |
| M02 | CA1SemanticProject | M01 | entities, triples, cache warm |
| M22 | EmbeddingExtract | M02 | 768-dim vector |
| M04 | AffectAnalyze | M02 | valence, arousal, tags |
| M05 | SpaceResolve | M02 | visibility, owner |
| M07 | SocialGraphResolve | M02 | participants, roles |
| M06 | SalienceScore | M04, M05, M07 | salience_score, band |
| M13 | HippEventsBuilder | all above | row dict |
| M16 | AtomicUoWWriter | M13, M22 | 3-table commit |
| M17 | OutboxEmitter | M16 | exit topics |

---

## Migration Notes

### ADR-K003 Changes (2025-12-13)

1. Added M22 (embedding.extract_from_cache:v1) after stage_20
2. Replaced M14 embedding_queue_write with M23 (now merged into M16)
3. Embeddings stored inline in st_vec (no async P08 for primary generation)
4. cognitive.vector.stored.v1 event triggers P08 maintenance (not primary indexing)

### PostgreSQL Migration (2025-12-24)

1. st_vec uses pgvector VECTOR(768) type
2. HNSW index auto-indexes vectors on INSERT
3. st_embedding_queue deprecated (embeddings written directly by M16)
4. P08 reduced to maintenance mode (backfill, cleanup)

---

## Security Considerations

1. **Capability Model:** M16 only granted st_hipp_events.write, st_vec.write, st_pipeline_processed.write
2. **No Raw Coordinates:** P02 reads pre-masked location_geohash from WAL (Gate Stage 3 masks)
3. **Policy Enforcement:** Only ALLOW envelopes reach WAL (DENY never enters P02)
4. **Audit Trail:** All writes traced via cognitive_trace_id

---

## Alternatives Considered

| Alternative | Rejected Reason |
|-------------|-----------------|
| Synchronous enrichment in hot path | Latency budget exceeded (93ms limit) |
| Event subscription (not outbox) | Less reliable, harder backpressure control |
| Separate embedding pipeline | Double forward pass (MiniLM + UltraBERT), wasted compute |
| FAISS for vector indexing | PostgreSQL migration - pgvector HNSW simpler |

---

## References

- [P02 Write Dossier](../../../pipelines/P02_write_dossier.md)
- [P02 Contract](../../../../k0/contracts/pipelines/p02_write.v1.yaml)
- [ADR-K001: Write Pipeline V1 Hardening](../k001-write-pipeline-v1-hardening.md)
- [ADR-K003: Inline Embedding](k003-inline-embedding-ultrabert.md)
- [ADR-K010.1: Atomic UoW Writer](../modules/k010.1-atomic-uow-writer.md)
