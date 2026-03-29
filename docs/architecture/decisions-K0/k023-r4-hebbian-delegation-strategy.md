---
adr_number: 'K023'
affected_layers: [k0]
affected_modules: [p03-r4-kg-consolidator, hebbian-learner]
authors:
- K0 Architecture Team
concerns:
- code-duplication
- maintainability
- correctness
date_created: '2025-07-02'
date_updated: '2025-07-02'
implementation_date: '2025-07-02'
implementation_phase: M5.H
implementation_status: ACCEPTED
propagation:
  affected_adrs: []
  affected_contracts: [p03_consolidation.v1.yaml]
  affected_tests: [test_r4_kg_consolidator.py]
  triggers:
  - Changes to R4 co-occurrence logic
  - Changes to HebbianLearner API
related_adrs: [k003]
related_contracts: [p03_consolidation.v1.yaml]
related_diagrams: []
research_citations: []
status: ACCEPTED
superseded_by: []
supersedes: []
title: R4 Hebbian Delegation Strategy -- Selective Method Calls
---

# K023: R4 Hebbian Delegation Strategy

## Context

R4's `_discover_relationships` has 150+ lines of co-occurrence counting logic. Meanwhile,
`HebbianLearner.process_batch()` does similar aggregation. The question is whether R4 should
delegate entirely to `process_batch()` or keep its own enumeration.

## Decision

**Selective method calls** -- R4 keeps its own co-occurrence enumeration and delegates only
weight computation to HebbianLearner methods.

### Rationale

R4's co-occurrence logic has R4-specific features that `process_batch()` lacks:

1. **UltraBERT relation type inference** (M10.3): R4 infers edge types (FAMILY, FRIEND,
   COLLEAGUE) from ULTRABERT relation heads. `process_batch()` uses a simpler 3-type system
   (INTERACTS_WITH, FREQUENTS, DISCUSSES).

2. **Cluster-level deduplication**: R4 operates on `EntityCluster` objects (12 fields) with
   cluster_id-based dedup. HebbianLearner operates on `ParsedEntity` (4 fields) parsed from
   `ner_entities_json`. The data models are incompatible without a lossy adapter.

3. **Self-loop guards**: R4 has multi-level self-loop prevention (same cluster_id from different
   NER heads). `process_batch()` has no equivalent.

4. **Existing edge lookup**: R4 loads existing edges from `st_kg_edges` and increments
   `observation_count`. `process_batch()` returns aggregated counts without DB awareness.

5. **R1 importance score injection** (5.H.1): R4 builds an `r1_importance_map` from
   `envelope.phases.r1_scored_events` and uses it per-event. `process_batch()` reads
   `event.importance_score` directly, which may not be populated at R4 execution time.

### What R4 delegates to HebbianLearner

| Method | Usage |
|--------|-------|
| `compute_initial_weight(avg_importance)` | Initial edge weight for new edges |
| `update_edge_weight(current, count, importance)` | Adaptive weight updates |
| `apply_decay(edges, days)` | Time-based exponential decay (5.H.2) |
| `apply_anti_decay(edge, signal, confidence)` | Anti-Hebbian weakening (5.H.2) |

### What R4 keeps

- Co-occurrence pair enumeration with cluster dedup
- UltraBERT relation type/subtype inference
- Self-loop guards
- DB read/write orchestration (existing edge lookup, observation count)
- R1 importance score map building and injection
- Edge provenance tracking (importance_source)

## Consequences

- No code duplication for weight computation (HebbianLearner is authoritative)
- R4 retains full control over co-occurrence enumeration specifics
- `ParsedEntity` alignment (5.H.3.2) is NOT needed -- no adapter layer required
- `process_batch()` remains available for simpler use cases (e.g., batch reprocessing)
- Future changes to weight formulas only need to update HebbianLearner

## Alternatives Considered

### Full delegation to process_batch()

Would require:
- Adapter from EntityCluster to ParsedEntity (lossy)
- Moving UltraBERT inference outside process_batch
- Reimplementing DB-aware observation counting
- Breaking the r1_importance_map injection pattern

Rejected: Too much code churn for marginal deduplication benefit.
