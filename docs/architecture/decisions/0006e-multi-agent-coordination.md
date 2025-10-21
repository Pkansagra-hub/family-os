# ADR-0006e: Multi-Agent Parallel Coordination (Q2 2025 Post-MVP)

**Status:** Accepted ✅
**Parent ADR:** [ADR-0006: 3-Phase Orchestration with Contract Net Protocol](0006-3phase-orchestration-contract-net.md)
**Last Updated:** 2025-01-30
**Deciders:** K1 Architecture Team
**Impact:** Core Kernel (Layer 1)
**Completion:** 0% → Design Complete (implementation post-MVP Q2 2025)

---

## Executive Summary

This sub-ADR defines **multi-agent parallel coordination** for Phase 3 (Execution) — an optimization where **multiple agents execute different waves concurrently** instead of a single agent executing the entire plan. This enables complex tasks to leverage specialized agents in parallel, reducing total turn latency.

**Core Multi-Agent Model:**

```
Wave 1: Concierge NLU (Agent A) + Planner planning (Agent B) → Parallel (independent)
    ↓ (both complete)
Wave 2: Tool Runner execution (Agent C) → Sequential (depends on Wave 1)
    ↓
Final result aggregation
```

**Performance Target:** TBD (latency reduction for complex tasks, estimated 20-40% speedup for multi-agent plans).

**Research Foundation:** Multi-agent systems (MAS) — Coordinated task execution with agent specialization.

**Status:** Design complete, implementation post-MVP (Q2 2025).

---

## Context

### Problem Statement

In the current 3-phase orchestration (ADR-0006a-c), **a single agent executes the entire plan**:

```
Phase 1: Negotiation → Select best agent (e.g., Concierge)
Phase 2: Selection → Award task to Concierge
Phase 3: Execution → Concierge executes all steps (Waves 1-N)
```

For complex tasks with **specialized steps**, this is inefficient:

**Example: "Plan trip to Italy and book flights"**

```
Wave 1:
    - Step 1: NLU parsing (best agent: Concierge)
    - Step 2: Itinerary planning (best agent: Planner)

Wave 2:
    - Step 3: Flight search (best agent: Tool Runner)
    - Step 4: Hotel search (best agent: Tool Runner)

Current: Concierge executes all 4 steps (suboptimal, not specialized)
Optimized: Concierge (Step 1) + Planner (Step 2) parallel, then Tool Runner (Steps 3-4)
```

**Multi-agent parallel coordination** solves this by:

1. **Wave independence analysis:** Determine if steps in a wave can be assigned to different agents
2. **Multi-agent wave assignment:** Negotiate per wave (not per task)
3. **Agent synchronization:** Coordinate multiple agents concurrently
4. **Multi-agent result aggregation:** Merge results from multiple agents

---

### Parent ADR Context

From [ADR-0006: 3-Phase Orchestration](0006-3phase-orchestration-contract-net.md) and [ADR-0006c: Parallel DAG Execution](0006c-parallel-dag-execution.md):

**Current Model (Single Agent):**

- Phase 1: Negotiate entire task → Select 1 winner
- Phase 2: Winner executes all waves
- Phase 3: Sequential wave execution per agent

**Multi-Agent Model (This Sub-ADR):**

- Phase 1: Negotiate **per wave** → Select N winners (1 per wave or step)
- Phase 2: Multiple agents execute waves concurrently (if independent)
- Phase 3: Synchronize + aggregate results

**Orchestrator Role:**

- Analyze wave independence (shared resources/data?)
- Assign agents per wave or per step
- Synchronize multiple agents (rendezvous points)
- Aggregate multi-agent results

---

### Implementation Status

**Multi-Agent Coordination:** 0% complete (design only, post-MVP)

**What's Needed:**

- ❌ Wave independence analysis (detect shared resources/data)
- ❌ Multi-agent wave assignment (per-wave negotiation)
- ❌ Agent synchronization primitives (rendezvous points, barriers)
- ❌ Multi-agent result aggregation (merge step results)
- ❌ Multi-agent compensation coordination (Saga with multiple agents)

---

## Research Foundation

### Multi-Agent Systems (MAS)

**Origin:** Multi-agent systems research (1980s-1990s) — Coordinated task execution with autonomous agents

**Core Concepts:**

1. **Agent specialization:** Agents have different capabilities/expertise
2. **Task decomposition:** Complex task → sub-tasks assigned to specialized agents
3. **Coordination protocols:** Agents synchronize via messages (e.g., Contract Net)
4. **Result aggregation:** Merge results from multiple agents into unified output

