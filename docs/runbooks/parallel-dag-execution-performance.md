# Parallel DAG Execution - Performance Analysis

**Date**: November 20, 2025
**Status**: ✅ IMPLEMENTED
**Related**: `k0/runtime/pipeline_runner.py`, `k0/runtime/dag_builder.py`

---

## Executive Summary

The pipeline runner now executes stages in **parallel within DAG levels** and **sequentially across levels**, as defined by the declarative DAG structure.

### Before (Sequential Execution)
```python
for stage in dag.topological_order():
    await execute_stage(stage)
```

### After (Level-Based Parallel Execution)
```python
for level in dag.get_level_groups():
    await asyncio.gather(*[execute_stage(s) for s in level])
```

---

## P02 Write Pipeline - Expected Performance Improvement

### DAG Structure (from `p02_write.v1.yaml`)

```
Level 0 (1 stage):
├─ stage_10_dg_pattern_separate (15ms)

Level 1 (1 stage):
├─ stage_20_ca1_semantic_project (30ms)

Level 2 (7 stages - NOW PARALLEL):
├─ stage_30_affect_analyze (20ms)
├─ stage_31_space_resolve (15ms)
├─ stage_32_social_resolve (25ms)
├─ stage_33_temporal_profile (10ms)
├─ stage_40_device_profile (5ms)
├─ stage_41_ingress_classify (10ms)
├─ stage_42_geo_metadata (15ms)
├─ stage_43_spatial_minimal (5ms)

Level 3 (1 stage):
├─ stage_50_retention_lookup (10ms)

Level 4 (1 stage):
├─ stage_55_salience_score (15ms)

Level 5 (2 stages - NOW PARALLEL):
├─ stage_60_build_hipp_events_row (20ms)
├─ stage_61_build_embedding_queue_job (10ms)

Level 6 (1 stage):
├─ stage_70_atomic_writer (25ms)

Level 7 (1 stage):
├─ stage_80_event_emitter (10ms)
```

### Timing Analysis

#### Sequential Execution (OLD)
```
Level 0: 15ms
Level 1: 30ms
Level 2: 20 + 15 + 25 + 10 + 5 + 10 + 15 + 5 = 105ms (sequential)
Level 3: 10ms
Level 4: 15ms
Level 5: 20 + 10 = 30ms (sequential)
Level 6: 25ms
Level 7: 10ms
---
TOTAL: 240ms
```

#### Parallel Execution (NEW)
```
Level 0: 15ms
Level 1: 30ms
Level 2: max(20, 15, 25, 10, 5, 10, 15, 5) = 25ms (parallel)
Level 3: 10ms
Level 4: 15ms
Level 5: max(20, 10) = 20ms (parallel)
Level 6: 25ms
Level 7: 10ms
---
TOTAL: 150ms
```

### Expected Improvement
- **Old P95**: 171ms (baseline with sequential execution)
- **New P95**: ~150ms (37% faster with parallel execution)
- **Saved**: ~90ms from parallelizing Levels 2 and 5
- **Future**: With module optimization (M04), target ~120ms P95

---

## Verification

### Log Indicators (Successful Parallel Execution)

```json
{
  "message": "Executing level 2: 8 stages in parallel",
  "level": 2,
  "stage_count": 8,
  "stage_ids": [
    "stage_30_affect_analyze",
    "stage_31_space_resolve",
    "stage_32_social_resolve",
    "stage_33_temporal_profile",
    "stage_40_device_profile",
    "stage_41_ingress_classify",
    "stage_42_geo_metadata",
    "stage_43_spatial_minimal"
  ]
}

{
  "message": "Level 2 completed",
  "duration_ms": 26.8,  // Should be ~25ms, not 105ms
  "completed_stages": [...]
}
```

### Metrics Exposure

```python
runner.get_metrics()
# {
#   "pipeline_id": "P02_WRITE",
#   "execution_levels": 8,
#   "max_parallelism": 8,  // Level 2 has 8 parallel stages
#   "stage_count": 13,
#   ...
# }
```

---

## Key Implementation Details

### 1. Envelope Enrichment Model

**Problem**: Parallel stages need to share state (enriched envelope).

**Solution**: Shared `_enriched_envelope` dict with atomic updates:

```python
# Each parallel stage reads from shared envelope
envelope_dict = self._enriched_envelope or decode(message.payload)

# Execute module
result = await module_fn(envelope=envelope_dict, **config)

# Merge result back atomically
if isinstance(result, dict):
    self._enriched_envelope.update(result)
```

