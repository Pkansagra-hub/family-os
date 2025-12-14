---
adr_number: 0008a
title: Compensating Transaction Design
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer3_execution
- layer4_runtime
affected_modules:
- k1.l2_orchestration.saga.compensating_actions
- k1.l2_orchestration.saga.transaction_registry
- k1.l2_orchestration.saga.semantic_undo
- k1.l3_execution.flow_engine.compensation_handler
- k1.l4_runtime.sessionstate.compensation_state
- k1.l5_infrastructure.persistence.compensation_log
concerns:
- architecture
- compliance
- modularity
- performance
- privacy
- reliability
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001a
- ADR-0006d
- ADR-0008
- ADR-0008a
- ADR-0008b
- ADR-0008c
implementation_status: COMPLETED
implementation_date: '2025-02-05'
implementation_phase: MVP
related_contracts:
- k1/contracts/flatbuffers/layer2_orchestration/compensating_transaction.fbs
- k1/contracts/flatbuffers/layer2_orchestration/transaction_registry.fbs
- k1/contracts/flatbuffers/layer2_orchestration/semantic_undo.fbs
- k1/contracts/flatbuffers/layer3_execution/compensation_handler.fbs
- k1/contracts/flatbuffers/layer4_runtime/compensation_state.fbs
- k1/contracts/flatbuffers/layer5_infrastructure/compensation_log.fbs
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
related_diagrams:
- k1_compensating_transaction_design
- k1_transaction_registry_architecture
- k1_semantic_undo_mechanism
- k1_compensation_handler_flow
- k1_compensation_state_management
- k1_compensation_log_persistence
research_citations:
- "Sagas" by Hector Garcia-Molina and Kenneth Salem (1987)
- "The Transaction Concept: Virtues and Limitations" by Jim Gray (1981)
- "Database System Concepts" by Abraham Silberschatz et al. (1990)
- "Compensating Transactions" by Henry F. Korth et al. (1990)
- "Semantic-Based Transaction Management" by Gerhard Weikum (1991)
- "Long-Running Transactions in Workflow Systems" by Frank Leymann and Dieter Roller (1999)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0001a
  - ADR-0006d
  - ADR-0008
  - ADR-0008a
  - ADR-0008b
  - ADR-0008c
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
  affected_tests:
- tests/k1/l2_orchestration/test_compensating_actions.py
- tests/k1/l2_orchestration/test_transaction_registry.py
- tests/k1/l2_orchestration/test_semantic_undo.py
- tests/k1/l3_execution/test_compensation_handler.py
- tests/k1/l4_runtime/test_compensation_state.py
- tests/k1/l5_infrastructure/test_compensation_log.py
- tests/integration/test_compensation_flow.py
- tests/performance/test_compensation_latency.py
---


# ADR-0008a: Compensating Transaction Design

**Status:** ✅ Approved (2025-10-12)
**Parent ADR:** [ADR-0008: Saga Pattern Error Recovery](./0008-saga-pattern-error-recovery.md)
**Related ADRs:**
- [ADR-0008b: Forward Recovery vs Backward Recovery](./0008b-forward-recovery-vs-backward-recovery.md) - Recovery strategy selection
- [ADR-0008c: Distributed State Management](./0008c-distributed-state-management.md) - Saga log persistence
- [ADR-0006d: Saga Pattern Integration for Phase 3](./0006d-saga-pattern-integration-phase3-error-recovery.md) - Saga coordinator
- [ADR-0001a: K0 Bridge Communication Protocol](./0001a-k0-bridge-communication-protocol.md) - Audit trail persistence

**Research Citations:**
- Garcia-Molina & Salem (1987) - Sagas: Long-lived database transactions
- Gray (1981) - The transaction concept: Virtues and limitations
- Compensating transactions (Korth et al. 1990) - Semantic-based transaction management

---

## Context & Problem Statement

