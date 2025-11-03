---
adr_number: '0073'
title: Agent Lifecycle FSM Enhancements (Warming, Idle, Draining State Implementations)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0002
- ADR-0002a
- ADR-0002b
- ADR-0005
- ADR-0005a
- ADR-0005b
- ADR-0005c
- ADR-0005d
- ADR-0024
- ADR-0024c
- ADR-0072
- ADR-0073
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts:
- k1/contracts/agent_lifecycle/warming_state.yml
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0002
  - ADR-0002a
  - ADR-0002b
  - ADR-0005
  - ADR-0005a
  - ADR-0005b
  - ADR-0005c
  - ADR-0005d
  - ADR-0024
  - ADR-0024c
  - ADR-0072
  - ADR-0073
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


# ADR-0073: Agent Lifecycle FSM Enhancements (Warming, Idle, Draining State Implementations)

**Status:** ✅ Accepted
**Date:** 2025-10-17
**Authors:** K1 Architecture Team
**Milestone:** M1 - Dynamic Agent Creation Subsystem
**Category:** Layer 1 - Core Kernel (Agent Fabric)
**Related ADRs:**
- [ADR-0005 (Agent Lifecycle FSM Foundation)](0005-agent-lifecycle-fsm.md)
- [ADR-0005a (Warming State Design)](0005a-agent-warming-state.md)
- [ADR-0005b (Idle Pooling)](0005b-agent-idle-pooling.md)
- [ADR-0005c (Graceful Draining)](0005c-agent-draining-shutdown.md)
- [ADR-0005d (Crash Blacklist)](0005d-supervisor-blacklist.md)
- [ADR-0072 (Dynamic Agent Creation - Parent M1 Epic 1)](0072-dynamic-agent-creation-subsystem.md)
- [ADR-0002 (Actor Model Agent Isolation)](0002-actor-model-agent-isolation.md)
- [ADR-0002a (Mailbox & MPSC)](0002a-mailbox-mpsc-queue-implementation.md)
- [ADR-0002b (Supervisor Monitoring)](0002b-supervisor-monitoring-crash-recovery.md)

---

## Context: Why FSM State Enhancements?

**Problem Statement:**

ADR-0005 defined the **6-state Agent Lifecycle FSM**, but the implementation details for three critical states were incomplete:

1. **WARMING State** (Issue 1.2.1)
   - Resource validation before activation
   - Model loading, capability binding, health checks
   - Currently in ADR-0005a but needs **full implementation spec** with error handling, timeouts, rollback

2. **IDLE State** (Issue 1.2.2)
   - Agent pooling for reuse efficiency
   - TTL-based expiration, health checks during idle
   - Currently in ADR-0005b but needs **memory conservation strategy**, wake thresholds, pool management

3. **DRAINING State** (Issue 1.2.3)
   - Graceful shutdown with task completion tracking
   - Currently in ADR-0005c but needs **concrete implementation** for task tracking, timeout handling, dependency cleanup

**Consequence of Incomplete Specs:**

- ❌ Factory doesn't know when to transition PENDING → WARMING (resource check algorithm missing)
- ❌ Supervisor doesn't know when to transition WARMING → ACTIVE (health check thresholds missing)
- ❌ Memory manager doesn't know how to pool IDLE agents (eviction policy missing)
- ❌ Draining logic doesn't track task completion (state machine missing)

**Goal:** This ADR provides **full implementation context** for each state, including:
- State entry/exit conditions
- Error handling & rollback
- Timeout enforcement
- Performance budgets
- Integration with supervisor, factory, and memory manager

---

## Decision: Implement 3-Part FSM Enhancement Pattern

We implement **three coordinated FSM enhancements** that work together:

### Enhancement 1: WARMING State - 4-Check Resource Validation (Issue 1.2.1)