---

### Industry Implementations Review

| System          | Multi-Agent | Wave-Level Assignment | Agent Synchronization | Result Aggregation |
| --------------- | ----------- | --------------------- | --------------------- | ------------------ |
| **K1**          | ✅ Yes (design) | ✅ Yes (design)    | ✅ Yes (design)       | ✅ Yes (design)    |
| CrewAI          | ⚠️ Limited  | ❌ No                 | ⚠️ Manager-based      | ⚠️ Manager-based   |
| AutoGPT         | ❌ No       | N/A                   | N/A                   | N/A                |
| LangGraph       | ⚠️ Limited  | ❌ No (static edges)  | ❌ No                 | ⚠️ Manual          |
| Temporal        | ✅ Yes      | ✅ Yes (activities)   | ✅ Yes (workflows)    | ✅ Yes             |

**K1's differentiation:** Wave-level multi-agent assignment with Contract Net negotiation per wave (dynamic, runtime selection).

---

## Decision

### Overview

Implement **multi-agent parallel coordination** for Phase 3 (Execution) as a post-MVP optimization:

```
┌─────────────────────────────────────────┐
│ Plan (Planner Agent)                    │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ 1. Wave Independence Analysis           │  Detect shared resources/data per wave
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ 2. Multi-Agent Wave Assignment          │  Negotiate per wave (Contract Net)
│    - Wave 1: Concierge + Planner        │
│    - Wave 2: Tool Runner                │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ 3. Parallel Execution (Multi-Agent)     │  Multiple agents execute concurrently
│    - Synchronization (rendezvous)       │
│    - Barrier (await all agents)         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ 4. Multi-Agent Result Aggregation       │  Merge results into unified state
└─────────────────────────────────────────┘
```

**Key Design Choices:**

1. **Wave independence analysis:** Check if wave steps share resources/data
2. **Multi-agent wave assignment:** Per-wave Contract Net negotiation (Phase 1)
3. **Agent synchronization:** Rendezvous points + barriers for dependent waves
4. **Multi-agent result aggregation:** Merge step results from multiple agents

---

### 1. Wave Independence Analysis

**Determine if steps in a wave can be assigned to different agents:**

```python
class WaveIndependenceAnalyzer:
    """
    Analyze wave independence for multi-agent assignment.
    """
    def analyze_wave_independence(self, wave: List[PlanStep]) -> bool:
        """
        Check if steps in wave are independent (no shared resources/data).

        Returns:
            independent: True if wave can be assigned to multiple agents
        """
        # Check 1: Shared resources (e.g., same external API)
        tools = set(step.tool for step in wave)
        if len(tools) < len(wave):
            # Some steps share same tool (potential resource contention)
            return False

        # Check 2: Shared session state (e.g., updating same SessionState section)
        # (TBD: SessionState write conflict detection)

        # Check 3: Shared model instance (e.g., same LLM model)
        # (TBD: Model Hub resource contention)

        # If all checks pass, wave is independent
        return True
```

**Example:**

**Wave 1:**

```
Step 1: NLU parsing (tool: nlu_api, model: gpt-4)
Step 2: Itinerary planning (tool: planning_api, model: claude-3)
```

**Independence check:**

- Tools: `{nlu_api, planning_api}` → Different tools ✅
- Models: `{gpt-4, claude-3}` → Different models ✅
- **Result: Independent** → Can assign to 2 different agents

---

### 2. Multi-Agent Wave Assignment

**Negotiate per wave instead of per task:**

```python
async def execute_plan_multi_agent(self, plan: Plan) -> Dict[str, Any]:
    """
    Execute plan with multi-agent coordination.
    """
    dag = DAG(plan)
    waves = dag.compute_waves()

    for wave_num, wave_step_ids in enumerate(waves, start=1):
        wave_steps = [dag.nodes[step_id].step for step_id in wave_step_ids]

        # Check wave independence
        is_independent = self.analyzer.analyze_wave_independence(wave_steps)

        if is_independent and len(wave_steps) > 1:
            # Multi-agent wave: Negotiate per step
            logger.info(
                "multi_agent_wave",
                wave_num=wave_num,
                step_count=len(wave_steps)
            )

            # Phase 1: Negotiate per step (parallel)
            agent_assignments = await self._negotiate_multi_agent_wave(wave_steps, plan.trace_id)

            # Phase 3: Execute with multiple agents (parallel)
            wave_results = await self._execute_multi_agent_wave(agent_assignments, wave_steps, plan.trace_id)

        else:
            # Single-agent wave: Use existing logic (ADR-0006c)
            logger.info(
                "single_agent_wave",
                wave_num=wave_num,
                step_count=len(wave_steps)
            )

            agent_id = self.current_agent_id  # Use already-assigned agent
            wave_results = await self._execute_wave(wave_steps, agent_id, plan.trace_id)

        # Aggregate results
        for step_id, result in zip(wave_step_ids, wave_results):
            self.step_results[step_id] = result

    return self.step_results
```

