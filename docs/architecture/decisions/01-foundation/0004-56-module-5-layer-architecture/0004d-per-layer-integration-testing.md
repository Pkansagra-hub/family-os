---
adr_number: '0004d'
title: Per-Layer Integration Testing Strategy
status: COMPLETED
date_created: '2025-10-12'
date_updated: '2025-10-12'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- modularity
- performance
- reliability
- scalability
- testing
- maintainability
- interoperability
supersedes: []
superseded_by: []
related_adrs:
- ADR-0002
- ADR-0004
- ADR-0004a
- ADR-0004b
- ADR-0004c
- ADR-0006
- ADR-0007
- ADR-0012
implementation_status: COMPLETED
implementation_date: null
implementation_phase: Phase 1 (Foundation)
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
- k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
- k1/contracts/flatbuffers/layer3_execution/model_request.fbs
- k1/contracts/flatbuffers/layer3_execution/model_response.fbs
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Adding a new layer
  - Changing existing layer dependency rules
  - Introduction of new module in any layer
  - Updating performance budgets for any layer
  - Modifying API contracts between layers
  affected_adrs:
  - ADR-0001c
  - ADR-0002c
  - ADR-0006d
  - ADR-0012d
  - ADR-0024
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
---

# ADR-0004d: Per-Layer Integration Testing Strategy

**Status:** ✅ **COMPLETED** (2025-10-12)
**Date:** 2025-10-12
**Last Updated:** 2025-10-12
**Deciders:** K1 Architecture Team
**Technical Story:** Define integration testing strategy for each layer (L1-L5) with layer-specific test suites, contracts, and performance validation
**Parent ADR:** [ADR-0004: 52-Module 5-Layer Microkernel Architecture](0004-52-module-5-layer-architecture.md)
**Related ADRs:**
- [ADR-0004a: Layer 1-2 Event Bus Communication](0004a-layer1-2-event-bus-communication.md)
- [ADR-0004b: Module Dependency Management](0004b-module-dependency-management.md)
- [ADR-0004c: Module README Template](0004c-module-readme-template.md)

---

## Executive Summary

K1's **5-layer architecture** requires **layer-specific integration tests** to validate:
- **Intra-layer contracts** (modules within same layer communicate correctly)
- **Inter-layer contracts** (Layer N → Layer M communication follows layering rules)
- **Performance budgets** (each layer meets latency/memory targets)

**Solution:** **Per-layer integration test suites** with WARD framework.

**Key Features:**
- **5 test directories:** `tests/integration/layer1/`, `tests/integration/layer2/`, ... `layer5/`
- **Layer-specific scenarios:** L1 (event publish), L2 (orchestration), L3 (agent lifecycle), L4 (state management), L5 (infrastructure resilience)
- **Contract validation:** Test layering rules (no forbidden imports triggered)
- **Performance validation:** Assert P95 latency budgets met
- **End-to-end tests:** `tests/integration/end_to_end/` (cross all layers)

**Test Organization:**
```
tests/
├── unit/                        # Unit tests (per module)
│   ├── execution/
│   ├── orchestration/
│   └── ...
├── integration/                 # Integration tests
│   ├── layer1/                 # Layer 1 (Input Processing)
│   ├── layer2/                 # Layer 2 (Orchestration)
│   ├── layer3/                 # Layer 3 (Execution)
│   ├── layer4/                 # Layer 4 (Runtime Core)
│   ├── layer5/                 # Layer 5 (Infrastructure)
│   └── end_to_end/             # Full stack (L1 → L5)
└── performance/                 # Performance benchmarks
```

**Performance Targets (P95):**
- **Layer 1:** Event publish <2ms, intent classification <50ms
- **Layer 2:** Orchestration <250ms, planning <5000ms
- **Layer 3:** Agent hire <600ms, tool call <3000ms
- **Layer 4:** SessionState serialization <1ms, learning update <100ms
- **Layer 5:** Event bus delivery <5ms, metrics export <10ms

---

## Context

### The Challenge

**K1 has 52+ modules across 5 layers (from ADR-0004):**
- **Layer 1:** 4 modules (Input Processing)
- **Layer 2:** 3 modules (Orchestration)
- **Layer 3:** 22 modules (Execution)
- **Layer 4:** 8 modules (Runtime Core)
- **Layer 5:** 19 modules (Infrastructure)

