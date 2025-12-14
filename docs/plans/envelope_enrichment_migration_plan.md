# Envelope Enrichment Structure Migration Plan

**Status**: 📝 Planning
**Priority**: P1 (High - Blocks P03 Implementation)
**Scope**: Breaking architectural change
**Estimated Effort**: 3-5 days (16 modules + tests + validation)
**Target Completion**: Before P03 M0 Gate

---

## Executive Summary

**Problem**: P02 modules use flat envelope structure while event_emitter expects nested `enrichments` structure, causing 0 events to be emitted to st_outbox. This blocks event-driven architecture and will cause severe name collisions in P03.

**Solution**: Migrate all P02 modules (16 modules) to use nested enrichment structure under `envelope["enrichments"]["<module_name>"]`, providing clean namespace separation, provenance tracking, and inter-pipeline composability.

**Impact**:

- ✅ Fixes event emission (P02 completion events)
- ✅ Enables P03 to cleanly consume P02 outputs
- ✅ Prevents name collisions across 28+ P03 capabilities
- ✅ Provides clear module attribution and debugging
- ⚠️ Breaking change requires coordinated updates across 16 modules + storage layer

---

## Current State Analysis

### Working (Flat Pattern)

- ✅ 15 P02 modules return flat envelopes: `{**envelope, "affect_valence": 0.9, ...}`
- ✅ Storage layer (hipp_events_row, hipp_events_writer) reads flat structure
- ✅ Database writes succeed (80/80 events in st_hipp_events)
- ✅ Capability model enforced correctly

### Broken (Nested Pattern Expected)

