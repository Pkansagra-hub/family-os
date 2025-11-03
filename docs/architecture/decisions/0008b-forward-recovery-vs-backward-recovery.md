---
adr_number: 0008b
title: Forward Recovery vs Backward Recovery
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
affected_modules: []
concerns:
- architecture
- compliance
- cost
- modularity
- performance
- privacy
- reliability
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0008
- ADR-0008a
- ADR-0008b
- ADR-0008c
- ADR-0009
- ADR-0074
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
  affected_adrs:
  - ADR-0008
  - ADR-0008a
  - ADR-0008b
  - ADR-0008c
  - ADR-0009
  - ADR-0074
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


# ADR-0008b: Forward Recovery vs Backward Recovery

**Status:** ✅ Approved (2025-10-12)
**Last Updated:** 2025-10-17 (M2 Context: See ADR-0074 for module load failure recovery)
**Parent ADR:** [ADR-0008: Saga Pattern Error Recovery](./0008-saga-pattern-error-recovery.md)
**Related ADRs:**
- [ADR-0008a: Compensating Transaction Design](./0008a-compensating-transaction-design.md) - Compensation handlers
- [ADR-0008c: Distributed State Management](./0008c-distributed-state-management.md) - Saga state persistence
- [ADR-0009: Circuit Breaker Pattern](./0009-circuit-breaker-pattern.md) - Circuit state for retry decisions
- [ADR-0074 (Pluggable Module System - **NEW M2**)](0074-pluggable-module-system.md)

**Research Citations:**
- Exponential backoff (AWS Architecture Blog 2015) - Retry best practices
- Circuit breaker pattern (Nygard 2007) - Release It! Design patterns
- Transient vs permanent failures (Azure reliability docs) - Failure classification

---

## Context & Problem Statement

### Current State
When a step fails mid-execution, the system has **no strategy to decide whether to retry forward or rollback backward**:
- ❌ No failure classification (transient vs permanent vs ambiguous)
- ❌ No retry policy (exponential backoff, max retries, jitter)
- ❌ No circuit breaker integration (stop retrying if service down)
- ❌ Always rollback on failure (even for transient errors like network timeout)

**Example: Network Timeout (Should Retry Forward)**
```
Step: Charge payment
Error: Network timeout (transient)
Current behavior: Rollback immediately (cancel booking, flight)
Desired behavior: Retry 5x with backoff → Success (no rollback needed)
```

### Problem Statement
**How do we classify failures and select the optimal recovery strategy (forward retry vs backward rollback) to minimize unnecessary compensations while ensuring system consistency?**

### Key Challenges

1. **Failure Classification:**
   - Transient failures (network timeout, rate limit) → Retry forward
   - Permanent failures (invalid input, permission denied) → Rollback backward
   - Ambiguous failures (unknown status) → Depends on idempotency

2. **Retry Budget:**
   - Max 5 retries per step (prevent infinite loops)
   - Total retry time ≤ session budget (default 10s)
   - Exponential backoff (100ms, 200ms, 400ms, 800ms, 1600ms)

3. **Circuit Breaker Integration:**
   - Don't retry if circuit OPEN (service down)
   - Half-open probe (test if service recovered)

4. **Hybrid Recovery:**
   - Try forward recovery first (up to max retries)
   - If all retries exhausted → Trigger backward recovery

---

## Decision

### Overview
Implement **recovery strategy selection** with 3 components:
1. **Failure Classification** (3 types: transient, permanent, ambiguous)
2. **Forward Recovery** (retry with exponential backoff + circuit breaker)
3. **Backward Recovery** (saga compensation in reverse order)
4. **Hybrid Recovery** (retry forward first → rollback backward if exhausted)

---

### Component 1: Failure Classification

**Purpose:** Classify errors to select optimal recovery strategy.

#### **Failure Type 1: Transient Failures (Retry Forward)**

**Definition:** Temporary errors that may succeed on retry.

**Examples:**
- Network timeout (connection timeout, read timeout)
- Rate limit exceeded (HTTP 429)
- Service temporarily unavailable (HTTP 503)
- Database connection pool exhausted
- Temporary disk full

