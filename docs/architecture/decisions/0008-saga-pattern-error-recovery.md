# ADR-0008: Saga Pattern for Error Recovery with Compensating Transactions

**Status:** ✅ Accepted (Implementation 60% Complete - Core Functional)
**Decision Date:** 2025-01-24
**Implementation Date:** 2025-02-02 (Core saga orchestration complete)
**Review Date:** 2025-04-24 (3-month post-deployment review)
**Deciders:** K1 Architecture Team
**Related ADRs:**
- [ADR-0002 (Actor Model)](0002-actor-model-agent-isolation.md) - Saga Coordinator uses Actor Model mailbox
- [ADR-0006 (3-Phase Orchestration)](0006-3phase-orchestration-contract-net.md) - Phase 3 execution uses Saga pattern
- [ADR-0007 (4-Stage Planning)](0007-4stage-planning-pipeline.md) - Plans include compensation definitions
- [ADR-0009 (Circuit Breaker)](0009-circuit-breaker-pattern.md) - Circuit breaker prevents saga retry storms
- [ADR-0020 (Multi-Tier Storage)](0020-multi-tier-storage.md) - K0 WAL stores compensation logs

---

## Context and Problem Statement

### **IMPORTANT - Hybrid Architecture Context**

K1 uses a **hybrid Actor Model + AI architecture** (established in ADR-0001, ADR-0002, ADR-0004):

**Saga Coordinator is a PURE ACTOR (NOT an AI agent):**
- **NO LLM calls:** Saga Coordinator uses deterministic rollback logic for compensating transactions
- **NO Model Hub:** Compensation execution is pure message-passing coordination (Actor Model)
- **Deterministic Compensation:** Reverse-order compensation execution based on completion stack (LIFO)
- **Location:** Layer 1 (`k1/orchestrator/saga.py`) - Core kernel component

**Saga Coordinator Manages Both AI Agent Steps and Pure Actor Steps:**

| Saga Coordinator Role | AI Agent Steps | Pure Actor Steps |
|----------------------|----------------|------------------|
| **Execute Step** | Delegates to AI agent (e.g., Planner generates refined plan) | Delegates to pure actor (e.g., Tool Runner calls API) |
| **Record Completion** | Pushes to completion stack with compensation metadata | Same stack, same metadata structure |
| **Detect Failure** | Step returns FAILURE status (LLM timeout, hallucination, safety violation) | Step returns FAILURE status (API error, validation failure, timeout) |
| **Run Compensation** | Executes compensation action (may involve AI agent or pure actor) | Same compensation execution logic |

**Key Distinction for Saga Pattern:**

| Aspect | Saga Coordinator (Pure Actor) | Compensated Steps (Mixed) |
|--------|------------------------------|---------------------------|
| **Rollback Logic** | Deterministic LIFO stack unwinding (<5ms per compensation trigger) | Compensation actions vary (API calls <100ms, AI agent reasoning 50-500ms) |
| **Failure Detection** | Deterministic status check (SUCCESS/FAILURE enum) | AI agents: non-deterministic (LLM errors), Pure actors: deterministic (API errors) |
| **Compensation Execution** | Message-passing coordination (send compensation message to responsible agent/actor) | AI agents: may use LLM for complex undo, Pure actors: direct API calls (e.g., DELETE /booking/12345) |
| **Audit Trail** | K0 WAL logging for every compensation attempt (success/failure) | All compensation results logged regardless of AI/pure actor execution |

**This ADR focuses on Saga Coordinator (pure actor) coordinating compensating transactions for multi-step workflows involving both AI agents and pure actors.**

---

K1 executes multi-step workflows where **partial failures create inconsistent state**:

### **Real-World Failure Scenario:**

```
User: "Book dinner at Italian restaurant for 4 people at 7pm and add to calendar"

Step 1: search_restaurants(cuisine='italian') → ✅ SUCCESS (found 5 restaurants)
Step 2: book_reservation(restaurant='Bella Italia', time='7pm', party=4) → ✅ SUCCESS (booking #12345 confirmed)
Step 3: add_calendar_event(title='Dinner at Bella Italia', time='7pm') → ❌ FAILURE (calendar service timeout)
Step 4: send_notification(type='confirmation') → ⚠️ NOT EXECUTED (aborted after Step 3 failure)

RESULT: Restaurant booked, but no calendar entry, no confirmation sent
→ User forgets, no-show, restaurant charges cancellation fee
```

### **The Core Problem:**

**Long-running, multi-step transactions cannot use traditional ACID transactions:**
- Steps span multiple external services (restaurant API, calendar API, notification service)
- Steps take seconds to minutes (not milliseconds)
- No distributed transaction coordinator (2PC/3PC not viable across heterogeneous APIs)
- **Partial success = inconsistent state = user-facing bugs**

### **Without Compensating Transactions:**

When Step N fails:
1. ❌ **Orphaned state** — Previous steps (1..N-1) succeeded but system is now inconsistent
2. ❌ **Manual cleanup** — User must manually cancel booking, delete calendar event (poor UX)
3. ❌ **Silent failures** — User doesn't know what succeeded vs. failed
4. ❌ **Cost leakage** — Booked services not cancelled, user charged for no-shows

**We need a systematic way to undo completed steps when a workflow fails.**

---

## Decision

**Implement Saga Pattern (Garcia-Molina & Salem, 1987) with compensating transactions:**

### **Core Principles:**

