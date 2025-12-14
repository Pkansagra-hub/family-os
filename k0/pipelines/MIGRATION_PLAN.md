# Pipeline Infrastructure Migration Plan

**Date:** November 14, 2025
**Status:** Preparation Phase
**Goal:** Transform current pipeline infrastructure to support declarative DAG-based execution

---

## Current State Analysis (Updated: November 15, 2025)

### 1. Pipeline Folder Structure

```
k0/pipelines/
├── __init__.py          # Exports: PipelineProtocol, PipelineContext, Pipeline
├── protocol.py          # Protocol definitions and dataclasses
├── loader.py            # Auto-discovery and validation system
├── README.md            # Authoritative pipeline development guide ✅
├── MIGRATION_PLAN.md    # This file
└── QUICK_REFERENCE.md   # Quick lookup for common patterns
```

### 2. Runtime Infrastructure (Phase 2 Complete ✅)

```
k0/runtime/
├── __init__.py          # Public API exports
├── module_registry.py   # Module discovery & lazy loading ✅
├── pipeline_runner.py   # Generic DAG executor (PipelineProtocol) ✅
├── dag_builder.py       # Topological sort, cycle detection ✅
├── schemas.py           # Pydantic models (ModuleContract, PipelineSpec) ✅
└── README.md            # Authoritative runtime guide ✅
```

### 3. Key Touchpoints (External Dependencies)

#### A. **k0/kernel/app.py** (Primary Integration) ✅

**Lines 488-527:** Pipeline lifecycle management

- Import: `from ..pipelines.loader import discover_and_boot_pipelines`
- Calls `discover_and_boot_pipelines()` during lifespan startup
- Stores pipelines in `app.state.pipelines`
- Calls `pipeline.on_shutdown()` during graceful shutdown
- **Status:** Working correctly with Python-based pipelines

#### B. **k0/bus/core.py** (Message Format) ✅ RESOLVED

**Lines 20-30:** Defines unified `BusMessage` dataclass

```python
@dataclass(slots=True, frozen=True)
class BusMessage:
    topic: str
    payload: bytes
    offset: int
    trace_id: str | None = None
    space_id: str | None = None
    metadata: dict | None = None
```

- **Status:** Consolidated in bus/core.py (Phase 1 complete)
- Imported by pipelines: `from k0.bus import BusMessage`

#### C. **k0/kernel/syscalls.py** (Capability Gating) ⚠️ INCOMPLETE

**Existing Methods:**

- ✅ `hipp_store_upsert()` - Write to st_hipp_store
- ✅ `working_memory_write()` - Write to working memory
- ✅ `query_embeddings()` - Query vector index

**Missing Methods (Required for P02):**

- ❌ `hipp_store_query()` - Query similar memories (pattern separation)
- ❌ `pipeline_check_processed()` - Check idempotency
- ❌ `pipeline_mark_processed()` - Record processing
- ❌ `pipeline_emit_status()` - Emit receipts

**Action Required:** Add 4 missing syscalls before P02 implementation

#### D. **Tests** ✅

- `tests/k0/pipelines/test_protocol.py` - Protocol interface tests
- `tests/k0/pipelines/test_loader.py` - Loader validation tests
- `tests/k0/kernel/test_app_pipeline_integration.py` - Kernel integration tests
- **Status:** All passing after Phase 1 & 2 bug fixes

---

## Current Pipeline Infrastructure Components

### Protocol Definition (`protocol.py`)

**Exports:**

1. **`BusMessage`** - Immutable message format (CONFLICT with bus/core.py)
2. **`PipelineContext`** - Startup context (syscalls, config, logger)
3. **`PipelineProtocol`** - Interface contract requiring:
   - 6 class properties: `pipeline_id`, `contract_version`, `declared_topics`, `concurrency`, `max_queue`, `required_caps`
   - 3 lifecycle methods: `on_startup()`, `on_shutdown()`, `handle()`