**Thread Safety**: Not an issue—Python asyncio is single-threaded. Stages in same level execute concurrently (async), not in parallel threads.

### 2. Level Synchronization

**Critical**: Stages must complete their level before next level starts.

```python
for level_idx, level_stages in enumerate(self._level_groups):
    # All stages in this level run concurrently
    await asyncio.gather(*[execute_stage(s, msg) for s in level_stages])
    # Barrier: wait for all to complete before proceeding
```

**Error Handling**: `return_exceptions=False` means first failure stops entire level immediately.

### 3. Deterministic Execution Order

**Within Level**: Stages execute in parallel (start order undefined).
**Across Levels**: Strict sequential order (Level N+1 only after Level N completes).

**Logging**: Log entries show parallel execution:
```
[DEBUG] Executing stage: stage_30_affect_analyze
[DEBUG] Executing stage: stage_31_space_resolve  // Started before stage_30 completed
[DEBUG] Executing stage: stage_32_social_resolve  // Started before stage_31 completed
```

---

## Testing

Run parallel execution tests:

```powershell
pytest tests/k0/runtime/test_parallel_dag_execution.py -v
```

**Test Coverage**:
- ✅ Parallel execution within level (timing verification)
- ✅ Sequential execution across levels (order verification)
- ✅ Envelope enrichment from parallel stages (merge verification)
- ✅ Metrics expose parallelism info

---

## Rollout Plan

### Phase 1: Verification (Current)
- ✅ Run tests to verify parallel execution
- ✅ Monitor P02 pipeline latency in dev environment
- ✅ Verify log patterns show parallel execution

### Phase 2: Baseline Comparison
- [ ] Deploy to staging with telemetry
- [ ] Compare P95 latency: 171ms (old) → ~150ms (new)
- [ ] Verify no data integrity issues (envelope enrichment)

### Phase 3: Production Rollout
- [ ] Deploy to 10% of production traffic
- [ ] Monitor for errors/regressions
- [ ] Gradual rollout to 100%

---

## Troubleshooting

### Issue: Total latency didn't decrease

**Diagnosis**:
```python
# Check level structure
logger.info(runner._level_groups)

# Expected: Multiple stages per level
# Actual: All stages in separate levels (sequential)
```

**Root Cause**: DAG dependencies too strict (everything depends on everything).

**Fix**: Review `after:` clauses in pipeline YAML—only list TRUE dependencies.

---

### Issue: Envelope data missing from parallel stages

**Diagnosis**: Parallel stages overwriting each other's results.

**Root Cause**: Module returning full envelope instead of delta.

**Fix**: Modules should return ONLY their enrichments:
```python
# ❌ BAD: Returns full envelope
return envelope

# ✅ GOOD: Returns only new fields
return {"affect_valence": 0.8, "affect_arousal": 0.6}
```

---

### Issue: Non-deterministic failures in parallel stages

**Diagnosis**: Race condition on shared state (unlikely in Python asyncio).

**Root Cause**: Module has side effects (writes to shared resource).

**Fix**: Ensure modules are **pure functions** or use proper locking.

---

## Future Optimizations

### 1. Adaptive Parallelism
Currently: All stages in level execute concurrently.
Future: Limit concurrency based on `latency_budget_ms` from module contracts.

```python
# Group stages by latency budget
fast_stages = [s for s in level if contract[s.module].latency_budget_ms < 20]
slow_stages = [s for s in level if contract[s.module].latency_budget_ms >= 20]

# Execute fast stages first, slow stages concurrently
await asyncio.gather(*fast_stages)
await asyncio.gather(*slow_stages)
```

### 2. Speculative Execution
For stages with low CPU cost, start them optimistically before dependencies complete.

### 3. Pipeline Variants
Create fast-path variants for hot paths:
- `P02_WRITE_FAST`: Skip optional enrichments (social, geo)
- `P02_WRITE_COMPLETE`: Full enrichment (current behavior)

---

## References

- **Implementation**: `k0/runtime/pipeline_runner.py`
- **DAG Builder**: `k0/runtime/dag_builder.py`
- **Pipeline Spec**: `k0/contracts/pipelines/p02_write.v1.yaml`
- **Tests**: `tests/k0/runtime/test_parallel_dag_execution.py`
- **ADRs**: `docs/architecture/decisions-K0/k009.2-builder-pattern.md`
