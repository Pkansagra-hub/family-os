# K0 Runtime - Declarative Pipeline Execution Engine

**Authoritative Source of Truth for Declarative DAG-Based Pipelines**

---

## Overview

The `k0/runtime/` directory contains the **execution engine** for declarative YAML-based pipelines. This infrastructure enables pipelines to be defined as **DAGs of reusable modules** rather than monolithic Python classes.

**Key Principle:**
> Pipelines are declarative DAGs over a small module library. Everything else is data, not custom glue code.

---

## Architecture

### System Components

```
k0/runtime/
├── __init__.py          # Public API: ModuleRegistry, PipelineRunner, schemas, DAG
├── schemas.py           # Pydantic models (ModuleContract, PipelineSpec, StageSpec)
├── module_registry.py   # Load & lookup modules by ID (switchboard)
├── pipeline_runner.py   # Generic DAG executor (implements PipelineProtocol)
├── dag_builder.py       # Build topologically sorted execution graph
└── README.md            # This file - authoritative guide
```

### Integration with Pipelines

**Current State:** Core runtime infrastructure complete ✅
- `ModuleRegistry` loads contracts from `k0/contracts/modules/*.yaml`
- `PipelineRunner` implements `PipelineProtocol` for kernel compatibility
- `DAG` builder validates dependencies and computes execution order
- Pydantic schemas validate YAML specs at startup

**Loader Integration** (Phase 3-5): 🚧 In Progress
- Loader extended to discover YAML specs in `k0/contracts/pipelines/`
- Both Python and YAML pipelines coexist
- Modules implemented in `k0/modules/<domain>/<action>.py`

---

## Core Concepts

### 1. Module Registry

**Purpose:** Central switchboard for module discovery and lookup

**Responsibilities:**
1. Load module contracts from `k0/contracts/modules/*.yaml`
2. Validate contract schemas (Pydantic)
3. Provide lookup by `module_id:version`
4. Lazy load module implementations from `k0/modules/`
5. Track module metadata for observability

**Usage:**
```python
from k0.runtime import ModuleRegistry
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext

# Initialize registry
registry = ModuleRegistry()
await registry.load_contracts("k0/contracts/modules")

# Get module implementation
module_fn = registry.get("hippocampus.pattern_separate:v1")

# Prepare arguments
message = BusMessage(topic="memory.delta", payload=b'{...}', offset=1)
context = PipelineContext(syscalls=syscalls, config={}, logger=logger)

# Call module with correct signature
result = await module_fn(message=message, context=context, novelty_threshold=0.7)

# Get module contract (metadata)
contract = registry.get_contract("hippocampus.pattern_separate:v1")
print(f"Latency budget: {contract.latency_budget_ms}ms")
```

**Module Lookup Convention:**
- Module ID: `hippocampus.pattern_separate:v1`
- Import path: `k0.modules.hippocampus.pattern_separate`
- Function: `pattern_separate.run()`

### 2. Pipeline Runner

**Purpose:** Generic executor for declarative YAML-based pipelines

**Implements:** `PipelineProtocol` (for kernel compatibility)

**Execution Model:**
1. Load `PipelineSpec` from YAML
2. Build DAG using `dag_builder.build_dag()`
3. On message arrival: Execute stages in topological order
4. Lookup module implementations via `ModuleRegistry`
5. Pass `BusMessage` + `PipelineContext` to each module
6. Track completion state, emit receipts, log telemetry

**Usage:**
```python
from k0.runtime import PipelineRunner, ModuleRegistry

# Load pipeline spec
spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")

# Create runner
registry = ModuleRegistry()
await registry.load_contracts("k0/contracts/modules")
runner = PipelineRunner(spec, registry)

# Integrate with kernel (implements PipelineProtocol)
await runner.on_startup(context)
await runner.handle(bus_message)
await runner.on_shutdown()
```

### 3. DAG Builder

**Purpose:** Construct topologically sorted execution graph from pipeline specs

**Validation:**
- All dependencies exist
- No cycles (raises `DAGCycleError`)
- Deterministic ordering

**Execution Modes:**
- **Sequential:** `dag.topological_order()` → list of stages
- **Parallel:** `dag.get_level_groups()` → list of stage groups per level

**Usage:**
```python
from k0.runtime import build_dag

# Build DAG from spec
dag = build_dag(pipeline_spec)

# Sequential execution
for stage in dag.topological_order():
    await execute_stage(stage)

# Parallel execution (future)
for level_group in dag.get_level_groups():
    await asyncio.gather(*[execute_stage(s) for s in level_group])
```