```python
class WarmingState:
    """WARMING state with 4-part resource validation before ACTIVE transition"""

    def __init__(self, agent_id: str, agent_spec: AgentSpec, supervisor: Supervisor):
        self.agent_id = agent_id
        self.agent_spec = agent_spec
        self.supervisor = supervisor
        self.warming_start_ts = None
        self.validation_results = {}
        self.health_checks_passed = 0
        self.health_checks_total = 4

    async def enter(self) -> None:
        """PENDING → WARMING transition"""
        self.warming_start_ts = time.time_ns() // 1_000_000  # ms
        logger.info("agent_warming_start", agent_id=self.agent_id, trace_id=self.supervisor.trace_id)

        try:
            # Check 1: Resource Availability (CPU, Memory, Disk)
            await self._check_resource_availability()

            # Check 2: Model Loading (language model, vision model, embeddings)
            await self._check_model_loading()

            # Check 3: Capability Binding (assign capabilities from spec)
            await self._check_capability_binding()

            # Check 4: Supervisor Health Signal (supervisor confirms monitoring ready)
            await self._check_supervisor_health()

            # All checks passed → mark ready for ACTIVE transition
            self.validation_results['all_checks_passed'] = True
            logger.info("agent_warming_checks_complete", agent_id=self.agent_id,
                       trace_id=self.supervisor.trace_id, passed=True)

        except WarmingCheckFailed as e:
            self.validation_results['error'] = str(e)
            logger.error("agent_warming_failed", agent_id=self.agent_id,
                        error=str(e), trace_id=self.supervisor.trace_id)
            # Signal supervisor to rollback (WARMING → TERMINATED)
            await self.supervisor.handle_warming_failure(self.agent_id, error=e)

    async def _check_resource_availability(self) -> None:
        """Check 1: CPU, memory, disk available per spec"""
        required_mem_mb = self.agent_spec.memory_budget_mb
        required_cpu_cores = self.agent_spec.cpu_cores

        available_mem_mb = self.supervisor.get_available_memory_mb()
        available_cpu_cores = self.supervisor.get_available_cpu_cores()

        if available_mem_mb < required_mem_mb:
            raise WarmingCheckFailed(
                f"Insufficient memory: need {required_mem_mb}MB, have {available_mem_mb}MB"
            )

        if available_cpu_cores < required_cpu_cores:
            raise WarmingCheckFailed(
                f"Insufficient CPU: need {required_cpu_cores} cores, have {available_cpu_cores}"
            )

        # Reserve resources
        self.supervisor.reserve_resources(
            agent_id=self.agent_id,
            memory_mb=required_mem_mb,
            cpu_cores=required_cpu_cores
        )

        self.validation_results['resource_check'] = 'PASS'
        logger.debug("resource_check_passed", agent_id=self.agent_id,
                    memory_mb=required_mem_mb, cpu_cores=required_cpu_cores)

    async def _check_model_loading(self) -> None:
        """Check 2: Language model, vision model, embeddings available"""
        model_hub = self.supervisor.model_hub

        # Load language model (e.g., gpt-4, claude-3-opus)
        if self.agent_spec.language_model:
            try:
                await model_hub.preload_model(
                    model_id=self.agent_spec.language_model,
                    agent_id=self.agent_id,
                    timeout_sec=30  # P95 budget: <30s for model load
                )
            except Exception as e:
                raise WarmingCheckFailed(f"Failed to load language model: {e}")

        # Load vision model if needed
        if self.agent_spec.vision_model:
            try:
                await model_hub.preload_model(
                    model_id=self.agent_spec.vision_model,
                    agent_id=self.agent_id,
                    timeout_sec=30
                )
            except Exception as e:
                raise WarmingCheckFailed(f"Failed to load vision model: {e}")

        # Load embeddings if needed
        if self.agent_spec.embedding_model:
            try:
                await model_hub.preload_model(
                    model_id=self.agent_spec.embedding_model,
                    agent_id=self.agent_id,
                    timeout_sec=10
                )
            except Exception as e:
                raise WarmingCheckFailed(f"Failed to load embedding model: {e}")

        self.validation_results['model_check'] = 'PASS'
        logger.debug("model_check_passed", agent_id=self.agent_id,
                    models=[self.agent_spec.language_model, self.agent_spec.vision_model])

    async def _check_capability_binding(self) -> None:
        """Check 3: Bind capabilities from spec to agent"""
        capability_manager = self.supervisor.capability_manager

        for capability_name in self.agent_spec.capabilities:
            try:
                # Create capability token (HMAC-signed)
                cap_token = await capability_manager.issue_capability(
                    subject=f"agent:{self.agent_id}",
                    resource=capability_name,
                    rights=["execute"],
                    ttl_seconds=3600,  # 1-hour capability TTL
                    constraints={
                        "agent_id": self.agent_id,
                        "session_id": self.supervisor.session_id
                    }
                )

                # Store capability token in agent's secure store
                await self.supervisor.store_capability(
                    agent_id=self.agent_id,
                    capability_name=capability_name,
                    capability_token=cap_token
                )

            except Exception as e:
                raise WarmingCheckFailed(f"Failed to bind capability {capability_name}: {e}")

        self.validation_results['capability_check'] = 'PASS'
        logger.debug("capability_check_passed", agent_id=self.agent_id,
                    capabilities_count=len(self.agent_spec.capabilities))

    async def _check_supervisor_health(self) -> None:
        """Check 4: Supervisor confirms it's ready to monitor this agent"""
        try:
            # Request supervisor health signal
            supervisor_ready = await self.supervisor.health_check(
                agent_id=self.agent_id,
                timeout_sec=5
            )

            if not supervisor_ready:
                raise WarmingCheckFailed("Supervisor health check failed")

        except asyncio.TimeoutError:
            raise WarmingCheckFailed("Supervisor health check timeout (>5s)")
        except Exception as e:
            raise WarmingCheckFailed(f"Supervisor health check error: {e}")

        self.validation_results['supervisor_check'] = 'PASS'
        logger.debug("supervisor_check_passed", agent_id=self.agent_id)

    async def exit(self) -> None:
        """WARMING → ACTIVE transition (successful) or WARMING → TERMINATED (failed)"""
        elapsed_ms = (time.time_ns() // 1_000_000) - self.warming_start_ts

        if self.validation_results.get('all_checks_passed'):
            logger.info("agent_warming_success", agent_id=self.agent_id,
                       elapsed_ms=elapsed_ms, trace_id=self.supervisor.trace_id)
        else:
            logger.info("agent_warming_exit", agent_id=self.agent_id,
                       elapsed_ms=elapsed_ms, result=self.validation_results)

```