**Problem:**
- **Unit tests alone insufficient:** Don't validate cross-module integration
- **No layer contract validation:** Can't verify layering rules enforced at runtime
- **Performance blind spots:** No P95 latency validation per layer
- **Hard to isolate failures:** If end-to-end test fails, which layer broke?

**Example Failure Scenario:**
```
End-to-end test fails: "User input → Agent response takes 3500ms (budget: 2000ms)"

Without per-layer tests:
  - Is Layer 1 slow? (intent classification)
  - Is Layer 2 slow? (orchestration)
  - Is Layer 3 slow? (agent execution)
  - Unknown, must debug entire stack

With per-layer tests:
  - Layer 1 test: PASS (50ms, budget: 150ms)
  - Layer 2 test: PASS (200ms, budget: 250ms)
  - Layer 3 test: FAIL (3200ms, budget: 3000ms) ← Isolated!
  - Layer 4 test: PASS (1ms, budget: 10ms)
  - Layer 5 test: PASS (5ms, budget: 10ms)

  Conclusion: Layer 3 (agent execution) is the bottleneck
```

**Requirement:**
- Per-layer integration test suites
- Contract validation (layering rules, API contracts)
- Performance validation (P95 latency per layer)
- Fast feedback (<5min to run all integration tests)

---

## Decision

We adopt **per-layer integration test suites** with layer-specific scenarios and performance validation using WARD framework.

**Architecture:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                    Integration Test Organization                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  tests/integration/                                                     │
│  ├── layer1/  (Input Processing)                                       │
│  │   ├── test_event_publish.py         # L1 → L5 event publishing     │
│  │   ├── test_intent_classification.py # 3-tier intent routing        │
│  │   └── test_stream_processing.py     # Multi-modal input handling   │
│  │                                                                      │
│  ├── layer2/  (Orchestration)                                          │
│  │   ├── test_3phase_orchestration.py  # Negotiation→Selection→Exec   │
│  │   ├── test_planning_pipeline.py     # 4-stage planner              │
│  │   └── test_protocol_validation.py   # MPST contract enforcement    │
│  │                                                                      │
│  ├── layer3/  (Execution)                                              │
│  │   ├── test_agent_lifecycle.py       # Hire → Warm → Active → Term  │
│  │   ├── test_tool_execution.py        # Tool call + sandbox          │
│  │   └── test_model_hub.py             # LLM routing + fallback       │
│  │                                                                      │
│  ├── layer4/  (Runtime Core)                                           │
│  │   ├── test_session_state.py         # State serialize/deserialize  │
│  │   ├── test_learning_loop.py         # Feedback → Drift detection   │
│  │   └── test_saga_rollback.py         # Saga pattern error recovery  │
│  │                                                                      │
│  ├── layer5/  (Infrastructure)                                         │
│  │   ├── test_event_bus.py             # Pub/sub delivery             │
│  │   ├── test_backpressure.py          # Cascade back-pressure        │
│  │   └── test_thermal_placement.py     # NPU/GPU/CPU placement        │
│  │                                                                      │
│  └── end_to_end/  (Full Stack)                                         │
│      ├── test_user_turn.py             # User input → Agent response  │
│      ├── test_barge_in.py              # Voice interrupt handling     │
│      └── test_multi_agent.py           # Multi-agent collaboration    │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Design

### Layer 1 Integration Tests (Input Processing)

**Directory:** `tests/integration/layer1/`

**Purpose:** Validate Layer 1 modules interact correctly (event publishing, intent routing, stream processing).

#### Test 1: Event Publishing (L1 → L5)

**File:** `tests/integration/layer1/test_event_publish.py`

