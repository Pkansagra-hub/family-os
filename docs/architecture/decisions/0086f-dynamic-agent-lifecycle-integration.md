# ADR-0086f: Dynamic Agent Lifecycle Integration

**Status:** Approved ✅ - Implementation Phase M2
**Decision Date:** 2025-10-23
**Implementation Date:** TBD (M2 - Post-M1)
**Review Date:** TBD (Post-implementation)
**Last Updated:** 2025-10-23
**Authors:** K1 Architecture Team
**Category:** Agent Lifecycle & State Management
**Parent ADR:** [ADR-0086 (Dynamic Agent Creation Subsystem)](0086-dynamic-agent-creation-subsystem.md)
**Related ADRs:**

- [ADR-0086a (Agent Factory)](0086a-agent-factory-pattern.md) - Factory creates agents
- [ADR-0005 (Agent Fabric Lifecycle)](0005-agent-fabric-lifecycle-fsm.md) - 6-state FSM (PENDING → TERMINATED)
- [ADR-0005b (Hire/Fire Manager)](0005b-agent-hire-fire-manager.md) - Agent hiring/firing orchestration
- [ADR-0005c (Supervisor)](0005c-supervisor-agent-state-transitions.md) - State transition enforcement
- [ADR-0086c (Resource Reservation)](0086c-resource-reservation-system.md) - Resource cleanup on termination

---

## Context

### Problem Statement

Dynamic agents created by AgentFactory need **full lifecycle integration** with existing Agent Fabric:

**Current State (Static Agents):**

```python
# Static agents (concierge, planner, researcher, safety_watch)
# Lifecycle managed by hire_fire/ module:

1. PENDING → hire_fire.hire() → WARMING
2. WARMING → supervisor checks → ACTIVE
3. ACTIVE → task completion → IDLE (reused for next task)
4. IDLE (60s timeout) → supervisor → DRAINING
5. DRAINING → hire_fire.fire() → TERMINATED
```

**Problems with Dynamic Agents:**

- ❌ **No IDLE pooling:** Task-specific agents (health_specialist) created fresh every time
- ❌ **Resource waste:** Recreate agent for "what's my health metrics?" asked 3x in 5 minutes
- ❌ **No termination policy:** When to terminate task-specific agents?
- ❌ **Factory isolation:** AgentFactory bypasses hire_fire/, breaks lifecycle guarantees

**Example Inefficiency:**

```text
10:00 AM: User asks "what's my health metrics?"
          → Factory creates health_specialist agent
          → Agent processes request
          → Agent terminated (no pooling)

10:02 AM: User asks "show me my step count"
          → Factory creates NEW health_specialist agent (wasteful!)
          → Agent processes request
          → Agent terminated

10:05 AM: User asks "compare my activity to last week"
          → Factory creates ANOTHER health_specialist agent
          → 3 identical agents created in 5 minutes!
```

### Desired State (M2 Goal)

**Integrated Lifecycle with IDLE Pooling:**

```python
# Dynamic agents with IDLE pooling

10:00 AM: User asks "what's my health metrics?"
          → Factory.create(agent_type="health_specialist")
          → hire_fire.hire(agent) → WARMING → ACTIVE
          → Agent processes request → IDLE (pooled)

10:02 AM: User asks "show me my step count"
          → Factory checks IDLE pool → health_specialist found!
          → hire_fire.reactivate(agent) → ACTIVE (reused, <10ms)
          → Agent processes request → IDLE (pooled again)

10:05 AM: User asks "compare my activity to last week"
          → Factory checks IDLE pool → health_specialist found!
          → Agent processes request → IDLE

11:00 AM: 60s timeout expires (no requests)
          → supervisor detects IDLE timeout
          → hire_fire.fire(agent) → DRAINING → TERMINATED
```

**Benefits:**

- ✅ **3x reduction in agent creation** (reuse IDLE agents)
- ✅ **<10ms reactivation** vs 100ms creation
- ✅ **Automatic cleanup** (60s timeout for task-specific agents)
- ✅ **Lifecycle guarantees preserved** (FSM enforced by supervisor)

---

## Decision

We will integrate AgentFactory with hire_fire/ module for full lifecycle management:

### 1. Factory ↔ hire_fire Integration

