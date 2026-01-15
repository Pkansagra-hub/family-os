# P03 Milestone Execution System — Guidelines

> **Purpose**: Enable AI agents to execute implementation plans without hallucination.
> **Principle**: If you can't link it, you can't claim it exists.

---

## 1. Document Hierarchy

```
TEMP_EXECUTION_DOCS/
├── 00_EXECUTION_GUIDELINES.md      # This file (read first)
├── 01_REPO_PATTERNS.md             # Code patterns, naming, imports (shared)
├── 02_VERIFICATION_COMMANDS.md     # How to verify work (shared)
├── M0_EXECUTION.md                 # Milestone 0 execution doc
├── M1_EXECUTION.md                 # Milestone 1 (reads M0 outputs)
├── M2_EXECUTION.md                 # ...and so on
└── ...
```

---

## 2. Milestone Execution Document Template

Each `MN_EXECUTION.md` has **6 Parts**:

### Part A: Context Foundation (BEFORE YOU START)
- What dossier sections apply
- What prior milestone outputs to use
- What existing code to reference (with hyperlinks)

### Part B: Repository Patterns (HOW WE DO THINGS HERE)
- Exact code snippets to copy/adapt
- Import patterns
- Naming conventions for this milestone's scope

### Part C: Scope Boundaries (WHAT TO DO / NOT DO)
- Files to create (exact paths)
- Files to modify (exact paths + what to change)
- Files to NEVER touch
- Out-of-scope items (defer to later milestone)

### Part D: Execution Checklist (THE WORK)
- Issue-by-issue breakdown
- Each issue has: inputs, outputs, verification step
- Dependencies between issues

### Part E: Outputs Manifest (WHAT WE PRODUCED)
- Every file created (with hyperlinks)
- Every file modified (with diff summary)
- Every decision made (with rationale)
- Registry updates completed

### Part F: Handoff to Next Milestone (WHAT M{N+1} CAN USE)
- Artifacts ready for consumption
- Import statements that now work
- Tables that now exist
- Topics that are now registered
- Known gaps deferred to future milestones

---

## 3. Anti-Hallucination Rules

### Rule 1: Path Verification
```
WRONG: "The envelope is in k0/runtime somewhere"
RIGHT: "The envelope is at [k0/runtime/p03/envelope.py](../../k0/runtime/p03/envelope.py)"
```

### Rule 2: Pattern Copying
```
WRONG: "Create a Pydantic model like usual"
RIGHT: "Copy pattern from [k0/feedback/envelope.py lines 15-45](../../k0/feedback/envelope.py#L15-L45)"
```

### Rule 3: Import Statements
```
WRONG: "Import the syscalls"
RIGHT: "from k0.kernel.syscalls import Syscalls  # see k0/kernel/syscalls.py"
```

### Rule 4: Schema Fields
```
WRONG: "Add the standard fields"
RIGHT: "Fields: tenant_id (TEXT NOT NULL), space_id (TEXT NOT NULL), created_at (BIGINT) — per st_epi pattern"
```

### Rule 5: Test Structure
```
WRONG: "Add tests"
RIGHT: "Create tests/k0/runtime/p03/test_envelope.py following pattern in tests/k0/uow/test_unit_of_work.py"
```

---

## 4. Verification Protocol

After each issue completion:

1. **Syntax Check**: `python -m py_compile <file>`
2. **Import Check**: `python -c "from <module> import <class>"`
3. **Test Run**: `python -m ward test --path tests/k0/<path>/`
4. **Governance Sync**: `python -m governance.k0.scripts.sync --report`

After each milestone completion:

1. **Full Test Suite**: `python -m ward test`
2. **Type Check**: `pyright k0/`
3. **Governance Sync**: Must show SYNCED
4. **Update M{N}_EXECUTION.md Part E and F**

---

## 5. Decision Recording Format

When a decision is made that's NOT in the original plan:

```markdown
### Decision: [Short Title]
- **Issue**: Which issue prompted this
- **Options Considered**: A, B, C
- **Chosen**: B
- **Rationale**: Why B over A and C
- **Recorded In**: Link to code comment or ADR
```

