# SEQUENTIAL_ROADMAP.yaml - Quick Reference Guide

**Last Updated:** 2025-10-17  
**Status:** MILESTONE 1 Epic 1.1 Complete | Remaining: Epic 1.2-1.3 + M2-M5 detailed planning

---

## File Structure

```yaml
SEQUENTIAL_ROADMAP.yaml
├── Milestone 1 (Weeks 1-2) — Foundational Architecture [STARTED: Epic 1.1 COMPLETE]
│   ├── Epic 1.1: K0/K1 Kernel Architecture & ADR Infrastructure [6 ISSUES - 320 HOURS]
│   │   ├── K1-001: K0/K1 Boundary Enforcement (16h)
│   │   ├── K1-002: ADR Governance & Traceability (24h)
│   │   ├── K1-003: K0 Bridge Dual-Protocol (40h)
│   │   ├── K1-004: Actor Model (48h)
│   │   ├── K1-005: MPST Protocols (56h)
│   │   └── K1-006: 52-Module Architecture (32h)
│   ├── Epic 1.2: Agent Lifecycle & Orchestration [3 ISSUES - TBD]
│   │   ├── K1-007: Agent Lifecycle FSM (ADR-0005)
│   │   ├── K1-008: 3-Phase Orchestration (ADR-0006)
│   │   └── K1-009: 4-Stage Planning (ADR-0007)
│   └── Epic 1.3: Error Recovery & Resilience [2 ISSUES - TBD]
│       ├── K1-010: Saga Pattern (ADR-0008)
│       └── K1-011: Circuit Breaker (ADR-0009)
│
├── Milestone 2 (Weeks 3-4) — Capability-Based Security [OUTLINE ONLY]
│   ├── Epic 2.1: Capability & Privacy (K1-012 to K1-014)
│   └── Epic 2.2: Serialization (K1-015 to K1-017)
│
├── Milestone 3 (Weeks 5-6) — SessionState & Storage [OUTLINE ONLY]
│   └── Epic 3.1: SessionState Management (K1-018 to K1-020)
│
├── Milestone 4 (Weeks 7-8) — Performance & Infrastructure [OUTLINE ONLY]
│   └── Epic 4.1: Performance Budgets & Observability (K1-021 to K1-023)
│
└── Milestone 5 (Weeks 9-12) — External Systems & Voice [OUTLINE ONLY]
    ├── Epic 5.1: K0 Integration & APIs (K1-024 to K1-026)
    └── Epic 5.2: Voice & Advanced Features (K1-027 to K1-029)
```

---

## Issue Structure (Per Issue)

Each issue in the roadmap includes:

```yaml
issue_X_X_X:
  id: "K1-NNN"                          # Issue ID (K1-001, K1-002, etc)
  title: "Title (ADR-ref)"              # Issue title with primary ADR
  description: |
    Detailed description of what needs to be done,
    why it matters, and what it enables downstream.
  
  adr_refs:                             # Primary ADRs (1+)
    - "ADR-NNNN"
    - "ADR-NNNNa"
  
  adr_chain:                            # Dependency chain (e.g., 0005→0005a-e)
    "ADR-NNNN → ADR-NNNNa + ADR-NNNNb"
  
  contract_refs:                        # Contract files (1+, PRIMARY marked)
    - "contracts/path/to/file.md (PRIMARY)"
    - "contracts/path/to/other.yaml"
  
  diagram_refs:                         # Architecture diagrams
    - "architecture_diagrams/xxx.mmd"
  
  whiteboard_section:                   # Reference to docs/whiteboard.md
    "2.1-Section, 2.2-Subsection"
  
  acceptance_criteria:                  # TESTABLE with WARD
    - "✅ Criterion 1"
    - "✅ WARD test: xxx passes"
  
  handoff_conditions:                   # Enable downstream work
    - "Component deployed"
    - "Tests passing"
    - "Documentation updated"
  
  depends_on:                           # Issues that must complete first
    - "K1-001"
    - "K1-003"
  
  verification_status:                  # Contract compliance tracking
    contract_status: "PRESENT|MISSING|PENDING"
    contract_refs_verified: [...]
    adr_status: "APPROVED|PROPOSED"
    adr_chain: [...]
    whiteboard_reference: "section"
    resolution_date: "YYYY-MM-DD"
    blocking_issues: []
  
  estimated_effort:
    hours: NN
    complexity: "HIGH|MEDIUM|LOW"
    risk: "HIGH|MEDIUM|LOW"
  
  owner: "Name"                         # RACI: Responsible
  reviewer: "Name"                      # RACI: Accountable
  
  phase: "Planning|Implementation|Testing"
  status: "NOT_STARTED|IN_PROGRESS|BLOCKED|COMPLETED"
```

