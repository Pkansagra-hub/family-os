# K0 Modules - Reusable Pipeline Building Blocks

**Status**: Phase 2 Complete ✅ | 16 modules operational in P02_WRITE pipeline

---

## Overview

The `k0/modules/` directory contains **pure function modules** that are composed into declarative pipeline DAGs. Each module performs one specific enrichment operation on episodic memory events.

**Key Principle:**
> Modules are stateless pure functions called by PipelineRunner. No cross-module dependencies, no shared state, capability-gated storage access.

---

## Module Architecture

### Function Signature (Standard)

```python
async def run(message: Any, context: Any, **config) -> dict[str, Any]:
    """
    Module entry point.

    Args:
        message: BusMessage with envelope payload and metadata
        context: PipelineContext with logger, syscalls, trace_id
        **config: Stage-specific configuration from pipeline YAML

    Returns:
        Enriched envelope dict (adds fields, never removes)

    Raises:
        ValueError: If envelope malformed or required data missing
    """
    # 1. Parse envelope
    envelope = getattr(message, "envelope", None) or json.loads(message.payload)

    # 2. Extract config
    threshold = config.get("threshold", 0.7)

    # 3. Process (using context.syscalls for storage if needed)
    result = await context.syscalls.some_query(...)

    # 4. Enrich envelope
    enriched = {
        **envelope,
        "my_module_output": {
            "field1": result,
            "computed_at": time.time(),
        }
    }

    # 5. Log completion
    context.logger.info("Module complete", extra={"trace_id": message.trace_id})

    return enriched
```

### Module Characteristics

✅ **Pure Function** - No class state, no singletons, no global variables
✅ **Idempotent** - Can be called multiple times with same result
✅ **Fast** - Respect latency budget from contract (typically 5-50ms)
✅ **Isolated** - Use `context.syscalls` for storage, `context.logger` for logging
✅ **Enrichment-Only** - Add fields to envelope, never remove or mutate existing
✅ **Error Handling** - Raise exceptions for validation errors, retry for transient failures

---

## Directory Structure

```
k0/modules/
├── README.md (this file)
├── module_development_guidelines.md (detailed dev guide)
├── hippocampus/          # Episodic memory functions
│   ├── __init__.py
│   ├── pattern_separate.py    # M01: SimHash/MinHash fingerprinting
│   └── semantic_project.py    # M02: Entity extraction + embedding
├── affect/               # Emotional analysis
│   ├── __init__.py
│   └── analyze.py             # M04: Valence/arousal/sentiment
├── space/               # Multi-tenancy & visibility
│   ├── __init__.py
│   └── resolve_visibility.py  # M05: owner_id, ACLs
├── salience/            # Importance scoring
│   ├── __init__.py
│   └── score.py               # M06: Salience computation
├── social/              # Family graph & relationships
│   ├── __init__.py
│   └── family_graph_resolve.py # M07: Participant roles
├── context/             # Contextual enrichment
│   ├── __init__.py
│   ├── temporal_profile.py    # M08: 11 temporal columns
│   ├── device_profile.py      # M09: Device metadata
│   ├── ingress_classify.py    # M10: Activity/content type
│   ├── retention_lookup.py    # M11: Retention policy
│   ├── geo_metadata.py        # M12: Geolocation
│   └── spatial_minimal.py     # M15: Privacy-preserving location
├── builders/            # Data assembly
│   ├── __init__.py
│   ├── hipp_events_row.py     # M13: 70+ column row builder
│   └── embedding_queue_write.py # M14: Vector job queue
└── core/                # Storage I/O
    ├── __init__.py
    ├── hipp_events_writer.py  # M16: st_hipp_events INSERT
    └── event_emitter.py       # M17: Event bus emissions
```

---

## Module Categories

### 1. Hippocampus Domain (Episodic Memory)