**Performance Budget (P95):**
- Resource check: <5ms (in-memory lookups)
- Model loading: <30s (network I/O to model hub, preload to device)
- Capability binding: <100ms (HMAC token generation + storage)
- Supervisor health: <5s (supervisor monitoring confirmation)
- **Total WARMING duration: <35s (P95)** ← This is intentional: model loading takes time, but only happens once per agent lifecycle

---

### Enhancement 2: IDLE State - Agent Pooling & TTL Management (Issue 1.2.2)

```python
class IdleState:
    """IDLE state with pooling, TTL expiration, and health checks"""

    def __init__(self, agent_id: str, supervisor: Supervisor):
        self.agent_id = agent_id
        self.supervisor = supervisor
        self.idle_start_ts = None
        self.ttl_seconds = 600  # 10-minute default TTL
        self.last_health_check_ts = None
        self.health_check_interval_sec = 30  # Every 30s in IDLE

    async def enter(self) -> None:
        """ACTIVE → IDLE transition (no active tasks)"""
        self.idle_start_ts = time.time_ns() // 1_000_000  # ms
        self.last_health_check_ts = time.time()

        # Add to agent pool for reuse
        await self.supervisor.pool_manager.add_to_pool(
            agent_id=self.agent_id,
            agent=self.supervisor.get_agent(self.agent_id),
            ttl_seconds=self.ttl_seconds
        )

        logger.info("agent_idle_start", agent_id=self.agent_id,
                   ttl_seconds=self.ttl_seconds, trace_id=self.supervisor.trace_id)

    async def periodic_health_check(self) -> bool:
        """Called every 30s while in IDLE state - return False if health check fails"""
        elapsed_sec = time.time() - self.last_health_check_ts

        if elapsed_sec < self.health_check_interval_sec:
            return True  # Not time for next check yet

        try:
            # Minimal health check: agent process still running, memory still allocated
            health_status = await self.supervisor.quick_health_check(self.agent_id, timeout_sec=2)

            if not health_status:
                logger.warn("idle_health_check_failed", agent_id=self.agent_id)
                return False  # Trigger IDLE → TERMINATED

            self.last_health_check_ts = time.time()
            return True

        except asyncio.TimeoutError:
            logger.error("idle_health_check_timeout", agent_id=self.agent_id, timeout_sec=2)
            return False

    async def check_ttl_expired(self) -> bool:
        """Check if TTL has elapsed - return True if expired"""
        elapsed_ms = (time.time_ns() // 1_000_000) - self.idle_start_ts
        elapsed_sec = elapsed_ms / 1000.0

        if elapsed_sec > self.ttl_seconds:
            logger.info("agent_idle_ttl_expired", agent_id=self.agent_id,
                       elapsed_sec=elapsed_sec, ttl_seconds=self.ttl_seconds)
            return True

        return False

    async def exit(self) -> None:
        """IDLE → ACTIVE transition (new task received) or IDLE → TERMINATED (TTL/health failure)"""
        await self.supervisor.pool_manager.remove_from_pool(self.agent_id)
        logger.debug("agent_idle_exit", agent_id=self.agent_id)

```