---

**Per-Step Negotiation:**

```python
async def _negotiate_multi_agent_wave(
    self,
    wave_steps: List[PlanStep],
    trace_id: str
) -> Dict[str, str]:
    """
    Negotiate agents for each step in wave (parallel).

    Returns:
        agent_assignments: Dict[step_id → agent_id]
    """
    # Create TaskAnnouncement per step
    tasks = []
    for step in wave_steps:
        task = TaskAnnouncement(
            task_id=step.step_id,
            trace_id=trace_id,
            task_type=step.action,
            intent=step.action,
            parameters=step.parameters,
            required_tools=[step.tool],
            required_models=[],  # TBD: Extract from step
            required_domain=None,
            deadline_ms=2000,
            announcement_time=time.time(),
            session_id=self.session_id,
            turn_number=self.turn_number,
            context_summary=None
        )
        tasks.append((step.step_id, task))

    # Negotiate all steps in parallel (Phase 1 per step)
    agent_assignments = {}

    negotiation_tasks = [
        self.orchestrator.negotiate(task)  # Returns List[Proposal]
        for _, task in tasks
    ]

    proposals_per_step = await asyncio.gather(*negotiation_tasks)

    # Select winner per step (Phase 2 per step)
    for (step_id, task), proposals in zip(tasks, proposals_per_step):
        if not proposals:
            raise ValueError(f"No proposals for step {step_id}")

        winner = await self.orchestrator.select_and_assign(proposals, task)
        agent_assignments[step_id] = winner.agent_id

    logger.info(
        "multi_agent_assignments",
        assignments=agent_assignments
    )

    return agent_assignments
```

---

### 3. Agent Synchronization (Rendezvous)

**Synchronize multiple agents executing same wave:**

```python
async def _execute_multi_agent_wave(
    self,
    agent_assignments: Dict[str, str],
    wave_steps: List[PlanStep],
    trace_id: str
) -> List[Any]:
    """
    Execute wave with multiple agents (parallel).

    Synchronization:
        - All agents start wave concurrently
        - Barrier: await all agents complete
    """
    # Create execution tasks per agent
    execution_tasks = []

    for step in wave_steps:
        agent_id = agent_assignments[step.step_id]
        task = self._execute_step(step, agent_id, trace_id)
        execution_tasks.append((step.step_id, task))

    # Barrier: await all agents (parallel execution)
    results = await asyncio.gather(*[task for _, task in execution_tasks], return_exceptions=True)

    # Check for errors
    for (step_id, _), result in zip(execution_tasks, results):
        if isinstance(result, Exception):
            logger.error("multi_agent_step_failed", step_id=step_id, error=str(result))
            # Trigger Saga compensation (multi-agent)
            await self._compensate_saga_multi_agent(agent_assignments)
            raise result

    return results
```

---

### 4. Multi-Agent Result Aggregation

**Merge results from multiple agents:**

```python
def _aggregate_multi_agent_results(
    self,
    step_ids: List[str],
    results: List[Any]
) -> Dict[str, Any]:
    """
    Aggregate results from multiple agents into unified step_results.

    Args:
        step_ids: List of step_ids executed by different agents
        results: List of results (same order as step_ids)

    Returns:
        aggregated: Dict[step_id → result]
    """
    aggregated = {}

    for step_id, result in zip(step_ids, results):
        aggregated[step_id] = result

    logger.info(
        "multi_agent_aggregation",
        step_count=len(step_ids),
        result_keys=list(aggregated.keys())
    )

    return aggregated
```

---

### 5. Multi-Agent Saga Compensation

**Compensate with multiple agents:**

