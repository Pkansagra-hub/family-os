# Orchestrator Cross-Component Contracts

> **Audience**: Concierge team building `FabricOrchestratorAdapter`.
>
> **Purpose**: Defines the exact Orchestrator public surface that the
> Concierge-side adapter programs against. This is NOT a port or runtime
> artifact -- it is a reference document that unblocks parallel Concierge
> development.
>
> **Source types**: `k1.orchestrator.types` (Epic 1.2).
>
> **Source ports**: `k1.orchestrator.ports.mailbox_port.IMailboxPort` (Epic 1.4).

---

## 1. submit_task(TaskEnvelope) -> TaskAck

The Concierge adapter submits tasks by constructing a `TaskEnvelope` and
calling `IMailboxPort.enqueue()`. The Orchestrator returns a `TaskAck`
synchronously.

### Entry Point

```
IMailboxPort.enqueue(message: TaskEnvelope, priority: str = "INTERACTIVE") -> int
```

The adapter wraps this call behind a **circuit breaker** named
`CB_ORCHESTRATOR` (Concierge-side) to handle Orchestrator unavailability
gracefully.

### TaskAck Response

| Field                 | Type            | Description                                  |
|-----------------------|-----------------|----------------------------------------------|
| `envelope_id`         | `str`           | Echoed from `TaskEnvelope.envelope_id`       |
| `status`              | `str`           | `ACCEPTED`, `DUPLICATE`, or `REJECTED_FULL`  |
| `estimated_duration_ms` | `Optional[int]` | Rough ETA (may be `None`)                   |

### Circuit Breaker Contract

- **Name**: `CB_ORCHESTRATOR`
- **Owned by**: Concierge (not Orchestrator)
- **Failure condition**: `IMailboxPort.enqueue()` raises or returns
  `REJECTED_FULL`
- **Threshold**: 3 consecutive failures within 60s window
- **Half-open**: After 30s, allow 1 probe call
- **Fallback**: Concierge degrades to canned response (see Section 4)

---

## 2. Event Subscription: dag.completed.v1

After DAG execution finishes, Orchestrator emits an event with the full
`AggregatedResult` payload. The Concierge adapter subscribes to this event
to deliver the final answer to the user.

### Event Details

| Property   | Value                                      |
|------------|--------------------------------------------|
| **Topic**  | `k1.orchestration.dag.completed.v1`        |
| **Schema** | `k1/contracts/schemas/events/orchestration/dag.completed.v1.json` |
| **Payload**| `AggregatedResult` (serialized via `to_dict()`) |

### AggregatedResult Fields (Concierge-relevant subset)

| Field          | Type               | Description                                    |
|----------------|--------------------|------------------------------------------------|
| `result_id`    | `str`              | Unique result identifier                       |
| `total_steps`  | `int`              | Total steps in the DAG                         |
| `completed`    | `int`              | Steps that finished successfully               |
| `failed`       | `int`              | Steps that exhausted retries                   |
| `cancelled`    | `int`              | Steps cancelled (interrupt or cascade)         |
| `skipped`      | `int`              | Steps skipped (unmet dependencies)             |
| `step_results` | `List[StepResult]` | Ordered step results with outputs              |
| `success`      | `bool`             | `True` iff `failed == 0 and cancelled == 0`    |
| `duration_ms`  | `int`              | Wall-clock execution time                      |
| `trace_id`     | `str`              | Cognitive trace identifier                     |
| `plan_id`      | `Optional[str]`    | `None` for MEDIUM tier (no plan)               |
| `compensations`| `List[CompensationRecord]` | Saga rollback actions performed        |

### Concierge Handling

1. Match `trace_id` to the originating user session.
2. If `success` is `True`: format `step_results` into user response.
3. If `success` is `False`: apply tier degradation (Section 4).

---

## 3. Event Subscription: hil.progress.v1

While a DAG is executing, the Orchestrator emits progress deltas and
human-in-the-loop requests via the delta bus. The Concierge adapter
subscribes to surface these to the user.

### Progress Events

| Property   | Value                                    |
|------------|------------------------------------------|
| **Topic**  | `k1.orchestration.delta.v1`              |
| **Schema** | `k1/contracts/schemas/events/orchestration/delta.v1.json` |
| **Payload**| Progress update with step summary        |