```python
"""
Integration Test: Layer 1 → Layer 5 Event Publishing
Validates IntentRouter publishes events to event bus (Layer 5)
"""

from ward import test, fixture
import asyncio
import time

@fixture
async def event_bus():
    """Fixture: Layer 5 event bus"""
    from k1.infrastructure.event_bus import event_bus
    await event_bus.start()
    yield event_bus
    await event_bus.stop()

@fixture
async def intent_router():
    """Fixture: Layer 1 intent router"""
    from k1.input.intent_router import IntentRouter
    return IntentRouter()

@test("Layer 1 publishes IntentDetected event to Layer 5")
async def _(router=intent_router, bus=event_bus):
    """
    Scenario:
    1. IntentRouter (L1) classifies user input
    2. IntentRouter publishes IntentDetected event to event bus (L5)
    3. Event bus delivers event to subscribers (L2)

    Contract Validation:
    - L1 imports L5 (event_bus) ✅ ALLOWED
    - Event published with cognitive_trace_id
    - Event delivered within <10ms P95
    """

    # Arrange: Subscribe to IntentDetected events
    events_received = []
    def handler(event):
        events_received.append(event)

    from k1.infrastructure.event_bus import EventTopic
    bus.subscribe(EventTopic.INTENT_DETECTED, handler)

    # Act: Classify intent (L1 → L5 event publish)
    start_time = time.time()
    await router.classify_intent(
        user_input="What's the weather?",
        session_id="session_123",
        trace_id="trace_456",
    )

    # Wait for event delivery
    await asyncio.sleep(0.05)  # 50ms max delivery time

    # Assert: Event received
    assert len(events_received) == 1, "IntentDetected event not received"

    event = events_received[0]
    assert event.topic == EventTopic.INTENT_DETECTED
    assert event.session_id == "session_123"
    assert event.cognitive_trace_id == "trace_456"
    assert event.payload["intent"] == "weather_query"
    assert event.payload["confidence"] > 0.8

    # Performance: <10ms end-to-end (L1 → L5 → L2)
    latency_ms = (time.time() - start_time) * 1000
    assert latency_ms < 10, f"Event delivery too slow: {latency_ms}ms (budget: 10ms)"
```

#### Test 2: Intent Classification (3-Tier Cascade)

**File:** `tests/integration/layer1/test_intent_classification.py`

```python
"""
Integration Test: 3-Tier Intent Classification
Validates regex → SLM → LLM cascade works correctly
"""

from ward import test, fixture
import time

@fixture
async def intent_router():
    from k1.input.intent_router import IntentRouter
    return IntentRouter()

@test("Tier 1 (regex) classifies simple intent <1ms")
async def _(router=intent_router):
    """Regex patterns for common intents (40% coverage)"""

    start_time = time.time()
    intent = await router.classify_intent(
        user_input="stop",  # Simple command
        session_id="session_123",
        trace_id="trace_456",
    )
    latency_ms = (time.time() - start_time) * 1000

    assert intent == "stop_command"
    assert latency_ms < 1, f"Tier 1 too slow: {latency_ms}ms (budget: 1ms)"

@test("Tier 2 (SLM) classifies medium intent <5ms")
async def _(router=intent_router):
    """SLM for moderate complexity (50% coverage)"""

    start_time = time.time()
    intent = await router.classify_intent(
        user_input="What's the weather in San Francisco?",
        session_id="session_123",
        trace_id="trace_456",
    )
    latency_ms = (time.time() - start_time) * 1000

    assert intent == "weather_query"
    assert latency_ms < 5, f"Tier 2 too slow: {latency_ms}ms (budget: 5ms)"

@test("Tier 3 (LLM) classifies complex intent <50ms")
async def _(router=intent_router):
    """LLM for complex/ambiguous intents (95% coverage)"""

    start_time = time.time()
    intent = await router.classify_intent(
        user_input="Can you help me figure out why my code isn't working?",
        session_id="session_123",
        trace_id="trace_456",
    )
    latency_ms = (time.time() - start_time) * 1000

    assert intent == "code_debugging"
    assert latency_ms < 50, f"Tier 3 too slow: {latency_ms}ms (budget: 50ms)"
```

---

### Layer 2 Integration Tests (Orchestration)

**Directory:** `tests/integration/layer2/`

**Purpose:** Validate Layer 2 orchestration (3-phase coordination, planning, protocol validation).

#### Test 1: 3-Phase Orchestration

**File:** `tests/integration/layer2/test_3phase_orchestration.py`

```python
"""
Integration Test: 3-Phase Orchestration (Contract Net Protocol)
Validates Negotiation → Selection → Execution pipeline
"""

from ward import test, fixture
import time

@fixture
async def orchestrator():
    from k1.orchestration.orchestrator import Orchestrator
    orch = Orchestrator()
    await orch.initialize()
    yield orch
    await orch.shutdown()

@test("3-phase orchestration completes within 250ms P95")
async def _(orch=orchestrator):
    """
    Scenario:
    1. Orchestrator receives IntentDetected event (from L1 via L5)
    2. Phase 1 (Negotiation): Broadcast task to agents, collect proposals
    3. Phase 2 (Selection): Select best agent based on score
    4. Phase 3 (Execution): Execute task with selected agent

    Performance Budget: <250ms P95 (excluding LLM planning)
    """

    # Arrange: Create task
    from k1.orchestration.orchestrator import TaskAnnouncement
    task = TaskAnnouncement(
        task_id="task_001",
        intent="weather_query",
        session_id="session_123",
        trace_id="trace_456",
    )

    # Act: 3-phase orchestration
    start_time = time.time()
    result = await orch.coordinate(task)
    latency_ms = (time.time() - start_time) * 1000

    # Assert: Task completed
    assert result.status == "COMPLETED"
    assert result.selected_agent_id is not None

    # Performance: <250ms P95
    assert latency_ms < 250, f"Orchestration too slow: {latency_ms}ms (budget: 250ms)"
```

