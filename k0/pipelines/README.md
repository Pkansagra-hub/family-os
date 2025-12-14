# K0 Pipelines - Protocol & Discovery System

**Authoritative Source of Truth for Pipeline Development**

---

## Overview

The `k0/pipelines/` directory contains the **protocol definition** and **auto-discovery system** for all K0 pipelines. This is the foundational infrastructure that enables the kernel to discover, validate, boot, and orchestrate pipeline execution.

**Key Principle:**
> Pipelines implement `PipelineProtocol` and are auto-discovered by the kernel at startup. The loader validates contracts, grants capabilities, and subscribes pipelines to event topics.

---

## Architecture

### System Components

```
k0/pipelines/
├── __init__.py          # Public API: PipelineProtocol, PipelineContext, Pipeline
├── protocol.py          # PipelineProtocol interface, PipelineContext dataclass
├── loader.py            # discover_and_boot_pipelines() - auto-discovery engine
├── README.md            # This file - authoritative guide
├── MIGRATION_PLAN.md    # Phase 1-5 migration to declarative DAGs
└── QUICK_REFERENCE.md   # Quick lookup for common patterns
```

### Integration with Kernel

**Kernel Startup** (`k0/kernel/app.py:488-510`)
1. Kernel calls `discover_and_boot_pipelines()` during lifespan startup
2. Loader scans `k0/pipelines/p*.py` files for pipeline classes
3. Validates each class implements `PipelineProtocol`
4. Creates `Syscalls` adapter with granted capabilities
5. Calls `pipeline.on_startup(PipelineContext)`
6. Subscribes `pipeline.handle()` to declared topics
7. Stores pipeline instances in `app.state.pipelines`

**Kernel Shutdown** (`k0/kernel/app.py:519-527`)
1. Kernel calls `pipeline.on_shutdown()` for each pipeline
2. Records clean shutdown timestamp for crash fencing
3. Logs shutdown status

**Message Dispatch**
1. Envelope committed to WAL → `BusDispatcher` publishes `BusMessage`
2. `BusDispatcher` routes message to subscribed pipelines
3. Pipeline `handle(msg)` executes processing logic
4. Pipeline emits receipts, updates telemetry, marks processed

---

## Core Concepts

### PipelineProtocol

The canonical interface all pipelines must implement:

**Class-Level Properties** (6 required):
```python
pipeline_id: str              # "P02_WRITE" (must match filename pattern)
contract_version: int         # 1 (protocol version)
declared_topics: Sequence[str]  # ["cognitive.memory.write.committed.v1"]
concurrency: int              # 1 (sequential) or 10+ (parallel)
max_queue: int               # 512 (backpressure threshold)
required_caps: Sequence[str]  # ["st_hipp_store.write"]
```

**Lifecycle Methods** (3 required):
```python
async def on_startup(self, ctx: PipelineContext) -> None:
    """Initialize resources (called once at kernel boot)"""

async def on_shutdown(self) -> None:
    """Clean up resources (called once at kernel shutdown)"""

async def handle(self, msg: BusMessage) -> None:
    """Process message (called for each subscribed topic event)"""
```

### PipelineContext

Startup context provided to pipelines during `on_startup()`:

```python
@dataclass(frozen=True, slots=True)
class PipelineContext:
    syscalls: Syscalls         # Capability-gated storage adapter
    config: dict[str, Any]     # Pipeline-specific configuration
    logger: Logger             # Structured logger with trace support
```

**Security:** `syscalls` enforces `required_caps` before allowing storage access.

### BusMessage

The canonical event format (defined in `k0/bus/core.py`):

```python
@dataclass(slots=True, frozen=True)
class BusMessage:
    topic: str                 # Event topic
    payload: bytes             # Event data (JSON/FlatBuffers)
    offset: int                # WAL position (monotonic)
    trace_id: str | None       # Observability trace
    space_id: str | None       # Per-space ordering
    metadata: dict | None      # Routing context
```

---

## How to Create a Pipeline

