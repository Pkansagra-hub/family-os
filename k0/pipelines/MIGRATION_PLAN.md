# Pipeline Infrastructure Migration Plan
**Date:** November 14, 2025
**Status:** Preparation Phase
**Goal:** Transform current pipeline infrastructure to support declarative DAG-based execution

---

## Current State Analysis

### 1. Pipeline Folder Structure
```
k0/pipelines/
├── __init__.py          # Exports: PipelineProtocol, BusMessage, PipelineContext, Pipeline
├── protocol.py          # Protocol definitions and dataclasses
├── loader.py            # Auto-discovery and validation system
├── whiteboard.md        # Design documentation
├── whiteboard_module.md # Module template documentation
├── P02_IMPLEMENTATION_GUIDE.md
└── pipeline_table.md
```

### 2. Key Touchpoints (External Dependencies)

#### A. **k0/kernel/app.py** (Primary Integration)
**Lines 488-527:** Pipeline lifecycle management
- Import: `from ..pipelines.loader import discover_and_boot_pipelines`
- Calls `discover_and_boot_pipelines()` during lifespan startup
- Stores pipelines in `app.state.pipelines`
- Calls `pipeline.on_shutdown()` during graceful shutdown

#### B. **k0/bus/core.py** (Message Format Conflict)
**Lines 20-26:** Defines `BusMessage` dataclass
```python
@dataclass(slots=True)
class BusMessage:
    topic: str
    payload: bytes
    offset: int
    trace_id: str | None = None
```

**CONFLICT:** `k0/pipelines/protocol.py` also defines `BusMessage` (lines 26-64)
- Pipeline version has: `space_id`, `metadata` (extra fields)
- Both are frozen dataclasses with slots
- **Resolution needed:** Consolidate to single definition

#### C. **k0/kernel/syscalls.py** (Capability Gating)
Referenced by loader for creating capability-gated storage adapters

#### D. **Tests** (2 test files)
- `tests/k0/pipelines/test_protocol.py` - Protocol interface tests
- `tests/k0/pipelines/test_loader.py` - Loader validation tests
- `tests/k0/kernel/test_app_pipeline_integration.py` - Kernel integration tests

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

### Phase 1: Resolve BusMessage Conflict ✅ PRIORITY

**Problem:** Two definitions of `BusMessage`
- `k0/bus/core.py` (4 fields) - Used by kernel
- `k0/pipelines/protocol.py` (6 fields) - Used by pipelines

**Solution Options:**
1. **Option A (Recommended):** Consolidate in `k0/bus/core.py`
   - Add `space_id` and `metadata` fields to bus version
   - Update pipeline protocol to import from bus
   - Maintains single source of truth

2. **Option B:** Keep separate but aligned
   - Pipeline version wraps/extends bus version
   - More complex, not recommended

**Action Items:**
- [ ] Add `space_id` and `metadata` to `k0/bus/core.py::BusMessage`
- [ ] Remove `BusMessage` from `k0/pipelines/protocol.py`
- [ ] Update imports: `from k0.bus import BusMessage`
- [ ] Update tests to use unified definition

### Phase 2: Add Runtime Layer (New Infrastructure)

**Create new directory:**
```
k0/runtime/
├── __init__.py
├── module_registry.py     # Load & lookup modules by ID
├── pipeline_runner.py     # Generic DAG executor
├── dag_builder.py         # Build DAG from YAML spec
└── schemas.py             # Pydantic models for contracts
```

**No changes to existing pipeline folder required**

### Phase 3: Add Contract Definitions (Data-Driven)

**Create contracts directory:**
```
k0/contracts/
├── modules/               # Module contracts (YAML)
│   ├── hippocampus.pattern_separate.v1.yaml
│   ├── affect.analyze.v1.yaml
│   ├── space.resolve_visibility.v1.yaml
│   └── ... (100+ modules)
└── pipelines/             # Pipeline specs (YAML)
    ├── p02_write.v1.yaml
    ├── p01_recall.v1.yaml
    ├── p03_consolidation.v1.yaml
    └── ... (20 pipelines)
```