#### Test 2: 4-Stage Planning Pipeline

**File:** `tests/integration/layer2/test_planning_pipeline.py`

```python
"""
Integration Test: 4-Stage Planning Pipeline
Validates Sketch → Expand → Validate → Commit stages
"""

from ward import test, fixture

@fixture
async def planner():
    from k1.orchestration.planner import Planner
    planner = Planner()
    await planner.initialize()
    yield planner
    await planner.shutdown()

@test("4-stage planning generates valid plan within 5000ms")
async def _(planner=planner):
    """
    Scenario:
    1. Sketch (LLM): Generate high-level plan steps
    2. Expand (deterministic): Fill in tool calls, parameters
    3. Validate (rules + arbiter): Check safety, feasibility
    4. Commit (store): Persist validated plan

    Performance Budget: <5000ms P95 (includes LLM call)
    """

    import time
    start_time = time.time()

    plan = await planner.generate_plan(
        intent="weather_query",
        session_id="session_123",
        trace_id="trace_456",
    )

    latency_ms = (time.time() - start_time) * 1000

    # Assert: Plan valid
    assert plan.status == "COMMITTED"
    assert len(plan.steps) > 0
    assert plan.steps[0].tool_name == "weather_api"

    # Performance: <5000ms P95
    assert latency_ms < 5000, f"Planning too slow: {latency_ms}ms (budget: 5000ms)"
```

---

### Layer 3 Integration Tests (Execution)

**Directory:** `tests/integration/layer3/`

**Purpose:** Validate Layer 3 execution (agent lifecycle, tool execution, Model Hub).

#### Test 1: Agent Lifecycle FSM

**File:** `tests/integration/layer3/test_agent_lifecycle.py`

```python
"""
Integration Test: Agent Lifecycle FSM
Validates PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED transitions
"""

from ward import test, fixture
import asyncio
import time

@fixture
async def agent_supervisor():
    from k1.execution.agent_supervisor import AgentSupervisor
    supervisor = AgentSupervisor()
    await supervisor.initialize()
    yield supervisor
    await supervisor.shutdown()

@test("Agent lifecycle: Hire → Warm → Execute → Terminate within 600ms")
async def _(supervisor=agent_supervisor):
    """
    Scenario:
    1. Hire agent (PENDING → WARMING)
    2. Warm agent (load model, <200ms budget)
    3. Transition to ACTIVE
    4. Execute task
    5. Transition to IDLE (no tasks)
    6. Drain agent (DRAINING)
    7. Terminate agent (TERMINATED)

    Performance Budget: <600ms for hire (PENDING → ACTIVE)
    """

    # Act: Hire agent
    start_time = time.time()
    agent_id = await supervisor.hire_agent(
        capabilities=["TOOL_CALL", "MEMORY_READ"],
        session_id="session_123",
        trace_id="trace_456",
    )
    hire_latency_ms = (time.time() - start_time) * 1000

    # Assert: Agent hired and warmed
    agent = await supervisor.get_agent(agent_id)
    assert agent.state == "ACTIVE"

    # Performance: <600ms for hire
    assert hire_latency_ms < 600, f"Agent hire too slow: {hire_latency_ms}ms (budget: 600ms)"

    # Act: Execute task
    result = await supervisor.execute_task(
        agent_id=agent_id,
        task_id="task_001",
        trace_id="trace_456",
    )
    assert result.status == "COMPLETED"

    # Act: Terminate agent
    await supervisor.terminate_agent(agent_id, trace_id="trace_456")
    agent = await supervisor.get_agent(agent_id)
    assert agent.state == "TERMINATED"
```

---

### Layer 4 Integration Tests (Runtime Core)

**Directory:** `tests/integration/layer4/`

**Purpose:** Validate Layer 4 runtime (session state, learning loop, saga rollback).

#### Test 1: SessionState Serialization

**File:** `tests/integration/layer4/test_session_state.py`