**Classification Logic:**
```python
class FailureClassifier:
    """Classify failures for recovery strategy selection"""

    def classify_error(self, error: StepError) -> FailureType:
        """Classify error as TRANSIENT, PERMANENT, or AMBIGUOUS"""

        # Transient errors (retry forward)
        if isinstance(error, asyncio.TimeoutError):
            return FailureType.TRANSIENT

        if isinstance(error, aiohttp.ClientError):
            if error.status in [429, 503, 504]:
                return FailureType.TRANSIENT

        if isinstance(error, ConnectionError):
            return FailureType.TRANSIENT

        # Permanent errors (rollback backward)
        if isinstance(error, ValueError):  # Invalid input
            return FailureType.PERMANENT

        if isinstance(error, PermissionError):  # Forbidden
            return FailureType.PERMANENT

        if isinstance(error, aiohttp.ClientError):
            if error.status in [400, 401, 403, 404]:
                return FailureType.PERMANENT

        # Ambiguous errors (depends on idempotency)
        return FailureType.AMBIGUOUS
```

---

#### **Failure Type 2: Permanent Failures (Rollback Backward)**

**Definition:** Errors that will never succeed on retry.

**Examples:**
- Invalid input (HTTP 400)
- Unauthorized (HTTP 401)
- Permission denied (HTTP 403)
- Resource not found (HTTP 404)
- Validation error (schema mismatch)

**Classification Logic:**
```python
PERMANENT_ERROR_CODES = {400, 401, 403, 404, 405, 422}

def is_permanent_error(error: StepError) -> bool:
    """Check if error is permanent (never succeeds on retry)"""
    if isinstance(error, aiohttp.ClientError):
        return error.status in PERMANENT_ERROR_CODES

    if isinstance(error, (ValueError, PermissionError, KeyError)):
        return True

    return False
```

---

#### **Failure Type 3: Ambiguous Failures (Depends on Idempotency)**

**Definition:** Unknown status (unclear if operation succeeded or failed).

**Examples:**
- Timeout after request sent (did server process it?)
- Unknown error code (HTTP 500 - internal server error)
- Network partition (client disconnected, server may continue)

**Classification Logic:**
```python
def is_ambiguous_error(error: StepError) -> bool:
    """Check if error is ambiguous (unknown status)"""
    if isinstance(error, asyncio.TimeoutError):
        # Timeout after send = ambiguous (server may have processed)
        if error.phase == "after_send":
            return True

    if isinstance(error, aiohttp.ClientError):
        if error.status in [500, 502]:  # Internal server error
            return True

    return False
```

**Recovery Decision for Ambiguous:**
```python
def handle_ambiguous_error(step: PlanStep, error: StepError) -> RecoveryStrategy:
    """
    Ambiguous error recovery:
    - If step is idempotent → Retry forward (safe to retry)
    - If step is NOT idempotent → Rollback backward (prevent duplicate)
    """
    if step.is_idempotent():
        return RecoveryStrategy.RETRY_FORWARD
    else:
        return RecoveryStrategy.ROLLBACK_BACKWARD
```

---

### Component 2: Forward Recovery (Retry with Exponential Backoff)

**Purpose:** Retry transient failures with exponential backoff.

