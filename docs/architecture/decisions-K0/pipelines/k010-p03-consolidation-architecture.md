    # ADR-K010: P03 Consolidation Architecture - Sleep-Cycle Memory Consolidation

**ADR ID:** K010
**Pipeline ID:** P03_CONSOLIDATION
**Status:** ✅ Accepted
**Date:** 2025-12-31
**Owner:** K0 Architecture Team

**Dossier Sections:** 1, 3, 4
**Normative Reference:** [P03_consolidation_dossier_v2.md](../../../pipelines/P03_consolidation_dossier_v2.md)

**Related ADRs:**

- k010.1-p03: Sleep Cycle State Machine
- k010.9-p03: Capability-Based Security
- K004: Capability Mesh Architecture
- K010.1: Atomic UoW Writer

---

## Context

P02 writes raw hippocampal events to `st_hipp_events` as staging records. These are not queryable truth. The system requires a consolidation process that:

1. **Clusters** related events into coherent episodes
2. **Deduplicates** near-identical memories using SimHash
3. **Forgets** low-importance memories via decay scoring
4. **Builds** knowledge graph from entity relationships
5. **Generates** insights through counterfactual exploration
6. **Writes** consolidated truth to 8 durable memory tables

**Key Principle:** The 8 memory layers are **TRUTH**. New signals from P02 are **candidates** that must be reconciled against existing truth.

---

## Decision

Implement P03_CONSOLIDATION as a **9-phase DAG pipeline (R0-R8)** inspired by neuroscience sleep consolidation:

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    P03 CONSOLIDATION PIPELINE                               │
│                                                                             │
│  Entry: p03.consolidation.triggered.v1 (Scheduler/Manual)                  │
│  Exit:  p03.consolidation.complete.v1                                       │
│                                                                             │
│  R0 (INIT)  → R1 (SCORE) → R2 (CLUST) → R3 (PRUNE) → R4 (KG)              │
│       ↓           ↓            ↓            ↓           ↓                   │
│  R5 (DREAM) → R6 (STAGE) → R7 (WRITE) → R8 (EMIT)                          │
│                                                                             │
│  Phases:                                                                    │
│  R0: Batch Selection        R5: Dream Exploration (REM)                    │
│  R1: Importance Scoring     R6: Staging Updates                            │
│  R2: Episodic Clustering    R7: Atomic Truth Writes                        │
│  R3: Forgetting/Pruning     R8: Event Emission                             │
│  R4: KG Consolidation                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | 9-Phase DAG (R0-R8) | Maps to neuroscience sleep phases |
| Trigger Model | INTERVAL + THRESHOLD + MANUAL | Flexible scheduling |
| Entry Topic | `p03.consolidation.triggered.v1` | Scheduler-initiated |
| Concurrency | 1 (single cycle) | Avoid conflicting truth writes |
| Clustering | DBSCAN | No predefined cluster count |
| Deduplication | SimHash | O(1) lookup, P02 pre-computed |
| Truth Write | Atomic multi-table UoW | All-or-nothing |

### Pipeline Variants

**P03_CONSOLIDATION (Batch Mode):**

- Trigger: INTERVAL (90 min) OR THRESHOLD (≥500 pending) OR MANUAL
- Entry: `p03.consolidation.triggered.v1`
- Exit: `p03.consolidation.complete.v1`
- Concurrency: 1
- Max Batch: 1000 events

**P03_INCREMENTAL (Future):**

- Event-driven lightweight scoring only

### Entry/Exit Topics

**Entry:** `p03.consolidation.triggered.v1`, `p02.write.complete.v1` (future)

**Exit:** 12 topics per Appendix E.2:

- `p03.consolidation.complete.v1`
- `p03.phase.complete.v1`
- `p03.episode.formed.v1`
- `p03.pattern.discovered.v1`
- `p03.truth.{reinforced,created,evolved}.v1`
- `p03.memory.pruned.v1`
- `p03.gap.detected.v1`
- `p03.kg.updated.v1`
- `p03.insight.generated.v1`
- `p03.embedding.created.v1`

### Storage Tables

**Input:** st_hipp_events, st_vec, st_epi, st_kg_dom, st_kg_edges
**Output:** st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_learning_queue, st_consolidation_audit

---

## Consequences

### Positive

- Clean separation of staging from truth
- Neuroscience-inspired architecture aids reasoning
- Phase-based design enables independent retry
- Declarative DAG contracts for version control

### Negative

- Batch latency (up to 90 min) before events become queryable
- R5 Dream phase adds complexity
- Requires P08 embedding.search dependency

### Risks

- P08 circuit breaker needed if embedding service unavailable
- Large batches may exceed memory/timeout budgets

---

## Implementation Notes

- **Contract:** `k0/contracts/pipelines/p03_consolidation.v1.yaml`
- **Modules:** `k0/modules/consolidation/` (to be created)
- **State Machine:** See [k010.1-sleep-cycle-state-machine.md](k010.1-sleep-cycle-state-machine.md)

---

## References

- [P03 Dossier v2](../../../pipelines/P03_consolidation_dossier_v2.md) - Sections 1, 3, 4
- [P02 Write Pipeline](P02-write-pipeline-architecture.md) - Reference implementation