```python
async def _compensate_saga_multi_agent(
    self,
    agent_assignments: Dict[str, str]
) -> None:
    """
    Saga compensation with multiple agents.

    LIFO unwinding (reverse order), but multiple agents execute compensation concurrently.
    """
    # Reverse order (LIFO)
    compensation_tasks = []

    for step in reversed(self.completed_steps):
        if step.compensation_action:
            agent_id = agent_assignments.get(step.step_id, self.current_agent_id)

            task = self._execute_compensation(
                step=step,
                agent_id=agent_id,
                parameters=self._resolve_dependencies(step.compensation_parameters),
                timeout_ms=3000
            )

            compensation_tasks.append((step.step_id, task))

    # Execute all compensations in parallel (best-effort)
    results = await asyncio.gather(*[task for _, task in compensation_tasks], return_exceptions=True)

    # Log errors
    for (step_id, _), result in zip(compensation_tasks, results):
        if isinstance(result, Exception):
            logger.error("multi_agent_compensation_failed", step_id=step_id, error=str(result))
```

---

## Performance Analysis

### Latency Budget

**Multi-Agent Target:** 20-40% latency reduction for complex tasks

**Example (Complex Task: "Plan trip + book flights + book hotels"):**

**Single-Agent Model:**

```
Wave 1: NLU (300ms) + Planning (500ms) = 800ms (sequential, same agent)
Wave 2: Flight search (600ms) + Hotel search (700ms) = 1300ms (sequential, same agent)
Total: 2100ms
```

**Multi-Agent Model:**

```
Wave 1: NLU (300ms, Agent A) || Planning (500ms, Agent B) = 500ms (parallel, max)
Wave 2: Flight search (600ms, Agent C) || Hotel search (700ms, Agent D) = 700ms (parallel, max)
Total: 1200ms (43% speedup)
```

**Speedup:** 2100ms → 1200ms = **43% latency reduction**

---

### Coordination Overhead

**Additional latency from multi-agent coordination:**

| Component                     | Overhead | Notes                                      |
| ----------------------------- | -------- | ------------------------------------------ |
| Wave independence analysis    | <5ms     | O(N) checks per wave                       |
| Per-step negotiation          | +50ms    | Phase 1 per step (parallel, not serialized)|
| Agent synchronization         | <5ms     | Barrier overhead (asyncio.gather)          |
| Result aggregation            | <5ms     | Dict merge                                 |
| **Total Overhead**            | **~65ms**| Acceptable for 20-40% speedup              |

---

## Consequences

### Positive

✅ **20-40% latency reduction:** For complex multi-agent tasks with wave independence
✅ **Agent specialization:** Leverage best agent per step (NLU → Concierge, Planning → Planner)
✅ **Parallel wave execution:** Multiple agents execute waves concurrently
✅ **Contract Net per step:** Dynamic agent selection at wave level (not task level)
✅ **Multi-agent Saga:** Compensation works with multiple agents

### Negative

⚠️ **Coordination complexity:** Wave independence analysis + multi-agent synchronization adds complexity
⚠️ **Overhead:** +65ms coordination overhead (acceptable for long tasks, not short tasks)
⚠️ **Wave independence detection:** Heuristic-based (shared tools/models), may miss edge cases
⚠️ **Post-MVP:** Not critical for MVP, delayed to Q2 2025

### Neutral

➖ **Negotiation per wave:** More negotiation rounds (per-step vs per-task), but parallelized
➖ **Multi-agent compensation:** More complex Saga unwinding, but agents handle compensation independently

---

## Implementation Roadmap

### Phase 1: Wave Independence Analysis (NOT STARTED ⏳)

- [ ] WaveIndependenceAnalyzer class
- [ ] Shared tool detection
- [ ] Shared model detection
- [ ] SessionState conflict detection (TBD)

**Estimated effort:** 2 days (analysis + tests)
**Target:** Q2 2025

---

### Phase 2: Multi-Agent Wave Assignment (NOT STARTED ⏳)

- [ ] Per-step TaskAnnouncement creation
- [ ] Parallel negotiation (Phase 1 per step)
- [ ] Per-step winner selection (Phase 2 per step)
- [ ] Agent assignment tracking (step_id → agent_id)

**Estimated effort:** 3 days (negotiation + tests)
**Target:** Q2 2025

---

### Phase 3: Agent Synchronization (NOT STARTED ⏳)

- [ ] Multi-agent wave execution (asyncio.gather)
- [ ] Barrier synchronization (await all agents)
- [ ] Multi-agent error handling

**Estimated effort:** 2 days (sync + tests)
**Target:** Q2 2025

