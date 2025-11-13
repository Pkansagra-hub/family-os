---
adr_number: 0008c
title: Distributed State Management
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
affected_modules:
- k1.l2_orchestration.saga.distributed_state
- k1.l3_execution.flow_engine.state_manager
- k1.l4_runtime.session_state.distributed_store
- k1.l5_infrastructure.storage.distributed_kv
- k1.l5_infrastructure.consensus.paxos_coordinator
- k0.storage.distributed_state
- k0.kernel.state_replication
concerns:
- architecture
- compliance
- observability
- performance
- privacy
- reliability
- scalability
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001a
- ADR-0008
- ADR-0008a
- ADR-0008b
- ADR-0008c
- ADR-0008d
implementation_status: COMPLETED
implementation_date: '2025-11-03'
implementation_phase: 'Phase 1'
related_contracts:
- k1/contracts/flatbuffers/layer2_orchestration/distributed_state.fbs
- k1/contracts/flatbuffers/layer3_execution/state_replication.fbs
- k1/contracts/flatbuffers/layer4_runtime/consensus_protocol.fbs
- k1/contracts/flatbuffers/layer5_infrastructure/distributed_kv.fbs
- k0/contracts/api/rest/state_management.yml
- k0/contracts/asyncapi.state_events.yaml
related_diagrams:
- k1_distributed_state_management
- k1_saga_state_replication
- k0_k1_state_boundary
- k1_consensus_protocol_flow
research_citations:
- CAP Theorem (Brewer 2000) - Consistency, Availability, Partition tolerance trade-offs
- Paxos Made Simple (Lamport 1998) - Consensus algorithm for distributed systems
- Raft Consensus Algorithm (Ongaro & Ousterhout 2014) - Understandable consensus algorithm
- Distributed Systems: Concepts and Design (Coulouris et al. 2011) - Comprehensive distributed systems textbook
- Write-Ahead Logging (WAL) (Gray & Reuter 1993) - Transaction processing fundamentals
- At-least-once delivery (Apache Kafka docs) - Message delivery semantics for state updates
- Crash recovery (ARIES algorithm, Mohan et al. 1992) - Database recovery techniques
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0001a
  - ADR-0008
  - ADR-0008a
  - ADR-0008b
  - ADR-0008c
  - ADR-0008d
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
- tests/k1/l2_orchestration/test_distributed_state_manager.py
- tests/k1/l3_execution/test_state_replication.py
- tests/k1/l4_runtime/test_consensus_protocol.py
- tests/k1/l5_infrastructure/test_distributed_kv.py
- tests/k0/storage/test_distributed_state.py
- tests/integration/test_saga_state_consistency.py
---


# ADR-0008c: Distributed State Management

**Status:** ✅ Approved (2025-10-12)
**Parent ADR:** [ADR-0008: Saga Pattern Error Recovery](./0008-saga-pattern-error-recovery.md)
**Related ADRs:**
- [ADR-0008a: Compensating Transaction Design](./0008a-compensating-transaction-design.md) - Idempotent compensations
- [ADR-0008b: Forward Recovery vs Backward Recovery](./0008b-forward-recovery-vs-backward-recovery.md) - Recovery strategies
- [ADR-0008d: Timeout & Deadlock Handling](./0008d-timeout-deadlock-handling.md) - Timeout hierarchy
- [ADR-0001a: K0 Bridge Communication Protocol](./0001a-k0-bridge-communication-protocol.md) - K0 WAL persistence

**Research Citations:**
- Write-Ahead Logging (WAL) (Gray & Reuter 1993) - Transaction processing
- At-least-once delivery (Apache Kafka docs) - Message delivery semantics
- Crash recovery (ARIES algorithm, Mohan et al. 1992) - Database recovery

---

## Context & Problem Statement