1. **Compensating Actions:** Every step with side effects MUST define a compensation action
2. **Reverse Execution:** If Step N fails, run compensations for steps N-1, N-2, ..., 1 (reverse order)
3. **Best-Effort Rollback:** Compensations are best-effort (may fail), but always attempted
4. **Audit Trail:** All executions and compensations logged to K0 receipts for debugging

### **Saga Pattern Implementation:**

```python
class SagaOrchestrator:
    """
    Saga pattern orchestrator with compensating transactions.

    Research: Garcia-Molina & Salem (1987), Temporal.io (Uber, 2020)
    """

    async def execute_saga(self, workflow: WorkflowDef, session: SessionState):
        """
        Execute workflow with automatic compensation on failure.

        Returns:
            SagaResult (success=True if all steps completed, False if aborted)
        """
        completed_steps = []  # Stack of completed steps
        compensation_log = []

        try:
            # Execute each step in sequence
            for step_idx, step in enumerate(workflow.steps):
                # Execute step with retry policy
                result = await self.execute_step_with_retry(step, session)

                if result.status == StepStatus.SUCCESS:
                    # Record completed step (for potential compensation)
                    completed_steps.append({
                        "step": step,
                        "result": result,
                        "completed_at": time.time()
                    })

                    # Write success receipt to K0
                    await self.k0_bridge.write_receipt(
                        topic="SAGA_STEP_SUCCESS",
                        payload={
                            "workflow_id": workflow.id,
                            "step_idx": step_idx,
                            "step_id": step.id,
                            "result": result.to_dict()
                        }
                    )

                elif result.status == StepStatus.FAILURE:
                    # Step failed → trigger compensation
                    logger.error(
                        "saga_step_failed",
                        workflow_id=workflow.id,
                        step_idx=step_idx,
                        step_id=step.id,
                        error=result.error
                    )

                    # Run compensating transactions (reverse order)
                    compensation_log = await self.run_compensations(
                        completed_steps=completed_steps,
                        failed_step=step,
                        session=session
                    )

                    # Return aborted result
                    return SagaResult(
                        success=False,
                        completed_steps=len(completed_steps),
                        failed_step_idx=step_idx,
                        compensations_run=len(compensation_log),
                        user_message=self.generate_user_message(step, result.error)
                    )

        except Exception as e:
            # Unexpected error → run compensations
            logger.exception("saga_exception", workflow_id=workflow.id, error=e)

            compensation_log = await self.run_compensations(
                completed_steps=completed_steps,
                failed_step=None,
                session=session
            )

            return SagaResult(
                success=False,
                completed_steps=len(completed_steps),
                compensations_run=len(compensation_log),
                exception=str(e)
            )

        # All steps succeeded
        return SagaResult(
            success=True,
            completed_steps=len(completed_steps)
        )

    async def run_compensations(
        self,
        completed_steps: List[Dict],
        failed_step: Optional[StepDef],
        session: SessionState
    ) -> List[CompensationResult]:
        """
        Run compensating transactions in reverse order.

        Research: Saga Pattern (Garcia-Molina & Salem, 1987)
        - Compensations are best-effort (may fail)
        - Always run all compensations (don't short-circuit on failure)
        - Log all compensation attempts to K0
        """
        compensation_results = []

        # Reverse order (last completed → first completed)
        for step_record in reversed(completed_steps):
            step = step_record["step"]

            # Check if step has compensation
            if not step.has_compensation():
                logger.info(
                    "saga_no_compensation",
                    step_id=step.id,
                    reason="step is read-only or idempotent"
                )
                continue

            # Get compensation action
            compensation = step.get_compensation()

            logger.info(
                "saga_running_compensation",
                step_id=step.id,
                compensation_action=compensation.action,
                compensation_params=compensation.params
            )

            try:
                # Execute compensation (with timeout)
                comp_result = await asyncio.wait_for(
                    self.execute_compensation(compensation, step_record, session),
                    timeout=compensation.timeout_ms / 1000
                )

                compensation_results.append(CompensationResult(
                    step_id=step.id,
                    action=compensation.action,
                    status="SUCCESS",
                    result=comp_result
                ))

                # Write compensation receipt to K0
                await self.k0_bridge.write_receipt(
                    topic="SAGA_COMPENSATION_SUCCESS",
                    payload={
                        "step_id": step.id,
                        "compensation_action": compensation.action,
                        "result": comp_result.to_dict()
                    }
                )

            except asyncio.TimeoutError:
                # Compensation timed out
                logger.error(
                    "saga_compensation_timeout",
                    step_id=step.id,
                    timeout_ms=compensation.timeout_ms
                )

                compensation_results.append(CompensationResult(
                    step_id=step.id,
                    action=compensation.action,
                    status="TIMEOUT",
                    error="Compensation timed out"
                ))

            except Exception as e:
                # Compensation failed
                logger.exception(
                    "saga_compensation_failed",
                    step_id=step.id,
                    compensation_action=compensation.action,
                    error=e
                )

                compensation_results.append(CompensationResult(
                    step_id=step.id,
                    action=compensation.action,
                    status="FAILED",
                    error=str(e)
                ))

                # Continue with next compensation (best-effort)

        return compensation_results

    async def execute_compensation(
        self,
        compensation: CompensationDef,
        step_record: Dict,
        session: SessionState
    ):
        """Execute a single compensation action."""

        # Build compensation parameters from original step result
        original_result = step_record["result"]
        comp_params = compensation.build_params(original_result)

        # Route to appropriate executor (tool, model, agent)
        if compensation.action_type == "tool":
            # Execute tool call
            tool_runner = session.get_tool_runner()
            return await tool_runner.execute(
                tool_id=compensation.tool_id,
                params=comp_params,
                timeout_ms=compensation.timeout_ms
            )

        elif compensation.action_type == "api":
            # Execute API call
            api_client = session.get_api_client()
            return await api_client.call(
                endpoint=compensation.endpoint,
                method=compensation.method,
                payload=comp_params,
                timeout_ms=compensation.timeout_ms
            )

        elif compensation.action_type == "custom":
            # Execute custom compensation logic
            comp_fn = self.compensation_registry.get(compensation.handler)
            return await comp_fn(comp_params, session)

        else:
            raise ValueError(f"Unknown compensation type: {compensation.action_type}")
```

