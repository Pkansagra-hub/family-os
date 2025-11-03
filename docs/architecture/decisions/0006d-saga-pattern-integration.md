---
adr_number: 0006d
title: Saga Pattern Integration for Phase 3 Error Recovery
status: ACCEPTED
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
- cost
- observability
- performance
- reliability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0006
- ADR-0006a
- ADR-0006b
- ADR-0006c
- ADR-0006d
- ADR-0008
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
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0006
  - ADR-0006a
  - ADR-0006b
  - ADR-0006c
  - ADR-0006d
  - ADR-0008
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


# ADR-0006d: Saga Pattern Integration for Phase 3 Error Recovery

**Status:** Accepted ✅
**Parent ADR:** [ADR-0006: 3-Phase Orchestration with Contract Net Protocol](0006-3phase-orchestration-contract-net.md)
**Last Updated:** 2025-01-30
**Deciders:** K1 Architecture Team
**Impact:** Core Kernel (Layer 1)
**Completion:** 0% → Design Complete (implementation pending Q1 2025)

---

## Executive Summary

This sub-ADR defines **Saga Pattern integration** into Phase 3 (Execution) for error recovery. When a step fails during DAG execution, the Orchestrator triggers **reverse-order compensation** (LIFO stack unwinding) to undo previously completed steps, ensuring system consistency.

**Core Compensation Model:**

```
Step 1 ✅ (compensation: cancel_search)
    ↓
Step 2 ✅ (compensation: cancel_reservation)
    ↓
Step 3 ❌ FAILS (compensation: n/a)
    ↓
Compensate Step 2 → cancel_reservation ✅
    ↓
Compensate Step 1 → cancel_search ✅
```

**Performance Target:** ~5s for 5-step plan compensation (1s per step), >90% compensation success rate.

**Research Foundation:** Saga Pattern (Garcia-Molina & Salem 1987) — Long-lived transactions with compensation-based recovery.

---

## Context

### Problem Statement

During DAG execution (Phase 3), **steps may fail** due to:

- **Agent crashes:** Agent terminates mid-execution
- **Tool errors:** External API returns error (e.g., booking API rejects reservation)
- **Timeouts:** Step exceeds deadline
- **LLM failures:** Model refuses to answer or returns invalid output

Without compensation, failed steps leave the system in an **inconsistent state**:

**Example:**

```
Step 1: Search restaurants ✅ (found 5 results)
Step 2: Book reservation ✅ (reservation confirmed, ID: 12345)
Step 3: Send email ❌ FAILS (email service down)

Result: Reservation booked but user not notified → BAD STATE
```

**Saga Pattern** solves this by defining **compensation actions** per step:

```
Step 1: Search restaurants (compensation: None — read-only)
Step 2: Book reservation (compensation: cancel_reservation)
Step 3: Send email (compensation: None — idempotent retry)

If Step 3 fails:
    1. Compensate Step 2 → cancel_reservation(ID: 12345) ✅
    2. (Step 1 has no compensation, skip)
    3. Return error to user
```

---

### Parent ADR Context

From [ADR-0006: 3-Phase Orchestration](0006-3phase-orchestration-contract-net.md) and [ADR-0006c: Parallel DAG Execution](0006c-parallel-dag-execution.md):

**Phase 3 (Execution):**

- DAG builder constructs dependency graph
- Wave computation groups independent steps
- Parallel execution (asyncio.gather + semaphore)
- **Error handling:** If step fails → **Saga compensation** (this sub-ADR)

**Orchestrator Role:**

- Track compensation actions per step
- Trigger reverse-order compensation on failure
- Continue best-effort compensation even if one fails

---

### Implementation Status

**Saga Integration:** 0% complete (design only)

**What's Needed:**

- ❌ Compensation action tracking per step
- ❌ Reverse-order compensation (LIFO stack unwinding)
- ❌ Best-effort compensation (continue on failure)
- ❌ Multi-agent compensation coordination
- ❌ Compensation timeout enforcement (3s default)
- ❌ Compensation retry logic (1 retry, then fail)