### Step 1: Create Pipeline File

**Filename Convention:** `pNN_description.py` where `NN` is pipeline number (01-99)

Example: `p02_episodic_write.py`

**Auto-Discovery Rules:**
- Must start with `p` followed by a digit (e.g., `p01`, `p02`, `p10`)
- Loader filters `p*.py` → only includes files matching `p[0-9]*`
- Excludes `protocol.py` and other helper files

### Step 2: Implement PipelineProtocol

```python
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext, PipelineProtocol


class P02EpisodicWrite:
    """
    P02 Pipeline - Episodic Memory Write Path

    Processes committed memory.delta envelopes and writes to hippocampus storage.
    """

    # ===== Contract (Class-Level Properties) =====

    pipeline_id = "P02_EPISODIC_WRITE"
    contract_version = 1
    declared_topics = ["cognitive.memory.write.committed.v1"]
    concurrency = 1  # Sequential processing
    max_queue = 512
    required_caps = ["st_hipp_store.write"]

    # ===== Lifecycle Methods =====

    async def on_startup(self, ctx: PipelineContext) -> None:
        """Initialize pipeline resources."""
        self.syscalls = ctx.syscalls
        self.logger = ctx.logger
        self.config = ctx.config

        # Optional: Initialize ProcessPoolExecutor, models, connections
        self.logger.info(f"{self.pipeline_id} started")

    async def on_shutdown(self) -> None:
        """Clean up pipeline resources."""
        # Close executors, flush buffers, etc.
        self.logger.info(f"{self.pipeline_id} shutdown complete")

    async def handle(self, msg: BusMessage) -> None:
        """Process incoming message."""
        # 1. Idempotency check
        if await self._already_processed(msg.offset):
            return

        # 2. Parse payload
        import json
        event = json.loads(msg.payload)

        # 3. Core processing logic
        await self.syscalls.hipp_store_upsert(
            space_id=event["space_id"],
            event_id=event["event_id"],
            payload=event,
            cognitive_trace_id=msg.trace_id,
        )

        # 4. Emit receipt
        await self._emit_receipt(msg.offset, status="OK")

        # 5. Mark processed
        await self._mark_processed(msg.offset)

    # ===== Helper Methods =====

    async def _already_processed(self, offset: int) -> bool:
        """Check if message already processed (idempotency)."""
        # Query st_pipeline_processed table
        pass

    async def _emit_receipt(self, offset: int, status: str) -> None:
        """Emit processing receipt to st_pipeline_status."""
        pass

    async def _mark_processed(self, offset: int) -> None:
        """Record processed offset in st_pipeline_processed."""
        pass
```

### Step 3: Restart Kernel

Pipeline is auto-discovered on next kernel boot:

```bash
cd k0/deploy
./k0.ps1 -Command restart
```

**Boot Logs:**
```json
{"level": "INFO", "message": "Starting pipeline discovery in /app/k0/pipelines"}
{"level": "INFO", "message": "Loading pipeline: P02_EPISODIC_WRITE"}
{"level": "INFO", "message": "Contract validation passed for P02_EPISODIC_WRITE"}
{"level": "INFO", "message": "Subscribed P02_EPISODIC_WRITE to cognitive.memory.write.committed.v1"}
{"level": "INFO", "message": "Booted 1 pipelines: ['P02_EPISODIC_WRITE']"}
```

---

## Loader Behavior

### Discovery Process

**1. Scan Phase** (`loader.py:135-142`)
```python
# Filter to only match p[0-9]* pattern (exclude protocol.py)
all_p_files = pipeline_dir.glob("p*.py")
pipeline_modules = sorted([
    p for p in all_p_files
    if p.stem[0] == 'p' and len(p.stem) > 1 and p.stem[1].isdigit()
])
```

**2. Validation Phase** (`loader.py:_validate_contract()`)
- Checks 6 required class properties exist
- Checks 3 required lifecycle methods exist
- Validates `pipeline_id` matches filename (`P02_WRITE` == `p02_write.py`)
- Validates `declared_topics` is non-empty