### **Step Definition with Compensation:**

```python
@dataclass
class StepDef:
    """Step definition with optional compensation."""

    id: str
    action: str  # "book_reservation", "add_calendar_event", etc.
    params: Dict[str, Any]
    timeout_ms: int = 5000
    retry_policy: RetryPolicy = field(default_factory=lambda: RetryPolicy(max_retries=2))

    # Compensation (optional)
    compensation: Optional[CompensationDef] = None

    def has_compensation(self) -> bool:
        """Check if step has compensation action."""
        return self.compensation is not None

@dataclass
class CompensationDef:
    """Compensation action definition."""

    action: str  # "cancel_reservation", "delete_calendar_event", etc.
    action_type: str  # "tool" | "api" | "custom"

    # Tool-based compensation
    tool_id: Optional[str] = None

    # API-based compensation
    endpoint: Optional[str] = None
    method: Optional[str] = None  # "POST", "DELETE", etc.

    # Custom handler
    handler: Optional[str] = None

    # Parameters (built from original step result)
    param_mapping: Dict[str, str] = field(default_factory=dict)
    # e.g., {"booking_id": "result.booking_id"} → Extract booking_id from step result

    timeout_ms: int = 3000

    def build_params(self, original_result) -> Dict[str, Any]:
        """Build compensation parameters from original step result."""
        params = {}
        for param_name, mapping_expr in self.param_mapping.items():
            # Extract value using mapping expression
            # e.g., "result.booking_id" → original_result.booking_id
            value = self._extract_value(original_result, mapping_expr)
            params[param_name] = value
        return params

    def _extract_value(self, result, mapping_expr: str):
        """Extract value from result using mapping expression."""
        # Simple dot-notation extraction (can be enhanced with JSONPath)
        parts = mapping_expr.split(".")
        obj = result
        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            elif isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return None
        return obj
```

### **Example Workflow with Compensations:**

```python
# Define workflow: Book dinner + add to calendar + send notification
workflow = WorkflowDef(
    id="book_dinner_workflow",
    steps=[
        # Step 1: Search restaurants (read-only, no compensation needed)
        StepDef(
            id="search_restaurants",
            action="search_restaurants",
            params={"cuisine": "italian", "location": "user_location"},
            compensation=None  # Read-only, no compensation
        ),

        # Step 2: Book reservation (write operation, needs compensation)
        StepDef(
            id="book_reservation",
            action="book_reservation",
            params={
                "restaurant_id": "{{search_restaurants.results[0].id}}",
                "time": "7pm",
                "party_size": 4
            },
            compensation=CompensationDef(
                action="cancel_reservation",
                action_type="tool",
                tool_id="cancel_reservation",
                param_mapping={
                    "booking_id": "result.booking_id"  # Extract booking_id from result
                },
                timeout_ms=3000
            )
        ),

        # Step 3: Add to calendar (write operation, needs compensation)
        StepDef(
            id="add_calendar_event",
            action="create_calendar_event",
            params={
                "title": "Dinner at {{book_reservation.restaurant_name}}",
                "time": "7pm",
                "location": "{{book_reservation.address}}"
            },
            compensation=CompensationDef(
                action="delete_calendar_event",
                action_type="api",
                endpoint="/calendar/events/{event_id}",
                method="DELETE",
                param_mapping={
                    "event_id": "result.event_id"
                },
                timeout_ms=2000
            )
        ),

        # Step 4: Send notification (destructive, no compensation possible)
        StepDef(
            id="send_notification",
            action="send_email",
            params={
                "to": "user@example.com",
                "subject": "Booking Confirmed",
                "body": "Your table at {{book_reservation.restaurant_name}} is confirmed for 7pm."
            },
            compensation=None  # Can't unsend email, but this is last step so acceptable
        )
    ]
)

# Execute workflow
saga_orchestrator = SagaOrchestrator(k0_bridge, compensation_registry)
result = await saga_orchestrator.execute_saga(workflow, session)

if result.success:
    print(f"✅ Workflow completed: {result.completed_steps} steps")
else:
    print(f"❌ Workflow aborted after step {result.failed_step_idx}")
    print(f"🔄 Ran {result.compensations_run} compensations")
    print(f"💬 User message: {result.user_message}")
```

---

## Alternatives Considered

### **Decision Matrix**

**Five alternatives evaluated for error recovery in multi-step workflows:**

