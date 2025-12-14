---
adr_number: 'K004'
affected_layers:
  - L6_BUS
  - L7_QUERY_WORKERS
  - L10_INFRA
affected_modules:
  - k0/bus/
  - k0/fabric/
  - k0/runtime/
  - k0/kernel/
authors:
  - K0 Architecture Team
concerns:
  - inter-pipeline-communication
  - scalability
  - capability-routing
  - request-reply-pattern
date_created: '2025-12-14'
date_updated: '2025-12-14'
implementation_date: null
implementation_phase: 'P03-Implementation'
implementation_status: PROPOSED
propagation:
  affected_adrs:
    - k003-inline-embedding
  affected_contracts:
    - k0/contracts/pipelines/*.yaml
    - k0/contracts/modules/*.yaml
  affected_tests:
    - tests/k0/fabric/
    - tests/k0/bus/
  triggers:
    - P03 Consolidation requires cross-pipeline queries
    - Unlimited pipelines + 1000s of modules needs structured communication
related_adrs:
  - k003-inline-embedding
  - k001-write-pipeline-v1-hardening
related_contracts:
  - p02_write.v1.yaml
  - p08_embedding_management.v2.yaml
related_diagrams:
  - architecture_diagrams/k0/k0_source_of_truth.mmd
  - architecture_diagrams/k0/project_architecture_part1.mmd
research_citations:
  - 'Dennis & Van Horn 1966 (Capability-based security)'
  - 'Hewitt 1973 (Actor model)'
  - 'Service Mesh patterns (Istio, Linkerd)'
status: PROPOSED
superseded_by: []
supersedes: []
title: 'Capability Mesh Architecture for Inter-Pipeline Communication'
---

# ADR-K004: Capability Mesh Architecture for Inter-Pipeline Communication

**Status**: PROPOSED

**Date**: 2025-12-14

**Authors**: @K0-Architecture-Team

## Context

### Problem Statement

K0 currently has 20 pipelines (P01-P20) and 22+ modules. The system is designed to scale to:
- **Unlimited pipelines** (P01-P100+)
- **1000s of modules** (hippocampus.*, affect.*, social.*, embedding.*, etc.)

Current communication patterns are insufficient:

| Pattern | Current Implementation | Limitation |
|---------|----------------------|-------------|
| Event Fan-Out | `BusDispatcher.subscribe()` | Fire-and-forget only, no request/reply |
| Scheduled Pipelines | Hardcoded in `app.py` (_p08_faiss_indexer_loop) | Not declarative, violates "pipelines stay out of kernel" |
| Cross-Pipeline Queries | None | P03 cannot query P02's salience.score module |
| Capability Discovery | None | No way to find "who provides embed_text?" |

### Specific Pain Points

1. **P03 Consolidation** needs to call `salience.score:v1` but cannot:
   - P03 doesn't know which pipeline/module provides scoring
   - No request/reply mechanism exists
   - No inherited context for capability enforcement

2. **P08 Scheduled Mode** is hardcoded:
   ```python
   # k0/kernel/app.py:501-620
   async def _p08_faiss_indexer_loop() -> None:
       # Hardcoded scheduler inside kernel
       await asyncio.sleep(interval_seconds)
   ```
   This violates the principle: "pipelines stay out of core kernel"

3. **Module Reuse** is limited:
   - `salience.score:v1` is only callable from P02's DAG
   - P03, P19 cannot reuse it without duplicating code

### Architectural Constraints (P03 Rules)

Per conversation context, P03 has three critical rules:

1. **Rule 1: P03 Is Read-Only to P02** - Never mutates original writes
2. **Rule 2: Consolidation Is Deterministic** - Same input + policies = same output
3. **Rule 3: Everything Has Lineage** - Every artifact traces back to sources

Any communication mechanism MUST preserve these properties.

## Decision

Implement a **3-layer Capability Mesh Architecture** consisting of:

### Layer 1: BusDispatcher (Existing) - Event Fan-Out
Already implemented in `k0/bus/core.py`. No changes needed.

### Layer 2: CapabilityFabric (NEW) - Request/Reply by Capability
Route inter-pipeline/module calls by **capability name**, not identity.

### Layer 3: PipelineScheduler (NEW) - Trigger-Based Activation
Declarative scheduling extracted from kernel into standalone component.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          K0 KERNEL (Privileged)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐  ┌───────────────────────┐  ┌─────────────────────┐  │
│  │  BusDispatcher   │  │   CapabilityFabric    │  │  PipelineScheduler  │  │
│  │  (k0/bus/)       │  │   (k0/fabric/)        │  │  (k0/scheduler/)    │  │
│  │                  │  │                       │  │                     │  │
│  │  - subscribe()   │  │  - request()          │  │  - cron triggers    │  │
│  │  - dispatch()    │  │  - resolve_provider() │  │  - threshold        │  │
│  │  - tap()         │  │  - invoke_module()    │  │  - idle detection   │  │
│  └────────┬─────────┘  └───────────┬───────────┘  └──────────┬──────────┘  │
│           │                        │                         │              │
│           ▼                        ▼                         ▼              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    ModuleRegistry (k0/runtime/)                      │  │
│  │  - load_contracts()  - get()  - resolve_capability()                 │  │
│  │  hippocampus.* | affect.* | social.* | embedding.* | salience.* ...  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│           │                        │                         │              │
│           ▼                        ▼                         ▼              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    PipelineRunners (k0/runtime/)                     │  │
│  │  P01 | P02 | P03 | ... | Pn (unlimited)                              │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### Component 1: CapabilityFabric

**Location**: `k0/fabric/`

**Purpose**: Route request/reply calls by capability name, not provider identity.

**Key Design Principles**:

1. **Route by Capability, Not Identity** - Callers request "score_salience", not "salience.score:v1"
2. **Context Inheritance** - Fabric calls inherit caller's syscalls (capability intersection)
3. **Full Lineage** - Every call traceable via `cognitive_trace_id` + `fabric_correlation_id`
4. **Declarative in YAML** - No hardcoded wiring

#### CapabilityFabric Interface

```python
# k0/fabric/core.py
class CapabilityFabric:
    """Routes capability requests to providers (modules or pipelines)."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        module_registry: ModuleRegistry,
        bus_dispatcher: BusDispatcher,
    ) -> None:
        self._registry = registry
        self._module_registry = module_registry
        self._bus = bus_dispatcher

    async def request(
        self,
        capability: str,              # e.g., "score_salience"
        payload: dict[str, Any],      # Request data
        caller_context: PipelineContext,  # Inherit syscalls/caps
        timeout_ms: int = 100,
        correlation_id: str | None = None,
    ) -> FabricResponse:
        """
        Find provider for capability, invoke it, return result.

        Args:
            capability: Capability name (e.g., "score_salience", "embed_text")
            payload: Request payload (passed to provider)
            caller_context: Caller's PipelineContext (for capability inheritance)
            timeout_ms: Max wait time before timeout
            correlation_id: Optional correlation ID (generated if None)

        Returns:
            FabricResponse with result or error

        Raises:
            CapabilityNotFoundError: No provider for capability
            FabricTimeoutError: Provider did not respond in time
        """
        ...

    def _enforce_context_policy(
        self,
        caller_context: PipelineContext,
        provider_policy: str,  # "inherit" | "isolated" | "synthetic"
    ) -> PipelineContext:
        """
        Enforce fabric_context_policy before invoking provider.

        - inherit: intersect caller and provider capabilities
        - isolated: use only provider's declared syscalls
        - synthetic: create minimal context with trace_id only
        """
        ...

    def _intersect_capabilities(
        self,
        caller_caps: set[str],
        provider_caps: set[str],
    ) -> set[str]:
        """Return intersection of caller and provider capabilities."""
        return caller_caps & provider_caps

@dataclass(frozen=True, slots=True)
class FabricResponse:
    """Response from a capability invocation."""
    success: bool
    result: dict[str, Any] | None
    error: str | None
    provider_id: str          # Which module/pipeline served request
    correlation_id: str       # For lineage tracking
    latency_ms: float
    trace_id: str | None
```

#### CapabilityRegistry Schema

```yaml
# k0/contracts/capabilities/registry.yaml
capabilities:
  score_salience:
    description: "Compute salience score for memory importance"
    providers:
      - type: module
        module_id: salience.score:v1
        priority: 1
        fabric_callable: true
        latency_budget_ms: 5

  embed_text:
    description: "Generate 768-dim embedding for text"
    providers:
      - type: module
        module_id: embedding.extract_from_cache:v1
        priority: 1
        condition: cache_hit
      - type: module
        module_id: embedding.compute_ultrabert:v1
        priority: 2
        condition: always

  resolve_family_graph:
    description: "Resolve family relationships for participants"
    providers:
      - type: pipeline
        pipeline_id: P19_PERSONALIZATION
        request_topic: fabric.p19.family_graph.request.v1
        response_topic: fabric.p19.family_graph.response.v1
        timeout_ms: 500
```

#### Module Contract Extension

Modules must declare `fabric_callable: true` to be invokable via Fabric:

```yaml
# k0/contracts/modules/salience.score.v1.yaml (extended)
module_id: salience.score
version: v1
# ... existing fields ...

# NEW: Fabric integration
fabric_callable: true
fabric_capabilities:
  - score_salience
fabric_context_policy: inherit  # inherit | isolated | synthetic

# Policy enforcement boundary:
# - inherit: caller_caps ∩ provider_caps = effective_caps
# - isolated: provider uses only its declared syscalls
# - synthetic: fabric creates minimal synthetic context
```

---

### Component 2: PipelineScheduler

**Location**: `k0/scheduler/`

**Purpose**: Declarative trigger-based pipeline activation (replaces hardcoded P08 loop).

**Key Design Principles**:

1. **Declarative in YAML** - Triggers defined in pipeline spec, not kernel code
2. **Multiple Trigger Types**:
   - **Phase 1 (Initial Release)**: `interval`, `threshold`, `manual`
   - **Phase 2 (Future)**: `cron`, `idle`
3. **Activation via Bus** - Scheduler emits to pipeline's entry_topic
4. **Hot-Reload Support** - Trigger changes don't require kernel restart

#### PipelineScheduler Interface

```python
# k0/scheduler/core.py
class PipelineScheduler:
    """Activates pipelines based on declarative triggers."""

    def __init__(
        self,
        bus_dispatcher: BusDispatcher,
        pipeline_specs: dict[str, PipelineSpec],
    ) -> None:
        self._bus = bus_dispatcher
        self._specs = pipeline_specs
        self._active_triggers: dict[str, list[TriggerHandle]] = {}

    async def start(self) -> None:
        """Read triggers from YAML specs, set up activations."""
        for pipeline_id, spec in self._specs.items():
            if not spec.triggers:
                continue
            for trigger in spec.triggers:
                await self._register_trigger(pipeline_id, spec, trigger)

    async def stop(self) -> None:
        """Cancel all active triggers."""
        for handles in self._active_triggers.values():
            for handle in handles:
                handle.cancel()

    async def _register_trigger(
        self,
        pipeline_id: str,
        spec: PipelineSpec,
        trigger: TriggerSpec,
    ) -> None:
        """Register a single trigger for pipeline activation."""
        if trigger.type == "cron":
            handle = await self._schedule_cron(pipeline_id, spec, trigger)
        elif trigger.type == "interval":
            handle = await self._schedule_interval(pipeline_id, spec, trigger)
        elif trigger.type == "threshold":
            handle = await self._register_threshold(pipeline_id, spec, trigger)
        elif trigger.type == "idle":
            handle = await self._register_idle(pipeline_id, spec, trigger)
        else:
            raise ValueError(f"Unknown trigger type: {trigger.type}")

        self._active_triggers.setdefault(pipeline_id, []).append(handle)

    async def _emit_trigger(
        self,
        pipeline_id: str,
        spec: PipelineSpec,
        trigger: TriggerSpec,
    ) -> None:
        """Emit synthetic message to pipeline's entry_topic."""
        message = BusMessage(
            topic=spec.entry_topic,
            payload=json.dumps({
                "trigger_type": trigger.type,
                "trigger_id": trigger.id,
                "scheduled_at": datetime.now(timezone.utc).isoformat(),
            }).encode(),
            offset=-1,  # Synthetic message (not from WAL)
            trace_id=f"scheduler_{pipeline_id}_{uuid4().hex[:8]}",
            metadata={"scheduler_triggered": True},
        )
        await self._bus.dispatch([message])
```

#### PipelineSpec Trigger Extension

```yaml
# k0/contracts/pipelines/p08_embedding_management.v2.yaml (extended)
pipeline_id: P08_EMBEDDING_MANAGEMENT
version: v2
entry_topic: scheduled.p08.trigger.v1
exit_topic: cognitive.vector.indexed.v1

# NEW: Declarative triggers (replaces hardcoded _p08_faiss_indexer_loop)
triggers:
  - id: faiss_indexer_interval
    type: interval
    interval_seconds: 300
    batch_size: 100
    catch_up_enabled: true

  - id: faiss_indexer_threshold
    type: threshold
    table: st_vec
    condition: "status = 'READY'"
    threshold_count: 50
    check_interval_seconds: 60

  - id: faiss_indexer_idle
    type: idle
    idle_seconds: 30
    min_pending: 10
```

---

### Component 3: Extended ModuleRegistry

**Location**: `k0/runtime/module_registry.py` (extension)

**Purpose**: Add capability-based lookup to existing module registry.

#### ModuleRegistry Extension

```python
# k0/runtime/module_registry.py (extended)
class ModuleRegistry:
    # ... existing code ...

    def __init__(self) -> None:
        # ... existing ...
        self._capability_index: dict[str, list[ModuleID]] = {}

    async def _load_single_contract(self, contract_file: Path) -> None:
        # ... existing loading code ...

        # NEW: Index by fabric_capabilities
        if contract.fabric_callable and contract.fabric_capabilities:
            for cap in contract.fabric_capabilities:
                self._capability_index.setdefault(cap, []).append(contract.full_id)

    def resolve_capability(self, capability: str) -> list[ModuleID]:
        """
        Find modules that provide a given capability.

        Args:
            capability: Capability name (e.g., "score_salience")

        Returns:
            List of module IDs that provide this capability
        """
        return self._capability_index.get(capability, [])
```

---

## Consequences

### Positive

1. **Scalability**: System can grow to unlimited pipelines and 1000s of modules
2. **Decoupling**: Modules don't know who calls them; callers don't know who provides capabilities
3. **Reusability**: Modules like `salience.score:v1` can serve P02, P03, P19 without duplication
4. **Declarative Wiring**: All communication patterns defined in YAML, not code
5. **Full Lineage**: Every Fabric call traceable via `trace_id` + `correlation_id`
6. **P03 Rules Preserved**:
   - Rule 1 (Read-Only): Fabric calls don't mutate original data
   - Rule 2 (Deterministic): Same capability request → same response
   - Rule 3 (Lineage): Full trace chain preserved

### Negative

1. **Complexity**: Three communication layers instead of one
2. **Latency**: Fabric adds ~1-5ms overhead per request/reply
3. **Debugging**: Distributed calls harder to trace (mitigated by correlation IDs)
4. **Learning Curve**: Developers must understand capability-based routing

### Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Circular capability calls | Medium | High | Cycle detection in Fabric with max depth |
| Capability version mismatch | Low | Medium | Version negotiation in registry |
| Scheduler resource exhaustion | Low | Medium | Rate limiting on trigger frequency |
| Fabric timeout cascades | Medium | High | Circuit breaker pattern per provider |

---

## Concurrency Policy

### Trigger Overlap Policy

**Decision**: One pipeline run at a time per pipeline ID ("single-flight").

When multiple triggers fire for the same pipeline while a run is in progress:

| Scenario | Policy | Behavior |
|----------|--------|----------|
| Interval fires while running | **SKIP** | Log warning, skip this interval tick |
| Threshold fires while running | **QUEUE** | Queue one pending run (max queue depth: 1) |
| Manual fires while running | **QUEUE** | Queue one pending run |
| Multiple queued | **COALESCE** | Only one pending run kept, others dropped with warning |

**Implementation**:

```python
class PipelineScheduler:
    def __init__(self):
        self._running: dict[str, asyncio.Task] = {}
        self._pending: dict[str, TriggerEvent | None] = {}
        self._run_lock = asyncio.Lock()

    async def _maybe_start_run(self, pipeline_id: str, event: TriggerEvent) -> bool:
        async with self._run_lock:
            if pipeline_id in self._running:
                if event.trigger_type == "interval":
                    logger.warning(f"Skipping {pipeline_id}: already running")
                    return False
                else:
                    # Queue (coalesce if already pending)
                    self._pending[pipeline_id] = event
                    return False
            # Start run
            self._running[pipeline_id] = asyncio.create_task(...)
            return True
```

### Hot Reload Policy

**Decision**: Atomic swap with graceful drain.

1. Build new trigger configuration in memory
2. Acquire scheduler lock
3. Cancel all triggers for affected pipelines
4. Wait for in-flight runs to complete (with timeout)
5. Install new triggers atomically
6. Release lock

**No partial states**: Either old config or new config, never mixed.

### Registry Thread Safety

**Decision**: Use `asyncio.Lock` for all registry mutations.

| Operation | Lock Required? |
|-----------|---------------|
| `register()` | Yes |
| `resolve()` | No (read-only) |
| `record_call()` | Yes (counter mutation) |
| Hot reload | Yes (exclusive) |

**Implementation**: Copy-on-write for iteration safety:

```python
def resolve(self, capability: str) -> list[RegisteredProvider]:
    # Return copy to prevent mutation during iteration
    return list(self._providers.get(capability, []))
```

---

## Scope Boundaries

### Single-Instance Assumption

**K0 v1 operates as a single-instance process.** The following are explicitly **out of scope**:

| Concern | Status | Future Path |
|---------|--------|-------------|
| Distributed scheduling | Out of scope | K1 orchestration layer |
| Cross-instance fabric calls | Out of scope | K1 with gRPC/message queue |
| Shared trigger state | Out of scope | External scheduler (e.g., Temporal) |
| Multi-node registry | Out of scope | Consul/etcd integration |

**Rationale**: K0 is the "local brain" for a single family instance. Distribution and federation are K1 concerns.

### Capacity Limits (Soft Recommendations)

| Resource | Recommended Limit | Hard Limit | Notes |
|----------|------------------|------------|-------|
| Pipelines | 50 | 200 | Beyond 200, consider sharding |
| Modules | 500 | 2000 | Memory constraint |
| Triggers per pipeline | 5 | 20 | Excessive triggers cause scheduling contention |
| Concurrent fabric calls | 100 | 1000 | Bounded by asyncio task pool |
| Registry entries | 1000 | 10000 | In-memory, ~1KB per entry |

### Persistence Model

**Phase 1**: All registry state is in-memory, rebuilt from YAML contracts at boot.

**Future (if needed)**: Optional SQLite cache for faster warm restart:

- `st_capability_registry` table
- Invalidated on contract file change (mtime check)

---

## Audit Logging

### Requirements

All fabric calls cross trust boundaries and must be auditable.

**Minimum Audit Events (Phase 1)**:

| Event | Fields | When |
|-------|--------|------|
| `fabric.invoke.start` | capability, caller_id, trace_id, correlation_id, timestamp | Before provider resolution |
| `fabric.invoke.complete` | capability, provider_id, latency_ms, success, timestamp | After handler returns |
| `fabric.invoke.error` | capability, provider_id, error_type, error_msg, timestamp | On exception |
| `trigger.fired` | pipeline_id, trigger_id, trigger_type, timestamp | When trigger activates |
| `trigger.skipped` | pipeline_id, trigger_id, reason, timestamp | When trigger is skipped (overlap policy) |

**Log Format** (structured JSON):

```json
{
  "event": "fabric.invoke.complete",
  "timestamp": "2025-12-14T10:30:00.123Z",
  "trace_id": "abc123",
  "correlation_id": "def456",
  "capability": "score_salience",
  "provider_id": "salience.score:v1",
  "caller_id": "P03",
  "latency_ms": 2.5,
  "success": true
}
```

**Audit Sink**: Standard Python logger with `k0.fabric.audit` namespace.
Operators can route to file, stdout, or external system.

### Metrics (Observability)

| Metric Name | Type | Labels |
|-------------|------|--------|
| `fabric_invoke_total` | Counter | capability, provider_id, success |
| `fabric_invoke_latency_ms` | Histogram | capability, provider_id |
| `trigger_fired_total` | Counter | pipeline_id, trigger_type |
| `trigger_skipped_total` | Counter | pipeline_id, trigger_type, reason |
| `scheduler_pending_runs` | Gauge | pipeline_id |

---

## Future Considerations

Features explicitly deferred to Phase 2 or Phase 3:

### Phase 2 (Post-Initial Release)

| Feature | Description | Prerequisite |
|---------|-------------|--------------|
| CRON triggers | Cron expression scheduling | `croniter` dependency |
| IDLE triggers | Fire after N seconds idle | Activity tracking |
| Circuit breakers | Fail-fast for unhealthy providers | Metrics infrastructure |
| Version negotiation | Capability version matching | Semantic versioning in registry |
| Provider health checks | Periodic liveness probes | Background health task |

### Phase 3 (Future Enhancement)

| Feature | Description | Prerequisite |
|---------|-------------|--------------|
| Load shedding | Automatic provider selection by load | Real-time metrics + decision engine |
| Distributed registry | Multi-instance capability discovery | K1 orchestration layer |
| Capability ACLs | Fine-grained access control per capability | Identity/auth infrastructure |
| Replay/debugging | Replay fabric call sequences | Event sourcing infrastructure |
| Schema evolution | Backward-compatible payload changes | Schema registry (e.g., Avro) |

### Design Notes for Future Implementers

1. **Circuit Breaker Pattern**: Use half-open state with exponential backoff. Recommend `circuitbreaker` library or hand-rolled 3-state machine.

2. **Load Shedding**: Requires `fabric_invoke_latency_ms` histogram. Select provider with lowest p99 latency in last 60s.

3. **Version Migration**: Add `min_version` and `max_version` to `CapabilityProvider`. Fabric resolves to highest compatible version.

4. **Distributed Scheduling**: Do NOT try to coordinate triggers across instances. Use external scheduler (Temporal, Airflow, Celery Beat) and have each instance subscribe to its partition.

---

## Alternatives Considered

### Alternative 1: Direct Module Imports

**Description**: Pipelines directly import and call modules.

```python
# P03 directly imports salience module
from k0.modules.salience.score import run as score_salience
result = await score_salience(envelope, context)
```

**Why Rejected**:
- Violates capability security model
- No lineage tracking
- Tight coupling between pipelines and modules
- Cannot swap providers at runtime

### Alternative 2: Expand BusDispatcher for Request/Reply

**Description**: Add request/reply semantics to existing bus.

```python
response = await bus.request(
    topic="salience.score.request.v1",
    payload=envelope,
    reply_topic="p03.salience.response.v1",
)
```

**Why Rejected**:
- Topic-based routing doesn't support capability abstraction
- Requires callers to know specific topic names
- No provider discovery mechanism
- Mixes event semantics with RPC semantics

### Alternative 3: gRPC Service Mesh

**Description**: Each pipeline exposes gRPC endpoints.

**Why Rejected**:
- Overkill for in-process communication
- Adds serialization/deserialization overhead
- External dependency (protobuf compiler)
- Doesn't integrate with existing YAML-based configuration

---

## Implementation Notes

### Phasing Strategy

Implementation is divided into milestones:

**Phase 1 (Initial Release)**:

- **M1**: Foundation (CapabilityRegistry, TriggerSpec schemas)
- **M2**: CapabilityFabric implementation with enforcement boundary
- **M3**: PipelineScheduler (INTERVAL, THRESHOLD, MANUAL triggers only)
- **M4**: P03 Integration (fabric usage for salience scoring)
- **M5**: P08 Migration (declarative triggers replacing hardcoded loop)

**Phase 2 (Future Enhancement)**:

- **M6**: CRON trigger engine (requires cron parser dependency)
- **M7**: IDLE trigger engine (requires activity tracking infrastructure)

### Migration Path

1. **Backward Compatible**: Existing pipelines continue to work
2. **Opt-In**: Only pipelines declaring `fabric_capabilities` are fabric-callable
3. **Gradual Migration**: P08's hardcoded loop remains until scheduler proven stable

### Testing Requirements

- Unit tests for CapabilityRegistry, CapabilityFabric, PipelineScheduler
- Integration tests for cross-pipeline fabric calls
- Contract tests for YAML schema validation
- Performance benchmarks for Fabric overhead

### Rollback Plan

1. Feature flag `FABRIC_ENABLED` controls Fabric activation
2. Fall back to direct module calls if Fabric fails
3. P08's hardcoded loop preserved as fallback

---

## References

- **Architecture Diagrams**:
  - `architecture_diagrams/k0/k0_source_of_truth.mmd` (Layer 6: Event Bus)
  - `architecture_diagrams/k0/project_architecture_part1.mmd` (K0 Kernel)

- **Related ADRs**:
  - ADR-K003: Inline Embedding via UltraBERT
  - ADR-K001: Write Pipeline V1 Hardening

- **Specifications**:
  - `k0/pipelines/whiteboard.md` (P01-P20 definitions)
  - `k0/runtime/schemas.py` (PipelineSpec, ModuleContract)

- **Research**:
  - Dennis & Van Horn 1966 (Capability-based security)
  - Hewitt 1973 (Actor model)
  - Service Mesh patterns (Istio, Linkerd)

---

## Revision History

- 2025-12-14: Initial draft (@K0-Architecture-Team)