4. **`Pipeline`** - Alias for PipelineProtocol

### Auto-Discovery System (`loader.py`)

**Functions:**

1. **`discover_and_boot_pipelines()`** - Main entry point
   - Scans `k0/pipelines/p*.py` files
   - Validates against PipelineProtocol
   - Creates Syscalls adapters with required capabilities
   - Calls `pipeline.on_startup(ctx)`
   - Subscribes `pipeline.handle()` to declared topics
   - Returns dict of pipeline instances

2. **`_find_pipeline_class()`** - Finds class with `pipeline_id` attribute
3. **`_validate_contract()`** - Validates 6 properties + 3 methods

---

## Migration Strategy

### Phase 1: Resolve BusMessage Conflict ✅ COMPLETE

**Problem:** Two definitions of `BusMessage`

- `k0/bus/core.py` (4 fields) - Used by kernel
- `k0/pipelines/protocol.py` (6 fields) - Used by pipelines

**Solution Implemented:**

- ✅ Added `space_id` and `metadata` to `k0/bus/core.py::BusMessage`
- ✅ Removed duplicate from `k0/pipelines/protocol.py`
- ✅ Updated all imports: `from k0.bus import BusMessage`
- ✅ Tests updated and passing

**Date Completed:** November 14, 2025

### Phase 2: Add Runtime Layer ✅ COMPLETE

**Directory created:**

```
k0/runtime/
├── __init__.py            # Public API exports ✅
├── module_registry.py     # Contract loading, lazy module loading ✅
├── pipeline_runner.py     # DAG executor (PipelineProtocol) ✅
├── dag_builder.py         # Topological sort, cycle detection ✅
├── schemas.py             # Pydantic validation models ✅
└── README.md              # Authoritative runtime guide ✅
```

**Key Accomplishments:**

- ✅ ModuleRegistry loads YAML contracts from `k0/contracts/modules/`
- ✅ PipelineRunner implements PipelineProtocol (kernel compatible)
- ✅ DAG builder validates dependencies and detects cycles
- ✅ PipelineSpec.load() reads YAML specs
- ✅ Comprehensive README documentation
- ✅ All Phase 1 & 2 bugs fixed (6 critical bugs resolved)
- ✅ ModuleCallable signature corrected: `async def run(message, context, **config)`

**Date Completed:** November 15, 2025

**No changes to existing pipeline folder required** ✅

### Phase 3: Complete Syscalls Infrastructure ⚠️ IN PROGRESS

**Current Status:**

- ✅ `hipp_store_upsert()` exists (write to st_hipp_store)
- ✅ `working_memory_write()` exists
- ✅ `query_embeddings()` exists

**Required for P02 Pipeline:**

```python
# k0/kernel/syscalls.py - MUST ADD:

async def hipp_store_query(space_id, query_vector, top_k) -> list[dict]:
    """Query similar memories for pattern separation."""
    # Capability: st_hipp_store.read

async def pipeline_check_processed(pipeline_id, space_id, wal_pos) -> bool:
    """Check if already processed (idempotency)."""
    # Capability: pipeline.read

async def pipeline_mark_processed(pipeline_id, space_id, wal_pos) -> None:
    """Mark message as processed."""
    # Capability: pipeline.write

async def pipeline_emit_status(pipeline_id, wal_pos, status, ...) -> None:
    """Emit processing receipt."""
    # Capability: pipeline.write
```

**Storage Tables (Already Exist):**

- ✅ `st_hipp_store` - Migration 0006 (50+ columns including pattern separation fields)
- ✅ `st_pipeline_processed` - Migration 0012 (idempotency tracking)
- ✅ `st_pipeline_status` - Migration 0012 (receipts)
- ✅ `st_pipeline_watermarks` - Migration 0012 (compaction)

**Action Required:** Implement 4 missing syscalls before proceeding to Phase 4

**Estimated Time:** 1-2 hours