### Current State
Saga execution state is **ephemeral (in-memory only)**, causing state loss on crashes:
- ❌ No durable saga log (state lost if K1 crashes)
- ❌ No crash recovery (orphaned sagas never complete)
- ❌ No heartbeat mechanism (can't detect crashed sagas)
- ❌ No compensation replay (compensations lost after crash)

**Example Crash Scenario:**
```
Saga execution:
  1. ✅ Step 1 complete (book hotel)
  2. ✅ Step 2 complete (reserve flight)
  3. ❌ Step 3 fails (charge payment)
  4. 🔄 Start compensation (cancel flight)
  5. 💥 K1 CRASHES (mid-compensation)

Current behavior: Saga state lost, hotel booking never cancelled
Desired behavior: Recovery coordinator detects crash → Resume compensation → Cancel hotel
```

### Problem Statement
**How do we persist saga execution state to K0 WAL for crash recovery while ensuring at-least-once compensation delivery and preventing orphaned sagas?**

### Key Challenges

1. **Durability:**
   - All saga state changes must be written to K0 WAL
   - Write frequency: After every step completion (real-time)
   - Retention: 7 days (configurable)

2. **Crash Recovery:**
   - Detect crashed sagas (no heartbeat for 60s)
   - Resume compensation from compensation_stack
   - At-least-once delivery (compensations may run multiple times)

3. **Heartbeat Mechanism:**
   - Saga coordinator sends heartbeat every 10s
   - K0 marks saga CRASHED if no heartbeat for 60s
   - Recovery coordinator scans for CRASHED sagas every 30s

4. **Orphan Cleanup:**
   - Abort sagas older than 24 hours with no progress
   - Prevent resource leaks

---

## Decision

### Overview
Implement **distributed state management** with 4 components:
1. **Saga Log Structure** (state, steps, compensation stack)
2. **K0 WAL Persistence** (durable saga state, 7-day retention)
3. **Saga Recovery Coordinator** (crash detection, compensation replay)
4. **Heartbeat Mechanism** (liveness detection, orphan cleanup)

---

### Component 1: Saga Log Structure

**Purpose:** Define saga execution state for persistence.

**Saga Log Schema (FlatBuffers):**
```flatbuffers
// saga_log.fbs
namespace K1.Saga;

table StepResult {
  step_id: int;
  tool_id: string;
  status: string;  // SUCCESS, FAILURE
  result_data: string;  // JSON serialized result
  latency_ms: int;
  error_message: string;
}

table CompensationAction {
  step_id: int;
  tool_id: string;
  compensation_type: string;  // TOOL, API, CUSTOM, NOOP
  params: string;  // JSON serialized params
}

table SagaLog {
  saga_id: string;
  flow_id: string;
  session_id: string;
  space: string;

  // State machine
  state: string;  // EXECUTING, COMPENSATING, COMPLETED, ABORTED, CRASHED

  // Execution progress
  steps_completed: [StepResult];
  steps_pending: [int];  // Step IDs
  current_step_id: int;

  // Compensation stack (LIFO)
  compensation_stack: [CompensationAction];

  // Timestamps
  created_at: long;
  updated_at: long;
  last_heartbeat_at: long;

  // Audit metadata
  trace_id: string;
}

root_type SagaLog;
```

**Saga State Machine:**
```python
class SagaState(Enum):
    """Saga execution states"""
    EXECUTING = "EXECUTING"           # Normal execution
    COMPENSATING = "COMPENSATING"     # Rolling back
    COMPLETED = "COMPLETED"           # All steps succeeded
    ABORTED = "ABORTED"              # All compensations complete
    CRASHED = "CRASHED"              # K1 crashed, needs recovery
```

**State Transitions:**
```python
def get_valid_transitions() -> Dict[SagaState, List[SagaState]]:
    """Valid saga state transitions"""
    return {
        SagaState.EXECUTING: [
            SagaState.COMPLETED,      # All steps succeed
            SagaState.COMPENSATING,   # Step fails, start rollback
            SagaState.CRASHED         # K1 crashes
        ],
        SagaState.COMPENSATING: [
            SagaState.ABORTED,        # All compensations complete
            SagaState.CRASHED         # K1 crashes mid-compensation
        ],
        SagaState.CRASHED: [
            SagaState.COMPENSATING,   # Recovery resumes
            SagaState.ABORTED         # Recovery completes
        ],
        SagaState.COMPLETED: [],      # Terminal state
        SagaState.ABORTED: []         # Terminal state
    }
```

---

### Component 2: K0 WAL Persistence

**Purpose:** Write saga state to K0 WAL after every state change.

**Write Frequency:**
```python
async def update_saga_log(
    saga_log: SagaLog,
    event_type: str
) -> None:
    """
    Write saga log to K0 WAL.

    Write frequency:
    - After every step completion (real-time)
    - After every state transition
    - After every heartbeat (every 10s)

    Topic: SAGA_LOG
    Retention: 7 days
    """
    # Serialize to FlatBuffers
    saga_log_bytes = serialize_saga_log(saga_log)

    # Write to K0 WAL
    await k0_client.write_to_wal(
        topic="SAGA_LOG",
        payload=saga_log_bytes,
        idempotency_key=saga_log.saga_id,  # Prevent duplicate writes
        headers={
            "X-Event-Type": event_type,  # STEP_COMPLETED, STATE_TRANSITION, HEARTBEAT
            "X-Saga-ID": saga_log.saga_id,
            "X-Trace-ID": saga_log.trace_id
        }
    )

    logger.info(
        "saga_log_written",
        saga_id=saga_log.saga_id,
        state=saga_log.state,
        event_type=event_type,
        trace_id=saga_log.trace_id
    )
```

**Write Events:**
```python
class SagaLogEvent:
    """Saga log write events"""
    SAGA_CREATED = "SAGA_CREATED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_FAILED = "STEP_FAILED"
    COMPENSATION_STARTED = "COMPENSATION_STARTED"
    COMPENSATION_COMPLETED = "COMPENSATION_COMPLETED"
    STATE_TRANSITION = "STATE_TRANSITION"
    HEARTBEAT = "HEARTBEAT"
    SAGA_COMPLETED = "SAGA_COMPLETED"
    SAGA_ABORTED = "SAGA_ABORTED"
```

**Performance:**
- Saga log write: <5ms (K0 WAL)
- Write frequency: Every step completion + every 10s (heartbeat)
- Retention: 7 days (configurable)

---

### Component 3: Saga Recovery Coordinator

**Purpose:** Detect crashed sagas and resume compensation.

**Crash Detection:**
```python
class SagaRecoveryCoordinator:
    """Detect and recover crashed sagas"""

    def __init__(self):
        self.scan_interval_seconds = 30
        self.crash_timeout_seconds = 60
        self.orphan_timeout_hours = 24

    async def start_recovery_loop(self):
        """Scan for crashed sagas every 30s"""
        while True:
            await asyncio.sleep(self.scan_interval_seconds)

            # Query K0 for potentially crashed sagas
            crashed_sagas = await self._query_crashed_sagas()

            # Recover each crashed saga
            for saga_log in crashed_sagas:
                await self._recover_saga(saga_log)

    async def _query_crashed_sagas(self) -> List[SagaLog]:
        """
        Query K0 for crashed sagas.

        Criteria:
        1. State = EXECUTING or COMPENSATING
        2. No heartbeat for 60s (crashed)
        3. Not older than 24 hours (orphan cleanup)
        """
        now = time.time() * 1000  # Unix timestamp (ms)
        crash_threshold = now - (self.crash_timeout_seconds * 1000)
        orphan_threshold = now - (self.orphan_timeout_hours * 3600 * 1000)

        # Query K0 SAGA_LOG topic
        saga_logs = await k0_client.query(
            topic="SAGA_LOG",
            filter={
                "state": ["EXECUTING", "COMPENSATING"],
                "last_heartbeat_at": {"$lt": crash_threshold},
                "created_at": {"$gt": orphan_threshold}
            },
            limit=100
        )

        return saga_logs

    async def _recover_saga(self, saga_log: SagaLog) -> None:
        """
        Recover crashed saga.

        Recovery steps:
        1. Mark saga as CRASHED
        2. Resume compensation from compensation_stack
        3. Execute compensations in reverse order (LIFO)
        4. Mark saga as ABORTED when complete
        """
        logger.info(
            "saga_crash_detected",
            saga_id=saga_log.saga_id,
            last_heartbeat=saga_log.last_heartbeat_at,
            trace_id=saga_log.trace_id
        )

        # Mark saga as CRASHED
        saga_log.state = SagaState.CRASHED
        await update_saga_log(saga_log, SagaLogEvent.STATE_TRANSITION)

        # Resume compensation
        if saga_log.state in [SagaState.EXECUTING, SagaState.CRASHED]:
            # Transition to COMPENSATING
            saga_log.state = SagaState.COMPENSATING
            await update_saga_log(saga_log, SagaLogEvent.STATE_TRANSITION)

            # Execute compensations (reverse order)
            for compensation in reversed(saga_log.compensation_stack):
                try:
                    await execute_compensation_action(
                        compensation=compensation,
                        saga_id=saga_log.saga_id,
                        trace_id=saga_log.trace_id
                    )
                except Exception as e:
                    # Best-effort: Log failure, continue
                    logger.error(
                        "recovery_compensation_failed",
                        saga_id=saga_log.saga_id,
                        step_id=compensation.step_id,
                        error=str(e),
                        trace_id=saga_log.trace_id
                    )

        # Mark saga as ABORTED
        saga_log.state = SagaState.ABORTED
        saga_log.updated_at = int(time.time() * 1000)
        await update_saga_log(saga_log, SagaLogEvent.SAGA_ABORTED)

        logger.info(
            "saga_recovery_complete",
            saga_id=saga_log.saga_id,
            trace_id=saga_log.trace_id
        )
```

**At-Least-Once Delivery:**
```python
# Compensations may run multiple times after crash recovery
# Idempotency (0008a) prevents duplicate compensations:
# - Redis cache (5-minute TTL) for deduplication
# - Idempotency key: saga_id:step_id:compensation_id
```

**Performance:**
- Crash detection: 60s max (heartbeat timeout)
- Recovery scan: every 30s (low overhead)
- At-least-once delivery: Compensations may run 1-3 times

---

### Component 4: Heartbeat Mechanism

**Purpose:** Liveness detection to identify crashed sagas.

**Heartbeat Sender (Saga Coordinator):**
```python
class SagaCoordinator:
    """Saga coordinator with heartbeat"""

    def __init__(self, saga_log: SagaLog):
        self.saga_log = saga_log
        self.heartbeat_interval_seconds = 10
        self._heartbeat_task = None

    async def start_heartbeat(self):
        """Start heartbeat loop (every 10s)"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self):
        """Stop heartbeat loop"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

    async def _heartbeat_loop(self):
        """Send heartbeat every 10s"""
        while True:
            try:
                # Update heartbeat timestamp
                self.saga_log.last_heartbeat_at = int(time.time() * 1000)

                # Write to K0 WAL
                await update_saga_log(self.saga_log, SagaLogEvent.HEARTBEAT)

                # Wait 10s
                await asyncio.sleep(self.heartbeat_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "heartbeat_failed",
                    saga_id=self.saga_log.saga_id,
                    error=str(e)
                )
```

**Heartbeat Monitoring:**
```python
def is_saga_crashed(saga_log: SagaLog, now_ms: int) -> bool:
    """
    Check if saga is crashed (no heartbeat for 60s).

    Criteria:
    - State = EXECUTING or COMPENSATING
    - No heartbeat for 60s
    """
    crash_threshold_ms = 60 * 1000  # 60s

    if saga_log.state not in [SagaState.EXECUTING, SagaState.COMPENSATING]:
        return False

    time_since_heartbeat_ms = now_ms - saga_log.last_heartbeat_at
    return time_since_heartbeat_ms > crash_threshold_ms
```

**Orphan Cleanup:**
```python
async def cleanup_orphaned_sagas():
    """
    Clean up orphaned sagas (older than 24 hours with no progress).

    Criteria:
    - State = EXECUTING or COMPENSATING
    - Created > 24 hours ago
    - Mark as ABORTED
    """
    now_ms = int(time.time() * 1000)
    orphan_threshold_ms = 24 * 3600 * 1000  # 24 hours

    # Query orphaned sagas
    orphaned_sagas = await k0_client.query(
        topic="SAGA_LOG",
        filter={
            "state": ["EXECUTING", "COMPENSATING"],
            "created_at": {"$lt": now_ms - orphan_threshold_ms}
        }
    )

    # Mark as ABORTED
    for saga_log in orphaned_sagas:
        saga_log.state = SagaState.ABORTED
        saga_log.updated_at = now_ms
        await update_saga_log(saga_log, SagaLogEvent.SAGA_ABORTED)

        logger.warning(
            "orphaned_saga_aborted",
            saga_id=saga_log.saga_id,
            age_hours=(now_ms - saga_log.created_at) / 3600000
        )
```

---

## Performance Analysis

### Latency Breakdown

| Component | Latency |
|-----------|---------|
| Saga log write | <5ms |
| Heartbeat write | <5ms |
| Crash detection | 60s max |
| Recovery scan | every 30s |

---

## Canonical Values

```yaml
# k1/config/saga.yml
saga:
  state:
    # K0 WAL persistence
    wal_topic: "SAGA_LOG"
    retention_days: 7
    write_timeout_ms: 5000

    # Heartbeat
    heartbeat_interval_ms: 10000     # 10s
    crash_detection_ms: 60000        # 60s no heartbeat = crashed

    # Recovery coordinator
    recovery_scan_interval_ms: 30000 # 30s scan interval
    orphan_cleanup_hours: 24         # 24 hours = orphaned

    # At-least-once delivery
    compensation_retry_max: 3
    compensation_retry_delay_ms: 1000
```

---

## Conclusion

Distributed State Management provides:
1. **Durable saga log** (K0 WAL persistence, 7-day retention)
2. **Crash recovery** (detect crashes, resume compensation)
3. **Heartbeat mechanism** (10s interval, 60s timeout)
4. **Orphan cleanup** (abort sagas older than 24 hours)

**Next step:** Proceed to **0008d (Timeout & Deadlock Handling)**.