### 4. Schemas (Pydantic Models)

**Purpose:** Validate YAML specs at load time

**Models:**
- `ModuleContract` - Module metadata (latency budget, side effects, idempotency)
- `PipelineSpec` - Pipeline DAG specification
- `StageSpec` - Individual DAG stage (module invocation)
- `PipelineExecutionState` - Runtime execution tracking

**Validation:**
- Pattern matching (e.g., `module_id` must be `domain.action`)
- Dependency checks (all `stage.after` references exist)
- Cycle detection (topological sort simulation)
- Side effect format (`operation:resource`)

---

## How to Create a Module

### Step 1: Create Module Contract

**Location:** `k0/contracts/modules/<module_id>.v<version>.yaml`

**Example:** `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`

```yaml
module_id: hippocampus.pattern_separate
version: v1
input_event_types:
  - p02.write.requested.v1
output_event_types:
  - p02.hippocampus.pattern_separated.v1
latency_budget_ms: 15
side_effects:
  - read:st_hipp_store
  - write:st_hipp_store
idempotent: true
failure_modes:
  - code: NOVELTY_SCORE_MISSING
    policy: drop
description: |
  Pattern separation module for episodic memory encoding.
  Computes novelty scores and similarity clusters.
```

**Required Fields:**
- `module_id` - Pattern: `domain.action` (e.g., `hippocampus.pattern_separate`)
- `version` - Pattern: `v[0-9]+` (e.g., `v1`, `v2`)
- `latency_budget_ms` - P95 latency budget (1-10000ms)
- `idempotent` - Can module be safely retried?

**Optional Fields:**
- `input_event_types` - Input schemas
- `output_event_types` - Output schemas
- `side_effects` - Storage operations (`read:table`, `write:table`, `emit:topic`)
- `failure_modes` - Known error codes and handling policies
- `description` - Human-readable description

### Step 2: Implement Module Function

**Location:** `k0/modules/<domain>/<action>.py`

**Convention:**
- Module ID: `hippocampus.pattern_separate:v1`
- Import path: `k0.modules.hippocampus.pattern_separate`
- Function name: `run()`

**Example:** `k0/modules/hippocampus/pattern_separate.py`

```python
"""
Hippocampus Pattern Separation Module

Performs pattern separation on episodic memory events by:
1. Computing novelty scores against existing memory
2. Identifying similar memory clusters
3. Separating orthogonal representations
"""

from __future__ import annotations

import logging
from typing import Any

from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext

logger = logging.getLogger(__name__)


async def run(
    message: BusMessage,
    context: PipelineContext,
    **config: Any,
) -> dict[str, Any]:
    """
    Execute pattern separation on incoming memory event.

    Args:
        message: Incoming BusMessage with memory.delta event
        context: PipelineContext with syscalls, logger, config
        **config: Stage-specific configuration overrides

    Returns:
        Enriched envelope with pattern separation metadata

    Raises:
        ValueError: If novelty score cannot be computed
    """
    # Parse envelope
    import json
    envelope = json.loads(message.payload)

    # Extract configuration
    novelty_threshold = config.get("novelty_threshold", 0.7)

    # Query similar memories (read capability)
    similar_memories = await context.syscalls.hipp_store_query(
        space_id=envelope["space_id"],
        query_vector=envelope.get("embedding"),
        top_k=10,
    )

    # Compute novelty score
    novelty_score = _compute_novelty(envelope, similar_memories)

    # Enrich envelope
    enriched = {
        **envelope,
        "pattern_separated": {
            "novelty_score": novelty_score,
            "similar_memory_count": len(similar_memories),
            "is_novel": novelty_score > novelty_threshold,
            "module_version": "v1",
        }
    }

    context.logger.info(
        f"Pattern separation complete: novelty={novelty_score:.3f}",
        extra={
            "module": "hippocampus.pattern_separate",
            "novelty_score": novelty_score,
            "trace_id": message.trace_id,
        },
    )

    return enriched


def _compute_novelty(envelope: dict, similar_memories: list) -> float:
    """Compute novelty score based on similar memories."""
    if not similar_memories:
        return 1.0  # Completely novel

    # Average similarity of top matches
    similarities = [m["similarity"] for m in similar_memories[:3]]
    avg_similarity = sum(similarities) / len(similarities)

    # Novelty is inverse of similarity
    return 1.0 - avg_similarity
```