---

## Research Foundation

### Saga Pattern (Garcia-Molina & Salem 1987)

**Origin:** Garcia-Molina, H., & Salem, K. (1987). "Sagas." *ACM SIGMOD Record*, 16(3), 249-259.

**Core Concepts:**

1. **Long-lived transaction:** Multi-step transaction that may span seconds/minutes
2. **Compensation:** Each step has a compensating action to undo its effects
3. **LIFO unwinding:** Compensate in reverse order (Step N → N-1 → ... → 1)
4. **Best-effort:** Continue compensation even if one step fails

**Saga Guarantees:**

- **Atomicity:** Either all steps succeed, or all are compensated (eventual consistency)
- **Isolation:** No guarantees (other transactions may see intermediate states)
- **Durability:** Compensation persists state changes

---

### Industry Implementations Review

| System          | Saga Support | Compensation Order | Best-Effort | Multi-Agent |
| --------------- | ------------ | ------------------ | ----------- | ----------- |
| **K1**          | ✅ Yes       | ✅ LIFO            | ✅ Yes      | ✅ Yes      |
| Temporal        | ✅ Yes       | ✅ LIFO            | ✅ Yes      | ✅ Yes      |
| Apache Camel    | ✅ Yes       | ✅ LIFO            | ⚠️ Optional | ❌ No       |
| AWS Step Functions | ✅ Yes    | ✅ LIFO            | ⚠️ Optional | ❌ No       |
| LangGraph       | ❌ No        | N/A                | N/A         | N/A         |
| CrewAI          | ❌ No        | N/A                | N/A         | N/A         |

**K1's differentiation:** Integrated Saga pattern with multi-agent compensation (agents execute compensation actions).

---

## Decision

### Overview

Integrate **Saga Pattern** into Phase 3 (Execution) for error recovery:

```
┌─────────────────────────────────────────┐
│ DAG Execution (Phase 3)                 │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Step N Execution                        │
└────────────────┬────────────────────────┘
                 │ SUCCESS / FAIL
                 ├─────────────────────────┐
                 │ SUCCESS                 │ FAIL
                 ▼                         ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ Continue to Step N+1        │  │ 1. Collect Completed Steps  │
└─────────────────────────────┘  │ 2. Reverse Order (LIFO)     │
                                 │ 3. Compensate Each Step     │
                                 │ 4. Best-Effort (continue)   │
                                 └─────────────────────────────┘
```

**Key Design Choices:**

1. **Compensation action per step:** Defined in PlanStep (e.g., `cancel_reservation`)
2. **LIFO unwinding:** Compensate in reverse order (Stack.pop() semantics)
3. **Best-effort:** Continue compensation even if one step fails
4. **Multi-agent coordination:** Orchestrator triggers compensation, agent executes
5. **Timeout enforcement:** 3s default per compensation action

---

### 1. Compensation Action Tracking

**Enhanced PlanStep (from ADR-0006c):**

```python
@dataclass(frozen=True)
class PlanStep:
    """
    A single step in the plan (with compensation action).
    """
    step_id: str
    action: str
    tool: str
    parameters: Dict[str, Any]
    dependencies: List[str]
    compensation_action: Optional[str]  # Compensation tool/action (e.g., "cancel_reservation")
    compensation_parameters: Optional[Dict[str, Any]]  # Parameters for compensation
```

**Example Plan with Compensation:**

