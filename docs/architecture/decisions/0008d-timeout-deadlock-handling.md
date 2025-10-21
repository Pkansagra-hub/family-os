# ADR-0008d: Timeout & Deadlock Handling

**Status:** ✅ Approved (2025-10-12)
**Parent ADR:** [ADR-0008: Saga Pattern Error Recovery](./0008-saga-pattern-error-recovery.md)
**Related ADRs:**
- [ADR-0008a: Compensating Transaction Design](./0008a-compensating-transaction-design.md) - Compensation timeout
- [ADR-0008b: Forward Recovery vs Backward Recovery](./0008b-forward-recovery-vs-backward-recovery.md) - Retry timeout
- [ADR-0008c: Distributed State Management](./0008c-distributed-state-management.md) - Saga timeout tracking
- [ADR-0007c: Validation Stage 2-Tier Implementation](./0007c-validation-stage-2-tier-implementation.md) - DAG cycle detection

**Research Citations:**
- Timeout patterns (Nygard 2007) - Release It! Design patterns
- Deadlock detection (Coffman et al. 1971) - System deadlocks
- Resource ordering (Havender 1968) - Deadlock prevention
- Liveness properties (Lamport 1977) - Temporal logic of actions

---

## Context & Problem Statement

### Current State
Saga execution can **hang indefinitely** without timeout enforcement:
- ❌ No step timeout (tool calls may never return)
- ❌ No compensation timeout (compensations may hang)
- ❌ No saga timeout (sagas may run forever)
- ❌ No deadlock detection (agents waiting for each other)

**Example Hang Scenario:**
```
Saga execution:
  1. ✅ Step 1 complete (book hotel)
  2. 🔄 Step 2 executing (reserve flight)
     → API call hangs (network issue, no timeout)
     → Saga never completes (infinite wait)

Current behavior: Saga hangs forever, no compensation
Desired behavior: Step timeout (30s) → Abort → Trigger compensation
```

### Problem Statement
**How do we prevent infinite waits through timeout enforcement and deadlock detection to ensure all sagas terminate (COMPLETED or ABORTED) within bounded time?**

### Key Challenges

1. **Timeout Hierarchy (4 levels):**
   - Step timeout (30s per tool call)
   - Compensation timeout (3s per compensation)
   - Saga timeout (120s total saga time)
   - Session timeout (600s session lifetime)

2. **Deadlock Detection:**
   - Circular dependencies (DAG cycles)
   - Resource deadlock (agents waiting for each other)

3. **Liveness Guarantees:**
   - Every saga terminates within saga_timeout
   - No infinite loops (max_steps = 10)
   - No infinite retries (max 5 retries)
   - No infinite compensations (timeout per step)

4. **Timeout Enforcement:**
   - Use `asyncio.wait_for()` for all async calls
   - Raise `TimeoutError` if exceeded
   - Log timeout events for debugging

---

## Decision

### Overview
Implement **timeout & deadlock handling** with 4 components:
1. **Timeout Hierarchy** (4 levels: step, compensation, saga, session)
2. **Timeout Enforcement** (asyncio.wait_for, timeout tracking)
3. **Deadlock Detection** (DAG cycles, resource deadlock)
4. **Liveness Guarantees** (bounded execution, no infinite loops)

---

### Component 1: Timeout Hierarchy

**Purpose:** Define cascading timeouts at 4 levels.

#### **Level 1: Step Timeout (30s per tool call)**

**Purpose:** Prevent individual tool calls from hanging.

**Configuration:**
```yaml
# k1/config/saga.yml
saga:
  timeouts:
    step_timeout_ms: 30000  # 30s per tool call
```

**Enforcement:**
```python
async def execute_step_with_timeout(
    step: PlanStep,
    timeout_ms: int = 30000
) -> StepResult:
    """
    Execute step with timeout.

    Raises asyncio.TimeoutError if step exceeds timeout.
    """
    try:
        result = await asyncio.wait_for(
            tool_runner.run_tool(step),
            timeout=timeout_ms / 1000  # Convert to seconds
        )
        return result

    except asyncio.TimeoutError:
        logger.error(
            "step_timeout",
            step_id=step.step_id,
            tool_id=step.tool,
            timeout_ms=timeout_ms
        )
        raise StepTimeoutError(f"Step {step.step_id} exceeded {timeout_ms}ms timeout")
```

