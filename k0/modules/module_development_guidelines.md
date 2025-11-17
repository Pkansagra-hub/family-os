# Module Development Guidelines

**Comprehensive guide for developing Phase 2+ declarative pipeline modules**

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Phase 2 Architecture](#phase-2-architecture)
4. [Step-by-Step Module Development](#step-by-step-module-development)
5. [Module Contract Specification](#module-contract-specification)
6. [Module Implementation Guide](#module-implementation-guide)
7. [Testing Strategy](#testing-strategy)
8. [Pipeline Integration](#pipeline-integration)
9. [Best Practices](#best-practices)
10. [Common Patterns](#common-patterns)
11. [Troubleshooting](#troubleshooting)
12. [Complete Example: Pattern Separation Module](#complete-example-pattern-separation-module)

---

## Overview

### What Are Modules?

Modules are **pure, reusable functions** that perform a single, well-defined transformation on data. They are the building blocks of declarative pipelines in the Phase 2+ architecture.

**Key Characteristics:**

- **Pure Functions**: No shared state, no cross-module dependencies
- **Async/Await**: All modules are async for non-blocking execution
- **Capability-Gated**: Access storage through `context.syscalls` (least-privilege security)
- **Composable**: Chain modules via pipeline DAG specifications
- **Versioned**: Multiple versions can coexist (`module_id:v1`, `module_id:v2`)

### Why Phase 2?

Phase 2 decouples pipeline orchestration from business logic:

| Aspect | Phase 1 (Imperative) | Phase 2+ (Declarative) |
|--------|---------------------|------------------------|
| Pipeline Definition | Python classes | YAML specs |
| Business Logic | Inline in `handle()` | Separate modules |
| Reusability | Copy-paste | Import by ID |
| Testing | Mock entire pipeline | Test pure functions |
| Versioning | Git only | Contract + Git |
| Documentation | Manual | Auto-generated from contracts |

### Module vs Pipeline

| Concept | Purpose | Example |
|---------|---------|---------|
| **Module** | Reusable transformation function | `hippocampus.pattern_separate:v1` |
| **Pipeline** | DAG orchestration specification | `P02_WRITE` (YAML) |
| **Stage** | Single module invocation in a DAG | `stage_30_hippocampus` |

---

## Prerequisites

### Required Knowledge

- Python 3.11+ (async/await, type hints)
- Pydantic models (validation)
- YAML syntax
- FamilyOS architecture (Bus, Kernel, Syscalls)

### Required Reading

**Before developing modules, read these files:**

1. **`k0/runtime/README.md`** - Runtime architecture and execution model
2. **`k0/pipelines/MIGRATION_PLAN.md`** - Phase 2 migration strategy (Phases 4-7)
3. **`k0/pipelines/protocol.py`** - PipelineContext and BusMessage definitions
4. **`k0/runtime/schemas.py`** - ModuleContract and PipelineSpec schemas

### System Prerequisites

**Infrastructure must be complete:**

- ✅ `k0/runtime/` - ModuleRegistry, PipelineRunner, DAG builder
- ✅ `k0/bus/core.py` - BusMessage definition
- ✅ `k0/kernel/syscalls.py` - Capability-gated storage adapter
- ✅ `k0/pipelines/loader.py` - Pipeline discovery and boot system

**Verify runtime is ready:**

```bash
# Check runtime exists
ls k0/runtime/README.md

# Verify "Core runtime infrastructure complete ✅"
grep "complete" k0/runtime/README.md
```

---

## Phase 2 Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Kernel (k0/kernel/app.py)                │
│  - Lifecycle management (startup/shutdown)                  │
│  - BusDispatcher integration (topic routing)                │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Pipeline Loader (k0/pipelines/loader.py)       │
│  - Discovers Python classes (Phase 1) AND YAML specs (Phase 2) │
│  - Validates PipelineProtocol compliance                    │
│  - Creates Syscalls adapters (capability enforcement)       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ├───► Phase 1: Python Classes (p*.py)
                          │     - Class with PipelineProtocol
                          │     - Inline handle() method
                          │
                          └───► Phase 2+: YAML Specs (contracts/pipelines/*.yaml)
                                - ModuleRegistry (loads contracts)
                                - PipelineRunner (DAG executor)
                                └───► Modules (k0/modules/<domain>/<action>.py)
                                      - Pure async functions
                                      - Capability-gated via context.syscalls
```

### Execution Flow (Phase 2+)

```
1. Kernel Boot
   └─► Loader discovers YAML specs
       └─► ModuleRegistry loads contracts (k0/contracts/modules/*.yaml)
       └─► PipelineRunner created per spec
           └─► DAG builder validates dependencies
           └─► Runner registered with BusDispatcher

2. Message Arrival (BusMessage on topic "cognitive.memory.write.committed.v1")
   └─► BusDispatcher routes to PipelineRunner.handle()
       └─► Runner executes stages in topological order
           └─► For each stage:
               ├─► Get module implementation (registry.get("module_id:v1"))
               ├─► Prepare args (message, context, **stage.config)
               ├─► Call module: result = await module_fn(**args)
               └─► Track completion

3. Completion
   └─► Runner emits completion event (exit_topic)
   └─► Logs telemetry (duration, completed stages)
```

### Data Flow Through Module

```
BusMessage (input)
  ↓
Module Function: async def run(message, context, **config)
  ├─ Parse payload: envelope = json.loads(message.payload)
  ├─ Query storage: data = await context.syscalls.hipp_store_query(...)
  ├─ Transform: enriched = {**envelope, "novelty_score": 0.85}
  └─ Return: dict (enriched envelope)
      ↓
Next Stage (or exit_topic emission)
```

---

## Step-by-Step Module Development

### Phase Overview (from MIGRATION_PLAN.md)

**Phase 4: Design Requirements** (2-3 hours)

- Document module purpose and contracts
- Identify storage dependencies
- Map syscalls to capabilities

**Phase 5: Create Contract Definitions** (1-2 hours)

- Create `k0/contracts/modules/<module_id>.v1.yaml`
- Define inputs, outputs, latency budget, side effects

**Phase 6: Implement Module** (varies)

- Create `k0/modules/<domain>/<action>.py`
- Implement `async def run(...)` signature
- Use `context.syscalls` for storage

**Phase 7: Integrate with Pipeline** (1 hour)

- Create pipeline spec `k0/contracts/pipelines/<pipeline_id>.v1.yaml`
- Add module to DAG with dependencies
- Configure stage-specific parameters

---

## Step 1: Design Module Requirements

### Questions to Answer

1. **What does this module do?**
   - Single, clear transformation (e.g., "Compute novelty score for episodic memory")

2. **What are the inputs?**
   - Event types (e.g., `p02.write.requested.v1`)
   - Required fields in payload (e.g., `space_id`, `embedding`, `text`)

3. **What are the outputs?**
   - Event types emitted (e.g., `p02.hippocampus.pattern_separated.v1`)
   - Fields added to envelope (e.g., `novelty_score`, `similar_memory_count`)

4. **What storage does it access?**
   - Tables read (e.g., `st_hipp_store`)
   - Tables written (e.g., `st_hipp_events`)
   - Topics emitted (e.g., `memory.consolidated`)

5. **What is the latency budget?**
   - Target P95 latency in milliseconds (e.g., 15ms for pattern separation)

6. **Is it idempotent?**
   - Can it be safely retried? (e.g., yes for read-only queries, careful for writes)

### Example: Pattern Separation Module Design

**Purpose:** Compute novelty score for episodic memory by comparing against existing memories.

**Inputs:**

- Event type: `p02.write.requested.v1`
- Required fields: `space_id`, `embedding`, `event_id`

**Outputs:**

- Event type: `p02.hippocampus.pattern_separated.v1`
- Added fields: `novelty_score` (float 0-1), `similar_memory_count` (int), `is_novel` (bool)

**Storage:**

- Read: `st_hipp_store` (query similar memories)
- No writes (read-only analysis)

**Latency Budget:** 15ms P95

**Idempotent:** Yes (pure function, no side effects)

---

## Step 2: Create Module Contract (YAML)

### Contract Location

```
k0/contracts/modules/<module_id>.v<version>.yaml
```

**Naming Convention:**

- Module ID: `<domain>.<action>` (e.g., `hippocampus.pattern_separate`)
- Version: `v1`, `v2`, etc.
- Example: `hippocampus.pattern_separate.v1.yaml`

### Contract Schema

**Required Fields:**

```yaml
module_id: string          # Pattern: [a-z_]+\.[a-z_]+
version: string            # Pattern: v\d+ (e.g., v1)
latency_budget_ms: int     # Range: 1-10000
idempotent: bool           # Can module be safely retried?
```

**Optional Fields:**

```yaml
input_event_types: list[string]      # Event schemas this module accepts
output_event_types: list[string]     # Event schemas this module emits
side_effects: list[string]           # Format: operation:resource
failure_modes: list[dict]            # Known error codes and policies
description: string                  # Human-readable description
```

### Side Effects Format

**Pattern:** `<operation>:<resource>`

**Operations:**

- `read` - Query storage
- `write` - Modify storage
- `emit` - Publish to topic

**Examples:**

- `read:st_hipp_store` - Query episodic memory
- `write:st_hipp_events` - Insert to events table
- `emit:memory.consolidated` - Publish consolidation event

### Example Contract: `hippocampus.pattern_separate.v1.yaml`

```yaml
module_id: hippocampus.pattern_separate
version: v1

# Input/Output contracts
input_event_types:
  - p02.write.requested.v1
output_event_types:
  - p02.hippocampus.pattern_separated.v1

# Performance requirements
latency_budget_ms: 15
idempotent: true

# Storage operations
side_effects:
  - read:st_hipp_store

# Error handling
failure_modes:
  - code: NOVELTY_SCORE_MISSING
    policy: drop
  - code: EMBEDDING_MISSING
    policy: drop

# Documentation
description: |
  Pattern separation module for episodic memory encoding.
  Computes novelty scores by comparing against existing memories.

  Algorithm:
  1. Query similar memories (cosine similarity > 0.7)
  2. Compute average similarity of top 3 matches
  3. Novelty = 1.0 - avg_similarity

  Returns novelty_score (0.0-1.0) and similar_memory_count.
```

### Validation

**Create contract directory if needed:**

```bash
mkdir -p k0/contracts/modules
```

**Validate schema with Python:**

```python
from k0.runtime.schemas import ModuleContract
import yaml

# Load and validate
with open("k0/contracts/modules/hippocampus.pattern_separate.v1.yaml") as f:
    data = yaml.safe_load(f)

contract = ModuleContract(**data)  # Raises ValidationError if invalid
print(f"✅ Valid contract: {contract.full_id}")
```

---

## Step 3: Create Module Implementation

### Directory Structure

```bash
# For new domain
mkdir -p k0/modules/<domain>
touch k0/modules/<domain>/__init__.py

# Example: hippocampus module
mkdir -p k0/modules/hippocampus
touch k0/modules/hippocampus/__init__.py
```

**Module Library Structure:**

```
k0/modules/
├── __init__.py
├── hippocampus/
│   ├── __init__.py
│   └── pattern_separate.py    # Module implementation
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

### Module Function Signature (CANONICAL)

**Every module MUST have this exact signature:**

```python
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
    Module entry point (REQUIRED).

    Args:
        message: Incoming BusMessage with topic, payload, offset, trace_id
        context: PipelineContext with syscalls, logger, config
        **config: Stage-specific configuration overrides

    Returns:
        Enriched envelope (dict) with module outputs

    Raises:
        ValueError: For invalid input data
        Exception: For transient errors (triggers retry)
    """
    pass  # Implementation here
```

### Signature Components

**1. `message: BusMessage`**

Access event data:

```python
topic = message.topic                        # "cognitive.memory.write.committed.v1"
payload_bytes = message.payload              # b'{"space_id": "..."}'
offset = message.offset                      # WAL position (int)
trace_id = message.trace_id                  # Observability trace ID
space_id = message.space_id                  # Per-space ordering hint
metadata = message.metadata                  # Routing context (dict)
```

Parse payload:

```python
import json
envelope = json.loads(message.payload)
space_id = envelope["space_id"]
event_id = envelope["event_id"]
```

**2. `context: PipelineContext`**

Access capabilities:

```python
syscalls = context.syscalls     # Capability-gated storage adapter
logger = context.logger         # Structured logger
config = context.config         # Pipeline-level config
```

**3. `**config: Any`**

Stage-specific overrides:

```python
# From pipeline spec:
# config:
#   novelty_threshold: 0.7
#   min_similarity: 0.5

novelty_threshold = config.get("novelty_threshold", 0.8)  # Default to 0.8
min_similarity = config.get("min_similarity", 0.3)
```

**4. Return Value: `dict[str, Any]`**

Return enriched envelope:

```python
# Input envelope
envelope = {
    "space_id": "space-home",
    "event_id": "evt-123",
    "text": "Dinner at 7pm"
}

# Enriched envelope (add module outputs)
return {
    **envelope,  # Preserve original fields
    "pattern_separated": {
        "novelty_score": 0.85,
        "similar_memory_count": 3,
        "is_novel": True,
        "module_version": "v1",
    }
}
```

### Implementation Template

```python
"""
<Module Name> Module

<Brief description of what this module does>

Architecture:
- Input: <event types>
- Output: <event types>
- Storage: <tables read/written>
- Latency Budget: <X>ms P95
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
    <Module purpose - one line>

    Args:
        message: Incoming BusMessage with <required fields>
        context: PipelineContext with syscalls, logger, config
        **config: Stage-specific configuration overrides

    Returns:
        Enriched envelope with <added fields>

    Raises:
        ValueError: If <specific error condition>
    """
    # 1. Parse envelope
    import json
    envelope = json.loads(message.payload)

    # 2. Extract configuration
    param1 = config.get("param1", default_value)
    param2 = config.get("param2", default_value)

    # 3. Validate inputs
    if "required_field" not in envelope:
        raise ValueError("Missing required field: required_field")

    # 4. Query storage (via syscalls)
    data = await context.syscalls.storage_query(...)

    # 5. Core transformation logic
    result = _transform_data(envelope, data, param1, param2)

    # 6. Enrich envelope
    enriched = {
        **envelope,
        "<output_key>": result,
    }

    # 7. Structured logging
    context.logger.info(
        f"<Module> complete: <metric>=<value>",
        extra={
            "module": "<domain>.<action>",
            "trace_id": message.trace_id,
            "metric": result["metric"],
        },
    )

    return enriched


def _transform_data(envelope, data, param1, param2):
    """Helper function for core logic (pure, testable)."""
    # Transformation logic here
    return {"metric": 0.85}
```

---

## Step 4: Use Syscalls for Storage

### Available Syscalls

**Check `k0/kernel/syscalls.py` for current methods. Common ones:**

```python
# Hippocampus (episodic memory)
await context.syscalls.hipp_store_upsert(space_id, event_id, payload, ...)
await context.syscalls.hipp_store_query(space_id, query_vector, top_k)

# Working Memory
await context.syscalls.working_memory_write(space_id, payload)
await context.syscalls.working_memory_read(space_id)

# Embeddings
await context.syscalls.query_embeddings(space_id, query_vector, top_k)

# Pipeline Tracking (idempotency)
await context.syscalls.pipeline_check_processed(pipeline_id, space_id, wal_pos)
await context.syscalls.pipeline_mark_processed(pipeline_id, space_id, wal_pos)

# Receipts
await context.syscalls.pipeline_emit_status(pipeline_id, wal_pos, status, ...)
```

### Capability Enforcement

**Module contract declares required capabilities:**

```yaml
side_effects:
  - read:st_hipp_store
  - write:st_hipp_events
```

**Runner validates at startup:**

```python
# PipelineRunner checks module contracts
# Creates Syscalls adapter with only declared capabilities
# Attempting unauthorized storage access raises CapabilityError
```

### Example: Query Similar Memories

```python
async def run(message, context, **config):
    envelope = json.loads(message.payload)

    # Query similar memories
    similar_memories = await context.syscalls.hipp_store_query(
        space_id=envelope["space_id"],
        query_vector=envelope.get("embedding"),
        top_k=10,
    )

    # Process results
    novelty_score = _compute_novelty(similar_memories)

    return {**envelope, "novelty_score": novelty_score}
```

---

## Step 5: Add Structured Logging

### Logging Best Practices

**Use `context.logger` (not `logger = logging.getLogger()`):**

```python
context.logger.info(
    "Pattern separation complete",
    extra={
        "module": "hippocampus.pattern_separate",
        "novelty_score": novelty_score,
        "trace_id": message.trace_id,
        "space_id": envelope["space_id"],
    },
)
```

**Log Levels:**

- `DEBUG` - Internal state, detailed execution steps
- `INFO` - Normal operation milestones (e.g., "Module complete")
- `WARNING` - Recoverable issues (e.g., "Low confidence score")
- `ERROR` - Failures requiring attention (e.g., "Storage query failed")

**Include trace_id for observability:**

```python
extra={"trace_id": message.trace_id}
```

---

## Step 6: Write Tests

### Unit Test Pattern

**Test pure functions without runtime:**

```python
import pytest
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.modules.hippocampus.pattern_separate import run


@pytest.fixture
def mock_syscalls():
    """Mock Syscalls adapter."""
    class MockSyscalls:
        async def hipp_store_query(self, space_id, query_vector, top_k):
            return [
                {"similarity": 0.8, "event_id": "evt-1"},
                {"similarity": 0.6, "event_id": "evt-2"},
            ]
    return MockSyscalls()


@pytest.fixture
def mock_logger():
    """Mock logger."""
    import logging
    return logging.getLogger("test")


@pytest.mark.asyncio
async def test_pattern_separate_module(mock_syscalls, mock_logger):
    # Arrange
    message = BusMessage(
        topic="p02.write.requested.v1",
        payload=b'{"space_id": "space-home", "embedding": [0.1, 0.2]}',
        offset=1,
        trace_id="trace-123",
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
    assert "novelty_score" in result["pattern_separated"]
    assert 0.0 <= result["pattern_separated"]["novelty_score"] <= 1.0
```

### Integration Test Pattern

**Test with real runtime:**

```python
@pytest.mark.asyncio
async def test_module_in_pipeline():
    # Load contracts
    registry = ModuleRegistry()
    await registry.load_contracts("k0/contracts/modules")

    # Get module
    module_fn = registry.get("hippocampus.pattern_separate:v1")

    # Execute
    result = await module_fn(message, context, novelty_threshold=0.7)

    # Validate
    assert result["pattern_separated"]["module_version"] == "v1"
```

---

## Step 7: Create Pipeline Spec

### Pipeline Spec Location

```
k0/contracts/pipelines/<pipeline_id>.v<version>.yaml
```

**Example:** `k0/contracts/pipelines/p02_write.v1.yaml`

### Pipeline Spec Schema

```yaml
pipeline_id: string         # Pattern: P[0-9]{2}_[A-Z_]+ (e.g., P02_WRITE)
version: string             # Pattern: v\d+ (e.g., v1)
entry_topic: string         # Topic that triggers pipeline
exit_topic: string          # Optional completion event
concurrency: int            # Max concurrent executions (default: 1)
max_queue: int              # Backpressure threshold (default: 512)
dag: list[StageSpec]        # List of stages (DAG)
description: string         # Optional description
```

### Stage Spec Schema

```yaml
- id: string                # Unique stage ID (pattern: [a-z0-9_]+)
  module: string            # Module reference (module_id:version or module_id)
  after: list[string]       # Dependencies (stage IDs)
  config: dict              # Stage-specific config
```

### Example Pipeline Spec

```yaml
pipeline_id: P02_WRITE
version: v1
entry_topic: cognitive.memory.write.committed.v1
exit_topic: p02.write.complete.v1
concurrency: 1
max_queue: 512

description: |
  P02 Pipeline - Episodic Memory Write Path
  Processes committed memory.delta envelopes through multi-stage enrichment.

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

### DAG Dependencies

**Topological ordering enforced:**

```yaml
# Valid: Linear chain
- id: A
  after: []
- id: B
  after: [A]
- id: C
  after: [B]

# Valid: Parallel branches
- id: A
  after: []
- id: B
  after: [A]
- id: C
  after: [A]  # B and C run in parallel (future)
- id: D
  after: [B, C]  # Waits for both

# Invalid: Cycle detected
- id: A
  after: [B]
- id: B
  after: [A]  # ❌ Raises DAGCycleError
```

---

## Step 8: Extend Loader (Future)

**When Phase 7 is implemented, loader will auto-discover YAML specs:**

```python
# k0/pipelines/loader.py (future extension)
async def discover_and_boot_pipelines(...):
    pipelines = {}

    # EXISTING: Python class pipelines (Phase 1)
    for py_file in pipeline_dir.glob("p[0-9]*.py"):
        pipeline = _load_python_pipeline(py_file)
        pipelines[pipeline.pipeline_id] = pipeline

    # NEW: YAML spec pipelines (Phase 2+)
    module_registry = ModuleRegistry()
    await module_registry.load_contracts("k0/contracts/modules")

    specs_dir = project_root / "k0/contracts/pipelines"
    for yaml_file in specs_dir.glob("*.yaml"):
        spec = PipelineSpec.load(yaml_file)
        runner = PipelineRunner(spec, module_registry)
        await runner.on_startup(ctx)
        pipelines[spec.pipeline_id] = runner

    return pipelines
```

**Both paradigms coexist:** Python pipelines for custom logic, YAML pipelines for declarative DAGs.

---

## Module Contract Specification

### Required Fields Reference

```yaml
module_id: <domain>.<action>
  # Pattern: [a-z_]+\.[a-z_]+
  # Examples: hippocampus.pattern_separate, affect.analyze

version: v<number>
  # Pattern: v\d+
  # Examples: v1, v2, v10

latency_budget_ms: <milliseconds>
  # Range: 1-10000
  # Guidelines:
  #   - Fast queries: 5-15ms
  #   - CPU transforms: 20-50ms
  #   - Network calls: 100-500ms

idempotent: true|false
  # Can module be safely retried?
  # Guidelines:
  #   - Read-only: true
  #   - Deterministic writes: true
  #   - Non-deterministic (timestamps): false
```

### Optional Fields Reference

```yaml
input_event_types:
  - <event_schema_id>
  # Event schemas this module accepts
  # Examples: p02.write.requested.v1

output_event_types:
  - <event_schema_id>
  # Event schemas this module emits
  # Examples: p02.hippocampus.pattern_separated.v1

side_effects:
  - <operation>:<resource>
  # Storage operations
  # Operations: read, write, emit
  # Examples:
  #   - read:st_hipp_store
  #   - write:st_hipp_events
  #   - emit:memory.consolidated

failure_modes:
  - code: <ERROR_CODE>
    policy: drop|retry|dlq
  # Known error codes and handling
  # Examples:
  #   - code: EMBEDDING_MISSING
  #     policy: drop

description: |
  <Multi-line description>
  # Human-readable documentation
```

---

## Module Implementation Guide

### Module Characteristics

**1. Pure Function**

- No shared state between calls
- No cross-module dependencies
- Deterministic for same inputs (when idempotent=true)

**2. Async/Await**

- All storage calls are async
- Non-blocking I/O
- Can use `asyncio.gather()` for parallelism

**3. Capability-Gated**

- Access storage via `context.syscalls`
- Enforcement via `side_effects` in contract
- Least-privilege security

**4. Fast**

- Respect `latency_budget_ms` from contract
- Optimize hot paths
- Use caching when appropriate

**5. Isolated**

- No global state
- No direct imports of other modules
- No direct database connections

### Core Transformation Logic

**Extract into testable helper functions:**

```python
async def run(message, context, **config):
    envelope = json.loads(message.payload)
    data = await context.syscalls.query_storage(...)

    # Core logic in pure function
    result = _compute_metric(envelope, data, config)

    return {**envelope, "metric": result}


def _compute_metric(envelope: dict, data: list, config: dict) -> float:
    """Pure function - easily testable."""
    threshold = config.get("threshold", 0.5)
    # ... computation
    return 0.85
```

### Error Handling

**Transient Errors (raise exception):**

```python
try:
    data = await context.syscalls.query_storage(...)
except ConnectionError as e:
    # Retry with backoff (runner handles)
    raise
```

**Permanent Errors (log and return gracefully):**

```python
if "required_field" not in envelope:
    context.logger.warning(
        "Missing required field, using default",
        extra={"trace_id": message.trace_id},
    )
    default_value = config.get("default", None)
    # Continue processing with default
```

**Critical Failures (raise exception to DLQ):**

```python
if critical_validation_failed:
    context.logger.error(
        "Critical validation failed",
        extra={"trace_id": message.trace_id, "error": error_details},
    )
    raise ValueError(f"Critical error: {error_details}")
```

---

## Testing Strategy

### Test Pyramid

```
          ┌───────────────┐
          │ Integration   │ (10% - End-to-end with runtime)
          └───────────────┘
         ┌─────────────────┐
         │  Component      │ (20% - Module + mock syscalls)
         └─────────────────┘
        ┌───────────────────┐
        │   Unit            │ (70% - Pure functions)
        └───────────────────┘
```

### Unit Tests (70%)

**Test pure transformation logic:**

```python
def test_compute_novelty():
    # No async, no syscalls
    similar_memories = [
        {"similarity": 0.8},
        {"similarity": 0.6},
    ]
    novelty = _compute_novelty(similar_memories)
    assert 0.0 <= novelty <= 1.0
```

### Component Tests (20%)

**Test module with mocked syscalls:**

```python
@pytest.mark.asyncio
async def test_pattern_separate_with_mock(mock_syscalls):
    result = await run(message, context, novelty_threshold=0.7)
    assert "pattern_separated" in result
```

### Integration Tests (10%)

**Test module with real runtime:**

```python
@pytest.mark.asyncio
async def test_module_in_pipeline_runner():
    registry = ModuleRegistry()
    await registry.load_contracts("k0/contracts/modules")

    spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")
    runner = PipelineRunner(spec, registry)

    await runner.on_startup(context)
    await runner.handle(message)

    # Validate pipeline completed
    assert runner._execution_count == 1
```

---

## Pipeline Integration

### Step-by-Step Integration

**1. Module exists and is tested**

```bash
ls k0/modules/hippocampus/pattern_separate.py
pytest tests/modules/hippocampus/test_pattern_separate.py
```

**2. Contract exists**

```bash
ls k0/contracts/modules/hippocampus.pattern_separate.v1.yaml
```

**3. Pipeline spec references module**

```yaml
# k0/contracts/pipelines/p02_write.v1.yaml
dag:
  - id: stage_30_hippocampus
    module: hippocampus.pattern_separate:v1
    after: [stage_20_space]
    config:
      novelty_threshold: 0.7
```

**4. Loader discovers pipeline (when Phase 7 complete)**

```python
# k0/pipelines/loader.py
pipelines = await discover_and_boot_pipelines(...)
# Logs: "Loaded pipeline: P02_WRITE (4 stages)"
```

**5. Kernel boots successfully**

```bash
python -m k0.kernel.app
# Logs: "Booted 1 pipelines: ['P02_WRITE']"
```

---

## Best Practices

### Module Design

**✅ DO:**

- Keep modules focused (single responsibility)
- Use descriptive names (`pattern_separate`, not `process`)
- Document inputs/outputs in docstrings
- Return enriched envelope (preserve original fields)
- Use structured logging with trace_id
- Respect latency budgets

**❌ DON'T:**

- Mix concerns (e.g., storage + business logic in one module)
- Create circular dependencies (DAG builder detects this)
- Use global state or class variables
- Directly import other modules
- Hardcode configuration (use **config)

### Performance

**Optimize hot paths:**

```python
# Bad: Sequential queries
for item in items:
    result = await context.syscalls.query(item)

# Good: Parallel queries
results = await asyncio.gather(
    *[context.syscalls.query(item) for item in items]
)
```

**Cache expensive computations:**

```python
# Module-level cache (use lru_cache for pure functions)
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_computation(input_data: str) -> float:
    # Heavy computation here
    return result
```

### Security

**Use capability-gated syscalls:**

```python
# ✅ Good: Enforced by contract
await context.syscalls.hipp_store_query(...)

# ❌ Bad: Direct database access
import asyncpg
conn = await asyncpg.connect(...)  # Bypass capability enforcement
```

**Validate inputs:**

```python
# ✅ Good: Validate required fields
if "space_id" not in envelope:
    raise ValueError("Missing required field: space_id")

# ❌ Bad: Assume fields exist
space_id = envelope["space_id"]  # KeyError if missing
```

---

## Common Patterns

### Pattern 1: Read-Only Analysis

**Module that queries storage and enriches envelope:**

```python
async def run(message, context, **config):
    envelope = json.loads(message.payload)

    # Query similar items
    similar_items = await context.syscalls.query_storage(
        space_id=envelope["space_id"],
        query=envelope["text"],
        top_k=config.get("top_k", 10),
    )

    # Compute metric
    metric = _compute_similarity_metric(similar_items)

    # Enrich envelope
    return {
        **envelope,
        "similarity_analysis": {
            "metric": metric,
            "similar_count": len(similar_items),
        }
    }
```

### Pattern 2: Write to Storage

**Module that persists data:**

```python
async def run(message, context, **config):
    envelope = json.loads(message.payload)

    # Write to storage
    await context.syscalls.storage_write(
        space_id=envelope["space_id"],
        event_id=envelope["event_id"],
        payload=envelope,
        trace_id=message.trace_id,
    )

    # Return envelope (no enrichment)
    return envelope
```

### Pattern 3: Conditional Processing

**Module that skips processing based on criteria:**

```python
async def run(message, context, **config):
    envelope = json.loads(message.payload)

    # Check condition
    threshold = config.get("threshold", 0.5)
    if envelope.get("confidence", 0) < threshold:
        context.logger.info("Skipping low-confidence event")
        return envelope  # Pass through unchanged

    # Process high-confidence events
    result = await _process_high_confidence(envelope, context)
    return {**envelope, "processed": result}
```

### Pattern 4: Parallel Operations

**Module that performs multiple async operations:**

```python
async def run(message, context, **config):
    envelope = json.loads(message.payload)

    # Parallel queries
    results = await asyncio.gather(
        context.syscalls.query_storage_a(...),
        context.syscalls.query_storage_b(...),
        context.syscalls.query_storage_c(...),
    )

    storage_a, storage_b, storage_c = results

    # Combine results
    combined = _merge_results(storage_a, storage_b, storage_c)

    return {**envelope, "combined": combined}
```

---

## Troubleshooting

### Module Not Found

**Error:** `ModuleNotFoundError: Module not found: hippocampus.pattern_separate:v1`

**Checklist:**

- [ ] Contract file exists: `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`
- [ ] Registry loaded: `await registry.load_contracts("k0/contracts/modules")`
- [ ] Module ID matches contract (`module_id: hippocampus.pattern_separate`)

### Module Load Failed

**Error:** `ModuleLoadError: Cannot import module k0.modules.hippocampus.pattern_separate`

**Checklist:**

- [ ] Implementation file exists: `k0/modules/hippocampus/pattern_separate.py`
- [ ] Directory has `__init__.py`: `k0/modules/hippocampus/__init__.py`
- [ ] Module has `run()` function: `async def run(...) -> dict`
- [ ] No syntax errors in module file

### Contract Validation Failed

**Error:** `ValidationError: Invalid side effect format: st_hipp_store`

**Fix:** Use `operation:resource` format:

```yaml
# ❌ Bad
side_effects:
  - st_hipp_store

# ✅ Good
side_effects:
  - read:st_hipp_store
```

### DAG Cycle Detected

**Error:** `DAGCycleError: Cycle detected involving stage 'stage_30_hippocampus'`

**Fix:** Review dependencies in pipeline spec:

```yaml
# ❌ Bad: Circular dependency
- id: stage_a
  after: [stage_b]
- id: stage_b
  after: [stage_a]

# ✅ Good: Linear dependency
- id: stage_a
  after: []
- id: stage_b
  after: [stage_a]
```

### Missing Syscall Method

**Error:** `AttributeError: 'Syscalls' object has no attribute 'hipp_store_query'`

**Fix:** Check if syscall exists in `k0/kernel/syscalls.py`:

```bash
grep "def hipp_store_query" k0/kernel/syscalls.py
```

If missing, implement syscall or use alternative method.

---

## Complete Example: Pattern Separation Module

### Step 1: Contract

**File:** `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`

```yaml
module_id: hippocampus.pattern_separate
version: v1

input_event_types:
  - p02.write.requested.v1

output_event_types:
  - p02.hippocampus.pattern_separated.v1

latency_budget_ms: 15
idempotent: true

side_effects:
  - read:st_hipp_store

failure_modes:
  - code: NOVELTY_SCORE_MISSING
    policy: drop
  - code: EMBEDDING_MISSING
    policy: drop

description: |
  Pattern separation module for episodic memory encoding.

  Computes novelty scores by comparing against existing memories
  using cosine similarity on embedding vectors.

  Algorithm:
  1. Query similar memories (top 10, similarity > 0.5)
  2. Compute average similarity of top 3 matches
  3. Novelty = 1.0 - avg_similarity

  Returns:
  - novelty_score: float (0.0-1.0)
  - similar_memory_count: int
  - is_novel: bool (novelty > threshold)
```

### Step 2: Implementation

**File:** `k0/modules/hippocampus/pattern_separate.py`

```python
"""
Hippocampus Pattern Separation Module

Performs pattern separation on episodic memory events by comparing
against existing memories and computing novelty scores.

Architecture:
- Input: p02.write.requested.v1 (requires embedding field)
- Output: Enriched envelope with pattern_separated metadata
- Storage: Read from st_hipp_store (query similar memories)
- Latency Budget: 15ms P95
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

    Queries similar memories and computes novelty score based on
    cosine similarity of embeddings.

    Args:
        message: Incoming BusMessage with memory.delta event
        context: PipelineContext with syscalls, logger, config
        **config: Stage-specific configuration overrides
            - novelty_threshold: float (default 0.7)
            - top_k: int (default 10)
            - min_similarity: float (default 0.5)

    Returns:
        Enriched envelope with pattern_separated metadata

    Raises:
        ValueError: If embedding field is missing
    """
    # 1. Parse envelope
    import json
    envelope = json.loads(message.payload)

    # 2. Extract configuration
    novelty_threshold = config.get("novelty_threshold", 0.7)
    top_k = config.get("top_k", 10)
    min_similarity = config.get("min_similarity", 0.5)

    # 3. Validate inputs
    if "embedding" not in envelope:
        context.logger.warning(
            "Pattern separation skipped: missing embedding",
            extra={
                "module": "hippocampus.pattern_separate",
                "trace_id": message.trace_id,
                "space_id": envelope.get("space_id"),
            },
        )
        # Return envelope unchanged (graceful degradation)
        return envelope

    # 4. Query similar memories (read capability)
    similar_memories = await context.syscalls.hipp_store_query(
        space_id=envelope["space_id"],
        query_vector=envelope["embedding"],
        top_k=top_k,
    )

    # 5. Compute novelty score
    novelty_score = _compute_novelty(similar_memories, min_similarity)
    is_novel = novelty_score > novelty_threshold

    # 6. Enrich envelope
    enriched = {
        **envelope,
        "pattern_separated": {
            "novelty_score": novelty_score,
            "similar_memory_count": len(similar_memories),
            "is_novel": is_novel,
            "module_version": "v1",
            "config": {
                "novelty_threshold": novelty_threshold,
                "top_k": top_k,
            },
        },
    }

    # 7. Structured logging
    context.logger.info(
        f"Pattern separation complete: novelty={novelty_score:.3f}",
        extra={
            "module": "hippocampus.pattern_separate",
            "novelty_score": novelty_score,
            "similar_count": len(similar_memories),
            "is_novel": is_novel,
            "trace_id": message.trace_id,
            "space_id": envelope["space_id"],
        },
    )

    return enriched


def _compute_novelty(similar_memories: list[dict], min_similarity: float) -> float:
    """
    Compute novelty score based on similar memories.

    Algorithm:
    - If no similar memories: novelty = 1.0 (completely novel)
    - Average similarity of top 3 matches (> min_similarity)
    - Novelty = 1.0 - avg_similarity

    Args:
        similar_memories: List of memory matches with similarity scores
        min_similarity: Minimum similarity threshold (filter noise)

    Returns:
        Novelty score (0.0-1.0), where 1.0 is completely novel
    """
    if not similar_memories:
        return 1.0  # Completely novel (no existing memories)

    # Filter by minimum similarity threshold
    relevant_memories = [
        m for m in similar_memories
        if m.get("similarity", 0) >= min_similarity
    ]

    if not relevant_memories:
        return 1.0  # No relevant similar memories

    # Average similarity of top 3 matches
    top_similarities = sorted(
        [m["similarity"] for m in relevant_memories],
        reverse=True,
    )[:3]

    avg_similarity = sum(top_similarities) / len(top_similarities)

    # Novelty is inverse of similarity
    novelty = 1.0 - avg_similarity

    return max(0.0, min(1.0, novelty))  # Clamp to [0, 1]
```

### Step 3: Tests

**File:** `tests/modules/hippocampus/test_pattern_separate.py`

```python
import pytest
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.modules.hippocampus.pattern_separate import run, _compute_novelty


# ===== Unit Tests (Pure Functions) =====

def test_compute_novelty_no_memories():
    """Novelty should be 1.0 when no similar memories exist."""
    novelty = _compute_novelty([], min_similarity=0.5)
    assert novelty == 1.0


def test_compute_novelty_high_similarity():
    """Novelty should be low when similar memories exist."""
    similar_memories = [
        {"similarity": 0.9},
        {"similarity": 0.85},
        {"similarity": 0.8},
    ]
    novelty = _compute_novelty(similar_memories, min_similarity=0.5)
    assert 0.0 <= novelty <= 0.2  # Low novelty (high similarity)


def test_compute_novelty_low_similarity():
    """Novelty should be high when memories are dissimilar."""
    similar_memories = [
        {"similarity": 0.3},
        {"similarity": 0.2},
    ]
    novelty = _compute_novelty(similar_memories, min_similarity=0.1)
    assert 0.7 <= novelty <= 1.0  # High novelty (low similarity)


# ===== Component Tests (Module with Mocks) =====

@pytest.fixture
def mock_syscalls():
    """Mock Syscalls adapter."""
    class MockSyscalls:
        async def hipp_store_query(self, space_id, query_vector, top_k):
            return [
                {"similarity": 0.8, "event_id": "evt-1"},
                {"similarity": 0.6, "event_id": "evt-2"},
                {"similarity": 0.4, "event_id": "evt-3"},
            ]
    return MockSyscalls()


@pytest.fixture
def mock_logger():
    """Mock logger."""
    import logging
    return logging.getLogger("test")


@pytest.mark.asyncio
async def test_pattern_separate_module(mock_syscalls, mock_logger):
    """Test module with mocked syscalls."""
    # Arrange
    message = BusMessage(
        topic="p02.write.requested.v1",
        payload=b'{"space_id": "space-home", "embedding": [0.1, 0.2], "event_id": "evt-123"}',
        offset=1,
        trace_id="trace-123",
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
    assert "novelty_score" in result["pattern_separated"]
    assert "similar_memory_count" in result["pattern_separated"]
    assert "is_novel" in result["pattern_separated"]

    # Validate ranges
    assert 0.0 <= result["pattern_separated"]["novelty_score"] <= 1.0
    assert result["pattern_separated"]["similar_memory_count"] == 3

    # Validate module version
    assert result["pattern_separated"]["module_version"] == "v1"


@pytest.mark.asyncio
async def test_pattern_separate_missing_embedding(mock_syscalls, mock_logger):
    """Test graceful degradation when embedding is missing."""
    # Arrange
    message = BusMessage(
        topic="p02.write.requested.v1",
        payload=b'{"space_id": "space-home", "event_id": "evt-123"}',  # No embedding
        offset=1,
        trace_id="trace-123",
    )
    context = PipelineContext(
        syscalls=mock_syscalls,
        config={},
        logger=mock_logger,
    )

    # Act
    result = await run(message, context)

    # Assert: Envelope returned unchanged
    assert "pattern_separated" not in result
    assert result["space_id"] == "space-home"


@pytest.mark.asyncio
async def test_pattern_separate_config_override(mock_syscalls, mock_logger):
    """Test config overrides are applied."""
    # Arrange
    message = BusMessage(
        topic="p02.write.requested.v1",
        payload=b'{"space_id": "space-home", "embedding": [0.1], "event_id": "evt-123"}',
        offset=1,
        trace_id="trace-123",
    )
    context = PipelineContext(
        syscalls=mock_syscalls,
        config={},
        logger=mock_logger,
    )

    # Act: Override novelty_threshold
    result = await run(message, context, novelty_threshold=0.5, top_k=5)

    # Assert: Config stored in result
    assert result["pattern_separated"]["config"]["novelty_threshold"] == 0.5
    assert result["pattern_separated"]["config"]["top_k"] == 5
```

### Step 4: Pipeline Integration

**File:** `k0/contracts/pipelines/p02_write.v1.yaml`

```yaml
pipeline_id: P02_WRITE
version: v1
entry_topic: cognitive.memory.write.committed.v1
exit_topic: p02.write.complete.v1
concurrency: 1
max_queue: 512

description: |
  P02 Pipeline - Episodic Memory Write Path

  Stages:
  1. Affect Analysis (valence, arousal)
  2. Space Resolution (visibility, permissions)
  3. Pattern Separation (novelty detection) ← Our module
  4. Writer (persist to st_hipp_store)

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

  # Stage 3: Pattern Separation ← Our module
  - id: stage_30_hippocampus
    module: hippocampus.pattern_separate:v1
    after: [stage_20_space]
    config:
      novelty_threshold: 0.7
      top_k: 10
      min_similarity: 0.5

  # Stage 4: Write to Storage
  - id: stage_40_writer
    module: core.writer:v1
    after: [stage_30_hippocampus]
```

---

## Summary Checklist

**When developing a new module, ensure:**

- [ ] **Design Document** - Requirements, inputs, outputs, storage (Step 1)
- [ ] **Module Contract** - `k0/contracts/modules/<module_id>.v1.yaml` (Step 2)
- [ ] **Implementation** - `k0/modules/<domain>/<action>.py` with `async def run(...)` (Step 3)
- [ ] **Syscalls Usage** - Access storage via `context.syscalls` (Step 4)
- [ ] **Structured Logging** - Use `context.logger` with `trace_id` (Step 5)
- [ ] **Unit Tests** - Test pure functions (70%) (Step 6)
- [ ] **Component Tests** - Test module with mocks (20%) (Step 6)
- [ ] **Pipeline Spec** - `k0/contracts/pipelines/<pipeline_id>.v1.yaml` (Step 7)
- [ ] **Integration Test** - Test with runtime (10%) (Step 6)
- [ ] **Documentation** - Docstrings, contract description, README updates

---

## Additional Resources

### Key Documentation

1. **`k0/runtime/README.md`** - Runtime architecture, PipelineRunner, ModuleRegistry
2. **`k0/pipelines/MIGRATION_PLAN.md`** - Phase 2+ migration roadmap
3. **`k0/pipelines/protocol.py`** - PipelineContext, BusMessage definitions
4. **`k0/runtime/schemas.py`** - Pydantic models (ModuleContract, PipelineSpec)
5. **`k0/pipelines/QUICK_REFERENCE.md`** - Quick lookup for common patterns

### Architecture Diagrams

- **`architecture_diagrams/k0/k0_source_of_truth.mmd`** - System architecture
- **`architecture_diagrams/k0/p02_write_driver_architecture.mmd`** - P02 pipeline example

### Example Modules (Future)

```
k0/modules/
├── hippocampus/pattern_separate.py  ← This guide's example
├── affect/analyze.py
├── space/resolve_visibility.py
└── core/writer.py
```

---

**For questions or clarification, refer to:**

- **MIGRATION_PLAN.md** - Detailed Phase 2+ implementation roadmap
- **runtime/README.md** - Runtime infrastructure documentation
- **Tests** - `tests/k0/runtime/`, `tests/modules/`

**Status:** Phase 2 runtime infrastructure complete ✅. Ready for module development (Phase 6).
