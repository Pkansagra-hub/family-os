# P03 Consolidation Pipeline - Production Implementation Plan

**Status**: Planning Phase
**Version**: 2.1.0
**Created**: 2025-01-21
**Updated**: 2025-12-14
**Owner**: Development Team
**Related Dossier**: [P03_consolidation_dossier.md](../pipelines/P03_consolidation_dossier.md)
**Upstream Pipeline**: P02 (Episodic Memory Formation)
**Master Tracking**: [whiteboard.md](../../k0/pipelines/whiteboard.md)
**Governance Document**: [k0_architecture_master.md](../../k0/pipelines/k0_architecture_master.md)

---

## K0 Architecture Master Registration Requirements

> **CRITICAL**: Before any implementation begins, P03 must be registered in the K0 Architecture Master document.
> This is the SOURCE OF TRUTH for all K0 pipelines and modules. Updates are MANDATORY at each lifecycle stage.

### Required K0 Architecture Master Updates

| Milestone | K0 Section to Update | Update Required |
|-----------|---------------------|-----------------|
| M0 Start | Part 2.1: Pipeline Master Registry | Add P03 row with status 📝 Design |
| M0 Complete | Part 7.1: ADR Index | Add all P03 ADRs (k010.x series) |
| M1 Start | Part 2.1: Pipeline Master Registry | Update status to 🎯 Planning |
| M1 Complete | Part 4.1: Event Topics Registry | Add all P03 events (p03.*.v1) |
| M1 Complete | Part 5.1: Global Contract Registry | Add all P03 contracts |
| M1 Complete | Part 5.2: Syscall Matrix | Add P03 storage operations |
| M1 Complete | Part 3.1: Module Master Registry | Add consolidation module entry |
| M2-M7 Start | Part 2.1: Pipeline Master Registry | Update status to ⚠️ Implementation |
| M8 Complete | Part 8.1: Performance Budgets | Add P03 performance targets |
| M8 Complete | Part 8.2: Test Requirements Matrix | Add P03 test coverage |
| M9 Complete | Part 2.1: Pipeline Master Registry | Update status to ✅ Production |
| M9 Complete | Part 8.3: Observability Hooks | Add P03 metrics/alerts |

### K0 Architecture Master Update Checklist (Per Phase)

Use this checklist before marking any milestone complete:

- [ ] Pipeline Registry status updated (Part 2.1)
- [ ] ADR Index updated with new decisions (Part 7.1)
- [ ] Module Registry updated if modules added (Part 3.1)
- [ ] Event Topics Registry updated if events added (Part 4.1)
- [ ] Contract Registry updated if schemas added (Part 5.1)
- [ ] Syscall Matrix updated if storage operations added (Part 5.2)
- [ ] Cross-references validated (pipeline → modules, events → consumers)
- [ ] Version bumped in K0 Architecture Master header

### K0 Architecture Master Quick Reference

**Document Location**: [`k0/pipelines/k0_architecture_master.md`](../../k0/pipelines/k0_architecture_master.md)

| Part | Section Name | P03 Impact | When to Update |
|------|--------------|------------|----------------|
| **2.1** | Pipeline Master Registry | P03 row status | M0 (Design), M1 (Planning), M2 (Implementation), M9 (Production) |
| **3.1** | Module Master Registry | 37 consolidation modules | M2-M7 (as modules implemented) |
| **4.1** | Event Topics Registry | 4 event types (p03.*.v1) | M1 (contract definition), M7 (event emission) |
| **5.1** | Global Contract Registry | 28+ module contracts | M1 (all contracts) |
| **5.2** | Syscall Matrix | 28 capabilities (st_* read/write) | M1 (capabilities), M2-M7 (validation) |
| **5.3** | Storage Contract Definitions | 10 new tables (st_epi, st_sem, etc.) | M1 (migrations) |
| **7.1** | ADR Index | 12 ADRs (k010-k010.11) | M0 (batch registration) |
| **8.1** | Performance Budgets | 90-minute cycle target | M8 (testing), M9 (production) |
| **8.2** | Test Requirements Matrix | Unit/Integration/Performance coverage | M8 (testing) |
| **8.3** | Observability Hooks | Grafana dashboards, Prometheus alerts | M9 (deployment) |

### Current P03 Entry in K0 Architecture Master (Part 2.1)

```markdown
| P03 | Memory Consolidation | 🎯 Planning | ✅ Spec Complete | `docs/pipelines/P03_consolidation_dossier.md` | 37 modules (consolidation.*) | P1 | 0.2.0 | 2025-12-14 |
```

**Target End State**:

```markdown
| P03 | Memory Consolidation | ✅ Production | ✅ Deployed | `docs/pipelines/P03_consolidation_dossier.md` | 37 modules (consolidation.*) | P1 | 1.0.0 | 2025-XX-XX |
```

### K0 Closure Requirements (MANDATORY for Every Issue)

> **⚠️ CRITICAL**: No issue can be marked as closed until the K0 Architecture Master has been updated.
> This ensures the governance document remains the single source of truth.

**Issue Closure Checklist** (copy to each PR):

```markdown
## K0 Architecture Master Closure Checklist

- [ ] **Part 2.1 (Pipeline Registry)**: Status updated if pipeline state changed
- [ ] **Part 3.1 (Module Registry)**: New modules added with correct status
- [ ] **Part 4.1 (Event Topics)**: New events registered with schema location
- [ ] **Part 5.1 (Contract Registry)**: New contracts added with version
- [ ] **Part 5.2 (Syscall Matrix)**: New storage operations registered
- [ ] **Part 7.1 (ADR Index)**: ADR status updated (Draft→Accepted→Implemented)
- [ ] **Version Header**: Document version bumped (PATCH for updates, MINOR for new items)
- [ ] **Last Updated**: Date updated in document header
- [ ] **Cross-References**: All affected sections link correctly

**File**: `k0/pipelines/k0_architecture_master.md`
```

**Quick Reference - What Updates Apply to Each Issue Type**:

| Issue Type | K0 Sections to Update |
|------------|----------------------|
| **Migration** | Part 5.3 (Storage Tables) |
| **Contract** | Part 5.1 (Contract Registry) |
| **Module Implementation** | Part 3.1 (Module Registry), Part 5.2 (Syscalls) |
| **Event Implementation** | Part 4.1 (Event Topics) |
| **ADR Creation** | Part 7.1 (ADR Index) |
| **Testing Complete** | Part 8.2 (Test Requirements) |
| **Deployment** | Part 2.1 (Pipeline Status → Production) |

---

## Executive Summary

### Overview

This plan implements P03 (Memory Consolidation Pipeline) using the declarative YAML-based DAG architecture established in P02. P03 is an **offline, batch-processing pipeline** that transforms raw hippocampal events (from `st_hipp_events`) into durable, queryable memories across 8 memory layers.

### Production Scope

- **Input**: st_hipp_events (97 columns from P02)
- **Output**: 8 Memory Layers (st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_vec)
- **Batch Size**: 1000 events per consolidation cycle
- **Cycle Duration**: 90 minutes target
- **Phases**: R0-R8 (9 phases, 37 modules)

### Critical Blockers (Must Resolve First)

| Blocker | Type | Impact | Resolution |
|---------|------|--------|------------|
| P02 not production-ready | PREREQUISITE | Cannot start P03 | Wait for P02 stable |
| Migration 0024 not applied | PREREQUISITE | No st_hipp_events schema | Apply migration first |
| Budget mismatch (182 min vs 90 min) | ARCHITECTURE | Cycles take 3+ hours | Make R5 optional, parallelize R3/R4 |
| No consolidation_lock mechanism | ARCHITECTURE | Race conditions | Design lock table |
| P08 backpressure missing | INTEGRATION | Embedding queue overflow | Add queue depth limits |

---

## Pipeline-Fabric Integration Alignment

> **CRITICAL**: P03 is a **trigger-driven batch pipeline**, not an event-driven pipeline.
> This section ensures alignment with the [Pipeline-Fabric Integration Guide](../../k0/fabric/pipeline-fabric-integration-guide.md).

### P03 Pipeline Protocol Requirements

P03 implements `PipelineProtocol` with the following class-level attributes:

```python
class P03Consolidation:
    """Memory consolidation pipeline - trigger-driven batch processing."""

    # Protocol requirements (class-level)
    pipeline_id: str = "P03_CONSOLIDATION"
    contract_version: int = 1
    declared_topics: Sequence[str] = []  # Trigger-driven, NO bus subscription
    concurrency: int = 1                  # Sequential batch processing
    max_queue: int = 64                   # Low - trigger-driven, not queue-heavy
    required_caps: Sequence[str] = [
        "st_hipp_events.read",
        "st_hipp_events.write",
        "st_epi.write",
        "st_sem.write",
        "st_procedural.write",
        "st_social.write",
        "st_prospective.write",
        "st_kg_dom.write",
        "st_kg_edges.write",
        "st_vec.write",
        "st_outbox.write",
        "st_pipeline_processed.write",
        "consolidation_locks.write",
        # ... (28 total capabilities)
    ]

    # Trigger-driven method (NOT handle())
    async def execute(self, trigger_event: TriggerEvent) -> None:
        """Called when trigger fires - consolidation cycle."""
        cycle_id = generate_cycle_id()
        # ... batch processing logic

    # Lifecycle methods
    async def on_startup(self, ctx: PipelineContext) -> None:
        self._syscalls = ctx.syscalls
        self._fabric = ctx.fabric
        self._logger = ctx.logger

    async def on_shutdown(self) -> None:
        self._logger.info("P03 shutdown complete")
```

### Trigger-Driven vs Event-Driven

| Aspect | Event-Driven (P02) | Trigger-Driven (P03) |
|--------|-------------------|---------------------|
| **Activation** | Bus topic subscription | Scheduler triggers (IDLE, CRON, THRESHOLD) |
| **Method** | `handle(msg: BusMessage)` | `execute(trigger_event: TriggerEvent)` |
| **declared_topics** | Topic list | `[]` (empty) |
| **Latency Target** | P95 < 100ms | 90-minute batch cycle |
| **Concurrency** | 10-50 (IO-bound) | 1 (sequential batch) |

> **Note**: P03's 90-minute batch cycle is intentional. The Integration Guide's 100ms P95 guideline applies to event-driven pipelines, not batch consolidation.

### Concurrency Control: Dual-Lock Strategy

P03 uses two layers of concurrency control:

1. **SingleFlightGate** (Scheduler-level): Ensures at most one P03 execution at a time across the kernel
2. **ConsolidationLockManager** (Tenant-level): Ensures at most one consolidation per tenant/space

```
┌─────────────────────────────────────────────────────────────┐
│                      Trigger Fires                          │
│                           │                                 │
│                           ▼                                 │
│               ┌──────────────────────┐                     │
│               │   SingleFlightGate   │ ◄── Pipeline-level  │
│               │   (one P03 at a time)│                     │
│               └──────────┬───────────┘                     │
│                          │                                  │
│                          ▼                                  │
│               ┌──────────────────────┐                     │
│               │ ConsolidationLockMgr │ ◄── Tenant-level    │
│               │ (one per tenant/space)│                    │
│               └──────────┬───────────┘                     │
│                          │                                  │
│                          ▼                                  │
│               ┌──────────────────────┐                     │
│               │   execute(trigger)   │ ◄── Batch processing│
│               └──────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### Fabric Integration

P03 uses `CapabilityFabric` for module invocations:

```yaml
# p03_consolidation.v1.yaml
fabric_actions:
  - score_importance
  - cluster_episodes
  - extract_patterns
  - compute_novelty
  - normalize_entities
```

```python
# In execute()
if self._fabric and self._fabric.has_capability("score_importance"):
    scores = self._fabric.invoke(
        "score_importance",
        events=batch_events,
        timeout_ms=5000,
    )
```

### Event Emission via Outbox

P03 emits events using the transactional outbox pattern:

```python
# R8.1 - Use outbox_emit_batch() for transactional safety
await self._syscalls.outbox_emit_batch([
    {
        "topic": "p03.consolidation.complete.v1",
        "payload": json.dumps(cycle_summary),
        "trace_id": trigger_event.trace_id,
    },
    {
        "topic": "p03.pattern.detected.v1",
        "payload": json.dumps(pattern_results),
        "trace_id": trigger_event.trace_id,
    },
])
```

### P08 Coordination (No Deprecated Tables)

> **IMPORTANT**: `st_embedding_queue` is DEPRECATED. Use `st_vec.embedding_status` instead.

P03 creates vector placeholders in `st_vec` with `embedding_status='PENDING'`:

```python
# R7.7 - Vector placeholder creation (NO st_embedding_queue)
await self._syscalls.vec_write(
    embedding_id=generate_id(),
    source_layer="st_epi",
    source_id=episode_id,
    text_to_embed=episode_text,
    embedding_status="PENDING",  # P08 will populate
)
# Emit event for P08 to pick up
await self._syscalls.outbox_emit_batch([{
    "topic": "cognitive.embedding.requested.v1",
    "payload": json.dumps({"embedding_id": embedding_id}),
}])
```

### Hot Reload Support

P03's trigger configuration supports atomic hot reload via `PipelineScheduler.hot_reload()`:

```python
# Hot reload test case (M8)
async def test_p03_hot_reload():
    new_spec = load_updated_spec("p03_consolidation.v2.yaml")
    result = await scheduler.hot_reload(
        new_specs={"P03": new_spec},
        affected_pipelines={"P03"},
    )
    assert result.success
    assert result.updated == 1
```

---

## Timeline Overview

| Milestone | Duration | Focus |
|-----------|----------|-------|
| M0: Pre-Implementation | 3-4 days | Blockers, ADRs, Lock Design |
| M1: Infrastructure | 5-6 days | Migrations, Contracts, Pipeline YAML |
| M2: Core Consolidation (R0-R1) | 4-5 days | Trigger, Replay, Importance |
| M3: Pattern Extraction (R2) | 5-6 days | Clustering, Patterns, CA1 Bridge |
| M4: Synaptic Homeostasis (R3) | 4-5 days | Dedup, Novelty, Retention |
| M5: Knowledge Graph (R4) | 5-6 days | Entities, Relationships, Causal |
| M5A: Dream Exploration (R5) | 5-6 days | Counterfactuals, Scenarios, Insights (v2 feature) |
| M6: Memory Writers (R6-R7) | 5-6 days | State Updates, 8 Layer Writers |
| M7: Event Emission (R8) | 3-4 days | Events, Offsets, Metrics |
| M8: Integration & Testing | 5-6 days | E2E Tests, Performance, Production |
| M9: Deployment & Observability | 3-4 days | Docker, K8s, Grafana, Runbooks |
| **Total (v1 without R5)** | **~8-10 weeks** | |
| **Total (v2 with R5)** | **~10-11 weeks** | |

---

## Capability-Based Security Requirements

**CRITICAL**: P03 must follow the K0 capability-based security model established for P02.

### Key Principles

1. **Explicit Declaration**: All storage capabilities must be declared in `p03_consolidation.v1.yaml`
2. **Least Privilege**: Request only capabilities actually needed by P03 modules
3. **Fail-Closed**: Operations without declared capabilities raise `PermissionError`
4. **Audit Trail**: All capability checks logged with pipeline_id and trace_id

### Required Capabilities Matrix

P03 requires **28 capabilities** (11 read, 17 write) across:

- **8 Core Memory Layers**: st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_vec
- **9 Infrastructure Tables**: st_hipp_events, st_archives, st_consolidation_logs, st_event_canon_map, st_event_cluster_history, st_kg_snapshots, deletion_audit, st_outbox, st_pipeline_processed
- **7 Tombstone Tables**: st_*_tombstones for soft delete
- **2 P08 Coordination**: st_vec (embedding_status tracking) - **NOTE: st_embedding_queue is DEPRECATED**

See P03 dossier "Required Capabilities" section for complete list.

### Implementation Requirements

1. **Pipeline YAML**: Add `required_capabilities` field to `p03_consolidation.v1.yaml`
2. **Module Contracts**: Each module declares `side_effects: [read:table, write:table]`
3. **Syscalls Usage**: All storage operations use `context.syscalls.*()` methods
4. **Testing**: Verify `PermissionError` raised when capabilities missing

### Security Verification Checklist

- [ ] All 28 capabilities declared in pipeline YAML
- [ ] No universal capability grants in app.py (removed for P02, apply to P03)
- [ ] All P03 modules use syscalls adapter (not direct DB access)
- [ ] Unit tests verify PermissionError for missing capabilities
- [ ] ADR documents capability rationale (why each capability is needed)

---

## Milestone 0: Pre-Implementation (Blockers & Architecture)

**Goal**: Resolve all architectural blockers before writing any code.
**Duration**: 3-4 days
**Gate**: GATE 1 (Architectural Decision Validation) + GATE 2 (Contract Discovery)

### Epic 0.0: K0 Architecture Master Registration (MANDATORY FIRST STEP)

**Description**: Register P03 in the K0 Architecture Master governance document before any other work.

#### Issue 0.0.1: Register P03 in K0 Architecture Master - Pipeline Registry

**Type**: Governance
**Priority**: BLOCKER
**Assignee**: Tech Lead
**Labels**: `governance`, `k0-master`, `p03`, `mandatory`

**Description**:
Add P03 to the K0 Architecture Master document's Pipeline Master Registry (Part 2.1).
This MUST be done before any ADRs, contracts, or code are created.

**K0 Architecture Master Updates Required**:

1. **Part 2.1: Pipeline Master Registry** - Add row:

   | ID | Name | Status | Design Phase | README Location | Modules Used | Priority | Version | Last Updated |
   |----|------|--------|--------------|-----------------|--------------|----------|---------|--------------|
   | P03 | Consolidation | 📝 Design | 📝 Initial | `docs/pipelines/P03_consolidation_dossier.md` | M20 (Consolidation) | P0 | 0.1.0 | 2025-11-25 |

2. **Part 7.2: Open Design Questions** - Add P03 open questions from dossier

3. **Part 6.1: Phase-Based Planning** - Add P03 to implementation roadmap

**Acceptance Criteria**:

- [ ] P03 row added to Pipeline Master Registry (Part 2.1)
- [ ] Status set to 📝 Design
- [ ] Priority set to P0 (Critical - depends on P02)
- [ ] README Location points to dossier
- [ ] Open questions added to Part 7.2
- [ ] Roadmap updated in Part 6.1
- [ ] K0 Architecture Master version bumped (MINOR)

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md`

**Governance Rule**: Per K0 Architecture Master Rule 2 (Pre-Merge Checklist), this must be done BEFORE any other P03 work.

---

#### Issue 0.0.2: Create P03 Pipeline README from Template

**Type**: Documentation
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `documentation`, `p03`, `k0-master`

**Description**:
Create P03 README.md following the K0 Architecture Master Pipeline README Template (Part 2.2).

**Sections Required** (per K0 Rule 4):

1. Overview (Purpose, Brain Analog, Scope)
2. Design Dossier (Problem, Requirements, Flow)
3. Architecture (Module Dependencies, DAG)
4. Event Contracts (Subscribes, Publishes)
5. Storage & Syscalls
6. ADRs
7. Implementation Details
8. Testing Strategy
9. Observability
10. Performance Data
11. Open Questions
12. Production Operations
13. Future Work
14. References

**Acceptance Criteria**:

- [ ] README follows K0 template exactly
- [ ] All 14 sections present (can be TBD initially)
- [ ] Brain analog documented (Sleep Consolidation)
- [ ] Status set to 📝 Design
- [ ] Links to dossier and ADRs
- [ ] K0 Architecture Master Pipeline Registry README Location updated

**Files to Create**:

- `k0/pipelines/p03_consolidation/README.md`

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 2.1 - update README Location)

---

### Epic 0.1: Architectural Decision Records

**Description**: Create ADRs for all novel algorithms and architectural decisions.

#### Issue 0.1.1: Create Parent ADR k010 - P03 Consolidation Architecture

**Type**: ADR
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `architecture`, `adr`, `p03`

**Description**:
Create the parent ADR documenting overall P03 architecture including:

- Sleep cycle model (biological inspiration)
- Phase execution order (R0→R8)
- Performance budgets per phase
- Integration with K0 4-Port architecture

**Acceptance Criteria**:

- [ ] ADR follows project template (Status, Context, Decision, Alternatives, Consequences)
- [ ] References dossier sections for each phase
- [ ] Diagram showing phase dependencies
- [ ] Performance budget table (sum must be ≤90 min)
- [ ] **K0 MASTER**: ADR added to Part 7.1 ADR Index

**K0 Architecture Master Updates**:

- **Part 7.1: ADR Index** - Add entry:

  | ADR | Title | Status | Affects | Date | Owner |
  |-----|-------|--------|---------|------|-------|
  | ADR-k010 | P03 Consolidation Architecture | 🎯 Draft | P03 | 2025-11-25 | Tech Lead |

**Files to Create**:

- `docs/architecture/decisions-K0/k010_p03_consolidation_architecture.md`

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 7.1 - ADR Index)

---

#### Issue 0.1.2: Create ADR k010.1 - Sleep Cycle Scheduling Model

**Type**: ADR
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `architecture`, `adr`, `p03`, `r0`

**Description**:
Document the 4 trigger mechanisms and sleep cycle state machine:

- Idle trigger (5 min inactive + 100 pending)
- Scheduled trigger (cron 2AM-5AM)
- Threshold trigger (1000 events)
- Manual trigger (CLI/API)
- State machine: IDLE → NREM1 → NREM2 → REM → COMPLETE

**Complete Trigger Specifications (Per Pipeline-Fabric Integration Guide)**:

```yaml
# p03_consolidation.v1.yaml triggers section
triggers:
  # IDLE trigger - fires after 5 minutes of inactivity with pending events
  - id: consolidation_idle
    type: idle
    idle_seconds: 300
    min_pending: 100
    table: st_hipp_events
    condition: "consolidation_status IS NULL"

  # CRON trigger - nightly consolidation during sleep window
  - id: consolidation_nightly
    type: cron
    cron_expression: "0 2 * * *"  # 2 AM daily

  # THRESHOLD trigger - batch size reached
  - id: consolidation_threshold
    type: threshold
    table: st_hipp_events
    condition: "consolidation_status IS NULL"
    threshold_count: 1000
    check_interval_seconds: 60

  # MANUAL trigger - operator-initiated
  - id: consolidation_manual
    type: manual
```

**Acceptance Criteria**:

- [ ] State machine diagram with all transitions
- [ ] Trigger priority ordering documented
- [ ] Lock acquisition protocol defined
- [ ] Multi-tenant scheduling policy
- [ ] **IDLE trigger includes table/condition for min_pending**
- [ ] **CRON expression follows 5-field format**

**Files to Create**:

- `docs/architecture/decisions-K0/k010.1_sleep_cycle_scheduling.md`

---

#### Issue 0.1.3: Create ADR k010.2 - Importance Scoring Formula

**Type**: ADR
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `architecture`, `adr`, `p03`, `r1`

**Description**:
Document the importance scoring formula from R1.1:

```
importance = 0.35*emotional + 0.25*recency + 0.20*access + 0.20*social
```

**Acceptance Criteria**:

- [ ] Formula derivation explained
- [ ] Weight rationale from neuroscience research
- [ ] Edge cases documented (missing fields)
- [ ] Benchmark against manual ratings

**Files to Create**:

- `docs/architecture/decisions-K0/k010.2_importance_scoring.md`

---

#### Issue 0.1.4: Create ADR k010.3 - Episodic Clustering Algorithm

**Type**: ADR
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `architecture`, `adr`, `p03`, `r2`

**Description**:
Document clustering approach for R2.1:

- DBSCAN on semantic embeddings
- SimHash Hamming distance ≤5 for candidate filtering
- Jaccard similarity >0.8 for confirmation
- Composite distance: 60% semantic + 20% temporal + 10% location + 10% participant

**Acceptance Criteria**:

- [ ] Algorithm pseudocode
- [ ] Complexity analysis (O(n) with LSH vs O(n²) brute force)
- [ ] Threshold justification
- [ ] Scalability at 10k events

**Files to Create**:

- `docs/architecture/decisions-K0/k010.3_episodic_clustering.md`

---

#### Issue 0.1.5: Create ADR k010.4 - CA1 Bridge Merge/Evolve/Create Logic

**Type**: ADR
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `architecture`, `adr`, `p03`, `r2`

**Description**:
Document the CA1 bridge decision logic from R2.3:

- MERGE: similarity >0.85 → update existing semantic
- EVOLVE: similarity 0.6-0.85 → create new version, supersede old
- CREATE: similarity <0.6 → create new semantic

**Acceptance Criteria**:

- [ ] Decision tree diagram
- [ ] Similarity computation method (cosine on embeddings)
- [ ] Version management strategy
- [ ] Conflict resolution for concurrent modifications

**Files to Create**:

- `docs/architecture/decisions-K0/k010.4_ca1_bridge.md`

---

#### Issue 0.1.6: Create ADR k010.5 - Near-Duplicate Detection (SimHash)

**Type**: ADR
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `architecture`, `adr`, `p03`, `r3`

**Description**:
Document deduplication approach from R3.1:

- SimHash computation (64-bit fingerprint)
- Hamming distance ≤3 for near-duplicate detection
- MinHash LSH fallback for batches >1000
- Jaccard >0.8 confirmation threshold

**Acceptance Criteria**:

- [ ] SimHash algorithm implementation details
- [ ] Performance benchmarks (1000 vs 10000 events)
- [ ] False positive/negative analysis
- [ ] LSH bucket configuration

**Files to Create**:

- `docs/architecture/decisions-K0/k010.5_near_duplicate_detection.md`

---

#### Issue 0.1.7: Create ADR k010.6 - Entity Normalization Strategy

**Type**: ADR
**Priority**: Critical
**Assignee**: NLP Engineer
**Labels**: `architecture`, `adr`, `p03`, `r4`

**Description**:
Document entity resolution approach from R4.1:

- **READ from P02**: `st_hipp_events.entities_json` (UltraBERT NER: 9 general + 12 family entity types)
- NO spaCy calls — entities already extracted by P02 M02 via UltraBERT
- Levenshtein similarity >0.85 for fuzzy matching
- Alias tracking in entity_aliases_json
- Canonical node resolution protocol

**Acceptance Criteria**:

- [ ] Document P02 → P03 entities_json contract
- [ ] Fuzzy matching algorithm
- [ ] Pre-filtering with BK-tree for scalability
- [ ] Entity merge protocol

**Files to Create**:

- `docs/architecture/decisions-K0/k010.6_entity_normalization.md`

---

#### Issue 0.1.8: Create ADR k010.7 - 8-Layer Memory Write Coordination

**Type**: ADR
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `architecture`, `adr`, `p03`, `r7`

**Description**:
Document K0 driver integration for R7:

- Outbox pattern for transactional writes
- alias_map.yaml configuration for SQLite drivers
- Driver registration and discovery
- Transaction boundaries (R6 commit → R7 outbox → R8 events)

**Acceptance Criteria**:

- [ ] Sequence diagram: R7 → st_outbox → OutboxWorker → Driver
- [ ] alias_map.yaml example configuration
- [ ] Error handling for driver failures
- [ ] Retry semantics (exponential backoff)

**Files to Create**:

- `docs/architecture/decisions-K0/k010.7_memory_write_coordination.md`

---

#### Issue 0.1.9: Create ADR k010.8 - P08 Embedding Coordination Protocol

**Type**: ADR
**Priority**: High
**Assignee**: Tech Lead
**Labels**: `architecture`, `adr`, `p03`, `r7`, `p08`

**Description**:
Document P03→P08 coordination from R7.7:

- Placeholder creation in st_vec (embedding_status='PENDING')
- Job queue in st_embedding_queue
- Event-driven notification (cognitive.embedding.queued.v1)
- Backpressure mechanism (queue depth >10k → throttle)

**Acceptance Criteria**:

- [ ] Queue management protocol
- [ ] Priority levels (HIGH/MEDIUM/LOW)
- [ ] Backpressure thresholds
- [ ] Query Port behavior with PENDING embeddings
- [ ] **K0 MASTER**: ADR added to Part 7.1 ADR Index

**Files to Create**:

- `docs/architecture/decisions-K0/k010.8_p08_embedding_coordination.md`

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 7.1 - ADR Index)

---

#### Issue 0.1.9A: Create ADR k010.9 - Capability-Based Security Model

**Type**: ADR
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `architecture`, `adr`, `p03`, `security`

**Description**:
Document P03's capability-based security model following the pattern established in P02.

**Context**:
P03 requires access to 28 storage tables (8 core memory layers + 9 infrastructure + 7 tombstones + 2 P08 coordination). Without capability enforcement, P03 could:

- Access tables outside its responsibility
- Modify data owned by other pipelines
- Bypass audit trails
- Violate tenant isolation

**Decision**:
P03 follows K0 capability-based security model:

1. Declare all 28 capabilities in `p03_consolidation.v1.yaml`
2. Use `syscalls` adapter for ALL storage operations (no direct DB access)
3. Syscalls enforces capability checks before operations
4. PermissionError raised + logged for unauthorized access

**Alternatives Considered**:

1. ❌ Universal grant (like P02 before fix) - Security theater
2. ❌ Role-based access (pipeline = admin) - Too coarse-grained
3. ✅ Capability-based (chosen) - Least privilege, auditable

**Consequences**:

- ✅ Security: Prevents privilege escalation
- ✅ Audit: Every storage operation logged
- ✅ Testing: Can simulate missing capabilities
- ⚠️ Complexity: 28 capabilities to maintain

**Implementation Requirements**:

- Pipeline YAML must declare `required_capabilities: [...]`
- Module contracts must declare `side_effects: [read:table, write:table]`
- Syscalls adapter must check capabilities before operations
- Tests must verify PermissionError for unauthorized access

**Acceptance Criteria**:

- [ ] ADR documents capability model
- [ ] Complete list of 28 capabilities with rationale
- [ ] Security threat model (what attacks does this prevent?)
- [ ] Comparison with P02 capability list (similar patterns)
- [ ] **K0 MASTER**: ADR added to Part 7.1 ADR Index

**Files to Create**:

- `docs/architecture/decisions-K0/k010.9_capability_based_security.md`

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 7.1 - ADR Index)

---

#### Issue 0.1.10: Update K0 Architecture Master - Complete ADR Index for P03

**Type**: Governance
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `governance`, `k0-master`, `p03`

**Description**:
After all P03 ADRs (k010.x series) are created, ensure the K0 Architecture Master ADR Index is complete.

**K0 Architecture Master Updates Required**:

- **Part 7.1: ADR Index** - Add all 11 ADRs:

| ADR | Title | Status | Affects | Date | Owner |
|-----|-------|--------|---------|------|-------|
| ADR-k010 | P03 Consolidation Architecture | 🎯 Draft | P03 | 2025-11-25 | Tech Lead |
| ADR-k010.1 | Sleep Cycle Scheduling | 🎯 Draft | P03/R0 | 2025-11-25 | Tech Lead |
| ADR-k010.2 | Importance Scoring | 🎯 Draft | P03/R1 | 2025-11-25 | ML Engineer |
| ADR-k010.3 | Episodic Clustering | 🎯 Draft | P03/R2 | 2025-11-25 | ML Engineer |
| ADR-k010.4 | CA1 Bridge Logic | 🎯 Draft | P03/R2 | 2025-11-25 | Tech Lead |
| ADR-k010.5 | SimHash Deduplication | 🎯 Draft | P03/R3 | 2025-11-25 | ML Engineer |
| ADR-k010.6 | Entity Normalization (P02 Data) | 🎯 Draft | P03/R4 | 2025-11-25 | ML Engineer |
| ADR-k010.7 | 8-Layer Memory Write Coordination | 🎯 Draft | P03 | 2025-11-25 | Tech Lead |
| ADR-k010.8 | P08 Coordination | 🎯 Draft | P03/P08 | 2025-11-25 | Tech Lead |
| ADR-k010.9 | Capability-Based Security | 🎯 Draft | P03 | 2025-11-25 | Tech Lead |
| ADR-k010.10 | Dream Phase Algorithms | 🎯 Draft | P03/R5 | 2025-12-14 | ML Engineer |
| ADR-k010.11 | UltraBERT Data Consumption | 🎯 Draft | P03 | 2025-12-14 | Tech Lead |

> **ADR-k010.11 (UltraBERT Data Consumption)**: Documents that P03 does NOT load any NLP models.
> All NLP outputs (NER, sentiment, emotions, 768-dim embeddings) are pre-computed by P02 via
> UltraBERT single-pass and stored in `st_hipp_events` and `st_vec`. P03 reads these directly.

- **Part 2.1: Pipeline Master Registry** - Update P03 status to 🎯 Planning

**Acceptance Criteria**:

- [ ] All 12 ADRs listed in Part 7.1 ADR Index (k010 through k010.11)
- [ ] P03 status updated to 🎯 Planning
- [ ] Cross-references from ADRs to P03 validated
- [ ] K0 Architecture Master version bumped

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 7.1, Part 2.1)

---

### Epic 0.2: Resolve Architectural Blockers

**Description**: Fix critical architectural issues before implementation.

#### Issue 0.2.1: Design Consolidation Lock Mechanism

**Type**: Design
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `architecture`, `blocker`, `p03`

**Description**:
Design lock mechanism to prevent concurrent consolidation runs on same tenant/space.

**Problem Statement**:
Without locks, if scheduled trigger (2AM) + threshold trigger (1000 events) fire simultaneously:

- Race condition on st_hipp_events updates
- Duplicate memory layer writes
- Database deadlocks

**Dual-Lock Strategy (Per Pipeline-Fabric Integration Guide)**:

P03 uses two layers of concurrency control:

1. **SingleFlightGate** (Scheduler-level, from `k0/scheduler/concurrency.py`):
   - Built into PipelineScheduler
   - Ensures at most one P03 `execute()` call at a time
   - Uses OverlapPolicy.QUEUE for threshold/manual triggers
   - Automatic - no P03 code needed

2. **ConsolidationLockManager** (Tenant-level, custom):
   - Prevents concurrent consolidation for same tenant/space
   - Needed because one P03 execution may process multiple tenants
   - Uses consolidation_locks table with row-level locking

**Requirements**:

1. Tenant/space-level granularity
2. Lock acquisition timeout (30 seconds)
3. Lock release on completion or failure
4. Stale lock detection (>2 hours = stale)

**Proposed Solution**:

```sql
CREATE TABLE consolidation_locks (
    lock_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT DEFAULT 'ACTIVE', -- ACTIVE, RELEASED, EXPIRED
    UNIQUE(tenant_id, space_id, status) WHERE status = 'ACTIVE'
);
```

**Acceptance Criteria**:

- [ ] Lock table schema defined
- [ ] Lock acquisition protocol documented
- [ ] Stale lock cleanup mechanism
- [ ] Unit tests for race conditions

**Files to Create**:

- `k0/contracts/sql/migrations/0028_consolidation_locks.sql`
- `k0/modules/consolidation/lock_manager.py`

---

#### Issue 0.2.2: Resolve Budget Mismatch (182 min vs 90 min)

**Type**: Design
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `architecture`, `blocker`, `p03`, `performance`

**Description**:
Current phase budgets sum to 182 minutes but target is 90 minutes.

**Current Budgets**:

| Phase | Budget (min) | Notes |
|-------|--------------|-------|
| R0 | 2 | Lock + batch selection |
| R1 | 35 | Importance scoring |
| R2 | 45 | Clustering + patterns |
| R3 | 12 | Dedup + novelty |
| R4 | 30 | KG construction |
| R5 | 30 | Dream (optional) |
| R6 | 5 | State updates |
| R7 | 20 | Memory writes |
| R8 | 5 | Events + metrics |
| **Total** | **184** | **Over by 94 min** |

**Proposed Solution**:

1. Make R5 (Dream) optional - saves 30 min
2. Run R3 and R4 in parallel - saves ~30 min
3. Reduce R2 budget to 35 min through optimization

**Revised Budgets**:

| Phase | Budget (min) | Execution |
|-------|--------------|-----------|
| R0 | 2 | Serial |
| R1 | 25 | Serial |
| R2 | 35 | Serial |
| R3 | 10 | Parallel with R4 |
| R4 | 20 | Parallel with R3 |
| R5 | 0 | SKIP (v2) |
| R6 | 3 | Serial |
| R7 | 12 | Serial |
| R8 | 3 | Serial |
| **Total** | **90** | **On target** |

**Acceptance Criteria**:

- [ ] Revised budget approved in ADR k010
- [ ] Pipeline YAML updated with parallel_group for R3/R4
- [ ] R5 modules stubbed with skip logic
- [ ] Performance tests validate 90-min target

**Files to Update**:

- `docs/architecture/decisions-K0/k010_p03_consolidation_architecture.md`
- `k0/contracts/pipelines/p03_consolidation.v1.yaml`

---

#### Issue 0.2.3: Design P08 Backpressure Mechanism

**Type**: Design
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `architecture`, `blocker`, `p03`, `p08`

**Description**:
Without backpressure, if P08 is slow/down:

- st_embedding_queue grows unbounded
- Memory exhaustion
- Search features broken until queue drains

**Requirements**:

1. Queue depth monitoring
2. Throttling when depth >10,000
3. Alert when depth >5,000
4. Circuit breaker for P08 unavailability

**Proposed Solution**:

```python
async def check_embedding_backpressure():
    queue_depth = await get_embedding_queue_depth()

    if queue_depth > 10000:
        logger.warning("embedding_queue_overflow", depth=queue_depth)
        return BackpressureAction.PAUSE_CONSOLIDATION
    elif queue_depth > 5000:
        logger.warning("embedding_queue_high", depth=queue_depth)
        return BackpressureAction.REDUCE_BATCH_SIZE
    else:
        return BackpressureAction.CONTINUE
```

**Acceptance Criteria**:

- [ ] Backpressure thresholds documented
- [ ] R7.7 checks backpressure before writes
- [ ] Alert configuration for queue depth
- [ ] Circuit breaker for P08 health

**Files to Create**:

- `k0/modules/consolidation/backpressure.py`

---

### Epic 0.3: Pre-Implementation Validation

**Description**: Validate prerequisites before starting implementation.

#### Issue 0.3.1: Verify P02 Production Readiness

**Type**: Task
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `validation`, `prerequisite`, `p02`

**Description**:
Verify P02 is stable and writing correctly to st_hipp_events.

**Validation Checklist**:

- [ ] P02 pipeline YAML exists: `k0/contracts/pipelines/p02_write.v1.yaml`
- [ ] Migration 0024 applied: `st_hipp_events` table exists
- [ ] All 97 columns present with correct types
- [ ] P02 processing events without errors for >24 hours
- [ ] SimHash fingerprints populated (required for R3)
- [ ] Entities JSON populated (required for R4)

**Acceptance Criteria**:

- [ ] Checklist 100% complete
- [ ] Screenshot of st_hipp_events sample data
- [ ] P02 error rate <1% over 24 hours

---

#### Issue 0.3.2: Verify st_hipp_events Schema Alignment

**Type**: Task
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `validation`, `prerequisite`, `schema`

**Description**:
Verify 0024 migration matches dossier requirements.

**Required Columns (from dossier)**:

| Column | Type | P02 Writes | P03 Reads | P03 Updates |
|--------|------|------------|-----------|-------------|
| event_id | TEXT | ✅ | ✅ | |
| simhash_fingerprint | INTEGER | ✅ | ✅ | |
| minhash32 | TEXT | ✅ | ✅ | |
| entities_json | TEXT | ✅ | ✅ | |
| novelty_score | REAL | | | ✅ |
| near_duplicates_json | TEXT | | | ✅ |
| is_near_duplicate | INTEGER | | | ✅ |
| episode_cluster_id | TEXT | | | ✅ |
| cluster_confidence | REAL | | | ✅ |
| consolidation_status | TEXT | | | ✅ |
| importance_score | REAL | | | ✅ |
| access_count | INTEGER | | | ✅ |

**Missing Columns (need migration 0040)**:

- `consolidation_cycle_id TEXT`
- `archival_deadline TEXT`
- `consolidated_at TEXT`

**Acceptance Criteria**:

- [ ] All required columns exist
- [ ] Missing columns documented
- [ ] Migration 0029 created for additions

**Files to Create**:

- `k0/contracts/sql/migrations/0029_p03_hipp_events_additions.sql`

---

### Milestone 0 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 0 complete, verify these K0 updates:

**K0 Closure Checklist for M0**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 2.1 | Pipeline Registry | P03 row added with status 📝 Design | ☐ |
| 7.1 | ADR Index | All 12 ADRs (k010-k010.11) registered as 🎯 Draft | ☐ |
| 7.2 | Open Design Questions | P03 blockers added | ☐ |
| 6.1 | Implementation Roadmap | P03 phase added | ☐ |
| Header | Version | Bumped to next MINOR version | ☐ |

**Commit Message Format**: `docs(k0): M0 complete - P03 registered in K0 Architecture Master`

---

## Milestone 1: Infrastructure Setup

**Goal**: Create all database migrations, module contracts, and pipeline YAML.
**Duration**: 5-6 days
**Gate**: GATE 2 (Contract Discovery & Validation)

### Epic 1.1: Database Migrations

**Description**: Create migrations for all P03 output tables.

#### Issue 1.1.1: Create Migration 0041 - st_epi (Episodic Memory Layer)

**Type**: Migration
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`

**Description**:
Create episodic memory table for R7.1.

**Schema Requirements**:

```sql
CREATE TABLE st_epi (
    -- Identity
    episode_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,

    -- Temporal
    event_time_utc TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER DEFAULT 1,
    temporal_bucket TEXT,
    is_weekend INTEGER DEFAULT 0,
    recency_weight REAL DEFAULT 1.0,

    -- Content
    text TEXT NOT NULL,
    participants_json TEXT,
    location_name TEXT,
    activity_type TEXT,

    -- Affect
    sentiment_score REAL,
    salience_score REAL,

    -- Quality
    confidence_score REAL,
    source_count INTEGER DEFAULT 1,
    source_quality TEXT DEFAULT 'raw',
    ambiguity_score REAL DEFAULT 0.0,

    -- Fusion
    modalities_json TEXT,
    fusion_method TEXT,
    fusion_confidence REAL,
    source_events_json TEXT,

    -- Promotion
    promoted_to_semantic_id TEXT,
    promoted_to_routine_id TEXT,

    -- Lifecycle
    decay_factor REAL DEFAULT 1.0,
    archival_status TEXT DEFAULT 'ACTIVE',
    access_count INTEGER DEFAULT 0,

    -- Versioning
    version INTEGER DEFAULT 1,
    is_canonical INTEGER DEFAULT 1,
    supersedes_episode_id TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);

-- Indexes
CREATE INDEX idx_epi_tenant_time ON st_epi(tenant_id, event_time_utc);
CREATE INDEX idx_epi_space_actor ON st_epi(space_id, actor_id);
CREATE INDEX idx_epi_activity ON st_epi(activity_type, event_time_utc);
CREATE INDEX idx_epi_salience ON st_epi(salience_score DESC);
CREATE INDEX idx_epi_canonical ON st_epi(is_canonical) WHERE is_canonical = 1;
CREATE INDEX idx_epi_archival ON st_epi(archival_status);
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] All indexes created
- [ ] Foreign key constraint to st_hipp_events
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0030_st_epi.sql`

---

#### Issue 1.1.2: Create Migration 0031 - st_sem (Semantic Pattern Layer)

**Type**: Migration
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`

**Description**:
Create semantic pattern table for R7.2.

**Schema Requirements**:

```sql
CREATE TABLE st_sem (
    -- Identity
    semantic_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,

    -- Pattern Definition
    pattern_type TEXT NOT NULL, -- routine, preference, theme, relationship
    pattern_name TEXT NOT NULL,
    pattern_description TEXT,
    common_elements_json TEXT NOT NULL,

    -- Temporal
    temporal_context TEXT,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER DEFAULT 1,
    temporal_bucket TEXT,
    is_weekend INTEGER DEFAULT 0,
    recency_weight REAL DEFAULT 1.0,

    -- Recurrence
    pattern_frequency TEXT, -- daily, weekly, monthly, irregular
    recurrence_interval_days REAL,
    pattern_last_occurrence TEXT,
    next_predicted_time TEXT,

    -- Quality
    frequency_score REAL,
    confidence_score REAL NOT NULL,
    source_count INTEGER DEFAULT 1,
    source_quality TEXT DEFAULT 'derived',
    ambiguity_score REAL DEFAULT 0.0,

    -- Source Tracking
    modalities_json TEXT,
    source_episodes_json TEXT NOT NULL,
    invariants_json TEXT,
    variations_json TEXT,

    -- Lifecycle
    decay_factor REAL DEFAULT 1.0,
    archival_status TEXT DEFAULT 'ACTIVE',

    -- Versioning
    version INTEGER DEFAULT 1,
    is_canonical INTEGER DEFAULT 1,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    supersedes_semantic_id TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX idx_sem_tenant ON st_sem(tenant_id, space_id);
CREATE INDEX idx_sem_actor ON st_sem(actor_id);
CREATE INDEX idx_sem_pattern_type ON st_sem(pattern_type);
CREATE INDEX idx_sem_confidence ON st_sem(confidence_score DESC);
CREATE INDEX idx_sem_frequency ON st_sem(pattern_frequency);
CREATE INDEX idx_sem_valid ON st_sem(valid_from, valid_to);
CREATE INDEX idx_sem_canonical ON st_sem(is_canonical) WHERE is_canonical = 1;
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] All indexes created
- [ ] Versioning columns present
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0031_st_sem.sql`

---

#### Issue 1.1.3: Create Migration 0032 - st_procedural (Routines Layer)

**Type**: Migration
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`

**Description**:
Create procedural memory table for R7.3.

**Schema Requirements**:

```sql
CREATE TABLE st_procedural (
    -- Identity
    routine_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,

    -- Routine Definition
    routine_category TEXT NOT NULL, -- morning, evening, work, exercise, meal
    routine_name TEXT NOT NULL,
    description TEXT,
    trigger_conditions_json TEXT,
    action_sequence_json TEXT NOT NULL,

    -- Temporal
    temporal_context TEXT,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER DEFAULT 1,
    execution_count INTEGER DEFAULT 0,

    -- Performance
    completion_rate REAL,
    avg_duration_minutes REAL,
    frequency_score REAL,
    consistency_score REAL,
    streak_count INTEGER DEFAULT 0,

    -- Quality
    confidence_score REAL NOT NULL,
    skill_level TEXT DEFAULT 'novice', -- novice, intermediate, expert
    optimization_score REAL,
    bottleneck_analysis_json TEXT,

    -- Source Tracking
    source_episodes_json TEXT,

    -- Lifecycle
    decay_factor REAL DEFAULT 1.0,
    archival_status TEXT DEFAULT 'ACTIVE',

    -- Versioning
    version INTEGER DEFAULT 1,
    is_canonical INTEGER DEFAULT 1,
    valid_from TEXT NOT NULL,
    valid_to TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX idx_proc_tenant ON st_procedural(tenant_id, space_id);
CREATE INDEX idx_proc_actor ON st_procedural(actor_id);
CREATE INDEX idx_proc_category ON st_procedural(routine_category);
CREATE INDEX idx_proc_confidence ON st_procedural(confidence_score DESC);
CREATE INDEX idx_proc_canonical ON st_procedural(is_canonical) WHERE is_canonical = 1;
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] All indexes created
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0032_st_procedural.sql`

---

#### Issue 1.1.4: Create Migration 0033 - st_social (Social Relationships Layer)

**Type**: Migration
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`

**Description**:
Create social relationships table for R7.4.

**Schema Requirements**:

```sql
CREATE TABLE st_social (
    -- Identity
    relationship_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    related_person_id TEXT NOT NULL,

    -- Relationship Definition
    relationship_type TEXT NOT NULL, -- family, friend, colleague, acquaintance
    relationship_label TEXT,

    -- Interaction Metrics
    interaction_count INTEGER DEFAULT 0,
    first_interaction_at TEXT NOT NULL,
    last_interaction_at TEXT NOT NULL,
    interaction_frequency_days REAL,

    -- Communication
    communication_channels_json TEXT,
    dominant_channel TEXT,

    -- Strength Metrics
    relationship_strength REAL,
    sentiment_avg REAL,
    sentiment_trend TEXT, -- improving, stable, declining
    trust_score REAL,
    reciprocity_score REAL,

    -- Shared Context
    shared_activities_json TEXT,
    shared_locations_json TEXT,

    -- Source Tracking
    source_episodes_json TEXT,
    source_kg_edges_json TEXT,

    -- Lifecycle
    decay_factor REAL DEFAULT 1.0,
    archival_status TEXT DEFAULT 'ACTIVE',

    -- Versioning
    version INTEGER DEFAULT 1,
    is_canonical INTEGER DEFAULT 1,
    valid_from TEXT NOT NULL,
    valid_to TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Constraints
    UNIQUE(tenant_id, space_id, actor_id, related_person_id, is_canonical)
);

-- Indexes
CREATE INDEX idx_social_tenant ON st_social(tenant_id, space_id);
CREATE INDEX idx_social_actor ON st_social(actor_id);
CREATE INDEX idx_social_related ON st_social(related_person_id);
CREATE INDEX idx_social_type ON st_social(relationship_type);
CREATE INDEX idx_social_strength ON st_social(relationship_strength DESC);
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] All indexes created
- [ ] Unique constraint for actor-person pairs
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0033_st_social.sql`

---

#### Issue 1.1.5: Create Migration 0034 - st_prospective (Intentions Layer)

**Type**: Migration
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`

**Description**:
Create prospective memory table for R7.5.

**Schema Requirements**:

```sql
CREATE TABLE st_prospective (
    -- Identity
    prospective_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,

    -- Intention Definition
    intention_type TEXT NOT NULL, -- reminder, goal, prediction, scenario, insight
    intention_text TEXT NOT NULL,

    -- Trigger Conditions
    trigger_conditions_json TEXT,
    trigger_time_utc TEXT,
    trigger_location TEXT,
    trigger_context TEXT,

    -- Priority & Confidence
    priority REAL,
    confidence REAL,

    -- Predictions (from R5.2 TPN-MCTS)
    predicted_outcome TEXT,
    predicted_outcome_confidence REAL,
    alternative_scenarios_json TEXT,

    -- Insights (from R5.4 BGT-SM)
    insight_category TEXT, -- opportunity, warning, optimization
    surprise_score REAL,

    -- Source Tracking
    source_episodes_json TEXT,
    source_semantics_json TEXT,
    created_from_pipeline TEXT,

    -- Status
    status TEXT DEFAULT 'PENDING', -- PENDING, TRIGGERED, COMPLETED, EXPIRED
    triggered_at TEXT,
    completed_at TEXT,

    -- Versioning
    version INTEGER DEFAULT 1,
    is_canonical INTEGER DEFAULT 1,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX idx_prosp_tenant ON st_prospective(tenant_id, space_id);
CREATE INDEX idx_prosp_actor ON st_prospective(actor_id);
CREATE INDEX idx_prosp_type ON st_prospective(intention_type);
CREATE INDEX idx_prosp_trigger ON st_prospective(trigger_time_utc);
CREATE INDEX idx_prosp_status ON st_prospective(status);
CREATE INDEX idx_prosp_priority ON st_prospective(priority DESC);
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] All indexes created
- [ ] Status lifecycle documented
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0034_st_prospective.sql`

---

#### Issue 1.1.6: Create Migration 0035 - st_kg_dom (Knowledge Graph Nodes)

**Type**: Migration
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`, `r4`

**Description**:
Create knowledge graph nodes table for R7.6.

**Schema Requirements**:

```sql
CREATE TABLE st_kg_dom (
    -- Identity
    node_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- Entity Definition
    entity_type TEXT NOT NULL, -- Person, Place, Organization, Activity, Topic, Event
    entity_name TEXT NOT NULL,
    entity_aliases_json TEXT,
    entity_description TEXT,

    -- Observation Metrics
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER DEFAULT 1,

    -- Quality
    confidence_score REAL,

    -- Properties
    node_properties_json TEXT,

    -- Temporal Validity
    valid_from TEXT NOT NULL,
    valid_to TEXT,

    -- Source Tracking
    source_episodes_json TEXT,

    -- Lifecycle
    decay_factor REAL DEFAULT 1.0,
    archival_status TEXT DEFAULT 'ACTIVE',

    -- Versioning
    version INTEGER DEFAULT 1,
    is_canonical INTEGER DEFAULT 1,
    canonical_node_id TEXT,
    supersedes_node_id TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (canonical_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (supersedes_node_id) REFERENCES st_kg_dom(node_id)
);

-- Indexes
CREATE INDEX idx_kg_dom_tenant ON st_kg_dom(tenant_id, space_id);
CREATE INDEX idx_kg_dom_entity_type ON st_kg_dom(entity_type);
CREATE INDEX idx_kg_dom_entity_name ON st_kg_dom(entity_name);
CREATE INDEX idx_kg_dom_canonical ON st_kg_dom(is_canonical, canonical_node_id);
CREATE INDEX idx_kg_dom_valid ON st_kg_dom(valid_from, valid_to);
CREATE INDEX idx_kg_dom_observation ON st_kg_dom(observation_count DESC);
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] All indexes created
- [ ] Self-referential FKs for versioning
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0035_st_kg_dom.sql`

---

#### Issue 1.1.7: Create Migration 0036 - st_kg_edges (Knowledge Graph Edges)

**Type**: Migration
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`, `r4`

**Description**:
Create knowledge graph edges table for R7.6.

**Schema Requirements**:

```sql
CREATE TABLE st_kg_edges (
    -- Identity
    edge_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- Relationship Definition
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    edge_type TEXT NOT NULL, -- co_occurs_with, causes, enables, conflicts_with, part_of
    edge_label TEXT,

    -- Strength Metrics
    relationship_strength REAL DEFAULT 1.0,
    observation_count INTEGER DEFAULT 1,

    -- Quality
    confidence_score REAL,

    -- Temporal Validity
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,

    -- Causal Properties (from R4.4)
    is_causal INTEGER DEFAULT 0,
    causal_confidence REAL,
    temporal_lag_seconds REAL,

    -- Properties
    edge_properties_json TEXT,

    -- Source Tracking
    source_episodes_json TEXT,

    -- Lifecycle
    decay_factor REAL DEFAULT 1.0,
    archival_status TEXT DEFAULT 'ACTIVE',

    -- Versioning
    version INTEGER DEFAULT 1,
    is_canonical INTEGER DEFAULT 1,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (source_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (target_node_id) REFERENCES st_kg_dom(node_id)
);

-- Indexes
CREATE INDEX idx_kg_edges_tenant ON st_kg_edges(tenant_id, space_id);
CREATE INDEX idx_kg_edges_source ON st_kg_edges(source_node_id);
CREATE INDEX idx_kg_edges_target ON st_kg_edges(target_node_id);
CREATE INDEX idx_kg_edges_type ON st_kg_edges(edge_type);
CREATE INDEX idx_kg_edges_strength ON st_kg_edges(relationship_strength DESC);
CREATE INDEX idx_kg_edges_causal ON st_kg_edges(is_causal) WHERE is_causal = 1;
CREATE INDEX idx_kg_edges_valid ON st_kg_edges(valid_from, valid_to);
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] All indexes created
- [ ] Foreign keys to st_kg_dom
- [ ] Causal edge support
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0036_st_kg_edges.sql`

---

#### Issue 1.1.8: Create Migration 0037 - st_vec (Vector Embeddings)

**Type**: Migration
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`, `p08`

**Description**:
Create vector embeddings table for R7.7.

> **IMPORTANT**: Per Pipeline-Fabric Integration Guide §1.9, `st_embedding_queue` is **DEPRECATED**.
> P08 coordination uses `st_vec.embedding_status` column instead of a separate queue table.

**Schema Requirements**:

```sql
CREATE TABLE st_vec (
    -- Identity
    embedding_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- Source Reference
    source_layer TEXT NOT NULL, -- st_epi, st_sem, st_kg_dom, st_prospective
    source_id TEXT NOT NULL,

    -- Embedding Definition
    embedding_type TEXT DEFAULT 'text', -- text, image, audio
    text_to_embed TEXT NOT NULL,

    -- Vector Data
    vector_dimensions INTEGER DEFAULT 768,
    embedding_model TEXT DEFAULT 'ultrabert-768',  -- UltraBERT, not mpnet
    vector_data BLOB, -- NULL until P08 populates

    -- Status (used for P08 coordination - replaces deprecated st_embedding_queue)
    embedding_status TEXT DEFAULT 'PENDING', -- PENDING, PROCESSING, READY, FAILED
    priority TEXT DEFAULT 'MEDIUM',          -- HIGH, MEDIUM, LOW (for P08 prioritization)
    retries INTEGER DEFAULT 0,
    error_message TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX idx_vec_tenant ON st_vec(tenant_id, space_id);
CREATE INDEX idx_vec_source ON st_vec(source_layer, source_id);
CREATE INDEX idx_vec_status ON st_vec(embedding_status);
CREATE INDEX idx_vec_model ON st_vec(embedding_model);
-- P08 queue query optimization
CREATE INDEX idx_vec_pending ON st_vec(embedding_status, priority) WHERE embedding_status = 'PENDING';
```

> **P08 Coordination Pattern**:
>
> - P03 creates row with `embedding_status='PENDING'`
> - P03 emits `cognitive.embedding.requested.v1` event via outbox
> - P08 queries `st_vec WHERE embedding_status='PENDING' ORDER BY priority, created_at`
> - P08 updates status to PROCESSING, then READY (with vector_data) or FAILED

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] st_vec table with BLOB for vector
- [ ] **NO st_embedding_queue table (DEPRECATED)**
- [ ] embedding_status used for P08 queue coordination
- [ ] Status workflow documented
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0037_st_vec.sql`

---

#### Issue 1.1.9: Create Migration 0038 - st_fts (Full-Text Search)

**Type**: Migration
**Priority**: Medium
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r7`

**Description**:
Create FTS5 virtual table for R7.8.

**Schema Requirements**:

```sql
-- FTS5 Virtual Table
CREATE VIRTUAL TABLE st_fts USING fts5(
    source_layer,
    source_id,
    tenant_id,
    searchable_text,
    metadata_json,
    content='',
    contentless_delete=1
);

-- FTS Index Configuration
INSERT INTO st_fts(st_fts, rank) VALUES('rank', 'bm25(10.0, 5.0, 1.0)');
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] FTS5 virtual table configured
- [ ] BM25 ranking configured
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0038_st_fts.sql`

---

#### Issue 1.1.10: Create Migration 0039 - pipeline_offsets

**Type**: Migration
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `database`, `migration`, `p03`, `r8`

**Description**:
Create pipeline offset tracking table for R8.2.

**Schema Requirements**:

```sql
CREATE TABLE pipeline_offsets (
    -- Identity
    offset_id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- Progress Tracking
    last_processed_event_id TEXT,
    last_processed_wal_pos INTEGER,

    -- Statistics
    batch_size INTEGER,
    success_count INTEGER,
    failure_count INTEGER,

    -- Timestamps
    processed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Unique constraint
    UNIQUE(pipeline_id, tenant_id, space_id)
);

CREATE INDEX idx_offsets_pipeline ON pipeline_offsets(pipeline_id);
CREATE INDEX idx_offsets_tenant ON pipeline_offsets(tenant_id, space_id);
CREATE INDEX idx_offsets_processed ON pipeline_offsets(processed_at);

-- Checkpoint table for resume support
CREATE TABLE pipeline_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    pipeline_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- Checkpoint State
    phase TEXT NOT NULL, -- R0, R1, R2, ..., R8
    last_processed_event_id TEXT,
    partial_results_json TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,

    UNIQUE(cycle_id, phase)
);

CREATE INDEX idx_checkpoint_cycle ON pipeline_checkpoints(cycle_id);
```

**Acceptance Criteria**:

- [ ] Migration file created
- [ ] pipeline_offsets table
- [ ] pipeline_checkpoints for resume
- [ ] Rollback script included

**Files to Create**:

- `k0/contracts/sql/migrations/0039_pipeline_offsets.sql`

---

### Epic 1.2: Module Contracts (YAML)

**Description**: Create contract YAML files defining module interfaces.

#### Issue 1.2.1: Create Contract - hippocampus.importance_score.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r1`

**Description**:
Create module contract for R1.1 Importance Scoring.

**Contract Specification**:

```yaml
module_id: hippocampus.importance_score
version: v1
description: |
  Compute importance score for hippocampal events using multi-factor weighting.
  Formula: 0.35*emotional + 0.25*recency + 0.20*access + 0.20*social

input_event_types:
  - p03.batch.events

input_schema:
  type: object
  properties:
    events:
      type: array
      items:
        type: object
        properties:
          event_id: { type: string }
          valence: { type: number }
          arousal: { type: number }
          event_time_utc: { type: string }
          access_count: { type: integer }
          participants_json: { type: string }
        required: [event_id, event_time_utc]
  required: [events]

output_event_types:
  - p03.importance.scored

output_schema:
  type: object
  properties:
    scored_events:
      type: array
      items:
        type: object
        properties:
          event_id: { type: string }
          importance_score: { type: number, minimum: 0.0, maximum: 1.0 }
          score_components:
            type: object
            properties:
              emotional: { type: number }
              recency: { type: number }
              access: { type: number }
              social: { type: number }

latency_budget_ms: 5000
batch_size_max: 1000
memory_budget_mb: 256

side_effects:
  - read:st_hipp_events

idempotent: true

failure_modes:
  - code: MISSING_REQUIRED_FIELD
    policy: drop
  - code: COMPUTATION_ERROR
    policy: retry
    max_retries: 3

config_schema:
  type: object
  properties:
    emotional_weight: { type: number, default: 0.35 }
    recency_weight: { type: number, default: 0.25 }
    access_weight: { type: number, default: 0.20 }
    social_weight: { type: number, default: 0.20 }
    recency_half_life_days: { type: number, default: 7 }
```

**Acceptance Criteria**:

- [ ] Contract follows template
- [ ] All required fields documented
- [ ] Performance budget specified
- [ ] Config schema complete

**Files to Create**:

- `k0/contracts/modules/hippocampus.importance_score.v1.yaml`

---

#### Issue 1.2.2: Create Contract - hippocampus.priority_weight.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r1`

**Description**:
Create module contract for R1.2 Priority Weighting.

**Key Specifications**:

- Input: importance_score array from R1.1
- Output: priority_weight array (softmax normalized)
- Algorithm: `priority_weight[i] = exp(importance[i] * temperature) / sum(exp(importance * temperature))`
- Temperature: 1.0 (configurable for exploration vs exploitation)
- Latency: <100ms for 1000 events

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Softmax algorithm documented
- [ ] Temperature parameter configurable
- [ ] Output sums to 1.0

**Files to Create**:

- `k0/contracts/modules/hippocampus.priority_weight.v1.yaml`

---

#### Issue 1.2.3: Create Contract - hippocampus.replay_sequence.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r1`

**Description**:
Create module contract for R1.3 Replay Sequencing.

**Key Specifications**:

- Input: events with priority_weights
- Output: Ordered replay sequence
- Algorithm: 70% new events (high priority), 30% retrieval practice (random old events)
- Theta rhythm: 50-event micro-batches with 200ms gaps (5Hz simulation)
- Latency: <500ms for 1000 events

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Interleaving algorithm documented
- [ ] Micro-batch size configurable
- [ ] Retrieval practice ratio configurable

**Files to Create**:

- `k0/contracts/modules/hippocampus.replay_sequence.v1.yaml`

---

#### Issue 1.2.4: Create Contract - consolidation.episodic_cluster.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `contract`, `p03`, `r2`

**Description**:
Create module contract for R2.1 Episodic Clustering.

**Key Specifications**:

- Input: Events with simhash fingerprints + embeddings
- Output: episode_cluster_id, cluster_confidence per event
- Algorithm:
  1. LSH bucketing on SimHash (Hamming ≤5)
  2. DBSCAN clustering on semantic embeddings
  3. Composite distance: 60% semantic + 20% temporal + 10% location + 10% participant
- Output: 50-200 clusters per 1000 events
- Latency: <3 minutes for 1000 events

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] DBSCAN parameters documented (eps=0.3, min_samples=3)
- [ ] Distance function weights configurable
- [ ] Cluster quality metrics defined

**Files to Create**:

- `k0/contracts/modules/consolidation.episodic_cluster.v1.yaml`

---

#### Issue 1.2.5: Create Contract - consolidation.pattern_extract.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `contract`, `p03`, `r2`

**Description**:
Create module contract for R2.2 Pattern Extraction.

**Key Specifications**:

- Input: Episode clusters from R2.1
- Output: Semantic patterns (type, name, common_elements, confidence)
- Algorithm:
  1. For each cluster, extract invariants (mode of location, activity, time_of_day)
  2. Detect temporal recurrence (daily/weekly/monthly)
  3. Compute pattern confidence using geometric mean
- Pattern types: routine, preference, theme, relationship
- Latency: <2 minutes for 100 clusters

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Common element extraction documented
- [ ] Temporal pattern detection algorithm
- [ ] Confidence formula documented

**Files to Create**:

- `k0/contracts/modules/consolidation.pattern_extract.v1.yaml`

---

#### Issue 1.2.6: Create Contract - consolidation.ca1_bridge.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `contract`, `p03`, `r2`

**Description**:
Create module contract for R2.3 CA1 Bridge Decision.

**Key Specifications**:

- Input: New patterns + existing st_sem records
- Output: Decision per pattern (MERGE/EVOLVE/CREATE)
- Algorithm:
  - Query existing semantics with same pattern_type
  - Compute cosine similarity between pattern embeddings
  - MERGE: similarity >0.85 → update existing
  - EVOLVE: similarity 0.6-0.85 → create new version
  - CREATE: similarity <0.6 → insert new
- Latency: <1 minute for 50 patterns

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Similarity thresholds configurable
- [ ] Conflict resolution for multiple matches
- [ ] Version management protocol

**Files to Create**:

- `k0/contracts/modules/consolidation.ca1_bridge.v1.yaml`

---

#### Issue 1.2.7: Create Contract - consolidation.criteria_check.v1.yaml

**Type**: Contract
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r2`

**Description**:
Create module contract for R2.4 Consolidation Criteria.

**Key Specifications**:

- Input: Bridge decisions with patterns
- Output: Filtered decisions passing quality gates
- Quality Gates:
  - confidence_score ≥0.6 (pattern quality)
  - observation_count ≥3 (statistical significance)
  - temporal_span ≥7 days (not just same-day burst)
- Rejected patterns → candidate_patterns table for P06 Active Learning

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Quality gate thresholds configurable
- [ ] Rejection reason tracking
- [ ] P06 handoff documented

**Files to Create**:

- `k0/contracts/modules/consolidation.criteria_check.v1.yaml`

---

#### Issue 1.2.8: Create Contract - consolidation.semantic_promote.v1.yaml

**Type**: Contract
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r2`

**Description**:
Create module contract for R2.5 Semantic Promotion.

**Key Specifications**:

- Input: Filtered bridge decisions
- Output: Promotion records (episode_id → semantic_id mappings)
- Actions:
  - Mark source episodes with promoted_to_semantic_id
  - Create backlinks in source_episodes_json
  - Emit p03.pattern.promoted.v1 event

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Promotion mapping structure
- [ ] Event payload documented
- [ ] Backlink consistency

**Files to Create**:

- `k0/contracts/modules/consolidation.semantic_promote.v1.yaml`

---

#### Issue 1.2.9: Create Contract - synaptic.near_duplicate.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r3`

**Description**:
Create module contract for R3.1 Near-Duplicate Detection.

**Key Specifications**:

- Input: Events with simhash_fingerprint
- Output: is_near_duplicate flag, near_duplicates_json array
- Algorithm:
  1. Compute Hamming distance between SimHash pairs
  2. Hamming ≤3 → candidate duplicate
  3. Confirm with Jaccard similarity >0.8 on text shingles
  4. Mark non-canonical duplicates with canonical_event_id
- Latency: <3 minutes for 1000 events (O(n) with LSH)

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] SimHash comparison algorithm
- [ ] Jaccard confirmation step
- [ ] Canonical selection (highest salience)

**Files to Create**:

- `k0/contracts/modules/synaptic.near_duplicate.v1.yaml`

---

#### Issue 1.2.10: Create Contract - synaptic.novelty_score.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r3`

**Description**:
Create module contract for R3.2 Novelty Scoring.

**Key Specifications**:

- Input: Events with deduplication results
- Output: novelty_score (0.0-1.0)
- Formula:

  ```
  base_novelty = 1.0 - (duplicate_count / time_window_count)
  novelty = base_novelty + salience_boost - exact_duplicate_penalty
  ```

- Novelty tiers: HIGH (>0.8), MEDIUM (0.3-0.8), LOW (<0.3)
- Latency: <1 minute for 1000 events

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Novelty formula documented
- [ ] Tier thresholds configurable
- [ ] Retention adjustment rules

**Files to Create**:

- `k0/contracts/modules/synaptic.novelty_score.v1.yaml`

---

#### Issue 1.2.11: Create Contract - synaptic.retention_enforce.v1.yaml

**Type**: Contract
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r3`

**Description**:
Create module contract for R3.3 Retention Policy Enforcement.

**Key Specifications**:

- Input: Events with novelty scores
- Output: archival_deadline per event
- Algorithm:
  1. Lookup base retention from policy matrix (band × topic × device_kind)
  2. Adjust by novelty: HIGH = 2x retention, LOW = 0.5x retention
  3. Compute archival_deadline = event_time + adjusted_retention_days
- Side effect: Update retention_policies table lookups

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Policy matrix lookup documented
- [ ] Novelty adjustment formula
- [ ] Default retention (90 days GREEN, 365 days YELLOW, 7 years RED)

**Files to Create**:

- `k0/contracts/modules/synaptic.retention_enforce.v1.yaml`

---

#### Issue 1.2.12: Create Contract - synaptic.decay_apply.v1.yaml

**Type**: Contract
**Priority**: Medium
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r3`

**Description**:
Create module contract for R3.4 Decay Application.

**Key Specifications**:

- Input: Events to decay
- Output: Updated decay_factor values
- Formula: `decay_factor = exp(-λ * days_since_access)` where λ = ln(2) / half_life_days
- Default half_life: 30 days (configurable per band)

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Exponential decay formula
- [ ] Half-life configurable per band
- [ ] Decay floor (minimum 0.1)

**Files to Create**:

- `k0/contracts/modules/synaptic.decay_apply.v1.yaml`

---

#### Issue 1.2.13: Create Contract - synaptic.archive_tombstone.v1.yaml

**Type**: Contract
**Priority**: Medium
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r3`

**Description**:
Create module contract for R3.5 Archive/Tombstone.

**Key Specifications**:

- Input: Events past archival_deadline
- Output: Archived events (compressed), tombstones (metadata only)
- Archive: zlib compression, store in st_archived_events
- Tombstone: Delete content, keep metadata in st_tombstones for audit
- GDPR: Tombstone retention 90 days, then full delete

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Compression algorithm (zlib level 6)
- [ ] Tombstone schema documented
- [ ] GDPR compliance notes

**Files to Create**:

- `k0/contracts/modules/synaptic.archive_tombstone.v1.yaml`

---

#### Issue 1.2.14: Create Contract - kg.entity_normalize.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: NLP Engineer
**Labels**: `contract`, `p03`, `r4`

**Description**:
Create module contract for R4.1 Entity Extraction & Normalization.

**Key Specifications**:

- Input: Events with entities_json (pre-computed by P02 UltraBERT)
- Output: Normalized entities with canonical node_ids
- Algorithm:
  1. Parse entities_json from st_hipp_events (NO NER model call)
  2. For each entity, query st_kg_dom for existing nodes
  3. Exact match → return canonical_node_id
  4. Fuzzy match (Levenshtein >0.85) → add alias, return canonical
  5. No match → create new node
- UltraBERT provides 21 entity types:
  - General (9): PERSON, ORG, LOC, GPE, DATE, TIME, MONEY, PERCENT, QUANTITY
  - Family (12): KINSHIP, FAMILY_EVENT, PET, MEAL, ACTIVITY, PLACE, CELEBRATION, etc.
- Output: 50-150 entities per 1000 events
- Latency: <2 minutes

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Document P02 entities_json format
- [ ] Fuzzy matching algorithm
- [ ] Pre-filtering for scalability

**Files to Create**:

- `k0/contracts/modules/kg.entity_normalize.v1.yaml`

---

#### Issue 1.2.15: Create Contract - kg.relationship_discover.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: NLP Engineer
**Labels**: `contract`, `p03`, `r4`

**Description**:
Create module contract for R4.2 Relationship Discovery.

**Key Specifications**:

- Input: Normalized entities + event context
- Output: Relationship edges (source, target, type, strength)
- Algorithm:
  1. Co-occurrence: Entities in same event → co_occurs_with edge
  2. Temporal proximity: Events within 1 hour → temporal edge
  3. Strength: count / max_count (normalized 0-1)
- Edge types: co_occurs_with, causes, enables, part_of
- Output: 100-300 relationships per 1000 events
- Latency: <3 minutes

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Co-occurrence algorithm
- [ ] Strength normalization
- [ ] Edge type classification

**Files to Create**:

- `k0/contracts/modules/kg.relationship_discover.v1.yaml`

---

#### Issue 1.2.16: Create Contract - kg.temporal_update.v1.yaml

**Type**: Contract
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r4`

**Description**:
Create module contract for R4.3 Temporal Graph Updates.

**Key Specifications**:

- Input: Entities + relationships with timestamps
- Output: Updated valid_from/valid_to on st_kg_dom and st_kg_edges
- Algorithm:
  1. For new observations, extend last_observed_at
  2. For conflicting facts, close old version (valid_to=now), create new
  3. Track observation_count increment

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Temporal validity management
- [ ] Conflict detection rules
- [ ] Version chain maintenance

**Files to Create**:

- `k0/contracts/modules/kg.temporal_update.v1.yaml`

---

#### Issue 1.2.17: Create Contract - kg.causal_construct.v1.yaml

**Type**: Contract
**Priority**: High
**Assignee**: ML Engineer
**Labels**: `contract`, `p03`, `r4`

**Description**:
Create module contract for R4.4 Causal Graph Construction.

**Key Specifications**:

- Input: Event sequences + relationships
- Output: Causal edges (is_causal=1, causal_confidence, temporal_lag)
- Algorithm:
  1. Temporal precedence: Event A consistently precedes Event B
  2. Granger causality test (simplified): Does A predict B better than B alone?
  3. Causal confidence = frequency × temporal_consistency
- Latency: <2 minutes

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Causal inference algorithm
- [ ] Confidence scoring
- [ ] Minimum observation threshold (≥5 occurrences)

**Files to Create**:

- `k0/contracts/modules/kg.causal_construct.v1.yaml`

---

#### Issue 1.2.18: Create Contract - kg.concept_evolve.v1.yaml

**Type**: Contract
**Priority**: Medium
**Assignee**: ML Engineer
**Labels**: `contract`, `p03`, `r4`

**Description**:
Create module contract for R4.5 Concept Evolution Tracking.

**Key Specifications**:

- Input: Semantic patterns + KG updates
- Output: Concept drift detection, versioned concept nodes
- Algorithm:
  1. Compare current concept embedding with previous version
  2. If drift >0.3 → create new version
  3. Track concept_evolution_history

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Drift detection algorithm
- [ ] Version chain maintenance
- [ ] Evolution history structure

**Files to Create**:

- `k0/contracts/modules/kg.concept_evolve.v1.yaml`

---

### Epic 1.3: Pipeline YAML Configuration

**Description**: Create the declarative pipeline specification.

#### Issue 1.3.1: Create Pipeline YAML - p03_consolidation.v1.yaml

**Type**: Pipeline Config
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `pipeline`, `p03`, `yaml`

**Description**:
Create the main pipeline YAML defining all stages, dependencies, and execution order.

**Key Sections**:

1. **Trigger Configuration**: 4 trigger modes (idle, scheduled, threshold, manual)
2. **Batch Configuration**: size=1000, max_duration=90min, checkpoint_interval=100
3. **Stage Definitions**: 37 stages from R0-R8
4. **Parallel Groups**: R3 and R4 in parallel
5. **Output Events**: p03.consolidation.complete.v1, p03.pattern.detected.v1
6. **Observability**: trace_id, metrics_prefix, log_level

**Acceptance Criteria**:

- [ ] All 37 stages defined
- [ ] Dependencies correctly specified
- [ ] Parallel groups for R3/R4
- [ ] Output events mapped to stages
- [ ] Follows P02 YAML pattern

**Files to Create**:

- `k0/contracts/pipelines/p03_consolidation.v1.yaml`

---

### Epic 1.4: Writer Contracts (R6-R7)

**Description**: Create contracts for state update and memory layer writers.

#### Issue 1.4.1: Create Contract - consolidation.update_dedup.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r6`

**Description**:
Create module contract for R6.1 Update Deduplication Columns.

**Key Specifications**:

- Input: Deduplication results from R3.1, novelty scores from R3.2
- Output: Updated st_hipp_events rows
- Columns updated: novelty_score, near_duplicates_json, is_near_duplicate
- Batch UPDATE with executemany()

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] UPDATE SQL documented
- [ ] Batch size optimization
- [ ] Error handling for missing events

**Files to Create**:

- `k0/contracts/modules/consolidation.update_dedup.v1.yaml`

---

#### Issue 1.4.2: Create Contract - consolidation.update_cluster.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r6`

**Description**:
Create module contract for R6.2 Update Cluster Columns.

**Key Specifications**:

- Input: Cluster assignments from R2.1
- Output: Updated st_hipp_events rows
- Columns updated: episode_cluster_id, cluster_confidence
- Handle outliers: cluster_id = SING_<event_id>

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Cluster ID format documented
- [ ] Outlier handling
- [ ] Validation rules

**Files to Create**:

- `k0/contracts/modules/consolidation.update_cluster.v1.yaml`

---

#### Issue 1.4.3: Create Contract - consolidation.update_status.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r6`

**Description**:
Create module contract for R6.3 Update Consolidation Status.

**Key Specifications**:

- Input: Results from R6.1, R6.2
- Output: Updated consolidation_status, consolidated_at
- Status values: PENDING → CONSOLIDATING → COMPLETE/FAILED
- Transaction: Combine with R6.1/R6.2 in single commit

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Status state machine
- [ ] Error tracking (consolidation_error column)
- [ ] Offset update coordination

**Files to Create**:

- `k0/contracts/modules/consolidation.update_status.v1.yaml`

---

#### Issue 1.4.4: Create Contract - writers.episodic.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r7`

**Description**:
Create module contract for R7.1 Episodic Writer.

**Key Specifications**:

- Input: Clusters + promotions from R2
- Output: st_epi records via st_outbox
- Cluster-to-episode mapping: 1 cluster → 1 episode
- Representative event: highest cluster_confidence
- Skip is_near_duplicate=1 events

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Episode record structure
- [ ] Outbox staging protocol
- [ ] Deduplication skip logic

**Files to Create**:

- `k0/contracts/modules/writers.episodic.v1.yaml`

---

#### Issue 1.4.5: Create Contract - writers.semantic.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r7`

**Description**:
Create module contract for R7.2 Semantic Writer.

**Key Specifications**:

- Input: CA1 bridge decisions from R2.3
- Output: st_sem records via st_outbox
- MERGE: UPDATE existing, increment observation_count
- EVOLVE: INSERT new version, UPDATE old (is_canonical=0)
- CREATE: INSERT new record

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] MERGE/EVOLVE/CREATE handling
- [ ] Version management
- [ ] Outbox staging protocol

**Files to Create**:

- `k0/contracts/modules/writers.semantic.v1.yaml`

---

#### Issue 1.4.6: Create Contract - writers.kg.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r7`

**Description**:
Create module contract for R7.6 Knowledge Graph Writer.

**Key Specifications**:

- Input: Entities, relationships, causal edges from R4
- Output: st_kg_dom + st_kg_edges records via st_outbox
- Node deduplication: Check canonical before insert
- Edge update: Increment observation_count for existing

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Node insert/update logic
- [ ] Edge insert/update logic
- [ ] Outbox staging protocol

**Files to Create**:

- `k0/contracts/modules/writers.kg.v1.yaml`

---

#### Issue 1.4.7: Create Contract - writers.vec_placeholder.v1.yaml

**Type**: Contract
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r7`, `p08`

**Description**:
Create module contract for R7.7 Vector Placeholder Writer.

> **IMPORTANT**: Per Pipeline-Fabric Integration Guide §1.9, `st_embedding_queue` is **DEPRECATED**.
> Use `st_vec.embedding_status` for P08 coordination instead.

**Key Specifications**:

- Input: Episodes + semantics from R7.1/R7.2
- Output: st_vec placeholders with `embedding_status='PENDING'`
- **NO st_embedding_queue** - use st_vec.embedding_status column
- P08 coordination: Emit `cognitive.embedding.requested.v1` event via outbox
- Backpressure: Query `COUNT(*) FROM st_vec WHERE embedding_status='PENDING'` before writes

**Implementation Pattern**:

```python
# R7.7 - Create vector placeholder (NO deprecated queue table)
async def create_vec_placeholder(self, source_layer: str, source_id: str, text: str):
    # Check backpressure
    pending_count = await self._syscalls.query_count(
        table="st_vec",
        where="embedding_status = 'PENDING'",
    )
    if pending_count > 10000:
        raise BackpressureError("Embedding queue depth exceeded")

    # Create placeholder in st_vec
    embedding_id = generate_id()
    await self._syscalls.vec_write(
        embedding_id=embedding_id,
        source_layer=source_layer,
        source_id=source_id,
        text_to_embed=text,
        embedding_status="PENDING",
        priority="MEDIUM",
    )

    # Emit event for P08 via outbox
    await self._syscalls.outbox_emit_batch([{
        "topic": "cognitive.embedding.requested.v1",
        "payload": json.dumps({"embedding_id": embedding_id}),
    }])
```

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Placeholder uses st_vec.embedding_status (NOT deprecated st_embedding_queue)
- [ ] Outbox event emission for P08 notification
- [ ] Backpressure check with configurable threshold

**Files to Create**:

- `k0/contracts/modules/writers.vec_placeholder.v1.yaml`

---

### Epic 1.5: Event Emission Contracts (R8)

**Description**: Create contracts for event emission and offset tracking.

> **IMPORTANT**: Per Pipeline-Fabric Integration Guide §8.3, all event emission must use
> the transactional outbox pattern via `syscalls.outbox_emit_batch()`.

#### Issue 1.5.1: Create Contract - consolidation.event_emit.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r8`

**Description**:
Create module contract for R8.1 Event Emission.

**Key Specifications**:

- Input: Consolidation results from R6, R7
- Output: K0 Bus events via **transactional outbox pattern**
- **Must use `syscalls.outbox_emit_batch()`** - NOT direct bus dispatch
- Events emitted:
  - p03.consolidation.complete.v1 (cycle summary)
  - p03.pattern.detected.v1 (per pattern)
  - p03.kg.updated.v1 (KG changes)
  - p03.event.archived.v1 (archival notifications)

**Implementation Pattern (Per Integration Guide §8.3)**:

```python
# R8.1 - Transactional event emission via outbox
async def emit_consolidation_events(self, cycle_result: CycleResult):
    events = []

    # Cycle completion event
    events.append({
        "topic": "p03.consolidation.complete.v1",
        "payload": json.dumps({
            "cycle_id": cycle_result.cycle_id,
            "events_processed": cycle_result.events_processed,
            "memories_created": cycle_result.memories_created,
            "duration_seconds": cycle_result.duration_seconds,
        }),
        "trace_id": cycle_result.trace_id,
    })

    # Pattern detection events
    for pattern in cycle_result.patterns:
        events.append({
            "topic": "p03.pattern.detected.v1",
            "payload": json.dumps({
                "pattern_id": pattern.id,
                "pattern_type": pattern.type,
                "confidence": pattern.confidence,
            }),
            "trace_id": cycle_result.trace_id,
        })

    # Emit all via outbox (transactional with storage writes)
    await self._syscalls.outbox_emit_batch(events)
```

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Event payload schemas defined
- [ ] **Uses outbox_emit_batch syscall** (NOT direct bus dispatch)
- [ ] Error handling for event emission failures
- [ ] Correlation ID (trace_id) propagation

**Files to Create**:

- `k0/contracts/modules/consolidation.event_emit.v1.yaml`

---

#### Issue 1.5.2: Create Contract - consolidation.offset_update.v1.yaml

**Type**: Contract
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r8`

**Description**:
Create module contract for R8.2 Offset Update.

**Key Specifications**:

- Input: Batch completion info
- Output: Updated pipeline_offsets row
- Fields: last_processed_event_id, batch_size, success_count, failure_count
- Idempotency: Use cycle_id to prevent double-processing

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Offset update SQL
- [ ] Idempotency mechanism
- [ ] Resume support from checkpoint

**Files to Create**:

- `k0/contracts/modules/consolidation.offset_update.v1.yaml`

---

#### Issue 1.5.3: Create Contract - consolidation.metrics.v1.yaml

**Type**: Contract
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `contract`, `p03`, `r8`

**Description**:
Create module contract for R8.3 Metrics Collection.

**Key Specifications**:

- Input: Cycle statistics
- Output: Prometheus metrics
- Metrics:
  - p03_cycle_duration_seconds (histogram)
  - p03_events_processed_total (counter)
  - p03_memories_created_total (counter by layer)
  - p03_novelty_score (histogram)
  - p03_cluster_count (gauge)

**Acceptance Criteria**:

- [ ] Contract YAML created
- [ ] Metric names and types
- [ ] Label dimensions
- [ ] Prometheus format

**Files to Create**:

- `k0/contracts/modules/consolidation.metrics.v1.yaml`

---

### Epic 1.6: K0 Architecture Master - Milestone 1 Registration

**Description**: Update K0 Architecture Master with all Milestone 1 artifacts (MANDATORY before M2).

#### Issue 1.6.1: Update K0 Architecture Master - Event Topics Registry

**Type**: Governance
**Priority**: BLOCKER
**Assignee**: Tech Lead
**Labels**: `governance`, `k0-master`, `p03`, `mandatory`

**Description**:
Add all P03 event topics to the K0 Architecture Master Event Topics Registry (Part 4.1).

**K0 Architecture Master Updates Required**:

- **Part 4.1: Event Topics Registry** - Add P03 events:

| Topic | Schema | Producer | Consumers | QoS Band |
|-------|--------|----------|-----------|----------|
| `p03.consolidation.triggered.v1` | ConsolidationTrigger | P03/R0 | P03 | GREEN |
| `p03.batch.selected.v1` | BatchSelection | P03/R1 | P03 | GREEN |
| `p03.importance.scored.v1` | ImportanceScores | P03/R1 | P03 | GREEN |
| `p03.cluster.formed.v1` | ClusterResult | P03/R2 | P03 | GREEN |
| `p03.pattern.detected.v1` | PatternResult | P03/R2 | P03, P06 | GREEN |
| `p03.memories.updated.v1` | MemoryUpdates | P03/R6-R7 | P06 | GREEN |
| `p03.kg.updated.v1` | KGUpdates | P03/R4 | P06 | GREEN |
| `p03.consolidation.complete.v1` | CycleComplete | P03/R8 | P06, Metrics | GREEN |

**Acceptance Criteria**:

- [ ] All 8 P03 event topics added to Part 4.1
- [ ] Schema references linked to contract files
- [ ] Producer/consumer relationships documented
- [ ] QoS bands assigned

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 4.1)

---

#### Issue 1.6.2: Update K0 Architecture Master - Contract Registry

**Type**: Governance
**Priority**: BLOCKER
**Assignee**: Tech Lead
**Labels**: `governance`, `k0-master`, `p03`, `mandatory`

**Description**:
Add all P03 module contracts to the K0 Architecture Master Contract Registry (Part 5.1).

**K0 Architecture Master Updates Required**:

- **Part 5.1: Global Contract Registry** - Add ~28 P03 contracts:

| Contract | Version | Module | Pipeline | Schema Location |
|----------|---------|--------|----------|-----------------|
| hippocampus.importance_score | v1 | Consolidation | P03/R1 | `k0/contracts/modules/` |
| hippocampus.episodic_cluster | v1 | Consolidation | P03/R2 | `k0/contracts/modules/` |
| hippocampus.ca1_bridge | v1 | Consolidation | P03/R2 | `k0/contracts/modules/` |
| ... (all 28 contracts) | | | | |

**Acceptance Criteria**:

- [ ] All 28 module contracts listed
- [ ] Version and schema location for each
- [ ] Linked to pipeline phases

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 5.1)

---

#### Issue 1.6.3: Update K0 Architecture Master - Syscall Matrix

**Type**: Governance
**Priority**: BLOCKER
**Assignee**: Tech Lead
**Labels**: `governance`, `k0-master`, `p03`, `mandatory`

**Description**:
Add all P03 storage operations to the K0 Architecture Master Syscall Matrix (Part 5.2).

**K0 Architecture Master Updates Required**:

- **Part 5.2: Syscall Matrix** - Add P03 syscalls:

| Capability | Operation | Tables | Pipeline | Why |
|------------|-----------|--------|----------|-----|
| `st_hipp_events.read` | SELECT | st_hipp_events | P03/R0 | Batch selection |
| `st_hipp_events.write` | UPDATE | st_hipp_events | P03/R6 | Set consolidated flag |
| `st_epi.write` | INSERT | st_epi | P03/R7.1 | Write episodic memories |
| `st_sem.write` | INSERT/UPDATE | st_sem | P03/R7.2 | Write semantic memories |
| `st_procedural.write` | INSERT | st_procedural | P03/R7.3 | Write procedural memories |
| `st_social.write` | INSERT | st_social | P03/R7.4 | Write social memories |
| `st_prospective.write` | INSERT | st_prospective | P03/R7.5 | Write prospective memories |
| `st_kg_dom.write` | INSERT/UPDATE | st_kg_dom | P03/R4 | Write KG nodes |
| `st_kg_edges.write` | INSERT/UPDATE | st_kg_edges | P03/R4 | Write KG edges |
| `st_vec.write` | INSERT | st_vec | P03/R8 | Write vector embeddings |
| `consolidation_locks.write` | INSERT/UPDATE/DELETE | consolidation_locks | P03/R0 | Lock management |
| `pipeline_offsets.write` | INSERT/UPDATE | pipeline_offsets | P03/R8 | Track progress |

**Acceptance Criteria**:

- [ ] All P03 syscalls documented
- [ ] Read vs Write permissions clear
- [ ] Error handling documented

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 5.2)

---

#### Issue 1.6.4: Update K0 Architecture Master - Module Registry

**Type**: Governance
**Priority**: BLOCKER
**Assignee**: Tech Lead
**Labels**: `governance`, `k0-master`, `p03`, `mandatory`

**Description**:
Add P03 Consolidation module to the K0 Architecture Master Module Registry (Part 3.1).

**K0 Architecture Master Updates Required**:

- **Part 3.1: Module Master Registry** - Add row:

| ID | Name | Status | Brain Analog | Pipelines | Version |
|----|------|--------|--------------|-----------|---------|
| M20 | Consolidation | 🎯 Planning | Sleep Consolidation | P03 | 0.1.0 |

- **Part 3.2: Per-Module Deep Dives** - Create M20 section following template

**Acceptance Criteria**:

- [ ] M20 added to Module Master Registry
- [ ] Status set to 🎯 Planning
- [ ] Deep dive section created with template
- [ ] Brain analog documented (Sleep Consolidation)

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 3.1, Part 3.2)

---

#### Issue 1.6.5: Update K0 Architecture Master - Pipeline Status to Planning

**Type**: Governance
**Priority**: BLOCKER
**Assignee**: Tech Lead
**Labels**: `governance`, `k0-master`, `p03`, `mandatory`

**Description**:
Update P03 status in Pipeline Registry after Milestone 1 completion.

**K0 Architecture Master Updates Required**:

- **Part 2.1: Pipeline Master Registry** - Update P03 row:
  - Status: 📝 Design → 🎯 Planning
  - Design Phase: 📝 Initial → ✅ Spec Complete
  - Modules Used: M20 (Consolidation)
  - Version: 0.1.0 → 0.2.0
  - Last Updated: 2025-11-25

**Acceptance Criteria**:

- [ ] P03 status updated to 🎯 Planning
- [ ] Design Phase set to ✅ Spec Complete
- [ ] Module dependencies documented
- [ ] Version bumped to 0.2.0
- [ ] K0 Architecture Master version bumped (MINOR)

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 2.1)

---

### Milestone 1 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 1 complete, verify these K0 updates:

**K0 Closure Checklist for M1**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 2.1 | Pipeline Registry | P03 status → 🎯 Planning | ☐ |
| 4.1 | Event Topics Registry | All P03 events registered | ☐ |
| 5.1 | Contract Registry | All 28+ module contracts added | ☐ |
| 5.2 | Syscall Matrix | All 28 capabilities registered | ☐ |
| 5.3 | Storage Contracts | 10 new tables documented | ☐ |
| Header | Version | Bumped to next MINOR version | ☐ |

**Commit Message Format**: `docs(k0): M1 complete - P03 contracts registered in K0 Architecture Master`

---

## Milestone 2: Core Consolidation (R0-R1)

**Goal**: Implement trigger detection, batch selection, and hippocampal replay.
**Duration**: 4-5 days
**Gate**: GATE 3 (Implementation)

### Epic 2.1: Trigger Detection (R0)

**Description**: Implement consolidation trigger mechanisms and lock management.

#### Issue 2.1.1: Implement Lock Manager

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r0`