```python
plan = Plan(
    plan_id="plan_12345",
    steps=[
        PlanStep(
            step_id="step_1",
            action="Search restaurants",
            tool="search_api",
            parameters={"query": "Italian", "count": 5},
            dependencies=[],
            compensation_action=None,  # Read-only, no compensation needed
            compensation_parameters=None
        ),
        PlanStep(
            step_id="step_2",
            action="Book reservation",
            tool="booking_api",
            parameters={"restaurant_id": "{step_1.results[0].id}", "time": "19:00"},
            dependencies=["step_1"],
            compensation_action="cancel_reservation",  # Compensation: cancel booking
            compensation_parameters={"booking_id": "{step_2.booking_id}"}  # Variable from step_2 result
        ),
        PlanStep(
            step_id="step_3",
            action="Send confirmation email",
            tool="email_api",
            parameters={"to": "user@example.com", "body": "Reservation confirmed"},
            dependencies=["step_2"],
            compensation_action=None,  # Idempotent retry, no compensation
            compensation_parameters=None
        )
    ],
    trace_id="trace_67890"
)
```

---

### 2. Compensation Tracking During Execution

**Track completed steps for compensation:**

```python
class ExecutionEngine:
    """
    Execution engine with Saga compensation tracking.
    """
    def __init__(self, orchestrator, config):
        self.orchestrator = orchestrator
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_concurrency)
        self.step_results: Dict[str, Any] = {}  # step_id → result
        self.completed_steps: List[PlanStep] = []  # LIFO stack for compensation

    async def execute_plan(self, plan: Plan, agent_id: str) -> Dict[str, Any]:
        """
        Execute plan with Saga compensation on failure.
        """
        try:
            # Execute DAG waves (same as ADR-0006c)
            dag = DAG(plan)
            waves = dag.compute_waves()

            for wave_num, wave_step_ids in enumerate(waves, start=1):
                wave_tasks = [
                    self._execute_step(dag.nodes[step_id].step, agent_id, plan.trace_id)
                    for step_id in wave_step_ids
                ]

                wave_results = await asyncio.gather(*wave_tasks, return_exceptions=True)

                # Check for errors
                for step_id, result in zip(wave_step_ids, wave_results):
                    if isinstance(result, Exception):
                        logger.error(
                            "step_failed",
                            plan_id=plan.plan_id,
                            step_id=step_id,
                            error=str(result)
                        )

                        # Trigger Saga compensation
                        await self._compensate_saga(plan, agent_id)

                        # Re-raise error after compensation
                        raise result

                    # Track completed step for compensation
                    step = dag.nodes[step_id].step
                    if step.compensation_action:
                        self.completed_steps.append(step)

                    # Store result
                    self.step_results[step_id] = result

            return self.step_results

        except Exception as e:
            logger.error("execution_failed", plan_id=plan.plan_id, error=str(e))
            raise
```

---

### 3. Reverse-Order Compensation (LIFO)

**Compensate completed steps in reverse order:**

```python
async def _compensate_saga(self, plan: Plan, agent_id: str):
    """
    Compensate completed steps in reverse order (LIFO stack unwinding).

    Best-effort: Continue compensation even if one fails.
    """
    start_time = time.perf_counter()

    logger.warning(
        "saga_compensation_start",
        plan_id=plan.plan_id,
        step_count=len(self.completed_steps),
        trace_id=plan.trace_id
    )

    compensation_results = []

    # Reverse order (LIFO)
    for step in reversed(self.completed_steps):
        try:
            compensation_start = time.perf_counter()

            logger.info(
                "compensation_start",
                plan_id=plan.plan_id,
                step_id=step.step_id,
                compensation_action=step.compensation_action
            )

            # Resolve compensation parameters (variable substitution)
            resolved_params = self._resolve_dependencies(step.compensation_parameters)

            # Execute compensation action
            compensation_result = await self._execute_compensation(
                step=step,
                agent_id=agent_id,
                parameters=resolved_params,
                timeout_ms=3000  # 3s default timeout
            )

            compensation_duration_ms = (time.perf_counter() - compensation_start) * 1000

            logger.info(
                "compensation_success",
                plan_id=plan.plan_id,
                step_id=step.step_id,
                duration_ms=compensation_duration_ms
            )

            compensation_results.append({
                "step_id": step.step_id,
                "status": "SUCCESS",
                "duration_ms": compensation_duration_ms
            })

            compensation_success.labels(action=step.compensation_action).inc()

        except Exception as e:
            # Best-effort: Log error but continue compensation
            logger.error(
                "compensation_failed",
                plan_id=plan.plan_id,
                step_id=step.step_id,
                error=str(e)
            )

            compensation_results.append({
                "step_id": step.step_id,
                "status": "FAILED",
                "error": str(e)
            })

            compensation_failures.labels(action=step.compensation_action).inc()

    total_duration_ms = (time.perf_counter() - start_time) * 1000

    logger.warning(
        "saga_compensation_complete",
        plan_id=plan.plan_id,
        duration_ms=total_duration_ms,
        success_count=sum(1 for r in compensation_results if r["status"] == "SUCCESS"),
        failure_count=sum(1 for r in compensation_results if r["status"] == "FAILED")
    )

    saga_compensation_duration_ms.observe(total_duration_ms)
```