**Retry Policy:**
```python
@dataclass
class RetryPolicy:
    """Retry policy configuration"""
    max_retries: int = 5
    base_delay_ms: int = 100
    max_delay_ms: int = 1600
    jitter_percent: int = 20
    retry_budget_ms: int = 10000  # 10s total

async def execute_with_retry(
    step: PlanStep,
    retry_policy: RetryPolicy,
    circuit_breaker: CircuitBreaker,
    trace_id: str
) -> StepResult:
    """
    Execute step with exponential backoff retry.

    Retry sequence:
    1. Initial attempt
    2. Wait 100ms (+/- 20% jitter) → Retry 1
    3. Wait 200ms (+/- 20% jitter) → Retry 2
    4. Wait 400ms (+/- 20% jitter) → Retry 3
    5. Wait 800ms (+/- 20% jitter) → Retry 4
    6. Wait 1600ms (+/- 20% jitter) → Retry 5 (final)

    Total retry time: 100+200+400+800+1600 = 3100ms (~3s)
    """
    retry_count = 0
    total_retry_time_ms = 0

    while retry_count <= retry_policy.max_retries:
        # Check circuit breaker
        if circuit_breaker.state == CircuitState.OPEN:
            logger.info(
                "circuit_breaker_open_skipping_retry",
                step_id=step.step_id,
                trace_id=trace_id
            )
            raise CircuitBreakerOpenError(f"Circuit open for {step.tool}")

        # Execute step
        try:
            result = await tool_runner.run_tool(
                step=step,
                timeout_ms=step.timeout_ms,
                trace_id=trace_id
            )

            # Success
            if result.status == "SUCCESS":
                return result

        except StepError as e:
            # Classify error
            error_type = failure_classifier.classify_error(e)

            # Permanent error → Don't retry
            if error_type == FailureType.PERMANENT:
                logger.info(
                    "permanent_error_no_retry",
                    step_id=step.step_id,
                    error=str(e),
                    trace_id=trace_id
                )
                raise e

            # Transient error → Retry
            if error_type == FailureType.TRANSIENT:
                retry_count += 1

                # Check retry budget
                if total_retry_time_ms >= retry_policy.retry_budget_ms:
                    logger.info(
                        "retry_budget_exhausted",
                        step_id=step.step_id,
                        total_retry_time_ms=total_retry_time_ms,
                        trace_id=trace_id
                    )
                    raise e

                # Check max retries
                if retry_count > retry_policy.max_retries:
                    logger.info(
                        "max_retries_exhausted",
                        step_id=step.step_id,
                        retry_count=retry_count,
                        trace_id=trace_id
                    )
                    raise e

                # Calculate backoff delay
                delay_ms = min(
                    retry_policy.base_delay_ms * (2 ** (retry_count - 1)),
                    retry_policy.max_delay_ms
                )

                # Add jitter
                jitter = random.uniform(-0.2, 0.2)  # +/- 20%
                delay_ms = int(delay_ms * (1 + jitter))

                # Wait before retry
                await asyncio.sleep(delay_ms / 1000)
                total_retry_time_ms += delay_ms

                logger.info(
                    "retrying_step",
                    step_id=step.step_id,
                    retry_count=retry_count,
                    delay_ms=delay_ms,
                    trace_id=trace_id
                )

                continue  # Retry

    # All retries exhausted
    raise MaxRetriesExceededError(f"Max retries exceeded for step {step.step_id}")
```

**Performance:**
- Total retry time: ~3s (5 retries)
- Jitter: ±20% (prevent thundering herd)
- Retry budget: 10s max (configurable)

---

### Component 3: Backward Recovery (Saga Compensation)

**Purpose:** Rollback completed steps through compensations.

**Compensation Execution:**
```python
async def execute_backward_recovery(
    saga_id: str,
    completed_steps: List[PlanStep],
    completed_results: List[StepResult],
    session_id: str,
    trace_id: str
) -> SagaRollbackResult:
    """
    Execute backward recovery (saga compensation).

    Compensation order: Reverse (Step N → N-1 → ... → 1)
    Best-effort: Continue on compensation failure
    """
    compensation_results = []

    # Reverse order (LIFO stack)
    for step, result in reversed(list(zip(completed_steps, completed_results))):
        # Check if step has compensation
        if isinstance(step.compensation, NoOpCompensation):
            logger.info(
                "step_no_compensation",
                step_id=step.step_id,
                trace_id=trace_id
            )
            continue

        # Execute compensation (idempotent)
        try:
            comp_result = await execute_compensation_idempotent(
                step=step,
                step_result=result,
                saga_id=saga_id,
                trace_id=trace_id
            )
            compensation_results.append(comp_result)

            logger.info(
                "compensation_executed",
                step_id=step.step_id,
                success=comp_result.success,
                latency_ms=comp_result.latency_ms,
                trace_id=trace_id
            )

        except Exception as e:
            # Best-effort: Log failure, continue with next compensation
            logger.error(
                "compensation_failed",
                step_id=step.step_id,
                error=str(e),
                trace_id=trace_id
            )
            compensation_results.append(CompensationResult(
                step_id=step.step_id,
                success=False,
                error_message=str(e)
            ))

    # Saga rollback result
    successful_compensations = sum(1 for r in compensation_results if r.success)
    total_compensations = len(compensation_results)

    return SagaRollbackResult(
        saga_id=saga_id,
        total_compensations=total_compensations,
        successful_compensations=successful_compensations,
        failed_compensations=total_compensations - successful_compensations,
        status="PARTIALLY_COMPENSATED" if failed_compensations > 0 else "FULLY_COMPENSATED"
    )
```

**Performance:**
- Compensation latency: <3s per step
- Total rollback: <15s for 5 steps
- Best-effort: Continue on failure

---

### Component 4: Hybrid Recovery (Retry Forward → Rollback Backward)

**Purpose:** Try forward recovery first, fallback to backward recovery.