### Current State
When multi-step plans fail mid-execution (e.g., Step 3 of 5 fails), the system has **no mechanism to undo completed steps**, leaving the system in an inconsistent state:
- ❌ No compensation handlers defined for reversible operations
- ❌ No idempotency tracking (compensations may run multiple times)
- ❌ No audit trail for compensation attempts
- ❌ Partial state leaks (e.g., booking created but payment failed → booking never cancelled)

**Example Failure Scenario:**
```
Plan: Book hotel + Reserve flight + Charge payment
Execution:
  1. ✅ Book hotel (hotel_booking_id = 123)
  2. ✅ Reserve flight (flight_reservation_id = 456)
  3. ❌ Charge payment (payment declined)

Current behavior: Hotel + flight reserved, no payment → Partial state leak
Desired behavior: Cancel flight + hotel (compensations) → Clean state
```

### Problem Statement
**How do we design compensating transactions for all tools with side effects to enable graceful rollback of completed steps while ensuring idempotency and providing audit trails?**

### Key Challenges

1. **Compensation Coverage (50+ tools):**
   - Must define compensations for all tools with side effects
   - Some tools are non-reversible (e.g., sent email - recall is best-effort)
   - Read-only tools need no-op compensations

2. **Idempotency:**
   - Compensations may run multiple times (crash recovery)
   - Must prevent double-cancellation (e.g., refund payment twice)
   - 5-minute deduplication window sufficient?

3. **Compensation Latency:**
   - Target: <3s per compensation (default timeout)
   - Total rollback: <15s for 5-step plan
   - Best-effort execution (continue on compensation failure)

4. **Audit Trail:**
   - All compensation attempts logged to K0 WAL
   - Query: "Show me all compensations for saga X"
   - Compliance: GDPR, SOC2 require audit logs

---

## Decision

### Overview
Implement **compensating transaction design** with 4 components:
1. **Compensation Handler Pattern** (3 handler types: tool-based, API-based, custom)
2. **Compensation Registry** (50+ tools with compensation metadata)
3. **Idempotent Execution** (Redis deduplication, 5-minute window)
4. **Audit Trail** (K0 WAL persistence for all compensation attempts)

---

### Component 1: Compensation Handler Pattern

**Purpose:** Define standard patterns for compensation handlers.

#### **Handler Type 1: Tool-Based Compensation**

**Pattern:** Use existing tool as compensation (e.g., DELETE API call).

**Example: Cancel Hotel Booking**
```python
@dataclass
class ToolCompensation:
    """Tool-based compensation handler"""
    tool_id: str
    params_mapping: Dict[str, str]  # Map step result to compensation params
    timeout_ms: int = 3000

# Original step
step = PlanStep(
    step_id=0,
    action="book_hotel",
    tool="booking_api",
    parameters={"hotel_id": "H123", "check_in": "2025-10-15"},
    compensation=ToolCompensation(
        tool_id="cancel_booking",
        params_mapping={
            "booking_id": "result.booking_id"  # Extract from step result
        }
    )
)

# Compensation execution
async def compensate_tool_based(
    step: PlanStep,
    step_result: StepResult,
    trace_id: str
) -> CompensationResult:
    """Execute tool-based compensation"""
    compensation = step.compensation

    # Map parameters from step result
    params = {}
    for param_name, mapping_expr in compensation.params_mapping.items():
        params[param_name] = eval_mapping(mapping_expr, step_result)

    # Execute compensation tool
    comp_result = await tool_runner.run_tool(
        tool_id=compensation.tool_id,
        parameters=params,
        timeout_ms=compensation.timeout_ms,
        trace_id=trace_id
    )

    return CompensationResult(
        step_id=step.step_id,
        success=(comp_result.status == "SUCCESS"),
        latency_ms=comp_result.latency_ms
    )
```

---

#### **Handler Type 2: API-Based Compensation**

**Pattern:** Custom HTTP endpoint for rollback.