**3. Boot Phase** (`loader.py:166-213`)
- Creates `Syscalls` adapter with granted capabilities from `required_caps`
- Creates `PipelineContext` with syscalls, config, logger
- Instantiates pipeline class
- Calls `pipeline.on_startup(ctx)`
- Subscribes `pipeline.handle` to each declared topic

**4. Error Handling**
- `ContractValidationError`: Stops boot (fail-fast)
- `ImportError`: Stops boot (fail-fast)
- `Exception` in `on_startup()`: Stops boot (fail-fast)

### Capability Gating

**Security Model:**
1. Pipeline declares `required_caps = ["st_hipp_store.write"]`
2. Loader creates `Syscalls(pipeline_id, granted_caps, uow_factory)`
3. `Syscalls` enforces capabilities before allowing storage operations
4. Unauthorized access → raises `CapabilityError`

**Common Capabilities:**
- `st_hipp_store.write` - Write to episodic memory
- `st_hipp_store.read` - Read episodic memory
- `working_memory.write` - Write to working memory
- `embeddings.read` - Query vector index
- `embeddings.write` - Insert embeddings

---

## Contract Validation

### Filename → pipeline_id Mapping

**Rule:** `pipeline_id` must match uppercase filename stem

| Filename | Expected pipeline_id | Valid? |
|----------|---------------------|--------|
| `p02_write.py` | `P02_WRITE` | ✅ |
| `p02_episodic_write.py` | `P02_EPISODIC_WRITE` | ✅ |
| `p10_consolidation.py` | `P10_CONSOLIDATION` | ✅ |
| `p02_write.py` | `P02` | ❌ Mismatch |
| `protocol.py` | (any) | ❌ Filtered out |

### Common Validation Errors

**Error: `Missing required attribute: pipeline_id`**
```python
# ❌ Wrong
class MyPipeline:
    pass

# ✅ Correct
class MyPipeline:
    pipeline_id = "P02_WRITE"
```

**Error: `pipeline_id mismatch: P02 != P02_WRITE`**
```python
# ❌ Wrong (file: p02_write.py)
pipeline_id = "P02"

# ✅ Correct (file: p02_write.py)
pipeline_id = "P02_WRITE"
```

**Error: `declared_topics cannot be empty`**
```python
# ❌ Wrong
declared_topics = []

# ✅ Correct
declared_topics = ["cognitive.memory.write.committed.v1"]
```

---

## Testing Pipelines

### Unit Test Pattern

```python
import pytest
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.pipelines.p02_episodic_write import P02EpisodicWrite


@pytest.mark.asyncio
async def test_pipeline_handle():
    # Arrange
    pipeline = P02EpisodicWrite()

    ctx = PipelineContext(
        syscalls=mock_syscalls,
        config={},
        logger=mock_logger,
    )
    await pipeline.on_startup(ctx)

    msg = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=b'{"space_id": "space-home", "event_id": "evt-001"}',
        offset=1,
        trace_id="trace-123",
    )

    # Act
    await pipeline.handle(msg)

    # Assert
    assert mock_syscalls.hipp_store_upsert.called
```

### Integration Test Pattern

```python
@pytest.mark.asyncio
async def test_pipeline_loader_integration():
    from k0.pipelines.loader import discover_and_boot_pipelines

    pipelines = await discover_and_boot_pipelines(
        bus_dispatcher=mock_bus,
        uow_factory=mock_uow,
        config={},
        logger=logger,
    )

    assert "P02_EPISODIC_WRITE" in pipelines
    assert len(pipelines["P02_EPISODIC_WRITE"].declared_topics) > 0
```

---

## Common Patterns

### Pattern 1: Idempotency Check

```python
async def handle(self, msg: BusMessage) -> None:
    # Check st_pipeline_processed table
    if await self._already_processed(msg.offset):
        self.logger.debug(f"Skipping duplicate offset {msg.offset}")
        return

    # Process...

    await self._mark_processed(msg.offset)
```