**M01: `hippocampus.pattern_separate`** (15ms budget)
- Computes SimHash (64-bit) and MinHash (32 permutations)
- Used for duplicate detection and similarity clustering
- Pure CPU-bound, no storage access
- **Output**: `simhash_hex`, `minhash32`, `fingerprint_computed_at_utc`

**M02: `hippocampus.semantic_project`** (50ms budget)
- Entity extraction (NER), triple generation (KG), embedding creation
- Generates `embedding_id` for vector search
- **Capabilities**: `st_embeddings.write`
- **Output**: `embedding_id`, `entities_json`, `kg_triples_json`

### 2. Affect Domain (Emotional Analysis)

**M04: `affect.analyze`** (25ms budget)
- Valence/arousal computation, sentiment classification
- Emotion detection (joy, sadness, anger, etc.)
- **Output**: `affect_valence`, `affect_arousal`, `sentiment`, `emotions_json`

### 3. Space Domain (Multi-Tenancy)

**M05: `space.resolve_visibility`** (10ms budget)
- Determines `owner_id`, ACL rules, visibility scope
- **Capabilities**: `st_space.read`
- **Output**: `owner_id`, `visible_to`, `visibility_scope`, `co_owners`

### 4. Salience Domain (Importance)

**M06: `salience.score`** (20ms budget)
- Computes importance score (0.0-1.0) based on multi-factor analysis
- Assigns salience band (CRITICAL/HIGH/MEDIUM/LOW)
- **Output**: `salience_score`, `salience_band`, `salience_reasons`

### 5. Social Domain (Relationships)

**M07: `social.family_graph_resolve`** (15ms budget)
- Resolves participant roles, relationships, intimacy levels
- **Capabilities**: `st_family_graph.read`
- **Output**: `social_context`, `participant_roles`, `intimacy_level`

### 6. Context Domain (Enrichment)

**M08: `context.temporal_profile`** (10ms budget)
- 11 temporal columns (event_time_utc, local_date, day_of_week, etc.)
- **Output**: `event_time_utc`, `local_date`, `local_time`, `time_zone`, etc.

**M09: `context.device_profile`** (5ms budget)
- Device metadata (kind, OS, client version)
- **Output**: `device_kind`, `device_os`, `client_version`

**M10: `context.ingress_classify`** (10ms budget)
- Activity type, content type classification
- **Output**: `activity_type`, `content_type`, `ingress_topic`

**M11: `context.retention_lookup`** (10ms budget)
- Retention policy assignment
- **Capabilities**: `st_retention_policy.read`
- **Output**: `retention_policy_id`, `retention_bucket`

**M12: `context.geo_metadata`** (15ms budget)
- Geolocation enrichment (geohash, location name)
- **Output**: `geohash_6`, `location_name`, `geo_precision_external`

**M15: `context.spatial_minimal`** (5ms budget)
- Privacy-preserving location truncation
- **Output**: `geohash_6` (truncated)

### 7. Builders Domain (Assembly)

**M13: `builders.hipp_events_row`** (10ms budget)
- Assembles complete 70+ column st_hipp_events row from all enrichments
- Maps 13 module outputs to table schema
- **Output**: `hipp_events_row` (dict with 70+ columns)

**M14: `builders.embedding_queue_write`** (5ms budget)
- Prepares vector generation job for P08 pipeline
- **Output**: `embedding_queue_entry`

### 8. Core Domain (Storage I/O)

**M16: `core.hipp_events_writer`** (25ms budget)
- Atomic 2-table INSERT (st_hipp_events + st_pipeline_processed)
- Extracts row from M13's `hipp_events_row` key
- **Capabilities**: `st_hipp_events.write`, `st_pipeline_processed.write`
- **Output**: `hipp_events_upsert` status

**M17: `core.event_emitter`** (10ms budget)
- Emits 6 enrichment completion events to internal bus
- **Capabilities**: `st_outbox.write`
- **Output**: Event emission receipts

---

## P02_WRITE Pipeline Integration

**Pipeline Spec**: `k0/contracts/pipelines/p02_write.v1.yaml`