```python
# k1/l3_execution/agents/factory.py (enhanced)

from k1.l4_runtime.agents.hire_fire import HireFireManager
from k1.l4_runtime.agents.active_roster import ActiveRoster

class AgentFactory:
    """
    Agent factory with lifecycle integration.

    M2 Changes:
    - Check IDLE pool before creating new agents
    - Delegate to hire_fire for PENDING → ACTIVE transitions
    - Register termination callbacks for resource cleanup
    """

    def __init__(
        self,
        template_loader: TemplateLoader,
        resource_reserver: ResourceReserver,
        composition_engine: CompositionEngine,
        hire_fire_manager: HireFireManager,    # NEW: M2 integration
        active_roster: ActiveRoster,           # NEW: IDLE pool access
        trace_id: str = ""
    ):
        self.template_loader = template_loader
        self.resource_reserver = resource_reserver
        self.composition_engine = composition_engine
        self.hire_fire_manager = hire_fire_manager
        self.active_roster = active_roster
        self.trace_id = trace_id

        # Agent registry (agent_id → Agent)
        self._agents: Dict[str, Agent] = {}

        # Metrics
        self._init_metrics()

    async def create_or_reuse(
        self,
        session_id: str,
        agent_type: str,
        capabilities: List[str],
        trace_id: str
    ) -> Agent:
        """
        Create new agent OR reuse IDLE agent (M2 optimization).

        Flow:
        1. Check IDLE pool for matching agent_type
        2. If found → reactivate (IDLE → ACTIVE, <10ms)
        3. If not → create new agent via hire_fire

        Performance:
        - Reactivation: <10ms P95 (IDLE → ACTIVE)
        - Creation: <100ms P95 (PENDING → ACTIVE)

        Args:
            session_id: Session ID for agent ownership
            agent_type: Agent type (e.g., "health_specialist")
            capabilities: Bound capabilities
            trace_id: Trace ID

        Returns:
            Agent: Reused IDLE agent OR newly created agent
        """
        start_time = time.perf_counter()

        # Step 1: Check IDLE pool (M2 optimization)
        idle_agent = await self._find_idle_agent(
            session_id=session_id,
            agent_type=agent_type,
            trace_id=trace_id
        )

        if idle_agent:
            # Reuse IDLE agent (fast path)
            reactivated = await self.hire_fire_manager.reactivate(
                agent=idle_agent,
                trace_id=trace_id
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            self._metrics_agent_reused.labels(agent_type=agent_type).inc()
            self._metrics_reactivation_latency.labels(agent_type=agent_type).observe(latency_ms)

            logger.info(
                "agent_reused_from_idle_pool",
                agent_id=idle_agent.agent_id,
                agent_type=agent_type,
                session_id=session_id,
                latency_ms=latency_ms,
                trace_id=trace_id
            )

            return reactivated

        # Step 2: No IDLE agent → create new agent (slow path)
        self._metrics_agent_created.labels(agent_type=agent_type).inc()

        # Generate agent ID
        agent_id = self._generate_agent_id(session_id)

        # Load template
        template = await self.template_loader.load(
            agent_type=agent_type,
            trace_id=trace_id
        )

        # Reserve resources
        reservation = await self.resource_reserver.reserve(
            agent_id=agent_id,
            memory_mb=template.lifecycle.get("memory_mb", 128),
            accelerator=template.lifecycle.get("accelerator", "CPU"),
            timeout_ms=30000,
            trace_id=trace_id
        )

        # Compose agent
        composed = await self.composition_engine.compose(
            agent_id=agent_id,
            agent_type=agent_type,
            template=template,
            capabilities=capabilities,
            trace_id=trace_id
        )

        # Create Agent instance (PENDING state)
        agent = Agent(
            agent_id=agent_id,
            agent_type=agent_type,
            session_id=session_id,
            state=AgentState.PENDING,
            composed_config=composed,
            reservation=reservation,
            created_at=time.time()
        )

        # Register agent
        self._agents[agent_id] = agent

        # Step 3: Hire via hire_fire (PENDING → ACTIVE)
        hired_agent = await self.hire_fire_manager.hire(
            agent=agent,
            trace_id=trace_id
        )

        # Register termination callback (resource cleanup)
        self._register_termination_callback(agent)

        latency_ms = (time.perf_counter() - start_time) * 1000
        self._metrics_creation_latency.labels(agent_type=agent_type).observe(latency_ms)

        logger.info(
            "agent_created_and_hired",
            agent_id=agent_id,
            agent_type=agent_type,
            session_id=session_id,
            state=hired_agent.state.value,
            latency_ms=latency_ms,
            trace_id=trace_id
        )

        return hired_agent

    async def _find_idle_agent(
        self,
        session_id: str,
        agent_type: str,
        trace_id: str
    ) -> Optional[Agent]:
        """
        Find IDLE agent in active roster.

        Criteria:
        - Same session_id (session-scoped pooling)
        - Same agent_type
        - State = IDLE
        - IDLE duration < 60s (before timeout)

        Returns:
            Optional[Agent]: IDLE agent if found, else None
        """
        idle_agents = self.active_roster.get_agents_by_state(
            state=AgentState.IDLE,
            session_id=session_id
        )

        for agent in idle_agents:
            if agent.agent_type == agent_type:
                idle_duration_s = time.time() - agent.last_state_change

                if idle_duration_s < 60:  # Before timeout
                    logger.debug(
                        "idle_agent_found",
                        agent_id=agent.agent_id,
                        agent_type=agent_type,
                        idle_duration_s=idle_duration_s,
                        trace_id=trace_id
                    )
                    return agent

        return None

    def _register_termination_callback(self, agent: Agent):
        """
        Register callback for resource cleanup on termination.

        Callback invoked when agent reaches TERMINATED state:
        1. Release resources (memory, accelerator slots)
        2. Remove from factory registry
        3. Emit metrics
        """
        async def on_terminate():
            # Release resources
            await self.resource_reserver.release(
                agent_id=agent.agent_id,
                trace_id=self.trace_id
            )

            # Remove from registry
            self._agents.pop(agent.agent_id, None)

            logger.info(
                "agent_terminated_cleanup",
                agent_id=agent.agent_id,
                agent_type=agent.agent_type,
                trace_id=self.trace_id
            )

        # Register with hire_fire manager
        self.hire_fire_manager.register_termination_callback(
            agent_id=agent.agent_id,
            callback=on_terminate
        )
```

