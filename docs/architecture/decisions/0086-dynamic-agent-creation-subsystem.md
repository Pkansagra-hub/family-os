---
adr_number: 0086
title: Dynamic Agent Creation Subsystem
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- maintainability
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
supersedes: []
superseded_by: []
related_adrs: []
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs: []
  affected_contracts:
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_config.fbs
  affected_tests: []
---


# ADR 0086: Dynamic Agent Creation Subsystem

**Date**: October 23, 2025
**Status**: APPROVED - Implementation Phase M1
**Milestone**: M1 - Dynamic Agent Creation & Lifecycle Management
**Related Issues**: 1.1.1, 1.1.2

**Sub-ADRs**: 0086a (Agent Factory), 0086b (Template System), 0086c (Resource Reservation), 0086d (Agent Composition), 0086e (Prompt Directory)

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

### 4. Template System (See ADR 0001b)

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

### Testing Strategy (from ADR 0020 - Testing)

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

## Required Sub-ADRs

This ADR requires the following sub-ADRs for complete implementation:

### **ADR-0086a: Agent Factory Pattern** ✅ REQUIRED
**Purpose**: Core factory implementation for dynamic agent creation
**Scope**:
- AgentFactory singleton class (`k1/l3_execution/agents/factory.py`)
- Agent ID generation algorithm (session-based, collision-resistant)
- Registry integration (O(1) lookup for created agents)
- Error handling and retry logic
- Prometheus metrics (agent_creations_total, creation_latency_ms)

**Deliverables**:
- Factory implementation with `create()`, `get_by_id()`, `get_created_agents()`
- WARD integration tests (ID uniqueness, concurrent creation, error paths)
- Performance validation (<100ms P95 creation latency)

---

### **ADR-0086b: Agent Template System** ✅ REQUIRED
**Purpose**: YAML-based agent configuration with inheritance
**Scope**:
- Template schema design (agent_type, capabilities, resources, personality)
- Template inheritance (base_agent.yml → specialized templates)
- Template validation (JSON Schema validation)
- Template registry with LRU caching
- Versioning strategy (semantic versioning for templates)

**Example Templates**:
- `base_agent.yml` - Default configuration
- `health_specialist.agent.yml` - Health domain expert
- `code_assistant.agent.yml` - Code generation/review
- `research_assistant.agent.yml` - Knowledge synthesis

**Deliverables**:
- Template directory: `k1/config/agent_templates/`
- Template loader with inheritance resolution
- WARD tests for template parsing, validation, inheritance

---

### **ADR-0086c: Resource Reservation System** ✅ REQUIRED
**Purpose**: Pre-allocation of memory, CPU, GPU resources before agent creation
**Scope**:
- ResourceReserver implementation with atomic allocation
- Memory budget tracking (global: 512MB, per-agent: 256MB max)
- Accelerator slot management (NPU/GPU/CPU availability)
- Reservation timeout (30s default, auto-release)
- Fail-fast on insufficient resources

**Performance Targets**:
- Reservation latency: <50ms P95
- Timeout enforcement: <10ms overhead
- Cleanup latency: <20ms P95

**Deliverables**:
- ResourceReserver class (`k1/l3_execution/agents/resource_reserver.py`)
- Integration with thermal placement planner (ADR-0027)
- WARD tests for reservation, timeout, cleanup

---

### **ADR-0086d: Agent Composition Pattern** ✅ REQUIRED
**Purpose**: Dynamic composition of task-specific agents from prompt + tools + persona
**Scope**:
- Composition engine: combine prompt (from directory) + tools (capability-filtered) + persona (traits)
- Agent specialization logic (e.g., "health specialist" = health_prompt + health_tools + friendly_persona)
- Capability-based tool filtering (only TOOL_CALL agents get tools)
- Prompt injection protection (validate prompt templates)
- Composition caching (reuse common configurations)