**Execution Order** (16 stages, topologically sorted):

```
Stage 10: hippocampus.pattern_separate     → simhash, minhash
Stage 20: hippocampus.semantic_project     → embedding_id, entities
Stage 30: affect.analyze                   → valence, arousal
Stage 31: space.resolve_visibility         → owner_id, ACLs
Stage 32: social.family_graph_resolve      → social context
Stage 33: context.temporal_profile         → 11 temporal columns
Stage 40: context.device_profile           → device metadata
Stage 41: context.ingress_classify         → activity type
Stage 42: context.geo_metadata             → geolocation
Stage 43: context.spatial_minimal          → privacy location
Stage 50: context.retention_lookup         → retention policy
Stage 55: salience.score                   → importance score
Stage 60: builders.hipp_events_row         → 70+ column assembly
Stage 61: builders.embedding_queue_write   → vector job prep
Stage 70: core.hipp_events_writer          → atomic INSERT
Stage 80: core.event_emitter               → event emissions
```

**Result**: Complete enriched event in `st_hipp_events` with 70+ populated columns ✅

---

## Creating a New Module

### Step 1: Create Contract YAML

**Location**: `k0/contracts/modules/<module_id>.v<version>.yaml`

**Example**: `k0/contracts/modules/affect.analyze.v1.yaml`

```yaml
module_id: affect.analyze
version: v1
input_event_types:
  - p02.write.requested.v1
output_event_types:
  - p02.affect.analyzed.v1
latency_budget_ms: 25
side_effects:
  - read:st_affect_models
idempotent: true
description: |
  Affect analysis module for emotional valence/arousal computation.
```

### Step 2: Create Module Implementation

**Location**: `k0/modules/<domain>/<action>.py`

**Example**: `k0/modules/affect/analyze.py`

```python
"""
M04: affect.analyze - Emotional Analysis (Phase 2)

Computes valence, arousal, sentiment, and emotion detection.

Performance target: ≤25ms P95
Contract: k0/contracts/modules/affect.analyze.v1.yaml
"""

import json
from typing import Any


async def run(message: Any, context: Any, **config) -> dict[str, Any]:
    """
    Affect analysis entry point.

    Args:
        message: BusMessage with envelope
        context: PipelineContext with logger, syscalls
        **config: confidence_threshold, emotion_model, etc.

    Returns:
        Enriched envelope with affect fields
    """
    # Parse envelope
    envelope = getattr(message, "envelope", None) or json.loads(message.payload)

    # Extract config
    confidence_threshold = config.get("confidence_threshold", 0.7)

    # Extract text
    text = envelope.get("text") or envelope.get("body", {}).get("text", "")

    # Compute affect (simplified example)
    valence = _compute_valence(text)
    arousal = _compute_arousal(text)
    sentiment = _classify_sentiment(valence)

    # Enrich envelope
    enriched = {
        **envelope,
        "affect_valence": valence,
        "affect_arousal": arousal,
        "sentiment": sentiment,
        "affect_confidence": 0.85,
        "affect_computed_at": time.time(),
    }

    context.logger.info(
        "Affect analysis complete",
        extra={
            "valence": valence,
            "arousal": arousal,
            "trace_id": message.trace_id,
        }
    )

    return enriched


def _compute_valence(text: str) -> float:
    """Compute emotional valence (-1.0 to 1.0)."""
    # Simplified placeholder
    return 0.5


def _compute_arousal(text: str) -> float:
    """Compute emotional arousal (0.0 to 1.0)."""
    return 0.6


def _classify_sentiment(valence: float) -> str:
    """Classify sentiment based on valence."""
    if valence > 0.3:
        return "POSITIVE"
    elif valence < -0.3:
        return "NEGATIVE"
    return "NEUTRAL"
```

### Step 3: Add to Pipeline YAML

**Location**: `k0/contracts/pipelines/p02_write.v1.yaml`

