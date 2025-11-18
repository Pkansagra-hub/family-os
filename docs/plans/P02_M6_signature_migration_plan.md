# P02 Module Signature Migration Plan

**Status**: 🎯 Active
**Priority**: 🔴 Critical (Blocks M6 Integration Testing)
**Created**: 2025-11-17
**Owner**: Development Team
**Related**: Milestone 6.1.1 (P02 End-to-End Integration Tests)

---

## Executive Summary

### Problem Statement

**Discovered**: 2025-11-17 during P02 pipeline YAML validation

The P02 pipeline YAML (`k0/contracts/pipelines/p02_write.v1.yaml`) references 16 modules, but only **1 module (M01)** uses the Phase 2 runtime signature expected by `PipelineRunner`. The remaining **15 modules** use an incompatible legacy signature.

**Impact**: Pipeline execution will fail at runtime when `PipelineRunner` attempts to invoke modules M02, M04-M17.

### Signature Comparison

| Signature Type | Pattern | Modules | Status |
|----------------|---------|---------|--------|
| **Phase 2 (New)** | `async def run(message, context, **config)` | M01 only | ✅ Compatible |
| **Legacy (Old)** | `async def run(envelope: dict)` | M02, M04-M17 | ❌ Incompatible |

**Expected by PipelineRunner**:

```python
async def run(
    message: BusMessage,        # Incoming event with payload, trace_id, offset
    context: PipelineContext,   # Runtime context with syscalls, logger, config
    **config: Any               # Stage-specific configuration from pipeline YAML
) -> dict[str, Any]:            # Enriched envelope with module outputs
```

**Current Legacy Pattern**:

```python
async def run(envelope: dict[str, Any]) -> dict[str, Any]:
    # envelope = pre-parsed JSON from message.payload
    # No access to: trace_id, syscalls, logger, stage config
```

### Root Cause

M01 (hippocampus.pattern_separate) was recently refactored to Phase 2 signature during Milestone 4 implementation. Other modules were implemented earlier using the legacy signature and have not yet been migrated.

---

## Migration Strategy

### Option A: Runtime Adapter (Rejected for Production)

**Approach**: Add signature detection in `ModuleRegistry._load_implementation()` to automatically wrap legacy modules.

**Pros**:

- ✅ Zero module changes required
- ✅ Immediate unblocking for M6.1.1 tests
- ✅ Backward compatibility maintained

**Cons**:

- ❌ Hidden complexity in registry layer
- ❌ Performance overhead (signature inspection at load time)
- ❌ Debugging difficulty (adapter adds indirection)
- ❌ Technical debt (masks underlying problem)
- ❌ Modules cannot access `context.syscalls` or `context.logger`

**Decision**: **Rejected** — Adapter pattern acceptable for prototypes, but P02 is production code requiring clean architecture.

---

### Option B: Update All Modules (Selected)

**Approach**: Systematically migrate all 15 legacy modules to Phase 2 signature.

**Pros**:

- ✅ Clean, maintainable architecture
- ✅ Modules gain access to `context.syscalls`, `context.logger`, `trace_id`
- ✅ Stage-specific `**config` enables pipeline-level tuning
- ✅ No performance overhead
- ✅ Consistent with Phase 2 declarative architecture

**Cons**:

- ⚠️ Requires updating 15 modules (~30 min each = 7.5 hours total)
- ⚠️ Must update corresponding tests (another ~2 hours)

**Decision**: **Selected** — One-time investment (~10 hours) for long-term maintainability and architectural integrity.

---

## Implementation Plan

### Phase 1: Signature Migration (15 Modules)

**Duration**: 8-10 hours
**Parallelizable**: Yes (independent modules can be updated concurrently)

#### Module Groups

**Group 1: Hippocampus** (2 modules)

- ✅ M01: `hippocampus.pattern_separate` — Already migrated (Phase 2)
- ✅ M02: `hippocampus.semantic_project` — Already migrated (Phase 2)

**Group 2: Core Cognition** (3 modules)

- ❌ M04: `affect.analyze` — **PURE LEGACY - NEEDS MIGRATION**
- ⚠️ M05: `space.resolve_visibility` — **NEEDS MIGRATION** (import path issue in test)
- ⚠️ M07: `social.family_graph_resolve` — **PARTIAL - NEEDS REFINEMENT** (has **config, needs message/context)

