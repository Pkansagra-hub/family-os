# P03 Milestone 0 Execution Document

> **Milestone**: M0 — Governance + Decisions + Contract Baseline
> **Status**: ✅ COMPLETE (Contracts done, registry sync pending)
> **Started**: 2025-12-31
> **Completed**: 2025-12-31
> **Prerequisites**: None (this is the first milestone)
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: `3ce195badedd983aaf2d1f35129f0d15ec45a96c`

---

## Part A: Context Foundation (BEFORE YOU START)

### A.1 Dossier Sections Governing This Milestone

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| Appendix D | Pipeline Architecture | [Dossier Appendix D](../pipelines/P03_consolidation_dossier_v2.md#appendix-d-pipeline-architecture) | Pipeline ID, stages, DAG shape |
| Appendix D.2.2 | Required Capabilities | [Dossier Appendix D.2.2](../pipelines/P03_consolidation_dossier_v2.md#d22-required-capabilities) | Capability list for contracts |
| Appendix D.3 | Stage Mapping | [Dossier Appendix D.3](../pipelines/P03_consolidation_dossier_v2.md#d3-stage-mapping) | R0-R8 phase definitions |
| Appendix D.5 | Scheduler Triggers | [Dossier Appendix D.5](../pipelines/P03_consolidation_dossier_v2.md#d5-scheduler-triggers) | INTERVAL/THRESHOLD/MANUAL triggers |
| Appendix D.8.3 | Fabric Invocation Policy | [Dossier Appendix D.8.3](../pipelines/P03_consolidation_dossier_v2.md#d83-fabric-invocation-policy) | INTERSECT_CALLER policy |
| Appendix D.9 | Observability | [Dossier Appendix D.9](../pipelines/P03_consolidation_dossier_v2.md#d9-observability) | Metrics names |
| Appendix D.10 | Failure Modes | [Dossier Appendix D.10](../pipelines/P03_consolidation_dossier_v2.md#d10-failure-modes) | Retry policies |
| Appendix E | Canonical Naming | [Dossier Appendix E](../pipelines/P03_consolidation_dossier_v2.md#appendix-e-canonical-naming) | Topic names, table names |
| Appendix E.2 | Entry/Exit Topics | [Dossier Appendix E.2](../pipelines/P03_consolidation_dossier_v2.md#e2-entryexit-topics) | Bus topics |
| Appendix E.5 | Capability Names | [Dossier Appendix E.5](../pipelines/P03_consolidation_dossier_v2.md#e5-capability-names) | Fabric capabilities |
| Appendix E.7 | Config Keys | [Dossier Appendix E.7](../pipelines/P03_consolidation_dossier_v2.md#e7-config-keys) | p03.* configuration |
| Appendix F | Threshold Validation | [Dossier Appendix F](../pipelines/P03_consolidation_dossier_v2.md#appendix-f-threshold-validation) | Config schema rules |
| Appendix G | State Machine | [Dossier Appendix G](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-state-machine) | R0-R8 states, idempotency keys |
| Appendix G.5 | Phase Metrics | [Dossier Appendix G.5](../pipelines/P03_consolidation_dossier_v2.md#g5-phase-metrics) | Per-phase metric names |
| Appendix I | RLS Posture | [Dossier Appendix I](../pipelines/P03_consolidation_dossier_v2.md#appendix-i-rls-posture) | Row-level security for learning tables |
| §6.x | Storage Tables | [Dossier Section 6](../pipelines/P03_consolidation_dossier_v2.md#6-storage-schema) | All st_* table names |

### A.2 Additional Source Documents

| Document | Path | What It Provides |
|----------|------|------------------|
| P03 Dossier V2 | [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md) | Master spec for P03 |
| P03 Dossier Notes | [P03_consolidation_dossier_v2_notes.md](../pipelines/P03_consolidation_dossier_v2_notes.md) | Implementation notes, clarifications |
| P03 Envelope Discovery | [P03_envelope_fields_discovery.md](../pipelines/P03_envelope_fields_discovery.md) | Envelope field specs (M1 prep) |
| Implementation Plan | [P03_implementation_plan_skeleton.md](../pipelines/P03_implementation_plan_skeleton.md) | Issue definitions for M0 |

### A.3 Governance Registry (MUST UPDATE)

| Registry | Path | Parts Affected by M0 |
|----------|------|----------------------|
| K0 Architecture Master | [governance/k0/k0_architecture_master.md](../../governance/k0/k0_architecture_master.md) | Part 2 (Pipelines), Part 4 (Events), Part 5 (Contracts), Part 6 (Storage), Part 7 (Syscalls), Part 9 (Scheduler), Part 10 (Observability), Part 11 (ADRs), Part 13 (Config) |
| Pipeline Whiteboard | [k0/pipelines/whiteboard.md](../../k0/pipelines/whiteboard.md) | Event bus namespace tables |

### A.4 Existing ADRs to Reference

| ADR | Path | What It Governs |
|-----|------|-----------------|
| K000 Template | [decisions-K0/k000-template.md](../architecture/decisions-K0/k000-template.md) | ADR format to follow |
| K001 Write Pipeline V1 | [decisions-K0/k001-write-pipeline-v1-hardening.md](../architecture/decisions-K0/k001-write-pipeline-v1-hardening.md) | Hardening patterns |
| K002 Idempotency TOCTOU | [decisions-K0/k002-idempotency-toctou-race-fix.md](../architecture/decisions-K0/k002-idempotency-toctou-race-fix.md) | Idempotency patterns |
| K003 Inline Embedding | [decisions-K0/k003-inline-embedding-ultrabert.md](../architecture/decisions-K0/k003-inline-embedding-ultrabert.md) | Embedding patterns |
| K004 Capability Mesh | [decisions-K0/k004-capability-mesh-architecture.md](../architecture/decisions-K0/k004-capability-mesh-architecture.md) | Capability model (MUST REFERENCE for Issue 0.2.3) |
| K020 Feedback Signals | [decisions-K0/k020-feedback-signals-subsystem.md](../architecture/decisions-K0/k020-feedback-signals-subsystem.md) | Feedback ingestion (MUST REFERENCE for Issue 0.2.4) |
| P02 Pipeline Architecture | [decisions-K0/pipelines/P02-write-pipeline-architecture.md](../architecture/decisions-K0/pipelines/P02-write-pipeline-architecture.md) | ADR format for pipeline ADRs |
| P08 Embedding Architecture | [decisions-K0/pipelines/P08-embedding-management-architecture.md](../architecture/decisions-K0/pipelines/P08-embedding-management-architecture.md) | Integration point for P03→P08 |

### A.5 Existing Contracts to Reference (PATTERNS TO COPY)

| Contract Type | Path | What Pattern to Copy |
|---------------|------|----------------------|
| Pipeline Contract | [k0/contracts/pipelines/p02_write.v1.yaml](../../k0/contracts/pipelines/p02_write.v1.yaml) | YAML structure, fields, DAG format |
| Pipeline Contract | [k0/contracts/pipelines/p08_embedding_management.v2.yaml](../../k0/contracts/pipelines/p08_embedding_management.v2.yaml) | Alternative pipeline YAML example |
| Module Contract | [k0/contracts/modules/affect.analyze.v1.yaml](../../k0/contracts/modules/affect.analyze.v1.yaml) | Module YAML structure |
| Module Contract | [k0/contracts/modules/hippocampus.pattern_separate.v1.yaml](../../k0/contracts/modules/hippocampus.pattern_separate.v1.yaml) | Hippocampus module pattern |
| Capability Contract | [k0/contracts/capabilities/core.v1.yaml](../../k0/contracts/capabilities/core.v1.yaml) | Capability definition format |
| Event Schema | [k0/contracts/schemas/cognitive_embedding_backfilled.json](../../k0/contracts/schemas/cognitive_embedding_backfilled.json) | JSON schema format for events |
| JSON Schema | [k0/contracts/jsonschema/envelope.schema.json](../../k0/contracts/jsonschema/envelope.schema.json) | JSON schema format for config |

### A.6 Governance Sync Tool

| Tool | Path | Command |
|------|------|---------|
| Sync Script | [governance/k0/scripts/sync.py](../../governance/k0/scripts/sync.py) | `python -m governance.k0.scripts.sync --report` |
| Event Scanner | [governance/k0/scripts/event_scanner.py](../../governance/k0/scripts/event_scanner.py) | Validates event topics |
| Contract Scanner | [governance/k0/scripts/contract_scanner.py](../../governance/k0/scripts/contract_scanner.py) | Validates contract files |
| ADR Scanner | [governance/k0/scripts/adr_scanner.py](../../governance/k0/scripts/adr_scanner.py) | Validates ADR index |

### A.7 Existing Directory Structure (WHERE TO CREATE FILES)

| Purpose | Path | Exists |
|---------|------|--------|
| Pipeline ADRs | [docs/architecture/decisions-K0/pipelines/](../architecture/decisions-K0/pipelines/) | ✅ Yes |
| Pipeline Contracts | [k0/contracts/pipelines/](../../k0/contracts/pipelines/) | ✅ Yes |
| Module Contracts | [k0/contracts/modules/](../../k0/contracts/modules/) | ✅ Yes |
| Capability Contracts | [k0/contracts/capabilities/](../../k0/contracts/capabilities/) | ✅ Yes |
| Event Schemas | [k0/contracts/schemas/](../../k0/contracts/schemas/) | ✅ Yes |
| JSON Schemas | [k0/contracts/jsonschema/](../../k0/contracts/jsonschema/) | ✅ Yes |
| Config Examples | [k0/contracts/jsonschema/examples/](../../k0/contracts/jsonschema/examples/) | ✅ Yes |

---

## Part B: Repository Patterns (HOW WE DO THINGS HERE)

### B.1 Pipeline Contract YAML Pattern

Source: [k0/contracts/pipelines/p02_write.v1.yaml](../../k0/contracts/pipelines/p02_write.v1.yaml) Lines 1-50

```yaml
# P03 Consolidation Pipeline: Memory Truth Formation
# Purpose: Transform st_hipp_events → truth layer tables (st_epi, st_sem, st_kg_*, etc.)
# Owner: Intelligence Kernel (K0)
# Status: PLANNING
# ADRs: P03-consolidation-architecture (TBD)

pipeline_id: P03_CONSOLIDATION
version: v1
name: P03 Consolidation - Memory Truth Formation
description: |
  Consolidates hippocampal events into truth-layer memory structures.
  Implements R0-R8 phases: batch selection, importance scoring, episodic clustering,
  duplicate detection, KG consolidation, dream phase, staging, truth writing, event emission.

entry_topic: p03.consolidation.triggered.v1
exit_topic: p03.consolidation.complete.v1
concurrency: 1
max_queue_depth: 64

required_capabilities:
  - st_hipp_events.read
  - st_hipp_events.write
  - st_epi.write
  - st_sem.write
  # ... (fill from Appendix D.2.2)

dag:
  - id: stage_r0_batch_selection
    module: consolidation.batch_selector:v1
    after: []
    description: R0 - Batch selection and context hydration
    config:
      max_batch_size: 100
```

### B.2 Module Contract YAML Pattern

Source: [k0/contracts/modules/affect.analyze.v1.yaml](../../k0/contracts/modules/affect.analyze.v1.yaml) Lines 1-30

```yaml
module_id: consolidation.importance_scorer
version: v1

input_event_types:
  - p03.batch.selected.v1

output_event_types:
  - p03.importance.scored.v1

latency_budget_ms: 100

side_effects:
  - writes to st_learned_weights

idempotent: true

failure_modes:
  - code: EMBEDDING_NOT_FOUND
    policy: retry
    max_retries: 2
  - code: TIMEOUT
    policy: fallback_default
    max_retries: 0

description: |
  Importance Scorer Module (R1 Phase)
  Computes importance scores for hippocampal events using weighted formula.
```

### B.3 Pipeline ADR Pattern

Source: [docs/architecture/decisions-K0/pipelines/P02-write-pipeline-architecture.md](../architecture/decisions-K0/pipelines/P02-write-pipeline-architecture.md) Lines 1-30

```markdown
# P03 Consolidation Pipeline - Architecture Decision Record

**Pipeline ID:** P03_CONSOLIDATION
**Phase:** K0 Phase 2 (Memory Consolidation)
**Status:** PROPOSED
**Date:** 2025-12-31
**Last Updated:** 2025-12-31
**Owner:** K0 Architecture Team

**Related ADRs:**
- K004: Capability Mesh Architecture
- K020: Feedback Signals Subsystem
- P02: Write Pipeline Architecture

---

## Executive Summary

P03_CONSOLIDATION is the K0 background pipeline responsible for...

---

## Architecture Overview

### System Context

[Diagram]
```

### B.4 Capability Contract YAML Pattern

Source: [k0/contracts/capabilities/core.v1.yaml](../../k0/contracts/capabilities/core.v1.yaml) Lines 1-50

```yaml
# Consolidation Capabilities
# Version: v1
# ADR: P03-consolidation-architecture

version: v1

capabilities:
  score_importance:
    description: "Compute importance score for hippocampal event"
    providers:
      - type: module
        module_id: consolidation.importance_scorer
        priority: 1
        latency_budget_ms: 100
        condition: always
    default_timeout_ms: 200

  cluster_episodes:
    description: "Cluster events into episodic memories using DBSCAN"
    providers:
      - type: module
        module_id: consolidation.episodic_clusterer
        priority: 1
        latency_budget_ms: 500
        condition: always
    default_timeout_ms: 1000
```

### B.5 Event Schema JSON Pattern

Source: [k0/contracts/schemas/cognitive_embedding_backfilled.json](../../k0/contracts/schemas/cognitive_embedding_backfilled.json)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://familyos.ai/schemas/p03_consolidation_triggered.v1.json",
  "title": "P03 Consolidation Triggered Event",
  "description": "Emitted when P03 consolidation cycle is triggered",
  "type": "object",
  "required": ["event_id", "tenant_id", "space_id", "trigger_type", "triggered_at"],
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Unique event identifier (ULID)"
    },
    "tenant_id": {
      "type": "string",
      "description": "Tenant identifier"
    },
    "space_id": {
      "type": "string",
      "description": "Space identifier"
    },
    "trigger_type": {
      "type": "string",
      "enum": ["INTERVAL", "THRESHOLD", "MANUAL"],
      "description": "What triggered the consolidation"
    },
    "triggered_at": {
      "type": "integer",
      "description": "Unix timestamp (ms) when triggered"
    }
  }
}
```

### B.6 Naming Conventions

| Entity Type | Pattern | Example |
|-------------|---------|---------|
| Pipeline ID | `P{NN}_{NAME}` | `P03_CONSOLIDATION` |
| Module ID | `{domain}.{function}` | `consolidation.importance_scorer` |
| Event Topic | `p{nn}.{action}.{status}.v{n}` | `p03.consolidation.triggered.v1` |
| Table Name | `st_{name}` | `st_epi`, `st_sem`, `st_kg_dom` |
| Capability | `{verb}_{noun}` | `score_importance`, `cluster_episodes` |
| Config Key | `p{nn}.{section}.{key}` | `p03.importance.emotional_weight` |
| Contract File | `{module_id}.v{n}.yaml` | `consolidation.importance_scorer.v1.yaml` |
| ADR File | `P{NN}-{slug}.md` | `P03-consolidation-architecture.md` |

---

## Part C: Scope Boundaries (WHAT TO DO / NOT DO)

### C.1 Files To CREATE (Exact Paths)

| File Path | Purpose | Created By Issue |
|-----------|---------|------------------|
| `docs/architecture/decisions-K0/pipelines/P03-consolidation-architecture.md` | Pipeline architecture ADR | 0.2.1 |
| `docs/architecture/decisions-K0/pipelines/P03-state-machine.md` | R0-R8 state machine ADR | 0.2.2 |
| `docs/architecture/decisions-K0/pipelines/P03-capability-security.md` | Capability model ADR | 0.2.3 |
| `docs/architecture/decisions-K0/pipelines/P03-feedback-safety.md` | Feedback safety ADR | 0.2.4 |
| `k0/contracts/pipelines/p03_consolidation.v1.yaml` | Pipeline contract | 0.2.5 |
| `k0/contracts/capabilities/consolidation.v1.yaml` | Capability definitions | 0.2.7 |
| `k0/contracts/schemas/p03_consolidation_triggered.json` | Event schema | 0.2.8 |
| `k0/contracts/schemas/p03_consolidation_complete.json` | Event schema | 0.2.8 |
| `k0/contracts/schemas/p03_phase_complete.json` | Event schema | 0.2.8 |
| `k0/contracts/schemas/p03_episode_formed.json` | Event schema | 0.2.8 |
| `k0/contracts/schemas/p03_pattern_discovered.json` | Event schema | 0.2.8 |
| `k0/contracts/schemas/p03_gap_detected.json` | Event schema | 0.2.8 |
| `k0/contracts/schemas/p03_kg_updated.json` | Event schema | 0.2.8 |
| `k0/contracts/schemas/p03_insight_generated.json` | Event schema | 0.2.8 |
| `k0/contracts/jsonschema/p03.config.schema.json` | Config schema | 0.2.9 |
| `k0/contracts/modules/consolidation.batch_selector.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.importance_scorer.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.hebbian_learner.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.simhash_deduplicator.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.decay_scorer.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.entity_extractor.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.relationship_builder.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.causal_inference.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.insight_generator.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.status_updater.v1.yaml` | Module contract | 0.2.6 |
| `k0/contracts/modules/consolidation.memory_writer.v1.yaml` | Module contract | 0.2.6 |

### C.2 Files To MODIFY (Exact Paths + What Changes)

| File Path | What To Change | Modified By Issue |
|-----------|----------------|-------------------|
| `governance/k0/k0_architecture_master.md` | Add P03 to Parts 2,4,5,6,7,9,10,11,13 | 0.1.3 |
| `k0/pipelines/whiteboard.md` | Add P03 topics to event bus tables | 0.1.4 |
| `k0/contracts/VERSION` | Update checksum (if required) | 0.2.10 |

### C.3 Files To NEVER TOUCH

| File Path | Reason |
|-----------|--------|
| `k0/contracts/pipelines/p02_write.v1.yaml` | Production P02 - not M0 scope |
| `k0/contracts/pipelines/p08_embedding_management.v2.yaml` | Production P08 - not M0 scope |
| `k0/contracts/capabilities/core.v1.yaml` | Core capabilities - create separate file instead |
| `k0/db/alembic/versions/*.py` | Migrations are M2 scope |
| `k0/kernel/*.py` | Kernel code is not M0 scope |

### C.4 Out of Scope (Deferred to Later Milestone)

| Item | Deferred To | Reason |
|------|-------------|--------|
| P03BatchEnvelope implementation | M1 | Code implementation |
| Alembic migrations | M2 | Storage is M2 scope |
| Module implementations | M4+ | Code is M4+ scope |
| Tests for modules | M4+ | Tests follow code |

---

## Part D: Execution Checklist (THE WORK)

### Epic 0.1 — Governance Sync + Drift Resolution

#### Issue 0.1.1 — Run governance sync and capture baseline

**Status**: ✅ COMPLETED (2025-12-31)

**Inputs Required**:

- [x] Implementation Plan: [P03 M0 scope](../pipelines/P03_implementation_plan_skeleton.md#milestone-0--governance--decisions--contract-baseline)
- [x] Sync tool: [governance/k0/scripts/sync.py](../../governance/k0/scripts/sync.py)

**Work To Do**:

1. ✅ Run `python -m governance.k0.scripts.sync --report`
2. ✅ Save output to this ticket (see Part E.0)
3. ✅ Record branch: `postgre-sql-migration`
4. ✅ Record commit SHA: `3ce195badedd983aaf2d1f35129f0d15ec45a96c`

**Outputs Produced**:

- [x] Sync report attached in Part E.0
- [x] Branch/SHA recorded in header

**Verification**:

```powershell
python -m governance.k0.scripts.sync --report
# Result: OVERALL SYNCED ✅
```

**Blocked By**: None

**Blocks**: 0.1.2, 0.1.3

---

#### Issue 0.1.2 — Reconcile P03 dossier vs K0 master registry

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] Dossier Appendix D/E: [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md)
- [x] Master registry: [k0_architecture_master.md](../../governance/k0/k0_architecture_master.md)
- [x] Whiteboard: [whiteboard.md](../../k0/pipelines/whiteboard.md)

**Work To Do**:

1. Create diff table:

| Current Registry Value | Dossier Canonical Value | Decision |
|------------------------|-------------------------|----------|
| P03 (short ID) | P03_CONSOLIDATION | CHANGE to P03_CONSOLIDATION |
| (missing) | p03.consolidation.triggered.v1 | ADD |
| st_hipp_store | st_hipp_events | CHANGE |
| contracts/schemas/ | k0/contracts/schemas/ | CHANGE |

1. Document approved canonical names

**Outputs Produced**:

- [x] Diff table in Part E.6
- [x] Canonical name list approved in Part E.4

**Verification**: ✅ Reviewed - dossier is authoritative, registry to be updated in 0.1.3

**Blocked By**: 0.1.1 ✅

**Blocks**: 0.1.3, 0.2.x

---

#### Issue 0.1.3 — Register P03 (Planning) artifacts across master registries

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] Canonical names from 0.1.2
- [x] Master registry: [k0_architecture_master.md](../../governance/k0/k0_architecture_master.md)
- [x] Dossier sections: Appendix D.5, D.9, E, F, G.5

**Work To Do**:

1. ✅ Update Part 2.1 (Pipeline Master Table): Updated P03 row with canonical name, modules M28-M35, scheduler types
2. ✅ Update Part 2.2 (Pipeline Dependencies): Updated P03 row with full events consumed/produced, all storage tables
3. ✅ Update Part 4 (Events): Verified all P03 topics present (including `p03.embedding.created.v1` from dossier §9.4.1)
4. ✅ Update Part 6 (Storage): Updated owner modules to canonical IDs (M34 TruthWriter, M31 KGConsolidator, M35 GapDetector)
5. (Deferred) Part 5, 7, 9, 10, 11, 13: Will be populated during Epic 0.2 ADR/contract creation

**Outputs Produced**:

- [x] k0_architecture_master.md updated (3 sections modified)

**Verification**:

```
python -m governance.k0.scripts.sync --report
# Result: OVERALL SYNCED ✅
```

**Blocked By**: 0.1.2 ✅

**Blocks**: 0.2.x

**Key Decision**: `p03.embedding.created.v1` KEPT (exists in dossier §9.4.1 even though omitted from Appendix E.2 summary)

---

#### Issue 0.1.4 — Update K0 pipeline whiteboard topic registry for P03

**Status**: ✅ COMPLETED (VERIFICATION ONLY)

**Inputs Required**:

- [x] Canonical topic names from 0.1.2
- [x] Whiteboard: [whiteboard.md](../../k0/pipelines/whiteboard.md)

**Work To Do**:

1. ✅ VERIFIED: P03 topics already in event bus namespace table (Lines 785-799)
2. ✅ VERIFIED: Producers/consumers documented (Lines 1183)

**Outputs Produced**:

- [x] whiteboard.md already contains P03 topics (NO CHANGES NEEDED)

**Verification**: Visual inspection confirmed all 14 P03 topics present with correct producers/consumers

**Finding**: Whiteboard was already updated with P03 topics matching dossier Appendix E.2:

- Entry: `p03.consolidation.triggered.v1`, `p02.write.complete.v1`
- Exit: 12 topics (all matching canonical names)

**Blocked By**: 0.1.2 ✅

**Blocks**: 0.2.8

---

### Epic 0.2 — ADR + Contract Set for P03

#### Issue 0.2.1 — ADR: P03 Consolidation pipeline architecture

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] ADR template: [k000-template.md](../architecture/decisions-K0/k000-template.md)
- [x] P02 ADR pattern: [P02-write-pipeline-architecture.md](../architecture/decisions-K0/pipelines/P02-write-pipeline-architecture.md)
- [x] Dossier Appendix D, E: [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md)
- [x] Dossier Appendix E.10 (canonical ADR naming): `k010-p03` series

**Work To Do**:

1. ✅ Created `docs/architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md` (per E.10)
2. ✅ Included: pipeline variants, entry/exit topics, R0-R8 stage mapping, concurrency=1, DAG structure

**Outputs Produced**:

- [x] ADR file created (k010-p03-consolidation-architecture.md)
- [ ] ADR indexed in master Part 11.1 (deferred to 0.2.10)

**Verification**: ✅ ADR follows template structure, references dossier sections

**Note**: File name changed from `P03-consolidation-architecture.md` to `k010-p03-consolidation-architecture.md` per Dossier Appendix E.10.

**Blocked By**: 0.1.3 ✅

**Blocks**: 0.2.5

---

#### Issue 0.2.2 — ADR: R0–R8 state machine + idempotency

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] Dossier Appendix G: [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md#appendix-g)
- [x] Dossier Appendix E.10 (canonical ADR naming): `k010.1-p03` series

**Work To Do**:

1. ✅ Created `docs/architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md` (per E.10)
2. ✅ Adopted Appendix G as normative
3. ✅ Documented INIT/PROC/SKIP/FAIL/DONE states, idempotency keys, retry matrix

**Outputs Produced**:

- [x] ADR file created (k010.1-sleep-cycle-state-machine.md)
- [x] Cross-linked from 0.2.1 ADR

**Verification**: ✅ ADR references Appendix G explicitly

**Note**: File name changed from `P03-state-machine.md` to `k010.1-sleep-cycle-state-machine.md` per Dossier Appendix E.10.

**Blocked By**: 0.1.3 ✅

**Blocks**: 0.2.5

---

#### Issue 0.2.3 — ADR: Capability/security model for P03

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] K004 Capability Mesh: [k004-capability-mesh-architecture.md](../architecture/decisions-K0/k004-capability-mesh-architecture.md)
- [x] Dossier Appendix D.2.2, D.8.3, I
- [x] Dossier Appendix E.10 (canonical ADR naming): `k010.9-p03` series

**Work To Do**:

1. ✅ Created `docs/architecture/decisions-K0/pipelines/k010.9-capability-based-security.md` (per E.10)
2. ✅ Defined capabilities per stage, INTERSECT_CALLER fabric invocation policy, RLS posture

**Outputs Produced**:

- [x] ADR file created (k010.9-capability-based-security.md)
- [x] References K004

**Verification**: ✅ ADR cross-references K004

**Note**: File name changed from `P03-capability-security.md` to `k010.9-capability-based-security.md` per Dossier Appendix E.10.

**Blocked By**: 0.1.3 ✅

**Blocks**: 0.2.7

---

#### Issue 0.2.4 — ADR: Closed-loop feedback ingestion + safety guardrails

**Status**: ⏭️ SKIPPED (N/A)

**Rationale**: Dossier Appendix E.10 does not include a feedback-safety ADR in the `k010.*-p03` series. Feedback signals architecture is governed by **K020 Feedback Signals Subsystem** at the K0 level. P03-specific quarantine/rollback mechanisms are documented in:
- Dossier §6.21 (st_feedback_quarantine schema)
- Dossier §2.5 (rollback mechanisms)
- K020 ADR (pipeline-agnostic feedback ingestion)

No separate P03 ADR required for M0 scope. M7 implementation will reference K020 directly.

**Inputs Required**:

- [x] K020 Feedback Signals: [k020-feedback-signals-subsystem.md](../architecture/decisions-K0/k020-feedback-signals-subsystem.md) (EXISTS)
- [x] Dossier learning budget, quarantine, rollback specs (§6.21, §2.5)

**Work To Do**:

1. ⏭️ SKIPPED - Not in E.10 canonical ADR list
2. ⏭️ K020 already covers feedback ingestion; P03 implementation will reference K020

**Outputs Produced**:

- [x] N/A - No file created (covered by K020)
- [x] References K020 (existing)

**Verification**: ✅ E.10 review confirms no P03-feedback-safety ADR required

**Blocked By**: 0.1.3 ✅

**Blocks**: None (M7 will reference K020 directly)

---

#### Issue 0.2.5 — Contracts: P03 pipeline contract(s) (YAML)

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] Pipeline YAML pattern: [p02_write.v1.yaml](../../k0/contracts/pipelines/p02_write.v1.yaml)
- [x] ADRs from 0.2.1, 0.2.2

**Work To Do**:

1. ✅ Created `k0/contracts/pipelines/p03_consolidation.v1.yaml`
2. ✅ Includes: pipeline_id=P03_CONSOLIDATION, entry_topic, exit_topic, concurrency=1, required_capabilities (34), dag (17 stages R0-R8), triggers (INTERVAL/THRESHOLD/MANUAL), failure_modes

**Outputs Produced**:

- [x] Pipeline contract created: `k0/contracts/pipelines/p03_consolidation.v1.yaml`
- [ ] Registered in master Part 5.2 (deferred to 0.2.10)

**Verification**:

```powershell
# Format matches P02 pattern ✅
# 17 DAG stages defined (R0-R8 phases) ✅
# All capabilities from Appendix D.2.2 included ✅
```

**Blocked By**: 0.2.1 ✅, 0.2.2 ✅

**Blocks**: 0.2.6, 0.2.10

---

#### Issue 0.2.6 — Contracts: P03 module contracts (YAML)

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] Module YAML pattern: [affect.analyze.v1.yaml](../../k0/contracts/modules/affect.analyze.v1.yaml)
- [x] Dossier Appendix D.10 (failure modes)

**Work To Do**:

1. ✅ Created 17 module contracts for all P03 stages
2. ✅ Each has: module_id, version, latency_budget_ms, idempotent, failure_modes, input/output event types, fabric_capabilities

**Files Created**:

- [x] `k0/contracts/modules/consolidation.batch_selector.v1.yaml`
- [x] `k0/contracts/modules/consolidation.importance_scorer.v1.yaml`
- [x] `k0/contracts/modules/consolidation.hebbian_learner.v1.yaml`
- [x] `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml`
- [x] `k0/contracts/modules/consolidation.episode_builder.v1.yaml`
- [x] `k0/contracts/modules/consolidation.simhash_deduplicator.v1.yaml`
- [x] `k0/contracts/modules/consolidation.decay_scorer.v1.yaml`
- [x] `k0/contracts/modules/consolidation.prune_decider.v1.yaml`
- [x] `k0/contracts/modules/consolidation.entity_extractor.v1.yaml`
- [x] `k0/contracts/modules/consolidation.relationship_builder.v1.yaml`
- [x] `k0/contracts/modules/consolidation.causal_inference.v1.yaml`
- [x] `k0/contracts/modules/consolidation.counterfactual.v1.yaml`
- [x] `k0/contracts/modules/consolidation.forward_simulator.v1.yaml`
- [x] `k0/contracts/modules/consolidation.insight_generator.v1.yaml`
- [x] `k0/contracts/modules/consolidation.status_updater.v1.yaml`
- [x] `k0/contracts/modules/consolidation.memory_writer.v1.yaml`
- [x] `k0/contracts/modules/consolidation.gap_detector.v1.yaml`

**Outputs Produced**:

- [x] 17 module contract files created
- [ ] Registered in master Part 5.1 (deferred to 0.2.10)

**Verification**: ✅ All module contracts follow existing pattern with latency budgets from dossier D.3.3

**Blocked By**: 0.2.5 ✅

**Blocks**: 0.2.10

---

#### Issue 0.2.7 — Contracts: P03 capabilities (fabric) registry

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] Capability YAML pattern: [core.v1.yaml](../../k0/contracts/capabilities/core.v1.yaml)
- [x] Dossier Appendix E.5
- [x] ADR from 0.2.3

**Work To Do**:

1. ✅ Created `k0/contracts/capabilities/consolidation.v1.yaml`
2. ✅ Defined 17 capabilities: score_importance, cluster_episodes, build_episodes, detect_duplicates, score_decay, decide_prune, extract_entities, build_relationships, infer_causality, generate_counterfactuals, run_forward_simulation, generate_insights, update_status, write_memory, detect_gaps, apply_hebbian_learning, select_batch

**Outputs Produced**:

- [x] Capability contract created: `k0/contracts/capabilities/consolidation.v1.yaml`
- [x] Referenced by pipeline + module contracts

**Verification**: ✅ All capabilities from Appendix E.5 included with providers, timeouts, capability_groups

**Blocked By**: 0.2.3 ✅

**Blocks**: 0.2.10

---

#### Issue 0.2.8 — Contracts: P03 event topic schemas (JSON)

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] JSON schema pattern: [cognitive_embedding_backfilled.json](../../k0/contracts/schemas/cognitive_embedding_backfilled.json)
- [x] Dossier Appendix E.2 (topics)

**Work To Do**:

1. ✅ Created 8 JSON schema files for P03 entry/exit topics
2. ✅ All schemas have `additionalProperties: false` per existing pattern
3. ✅ All schemas use `$id` as topic name (e.g., `p03.consolidation.triggered.v1`)
4. ✅ Timestamps in seconds (not milliseconds) matching existing pattern

**Files Created**:

- [x] `k0/contracts/schemas/p03_consolidation_triggered.json`
- [x] `k0/contracts/schemas/p03_consolidation_complete.json`
- [x] `k0/contracts/schemas/p03_phase_complete.json`
- [x] `k0/contracts/schemas/p03_episode_formed.json`
- [x] `k0/contracts/schemas/p03_pattern_discovered.json`
- [x] `k0/contracts/schemas/p03_gap_detected.json`
- [x] `k0/contracts/schemas/p03_kg_updated.json`
- [x] `k0/contracts/schemas/p03_insight_generated.json`

**Outputs Produced**:

- [x] 8 event schema files created
- [ ] Registered in master Part 5.3 (deferred to 0.2.10)

**Verification**: ✅ All schemas match existing `cognitive_*.json` pattern:
- `additionalProperties: false` present in all
- `$id` format matches topic naming convention
- Timestamps in seconds (Unix epoch)

**Blocked By**: 0.1.4 ✅

**Blocks**: 0.2.10

---

#### Issue 0.2.9 — Contracts: P03 config schema + threshold validation

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] JSON schema pattern: [retention_policy.schema.json](../../k0/contracts/jsonschema/retention_policy.schema.json)
- [x] Dossier Appendix E.7, F

**Work To Do**:

1. ✅ Created `k0/contracts/jsonschema/p03.config.schema.json`
2. ✅ Includes all p03.* config keys from Appendix E.7:
   - Schedule keys (enabled, cron, interval_seconds)
   - Batch keys (size, max_events_per_cycle, timeout_seconds)
   - Reconciliation thresholds (reinforce_min, extend_min, extend_max, contradict_threshold, novelty_min)
   - Decay thresholds (prune, archive, active)
   - Confidence thresholds (canonical_min, high, medium, low)
   - Phase keys (r5_dream.enabled, skip_on_backlog, backlog_threshold)
   - Active learning keys (enabled, max_gaps_per_cycle)
   - Gap thresholds (entropy_min, priority_high, priority_low)
   - Anchor thresholds (drift)
   - Concurrency keys (parallel_workers, max_concurrent_cycles)
   - Thompson sampling priors (reinforce.alpha/beta, extend_lower.alpha/beta)

**Outputs Produced**:

- [x] Config schema created: `k0/contracts/jsonschema/p03.config.schema.json`
- [x] Includes validation rules (min/max from Appendix F)
- [x] Includes example configuration

**Verification**: ✅ All config keys from E.7 and F present with proper validation constraints

**Blocked By**: 0.1.3 ✅

**Blocks**: 0.2.10

---

#### Issue 0.2.10 — Contract checksum + registry hygiene

**Status**: ✅ COMPLETED

**Inputs Required**:

- [x] All contracts from 0.2.5-0.2.9 COMPLETED
- [x] Master registry: [k0_architecture_master.md](../../governance/k0/k0_architecture_master.md) UPDATED

**Work To Do**:

1. ✅ Updated Part 4.1 - Added P03 Internal Stage Events (16 events)
2. ✅ Updated Part 5.1 - Added 17 P03 module contracts (M37-M53)
3. ✅ Updated Part 5.2 - Added p03_consolidation.v1.yaml pipeline contract
4. ✅ Updated Part 5.3 - P03 event schemas already present
5. ✅ Updated Part 5.4 - Added P03 module contracts, pipeline contract, capability contract, config schema
6. ✅ Updated Part 11.1 - Added K010, K010.1, K010.9 ADRs (canonical per E.10)
7. ✅ Run contract validation - **SYNCED**
8. ✅ Fixed governance scanners to properly detect P03 artifacts

**Governance Sync Report (2025-12-31 20:19:33)**:

```
OVERALL SYNCED

All categories OK:
- Syscalls: 19/19 OK
- Pipelines: 3/20 OK
- Modules: 22/24 OK
- ADRs: 43/39 OK
- Events: 65/85 OK
- ModuleContracts: 39/40 OK
- PipelineContracts: 3/3 OK
- EventSchemas: 13/22 OK
- All other categories OK
```

**Scanner Fixes Applied**:
1. `event_scanner.py` - Added "P03 Internal" and "Feedback" table fragments to search list
2. `contract_scanner.py` - Fixed regex to include digits `[a-z0-9_.]+` for p03/p06 schema names

**Outputs Produced**:

- [x] All contracts created (0.2.5-0.2.9)
- [x] All registries updated in k0_architecture_master.md
- [x] Governance scanners fixed for P03 artifact detection
- [x] VERSION checksums: Not required for Planning status contracts

**Verification**:

```powershell
python -m governance.k0.scripts.sync --report
# Result: OVERALL SYNCED
```

**Blocked By**: 0.2.5 ✅, 0.2.6 ✅, 0.2.7 ✅, 0.2.8 ✅, 0.2.9 ✅

**Blocks**: M1

---

## Part E: Outputs Manifest (WHAT WE PRODUCED)

> **Fill this section AS YOU COMPLETE each issue**

### E.0 Baseline Governance Sync Report (Issue 0.1.1)

**Date**: 2025-12-31
**Branch**: `postgre-sql-migration`
**Commit**: `3ce195badedd983aaf2d1f35129f0d15ec45a96c`

```text
K0 Architecture Sync Tool
Master: governance/k0/k0_architecture_master.md
Date: 2025-12-31 19:07:19

Category          Scanned    Registered   Undoc    Missing(C)   Status
--------------------------------------------------------------------------------
Syscalls          19         19           0        0            OK
Pipelines         2          20           0        0            OK
Modules           22         24           0        0            OK
ADRs              40         37           0        0            OK
Events            49         66           0        0            OK
Tables            25         39           0        0            OK
Migrations        26         26           0        0            OK
Indexes           74         74           0        0            OK
ModuleContracts   22         31           0        0            OK
PipelineContracts 2          3            0        0            OK
EventSchemas      5          6            0        0            OK
Capabilities      13         29           0        0            OK
FabricProviders   18         18           0        0            OK
KernelHooks       17         18           0        0            OK
BackgroundWorkers 8          11           0        0            OK
Metrics           0          0            0        0            OK
ConfigKeys*       223        232          0        0            OK
FeatureFlags      5          5            0        0            OK
ConfigVersions    4          4            0        0            OK
ContractVersions* 25         0            25       0            OK
ArtifactChecksums 70         70           0        0            OK
--------------------------------------------------------------------------------
OVERALL                                                         SYNCED
```

**Key Observations**:

- Pipelines: 2 scanned (P02, P08), 20 registered (includes Planning)
- Modules: 22 scanned, 24 registered (some Planning)
- Events: 49 scanned, 66 registered (many Planning)
- Tables: 25 scanned, 39 registered (many Planning)
- P03 can be added without drift conflicts

### E.1 Files Created

| File | Path | Created By | Verified |
|------|------|------------|----------|
| (To be filled during execution) | | | |

### E.2 Files Modified

| File | Path | What Changed | Modified By |
|------|------|--------------|-------------|
| (To be filled during execution) | | | |

### E.3 Decisions Made (Not In Original Plan)

| Decision | Options Considered | Chosen | Rationale | Recorded In |
|----------|-------------------|--------|-----------|-------------|
| (To be filled during execution) | | | | |

### E.4 Canonical Names Approved (Issue 0.1.2)

> **Decision**: Dossier Appendix E is AUTHORITATIVE. Registry values will be updated to match.

#### Pipeline Identifiers

| Entity Type | Canonical Name | Notes |
|-------------|----------------|-------|
| Pipeline ID | `P03_CONSOLIDATION` | Full ID for contracts; short `P03` OK for registry tables |
| Pipeline Version | `v1` | First version |
| Incremental Mode ID | `P03_INCREMENTAL` | Future: event-driven mode |

#### Entry Topics (P03 Subscribes)

| Canonical Topic | Schema | Source | QoS |
|-----------------|--------|--------|-----|
| `p03.consolidation.triggered.v1` | `P03TriggerEvent` | Scheduler | AMBER |
| `p02.write.complete.v1` | `P02WriteComplete` | P02 | AMBER |

#### Exit Topics (P03 Emits)

| Canonical Topic | Schema | Consumer | QoS |
|-----------------|--------|----------|-----|
| `p03.consolidation.complete.v1` | `P03ConsolidationComplete` | Monitoring, P04 | AMBER |
| `p03.phase.complete.v1` | `P03PhaseComplete` | Monitoring | GREEN |
| `p03.episode.formed.v1` | `P03EpisodeFormed` | P04, P05 | AMBER |
| `p03.pattern.discovered.v1` | `P03PatternDiscovered` | P04 | AMBER |
| `p03.truth.reinforced.v1` | `P03TruthReinforced` | Audit | GREEN |
| `p03.truth.created.v1` | `P03TruthCreated` | Audit | GREEN |
| `p03.truth.evolved.v1` | `P03TruthEvolved` | Audit | GREEN |
| `p03.memory.pruned.v1` | `P03MemoryPruned` | Audit | RED |
| `p03.gap.detected.v1` | `P03GapDetected` | P06 | AMBER |
| `p03.kg.updated.v1` | `P03KGUpdated` | P04 | AMBER |
| `p03.insight.generated.v1` | `P03InsightGenerated` | P05 | AMBER |

#### Truth Layer Tables (8 Memory Layers)

| Canonical Table | Primary Key | Partitioned By |
|-----------------|-------------|----------------|
| `st_epi` | `epi_id` | tenant_id, space_id |
| `st_sem` | `sem_id` | tenant_id, space_id |
| `st_procedural` | `proc_id` | tenant_id, space_id |
| `st_social` | `social_id` | tenant_id, space_id |
| `st_prospective` | `prosp_id` | tenant_id, space_id |
| `st_kg_dom` | `entity_id` | tenant_id |
| `st_kg_edges` | `edge_id` | tenant_id |
| `st_vec` | `embedding_id` | tenant_id, space_id |

#### Staging & Support Tables

| Canonical Table | Purpose | Lifecycle |
|-----------------|---------|----------|
| `st_hipp_events` | Hippocampal staging (P02 writes, P03 reads) | Cleared after consolidation |
| `st_learning_queue` | Active learning gaps | 30 day retention |
| `st_anchors` | Bayesian belief anchors | Permanent |
| `st_anchor_observations` | Anchor evidence history | 90 day retention |
| `st_consolidation_audit` | Consolidation decision log | 90 day retention |

#### Module IDs (M18-M25 Logical → M28-M35 K0 Registry)

| Dossier ID | Canonical Module ID | K0 Registry ID | Phase |
|------------|---------------------|----------------|-------|
| M18 | `consolidation.episodic_clusterer:v1` | M28 (reserved) | R2 |
| M19 | `consolidation.duplicate_detector:v1` | M29 (reserved) | R3 |
| M20 | `consolidation.retention_enforcer:v1` | M30 (reserved) | R3 |
| M21 | `consolidation.kg_consolidator:v1` | M31 (reserved) | R4 |
| M22 | `consolidation.dream_explorer:v1` | M32 (reserved) | R5 |
| M23 | `consolidation.replay_coordinator:v1` | M33 (reserved) | R1 |
| M24 | `consolidation.truth_writer:v1` | M34 (reserved) | R7 |
| M25 | `consolidation.gap_detector:v1` | M35 (reserved) | R8 |

### E.5 Governance Sync Status (End of Milestone)

(To be filled after M0 completion)

---

### E.6 Reconciliation Diff Table (Issue 0.1.2)

> **Created**: 2025-12-31
> **Sources Compared**:
>
> - Master: [k0_architecture_master.md](../../governance/k0/k0_architecture_master.md) Lines 142, 186, 491-495, 925-937
> - Dossier: [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md) Appendix E (Lines 26988-27280)

#### Category 1: Pipeline Registry (Part 2.1)

| Field | Current Registry Value | Dossier Canonical Value | Action |
|-------|------------------------|-------------------------|--------|
| Pipeline ID | `P03` | `P03_CONSOLIDATION` | KEEP `P03` in table, use full ID in contracts |
| Name | `Consolidation / Forgetting` | `P03 Consolidation - Memory Truth Formation` | UPDATE name |
| Modules Used | `M18,M19,M20,M21,M22,M23,M24,M25` | `M28,M29,M30,M31,M32,M33,M34,M35` | UPDATE to K0 registry IDs |
| Scheduler? | `Yes (timer)` | `Yes (INTERVAL/THRESHOLD/MANUAL)` | UPDATE with trigger types |
| ADRs | `-` | `K010.x-p03-*` | ADD during Issue 0.2.x |

#### Category 2: Event Topics (Part 4.1)

| Topic | Current Status | Dossier Status | Action |
|-------|----------------|----------------|--------|
| `p03.consolidation.triggered.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.consolidation.complete.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.phase.complete.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.episode.formed.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.pattern.discovered.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.truth.reinforced.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.truth.created.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.truth.evolved.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.memory.pruned.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.gap.detected.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.kg.updated.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.insight.generated.v1` | ✅ Registered (Planning) | ✅ Canonical | NO CHANGE |
| `p03.embedding.created.v1` | ✅ Registered (Planning) | ❌ NOT in dossier E.2 | REMOVE (use P08 embedding events) |
| `p03.causal_edge.demoted.v1` | ✅ Registered (Planning) | ❌ NOT in dossier E.2 | KEEP (internal R4 event) |
| `core.enrichment.complete.v1` | Listed as P03 entry | ❌ NOT in dossier E.2.1 | REMOVE from P03 entry (P02 internal) |

#### Category 3: Storage Tables (Part 6.1)

| Table | Current Registry | Dossier | Action |
|-------|------------------|---------|--------|
| `st_epi` | ✅ Owner: P03 (M35) | Owner: P03 (M24 TruthWriter) | UPDATE owner module |
| `st_sem` | ✅ Owner: P03 (M35) | Owner: P03 (M24 TruthWriter) | UPDATE owner module |
| `st_procedural` | ✅ Owner: P03 (M35) | Owner: P03 (M24 TruthWriter) | UPDATE owner module |
| `st_social` | ✅ Owner: P03 (M35) | Owner: P03 (M24 TruthWriter) | UPDATE owner module |
| `st_prospective` | ✅ Owner: P03 (M33) | Owner: P03 (M24 TruthWriter) | UPDATE owner module |
| `st_kg_dom` | ✅ Owner: P03 (M32) | Owner: P03 (M21 KGConsolidator) | UPDATE owner module |
| `st_kg_edges` | ✅ Owner: P03 (M32) | Owner: P03 (M21 KGConsolidator) | UPDATE owner module |
| `st_learning_queue` | ✅ Owner: P03 (M36) | Owner: P03 (M25 GapDetector) | UPDATE owner module |
| `st_anchors` | ✅ Owner: P03 (M36), P06 | Owner: P03/P06 | NO CHANGE |
| `st_anchor_observations` | ✅ Exists | ✅ Matches | NO CHANGE |
| `st_consolidation_audit` | ✅ Exists | ✅ Matches | NO CHANGE |

#### Category 4: Schema Paths

| Schema | Current Path | Dossier Path | Action |
|--------|--------------|--------------|--------|
| P03 Trigger | `k0/contracts/schemas/p03_consolidation_triggered.json` | Same | NO CHANGE |
| P03 Complete | `k0/contracts/schemas/p03_consolidation_complete.json` | Same | NO CHANGE |
| All P03 schemas | `k0/contracts/schemas/p03_*.json` | Same pattern | NO CHANGE |

#### Summary of Required Actions for Issue 0.1.3

| Category | Total Items | No Change | Update | Add | Remove |
|----------|-------------|-----------|--------|-----|--------|
| Pipeline Registry | 5 fields | 0 | 4 | 1 | 0 |
| Event Topics | 15 topics | 12 | 0 | 0 | 3 |
| Storage Tables | 11 tables | 4 | 7 | 0 | 0 |
| Schema Paths | 12 schemas | 12 | 0 | 0 | 0 |

**Decision**: Proceed with Issue 0.1.3 using dossier Appendix E as authoritative source.

```text
$ python -m governance.k0.scripts.sync --report
Date: YYYY-MM-DD
Status: (TBD)
Details: ...
```

---

## Part F: Handoff to Next Milestone (WHAT M1 CAN USE)

> **Fill this section AFTER M0 is complete**

### F.1 ADRs Now Available

| ADR | Path | Governs |
|-----|------|---------|
| (To be filled after completion) | | |

### F.2 Contracts Now Available

| Contract | Path | Version | Import/Usage |
|----------|------|---------|--------------|
| (To be filled after completion) | | | |

### F.3 Registry Entries Now Complete

| Registry Part | What Was Added |
|---------------|----------------|
| Part 2 (Pipelines) | (TBD) |
| Part 4 (Events) | (TBD) |
| Part 5 (Contracts) | (TBD) |
| Part 6 (Storage) | (TBD) |
| Part 7 (Syscalls) | (TBD) |
| Part 9 (Scheduler) | (TBD) |
| Part 10 (Observability) | (TBD) |
| Part 11 (ADRs) | (TBD) |
| Part 13 (Config) | (TBD) |

### F.4 Known Gaps for M1+

| Gap | Why Deferred | Needed By |
|-----|--------------|-----------|
| Module implementations | M0 is contracts only | M4+ |
| Storage migrations | M0 is contracts only | M2 |
| Envelope code | M0 is contracts only | M1 |

---

## Appendix: Quick Reference Commands

```powershell
# Governance sync check
python -m governance.k0.scripts.sync --report

# Individual scanners
python -m governance.k0.scripts.contract_scanner
python -m governance.k0.scripts.event_scanner
python -m governance.k0.scripts.adr_scanner
python -m governance.k0.scripts.module_scanner
python -m governance.k0.scripts.capability_scanner

# Check current branch
git branch --show-current

# Check current commit
git rev-parse HEAD
```