### 2. IDLE Pool Configuration

```yaml
# k1/config/agent_fabric.yml

agent_fabric:
  idle_pooling:
    # Enable IDLE pooling for task-specific agents
    enabled: true

    # Agent types eligible for pooling
    poolable_types:
      - health_specialist
      - code_assistant
      - finance_advisor
      - travel_planner
      - recipe_assistant
      - fitness_coach

    # Non-poolable types (always create fresh)
    non_poolable_types:
      - concierge      # Persistent (never terminates)
      - planner        # Persistent
      - researcher     # Persistent
      - safety_watch   # Persistent

    # IDLE timeout (before termination)
    idle_timeout_ms: 60000  # 60 seconds

    # Max IDLE agents per session
    max_idle_per_session: 3

    # Pool eviction policy
    eviction_policy: "LRU"  # Least Recently Used
```

### 3. Termination Policies

```python
# k1/l4_runtime/agents/hire_fire/termination_policy.py

from enum import Enum
from dataclasses import dataclass
from typing import Callable

class TerminationReason(Enum):
    """Reason for agent termination"""
    IDLE_TIMEOUT = "IDLE_TIMEOUT"           # 60s with no tasks
    SESSION_END = "SESSION_END"             # User session ended
    RESOURCE_PRESSURE = "RESOURCE_PRESSURE" # Memory/accelerator shortage
    CRASH = "CRASH"                         # Agent crashed/blacklisted
    MANUAL = "MANUAL"                       # Explicit fire() call


@dataclass
class TerminationPolicy:
    """
    Termination policy for agent types.

    Defines when agents should be terminated based on:
    - Agent type (task-specific vs persistent)
    - IDLE duration
    - Resource pressure
    - Session lifecycle
    """
    agent_type: str

    # IDLE timeout (None = never terminate on IDLE)
    idle_timeout_ms: Optional[int]

    # Terminate on session end?
    terminate_on_session_end: bool

    # Allow resource-pressure termination?
    allow_resource_pressure_termination: bool

    # Custom termination callback
    on_terminate: Optional[Callable] = None


# Built-in policies
TERMINATION_POLICIES = {
    # Persistent agents (never auto-terminate)
    "concierge": TerminationPolicy(
        agent_type="concierge",
        idle_timeout_ms=None,  # Never timeout
        terminate_on_session_end=False,
        allow_resource_pressure_termination=False
    ),

    "planner": TerminationPolicy(
        agent_type="planner",
        idle_timeout_ms=None,
        terminate_on_session_end=False,
        allow_resource_pressure_termination=False
    ),

    "researcher": TerminationPolicy(
        agent_type="researcher",
        idle_timeout_ms=None,
        terminate_on_session_end=False,
        allow_resource_pressure_termination=False
    ),

    "safety_watch": TerminationPolicy(
        agent_type="safety_watch",
        idle_timeout_ms=None,
        terminate_on_session_end=False,
        allow_resource_pressure_termination=False
    ),

    # Task-specific agents (auto-terminate on IDLE)
    "health_specialist": TerminationPolicy(
        agent_type="health_specialist",
        idle_timeout_ms=60000,  # 60s timeout
        terminate_on_session_end=True,
        allow_resource_pressure_termination=True
    ),

    "code_assistant": TerminationPolicy(
        agent_type="code_assistant",
        idle_timeout_ms=120000,  # 2 min timeout (longer for coding)
        terminate_on_session_end=True,
        allow_resource_pressure_termination=True
    ),

    "finance_advisor": TerminationPolicy(
        agent_type="finance_advisor",
        idle_timeout_ms=60000,
        terminate_on_session_end=True,
        allow_resource_pressure_termination=True
    ),

    # Default for unknown types
    "default": TerminationPolicy(
        agent_type="default",
        idle_timeout_ms=60000,
        terminate_on_session_end=True,
        allow_resource_pressure_termination=True
    )
}


class TerminationPolicyManager:
    """
    Manages termination policies for all agent types.

    Responsibilities:
    1. Get termination policy for agent type
    2. Evaluate termination conditions
    3. Invoke termination callbacks
    """

    def __init__(self, policies: Dict[str, TerminationPolicy]):
        self.policies = policies

    def get_policy(self, agent_type: str) -> TerminationPolicy:
        """Get termination policy (fallback to default)"""
        return self.policies.get(agent_type, self.policies["default"])

    def should_terminate(
        self,
        agent: Agent,
        reason: TerminationReason
    ) -> bool:
        """
        Evaluate if agent should be terminated.

        Args:
            agent: Agent instance
            reason: Termination reason

        Returns:
            bool: True if agent should be terminated
        """
        policy = self.get_policy(agent.agent_type)

        if reason == TerminationReason.IDLE_TIMEOUT:
            if policy.idle_timeout_ms is None:
                return False  # Never timeout

            idle_duration_ms = (time.time() - agent.last_state_change) * 1000
            return idle_duration_ms >= policy.idle_timeout_ms

        elif reason == TerminationReason.SESSION_END:
            return policy.terminate_on_session_end

        elif reason == TerminationReason.RESOURCE_PRESSURE:
            return policy.allow_resource_pressure_termination

        elif reason == TerminationReason.CRASH:
            return True  # Always terminate crashed agents

        elif reason == TerminationReason.MANUAL:
            return True  # Always respect manual fire()

        return False
```