**Module Function Signature:**
```python
async def run(
    message: BusMessage,      # Incoming event
    context: PipelineContext, # Syscalls, logger, config
    **config: Any,            # Stage-specific overrides
) -> dict[str, Any]:          # Enriched envelope
```

**Module Characteristics:**
- **Pure function** - No side state, no cross-module dependencies
- **Idempotent** - Can be called multiple times safely
- **Fast** - Respects latency budget from contract
- **Isolated** - Uses `context.syscalls` for storage, `context.logger` for logging

### Step 3: Create Directory Structure (If New Domain)

```bash
# For new domain "hippocampus"
mkdir -p k0/modules/hippocampus
touch k0/modules/hippocampus/__init__.py
```

**Module Library Structure:**
```
k0/modules/
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

---

## How to Create a Pipeline (Declarative)

### Step 1: Create Pipeline Spec

**Location:** `k0/contracts/pipelines/<pipeline_id>.v<version>.yaml`

**Example:** `k0/contracts/pipelines/p02_write.v1.yaml`

```yaml
pipeline_id: P02_WRITE
version: v1
entry_topic: cognitive.memory.write.committed.v1
exit_topic: p02.write.complete.v1
concurrency: 1
max_queue: 512
description: |
  P02 Pipeline - Episodic Memory Write Path
  Processes committed memory.delta envelopes and writes to hippocampus storage.

dag:
  # Stage 1: Affect Analysis
  - id: stage_10_affect
    module: affect.analyze:v1
    after: []
    config:
      confidence_threshold: 0.8

  # Stage 2: Space Resolution
  - id: stage_20_space
    module: space.resolve_visibility:v1
    after: [stage_10_affect]
    config:
      visibility_mode: "household"

  # Stage 3: Pattern Separation
  - id: stage_30_hippocampus
    module: hippocampus.pattern_separate:v1
    after: [stage_20_space]
    config:
      novelty_threshold: 0.7

  # Stage 4: Write to Storage
  - id: stage_40_writer
    module: core.writer:v1
    after: [stage_30_hippocampus]
```

**Required Fields:**
- `pipeline_id` - Pattern: `P[0-9]{2}_[A-Z_]+` (e.g., `P02_WRITE`)
- `version` - Pattern: `v[0-9]+` (e.g., `v1`)
- `entry_topic` - Event topic that triggers pipeline
- `dag` - List of stages (at least 1)

**Optional Fields:**
- `exit_topic` - Event emitted on successful completion
- `concurrency` - Max concurrent executions (default: 1)
- `max_queue` - Backpressure threshold (default: 512)
- `description` - Human-readable description

**Stage Fields:**
- `id` - Unique stage identifier (pattern: `[a-z0-9_]+`)
- `module` - Module reference (`module_id:version` or `module_id` → defaults to `:v1`)
- `after` - List of stage IDs that must complete first
- `config` - Stage-specific configuration overrides

### Step 2: Loader Integration (Future)

**When Phase 5 is implemented:**

Loader will auto-discover YAML specs:

```python
# k0/pipelines/loader.py (future extension)
async def discover_and_boot_pipelines(...):
    pipelines = {}

    # EXISTING: Python class pipelines
    for py_file in pipeline_dir.glob("p[0-9]*.py"):
        pipeline = _load_python_pipeline(py_file)
        pipelines[pipeline.pipeline_id] = pipeline

    # NEW: YAML spec pipelines
    specs_dir = project_root / "k0/contracts/pipelines"
    for yaml_file in specs_dir.glob("*.yaml"):
        spec = PipelineSpec.load(yaml_file)
        runner = PipelineRunner(spec, module_registry)
        pipelines[spec.pipeline_id] = runner

    return pipelines
```

**Both paradigms coexist:** Python pipelines for custom logic, YAML pipelines for declarative DAGs.

---

## DAG Execution

### Topological Ordering

**Sequential Execution:**
```python
# DAG enforces dependencies
dag = build_dag(pipeline_spec)
for stage in dag.topological_order():
    # Guaranteed: all dependencies completed
    await execute_stage(stage)
```

**Example DAG:**
```yaml
dag:
  - id: A
    after: []
  - id: B
    after: [A]
  - id: C
    after: [A]
  - id: D
    after: [B, C]
```

**Topological Order:** `[A, B, C, D]` or `[A, C, B, D]` (both valid)

### Level-Based Parallelism (Future)

**Parallel Execution:**
```python
# Execute stages at same level in parallel
for level_group in dag.get_level_groups():
    await asyncio.gather(*[execute_stage(s) for s in level_group])