**Description**:
Implement consolidation lock acquisition and release.

**Implementation Requirements**:

```python
# k0/modules/consolidation/lock_manager.py

class ConsolidationLockManager:
    async def acquire_lock(
        self,
        tenant_id: str,
        space_id: str,
        cycle_id: str,
        timeout_seconds: int = 30
    ) -> bool:
        """
        Acquire consolidation lock for tenant/space.
        Returns True if acquired, False if already locked.
        """

    async def release_lock(self, cycle_id: str) -> None:
        """Release lock after consolidation completes."""

    async def cleanup_stale_locks(self, max_age_hours: int = 2) -> int:
        """Clean up locks older than max_age_hours. Returns count cleaned."""

    async def get_lock_status(self, tenant_id: str, space_id: str) -> LockStatus:
        """Get current lock status for tenant/space."""
```

**Acceptance Criteria**:

- [ ] Lock acquisition with timeout
- [ ] Lock release on completion
- [ ] Stale lock cleanup (>2 hours)
- [ ] Unit tests for race conditions
- [ ] Integration test with concurrent calls

**Files to Create**:

- `k0/modules/consolidation/lock_manager.py`
- `tests/k0/modules/consolidation/test_lock_manager.py`

---

#### Issue 2.1.2: Implement Batch Selector

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r0`

**Description**:
Implement batch selection query for pending events.

**Implementation Requirements**:

```python
# k0/modules/consolidation/batch_selector.py

class BatchSelector:
    async def select_batch(
        self,
        tenant_id: str,
        space_id: str,
        batch_size: int = 1000,
        min_events: int = 100
    ) -> List[dict]:
        """
        Select batch of pending events for consolidation.

        Query:
        SELECT * FROM st_hipp_events
        WHERE tenant_id = ? AND space_id = ?
          AND consolidation_status IS NULL
        ORDER BY event_time_utc ASC
        LIMIT ?
        """

    async def get_pending_count(self, tenant_id: str, space_id: str) -> int:
        """Get count of pending events."""
```

**Acceptance Criteria**:

- [ ] Batch selection query
- [ ] Event ordering (oldest first)
- [ ] Minimum event threshold check
- [ ] Performance: <1 second for 10k pending
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/batch_selector.py`
- `tests/k0/modules/consolidation/test_batch_selector.py`

---

#### Issue 2.1.3: Implement Trigger Coordinator

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r0`

**Description**:
Implement the 4 trigger mechanisms and priority ordering.

**Implementation Requirements**:

```python
# k0/modules/consolidation/trigger_coordinator.py

class TriggerCoordinator:
    async def check_idle_trigger(self, tenant_id: str, space_id: str) -> bool:
        """Check if idle trigger conditions met (5 min inactive + 100 pending)."""

    async def check_threshold_trigger(self, tenant_id: str, space_id: str) -> bool:
        """Check if threshold trigger conditions met (1000 pending)."""

    async def check_scheduled_trigger(self, cron_expression: str) -> bool:
        """Check if scheduled trigger time reached."""

    async def trigger_consolidation(
        self,
        tenant_id: str,
        space_id: str,
        trigger_type: TriggerType,
        manual_override: bool = False
    ) -> ConsolidationCycle:
        """
        Start consolidation cycle.
        Priority: Manual > Threshold > Idle > Scheduled
        """
```

**Acceptance Criteria**:

- [ ] All 4 trigger types implemented
- [ ] Priority ordering enforced
- [ ] Lock acquisition before start
- [ ] Cycle ID generation
- [ ] Unit tests for each trigger type

**Files to Create**:

- `k0/modules/consolidation/trigger_coordinator.py`
- `tests/k0/modules/consolidation/test_trigger_coordinator.py`

---

### Epic 2.2: Hippocampal Replay (R1)

**Description**: Implement importance scoring, priority weighting, and replay sequencing.

#### Issue 2.2.1: Implement Importance Scorer

**Type**: Implementation
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r1`

**Description**:
Implement R1.1 importance scoring formula.

**Implementation Requirements**:

```python
# k0/modules/consolidation/importance_scorer.py

class ImportanceScorer:
    def __init__(
        self,
        emotional_weight: float = 0.35,
        recency_weight: float = 0.25,
        access_weight: float = 0.20,
        social_weight: float = 0.20,
        recency_half_life_days: float = 7.0
    ):
        self.weights = {...}

    def compute_emotional_intensity(self, event: dict) -> float:
        """
        Compute emotional intensity from valence/arousal.
        Formula: sqrt(valence² + arousal²) / sqrt(2)
        """

    def compute_recency_score(self, event_time_utc: str) -> float:
        """
        Compute recency with exponential decay.
        Formula: exp(-ln(2) * days_ago / half_life)
        """

    def compute_access_score(self, access_count: int) -> float:
        """
        Compute access score (log scale).
        Formula: log(access_count + 1) / log(max_access + 1)
        """

    def compute_social_score(self, participants_json: str) -> float:
        """
        Compute social significance.
        Formula: len(participants) / max_participants
        """

    def score_batch(self, events: List[dict]) -> List[ScoredEvent]:
        """Score batch of events, return with importance_score."""
```

**Acceptance Criteria**:

- [ ] All 4 component scores implemented
- [ ] Weighted combination formula
- [ ] Edge case handling (missing fields)
- [ ] Performance: <5 seconds for 1000 events
- [ ] Unit tests with fixtures
- [ ] Integration test with st_hipp_events

**Files to Create**:

- `k0/modules/consolidation/importance_scorer.py`
- `tests/k0/modules/consolidation/test_importance_scorer.py`

---

#### Issue 2.2.2: Implement Priority Weighter

**Type**: Implementation
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r1`

**Description**:
Implement R1.2 softmax priority weighting.

**Implementation Requirements**:

```python
# k0/modules/consolidation/priority_weighter.py

class PriorityWeighter:
    def __init__(self, temperature: float = 1.0):
        self.temperature = temperature

    def compute_weights(self, importance_scores: List[float]) -> List[float]:
        """
        Compute softmax weights for stochastic replay.
        Formula: exp(score * temp) / sum(exp(scores * temp))
        """

    def sample_replay_order(
        self,
        events: List[dict],
        weights: List[float],
        sample_size: int
    ) -> List[dict]:
        """Sample events according to weights (without replacement)."""
```

**Acceptance Criteria**:

- [ ] Softmax normalization
- [ ] Temperature parameter
- [ ] Numerical stability (log-sum-exp trick)
- [ ] Weights sum to 1.0
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/priority_weighter.py`
- `tests/k0/modules/consolidation/test_priority_weighter.py`

---

#### Issue 2.2.3: Implement Replay Sequencer

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r1`

**Description**:
Implement R1.3 replay sequencing with interleaving.

**Implementation Requirements**:

```python
# k0/modules/consolidation/replay_sequencer.py

class ReplaySequencer:
    def __init__(
        self,
        new_event_ratio: float = 0.7,
        micro_batch_size: int = 50,
        theta_gap_ms: int = 200
    ):
        self.new_event_ratio = new_event_ratio
        self.micro_batch_size = micro_batch_size

    async def generate_sequence(
        self,
        new_events: List[dict],
        priority_weights: List[float],
        old_events: List[dict]  # From retrieval practice query
    ) -> AsyncIterator[List[dict]]:
        """
        Generate replay sequence with theta rhythm.
        Yields micro-batches of 50 events with 200ms gaps.
        Interleaves: 70% new (priority-weighted), 30% old (random).
        """

    async def fetch_retrieval_practice_events(
        self,
        tenant_id: str,
        space_id: str,
        count: int
    ) -> List[dict]:
        """
        Fetch old events for retrieval practice.
        Query: Random sample from consolidated events with decay weighting.
        """
```

**Acceptance Criteria**:

- [ ] 70/30 interleaving
- [ ] Micro-batch generation (50 events)
- [ ] Theta rhythm simulation (200ms gaps)
- [ ] Retrieval practice query
- [ ] Async iterator pattern
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/replay_sequencer.py`
- `tests/k0/modules/consolidation/test_replay_sequencer.py`

---

#### Issue 2.2.4: Write Importance Scores to st_hipp_events

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r1`

**Description**:
Persist computed importance scores back to st_hipp_events.

**Implementation Requirements**:

```python
async def write_importance_scores(
    scored_events: List[ScoredEvent],
    cycle_id: str
) -> int:
    """
    Batch UPDATE st_hipp_events with importance_score.
    Also sets consolidation_cycle_id and consolidation_status='CONSOLIDATING'.
    Returns count of updated rows.
    """
```

**Acceptance Criteria**:

- [ ] Batch UPDATE query
- [ ] Set consolidation_status='CONSOLIDATING'
- [ ] Set consolidation_cycle_id
- [ ] Transaction management
- [ ] Unit tests

**Files to Create**:

- Update `k0/modules/consolidation/importance_scorer.py`

---

### Epic 2.3: K0 Architecture Master - R0/R1 Module Registration

**Description**: Register all Milestone 2 modules, contracts, and syscalls in K0 Architecture Master.

#### Issue 2.3.1: Update K0 Module Registry - R0/R1 Components

**Type**: Documentation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `k0-governance`, `documentation`, `p03`

**Description**:
Register all R0 and R1 modules in K0 Architecture Master Part 3.1.

**K0 Registration Requirements**:

1. **Part 3.1 - Module Registry** - Add entries for:

| Module | Type | Status | Layer | Pipelines | Lifecycle |
|--------|------|--------|-------|-----------|-----------|
| `consolidation.lock_manager` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Request |
| `consolidation.trigger_detector` | Service | ⚠️ Impl | K0/Consolidation | P03 | Scheduled |
| `consolidation.batch_selector` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.hippocampal_replay` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.importance_scorer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.activation_spreader` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |

2. **Part 5.2 - Syscall Matrix** - Add syscall entries:

| Syscall | Target | Operation | Module | Band |
|---------|--------|-----------|--------|------|
| `st_consolidation_locks.acquire` | Storage | WRITE | lock_manager | GREEN |
| `st_consolidation_locks.release` | Storage | DELETE | lock_manager | GREEN |
| `st_consolidation_cycles.create` | Storage | WRITE | trigger_detector | GREEN |
| `st_hipp_events.select_batch` | Storage | READ | batch_selector | GREEN |
| `st_hipp_events.update_status` | Storage | WRITE | hippocampal_replay | GREEN |
| `st_hipp_events.update_importance` | Storage | WRITE | importance_scorer | GREEN |

3. **Part 4.1 - Event Topics Registry** - Add event topics:

| Topic | Publisher | Subscribers | Schema | Band |
|-------|-----------|-------------|--------|------|
| `consolidation.cycle.started.v1` | trigger_detector | orchestrator | CycleStarted | GREEN |
| `consolidation.batch.selected.v1` | batch_selector | replay | BatchSelected | GREEN |
| `consolidation.replay.completed.v1` | hippocampal_replay | integration | ReplayCompleted | GREEN |
| `consolidation.scoring.completed.v1` | importance_scorer | orchestrator | ScoringCompleted | GREEN |

**Acceptance Criteria**:

- [ ] All R0 modules added to Part 3.1 Module Registry
- [ ] All R1 modules added to Part 3.1 Module Registry
- [ ] Syscalls added to Part 5.2 Syscall Matrix
- [ ] Event topics added to Part 4.1 Event Topics Registry
- [ ] Module dependencies documented
- [ ] Status set to ⚠️ Implementation

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 3.1, 4.1, 5.2)

**K0 Pre-Merge Checklist**:

- [ ] Part 3.1 Module Registry updated
- [ ] Part 4.1 Event Topics Registry updated
- [ ] Part 5.2 Syscall Matrix updated
- [ ] Cross-references correct
- [ ] Status transitions documented

---

### Milestone 2 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 2 complete, verify these K0 updates:

**K0 Closure Checklist for M2**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 2.1 | Pipeline Registry | P03 status → ⚠️ Implementation | ☐ |
| 3.1 | Module Registry | R0/R1 modules added (lock_manager, trigger, importance, etc.) | ☐ |
| 5.2 | Syscall Matrix | R0/R1 syscalls validated | ☐ |
| Header | Version | Bumped to next PATCH version | ☐ |

**Commit Message Format**: `docs(k0): M2 complete - R0/R1 modules registered`

---

## Milestone 3: Pattern Extraction (R2)

**Goal**: Implement episodic clustering, pattern extraction, and CA1 bridge.
**Duration**: 5-6 days
**Gate**: GATE 3 (Implementation)

### Epic 3.1: Episodic Clustering (R2.1)

**Description**: Implement semantic clustering of events into episodes.

#### Issue 3.1.1: Implement Embedding Reader

**Type**: Implementation
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Read pre-computed embeddings from st_vec (written by P02 M16).

**Implementation Requirements**:

```python
# k0/modules/consolidation/embedding_reader.py
import struct
from typing import List
import numpy as np

class EmbeddingReader:
    """
    Read 768-dim UltraBERT embeddings from st_vec.

    NOTE: P03 does NOT call any embedding model.
    P02 M22 extracts embeddings from UltraBERT cache and M16 writes to st_vec.
    P03 reads these pre-computed embeddings for clustering.
    """

    def __init__(self, db_connection):
        self.db = db_connection

    def read_embedding(self, event_id: str) -> np.ndarray | None:
        """
        Read 768-dim embedding from st_vec BLOB.
        Returns None if embedding not found or not READY.
        """
        cursor = self.db.execute("""
            SELECT vector FROM st_vec
            WHERE event_id = ? AND status IN ('READY', 'INDEXED')
        """, (event_id,))
        row = cursor.fetchone()
        if row and row['vector']:
            return np.array(struct.unpack('<768f', row['vector']))
        return None

    def batch_read(self, event_ids: List[str]) -> dict[str, np.ndarray]:
        """Batch read embeddings for multiple events."""
        placeholders = ','.join('?' * len(event_ids))
        cursor = self.db.execute(f"""
            SELECT event_id, vector FROM st_vec
            WHERE event_id IN ({placeholders}) AND status IN ('READY', 'INDEXED')
        """, event_ids)
        return {
            row['event_id']: np.array(struct.unpack('<768f', row['vector']))
            for row in cursor
        }
```

**Acceptance Criteria**:

- [ ] st_vec BLOB reading with struct.unpack
- [ ] 768-dimensional output (UltraBERT dimension)
- [ ] Batch reading for performance
- [ ] Handle missing embeddings gracefully
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/embedding_reader.py`
- `tests/k0/modules/consolidation/test_embedding_reader.py`

---

#### Issue 3.1.2: Implement Distance Calculator

**Type**: Implementation
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Compute composite distance for clustering.

**Implementation Requirements**:

```python
# k0/modules/consolidation/distance_calculator.py

class DistanceCalculator:
    def __init__(
        self,
        semantic_weight: float = 0.6,
        temporal_weight: float = 0.2,
        location_weight: float = 0.1,
        participant_weight: float = 0.1
    ):
        self.weights = {...}

    def compute_semantic_distance(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """Cosine distance: 1 - cosine_similarity"""

    def compute_temporal_distance(
        self,
        time1: str,
        time2: str,
        max_hours: float = 168  # 1 week
    ) -> float:
        """Normalized time difference"""

    def compute_location_distance(
        self,
        loc1: dict,
        loc2: dict
    ) -> float:
        """Haversine distance (normalized to 50km)"""

    def compute_participant_distance(
        self,
        participants1: List[str],
        participants2: List[str]
    ) -> float:
        """Jaccard distance on participant sets"""

    def compute_composite_distance(
        self,
        event1: dict,
        event2: dict,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """Weighted combination of all distances"""
```

**Acceptance Criteria**:

- [ ] All 4 distance types implemented
- [ ] Weighted combination
- [ ] Haversine formula for GPS
- [ ] Jaccard for participants
- [ ] Unit tests with edge cases

**Files to Create**:

- `k0/modules/consolidation/distance_calculator.py`
- `tests/k0/modules/consolidation/test_distance_calculator.py`

---

#### Issue 3.1.3: Implement DBSCAN Clusterer

**Type**: Implementation
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Cluster events using DBSCAN on composite distance.

**Implementation Requirements**:

```python
# k0/modules/consolidation/episodic_clusterer.py

class EpisodicClusterer:
    def __init__(
        self,
        eps: float = 0.3,
        min_samples: int = 3
    ):
        self.eps = eps
        self.min_samples = min_samples

    async def cluster_events(
        self,
        events: List[dict],
        embeddings: np.ndarray,
        distance_calculator: DistanceCalculator
    ) -> ClusteringResult:
        """
        Run DBSCAN clustering on events.

        Returns:
            ClusteringResult with:
            - clusters: {cluster_id: [event_ids]}
            - noise_events: [event_ids] (outliers)
            - cluster_confidences: {event_id: confidence}
        """

    def compute_cluster_confidence(
        self,
        event_embedding: np.ndarray,
        cluster_centroid: np.ndarray
    ) -> float:
        """Confidence = cosine similarity to cluster centroid"""
```

**Acceptance Criteria**:

- [ ] DBSCAN with precomputed distance matrix
- [ ] Cluster ID generation (CLU_<hash>_<date>)
- [ ] Confidence scoring
- [ ] Noise/outlier handling
- [ ] Performance: <3 minutes for 1000 events
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/episodic_clusterer.py`
- `tests/k0/modules/consolidation/test_episodic_clusterer.py`

---

### Epic 3.2: Pattern Extraction (R2.2)

**Description**: Extract semantic patterns from episode clusters.

#### Issue 3.2.1: Implement Common Element Extractor

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Extract shared features across events in a cluster.

**Implementation Requirements**:

```python
# k0/modules/consolidation/common_element_extractor.py

class CommonElementExtractor:
    def extract_common_elements(
        self,
        cluster_events: List[dict]
    ) -> CommonElements:
        """
        Extract invariants from cluster.

        Returns CommonElements with:
        - activity_type (mode)
        - location_name (mode)
        - time_of_day (average hour:minute)
        - day_of_week (mode)
        - core_participants (>50% occurrence)
        - median_duration
        - avg_sentiment
        - key_phrases (frequent n-grams)

        Each element has confidence = frequency / n
        """

    def extract_frequent_ngrams(
        self,
        events: List[dict],
        n: int = 3,
        min_frequency: int = 2
    ) -> List[str]:
        """Extract frequent n-word phrases from text."""
```

**Acceptance Criteria**:

- [ ] All common elements extracted
- [ ] Confidence per element
- [ ] N-gram extraction
- [ ] Handle missing fields gracefully
- [ ] Unit tests with fixtures

**Files to Create**:

- `k0/modules/consolidation/common_element_extractor.py`
- `tests/k0/modules/consolidation/test_common_element_extractor.py`

---

#### Issue 3.2.2: Implement Temporal Pattern Detector

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Detect temporal recurrence patterns.

**Implementation Requirements**:

```python
# k0/modules/consolidation/temporal_pattern_detector.py

class TemporalPatternDetector:
    def detect_pattern(
        self,
        cluster_events: List[dict]
    ) -> TemporalPattern:
        """
        Detect recurrence pattern from timestamps.

        Returns TemporalPattern with:
        - pattern_type: daily|weekly|monthly|irregular
        - recurrence_interval_days
        - recurrence_confidence (1 - CV)
        - next_predicted_time
        - most_common_day (for weekly)
        """

    def classify_pattern_type(
        self,
        mean_interval: float,
        coefficient_of_variation: float
    ) -> str:
        """
        Classify based on interval:
        - 0.8-1.2 days → daily
        - 6.5-7.5 days → weekly
        - 28-32 days → monthly
        - CV > 0.15 → irregular
        """
```

**Acceptance Criteria**:

- [ ] Pattern type classification
- [ ] Coefficient of variation calculation
- [ ] Next occurrence prediction
- [ ] Handle <3 events (insufficient data)
- [ ] Unit tests for each pattern type

**Files to Create**:

- `k0/modules/consolidation/temporal_pattern_detector.py`
- `tests/k0/modules/consolidation/test_temporal_pattern_detector.py`

---

#### Issue 3.2.3: Implement Pattern Confidence Scorer

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Compute confidence score for extracted patterns.

**Implementation Requirements**:

```python
# k0/modules/consolidation/pattern_confidence_scorer.py

class PatternConfidenceScorer:
    def compute_confidence(
        self,
        cluster_events: List[dict],
        common_elements: CommonElements,
        temporal_pattern: TemporalPattern
    ) -> float:
        """
        Compute pattern confidence using geometric mean.

        Formula:
        confidence = sqrt(frequency_score * consistency_score * significance_score)

        Where:
        - frequency_score = min(1.0, log(n+1) / log(10))
        - consistency_score = avg(element_confidences)
        - significance_score = (recurrence_confidence + spatial_tightness) / 2
        """
```

**Acceptance Criteria**:

- [ ] Geometric mean formula
- [ ] All 3 component scores
- [ ] Range [0.0, 1.0]
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/pattern_confidence_scorer.py`
- `tests/k0/modules/consolidation/test_pattern_confidence_scorer.py`

---

#### Issue 3.2.4: Implement Pattern Name Generator

**Type**: Implementation
**Priority**: Medium
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Generate human-readable pattern names.

**Implementation Requirements**:

```python
# k0/modules/consolidation/pattern_name_generator.py

def generate_pattern_name(common_elements: CommonElements) -> str:
    """
    Generate readable name like:
    - "Tuesday morning yoga at CorePower"
    - "Weekly coffee with Sarah"
    - "Daily commute to office"

    Format: [day?] [time_of_day?] [activity] [at location?] [with participants?]
    """
```

**Acceptance Criteria**:

- [ ] Readable name generation
- [ ] Handle missing components
- [ ] Max length 100 chars
- [ ] Unit tests with examples

**Files to Create**:

- `k0/modules/consolidation/pattern_name_generator.py`
- `tests/k0/modules/consolidation/test_pattern_name_generator.py`

---

### Epic 3.3: CA1 Bridge (R2.3)

**Description**: Implement merge/evolve/create decisions for semantic patterns.

#### Issue 3.3.1: Implement Semantic Similarity Calculator

**Type**: Implementation
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Compute similarity between new pattern and existing semantics.

**Implementation Requirements**:

```python
# k0/modules/consolidation/semantic_similarity.py

class SemanticSimilarityCalculator:
    async def find_similar_semantics(
        self,
        pattern: ExtractedPattern,
        tenant_id: str,
        space_id: str,
        threshold: float = 0.6
    ) -> List[SimilarSemantic]:
        """
        Query existing st_sem records and compute similarity.

        Returns list of (semantic_id, similarity_score) sorted desc.
        """

    def compute_pattern_similarity(
        self,
        pattern1_embedding: np.ndarray,
        pattern2_embedding: np.ndarray,
        pattern1_elements: dict,
        pattern2_elements: dict
    ) -> float:
        """
        Composite similarity:
        - 0.7 * cosine_similarity(embeddings)
        - 0.3 * jaccard_similarity(elements)
        """
```

**Acceptance Criteria**:

- [ ] st_sem query by pattern_type
- [ ] Embedding similarity (cosine)
- [ ] Element overlap (Jaccard)
- [ ] Threshold filtering
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/semantic_similarity.py`
- `tests/k0/modules/consolidation/test_semantic_similarity.py`

---

#### Issue 3.3.2: Implement CA1 Bridge Decision Maker

**Type**: Implementation
**Priority**: Critical
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Make MERGE/EVOLVE/CREATE decisions for patterns.

**Implementation Requirements**:

```python
# k0/modules/consolidation/ca1_bridge.py

class CA1Bridge:
    def __init__(
        self,
        merge_threshold: float = 0.85,
        evolve_threshold: float = 0.60
    ):
        self.merge_threshold = merge_threshold
        self.evolve_threshold = evolve_threshold

    async def decide(
        self,
        pattern: ExtractedPattern,
        similar_semantics: List[SimilarSemantic]
    ) -> BridgeDecision:
        """
        Make decision based on similarity:
        - >0.85: MERGE (update existing)
        - 0.6-0.85: EVOLVE (new version)
        - <0.6: CREATE (new record)

        Returns BridgeDecision with:
        - action: MERGE|EVOLVE|CREATE
        - target_semantic_id (for MERGE/EVOLVE)
        - confidence
        """

    def resolve_multiple_matches(
        self,
        matches: List[SimilarSemantic]
    ) -> SimilarSemantic:
        """
        If multiple matches >0.85, pick highest similarity.
        If multiple matches 0.6-0.85, flag for Active Learning.
        """
```

**Acceptance Criteria**:

- [ ] MERGE/EVOLVE/CREATE logic
- [ ] Threshold enforcement
- [ ] Multiple match resolution
- [ ] Active Learning flag for ambiguity
- [ ] Unit tests for each decision path

**Files to Create**:

- `k0/modules/consolidation/ca1_bridge.py`
- `tests/k0/modules/consolidation/test_ca1_bridge.py`

---

### Epic 3.4: Consolidation Criteria (R2.4-R2.5)

**Description**: Implement quality gates and semantic promotion.

#### Issue 3.4.1: Implement Criteria Checker

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Filter patterns that pass quality gates.

**Implementation Requirements**:

```python
# k0/modules/consolidation/criteria_checker.py

class CriteriaChecker:
    def __init__(
        self,
        min_confidence: float = 0.6,
        min_observations: int = 3,
        min_temporal_span_days: int = 7
    ):
        self.criteria = {...}

    def check_pattern(
        self,
        pattern: ExtractedPattern,
        decision: BridgeDecision
    ) -> CriteriaResult:
        """
        Check if pattern passes quality gates.

        Returns CriteriaResult with:
        - passed: bool
        - failed_criteria: [list of failed checks]
        - recommendation: 'promote'|'reject'|'defer_to_active_learning'
        """
```

**Acceptance Criteria**:

- [ ] All quality gates implemented
- [ ] Rejection reason tracking
- [ ] Active Learning deferral
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/criteria_checker.py`
- `tests/k0/modules/consolidation/test_criteria_checker.py`

---

#### Issue 3.4.2: Implement Semantic Promoter

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r2`

**Description**:
Handle promotion of patterns to semantic layer.

**Implementation Requirements**:

```python
# k0/modules/consolidation/semantic_promoter.py

class SemanticPromoter:
    async def promote_patterns(
        self,
        approved_decisions: List[Tuple[ExtractedPattern, BridgeDecision]]
    ) -> List[PromotionRecord]:
        """
        Create promotion records for approved patterns.

        Returns list of PromotionRecord with:
        - source_episode_ids
        - target_semantic_id (new or existing)
        - promotion_type: MERGE|EVOLVE|CREATE
        """

    async def update_episode_backlinks(
        self,
        promotions: List[PromotionRecord]
    ) -> int:
        """
        Update st_epi.promoted_to_semantic_id for source episodes.
        Returns count of updated episodes.
        """
```

**Acceptance Criteria**:

- [ ] Promotion record creation
- [ ] Episode backlink updates
- [ ] Event emission (p03.pattern.promoted.v1)
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/semantic_promoter.py`
- `tests/k0/modules/consolidation/test_semantic_promoter.py`

---

### Epic 3.5: K0 Architecture Master - R2 Module Registration

**Description**: Register all Milestone 3 (R2) modules in K0 Architecture Master.

#### Issue 3.5.1: Update K0 Module Registry - R2 Components

**Type**: Documentation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `k0-governance`, `documentation`, `p03`

**Description**:
Register all R2 pattern extraction modules in K0 Architecture Master Part 3.1.

**K0 Registration Requirements**:

1. **Part 3.1 - Module Registry** - Add entries for:

| Module | Type | Status | Layer | Pipelines | Lifecycle |
|--------|------|--------|-------|-----------|-----------|
| `consolidation.embedding_reader` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.episodic_clusterer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.pattern_extractor` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.bridge_scorer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.novelty_scorer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.consolidation_decider` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.episode_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.semantic_promoter` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |

2. **Part 5.2 - Syscall Matrix** - Add syscall entries:

| Syscall | Target | Operation | Module | Band |
|---------|--------|-----------|--------|------|
| `st_vec.read_embeddings` | Storage | READ | embedding_reader | GREEN |
| `st_epi.create_episode` | Storage | WRITE | episode_writer | GREEN |
| `st_epi.update_backlinks` | Storage | WRITE | episode_writer | GREEN |
| `st_sem.check_exists` | Storage | READ | semantic_promoter | GREEN |
| `st_sem.create_semantic` | Storage | WRITE | semantic_promoter | YELLOW |
| `st_bridge_candidates.read` | Storage | READ | bridge_scorer | GREEN |
| `st_bridge_candidates.write` | Storage | WRITE | bridge_scorer | GREEN |

3. **Part 4.1 - Event Topics Registry** - Add event topics:

| Topic | Publisher | Subscribers | Schema | Band |
|-------|-----------|-------------|--------|------|
| `consolidation.clustering.completed.v1` | episodic_clusterer | pattern_extractor | ClusteringCompleted | GREEN |
| `consolidation.patterns.extracted.v1` | pattern_extractor | bridge_scorer | PatternsExtracted | GREEN |
| `consolidation.episode.created.v1` | episode_writer | orchestrator | EpisodeCreated | GREEN |
| `consolidation.pattern.promoted.v1` | semantic_promoter | orchestrator | PatternPromoted | YELLOW |

**Acceptance Criteria**:

- [ ] All R2 modules added to Part 3.1 Module Registry
- [ ] Syscalls added to Part 5.2 Syscall Matrix
- [ ] Event topics added to Part 4.1 Event Topics Registry
- [ ] Cross-references to R0/R1 modules verified
- [ ] Status set to ⚠️ Implementation

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 3.1, 4.1, 5.2)

---

### Milestone 3 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 3 complete, verify these K0 updates:

**K0 Closure Checklist for M3**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 3.1 | Module Master Registry | Add 8 R2 modules (embedding_reader → semantic_promoter) | ☐ |
| 4.1 | Event Topics Registry | Add 4 consolidation event topics | ☐ |
| 5.2 | Syscall Matrix | Add 7 R2 syscalls (st_vec, st_epi, st_sem, st_bridge) | ☐ |
| 5.3 | Storage Tables | Verify bridge_candidates table entry | ☐ |
| 7.1 | ADR Index | Update k010.3-p03 (episodic) to ✅ Accepted | ☐ |
| 7.1 | ADR Index | Update k010.4-p03 (patterns) to ✅ Accepted | ☐ |

**Commit Message Format**: `docs(k0): M3 complete - 8 R2 modules, 4 events, 7 syscalls registered`

---

## Milestone 4: Memory Management (R3)

**Goal**: Implement synaptic homeostasis - deduplication, novelty, retention, decay.
**Duration**: 4-5 days
**Gate**: GATE 3 (Implementation)

### Epic 4.1: Near-Duplicate Detection (R3.1)

**Description**: Implement SimHash-based deduplication.

#### Issue 4.1.1: Implement SimHash Calculator

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r3`