---

## Key Conventions

### Naming
- **Issue ID:** `K1-NNN` (K1 = K1 kernel, NNN = sequential 001-999)
- **ADR Ref:** `ADR-NNNN` with chain notation `ADR-NNNN → ADR-NNNNa + ADR-NNNNb`
- **Contract Ref:** `contracts/path/to/contract.md` with `(PRIMARY)` marker

### Validation Rules (MANDATORY)
1. ✅ Every issue has `adr_refs` (minimum 1 ADR)
2. ✅ Every issue has `contract_refs` (minimum 1 contract)
3. ✅ No forward dependencies (`depends_on` must be completed first)
4. ✅ `acceptance_criteria` are TESTABLE with WARD framework
5. ✅ `handoff_conditions` enable downstream work

### ADR Traceability
- Each issue linked to 1-5 ADRs forming a decision chain
- Primary ADR in title, sub-ADRs in `adr_refs`
- ADR status tracked: "APPROVED" ≥ ready to code
- Sub-ADRs: `ADR-NNNN → ADR-NNNNa/NNNNb/NNNNc` (all must be referenced)

### Effort Estimation
- **hours:** Estimated development time (not including review/merge)
- **complexity:** HIGH (new design), MEDIUM (known pattern), LOW (straightforward)
- **risk:** HIGH (novel approach), MEDIUM (some uncertainty), LOW (well-understood)

---

## How to Complete Remaining Milestones

### For Epic 1.2-1.3 (within M1):
1. Read ADR-0005-0011 (Agent Lifecycle, Orchestration, Planning, Error Recovery)
2. Follow same template as K1-001 through K1-006
3. Estimate hours based on ADR complexity
4. Ensure all acceptance criteria testable with WARD

### For Milestone 2-5:
1. Group related ADRs into Epics (e.g., "Capability-Based Security" → ADR-0010, 0032-0038)
2. Create one issue per ADR or sub-ADR chain
3. Establish inter-issue dependencies via `depends_on`
4. Keep each issue focused (1-2 week effort)
5. Validate using Hierarchical Verification Loop (see ADR governance rules)

---

## Hierarchical Verification Loop (MANDATORY)

Before finalizing any roadmap item:

1. **Check Contract** → Reference contract ID in planning item
2. **If Contract Missing** → Check ADR & Sub-ADRs
3. **If ADR Missing** → Check docs/whiteboard.md
4. **If All Missing** → Create blocking issue with template
5. **Once Resolved** → Create ADR/Contract, then finalize roadmap item

See: docs/plan/PLAN-000_BOOTSTRAP.md for full details

---

## Cross-References

- **ADR Index:** docs/plan/ADR_INDEX.csv
- **Dependency Map:** docs/plan/DEPENDENCY_MAP.md
- **Component Connections:** docs/plan/COMPONENT_CONNECTIONS.md
- **MILESTONE 1 Summary:** docs/plan/MILESTONE_1_SUMMARY.md
- **Whiteboard Spec:** docs/whiteboard.md (21,123 lines)
- **Architecture Diagrams:** architecture_diagrams/ (11 Mermaid files)
- **Contracts:** contracts/ (52+ contract files)

---

## Next Steps

### Immediate (This Sprint)
1. ✅ Complete MILESTONE 1 Epic 1.1 (6 issues defined)
2. ⏳ Review & approve Epic 1.1 with stakeholders
3. ⏳ Begin implementation of K1-001 (K0/K1 Boundary)

### Week 2
4. ⏳ Complete Epic 1.2-1.3 issues (K1-007 through K1-011)
5. ⏳ Begin K0 Bridge implementation (K1-003)
6. ⏳ Finalize ADR governance (K1-002)

### Weeks 3-12
7. ⏳ Implement MILESTONE 2-5 sequentially
8. ⏳ Generate detailed issue definitions for each milestone
9. ⏳ Track progress against effort estimates

---

**Generated:** 2025-10-17  
**Format:** YAML with hierarchical validation  
**Version:** 1.0