**Example: Refund Payment**
```python
@dataclass
class APICompensation:
    """API-based compensation handler"""
    endpoint: str
    method: str  # GET, POST, DELETE, etc.
    payload_mapping: Dict[str, str]
    timeout_ms: int = 3000

# Original step
step = PlanStep(
    step_id=2,
    action="charge_payment",
    tool="payment_api",
    parameters={"amount": 100.00, "card_token": "tok_abc"},
    compensation=APICompensation(
        endpoint="https://payment-api.com/v1/refund",
        method="POST",
        payload_mapping={
            "transaction_id": "result.transaction_id",
            "amount": "result.amount",
            "reason": "'Saga compensation'"
        }
    )
)

# Compensation execution
async def compensate_api_based(
    step: PlanStep,
    step_result: StepResult,
    trace_id: str
) -> CompensationResult:
    """Execute API-based compensation"""
    compensation = step.compensation

    # Map payload from step result
    payload = {}
    for field_name, mapping_expr in compensation.payload_mapping.items():
        payload[field_name] = eval_mapping(mapping_expr, step_result)

    # Execute HTTP request
    async with aiohttp.ClientSession() as session:
        response = await session.request(
            method=compensation.method,
            url=compensation.endpoint,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=compensation.timeout_ms / 1000),
            headers={"X-Trace-ID": trace_id}
        )

    return CompensationResult(
        step_id=step.step_id,
        success=(response.status in [200, 201, 204]),
        latency_ms=response.elapsed.total_seconds() * 1000
    )
```

---

#### **Handler Type 3: Custom Compensation**

**Pattern:** Application-specific logic (e.g., complex rollback).

**Example: Rollback Database Write**
```python
@dataclass
class CustomCompensation:
    """Custom compensation handler"""
    handler_function: str  # Module path to handler
    params_mapping: Dict[str, str]
    timeout_ms: int = 3000

# Original step
step = PlanStep(
    step_id=1,
    action="update_user_profile",
    tool="database_write",
    parameters={"user_id": "U123", "field": "email", "value": "new@email.com"},
    compensation=CustomCompensation(
        handler_function="k1.compensation.handlers.rollback_database_write",
        params_mapping={
            "user_id": "step.parameters.user_id",
            "field": "step.parameters.field",
            "old_value": "result.old_value"  # Database returns old value
        }
    )
)

# Custom handler implementation
async def rollback_database_write(
    user_id: str,
    field: str,
    old_value: str,
    trace_id: str
) -> CompensationResult:
    """Custom handler: Restore old database value"""
    # Execute UPDATE with old value
    query = f"UPDATE users SET {field} = %s WHERE user_id = %s"
    await db.execute(query, (old_value, user_id))

    return CompensationResult(
        success=True,
        latency_ms=12
    )
```

---

#### **Handler Type 4: No-Op Compensation**

**Pattern:** Read-only tools have no side effects (no compensation needed).

**Example: Search Web**
```python
@dataclass
class NoOpCompensation:
    """No-op compensation (read-only tool)"""
    pass

# Original step
step = PlanStep(
    step_id=0,
    action="search_hotels",
    tool="search_web",
    parameters={"query": "hotels in Paris"},
    compensation=NoOpCompensation()  # No compensation needed
)

# Compensation execution
async def compensate_noop(
    step: PlanStep,
    step_result: StepResult,
    trace_id: str
) -> CompensationResult:
    """No-op compensation (read-only)"""
    return CompensationResult(
        step_id=step.step_id,
        success=True,
        latency_ms=0
    )
```

---

### Component 2: Compensation Registry (50+ Tools)

**Purpose:** Central registry of compensation handlers for all tools.