**Description**:
Calculate SimHash fingerprints for events.

**Implementation Requirements**:

```python
# k0/modules/consolidation/simhash_calculator.py

class SimHashCalculator:
    def __init__(self, hash_bits: int = 128):
        self.hash_bits = hash_bits

    def compute_simhash(self, text: str) -> int:
        """
        Compute SimHash fingerprint for text.
        Algorithm:
        1. Tokenize into 3-grams
        2. Hash each 3-gram with MurmurHash3
        3. Create weighted bit vector
        4. Threshold to binary
        """

    def hamming_distance(self, hash1: int, hash2: int) -> int:
        """Count differing bits between two hashes."""

    def batch_compute(self, texts: List[str]) -> List[int]:
        """Vectorized SimHash computation."""
```

**Acceptance Criteria**:

- [ ] 128-bit SimHash implementation
- [ ] Hamming distance calculation
- [ ] Batch processing
- [ ] Performance: <1 second for 1000 texts
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/simhash_calculator.py`
- `tests/k0/modules/consolidation/test_simhash_calculator.py`

---

#### Issue 4.1.2: Implement LSH Index

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r3`

**Description**:
Build LSH index for O(n) near-duplicate search.

**Implementation Requirements**:

```python
# k0/modules/consolidation/lsh_index.py

class LSHIndex:
    def __init__(
        self,
        num_bands: int = 8,
        rows_per_band: int = 16  # 8 * 16 = 128 bits
    ):
        self.num_bands = num_bands
        self.rows_per_band = rows_per_band
        self.buckets: Dict[int, List[str]] = {}

    def index(self, event_id: str, simhash: int) -> None:
        """Add event to LSH index."""

    def query(self, simhash: int, max_hamming: int = 3) -> List[str]:
        """Find candidate duplicates with Hamming ≤ max_hamming."""

    def batch_index(self, events: List[Tuple[str, int]]) -> None:
        """Batch index events."""
```

**Acceptance Criteria**:

- [ ] Band-based hashing
- [ ] O(1) bucket lookup
- [ ] Configurable bands/rows
- [ ] Memory-efficient buckets
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/lsh_index.py`
- `tests/k0/modules/consolidation/test_lsh_index.py`

---

#### Issue 4.1.3: Implement Duplicate Detector

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r3`

**Description**:
Orchestrate near-duplicate detection pipeline.

**Implementation Requirements**:

```python
# k0/modules/consolidation/duplicate_detector.py

class DuplicateDetector:
    def __init__(
        self,
        hamming_threshold: int = 3,
        jaccard_threshold: float = 0.8
    ):
        self.hamming_threshold = hamming_threshold
        self.jaccard_threshold = jaccard_threshold

    async def detect_duplicates(
        self,
        events: List[dict]
    ) -> DeduplicationResult:
        """
        Full deduplication pipeline:
        1. Build LSH index on SimHash
        2. For each event, query candidates
        3. Confirm with Jaccard similarity on shingles
        4. Select canonical (highest salience)
        5. Mark non-canonical as is_near_duplicate=True

        Returns DeduplicationResult with:
        - duplicate_groups: [[event_ids]]
        - canonical_mapping: {event_id: canonical_id}
        - near_duplicates_json per event
        """

    def compute_jaccard_similarity(
        self,
        text1: str,
        text2: str,
        shingle_size: int = 3
    ) -> float:
        """Jaccard similarity on word shingles."""
```

**Acceptance Criteria**:

- [ ] Full pipeline orchestration
- [ ] Jaccard confirmation step
- [ ] Canonical selection (highest salience)
- [ ] Performance: <3 minutes for 1000 events
- [ ] Unit tests with duplicate fixtures

**Files to Create**:

- `k0/modules/consolidation/duplicate_detector.py`
- `tests/k0/modules/consolidation/test_duplicate_detector.py`

---

### Epic 4.2: Novelty Scoring (R3.2)

**Description**: Compute novelty scores based on uniqueness.

#### Issue 4.2.1: Implement Novelty Scorer

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r3`

**Description**:
Score events by novelty/uniqueness.

**Implementation Requirements**:

```python
# k0/modules/consolidation/novelty_scorer.py

class NoveltyScorer:
    def __init__(
        self,
        high_threshold: float = 0.8,
        low_threshold: float = 0.3,
        time_window_days: int = 30
    ):
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold

    def compute_novelty(
        self,
        event: dict,
        dedup_result: DeduplicationResult
    ) -> float:
        """
        Compute novelty score [0.0, 1.0].

        Formula:
        base = 1.0 - (duplicate_count / window_count)
        adjusted = base + salience_boost - exact_duplicate_penalty

        Where:
        - salience_boost = 0.1 if salience_score > 0.8
        - exact_duplicate_penalty = 0.5 if is_exact_duplicate
        """

    def classify_tier(self, novelty_score: float) -> str:
        """Classify: HIGH (>0.8), MEDIUM (0.3-0.8), LOW (<0.3)"""
```

**Acceptance Criteria**:

- [ ] Novelty formula implemented
- [ ] Tier classification
- [ ] Salience boost integration
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/novelty_scorer.py`
- `tests/k0/modules/consolidation/test_novelty_scorer.py`

---

### Epic 4.3: Retention Policy (R3.3)

**Description**: Enforce retention policies with novelty adjustment.

#### Issue 4.3.1: Create Retention Policy Matrix

**Type**: Configuration
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `config`, `p03`, `r3`

**Description**:
Define retention policy matrix for all band/topic/device combinations.

**Policy Matrix**:

| Band | Default Retention | Novelty HIGH | Novelty LOW |
|------|-------------------|--------------|-------------|
| GREEN | 90 days | 180 days | 45 days |
| YELLOW | 365 days | 730 days | 180 days |
| RED | 7 years | 10 years | 5 years |

**Acceptance Criteria**:

- [ ] Policy YAML created
- [ ] All combinations covered
- [ ] Schema validation
- [ ] Unit tests for lookup

**Files to Create**:

- `k0/config/retention_policies.yaml`

---

#### Issue 4.3.2: Implement Retention Enforcer

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r3`

**Description**:
Apply retention policies to events.

**Implementation Requirements**:

```python
# k0/modules/consolidation/retention_enforcer.py

class RetentionEnforcer:
    def __init__(self, policy_path: str):
        self.policies = load_retention_policies(policy_path)

    def compute_archival_deadline(
        self,
        event: dict,
        novelty_tier: str
    ) -> datetime:
        """
        Compute archival_deadline for event.

        base_days = lookup(band, topic, device_kind)
        adjustment = novelty_adjustment[novelty_tier]  # 2.0, 1.0, 0.5
        final_days = base_days * adjustment
        return event_time + timedelta(days=final_days)
        """

    def batch_compute_deadlines(
        self,
        events: List[dict],
        novelty_scores: Dict[str, float]
    ) -> Dict[str, datetime]:
        """Batch compute archival deadlines."""
```

**Acceptance Criteria**:

- [ ] Policy lookup
- [ ] Novelty adjustment
- [ ] Batch processing
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/retention_enforcer.py`
- `tests/k0/modules/consolidation/test_retention_enforcer.py`

---

### Epic 4.4: Decay Application (R3.4)

**Description**: Apply exponential decay to memory strength.

#### Issue 4.4.1: Implement Decay Calculator

**Type**: Implementation
**Priority**: Medium
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r3`

**Description**:
Calculate and apply decay factors.

**Implementation Requirements**:

```python
# k0/modules/consolidation/decay_calculator.py

class DecayCalculator:
    def __init__(
        self,
        default_half_life_days: float = 30.0,
        decay_floor: float = 0.1
    ):
        self.default_half_life = default_half_life_days
        self.decay_floor = decay_floor

    def compute_decay_factor(
        self,
        days_since_access: float,
        half_life_days: float = None
    ) -> float:
        """
        Exponential decay formula.
        decay = max(floor, exp(-λ * t))
        where λ = ln(2) / half_life
        """

    def batch_apply_decay(
        self,
        events: List[dict]
    ) -> List[Tuple[str, float]]:
        """
        Apply decay to batch of events.
        Returns [(event_id, new_decay_factor), ...]
        """
```

**Acceptance Criteria**:

- [ ] Exponential decay formula
- [ ] Decay floor enforcement
- [ ] Configurable half-life per band
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/decay_calculator.py`
- `tests/k0/modules/consolidation/test_decay_calculator.py`

---

### Epic 4.5: Archive/Tombstone (R3.5)

**Description**: Archive old events and create tombstones.

#### Issue 4.5.1: Implement Archiver

**Type**: Implementation
**Priority**: Medium
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r3`

**Description**:
Archive events past retention deadline.

**Implementation Requirements**:

```python
# k0/modules/consolidation/archiver.py

class Archiver:
    def __init__(self, compression_level: int = 6):
        self.compression_level = compression_level

    async def archive_events(
        self,
        event_ids: List[str]
    ) -> ArchiveResult:
        """
        Archive events to st_archived_events.

        Process:
        1. Select full event data
        2. Compress with zlib
        3. INSERT into st_archived_events
        4. DELETE from st_hipp_events
        5. Emit p03.event.archived.v1
        """

    def compress_event(self, event: dict) -> bytes:
        """Compress event JSON with zlib."""

    def decompress_event(self, compressed: bytes) -> dict:
        """Decompress for retrieval."""
```

**Acceptance Criteria**:

- [ ] zlib compression
- [ ] Archive table structure
- [ ] Atomic archive + delete
- [ ] Event emission
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/archiver.py`
- `tests/k0/modules/consolidation/test_archiver.py`

---

#### Issue 4.5.2: Implement Tombstone Manager

**Type**: Implementation
**Priority**: Medium
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r3`, `gdpr`

**Description**:
Create tombstone records for GDPR compliance.

**Implementation Requirements**:

```python
# k0/modules/consolidation/tombstone_manager.py

class TombstoneManager:
    def __init__(self, tombstone_retention_days: int = 90):
        self.retention_days = tombstone_retention_days

    async def create_tombstone(
        self,
        event_id: str,
        reason: str,  # 'retention_expired' | 'user_deleted' | 'gdpr_request'
        deleted_at: datetime
    ) -> Tombstone:
        """
        Create tombstone record preserving:
        - event_id, tenant_id, space_id
        - event_time_utc, band
        - deletion_reason, deleted_at
        - tombstone_expires_at (deleted_at + 90 days)
        """

    async def purge_expired_tombstones(self) -> int:
        """Delete tombstones older than retention period. Returns count."""
```

**Acceptance Criteria**:

- [ ] Tombstone record creation
- [ ] Metadata preservation
- [ ] Expiration tracking
- [ ] GDPR compliance
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/tombstone_manager.py`
- `tests/k0/modules/consolidation/test_tombstone_manager.py`

---

### Epic 4.6: K0 Architecture Master - R3 Module Registration

**Description**: Register all Milestone 4 (R3) homeostasis modules in K0 Architecture Master.

#### Issue 4.6.1: Update K0 Module Registry - R3 Components

**Type**: Documentation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `k0-governance`, `documentation`, `p03`

**Description**:
Register all R3 synaptic homeostasis modules in K0 Architecture Master Part 3.1.

**K0 Registration Requirements**:

1. **Part 3.1 - Module Registry** - Add entries for:

| Module | Type | Status | Layer | Pipelines | Lifecycle |
|--------|------|--------|-------|-----------|-----------|
| `consolidation.simhash_calculator` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.duplicate_detector` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.novelty_scorer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.retention_policy` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.decay_applicator` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.event_archiver` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.tombstone_manager` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |

2. **Part 5.2 - Syscall Matrix** - Add syscall entries:

| Syscall | Target | Operation | Module | Band |
|---------|--------|-----------|--------|------|
| `st_hipp_events.read_for_dedup` | Storage | READ | duplicate_detector | GREEN |
| `st_hipp_events.mark_duplicate` | Storage | WRITE | duplicate_detector | GREEN |
| `st_hipp_events.apply_decay` | Storage | WRITE | decay_applicator | GREEN |
| `st_hipp_events.archive` | Storage | WRITE | event_archiver | GREEN |
| `st_archive.write` | Storage | WRITE | event_archiver | GREEN |
| `st_tombstones.create` | Storage | WRITE | tombstone_manager | YELLOW |
| `st_tombstones.purge_expired` | Storage | DELETE | tombstone_manager | YELLOW |

3. **Part 4.1 - Event Topics Registry** - Add event topics:

| Topic | Publisher | Subscribers | Schema | Band |
|-------|-----------|-------------|--------|------|
| `consolidation.dedup.completed.v1` | duplicate_detector | orchestrator | DedupCompleted | GREEN |
| `consolidation.decay.applied.v1` | decay_applicator | orchestrator | DecayApplied | GREEN |
| `consolidation.events.archived.v1` | event_archiver | orchestrator | EventsArchived | GREEN |
| `consolidation.tombstone.created.v1` | tombstone_manager | audit_log | TombstoneCreated | YELLOW |

**Acceptance Criteria**:

- [ ] All R3 modules added to Part 3.1 Module Registry
- [ ] Syscalls added to Part 5.2 Syscall Matrix (including YELLOW band for tombstones)
- [ ] Event topics added to Part 4.1 Event Topics Registry
- [ ] GDPR-related syscalls documented with YELLOW band
- [ ] Status set to ⚠️ Implementation

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 3.1, 4.1, 5.2)

---

### Milestone 4 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 4 complete, verify these K0 updates:

**K0 Closure Checklist for M4**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 3.1 | Module Master Registry | Add 6 R3 modules (simhash_calc → tombstone_manager) | ☐ |
| 4.1 | Event Topics Registry | Add 4 R3 event topics (dedup, decay, archive, tombstone) | ☐ |
| 5.2 | Syscall Matrix | Add 8 R3 syscalls (mark YELLOW for GDPR ops) | ☐ |
| 5.3 | Storage Tables | Add tombstones, archive tables | ☐ |
| 7.1 | ADR Index | Update k010.5-p03 (simhash) to ✅ Accepted | ☐ |
| 7.1 | ADR Index | Update k010.6-p03 (retention) to ✅ Accepted | ☐ |
| 7.1 | ADR Index | Update k010.7-p03 (GDPR) to ✅ Accepted | ☐ |

**Commit Message Format**: `docs(k0): M4 complete - 6 R3 modules, GDPR syscalls, retention ADRs accepted`

---

## Milestone 5: Knowledge Graph (R4)

**Goal**: Implement entity extraction, relationship discovery, and KG construction.
**Duration**: 5-6 days
**Gate**: GATE 3 (Implementation)

### Epic 5.1: Entity Extraction (R4.1)

**Description**: Extract and normalize entities from events.

#### Issue 5.1.1: Implement Entity Reader

**Type**: Implementation
**Priority**: Critical
**Assignee**: NLP Engineer
**Labels**: `implementation`, `p03`, `r4`, `nlp`

**Description**:
Read pre-extracted entities from st_hipp_events.entities_json (computed by P02 UltraBERT).

**Implementation Requirements**:

```python
# k0/modules/consolidation/entity_reader.py
import json
from typing import List
from dataclasses import dataclass

@dataclass
class Entity:
    text: str
    label: str  # PERSON, ORG, GPE, DATE, TIME, KINSHIP, FAMILY_EVENT, etc.
    confidence: float = 0.8
    source: str = "ultrabert"  # Always UltraBERT in our stack

class EntityReader:
    """
    Read pre-extracted entities from st_hipp_events.entities_json.

    NOTE: P03 does NOT call any NER model.
    P02 M02 extracts entities via UltraBERT single-pass and stores in entities_json.
    UltraBERT provides 21 entity types: 9 general + 12 family-specific.
    """

    def read_entities(self, event_row: dict) -> List[Entity]:
        """
        Parse entities_json from st_hipp_events.

        entities_json format: ["person_mom", "person_dad", "org_olive_garden"]
        OR detailed format: [{"text": "Mom", "label": "KINSHIP", "confidence": 0.95}, ...]
        """
        entities_json = event_row.get('entities_json')
        if not entities_json:
            return []

        entities_data = json.loads(entities_json)
        entities = []

        for item in entities_data:
            if isinstance(item, dict):
                entities.append(Entity(
                    text=item.get('text', ''),
                    label=item.get('label', 'UNKNOWN'),
                    confidence=item.get('confidence', 0.8),
                    source='ultrabert'
                ))
            else:
                # Simple string format: "person_mom" -> parse prefix
                parts = str(item).split('_', 1)
                label = parts[0].upper() if parts else 'UNKNOWN'
                text = parts[1] if len(parts) > 1 else item
                entities.append(Entity(text=text, label=label))

        return entities

    def batch_read(self, event_rows: List[dict]) -> dict[str, List[Entity]]:
        """Batch read entities for multiple events."""
        return {
            row['event_id']: self.read_entities(row)
            for row in event_rows
        }
```

**Acceptance Criteria**:

- [ ] Parse entities_json from st_hipp_events
- [ ] Handle both simple and detailed entity formats
- [ ] Batch processing for performance
- [ ] Entity type classification
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/entity_reader.py`
- `tests/k0/modules/consolidation/test_entity_reader.py`

---

#### Issue 5.1.2: Implement Entity Normalizer

**Type**: Implementation
**Priority**: Critical
**Assignee**: NLP Engineer
**Labels**: `implementation`, `p03`, `r4`, `nlp`

**Description**:
Normalize entities to canonical forms and deduplicate.

**Implementation Requirements**:

```python
# k0/modules/consolidation/entity_normalizer.py

class EntityNormalizer:
    def __init__(self, fuzzy_threshold: float = 0.85):
        self.fuzzy_threshold = fuzzy_threshold

    async def normalize(
        self,
        entity: Entity,
        tenant_id: str,
        space_id: str
    ) -> NormalizedEntity:
        """
        Normalize entity to canonical form.

        Process:
        1. Query st_kg_dom for existing nodes of same type
        2. Exact match → return canonical_node_id
        3. Fuzzy match (Levenshtein > 0.85) → add alias, return canonical
        4. No match → mark for new node creation
        """

    def compute_fuzzy_similarity(
        self,
        text1: str,
        text2: str
    ) -> float:
        """Levenshtein ratio normalized to [0,1]."""

    async def batch_normalize(
        self,
        entities: List[Entity],
        tenant_id: str,
        space_id: str
    ) -> List[NormalizedEntity]:
        """Batch normalization with caching."""
```

**Acceptance Criteria**:

- [ ] Exact match lookup
- [ ] Fuzzy matching with Levenshtein
- [ ] Alias management
- [ ] Node creation marking
- [ ] Performance: <2 minutes for 150 entities
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/entity_normalizer.py`
- `tests/k0/modules/consolidation/test_entity_normalizer.py`

---

### Epic 5.2: Relationship Discovery (R4.2)

**Description**: Discover relationships between entities.

#### Issue 5.2.1: Implement Co-occurrence Detector

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r4`

**Description**:
Detect entity co-occurrence relationships.

**Implementation Requirements**:

```python
# k0/modules/consolidation/cooccurrence_detector.py

class CooccurrenceDetector:
    def detect_cooccurrences(
        self,
        events: List[dict],
        entity_mapping: Dict[str, List[NormalizedEntity]]
    ) -> List[Relationship]:
        """
        Detect co-occurrence relationships.

        Rule: Entities in same event → co_occurs_with edge

        Returns relationships with:
        - source_node_id
        - target_node_id
        - relationship_type: 'co_occurs_with'
        - strength: count / max_count
        - observation_count
        """

    def aggregate_cooccurrences(
        self,
        raw_cooccurrences: List[Tuple[str, str]]
    ) -> Dict[Tuple[str, str], int]:
        """Aggregate co-occurrence counts."""
```

**Acceptance Criteria**:

- [ ] Co-occurrence detection
- [ ] Strength normalization
- [ ] Observation counting
- [ ] Bidirectional relationship handling
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/cooccurrence_detector.py`
- `tests/k0/modules/consolidation/test_cooccurrence_detector.py`

---

#### Issue 5.2.2: Implement Temporal Relationship Detector

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r4`

**Description**:
Detect temporal relationships between events/entities.

**Implementation Requirements**:

```python
# k0/modules/consolidation/temporal_relationship_detector.py

class TemporalRelationshipDetector:
    def __init__(self, proximity_hours: float = 1.0):
        self.proximity_hours = proximity_hours

    def detect_temporal_relationships(
        self,
        events: List[dict],
        entity_mapping: Dict[str, List[NormalizedEntity]]
    ) -> List[Relationship]:
        """
        Detect temporal relationships.

        Rules:
        - Events within proximity_hours → 'temporal_proximity' edge
        - Entity A precedes Entity B → 'precedes' edge
        - Activity A enables Activity B → 'enables' edge
        """

    def compute_temporal_confidence(
        self,
        time_diff_hours: float,
        occurrence_count: int
    ) -> float:
        """Confidence = recency_weight * consistency_weight"""
```

**Acceptance Criteria**:

- [ ] Temporal proximity detection
- [ ] Precedence relationships
- [ ] Confidence scoring
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/temporal_relationship_detector.py`
- `tests/k0/modules/consolidation/test_temporal_relationship_detector.py`

---

### Epic 5.3: Graph Updates (R4.3-R4.5)

**Description**: Update knowledge graph with extracted entities and relationships.

#### Issue 5.3.1: Implement Graph Node Manager

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r4`

**Description**:
Manage st_kg_dom node operations.

**Implementation Requirements**:

```python
# k0/modules/consolidation/graph_node_manager.py

class GraphNodeManager:
    async def create_node(
        self,
        entity: NormalizedEntity,
        tenant_id: str,
        space_id: str
    ) -> str:
        """
        Create new node in st_kg_dom via st_outbox.

        Returns node_id.
        """

    async def update_node(
        self,
        node_id: str,
        updates: Dict[str, Any]
    ) -> None:
        """Update existing node (last_observed_at, observation_count)."""

    async def add_alias(
        self,
        node_id: str,
        alias: str
    ) -> None:
        """Add alias to existing node."""

    async def batch_upsert_nodes(
        self,
        entities: List[NormalizedEntity],
        tenant_id: str,
        space_id: str
    ) -> Dict[str, str]:
        """Batch upsert, returns {entity_text: node_id}."""
```

**Acceptance Criteria**:

- [ ] Node creation via outbox
- [ ] Node updates
- [ ] Alias management
- [ ] Batch operations
- [ ] Idempotency
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/graph_node_manager.py`
- `tests/k0/modules/consolidation/test_graph_node_manager.py`

---

#### Issue 5.3.2: Implement Graph Edge Manager

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r4`

**Description**:
Manage st_kg_edges edge operations.

**Implementation Requirements**:

```python
# k0/modules/consolidation/graph_edge_manager.py

class GraphEdgeManager:
    async def create_edge(
        self,
        relationship: Relationship
    ) -> str:
        """
        Create new edge in st_kg_edges via st_outbox.

        Returns edge_id.
        """

    async def update_edge(
        self,
        edge_id: str,
        updates: Dict[str, Any]
    ) -> None:
        """Update edge (strength, observation_count, last_observed_at)."""

    async def find_existing_edge(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str
    ) -> Optional[str]:
        """Find existing edge between nodes."""

    async def batch_upsert_edges(
        self,
        relationships: List[Relationship]
    ) -> List[str]:
        """Batch upsert edges."""
```

**Acceptance Criteria**:

- [ ] Edge creation via outbox
- [ ] Edge updates (increment counts)
- [ ] Duplicate edge handling (upsert)
- [ ] Batch operations
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/graph_edge_manager.py`
- `tests/k0/modules/consolidation/test_graph_edge_manager.py`

---

#### Issue 5.3.3: Implement Causal Inference Engine

**Type**: Implementation
**Priority**: High
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r4`

**Description**:
Infer causal relationships from temporal patterns.

**Implementation Requirements**:

```python
# k0/modules/consolidation/causal_inference.py

class CausalInferenceEngine:
    def __init__(
        self,
        min_observations: int = 5,
        min_confidence: float = 0.6
    ):
        self.min_observations = min_observations
        self.min_confidence = min_confidence

    def detect_causal_relationships(
        self,
        event_sequences: List[List[dict]],
        relationships: List[Relationship]
    ) -> List[CausalRelationship]:
        """
        Infer causal relationships from temporal patterns.

        Criteria:
        1. Temporal precedence: A consistently precedes B
        2. Consistency: Low variance in temporal lag
        3. Frequency: ≥min_observations occurrences

        Returns causal edges with:
        - source_id, target_id
        - is_causal=True
        - causal_confidence
        - median_temporal_lag_hours
        """

    def compute_causal_confidence(
        self,
        precedence_count: int,
        total_observations: int,
        lag_coefficient_of_variation: float
    ) -> float:
        """
        confidence = (precedence_ratio) * (1 - CV)
        """
```

**Acceptance Criteria**:

- [ ] Temporal precedence detection
- [ ] Granger-like causality test
- [ ] Confidence scoring
- [ ] Minimum observation threshold
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/causal_inference.py`
- `tests/k0/modules/consolidation/test_causal_inference.py`

---

### Epic 5.4: K0 Architecture Master - R4 Module Registration

**Description**: Register all Milestone 5 (R4) knowledge graph modules in K0 Architecture Master.

#### Issue 5.4.1: Update K0 Module Registry - R4 Components

**Type**: Documentation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `k0-governance`, `documentation`, `p03`

**Description**:
Register all R4 knowledge graph modules in K0 Architecture Master Part 3.1.

**K0 Registration Requirements**:

1. **Part 3.1 - Module Registry** - Add entries for:

| Module | Type | Status | Layer | Pipelines | Lifecycle |
|--------|------|--------|-------|-----------|-----------|
| `consolidation.entity_reader` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.entity_normalizer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.relationship_discoverer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.graph_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.edge_strengthener` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.community_detector` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.causal_inference` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |

2. **Part 5.2 - Syscall Matrix** - Add syscall entries:

| Syscall | Target | Operation | Module | Band |
|---------|--------|-----------|--------|------|
| `st_hipp_events.read_entities` | Storage | READ | entity_reader | GREEN |
| `st_kg_nodes.create` | Storage | WRITE | entity_normalizer | GREEN |
| `st_kg_nodes.update` | Storage | WRITE | entity_normalizer | GREEN |
| `st_kg_edges.create` | Storage | WRITE | relationship_discoverer | GREEN |
| `st_kg_edges.update_weight` | Storage | WRITE | edge_strengthener | GREEN |
| `st_kg_community.assign` | Storage | WRITE | community_detector | GREEN |
| `st_kg_edges.set_causal` | Storage | WRITE | causal_inference | GREEN |

3. **Part 4.1 - Event Topics Registry** - Add event topics:

| Topic | Publisher | Subscribers | Schema | Band |
|-------|-----------|-------------|--------|------|
| `consolidation.entities.read.v1` | entity_reader | entity_normalizer | EntitiesRead | GREEN |
| `consolidation.relationships.discovered.v1` | relationship_discoverer | graph_writer | RelationshipsDiscovered | GREEN |
| `consolidation.graph.updated.v1` | graph_writer | community_detector | GraphUpdated | GREEN |
| `consolidation.communities.detected.v1` | community_detector | orchestrator | CommunitiesDetected | GREEN |

**Acceptance Criteria**:

- [ ] All R4 modules added to Part 3.1 Module Registry
- [ ] Knowledge graph syscalls added to Part 5.2 Syscall Matrix
- [ ] Event topics added to Part 4.1 Event Topics Registry
- [ ] Graph storage dependencies documented
- [ ] Status set to ⚠️ Implementation

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 3.1, 4.1, 5.2)

---

### Milestone 5 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 5 complete, verify these K0 updates:

**K0 Closure Checklist for M5**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 3.1 | Module Master Registry | Add 7 R4 modules (entity_reader → causal_inference) | ☐ |
| 4.1 | Event Topics Registry | Add 4 R4 KG event topics | ☐ |
| 5.2 | Syscall Matrix | Add 7 R4 KG syscalls (st_kg_*) | ☐ |
| 5.3 | Storage Tables | Add st_kg_nodes, st_kg_edges, st_kg_community | ☐ |
| 7.1 | ADR Index | Update k010.8-p03 (KG construction) to ✅ Accepted | ☐ |
| 7.1 | ADR Index | Update k010.9-p03 (causal inference) to ✅ Accepted | ☐ |

**Commit Message Format**: `docs(k0): M5 complete - 7 R4 KG modules, graph storage tables registered`

---

## Milestone 5A: Dream-Like Exploration (R5)

**Goal**: Implement creative insight generation, counterfactual thinking, forward simulation, and procedural rehearsal.
**Duration**: 5-6 days
**Gate**: GATE 3 (Implementation)
**Conditional**: R5 is optional when consolidation budget is exceeded. Implement with feature flag for v1.

> **Brain Analog**: REM Sleep Consolidation - Hippocampus-neocortex dialogue enables creative associations, emotional regulation, and procedural skill enhancement.

### Epic 5A.1: Counterfactual Thinking (R5.1)

**Description**: Generate "what if" scenarios by perturbing past events and exploring alternative outcomes.

#### Issue 5A.1.1: Implement Causal Perturbation Network (CPN)

**Type**: Implementation
**Priority**: Medium (v2 feature)
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r5`, `ml`

**Description**:
Implement counterfactual thinking engine based on Causal Perturbation Network algorithm.

**Implementation Requirements**:

```python
# k0/modules/consolidation/counterfactual_thinker.py

class CounterfactualThinker:
    def __init__(
        self,
        emotional_threshold: float = 0.6,
        regret_threshold: float = -0.5,
        max_counterfactuals_per_event: int = 3
    ):
        self.emotional_threshold = emotional_threshold
        self.regret_threshold = regret_threshold

    async def select_high_emotion_events(
        self,
        events: List[dict],
        limit: int = 10
    ) -> List[dict]:
        """
        Select events with |sentiment_score| > threshold.
        Prioritize negative outcomes (high regret potential).
        Rank by: emotional_impact = |sentiment| × salience × recency
        """

    async def extract_causal_chain(
        self,
        event: dict,
        kg_edges: List[dict]
    ) -> CausalDAG:
        """
        Build DAG of causal predecessors from st_kg_edges.
        Identify modifiable nodes (actor-controlled) vs external factors.
        """

    def generate_counterfactuals(
        self,
        event: dict,
        causal_dag: CausalDAG
    ) -> List[Counterfactual]:
        """
        Generate counterfactual scenarios:
        - Upward: "If I had X, outcome would be better"
        - Downward: "If I had also Y, outcome would be worse"
        - Semifactual: "Even if X, outcome unchanged" (tests necessity)
        """

    async def simulate_counterfactual_outcome(
        self,
        counterfactual: Counterfactual,
        causal_dag: CausalDAG
    ) -> float:
        """
        Use Bayesian network with CPT to predict outcome probability.
        Perform do-calculus intervention (Pearl 2009).
        """

    def extract_learning_signal(
        self,
        original_event: dict,
        counterfactual: Counterfactual,
        predicted_outcome: float
    ) -> LearningSignal:
        """
        Generate actionable insights:
        - Preventable regret (>0.4 improvement)
        - Uncontrollable factors
        - If-then mitigation strategy
        """
