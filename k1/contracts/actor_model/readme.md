# Actor Model Contracts

**Source ADRs:** ADR-0002, ADR-0002a-d

## Overview

This directory contains contracts for K1's Actor Model implementation, which provides isolated, message-passing concurrency for all 58 agents (4 AI agents + 54 pure actors).

## Research Foundation

- **Actor Model (Hewitt 1973):** Isolated entities communicating via asynchronous messages
- **Akka Patterns (Lightbend):** Battle-tested actor patterns
- **Orleans (Microsoft):** Virtual actor implementation patterns

## Contracts Included

### 1. Mailbox MPSC Queue Contract (`mailbox_mpsc.yaml`)
- **Source:** ADR-0002a
- Multi-producer single-consumer queue implementation
- Bounded queue size (1000 messages default)
- Backpressure handling when full

### 2. Supervisor Monitoring Contract (`supervisor_monitoring.yaml`)
- **Source:** ADR-0002b
- Supervisor-child relationship
- Crash detection and recovery strategies
- Restart policies (one-for-one, all-for-one)

### 3. Actor Router Contract (`actor_router.yaml`)
- **Source:** ADR-0002c
- Message routing strategies
- Admission control (max 3 agents/session)
- Load balancing across actor instances

### 4. Observability Schema Contract (`observability_schema.yaml`)
- **Source:** ADR-0002d
- Actor lifecycle events
- Message flow tracing
- Performance metrics

## Key Specifications

### Actor Isolation

```yaml
actor_isolation:
  principle: |
    Actors have NO shared mutable state.
    All communication via asynchronous messages.

  guarantees:
    - No direct memory access between actors
    - Messages are immutable or deep-copied
    - Actor state is private and encapsulated
    - No global variables or singletons

  violations:
    - Sharing mutable references
    - Accessing another actor's state directly
    - Using shared global state
```

### Message Passing

```yaml
message_passing:
  semantics: at_most_once
  ordering: FIFO per sender-receiver pair
  delivery: asynchronous

  message_structure:
    - sender_id: ActorID
    - receiver_id: ActorID
    - message_type: string
    - payload: immutable_object
    - trace_id: string
    - timestamp: iso8601

  constraints:
    max_message_size_kb: 64
    max_mailbox_size: 1000
    message_timeout_ms: 5000
```

### Mailbox (MPSC Queue)

**Source:** ADR-0002a

```yaml
mailbox:
  implementation: bounded_mpsc_queue
  capacity: 1000

  overflow_policy:
    strategy: drop_oldest
    alert: mailbox_overflow{actor_id}

  backpressure:
    trigger: queue_size > 800
    response: signal_sender_to_slow_down
    propagation: cascade_to_upstream_actors

  performance:
    enqueue_latency_p95_ms: 1
    dequeue_latency_p95_ms: 1
    throughput_msgs_per_sec: 100000
```

### Supervisor Hierarchy

**Source:** ADR-0002b

```yaml
supervisor:
  responsibility:
    - Monitor child actor health
    - Detect crashes and failures
    - Apply restart strategies
    - Maintain actor lifecycle

  restart_strategies:
    one_for_one:
      description: Restart only failed child
      use_case: Independent actors
      max_restarts: 3
      time_window_ms: 60000

    all_for_one:
      description: Restart all children on failure
      use_case: Dependent actors (e.g., orchestrator + agents)
      max_restarts: 3
      time_window_ms: 60000

  escalation:
    - If max_restarts exceeded: escalate to parent supervisor
    - If parent also fails: trigger system-level recovery
    - If system-level fails: alert operations team
```

### Actor Router & Admission Control

**Source:** ADR-0002c

```yaml
actor_router:
  routing_strategies:
    round_robin:
      description: Distribute messages evenly
      use_case: Stateless actors

    consistent_hash:
      description: Route by session_id hash
      use_case: Stateful actors (e.g., session-bound)

    broadcast:
      description: Send to all instances
      use_case: Configuration updates

  admission_control:
    max_agents_per_session: 3
    max_concurrent_sessions_per_k1_instance: 100

    rejection_policy:
      - If limit exceeded: return AgentHireRejected
      - If system overloaded: apply backpressure
      - If blacklisted: permanent rejection
```

## Actor Lifecycle

