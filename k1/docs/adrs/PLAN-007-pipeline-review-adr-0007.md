---
adr_id: PLAN-007
title: "Pipeline Review -- ADR-0007 Alignment with planner.md"
status: Accepted
date: 2026-02-14
module: planner
layer: "L3"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-002"
  - "PLAN-001"
  - "PLAN-002"
  - "PLAN-005"
related_events:
  - "k1.planner.plan.ready.v1"
  - "k1.planner.plan.failed.v1"
related_contracts:
  - "k1/contracts/modules/planner/wiring.contract.yaml"
  - "k1/contracts/modules/planner/module.contract.yaml"
related_ports:
  - "ILLMPort"
  - "IMailboxPort"
  - "IBridgePort"
  - "IFabricRetrievalPort"
  - "IStateReadPort"
  - "IDeltaEmitPort"
  - "IEventPort"
implements_issue: "1.1.1"
superseded_by: ""
tags:
  - planner
  - review
  - adr-0007
  - pipeline
  - alignment
  - architectural-pivot
---

# PLAN-007: Pipeline Review -- ADR-0007 Alignment with planner.md

## Context

### Problem Statement

ADR-0007 (4-Stage Planning Pipeline, accepted 2025-01-22) defines the original Planner architecture. Since then, the system has undergone a significant architectural pivot: from a layered Actor Model + FlatBuffers design to a hexagonal port-based event-driven architecture documented in planner.md (Feb 2026). This review assesses alignment between ADR-0007's decisions and the current planner.md specification, flags all drift, and documents which elements are superseded versus preserved.

### Scope

This review covers:

- 4-stage pipeline structure (SKETCH -> EXPAND -> VALIDATE -> COMMIT)
- Per-stage responsibilities and timing
- Serialization and persistence approach
- Module paths and layer organization
- Concurrency and communication model

### Review Source Documents

- **ADR-0007**: `docs/architecture/decisions-K1/03-layer2-orchestration/0007-4stage-planning-pipeline/0007.md` (1804 lines, Jan 2025)
- **planner.md**: Authoritative Planner specification (Feb 2026)
- **ORCH-002**: `k1/docs/adrs/ORCH-002-4stage-planning-orchestrator-protocol.md` (Feb 2026, new-era ADR)

---

## Review Findings

### Preserved Intent (Aligned)

The following ADR-0007 decisions remain valid and are carried forward in planner.md:

| ADR-0007 Decision | planner.md Reference | Status |
| ------------------ | -------------------- | ------ |
| 4-stage pipeline (SKETCH -> EXPAND -> VALIDATE -> COMMIT) | SS5 (26-step pipeline flow) | Preserved -- same 4 stages, same ordering |
| SKETCH uses LLM for creative plan generation | SS6 (SketchService, LLM-1) | Preserved -- LLM generates rough plan |
| COMMIT is deterministic, no LLM | SS9 (PLAN-03), PLAN-005 | Preserved -- zero-LLM COMMIT, now structurally enforced |
| Validation checks structure, deps, capabilities | SS8 (ValidateService, deterministic + LLM arbiter) | Preserved -- 2-tier validation retained |
| WAL persistence for committed plans | SS9.3 (IBridgePort.persist_plan) | Preserved -- fire-and-forget WAL persist |
| Replanning support for mid-execution changes | SS10 (Micro-Replan), PLAN-003 | Preserved -- formalized as micro-replan with 10s budget |

### Architectural Drift (Superseded)

The following ADR-0007 decisions are **superseded** by planner.md and no longer apply:

#### Drift 1: Performance Model

| Aspect | ADR-0007 | planner.md | Impact |
| ------ | -------- | ---------- | ------ |
| SKETCH latency | 150-500ms | 4s P50, 8s timeout | Major -- 8-26x slower; reflects realistic LLM call timing with tool discovery |
| EXPAND latency | <1ms (deterministic lookup) | 3s P50, 5s timeout | Major -- EXPAND now uses LLM (LLM-2) for capability mapping, not pure lookup |
| VALIDATE Tier 1 | <1ms (rule-based) | 2s P50, 3s timeout | Major -- deterministic checks + LLM-3 arbiter integrated in budget |
| COMMIT latency | <10ms | <100ms | Minor -- same order of magnitude |
| Total P95 | <2.5s | ~12s P50 | Major -- fundamentally different performance envelope |

**Root cause:** ADR-0007 assumed EXPAND and VALIDATE Tier 1 were purely deterministic with no LLM calls. planner.md SS7 defines EXPAND as LLM-assisted (LLM-2 for capability mapping) and SS8 includes LLM-3 arbiter in the VALIDATE timing budget.

#### Drift 2: Serialization

| Aspect | ADR-0007 | planner.md | Impact |
| ------ | -------- | ---------- | ------ |
| Serialization format | FlatBuffers (ADR-0011) | Frozen dataclasses (SS4.5, SS9.2) | Major -- no FlatBuffers dependency |
| COMMIT output | FlatBuffers FlowDef | CommittedPlan frozen dataclass | Major -- different output type |
| Schema validation | FlatBuffers compile-time | Protocol classes + contract YAML | Medium -- different validation mechanism |

**Root cause:** Architecture pivot from FlatBuffers binary protocol to Python dataclasses with YAML contracts. Eliminates the FlatBuffers toolchain dependency.

#### Drift 3: Module Paths and Layer Organization

