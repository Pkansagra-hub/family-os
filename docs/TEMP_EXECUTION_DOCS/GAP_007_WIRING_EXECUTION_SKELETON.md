# GAP-007 Wiring Execution Skeleton

> **Scope**: GAP-007 — R4 Knowledge Graph Edge Enrichment (Production-Grade Wiring)
> **Status**: NOT_STARTED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: TBD
>
> **Goal**: Define *wiring-only* (skeleton) for how each enrichment algorithm plugs into the existing
> P03 pipeline execution path: **R4 → envelope → R6 staging → R7 truth writer → st_kg_edges**.
>
---

## Document Overview

This document is a wiring checklist skeleton for GAP-007 algorithms.

**Non-goals (for this skeleton)**:

- Detailed algorithm math/threshold tuning
- Full schema migration scripts
- Full test cases

**Primary wiring chain (must remain true for all algorithms)**:

- R4 produces `KGEdge` and/or `KGEdgeUpdate`
- R4 emits to envelope fields (R4 phase outputs)
- R6 converts envelope outputs to `StagedWrite` records via `KGWriteAssembler`
- R7 persists to truth tables using `KGLayerWriter` (for `st_kg_edges`)

**Core touchpoints (reference only)**:

- R4: `k0/pipelines/p03/phases/r4_kg_consolidator.py`
- Envelope types: `k0/pipelines/p03/phase_outputs.py`
- R6 staging: `k0/pipelines/p03/phases/r6_staging.py`
- Staging assembler: `k0/modules/consolidation/staging/kg_write_assembler.py`
- R7 truth writer: `k0/pipelines/p03/phases/r7_truth_writer.py`
- KG layer writer: `k0/modules/consolidation/truth_writer/layers/kg.py`
- Syscalls: `k0/kernel/syscalls.py`

---

## Part J: Wiring checklist per algorithm

> **Important**: Each algorithm section below is intentionally a *skeleton*.
> Fill in specifics during implementation.
>
> **Persistence principle**: If an algorithm produces a signal we want to query later,
> it must survive the full path: R4 object → envelope → staged write → writer SQL → `st_kg_edges`.

### J.1 Semantic similarity edges

#### J.1.1 Inputs it needs

- Batch KG entities (IDs + types)
- Entity embeddings:
  - Prefer in-memory vectors if available
  - Otherwise `embedding_id` for lookup from `st_vec`
- Thresholds/config: k, similarity_threshold, max_edges_per_entity
- Existing edges lookup (to decide INSERT vs UPDATE)

#### J.1.2 Syscalls it calls

- `union_index_search(query_vector, k, layer_filter=["st_kg_dom"], tenant_id, space_id)` (recommended)
- `embedding_vectors_batch_query(embedding_ids)` (if vectors not in memory)
- `kg_edges_lookup(tenant_id, space_id)`

#### J.1.3 Envelope fields it emits

- `envelope.phases.r4_new_edges` (new similarity edges)
- `envelope.phases.r4_updated_edges` (reinforcements to existing edges)

#### J.1.4 What must be persisted in st_kg_edges

- `relation_type` (e.g., RELATED_TO or a dedicated SIMILAR_TO)
- `edge_weight` and `confidence_score`
- `properties_json` (must include at least similarity score and thresholds)
- `source_algorithm` (required; target value: `semantic_similarity`)
- Evidence linkage:
  - TODO: decide correct column(s) for event/episode evidence

---

### J.2 Temporal proximity edges

#### J.2.1 Inputs it needs

- Event timestamps (epoch ms) for all events participating in the batch
- Event → entities mapping (which entities appeared in which events)
- Thresholds/config: temporal_window_ms, decay/tau, max_edges_per_entity
- Existing edges lookup (to decide INSERT vs UPDATE)

#### J.2.2 Syscalls it calls

- `kg_edges_lookup(tenant_id, space_id)`
- (Optional) additional historical reads if the algorithm extends beyond batch window (TBD)

#### J.2.3 Envelope fields it emits

- `envelope.phases.r4_new_edges`
- `envelope.phases.r4_updated_edges`

#### J.2.4 What must be persisted in st_kg_edges

- `relation_type` (e.g., RELATED_TO or TEMPORALLY_ASSOCIATED)
- `edge_weight` and `confidence_score`
- `properties_json` (must include temporal deltas/window/tau)
- `source_algorithm` (required; target value: `temporal_proximity`)
- Evidence linkage:
  - event IDs used for the temporal linkage

---

### J.3 Contextual edges

#### J.3.1 Inputs it needs

- Context signals per event (as available from `st_hipp_events` hydration), such as:
  - location/location_type
  - participants
  - mood/emotion/affect signals
  - activity type