```

**Level Assignment:**
- Level 0: Stages with no dependencies
- Level N: Stages whose dependencies are all in levels < N

**Example Levels:**
```
Level 0: [A]
Level 1: [B, C]  ← Can run in parallel
Level 2: [D]
```

### Cycle Detection

**DAG Builder validates:**
```python
# Raises DAGCycleError if cycle detected
dag = build_dag(spec)
```

**Example Cycle (Invalid):**
```yaml
# ❌ Invalid - cycle detected
dag:
  - id: A
    after: [B]
  - id: B
    after: [A]
```

---

## Module Registry Behavior

### Loading Contracts

**Startup:**
```python
registry = ModuleRegistry()
await registry.load_contracts("k0/contracts/modules")
```

**Scans for:** `*.yaml` or `*.yml` files matching `<module_id>.v<version>.yaml`

**Example Files:**
- `hippocampus.pattern_separate.v1.yaml` → `hippocampus.pattern_separate:v1`
- `affect.analyze.v1.yaml` → `affect.analyze:v1`
- `space.resolve_visibility.v2.yaml` → `space.resolve_visibility:v2`

**Validation:**
- Pydantic schema validation
- Side effect format check (`operation:resource`)
- Latency budget range (1-10000ms)

### Lazy Loading Implementations

**On First Get:**
```python
# First call loads implementation
module_fn = registry.get("hippocampus.pattern_separate:v1")
# → Imports k0.modules.hippocampus.pattern_separate
# → Returns pattern_separate.run

# Subsequent calls use cache
module_fn = registry.get("hippocampus.pattern_separate:v1")
# → Returns cached implementation
```

**Error Handling:**
- `ModuleNotFoundError` - Contract not registered
- `ModuleLoadError` - Import failed or missing `run()` function

### Lookup API

```python
# Get implementation
module_fn = registry.get("hippocampus.pattern_separate:v1")

# Get contract (metadata)
contract = registry.get_contract("hippocampus.pattern_separate:v1")
print(contract.latency_budget_ms)  # 15
print(contract.idempotent)  # True

# List all modules
modules = registry.list_modules()  # ["hippocampus.pattern_separate:v1", ...]

# Check if registered
if "hippocampus.pattern_separate:v1" in registry:
    print("Module available")
```

---

## Pipeline Runner Behavior

### PipelineProtocol Implementation

**Runner acts as a pipeline from kernel's perspective:**

```python
runner = PipelineRunner(spec, registry)

# Implements PipelineProtocol properties (via @property)
runner.pipeline_id          # "P02_WRITE"
runner.contract_version     # 1
runner.declared_topics      # ("cognitive.memory.write.committed.v1",)
runner.concurrency          # 1
runner.max_queue           # 512
runner.required_caps       # () (computed from modules)

# Implements PipelineProtocol methods
await runner.on_startup(ctx)
await runner.on_shutdown()
await runner.handle(msg)
```

### Execution Flow

**On Message Arrival:**
1. Check topic matches `declared_topics`
2. Reset per-execution state (`_completed_stages`, `_failed_stages`)
3. Execute stages in topological order:
   - Get module implementation from registry
   - Prepare args: `message`, `context`, `**stage.config`
   - Call `module_fn(**args)`
   - Track completion
4. Log telemetry (duration, completed stages, errors)
5. Raise exception on failure (kernel handles DLQ)

**State Tracking:**
```python
# Per-execution state
self._completed_stages: set[str]  # {"stage_10_affect", "stage_20_space"}
self._failed_stages: set[str]     # {"stage_30_hippocampus"}
self._execution_count: int        # 42 (total executions)
```

### Error Handling

**Stage Failure:**
```python
try:
    result = await module_fn(**args)
    self._completed_stages.add(stage.id)
except Exception as e:
    self._failed_stages.add(stage.id)
    self.logger.error(f"Stage failed: {stage.id}", exc_info=True)
    raise  # Propagate to kernel
```

**Kernel Behavior:**
- Exception raised → Driver pool retries with exponential backoff (default: 10 attempts, configurable via `dlq.max_retry_attempts`)
- After max retries → Move to DLQ (`st_dlq`)

---

## Schema Validation

### ModuleContract Validation

**Pattern Checks:**
```python
module_id: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$")
# ✅ Valid: "hippocampus.pattern_separate"
# ❌ Invalid: "HippocampusPatternSeparate", "hippocampus", "pattern_separate"

