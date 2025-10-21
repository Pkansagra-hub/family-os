# Saga Rollback Protocol Contracts

**Version:** 1.0.0
**Last Updated:** 2025-10-21
**Source ADRs:** ADR-0003 (MPST Protocol Validation), ADR-0003b (6 Core Protocol Implementations), ADR-0009 (Circuit Breaker Pattern)
**Research Foundation:** Saga Pattern (Garcia-Molina & Salem 1987), Temporal Workflows (Uber 2020)

---

## 📋 Overview

This directory contains comprehensive contracts for the **Saga Rollback Protocol**, which enables distributed transaction error recovery through compensating actions. The saga pattern allows multi-step transactions to roll back gracefully when errors occur, restoring system consistency.

### **Key Concepts**

- **Saga**: Multi-step transaction with compensation for each step
- **Compensation**: Counteracting action to undo a forward step (e.g., cancel booking after payment fails)
- **Rollback**: Execute compensations in reverse order to restore pre-saga state
- **Idempotency**: Compensations must be safe to retry (no duplicate side effects)
- **Partial Rollback**: Some compensations succeed, others fail (requires manual intervention)

---

## 📁 Contract Files

### **1. saga_protocol_fsm.yml**
**Purpose:** 5-state FSM definition for saga execution and rollback

**States:**
- `executing` → Normal forward execution
- `compensating` → Executing compensations (reverse order)
- `rolling_back` → Restoring session state to pre-saga checkpoint
- `rolled_back` → Success terminal state (all compensations complete)
- `failed` → Failure terminal state (compensation timeout or permanent error)
- `partial_rollback` → Partial failure (manual intervention required)

**Transitions:** 9 total (including self-loops for multiple compensation steps)

**Timeout Budgets:**
- Compensation: 5000ms total (ADR-0003b)
- Rollback: 2000ms (restore session state)

**Key Features:**
- FSM validation with guards (e.g., `all_compensations_succeeded`)
- Automatic timeout transitions (COMPENSATING → FAILED after 5s)
- Observability hooks (metrics, traces, logs)

---

### **2. saga_definition_contract.yml**
**Purpose:** Schema for defining sagas (steps, compensations, dependencies)

**Core Structure:**
```yaml
saga_definition:
  saga_id: UUID v4
  saga_name: "hotel_flight_booking_saga"
  saga_type: BOOKING | PAYMENT | WORKFLOW
  steps: [array of SagaStep]
  execution_config:
    execution_mode: SEQUENTIAL | PARALLEL_SAFE
    failure_strategy: FAIL_FAST | CONTINUE_ON_NON_CRITICAL
    compensation_order: REVERSE | EXPLICIT
    circuit_breaker_enabled: true
```

**SagaStep Schema:**
- `step_id`: Unique identifier
- `action`: Forward action (service URL, parameters, timeout)
- `compensation`: Compensation action (service URL, idempotency key, timeout)
- `dependencies`: Array of step IDs that must complete first
- `is_critical`: If true, failure triggers saga rollback
- `retry_policy`: Max retries, backoff strategy

**Dependency Graph Validation:**
- No circular dependencies (DAG validation via topological sort)
- Dependencies must execute before dependent steps
- All referenced step IDs must exist

---

### **3. compensation_request_contract.yml**
**Purpose:** Message contracts for orchestrator → agent compensation requests

**CompensationRequest Schema:**
```yaml
compensation_request:
  compensation_id: UUID v4
  saga_id: UUID v4
  step_id: string
  idempotency_key: UUID v4  # CRITICAL for safe retries
  original_action:
    action_type: CREATE | UPDATE | DELETE | BOOK | CHARGE
    resource_id: string
    action_result: JSON
  compensation_type: UNDO | COMPENSATE | BEST_EFFORT
  compensation_action:
    service_url: URL
    http_method: DELETE | POST | PUT
    parameters: JSON
  timeout_ms: 3000
  retry_policy:
    max_retries: 3
    backoff_strategy: exponential
```

**CompensationResponse Schema:**
```yaml
compensation_response:
  compensation_id: UUID v4
  success: boolean
  compensation_status: COMPLETED | PARTIALLY_COMPLETED | FAILED | SKIPPED
  result_data: JSON
  error_code: TIMEOUT | SERVICE_ERROR | INVALID_STATE
  resource_state_after_compensation: JSON
  is_idempotent: true
  compensation_latency_ms: integer
```