### Phase 4: Design P02 Pipeline Requirements 📋 BLOCKED

**CANNOT START until Phase 3 complete**

**Approach:**

1. Document P02 requirements (input/output/storage)
2. Identify minimum viable modules (2-3 modules)
3. Define module contracts (what each module does)
4. Map syscalls to module capabilities

**Example Design Document:**

```markdown
# P02 Write Pipeline Design

## Input
- Topic: cognitive.memory.write.committed.v1
- Payload: JSON envelope with text, space_id, event_id

## Required Modules (Minimal)
1. hippocampus.pattern_separate (novelty detection)
2. core.writer (persist to st_hipp_store)

## Storage Contracts
- Reads: st_hipp_store (recent memories)
- Writes: st_hipp_store, st_pipeline_processed, st_pipeline_status

## Syscalls Required
- hipp_store_query (pattern separation)
- hipp_store_upsert (storage)
- pipeline_mark_processed (idempotency)
- pipeline_emit_status (receipts)
```

**Estimated Time:** 2-3 hours for design + review

### Phase 5: Create Contract Definitions 📋 BLOCKED

**Create contracts directory structure:**

```bash
mkdir -p k0/contracts/modules
mkdir -p k0/contracts/pipelines
```

**Module Contracts (YAML):**

```
k0/contracts/modules/
├── hippocampus.pattern_separate.v1.yaml  # Novelty detection
├── core.writer.v1.yaml                   # Storage writer
└── ... (add modules as needed)
```

**Pipeline Specs (YAML):**

```
k0/contracts/pipelines/
├── p02_write.v1.yaml  # Declarative DAG spec
└── ... (future pipelines)
```

**Cannot proceed until:** Phase 3 & 4 complete

### Phase 6: Implement Module Library 🔨 BLOCKED

**Create modules directory:**

```
k0/modules/
├── __init__.py
├── hippocampus/
│   ├── __init__.py
│   └── pattern_separate.py  # async def run(message, context, **config)
└── core/
    ├── __init__.py
    └── writer.py             # async def run(message, context, **config)
```

**Module Implementation Pattern:**

```python
async def run(
    message: BusMessage,
    context: PipelineContext,
    **config: Any,
) -> dict[str, Any]:
    # Use context.syscalls for storage
    # Use context.logger for logging
    # Return enriched envelope
```

**Cannot proceed until:** Phase 3, 4, 5 complete

### Phase 7: Extend Loader for YAML Discovery 🔌 BLOCKED

**Modify `k0/pipelines/loader.py`:**

- Keep existing Python pipeline discovery (backward compatible)
- Add YAML spec discovery
- Instantiate PipelineRunner for YAML specs
- Initialize ModuleRegistry with contracts

**Implementation approach:**

```python
async def discover_and_boot_pipelines(...):
    pipelines = {}

    # EXISTING: Scan for p*.py files (Python pipelines)
    for py_file in pipeline_dir.glob("p[0-9]*.py"):
        pipeline = _load_python_pipeline(py_file)
        pipelines[pipeline.pipeline_id] = pipeline

    # NEW: Scan for YAML specs (declarative pipelines)
    module_registry = ModuleRegistry()
    await module_registry.load_contracts("k0/contracts/modules")

    for yaml_file in (project_root / "k0/contracts/pipelines").glob("*.yaml"):
        spec = PipelineSpec.load(yaml_file)
        runner = PipelineRunner(spec, module_registry)
        await runner.on_startup(ctx)
        pipelines[spec.pipeline_id] = runner

    return pipelines
```

**Cannot proceed until:** Phase 3-6 complete

---

## Benefits of This Approach

### 1. **Zero Breaking Changes**

- Existing kernel integration unchanged
- Tests continue to pass
- No refactoring of working code

### 2. **Incremental Migration**

- Add new infrastructure alongside existing
- Convert pipelines one at a time
- Both paradigms coexist during transition