### 4. Supervisor Integration

```python
# k1/l4_runtime/agents/supervisor/__init__.py (enhanced)

class Supervisor:
    """
    Supervisor with M2 termination policy enforcement.

    New Responsibilities:
    - Check IDLE timeouts (every 5s)
    - Evaluate termination policies
    - Invoke hire_fire.fire() for expired agents
    """

    def __init__(
        self,
        active_roster: ActiveRoster,
        hire_fire_manager: HireFireManager,
        termination_policy_manager: TerminationPolicyManager
    ):
        self.active_roster = active_roster
        self.hire_fire_manager = hire_fire_manager
        self.termination_policy_manager = termination_policy_manager

        # Start background task
        self._running = False

    async def start(self):
        """Start supervisor background task"""
        self._running = True
        asyncio.create_task(self._check_idle_timeouts())

    async def _check_idle_timeouts(self):
        """
        Check IDLE agents for timeout expiration (every 5s).

        Flow:
        1. Get all IDLE agents
        2. For each agent, check termination policy
        3. If timeout expired → fire(agent)
        """
        while self._running:
            try:
                idle_agents = self.active_roster.get_agents_by_state(
                    state=AgentState.IDLE
                )

                for agent in idle_agents:
                    # Check termination policy
                    should_terminate = self.termination_policy_manager.should_terminate(
                        agent=agent,
                        reason=TerminationReason.IDLE_TIMEOUT
                    )

                    if should_terminate:
                        logger.info(
                            "idle_timeout_firing_agent",
                            agent_id=agent.agent_id,
                            agent_type=agent.agent_type,
                            idle_duration_s=(time.time() - agent.last_state_change)
                        )

                        # Fire agent (IDLE → DRAINING → TERMINATED)
                        await self.hire_fire_manager.fire(
                            agent=agent,
                            reason=TerminationReason.IDLE_TIMEOUT
                        )

            except Exception as e:
                logger.error("supervisor_idle_check_error", error=str(e))

            # Check every 5 seconds
            await asyncio.sleep(5)
```