**Composition Flow**:
```
User Request → Concierge Routes → Factory.create(agent_type="health_specialist")
  ↓
Factory loads template: health_specialist.agent.yml
  ↓
Composition Engine:
  1. Load prompt: agent_prompts/health_specialist.prompt.j2
  2. Filter tools: health_metrics, activity_tracker, sleep_analyzer
  3. Apply persona: friendly, empathetic, data-driven
  ↓
Return composed AI agent → Activate → Process request
```

**Deliverables**:
- CompositionEngine class (`k1/l3_execution/agents/composition.py`)
- Prompt directory structure: `k1/l3_execution/model_hub/prompt_library/agent_prompts/`
- Tool filtering by capability
- WARD tests for composition correctness, security

---

### **ADR-0086e: Prompt Directory & Template Management** ✅ REQUIRED
**Purpose**: Structured storage and versioning of agent-specific prompts
**Scope**:
- Prompt directory structure (`agent_prompts/{agent_type}.prompt.j2`)
- Jinja2 template rendering (<5ms P95)
- Semantic versioning for prompts (breaking changes)
- Prompt validation (max tokens, injection detection)
- Multi-language support (future: i18n)

**Directory Structure**:
```
k1/l3_execution/model_hub/prompt_library/
├── __init__.py
├── agent_prompts/
│   ├── concierge.prompt.j2          # Intent classification
│   ├── planner.prompt.j2            # Task planning
│   ├── researcher.prompt.j2         # Knowledge synthesis
│   ├── safety_watch.prompt.j2       # Safety filtering
│   ├── health_specialist.prompt.j2  # Health domain
│   ├── code_assistant.prompt.j2     # Code tasks
│   └── ...
└── system_prompts/
    ├── base_system.prompt.j2
    └── ...
```

**Deliverables**:
- Prompt loading with Jinja2 rendering
- Versioned prompt templates (v1.0.0, v1.1.0, etc.)
- Validation: token budget, injection protection
- WARD tests for rendering, validation

---

### **ADR-0086f: Dynamic Agent Lifecycle Integration** 🔄 OPTIONAL (Future)
**Purpose**: Integration between dynamic creation and existing lifecycle FSM (ADR-0005)
**Scope**:
- Factory → hire_fire/ integration
- PENDING→WARMING transition for dynamically created agents
- IDLE pool management for task-specific agents
- Termination policy (when to terminate vs pool)

**Note**: Defer to M2 - requires hire_fire/ refactoring

---

### **ADR-0086g: Agent Registry Extension** 🔄 OPTIONAL (Future)
**Purpose**: Extend agent registry to support 58+ agent types (4 AI + 54+ task-specific)
**Scope**:
- Registry YAML specs for all task-specific agents
- Agent type categorization (core infrastructure vs task-specific)
- Registry indexing (by type, by capability, by domain)

**Note**: Defer to M2 - create as needed

---

### **ADR-0086h: Agent Metrics & Observability** 🔄 OPTIONAL (Future)
**Purpose**: Enhanced metrics for dynamic agent creation
**Scope**:
- Per-agent-type creation counters
- Resource utilization tracking
- Composition latency histograms
- Template cache hit rate

**Note**: Basic metrics in ADR-0086a, enhanced in M2

---

## Implementation Priority

**M1 (Milestone 1) - REQUIRED**:
1. ✅ **ADR-0086a**: Agent Factory Pattern (Issue 1.1.1)
2. ✅ **ADR-0086b**: Agent Template System (Issue 1.1.2)
3. ✅ **ADR-0086c**: Resource Reservation System (Issue 1.1.1)
4. ✅ **ADR-0086d**: Agent Composition Pattern (Issue 1.1.2)
5. ✅ **ADR-0086e**: Prompt Directory & Template Management (Issue 1.1.2)

**M2 (Milestone 2) - OPTIONAL**:
6. 🔄 **ADR-0086f**: Dynamic Agent Lifecycle Integration
7. 🔄 **ADR-0086g**: Agent Registry Extension
8. 🔄 **ADR-0086h**: Agent Metrics & Observability

---

**Status**: APPROVED → IN PROGRESS (M1) → IMPLEMENTED