### Pattern 2: Error Handling & Retry

```python
async def handle(self, msg: BusMessage) -> None:
    try:
        # Core processing
        await self._process(msg)
        await self._emit_receipt(msg.offset, status="OK")
    except TransientError as e:
        # Retry with backoff (dispatcher handles this)
        raise
    except PermanentError as e:
        # Log and emit ERROR receipt (don't raise)
        self.logger.error(f"Permanent error: {e}")
        await self._emit_receipt(msg.offset, status="ERROR")
```

### Pattern 3: Capability-Gated Storage

```python
async def on_startup(self, ctx: PipelineContext) -> None:
    # Syscalls enforces required_caps
    self.syscalls = ctx.syscalls

async def handle(self, msg: BusMessage) -> None:
    # Raises CapabilityError if "st_hipp_store.write" not granted
    await self.syscalls.hipp_store_upsert(...)
```

### Pattern 4: CPU-Bound Work

```python
from concurrent.futures import ProcessPoolExecutor

async def on_startup(self, ctx: PipelineContext) -> None:
    self.executor = ProcessPoolExecutor(max_workers=2)

async def handle(self, msg: BusMessage) -> None:
    # Offload CPU-heavy work to process pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        self.executor,
        self._heavy_computation,
        msg.payload,
    )

async def on_shutdown(self) -> None:
    self.executor.shutdown(wait=True)
```

---

## Troubleshooting

### Pipeline Not Discovered

**Symptoms:**
- `Booted 0 pipelines: []` in kernel logs
- No error messages

**Checklist:**
- [ ] File named `pNN_*.py` (e.g., `p02_write.py`)
- [ ] File located in `k0/pipelines/` directory
- [ ] Class has `pipeline_id` attribute
- [ ] `pipeline_id` is a class attribute (not instance)

**Debug:**
```python
# Enable loader debug logging
import logging
logging.getLogger("k0.pipelines.loader").setLevel(logging.DEBUG)
```

### Contract Validation Failed

**Symptoms:**
- `ContractValidationError: Missing required attribute: X`
- Kernel fails to boot

**Checklist:**
- [ ] All 6 properties present (`pipeline_id`, `contract_version`, `declared_topics`, `concurrency`, `max_queue`, `required_caps`)
- [ ] All 3 methods present (`on_startup`, `on_shutdown`, `handle`)
- [ ] `pipeline_id` matches filename pattern
- [ ] `declared_topics` is non-empty

### Pipeline Not Receiving Messages

**Symptoms:**
- Pipeline booted successfully
- `handle()` never called

**Checklist:**
- [ ] Topic subscription logged during boot
- [ ] `BusDispatcher` publishing to correct topic
- [ ] No exceptions in `on_startup()`
- [ ] `declared_topics` matches published topic exactly

**Verify subscription:**
```bash
# Check kernel logs for:
{"message": "Subscribed P02_EPISODIC_WRITE to cognitive.memory.write.committed.v1"}
```

---

## Future: Declarative DAG System

### Planned Migration (Phase 2-5)

**Current State (Phase 1):** ✅ Complete
- Python class-based pipelines
- Auto-discovery via `PipelineProtocol`
- Capability-gated execution

**Future State (Phase 2-5):** 🚧 In Progress
- YAML-based pipeline specifications
- Reusable module library in `k0/modules/`
- Generic `PipelineRunner` executing DAGs
- Both paradigms coexist (backward compatible)

**Migration Plan:** See `MIGRATION_PLAN.md` for detailed roadmap.

### Example: Declarative Pipeline (Future)

**Pipeline Spec** (`k0/contracts/pipelines/p02_write.v1.yaml`):
```yaml
pipeline_id: P02_WRITE
version: v1
entry_topic: cognitive.memory.write.committed.v1
concurrency: 1
max_queue: 512
dag:
  - id: stage_10_affect
    module: affect.analyze:v1
    after: []

  - id: stage_20_space
    module: space.resolve_visibility:v1
    after: [stage_10_affect]

  - id: stage_30_hippocampus
    module: hippocampus.pattern_separate:v1
    after: [stage_20_space]
```