**Group 3: Context Enrichment** (7 modules)

- ⚠️ M08: `context.temporal_profile` — **PARTIAL - NEEDS REFINEMENT** (custom params, needs message/context)
- ❌ M09: `context.device_profile` — **PURE LEGACY - NEEDS MIGRATION**
- ❌ M10: `context.ingress_classify` — **PURE LEGACY - NEEDS MIGRATION**
- ❌ M11: `context.retention_lookup` — **PURE LEGACY - NEEDS MIGRATION**
- ❌ M12: `context.geo_metadata` — **PURE LEGACY - NEEDS MIGRATION**
- ❌ M15: `context.spatial_minimal` — **PURE LEGACY - NEEDS MIGRATION**
- ❌ M06: `salience.score` — **PURE LEGACY - NEEDS MIGRATION**

**Group 4: Builders** (2 modules)

- ❌ M13: `builders.hipp_events_row` — **PURE LEGACY - NEEDS MIGRATION**
- ❌ M14: `builders.embedding_queue_write` — **PURE LEGACY - NEEDS MIGRATION**

**Group 5: Core I/O** (2 modules)

- ⚠️ M16: `core.hipp_events_writer` — **PARTIAL - NEEDS REFINEMENT** (has context optional, needs message required)
- ⚠️ M17: `core.event_emitter` — **PARTIAL - NEEDS REFINEMENT** (has context optional, needs message required)

**Migration Status Summary** (from signature analysis):

- ✅ **Complete**: 2 modules (M01, M02)
- ❌ **Pure Legacy**: 9 modules (M04, M06, M09-M15)
- ⚠️ **Partial**: 4 modules (M07, M08, M16, M17)
- **Total Requiring Work**: 13 modules

---

### Migration Template

**Before (Legacy)**:

```python
async def run(envelope: dict[str, Any]) -> dict[str, Any]:
    """Module entry point (legacy signature)."""
    # Extract data from envelope
    text = envelope.get("body", {}).get("text", "")

    # Process
    result = process_data(text)

    # Return enriched envelope
    return {**envelope, "module_output": result}
```

**After (Phase 2)**:

```python
async def run(
    message: Any,           # BusMessage with .payload, .trace_id, .offset
    context: Any,           # PipelineContext with .syscalls, .logger, .config
    **config: Any           # Stage-specific configuration from pipeline YAML
) -> dict[str, Any]:
    """Module entry point (Phase 2 signature)."""
    # Parse envelope from message
    import json
    envelope = (
        json.loads(message.payload)
        if isinstance(message.payload, (str, bytes))
        else message.payload
    )

    # Extract configuration (with defaults)
    param1 = config.get("param1", default_value)
    param2 = config.get("param2", default_value)

    # Log module start (structured logging)
    context.logger.debug(
        f"Module started: {__name__}",
        extra={
            "module": "domain.action",
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
        },
    )

    # Extract data from envelope
    text = envelope.get("body", {}).get("text", "")

    # Process (using config params)
    result = process_data(text, param1, param2)

    # Log completion
    context.logger.debug(
        f"Module completed: {__name__}",
        extra={
            "module": "domain.action",
            "trace_id": message.trace_id,
            "result_summary": str(result)[:100],
        },
    )

    # Return enriched envelope
    return {**envelope, "module_output": result}
```

---

### Migration Checklist (Per Module)

- [ ] **Update function signature**
  - Change `async def run(envelope: dict)` → `async def run(message, context, **config)`
  - Add type hints: `message: Any, context: Any, **config: Any`

- [ ] **Add envelope parsing**
  - Insert at function start:

    ```python
    import json
    envelope = (
        json.loads(message.payload)
        if isinstance(message.payload, (str, bytes))
        else message.payload
    )
    ```

- [ ] **Extract config parameters**
  - Replace hardcoded values with `config.get("param_name", default)`
  - Document expected config keys in docstring

- [ ] **Add structured logging**
  - Module start: `context.logger.debug("Module started: ...")`
  - Module end: `context.logger.debug("Module completed: ...")`
  - Errors: `context.logger.error("Module failed: ...", exc_info=True)`
  - Include `trace_id` in all log extras

- [ ] **Update docstring**
  - Document Args: `message`, `context`, `**config`
  - List expected config keys with defaults
  - Add "Contract:" reference to YAML file

