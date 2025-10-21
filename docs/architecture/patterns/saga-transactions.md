# Saga Pattern - K1 Implementation Guide

## Overview

The Saga Pattern (Garcia-Molina & Salem 1987) enables distributed transactions in K1 with compensating actions for rollback. K1 uses sagas for multi-agent coordination and K0 bridge operations.

## Core Principles

1. **Local transactions**: Each step is a local transaction
2. **Compensating actions**: Every forward action has a compensation
3. **Eventual consistency**: No distributed locks, eventual consistency only
4. **Durability**: K0 bridge ensures persistence across rollbacks

## Saga Structure

```python
from dataclasses import dataclass
from enum import Enum

class SagaState(Enum):
    TRANSACTION_START = "TRANSACTION_START"
    STEPS_EXECUTING = "STEPS_EXECUTING"
    FAILURE_DETECTED = "FAILURE_DETECTED"
    COMPENSATING = "COMPENSATING"
    ROLLED_BACK = "ROLLED_BACK"
    COMMITTED = "COMMITTED"

@dataclass
class SagaStep:
    """Individual saga step with forward + compensation"""
    step_id: str
    forward_action: callable
    compensating_action: callable
    timeout_ms: int
    executed: bool = False
    compensated: bool = False

@dataclass
class Saga:
    """Saga transaction with compensation"""
    saga_id: str
    steps: list[SagaStep]
    state: SagaState
    current_step: int = 0
    trace_id: str = ""
```

## K1 Saga Implementation

### Saga Coordinator

```python
class SagaCoordinator:
    """Coordinates saga execution with rollback"""

    def __init__(self, k0_bridge):
        self.k0_bridge = k0_bridge
        self.active_sagas: dict[str, Saga] = {}

    async def execute_saga(self, saga: Saga) -> bool:
        """Execute saga with automatic compensation on failure"""
        saga.state = SagaState.TRANSACTION_START

        try:
            # Execute forward steps
            saga.state = SagaState.STEPS_EXECUTING
            await self._execute_forward(saga)

            # Commit if all steps succeeded
            saga.state = SagaState.COMMITTED
            await self._persist_saga(saga)
            return True

        except Exception as e:
            # Rollback on any failure
            logger.error(
                "saga_failure_detected",
                saga_id=saga.saga_id,
                step=saga.current_step,
                error=str(e),
                trace_id=saga.trace_id
            )

            saga.state = SagaState.FAILURE_DETECTED
            await self._compensate(saga)

            saga.state = SagaState.ROLLED_BACK
            await self._persist_saga(saga)
            return False

    async def _execute_forward(self, saga: Saga):
        """Execute all forward steps"""
        for i, step in enumerate(saga.steps):
            saga.current_step = i

            try:
                result = await asyncio.wait_for(
                    step.forward_action(),
                    timeout=step.timeout_ms / 1000
                )
                step.executed = True

                # Persist after each step
                await self._persist_saga(saga)

            except asyncio.TimeoutError:
                raise TimeoutError(f"Step {step.step_id} timeout after {step.timeout_ms}ms")

    async def _compensate(self, saga: Saga):
        """Compensate executed steps in reverse order"""
        saga.state = SagaState.COMPENSATING

        # Compensate in reverse order
        for step in reversed(saga.steps[:saga.current_step + 1]):
            if step.executed and not step.compensated:
                try:
                    await step.compensating_action()
                    step.compensated = True

                    logger.info(
                        "saga_step_compensated",
                        saga_id=saga.saga_id,
                        step_id=step.step_id,
                        trace_id=saga.trace_id
                    )

                except Exception as e:
                    logger.error(
                        "compensation_failed",
                        saga_id=saga.saga_id,
                        step_id=step.step_id,
                        error=str(e),
                        trace_id=saga.trace_id
                    )
                    # Continue compensating other steps

    async def _persist_saga(self, saga: Saga):
        """Persist saga state to K0 for durability"""
        await self.k0_bridge.write(
            key=f"saga:{saga.saga_id}",
            value=serialize_saga(saga),
            trace_id=saga.trace_id
        )
```

## Example: Multi-Agent Task Saga

```python
async def create_multi_agent_task_saga(
    orchestrator,
    task: TaskAnnouncement,
    agents: list[Agent]
) -> Saga:
    """Create saga for multi-agent task execution"""

    steps = []

    # Step 1: Reserve agents
    steps.append(SagaStep(
        step_id="reserve_agents",
        forward_action=lambda: orchestrator.reserve_agents(agents),
        compensating_action=lambda: orchestrator.release_agents(agents),
        timeout_ms=250
    ))

    # Step 2: Allocate resources
    steps.append(SagaStep(
        step_id="allocate_resources",
        forward_action=lambda: orchestrator.allocate_resources(agents, task),
        compensating_action=lambda: orchestrator.deallocate_resources(agents),
        timeout_ms=100
    ))

    # Step 3: Execute task
    steps.append(SagaStep(
        step_id="execute_task",
        forward_action=lambda: orchestrator.execute_task(agents, task),
        compensating_action=lambda: orchestrator.abort_task(task),
        timeout_ms=1600
    ))

    # Step 4: Collect results
    steps.append(SagaStep(
        step_id="collect_results",
        forward_action=lambda: orchestrator.collect_results(task),
        compensating_action=lambda: orchestrator.discard_results(task),
        timeout_ms=50
    ))

    return Saga(
        saga_id=f"saga-{task.task_id}",
        steps=steps,
        state=SagaState.TRANSACTION_START,
        trace_id=task.trace_id
    )
```