### 3. **Clean Separation**

- `k0/pipelines/` = protocol + loader (infrastructure)
- `k0/runtime/` = execution engine (generic runner)
- `k0/modules/` = business logic (reusable components)
- `k0/contracts/` = wiring specifications (data)

### 4. **Future-Proof**

- Add 100+ modules without touching loader
- Add 20 pipelines without writing Python classes
- Generate diagrams from YAML specs
- Version contracts independently of code

---

## Critical Design Decisions

### Decision 1: Module Registry Location

**Recommendation:** `k0/runtime/module_registry.py`

- Single switchboard for all modules
- Loads contracts on startup
- Provides lookup: `get(module_id, version) → callable`

### Decision 2: Pipeline Runner Interface

**Recommendation:** Implement `PipelineProtocol`

- Runner acts as a pipeline from kernel's perspective
- Internally executes DAG stages
- Maintains compatibility with existing loader

### Decision 3: Contract Format

**Recommendation:** YAML with Pydantic validation

- Human-readable for review
- Strongly typed via Pydantic models
- Versionable in git
- Can generate JSON Schema for docs

### Decision 4: Module Implementation Pattern

**Recommendation:** Pure functions with dependency injection

```python
async def run(
    envelope: dict,
    syscalls: Syscalls,
    logger: Logger,
    config: dict
) -> dict:
    # Module logic here
    return enriched_envelope
```

---

## Migration Sequence (1 Developer) - UPDATED

### Week 1-2: Foundation ✅ COMPLETE

1. ✅ Resolved BusMessage conflict (November 14)
2. ✅ Created `k0/runtime/` structure
3. ✅ Defined schema models (ModuleContract, PipelineSpec)
4. ✅ Implemented ModuleRegistry (load + lookup)
5. ✅ Implemented PipelineRunner (DAG executor)
6. ✅ Implemented DAG builder (topological sort, cycle detection)
7. ✅ Fixed all Phase 1 & 2 bugs (6 critical bugs)
8. ✅ Created authoritative README documentation

**Completed:** November 15, 2025

### Week 3: Syscalls + P02 Design ⚠️ CURRENT PHASE

1. ⏳ Add 4 missing syscalls to `k0/kernel/syscalls.py` (1-2 hours)
   - `hipp_store_query()`
   - `pipeline_check_processed()`
   - `pipeline_mark_processed()`
   - `pipeline_emit_status()`
2. ⏳ Document P02 requirements (what modules needed) (2-3 hours)
3. ⏳ Create first 2 module contracts (YAML) (1-2 hours)
4. ⏳ Create P02 pipeline spec (YAML) (1 hour)

**Target Completion:** November 17-18, 2025

### Week 4: Implement P02 Golden Path

1. Create `k0/modules/hippocampus/` directory
2. Implement `pattern_separate.py` module (novelty detection)
3. Implement `core/writer.py` module (storage)
4. Extend loader to discover YAML specs
5. Test P02 end-to-end with envelope submission
6. Verify kernel boots with both Python + YAML pipelines
7. Performance testing (latency budgets)

**Target Completion:** November 22-25, 2025

### Week 5-6: Second Pipeline (Validate Reusability)

1. Design P01 or P03 pipeline
2. Reuse existing modules where possible
3. Implement 1-2 new modules
4. Validate module reusability benefit
5. Performance benchmarking
6. Documentation updates

**Target Completion:** December 1-6, 2025

### Week 7+: Scale & Production Hardening

1. Convert additional pipelines incrementally
2. Build module library organically (as needed)
3. Add monitoring/alerting for declarative pipelines
4. Create ADRs for design decisions
5. Consider deprecating Python-based pipelines (after 3+ declarative pipelines proven)

---

## Risk Mitigation

### Risk 1: BusMessage Schema Evolution

**Mitigation:** Add fields additively, never remove
**Test:** Comprehensive serialization tests