**Memory Conservation Strategy (ADR-0024c integration):**

```python
class AgentPoolManager:
    """Manages agent pooling to maximize reuse while respecting memory budgets"""

    def __init__(self, max_agents_per_session: int = 3, memory_budget_mb: int = 500):
        self.max_agents_per_session = max_agents_per_session
        self.memory_budget_mb = memory_budget_mb
        self.idle_pools = {}  # session_id → {agent_id → Agent}
        self.total_memory_used_mb = 0

    async def add_to_pool(self, agent_id: str, agent: Agent, ttl_seconds: int = 600) -> None:
        """Add idle agent to pool"""
        session_id = agent.session_id

        if session_id not in self.idle_pools:
            self.idle_pools[session_id] = {}

        # Check if pool is full
        if len(self.idle_pools[session_id]) >= self.max_agents_per_session:
            # Evict LRU agent (least recently used)
            lru_agent_id = self._find_lru_agent(session_id)
            await self.remove_from_pool(lru_agent_id)
            logger.debug("pool_eviction_lru", session_id=session_id, evicted_agent_id=lru_agent_id)

        # Add agent to pool with TTL
        self.idle_pools[session_id][agent_id] = {
            'agent': agent,
            'added_ts': time.time(),
            'ttl_seconds': ttl_seconds,
            'access_count': 0
        }

        logger.debug("agent_added_to_pool", agent_id=agent_id, session_id=session_id)

    async def remove_from_pool(self, agent_id: str) -> Agent:
        """Remove agent from pool (for reuse or termination)"""
        for session_id, pool in self.idle_pools.items():
            if agent_id in pool:
                agent_entry = pool.pop(agent_id)
                logger.debug("agent_removed_from_pool", agent_id=agent_id, session_id=session_id)
                return agent_entry['agent']

        raise KeyError(f"Agent {agent_id} not in any pool")

    async def get_from_pool(self, session_id: str, agent_type: str) -> Optional[Agent]:
        """Get first available idle agent from pool for session"""
        if session_id not in self.idle_pools:
            return None

        pool = self.idle_pools[session_id]

        for agent_id, agent_entry in list(pool.items()):
            # Check TTL
            elapsed_sec = time.time() - agent_entry['added_ts']
            if elapsed_sec > agent_entry['ttl_seconds']:
                # TTL expired, remove
                pool.pop(agent_id)
                logger.debug("pool_agent_ttl_expired", agent_id=agent_id)
                continue

            # Check type match
            if agent_entry['agent'].agent_type == agent_type:
                # Reuse this agent
                pool.pop(agent_id)
                agent_entry['access_count'] += 1
                logger.info("pool_agent_reused", agent_id=agent_id, access_count=agent_entry['access_count'])
                return agent_entry['agent']

        return None  # No available agents of this type

    def _find_lru_agent(self, session_id: str) -> str:
        """Find least recently used agent in session pool"""
        pool = self.idle_pools[session_id]
        lru_agent_id = min(pool.keys(), key=lambda aid: pool[aid]['added_ts'])
        return lru_agent_id

```

**Performance Budget (P95):**
- Pool lookup: <1ms (in-memory dict)
- Health check: <2s (quick process/memory verification)
- TTL check: <1ms (timestamp comparison)
- Pool eviction: <10ms (LRU scan of ≤3 agents)

---

### Enhancement 3: DRAINING State - Task Completion Tracking (Issue 1.2.3)

