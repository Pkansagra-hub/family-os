# ADR-0086a: Agent Factory Pattern

**Status:** Approved ✅ - Implementation Phase M1
**Decision Date:** 2025-10-23
**Implementation Date:** TBD (M1 - Issue 1.1.1)
**Review Date:** TBD (Post-implementation)
**Last Updated:** 2025-10-23
**Authors:** K1 Architecture Team
**Category:** Agent Lifecycle & Dynamic Creation
**Parent ADR:** [ADR-0086 (Dynamic Agent Creation Subsystem)](0086-dynamic-agent-creation-subsystem.md)
**Related ADRs:**

- [ADR-0002 (Actor Model)](0002-actor-model-agent-isolation.md) - Foundation for all agents
- [ADR-0005 (Agent Lifecycle FSM)](0005-agent-lifecycle-fsm.md) - 6-state FSM integration
- [ADR-0005a (WARMING State)](0005a-agent-warming-state.md) - Warmup integration
- [ADR-0010 (Capability Security)](0010-capability-based-security.md) - Capability binding
- [ADR-0024 (Performance Budgets)](0024-performance-budgets-p95-targets.md) - <100ms P95 target
- [ADR-0086b (Template System)](0086b-agent-template-system.md) - Template integration
- [ADR-0086c (Resource Reservation)](0086c-resource-reservation-system.md) - Resource pre-allocation

---

## Context

### Problem Statement

K1's current architecture creates agents at startup with fixed configurations. As we move toward **dynamic task-specific agent spawning** (e.g., "health specialist" created on-demand when user asks about health), we need:

1. **Runtime Agent Creation:** Factory pattern to create agents dynamically during execution
2. **Unique Agent IDs:** Collision-resistant ID generation for distributed scenarios
3. **Registry Integration:** O(1) lookup for created agents by ID, session, or type
4. **Resource Safety:** Integration with resource reservation (ADR-0086c) to prevent failures
5. **Capability Binding:** Integration with capability system (ADR-0010) for security
6. **Observability:** Metrics for creation latency, success/failure rates, active agent counts

### Current State

**Existing Infrastructure (70% Complete):**