---

### 4. Compensation Execution (Multi-Agent)

**Send CompensationExecution message to agent:**

```python
@dataclass(frozen=True)
class CompensationExecution:
    """
    CompensationExecution message - sent by Orchestrator to agent for compensation.
    """
    step_id: str                     # Original step ID
    compensation_action: str         # Compensation tool/action
    parameters: Dict[str, Any]       # Resolved compensation parameters
    timeout_ms: int                  # Compensation timeout (3000ms default)
    trace_id: str


async def _execute_compensation(
    self,
    step: PlanStep,
    agent_id: str,
    parameters: Dict[str, Any],
    timeout_ms: int
) -> Any:
    """
    Execute compensation action via agent.

    Args:
        step: Original PlanStep with compensation_action
        agent_id: Agent ID to execute compensation
        parameters: Resolved compensation parameters
        timeout_ms: Compensation timeout (3000ms default)

    Returns:
        compensation_result: Result from agent

    Raises:
        TimeoutError: If compensation exceeds timeout
        Exception: If agent returns error
    """
    # Send CompensationExecution message to agent
    compensation_msg = CompensationExecution(
        step_id=step.step_id,
        compensation_action=step.compensation_action,
        parameters=parameters,
        timeout_ms=timeout_ms,
        trace_id=self.plan.trace_id
    )

    agent = await self.orchestrator.agent_registry.get_agent(agent_id)
    await agent.mailbox.send(compensation_msg)

    # Wait for CompensationResult from agent (with timeout)
    try:
        result = await asyncio.wait_for(
            self._wait_for_compensation_result(step.step_id),
            timeout=timeout_ms / 1000.0
        )
        return result

    except asyncio.TimeoutError:
        logger.error(
            "compensation_timeout",
            step_id=step.step_id,
            timeout_ms=timeout_ms
        )
        raise TimeoutError(f"Compensation timeout for step {step.step_id}")
```

---

### 5. Compensation Retry Logic

**Retry compensation once on failure:**

```python
async def _execute_compensation_with_retry(
    self,
    step: PlanStep,
    agent_id: str,
    parameters: Dict[str, Any],
    timeout_ms: int
) -> Any:
    """
    Execute compensation with 1 retry on failure.
    """
    for attempt in range(2):  # 2 attempts (initial + 1 retry)
        try:
            result = await self._execute_compensation(step, agent_id, parameters, timeout_ms)

            if attempt > 0:
                # Retry succeeded
                compensation_retries.labels(action=step.compensation_action, attempt=attempt).inc()

            return result

        except Exception as e:
            if attempt == 0:
                # First attempt failed, retry
                logger.warning(
                    "compensation_retry",
                    step_id=step.step_id,
                    attempt=attempt + 1,
                    error=str(e)
                )
                await asyncio.sleep(0.5)  # Wait 500ms before retry
            else:
                # Second attempt failed, give up
                logger.error(
                    "compensation_failed_after_retry",
                    step_id=step.step_id,
                    error=str(e)
                )
                raise
```

---

## Performance Analysis

### Latency Budget

**Compensation Target:** ~5s for 5-step plan (1s per compensation action)

**Breakdown:**

