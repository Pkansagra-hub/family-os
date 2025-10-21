# MPST Protocol Contracts

**Source ADRs:** ADR-0003, ADR-0003a-d

## Overview

This directory contains Multiparty Session Type (MPST) protocol contracts for K1's 6 core protocols. These contracts define the communication choreography between K1 agents using Scribble-like protocol definitions.

## Research Foundation

- **MPST (Honda et al. 2008):** Multiparty session types for protocol validation
- **Scribble (Yoshida et al. 2013):** Protocol description language
- **Session Types:** Compile-time verification of communication safety

## Contracts Included

### 1. Agent Hire Protocol (`agent_hire.yaml`)
- **Source:** ADR-0003b (Protocol 1)
- Orchestrator hires agent for task
- State machine: IDLE → WARM_UP → ACTIVE
- Timeout: 200ms for warm-up

### 2. Task Execution Protocol (`task_execution.yaml`)
- **Source:** ADR-0003b (Protocol 2)
- Agent executes assigned task
- State machine: ASSIGNED → EXECUTING → COMPLETED/FAILED
- Timeout: 5000ms for execution

### 3. Clarification Protocol (`clarification.yaml`)
- **Source:** ADR-0003b (Protocol 3)
- Agent requests clarification from user via orchestrator
- State machine: NEED_CLARIFICATION → WAITING_USER → CLARIFIED
- Timeout: 30000ms for user response

### 4. Barge-In Protocol (`barge_in.yaml`)
- **Source:** ADR-0003b (Protocol 4)
- User interrupts ongoing turn
- State machine: EXECUTING → INTERRUPTED → CANCELLED
- Timeout: 120ms for cancellation

### 5. Tool Call Protocol (`tool_call.yaml`)
- **Source:** ADR-0003b (Protocol 5)
- Agent invokes external tool
- State machine: TOOL_REQUESTED → TOOL_EXECUTING → TOOL_COMPLETED/FAILED
- Timeout: 3000ms for tool execution

### 6. Saga Rollback Protocol (`saga_rollback.yaml`)
- **Source:** ADR-0003b (Protocol 6)
- Compensating transactions for multi-step failures
- State machine: EXECUTING → FAILED → ROLLING_BACK → ROLLED_BACK
- Timeout: Variable based on saga depth

## Protocol Definition Language (PDL)

**Source:** ADR-0003a

All protocols are defined using a Scribble-like PDL with the following syntax:

```scribble
protocol AgentHire(role Orchestrator, role Agent) {
  // Hire request
  HireRequest(agent_id, capabilities) from Orchestrator to Agent;

  choice at Agent {
    // Accept and warm up
    HireAccepted(agent_id) from Agent to Orchestrator;
    WarmUpComplete(agent_id) from Agent to Orchestrator;
  } or {
    // Reject hire
    HireRejected(agent_id, reason) from Agent to Orchestrator;
  }
}
```

## Key Specifications

### Protocol Monitor Runtime
- **Source:** ADR-0003c
- Validates protocol adherence at runtime
- Enforces timeout constraints
- Detects protocol violations

### Role Attestation
- **Source:** ADR-0003d
- Capability-based role verification
- Ensures agents have required capabilities
- Prevents unauthorized protocol participation

### Timeout Enforcement

```yaml
timeouts:
  agent_hire:
    warm_up: 200ms
    total: 500ms

  task_execution:
    execution: 5000ms
    total: 6000ms

  clarification:
    user_response: 30000ms
    total: 35000ms

  barge_in:
    cancellation: 120ms
    total: 200ms

  tool_call:
    execution: 3000ms
    total: 3500ms

  saga_rollback:
    per_compensation: 1000ms
    max_total: 10000ms
```

## Protocol State Machines

Each protocol defines valid state transitions:

```yaml
protocol_fsm:
  agent_hire:
    states: [IDLE, HIRING, WARMING, ACTIVE, REJECTED]
    initial: IDLE
    final: [ACTIVE, REJECTED]
    transitions:
      - from: IDLE, to: HIRING, event: hire_request
      - from: HIRING, to: WARMING, event: hire_accepted
      - from: WARMING, to: ACTIVE, event: warmup_complete
      - from: HIRING, to: REJECTED, event: hire_rejected
```

## Violation Handling

```yaml
violation_handling:
  detection:
    - Invalid state transition
    - Timeout exceeded
    - Unexpected message
    - Role capability mismatch

  response:
    severity: CRITICAL
    action: terminate_protocol
    compensation: trigger_saga_rollback
    alert: protocol_violation{protocol, violation_type}
```

## Performance Requirements

```yaml
performance:
  protocol_validation_latency_p95_ms: 1
  protocol_overhead_per_message_ms: 0.5
  max_concurrent_protocols_per_agent: 10
  protocol_state_memory_bytes: 256
```

## Usage Examples

### Agent Hire Protocol

```python
# Orchestrator initiates hire
protocol = ProtocolMonitor.start_protocol(
    protocol_type="agent_hire",
    roles={"orchestrator": orch_id, "agent": agent_id}
)

# Send hire request
await protocol.send(
    from_role="orchestrator",
    to_role="agent",
    message_type="HireRequest",
    payload={"agent_id": agent_id, "capabilities": caps}
)

# Agent accepts and warms up
await protocol.send(
    from_role="agent",
    to_role="orchestrator",
    message_type="HireAccepted",
    payload={"agent_id": agent_id}
)

# Validate protocol completion
if protocol.is_complete():
    print("Agent hire protocol completed successfully")
```

## Testing Strategies

```yaml
protocol_tests:
  positive_tests:
    - Happy path: all messages in correct order
    - All protocol variants (choice branches)

  negative_tests:
    - Timeout violations
    - Invalid state transitions
    - Unauthorized role participation
    - Malformed messages

  property_tests:
    - Safety: no invalid states reachable
    - Liveness: protocols eventually complete
    - Progress: no deadlocks
```

## Monitoring & Observability

```yaml
metrics:
  - protocol_started_total{protocol}
  - protocol_completed_total{protocol, outcome}
  - protocol_violations_total{protocol, violation_type}
  - protocol_duration_ms{protocol, percentile}
  - protocol_timeout_total{protocol}

alerts:
  - ProtocolViolation: violation_rate > 0.1% for 5 min
  - ProtocolTimeout: timeout_rate > 1% for 5 min
  - ProtocolStuck: duration > 2x expected for 5 min
```

## Related Contracts

- Actor Model: `../actor_model/`
- Agent Lifecycle: `../agent_lifecycle/`
- Orchestration: `../orchestration/`
- Error Recovery: `../error_recovery/`

---

**Last Updated:** 2025-10-13
