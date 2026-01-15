# P03 Milestone 1 Execution Document

> **Milestone**: M1 — Core pipeline skeleton + envelope + sequential runner
> **Status**: NOT_STARTED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Prerequisites**: M0 COMPLETED (2025-12-31)
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: TBD (after M0 merge)

---

## Part A: Context Foundation (BEFORE YOU START)

### A.0 M0 Outputs (PREREQUISITES FROM PREVIOUS MILESTONE)

> **Reference**: [M0_EXECUTION.md](./M0_EXECUTION.md)

**M0 Created These Artifacts That M1 Depends On**:

| Artifact | Path | M1 Issues Using It |
|----------|------|-------------------|
| Pipeline ADR | [k010-p03-consolidation-architecture.md](../architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md) | 1.1.1, 1.2.1 |
| State Machine ADR | [k010.1-sleep-cycle-state-machine.md](../architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md) | 1.2.1, 1.2.2, 1.2.7 |
| Capability ADR | [k010.9-capability-based-security.md](../architecture/decisions-K0/pipelines/k010.9-capability-based-security.md) | 1.3.4, 1.3.6 |
| Pipeline Contract | [k0/contracts/pipelines/p03_consolidation.v1.yaml](../../k0/contracts/pipelines/p03_consolidation.v1.yaml) | 1.3.1, 1.3.5 |
| Module Contracts | [k0/contracts/modules/consolidation.*.v1.yaml](../../k0/contracts/modules/) | 1.1.4, 1.2.2 |
| Capability Contract | [k0/contracts/capabilities/consolidation.v1.yaml](../../k0/contracts/capabilities/consolidation.v1.yaml) | 1.3.4, 1.3.6 |
| Event Schemas | [k0/contracts/schemas/p03_*.json](../../k0/contracts/schemas/) | 1.1.4, 1.2.4 |
| Config Schema | [k0/contracts/jsonschema/p03.config.schema.json](../../k0/contracts/jsonschema/p03.config.schema.json) | 1.3.5 |
| Master Registry Update | [k0_architecture_master.md](../../governance/k0/k0_architecture_master.md) | All issues |

**M0 Governance Status**: ✅ SYNCED (verified 2025-12-31)

