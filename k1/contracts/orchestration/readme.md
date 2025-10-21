# Orchestration Contracts

**Source ADRs:** ADR-0005, ADR-0005a-d

## Overview

This directory contains contracts for K1's Orchestrator Core, which implements the 3-phase coordination protocol (Negotiation → Selection → Execution) based on the Contract Net Protocol.

## Research Foundation

- **Contract Net Protocol (Smith 1980):** Multi-agent task allocation through negotiation
- **Consensus Algorithms:** Leader election and agreement protocols
- **Multi-Agent Systems:** Coordination patterns for distributed agents

## Contracts Included

### 1. Three-Phase Protocol Contract (`three_phase_protocol.yaml`)
- **Source:** ADR-0005a
- Phase 1: Negotiation (task announcement, bidding)
- Phase 2: Selection (bid evaluation, agent selection)
- Phase 3: Execution (task assignment, monitoring)

### 2. Task Announcement Contract (`task_announcement.yaml`)
- **Source:** ADR-0005b
- Task announcement format
- Required capabilities specification
- Task priority and deadline

### 3. Bid Evaluation Contract (`bid_evaluation.yaml`)
- **Source:** ADR-0005c
- Bid scoring algorithm
- Selection criteria (capability match, availability, past performance)
- Tie-breaking rules

### 4. Execution Monitoring Contract (`execution_monitoring.yaml`)
- **Source:** ADR-0005d
- Task execution tracking
- Progress reporting
- Timeout enforcement and failure handling

## Three-Phase Orchestration Protocol

```yaml
three_phase_protocol:
  overview: |
    Contract Net Protocol-based orchestration:
    1. Negotiation: Announce task, collect bids
    2. Selection: Evaluate bids, select best agent
    3. Execution: Assign task, monitor completion

  performance_target:
    total_latency_p95_ms: 250
    phase1_latency_ms: 100
    phase2_latency_ms: 50
    phase3_latency_ms: 100
```

### Phase 1: Negotiation

**Source:** ADR-0005a, ADR-0005b

```yaml
phase1_negotiation:
  step1_task_announcement:
    description: Orchestrator broadcasts task to eligible agents
    message_type: TaskAnnouncement
    payload:
      task_id: string
      task_type: string
      required_capabilities: [Capability]
      task_description: string
      priority: URGENT | HIGH | NORMAL | LOW
      deadline_ms: integer
      context: object

    routing:
      strategy: broadcast
      filter: agents_with_required_capabilities
      max_recipients: 10

    timeout_ms: 50

  step2_bid_collection:
    description: Agents submit bids if interested and capable
    message_type: BidSubmission
    payload:
      agent_id: string
      bid_score: float [0.0, 1.0]
      estimated_duration_ms: integer
      confidence: float [0.0, 1.0]
      reasons: [string]

    collection_window_ms: 50
    min_bids: 1
    max_bids: 10

    no_bids_handling:
      action: fallback_to_default_agent
      alert: no_bids_received{task_id}
```

### Phase 2: Selection

**Source:** ADR-0005a, ADR-0005c

```yaml
phase2_selection:
  step1_bid_evaluation:
    description: Evaluate all received bids
    algorithm: weighted_scoring

    scoring_factors:
      capability_match:
        weight: 0.4
        calculation: |
          required = task.required_capabilities
          provided = agent.capabilities
          score = len(required & provided) / len(required)

      availability:
        weight: 0.2
        calculation: |
          if agent.state == IDLE: score = 1.0
          elif agent.state == ACTIVE: score = 0.5
          else: score = 0.0

      past_performance:
        weight: 0.2
        calculation: |
          history = agent.task_history[-10:]
          success_rate = successes / total
          avg_duration = mean(durations)
          score = success_rate * (1.0 / avg_duration_normalized)

      confidence:
        weight: 0.2
        calculation: bid.confidence

    final_score: |
      score = (capability_match * 0.4 +
               availability * 0.2 +
               past_performance * 0.2 +
               confidence * 0.2)

  step2_agent_selection:
    description: Select highest-scoring agent
    strategy: highest_score

    tie_breaking:
      - If scores equal: prefer IDLE over ACTIVE
      - If still tied: prefer lower estimated_duration
      - If still tied: random selection

    latency_target_ms: 50

  step3_award_notification:
    description: Notify selected agent and rejected agents

    award_message:
      message_type: TaskAwarded
      recipient: selected_agent
      payload:
        task_id: string
        task: Task
        expected_start: timestamp

    rejection_message:
      message_type: BidRejected
      recipients: rejected_agents
      payload:
        task_id: string
        reason: string
```

### Phase 3: Execution

**Source:** ADR-0005a, ADR-0005d