```python
"""
Integration Test: SessionState Serialization (FlatBuffers)
Validates serialize → deserialize round-trip <1ms
"""

from ward import test, fixture
import time

@fixture
def session_state():
    from k1.runtime.session_state import SessionState
    return SessionState(session_id="session_123")

@test("SessionState serialize/deserialize within 1ms")
def _(state=session_state):
    """
    Scenario:
    1. Create SessionState with 6 sections (beliefs, scoreboard, control, persona, multimodal, meta)
    2. Serialize to FlatBuffers (<1ms)
    3. Deserialize from FlatBuffers (<1ms)
    4. Verify data integrity (no corruption)

    Performance Budget: <1ms for serialize + deserialize
    """

    # Arrange: Populate state
    state.beliefs["user_name"] = "Alice"
    state.scoreboard["task_completed"] = True

    # Act: Serialize
    start_time = time.time()
    serialized = state.serialize()
    serialize_latency_ms = (time.time() - start_time) * 1000

    # Act: Deserialize
    start_time = time.time()
    from k1.runtime.session_state import SessionState
    deserialized = SessionState.deserialize(serialized)
    deserialize_latency_ms = (time.time() - start_time) * 1000

    # Assert: Data integrity
    assert deserialized.beliefs["user_name"] == "Alice"
    assert deserialized.scoreboard["task_completed"] is True

    # Performance: <1ms total
    total_latency_ms = serialize_latency_ms + deserialize_latency_ms
    assert total_latency_ms < 1, f"Serialization too slow: {total_latency_ms}ms (budget: 1ms)"
```

---

### Layer 5 Integration Tests (Infrastructure)

**Directory:** `tests/integration/layer5/`

**Purpose:** Validate Layer 5 infrastructure (event bus, backpressure, thermal placement).

#### Test 1: Event Bus Delivery

**File:** `tests/integration/layer5/test_event_bus.py`

```python
"""
Integration Test: Event Bus Pub/Sub Delivery
Validates event publish → delivery <5ms P95
"""

from ward import test, fixture
import asyncio
import time

@fixture
async def event_bus():
    from k1.infrastructure.event_bus import event_bus
    await event_bus.start()
    yield event_bus
    await event_bus.stop()

@test("Event bus delivers event within 5ms P95")
async def _(bus=event_bus):
    """
    Scenario:
    1. Publisher publishes event to topic
    2. Event bus routes event to subscribers
    3. Subscriber receives event (<5ms P95)

    Performance Budget: <5ms P95 delivery latency
    """

    # Arrange: Subscribe to topic
    events_received = []
    async def handler(event):
        events_received.append(event)

    from k1.infrastructure.event_bus import Event, EventTopic
    bus.subscribe(EventTopic.USER_INPUT, handler)

    # Act: Publish event
    start_time = time.time()
    event = Event(
        topic=EventTopic.USER_INPUT,
        session_id="session_123",
        payload={"text": "Hello"},
        cognitive_trace_id="trace_456",
        timestamp=time.time(),
    )
    await bus.publish(event)

    # Wait for delivery
    await asyncio.sleep(0.01)  # 10ms max

    delivery_latency_ms = (time.time() - start_time) * 1000

    # Assert: Event delivered
    assert len(events_received) == 1
    assert events_received[0].payload["text"] == "Hello"

    # Performance: <5ms P95
    assert delivery_latency_ms < 5, f"Event delivery too slow: {delivery_latency_ms}ms (budget: 5ms)"
```

---

## End-to-End Integration Tests

**Directory:** `tests/integration/end_to_end/`

**Purpose:** Validate full-stack integration (L1 → L2 → L3 → L4 → L5).

### Test 1: User Turn (End-to-End)

**File:** `tests/integration/end_to_end/test_user_turn.py`

```python
"""
End-to-End Integration Test: User Turn
Validates user input → agent response (<2000ms P95)
"""

from ward import test, fixture
import time

@fixture
async def k1_kernel():
    """Fixture: Full K1 kernel"""
    from k1.kernel import K1Kernel
    kernel = K1Kernel()
    await kernel.initialize()
    yield kernel
    await kernel.shutdown()

@test("User turn completes within 2000ms P95")
async def _(kernel=k1_kernel):
    """
    Scenario:
    1. User input (text) → Layer 1 (stream processing)
    2. Intent classification (Layer 1) → Event publish (Layer 5)
    3. Orchestration triggered (Layer 2) → Planning + agent hire
    4. Agent execution (Layer 3) → Tool call
    5. Response generation → Layer 1 (TTS if voice)
    6. Return response to user

    Performance Budget: <2000ms P95 end-to-end
    """

    start_time = time.time()

    response = await kernel.process_turn(
        user_input="What's the weather in San Francisco?",
        session_id="session_123",
        trace_id="trace_456",
    )

    latency_ms = (time.time() - start_time) * 1000

    # Assert: Response received
    assert response.text.startswith("The weather in San Francisco")
    assert response.status == "COMPLETED"

    # Performance: <2000ms P95
    assert latency_ms < 2000, f"User turn too slow: {latency_ms}ms (budget: 2000ms)"
```