---

## 6. Hyperlink Format Standards

### Internal Repo Links (Relative)
```markdown
[k0/uow/unit_of_work.py](../../k0/uow/unit_of_work.py)
[Line 45-60](../../k0/uow/unit_of_work.py#L45-L60)
```

### Dossier Section Links
```markdown
[Dossier §4.2.1](../pipelines/P03_consolidation_dossier_v2.md#421-importance-scoring)
```

### Prior Milestone Links
```markdown
[M0 Output: Pipeline Contract](./M0_EXECUTION.md#part-e-outputs-manifest)
```

---

## 7. Milestone Dependency Chain

```
M0 (Governance) ──────────────────────────────────────────────────────────────►
     │ Produces: ADRs, Contracts, Registry entries
     ▼
M1 (Envelope/Runner) ─────────────────────────────────────────────────────────►
     │ Consumes: M0 contracts
     │ Produces: Envelope classes, SequentialRunner, Phase interface
     ▼
M2 (Storage) ─────────────────────────────────────────────────────────────────►
     │ Consumes: M0 contracts (table names), M1 envelope (field alignment)
     │ Produces: Alembic migrations, Table models
     ▼
M3 (Bus Wiring) ──────────────────────────────────────────────────────────────►
     │ Consumes: M0 topics, M1 runner, M2 tables
     │ Produces: Outbox integration, Cross-pipeline clients
     ▼
M4 (R1-R4 Cognition) ─────────────────────────────────────────────────────────►
     │ Consumes: M1 envelope, M2 tables, M3 bus
     │ Produces: ImportanceScorer, Clusterer, Deduplicator, KGConsolidator
     ▼
M5 (R6-R8 Finalize) ──────────────────────────────────────────────────────────►
     │ Consumes: M1-M4 all
     │ Produces: TruthWriter, EventEmitter, full pipeline
     ▼
M6 (Ops) ─────────────────────────────────────────────────────────────────────►
     │ Consumes: M1-M5 all
     │ Produces: Metrics, DLQ handling, Security, Performance tuning
     ▼
M7 (Learning) ────────────────────────────────────────────────────────────────►
     │ Consumes: M2 learning tables, M4 scorers, M6 observability
     │ Produces: Closed-loop feedback integration
     ▼
M8 (Dream/P06) ───────────────────────────────────────────────────────────────►
     │ Consumes: M1-M7 all
     │ Produces: R5 Dream phase, P06 active learning integration
```

---

## 8. File Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Execution Doc | `MN_EXECUTION.md` | `M0_EXECUTION.md` |
| Alembic Migration | `XXXX_st_<table>.py` | `0030_st_epi.py` |
| Module Contract | `<domain>.<module>.v1.yaml` | `consolidation.importance_scorer.v1.yaml` |
| Pipeline Contract | `p03_<variant>.v1.yaml` | `p03_consolidation.v1.yaml` |
| Event Schema | `p03_<event_type>.json` | `p03_consolidation_complete.json` |
| Test File | `test_<module>.py` | `test_envelope.py` |

---

## 9. Emergency Protocols

### If Governance Sync Shows DRIFT
1. STOP execution
2. Document drift in current milestone's Part E
3. Resolve before proceeding (update master registry OR code)

### If Tests Fail After Change
1. STOP execution
2. Do NOT proceed to next issue
3. Fix failing test or revert change
4. Document in Part E what happened

### If Pattern Not Found
1. STOP execution
2. Search repo for similar patterns
3. If none exist, document as "NEW PATTERN" decision
4. Get explicit approval before inventing

---

## 10. Checklist Before Starting Any Milestone

- [ ] Read `00_EXECUTION_GUIDELINES.md` (this file)
- [ ] Read `01_REPO_PATTERNS.md` (code patterns)
- [ ] Read prior milestone's Part F (handoff)
- [ ] Verify all Part F artifacts exist (click every link)
- [ ] Run governance sync (must be SYNCED)
- [ ] Run full test suite (must pass)

---

**Next Step**: Create `01_REPO_PATTERNS.md` with actual code snippets from this repo, then `M0_EXECUTION.md` template.