- [ ] **Update tests**
  - Change test calls from `await run(envelope)` to `await run(message, context, **config)`
  - Create mock `message` object with `.payload`, `.trace_id`, `.offset`
  - Create mock `context` object with `.syscalls`, `.logger`, `.config`

- [ ] **Validate**
  - Run module tests: `pytest tests/k0/modules/<domain>/test_<action>.py -v`
  - Check no regression in functionality
  - Verify logging output includes trace_id

---

## Execution Order - Milestones, Epics, and Issues

### Milestone Structure

**Milestone 6.2: Phase 2 Signature Migration** (13 modules, 8-10 hours)

- Epic 6.2.1: Core Cognition Modules (3 modules)
- Epic 6.2.2: Context Enrichment Modules (7 modules)
- Epic 6.2.3: Builder Modules (2 modules)
- Epic 6.2.4: Core I/O Modules (2 modules)

---

### Epic 6.2.1: Core Cognition Module Migrations

**Goal**: Migrate M04, M07 to Phase 2 signature (M05 excluded - import path issue)
**Duration**: 1.5 hours
**Status**: 📝 Not Started

---

#### Issue 6.2.1.1: Migrate M04 (affect.analyze) to Phase 2 Signature

**Priority**: 🔴 Critical
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: dict[str, Any]) -> dict[str, Any]:
```

**Target Signature**:

```python
async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
```

**Tasks**:

- [ ] Update function signature to accept `message, context, **config`
- [ ] Add envelope parsing from `message.payload`
- [ ] Extract config parameters: `confidence_threshold` (default: 0.8)
- [ ] Add structured logging with `context.logger.debug()` at start/end
- [ ] Include `trace_id` in all log extras
- [ ] Update docstring with Phase 2 args documentation
- [ ] Update tests to pass `message, context, **config`
- [ ] Run tests: `pytest tests/k0/modules/affect/test_analyze.py -v`
- [ ] Verify 38/38 tests pass (no regression)

**Acceptance Criteria**:

- ✅ Signature matches Phase 2 template exactly
- ✅ All 38 module tests pass
- ✅ Performance tests pass (P95 <5ms maintained)
- ✅ Structured logging includes trace_id

**Estimated Time**: 30 minutes

---

#### Issue 6.2.1.2: Migrate M07 (social.family_graph_resolve) to Phase 2 Signature

**Priority**: 🔴 Critical
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature** (Partial Phase 2):

```python
async def run(envelope: Dict[str, Any], **config) -> Dict[str, Any]:
```

**Target Signature**:

```python
async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
```

**Tasks**:

- [ ] Update signature to add `message, context` parameters
- [ ] Add envelope parsing from `message.payload`
- [ ] Extract config: `cache_ttl_seconds`, `default_social_context`, `default_social_intimacy`, `max_participants_to_resolve`
- [ ] Add structured logging with `context.logger.debug()`
- [ ] Update docstring
- [ ] Update tests to pass `message, context`
- [ ] Run tests: `pytest tests/k0/modules/social/test_family_graph_resolve.py -v`
- [ ] Verify 40/40 tests pass

**Acceptance Criteria**:

- ✅ Signature matches Phase 2 template
- ✅ All 40 module tests pass
- ✅ Config parameters work from pipeline YAML
- ✅ Logging includes trace_id

**Estimated Time**: 30 minutes

---

### Epic 6.2.2: Context Enrichment Module Migrations

**Goal**: Migrate M06, M08, M09, M10, M11, M12, M15 to Phase 2 signature
**Duration**: 3.5 hours (7 modules × 30 min each)
**Status**: 📝 Not Started

---

#### Issue 6.2.2.1: Migrate M08 (context.temporal_profile) to Phase 2 Signature

**Priority**: 🟡 High
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature** (Custom):

```python
async def run(envelope: dict, write_time_utc: Optional[int] = None, ingested_at: Optional[int] = None) -> dict:
```

**Target Signature**:

```python
async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
```

**Tasks**:

- [ ] Replace custom params with `message, context, **config`
- [ ] Extract `write_time_utc`, `ingested_at` from envelope or config
- [ ] Add envelope parsing
- [ ] Extract config: `timezone_source` (default: "tenant_config")
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/context/test_temporal_profile.py -v`
- [ ] Verify 58/58 tests pass

