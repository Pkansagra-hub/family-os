# Pipeline Infrastructure - Quick Reference

**For Future Development**

---

## Current State (After Phase 1)

### Pipeline Infrastructure Files

```
k0/pipelines/
├── __init__.py          # Exports: PipelineProtocol, BusMessage (from k0.bus), PipelineContext
├── protocol.py          # PipelineProtocol, PipelineContext definitions
├── loader.py            # discover_and_boot_pipelines()
├── MIGRATION_PLAN.md    # Detailed migration strategy
├── MIGRATION_STATUS.md  # Current status & validation
└── docs/                # Design documentation
```

### Integration Points

**Kernel Startup** (`k0/kernel/app.py:488-510`)

```python
from ..pipelines.loader import discover_and_boot_pipelines

pipelines = await discover_and_boot_pipelines(
    bus_dispatcher=bus_dispatcher,
    uow_factory=_unit_of_work_factory,
    config=pipeline_config_dict,
    logger=logger,
)
app.state.pipelines = pipelines
```

**Kernel Shutdown** (`k0/kernel/app.py:519-527`)

```python
for pipeline_id, pipeline in pipelines.items():
    await pipeline.on_shutdown()
```

---

## Adding a New Pipeline (Current System)

### Option A: Python Class (Current Paradigm)

**1. Create file:** `k0/pipelines/p02_write.py`

```python
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext, PipelineProtocol

class P02EpisodicWrite:
    # Contract
    pipeline_id = "P02_WRITE"
    contract_version = 1
    declared_topics = ["cognitive.memory.write.committed.v1"]
    concurrency = 1
    max_queue = 512
    required_caps = ["st_hipp_store.write"]

    async def on_startup(self, ctx: PipelineContext) -> None:
        self.syscalls = ctx.syscalls
        self.logger = ctx.logger
        self.config = ctx.config

    async def on_shutdown(self) -> None:
        pass

    async def handle(self, msg: BusMessage) -> None:
        # Process message
        pass
```

**2. Restart kernel** - Auto-discovered by loader

---

## Future: Declarative DAG System (Phase 2+)

### When Implemented, You Can

**1. Create pipeline spec:** `k0/contracts/pipelines/p02_write.v1.yaml`

```yaml
pipeline_id: P02_WRITE
version: v1
entry_topic: cognitive.memory.write.committed.v1
exit_topic: p02.write.complete.v1
dag:
  - id: stage_10_affect
    module: affect.analyze:v1
    after: [entry]

  - id: stage_20_space
    module: space.resolve_visibility:v1
    after: [stage_10_affect]

  - id: stage_30_hippocampus
    module: hippocampus.pattern_separate:v1
    after: [stage_20_space]
```

**2. Create module contracts:** `k0/contracts/modules/affect.analyze.v1.yaml`

```yaml
module_id: affect.analyze
version: v1
input_types: [cognitive.memory.write.committed.v1]
output_types: [affect.analyzed.v1]
latency_budget_ms: 5
side_effects: []
idempotent: true
```

**3. Implement module:** `k0/modules/affect/analyze.py`

```python
async def run(envelope: dict, syscalls, logger, config) -> dict:
    # Pure function, no pipeline coupling
    return {**envelope, "affect_valence": 0.8}
```

**4. Restart kernel** - Both YAML and Python pipelines discovered

---

## BusMessage Reference

### Unified Definition (`k0/bus/core.py`)

```python
@dataclass(slots=True, frozen=True)
class BusMessage:
    topic: str                          # Event topic
    payload: bytes                      # Event data (JSON/FlatBuffers)
    offset: int                         # WAL position
    trace_id: str | None = None        # Observability trace
    space_id: str | None = None        # Per-space ordering
    metadata: dict[str, Any] | None = None  # Routing context
```

### Usage in Pipelines

```python
from k0.bus import BusMessage

async def handle(self, msg: BusMessage) -> None:
    topic = msg.topic
    data = json.loads(msg.payload)
    trace = msg.trace_id
    space = msg.space_id
```

---

## PipelineProtocol Contract

### Required Class Properties (6)

```python
pipeline_id: str              # "P02_WRITE"
contract_version: int         # 1
declared_topics: Sequence[str]  # ["cognitive.memory.write.committed.v1"]
concurrency: int              # 1 (sequential) or 10+ (parallel)
max_queue: int               # 512 (typical)
required_caps: Sequence[str]  # ["st_hipp_store.write"]
```

### Required Methods (3)