### Risk 2: Module Circular Dependencies

**Mitigation:** Modules are stateless, no cross-imports
**Validation:** DAG builder detects cycles

### Risk 3: Performance Regression

**Mitigation:** Benchmark each stage, set latency budgets
**Monitoring:** Per-module tracing in runner

### Risk 4: Contract/Code Drift

**Mitigation:** Contract validation in CI
**Tooling:** Auto-generate module stubs from contracts

---

## Success Metrics

**After Phase 1 (Foundation):** ✅ ACHIEVED

- ✅ Single BusMessage definition in `k0/bus/core.py`
- ✅ ModuleRegistry loads contracts successfully
- ✅ All tests pass (Python pipelines working)
- ✅ Kernel boots with 0 pipelines correctly
- ✅ Authoritative documentation complete

**After Phase 2 (Runtime Infrastructure):** ✅ ACHIEVED

- ✅ ModuleRegistry implements lazy loading
- ✅ PipelineRunner executes DAG in topological order
- ✅ DAG builder detects cycles
- ✅ PipelineSpec.load() reads YAML
- ✅ PipelineRunner implements PipelineProtocol
- ✅ All 6 critical bugs fixed
- ✅ ModuleCallable signature correct

**After Phase 3 (Syscalls Complete):** ⏳ IN PROGRESS

- [ ] 4 new syscalls implemented
- [ ] Syscalls tested in isolation
- [ ] Capability enforcement working
- [ ] Storage tables validated (st_hipp_store accessible)

**After Phase 4-7 (P02 Golden Path):** 🎯 TARGET

- [ ] P02 runs via declarative YAML spec
- [ ] 2-3 modules have contracts and implementations
- [ ] End-to-end envelope submission flows through P02 DAG
- [ ] Latency within budget (< 100ms P95)
- [ ] Kernel logs show: "Booted 1 pipelines: ['P02_WRITE']"
- [ ] Receipt emitted to st_pipeline_status
- [ ] Both Python and YAML pipelines coexist

**After Phase 8+ (Scale):** 🚀 FUTURE

- [ ] 3+ pipelines using declarative specs
- [ ] 10+ modules in library
- [ ] Module reuse demonstrated (same module in 2+ pipelines)
- [ ] Auto-generated system diagram from contracts
- [ ] Migration 0021 cleans up orphaned schema

---

## Files Requiring Modification

### Phase 1: Foundation ✅ COMPLETE

1. ✅ `k0/bus/core.py` - Added `space_id` and `metadata` to BusMessage
2. ✅ `k0/pipelines/protocol.py` - Removed duplicate BusMessage
3. ✅ `k0/pipelines/__init__.py` - Updated imports
4. ✅ `tests/k0/pipelines/test_protocol.py` - Updated imports

### Phase 2: Runtime Infrastructure ✅ COMPLETE

1. ✅ Created `k0/runtime/__init__.py`
2. ✅ Created `k0/runtime/module_registry.py`
3. ✅ Created `k0/runtime/pipeline_runner.py`
4. ✅ Created `k0/runtime/dag_builder.py`
5. ✅ Created `k0/runtime/schemas.py`
6. ✅ Created `k0/runtime/README.md`
7. ✅ Created `k0/pipelines/README.md`
8. ✅ Fixed ModuleCallable type hint in `module_registry.py`

### Phase 3: Syscalls ⏳ IN PROGRESS

1. ⏳ `k0/kernel/syscalls.py` - Add 4 new methods:
   - `hipp_store_query()`
   - `pipeline_check_processed()`
   - `pipeline_mark_processed()`
   - `pipeline_emit_status()`

### Phase 4-6: Contracts & Modules 📋 BLOCKED (waiting on Phase 3)