**Registry Structure:**
```python
class CompensationRegistry:
    """Global registry of compensation handlers"""

    def __init__(self):
        self.handlers: Dict[str, CompensationHandler] = {}
        self._initialize_handlers()

    def _initialize_handlers(self):
        """Register all compensation handlers"""

        # Booking tools
        self.register("book_hotel", ToolCompensation(
            tool_id="cancel_booking",
            params_mapping={"booking_id": "result.booking_id"}
        ))

        self.register("reserve_flight", ToolCompensation(
            tool_id="cancel_flight",
            params_mapping={"reservation_id": "result.reservation_id"}
        ))

        # Calendar tools
        self.register("create_event", ToolCompensation(
            tool_id="delete_event",
            params_mapping={"event_id": "result.event_id"}
        ))

        # Payment tools
        self.register("charge_payment", APICompensation(
            endpoint="https://payment-api.com/v1/refund",
            method="POST",
            payload_mapping={
                "transaction_id": "result.transaction_id",
                "amount": "result.amount"
            }
        ))

        # File tools
        self.register("write_file", ToolCompensation(
            tool_id="delete_file",
            params_mapping={"file_id": "result.file_id"}
        ))

        # Email tools (best-effort)
        self.register("send_email", APICompensation(
            endpoint="https://email-api.com/v1/recall",
            method="POST",
            payload_mapping={
                "message_id": "result.message_id",
                "reason": "'Saga compensation (best-effort)'"
            }
        ))

        # Database tools
        self.register("database_write", CustomCompensation(
            handler_function="k1.compensation.handlers.rollback_database_write",
            params_mapping={
                "table": "step.parameters.table",
                "record_id": "step.parameters.record_id",
                "old_value": "result.old_value"
            }
        ))

        # Read-only tools (no-op)
        for tool_id in ["search_web", "read_file", "get_weather", "list_files"]:
            self.register(tool_id, NoOpCompensation())

    def register(self, tool_id: str, handler: CompensationHandler):
        """Register compensation handler for tool"""
        self.handlers[tool_id] = handler

    def get_handler(self, tool_id: str) -> CompensationHandler:
        """Get compensation handler for tool"""
        if tool_id not in self.handlers:
            logger.warning(f"No compensation handler for tool: {tool_id}")
            return NoOpCompensation()  # Default to no-op
        return self.handlers[tool_id]
```

**Complete Registry (50+ Tools):**

| Tool Category | Tool ID | Compensation Handler | Type | Timeout |
|--------------|---------|---------------------|------|---------|
| **Booking** | book_hotel | cancel_booking | Tool | 3s |
| | reserve_flight | cancel_flight | Tool | 3s |
| | book_restaurant | cancel_reservation | Tool | 3s |
| **Calendar** | create_event | delete_event | Tool | 3s |
| | update_event | restore_event | Custom | 3s |
| **Payment** | charge_payment | refund_payment | API | 5s |
| | void_transaction | void_payment | API | 5s |
| **File** | write_file | delete_file | Tool | 3s |
| | upload_file | delete_upload | Tool | 3s |
| | delete_file | restore_file | Custom | 3s |
| **Email** | send_email | recall_email | API | 10s |
| **Database** | database_write | rollback_write | Custom | 3s |
| | database_delete | restore_record | Custom | 3s |
| **Read-Only** | search_web | no-op | NoOp | 0s |
| | read_file | no-op | NoOp | 0s |
| | get_weather | no-op | NoOp | 0s |

---

### Component 3: Idempotent Compensation Execution

**Purpose:** Prevent duplicate compensations through deduplication.

**Idempotency Key Generation:**
```python
def generate_compensation_idempotency_key(
    saga_id: str,
    step_id: int,
    compensation_id: str
) -> str:
    """
    Generate idempotency key for compensation.

    Key = saga_id:step_id:compensation_id
    Scope: Single compensation execution
    Window: 5 minutes (deduplication)
    """
    return f"{saga_id}:{step_id}:{compensation_id}"
```

**Idempotency Check (Redis):**
```python
async def execute_compensation_idempotent(
    step: PlanStep,
    step_result: StepResult,
    saga_id: str,
    trace_id: str
) -> CompensationResult:
    """
    Execute compensation with idempotency check.

    1. Generate idempotency key
    2. Check Redis cache (5-minute TTL)
    3. If key exists → Skip compensation (return cached result)
    4. If key not exists → Execute compensation + cache result
    """
    # Generate idempotency key
    idempotency_key = generate_compensation_idempotency_key(
        saga_id=saga_id,
        step_id=step.step_id,
        compensation_id=step.compensation.id
    )

    # Check Redis cache
    cached_result = await redis.get(idempotency_key)
    if cached_result is not None:
        logger.info(
            "compensation_duplicate_skipped",
            saga_id=saga_id,
            step_id=step.step_id,
            trace_id=trace_id
        )
        return CompensationResult.from_json(cached_result)

    # Execute compensation
    comp_result = await execute_compensation(step, step_result, trace_id)

    # Cache result (5-minute TTL)
    await redis.setex(
        key=idempotency_key,
        time=300,  # 5 minutes
        value=comp_result.to_json()
    )

    return comp_result
```