---

## Performance Budgets

| Metric | Budget | Rationale |
|--------|--------|-----------|
| **Agent reactivation (IDLE → ACTIVE)** | <10ms P95 | State change only, no creation overhead |
| **IDLE pool lookup** | <1ms | Hash table lookup in active roster |
| **Termination callback execution** | <20ms | Resource release + registry cleanup |
| **Supervisor idle check cycle** | <100ms | Check all IDLE agents (expected ~10 agents) |
| **IDLE pool hit rate** | >60% | Reuse 60%+ of task-specific agents |

---

## Consequences

### Positive ✅

- **Performance:** 10x faster reactivation (<10ms) vs creation (100ms)
- **Resource efficiency:** 3x reduction in agent creation (IDLE pooling)
- **Automatic cleanup:** 60s timeout prevents agent leaks
- **Policy-driven:** Configurable termination policies per agent type
- **Lifecycle guarantees:** Full FSM enforcement via hire_fire integration

### Negative ❌

- **Complexity:** 3 new components (termination policies, IDLE pooling, supervisor integration)
- **State management:** IDLE pool adds state tracking overhead
- **Configuration burden:** Termination policies need tuning per agent type

### Mitigations

- **Gradual rollout:** M2 feature (after M1 stable)
- **Sensible defaults:** 60s timeout, LRU eviction, session-scoped pooling
- **Metrics:** Track pool hit rate, reactivation latency, termination reasons

---

## Validation & Testing

### Acceptance Criteria

- [ ] Agent reactivation <10ms P95 ✓
- [ ] IDLE pool hit rate >60% (100 requests) ✓
- [ ] Termination policy enforcement (60s timeout) ✓
- [ ] Resource cleanup on termination ✓
- [ ] Supervisor idle check <100ms ✓
- [ ] WARD tests cover all lifecycle transitions ✓

### WARD Integration Tests

```python
# tests/l4_runtime/agents/test_lifecycle_integration.py

from ward import test, fixture
from k1.l3_execution.agents.factory import AgentFactory
from k1.l4_runtime.agents.hire_fire import HireFireManager

@fixture
async def integrated_factory():
    """Factory with hire_fire integration"""
    hire_fire = HireFireManager(...)
    active_roster = ActiveRoster(...)
    factory = AgentFactory(
        hire_fire_manager=hire_fire,
        active_roster=active_roster,
        ...
    )
    yield factory
    await factory.shutdown()


@test("reuse IDLE agent from pool")
async def _(factory=integrated_factory):
    # Create agent
    agent1 = await factory.create_or_reuse(
        session_id="session_1",
        agent_type="health_specialist",
        capabilities=["TOOL_CALL"],
        trace_id="test_1a"
    )

    # Transition to IDLE
    await agent1.transition_to_idle()

    # Request same agent type → should reuse
    agent2 = await factory.create_or_reuse(
        session_id="session_1",
        agent_type="health_specialist",
        capabilities=["TOOL_CALL"],
        trace_id="test_1b"
    )

    assert agent1.agent_id == agent2.agent_id  # Same agent reused
    assert agent2.state == AgentState.ACTIVE


@test("terminate agent after 60s IDLE timeout")
async def _(factory=integrated_factory):
    import asyncio

    agent = await factory.create_or_reuse(
        session_id="session_2",
        agent_type="health_specialist",
        capabilities=["TOOL_CALL"],
        trace_id="test_2"
    )

    # Transition to IDLE
    await agent.transition_to_idle()

    # Wait 65 seconds (past timeout)
    await asyncio.sleep(65)

    # Supervisor should have fired agent
    assert agent.state == AgentState.TERMINATED


@test("respect termination policy (persistent agents)")
async def _(factory=integrated_factory):
    import asyncio

    # Concierge = persistent (never timeout)
    agent = await factory.create_or_reuse(
        session_id="session_3",
        agent_type="concierge",
        capabilities=["MODEL_CALL"],
        trace_id="test_3"
    )

    await agent.transition_to_idle()

    # Wait 65 seconds
    await asyncio.sleep(65)

    # Should NOT be terminated (persistent policy)
    assert agent.state == AgentState.IDLE


@test("reactivation latency <10ms P95")
async def _(factory=integrated_factory):
    import time

    # Create agent and idle
    agent = await factory.create_or_reuse(
        session_id="session_4",
        agent_type="health_specialist",
        capabilities=["TOOL_CALL"],
        trace_id="test_4a"
    )
    await agent.transition_to_idle()

    # Measure reactivation latency (100 iterations)
    latencies = []
    for i in range(100):
        start = time.perf_counter()

        await factory.create_or_reuse(
            session_id="session_4",
            agent_type="health_specialist",
            capabilities=["TOOL_CALL"],
            trace_id=f"test_4_{i}"
        )

        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

        await agent.transition_to_idle()  # Reset for next iteration

    p95 = sorted(latencies)[94]
    assert p95 < 10, f"P95 reactivation latency {p95:.2f}ms exceeds 10ms budget"
```