| Aspect | ADR-0007 | planner.md | Impact |
| ------ | -------- | ---------- | ------ |
| Module root | `k1/l2_orchestration/planner/` | `k1/planner/` | Major -- flat module structure |
| Stage files | `k1.l2_orchestration.planner.sketch_stage` | `k1/planner/services/sketch_service.py` | Major -- different naming convention |
| Layer reference | Layer 2 (Orchestration) | Layer 3 (L3) | Major -- Planner is now L3, not L2 |
| Test paths | `tests/k1/l2_orchestration/test_planning_pipeline.py` | `tests/k1/planner/` | Major -- tests follow new module structure |

**Root cause:** Architectural pivot from layered directory structure (l1_input, l2_orchestration, l3_execution, etc.) to flat hexagonal module structure (planner/, orchestrator/, fabric/, etc.).

#### Drift 4: Communication Protocol

| Aspect | ADR-0007 | planner.md | Impact |
| ------ | -------- | ---------- | ------ |
| Request protocol | Actor mailbox (ADR-0002) | Event bus + IMailboxPort (SS4) | Medium -- same mailbox concept, different implementation |
| Plan delivery | Contract Net (ADR-0006) | Event: k1.planner.plan.ready.v1 (ORCH-002) | Major -- event-driven, not Contract Net |
| Inter-stage | Internal method calls | PipelineController orchestration (SS5, F03) | Minor -- similar internal coordination |

**Root cause:** Contract Net protocol replaced by event-driven architecture. ORCH-002 documents the new protocol.

#### Drift 5: EXPAND Stage Nature

| Aspect | ADR-0007 | planner.md | Impact |
| ------ | -------- | ---------- | ------ |
| EXPAND type | Deterministic (pure lookup) | LLM-assisted (LLM-2, 1024 tokens) | Major -- fundamental change in stage nature |
| EXPAND purpose | Fill tool schemas from registry | Map rough steps to concrete capabilities with parameters | Aligned in intent, different in mechanism |
| EXPAND latency | <1ms | 3s P50 | Major -- 3000x slower |

**Root cause:** ADR-0007 envisioned EXPAND as a simple registry lookup. planner.md SS7 defines EXPAND as LLM-assisted because mapping rough plan steps to concrete capability invocations with correct parameters requires inference, not just lookup.

### Sub-ADR Status

ADR-0007 has 4 sub-ADRs that need independent assessment:

| Sub-ADR | Topic | Alignment | Notes |
| ------- | ----- | --------- | ----- |
| 0007a | Sketch prompt engineering | Partially aligned | Prompt engineering intent preserved; specific prompts may need updates for SS6 |
| 0007b | Expand tool registry | Superseded | EXPAND is no longer pure registry lookup (SS7) |
| 0007c | Validation 2-tier | Partially aligned | 2-tier concept preserved; timing and arbiter model changed |
| 0007d | Commit K0 WAL | Partially aligned | WAL persist intent preserved; FlatBuffers serialization superseded |

---

## Decision

### Alignment Assessment

ADR-0007 is **partially aligned** with planner.md. The core intent (4-stage pipeline with creative planning and deterministic commitment) is preserved. The implementation details are **substantially superseded** due to the hexagonal architecture pivot.

### Recommendation

1. **Do not modify ADR-0007** -- it is a historical record of the original architecture
2. **Mark ADR-0007 as superseded** -- reference planner.md and ORCH-002 as the authoritative sources
3. **PLAN-001 through PLAN-006** serve as the new-era ADRs for Planner architectural decisions
4. **ORCH-002** documents the Planner-Orchestrator protocol (replacing Contract Net aspects of ADR-0007)

### What Remains Valid from ADR-0007

- 4-stage pipeline concept (SKETCH -> EXPAND -> VALIDATE -> COMMIT)
- LLM-powered creative planning in SKETCH
- Zero-LLM deterministic COMMIT
- 2-tier validation (deterministic + LLM arbiter)
- WAL persistence for audit trail
- Replanning capability for mid-execution changes

### What Is Superseded

- All performance targets (150-500ms SKETCH -> 4s P50 SKETCH)
- FlatBuffers serialization -> frozen dataclasses
- Layered module paths -> flat hexagonal structure
- Contract Net delivery -> event-driven delivery
- Deterministic EXPAND -> LLM-assisted EXPAND
- Layer 2 placement -> Layer 3 placement

---

## Consequences

### Positive

- Clear documentation of the architectural pivot
- Historical context preserved in ADR-0007
- New-era ADRs (PLAN-001 through PLAN-006) provide current architectural decisions
- ORCH-002 provides the definitive Planner-Orchestrator protocol

### Negative

- Developers must be aware that ADR-0007 is historical, not authoritative
- Sub-ADRs (0007a-0007d) need individual review for partial alignment

### Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Developers follow ADR-0007 instead of planner.md | Med | High | ADR-0007 marked as superseded; planner.md referenced as authoritative |
| Sub-ADR partial alignment causes confusion | Low | Med | Individual sub-ADR reviews in future epic |

---

## Implementation

### Affected Code Paths

No code changes. This is a review document.

### Action Items

| Action | Location | Description |
| ------ | -------- | ----------- |
| Mark ADR-0007 as SUPERSEDED | ADR-0007 frontmatter | Add `superseded_by: [planner.md, ORCH-002, PLAN-001..006]` |
| Reference this review | ADR-0007 body | Add note pointing to PLAN-007 review |
| Update ADR index | `k1/docs/adrs/README.md` | Add PLAN-007 to index |

### Success Metrics

- ADR-0007 frontmatter updated with superseded_by reference
- No implementation code references ADR-0007 paths or contracts
- All new Planner code references planner.md and PLAN-001..006

### Testing Strategy

No tests. Review document only.

---

## Amendment History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2026-02-14 | K1 Architecture Team | Initial review -- ADR-0007 alignment assessment |