**Acceptance Criteria**:

- ✅ All 58 tests pass
- ✅ P95 <4ms maintained

**Estimated Time**: 30 minutes

---

#### Issue 6.2.2.2: Migrate M09 (context.device_profile) to Phase 2 Signature

**Priority**: 🟡 High
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: Dict[str, Any]) -> Dict[str, Any]:
```

**Tasks**:

- [ ] Update to Phase 2 signature
- [ ] Add envelope parsing
- [ ] Extract config: `default_device_kind`, `supported_platforms`, `minimum_client_version`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/context/test_device_profile.py -v`
- [ ] Verify 48/48 tests pass

**Acceptance Criteria**:

- ✅ All 48 tests pass
- ✅ P95 <2ms maintained

**Estimated Time**: 30 minutes

---

#### Issue 6.2.2.3: Migrate M10 (context.ingress_classify) to Phase 2 Signature

**Priority**: 🟡 High
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: Dict[str, Any]) -> Dict[str, Any]:
```

**Tasks**:

- [ ] Update to Phase 2 signature
- [ ] Add envelope parsing
- [ ] Extract config: `default_activity_type`, `default_content_type`, `supported_ingress_topics`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/context/test_ingress_classify.py -v`
- [ ] Verify 50/50 tests pass

**Acceptance Criteria**:

- ✅ All 50 tests pass
- ✅ P95 <3ms maintained

**Estimated Time**: 30 minutes

---

#### Issue 6.2.2.4: Migrate M11 (context.retention_lookup) to Phase 2 Signature

**Priority**: 🟡 High
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: Dict[str, Any]) -> Dict[str, Any]:
```

**Tasks**:

- [ ] Update to Phase 2 signature
- [ ] Add envelope parsing
- [ ] Extract config: `default_retention_bucket`, `default_retention_days`, `cache_ttl_seconds`, `fallback_policy_chain`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/context/test_retention_lookup.py -v`
- [ ] Verify 38/38 tests pass

**Acceptance Criteria**:

- ✅ All 38 tests pass
- ✅ P95 <3ms maintained

**Estimated Time**: 30 minutes

---

#### Issue 6.2.2.5: Migrate M12 (context.geo_metadata) to Phase 2 Signature

**Priority**: 🟡 High
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: Dict[str, Any]) -> Dict[str, Any]:
```

**Tasks**:

- [ ] Update to Phase 2 signature
- [ ] Add envelope parsing
- [ ] Extract config: `default_location_type`, `default_geo_precision`, `validate_geohash_format`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/context/test_geo_metadata.py -v`
- [ ] Verify 36/36 tests pass

**Acceptance Criteria**:

- ✅ All 36 tests pass
- ✅ P95 <2ms maintained

**Estimated Time**: 30 minutes

---

#### Issue 6.2.2.6: Migrate M15 (context.spatial_minimal) to Phase 2 Signature

**Priority**: 🟡 High
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: Dict[str, Any]) -> Dict[str, Any]:
```

**Tasks**:

- [ ] Update to Phase 2 signature
- [ ] Add envelope parsing
- [ ] Extract config: `green_band_precision`, `amber_band_precision`, `red_band_precision`, `allow_null_location`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/context/test_spatial_minimal.py -v`
- [ ] Verify 34/34 tests pass

**Acceptance Criteria**:

- ✅ All 34 tests pass
- ✅ P95 <3ms maintained

**Estimated Time**: 30 minutes

---

#### Issue 6.2.2.7: Migrate M06 (salience.score) to Phase 2 Signature

**Priority**: 🟡 High
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: dict) -> dict:
```

**Tasks**:

- [ ] Update to Phase 2 signature
- [ ] Add envelope parsing
- [ ] Extract config: `social_weight`, `affect_weight`, `recency_weight`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/salience/test_score.py -v`
- [ ] Verify 57/57 tests pass

**Acceptance Criteria**:

- ✅ All 57 tests pass
- ✅ P95 <5ms maintained

**Estimated Time**: 30 minutes

---

### Epic 6.2.3: Builder Module Migrations

**Goal**: Migrate M13, M14 to Phase 2 signature
**Duration**: 1 hour (2 modules × 30 min each)
**Status**: 📝 Not Started

---

#### Issue 6.2.3.1: Migrate M13 (builders.hipp_events_row) to Phase 2 Signature

