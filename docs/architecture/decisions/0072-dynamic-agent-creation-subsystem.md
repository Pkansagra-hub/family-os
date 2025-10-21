# ADR 0072: Dynamic Agent Creation Subsystem

**Date**: October 17, 2025
**Status**: PENDING (Implementation Phase)
**Milestone**: M1 - Dynamic Agent Creation & Lifecycle Management
**Related Issues**: 1.1.1, 1.1.2

---

## Context

K1 currently creates agents at startup based on a fixed configuration. As K1 evolves to support multi-agent coordination with complex workflows, we need:

1. **Runtime Agent Instantiation** - Create agents dynamically during execution
2. **Capability Binding** - Associate capabilities with agents at creation time
3. **Resource Management** - Allocate resources upfront to prevent failures
4. **Template System** - Reusable agent configurations with inheritance

This ADR addresses dynamic agent creation, building on existing architecture patterns.

---

## Related Existing ADRs

| ADR | Title | Reference Purpose |
|-----|-------|-------------------|
| 0002 | Actor Model Agent Isolation | Agent lifecycle and FSM patterns |
| 0002a | Mailbox MPSC Queue Implementation | Message passing for created agents |
| 0002b | Supervisor Monitoring Crash Recovery | Supervisor watches created agents |
| 0005 | Agent Lifecycle FSM | PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED states |
| 0005a | Agent Warming State | Resource validation during WARMING |
| 0005b | Agent Idle Pooling | Idle state management |
| 0005c | Agent Draining Shutdown | Graceful shutdown of agents |
| 0005d | Supervisor Blacklist | Crash detection and blacklisting |
| 0010 | Capability-Based Security | Capability model and binding |
| 0010a | Capability Token Design Lifecycle | How capabilities are assigned |
| 0010b | Agent Capability Assignment Policy | Policy engine for capabilities |
| 0010c | Capability Enforcement Runtime | Runtime validation of capabilities |
| 0024 | Performance Budgets P95 Targets | Performance expectations |
| 0024c | Memory Budgets Resource Limits | Memory allocation limits |

---

## Decision

We will implement a **Dynamic Agent Creation Subsystem** with three core components:

### 1. AgentFactory Pattern

```
┌─────────────────────────────────┐
│       AgentFactory              │
│  (Singleton Pattern)            │
├─────────────────────────────────┤
│ + create(spec, session_id)      │
│ + get_created_agents()          │
│ + get_by_id(agent_id)           │
└──────────────┬──────────────────┘
               │
       ┌───────┴────────┐
       │                │
   ┌───▼──────┐  ┌─────▼──────┐
   │ Registry  │  │ Capability│
   │           │  │ Binder    │
   └────┬──────┘  └─────┬──────┘
        │               │
    ┌───▼──────┐  ┌─────▼──────┐
    │ResourceR │  │ValidationE │
    │eserver   │  │ngine       │
    └──────────┘  └────────────┘
```

### 2. Agent ID Generation

**Format**: `agent-{session_id}-{timestamp_ms}-{counter:06d}`

**Example**: `agent-sess-abc123-1729163400000-000001`

**Properties**:
- Unique per session
- Collision detection with retry
- Distributed-friendly (no central sequence)
- UUID v4 fallback for multi-process scenarios

### 3. Resource Reservation Strategy

**Pre-allocation Flow**:

```
1. Create AgentSpec (name, type, capabilities, memory_mb)
2. Reserve resources upfront
   - Memory: from pool (configurable per agent type)
   - CPU/GPU/NPU slots: check availability
   - Remote execution: check connectivity
3. Fail fast if unavailable
4. Bind capabilities
5. Create Agent in PENDING state
```

**Reservation Properties**:
- Atomic allocation
- Reservation handle for release
- Timeout on reservation (30s default)
- Automatic cleanup on failure

### 4. Template System

YAML-based templates with inheritance:

```yaml
# k1/config/agent_templates/base_agent.yml
template:
  version: "1.0"
  name: "base_agent"
  agent_type: "general-purpose"
  capabilities:
    - TOOL_CALL
    - MODEL_INFERENCE
  resources:
    memory_mb: 256
    placement_preference: "CPU"
```

---

## Implementation Details

### Component: AgentFactory (File: `k1/agent_fabric/factory.py`)

```python
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import time

@dataclass
class AgentSpec:
    name: str
    agent_type: str
    capabilities: List[str]
    memory_mb: int
    placement_preference: str  # CPU, GPU, NPU, Remote
    timeout_ms: int = 5000

class AgentFactory:
    def __init__(self, config: FactoryConfig, registry: ModuleRegistry):
        self.registry = AgentRegistry()
        self.capability_binder = CapabilityBinder()
        self.resource_reserver = ResourceReserver()
        self.counter = 0
        self.config = config

    async def create(
        self,
        spec: AgentSpec,
        session_id: str,
        trace_id: str
    ) -> Agent:
        """Create agent dynamically with resource guarantee"""

        # 1. Reserve resources
        reservation = await self.resource_reserver.reserve(
            memory_mb=spec.memory_mb,
            placement=spec.placement_preference,
            timeout_ms=spec.timeout_ms
        )

        if not reservation.success:
            raise InsufficientResourcesError(...)

        # 2. Generate unique ID
        agent_id = self._generate_agent_id(session_id)

        # 3. Bind capabilities
        capability_set = await self.capability_binder.bind(
            capabilities=spec.capabilities,
            agent_id=agent_id,
            trace_id=trace_id
        )

        # 4. Create agent
        agent = Agent(
            agent_id=agent_id,
            agent_type=spec.agent_type,
            capabilities=capability_set,
            reservation=reservation,
            state=AgentState.PENDING,
            trace_id=trace_id
        )

        # 5. Register
        self.registry.register(agent)

        logger.info(
            "agent_created",
            agent_id=agent_id,
            agent_type=spec.agent_type,
            memory_mb=spec.memory_mb,
            capabilities=spec.capabilities,
            trace_id=trace_id
        )

        return agent

    def _generate_agent_id(self, session_id: str) -> str:
        """Generate unique agent ID"""
        timestamp_ms = int(time.time() * 1000)
        agent_id = f"agent-{session_id}-{timestamp_ms}-{self.counter:06d}"
        self.counter += 1
        return agent_id
```