```yaml
dag:
  - id: stage_30_affect
    module: affect.analyze:v1
    after: [stage_20_semantic]
    config:
      confidence_threshold: 0.8
      emotion_model: "distilbert"
```

### Step 4: Restart Kernel

```bash
cd k0/deploy
./k0.ps1 up -Rebuild
```

Module is automatically loaded by `ModuleRegistry` at startup ✅

---

## Module Development Guidelines

### DO ✅

- Keep modules under 300 lines (single responsibility)
- Use `context.logger` for all logging (never `print()`)
- Use `context.syscalls` for storage (never direct DB access)
- Raise `ValueError` for validation errors (retryable by dispatcher)
- Return enriched envelope `{**envelope, "new_field": value}`
- Document performance budget in docstring
- Add type hints to function signature

### DON'T ❌

- Use class state or singletons
- Import other modules from `k0/modules/` (cross-dependencies)
- Mutate input envelope (create new dict instead)
- Use blocking I/O without `asyncio` (kills async runtime)
- Log PII at INFO level (use DEBUG + redaction)
- Catch all exceptions (let transient errors propagate for retry)

---

## Testing Modules

### Unit Test Pattern

```python
import pytest
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.modules.affect.analyze import run


@pytest.mark.asyncio
async def test_affect_analyze_module():
    # Arrange
    message = BusMessage(
        topic="memory.delta",
        payload=b'{"text": "I love sunny days!"}',
        offset=1,
        trace_id="test-trace",
    )
    context = PipelineContext(
        syscalls=mock_syscalls,
        config={},
        logger=mock_logger,
    )

    # Act
    result = await run(message, context, confidence_threshold=0.7)

    # Assert
    assert "affect_valence" in result
    assert result["affect_valence"] > 0  # Positive text
    assert result["sentiment"] == "POSITIVE"
```

### Integration Test (via PipelineRunner)

```python
@pytest.mark.asyncio
async def test_p02_pipeline_with_affect_module():
    # Load pipeline spec
    spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")
    registry = ModuleRegistry()
    await registry.load_contracts("k0/contracts/modules")

    runner = PipelineRunner(spec, registry)
    await runner.on_startup(context)

    # Submit message
    msg = BusMessage(topic="memory.delta", payload=envelope_json, offset=1)
    await runner.handle(msg)

    # Assert all stages completed
    assert len(runner._completed_stages) == 16
```

---

## Performance Monitoring

### Latency Budgets (by domain)

| Domain | Typical Budget | Critical Path? |
|--------|---------------|----------------|
| hippocampus | 15-50ms | Yes (M01, M02) |
| affect | 25ms | Yes (M04) |
| space | 10ms | Yes (M05) |
| salience | 20ms | No |
| social | 15ms | No |
| context | 5-15ms | Varies |
| builders | 5-10ms | Yes (M13) |
| core | 10-25ms | Yes (M16, M17) |

**Total P02 Pipeline**: ~200ms P95 (16 stages sequential)

### Metrics Collection

Modules emit metrics via `context.logger`:

```python
context.logger.info(
    "Module execution complete",
    extra={
        "module_id": "affect.analyze",
        "duration_ms": 23.5,
        "trace_id": message.trace_id,
    }
)
```

Aggregated by Grafana dashboards for P95/P99 latency tracking.

---

## Common Patterns

### Pattern 1: Envelope Parsing

```python
# Standard envelope extraction
envelope = getattr(message, "envelope", None)
if envelope is None:
    # Fallback for standalone testing
    envelope = json.loads(message.payload if isinstance(message.payload, (str, bytes)) else message.payload)
```

### Pattern 2: Configuration Extraction

```python
# Get config with defaults
threshold = config.get("threshold", 0.7)
model_name = config.get("model", "default")
max_results = config.get("max_results", 10)
```

### Pattern 3: Storage Query (Capability-Gated)

```python
# Use context.syscalls for storage access
results = await context.syscalls.hipp_store_query(
    space_id=envelope["space_id"],
    query_vector=embedding,
    top_k=10,
    cognitive_trace_id=message.trace_id,
)
```