**Special Cases:**
- **Already Compensated**: Return `success=true, status=SKIPPED` (idempotent)
- **Resource Not Found**: Return `success=true, status=NOT_FOUND` (goal achieved)
- **Cannot Compensate**: Return `success=false, status=FAILED, error_code=INVALID_STATE`

---

### **4. rollback_strategy.yml**
**Purpose:** Define rollback strategies and when to apply each

**Three Strategies:**

#### **UNDO Strategy**
- **Description:** Completely undo forward action (DELETE resource)
- **Use Cases:** Resource creation, state transitions
- **Example:** `CREATE booking → DELETE booking`
- **Idempotency:** Natural (deleting non-existent resource = success)

#### **COMPENSATE Strategy**
- **Description:** Counteracting action (may involve multiple steps)
- **Use Cases:** Payment processing, multi-resource operations
- **Example:** `CHARGE payment → REFUND payment + SEND cancellation email`
- **Idempotency:** Explicit (via idempotency key)

#### **BEST_EFFORT Strategy**
- **Description:** Partial rollback with manual intervention
- **Use Cases:** Irreversible operations (email sent, analytics logged)
- **Example:** `SEND email → LOG failure + SEND cancellation email`
- **Idempotency:** Logging is naturally idempotent

**Strategy Selection Decision Tree:**
```
Is action reversible with single API call?
  YES → UNDO
  NO ↓
Does service provide compensation endpoint?
  YES → COMPENSATE
  NO → BEST_EFFORT
```

---

### **5. partial_rollback.yml**
**Purpose:** Handle scenarios where some compensations fail

**Partial Rollback Scenarios:**
1. **Compensation Timeout**: Compensation exceeds 5000ms budget
2. **Service Unavailable**: Compensation endpoint returns 5xx or times out
3. **Permanent Error**: Compensation impossible (e.g., booking already checked in)
4. **Multiple Failures**: 2+ compensations fail (cascading failure)

**Partial Rollback State Tracking:**
```yaml
partial_rollback_state:
  saga_id: UUID v4
  rollback_status: IN_PROGRESS | PARTIAL_SUCCESS | TOTAL_FAILURE
  total_steps_requiring_compensation: 3
  compensations_succeeded: 1
  compensations_failed: 2
  failed_compensation_details: [array of FailedCompensation]
  manual_intervention_required: true
  partial_state_description: "Hotel cancelled, flight NOT cancelled, payment NOT refunded"
  recommended_manual_actions:
    - "Manually cancel flight reservation FL12345"
    - "Process manual refund $500 to card ending in 1234"
```

**Manual Remediation Workflow:**
1. **Triage**: Assess severity, assign to operations team
2. **Verify State**: Check actual resource states in services
3. **Execute Manual Compensations**: Use admin UIs or APIs
4. **Verify Consistency**: Ensure all compensations complete
5. **Notify User**: Send confirmation email
6. **Post-Mortem**: Document root cause, prevent recurrence

---

### **6. idempotency_contracts.yml**
**Purpose:** Ensure compensations are idempotent (safe to retry)

**Why Idempotency is Critical:**
- **Retry Safety**: Compensations retried due to timeouts/transient errors
- **Circuit Breaker**: Circuit may allow probe after timeout
- **Manual Remediation**: Operations may retry compensations
- **At-Least-Once Delivery**: Message queues may redeliver requests

**Idempotency Implementation Strategies:**

#### **1. Idempotency Key (Recommended)**
```python
def compensate(compensation_request):
    key = compensation_request.idempotency_key

    # Check cache
    cached_result = cache.get(key)
    if cached_result:
        return cached_result  # Idempotent duplicate

    # Execute compensation
    result = execute_compensation(compensation_request)

    # Cache result (TTL: 24 hours)
    cache.set(key, result, ttl_seconds=86400)
    return result
```

#### **2. Natural Idempotency (HTTP DELETE/PUT)**
- `DELETE /bookings/{id}` → Naturally idempotent
- `PUT /bookings/{id}/status` → Naturally idempotent