**Priority**: 🔴 Critical
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: Dict[str, Any]) -> Dict[str, Any]:
```

**Target Signature**:

```python
async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
```

**Tasks**:

- [ ] Update to Phase 2 signature
- [ ] Add envelope parsing
- [ ] Extract config: `validate_required_fields` (default: True)
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/builders/test_hipp_events_row.py -v`
- [ ] Verify 35/35 tests pass

**Acceptance Criteria**:

- ✅ All 35 tests pass
- ✅ P95 0.0195ms maintained (critical - row builder is fast path)

**Estimated Time**: 30 minutes

---

#### Issue 6.2.3.2: Migrate M14 (builders.embedding_queue_write) to Phase 2 Signature

**Priority**: 🔴 Critical
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature**:

```python
async def run(envelope: Dict[str, Any]) -> Dict[str, Any]:
```

**Target Signature**:

```python
async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
```

**Tasks**:

- [ ] Update to Phase 2 signature
- [ ] Add envelope parsing
- [ ] Extract config: `priority`, `model_id`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/builders/test_embedding_queue_write.py -v`
- [ ] Verify 28/28 tests pass

**Acceptance Criteria**:

- ✅ All 28 tests pass
- ✅ P95 0.0029ms maintained

**Estimated Time**: 30 minutes

---

### Epic 6.2.4: Core I/O Module Migrations

**Goal**: Migrate M16, M17 to Phase 2 signature (critical path - sequential)
**Duration**: 1 hour (2 modules × 30 min each, sequential)
**Status**: 📝 Not Started

---

#### Issue 6.2.4.1: Migrate M16 (core.hipp_events_writer) to Phase 2 Signature

**Priority**: 🔴 Critical
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature** (Partial Phase 2):

```python
async def run(envelope: dict[str, Any], context: Any = None, **config: Any) -> dict[str, Any]:
```

**Target Signature**:

```python
async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
```

**Tasks**:

- [ ] Replace `envelope` parameter with `message`
- [ ] Make `context` required (remove `= None`)
- [ ] Add envelope parsing from `message.payload`
- [ ] Extract config: `batch_size`, `retry_backoff_ms`, `max_retry_attempts`
- [ ] Ensure syscalls accessed via `context.syscalls`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/core/test_hipp_events_writer.py -v`
- [ ] Verify 35/35 tests pass

**Acceptance Criteria**:

- ✅ All 35 tests pass
- ✅ P95 <1ms maintained (critical - atomic writer)
- ✅ Syscalls work correctly via context

**Estimated Time**: 30 minutes

---

#### Issue 6.2.4.2: Migrate M17 (core.event_emitter) to Phase 2 Signature

**Priority**: 🔴 Critical
**Size**: M (30 minutes)
**Status**: 📝 Not Started

**Current Signature** (Partial Phase 2):

```python
async def run(envelope: dict[str, Any], context: Any = None, **config: Any) -> dict[str, Any]:
```

**Target Signature**:

```python
async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
```

**Tasks**:

- [ ] Replace `envelope` parameter with `message`
- [ ] Make `context` required (remove `= None`)
- [ ] Add envelope parsing from `message.payload`
- [ ] Extract config: `enable_telemetry_event`, `batch_emit_enabled`
- [ ] Ensure syscalls accessed via `context.syscalls`
- [ ] Add structured logging
- [ ] Update tests
- [ ] Run tests: `pytest tests/k0/modules/core/test_event_emitter.py -v`
- [ ] Verify 32/32 tests pass

**Acceptance Criteria**:

- ✅ All 32 tests pass
- ✅ P95 <10ms maintained
- ✅ All 6 exit topics emitted correctly

**Estimated Time**: 30 minutes

---

### Total Migration Summary

| Epic | Modules | Issues | Duration | Status |
|------|---------|--------|----------|--------|
| 6.2.1: Core Cognition | 2 | 2 | 1 hour | 📝 Not Started |
| 6.2.2: Context Enrichment | 7 | 7 | 3.5 hours | 📝 Not Started |
| 6.2.3: Builders | 2 | 2 | 1 hour | 📝 Not Started |
| 6.2.4: Core I/O | 2 | 2 | 1 hour | 📝 Not Started |
| **TOTAL** | **13** | **13** | **6.5 hours** | |