### Pattern 4: Error Handling

```python
try:
    result = await _heavy_computation(text)
except ValueError as e:
    # Validation error - fail fast, no retry
    context.logger.error(f"Validation failed: {e}", extra={"trace_id": message.trace_id})
    raise
except Exception as e:
    # Transient error - let dispatcher retry
    context.logger.warning(f"Transient error, will retry: {e}", extra={"trace_id": message.trace_id})
    raise
```

### Pattern 5: Enrichment (Never Mutate)

```python
# ❌ WRONG - mutates input
envelope["new_field"] = value
return envelope

# ✅ CORRECT - creates new dict
return {**envelope, "new_field": value}
```

---

## Troubleshooting

### Module Not Loaded

**Error**: `ModuleNotFoundError: Module not found: affect.analyze:v1`

**Checklist**:
- [ ] Contract file exists: `k0/contracts/modules/affect.analyze.v1.yaml`
- [ ] Implementation file exists: `k0/modules/affect/analyze.py`
- [ ] Module has `run()` function with correct signature
- [ ] Directory has `__init__.py`: `k0/modules/affect/__init__.py`

### Module Load Failed

**Error**: `ModuleLoadError: Cannot import k0.modules.affect.analyze`

**Checklist**:
- [ ] No syntax errors in module file
- [ ] No circular imports
- [ ] All dependencies installed (check `requirements.txt`)
- [ ] `__init__.py` files present in all parent directories

### Pipeline Stage Failed

**Error**: Stage shows in `_failed_stages`, pipeline execution stops

**Debug Steps**:
1. Check kernel logs for exception traceback
2. Run module unit test in isolation
3. Verify envelope has required fields for module
4. Check `context.syscalls` capabilities match module contract

---

## Module Library Status

**Phase 2 Complete** ✅: 16 operational modules

**Modules Implemented**:
- ✅ M01-M02: Hippocampus (pattern separation, semantic projection)
- ✅ M04: Affect analysis
- ✅ M05: Space visibility
- ✅ M06: Salience scoring
- ✅ M07: Social graph
- ✅ M08-M12, M15: Context enrichment (6 modules)
- ✅ M13-M14: Builders (row assembly, queue write)
- ✅ M16-M17: Core I/O (writer, emitter)

**Future Modules** (Phase 3-5):
- M03: Policy stamp (PEP enforcement)
- M18-M20: Additional enrichment modules
- P03 modules: CA3 consolidation, clustering
- P08 modules: Vector generation pipeline

---

## Key Files

### Must Read Before Modifying

1. **`module_development_guidelines.md`** - Detailed development guide
2. **`k0/runtime/module_registry.py`** - Module discovery & lookup
3. **`k0/runtime/pipeline_runner.py`** - How modules are invoked
4. **`k0/contracts/modules/*.yaml`** - Module contracts (metadata)

### Related Documentation

1. **`k0/pipelines/README.md`** - Pipeline architecture
2. **`k0/runtime/README.md`** - Runtime execution engine
3. **`docs/pipelines/P02_data_schema.md`** - st_hipp_events schema
4. **Tests**: `tests/k0/modules/*/test_*.py`

---

## Design Principles

### 1. Pure Functions Over Classes
- Stateless, testable, composable
- No singletons, no class state

### 2. Enrichment-Only Philosophy
- Modules add fields, never remove or mutate
- Preserves full event history

### 3. Capability Security
- Storage access gated by `context.syscalls`
- Enforces least-privilege principle

### 4. Performance First
- Respect latency budgets from contracts
- Profile hot paths, optimize critical stages

### 5. Fail Fast
- Raise exceptions for validation errors
- Let dispatcher handle retries for transient failures

---

**For detailed development guidelines, see `module_development_guidelines.md`**
**For pipeline integration, see `k0/pipelines/README.md`**
**For runtime execution, see `k0/runtime/README.md`**