#### **3. Check-Then-Act Pattern**
```python
def cancel_booking(booking_id):
    booking = get_booking(booking_id)

    if booking.status == "CANCELLED":
        return {"success": true, "message": "Already cancelled"}

    booking.status = "CANCELLED"
    save_booking(booking)
    return {"success": true}
```

**Idempotency Testing:**
- **Test 1**: Send same request twice, verify no duplicate side effects
- **Test 2**: Simulate timeout, retry with same key
- **Test 3**: Send 10 concurrent requests, verify compensation executes ONCE
- **Test 4**: Different idempotency keys execute independently

---

### **7. timeout_enforcement.yml**
**Purpose:** Define timeout policies, budgets, and enforcement

**Timeout Hierarchy:**

#### **Level 1: Per-Compensation Timeout (5000ms)**
- **Enforcement**: Orchestrator (client-side)
- **Behavior**: Cancel request, mark FAILED, retry with exponential backoff

#### **Level 2: COMPENSATING State Timeout (5000ms)**
- **Enforcement**: Protocol Monitor (FSM)
- **Behavior**: Transition to FAILED state, alert operations

#### **Level 3: Total Saga Timeout (60000ms)**
- **Enforcement**: Orchestrator (saga-level)
- **Behavior**: ABORT saga, CRITICAL alert, escalate to engineering

**Timeout Budget Rules:**
1. `compensation_timeout_ms >= step_timeout_ms`
2. `compensating.timeout_ms >= SUM(compensation_timeout_ms)`
3. `max_saga_timeout_ms >= forward_time + compensating.timeout_ms`
4. Add 20-50% buffer for network latency

**Timeout Retry Strategy:**
- **Timeout is transient**: Retry up to 3 times
- **Exponential backoff**: 100ms, 200ms, 400ms
- **Same idempotency key**: CRITICAL for retry safety
- **Circuit breaker integration**: Stop retrying if circuit OPEN

---

## 🔄 Saga Rollback Flow Example

### **Scenario: Hotel + Flight Booking Saga**

#### **Forward Execution:**
```
step_1: book_hotel → ✓ Success (booking_id=hotel_123)
step_2: book_flight → ✓ Success (reservation_id=flight_456)
step_3: charge_payment → ✗ FAILED (credit card declined)
```

#### **Compensation (Reverse Order):**
```
Saga transitions to COMPENSATING state
↓
step_2: cancel_flight
  → CompensationRequest(idempotency_key=idem-1, resource_id=flight_456)
  → ✓ Success (flight cancelled)
↓
step_1: cancel_hotel
  → CompensationRequest(idempotency_key=idem-2, resource_id=hotel_123)
  → ✓ Success (hotel cancelled)
↓
Saga transitions to ROLLED_BACK state
Result: System restored to pre-saga state
```

#### **Partial Rollback Scenario:**
```
step_2: cancel_flight → ⏱️ TIMEOUT (5000ms exceeded)
step_1: cancel_hotel → ✓ Success
↓
Saga transitions to PARTIAL_ROLLBACK state
Log to DLQ: "Flight NOT cancelled, hotel cancelled"
Alert operations: HIGH severity
Create remediation ticket: "Manually cancel flight_456"
```

---

## 📊 Metrics & Observability

### **Key Metrics:**
- `saga_initiated_total` — Total sagas started
- `saga_rollback_duration_ms` — Rollback latency histogram
- `compensation_count_per_saga` — Number of compensations per saga
- `compensation_success_rate` — Success rate (rolling 5min)
- `partial_rollback_total` — Partial rollbacks requiring manual intervention
- `compensation_idempotency_hit_total` — Duplicate requests handled via idempotency

### **Alerting Rules:**
- **Any compensation failure** → HIGH (PagerDuty + Slack)
- **Multiple compensation failures** → CRITICAL (escalate to engineering after 30min)
- **Compensation timeout** → HIGH
- **Circuit breaker OPEN during compensation** → CRITICAL

---

## 🧪 Testing Requirements

### **Unit Tests (WARD Framework):**
- All 9 FSM transitions exercised
- Timeout policies trigger correctly
- Guards evaluated correctly (e.g., `all_compensations_succeeded`)

