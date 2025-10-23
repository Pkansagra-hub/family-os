"""
K1 Layer 3 Execution — agents/hire_fire/

PURPOSE:
========
Agent lifecycle FSM manager implementing 6-state FSM (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED).
Handles agent hiring (<600ms P95) and firing (<50ms P95) with thermal-aware placement.

RESPONSIBILITIES:
=================
**Agent Hiring (<600ms P95):**
1. PENDING→WARMING: Trigger warmup, spawn process/thread
2. WARMING→ACTIVE: Load model (AI) or config (pure actor)
   - AI Agent Warmup (150-200ms): Model load, prompt cache, KV cache init
   - Pure Actor Warmup (10-20ms): Config load, mailbox init, supervisor registration
3. Placement Planner: Thermal-aware placement (NPU→GPU→CPU→Remote)
4. Lease Issuance: Generate capability token (HMAC-SHA256 signature)

**Agent Firing (<50ms P95):**
1. ACTIVE→DRAINING: Stop accepting new tasks
2. DRAINING→TERMINATED: Complete in-flight tasks (5s timeout), cleanup
3. Resource Cleanup: Model unload (200ms), KV cache free (100ms), metrics flush (50ms)

**IDLE Pooling:**
- TTL tracking (5 min default)
- Reactivation <50ms P95 (5× faster than cold start)
- Pool hit rate >80%
- Memory optimization (42% footprint reduction: 90MB vs 155MB)

PRIMARY ADRs:
=============
- ADR-0005: Agent Lifecycle (6-state FSM: PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
  * Complete FSM specification with all 6 states
  * State transition rules, timeout enforcement
  * Performance budgets: hire <600ms P95, fire <50ms P95

- ADR-0005a: WARMING State (dual-path warmup)
  * AI agents: Model load (150-200ms), prompt cache (5-10ms), KV cache init (20-30ms), warmup inference (30-50ms)
  * Pure actors: Config load (10-20ms), mailbox init (5ms), supervisor registration (5ms)
  * Thermal-aware placement via Model Hub Placement Planner (ADR-0027)
  * Timeout: 5s max → TERMINATED if exceeded

- ADR-0005b: IDLE Pooling (TTL tracking, reactivation <50ms)
  * Transition: ACTIVE → IDLE after 5 min inactivity
  * Reactivation: IDLE → ACTIVE <50ms P95 (5× faster than cold start)
  * Pool management: LRU eviction, memory budget (512MB global), per-agent max 256MB
  * Hit rate target: >80% (20% miss → cold start)
  * Memory optimization: 42% reduction (90MB pooled vs 155MB active)

- ADR-0005c: DRAINING State (3-phase drain, 5s timeout)
  * Phase 1: Stop accepting new tasks (mailbox read-only)
  * Phase 2: Complete in-flight tasks (5s timeout)
  * Phase 3: Resource cleanup (model unload, KV cache free, metrics flush)
  * Timeout enforcement: SIGTERM → 5s → SIGKILL
  * Saga integration (ADR-0008): Compensation actions during drain

RELATED ADRs:
=============
- ADR-0002: Actor Model (hire_fire is pure actor)
- ADR-0006: 3-Phase Orchestration (hire triggered by negotiation)
- ADR-0024: Performance Budgets (hire <600ms P95)
- ADR-0027: Model Placement (thermal-aware placement)
- ADR-0029: Prometheus Metrics (hire latency, crash rate)

PERFORMANCE METRICS:
====================
- Agent hire (cold start): 300-600ms P95 (AI), 50-100ms P95 (pure actor)
- Agent hire (warm pool): <50ms P95 (reactivation)
- Agent fire: <50ms P95
- IDLE pool hit rate: >80%
- Memory per pooled agent: 90MB (42% reduction vs 155MB active)

KEY ALGORITHMS:
===============
**Agent Hiring (Cold Start):**
```python
async def hire_agent(agent_type: str, session_id: str) -> str:
    \"\"\"Hire agent with 6-state FSM.\"\"\"
    # 1. PENDING: Validate request, allocate agent_id
    agent_id = generate_agent_id()
    agent_state = AgentState(agent_id, state=State.PENDING)

    # 2. WARMING: Spawn process, load resources
    await transition_to_warming(agent_id)
    if is_ai_agent(agent_type):
        await load_model(agent_id)  # 150-200ms
    else:
        await load_config(agent_id)  # 10-20ms

    # 3. ACTIVE: Ready to process tasks
    await transition_to_active(agent_id)
    return agent_id
```

**Agent Firing (Graceful Shutdown):**
```python
async def fire_agent(agent_id: str, reason: str) -> None:
    \"\"\"Fire agent with graceful drain.\"\"\"
    # 1. DRAINING: Stop new tasks, complete in-flight
    await transition_to_draining(agent_id)
    await wait_for_completion(agent_id, timeout_ms=5000)

    # 2. TERMINATED: Cleanup resources
    await cleanup_resources(agent_id)
    await transition_to_terminated(agent_id, reason)
```

**IDLE Pool Reactivation:**
```python
async def reactivate_agent(agent_id: str) -> None:
    \"\"\"Reactivate IDLE agent <50ms.\"\"\"
    # Fast path: IDLE → ACTIVE (no model reload)
    if agent_state.state == State.IDLE:
        await transition_to_active(agent_id)  # <50ms
    else:
        await hire_agent(agent_type, session_id)  # Cold start
```

INTEGRATION POINTS:
===================
Layer 2 → Layer 3 (Agent Hiring):
```python
# Orchestrator calls hire_fire
from k1.l3_execution.agents.hire_fire import AgentHireFireManager

mgr = AgentHireFireManager(config)
agent_id = await mgr.hire_agent(
    agent_type="concierge",
    session_id="sess_123",
    capabilities=["TOOL_CALL", "MEMORY_READ"]
)
```

Layer 3 → Layer 4 (State Updates):
```python
# Update SessionState control section
await session_state.update_control(
    field_path="active_agents",
    value=[agent_id],
    cognitive_trace_id=trace_id
)
```

Layer 3 → Layer 5 (Placement):
```python
# Call Placement Planner for thermal-aware placement
from k1.l5_infrastructure.thermal import PlacementPlanner

planner = PlacementPlanner()
accelerator = await planner.select_accelerator(
    model_name="phi-3-mini",
    thermal_budget_w=12.0
)  # Returns: NPU | GPU | CPU | Remote
```

TESTING:
========
See tests/l3_execution/agents/test_hire_fire.py (ADR-0004d):
- Agent hiring (cold start): <600ms P95
- Agent hiring (warm pool): <50ms P95
- Agent firing: <50ms P95
- FSM transitions (all 6 states)
- IDLE pooling (hit rate >80%)
- DRAINING timeout enforcement
- Resource cleanup validation

OBSERVABILITY:
==============
Prometheus Metrics (ADR-0029):
- layer3_agent_hire_latency_ms{agent_type, warmup_type="cold|warm"}
- layer3_agent_fire_latency_ms{agent_type}
- layer3_agent_crash_rate{agent_type}
- layer3_idle_pool_hit_rate{}
- layer3_idle_pool_size{agent_type}

Structured Logs:
```python
logger.info(
    "agent_hired",
    agent_id=agent_id,
    agent_type=agent_type,
    latency_ms=latency,
    warmup_type="cold",
    accelerator="NPU",
    trace_id=trace_id
)
```

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