- Event → entities mapping
- Thresholds/config: contextual_similarity_threshold, max_edges_per_entity
- Existing edges lookup

#### J.3.2 Syscalls it calls

- `kg_edges_lookup(tenant_id, space_id)`
- (Optional) `kg_entities_lookup(tenant_id, space_id)` if required for additional attributes

#### J.3.3 Envelope fields it emits

- `envelope.phases.r4_new_edges`
- `envelope.phases.r4_updated_edges`

#### J.3.4 What must be persisted in st_kg_edges

- `relation_type` (e.g., CONTEXTUALLY_RELATED)
- `edge_weight` and `confidence_score`
- `properties_json` (must include context feature overlap details)
- `source_algorithm` (required; target value: `contextual`)
- Evidence linkage:
  - event IDs contributing context

---

### J.4 Transitive closure edges

#### J.4.1 Inputs it needs

- A bounded subgraph input set:
  - batch-local edges, and/or
  - k-hop neighborhood for batch entities
- Rules/config: max_hops, attenuation factor, min_confidence
- Existing edges lookup

#### J.4.2 Syscalls it calls

- `kg_edges_lookup(tenant_id, space_id)` (may be too expensive at scale; consider bounded syscall)
- (Potential new syscall, TBD): `kg_edges_by_entity_ids(tenant_id, space_id, entity_ids)`

#### J.4.3 Envelope fields it emits

- `envelope.phases.r4_new_edges` (inferred edges)
- `envelope.phases.r4_updated_edges` (reinforce inferred edge if already exists)

#### J.4.4 What must be persisted in st_kg_edges

- `relation_type` (inferred type; may reuse RELATED_TO with subtype)
- `edge_weight` and `confidence_score`
- `properties_json` (must include inference chain, e.g., via edge IDs and hop count)
- `source_algorithm` (required; target value: `transitive_closure`)
- Evidence linkage:
  - inference provenance (which edges/observations implied this)

---

### J.5 Bayesian causal edges

#### J.5.1 Inputs it needs

- Time-ordered event evidence (even when sparse)
- Priors (by entity_type, relation_type, domain heuristics)
- Existing causal signals (Granger outputs if present)
- Existing edges lookup

#### J.5.2 Syscalls it calls

- `kg_edges_lookup(tenant_id, space_id)`
- (Optional) `kg_edges_query(tenant_id, space_id, relationship_types=[...])` for scoped reads

#### J.5.3 Envelope fields it emits

- `envelope.phases.r4_new_edges` (new CAUSES edges)
- `envelope.phases.r4_updated_edges` (updates to CAUSES edges)
- (If using the existing causal channel) `envelope.phases.r4_causal_edges` (TBD: unify vs separate)

#### J.5.4 What must be persisted in st_kg_edges

- `relation_type` = CAUSES (or a dedicated causal relation type)
- `edge_weight` and `confidence_score`
- `properties_json` (must include priors/posterior summary and key evidences)
- `source_algorithm` (required; target value: `bayesian_causal`)
- Evidence linkage:
  - event IDs supporting the causal claim

---

### J.6 Edge weight normalization

#### J.6.1 Inputs it needs

- All edges created/updated in the current R4 run (post-enrichment)
- Existing edge weights for affected nodes (bounded neighborhood)
- Rules/config: normalization target (sum=1, cap per node, etc.)

#### J.6.2 Syscalls it calls

- `kg_edges_lookup(tenant_id, space_id)` or a bounded neighbor query (preferred)

#### J.6.3 Envelope fields it emits

- `envelope.phases.r4_updated_edges` (weight_delta updates)

#### J.6.4 What must be persisted in st_kg_edges

- Updated `edge_weight` values (typically via delta application)
- `properties_json` (must include normalization strategy and before/after summaries where feasible)
- `source_algorithm` (required; target value: `weight_normalization`)

---

## Appendix: Capability checklist (skeleton)

- For semantic similarity via union index:
  - Required capability: `faiss.read`
  - Required capability (if embedding fetch needed): `st_vec.read`
- For all algorithms that read existing KG:
  - `st_kg_edges.read`
  - `st_kg_dom.read` (if entity attributes are needed)
- For writing edges:
  - `st_kg_edges.write`

---

## Appendix: Persistence checklist for st_kg_edges (skeleton)

The following fields must be reviewed/confirmed for GAP-007:

- Existing: `edge_id`, `tenant_id`, `space_id`, `source_entity_id`, `target_entity_id`, `relation_type`
- Existing: `edge_weight`, `confidence_score`, `observation_count`, `properties_json`, `archival_status`, `valid_from`, `created_at`, `updated_at`
- New (recommended): `source_algorithm`
- Evidence fields (TBD): event/episode provenance columns (avoid overloading `source_episodes_json`)