### A.1 Dossier Sections Governing This Milestone

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| §4.0 | Phase Transition Rules | [Dossier §4.0](../pipelines/P03_consolidation_dossier_v2.md#40-phase-transition-rules) | Sequential runner transitions |
| Appendix G | R0-R8 State Machine Spec | [Dossier Appendix G](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) | Phase states, idempotency, retries |
| Appendix G.2 | Per-Phase Tables | [Dossier Appendix G.2](../pipelines/P03_consolidation_dossier_v2.md#g2-per-phase-specification) | Phase contracts |
| Appendix G.5 | Phase Metrics | [Dossier Appendix G.5](../pipelines/P03_consolidation_dossier_v2.md#g5-phase-metrics) | Observability |

### A.2 Envelope Discovery Document (PRIMARY SOURCE)

| Part | Title | Link | Issues Using It |
|------|-------|------|-----------------|
| Part II §14-21 | Envelope Fields & Per-Phase State | [P03_envelope_fields_discovery.md](../pipelines/P03_envelope_fields_discovery.md) | 1.1.1-1.1.8 |
| §1.1-1.4 | Batch-Level Fields | [Envelope §1](../pipelines/P03_envelope_fields_discovery.md#1-batch-level-fields) | 1.1.2 |
| §2.x | Per-Event Fields | [Envelope §2](../pipelines/P03_envelope_fields_discovery.md#2-per-event-fields) | 1.1.3 |
| §3.x | Per-Phase Output Fields | [Envelope §3](../pipelines/P03_envelope_fields_discovery.md#3-per-phase-output-fields-r0-r8) | 1.1.4 |
| §7.x | Observability Fields | [Envelope §7](../pipelines/P03_envelope_fields_discovery.md#7-observability-fields) | 1.1.6 |

### A.3 Dossier Notes (Implementation Clarifications)

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| Envelope Architecture | Immutability / Lazy Embedding | [Dossier Notes](../pipelines/P03_consolidation_dossier_v2_notes.md) | 1.1.1, 1.1.2, 1.1.3 |
| Execution Model | Phase boundaries | [Dossier Notes](../pipelines/P03_consolidation_dossier_v2_notes.md) | 1.2.x |

### A.4 Existing Code Patterns to Reference

| Pattern | Path | What to Learn |
|---------|------|---------------|
| Pydantic Envelope | [k0/feedback/envelope.py](../../k0/feedback/envelope.py) | Pydantic BaseModel with frozen config, validators |
| Pipeline Protocol | [k0/pipelines/protocol.py](../../k0/pipelines/protocol.py) | PipelineProtocol interface, PipelineContext |
| Pipeline Runner | [k0/runtime/pipeline_runner.py](../../k0/runtime/pipeline_runner.py) | Existing DAG runner (NOT for P03, but understand pattern) |
| Kernel Envelope Schema | [k0/contracts/jsonschema/envelope.schema.json](../../k0/contracts/jsonschema/envelope.schema.json) | NOT P03BatchEnvelope (different purpose) |

### A.5 ADRs to Reference

| ADR | Path | Governs |
|-----|------|---------|
| K010 | [k010-p03-consolidation-architecture.md](../architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md) | P03 pipeline architecture |
| K010.1 | [k010.1-sleep-cycle-state-machine.md](../architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md) | R0-R8 state machine |
| K010.9 | [k010.9-capability-based-security.md](../architecture/decisions-K0/pipelines/k010.9-capability-based-security.md) | Capability model |

### A.6 Governance Sync Tool (RUN BEFORE AND AFTER EACH EPIC)

| Tool | Path | Command |
|------|------|---------|
| Sync Script | [governance/k0/scripts/sync.py](../../governance/k0/scripts/sync.py) | `python -m governance.k0.scripts.sync --report` |
| Event Scanner | [governance/k0/scripts/event_scanner.py](../../governance/k0/scripts/event_scanner.py) | Validates event topics |
| Contract Scanner | [governance/k0/scripts/contract_scanner.py](../../governance/k0/scripts/contract_scanner.py) | Validates contract files |
| ADR Scanner | [governance/k0/scripts/adr_scanner.py](../../governance/k0/scripts/adr_scanner.py) | Validates ADR index |

**When To Run Governance Sync**:

- ✅ Before starting any Epic (capture baseline)
- ✅ After completing any Epic (verify no drift)
- ✅ Before marking M1 complete (final verification)

### A.7 Directory Structure (WHERE TO CREATE FILES)

| Purpose | Path | Exists | Create In |
|---------|------|--------|-----------|
| P03 Pipeline Code | `k0/pipelines/p03/` | ❌ No | Issue 1.1.1 decision |
| P03 Runtime Code | `k0/runtime/p03/` | ❌ No | Alternative location |
| P03 Tests | `tests/k0/pipelines/p03/` | ❌ No | Issue 1.1.8 |

---

## Part B: Code Discovery Results

> **Fill this section DURING Epic execution with actual code findings**

### B.1 Existing Envelope Patterns Found

| File | Pattern | Relevant For |
|------|---------|--------------|
| `k0/feedback/envelope.py` | Pydantic BaseModel with `model_config = ConfigDict(extra="forbid")` | 1.1.1 decision |
| `k0/feedback/envelope.py` | Field validators, AliasChoices | 1.1.2, 1.1.3 |

### B.2 Existing Pipeline Patterns Found

| File | Pattern | Relevant For |
|------|---------|--------------|
| `k0/pipelines/protocol.py` | `PipelineProtocol` (Protocol class) | 1.2.1 decision |
| `k0/pipelines/protocol.py` | `PipelineContext` (dataclass) | 1.2.2, 1.2.3 |
| `k0/runtime/pipeline_runner.py` | DAG-based parallel runner | 1.2.1 (contrast) |

---

## Part C: Scope Boundaries (WHAT TO DO / NOT DO)

### C.1 Files To CREATE (Epic 1.1)

| File Path | Purpose | Created By Issue |
|-----------|---------|------------------|
| TBD (decision in 1.1.1) | P03CycleContext | 1.1.2 |
| TBD (decision in 1.1.1) | P03EventState + enums | 1.1.3 |
| TBD (decision in 1.1.1) | P03PhaseOutputs + types | 1.1.4 |
| TBD (decision in 1.1.1) | P03StagedWrites | 1.1.5 |
| TBD (decision in 1.1.1) | P03ObservabilityContext | 1.1.6 |
| TBD (decision in 1.1.1) | P03EnvelopeSerializer | 1.1.7 |
| `tests/k0/pipelines/p03/test_envelope.py` | Envelope tests | 1.1.8 |

### C.2 Files To NEVER TOUCH

| File Path | Reason |
|-----------|--------|
| `k0/contracts/jsonschema/envelope.schema.json` | Kernel envelope, not P03BatchEnvelope |
| `k0/runtime/pipeline_runner.py` | Generic DAG runner, P03 needs sequential |
| `k0/feedback/envelope.py` | Reference only, don't modify |

### C.3 Out of Scope (Deferred)

| Item | Deferred To | Reason |
|------|-------------|--------|
| Database writes | M2 | Storage is M2 scope |
| Actual phase implementations | M3-M6 | Phase code is later milestones |
| P08 embedding integration | M4 | Embedding pipeline integration |

---

## Part D: Execution Checklist (THE WORK)

### Epic 1.1 — Envelope model (from envelope discovery)

> **Status**: ✅ **COMPLETED** (2025-01-01)
> **Source**: [P03_envelope_fields_discovery.md](../pipelines/P03_envelope_fields_discovery.md)
> **Governance Baseline**: SYNCED (2025-12-31 20:56)
> **All 8 issues complete**: 1.1.1–1.1.8 ✅

**Summary**:

- Created `k0/pipelines/p03/` module with 10 submodules:
  - `context.py` - P03CycleContext (frozen)
  - `event_state.py` - P03EventState + enums
  - `phase_outputs.py` - P03PhaseOutputs + 22 aggregate types
  - `staged_writes.py` - P03StagedWrites + WriteOperation
  - `observability.py` - P03ObservabilityContext + P03Error
  - `serializer.py` - P03EnvelopeSerializer + PhaseCheckpoint
  - `envelope.py` - P03BatchEnvelope (top-level container)
  - `runner_contract.py` - Phase contracts (Issue 1.2.1)
  - `phase_interface.py` - Phase interface (Issue 1.2.2)
  - `sequential_runner.py` - P03SequentialRunner (Issue 1.2.3)
- Total coverage: **91.74%** (exceeds 80% requirement)
- 125 tests passing, deterministic, no flaky tests

---

#### Issue 1.1.1 — Confirm envelope design + choose implementation pattern

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Translate envelope design spec into implementation-ready blueprint without drifting from dossier/discovery.

**Decisions Required**:

1. [x] Confirm P03BatchEnvelope is INTERNAL pipeline state (distinct from kernel envelope)
2. [x] Choose: **dataclasses** vs **Pydantic BaseModel**
3. [x] Choose module location: `k0/runtime/p03/` vs `k0/pipelines/p03/`

**Inputs Required**:

- [x] Envelope discovery spec: [P03_envelope_fields_discovery.md](../pipelines/P03_envelope_fields_discovery.md) (Part II, §14-21)
- [x] Dossier notes: [P03_consolidation_dossier_v2_notes.md](../pipelines/P03_consolidation_dossier_v2_notes.md)
- [x] Existing pattern: [k0/feedback/envelope.py](../../k0/feedback/envelope.py)

---

### 🎯 DECISION NOTE — Issue 1.1.1

#### Decision 1: P03BatchEnvelope is INTERNAL pipeline state

**CONFIRMED**: P03BatchEnvelope is distinct from `k0/feedback/envelope.py` (FeedbackEnvelope).

| Aspect | FeedbackEnvelope | P03BatchEnvelope |
|--------|------------------|------------------|
| Purpose | Pipeline-agnostic feedback routing | P03-specific consolidation state |
| Scope | Cross-pipeline | P03 internal only |
| Mutability | Mostly immutable | Mixed (context frozen, events mutable) |
| Serialization | JSON for inter-pipeline | JSON for checkpoints/DLQ |

**Rationale**: Discovery doc §14.3 explicitly shows P03BatchEnvelope as internal state with nested hierarchy (context, events, phases, staged, observability). It never crosses pipeline boundaries.

#### Decision 2: Use **dataclasses** (not Pydantic)

**CHOSEN**: Python `dataclasses` with `@dataclass(frozen=True)` for immutable parts

| Criterion | dataclass | Pydantic | Winner |
|-----------|-----------|----------|--------|
| Immutability | `frozen=True` native | Requires `model_config` | dataclass |
| Performance | Faster (no validation overhead) | Slower | dataclass |
| JSON Serialization | Manual `asdict()` / custom | Built-in `.model_dump()` | Pydantic |
| Validation | Manual | Built-in | Pydantic |
| Discovery Spec | Uses dataclass examples | — | dataclass |
| Codebase Pattern | Mixed (feedback uses Pydantic) | — | Tie |

**Rationale**:

1. Discovery doc §15.x provides all examples as `@dataclass` (including `frozen=True` for `P03CycleContext`)
2. P03 envelope is internal — no need for Pydantic's validation/parsing for external inputs
3. Performance matters for batch processing (100+ events per cycle)
4. Serialization will be explicit via `P03EnvelopeSerializer` (Issue 1.1.7)

**Exception**: If validation becomes critical, we can add `pydantic.dataclasses` decorator later without changing API.

#### Decision 3: Module location — `k0/pipelines/p03/`

**CHOSEN**: `k0/pipelines/p03/`

| Option | Pros | Cons |
|--------|------|------|
| `k0/pipelines/p03/` | Aligns with pipeline organization, near contracts | New subdirectory |
| `k0/runtime/p03/` | Near runner code | Runtime is execution, not domain models |

**Rationale**:

1. `k0/pipelines/` contains pipeline-specific code (protocol, whiteboard)
2. Mirrors contract structure: `k0/contracts/pipelines/p03_consolidation.v1.yaml`
3. Clear separation: models in `k0/pipelines/p03/`, runner integration in `k0/runtime/`

#### File Layout

```
k0/pipelines/p03/
├── __init__.py
├── envelope.py           # P03BatchEnvelope, P03Phase enum
├── context.py            # P03CycleContext (frozen)
├── event_state.py        # P03EventState, ReconciliationAction enum
├── phase_outputs.py      # P03PhaseOutputs + all aggregate types
├── staged_writes.py      # P03StagedWrites, WriteOperation enum
├── observability.py      # P03ObservabilityContext, P03Error
├── serializer.py         # P03EnvelopeSerializer
└── README.md             # Module documentation
```

**Mapping to Discovery Spec**:

| File | Discovery Section | Issue |
|------|-------------------|-------|
| `context.py` | §15.2 | 1.1.2 |
| `event_state.py` | §16.1-16.3 | 1.1.3 |
| `phase_outputs.py` | §17.x | 1.1.4 |
| `staged_writes.py` | §18.1 | 1.1.5 |
| `observability.py` | §19.1 | 1.1.6 |
| `serializer.py` | §21.2 | 1.1.7 |
| `envelope.py` | §15.1 | All (top-level) |

---

**Deliverables**:

- [x] Decision note in this ticket (above)
- [x] Chosen representation: **dataclasses**
- [x] Chosen file layout: `k0/pipelines/p03/`
- [x] Rationale documented

**Acceptance**:

- [x] Implementation plan maps to discovery spec sections
- [x] Lists which classes will exist and where

**Blocked By**: M0 ✅

**Blocks**: 1.1.2, 1.1.3, 1.1.4, 1.1.5, 1.1.6, 1.1.7

---

#### Issue 1.1.2 — Implement immutable cycle context (P03CycleContext)

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Create the immutable "batch header" required by dossier: set once in R0 and never mutated.

**Spec Reference**: [P03_envelope_fields_discovery.md §1.1-1.4](../pipelines/P03_envelope_fields_discovery.md#1-batch-level-fields)

**Fields From Discovery Document**:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `cycle_id` | str (ULID) | R0 | Unique cycle identifier |
| `batch_id` | str | R0 | SHA256(sorted(event_ids))[:16] |
| `tenant_id` | str | Input | Multi-tenant isolation |
| `space_id` | str | Input | User/family space identifier |
| `trace_id` | str | Input | Distributed tracing identifier |
| `trigger_type` | str | Input | "INTERVAL" / "THRESHOLD" / "MANUAL" / "IDLE" |
| `trigger_reason` | str | Input | Human-readable trigger description |
| `triggered_at` | int | Input | Unix timestamp (ms) when triggered |
| `scheduler_token` | str | K0 Scheduler | QoS scheduler token |
| `qos_band` | str | K0 | "GREEN" / "AMBER" / "RED" |
| `priority` | int | Config | Batch priority (0-100) |
| `deadline_ms` | int | Config | Hard deadline for completion |
| `batch_size` | int | R0 | Number of events in batch |
| `event_ids` | List[str] | R0 | ULIDs of events (immutable) |
| `pending_before` | int | R0 | Total pending before selection |

**Inputs Required**:

- [x] Design decision from 1.1.1 (dataclass vs Pydantic, location)
- [x] Spec: [P03_envelope_fields_discovery.md §1.1-1.4, §15.2](../pipelines/P03_envelope_fields_discovery.md#1-batch-level-fields)
- [x] Dossier notes: [P03_consolidation_dossier_v2_notes.md](../pipelines/P03_consolidation_dossier_v2_notes.md) (immutability after R0)

**Deliverables**:

- [x] Implement `P03CycleContext` class with all fields above → [k0/pipelines/p03/context.py](../../k0/pipelines/p03/context.py)
- [x] Factory method `create(...)` matching discovery spec
- [x] Enforced immutability (`@dataclass(frozen=True)`)
- [x] `batch_id` computed deterministically: `SHA256(sorted(event_ids))[:16]`
- [x] Helper: `generate_ulid()` for ULID-like ID generation (Crockford base32)
- [x] Helper methods: `remaining_deadline_ms()`, `is_deadline_exceeded()`, `contains_event()`

**Implementation Notes**:

```python
# Usage example
ctx = P03CycleContext.create(
    tenant_id="tenant-001",
    space_id="family-abc",
    event_ids=["01JFXYZ...", "01JFXYZ..."],
    trigger_type="INTERVAL",
    trigger_reason="Scheduled 4-hour consolidation",
)
# ctx.batch_id → deterministic hash of sorted event IDs
# ctx.batch_size = 99  # FrozenInstanceError (immutability enforced)
```

**Acceptance**:

- [x] `P03CycleContext` is frozen after construction
- [x] `batch_id` is stable/deterministic for same event IDs (verified: sorted IDs → SHA256[:16])

**Blocked By**: 1.1.1 ✅

**Blocks**: 1.1.8

---

#### Issue 1.1.3 — Implement per-event state (P03EventState) + decision enums

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Provide a single per-event state object that accumulates enrichment from R1-R6 and supports idempotent retries.

**Spec Reference**: [P03_envelope_fields_discovery.md §2.x, §16.1](../pipelines/P03_envelope_fields_discovery.md#2-per-event-fields)

**Enums Implemented**:

```python
class ReconciliationAction(Enum):
    PENDING = "PENDING"       # Initial state
    REINFORCE = "REINFORCE"   # Strengthen existing (sim >= 0.85)
    EXTEND = "EXTEND"         # Add detail (0.60 <= sim < 0.85)
    CREATE = "CREATE"         # New truth record
    EVOLVE = "EVOLVE"         # Version existing
    CONTRADICT = "CONTRADICT" # Conflicts (flagged for P06)
    PRUNE = "PRUNE"           # Decay below threshold
    SKIP = "SKIP"             # Duplicate or filtered

class PruneDecision(Enum):
    KEEP = "KEEP"             # Retain in active store
    ARCHIVE = "ARCHIVE"       # Move to cold storage
    TOMBSTONE = "TOMBSTONE"   # Mark for deletion
```

**P03EventState Fields** (from discovery §2.1-2.8):

| Category | Fields |
|----------|--------|
| Identification | `event_id`, `hipp_event_id` |
| Content (P02) | `content_text`, `content_type`, `content_hash`, `simhash_hex`, `channel_id`, `timestamp` |
| NLP (P02) | `embedding_id` (lazy), `embedding_768`, `sentiment_score`, `sentiment_label`, `emotions_json`, `intent_label`, `ner_entities_json`, `temporal_expressions_json` |
| R1 Importance | `importance_score`, `recency_factor`, `affect_factor`, `social_factor`, `novelty_factor`, `importance_computed`, `hebbian_updates` |
| R2 Cluster | `cluster_id`, `cluster_label`, `is_noise`, `centroid_distance` |
| R3 Reconciliation | `reconciliation_action`, `best_match_id`, `best_match_layer`, `similarity_score`, `confidence`, `reconciliation_reason` |
| R3 Decay | `decay_score`, `lambda_decay`, `days_since_access`, `access_count`, `prune_decision` |
| R3 Dedup | `is_duplicate`, `duplicate_of_id`, `hamming_distance` |
| R6 Locking | `expected_version`, `version_conflict` |
| R7 Write | `write_success`, `write_error`, `written_to_layer`, `written_record_id` |

**Key Requirement**: Lazy Embedding Materialization ✅

- Store `embedding_id` only by default
- `materialize_embedding()` method loads vector only when needed
- `clear_embedding()` method frees memory after R3

**Inputs Required**:

- [x] Design decision from 1.1.1
- [x] Spec: [P03_envelope_fields_discovery.md §2.x, §16.1](../pipelines/P03_envelope_fields_discovery.md#2-per-event-fields)

**Deliverables**:

- [x] `ReconciliationAction` enum (8 values) → [k0/pipelines/p03/event_state.py](../../k0/pipelines/p03/event_state.py)
- [x] `PruneDecision` enum (3 values) → [k0/pipelines/p03/event_state.py](../../k0/pipelines/p03/event_state.py)
- [x] `P03EventState` dataclass with all fields
- [x] Helper methods: `materialize_embedding()`, `clear_embedding()`, `set_importance()`, `add_hebbian_update()`, `assign_cluster()`, `mark_as_noise()`, `set_reconciliation()`, `mark_duplicate()`, `set_decay()`, `set_version_conflict()`, `set_write_result()`
- [x] Utility methods: `is_actionable()`, `needs_truth_write()`, `needs_reinforcement()`, `to_summary_dict()`
- [x] Factory method: `from_hipp_event()` for R0 initialization

**Implementation Notes**:

```python
# Usage example - R0 initialization
event = P03EventState.from_hipp_event(
    event_id="01JFXYZ...",
    hipp_event_id="hipp_123",
    content_text="Had lunch with mom",
    content_type="CHAT",
    content_hash="abc123...",
    simhash_hex="ff00ff00...",
    timestamp=1735600000000,
    channel_id="whatsapp",
    embedding_id="vec_456",
)

# R1 - set importance
event.set_importance(score=0.85, recency=0.3, affect=0.2, social=0.2, novelty=0.15)

# R3 - set reconciliation
event.set_reconciliation(
    action=ReconciliationAction.CREATE,
    confidence=0.92,
    reason="Novel family event"
)
```

**Acceptance**:

- [x] Default construction does NOT require loading embeddings (IDs only)
- [x] Event state updates mutate in-place (not frozen like context)
- [x] All phase helper methods tested

**Blocked By**: 1.1.1 ✅

**Blocks**: 1.1.8

---

#### Issue 1.1.4 — Implement per-phase outputs (P03PhaseOutputs)

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Container for all R0-R8 phase outputs with aggregate types (EpisodeCluster, DedupMerge, KGEntity, etc.)

**Spec Reference**: [P03_envelope_fields_discovery.md §17.x](../pipelines/P03_envelope_fields_discovery.md#17-phase-outputs-container)

**Implemented Types** (22 total):

| Category | Types Implemented |
|----------|-------------------|
| R1 | `ScoredEvent`, `HebbianEdgeUpdate` |
| R2 | `EpisodeCluster` |
| R3 | `DedupMerge`, `DecayUpdate` |
| R4 | `KGEntity`, `KGEntityUpdate`, `KGEdge`, `KGEdgeUpdate`, `CausalEdge`, `GapCandidate` |
| R5 | `CounterfactualScenario`, `Insight`, `RoutineOptimization`, `ProspectiveMemory` |
| R6 | `EventStatusUpdate`, `TruthWrite`, `ReconciliationSummary` |
| R7 | `WriteResult`, `WriteManifest` |
| R8 | `EmittedEvent`, `CycleSummary` |
| Container | `P03PhaseOutputs` |

**Inputs Required**:

- [x] Design decision from 1.1.1
- [x] Spec: [P03_envelope_fields_discovery.md §17.x](../pipelines/P03_envelope_fields_discovery.md#17-phase-outputs-container)

**Deliverables**:

- [x] `P03PhaseOutputs` container class with R0-R8 output slots → [k0/pipelines/p03/phase_outputs.py](../../k0/pipelines/p03/phase_outputs.py)
- [x] All aggregate dataclasses (22 types) → [k0/pipelines/p03/phase_outputs.py](../../k0/pipelines/p03/phase_outputs.py)
- [x] Helper methods: `set_r6_counts()`, `total_kg_changes()`, `total_insights()`, `to_summary_dict()`
- [x] Property helpers on types: `EpisodeCluster.event_count`, `EpisodeCluster.duration_ms`, `ReconciliationSummary.total_processed`

**Implementation Notes**:

```python
# Usage example
outputs = P03PhaseOutputs()

# R1 populates importance scores
outputs.r1_scored_events.append(ScoredEvent(...))
outputs.r1_total_importance = 4.5

# R2 creates clusters
outputs.r2_clusters.append(EpisodeCluster(
    cluster_id="c1",
    member_event_ids=["e1", "e2", "e3"],
))

# R6 sets reconciliation summary
outputs.set_r6_counts(reinforce=5, create=3, skip=2)
print(outputs.r6_summary.total_processed)  # 8

# Get summary for logging
summary = outputs.to_summary_dict()
```

**Design Decisions**:

- Used flat container (not Optional[RxOutput] per phase) for simpler access
- All aggregate types are mutable (not frozen) - frozen would require rebuilding on every append
- `ReconciliationSummary` has computed properties for totals
- TIMESTAMP CONVENTION: All `*_ts`, `*_start`, `*_end` fields use MILLISECONDS

**Acceptance**:

- [x] Phase outputs grouped by phase (r1_*, r2_*, etc.)
- [x] All 22 aggregate types implemented with correct fields
- [x] Helper methods for common operations
- [x] `to_summary_dict()` for compact logging/metrics

**Blocked By**: 1.1.1 ✅

**Blocks**: 1.1.7, 1.1.8

---

#### Issue 1.1.5 — Implement staged writes container (P03StagedWrites)

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Accumulator for deferred writes (R1-R6 accumulate, R7 commits atomically)

**Spec Reference**: [P03_envelope_fields_discovery.md §18.1](../pipelines/P03_envelope_fields_discovery.md#18-staged-writes-container)

**Implemented Types**:

| Type | Purpose |
|------|---------|
| `WriteOperation` | Enum: INSERT, UPDATE, ARCHIVE, TOMBSTONE |
| `StagedWrite` | Single deferred write with factory methods |
| `StagedOutboxEvent` | Event for R8 emission after commit |
| `P03StagedWrites` | Container with layer buckets |

**Layer Constants** (10 total):

- `LAYER_ST_EPI`, `LAYER_ST_SEM`, `LAYER_ST_PROCEDURAL`, `LAYER_ST_SOCIAL`, `LAYER_ST_PROSPECTIVE`
- `LAYER_ST_KG_DOM`, `LAYER_ST_KG_EDGES`, `LAYER_ST_VEC`
- `LAYER_ST_HIPP_EVENTS`, `LAYER_ST_LEARNING_QUEUE`
- `VALID_LAYERS` frozenset for validation

**Inputs Required**:

- [x] Design decision from 1.1.1
- [x] Spec: [P03_envelope_fields_discovery.md §18.1](../pipelines/P03_envelope_fields_discovery.md#181-deferred-write-accumulation)

**Deliverables**:

- [x] `WriteOperation` enum → [staged_writes.py](../../k0/pipelines/p03/staged_writes.py)
- [x] `StagedWrite` dataclass with factory methods `insert()`, `update()`, `archive()`, `tombstone()` → [staged_writes.py](../../k0/pipelines/p03/staged_writes.py)
- [x] `StagedOutboxEvent` dataclass with `create()` factory → [staged_writes.py](../../k0/pipelines/p03/staged_writes.py)
- [x] `P03StagedWrites` container with layer buckets → [staged_writes.py](../../k0/pipelines/p03/staged_writes.py)
- [x] Methods: `add_write()`, `add_outbox_event()`, `total_writes()`, `get_all_writes_ordered()`, `get_writes_by_layer()`, `get_writes_by_phase()`, `to_summary_dict()`, `clear()`

**Implementation Notes**:

```python
# Usage example
staged = P03StagedWrites()

# R3 stages episodic insert
staged.add_write(StagedWrite.insert(
    layer="st_epi",
    record_id="ep123",
    data={"title": "Morning routine", "score": 0.8},
    phase="R3",
    event_ids=["e1", "e2"]
))

# R4 stages KG entity update
staged.add_write(StagedWrite.update(
    layer="st_kg_dom",
    record_id="ent456",
    data={"canonical_name": "Updated Name"},
    phase="R4",
    expected_version=3
))

# R8 stages outbox event
staged.add_outbox_event("p03.cycle.completed", {"cycle_id": "c1"}, "R8")

# R7 commits in dependency order
for write in staged.get_all_writes_ordered():
    unit_of_work.execute(write)
# Order: vec → kg_dom → kg_edges → epi → sem → ...
```

**Idempotency Key Format**:

- INSERT: `{phase}:{layer}:{record_id}`
- UPDATE: `{phase}:{layer}:{record_id}:v{expected_version}`
- ARCHIVE: `{phase}:{layer}:{record_id}:archive`
- TOMBSTONE: `{phase}:{layer}:{record_id}:tombstone`

**Acceptance**:

- [x] `idempotency_key` computed deterministically for retry safety
- [x] `get_all_writes_ordered()` returns writes in dependency order
- [x] Container is JSON-serializable for checkpoint persistence
- [x] `add_write()` returns bool indicating success (unknown layer = False)

**Blocked By**: 1.1.1 ✅

**Blocks**: 1.1.7, 1.1.8

---

#### Issue 1.1.6 — Implement observability context (P03ObservabilityContext)

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Tracing, timing, and metrics aggregation carrier through envelope

**Spec Reference**: [P03_envelope_fields_discovery.md §19.1](../pipelines/P03_envelope_fields_discovery.md#19-observability-context)

**Implemented Types**:

| Type | Purpose |
|------|---------|
| `P03ObservabilityContext` | Tracing, timing, metrics, error tracking |
| `P03Error` | Error record with factory methods |
| `PIPELINE_ID` | Constant: "P03_CONSOLIDATE" |
| `VALID_PHASES` | frozenset of R0-R8 |

**Inputs Required**:

- [x] Design decision from 1.1.1
- [x] Spec: [P03_envelope_fields_discovery.md §19.1](../pipelines/P03_envelope_fields_discovery.md#191-tracing-and-metrics)

**Deliverables**:

- [x] `P03ObservabilityContext` dataclass → [observability.py](../../k0/pipelines/p03/observability.py)
- [x] `P03Error` dataclass with `create()` and `from_exception()` factories → [observability.py](../../k0/pipelines/p03/observability.py)
- [x] Span management: `push_span()`, `pop_span()`
- [x] Phase timing: `start_phase()`, `end_phase()`, `get_phase_duration_ms()`, `get_all_phase_durations()`, `get_total_duration_ms()`
- [x] Metrics: `increment()`, `record_histogram()`, `get_histogram_stats()`
- [x] Log context: `set_log_context()`, `get_log_context()`
- [x] Error tracking: `add_error()`, `record_error()`, `record_exception()`, `has_errors()`, `has_unrecoverable_errors()`, `get_errors_by_phase()`

**Implementation Notes**:

```python
# Usage example
obs = P03ObservabilityContext.create(log_context={"tenant_id": "t1"})

# Phase timing
obs.start_phase("R1")
# ... R1 processing ...
obs.end_phase("R1")
print(obs.get_phase_duration_ms("R1"))  # e.g., 42

# Metrics
obs.increment("events_processed", 5)
obs.record_histogram("importance_scores", 0.8)
stats = obs.get_histogram_stats("importance_scores")
# {'count': 1, 'sum': 0.8, 'min': 0.8, 'max': 0.8, 'avg': 0.8}

# Log context
ctx = obs.get_log_context("R1", "importance_scorer")
# {'pipeline_id': 'P03_CONSOLIDATE', 'trace_id': '...', 'span_id': '...', 'phase': 'R1', ...}

# Error tracking
obs.record_error("R2", "clustering", "ValidationError", "Invalid dimension")
obs.record_exception("R3", "dedup", exc, recoverable=False)
print(obs.has_unrecoverable_errors())  # True
```

**Acceptance**:

- [x] `get_log_context()` always includes `pipeline_id`, `trace_id`, `span_id`, `phase`, `module_id`
- [x] Phase timing can compute duration: `end_ts - start_ts`
- [x] Error tracking integrated with counters (`errors.{phase}` incremented)
- [x] `to_summary_dict()` for compact logging/metrics

**Blocked By**: 1.1.1 ✅

**Blocks**: 1.1.8

---

#### Issue 1.1.7 — Implement envelope serializer (P03EnvelopeSerializer) + checkpointing

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Serialization for DLQ storage, debugging snapshots, and checkpoint recovery

**Spec Reference**: [P03_envelope_fields_discovery.md §21.2, §24.4](../pipelines/P03_envelope_fields_discovery.md#212-envelope-serialization)

**PhaseCheckpoint Fields** (from discovery §24.4):

| Field | Type | Description |
|-------|------|-------------|
| `phase` | str | Phase at checkpoint |
| `timestamp` | int | Checkpoint creation time (unix ms) |
| `events_count` | int | Number of events in batch |
| `staged_writes_count` | int | Total staged writes |
| `errors_count` | int | Accumulated errors |
| `phase_timings` | Dict[str, int] | Phase duration map |
| `summary` | Dict[str, Any] | Phase-specific summary |

**P03EnvelopeSerializer Methods** (from discovery §21.2):

| Method | Purpose |
|--------|---------|
| `to_dict(envelope)` | Convert to JSON-serializable dict (summary only) |
| `to_full_dict(envelope)` | Full serialization including all events |
| `from_dict(data)` | Deserialize from dict (recovery) |

**to_dict Output Fields**:

```json
{
  "context": {
    "cycle_id", "batch_id", "tenant_id", "space_id",
    "trace_id", "trigger_type", "triggered_at",
    "batch_size", "event_ids"
  },
  "current_phase": "...",
  "phase_timings": {},
  "events_count": 0,
  "staged_writes_count": 0,
  "errors_count": 0
}
```

**Envelope Checkpoint Methods** (from discovery §24.4):

| Method | Purpose |
|--------|---------|
| `checkpoint(summary=None)` | Create checkpoint at current phase |
| `_generate_phase_summary()` | Auto-generate phase-specific summary |
| `get_checkpoint(phase)` | Retrieve checkpoint for specific phase |
| `checkpoints_summary()` | Get all checkpoints as dicts |

**Inputs Required**:

- [x] Design decision from 1.1.1 ✅
- [x] Spec: [P03_envelope_fields_discovery.md §21.2](../pipelines/P03_envelope_fields_discovery.md#212-envelope-serialization) ✅
- [x] Spec: [P03_envelope_fields_discovery.md §24.4](../pipelines/P03_envelope_fields_discovery.md#244-checkpoint-snapshots) ✅
- [x] Types: P03CycleContext (1.1.2), P03EventState (1.1.3), P03PhaseOutputs (1.1.4), P03StagedWrites (1.1.5) ✅

**Deliverables**:

- [x] `PhaseCheckpoint` dataclass → [serializer.py](../../k0/pipelines/p03/serializer.py)
- [x] `P03EnvelopeSerializer` class with `to_dict()`, `to_full_dict()`, `from_dict()` → [serializer.py](../../k0/pipelines/p03/serializer.py)
- [x] `P03Phase` enum with valid transitions
- [x] `generate_phase_summary()` helper function
- [x] Checkpoint methods on P03BatchEnvelope: `checkpoint()`, `get_checkpoint()`, `has_checkpoint()` → [envelope.py](../../k0/pipelines/p03/envelope.py)

**Acceptance**:

- [x] Serialized output is valid JSON
- [x] Checkpoints stored in envelope.checkpoints dict
- [x] Summary generation handles all phases R0-R8

**Blocked By**: 1.1.4 ✅, 1.1.5 ✅, 1.1.6 ✅

**Blocks**: 1.1.8 ✅

---

#### Issue 1.1.8 — Envelope model tests + fixtures

**Status**: ✅ COMPLETED

**Goal**: Ensure envelope invariants are enforced and regressions are caught early

**Spec Reference**: [P03_implementation_plan_skeleton.md Issue 1.1.8](../pipelines/P03_implementation_plan_skeleton.md)

**Test File Location**: `tests/k0/pipelines/p03/test_p03_envelope.py` (created)

**Test Categories** (from plan):

| Category | Test Case | Tests |
|----------|-----------|-------|
| Context Determinism | `batch_id` stable across event ID permutations | 4 tests |
| Context Immutability | `P03CycleContext` frozen after construction | 4 tests |
| Event State Mutability | Enrichment through phases | 5 tests |
| Staged Writes Order | `get_all_writes_ordered()` returns dependency order | 5 tests |
| Serializer Roundtrip | `to_full_dict()` → `from_dict()` → equivalent envelope | 5 tests |
| Lazy Embedding | Default event state has `embedding_id` without materialized vector | 2 tests |
| Phase Output Defaults | All phase outputs have safe defaults (None or empty) | 9 tests |
| Error Collection | Errors accumulate with recoverable/non-recoverable distinction | 5 tests |
| Observability Context | Timing, counters, histograms | 6 tests |
| Phase Transitions | P03Phase enum valid/invalid transitions | 8 tests |
| Generate Phase Summary | Phase summary helper function | 7 tests |
| Phase Checkpoint | Checkpoint dataclass | 3 tests |
| ULID Generation | ULID helper function | 4 tests |
| Edge Cases | Boundary conditions | 5 tests |

**Test Pattern Reference**:

- Style: [test_full_envelope_signature.py](../../tests/k0/gate/test_full_envelope_signature.py)
- Style: [test_envelope_samples.py](../../k0/scripts/test_envelope_samples.py)

**Fixtures Created** (in `tests/k0/pipelines/p03/conftest.py`):

| Fixture | Purpose |
|---------|---------|
| `sample_event_ids()` | List of 5 deterministic ULIDs for batch |
| `sample_tenant_id()` | Deterministic tenant ID |
| `sample_space_id()` | Deterministic space ID |
| `sample_cycle_context()` | Pre-built P03CycleContext |
| `minimal_cycle_context()` | Minimal context with only required fields |
| `sample_event_state()` | Single P03EventState with P02 data |
| `sample_event_states()` | Batch of 5 P03EventState instances |
| `enriched_event_state()` | Event state with R1-R3 enrichment applied |
| `sample_phase_outputs()` | P03PhaseOutputs with sample data per phase |
| `empty_phase_outputs()` | P03PhaseOutputs with defaults |
| `sample_staged_writes()` | P03StagedWrites with sample writes per layer |
| `empty_staged_writes()` | P03StagedWrites with no writes |
| `sample_observability_context()` | P03ObservabilityContext with sample data |
| `observability_with_errors()` | P03ObservabilityContext with errors |
| `fresh_observability_context()` | Clean P03ObservabilityContext |
| `sample_checkpoint()` | Single PhaseCheckpoint |
| `sample_checkpoints()` | List of checkpoints for R0-R3 |

**Inputs Required**:

- [x] All envelope types from 1.1.1–1.1.7 complete
- [x] Spec: [P03_envelope_fields_discovery.md](../pipelines/P03_envelope_fields_discovery.md)

**Deliverables**:

- [x] `tests/k0/pipelines/p03/test_p03_envelope.py` — 72 tests across 14 test classes
- [x] `tests/k0/pipelines/p03/conftest.py` — 17 fixtures
- [x] `tests/k0/pipelines/p03/__init__.py` — package init
- [x] Tests for each category above

**Acceptance**:

- [x] All tests pass in CI (95/95 passing)
- [x] Tests are deterministic (no flaky tests)
- [x] Coverage on envelope module ≥ 80% (achieved: **91.74%**)

**Coverage Details** (Updated 2025-12-31):

| Module | Coverage |
|--------|----------|
| `context.py` | 93% |
| `event_state.py` | 100% |
| `observability.py` | 85% |
| `phase_outputs.py` | 97% |
| `serializer.py` | 88% |
| `staged_writes.py` | 84% |
| `envelope.py` | NEW |
| **TOTAL** | **91.74%** |

**Blocked By**: 1.1.1, 1.1.2, 1.1.3, 1.1.4, 1.1.5, 1.1.6, 1.1.7

**Blocks**: Epic 1.2

---

### Epic 1.2 — Sequential phase runner + checkpoints

**Goal**: Implement P03's strict R0→R8 sequential execution engine with checkpoint/resume capability

**Spec References**:

- [P03_consolidation_dossier_v2.md §4.0 "Phase Transition Rules"](../pipelines/P03_consolidation_dossier_v2.md)
- [P03_consolidation_dossier_v2.md Appendix G](../pipelines/P03_consolidation_dossier_v2.md)
- [P03_envelope_fields_discovery.md §24.4](../pipelines/P03_envelope_fields_discovery.md#244-checkpoint-snapshots)

**Existing Code References**:

- Generic DAG runner (parallel-by-level, contrast): `k0/runtime/pipeline_runner.py`
- Pipeline protocol interface: `k0/pipelines/protocol.py`
- Offset storage: `k0/storage/offsets.py`
- UnitOfWork: `k0/uow/unit_of_work.py`

---

#### Issue 1.2.1 — Confirm sequential-runner contract (vs generic DAG) + map to Appendix G

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Lock the semantics of "sequential R0→R8" execution and document runner contract

**Spec Reference**: [P03_consolidation_dossier_v2.md §4.0, Appendix G](../pipelines/P03_consolidation_dossier_v2.md)

**Decision**: **(A) Dedicated P03Pipeline with internal sequential runner**

**Rationale**:

1. Generic DAG runner uses parallel-by-level execution; P03 needs strict sequential
2. P03 has specific skip transitions (R2→R6, R4→R6) not expressible in DAG model
3. Each phase has INIT/PROC/SKIP/FAIL/DONE states with custom recovery semantics
4. Resume from failed phase requires checkpoint dependency tracking
5. Per-phase idempotency keys need explicit handling

**Phase Order** (from Appendix G):
`R0 → R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8`

**Phase States** (from Appendix G.1):

- `INIT` — Phase not yet started
- `PROC` — Phase in progress
- `SKIP` — Phase skipped (with reason)
- `FAIL` — Phase failed (may be retriable)
- `DONE` — Phase completed successfully

**Skip Transitions Allowed**:

- R2 → R6 (minimal work fast-path, batch_size < 2)
- R4 → R6 / R5 → R6 (skip R5 when backlogged)

**Inputs Required**:

- [x] Dossier: [P03_consolidation_dossier_v2.md §4.0](../pipelines/P03_consolidation_dossier_v2.md)
- [x] Dossier: [P03_consolidation_dossier_v2.md Appendix G.1-G.5](../pipelines/P03_consolidation_dossier_v2.md)
- [x] Existing runner: `k0/runtime/pipeline_runner.py` (contrast study)
- [x] Protocol: `k0/pipelines/protocol.py`

**Deliverables**:

- [x] Runner contract module: `k0/pipelines/p03/runner_contract.py`
  - `P03PhaseId` enum with execution order
  - `P03PhaseStatus` enum (INIT/PROC/SKIP/FAIL/DONE)
  - `NORMAL_TRANSITIONS` and `SKIP_TRANSITIONS` dicts
  - `PhaseContract` dataclass with inputs/outputs/retry/timeout
  - `PHASE_CONTRACTS` dict for all R0-R8
  - `ResumePolicy` dataclass and `RESUME_MATRIX`
  - `ErrorRecovery` dataclass and `ERROR_RECOVERY_MATRIX`
  - `is_valid_transition()` helper function

**Contract Table Summary**:

| Phase | Timeout | Retries | Skip Condition |
|-------|---------|---------|----------------|
| R0 | 30s | 3x | Never |
| R1 | 60s | 3x | Never |
| R2 | 120s | 2x | batch_size < 2 |
| R3 | 60s | 3x | Never |
| R4 | 90s | 3x | Never |
| R5 | 120s | 3x | Backlog threshold |
| R6 | 30s | 3x | Never |
| R7 | 60s | 3x | Never |
| R8 | 30s | 10x | Never |

**Persistence Surfaces**:

- `st_pipeline_status` — Cycle status, current phase
- `st_p03_checkpoints` — Phase snapshots for resume (new table)
- `st_dlq` — Failed cycles after max retries

**Acceptance**:

- [x] Contract table maps each R0-R8 to: inputs/outputs, idempotency key, retry policy, skip condition, checkpoint boundary

**Blocked By**: Epic 1.1 complete ✅

**Blocks**: 1.2.2, 1.2.3

---

#### Issue 1.2.2 — Define the R0–R8 phase interface (typed inputs/outputs + hooks)

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Single testable interface for phases, uniform execution by sequential runner

**Spec Reference**: [P03_consolidation_dossier_v2.md Appendix G.2](../pipelines/P03_consolidation_dossier_v2.md)

**Implementation**: [k0/pipelines/p03/phase_interface.py](../../k0/pipelines/p03/phase_interface.py)

**Types Implemented**:

| Type | Purpose |
|------|---------|
| `P03PhaseResult` | Outcome of phase execution (status, duration, outputs, error) |
| `P03RunnerContext` | Dependencies passed to phases (syscalls, logger, config, QoS) |
| `P03PhaseProtocol` | Protocol defining phase interface (run, should_skip, idempotency_key) |
| `P03PhaseBase` | Abstract base class for phase implementations |
| `P03CycleResult` | Result of full cycle execution (per-phase results, total duration) |

**P03PhaseResult Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `phase_id` | P03PhaseId | Which phase |
| `status` | P03PhaseStatus | Outcome status |
| `outputs_summary` | Dict[str, Any] | Phase-specific output summary |
| `error_info` | Optional[P03Error] | Error details if failed |
| `duration_ms` | int | Phase duration |
| `skip_reason` | Optional[str] | Why skipped (if SKIP) |
| `retry_count` | int | Number of retries attempted |
| `idempotency_key` | Optional[str] | Key for exactly-once semantics |

**P03PhaseResult Factory Methods**:

- `P03PhaseResult.done(phase_id, duration_ms, outputs_summary)` - Success
- `P03PhaseResult.skip(phase_id, reason, duration_ms)` - Skipped
- `P03PhaseResult.fail(phase_id, error, duration_ms, retry_count)` - Failed

**P03Phase Protocol**:

| Method | Signature | Purpose |
|--------|-----------|---------|
| `phase_id` | property → P03PhaseId | Phase identifier |
| `run` | async (envelope, ctx) → P03PhaseResult | Execute phase |
| `should_skip` | (envelope, ctx) → Tuple[bool, str] | Check skip condition |
| `idempotency_key` | (envelope) → str | Deterministic key for retries |

**P03RunnerContext Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `syscalls` | Any | K0 syscall interface |
| `logger` | Any | Structured logger |
| `qos_band` | str | "GREEN", "AMBER", "RED" |
| `priority` | int | Batch priority (0-100) |
| `deadline_ms` | Optional[int] | Hard deadline for completion |
| `config` | Dict[str, Any] | Pipeline configuration |
| `fabric` | Optional[Any] | Agent fabric reference |
| `dry_run` | bool | Skip actual writes (testing) |
| `checkpoint_enabled` | bool | Persist checkpoints at phase boundaries |

**P03PhaseBase Abstract Methods**:

- `phase_id` (property) - Return phase identifier
- `_execute(envelope, ctx)` - Internal phase logic (override this)
- Built-in `run()` wraps `_execute()` with timing, skip check, error handling

**P03CycleResult Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `cycle_id` | str | ULID of the cycle |
| `batch_id` | str | Batch identifier |
| `status` | P03PhaseStatus | Final cycle status |
| `phase_results` | Dict[P03PhaseId, P03PhaseResult] | Per-phase results |
| `total_duration_ms` | int | Total execution time |
| `final_phase` | Optional[P03PhaseId] | Last phase completed/failed |
| `dlq_reason` | Optional[str] | DLQ reason if applicable |

**Inputs Required**:

- [x] Design decision from 1.2.1 ✅
- [x] Spec: [P03_consolidation_dossier_v2.md Appendix G.2](../pipelines/P03_consolidation_dossier_v2.md) ✅
- [x] Envelope types from Epic 1.1 ✅

**Deliverables**:

- [x] `P03PhaseId` enum → Already in runner_contract.py (Issue 1.2.1)
- [x] `P03PhaseStatus` enum → Already in runner_contract.py (Issue 1.2.1)
- [x] `P03PhaseResult` dataclass → phase_interface.py
- [x] `P03PhaseProtocol` protocol with `run()`, `should_skip()`, `idempotency_key()` → phase_interface.py
- [x] `P03PhaseBase` ABC for convenient implementation → phase_interface.py
- [x] `P03RunnerContext` dataclass → phase_interface.py
- [x] `P03CycleResult` dataclass → phase_interface.py

**Acceptance**:

- [x] Interface supports deterministic idempotency keys per phase
- [x] Interface supports skip decision with explicit reason
- [x] Interface enables consistent observability events per phase
- [x] All 95 tests passing

**Blocked By**: 1.2.1 ✅

**Blocks**: 1.2.3

---

#### Issue 1.2.3 — Implement sequential runner core (R0–R8 orchestration)

**Status**: ✅ COMPLETED (2025-12-31)

**Goal**: Engine that runs phases strictly in order, applies transitions/skip rules, records per-phase results

**Spec Reference**: [P03_consolidation_dossier_v2.md §4.0](../pipelines/P03_consolidation_dossier_v2.md)

**P03SequentialRunner Responsibilities**:

1. Take `P03BatchEnvelope` from Epic 1.1
2. Execute phases in order with loop:
   - Mark phase start
   - Evaluate skip policy via `should_skip()`
   - Run phase via `run()`
   - Validate outputs and update envelope
   - Checkpoint boundary (hook)
   - Decide next phase via transition rules
3. Support "resume from phase" entrypoint: `run_from(phase_id=...)`

**Key Constraint**: Do NOT reuse generic DAG runner's parallel grouping semantics for P03

**Inputs Required**:

- [x] Design decision from 1.2.1 ✅
- [x] Phase interface from 1.2.2 ✅
- [x] Envelope model from Epic 1.1 ✅
- [x] Spec: [P03_consolidation_dossier_v2.md §4.0](../pipelines/P03_consolidation_dossier_v2.md) ✅

**Deliverables**:

- [x] `P03SequentialRunner` class → [sequential_runner.py](../../k0/pipelines/p03/sequential_runner.py)
- [x] Main method: `async run(envelope) → P03CycleResult`
- [x] Resume method: `async run_from(envelope, phase_id) → P03CycleResult`
- [x] Transition validation (reject illegal phase jumps)
- [x] Phase timeline recording for metrics (`PhaseTimelineEntry`)
- [x] Callback hooks: `on_phase_start`, `on_phase_complete`, `on_checkpoint`
- [x] Skip transition support: R2→R6, R4→R6, R5→R6

**Implementation Details**:

| Component | Description |
|-----------|-------------|
| `P03SequentialRunner` | Main runner class with phase registration |
| `PhaseTimelineEntry` | Timeline entry for metrics recording |
| `P03RunnerError` | Base exception for runner errors |
| `InvalidPhaseTransitionError` | Raised on illegal transitions |
| `PhaseNotRegisteredError` | Raised when phase implementation missing |
| `ResumeNotAllowedError` | Raised when resume not possible |
| `create_runner()` | Factory function for runner creation |

**Acceptance**:

- [x] Runner enforces legal transitions only
- [x] Runner records phase timeline sufficient for metrics emission
- [x] Resume from phase X does not re-run earlier phases
- [x] Skip transitions properly jump to target phase (R2→R6 skips R3-R5)
- [x] 30 tests passing for sequential runner

**Blocked By**: 1.2.2 ✅

**Blocks**: 1.2.4, 1.2.5

---

#### Issue 1.2.4 — Phase transition bookkeeping + observability events

**Status**: COMPLETE

**Completed**: 2025-01-13

**Goal**: Every phase transition (including skips and aborts) is observable from logs/metrics and envelope state

**Spec Reference**: [P03_consolidation_dossier_v2.md Appendix G.5](../pipelines/P03_consolidation_dossier_v2.md)

**Implementation Summary**:

Added structured phase transition logging to P03 runner:

1. **observability.py** - Added phase transition event types and logger:
   - `PhaseEventType` enum: `PHASE_START`, `PHASE_SKIP`, `PHASE_COMPLETE`, `PHASE_FAIL`
   - `PhaseTransitionEvent` dataclass: Full event with cycle_id, batch_id, space_id, tenant_id, phase_id, status, duration_ms, skip_reason, error_type, etc.
   - `PhaseTransitionLoggerProtocol`: Protocol for logging implementations
   - `PhaseTransitionLogger`: Default implementation that records events and optionally emits to external logger
   - `get_phase_summary()`: Generates summary for audit/outbox

2. **sequential_runner.py** - Integrated logging:
   - Runner accepts optional `transition_logger` parameter
   - `_execute_phase()` emits `phase_start`, `phase_complete`, `phase_skip`, `phase_fail` events
   - Skip transitions emit events for intermediate phases
   - All events include trace_id and span_id for distributed tracing

**Structured Log Events Per Phase**:

| Event | Fields |
|-------|--------|
| `phase_start` | cycle_id, batch_id, space_id, phase_id, status=PROC |
| `phase_skip` | cycle_id, batch_id, space_id, phase_id, status=SKIP, skip_reason |
| `phase_complete` | cycle_id, batch_id, space_id, phase_id, status=DONE, duration_ms |
| `phase_fail` | cycle_id, batch_id, space_id, phase_id, status=FAIL, error_type, retry_count |

**Envelope Observability Updates**:

- Phase statuses stored in `observability.phase_statuses`
- Start/end timestamps in `observability.phase_start_ts`, `observability.phase_end_ts`
- Durations computed from timestamps
- Error summaries in `errors` list

**Files Changed**:

- `k0/pipelines/p03/observability.py`: Added PhaseEventType, PhaseTransitionEvent, PhaseTransitionLoggerProtocol, PhaseTransitionLogger
- `k0/pipelines/p03/sequential_runner.py`: Integrated transition logging into _execute_phase
- `k0/pipelines/p03/__init__.py`: Added new exports

**Tests Added**:

- `tests/k0/pipelines/p03/test_p03_sequential_runner.py`: Added TestPhaseTransitionLogging class (10 tests)

**Test Results**: 135 tests passing (95 envelope + 40 runner)

**Acceptance Criteria Met**:

- [x] Given envelope snapshot, operator can determine: which phase last ran, whether skipped, why
- [x] Structured log events emitted for all phase transitions
- [x] Phase summary suitable for outbox emission (R8) and audit persistence

---

#### Issue 1.2.5 — Define checkpoint + resume contract (envelope snapshot + persistence hooks)

**Status**: COMPLETE

**Goal**: Runner-level checkpointing surface for DB offsets/watermarks and recovery

**Spec Reference**: [P03_consolidation_dossier_v2.md §4.9.2, §6.14](../pipelines/P03_consolidation_dossier_v2.md)

**P03Checkpoint Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `cycle_id` | str | ULID of cycle |
| `batch_id` | str | Batch identifier |
| `phase_id` | P03PhaseId | Phase at checkpoint |
| `phase_status` | P03PhaseStatus | Status at checkpoint |
| `created_at` | int | Checkpoint timestamp |
| `envelope_summary` | Dict | Small envelope summary |
| `envelope_full` | Optional[Dict] | Full snapshot (optional) |
| `last_wal_pos` | Optional[int] | Last processed WAL position |
| `last_event_id` | Optional[str] | Last processed event ID |

**CheckpointStore Interface**:

| Method | Signature | Purpose |
|--------|-----------|---------|
| `save` | (checkpoint) → None | Persist checkpoint |
| `load_latest` | (space_id, ...) → Optional[P03Checkpoint] | Load most recent checkpoint |

**Runner Hooks**:

| Hook | When Called | Purpose |
|------|-------------|---------|
| `on_checkpoint` | At phase boundaries | Persist state for recovery |
| `on_resume` | When resuming from checkpoint | Restore state |

**Offset Representation for P03**:

- `subscriber_id` = pipeline id (e.g., "P03_CONSOLIDATE")
- `topic` = entry topic (e.g., "st_hipp_events")
- `offset` = wal_pos / last processed position

**Inputs Required**:

- [x] Runner core from 1.2.3
- [x] Existing offset storage: `k0/storage/offsets.py`
- [x] Spec: [P03_consolidation_dossier_v2.md §4.9.2](../pipelines/P03_consolidation_dossier_v2.md)

**Deliverables**:

- [x] `P03Checkpoint` dataclass
- [x] `CheckpointStore` protocol/ABC
- [x] Runner hooks: `on_checkpoint()`, `on_resume()` (hooks in runner from 1.2.3)
- [x] Checkpoint contract compatible with K0's existing offset storage patterns

**Implementation Summary**:

Created `k0/pipelines/p03/checkpoint.py` with:

- `P03Checkpoint` dataclass with all required fields plus `space_id`, `tenant_id`, `event_ids`, `errors`, `metadata`
- Properties: `is_terminal`, `is_failed`, `is_resumable`, `resume_phase`
- Methods: `create()`, `from_dict()`, `to_dict()`, `to_summary_dict()`
- `CheckpointStoreProtocol` with `save()`, `load_latest()`, `load_by_cycle()`, `delete()`
- `CheckpointStoreBase` ABC
- `InMemoryCheckpointStore` for testing
- `P03Offset` with `from_checkpoint()` and `to_k0_offset()` for K0 OffsetStore compatibility
- Error classes: `CheckpointError`, `CheckpointSaveError`, `CheckpointLoadError`, `CheckpointNotFoundError`
- Helper: `create_checkpoint_from_envelope()` function
- Constants: `P03_SUBSCRIBER_ID`, `P03_CHECKPOINT_TOPIC`, `P03_SOURCE_TOPIC`

**Tests**: 35 tests in `tests/k0/pipelines/p03/test_p03_checkpoint.py`

**Acceptance**:

- [x] Checkpoint contract is compatible with K0 offset storage (P03Offset.to_k0_offset())
- [x] Checkpoint includes sufficient info for resume from any phase boundary

**Blocked By**: 1.2.3

**Blocks**: 1.2.6

---

#### Issue 1.2.6 — Implement offset/watermark integration path (no-op safe until M2)

**Status**: DONE

**Completed**: 2025-01-XX

**Goal**: Wire runner to offset persistence, safe even before full P03 ingestion is implemented

**Spec Reference**: [P03_consolidation_dossier_v2.md §4.9.2](../pipelines/P03_consolidation_dossier_v2.md)

**Ack Behavior**:

| Scenario | Action |
|----------|--------|
| Cycle completes (R8 DONE) | Persist offset for P03 subscriber |
| Cycle aborts, resumable phase | Persist checkpoint, do NOT advance offset |
| Cycle aborts, non-resumable | Mark DLQ, do NOT advance offset |

**Integration Points**:

- Inside `UnitOfWork` (preferred for atomicity when R7 writes are introduced)
- Outside UoW (read-only phases)

**Inputs Required**:

- [x] Checkpoint contract from 1.2.5
- [x] OffsetStore: `k0/storage/offsets.py`
- [x] UnitOfWork: `k0/uow/unit_of_work.py`

**Deliverables**:

- [x] Offset write logic in runner for cycle completion — `P03OffsetManager.commit_offset()`
- [x] Integration with both UoW and standalone modes — `commit_offset_in_uow()` for atomic, `commit_offset()` for standalone
- [x] Idempotency check for same cycle (safe for retries) — `_committed_cycles` tracking with `is_cycle_committed()`

**Artifacts**:

| File | Purpose |
|------|---------|
| `k0/pipelines/p03/offset_manager.py` | P03OffsetManager, OffsetAction, OffsetDecision, InMemoryOffsetStore |
| `tests/k0/pipelines/p03/test_p03_offset_manager.py` | 43 tests covering decision logic, idempotency, commit modes |

**Key Components**:

- `OffsetAction` enum: COMMIT, CHECKPOINT_ONLY, DLQ, SKIP
- `OffsetDecision` dataclass: action, reason, phase_id, phase_status, offset_value, checkpoint, idempotent
- `P03OffsetManager.decide_action()`: Determines offset action based on cycle result
- `OffsetStoreProtocol`: Compatible with K0's existing OffsetStore interface
- `InMemoryOffsetStore`: Testing implementation

**Acceptance**:

- [x] Offset writes never performed for partial/incomplete cycles — CHECKPOINT_ONLY returned for resumable failures
- [x] Offset updates are idempotent for same cycle — `is_cycle_committed()` prevents duplicate commits

**Tests**: 43 passed (213 total P03 tests)

**Blocked By**: 1.2.5

**Blocks**: 1.2.8

---

#### Issue 1.2.7 — Deterministic cycle seeding + skip rule encoding

**Status**: DONE

**Completed**: 2025-12-31

**Goal**: All randomized/heuristic behavior deterministic per cycle; skip rules are first-class policy checks

**Spec Reference**: [P03_consolidation_dossier_v2.md §4.0, Appendix G.1-G.2](../pipelines/P03_consolidation_dossier_v2.md)

**Deterministic Seed Derivation**:

```python
def derive_cycle_seed(cycle_id: str, batch_id: str) -> int:
    """Derive deterministic seed from cycle identifiers."""
    # cycle_id is ULID, batch_id is SHA256[:16]
    return int(hashlib.sha256(f"{cycle_id}:{batch_id}".encode()).hexdigest()[:16], 16)
```

**Skip Rules as Policy Checks**:

| Phase | Skip Condition | Config Threshold |
|-------|----------------|------------------|
| R5 | `pending_count > r5_skip_threshold` | `r5_skip_threshold` (default: 5000) |
| R2 | `batch_size < minimal_work_threshold` | `minimal_work_threshold` (default: 2) |

**Skip Transitions**:

- R5 skip-on-backlog: R4 → R6 (skip R5)
- Minimal work fast-path: R2 → R6 (skip R3-R5)

**Inputs Required**:

- [x] Runner core from 1.2.3
- [x] Spec: [P03_consolidation_dossier_v2.md §4.0](../pipelines/P03_consolidation_dossier_v2.md)
- [x] Envelope R5Output.skip_reason field from 1.1.4

**Deliverables**:

- [x] `derive_cycle_seed()` function with documentation
- [x] Seeded RNG passed to phases from runner — `P03SeededRNG`, `derive_phase_seed()`
- [x] Skip rule policy functions for R5, R3-R5 — `evaluate_r5_skip()`, `evaluate_minimal_work_skip()`
- [x] Skip decisions recorded in envelope observability — `record_skip_in_envelope()`

**Artifacts**:

| File | Purpose |
|------|---------|
| `k0/pipelines/p03/deterministic.py` | Seed derivation, P03SeededRNG, P03SkipPolicy, SkipDecision, skip rule functions |
| `tests/k0/pipelines/p03/test_p03_deterministic.py` | 71 tests covering seed derivation, RNG determinism, skip rules |

**Key Components**:

- `derive_cycle_seed()`: SHA256-based seed from cycle_id + batch_id
- `derive_phase_seed()`: Phase-isolated seeds for R0-R8
- `P03SeededRNG`: Seeded RNG context with phase isolation
- `P03SkipPolicy`: Skip rule policy manager with caching
- `SkipDecision`: Immutable skip decision with reason tracking
- `SkipPolicyConfig`: Configurable thresholds (r5_backlog_threshold, minimal_work_threshold)
- `P03DeterministicContext`: Combined RNG + skip policy context

**Acceptance**:

- [x] Two runs with same `cycle_id` and inputs produce identical skip decisions — TestDeterministicIntegration::test_skip_decisions_deterministic
- [x] Two runs with same `cycle_id` and inputs produce identical seeded-random choices — TestDeterministicIntegration::test_full_cycle_determinism
- [x] Skip reasons always populated when phase is skipped — SkipDecision.reason_detail always set

**Tests**: 71 passed (284 total P03 tests)

**Blocked By**: 1.2.3

**Blocks**: 1.2.8

---

#### Issue 1.2.8 — Sequential runner tests (transitions, resume, deterministic seeding, skip visibility)

**Status**: DONE

**Goal**: Prove runner semantics match Appendix G and remain stable under refactors

**Spec Reference**: [P03_consolidation_dossier_v2.md Appendix G](../pipelines/P03_consolidation_dossier_v2.md)

**Test File Location**: `tests/k0/pipelines/test_p03_runner.py` (new file)

**Test Categories**:

| Category | Test Cases |
|----------|------------|
| Legal Transitions | R0→R1→...→R8 passes; illegal jumps rejected |
| Skip Transitions | R2→R6 fast-path works; R4→R6 (skip R5) works |
| Skip Behavior | R5 skipped emits status=SKIP with skip_reason |
| Deterministic Seeding | Same cycle_id yields same RNG output sequence |
| Checkpoint Hooks | `on_checkpoint` called at each phase boundary |
| Resume | Given checkpoint at phase X, runner starts at X, does not re-run earlier |
| Observability | Phase events logged with correct fields |

**Test Pattern**:

- Use small stub phases (not real R1-R8 implementations)
- Avoid mocking storage except at boundary
- Tests must be deterministic

**Inputs Required**:

- [x] All runner components from 1.2.1-1.2.7
- [x] Stub phase implementations for testing
- [x] Spec: [P03_consolidation_dossier_v2.md Appendix G](../pipelines/P03_consolidation_dossier_v2.md)

**Deliverables**:

- [x] `tests/k0/pipelines/test_p03_runner.py` (40 tests across 7 test classes)
- [x] TrackingStubPhase implementation with execution tracking
- [x] Tests for all 7 categories

**Implementation Summary**:

- Created `tests/k0/pipelines/test_p03_runner.py` with 40 integration tests
- Test classes: TestLegalTransitions, TestSkipTransitions, TestSkipBehavior, TestDeterministicSeeding, TestCheckpointHooks, TestResume, TestObservability, TestRunnerIntegration
- TrackingStubPhase with configurable skip/fail behavior and RNG capture
- Fixed bug in `checkpoint.py` (envelope.event_states → envelope.events, staged_writes → staged)
- All 324 P03 tests pass

**Acceptance**:

- [x] All tests pass in CI (324 P03 tests pass)
- [x] Tests are deterministic
- [x] No real DB/network services required

**Blocked By**: 1.2.1, 1.2.2, 1.2.3, 1.2.4, 1.2.5, 1.2.6, 1.2.7

**Blocks**: Epic 1.3

---

### Epic 1.3 — Scheduler + concurrency guard

**Goal**: Implement P03 trigger configuration, overlap policy, single-writer-per-space lock, and QoS integration

**Spec References**:

- [P03_consolidation_dossier_v2.md Appendix D.5](../pipelines/P03_consolidation_dossier_v2.md)
- [P03_consolidation_dossier_v2.md §4.10.2, §4.10.6](../pipelines/P03_consolidation_dossier_v2.md)
- [P03_consolidation_dossier_v2.md §15.1-15.2](../pipelines/P03_consolidation_dossier_v2.md)

**Existing Code References**:

- Trigger schema: `k0/runtime/schemas.py` (`TriggerType`, `TriggerSpec`)
- Trigger engine factory: `k0/scheduler/triggers.py`
- Scheduler: `k0/scheduler/scheduler.py`
- Concurrency gate: `k0/scheduler/concurrency.py`
- QoS scheduler: `k0/qos/scheduler.py`
- QoS context: `k0/qos/context.py`

---

#### Issue 1.3.1 — Implement P03 trigger specs (INTERVAL/THRESHOLD/MANUAL)

**Status**: DONE

**Goal**: Configure P03's declarative triggers as specified in dossier Appendix D.5, using K0 trigger schema

**Spec Reference**: [P03_consolidation_dossier_v2.md Appendix D.5.1](../pipelines/P03_consolidation_dossier_v2.md)

**Trigger Types Required**:

| Trigger | Type | Purpose |
|---------|------|---------|
| INTERVAL | `interval` | Periodic consolidation (90 min cycle) |
| THRESHOLD | `threshold` | Fire when `st_hipp_events` pending count exceeds 500 |
| MANUAL | `manual` | Admin/debug on-demand runs |

**YAML Fields** (must match `TriggerSpec`):

```yaml
triggers:
  - id: p03_interval_90m
    type: interval
    interval_seconds: 5400  # 90 minutes
    catch_up_enabled: true

  - id: p03_threshold_500
    type: threshold
    table: st_hipp_events
    condition: "consolidation_status = 'PENDING'"
    threshold_count: 500
    check_interval_seconds: 60

  - id: p03_manual
    type: manual
```

**Inputs Required**:

- [x] P03 pipeline contract YAML from M0 (Epic 0.2.5)
- [x] K0 trigger schema: `k0/runtime/schemas.py`
- [x] Spec: [P03_consolidation_dossier_v2.md Appendix D.5.1](../pipelines/P03_consolidation_dossier_v2.md)

**Deliverables**:

- [x] P03 pipeline YAML with all three trigger types — `k0/contracts/pipelines/p03_consolidation.v1.yaml`
- [x] Validation that YAML passes `TriggerSpec` schema — 31 tests in `test_p03_triggers.py`
- [x] Test that `PipelineScheduler.register_pipeline()` creates all trigger engines

**Acceptance**:

- [x] P03 pipeline YAML validates under `k0/runtime/schemas.py::TriggerSpec`
- [x] `PipelineScheduler.register_pipeline(...)` creates all trigger engines without error

**Files Changed**:

- `k0/contracts/pipelines/p03_consolidation.v1.yaml` — Fixed trigger specs (lowercase types, added IDs, corrected field names)
- `tests/k0/pipelines/p03/test_p03_triggers.py` — 31 new tests for trigger validation

**Test Results**: 315 P03 tests passing (including 31 new trigger tests)

**Blocked By**: M0 complete (pipeline YAML exists) ✅

**Blocks**: 1.3.2, 1.3.3

---

#### Issue 1.3.2 — Extend manual triggering to carry P03 options

**Status**: DONE

**Goal**: Support dossier's manual trigger API semantics by propagating payload into pipeline execution

**Spec Reference**: [P03_consolidation_dossier_v2.md Appendix D.5.3](../pipelines/P03_consolidation_dossier_v2.md)

**Manual Trigger Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `reason` | str | Human-readable reason for manual trigger |
| `options.skip_r5` | bool | Skip R5 dream exploration phase |
| `options.max_events` | int | Override batch size limit |
| `options.space_id` | Optional[str] | Target specific space (debug mode) |
| `options.tenant_id` | Optional[str] | Target specific tenant (debug mode) |

**Integration Point**: `TriggerEvent.context` (already supported)

**Inputs Required**:

- [x] Trigger specs from 1.3.1
- [x] `TriggerEvent.context` in `k0/scheduler/triggers.py`
- [x] Spec: [P03_consolidation_dossier_v2.md Appendix D.5.3](../pipelines/P03_consolidation_dossier_v2.md)

**Deliverables**:

- [x] Update `PipelineScheduler.fire_manual_trigger(...)` to accept payload — context param added
- [x] Payload passed to `ManualTriggerEngine.fire()` as context — context param added
- [x] `P03ManualTriggerOptions` dataclass for type-safe option parsing

**Acceptance**:

- [x] Manual trigger produces `TriggerEvent` with payload in `context`
- [x] P03 can read context in R0 to apply options deterministically via `P03ManualTriggerOptions.from_trigger_context()`

**Files Changed**:

- `k0/scheduler/triggers.py` — Added `context` param to `ManualTriggerEngine.fire()`
- `k0/scheduler/scheduler.py` — Added `context` param to `PipelineScheduler.fire_manual_trigger()`
- `k0/pipelines/p03/context.py` — Added `P03ManualTriggerOptions` dataclass
- `tests/k0/pipelines/p03/test_p03_triggers.py` — Added 11 new tests for context propagation

**Test Results**: 326 P03 tests passing (11 new context propagation tests)

**Blocked By**: 1.3.1 ✅

**Blocks**: 1.3.5

---

#### Issue 1.3.3 — Validate overlap policy (single-flight) matches trigger semantics

**Status**: DONE

**Goal**: Ensure scheduler-level overlap behavior is deterministic and matches operational intent

**Spec Reference**: [P03_consolidation_dossier_v2.md §4.10](../pipelines/P03_consolidation_dossier_v2.md)

**Overlap Policy by Trigger Type**:

| Trigger | Policy | Behavior |
|---------|--------|----------|
| INTERVAL | SKIP | Skip overlapping runs |
| THRESHOLD | QUEUE (depth 1) | Queue at most one pending run (coalesced) |
| MANUAL | QUEUE (depth 1) | Queue at most one pending run (coalesced) |

**Inputs Required**:

- [x] Trigger specs from 1.3.1
- [x] `SingleFlightGate` in `k0/scheduler/concurrency.py`
- [x] Spec: [P03_consolidation_dossier_v2.md §4.10](../pipelines/P03_consolidation_dossier_v2.md)

**Deliverables**:

- [x] Confirm P03 uses `SingleFlightGate` behavior as-is — Verified, implementation matches dossier
- [x] Tests for overlap policy mapping by trigger type — 5 tests in `TestP03OverlapPolicyMapping`
- [x] Tests for queue depth behavior (coalescing) for repeated threshold fires — 7 tests in `TestP03OverlapPolicy`

**Acceptance**:

- [x] Repeated THRESHOLD/MANUAL fires during in-flight run result in at most one queued run
- [x] INTERVAL fires during in-flight run are skipped (not queued)

**Verified Behavior**:

| Scenario | Expected | Verified |
|----------|----------|----------|
| INTERVAL during running INTERVAL | SKIP | ✅ |
| THRESHOLD during running THRESHOLD | QUEUE (depth 1) | ✅ |
| MANUAL during running MANUAL | QUEUE (depth 1) | ✅ |
| INTERVAL during running THRESHOLD | SKIP | ✅ |
| THRESHOLD during running INTERVAL | QUEUE (depth 1) | ✅ |
| Multiple THRESHOLDs coalesce | Single pending run | ✅ |

**Files Changed**:

- `tests/k0/pipelines/p03/test_p03_triggers.py` — Added 12 new overlap policy tests

**Test Results**: 338 P03 tests passing (12 new overlap policy tests)

**Blocked By**: 1.3.1 ✅

**Blocks**: 1.3.4

---

#### Issue 1.3.4 — Implement single-writer-per-space guard using PostgreSQL advisory locks

**Status**: DONE

**Goal**: Enforce dossier requirement that consolidation cycles must not overlap within same (tenant_id, space_id)

**Spec Reference**: [P03_consolidation_dossier_v2.md §4.10.2, §4.10.6](../pipelines/P03_consolidation_dossier_v2.md)

**Lock Key Pattern**:

```text
{pipeline_id}:{tenant_id}:{space_id}
```

**Lock Strategy**:

- Non-blocking `pg_try_advisory_lock(...)` or bounded-wait variant
- Explicit behavior when lock cannot be acquired (defer/skip per policy)
- Best-effort cleanup on exceptions

**Lock Lifecycle**:

| Stage | Action |
|-------|--------|
| R0 Start | Acquire advisory lock |
| R8 Complete | Release lock |
| Any Abort | Release lock (finally block) |

**Inputs Required**:

- [x] Overlap policy from 1.3.3
- [x] Existing scheduler gating: `k0/scheduler/concurrency.py`
- [x] Spec: [P03_consolidation_dossier_v2.md §4.10.2](../pipelines/P03_consolidation_dossier_v2.md)

**Deliverables**:

- [x] Postgres advisory lock helper (as syscall or DB helper) — `k0/db/advisory_lock.py`
- [x] Lock acquisition at R0, release on completion/abort — via syscalls `lock_acquire`, `lock_release`
- [x] Structured log + metric counter for lock acquisition/failure — INFO/DEBUG logs with extras

**Implementation Details**:

| Component | File | Description |
|-----------|------|-------------|
| `AdvisoryLockService` | `k0/db/advisory_lock.py` | PostgreSQL advisory lock service |
| `hash_lock_key()` | `k0/db/advisory_lock.py` | SHA256→bigint for pg_advisory_lock |
| `make_p03_lock_key()` | `k0/db/advisory_lock.py` | Creates `P03:{tenant}:{space}` keys |
| `lock_acquire` syscall | `k0/kernel/syscalls.py` | Requires `advisory_lock.acquire` cap |
| `lock_release` syscall | `k0/kernel/syscalls.py` | Requires `advisory_lock.release` cap |
| `lock_is_held` syscall | `k0/kernel/syscalls.py` | Requires `advisory_lock.read` cap |

**Acceptance**:

- [x] Two workers attempting P03 for same space concurrently: one proceeds, other defers/skips
- [x] Lock acquisition/failure is observable (structured logging with lock_key, holder_id, acquired)

**Files Changed**:

- `k0/db/advisory_lock.py` — New file (AdvisoryLockService implementation)
- `k0/db/__init__.py` — Already exports advisory lock symbols
- `k0/kernel/syscalls.py` — Already has lock_acquire/lock_release/lock_is_held syscalls
- `docs/pipelines/P03_consolidation_dossier_v2.md` — Updated §4.10.2 to reflect implementation

**Tests Added**:

- `tests/k0/db/test_advisory_lock.py` — 29 unit tests for advisory lock service

**Blocked By**: 1.3.3 ✅

**Blocks**: 1.3.6

---

#### Issue 1.3.5 — Define batch selection/backpressure inputs and plumb trigger context into R0

**Status**: DONE

**Goal**: Make batch selection (R0) explicitly parameterized by trigger and resource context

**Spec Reference**: [P03_consolidation_dossier_v2.md Appendix D.5.1](../pipelines/P03_consolidation_dossier_v2.md)

**Trigger-Derived Inputs for R0**:

| Input | Source | Description |
|-------|--------|-------------|
| `trigger_type` | TriggerEvent | INTERVAL/THRESHOLD/MANUAL |
| `trigger_reason` | TriggerEvent | Human-readable reason |
| `max_events` | Manual context | Override batch size limit |
| `threshold_count` | Threshold context | Pending count that triggered |
| `batch_size` | TriggerSpec | Default batch size from config |
| `deadline_ms` | QoS context | Cycle deadline |
| `qos_band` | QoS context | QoS band (GREEN/AMBER/RED) |

**Backpressure Policy for R0**:

| Scenario | Action |
|----------|--------|
| Backlog large, capacity available | SELECT_FULL |
| Backlog large, capacity limited | SELECT_REDUCED |
| No capacity / QoS fail | DEFER |

**Inputs Required**:

- [x] Manual trigger context from 1.3.2
- [x] TriggerEvent: `k0/scheduler/triggers.py`
- [x] TriggerSpec: `k0/runtime/schemas.py`
- [x] Spec: [P03_consolidation_dossier_v2.md Appendix D.5.1](../pipelines/P03_consolidation_dossier_v2.md)

**Deliverables**:

- [x] Document trigger-derived inputs that R0 consumes — `R0TriggerInputs` dataclass
- [x] Backpressure policy implemented — `BackpressureAction` + `evaluate_backpressure()`
- [x] Inputs arrive at P03 runner as part of cycle context/envelope — via `R0TriggerInputs.from_trigger_event()`

**Implementation Details**:

| Component | File | Description |
|-----------|------|-------------|
| `R0TriggerInputs` | `k0/pipelines/p03/context.py` | Frozen dataclass with all trigger-derived inputs |
| `BackpressureAction` | `k0/pipelines/p03/context.py` | Enum: SELECT_FULL, SELECT_REDUCED, DEFER |
| `from_trigger_event()` | `k0/pipelines/p03/context.py` | Factory to create from TriggerEvent data |
| `evaluate_backpressure()` | `k0/pipelines/p03/context.py` | Returns backpressure action |
| `get_effective_batch_size()` | `k0/pipelines/p03/context.py` | Computes min(max_events, batch_size) |

**Acceptance**:

- [x] R0 selection is deterministic for same inputs — frozen dataclass ensures immutability
- [x] R0 never exceeds configured `max_events` / effective batch size — `get_effective_batch_size()` enforces

**Files Changed**:

- `k0/pipelines/p03/context.py` — Added `R0TriggerInputs`, `BackpressureAction`

**Tests Added**:

- `tests/k0/pipelines/p03/test_p03_triggers.py` — 16 new tests:
  - `TestR0TriggerInputs` (7 tests)
  - `TestR0TriggerInputsBackpressure` (4 tests)
  - `TestR0TriggerInputsFilters` (4 tests)
  - `TestR0TriggerInputsSerialization` (1 test)

**Test Results**: 354 P03 tests passing (16 new)

**Blocked By**: 1.3.2 ✅

**Blocks**: 1.3.6

---

#### Issue 1.3.6 — Integrate QoS token acquisition + budget enforcement into cycle start/end

**Status**: DONE

**Goal**: Apply dossier's QoS-aware consolidation by acquiring scheduler capacity and enforcing budgets

**Spec Reference**: [P03_consolidation_dossier_v2.md §15.1-15.2](../pipelines/P03_consolidation_dossier_v2.md)

**QoS Token Lifecycle**:

| Stage | Action |
|-------|--------|
| R0 Start | `QoSContext.acquire(band, port, cost)` |
| Any Exit | `token.release()` (try/finally) |

**Initial Cost Model**:

```python
cost = f(batch_size)  # For port="command" acquisitions
```

**Budget Enforcement**:

- `fanout_budget` at phase boundaries
- `top_k_budget` at phase boundaries
- `QoSContext.consume_*` calls

**Error Handling**:

| Error | Action |
|-------|--------|
| `SchedulerCapacityError` | Defer / reschedule / smaller batch |
| `QoSBudgetError` | Stop or reduce work per policy |

**Inputs Required**:

- [x] Advisory lock from 1.3.4
- [x] Batch selection from 1.3.5
- [x] QoS scheduler: `k0/qos/scheduler.py`
- [x] QoS context: `k0/qos/context.py`
- [x] Spec: [P03_consolidation_dossier_v2.md §15.1-15.2](../pipelines/P03_consolidation_dossier_v2.md)

**Deliverables**:

- [x] Token acquisition at cycle start (R0) — `P03QoSIntegration.acquire_batch_token()`
- [x] Token release in all exit paths (try/finally) — `P03QoSIntegration.release_token()` + context manager
- [x] Budget enforcement at applicable phase boundaries — `consume_fanout()`, `consume_top_k()`
- [x] Error handling for capacity/budget exhaustion — `P03CapacityError`, `P03BudgetExhaustedError`

**Implementation Summary**:

Created `P03QoSIntegration` class in `k0/pipelines/p03/context.py`:

- `acquire_batch_token(batch_size, band, cost_multiplier)` — Acquires scheduler token with calculated cost
- `release_token(token)` — Releases token (safe to call multiple times)
- `consume_fanout(amount)` / `consume_top_k(amount)` — Budget consumption with error on exhaustion
- `check_fanout_budget()` / `check_top_k_budget()` — Budget availability checks
- `tighten_budgets()` — Reduce budgets (cannot increase)
- `evaluate_capacity_action()` — Returns BackpressureAction based on QoS state
- Context manager protocol for automatic token release

Created `P03QoSSnapshot` frozen dataclass for observability snapshots.

Created exception hierarchy:

- `P03QoSError` — Base exception
- `P03CapacityError` — Raised when scheduler capacity exhausted
- `P03BudgetExhaustedError` — Raised when fanout/top_k budgets exhausted

**Test File**: `tests/k0/pipelines/p03/test_p03_qos_integration.py` (45 tests)

**Acceptance**:

- [x] QoS token is always released (no leaked capacity) even when phases fail
- [x] Capacity/budget exhaustion paths are test-covered and observable

**Blocked By**: 1.3.4, 1.3.5

**Blocks**: M1 complete

---

## Part E — M1 Summary

**Epic 1.1** (Envelope Model): 8 issues (1.1.1-1.1.8)

- Core data structures for P03 batch processing
- P03CycleContext, P03EventState, P03PhaseOutputs, P03StagedWrites, P03ObservabilityContext
- Serialization for checkpointing/recovery
- Tests and fixtures

**Epic 1.2** (Sequential Runner): 8 issues (1.2.1-1.2.8)

- P03 strict R0→R8 sequential execution engine
- Phase interface and runner core
- Checkpoint/resume capability
- Offset/watermark integration
- Deterministic seeding and skip rules
- Tests

**Epic 1.3** (Scheduler + Concurrency): 6 issues (1.3.1-1.3.6)

- Trigger configuration (INTERVAL/THRESHOLD/MANUAL)
- Overlap policy validation
- Single-writer-per-space advisory lock
- Batch selection and backpressure
- QoS token acquisition and budget enforcement

**Total Issues**: 22

---

## Part F — Governance Checklist (PER-EPIC VERIFICATION)

### F.1 Epic 1.1 Governance

**Run AFTER completing Epic 1.1**:

```powershell
python -m governance.k0.scripts.sync --report
```

**Expected Updates** (if any code creates new registerable items):

| Registry Part | What To Add | Issue |
|---------------|-------------|-------|
| Part 3.1 (Module Registry) | P03 envelope module if registered | 1.1.1 |
| (None expected) | Epic 1.1 is internal envelope code | - |

**Verification**: [ ] SYNCED / [ ] DRIFT DETECTED (explain)

---

### F.2 Epic 1.2 Governance

**Run AFTER completing Epic 1.2**:

```powershell
python -m governance.k0.scripts.sync --report
```

**Expected Updates**:

| Registry Part | What To Add | Issue |
|---------------|-------------|-------|
| Part 3.1 (Module Registry) | P03 runner module if registered | 1.2.1 |
| (None expected) | Epic 1.2 is internal runner code | - |

**Verification**: [ ] SYNCED / [ ] DRIFT DETECTED (explain)

---

### F.3 Epic 1.3 Governance

**Run AFTER completing Epic 1.3**:

```powershell
python -m governance.k0.scripts.sync --report
```

**Expected Updates**:

| Registry Part | What To Add | Issue |
|---------------|-------------|-------|
| Part 9 (Scheduler) | P03 trigger registrations (already in M0) | 1.3.1 |
| Part 5.2 (Syscall Matrix) | Advisory lock syscall if new | 1.3.4 |

**Verification**: [ ] SYNCED / [ ] DRIFT DETECTED (explain)

---

### F.4 M1 Final Governance Verification

**Run BEFORE marking M1 complete**:

```powershell
python -m governance.k0.scripts.sync --report
```

**Status**: [ ] OVERALL SYNCED

**If DRIFT DETECTED, resolve by**:

1. Add missing items to `governance/k0/k0_architecture_master.md`
2. Re-run sync until SYNCED
3. Document resolution in this section

**Final Sync Output**:

```
(Paste sync output here when M1 complete)
```

---

## Part G — M1 Completion Criteria

- [ ] All 22 issues completed
- [ ] All tests pass in CI
- [ ] Part F governance sync shows OVERALL SYNCED
- [ ] M1_EXECUTION.md updated with completion status
- [ ] Part G checklist all checked

---

*Document created: 2025-12-31*
*Last updated: 2025-12-31*
