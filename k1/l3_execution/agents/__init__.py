"""
K1 Layer 3 Execution — agents/ module

PURPOSE:
========
Agent lifecycle management, AI agent personalities, mailboxes, and supervision.
Implements the Actor Model for all 58 K1 agents (4 AI agents + 54 pure actors).

ARCHITECTURE:
=============
8 sub-modules implementing agent lifecycle FSM, message passing, and supervision:

1. registry/      - Agent YAML specifications (58 agent types, O(1) lookup)
2. hire_fire/     - Agent lifecycle FSM manager (6-state FSM, <600ms hire, <50ms fire)
3. supervisor/    - Health monitoring & crash detection (<100ms detection)
4. personality/   - Persona adaptation (<5ms trait formatting)
5. mailbox/       - Inter-agent messaging (MPSC queues, <1ms enqueue/dequeue)
6. active_roster/ - Runtime agent tracking (O(1) lookup/insert/remove)
7. concierge/     - AI Agent: NLU & intent classification (<50ms P95)
8. researcher/    - AI Agent: Knowledge synthesis & retrieval (<3000ms P95)

PRIMARY ADRs:
=============
- ADR-0002: Actor Model for Agent Isolation
  * ALL 58 agents use Actor Model (message passing, mailboxes, supervision)
  * No shared memory, no locks, no mutexes
  * Fault isolation: agent crash ≠ kernel crash

- ADR-0002a: Mailbox MPSC Queue Implementation
  * Multi-Producer Single-Consumer lock-free queue
  * 4-tier priority (URGENT/REALTIME/INTERACTIVE/BACKGROUND)
  * Backpressure handling (high watermark 50, low watermark 25)

- ADR-0002b: Actor Fabric Supervisor
  * Heartbeat monitoring (1s interval, 3s timeout)
  * Crash detection (<100ms), blacklist manager (3 crashes → 1 hour)
  * Supervisor tree (all agents monitored)

- ADR-0005: Agent Lifecycle FSM (6-State)
  * PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
  * Cold start <600ms P95 (AI agents), <100ms P95 (pure actors)
  * Warm pool reactivation <50ms P95

- ADR-0005a: WARMING State (Dual-Path Warmup)
  * AI agents: Load LLM models (150-200ms)
  * Pure actors: Load config (10-20ms)
  * Thermal-aware placement (NPU → GPU → CPU → Remote)

- ADR-0005b: IDLE Pooling
  * TTL tracking (5 min default)
  * Reactivation <50ms P95 (5× faster than cold start)
  * Pool hit rate >80%, 42% memory reduction

- ADR-0005c: DRAINING State (3-Phase Drain)
  * Stop accepting new tasks, complete in-flight tasks
  * 5s timeout, SIGTERM → SIGKILL cleanup
  * Resource cleanup: model unload (200ms), KV cache free (100ms)

- ADR-0005d: Supervisor
  * Heartbeat monitoring (1s interval, event-loop heartbeat 200ms)
  * Crash detection <100ms, replacement spawning
  * Blacklist: 3 crashes in 10 min → 1 hour duration → 88% reduction

- ADR-0005e: Agent Personalities
  * 4 AI agents: Concierge (50ms), Planner (5000ms), Researcher (3000ms), Safety Watch (100ms)
  * 54 pure actors: deterministic logic (no LLM)
  * Capability system (5 types: TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL, NETWORK_ACCESS)

RELATED ADRs:
=============
- ADR-0001b: Model Hub Architecture (AI agent integration)
- ADR-0010: Capability Security (agent capability declarations)
- ADR-0017d: SessionState Persona Section (personality integration)
- ADR-0024: Performance Budgets (Agent Hire <600ms, Fire <50ms)
- ADR-0028: WFQ Scheduler (priority-based scheduling)
- ADR-0029: Prometheus Metrics (agent lifecycle, crash rate)
- ADR-0031: Cost Tracking (LLM token usage)

PERFORMANCE BUDGETS:
====================
- Agent hire (cold):       300-600ms P95 (AI), 50-100ms P95 (pure actor)
- Agent hire (warm pool):  <50ms P95 (reactivation)
- Agent fire:              <50ms P95
- Mailbox enqueue:         <1ms P95
- Mailbox dequeue:         <0.5ms P95
- Supervisor overhead:     <5ms per agent per second
- IDLE pool hit rate:      >80%

TESTING STRATEGY:
=================
See ADR-0004d: Layer 3 Integration Tests
- Agent lifecycle FSM transitions (all 6 states)
- WARMING: AI vs pure actor warmup paths
- IDLE pooling: reactivation <50ms
- DRAINING: 3-phase drain, timeout enforcement
- Supervisor: heartbeat, crash detection, blacklist
- Mailbox: MPSC queue, priority, backpressure
- Performance: hire <600ms, fire <50ms

OBSERVABILITY:
==============
Prometheus Metrics (ADR-0029):
- layer3_agent_hire_latency_ms{agent_type, warmup_type}
- layer3_agent_crash_rate{agent_type}
- layer3_agent_fire_latency_ms{agent_type}
- layer3_mailbox_depth{agent_id, priority}
- layer3_supervisor_heartbeat_failures{agent_id}
- layer3_idle_pool_hit_rate{}

INTEGRATION POINTS:
===================
Layer 3 ← Layer 2:
- AgentHireRequest → hire_fire/ (spawn agent, FSM transition PENDING→WARMING)
- TaskAssignment → mailbox/ (enqueue task to agent mailbox)

Layer 3 → Layer 4:
- AgentState → session_state/control section (FSM state, last heartbeat)
- Active roster → session_state/roster (active agent IDs)

Layer 3 → Layer 5:
- Metrics → observability/prometheus (agent lifecycle metrics)
- Logs → logging/ (structured logging with trace_id)

USAGE EXAMPLE:
==============
```python
from k1.l3_execution.agents.hire_fire import AgentHireFireManager
from k1.l3_execution.agents.supervisor import AgentSupervisor

# Initialize agents subsystem
hire_fire_mgr = AgentHireFireManager(config)
supervisor = AgentSupervisor(config)

# Hire agent (Layer 2 → Layer 3)
agent_id = await hire_fire_mgr.hire_agent(
    agent_type="concierge",
    session_id="sess_123",
    capabilities=["TOOL_CALL", "MEMORY_READ"]
)

# Supervisor monitors health
await supervisor.start_monitoring(agent_id)

# Fire agent when done
await hire_fire_mgr.fire_agent(agent_id, reason="task_complete")
```

RESEARCH FOUNDATIONS:
=====================
- Actor Model (Hewitt 1973) — Message passing, fault isolation
- Erlang OTP Supervision Trees (Armstrong 2003) — Supervisor patterns
- Akka Actor Lifecycle (Lightbend 2013) — Lifecycle management
- Capabilities (Dennis & Van Horn 1966) — Unforgeable tokens, least privilege

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