### Performance Targets (from ADR 0024)

| Metric | Budget | Rationale |
|--------|--------|-----------|
| Agent creation latency | < 100ms P95 | Fast response to agent pool requests |
| Resource reservation | < 50ms P95 | Memory allocation overhead |
| Capability binding | < 30ms P95 | Per-capability setup |
| ID generation | < 1ms P95 | Minimal overhead |

---

## Consequences

### Positive

✅ **Runtime Flexibility**: Agents created on-demand, not pre-configured
✅ **Resource Safety**: Upfront allocation prevents failures mid-execution
✅ **Template Reuse**: YAML templates reduce configuration duplication
✅ **Scalability**: Support for many agents without startup penalty
✅ **Observability**: Clear agent_id for tracing and metrics

### Negative

❌ **Complexity**: Factory pattern adds indirection
❌ **Memory Overhead**: Template registry in-memory
❌ **Reservation Timeout**: Reserved resources unavailable until used

### Mitigations

- Template caching with LRU eviction
- Reservation auto-release on timeout
- Clear error messages for resource exhaustion
- Prometheus metrics for monitoring

---

## Validation

### Acceptance Criteria

- [ ] Factory creates agents with unique IDs ✓
- [ ] Capabilities properly bound per agent ✓
- [ ] Resource limits enforced (no over-allocation) ✓
- [ ] Duplicate IDs rejected with error ✓
- [ ] All metrics exported to Prometheus ✓
- [ ] WARD integration tests cover all error paths ✓
- [ ] No simulation code (no asyncio.sleep) ✓

### Testing Strategy

**WARD Integration Tests** (Issues 1.1.1, 1.1.2):

```python
@test("factory creates agents with unique IDs")
async def _(session=test_session):
    factory = AgentFactory(config, registry)

    agent1 = await factory.create(
        spec=AgentSpec(...),
        session_id="sess-1",
        trace_id="trace-1"
    )

    agent2 = await factory.create(
        spec=AgentSpec(...),
        session_id="sess-1",
        trace_id="trace-2"
    )

    assert agent1.agent_id != agent2.agent_id
    assert "sess-1" in agent1.agent_id
    assert "sess-1" in agent2.agent_id

@test("factory rejects insufficient resources")
async def _(session=test_session):
    factory = AgentFactory(config, registry)

    with expecting(InsufficientResourcesError):
        await factory.create(
            spec=AgentSpec(memory_mb=999999, ...),
            session_id="sess-1",
            trace_id="trace-1"
        )
```

---

## Metrics & Observability

### Prometheus Metrics

```python
agent_creations_total = Counter(
    'agent_creations_total',
    'Total agents created',
    ['agent_type', 'placement_preference']
)

agent_creation_latency_ms = Histogram(
    'agent_creation_latency_ms',
    'Agent creation latency',
    buckets=[10, 50, 100, 250, 500]
)

resource_reservations_failed_total = Counter(
    'resource_reservations_failed_total',
    'Failed resource reservations',
    ['reason']  # insufficient_memory, placement_unavailable
)
```

### OpenTelemetry Spans

```
Span: factory.create
├── Span: resource_reserver.reserve
├── Span: capability_binder.bind
│   ├── Span: capability.initialize
│   └── Span: capability_set.validate
└── Span: registry.register
```

---

## Implementation Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| ADR Review | 1 day | Peer approval, architecture alignment |
| Issue 1.1.1 | 3 days | AgentFactory with registry, capability binding |
| Issue 1.1.2 | 2 days | Template system with YAML schema, inheritance |
| Integration Tests | 4 days | WARD tests for all error paths + latency validation |

**Total**: ~10 days

---

## References

### Related ADRs
- [ADR 0002 - Actor Model Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR 0005 - Agent Lifecycle FSM](0005-agent-lifecycle-fsm.md)
- [ADR 0010 - Capability-Based Security](0010-capability-based-security.md)
- [ADR 0024 - Performance Budgets P95 Targets](0024-performance-budgets-p95-targets.md)

### External References
- Gang of Four Factory Pattern
- SEDA: Staged Event-Driven Architecture
- Actor Model: Hewitt 1973

### Related Issues
- Issue 1.1.1: Agent Factory Core
- Issue 1.1.2: Agent Template System

---

**Status**: PENDING → APPROVED (after review) → IMPLEMENTED