### Phase 4: Create Module Library

**Create modules directory:**
```
k0/modules/               # Module implementations
├── __init__.py
├── hippocampus/
│   ├── __init__.py
│   └── pattern_separate.py
├── affect/
│   ├── __init__.py
│   └── analyze.py
├── space/
│   ├── __init__.py
│   └── resolve_visibility.py
└── core/
    ├── __init__.py
    └── writer.py
```

### Phase 5: Extend Loader (Backward Compatible)

**Modify `k0/pipelines/loader.py`:**
- Keep existing `discover_and_boot_pipelines()` function
- Add YAML spec loading alongside Python class scanning
- For YAML specs: instantiate `PipelineRunner` instead of custom class
- Maintain backward compatibility with Python-based pipelines

**Pseudo-code:**
```python
async def discover_and_boot_pipelines(...):
    pipelines = {}

    # EXISTING: Scan for p*.py files (custom Python pipelines)
    for py_file in pipeline_dir.glob("p*.py"):
        pipeline = _load_python_pipeline(py_file)
        pipelines[pipeline.pipeline_id] = pipeline

    # NEW: Scan for YAML specs (declarative pipelines)
    for yaml_file in (project_root / "k0/contracts/pipelines").glob("*.yaml"):
        spec = PipelineSpec.load(yaml_file)
        runner = PipelineRunner(spec, module_registry)
        pipelines[spec.pipeline_id] = runner

    return pipelines
```

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

## Migration Sequence (1 Developer)

### Week 1-2: Foundation
1. ✅ Resolve BusMessage conflict
2. Create `k0/runtime/` structure
3. Define schema models (ModuleContract, PipelineSpec)
4. Implement ModuleRegistry (load + lookup)

### Week 3-4: Golden Path (P02 Write)
1. Create P02 pipeline spec YAML
2. Create 5-7 module contract YAMLs
3. Implement module functions
4. Extend loader to support YAML specs
5. Test P02 end-to-end

### Week 5-6: Second Pipeline (P01 Recall)
1. Create P01 pipeline spec
2. Reuse existing modules where possible
3. Implement delta modules
4. Validate reusability benefit

### Week 7+: Scale
1. Convert remaining pipelines incrementally
2. Build module library organically
3. Deprecate Python-based pipelines over time

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

**After Phase 1 (Foundation):**
- [ ] Single BusMessage definition across codebase
- [ ] ModuleRegistry loads contracts successfully
- [ ] Tests pass without modification

**After Phase 2 (P02 Golden Path):**
- [ ] P02 runs via declarative spec
- [ ] All modules have contracts
- [ ] End-to-end trace shows DAG execution
- [ ] Latency within budget

**After Phase 3 (Scale):**
- [ ] 3+ pipelines using declarative specs
- [ ] 20+ modules in library
- [ ] Module reuse demonstrated (same module in 2+ pipelines)
- [ ] Auto-generated system diagram from contracts

---

## Files Requiring Modification

### Immediate (Phase 1):
1. ✅ `k0/bus/core.py` - Add fields to BusMessage
2. ✅ `k0/pipelines/protocol.py` - Remove BusMessage, import from bus
3. ✅ `k0/pipelines/__init__.py` - Update imports
4. ✅ `tests/k0/pipelines/test_protocol.py` - Update import

### Future (Phase 2+):
1. `k0/pipelines/loader.py` - Add YAML spec support
2. `k0/kernel/app.py` - No changes (backward compatible)

### New Files:
- All files in `k0/runtime/`, `k0/modules/`, `k0/contracts/`

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

**Status:** Ready for Phase 1 implementation
**Blocker:** None (BusMessage conflict is addressable)
**Owner:** Single developer (you)
**Timeline:** 6-8 weeks for full migration