```yaml
phase3_execution:
  step1_task_assignment:
    description: Assign task to selected agent
    protocol: AgentHire + TaskExecution

    agent_hire:
      - Send HireRequest
      - Wait for HireAccepted (or HireRejected)
      - Wait for WarmUpComplete (200ms)

    task_assignment:
      - Send TaskAssigned
      - Agent enters ACTIVE state
      - Agent begins execution

  step2_execution_monitoring:
    description: Monitor task execution progress

    progress_tracking:
      - Agent sends ProgressUpdate every 5 seconds
      - Orchestrator tracks elapsed time
      - Compare against estimated_duration

    timeout_enforcement:
      task_timeout: task.deadline_ms or 30000ms
      action_on_timeout:
        - Send TaskCancelled to agent
        - Trigger barge-in protocol
        - Mark task as FAILED
        - Alert: task_timeout{task_id, agent_id}

  step3_completion_handling:
    description: Handle task completion or failure

    success:
      message: TaskCompleted
      payload:
        task_id: string
        result: object
        duration_ms: integer
      action:
        - Update agent performance history
        - Transition agent to IDLE
        - Return result to requester

    failure:
      message: TaskFailed
      payload:
        task_id: string
        error: string
        duration_ms: integer
      action:
        - Update agent crash count
        - Check blacklist criteria
        - Transition agent to DRAINING or TERMINATED
        - Retry task with different agent (if retryable)
```

## Task Announcement Format

**Source:** ADR-0005b

```yaml
task_announcement:
  task_id: string            # Unique task ID
  task_type: string          # e.g., "planning", "tool_call", "clarification"
  required_capabilities: [Capability]
  task_description: string   # Human-readable description
  priority: enum             # URGENT, HIGH, NORMAL, LOW
  deadline_ms: integer       # Task deadline in milliseconds
  context: object            # Task-specific context
  trace_id: string           # cognitive_trace_id for tracing

  constraints:
    max_description_length: 1000
    max_context_size_kb: 16
    required_capabilities_max: 10
```

## Bid Evaluation & Selection

**Source:** ADR-0005c

```yaml
bid_evaluation:
  inputs:
    - bids: [BidSubmission]
    - task: TaskAnnouncement
    - agent_history: {agent_id: PerformanceHistory}

  outputs:
    - selected_agent_id: string
    - selection_reason: string
    - rejected_agents: [agent_id]

  constraints:
    evaluation_latency_p95_ms: 50
    min_score_threshold: 0.5

  fallback:
    - If all scores < threshold: use default agent
    - If default agent unavailable: queue task
    - If queue full: reject task with error
```

## Execution Monitoring

**Source:** ADR-0005d

```yaml
execution_monitoring:
  tracking:
    start_time: timestamp
    estimated_duration_ms: integer
    actual_duration_ms: integer
    progress_updates: [ProgressUpdate]

  progress_update_format:
    agent_id: string
    task_id: string
    progress_percent: integer [0, 100]
    status_message: string
    timestamp: iso8601

  timeout_strategy:
    soft_timeout: estimated_duration * 1.5
    hard_timeout: estimated_duration * 2.0 or task.deadline_ms

    soft_timeout_action:
      - Log warning
      - Metric: task_duration_exceeded_soft{task_id}

    hard_timeout_action:
      - Cancel task (barge-in protocol)
      - Mark as FAILED
      - Alert: task_timeout{task_id, agent_id}
```

## Performance Requirements

```yaml
performance:
  three_phase_total_latency_p95_ms: 250
  phase1_negotiation_latency_ms: 100
  phase2_selection_latency_ms: 50
  phase3_execution_latency_ms: 100

  throughput:
    tasks_per_second: 50
    concurrent_tasks_per_orchestrator: 100
```

## Observability

```yaml
observability:
  events:
    - task_announced{task_id, task_type, priority}
    - bid_received{task_id, agent_id, score}
    - agent_selected{task_id, agent_id, score}
    - task_assigned{task_id, agent_id}
    - task_completed{task_id, agent_id, duration_ms}
    - task_failed{task_id, agent_id, error}
    - task_timeout{task_id, agent_id}

  metrics:
    - orchestration_latency_ms{phase, percentile}
    - task_assignment_total{task_type}
    - task_completion_total{task_type, outcome}
    - bid_count{task_id}
    - selection_score{agent_id}
    - task_duration_ms{task_type, percentile}

  alerts:
    - OrchestrationSlow: p95 > 250ms for 5 min
    - NoBidsReceived: rate > 5% for 5 min
    - TaskTimeoutHigh: timeout_rate > 1% for 5 min
```

## Testing Strategies

```yaml
orchestration_tests:
  unit_tests:
    - Bid evaluation algorithm
    - Agent selection logic
    - Timeout enforcement

  integration_tests:
    - Full 3-phase protocol
    - Multiple concurrent tasks
    - Agent unavailability scenarios

  performance_tests:
    - Latency under load (50 tasks/sec)
    - Scalability (100 concurrent tasks)
    - Bid evaluation with 10 agents
```

## Usage Examples

### Orchestrator Flow

```python
# Phase 1: Negotiation
task = TaskAnnouncement(
    task_id="task-123",
    task_type="planning",
    required_capabilities=[Capability.PLANNING],
    priority=Priority.HIGH,
    deadline_ms=5000
)

bids = await orchestrator.announce_and_collect_bids(task, timeout_ms=100)

# Phase 2: Selection
selected_agent = await orchestrator.evaluate_and_select(bids, task)

# Phase 3: Execution
result = await orchestrator.assign_and_monitor(selected_agent, task)
```

## Related Contracts

- Agent Lifecycle: `../agent_lifecycle/`
- Protocols: `../protocols/`
- Actor Model: `../actor_model/`
- Planning: `../planning/`

---

**Last Updated:** 2025-10-13
