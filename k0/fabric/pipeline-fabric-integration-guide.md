# Pipeline-Fabric Integration Guide

**Status**: REFERENCE DOCUMENTATION
**Last Updated**: 2025-12-14
**Accuracy**: Code-verified (each section derived from actual implementation)

---

## Table of Contents

1. [Kernel Syscalls](#1-kernel-syscalls)
   - [1.9 Storage Tables Registry](#19-storage-tables-registry)
2. [Event Bus](#2-event-bus)
3. [Runtime Schemas](#3-runtime-schemas)
4. [Pipelines](#4-pipelines)
5. [Capability Fabric](#5-capability-fabric)
6. [Modules](#6-modules)
7. [Scheduler](#7-scheduler)
8. [Integration Patterns](#8-integration-patterns)
9. [Creating a New Pipeline (Step-by-Step)](#9-creating-a-new-pipeline-step-by-step)
10. [Quick Reference](#quick-reference)
    - [Naming Conventions](#naming-conventions)

---

## 1. Kernel Syscalls

**Source**: `k0/kernel/syscalls.py` (2667 lines)

### 1.1 Purpose

The Syscalls class provides **capability-gated storage access** for pipelines. It enforces the principle of least privilege - pipelines can only access storage resources they explicitly declare in their `required_caps`.

### 1.2 Architecture Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                     Pipeline Code                           │
│                         │                                   │
│                         ▼                                   │
│              ┌──────────────────┐                          │
│              │     Syscalls     │  ◄── Capability Gate     │
│              │                  │                           │
│              │  _require_cap()  │  ◄── Fail-Closed Check   │
│              └────────┬─────────┘                          │
│                       │                                     │
│                       ▼                                     │
│              ┌──────────────────┐                          │
│              │   UnitOfWork     │  ◄── Transaction Scope   │
│              └────────┬─────────┘                          │
│                       │                                     │
│                       ▼                                     │
│              ┌──────────────────┐                          │
│              │   SQLite/FAISS   │  ◄── Storage Layer       │
│              └──────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Security Properties

| Property | Implementation |
|----------|----------------|
| **Least Privilege** | Pipelines only get declared capabilities from `required_caps` |
| **Fail-Closed** | Missing capability raises `PermissionError` |
| **Audit Trail** | All operations logged with `trace_id` and `pipeline_id` |
| **Immutability** | Granted caps stored as `frozenset` (cannot be modified) |
| **No Ambient Authority** | Cannot access storage without Syscalls instance |

### 1.4 Initialization

```python
# In loader (when bootstrapping pipeline)
syscalls = Syscalls(
    pipeline_id="P02",
    granted_caps={"st_hipp_events.write", "st_hipp_events.read"},
    uow_factory=lambda: UnitOfWork(connection_pool),
)
```

### 1.5 Available Syscall Methods

| Method | Capability Required | Purpose |
|--------|---------------------|---------|
| `hipp_events_upsert(**row)` | `st_hipp_events.write` | Insert/update episodic events (70+ columns) |
| `hipp_events_query(...)` | `st_hipp_events.read` | Query episodic events |
| `hipp_events_update_embedding_status(...)` | `st_hipp_events.write` | Update embedding status |
| `pipeline_processed_upsert(...)` | `st_pipeline_processed.write` | Record pipeline completion (idempotency) |
| `vec_write(...)` | `st_vec.write` | Write vector records |
| `vec_query(...)` | `st_vec.read` | Query vector records |
| `vec_update_status(...)` | `st_vec.write` | Update vector status |
| `query_count(table, where)` | `<table>.read` | Generic count query for threshold triggers |
| `faiss_add(...)` | `faiss.write` | Add vectors to FAISS index |
| `faiss_add_batch(...)` | `faiss.write` | Batch add to FAISS |
| `faiss_search(...)` | `faiss.read` | Search FAISS index |
| `faiss_remove_batch(...)` | `faiss.write` | Remove from FAISS |
| `outbox_emit_batch(...)` | `st_outbox.write` | Emit to outbox |
| `embedding_enqueue(...)` | `st_vec.write` | Enqueue for embedding |
| `ultrabert_embed(...)` | `ultrabert.read` | Generate embeddings via UltraBert |
| `working_memory_write(...)` | `working_memory.write` | NOT IMPLEMENTED YET |
| `query_embeddings(...)` | `embeddings.read` | Query embeddings |
| `relationships_query(...)` | `relationships.read` | Query relationships |

> **Note**: This is a subset of available syscalls. For the complete syscall matrix including implementation status, performance data, and audit logging configuration, see:
> - **[k0_architecture_master.md Part 5.2: Syscall Matrix](../pipelines/k0_architecture_master.md#52-syscall-matrix)**
> - **Source**: `k0/kernel/syscalls.py` (2667 lines)

### 1.6 Capability Format

```
<table>.<operation>

Examples:
- st_hipp_events.write
- st_hipp_events.read
- st_vec.write
- faiss.read
- embeddings.read
- working_memory.write
```

### 1.7 Error Handling

```python
# If capability missing:
PermissionError: Pipeline P02 missing capability: st_vec.write. Granted: ['st_hipp_events.write']

# Security logging (ERROR level):
{
    "pipeline_id": "P02",
    "required_capability": "st_vec.write",
    "granted_caps": ["st_hipp_events.write"],
    "security_violation": true
}
```

### 1.8 Usage in Pipeline

```python
class P02EpisodicWrite:
    required_caps = ["st_hipp_events.write", "st_pipeline_processed.write"]

    async def on_startup(self, ctx: PipelineContext) -> None:
        self.syscalls = ctx.syscalls  # Store syscalls from context

    async def handle(self, msg: BusMessage) -> None:
        # Use syscalls for storage operations
        result = await self.syscalls.hipp_events_upsert(
            event_id=event["event_id"],
            wal_pos=msg.offset,
            cognitive_trace_id=msg.trace_id,
            # ... 70+ columns
        )
```

### 1.9 Storage Tables Registry

All storage tables in K0. Pipelines must declare capabilities for any table access.

| Table | Owner (Writer) | Readers | Purpose | Status |
|-------|----------------|---------|---------|--------|
| `st_wal` | Kernel | All Pipelines | Write-Ahead Log for event ordering | ✅ Active |
| `st_hipp_events` | P02 | P03, P04, Retention | Enriched hippocampus events (70+ columns) | ✅ Active |
| `st_vec` | P02 (M16) | P03, P08 | 768-dim UltraBERT embeddings, FAISS index ref | ✅ Active |
| `st_relationships` | P02 | Analytics | Family graph cache (SPOUSE_OF, PARENT_OF, etc.) | ✅ Active |
| `st_pipeline_processed` | All Pipelines | - | Idempotency tracking (pipeline_id, wal_pos) | ✅ Active |
| `st_outbox` | P02 (M17) | Dispatcher | Transactional outbox for event emission | ✅ Active |
| `st_dlq` | Kernel | Operators | Dead Letter Queue for failed messages | ✅ Active |
| `st_embedding_queue` | - | - | ❌ **DEPRECATED** - Use `st_vec` instead | ❌ Deprecated |

> **Complete table schemas**: See [k0_architecture_master.md Part 5.3: Storage Contract Definitions](../pipelines/k0_architecture_master.md#53-storage-contract-definitions)

---

## 2. Event Bus

**Source**: `k0/bus/core.py` (351 lines), `k0/bus/middleware.py` (155 lines)

### 2.1 Purpose

The `BusDispatcher` is the **post-commit dispatch coordinator** that fans out WAL (Write-Ahead Log) commits to pipelines and SSE (Server-Sent Events) endpoints. It provides topic-based subscriptions with middleware support.

### 2.2 Architecture Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                      WAL Commit                             │
│                          │                                  │
│                          ▼                                  │
│               ┌──────────────────┐                         │
│               │   BusDispatcher  │                         │
│               │                  │                         │
│               │  dispatch(msgs)  │  ◄── Monotonic ordering │
│               └────────┬─────────┘                         │
│                        │                                    │
│            ┌───────────┼───────────┐                       │
│            ▼           ▼           ▼                       │
│       ┌────────┐  ┌────────┐  ┌────────┐                  │
│       │Pipeline│  │Pipeline│  │  SSE   │                  │
│       │  P02   │  │  P08   │  │ Client │                  │
│       └────────┘  └────────┘  └────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 BusMessage (Canonical Event Format)

```python
@dataclass(slots=True, frozen=True)
class BusMessage:
    """Immutable view of a post-commit WAL record."""

    topic: str              # e.g., "cognitive.memory.write.committed.v1"
    payload: bytes          # JSON or FlatBuffers
    offset: int             # Monotonic WAL position (st_wal.pos)
    trace_id: str | None    # Cognitive trace ID for observability
    space_id: str | None    # Space ID for per-space ordering
    metadata: dict | None   # Additional routing context
```

### 2.4 BusDispatcher Initialization

```python
from k0.bus import BusDispatcher
from k0.qos import Scheduler

scheduler = Scheduler()
dispatcher = BusDispatcher(
    scheduler=scheduler,
    port="bus",
    default_band="GREEN",
    token_cost=1,
    middlewares=[
        timestamp_middleware(),
        latency_metrics_middleware(metrics),
        tracing_middleware(tracer_factory=tracer_factory),
    ],
)
```

### 2.5 Subscription Methods

| Method | Purpose | Use Case |
|--------|---------|----------|
| `subscribe(topic, handler)` | Subscribe to specific topic | Pipeline handlers |
| `subscribe("*", handler)` | Wildcard (all topics) | Broadcast handlers |
| `tap(handler)` | Observability-only (all messages) | Metrics, logging |
| `register_sink(sink)` | **DEPRECATED** - use `subscribe()` | Legacy code |

### 2.6 Topic-Based Dispatch (O(k) Lookup)

```python
# Pipeline subscribes to specific topic
dispatcher.subscribe("cognitive.memory.write.committed.v1", pipeline.handle)

# Observability tap gets everything
dispatcher.tap(metrics_sink)

# Handler resolution at dispatch time:
# 1. Exact topic match
# 2. Wildcard "*" subscriptions
# 3. Legacy _sinks (backward compatibility)
```

### 2.7 Middleware Chain

Middleware wraps the fan-out with cross-cutting concerns:

| Middleware | Purpose |
|------------|---------|
| `timestamp_middleware` | Records wall-clock and monotonic timestamps |
| `latency_metrics_middleware` | Emits `bus_dispatch_latency_seconds` histogram |
| `tracing_middleware` | Propagates cognitive trace IDs, emits spans |

```python
# Middleware execution order:
# 1. timestamp_middleware → sets started_at, monotonic_start
# 2. latency_metrics_middleware → starts timer
# 3. tracing_middleware → attaches trace context
# 4. _fan_out() → calls all handlers
# 5. Middleware unwinds in reverse order
```

### 2.8 Dispatch Flow

```python
async def dispatch(self, messages: Iterable[BusMessage]) -> None:
    """Dispatch messages in WAL order using scheduler tokens."""
    batch = sorted(messages, key=lambda m: m.offset)

    async with self._lock:  # Single writer
        for message in batch:
            self._ensure_monotonic(message.offset)  # Ordering check
            await self._dispatch_single(message)
            self._last_offset = message.offset
```

### 2.9 BusDispatchContext

```python
@dataclass(slots=True)
class BusDispatchContext:
    """Runtime context exposed to middleware and sinks."""

    message: BusMessage
    band: str                 # QoS band (GREEN/AMBER/RED)
    port: str                 # Scheduler port
    token_cost: int           # QoS token cost
    started_at: datetime      # Wall-clock start
    completed_at: datetime    # Wall-clock end
    duration_seconds: float   # Elapsed time
    monotonic_start: float    # perf_counter() start
    monotonic_end: float      # perf_counter() end
    trace_id: str             # Cognitive trace ID
```

### 2.10 Current Context Access

```python
from k0.bus import current_dispatch_context

async def my_handler(msg: BusMessage) -> None:
    ctx = current_dispatch_context()
    if ctx:
        print(f"Processing with trace: {ctx.trace_id}")
```

---

## 3. Runtime Schemas

**Source**: `k0/runtime/schemas.py` (685 lines)

### 3.1 Purpose

Runtime schemas define the **Pydantic models** for all declarative configurations: pipeline specs, trigger specs, module contracts, and capability providers. These are loaded from YAML files and validated at boot time.

### 3.2 Schema Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    PipelineSpec                             │
│                         │                                   │
│    ┌────────────────────┼────────────────────┐             │
│    ▼                    ▼                    ▼             │
│ TriggerSpec[]      StageSpec[]        fabric_actions[]     │
│                         │                                   │
│                         ▼                                   │
│                    ModuleContract                           │
│                         │                                   │
│         ┌───────────────┼───────────────┐                  │
│         ▼               ▼               ▼                  │
│  FailureMode[]   fabric_capabilities[]  FabricContextPolicy│
└─────────────────────────────────────────────────────────────┘
```

### 3.3 TriggerType Enum

```python
class TriggerType(str, Enum):
    """Types of pipeline triggers."""

    # Phase 1 (Implemented)
    INTERVAL = "interval"    # Fire at fixed intervals
    THRESHOLD = "threshold"  # Fire when row count exceeds threshold
    MANUAL = "manual"        # Fire on explicit request

    # Phase 2 (Partially Implemented)
    CRON = "cron"            # Fire on cron schedule (IMPLEMENTED - requires croniter)
    IDLE = "idle"            # Fire after idle period (NOT YET IMPLEMENTED)
```

### 3.4 TriggerSpec Model

```python
class TriggerSpec(BaseModel):
    id: str                          # Pattern: ^[a-z0-9_]+$
    type: TriggerType                # INTERVAL, THRESHOLD, MANUAL, etc.

    # Interval trigger fields
    interval_seconds: int | None     # 1-86400 seconds

    # Cron trigger fields
    cron_expression: str | None      # Standard cron expression

    # Threshold trigger fields
    table: str | None                # Table to monitor
    condition: str | None            # SQL WHERE clause
    threshold_count: int | None      # Count to trigger
    check_interval_seconds: int      # Default: 60

    # Idle trigger fields
    idle_seconds: int | None         # Idle time before trigger (seconds)
    min_pending: int | None          # Default: None (no minimum)

    # Common fields
    batch_size: int | None           # Batch size for processing
    catch_up_enabled: bool           # Default: True
```

### 3.5 TriggerSpec Validation Examples

```yaml
# Interval trigger (every 5 minutes)
- id: consolidation_interval
  type: interval
  interval_seconds: 300

# Threshold trigger (when 50+ vectors pending)
- id: faiss_indexer_threshold
  type: threshold
  table: st_vec
  condition: "status = 'READY'"
  threshold_count: 50
  check_interval_seconds: 30

# Manual trigger (on-demand)
- id: consolidation_manual
  type: manual
```

### 3.6 StageSpec Model

```python
class StageSpec(BaseModel):
    id: str                  # Pattern: ^[a-z0-9_]+$
    module: str              # Pattern: ^[a-z_]+\.[a-z_]+(:[a-z0-9]+)?$
    after: list[str] = []    # Dependencies (DAG edges)
    config: dict = {}        # Stage-specific config overrides
    condition: str | None    # Optional condition (future)
```

### 3.7 PipelineSpec Model

```python
class PipelineSpec(BaseModel):
    pipeline_id: str              # Pattern: ^P[0-9]{2}_[A-Z_]+$
    version: str                  # Pattern: ^v\d+$ (e.g., "v1")

    # Event-driven activation
    entry_topic: str | None       # Topic that triggers pipeline
    exit_topic: str | None        # Topic emitted on completion

    # Concurrency control
    concurrency: int = 1          # 1-100
    max_queue: int = 512          # 1-10000

    # DAG definition
    dag: list[StageSpec]          # min_length=1

    # Configuration
    config: dict = {}
    description: str | None
    required_capabilities: list[str] = []

    # Scheduler integration (Issue 1.1.4)
    triggers: list[TriggerSpec] = []

    # Fabric integration
    fabric_actions: list[str] = []
```

### 3.8 ModuleContract Model

```python
class ModuleContract(BaseModel):
    module_id: str            # Pattern: ^[a-z_]+\.[a-z_]+$
    version: str              # Pattern: ^v\d+$

    # Event types
    input_event_types: list[str] = []
    output_event_types: list[str] = []

    # Performance contract
    latency_budget_ms: int    # 1-10000ms

    # Side effects
    side_effects: list[str] = []   # Format: "operation:resource"
    idempotent: bool = True
    failure_modes: list[FailureMode] = []

    # Fabric integration (Issue 1.1.3)
    fabric_callable: bool = False
    fabric_capabilities: list[str] = []
    fabric_context_policy: FabricContextPolicy = FabricContextPolicy.INHERIT

    @property
    def full_id(self) -> str:
        return f"{self.module_id}:{self.version}"
```

### 3.9 CapabilityProvider Model

```python
class ProviderType(str, Enum):
    MODULE = "module"
    PIPELINE = "pipeline"

class FabricContextPolicy(str, Enum):
    INHERIT = "inherit"      # Inherit caller's syscalls
    ISOLATED = "isolated"    # Provider uses own context
    SYNTHETIC = "synthetic"  # Fabric creates synthetic context

class CapabilityProvider(BaseModel):
    type: ProviderType

    # Module provider fields
    module_id: str | None    # Pattern: ^[a-z_]+\.[a-z_]+(:[a-z0-9]+)?$

    # Pipeline provider fields
    pipeline_id: str | None
    request_topic: str | None
    response_topic: str | None

    # Common fields
    priority: int = 1        # 1-100 (lower = higher priority)
    condition: str = "always"
    latency_budget_ms: int | None
    timeout_ms: int | None
```

### 3.10 Validation Rules

| Model | Field | Validation |
|-------|-------|------------|
| TriggerSpec | type=INTERVAL | `interval_seconds` required |
| TriggerSpec | type=THRESHOLD | `table` and `threshold_count` required |
| TriggerSpec | type=CRON | `cron_expression` required |
| TriggerSpec | type=IDLE | `idle_seconds` required |
| CapabilityProvider | type=MODULE | `module_id` required |
| CapabilityProvider | type=PIPELINE | `pipeline_id`, `request_topic`, `response_topic` required |
| PipelineSpec | dag | No cycles, all dependencies must exist |
| ModuleContract | side_effects | Format: `operation:resource` where operation ∈ {read, write, emit} |

---

## 4. Pipelines

**Source**: `k0/pipelines/protocol.py` (362 lines)

### 4.1 Purpose

Pipelines are the **primary processing units** in K0. They implement the `PipelineProtocol` interface and are auto-discovered by the loader at boot time.

### 4.2 PipelineProtocol Interface

```python
@runtime_checkable
class PipelineProtocol(Protocol):
    """Canonical interface for K0 pipelines."""

    # Class-level contract (required attributes)
    pipeline_id: str              # e.g., "P02"
    contract_version: int         # e.g., 1
    declared_topics: Sequence[str]  # Topics to subscribe
    concurrency: int              # Max concurrent handlers
    max_queue: int                # Max pending messages
    required_caps: Sequence[str]  # Capability requirements

    # Lifecycle methods
    async def on_startup(self, ctx: PipelineContext) -> None: ...
    async def on_shutdown(self) -> None: ...
    async def handle(self, msg: BusMessage) -> None: ...
```

> **Trigger-Driven Pipelines**: Pipelines activated by scheduler triggers (INTERVAL, THRESHOLD, MANUAL) implement `execute(trigger_event: TriggerEvent)` instead of (or in addition to) `handle()`. The `handle()` method is for **event-driven** pipelines that subscribe to bus topics. See [§9.4 Event-Driven vs Trigger-Driven](#94-event-driven-vs-trigger-driven) for details.

### 4.3 PipelineContext

```python
@dataclass(frozen=True, slots=True)
class PipelineContext:
    """Context provided to pipelines during on_startup()."""

    syscalls: Any                    # Capability-gated storage adapter
    config: dict[str, Any]           # Pipeline-specific configuration
    logger: Logger                   # Structured logger with trace_id
    preloaded_models: dict | None    # Optional preloaded NLP models
    bus_dispatcher: Any | None       # Optional BusDispatcher
    fabric: CapabilityFabric | None  # Optional CapabilityFabric (ADR-K004)
```

### 4.4 Class-Level Properties

| Property | Type | Description |
|----------|------|-------------|
| `pipeline_id` | `str` | Unique ID, e.g., "P02", "P03" |
| `contract_version` | `int` | Protocol version for compatibility |
| `declared_topics` | `Sequence[str]` | Topics this pipeline subscribes to |
| `concurrency` | `int` | Max concurrent handlers (1 = sequential) |
| `max_queue` | `int` | Max pending before backpressure |
| `required_caps` | `Sequence[str]` | Capability requirements |

### 4.5 Lifecycle Methods

#### on_startup(ctx: PipelineContext)

Called once at kernel boot, before topic subscription.

```python
async def on_startup(self, ctx: PipelineContext) -> None:
    # 1. Store context components
    self.syscalls = ctx.syscalls
    self.logger = ctx.logger
    self.config = ctx.config
    self.fabric = ctx.fabric  # For capability-based calls

    # 2. Initialize resources
    self.executor = ProcessPoolExecutor(max_workers=2)

    # 3. Pre-load models if needed
    if ctx.preloaded_models:
        self.nlp = ctx.preloaded_models.get("spacy")

    ctx.logger.info(f"{self.pipeline_id} started")
```

#### on_shutdown()

Called at kernel shutdown for cleanup.

```python
async def on_shutdown(self) -> None:
    if hasattr(self, 'executor'):
        self.executor.shutdown(wait=True)
    self.logger.info(f"{self.pipeline_id} shutdown complete")
```

#### handle(msg: BusMessage)

Core processing method, called for each subscribed topic event.

```python
async def handle(self, msg: BusMessage) -> None:
    # 1. Idempotency check
    if await self._already_processed(msg.offset):
        return

    # 2. Parse payload
    event = json.loads(msg.payload)

    # 3. Core work (using syscalls)
    await self.syscalls.hipp_events_upsert(
        event_id=event["event_id"],
        wal_pos=msg.offset,
        cognitive_trace_id=msg.trace_id,
        # ... more fields
    )

    # 4. Optional: Use fabric for capability calls
    if self.fabric:
        score = self.fabric.invoke(
            "score_salience",
            content=event["text"],
        )

    # 5. Record processed
    await self._mark_processed(msg.offset)
```

### 4.6 Processing Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                    handle(msg) Flow                         │
│                                                             │
│  ┌─────────────┐                                           │
│  │ Idempotency │ ─── Already processed? ──► Skip           │
│  │   Check     │                                           │
│  └──────┬──────┘                                           │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────┐                                           │
│  │ Parse       │                                           │
│  │ Payload     │                                           │
│  └──────┬──────┘                                           │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────┐     ┌─────────────┐                       │
│  │ Core Work   │ ──► │  Syscalls   │ ──► Storage           │
│  │             │     └─────────────┘                       │
│  │             │     ┌─────────────┐                       │
│  │             │ ──► │   Fabric    │ ──► Capabilities      │
│  └──────┬──────┘     └─────────────┘                       │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────┐                                           │
│  │ Record      │                                           │
│  │ Processed   │                                           │
│  └─────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

### 4.7 Error Handling Strategy

| Error Type | Behavior |
|------------|----------|
| Transient | Raise exception → dispatcher retries with backoff |
| Permanent | Log + emit ERROR receipt → don't raise |
| DLQ | After 5 retries → moved to st_dlq |

### 4.8 Performance Guidelines

| Concern | Guideline |
|---------|-----------|
| Target latency | P95 < 100ms for fast pipelines |
| CPU-bound work | Use `ProcessPoolExecutor` (non-blocking) |
| IO-bound work | Use `async/await` (concurrent) |
| Startup time | < 100ms (blocks kernel boot) |
| Shutdown time | < 5 seconds (timeout enforced) |

### 4.9 Concurrency Guidelines

| Pipeline Type | Concurrency | Max Queue |
|---------------|-------------|-----------|
| CPU-bound | 1-2 | 64-128 |
| IO-bound | 10-50 | 512-1024 |
| Memory-sensitive | 1 | 64-128 |
| Fast (< 50ms) | 1-10 | 512-1024 |
| Slow (> 500ms) | 1-5 | 128-256 |

---

## 5. Capability Fabric

**Source**: `k0/fabric/fabric.py` (435 lines), `k0/fabric/registry.py` (459 lines), `k0/fabric/messages.py` (204 lines)

### 5.1 Purpose

The CapabilityFabric provides a **request/reply layer by capability name**. It sits above the event bus, enabling modules to invoke capabilities without knowing the concrete provider implementation.

### 5.2 Architecture (ADR-K004 Layer 2)

```
┌─────────────────────────────────────────────────────────────┐
│                     Caller (Pipeline/Module)                │
│                              │                              │
│                              ▼                              │
│                  ┌──────────────────────┐                  │
│                  │   CapabilityFabric   │                  │
│                  │                      │                  │
│                  │  invoke(capability)  │                  │
│                  └───────────┬──────────┘                  │
│                              │                              │
│                              ▼                              │
│                  ┌──────────────────────┐                  │
│                  │  CapabilityRegistry  │                  │
│                  │                      │                  │
│                  │  resolve(capability) │                  │
│                  └───────────┬──────────┘                  │
│                              │                              │
│          ┌───────────────────┼───────────────────┐         │
│          ▼                   ▼                   ▼         │
│    ┌──────────┐       ┌──────────┐       ┌──────────┐     │
│    │ Module A │       │ Module B │       │ Pipeline │     │
│    │ (pri: 1) │       │ (pri: 2) │       │ (pri: 3) │     │
│    └──────────┘       └──────────┘       └──────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 CapabilityRequest

```python
@dataclass
class CapabilityRequest:
    capability: str              # e.g., "score_salience"
    payload: dict[str, Any]      # Arguments to handler
    request_id: str              # UUID for tracing
    timeout_ms: int = 100        # Request timeout
    caller_id: str | None        # Calling module/pipeline
    trace_id: str | None         # Distributed trace ID

    # Monotonic timing (clock-jump safe)
    created_mono: float          # time.monotonic() at creation
    deadline_mono: float         # Computed deadline
    created_wall: float          # time.time() for logging only

    def elapsed_ms(self) -> float: ...
    def remaining_ms(self) -> float: ...  # For budget propagation
    def is_expired(self) -> bool: ...
```

### 5.4 CapabilityResponse

```python
@dataclass
class CapabilityResponse:
    request_id: str
    status: RequestStatus        # SUCCESS, ERROR, TIMEOUT
    result: Any = None           # Result on success
    error_message: str | None    # Error details
    provider_id: str | None      # Which provider handled
    handler_ms: float            # Handler execution time
    e2e_ms: float               # End-to-end latency
    timeout_ms: float | None     # Original timeout

    @property
    def is_success(self) -> bool: ...
    @property
    def is_error(self) -> bool: ...
    @property
    def is_timeout(self) -> bool: ...

    # Factory methods
    @classmethod
    def success(cls, ...) -> CapabilityResponse: ...
    @classmethod
    def error(cls, ...) -> CapabilityResponse: ...
    @classmethod
    def timeout(cls, ...) -> CapabilityResponse: ...
```

### 5.5 ResolutionStrategy

```python
class ResolutionStrategy(str, Enum):
    FIRST = "first"           # First matching provider
    PRIORITY = "priority"     # Lowest priority value wins (default)
    ROUND_ROBIN = "round_robin"  # Distribute across providers
```

### 5.6 RegisteredProvider

```python
@dataclass
class RegisteredProvider:
    capability: str
    provider: CapabilityProvider
    handler: Callable | None     # Resolved handler function

    # Runtime metrics
    call_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0

    @property
    def provider_id(self) -> str: ...   # module_id or pipeline_id
    @property
    def avg_latency_ms(self) -> float: ...
```

### 5.7 CapabilityRegistry

```python
@dataclass
class CapabilityRegistry:
    _providers: dict[str, list[RegisteredProvider]]
    _round_robin_index: dict[str, int]
    _lock: threading.RLock

    def register(capability, provider, handler) -> None
    def unregister(capability, provider_id) -> bool
    def resolve(capability, strategy) -> RegisteredProvider | None
    def list_capabilities() -> list[str]
    def list_providers(capability) -> list[RegisteredProvider]
    def bind_handler(capability, provider_id, handler) -> bool
    def record_call(capability, provider_id, latency_ms, error) -> None
    def has_capability(capability) -> bool
    def clear() -> None

    # Thread-safe async methods
    async def register_async(...) -> None
    def resolve_safe(...) -> RegisteredProvider | None  # Copy-on-read
    async def record_call_async(...) -> None
```

### 5.8 CapabilityFabric

```python
class CapabilityFabric:
    _registry: CapabilityRegistry
    _executor: ThreadPoolExecutor  # For timeout-enforced execution

    # Singleton pattern
    @classmethod
    def get_instance(cls) -> CapabilityFabric
    @classmethod
    def reset_instance(cls) -> None

    # Core methods
    def invoke(
        capability: str,
        timeout_ms: int = 100,
        caller_id: str | None = None,
        trace_id: str | None = None,
        strategy: ResolutionStrategy = PRIORITY,
        **kwargs,
    ) -> Any

    def call(request: CapabilityRequest, strategy) -> CapabilityResponse

    # Introspection
    def has_capability(capability) -> bool
    def list_capabilities() -> list[str]
    def get_stats() -> dict[str, Any]
```

### 5.9 Exception Types

| Exception | When Raised |
|-----------|-------------|
| `CapabilityNotFoundError` | Capability not registered |
| `CapabilityTimeoutError` | Request exceeded timeout |
| `CapabilityInvocationError` | Handler raised exception |

### 5.10 Timeout Enforcement

The fabric uses `ThreadPoolExecutor` with real timeout enforcement:

```python
# Handler submitted to thread pool
future = self._executor.submit(handler, **payload)

# Wait with timeout (remaining budget)
try:
    result = future.result(timeout=remaining_ms / 1000.0)
except TimeoutError:
    # Handler may still be running, but response returned immediately
    return CapabilityResponse.timeout(...)
```

### 5.11 Usage Examples

```python
# Simple invocation
fabric = get_capability_fabric()
score = fabric.invoke("score_salience", content="Hello world")

# With full control
request = CapabilityRequest(
    capability="score_salience",
    payload={"content": "Hello"},
    timeout_ms=50,
    caller_id="P02_WRITE",
)
response = fabric.call(request)
if response.is_success:
    print(f"Score: {response.result}")
elif response.is_timeout:
    print(f"Timed out after {response.timeout_ms}ms")

# In pipeline context
class P02Write:
    async def on_startup(self, ctx: PipelineContext) -> None:
        self.fabric = ctx.fabric

    async def handle(self, msg: BusMessage) -> None:
        if self.fabric:
            result = self.fabric.invoke(
                "generate_embedding",
                text=event["text"],
                timeout_ms=200,
            )
```

### 5.12 Metrics Tracking

```python
# Recorded on every call
registry.record_call(
    capability="score_salience",
    provider_id="salience.score:v1",
    latency_ms=3.5,
    error=False,
    status="success",
    caller_id="P02_WRITE",
    trace_id="trace-123",
    strategy="priority",
)

# Get stats
stats = fabric.get_stats()
# {
#     "total_calls": 1000,
#     "total_errors": 5,
#     "total_timeouts": 2,
#     "pending_requests": 0,
#     "registry": { ... per-capability stats }
# }
```

---

## 6. Modules

**Source**: `k0/modules/` directory, `k0/fabric/loader.py` (243 lines)

### 6.1 Purpose

Modules are **reusable processing units** that can be invoked by pipelines either directly or via the CapabilityFabric. They provide specific capabilities like scoring, embedding generation, or pattern separation.

### 6.2 Module Directory Structure

```
k0/modules/
├── activity/          # Activity type classification
├── affect/            # Sentiment/affect analysis
├── builders/          # Row builders for storage
├── context/           # Context resolution
├── core/              # Core processing modules
├── embedding/         # Embedding generation
├── hippocampus/       # Pattern separation, novelty
├── salience/          # Salience scoring
├── social/            # Social relationship analysis
└── space/             # Space/visibility resolution
```

### 6.3 ModuleContract Schema

Modules are defined via YAML contracts in `k0/contracts/modules/`:

```yaml
# Example: hippocampus.pattern_separate.v1.yaml
module_id: hippocampus.pattern_separate
version: v1
description: "Pattern separation via hippocampus"

# Event types
input_event_types:
  - p02.write.requested.v1
output_event_types:
  - p02.hippocampus.pattern_separated.v1

# Performance contract
latency_budget_ms: 15

# Side effects (storage access)
side_effects:
  - read:st_hipp_events
  - write:st_hipp_events

idempotent: true

# Failure modes
failure_modes:
  - code: NOVELTY_SCORE_MISSING
    policy: drop

# Fabric integration
fabric_callable: true
fabric_capabilities:
  - pattern_separate
fabric_context_policy: inherit
```

### 6.4 Capability Registration Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    App Bootstrap                            │
│                         │                                   │
│                         ▼                                   │
│          ┌──────────────────────────┐                      │
│          │ load_capability_definitions │                   │
│          │                            │                    │
│          │ k0/contracts/capabilities/ │                    │
│          │      *.yaml                │                    │
│          └────────────┬───────────────┘                    │
│                       │                                     │
│                       ▼                                     │
│          ┌──────────────────────────┐                      │
│          │ register_capabilities    │                      │
│          │                          │                      │
│          │ For each capability:     │                      │
│          │ 1. Resolve module handler│                      │
│          │ 2. Register provider     │                      │
│          └────────────┬───────────────┘                    │
│                       │                                     │
│                       ▼                                     │
│          ┌──────────────────────────┐                      │
│          │  CapabilityRegistry      │                      │
│          │                          │                      │
│          │  score_salience → handler│                      │
│          │  pattern_separate → ...  │                      │
│          └──────────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### 6.5 Capability Loader Functions

```python
from k0.fabric.loader import (
    load_capability_definitions,
    register_capabilities_from_definitions,
    discover_and_register_capabilities,
    get_capability_loader_stats,
)

# Full discovery and registration (call at boot)
provider_count = discover_and_register_capabilities(
    module_registry=module_registry,
    contracts_dir=Path("k0/contracts/capabilities"),
)

# Or step by step
definitions = load_capability_definitions()
registered = register_capabilities_from_definitions(
    definitions,
    module_registry=module_registry,
)

# Check stats
stats = get_capability_loader_stats()
# {"total_capabilities": 6, "total_providers": 6}
```

### 6.6 Capability Definition YAML

```yaml
# k0/contracts/capabilities/core.v1.yaml
version: v1

capabilities:
  score_salience:
    description: "Compute salience score for content"
    default_timeout_ms: 100
    providers:
      - type: module
        module_id: salience.score:v1
        priority: 1
        condition: always

  pattern_separate:
    description: "Pattern separation via hippocampus"
    default_timeout_ms: 200
    providers:
      - type: module
        module_id: hippocampus.pattern_separate:v1
        priority: 1

  generate_embedding:
    description: "Generate embedding vector"
    default_timeout_ms: 500
    providers:
      - type: module
        module_id: embedding.generate:v1
        priority: 1
```

### 6.7 Module Handler Requirements

When a module is registered as a capability provider:

1. **Handler must be callable**: Function or method accepting `**kwargs`
2. **Input via payload**: All arguments passed via `payload` dict
3. **Return value**: Handler return value becomes `response.result`
4. **Exceptions**: Raised exceptions result in `CapabilityInvocationError`

```python
# Module handler signature
def score_salience(
    content: str,
    participants: list[str] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Score content salience."""
    score = compute_salience(content, participants)
    return {"salience_score": score, "factors": [...]}

# Registration
registry.register("score_salience", provider, handler=score_salience)

# Invocation
result = fabric.invoke(
    "score_salience",
    content="Important meeting tomorrow",
    participants=["Alice", "Bob"],
)
# result = {"salience_score": 0.85, "factors": [...]}
```

### 6.8 FabricContextPolicy

| Policy | Description |
|--------|-------------|
| `INHERIT` | Inherit caller's syscalls (capability intersection) |
| `ISOLATED` | Provider uses its own context only |
| `SYNTHETIC` | Fabric creates synthetic context |

### 6.9 Handler Late Binding

Handlers can be bound after registration:

```python
# Register without handler
registry.register("score_salience", provider, handler=None)

# Later, bind handler
registry.bind_handler("score_salience", "salience.score:v1", handler_fn)
```

---

## 7. Scheduler

**Source**: `k0/scheduler/scheduler.py` (573 lines), `k0/scheduler/triggers.py` (521 lines), `k0/scheduler/concurrency.py` (287 lines), `k0/scheduler/audit.py` (257 lines)

### 7.1 Purpose

The Scheduler is **Layer 3 of the Capability Mesh Architecture** (ADR-K004). It provides declarative trigger-based pipeline activation, managing pipeline registration, trigger engines, and execution coordination.

### 7.2 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PipelineScheduler                        │
│                          │                                  │
│    ┌─────────────────────┼─────────────────────┐           │
│    │                     │                     │           │
│    ▼                     ▼                     ▼           │
│ ┌──────────┐      ┌──────────┐      ┌──────────┐          │
│ │ Interval │      │Threshold │      │  Manual  │          │
│ │ Trigger  │      │ Trigger  │      │ Trigger  │          │
│ │ Engine   │      │ Engine   │      │ Engine   │          │
│ └────┬─────┘      └────┬─────┘      └────┬─────┘          │
│      │                 │                 │                 │
│      └─────────────────┼─────────────────┘                 │
│                        │                                    │
│                        ▼                                    │
│            ┌───────────────────┐                           │
│            │  SingleFlightGate │ ◄── Concurrency Control   │
│            └─────────┬─────────┘                           │
│                      │                                      │
│                      ▼                                      │
│            ┌───────────────────┐                           │
│            │ Pipeline Executor │ ◄── Callback              │
│            └───────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Core Components

#### PipelineState Enum

```python
class PipelineState(Enum):
    REGISTERED = "registered"   # Pipeline registered, not started
    STARTING = "starting"       # Triggers being started
    RUNNING = "running"         # Triggers active
    STOPPING = "stopping"       # Triggers being stopped
    STOPPED = "stopped"         # Triggers stopped
    ERROR = "error"             # Startup/runtime error
```

#### ScheduledPipeline

```python
@dataclass
class ScheduledPipeline:
    pipeline_id: str                      # Unique pipeline ID
    spec: PipelineSpec                    # Full specification
    triggers: list[TriggerEngine] = []    # Active trigger engines
    state: PipelineState = REGISTERED     # Lifecycle state
    execution_count: int = 0              # Total executions
    last_execution: float | None = None   # Monotonic timestamp
```

#### TriggerEvent

```python
@dataclass(slots=True, frozen=True)
class TriggerEvent:
    trigger_id: str           # ID of the trigger that fired
    pipeline_id: str          # Target pipeline
    fired_at: float           # Monotonic timestamp
    context: dict = {}        # Optional context (e.g., threshold count)
```

### 7.4 TriggerEngine Types

| Type | Class | Behavior | Overlap Policy |
|------|-------|----------|----------------|
| INTERVAL | `IntervalTriggerEngine` | Fires at fixed intervals | SKIP |
| THRESHOLD | `ThresholdTriggerEngine` | Fires when table count >= threshold | QUEUE |
| MANUAL | `ManualTriggerEngine` | Fires on explicit request | QUEUE |
| CRON | `CronTriggerEngine` | Fires on cron schedule (requires `croniter`) | SKIP |
| IDLE | `IdleTriggerEngine` | Fires when system idle for threshold (requires `ActivityTracker`) | QUEUE |

#### IntervalTriggerEngine

```python
class IntervalTriggerEngine(TriggerEngine):
    """Fires at fixed time intervals."""

    async def _run_loop(self) -> None:
        interval = self.spec.interval_seconds
        while self._running:
            await asyncio.sleep(interval)
            event = self._create_event()
            self._record_fire(event)
            if self._callback:
                self._callback(event)
```

#### ThresholdTriggerEngine

```python
class ThresholdTriggerEngine(TriggerEngine):
    """Fires when table row count exceeds threshold."""

    async def _run_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.spec.check_interval_seconds)
            count = await self._check_count()
            if count >= self.spec.threshold_count:
                event = self._create_event({"count": count})
                self._callback(event)

    async def _check_count(self) -> int:
        return await self._syscalls.query_count(
            table=self.spec.table,
            where=self.spec.condition,
        )
```

#### ManualTriggerEngine

```python
class ManualTriggerEngine(TriggerEngine):
    """Fires only on explicit request."""

    def fire(self) -> bool:
        if not self._running or not self._callback:
            return False
        event = self._create_event()
        self._callback(event)
        return True
```

#### CronTriggerEngine (Phase 2)

```python
class CronTriggerEngine(TriggerEngine):
    """
    Fires on cron schedule.

    Requires croniter package: pip install croniter
    Or install with scheduler extras: pip install -e ".[scheduler]"

    Supports standard 5-field cron expressions:
    - minute (0-59)
    - hour (0-23)
    - day of month (1-31)
    - month (1-12)
    - day of week (0-6, Sunday=0)
    """

    async def _run_loop(self) -> None:
        while self._running:
            next_fire = self._cron.get_next(float)
            delay = next_fire - time.time()
            if delay > 0:
                await asyncio.sleep(delay)
            if self._running:
                event = self._create_event({
                    "scheduled_time": next_fire,
                    "trigger_type": "cron",
                    "cron_expression": self.spec.cron_expression,
                })
                self._callback(event)

    def get_next_fire_time(self) -> float | None:
        """Return next scheduled fire time for observability."""
        ...
```

**CRON Trigger YAML Examples**:

```yaml
# P03 consolidation triggers
triggers:
  # Daily at 2 AM
  - id: consolidation_nightly
    type: cron
    cron_expression: "0 2 * * *"

  # Hourly during sleep window (2-5 AM)
  - id: consolidation_sleep_window
    type: cron
    cron_expression: "0 2-5 * * *"

  # Every 5 minutes
  - id: frequent_sync
    type: cron
    cron_expression: "*/5 * * * *"

  # Weekdays at noon
  - id: weekday_batch
    type: cron
    cron_expression: "0 12 * * 1-5"
```

#### IdleTriggerEngine

```python
class IdleTriggerEngine(TriggerEngine):
    """
    Fires when system has been idle for specified duration.

    Requires ActivityTracker to be running (started by kernel).
    ActivityTracker tracks idle time via BusDispatcher activity.

    Optional min_pending condition requires pending items before firing.
    """

    def __init__(
        self,
        spec: TriggerSpec,
        pipeline_id: str,
        activity_tracker: ActivityTracker,
        syscalls: Syscalls | None = None,  # For min_pending queries
    ):
        ...

    async def start(self, callback: Callable[[TriggerEvent], None]) -> None:
        """Register with ActivityTracker for idle callbacks."""
        ...

    async def stop(self) -> None:
        """Unregister from ActivityTracker."""
        ...
```

**IDLE Trigger YAML Examples**:

```yaml
# P03 consolidation triggers - idle-based processing
triggers:
  # Fire after 5 minutes idle
  - id: consolidation_idle
    type: idle
    idle_seconds: 300

  # Fire after 2 minutes idle, only if pending items exist
  - id: consolidation_pending
    type: idle
    idle_seconds: 120
    min_pending: 10
    table: st_vec
    condition: "status = 'pending'"

  # Fire after 10 minutes idle for deep consolidation
  - id: deep_consolidation
    type: idle
    idle_seconds: 600
```

**TriggerEvent Context for IDLE**:

```python
{
    "trigger_type": "idle",
    "idle_seconds": 312.5,      # Actual idle time when fired
    "pending_count": 42,        # If min_pending configured
}
```

### 7.5 PipelineScheduler API

```python
class PipelineScheduler:
    def __init__(
        self,
        syscalls: Syscalls,              # For threshold queries
        executor: PipelineExecutor | None, # Execution callback
    )

    # Registration
    def register_pipeline(spec: PipelineSpec) -> ScheduledPipeline
    def unregister_pipeline(pipeline_id: str) -> bool
    def get_pipeline(pipeline_id: str) -> ScheduledPipeline | None

    # Lifecycle
    async def start() -> None              # Start all trigger engines
    async def stop() -> None               # Stop all trigger engines

    # Hot reload
    async def hot_reload(
        new_specs: dict[str, PipelineSpec],
        affected_pipelines: set[str] | None = None,
    ) -> HotReloadResult

    # Manual triggering
    def fire_manual_trigger(pipeline_id: str, trigger_id: str) -> bool

    # Introspection
    def get_trigger_stats(pipeline_id: str | None = None) -> dict

    # Properties
    @property
    def pipelines(self) -> dict[str, ScheduledPipeline]
    @property
    def is_running(self) -> bool
```

### 7.6 Hot Reload Protocol (ADR-K004)

```python
async def hot_reload(self, new_specs, affected_pipelines) -> HotReloadResult:
    """
    Atomically swap trigger configuration.

    Steps (per ADR-K004):
    1. Build new config in memory
    2. Acquire reload lock
    3. Cancel triggers for affected pipelines
    4. Drain in-flight runs (with timeout)
    5. Install new triggers
    6. Release lock
    """
```

#### HotReloadResult

```python
@dataclass
class HotReloadResult:
    affected_pipelines: list[str] = []
    success: bool = False
    error: str | None = None
    added: int = 0
    updated: int = 0
    removed: int = 0
```

### 7.7 SingleFlightGate (Concurrency Control)

The gate ensures **at most one concurrent run per pipeline**.

```python
class SingleFlightGate:
    """Concurrency control for pipeline execution."""

    async def try_acquire(
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
    ) -> bool
    """
    Attempt to acquire run slot.

    Behavior based on OverlapPolicy:
    - SKIP (interval): Drop if running → return False
    - QUEUE (threshold/manual): Coalesce pending → return False

    Returns True if slot acquired (caller should run).
    """

    def mark_running(pipeline_id: str, task: asyncio.Task) -> None
    """Mark pipeline as running with its task."""

    async def release(pipeline_id: str) -> PendingRun | None
    """Release slot, return any pending run to execute next."""

    def is_running(pipeline_id: str) -> bool
    def get_stats(pipeline_id: str) -> RunStats | None
    def get_all_stats() -> dict[str, RunStats]
```

### 7.8 OverlapPolicy

```python
class OverlapPolicy(str, Enum):
    SKIP = "skip"    # Drop trigger if running (interval triggers)
    QUEUE = "queue"  # Queue for later (threshold/manual triggers)
```

| Trigger Type | Overlap Policy | On Conflict |
|--------------|----------------|-------------|
| INTERVAL | SKIP | Silently drop |
| THRESHOLD | QUEUE | Coalesce (replace pending) |
| MANUAL | QUEUE | Coalesce (replace pending) |

### 7.9 RunStats

```python
@dataclass
class RunStats:
    total_runs: int = 0          # Completed runs
    total_skipped: int = 0       # Dropped due to overlap
    total_queued: int = 0        # Times a run was queued
    last_run_at: datetime | None = None
```

### 7.10 SchedulerAuditor

Provides structured logging for all scheduler events:

```python
class SchedulerAuditor:
    def log_trigger_fired(pipeline_id, trigger_id, trigger_type, execution_count)
    def log_trigger_skipped(pipeline_id, trigger_id, trigger_type, reason)
    def log_trigger_queued(pipeline_id, trigger_id, trigger_type, replaced_id)
    def log_pipeline_run_start(pipeline_id, trigger_id, trigger_type, run_number)
    def log_pipeline_run_complete(pipeline_id, trigger_id, duration_ms, success, error)
```

#### Audit Event Types

| Event | When Logged |
|-------|-------------|
| `TriggerFiredEvent` | Trigger activates pipeline |
| `TriggerSkippedEvent` | Trigger skipped (overlap policy) |
| `TriggerQueuedEvent` | Trigger queued for later |
| `PipelineRunStartEvent` | Pipeline execution starts |
| `PipelineRunCompleteEvent` | Pipeline execution completes |

### 7.11 Usage Example

```python
from k0.scheduler import (
    PipelineScheduler,
    get_single_flight_gate,
    get_scheduler_auditor,
)

# Create scheduler
scheduler = PipelineScheduler(syscalls=syscalls, executor=my_executor)

# Register pipelines
for spec in pipeline_specs:
    scheduler.register_pipeline(spec)

# Start (activates all trigger engines)
await scheduler.start()

# Manual trigger
scheduler.fire_manual_trigger("P03", "consolidation_manual")

# Hot reload (atomic reconfiguration)
result = await scheduler.hot_reload(
    new_specs={"P03": updated_spec},
    affected_pipelines={"P03"},
)

# Shutdown
await scheduler.stop()
```

### 7.12 TriggerSpec Examples

```yaml
# Pipeline with multiple triggers
pipeline_id: P03_CONSOLIDATION
version: v1
triggers:
  - id: consolidation_interval
    type: interval
    interval_seconds: 300  # Every 5 minutes

  - id: consolidation_threshold
    type: threshold
    table: st_vec
    condition: "status = 'PENDING'"
    threshold_count: 100
    check_interval_seconds: 30

  - id: consolidation_manual
    type: manual
```

---

## 8. Integration Patterns

This section documents how all components work together to form the complete K0 architecture.

### 8.1 Layered Architecture (ADR-K004)

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 3: Scheduler                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ TriggerEngines → PipelineScheduler → SingleFlightGate│   │
│  └───────────────────────────┬─────────────────────────┘   │
│                              │                              │
│                              ▼                              │
├─────────────────────────────────────────────────────────────┤
│                    Layer 2: Fabric                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ CapabilityFabric → CapabilityRegistry → Modules      │   │
│  └───────────────────────────┬─────────────────────────┘   │
│                              │                              │
│                              ▼                              │
├─────────────────────────────────────────────────────────────┤
│                    Layer 1: Kernel                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Syscalls → UnitOfWork → SQLite/FAISS Storage         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Boot Sequence

```python
# 1. Initialize storage
connection_pool = create_connection_pool()

# 2. Initialize capability fabric
fabric = CapabilityFabric.get_instance()

# 3. Load and register capabilities
discover_and_register_capabilities(
    module_registry=module_registry,
    contracts_dir=Path("k0/contracts/capabilities"),
)

# 4. Initialize bus dispatcher with middleware
dispatcher = BusDispatcher(
    scheduler=qos_scheduler,
    middlewares=[timestamp_middleware(), tracing_middleware()],
)

# 5. Initialize pipeline scheduler
scheduler = PipelineScheduler(
    syscalls=syscalls,
    executor=pipeline_executor,
)

# 6. Load and register pipelines
for spec in load_pipeline_specs():
    # Create capability-gated syscalls for this pipeline
    pipeline_syscalls = Syscalls(
        pipeline_id=spec.pipeline_id,
        granted_caps=frozenset(spec.required_capabilities),
        uow_factory=lambda: UnitOfWork(connection_pool),
    )

    # Create pipeline context
    ctx = PipelineContext(
        syscalls=pipeline_syscalls,
        config=spec.config,
        logger=get_logger(spec.pipeline_id),
        fabric=fabric,
    )

    # Initialize pipeline
    pipeline = load_pipeline_class(spec)
    await pipeline.on_startup(ctx)

    # Subscribe to topics
    for topic in pipeline.declared_topics:
        dispatcher.subscribe(topic, pipeline.handle)

    # Register with scheduler
    scheduler.register_pipeline(spec)

# 7. Start scheduler
await scheduler.start()
```

### 8.3 Event-Driven Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Event-Driven Flow                        │
│                                                             │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐           │
│  │   WAL    │ ──► │  Bus     │ ──► │ Pipeline │           │
│  │  Commit  │     │Dispatcher│     │  Handle  │           │
│  └──────────┘     └──────────┘     └────┬─────┘           │
│                                         │                   │
│                      ┌──────────────────┼──────────────────┐│
│                      ▼                  ▼                  ▼│
│                ┌──────────┐      ┌──────────┐      ┌───────┐│
│                │ Syscalls │      │  Fabric  │      │ Outbox││
│                │ (Storage)│      │(Capability)     │ (Emit)││
│                └──────────┘      └──────────┘      └───────┘│
└─────────────────────────────────────────────────────────────┘
```

**Example: P02 Episodic Write**

```python
class P02EpisodicWrite:
    pipeline_id = "P02"
    declared_topics = ["cognitive.memory.write.committed.v1"]
    required_caps = ["st_hipp_events.write", "st_pipeline_processed.write"]

    async def handle(self, msg: BusMessage) -> None:
        # 1. Parse payload
        event = json.loads(msg.payload)

        # 2. Use fabric for salience scoring
        salience = self.fabric.invoke(
            "score_salience",
            content=event["text"],
            timeout_ms=50,
        )

        # 3. Use syscalls for storage
        await self.syscalls.hipp_events_upsert(
            event_id=event["event_id"],
            salience_score=salience["score"],
            wal_pos=msg.offset,
            cognitive_trace_id=msg.trace_id,
        )
```

### 8.4 Trigger-Driven Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   Trigger-Driven Flow                       │
│                                                             │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐           │
│  │ Trigger  │ ──► │SingleFlight    │ Executor │           │
│  │  Engine  │     │   Gate   │ ──► │ Callback │           │
│  └──────────┘     └──────────┘     └────┬─────┘           │
│       ▲                                  │                  │
│       │                                  ▼                  │
│  ┌──────────┐                    ┌──────────────┐          │
│  │ Interval │                    │   Pipeline   │          │
│  │Threshold │                    │   Execute    │          │
│  │ Manual   │                    └──────────────┘          │
│  └──────────┘                                               │
└─────────────────────────────────────────────────────────────┘
```

**Example: P03 Consolidation**

```python
class P03Consolidation:
    pipeline_id = "P03"
    required_caps = ["st_vec.read", "st_vec.write", "faiss.write"]

    async def execute(self, trigger_event: TriggerEvent) -> None:
        # 1. Query pending vectors
        pending = await self.syscalls.vec_query(
            status="PENDING",
            limit=trigger_event.context.get("count", 100),
        )

        # 2. Batch add to FAISS
        await self.syscalls.faiss_add_batch(
            vectors=[(v["vector_id"], v["embedding"]) for v in pending],
        )

        # 3. Update status
        for v in pending:
            await self.syscalls.vec_update_status(v["vector_id"], "INDEXED")
```

### 8.5 Capability Resolution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 Capability Resolution                       │
│                                                             │
│  Pipeline calls:   fabric.invoke("score_salience", ...)    │
│                              │                              │
│                              ▼                              │
│              ┌───────────────────────────┐                 │
│              │    CapabilityRegistry     │                 │
│              │                           │                 │
│              │  resolve("score_salience")│                 │
│              │         │                 │                 │
│              │         ▼                 │                 │
│              │  ┌─────────────────┐     │                 │
│              │  │ Providers List  │     │                 │
│              │  │ [pri:1, pri:2]  │     │                 │
│              │  └────────┬────────┘     │                 │
│              └───────────┼───────────────┘                 │
│                          │                                  │
│                          ▼ (Strategy: PRIORITY)             │
│              ┌───────────────────────────┐                 │
│              │   salience.score:v1       │                 │
│              │        (handler)          │                 │
│              └───────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 8.6 Security Boundary Enforcement

```
┌─────────────────────────────────────────────────────────────┐
│                  Security Boundaries                        │
│                                                             │
│  Pipeline Declaration:                                      │
│    required_caps = ["st_hipp_events.write"]                │
│              │                                              │
│              ▼                                              │
│  ┌──────────────────────────────────────────┐              │
│  │           Syscalls Instance              │              │
│  │                                          │              │
│  │  granted_caps = frozenset(required_caps) │              │
│  │                                          │              │
│  │  _require_cap(needed_cap):               │              │
│  │    if needed_cap not in granted_caps:    │              │
│  │      raise PermissionError(...)          │ ◄── FAIL     │
│  │      log_security_violation(...)         │     CLOSED   │
│  └──────────────────────────────────────────┘              │
│                                                             │
│  Allowed operations (capability present):                   │
│    ✓ syscalls.hipp_events_upsert(...)                      │
│                                                             │
│  Blocked operations (capability missing):                   │
│    ✗ syscalls.vec_write(...)   → PermissionError           │
│    ✗ syscalls.faiss_add(...)   → PermissionError           │
└─────────────────────────────────────────────────────────────┘
```

### 8.7 Complete Request Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│               Complete Request Lifecycle                    │
│                                                             │
│  1. External API Request                                    │
│         │                                                   │
│         ▼                                                   │
│  2. WAL Commit (with trace_id)                             │
│         │                                                   │
│         ▼                                                   │
│  3. BusDispatcher.dispatch()                               │
│     ├─ timestamp_middleware                                │
│     ├─ tracing_middleware                                  │
│     └─ fan_out to subscribers                              │
│         │                                                   │
│         ▼                                                   │
│  4. Pipeline.handle(msg)                                   │
│     ├─ Idempotency check                                   │
│     ├─ Fabric calls (if needed)                            │
│     │   └─ Module invocations                              │
│     ├─ Syscall operations                                  │
│     │   └─ Capability enforcement                          │
│     └─ Record processed                                    │
│         │                                                   │
│         ▼                                                   │
│  5. Outbox emit (if producing events)                      │
│         │                                                   │
│         ▼                                                   │
│  6. SSE delivery (if subscribed)                           │
└─────────────────────────────────────────────────────────────┘
```

### 8.8 Scheduler + Fabric Integration

```python
# Pipeline with both trigger-based and capability integration
class P03Consolidation:
    pipeline_id = "P03"
    required_caps = ["st_vec.read", "st_vec.write", "faiss.write"]

    async def on_startup(self, ctx: PipelineContext) -> None:
        self.syscalls = ctx.syscalls
        self.fabric = ctx.fabric
        self.logger = ctx.logger

    async def execute(self, trigger_event: TriggerEvent) -> None:
        self.logger.info(
            "Consolidation triggered",
            extra={
                "trigger_id": trigger_event.trigger_id,
                "trigger_type": trigger_event.context.get("trigger_type"),
            }
        )

        # Use fabric for embedding if needed
        if self.fabric and self.fabric.has_capability("generate_embedding"):
            for item in pending_items:
                embedding = self.fabric.invoke(
                    "generate_embedding",
                    text=item["content"],
                    timeout_ms=500,
                )
                # ... use embedding

        # Use syscalls for storage
        await self.syscalls.faiss_add_batch(...)
```

### 8.9 Testing Patterns

```python
# Unit test with mocked fabric
@pytest.fixture
def mock_fabric():
    fabric = Mock(spec=CapabilityFabric)
    fabric.invoke.return_value = {"score": 0.75}
    fabric.has_capability.return_value = True
    return fabric

@pytest.fixture
def mock_syscalls():
    syscalls = Mock(spec=Syscalls)
    syscalls.hipp_events_upsert.return_value = {"rows_affected": 1}
    return syscalls

async def test_pipeline_handle(mock_fabric, mock_syscalls):
    ctx = PipelineContext(
        syscalls=mock_syscalls,
        fabric=mock_fabric,
        config={},
        logger=get_test_logger(),
    )

    pipeline = P02EpisodicWrite()
    await pipeline.on_startup(ctx)

    msg = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps({"event_id": "e1", "text": "Hello"}).encode(),
        offset=1,
        trace_id="trace-1",
    )

    await pipeline.handle(msg)

    # Verify fabric called
    mock_fabric.invoke.assert_called_once()

    # Verify syscalls called
    mock_syscalls.hipp_events_upsert.assert_called_once()
```

### 8.10 Observability Integration

```python
# All components emit structured logs with trace_id
{
    "timestamp": "2024-01-15T10:30:00.000Z",
    "level": "INFO",
    "logger": "k0.pipelines.P02",
    "message": "Processing event",
    "trace_id": "abc-123-def-456",
    "pipeline_id": "P02",
    "wal_pos": 12345,
    "capability_calls": 2,
    "syscall_calls": 3,
    "duration_ms": 15.3
}
```

### 8.11 Error Handling Patterns

| Layer | Error Type | Behavior |
|-------|------------|----------|
| Syscalls | `PermissionError` | Logged, not retried |
| Syscalls | Database error | Raised, retried by dispatcher |
| Fabric | `CapabilityNotFoundError` | Raised, fail pipeline |
| Fabric | `CapabilityTimeoutError` | Logged, can continue or fail |
| Scheduler | Trigger error | Logged, continues other triggers |
| Bus | Handler error | Retried with backoff, DLQ after 5 |

### 8.12 Configuration Best Practices

```yaml
# Pipeline configuration
pipelines:
  P02_WRITE:
    concurrency: 10              # IO-bound
    max_queue: 512
    required_capabilities:
      - st_hipp_events.write
      - st_pipeline_processed.write
    triggers:
      - id: write_interval
        type: interval
        interval_seconds: 60
    fabric_actions:
      - score_salience
      - pattern_separate

# Capability configuration
capabilities:
  score_salience:
    default_timeout_ms: 50       # Fast capability
    providers:
      - type: module
        module_id: salience.score:v1
        priority: 1

# Fabric configuration
fabric:
  executor_threads: 4
  default_timeout_ms: 100
  resolution_strategy: priority
```

---

## 9. Creating a New Pipeline (Step-by-Step)

This section provides a complete walkthrough for creating a new pipeline from scratch.

### 9.1 Pipeline File Location

```
k0/pipelines/
├── __init__.py           # Re-exports all pipelines
├── protocol.py           # PipelineProtocol, PipelineContext
├── p02_episodic_write.py # P02 implementation
├── p03_consolidation.py  # P03 implementation
└── your_new_pipeline.py  # Create new file here
```

**Naming Convention**: `p<number>_<snake_case_name>.py`

### 9.2 Pipeline ID Naming

```python
# Pattern: P<2-digit-number>_<UPPERCASE_NAME>
# Examples:
pipeline_id = "P02"                    # Short form (legacy)
pipeline_id = "P10_RELATIONSHIP_EXTRACTOR"  # Full form (preferred)
```

### 9.3 Complete Pipeline Template

```python
"""
P10 Relationship Extractor - Extract relationships from episodic events.

Related:
- k0/kernel/syscalls.py: Storage operations
- k0/fabric/fabric.py: Capability invocations
- k0/runtime/schemas.py: PipelineSpec
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from k0.bus import BusMessage
    from k0.fabric import CapabilityFabric
    from k0.kernel.syscalls import Syscalls
    from k0.pipelines.protocol import PipelineContext

logger = logging.getLogger(__name__)


class P10RelationshipExtractor:
    """
    Extract and store relationships from episodic events.

    This pipeline:
    1. Receives events from the bus
    2. Uses fabric to extract relationships
    3. Writes relationships to st_relationships

    Attributes (Protocol Requirements):
        pipeline_id: Unique identifier
        contract_version: Protocol version
        declared_topics: Topics to subscribe
        concurrency: Max concurrent handlers
        max_queue: Max pending messages
        required_caps: Required capabilities
    """

    # Protocol requirements (class-level)
    pipeline_id: str = "P10_RELATIONSHIP_EXTRACTOR"
    contract_version: int = 1
    declared_topics: Sequence[str] = ["cognitive.memory.write.committed.v1"]
    concurrency: int = 5  # IO-bound, moderate parallelism
    max_queue: int = 256
    required_caps: Sequence[str] = [
        "st_relationships.write",
        "st_relationships.read",
        "st_pipeline_processed.write",
    ]

    # Instance attributes (set in on_startup)
    _syscalls: "Syscalls"
    _fabric: "CapabilityFabric | None"
    _logger: logging.Logger
    _config: dict

    async def on_startup(self, ctx: "PipelineContext") -> None:
        """
        Initialize pipeline resources.

        Called once at kernel boot, before topic subscription.

        Args:
            ctx: Pipeline context with syscalls, fabric, config, logger
        """
        self._syscalls = ctx.syscalls
        self._fabric = ctx.fabric
        self._logger = ctx.logger
        self._config = ctx.config

        self._logger.info(
            f"{self.pipeline_id} started",
            extra={
                "pipeline_id": self.pipeline_id,
                "concurrency": self.concurrency,
                "topics": list(self.declared_topics),
            },
        )

    async def on_shutdown(self) -> None:
        """
        Cleanup pipeline resources.

        Called at kernel shutdown. Complete within 5 seconds.
        """
        self._logger.info(f"{self.pipeline_id} shutdown complete")

    async def handle(self, msg: "BusMessage") -> None:
        """
        Process a single bus message.

        Args:
            msg: Immutable bus message with topic, payload, offset, trace_id
        """
        # 1. Idempotency check
        if await self._already_processed(msg.offset):
            self._logger.debug(
                f"Skipping already processed offset {msg.offset}",
                extra={"offset": msg.offset},
            )
            return

        try:
            # 2. Parse payload
            event = json.loads(msg.payload)

            # 3. Use fabric for relationship extraction (if available)
            relationships = []
            if self._fabric and self._fabric.has_capability("extract_relationships"):
                result = self._fabric.invoke(
                    "extract_relationships",
                    text=event.get("text", ""),
                    participants=event.get("participants", []),
                    timeout_ms=100,
                )
                relationships = result.get("relationships", [])

            # 4. Write to storage
            for rel in relationships:
                await self._syscalls.relationships_write(
                    source_entity=rel["source"],
                    target_entity=rel["target"],
                    relationship_type=rel["type"],
                    confidence=rel["confidence"],
                    event_id=event["event_id"],
                    cognitive_trace_id=msg.trace_id,
                )

            # 5. Record processed (idempotency)
            await self._mark_processed(msg.offset)

            self._logger.info(
                f"Processed event with {len(relationships)} relationships",
                extra={
                    "event_id": event.get("event_id"),
                    "relationship_count": len(relationships),
                    "offset": msg.offset,
                    "trace_id": msg.trace_id,
                },
            )

        except json.JSONDecodeError as e:
            # Permanent error - don't retry
            self._logger.error(
                f"Invalid JSON payload: {e}",
                extra={"offset": msg.offset, "error": str(e)},
            )
            # Don't raise - message will not be retried

        except Exception as e:
            # Transient error - raise for retry
            self._logger.error(
                f"Processing failed: {e}",
                extra={"offset": msg.offset, "error": str(e)},
                exc_info=True,
            )
            raise  # Will be retried by dispatcher

    async def _already_processed(self, offset: int) -> bool:
        """
        Check if this offset was already processed.

        Uses st_pipeline_processed table for idempotency.

        Args:
            offset: WAL offset to check

        Returns:
            True if already processed, False otherwise
        """
        result = await self._syscalls.pipeline_processed_query(
            pipeline_id=self.pipeline_id,
            wal_pos=offset,
        )
        return result is not None

    async def _mark_processed(self, offset: int) -> None:
        """
        Record that this offset was processed.

        Args:
            offset: WAL offset to mark as processed
        """
        await self._syscalls.pipeline_processed_upsert(
            pipeline_id=self.pipeline_id,
            wal_pos=offset,
        )
```

### 9.4 Event-Driven vs Trigger-Driven

| Activation | Method | When to Use |
|------------|--------|-------------|
| **Event-Driven** | `handle(msg: BusMessage)` | React to WAL commits, real-time processing |
| **Trigger-Driven** | `execute(trigger_event: TriggerEvent)` | Periodic batch processing, consolidation |

**Hybrid Pipeline** (both methods):

```python
class P03Consolidation:
    pipeline_id = "P03"
    declared_topics = []  # No bus subscription

    async def handle(self, msg: BusMessage) -> None:
        """Not used - trigger-driven only."""
        pass

    async def execute(self, trigger_event: TriggerEvent) -> None:
        """Called when trigger fires."""
        # Batch processing logic here
```

### 9.5 Adding Trigger Configuration

Triggers are defined in pipeline YAML specs:

```yaml
# k0/contracts/pipelines/p10_relationship_extractor.yaml
pipeline_id: P10_RELATIONSHIP_EXTRACTOR
version: v1

entry_topic: cognitive.memory.write.committed.v1
concurrency: 5
max_queue: 256

required_capabilities:
  - st_relationships.write
  - st_relationships.read
  - st_pipeline_processed.write

triggers:
  # Interval trigger for catch-up processing
  - id: relationship_interval
    type: interval
    interval_seconds: 600  # Every 10 minutes

  # Manual trigger for admin-initiated runs
  - id: relationship_manual
    type: manual

dag:
  - id: extract
    module: relationships.extract:v1
```

### 9.6 Syscall Return Types

| Method | Return Type | Example |
|--------|-------------|---------|
| `hipp_events_upsert(...)` | `dict[str, Any]` | `{"rows_affected": 1, "event_id": "e1"}` |
| `hipp_events_query(...)` | `list[dict]` | `[{"event_id": "e1", ...}, ...]` |
| `vec_write(...)` | `dict[str, Any]` | `{"vector_id": "v1", "inserted": True}` |
| `vec_query(...)` | `list[dict]` | `[{"vector_id": "v1", ...}, ...]` |
| `query_count(table, where)` | `int` | `42` |
| `faiss_add(...)` | `bool` | `True` |
| `faiss_search(...)` | `list[tuple[str, float]]` | `[("v1", 0.95), ("v2", 0.87)]` |
| `pipeline_processed_query(...)` | `dict` or `None` | `{"wal_pos": 123}` or `None` |
| `pipeline_processed_upsert(...)` | `dict[str, Any]` | `{"rows_affected": 1}` |

### 9.7 Pipeline Auto-Discovery

Pipelines are discovered at boot via:

1. **Module Scan**: Loader scans `k0/pipelines/` for classes implementing `PipelineProtocol`
2. **Protocol Check**: `isinstance(cls, PipelineProtocol)` via `@runtime_checkable`
3. **Registration**: Each discovered pipeline is instantiated and registered

**To ensure discovery**:
- Place file in `k0/pipelines/`
- Class must have all protocol attributes (`pipeline_id`, `contract_version`, etc.)
- Export from `k0/pipelines/__init__.py`:

```python
# k0/pipelines/__init__.py
from .p10_relationship_extractor import P10RelationshipExtractor

__all__ = [
    # ... existing exports
    "P10RelationshipExtractor",
]
```

### 9.8 UnitOfWork (Transaction Scope)

The `UnitOfWork` provides transaction boundaries for syscall operations:

```python
# Syscalls automatically manage UnitOfWork
async with syscalls._uow() as uow:
    # All operations in this block are atomic
    await syscalls.hipp_events_upsert(...)
    await syscalls.vec_write(...)
    # Commit on exit, rollback on exception
```

**You don't manage UnitOfWork directly** - syscalls handle it internally. Each `handle()` call gets its own transaction scope.

### 9.9 Dead Letter Queue (DLQ)

Failed messages are moved to `st_dlq` after retry exhaustion:

```sql
-- st_dlq schema
CREATE TABLE st_dlq (
    id INTEGER PRIMARY KEY,
    topic TEXT NOT NULL,
    payload BLOB NOT NULL,
    offset INTEGER NOT NULL,
    trace_id TEXT,
    pipeline_id TEXT NOT NULL,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_retry_at TEXT
);
```

**Querying DLQ**:

```python
# Via syscalls (if you have st_dlq.read capability)
failed = await syscalls.dlq_query(pipeline_id="P10")
```

### 9.10 Error Receipt Emission

For permanent errors that shouldn't retry:

```python
from k0.receipts import emit_error_receipt

async def handle(self, msg: BusMessage) -> None:
    try:
        event = json.loads(msg.payload)
    except json.JSONDecodeError as e:
        # Emit error receipt, don't retry
        await emit_error_receipt(
            pipeline_id=self.pipeline_id,
            offset=msg.offset,
            error_code="INVALID_JSON",
            error_message=str(e),
            trace_id=msg.trace_id,
        )
        return  # Don't raise

    # ... continue processing
```

### 9.11 Checklist: New Pipeline

Before deploying a new pipeline, verify:

- [ ] File placed in `k0/pipelines/`
- [ ] Class has all protocol attributes (`pipeline_id`, `contract_version`, `declared_topics`, `concurrency`, `max_queue`, `required_caps`)
- [ ] `on_startup()` stores context components
- [ ] `on_shutdown()` cleans up resources
- [ ] `handle()` implements idempotency check
- [ ] Required capabilities declared match syscall usage
- [ ] Exported from `k0/pipelines/__init__.py`
- [ ] YAML spec in `k0/contracts/pipelines/` (if using triggers)
- [ ] Unit tests with mocked syscalls/fabric
- [ ] Integration test with real storage

---

## Quick Reference

### Component Imports

```python
# Kernel
from k0.kernel.syscalls import Syscalls

# Bus
from k0.bus import BusDispatcher, BusMessage, current_dispatch_context

# Fabric
from k0.fabric import (
    CapabilityFabric,
    CapabilityRegistry,
    CapabilityRequest,
    CapabilityResponse,
    get_capability_fabric,
)

# Scheduler
from k0.scheduler import (
    PipelineScheduler,
    TriggerEngine,
    TriggerEvent,
    SingleFlightGate,
    get_single_flight_gate,
    get_scheduler_auditor,
)

# Runtime
from k0.runtime.schemas import (
    PipelineSpec,
    TriggerSpec,
    TriggerType,
    ModuleContract,
)

# Pipelines
from k0.pipelines.protocol import PipelineProtocol, PipelineContext

# Loader (internal - typically not imported by pipelines)
from k0.runtime.loader import load_pipeline_specs, load_pipeline_class

# Receipts
from k0.receipts import emit_error_receipt, emit_success_receipt
```

### Key Files

| Component | Primary File(s) |
|-----------|-----------------|
| Syscalls | `k0/kernel/syscalls.py` |
| Bus | `k0/bus/core.py`, `k0/bus/middleware.py` |
| Fabric | `k0/fabric/fabric.py`, `k0/fabric/registry.py` |
| Scheduler | `k0/scheduler/scheduler.py`, `k0/scheduler/triggers.py` |
| Concurrency | `k0/scheduler/concurrency.py` |
| Audit | `k0/scheduler/audit.py` |
| Schemas | `k0/runtime/schemas.py` |
| Pipelines | `k0/pipelines/protocol.py` |
| Loader | `k0/fabric/loader.py` |

### Naming Conventions

> **Complete naming rules**: See [k0_architecture_master.md Part 9.2: Naming Conventions](../pipelines/k0_architecture_master.md#92-naming-conventions)

#### Event Topics

**Pattern**: `{namespace}.{component}.{action}.v{version}`

| Namespace | Purpose | Example |
|-----------|---------|--------|
| `cognitive.*` | Memory operations | `cognitive.memory.write.committed.v1` |
| `intelligence.*` | Advisory signals | `intelligence.advisory.decision.ready.v1` |
| `system.*` | System lifecycle | `system.pipeline.started.v1` |
| `infra.*` | Infrastructure | `infra.storage.checkpoint.v1` |
| `privacy.*` | Privacy controls | `privacy.redaction.applied.v1` |

**Actions**:
- Requests: `request`, `query`, `command`
- Completions: `committed`, `completed`, `failed`
- States: `started`, `stopped`, `updated`

#### Capability Names

**Pattern**: `{verb}_{noun}` (snake_case)

| Example | Description |
|---------|-------------|
| `score_salience` | Compute salience score |
| `pattern_separate` | Hippocampus pattern separation |
| `generate_embedding` | Create vector embedding |
| `extract_relationships` | Parse entity relationships |

#### Storage Capabilities

**Pattern**: `{table}.{operation}`

| Operation | Meaning |
|-----------|--------|
| `.read` | SELECT queries |
| `.write` | INSERT, UPDATE, DELETE |
| `.delete` | DELETE only (for cleanup jobs) |

### ADR References

| ADR | Topic |
|-----|-------|
| ADR-K004 | Capability Mesh Architecture (3-layer design) |
| ADR-K006 | Pipeline Protocol and Lifecycle |
| ADR-K007 | Event Bus Design |
| ADR-K010 | Trigger-Based Scheduling |

---

**Document Version**: 1.0.0
**Last Updated**: 2025-12-14
**Verified Against**: K0 codebase (scheduler, fabric, bus, kernel)