```

**Acceptance Criteria**:

- [ ] High-emotion event selection
- [ ] Causal chain extraction from KG
- [ ] Counterfactual generation (upward/downward/semifactual)
- [ ] Bayesian outcome prediction
- [ ] Learning signal extraction
- [ ] 10-20 counterfactuals per cycle
- [ ] Performance: <2 minutes
- [ ] Unit tests with fixture events

**Files to Create**:

- `k0/modules/consolidation/counterfactual_thinker.py`
- `tests/k0/modules/consolidation/test_counterfactual_thinker.py`

**Dependencies**:

- `pgmpy` or similar Bayesian network library
- st_epi for high-emotion events
- st_kg_edges for causal graph

---

### Epic 5A.2: Forward Simulation (R5.2)

**Description**: Generate plausible future scenarios using Monte Carlo Tree Search.

#### Issue 5A.2.1: Implement Temporal Projection Network (TPN-MCTS)

**Type**: Implementation
**Priority**: Medium (v2 feature)
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r5`, `ml`, `planning`

**Description**:
Implement forward simulation engine using MCTS for scenario generation.

**Implementation Requirements**:

```python
# k0/modules/consolidation/forward_simulator.py

class ForwardSimulator:
    def __init__(
        self,
        exploration_constant: float = 1.414,  # sqrt(2)
        max_rollout_depth: int = 30,  # days horizon
        n_simulations: int = 100
    ):
        self.c = exploration_constant
        self.max_depth = max_rollout_depth
        self.n_simulations = n_simulations

    async def extract_goals_and_context(
        self,
        tenant_id: str,
        space_id: str
    ) -> Tuple[List[Goal], Context]:
        """
        Query st_prospective for active goals.
        Query st_procedural for upcoming routines.
        Extract contextual constraints.
        """

    def build_state_space(
        self,
        current_state: State,
        action_repertoire: List[Action],
        transition_model: Dict
    ) -> StateSpace:
        """
        Build MDP for forward simulation:
        - States (S): Actor's situation
        - Actions (A): From st_procedural habits
        - Transitions (T): From st_epi history
        - Rewards (R): Goal alignment + sentiment
        """

    def mcts_search(
        self,
        state_space: StateSpace,
        goal: Goal
    ) -> List[Scenario]:
        """
        Monte Carlo Tree Search with UCT.
        Selection → Expansion → Simulation → Backpropagation
        """

    def diversify_scenarios_dpp(
        self,
        scenarios: List[Scenario],
        n_diverse: int = 10
    ) -> List[Scenario]:
        """
        Use Determinantal Point Process for scenario diversity.
        Ensure qualitative variety: optimistic, pessimistic, creative paths.
        """

    def score_plausibility(
        self,
        scenario: Scenario,
        historical_patterns: Dict
    ) -> float:
        """
        Validate scenario realism:
        - Historical frequency
        - Actor consistency (cosine to routine embeddings)
        - Social norm compliance
        """

    def assess_risk_opportunity(
        self,
        scenario: Scenario
    ) -> RiskOpportunityAssessment:
        """
        Analyze scenario outcomes:
        - Success probability
        - Expected sentiment
        - Risk exposure
        - Hidden opportunities
        """
```

**Acceptance Criteria**:

- [ ] Goal extraction from st_prospective
- [ ] State space construction
- [ ] MCTS implementation with UCT
- [ ] DPP diversity sampling
- [ ] Plausibility scoring
- [ ] Risk/opportunity assessment
- [ ] 5-10 scenarios per cycle
- [ ] Performance: <2 minutes
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/forward_simulator.py`
- `tests/k0/modules/consolidation/test_forward_simulator.py`

**Dependencies**:

- `dppy` for Determinantal Point Process
- Custom MCTS implementation or pytorch-based
- st_prospective for goals
- st_procedural for action repertoire
- st_epi for transition statistics

---

### Epic 5A.3: Episodic Simulation (R5.3)

**Description**: Reconstruct incomplete memories using schema-driven inference.

#### Issue 5A.3.1: Implement Schematic Pattern Completion (SPC-UQ)

**Type**: Implementation
**Priority**: Medium (v2 feature)
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r5`, `ml`

**Description**:
Implement memory reconstruction with uncertainty quantification.

**Implementation Requirements**:

```python
# k0/modules/consolidation/episodic_simulator.py

class EpisodicSimulator:
    def __init__(
        self,
        ambiguity_threshold: float = 0.5,
        max_reconstructions: int = 50
    ):
        self.ambiguity_threshold = ambiguity_threshold
        self.max_reconstructions = max_reconstructions

    async def identify_incomplete_memories(
        self,
        tenant_id: str,
        space_id: str
    ) -> List[dict]:
        """
        Query st_epi for episodes with:
        - ambiguity_score > threshold
        - Missing attributes (location, participants, sentiment)
        Prioritize recent memories (last 30 days).
        """

    async def retrieve_schemas(
        self,
        episode: dict
    ) -> List[SemanticSchema]:
        """
        Query st_sem for patterns matching activity_type and context.
        Extract schema prototypes and feature distributions.
        """

    def bayesian_reconstruction(
        self,
        episode: dict,
        schema: SemanticSchema
    ) -> ReconstructedMemory:
        """
        Fill gaps using Bayesian inference:
        - Prior: P(attr | schema)
        - Likelihood: P(context | attr)
        - Posterior: P(attr | schema, context)

        Sample most probable value with confidence.
        """

    def constraint_satisfaction_temporal(
        self,
        episodes: List[dict]
    ) -> List[dict]:
        """
        Resolve timeline ambiguities using CSP.
        Detect contradictions for Active Learning.
        """

    def counterfactual_consistency_check(
        self,
        reconstruction: ReconstructedMemory,
        kg_constraints: List[dict]
    ) -> bool:
        """
        Validate reconstruction against KG constraints.
        Reject if violating logical constraints.
        """

    def version_and_store(
        self,
        original: dict,
        reconstructed: ReconstructedMemory
    ) -> str:
        """
        Create new version with supersedes chain.
        Track reconstruction_metadata for transparency.
        """
```

**Acceptance Criteria**:

- [ ] Incomplete memory detection
- [ ] Schema retrieval
- [ ] Bayesian reconstruction with confidence
- [ ] Temporal constraint satisfaction
- [ ] Consistency validation
- [ ] Versioning for reconstructions
- [ ] Performance: <1.5 minutes
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/episodic_simulator.py`
- `tests/k0/modules/consolidation/test_episodic_simulator.py`

**Dependencies**:

- CSP library (python-constraint)
- st_epi for incomplete memories
- st_sem for schemas
- st_kg_edges for validation

---

### Epic 5A.4: Insight Generation (R5.4)

**Description**: Discover latent patterns and creative connections via graph traversal.

#### Issue 5A.4.1: Implement Bisociative Graph Traversal (BGT-SM)

**Type**: Implementation
**Priority**: Medium (v2 feature)
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r5`, `ml`, `creativity`

**Description**:
Implement insight discovery using random walks and surprise maximization.

**Implementation Requirements**:

```python
# k0/modules/consolidation/insight_generator.py

class InsightGenerator:
    def __init__(
        self,
        restart_probability: float = 0.15,
        walk_steps: int = 1000,
        pmi_threshold: float = 3.0,
        serendipity_threshold: float = 0.6
    ):
        self.c = restart_probability
        self.walk_steps = walk_steps
        self.pmi_threshold = pmi_threshold
        self.serendipity_threshold = serendipity_threshold

    def build_semantic_distance_map(
        self,
        nodes: List[dict],
        embeddings: Dict[str, np.ndarray]
    ) -> Dict[Tuple[str, str], float]:
        """
        Combine graph geodesic + embedding cosine distance.
        semantic_distance = α × graph_dist + (1-α) × embed_dist
        """

    def random_walk_with_restart(
        self,
        graph: nx.DiGraph,
        seed_node: str
    ) -> Dict[str, float]:
        """
        RWR from seed concept.
        Favor low observation_count edges (unexplored).
        Return visit frequencies.
        """

    def compute_surprise(
        self,
        connection: Tuple[str, str],
        cooccurrence_stats: Dict
    ) -> float:
        """
        Pointwise Mutual Information:
        PMI = log(P_observed / P_expected)
        High PMI = surprising connection.
        """

    def bisociative_recombination(
        self,
        connection: Tuple[str, str],
        frame_assignments: Dict[str, str]
    ) -> Optional[Insight]:
        """
        Generate insight when entities from different frames connect.
        Validate using causal graph path.
        Rate novelty = semantic_distance × PMI / (obs_count + 1)
        """

    def find_analogies(
        self,
        graph: nx.DiGraph
    ) -> List[Analogy]:
        """
        Structure mapping: find isomorphic subgraphs.
        Generate transferrable insights.
        """

    def score_serendipity(
        self,
        insight: Insight,
        goals: List[Goal]
    ) -> float:
        """
        serendipity = novelty × relevance × actionability
        Filter insights below threshold.
        """
```

**Acceptance Criteria**:

- [ ] Semantic distance mapping
- [ ] Random walk implementation
- [ ] PMI-based surprise scoring
- [ ] Bisociative frame recombination
- [ ] Analogy detection via structure mapping
- [ ] Serendipity scoring
- [ ] 10-30 insights per cycle
- [ ] Performance: <2 minutes
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/insight_generator.py`
- `tests/k0/modules/consolidation/test_insight_generator.py`

**Dependencies**:

- `networkx` or `igraph` for graph operations
- st_kg_dom and st_kg_edges
- st_vec for embedding distances

---

### Epic 5A.5: Motor Skill Rehearsal (R5.5)

**Description**: Optimize procedural sequences using reinforcement learning.

#### Issue 5A.5.1: Implement Temporal Difference Learning for Habits (TDL-HCO)

**Type**: Implementation
**Priority**: Medium (v2 feature)
**Assignee**: ML Engineer
**Labels**: `implementation`, `p03`, `r5`, `ml`, `rl`

**Description**:
Implement habit chain optimization using TD learning.

**Implementation Requirements**:

```python
# k0/modules/consolidation/motor_rehearser.py

class MotorRehearser:
    def __init__(
        self,
        learning_rate: float = 0.1,
        discount_factor: float = 0.9,
        consistency_threshold: float = 0.8
    ):
        self.alpha = learning_rate
        self.gamma = discount_factor
        self.consistency_threshold = consistency_threshold

    async def select_routines_for_rehearsal(
        self,
        tenant_id: str,
        actor_id: str
    ) -> List[dict]:
        """
        Query st_procedural for:
        - consistency_score < threshold (not automatized)
        - Recent performance degradation (streak declining)
        """

    def build_mdp(
        self,
        routine: dict,
        execution_history: List[dict]
    ) -> MDP:
        """
        Model habit as MDP:
        - States: Steps in sequence
        - Actions: Possible next steps
        - Transitions: From st_epi history
        - Rewards: Completion +10, pleasant +2, unpleasant -1
        """

    def td_learning(
        self,
        mdp: MDP,
        episodes: List[List[State]]
    ) -> Dict[State, float]:
        """
        Temporal Difference learning for value estimation.
        V(s) ← V(s) + α × (R + γ × V(s') - V(s))
        """

    def detect_bottlenecks(
        self,
        value_function: Dict[State, float]
    ) -> List[Bottleneck]:
        """
        Identify steps with value gradient ΔV < -2.
        These are inefficient/unpleasant steps.
        """

    async def explore_alternatives(
        self,
        bottleneck: Bottleneck,
        actor_id: str
    ) -> List[Alternative]:
        """
        Query similar routines from other actors.
        Query historical deviations from st_epi.
        Simulate alternatives and predict value.
        """

    def chunk_actions(
        self,
        routine: dict
    ) -> dict:
        """
        Identify repeated subsequences.
        Create composite "chunk" actions.
        Reduces cognitive load.
        """

    def rehearse_accelerated(
        self,
        optimized_routine: dict,
        rehearsal_count: int = 5
    ) -> RehearsalResult:
        """
        Replay at 10x speed.
        Update confidence and transition probabilities.
        """
```

**Acceptance Criteria**:

- [ ] Routine selection for rehearsal
- [ ] MDP construction
- [ ] TD learning implementation
- [ ] Bottleneck detection
- [ ] Alternative exploration
- [ ] Action chunking
- [ ] Accelerated rehearsal
- [ ] 3-8 routines per cycle
- [ ] Performance: <30 seconds
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/motor_rehearser.py`
- `tests/k0/modules/consolidation/test_motor_rehearser.py`

**Dependencies**:

- PyTorch with TD(λ) or custom implementation
- st_procedural for routines
- st_epi for execution history
- st_prospective for optimization recommendations

---

### Epic 5A.6: Dream Phase Orchestration

**Description**: Coordinate R5 sub-phases with budget management.

#### Issue 5A.6.1: Implement Dream Simulator (M22)

**Type**: Implementation
**Priority**: Medium (v2 feature)
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r5`

**Description**:
Implement M22 DreamSimulator to orchestrate all R5 sub-phases.

**Implementation Requirements**:

```python
# k0/modules/consolidation/dream_simulator.py

class DreamSimulator:
    def __init__(
        self,
        enabled: bool = False,  # Feature flag for v1
        budget_minutes: float = 8.0,
        sub_phase_budgets: Dict[str, float] = None
    ):
        self.enabled = enabled
        self.budget_minutes = budget_minutes
        self.sub_phase_budgets = sub_phase_budgets or {
            'counterfactual': 2.0,
            'forward_sim': 2.0,
            'episodic_sim': 1.5,
            'insight_gen': 2.0,
            'motor_rehearsal': 0.5
        }

    async def should_run(
        self,
        cycle_elapsed_minutes: float,
        cycle_budget_minutes: float = 90.0
    ) -> bool:
        """
        Run R5 only if:
        1. Feature flag enabled
        2. Remaining budget ≥ 8 minutes
        3. R4 completed successfully
        """

    async def run(
        self,
        consolidation_context: ConsolidationContext
    ) -> DreamResult:
        """
        Orchestrate R5 sub-phases:
        1. R5.1 Counterfactual Thinking
        2. R5.2 Forward Simulation
        3. R5.3 Episodic Simulation
        4. R5.4 Insight Generation
        5. R5.5 Motor Skill Rehearsal

        Skip remaining if budget exceeded.
        """

    async def store_dream_outputs(
        self,
        result: DreamResult
    ) -> int:
        """
        Write to st_prospective and st_sem:
        - Counterfactual scenarios
        - Forward simulation scenarios
        - Creative insights
        - Optimization recommendations

        Returns count of records written.
        """
```

**Acceptance Criteria**:

- [ ] Feature flag implementation
- [ ] Budget checking
- [ ] Sub-phase orchestration
- [ ] Graceful degradation (skip if budget exceeded)
- [ ] Output storage to st_prospective and st_sem
- [ ] Metrics emission
- [ ] Unit tests
- [ ] Integration test with full cycle

**Files to Create**:

- `k0/modules/consolidation/dream_simulator.py`
- `tests/k0/modules/consolidation/test_dream_simulator.py`

---

### Epic 5A.7: K0 Architecture Master - R5 Module Registration

**Description**: Register all Milestone 5A (R5) dream modules in K0 Architecture Master.

#### Issue 5A.7.1: Update K0 Module Registry - R5 Components

**Type**: Documentation
**Priority**: Medium
**Assignee**: Backend Engineer
**Labels**: `k0-governance`, `documentation`, `p03`

**Description**:
Register all R5 dream modules in K0 Architecture Master Part 3.1.

**K0 Registration Requirements**:

1. **Part 3.1 - Module Registry** - Add entries for:

| Module | Type | Status | Layer | Pipelines | Lifecycle |
|--------|------|--------|-------|-----------|-----------|
| `consolidation.counterfactual_thinker` | Service | 📝 Design | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.forward_simulator` | Service | 📝 Design | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.episodic_simulator` | Service | 📝 Design | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.insight_generator` | Service | 📝 Design | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.motor_rehearser` | Service | 📝 Design | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.dream_simulator` (M22) | Orchestrator | 📝 Design | K0/Consolidation | P03 | Per-Cycle |

2. **Part 5.2 - Syscall Matrix** - Add syscall entries:

| Syscall | Target | Operation | Module | Band |
|---------|--------|-----------|--------|------|
| `st_epi.read_high_emotion` | Storage | READ | counterfactual_thinker | GREEN |
| `st_kg_edges.read_causal` | Storage | READ | counterfactual_thinker | GREEN |
| `st_prospective.read_goals` | Storage | READ | forward_simulator | GREEN |
| `st_procedural.read_routines` | Storage | READ | motor_rehearser | GREEN |
| `st_prospective.write_scenario` | Storage | WRITE | forward_simulator | GREEN |
| `st_prospective.write_counterfactual` | Storage | WRITE | counterfactual_thinker | GREEN |
| `st_sem.write_insight` | Storage | WRITE | insight_generator | GREEN |
| `st_prospective.write_optimization` | Storage | WRITE | motor_rehearser | GREEN |

3. **Part 4.1 - Event Topics Registry** - Add event topics:

| Topic | Publisher | Subscribers | Schema | Band |
|-------|-----------|-------------|--------|------|
| `consolidation.counterfactual.generated.v1` | counterfactual_thinker | orchestrator | CounterfactualGenerated | GREEN |
| `consolidation.scenario.simulated.v1` | forward_simulator | orchestrator | ScenarioSimulated | GREEN |
| `consolidation.insight.discovered.v1` | insight_generator | orchestrator | InsightDiscovered | GREEN |
| `consolidation.routine.optimized.v1` | motor_rehearser | orchestrator | RoutineOptimized | GREEN |
| `consolidation.dream.completed.v1` | dream_simulator | orchestrator | DreamCompleted | GREEN |

4. **Part 7.1 - ADR Index** - Add ADR entry:

| ADR | Title | Status | Affects | Date | Owner |
|-----|-------|--------|---------|------|-------|
| ADR-k010.10 | Dream Phase Algorithms | 📝 Draft | P03/R5 | 2025-12-14 | ML Engineer |

**Acceptance Criteria**:

- [ ] All R5 modules added to Part 3.1 Module Registry
- [ ] R5 syscalls added to Part 5.2 Syscall Matrix
- [ ] Event topics added to Part 4.1 Event Topics Registry
- [ ] ADR-k010.10 added to Part 7.1 ADR Index
- [ ] Feature flag documented
- [ ] Status set to 📝 Design (v2 feature)

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 3.1, 4.1, 5.2, 7.1)

---

#### Issue 5A.7.2: Create ADR k010.10 - Dream Phase Algorithms

**Type**: ADR
**Priority**: Medium
**Assignee**: ML Engineer
**Labels**: `architecture`, `adr`, `p03`, `r5`

**Description**:
Document all 5 novel algorithms introduced in R5:

1. **Causal Perturbation Network (CPN)** - Emotion-weighted counterfactual generation
2. **Temporal Projection Network with MCTS (TPN-MCTS)** - Personalized scenario generation
3. **Schematic Pattern Completion with UQ (SPC-UQ)** - Confidence-tracked memory reconstruction
4. **Bisociative Graph Traversal with Surprise Maximization (BGT-SM)** - Insight discovery
5. **Temporal Difference Learning for Habit Chain Optimization (TDL-HCO)** - Procedural optimization

**Acceptance Criteria**:

- [ ] All 5 algorithms documented
- [ ] Research citations included
- [ ] Pseudocode for each algorithm
- [ ] Complexity analysis
- [ ] Novel contributions explained
- [ ] Feature flag rationale

**Files to Create**:

- `docs/architecture/decisions-K0/k010.10_dream_phase_algorithms.md`

---

### Milestone 5A Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 5A complete, verify these K0 updates:

**K0 Closure Checklist for M5A**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 3.1 | Module Master Registry | Add 5 R5 modules (counterfactual_thinker → motor_rehearser) | ☐ |
| 3.1 | Module Master Registry | Status = 📝 Design (v2 feature flagged) | ☐ |
| 4.1 | Event Topics Registry | Add 5 R5 dream event topics | ☐ |
| 5.2 | Syscall Matrix | Add R5 dream syscalls (all GREEN band) | ☐ |
| 7.1 | ADR Index | Create k010.10-p03 (dream algorithms) as 📝 Draft | ☐ |
| 7.1 | ADR Index | Create k010.10-dream-phase-algorithms.md file | ☐ |

**Special Note**: R5 modules are v2 features. Mark as 📝 Design in Part 3.1 to indicate implementation deferred.

**Commit Message Format**: `docs(k0): M5A complete - 5 R5 dream modules registered (v2 flagged), k010.10 ADR created`

---

## Milestone 6: State Writers (R6-R7)

**Goal**: Implement st_hipp_events updates and memory layer writers.
**Duration**: 4-5 days
**Gate**: GATE 3 (Implementation)

### Epic 6.1: Event Updates (R6)

**Description**: Write consolidation results back to st_hipp_events.

#### Issue 6.1.1: Implement Deduplication Writer

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r6`

**Description**:
Write deduplication results to st_hipp_events.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/dedup_writer.py

class DedupWriter:
    async def write_dedup_results(
        self,
        results: DeduplicationResult,
        cycle_id: str
    ) -> int:
        """
        Batch UPDATE st_hipp_events with:
        - novelty_score
        - near_duplicates_json
        - is_near_duplicate

        Returns count of updated rows.
        """

    def build_update_query(
        self,
        batch: List[Tuple[str, float, str, bool]]
    ) -> Tuple[str, List]:
        """Build batch UPDATE query."""
```

**Acceptance Criteria**:

- [ ] Batch UPDATE implementation
- [ ] All dedup columns updated
- [ ] Transaction safety
- [ ] Performance: <10 seconds for 1000 events
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/dedup_writer.py`
- `tests/k0/modules/consolidation/writers/test_dedup_writer.py`

---

#### Issue 6.1.2: Implement Cluster Writer

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r6`

**Description**:
Write cluster assignments to st_hipp_events.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/cluster_writer.py

class ClusterWriter:
    async def write_cluster_results(
        self,
        clusters: ClusteringResult,
        cycle_id: str
    ) -> int:
        """
        Batch UPDATE st_hipp_events with:
        - episode_cluster_id
        - cluster_confidence

        Handle outliers: cluster_id = 'SING_<event_id>'

        Returns count of updated rows.
        """
```

**Acceptance Criteria**:

- [ ] Cluster ID assignment
- [ ] Confidence writing
- [ ] Outlier handling (SING_ prefix)
- [ ] Transaction safety
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/cluster_writer.py`
- `tests/k0/modules/consolidation/writers/test_cluster_writer.py`

---

#### Issue 6.1.3: Implement Status Writer

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r6`

**Description**:
Write consolidation status updates.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/status_writer.py

class StatusWriter:
    async def mark_consolidating(
        self,
        event_ids: List[str],
        cycle_id: str
    ) -> int:
        """Set consolidation_status='CONSOLIDATING', consolidation_cycle_id."""

    async def mark_complete(
        self,
        event_ids: List[str],
        cycle_id: str
    ) -> int:
        """Set consolidation_status='COMPLETE', consolidated_at=now()."""

    async def mark_failed(
        self,
        event_ids: List[str],
        cycle_id: str,
        error_message: str
    ) -> int:
        """Set consolidation_status='FAILED', consolidation_error."""
```

**Acceptance Criteria**:

- [ ] Status state machine
- [ ] Error tracking
- [ ] Timestamp management
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/status_writer.py`
- `tests/k0/modules/consolidation/writers/test_status_writer.py`

---

### Epic 6.2: Memory Layer Writers (R7)

**Description**: Write to all 8 memory layer tables via st_outbox.

#### Issue 6.2.1: Implement Episodic Writer

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r7`

**Description**:
Write episode records from clusters.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/episodic_writer.py

class EpisodicWriter:
    async def write_episodes(
        self,
        clusters: ClusteringResult,
        common_elements: Dict[str, CommonElements],
        cycle_id: str
    ) -> List[str]:
        """
        Create episode records in st_epi via st_outbox.

        Mapping: 1 cluster → 1 episode

        Episode record:
        - episode_id (generated)
        - tenant_id, space_id
        - episode_title (from pattern name generator)
        - representative_event_id (highest confidence)
        - episode_start_time, episode_end_time
        - source_events_json
        - embedding (centroid)

        Returns list of created episode_ids.
        """

    def select_representative_event(
        self,
        cluster_events: List[dict],
        confidences: Dict[str, float]
    ) -> str:
        """Select event with highest cluster confidence."""
```

**Acceptance Criteria**:

- [ ] Cluster-to-episode mapping
- [ ] Outbox staging
- [ ] Representative selection
- [ ] Embedding generation (centroid)
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/episodic_writer.py`
- `tests/k0/modules/consolidation/writers/test_episodic_writer.py`

---

#### Issue 6.2.2: Implement Semantic Writer

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r7`

**Description**:
Write semantic patterns based on CA1 decisions.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/semantic_writer.py

class SemanticWriter:
    async def write_semantics(
        self,
        decisions: List[Tuple[ExtractedPattern, BridgeDecision]],
        cycle_id: str
    ) -> List[str]:
        """
        Create/update semantic records via st_outbox.

        Actions by decision:
        - CREATE: INSERT new st_sem record
        - MERGE: UPDATE existing (increment observation_count, update confidence)
        - EVOLVE: INSERT new version, UPDATE old (is_canonical=0)

        Returns list of semantic_ids affected.
        """

    def prepare_semantic_record(
        self,
        pattern: ExtractedPattern,
        decision: BridgeDecision
    ) -> dict:
        """Prepare st_sem record from pattern."""
```

**Acceptance Criteria**:

- [ ] CREATE/MERGE/EVOLVE handling
- [ ] Version management
- [ ] Outbox staging
- [ ] Observation count increment
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/semantic_writer.py`
- `tests/k0/modules/consolidation/writers/test_semantic_writer.py`

---

#### Issue 6.2.3: Implement Procedural Writer

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r7`

**Description**:
Write procedural memory patterns.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/procedural_writer.py

class ProceduralWriter:
    async def write_procedures(
        self,
        patterns: List[ExtractedPattern],
        cycle_id: str
    ) -> List[str]:
        """
        Create procedural records from activity patterns.

        Filter: pattern.activity_type in PROCEDURAL_ACTIVITIES

        Record:
        - procedure_id
        - procedure_name
        - steps_json (ordered activities)
        - avg_duration_minutes
        - success_rate (from outcome patterns)
        """
```

**Acceptance Criteria**:

- [ ] Activity pattern filtering
- [ ] Steps sequencing
- [ ] Duration estimation
- [ ] Outbox staging
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/procedural_writer.py`
- `tests/k0/modules/consolidation/writers/test_procedural_writer.py`

---

#### Issue 6.2.4: Implement Social Writer

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r7`

**Description**:
Write social graph updates.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/social_writer.py

class SocialWriter:
    async def write_social_patterns(
        self,
        relationships: List[Relationship],
        entities: List[NormalizedEntity],
        cycle_id: str
    ) -> List[str]:
        """
        Create social graph records from person entities and relationships.

        Filter: entity.label == 'PERSON'

        Records:
        - Person nodes with relationship counts
        - Interaction frequencies
        - Closeness scores
        """
```

**Acceptance Criteria**:

- [ ] Person entity filtering
- [ ] Relationship frequency tracking
- [ ] Closeness scoring
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/social_writer.py`
- `tests/k0/modules/consolidation/writers/test_social_writer.py`

---

#### Issue 6.2.5: Implement Prospective Writer

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r7`

**Description**:
Write prospective memory (future intentions).

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/prospective_writer.py

class ProspectiveWriter:
    async def write_intentions(
        self,
        patterns: List[ExtractedPattern],
        cycle_id: str
    ) -> List[str]:
        """
        Create prospective memory records from temporal patterns.

        Filter: pattern has future prediction with high confidence

        Records:
        - intention_id
        - predicted_activity
        - predicted_time
        - confidence
        - trigger_conditions
        """
```

**Acceptance Criteria**:

- [ ] Future prediction extraction
- [ ] Intention record structure
- [ ] Trigger condition mapping
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/prospective_writer.py`
- `tests/k0/modules/consolidation/writers/test_prospective_writer.py`

---

#### Issue 6.2.6: Implement KG Writer

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r7`

**Description**:
Write knowledge graph updates.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/kg_writer.py

class KGWriter:
    def __init__(
        self,
        node_manager: GraphNodeManager,
        edge_manager: GraphEdgeManager
    ):
        self.node_manager = node_manager
        self.edge_manager = edge_manager

    async def write_kg_updates(
        self,
        entities: List[NormalizedEntity],
        relationships: List[Relationship],
        causal_relationships: List[CausalRelationship],
        cycle_id: str
    ) -> KGWriteResult:
        """
        Write all KG updates via st_outbox.

        Process:
        1. Upsert all nodes (entities)
        2. Upsert all edges (relationships)
        3. Mark causal edges (is_causal=1)

        Returns counts of nodes/edges created/updated.
        """
```

**Acceptance Criteria**:

- [ ] Node upsert coordination
- [ ] Edge upsert coordination
- [ ] Causal marking
- [ ] Outbox staging
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/kg_writer.py`
- `tests/k0/modules/consolidation/writers/test_kg_writer.py`

---

#### Issue 6.2.7: Implement Vector Placeholder Writer

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r7`, `p08`

**Description**:
Write vector placeholders and queue embedding jobs.

**Implementation Requirements**:

```python
# k0/modules/consolidation/writers/vec_writer.py

class VecPlaceholderWriter:
    def __init__(self, queue_depth_limit: int = 10000):
        self.queue_depth_limit = queue_depth_limit

    async def write_placeholders(
        self,
        episodes: List[str],
        semantics: List[str],
        cycle_id: str
    ) -> VecWriteResult:
        """
        Create vector placeholders in st_vec.

        Records:
        - vec_id
        - source_type: 'episode' | 'semantic'
        - source_id
        - embedding_status: 'PENDING'
        - embedding: NULL

        Also queue jobs in st_embedding_queue for P08.

        Backpressure: Check queue depth before writes.
        If depth > limit, emit p03.backpressure.detected.v1
        """

    async def check_queue_depth(self) -> int:
        """Check current st_embedding_queue depth."""
```

**Acceptance Criteria**:

- [ ] Placeholder creation
- [ ] Queue job creation
- [ ] Backpressure detection
- [ ] P08 event emission
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/writers/vec_writer.py`
- `tests/k0/modules/consolidation/writers/test_vec_writer.py`

---

### Epic 6.3: K0 Architecture Master - R6/R7 Module Registration

**Description**: Register all Milestone 6 (R6-R7) state writer modules in K0 Architecture Master.

#### Issue 6.3.1: Update K0 Module Registry - R6/R7 Components

**Type**: Documentation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `k0-governance`, `documentation`, `p03`

**Description**:
Register all R6 and R7 state writer modules in K0 Architecture Master Part 3.1.

**K0 Registration Requirements**:

1. **Part 3.1 - Module Registry** - Add entries for:

| Module | Type | Status | Layer | Pipelines | Lifecycle |
|--------|------|--------|-------|-----------|-----------|
| `consolidation.writers.dedup_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.writers.decay_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.writers.status_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.writers.epi_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.writers.sem_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.writers.kg_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.writers.vec_writer` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.writers.batch_coordinator` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |

2. **Part 5.2 - Syscall Matrix** - Add syscall entries:

| Syscall | Target | Operation | Module | Band |
|---------|--------|-----------|--------|------|
| `st_hipp_events.batch_update_dedup` | Storage | WRITE | dedup_writer | GREEN |
| `st_hipp_events.batch_update_decay` | Storage | WRITE | decay_writer | GREEN |
| `st_hipp_events.batch_update_status` | Storage | WRITE | status_writer | GREEN |
| `st_epi.batch_create` | Storage | WRITE | epi_writer | GREEN |
| `st_epi.batch_update_backlinks` | Storage | WRITE | epi_writer | GREEN |
| `st_sem.batch_create` | Storage | WRITE | sem_writer | YELLOW |
| `st_kg_nodes.batch_create` | Storage | WRITE | kg_writer | GREEN |
| `st_kg_edges.batch_create` | Storage | WRITE | kg_writer | GREEN |
| `st_vec.batch_create_placeholders` | Storage | WRITE | vec_writer | GREEN |
| `st_embedding_queue.batch_enqueue` | Storage | WRITE | vec_writer | GREEN |

3. **Part 4.1 - Event Topics Registry** - Add event topics:

| Topic | Publisher | Subscribers | Schema | Band |
|-------|-----------|-------------|--------|------|
| `consolidation.hipp.updated.v1` | status_writer | orchestrator | HippUpdated | GREEN |
| `consolidation.epi.written.v1` | epi_writer | orchestrator | EpiWritten | GREEN |
| `consolidation.sem.written.v1` | sem_writer | orchestrator | SemWritten | YELLOW |
| `consolidation.kg.written.v1` | kg_writer | orchestrator | KGWritten | GREEN |
| `consolidation.vec.queued.v1` | vec_writer | P08_embedding | VecQueued | GREEN |
| `consolidation.backpressure.detected.v1` | vec_writer | orchestrator | BackpressureDetected | GREEN |

**Acceptance Criteria**:

- [ ] All R6 writer modules added to Part 3.1 Module Registry
- [ ] All R7 writer modules added to Part 3.1 Module Registry
- [ ] Batch syscalls added to Part 5.2 Syscall Matrix
- [ ] Event topics added to Part 4.1 Event Topics Registry
- [ ] Cross-pipeline events (P08) documented
- [ ] Status set to ⚠️ Implementation

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 3.1, 4.1, 5.2)

---

### Milestone 6 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 6 complete, verify these K0 updates:

**K0 Closure Checklist for M6**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 3.1 | Module Master Registry | Add R6 modules (dedup_writer, decay_writer, status_writer) | ☐ |
| 3.1 | Module Master Registry | Add R7 modules (epi_writer, sem_writer, kg_writer, vec_writer) | ☐ |
| 4.1 | Event Topics Registry | Add 6 R6-R7 writer event topics | ☐ |
| 5.2 | Syscall Matrix | Add 10 batch write syscalls | ☐ |
| 4.1 | Event Topics | Document cross-pipeline event (P08 vec queued) | ☐ |

**Commit Message Format**: `docs(k0): M6 complete - R6-R7 writers, 10 batch syscalls, P08 cross-link documented`

---

## Milestone 7: Event Emission & Orchestration (R8)

**Goal**: Implement event emission, offset tracking, and pipeline orchestration.
**Duration**: 3-4 days
**Gate**: GATE 3 (Implementation)

### Epic 7.1: Event Emission (R8.1)

**Description**: Emit K0 Bus events for consolidation results.

#### Issue 7.1.1: Implement Event Emitter

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r8`

**Description**:
Emit consolidation result events to K0 Bus.

**Implementation Requirements**:

```python
# k0/modules/consolidation/event_emitter.py

class ConsolidationEventEmitter:
    def __init__(self, bus_client: BusClient):
        self.bus = bus_client

    async def emit_cycle_complete(
        self,
        cycle: ConsolidationCycle,
        results: ConsolidationResults
    ) -> str:
        """
        Emit p03.consolidation.complete.v1 event.

        Payload:
        - cycle_id
        - tenant_id, space_id
        - events_processed
        - episodes_created
        - patterns_detected
        - kg_nodes_created, kg_edges_created
        - duration_seconds
        - trigger_type
        """

    async def emit_pattern_detected(
        self,
        pattern: ExtractedPattern,
        decision: BridgeDecision,
        cycle_id: str
    ) -> str:
        """
        Emit p03.pattern.detected.v1 event.

        Payload:
        - pattern_id
        - pattern_type
        - pattern_name
        - confidence
        - source_episode_ids
        - decision: CREATE|MERGE|EVOLVE
        """

    async def emit_kg_updated(
        self,
        kg_results: KGWriteResult,
        cycle_id: str
    ) -> str:
        """
        Emit p03.kg.updated.v1 event.

        Payload:
        - nodes_created, nodes_updated
        - edges_created, edges_updated
        - causal_edges_created
        """

    async def emit_event_archived(
        self,
        archived_event_ids: List[str],
        cycle_id: str
    ) -> str:
        """Emit p03.event.archived.v1 event."""
```

**Acceptance Criteria**:

- [ ] All event types implemented
- [ ] Payload schema compliance
- [ ] Correlation ID propagation
- [ ] Error handling (retry on bus failure)
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/event_emitter.py`
- `tests/k0/modules/consolidation/test_event_emitter.py`

---

### Epic 7.2: Offset Management (R8.2)

**Description**: Track processing progress for resumability.

#### Issue 7.2.1: Implement Offset Manager

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r8`

**Description**:
Manage pipeline_offsets for checkpoint/resume.

**Implementation Requirements**:

```python
# k0/modules/consolidation/offset_manager.py

class OffsetManager:
    async def get_last_offset(
        self,
        tenant_id: str,
        space_id: str,
        pipeline_id: str = 'P03'
    ) -> Optional[OffsetRecord]:
        """Get last processed offset for tenant/space."""

    async def update_offset(
        self,
        tenant_id: str,
        space_id: str,
        cycle_id: str,
        last_event_id: str,
        batch_size: int,
        success_count: int,
        failure_count: int
    ) -> None:
        """
        Update offset after batch completion.

        Idempotency: Use cycle_id to prevent double-update.
        """

    async def checkpoint(
        self,
        cycle_id: str,
        checkpoint_event_id: str,
        checkpoint_index: int
    ) -> None:
        """Create mid-batch checkpoint for crash recovery."""

    async def get_checkpoint(
        self,
        tenant_id: str,
        space_id: str
    ) -> Optional[CheckpointRecord]:
        """Get last checkpoint for resume after crash."""
```

**Acceptance Criteria**:

- [ ] Offset read/write
- [ ] Idempotent updates
- [ ] Checkpoint support
- [ ] Resume from checkpoint
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/offset_manager.py`
- `tests/k0/modules/consolidation/test_offset_manager.py`

---

### Epic 7.3: Metrics Collection (R8.3)

**Description**: Collect and expose Prometheus metrics.

#### Issue 7.3.1: Implement Metrics Collector

**Type**: Implementation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `r8`, `observability`

**Description**:
Collect and expose pipeline metrics.

**Implementation Requirements**:

```python
# k0/modules/consolidation/metrics_collector.py

from prometheus_client import Counter, Histogram, Gauge

class P03MetricsCollector:
    def __init__(self):
        self.cycle_duration = Histogram(
            'p03_cycle_duration_seconds',
            'Consolidation cycle duration',
            ['tenant_id', 'trigger_type'],
            buckets=[60, 300, 600, 1200, 1800, 3600, 5400]
        )

        self.events_processed = Counter(
            'p03_events_processed_total',
            'Total events processed',
            ['tenant_id', 'status']
        )

        self.memories_created = Counter(
            'p03_memories_created_total',
            'Memories created by layer',
            ['tenant_id', 'layer']
        )

        self.novelty_score = Histogram(
            'p03_novelty_score',
            'Distribution of novelty scores',
            ['tenant_id'],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )

        self.cluster_count = Gauge(
            'p03_cluster_count',
            'Number of clusters in last cycle',
            ['tenant_id']
        )

    def record_cycle(
        self,
        cycle: ConsolidationCycle,
        results: ConsolidationResults
    ) -> None:
        """Record all metrics for completed cycle."""
```

**Acceptance Criteria**:

- [ ] All metric types implemented
- [ ] Proper labeling
- [ ] Histogram buckets appropriate for SLOs
- [ ] Integration with Prometheus
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/metrics_collector.py`
- `tests/k0/modules/consolidation/test_metrics_collector.py`

---

### Epic 7.4: Pipeline Orchestrator

**Description**: Main orchestration logic coordinating all phases.

#### Issue 7.4.1: Implement Consolidation Orchestrator

**Type**: Implementation
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `implementation`, `p03`, `orchestrator`

**Description**:
Main orchestrator coordinating R0-R8 phases.

**Implementation Requirements**:

```python
# k0/modules/consolidation/orchestrator.py

class ConsolidationOrchestrator:
    def __init__(
        self,
        trigger_coordinator: TriggerCoordinator,
        lock_manager: ConsolidationLockManager,
        batch_selector: BatchSelector,
        importance_scorer: ImportanceScorer,
        replay_sequencer: ReplaySequencer,
        episodic_clusterer: EpisodicClusterer,
        pattern_extractor: PatternExtractor,
        ca1_bridge: CA1Bridge,
        duplicate_detector: DuplicateDetector,
        novelty_scorer: NoveltyScorer,
        entity_reader: EntityReader,
        kg_builder: KGBuilder,
        writers: WriterRegistry,
        event_emitter: ConsolidationEventEmitter,
        offset_manager: OffsetManager,
        metrics_collector: P03MetricsCollector
    ):
        # Inject all dependencies

    async def run_consolidation_cycle(
        self,
        tenant_id: str,
        space_id: str,
        trigger_type: TriggerType
    ) -> ConsolidationResults:
        """
        Execute full consolidation cycle.

        Phases:
        R0: Trigger & Lock → acquire lock, select batch
        R1: Replay → score importance, sequence replay
        R2: Integration → cluster, extract patterns, CA1 bridge
        R3 || R4: Parallel execution
          R3: Homeostasis → deduplicate, novelty, retention
          R4: KG → entities, relationships, causal
        R5: SKIP (v1)
        R6: Update → write to st_hipp_events
        R7: Writers → write to memory layers
        R8: Events → emit events, update offset

        Error handling:
        - Catch phase errors
        - Update status to FAILED
        - Release lock
        - Emit failure event
        """

    async def _run_parallel_phases(
        self,
        cycle: ConsolidationCycle,
        r2_results: R2Results
    ) -> Tuple[R3Results, R4Results]:
        """Run R3 and R4 in parallel using asyncio.gather."""

    async def _handle_phase_error(
        self,
        cycle: ConsolidationCycle,
        phase: str,
        error: Exception
    ) -> None:
        """Handle phase failure."""
```

**Acceptance Criteria**:

- [ ] All phases coordinated
- [ ] R3/R4 parallel execution
- [ ] Error handling and recovery
- [ ] Lock management
- [ ] Metric recording
- [ ] Integration tests

**Files to Create**:

- `k0/modules/consolidation/orchestrator.py`
- `tests/k0/modules/consolidation/test_orchestrator.py`

---

#### Issue 7.4.2: Implement Sleep Cycle State Machine

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `p03`, `state-machine`

**Description**:
Implement state machine for consolidation cycles.

**Implementation Requirements**:

```python
# k0/modules/consolidation/state_machine.py

from enum import Enum, auto

class CycleState(Enum):
    IDLE = auto()
    NREM1 = auto()  # R0-R1: Trigger, Replay
    NREM2 = auto()  # R2: Integration
    REM = auto()     # R3-R4: Homeostasis, KG (parallel)
    WAKE = auto()    # R5-R8: Update, Write, Emit (SKIP R5 for v1)
    COMPLETE = auto()
    FAILED = auto()

class CycleStateMachine:
    TRANSITIONS = {
        CycleState.IDLE: [CycleState.NREM1],
        CycleState.NREM1: [CycleState.NREM2, CycleState.FAILED],
        CycleState.NREM2: [CycleState.REM, CycleState.FAILED],
        CycleState.REM: [CycleState.WAKE, CycleState.FAILED],
        CycleState.WAKE: [CycleState.COMPLETE, CycleState.FAILED],
        CycleState.COMPLETE: [CycleState.IDLE],
        CycleState.FAILED: [CycleState.IDLE],
    }

    def __init__(self, cycle_id: str):
        self.cycle_id = cycle_id
        self.state = CycleState.IDLE
        self.state_history: List[Tuple[CycleState, datetime]] = []

    def transition(self, to_state: CycleState) -> None:
        """Validate and execute state transition."""

    def can_transition(self, to_state: CycleState) -> bool:
        """Check if transition is valid."""
```

**Acceptance Criteria**:

- [ ] All states defined
- [ ] Valid transitions enforced
- [ ] State history tracking
- [ ] Invalid transition rejection
- [ ] Unit tests

**Files to Create**:

- `k0/modules/consolidation/state_machine.py`
- `tests/k0/modules/consolidation/test_state_machine.py`

---

### Epic 7.5: K0 Architecture Master - R8 Module Registration

**Description**: Register all Milestone 7 (R8) event emission and orchestration modules in K0 Architecture Master.

#### Issue 7.5.1: Update K0 Module Registry - R8 Components

**Type**: Documentation
**Priority**: High
**Assignee**: Backend Engineer
**Labels**: `k0-governance`, `documentation`, `p03`

**Description**:
Register all R8 event emission and orchestration modules in K0 Architecture Master Part 3.1.

**K0 Registration Requirements**:

1. **Part 3.1 - Module Registry** - Add entries for:

| Module | Type | Status | Layer | Pipelines | Lifecycle |
|--------|------|--------|-------|-----------|-----------|
| `consolidation.event_emitter` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.offset_manager` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.metrics_collector` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.orchestrator` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |
| `consolidation.state_machine` | Service | ⚠️ Impl | K0/Consolidation | P03 | Per-Cycle |

2. **Part 5.2 - Syscall Matrix** - Add syscall entries:

| Syscall | Target | Operation | Module | Band |
|---------|--------|-----------|--------|------|
| `st_consolidation_offsets.read` | Storage | READ | offset_manager | GREEN |
| `st_consolidation_offsets.write` | Storage | WRITE | offset_manager | GREEN |
| `st_consolidation_cycles.update_status` | Storage | WRITE | orchestrator | GREEN |
| `st_consolidation_cycles.record_metrics` | Storage | WRITE | metrics_collector | GREEN |
| `k0_bus.emit` | Bus | EMIT | event_emitter | GREEN |

3. **Part 4.1 - Event Topics Registry** - Add event topics (FINAL):

| Topic | Publisher | Subscribers | Schema | Band |
|-------|-----------|-------------|--------|------|
| `p03.cycle.completed.v1` | orchestrator | P02, monitoring | CycleCompleted | GREEN |
| `p03.cycle.failed.v1` | orchestrator | monitoring, alerting | CycleFailed | YELLOW |
| `p03.memory.consolidated.v1` | orchestrator | P02, workspace | MemoryConsolidated | GREEN |
| `p03.metrics.recorded.v1` | metrics_collector | monitoring | MetricsRecorded | GREEN |

4. **Update Pipeline Registry Status**:

Update Part 2.1 Pipeline Registry - P03 status to ⚠️ Implementation:

```markdown
| P03 | Offline Consolidation | ⚠️ Implementation | K0-Foundation | Batch Memory Consolidation |
```

**Acceptance Criteria**:

- [ ] All R8 modules added to Part 3.1 Module Registry
- [ ] Syscalls added to Part 5.2 Syscall Matrix
- [ ] Final event topics added to Part 4.1 Event Topics Registry
- [ ] Pipeline status updated from 📝 Design to ⚠️ Implementation in Part 2.1
- [ ] Cross-pipeline events (P02) documented
- [ ] All module cross-references verified

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 2.1, 3.1, 4.1, 5.2)

**K0 Pre-Merge Checklist**:

- [ ] Part 2.1 Pipeline Registry - status updated
- [ ] Part 3.1 Module Registry - all P03 modules registered
- [ ] Part 4.1 Event Topics Registry - all topics registered
- [ ] Part 5.2 Syscall Matrix - all syscalls registered
- [ ] Implementation checklist items verified
- [ ] Status transitions documented

---

### Milestone 7 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 7 complete, verify these K0 updates:

**K0 Closure Checklist for M7**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 2.1 | Pipeline Registry | Update P03 status: 🎯 Planning → ⚠️ Implementation | ☐ |
| 3.1 | Module Master Registry | Add R8 modules (event_emitter, offset_tracker, orchestrator, metrics_collector) | ☐ |
| 4.1 | Event Topics Registry | Add 4 final event topics (cycle.completed, cycle.failed, memory.consolidated, metrics.recorded) | ☐ |
| 5.2 | Syscall Matrix | Add R8 syscalls (offset tracking, bus emit) | ☐ |
| 5.3 | Storage Tables | st_consolidation_cycles registered | ☐ |
| 7.1 | ADR Index | Update k010.11-p03 (UltraBERT consumption) to ✅ Accepted | ☐ |

**This is the final implementation milestone. Verify ALL 37 modules registered before proceeding to M8.**

**Commit Message Format**: `docs(k0): M7 complete - P03 status → Implementation, all 37 modules registered`

---

## Milestone 8: Testing & Validation

**Goal**: Comprehensive testing coverage for P03.
**Duration**: 5-6 days
**Gate**: GATE 4 (Testing)

### Epic 8.1: Unit Tests

**Description**: Unit tests for all modules.

#### Issue 8.1.1: Create Unit Test Fixtures

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `fixtures`

**Description**:
Create comprehensive test fixtures for P03 testing.

**Fixtures Required**:

```python
# tests/k0/modules/consolidation/conftest.py

@pytest.fixture
def sample_events(n: int = 1000) -> List[dict]:
    """Generate n sample st_hipp_events records."""

@pytest.fixture
def clustered_events() -> List[dict]:
    """Events pre-organized into 3-5 known clusters."""

@pytest.fixture
def duplicate_events() -> List[dict]:
    """Events with known near-duplicates (Hamming ≤ 3)."""

@pytest.fixture
def pattern_events() -> List[dict]:
    """Events with clear temporal pattern (daily routine)."""

@pytest.fixture
def entity_rich_events() -> List[dict]:
    """Events with multiple named entities for KG testing."""

@pytest.fixture
def mock_st_hipp_events_table(db_session):
    """In-memory SQLite table mimicking st_hipp_events."""

@pytest.fixture
def mock_outbox(db_session):
    """Mock st_outbox for testing writes."""
```

**Acceptance Criteria**:

- [ ] All fixture types created
- [ ] Realistic data distribution
- [ ] Parameterized for different scenarios
- [ ] Documented edge cases
- [ ] Reusable across test files

**Files to Create**:

- `tests/k0/modules/consolidation/conftest.py`
- `tests/k0/modules/consolidation/fixtures/sample_events.py`
- `tests/k0/modules/consolidation/fixtures/clustered_events.py`
- `tests/k0/modules/consolidation/fixtures/duplicate_events.py`

---

#### Issue 8.1.2: Unit Tests - Importance Scorer

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `r1`

**Description**:
Comprehensive unit tests for ImportanceScorer.

**Test Cases**:

1. `test_emotional_intensity_calculation` - verify sqrt(v² + a²) / sqrt(2)
2. `test_recency_score_exponential_decay` - verify decay formula
3. `test_access_score_log_scale` - verify log scaling
4. `test_social_score_participant_count` - verify normalization
5. `test_weighted_combination` - verify weights sum correctly
6. `test_missing_fields_handled` - edge case: null valence/arousal
7. `test_batch_scoring_performance` - 1000 events < 5 seconds
8. `test_score_range_0_to_1` - output bounds validation

**Acceptance Criteria**:

- [ ] All 8 test cases implemented
- [ ] Edge cases covered
- [ ] Performance assertions
- [ ] 100% branch coverage for module

**Files to Create**:

- `tests/k0/modules/consolidation/test_importance_scorer.py`

---

#### Issue 8.1.3: Unit Tests - Episodic Clusterer

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `r2`

**Description**:
Unit tests for EpisodicClusterer.

**Test Cases**:

1. `test_cluster_formation` - known clusters correctly identified
2. `test_cluster_confidence_scoring` - confidence = similarity to centroid
3. `test_outlier_handling` - noise events marked as SING_*
4. `test_dbscan_parameters` - eps and min_samples effect
5. `test_composite_distance` - all 4 distance types weighted
6. `test_empty_input` - graceful handling
7. `test_single_event` - single event becomes singleton cluster
8. `test_performance_1000_events` - <3 minutes

**Acceptance Criteria**:

- [ ] All test cases implemented
- [ ] Known cluster validation
- [ ] Performance benchmark

**Files to Create**:

- `tests/k0/modules/consolidation/test_episodic_clusterer.py`

---

#### Issue 8.1.4: Unit Tests - Duplicate Detector

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `r3`

**Description**:
Unit tests for DuplicateDetector.

**Test Cases**:

1. `test_simhash_calculation` - deterministic for same text
2. `test_hamming_distance` - correct bit difference count
3. `test_lsh_bucket_collision` - candidates found in same bucket
4. `test_jaccard_confirmation` - false positives filtered
5. `test_canonical_selection` - highest salience wins
6. `test_near_duplicate_marking` - is_near_duplicate=True
7. `test_no_duplicates` - all unique events handled
8. `test_performance_1000_events` - <3 minutes

**Acceptance Criteria**:

- [ ] All test cases implemented
- [ ] Precision/recall metrics
- [ ] Performance benchmark

**Files to Create**:

- `tests/k0/modules/consolidation/test_duplicate_detector.py`

---

#### Issue 8.1.5: Unit Tests - CA1 Bridge

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `r2`

**Description**:
Unit tests for CA1Bridge decision making.

**Test Cases**:

1. `test_merge_decision_high_similarity` - >0.85 → MERGE
2. `test_evolve_decision_medium_similarity` - 0.6-0.85 → EVOLVE
3. `test_create_decision_low_similarity` - <0.6 → CREATE
4. `test_no_existing_semantics` - always CREATE
5. `test_multiple_matches_resolution` - highest similarity wins
6. `test_ambiguous_matches_flagged` - Active Learning deferral
7. `test_threshold_boundary_cases` - exact 0.60, exact 0.85

**Acceptance Criteria**:

- [ ] All test cases implemented
- [ ] Boundary conditions tested
- [ ] Decision consistency

**Files to Create**:

- `tests/k0/modules/consolidation/test_ca1_bridge.py`

---

#### Issue 8.1.6: Unit Tests - KG Components

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `r4`

**Description**:
Unit tests for KG extraction and construction.

**Test Cases for EntityReader** (reads from P02 entities_json):

1. `test_parse_entities_json` - Parse entities from st_hipp_events.entities_json
2. `test_all_entity_types` - PERSON, ORG, GPE, KINSHIP, FAMILY_EVENT types handled
3. `test_batch_read` - Batch reading for multiple events

**Test Cases for EntityNormalizer**:

1. `test_exact_match_lookup` - existing node returned
2. `test_fuzzy_match_alias` - alias added to existing
3. `test_new_node_creation` - no match creates new

**Test Cases for RelationshipDetector**:

1. `test_cooccurrence_detection` - entities in same event
2. `test_temporal_relationship` - events within 1 hour
3. `test_strength_normalization` - count / max_count

**Test Cases for CausalInference**:

1. `test_temporal_precedence` - A consistently before B
2. `test_causal_confidence` - frequency × consistency
3. `test_minimum_observations` - <5 observations rejected

**Acceptance Criteria**:

- [ ] All test cases implemented
- [ ] No NLP model mocking needed (reading from DB)
- [ ] Integration test with real st_hipp_events data

**Files to Create**:

- `tests/k0/modules/consolidation/test_entity_reader.py`
- `tests/k0/modules/consolidation/test_entity_normalizer.py`
- `tests/k0/modules/consolidation/test_cooccurrence_detector.py`
- `tests/k0/modules/consolidation/test_causal_inference.py`

---

### Epic 8.2: Integration Tests

**Description**: End-to-end integration tests.

#### Issue 8.2.1: Integration Test - Full Cycle

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `integration`

**Description**:
End-to-end test of full consolidation cycle.

**Test Scenario**:

```python
# tests/integration/p03/test_full_cycle.py

@pytest.mark.integration
async def test_full_consolidation_cycle(
    db_session,
    sample_events_1000,
    mock_bus_client
):
    """
    Test complete P03 cycle with 1000 events.

    Setup:
    1. Insert 1000 events into st_hipp_events
    2. Configure trigger for immediate execution

    Execute:
    3. Run ConsolidationOrchestrator.run_consolidation_cycle()

    Verify:
    4. All events have consolidation_status='COMPLETE'
    5. Episodes created in st_epi (via outbox)
    6. Patterns detected and stored in st_sem (via outbox)
    7. KG nodes/edges created (via outbox)
    8. Events emitted to bus
    9. Offset updated in pipeline_offsets
    10. Metrics recorded

    Performance:
    11. Total duration < 90 minutes
    """
```

**Acceptance Criteria**:

- [ ] Full cycle completes successfully
- [ ] All memory layers populated
- [ ] Events emitted
- [ ] Performance within budget
- [ ] Cleanup after test

**Files to Create**:

- `tests/integration/p03/test_full_cycle.py`

---

#### Issue 8.2.2: Integration Test - Crash Recovery

**Type**: Testing
**Priority**: High
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `integration`, `resilience`

**Description**:
Test checkpoint/resume after simulated crash.

**Test Scenario**:

```python
@pytest.mark.integration
async def test_crash_recovery(db_session, sample_events_1000):
    """
    Test resume after mid-cycle crash.

    Setup:
    1. Insert 1000 events
    2. Start consolidation cycle
    3. Simulate crash after R2 (500 events processed)

    Verify:
    4. Checkpoint exists with checkpoint_event_id
    5. Resume from checkpoint
    6. Remaining 500 events processed
    7. No duplicate processing
    8. Final results correct
    """
```

**Acceptance Criteria**:

- [ ] Checkpoint created mid-cycle
- [ ] Resume from checkpoint works
- [ ] No duplicate processing
- [ ] Idempotency verified

**Files to Create**:

- `tests/integration/p03/test_crash_recovery.py`

---

#### Issue 8.2.3: Integration Test - Lock Contention

**Type**: Testing
**Priority**: High
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `integration`, `concurrency`

**Description**:
Test behavior under concurrent trigger attempts.

**Test Scenario**:

```python
@pytest.mark.integration
async def test_lock_contention(db_session, sample_events_1000):
    """
    Test concurrent consolidation attempts.

    Setup:
    1. Insert 1000 events for same tenant/space

    Execute:
    2. Trigger 3 concurrent consolidation attempts

    Verify:
    3. Only 1 acquires lock and runs
    4. Other 2 return immediately (lock held)
    5. No race conditions or data corruption
    """
```

**Acceptance Criteria**:

- [ ] Single cycle runs
- [ ] Others blocked by lock
- [ ] No data corruption
- [ ] Lock released on completion

**Files to Create**:

- `tests/integration/p03/test_lock_contention.py`

---

#### Issue 8.2.4: Integration Test - P08 Coordination

**Type**: Testing
**Priority**: High
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `integration`, `p08`

**Description**:
Test P03 → P08 handoff for embeddings.

**Test Scenario**:

```python
@pytest.mark.integration
async def test_p08_coordination(db_session, sample_events_1000, mock_embedding_service):
    """
    Test P08 embedding coordination via st_vec.embedding_status.

    Setup:
    1. Run full P03 cycle

    Verify:
    2. st_vec placeholders created with embedding_status='PENDING'
    3. NO st_embedding_queue table used (DEPRECATED)
    4. cognitive.embedding.requested.v1 events emitted via outbox
    5. Mock P08 can query st_vec WHERE embedding_status='PENDING'
    """
```

> **NOTE**: Per Pipeline-Fabric Integration Guide §1.9, `st_embedding_queue` is deprecated.
> P08 coordination uses `st_vec.embedding_status` column and outbox events.

**Acceptance Criteria**:

- [ ] st_vec placeholders created with embedding_status='PENDING'
- [ ] **NO st_embedding_queue usage** (deprecated table)
- [ ] Events emitted via outbox_emit_batch
- [ ] P08 can query st_vec for pending embeddings

**Files to Create**:

- `tests/integration/p03/test_p08_coordination.py`

---

#### Issue 8.2.5: Integration Test - Hot Reload Configuration

**Type**: Testing
**Priority**: Medium
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `integration`, `hot-reload`

**Description**:
Test hot-reloading of pipeline configuration per Integration Guide §5.1.

> **Reference**: Pipeline-Fabric Integration Guide §5.1 - Hot Reload Configuration

**Test Scenario**:

```python
@pytest.mark.integration
async def test_hot_reload_configuration(db_session, sample_events_100):
    """
    Test pipeline hot-reload picks up config changes.

    Setup:
    1. Start P03 with batch_size=50
    2. Process 25 events (partial batch)

    Execute:
    3. Update config: batch_size=25 via config store
    4. Trigger SIGHUP or watch notify

    Verify:
    5. Pipeline picks up new batch_size=25
    6. Next batch uses updated config
    7. No cycle interruption
    8. Config change logged with trace_id
    """
```

**Hot Reload Verification**:

```python
async def verify_hot_reload(pipeline_runtime):
    # Check fabric observed config change
    assert pipeline_runtime.config.batch_size == 25

    # Verify reload logged
    assert any(
        log.msg == "hot_reload_applied"
        for log in pipeline_runtime.logs
    )

    # Verify no cycle restart
    assert pipeline_runtime.cycle_count == 1
```

**Acceptance Criteria**:

- [ ] Config changes detected within reload interval
- [ ] Pipeline uses new config without restart
- [ ] No processing interruption
- [ ] Reload event logged with trace context

**Files to Create**:

- `tests/integration/p03/test_hot_reload.py`

---

### Epic 8.3: Performance Tests

**Description**: Performance and load testing.

#### Issue 8.3.1: Performance Test - 1000 Event Batch

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `performance`

**Description**:
Benchmark 1000-event batch performance.

**Test Configuration**:

```python
@pytest.mark.performance
async def test_1000_event_batch_performance(
    db_session,
    sample_events_1000
):
    """
    Performance benchmark for 1000-event batch.

    SLOs:
    - R1 (Replay): < 25 minutes
    - R2 (Integration): < 35 minutes
    - R3 (Homeostasis): < 10 minutes (parallel with R4)
    - R4 (KG): < 20 minutes (parallel with R3)
    - R6 (Update): < 3 minutes
    - R7 (Writers): < 15 minutes
    - R8 (Events): < 5 minutes
    - Total: < 90 minutes

    Measure:
    - Wall clock time per phase
    - CPU utilization
    - Memory peak
    - DB query count
    """
```

**Acceptance Criteria**:

- [ ] All phase SLOs met
- [ ] Total < 90 minutes
- [ ] Memory < 2GB peak
- [ ] Metrics recorded

**Files to Create**:

- `tests/performance/p03/test_1000_event_batch.py`

---

#### Issue 8.3.2: Performance Test - 10000 Event Batch

**Type**: Testing
**Priority**: High
**Assignee**: QA Engineer
**Labels**: `testing`, `p03`, `performance`

**Description**:
Stress test with 10x normal batch size.

**Test Configuration**:

```python
@pytest.mark.performance
@pytest.mark.slow
async def test_10000_event_batch_stress(db_session):
    """
    Stress test with 10,000 events.

    Goals:
    - Identify scaling bottlenecks
    - Memory pressure testing
    - DB connection pooling under load

    Expected:
    - Linear scaling (10x events ≈ 10x time)
    - No OOM errors
    - Graceful degradation
    """
```

**Acceptance Criteria**:

- [ ] Completes without OOM
- [ ] Scaling characteristics documented
- [ ] Bottlenecks identified

**Files to Create**:

- `tests/performance/p03/test_10000_event_stress.py`

---

### Milestone 8 Completion: K0 Architecture Master Closure

> **⚠️ MANDATORY**: Before marking Milestone 8 complete, verify these K0 updates:

**K0 Closure Checklist for M8**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 8.1 | Coverage Requirements | Document P03 test coverage target (≥90%) | ☐ |
| 8.2 | Quality Gates | P03 passes all quality gates | ☐ |
| 8.3 | Module Test Status | All 37 modules have test coverage | ☐ |
| 3.1 | Module Registry | All module statuses verified as ⚠️ Implementation | ☐ |

**Testing Verification**:

| Test Category | Count | Coverage |
|---------------|-------|----------|
| Unit Tests | Per module | ≥90% |
| Integration Tests | Per epic | Cross-module flows |
| Performance Tests | 2 benchmarks | SLOs documented |
| Contract Tests | Per interface | Schema compliance |

**Commit Message Format**: `docs(k0): M8 complete - test coverage verified, quality gates passed`

---

## Milestone 9: Deployment & Observability

**Goal**: Production deployment readiness.
**Duration**: 3-4 days
**Gate**: GATE 5 (Documentation)

### Epic 9.1: Deployment Configuration

**Description**: Production deployment artifacts.

#### Issue 9.1.1: Create Docker Configuration

**Type**: DevOps
**Priority**: Critical
**Assignee**: DevOps Engineer
**Labels**: `devops`, `p03`, `docker`

**Description**:
Create Docker configuration for P03 worker.

**Deliverables**:

```dockerfile
# k0/deploy/p03/Dockerfile

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NOTE: No NLP models required!
# P03 reads pre-computed UltraBERT outputs from st_hipp_events and st_vec
# P02 already computed: entities_json, kg_triples_json, sentiment, emotions, embeddings

# Copy application code
COPY k0/modules/consolidation /app/consolidation
COPY k0/contracts /app/contracts

WORKDIR /app
CMD ["python", "-m", "consolidation.worker"]
```

**Acceptance Criteria**:

- [ ] Dockerfile created
- [ ] Multi-stage build for size optimization
- [ ] No NLP models needed (lightweight image)
- [ ] Health check endpoint
- [ ] Resource limits documented

**Files to Create**:

- `k0/deploy/p03/Dockerfile`
- `k0/deploy/p03/docker-compose.yml`
- `k0/deploy/p03/requirements.txt`

---

#### Issue 9.1.2: Create Kubernetes Manifests

**Type**: DevOps
**Priority**: Critical
**Assignee**: DevOps Engineer
**Labels**: `devops`, `p03`, `kubernetes`

**Description**:
Create Kubernetes deployment manifests.

**Deliverables**:

```yaml
# k0/deploy/p03/k8s/deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: p03-consolidation-worker
spec:
  replicas: 1  # Single worker per tenant (lock-based)
  selector:
    matchLabels:
      app: p03-consolidation-worker
  template:
    spec:
      containers:
      - name: worker
        image: familyos/p03-consolidation:v1
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        env:
        - name: P03_BATCH_SIZE
          value: "1000"
        - name: P03_MAX_DURATION_MINUTES
          value: "90"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          periodSeconds: 10
```

**Acceptance Criteria**:

- [ ] Deployment manifest
- [ ] Service manifest
- [ ] ConfigMap for configuration
- [ ] Resource limits appropriate
- [ ] Health/readiness probes

**Files to Create**:

- `k0/deploy/p03/k8s/deployment.yaml`
- `k0/deploy/p03/k8s/service.yaml`
- `k0/deploy/p03/k8s/configmap.yaml`

---

#### Issue 9.1.3: Create Scheduled Job Configuration

**Type**: DevOps
**Priority**: High
**Assignee**: DevOps Engineer
**Labels**: `devops`, `p03`, `kubernetes`

**Description**:
Create CronJob for scheduled consolidation.

**Deliverables**:

```yaml
# k0/deploy/p03/k8s/cronjob.yaml

apiVersion: batch/v1
kind: CronJob
metadata:
  name: p03-consolidation-scheduled
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: trigger
            image: familyos/p03-consolidation:v1
            command: ["python", "-m", "consolidation.trigger", "--type", "scheduled"]
          restartPolicy: OnFailure
```

**Acceptance Criteria**:

- [ ] CronJob manifest
- [ ] Schedule configurable
- [ ] Concurrency policy prevents overlap
- [ ] Failure handling

**Files to Create**:

- `k0/deploy/p03/k8s/cronjob.yaml`

---

### Epic 9.2: Observability Configuration

**Description**: Monitoring and alerting setup.

#### Issue 9.2.1: Create Grafana Dashboard

**Type**: DevOps
**Priority**: High
**Assignee**: DevOps Engineer
**Labels**: `devops`, `p03`, `observability`

**Description**:
Create Grafana dashboard for P03 monitoring.

**Dashboard Panels**:

1. **Cycle Overview**: Duration histogram, success/failure rate
2. **Phase Breakdown**: Time per phase (R0-R8)
3. **Memory Creation**: Counts by layer over time
4. **Novelty Distribution**: Histogram of novelty scores
5. **KG Growth**: Node/edge counts over time
6. **Error Rate**: Failures by phase
7. **Queue Depth**: P08 embedding queue backpressure
8. **Lock Status**: Current lock holders

**Acceptance Criteria**:

- [ ] All panels created
- [ ] Variables for tenant filtering
- [ ] Alert annotations
- [ ] JSON export provided

**Files to Create**:

- `k0/deploy/p03/grafana/p03-dashboard.json`

---

#### Issue 9.2.2: Create Alerting Rules

**Type**: DevOps
**Priority**: High
**Assignee**: DevOps Engineer
**Labels**: `devops`, `p03`, `observability`

**Description**:
Create Prometheus alerting rules.

**Alert Rules**:

```yaml
# k0/deploy/p03/prometheus/alerts.yaml

groups:
- name: p03_alerts
  rules:
  - alert: P03CycleTooLong
    expr: p03_cycle_duration_seconds > 5400  # 90 minutes
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "P03 consolidation cycle exceeding budget"

  - alert: P03CyclesFailing
    expr: rate(p03_events_processed_total{status="failed"}[1h]) > 0.1
    for: 10m
    labels:
      severity: critical
    annotations:
      summary: "P03 consolidation cycles failing"

  - alert: P03BackpressureHigh
    expr: p03_embedding_queue_depth > 8000
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "P08 embedding queue backpressure detected"

  - alert: P03StaleLock
    expr: p03_lock_age_seconds > 7200  # 2 hours
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "P03 consolidation lock stale"
```

**Acceptance Criteria**:

- [ ] All alert rules created
- [ ] Severity levels appropriate
- [ ] Runbook links in annotations
- [ ] Testing with alertmanager

**Files to Create**:

- `k0/deploy/p03/prometheus/alerts.yaml`

---

### Epic 9.3: Runbook & Documentation

**Description**: Operational documentation.

#### Issue 9.3.1: Create Operational Runbook

**Type**: Documentation
**Priority**: High
**Assignee**: Tech Lead
**Labels**: `documentation`, `p03`, `runbook`

**Description**:
Create operational runbook for P03.

**Runbook Sections**:

1. **Overview**: What P03 does, when it runs
2. **Architecture**: Component diagram, data flow
3. **Health Checks**: How to verify healthy operation
4. **Common Issues**:
   - Lock stuck → cleanup procedure
   - Cycle too slow → identify bottleneck
   - OOM → adjust batch size
   - P08 backpressure → pause triggers
5. **Manual Operations**:
   - Force trigger consolidation
   - Clear stale lock
   - Reprocess failed batch
   - Adjust configuration live
6. **Disaster Recovery**:
   - Resume from checkpoint
   - Rollback partial cycle
   - Revert memory layer writes

**Acceptance Criteria**:

- [ ] All sections documented
- [ ] Step-by-step procedures
- [ ] Command examples
- [ ] Linked from alerts

**Files to Create**:

- `docs/runbooks/p03-consolidation.md`

---

#### Issue 9.3.2: Update Architecture Documentation

**Type**: Documentation
**Priority**: Medium
**Assignee**: Tech Lead
**Labels**: `documentation`, `p03`

**Description**:
Update architecture docs with P03 details.

**Updates Required**:

1. Add P03 to pipeline catalog in `k0/pipelines/whiteboard.md`
2. Register consolidation module in `k0/pipelines/whiteboard_module.md`
3. Update memory layer documentation with P03 writers
4. Add P03 to system architecture diagram

**Acceptance Criteria**:

- [ ] Pipeline catalog updated
- [ ] Module registered
- [ ] Diagrams updated
- [ ] Cross-references added

**Files to Update**:

- `k0/pipelines/whiteboard.md`
- `k0/pipelines/whiteboard_module.md`
- `docs/architecture/diagrams/system-overview.mmd`

---

### Epic 9.4: K0 Architecture Master - Production Status Update

**Description**: Final K0 Architecture Master update - transition P03 status from Implementation to Production.

#### Issue 9.4.1: Update K0 Pipeline Status to Production

**Type**: Documentation
**Priority**: Critical
**Assignee**: Tech Lead
**Labels**: `k0-governance`, `documentation`, `p03`, `production`

**Description**:
After all tests pass and deployment is verified, update P03 status to Production in K0 Architecture Master.

**K0 Final Registration**:

1. **Part 2.1 - Pipeline Registry** - Update P03 status:

```markdown
| P03 | Offline Consolidation | ✅ Production | K0-Foundation | Batch Memory Consolidation |
```

2. **Part 3.1 - Module Registry** - Update all consolidation module statuses:

```markdown
| consolidation.* | Service | ✅ Production | K0/Consolidation | P03 | Per-Cycle |
```

3. **Part 7.1 - ADR Index** - Update ADR statuses to IMPLEMENTED:

| ADR | Status |
|-----|--------|
| ADR-0024 | IMPLEMENTED |
| ADR-XXXX-p03-storage | IMPLEMENTED |
| ADR-XXXX-p03-events | IMPLEMENTED |
| ADR-XXXX-p03-performance | IMPLEMENTED |
| All P03 ADRs | IMPLEMENTED |

4. **Implementation Checklist** - Final verification:

- [ ] All modules implemented and tested
- [ ] All contracts validated
- [ ] All syscalls exercised in tests
- [ ] All event topics emitted and consumed
- [ ] Performance targets met (90 min budget)
- [ ] Security requirements met (band separation)
- [ ] Observability complete (metrics, traces, logs)
- [ ] Runbooks created and linked

**Acceptance Criteria**:

- [ ] P03 status updated to ✅ Production in Part 2.1
- [ ] All consolidation module statuses updated to ✅ Production in Part 3.1
- [ ] All P03 ADR statuses updated to IMPLEMENTED in Part 7.1
- [ ] Implementation checklist verified complete
- [ ] Production readiness sign-off documented

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md` (Part 2.1, 3.1, 7.1)

**K0 Production Readiness Checklist**:

- [ ] All modules registered in Part 3.1
- [ ] All syscalls registered in Part 5.2
- [ ] All event topics registered in Part 4.1
- [ ] All contracts registered in Part 5.1
- [ ] All ADRs in Part 7.1 status = IMPLEMENTED
- [ ] Pipeline status = ✅ Production
- [ ] Cross-pipeline dependencies documented
- [ ] Rollback procedures documented
- [ ] Monitoring dashboards configured
- [ ] Alerting rules configured

---

### Milestone 9 Completion: K0 Architecture Master Closure (FINAL)

> **⚠️ MANDATORY**: Before marking Milestone 9 complete, verify these K0 updates:

**K0 Closure Checklist for M9 (FINAL)**:

| Part | Section | Update Required | Status |
|------|---------|-----------------|--------|
| 2.1 | Pipeline Registry | P03 status: ⚠️ Implementation → ✅ Production | ☐ |
| 3.1 | Module Master Registry | All 37 consolidation.* modules → ✅ Production | ☐ |
| 5.1 | Global Contract Registry | All P03 contracts marked ✅ Validated | ☐ |
| 7.1 | ADR Index | All 12 P03 ADRs → 🏁 Implemented | ☐ |
| 7.1 | ADR Index | ADR status column updated | ☐ |
| 8.2 | Quality Gates | P03 production readiness documented | ☐ |

**Final Verification - Complete K0 Audit**:

| Category | Expected | Actual | Status |
|----------|----------|--------|--------|
| Modules | 37 | | ☐ |
| Syscalls | 28+ | | ☐ |
| Event Topics | 20+ | | ☐ |
| ADRs | 12 | | ☐ |
| Contracts | 15+ | | ☐ |
| Storage Tables | 8+ | | ☐ |

**Commit Message Format**: `docs(k0): M9 complete - P03 → Production, all 12 ADRs implemented, K0 audit passed`

**P03 IS NOT COMPLETE UNTIL THIS CHECKLIST IS 100% VERIFIED.**

---

## Summary

### Total Issue Count by Milestone

| Milestone | Epic Count | Issue Count | K0 Updates | K0 Closure |
|-----------|------------|-------------|------------|------------|
| M0: Pre-Implementation | 3 | 16 | 2 (Initial Registration) | ☐ 4 items |
| M1: Contracts & Infrastructure | 6 | 34 | 1 (Contract Registry) | ☐ 5 items |
| M2: Core Consolidation (R0-R1) | 3 | 8 | 1 (R0/R1 Modules) | ☐ 5 items |
| M3: Pattern Extraction (R2) | 5 | 12 | 1 (R2 Modules) | ☐ 6 items |
| M4: Memory Management (R3) | 6 | 10 | 1 (R3 Modules) | ☐ 7 items |
| M5: Knowledge Graph (R4) | 4 | 9 | 1 (R4 Modules) | ☐ 6 items |
| M5A: Dream Exploration (R5) | 7 | 9 | 2 (R5 Modules + ADR) | ☐ 6 items |
| M6: State Writers (R6-R7) | 3 | 11 | 1 (R6/R7 Modules) | ☐ 5 items |
| M7: Event Emission (R8) | 5 | 7 | 1 (R8 Modules + Status) | ☐ 6 items |
| M8: Testing & Validation | 3 | 14 | 0 | ☐ 4 items |
| M9: Deployment & Observability | 4 | 8 | 1 (Production Status) | ☐ 6 items (FINAL) |
| **TOTAL** | **49** | **138** | **12** | **60 items** |

### K0 Architecture Master Update Summary

| Milestone | K0 Update | Part(s) Updated | Purpose |
|-----------|-----------|-----------------|---------|
| M0 | Issue 0.0.1 | Part 2.1 | Initial P03 Pipeline Registration |
| M0 | Issue 0.0.2 | P03 README | Create per-pipeline README |
| M0 | Issue 0.1.10 | Part 7.1 | Batch ADR Registration |
| M1 | Issue 1.6.1 | Part 5.1, 5.2, 4.1 | Contract, Syscall, Topic Registration |
| M2 | Issue 2.3.1 | Part 3.1, 4.1, 5.2 | R0/R1 Module Registration |
| M3 | Issue 3.5.1 | Part 3.1, 4.1, 5.2 | R2 Module Registration |
| M4 | Issue 4.6.1 | Part 3.1, 4.1, 5.2 | R3 Module Registration |
| M5 | Issue 5.4.1 | Part 3.1, 4.1, 5.2 | R4 Module Registration |
| M5A | Issue 5A.7.1 | Part 3.1, 4.1, 5.2, 7.1 | R5 Module + ADR Registration |
| M6 | Issue 6.3.1 | Part 3.1, 4.1, 5.2 | R6/R7 Module Registration |
| M7 | Issue 7.5.1 | Part 2.1, 3.1, 4.1, 5.2 | R8 Registration + Status Update |
| M9 | Issue 9.4.1 | Part 2.1, 3.1, 7.1 | Production Status Update |

### Critical Path

```
M0 (Pre-Impl) → M1 (Contracts) → M2 (R0-R1) → M3 (R2) → [M4 || M5] → M5A (optional) → M6 → M7 → M8 → M9
                                                           ↓                              ↑
                                                      (Parallel)────────────────────────────
```

**Note**: M5A (Dream Exploration) is **optional** and runs only if consolidation budget allows. Implemented with feature flag, disabled in v1.

### Estimated Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| M0: Pre-Implementation | 5 days | Week 1 |
| M1: Contracts & Infrastructure | 7 days | Week 2-3 |
| M2: Core Consolidation | 5 days | Week 3-4 |
| M3: Pattern Extraction | 6 days | Week 4-5 |
| M4+M5: Memory + KG (Parallel) | 6 days | Week 5-6 |
| M5A: Dream Exploration (v2) | 5 days | Week 6-7 (parallel track) |
| M6: State Writers | 5 days | Week 6-7 |
| M7: Event Emission | 4 days | Week 7-8 |
| M8: Testing | 6 days | Week 8-9 |
| M9: Deployment | 4 days | Week 9-10 |
| **Total (v1 without R5)** | **48 days** | **~10 weeks** |
| **Total (v2 with R5)** | **53 days** | **~11 weeks** |

### Risk Register

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Budget overrun (90 min) | High | Medium | R5 feature flag (skip if budget exceeded) |
| P08 backpressure | Medium | Medium | Queue depth limits, circuit breaker |
| Lock contention | Low | Low | Stale lock cleanup, timeout |
| st_vec missing embeddings | Low | Low | Graceful fallback, skip event in cluster |

> **Note**: NLP model performance risks eliminated — P03 reads pre-computed UltraBERT outputs
> from P02 (entities_json, embeddings, sentiment). No model loading or inference in P03.

---

## Appendix A: File Manifest

### New Files to Create

```
k0/
├── contracts/
│   ├── modules/
│   │   ├── hippocampus.importance_score.v1.yaml
│   │   ├── hippocampus.priority_weight.v1.yaml
│   │   ├── hippocampus.replay_sequence.v1.yaml
│   │   ├── consolidation.episodic_cluster.v1.yaml
│   │   ├── consolidation.pattern_extract.v1.yaml
│   │   ├── consolidation.ca1_bridge.v1.yaml
│   │   ├── consolidation.criteria_check.v1.yaml
│   │   ├── consolidation.semantic_promote.v1.yaml
│   │   ├── synaptic.near_duplicate.v1.yaml
│   │   ├── synaptic.novelty_score.v1.yaml
│   │   ├── synaptic.retention_enforce.v1.yaml
│   │   ├── synaptic.decay_apply.v1.yaml
│   │   ├── synaptic.archive_tombstone.v1.yaml
│   │   ├── kg.entity_normalize.v1.yaml
│   │   ├── kg.relationship_discover.v1.yaml
│   │   ├── kg.temporal_update.v1.yaml
│   │   ├── kg.causal_construct.v1.yaml
│   │   ├── kg.concept_evolve.v1.yaml
│   │   ├── consolidation.update_dedup.v1.yaml
│   │   ├── consolidation.update_cluster.v1.yaml
│   │   ├── consolidation.update_status.v1.yaml
│   │   ├── writers.episodic.v1.yaml
│   │   ├── writers.semantic.v1.yaml
│   │   ├── writers.kg.v1.yaml
│   │   ├── writers.vec_placeholder.v1.yaml
│   │   ├── consolidation.event_emit.v1.yaml
│   │   ├── consolidation.offset_update.v1.yaml
│   │   └── consolidation.metrics.v1.yaml
│   └── pipelines/
│       └── p03_consolidation.v1.yaml
├── config/
│   └── retention_policies.yaml
├── modules/
│   └── consolidation/
│       ├── __init__.py
│       ├── lock_manager.py
│       ├── batch_selector.py
│       ├── trigger_coordinator.py
│       ├── importance_scorer.py
│       ├── priority_weighter.py
│       ├── replay_sequencer.py
│       ├── embedding_reader.py
│       ├── distance_calculator.py
│       ├── episodic_clusterer.py
│       ├── common_element_extractor.py
│       ├── temporal_pattern_detector.py
│       ├── pattern_confidence_scorer.py
│       ├── pattern_name_generator.py
│       ├── semantic_similarity.py
│       ├── ca1_bridge.py
│       ├── criteria_checker.py
│       ├── semantic_promoter.py
│       ├── simhash_calculator.py
│       ├── lsh_index.py
│       ├── duplicate_detector.py
│       ├── novelty_scorer.py
│       ├── retention_enforcer.py
│       ├── decay_calculator.py
│       ├── archiver.py
│       ├── tombstone_manager.py
│       ├── entity_reader.py
│       ├── entity_normalizer.py
│       ├── cooccurrence_detector.py
│       ├── temporal_relationship_detector.py
│       ├── graph_node_manager.py
│       ├── graph_edge_manager.py
│       ├── causal_inference.py
│       ├── counterfactual_thinker.py
│       ├── forward_simulator.py
│       ├── episodic_simulator.py
│       ├── insight_generator.py
│       ├── motor_rehearser.py
│       ├── dream_simulator.py
│       ├── event_emitter.py
│       ├── offset_manager.py
│       ├── metrics_collector.py
│       ├── orchestrator.py
│       ├── state_machine.py
│       └── writers/
│           ├── __init__.py
│           ├── dedup_writer.py
│           ├── cluster_writer.py
│           ├── status_writer.py
│           ├── episodic_writer.py
│           ├── semantic_writer.py
│           ├── procedural_writer.py
│           ├── social_writer.py
│           ├── prospective_writer.py
│           ├── kg_writer.py
│           └── vec_writer.py
├── deploy/
│   └── p03/
│       ├── Dockerfile
│       ├── docker-compose.yml
│       ├── requirements.txt
│       ├── grafana/
│       │   └── p03-dashboard.json
│       ├── prometheus/
│       │   └── alerts.yaml
│       └── k8s/
│           ├── deployment.yaml
│           ├── service.yaml
│           ├── configmap.yaml
│           └── cronjob.yaml
└── storage/
    └── migrations/
        ├── 0030_st_epi.sql
        ├── 0031_st_sem.sql
        ├── 0032_st_procedural.sql
        ├── 0033_st_social.sql
        ├── 0034_st_prospective.sql
        ├── 0035_st_kg_dom.sql
        ├── 0036_st_kg_edges.sql
        ├── 0037_st_vec.sql
        ├── 0038_st_fts.sql
        └── 0039_pipeline_offsets.sql

tests/
├── k0/
│   └── modules/
│       └── consolidation/
│           ├── conftest.py
│           ├── fixtures/
│           │   ├── sample_events.py
│           │   ├── clustered_events.py
│           │   └── duplicate_events.py
│           ├── test_lock_manager.py
│           ├── test_batch_selector.py
│           ├── test_trigger_coordinator.py
│           ├── test_importance_scorer.py
│           ├── test_priority_weighter.py
│           ├── test_replay_sequencer.py
│           ├── test_embedding_reader.py
│           ├── test_distance_calculator.py
│           ├── test_episodic_clusterer.py
│           ├── test_common_element_extractor.py
│           ├── test_temporal_pattern_detector.py
│           ├── test_pattern_confidence_scorer.py
│           ├── test_pattern_name_generator.py
│           ├── test_semantic_similarity.py
│           ├── test_ca1_bridge.py
│           ├── test_criteria_checker.py
│           ├── test_semantic_promoter.py
│           ├── test_simhash_calculator.py
│           ├── test_lsh_index.py
│           ├── test_duplicate_detector.py
│           ├── test_novelty_scorer.py
│           ├── test_retention_enforcer.py
│           ├── test_decay_calculator.py
│           ├── test_archiver.py
│           ├── test_tombstone_manager.py
│           ├── test_entity_reader.py
│           ├── test_entity_normalizer.py
│           ├── test_cooccurrence_detector.py
│           ├── test_temporal_relationship_detector.py
│           ├── test_graph_node_manager.py
│           ├── test_graph_edge_manager.py
│           ├── test_causal_inference.py
│           ├── test_counterfactual_thinker.py
│           ├── test_forward_simulator.py
│           ├── test_episodic_simulator.py
│           ├── test_insight_generator.py
│           ├── test_motor_rehearser.py
│           ├── test_dream_simulator.py
│           ├── test_event_emitter.py
│           ├── test_offset_manager.py
│           ├── test_metrics_collector.py
│           ├── test_orchestrator.py
│           ├── test_state_machine.py
│           └── writers/
│               ├── test_dedup_writer.py
│               ├── test_cluster_writer.py
│               ├── test_status_writer.py
│               ├── test_episodic_writer.py
│               ├── test_semantic_writer.py
│               ├── test_procedural_writer.py
│               ├── test_social_writer.py
│               ├── test_prospective_writer.py
│               ├── test_kg_writer.py
│               └── test_vec_writer.py
├── integration/
│   └── p03/
│       ├── test_full_cycle.py
│       ├── test_crash_recovery.py
│       ├── test_lock_contention.py
│       └── test_p08_coordination.py
└── performance/
    └── p03/
        ├── test_1000_event_batch.py
        └── test_10000_event_stress.py

docs/
├── architecture/
│   └── decisions-K0/
│       ├── k010-p03-consolidation-architecture.md
│       ├── k010.1-sleep-cycle-state-machine.md
│       ├── k010.2-importance-scoring-formula.md
│       ├── k010.3-episodic-clustering-algorithm.md
│       ├── k010.4-ca1-bridge-decision-protocol.md
│       ├── k010.5-simhash-deduplication.md
│       ├── k010.6-entity-normalization-strategy.md
│       ├── k010.7-8-layer-memory-write-coordination.md
│       ├── k010.8-p08-embedding-coordination.md
│       ├── k010.9-capability-based-security.md
│       ├── k010.10-dream-phase-algorithms.md
│       └── k010.11-ultrabert-data-consumption.md
├── plans/
│   └── P03_implementation_plan_v2.md (this file)
└── runbooks/
    └── p03-consolidation.md
```

### Dependencies to Add

```toml
# pyproject.toml additions

[project.dependencies]
# NOTE: spaCy and sentence-transformers REMOVED — P03 consumes UltraBERT outputs from P02
# P02 already computed: entities_json, kg_triples_json, sentiment, emotions, 768-dim embeddings
# P03 reads from st_hipp_events and st_vec — ZERO new model calls required
scikit-learn = ">=1.2.0"  # DBSCAN clustering
numpy = ">=1.24.0"
prometheus-client = ">=0.16.0"
mmh3 = ">=3.0.0"  # MurmurHash3 for SimHash
python-Levenshtein = ">=0.20.0"  # Fuzzy string matching for entity resolution
croniter = ">=1.3.0"  # Cron expression parsing
pgmpy = ">=0.1.23"  # Bayesian networks for R5 counterfactuals
dppy = ">=0.3.2"  # Determinantal Point Process for R5 scenario diversity
python-constraint = ">=1.4.0"  # CSP for R5 episodic simulation
networkx = ">=3.1"  # Graph operations for R5 insight generation
```

> **Architecture Decision (ADR-k010.11)**: P03 does NOT load any NLP models. All NLP outputs
> (NER, sentiment, emotions, embeddings) are pre-computed by P02 via UltraBERT single-pass
> and stored in `st_hipp_events` and `st_vec`. P03 reads these outputs directly from the database.

---

## Appendix B: Open Questions Resolution

| ID | Question | Resolution |
|----|----------|------------|
| Q1 | M24 circular dependency | Split Coordinator/Executor - tracked in Issue 0.2.1 |
| Q2 | Recency half-life | 7 days default - configurable in ImportanceScorer |
| Q3 | Replay sequence gap | 200ms theta gaps in ReplaySequencer |
| Q4 | Budget 182min vs 90min | R5 feature flag (skip if budget exceeded) + R3/R4 parallel |
| Q5 | Race condition batch select | Lock acquisition in Issue 2.1.1 |
| Q6 | DBSCAN eps | 0.3 default - tuned via validation tests |
| Q7 | Pattern type classification | Heuristic in temporal_pattern_detector.py |
| Q8 | Confidence geometric mean | Implemented in pattern_confidence_scorer.py |
| Q9 | Multiple CA1 matches | Highest similarity wins - Issue 3.3.2 |
| Q10 | archival_deadline logic | In retention_enforcer.py with novelty adjustment |
| Q11 | Near-duplicate threshold | Hamming ≤3 → Jaccard >0.8 confirmation |
| Q12 | novelty_score formula | Implemented in novelty_scorer.py |
| Q13 | KG strength normalization | count / max_count in cooccurrence_detector.py |
| Q14 | P08 backpressure | Queue depth check in vec_writer.py |
| Q15 | Edge observation_count | Increment on upsert in graph_edge_manager.py |
| Q16 | Causal confidence | frequency × consistency in causal_inference.py |
| Q17 | Node evolution detection | Embedding drift >0.3 triggers new version |
| Q18 | Offset idempotency | cycle_id check in offset_manager.py |
| Q19 | Metric histogram buckets | Aligned with 90min SLO in metrics_collector.py |
| Q20 | Event retry policy | 3 retries with exponential backoff |
| Q21 | Trigger priority | Manual > Threshold > Idle > Scheduled |
| Q22 | Lock timeout | 30 seconds default, 2 hour stale cleanup |
| Q23 | Checkpoint interval | Every 100 events for crash recovery |
| Q24 | R5 Dream phase enablement | Feature flag (default: disabled in v1, enabled in v2) |
| Q25 | R5 sub-phase budgets | Counterfactual: 2min, Forward: 2min, Episodic: 1.5min, Insight: 2min, Motor: 0.5min |

---

*Document Version: 2.0.0*
*Last Updated: 2025-01-XX*
*Status: Ready for Implementation*