```python
async def on_startup(self, ctx: PipelineContext) -> None:
    """Initialize resources"""

async def on_shutdown(self) -> None:
    """Clean up resources"""

async def handle(self, msg: BusMessage) -> None:
    """Process message"""
```

---

## Testing Pipelines

### Unit Test Pattern

```python
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext

async def test_pipeline_handle():
    pipeline = MyPipeline()

    ctx = PipelineContext(
        syscalls=mock_syscalls,
        config={},
        logger=mock_logger
    )
    await pipeline.on_startup(ctx)

    msg = BusMessage(
        topic="test.topic",
        payload=b'{"data": "value"}',
        offset=1
    )
    await pipeline.handle(msg)
```

### Integration Test Pattern

See `tests/k0/pipelines/test_loader.py` for loader integration examples.

---

## Common Patterns

### Pattern 1: Idempotency Check

```python
async def handle(self, msg: BusMessage) -> None:
    if await self._already_processed(msg.offset):
        return  # Skip duplicate

    # Process...
    await self._mark_processed(msg.offset)
```

### Pattern 2: Error Handling

```python
async def handle(self, msg: BusMessage) -> None:
    try:
        # Process...
        await self._emit_receipt(msg.offset, status="OK")
    except TransientError:
        raise  # Retry with backoff
    except PermanentError as e:
        self.logger.error(f"Permanent error: {e}")
        await self._emit_receipt(msg.offset, status="ERROR")
```

### Pattern 3: Capability-Gated Storage

```python
async def on_startup(self, ctx: PipelineContext) -> None:
    self.syscalls = ctx.syscalls  # Pre-validated capabilities

async def handle(self, msg: BusMessage) -> None:
    # Syscalls enforces required_caps before allowing access
    await self.syscalls.hipp_store_upsert(...)
```

---

## Troubleshooting

### Pipeline Not Discovered

**Check:**

- [ ] File named `p*.py` in `k0/pipelines/`
- [ ] Class has `pipeline_id` attribute
- [ ] All 6 properties present
- [ ] All 3 methods present

**Debug:**

```python
# Enable loader debug logging
logger.setLevel(logging.DEBUG)
```

### Contract Validation Failed

**Check:**

- [ ] `pipeline_id` matches filename (e.g., `P02_WRITE` for `p02_write.py`)
- [ ] `declared_topics` is non-empty sequence
- [ ] All methods are `async def`

### Pipeline Not Receiving Messages

**Check:**

- [ ] Topic subscription logged during boot
- [ ] BusDispatcher publishing to correct topic
- [ ] No exceptions in `on_startup()`

---

## Architecture Decisions

### Why Protocol (not ABC)?

Allows structural subtyping without explicit inheritance. Future `PipelineRunner` can implement protocol without modifying existing code.

### Why Class Properties (not instance)?

Enables contract validation before instantiation. Loader can check compatibility without running code.

### Why Frozen BusMessage?

Immutability prevents accidental modification in async handlers. Hashable for caching/deduplication.

### Why Single BusMessage?

Single source of truth prevents schema drift. Easy to evolve (add fields once, all code benefits).

---

## Migration Timeline (When Ready)

### Week 1-2: Runtime Layer

- Create `k0/runtime/module_registry.py`
- Create `k0/runtime/pipeline_runner.py`
- Define Pydantic schemas

### Week 3-4: Golden Path (P02)

- Create P02 YAML spec
- Implement 5-7 modules
- Extend loader for YAML support

### Week 5-6: Validation

- Test P02 end-to-end
- Benchmark performance
- Validate observability

### Week 7+: Scale

- Convert remaining pipelines
- Build module library
- Generate docs from contracts

---

## Key Files to Review

**Before modifying pipeline system:**

1. `k0/pipelines/MIGRATION_PLAN.md` - Detailed strategy
2. `k0/pipelines/MIGRATION_STATUS.md` - Current state
3. `k0/pipelines/protocol.py` - Interface definition
4. `k0/pipelines/loader.py` - Discovery logic

**For examples:**

1. `tests/k0/pipelines/test_protocol.py` - Protocol usage
2. `tests/k0/pipelines/test_loader.py` - Loader integration
3. `k0/kernel/app.py:488-527` - Kernel integration

---

## Questions?

**Consult:**

- `MIGRATION_PLAN.md` for detailed implementation steps
- `MIGRATION_STATUS.md` for current status and validation
- `protocol.py` for interface documentation
- Tests for usage patterns

**Key Principle:**
> Pipelines are declarative DAGs over a small module library.
> Everything else is data, not custom glue code.

---

**Status:** Infrastructure ready, waiting for runtime layer implementation