**Performance:**
- Idempotency check: <1ms (Redis GET)
- Cache write: <1ms (Redis SETEX)
- Total overhead: <2ms

---

### Component 4: Audit Trail (K0 WAL Persistence)

**Purpose:** Log all compensation attempts for audit and debugging.

**Compensation Log Schema (FlatBuffers):**
```flatbuffers
// compensation_log.fbs
namespace K1.Saga;

table CompensationLog {
  compensation_id: string;
  saga_id: string;
  step_id: int;
  tool_id: string;
  compensation_type: string;  // TOOL, API, CUSTOM, NOOP

  // Execution metadata
  started_at: long;
  completed_at: long;
  latency_ms: int;

  // Result
  success: bool;
  error_message: string;

  // Audit metadata
  trace_id: string;
  session_id: string;
  space: string;
}

root_type CompensationLog;
```

**K0 WAL Write:**
```python
async def log_compensation_to_k0(
    compensation_result: CompensationResult,
    saga_id: str,
    step: PlanStep,
    session_id: str,
    trace_id: str
) -> None:
    """
    Write compensation log to K0 WAL.

    Topic: COMPENSATION_LOG
    Retention: 30 days (audit compliance)
    """
    # Serialize to FlatBuffers
    comp_log_bytes = serialize_compensation_log(
        compensation_id=str(uuid.uuid4()),
        saga_id=saga_id,
        step_id=step.step_id,
        tool_id=step.tool,
        compensation_type=type(step.compensation).__name__,
        started_at=compensation_result.started_at,
        completed_at=compensation_result.completed_at,
        latency_ms=compensation_result.latency_ms,
        success=compensation_result.success,
        error_message=compensation_result.error_message or "",
        trace_id=trace_id,
        session_id=session_id
    )

    # Write to K0 WAL
    await k0_client.write_to_wal(
        topic="COMPENSATION_LOG",
        payload=comp_log_bytes,
        idempotency_key=f"{saga_id}:{step.step_id}:{trace_id}"
    )
```

**Query Compensations:**
```python
async def query_compensations_for_saga(saga_id: str) -> List[CompensationLog]:
    """Query all compensations for a saga (audit trail)"""
    return await k0_client.query(
        topic="COMPENSATION_LOG",
        filter={"saga_id": saga_id},
        limit=100
    )
```

---

## Performance Analysis

### Latency Breakdown

| Component | Latency (P95) |
|-----------|---------------|
| Idempotency check | <1ms |
| Compensation execution | <3s |
| K0 audit log write | <5ms |
| **Total per compensation** | **~3s** |

**Total Saga Rollback (5 steps):** ~15s (5 × 3s)

---

## Canonical Values

```yaml
# k1/config/saga.yml
saga:
  compensation:
    # Default timeout per compensation
    default_timeout_ms: 3000

    # Best-effort execution
    best_effort: true  # Continue on compensation failure

    # Idempotency
    idempotency_enabled: true
    idempotency_window_seconds: 300  # 5 minutes
    redis_host: "localhost"
    redis_port: 6379

    # Audit trail
    audit_enabled: true
    wal_topic: "COMPENSATION_LOG"
    retention_days: 30
```

---

## Conclusion

Compensating Transaction Design provides:
1. **50+ compensation handlers** (tool-based, API-based, custom, no-op)
2. **Idempotent execution** (Redis deduplication, 5-minute window)
3. **Audit trail** (K0 WAL persistence, 30-day retention)
4. **<15s rollback** for 5-step plans

**Next step:** Proceed to **0008b (Forward Recovery vs Backward Recovery)**.