version: str = Field(pattern=r"^v\d+$")
# ✅ Valid: "v1", "v2", "v10"
# ❌ Invalid: "1", "version1", "v1.0"
```

**Side Effect Validation:**
```python
side_effects: list[str]
# ✅ Valid: ["read:st_hipp_store", "write:st_wal", "emit:memory.delta"]
# ❌ Invalid: ["st_hipp_store", "read", "query:st_hipp_store"]

# Allowed operations: read, write, emit
```

**Latency Budget Range:**
```python
latency_budget_ms: int = Field(ge=1, le=10000)
# ✅ Valid: 5, 100, 5000
# ❌ Invalid: 0, -5, 20000
```

### PipelineSpec Validation

**Pattern Checks:**
```python
pipeline_id: str = Field(pattern=r"^P[0-9]{2}_[A-Z_]+$")
# ✅ Valid: "P02_WRITE", "P10_CONSOLIDATION"
# ❌ Invalid: "P2_WRITE", "P02WRITE", "p02_write"
```

**DAG Validation:**
```python
@field_validator("dag")
def validate_dag_structure(cls, v: list[StageSpec]) -> list[StageSpec]:
    # Check all dependencies exist
    stage_ids = {stage.id for stage in v}
    for stage in v:
        for dep in stage.after:
            if dep not in stage_ids:
                raise ValueError(f"Stage '{stage.id}' depends on non-existent stage '{dep}'")

    # Check for cycles (topological sort simulation)
    # ...raises ValueError if cycle detected
```

### StageSpec Validation

**Pattern Checks:**
```python
id: str = Field(pattern=r"^[a-z0-9_]+$")
# ✅ Valid: "stage_10_affect", "stage01"
# ❌ Invalid: "Stage-10", "stage 10", "STAGE_10"

module: str = Field(pattern=r"^[a-z_]+\.[a-z_]+(:[a-z0-9]+)?$")
# ✅ Valid: "hippocampus.pattern_separate:v1", "affect.analyze"
# ❌ Invalid: "Hippocampus.PatternSeparate", "pattern_separate"
```

**Version Defaulting:**
```python
@field_validator("module")
def validate_module_ref(cls, v: str) -> str:
    if ":" not in v:
        return f"{v}:v1"  # Default to v1
    return v

# "hippocampus.pattern_separate" → "hippocampus.pattern_separate:v1"
```

---

## Testing

### Unit Test: Module Function

```python
import pytest
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.modules.hippocampus.pattern_separate import run


@pytest.mark.asyncio
async def test_pattern_separate_module():
    # Arrange
    message = BusMessage(
        topic="memory.delta",
        payload=b'{"space_id": "space-home", "embedding": [0.1, 0.2]}',
        offset=1,
    )
    context = PipelineContext(
        syscalls=mock_syscalls,
        config={},
        logger=mock_logger,
    )

    # Act
    result = await run(message, context, novelty_threshold=0.7)

    # Assert
    assert "pattern_separated" in result
    assert result["pattern_separated"]["novelty_score"] > 0
```

### Unit Test: Module Registry

```python
@pytest.mark.asyncio
async def test_module_registry_loading():
    # Arrange
    registry = ModuleRegistry()

    # Act
    await registry.load_contracts("k0/contracts/modules")

    # Assert
    assert len(registry) > 0
    assert "hippocampus.pattern_separate:v1" in registry

    # Get contract
    contract = registry.get_contract("hippocampus.pattern_separate:v1")
    assert contract.latency_budget_ms == 15
```

### Unit Test: Pipeline Runner

```python
@pytest.mark.asyncio
async def test_pipeline_runner_execution():
    # Arrange
    spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")
    registry = ModuleRegistry()
    await registry.load_contracts("k0/contracts/modules")
    runner = PipelineRunner(spec, registry)

    ctx = PipelineContext(syscalls=mock_syscalls, config={}, logger=mock_logger)
    await runner.on_startup(ctx)

    msg = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=b'{"space_id": "space-home"}',
        offset=1,
    )

    # Act
    await runner.handle(msg)

    # Assert
    assert runner._execution_count == 1
    assert len(runner._completed_stages) == 4  # All stages completed