---

## Consequences

### Positive ✅

**✅ Fast Failure Isolation:**
- Per-layer tests identify which layer broke
- No need to debug entire stack
- **Result:** Faster bug fixes, less downtime

**✅ Performance Validation:**
- Each layer has P95 latency budget
- Tests assert budgets met
- **Result:** No performance regressions

**✅ Contract Enforcement:**
- Tests validate layering rules (no forbidden imports)
- Tests validate API contracts (correct behavior)
- **Result:** Architecture integrity preserved

**✅ Fast Feedback (<5min):**
- Per-layer tests run in parallel
- Total integration test time: <5min
- **Result:** Developer-friendly, CI-friendly

---

### Negative ⚠️

**⚠️ Test Maintenance Overhead:**
- 5 layer test directories + end-to-end tests
- Must update tests when architecture changes
- **Mitigation:** Auto-generate test stubs from module READMEs
- **Risk Level:** MEDIUM (manageable with tooling)

**⚠️ Test Flakiness (Timing):**
- Performance tests depend on system load
- CI runners may be slower than local machines
- **Mitigation:** Use P95 budgets (not P50), retry flaky tests
- **Risk Level:** LOW (standard practice)

---

## Implementation Notes

### **Implementation Timeline**

**Phase 1 (Week 1): Layer 1-2 Tests**
- Create `tests/integration/layer1/` and `tests/integration/layer2/`
- Implement event publish, intent classification, orchestration tests
- Validate <10ms event delivery, <250ms orchestration

**Phase 2 (Week 2): Layer 3-4 Tests**
- Create `tests/integration/layer3/` and `tests/integration/layer4/`
- Implement agent lifecycle, tool execution, session state tests
- Validate <600ms agent hire, <1ms state serialization

**Phase 3 (Week 3): Layer 5 + End-to-End Tests**
- Create `tests/integration/layer5/` and `tests/integration/end_to_end/`
- Implement event bus, backpressure, user turn tests
- Validate <5ms event delivery, <2000ms user turn

**Phase 4 (Week 4): CI Integration**
- Add integration tests to `.github/workflows/test.yml`
- Run per-layer tests in parallel (reduce CI time)
- Monitor flaky tests, adjust budgets if needed

---

### **Success Metrics**

**Coverage:**
- ✅ All 5 layers have integration test suites
- ✅ All inter-layer contracts tested
- ✅ All performance budgets validated

**Performance:**
- ✅ Integration test suite: <5min total
- ✅ Per-layer tests: <1min each (parallelizable)

**Quality:**
- ✅ Zero performance regressions (CI catches budget violations)
- ✅ Fast failure isolation (<5min to identify broken layer)

---

## References

### **Related ADRs**

- [ADR-0004: 52-Module 5-Layer Architecture](0004-52-module-5-layer-architecture.md) — Parent ADR
- [ADR-0004a: Layer 1-2 Event Bus Communication](0004a-layer1-2-event-bus-communication.md)
- [ADR-0004b: Module Dependency Management](0004b-module-dependency-management.md)

---

**Document Status:** ✅ **COMPLETE** - Per-layer integration testing strategy fully specified with test organization, layer-specific scenarios, performance validation, and end-to-end tests.

**Cross-References:**
- ADR-0004 (Parent): 52-Module 5-Layer Architecture
- All 5 layers (L1-L5) have dedicated test suites

**Canonical Values:**
- **Layer 1 budgets:** Event publish <2ms, intent classification <50ms
- **Layer 2 budgets:** Orchestration <250ms, planning <5000ms
- **Layer 3 budgets:** Agent hire <600ms, tool call <3000ms
- **Layer 4 budgets:** SessionState serialization <1ms, learning update <100ms
- **Layer 5 budgets:** Event bus delivery <5ms, metrics export <10ms
- **End-to-end budget:** User turn <2000ms P95

**Document End**