### **Integration Tests:**
- End-to-end saga with 3 compensations
- Compensation timeout → FAILED state
- Rollback timeout → PARTIAL_ROLLBACK state
- Compensation retry with exponential backoff

### **Chaos Tests:**
- Random compensation failures (50% failure rate)
- Network partition during rollback
- Checkpoint corruption (rollback should fail gracefully)

---

## 🔗 Related ADRs

- **ADR-0003**: MPST Protocol Validation (Saga Rollback Protocol definition)
- **ADR-0003b**: 6 Core Protocol Implementations (Saga FSM details)
- **ADR-0009**: Circuit Breaker Pattern (Prevents compensation retry storms)
- **ADR-0002**: Actor Model Foundation (Message passing for compensation requests)
- **ADR-0008**: Saga Pattern for Error Recovery (if exists)

---

## 📚 Research References

1. **Garcia-Molina, H., & Salem, K. (1987)**
   *Sagas. ACM SIGMOD Record, 16(3), 249-259.*
   Original saga pattern — long-running transactions with compensating actions

2. **Temporal.io Workflows (Uber, 2020)**
   Modern implementation with built-in compensation support

3. **Nygard, M. (2007)**
   *Release It! Design and Deploy Production-Ready Software.*
   Circuit breaker prevents compensation retry storms

4. **Richardson, C. (2018)**
   *Microservices Patterns: With Examples in Java.*
   Chapter 4: Saga pattern for distributed transactions

---

## 🚀 Implementation Status

- ✅ **Saga Protocol FSM** — Complete (5 states, 9 transitions)
- ✅ **Saga Definition Schema** — Complete (DAG validation, step dependencies)
- ✅ **Compensation Request/Response** — Complete (idempotency key, retry policy)
- ✅ **Rollback Strategies** — Complete (UNDO, COMPENSATE, BEST_EFFORT)
- ✅ **Partial Rollback Handling** — Complete (manual remediation workflow)
- ✅ **Idempotency Contracts** — Complete (4 strategies, testing requirements)
- ✅ **Timeout Enforcement** — Complete (3-level hierarchy, budget rules)

**Next Steps:**
1. Implement FlatBuffers schemas (`CompensationRequest.fbs`, `CompensationResponse.fbs`)
2. Implement orchestrator saga execution engine
3. Implement Protocol Monitor FSM validation
4. Implement idempotency cache (Redis with AOF persistence)
5. Implement DLQ logging for partial rollbacks
6. Implement manual remediation UI/API

---

## 📝 Usage Example

### **Define Saga:**
```yaml
saga_definition:
  saga_id: "saga-123"
  saga_name: "hotel_flight_booking_saga"
  max_saga_timeout_ms: 60000
  steps:
    - step_id: "step_book_hotel"
      action:
        service_url: "https://hotel-service/api/bookings"
        parameters: {"hotel_id": "hilton_sf", "guests": 2}
      compensation:
        service_url: "https://hotel-service/api/bookings/{id}/cancel"
        timeout_ms: 3000
        idempotent: true
    - step_id: "step_book_flight"
      action:
        service_url: "https://flight-service/api/reservations"
      compensation:
        service_url: "https://flight-service/api/reservations/{id}/cancel"
    - step_id: "step_charge_payment"
      dependencies: ["step_book_hotel", "step_book_flight"]
      action:
        service_url: "https://payment-service/api/charges"
      compensation:
        service_url: "https://payment-service/api/charges/{id}/refund"
```

### **Execute Saga:**
```python
saga = Saga(saga_definition)
result = await saga.execute()

if result.status == "COMPLETED":
    print("Saga succeeded:", result.final_state)
elif result.status == "FAILED":
    print("Saga failed, rolled back:", result.compensation_summary)
elif result.status == "PARTIALLY_FAILED":
    print("Partial rollback, manual intervention required:", result.remediation_steps)
```

---

## 📞 Support

**For questions or issues:**
- Review ADR-0003, ADR-0003b, ADR-0009
- Check `docs/whiteboard.md` (Saga Pattern section)
- Consult architecture team

**Document Version:** 1.0.0
**Last Updated:** 2025-10-21
**Maintained by:** K1 Architecture Team