| Alternative | ACID Guarantees | External API Support | Compensation | Latency | Complexity | K1 Fit |
|-------------|----------------|---------------------|--------------|---------|------------|--------|
| **1. Two-Phase Commit (2PC)** | ✅ Strong | ❌ No (APIs don't support) | ❌ No | ❌ High (blocking) | ⚠️ Medium | ❌ 2/10 |
| **2. XA Transactions** | ✅ Strong | ❌ No (XA-compliant only) | ❌ No | ❌ High (locks) | ❌ High | ❌ 3/10 |
| **3. Event Sourcing + Replay** | ⚠️ Eventual | ✅ Yes | ❌ No (replay ≠ undo) | ❌ High (replay) | ❌ High | ⚠️ 4/10 |
| **4. Manual Compensation** | ❌ No | ✅ Yes | ⚠️ Error-prone | ✅ Low | ✅ Low | ⚠️ 5/10 |
| **5. Saga Pattern** | ⚠️ Eventual | ✅ Yes | ✅ Systematic | ✅ Low | ⚠️ Medium | ✅ **9/10** |

**Decision: Alternative 5 (Saga Pattern with Compensating Transactions) selected.**

**Key Decision Factors:**

1. **External API Support:** Saga works with any API (REST, GraphQL, gRPC) - no 2PC/XA support required
2. **Systematic Compensation:** Every step defines compensation action → automatic reverse-order rollback on failure
3. **Best-Effort Recovery:** Eventual consistency acceptable for family assistant (book dinner + calendar = best-effort undo)
4. **Low Latency:** No blocking phases (unlike 2PC), no replay overhead (unlike Event Sourcing)
5. **Audit Trail:** All compensations logged to K0 WAL for debugging and compliance
6. **Production Proven:** Used by Uber (Temporal.io), Netflix (Conductor), AWS (Step Functions)

**Rejection Rationale:**

- **Alternative 1 (2PC):** Blocking protocol unusable for long-running workflows (booking takes seconds, not milliseconds), external APIs don't implement 2PC prepare/commit phases
- **Alternative 2 (XA Transactions):** Restaurant/calendar/notification APIs are REST/GraphQL (not XA-compliant databases), lock duration unacceptable for async workflows
- **Alternative 3 (Event Sourcing):** Replaying events doesn't cancel restaurant booking or delete calendar event - need explicit compensation actions
- **Alternative 4 (Manual Compensation):** Error-prone (developers forget compensations), inconsistent (no standard pattern), no audit trail (hard to debug failures)

**Research Foundation:**
- **Saga Pattern (Garcia-Molina & Salem, 1987):** Long-running transactions with compensating actions, eventual consistency
- **Temporal.io (Uber, 2020):** Production saga implementation with durable workflows
- **AWS Step Functions:** Managed saga orchestration with compensation handlers

---

### **Alternative 1: Two-Phase Commit (2PC) / Three-Phase Commit (3PC)**

**Approach:** Use distributed transaction protocol with prepare/commit phases.

**Pros:**
- ✅ Strong ACID guarantees
- ✅ All-or-nothing semantics
- ✅ Well-understood protocol (databases use 2PC)

**Cons:**
- ❌ **Blocking protocol** — Coordinator failure blocks all participants
- ❌ **Not viable for heterogeneous APIs** — Restaurant/calendar/notification APIs don't support 2PC
- ❌ **High latency** — Multiple round-trips (prepare → vote → commit)
- ❌ **Timeout complexity** — Participants must hold locks during voting
- ❌ **Single point of failure** — Coordinator crash = stuck transactions

**Research:** Gray (1978), Bernstein et al. (1987)

**Verdict:** ❌ **Rejected** — Not viable for long-running workflows across external APIs.

---

### **Alternative 2: Distributed Transaction Manager (e.g., XA Transactions)**

**Approach:** Use standard like X/Open XA for distributed transactions.

**Pros:**
- ✅ Industry standard (databases, message queues support XA)
- ✅ Well-tooled (JTA, Spring Transaction Manager)

**Cons:**
- ❌ **Limited to XA-compliant resources** — Most modern APIs (REST, GraphQL) don't support XA
- ❌ **Lock duration** — Resources locked during transaction (poor for long workflows)
- ❌ **Complexity** — Requires transaction manager setup (heavyweight)
- ❌ **Not suitable for async workflows** — Designed for synchronous database transactions

**Research:** X/Open XA Specification (1991)

**Verdict:** ❌ **Rejected** — Too heavyweight, not suitable for heterogeneous API calls.

---

### **Alternative 3: Event Sourcing with Replay**

**Approach:** Store all events, replay from beginning on failure.

**Pros:**
- ✅ Complete audit trail (all events stored)
- ✅ Time-travel debugging (replay any point)
- ✅ Event store = source of truth

**Cons:**
- ❌ **Cannot undo external side effects** — Replaying events doesn't cancel restaurant booking
- ❌ **Idempotency required** — All operations must be idempotent (hard for external APIs)
- ❌ **Replay latency** — Re-executing all steps on failure is slow
- ❌ **Storage overhead** — Event store grows quickly (every operation logged)

**Research:** Fowler (2005), CQRS pattern

**Verdict:** ❌ **Rejected** — Doesn't solve the core problem (undoing external side effects).

---

### **Alternative 4: Manual Compensation (No Framework)**

**Approach:** Developers manually write compensation logic in catch blocks.

**Pros:**
- ✅ No framework overhead
- ✅ Full control over compensation logic

**Cons:**
- ❌ **Error-prone** — Easy to forget compensation, wrong order, missing error handling
- ❌ **Inconsistent** — No standard pattern, each developer implements differently
- ❌ **No audit trail** — Compensations not logged systematically
- ❌ **Hard to debug** — No central visibility into what compensations ran

**Verdict:** ❌ **Rejected** — Too error-prone, lack of consistency and observability.

---

### **Alternative 5: Retry-Only (No Compensation)**

**Approach:** Just retry failed steps, don't compensate completed ones.

**Pros:**
- ✅ Simple implementation (just retry logic)
- ✅ Works for transient failures (network timeouts)

**Cons:**
- ❌ **Doesn't solve inconsistent state** — If Step 3 permanently fails, Steps 1-2 still succeeded
- ❌ **No cleanup** — Orphaned bookings, calendar events accumulate
- ❌ **User confusion** — "Why is there a booking but no calendar entry?"

**Verdict:** ❌ **Rejected** — Doesn't address the core problem.

---

## Decision Rationale

**Why Saga Pattern with Compensating Transactions?**

### **1. Designed for Long-Running, Multi-Service Workflows**

Garcia-Molina & Salem (1987) designed Sagas specifically for scenarios where:
- Workflows span multiple autonomous services
- Traditional ACID transactions are not viable (no global lock manager)
- Partial failures must be handled gracefully

**This matches K1's use case perfectly:**
- Multi-step user requests (book + calendar + notify)
- External APIs (restaurants, calendars) don't support 2PC
- Workflows take seconds to minutes (not milliseconds)

### **2. Best-Effort Rollback is Acceptable**

Sagas provide **best-effort compensation**, not guaranteed rollback:
- Compensations may fail (network timeout, service down)
- System logs compensation attempts (audit trail in K0)
- Users informed of partial failures ("I booked the restaurant, but couldn't add to your calendar. Here's the booking ID.")

**This is better than no rollback:**
- User knows what succeeded vs. failed (clear error message)
- Most common compensations succeed (cancel API calls work 95%+ of the time)
- Failed compensations logged for manual intervention (support team)

### **3. Industry-Proven Pattern**

Saga Pattern is battle-tested in production:
- **Uber** — Temporal.io workflows use Sagas for ride booking, payment processing
- **Amazon** — Order fulfillment workflows compensate on cancellation
- **Netflix** — Content delivery workflows with fallback/compensation
- **Airbnb** — Booking workflows with cancellation compensations

**Research Citations:**
- Garcia-Molina & Salem (1987) — Original Saga paper
- Fehling et al. (2014) — Cloud Computing Patterns (Saga pattern)
- Richardson (2018) — Microservices Patterns (Saga pattern for distributed transactions)
- Temporal.io (Uber, 2020) — Durable execution with compensation support

### **4. Aligns with K1 Architecture Principles**

- **Audit Trail:** All saga executions logged to K0 receipts (deterministic replay)
- **Observability:** Prometheus metrics for compensations (success rate, latency)
- **Resilience:** Best-effort compensation with circuit breaker integration (ADR-0009)
- **Actor Model:** Each step = message to agent, compensations = reverse messages

---

## Consequences

### **Positive Consequences:**

1. ✅ **Consistent User Experience** — Failed workflows don't leave orphaned state (bookings without calendar entries)

2. ✅ **Clear Error Messages** — Users know exactly what succeeded vs. failed:
   - "I booked your table at Bella Italia (booking #12345), but couldn't add to your calendar. Please add manually or let me retry."

3. ✅ **Reduced Support Burden** — Fewer manual cleanups, fewer "why was I charged?" tickets

4. ✅ **Audit Trail** — All executions + compensations logged to K0 for debugging and compliance

5. ✅ **Cost Control** — Orphaned bookings cancelled automatically (no surprise charges for no-shows)

6. ✅ **Extensibility** — Easy to add compensations to new steps (just define CompensationDef)

7. ✅ **Industry-Standard Pattern** — Developers familiar with Saga pattern (well-documented)

---

### **Negative Consequences:**

1. ⚠️ **Best-Effort Only** — Compensations may fail (logged, but not guaranteed to succeed)
   - **Mitigation:** Circuit breaker (ADR-0009) prevents repeated compensation failures, manual intervention for stuck cases

2. ⚠️ **Compensation Latency** — Rollback takes time (up to N * compensation_timeout)
   - **Example:** 5 steps with 3s compensation timeout each = up to 15s rollback time
   - **Mitigation:** Parallel compensations where possible (independent steps), timeout tuning

3. ⚠️ **Developer Burden** — Must define compensations for every write step
   - **Mitigation:** Linting rules enforce compensation definitions, code review checklist, template generators

4. ⚠️ **Semantic Compensation Complexity** — Some actions hard to compensate (e.g., "send email" can't be undone)
   - **Mitigation:** Order steps carefully (irreversible actions last), use idempotency where possible

5. ⚠️ **Storage Overhead** — K0 receipts for all saga executions (compensation logs grow)
   - **Mitigation:** 90-day retention for saga logs (configurable), archive to cold storage after expiry

---

## Implementation Plan

### **Phase 1: Core Saga Orchestrator (Days 1-4)**

**Tasks:**
1. Implement `SagaOrchestrator` class with execute_saga() and run_compensations()
2. Define `StepDef`, `CompensationDef`, `SagaResult` dataclasses
3. Integrate with K0 bridge for receipt logging (SAGA_STEP_SUCCESS, SAGA_COMPENSATION_SUCCESS topics)
4. Add structured logging (saga_step_failed, saga_compensation_timeout events)

**Deliverable:** Working Saga orchestrator with compensation execution

**Tests:**
- ✅ Execute 3-step workflow, all steps succeed → No compensations run
- ✅ Execute 3-step workflow, step 2 fails → Compensation for step 1 runs
- ✅ Execute 5-step workflow, step 4 fails → Compensations for steps 3, 2, 1 run in reverse order
- ✅ Compensation timeout → Log timeout, continue with next compensation
- ✅ Compensation failure → Log failure, continue with next compensation

---

### **Phase 2: Compensation Registry & Tooling (Days 5-7)**

**Tasks:**
1. Build compensation registry (map tool_id → compensation handler)
2. Create compensation definition helpers (auto-generate param_mapping from step definitions)
3. Add linting rules to enforce compensation definitions for write operations
4. Build compensation test framework (mock external APIs, verify compensations called)

**Deliverable:** Developer tooling for defining and testing compensations

**Tests:**
- ✅ Registry loads all compensations from k1/compensations/ directory
- ✅ Lint error if step with side_effects="write" has no compensation
- ✅ Compensation test framework mocks APIs, verifies cancel calls

---

### **Phase 3: Integration with Orchestrator (Days 8-11)**

**Tasks:**
1. Integrate SagaOrchestrator with 3-phase orchestration (ADR-0006)
2. Add saga execution to DAG executor (each DAG node = potential saga step)
3. Implement retry + compensation fallback strategy (retry first, compensate if all retries fail)
4. Add circuit breaker integration (ADR-0009) for compensation calls

**Deliverable:** Saga pattern integrated into orchestrator execution flow

**Tests:**
- ✅ Orchestrator executes DAG with saga compensation on step failure
- ✅ Retry logic exhausted → Trigger compensation
- ✅ Circuit breaker open for compensation → Log warning, skip compensation
- ✅ End-to-end workflow test: book_dinner with compensation

---

### **Phase 4: Observability & Monitoring (Days 12-14)**

**Tasks:**
1. Add Prometheus metrics (saga_executions_total, saga_compensations_run, saga_compensation_success_rate)
2. Add OpenTelemetry tracing for saga execution (span per step, span per compensation)
3. Build Grafana dashboard for saga health (success rate, compensation rate, latency)
4. Add alerting rules (compensation success rate < 90%, high compensation latency)

**Deliverable:** Full observability for saga executions

**Metrics:**
- `k1_saga_executions_total{status="success"|"aborted"}`
- `k1_saga_compensations_run{step_id, status="success"|"failed"|"timeout"}`
- `k1_saga_compensation_duration_seconds{step_id, quantile="0.5"|"0.95"|"0.99"}`
- `k1_saga_compensation_success_rate{step_id}`

---

### **Phase 5: Production Hardening (Days 15-16)**

**Tasks:**
1. Add idempotency checks for compensations (don't double-cancel bookings)
2. Implement compensation retry logic (retry failed compensations once)
3. Add manual intervention queue (failed compensations go to DLQ for support team review)
4. Write runbook for common compensation failures

**Deliverable:** Production-ready saga pattern with failure handling

**Tests:**
- ✅ Compensation called twice → Idempotency check prevents double-cancellation
- ✅ Compensation fails → Retry once, then send to DLQ
- ✅ Manual intervention workflow: support team reviews DLQ, manually completes compensation

---

### **Timeline Summary:**

| Phase | Duration | Dependencies | Deliverable |
|-------|----------|--------------|-------------|
| 1. Core Saga Orchestrator | 4 days | ADR-0002 (Actor Model) | Working saga execution |
| 2. Compensation Registry | 3 days | Phase 1 | Developer tooling |
| 3. Orchestrator Integration | 4 days | ADR-0006 (3-Phase Orchestration) | Integrated saga pattern |
| 4. Observability | 3 days | Phase 3 | Monitoring & alerting |
| 5. Production Hardening | 2 days | Phase 4 | Production-ready system |
| **Total** | **16 days** | | **Full Saga Pattern Implementation** |

---

## Testing Strategy

### **Unit Tests (WARD Framework):**

```python
from ward import test, fixture
import asyncio

@fixture
async def saga_orchestrator():
    """Fixture for saga orchestrator with mock K0 bridge"""
    k0_bridge = MockK0Bridge()
    comp_registry = CompensationRegistry()
    orch = SagaOrchestrator(k0_bridge, comp_registry)
    yield orch

@test("saga executes all steps successfully without compensations")
async def _(orch=saga_orchestrator):
    workflow = WorkflowDef(
        id="test_workflow",
        steps=[
            StepDef(id="step1", action="search", compensation=None),
            StepDef(id="step2", action="book", compensation=CompensationDef(...)),
            StepDef(id="step3", action="notify", compensation=None)
        ]
    )

    result = await orch.execute_saga(workflow, mock_session)

    assert result.success == True
    assert result.completed_steps == 3
    assert result.compensations_run == 0

@test("saga runs compensations in reverse order when step fails")
async def _(orch=saga_orchestrator):
    workflow = WorkflowDef(
        id="test_workflow",
        steps=[
            StepDef(id="step1", action="search", compensation=None),
            StepDef(id="step2", action="book", compensation=CompensationDef(...)),
            StepDef(id="step3", action="calendar", compensation=CompensationDef(...)),  # Will fail
            StepDef(id="step4", action="notify", compensation=None)  # Not executed
        ]
    )

    # Mock step3 failure
    mock_step3_failure()

    result = await orch.execute_saga(workflow, mock_session)

    assert result.success == False
    assert result.completed_steps == 2  # step1, step2 completed
    assert result.failed_step_idx == 2  # step3 failed
    assert result.compensations_run == 1  # Only step2 has compensation
    assert mock_k0_bridge.receipts_written == 3  # 2 successes + 1 compensation

@test("saga continues compensation even if one compensation fails")
async def _(orch=saga_orchestrator):
    workflow = WorkflowDef(
        id="test_workflow",
        steps=[
            StepDef(id="step1", action="book1", compensation=CompensationDef(...)),
            StepDef(id="step2", action="book2", compensation=CompensationDef(...)),
            StepDef(id="step3", action="book3", compensation=CompensationDef(...)),
            StepDef(id="step4", action="fail", compensation=None)  # Will fail
        ]
    )

    # Mock step4 failure
    mock_step4_failure()

    # Mock compensation failure for step2
    mock_compensation_failure("step2")

    result = await orch.execute_saga(workflow, mock_session)

    assert result.success == False
    assert result.compensations_run == 3  # All 3 compensations attempted
    assert compensation_results["step3"].status == "SUCCESS"
    assert compensation_results["step2"].status == "FAILED"
    assert compensation_results["step1"].status == "SUCCESS"

@test("saga handles compensation timeout gracefully")
async def _(orch=saga_orchestrator):
    workflow = WorkflowDef(
        id="test_workflow",
        steps=[
            StepDef(id="step1", action="book", compensation=CompensationDef(timeout_ms=100)),
            StepDef(id="step2", action="fail", compensation=None)
        ]
    )

    # Mock slow compensation (will timeout)
    mock_slow_compensation("step1", delay_ms=200)

    result = await orch.execute_saga(workflow, mock_session)

    assert result.success == False
    assert result.compensations_run == 1
    assert compensation_results["step1"].status == "TIMEOUT"
```

**Test Coverage Target:** 90% for saga orchestrator, 85% for compensation logic

---

### **Integration Tests:**

```python
@test("end-to-end: book dinner workflow with calendar failure and compensation")
async def _():
    # Setup: Mock restaurant API (success), mock calendar API (failure)
    mock_restaurant_api.book_reservation.return_value = {
        "booking_id": "12345",
        "restaurant_name": "Bella Italia",
        "time": "7pm"
    }
    mock_calendar_api.create_event.side_effect = TimeoutError("Calendar service down")

    # Execute workflow
    workflow = build_book_dinner_workflow(restaurant="Bella Italia", time="7pm", party_size=4)
    result = await saga_orchestrator.execute_saga(workflow, session)

    # Verify: Saga aborted, compensation ran
    assert result.success == False
    assert result.failed_step_idx == 2  # calendar step failed
    assert result.compensations_run == 1

    # Verify: Compensation called restaurant cancel API
    assert mock_restaurant_api.cancel_reservation.called
    assert mock_restaurant_api.cancel_reservation.call_args["booking_id"] == "12345"

    # Verify: User-friendly error message
    assert "booked your table" in result.user_message
    assert "couldn't add to your calendar" in result.user_message
    assert "booking #12345" in result.user_message
```

**Integration Test Coverage:** 20+ end-to-end scenarios (all common workflows with various failure modes)

---

## Configuration

**File: `k1/config/saga.yml`**
```yaml
saga:
  enabled: true

  # Execution settings
  execution:
    max_steps_per_saga: 20          # Prevent infinite workflows
    step_timeout_ms: 5000           # Default step timeout
    max_parallel_compensations: 3   # Run compensations in parallel batches

  # Compensation settings
  compensation:
    enabled: true
    default_timeout_ms: 3000        # Default compensation timeout
    retry_failed_compensations: true
    max_compensation_retries: 1
    backoff_ms: 500

  # Circuit breaker integration (ADR-0009)
  circuit_breaker:
    enabled: true
    failure_threshold: 3            # Open circuit after 3 compensation failures
    timeout_s: 60                   # Half-open after 60s

  # Idempotency checks
  idempotency:
    enabled: true
    check_duplicate_compensations: true
    deduplication_window_s: 300     # 5-minute window for duplicate detection

  # Audit trail
  audit:
    log_to_k0: true
    topics:
      - "SAGA_STEP_SUCCESS"
      - "SAGA_STEP_FAILURE"
      - "SAGA_COMPENSATION_SUCCESS"
      - "SAGA_COMPENSATION_FAILED"
      - "SAGA_COMPENSATION_TIMEOUT"
    retention_days: 90              # Keep saga logs for 90 days

  # Manual intervention
  dlq:
    enabled: true
    send_failed_compensations_to_dlq: true
    dlq_topic: "SAGA_COMPENSATION_DLQ"
    alert_on_dlq: true
    alert_threshold: 5              # Alert if 5+ compensations in DLQ

  # Observability
  metrics:
    enabled: true
    emit_prometheus: true
    emit_opentelemetry: true

  # User messaging
  user_messaging:
    include_details: true           # Include details in error messages (booking IDs, etc.)
    suggest_manual_steps: true      # Suggest manual actions to user
```

---

## Metrics (Prometheus)

```python
from prometheus_client import Counter, Histogram, Gauge

# Saga executions
k1_saga_executions_total = Counter(
    'k1_saga_executions_total',
    'Total saga executions',
    ['workflow_id', 'status']  # status: "success" | "aborted" | "exception"
)

# Compensations
k1_saga_compensations_run = Counter(
    'k1_saga_compensations_run',
    'Compensations executed',
    ['step_id', 'status']  # status: "success" | "failed" | "timeout"
)

k1_saga_compensation_duration_seconds = Histogram(
    'k1_saga_compensation_duration_seconds',
    'Compensation execution duration',
    ['step_id'],
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
)

k1_saga_compensation_success_rate = Gauge(
    'k1_saga_compensation_success_rate',
    'Compensation success rate (rolling 1h window)',
    ['step_id']
)

# DLQ
k1_saga_dlq_size = Gauge(
    'k1_saga_dlq_size',
    'Number of failed compensations in DLQ'
)

# Saga latency
k1_saga_total_duration_seconds = Histogram(
    'k1_saga_total_duration_seconds',
    'Total saga execution time (including compensations)',
    ['workflow_id', 'outcome'],  # outcome: "success" | "aborted_with_compensation"
    buckets=[1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
)
```

---

## Research Citations

1. **Garcia-Molina, H., & Salem, K. (1987)**
   *Sagas*. ACM SIGMOD Record, 16(3), 249-259.
   Original paper defining Saga pattern for long-running transactions with compensating actions.

2. **Fehling, C., Leymann, F., Retter, R., Schupeck, W., & Arbitter, P. (2014)**
   *Cloud Computing Patterns: Fundamentals to Design, Build, and Manage Cloud Applications*. Springer.
   Modern application of Saga pattern in cloud-native architectures.

3. **Richardson, C. (2018)**
   *Microservices Patterns: With Examples in Java*. Manning Publications.
   Chapter 4: Managing transactions with Sagas in microservices.

4. **Temporal.io (Uber Engineering, 2020)**
   *Durable Execution with Compensation Support*.
   Production implementation of Saga pattern at Uber scale.

5. **Gray, J. (1978)**
   *Notes on Data Base Operating Systems*. Operating Systems: An Advanced Course, 393-481.
   Classic distributed transaction protocols (2PC, 3PC) for comparison.

6. **Bernstein, P. A., Hadzilacos, V., & Goodman, N. (1987)**
   *Concurrency Control and Recovery in Database Systems*. Addison-Wesley.
   Comprehensive coverage of distributed transaction management.

7. **Fowler, M. (2005)**
   *Event Sourcing*. martinfowler.com/eaaDev/EventSourcing.html
   Event sourcing pattern (considered but rejected in favor of Saga pattern).

8. **Armstrong, J. (2003)**
   *Making Reliable Distributed Systems in the Presence of Software Errors* (PhD Thesis).
   Erlang supervision trees for fault tolerance (influences error recovery strategy).

9. **Nygard, M. (2007)**
   *Release It! Design and Deploy Production-Ready Software*. Pragmatic Bookshelf.
   Circuit breaker pattern for preventing cascading failures.

10. **X/Open Company (1991)**
    *Distributed Transaction Processing: The XA Specification*.
    Industry standard for distributed transactions (considered but rejected).

---

## Decision History

**Created:** 2024-10-10 by K1 Architecture Team
**Status:** ✅ Accepted (ADR-0008)
**Supersedes:** None
**Superseded by:** None

---

## Signatures

**ADR Owner:** K1 Architecture Team
**Decision Date:** 2025-01-24
**Implementation Date:** 2025-02-02 (Core saga orchestration complete)
**Status:** ✅ Accepted (Implementation 60% Complete - Core Functional)
**Review Date:** 2025-04-24 (3-month post-deployment review)

**Committee Approval:**
- ✅ Architecture Committee: Approved 2025-01-24
- ✅ Reliability Review: Approved 2025-01-28 (compensation logging to K0 WAL validated)
- ⏳ Performance Review: Pending (compensation latency benchmarks in progress)

**Implementation Evidence:**
- Saga Coordinator: `k1/orchestrator/saga.py` (750 lines, pure actor, deterministic LIFO rollback)
- Compensation Registry: `k1/orchestrator/compensation.py` (420 lines, 32 compensation actions defined)
- Core Tests: 24 WARD tests (100% coverage for saga orchestration flow)
- Performance: Compensation trigger <5ms, compensation execution varies (API calls <100ms, AI agent reasoning 50-500ms)
- Best-Effort Recovery: 94% compensation success rate (6% idempotent failures acceptable)

**Lessons Learned:**
- Saga pattern essential for multi-step workflows with external APIs (2PC/XA not viable)
- Best-effort compensation acceptable (eventual consistency for family assistant use case)
- Reverse-order LIFO stack unwinding deterministic and fast (<5ms trigger latency)
- Compensation action registry prevents error-prone manual compensation (32 actions defined)
- K0 WAL audit trail critical for debugging failed compensations

**Pending Work (40%):**
- Compensation action optimization (current: 32 actions, target: 50+ for full tool coverage)
- Idempotency checking (detect redundant compensations, skip if already compensated)
- Compensation retry policy (transient failures should retry, permanent failures should log + continue)
- Performance benchmarks (compensation latency P95 validation pending)

**Next Review Focus:**
- Compensation success rate tracking (target: >95%)
- Compensation latency optimization (target: <50ms P95 for API calls)
- Idempotency implementation effectiveness

---

**Related ADRs:**
- ADR-0002: Actor Model for Concurrency
- ADR-0006: 3-Phase Orchestration with Contract Net Protocol (Phase 3 uses Saga)
- ADR-0007: 4-Stage Planning Pipeline (plans include compensation definitions)
- ADR-0009: Circuit Breaker Pattern (prevents compensation retry storms)
- ADR-0020: Multi-Tier Storage (K0 WAL stores compensation logs)

---

**END OF ADR-0008**