```python
class DrainingState:
    """DRAINING state with task tracking and graceful shutdown"""

    def __init__(self, agent_id: str, supervisor: Supervisor):
        self.agent_id = agent_id
        self.supervisor = supervisor
        self.draining_start_ts = None
        self.active_tasks = {}  # task_id → TaskTracker
        self.draining_timeout_sec = 30  # Max 30s to complete all tasks

    async def enter(self) -> None:
        """ACTIVE/IDLE → DRAINING transition (shutdown requested)"""
        self.draining_start_ts = time.time_ns() // 1_000_000  # ms

        # Get list of active tasks for this agent
        self.active_tasks = await self.supervisor.get_active_tasks(self.agent_id)

        logger.info("agent_draining_start", agent_id=self.agent_id,
                   active_task_count=len(self.active_tasks), trace_id=self.supervisor.trace_id)

        # Signal all tasks to complete gracefully
        for task_id, task in self.active_tasks.items():
            await task.request_completion()

    async def wait_for_completion(self) -> bool:
        """Wait for all tasks to complete or timeout - return True if all completed"""
        start_time = time.time()

        while True:
            elapsed_sec = time.time() - start_time

            # Check timeout
            if elapsed_sec > self.draining_timeout_sec:
                logger.warn("draining_timeout", agent_id=self.agent_id,
                           elapsed_sec=int(elapsed_sec), timeout_sec=self.draining_timeout_sec,
                           incomplete_tasks=len(self.active_tasks))
                return False  # Timeout - force termination

            # Check if all tasks completed
            remaining_tasks = [tid for tid, task in self.active_tasks.items()
                             if not task.is_completed()]

            if not remaining_tasks:
                logger.info("draining_all_tasks_completed", agent_id=self.agent_id,
                           elapsed_sec=int(elapsed_sec))
                return True

            # Log progress
            logger.debug("draining_in_progress", agent_id=self.agent_id,
                        completed=len(self.active_tasks) - len(remaining_tasks),
                        total=len(self.active_tasks))

            # Wait a bit before checking again (250ms)
            await asyncio.sleep(0.25)

    async def cleanup_dependencies(self) -> None:
        """Clean up agent dependencies before termination"""
        try:
            # Release resources from supervisor
            await self.supervisor.release_resources(self.agent_id)

            # Remove from pool if present
            try:
                await self.supervisor.pool_manager.remove_from_pool(self.agent_id)
            except KeyError:
                pass  # Not in pool

            # Revoke all capabilities
            await self.supervisor.capability_manager.revoke_agent_capabilities(self.agent_id)

            # Unload models from model hub
            await self.supervisor.model_hub.unload_agent_models(self.agent_id)

            logger.info("agent_dependencies_cleanup", agent_id=self.agent_id)

        except Exception as e:
            logger.error("draining_cleanup_error", agent_id=self.agent_id, error=str(e))

    async def exit(self) -> None:
        """DRAINING → TERMINATED transition"""
        elapsed_ms = (time.time_ns() // 1_000_000) - self.draining_start_ts

        # Wait for task completion
        all_completed = await self.wait_for_completion()

        if not all_completed:
            logger.warn("agent_draining_forced_termination", agent_id=self.agent_id)
            # Force-terminate remaining tasks
            for task_id, task in self.active_tasks.items():
                await task.force_terminate()

        # Clean up dependencies
        await self.cleanup_dependencies()

        logger.info("agent_draining_complete", agent_id=self.agent_id,
                   elapsed_ms=elapsed_ms, all_tasks_completed=all_completed)

```

**Task Tracking Implementation:**

```python
class TaskTracker:
    """Tracks task completion during draining"""

    def __init__(self, task_id: str, agent_id: str):
        self.task_id = task_id
        self.agent_id = agent_id
        self.completion_requested = False
        self.completed = False
        self.started_ts = time.time()

    async def request_completion(self) -> None:
        """Request task to complete gracefully"""
        self.completion_requested = True
        logger.debug("task_completion_requested", task_id=self.task_id, agent_id=self.agent_id)

    def is_completed(self) -> bool:
        """Check if task completed"""
        return self.completed

    async def mark_completed(self) -> None:
        """Mark task as completed"""
        elapsed_sec = time.time() - self.started_ts
        self.completed = True
        logger.debug("task_completed", task_id=self.task_id, agent_id=self.agent_id,
                    elapsed_sec=int(elapsed_sec), graceful=self.completion_requested)

    async def force_terminate(self) -> None:
        """Force-terminate task (timeout during draining)"""
        elapsed_sec = time.time() - self.started_ts
        logger.warn("task_force_terminated", task_id=self.task_id, agent_id=self.agent_id,
                   elapsed_sec=int(elapsed_sec))
        self.completed = True

```