**Notes**:

- Each issue MUST pass all module tests before being marked complete
- Performance tests (P95/P99) must be maintained within 10% of baseline
- M05 (space.resolve_visibility) excluded due to import path issue (separate fix needed)
- M01, M02 already complete (Phase 2 signature)

---

## Testing Strategy

### Per-Module Testing (Required for Each Issue)

**Test Execution Command Template**:

```bash
# Run module tests
pytest tests/k0/modules/<domain>/test_<action>.py -v

# Run with performance timing
pytest tests/k0/modules/<domain>/test_<action>.py -v -s

# Run with coverage
pytest tests/k0/modules/<domain>/test_<action>.py --cov=k0.modules.<domain>.<action> --cov-report=term
```

**Acceptance Checklist** (Must pass for each issue):

- [ ] All module unit tests pass (0 failures, 0 errors)
- [ ] Test count matches baseline (no tests accidentally removed)
- [ ] Performance tests pass (P95/P99 within 10% of baseline)
- [ ] No new warnings or deprecation messages
- [ ] Code coverage maintained or improved
- [ ] Module imports successfully: `python -c "from k0.modules.<domain>.<action> import run; print('✅ Import OK')"`

**Test Failure Protocol**:

1. **DO NOT PROCEED** to next issue if tests fail
2. Debug failure in isolation
3. Verify envelope parsing logic
4. Check config parameter extraction
5. Ensure trace_id propagation
6. Re-run tests until 100% pass
7. Document any test changes in commit message

### Epic-Level Integration Testing

After completing all issues in an epic, run combined test suite:

**Epic 6.2.1** (Core Cognition):

```bash
pytest tests/k0/modules/affect/ tests/k0/modules/social/ -v
# Expected: 78 tests passing (38 + 40)
```

**Epic 6.2.2** (Context Enrichment):

```bash
pytest tests/k0/modules/context/ tests/k0/modules/salience/ -v
# Expected: 281 tests passing (58+48+50+38+36+34+57)
```

**Epic 6.2.3** (Builders):

```bash
pytest tests/k0/modules/builders/ -v
# Expected: 63 tests passing (35 + 28)
```

**Epic 6.2.4** (Core I/O):

```bash
pytest tests/k0/modules/core/ -v
# Expected: 67 tests passing (35 + 32)
```

### Milestone-Level Validation

After completing Milestone 6.2 (all 13 issues):

**Full Regression Test**:

```bash
# Run ALL module tests
pytest tests/k0/modules/ -v --tb=short

# Expected: 489+ tests passing (baseline from Milestone 4)
# Allowed: Same or better pass rate (99.3%+ maintained)
```

**Pipeline Validation**:

```bash
# Validate P02 pipeline loads without errors
python validate_p02_pipeline.py

# Expected output:
# ✅ VALIDATION PASSED: All 16 modules exist
```

**Signature Validation**:

```bash
# Verify all modules use Phase 2 signature
python check_module_signatures.py

# Expected output:
# Phase 2 Modules: 15 (M01-M02, M04, M06-M17)
# Legacy Modules: 0
```

**Performance Baseline Check**:

```bash
# Run performance tests (if exist)
pytest tests/performance/ -v -s

# Compare P95/P99 against baseline from Milestone 4
# Allowed deviation: ±10% maximum
```

### Test Data Requirements

**Mock Objects for Tests** (create in test fixtures):

**Mock Message**:

```python
class MockMessage:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload) if isinstance(payload, dict) else payload
        self.trace_id = str(uuid.uuid4())
        self.offset = 12345
        self.topic = "cognitive.memory.write.committed.v1"
        self.space_id = "test_space"
        self.tenant_id = "test_tenant"
```

**Mock Context**:

```python
class MockContext:
    def __init__(self):
        self.logger = logging.getLogger("test")
        self.trace_id = str(uuid.uuid4())
        self.syscalls = MockSyscalls()  # If needed
        self.config = {}
```

**Test Envelope Template**:

```python
test_envelope = {
    "event_id": str(uuid.uuid4()),
    "tenant_id": "test_tenant",
    "space_id": "test_space",
    "body": {
        "text": "Test event for module validation",
        "participants": ["person_dad", "person_mom"],
    },
    "event_time_utc": int(datetime.now(UTC).timestamp() * 1000),
}
```