---

## Implementation Plan

### Phase 1: hire_fire Integration (3 days)

**Day 1: Factory Integration**

- [ ] Add `hire_fire_manager` to AgentFactory
- [ ] Add `active_roster` access for IDLE pool
- [ ] Implement `create_or_reuse()` method
- [ ] Implement `_find_idle_agent()` helper

**Day 2: Termination Policies**

- [ ] Create `TerminationPolicy` dataclass
- [ ] Define built-in policies (persistent vs task-specific)
- [ ] Implement `TerminationPolicyManager`
- [ ] Add policy evaluation logic

**Day 3: Resource Cleanup**

- [ ] Implement `_register_termination_callback()`
- [ ] Add resource release on termination
- [ ] Test callback invocation

### Phase 2: Supervisor Enhancement (2 days)

**Day 4: IDLE Timeout Checking**

- [ ] Enhance supervisor with `_check_idle_timeouts()`
- [ ] Add 5s background task
- [ ] Integrate with termination policies
- [ ] Fire agents on timeout expiration

**Day 5: WARD Tests**

- [ ] Test IDLE pool reuse
- [ ] Test 60s timeout enforcement
- [ ] Test persistent agent policies
- [ ] Validate <10ms reactivation

**Total**: 5 days (M2 timeline)

---

## Dependencies

### Required Before Implementation

- ✅ **ADR-0086a (Agent Factory):** Base factory implementation
- ✅ **ADR-0086c (Resource Reservation):** Resource cleanup on termination
- ✅ **ADR-0005b (Hire/Fire Manager):** hire(), fire(), reactivate() methods
- ✅ **ADR-0005c (Supervisor):** State transition enforcement

### Enables

- 🚀 **10x faster agent reuse** (<10ms reactivation)
- 🚀 **60% reduction in agent creation** (IDLE pooling)
- 🚀 **Automatic resource cleanup** (termination policies)

---

## References

### Related ADRs

- [ADR-0086 (Dynamic Agent Creation)](0086-dynamic-agent-creation-subsystem.md)
- [ADR-0086a (Agent Factory)](0086a-agent-factory-pattern.md)
- [ADR-0005 (Agent Fabric Lifecycle)](0005-agent-fabric-lifecycle-fsm.md)
- [ADR-0005b (Hire/Fire Manager)](0005b-agent-hire-fire-manager.md)
- [ADR-0005c (Supervisor)](0005c-supervisor-agent-state-transitions.md)

### Research Citations

- **Actor Model (Hewitt 1973):** Autonomous lifecycle management
- **SEDA (Welsh 2001):** Resource management and admission control

---

**Status**: Approved ✅ → Implementation Phase M2 (Post-M1)

**Next Steps**:

1. Complete M1 sub-ADRs first (ADR-0086a-e)
2. Implement hire_fire integration (Day 1-3)
3. Enhance supervisor (Day 4-5)
4. Write WARD tests and validate <10ms reactivation