| Step              | Compensation Action    | Latency | Notes                      |
| ----------------- | ---------------------- | ------- | -------------------------- |
| Step 5 (failed)   | None                   | 0ms     | No compensation            |
| Step 4            | cancel_booking         | 800ms   | API call to booking service|
| Step 3            | refund_payment         | 1200ms  | API call to payment gateway|
| Step 2            | release_inventory      | 600ms   | Database update            |
| Step 1            | None                   | 0ms     | Read-only, no compensation |
| **Total**         |                        | **2600ms** | Well within 5s budget   |

**Performance Monitoring:**

```python
saga_compensation_duration_ms = Histogram(
    'orchestrator_saga_compensation_duration_ms',
    'Saga compensation total latency (ms)',
    buckets=[100, 500, 1000, 2000, 5000, 10000]
)

compensation_step_duration_ms = Histogram(
    'orchestrator_compensation_step_duration_ms',
    'Per-step compensation latency (ms)',
    ['action'],
    buckets=[100, 500, 1000, 2000, 3000]
)
```

---

### Success Rate

**Target:** >90% compensation success rate

**Failure Modes:**

| Failure Mode           | Probability | Mitigation                              |
| ---------------------- | ----------- | --------------------------------------- |
| Agent crash            | ~1%         | Retry with different agent              |
| Compensation timeout   | ~3%         | 3s default timeout, retry once          |
| External API error     | ~5%         | Best-effort (log error, continue)       |
| Invalid parameters     | ~1%         | Validate before compensation            |

**Expected Success Rate:** ~90% (1 - 0.01 - 0.03 - 0.05 - 0.01)

**Monitoring:**

```python
compensation_success = Counter(
    'orchestrator_compensation_success_total',
    'Total successful compensations',
    ['action']
)

compensation_failures = Counter(
    'orchestrator_compensation_failures_total',
    'Total failed compensations',
    ['action', 'reason']
)

compensation_retries = Counter(
    'orchestrator_compensation_retries_total',
    'Total compensation retries',
    ['action', 'attempt']
)
```

---

## Consequences

### Positive

✅ **Consistency:** Failed executions leave system in consistent state (all compensated)
✅ **Best-effort:** Continue compensation even if one fails (robustness)
✅ **LIFO order:** Reverse-order unwinding ensures correct compensation sequence
✅ **Multi-agent:** Agents execute compensation actions (distributed)
✅ **Retry logic:** 1 retry per compensation increases success rate
✅ **Research-backed:** Saga Pattern (Garcia-Molina 1987) proven for long-lived transactions

### Negative

⚠️ **Compensation latency:** 1s per step adds overhead (~5s for 5-step plan)
⚠️ **Best-effort only:** No guarantee all compensations succeed (eventual consistency)
⚠️ **Compensation complexity:** Each step must define compensation action (design overhead)
⚠️ **External API dependency:** Compensation success depends on external APIs (booking, payment, etc.)

### Neutral

➖ **LIFO semantics:** Reverse order is correct for most cases, but may not suit all scenarios
➖ **Timeout enforcement:** 3s default may be too short for some compensation actions
➖ **No partial compensation:** All-or-nothing (either full compensation or best-effort)

---

## Implementation Roadmap

### Phase 1: Core Compensation (NOT STARTED ⏳)

- [ ] CompensationExecution message
- [ ] Compensation tracking (completed_steps stack)
- [ ] LIFO unwinding logic
- [ ] Best-effort compensation (continue on failure)

**Estimated effort:** 2-3 days (implement + test)

---

### Phase 2: Multi-Agent Coordination (NOT STARTED ⏳)

- [ ] Agent-side compensation execution
- [ ] CompensationResult message
- [ ] Timeout enforcement (3s default)
- [ ] Agent crash handling

**Estimated effort:** 2 days (agent integration + tests)

---

### Phase 3: Retry Logic (NOT STARTED ⏳)

- [ ] 1 retry per compensation
- [ ] 500ms delay between retries
- [ ] Retry metrics