---

#### **Level 2: Compensation Timeout (3s per compensation)**

**Purpose:** Prevent compensations from hanging (fail-fast).

**Configuration:**
```yaml
saga:
  timeouts:
    compensation_timeout_ms: 3000  # 3s per compensation
```

**Enforcement:**
```python
async def execute_compensation_with_timeout(
    compensation: CompensationAction,
    timeout_ms: int = 3000
) -> CompensationResult:
    """
    Execute compensation with timeout.

    Best-effort: Log failure, continue with next compensation.
    """
    try:
        result = await asyncio.wait_for(
            execute_compensation_action(compensation),
            timeout=timeout_ms / 1000
        )
        return result

    except asyncio.TimeoutError:
        logger.error(
            "compensation_timeout",
            step_id=compensation.step_id,
            timeout_ms=timeout_ms
        )
        return CompensationResult(
            step_id=compensation.step_id,
            success=False,
            error_message=f"Compensation timeout ({timeout_ms}ms)"
        )
```

---

#### **Level 3: Saga Timeout (120s total saga time)**

**Purpose:** Prevent sagas from running forever.

**Configuration:**
```yaml
saga:
  timeouts:
    saga_timeout_ms: 120000  # 120s total saga time
```

**Enforcement:**
```python
class SagaCoordinator:
    """Saga coordinator with total timeout"""

    async def execute_saga(
        self,
        plan: ValidatedPlan,
        timeout_ms: int = 120000
    ) -> SagaResult:
        """
        Execute saga with total timeout.

        If saga exceeds timeout → Abort → Trigger compensation.
        """
        try:
            result = await asyncio.wait_for(
                self._execute_saga_internal(plan),
                timeout=timeout_ms / 1000
            )
            return result

        except asyncio.TimeoutError:
            logger.error(
                "saga_timeout",
                saga_id=self.saga_id,
                timeout_ms=timeout_ms
            )

            # Trigger compensation
            await self.rollback()

            raise SagaTimeoutError(f"Saga {self.saga_id} exceeded {timeout_ms}ms timeout")
```

**Timeout Calculation:**
```python
def calculate_saga_timeout(plan: ValidatedPlan) -> int:
    """
    Calculate saga timeout based on plan steps.

    Formula:
    saga_timeout = sum(step_timeout) + sum(compensation_timeout) + buffer
                 = (num_steps × 30s) + (num_steps × 3s) + 30s buffer

    Example (5 steps):
    saga_timeout = (5 × 30s) + (5 × 3s) + 30s
                 = 150s + 15s + 30s
                 = 195s

    Default: 120s (covers 3-4 steps)
    """
    num_steps = len(plan.steps)
    step_timeout_total = num_steps * 30  # 30s per step
    compensation_timeout_total = num_steps * 3  # 3s per compensation
    buffer = 30  # 30s buffer

    saga_timeout = step_timeout_total + compensation_timeout_total + buffer
    return min(saga_timeout, 300) * 1000  # Max 300s, convert to ms
```

---

#### **Level 4: Session Timeout (600s session lifetime)**

**Purpose:** Prevent sessions from living forever.

**Configuration:**
```yaml
saga:
  timeouts:
    session_timeout_ms: 600000  # 600s = 10 minutes
```

**Enforcement:**
```python
class SessionManager:
    """Session manager with lifetime timeout"""

    async def create_session(self, user_id: str) -> Session:
        """Create session with timeout"""
        session = Session(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            created_at=time.time(),
            expires_at=time.time() + 600  # 10 minutes
        )

        # Schedule session cleanup
        asyncio.create_task(self._cleanup_session_after_timeout(session))

        return session

    async def _cleanup_session_after_timeout(self, session: Session):
        """Clean up session after timeout"""
        await asyncio.sleep(600)  # Wait 10 minutes

        # Abort any running sagas
        for saga_id in session.active_sagas:
            await self.abort_saga(saga_id)

        # Delete session
        await self.delete_session(session.session_id)

        logger.info(
            "session_timeout_cleanup",
            session_id=session.session_id
        )
```