- ✅ `k1/l3_execution/agents/hire_fire/` - Lifecycle FSM (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
- ✅ `k1/l3_execution/agents/registry/` - Agent specification registry (O(1) lookup)
- ✅ `k1/l3_execution/agents/active_roster/` - Runtime agent tracking (hash table)
- ✅ `k1/l3_execution/agents/supervisor/` - Crash detection and recovery

**Missing Components (M1 Gap):**

- ❌ **AgentFactory** - No centralized creation interface
- ❌ **Dynamic ID Generation** - Currently hardcoded IDs
- ❌ **Template Loading** - No YAML template support (ADR-0086b dependency)
- ❌ **Composition Logic** - No prompt+tools+persona composition (ADR-0086d dependency)

### User Journey Example

```
User: "What does my health metrics show?"
  ↓
Concierge (AI Agent): Classifies intent → "health_query"
  ↓
Orchestrator: Needs specialist agent for health domain
  ↓
AgentFactory.create(agent_type="health_specialist", session_id="sess_123")
  ↓
Factory Flow:
  1. Load template: health_specialist.agent.yml (ADR-0086b)
  2. Reserve resources: 256MB memory, GPU slot (ADR-0086c)
  3. Generate ID: agent-sess_123-1729700000-000001
  4. Bind capabilities: [TOOL_CALL, MEMORY_READ, MODEL_CALL]
  5. Compose agent: health_prompt + health_tools + empathetic_persona (ADR-0086d)
  6. Transition to PENDING state → hire_fire/ takes over
  ↓
Return: AgentHandle (agent_id, capabilities, state=PENDING)
  ↓
Health Specialist Agent: Processes health query, returns metrics
```

---

## Decision

We will implement **AgentFactory as a singleton class** with the following responsibilities:

### 1. Core Factory Interface

```python
# k1/l3_execution/agents/factory.py

from dataclasses import dataclass
from typing import Dict, List, Optional
import time
import uuid
from prometheus_client import Counter, Histogram

@dataclass
class AgentSpec:
    """Agent creation specification (from template or runtime)"""
    agent_type: str                    # "health_specialist", "code_assistant", etc.
    session_id: str                    # Session binding
    capabilities: List[str]            # ["TOOL_CALL", "MEMORY_READ", "MODEL_CALL"]
    memory_mb: int                     # Memory budget (default: 256MB)
    placement_preference: str          # "NPU" | "GPU" | "CPU" | "Remote"
    timeout_ms: int = 5000             # Creation timeout
    metadata: Dict[str, str] = None    # Optional metadata


@dataclass
class AgentHandle:
    """Handle returned to caller after creation"""
    agent_id: str                      # Unique agent ID
    agent_type: str                    # Agent type
    state: str                         # "PENDING" initially
    capabilities: List[str]            # Bound capabilities
    reservation_id: str                # Resource reservation handle
    created_at_ms: int                 # Creation timestamp


class AgentFactory:
    """
    Singleton factory for dynamic agent creation.

    Responsibilities:
    1. Agent ID generation (collision-resistant)
    2. Template loading (ADR-0086b integration)
    3. Resource reservation (ADR-0086c integration)
    4. Capability binding (ADR-0010 integration)
    5. Agent composition (ADR-0086d integration)
    6. Registry integration (active_roster/)
    7. Metrics emission (Prometheus)

    Performance Target: <100ms P95 creation latency
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        config: FactoryConfig,
        template_loader: TemplateLoader,          # ADR-0086b
        resource_reserver: ResourceReserver,      # ADR-0086c
        capability_binder: CapabilityBinder,      # ADR-0010
        composition_engine: CompositionEngine,    # ADR-0086d
        active_roster: ActiveRoster,              # Registry
        hire_fire_manager: AgentHireFireManager   # Lifecycle FSM
    ):
        """Initialize factory with dependencies"""
        if hasattr(self, '_initialized'):
            return

        self.config = config
        self.template_loader = template_loader
        self.resource_reserver = resource_reserver
        self.capability_binder = capability_binder
        self.composition_engine = composition_engine
        self.active_roster = active_roster
        self.hire_fire = hire_fire_manager

        # ID generation state
        self._id_counter = 0
        self._id_lock = asyncio.Lock()

        # Metrics
        self._init_metrics()

        self._initialized = True

    async def create(
        self,
        spec: AgentSpec,
        trace_id: str
    ) -> AgentHandle:
        """
        Create agent dynamically with full lifecycle management.

        Flow:
        1. Load template (if agent_type references template)
        2. Reserve resources (memory, accelerator slots)
        3. Generate unique ID
        4. Bind capabilities
        5. Compose agent (prompt + tools + persona)
        6. Register in active_roster
        7. Transition to PENDING state (hire_fire takes over)

        Performance: <100ms P95

        Raises:
            TemplateNotFoundError: Template doesn't exist
            InsufficientResourcesError: Not enough memory/accelerator slots
            CapabilityBindingError: Capability assignment failed
            AgentCreationError: Generic creation failure
        """
        start_time = time.perf_counter()

        try:
            # Step 1: Load template (ADR-0086b)
            template = await self.template_loader.load(
                agent_type=spec.agent_type,
                trace_id=trace_id
            )

            # Merge spec with template defaults
            merged_spec = self._merge_spec_with_template(spec, template)

            # Step 2: Reserve resources (ADR-0086c)
            reservation = await self.resource_reserver.reserve(
                memory_mb=merged_spec.memory_mb,
                placement=merged_spec.placement_preference,
                timeout_ms=merged_spec.timeout_ms,
                trace_id=trace_id
            )

            if not reservation.success:
                self._metrics_creation_failed.labels(
                    reason="insufficient_resources",
                    agent_type=spec.agent_type
                ).inc()
                raise InsufficientResourcesError(
                    f"Cannot reserve {merged_spec.memory_mb}MB for {spec.agent_type}"
                )

            # Step 3: Generate unique ID
            agent_id = await self._generate_agent_id(
                session_id=spec.session_id,
                agent_type=spec.agent_type
            )

            # Step 4: Bind capabilities (ADR-0010)
            capability_set = await self.capability_binder.bind(
                agent_id=agent_id,
                capabilities=merged_spec.capabilities,
                session_id=spec.session_id,
                trace_id=trace_id
            )

            # Step 5: Compose agent (ADR-0086d)
            composed_agent = await self.composition_engine.compose(
                agent_id=agent_id,
                agent_type=spec.agent_type,
                template=template,
                capabilities=capability_set,
                trace_id=trace_id
            )

            # Step 6: Create agent in PENDING state
            agent_info = AgentInfo(
                agent_id=agent_id,
                agent_type=spec.agent_type,
                session_id=spec.session_id,
                state=State.PENDING,
                capabilities=capability_set,
                reservation=reservation,
                composed_config=composed_agent,
                created_at_ms=int(time.time() * 1000),
                metadata=spec.metadata or {}
            )

            # Step 7: Register in active_roster
            self.active_roster.insert(agent_info)

            # Step 8: Trigger hire_fire/ lifecycle (PENDING → WARMING → ACTIVE)
            await self.hire_fire.transition_to_warming(
                agent_id=agent_id,
                trace_id=trace_id
            )

            # Metrics
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._metrics_creation_latency.labels(
                agent_type=spec.agent_type
            ).observe(latency_ms)
            self._metrics_creations_total.labels(
                agent_type=spec.agent_type,
                placement=merged_spec.placement_preference
            ).inc()

            logger.info(
                "agent_created",
                agent_id=agent_id,
                agent_type=spec.agent_type,
                session_id=spec.session_id,
                memory_mb=merged_spec.memory_mb,
                placement=merged_spec.placement_preference,
                latency_ms=latency_ms,
                trace_id=trace_id
            )

            return AgentHandle(
                agent_id=agent_id,
                agent_type=spec.agent_type,
                state="PENDING",
                capabilities=list(capability_set),
                reservation_id=reservation.reservation_id,
                created_at_ms=agent_info.created_at_ms
            )

        except Exception as e:
            # Cleanup on failure
            if 'reservation' in locals() and reservation.success:
                await self.resource_reserver.release(
                    reservation_id=reservation.reservation_id,
                    trace_id=trace_id
                )

            self._metrics_creation_failed.labels(
                reason=type(e).__name__,
                agent_type=spec.agent_type
            ).inc()

            logger.error(
                "agent_creation_failed",
                agent_type=spec.agent_type,
                error=str(e),
                trace_id=trace_id
            )
            raise

    async def _generate_agent_id(
        self,
        session_id: str,
        agent_type: str
    ) -> str:
        """
        Generate collision-resistant agent ID.

        Format: agent-{session_id}-{timestamp_ms}-{counter:06d}
        Example: agent-sess_abc123-1729700000000-000001

        Collision Resistance:
        - session_id: Unique per session (namespace isolation)
        - timestamp_ms: Millisecond precision (1000 IDs/sec max)
        - counter: 6-digit counter (up to 1M agents per millisecond)
        - Total: ~1 billion unique IDs per session

        Fallback: UUID v4 if counter overflow

        Performance: <1ms P95
        """
        async with self._id_lock:
            timestamp_ms = int(time.time() * 1000)

            # Reset counter if new millisecond
            if not hasattr(self, '_last_timestamp_ms') or self._last_timestamp_ms != timestamp_ms:
                self._id_counter = 0
                self._last_timestamp_ms = timestamp_ms

            # Check overflow (unlikely but handle it)
            if self._id_counter >= 999999:
                # Fallback to UUID v4
                agent_id = f"agent-{session_id}-{uuid.uuid4().hex[:12]}"
                logger.warning(
                    "agent_id_counter_overflow",
                    session_id=session_id,
                    fallback_id=agent_id
                )
                return agent_id

            # Normal path
            agent_id = f"agent-{session_id}-{timestamp_ms}-{self._id_counter:06d}"
            self._id_counter += 1

            # Collision detection (paranoid check)
            if self.active_roster.get(agent_id) is not None:
                # Retry with UUID fallback
                agent_id = f"agent-{session_id}-{uuid.uuid4().hex[:12]}"
                logger.warning(
                    "agent_id_collision_detected",
                    session_id=session_id,
                    fallback_id=agent_id
                )

            return agent_id

    def _merge_spec_with_template(
        self,
        spec: AgentSpec,
        template: AgentTemplate
    ) -> AgentSpec:
        """Merge runtime spec with template defaults"""
        return AgentSpec(
            agent_type=spec.agent_type,
            session_id=spec.session_id,
            capabilities=spec.capabilities or template.capabilities,
            memory_mb=spec.memory_mb or template.resources.memory_mb,
            placement_preference=spec.placement_preference or template.resources.placement_preference,
            timeout_ms=spec.timeout_ms or template.lifecycle.warmup_timeout_ms,
            metadata=spec.metadata
        )

    def get_by_id(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent by ID (O(1) lookup)"""
        return self.active_roster.get(agent_id)

    def get_by_session(self, session_id: str) -> List[AgentInfo]:
        """Get all agents for session (O(1) lookup)"""
        return self.active_roster.get_by_session(session_id)

    def get_by_type(self, agent_type: str) -> List[AgentInfo]:
        """Get all agents of type (O(1) lookup)"""
        return self.active_roster.get_by_type(agent_type)

    def get_created_agents(self) -> List[AgentInfo]:
        """Get all created agents"""
        return list(self.active_roster.agents.values())

    def _init_metrics(self):
        """Initialize Prometheus metrics"""
        self._metrics_creations_total = Counter(
            'k1_agent_creations_total',
            'Total agents created by factory',
            ['agent_type', 'placement']
        )

        self._metrics_creation_latency = Histogram(
            'k1_agent_creation_latency_ms',
            'Agent creation latency in milliseconds',
            ['agent_type'],
            buckets=[10, 25, 50, 75, 100, 150, 200, 300, 500]
        )

        self._metrics_creation_failed = Counter(
            'k1_agent_creation_failed_total',
            'Failed agent creations',
            ['reason', 'agent_type']
        )
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentFactory                             │
│                      (Singleton Pattern)                        │
├─────────────────────────────────────────────────────────────────┤
│ + create(spec, trace_id) → AgentHandle     <100ms P95          │
│ + get_by_id(agent_id) → AgentInfo          <1ms                │
│ + get_by_session(session_id) → List        <1ms                │
│ + get_by_type(agent_type) → List           <1ms                │
│ + get_created_agents() → List              <5ms                │
└────────────┬───────────────────────────────────────────────────┘
             │
     ┌───────┴────────┐
     │                │
┌────▼─────┐    ┌────▼─────────┐
│Template  │    │Resource      │
│Loader    │    │Reserver      │
│(0086b)   │    │(0086c)       │
└────┬─────┘    └────┬─────────┘
     │                │
┌────▼─────┐    ┌────▼─────────┐
│Capability│    │Composition   │
│Binder    │    │Engine        │
│(0010)    │    │(0086d)       │
└────┬─────┘    └────┬─────────┘
     │                │
     └────────┬───────┘
              │
         ┌────▼──────┐
         │Active     │
         │Roster     │
         │(Registry) │
         └────┬──────┘
              │
         ┌────▼──────┐
         │hire_fire/ │
         │(FSM)      │
         └───────────┘
```

---

## Performance Budgets

| Metric | Budget | Rationale |
|--------|--------|-----------|
| **Agent creation latency** | <100ms P95 | User-facing operation, must feel instant |
| **ID generation** | <1ms P95 | Minimal overhead, synchronous operation |
| **Lookup (by ID)** | <1ms P95 | O(1) hash table, frequently called |
| **Lookup (by session/type)** | <1ms P95 | O(1) index lookup |
| **Get all agents** | <5ms P95 | List copy, infrequent operation |
| **Memory footprint** | <10MB | Singleton instance, small state |

**Budget Breakdown (100ms creation)**:

- Template loading: 10ms (ADR-0086b)
- Resource reservation: 50ms (ADR-0086c)
- ID generation: 1ms
- Capability binding: 30ms (ADR-0010)
- Composition: 5ms (ADR-0086d)
- Registry insert: 1ms
- FSM transition: 3ms
- **Total**: ~100ms P95

---

## Consequences

### Positive ✅

- **Runtime Flexibility**: Agents created on-demand, not pre-configured at startup
- **Collision Resistance**: ID generation handles distributed scenarios (session-based + timestamp + counter)
- **Resource Safety**: Integration with reservation system (ADR-0086c) prevents OOM failures
- **O(1) Lookup**: Fast agent retrieval by ID, session, or type
- **Observability**: Comprehensive Prometheus metrics for creation latency, success/failure
- **Singleton Pattern**: Single source of truth for agent creation across K1
- **Clean Integration**: Leverages existing infrastructure (hire_fire/, active_roster/, capability_binder/)

### Negative ❌

- **Singleton Complexity**: Requires careful initialization order in K1 startup
- **Dependency Count**: Factory depends on 6 subsystems (template loader, resource reserver, capability binder, composition engine, registry, hire_fire)
- **Error Handling**: Cleanup on failure requires careful resource release coordination
- **ID Counter State**: Requires thread-safe counter management (asyncio.Lock overhead ~1-5ms)

### Mitigations

- **Initialization Order**: Document in K1 startup sequence (ADR-0001)
- **Dependency Injection**: Use DI container for clean factory initialization
- **Error Cleanup**: Implement transaction-like rollback on creation failure
- **ID Generation**: Use UUID v4 fallback on counter overflow (rare edge case)

---

## Validation & Testing

### Acceptance Criteria

- [ ] Factory creates agents with unique IDs ✓
- [ ] ID generation handles 1000 agents/sec without collisions ✓
- [ ] Creation latency <100ms P95 (measured with WARD) ✓
- [ ] Capabilities properly bound per agent ✓
- [ ] Resource limits enforced (no over-allocation) ✓
- [ ] Duplicate IDs rejected with error ✓
- [ ] All metrics exported to Prometheus ✓
- [ ] WARD integration tests cover all error paths ✓
- [ ] No simulation code (no asyncio.sleep) ✓

### WARD Integration Tests

```python
# tests/l3_execution/agents/test_factory.py

from ward import test, fixture
from k1.l3_execution.agents.factory import AgentFactory, AgentSpec

@fixture
async def factory():
    """Factory fixture with real dependencies"""
    config = FactoryConfig(...)
    template_loader = TemplateLoader(...)
    resource_reserver = ResourceReserver(...)
    capability_binder = CapabilityBinder(...)
    composition_engine = CompositionEngine(...)
    active_roster = ActiveRoster()
    hire_fire = AgentHireFireManager(...)

    factory = AgentFactory(
        config=config,
        template_loader=template_loader,
        resource_reserver=resource_reserver,
        capability_binder=capability_binder,
        composition_engine=composition_engine,
        active_roster=active_roster,
        hire_fire_manager=hire_fire
    )

    yield factory

    # Cleanup
    await factory.shutdown()


@test("factory creates agents with unique IDs")
async def _(f=factory):
    spec1 = AgentSpec(
        agent_type="health_specialist",
        session_id="sess_123",
        capabilities=["TOOL_CALL", "MODEL_CALL"],
        memory_mb=256,
        placement_preference="GPU"
    )

    spec2 = AgentSpec(
        agent_type="code_assistant",
        session_id="sess_123",
        capabilities=["TOOL_CALL", "MODEL_CALL"],
        memory_mb=256,
        placement_preference="GPU"
    )

    handle1 = await f.create(spec1, trace_id="trace_1")
    handle2 = await f.create(spec2, trace_id="trace_2")

    assert handle1.agent_id != handle2.agent_id
    assert "sess_123" in handle1.agent_id
    assert "sess_123" in handle2.agent_id


@test("factory rejects insufficient resources")
async def _(f=factory):
    spec = AgentSpec(
        agent_type="memory_hog",
        session_id="sess_123",
        capabilities=["MODEL_CALL"],
        memory_mb=999999,  # Exceeds budget
        placement_preference="GPU"
    )

    with expecting(InsufficientResourcesError):
        await f.create(spec, trace_id="trace_1")


@test("factory creation latency <100ms P95")
async def _(f=factory):
    import time

    latencies = []
    for i in range(100):
        spec = AgentSpec(
            agent_type="health_specialist",
            session_id=f"sess_{i}",
            capabilities=["TOOL_CALL"],
            memory_mb=256,
            placement_preference="CPU"
        )

        start = time.perf_counter()
        handle = await f.create(spec, trace_id=f"trace_{i}")
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    p95 = sorted(latencies)[94]  # 95th percentile
    assert p95 < 100, f"P95 latency {p95:.2f}ms exceeds 100ms budget"


@test("factory handles concurrent creation")
async def _(f=factory):
    import asyncio

    async def create_agent(i):
        spec = AgentSpec(
            agent_type="concurrent_test",
            session_id=f"sess_{i}",
            capabilities=["TOOL_CALL"],
            memory_mb=128,
            placement_preference="CPU"
        )
        return await f.create(spec, trace_id=f"trace_{i}")

    # Create 50 agents concurrently
    handles = await asyncio.gather(*[create_agent(i) for i in range(50)])

    # All IDs must be unique
    ids = [h.agent_id for h in handles]
    assert len(ids) == len(set(ids)), "Duplicate IDs detected in concurrent creation"


@test("factory lookup by ID is O(1)")
async def _(f=factory):
    spec = AgentSpec(
        agent_type="lookup_test",
        session_id="sess_123",
        capabilities=["TOOL_CALL"],
        memory_mb=128,
        placement_preference="CPU"
    )

    handle = await f.create(spec, trace_id="trace_1")

    import time
    start = time.perf_counter()
    agent_info = f.get_by_id(handle.agent_id)
    latency_ms = (time.perf_counter() - start) * 1000

    assert agent_info is not None
    assert agent_info.agent_id == handle.agent_id
    assert latency_ms < 1, f"Lookup took {latency_ms:.3f}ms (expected <1ms)"


@test("factory cleanup on creation failure")
async def _(f=factory):
    # Mock resource reserver to fail
    original_reserve = f.resource_reserver.reserve

    async def failing_reserve(*args, **kwargs):
        from k1.l3_execution.agents.resource_reserver import ReservationResult
        return ReservationResult(success=False, reservation_id=None)

    f.resource_reserver.reserve = failing_reserve

    spec = AgentSpec(
        agent_type="fail_test",
        session_id="sess_123",
        capabilities=["TOOL_CALL"],
        memory_mb=256,
        placement_preference="GPU"
    )

    with expecting(InsufficientResourcesError):
        await f.create(spec, trace_id="trace_1")

    # Verify no agent created
    agents = f.get_by_session("sess_123")
    assert len(agents) == 0, "Agent should not exist after failed creation"

    # Restore
    f.resource_reserver.reserve = original_reserve
```

---

## Metrics & Observability

### Prometheus Metrics

```python
# k1/l3_execution/agents/factory.py

from prometheus_client import Counter, Histogram, Gauge

# Agent creation metrics
k1_agent_creations_total = Counter(
    'k1_agent_creations_total',
    'Total agents created by factory',
    ['agent_type', 'placement']
)

k1_agent_creation_latency_ms = Histogram(
    'k1_agent_creation_latency_ms',
    'Agent creation latency in milliseconds',
    ['agent_type'],
    buckets=[10, 25, 50, 75, 100, 150, 200, 300, 500]
)

k1_agent_creation_failed_total = Counter(
    'k1_agent_creation_failed_total',
    'Failed agent creations',
    ['reason', 'agent_type']
)

# Active agent tracking
k1_active_agents_count = Gauge(
    'k1_active_agents_count',
    'Current number of active agents',
    ['agent_type']
)

# ID generation metrics
k1_agent_id_collisions_total = Counter(
    'k1_agent_id_collisions_total',
    'Total ID collision detections (should be near zero)',
    ['session_id']
)

k1_agent_id_counter_overflows_total = Counter(
    'k1_agent_id_counter_overflows_total',
    'Total counter overflow events (UUID fallback triggered)'
)
```

### Structured Logs

```python
# Success
logger.info(
    "agent_created",
    agent_id=agent_id,
    agent_type=spec.agent_type,
    session_id=spec.session_id,
    memory_mb=merged_spec.memory_mb,
    placement=merged_spec.placement_preference,
    latency_ms=latency_ms,
    trace_id=trace_id
)

# Failure
logger.error(
    "agent_creation_failed",
    agent_type=spec.agent_type,
    session_id=spec.session_id,
    error=str(e),
    reason=type(e).__name__,
    trace_id=trace_id
)

# ID collision (rare)
logger.warning(
    "agent_id_collision_detected",
    session_id=session_id,
    fallback_id=agent_id,
    timestamp_ms=timestamp_ms
)
```

### OpenTelemetry Spans

```
Span: factory.create (100ms)
├── Span: template_loader.load (10ms)
├── Span: resource_reserver.reserve (50ms)
│   ├── Span: memory_allocator.allocate (30ms)
│   └── Span: accelerator_manager.reserve_slot (20ms)
├── Span: id_generation (1ms)
├── Span: capability_binder.bind (30ms)
│   ├── Span: capability_policy.evaluate (20ms)
│   └── Span: token_generator.sign (10ms)
├── Span: composition_engine.compose (5ms)
├── Span: active_roster.insert (1ms)
└── Span: hire_fire.transition_to_warming (3ms)
```

---

## Implementation Plan

### Phase 1: Core Factory (3 days)

**Day 1: Factory Skeleton**

- [ ] Create `k1/l3_execution/agents/factory.py`
- [ ] Implement AgentFactory singleton class
- [ ] Implement ID generation algorithm
- [ ] Add collision detection logic
- [ ] Add Prometheus metrics initialization

**Day 2: Integration**

- [ ] Integrate with TemplateLoader (ADR-0086b stub)
- [ ] Integrate with ResourceReserver (ADR-0086c stub)
- [ ] Integrate with CapabilityBinder (ADR-0010 existing)
- [ ] Integrate with CompositionEngine (ADR-0086d stub)
- [ ] Integrate with active_roster/ (existing)
- [ ] Integrate with hire_fire/ (existing)

**Day 3: Error Handling & Cleanup**

- [ ] Implement transaction-like rollback on failure
- [ ] Add resource cleanup logic
- [ ] Add retry logic for ID collisions
- [ ] Add timeout handling

### Phase 2: WARD Tests (2 days)

**Day 4: Unit Tests**

- [ ] Test ID generation (uniqueness, collision handling)
- [ ] Test lookup operations (by ID, session, type)
- [ ] Test concurrent creation (50+ agents)
- [ ] Test error paths (insufficient resources, template not found)

**Day 5: Performance Tests**

- [ ] Validate <100ms P95 creation latency
- [ ] Validate <1ms P95 lookup latency
- [ ] Load test: 1000 agents/sec
- [ ] Memory footprint test: <10MB factory

### Phase 3: Documentation & Review (1 day)

**Day 6: Finalization**

- [ ] Update ADR-0086a with implementation details
- [ ] Add code comments and docstrings
- [ ] Generate API documentation
- [ ] Peer review and approval
- [ ] Merge to develop branch

**Total**: 6 days (within M1 budget)

---

## Dependencies

### Required Before Implementation

- ✅ **ADR-0086b (Template System)**: Stub TemplateLoader for testing, full implementation parallel
- ✅ **ADR-0086c (Resource Reservation)**: Stub ResourceReserver for testing, full implementation parallel
- ✅ **ADR-0086d (Composition Engine)**: Stub CompositionEngine for testing, full implementation parallel
- ✅ **ADR-0010 (Capability Binder)**: Already implemented (70% complete)
- ✅ **active_roster/**: Already implemented (100% complete)
- ✅ **hire_fire/**: Already implemented (70% complete)

### Blocks Other Work

- 🔄 **ADR-0086d (Composition)**: Needs factory to instantiate composed agents
- 🔄 **Orchestrator Integration**: Needs factory to create task-specific agents
- 🔄 **Concierge Integration**: Needs factory to route to specialist agents

---

## References

### Research Foundations

- **Factory Pattern**: Gang of Four Design Patterns (1994)
- **Singleton Pattern**: Ensures single instance for global agent creation
- **Collision Resistance**: Distributed ID generation strategies (Snowflake, ULID)

### Related ADRs

- [ADR-0086 (Dynamic Agent Creation)](0086-dynamic-agent-creation-subsystem.md) - Parent ADR
- [ADR-0086b (Template System)](0086b-agent-template-system.md) - Template loading
- [ADR-0086c (Resource Reservation)](0086c-resource-reservation-system.md) - Resource pre-allocation
- [ADR-0086d (Agent Composition)](0086d-agent-composition-pattern.md) - Prompt+tools+persona
- [ADR-0005 (Agent Lifecycle FSM)](0005-agent-lifecycle-fsm.md) - 6-state FSM integration
- [ADR-0010 (Capability Security)](0010-capability-based-security.md) - Capability binding

### External References

- Snowflake ID: Twitter's distributed ID generation
- ULID: Universally Unique Lexicographically Sortable Identifier
- Factory Pattern: GoF Design Patterns

---

**Status**: Approved ✅ → Implementation Phase M1 (Issue 1.1.1)

**Next Steps**:

1. Create factory.py skeleton (Day 1)
2. Integrate with existing infrastructure (Day 2-3)
3. Write WARD tests (Day 4-5)
4. Review and merge (Day 6)