- ❌ event_emitter expects `envelope["enrichments"]["affect_analyzer"]`
- ❌ 0 events in st_outbox (event emission silently skipped)
- ❌ No completion events for downstream consumers
- ❌ Observability gap (can't trace which module produced which data)

### Modules Affected (16 Total)

1. `hippocampus.pattern_separate` (M01) - DG pattern separation
2. `hippocampus.semantic_project` (M02) - CA1 knowledge graph
3. `affect.analyze` (M04) - Sentiment/emotion analysis
4. `space.resolve_visibility` (M05) - Space routing
5. `salience.score` (M06) - Importance scoring
6. `social.family_graph_resolve` (M07) - Social context
7. `context.temporal_profile` (M08) - Temporal enrichment
8. `context.device_profile` (M09) - Device metadata
9. `context.ingress_classify` (M10) - Activity classification
10. `context.retention_lookup` (M11) - Retention policy
11. `context.geo_metadata` (M12) - Geospatial data
12. `context.spatial_minimal` (M15) - Location resolution
13. `builders.hipp_events_row` (M14) - Row builder
14. `builders.embedding_queue_write` (M13) - Embedding writer
15. `core.hipp_events_writer` (M16) - Atomic writer
16. `core.event_emitter` (M17) - Event emission

---

## Target State Definition

### Nested Enrichment Structure

```python
envelope = {
    # Original envelope fields (unchanged)
    "header": {...},
    "body": {...},
    "metadata": {...},

    # NEW: Enrichments namespace
    "enrichments": {
        "hippocampus_pattern_separate": {
            "simhash_hex": "0a707eb7b16d307b",
            "minhash32": [...],
            "module_version": "v1",
            "execution_time_ms": 0.307
        },
        "hippocampus_semantic_project": {
            "embedding_id": "uuid",
            "entities_json": "[...]",
            "kg_triples_json": "[...]",
            "module_version": "v1",
            "execution_time_ms": 79.696
        },
        "affect_analyzer": {
            "valence": 0.9,
            "arousal": 0.5,
            "dominant_emotions": ["joy", "contentment"],
            "band": "GREEN",
            "clinical_safety_risk": false,
            "module_version": "v1",
            "execution_time_ms": 1.461
        },
        "salience_scorer": {
            "score": 0.5,
            "band": "MED",
            "reasons": ["Social context: moderate..."],
            "module_version": "v1",
            "execution_time_ms": 0.074
        },
        # ... other modules ...
    }
}
```

### Module Naming Convention

- Pattern: `{category}_{module_name}` (snake_case)
- Examples:
  - `hippocampus_pattern_separate` (not "dg_pattern_separate")
  - `hippocampus_semantic_project` (not "ca1_semantic_project")
  - `affect_analyzer` (not "affect.analyze")
  - `salience_scorer` (not "salience.score")
  - `space_resolver` (not "space.resolve_visibility")

### Output Schema Per Module

Each enrichment MUST include:

- `module_version`: str (e.g., "v1", "v2.1")
- `execution_time_ms`: float (for performance tracking)
- Module-specific fields (documented in module contract)

---

## Migration Phases

### Phase 1: Foundation (2-3 hours)

**Goal**: Update core infrastructure to support nested structure

**Tasks**:

1. Add helper functions to PipelineRunner for enrichment access
2. Update event_emitter to read nested structure (with flat fallback)
3. Add enrichment schema validation helpers
4. Update module contract templates

**Deliverables**:

- `k0/runtime/enrichment_helpers.py` - Utility functions
- Updated `k0/modules/core/event_emitter.py` - Dual-mode support
- Contract update guide in `docs/development/`

---

### Phase 2: Pilot Module Migration (4-6 hours)

**Goal**: Migrate 3 representative modules as proof-of-concept

**Pilot Modules**:

1. `affect.analyze` (M04) - Complex output, clinical safety integration
2. `salience.score` (M06) - Simple output, clear contract
3. `space.resolve_visibility` (M05) - Critical for events

**Tasks per Module**:

1. Update module `run()` to return nested structure
2. Update module contract YAML with output schema
3. Update module tests (unit + integration)
4. Verify no regressions in P02 pipeline

**Deliverables**:

- 3 migrated modules with tests passing
- Migration pattern documented
- Performance validated (no latency regression)

---

### Phase 3: Storage Layer Adaptation (3-4 hours)

**Goal**: Update builders to read nested structure (with flat fallback)

**Modules to Update**:

1. `builders.hipp_events_row` (M14) - Row assembly
2. `builders.embedding_queue_write` (M13) - Embedding writes
3. `core.hipp_events_writer` (M16) - Atomic commits

**Tasks**:

1. Add enrichment extraction helpers
2. Update column mappers to prefer nested, fallback to flat
3. Add validation for both patterns during transition
4. Update integration tests

**Deliverables**:

- Storage layer supports both patterns
- Tests validate backward compatibility
- Clear deprecation warnings for flat access

---

### Phase 4: Remaining Module Migration (6-8 hours)

**Goal**: Migrate remaining 13 modules in batches

**Batch 1: Hippocampus & Context (3 hours)**

- M01: hippocampus.pattern_separate
- M02: hippocampus.semantic_project
- M08: context.temporal_profile
- M09: context.device_profile
- M10: context.ingress_classify

**Batch 2: Context & Social (2 hours)**

- M07: social.family_graph_resolve
- M11: context.retention_lookup
- M12: context.geo_metadata
- M15: context.spatial_minimal

**Batch 3: Core Infrastructure (1 hour)**

- M16: core.hipp_events_writer (if not done in Phase 3)
- M13: builders.embedding_queue_write (if not done in Phase 3)
- M14: builders.hipp_events_row (if not done in Phase 3)

**Tasks per Batch**:

1. Migrate modules following pilot pattern
2. Update tests
3. Run P02 integration tests after each batch
4. Verify event emission working

**Deliverables**:

- All 16 modules migrated
- Full P02 test suite passing
- Event emission verified (events in st_outbox)

---

### Phase 5: Validation & Cleanup (2-3 hours)

**Goal**: Remove flat pattern support, full cutover

**Tasks**:

1. Remove flat field generation from all modules
2. Remove flat fallback logic from storage layer
3. Update all module contracts to enforce nested schema
4. Run full regression test suite
5. Update P02 dossier documentation
6. Update K0 architecture master

**Deliverables**:

- Clean nested-only implementation
- 100% test coverage maintained
- Documentation updated
- ADR created for migration

---

## Detailed Issue Breakdown

### Issue 0: Planning & Infrastructure (Priority: P0)

#### Task 0.1: Create Enrichment Helper Utilities

**File**: `k0/runtime/enrichment_helpers.py` (new)
**Effort**: 1 hour
**Description**: Create utility functions for enrichment access and validation

```python
def get_enrichment(envelope: dict, module_name: str, field: str, default=None):
    """Get enrichment value with fallback to flat structure."""

def set_enrichment(envelope: dict, module_name: str, data: dict):
    """Set enrichment in nested structure."""

def validate_enrichment_schema(enrichment: dict, required_fields: list):
    """Validate enrichment has required fields."""
```

#### Task 0.2: Update Module Contract Template

**File**: `docs/development/module_contract_template.md`
**Effort**: 30 minutes
**Description**: Update template to include enrichment output schema

#### Task 0.3: Create Migration Testing Checklist

**File**: `docs/development/enrichment_migration_checklist.md`
**Effort**: 30 minutes
**Description**: Per-module checklist for validation

---

### Issue 1: Event Emitter Fix (Priority: P0 - BLOCKER)

#### Task 1.1: Add Flat Fallback to Event Emitter

**File**: `k0/modules/core/event_emitter.py`
**Effort**: 2 hours
**Description**: Make event_emitter work with current flat structure immediately

**Changes**:

```python
# BEFORE (line 144-162):
enrichments = envelope.get("enrichments", {})
if not enrichments:
    return envelope  # Skips emission

# AFTER:
enrichments = envelope.get("enrichments", {})
if not enrichments:
    # Fallback: Build enrichments from flat structure
    enrichments = _extract_flat_enrichments(envelope)

def _extract_flat_enrichments(envelope: dict) -> dict:
    """Extract enrichments from flat envelope structure."""
    return {
        "affect_analyzer": {
            "valence": envelope.get("affect_valence"),
            "arousal": envelope.get("affect_arousal"),
            ...
        },
        "salience_scorer": {
            "score": envelope.get("salience_score"),
            ...
        }
        # ... extract all module outputs ...
    }
```

**Testing**:

- Run P02 pipeline with test envelopes
- Verify events appear in st_outbox
- Verify 6 events emitted per envelope

**Success Criteria**:

- ✅ st_outbox has >0 rows after envelope submission
- ✅ Events have correct topics and payloads
- ✅ No PermissionError raised

---

### Issue 2: Pilot Module - affect.analyze (Priority: P1)

#### Task 2.1: Update affect.analyze Output

**File**: `k0/modules/affect/analyze.py`
**Effort**: 1 hour
**Line**: 1050-1075

**Changes**:

```python
# BEFORE:
return {
    **envelope,
    "affect_valence": annotation.valence,
    "affect_arousal": annotation.arousal,
    ...
}

# AFTER:
return {
    **envelope,
    # Keep flat fields for backward compat (temporary)
    "affect_valence": annotation.valence,
    "affect_arousal": annotation.arousal,
    ...
    # NEW: Add nested structure
    "enrichments": {
        **envelope.get("enrichments", {}),
        "affect_analyzer": {
            "valence": annotation.valence,
            "arousal": annotation.arousal,
            "dominant_emotions": list(annotation.dominant_emotions),
            "band": final_affect_band,
            "band_reasons": final_band_reasons,
            "clinical_safety_risk": safety_risk,
            "clinical_safety_severity": safety_severity,
            "confidence": annotation.confidence,
            "tier": annotation.tier,
            "module_version": "v1",
            "execution_time_ms": 0.0,  # Will be set by PipelineRunner
        }
    }
}
```

#### Task 2.2: Update affect.analyze Contract

**File**: `k0/contracts/modules/affect.analyze.v1.yaml`
**Effort**: 30 minutes

#### Task 2.3: Update affect.analyze Tests

**File**: `tests/k0/modules/affect/test_analyze_full.py`
**Effort**: 1 hour
**Changes**: Add assertions for nested enrichments structure

---

### Issue 3: Pilot Module - salience.score (Priority: P1)

#### Task 3.1: Update salience.score Output

**File**: `k0/modules/salience/score.py`
**Effort**: 45 minutes

#### Task 3.2: Update salience.score Contract

**File**: `k0/contracts/modules/salience.score.v1.yaml`
**Effort**: 20 minutes

#### Task 3.3: Update salience.score Tests

**File**: `tests/k0/modules/salience/test_score_*.py`
**Effort**: 45 minutes

---

### Issue 4: Pilot Module - space.resolve_visibility (Priority: P1)

#### Task 4.1: Update space.resolve_visibility Output

**File**: `k0/modules/space/resolve_visibility.py`
**Effort**: 45 minutes

#### Task 4.2: Update space Contract

**File**: `k0/contracts/modules/space.resolve_visibility.v1.yaml`
**Effort**: 20 minutes

#### Task 4.3: Update space Tests

**File**: `tests/k0/modules/space/*.py`
**Effort**: 45 minutes

---

### Issue 5: Storage Layer Adaptation (Priority: P1)

#### Task 5.1: Update hipp_events_row Builder

**File**: `k0/modules/builders/hipp_events_row.py`
**Effort**: 2 hours
**Lines**: 100-550 (all mapper functions)

**Changes**: Add enrichment extraction with fallback

```python
# BEFORE:
def map_affect_salience_group(affect_output: dict, salience_output: dict):
    valence = affect_output.get("valence")  # Expects flat

# AFTER:
def map_affect_salience_group(affect_output: dict, salience_output: dict):
    # Try nested structure first
    affect_enrichment = affect_output.get("enrichments", {}).get("affect_analyzer")
    if affect_enrichment:
        valence = affect_enrichment.get("valence")
    else:
        # Fallback to flat (backward compat)
        valence = affect_output.get("affect_valence")
```

#### Task 5.2: Update embedding_queue_write

**File**: `k0/modules/builders/embedding_queue_write.py`
**Effort**: 1 hour

#### Task 5.3: Update hipp_events_writer

**File**: `k0/modules/core/hipp_events_writer.py`
**Effort**: 1 hour

#### Task 5.4: Integration Testing

**Effort**: 1 hour
**Test**: Run P02 with pilot modules + storage updates, verify database writes

---

### Issue 6-13: Remaining Module Migrations

Each following same pattern as Issues 2-4:

- Update module `run()` function
- Update module contract YAML
- Update module tests
- Effort: 30-60 minutes per module

**Issue 6**: hippocampus.pattern_separate (M01)
**Issue 7**: hippocampus.semantic_project (M02)
**Issue 8**: context.temporal_profile (M08)
**Issue 9**: context.device_profile (M09)
**Issue 10**: context.ingress_classify (M10)
**Issue 11**: social.family_graph_resolve (M07)
**Issue 12**: context.retention_lookup (M11)
**Issue 13**: context.geo_metadata (M12)
**Issue 14**: context.spatial_minimal (M15)

---

### Issue 15: Event Emitter Update (Priority: P1)

#### Task 15.1: Remove Flat Fallback Logic

**File**: `k0/modules/core/event_emitter.py`
**Effort**: 1 hour
**Description**: After all modules migrated, remove flat extraction and use nested exclusively

#### Task 15.2: Update Event Payloads

**Effort**: 1 hour
**Description**: Update event payload builders to use enrichment structure directly

---

### Issue 16: Phase 5 Cleanup (Priority: P2)

#### Task 16.1: Remove Flat Fields from Modules

**Effort**: 2 hours
**Description**: Remove backward-compat flat fields from all module outputs

#### Task 16.2: Remove Flat Fallback from Storage

**Effort**: 1 hour
**Description**: Remove fallback logic from hipp_events_row and other builders

#### Task 16.3: Schema Validation Enforcement

**Effort**: 1 hour
**Description**: Add Pydantic schema validation for enrichments

#### Task 16.4: Documentation Updates

**Effort**: 2 hours
**Files**:

- `docs/pipelines/P02_write_dossier.md`
- `k0/pipelines/k0_architecture_master.md`
- `k0/PIPELINE_PROCESS.md`

#### Task 16.5: Create ADR

**File**: `docs/architecture/decisions-K0/k009.md` (or next available)
**Effort**: 1 hour
**Title**: "ADR-k009: Nested Enrichment Structure for Module Outputs"

---

## Testing Strategy

### Unit Tests (Per Module)

```python
def test_module_returns_nested_enrichment():
    result = await module.run(message, context)
    assert "enrichments" in result
    assert "module_name" in result["enrichments"]
    assert "module_version" in result["enrichments"]["module_name"]
```

### Integration Tests (Per Phase)

```python
def test_p02_pipeline_with_nested_enrichments():
    # Submit envelope
    response = client.post("/k0/command.submit", json=envelope)

    # Check database
    row = db.query("SELECT * FROM st_hipp_events WHERE event_id = ?")
    assert row["affect_valence"] == 0.9

    # Check outbox
    events = db.query("SELECT * FROM st_outbox WHERE tenant_id = ?")
    assert len(events) == 6  # 6 completion events
```

### Regression Tests

- Full P02 pipeline with 10 diverse envelopes
- Verify latency not regressed (P95 <150ms)
- Verify all database columns populated
- Verify event emission working

### Performance Tests

- Benchmark envelope processing latency
- Target: <5% latency increase
- Profile memory usage (nested structure adds ~5-10% overhead)

---

## Rollback Plan

### Immediate Rollback (If Issue 1 Fails)

- Revert `event_emitter.py` changes
- Keep flat structure
- Event emission remains broken but storage works

### Phase Rollback (If Pilot Fails)

- Revert pilot modules (Issues 2-4)
- Keep Issue 1 fix (flat fallback in event_emitter)
- System functional with events emitting

### Full Rollback (If Phase 5 Fails)

- All modules support dual pattern (flat + nested)
- Can operate indefinitely in dual mode
- P03 can use nested, P02 consumers use flat

---

## Success Criteria

### Phase 1 Success

- ✅ event_emitter emits 6 events per envelope
- ✅ st_outbox has correct event counts
- ✅ No PermissionError or capability failures
- ✅ P02 pipeline latency <150ms P95

### Phase 2 Success

- ✅ 3 pilot modules return nested enrichments
- ✅ All unit tests passing
- ✅ Integration tests validate both flat and nested access
- ✅ No regression in database writes

### Phase 3 Success

- ✅ Storage layer reads nested with flat fallback
- ✅ All 80+ database columns populated correctly
- ✅ hipp_events_row tests passing

### Phase 4 Success

- ✅ All 16 modules migrated
- ✅ 100% test coverage maintained
- ✅ Full P02 regression suite passing

### Phase 5 Success

- ✅ Flat pattern removed
- ✅ Clean nested-only implementation
- ✅ Documentation complete
- ✅ ADR published
- ✅ P03 can begin implementation

---

## Risk Assessment

### High Risk

- **Storage layer breakage**: Mappers are complex, 90 columns
  - Mitigation: Extensive integration tests, gradual rollout
- **Performance regression**: Nested structure adds overhead
  - Mitigation: Benchmark each phase, optimize if needed

### Medium Risk

- **Test maintenance**: 16 modules × 5-10 tests each
  - Mitigation: Use test helpers, shared fixtures
- **Contract drift**: 16 contracts to update
  - Mitigation: Schema validation, contract linting

### Low Risk

- **Name collisions**: Already tracked in contracts
  - Mitigation: Naming convention enforced
- **Backward compat**: Dual pattern during transition
  - Mitigation: Deprecation warnings, clear timeline

---

## Timeline

| Phase | Duration | Dependencies | Deliverable |
|-------|----------|--------------|-------------|
| Phase 1 | 2-3 hours | None | Event emission working (flat fallback) |
| Phase 2 | 4-6 hours | Phase 1 | 3 pilot modules migrated |
| Phase 3 | 3-4 hours | Phase 2 | Storage layer dual-mode |
| Phase 4 | 6-8 hours | Phase 3 | All 16 modules migrated |
| Phase 5 | 2-3 hours | Phase 4 | Clean cutover, docs complete |
| **Total** | **17-24 hours** | | **Nested enrichments production-ready** |

**Recommended Schedule** (assuming 4 hour work sessions):

- Day 1: Phase 1 (Issue 0-1) - Foundation + event emission fix
- Day 2: Phase 2 (Issues 2-4) - Pilot modules
- Day 3: Phase 3 (Issue 5) - Storage layer
- Day 4: Phase 4 Part 1 (Issues 6-10) - Batch 1 modules
- Day 5: Phase 4 Part 2 (Issues 11-14) + Phase 5 (Issues 15-16) - Complete migration

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Create GitHub Issues** from each task above
3. **Set up feature branch**: `feature/nested-enrichments`
4. **Begin Phase 1**: Issue 0 (infrastructure) + Issue 1 (event emitter fix)
5. **Checkpoint after each phase**: Review metrics, tests, rollback readiness

---

## Appendix A: Module-to-Enrichment Name Mapping

| Module ID | Current Name | Enrichment Key | Priority |
|-----------|--------------|----------------|----------|
| M01 | hippocampus.pattern_separate | `hippocampus_pattern_separate` | P1 (Batch 1) |
| M02 | hippocampus.semantic_project | `hippocampus_semantic_project` | P1 (Batch 1) |
| M04 | affect.analyze | `affect_analyzer` | P0 (Pilot) |
| M05 | space.resolve_visibility | `space_resolver` | P0 (Pilot) |
| M06 | salience.score | `salience_scorer` | P0 (Pilot) |
| M07 | social.family_graph_resolve | `social_resolver` | P1 (Batch 2) |
| M08 | context.temporal_profile | `temporal_profiler` | P1 (Batch 1) |
| M09 | context.device_profile | `device_profiler` | P1 (Batch 1) |
| M10 | context.ingress_classify | `ingress_classifier` | P1 (Batch 1) |
| M11 | context.retention_lookup | `retention_policy` | P1 (Batch 2) |
| M12 | context.geo_metadata | `geo_metadata` | P1 (Batch 2) |
| M13 | builders.embedding_queue_write | `embedding_queue_writer` | P1 (Storage) |
| M14 | builders.hipp_events_row | `hipp_row_builder` | P1 (Storage) |
| M15 | context.spatial_minimal | `spatial_resolver` | P1 (Batch 2) |
| M16 | core.hipp_events_writer | `hipp_writer` | P1 (Storage) |
| M17 | core.event_emitter | `event_emitter` | P0 (Fix First) |

---

## Appendix B: Example Enrichment Schemas

### affect_analyzer

```yaml
type: object
required:
  - valence
  - arousal
  - dominant_emotions
  - band
  - module_version
properties:
  valence:
    type: number
    minimum: -1.0
    maximum: 1.0
  arousal:
    type: number
    minimum: 0.0
    maximum: 1.0
  dominant_emotions:
    type: array
    items:
      type: string
    maxItems: 3
  band:
    type: string
    enum: [GREEN, AMBER, RED]
  clinical_safety_risk:
    type: boolean
  clinical_safety_severity:
    type: string
    enum: [CRITICAL, HIGH, MEDIUM, LOW]
  module_version:
    type: string
  execution_time_ms:
    type: number
```

### salience_scorer

```yaml
type: object
required:
  - score
  - band
  - reasons
  - module_version
properties:
  score:
    type: number
    minimum: 0.0
    maximum: 1.0
  band:
    type: string
    enum: [HIGH, MED, LOW]
  reasons:
    type: array
    items:
      type: string
  module_version:
    type: string
  execution_time_ms:
    type: number
```

---

**Document Version**: 1.0
**Last Updated**: 2025-12-12
**Author**: Intelligence Kernel Team
**Status**: Ready for Review


Create ADR for this architecture change (embedding inline vs async)
Add embedding.extract_from_cache:v1 module to P02 pipeline
Replace embedding_queue_write:v1 with direct embedding_write:v1
Keep P08 for backfill/batch operations only
Update P03 dossier to reflect synchronous embedding availability