### Continuous Validation During Migration

After each issue completion:

1. **Commit Message Format**:

   ```
   feat(k0/m<XX>): migrate to Phase 2 signature

   - Update run() to accept message, context, **config
   - Add envelope parsing from message.payload
   - Extract config parameters: <list params>
   - Add structured logging with trace_id
   - Tests: <XX>/<XX> passing (maintained baseline)
   - Performance: P95 <XXms (no regression)

   Closes: Issue 6.2.X.Y
   Related: Milestone 6.2, Epic 6.2.X
   ```

2. **Git Tag** (optional, for milestone tracking):

   ```bash
   git tag -a "m6.2-epic<X>-complete" -m "Epic 6.2.<X> complete: <N> modules migrated"
   ```

3. **Progress Tracking**:
   - Update issue status in migration plan document
   - Update todo list in workspace
   - Log test results in PR description (if using PRs)

---

## Risk Assessment

### High Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Module behavior changes during migration | Medium | High | Run full test suite per module before/after |
| Performance regression | Low | Medium | Run performance tests, compare P95/P99 latencies |
| Breaking existing callers | Low | High | Grep for direct `run(envelope)` calls outside pipeline |

### Medium Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Config parameter naming conflicts | Medium | Low | Review pipeline YAML configs, ensure no collisions |
| Logging verbosity increase | High | Low | Use `context.logger.debug()` not `.info()` |
| Test fixture maintenance | Medium | Medium | Create shared test fixtures in `tests/fixtures/` |

---

## Success Criteria

### Module-Level Success

- ✅ All 15 modules use Phase 2 signature
- ✅ All module unit tests pass (539/543 or better)
- ✅ No performance regression (within 10% of baseline)
- ✅ Structured logging includes trace_id in all modules

### Pipeline-Level Success

- ✅ `PipelineSpec.load()` succeeds for p02_write.v1.yaml
- ✅ `ModuleRegistry` can load all 16 modules without errors
- ✅ P02 E2E integration test passes (M6.1.1)
- ✅ DAG execution completes all 16 stages successfully

---

## Rollback Plan

If migration causes critical issues:

1. **Immediate**: Revert commits for problematic modules
2. **Temporary**: Use Option A (adapter pattern) in `module_registry.py` to unblock testing
3. **Investigation**: Debug specific module failures in isolation
4. **Re-attempt**: Fix issues and re-migrate with updated checklist

---

## Timeline

**Milestone**: 6.2 - Phase 2 Signature Migration
**Start Date**: 2025-11-17 (today)
**Target Completion**: 2025-11-17 (same day, 6.5 hours)
**Total Issues**: 13 (one per module)

### Execution Timeline

| Epic | Issue | Module | Duration | Cumulative | Owner | Status |
|------|-------|--------|----------|------------|-------|--------|
| **6.2.1** | 6.2.1.1 | M04: affect.analyze | 30 min | 0.5h | TBD | 📝 Pending |
| **6.2.1** | 6.2.1.2 | M07: social.family_graph_resolve | 30 min | 1.0h | TBD | 📝 Pending |
| **6.2.2** | 6.2.2.1 | M08: context.temporal_profile | 30 min | 1.5h | TBD | 📝 Pending |
| **6.2.2** | 6.2.2.2 | M09: context.device_profile | 30 min | 2.0h | TBD | 📝 Pending |
| **6.2.2** | 6.2.2.3 | M10: context.ingress_classify | 30 min | 2.5h | TBD | 📝 Pending |
| **6.2.2** | 6.2.2.4 | M11: context.retention_lookup | 30 min | 3.0h | TBD | 📝 Pending |
| **6.2.2** | 6.2.2.5 | M12: context.geo_metadata | 30 min | 3.5h | TBD | 📝 Pending |
| **6.2.2** | 6.2.2.6 | M15: context.spatial_minimal | 30 min | 4.0h | TBD | 📝 Pending |
| **6.2.2** | 6.2.2.7 | M06: salience.score | 30 min | 4.5h | TBD | 📝 Pending |
| **6.2.3** | 6.2.3.1 | M13: builders.hipp_events_row | 30 min | 5.0h | TBD | 📝 Pending |
| **6.2.3** | 6.2.3.2 | M14: builders.embedding_queue_write | 30 min | 5.5h | TBD | 📝 Pending |
| **6.2.4** | 6.2.4.1 | M16: core.hipp_events_writer | 30 min | 6.0h | TBD | 📝 Pending |
| **6.2.4** | 6.2.4.2 | M17: core.event_emitter | 30 min | 6.5h | TBD | 📝 Pending |