```yaml
actor_lifecycle:
  states:
    - UNINITIALIZED: Actor created but not started
    - STARTING: Actor initializing resources
    - RUNNING: Actor processing messages
    - STOPPING: Actor draining mailbox and cleaning up
    - STOPPED: Actor terminated
    - FAILED: Actor crashed

  transitions:
    - UNINITIALIZED → STARTING: on_start()
    - STARTING → RUNNING: on_ready()
    - RUNNING → STOPPING: on_stop()
    - STOPPING → STOPPED: on_cleanup_complete()
    - RUNNING → FAILED: on_crash()
    - FAILED → STARTING: on_restart()

  hooks:
    - on_start(): Initialize actor resources
    - on_ready(): Signal actor is ready to receive messages
    - on_receive(message): Process incoming message
    - on_stop(): Begin graceful shutdown
    - on_cleanup_complete(): Release resources
    - on_crash(error): Handle crash
    - on_restart(): Restart after failure
```

## Error Handling & Fault Tolerance

```yaml
fault_tolerance:
  crash_detection:
    - Unhandled exceptions in on_receive()
    - Heartbeat timeout (no message processed in 60s)
    - Resource exhaustion (OOM, file handles)

  recovery_strategies:
    restart:
      description: Restart actor with fresh state
      use_case: Transient failures

    resume:
      description: Continue with current state
      use_case: Recoverable errors

    stop:
      description: Stop actor permanently
      use_case: Unrecoverable errors

    escalate:
      description: Propagate failure to supervisor
      use_case: Systematic failures

  blacklist_policy:
    trigger: 3 crashes within 10 minutes
    duration: 1 hour
    action: Reject all hire requests
```

## Performance Requirements

```yaml
performance:
  message_latency_p95_ms: 5
  actor_startup_time_ms: 50
  actor_shutdown_time_ms: 100
  max_actors_per_k1_instance: 200
  memory_per_actor_kb: 500
```

## Observability

**Source:** ADR-0002d

```yaml
observability:
  events:
    - actor_created{actor_id, actor_type}
    - actor_started{actor_id}
    - actor_stopped{actor_id, reason}
    - actor_crashed{actor_id, error}
    - actor_restarted{actor_id, restart_count}
    - message_sent{from, to, message_type}
    - message_received{actor_id, message_type}
    - message_processed{actor_id, duration_ms}
    - mailbox_overflow{actor_id, dropped_count}

  metrics:
    - actor_count{state}
    - mailbox_size{actor_id}
    - message_processing_duration_ms{actor_id, percentile}
    - actor_restart_total{actor_id}
    - message_throughput{actor_id}

  tracing:
    - All messages include cognitive_trace_id
    - Span per message: actor.receive_message
    - Parent-child span linking
```

## Testing Strategies

```yaml
actor_tests:
  unit_tests:
    - Message processing logic
    - State transitions
    - Error handling

  integration_tests:
    - Multi-actor scenarios
    - Supervisor-child interactions
    - Message routing

  chaos_tests:
    - Random actor crashes
    - Network delays
    - Mailbox overflow
    - Resource exhaustion
```

## Usage Examples

### Creating an Actor

```python
class PlannerActor(Actor):
    def __init__(self, actor_id: str):
        super().__init__(actor_id)
        self.state = PlannerState()

    async def on_receive(self, message: Message):
        if message.type == "GeneratePlan":
            plan = await self.generate_plan(message.payload)
            await self.send(message.sender_id, "PlanGenerated", plan)
        elif message.type == "ValidatePlan":
            result = await self.validate_plan(message.payload)
            await self.send(message.sender_id, "PlanValidated", result)
```

### Supervisor with Restart Strategy

```python
supervisor = Supervisor(
    actor_id="orchestrator_supervisor",
    restart_strategy=RestartStrategy.ONE_FOR_ONE,
    max_restarts=3,
    time_window_ms=60000
)

# Add child actors
await supervisor.add_child(orchestrator_actor)
await supervisor.add_child(planner_actor)

# Supervisor monitors children automatically
```

## Related Contracts

- Agent Lifecycle: `../agent_lifecycle/`
- Protocols: `../protocols/`
- Orchestration: `../orchestration/`
- Error Recovery: `../error_recovery/`

---

**Last Updated:** 2025-10-13