```

### Integration Test: DAG Builder

```python
def test_dag_cycle_detection():
    # Arrange
    spec = PipelineSpec(
        pipeline_id="P99_TEST",
        version="v1",
        entry_topic="test.topic",
        dag=[
            StageSpec(id="A", module="test.module", after=["B"]),
            StageSpec(id="B", module="test.module", after=["A"]),
        ],
    )

    # Act & Assert
    with pytest.raises(DAGCycleError):
        build_dag(spec)
```

---

## Troubleshooting

### Module Not Found

**Error:** `ModuleNotFoundError: Module not found: hippocampus.pattern_separate:v1`

**Checklist:**
- [ ] Contract file exists: `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`
- [ ] Registry loaded: `await registry.load_contracts("k0/contracts/modules")`
- [ ] Module ID matches filename

### Module Load Failed

**Error:** `ModuleLoadError: Cannot import module k0.modules.hippocampus.pattern_separate`

**Checklist:**
- [ ] Implementation file exists: `k0/modules/hippocampus/pattern_separate.py`
- [ ] Directory has `__init__.py`: `k0/modules/hippocampus/__init__.py`
- [ ] Module has `run()` function: `async def run(...) -> dict`

### DAG Cycle Detected

**Error:** `DAGCycleError: Cycle detected in pipeline P02_WRITE`

**Fix:** Review `stage.after` dependencies, ensure no circular references

**Example:**
```yaml
# ❌ Invalid
- id: A
  after: [B]
- id: B
  after: [A]

# ✅ Valid
- id: A
  after: []
- id: B
  after: [A]
```

### Pipeline Not Receiving Messages

**Checklist:**
- [ ] `entry_topic` matches published topic exactly
- [ ] Runner implements `PipelineProtocol` correctly
- [ ] Loader extended to discover YAML specs (Phase 5)

---

## Design Principles

### 1. Pure Functions Over Classes
- Modules are stateless functions
- No cross-module dependencies
- Easy to test, compose, and reuse

### 2. Data Over Code
- Pipelines defined in YAML, not Python
- Module contracts are data (YAML), not code
- Easier to version, review, and generate docs

### 3. Lazy Loading
- Module implementations loaded on first use
- Reduces startup time
- Supports hot-reloading (future)

### 4. Strong Validation
- Pydantic validates all YAML at load time
- DAG builder detects cycles before execution
- Fail-fast on invalid specs

### 5. Backward Compatibility
- `PipelineRunner` implements `PipelineProtocol`
- Both Python and YAML pipelines coexist
- Incremental migration path

---

## Status

**Current State:** Core runtime infrastructure complete ✅
- `ModuleRegistry` - Contract loading, lazy implementation loading
- `PipelineRunner` - DAG execution, PipelineProtocol implementation
- `DAG` - Topological sort, cycle detection, level computation
- Pydantic schemas - YAML validation

**Next Phase:** Loader integration + first declarative pipelines (Phase 3-5) 🚧
- Extend loader to discover YAML specs in `k0/contracts/pipelines/`
- Implement 5-7 modules in `k0/modules/`
- Create P02 YAML spec
- Test end-to-end declarative pipeline

---

## Key Files

### Must Read Before Modifying

1. **`schemas.py`** - Pydantic models (contract definitions)
2. **`module_registry.py`** - Module discovery & lookup
3. **`pipeline_runner.py`** - Generic DAG executor
4. **`dag_builder.py`** - DAG construction & validation

### Related Documentation

1. **`k0/pipelines/MIGRATION_PLAN.md`** - Full migration roadmap
2. **`k0/pipelines/README.md`** - PipelineProtocol reference
3. **`k0/kernel/app.py:488-527`** - Kernel integration

---

## FAQ

**Q: When will YAML pipelines be supported?**
A: Phase 5 (2-3 weeks after completing module library). Infrastructure ready, needs loader extension.

**Q: Can I use both Python and YAML pipelines?**
A: Yes. Both paradigms coexist. Python for custom logic, YAML for declarative DAGs.

**Q: How do modules access storage?**
A: Via `context.syscalls` (capability-gated adapter provided by runner).

**Q: Can modules call other modules?**
A: No direct calls. Modules are composed via DAG stages in pipeline specs.

**Q: How do I version modules?**
A: Use filename versioning (`module_id.v1.yaml`, `module_id.v2.yaml`). Multiple versions can coexist.

**Q: What happens if a module exceeds latency budget?**
A: Logged as warning. No enforcement yet (future: timeouts, circuit breakers).

---

**For migration roadmap, see `k0/pipelines/MIGRATION_PLAN.md`**
**For PipelineProtocol reference, see `k0/pipelines/README.md`**