---

### Phase 4: Multi-Agent Result Aggregation (NOT STARTED ⏳)

- [ ] Result merging (Dict[step_id → result])
- [ ] Multi-agent state consistency checks

**Estimated effort:** 1 day (aggregation + tests)
**Target:** Q2 2025

---

### Phase 5: Multi-Agent Saga Compensation (NOT STARTED ⏳)

- [ ] Multi-agent compensation coordination
- [ ] Parallel compensation execution
- [ ] Multi-agent compensation metrics

**Estimated effort:** 2 days (Saga integration + tests)
**Target:** Q2 2025

---

## Cross-References

### Parent ADR

- **[ADR-0006: 3-Phase Orchestration with Contract Net Protocol](0006-3phase-orchestration-contract-net.md)** — Parent ADR defining 3 phases (Negotiation, Selection, Execution)

### Dependencies (Architecture)

- **[ADR-0006a: Contract Net Protocol Negotiation](0006a-contract-net-negotiation.md)** — Phase 1 (Negotiation), used per wave in multi-agent model
- **[ADR-0006b: Multi-Criteria Proposal Scoring](0006b-multi-criteria-scoring.md)** — Phase 2 (Selection), used per wave in multi-agent model
- **[ADR-0006c: Parallel DAG Execution Engine](0006c-parallel-dag-execution.md)** — Phase 3 (Execution), extended with multi-agent coordination
- **[ADR-0006d: Saga Pattern Integration](0006d-saga-pattern-integration.md)** — Saga compensation with multiple agents

### Diagrams

- **Architecture diagram:** `architecture_diagrams/k1_orchestrator_3phase.mmd`
  - Section: "Phase 3: Multi-Agent Coordination" (nodes: Wave Independence, Multi-Agent Assignment, Agent Synchronization, Result Aggregation)

### Code Locations

- **Wave independence analyzer:** `k1/orchestrator/wave_independence.py` (WaveIndependenceAnalyzer class)
- **Multi-agent execution:** `k1/orchestrator/multi_agent_execution.py` (`execute_plan_multi_agent()`)
- **Agent synchronization:** `k1/orchestrator/multi_agent_execution.py` (`_execute_multi_agent_wave()`)
- **Result aggregation:** `k1/orchestrator/multi_agent_execution.py` (`_aggregate_multi_agent_results()`)

---

## Appendix: Example Multi-Agent Scenarios

### Scenario 1: 2-Agent Wave (Independent Steps)

**Plan:**

```
Wave 1:
    - Step 1: NLU parsing (tool: nlu_api, agent: Concierge)
    - Step 2: Itinerary planning (tool: planning_api, agent: Planner)

Wave 2:
    - Step 3: Flight search (tool: flight_api, agent: Tool Runner)
```

**Execution:**

```
Wave 1: Concierge (Step 1, 300ms) || Planner (Step 2, 500ms) → 500ms (parallel, max)
Wave 2: Tool Runner (Step 3, 600ms) → 600ms
Total: 1100ms

Single-Agent: 300 + 500 + 600 = 1400ms
Speedup: 1400ms → 1100ms = 21% reduction
```

---

### Scenario 2: 4-Agent Wave (Highly Parallel)

**Plan:**

```
Wave 1:
    - Step 1: Search flights (agent: Tool Runner A)
    - Step 2: Search hotels (agent: Tool Runner B)
    - Step 3: Search restaurants (agent: Tool Runner C)
    - Step 4: Search activities (agent: Tool Runner D)
```

**Execution:**

```
Wave 1: All 4 agents execute concurrently (600ms, 700ms, 550ms, 650ms) → 700ms (max)

Single-Agent: 600 + 700 + 550 + 650 = 2500ms
Speedup: 2500ms → 700ms = 72% reduction
```

---

## Summary

This sub-ADR defines **multi-agent parallel coordination** for Phase 3 (Execution) as a post-MVP optimization, implementing:

1. **Wave independence analysis** (detect shared resources/data)
2. **Multi-agent wave assignment** (per-step Contract Net negotiation)
3. **Agent synchronization** (rendezvous points, barriers)
4. **Multi-agent result aggregation** (merge results from multiple agents)
5. **Multi-agent Saga compensation** (parallel compensation execution)

**Performance:** 20-40% latency reduction for complex multi-agent tasks, +65ms coordination overhead.

**Status:** Design complete, implementation post-MVP (Q2 2025).

---

**Document End**