## K0 Bridge Integration

```python
class K0Bridge:
    """Durable storage for saga persistence"""

    async def write(self, key: str, value: bytes, trace_id: str):
        """Write to K0 with durability guarantee"""
        # Write to K0 with fsync for durability
        await self._write_with_fsync(key, value)

        logger.info(
            "k0_write",
            key=key,
            size_bytes=len(value),
            trace_id=trace_id
        )

    async def read(self, key: str, trace_id: str) -> bytes:
        """Read from K0"""
        value = await self._read_from_k0(key)

        logger.info(
            "k0_read",
            key=key,
            size_bytes=len(value),
            trace_id=trace_id
        )

        return value
```

## Saga Recovery

```python
class SagaRecovery:
    """Recover sagas after crash"""

    async def recover_all(self, coordinator: SagaCoordinator):
        """Recover all in-progress sagas from K0"""
        saga_keys = await self._list_sagas()

        for key in saga_keys:
            saga_data = await self.k0_bridge.read(key, trace_id="recovery")
            saga = deserialize_saga(saga_data)

            if saga.state == SagaState.STEPS_EXECUTING:
                # Resume forward execution
                await coordinator.execute_saga(saga)

            elif saga.state == SagaState.FAILURE_DETECTED:
                # Resume compensation
                await coordinator._compensate(saga)
                saga.state = SagaState.ROLLED_BACK
                await coordinator._persist_saga(saga)
```

## Performance Considerations

- **Saga timeout**: 5000ms (P95) for typical multi-step saga
- **Compensation timeout**: 1000ms per compensating action
- **K0 write latency**: <10ms for persistence
- **Memory per saga**: <1KB (state only, not intermediate results)

## Testing with WARD

```python
from ward import test, fixture

@fixture
async def saga_coordinator():
    """Saga coordinator with K0 bridge"""
    k0 = K0Bridge()
    coordinator = SagaCoordinator(k0_bridge=k0)
    yield coordinator
    await coordinator.shutdown()

@test("saga commits when all steps succeed")
async def _(coordinator=saga_coordinator):
    """Test successful saga execution"""
    executed_steps = []

    saga = Saga(
        saga_id="test-saga-1",
        steps=[
            SagaStep(
                step_id="step1",
                forward_action=lambda: executed_steps.append("step1"),
                compensating_action=lambda: None,
                timeout_ms=1000
            ),
            SagaStep(
                step_id="step2",
                forward_action=lambda: executed_steps.append("step2"),
                compensating_action=lambda: None,
                timeout_ms=1000
            )
        ],
        state=SagaState.TRANSACTION_START,
        trace_id="trace-123"
    )

    success = await coordinator.execute_saga(saga)

    assert success is True
    assert saga.state == SagaState.COMMITTED
    assert executed_steps == ["step1", "step2"]

@test("saga compensates on failure")
async def _(coordinator=saga_coordinator):
    """Test saga compensation on failure"""
    executed = []
    compensated = []

    saga = Saga(
        saga_id="test-saga-2",
        steps=[
            SagaStep(
                step_id="step1",
                forward_action=lambda: executed.append("step1"),
                compensating_action=lambda: compensated.append("step1"),
                timeout_ms=1000
            ),
            SagaStep(
                step_id="step2",
                forward_action=lambda: 1/0,  # Intentional failure
                compensating_action=lambda: compensated.append("step2"),
                timeout_ms=1000
            )
        ],
        state=SagaState.TRANSACTION_START,
        trace_id="trace-456"
    )

    success = await coordinator.execute_saga(saga)

    assert success is False
    assert saga.state == SagaState.ROLLED_BACK
    assert executed == ["step1"]
    assert compensated == ["step1"]  # step2 never executed, no compensation needed
```

## Common Pitfalls

❌ **Don't**: Use distributed locks
```python
# BAD - distributed locks defeat saga purpose
async with distributed_lock("resource"):
    await execute_step()
```

✅ **Do**: Use compensating actions
```python
# GOOD - compensating actions for rollback
async def forward_action():
    await reserve_resource()

async def compensating_action():
    await release_resource()
```

❌ **Don't**: Forget to persist saga state
```python
# BAD - no persistence, can't recover
await execute_step()
saga.current_step += 1  # Lost on crash!
```

✅ **Do**: Persist after each step
```python
# GOOD - persist for crash recovery
await execute_step()
saga.current_step += 1
await k0_bridge.write(saga)  # Durable!
```

## References

- **Research**: Garcia-Molina, H., Salem, K. (1987). "Sagas"
- **K1 Diagram**: `architecture_diagrams/k1_protocol_monitor_fsms.mmd` (Saga Rollback Protocol)
- **Module**: `k1/orchestrator/saga/` (Layer 1 - Core Kernel), `k1/k0_bridge/` (Layer 2 - State & Persistence)
- **Specifications**: `docs/whiteboard.md` (lines 500-700)
- **Related ADRs**: (to be created)

## See Also

- **MPST Protocols**: Saga Rollback Protocol FSM
- **K0 Bridge**: Durable storage for saga persistence
- **Orchestrator**: Multi-agent coordination with sagas
