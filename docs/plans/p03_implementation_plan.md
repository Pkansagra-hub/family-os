# P03 Consolidation Pipeline v2 - Implementation Plan

**Status**: Planning Phase
**Version**: 1.0.0
**Created**: 2025-12-21
**Owner**: Development Team
**Dossier Reference**: [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md)
**Upstream Pipeline**: P02 (Memory Formation)
**Downstream**: P06 (Active Learning), P08 (Embedding Index), P04 (Query)
**Master Tracking**: [k0_architecture_master.md](../../k0/pipelines/k0_architecture_master.md)

---

## Document Purpose

This plan provides the **implementation skeleton** for P03 Consolidation Pipeline v2.
It defines milestones, epics, and issues but leaves detailed specifications to be filled during implementation.

**Key Principle**: P03 v2 implements **bidirectional truth reconciliation** — new signals from P02 are candidates that must be reconciled against existing truth in 8 memory layers.

---

## K0 Architecture Master Registration Requirements

> **CRITICAL**: Updates to K0 Architecture Master are MANDATORY at each milestone.

### K0 Update Checklist (Copy to Each Milestone Closure)

```markdown
## K0 Architecture Master Closure Checklist

- [ ] Part 2.1 (Pipeline Registry): Status updated
- [ ] Part 3.1 (Module Registry): New modules added (M18-M25)
- [ ] Part 4.1 (Event Topics): P03 events registered
- [ ] Part 5.1 (Contract Registry): Module contracts added
- [ ] Part 5.2 (Syscall Matrix): Storage capabilities registered
- [ ] Part 5.3 (Storage Tables): Memory layer tables documented
- [ ] Part 7.1 (ADR Index): ADR status updated
- [ ] Version Header: Document version bumped
```

---

## Critical Blockers (Resolve Before Implementation)

<!-- NOTE: Blockers verified 2025-12-21 against actual codebase -->

| Blocker | Type | Status | Impact | Resolution |
|---------|------|--------|--------|------------|
| P02 production readiness | PREREQUISITE | ✅ **RESOLVED** | Cannot consume st_hipp_events | P02 stable and running |
| P08 embedding.search availability | DEPENDENCY | ✅ **RESOLVED** | R1/R4 need embedding queries | P08 embedding management working |
| Budget alignment (target 90 min cycle) | ARCHITECTURE | ✅ **RESOLVED** | Phases sum to 182 min without optimization | R5 optional, R3/R4 parallel (dossier design) |
| P08 backpressure | INTEGRATION | ✅ **RESOLVED** | Embedding queue overflow risk | Circuit breaker pattern implemented (ADR-0009, k1/bridge tests) |
| UltraBERT v2.1.0 | DEPENDENCY | ✅ **RESOLVED** | R1/R4 encoders: sentiment, emotions, NER | Wheel `familyos_ultrabert-2.1.0` present with 12 capabilities |
| K0 DLQ subsystem | DEPENDENCY | ✅ **RESOLVED** | Error recovery requires DLQStore | `k0/storage/dlq.py` (254 lines) ready with DeadLetterQueue class |
| K0 QoS Scheduler | DEPENDENCY | ✅ **RESOLVED** | Batch token acquisition | `k0/qos/scheduler.py` (152 lines) ready with Scheduler class |
| **K0 Advisory Lock Service** | K0 ENHANCEMENT | ⚠️ **M0 WORK** | Multi-node race conditions | Implement in Epic 0.4 (`k0/sync/advisory_lock.py`) |
| **K0 Partitioned Execution** | K0 ENHANCEMENT | ⚠️ **M0 WORK** | No horizontal scaling | Implement in Epic 0.5 (extend PipelineScheduler) |
| **K0 Optimistic Concurrency** | K0 ENHANCEMENT | ⚠️ **M0 WORK** | Duplicated version-check SQL | Implement in Epic 0.6 (extend UnitOfWork) |
| **K0 Pipeline Context** | K0 ENHANCEMENT | ⚠️ **M0 WORK** | No cluster awareness | Implement in Epic 0.7 (extend PipelineContext) |

---

## Milestone Overview

| Milestone | Focus | Key Deliverables |
|-----------|-------|------------------|
| M0 | Pre-Implementation + K0 Enhancements | ADRs, K0 registration, **K0 kernel enhancements** (Advisory Lock, Partitioned Execution, Optimistic Concurrency, Pipeline Context) |
| M1 | Infrastructure | Migrations, contracts, pipeline YAML |
| M2 | R0-R1 Core | Trigger, lock, batch selection, importance scoring |
| M3 | R2 Pattern Extraction | Clustering, pattern detection, CA1 bridge (truth query) |
| M4 | R3 Forgetting | Deduplication, novelty scoring, retention enforcement |
| M5 | R4 Knowledge Graph | Entity normalization, relationship discovery, temporal updates |
| M5A | R5 Dream (Optional) | Counterfactual, prediction, insight generation |
| M6 | R6-R7 Writers | Staging updates, 8-layer truth writes, outbox pattern |
| M7 | R8 Events & P06 | Event emission, gap detection, offset tracking |
| M8 | Testing & Performance | Integration tests, performance validation, golden dataset |
| M9 | Deployment & Ops | Docker, observability, runbooks, production rollout |

---

## Milestone 0: Pre-Implementation + K0 Kernel Enhancements

**Goal**: Create ADRs, register in K0 Architecture Master, **implement K0 kernel enhancements** required for P03
**Gate**: GATE 1 (Architectural Decision Validation) + GATE 3 (Implementation for K0 enhancements)
**Estimated Duration**: 2-3 weeks

### M0 Epic Summary

| Epic | Focus | Deliverables | Prerequisite |
|------|-------|--------------|--------------|
| 0.0 | K0 Registration | P03 in architecture master | None |
| 0.1 | P03 ADRs | k010.x ADRs for consolidation | None |
| 0.2 | Blockers | Lock design, budget resolution | None |
| 0.3 | K0 Enhancement ADRs | k011-k014 ADRs for kernel | 0.2 |
| 0.4 | Advisory Lock Service | `k0/sync/advisory_lock.py` | 0.3.1 ADR accepted |
| 0.5 | Partitioned Execution | Extend PipelineScheduler | 0.3.2 ADR accepted |
| 0.6 | Optimistic Concurrency | Extend UnitOfWork | 0.3.3 ADR accepted |
| 0.7 | Pipeline Context | Node/partition info | 0.3.4 ADR accepted |
| 0.8 | K0 Integration Tests | Validate all enhancements | 0.4-0.7 complete |

---

### Epic 0.0: K0 Architecture Master Registration

> **File**: `k0/pipelines/k0_architecture_master.md`
> **Purpose**: Register P03 in the single source of truth before any implementation

#### Issue 0.0.1: Register P03 in Pipeline Master Registry

**Section**: Part 2.1 - Pipeline Master Registry

**What to Cover**:

1. **Add P03 Row** with initial status:
   - Pipeline ID: P03
   - Name: Memory Consolidation
   - Status: **DESIGN** (will change to PLANNING after M0)
   - Owner: Memory Team
   - Layer: L3 (Pipeline Layer)
   - Dependencies: P02 (upstream), P08 (embedding dependency)
   - Downstream Consumers: P04, P06, P07

2. **Dependency Chain Documentation**:
   - P02 → P03: st_hipp_events consumption
   - P03 → P08: embedding.search capability
   - P03 → P06: gap.detected event emission
   - P03 → P04: truth tables for query

3. **Initial Trigger Documentation**:
   - Trigger types: IDLE, CRON, THRESHOLD, MANUAL
   - Default schedule: 2:00 AM local daily
   - Idle threshold: 30 minutes inactivity

**Acceptance Criteria**:

- [ ] P03 row exists in Part 2.1
- [ ] All dependencies documented
- [ ] Trigger configuration documented
- [ ] Version header updated

#### Issue 0.0.2: Create P03 Pipeline Contract and README

> **K0 Architecture Discovery** (Based on actual K0 codebase):
>
> K0 uses a **YAML-first declarative pipeline architecture**:
>
> - **Pipeline Contracts**: `k0/contracts/pipelines/*.yaml` define pipeline DAGs
> - **Module Contracts**: `k0/contracts/modules/*.yaml` define module interfaces
> - **Module Implementations**: `k0/modules/<domain>/<module>.py` contain async `run()` functions
> - **Pipeline Runner**: `k0/runtime/pipeline_runner.py` executes DAGs by orchestrating modules
> - **Module Registry**: `k0/runtime/module_registry.py` loads contracts and resolves modules
>
> **NO Python pipeline files in `k0/pipelines/`** - that folder contains loader, protocol, and docs only.

**Files to Create**:

1. **Pipeline Contract**: `k0/contracts/pipelines/p03_consolidation.v1.yaml`
2. **Pipeline README**: `k0/pipelines/p03_consolidation_README.md`

---

**File 1: Pipeline Contract YAML** (`k0/contracts/pipelines/p03_consolidation.v1.yaml`)

**What to Cover** (following P02 pattern from `p02_write.v1.yaml`):

```yaml
# P03 Consolidation Pipeline: Memory Consolidation (Sleep Cycle)
# Purpose: Transform st_hipp_events → 8 truth layers via bidirectional reconciliation
# Owner: Intelligence Kernel (K0)
# Status: DESIGN
# ADRs: k010.x (consolidation architecture)

pipeline_id: P03_CONSOLIDATION
version: v1
name: P03 Consolidation - Memory Consolidation
description: |
  Implements neuroscience-inspired sleep cycle consolidation.
  R0-R8 phases transform ephemeral hippocampal events into durable truth.
  Bidirectional reconciliation: new signals are candidates against 8 truth layers.

entry_topic: p03.consolidation.trigger.v1
exit_topic: p03.consolidation.complete.v1
concurrency: 1  # Single-flight per tenant/space
max_queue_depth: 16  # Low queue - consolidation is scheduled, not high-throughput

required_capabilities:
  # Read capabilities
  - st_hipp_events.read
  - st_epi.read
  - st_sem.read
  - st_procedural.read
  - st_social.read
  - st_prospective.read
  - st_kg_dom.read
  - st_kg_edges.read
  - st_vec.read
  # Write capabilities
  - st_epi.write
  - st_sem.write
  - st_procedural.write
  - st_social.write
  - st_prospective.write
  - st_kg_dom.write
  - st_kg_edges.write
  - st_vec.write
  - st_hipp_events.write  # Update consolidation_status
  - st_outbox.write
  - st_pipeline_processed.write
  - st_consolidation_locks.write

dag:
  # R0: Trigger Detection & Lock Acquisition
  - id: r0_trigger
    module: consolidation.trigger:v1
    after: []
    description: Acquire single-flight lock, validate pre-conditions

  # R1: Hippocampal Replay
  - id: r1_replay
    module: consolidation.replay:v1
    after: [r0_trigger]
    description: Batch selection, importance scoring, embedding warm-up

  # R2: Neocortical Integration
  - id: r2_integration
    module: consolidation.integration:v1
    after: [r1_replay]
    description: Episodic clustering, pattern detection, CA1 bridge reconciliation

  # R3/R4 Parallel Group (Synaptic Homeostasis + KG)
  - id: r3_forgetting
    module: consolidation.forgetting:v1
    after: [r2_integration]
    description: Deduplication, novelty scoring, retention enforcement

  - id: r4_knowledge_graph
    module: consolidation.knowledge_graph:v1
    after: [r2_integration]  # Parallel with R3
    description: Entity normalization, relationship discovery, temporal updates

  # R5: Dream (Optional)
  - id: r5_dream
    module: consolidation.dream:v1
    after: [r3_forgetting, r4_knowledge_graph]
    description: Counterfactual simulation, prediction generation (feature-flagged)
    config:
      enabled: false  # Controlled by P03_FF_R5_MODE

  # R6: Staging Updates
  - id: r6_staging
    module: consolidation.staging:v1
    after: [r5_dream]
    description: Mark st_hipp_events consolidated, write reconciliation queue

  # R7: Memory Layer Writes
  - id: r7_writers
    module: consolidation.writers:v1
    after: [r6_staging]
    description: Atomic writes to 8 truth layers via outbox pattern

  # R8: Finalization
  - id: r8_finalization
    module: consolidation.finalization:v1
    after: [r7_writers]
    description: Event emission, offset tracking, lock release, gap detection
```

---

**File 2: Module Contracts** (`k0/contracts/modules/consolidation.*.v1.yaml`)

**What to Cover**: Create 9 module contracts (one per R* phase):

| Module Contract File | Module ID | Purpose |
|---------------------|-----------|---------|
| `consolidation.trigger.v1.yaml` | `consolidation.trigger:v1` | R0 lock acquisition |
| `consolidation.replay.v1.yaml` | `consolidation.replay:v1` | R1 batch selection |
| `consolidation.integration.v1.yaml` | `consolidation.integration:v1` | R2 clustering |
| `consolidation.forgetting.v1.yaml` | `consolidation.forgetting:v1` | R3 deduplication |
| `consolidation.knowledge_graph.v1.yaml` | `consolidation.knowledge_graph:v1` | R4 KG updates |
| `consolidation.dream.v1.yaml` | `consolidation.dream:v1` | R5 optional |
| `consolidation.staging.v1.yaml` | `consolidation.staging:v1` | R6 status updates |
| `consolidation.writers.v1.yaml` | `consolidation.writers:v1` | R7 truth writes |
| `consolidation.finalization.v1.yaml` | `consolidation.finalization:v1` | R8 events |

Each contract follows `hippocampus.pattern_separate.v1.yaml` template with:

- `module_id`, `version`
- `input_event_types`, `output_event_types`
- `latency_budget_ms` (from dossier phase budgets)
- `side_effects` (storage read/write)
- `idempotent: true/false`
- `failure_modes` with retry policies
- `config_schema`

---

**File 3: Module Implementations** (`k0/modules/consolidation/*.py`)

**Directory Structure**:

```
k0/modules/consolidation/
├── __init__.py
├── README.md                    # Module family overview
├── trigger.py                   # R0: async def run(message, context, **config)
├── replay.py                    # R1: async def run(...)
├── integration.py               # R2: async def run(...)
├── forgetting.py                # R3: async def run(...)
├── knowledge_graph.py           # R4: async def run(...)
├── dream.py                     # R5: async def run(...)
├── staging.py                   # R6: async def run(...)
├── writers.py                   # R7: async def run(...)
└── finalization.py              # R8: async def run(...)
```

Each module follows `k0/modules/hippocampus/pattern_separate.py` pattern:

```python
"""
M18: consolidation.trigger - R0 Trigger Detection

Lock acquisition, pre-flight checks, cycle initialization.
Contract: k0/contracts/modules/consolidation.trigger.v1.yaml
"""

async def run(message: Any, context: Any, **config) -> dict[str, Any]:
    """Phase 2 module entry point."""
    # Implementation...
    return {"cycle_id": "...", "lock_acquired": True, ...}
```

---

**File 4: Pipeline README** (`k0/pipelines/p03_consolidation_README.md`)

**What to Cover** (14-Section Template):

1. **Overview**: Memory consolidation pipeline implementing bidirectional truth reconciliation
2. **Purpose**: Transform P02 episodic signals into durable truth across 8 memory layers
3. **Architecture**: R0-R8 phase model with brain-analog mapping
4. **Dependencies**: P02 (upstream), P08 (embedding), P06 (downstream)
5. **Input Contract**: st_hipp_events consumption, offset tracking
6. **Output Contract**: 8 truth tables + event emissions
7. **Configuration**: Trigger types, phase budgets, feature flags
8. **Phase Specifications**: Summary of R0-R8 with latency budgets
9. **Module Registry**: M18-M25 (P03-specific modules in `k0/modules/consolidation/`)
10. **Storage Tables**: 10+ tables created/updated by P03
11. **Events Emitted**: 8 event topics for downstream pipelines
12. **Observability**: Metrics, traces, logs specifications
13. **Testing**: Test categories and coverage expectations
14. **ADR References**: Links to k010.x ADRs

---

**Acceptance Criteria**:

- [ ] Pipeline contract YAML created at `k0/contracts/pipelines/p03_consolidation.v1.yaml`
- [ ] 9 module contracts created at `k0/contracts/modules/consolidation.*.v1.yaml`
- [ ] Module directory created at `k0/modules/consolidation/`
- [ ] Each module has `async def run(message, context, **config)` signature
- [ ] Pipeline README follows 14-section template
- [ ] PipelineRunner can load and execute the DAG (integration test)

---

### Epic 0.1: Architectural Decision Records

> **Location**: `docs/architecture/decisions-K0/`
> **Naming Pattern**: `k010-*` for P03 decisions
> **Template**: Follow existing ADR format in repository

#### Issue 0.1.1: Create ADR k010 - P03 Consolidation Architecture

**File**: `docs/architecture/decisions-K0/k010-p03-consolidation-architecture.md`

**What to Cover**:

1. **Context**:
   - P03 is the memory consolidation pipeline in K0
   - Inspired by neuroscience sleep cycle model (NREM/REM phases)
   - Transforms ephemeral st_hipp_events into durable truth
   - v2 introduces bidirectional reconciliation

2. **Decision**:
   - Adopt 9-phase model (R0-R8) mapped to brain regions
   - Target cycle budget: 90 minutes (excluding R5)
   - Make R5 (Dream) optional via feature flag
   - Use capability-based security (28 capabilities)

3. **Consequences**:
   - Phases are sequential with R3/R4 parallelizable
   - Each phase has explicit latency budget
   - K0 scheduler manages trigger detection
   - Four integration points: P02, P08, P06, P04

4. **Alternatives Considered**:
   - Single-phase batch processing (rejected: too monolithic)
   - Real-time streaming consolidation (rejected: resource intensive)
   - 3-phase simplified model (rejected: loses neuroscience benefits)

**Cross-References**:

- Dossier Section 1: Core Philosophy
- Dossier Section 2: Neuroscience Foundation
- Dossier Section 3: Architectural Overview

#### Issue 0.1.2: Create ADR k010.1 - Sleep Cycle Scheduling Model

**File**: `docs/architecture/decisions-K0/k010.1-sleep-cycle-scheduling.md`

**What to Cover**:

1. **Context**:
   - Consolidation is resource-intensive, should run during idle
   - Multiple trigger types needed (user idle, scheduled, backlog)
   - Concurrent cycles on same space cause conflicts

2. **Decision**:
   - Four trigger types with priority ordering:
     1. MANUAL (highest) - Admin override
     2. THRESHOLD - Backlog > 5000 events
     3. CRON - Daily at 2:00 AM local
     4. IDLE (lowest) - 30+ min inactivity
   - State machine: IDLE → TRIGGERED → ACQUIRING_LOCK → RUNNING → COMPLETING → IDLE
   - Single-flight gate: Only one cycle per tenant/space at a time

3. **Lock Acquisition Protocol**:
   - Lock key: `p03:{tenant_id}:{space_id}`
   - TTL: 120 minutes (2x expected cycle time)
   - Heartbeat: Every 60 seconds during cycle
   - Stale lock cleanup: 5 minutes after TTL expiry

4. **Consequences**:
   - Pre-flight checks before lock acquisition
   - Graceful handling of lock contention
   - Metrics for trigger frequency by type

**Cross-References**:

- Dossier Section 4.1: R0 — Trigger Detection
- Dossier Appendix G: State Machine Specification

#### Issue 0.1.3: Create ADR k010.2 - Importance Scoring Formula

**File**: `docs/architecture/decisions-K0/k010.2-importance-scoring.md`

**What to Cover**:

1. **Context**:
   - R1 (Replay) phase needs to score event importance
   - Determines which events get more processing attention
   - Based on neuroscience memory consolidation research

2. **Decision - Formula**:

   ```
   importance = 0.35 × emotional_salience
              + 0.25 × recency_score
              + 0.20 × access_frequency
              + 0.20 × social_significance
   ```

3. **Component Definitions**:
   - `emotional_salience`: Derived from P02 sentiment + affect scores
   - `recency_score`: Exponential decay from event_time_utc
   - `access_frequency`: Query count from st_usage_log (future)
   - `social_significance`: num_participants × participant_weights

4. **Tuning Parameters**:
   - All weights configurable via feature flags
   - Decay half-life for recency: 7 days (default)
   - Minimum importance threshold for processing: 0.1

5. **Consequences**:
   - High emotional events prioritized
   - Recent events weighted higher
   - Social events get attention boost

**Cross-References**:

- Dossier Section 2.4: Scientific Formulas
- Dossier Section 4.2: R1 — Hippocampal Replay

#### Issue 0.1.4: Create ADR k010.3 - Episodic Clustering Algorithm

**File**: `docs/architecture/decisions-K0/k010.3-episodic-clustering.md`

**What to Cover**:

1. **Context**:
   - R2 groups related events into episodes
   - Events may span hours/days but share context
   - Need efficient clustering at scale (10K+ events)

2. **Decision - Algorithm: DBSCAN**:
   - Distance metric: Cosine distance on 384-dim embeddings
   - eps (neighborhood radius): 0.3 (cosine distance)
   - min_samples: 2 (minimum cluster size)
   - Pre-filtering: SimHash Hamming distance ≤ 3

3. **Composite Distance Function**:

   ```
   distance = 0.60 × embedding_distance
            + 0.20 × temporal_distance
            + 0.10 × entity_overlap_distance
            + 0.10 × location_distance
   ```

4. **Temporal Bucketing**:
   - 4-hour windows for initial grouping
   - Cross-window merging if distance < eps

5. **Consequences**:
   - O(n log n) complexity with spatial indexing
   - Handles noise (outliers become single-event episodes)
   - Clusters may span multiple temporal buckets

**Cross-References**:

- Dossier Section 4.3: R2 — Neocortical Integration
- Dossier Appendix C.3: R2 Episodic Integration Algorithms

#### Issue 0.1.5: Create ADR k010.4 - Bidirectional Truth Reconciliation

**File**: `docs/architecture/decisions-K0/k010.4-bidirectional-reconciliation.md`

**What to Cover**:

1. **Context** (CRITICAL ADR):
   - v1 was one-way: new data overwrites truth
   - v2 recognizes 8 memory layers as TRUTH
   - New signals are CANDIDATES that must reconcile

2. **Decision - 6 Reconciliation Actions**:

   | Action | Condition | Truth Update |
   |--------|-----------|--------------|
   | REINFORCE | High similarity (>0.85), same meaning | confidence++, observation_count++ |
   | EXTEND | Moderate similarity (0.6-0.85), adds detail | Add new attributes, link sources |
   | CREATE | Low similarity (<0.6), novel information | Insert new truth record |
   | EVOLVE | Pattern drift detected | Create new version, supersede old |
   | CONTRADICT | Conflicts with existing truth | Flag for P06 clarification |
   | SUPERSEDE | Replaces obsolete truth | Archive old, create new |

3. **Similarity Calculation**:

   ```
   similarity = 0.40 × embedding_cosine_sim
              + 0.25 × simhash_similarity
              + 0.15 × entity_overlap
              + 0.10 × temporal_proximity
              + 0.10 × spatial_proximity
   ```

4. **Truth Query Pattern** (CA1 Bridge):
   - For each new signal, query all 8 truth layers
   - Compare against existing patterns, episodes, entities
   - Collect matches above threshold (0.4)
   - Apply decision matrix based on best match

5. **Consequences**:
   - Truth is never blindly overwritten
   - Contradictions surfaced to user via P06
   - Version history maintained via supersedes_id

**Cross-References**:

- Dossier Section 1: Core Philosophy
- Dossier Section 4.3.3: CA1 Bridge (Truth Query)
- Dossier Appendix C.1: Core Reconciliation Algorithms

#### Issue 0.1.6: Create ADR k010.5 - Near-Duplicate Detection (SimHash)

**File**: `docs/architecture/decisions-K0/k010.5-simhash-deduplication.md`

**What to Cover**:

1. **Context**:
   - R3 (Forgetting) needs to identify near-duplicates
   - Exact matching insufficient (rephrased content)
   - Must scale to 100K+ events per cycle

2. **Decision - SimHash Algorithm**:
   - 64-bit fingerprint per event
   - Computed from: content_text + entities + temporal_bucket
   - Hamming distance threshold: ≤ 3 bits = near-duplicate

3. **Pre-Computation in P02**:
   - SimHash computed during P02 ingestion
   - Stored in st_hipp_events.simhash_hex column
   - P03 only needs to compare, not compute

4. **LSH for Scale**:
   - Locality-Sensitive Hashing for O(1) lookup
   - Band-based bucketing (4 bands × 16 bits)
   - Candidate pairs filtered by exact Hamming distance

5. **Consequences**:
   - Near-duplicates flagged before clustering
   - Reduces R2 workload (fewer events to cluster)
   - novelty_score inversely related to duplicate count

**Cross-References**:

- Dossier Section 4.4: R3 — Synaptic Homeostasis
- Dossier Appendix C.4: R3 Forgetting Algorithms

#### Issue 0.1.7: Create ADR k010.6 - Entity Normalization Strategy

**File**: `docs/architecture/decisions-K0/k010.6-entity-normalization.md`

**What to Cover**:

1. **Context**:
   - R4 updates knowledge graph with entities
   - P02 already extracted entities via UltraBERT NER
   - P03 must NOT call NER model again

2. **Decision - P02 Data Consumption**:
   - Use st_hipp_events.entities_json (pre-computed)
   - 9 general entity types + 12 family-specific types
   - P03 normalizes, deduplicates, and merges

3. **Normalization Pipeline**:
   1. Parse entities_json array
   2. Canonical name resolution (lowercase, trim, normalize)
   3. Alias detection (Levenshtein distance > 0.85)
   4. Merge duplicates (same canonical name)
   5. Update observation_count on existing entities

4. **Entity Type Hierarchy**:
   - General: PERSON, LOCATION, ORGANIZATION, EVENT, DATE, TIME, QUANTITY, MISC, PRODUCT
   - Family: FAMILY_MEMBER, CHILD, PARENT, SIBLING, GRANDPARENT, GRANDCHILD, UNCLE_AUNT, COUSIN, IN_LAW, PET, FRIEND, COLLEAGUE

5. **Consequences**:
   - No model inference in P03 (CPU-only)
   - Depends on P02 UltraBERT quality
   - Alias resolution may need P06 clarification

**Cross-References**:

- Dossier Section 4.5: R4 — Knowledge Graph Consolidation
- Dossier Appendix H: UltraBERT Model Specification

#### Issue 0.1.8: Create ADR k010.7 - 8-Layer Memory Write Coordination

**File**: `docs/architecture/decisions-K0/k010.7-memory-layer-writes.md`

**What to Cover**:

1. **Context**:
   - R7 writes to 8 memory layers
   - Writes must be atomic and durable
   - Downstream pipelines need reliable event delivery

2. **Decision - Outbox Pattern**:
   1. Within single DB transaction:
      - Write to target truth table (st_epi, st_sem, etc.)
      - Insert event record into st_outbox
   2. Commit transaction
   3. Background worker publishes st_outbox → event bus
   4. Mark outbox record as published

3. **Write Order**:
   1. st_epi (episodes)
   2. st_sem (patterns)
   3. st_procedural (habits)
   4. st_social (relationships)
   5. st_prospective (intentions)
   6. st_kg_dom (entities)
   7. st_kg_edges (relationships)
   8. st_vec (embedding placeholders)

4. **Version Handling**:
   - Each write checks current version
   - Optimistic concurrency via version increment
   - Conflict → retry with fresh read

5. **Consequences**:
   - At-least-once event delivery guaranteed
   - PostgreSQL supports cross-table transactions within UoW
   - Ordering preserved within layer, not across

**Cross-References**:

- Dossier Section 4.8: R7 — Memory Layer Writes
- Dossier Section 6.15: st_outbox (Durable Writes)

#### Issue 0.1.9: Create ADR k010.8 - P08 Embedding Coordination

**File**: `docs/architecture/decisions-K0/k010.8-p08-embedding-coordination.md`

**What to Cover**:

1. **Context**:
   - P03 needs embeddings for similarity search (R1, R4)
   - P08 manages embedding lifecycle and FAISS index
   - Must avoid deprecated st_embedding_queue

2. **Decision - st_vec Integration**:
   - Query existing embeddings via st_vec.status = 'COMPLETED'
   - For new content, insert st_vec placeholder with status = 'PENDING'
   - Emit `p08.embedding.requested.v1` event
   - P08 fills embedding_384, faiss_id, sets status = 'COMPLETED'

3. **Backpressure Mechanism**:
   - Check st_vec pending count before cycle
   - Threshold: 10,000 pending = warn, 50,000 = defer
   - Circuit breaker on P08 availability

4. **Embedding Batching**:
   - Batch embedding requests (100 at a time)
   - Use embedding cache with 1-hour TTL
   - Pre-warm cache with recent 24h embeddings

5. **Consequences**:
   - No direct FAISS manipulation in P03
   - Async embedding may delay first query result
   - Circuit breaker prevents cascade failure

**Cross-References**:

- Dossier Section 9.4: P03 → P08 Contract
- Dossier Section 13.6: Circuit Breaker Configuration

#### Issue 0.1.10: Create ADR k010.9 - Capability-Based Security Model

**File**: `docs/architecture/decisions-K0/k010.9-capability-security.md`

**What to Cover**:

1. **Context**:
   - P03 accesses 10+ tables with mixed read/write
   - K0 capability fabric enforces least-privilege
   - Must declare all capabilities upfront

2. **Decision - 28 Capabilities**:
   - 10 database read capabilities (st_hipp_events, st_epi, etc.)
   - 10 database write capabilities
   - 3 bus capabilities (emit, consume)
   - 2 lock capabilities (acquire, release)
   - 3 observability capabilities (metrics, traces, logs)

3. **Capability Acquisition**:
   - Declared in pipeline YAML contract
   - K0 CapabilityFabric grants on pipeline init
   - Runtime checks on every operation

4. **Principle of Least Privilege**:
   - Each phase only gets capabilities it needs
   - R1 has read-only access to truth tables
   - R7 has write access to all truth tables

5. **Consequences**:
   - Security auditable from pipeline contract
   - Missing capability = runtime error (fail-fast)
   - Capability changes require contract update

**Cross-References**:

- Dossier Section 9: Integration Contracts
- Dossier Appendix E.5: Fabric Capabilities

#### Issue 0.1.11: Create ADR k010.10 - P06 Active Learning Integration

**File**: `docs/architecture/decisions-K0/k010.10-p06-active-learning.md`

**What to Cover**:

1. **Context**:
   - P03 detects knowledge gaps during reconciliation
   - Gaps should trigger user questions via P06
   - Questions must respect attention budget

2. **Decision - Gap Detection Points**:
   - R2 (CA1 Bridge): Contradiction, ambiguous entity
   - R3 (Forgetting): Low-confidence patterns
   - R4 (KG): Missing relationships, stale anchors
   - R8 (Finalization): Aggregate gap emission

3. **Gap Types**:
   - CONTRADICTION: Conflicting truth
   - AMBIGUOUS_ENTITY: Unclear reference
   - MISSING_ATTRIBUTE: Incomplete knowledge
   - STRUCTURAL_HOLE: Expected but missing relationship
   - CONCEPT_DRIFT: Pattern has changed

4. **Attention Budget Integration**:
   - Query P05 for current budget before emission
   - Priority score per gap (entropy × 1/confidence × recency)
   - Emit only high-priority gaps if budget low

5. **Event Contract**:
   - `p03.gaps.detected.v1` → P06
   - Payload: gap_type, entity_id, context_json, priority

**Cross-References**:

- Dossier Section 5: P06 Active Learning Integration
- Dossier Section 9.3: P03 → P06 Contract

#### Issue 0.1.12: Create ADR k010.11 - UltraBERT Data Consumption

**File**: `docs/architecture/decisions-K0/k010.11-ultrabert-consumption.md`

**What to Cover**:

1. **Context**:
   - UltraBERT v2.2.1 provides 12 NLP capabilities
   - P02 runs UltraBERT during ingestion
   - P03 consumes pre-computed outputs (NO model calls)

2. **Decision - P02 Output Consumption**:

   | P02 Column | UltraBERT Encoder | P03 Usage |
   |------------|-------------------|-----------|
   | embedding_384 | base_encoder | Similarity search |
   | simhash_hex | simhash_encoder | Duplicate detection |
   | entities_json | ner_encoder | KG updates |
   | sentiment_score | sentiment_encoder | Importance scoring |
   | salience_score | salience_encoder | Importance scoring |
   | affect_valence | affect_encoder | Emotional weighting |
   | affect_arousal | affect_encoder | Emotional weighting |
   | topics_json | topic_encoder | Pattern extraction |
   | summary_text | summary_encoder | Episode descriptions |

3. **Model Call Prohibition**:
   - P03 MUST NOT import UltraBERT
   - All NLP features pre-computed in P02
   - Missing data = skip event, do not fill

4. **Version Compatibility**:
   - P03 requires P02 with UltraBERT v2.2.1+
   - Schema validation on st_hipp_events columns
   - Missing columns = fail-fast on startup

**Cross-References**:

- Dossier Appendix H: UltraBERT Model Specification
- Dossier Section 9.2: P02 → P03 Contract

#### Issue 0.1.13: Update K0 ADR Index with All k010.x ADRs

**File**: `k0/pipelines/k0_architecture_master.md` (Part 7.1)

**What to Cover**:

1. **Add 12 ADR Entries to Index**:

   | ADR ID | Title | Status | Pipeline |
   |--------|-------|--------|----------|
   | k010 | P03 Consolidation Architecture | PROPOSED | P03 |
   | k010.1 | Sleep Cycle Scheduling | PROPOSED | P03 |
   | k010.2 | Importance Scoring Formula | PROPOSED | P03 |
   | k010.3 | Episodic Clustering Algorithm | PROPOSED | P03 |
   | k010.4 | Bidirectional Truth Reconciliation | PROPOSED | P03 |
   | k010.5 | Near-Duplicate Detection (SimHash) | PROPOSED | P03 |
   | k010.6 | Entity Normalization Strategy | PROPOSED | P03 |
   | k010.7 | 8-Layer Memory Write Coordination | PROPOSED | P03 |
   | k010.8 | P08 Embedding Coordination | PROPOSED | P03 |
   | k010.9 | Capability-Based Security Model | PROPOSED | P03 |
   | k010.10 | P06 Active Learning Integration | PROPOSED | P03 |
   | k010.11 | UltraBERT Data Consumption | PROPOSED | P03 |

2. **Cross-Reference Updates**:
   - Link each ADR to relevant dossier sections
   - Link to related P02, P08 ADRs if exist

3. **Status Workflow**:
   - PROPOSED → ACCEPTED (after review)
   - ACCEPTED → IMPLEMENTED (after M1)

**Acceptance Criteria**:

- [ ] All 12 ADRs listed in Part 7.1
- [ ] Each ADR has correct status
- [ ] Cross-references complete

---

### Epic 0.2: Resolve Architectural Blockers

> **Reference**: Critical Blockers table at top of document
> **Purpose**: Resolve blocking issues before implementation can proceed

#### Issue 0.2.1: Design Consolidation Lock Mechanism

**What to Cover**:

1. **Problem Statement**:
   - Multiple P03 cycles could start for same tenant/space
   - Without locking, concurrent writes corrupt truth tables
   - K0 lacks native distributed lock primitive

2. **Lock Table Design** (st_consolidation_locks):

   ```sql
   CREATE TABLE st_consolidation_locks (
     lock_id TEXT PRIMARY KEY,
     tenant_id TEXT NOT NULL,
     space_id TEXT NOT NULL,
     holder_id TEXT NOT NULL,  -- Instance UUID
     acquired_at INTEGER NOT NULL,
     expires_at INTEGER NOT NULL,
     heartbeat_at INTEGER NOT NULL,
     cycle_id TEXT,
     UNIQUE(tenant_id, space_id)
   );
   ```

3. **Lock Acquisition Protocol**:
   - Attempt INSERT with UNIQUE constraint
   - If conflict, check if existing lock expired
   - If expired, DELETE + INSERT (CAS pattern)
   - If not expired, return LOCK_HELD

4. **Lock Lifecycle**:
   - TTL: 120 minutes (2x expected cycle)
   - Heartbeat: Every 60 seconds
   - Stale cleanup: Background job every 5 minutes

5. **Granularity Decision**:
   - Per tenant/space (not per tenant only)
   - Allows parallel consolidation across spaces
   - Single writer per space guaranteed

**Acceptance Criteria**:

- [ ] Lock table schema defined
- [ ] Acquisition/release protocol documented
- [ ] Stale lock cleanup procedure defined
- [ ] Unit test scenarios listed

#### Issue 0.2.2: Resolve Budget Mismatch (182 min vs 90 min)

**What to Cover**:

1. **Problem Statement**:
   - Phase budgets sum to 182 minutes:
     - R0: 1 min, R1: 15 min, R2: 20 min, R3: 10 min
     - R4: 25 min, R5: 20 min, R6: 10 min, R7: 10 min, R8: 5 min
   - Target SLO: 90 minutes per cycle
   - Need 50% reduction

2. **Solution 1: Make R5 Optional**:
   - R5 (Dream) is exploratory, not critical path
   - Feature flag: `dream_phase_enabled = false` (default)
   - Savings: 20 minutes

3. **Solution 2: Parallelize R3/R4**:
   - R3 (Forgetting) and R4 (KG) are independent
   - Can run concurrently after R2 completes
   - Combined: max(10, 25) = 25 min vs 35 min sequential
   - Savings: 10 minutes

4. **Solution 3: Optimize R2 Clustering**:
   - Pre-filter with SimHash before DBSCAN
   - Reduce effective event count by 30%
   - Potential savings: 6 minutes (30% of 20)

5. **Revised Budget**:

   | Phase | Original | Optimized | Savings |
   |-------|----------|-----------|---------|
   | R0 | 1 | 1 | 0 |
   | R1 | 15 | 15 | 0 |
   | R2 | 20 | 14 | 6 |
   | R3+R4 | 35 | 25 | 10 |
   | R5 | 20 | 0 (skipped) | 20 |
   | R6 | 10 | 10 | 0 |
   | R7 | 10 | 10 | 0 |
   | R8 | 5 | 5 | 0 |
   | **Total** | **116** | **80** | **36** |

6. **Consequence**:
   - 80 min without R5 (within 90 min SLO)
   - 100 min with R5 (11% over SLO, acceptable for optional phase)

**Acceptance Criteria**:

- [ ] R5 feature flag documented
- [ ] Parallel group configuration defined
- [ ] R2 optimization approach validated
- [ ] Revised budget approved

#### Issue 0.2.3: Design P08 Backpressure Mechanism

**What to Cover**:

1. **Problem Statement**:
   - P03 requests embeddings from P08
   - If P08 queue is full, requests pile up
   - Cascade failure possible without backpressure

2. **Queue Depth Monitoring**:

   ```sql
   SELECT COUNT(*) FROM st_vec
   WHERE status = 'PENDING'
     AND tenant_id = :tenant_id;
   ```

3. **Threshold Configuration**:

   | Pending Count | Action |
   |---------------|--------|
   | < 10,000 | Normal operation |
   | 10,000 - 49,999 | Log warning, reduce batch size |
   | ≥ 50,000 | Defer cycle, emit alert |

4. **Circuit Breaker for P08**:
   - Failure threshold: 5 consecutive failures
   - Success threshold: 2 successes to close
   - Timeout: 30 seconds per request
   - Half-open max calls: 3

5. **Pre-Flight Check in R0**:
   - Before acquiring lock, check P08 queue depth
   - If above threshold, skip this trigger
   - Log: "P08 backpressure detected, deferring consolidation"

6. **Fallback Behavior**:
   - If P08 unavailable, use cached embeddings
   - If no cache, mark events as DEFERRED (retry next cycle)
   - Never block on P08 indefinitely

**Acceptance Criteria**:

- [ ] Queue depth query defined
- [ ] Thresholds documented
- [ ] Circuit breaker config specified
- [ ] Pre-flight check added to R0

#### Issue 0.2.4: Validate P02 st_hipp_events Schema Alignment

**What to Cover**:

1. **Problem Statement**:
   - P03 consumes st_hipp_events from P02
   - Schema must include all P03-required columns
   - Mismatch causes runtime failures

2. **Required Columns** (from P02):

   | Column | Type | P03 Usage |
   |--------|------|-----------|
   | event_id | TEXT | Primary key, tracking |
   | tenant_id | TEXT | Multi-tenancy |
   | space_id | TEXT | Partition key |
   | event_time_utc | INTEGER | Ordering, recency |
   | content_text | TEXT | Display, summarization |
   | embedding_384 | BLOB | Similarity search |
   | simhash_hex | TEXT | Duplicate detection |
   | entities_json | TEXT | KG updates |
   | sentiment_score | REAL | Importance scoring |
   | salience_score | REAL | Importance scoring |
   | affect_valence | REAL | Emotional weighting |
   | affect_arousal | REAL | Emotional weighting |
   | topics_json | TEXT | Pattern extraction |

3. **Consolidation Columns** (P03 writes):

   | Column | Type | Purpose |
   |--------|------|---------|
   | consolidation_status | TEXT | PENDING/COMPLETED/DEFERRED |
   | episode_cluster_id | TEXT | Assigned cluster |
   | novelty_score | REAL | Duplicate detection result |
   | reconciliation_decision | TEXT | REINFORCE/EXTEND/CREATE/etc |

4. **Validation Query**:

   ```sql
   PRAGMA table_info(st_hipp_events);
   -- Verify all required columns exist
   ```

5. **Migration Dependency**:
   - P02 migration must run before P03
   - Version check: st_hipp_events schema version ≥ 2.0

**Acceptance Criteria**:

- [ ] Required columns list finalized
- [ ] Validation query implemented
- [ ] Version compatibility documented
- [ ] P02 team confirmed alignment

---

### Epic 0.3: K0 Kernel Enhancement ADRs

> **Reference**: Dossier Section 4.10 - K0 Kernel Enhancements Required
> **Purpose**: Create ADRs for K0 kernel enhancements required before P03 implementation
> **Gate**: GATE 1 (Architectural Decision Validation)
> **Note**: These ADRs MUST be ACCEPTED before proceeding to Epic 0.4-0.7 implementations.

#### Issue 0.3.1: Create ADR k011 - K0 Advisory Lock Service

**File**: `docs/architecture/decisions-K0/k011-advisory-lock-service.md`

**What to Cover**:

1. **Context**:
   - K0 lacks distributed locking primitive
   - P03 needs single-writer semantics per tenant/space
   - Other pipelines (P07 CRDT, P08 Embedding) need similar capability
   - **PostgreSQL Migration (2025-01)**: Native advisory locks now available

2. **Decision**:
   - Create `k0/sync/advisory_lock.py` with `AdvisoryLockService` class
   - **PostgreSQL-based implementation using `pg_advisory_lock()` / `pg_try_advisory_lock()`**
   - Lock key pattern: `{pipeline_id}:{tenant_id}:{space_id}` → hashed to bigint
   - Session-scoped or transaction-scoped locks (configurable)
   - Multi-node safe (PostgreSQL handles coordination)

3. **API Design**:

   ```python
   @dataclass
   class LockResult:
       acquired: bool
       lock_id: str | None
       holder_id: str | None
       expires_at: datetime | None
       error: str | None

   class AdvisoryLockService(Protocol):
       async def acquire(self, lock_key: str, holder_id: str, ttl_seconds: int = 300) -> LockResult
       async def release(self, lock_key: str, holder_id: str) -> bool
       async def heartbeat(self, lock_key: str, holder_id: str, extend_seconds: int = 60) -> bool
       async def is_held(self, lock_key: str) -> LockInfo | None
       async def force_release(self, lock_key: str, reason: str) -> bool  # Admin only
   ```

4. **Backend**:
   - **PostgreSQL native using `pg_advisory_lock()` functions**
   - Session locks: `pg_advisory_lock(key)` / `pg_advisory_unlock(key)`
   - Transaction locks: `pg_advisory_xact_lock(key)` (auto-release on commit/rollback)
   - Try variants: `pg_try_advisory_lock(key)` returns boolean immediately

5. **Consequences**:
   - P03, P07, P08 can use same locking primitive
   - **Multi-node safe** (PostgreSQL coordinates across connections)
   - No cleanup needed for transaction-scoped locks (auto-release)
   - Session locks require explicit release or connection close

**Cross-References**:

- Dossier Section 4.10.2: Advisory Lock Service
- Issue 0.4.1: Implementation

**Acceptance Criteria**:

- [ ] ADR created with full context and alternatives
- [ ] API design reviewed by K0 team
- [ ] Backend selection strategy documented
- [ ] ADR status: ACCEPTED

#### Issue 0.3.2: Create ADR k012 - Partitioned Pipeline Execution

**File**: `docs/architecture/decisions-K0/k012-partitioned-pipeline-execution.md`

**What to Cover**:

1. **Context**:
   - PipelineScheduler triggers pipelines globally
   - No native support for partition-aware execution
   - P03 consolidation should run independently per space
   - Horizontal scaling blocked without partitioning

2. **Decision**:
   - Extend `ScheduledPipeline` with partition configuration
   - Add `PartitionStrategy` enum: NONE, TENANT, SPACE, CONSISTENT_HASH
   - Partition discovery via `get_partitions()` callback
   - Each partition runs independently with own trigger state

3. **API Design**:

   ```python
   class PartitionStrategy(Enum):
       NONE = "none"              # Current behavior (global)
       TENANT = "tenant"          # One partition per tenant
       SPACE = "space"            # One partition per tenant:space
       CONSISTENT_HASH = "hash"   # Distribute across N nodes

   @dataclass
   class PartitionConfig:
       strategy: PartitionStrategy
       partition_key_template: str  # e.g., "{tenant_id}:{space_id}"
       discover_partitions: Callable[[], list[str]]  # Returns partition keys
       node_affinity: str | None  # For consistent hashing

   @dataclass
   class ScheduledPipeline:
       # Existing fields...
       partition_config: PartitionConfig | None = None
   ```

4. **Execution Model**:
   - `NONE`: Current behavior, single global execution
   - `TENANT`: One concurrent execution per tenant
   - `SPACE`: One concurrent execution per tenant:space (P03 uses this)
   - `CONSISTENT_HASH`: Partitions assigned to nodes via hash ring

5. **Consequences**:
   - P03 can consolidate multiple spaces in parallel
   - Each partition has independent trigger state
   - Requires partition discovery mechanism

**Cross-References**:

- Dossier Section 4.10.3: Partitioned Pipeline Execution
- Issue 0.5.1: Implementation

**Acceptance Criteria**:

- [ ] ADR created with partition strategy comparison
- [ ] Consistent hashing algorithm specified
- [ ] Partition discovery interface defined
- [ ] ADR status: ACCEPTED

#### Issue 0.3.3: Create ADR k013 - Optimistic Concurrency in UnitOfWork

**File**: `docs/architecture/decisions-K0/k013-optimistic-concurrency-uow.md`

**What to Cover**:

1. **Context**:
   - UnitOfWork provides transaction boundaries
   - No built-in version-based conflict detection
   - P03 R7 writes need version checking for truth tables
   - Pattern duplicated across pipelines

2. **Decision**:
   - Add `execute_with_version_check()` method to UnitOfWork
   - Return structured result with conflict detection
   - Support automatic retry with backoff

3. **API Design**:

   ```python
   @dataclass
   class VersionedWriteResult:
       rows_affected: int
       version_conflict: bool
       new_version: int | None
       should_retry: bool
       retry_delay_ms: int

   class UnitOfWork:
       async def execute_with_version_check(
           self,
           sql: str,
           params: tuple,
           version_column: str = "version",
           max_retries: int = 3,
           backoff_base_ms: int = 100
       ) -> VersionedWriteResult:
           """
           Execute SQL with optimistic concurrency control.

           The SQL must include:
           - UPDATE ... SET version = version + 1 ... WHERE version = :expected
           - Or INSERT with version = 1

           Returns conflict info and retry guidance.
           """
   ```

4. **Retry Strategy**:
   - Exponential backoff: 100ms, 200ms, 400ms
   - Max 3 retries before raising `VersionConflictError`
   - Caller can disable retry via `max_retries=0`

5. **Consequences**:
   - Consistent pattern across all pipelines
   - Automatic retry reduces boilerplate
   - Version column required in truth tables

**Cross-References**:

- Dossier Section 4.10.4: Optimistic Concurrency
- Issue 0.6.1: Implementation

**Acceptance Criteria**:

- [ ] ADR created with retry strategy analysis
- [ ] Integration with existing UnitOfWork documented
- [ ] Error handling patterns specified
- [ ] ADR status: ACCEPTED

#### Issue 0.3.4: Create ADR k014 - Pipeline Execution Context

**File**: `docs/architecture/decisions-K0/k014-pipeline-execution-context.md`

**What to Cover**:

1. **Context**:
   - Pipelines need access to node identity for distributed coordination
   - Partition assignment must be available at runtime
   - Current PipelineContext lacks cluster awareness

2. **Decision**:
   - Extend PipelineContext with node and partition information
   - Add cluster membership discovery
   - Provide partition assignment at execution time

3. **API Design**:

   ```python
   @dataclass
   class NodeInfo:
       node_id: str              # Unique identifier (ULID)
       hostname: str             # Network hostname
       started_at: datetime      # Node start time
       version: str              # K0 version

   @dataclass
   class PartitionAssignment:
       partitions: list[str]     # Assigned partition keys
       total_nodes: int          # Cluster size
       assignment_version: int   # For rebalancing detection
       assigned_at: datetime     # Assignment timestamp

   @dataclass
   class PipelineContext:
       # Existing fields...
       node_info: NodeInfo
       partition_assignment: PartitionAssignment | None

       def is_my_partition(self, partition_key: str) -> bool:
           """Check if this node should process the partition."""
   ```

4. **Node Discovery**:
   - Single-node: Static `NodeInfo` from environment variables
   - Node ID generated on startup (ULID or UUID)

5. **Consequences**:
   - Pipelines can make partition-aware decisions
   - Enables load balancing across cluster
   - Requires node registry for multi-node

**Cross-References**:

- Dossier Section 4.10.5: Pipeline Execution Context
- Issue 0.7.1: Implementation

**Acceptance Criteria**:

- [ ] ADR created with cluster topology options
- [ ] Node discovery mechanism specified
- [ ] Partition assignment algorithm documented
- [ ] ADR status: ACCEPTED

---

### Epic 0.4: Implement K0 Advisory Lock Service

> **Location**: `k0/sync/`
> **Prerequisite**: ADR k011 ACCEPTED (Issue 0.3.1)
> **Gate**: GATE 3 (Implementation)
> **Priority**: P1 (Critical for P03)

#### Issue 0.4.1: Create Advisory Lock Service Interface

**File**: `k0/sync/advisory_lock.py`

**What to Implement**:

1. **Protocol Definition**:

   ```python
   from dataclasses import dataclass
   from datetime import datetime
   from typing import Protocol

   @dataclass(slots=True)
   class LockResult:
       acquired: bool
       lock_id: str | None
       holder_id: str | None
       expires_at: datetime | None
       error: str | None

   @dataclass(slots=True)
   class LockInfo:
       lock_key: str
       holder_id: str
       acquired_at: datetime
       expires_at: datetime
       heartbeat_at: datetime

   class AdvisoryLockService(Protocol):
       async def acquire(
           self, lock_key: str, holder_id: str, ttl_seconds: int = 300
       ) -> LockResult: ...

       async def release(self, lock_key: str, holder_id: str) -> bool: ...

       async def heartbeat(
           self, lock_key: str, holder_id: str, extend_seconds: int = 60
       ) -> bool: ...

       async def is_held(self, lock_key: str) -> LockInfo | None: ...

       async def force_release(self, lock_key: str, reason: str) -> bool: ...
   ```

2. **Factory Function**:

   ```python
   def create_lock_service(pool: asyncpg.Pool) -> AdvisoryLockService:
       """Create PostgreSQL-based advisory lock service."""
       return PostgresAdvisoryLockService(pool)
   ```

**Acceptance Criteria**:

- [ ] Protocol class defined with all methods
- [ ] LockResult and LockInfo dataclasses created
- [ ] Factory function implemented
- [ ] Type hints complete

#### Issue 0.4.2: Create PostgreSQL Lock Backend

**File**: `k0/sync/backends/postgres_lock.py`

> **PostgreSQL Migration Note** (2025-01): Uses native `pg_advisory_lock()` functions.
> No migration needed - PostgreSQL advisory locks are built-in.

**What to Implement**:

1. **Lock Key Hashing** (string → bigint for pg_advisory_lock):

   ```python
   import hashlib

   def _hash_lock_key(lock_key: str) -> int:
       """Convert string lock key to bigint for pg_advisory_lock."""
       # Use first 8 bytes of SHA256 as signed 64-bit int
       h = hashlib.sha256(lock_key.encode()).digest()[:8]
       return int.from_bytes(h, byteorder='big', signed=True)
   ```

2. **PostgreSQL Implementation**:

   ```python
   class PostgresAdvisoryLockService:
       def __init__(self, pool: asyncpg.Pool):
           self._pool = pool

       async def acquire(
           self, lock_key: str, holder_id: str, ttl_seconds: int = 300
       ) -> LockResult:
           lock_id = _hash_lock_key(lock_key)

           async with self._pool.acquire() as conn:
               # Try to acquire lock (non-blocking)
               acquired = await conn.fetchval(
                   "SELECT pg_try_advisory_lock($1)",
                   lock_id
               )

               if acquired:
                   return LockResult(acquired=True, lock_id=lock_key, holder_id=holder_id)
               return LockResult(acquired=False, lock_id=lock_key, holder_id=None)

       async def acquire_blocking(
           self, lock_key: str, holder_id: str, timeout_ms: int = 30000
       ) -> LockResult:
           lock_id = _hash_lock_key(lock_key)

           async with self._pool.acquire() as conn:
               # Set statement timeout for blocking acquire
               await conn.execute(f"SET statement_timeout = {timeout_ms}")
               try:
                   await conn.execute("SELECT pg_advisory_lock($1)", lock_id)
                   return LockResult(acquired=True, lock_id=lock_key, holder_id=holder_id)
               except asyncpg.QueryCanceledError:
                   return LockResult(acquired=False, lock_id=lock_key, error="timeout")

       async def release(self, lock_key: str, holder_id: str) -> bool:
           lock_id = _hash_lock_key(lock_key)
           async with self._pool.acquire() as conn:
               return await conn.fetchval(
                   "SELECT pg_advisory_unlock($1)",
                   lock_id
               )
   ```

3. **Transaction-Scoped Locks** (auto-release on commit/rollback):

   ```python
   async def acquire_xact(self, lock_key: str) -> bool:
       """Acquire transaction-scoped lock (auto-releases on commit/rollback)."""
       lock_id = _hash_lock_key(lock_key)
       # Must be called within a transaction context
       return await self._conn.fetchval(
           "SELECT pg_try_advisory_xact_lock($1)",
           lock_id
       )
   ```

**Acceptance Criteria**:

- [ ] PostgresAdvisoryLockService implements all Protocol methods
- [ ] Lock key hashing to bigint implemented
- [ ] Both blocking and non-blocking acquire supported
- [ ] Transaction-scoped locks for R7 writes
- [ ] Unit tests for all lock scenarios

#### Issue 0.4.3: Create Lock Service Tests

**File**: `tests/k0/sync/test_advisory_lock.py`

**Test Scenarios**:

1. **Basic Operations**:
   - `test_acquire_new_lock`: Acquire on empty key succeeds
   - `test_acquire_held_lock`: Acquire on held key fails
   - `test_release_held_lock`: Release by holder succeeds
   - `test_release_not_holder`: Release by non-holder fails
   - `test_heartbeat_extends_ttl`: Heartbeat updates expiry

2. **Expiry Scenarios**:
   - `test_acquire_expired_lock`: Can acquire expired lock
   - `test_stale_cleanup`: Cleanup removes old locks

3. **Concurrency**:
   - `test_concurrent_acquire`: Only one wins
   - `test_lock_reentrant`: Same holder can refresh

**Acceptance Criteria**:

- [ ] All test scenarios implemented
- [ ] Tests for PostgreSQL backend
- [ ] Concurrency tests with asyncio
- [ ] 100% coverage on lock service

#### Issue 0.4.4: Integrate Lock Service with Kernel

**Files to Modify**:

1. `k0/kernel/dependencies.py`: Add lock service to DI container
2. `k0/kernel/syscalls.py`: Add `lock_acquire`, `lock_release` syscalls
3. `k0/sync/__init__.py`: Export public API

**Syscall Additions**:

```python
# In k0/kernel/syscalls.py
class Syscalls:
    async def lock_acquire(
        self, lock_key: str, holder_id: str, ttl_seconds: int = 300
    ) -> LockResult:
        """Acquire an advisory lock."""
        return await self._lock_service.acquire(lock_key, holder_id, ttl_seconds)

    async def lock_release(self, lock_key: str, holder_id: str) -> bool:
        """Release an advisory lock."""
        return await self._lock_service.release(lock_key, holder_id)

    async def lock_heartbeat(
        self, lock_key: str, holder_id: str, extend_seconds: int = 60
    ) -> bool:
        """Extend lock TTL."""
        return await self._lock_service.heartbeat(lock_key, holder_id, extend_seconds)
```

**Acceptance Criteria**:

- [ ] Lock service in DI container
- [ ] Syscalls added and documented
- [ ] Integration test with kernel startup
- [ ] README updated with lock service docs

---

### Epic 0.5: Implement K0 Partitioned Pipeline Execution

> **Location**: `k0/scheduler/`
> **Prerequisite**: ADR k012 ACCEPTED (Issue 0.3.2)
> **Gate**: GATE 3 (Implementation)
> **Priority**: P1 (Required for horizontal scaling)

#### Issue 0.5.1: Define Partition Strategy Types

**File**: `k0/scheduler/partitions.py`

**What to Implement**:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

class PartitionStrategy(Enum):
    NONE = "none"              # Global execution (current behavior)
    TENANT = "tenant"          # One partition per tenant
    SPACE = "space"            # One partition per tenant:space
    CONSISTENT_HASH = "hash"   # Distribute across N nodes

@dataclass
class PartitionConfig:
    strategy: PartitionStrategy = PartitionStrategy.NONE
    partition_key_template: str = "{tenant_id}:{space_id}"
    max_concurrent_partitions: int = 10

    # Callback to discover partitions (optional)
    discover_partitions: Callable[[], list[str]] | None = None

    # For consistent hashing
    hash_ring_replicas: int = 100
    node_affinity: str | None = None

@dataclass
class PartitionState:
    partition_key: str
    last_execution: float | None = None
    execution_count: int = 0
    is_running: bool = False

class PartitionDiscovery(Protocol):
    async def get_partitions(self) -> list[str]: ...
```

**Acceptance Criteria**:

- [ ] PartitionStrategy enum created
- [ ] PartitionConfig dataclass with all options
- [ ] PartitionState for tracking per-partition execution
- [ ] PartitionDiscovery protocol defined

#### Issue 0.5.2: Extend ScheduledPipeline with Partition Support

**File**: `k0/scheduler/scheduler.py` (modify existing)

**What to Implement**:

1. **Add partition_config to ScheduledPipeline**:

   ```python
   @dataclass
   class ScheduledPipeline:
       pipeline_id: str
       spec: PipelineSpec
       triggers: list[TriggerEngine] = field(default_factory=list)
       state: PipelineState = PipelineState.REGISTERED
       execution_count: int = 0
       last_execution: float | None = None

       # NEW: Partition support
       partition_config: PartitionConfig | None = None
       partition_states: dict[str, PartitionState] = field(default_factory=dict)
   ```

2. **Update trigger handling for partitions**:

   ```python
   async def _handle_trigger(self, pipeline: ScheduledPipeline, event: TriggerEvent):
       if pipeline.partition_config is None or pipeline.partition_config.strategy == PartitionStrategy.NONE:
           # Current behavior: single global execution
           await self._execute_pipeline(pipeline, event, partition_key=None)
       else:
           # Partitioned execution
           partitions = await self._get_partitions(pipeline)
           for partition_key in partitions:
               if self._should_execute_partition(pipeline, partition_key):
                   asyncio.create_task(
                       self._execute_pipeline(pipeline, event, partition_key)
                   )
   ```

3. **Partition execution gate**:

   ```python
   def _should_execute_partition(self, pipeline: ScheduledPipeline, partition_key: str) -> bool:
       state = pipeline.partition_states.get(partition_key)
       if state and state.is_running:
           return False  # Already running

       # Check max concurrent partitions
       running_count = sum(1 for s in pipeline.partition_states.values() if s.is_running)
       if running_count >= pipeline.partition_config.max_concurrent_partitions:
           return False

       return True
   ```

**Acceptance Criteria**:

- [ ] ScheduledPipeline extended with partition support
- [ ] Backward compatible (NONE strategy = current behavior)
- [ ] Per-partition execution tracking
- [ ] Max concurrent partitions enforced

#### Issue 0.5.3: Implement Consistent Hash Partition Assignment

**File**: `k0/scheduler/hash_ring.py`

**What to Implement**:

```python
import hashlib
from bisect import bisect_left
from dataclasses import dataclass

@dataclass
class HashRingNode:
    node_id: str
    weight: int = 1

class ConsistentHashRing:
    def __init__(self, replicas: int = 100):
        self._replicas = replicas
        self._ring: list[tuple[int, str]] = []  # (hash, node_id)
        self._nodes: dict[str, HashRingNode] = {}

    def add_node(self, node: HashRingNode) -> None:
        for i in range(self._replicas * node.weight):
            key = f"{node.node_id}:{i}"
            h = self._hash(key)
            self._ring.append((h, node.node_id))
        self._ring.sort()
        self._nodes[node.node_id] = node

    def remove_node(self, node_id: str) -> None:
        self._ring = [(h, n) for h, n in self._ring if n != node_id]
        self._nodes.pop(node_id, None)

    def get_node(self, key: str) -> str | None:
        if not self._ring:
            return None
        h = self._hash(key)
        idx = bisect_left(self._ring, (h,))
        if idx == len(self._ring):
            idx = 0
        return self._ring[idx][1]

    def get_partitions_for_node(self, node_id: str, all_partitions: list[str]) -> list[str]:
        return [p for p in all_partitions if self.get_node(p) == node_id]

    @staticmethod
    def _hash(key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
```

**Acceptance Criteria**:

- [ ] ConsistentHashRing implemented
- [ ] Weighted node support
- [ ] Partition assignment is deterministic
- [ ] Unit tests for hash distribution

#### Issue 0.5.4: Add Partition Support to Pipeline YAML Schema

**File**: `k0/runtime/schemas.py` (modify existing)

**What to Implement**:

```python
@dataclass
class PartitionSpec:
    strategy: str = "none"  # none, tenant, space, hash
    key_template: str = "{tenant_id}:{space_id}"
    max_concurrent: int = 10
    hash_replicas: int = 100

@dataclass
class PipelineSpec:
    # Existing fields...
    partition: PartitionSpec | None = None
```

**Example YAML**:

```yaml
# In p03_consolidation.v1.yaml
pipeline_id: P03_CONSOLIDATION
partition:
  strategy: space
  key_template: "{tenant_id}:{space_id}"
  max_concurrent: 10
```

**Acceptance Criteria**:

- [ ] PartitionSpec dataclass created
- [ ] PipelineSpec extended with partition field
- [ ] YAML loading validates partition config
- [ ] Example YAML documented

#### Issue 0.5.5: Create Partition Execution Tests

**File**: `tests/k0/scheduler/test_partitioned_execution.py`

**Test Scenarios**:

1. **Strategy Tests**:
   - `test_none_strategy_global_execution`: Single execution
   - `test_tenant_strategy_per_tenant`: One per tenant
   - `test_space_strategy_per_space`: One per tenant:space
   - `test_hash_strategy_distribution`: Partitions distributed

2. **Concurrency Tests**:
   - `test_max_concurrent_partitions_enforced`
   - `test_partition_already_running_skipped`
   - `test_partition_completion_allows_next`

3. **Hash Ring Tests**:
   - `test_consistent_hash_stable`
   - `test_node_add_minimal_rebalance`
   - `test_node_remove_rebalance`

**Acceptance Criteria**:

- [ ] All test scenarios implemented
- [ ] Integration test with mock pipelines
- [ ] Performance test for 1000+ partitions
- [ ] Documentation updated

---

### Epic 0.6: Implement K0 Optimistic Concurrency in UnitOfWork

> **Location**: `k0/uow/`
> **Prerequisite**: ADR k013 ACCEPTED (Issue 0.3.3)
> **Gate**: GATE 3 (Implementation)
> **Priority**: P2 (Code quality improvement)

#### Issue 0.6.1: Define VersionedWriteResult

**File**: `k0/uow/versioning.py`

**What to Implement**:

```python
from dataclasses import dataclass

@dataclass(slots=True)
class VersionedWriteResult:
    rows_affected: int
    version_conflict: bool
    new_version: int | None
    should_retry: bool
    retry_delay_ms: int
    attempt_number: int

class VersionConflictError(Exception):
    """Raised when max retries exceeded for version conflict."""

    def __init__(self, table: str, key: str, attempts: int):
        self.table = table
        self.key = key
        self.attempts = attempts
        super().__init__(f"Version conflict on {table}:{key} after {attempts} attempts")
```

**Acceptance Criteria**:

- [ ] VersionedWriteResult dataclass created
- [ ] VersionConflictError exception defined
- [ ] Type hints complete

#### Issue 0.6.2: Add execute_with_version_check to UnitOfWork

**File**: `k0/uow/unit_of_work.py` (modify existing)

**What to Implement**:

```python
import asyncio
import random

class UnitOfWork:
    # Existing code...

    async def execute_with_version_check(
        self,
        sql: str,
        params: tuple,
        version_column: str = "version",
        max_retries: int = 3,
        backoff_base_ms: int = 100,
        jitter_ms: int = 50
    ) -> VersionedWriteResult:
        """
        Execute SQL with optimistic concurrency control.

        The SQL must be an UPDATE that:
        1. Increments version: SET version = version + 1
        2. Checks version: WHERE version = :expected_version

        Args:
            sql: UPDATE statement with version check
            params: Parameters including expected version
            version_column: Name of version column (default: "version")
            max_retries: Max retry attempts on conflict (default: 3)
            backoff_base_ms: Base delay for exponential backoff
            jitter_ms: Random jitter to add to backoff

        Returns:
            VersionedWriteResult with conflict info

        Raises:
            VersionConflictError: If max_retries exceeded
        """
        attempt = 0

        while attempt <= max_retries:
            attempt += 1

            if self._connection is None:
                raise RuntimeError("UnitOfWork not in transaction context")

            cursor = self._connection.execute(sql, params)
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                # Success
                return VersionedWriteResult(
                    rows_affected=rows_affected,
                    version_conflict=False,
                    new_version=None,  # Caller should query if needed
                    should_retry=False,
                    retry_delay_ms=0,
                    attempt_number=attempt
                )

            # Version conflict (0 rows affected)
            if attempt > max_retries:
                break

            # Calculate backoff with jitter
            delay_ms = (backoff_base_ms * (2 ** (attempt - 1))) + random.randint(0, jitter_ms)

            if max_retries > 0:
                await asyncio.sleep(delay_ms / 1000.0)
                # Caller must refresh data before retry
                return VersionedWriteResult(
                    rows_affected=0,
                    version_conflict=True,
                    new_version=None,
                    should_retry=True,
                    retry_delay_ms=delay_ms,
                    attempt_number=attempt
                )

        # Max retries exceeded
        raise VersionConflictError(
            table="unknown",  # Caller should provide context
            key="unknown",
            attempts=attempt
        )
```

**Note**: The actual retry loop should be in the caller since they need to refresh the data between retries. UoW provides the building blocks.

**Acceptance Criteria**:

- [ ] execute_with_version_check method added
- [ ] Exponential backoff with jitter
- [ ] VersionConflictError raised on max retries
- [ ] Backward compatible with existing UoW usage

#### Issue 0.6.3: Create Versioned Write Helper Functions

**File**: `k0/uow/helpers.py`

**What to Implement**:

```python
from typing import Any

def build_versioned_update(
    table: str,
    set_columns: dict[str, Any],
    where_columns: dict[str, Any],
    version_column: str = "version"
) -> tuple[str, tuple]:
    """
    Build UPDATE SQL with version check.

    > **PostgreSQL Migration Note** (2025-01): Uses $N placeholder style.

    Example:
        sql, params = build_versioned_update(
            table="st_epi",
            set_columns={"episode_summary": "New summary", "updated_at": now},
            where_columns={"episode_id": "ep_123", "version": 5}
        )
        # Returns:
        # UPDATE st_epi SET episode_summary=$1, updated_at=$2, version=version+1
        # WHERE episode_id=$3 AND version=$4
        # RETURNING version
    """
    param_idx = 1
    set_parts = []
    for col in set_columns.keys():
        set_parts.append(f"{col}=${param_idx}")
        param_idx += 1
    set_parts.append(f"{version_column}={version_column}+1")

    where_parts = []
    for col in where_columns.keys():
        where_parts.append(f"{col}=${param_idx}")
        param_idx += 1

    sql = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)} RETURNING {version_column}"
    params = tuple(set_columns.values()) + tuple(where_columns.values())

    return sql, params

async def execute_versioned_update_with_retry(
    uow: "UnitOfWork",
    table: str,
    primary_key: dict[str, Any],
    refresh_callback: Callable[[], Awaitable[dict[str, Any]]],
    update_callback: Callable[[dict[str, Any]], dict[str, Any]],
    version_column: str = "version",
    max_retries: int = 3
) -> VersionedWriteResult:
    """
    Execute versioned update with automatic refresh-and-retry.

    Args:
        uow: Active UnitOfWork
        table: Table name
        primary_key: Dict of PK columns and values
        refresh_callback: Async function to fetch current row
        update_callback: Function that takes current row and returns new values
        version_column: Version column name
        max_retries: Max retry attempts

    Returns:
        VersionedWriteResult
    """
    for attempt in range(1, max_retries + 2):
        current_row = await refresh_callback()
        if current_row is None:
            raise ValueError(f"Row not found: {table} {primary_key}")

        new_values = update_callback(current_row)
        current_version = current_row[version_column]

        where_columns = {**primary_key, version_column: current_version}
        sql, params = build_versioned_update(table, new_values, where_columns, version_column)

        result = await uow.execute_with_version_check(
            sql, params, version_column, max_retries=0  # We handle retry
        )

        if not result.version_conflict:
            return result

        if attempt > max_retries:
            raise VersionConflictError(table, str(primary_key), attempt)

        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))

    raise VersionConflictError(table, str(primary_key), max_retries + 1)
```

**Acceptance Criteria**:

- [ ] build_versioned_update helper created
- [ ] execute_versioned_update_with_retry with refresh loop
- [ ] Examples in docstrings
- [ ] Unit tests for helpers

#### Issue 0.6.4: Create Optimistic Concurrency Tests

**File**: `tests/k0/uow/test_optimistic_concurrency.py`

**Test Scenarios**:

1. **Basic Operations**:
   - `test_versioned_update_success`: Normal update increments version
   - `test_versioned_update_conflict`: Stale version fails
   - `test_versioned_update_retry_success`: Retry after refresh succeeds

2. **Error Handling**:
   - `test_max_retries_exceeded_raises`: VersionConflictError raised
   - `test_backoff_timing`: Verify exponential backoff

3. **Helper Functions**:
   - `test_build_versioned_update_sql`: SQL generation
   - `test_execute_with_retry_refreshes`: Refresh callback called

**Acceptance Criteria**:

- [ ] All test scenarios implemented
- [ ] Concurrent update simulation
- [ ] Integration with PostgreSQL (asyncpg)
- [ ] 100% coverage on new code

---

### Epic 0.7: Implement K0 Pipeline Execution Context

> **Location**: `k0/pipelines/`
> **Prerequisite**: ADR k014 ACCEPTED (Issue 0.3.4)
> **Gate**: GATE 3 (Implementation)
> **Priority**: P2 (Cluster awareness)

#### Issue 0.7.1: Define NodeInfo and PartitionAssignment

**File**: `k0/pipelines/context.py` (new or modify existing)

**What to Implement**:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
import os
import uuid

@dataclass(slots=True)
class NodeInfo:
    node_id: str
    hostname: str
    started_at: datetime
    version: str

    @classmethod
    def from_environment(cls) -> "NodeInfo":
        """Create NodeInfo from environment variables."""
        return cls(
            node_id=os.environ.get("K0_NODE_ID", str(uuid.uuid4())),
            hostname=os.environ.get("HOSTNAME", "localhost"),
            started_at=datetime.utcnow(),
            version=os.environ.get("K0_VERSION", "0.0.0")
        )

@dataclass(slots=True)
class PartitionAssignment:
    partitions: list[str]
    total_nodes: int
    assignment_version: int
    assigned_at: datetime

    def contains(self, partition_key: str) -> bool:
        return partition_key in self.partitions

class NodeRegistry(Protocol):
    """Protocol for node discovery in multi-node deployments."""

    async def register(self, node: NodeInfo) -> None: ...
    async def deregister(self, node_id: str) -> None: ...
    async def get_all_nodes(self) -> list[NodeInfo]: ...
    async def heartbeat(self, node_id: str) -> None: ...
```

**Acceptance Criteria**:

- [ ] NodeInfo with environment-based factory
- [ ] PartitionAssignment with contains() helper
- [ ] NodeRegistry protocol defined
- [ ] Type hints complete

#### Issue 0.7.2: Extend PipelineContext with Node and Partition Info

**File**: `k0/pipelines/protocol.py` (modify existing)

**What to Implement**:

```python
from dataclasses import dataclass, field
from .context import NodeInfo, PartitionAssignment

@dataclass
class PipelineContext:
    # Existing fields...
    tenant_id: str
    space_id: str
    trace_id: str

    # NEW: Node and partition information
    node_info: NodeInfo = field(default_factory=NodeInfo.from_environment)
    partition_assignment: PartitionAssignment | None = None
    current_partition_key: str | None = None

    def is_my_partition(self, partition_key: str) -> bool:
        """Check if this node should process the partition."""
        if self.partition_assignment is None:
            return True  # No partitioning = process everything
        return self.partition_assignment.contains(partition_key)

    @property
    def partition_key(self) -> str:
        """Get current partition key (tenant:space)."""
        return self.current_partition_key or f"{self.tenant_id}:{self.space_id}"
```

**Acceptance Criteria**:

- [ ] PipelineContext extended with node_info
- [ ] partition_assignment added
- [ ] is_my_partition() helper method
- [ ] Backward compatible with existing code

#### Issue 0.7.3: Create Static Node Registry (Single-Node)

**File**: `k0/pipelines/registry/static.py`

**What to Implement**:

```python
from ..context import NodeInfo, NodeRegistry

class StaticNodeRegistry:
    """Single-node registry that only tracks local node."""

    def __init__(self):
        self._local_node: NodeInfo | None = None

    async def register(self, node: NodeInfo) -> None:
        self._local_node = node

    async def deregister(self, node_id: str) -> None:
        if self._local_node and self._local_node.node_id == node_id:
            self._local_node = None

    async def get_all_nodes(self) -> list[NodeInfo]:
        return [self._local_node] if self._local_node else []

    async def heartbeat(self, node_id: str) -> None:
        pass  # No-op for single node
```

**Acceptance Criteria**:

- [ ] StaticNodeRegistry for single-node deployments
- [ ] Implements NodeRegistry protocol
- [ ] No external dependencies

#### Issue 0.7.4: Create Pipeline Context Tests

**File**: `tests/k0/pipelines/test_context.py`

**Test Scenarios**:

1. **NodeInfo**:
   - `test_node_info_from_environment`
   - `test_node_info_defaults`

2. **PartitionAssignment**:
   - `test_partition_contains`
   - `test_empty_assignment`

3. **PipelineContext**:
   - `test_is_my_partition_with_assignment`
   - `test_is_my_partition_no_assignment`
   - `test_partition_key_property`

4. **NodeRegistry**:
   - `test_static_registry_single_node`
   - `test_static_registry_operations`

**Acceptance Criteria**:

- [ ] All test scenarios implemented
- [ ] Tests for both registry implementations
- [ ] Environment variable mocking
- [ ] 100% coverage on new code

---

### Epic 0.8: K0 Enhancement Integration Tests

> **Purpose**: Validate all K0 enhancements work together
> **Prerequisite**: Epics 0.4-0.7 complete
> **Gate**: GATE 4 (Test Implementation)

#### Issue 0.8.1: Create K0 Enhancement Integration Test Suite

**File**: `tests/k0/integration/test_kernel_enhancements.py`

**Test Scenarios**:

1. **Lock + Partition Integration**:
   - `test_partitioned_pipeline_acquires_partition_lock`
   - `test_concurrent_partitions_independent_locks`

2. **Lock + UoW Integration**:
   - `test_lock_released_on_uow_commit`
   - `test_lock_released_on_uow_rollback`

3. **Context + Partition Integration**:
   - `test_context_has_partition_key`
   - `test_context_is_my_partition_check`

4. **Full Pipeline Simulation**:
   - `test_p03_style_execution_with_all_enhancements`

**Acceptance Criteria**:

- [ ] All integration scenarios pass
- [ ] No regressions in existing K0 tests
- [ ] Performance baseline established
- [ ] Documentation updated

#### Issue 0.8.2: Update K0 Architecture Master

**File**: `k0/pipelines/k0_architecture_master.md`

**What to Update**:

1. **Part 3.1 (Module Registry)**: Add new K0 modules
   - `k0/sync/advisory_lock.py`
   - `k0/scheduler/partitions.py`
   - `k0/scheduler/hash_ring.py`
   - `k0/uow/versioning.py`
   - `k0/pipelines/context.py`

2. **Part 5.2 (Syscall Matrix)**: Add new syscalls
   - `lock_acquire`
   - `lock_release`
   - `lock_heartbeat`

3. **Part 5.3 (Storage Tables)**: Add new tables
   - `st_advisory_locks`

4. **Part 7.1 (ADR Index)**: Add ADRs
   - k011, k012, k013, k014 with status IMPLEMENTED

**Acceptance Criteria**:

- [ ] All new components registered
- [ ] ADR statuses updated
- [ ] Version header bumped
- [ ] Cross-references complete

---

## Milestone 1: Infrastructure Setup

**Goal**: Create migrations, contracts, pipeline YAML
**Gate**: GATE 2 (Contract Discovery & Validation)

### Epic 1.1: Database Migrations

> **Location**: `k0/contracts/sql/migrations/`
> **Starting Migration Number**: 0028
> **Schema Source**: Dossier Section 6

#### Issue 1.1.1: Create Migration - st_epi (Episodic Memory)

**File**: `k0/contracts/sql/migrations/0028_p03_episodic_memory_table.sql`

**Schema** (from dossier Section 6.3):

```sql
CREATE TABLE st_epi (
  episode_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,
  episode_summary TEXT,
  episode_type TEXT,
  start_time_utc INTEGER NOT NULL,
  end_time_utc INTEGER NOT NULL,
  duration_minutes INTEGER,
  temporal_bucket TEXT,
  day_of_week TEXT,
  is_recurring BOOLEAN,
  recurrence_pattern TEXT,
  source_events_json TEXT NOT NULL,
  source_event_count INTEGER NOT NULL,
  primary_location TEXT,
  location_type TEXT,
  participants_json TEXT,
  participant_count INTEGER,
  embedding_id TEXT,
  cluster_id TEXT,
  cluster_confidence REAL,
  consolidation_cycle_id TEXT,
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  last_observed_at INTEGER,
  decay_factor REAL DEFAULT 1.0,
  archival_status TEXT DEFAULT 'ACTIVE' CHECK(archival_status IN ('ACTIVE','ARCHIVED','TOMBSTONE')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);
```

**Indexes**:

- `idx_epi_tenant_time(tenant_id, start_time_utc DESC)`
- `idx_epi_space_time(space_id, start_time_utc DESC)`
- `idx_epi_cluster(cluster_id)`
- `idx_epi_canonical(is_canonical, archival_status)`

**Acceptance**:

- [ ] Migration applies cleanly on empty DB
- [ ] Migration applies cleanly on production clone
- [ ] All indexes created
- [ ] FK to st_vec.embedding_id validated

#### Issue 1.1.2: Create Migration - st_sem (Semantic Patterns)

**File**: `k0/contracts/sql/migrations/0029_p03_semantic_patterns_table.sql`

**Schema** (from dossier Section 6.4):

```sql
CREATE TABLE st_sem (
  pattern_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,
  pattern_type TEXT NOT NULL CHECK(pattern_type IN ('ROUTINE','PREFERENCE','THEME','RELATIONSHIP','GOAL','VALUE')),
  pattern_subtype TEXT,
  pattern_name TEXT NOT NULL,
  pattern_description TEXT,
  pattern_attributes_json TEXT,
  temporal_regularity REAL,
  temporal_pattern_json TEXT,
  source_episodes_json TEXT NOT NULL,
  source_episode_count INTEGER NOT NULL,
  embedding_id TEXT,
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  last_observed_at INTEGER,
  first_observed_at INTEGER,
  decay_factor REAL DEFAULT 1.0,
  archival_status TEXT DEFAULT 'ACTIVE' CHECK(archival_status IN ('ACTIVE','ARCHIVED','TOMBSTONE')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);
```

**Indexes**:

- `idx_sem_tenant_type(tenant_id, pattern_type)`
- `idx_sem_actor_type(actor_id, pattern_type)`
- `idx_sem_canonical(is_canonical, archival_status)`
- `idx_sem_confidence(confidence_score DESC)`

#### Issue 1.1.3: Create Migration - st_procedural (Habits)

**File**: `k0/contracts/sql/migrations/0030_p03_procedural_habits_table.sql`

**Schema** (from dossier Section 6.5):

```sql
CREATE TABLE st_procedural (
  routine_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,
  routine_name TEXT NOT NULL,
  routine_category TEXT,
  temporal_anchor TEXT,
  day_pattern TEXT,
  frequency TEXT,
  regularity_score REAL,
  action_sequence_json TEXT,
  typical_duration_minutes INTEGER,
  source_episodes_json TEXT NOT NULL,
  source_episode_count INTEGER NOT NULL,
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  last_observed_at INTEGER,
  streak_count INTEGER DEFAULT 0,
  streak_broken_at INTEGER,
  decay_factor REAL DEFAULT 1.0,
  archival_status TEXT DEFAULT 'ACTIVE',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);
```

**Indexes**:

- `idx_procedural_tenant_actor(tenant_id, actor_id)`
- `idx_procedural_category(routine_category)`

#### Issue 1.1.4: Create Migration - st_social (Relationships)

**File**: `k0/contracts/sql/migrations/0031_p03_social_relationships_table.sql`

**Schema** (from dossier Section 6.6):

```sql
CREATE TABLE st_social (
  relationship_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_a_id TEXT NOT NULL,
  actor_b_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,
  relationship_type TEXT NOT NULL,
  relationship_subtype TEXT,
  relationship_label TEXT,
  interaction_count INTEGER DEFAULT 0,
  avg_sentiment REAL,
  relationship_strength REAL DEFAULT 0.5,
  intimacy_level TEXT,
  first_interaction_at INTEGER,
  last_interaction_at INTEGER,
  interaction_frequency TEXT,
  source_episodes_json TEXT,
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  decay_factor REAL DEFAULT 1.0,
  archival_status TEXT DEFAULT 'ACTIVE',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER,
  UNIQUE(tenant_id, actor_a_id, actor_b_id, is_canonical)
);
```

**Note**: This extends the existing `st_relationships` table (migration 0024) with P03-specific columns for truth tracking. Consider ALTER TABLE vs new table.

#### Issue 1.1.5: Create Migration - st_prospective (Intentions)

**File**: `k0/contracts/sql/migrations/0032_p03_prospective_intentions_table.sql`

**Schema** (from dossier Section 6.7):

```sql
CREATE TABLE st_prospective (
  intention_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,
  intention_type TEXT NOT NULL CHECK(intention_type IN ('GOAL','PLAN','REMINDER','COMMITMENT','WISH')),
  intention_description TEXT NOT NULL,
  target_date INTEGER,
  target_context TEXT,
  status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','COMPLETED','ABANDONED','DEFERRED')),
  inferred_from_json TEXT,
  inference_confidence REAL,
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  decay_factor REAL DEFAULT 1.0,
  archival_status TEXT DEFAULT 'ACTIVE',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);
```

#### Issue 1.1.6: Create Migration - st_kg_dom (KG Entities)

**File**: `k0/contracts/sql/migrations/0033_p03_kg_entities_table.sql`

**Schema** (from dossier Section 6.8):

```sql
CREATE TABLE st_kg_dom (
  entity_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,
  entity_type TEXT NOT NULL,
  entity_subtype TEXT,
  canonical_name TEXT NOT NULL,
  aliases_json TEXT,
  attributes_json TEXT,
  embedding_id TEXT,
  source_episodes_json TEXT,
  first_mentioned_event_id TEXT,
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  last_observed_at INTEGER,
  decay_factor REAL DEFAULT 1.0,
  archival_status TEXT DEFAULT 'ACTIVE',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);
```

**Indexes**:

- `idx_kg_dom_tenant_type(tenant_id, entity_type)`
- `idx_kg_dom_name(canonical_name)`
- `idx_kg_dom_canonical(is_canonical, archival_status)`

#### Issue 1.1.7: Create Migration - st_kg_edges (KG Relationships)

**File**: `k0/contracts/sql/migrations/0034_p03_kg_edges_table.sql`

**Schema** (from dossier Section 6.9):

```sql
CREATE TABLE st_kg_edges (
  edge_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  source_entity_id TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,
  relation_type TEXT NOT NULL,
  relation_subtype TEXT,
  properties_json TEXT,
  edge_weight REAL DEFAULT 1.0,
  confidence_score REAL DEFAULT 0.5,
  source_episodes_json TEXT,
  co_occurrence_count INTEGER DEFAULT 1,
  observation_count INTEGER DEFAULT 1,
  last_observed_at INTEGER,
  decay_factor REAL DEFAULT 1.0,
  archival_status TEXT DEFAULT 'ACTIVE',
  valid_from INTEGER NOT NULL,
  valid_to INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY (source_entity_id) REFERENCES st_kg_dom(entity_id),
  FOREIGN KEY (target_entity_id) REFERENCES st_kg_dom(entity_id)
);
```

**Indexes**:

- `idx_kg_edges_source(source_entity_id, relation_type)`
- `idx_kg_edges_target(target_entity_id, relation_type)`
- `idx_kg_edges_canonical(is_canonical, archival_status)`

#### Issue 1.1.8: Create Migration - st_vec Updates (P03 columns)

**File**: `k0/contracts/sql/migrations/0035_p03_st_vec_enhancements.sql`

**Existing table**: `st_vec` (migration 0026)

**Verify columns exist** (from dossier Section 6.10):

- `embedding_id TEXT PRIMARY KEY`
- `event_id TEXT NOT NULL`
- `tenant_id TEXT NOT NULL`
- `space_id TEXT NOT NULL`
- `vector BLOB NOT NULL`
- `vector_dim INTEGER DEFAULT 768`
- `model_id TEXT DEFAULT 'ultrabert_v2.1.0'`
- `status TEXT CHECK IN ('READY','INDEXED','FAILED')`
- `faiss_id INTEGER` (added in 0027)

**No new columns needed** - verify existing schema covers P03 requirements.

#### Issue 1.1.9: Create Migration - st_learning_queue (Gap Queue)

**File**: `k0/contracts/sql/migrations/0036_p03_learning_queue_table.sql`

**Schema** (from dossier Section 6.11):

```sql
CREATE TABLE st_learning_queue (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  gap_type TEXT NOT NULL CHECK(gap_type IN (
    'AMBIGUOUS_ENTITY','LOW_CONFIDENCE_EDGE','MISSING_ATTRIBUTE',
    'CONTRADICTION','CONCEPT_DRIFT','STRUCTURAL_HOLE','STALE_ANCHOR'
  )),
  entity_id TEXT,
  related_event_id TEXT,
  related_truth_id TEXT,
  confidence_score REAL,
  entropy_score REAL,
  importance_score REAL GENERATED ALWAYS AS (entropy_score * (1.0 / (confidence_score + 0.1))) STORED,
  context_json TEXT,
  status TEXT DEFAULT 'PENDING' CHECK(status IN (
    'PENDING','READY','ASKED','ANSWERED','RESOLVED','EXPIRED','REJECTED','SUPPRESSED'
  )),
  created_at INTEGER NOT NULL,
  expires_at INTEGER,
  ready_at INTEGER,
  asked_at INTEGER,
  answered_at INTEGER,
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  last_attempt_at INTEGER,
  resolution_type TEXT,
  resolution_data_json TEXT,
  consolidation_cycle_id TEXT,
  FOREIGN KEY (related_event_id) REFERENCES st_hipp_events(event_id)
);
```

**Indexes**:

- `idx_learning_queue_importance(importance_score DESC, created_at)`
- `idx_learning_queue_status(status, expires_at)`
- `idx_learning_queue_tenant(tenant_id, gap_type, status)`

#### Issue 1.1.10: Create Migration - st_anchors (Bayesian Beliefs)

**File**: `k0/contracts/sql/migrations/0037_p03_anchors_table.sql`

**Schema** (from dossier Section 6.12):

```sql
CREATE TABLE st_anchors (
  entity_id TEXT NOT NULL,
  attribute TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  alpha REAL DEFAULT 1.0,
  beta REAL DEFAULT 1.0,
  confidence REAL GENERATED ALWAYS AS (alpha / (alpha + beta)) STORED,
  uncertainty REAL GENERATED ALWAYS AS (1.0 / (1.0 + alpha + beta)) STORED,
  observation_count INTEGER DEFAULT 0,
  first_observed_at INTEGER,
  last_updated_at INTEGER NOT NULL,
  decay_rate REAL DEFAULT 0.05,
  half_life_days INTEGER DEFAULT 180,
  last_drift_check_at INTEGER,
  drift_detected BOOLEAN DEFAULT FALSE,
  drift_magnitude REAL,
  status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','DRIFTING','STALE','ARCHIVED')),
  PRIMARY KEY (entity_id, attribute, tenant_id)
);
```

**Indexes**:

- `idx_anchors_entity(entity_id, last_updated_at DESC)`
- `idx_anchors_confidence(confidence DESC)`
- `idx_anchors_drift(drift_detected, status)`

#### Issue 1.1.11: Create Migration - st_anchor_observations

**File**: `k0/contracts/sql/migrations/0038_p03_anchor_observations_table.sql`

**Schema** (from dossier Section 6.13):

```sql
CREATE TABLE st_anchor_observations (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL,
  attribute TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  observed_at INTEGER NOT NULL,
  event_id TEXT,
  supports_anchor BOOLEAN NOT NULL,
  observation_weight REAL DEFAULT 1.0,
  observation_context TEXT,
  FOREIGN KEY (entity_id, attribute, tenant_id) REFERENCES st_anchors(entity_id, attribute, tenant_id),
  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);
```

**Indexes**:

- `idx_anchor_obs_anchor(entity_id, attribute, observed_at DESC)`

#### Issue 1.1.12: Create Migration - consolidation_locks

**File**: `k0/contracts/sql/migrations/0039_p03_consolidation_locks_table.sql`

**Schema** (per Issue 0.2.1 design):

```sql
CREATE TABLE consolidation_locks (
  lock_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  pipeline_id TEXT NOT NULL DEFAULT 'P03',
  acquired_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  holder_node_id TEXT NOT NULL,
  cycle_id TEXT NOT NULL,
  UNIQUE(tenant_id, space_id, pipeline_id)
);
```

**Purpose**: Prevent concurrent P03 cycles on same tenant/space.

**Cleanup**: Stale locks (expired > 5 minutes) cleaned by scheduler.

#### Issue 1.1.13: Create Migration - st_hipp_events P03 Columns

**File**: `k0/contracts/sql/migrations/0040_p03_hipp_events_consolidation_columns.sql`

**ALTER TABLE** (extend existing st_hipp_events from migration 0024):

```sql
ALTER TABLE st_hipp_events ADD COLUMN consolidation_status TEXT
  CHECK(consolidation_status IN ('PENDING','IN_PROGRESS','CONSOLIDATED','DUPLICATE','PRUNED','PENDING_REVIEW'));
ALTER TABLE st_hipp_events ADD COLUMN consolidation_cycle_id TEXT;
ALTER TABLE st_hipp_events ADD COLUMN consolidated_at INTEGER;
ALTER TABLE st_hipp_events ADD COLUMN reconciliation_decision TEXT;
ALTER TABLE st_hipp_events ADD COLUMN truth_match_id TEXT;
ALTER TABLE st_hipp_events ADD COLUMN truth_match_similarity REAL;

CREATE INDEX idx_hipp_events_consolidation ON st_hipp_events(consolidation_status, event_time_utc)
  WHERE consolidation_status IS NULL OR consolidation_status = 'PENDING';
```

#### Issue 1.1.14: Create Migration - st_consolidation_audit

**File**: `k0/contracts/sql/migrations/0041_p03_consolidation_audit_table.sql`

**Schema** (per Section 14.5.1):

```sql
CREATE TABLE st_consolidation_audit (
  audit_id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  decision_type TEXT NOT NULL,
  target_table TEXT,
  target_id TEXT,
  similarity_score REAL,
  confidence_before REAL,
  confidence_after REAL,
  decision_reason TEXT,
  created_at INTEGER NOT NULL,
  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);
```

**Indexes**:

- `idx_consolidation_audit_cycle(cycle_id)`
- `idx_consolidation_audit_event(event_id)`

#### Issue 1.1.15: Create Migration - st_dlq P03 entries

**File**: Verify existing `st_dlq` schema (baseline migration 0001)

**Existing schema** supports:

- `pipeline_id` via `driver` column
- `phase` can use `op_kind` column
- `payload` for P03-specific error context

**No migration needed** - existing st_dlq schema is sufficient per Section 13.4.

#### Issue 1.1.16: Create v1 to v2 Backfill - observation_count

**File**: `k0/contracts/sql/migrations/0042_p03_backfill_observation_count.sql`

**Purpose**: Backfill observation_count for existing patterns per Section 11.2.3.

**SQL**:

```sql
-- Backfill st_sem observation_count from source_episode_count
UPDATE st_sem SET observation_count = source_episode_count WHERE observation_count = 1;

-- Backfill st_procedural from source_episode_count
UPDATE st_procedural SET observation_count = source_episode_count WHERE observation_count = 1;
```

**Note**: Run AFTER data migration from v1 tables.

---

### Epic 1.2: Module Contracts (R0-R4)

> **Location**: `k0/contracts/modules/`
> **Naming Pattern**: `<domain>.<module>.v1.yaml`
> **Template**: Based on existing contracts like `core.hipp_events_writer.v1.yaml`

#### Issue 1.2.1: Create Contract - consolidation.trigger.v1.yaml

**File**: `k0/contracts/modules/consolidation.trigger.v1.yaml`

**Module ID**: `consolidation.trigger`
**Version**: v1
**Phase**: R0

**Input Events**:

- `p03.consolidation.schedule.v1` (cron/threshold)
- `system.idle.detected.v1` (idle trigger)
- `p03.consolidation.manual.v1` (manual trigger)

**Output Events**:

- `p03.consolidation.triggered.v1`

**Side Effects**:

- read:st_hipp_events (check pending count)
- read:st_offsets (check last processed)

**Trigger Types** (per Section 4.1):

1. IDLE: User inactive for 30+ minutes
2. CRON: Scheduled (default 2:00 AM local)
3. THRESHOLD: Pending events > 5000
4. MANUAL: Admin-triggered

**Latency Budget**: 50ms

#### Issue 1.2.2: Create Contract - consolidation.lock.v1.yaml

**File**: `k0/contracts/modules/consolidation.lock.v1.yaml`

**Module ID**: `consolidation.lock`
**Version**: v1
**Phase**: R0

**Input Events**:

- `p03.consolidation.triggered.v1`

**Output Events**:

- `p03.consolidation.lock.acquired.v1`
- `p03.consolidation.lock.failed.v1`

**Side Effects**:

- write:consolidation_locks
- read:consolidation_locks

**Contract**:

```python
async def acquire_lock(tenant_id: str, space_id: str, cycle_id: str) -> LockResult
async def release_lock(lock_id: str) -> bool
async def cleanup_stale_locks(older_than_minutes: int = 5) -> int
```

**Idempotent**: Yes (upsert on conflict)
**Latency Budget**: 20ms

#### Issue 1.2.3: Create Contract - consolidation.batch_select.v1.yaml

**File**: `k0/contracts/modules/consolidation.batch_select.v1.yaml`

**Module ID**: `consolidation.batch_select`
**Version**: v1
**Phase**: R0

**Input Events**:

- `p03.consolidation.lock.acquired.v1`

**Output Events**:

- `p03.batch.selected.v1`

**Side Effects**:

- read:st_hipp_events
- read:st_offsets

**Batch Selection Query**:

```sql
SELECT * FROM st_hipp_events
WHERE tenant_id = :tenant_id
  AND space_id = :space_id
  AND (consolidation_status IS NULL OR consolidation_status = 'PENDING')
  AND event_time_utc > :last_offset
ORDER BY event_time_utc ASC
LIMIT :batch_size
```

**Config**:

- `batch_size`: 1000 (default), max 10000
- `min_batch_size`: 10 (skip cycle if fewer)

**Latency Budget**: 100ms

#### Issue 1.2.4: Create Contract - hippocampus.replay_coordinator.v1.yaml

**File**: `k0/contracts/modules/hippocampus.replay_coordinator.v1.yaml`

**Module ID**: `hippocampus.replay_coordinator`
**Version**: v1
**Phase**: R1
**Brain Analog**: CA3

**Input Events**:

- `p03.batch.selected.v1`

**Output Events**:

- `p03.replay.complete.v1`

**Side Effects**:

- read:st_hipp_events (batch)
- read:st_vec (embeddings via P08)

**Interface** (per Section 7.4.6):

```python
async def coordinate_replay(
    batch: List[HippEvent],
    embeddings: Dict[str, np.ndarray]
) -> ReplayResult
```

**Output**: `ReplayResult` containing:

- `scored_events`: List with importance_score per event
- `associations`: List of Hebbian association strengths
- `replay_duration_ms`: Actual replay time

**Latency Budget**: 15 minutes (R1 phase budget)

#### Issue 1.2.5: Create Contract - hippocampus.importance_score.v1.yaml

**File**: `k0/contracts/modules/hippocampus.importance_score.v1.yaml`

**Module ID**: `hippocampus.importance_score`
**Version**: v1
**Phase**: R1

**Formula** (per Section 2.4):

```
importance = 0.35 × emotional_salience
           + 0.25 × recency_score
           + 0.20 × access_frequency
           + 0.20 × social_significance
```

**Input Fields from st_hipp_events**:

- `salience_score`, `sentiment_score`, `affect_valence`, `affect_arousal`
- `event_time_utc` (for recency)
- `participants_json`, `num_participants` (for social)

**Output**: `importance_score` [0-1]

**Latency Budget**: 1ms per event

#### Issue 1.2.6: Create Contract - hippocampus.association_strength.v1.yaml

**File**: `k0/contracts/modules/hippocampus.association_strength.v1.yaml`

**Module ID**: `hippocampus.association_strength`
**Version**: v1
**Phase**: R1

**Hebbian Learning** (per Section 2.4):

```
strength_new = strength_old + learning_rate × (co_occurrence - strength_old)
```

**Default Learning Rate**: 0.1

**Input**: Event pairs with co-occurrence data
**Output**: Association strength matrix

**Latency Budget**: 5ms per event pair

#### Issue 1.2.7: Create Contract - neocortical.episode_cluster.v1.yaml

**File**: `k0/contracts/modules/neocortical.episode_cluster.v1.yaml`

**Module ID**: `neocortical.episode_cluster`
**Version**: v1
**Phase**: R2
**Implements**: M18 EpisodeClusterer

**Input Events**:

- `p03.replay.complete.v1`

**Output Events**:

- `p03.cluster.formed.v1`

**Side Effects**:

- read:st_vec (embeddings)

**Algorithm**: DBSCAN (per Section 7.4.1)

**Config**:

- `eps`: 0.3 (cosine distance threshold)
- `min_samples`: 2
- `max_cluster_size`: 50
- `temporal_window_hours`: 4

**Output**: List of `EpisodeCluster` with:

- `cluster_id`, `member_events`, `centroid_embedding`
- `cluster_confidence` (mean pairwise similarity)

**Latency Budget**: 20 minutes (R2 phase budget)

#### Issue 1.2.8: Create Contract - neocortical.pattern_extract.v1.yaml

**File**: `k0/contracts/modules/neocortical.pattern_extract.v1.yaml`

**Module ID**: `neocortical.pattern_extract`
**Version**: v1
**Phase**: R2

**Input**: Episode clusters
**Output**: Extracted patterns (ROUTINE, PREFERENCE, THEME, etc.)

**Pattern Types**:

- ROUTINE: Temporal regularity (same time, same action)
- PREFERENCE: Repeated choices with positive sentiment
- THEME: Semantic clustering across episodes
- RELATIONSHIP: Social interaction patterns

**Latency Budget**: 5 minutes

#### Issue 1.2.9: Create Contract - neocortical.ca1_bridge.v1.yaml

**File**: `k0/contracts/modules/neocortical.ca1_bridge.v1.yaml`

**Module ID**: `neocortical.ca1_bridge`
**Version**: v1
**Phase**: R2
**Status**: CRITICAL - Core of bidirectional reconciliation

**Input**: Extracted patterns from new signals
**Output**: Reconciliation decisions

**Truth Query** (per Section 1.4):
Queries all 8 memory layers for existing truth matching new patterns.

**Decision Matrix**:

- REINFORCE: similarity > 0.85, confidence++
- EXTEND: similarity 0.6-0.85, add examples
- CREATE: similarity < 0.6, new truth entry
- EVOLVE: pattern drift detected, version update
- CONTRADICT: conflict with existing truth
- SUPERSEDE: replaces obsolete truth

**Similarity Calculation** (per Section 4.3.3):

```
similarity = 0.40 × embedding_sim
           + 0.25 × simhash_sim
           + 0.15 × entity_overlap
           + 0.10 × temporal_proximity
           + 0.10 × spatial_proximity
```

**Latency Budget**: 10 minutes

#### Issue 1.2.10: Create Contract - synaptic.duplicate_detect.v1.yaml

**File**: `k0/contracts/modules/synaptic.duplicate_detect.v1.yaml`

**Module ID**: `synaptic.duplicate_detect`
**Version**: v1
**Phase**: R3
**Implements**: M19 DuplicateDetector

**Algorithm**: SimHash (per Section 7.4.2)

**Input**: Batch of HippEvents
**Output**: `DuplicationResult` per event

**Config**:

- `hamming_threshold`: 3 (bits difference for near-duplicate)
- `time_window_hours`: 168 (1 week)

**Side Effects**:

- read:st_hipp_events (simhash_hex column)

**Latency Budget**: 5 minutes

#### Issue 1.2.11: Create Contract - synaptic.novelty_score.v1.yaml

**File**: `k0/contracts/modules/synaptic.novelty_score.v1.yaml`

**Module ID**: `synaptic.novelty_score`
**Version**: v1
**Phase**: R3

**Formula** (per Section 2.4):

```
novelty = (1 - max_similarity) × (1 + first_time_bonus) × (1 + milestone_bonus) × (1 - routine_penalty)
```

**Bonuses**:

- First-time activity: +0.15 (activity_count < 3)
- Milestone event: +0.20 (birthday, anniversary, graduation)
- Temporal anomaly: +0.10 (unusual time)

**Penalties**:

- Routine activity: -0.50 (same action, same time pattern)

**Output**: `novelty_score` [0-1]

**Latency Budget**: 1ms per event

#### Issue 1.2.12: Create Contract - synaptic.retention_enforce.v1.yaml

**File**: `k0/contracts/modules/synaptic.retention_enforce.v1.yaml`

**Module ID**: `synaptic.retention_enforce`
**Version**: v1
**Phase**: R3
**Implements**: M20 RetentionEnforcer

**Decay Formula** (per Section 7.4.3):

```
decay_factor = exp(-λ × days_since_observation)
```

**Layer-specific λ values**:

- st_epi: 0.005 (slow decay)
- st_sem: 0.002 (very slow)
- st_procedural: 0.001 (habits stable)
- st_social: 0.003 (moderate)
- st_prospective: 0.010 (faster decay)
- st_kg_dom: 0.001 (stable)
- st_kg_edges: 0.004 (volatile)

**Thresholds**:

- Archive: decay < 0.1
- Tombstone: decay < 0.01

**Latency Budget**: 10 minutes

#### Issue 1.2.13: Create Contract - kg.entity_normalize.v1.yaml

**File**: `k0/contracts/modules/kg.entity_normalize.v1.yaml`

**Module ID**: `kg.entity_normalize`
**Version**: v1
**Phase**: R4

**Input**: P02 `entities_json` from st_hipp_events

**NOTE**: NO NER model calls in P03 - uses pre-computed UltraBERT output from P02.

**Processing**:

1. Parse entities_json (9 general + 12 family entity types)
2. Resolve aliases (Levenshtein > 0.85)
3. Merge duplicates (same canonical name)
4. Update observation_count

**Side Effects**:

- read:st_kg_dom (existing entities)
- (writes via M24 TruthWriter)

**Latency Budget**: 5 minutes

#### Issue 1.2.14: Create Contract - kg.relationship_discover.v1.yaml

**File**: `k0/contracts/modules/kg.relationship_discover.v1.yaml`

**Module ID**: `kg.relationship_discover`
**Version**: v1
**Phase**: R4

**Algorithm**: Hebbian co-occurrence + Granger causality

**Co-occurrence Rule**: Entities appearing together in 2+ events within 1 hour = temporal edge.

**Hebbian Update**:

```
weight_new = weight_old + 0.1 × (co_occurrence - weight_old)
```

**Latency Budget**: 5 minutes

#### Issue 1.2.15: Create Contract - kg.temporal_update.v1.yaml

**File**: `k0/contracts/modules/kg.temporal_update.v1.yaml`

**Module ID**: `kg.temporal_update`
**Version**: v1
**Phase**: R4

**Bitemporal Tracking**:

- `valid_from`: When this truth became valid
- `valid_to`: When this truth stopped being valid (NULL = current)

**Version Chain**:

- New version links via `supersedes_id` to previous
- Only one version has `is_canonical = TRUE`

**Latency Budget**: 2 minutes

#### Issue 1.2.16: Create Contract - kg.consolidator.v1.yaml

**File**: `k0/contracts/modules/kg.consolidator.v1.yaml`

**Module ID**: `kg.consolidator`
**Version**: v1
**Phase**: R4
**Implements**: M21 KGConsolidator

**Input Events**:

- `p03.cluster.formed.v1`

**Output Events**:

- `p03.kg.updated.v1`

**Interface** (per Section 7.4.4):

```python
async def consolidate(
    clusters: List[EpisodeCluster],
    existing_kg: KnowledgeGraph
) -> List[KGUpdate]
```

**Side Effects**:

- read:st_kg_dom, st_kg_edges

**Latency Budget**: 25 minutes (R4 phase budget, parallel with R3)

---

### Epic 1.3: Module Contracts (R5-R8)

> **Location**: `k0/contracts/modules/`
> **Note**: R5 (Dream Phase) is OPTIONAL - graceful skip if disabled

#### Issue 1.3.1: Create Contract - dream.counterfactual.v1.yaml

**File**: `k0/contracts/modules/dream.counterfactual.v1.yaml`

**Module ID**: `dream.counterfactual`
**Version**: v1
**Phase**: R5 (OPTIONAL)
**Algorithm**: CPN (Counterfactual Prediction Network)

**Purpose**: Explores "what if" scenarios from episode data

**Input**: Episode clusters with high emotional salience

**Output**: `CounterfactualInsight` containing:

- `scenario`: Alternative outcome description
- `confidence`: [0-1] prediction confidence
- `contributing_patterns`: Source patterns

**Feature Flag**: `dream_phase_enabled` (default: false)

**Latency Budget**: 5 minutes (within R5 20-minute total)

#### Issue 1.3.2: Create Contract - dream.prediction.v1.yaml

**File**: `k0/contracts/modules/dream.prediction.v1.yaml`

**Module ID**: `dream.prediction`
**Version**: v1
**Phase**: R5 (OPTIONAL)
**Algorithm**: TPN-MCTS (Temporal Prediction Network with Monte Carlo Tree Search)

**Purpose**: Projects future likely scenarios

**Input**: Recent patterns, routines, upcoming calendar events

**Output**: `PredictionInsight` containing:

- `prediction`: Future scenario
- `probability`: [0-1]
- `time_horizon_days`: Prediction window

**Latency Budget**: 5 minutes

#### Issue 1.3.3: Create Contract - dream.insight.v1.yaml

**File**: `k0/contracts/modules/dream.insight.v1.yaml`

**Module ID**: `dream.insight`
**Version**: v1
**Phase**: R5 (OPTIONAL)
**Algorithm**: BGT-SM (Basal Ganglia Thalamus Semantic Memory)

**Purpose**: Discovers remote associations across knowledge domains

**Input**: Semantic clusters, KG subgraphs

**Output**: `SemanticInsight` containing:

- `association`: Novel connection discovered
- `source_domains`: Connected knowledge areas
- `novelty_score`: [0-1]

**Latency Budget**: 5 minutes

#### Issue 1.3.4: Create Contract - dream.explorer.v1.yaml

**File**: `k0/contracts/modules/dream.explorer.v1.yaml`

**Module ID**: `dream.explorer`
**Version**: v1
**Phase**: R5 (OPTIONAL)
**Implements**: M22 DreamExplorer

**Interface** (per Section 7.4.5):

```python
async def explore(
    clusters: List[EpisodeCluster],
    config: DreamConfig
) -> Optional[DreamOutput]
```

**Output**: `DreamOutput` containing:

- `counterfactuals`: List[CounterfactualInsight]
- `predictions`: List[PredictionInsight]
- `insights`: List[SemanticInsight]
- `exploration_time_ms`: Actual time spent

**Bypass Logic**:

```python
if not config.dream_phase_enabled:
    return None  # Skip R5 entirely
```

**Latency Budget**: 20 minutes total (R5 phase)

#### Issue 1.3.5: Create Contract - staging.update_status.v1.yaml

**File**: `k0/contracts/modules/staging.update_status.v1.yaml`

**Module ID**: `staging.update_status`
**Version**: v1
**Phase**: R6

**Updates st_hipp_events columns**:

- `consolidation_status`: 'PENDING' → 'COMPLETED' | 'DEFERRED' | 'ARCHIVED'
- `last_consolidated_utc`: Current timestamp
- `consolidation_cycle_id`: Current cycle UUID

**SQL Template**:

```sql
UPDATE st_hipp_events
SET consolidation_status = :status,
    last_consolidated_utc = :now,
    consolidation_cycle_id = :cycle_id,
    updated_at_utc = :now
WHERE event_id = :event_id
  AND (version < :new_version OR version IS NULL);
```

**Batch Size**: 500 events per transaction

**Latency Budget**: 5 minutes

#### Issue 1.3.6: Create Contract - staging.update_cluster.v1.yaml

**File**: `k0/contracts/modules/staging.update_cluster.v1.yaml`

**Module ID**: `staging.update_cluster`
**Version**: v1
**Phase**: R6

**Updates st_hipp_events columns**:

- `episode_cluster_id`: Assigned cluster UUID
- `cluster_confidence`: Similarity to cluster centroid

**SQL Template**:

```sql
UPDATE st_hipp_events
SET episode_cluster_id = :cluster_id,
    cluster_confidence = :confidence,
    updated_at_utc = :now
WHERE event_id = :event_id;
```

**Latency Budget**: 2 minutes

#### Issue 1.3.7: Create Contract - staging.update_dedup.v1.yaml

**File**: `k0/contracts/modules/staging.update_dedup.v1.yaml`

**Module ID**: `staging.update_dedup`
**Version**: v1
**Phase**: R6

**Updates st_hipp_events columns**:

- `novelty_score`: Computed novelty [0-1]
- `is_near_duplicate`: Boolean flag
- `near_duplicates_json`: Array of similar event IDs

**SQL Template**:

```sql
UPDATE st_hipp_events
SET novelty_score = :novelty,
    is_near_duplicate = :is_dup,
    near_duplicates_json = :dups_json,
    updated_at_utc = :now
WHERE event_id = :event_id;
```

**Latency Budget**: 2 minutes

#### Issue 1.3.8: Create Contract - staging.record_decisions.v1.yaml

**File**: `k0/contracts/modules/staging.record_decisions.v1.yaml`

**Module ID**: `staging.record_decisions`
**Version**: v1
**Phase**: R6

**Updates st_hipp_events columns**:

- `reconciliation_decision`: REINFORCE|EXTEND|CREATE|EVOLVE|CONTRADICT|SUPERSEDE

**SQL Template**:

```sql
UPDATE st_hipp_events
SET reconciliation_decision = :decision,
    updated_at_utc = :now
WHERE event_id = :event_id;
```

**Audit**: All decisions logged to st_audit with before/after

**Latency Budget**: 2 minutes

#### Issue 1.3.9: Create Contract - writers.truth_writer.v1.yaml

**File**: `k0/contracts/modules/writers.truth_writer.v1.yaml`

**Module ID**: `writers.truth_writer`
**Version**: v1
**Phase**: R7
**Implements**: M24 TruthWriter

**Interface** (per Section 7.4.7):

```python
async def write(
    layer: MemoryLayerType,
    action: WriteAction,  # CREATE|UPDATE|ARCHIVE|TOMBSTONE
    record: MemoryRecord,
    context: ConsolidationContext
) -> WriteResult
```

**Outbox Pattern**:

1. Insert/update target table in transaction
2. Insert outbox record in same transaction
3. Return success
4. Background worker publishes outbox → bus

**Memory Layers**:

- EPISODIC → st_epi
- SEMANTIC → st_sem
- PROCEDURAL → st_procedural
- SOCIAL → st_social
- PROSPECTIVE → st_prospective
- KG_DOMAIN → st_kg_dom
- KG_EDGES → st_kg_edges

**Latency Budget**: 10 minutes (R7 phase)

#### Issue 1.3.10: Create Contract - writers.episodic.v1.yaml

**File**: `k0/contracts/modules/writers.episodic.v1.yaml`

**Module ID**: `writers.episodic`
**Version**: v1
**Phase**: R7
**Target Table**: st_epi

**Write Actions** (per Section 4.8.2):

- CREATE: New episode record from cluster
- REINFORCE: Increment access_count, update last_accessed

**Required Fields**:

- `episode_id`: UUID
- `cluster_id`: Source episode_cluster_id
- `summary`: Compressed episode description
- `embedding_384`: Via P08 async
- `importance_score`, `emotional_valence`
- `start_time_utc`, `end_time_utc`

**Latency Budget**: 2 minutes

#### Issue 1.3.11: Create Contract - writers.semantic.v1.yaml

**File**: `k0/contracts/modules/writers.semantic.v1.yaml`

**Module ID**: `writers.semantic`
**Version**: v1
**Phase**: R7
**Target Table**: st_sem

**Write Actions** (per Section 4.8.3):

- CREATE: New semantic fact
- MERGE: Combine with existing similar fact
- EVOLVE: Create new version, supersede old
- REINFORCE: Increment observation_count

**Deduplication**: Check existing via embedding similarity > 0.9

**Required Fields**:

- `fact_id`: UUID
- `fact_text`: Canonical fact statement
- `category`: FACT|PREFERENCE|BELIEF|SKILL
- `confidence`, `observation_count`
- `sources_json`: Contributing event IDs

**Latency Budget**: 2 minutes

#### Issue 1.3.12: Create Contract - writers.procedural.v1.yaml

**File**: `k0/contracts/modules/writers.procedural.v1.yaml`

**Module ID**: `writers.procedural`
**Version**: v1
**Phase**: R7
**Target Table**: st_procedural

**Write Actions** (per Section 4.8.4):

- CREATE: New routine/habit/skill
- REINFORCE: Increment execution_count
- EVOLVE: Habit pattern changed

**Routine Detection**: Same action + same time (±30 min) + 3+ occurrences

**Required Fields**:

- `routine_id`: UUID
- `routine_name`: Descriptive name
- `category`: ROUTINE|HABIT|SKILL|WORKFLOW
- `trigger_pattern_json`: Temporal/contextual triggers
- `execution_count`, `last_executed_utc`

**Latency Budget**: 1 minute

#### Issue 1.3.13: Create Contract - writers.social.v1.yaml

**File**: `k0/contracts/modules/writers.social.v1.yaml`

**Module ID**: `writers.social`
**Version**: v1
**Phase**: R7
**Target Table**: st_social

**Write Actions** (per Section 4.8.5):

- CREATE: New relationship
- EVOLVE: Relationship quality changed
- UPDATE: Interaction count/recency

**Required Fields**:

- `relationship_id`: UUID
- `person_id_a`, `person_id_b`: Entity IDs
- `relationship_type`: FAMILY|FRIEND|COLLEAGUE|ACQUAINTANCE
- `interaction_count`, `last_interaction_utc`
- `sentiment_avg`: Running average sentiment

**Latency Budget**: 1 minute

#### Issue 1.3.14: Create Contract - writers.prospective.v1.yaml

**File**: `k0/contracts/modules/writers.prospective.v1.yaml`

**Module ID**: `writers.prospective`
**Version**: v1
**Phase**: R7
**Target Table**: st_prospective

**Write Actions** (per Section 4.8.6):

- CREATE: New goal/intention/reminder
- UPDATE: Progress update
- COMPLETE: Mark as achieved
- EXPIRE: Past deadline

**Required Fields**:

- `intention_id`: UUID
- `intention_type`: GOAL|TASK|REMINDER|ASPIRATION
- `description`: What to remember
- `target_date_utc`: Optional deadline
- `priority`: HIGH|MEDIUM|LOW
- `status`: ACTIVE|COMPLETED|EXPIRED|CANCELLED

**Latency Budget**: 1 minute

#### Issue 1.3.15: Create Contract - writers.kg.v1.yaml

**File**: `k0/contracts/modules/writers.kg.v1.yaml`

**Module ID**: `writers.kg`
**Version**: v1
**Phase**: R7
**Target Tables**: st_kg_dom, st_kg_edges

**Write Actions** (per Section 4.8.7):

**For st_kg_dom** (entities):

- CREATE: New entity node
- MERGE: Alias resolution
- UPDATE: observation_count, properties

**For st_kg_edges** (relationships):

- CREATE: New edge between entities
- REINFORCE: Increment weight via Hebbian rule
- EVOLVE: Relationship type changed

**Required Fields for st_kg_dom**:

- `node_id`: UUID
- `entity_type`: 9 general + 12 family types
- `canonical_name`: Normalized name
- `properties_json`: Flexible attributes

**Required Fields for st_kg_edges**:

- `edge_id`: UUID
- `source_id`, `target_id`: Node IDs
- `relationship_type`: Edge label
- `weight`: [0-1] Hebbian strength
- `evidence_json`: Supporting events

**Latency Budget**: 2 minutes

#### Issue 1.3.16: Create Contract - writers.vec_placeholder.v1.yaml

**File**: `k0/contracts/modules/writers.vec_placeholder.v1.yaml`

**Module ID**: `writers.vec_placeholder`
**Version**: v1
**Phase**: R7
**Target Table**: st_vec

**Purpose**: Create placeholder rows for P08 embedding pipeline

**NO st_embedding_queue** - Direct st_vec insert with status='PENDING'

**SQL Template**:

```sql
INSERT INTO st_vec (
    vec_id, tenant_id, space_id,
    source_table, source_id,
    status, requested_at_utc, created_at_utc
) VALUES (
    :vec_id, :tenant_id, :space_id,
    :source_table, :source_id,
    'PENDING', :now, :now
)
ON CONFLICT (source_table, source_id) DO NOTHING;
```

**P08 Coordination**:

- Emit `p08.embedding.requested.v1` event
- P08 fills embedding_384, faiss_id, updates status='COMPLETED'

**Latency Budget**: 1 minute

#### Issue 1.3.17: Create Contract - consolidation.event_emit.v1.yaml

**File**: `k0/contracts/modules/consolidation.event_emit.v1.yaml`

**Module ID**: `consolidation.event_emit`
**Version**: v1
**Phase**: R8

**Output Events** (per Section 4.9.1):

- `p03.consolidation.completed.v1`: Cycle summary
- `p03.truth.created.v1`: New memory layer record
- `p03.truth.evolved.v1`: Version update
- `p03.truth.archived.v1`: Moved to archive
- `p03.kg.node.created.v1`: New entity
- `p03.kg.edge.created.v1`: New relationship
- `p03.gaps.detected.v1`: Missing information

**Outbox Pattern**:

1. Insert event to st_outbox in R7 transactions
2. Background outbox worker publishes to bus
3. Consumer pipelines (P04, P06, P07) receive

**Latency Budget**: 1 minute

#### Issue 1.3.18: Create Contract - consolidation.gap_detector.v1.yaml

**File**: `k0/contracts/modules/consolidation.gap_detector.v1.yaml`

**Module ID**: `consolidation.gap_detector`
**Version**: v1
**Phase**: R8
**Implements**: M25 GapDetector

**Interface** (per Section 7.4.8):

```python
async def detect(
    consolidated_data: ConsolidationOutput,
    existing_knowledge: KnowledgeGraph
) -> List[Gap]
```

**Gap Types**:

- TEMPORAL: Missing time periods in routines
- ENTITY: Mentioned but undefined person/place
- RELATIONSHIP: Unclear connection between entities
- CONTEXT: Ambiguous reference needing clarification
- PROCEDURAL: Incomplete workflow/routine

**Output**: `Gap` containing:

- `gap_id`: UUID
- `gap_type`: Enum above
- `description`: Human-readable gap
- `priority`: HIGH|MEDIUM|LOW
- `suggested_questions`: For P06 to ask

**P06 Integration**: Emit `p03.gaps.detected.v1` → P06 clarification pipeline

**Latency Budget**: 2 minutes

#### Issue 1.3.19: Create Contract - consolidation.offset_update.v1.yaml

**File**: `k0/contracts/modules/consolidation.offset_update.v1.yaml`

**Module ID**: `consolidation.offset_update`
**Version**: v1
**Phase**: R8

**Purpose**: Track pipeline progress for exactly-once semantics

**Updates st_offsets** (per Section 4.9.2):

```sql
INSERT INTO st_offsets (pipeline_id, tenant_id, space_id, last_offset, updated_at_utc)
VALUES ('P03', :tenant_id, :space_id, :last_event_time, :now)
ON CONFLICT (pipeline_id, tenant_id, space_id)
DO UPDATE SET last_offset = :last_event_time, updated_at_utc = :now;
```

**Offset Value**: `event_time_utc` of last processed event

**Latency Budget**: 10ms

#### Issue 1.3.20: Create Contract - consolidation.metrics.v1.yaml

**File**: `k0/contracts/modules/consolidation.metrics.v1.yaml`

**Module ID**: `consolidation.metrics`
**Version**: v1
**Phase**: R8

**Prometheus Metrics** (per Section 8.2):

**Counters**:

- `p03_cycles_total{status,trigger_type}`: Completed cycles
- `p03_events_processed_total{decision}`: By reconciliation decision
- `p03_memories_written_total{layer,action}`: By layer and action
- `p03_errors_total{phase,error_type}`: Errors by phase

**Histograms**:

- `p03_cycle_duration_seconds{trigger_type}`: Cycle latency
- `p03_phase_duration_seconds{phase}`: Per-phase latency
- `p03_batch_size_events{phase}`: Batch sizes

**Gauges**:

- `p03_pending_events{tenant,space}`: Backlog size
- `p03_active_cycles`: Currently running cycles

**Latency Budget**: 1ms (async metrics collection)

---

### Epic 1.4: Pipeline YAML Configuration

> **Location**: `k0/contracts/pipelines/`
> **Template**: Based on `p02_write.v1.yaml`

#### Issue 1.4.1: Create Pipeline YAML - p03_consolidation.v1.yaml

**File**: `k0/contracts/pipelines/p03_consolidation.v1.yaml`

```yaml
pipeline_id: P03
name: Consolidation Pipeline
version: v1
status: PLANNING
description: >
  Memory consolidation pipeline implementing bidirectional reconciliation
  between hippocampal staging (st_hipp_events) and neocortical truth stores.

triggers:
  - type: idle
    config:
      idle_threshold_minutes: 30
  - type: cron
    config:
      schedule: "0 2 * * *"  # 2:00 AM daily
      timezone: local
  - type: threshold
    config:
      pending_count: 5000
      check_interval_seconds: 300
  - type: manual
    config:
      require_admin: true

phases:
  - id: R0
    name: Initialization
    budget_minutes: 1
    modules:
      - consolidation.trigger
      - consolidation.lock
      - consolidation.batch_select

  - id: R1
    name: Replay
    budget_minutes: 15
    modules:
      - hippocampus.replay_coordinator
      - hippocampus.importance_score
      - hippocampus.association_strength

  - id: R2
    name: Pattern Formation
    budget_minutes: 20
    modules:
      - neocortical.episode_cluster
      - neocortical.pattern_extract
      - neocortical.ca1_bridge

  - id: R3
    name: Pruning
    budget_minutes: 10
    parallel_group: synaptic
    modules:
      - synaptic.duplicate_detect
      - synaptic.novelty_score
      - synaptic.retention_enforce

  - id: R4
    name: Knowledge Graph
    budget_minutes: 25
    parallel_group: synaptic  # Runs parallel to R3
    modules:
      - kg.entity_normalize
      - kg.relationship_discover
      - kg.temporal_update
      - kg.consolidator

  - id: R5
    name: Dream (Optional)
    budget_minutes: 20
    optional: true
    feature_flag: dream_phase_enabled
    modules:
      - dream.counterfactual
      - dream.prediction
      - dream.insight
      - dream.explorer

  - id: R6
    name: Staging Update
    budget_minutes: 10
    modules:
      - staging.update_status
      - staging.update_cluster
      - staging.update_dedup
      - staging.record_decisions

  - id: R7
    name: Truth Write
    budget_minutes: 10
    modules:
      - writers.truth_writer
      - writers.episodic
      - writers.semantic
      - writers.procedural
      - writers.social
      - writers.prospective
      - writers.kg
      - writers.vec_placeholder

  - id: R8
    name: Finalization
    budget_minutes: 5
    modules:
      - consolidation.event_emit
      - consolidation.gap_detector
      - consolidation.offset_update
      - consolidation.metrics

output_events:
  - p03.consolidation.completed.v1
  - p03.truth.created.v1
  - p03.truth.evolved.v1
  - p03.truth.archived.v1
  - p03.kg.node.created.v1
  - p03.kg.edge.created.v1
  - p03.gaps.detected.v1

total_budget_minutes: 116  # Without R5: 96 minutes
```

#### Issue 1.4.2: Define Trigger Configuration

**File**: `k0/contracts/pipelines/p03_consolidation.v1.yaml` (triggers section)

**Trigger Types** (per Section 4.1):

| Type | Condition | Priority | Notes |
|------|-----------|----------|-------|
| IDLE | User inactive 30+ min | 1 (lowest) | Background processing |
| CRON | 2:00 AM local daily | 2 | Guaranteed daily run |
| THRESHOLD | pending > 5000 | 3 | Backlog prevention |
| MANUAL | Admin API call | 4 (highest) | Override all |

**Trigger Detection Module**: `k0/modules/consolidation/trigger.py`

**Implementation**:

```python
class TriggerDetector:
    async def check_idle(self, tenant_id: str) -> bool:
        last_activity = await self.get_last_activity(tenant_id)
        return (now() - last_activity).minutes >= 30

    async def check_threshold(self, tenant_id: str, space_id: str) -> bool:
        pending = await self.count_pending_events(tenant_id, space_id)
        return pending >= 5000
```

#### Issue 1.4.3: Define Required Capabilities (28 total)

**File**: `k0/contracts/pipelines/p03_consolidation.v1.yaml` (capabilities section)

**Capabilities** (per Section 9 and capability-based security ADR):

```yaml
capabilities:
  # Database Read Capabilities (10)
  - db:read:st_hipp_events
  - db:read:st_offsets
  - db:read:st_epi
  - db:read:st_sem
  - db:read:st_procedural
  - db:read:st_social
  - db:read:st_prospective
  - db:read:st_kg_dom
  - db:read:st_kg_edges
  - db:read:st_vec

  # Database Write Capabilities (10)
  - db:write:st_hipp_events
  - db:write:st_epi
  - db:write:st_sem
  - db:write:st_procedural
  - db:write:st_social
  - db:write:st_prospective
  - db:write:st_kg_dom
  - db:write:st_kg_edges
  - db:write:st_vec
  - db:write:st_offsets

  # Bus Capabilities (3)
  - bus:emit:p03.*
  - bus:emit:p08.embedding.requested.v1
  - bus:consume:p08.embedding.completed.v1

  # Lock Capabilities (2)
  - lock:acquire:consolidation
  - lock:release:consolidation

  # Observability Capabilities (3)
  - metrics:emit:p03.*
  - traces:emit:p03.*
  - logs:emit:p03.*
```

#### Issue 1.4.4: Define Parallel Groups (R3/R4)

**File**: `k0/contracts/pipelines/p03_consolidation.v1.yaml` (parallel_groups section)

**Parallel Execution** (per Issue 0.2.2):

```yaml
parallel_groups:
  synaptic:
    phases: [R3, R4]
    strategy: concurrent
    combined_budget_minutes: 25
    join_point: R6
    failure_handling:
      mode: partial_success
      min_required: 1  # At least one phase must complete
```

**Execution Flow**:

```
R0 → R1 → R2 → [R3 ║ R4] → R5? → R6 → R7 → R8
                  ↓
              join_point
```

**Budget Optimization**:

- R3 (10 min) and R4 (25 min) run in parallel
- Combined budget: max(10, 25) = 25 min vs sequential 35 min
- Savings: 10 minutes per cycle

---

### Epic 1.5: K0 Architecture Master - M1 Registration

> **File**: `k0/pipelines/k0_architecture_master.md`
> **Purpose**: Single source of truth for all K0 registries

#### Issue 1.5.1: Update Event Topics Registry (Part 4.1)

**Section**: Part 4.1 - Event Topics Registry

**P03 Event Topics** (per Section 9.6):

| Topic | Schema | Publisher | Consumers | Description |
|-------|--------|-----------|-----------|-------------|
| `p03.consolidation.triggered.v1` | JSON | P03.R0 | P03.R0 | Cycle started |
| `p03.batch.selected.v1` | JSON | P03.R0 | P03.R1 | Batch ready for replay |
| `p03.replay.complete.v1` | JSON | P03.R1 | P03.R2 | Replay phase done |
| `p03.cluster.formed.v1` | JSON | P03.R2 | P03.R3,R4 | Episode clusters created |
| `p03.consolidation.completed.v1` | JSON | P03.R8 | P04, P07 | Cycle summary |
| `p03.truth.created.v1` | JSON | P03.R7 | P04 | New memory record |
| `p03.truth.evolved.v1` | JSON | P03.R7 | P04 | Version update |
| `p03.gaps.detected.v1` | JSON | P03.R8 | P06 | Knowledge gaps |

**Schema Location**: `k0/contracts/schemas/events/p03/`

#### Issue 1.5.2: Update Contract Registry (Part 5.1)

**Section**: Part 5.1 - Global Contract Registry

**P03 Contracts**:

| Contract ID | Type | Version | File |
|-------------|------|---------|------|
| `consolidation.trigger` | module | v1 | `k0/contracts/modules/consolidation.trigger.v1.yaml` |
| `consolidation.lock` | module | v1 | `k0/contracts/modules/consolidation.lock.v1.yaml` |
| `consolidation.batch_select` | module | v1 | `k0/contracts/modules/consolidation.batch_select.v1.yaml` |
| `hippocampus.replay_coordinator` | module | v1 | `k0/contracts/modules/hippocampus.replay_coordinator.v1.yaml` |
| `hippocampus.importance_score` | module | v1 | `k0/contracts/modules/hippocampus.importance_score.v1.yaml` |
| `hippocampus.association_strength` | module | v1 | `k0/contracts/modules/hippocampus.association_strength.v1.yaml` |
| `neocortical.episode_cluster` | module | v1 | `k0/contracts/modules/neocortical.episode_cluster.v1.yaml` |
| `neocortical.pattern_extract` | module | v1 | `k0/contracts/modules/neocortical.pattern_extract.v1.yaml` |
| `neocortical.ca1_bridge` | module | v1 | `k0/contracts/modules/neocortical.ca1_bridge.v1.yaml` |
| `synaptic.duplicate_detect` | module | v1 | `k0/contracts/modules/synaptic.duplicate_detect.v1.yaml` |
| `synaptic.novelty_score` | module | v1 | `k0/contracts/modules/synaptic.novelty_score.v1.yaml` |
| `synaptic.retention_enforce` | module | v1 | `k0/contracts/modules/synaptic.retention_enforce.v1.yaml` |
| `kg.entity_normalize` | module | v1 | `k0/contracts/modules/kg.entity_normalize.v1.yaml` |
| `kg.relationship_discover` | module | v1 | `k0/contracts/modules/kg.relationship_discover.v1.yaml` |
| `kg.temporal_update` | module | v1 | `k0/contracts/modules/kg.temporal_update.v1.yaml` |
| `kg.consolidator` | module | v1 | `k0/contracts/modules/kg.consolidator.v1.yaml` |
| `dream.explorer` | module | v1 | `k0/contracts/modules/dream.explorer.v1.yaml` |
| `staging.*` | module | v1 | `k0/contracts/modules/staging.*.v1.yaml` |
| `writers.*` | module | v1 | `k0/contracts/modules/writers.*.v1.yaml` |
| `consolidation.event_emit` | module | v1 | `k0/contracts/modules/consolidation.event_emit.v1.yaml` |
| `consolidation.gap_detector` | module | v1 | `k0/contracts/modules/consolidation.gap_detector.v1.yaml` |
| `p03_consolidation` | pipeline | v1 | `k0/contracts/pipelines/p03_consolidation.v1.yaml` |
| `P03_tables` | schema | v1 | `k0/contracts/table_schemas/P03_tables_schema.yaml` |

#### Issue 1.5.3: Update Syscall Matrix (Part 5.2)

**Section**: Part 5.2 - Syscall Matrix

**P03 Capabilities** (28 total):

| Capability | Module | Operation | Table/Resource |
|------------|--------|-----------|----------------|
| `db:read:st_hipp_events` | batch_select, replay | SELECT | st_hipp_events |
| `db:read:st_offsets` | batch_select | SELECT | st_offsets |
| `db:read:st_epi` | ca1_bridge | SELECT | st_epi |
| `db:read:st_sem` | ca1_bridge | SELECT | st_sem |
| `db:read:st_procedural` | ca1_bridge | SELECT | st_procedural |
| `db:read:st_social` | ca1_bridge | SELECT | st_social |
| `db:read:st_prospective` | ca1_bridge | SELECT | st_prospective |
| `db:read:st_kg_dom` | kg.*, ca1_bridge | SELECT | st_kg_dom |
| `db:read:st_kg_edges` | kg.*, ca1_bridge | SELECT | st_kg_edges |
| `db:read:st_vec` | replay, cluster | SELECT | st_vec |
| `db:write:st_hipp_events` | staging.* | UPDATE | st_hipp_events |
| `db:write:st_epi` | writers.episodic | INSERT/UPDATE | st_epi |
| `db:write:st_sem` | writers.semantic | INSERT/UPDATE | st_sem |
| `db:write:st_procedural` | writers.procedural | INSERT/UPDATE | st_procedural |
| `db:write:st_social` | writers.social | INSERT/UPDATE | st_social |
| `db:write:st_prospective` | writers.prospective | INSERT/UPDATE | st_prospective |
| `db:write:st_kg_dom` | writers.kg | INSERT/UPDATE | st_kg_dom |
| `db:write:st_kg_edges` | writers.kg | INSERT/UPDATE | st_kg_edges |
| `db:write:st_vec` | writers.vec_placeholder | INSERT | st_vec |
| `db:write:st_offsets` | offset_update | UPSERT | st_offsets |
| `bus:emit:p03.*` | event_emit | PUBLISH | K0 bus |
| `bus:emit:p08.embedding.requested.v1` | vec_placeholder | PUBLISH | K0 bus |
| `bus:consume:p08.embedding.completed.v1` | - | SUBSCRIBE | K0 bus |
| `lock:acquire:consolidation` | lock | ACQUIRE | Distributed lock |
| `lock:release:consolidation` | lock | RELEASE | Distributed lock |
| `metrics:emit:p03.*` | metrics | EMIT | Prometheus |
| `traces:emit:p03.*` | all | EMIT | Jaeger/OTLP |
| `logs:emit:p03.*` | all | EMIT | Structured logs |

#### Issue 1.5.4: Update Module Registry (Part 3.1)

**Section**: Part 3.1 - Module Master Registry

**P03 Modules** (M18-M25 per dossier Section 7):

| Module ID | Name | Layer | Pipeline | Brain Analog |
|-----------|------|-------|----------|--------------|
| M18 | EpisodeClusterer | L3 | P03.R2 | Neocortex |
| M19 | DuplicateDetector | L3 | P03.R3 | Synaptic pruning |
| M20 | RetentionEnforcer | L3 | P03.R3 | Synaptic decay |
| M21 | KGConsolidator | L3 | P03.R4 | Association cortex |
| M22 | DreamExplorer | L3 | P03.R5 | REM sleep |
| M23 | ReplayCoordinator | L3 | P03.R1 | CA3 hippocampus |
| M24 | TruthWriter | L3 | P03.R7 | Memory commit |
| M25 | GapDetector | L3 | P03.R8 | Meta-cognition |

**Implementation Path**: `k0/modules/<module_name>/`

#### Issue 1.5.5: Update Storage Tables Registry (Part 5.3)

**Section**: Part 5.3 - Storage Tables Registry

**P03 Tables**:

| Table | Migration | Type | Owner | Primary Key |
|-------|-----------|------|-------|-------------|
| st_epi | 0028 | truth | P03 | episode_id |
| st_sem | 0029 | truth | P03 | fact_id |
| st_procedural | 0030 | truth | P03 | routine_id |
| st_social | 0031 | truth | P03 | relationship_id |
| st_prospective | 0032 | truth | P03 | intention_id |
| st_kg_dom | 0033 | truth | P03 | node_id |
| st_kg_edges | 0034 | truth | P03 | edge_id |
| st_learning_queue | 0039 | operational | P03 | queue_id |
| st_anchors | 0040 | truth | P03 | anchor_id |
| st_anchor_observations | 0041 | operational | P03 | observation_id |
| st_consolidation_locks | 0042 | operational | P03 | lock_id |

**Note**: st_vec, st_hipp_events, st_dlq already exist (P02/K0 baseline)

#### Issue 1.5.6: Update Pipeline Status to Planning

**Section**: Part 2.1 - Pipeline Master Registry

**Update P03 Row**:

| Pipeline | Name | Status | Owner | Depends On |
|----------|------|--------|-------|------------|
| P03 | Consolidation | ~~DESIGN~~ → **PLANNING** | Memory Team | P02, P08 |

**Changelog Entry**:

```
- 2024-XX-XX: P03 status changed from DESIGN to PLANNING
  - Reason: M1 contracts and schemas defined
  - Reference: P03 Implementation Plan Milestone 1
```

---

### Epic 1.6: Error Handling Infrastructure (Section 13)

**Gate**: GATE 2 (Contract Discovery)

> **Location**: `k0/modules/consolidation/errors/`
> **Reference**: Dossier Section 13 - Error Handling

#### Issue 1.6.1: Define P03ErrorHandler Class

**File**: `k0/modules/consolidation/errors/handler.py`

**Class Definition**:

```python
class P03ErrorHandler:
    """P03-specific error handling with phase-aware recovery."""

    def __init__(
        self,
        dlq_store: DLQStore,
        retry_strategy: RetryStrategyFactory,
        circuit_breaker: CircuitBreakerRegistry,
        metrics: P03Metrics
    ):
        self.dlq = dlq_store
        self.retry = retry_strategy
        self.breakers = circuit_breaker
        self.metrics = metrics

    async def handle_error(
        self,
        error: Exception,
        context: ConsolidationContext,
        phase: Phase,
        event_batch: List[HippEvent]
    ) -> ErrorResult:
        """
        Handle errors with phase-specific strategy.
        Returns: RETRY, DLQ, SKIP, or ABORT
        """

    async def handle_partial_failure(
        self,
        successful: List[HippEvent],
        failed: List[Tuple[HippEvent, Exception]],
        context: ConsolidationContext
    ) -> PartialFailureResult:
        """
        Handle partial batch failures.
        Returns: COMMIT_PARTIAL or ROLLBACK_ALL
        """
```

**Error Categories** (per Section 13.2):

| Category | Examples | Default Action |
|----------|----------|----------------|
| TRANSIENT | Network timeout, DB lock | RETRY |
| EMBEDDING | P08 unavailable | CIRCUIT_BREAKER → DLQ |
| VALIDATION | Schema mismatch | DLQ (no retry) |
| RESOURCE | OOM, disk full | ABORT cycle |
| BUSINESS | Conflict, version mismatch | SKIP event |

#### Issue 1.6.2: Define DLQ Contract for P03

**File**: `k0/contracts/modules/consolidation.dlq.v1.yaml`

**Interface** (per Section 13.4):

```python
class DLQStore(Protocol):
    async def enqueue(
        self,
        event_id: str,
        error_type: str,
        error_message: str,
        phase: str,
        retry_count: int,
        context: dict
    ) -> str:
        """Insert into st_dlq, return dlq_id."""

    async def dequeue_for_retry(
        self,
        max_items: int = 100,
        max_age_hours: int = 24
    ) -> List[DLQItem]:
        """Get items eligible for retry."""

    async def mark_processed(
        self,
        dlq_id: str,
        outcome: Literal['SUCCESS', 'PERMANENT_FAILURE']
    ) -> None:
        """Mark DLQ item as processed."""
```

**st_dlq Columns Used**:

- `dlq_id`: UUID primary key
- `tenant_id`, `space_id`: Multi-tenant context
- `source_table`: 'st_hipp_events'
- `source_id`: Original event_id
- `pipeline_id`: 'P03'
- `phase`: R0-R8
- `error_type`, `error_message`: Error details
- `retry_count`: Current retry attempt
- `max_retries`: Phase-specific max
- `next_retry_at`: Scheduled retry time
- `created_at_utc`, `updated_at_utc`: Timestamps

#### Issue 1.6.3: Define Retry Strategy Configuration

**File**: `k0/config/consolidation/retry_strategies.yaml`

**Phase-Specific Retry Policies** (per Section 13.3.2):

```yaml
retry_strategies:
  R0:  # Initialization
    initial_delay_seconds: 2
    max_retries: 5
    backoff: exponential
    max_delay_seconds: 30

  R1:  # Replay
    initial_delay_seconds: 5
    max_retries: 3
    backoff: exponential
    max_delay_seconds: 60

  R2:  # Pattern Formation
    initial_delay_seconds: 10
    max_retries: 2
    backoff: linear
    max_delay_seconds: 30

  R3:  # Pruning
    initial_delay_seconds: 5
    max_retries: 3
    backoff: exponential
    max_delay_seconds: 60

  R4:  # KG Update
    initial_delay_seconds: 5
    max_retries: 3
    backoff: exponential
    max_delay_seconds: 60

  R5:  # Dream (optional)
    initial_delay_seconds: 30
    max_retries: 1
    backoff: none
    max_delay_seconds: 30
    skip_on_failure: true  # Optional phase

  R6:  # Staging Update
    initial_delay_seconds: 3
    max_retries: 5
    backoff: exponential
    max_delay_seconds: 30

  R7:  # Truth Write (CRITICAL)
    initial_delay_seconds: 5
    max_retries: 5
    backoff: exponential
    max_delay_seconds: 120
    dlq_on_exhaust: true

  R8:  # Finalization
    initial_delay_seconds: 2
    max_retries: 3
    backoff: exponential
    max_delay_seconds: 30
```

#### Issue 1.6.4: Define Circuit Breaker Configuration

**File**: `k0/config/consolidation/circuit_breakers.yaml`

**Circuit Breakers** (per Section 13.3.1):

```yaml
circuit_breakers:
  p08_embedding:
    name: P08 Embedding Service
    failure_threshold: 5
    success_threshold: 2
    timeout_seconds: 30
    half_open_max_calls: 3
    fallback: use_cached_embedding

  database:
    name: Database Connection
    failure_threshold: 10
    success_threshold: 3
    timeout_seconds: 60
    half_open_max_calls: 5
    fallback: abort_cycle

  lock_service:
    name: Distributed Lock
    failure_threshold: 3
    success_threshold: 2
    timeout_seconds: 10
    half_open_max_calls: 2
    fallback: retry_next_cycle
```

**Circuit Breaker States**:

- CLOSED: Normal operation
- OPEN: Failing, reject calls immediately
- HALF_OPEN: Testing if service recovered

#### Issue 1.6.5: Define Partial Failure Handling Policy

**File**: `k0/config/consolidation/partial_failure.yaml`

**Policy** (per Section 13.5):

```yaml
partial_failure:
  default_policy: COMMIT_PARTIAL

  thresholds:
    # Commit if at least this percentage succeeded
    commit_threshold: 0.80  # 80% success required

    # Rollback if failure rate exceeds this
    rollback_threshold: 0.50  # >50% failure = rollback

  per_phase:
    R1:
      policy: COMMIT_PARTIAL
      threshold: 0.70  # Replay can lose some

    R7:
      policy: COMMIT_PARTIAL
      threshold: 0.95  # Truth writes must mostly succeed
      dlq_failures: true

  actions:
    COMMIT_PARTIAL:
      - commit_successful_events
      - enqueue_failed_to_dlq
      - emit_partial_success_metric
      - continue_to_next_phase

    ROLLBACK_ALL:
      - rollback_transaction
      - enqueue_all_to_dlq
      - emit_rollback_metric
      - schedule_retry_cycle
```

**Decision Logic**:

```python
def decide_partial_failure(
    success_count: int,
    failure_count: int,
    phase: Phase,
    config: PartialFailureConfig
) -> PartialFailureAction:
    total = success_count + failure_count
    success_rate = success_count / total if total > 0 else 0

    phase_config = config.per_phase.get(phase, config.default)

    if success_rate >= phase_config.threshold:
        return PartialFailureAction.COMMIT_PARTIAL
    elif success_rate < (1 - config.rollback_threshold):
        return PartialFailureAction.ROLLBACK_ALL
    else:
        return PartialFailureAction.COMMIT_PARTIAL  # Default
```

---

### Epic 1.7: Security & Privacy Infrastructure (Section 14)

**Gate**: GATE 2 (Contract Discovery)

> **Location**: `k0/modules/consolidation/security/`
> **Reference**: Dossier Section 14 - Security & Privacy

#### Issue 1.7.1: Define Privacy Band Integration

**File**: `k0/contracts/modules/consolidation.privacy.v1.yaml`

**Privacy Bands** (per Section 14.2):

| Band | Read | Write | Audit Level | Notes |
|------|------|-------|-------------|-------|
| GREEN | Full | Full | Minimal | General family info |
| AMBER | Full | Full | Full | Sensitive personal |
| RED | Masked | Full | Full + Encrypt | Medical, financial, legal |

**Band Inheritance Rules**:

- Event band inherits to extracted facts
- Highest band in cluster = cluster band
- Truth record band = max(contributing_event_bands)

**Interface**:

```python
class PrivacyBandHandler:
    def get_event_band(self, event: HippEvent) -> PrivacyBand:
        """Get privacy band from event metadata."""

    def mask_for_read(self, data: dict, band: PrivacyBand) -> dict:
        """Apply masking rules for read operations."""

    def apply_band_to_truth(
        self,
        truth_record: TruthRecord,
        source_bands: List[PrivacyBand]
    ) -> PrivacyBand:
        """Determine truth record band from sources."""
```

**Masking Rules for RED band**:

- Names → First initial + "***"
- Dates → Year only
- Amounts → Range ("$1K-$5K")
- Locations → City only
- Medical → Category only ("medical appointment")

#### Issue 1.7.2: Define ACL Integration Contract

**File**: `k0/contracts/modules/consolidation.acl.v1.yaml`

**K0 Policy Engine Integration** (per Section 14.3):

```python
from k0.policy import PolicyEngine

class ConsolidationACL:
    def __init__(self, policy_engine: PolicyEngine):
        self.policy = policy_engine

    async def check_access(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str,
        action: str
    ) -> AccessDecision:
        """
        Check if principal can perform action on resource.

        Returns: AccessDecision(allowed, reason, audit_id)
        """
        return await self.policy.check_access(
            principal=principal_id,
            resource=f"{resource_type}:{resource_id}",
            action=action,
            context={"pipeline": "P03"}
        )

    async def check_batch_access(
        self,
        principal_id: str,
        events: List[HippEvent],
        action: str
    ) -> Dict[str, AccessDecision]:
        """Batch access check for efficiency."""
```

**Resource Types**:

- `event`: st_hipp_events records
- `episode`: st_epi records
- `fact`: st_sem records
- `entity`: st_kg_dom records
- `relationship`: st_kg_edges records

**Actions**:

- `read`: Query existing data
- `write`: Create/update truth records
- `archive`: Move to archive status
- `tombstone`: Mark as deleted

#### Issue 1.7.3: Define Location Privacy Rules

**File**: `k0/config/consolidation/location_privacy.yaml`

**Coordinate Precision by Band** (per Section 14.3.3):

```yaml
location_privacy:
  precision_by_band:
    GREEN:
      coordinate_decimals: 4  # ~11m precision
      include_address: true
      include_place_name: true

    AMBER:
      coordinate_decimals: 3  # ~111m precision
      include_address: false
      include_place_name: true

    RED:
      coordinate_decimals: 1  # ~11km precision
      include_address: false
      include_place_name: false
      fuzzy_to_city: true

  special_locations:
    home:
      min_band: AMBER
      default_precision: city

    work:
      min_band: AMBER
      default_precision: neighborhood

    medical:
      min_band: RED
      default_precision: city
```

**Implementation**:

```python
def apply_location_privacy(
    location: Location,
    band: PrivacyBand,
    config: LocationPrivacyConfig
) -> Location:
    precision = config.precision_by_band[band]

    return Location(
        latitude=round(location.latitude, precision.coordinate_decimals),
        longitude=round(location.longitude, precision.coordinate_decimals),
        address=location.address if precision.include_address else None,
        place_name=location.place_name if precision.include_place_name else None,
        city=location.city,  # Always included
        country=location.country  # Always included
    )
```

#### Issue 1.7.4: Define Decision Audit Schema

**File**: `k0/contracts/table_schemas/P03_audit_schema.yaml`

**st_consolidation_audit Columns** (per Section 14.5.1):

```yaml
table_name: st_consolidation_audit
description: Audit log for consolidation decisions

columns:
  - name: audit_id
    type: TEXT
    primary_key: true
    description: UUID for audit record

  - name: tenant_id
    type: TEXT
    not_null: true

  - name: space_id
    type: TEXT
    not_null: true

  - name: cycle_id
    type: TEXT
    not_null: true
    description: Consolidation cycle UUID

  - name: phase
    type: TEXT
    not_null: true
    description: R0-R8

  - name: event_id
    type: TEXT
    description: Source event (if applicable)

  - name: decision
    type: TEXT
    not_null: true
    description: REINFORCE|EXTEND|CREATE|EVOLVE|CONTRADICT|SUPERSEDE|SKIP|DLQ

  - name: target_table
    type: TEXT
    description: Affected truth table

  - name: target_id
    type: TEXT
    description: Affected record ID

  - name: before_json
    type: TEXT
    description: State before change (encrypted for RED band)

  - name: after_json
    type: TEXT
    description: State after change (encrypted for RED band)

  - name: privacy_band
    type: TEXT
    not_null: true
    description: GREEN|AMBER|RED

  - name: principal_id
    type: TEXT
    description: Who triggered (system or user)

  - name: reason
    type: TEXT
    description: Decision rationale

  - name: created_at_utc
    type: TEXT
    not_null: true

indexes:
  - name: idx_audit_cycle
    columns: [cycle_id]
  - name: idx_audit_event
    columns: [event_id]
  - name: idx_audit_target
    columns: [target_table, target_id]
  - name: idx_audit_decision
    columns: [decision, created_at_utc]
```

**Migration**: `0043_p03_audit_table.sql`

#### Issue 1.7.5: Define GDPR Erasure Hooks

**File**: `k0/contracts/modules/consolidation.gdpr.v1.yaml`

**Erasure Interface** (per Section 14.4):

```python
class GDPRErasureHandler:
    """Handle right-to-be-forgotten requests across all truth tables."""

    async def erase_entity(
        self,
        tenant_id: str,
        entity_id: str,
        cascade: bool = True
    ) -> ErasureResult:
        """
        Erase all records related to an entity.

        Cascade order:
        1. st_kg_edges (relationships involving entity)
        2. st_kg_dom (entity node)
        3. st_social (relationships)
        4. st_epi (episodes mentioning entity)
        5. st_sem (facts about entity)
        6. st_procedural (routines with entity)
        7. st_prospective (intentions about entity)
        8. st_hipp_events (source events)
        """

    async def anonymize_entity(
        self,
        tenant_id: str,
        entity_id: str
    ) -> AnonymizeResult:
        """
        Anonymize rather than delete (softer erasure).
        Replace entity references with anonymous placeholder.
        """
```

**Cascade Tombstone Pattern**:

```sql
-- Step 1: Mark all related records with tombstone
UPDATE st_kg_edges
SET is_tombstone = TRUE,
    tombstone_reason = 'GDPR_ERASURE',
    tombstone_at_utc = :now
WHERE (source_id = :entity_id OR target_id = :entity_id)
  AND tenant_id = :tenant_id;

-- Repeat for each truth table...

-- Step 2: Emit erasure event for downstream cleanup
INSERT INTO st_outbox (event_type, payload)
VALUES ('p03.entity.erased.v1', :erasure_summary);
```

**Retention After Erasure**:

- Audit records: Retained but entity_id anonymized
- Aggregate statistics: Retained (no PII)
- Raw events: Tombstoned, not deleted (for consistency)

---

### Epic 1.8: Performance Tuning Infrastructure (Section 15)

**Gate**: GATE 2 (Contract Discovery)

> **Location**: `k0/config/consolidation/performance/`
> **Reference**: Dossier Section 15 - Performance Optimization

#### Issue 1.8.1: Define K0 QoS Integration Contract

**File**: `k0/contracts/modules/consolidation.qos.v1.yaml`

**K0 QoS Token Bucket Integration** (per Section 15.1):

```python
from k0.qos import TokenBucket, QoSManager

class ConsolidationQoS:
    """QoS integration for P03 resource management."""

    # Token budgets per phase
    PHASE_BUDGETS = {
        'R1': {'embedding.read': 50_000, 'compute.light': 10_000},
        'R2': {'compute.medium': 50_000, 'embedding.read': 20_000},
        'R3': {'compute.light': 20_000},
        'R4': {'embedding.read': 100_000, 'compute.light': 30_000},
        'R5': {'attention.compute': 10_000},  # Optional
        'R6': {'storage.write': 10_000},
        'R7': {'storage.write': 50_000},
        'R8': {'bus.emit': 5_000},
    }

    async def acquire_phase_budget(
        self,
        phase: str,
        timeout_seconds: float = 30.0
    ) -> TokenGrant:
        """Acquire token budget for phase, block if unavailable."""

    async def release_unused_tokens(
        self,
        grant: TokenGrant,
        used: Dict[str, int]
    ) -> None:
        """Return unused tokens to bucket."""

    async def check_budget_available(
        self,
        phase: str
    ) -> bool:
        """Pre-flight check if budget likely available."""
```

**Backpressure Behavior**:

- If tokens unavailable for >30s: Log warning, proceed with reduced batch
- If tokens unavailable for >60s: Defer cycle to next trigger

#### Issue 1.8.2: Define Batch Size Configuration

**File**: `k0/config/consolidation/batch_sizes.yaml`

**Adaptive Batch Sizing** (per Section 15.2):

```yaml
batch_sizing:
  # Memory-based thresholds
  memory_thresholds:
    low:
      rss_percent: 50  # <50% RSS usage
      batch_size: 10000
      parallel_workers: 4

    medium:
      rss_percent: 75  # 50-75% RSS usage
      batch_size: 1000
      parallel_workers: 2

    high:
      rss_percent: 100  # >75% RSS usage
      batch_size: 100
      parallel_workers: 1

  # Phase-specific overrides
  per_phase:
    R1:
      max_batch: 5000  # Replay memory intensive

    R2:
      max_batch: 2000  # Clustering needs full batch in memory

    R5:
      max_batch: 500   # Dream phase resource intensive

    R7:
      max_batch: 500   # Write batches for transaction safety

  # Adaptive adjustment
  adaptive:
    enabled: true
    increase_factor: 1.5
    decrease_factor: 0.5
    min_batch: 10
    check_interval_events: 100
```

**Implementation**:

```python
class AdaptiveBatchSizer:
    def get_batch_size(self, phase: str) -> int:
        memory_usage = psutil.Process().memory_percent()

        if memory_usage < 50:
            tier = 'low'
        elif memory_usage < 75:
            tier = 'medium'
        else:
            tier = 'high'

        base = self.config.memory_thresholds[tier].batch_size
        phase_max = self.config.per_phase.get(phase, {}).get('max_batch', base)

        return min(base, phase_max)
```

#### Issue 1.8.3: Define Embedding Query Optimization

**File**: `k0/contracts/modules/consolidation.embedding_query.v1.yaml`

**Batched Vector Queries to P08** (per Section 15.3):

```python
class EmbeddingQueryOptimizer:
    """Optimize embedding queries to P08 pipeline."""

    def __init__(
        self,
        p08_client: P08EmbeddingClient,
        cache: EmbeddingCache,
        batch_size: int = 100
    ):
        self.p08 = p08_client
        self.cache = cache
        self.batch_size = batch_size

    async def get_embeddings(
        self,
        event_ids: List[str]
    ) -> Dict[str, np.ndarray]:
        """
        Get embeddings for events with caching and batching.

        1. Check cache first
        2. Batch remaining into groups of 100
        3. Query P08 in parallel batches
        4. Update cache
        """

    async def similarity_search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        filters: Optional[dict] = None
    ) -> List[SimilarityResult]:
        """FAISS-backed similarity search via P08."""
```

**Caching Strategy**:

```yaml
embedding_cache:
  backend: lru_memory
  max_entries: 50000
  ttl_seconds: 3600  # 1 hour

  # Pre-warm on cycle start
  prewarm:
    enabled: true
    recent_hours: 24
    max_prewarm: 10000
```

#### Issue 1.8.4: Define PostgreSQL Session Configuration

**File**: `k0/config/consolidation/postgres_session.yaml`

> **PostgreSQL Migration Note** (2025-01): Replaces SQLite PRAGMA settings.
> PostgreSQL uses GUC (Grand Unified Configuration) via SET commands.

**PostgreSQL Optimization** (per Section 15.6):

```yaml
postgres_session:
  # Work memory for complex sorts/joins (per operation)
  work_mem: "64MB"

  # Maintenance operations (VACUUM, CREATE INDEX)
  maintenance_work_mem: "128MB"

  # Statement timeout for long-running queries
  statement_timeout: "60s"

  # Lock timeout for advisory locks
  lock_timeout: "30s"

  # Idle transaction timeout
  idle_in_transaction_session_timeout: "5min"

  # Random page cost (adjust for SSD)
  random_page_cost: 1.1

  # Effective cache size hint to planner
  effective_cache_size: "1GB"
```

**Apply on Connection** (via asyncpg pool init):

```python
async def configure_connection(conn: asyncpg.Connection):
    """Apply session-level PostgreSQL settings."""
    await conn.execute("SET work_mem = '64MB'")
    await conn.execute("SET statement_timeout = '60s'")
    await conn.execute("SET lock_timeout = '30s'")
    await conn.execute("SET idle_in_transaction_session_timeout = '5min'")
```

#### Issue 1.8.5: Define Memory Pressure Handlers

**File**: `k0/contracts/modules/consolidation.memory.v1.yaml`

**Memory Pressure Handling** (per Section 15.4.2):

```python
import gc
import psutil

class MemoryPressureHandler:
    """Handle memory pressure during consolidation."""

    # Thresholds
    WARNING_PERCENT = 70
    CRITICAL_PERCENT = 85
    EMERGENCY_PERCENT = 95

    async def check_and_respond(self) -> MemoryAction:
        """Check memory and take action if needed."""
        usage = psutil.Process().memory_percent()

        if usage >= self.EMERGENCY_PERCENT:
            return await self._emergency_action()
        elif usage >= self.CRITICAL_PERCENT:
            return await self._critical_action()
        elif usage >= self.WARNING_PERCENT:
            return await self._warning_action()
        else:
            return MemoryAction.CONTINUE

    async def _warning_action(self) -> MemoryAction:
        """70-85% usage: Reduce batch size, trigger minor GC."""
        gc.collect(generation=0)
        self.batch_sizer.reduce(factor=0.5)
        return MemoryAction.REDUCED_BATCH

    async def _critical_action(self) -> MemoryAction:
        """85-95% usage: Full GC, minimal batch, clear caches."""
        gc.collect()
        self.batch_sizer.set_minimum()
        self.cache.clear()
        return MemoryAction.MINIMAL_BATCH

    async def _emergency_action(self) -> MemoryAction:
        """95%+ usage: Abort cycle, schedule retry."""
        gc.collect()
        self.cache.clear()
        logger.error("Memory emergency, aborting consolidation cycle")
        return MemoryAction.ABORT
```

**GC Triggers**:

- After each phase completion: `gc.collect(generation=0)`
- After R2 (clustering): `gc.collect()` (full)
- After R5 (dream): `gc.collect()` (full)
- On memory warning: Adaptive based on pressure level

**Batch Reduction on Pressure**:

```yaml
memory_pressure_response:
  warning:  # 70-85%
    batch_reduction: 0.5
    gc_generation: 0
    clear_cache: false

  critical:  # 85-95%
    batch_reduction: 0.1
    gc_generation: 2  # Full
    clear_cache: true

  emergency:  # 95%+
    action: abort_cycle
    gc_generation: 2
    clear_cache: true
    schedule_retry_minutes: 30
```

---

## Milestone 2: Core Consolidation (R0-R1)

**Goal**: Implement trigger, lock, batch selection, hippocampal replay
**Gate**: GATE 3 (Implementation)
**Prerequisites**:

- M0 complete (including K0 kernel enhancements)
- M1 complete (migrations, contracts)

> **K0 Enhancement Dependency**: M2 uses the following K0 enhancements implemented in M0:
>
> - `AdvisoryLockService` (Epic 0.4): Used by R0 lock acquisition
> - `PartitionConfig` (Epic 0.5): Used for per-space consolidation
> - `PipelineContext.node_info` (Epic 0.7): Used for lock holder identification

### Epic 2.1: Trigger Detection (R0)

#### Issue 2.1.1: Implement Lock Manager Using K0 AdvisoryLockService

**Dossier Reference**: Section 4.1.4 Pre-Flight Checks, Section 4.10.2

**What to Cover**:

1. **ConsolidationLockManager Class** (`k0/modules/consolidation/lock_manager.py`):
   - **Use K0 AdvisoryLockService** (implemented in Epic 0.4)
   - Wraps K0 lock service with P03-specific semantics
   - Lock key format: `p03:consolidation:{tenant_id}:{space_id}`
   - TTL: 300 seconds default, renewable via heartbeat every 60 seconds

   ```python
   from k0.sync.advisory_lock import AdvisoryLockService, LockResult

   class ConsolidationLockManager:
       def __init__(self, lock_service: AdvisoryLockService, node_id: str):
           self._lock_service = lock_service
           self._node_id = node_id

       async def acquire(self, tenant_id: str, space_id: str, ttl_seconds: int = 300) -> LockResult:
           lock_key = f"p03:consolidation:{tenant_id}:{space_id}"
           return await self._lock_service.acquire(lock_key, self._node_id, ttl_seconds)

       async def release(self, tenant_id: str, space_id: str) -> bool:
           lock_key = f"p03:consolidation:{tenant_id}:{space_id}"
           return await self._lock_service.release(lock_key, self._node_id)

       async def heartbeat(self, tenant_id: str, space_id: str) -> bool:
           lock_key = f"p03:consolidation:{tenant_id}:{space_id}"
           return await self._lock_service.heartbeat(lock_key, self._node_id, 60)
   ```

2. **Distributed Lock Semantics**:
   - Exactly-one-writer guarantee per tenant/space
   - Stale lock detection handled by K0 AdvisoryLockService
   - Lock stealing prevention: holder_id check on release

3. **Syscalls Required**:
   - `lock_acquire`: Via K0 Syscalls (Issue 0.4.5)
   - `lock_release`: Via K0 Syscalls (Issue 0.4.5)
   - `st_consolidation_locks.heartbeat`: UPDATE acquired_at = NOW()

**Dependencies**: M1 Epic 1.2 (st_consolidation_locks DDL)

---

#### Issue 2.1.2: Implement Batch Selector

**Dossier Reference**: Section 4.1.3 Batch Selection Criteria

**What to Cover**:

1. **BatchSelector Class** (`k0/modules/consolidation/batch_selector.py`):
   - Query `st_hipp_events` for consolidation candidates
   - Filter: `consolidation_status IS NULL OR consolidation_status = 'PENDING'`
   - Recency window: configurable (default: 72 hours)
   - Priority ordering: `importance_score DESC, event_time_utc DESC`

2. **Batch Selection Query**:

   ```sql
   SELECT event_id, tenant_id, space_id, event_type, event_time_utc,
          affect_valence, affect_intensity, num_participants, novelty_score
   FROM st_hipp_events
   WHERE tenant_id = :tenant_id
     AND space_id = :space_id
     AND (consolidation_status IS NULL OR consolidation_status = 'PENDING')
     AND event_time_utc >= :window_start
   ORDER BY importance_score DESC NULLS LAST, event_time_utc DESC
   LIMIT :batch_size
   ```

3. **Batch Size Configuration**:
   - Default: 1000 events per cycle
   - Max: 5000 (prevent memory bloat)
   - Min: 10 (avoid too-small batches)

4. **Pre-Fetch Embeddings**:
   - Join with `st_vec` to fetch embeddings in same query
   - Avoid N+1 queries for similarity computation

**Syscalls Required**:

- `st_hipp_events.query`: Read-only batch selection
- `st_vec.query`: Embedding fetch for selected events

**Dependencies**: M1 Epic 1.4 (st_hipp_events consolidation_status column)

---

#### Issue 2.1.3: Implement Trigger Coordinator

**Dossier Reference**: Section 4.1.1 Trigger Mechanisms

**What to Cover**:

1. **TriggerCoordinator Class** (`k0/modules/consolidation/trigger_coordinator.py`):
   - Orchestrate 4 trigger types with priority ordering
   - Integrate with K0 TriggerEngine ABC (`k0/scheduler/triggers.py`)

2. **Trigger Types** (Priority Order):

   | Priority | Type | K0 Engine | Configuration |
   |----------|------|-----------|---------------|
   | 1 | Manual | `ManualTriggerEngine` | Admin API call |
   | 2 | Threshold | `ThresholdTriggerEngine` | `st_hipp_events` count > 500 pending |
   | 3 | Idle | `IdleTriggerEngine` | No user activity for 15 minutes |
   | 4 | Scheduled | `IntervalTriggerEngine` | Every 4 hours (cron: `0 */4 * * *`) |

3. **Trigger Spec Contract** (`k0/contracts/pipelines/p03_consolidation.v1.yaml`):

   ```yaml
   triggers:
     - id: p03_manual
       type: manual
       overlap_policy: QUEUE
     - id: p03_threshold
       type: threshold
       table: st_hipp_events
       condition: "consolidation_status IS NULL"
       threshold_count: 500
       check_interval_seconds: 60
       overlap_policy: QUEUE
     - id: p03_idle
       type: idle
       idle_minutes: 15
       overlap_policy: SKIP
     - id: p03_scheduled
       type: interval
       interval_seconds: 14400  # 4 hours
       overlap_policy: SKIP
   ```

4. **Trigger Fire Event**:
   - Emit `TriggerEvent` (from `k0/scheduler/triggers.py`)
   - Include: trigger_id, pipeline_id, fired_at, context (trigger_type, priority)

**K0 Integration**:

- Extend `TriggerEngine` ABC for `IdleTriggerEngine` if not exists
- Use existing `IntervalTriggerEngine`, `ThresholdTriggerEngine`, `ManualTriggerEngine`

**Dependencies**: K0 scheduler module (`k0/scheduler/triggers.py`)

---

#### Issue 2.1.4: Implement Pre-Flight Checks

**Dossier Reference**: Section 4.1.4 Pre-Flight Checks

**What to Cover**:

1. **PreFlightChecker Class** (`k0/modules/consolidation/pre_flight.py`):
   - Run before each consolidation cycle
   - Return: `PreFlightResult(can_proceed: bool, blockers: list[str])`

2. **Resource Availability Checks**:
   - CPU usage < 80% (via `psutil.cpu_percent()`)
   - Memory available > 512MB
   - Database connection pool: at least 2 connections available

3. **Concurrent Consolidation Prevention**:
   - Call `ConsolidationLockManager.acquire()` (Issue 2.1.1)
   - If lock acquisition fails → abort with `LOCK_HELD` blocker

4. **User Activity Monitoring**:
   - Query P05 Attention Router for active sessions
   - If active sessions > 0 for tenant/space → yield (unless Manual trigger)
   - Yield timeout: 5 minutes max, then proceed anyway

5. **P08 Availability Check**:
   - Check circuit breaker state for `p08_embedding`
   - If OPEN → can still proceed but skip embedding similarity checks

6. **Pre-Flight Result Schema**:

   ```python
   @dataclass
   class PreFlightResult:
       can_proceed: bool
       blockers: list[str]  # e.g., ['LOCK_HELD', 'USER_ACTIVE', 'LOW_MEMORY']
       warnings: list[str]  # e.g., ['P08_CIRCUIT_OPEN']
       resource_snapshot: dict  # CPU%, mem_available, db_pool_size
   ```

**Dependencies**: Issue 2.1.1 (Lock Manager), P05 contract (availability query)

---

#### Issue 2.1.5: Integrate with K0 PipelineScheduler

**Dossier Reference**: Section 4.10.3 K0 Integration Points

**What to Cover**:

1. **Pipeline Registration**:
   - Register P03 with `PipelineScheduler` (`k0/scheduler/scheduler.py`)
   - Pipeline spec: `ScheduledPipeline(pipeline_id="P03_CONSOLIDATION", ...)`

2. **SingleFlightGate Integration** (`k0/scheduler/concurrency.py`):
   - Use existing `SingleFlightGate.try_acquire()` for pipeline-level concurrency
   - Overlap policies per trigger type:
     - `INTERVAL/IDLE` → `OverlapPolicy.SKIP`
     - `THRESHOLD/MANUAL` → `OverlapPolicy.QUEUE` (max depth 1, coalesce)

3. **Pipeline Executor Callback**:

   ```python
   async def execute_p03(context: PipelineContext) -> PipelineResult:
       # 1. Pre-flight checks
       pre_flight = await pre_flight_checker.check(context.tenant_id, context.space_id)
       if not pre_flight.can_proceed:
           return PipelineResult(status="SKIPPED", reason=pre_flight.blockers)

       # 2. Acquire consolidation lock
       lock = await lock_manager.acquire(...)

       # 3. Select batch
       batch = await batch_selector.select(...)

       # 4. R1 replay (Epic 2.2)
       await replay_coordinator.replay(batch)

       # 5. Release lock
       await lock_manager.release(lock)
   ```

4. **State Transitions**:
   - Use `PipelineState` enum: `REGISTERED → STARTING → RUNNING → STOPPING → STOPPED`
   - Track execution count, last run time per scheduler statistics

5. **Pipeline Contract Registration**:
   - Path: `k0/contracts/pipelines/p03_consolidation.v1.yaml`
   - Include: triggers, capabilities, execution config

**K0 Components Used**:

- `k0/scheduler/scheduler.py`: `PipelineScheduler`, `ScheduledPipeline`
- `k0/scheduler/concurrency.py`: `SingleFlightGate`, `OverlapPolicy`
- `k0/scheduler/triggers.py`: `TriggerEngine` implementations

**Dependencies**: Issue 2.1.3 (Trigger Coordinator), Issue 2.1.4 (Pre-Flight)

---

### Epic 2.2: Hippocampal Replay (R1)

#### Issue 2.2.1: Implement Importance Scorer

**Dossier Reference**: Section 2.4 Scientific Formulas, Section 4.2.2

**What to Cover**:

1. **ImportanceScorer Class** (`k0/modules/consolidation/importance_scorer.py`):
   - Compute importance score for each event in batch
   - Formula from Dossier Section 2.4:

   ```python
   importance_score = (
       0.35 * abs(sentiment_score) * abs(affect_valence) * (1 + affect_arousal)  # Emotional
     + 0.25 * exp(-λ_recency * days_since_event)     # Recency (λ=0.05, 14-day half-life)
     + 0.20 * log(1 + access_count) / log(10)        # Access frequency
     + 0.20 * participant_count * avg_relationship_strength  # Social
   )
   ```

2. **Component Weights Configuration**:

   | Component | Weight | Source Column | Fallback |
   |-----------|--------|---------------|----------|
   | Emotional | 0.35 | `affect_valence`, `affect_intensity` | 0.5 |
   | Recency | 0.25 | `event_time_utc` → days_old | exp(-0.05 * days) |
   | Access | 0.20 | `access_count` | 0 |
   | Social | 0.20 | `num_participants`, `entities_json` | 0.1 |

3. **Weight Tuning Per Memory Layer** (configurable):
   - `st_epi`: Higher emotional weight (0.40)
   - `st_sem`: Higher access weight (0.30)
   - `st_procedural`: Higher recency weight (0.35)
   - `st_social`: Higher social weight (0.35)

4. **Emotional Salience Extraction**:
   - Use `affect_valence` (signed -1 to +1) and `affect_intensity` (0 to 1)
   - Absolute value of valence × intensity = emotional score
   - Arousal bonus: multiply by `(1 + affect_arousal)` if available

5. **Recency Decay Formula**:
   - `exp(-0.05 * days_old)` gives 14-day half-life
   - days_old = `(NOW() - event_time_utc).days`

6. **Output**: Annotate each `HippEvent` with `importance_score` float [0.0, 1.0]

**Dependencies**: M1 Epic 1.4 (affect columns), Section 2.4 formulas

---

#### Issue 2.2.2: Implement Association Strengthener

**Dossier Reference**: Section 2.4 Association Strength, Section 4.2.3

**What to Cover**:

1. **AssociationStrengthener Class** (`k0/modules/consolidation/association_strengthener.py`):
   - Implement Hebbian learning: "neurons that fire together, wire together"
   - Build association strength between co-occurring entities

2. **Hebbian Association Formula** (Section 2.4):

   ```python
   association_strength = (
       co_occurrence_count                           # How often entities appear together
     * exp(-λ_temporal * avg_time_gap_hours)         # Temporal proximity (λ=0.01)
     * (unique_contexts / total_contexts)            # Context diversity bonus
     * (1 + avg_sentiment_score)                     # Emotional significance
   )
   ```

3. **Co-Occurrence Counting**:
   - Parse `entities_json` from each event
   - For each pair (entity_a, entity_b) in same event → increment count
   - Track per (tenant_id, space_id, entity_a, entity_b)

4. **Temporal Proximity Bonus**:
   - If entities appear in events within 1 hour → max bonus
   - Decay: `exp(-0.01 * avg_hours_between_appearances)`
   - Minimum gap tracking via sliding window

5. **Context Diversity Score**:
   - Track unique activity_types where pair co-occurs
   - `unique_contexts / total_occurrences`
   - Higher diversity = stronger general association

6. **Output Format**:

   ```python
   @dataclass
   class EntityAssociation:
       entity_a_id: str
       entity_b_id: str
       association_strength: float  # 0.0 to unbounded, typically 0-100
       co_occurrence_count: int
       last_seen_together: datetime
       contexts: list[str]  # Activity types
   ```

7. **Storage Target**: Prepare for `st_kg_edges` (R4) - do not write yet, just compute

**Dependencies**: `entities_json` column in st_hipp_events

---

#### Issue 2.2.3: Implement M23 ReplayCoordinator

**Dossier Reference**: Section 4.2 R1, Section 7.4.6 M23

**What to Cover**:

1. **ReplayCoordinator Class** (`k0/modules/consolidation/replay_coordinator.py`):
   - Orchestrate hippocampal replay (R1 phase lead)
   - Batch pacing with theta rhythm metaphor (batch windows)

2. **Core Interface** (from Dossier Section 7.4.6):

   ```python
   class ReplayCoordinator:
       def __init__(self, config: ReplayConfig):
           self.importance_scorer = ImportanceScorer(config.weights)
           self.association_strengthener = AssociationStrengthener()
           self.batch_size = config.batch_size       # Default: 1000
           self.replay_speed = config.speed          # Metaphorical 10-20x

       async def select_batch(
           self,
           pending_events: AsyncIterator[HippEvent],
           max_events: int
       ) -> List[HippEvent]:
           """Select events for consolidation based on importance."""

       async def replay_batch(
           self,
           batch: List[HippEvent]
       ) -> ReplayResult:
           """Process batch: score, strengthen associations, prepare for R2."""
   ```

3. **Sharp-Wave Ripple Simulation** (CA3 pattern):
   - Process events in "ripple" bursts of 50-100 events
   - Brief pause (10ms simulated) between ripples
   - Total batch processing time tracking for metrics

4. **Batch Selection Priority** (from Dossier):
   - High emotional salience (affect_valence, affect_intensity)
   - Recent events (decay bonus)
   - Events with novel entities/activities
   - Events completing patterns

5. **Replay Output**:

   ```python
   @dataclass
   class ReplayResult:
       events_processed: int
       importance_scores: dict[str, float]  # event_id → score
       associations: list[EntityAssociation]
       replay_duration_ms: int
       ready_for_r2: list[str]  # event_ids to pass to R2
   ```

6. **Theta Rhythm Coordination**:
   - Interleave processing with user activity checks
   - If activity detected mid-batch → pause, yield, resume
   - Max pause duration: 30 seconds

**Dependencies**: Issue 2.2.1 (Importance Scorer), Issue 2.2.2 (Association Strengthener)

---

#### Issue 2.2.4: Integrate with P08 Embedding Search

**Dossier Reference**: Section 9.4 P03→P08 Contract

**What to Cover**:

1. **P08 Capability Invocation**:
   - Use `CapabilityFabric.invoke("embedding.search")` for similarity queries
   - Required for: finding existing truth matches during R2 preparation

2. **Similarity Search Interface**:

   ```python
   @dataclass
   class SimilaritySearchRequest:
       embedding: list[float]  # 768-dim UltraBERT vector
       top_k: int = 10
       min_similarity: float = 0.6
       filter_layer: str | None = None  # e.g., 'st_epi', 'st_sem'
       tenant_id: str
       space_id: str

   @dataclass
   class SimilarityMatch:
       record_id: str
       layer: str
       similarity: float  # cosine similarity 0-1
       record_type: str  # EPISODIC, SEMANTIC, etc.
   ```

3. **P08 Circuit Breaker**:
   - Check `p08_embedding` circuit breaker state before calls
   - If OPEN: skip similarity search, proceed without deduplication
   - Log warning: "P08 unavailable, consolidation proceeding without similarity checks"

4. **Batch Similarity Queries**:
   - Group events by embedding proximity
   - Send batch queries to P08 (max 100 embeddings per request)
   - Reduce P08 call count via batching

5. **Pre-Fetch Existing Embeddings**:
   - For each event's embedding → find similar existing truth records
   - Store similarity matches for R2 decision making
   - Cache results for batch duration

6. **P08 Coordinator Usage** (from Dossier Section 9.4.2):

   ```python
   coordinator = P08Coordinator(config=P08CoordinationConfig(
       mode='ASYNC',
       circuit_breaker_enabled=True,
       failure_threshold=5,
       reset_timeout_seconds=60
   ))
   ```

**K0 Integration**:

- `k0/fabric/fabric.py`: `CapabilityFabric.invoke()`
- Circuit breaker: `k0/qos/circuit_breaker.py`

**Dependencies**: P08 embedding pipeline, Section 9.4 contract

---

### Epic 2.3: R0-R1 Unit Tests

#### Issue 2.3.1: Lock Manager Tests

**Test File**: `tests/k0/modules/consolidation/test_lock_manager.py`

**What to Cover**:

1. **Lock Acquisition Tests**:
   - `test_acquire_lock_success`: First acquire succeeds, returns lock_id
   - `test_acquire_lock_already_held`: Second acquire fails with `LOCK_HELD`
   - `test_acquire_lock_different_space`: Same tenant, different space → both succeed
   - `test_acquire_lock_different_tenant`: Different tenants → both succeed

2. **Lock Release Tests**:
   - `test_release_lock_success`: Holder releases own lock → success
   - `test_release_lock_wrong_holder`: Non-holder tries to release → fails
   - `test_release_lock_not_held`: Release non-existent lock → no-op (idempotent)

3. **Stale Lock Cleanup Tests**:
   - `test_stale_lock_auto_release`: Lock older than TTL → can be acquired by new holder
   - `test_heartbeat_extends_lock`: Heartbeat before TTL → lock remains valid
   - `test_stale_lock_detection_query`: Query returns only non-stale locks

4. **Race Condition Tests**:
   - `test_concurrent_acquire_one_wins`: Two concurrent acquires → exactly one succeeds
   - `test_acquire_during_release`: Acquire while release in progress → deterministic outcome
   - `test_heartbeat_race`: Concurrent heartbeats don't corrupt lock state

5. **Performance Tests**:
   - `test_acquire_latency_p95`: < 50ms for acquisition
   - `test_cleanup_large_stale_count`: 1000 stale locks cleanup < 1 second

**Fixtures Needed**:

- `mock_db`: Test PostgreSQL database with `st_consolidation_locks` schema
- `lock_manager`: ConsolidationLockManager instance
- `test_tenant_id`, `test_space_id`: Standard test identifiers

---

#### Issue 2.3.2: Batch Selector Tests

**Test File**: `tests/k0/modules/consolidation/test_batch_selector.py`

**What to Cover**:

1. **Ordering Tests**:
   - `test_batch_orders_by_importance_desc`: Higher importance first
   - `test_batch_orders_by_time_desc`: Same importance → newer first
   - `test_null_importance_last`: NULL importance_score → end of batch

2. **Filtering Tests**:
   - `test_filters_null_consolidation_status`: Only NULL or PENDING included
   - `test_excludes_consolidated_events`: CONSOLIDATED status excluded
   - `test_respects_recency_window`: Events older than window excluded
   - `test_tenant_space_isolation`: Only returns events for specified tenant/space

3. **Batch Size Tests**:
   - `test_respects_max_batch_size`: Returns at most N events
   - `test_min_batch_threshold`: Returns empty if < 10 pending events
   - `test_over_sample_then_sort`: Fetches 2x max, sorts, returns top N

4. **Performance Tests**:
   - `test_batch_selection_1000_events_under_100ms`: Query performance
   - `test_embedding_prefetch_reduces_queries`: Single query for events + embeddings
   - `test_index_usage`: Explain plan uses `idx_hipp_events_consolidation`

5. **Edge Cases**:
   - `test_empty_table`: Returns empty list, no error
   - `test_all_events_consolidated`: Returns empty list
   - `test_mixed_spaces`: Only specified space returned

**Fixtures Needed**:

- `populated_hipp_events`: 100 events with varying importance, status, times
- `batch_selector`: BatchSelector instance with test config

---

#### Issue 2.3.3: Importance Scorer Tests

**Test File**: `tests/k0/modules/consolidation/test_importance_scorer.py`

**What to Cover**:

1. **Formula Validation Tests** (from Dossier Section 2.4):
   - `test_emotional_component_high_valence`: High |valence| × intensity → high score
   - `test_recency_component_today`: Today's event → recency ≈ 1.0
   - `test_recency_component_14_days`: 14-day old event → recency ≈ 0.5 (half-life)
   - `test_access_component_log_scale`: access_count=9 → access ≈ 1.0
   - `test_social_component_multiple_participants`: 5+ participants → social = 1.0

2. **Weight Validation Tests**:
   - `test_weights_sum_to_one`: 0.35 + 0.25 + 0.20 + 0.20 = 1.0
   - `test_custom_weights_override`: Layer-specific weights applied correctly
   - `test_zero_weight_disables_component`: weight=0 → component ignored

3. **Edge Cases**:
   - `test_null_affect_values`: NULL affect → use fallback 0.5
   - `test_null_access_count`: NULL → use 0
   - `test_negative_days_old`: Future event (clock skew) → clamp to 0
   - `test_very_old_event`: 365 days old → recency ≈ 0.0

4. **Score Range Tests**:
   - `test_score_between_0_and_1`: All scores in [0.0, 1.0]
   - `test_maximum_score_achievable`: Perfect event → score ≈ 1.0
   - `test_minimum_score_achievable`: Zero-everything event → score > 0

5. **Batch Scoring Tests**:
   - `test_batch_scoring_1000_events_under_50ms`: Performance
   - `test_batch_scoring_preserves_order`: Input order → output order match
   - `test_batch_scoring_parallel`: Async batch doesn't corrupt state

**Golden Dataset Integration**:

- Use `golden_dataset/dataset.yaml` for standardized test events
- Validate against expected importance scores

---

#### Issue 2.3.4: Trigger Coordinator Tests

**Test File**: `tests/k0/modules/consolidation/test_trigger_coordinator.py`

**What to Cover**:

1. **Trigger Type Tests**:
   - `test_manual_trigger_fires_immediately`: No delay, highest priority
   - `test_threshold_trigger_fires_at_count`: Fires when count > threshold
   - `test_idle_trigger_fires_after_inactivity`: Fires after 15 min idle
   - `test_scheduled_trigger_fires_on_interval`: Fires every 4 hours

2. **Priority Ordering Tests**:
   - `test_manual_overrides_scheduled`: Manual preempts pending scheduled
   - `test_threshold_overrides_idle`: Threshold preempts pending idle
   - `test_concurrent_triggers_priority`: Multiple triggers → highest priority wins

3. **Overlap Policy Tests** (from K0 SingleFlightGate):
   - `test_interval_trigger_skip_if_running`: SKIP policy for intervals
   - `test_threshold_trigger_queue_if_running`: QUEUE policy for threshold
   - `test_manual_trigger_queue_if_running`: QUEUE policy for manual
   - `test_queue_coalesces`: Multiple queued → only latest runs

4. **Trigger Spec Contract Tests**:
   - `test_trigger_spec_schema_valid`: YAML spec validates against schema
   - `test_trigger_ids_unique`: No duplicate trigger_id in spec
   - `test_required_fields_present`: Each trigger type has required config

5. **K0 Integration Tests**:
   - `test_trigger_engine_factory`: Correct engine type instantiated
   - `test_trigger_event_emitted`: TriggerEvent has correct fields
   - `test_trigger_callback_invoked`: Callback receives TriggerEvent

6. **Error Handling Tests**:
   - `test_threshold_check_db_error`: Retry on transient error
   - `test_idle_detection_timeout`: Timeout doesn't crash coordinator
   - `test_invalid_trigger_type`: Unknown type → clear error message

**Fixtures Needed**:

- `trigger_coordinator`: TriggerCoordinator with all 4 trigger types
- `mock_single_flight_gate`: Mock of K0 SingleFlightGate
- `mock_threshold_query`: Controllable row count for threshold tests

---

### Epic 2.8: K0 Architecture Master Closure

#### Issue 2.8.1: Milestone 2 K0 Updates

**What to Cover**:

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated to reflect M2 completion
- [ ] **Part 3.1 (Module Registry)**: M18 (EpisodeClusterer), M24 (TriggerCoordinator) rows added
- [ ] **Part 4.1 (Event Topics)**: P03 trigger events registered
- [ ] **Part 5.1 (Contract Registry)**: TriggerCoordinator module contract added
- [ ] **Part 5.2 (Syscall Matrix)**: Storage capabilities for st_hipp_events queries registered
- [ ] **Part 5.3 (Storage Tables)**: st_consolidation_triggers table documented
- [ ] **Part 7.1 (ADR Index)**: ADR status for M2 decisions updated
- [ ] **Version Header**: Document version bumped to reflect M2 completion

**K0 File**: `k0/pipelines/k0_architecture_master.md`

---

## Milestone 3: Pattern Extraction (R2)

**Goal**: Implement clustering, pattern detection, bidirectional reconciliation
**Gate**: GATE 3 (Implementation)

### Epic 3.1: Episodic Clustering

#### Issue 3.1.1: Implement M18 EpisodeClusterer

**Dossier Reference**: Section 4.3.1, Section 7.4.1

**What to Cover**:

1. **EpisodicClusterer Class** (`k0/modules/consolidation/episode_clusterer.py`):
   - DBSCAN clustering on 768-dim UltraBERT embeddings
   - Brain analogy: Dentate Gyrus pattern separation

2. **Core Interface** (from Dossier Section 7.4.1):

   ```python
   class EpisodicClusterer:
       def __init__(self, config: ClustererConfig):
           self.eps = config.eps                    # Default: 0.3 (cosine distance)
           self.min_samples = config.min_samples    # Default: 2
           self.max_cluster_size = 50
           self.temporal_window_hours = 4

       async def cluster(
           self,
           events: List[HippEvent],
           embeddings: Dict[str, np.ndarray]
       ) -> List[EpisodeCluster]
   ```

3. **DBSCAN Configuration**:

   | Parameter | Default | Description |
   |-----------|---------|-------------|
   | eps | 0.3 | Max cosine distance (1 - similarity) |
   | min_samples | 2 | Minimum events per cluster |
   | metric | precomputed | Distance matrix provided |

4. **Clustering Algorithm Steps**:
   - Step 1: Build distance matrix `(1 - cosine_similarity(emb_i, emb_j))`
   - Step 2: Apply temporal proximity bonus (events within 4 hours get 0.1 distance reduction)
   - Step 3: Run sklearn.cluster.DBSCAN with precomputed distances
   - Step 4: Post-process: split clusters > 50 events using hierarchical subdivision
   - Step 5: Calculate centroid embedding (mean of member embeddings)

5. **EpisodeCluster Dataclass**:

   ```python
   @dataclass
   class EpisodeCluster:
       cluster_id: str              # ULID
       member_events: list[str]     # event_ids
       centroid_embedding: np.ndarray  # 768-dim
       temporal_span: tuple[int, int]  # (start_utc, end_utc)
       primary_location: str | None
       participant_ids: list[str]
       cluster_confidence: float    # [0-1]
   ```

6. **Performance Target**: Cluster 1000 events < 500ms

**Dependencies**: P08 embeddings (st_vec), numpy, sklearn

---

#### Issue 3.1.2: Implement SimHash Pre-Filtering

**Dossier Reference**: Section 4.4.1 (SimHash), Section 7.4.2

**What to Cover**:

1. **SimHash Pre-Filter** (`k0/modules/consolidation/simhash_filter.py`):
   - Reduce DBSCAN distance matrix size via SimHash candidate filtering
   - Only compute embedding similarity for Hamming distance ≤ 5

2. **Pre-Filtering Algorithm**:

   ```python
   def prefilter_candidates(events: list[HippEvent]) -> list[tuple[str, str]]:
       """Return pairs of event_ids that are SimHash candidates."""
       candidates = []
       for i, e1 in enumerate(events):
           for e2 in events[i+1:]:
               hamming = popcount(e1.simhash ^ e2.simhash)
               if hamming <= 5:
                   candidates.append((e1.event_id, e2.event_id))
       return candidates
   ```

3. **Hamming Distance Thresholds**:

   | Hamming Distance | Interpretation | Action |
   |------------------|----------------|--------|
   | 0 | Exact duplicate | Skip DBSCAN, mark duplicate |
   | 1-3 | Near-duplicate | High-priority candidate |
   | 4-5 | Similar | Include in distance matrix |
   | 6+ | Different | Exclude from distance matrix |

4. **Sparse Distance Matrix**:
   - Only compute cosine similarity for candidate pairs
   - Set non-candidate distances to 1.0 (maximum distance)
   - Reduces O(n²) to O(n × avg_candidates)

5. **SimHash Source**: Use `simhash` column from `st_hipp_events` (populated by P02 via UltraBERT)

**Dependencies**: Issue 3.1.1 (EpisodeClusterer), popcount implementation

---

#### Issue 3.1.3: Implement Cluster Confidence Scoring

**Dossier Reference**: Section 7.4.1 `_calculate_cluster_confidence`

**What to Cover**:

1. **Confidence Formula** (from Dossier):

   ```python
   confidence = mean(pairwise_cosine_similarities within cluster)
   ```

2. **ClusterConfidenceScorer Class**:

   ```python
   class ClusterConfidenceScorer:
       def score(
           self,
           cluster: EpisodeCluster,
           embeddings: dict[str, np.ndarray]
       ) -> float:
           if len(cluster.member_events) < 2:
               return 0.5  # Single-event clusters get neutral confidence

           similarities = []
           for i, e1 in enumerate(cluster.member_events):
               for e2 in cluster.member_events[i+1:]:
                   sim = cosine_similarity(embeddings[e1], embeddings[e2])
                   similarities.append(sim)

           return np.mean(similarities)
   ```

3. **Confidence Interpretation**:

   | Confidence | Interpretation | Action |
   |------------|----------------|--------|
   | 0.9+ | Very tight cluster | High-priority for promotion to st_epi |
   | 0.7-0.9 | Good cluster | Standard processing |
   | 0.5-0.7 | Loose cluster | Flag for review |
   | < 0.5 | Poor cluster | Consider splitting or rejecting |

4. **Quality Gates** (from Dossier Section 4.3.4):
   - Minimum cluster size: 2 events
   - Minimum confidence: 0.5 for promotion
   - Temporal spread: at least 2 distinct timestamps

**Dependencies**: Issue 3.1.1 (EpisodeCluster output)

---

#### Issue 3.1.4: Handle Outliers (Singletons)

**Dossier Reference**: Section 7.4.1

**What to Cover**:

1. **Outlier Definition**:
   - DBSCAN label = -1 (noise points)
   - Events that don't belong to any cluster

2. **Singleton Cluster Assignment**:

   ```python
   for event_id in outlier_event_ids:
       singleton = EpisodeCluster(
           cluster_id=f"SING_{event_id}",
           member_events=[event_id],
           centroid_embedding=embeddings[event_id],
           temporal_span=(event.event_time_utc, event.event_time_utc),
           primary_location=event.location,
           participant_ids=extract_participants(event),
           cluster_confidence=0.5  # Neutral confidence
       )
   ```

3. **Singleton Handling Strategies**:

   | Strategy | Condition | Action |
   |----------|-----------|--------|
   | Promote | High importance_score (>0.7) | Create singleton st_epi record |
   | Queue | Medium importance (0.4-0.7) | Hold for next consolidation cycle |
   | Discard | Low importance (<0.4) | Mark as processed, don't promote |

4. **Singleton Metrics**:
   - `p03_singletons_total{action}`: Count by promotion/queue/discard
   - `p03_singleton_ratio`: singletons / total_events (target < 30%)

5. **Re-Clustering on Next Cycle**:
   - Queue'd singletons can join future clusters
   - Track `singleton_cycles` to prevent indefinite queuing (max 3)

**Dependencies**: Issue 3.1.1 (DBSCAN output)

---

### Epic 3.2: Pattern Extraction

#### Issue 3.2.1: Implement Routine Detection

**Dossier Reference**: Section 4.3.2 Pattern Extraction Pipeline

**What to Cover**:

1. **RoutineDetector Class** (`k0/modules/consolidation/routine_detector.py`):
   - Detect temporal patterns in clustered episodes
   - Output: `st_procedural` candidate records

2. **Temporal Pattern Types**:

   | Pattern | Detection Rule | Example |
   |---------|----------------|---------|
   | Daily | Same time ±1 hour, 3+ occurrences | "Morning coffee at 7am" |
   | Weekly | Same day of week, 3+ occurrences | "Tuesday yoga class" |
   | Monthly | Same date (±2 days), 3+ occurrences | "1st of month bills" |
   | Seasonal | Same month(s), 2+ years | "Summer vacation July" |

3. **Routine Detection Algorithm**:

   ```python
   class RoutineDetector:
       def detect(self, clusters: list[EpisodeCluster]) -> list[Routine]:
           # 1. Group clusters by activity_type
           # 2. For each group, analyze temporal distribution
           # 3. Apply pattern matching (daily, weekly, monthly)
           # 4. Calculate routine confidence from consistency
           # 5. Return routines with confidence > threshold
   ```

4. **Routine Confidence Scoring**:

   ```python
   routine_confidence = sqrt(
       frequency_score *      # How often pattern occurs
       consistency_score *    # Variance in timing
       significance_score     # Pattern vs random distribution
   )
   ```

5. **Output Schema**:

   ```python
   @dataclass
   class Routine:
       routine_id: str
       pattern_type: str  # DAILY, WEEKLY, MONTHLY, SEASONAL
       activity_type: str
       temporal_pattern: dict  # {"day_of_week": 2, "hour": 18}
       frequency: int  # Occurrences count
       confidence: float
       source_clusters: list[str]
   ```

**Dependencies**: Issue 3.1.1 (EpisodeCluster output)

---

#### Issue 3.2.2: Implement Preference Extraction

**Dossier Reference**: Section 4.3.2 Pattern Extraction Pipeline

**What to Cover**:

1. **PreferenceExtractor Class** (`k0/modules/consolidation/preference_extractor.py`):
   - Extract repeated choices and sentiment patterns
   - Output: `st_sem` candidate records (PREFERENCE type)

2. **Preference Types**:

   | Type | Detection | Example |
   |------|-----------|---------|
   | Entity Preference | Same entity, positive sentiment, 3+ times | "Loves Thai food" |
   | Activity Preference | Same activity, positive sentiment | "Enjoys hiking" |
   | Temporal Preference | Consistent time choices | "Prefers morning workouts" |
   | Location Preference | Same location visits | "Favorite coffee shop: Blue Bottle" |

3. **Preference Extraction Algorithm**:

   ```python
   class PreferenceExtractor:
       def extract(self, clusters: list[EpisodeCluster]) -> list[Preference]:
           # 1. Aggregate entity mentions across clusters
           # 2. Calculate mean sentiment per entity
           # 3. Filter: count >= 3 AND mean_sentiment > 0.3
           # 4. Rank by frequency × sentiment strength
           # 5. Return top N preferences per category
   ```

4. **Sentiment Aggregation**:
   - Use `affect_valence` from source events
   - Weight by `affect_intensity` (stronger = more signal)
   - Handle mixed sentiment: flag as AMBIVALENT if std_dev > 0.5

5. **Output Schema**:

   ```python
   @dataclass
   class Preference:
       preference_id: str
       preference_type: str  # ENTITY, ACTIVITY, TEMPORAL, LOCATION
       subject: str  # What is preferred
       valence: float  # -1 to +1 (negative = dislikes)
       intensity: float  # 0 to 1
       evidence_count: int
       confidence: float
       source_clusters: list[str]
   ```

**Dependencies**: `affect_valence`, `entities_json` columns

---

#### Issue 3.2.3: Implement Theme Identification

**Dossier Reference**: Section 4.3.2 Pattern Extraction Pipeline

**What to Cover**:

1. **ThemeIdentifier Class** (`k0/modules/consolidation/theme_identifier.py`):
   - Semantic clustering across domains
   - Output: `st_sem` candidate records (THEME type)

2. **Theme Detection Approach**:
   - Cluster centroid embeddings (from Issue 3.1.1) using hierarchical clustering
   - Group similar clusters into themes
   - Label themes via representative keyword extraction

3. **Theme Identification Algorithm**:

   ```python
   class ThemeIdentifier:
       def identify(self, clusters: list[EpisodeCluster]) -> list[Theme]:
           # 1. Collect centroid embeddings from all clusters
           # 2. Run hierarchical clustering (Ward linkage)
           # 3. Cut dendrogram at threshold to form themes
           # 4. Extract theme label via TF-IDF on member events
           # 5. Calculate theme coherence score
   ```

4. **Theme Coherence Scoring**:

   ```python
   theme_coherence = mean(cosine_similarity(centroid_i, theme_centroid))
   ```

5. **Theme Types**:

   | Category | Example Themes |
   |----------|----------------|
   | Life Domain | "Work", "Family", "Health", "Hobbies" |
   | Relationship | "Friends_Group_A", "Colleagues" |
   | Interest | "Photography", "Cooking", "Travel" |
   | Temporal | "Weekend_Activities", "Workday_Routine" |

6. **Output Schema**:

   ```python
   @dataclass
   class Theme:
       theme_id: str
       theme_label: str  # Human-readable label
       theme_type: str  # DOMAIN, RELATIONSHIP, INTEREST, TEMPORAL
       member_clusters: list[str]
       coherence: float
       keywords: list[str]  # Top 5 representative words
   ```

**Dependencies**: Issue 3.1.1 (cluster centroid embeddings), scipy.cluster.hierarchy

---

#### Issue 3.2.4: Implement Relationship Pattern Mining

**Dossier Reference**: Section 4.3.2, Section 4.5 (R4 KG)

**What to Cover**:

1. **RelationshipMiner Class** (`k0/modules/consolidation/relationship_miner.py`):
   - Social graph pattern extraction
   - Output: `st_social` and `st_kg_edges` candidate records

2. **Relationship Patterns**:

   | Pattern | Detection | Example |
   |---------|-----------|---------|
   | Dyad | 2 people, 5+ co-occurrences | "Best friend: Alice" |
   | Group | 3+ people, frequent co-occurrence | "Hiking group" |
   | Role | Person + context pattern | "Work colleague: Bob" |
   | Temporal | Relationship timing patterns | "Weekend friend: Carol" |

3. **Co-Occurrence Analysis** (Hebbian):

   ```python
   class RelationshipMiner:
       def mine(self, clusters: list[EpisodeCluster]) -> list[Relationship]:
           # 1. Extract participant_ids from all clusters
           # 2. Build co-occurrence matrix (person × person)
           # 3. Apply temporal weighting (recent = stronger)
           # 4. Detect cliques for group relationships
           # 5. Infer relationship types from context
   ```

4. **Relationship Strength Formula** (from Dossier Section 2.4):

   ```python
   strength = (
       co_occurrence_count
     * exp(-0.01 * avg_days_between)
     * (unique_contexts / total_contexts)
     * (1 + avg_sentiment)
   )
   ```

5. **Output Schema**:

   ```python
   @dataclass
   class Relationship:
       relationship_id: str
       relationship_type: str  # DYAD, GROUP, ROLE, TEMPORAL
       participants: list[str]  # person_ids
       strength: float
       context: str  # Primary activity context
       first_seen: datetime
       last_seen: datetime
       source_clusters: list[str]
   ```

6. **Group Detection**:
   - Use community detection (Louvain algorithm) on co-occurrence graph
   - Minimum group size: 3 people
   - Minimum internal edge weight: 0.5

**Dependencies**: `participants_json` column, networkx for graph algorithms

---

### Epic 3.3: CA1 Bridge (Bidirectional Reconciliation)

<!-- CRITICAL: This is the heart of P03 v2 -->

#### Issue 3.3.1: Implement Truth Query Module

**Dossier Reference**: Section 1.4 Reconciliation Algorithm, Section 4.3.3

**What to Cover**:

1. **TruthQueryModule Class** (`k0/modules/consolidation/truth_query.py`):
   - Query all 8 memory layers for existing truth
   - This is the READ phase of bidirectional consolidation

2. **Truth Layers to Query**:

   | Layer | Table | Query Fields | Purpose |
   |-------|-------|--------------|---------|
   | Episodic | st_epi | simhash, embedding_id, time | Similar past episodes |
   | Semantic | st_sem | embedding_id, pattern_type | Matching patterns |
   | Procedural | st_procedural | activity_type, time_pattern | Existing routines |
   | Social | st_social | participant_ids | Relationship matches |
   | KG Entities | st_kg_dom | entity_name, aliases | Entity resolution |
   | KG Edges | st_kg_edges | source_id, target_id | Relationship edges |
   | Prospective | st_prospective | intent_type | Future intentions |
   | Vector | st_vec | embedding | Similarity search |

3. **Query Interface**:

   ```python
   class TruthQueryModule:
       async def query_truth_for_signal(
           self,
           signal: HippEvent,
           search_config: TruthSearchConfig
       ) -> list[TruthMatch]:
           """
           Query all relevant layers for potential matches.

           Returns ranked list of truth records that may match this signal.
           """

       async def query_truth_for_cluster(
           self,
           cluster: EpisodeCluster,
           search_config: TruthSearchConfig
       ) -> list[TruthMatch]:
           """Query truth for entire cluster (batch efficiency)."""
   ```

4. **Query Optimization**:
   - SimHash pre-filter: Only query records with Hamming distance ≤ 5
   - Time window: Default 30 days for episodic, 365 days for semantic
   - Limit per layer: 10 candidates (configurable)

5. **TruthMatch Schema**:

   ```python
   @dataclass
   class TruthMatch:
       record_id: str
       layer: str  # st_epi, st_sem, etc.
       record_type: str  # EPISODE, PATTERN, ROUTINE, etc.
       simhash: int
       embedding_id: str | None
       confidence: float
       observation_count: int
       last_observed_at: datetime
   ```

**Dependencies**: All 8 memory layer tables, P08 embedding search

---

#### Issue 3.3.2: Implement Similarity Computation

**Dossier Reference**: Section 2.4 Similarity Formula

**What to Cover**:

1. **SimilarityComputer Class** (`k0/modules/consolidation/similarity_computer.py`):
   - Multi-factor similarity computation
   - Core formula from Dossier Section 2.4

2. **Similarity Formula** (from Dossier):

   ```python
   similarity = (
       0.40 * cosine_similarity(embedding_new, embedding_existing)  # Semantic
     + 0.25 * (1 - hamming_distance(simhash_new, simhash_existing) / 64)  # Structure
     + 0.15 * jaccard_similarity(entities_new, entities_existing)  # Entity overlap
     + 0.10 * temporal_proximity_score(time_new, time_existing)  # Time closeness
     + 0.10 * spatial_proximity_score(location_new, location_existing)  # Location
   )
   ```

3. **Component Implementations**:

   | Component | Weight | Implementation |
   |-----------|--------|----------------|
   | Embedding | 0.40 | `np.dot(a, b) / (norm(a) * norm(b))` |
   | SimHash | 0.25 | `1 - popcount(a ^ b) / 64` |
   | Entity | 0.15 | `len(A ∩ B) / len(A ∪ B)` |
   | Temporal | 0.10 | `exp(-0.1 * abs(days_diff))` |
   | Spatial | 0.10 | `1.0 if same_location else 0.0` |

4. **Batch Similarity Computation**:

   ```python
   async def compute_similarity_batch(
       self,
       signal: HippEvent | EpisodeCluster,
       truth_matches: list[TruthMatch]
   ) -> list[tuple[TruthMatch, float]]:
       """Compute similarity to all truth matches, return sorted."""
   ```

5. **Similarity Thresholds** (decision boundaries):

   | Similarity | Decision |
   |------------|----------|
   | > 0.85 | REINFORCE |
   | 0.60 - 0.85 | EXTEND or EVOLVE |
   | < 0.60 | CREATE or CONTRADICT |

**Dependencies**: Issue 3.3.1 (TruthMatch), numpy, embeddings from st_vec

---

#### Issue 3.3.3: Implement Decision Matrix

**Dossier Reference**: Section 1.3 Reconciliation Decision Types

**What to Cover**:

1. **DecisionMatrix Class** (`k0/modules/consolidation/decision_matrix.py`):
   - Apply decision rules based on similarity scores
   - 6 decision types: REINFORCE, EXTEND, CREATE, EVOLVE, CONTRADICT, PRUNE

2. **Decision Type Enum**:

   ```python
   class DecisionType(str, Enum):
       REINFORCE = "REINFORCE"   # Boost existing truth
       EXTEND = "EXTEND"         # Add details to existing
       CREATE = "CREATE"         # Insert new truth
       EVOLVE = "EVOLVE"         # Schema evolution
       CONTRADICT = "CONTRADICT" # Flag for P06 resolution
       PRUNE = "PRUNE"           # Decay/archive old truth
   ```

3. **Decision Rules** (from Dossier Section 1.3):

   | Condition | Decision | Action |
   |-----------|----------|--------|
   | similarity > 0.85 | REINFORCE | Increment observation_count, refresh last_observed |
   | 0.60 < similarity ≤ 0.85 AND schema_match | EXTEND | Append to source_episodes_json |
   | 0.60 < similarity ≤ 0.85 AND schema_change | EVOLVE | Create new version, link supersedes_id |
   | similarity < 0.60 AND no_conflict | CREATE | INSERT new record |
   | similarity < 0.60 AND conflict | CONTRADICT | Flag for P06 Active Learning |
   | no_signal_for_N_days | PRUNE | Apply decay, archive, or tombstone |

4. **Decision Matrix Algorithm**:

   ```python
   class DecisionMatrix:
       def decide(
           self,
           signal: HippEvent | EpisodeCluster,
           similarities: list[tuple[TruthMatch, float]]
       ) -> ReconciliationDecision:
           if not similarities:
               return ReconciliationDecision(type=DecisionType.CREATE, ...)

           best_match, best_sim = max(similarities, key=lambda x: x[1])

           if best_sim > 0.85:
               return self._build_reinforce(signal, best_match, best_sim)
           elif best_sim > 0.60:
               if self._is_schema_evolution(signal, best_match):
                   return self._build_evolve(signal, best_match, best_sim)
               else:
                   return self._build_extend(signal, best_match, best_sim)
           else:
               if self._is_contradiction(signal, best_match):
                   return self._build_contradict(signal, best_match)
               else:
                   return self._build_create(signal)
   ```

5. **Conflict Detection** (for CONTRADICT):
   - Semantic opposition: "loves X" vs "hates X"
   - Temporal impossibility: overlapping exclusive events
   - Entity contradiction: conflicting attributes

**Dependencies**: Issue 3.3.2 (similarity scores)

---

#### Issue 3.3.4: Implement Reconciliation Decision Builder

**Dossier Reference**: Section 1.4 Reconciliation Algorithm

**What to Cover**:

1. **ReconciliationDecisionBuilder Class** (`k0/modules/consolidation/reconciliation_builder.py`):
   - Build complete ReconciliationDecision objects for R6/R7 processing
   - Prepare all data needed for truth layer updates

2. **ReconciliationDecision Schema**:

   ```python
   @dataclass
   class ReconciliationDecision:
       decision_id: str  # ULID
       decision_type: DecisionType
       source_signal_id: str  # event_id or cluster_id
       target_layer: str  # st_epi, st_sem, etc.
       target_record_id: str | None  # Existing record for REINFORCE/EXTEND/EVOLVE
       similarity: float | None
       confidence: float

       # Type-specific payloads
       reinforce_updates: dict | None  # observation_count, last_observed_at, decay_factor
       extend_data: dict | None  # New attributes to append
       create_data: dict | None  # Full record for INSERT
       evolve_data: dict | None  # New version data + supersedes_id
       contradict_data: dict | None  # Conflict details for P06

       # Audit
       created_at: datetime
       processing_phase: str  # R2, R3, R4, etc.
   ```

3. **Builder Methods**:

   ```python
   class ReconciliationDecisionBuilder:
       def build_reinforce(
           self,
           signal: HippEvent,
           target: TruthMatch,
           similarity: float
       ) -> ReconciliationDecision:
           return ReconciliationDecision(
               decision_type=DecisionType.REINFORCE,
               target_record_id=target.record_id,
               target_layer=target.layer,
               similarity=similarity,
               reinforce_updates={
                   'observation_count': target.observation_count + 1,
                   'last_observed_at': signal.event_time_utc,
                   'decay_factor': 1.0,
                   'confidence_score': self._boost_confidence(target.confidence, similarity)
               }
           )

       def build_create(self, signal: HippEvent, target_layer: str) -> ReconciliationDecision
       def build_extend(self, signal: HippEvent, target: TruthMatch, extensions: dict) -> ReconciliationDecision
       def build_evolve(self, signal: HippEvent, target: TruthMatch, new_version: dict) -> ReconciliationDecision
       def build_contradict(self, signal: HippEvent, target: TruthMatch, conflict: dict) -> ReconciliationDecision
   ```

4. **Confidence Boost Formula**:

   ```python
   def _boost_confidence(self, current: float, similarity: float) -> float:
       # Asymptotic approach to 1.0
       boost = 0.1 * similarity * (1 - current)
       return min(0.99, current + boost)
   ```

5. **Output Queue**:
   - Store decisions in `st_reconciliation_queue` (M1 Epic 1.5)
   - R6/R7 modules consume from queue for durable writes

**Dependencies**: Issue 3.3.3 (DecisionMatrix), M1 Epic 1.5 (st_reconciliation_queue)

---

### Epic 3.4: R2 Unit Tests

#### Issue 3.4.1: Clustering Tests

**Test File**: `tests/k0/modules/consolidation/test_episode_clusterer.py`

**What to Cover**:

1. **Cluster Formation Tests**:
   - `test_dbscan_forms_clusters`: Similar events → same cluster
   - `test_dbscan_separates_dissimilar`: Different embeddings → different clusters
   - `test_temporal_proximity_bonus`: Close-in-time events cluster together
   - `test_respects_eps_parameter`: eps=0.3 vs eps=0.5 → different cluster counts
   - `test_respects_min_samples`: min_samples=2 vs min_samples=5 → different cluster sizes

2. **Confidence Scoring Tests**:
   - `test_tight_cluster_high_confidence`: All members similar → confidence > 0.8
   - `test_loose_cluster_low_confidence`: Members dissimilar → confidence < 0.6
   - `test_singleton_neutral_confidence`: Single event → confidence = 0.5
   - `test_confidence_formula_correct`: Manual calculation matches implementation

3. **Outlier Handling Tests**:
   - `test_outliers_labeled_minus_one`: DBSCAN noise points identified
   - `test_outliers_become_singletons`: Noise → SING_{event_id} clusters
   - `test_singleton_metrics_tracked`: p03_singletons_total counter incremented
   - `test_high_importance_singletons_promoted`: importance > 0.7 → promoted

4. **SimHash Pre-Filter Tests**:
   - `test_prefilter_reduces_candidates`: Only Hamming ≤ 5 pairs computed
   - `test_exact_duplicate_skipped`: Hamming = 0 → marked duplicate, no cluster
   - `test_sparse_matrix_correct`: Non-candidates have distance 1.0

5. **Performance Tests**:
   - `test_cluster_1000_events_under_500ms`: Batch performance
   - `test_memory_usage_reasonable`: < 500MB for 5000 events
   - `test_prefilter_speedup`: Pre-filtered 2x faster than full matrix

**Fixtures Needed**:

- `sample_embeddings`: 100 768-dim vectors with known similarity structure
- `sample_events`: HippEvents with simhash, timestamps, locations
- `episode_clusterer`: EpisodicClusterer with test config

---

#### Issue 3.4.2: Pattern Extraction Tests

**Test File**: `tests/k0/modules/consolidation/test_pattern_extraction.py`

**What to Cover**:

1. **Routine Detection Tests**:
   - `test_detects_daily_routine`: Same time 5 days → DAILY pattern
   - `test_detects_weekly_routine`: Same weekday 4 weeks → WEEKLY pattern
   - `test_rejects_insufficient_frequency`: 2 occurrences → no routine
   - `test_routine_confidence_formula`: Verify sqrt(freq × consistency × significance)
   - `test_temporal_tolerance`: ±1 hour still matches pattern

2. **Preference Extraction Tests**:
   - `test_extracts_entity_preference`: "Thai food" + positive sentiment 3x → preference
   - `test_negative_preference`: Negative sentiment → valence < 0
   - `test_mixed_sentiment_ambivalent`: High variance → AMBIVALENT flag
   - `test_preference_requires_minimum_count`: < 3 occurrences → no preference

3. **Theme Identification Tests**:
   - `test_clusters_similar_centroids`: Related clusters → same theme
   - `test_theme_coherence_scoring`: Tight theme → high coherence
   - `test_theme_label_extraction`: Keywords represent theme content
   - `test_theme_types_assigned`: DOMAIN, INTEREST, etc. correctly labeled

4. **Relationship Mining Tests**:
   - `test_detects_dyad_relationship`: 2 people, 5+ co-occurrences → dyad
   - `test_detects_group_relationship`: 3+ people, frequent → group
   - `test_relationship_strength_formula`: Verify Hebbian formula
   - `test_community_detection`: Louvain finds cliques

**Fixtures Needed**:

- `temporal_events`: Events with known temporal patterns
- `sentiment_events`: Events with controlled affect_valence
- `social_events`: Events with participant_ids for relationship tests

---

#### Issue 3.4.3: CA1 Bridge Tests

**Test File**: `tests/k0/modules/consolidation/test_ca1_bridge.py`

**What to Cover**:

1. **Truth Query Tests**:
   - `test_queries_all_8_layers`: All layers queried, results aggregated
   - `test_simhash_prefilter_applied`: Only Hamming ≤ 5 returned
   - `test_time_window_respected`: Old records excluded
   - `test_limit_per_layer`: Max 10 candidates per layer

2. **Similarity Computation Tests**:
   - `test_embedding_similarity_weight_40`: Embedding contributes 40%
   - `test_simhash_similarity_weight_25`: SimHash contributes 25%
   - `test_entity_jaccard_weight_15`: Entity overlap contributes 15%
   - `test_temporal_proximity_weight_10`: Time proximity contributes 10%
   - `test_spatial_proximity_weight_10`: Location match contributes 10%
   - `test_total_similarity_normalized`: Result in [0, 1]

3. **Decision Matrix Tests**:
   - `test_reinforce_above_085`: similarity > 0.85 → REINFORCE
   - `test_extend_between_060_085`: 0.60 < sim ≤ 0.85 → EXTEND
   - `test_evolve_schema_change`: Schema evolution → EVOLVE
   - `test_create_below_060`: similarity < 0.60 → CREATE
   - `test_contradict_on_conflict`: Semantic opposition → CONTRADICT
   - `test_prune_stale_truth`: No signal for N days → PRUNE

4. **Decision Builder Tests**:
   - `test_reinforce_increments_count`: observation_count + 1
   - `test_reinforce_resets_decay`: decay_factor = 1.0
   - `test_extend_appends_episodes`: source_episodes_json extended
   - `test_evolve_creates_version`: supersedes_id linked
   - `test_contradict_flags_p06`: flag_for_p06 = True
   - `test_confidence_boost_asymptotic`: Boost approaches but never exceeds 0.99

5. **Integration Tests**:
   - `test_full_reconciliation_flow`: Signal → Query → Similarity → Decision
   - `test_batch_reconciliation`: 100 signals processed correctly
   - `test_decision_queue_populated`: Decisions written to st_reconciliation_queue

**Fixtures Needed**:

- `mock_truth_layers`: Controllable query results per layer
- `sample_signals`: HippEvents with known similarity to truth
- `ca1_bridge`: Full CA1 Bridge module with mocked dependencies

**Golden Dataset Integration**:

- Use `golden_dataset/dataset.yaml` for standardized reconciliation scenarios
- Validate decision types match expected outcomes

---

### Epic 3.6: K0 Architecture Master Closure

#### Issue 3.6.1: Milestone 3 K0 Updates

**What to Cover**:

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated to reflect M3 completion
- [ ] **Part 3.1 (Module Registry)**: M19 (PatternDetector), M20 (CA1Bridge) rows added
- [ ] **Part 4.1 (Event Topics)**: P03 pattern extraction events registered
- [ ] **Part 5.1 (Contract Registry)**: PatternDetector, CA1Bridge module contracts added
- [ ] **Part 5.2 (Syscall Matrix)**: Storage capabilities for pattern queries registered
- [ ] **Part 5.3 (Storage Tables)**: st_reconciliation_queue, st_pattern_cache tables documented
- [ ] **Part 7.1 (ADR Index)**: ADR status for M3 decisions updated
- [ ] **Version Header**: Document version bumped to reflect M3 completion

**K0 File**: `k0/pipelines/k0_architecture_master.md`

---

## Milestone 4: Synaptic Homeostasis (R3)

**Goal**: Implement forgetting - deduplication, novelty, retention
**Gate**: GATE 3 (Implementation)

### Epic 4.1: Deduplication

#### Issue 4.1.1: Implement M19 DuplicateDetector

**Dossier Reference**: Section 4.4.1, Section 7.4.2

**What to Cover**:

1. **DuplicateDetector Class** (`k0/modules/consolidation/duplicate_detector.py`):
   - SimHash-based deduplication and novelty scoring
   - Brain analogy: Dentate Gyrus pattern separation

2. **Core Interface** (from Dossier Section 7.4.2):

   ```python
   class DuplicateDetector:
       def __init__(self, config: DeduplicationConfig):
           self.hamming_threshold = config.hamming_threshold  # Default: 3
           self.time_window_hours = config.time_window        # Default: 168 (1 week)

       async def detect(
           self,
           event: HippEvent,
           existing_hashes: dict[str, int]  # event_id → simhash
       ) -> DuplicationResult
   ```

3. **DuplicationResult Schema**:

   ```python
   @dataclass
   class DuplicationResult:
       event_id: str
       is_duplicate: bool           # True if exact duplicate (Hamming = 0)
       near_duplicates: list[str]   # event_ids with Hamming ≤ threshold
       novelty_score: float         # [0-1] higher = more novel
       duplicate_of: str | None     # Canonical event if duplicate
   ```

4. **Hamming Distance Calculation**:

   ```python
   def hamming_distance(hash1: int, hash2: int) -> int:
       """Count differing bits in 64-bit SimHash."""
       return bin(hash1 ^ hash2).count('1')
   ```

5. **Deduplication Thresholds**:

   | Hamming Distance | Classification | Action |
   |------------------|----------------|--------|
   | 0 | Exact duplicate | Skip consolidation, mark as duplicate |
   | 1-3 | Near-duplicate | Group together, consolidate as one |
   | 4-5 | Similar | Process normally, note similarity |
   | 6+ | Different | Process independently |

6. **Time Window Filtering**:
   - Only compare against events within `time_window_hours` (default: 168 = 1 week)
   - Older events excluded from duplicate detection

**Dependencies**: `simhash` column in st_hipp_events (populated by P02)

---

#### Issue 4.1.2: Implement MinHash LSH for Scale

**Dossier Reference**: Section 4.4.1 (100K+ events)

**What to Cover**:

1. **MinHashLSH Class** (`k0/modules/consolidation/minhash_lsh.py`):
   - Locality-Sensitive Hashing for batches > 1000 events
   - Reduces O(n²) comparisons to O(n × k) where k << n

2. **MinHash Configuration**:

   | Parameter | Default | Description |
   |-----------|---------|-------------|
   | num_perm | 128 | Number of permutations for MinHash |
   | threshold | 0.5 | Jaccard similarity threshold |
   | num_bands | 32 | Number of LSH bands |
   | rows_per_band | 4 | Rows per band (num_perm / num_bands) |

3. **LSH Algorithm Steps**:

   ```python
   class MinHashLSH:
       def __init__(self, config: LSHConfig):
           self.lsh = datasketch.MinHashLSH(
               threshold=config.threshold,
               num_perm=config.num_perm
           )

       def index_batch(self, events: list[HippEvent]) -> None:
           """Index all events for similarity search."""
           for event in events:
               mh = self._compute_minhash(event.text_content)
               self.lsh.insert(event.event_id, mh)

       def query_similar(self, event: HippEvent) -> list[str]:
           """Find candidate duplicates via LSH."""
           mh = self._compute_minhash(event.text_content)
           return self.lsh.query(mh)
   ```

4. **Hybrid Approach**:
   - Batch size < 1000: Use direct SimHash comparison (Issue 4.1.1)
   - Batch size ≥ 1000: Use MinHash LSH for candidate generation, then SimHash verify

5. **Performance Target**:
   - 10,000 events: < 5 seconds for full deduplication
   - 100,000 events: < 60 seconds

**Dependencies**: `datasketch` library, Issue 4.1.1 (DuplicateDetector)

---

#### Issue 4.1.3: Implement Near-Duplicate Grouping

**Dossier Reference**: Section 4.4.1 (Hamming ≤ 3)

**What to Cover**:

1. **NearDuplicateGrouper Class** (`k0/modules/consolidation/near_duplicate_grouper.py`):
   - Group near-duplicates for consolidated processing
   - Select canonical representative per group

2. **Grouping Algorithm**:

   ```python
   class NearDuplicateGrouper:
       def group(
           self,
           events: list[HippEvent],
           duplicate_results: list[DuplicationResult]
       ) -> list[DuplicateGroup]:
           # 1. Build graph: nodes = events, edges = Hamming ≤ 3
           # 2. Find connected components
           # 3. For each component, select canonical
           # 4. Return groups with canonical + duplicates
   ```

3. **Canonical Selection Criteria** (priority order):
   - Highest importance_score
   - Most recent event_time_utc
   - Longest text_content (most detail)
   - Lowest event_id (tie-breaker)

4. **DuplicateGroup Schema**:

   ```python
   @dataclass
   class DuplicateGroup:
       group_id: str  # ULID
       canonical_id: str  # Event selected as canonical
       duplicate_ids: list[str]  # Other events in group
       mean_similarity: float  # Average pairwise similarity
       member_count: int
   ```

5. **Group Processing**:
   - Canonical event proceeds to R4 (KG consolidation)
   - Duplicate events marked: `consolidation_status = 'DUPLICATE'`
   - Link duplicates: `duplicate_of = canonical_id`

6. **Metrics**:
   - `p03_duplicate_groups_total`: Number of groups formed
   - `p03_duplicates_skipped_total`: Events skipped as duplicates
   - `p03_dedup_ratio`: duplicates / total_events (monitor for anomalies)

**Dependencies**: Issue 4.1.1 (DuplicationResult), networkx for graph components

---

### Epic 4.2: Novelty Scoring

#### Issue 4.2.1: Implement Novelty Formula

**Dossier Reference**: Section 2.4 Novelty Score Formula

**What to Cover**:

1. **NoveltyScorer Class** (`k0/modules/consolidation/novelty_scorer.py`):
   - Calculate novelty score for each event
   - Brain analogy: Hippocampal novelty detection, pattern separation

2. **Base Novelty Formula** (from Dossier Section 2.4):

   ```python
   novelty_score = 1.0 - (duplicate_count / time_window_event_count)
   ```

3. **Full Novelty Calculation with Bonuses/Penalties**:

   ```python
   class NoveltyScorer:
       def score(self, event: HippEvent, context: NoveltyContext) -> float:
           # Base novelty from duplicate ratio
           base = 1.0 - (context.duplicate_count / max(1, context.window_count))

           # Apply bonuses and penalties
           bonuses = (
               self._first_time_bonus(event, context) +      # +0.15
               self._milestone_bonus(event) +                 # +0.20
               self._temporal_anomaly_bonus(event, context)   # +0.10
           )

           penalties = (
               self._exact_duplicate_penalty(context) +       # -0.30
               self._routine_penalty(event, context)          # -0.20
           )

           return max(0.0, min(1.0, base + bonuses - penalties))
   ```

4. **NoveltyContext Schema**:

   ```python
   @dataclass
   class NoveltyContext:
       duplicate_count: int      # Near-duplicates found
       window_count: int         # Total events in time window
       activity_count: int       # Times this activity seen
       is_exact_duplicate: bool  # Hamming distance = 0
       typical_times: list[int]  # Usual hours for this activity
   ```

5. **Novelty Score Output Range**: [0.0, 1.0]
   - 0.0 = Completely routine/duplicate
   - 0.5 = Average novelty
   - 1.0 = Highly novel (first-time + milestone + anomalous)

**Dependencies**: Issue 4.1.1 (duplicate detection results)

---

#### Issue 4.2.2: Implement First-Time Activity Bonus

**Dossier Reference**: Section 2.4 (Novelty Bonuses)

**What to Cover**:

1. **First-Time Detection**:
   - Check if `activity_type` seen fewer than 3 times
   - Query `st_hipp_events` for historical activity count

2. **Bonus Application**:

   ```python
   def _first_time_bonus(self, event: HippEvent, context: NoveltyContext) -> float:
       if context.activity_count < 3:
           return 0.15  # +15% novelty bonus
       return 0.0
   ```

3. **Activity Count Query**:

   ```sql
   SELECT COUNT(*) FROM st_hipp_events
   WHERE tenant_id = :tenant_id
     AND space_id = :space_id
     AND activity_type = :activity_type
     AND event_time_utc < :current_event_time
   ```

4. **Activity Categories Tracked**:
   - Primary: `activity_type` from UltraBERT classification
   - Secondary: `activity_category` (broader grouping)
   - Location-specific: `activity_type + location` combination

5. **Graduated Bonus** (optional enhancement):

   | Activity Count | Bonus |
   |----------------|-------|
   | 0 (never seen) | +0.20 |
   | 1-2 (rare) | +0.15 |
   | 3-5 (occasional) | +0.05 |
   | 6+ (familiar) | 0.00 |

**Dependencies**: `activity_type` column, historical event query

---

#### Issue 4.2.3: Implement Milestone Event Detection

**Dossier Reference**: Section 2.4 (Novelty Bonuses)

**What to Cover**:

1. **MilestoneDetector Class** (`k0/modules/consolidation/milestone_detector.py`):
   - Detect life milestone events for novelty boost
   - Bonus: +0.20 for confirmed milestones

2. **Milestone Categories**:

   | Category | Keywords/Patterns | Bonus |
   |----------|-------------------|-------|
   | Birthday | "birthday", "bday", date matches birth_date | +0.20 |
   | Anniversary | "anniversary", annual recurrence | +0.20 |
   | Graduation | "graduation", "commencement", "diploma" | +0.20 |
   | Wedding | "wedding", "married", "engagement" | +0.20 |
   | New Job | "first day", "new job", "started at" | +0.15 |
   | Birth | "born", "baby", "newborn" | +0.20 |
   | Achievement | "award", "promotion", "achieved" | +0.15 |

3. **Detection Algorithm**:

   ```python
   class MilestoneDetector:
       def detect(self, event: HippEvent) -> MilestoneResult:
           # 1. Check entities_json for milestone keywords
           # 2. Check event_type against milestone patterns
           # 3. Check date against known recurring milestones
           # 4. Return milestone type and bonus
   ```

4. **Recurring Milestone Detection**:
   - Match `event_time_utc.month` and `event_time_utc.day` against stored dates
   - Sources: `st_kg_dom` entities with `type = 'DATE_MILESTONE'`

5. **MilestoneResult Schema**:

   ```python
   @dataclass
   class MilestoneResult:
       is_milestone: bool
       milestone_type: str | None  # BIRTHDAY, ANNIVERSARY, etc.
       bonus: float  # 0.15 - 0.20
       confidence: float  # How certain about detection
   ```

**Dependencies**: `entities_json`, `st_kg_dom` for recurring dates

---

#### Issue 4.2.4: Implement Temporal Anomaly Detection

**Dossier Reference**: Section 2.4 (Novelty Bonuses)

**What to Cover**:

1. **TemporalAnomalyDetector Class** (`k0/modules/consolidation/temporal_anomaly.py`):
   - Detect activities at unusual times
   - Bonus: +0.10 for temporal anomalies

2. **Typical Time Pattern Learning**:

   ```python
   class TemporalAnomalyDetector:
       async def learn_patterns(
           self,
           tenant_id: str,
           space_id: str,
           activity_type: str
       ) -> TemporalPattern:
           # Query historical events for this activity
           # Build distribution: hour_of_day, day_of_week
           # Calculate mean and std_dev for timing
   ```

3. **Anomaly Detection Algorithm**:

   ```python
   def detect_anomaly(self, event: HippEvent, pattern: TemporalPattern) -> float:
       hour = event.event_time_utc.hour
       z_score = abs(hour - pattern.mean_hour) / max(pattern.std_hour, 1)

       if z_score > 2.0:  # More than 2 std devs from normal
           return 0.10  # +10% novelty bonus
       return 0.0
   ```

4. **Anomaly Types**:

   | Anomaly | Detection | Bonus |
   |---------|-----------|-------|
   | Unusual hour | > 2σ from mean hour | +0.10 |
   | Unusual day | Weekend activity on weekday (or vice versa) | +0.05 |
   | Unusual duration | Event much longer/shorter than typical | +0.05 |
   | Location shift | Different location for same activity | +0.05 |

5. **TemporalPattern Schema**:

   ```python
   @dataclass
   class TemporalPattern:
       activity_type: str
       mean_hour: float
       std_hour: float
       typical_days: list[int]  # 0=Mon, 6=Sun
       sample_count: int
   ```

6. **Minimum Sample Requirement**:
   - Need at least 5 historical events to establish pattern
   - If < 5 events: assume novelty (first-time activity)

**Dependencies**: Historical events query, datetime analysis

---

### Epic 4.3: Retention Enforcement

#### Issue 4.3.1: Implement M20 RetentionEnforcer

**Dossier Reference**: Section 4.4.3, Section 7.4.3

**What to Cover**:

1. **RetentionEnforcer Class** (`k0/modules/consolidation/retention_enforcer.py`):
   - Implement synaptic homeostasis (forgetting)
   - Brain analogy: Tononi & Cirelli (2006) synaptic downscaling

2. **Core Interface** (from Dossier Section 7.4.3):

   ```python
   class RetentionEnforcer:
       def __init__(self, config: RetentionConfig):
           self.decay_rates = {
               'st_epi': 0.005,        # Half-life: 139 days
               'st_sem': 0.003,        # Half-life: 231 days
               'st_procedural': 0.010, # Half-life: 69 days
               'st_social': 0.002,     # Half-life: 347 days
               'st_prospective': 0.010,
               'st_kg_dom': 0.001,
               'st_kg_edges': 0.004,
           }
           self.archive_threshold = config.archive_threshold    # Default: 0.1
           self.tombstone_threshold = config.tombstone_threshold  # Default: 0.01

       async def evaluate(
           self,
           record: TruthRecord,
           table: str
       ) -> RetentionDecision
   ```

3. **Layer-Specific Decay Rates** (from Dossier Section 2.4):

   | Layer | λ (decay rate) | Half-Life | Rationale |
   |-------|----------------|-----------|-----------|
   | st_epi | 0.005 | 139 days | Episodic memories fade slowly |
   | st_sem | 0.003 | 231 days | Semantic knowledge very stable |
   | st_procedural | 0.010 | 69 days | Habits need reinforcement |
   | st_social | 0.002 | 347 days | Relationships persist long |
   | st_prospective | 0.010 | 69 days | Intentions expire quickly |
   | st_kg_dom | 0.001 | 693 days | Entities are very stable |
   | st_kg_edges | 0.004 | 173 days | Edges more volatile |

4. **RetentionDecision Schema**:

   ```python
   @dataclass
   class RetentionDecision:
       record_id: str
       table: str
       current_decay: float
       new_decay: float
       action: str  # 'KEEP', 'DECAY', 'ARCHIVE', 'TOMBSTONE'
       reason: str
   ```

5. **Batch Evaluation**:
   - Process all records in a table per consolidation cycle
   - Prioritize records not observed in > 30 days

**Dependencies**: All truth layer tables, `decay_factor` column

---

#### Issue 4.3.2: Implement Decay Calculation

**Dossier Reference**: Section 2.4 Decay Formula

**What to Cover**:

1. **Decay Formula** (from Dossier):

   ```python
   decay_factor = exp(-λ * days_since_last_observed)
   ```

   Where:
   - `λ` = layer-specific decay constant
   - `days_since_last_observed` = `(NOW() - last_observed_at) / 86400`

2. **DecayCalculator Class**:

   ```python
   class DecayCalculator:
       def calculate(
           self,
           record: TruthRecord,
           decay_rate: float,
           current_time: datetime
       ) -> float:
           days_since = (current_time - record.last_observed_at).total_seconds() / 86400
           return record.decay_factor * math.exp(-decay_rate * days_since)
   ```

3. **Decay Reinforcement** (on REINFORCE decision):

   ```python
   def reinforce(self, record: TruthRecord) -> float:
       """Reset decay when memory is reinforced."""
       return 1.0  # Full strength
   ```

4. **Half-Life Calculation Reference**:

   ```python
   # Half-life = ln(2) / λ ≈ 0.693 / λ
   # st_epi: 0.693 / 0.005 = 139 days
   # st_sem: 0.693 / 0.003 = 231 days
   ```

5. **Decay Visualization** (for debugging):

   | Days Since | λ=0.005 | λ=0.003 | λ=0.010 |
   |------------|---------|---------|---------|
   | 30 | 0.86 | 0.91 | 0.74 |
   | 90 | 0.64 | 0.76 | 0.41 |
   | 180 | 0.41 | 0.58 | 0.17 |
   | 365 | 0.16 | 0.33 | 0.03 |

**Dependencies**: `last_observed_at`, `decay_factor` columns

---

#### Issue 4.3.3: Implement Archival Status Transitions

**Dossier Reference**: Section 4.4.3, Section 6.1.1

**What to Cover**:

1. **Status Transition State Machine**:

   ```
   ACTIVE → ARCHIVED → TOMBSTONE → [deleted]
   ```

2. **Transition Thresholds**:

   | Current Status | Decay Factor | Action |
   |----------------|--------------|--------|
   | ACTIVE | > 0.1 | Keep as ACTIVE |
   | ACTIVE | 0.01 - 0.1 | Transition to ARCHIVED |
   | ARCHIVED | > 0.1 | Promote back to ACTIVE (if reinforced) |
   | ARCHIVED | < 0.01 | Transition to TOMBSTONE |
   | TOMBSTONE | - | Mark for garbage collection |

3. **StatusTransitioner Class**:

   ```python
   class StatusTransitioner:
       def transition(
           self,
           record: TruthRecord,
           new_decay: float
       ) -> StatusTransition:
           current = record.archival_status

           if new_decay < self.tombstone_threshold:
               new_status = 'TOMBSTONE'
           elif new_decay < self.archive_threshold:
               new_status = 'ARCHIVED'
           else:
               new_status = 'ACTIVE'

           return StatusTransition(
               record_id=record.id,
               from_status=current,
               to_status=new_status,
               decay_factor=new_decay,
               transition_time=datetime.now(timezone.utc)
           )
   ```

4. **ARCHIVED Records Behavior**:
   - Excluded from primary queries (Query Port)
   - Still available for historical analysis
   - Can be promoted back if referenced

5. **TOMBSTONE Records Behavior**:
   - Invisible to all queries
   - Retain for audit trail (configurable retention)
   - Scheduled for physical deletion

6. **Transition Audit Log**:
   - Log all transitions to `st_retention_audit` (if exists)
   - Include: record_id, from_status, to_status, decay_factor, timestamp

**Dependencies**: `archival_status` column in truth layers

---

#### Issue 4.3.4: Implement Garbage Collection Hook

**Dossier Reference**: Section 4.4.5

**What to Cover**:

1. **GarbageCollectionHook Class** (`k0/modules/consolidation/gc_hook.py`):
   - Mark tombstone records for background cleanup
   - Do not perform actual deletion in consolidation cycle

2. **GC Hook Interface**:

   ```python
   class GarbageCollectionHook:
       async def mark_for_collection(
           self,
           tombstones: list[TombstoneRecord]
       ) -> None:
           """Mark tombstone records for background GC."""
           for record in tombstones:
               await self._enqueue_gc(record)

       async def _enqueue_gc(self, record: TombstoneRecord) -> None:
           """Add to GC queue for background processing."""
           await self.outbox.publish(
               topic='familyos.p03.gc.pending.v1',
               payload={
                   'record_id': record.id,
                   'table': record.table,
                   'tombstoned_at': record.tombstoned_at,
                   'gc_after': record.tombstoned_at + self.retention_period
               }
           )
   ```

3. **GC Queue Message Schema**:

   ```python
   @dataclass
   class GCPendingMessage:
       record_id: str
       table: str
       tombstoned_at: datetime
       gc_after: datetime  # Do not delete until this time
       tenant_id: str
       space_id: str
   ```

4. **Retention Periods Before Hard Delete**:

   | Table | Retention After Tombstone | Rationale |
   |-------|---------------------------|-----------|
   | st_epi | 30 days | Episodic might be referenced |
   | st_sem | 90 days | Semantic patterns may need recovery |
   | st_procedural | 30 days | Habits can be re-learned |
   | st_social | 180 days | Relationships hard to reconstruct |
   | st_kg_dom | 365 days | Entities are foundational |
   | st_kg_edges | 30 days | Edges easily re-derived |

5. **Background GC Worker** (separate from P03):
   - Poll `familyos.p03.gc.pending.v1` topic
   - Check `gc_after` timestamp
   - Perform hard DELETE when retention expired
   - Emit `familyos.p03.gc.completed.v1` for audit

6. **GC Metrics**:
   - `p03_tombstones_created_total`: New tombstones this cycle
   - `p03_gc_pending_total`: Records awaiting hard delete
   - `p03_gc_completed_total`: Records hard deleted

**Dependencies**: st_outbox for event publishing, background worker

---

### Epic 4.4: R3 Unit Tests

#### Issue 4.4.1: Deduplication Tests

**Test File**: `tests/k0/modules/consolidation/test_deduplication.py`

**What to Cover**:

1. **SimHash Comparison Tests**:
   - `test_hamming_distance_calculation`: popcount(a ^ b) correct
   - `test_exact_duplicate_hamming_zero`: Identical hashes → distance = 0
   - `test_near_duplicate_hamming_three`: Similar hashes → distance ≤ 3
   - `test_different_hashes_high_distance`: Different content → distance > 5

2. **Duplicate Detection Tests**:
   - `test_exact_duplicate_flagged`: is_duplicate = True, duplicate_of populated
   - `test_near_duplicates_listed`: near_duplicates contains all Hamming ≤ 3
   - `test_time_window_respected`: Events outside window not considered
   - `test_empty_existing_hashes`: No duplicates, novelty = 1.0

3. **Near-Duplicate Grouping Tests**:
   - `test_connected_components_formed`: Graph correctly partitions
   - `test_canonical_selection_by_importance`: Highest importance selected
   - `test_canonical_selection_by_recency`: Same importance → most recent wins
   - `test_duplicate_status_updated`: Non-canonical marked DUPLICATE

4. **MinHash LSH Tests**:
   - `test_lsh_finds_candidates`: Similar docs returned as candidates
   - `test_lsh_excludes_dissimilar`: Different docs not in candidates
   - `test_lsh_scales_to_10k`: 10,000 events < 5 seconds
   - `test_hybrid_approach_threshold`: LSH used when batch > 1000

5. **Performance Tests**:
   - `test_dedup_1000_events_under_1s`: Batch performance
   - `test_dedup_memory_bounded`: Memory usage reasonable

**Fixtures Needed**:

- `sample_simhashes`: 100 hashes with known distances
- `duplicate_detector`: DuplicateDetector instance
- `near_duplicate_grouper`: NearDuplicateGrouper instance

---

#### Issue 4.4.2: Novelty Scoring Tests

**Test File**: `tests/k0/modules/consolidation/test_novelty_scoring.py`

**What to Cover**:

1. **Base Novelty Formula Tests**:
   - `test_no_duplicates_novelty_one`: 0 duplicates → novelty = 1.0
   - `test_all_duplicates_novelty_zero`: duplicate_count = window_count → novelty = 0.0
   - `test_partial_duplicates`: 5 dups / 10 window → novelty ≈ 0.5

2. **First-Time Activity Bonus Tests**:
   - `test_first_time_bonus_applied`: activity_count = 0 → +0.15
   - `test_rare_activity_bonus`: activity_count = 2 → +0.15
   - `test_familiar_activity_no_bonus`: activity_count = 10 → +0.00

3. **Milestone Event Bonus Tests**:
   - `test_birthday_milestone_bonus`: "birthday" keyword → +0.20
   - `test_anniversary_milestone_bonus`: "anniversary" → +0.20
   - `test_graduation_milestone_bonus`: "graduation" → +0.20
   - `test_no_milestone_no_bonus`: Regular event → +0.00

4. **Temporal Anomaly Bonus Tests**:
   - `test_unusual_hour_bonus`: > 2σ from mean → +0.10
   - `test_normal_hour_no_bonus`: Within 1σ → +0.00
   - `test_insufficient_history`: < 5 events → treat as novel

5. **Penalty Tests**:
   - `test_exact_duplicate_penalty`: Hamming = 0 → -0.30
   - `test_routine_penalty`: Matches routine pattern → -0.20

6. **Combined Score Tests**:
   - `test_score_clamped_to_one`: Bonuses don't exceed 1.0
   - `test_score_floored_at_zero`: Penalties don't go below 0.0
   - `test_all_bonuses_combined`: First-time + milestone + anomaly

**Fixtures Needed**:

- `novelty_scorer`: NoveltyScorer instance
- `milestone_detector`: MilestoneDetector instance
- `temporal_patterns`: Pre-computed activity patterns

---

#### Issue 4.4.3: Retention Enforcement Tests

**Test File**: `tests/k0/modules/consolidation/test_retention_enforcement.py`

**What to Cover**:

1. **Decay Calculation Tests**:
   - `test_decay_formula_correct`: exp(-λ × days) matches implementation
   - `test_layer_specific_rates`: Each layer uses correct λ
   - `test_half_life_verification`: At half-life, decay ≈ 0.5
   - `test_reinforcement_resets_decay`: REINFORCE → decay = 1.0

2. **Decay Rate by Layer Tests**:
   - `test_st_epi_decay_rate_0005`: λ = 0.005
   - `test_st_sem_decay_rate_0003`: λ = 0.003
   - `test_st_procedural_decay_rate_001`: λ = 0.010
   - `test_st_social_decay_rate_0002`: λ = 0.002

3. **Status Transition Tests**:
   - `test_active_stays_active`: decay > 0.1 → ACTIVE
   - `test_active_to_archived`: 0.01 < decay < 0.1 → ARCHIVED
   - `test_archived_to_tombstone`: decay < 0.01 → TOMBSTONE
   - `test_archived_to_active`: Reinforced → back to ACTIVE
   - `test_transition_audit_logged`: All transitions logged

4. **Garbage Collection Hook Tests**:
   - `test_tombstone_enqueued_for_gc`: Tombstone → GC message published
   - `test_gc_message_schema_valid`: Message matches schema
   - `test_retention_period_applied`: gc_after = tombstoned_at + retention
   - `test_layer_specific_retention`: Each layer has correct retention period

5. **Edge Cases**:
   - `test_very_old_record`: 365 days → appropriate decay
   - `test_just_observed_record`: 0 days → decay = 1.0
   - `test_missing_last_observed`: Handle NULL gracefully

**Fixtures Needed**:

- `retention_enforcer`: RetentionEnforcer instance
- `decay_calculator`: DecayCalculator instance
- `status_transitioner`: StatusTransitioner instance
- `mock_outbox`: Capture GC messages

---

### Epic 4.5: K0 Architecture Master Closure

#### Issue 4.5.1: Milestone 4 K0 Updates

**What to Cover**:

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated to reflect M4 completion
- [ ] **Part 3.1 (Module Registry)**: M21 (DuplicateDetector), M22 (RetentionEnforcer) rows added
- [ ] **Part 4.1 (Event Topics)**: P03 forgetting events registered
- [ ] **Part 5.1 (Contract Registry)**: DuplicateDetector, RetentionEnforcer module contracts added
- [ ] **Part 5.2 (Syscall Matrix)**: Storage capabilities for decay/retention registered
- [ ] **Part 5.3 (Storage Tables)**: st_memory_status, decay_factor columns documented
- [ ] **Part 7.1 (ADR Index)**: ADR status for M4 decisions updated
- [ ] **Version Header**: Document version bumped to reflect M4 completion

**K0 File**: `k0/pipelines/k0_architecture_master.md`

---

## Milestone 5: Knowledge Graph Consolidation (R4)

**Goal**: Implement KG entity/edge consolidation
**Gate**: GATE 3 (Implementation)

### Epic 5.1: Entity Normalization

#### Issue 5.1.1: Parse P02 entities_json

**What to cover**:

1. **UltraBERT NER Output Parsing**
   - Parse `entities_json` field from st_hipp_events
   - JSON structure: `[{"text": "...", "type": "...", "start": N, "end": N, "confidence": 0.X}, ...]`
   - Validate array format, handle empty arrays gracefully (`"[]"`)

2. **Entity Type Mapping (21 Types Total)**
   - 9 General Types: `PERSON`, `LOCATION`, `ORGANIZATION`, `EVENT`, `PRODUCT`, `DATE`, `TIME`, `MONEY`, `QUANTITY`
   - 12 Family-Specific Types: `FAMILY_MEMBER`, `PET`, `MEAL`, `RECIPE`, `FOOD`, `ACTIVITY`, `PREFERENCE`, `MEDICAL`, `SCHOOL`, `HOUSEHOLD`, `VEHICLE`, `HOBBY`
   - Map NER output types to st_kg_dom.entity_type enum

3. **Entity Extraction Pipeline**
   - Filter by confidence threshold (>= 0.6 per Section 7.4.4 `entity_confidence_threshold`)
   - Extract text span, type, position offsets
   - Preserve source event_id linkage for `first_mentioned_event_id`

4. **Batch Processing for Cluster**
   - Process all events in an EpisodeCluster together
   - Aggregate entities across cluster events
   - Track `source_episodes_json` as array of event_ids mentioning entity

**Reference**: Dossier Section 4.5.1, Section 7.4.4 KGConsolidator
**Integration Point**: P02 inline NER via UltraBERT semantic_project module
**Storage Target**: st_kg_dom.entity_type, st_kg_dom.source_episodes_json

---

#### Issue 5.1.2: Implement Entity Deduplication

**What to cover**:

1. **Same Entity, Different Mentions Detection**
   - "Mom" vs "my mother" vs "Linda" = same FAMILY_MEMBER entity
   - Case-insensitive comparison for initial grouping
   - Handle nicknames, abbreviations, and informal references

2. **Entity Resolution Strategy**
   - Step 1: Exact match on normalized text (lowercase, trimmed)
   - Step 2: Fuzzy match with Levenshtein ratio > 0.85 (see Issue 5.1.3)
   - Step 3: Semantic similarity via st_vec embeddings (cosine > 0.90)

3. **Entity Grouping Data Structure**

   ```python
   @dataclass
   class EntityGroup:
       canonical_id: str          # Primary entity_id
       mentions: List[str]        # All text forms seen
       source_events: List[str]   # All event_ids mentioning this entity
       confidence: float          # Aggregated confidence
   ```

4. **Deduplication Within Cluster**
   - Group entities by (entity_type, normalized_text)
   - Merge confidence scores: `combined = 1 - (1-c1)*(1-c2)` (independent corroboration)
   - Track first_mentioned_event_id as earliest chronologically

5. **Deduplication Against Existing st_kg_dom**
   - Query st_kg_dom for entities with matching type and similar name
   - Use existing entity_id if match found (UPDATE vs CREATE decision)
   - Compare attributes_json for potential conflicts

**Reference**: Dossier Section 4.5.1, Algorithm C.2 (Bayesian Confidence Merging)
**Storage Target**: st_kg_dom with is_canonical=1 for primary, aliases_json for variants

---

#### Issue 5.1.3: Implement Canonical Name Resolution

**What to cover**:

1. **Levenshtein Similarity Computation**
   - Use ratio threshold > 0.85 for "same entity" determination
   - Library: `rapidfuzz.fuzz.ratio()` or `python-Levenshtein`
   - Normalize strings before comparison: lowercase, remove punctuation, collapse whitespace

2. **Canonical Name Selection Rules**
   - Prefer longer, more complete names: "Jennifer Smith" > "Jen" > "J"
   - Prefer formal over informal: "Dr. Johnson" > "Doc"
   - Prefer names from higher-confidence source events
   - For ties: use alphabetically first for determinism

3. **Name Normalization Pipeline**

   ```python
   def normalize_for_comparison(text: str) -> str:
       # 1. Lowercase
       # 2. Remove punctuation (except apostrophes in names like O'Brien)
       # 3. Collapse multiple spaces
       # 4. Strip leading/trailing whitespace
   ```

4. **Cross-Type Resolution Prevention**
   - Never merge entities of different types (PERSON cannot match LOCATION)
   - Exception: FAMILY_MEMBER is subtype of PERSON, allow upward resolution

5. **Resolution Output**
   - Set st_kg_dom.canonical_name to selected canonical form
   - Populate aliases_json with all other encountered forms
   - Example: `canonical_name="Jennifer Smith"`, `aliases_json=["Jen", "Jenny", "J. Smith"]`

**Reference**: Dossier Section 4.5.1
**Storage Target**: st_kg_dom.canonical_name, st_kg_dom.aliases_json

---

#### Issue 5.1.4: Implement Alias Tracking

**What to cover**:

1. **aliases_json Schema**

   ```json
   {
     "names": ["Jen", "Jenny", "J. Smith"],
     "sources": {
       "Jen": ["event_001", "event_015"],
       "Jenny": ["event_042"]
     },
     "last_seen": {
       "Jen": 1704067200,
       "Jenny": 1704153600
     }
   }
   ```

2. **Alias Accumulation on Observation**
   - When entity mentioned with non-canonical name:
     - Add to aliases_json.names (deduplicated)
     - Append event_id to sources[alias]
     - Update last_seen[alias] timestamp

3. **Alias Confidence Tracking**
   - Track observation_count per alias (implicit in sources array length)
   - More observations = more confident alias is valid
   - Very rare aliases (1 mention in 6+ months) may be typos

4. **Alias Promotion Rules**
   - If alias becomes more frequently used than canonical_name:
     - Consider EVOLVE decision (version change)
     - Swap canonical_name with alias
     - Update supersedes_id chain

5. **Alias Query Support**
   - Enable lookup by any alias: "Find events mentioning Jenny"
   - Return canonical entity_id regardless of alias used in query
   - Support autocomplete/suggestion from aliases

**Reference**: Dossier Section 4.5.1, Section 6.8 st_kg_dom schema
**Storage Target**: st_kg_dom.aliases_json, st_kg_dom.observation_count

---

### Epic 5.2: Relationship Discovery

#### Issue 5.2.1: Implement M21 KGConsolidator

**What to cover**:

1. **Module Interface per Section 7.4.4**

   ```python
   class KGConsolidator:
       def __init__(self, config: KGConfig):
           self.entity_confidence_threshold = config.entity_threshold  # 0.6
           self.edge_confidence_threshold = config.edge_threshold      # 0.5
           self.co_occurrence_min = config.co_occurrence_min           # 2

       async def consolidate(
           clusters: List[EpisodeCluster],
           existing_kg: KnowledgeGraph
       ) -> List[KGUpdate]
   ```

2. **Integration with Existing Neo4jKGDriver**
   - Import from `k0/drivers/neo4j_driver.py`
   - `Neo4jKGDriver` provides: `apply()`, `query_relationships()`, `find_path()`
   - Node labels supported: `Person`, `Location`, `Event`, `Organization`, `Thing`
   - Use `build_driver()` factory for environment-based configuration

3. **KGUpdate Output Types**
   - `CREATE_ENTITY`: New entity to st_kg_dom
   - `UPDATE_ENTITY`: Update existing entity (observation_count, confidence, attributes)
   - `CREATE_EDGE`: New relationship to st_kg_edges
   - `UPDATE_EDGE`: Update existing edge (weight, co_occurrence_count)

4. **Entity Resolution Flow**
   - Extract entities from cluster via Issue 5.1.1
   - Resolve against existing st_kg_dom (Issue 5.1.2)
   - For each resolved entity:
     - If `is_new=True`: generate CREATE_ENTITY update
     - If `should_update=True`: generate UPDATE_ENTITY update

5. **Edge Discovery Flow**
   - Call `_discover_relationships()` for cluster
   - Filter edges by `edge_confidence >= self.edge_confidence_threshold`
   - Generate CREATE_EDGE updates for qualifying edges

**Reference**: Dossier Section 7.4.4, k0/drivers/neo4j_driver.py
**Integration Point**: Neo4jKGDriver for graph storage, P02 for entity input
**Storage Target**: st_kg_dom, st_kg_edges, Neo4j graph

---

#### Issue 5.2.2: Implement Co-Occurrence Analysis

**What to cover**:

1. **Hebbian Principle: "Entities That Fire Together Wire Together"**
   - Two entities appearing in same event = 1 co-occurrence
   - Same cluster, different events = fractional co-occurrence (0.5)
   - Higher co-occurrence = stronger relationship

2. **Co-Occurrence Counting Algorithm**

   ```python
   def count_co_occurrences(
       entity1_id: str,
       entity2_id: str,
       cluster: EpisodeCluster
   ) -> int:
       # Count events where both entities appear
       count = 0
       for event in cluster.events:
           entities_in_event = set(e['entity_id'] for e in event.entities_json)
           if entity1_id in entities_in_event and entity2_id in entities_in_event:
               count += 1
       return count
   ```

3. **Co-Occurrence Threshold**
   - `co_occurrence_min = 2` (default from Section 7.4.4)
   - Single co-occurrence may be coincidental
   - 2+ co-occurrences suggest meaningful relationship

4. **Confidence Scoring Formula**
   - From Dossier Section 7.4.4:
   - `confidence = min(0.9, 0.3 + 0.1 * co_occurrences)`
   - 2 co-occurrences = 0.5 confidence
   - 5 co-occurrences = 0.8 confidence
   - 7+ co-occurrences = 0.9 confidence (capped)

5. **Edge Weight Calculation (Hebbian Learning)**
   - Per Algorithm C.5:
   - `weight_new = weight_old + learning_rate * (co_occurrence - weight_old)`
   - Default learning_rate = 0.1
   - Edge weight approaches co-occurrence count asymptotically

6. **Relationship Type Inference**
   - Infer from entity type pairs:
     - `PERSON + PERSON` → `KNOWS`, `FAMILY`, or `COLLEAGUE`
     - `PERSON + LOCATION` → `VISITS`, `LIVES_AT`, `WORKS_AT`
     - `PERSON + ORGANIZATION` → `MEMBER_OF`, `WORKS_FOR`
     - `PERSON + EVENT` → `ATTENDED`, `ORGANIZED`
   - Context from event activity_type can refine inference

**Reference**: Dossier Section 4.5.2, Section 7.4.4, Algorithm C.5
**Storage Target**: st_kg_edges.co_occurrence_count, st_kg_edges.edge_weight

---

#### Issue 5.2.3: Implement Temporal Relationship Inference

**What to cover**:

1. **Temporal Proximity Rule**
   - Events within 1 hour → entities have temporal relationship
   - Events within same day → weaker temporal link (0.5 weight factor)
   - Events same week → weakest temporal link (0.25 weight factor)

2. **Temporal Edge Types**
   - `CONCURRENT_WITH`: Entities appeared at same time
   - `FOLLOWED_BY`: Entity B appeared shortly after Entity A
   - `PRECEDED_BY`: Entity A appeared before Entity B
   - `SAME_DAY_AS`: Appeared in different events on same day

3. **Temporal Sequence Detection**

   ```python
   def infer_temporal_edges(
       cluster: EpisodeCluster,
       entities: List[ResolvedEntity]
   ) -> List[TemporalEdge]:
       # Sort events by event_at
       # For consecutive events with different entity sets:
       #   Create FOLLOWED_BY edges from earlier to later
   ```

4. **Temporal Confidence Calculation**
   - Inverse of time gap: `confidence = 1.0 / (1 + hours_apart / 24)`
   - Same hour = ~1.0 confidence
   - Same day = ~0.5 confidence
   - 1 week apart = ~0.04 confidence (likely not related)

5. **valid_from/valid_to Assignment**
   - Temporal edges have bounded validity:
   - `valid_from`: timestamp of earlier event
   - `valid_to`: timestamp of later event + buffer (1 hour)
   - Unbounded edges (NULL valid_to) only for strong relationships (5+ co-occurrences)

**Reference**: Dossier Section 4.5.2, Section 4.5.3
**Storage Target**: st_kg_edges with relation_type IN ('CONCURRENT_WITH', 'FOLLOWED_BY', ...)

---

#### Issue 5.2.4: Implement Causal Inference (Granger)

**What to cover**:

1. **Granger Causality Principle**
   - "X Granger-causes Y" if past values of X help predict Y
   - For entities: Does entity A appearing predict entity B appearing later?
   - Requires sufficient temporal data (10+ events minimum)

2. **Simplified Causal Detection**

   ```python
   def detect_causal_relationship(
       entity_a: str,
       entity_b: str,
       events: List[HippEvent]
   ) -> Optional[CausalEdge]:
       # 1. Temporal precedence: A must precede B (on average)
       # 2. Prediction improvement: P(B | A occurred) > P(B)
       # 3. No confounding: No entity C that explains both A and B
   ```

3. **Causal Strength Scoring**
   - `causal_strength = P(B_follows_A) - P(B_random)`
   - If A always precedes B, and B rarely occurs without A: strong causality
   - Range: 0.0 (no causality) to 1.0 (deterministic causality)

4. **Causal Edge Types**
   - `CAUSES`: Strong causal relationship (strength > 0.7)
   - `INFLUENCES`: Moderate causality (strength 0.4-0.7)
   - `CORRELATES`: Statistical association, not necessarily causal (strength 0.2-0.4)

5. **Minimum Data Requirements**
   - Need 10+ occurrences of both entities for reliable inference
   - Need 5+ times where A precedes B for temporal pattern
   - Skip causal inference if data insufficient (log warning)

6. **Confidence Intervals**
   - Bootstrap sampling to estimate confidence bounds
   - Report `confidence_lower`, `confidence_upper` alongside point estimate
   - Reject causal claim if confidence interval includes 0

**Reference**: Dossier Section 4.5.4
**Storage Target**: st_kg_edges with relation_type IN ('CAUSES', 'INFLUENCES', 'CORRELATES')
**Note**: Deferred to Phase 2 if complexity exceeds MVP timeline

---

### Epic 5.3: Temporal Graph Updates

#### Issue 5.3.1: Implement valid_from/valid_to Management

**What to cover**:

1. **Bitemporal Model Overview**
   - `valid_from`: When the fact became true in the real world
   - `valid_to`: When the fact ceased to be true (NULL = still valid)
   - Enables "What did we know at time T?" queries
   - Supports relationship evolution tracking

2. **valid_from Assignment Rules**
   - For entities: `valid_from = first_mentioned_event.event_at`
   - For edges: `valid_from = first_co_occurrence_event.event_at`
   - Historical data import: use earliest known date
   - System-created entities: use `created_at` timestamp

3. **valid_to Assignment Rules**
   - Default: NULL (relationship still active)
   - Set when relationship ends:
     - Explicit end: "Mom no longer works at hospital" → set valid_to
     - Contradicting event: New fact supersedes old
     - Decay threshold reached: archival_status = 'ARCHIVED' → set valid_to

4. **Temporal Range Queries**

   ```cypher
   // Neo4j: Find relationships valid at specific time
   MATCH (a)-[r]->(b)
   WHERE r.valid_from <= $query_time
     AND (r.valid_to IS NULL OR r.valid_to >= $query_time)
   RETURN a, r, b

   // PostgreSQL st_kg_edges equivalent
   SELECT * FROM st_kg_edges
   WHERE valid_from <= $1
     AND (valid_to IS NULL OR valid_to >= $2)
   ```

5. **Neo4jKGDriver Integration**
   - `create_relationship()` accepts `valid_from`, `valid_to` params
   - `update_relationship()` can modify temporal bounds
   - `query_relationships()` returns temporal metadata

6. **Temporal Overlap Detection**
   - Detect overlapping validity periods for same entity pair
   - Two edges: A→B valid [T1, T2] and A→B valid [T1.5, T3]
   - Resolution: Merge into single edge or flag for review

**Reference**: Dossier Section 4.5.3, ADR-0081a (Temporal Graph Schema Design)
**Storage Target**: st_kg_dom.valid_from/valid_to, st_kg_edges.valid_from/valid_to
**Integration Point**: Neo4jKGDriver temporal property support

---

#### Issue 5.3.2: Implement Version Chain Maintenance

**What to cover**:

1. **Version Chain Model**
   - `version`: Incrementing integer per entity/edge
   - `supersedes_id`: Points to previous version entity_id/edge_id
   - `is_canonical`: Only 1 version is canonical (TRUE), others are historical (FALSE)

2. **EVOLVE Operation Implementation**

   ```python
   async def evolve_entity(
       current: KGEntity,
       updates: Dict[str, Any]
   ) -> KGEntity:
       # 1. Mark current as non-canonical
       current.is_canonical = False

       # 2. Create new version
       new_entity = KGEntity(
           entity_id=generate_ulid(),
           version=current.version + 1,
           supersedes_id=current.entity_id,
           is_canonical=True,
           # Copy unchanged fields, apply updates
       )

       return new_entity
   ```

3. **Version Chain Traversal**
   - Forward: Given entity_id, find all versions that supersede it
   - Backward: Given entity_id, find all versions it supersedes
   - Full chain: Reconstruct complete entity evolution history

4. **Optimistic Locking Integration**
   - Per Algorithm C.3: Read version, compute update, CAS write
   - If version mismatch: re-read, re-merge, retry (max 5 attempts)
   - Version increments on every successful update

5. **Canonical Resolution**
   - Always query with `WHERE is_canonical = TRUE` for current state
   - Historical queries: allow is_canonical = FALSE with valid_from/valid_to filter
   - Index: `CREATE INDEX idx_kg_dom_canonical ON st_kg_dom(is_canonical, archival_status)`

6. **supersedes_id Chain Limits**
   - Warn if chain exceeds 10 versions (possible infinite loop)
   - GC: Tombstoned versions older than retention period can have chain compacted

**Reference**: Dossier Section 4.5.3, Section 6.8, Algorithm C.3
**Storage Target**: st_kg_dom.version, st_kg_dom.supersedes_id, st_kg_dom.is_canonical
**Storage Target**: st_kg_edges.version, st_kg_edges.supersedes_id, st_kg_edges.is_canonical

---

#### Issue 5.3.3: Implement Observation Count Updates

**What to cover**:

1. **Observation Semantics**
   - `observation_count`: How many times entity/relationship has been observed
   - Each sighting reinforces truth (Bayesian prior update)
   - Higher count = higher confidence = slower decay

2. **Observation Increment Triggers**
   - Entity mentioned in new event → `observation_count += 1`
   - Relationship co-occurrence in new event → `observation_count += 1`
   - Cluster containing entity processed → `observation_count += 1`

3. **REINFORCE Operation Implementation**

   ```python
   async def reinforce(
       entity: KGEntity,
       source_event_id: str
   ) -> None:
       # 1. Increment observation count
       entity.observation_count += 1

       # 2. Update last observed timestamp
       entity.last_observed_at = now()

       # 3. Boost confidence (diminishing returns)
       # confidence_boost = 1 / (1 + observation_count)
       entity.confidence_score = min(0.99,
           entity.confidence_score + (1 - entity.confidence_score) * 0.1
       )

       # 4. Reset decay factor (observation refreshes memory)
       entity.decay_factor = 1.0

       # 5. Append to source_episodes_json
       entity.source_episodes_json.append(source_event_id)
   ```

4. **last_observed_at Tracking**
   - Unix timestamp of most recent observation
   - Used for decay calculation: `days_since = (now - last_observed_at) / 86400`
   - Critical for R3 Synaptic Homeostasis pruning decisions

5. **Confidence Score Dynamics**
   - New entity: confidence = 0.5 (neutral prior)
   - Each observation: confidence approaches 1.0 asymptotically
   - Formula: `confidence = 1 - (1 - base)^observation_count`
   - Or simpler: `confidence = min(0.99, 0.5 + 0.1 * log(1 + observation_count))`

6. **source_episodes_json Management**
   - JSON array of event_ids that contributed to entity knowledge
   - Append-only during observations
   - Compact by removing tombstoned event references periodically
   - Max size: 1000 entries (drop oldest if exceeded)

**Reference**: Dossier Section 4.8, Algorithm C.2 (Bayesian Confidence Merging)
**Storage Target**: st_kg_dom.observation_count, st_kg_dom.last_observed_at
**Storage Target**: st_kg_dom.confidence_score, st_kg_dom.decay_factor
**Storage Target**: st_kg_edges (same fields)

---

### Epic 5.4: R4 Unit Tests

#### Issue 5.4.1: Entity Normalization Tests

**What to cover**:

1. **entities_json Parsing Tests**
   - Test valid JSON array parsing: `[{"text": "Mom", "type": "FAMILY_MEMBER", ...}]`
   - Test empty array: `"[]"` → returns empty entity list
   - Test malformed JSON handling: graceful degradation, log error
   - Test all 21 entity types (9 general + 12 family-specific)

2. **Entity Deduplication Tests**
   - Same text, same event → single entity (not duplicated)
   - "Mom" vs "my mother" → deduplicated with fuzzy matching
   - Different entity types → never merged (PERSON != LOCATION)
   - Case insensitivity: "John" == "john" == "JOHN"

3. **Canonical Name Resolution Tests**
   - Levenshtein > 0.85: "Jennifer" vs "Jenifer" → same entity
   - Levenshtein < 0.85: "Jennifer" vs "Janet" → different entities
   - Longer name preferred: "Dr. Smith" > "Smith"
   - Ties resolved alphabetically for determinism

4. **Alias Tracking Tests**
   - New alias added to aliases_json.names
   - Source event appended to aliases_json.sources[alias]
   - last_seen timestamp updated for alias
   - Alias limit respected (dedup, no unbounded growth)

5. **Integration with st_kg_dom Tests**
   - New entity → INSERT with is_canonical=TRUE
   - Existing entity match → UPDATE observation_count, last_observed_at
   - Version increment on UPDATE
   - first_mentioned_event_id preserved (earliest chronologically)

**Test File**: `tests/k0/modules/consolidation/test_entity_normalization.py`
**Fixtures**: Entity JSON samples from golden_dataset
**Reference**: Existing test patterns in tests/k0/modules/hippocampus/test_semantic_project_full.py

---

#### Issue 5.4.2: Relationship Discovery Tests

**What to cover**:

1. **M21 KGConsolidator Unit Tests**
   - Consolidate empty cluster → returns empty KGUpdate list
   - Consolidate cluster with entities → returns CREATE_ENTITY updates
   - Consolidate with existing KG overlap → returns UPDATE_ENTITY updates
   - Edge discovery → returns CREATE_EDGE updates

2. **Co-Occurrence Analysis Tests**
   - Two entities in same event → co_occurrence_count = 1
   - Two entities in 3 events → co_occurrence_count = 3
   - co_occurrence < min threshold → no edge created
   - Confidence formula: `min(0.9, 0.3 + 0.1 * count)` verified

3. **Hebbian Learning Tests**
   - Initial edge weight = 1.0
   - After observation: `weight_new = weight_old + 0.1 * (co_occ - weight_old)`
   - Multiple observations → weight approaches co_occurrence asymptotically
   - Learning rate configurable

4. **Temporal Relationship Tests**
   - Events within 1 hour → CONCURRENT_WITH edge
   - Event A before Event B → FOLLOWED_BY edge (A→B)
   - Events > 1 week apart → no temporal edge (below threshold)
   - Temporal confidence = 1 / (1 + hours_apart/24) verified

5. **Causal Inference Tests** (if implemented)
   - Insufficient data (< 10 events) → skip causal inference
   - A always precedes B → CAUSES edge with high confidence
   - Random co-occurrence → CORRELATES edge (low confidence)
   - Confidence interval includes 0 → no edge created

**Test File**: `tests/k0/modules/consolidation/test_relationship_discovery.py`
**Fixtures**: EpisodeCluster with multiple events, known entity co-occurrences

---

#### Issue 5.4.3: Temporal Graph Tests

**What to cover**:

1. **valid_from/valid_to Management Tests**
   - New entity: valid_from = first event timestamp
   - New edge: valid_from = first co-occurrence timestamp
   - Ended relationship: valid_to = last observation + buffer
   - Temporal query: returns only entities valid at query_time

2. **Version Chain Tests**
   - EVOLVE operation: version increments
   - supersedes_id links to previous version
   - is_canonical: only new version is TRUE
   - Chain traversal: can walk from latest to first version

3. **Optimistic Locking Tests**
   - Concurrent update same entity → one succeeds, one retries
   - Version mismatch detected → re-read and retry
   - Max 5 retries → fail with ConflictError
   - Successful retry → version correctly incremented

4. **Observation Count Tests**
   - New entity: observation_count = 1
   - REINFORCE operation: observation_count += 1
   - Confidence update: approaches 0.99 asymptotically
   - decay_factor reset to 1.0 on observation

5. **Neo4jKGDriver Integration Tests**
   - Reference existing tests: `tests/k0/drivers/test_neo4j_driver.py`
   - Test temporal property storage/retrieval

---

### Epic 5.5: K0 Architecture Master Closure

#### Issue 5.5.1: Milestone 5 K0 Updates

**What to Cover**:

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated to reflect M5 completion
- [ ] **Part 3.1 (Module Registry)**: M23 (KGConsolidator) row added
- [ ] **Part 4.1 (Event Topics)**: P03 KG consolidation events registered
- [ ] **Part 5.1 (Contract Registry)**: KGConsolidator module contract added
- [ ] **Part 5.2 (Syscall Matrix)**: Neo4j storage capabilities registered
- [ ] **Part 5.3 (Storage Tables)**: st_kg_entities, st_kg_edges tables documented
- [ ] **Part 7.1 (ADR Index)**: ADR status for M5 decisions updated
- [ ] **Version Header**: Document version bumped to reflect M5 completion

**K0 File**: `k0/pipelines/k0_architecture_master.md`

- Test version chain queries in Cypher
- Test observation count persistence

1. **Performance Tests**
   - Entity normalization: < 10ms for 100 entities
   - Co-occurrence analysis: < 50ms for 1000 entity pairs
   - Neo4j write batch: < 100ms for 50 updates
   - Reference P95 budgets from k0/config/neo4j.yaml

**Test File**: `tests/k0/modules/consolidation/test_temporal_graph.py`
**Docker Compose**: Uses neo4j:5.20.0 container per existing test infrastructure
**Reference**: tests/k0/drivers/test_neo4j_driver.py for Neo4j test patterns

---

## Milestone 5A: Dream Exploration (R5) - Optional

**Goal**: Implement creative exploration (can be deferred to Phase 2)
**Gate**: GATE 3 (Implementation)
**Note**: Skip if backlog > 500 or time constrained per Section 4.6.6

### Epic 5A.1: Counterfactual Thinking (CPN)

#### Issue 5A.1.1: Implement CPN Algorithm

<!-- "What if" scenario generation -->

#### Issue 5A.1.2: Implement Insight Extraction

<!-- Counterfactual outcomes -->

---

### Epic 5A.2: Forward Prediction (TPN-MCTS)

#### Issue 5A.2.1: Implement TPN-MCTS Algorithm

<!-- Monte Carlo Tree Search for future scenarios -->

#### Issue 5A.2.2: Implement Probability Estimation

<!-- Outcome likelihood scoring -->

---

### Epic 5A.3: Insight Generation (BGT-SM)

#### Issue 5A.3.1: Implement M22 DreamExplorer

<!-- Per Section 7.4.5 -->

#### Issue 5A.3.2: Implement Remote Association Discovery

<!-- Cross-domain pattern matching (Mednick) -->

#### Issue 5A.3.3: Implement Creative Connection Scoring

<!-- Novelty vs coherence balance -->

---

### Epic 5A.4: R5 Feature Flag

#### Issue 5A.4.1: Implement P03_FF_R5_MODE Flag

<!-- disabled, lightweight, full modes -->

#### Issue 5A.4.2: Implement Skip Logic

<!-- Skip when backlog > 500 or time < 60s remaining -->

---

### Epic 5A.5: K0 Architecture Master Closure

#### Issue 5A.5.1: Milestone 5A K0 Updates

**What to Cover**:

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated to reflect M5A completion (if implemented)
- [ ] **Part 3.1 (Module Registry)**: M25 (RemoteAssociationEngine) row added (if implemented)
- [ ] **Part 4.1 (Event Topics)**: P03 remote association events registered
- [ ] **Part 5.1 (Contract Registry)**: RemoteAssociationEngine module contract added (if implemented)
- [ ] **Part 5.2 (Syscall Matrix)**: Cross-domain query capabilities registered
- [ ] **Part 5.3 (Storage Tables)**: Remote association cache tables documented
- [ ] **Part 7.1 (ADR Index)**: ADR status for M5A decisions updated
- [ ] **Version Header**: Document version bumped to reflect M5A completion

**K0 File**: `k0/pipelines/k0_architecture_master.md`
**Note**: Only apply if R5 (Remote Association) is implemented per feature flag

---

## Milestone 6: Memory Writers (R6-R7)

**Goal**: Implement staging updates and 8-layer truth writes
**Gate**: GATE 3 (Implementation)
**Prerequisites**:

- M0 complete (including K0 kernel enhancements)
- M1-M5 complete

> **K0 Enhancement Dependency**: M6 uses the following K0 enhancements implemented in M0:
>
> - `UnitOfWork.execute_with_version_check()` (Epic 0.6): Used for optimistic concurrency in R7 truth writes
> - `VersionedWriteResult` (Epic 0.6): Used for conflict detection and retry logic
> - `AdvisoryLockService` (Epic 0.4): Lock heartbeat during long R7 write operations

### Epic 6.1: Staging Table Updates (R6)

#### Issue 6.1.1: Implement Consolidation Status Marking

**What to cover**:

1. **Consolidation Status Enum**
   - `PENDING`: Default, not yet processed by P03
   - `IN_PROGRESS`: Currently being processed in a cycle
   - `CONSOLIDATED`: Successfully processed, linked to truth
   - `DUPLICATE`: Identified as near-duplicate, marked for dedup
   - `PRUNED`: Below novelty threshold, flagged for decay
   - `PENDING_REVIEW`: Contradiction detected, needs resolution

2. **Status Transition Rules**

   ```
   PENDING → IN_PROGRESS     (cycle starts processing)
   IN_PROGRESS → CONSOLIDATED (successful reconciliation)
   IN_PROGRESS → DUPLICATE    (SimHash match found)
   IN_PROGRESS → PRUNED       (novelty < threshold)
   IN_PROGRESS → PENDING_REVIEW (contradiction detected)
   IN_PROGRESS → PENDING      (cycle aborted, rollback)
   ```

3. **Column Updates for st_hipp_events**
   - `consolidation_status`: Status enum value
   - `consolidation_cycle_id`: P03 cycle ULID that processed event
   - `consolidated_at`: Unix timestamp when processing completed
   - Update via single UPDATE statement with WHERE clause

4. **Batch Status Updates**
   - Process in batches of 100 events per dossier Section 7.4.7
   - Use transaction boundaries to ensure atomicity
   - On failure: rollback batch, reset status to PENDING

5. **Index Utilization**
   - Query by: `WHERE consolidation_status = 'PENDING' ORDER BY event_time_utc`
   - Index recommended: `idx_hipp_events_consolidation(consolidation_status, event_time_utc)`

**Reference**: Dossier Section 4.7.1, Section 6.2.2
**Storage Target**: st_hipp_events.consolidation_status, consolidation_cycle_id, consolidated_at

---

#### Issue 6.1.2: Implement Deduplication Metadata Updates

**What to cover**:

1. **Near-Duplicate Detection Results**
   - Populated during R3 (Synaptic Homeostasis)
   - SimHash Hamming distance <= 3 = near-duplicate

2. **Column Updates**
   - `near_duplicates_json`: JSON array of duplicate event_ids
     - Example: `["evt_01ABC", "evt_01DEF"]`
   - `novelty_score`: Float [0-1] from R3 novelty scoring
   - `is_near_duplicate`: Boolean flag for quick filtering

3. **near_duplicates_json Schema**

   ```json
   [
     {"event_id": "evt_01ABC", "hamming_distance": 2, "detected_at": 1704067200},
     {"event_id": "evt_01DEF", "hamming_distance": 3, "detected_at": 1704067200}
   ]
   ```

4. **Update Logic**

   ```python
   async def update_dedup_metadata(
       event_id: str,
       duplicates: List[DuplicateMatch],
       novelty: float
   ):
       near_dups = json.dumps([
           {"event_id": d.event_id, "hamming_distance": d.distance}
           for d in duplicates
       ])
       # PostgreSQL $N placeholder style
       await db.execute("""
           UPDATE st_hipp_events
           SET near_duplicates_json = $1,
               novelty_score = $2,
               is_near_duplicate = $3
           WHERE event_id = $4
       """, [near_dups, novelty, len(duplicates) > 0, event_id])
   ```

5. **Novelty Score Persistence**
   - Calculate in R3 using formula from Section 2.4
   - Store for future reference (avoid recalculation)
   - Used by R1 importance scoring in subsequent cycles

**Reference**: Dossier Section 4.7.2, Section 4.4.2
**Storage Target**: st_hipp_events.near_duplicates_json, novelty_score, is_near_duplicate

---

#### Issue 6.1.3: Implement Cluster Assignment Updates

**What to cover**:

1. **Cluster Assignment from R2**
   - DBSCAN clustering produces episode_cluster_id
   - Each event assigned to exactly one cluster (or noise = -1)

2. **Column Updates**
   - `episode_cluster_id`: Cluster ID (ULID format)
   - `cluster_confidence`: Float [0-1], based on distance to centroid
   - `clustering_version`: Algorithm version string (e.g., "dbscan_v1.0")

3. **Cluster Confidence Calculation**
   - Distance from event embedding to cluster centroid
   - `confidence = 1.0 - (distance / max_cluster_radius)`
   - Capped at [0.1, 1.0] range

4. **Noise Handling**
   - DBSCAN noise points: `episode_cluster_id = NULL`
   - `cluster_confidence = 0.0` for noise
   - May form singleton clusters in future cycles

5. **Batch Update Pattern**

   ```python
   async def assign_clusters(
       assignments: List[ClusterAssignment]
   ):
       # PostgreSQL $N placeholder style with executemany
       for batch in chunk(assignments, 100):
           await db.executemany("""
               UPDATE st_hipp_events
               SET episode_cluster_id = $1,
                   cluster_confidence = $2,
                   clustering_version = $3
               WHERE event_id = $4
           """, [(a.cluster_id, a.confidence, a.version, a.event_id)
                 for a in batch])
   ```

**Reference**: Dossier Section 4.3.1, Section 4.7.2
**Storage Target**: st_hipp_events.episode_cluster_id, cluster_confidence, clustering_version

---

#### Issue 6.1.4: Implement Reconciliation Decision Recording

**What to cover**:

1. **Reconciliation Decision Types**
   - `REINFORCE`: Matched existing truth, boost confidence
   - `EXTEND`: Matched existing truth, add new context
   - `CREATE`: No match, create new truth record
   - `EVOLVE`: Significant change, version truth record
   - `PRUNE`: Low importance, mark for decay
   - `CONTRADICT`: Conflicts with existing truth

2. **Column Updates**
   - `reconciliation_decision`: Decision type enum
   - `truth_match_id`: ID of matched truth record (if any)
   - `truth_match_similarity`: Cosine similarity to matched truth

3. **Decision Recording Schema**

   ```python
   @dataclass
   class ReconciliationRecord:
       event_id: str
       decision: str           # REINFORCE, EXTEND, etc.
       truth_match_id: str     # st_epi.episode_id, st_sem.fact_id, etc.
       truth_match_layer: str  # Which layer: st_epi, st_sem, etc.
       similarity_score: float # [0-1] cosine similarity
       confidence: float       # Decision confidence
   ```

4. **Link to Truth Tables**
   - `truth_match_id` references polymorphic truth record
   - Layer indicated by `truth_match_layer` field
   - Enables traceability: "Which events support this fact?"

5. **Batch Recording**
   - Record decisions as R6 processes each cluster
   - Transaction-safe: all-or-nothing per cluster
   - On conflict: log warning, continue with next cluster

**Reference**: Dossier Section 4.7.3, Section 3.2 (Decision Matrix)
**Storage Target**: st_hipp_events.reconciliation_decision, truth_match_id, truth_match_similarity

---

### Epic 6.2: Outbox Pattern Implementation

#### Issue 6.2.1: Implement M24 TruthWriter

**What to cover**:

1. **M24 TruthWriter Interface per Section 7.4.7**

   ```python
   class TruthWriter:
       def __init__(self, config: WriterConfig):
           self.batch_size = config.batch_size          # Default: 100
           self.transaction_mode = config.transaction   # 'ATOMIC' or 'PARTIAL'
           self.outbox_driver = config.outbox_driver

       async def write_decisions(
           decisions: List[ReconciliationDecision]
       ) -> WriteResult
   ```

2. **Decision Routing**
   - Route each decision to appropriate layer writer:
     - `REINFORCE` → Call `_reinforce()` on matched layer
     - `EXTEND` → Call `_extend()` to add context
     - `CREATE` → Call `_create()` for new truth record
     - `EVOLVE` → Call `_evolve()` with versioning
     - `PRUNE` → Call `_prune()` for decay marking
     - `CONTRADICT` → Call `_emit_gap()` for P06 Active Learning

3. **WriteResult Response**

   ```python
   @dataclass
   class WriteResult:
       successes: List[str]           # Decision IDs that succeeded
       failures: List[Tuple[str, str]]  # (decision_id, error_message)
       metrics: WriteMetrics          # Timing, counts
   ```

4. **Error Handling**
   - ATOMIC mode: Any failure rolls back entire batch
   - PARTIAL mode: Continue on failure, collect errors
   - Log all failures with decision_id and error details
   - Emit `p03.write.failed.v1` event for monitoring

5. **Layer Writer Dispatch**
   - Determine target layer from decision.target_layer
   - Call appropriate writer: st_epi, st_sem, st_procedural, etc.
   - Pass transaction context for atomicity

**Reference**: Dossier Section 7.4.7
**Integration Point**: K0 outbox infrastructure

---

#### Issue 6.2.2: Integrate with K0 st_outbox

**What to cover**:

1. **K0 Outbox Pattern Overview**
   - All durable writes go through st_outbox table
   - Ensures exactly-once delivery semantics
   - Outbox workers process entries asynchronously

2. **st_outbox Entry Format**

   ```python
   @dataclass
   class OutboxEntry:
       entry_id: str             # ULID
       topic: str                # Target driver/topic
       payload: bytes            # JSON-encoded operation
       created_at: int           # Unix timestamp
       status: str               # PENDING, PROCESSING, DONE, FAILED
       retry_count: int          # Number of retries
       cognitive_trace_id: str   # Observability
   ```

3. **Write Pattern**

   ```python
   async def write_via_outbox(
       decision: ReconciliationDecision,
       txn: Transaction
   ):
       entry = OutboxEntry(
           entry_id=generate_ulid(),
           topic=f"truth.{decision.target_layer}",
           payload=json.dumps(decision.to_payload()).encode(),
           status='PENDING',
           cognitive_trace_id=decision.trace_id
       )
       await txn.insert('st_outbox', entry)
   ```

4. **Transactional Guarantees**
   - Outbox entry created in SAME transaction as status update
   - If transaction commits → outbox entry persisted
   - If transaction fails → both rollback together

5. **Outbox Worker Processing**
   - K0 outbox workers poll st_outbox for PENDING entries
   - Process and apply to target layer
   - Update status to DONE on success, FAILED on error

**Reference**: K0 storage/outbox module, Dossier Section 4.8.1
**Storage Target**: st_outbox table

---

#### Issue 6.2.3: Implement Transaction Boundaries

**What to cover**:

1. **Transaction Modes**
   - `ATOMIC`: Entire batch succeeds or fails together
   - `PARTIAL`: Individual decisions can fail independently

2. **Batch Size Configuration**
   - Default: 100 decisions per batch (per Section 7.4.7)
   - Configurable via P03 config
   - Trade-off: Larger = more efficient, smaller = faster recovery

3. **Transaction Scope**

   ```python
   async def process_batch(
       decisions: List[ReconciliationDecision],
       mode: str
   ):
       if mode == 'ATOMIC':
           async with db.transaction() as txn:
               for decision in decisions:
                   await apply_decision(decision, txn)
               # All succeed or all rollback
       else:  # PARTIAL
           for decision in decisions:
               try:
                   async with db.transaction() as txn:
                       await apply_decision(decision, txn)
               except Exception as e:
                   log_failure(decision.id, e)
                   continue
   ```

4. **Savepoint Strategy**
   - For PARTIAL mode: Use savepoints within batch
   - Rollback to savepoint on individual failure
   - Continue processing remaining decisions

5. **Timeout Handling**
   - Per-batch timeout: 60 seconds default
   - Per-decision timeout: 5 seconds
   - On timeout: Abort, rollback, log, emit alert

6. **Idempotency**
   - Each decision has unique ID
   - Check if already processed before applying
   - Prevents duplicate writes on retry

**Reference**: Dossier Section 4.8.1, Algorithm C.3 (Optimistic Locking)
**Integration Point**: K0 UnitOfWork pattern

---

### Epic 6.3: Memory Layer Writers (R7)

<!-- Per Section 4.8 - Bidirectional Truth Reconciliation -->
<!-- Key Principle: Truth tables ARE truth; new signals are CANDIDATES -->
<!-- Version conflicts use optimistic locking per Algorithm C.3 -->

#### Issue 6.3.1: Implement st_epi Writer

**What to cover**:

1. **Episodic Memory (st_epi) Purpose**
   - Brain analog: Hippocampus (episodic memory)
   - Stores consolidated episode records from R2 clusters
   - Each episode represents a coherent experience

2. **Write Mode: CREATE (New Episode from Cluster)**

   ```python
   async def create_episode(
       cluster: EpisodeCluster,
       txn: Transaction
   ) -> str:
       episode = Episode(
           episode_id=generate_ulid(),
           tenant_id=cluster.tenant_id,
           space_id=cluster.space_id,
           # Content
           summary=cluster.generate_summary(),
           source_events_json=json.dumps(cluster.event_ids),
           # Metrics
           importance_score=cluster.importance,
           emotional_salience=cluster.emotional_salience,
           access_count=1,
           # Embedding: cluster centroid via Algorithm C.7
           embedding_id=cluster.centroid_embedding_id,
           # Temporal
           valid_from=cluster.earliest_event_at,
           created_at=now()
       )
       await txn.insert('st_epi', episode)
       return episode.episode_id
   ```

3. **Cluster Centroid Calculation (Algorithm C.7)**
   - Average embeddings of all events in cluster
   - `centroid = mean([e.embedding for e in cluster.events])`
   - Store centroid in st_vec, link via embedding_id

4. **Importance & Salience Propagation**
   - `importance_score`: Max importance from cluster events
   - `emotional_salience`: Weighted average of affect_valence * affect_arousal
   - Initial `access_count = 1`, incremented on P01 recall

5. **Source Events Linkage**
   - `source_events_json`: Array of event_ids in cluster
   - Enables traceability: "Which events formed this episode?"

**Reference**: Dossier Section 4.8.2, Section 6.3 (st_epi schema)
**Storage Target**: st_epi table

---

#### Issue 6.3.2: Implement st_sem Writer

**What to cover**:

1. **Semantic Memory (st_sem) Purpose**
   - Brain analog: Temporal cortex (semantic memory)
   - Stores patterns: ROUTINE, PREFERENCE, THEME, RELATIONSHIP, GOAL, VALUE
   - Abstracted knowledge extracted from episodes

2. **Write Modes**
   - `REINFORCE`: Existing pattern confirmed, boost confidence
   - `EXTEND`: Add new examples to existing pattern
   - `CREATE`: New pattern discovered
   - `EVOLVE`: Pattern changed significantly, version update

3. **REINFORCE Implementation**

   ```python
   async def reinforce_pattern(
       pattern_id: str,
       source_event_id: str,
       txn: Transaction
   ):
       # PostgreSQL $N placeholder style, jsonb_insert for array append
       await txn.execute("""
           UPDATE st_sem SET
               observation_count = observation_count + 1,
               confidence_score = LEAST(0.99, confidence_score + (1 - confidence_score) * 0.1),
               last_observed_at = $1,
               decay_factor = 1.0,
               source_episodes_json = source_episodes_json || to_jsonb($2::text)
           WHERE pattern_id = $3
       """, [now(), source_event_id, pattern_id])
   ```

4. **Confidence Merge per Algorithm C.2 (Bayesian)**
   - `posterior = prior * likelihood / evidence`
   - Simplified: `new_confidence = old + (1 - old) * learning_rate`
   - Default learning_rate = 0.1

5. **CREATE Implementation**
   - Generate new pattern_id (ULID)
   - Set initial confidence = 0.5
   - Populate pattern_attributes_json from extraction
   - Set source_episodes_json with originating events

6. **EVOLVE Implementation**
   - Version increment, supersedes_id linking
   - Old record: is_canonical = FALSE
   - New record: is_canonical = TRUE, copy + modify

**Reference**: Dossier Section 4.8.3, Section 6.4 (st_sem schema)
**Storage Target**: st_sem table

---

#### Issue 6.3.3: Implement st_procedural Writer

**What to cover**:

1. **Procedural Memory (st_procedural) Purpose**
   - Brain analog: Basal ganglia (procedural memory)
   - Stores habits, routines, recurring behavioral patterns
   - "Things done automatically without conscious thought"

2. **Routine Detection Criteria**
   - Same action, same time, same context > 3 times
   - Temporal regularity: actions occur at consistent times
   - Context consistency: same location, participants, etc.

3. **Habit Strength Formula**

   ```python
   habit_strength = observation_count / (days_observed * expected_frequency)
   # Example: 10 observations over 14 days, expected daily
   # strength = 10 / (14 * 1) = 0.71 (71% adherence)
   ```

4. **Streak Tracking**
   - `streak_count`: Consecutive occurrences without miss
   - `streak_broken_at`: Timestamp when streak broke
   - Broken streak triggers decay, not immediate removal

5. **Temporal Pattern Storage**

   ```json
   {
     "temporal_anchor": "07:30",
     "day_pattern": "WEEKDAYS",
     "frequency": "DAILY",
     "tolerance_minutes": 30
   }
   ```

6. **REINFORCE for Routines**
   - Increment observation_count
   - Update streak_count if within tolerance
   - Recalculate regularity_score

**Reference**: Dossier Section 4.8.4, Section 6.5 (st_procedural schema)
**Storage Target**: st_procedural table

---

#### Issue 6.3.4: Implement st_social Writer

**What to cover**:

1. **Social Memory (st_social) Purpose**
   - Brain analog: Social brain network
   - Tracks relationships between people
   - Stores interaction history, relationship strength

2. **Hebbian Relationship Learning**
   - "People who interact together strengthen bonds"
   - Co-occurrence increases relationship_strength
   - Non-interaction triggers decay

3. **Relationship Strength Update**

   ```python
   async def update_relationship(
       actor_a: str,
       actor_b: str,
       interaction_sentiment: float,
       txn: Transaction
   ):
       # PostgreSQL $N placeholder style, Hebbian learning
       await txn.execute("""
           UPDATE st_social SET
               interaction_count = interaction_count + 1,
               relationship_strength = relationship_strength + 0.1 * (1 - relationship_strength),
               avg_sentiment = (avg_sentiment * interaction_count + $1) / (interaction_count + 1),
               last_interaction_at = $2
           WHERE actor_a_id = $3 AND actor_b_id = $4 AND is_canonical = TRUE
       """, [interaction_sentiment, now(), actor_a, actor_b])
   ```

4. **Decay on Non-Interaction**
   - If last_interaction_at > 30 days: apply decay
   - `decay = exp(-lambda * days_since_interaction)`
   - Update relationship_strength *= decay

5. **Interaction Frequency Classification**
   - DAILY: < 2 days between interactions
   - WEEKLY: 2-10 days
   - MONTHLY: 10-45 days
   - RARE: > 45 days

**Reference**: Dossier Section 4.8.5, Section 6.6 (st_social schema)
**Storage Target**: st_social table

---

#### Issue 6.3.5: Implement st_prospective Writer

**What to cover**:

1. **Prospective Memory (st_prospective) Purpose**
   - Brain analog: Prefrontal cortex (future thinking)
   - Stores intentions, goals, reminders
   - "Things to remember to do in the future"

2. **Status Transitions**

   ```
   PENDING → ACTIVE      (Start working on goal)
   ACTIVE → COMPLETED    (Goal achieved)
   ACTIVE → ABANDONED    (Goal given up)
   PENDING → EXPIRED     (Deadline passed without action)
   ```

3. **Deadline Tracking**
   - `deadline_at`: When intention must be completed
   - `reminder_at`: When to remind user
   - Emit reminder events as deadlines approach

4. **Goal Inference from Patterns**
   - Detect recurring future references: "I want to...", "I plan to..."
   - Extract goal from semantic analysis
   - Link to supporting events (source_episodes_json)

5. **Progress Tracking**

   ```python
   @dataclass
   class Intention:
       intention_id: str
       intention_type: str  # GOAL, REMINDER, TASK
       description: str
       status: str          # PENDING, ACTIVE, COMPLETED, ABANDONED
       deadline_at: int
       progress_pct: float  # 0-100
       milestones_json: str # Intermediate checkpoints
   ```

6. **Reminder Emission**
   - Emit `p03.reminder.due.v1` event when reminder_at reached
   - P01 or notification system handles user-facing reminder

**Reference**: Dossier Section 4.8.6, Section 6.7 (st_prospective schema)
**Storage Target**: st_prospective table

---

#### Issue 6.3.6: Implement st_kg_dom Writer

**What to cover**:

1. **Knowledge Graph Entities (st_kg_dom) Purpose**
   - Brain analog: Semantic memory (concept nodes)
   - Canonical entity records: people, places, organizations, things
   - Written by R4 entity extraction

2. **Write Operations**
   - `CREATE`: New entity discovered
   - `UPDATE`: Merge aliases, increment observation_count
   - `EVOLVE`: Significant attribute change

3. **Alias Merging**

   ```python
   async def merge_aliases(
       entity_id: str,
       new_aliases: List[str],
       txn: Transaction
   ):
       # PostgreSQL jsonb_set for JSON updates, $N placeholder style
       await txn.execute("""
           UPDATE st_kg_dom SET
               aliases_json = aliases_json || $1::jsonb,
               observation_count = observation_count + 1,
               last_observed_at = $2
           WHERE entity_id = $3
       """, [json.dumps({"names": new_aliases}), now(), entity_id])
   ```

4. **Observation Count & Confidence**
   - Each mention increments observation_count
   - Confidence increases with observations
   - Higher observation_count = slower decay

5. **valid_from/valid_to Tracking**
   - Temporal validity for entity attributes
   - "Mom worked at Hospital from 2020-2023"
   - Enables historical queries

6. **Integration with Neo4jKGDriver**
   - **PostgreSQL st_kg_dom is source of truth**
   - Neo4j updated via outbox pattern
   - Sync on write, not on read

**Reference**: Dossier Section 4.8.7, Section 6.8 (st_kg_dom schema)
**Storage Target**: st_kg_dom table, Neo4j via outbox

---

#### Issue 6.3.7: Implement st_kg_edges Writer

**What to cover**:

1. **Knowledge Graph Edges (st_kg_edges) Purpose**
   - Brain analog: Associative connections
   - Typed relationships between entities
   - Temporal validity for relationship evolution

2. **Hebbian Edge Learning (Algorithm C.5)**

   ```python
   # Learning rate default: 0.1
   weight_new = weight_old + learning_rate * (co_occurrence - weight_old)

   async def update_edge_weight(
       edge_id: str,
       co_occurrence: int,
       learning_rate: float = 0.1,
       txn: Transaction
   ):
       # PostgreSQL $N placeholder style
       await txn.execute("""
           UPDATE st_kg_edges SET
               edge_weight = edge_weight + $1 * ($2 - edge_weight),
               co_occurrence_count = $3,
               observation_count = observation_count + 1,
               last_observed_at = $4
           WHERE edge_id = $5
       """, [learning_rate, co_occurrence, co_occurrence, now(), edge_id])
   ```

3. **Edge Creation**
   - Generate edge_id (ULID)
   - Set source_entity_id, target_entity_id
   - Initial edge_weight = 1.0, confidence = 0.5
   - Set valid_from to first observation

4. **Relationship Type Assignment**
   - Inferred from entity types and context
   - Types: WORKS_AT, LIVES_IN, KNOWS, FAMILY, LIKES, etc.
   - Can be explicit from NLP or inferred from co-occurrence

5. **Confidence Scoring**
   - `confidence = min(0.9, 0.3 + 0.1 * co_occurrence_count)`
   - Higher co-occurrence = higher confidence
   - Capped at 0.9 (never fully certain)

**Reference**: Dossier Section 4.8.7, Section 6.9 (st_kg_edges schema), Algorithm C.5
**Storage Target**: st_kg_edges table, Neo4j via outbox

---

#### Issue 6.3.8: Implement st_vec Placeholder Writer

**What to cover**:

1. **Embeddings (st_vec) Purpose**
   - Stores UltraBERT 768-dim embeddings
   - Written by P02 inline embedding (M23)
   - Indexed by P08 for similarity search

2. **P03 Role: Status Coordination**
   - P03 does NOT generate embeddings
   - P03 updates embedding_status for P08 coordination
   - Status: PENDING, STALE, CURRENT

3. **Status Updates**

   ```python
   async def mark_embedding_stale(
       embedding_id: str,
       reason: str,
       txn: Transaction
   ):
       # PostgreSQL $N placeholder style
       # Mark for re-indexing by P08
       await txn.execute("""
           UPDATE st_vec SET
               status = 'STALE',
               updated_at = $1
           WHERE embedding_id = $2
       """, [now(), embedding_id])
   ```

4. **When to Mark STALE**
   - Pattern evolved significantly (centroid shifted)
   - Entity merged (need new combined embedding)
   - Truth contradiction resolved (context changed)

5. **DO NOT Use Deprecated embedding_queue**
   - Old pattern: queue embeddings for processing
   - New pattern: P08 polls st_vec for PENDING/STALE status
   - Ensures no orphaned queue entries

6. **FAISS Integration Coordination**
   - `faiss_id`: Set by P08 when indexed
   - `indexed_at`: Timestamp of indexing
   - P03 never writes these fields directly

**Reference**: Dossier Section 4.8.8, Section 6.10 (st_vec schema)
**Storage Target**: st_vec.status only (other fields owned by P02/P08)

---

#### Issue 6.3.9: Implement Optimistic Locking Using K0 UnitOfWork

**What to cover**:

> **K0 Enhancement**: This issue uses `UnitOfWork.execute_with_version_check()` implemented in Epic 0.6.

1. **Optimistic Locking per Algorithm C.3 + K0 UoW Integration**
   - Use K0's `execute_with_version_check()` method (Epic 0.6)
   - Automatic retry with exponential backoff
   - Structured `VersionedWriteResult` for conflict detection

2. **Implementation Pattern Using K0 UoW**

   ```python
   from k0.uow.versioning import VersionedWriteResult, VersionConflictError
   from k0.uow.helpers import build_versioned_update, execute_versioned_update_with_retry

   async def update_with_locking(
       uow: UnitOfWork,
       table: str,
       record_id: str,
       primary_key: dict,
       refresh_callback: Callable,
       update_callback: Callable
   ) -> VersionedWriteResult:
       """
       Update record with optimistic concurrency using K0 UoW.

       Args:
           uow: Active UnitOfWork context
           table: Target table name
           record_id: For logging
           primary_key: Dict of PK columns and values
           refresh_callback: Async fn to fetch current row
           update_callback: Fn that takes current row, returns new values

       Returns:
           VersionedWriteResult with success/conflict info

       Raises:
           VersionConflictError: If max retries (3) exceeded
       """
       return await execute_versioned_update_with_retry(
           uow=uow,
           table=table,
           primary_key=primary_key,
           refresh_callback=refresh_callback,
           update_callback=update_callback,
           version_column="version",
           max_retries=3
       )

   # Example usage for st_sem
   async def reinforce_semantic_pattern(
       uow: UnitOfWork,
       pattern_id: str,
       new_observation: ObservationData
   ) -> VersionedWriteResult:
       async def refresh():
           return await fetch_pattern(uow, pattern_id)

       def compute_update(current: dict) -> dict:
           return {
               "observation_count": current["observation_count"] + 1,
               "confidence_score": merge_confidence(current, new_observation),
               "last_observed_at": int(time.time()),
               "updated_at": int(time.time())
           }

       return await update_with_locking(
           uow, "st_sem", pattern_id,
           {"pattern_id": pattern_id},
           refresh, compute_update
       )
   ```

3. **Version Increment** (handled by K0 helper)
   - `build_versioned_update()` adds `version = version + 1`
   - Every successful update increments version
   - Version is INTEGER, monotonically increasing

4. **Conflict Detection** (handled by K0 UoW)
   - `execute_with_version_check()` returns `VersionedWriteResult`
   - `version_conflict=True` if rows_affected=0
   - Automatic retry with exponential backoff (100ms, 200ms, 400ms)

5. **Merge Strategy on Conflict**
   - `refresh_callback` fetches current state on retry
   - `update_callback` computes merge with fresh data
   - K0 handles retry loop automatically

**Reference**: Dossier Algorithm C.3, Epic 0.6 (K0 Optimistic Concurrency)
**Applies To**: All truth tables with version column

---

#### Issue 6.3.10: Implement Confidence Merging

**What to cover**:

1. **Bayesian Confidence per Algorithm C.2**
   - `posterior = prior * likelihood / evidence`
   - Simplified approximation for efficiency

2. **Simplified Confidence Update**

   ```python
   def merge_confidence(
       current: float,
       observation_strength: float,
       learning_rate: float = 0.1
   ) -> float:
       # Asymptotic approach to 1.0
       return current + learning_rate * (observation_strength - current)
   ```

3. **Decision-Specific Confidence Changes**
   - `REINFORCE`: Boost confidence (observation_strength = 1.0)
   - `EXTEND`: Modest boost (observation_strength = 0.8)
   - `CREATE`: Initial confidence = 0.5
   - `EVOLVE`: Slight reduction (uncertainty from change)
   - `CONTRADICT`: Apply 0.3 penalty

4. **CONTRADICT Handling per Section 12.2.3**

   ```python
   def apply_contradiction_penalty(
       current: float,
       penalty: float = 0.3
   ) -> float:
       # Reduce confidence on contradiction
       return max(0.1, current - penalty)
   ```

5. **Confidence Bounds**
   - Minimum: 0.1 (never fully reject)
   - Maximum: 0.99 (never fully certain)
   - Initial: 0.5 (neutral prior)

6. **Confidence Decay**
   - Over time without observation, confidence decays
   - Integrated with decay_factor calculation
   - `effective_confidence = confidence * decay_factor`

**Reference**: Dossier Algorithm C.2, Section 12.2.3
**Applies To**: All truth tables with confidence_score column

---

### Epic 6.4: P08 Coordination

#### Issue 6.4.1: Implement Embedding Request Events

**What to cover**:

1. **Event Topic: cognitive.embedding.requested.v1**
   - Emitted when new embedding needed
   - P08 subscribes and processes requests
   - NOT used for P02 inline embeddings (already generated)

2. **Event Payload Schema**

   ```python
   @dataclass
   class EmbeddingRequestEvent:
       event_type: str = "cognitive.embedding.requested.v1"
       embedding_id: str        # Target embedding_id in st_vec
       source_type: str         # 'EPISODE', 'PATTERN', 'ENTITY'
       source_id: str           # episode_id, pattern_id, or entity_id
       priority: str            # 'HIGH', 'NORMAL', 'LOW'
       cognitive_trace_id: str
       requested_at: int        # Unix timestamp
   ```

3. **When to Request Embeddings**
   - New episode created from cluster (centroid embedding)
   - Pattern evolved significantly (new centroid needed)
   - Entity merged (combined embedding needed)

4. **Emission via Outbox**

   ```python
   async def request_embedding(
       source_type: str,
       source_id: str,
       priority: str,
       txn: Transaction
   ):
       event = EmbeddingRequestEvent(
           embedding_id=generate_ulid(),
           source_type=source_type,
           source_id=source_id,
           priority=priority,
           cognitive_trace_id=current_trace_id()
       )
       await emit_via_outbox(event, txn)
   ```

5. **Priority Levels**
   - `HIGH`: User-facing recall needs this embedding
   - `NORMAL`: Background consolidation, no urgency
   - `LOW`: Batch processing, can wait

**Reference**: Dossier Section 4.8.8, P08 pipeline contract
**Event Bus Topic**: cognitive.embedding.requested.v1

---

#### Issue 6.4.2: Implement Backpressure Checks

**What to cover**:

1. **Backpressure Threshold per Issue 0.2.3**
   - If pending embedding count > 10,000: PAUSE P03
   - Prevents overwhelming P08 indexing pipeline
   - Resume when pending < 5,000 (hysteresis)

2. **Pending Count Query**

   ```python
   async def get_pending_embedding_count() -> int:
       result = await db.fetch_one("""
           SELECT COUNT(*) as cnt FROM st_vec
           WHERE status IN ('PENDING', 'STALE')
       """)
       return result['cnt']
   ```

3. **Backpressure Check Integration**

   ```python
   async def should_pause_consolidation() -> bool:
       pending = await get_pending_embedding_count()
       if pending > 10_000:
           logger.warning(f"Backpressure: {pending} pending embeddings")
           return True
       return False
   ```

4. **Pause Behavior**
   - Log warning with pending count
   - Emit `p03.backpressure.activated.v1` event
   - Skip R4 KG consolidation (embedding-dependent)
   - Continue R3 deduplication (SimHash-based, no embedding)

5. **Resume Behavior**
   - Poll pending count every 30 seconds during pause
   - Resume when pending < 5,000
   - Emit `p03.backpressure.released.v1` event

6. **Metrics**
   - `p03_backpressure_active` gauge (0 or 1)
   - `p03_pending_embeddings` gauge (current count)
   - Alert if backpressure active > 10 minutes

**Reference**: Issue 0.2.3 (P08 Backpressure), Dossier Section 13.6
**Integration Point**: P08 embedding pipeline

---

#### Issue 6.4.3: Implement Circuit Breaker for P08

**What to cover**:

1. **Circuit Breaker Pattern per Section 13.6**
   - Prevent cascading failures if P08 is unhealthy
   - States: CLOSED (normal), OPEN (failing), HALF_OPEN (testing)

2. **Circuit Breaker Configuration**

   ```python
   @dataclass
   class CircuitBreakerConfig:
       failure_threshold: int = 5      # Failures to trip
       success_threshold: int = 3      # Successes to close
       timeout_seconds: int = 60       # Time before half-open
       half_open_max_calls: int = 3    # Test calls in half-open
   ```

3. **State Transitions**

   ```
   CLOSED → OPEN        (failure_count >= threshold)
   OPEN → HALF_OPEN     (timeout elapsed)
   HALF_OPEN → CLOSED   (success_count >= threshold)
   HALF_OPEN → OPEN     (any failure)
   ```

4. **P08 Health Detection**
   - Monitor embedding request success/failure
   - Track response latency (timeout = failure)
   - Count consecutive failures

5. **Behavior When OPEN**
   - Do not emit embedding requests
   - Queue requests locally (bounded queue: 1000 max)
   - Log circuit breaker state
   - Emit `p03.circuit_breaker.open.v1` alert

6. **Integration with Consolidation**

   ```python
   async def request_embedding_with_circuit_breaker(
       request: EmbeddingRequest
   ) -> bool:
       if circuit_breaker.state == 'OPEN':
           logger.warning("Circuit breaker OPEN, queueing request")
           local_queue.append(request)
           return False

       try:
           await emit_embedding_request(request)
           circuit_breaker.record_success()
           return True
       except Exception as e:
           circuit_breaker.record_failure()
           raise
   ```

**Reference**: Dossier Section 13.6, Circuit Breaker pattern
**Integration Point**: P08 embedding pipeline health monitoring

---

### Epic 6.5: R6-R7 Unit Tests

#### Issue 6.5.1: Staging Update Tests

**What to cover**:

1. **Consolidation Status Tests**
   - Test all status transitions: PENDING → IN_PROGRESS → CONSOLIDATED
   - Test DUPLICATE, PRUNED, PENDING_REVIEW paths
   - Test rollback: IN_PROGRESS → PENDING on abort
   - Verify consolidation_cycle_id populated

2. **Deduplication Metadata Tests**
   - near_duplicates_json valid JSON format
   - novelty_score in [0, 1] range
   - is_near_duplicate flag consistency with near_duplicates_json
   - Empty duplicates → is_near_duplicate = FALSE

3. **Cluster Assignment Tests**
   - episode_cluster_id is valid ULID
   - cluster_confidence in [0.1, 1.0] range
   - Noise points: cluster_id = NULL, confidence = 0.0
   - clustering_version matches expected algorithm version

4. **Reconciliation Recording Tests**
   - All decision types recorded correctly
   - truth_match_id references valid record
   - truth_match_similarity in [0, 1] range
   - Batch recording: all-or-nothing semantics

5. **Index Utilization Tests**
   - Verify idx_hipp_events_consolidation used for PENDING queries
   - Query performance < 10ms for 10K events

**Test File**: `tests/k0/modules/consolidation/test_staging_updates.py`
**Fixtures**: st_hipp_events records with various states

---

#### Issue 6.5.2: Outbox Pattern Tests

**What to cover**:

1. **M24 TruthWriter Tests**
   - write_decisions() returns correct WriteResult
   - ATOMIC mode: failure rollbacks all decisions
   - PARTIAL mode: continues on individual failure
   - Empty decisions list handled gracefully

2. **st_outbox Integration Tests**
   - OutboxEntry created with correct topic
   - Payload serialization valid JSON
   - Transaction atomicity: status + outbox together
   - Rollback: neither persisted on failure

3. **Transaction Boundary Tests**
   - Batch size respected (100 default)
   - Savepoint creation in PARTIAL mode
   - Timeout handling: abort after 60s
   - Idempotency: duplicate decision_id rejected

4. **Error Handling Tests**
   - Invalid decision type → ValueError
   - Database error → proper rollback
   - Retry exhaustion → ConflictError raised
   - Failure event emitted on persistent failure

**Test File**: `tests/k0/modules/consolidation/test_outbox_pattern.py`
**Fixtures**: Mock transaction context, sample ReconciliationDecisions

---

#### Issue 6.5.3: Layer Writer Tests (each layer)

**What to cover**:

1. **st_epi Writer Tests**
   - CREATE: Episode inserted with correct fields
   - importance_score, emotional_salience propagated
   - embedding_id links to cluster centroid
   - source_events_json valid array

2. **st_sem Writer Tests**
   - REINFORCE: observation_count incremented
   - EXTEND: source_episodes_json appended
   - CREATE: New pattern with confidence = 0.5
   - EVOLVE: version incremented, supersedes_id set

3. **st_procedural Writer Tests**
   - Routine detection: 3+ observations required
   - Habit strength formula verified
   - Streak tracking: increment and break
   - Temporal pattern storage format

4. **st_social Writer Tests**
   - Relationship strength Hebbian update
   - Decay on non-interaction
   - avg_sentiment running average
   - Interaction frequency classification

5. **st_prospective Writer Tests**
   - Status transitions valid
   - Deadline tracking functional
   - Progress percentage bounds [0, 100]
   - Reminder event emission

6. **st_kg_dom Writer Tests**
   - Entity creation with canonical_name
   - Alias merging (no duplicates)
   - observation_count increment
   - valid_from/valid_to temporal bounds

7. **st_kg_edges Writer Tests**
   - Edge creation with correct endpoints
   - Hebbian weight update formula
   - Confidence formula: min(0.9, 0.3 + 0.1 * count)
   - co_occurrence_count tracking

8. **st_vec Status Writer Tests**
   - Status transitions: PENDING → STALE
   - DO NOT modify other st_vec fields
   - Integration with P08 polling

**Test File**: `tests/k0/modules/consolidation/test_layer_writers.py`
**Fixtures**: Sample decisions for each layer type

---

#### Issue 6.5.4: P08 Coordination Tests

**What to cover**:

1. **Embedding Request Event Tests**
   - Event payload schema validation
   - Priority levels: HIGH, NORMAL, LOW
   - cognitive_trace_id propagated
   - Emission via outbox

2. **Backpressure Tests**
   - Pending count > 10K → pause consolidation
   - Pending count < 5K → resume (hysteresis)
   - Skip R4 when paused, continue R3
   - Metrics emitted correctly

3. **Circuit Breaker Tests**
   - CLOSED → OPEN after 5 failures
   - OPEN → HALF_OPEN after 60s timeout
   - HALF_OPEN → CLOSED after 3 successes
   - HALF_OPEN → OPEN on any failure

4. **Integration Tests**
   - Embedding request with circuit breaker
   - Queue behavior when OPEN
   - Resume processing when CLOSED

5. **Performance Tests**
   - Pending count query < 5ms
   - Backpressure check < 10ms
   - Circuit breaker overhead < 1ms

**Test File**: `tests/k0/modules/consolidation/test_p08_coordination.py`
**Fixtures**: Mock P08 responses, configurable failure scenarios

---

### Epic 6.6: K0 Architecture Master Closure

#### Issue 6.6.1: Milestone 6 K0 Updates

**What to Cover**:

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated to reflect M6 completion
- [ ] **Part 3.1 (Module Registry)**: M18-M25 consolidation modules fully documented
- [ ] **Part 4.1 (Event Topics)**: P03 memory write events registered
- [ ] **Part 5.1 (Contract Registry)**: Memory writer module contracts added
- [ ] **Part 5.2 (Syscall Matrix)**: 8-layer truth write capabilities registered
- [ ] **Part 5.3 (Storage Tables)**: All 8 truth layer tables documented
- [ ] **Part 7.1 (ADR Index)**: ADR status for M6 decisions updated
- [ ] **Version Header**: Document version bumped to reflect M6 completion

**K0 File**: `k0/pipelines/k0_architecture_master.md`

---

## Milestone 7: Event Emission & P06 Integration (R8)

**Goal**: Implement event emission, gap detection, P06 active learning
**Gate**: GATE 3 (Implementation)

### Epic 7.1: Bus Event Emission

> **Dossier Reference**: Section 4.9.1 (R8 Event Emission), Section 9 (Integration Contracts)
> **K0 Reference**: [k0/bus/core.py](../../k0/bus/core.py) `BusMessage` and `BusDispatcher`
> **Test Reference**: [test_event_emitter.py](../../tests/k0/modules/core/test_event_emitter.py) for emission patterns

#### Issue 7.1.1: Implement p03.consolidation.complete.v1

**What to Cover**:

1. **Event Payload Schema** (per Dossier Section 9.3):
   - `cycle_id` (ULID): Consolidation cycle identifier
   - `tenant_id`, `space_id`: Isolation keys
   - `events_processed`: Total events consolidated this cycle
   - `decisions_summary`: Dict with counts per decision type (REINFORCE, EXTEND, CREATE, EVOLVE, PRUNE, CONTRADICT)
   - `phases_completed`: List of phase names (R0-R8)
   - `duration_seconds`: Total cycle execution time
   - `started_at`, `completed_at`: Unix epoch timestamps
   - `trace_id`: Cognitive trace ID for observability correlation

2. **Bus Integration** (per `k0/bus/core.py`):
   - Create `BusMessage(topic='p03.consolidation.complete.v1', payload=..., offset=..., trace_id=...)`
   - Include `space_id` for per-space ordering enforcement
   - Include `metadata` with `{'cycle_id': ..., 'phase': 'R8'}`

3. **Emission Timing**:
   - Emit AFTER all R7 writes committed to truth tables
   - Emit AFTER st_pipeline_offsets updated with cycle checkpoint
   - Single emit per cycle (aggregated summary, not per-event)

4. **Idempotency**:
   - Fingerprint = SHA256(cycle_id + tenant_id + space_id)
   - Reference `test_event_emitter.py` fingerprint uniqueness pattern (lines 266-283)

5. **Reference Patterns**:
   - Follow `outbox_emit_batch` syscall pattern from test_event_emitter.py
   - Batch this event with other R8 events for atomic emission

---

#### Issue 7.1.2: Implement p03.pattern.detected.v1

**What to Cover**:

1. **Event Payload Schema**:
   - `pattern_id` (ULID): Unique pattern identifier
   - `tenant_id`, `space_id`: Isolation keys
   - `cycle_id`: Which consolidation cycle detected this
   - `pattern_type`: Enum (BEHAVIORAL, TEMPORAL, PREFERENTIAL, PROCEDURAL)
   - `pattern_label`: Human-readable description
   - `source_cluster_id`: Episode cluster from R2 that produced this pattern
   - `source_event_count`: Number of episodes that support this pattern
   - `confidence_score`: Pattern confidence (0.0-1.0)
   - `temporal_span`: Dict with `start_epoch`, `end_epoch`, `recurrence_type`
   - `entities_involved`: List of entity_ids participating in pattern
   - `detected_at`: Unix epoch timestamp

2. **Emission Cardinality**:
   - Emit ONE event per newly detected pattern (not per-event)
   - R2 EpisodeClustering outputs episode_cluster_id → patterns extracted
   - Only emit for NEW patterns, not reinforced existing patterns

3. **Pattern Type Mapping** (per Dossier Section 4.5 R2):
   - BEHAVIORAL: Activity patterns (exercise routines, meal times)
   - TEMPORAL: Time-based recurrences (weekly calls, daily habits)
   - PREFERENTIAL: Preference patterns (food choices, activity preferences)
   - PROCEDURAL: Sequence patterns (morning routines, work habits)

4. **Reference**: test_event_emitter.py `test_batch_emission_single_syscall` for batching multiple pattern events

---

#### Issue 7.1.3: Implement p03.truth.*.v1 Events

**What to Cover**:

1. **Three Event Types** (per Dossier Section 4.9.1):

   **a) p03.truth.reinforced.v1**:
   - Emitted when REINFORCE decision boosts existing truth record
   - Payload: `truth_id`, `layer` (st_epi, st_sem, etc.), `confidence_before`, `confidence_after`, `observation_count`, `source_event_id`
   - Cardinality: One per REINFORCE decision

   **b) p03.truth.created.v1**:
   - Emitted when CREATE decision inserts new canonical truth
   - Payload: `truth_id`, `layer`, `truth_type` (episode, fact, procedure, etc.), `initial_confidence`, `source_event_ids`, `version` (always 1)
   - Cardinality: One per CREATE decision

   **c) p03.truth.evolved.v1**:
   - Emitted when EVOLVE decision supersedes existing truth with new version
   - Payload: `new_truth_id`, `supersedes_truth_id`, `layer`, `evolution_type` (SPLIT, MERGE, UPDATE), `version` (incremented), `reason`
   - Reference: Dossier Section 6.1.4 `evolve_truth_record` pattern

2. **Layer Mappings**:
   - `st_epi` → Episodic memories
   - `st_sem` → Semantic facts
   - `st_procedural` → Procedural sequences
   - `st_social` → Relationship records
   - `st_spatial` → Place associations
   - `st_anchors` → Bayesian preferences (Issue 7.3.4)
   - `st_kg_dom` → Entity records
   - `st_kg_edges` → Relationship edges

3. **Batch Emission**:
   - Collect all truth.* events during R7
   - Emit via single `outbox_emit_batch` syscall in R8
   - Maintain ordering: reinforced → created → evolved

---

#### Issue 7.1.4: Implement p03.memory.pruned.v1

**What to Cover**:

1. **Event Payload Schema**:
   - `pruned_truth_ids`: List of truth_ids that were archived/tombstoned
   - `tenant_id`, `space_id`: Isolation keys
   - `cycle_id`: Consolidation cycle that performed pruning
   - `prune_reason`: Enum (DECAY, DUPLICATE, SUPERSEDED, CONTRADICTION)
   - `archival_status`: Target status (ARCHIVED or TOMBSTONE)
   - `layer`: Which memory layer was pruned
   - `pruned_at`: Unix epoch timestamp
   - `total_pruned_count`: Aggregate count per prune_reason

2. **R3 Forgetting Integration**:
   - R3 (Forgetting Application) marks records for pruning
   - R7 writes archival_status updates
   - R8 emits p03.memory.pruned.v1 summarizing all prunes

3. **Prune Reason Mapping** (per Dossier Section 4.6 R3):
   - DECAY: `decay_factor < 0.1` threshold crossed
   - DUPLICATE: Near-duplicate detected (Hamming distance ≤ 3)
   - SUPERSEDED: EVOLVE decision replaced this version
   - CONTRADICTION: CONTRADICT decision invalidated this truth

4. **Cardinality**:
   - One event per (layer, prune_reason) combination to avoid event explosion
   - Include `pruned_truth_ids` list for detailed tracking

---

#### Issue 7.1.5: Implement p03.gap.detected.v1

**What to Cover**:

1. **Event Payload Schema** (per Dossier Section 9.3.1):

   ```yaml
   gap_id: ULID (unique gap identifier)
   tenant_id: string
   space_id: string
   actor_id: string (preferred actor to ask, if known)
   gap_type: enum [AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, MISSING_ATTRIBUTE, CONTRADICTION, CONCEPT_DRIFT, STRUCTURAL_HOLE, STALE_ANCHOR]
   importance_score: number (0.0-1.0)
   context:
     source_event_ids: array[string]
     conflicting_truths: array[{truth_id, layer, confidence}]
     question_template: string (suggested question phrasing)
   ttl_hours: integer (default 168 = 7 days)
   detected_at: integer (Unix epoch ms)
   ```

2. **P06 Active Learning Integration**:
   - This event is consumed by P06 Active Learning pipeline
   - P06 uses `question_template` to generate clarification prompts
   - P06 emits `p06.gap.resolved.v1` when user answers (Section 9.3.2)

3. **Dual Write Pattern**:
   - Step 1: Insert gap record into `st_learning_queue` (Issue 7.2.5)
   - Step 2: Emit `p03.gap.detected.v1` to bus for P06 subscription
   - Both writes in same transaction for consistency

4. **M25 GapDetector Integration** (Issue 7.2.1):
   - M25 outputs `List[GapRecord]` with max 50 gaps per cycle
   - Each GapRecord maps to one `p03.gap.detected.v1` event
   - Sort by `importance_score` DESC, emit top N

5. **Kafka Binding** (per Dossier):
   - Topic: `familyos.p03.gaps`
   - Partition key: `$.tenant_id`
   - Content-Type: `application/json`

---

### Epic 7.2: Gap Detection (P06 Integration)

> **Dossier Reference**: Section 5.2-5.5 (Gap Detection Algorithms), Section 7.4.8 (M25 GapDetector)
> **Schema Reference**: Dossier Section 6.11 (st_learning_queue)
> **P06 Contract**: Dossier Section 9.3 (P03 → P06 Active Learning)

#### Issue 7.2.1: Implement M25 GapDetector

**What to Cover**:

1. **Module Interface** (per Dossier Section 7.4.8):

   ```python
   class GapDetector:
       """M25 — Detects knowledge gaps for Active Learning (R8 lead)."""

       def __init__(self, config: GapConfig):
           self.thresholds = config.thresholds
           self.max_gaps_per_cycle = config.max_gaps  # Default: 50

       async def detect(
           self,
           reconciliation_results: List[ReconciliationResult]
       ) -> List[GapRecord]:
           """Analyze reconciliation results for knowledge gaps."""
   ```

2. **Gap Record Structure**:
   - `gap_id`: ULID (generated by M25)
   - `gap_type`: One of the 7 types from Dossier Section 5.2
   - `importance_score`: Computed priority (0.0-1.0)
   - `context`: Dict with source_event_ids, conflicting_truths, question_template
   - `entity_ids`: Affected entities (for AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE)
   - `layer`: Memory layer where gap was detected

3. **Processing Flow**:
   - Input: `List[ReconciliationResult]` from R7 TruthWriter
   - For each result, check: `has_ambiguous_entities`, `has_low_confidence_edges`, `has_contradictions`
   - Create typed gaps via helper methods: `_create_ambiguity_gaps()`, `_create_edge_gaps()`, `_create_contradiction_gaps()`
   - Sort by `importance_score` DESC, cap at `max_gaps_per_cycle`

4. **Configuration** (GapConfig):
   - `thresholds.confidence_floor`: Below this, edge is "low confidence" (default: 0.4)
   - `thresholds.contradiction_threshold`: Conflict detection threshold (default: 0.8)
   - `thresholds.ambiguity_similarity`: Entity ambiguity threshold (default: 0.85)
   - `max_gaps`: Max gaps per cycle (default: 50)

5. **Question Template Generation**:
   - AMBIGUOUS_ENTITY: "Did you mean {entity_a} or {entity_b}?"
   - LOW_CONFIDENCE_EDGE: "Are {entity_a} and {entity_b} {relation_type}?"
   - CONTRADICTION: "You mentioned {fact_a}, but earlier said {fact_b}. Which is correct?"

---

#### Issue 7.2.2: Implement Contradiction Detection

**What to Cover**:

1. **Algorithm** (per Dossier Section 5.5):
   - Compare new signal against existing canonical truths in same layer
   - Detect semantic contradictions using embedding similarity
   - Threshold: `similarity > 0.8` AND `polarity_opposite = true`

2. **Contradiction Types**:
   - **Temporal**: "I work at Google" vs "I work at Microsoft" (same time frame)
   - **Attribute**: "I love coffee" vs "I hate coffee"
   - **Relational**: "John is married to Jane" vs "John is single"
   - **Procedural**: "I take the bus to work" vs "I drive to work"

3. **Contradiction Record**:

   ```python
   ContradictionGap(
       gap_type='CONTRADICTION',
       importance_score=0.9,  # High priority for user resolution
       context={
           'conflicting_truths': [
               {'truth_id': existing.id, 'layer': 'st_sem', 'confidence': 0.8},
               {'truth_id': new.id, 'layer': 'st_sem', 'confidence': 0.7}
           ],
           'source_event_ids': [event_id_1, event_id_2],
           'question_template': 'You mentioned X, but earlier said Y. Which is correct?'
       }
   )
   ```

4. **Semantic Conflict Analysis**:
   - Fetch embedding for new signal from st_vec
   - Query existing truths in same layer with high similarity (>0.8)
   - Apply sentiment/polarity check to detect opposition
   - Generate contradiction gap if opposing polarity detected

5. **Decision Mapping**:
   - Contradiction detected → CONTRADICT decision in R7
   - R7 writes new truth with lower confidence + penalty
   - R8 emits `p03.gap.detected.v1` with type=CONTRADICTION

---

#### Issue 7.2.3: Implement Ambiguity Detection

**What to Cover**:

1. **Entity Ambiguity** (per Dossier Section 5.4):
   - When entity resolution produces multiple candidates with similar scores
   - Example: "John" could be "John Smith" (brother) or "John Doe" (colleague)
   - Threshold: Top 2 candidates within `0.15` confidence of each other

2. **Ambiguity Types**:
   - **AMBIGUOUS_ENTITY**: Multiple entity matches
   - **MISSING_ATTRIBUTE**: Entity exists but lacks key attributes
   - **STRUCTURAL_HOLE**: Disconnected subgraph in KG

3. **Detection Algorithm**:

   ```python
   def detect_ambiguity(entity_candidates: List[EntityMatch]) -> Optional[AmbiguityGap]:
       if len(entity_candidates) < 2:
           return None
       top, second = entity_candidates[0], entity_candidates[1]
       if top.confidence - second.confidence < 0.15:
           return AmbiguityGap(
               gap_type='AMBIGUOUS_ENTITY',
               importance_score=0.7 + (0.3 * top.mention_frequency),
               context={
                   'candidates': [c.entity_id for c in entity_candidates[:3]],
                   'mention_text': entity_candidates[0].mention_text,
                   'question_template': f"Did you mean {top.label} or {second.label}?"
               }
           )
   ```

4. **Importance Scoring**:
   - Base score: 0.5 for any ambiguity
   - Boost +0.2 if entity appears frequently in recent events
   - Boost +0.1 if entity is central to a pattern (high degree in KG)
   - Cap at 1.0

5. **LOW_CONFIDENCE_EDGE Detection**:
   - KG edges with `confidence_score < 0.4` after R4
   - Generated from single observation (co_occurrence_count = 1)
   - Question: "Are {source} and {target} {relation_type}?"

---

#### Issue 7.2.4: Implement Entropy Scanning

**What to Cover**:

1. **Proactive Gap Detection** (per Dossier Section 5.3):
   - Not triggered by specific events, but by periodic analysis
   - Identify areas of high uncertainty in memory layers
   - Run during R8 after all decisions are made

2. **Entropy Metrics**:
   - **Confidence Entropy**: Distribution of confidence scores in a layer
   - **Edge Density Entropy**: Unevenness in KG connectivity
   - **Temporal Entropy**: Gaps in temporal coverage

3. **STALE_ANCHOR Detection**:
   - Bayesian anchors in st_anchors with `drift_detected = true`
   - Preferences that haven't been reinforced in `stale_threshold_days` (default: 90)
   - Formula: `staleness = days_since_last_observation / decay_half_life`

4. **CONCEPT_DRIFT Detection**:
   - Track anchor values over time (alpha, beta distributions)
   - Detect significant shifts in preference patterns
   - Threshold: `|current_confidence - historical_mean| > 2 * std_dev`

5. **Gap Generation**:

   ```python
   def scan_entropy(layer_stats: LayerStatistics) -> List[GapRecord]:
       gaps = []

       # Stale anchors
       for anchor in layer_stats.stale_anchors:
           gaps.append(GapRecord(
               gap_type='STALE_ANCHOR',
               importance_score=0.5,
               context={'anchor_id': anchor.id, 'days_stale': anchor.days_stale}
           ))

       # Concept drift
       for drift in layer_stats.detected_drifts:
           gaps.append(GapRecord(
               gap_type='CONCEPT_DRIFT',
               importance_score=0.8,
               context={'anchor_id': drift.anchor_id, 'old_value': drift.old, 'new_value': drift.new}
           ))

       return gaps
   ```

---

#### Issue 7.2.5: Implement st_learning_queue Writer

**What to Cover**:

1. **Schema Reference** (Dossier Section 6.11):

   ```sql
   CREATE TABLE st_learning_queue (
       gap_id TEXT PRIMARY KEY,           -- ULID
       tenant_id TEXT NOT NULL,
       space_id TEXT NOT NULL,
       actor_id TEXT,                     -- Preferred responder
       gap_type TEXT NOT NULL CHECK(gap_type IN (
           'AMBIGUOUS_ENTITY', 'LOW_CONFIDENCE_EDGE', 'MISSING_ATTRIBUTE',
           'CONTRADICTION', 'CONCEPT_DRIFT', 'STRUCTURAL_HOLE', 'STALE_ANCHOR'
       )),
       importance_score REAL NOT NULL,
       context_json TEXT NOT NULL,        -- JSON blob with gap-specific data
       status TEXT DEFAULT 'PENDING' CHECK(status IN (
           'PENDING', 'ASKED', 'ANSWERED', 'DISMISSED', 'EXPIRED', 'SUPERSEDED'
       )),
       ttl_expires_at INTEGER NOT NULL,   -- Unix epoch when gap expires
       cycle_id TEXT NOT NULL,            -- Which P03 cycle detected this
       created_at INTEGER NOT NULL,
       updated_at INTEGER NOT NULL
   );
   ```

2. **Write Flow**:
   - Input: `List[GapRecord]` from M25 GapDetector
   - Transform each GapRecord to st_learning_queue row
   - Calculate `ttl_expires_at` from `ttl_hours` (default 168h = 7 days)
   - Insert via UoW transaction (same as R7 truth writes)

3. **Outbox Pattern**:
   - Follow same pattern as M6 memory layer writers
   - Insert via `_write_via_outbox()` for durability
   - Emit `p03.gap.detected.v1` events after outbox write

4. **Status Lifecycle**:
   - `PENDING` → Initial state (set by P03)
   - `ASKED` → P06 has surfaced question to user
   - `ANSWERED` → User provided response
   - `DISMISSED` → User declined to answer
   - `EXPIRED` → TTL exceeded without resolution
   - `SUPERSEDED` → New gap replaced this one

5. **Deduplication**:
   - Check for existing PENDING gaps with same context
   - If duplicate: update `importance_score` if higher, skip insert
   - Key: (tenant_id, space_id, gap_type, entity_ids hash)

---

### Epic 7.3: Bayesian Anchor Updates

> **Dossier Reference**: Section 5.4 (Anchor Evolution), Section 6.12 (st_anchors schema)
> **Brain Analog**: Hippocampal-prefrontal preference encoding with Beta priors

#### Issue 7.3.1: Implement Anchor Updater

**What to Cover**:

1. **Beta Distribution Updates** (per Dossier Section 5.4.2):
   - st_anchors stores Bayesian preference beliefs as Beta(α, β) distributions
   - Confidence = α / (α + β)
   - Uncertainty = 1 / (α + β + 1)
   - REINFORCE: α++ for positive evidence, β++ for negative evidence

2. **Update Algorithm**:

   ```python
   class AnchorUpdater:
       """Update Bayesian anchors based on consolidation evidence."""

       async def update(
           self,
           anchor_id: str,
           evidence_type: Literal['POSITIVE', 'NEGATIVE'],
           weight: float = 1.0
       ) -> AnchorUpdateResult:
           """
           Update anchor's Beta distribution based on evidence.

           POSITIVE evidence: α += weight
           NEGATIVE evidence: β += weight
           """
           anchor = await self._fetch_anchor(anchor_id)

           if evidence_type == 'POSITIVE':
               new_alpha = anchor.alpha + weight
               new_beta = anchor.beta
           else:
               new_alpha = anchor.alpha
               new_beta = anchor.beta + weight

           new_confidence = new_alpha / (new_alpha + new_beta)
           old_confidence = anchor.alpha / (anchor.alpha + anchor.beta)

           return AnchorUpdateResult(
               anchor_id=anchor_id,
               alpha=new_alpha,
               beta=new_beta,
               confidence_before=old_confidence,
               confidence_after=new_confidence,
               drift_detected=abs(new_confidence - old_confidence) > 0.1
           )
   ```

3. **Evidence Weight Calculation**:
   - Base weight: 1.0 for normal observation
   - Explicit statement: 2.0 ("I love X" = stronger evidence)
   - Behavioral evidence: 0.5 (action implies preference)
   - Recency boost: weight * (1 + recency_factor) where recency_factor decays

4. **Anchor Categories**:
   - FOOD: Dietary preferences
   - ACTIVITY: Exercise, hobbies, leisure
   - SOCIAL: Communication preferences, social settings
   - TEMPORAL: Time-of-day preferences, scheduling
   - SPATIAL: Location preferences

5. **Transaction Safety**:
   - Read-modify-write must be atomic
   - Use optimistic locking with version column
   - Retry on conflict up to 3 times

---

#### Issue 7.3.2: Implement Anchor Extractors

**What to Cover**:

1. **Preference Extraction from Events**:
   - Parse st_hipp_events for preference signals during R1/R2
   - Extract explicit preferences: "I prefer X", "I love Y", "I don't like Z"
   - Extract implicit preferences: Repeated behaviors, consistent choices

2. **Extractor Interface**:

   ```python
   class PreferenceExtractor:
       """Extract preference signals from hippocampus events."""

       def extract(self, event: HippEvent) -> List[PreferenceSignal]:
           signals = []

           # Explicit preferences from text
           signals.extend(self._extract_explicit(event.text_normalized))

           # Implicit from activity patterns
           signals.extend(self._extract_implicit(event))

           return signals

       def _extract_explicit(self, text: str) -> List[PreferenceSignal]:
           """NLP extraction of preference statements."""
           # Use patterns: "I {love|like|prefer|enjoy|hate|dislike} {entity}"
           # Return PreferenceSignal with polarity and confidence
           ...

       def _extract_implicit(self, event: HippEvent) -> List[PreferenceSignal]:
           """Behavioral pattern extraction."""
           # Activity repetition = positive preference
           # Location visits = spatial preference
           # Time patterns = temporal preference
           ...
   ```

3. **PreferenceSignal Structure**:
   - `anchor_category`: FOOD, ACTIVITY, SOCIAL, TEMPORAL, SPATIAL
   - `anchor_key`: Specific preference key (e.g., "food:coffee", "activity:yoga")
   - `polarity`: POSITIVE or NEGATIVE
   - `confidence`: Extraction confidence (0.0-1.0)
   - `source_event_id`: Origin event
   - `extraction_method`: EXPLICIT or IMPLICIT

4. **Anchor Key Generation**:
   - Normalize entity to canonical form via st_kg_dom lookup
   - Key format: `{category}:{normalized_entity}`
   - Example: "food:coffee", "activity:morning_yoga", "social:family_dinner"

5. **Aggregation Strategy**:
   - Multiple signals for same anchor in same cycle → aggregate
   - Positive signals: Sum weights for α update
   - Negative signals: Sum weights for β update

---

#### Issue 7.3.3: Implement Drift Detection

**What to Cover**:

1. **Preference Drift Definition** (per Dossier Section 5.4.4):
   - Significant change in anchor confidence over time window
   - Threshold: `|current_confidence - 30_day_mean| > 2 * std_dev`
   - Triggers CONCEPT_DRIFT gap type

2. **Detection Algorithm**:

   ```python
   class DriftDetector:
       """Detect preference drift in Bayesian anchors."""

       def __init__(self, window_days: int = 30, threshold_std: float = 2.0):
           self.window_days = window_days
           self.threshold_std = threshold_std

       async def detect(self, anchor: AnchorRecord) -> Optional[DriftRecord]:
           # Fetch historical confidence values from last N days
           history = await self._fetch_confidence_history(anchor.anchor_id)

           if len(history) < 5:  # Need minimum samples
               return None

           mean_conf = statistics.mean(history)
           std_conf = statistics.stdev(history)

           current_conf = anchor.alpha / (anchor.alpha + anchor.beta)

           if abs(current_conf - mean_conf) > self.threshold_std * std_conf:
               return DriftRecord(
                   anchor_id=anchor.anchor_id,
                   drift_magnitude=abs(current_conf - mean_conf),
                   direction='INCREASING' if current_conf > mean_conf else 'DECREASING',
                   historical_mean=mean_conf,
                   current_confidence=current_conf
               )

           return None
   ```

3. **Drift Actions**:
   - Mark anchor with `drift_detected = true` in st_anchors
   - Generate CONCEPT_DRIFT gap for user confirmation
   - Question template: "Your preference for X seems to have changed. Is that right?"

4. **History Tracking**:
   - st_anchors tracks `confidence` (computed), not raw history
   - May need st_anchor_history table for detailed drift analysis
   - Alternative: Use confidence + observation_count + timestamps

5. **Drift Severity Levels**:
   - MINOR: 1-2 std_dev deviation (log only)
   - MODERATE: 2-3 std_dev (generate gap with low priority)
   - MAJOR: >3 std_dev (generate gap with high priority)

---

#### Issue 7.3.4: Implement st_anchors Writer

**What to Cover**:

1. **Schema Reference** (Dossier Section 6.12):

   ```sql
   CREATE TABLE st_anchors (
       anchor_id TEXT PRIMARY KEY,
       tenant_id TEXT NOT NULL,
       space_id TEXT NOT NULL,
       actor_id TEXT NOT NULL,            -- Whose preference

       -- Anchor Identity
       anchor_category TEXT NOT NULL CHECK(anchor_category IN (
           'FOOD', 'ACTIVITY', 'SOCIAL', 'TEMPORAL', 'SPATIAL'
       )),
       anchor_key TEXT NOT NULL,          -- e.g., "food:coffee"

       -- Bayesian Belief (Beta distribution)
       alpha REAL NOT NULL DEFAULT 1.0,   -- Prior + positive evidence
       beta REAL NOT NULL DEFAULT 1.0,    -- Prior + negative evidence

       -- Computed Fields (denormalized for query performance)
       confidence REAL GENERATED ALWAYS AS (alpha / (alpha + beta)) STORED,
       uncertainty REAL GENERATED ALWAYS AS (1.0 / (alpha + beta + 1)) STORED,

       -- Drift Detection
       drift_detected BOOLEAN DEFAULT FALSE,
       last_drift_at INTEGER,

       -- Evidence Tracking
       observation_count INTEGER DEFAULT 0,
       last_observed_at INTEGER,
       source_episodes_json TEXT,         -- Recent supporting events (capped)

       -- Versioning
       version INTEGER NOT NULL DEFAULT 1,
       supersedes_id TEXT,
       is_canonical BOOLEAN DEFAULT TRUE,

       -- Lifecycle
       archival_status TEXT DEFAULT 'ACTIVE',
       decay_factor REAL DEFAULT 1.0,

       -- Timestamps
       created_at INTEGER NOT NULL,
       updated_at INTEGER NOT NULL,

       UNIQUE(tenant_id, space_id, actor_id, anchor_key, is_canonical)
   );
   ```

2. **Write Operations**:

   **a) Create new anchor** (first observation):
   - alpha = 1.0 + weight (positive) OR alpha = 1.0
   - beta = 1.0 + weight (negative) OR beta = 1.0
   - version = 1, is_canonical = true

   **b) Update existing anchor** (REINFORCE):
   - In-place UPDATE for alpha/beta increments
   - Increment observation_count
   - Update last_observed_at
   - Reset decay_factor to 1.0

   **c) Evolve anchor** (EVOLVE for drift):
   - Mark existing as is_canonical = false
   - Create new version with supersedes_id
   - Reset alpha/beta to new baseline

3. **Outbox Integration**:
   - Write via `_write_via_outbox()` pattern
   - Include in same UoW transaction as other R7 writes
   - Emit `p03.truth.reinforced.v1` with layer='st_anchors' on update

4. **Prior Selection**:
   - Uninformative prior: Alpha=1, Beta=1 (uniform)
   - Jeffreys prior: Alpha=0.5, Beta=0.5 (alternative)
   - Configurable via P03_ANCHOR_PRIOR setting

5. **Index Strategy**:

   ```sql
   CREATE INDEX idx_anchors_lookup ON st_anchors(tenant_id, space_id, actor_id, anchor_key)
       WHERE is_canonical = TRUE AND archival_status = 'ACTIVE';
   CREATE INDEX idx_anchors_drift ON st_anchors(drift_detected, last_observed_at)
       WHERE drift_detected = TRUE;
   ```

---

### Epic 7.4: Offset & Metrics

> **Dossier Reference**: Section 6.14 (st_pipeline_offsets), Section 8 (Observability & Metrics)
> **K0 Reference**: k0/obs/ for telemetry patterns, k0/scheduler/ for checkpointing

#### Issue 7.4.1: Implement Offset Tracking

**What to Cover**:

1. **Schema Reference** (Dossier Section 6.14):

   ```sql
   -- Primary offset tracking
   CREATE TABLE st_pipeline_offsets (
       pipeline_id TEXT NOT NULL,
       tenant_id TEXT NOT NULL,
       space_id TEXT NOT NULL,
       last_processed_event_id TEXT NOT NULL,  -- ULID of last processed event
       last_processed_wal_pos INTEGER NOT NULL, -- WAL position for ordering
       last_cycle_id TEXT,                     -- Most recent cycle ID
       checkpoint_at INTEGER NOT NULL,         -- When checkpoint was written
       PRIMARY KEY (pipeline_id, tenant_id, space_id)
   );

   -- Cycle status tracking
   CREATE TABLE st_pipeline_status (
       cycle_id TEXT PRIMARY KEY,
       pipeline_id TEXT NOT NULL,
       tenant_id TEXT NOT NULL,
       space_id TEXT NOT NULL,
       status TEXT NOT NULL CHECK(status IN (
           'STARTED', 'R0', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8',
           'COMPLETED', 'FAILED', 'ABORTED'
       )),
       started_at INTEGER NOT NULL,
       completed_at INTEGER,
       error_message TEXT,
       events_processed INTEGER,
       decisions_json TEXT                     -- Summary of decisions made
   );

   -- High-water marks for batch processing
   CREATE TABLE st_pipeline_watermarks (
       pipeline_id TEXT NOT NULL,
       tenant_id TEXT NOT NULL,
       space_id TEXT NOT NULL,
       low_watermark INTEGER NOT NULL,        -- Oldest unprocessed wal_pos
       high_watermark INTEGER NOT NULL,       -- Newest available wal_pos
       pending_count INTEGER NOT NULL,        -- Events in range
       updated_at INTEGER NOT NULL,
       PRIMARY KEY (pipeline_id, tenant_id, space_id)
   );
   ```

2. **Resume Capability**:
   - On startup, query `st_pipeline_offsets` for last checkpoint
   - Resume R1 batch selection from `last_processed_wal_pos + 1`
   - Handle partial cycles: check `st_pipeline_status` for STARTED/R* status
   - If partial cycle found, either resume or abort based on TTL

3. **Checkpoint Strategy**:
   - Checkpoint at END of each successful cycle (R8)
   - Include: `last_processed_event_id`, `last_processed_wal_pos`, `cycle_id`
   - Checkpoint is atomic with final event emission

4. **Write Implementation**:

   ```python
   class OffsetManager:
       """Manage P03 pipeline checkpoints for resume capability."""

       async def update_checkpoint(
           self,
           cycle_id: str,
           tenant_id: str,
           space_id: str,
           last_event_id: str,
           last_wal_pos: int
       ) -> None:
           """Update checkpoint after successful cycle completion."""
           await self.db.execute(
               """
               INSERT INTO st_pipeline_offsets
                   (pipeline_id, tenant_id, space_id, last_processed_event_id,
                    last_processed_wal_pos, last_cycle_id, checkpoint_at)
               VALUES ('P03', :tenant_id, :space_id, :event_id, :wal_pos, :cycle_id, :now)
               ON CONFLICT (pipeline_id, tenant_id, space_id)
               DO UPDATE SET
                   last_processed_event_id = :event_id,
                   last_processed_wal_pos = :wal_pos,
                   last_cycle_id = :cycle_id,
                   checkpoint_at = :now
               """,
               {
                   'tenant_id': tenant_id,
                   'space_id': space_id,
                   'event_id': last_event_id,
                   'wal_pos': last_wal_pos,
                   'cycle_id': cycle_id,
                   'now': int(time.time())
               }
           )

       async def get_resume_point(
           self,
           tenant_id: str,
           space_id: str
       ) -> Optional[int]:
           """Get WAL position to resume from."""
           result = await self.db.fetch_one(
               """
               SELECT last_processed_wal_pos FROM st_pipeline_offsets
               WHERE pipeline_id = 'P03' AND tenant_id = :tenant_id AND space_id = :space_id
               """,
               {'tenant_id': tenant_id, 'space_id': space_id}
           )
           return result['last_processed_wal_pos'] if result else None
   ```

5. **Phase Status Updates**:
   - Update `st_pipeline_status` on each phase transition
   - Status progression: STARTED → R0 → R1 → ... → R8 → COMPLETED
   - On error: FAILED with error_message
   - On timeout/cancel: ABORTED

---

#### Issue 7.4.2: Implement Prometheus Metrics

**What to Cover**:

1. **Metric Definitions** (per Dossier Section 8.2):

   ```python
   from prometheus_client import Counter, Histogram, Gauge

   # Cycle execution metrics
   p03_cycle_total = Counter(
       'p03_cycle_total',
       'Total consolidation cycles executed',
       ['tenant_id', 'status']  # status: success, failure, partial, aborted
   )

   p03_cycle_duration_seconds = Histogram(
       'p03_cycle_duration_seconds',
       'Consolidation cycle duration',
       ['tenant_id', 'phase'],
       buckets=[1, 5, 10, 30, 60, 120, 300, 600]
   )

   p03_events_processed_total = Counter(
       'p03_events_processed_total',
       'Total events processed during consolidation',
       ['tenant_id', 'space_id', 'outcome']  # outcome: consolidated, duplicate, pruned
   )

   p03_pending_events = Gauge(
       'p03_pending_events',
       'Number of events pending consolidation',
       ['tenant_id', 'space_id']
   )

   # Phase timing (per Dossier Section 8.2.1)
   p03_phase_duration_seconds = Histogram(
       'p03_phase_duration_seconds',
       'Duration of each consolidation phase',
       ['tenant_id', 'phase'],  # R0, R1, R2, ..., R8
       buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120]
   )

   # Decision metrics (per Section 8.2.2)
   p03_decisions_total = Counter(
       'p03_decisions_total',
       'Reconciliation decisions by type',
       ['tenant_id', 'decision_type', 'target_layer']
   )

   # Gap detection metrics (per Section 8.2.3)
   p03_gaps_detected_total = Counter(
       'p03_gaps_detected_total',
       'Knowledge gaps detected during consolidation',
       ['tenant_id', 'gap_type']
   )

   p03_gaps_pending = Gauge(
       'p03_gaps_pending',
       'Gaps pending resolution in st_learning_queue',
       ['tenant_id', 'gap_type', 'status']
   )
   ```

2. **Instrumentation Points**:
   - **Cycle start**: Increment `p03_cycle_total{status="started"}`
   - **Phase entry/exit**: Record `p03_phase_duration_seconds`
   - **Each decision**: Increment `p03_decisions_total{decision_type=..., target_layer=...}`
   - **Cycle end**: Increment `p03_cycle_total{status="success"|"failure"}`
   - **Gap detection**: Increment `p03_gaps_detected_total{gap_type=...}`

3. **K0 Telemetry Integration**:
   - Reference: k0/obs/ telemetry patterns
   - Use k0 MetricsRegistry for Prometheus exposition
   - Labels must include `tenant_id` for multi-tenant isolation
   - Space-level metrics where cardinality is acceptable

4. **Performance Targets** (per Dossier Section 10.5):
   - Monitor: `p03_cycle_duration_seconds` P95 < 5 minutes
   - Monitor: `p03_events_processed_total` rate > 1000/hour
   - Alert: `p03_pending_events` > 10000 for 30m
   - Alert: `p03_cycle_total{status="failure"}` rate > 10% for 15m

5. **Cardinality Management**:
   - Avoid high-cardinality labels (event_id, cycle_id)
   - Use `tenant_id` but consider bucketing for >100 tenants
   - Gap type enum is bounded (7 types) - safe for label

---

#### Issue 7.4.3: Implement Structured Logging

**What to Cover**:

1. **Log Schema** (per Dossier Section 8.4):

   ```python
   from structlog import get_logger

   logger = get_logger()

   # Standard log fields for all P03 logs
   P03_LOG_SCHEMA = {
       # Required fields
       "timestamp": "ISO 8601 timestamp",
       "level": "DEBUG | INFO | WARN | ERROR",
       "message": "Human-readable message",
       "correlation_id": "Trace correlation ID",

       # P03-specific fields
       "cycle_id": "P03 cycle identifier (ULID)",
       "phase": "R0 | R1 | R2 | ... | R8",
       "tenant_id": "Tenant ID",
       "space_id": "Space ID",

       # Contextual fields (optional)
       "event_id": "Source event ID if applicable",
       "decision_type": "REINFORCE | EXTEND | CREATE | EVOLVE | PRUNE | CONTRADICT",
       "target_layer": "st_epi | st_sem | st_procedural | ...",
       "duration_ms": "Operation duration",
       "error_code": "Error code if error",
       "error_message": "Error message if error",
   }
   ```

2. **Log Examples by Phase** (per Dossier Section 8.4.2):

   ```python
   # R0 - Cycle start
   logger.info(
       "consolidation_cycle_started",
       cycle_id="01HXYZ...",
       tenant_id="tenant_123",
       space_id="space_456",
       phase="R0",
       pending_events=1500
   )

   # R7 - Reconciliation decision
   logger.debug(
       "reconciliation_decision",
       cycle_id="01HXYZ...",
       phase="R7",
       event_id="evt_789",
       decision_type="REINFORCE",
       target_layer="st_sem",
       similarity_score=0.92,
       confidence_before=0.75,
       confidence_after=0.80
   )

   # R7 - Error
   logger.error(
       "truth_write_failed",
       cycle_id="01HXYZ...",
       phase="R7",
       target_layer="st_epi",
       error_code="CONSTRAINT_VIOLATION",
       error_message="Unique constraint violated on episode_id",
       affected_events=["evt_001", "evt_002"]
   )

   # R8 - Completion
   logger.info(
       "consolidation_cycle_completed",
       cycle_id="01HXYZ...",
       phase="R8",
       duration_ms=45230,
       events_processed=1500,
       decisions={"REINFORCE": 1200, "CREATE": 250, "EVOLVE": 40, "PRUNE": 10}
   )
   ```

3. **Log Level Guidelines** (per Dossier Table 8.4.2):
   - **INFO**: Cycle start/end, phase transitions, aggregate counts
   - **DEBUG**: Per-event decisions, per-cluster details
   - **WARN**: Lock contention, retry scenarios, low-importance batches
   - **ERROR**: Transaction failures, constraint violations, DLQ routing

4. **Trace Context Propagation**:
   - Include `cognitive_trace_id` from source events
   - Propagate via structlog context
   - Enable cross-pipeline correlation (P02 → P03 → P06)

5. **Sensitive Data Handling**:
   - Never log raw event `text` content
   - Mask entity names in DEBUG logs if RED band
   - Log event_ids (safe) not event content

---

### Epic 7.5: R8 Unit Tests

> **Test Reference**: [test_event_emitter.py](../../tests/k0/modules/core/test_event_emitter.py) for emission patterns
> **Dossier Reference**: Section 10.3 (Test Categories)
> **Coverage Target**: 90%+ for all R8 modules

#### Issue 7.5.1: Event Emission Tests

**What to Cover**:

1. **Test Categories** (following test_event_emitter.py structure):

   **a) Schema Validation Tests** (per lines 1-150 pattern):
   - `test_consolidation_complete_event_structure`: Verify payload schema
   - `test_pattern_detected_event_structure`: Pattern fields present
   - `test_truth_reinforced_event_structure`: Confidence before/after
   - `test_truth_created_event_structure`: Version=1, initial fields
   - `test_truth_evolved_event_structure`: supersedes_id, version++
   - `test_memory_pruned_event_structure`: prune_reason, archival_status
   - `test_gap_detected_event_structure`: gap_type, context, ttl_hours

   **b) Happy Path Tests** (per lines 250-320 pattern):
   - `test_successful_batch_emission`: All events emitted via single syscall
   - `test_idempotency_fingerprints_unique`: Each event has unique fingerprint
   - `test_same_cycle_produces_same_fingerprints`: Idempotency validation
   - `test_latency_tracking`: latency_ms recorded in result

   **c) Error Handling Tests** (per lines 350-420 pattern):
   - `test_bus_unavailable_graceful_handling`: Bus timeout → retry or DLQ
   - `test_partial_emission_rollback`: If batch fails, no partial state
   - `test_syscall_failure_propagates`: Errors bubble to cycle failure

2. **Mock Setup** (following test_event_emitter.py MockContext):

   ```python
   @pytest.fixture
   def mock_context():
       context = MagicMock()
       context.syscalls.outbox_emit_batch = AsyncMock(return_value={
           "events_inserted": 5,
           "batch_size": 5,
           "operation": "outbox_emit_batch",
           "status": "success"
       })
       return context

   @pytest.fixture
   def sample_cycle_result():
       return CycleResult(
           cycle_id="01HXYZ...",
           tenant_id="tenant_123",
           space_id="space_456",
           events_processed=100,
           decisions={
               'REINFORCE': 80,
               'CREATE': 15,
               'EVOLVE': 3,
               'PRUNE': 2
           },
           patterns_detected=[...],
           gaps_detected=[...],
           duration_seconds=45.2
       )
   ```

3. **Fingerprint Tests**:
   - Fingerprint = SHA256(topic + cycle_id + tenant_id + space_id + payload_hash)
   - Test: Same inputs → same fingerprint
   - Test: Different topic → different fingerprint
   - Reference: test_event_emitter.py lines 266-320

4. **Bus Integration Tests**:
   - Test: BusMessage creation with correct topic, payload, metadata
   - Test: space_id included for per-space ordering
   - Test: trace_id propagated from cycle context

---

#### Issue 7.5.2: Gap Detection Tests

**What to Cover**:

1. **M25 GapDetector Unit Tests**:

   ```python
   class TestGapDetector:
       """Unit tests for M25 GapDetector module."""

       def test_detect_ambiguous_entities(self):
           """Ambiguous entity candidates produce AMBIGUOUS_ENTITY gap."""
           results = [ReconciliationResult(
               has_ambiguous_entities=True,
               entity_candidates=[
                   EntityMatch(entity_id='e1', confidence=0.85),
                   EntityMatch(entity_id='e2', confidence=0.82)  # Within 0.15
               ]
           )]
           detector = GapDetector(GapConfig(max_gaps=50))
           gaps = await detector.detect(results)

           assert len(gaps) == 1
           assert gaps[0].gap_type == 'AMBIGUOUS_ENTITY'
           assert 'e1' in gaps[0].context['candidates']

       def test_detect_low_confidence_edges(self):
           """Edges below threshold produce LOW_CONFIDENCE_EDGE gap."""
           results = [ReconciliationResult(
               has_low_confidence_edges=True,
               low_edges=[Edge(source='e1', target='e2', confidence=0.3)]
           )]
           gaps = await detector.detect(results)
           assert gaps[0].gap_type == 'LOW_CONFIDENCE_EDGE'

       def test_detect_contradictions(self):
           """Semantic conflicts produce CONTRADICTION gap."""
           results = [ReconciliationResult(
               has_contradictions=True,
               contradicting_truths=[truth1, truth2]
           )]
           gaps = await detector.detect(results)
           assert gaps[0].gap_type == 'CONTRADICTION'
           assert gaps[0].importance_score >= 0.9

       def test_max_gaps_cap(self):
           """Gaps capped at max_gaps_per_cycle."""
           # Create 100 gap-producing results
           results = [make_ambiguous_result() for _ in range(100)]
           detector = GapDetector(GapConfig(max_gaps=50))
           gaps = await detector.detect(results)
           assert len(gaps) == 50

       def test_gaps_sorted_by_importance(self):
           """Gaps returned in importance_score DESC order."""
           results = [...]  # Mixed importance
           gaps = await detector.detect(results)
           for i in range(len(gaps) - 1):
               assert gaps[i].importance_score >= gaps[i+1].importance_score
   ```

2. **Contradiction Detection Tests**:
   - `test_temporal_contradiction`: Same entity, conflicting facts, overlapping time
   - `test_attribute_contradiction`: Opposite polarity (love vs hate)
   - `test_no_contradiction_different_time`: Old fact vs new fact = EVOLVE, not CONTRADICT
   - `test_question_template_generation`: Template correctly interpolates entities

3. **st_learning_queue Writer Tests**:
   - `test_gap_written_to_queue`: GapRecord → st_learning_queue row
   - `test_ttl_calculated_correctly`: ttl_hours → ttl_expires_at Unix epoch
   - `test_duplicate_gap_deduplication`: Same context → update, not insert
   - `test_status_defaults_to_pending`: New gaps have status='PENDING'

---

#### Issue 7.5.3: Anchor Update Tests

**What to Cover**:

1. **AnchorUpdater Unit Tests**:

   ```python
   class TestAnchorUpdater:
       """Unit tests for Bayesian anchor updates."""

       def test_positive_evidence_increases_alpha(self):
           """POSITIVE evidence increments alpha."""
           anchor = Anchor(alpha=5.0, beta=3.0)  # confidence = 0.625
           result = await updater.update(anchor.id, 'POSITIVE', weight=1.0)
           assert result.alpha == 6.0
           assert result.beta == 3.0
           assert result.confidence_after > 0.625

       def test_negative_evidence_increases_beta(self):
           """NEGATIVE evidence increments beta."""
           anchor = Anchor(alpha=5.0, beta=3.0)
           result = await updater.update(anchor.id, 'NEGATIVE', weight=1.0)
           assert result.alpha == 5.0
           assert result.beta == 4.0
           assert result.confidence_after < 0.625

       def test_weighted_evidence(self):
           """Weight parameter scales update magnitude."""
           anchor = Anchor(alpha=5.0, beta=3.0)
           result = await updater.update(anchor.id, 'POSITIVE', weight=2.0)
           assert result.alpha == 7.0  # +2 instead of +1

       def test_drift_detection_triggered(self):
           """Large confidence change triggers drift_detected."""
           anchor = Anchor(alpha=1.0, beta=9.0)  # confidence = 0.1
           result = await updater.update(anchor.id, 'POSITIVE', weight=5.0)
           # New: alpha=6, beta=9, confidence=0.4
           assert result.drift_detected == True  # 0.4 - 0.1 > 0.1 threshold
   ```

2. **Preference Extractor Tests**:
   - `test_explicit_positive_extraction`: "I love coffee" → POSITIVE signal
   - `test_explicit_negative_extraction`: "I hate mornings" → NEGATIVE signal
   - `test_implicit_behavioral_extraction`: Repeated yoga attendance → implicit preference
   - `test_anchor_key_generation`: Entity normalized to canonical key

3. **Drift Detection Tests**:
   - `test_minor_drift_not_flagged`: 1 std_dev change = no gap
   - `test_major_drift_creates_gap`: >2 std_dev change = CONCEPT_DRIFT gap
   - `test_stale_anchor_detection`: 90+ days since last observation = STALE_ANCHOR gap
   - `test_insufficient_history_skips`: <5 data points = no drift analysis

4. **st_anchors Writer Tests**:
   - `test_new_anchor_creation`: First observation creates anchor with priors
   - `test_anchor_reinforce_in_place`: REINFORCE updates alpha/beta in place
   - `test_anchor_evolve_creates_version`: EVOLVE marks old canonical=false, creates new
   - `test_generated_columns_computed`: confidence, uncertainty correctly computed

---

#### Issue 7.5.4: Offset Tracking Tests

**What to Cover**:

1. **OffsetManager Unit Tests**:

   ```python
   class TestOffsetManager:
       """Unit tests for checkpoint and resume capability."""

       async def test_checkpoint_written_after_cycle(self):
           """Successful cycle writes checkpoint to st_pipeline_offsets."""
           await manager.update_checkpoint(
               cycle_id='cycle_001',
               tenant_id='t1',
               space_id='s1',
               last_event_id='evt_100',
               last_wal_pos=12345
           )
           result = await db.fetch_one(
               "SELECT * FROM st_pipeline_offsets WHERE pipeline_id='P03'"
           )
           assert result['last_processed_wal_pos'] == 12345
           assert result['last_cycle_id'] == 'cycle_001'

       async def test_resume_from_checkpoint(self):
           """Resume point returns last processed WAL position."""
           # Setup: checkpoint exists
           await manager.update_checkpoint(...)

           resume_pos = await manager.get_resume_point('t1', 's1')
           assert resume_pos == 12345

       async def test_resume_returns_none_if_no_checkpoint(self):
           """New tenant/space returns None for resume."""
           resume_pos = await manager.get_resume_point('new_tenant', 'new_space')
           assert resume_pos is None

       async def test_upsert_updates_existing_checkpoint(self):
           """Second cycle updates existing checkpoint, not inserts."""
           await manager.update_checkpoint(cycle_id='c1', ..., last_wal_pos=100)
           await manager.update_checkpoint(cycle_id='c2', ..., last_wal_pos=200)

           count = await db.fetch_one(
               "SELECT COUNT(*) FROM st_pipeline_offsets WHERE pipeline_id='P03'"
           )
           assert count == 1  # Upsert, not 2 rows
   ```

2. **Phase Status Tests**:
   - `test_phase_transitions_recorded`: Each R* phase updates st_pipeline_status
   - `test_failed_cycle_records_error`: FAILED status includes error_message
   - `test_aborted_cycle_marked`: Timeout → ABORTED status

3. **Metrics Integration Tests**:
   - `test_cycle_counter_incremented`: p03_cycle_total incremented on completion
   - `test_phase_histogram_recorded`: p03_phase_duration_seconds per phase
   - `test_decision_counter_labeled`: p03_decisions_total with correct labels
   - `test_gap_gauge_updated`: p03_gaps_pending reflects queue state

4. **Structured Logging Tests**:
   - `test_cycle_start_logged_with_fields`: Required fields present
   - `test_decision_debug_logged`: Per-decision logs at DEBUG level
   - `test_error_logged_with_context`: Error logs include cycle_id, phase, error_code
   - `test_no_sensitive_data_logged`: Raw text content not in logs

---

### Epic 7.5: K0 Architecture Master Closure

#### Issue 7.5.1: Milestone 7 K0 Updates

**What to Cover**:

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated to reflect M7 completion
- [ ] **Part 3.1 (Module Registry)**: Event emission modules documented
- [ ] **Part 4.1 (Event Topics)**: P03 outbound events (consolidation.complete, gap.detected) registered
- [ ] **Part 5.1 (Contract Registry)**: P06/P08 integration contracts added
- [ ] **Part 5.2 (Syscall Matrix)**: Bus event emission capabilities registered
- [ ] **Part 5.3 (Storage Tables)**: st_outbox table documented
- [ ] **Part 7.1 (ADR Index)**: ADR status for M7 decisions updated
- [ ] **Version Header**: Document version bumped to reflect M7 completion

**K0 File**: `k0/pipelines/k0_architecture_master.md`

---

## Milestone 8: Testing & Performance

**Goal**: Integration tests, performance validation, golden dataset
**Gate**: GATE 4 (Test Implementation)
**Dossier Reference**: Section 10 (Testing Strategy), Section 15 (Performance Tuning)
**Test Reference**: [test_command_port.py](../../tests/integration/test_command_port.py) for integration patterns

### Epic 8.1: Integration Tests

> **Dossier Reference**: Section 10.3 (Integration Tests), Section 10.3.1 (End-to-End Cycle)
> **Pattern Reference**: tests/integration/test_command_port.py for @pytest.mark.integration usage

#### Issue 8.1.1: Full Cycle Integration Test

**What to Cover**:

1. **Test Location**: `tests/k0/pipelines/p03/integration/test_full_cycle.py`

2. **R0 → R8 Complete Flow Test**:

   ```python
   @pytest.mark.integration
   class TestFullConsolidationCycle:
       """End-to-end consolidation cycle tests."""

       async def test_basic_consolidation_cycle(
           self,
           pipeline,
           p03_fixtures: P03TestFixtures
       ):
           """Test complete R0-R8 cycle with known input."""
           # Setup: 100 events with known patterns
           events = p03_fixtures.create_events_with_patterns(
               n_events=100,
               n_patterns=5,
               events_per_pattern=20
           )
           await pipeline.storage.insert_hipp_events(events)

           # Execute
           result = await pipeline.run_cycle(
               tenant_id="test_tenant",
               space_id="test_space"
           )

           # Assert cycle completed
           assert result.status == "SUCCESS"
           assert result.events_processed == 100
           assert len(result.phases_completed) == 9  # R0-R8
   ```

3. **Assertions Per Phase**:
   - **R0**: Lock acquired, cycle_id generated
   - **R1**: Batch selected with importance scores
   - **R2**: Clusters formed (expect ~5 clusters for 5 patterns)
   - **R3**: Duplicates marked, decay applied
   - **R4**: Entities extracted to st_kg_dom, edges to st_kg_edges
   - **R5**: Dream insights generated (if enabled)
   - **R6**: st_hipp_events.consolidation_status updated
   - **R7**: Truth records written to memory layers
   - **R8**: Events emitted, offsets checkpointed

4. **Database State Verification**:
   - Query st_sem for pattern records (expect 5)
   - Query st_kg_dom for entities (expect extracted from events)
   - Query st_pipeline_offsets for checkpoint
   - Query st_pipeline_status for COMPLETED status

5. **Cleanup Fixture**:
   - Reset all truth tables between tests
   - Clear st_hipp_events staging data
   - Reset st_pipeline_offsets

---

#### Issue 8.1.2: Bidirectional Reconciliation Tests

**What to Cover**:

1. **All 6 Decision Types** (per Dossier Section 10.3.1):

   ```python
   @pytest.mark.integration
   class TestBidirectionalReconciliation:
       """Test all 6 reconciliation decision types."""

       async def test_reinforce_boosts_confidence(self, pipeline, fixtures):
           """REINFORCE: Signal matches truth, confidence++."""
           # Setup: Existing truth with confidence=0.6
           existing = fixtures.create_semantic_truth(confidence=0.6, obs_count=3)
           await pipeline.storage.insert_semantic(existing)

           # Setup: Matching events (similarity > 0.85)
           events = fixtures.create_events_matching_truth(
               truth=existing, n_events=5, similarity=0.92
           )
           await pipeline.storage.insert_hipp_events(events)

           # Execute
           await pipeline.run_cycle(tenant_id=existing.tenant_id, space_id=existing.space_id)

           # Assert
           updated = await pipeline.storage.get_semantic_by_id(existing.id)
           assert updated.confidence > 0.6
           assert updated.observation_count == 8  # 3 + 5
           assert updated.decay_factor == 1.0  # Reset

       async def test_extend_adds_examples(self, pipeline, fixtures):
           """EXTEND: Signal adds examples to existing pattern (0.6 <= sim < 0.85)."""
           existing = fixtures.create_semantic_truth(content="User likes coffee")
           events = fixtures.create_events(
               content="User prefers dark roast coffee",
               similarity_to_existing=0.72
           )
           # ... execute and assert extended examples

       async def test_create_for_novel_signal(self, pipeline, fixtures):
           """CREATE: Signal is novel, creates new truth entry."""
           # No existing truths
           events = fixtures.create_events(content="User has a dog named Max")

           await pipeline.run_cycle(...)

           # Assert new semantic record created
           records = await pipeline.storage.query_semantic(...)
           assert len(records) == 1
           assert records[0].version == 1

       async def test_evolve_supersedes_truth(self, pipeline, fixtures):
           """EVOLVE: Signal causes truth entry to split/merge (0.4 <= sim < 0.6)."""
           existing = fixtures.create_semantic_truth(content="User likes coffee")
           events = fixtures.create_events(
               content="User now prefers tea",
               similarity_to_existing=0.45
           )
           # Assert: existing.is_canonical = False, new version created

       async def test_contradict_emits_gap(self, pipeline, fixtures, mock_bus):
           """CONTRADICT: Signal conflicts with high-confidence truth."""
           existing = fixtures.create_semantic_truth(
               content="User loves coffee", confidence=0.9, obs_count=10
           )
           events = fixtures.create_events(content="User hates coffee")

           await pipeline.run_cycle(...)

           # Assert gap emitted
           gaps = mock_bus.get_published('p03.gap.detected.v1')
           assert len(gaps) == 1
           assert gaps[0]['gap_type'] == 'CONTRADICTION'

       async def test_prune_archives_stale_record(self, pipeline, fixtures):
           """PRUNE: Low decay_factor triggers archival."""
           stale = fixtures.create_semantic_truth(decay_factor=0.05)
           await pipeline.storage.insert_semantic(stale)

           await pipeline.run_cycle(...)

           updated = await pipeline.storage.get_semantic_by_id(stale.id)
           assert updated.archival_status == 'ARCHIVED'
   ```

2. **Similarity Threshold Boundaries**:
   - Test boundary at 0.85: sim=0.85 → REINFORCE, sim=0.84 → EXTEND
   - Test boundary at 0.6: sim=0.60 → EXTEND, sim=0.59 → EVOLVE
   - Test boundary at 0.4: sim=0.40 → EVOLVE, sim=0.39 → CONTRADICT

3. **Confidence Dynamics**:
   - Verify confidence increments follow formula
   - Verify confidence cap at 0.99
   - Verify decay_factor reset on observation

---

#### Issue 8.1.3: P02 -> P03 Contract Tests

**What to Cover**:

1. **st_hipp_events Input Validation**:

   ```python
   @pytest.mark.integration
   class TestP02P03Contract:
       """Test P02 → P03 input contract."""

       async def test_required_columns_present(self, pipeline, db_session):
           """Verify st_hipp_events has all required P03 columns."""
           required_columns = [
               'event_id', 'tenant_id', 'space_id', 'actor_id',
               'embedding_id', 'embedding_status',
               'entities_json', 'sentiment_score', 'dominant_emotions_json',
               'salience_score', 'simhash_hex', 'minhash32',
               'consolidation_status', 'created_at'
           ]
           actual = await db_session.get_table_columns('st_hipp_events')
           for col in required_columns:
               assert col in actual, f"Missing column: {col}"

       async def test_entities_json_parsing(self, pipeline, fixtures):
           """Verify entities_json from P02 UltraBERT NER parses correctly."""
           events = fixtures.create_events_with_entities_json([
               {"entity": "Alice", "type": "PERSON", "confidence": 0.95},
               {"entity": "Google", "type": "ORGANIZATION", "confidence": 0.88}
           ])
           # Execute R4 and verify entities extracted to st_kg_dom

       async def test_embedding_id_links_to_st_vec(self, pipeline, fixtures):
           """Verify embedding_id references valid st_vec record."""
           events = fixtures.create_events_with_embeddings()
           # Execute and verify embedding lookup succeeds

       async def test_embedding_status_ready_required(self, pipeline, fixtures):
           """Verify only READY embeddings are processed."""
           events_pending = fixtures.create_events(embedding_status='PENDING')
           events_ready = fixtures.create_events(embedding_status='READY')
           # Execute and verify only READY events processed
   ```

2. **Affect Signal Validation**:
   - `sentiment_score` in range [-1, +1]
   - `dominant_emotions_json` valid array
   - `affect_valence`, `affect_arousal` in expected ranges

3. **Fingerprint Validation**:
   - `simhash_hex` is 16-character hex string
   - `minhash32` is valid 32-band signature

---

#### Issue 8.1.4: P03 -> P06 Contract Tests

**What to Cover**:

1. **Gap Emission Contract** (per Dossier Section 9.3):

   ```python
   @pytest.mark.integration
   class TestP03P06Contract:
       """Test P03 → P06 output contract."""

       async def test_gap_payload_schema(self, pipeline, fixtures, mock_bus):
           """Verify p03.gap.detected.v1 payload matches contract."""
           # Trigger a contradiction to emit gap
           existing = fixtures.create_semantic_truth(confidence=0.9)
           events = fixtures.create_contradicting_events(existing)

           await pipeline.run_cycle(...)

           gaps = mock_bus.get_published('p03.gap.detected.v1')
           assert len(gaps) >= 1

           gap = gaps[0]
           # Required fields
           assert 'gap_id' in gap
           assert 'tenant_id' in gap
           assert 'space_id' in gap
           assert gap['gap_type'] in [
               'AMBIGUOUS_ENTITY', 'LOW_CONFIDENCE_EDGE', 'MISSING_ATTRIBUTE',
               'CONTRADICTION', 'CONCEPT_DRIFT', 'STRUCTURAL_HOLE', 'STALE_ANCHOR'
           ]
           assert 0.0 <= gap['importance_score'] <= 1.0
           assert 'context' in gap
           assert 'detected_at' in gap

       async def test_st_learning_queue_populated(self, pipeline, fixtures):
           """Verify gaps written to st_learning_queue."""
           # Trigger gap
           # ...
           queue = await pipeline.storage.query_learning_queue(status='PENDING')
           assert len(queue) >= 1
           assert queue[0].gap_type == 'CONTRADICTION'
           assert queue[0].ttl_expires_at > int(time.time())

       async def test_question_template_provided(self, pipeline, fixtures, mock_bus):
           """Verify context includes question_template."""
           # Trigger gap
           # ...
           gap = mock_bus.get_published('p03.gap.detected.v1')[0]
           assert 'question_template' in gap['context']
           assert len(gap['context']['question_template']) > 0
   ```

2. **Gap Priority Validation**:
   - `importance_score` computed per formula (entropy, recency, impact)
   - Gaps sorted by importance_score DESC

3. **TTL Validation**:
   - Default TTL = 168 hours (7 days)
   - `ttl_expires_at` computed correctly

---

#### Issue 8.1.5: P03 -> P08 Contract Tests

**What to Cover**:

1. **Embedding Coordination**:

   ```python
   @pytest.mark.integration
   class TestP03P08Contract:
       """Test P03 ↔ P08 embedding coordination."""

       async def test_embedding_status_transitions(self, pipeline, fixtures):
           """Verify embedding_status lifecycle."""
           # PENDING → (P08 indexes) → READY → (P03 uses)
           events = fixtures.create_events(embedding_status='PENDING')
           # Simulate P08 indexing
           await pipeline.storage.update_embedding_status(
               events[0]['embedding_id'], 'READY'
           )
           # P03 should now process

       async def test_backpressure_handling(self, pipeline, fixtures):
           """Verify P03 handles P08 backpressure gracefully."""
           # Simulate circuit breaker open
           with mock.patch.object(pipeline.p08_client, 'is_available', return_value=False):
               result = await pipeline.run_cycle(...)
               # Should complete with local queue fallback
               assert result.status == "SUCCESS"
               assert result.p08_fallback_used == True

       async def test_new_embeddings_coordinated(self, pipeline, fixtures, mock_bus):
           """Verify new truth embeddings trigger P08 indexing."""
           # Create novel event → CREATE decision → new embedding
           events = fixtures.create_novel_events()
           await pipeline.run_cycle(...)

           # Verify p03.embedding.created.v1 emitted
           emb_events = mock_bus.get_published('p03.embedding.created.v1')
           assert len(emb_events) >= 1
   ```

2. **FAISS Query Integration**:
   - Similarity search uses indexed embeddings
   - Query batching respects QoS top_k_budget

---

#### Issue 8.1.6: Error Recovery Integration Tests

**What to Cover**:

1. **DLQ and Retry Patterns** (per Dossier Section 13):

   ```python
   @pytest.mark.integration
   class TestErrorRecovery:
       """Test error handling and recovery."""

       async def test_transient_failure_retries(self, pipeline, fixtures):
           """Transient failure → retry → success."""
           # Inject transient DB failure
           with mock.patch.object(
               pipeline.db, 'execute',
               side_effect=[ConnectionError("Timeout"), None]  # Fail then succeed
           ):
               result = await pipeline.run_cycle(...)
               assert result.status == "SUCCESS"
               assert result.retry_count == 1

       async def test_permanent_failure_dlq(self, pipeline, fixtures):
           """Permanent failure → DLQ."""
           # Inject permanent validation error
           events = fixtures.create_events_with_invalid_schema()
           await pipeline.storage.insert_hipp_events(events)

           result = await pipeline.run_cycle(...)

           # Verify event routed to DLQ
           dlq_records = await pipeline.storage.query_dlq(pipeline_id='P03')
           assert len(dlq_records) >= 1
           assert dlq_records[0].error_type == 'VALIDATION'

       async def test_circuit_breaker_opens(self, pipeline, fixtures):
           """Repeated failures → circuit breaker open → graceful skip."""
           # Inject 5 consecutive failures to trip breaker
           failure_count = 0
           def failing_call(*args, **kwargs):
               nonlocal failure_count
               failure_count += 1
               if failure_count <= 5:
                   raise ConnectionError("P08 unavailable")
               return None

           with mock.patch.object(pipeline.p08_client, 'query', failing_call):
               result = await pipeline.run_cycle(...)
               assert result.p08_circuit_open == True
               # Should still complete with fallback

       async def test_partial_cycle_recovery(self, pipeline, fixtures):
           """Crash during R4 → restart resumes from R4."""
           # Start cycle, crash at R4
           events = fixtures.create_events(n=100)
           await pipeline.storage.insert_hipp_events(events)

           # Simulate crash at R4
           with mock.patch.object(pipeline, '_execute_r4', side_effect=RuntimeError("Crash")):
               with pytest.raises(RuntimeError):
                   await pipeline.run_cycle(...)

           # Check status is stuck at R4
           status = await pipeline.storage.get_cycle_status(cycle_id)
           assert status.phase == 'R4'

           # Restart - should resume from R4
           result = await pipeline.run_cycle(...)
           assert result.status == "SUCCESS"
   ```

2. **Error Classification Verification**:
   - TRANSIENT: DB timeout, lock contention → retry
   - VALIDATION: Schema mismatch, constraint violation → DLQ
   - LOGIC: Reconciliation failure → DLQ + alert
   - FATAL: OOM, disk full → abort cycle

---

### Epic 8.2: Performance Tests

> **Dossier Reference**: Section 10.5 (Performance Tests), Section 15 (Performance Tuning)
> **Test Reference**: tests/performance/test_pem_latency.py for @pytest.mark.performance patterns
> **K0 Reference**: k0/qos/ for scheduler and QoS context integration

#### Issue 8.2.1: Throughput Benchmark

**What to Cover**:

1. **Target**: 1000 events/minute (per Dossier Section 10.5)

2. **Benchmark Implementation**:

   ```python
   @pytest.mark.performance
   class TestThroughputBenchmarks:
       """Performance benchmarks for P03 consolidation."""

       async def test_consolidation_throughput(
           self,
           pipeline,
           p03_fixtures: P03TestFixtures
       ):
           """Target: 1000 events/minute."""
           # Setup: 1000 events
           events = p03_fixtures.create_random_events(n=1000)
           await pipeline.storage.insert_hipp_events(events)

           # Execute with timing
           start = time.perf_counter()
           await pipeline.run_cycle(
               tenant_id="perf_tenant",
               space_id="perf_space"
           )
           elapsed = time.perf_counter() - start

           # Calculate throughput
           events_per_second = 1000 / elapsed
           events_per_minute = events_per_second * 60

           # Assert
           assert events_per_minute >= 1000, (
               f"Throughput {events_per_minute:.0f} events/min "
               f"below target 1000 events/min"
           )

           # Record for baseline tracking
           pytest.benchmark_result = {
               'events_processed': 1000,
               'duration_seconds': elapsed,
               'events_per_minute': events_per_minute
           }
   ```

3. **Measurement Metrics**:
   - `events_processed / cycle_duration_seconds * 60`
   - Record P50, P95, P99 across multiple runs
   - Track regression vs baseline

4. **Environment Requirements**:
   - Isolated test database (PostgreSQL)
   - Disabled DEBUG logging
   - Disabled P03_FF_OBSERVABILITY_VERBOSE

5. **CI Integration**:
   - Run nightly on dedicated perf environment
   - Fail build if throughput drops >10% from baseline

---

#### Issue 8.2.2: Large Batch Cycle Time

**What to Cover**:

1. **Target**: <5 min for 10K events (per Dossier Section 10.5)

2. **Batch Size Scaling Tests**:

   ```python
   @pytest.mark.performance
   @pytest.mark.parametrize("batch_size", [1000, 5000, 10000, 20000])
   async def test_large_batch_cycle_time(
       self,
       pipeline,
       p03_fixtures,
       batch_size: int
   ):
       """Target: <5 min for 10K events."""
       events = p03_fixtures.create_random_events(n=batch_size)
       await pipeline.storage.insert_hipp_events(events)

       start = time.perf_counter()
       result = await pipeline.run_cycle(
           tenant_id="perf_tenant",
           space_id="perf_space"
       )
       elapsed = time.perf_counter() - start

       # Targets by batch size
       targets = {
           1000: 30,    # 30 seconds
           5000: 150,   # 2.5 minutes
           10000: 300,  # 5 minutes
           20000: 600,  # 10 minutes
       }

       assert elapsed < targets[batch_size], (
           f"Cycle time {elapsed:.1f}s exceeds target {targets[batch_size]}s "
           f"for {batch_size} events"
       )
   ```

3. **Phase Timing Breakdown**:
   - Record duration per phase (R0-R8)
   - Identify bottleneck phases
   - Per Dossier Section 15.3.1 targets:
     - R2 (Clustering): <200ms P95
     - R4 (KG): <300ms P95
     - R7 (Write): <150ms P95

4. **Scaling Curve Analysis**:
   - Plot batch_size vs cycle_time
   - Verify linear or sub-linear scaling
   - Alert if super-linear (O(n²)) detected

---

#### Issue 8.2.3: Memory Footprint Validation

**What to Cover**:

1. **Target**: <500MB peak per cycle (per Dossier Section 10.5)

2. **Memory Tracking Implementation**:

   ```python
   @pytest.mark.performance
   class TestMemoryFootprint:
       """Memory usage benchmarks."""

       async def test_peak_memory_under_limit(
           self,
           pipeline,
           p03_fixtures
       ):
           """Target: <500MB peak memory."""
           import tracemalloc

           events = p03_fixtures.create_random_events(n=10000)
           await pipeline.storage.insert_hipp_events(events)

           tracemalloc.start()

           await pipeline.run_cycle(
               tenant_id="perf_tenant",
               space_id="perf_space"
           )

           current, peak = tracemalloc.get_traced_memory()
           tracemalloc.stop()

           peak_mb = peak / (1024 * 1024)

           assert peak_mb < 500, (
               f"Peak memory {peak_mb:.1f}MB exceeds target 500MB"
           )

       async def test_streaming_prevents_oom(
           self,
           pipeline,
           p03_fixtures
       ):
           """Streaming batches prevent OOM on large datasets."""
           events = p03_fixtures.create_random_events(n=100000)
           await pipeline.storage.insert_hipp_events(events)

           # Should not raise MemoryError
           try:
               await pipeline.run_cycle(
                   tenant_id="perf_tenant",
                   space_id="perf_space",
                   batch_size=1000  # Stream in batches
               )
           except MemoryError:
               pytest.fail("MemoryError raised - streaming not working")

       async def test_gc_runs_between_phases(self, pipeline, p03_fixtures):
           """Verify garbage collection between phases."""
           import gc
           gc_counts_before = gc.get_count()
           # Execute cycle
           # Verify gc.get_count() shows collections occurred
   ```

3. **Resource Monitoring**:
   - RSS (Resident Set Size)
   - Heap allocations
   - GC collection counts

4. **Memory Leak Detection**:
   - Run 10 consecutive cycles
   - Assert memory doesn't grow indefinitely
   - Check for leaked DB connections

---

#### Issue 8.2.4: 90-Minute Cycle Validation

**What to Cover**:

1. **Full Budget Compliance** (per Dossier Section 3.2):

   | Phase | Budget | Cumulative |
   |-------|--------|------------|
   | R0 | 1 min | 1 min |
   | R1 | 15 min | 16 min |
   | R2 | 20 min | 36 min |
   | R3+R4 | 25 min (parallel) | 61 min |
   | R5 | 30 min (optional) | 91 min |
   | R6 | 5 min | 96 min |
   | R7 | 10 min | 106 min |
   | R8 | 5 min | 111 min |

2. **Budget Enforcement Test**:

   ```python
   @pytest.mark.performance
   async def test_phase_budget_compliance(self, pipeline, p03_fixtures):
       """Verify each phase completes within budget."""
       events = p03_fixtures.create_random_events(n=10000)
       await pipeline.storage.insert_hipp_events(events)

       phase_timings = {}

       # Instrument phase timing
       for phase in ['R0', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8']:
           start = time.perf_counter()
           await pipeline._execute_phase(phase)
           phase_timings[phase] = time.perf_counter() - start

       # Assert budgets (in seconds)
       budgets = {
           'R0': 60, 'R1': 900, 'R2': 1200,
           'R3': 750, 'R4': 750,  # Parallel
           'R5': 1800,  # Optional
           'R6': 300, 'R7': 600, 'R8': 300
       }

       for phase, budget in budgets.items():
           if phase in phase_timings:
               assert phase_timings[phase] < budget, (
                   f"Phase {phase} exceeded budget: "
                   f"{phase_timings[phase]:.1f}s > {budget}s"
               )
   ```

3. **Timeout Enforcement**:
   - Each phase has hard timeout
   - Timeout triggers graceful abort
   - Partial progress checkpointed

---

#### Issue 8.2.5: QoS Token Budget Validation

**What to Cover**:

1. **K0 QoS Integration** (per Dossier Section 15.1-15.3):

   ```python
   @pytest.mark.performance
   async def test_qos_token_budget_compliance(
       self,
       pipeline,
       p03_fixtures,
       qos_context: QoSContext
   ):
       """Verify no phase exceeds allocated token budget."""
       events = p03_fixtures.create_random_events(n=1000)
       await pipeline.storage.insert_hipp_events(events)

       # Set QoS budgets
       qos_context.fanout_budget = 1000  # Max cross-event queries
       qos_context.top_k_budget = 500    # Max similarity results

       await pipeline.run_cycle(
           tenant_id="perf_tenant",
           space_id="perf_space",
           qos_context=qos_context
       )

       # Assert budgets not exceeded
       assert qos_context.fanout_consumed <= 1000
       assert qos_context.top_k_consumed <= 500

   async def test_qos_tightening_respected(self, pipeline, p03_fixtures):
       """Verify QoS tightening from policy obligations."""
       # Apply AMBER band tightening
       qos_context = QoSContext(fanout_budget=1000)
       qos_context.tighten(QoSTightening(fanout_factor=0.5))  # 50% reduction

       # Run with tightened budget
       await pipeline.run_cycle(qos_context=qos_context)

       # Should complete within reduced budget
       assert qos_context.fanout_consumed <= 500
   ```

2. **Scheduler Token Acquisition**:
   - Verify token acquired before batch processing
   - Verify token released on completion
   - Verify WDRR priority respected (GREEN > AMBER > RED)

---

#### Issue 8.2.6: Embedding Query Batching Test

**What to Cover**:

1. **Target**: <100ms per batch of 100 vectors (per Dossier Section 15.3)

2. **FAISS Query Performance**:

   ```python
   @pytest.mark.performance
   async def test_embedding_query_batching(
       self,
       pipeline,
       p03_fixtures,
       faiss_index
   ):
       """Target: <100ms per batch of 100 vectors."""
       # Create 100 query vectors
       query_vectors = p03_fixtures.create_embeddings(n=100)

       # Execute batched query
       start = time.perf_counter()
       results = await faiss_index.batch_query(
           vectors=query_vectors,
           top_k=10
       )
       elapsed_ms = (time.perf_counter() - start) * 1000

       assert elapsed_ms < 100, (
           f"Batch query {elapsed_ms:.1f}ms exceeds target 100ms"
       )

   async def test_individual_vs_batch_performance(self, pipeline, faiss_index):
       """Verify batching provides >5x speedup."""
       query_vectors = p03_fixtures.create_embeddings(n=100)

       # Individual queries
       start_individual = time.perf_counter()
       for v in query_vectors:
           await faiss_index.query(v, top_k=10)
       elapsed_individual = time.perf_counter() - start_individual

       # Batched query
       start_batch = time.perf_counter()
       await faiss_index.batch_query(query_vectors, top_k=10)
       elapsed_batch = time.perf_counter() - start_batch

       speedup = elapsed_individual / elapsed_batch
       assert speedup >= 5, f"Batch speedup {speedup:.1f}x below target 5x"
   ```

3. **P08 Coordination**:
   - Verify FAISS index is warmed before query
   - Verify index refresh doesn't block queries

---

#### Issue 8.2.7: PostgreSQL Connection Pool Performance Test

> **PostgreSQL Migration Note** (2025-01): Replaces SQLite PRAGMA tests.
> Tests asyncpg pool configuration and session settings.

**What to Cover**:

1. **Pool Settings** (per k0/config/postgres.py PostgresSettings):

   ```python
   @pytest.mark.performance
   async def test_postgres_pool_configuration(self, db_pool):
       """Verify PostgreSQL pool settings are optimal."""
       # Verify pool size
       assert db_pool.get_min_size() >= 5
       assert db_pool.get_max_size() <= 25

       # Verify session settings on acquired connection
       async with db_pool.acquire() as conn:
           result = await conn.fetchval("SHOW work_mem")
           assert result == "64MB", f"work_mem={result}, expected 64MB"

           result = await conn.fetchval("SHOW statement_timeout")
           assert result == "60s", f"statement_timeout={result}, expected 60s"

   async def test_connection_reuse_performance(self, db_pool, p03_fixtures):
       """Verify connection pooling provides performance benefit."""
       events = p03_fixtures.create_random_events(n=1000)

       # Measure with pooled connections
       start_pooled = time.perf_counter()
       async with db_pool.acquire() as conn:
           for event in events:
               await conn.execute(
                   "INSERT INTO st_hipp_events (event_id, data) VALUES ($1, $2)",
                   event.id, event.data
               )
       elapsed_pooled = time.perf_counter() - start_pooled

       # Connection pooling should be efficient
       assert elapsed_pooled < 5.0, (
           f"Pooled insert too slow: {elapsed_pooled:.2f}s for 1000 events"
       )
   ```

2. **Index Verification**:
   - Verify required indexes exist
   - Verify EXPLAIN QUERY PLAN uses indexes
   - Alert on full table scans

---

### Epic 8.3: Golden Dataset Tests

> **Dossier Reference**: Section 10.6 (Golden Dataset Testing), Section 12.2.4 (Golden Dataset Location)
> **Location Reference**: golden_dataset/p03/ for P03-specific test fixtures
> **Schema Reference**: golden_dataset/schema.yaml for entity types, emotion labels, family roles

#### Issue 8.3.1: Create P03 Golden Dataset

**What to Cover**:

1. **Golden Dataset Structure** (per Dossier Section 12.2.4):

   Location: `golden_dataset/p03/`

   Files to create:
   - `hipp_events_baseline.yaml` - Canonical input events
   - `truth_table_expected.yaml` - Expected truth table state
   - `patterns_expected.yaml` - Expected pattern extractions
   - `gaps_expected.yaml` - Expected gap detections
   - `reconciliation_expected.yaml` - Expected decisions

2. **Event Baseline Format**:

   ```yaml
   # golden_dataset/p03/hipp_events_baseline.yaml
   ---
   version: "1.0.0"
   description: "P03 consolidation golden dataset"
   scenarios:
     - name: "family_morning_routine"
       events:
         - id: "evt_001"
           tenant_id: "test_tenant"
           space_id: "test_space"
           entity_type: "person"  # per schema.yaml entity_types
           entity_id: "person_mom"
           timestamp: "2024-01-15T07:00:00Z"
           payload:
             action: "wake_up"
             emotion: "neutral"  # per schema.yaml emotion_labels
           privacy_band: "GREEN"

         - id: "evt_002"
           tenant_id: "test_tenant"
           space_id: "test_space"
           entity_type: "person"
           entity_id: "person_child"
           timestamp: "2024-01-15T07:15:00Z"
           payload:
             action: "breakfast"
             emotion: "happy"
           privacy_band: "GREEN"
   ```

3. **Entity Types** (per golden_dataset/schema.yaml):
   - person, location, event, object, relationship
   - organization, concept, time_period, emotion
   - activity, goal, preference, routine, narrative

4. **Family Roles** (per golden_dataset/schema.yaml):
   - parent, child, spouse, sibling, grandparent, grandchild
   - aunt_uncle, cousin, niece_nephew, in_law
   - step_parent, step_child, step_sibling
   - foster_parent, foster_child, guardian

5. **Scenario Coverage**:
   - Morning routine (5+ events)
   - Weekly schedule (20+ events)
   - Monthly patterns (50+ events)
   - Yearly traditions (100+ events)
   - Conflict resolution (10+ events)
   - New family member (15+ events)

---

#### Issue 8.3.2: Pattern Extraction Golden Tests

**What to Cover**:

1. **Pattern Test Implementation** (per Dossier Section 10.6):

   ```python
   @pytest.mark.golden
   class TestPatternExtractionGolden:
       """Golden dataset tests for pattern extraction."""

       @pytest.fixture
       def golden_loader(self):
           """Load P03 golden dataset."""
           from golden_dataset.loader import GoldenDatasetLoader
           return GoldenDatasetLoader("golden_dataset/p03/")

       async def test_routine_pattern_detection(
           self,
           pipeline,
           golden_loader
       ):
           """Verify routine patterns detected from golden events."""
           # Load golden events
           events = golden_loader.load_events("hipp_events_baseline.yaml")
           expected = golden_loader.load_patterns("patterns_expected.yaml")

           # Insert and run
           await pipeline.storage.insert_hipp_events(events)
           result = await pipeline.run_cycle(
               tenant_id="test_tenant",
               space_id="test_space"
           )

           # Extract detected patterns
           actual_patterns = await pipeline.storage.get_patterns(
               tenant_id="test_tenant",
               space_id="test_space"
           )

           # Assert pattern count matches
           assert len(actual_patterns) == len(expected.patterns), (
               f"Expected {len(expected.patterns)} patterns, "
               f"got {len(actual_patterns)}"
           )

           # Assert each expected pattern exists
           for exp_pattern in expected.patterns:
               matching = [
                   p for p in actual_patterns
                   if p.pattern_type == exp_pattern.pattern_type
                   and p.entity_id == exp_pattern.entity_id
               ]
               assert matching, f"Missing pattern: {exp_pattern}"
   ```

2. **Pattern Types to Test**:
   - Temporal patterns (daily, weekly, monthly)
   - Behavioral patterns (routines, habits)
   - Emotional patterns (mood cycles)
   - Relational patterns (interaction frequencies)

3. **Verification Criteria**:
   - Pattern type matches expected
   - Entity association correct
   - Confidence score within tolerance (±0.1)
   - Temporal bounds within tolerance (±1 hour)

---

#### Issue 8.3.3: Gap Detection Golden Tests

**What to Cover**:

1. **Gap Detection Scenarios**:

   ```python
   @pytest.mark.golden
   class TestGapDetectionGolden:
       """Golden dataset tests for gap detection."""

       async def test_missing_routine_gap_detected(
           self,
           pipeline,
           golden_loader
       ):
           """Verify gaps detected when routine events missing."""
           events = golden_loader.load_events("hipp_events_with_gaps.yaml")
           expected_gaps = golden_loader.load_gaps("gaps_expected.yaml")

           await pipeline.storage.insert_hipp_events(events)
           result = await pipeline.run_cycle(
               tenant_id="test_tenant",
               space_id="test_space"
           )

           actual_gaps = await pipeline.storage.get_detected_gaps(
               tenant_id="test_tenant",
               space_id="test_space"
           )

           # Verify gap count
           assert len(actual_gaps) == len(expected_gaps.gaps)

           # Verify gap details
           for exp_gap in expected_gaps.gaps:
               matching = [
                   g for g in actual_gaps
                   if g.gap_type == exp_gap.gap_type
                   and g.pattern_id == exp_gap.pattern_id
               ]
               assert matching, f"Missing gap: {exp_gap}"
   ```

2. **Gap Types**:
   - Missing routine occurrence
   - Unexpected timing deviation
   - Entity absence
   - Relationship gap (missing interaction)
   - Emotional gap (missing state)

3. **Gap Significance Levels**:
   - Minor (< 24 hours deviation)
   - Moderate (24-72 hours)
   - Major (> 72 hours)
   - Critical (pattern breaking)

---

#### Issue 8.3.4: Reconciliation Decision Golden Tests

**What to Cover**:

1. **Decision Type Testing** (per Dossier Section 5.4):

   ```python
   @pytest.mark.golden
   @pytest.mark.parametrize("decision_type", [
       "REINFORCE", "EXTEND", "CREATE",
       "EVOLVE", "CONTRADICT", "SUPERSEDE"
   ])
   async def test_reconciliation_decision_golden(
       self,
       pipeline,
       golden_loader,
       decision_type: str
   ):
       """Verify reconciliation decision matches golden expectation."""
       scenario_file = f"reconciliation_{decision_type.lower()}.yaml"
       scenario = golden_loader.load_scenario(scenario_file)

       # Load events for this scenario
       await pipeline.storage.insert_hipp_events(scenario.events)

       # Load existing truth (for non-CREATE scenarios)
       if decision_type != "CREATE":
           await pipeline.storage.insert_truth_entries(
               scenario.existing_truth
           )

       # Run reconciliation
       result = await pipeline.run_cycle(
           tenant_id="test_tenant",
           space_id="test_space"
       )

       # Verify decision type
       decisions = await pipeline.storage.get_reconciliation_decisions(
           tenant_id="test_tenant",
           space_id="test_space"
       )

       decision_types = [d.decision_type for d in decisions]
       assert decision_type in decision_types, (
           f"Expected {decision_type} decision, got {decision_types}"
       )
   ```

2. **Decision Scenario Files**:
   - `reconciliation_reinforce.yaml` - Consistent pattern reoccurrence
   - `reconciliation_extend.yaml` - Pattern applies to new entity
   - `reconciliation_create.yaml` - Novel pattern from new events
   - `reconciliation_evolve.yaml` - Pattern modification over time
   - `reconciliation_contradict.yaml` - Conflicting evidence
   - `reconciliation_supersede.yaml` - Old truth replaced by new

3. **Verification Points**:
   - Decision type correct
   - Confidence score reasonable (> 0.5 for action)
   - Affected truth entries correct
   - Audit trail logged

---

### Epic 8.4: Contract Validation

> **Dossier Reference**: Section 10.4 (Contract Testing), Section 8 (Data Contracts)
> **Contract Location**: k1/contracts/schemas/ for Pydantic models
> **Database Reference**: k0/storage/ for schema definitions

#### Issue 8.4.1: Schema Contract Tests

**What to Cover**:

1. **Pydantic Model Validation** (per Dossier Section 10.4):

   ```python
   @pytest.mark.contract
   class TestPydanticSchemaContracts:
       """Contract tests for Pydantic models."""

       def test_hipp_event_schema_required_fields(self):
           """Verify HippEvent requires all mandatory fields."""
           from k1.contracts.schemas import HippEvent

           # Valid event
           valid = HippEvent(
               id="evt_001",
               tenant_id="tenant",
               space_id="space",
               entity_type="person",
               entity_id="person_1",
               timestamp=datetime.now(UTC),
               payload={"action": "test"},
               privacy_band="GREEN"
           )
           assert valid.id == "evt_001"

           # Missing required field
           with pytest.raises(ValidationError) as exc:
               HippEvent(
                   id="evt_001",
                   # Missing tenant_id
                   space_id="space",
                   entity_type="person"
               )
           assert "tenant_id" in str(exc.value)

       def test_privacy_band_enum_validation(self):
           """Verify privacy_band accepts only valid values."""
           from k1.contracts.schemas import HippEvent

           # Valid bands
           for band in ["GREEN", "AMBER", "RED"]:
               event = HippEvent(
                   id="evt_001",
                   tenant_id="tenant",
                   space_id="space",
                   entity_type="person",
                   entity_id="person_1",
                   timestamp=datetime.now(UTC),
                   payload={},
                   privacy_band=band
               )
               assert event.privacy_band == band

           # Invalid band
           with pytest.raises(ValidationError):
               HippEvent(
                   ...,
                   privacy_band="INVALID"
               )

       def test_truth_table_entry_schema(self):
           """Verify TruthTableEntry schema constraints."""
           from k1.contracts.schemas import TruthTableEntry

           # Verify layer enum
           valid_layers = [
               "st_epi", "st_sem", "st_procedural",
               "st_people", "st_places", "st_concepts"
           ]
           for layer in valid_layers:
               entry = TruthTableEntry(
                   id="truth_001",
                   layer=layer,
                   ...
               )
               assert entry.layer == layer
   ```

2. **Schema Evolution Testing**:
   - Test forward compatibility (new fields)
   - Test backward compatibility (missing optional fields)
   - Test JSON serialization round-trip

---

#### Issue 8.4.2: Database Schema Contract Tests

**What to Cover**:

1. **Column Presence Validation**:

   ```python
   @pytest.mark.contract
   class TestDatabaseSchemaContracts:
       """Contract tests for database schemas."""

       async def test_hipp_events_table_schema(self, db_session):
           """Verify hipp_events table has required columns."""
           result = await db_session.execute(
               "PRAGMA table_info(hipp_events)"
           )
           columns = {row[1]: row[2] for row in result.fetchall()}

           required_columns = {
               'id': 'TEXT',
               'tenant_id': 'TEXT',
               'space_id': 'TEXT',
               'entity_type': 'TEXT',
               'entity_id': 'TEXT',
               'timestamp': 'TEXT',  # ISO 8601
               'payload': 'TEXT',    # JSON
               'privacy_band': 'TEXT',
               'embedding': 'BLOB',
               'created_at': 'TEXT',
           }

           for col, dtype in required_columns.items():
               assert col in columns, f"Missing column: {col}"
               assert columns[col] == dtype, (
                   f"Column {col} type mismatch: {columns[col]} != {dtype}"
               )

       async def test_truth_table_schema_per_layer(self, db_session):
           """Verify truth table schema matches per-layer requirements."""
           layers = [
               "st_epi", "st_sem", "st_procedural",
               "st_people", "st_places", "st_concepts"
           ]

           for layer in layers:
               result = await db_session.execute(
                   f"PRAGMA table_info({layer})"
               )
               columns = {row[1] for row in result.fetchall()}

               # Common required columns
               assert 'id' in columns
               assert 'tenant_id' in columns
               assert 'space_id' in columns
               assert 'created_at' in columns
               assert 'updated_at' in columns
               assert 'privacy_band' in columns
               assert 'confidence' in columns

       async def test_required_indexes_exist(self, db_session):
           """Verify required indexes are present."""
           # PostgreSQL pg_indexes catalog query
           result = await db_session.execute(
               "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
           )
           indexes = {row[0] for row in result.fetchall()}

           required_indexes = [
               'idx_hipp_events_tenant_space',
               'idx_hipp_events_timestamp',
               'idx_truth_tenant_space',
           ]

           for idx in required_indexes:
               assert idx in indexes, f"Missing index: {idx}"
   ```

2. **Foreign Key Constraints**:
   - Verify FK relationships enforced
   - Test cascade behavior on delete

---

#### Issue 8.4.3: Event Payload Contract Tests

**What to Cover**:

1. **Inter-Pipeline Contract Compliance**:

   ```python
   @pytest.mark.contract
   class TestEventPayloadContracts:
       """Contract tests for event payloads between pipelines."""

       def test_p02_to_p03_envelope_contract(self):
           """Verify P02 output matches P03 input contract."""
           from k1.contracts.schemas import P02OutputEnvelope, P03InputEnvelope

           # Create P02 output
           p02_output = P02OutputEnvelope(
               envelope_id="env_001",
               tenant_id="tenant",
               space_id="space",
               events=[...],
               metadata={...}
           )

           # Convert to P03 input
           p03_input = P03InputEnvelope.from_p02_output(p02_output)

           # Verify all required fields transferred
           assert p03_input.envelope_id == p02_output.envelope_id
           assert p03_input.tenant_id == p02_output.tenant_id
           assert len(p03_input.events) == len(p02_output.events)

       def test_p03_to_p06_pattern_contract(self):
           """Verify P03 pattern output matches P06 input contract."""
           from k1.contracts.schemas import P03PatternOutput, P06PatternInput

           # Create P03 output
           p03_output = P03PatternOutput(
               pattern_id="pat_001",
               pattern_type="routine",
               entities=["person_1", "person_2"],
               confidence=0.85,
               temporal_bounds={...}
           )

           # Convert to P06 input
           p06_input = P06PatternInput.from_p03_output(p03_output)

           # Verify semantic preservation
           assert p06_input.pattern_id == p03_output.pattern_id
           assert p06_input.confidence == p03_output.confidence

       def test_p03_to_p08_gap_contract(self):
           """Verify P03 gap output matches P08 input contract."""
           from k1.contracts.schemas import P03GapOutput, P08GapInput

           p03_gap = P03GapOutput(
               gap_id="gap_001",
               gap_type="missing_routine",
               pattern_id="pat_001",
               expected_time="2024-01-15T07:00:00Z",
               significance="moderate"
           )

           p08_input = P08GapInput.from_p03_output(p03_gap)

           assert p08_input.gap_id == p03_gap.gap_id
           assert p08_input.requires_embedding_refresh == True
   ```

2. **Version Compatibility**:
   - Test v1 payload accepted by v2 consumer
   - Test unknown fields ignored gracefully
   - Test schema version negotiation

3. **Error Contract Testing**:
   - Verify error payloads follow contract
   - Test DLQ message format compliance
   - Verify retry metadata preserved

---

### Epic 8.6: K0 Architecture Master Closure

#### Issue 8.6.1: Milestone 8 K0 Updates

**What to Cover**:

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated to reflect M8 completion
- [ ] **Part 3.1 (Module Registry)**: All P03 modules tested and documented
- [ ] **Part 4.1 (Event Topics)**: All P03 events validated
- [ ] **Part 5.1 (Contract Registry)**: All module/pipeline contracts validated
- [ ] **Part 5.2 (Syscall Matrix)**: All storage capabilities tested
- [ ] **Part 5.3 (Storage Tables)**: All table schemas validated
- [ ] **Part 7.1 (ADR Index)**: ADR status for M8 decisions updated
- [ ] **Version Header**: Document version bumped to reflect M8 completion

**K0 File**: `k0/pipelines/k0_architecture_master.md`

---

## Milestone 9: Deployment & Operations

**Goal**: Production deployment, observability, runbooks, SLOs
**Gate**: GATE 5 (Documentation of Change)
**Dossier Reference**: Sections 13 (Error Handling), 14 (Security), 15 (Performance), 16 (Configuration), 17 (Ops Readiness)

### Epic 9.1: Deployment Artifacts

> **Dossier Reference**: Section 16 (Configuration), Section 15 (Performance)
> **K0 Reference**: k0/deploy/ for deployment patterns, Dockerfile templates
> **Environment Reference**: docs/deployment/ for Docker and K8s patterns

#### Issue 9.1.1: Docker Configuration

**What to Cover**:

1. **P03 Dockerfile**:

   ```dockerfile
   # Dockerfile.p03
   FROM python:3.12-slim AS base

   # Labels for container registry
   LABEL org.opencontainers.image.title="P03 Consolidation Pipeline"
   LABEL org.opencontainers.image.description="Memory consolidation sleep cycle"
   LABEL org.opencontainers.image.version="${P03_VERSION}"

   # Environment
   ENV PYTHONUNBUFFERED=1
   ENV PYTHONDONTWRITEBYTECODE=1
   ENV P03_LOG_LEVEL=INFO
   ENV P03_DB_PATH=/data/p03.db
   ENV P03_CYCLE_INTERVAL_MINUTES=90

   # Dependencies
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   # Application
   COPY k0/ ./k0/
   COPY k1/ ./k1/

   # Health check
   HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
     CMD python -c "from k0.cli.health import check_p03; check_p03()"

   # Entrypoint
   CMD ["python", "-m", "k0.pipelines.p03.main"]
   ```

2. **Multi-Stage Build** (for smaller image):

   ```dockerfile
   # Build stage
   FROM python:3.12-slim AS builder
   COPY requirements.txt .
   RUN pip install --no-cache-dir --target=/deps -r requirements.txt

   # Runtime stage
   FROM python:3.12-slim AS runtime
   COPY --from=builder /deps /usr/local/lib/python3.12/site-packages
   COPY k0/ ./k0/
   COPY k1/ ./k1/
   CMD ["python", "-m", "k0.pipelines.p03.main"]
   ```

3. **Docker Compose Integration**:

   ```yaml
   # docker-compose.p03.yml
   services:
     p03-consolidation:
       build:
         context: .
         dockerfile: Dockerfile.p03
       environment:
         - P03_DB_PATH=/data/p03.db
         - P03_CYCLE_INTERVAL_MINUTES=90
         - P03_FF_DREAM_EXPLORATION=true
         - K0_DB_PATH=/data/k0.db
         - K0_METRICS_ENDPOINT=http://prometheus:9090
       volumes:
         - p03-data:/data
       restart: unless-stopped
       logging:
         driver: "json-file"
         options:
           max-size: "10m"
           max-file: "3"

   volumes:
     p03-data:
   ```

4. **Resource Limits**:

   ```yaml
   deploy:
     resources:
       limits:
         memory: 512M
         cpus: '1.0'
       reservations:
         memory: 256M
         cpus: '0.5'
   ```

---

#### Issue 9.1.2: K8s Manifests (if applicable)

**What to Cover**:

1. **Deployment Manifest**:

   ```yaml
   # k8s/p03-deployment.yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: p03-consolidation
     labels:
       app: familyos
       component: p03-consolidation
       tier: background
   spec:
     replicas: 1  # Single instance per tenant cluster
     strategy:
       type: Recreate  # No rolling updates for singleton
     selector:
       matchLabels:
         app: p03-consolidation
     template:
       metadata:
         labels:
           app: p03-consolidation
         annotations:
           prometheus.io/scrape: "true"
           prometheus.io/port: "9090"
           prometheus.io/path: "/metrics"
       spec:
         containers:
           - name: p03
             image: familyos/p03-consolidation:latest
             resources:
               limits:
                 memory: "512Mi"
                 cpu: "1000m"
               requests:
                 memory: "256Mi"
                 cpu: "500m"
             env:
               - name: P03_DB_PATH
                 value: "/data/p03.db"
               - name: P03_CYCLE_INTERVAL_MINUTES
                 valueFrom:
                   configMapKeyRef:
                     name: p03-config
                     key: cycle_interval
             volumeMounts:
               - name: data
                 mountPath: /data
             livenessProbe:
               httpGet:
                 path: /health
                 port: 8080
               initialDelaySeconds: 60
               periodSeconds: 30
             readinessProbe:
               httpGet:
                 path: /ready
                 port: 8080
               initialDelaySeconds: 30
               periodSeconds: 10
         volumes:
           - name: data
             persistentVolumeClaim:
               claimName: p03-data-pvc
   ```

2. **ConfigMap**:

   ```yaml
   # k8s/p03-configmap.yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: p03-config
   data:
     cycle_interval: "90"
     batch_size: "1000"
     log_level: "INFO"
     feature_flags: |
       P03_FF_DREAM_EXPLORATION=true
       P03_FF_KG_CONSTRUCTION=true
       P03_FF_OBSERVABILITY_VERBOSE=false
   ```

3. **PersistentVolumeClaim**:

   ```yaml
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: p03-data-pvc
   spec:
     accessModes:
       - ReadWriteOnce
     resources:
       requests:
         storage: 10Gi
     storageClassName: fast-ssd
   ```

4. **Service** (for metrics scraping):

   ```yaml
   apiVersion: v1
   kind: Service
   metadata:
     name: p03-consolidation
   spec:
     selector:
       app: p03-consolidation
     ports:
       - name: metrics
         port: 9090
         targetPort: 9090
       - name: health
         port: 8080
         targetPort: 8080
   ```

---

#### Issue 9.1.3: Environment Configuration

**What to Cover**:

1. **Environment Variables** (per Dossier Section 16):

   > **PostgreSQL Migration Note** (2025-01): Database path replaced with PostgreSQL settings.
   > Connection settings inherited from K0 kernel (`K0_POSTGRES_*` prefix).

   | Variable | Default | Description |
   |----------|---------|-------------|
   | `K0_POSTGRES_HOST` | `localhost` | PostgreSQL host (via k0/config/postgres.py) |
   | `K0_POSTGRES_PORT` | `5432` | PostgreSQL port |
   | `K0_POSTGRES_DB` | `k0_kernel` | Database name |
   | `P03_CYCLE_INTERVAL_MINUTES` | `90` | Sleep cycle interval |
   | `P03_BATCH_SIZE` | `1000` | Events per batch |
   | `P03_LOG_LEVEL` | `INFO` | Logging level |
   | `P03_METRICS_PORT` | `9090` | Prometheus metrics port |
   | `P03_HEALTH_PORT` | `8080` | Health check port |

2. **Feature Flags**:

   | Flag | Default | Description |
   |------|---------|-------------|
   | `P03_FF_DREAM_EXPLORATION` | `false` | Enable R5 REM phase |
   | `P03_FF_KG_CONSTRUCTION` | `true` | Enable R4 KG building |
   | `P03_FF_INLINE_EMBEDDING` | `false` | Bypass P08 coordination |
   | `P03_FF_OBSERVABILITY_VERBOSE` | `false` | Detailed metrics |

3. **Secrets Management**:

   ```yaml
   # k8s/p03-secrets.yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: p03-secrets
   type: Opaque
   data:
     db_encryption_key: <base64-encoded>
     k0_bus_password: <base64-encoded>
   ```

4. **Configuration Loader**:

   ```python
   # k0/pipelines/p03/config.py
   from pydantic_settings import BaseSettings

   class P03Config(BaseSettings):
       db_path: str = "/data/p03.db"
       cycle_interval_minutes: int = 90
       batch_size: int = 1000
       log_level: str = "INFO"
       metrics_port: int = 9090
       health_port: int = 8080

       # Feature flags
       ff_dream_exploration: bool = False
       ff_kg_construction: bool = True
       ff_inline_embedding: bool = False
       ff_observability_verbose: bool = False

       class Config:
           env_prefix = "P03_"
   ```

---

### Epic 9.2: Observability

> **Dossier Reference**: Section R8.3 (Metrics Emission), Performance Budgets
> **Dashboard Reference**: docs/observability/grafana_dashboards/p03_consolidation.json
> **Alerting Reference**: k0/obs/ for Prometheus integration patterns

#### Issue 9.2.1: Grafana Dashboard - P03 Health

**What to Cover**:

1. **Dashboard ID**: D-P03-001
2. **Dashboard Panels**:

   | Panel | Query | Visualization |
   |-------|-------|---------------|
   | Cycle Success Rate | `sum(rate(p03_cycle_complete_total[5m])) / sum(rate(p03_cycle_started_total[5m]))` | Gauge (target: >95%) |
   | Cycle Latency P50/P95/P99 | `histogram_quantile(0.95, p03_cycle_total_duration_seconds_bucket)` | Time series |
   | Active Cycles | `p03_active_cycles` | Stat |
   | Events Processed/Hour | `sum(rate(p03_events_processed_total[1h])) * 3600` | Time series |
   | Phase Duration Breakdown | `p03_R0_duration_seconds` ... `p03_R8_duration_seconds` | Stacked area |
   | Error Rate | `rate(p03_consolidation_errors_total[5m])` | Time series |

3. **Time Ranges**: 1h, 6h, 24h, 7d selectable

4. **Dashboard JSON Structure**:

   ```json
   {
     "title": "P03 Consolidation Health",
     "uid": "p03-health",
     "tags": ["p03", "consolidation", "health"],
     "panels": [
       {
         "title": "Cycle Success Rate",
         "type": "gauge",
         "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0},
         "targets": [...]
       }
     ],
     "templating": {
       "list": [
         {"name": "tenant_id", "type": "query"},
         {"name": "space_id", "type": "query"}
       ]
     }
   }
   ```

---

#### Issue 9.2.2: Grafana Dashboard - Memory Growth

**What to Cover**:

1. **Dashboard ID**: D-P03-002
2. **Dashboard Panels**:

   | Panel | Query | Visualization |
   |-------|-------|---------------|
   | st_epi Row Count | `p03_st_epi_row_count` | Time series |
   | st_sem Row Count | `p03_st_sem_row_count` | Time series |
   | st_procedural Row Count | `p03_st_procedural_row_count` | Time series |
   | st_kg_dom Node Count | `p03_st_kg_dom_row_count` | Time series |
   | st_kg_edges Edge Count | `p03_st_kg_edges_row_count` | Time series |
   | Total Storage (MB) | `p03_storage_bytes_total / 1024 / 1024` | Stat |
   | Growth Rate/Day | `delta(p03_st_epi_row_count[1d])` | Bar gauge |

3. **Layer Breakdown Table**:

   ```sql
   -- Query for per-layer metrics
   SELECT
     layer_name,
     row_count,
     avg_row_size_bytes,
     total_size_mb
   FROM p03_layer_stats
   ORDER BY total_size_mb DESC
   ```

4. **Alerts Integration**:
   - Alert when growth rate > 10%/day sustained for 7 days
   - Alert when total storage > 80% of quota

---

#### Issue 9.2.3: Grafana Dashboard - Pattern Analysis

**What to Cover**:

1. **Dashboard ID**: D-P03-003
2. **Dashboard Panels**:

   | Panel | Query | Visualization |
   |-------|-------|---------------|
   | Clusters Formed | `sum(rate(p03_clusters_formed_total[1h])) * 3600` | Time series |
   | Patterns Detected | `sum(rate(p03_patterns_detected_total[1h])) * 3600` | Time series |
   | Avg Cluster Confidence | `avg(p03_cluster_confidence_score)` | Gauge |
   | Avg Pattern Confidence | `avg(p03_pattern_confidence_score)` | Gauge |
   | Reconciliation Decisions | `sum by (decision_type) (rate(p03_reconciliation_decisions_total[1h]))` | Pie chart |

3. **Decision Type Breakdown**:

   ```promql
   # Per decision type
   p03_reconciliation_decisions_total{decision_type="REINFORCE"}
   p03_reconciliation_decisions_total{decision_type="EXTEND"}
   p03_reconciliation_decisions_total{decision_type="CREATE"}
   p03_reconciliation_decisions_total{decision_type="EVOLVE"}
   p03_reconciliation_decisions_total{decision_type="CONTRADICT"}
   p03_reconciliation_decisions_total{decision_type="SUPERSEDE"}
   ```

4. **Quality Heatmap**: Novelty vs Importance score distribution

---

#### Issue 9.2.4: Grafana Dashboard - Active Learning

**What to Cover**:

1. **Dashboard ID**: D-P03-004
2. **Dashboard Panels**:

   | Panel | Query | Visualization |
   |-------|-------|---------------|
   | Gaps Detected | `sum(rate(p03_gaps_detected_total[1h])) * 3600` | Time series |
   | Gap Queue Depth | `p03_gap_queue_depth` | Gauge (target: <500) |
   | P06 Response Rate | `rate(p06_gap_responses_total[1h]) / rate(p03_gaps_detected_total[1h])` | Gauge |
   | Anchor Count | `p03_anchor_count` | Stat |
   | Anchor Drift Rate | `rate(p03_anchor_drift_total[1h])` | Time series |
   | Entropy Distribution | `histogram_quantile(0.5, p03_anchor_entropy_bucket)` | Histogram |

3. **Gap Type Breakdown**:

   ```promql
   sum by (gap_type) (p03_gaps_detected_total)
   # gap_type: missing_routine, timing_deviation, entity_absence, etc.
   ```

4. **Learning Loop Health**: P03 → P06 → P03 round-trip latency

---

#### Issue 9.2.5: Prometheus Alerting Rules - Critical

**What to Cover**:

1. **Alert Rules File**: `prometheus/rules/p03_critical.yml`

   ```yaml
   groups:
     - name: p03_critical
       rules:
         - alert: P03CycleFailureHigh
           expr: |
             (
               sum(rate(p03_cycle_failed_total[5m]))
               / sum(rate(p03_cycle_started_total[5m]))
             ) > 0.05
           for: 5m
           labels:
             severity: critical
             pipeline: p03
           annotations:
             summary: "P03 cycle failure rate > 5%"
             description: "{{ $value | printf \"%.2f\" }}% of cycles failing"
             runbook_url: "docs/runbooks/RB-P03-001.md"

         - alert: P03TruthWriteFailure
           expr: rate(p03_r7_write_errors_total[1m]) > 0.01
           for: 1m
           labels:
             severity: critical
             pipeline: p03
           annotations:
             summary: "P03 R7 truth write failures detected"
             description: "Data integrity at risk - immediate action required"
             runbook_url: "docs/runbooks/RB-P03-002.md"

         - alert: P03DLQOverflow
           expr: p03_dlq_depth > 1000
           for: 5m
           labels:
             severity: critical
             pipeline: p03
           annotations:
             summary: "P03 Dead Letter Queue depth > 1000"
             description: "DLQ depth: {{ $value }}"
             runbook_url: "docs/runbooks/RB-P03-003.md"

         - alert: P03CircuitBreakerOpen
           expr: p03_p08_circuit_breaker_open == 1
           for: 5m
           labels:
             severity: critical
             pipeline: p03
           annotations:
             summary: "P08 circuit breaker open"
             description: "P08 embedding service unavailable"
             runbook_url: "docs/runbooks/RB-P03-004.md"

         - alert: P03LockContention
           expr: p03_lock_wait_seconds > 60
           for: 2m
           labels:
             severity: critical
             pipeline: p03
           annotations:
             summary: "P03 lock contention detected"
             description: "Lock wait time: {{ $value }}s"
             runbook_url: "docs/runbooks/RB-P03-005.md"
   ```

---

#### Issue 9.2.6: Prometheus Alerting Rules - Warning

**What to Cover**:

1. **Alert Rules File**: `prometheus/rules/p03_warning.yml`

   ```yaml
   groups:
     - name: p03_warning
       rules:
         - alert: P03CycleLatencyHigh
           expr: |
             histogram_quantile(0.95, rate(p03_cycle_total_duration_seconds_bucket[5m])) > 300
           for: 15m
           labels:
             severity: warning
             pipeline: p03
           annotations:
             summary: "P03 cycle P95 latency > 5 minutes"
             description: "P95 latency: {{ $value | printf \"%.0f\" }}s"
             runbook_url: "docs/runbooks/RB-P03-011.md"

         - alert: P03BacklogGrowing
           expr: p03_pending_events > 10000
           for: 30m
           labels:
             severity: warning
             pipeline: p03
           annotations:
             summary: "P03 pending event backlog > 10K"
             description: "Backlog: {{ $value }} events"
             runbook_url: "docs/runbooks/RB-P03-010.md"

         - alert: P03MemoryPressure
           expr: p03_memory_usage_mb > 400
           for: 10m
           labels:
             severity: warning
             pipeline: p03
           annotations:
             summary: "P03 memory usage > 400MB"
             description: "Current: {{ $value }}MB, limit: 500MB"

         - alert: P03GapQueueFull
           expr: p03_gap_queue_depth > 400
           for: 30m
           labels:
             severity: warning
             pipeline: p03
           annotations:
             summary: "P03 gap queue depth > 400"
             description: "Gap queue may overflow (max 500)"

         - alert: P03AnchorDriftHigh
           expr: rate(p03_anchor_drift_total[1h]) > 0.1
           for: 1h
           labels:
             severity: warning
             pipeline: p03
           annotations:
             summary: "P03 anchor drift rate > 10%/hour"
             description: "Belief system unstable"

         - alert: P03LowThroughput
           expr: rate(p03_events_processed_total[1h]) * 60 < 500
           for: 2h
           labels:
             severity: warning
             pipeline: p03
           annotations:
             summary: "P03 throughput < 500 events/min"
             description: "Target: 1000 events/min"
   ```

---

#### Issue 9.2.7: Distributed Tracing Integration

**What to Cover**:

1. **Jaeger Span Hierarchy**:

   ```
   p03.consolidation.cycle (root)
   ├── p03.phase.R0.trigger_detection
   ├── p03.phase.R1.hippocampal_replay
   │   ├── p03.batch.selection
   │   └── p03.salience.scoring
   ├── p03.phase.R2.neocortical_integration
   │   ├── p03.clustering.dbscan
   │   └── p03.pattern.extraction
   ├── p03.phase.R3.synaptic_homeostasis
   │   ├── p03.deduplication
   │   └── p03.retention.enforcement
   ├── p03.phase.R4.kg_consolidation
   │   ├── p03.entity.resolution
   │   └── p03.relationship.discovery
   ├── p03.phase.R5.dream_exploration
   │   └── p03.counterfactual.generation
   ├── p03.phase.R6.update_staging
   ├── p03.phase.R7.write_memory_layers
   │   ├── p03.write.st_epi
   │   ├── p03.write.st_sem
   │   └── p03.write.st_kg
   └── p03.phase.R8.event_emission
       ├── p03.emit.consolidation_complete
       └── p03.emit.metrics
   ```

2. **Span Attributes**:

   ```python
   # OpenTelemetry integration
   from opentelemetry import trace

   tracer = trace.get_tracer("p03.consolidation")

   async def run_consolidation_cycle(cycle_id: str, batch_size: int):
       with tracer.start_as_current_span("p03.consolidation.cycle") as span:
           span.set_attribute("cycle_id", cycle_id)
           span.set_attribute("batch_size", batch_size)
           span.set_attribute("tenant_id", tenant_id)
           span.set_attribute("space_id", space_id)

           # Baggage for downstream propagation
           span.set_baggage("p03.cycle_id", cycle_id)
   ```

3. **Baggage Items**:
   - `cycle_id`: Unique cycle identifier
   - `batch_size`: Number of events in batch
   - `tenant_id`: Multi-tenant isolation
   - `space_id`: Space isolation

4. **Sampling Strategy**: 10% sampling rate, 100% for errors

---

### Epic 9.3: Runbooks

> **Dossier Reference**: Section R8 (Event Emission), Error Handling patterns
> **Runbook Location**: docs/runbooks/
> **On-Call Reference**: docs/runbooks/on-call-checklist.md

#### Issue 9.3.1: Create P03 Runbook Index

**What to Cover**:

1. **Runbook Index File**: `docs/runbooks/P03_RUNBOOK_INDEX.md`

   ```markdown
   # P03 Consolidation Runbooks

   ## Critical Alerts (Immediate Response Required)

   | ID | Alert | Runbook | Owner |
   |----|-------|---------|-------|
   | RB-P03-001 | P03CycleFailureHigh | [Link](RB-P03-001.md) | SRE |
   | RB-P03-002 | P03TruthWriteFailure | [Link](RB-P03-002.md) | SRE |
   | RB-P03-003 | P03DLQOverflow | [Link](RB-P03-003.md) | SRE |
   | RB-P03-004 | P03CircuitBreakerOpen | [Link](RB-P03-004.md) | SRE |
   | RB-P03-005 | P03LockContention | [Link](RB-P03-005.md) | SRE |

   ## Warning Alerts (30-minute Response)

   | ID | Alert | Runbook | Owner |
   |----|-------|---------|-------|
   | RB-P03-010 | P03BacklogGrowing | [Link](RB-P03-010.md) | SRE |
   | RB-P03-011 | P03CycleLatencyHigh | [Link](RB-P03-011.md) | SRE |
   | RB-P03-012 | P03MemoryPressure | [Link](RB-P03-012.md) | SRE |
   | RB-P03-013 | P03GapQueueFull | [Link](RB-P03-013.md) | SRE |
   | RB-P03-014 | P03AnchorDriftHigh | [Link](RB-P03-014.md) | SRE |
   | RB-P03-015 | P03LowThroughput | [Link](RB-P03-015.md) | SRE |
   ```

2. **Runbook Template**:

   ```markdown
   # RB-P03-XXX: Alert Name

   ## Alert Details
   - **Severity**: CRITICAL | WARNING
   - **Alert Name**: P03AlertName
   - **Dashboard**: [Link to dashboard]

   ## Impact
   [Description of user/system impact]

   ## Symptoms
   - Symptom 1
   - Symptom 2

   ## Diagnosis Steps
   1. Step 1
   2. Step 2

   ## Resolution Steps
   1. Step 1
   2. Step 2

   ## Escalation
   - Level 1: SRE on-call
   - Level 2: P03 team lead
   - Level 3: Engineering manager

   ## Prevention
   [How to prevent recurrence]
   ```

---

#### Issue 9.3.2: Runbook RB-P03-001 - High Cycle Failure Rate

**What to Cover**:

1. **Alert**: P03CycleFailureHigh (>5% failure rate for 5m)

2. **Impact**:
   - Memory consolidation blocked
   - Truth table staleness increasing
   - User experience degraded (stale patterns)

3. **Diagnosis Steps**:

   ```bash
   # 1. Check recent cycle logs
   kubectl logs -l app=p03-consolidation --tail=100 | grep -E "ERROR|FAILED"

   # 2. Check phase failure distribution
   curl http://p03-metrics:9090/api/v1/query?query=p03_phase_errors_total

   # 3. Check database connectivity
   python -c "from k0.storage import check_db; check_db()"

   # 4. Check K0 Bus connectivity
   python -c "from k0.bus import check_bus; check_bus()"
   ```

4. **Resolution Steps**:
   - If DB connection failure: Restart database pod, verify PVC
   - If Bus failure: Check K0 bus health, restart service
   - If schema validation: Check for data corruption, rollback batch
   - If resource exhaustion: Scale up pod resources

---

#### Issue 9.3.3: Runbook RB-P03-002 - R7 Truth Write Failure

**What to Cover**:

1. **Alert**: P03TruthWriteFailure (write errors in R7 phase)

2. **Impact**:
   - **CRITICAL**: Data integrity at risk
   - Consolidated memories not persisted
   - Potential data loss

3. **Diagnosis Steps**:

   ```bash
   # 1. Check R7 error logs
   kubectl logs -l app=p03-consolidation | grep "r7_write_error"

   # 2. Check database disk space
   df -h /var/lib/postgresql/data

   # 3. Check for blocking queries and locks
   psql -h $K0_POSTGRES_HOST -U $K0_POSTGRES_USER -d $K0_POSTGRES_DB -c "
     SELECT pid, usename, state, query, wait_event_type, wait_event
     FROM pg_stat_activity
     WHERE state != 'idle' AND datname = current_database();
   "

   # 4. Check outbox status
   python -c "from k0.outbox import check_outbox; check_outbox()"
   ```

4. **Resolution Steps**:
   - If disk full: Clean archived data, expand PVC
   - If table locked: Kill blocking transactions, restart pod
   - If schema mismatch: Run migrations, verify column presence
   - **ALWAYS**: Verify data integrity after resolution

---

#### Issue 9.3.4: Runbook RB-P03-003 - DLQ Overflow

**What to Cover**:

1. **Alert**: P03DLQOverflow (DLQ depth > 1000)

2. **Impact**:
   - Failed events accumulating
   - Memory pressure on DLQ storage
   - Potential event loss if DLQ full

3. **Diagnosis Steps**:

   ```bash
   # 1. Check DLQ message distribution
   python -c "from k0.dlq import analyze_dlq; analyze_dlq('p03')"

   # 2. Identify error patterns
   SELECT error_type, COUNT(*) FROM p03_dlq GROUP BY error_type ORDER BY COUNT(*) DESC;

   # 3. Check oldest DLQ message age
   SELECT MIN(created_at) FROM p03_dlq;
   ```

4. **Resolution Steps**:
   - Identify root cause from error patterns
   - Fix underlying issue (schema, connectivity, etc.)
   - Replay DLQ messages in batches of 100
   - Monitor success rate during replay

---

#### Issue 9.3.5: Runbook RB-P03-004 - Circuit Breaker Open

**What to Cover**:

1. **Alert**: P03CircuitBreakerOpen (P08 unavailable)

2. **Impact**:
   - P03 cannot coordinate embeddings with P08
   - If P03_FF_INLINE_EMBEDDING=false: Cycle blocked
   - If P03_FF_INLINE_EMBEDDING=true: Continue with stale embeddings

3. **Diagnosis Steps**:

   ```bash
   # 1. Check P08 health
   curl http://p08-embedding:8080/health

   # 2. Check circuit breaker state
   python -c "from k0.circuit import get_state; get_state('p08')"

   # 3. Check P08 error logs
   kubectl logs -l app=p08-embedding --tail=50
   ```

4. **Resolution Steps**:
   - If P08 down: Restart P08 pod, check resources
   - If network issue: Check service mesh, DNS resolution
   - Temporary workaround: Enable P03_FF_INLINE_EMBEDDING=true
   - Reset circuit breaker after P08 recovery

---

#### Issue 9.3.6: Runbook RB-P03-010 - Pending Event Backlog

**What to Cover**:

1. **Alert**: P03BacklogGrowing (>10K pending events)

2. **Impact**:
   - Consolidation falling behind ingestion rate
   - Stale truth table
   - Eventually consistent queries return old data

3. **Diagnosis Steps**:

   ```bash
   # 1. Check event ingestion rate vs processing rate
   rate(p02_events_ingested_total[1h]) vs rate(p03_events_processed_total[1h])

   # 2. Check cycle duration trend
   avg_over_time(p03_cycle_total_duration_seconds[24h])

   # 3. Check batch size effectiveness
   p03_batch_size vs p03_events_processed_per_cycle
   ```

4. **Resolution Steps**:
   - Increase batch size: P03_BATCH_SIZE=2000
   - Reduce cycle interval: P03_CYCLE_INTERVAL_MINUTES=60
   - Scale up resources: +50% CPU, +50% memory
   - Temporarily disable R5 (dream exploration)

---

#### Issue 9.3.7: Runbook RB-P03-011 - High Cycle Latency

**What to Cover**:

1. **Alert**: P03CycleLatencyHigh (P95 > 300s)

2. **Impact**:
   - Consolidation cycles taking longer than expected
   - May indicate performance regression
   - Could lead to backlog if sustained

3. **Diagnosis Steps**:

   ```bash
   # 1. Identify slowest phase
   SELECT phase, AVG(duration_seconds) FROM p03_phase_metrics GROUP BY phase ORDER BY AVG DESC;

   # 2. Check for slow queries (requires pg_stat_statements extension)
   psql -h $K0_POSTGRES_HOST -U $K0_POSTGRES_USER -d $K0_POSTGRES_DB -c "
     SELECT query, calls, mean_exec_time, total_exec_time
     FROM pg_stat_statements
     WHERE query LIKE '%st_%'
     ORDER BY mean_exec_time DESC
     LIMIT 10;
   "

   # 3. Check embedding query latency (P08)
   histogram_quantile(0.95, p08_query_duration_seconds_bucket)
   ```

4. **Resolution Steps**:
   - If R2 slow: Reduce DBSCAN depth, increase eps parameter
   - If R4 slow: Limit entity resolution candidates
   - If R7 slow: Increase write batch size
   - If P08 slow: Scale P08 or enable inline embedding

---

#### Issue 9.3.8: On-Call Checklist

**What to Cover**:

1. **Shift Start Checklist**:

   ```markdown
   ## P03 On-Call Shift Start

   - [ ] Review P03 Health dashboard (D-P03-001)
   - [ ] Check current alert status (no firing alerts)
   - [ ] Verify last cycle completed successfully
   - [ ] Check pending event backlog (<5K normal)
   - [ ] Review handoff notes from previous shift
   - [ ] Verify runbook access
   - [ ] Confirm escalation contacts available
   ```

2. **During Shift Monitoring**:

   ```markdown
   ## Hourly Checks

   - [ ] Cycle success rate >95%
   - [ ] P95 latency <5 minutes
   - [ ] DLQ depth <100
   - [ ] Memory usage <400MB
   - [ ] No critical alerts firing
   ```

3. **Shift End Handoff**:

   ```markdown
   ## P03 On-Call Shift End

   - [ ] Document any incidents
   - [ ] Document any config changes
   - [ ] Note any concerning trends
   - [ ] Prepare handoff notes
   - [ ] Notify incoming on-call
   ```

---

### Epic 9.4: Production Rollout

> **Dossier Reference**: Section 12.4 (Feature Flags), Section 16 (Configuration)
> **Rollout Reference**: docs/deployment/ for staged rollout patterns
> **Feature Flag Reference**: k0/config/feature_flags.py

#### Issue 9.4.1: Feature Flag Configuration

**What to Cover**:

1. **P03 Feature Flag Master List**:

   | Flag | Default | Stage 1 | Stage 2 | Production |
   |------|---------|---------|---------|------------|
   | `P03_FF_ENABLED` | false | true | true | true |
   | `P03_FF_DREAM_EXPLORATION` | false | false | true | true |
   | `P03_FF_KG_CONSTRUCTION` | true | true | true | true |
   | `P03_FF_INLINE_EMBEDDING` | false | true | false | false |
   | `P03_FF_OBSERVABILITY_VERBOSE` | true | true | false | false |
   | `P03_FF_DEDUPLICATION` | true | true | true | true |
   | `P03_FF_RETENTION_ENFORCEMENT` | false | false | true | true |
   | `P03_FF_GAP_DETECTION` | false | false | true | true |
   | `P03_FF_ANCHOR_UPDATES` | false | false | false | true |

2. **Feature Flag Implementation**:

   ```python
   # k0/pipelines/p03/feature_flags.py
   from k0.config import FeatureFlags

   class P03FeatureFlags(FeatureFlags):
       """P03 Consolidation feature flags."""

       prefix = "P03_FF_"

       # Core pipeline
       ENABLED = "P03_FF_ENABLED"
       DREAM_EXPLORATION = "P03_FF_DREAM_EXPLORATION"
       KG_CONSTRUCTION = "P03_FF_KG_CONSTRUCTION"

       # Optimization
       INLINE_EMBEDDING = "P03_FF_INLINE_EMBEDDING"
       DEDUPLICATION = "P03_FF_DEDUPLICATION"
       RETENTION_ENFORCEMENT = "P03_FF_RETENTION_ENFORCEMENT"

       # Active learning
       GAP_DETECTION = "P03_FF_GAP_DETECTION"
       ANCHOR_UPDATES = "P03_FF_ANCHOR_UPDATES"

       # Observability
       OBSERVABILITY_VERBOSE = "P03_FF_OBSERVABILITY_VERBOSE"

       @classmethod
       def is_r5_enabled(cls) -> bool:
           """Check if R5 (Dream Exploration) is enabled."""
           return cls.is_enabled(cls.DREAM_EXPLORATION)

       @classmethod
       def should_skip_p08(cls) -> bool:
           """Check if inline embedding mode (skip P08)."""
           return cls.is_enabled(cls.INLINE_EMBEDDING)
   ```

3. **Flag Toggle API**:

   ```python
   # Runtime flag toggle via K0 CLI
   from k0.cli import toggle_feature_flag

   # Enable dream exploration
   await toggle_feature_flag("P03_FF_DREAM_EXPLORATION", True)

   # Check flag state
   state = await get_feature_flag_state("P03_FF_DREAM_EXPLORATION")
   ```

4. **Flag Audit Logging**:
   - Log all flag changes with timestamp, actor, old/new value
   - Alert on critical flag changes (ENABLED, KG_CONSTRUCTION)

---

#### Issue 9.4.2: Staged Rollout Plan

**What to Cover**:

1. **Rollout Stages**:

   | Stage | % Traffic | Duration | Success Criteria |
   |-------|-----------|----------|------------------|
   | Canary | 1% | 24h | Error rate <1%, latency P95 <5min |
   | Stage 1 | 10% | 48h | Error rate <2%, no critical alerts |
   | Stage 2 | 50% | 72h | Error rate <3%, backlog stable |
   | Production | 100% | - | All SLOs met |

2. **Canary Deployment**:

   ```yaml
   # k8s/p03-canary.yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: p03-consolidation-canary
     labels:
       app: p03-consolidation
       track: canary
   spec:
     replicas: 1
     selector:
       matchLabels:
         app: p03-consolidation
         track: canary
     template:
       metadata:
         labels:
           app: p03-consolidation
           track: canary
         annotations:
           traffic.sidecar.istio.io/includeInboundPorts: ""
       spec:
         containers:
           - name: p03
             image: familyos/p03-consolidation:canary
             env:
               - name: P03_CANARY_MODE
                 value: "true"
   ```

3. **Traffic Splitting** (Istio VirtualService):

   ```yaml
   apiVersion: networking.istio.io/v1beta1
   kind: VirtualService
   metadata:
     name: p03-consolidation
   spec:
     hosts:
       - p03-consolidation
     http:
       - route:
           - destination:
               host: p03-consolidation
               subset: stable
             weight: 90
           - destination:
               host: p03-consolidation
               subset: canary
             weight: 10
   ```

4. **Stage Promotion Criteria**:

   ```markdown
   ## Promotion Checklist

   - [ ] Error rate below threshold for duration
   - [ ] No critical alerts fired
   - [ ] P95 latency within SLO
   - [ ] No data integrity issues
   - [ ] Memory usage stable
   - [ ] Backlog not growing
   - [ ] Approval from on-call SRE
   - [ ] Approval from P03 team lead
   ```

5. **Rollout Automation**:

   ```bash
   # Promote canary to 10%
   kubectl set env deployment/p03-consolidation P03_ROLLOUT_STAGE=1

   # Promote to 50%
   kubectl set env deployment/p03-consolidation P03_ROLLOUT_STAGE=2

   # Promote to 100%
   kubectl set env deployment/p03-consolidation P03_ROLLOUT_STAGE=3
   ```

---

#### Issue 9.4.3: Rollback Procedure

**What to Cover**:

1. **Rollback Triggers**:

   | Trigger | Threshold | Auto-Rollback |
   |---------|-----------|---------------|
   | Error Rate | >5% for 5m | Yes |
   | P95 Latency | >10min for 15m | Yes |
   | Data Integrity | Any R7 failure | Yes |
   | Critical Alert | Firing for 10m | Manual |
   | Backlog Growth | >50K events | Manual |

2. **Automatic Rollback**:

   ```yaml
   # Argo Rollouts configuration
   apiVersion: argoproj.io/v1alpha1
   kind: Rollout
   metadata:
     name: p03-consolidation
   spec:
     strategy:
       canary:
         steps:
           - setWeight: 10
           - pause: {duration: 1h}
           - setWeight: 50
           - pause: {duration: 2h}
           - setWeight: 100
         analysis:
           templates:
             - templateName: p03-success-rate
           startingStep: 1
         autoRollbackOnError: true
   ```

3. **Manual Rollback Steps**:

   ```bash
   # 1. Stop P03 consolidation
   kubectl scale deployment p03-consolidation --replicas=0

   # 2. Rollback to previous version
   kubectl rollout undo deployment/p03-consolidation

   # 3. Verify rollback
   kubectl rollout status deployment/p03-consolidation

   # 4. Resume consolidation
   kubectl scale deployment p03-consolidation --replicas=1

   # 5. Monitor for stability
   watch -n 10 "kubectl logs -l app=p03-consolidation --tail=5"
   ```

4. **Data Recovery** (if R7 failure occurred):

   ```sql
   -- 1. Identify affected batch
   SELECT batch_id, started_at, status
   FROM p03_consolidation_batches
   WHERE status = 'FAILED'
   ORDER BY started_at DESC
   LIMIT 1;

   -- 2. Rollback partial writes
   DELETE FROM st_epi WHERE batch_id = '<failed_batch_id>';
   DELETE FROM st_sem WHERE batch_id = '<failed_batch_id>';
   DELETE FROM st_kg_dom WHERE batch_id = '<failed_batch_id>';

   -- 3. Reset event consolidation status
   UPDATE st_hipp_events
   SET consolidation_status = 'PENDING'
   WHERE batch_id = '<failed_batch_id>';
   ```

5. **Post-Rollback Actions**:
   - Create incident report
   - Identify root cause
   - Fix issue in development
   - Re-run rollout from canary

---

### Epic 9.5: K0 Architecture Master - Final Update

> **Reference**: k0/pipelines/k0_architecture_master.md
> **ADR Reference**: docs/architecture/decisions-K0/
> **Gate**: GATE 5 (Documentation of Change)

#### Issue 9.5.1: Update Pipeline Status to Production

**What to Cover**:

1. **Pipeline Master Registry Update** (Part 2.1):

   ```markdown
   | ID | Name | Status | Owner | README | Last Updated |
   |----|------|--------|-------|--------|--------------|
   | P03 | Consolidation | 🚀 Production | P03 Team | [Link](k0/pipelines/p03/README.md) | 2025-XX-XX |
   ```

2. **Status Transitions**:
   - 📝 Planning → 📋 ADR Complete → ✅ Implemented → 🚀 Production

3. **Production Readiness Checklist**:

   ```markdown
   ## P03 Production Readiness

   - [x] All ADRs accepted
   - [x] All contracts defined and validated
   - [x] Integration tests passing
   - [x] Performance tests passing
   - [x] Golden dataset tests passing
   - [x] Observability dashboards deployed
   - [x] Alerting rules deployed
   - [x] Runbooks created
   - [x] On-call rotation established
   - [x] Staged rollout completed
   - [x] SLOs defined and baselined
   ```

---

#### Issue 9.5.2: Update ADR Status to Implemented

**What to Cover**:

1. **P03 ADR Index Update** (Part 7.1):

   | ADR ID | Title | Status | Implemented |
   |--------|-------|--------|-------------|
   | k010.1 | P03 Sleep Cycle Architecture | ✅ Accepted → Implemented | 2025-XX-XX |
   | k010.2 | P03 Phase Pipeline (R0-R8) | ✅ Accepted → Implemented | 2025-XX-XX |
   | k010.3 | P03 Pattern Extraction | ✅ Accepted → Implemented | 2025-XX-XX |
   | k010.4 | P03 KG Construction | ✅ Accepted → Implemented | 2025-XX-XX |
   | k010.5 | P03 Reconciliation Strategy | ✅ Accepted → Implemented | 2025-XX-XX |
   | k010.6 | P03 P08 Coordination | ✅ Accepted → Implemented | 2025-XX-XX |
   | k010.7 | P03 Gap Detection | ✅ Accepted → Implemented | 2025-XX-XX |

2. **ADR File Updates**:

   ```markdown
   ## Status

   ~~Accepted~~ → **Implemented**

   ## Implementation Date

   2025-XX-XX

   ## Implementation Notes

   - Implemented in Epic X.Y
   - Tests: tests/integration/test_p03_*.py
   - Coverage: XX%
   ```

---

#### Issue 9.5.3: Update Performance Budgets

**What to Cover**:

1. **Actual Measurements** (Part 8.1):

   | Metric | Budget | Actual (P50) | Actual (P95) | Status |
   |--------|--------|--------------|--------------|--------|
   | Cycle Duration | 90 min | TBD | TBD | TBD |
   | Throughput | 1000 events/min | TBD | TBD | TBD |
   | Memory Peak | 500 MB | TBD | TBD | TBD |
   | R2 Latency | 200ms P95 | TBD | TBD | TBD |
   | R4 Latency | 300ms P95 | TBD | TBD | TBD |
   | R7 Latency | 150ms P95 | TBD | TBD | TBD |

2. **Baseline Establishment**:

   ```python
   # Run performance baseline
   pytest tests/performance/test_p03_*.py --benchmark-json=baseline.json

   # Store baseline in registry
   python -m k0.cli.perf store_baseline --pipeline=p03 --file=baseline.json
   ```

3. **Regression Detection**:
   - CI job compares against baseline
   - Alert if P95 regresses >10%

---

#### Issue 9.5.4: Update Test Requirements Matrix

**What to Cover**:

1. **Coverage Achieved** (Part 8.2):

   | Test Type | Required | Achieved | Gap |
   |-----------|----------|----------|-----|
   | Unit Tests | 80% | TBD | TBD |
   | Integration Tests | 70% | TBD | TBD |
   | Contract Tests | 100% | TBD | TBD |
   | Performance Tests | All budgets | TBD | TBD |
   | Golden Dataset | 6 decision types | TBD | TBD |

2. **Test File Mapping**:

   | Epic | Test Files | Line Count |
   |------|------------|------------|
   | M1 | tests/integration/test_p03_trigger.py | TBD |
   | M2 | tests/integration/test_p03_pattern.py | TBD |
   | M3 | tests/integration/test_p03_dedup.py | TBD |
   | M4 | tests/integration/test_p03_kg.py | TBD |
   | M5 | tests/integration/test_p03_reconcile.py | TBD |
   | M6 | tests/integration/test_p03_write.py | TBD |
   | M7 | tests/integration/test_p03_event.py | TBD |
   | M8 | tests/performance/test_p03_perf.py | TBD |

3. **Coverage Report Integration**:

   ```yaml
   # .github/workflows/coverage.yml
   - name: Generate Coverage Report
     run: |
       pytest tests/k0/p03/ --cov=k0/pipelines/p03 --cov-report=xml
       python -m k0.cli.coverage update_matrix --pipeline=p03
   ```

#### Issue 9.5.3: Update Performance Budgets

<!-- Part 8.1: Actual measurements -->

#### Issue 9.5.4: Update Test Requirements Matrix

<!-- Part 8.2: Coverage achieved -->

---

## Appendix A: Module Registry Summary

| Module ID | Name | Phase | Dossier Section |
|-----------|------|-------|-----------------|
| M18 | EpisodeClusterer | R2 | 7.4.1 |
| M19 | DuplicateDetector | R3 | 7.4.2 |
| M20 | RetentionEnforcer | R3 | 7.4.3 |
| M21 | KGConsolidator | R4 | 7.4.4 |
| M22 | DreamExplorer | R5 | 7.4.5 |
| M23 | ReplayCoordinator | R1 | 7.4.6 |
| M24 | TruthWriter | R7 | 7.4.7 |
| M25 | GapDetector | R8 | 7.4.8 |

---

## Appendix B: Event Topics Summary

| Topic | Phase | Purpose |
|-------|-------|---------|
| p03.consolidation.triggered.v1 | R0 | Cycle start notification |
| p03.batch.selected.v1 | R1 | Batch selection complete |
| p03.cluster.formed.v1 | R2 | Clustering complete |
| p03.pattern.detected.v1 | R2 | Pattern extracted |
| p03.memories.updated.v1 | R7 | Truth writes complete |
| p03.kg.updated.v1 | R4 | KG changes |
| p03.consolidation.complete.v1 | R8 | Cycle complete |
| p03.gap.detected.v1 | R8 | P06 gap notification |

---

## Appendix C: Storage Tables Summary

| Table | Purpose | Dossier Section |
|-------|---------|-----------------|
| st_hipp_events | Staging (P02 input) | 6.2 |
| st_epi | Episodic memory | 6.3 |
| st_sem | Semantic patterns | 6.4 |
| st_procedural | Habits/routines | 6.5 |
| st_social | Relationships | 6.6 |
| st_prospective | Intentions | 6.7 |
| st_kg_dom | KG entities | 6.8 |
| st_kg_edges | KG relationships | 6.9 |
| st_vec | Embeddings | 6.10 |
| st_learning_queue | P06 gap queue | 6.11 |
| st_anchors | Bayesian beliefs | 6.12 |
| st_anchor_observations | Evidence log | 6.13 |
| consolidation_locks | Concurrency | Epic 0.2 |

---

## Appendix D: ADR Index

| ADR | Title | Status |
|-----|-------|--------|
| k010 | P03 Consolidation Architecture | Draft |
| k010.1 | Sleep Cycle Scheduling | Draft |
| k010.2 | Importance Scoring | Draft |
| k010.3 | Episodic Clustering | Draft |
| k010.4 | Bidirectional Truth Reconciliation | Draft |
| k010.5 | Near-Duplicate Detection | Draft |
| k010.6 | Entity Normalization | Draft |
| k010.7 | 8-Layer Memory Write Coordination | Draft |
| k010.8 | P08 Embedding Coordination | Draft |
| k010.9 | Capability-Based Security | Draft |
| k010.10 | P06 Active Learning Integration | Draft |

---

## Appendix E: Feature Flags

| Flag | Default | Purpose |
|------|---------|---------|
| P03_FF_R5_MODE | disabled | Enable dream exploration phase |
| P03_FF_PARALLEL_R3_R4 | enabled | Run R3/R4 in parallel |
| P03_FF_P06_INTEGRATION | enabled | Emit gaps to P06 |
| P03_FF_ANCHOR_UPDATES | enabled | Update Bayesian anchors |
| P03_FF_BACKPRESSURE_CHECK | enabled | Check P08 queue depth |
| P03_FF_CONTRADICT_COMMIT | enabled | Commit contradictions at reduced confidence |
| P03_FF_MULTIMODAL_ANCHORS | enabled | Allow multiple modes per entity |
| P03_FF_AUDIT_FULL | disabled | Full audit trail for all decisions |
| P03_FF_DRY_RUN | disabled | Execute without truth writes |

---

## Appendix F: Algorithm Reference (Appendix C Summary)

<!-- Detailed specs in dossier Appendix C -->

| Algorithm | Used In | Purpose |
|-----------|---------|---------|
| C.1 Cosine Similarity | R2, R3 | Episode clustering, duplicate detection |
| C.2 Bayesian Confidence | R7 | Truth merge confidence calculation |
| C.3 Optimistic Locking | R7 | Concurrent write protection |
| C.4 Importance Scoring | R1 | Replay priority calculation |
| C.5 Hebbian Learning | R4 | Edge strength updates |
| C.6 DBSCAN | R2 | Density-based episode clustering |
| C.7 Centroid Calculation | R2 | Cluster centroid for st_epi.embedding |
| C.8 SimHash | R3 | Near-duplicate fingerprinting |
| C.9 Exponential Decay | R3 | Retention curve calculation |
| C.10 Novelty Scoring | R3 | Uniqueness quantification |
| C.11 UltraBERT NER | R4 | Entity extraction (via P02) |
| C.12 Granger Causality | R4 | Temporal relationship inference |
| C.13 CPN | R5 | Counterfactual processing |
| C.14 TPN-MCTS | R5 | Temporal prediction |
| C.15 BGT-SM | R5 | Remote associations |
| C.16 TDL-HCO | R5 | Hierarchical coherence |
| C.17 Shannon Entropy | R8 | Gap detection via uncertainty |
| C.18 Beta Distribution | R8 | Confidence interval estimation |
| C.19 Token Bucket | ALL | K0 QoS rate limiting |
| C.20 SPC-UQ | R2 | Uncertainty quantification |
| C.21 Exponential Backoff | ALL | Error retry timing |
| C.22 WFQ | ALL | Weighted fair queueing |
| C.23 FAISS IVF | R2, R3 | Vector similarity search |

---

## Appendix G: K0 Integration Points (Appendix D Summary)

<!-- Per dossier Appendix D - K0 Kernel Integration Blueprint -->

| K0 Layer | Integration Point | P03 Usage |
|----------|-------------------|-----------|
| Layer 2: Policy | PolicyEngine | Privacy band checks, ACL validation |
| Layer 3: Transaction | UoW | R7 atomic truth writes |
| Layer 4: Storage | TruthStore, DLQStore | All truth tables, error recovery |
| Layer 5: QoS | TokenBucket | Phase budget enforcement |
| Layer 6: Bus | EventBus, Outbox | R8 event emission |
| Layer 7: Fabric | CapabilityFabric | 28 capability checks |
| Layer 8: Drivers | P02Driver, P08Driver | Data consumption, embedding queries |
| Layer 9: Observability | MetricsRegistry, TracingProvider | Prometheus, spans |
| Layer 10: Infrastructure | ConfigRegistry, Scheduler | Trigger scheduling, config |

---

## Appendix H: State Machine Reference (Appendix G Summary)

<!-- Per dossier Appendix G - R0-R8 State Machine Specification -->

| Phase | Idempotency Key | Timeout | DLQ Condition |
|-------|-----------------|---------|---------------|
| R0 | cycle_id | 60s | Lock acquisition fails 3x |
| R1 | batch_hash | 300s | Importance scoring timeout |
| R2 | cluster_run_id | 600s | DBSCAN memory overflow |
| R3 | dedup_run_id | 300s | SimHash batch failure |
| R4 | kg_run_id | 300s | Entity normalization timeout |
| R5 | dream_run_id | 1800s | CPN/TPN timeout (optional) |
| R6 | staging_write_id | 120s | Status update failure |
| R7 | truth_write_id | 600s | Version conflict 5x |
| R8 | finalize_id | 60s | Event emission failure |

---

## Appendix I: SLO Reference (Section 17 Summary)

<!-- Per dossier Section 17.3 -->

| SLO ID | Metric | Target | Alert Threshold |
|--------|--------|--------|-----------------|
| SLO-P03-001 | Cycle success rate | 99.5% | < 95% |
| SLO-P03-002 | Cycle latency P95 | 300s | > 600s |
| SLO-P03-005 | Truth write success | 99.9% | < 99% |
| SLO-P03-010 | DLQ depth | < 100 | > 500 |
| SLO-P03-015 | Backlog age | < 24h | > 12h |
| SLO-P03-020 | Memory utilization | < 80% | > 90% |

---

## Appendix J: Threshold Configuration (Appendix F Summary)

<!-- Per dossier Appendix F -->

| Threshold | Min | Default | Max | Phase |
|-----------|-----|---------|-----|-------|
| CLUSTER_EPS | 0.1 | 0.25 | 0.5 | R2 |
| CLUSTER_MIN_SAMPLES | 2 | 3 | 10 | R2 |
| SIMHASH_THRESHOLD | 3 | 5 | 8 | R3 |
| DECAY_HALF_LIFE_DAYS | 30 | 90 | 365 | R3 |
| NOVELTY_MIN | 0.1 | 0.3 | 0.5 | R3 |
| HEBBIAN_LEARNING_RATE | 0.01 | 0.1 | 0.5 | R4 |
| CONFIDENCE_PENALTY | 0.1 | 0.3 | 0.5 | R7 |
| GAP_QUEUE_MAX_DEPTH | 100 | 500 | 2000 | R8 |
| GAP_PRIORITY_FLOOR | 0.1 | 0.3 | 0.5 | R8 |

---

## Changelog

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-12-21 | Dev Team | Initial skeleton from dossier v2.3.0 |
| 1.1.0 | 2025-12-21 | Dev Team | Enhanced with dossier Sections 11-17, Appendices C-H |

### v1.1.0 Enhancements

**New Epics Added:**

- Epic 1.6: Error Handling Infrastructure (from Section 13)
- Epic 1.7: Security & Privacy Infrastructure (from Section 14)
- Epic 1.8: Performance Tuning Infrastructure (from Section 15)

**New Issues Added:**

- Migration: st_consolidation_audit, st_dlq P03 entries, v1→v2 backfill
- ADR: k010.11 UltraBERT Data Consumption
- Issue 8.1.6: Error Recovery Integration Tests
- Issues 8.2.5-8.2.7: QoS, Embedding, PostgreSQL performance tests
- Issues 6.3.9-6.3.10: Optimistic Locking, Confidence Merging
- Runbooks: RB-P03-001 through RB-P03-011 with specific IDs

**New Appendices:**

- Appendix F: Algorithm Reference (23 algorithms from Appendix C)
- Appendix G: K0 Integration Points (10 layers from Appendix D)
- Appendix H: State Machine Reference (R0-R8 from Appendix G)
- Appendix I: SLO Reference (from Section 17)
- Appendix J: Threshold Configuration (from Appendix F)

**Enhanced Details:**

- Feature Flags: Added 4 new flags (9 total)
- Blockers: Added UltraBERT, DLQ, QoS Scheduler dependencies
- Epic 6.3: Detailed R7 writer implementation notes
- Epic 8.1: Detailed reconciliation decision test cases
- Epic 8.2: Performance test targets and methodology
- Epic 9.2: Dashboard and alerting rule specifications