**Hybrid Strategy:**
```python
async def execute_hybrid_recovery(
    step: PlanStep,
    completed_steps: List[PlanStep],
    completed_results: List[StepResult],
    saga_id: str,
    session_id: str,
    trace_id: str
) -> RecoveryResult:
    """
    Hybrid recovery strategy:
    1. Try forward recovery (retry up to max retries)
    2. If all retries exhausted → Trigger backward recovery
    """
    try:
        # Forward recovery (retry with backoff)
        result = await execute_with_retry(
            step=step,
            retry_policy=RetryPolicy(),
            circuit_breaker=circuit_breaker_registry.get(step.tool),
            trace_id=trace_id
        )

        # Success
        return RecoveryResult(
            strategy=RecoveryStrategy.RETRY_FORWARD,
            success=True,
            step_result=result
        )

    except (MaxRetriesExceededError, CircuitBreakerOpenError) as e:
        # Forward recovery failed → Trigger backward recovery
        logger.info(
            "forward_recovery_failed_rollback",
            step_id=step.step_id,
            error=str(e),
            trace_id=trace_id
        )

        # Backward recovery (saga compensation)
        rollback_result = await execute_backward_recovery(
            saga_id=saga_id,
            completed_steps=completed_steps,
            completed_results=completed_results,
            session_id=session_id,
            trace_id=trace_id
        )

        return RecoveryResult(
            strategy=RecoveryStrategy.ROLLBACK_BACKWARD,
            success=False,
            rollback_result=rollback_result
        )
```

**Performance:**
- Forward recovery: 5 retries × ~600ms avg = ~3s
- Backward recovery: 5 steps × 3s = ~15s
- Total (worst-case): ~18s

---

## Recovery Strategy Selection Logic

```python
class RecoveryStrategySelector:
    """Select optimal recovery strategy based on failure type"""

    def select_strategy(
        self,
        step: PlanStep,
        error: StepError,
        retry_count: int
    ) -> RecoveryStrategy:
        """
        Select recovery strategy:

        1. Classify error (transient, permanent, ambiguous)
        2. Check retry budget
        3. Check circuit breaker state
        4. Return strategy (RETRY_FORWARD, ROLLBACK_BACKWARD, HYBRID)
        """
        # Classify error
        error_type = failure_classifier.classify_error(error)

        # Permanent error → Rollback immediately
        if error_type == FailureType.PERMANENT:
            return RecoveryStrategy.ROLLBACK_BACKWARD

        # Transient error → Retry forward (if budget allows)
        if error_type == FailureType.TRANSIENT:
            if retry_count < 5:  # Max retries
                return RecoveryStrategy.RETRY_FORWARD
            else:
                return RecoveryStrategy.ROLLBACK_BACKWARD  # Retries exhausted

        # Ambiguous error → Depends on idempotency
        if error_type == FailureType.AMBIGUOUS:
            if step.is_idempotent():
                return RecoveryStrategy.RETRY_FORWARD  # Safe to retry
            else:
                return RecoveryStrategy.ROLLBACK_BACKWARD  # Avoid duplicate

        # Default: Rollback
        return RecoveryStrategy.ROLLBACK_BACKWARD
```

---

## Performance Analysis

### Latency Breakdown

| Strategy | Latency (P95) | Use Case |
|----------|---------------|----------|
| Forward recovery | ~3s | Transient errors (85%) |
| Backward recovery | ~15s | Permanent errors (10%) |
| Hybrid recovery | ~18s | Exhausted retries (5%) |

---

## Canonical Values

```yaml
# k1/config/saga.yml
saga:
  recovery:
    # Retry policy
    retry_policy:
      max_retries: 5
      base_delay_ms: 100
      max_delay_ms: 1600
      jitter_percent: 20

    # Retry budget
    retry_budget_ms: 10000  # 10s total

    # Failure classification
    transient_errors:
      - "asyncio.TimeoutError"
      - "aiohttp.ClientError:429"
      - "aiohttp.ClientError:503"
      - "ConnectionError"

    permanent_errors:
      - "ValueError"
      - "PermissionError"
      - "aiohttp.ClientError:400"
      - "aiohttp.ClientError:401"
      - "aiohttp.ClientError:403"
      - "aiohttp.ClientError:404"
```

---

## Conclusion

Forward Recovery vs Backward Recovery provides:
1. **Failure classification** (transient, permanent, ambiguous)
2. **Forward recovery** (retry with exponential backoff, ~3s)
3. **Backward recovery** (saga compensation, ~15s)
4. **Hybrid recovery** (retry first → rollback if exhausted)

**Next step:** Proceed to **0008c (Distributed State Management)**.