**Module Implementation** (`k0/modules/affect/analyze.py`):
```python
async def run(envelope: dict, syscalls, logger, config) -> dict:
    """Affect analysis module (reusable across pipelines)."""
    # Pure function - no pipeline coupling
    return {**envelope, "affect_valence": 0.8}
```

**Benefits:**
- Add 100+ modules without touching loader
- Compose pipelines from reusable modules
- Generate diagrams from YAML specs
- Version contracts independently

---

## Key Files

### Must Read Before Modifying

1. **`protocol.py`** - `PipelineProtocol` interface (canonical contract)
2. **`loader.py`** - Auto-discovery logic (how pipelines boot)
3. **`MIGRATION_PLAN.md`** - Future declarative DAG architecture
4. **`k0/kernel/app.py:488-527`** - Kernel integration (startup/shutdown)

### Reference Documentation

1. **`QUICK_REFERENCE.md`** - Quick lookup for common patterns
2. **`k0/bus/core.py`** - `BusMessage` definition
3. **`k0/kernel/syscalls.py`** - `Syscalls` capability enforcement
4. **Tests:** `tests/k0/pipelines/test_protocol.py`, `test_loader.py`

---

## Design Principles

### 1. Protocol-Based Contracts
- Use `Protocol` (not ABC) for structural subtyping
- Enables `PipelineRunner` to implement interface without inheritance
- Duck typing with type checking

### 2. Class-Level Properties
- Enables contract validation before instantiation
- Loader checks compatibility without running code
- Clear separation of contract vs implementation

### 3. Capability Security
- Least-privilege access via `required_caps`
- `Syscalls` enforces capabilities before storage access
- Fail-fast on unauthorized access

### 4. Fail-Fast Validation
- Stop kernel boot on first validation error
- Clear error messages for debugging
- No silent failures or degraded modes

### 5. Immutable Messages
- `BusMessage` is frozen (immutable)
- Prevents accidental modification in async handlers
- Hashable for caching/deduplication

---

## FAQ

**Q: Can I have multiple pipelines subscribe to the same topic?**
A: Yes. `BusDispatcher` calls all subscribed `handle()` methods.

**Q: How do I add configuration to my pipeline?**
A: Pass via `config` dict to `discover_and_boot_pipelines()`. Access in `on_startup()` via `ctx.config`.

**Q: Can pipelines communicate with each other?**
A: No direct communication. Pipelines communicate via events (publish → WAL → BusDispatcher → handle).

**Q: How do I test my pipeline without booting the kernel?**
A: Unit test by instantiating the class directly and calling lifecycle methods with mock objects.

**Q: Can I use threads in my pipeline?**
A: Use `ProcessPoolExecutor` for CPU-bound work. Avoid raw threads (breaks async runtime).

**Q: How do I handle backpressure?**
A: Set `max_queue` appropriately. When queue full, dispatcher returns `DEFERRED` status and client retries.

---

## Status

**Current State:** Phase 1 Complete ✅
- `PipelineProtocol` interface finalized
- Auto-discovery system operational
- Capability-gated execution working
- Kernel integration stable

**Current Phase:** Declarative YAML Pipelines Operational ✅
- `k0/runtime/` infrastructure complete
- `ModuleRegistry`, `PipelineRunner`, DAG builder implemented
- YAML-based pipeline specs supported (`p02_write.v1.yaml`)
- 16 modules operational in `k0/modules/` (M01-M17)
- P02_WRITE pipeline: 16 stages, 70+ column enrichment, atomic 2-table writes
- Backward compatibility maintained (both Python and YAML pipelines coexist)

---

**For detailed migration roadmap, see `MIGRATION_PLAN.md`**
**For quick reference patterns, see `QUICK_REFERENCE.md`**