**Performance Budget (P95):**
- Draining start: <10ms (task list collection)
- Task completion wait: <30s (user-defined timeout)
- Dependency cleanup: <500ms (resource deallocation)
- **Total DRAINING duration: <30.5s (P95)** ← Intentional: wait for user tasks to finish

---

## Consequences

### Positive

✅ **Complete FSM Implementation:** All three critical states (WARMING, IDLE, DRAINING) now have full implementation specs with error handling and timeouts.

✅ **Resource Safety:** WARMING validates resource availability before activation; IDLE manages memory pooling; DRAINING releases all resources.

✅ **Reliability:** Health checks in all states (WARMING supervisor check, IDLE periodic checks, DRAINING task tracking).

✅ **Performance:** Inline with ADR-0024 budgets:
- WARMING: <35s (model loading dominates)
- IDLE: <2ms checks
- DRAINING: <30.5s (graceful shutdown)

✅ **Testability:** Clear entry/exit conditions for each state enable comprehensive WARD testing.

### Negative

❌ **Model Preloading Latency:** WARMING state preloads models (~20-30s), which blocks agent activation. This is intentional but adds to P95.

❌ **Memory Overhead:** Agent pooling in IDLE requires keeping models/capabilities loaded (solves latency, costs memory).

❌ **Task Tracking Complexity:** DRAINING requires supervisor to track all active tasks per agent (adds operational complexity).

### Mitigations

- Model preloading happens **once** per agent lifecycle, amortized over many tasks
- Agent pooling is **bounded** (max 3 agents per session) to prevent unbounded memory growth
- Task tracking uses **lightweight metadata**, not full task capture

---

## Implementation Roadmap (M1 Issues 1.2.1, 1.2.2, 1.2.3)

### Issue 1.2.1: WARMING State Implementation (1-2 weeks)

**Deliverables:**
- `k1/agent_fabric/warming_state.py` - Full implementation with 4 checks
- `tests/agent_fabric/test_warming_state.py` - WARD integration tests (resource check, model loading, capability binding, supervisor health)
- `contracts/agent_lifecycle/warming_state.yml` - YAML spec with check conditions

**Success Criteria:**
- All 4 checks implemented and tested
- <30s P95 for non-preloaded models
- Rollback on any check failure (WARMING → TERMINATED)

### Issue 1.2.2: IDLE State + Pooling Implementation (1 week)

**Deliverables:**
- `k1/agent_fabric/idle_state.py` - IDLE state with TTL and health checks
- `k1/agent_fabric/pool_manager.py` - AgentPoolManager with LRU eviction
- `tests/agent_fabric/test_idle_state.py` - WARD tests (pool management, TTL expiration, health checks)

**Success Criteria:**
- Agents reused from pool within <1ms
- TTL-based eviction working correctly
- Memory budgets respected (≤3 agents per session)

### Issue 1.2.3: DRAINING State + Task Tracking (1 week)

**Deliverables:**
- `k1/agent_fabric/draining_state.py` - DRAINING state with task tracking
- `k1/agent_fabric/task_tracker.py` - TaskTracker for completion tracking
- `tests/agent_fabric/test_draining_state.py` - WARD tests (graceful shutdown, task completion, timeout)

**Success Criteria:**
- Graceful shutdown completes all in-flight tasks
- Timeout enforcement after 30s
- Dependency cleanup (resources, capabilities, models)

---

## References

**Research:**
- Actor Model (Hewitt 1973) - Agent isolation and message-passing
- Capabilities (Dennis & Van Horn 1966) - Fine-grained access control
- Saga Pattern (Garcia-Molina 1987) - Task completion tracking in distributed systems

**Related Architecture:**
- `k1_agent_lifecycle_fsm.mmd` - FSM diagram with 6 states
- `k1_agent_lifecycle_fsm_docs.md` - High-level documentation
- ADR-0005 (Agent Lifecycle FSM Foundation)
- ADR-0024c (Memory Budgets - resource pooling constraints)

**Performance Targets:**
- WARMING: <35s (P95) including model preload
- IDLE: <2s (health check interval)
- DRAINING: <30s (task completion timeout)