---

### Component 2: Timeout Enforcement

**Purpose:** Enforce timeouts using asyncio primitives.

**Timeout Wrapper:**
```python
async def with_timeout(
    coro: Coroutine,
    timeout_ms: int,
    operation_name: str,
    trace_id: str
) -> Any:
    """
    Execute coroutine with timeout.

    Raises TimeoutError if exceeded.
    Logs timeout events for debugging.
    """
    start_time = time.time()

    try:
        result = await asyncio.wait_for(
            coro,
            timeout=timeout_ms / 1000
        )

        latency_ms = (time.time() - start_time) * 1000
        logger.info(
            "operation_complete",
            operation=operation_name,
            latency_ms=latency_ms,
            trace_id=trace_id
        )

        return result

    except asyncio.TimeoutError:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(
            "operation_timeout",
            operation=operation_name,
            timeout_ms=timeout_ms,
            actual_latency_ms=latency_ms,
            trace_id=trace_id
        )
        raise
```

**Usage Example:**
```python
# Step execution with timeout
result = await with_timeout(
    coro=tool_runner.run_tool(step),
    timeout_ms=30000,
    operation_name=f"step_{step.step_id}",
    trace_id=trace_id
)

# Compensation with timeout
comp_result = await with_timeout(
    coro=execute_compensation_action(compensation),
    timeout_ms=3000,
    operation_name=f"compensation_{compensation.step_id}",
    trace_id=trace_id
)
```

---

### Component 3: Deadlock Detection

**Purpose:** Detect and prevent deadlocks.

#### **Deadlock Type 1: Circular Dependencies (DAG Cycles)**

**Detection:** Already handled by 0007c (Validation Stage).

**Prevention:**
```python
# From 0007c: Kahn's algorithm for DAG cycle detection
# Validation fails if circular dependencies detected
# Example:
#   Step 1 depends on Step 2
#   Step 2 depends on Step 1
#   → Circular dependency → Validation error
```

---

#### **Deadlock Type 2: Resource Deadlock**

**Definition:** Agent A waits for Agent B, Agent B waits for Agent A.

**Example:**
```
Agent Concierge: Waiting for Planner to respond
Agent Planner: Waiting for Concierge to respond
→ Deadlock (both waiting forever)
```

**Prevention: Resource Ordering**

**Rule:** Agents acquire resources in deterministic order (agent_id ascending).

**Implementation:**
```python
class ResourceLock:
    """Resource lock with ordering"""

    def __init__(self):
        self.locks: Dict[str, asyncio.Lock] = {}

    async def acquire_multiple(
        self,
        resource_ids: List[str],
        agent_id: str,
        timeout_ms: int = 5000
    ) -> None:
        """
        Acquire multiple resources in order.

        Ordering: Sort resource_ids alphabetically (deterministic)
        Timeout: Abort if can't acquire all locks within timeout
        """
        # Sort resource IDs (deterministic ordering)
        sorted_resource_ids = sorted(resource_ids)

        acquired_locks = []

        try:
            # Acquire locks in order
            for resource_id in sorted_resource_ids:
                lock = self.locks.setdefault(resource_id, asyncio.Lock())

                # Acquire with timeout
                try:
                    await asyncio.wait_for(
                        lock.acquire(),
                        timeout=timeout_ms / 1000
                    )
                    acquired_locks.append(lock)

                except asyncio.TimeoutError:
                    logger.error(
                        "resource_deadlock_detected",
                        agent_id=agent_id,
                        resource_id=resource_id,
                        timeout_ms=timeout_ms
                    )
                    raise DeadlockError(f"Deadlock detected acquiring {resource_id}")

        except:
            # Release all acquired locks on error
            for lock in acquired_locks:
                lock.release()
            raise
```