**Usage**: Concierge displays partial progress (e.g., "Step 2 of 5
complete: calendar search done").

### HIL Override Request

| Property   | Value                                          |
|------------|------------------------------------------------|
| **Topic**  | `k1.hil.override_response.v1` (Concierge sends) |
| **Schema** | `k1/contracts/schemas/events/hil/override_response.v1.json` |

| Property   | Value                                           |
|------------|--------------------------------------------------|
| **Topic**  | `k1.hil.fallback_response.v1` (Concierge sends) |
| **Schema** | `k1/contracts/schemas/events/hil/fallback_response.v1.json` |

**Flow**:
1. Orchestrator emits `HILRequest` via `IDeltaEmitPort.emit_hil_request()`.
2. Concierge surfaces `question` and `options` to the user.
3. User responds; Concierge publishes either `hil.override_response.v1`
   or `hil.fallback_response.v1`.
4. Orchestrator's `on_hil_override` / `on_hil_fallback` handler resumes
   the paused step.
5. If `pending_hil_ttl_s` (120s) expires with no response, the Reaper
   evicts the pending HIL context and the step fails with `HIL_TIMEOUT`.

---

## 4. Tier Degradation Callbacks

When Orchestrator cannot fulfill a task at the requested tier, the
Concierge adapter is responsible for attempting the next lower tier.
Orchestrator signals degradation via `dag.completed.v1` with
`success: false` and specific error codes.

### Degradation Ladder

```
HIGH  ->  MEDIUM  ->  LOW  ->  Canned Response
```

| From   | To     | Trigger                                      | Concierge Action                              |
|--------|--------|----------------------------------------------|-----------------------------------------------|
| HIGH   | MEDIUM | Planner timeout or plan.failed event         | Re-submit with `tier: "MEDIUM"`, pre-resolved capabilities |
| MEDIUM | LOW    | All capabilities fail after retries          | Route to LOW-tier handler (direct LLM call, no Orchestrator) |
| LOW    | Canned | LLM call fails or CB_ORCHESTRATOR open       | Return static canned response from locale store |

### Rules

- Degradation is **Concierge-owned** logic. Orchestrator does NOT
  auto-degrade.
- Each degradation step is a **new TaskEnvelope** (new `envelope_id`,
  same `trace_id`).
- The `trace_id` MUST be preserved across all degradation attempts for
  end-to-end tracing.
- LOW tier tasks never reach the Orchestrator (Concierge handles
  directly via a single LLM call).
- CRISIS tier is system-initiated and uses canned responses only.

---

## 5. TaskEnvelope Construction Spec (Per Tier)

The Concierge adapter MUST construct `TaskEnvelope` correctly per tier.
The Orchestrator validates invariants in `__post_init__` and will raise
`ValueError` on invalid construction.

### MEDIUM Tier

```python
TaskEnvelope(
    intent="search my calendar for tomorrow",
    trace_id="<cognitive_trace_id>",        # required, non-empty
    caller_id="concierge-session-abc",      # recommended
    tier="MEDIUM",
    capabilities=["tool.calendar.search"],  # REQUIRED, 1-2 items (ORCH-10)
    params={
        "tool.calendar.search": {
            "query": "tomorrow"
        }
    },
    timeout_ms=10000,                       # medium_tier_total_ms budget
)
```

**Invariants enforced by TaskEnvelope.__post_init__**:
- `tier` must be `"MEDIUM"` or `"HIGH"`
- `capabilities` must be non-empty for MEDIUM
- `len(capabilities) <= 2` for MEDIUM (ORCH-10)
- `intent` must be non-empty
- `trace_id` must be non-empty

### HIGH Tier

```python
TaskEnvelope(
    intent="plan my family vacation for next week",
    trace_id="<cognitive_trace_id>",        # required, non-empty
    caller_id="concierge-session-abc",      # recommended
    tier="HIGH",
    capabilities=[],                        # MAY be empty (Planner decides)
    params={},                              # MAY be empty
    context={
        "user_preferences": {...},          # optional enrichment
    },
    timeout_ms=45000,                       # high_tier_total_ms budget
)
```

**HIGH-tier specific behavior**:
- Orchestrator forwards to Planner via `IPlannerPort.request_plan()`.
- Planner returns `CommittedPlan` asynchronously via `plan.ready.v1` event.
- Orchestrator builds DAG from plan and executes.
- If Planner fails (`plan.failed.v1`), Concierge receives
  `dag.completed.v1` with `success: false` and should attempt MEDIUM
  degradation.

### Fields Reference

| Field          | Type                          | MEDIUM Required | HIGH Required | Default      |
|----------------|-------------------------------|-----------------|---------------|--------------|
| `intent`       | `str`                         | Yes             | Yes           | --           |
| `trace_id`     | `str`                         | Yes             | Yes           | --           |
| `caller_id`    | `str`                         | Recommended     | Recommended   | `""`         |
| `envelope_id`  | `str`                         | Auto-generated  | Auto-generated| `uuid4()`    |
| `context`      | `Dict[str, Any]`              | Optional        | Optional      | `{}`         |
| `tier`         | `str`                         | `"MEDIUM"`      | `"HIGH"`      | `"MEDIUM"`   |
| `capabilities` | `List[str]`                   | 1-2 items       | 0+ items      | `[]`         |
| `params`       | `Dict[str, Dict[str, Any]]`   | Per-capability  | Optional      | `{}`         |
| `constraints`  | `Dict[str, Any]`              | Optional        | Optional      | `{}`         |
| `timeout_ms`   | `int`                         | 10000           | 45000         | `30000`      |

---

## Appendix: Event Topic Quick Reference

| Direction | Topic                                      | Payload Type       |
|-----------|--------------------------------------------|--------------------|
| Subscribe | `k1.orchestration.dag.completed.v1`        | `AggregatedResult` |
| Subscribe | `k1.orchestration.delta.v1`                | Progress delta     |
| Publish   | `k1.hil.override_response.v1`              | HIL user response  |
| Publish   | `k1.hil.fallback_response.v1`              | HIL fallback       |
| Observe   | `k1.orchestration.step.started.v1`         | Step lifecycle     |
| Observe   | `k1.orchestration.step.completed.v1`       | Step lifecycle     |
| Observe   | `k1.orchestration.step.failed.v1`          | Step lifecycle     |