### Epic Completion Gates

**Epic 6.2.1 Complete** (1.0h):

- ✅ All Epic 6.2.1 issues closed (2/2)
- ✅ Combined test run: `pytest tests/k0/modules/affect/ tests/k0/modules/social/ -v`
- ✅ 78 total tests passing (38 + 40)

**Epic 6.2.2 Complete** (4.5h cumulative):

- ✅ All Epic 6.2.2 issues closed (7/7)
- ✅ Combined test run: `pytest tests/k0/modules/context/ tests/k0/modules/salience/ -v`
- ✅ 281 total tests passing (58+48+50+38+36+34+57)

**Epic 6.2.3 Complete** (5.5h cumulative):

- ✅ All Epic 6.2.3 issues closed (2/2)
- ✅ Combined test run: `pytest tests/k0/modules/builders/ -v`
- ✅ 63 total tests passing (35 + 28)

**Epic 6.2.4 Complete** (6.5h cumulative):

- ✅ All Epic 6.2.4 issues closed (2/2)
- ✅ Combined test run: `pytest tests/k0/modules/core/ -v`
- ✅ 67 total tests passing (35 + 32)

**Milestone 6.2 Complete**:

- ✅ All 4 epics complete (13/13 issues)
- ✅ Full regression test: `pytest tests/k0/modules/ -v` (489 tests minimum)
- ✅ Pipeline validation: `python validate_p02_pipeline.py`
- ✅ Signature check: `python check_module_signatures.py` (15/15 Phase 2)
- ✅ Performance check: All P95/P99 within 10% of baseline
- ✅ Documentation updated: Module READMEs reflect Phase 2 signature

### Parallel Execution Strategy (Optional)

If multiple developers available, epics can be parallelized:

**Parallel Track A** (3.5 hours):

- Epic 6.2.2: Context Enrichment (7 modules)

**Parallel Track B** (1.5 hours):

- Epic 6.2.1: Core Cognition (2 modules)
- Epic 6.2.3: Builders (2 modules)

**Sequential Track C** (1 hour):

- Epic 6.2.4: Core I/O (2 modules) - Must be last (critical path)

**With 2 developers**: 4.5 hours total (Track A + Track C sequential)
**With 3 developers**: 3.5 hours total (all parallel, sync at end)

---

## Dependencies

**Blocks**:

- Milestone 6.1.1: P02 End-to-End Integration Tests
- Milestone 6.1.2: Contract Compliance Tests
- Milestone 6.2: Data Validation Tests

**Blocked By**:

- ✅ Milestone 4: Module Implementation (complete)
- ✅ Milestone 5: Syscalls Integration (complete)
- ✅ P02 Pipeline YAML created (complete)

---

## References

**Architecture Documents**:

- `k0/runtime/README.md` — Phase 2 runtime architecture
- `k0/runtime/pipeline_runner.py` — PipelineRunner implementation
- `k0/runtime/module_registry.py` — ModuleRegistry signature expectations
- `docs/plans/P02_implementation_plan.md` — Milestone 6 definition

**Related ADRs**:

- K003.1-K003.3: Hippocampus modules
- K004.1: Affect classification
- K005.1: Space resolution
- K007.1-K007.5: Context enrichment
- K008.1: Social graph resolution
- K009.1-K009.2: Builder pattern
- K010.1-K010.2: Core I/O

**Contracts**:

- `k0/contracts/modules/*.yaml` — All 16 module contracts
- `k0/contracts/pipelines/p02_write.v1.yaml` — P02 pipeline specification

---

## Notes

- **M01 Already Complete**: `hippocampus.pattern_separate` already uses Phase 2 signature (reference implementation)
- **No M03**: M03 (CA3 clustering) deferred to P03, not part of P02 pipeline
- **Backward Compatibility**: Legacy signature no longer supported after migration (breaking change)
- **Future Pipelines**: All new modules MUST use Phase 2 signature from day 1

---

**Status**: 🎯 Ready to Execute
**Next Action**: Begin Wave 1 (M02 migration)