1. Create `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`
2. Create `k0/contracts/modules/core.writer.v1.yaml`
3. Create `k0/contracts/pipelines/p02_write.v1.yaml`
4. Create `k0/modules/hippocampus/__init__.py`
5. Create `k0/modules/hippocampus/pattern_separate.py`
6. Create `k0/modules/core/__init__.py`
7. Create `k0/modules/core/writer.py`

### Phase 7: Loader Extension 🔌 BLOCKED (waiting on Phase 4-6)

1. Modify `k0/pipelines/loader.py` - Add YAML spec discovery
2. No changes to `k0/kernel/app.py` (backward compatible ✅)

### Files Created (Complete)

- ✅ All files in `k0/runtime/` (6 files)
- ✅ Authoritative README documentation (2 files)
- ⏳ Files in `k0/modules/` (pending Phase 6)
- ⏳ Files in `k0/contracts/` (pending Phase 5)

---

## Validation Checklist

Before starting migration:

- [ ] All tests pass
- [ ] BusMessage conflict resolved
- [ ] Contract schemas defined
- [ ] Module registry interface agreed
- [ ] P02 pipeline spec drafted
- [ ] 5-7 module contracts drafted

During migration:

- [ ] Tests pass after each phase
- [ ] Kernel boots successfully
- [ ] No performance regression
- [ ] Observability maintained

After migration:

- [ ] Documentation updated
- [ ] Architecture diagrams regenerated
- [ ] Migration guide written
- [ ] Deprecation plan for Python pipelines

---

## Next Steps

**Immediate Action (Next 2 Hours):**

1. Resolve BusMessage conflict
2. Update all imports
3. Run test suite
4. Commit: "Consolidate BusMessage definition"

**Short Term (Next Week):**

1. Create `k0/runtime/` directory
2. Define Pydantic schemas
3. Implement ModuleRegistry skeleton
4. Write design doc for PipelineRunner

**Medium Term (2-3 Weeks):**

1. Draft P02 spec + module contracts
2. Implement first 3 modules
3. Extend loader for YAML support
4. Test P02 declarative execution

---

## Questions to Resolve

1. **Module naming convention?**
   - Recommendation: `<domain>.<action>` (e.g., `hippocampus.pattern_separate`)

2. **Contract versioning strategy?**
   - Recommendation: Semantic versioning in filename (`.v1.yaml`, `.v2.yaml`)

3. **Module error handling?**
   - Recommendation: Raise exceptions, runner handles retry/DLQ

4. **Config source for modules?**
   - Recommendation: Pass through PipelineContext, source from `k0/config/`

5. **Testing strategy for modules?**
   - Recommendation: Pure function tests, mock syscalls

---

## Current Status Summary

**Date:** November 15, 2025

**Completed Phases:**

- ✅ Phase 1: BusMessage consolidation (November 14)
- ✅ Phase 2: Runtime infrastructure (November 15)

**Current Phase:**

- ⏳ Phase 3: Syscalls completion (IN PROGRESS)
  - Blocker: 4 syscalls missing
  - Estimated: 1-2 hours to complete

**Next Phase:**

- 📋 Phase 4: P02 Design Document
  - Blocked by: Phase 3 completion
  - Estimated: 2-3 hours

**Critical Path:**

```
Phase 3 (Syscalls) → Phase 4 (Design) → Phase 5 (Contracts) →
Phase 6 (Modules) → Phase 7 (Loader) → P02 End-to-End Test
```

**Owner:** Single developer
**Timeline:**

- Phases 1-2: ✅ Complete (2 weeks)
- Phase 3: ⏳ 1-2 hours remaining
- Phases 4-7: 2-3 weeks estimated
- **Total:** 4-5 weeks for first declarative pipeline (P02)

**Blocker Status:**

- 🚫 BLOCKED: Cannot create modules until syscalls complete
- 🚫 BLOCKED: Cannot test P02 without storage access methods
- ✅ UNBLOCKED: Infrastructure (Phase 1-2) complete and validated

**Next Action:**
Implement 4 missing syscalls in `k0/kernel/syscalls.py`