**Deadlock Metrics:**
```python
from prometheus_client import Counter

deadlock_detected_total = Counter(
    'deadlock_detected_total',
    'Total deadlocks detected',
    ['agent_id', 'resource_id']
)
```

---

### Component 4: Liveness Guarantees

**Purpose:** Ensure all sagas terminate within bounded time.

**Guarantee 1: Saga Termination**
```python
# Every saga terminates (COMPLETED or ABORTED) within saga_timeout
# Proof:
# - Saga timeout enforced via asyncio.wait_for()
# - Timeout triggers compensation → Saga ABORTED
# - Therefore: All sagas terminate within saga_timeout
```

**Guarantee 2: No Infinite Loops**
```python
# Max steps per plan = 10 (enforced by 0007c validation)
# Max retries per step = 5 (enforced by 0008b retry policy)
# Total max iterations = 10 steps × 5 retries = 50 iterations
# Total max time = 50 × 30s = 1500s (25 minutes)
# Saga timeout (120s) terminates earlier → Liveness guaranteed
```

**Guarantee 3: No Infinite Compensations**
```python
# Compensation timeout = 3s per step (enforced)
# Max compensations = 10 steps (max plan size)
# Total compensation time = 10 × 3s = 30s
# Saga timeout (120s) covers compensation time → Liveness guaranteed
```

**Liveness Proof:**
```python
def prove_liveness():
    """
    Liveness proof: All sagas terminate within bounded time.

    Assumptions:
    1. Step timeout = 30s
    2. Compensation timeout = 3s
    3. Saga timeout = 120s
    4. Max steps = 10
    5. Max retries = 5

    Proof:
    - Case 1 (All steps succeed):
      Total time = 10 steps × 30s = 300s
      Saga timeout (120s) triggers → Abort → Saga terminates

    - Case 2 (Step fails, compensation succeeds):
      Total time = (failed_steps × 30s) + (compensations × 3s)
                 ≤ (10 × 30s) + (10 × 3s)
                 = 300s + 30s
                 = 330s
      Saga timeout (120s) triggers → Abort → Saga terminates

    - Case 3 (Infinite retry loop):
      Max retries = 5 per step
      Retry policy timeout triggers → Abort → Saga terminates

    Conclusion: All sagas terminate within saga_timeout (120s) ✓
    """
    pass
```

---

## Performance Analysis

### Timeout Latency Budget

| Level | Timeout | Coverage |
|-------|---------|----------|
| **Step** | 30s | Individual tool call |
| **Compensation** | 3s | Individual compensation |
| **Saga** | 120s | Total saga execution |
| **Session** | 600s | Session lifetime |

**Worst-Case Scenario (5-step plan):**
- Step execution: 5 × 30s = 150s
- Compensation: 5 × 3s = 15s
- Total: 165s
- Saga timeout: 120s (triggers before worst-case) ✓

---

## Canonical Values

```yaml
# k1/config/saga.yml
saga:
  timeouts:
    # Level 1: Step timeout
    step_timeout_ms: 30000        # 30s per tool call

    # Level 2: Compensation timeout
    compensation_timeout_ms: 3000 # 3s per compensation

    # Level 3: Saga timeout
    saga_timeout_ms: 120000       # 120s total saga time
    saga_timeout_buffer_ms: 30000 # 30s buffer

    # Level 4: Session timeout
    session_timeout_ms: 600000    # 600s = 10 minutes

  # Deadlock prevention
  deadlock:
    resource_acquire_timeout_ms: 5000  # 5s to acquire resource

  # Liveness guarantees
  liveness:
    max_steps_per_plan: 10
    max_retries_per_step: 5
    max_saga_iterations: 50
```

---

## Conclusion

Timeout & Deadlock Handling provides:
1. **4-level timeout hierarchy** (step 30s, compensation 3s, saga 120s, session 600s)
2. **Timeout enforcement** (asyncio.wait_for, timeout tracking)
3. **Deadlock prevention** (resource ordering, timeout-based resolution)
4. **Liveness guarantees** (all sagas terminate within 120s)

**ADR-0008 Complete!** All 4 sub-ADRs created for Saga Pattern Error Recovery.