**Estimated effort:** 1 day (retry + metrics)

---

### Phase 4: Observability & Testing (NOT STARTED ⏳)

- [ ] Prometheus metrics (saga_compensation_duration_ms, compensation_success, compensation_failures)
- [ ] OpenTelemetry traces (full compensation span)
- [ ] WARD integration tests (compensation scenarios)

**Estimated effort:** 2 days (tests + metrics)

---

## Cross-References

### Parent ADR

- **[ADR-0006: 3-Phase Orchestration with Contract Net Protocol](0006-3phase-orchestration-contract-net.md)** — Parent ADR defining 3 phases (Negotiation, Selection, Execution)

### Dependencies (Architecture)

- **[ADR-0006c: Parallel DAG Execution Engine](0006c-parallel-dag-execution.md)** — Phase 3 (Execution), triggers Saga compensation on failure
- **[ADR-0008: Saga Pattern for Error Recovery](0008-saga-pattern-error-recovery.md)** — Parent ADR for Saga pattern architecture

### Related Sub-ADRs (Same Parent)

- **[ADR-0006a: Contract Net Protocol Negotiation](0006a-contract-net-negotiation.md)** — Phase 1 (Negotiation)
- **[ADR-0006b: Multi-Criteria Proposal Scoring](0006b-multi-criteria-scoring.md)** — Phase 2 (Selection)

### Diagrams

- **Architecture diagram:** `architecture_diagrams/k1_orchestrator_3phase.mmd`
  - Section: "Phase 3: Execution - Saga Compensation" (nodes: Compensation Tracking, LIFO Unwinding, Multi-Agent Compensation)

### Code Locations

- **Compensation engine:** `k1/orchestrator/saga_compensation.py` (`_compensate_saga()`, `_execute_compensation()`)
- **Execution engine:** `k1/orchestrator/execution_engine.py` (integrated with DAG execution)
- **Messages:** `k1/orchestrator/messages.py` (CompensationExecution, CompensationResult)

---

## Appendix: Example Compensation Scenarios

### Scenario 1: Full Compensation Success

**Plan:**

```
Step 1: Search restaurants ✅ (no compensation)
Step 2: Book reservation ✅ (compensation: cancel_reservation)
Step 3: Send email ❌ FAILS
```

**Compensation:**

```
Step 3 failed → Trigger Saga compensation
    ↓
Compensate Step 2 → cancel_reservation(booking_id: 12345) ✅ (800ms)
    ↓
(Step 1 has no compensation, skip)
    ↓
Saga compensation complete (total: 800ms)
```

**Result:** Reservation canceled, user notified of failure.

---

### Scenario 2: Best-Effort Compensation (One Fails)

**Plan:**

```
Step 1: Reserve inventory ✅ (compensation: release_inventory)
Step 2: Charge payment ✅ (compensation: refund_payment)
Step 3: Ship order ❌ FAILS
```

**Compensation:**

```
Step 3 failed → Trigger Saga compensation
    ↓
Compensate Step 2 → refund_payment(payment_id: 67890) ❌ FAILS (payment gateway down)
    ↓
(Best-effort: Continue compensation despite failure)
    ↓
Compensate Step 1 → release_inventory(item_id: 123) ✅ (600ms)
    ↓
Saga compensation complete (total: 1200ms, 1 failure, 1 success)
```

**Result:** Inventory released, payment refund FAILED (manual intervention needed).

---

## Summary

This sub-ADR defines **Saga Pattern integration** for Phase 3 (Execution) error recovery, implementing:

1. **Compensation action tracking** per step
2. **LIFO unwinding** (reverse-order compensation)
3. **Best-effort compensation** (continue on failure)
4. **Multi-agent coordination** (Orchestrator triggers, agent executes)
5. **Retry logic** (1 retry per compensation, 500ms delay)

**Performance:** ~5s for 5-step plan compensation (1s per step), >90% success rate target.

**Status:** Design complete, implementation pending Q1 2025.

---

**Document End**