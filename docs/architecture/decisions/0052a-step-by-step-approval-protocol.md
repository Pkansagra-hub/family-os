# ADR-0052a: Step-by-Step Approval Protocol (Progressive Disclosure)

**Status:** ✅ **ACCEPTED** (2025-10-14)
**Date:** 2025-10-14
**Decision Date:** 2025-10-14
**Parent ADR:** [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
**Authors:** K1 Architecture Team
**Category:** Human-in-the-Loop & Safety
**Technical Story:** [Progressive Disclosure for Multi-Step Workflows]

**Related ADRs:**
- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md) - Parent umbrella ADR
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md) - Protocol 3 (Clarification) foundation
- [ADR-0007: 4-Stage Planning Pipeline](0007-4stage-planning-pipeline.md) - Planner integration
- [ADR-0008: Saga Pattern](0008-saga-pattern-error-recovery.md) - Rollback for failed steps
- [ADR-0007d: Planner K0 WAL Integration](0007d-planner-k0-wal-integration.md) - State checkpointing
- [ADR-0017b: SessionState Scoreboard](0017b-sessionstate-scoreboard-qud-belief.md) - Progress tracking

---

## Executive Summary

**Purpose:** Enable multi-step workflows where the user must approve each step before execution, with rollback capability for failed or rejected steps.

**Core Functionality:**
- **Progressive Disclosure:** Show one step at a time, not entire workflow upfront
- **Per-Step Approval:** User must explicitly approve each step ("Yes/No/Cancel")
- **Rollback via Saga Pattern:** Undo previous steps using compensating transactions (ADR-0008)
- **Progress Tracking:** Visual indicator (Step 3/5) and elapsed time
- **Risk Labeling:** Each step labeled LOW/MEDIUM/HIGH for user awareness
- **Pause/Resume:** User can pause workflow and resume later (state persisted to K0)

**Key Design Decisions:**
1. **Pause after Planner Validate stage** (ADR-0007) — Wait for user approval before Commit
2. **Rollback is user-initiated** — User chooses: "Rollback", "Keep progress", or "Cancel"
3. **State checkpointed to K0 after each step** — Persistent workflow state (<10ms P95)
4. **Max 10 steps per workflow** — Hard limit to prevent excessive approval fatigue
5. **Timeout: 5 minutes per step** — Long timeout (not 30s like basic clarification)

**Performance Targets:**
- Step approval latency: <100ms (user clicks "Yes" → agent proceeds)
- State checkpoint to K0: <10ms P95
- Rollback execution: <500ms per step (depends on compensating transaction)

---

## Context

### The Problem

**Current State:** K1 supports basic HITL clarifications (ADR-0003b Protocol 3) with 4 types:
- MULTIPLE_CHOICE, FREE_TEXT, YES_NO, APPROVAL

**Limitation:** Cannot handle **multi-step workflows** where each step needs approval:
- Production deployments (run tests → backup → deploy → validate)
- Financial transactions (verify balance → hold funds → execute transfer)
- Data migrations (validate schema → copy data → verify integrity → switch over)
- Bulk operations (analyze 1000 records → preview changes → execute batch)

**Real-World Example (FamilyOS - Planning Family Vacation):**
```
User: "Plan our summer vacation to Hawaii"

Current Behavior (BAD):
Agent: "I'll book flights, reserve hotel, rent a car, and schedule activities.
        Total cost: $4,850. This will take 15 minutes. Proceed? [Yes/No]"

User: "Yes" [approves entire workflow]

[10 minutes later]
Agent: "Flights booked, hotel reserved, booking car rental..."
[Realizes dates conflict with daughter's recital]
User: "WAIT! Cancel everything! I forgot about Emma's recital!"
[Too late - already charged $3,200 for non-refundable bookings]

Problem: User approved entire workflow upfront, no control during execution
```

**Desired Behavior (GOOD - This ADR):**
```
User: "Plan our summer vacation to Hawaii"

Agent: "🏖️ Hawaii Vacation Plan (5 steps)
  Step 1/5: Book round-trip flights (4 people)
  - Dates: June 15-22, 2025
  - Cost: $2,400 (United Airlines)
  - Duration: ~2 minutes to book
  - Risk: MEDIUM ⚠️ (non-refundable)
  - Rollback: $200 cancellation fee per person

  Proceed with step 1? [Yes/No/Cancel]"

User: "Yes"

[Agent books flights...]

Agent: "✅ Step 1 complete (2m 15s)
  Flights booked: Confirmation #UA-789456
  Total charged: $2,400

  Step 2/5: Reserve hotel (Ocean View Suite)
  - Hotel: Hilton Waikiki Beach
  - Dates: June 15-22 (7 nights)
  - Cost: $1,750 ($250/night)
  - Duration: ~1 minute to reserve
  - Risk: LOW (free cancellation until June 1)
  - Rollback: Can cancel for free

  Proceed with step 2? [Yes/No/Cancel]"

User: "Yes"

[Agent reserves hotel...]

Agent: "✅ Step 2 complete (1m 05s)
  Hotel reserved: Confirmation #HIL-234987
  Total charged: $1,750

  Step 3/5: Rent car (SUV for 7 days)
  - Vehicle: Toyota Highlander
  - Cost: $490 ($70/day)
  - Duration: ~1 minute
  - Risk: LOW (free cancellation)
  - Rollback: Can cancel anytime

  Proceed with step 3? [Yes/No/Cancel]"

User: "Wait... let me check if we need a car. No" [user changes mind]

Agent: "❓ Step 3 not approved. What would you like to do?
  A) Rollback step 2 (cancel hotel - free)
  B) Keep progress (flights + hotel), skip car
  C) Cancel entire vacation

  Your choice: ___"

User: "B" [keep flights and hotel, skip car]

Agent: "✅ Car rental skipped. Current booking status:
  - Step 1: ✅ Flights booked ($2,400)
  - Step 2: ✅ Hotel reserved ($1,750)
  - Step 3: ⏸️ Car rental skipped
  - Step 4: ⏸️ Activities not scheduled (workflow ended)
  - Step 5: ⏸️ Travel insurance not purchased

  Total spent: $4,150
  Would you like to continue with remaining steps? [Yes/No]"
```

### Research Foundation

**1. Progressive Disclosure (Nielsen Norman Group, 2006)**
- **Principle:** Show users only what they need to know at each step, not entire workflow upfront
- **Benefit:** Reduces cognitive load, prevents decision fatigue
- **Application:** Step-by-step approval shows 1 step at a time

**2. Saga Pattern (Garcia-Molina & Salem, 1987)**
- **Principle:** Long-running transactions decomposed into steps with compensating transactions
- **Benefit:** Each step can be undone if later steps fail
- **Application:** Rollback uses Saga compensating transactions (ADR-0008)

**3. Human Error Theory (Reason, 1990)**
- **Principle:** Errors are inevitable, design systems to minimize consequences
- **Benefit:** Step-by-step approval allows users to catch errors early (before executing all steps)
- **Application:** User can say "No" at step 3, preventing execution of steps 4-5

**4. Checkpoint-Restart (Chandy & Lamport, 1985)**
- **Principle:** Save consistent state periodically, restore on failure
- **Benefit:** Workflows can be resumed after interruption
- **Application:** Checkpoint workflow state to K0 after each approved step

**5. CHI Guidelines for Conversational AI (2019)**
- **Principle:** Support undo, show progress, explain consequences
- **Benefit:** Users feel in control, understand what agent is doing
- **Application:** Progress indicator (Step 3/5), rollback options, risk labeling

---

## Decision

We implement **Step-by-Step Approval Protocol** as a new ClarificationType in Protocol 3 (ADR-0003b), with the following design:

### 1. ClarificationType Enum Extension

**Add to existing Protocol 3 enums:**

```yaml
enum ClarificationType:
  MULTIPLE_CHOICE = 0      # Existing
  FREE_TEXT = 1            # Existing
  YES_NO = 2               # Existing
  APPROVAL = 3             # Existing

  # NEW in ADR-0052a
  STEP_BY_STEP = 4         # Progressive approval for multi-step workflows
```

### 2. FlatBuffers Schema

**File:** `k1/schemas/websocket/clarification.fbs`

```flatbuffers
// Step-by-step approval request (sent by agent to user)
table StepByStepRequest {
  step_id: string;                      // UUID for this step
  current_step: uint16;                 // 1-based index (1, 2, 3, ...)
  total_steps: uint16;                  // Total steps in workflow
  step_description: string;             // What this step does
  risk_level: RiskLevel;                // LOW | MEDIUM | HIGH
  estimated_duration_sec: uint32;       // Estimated time in seconds
  can_rollback: bool;                   // Whether previous steps can be undone
  rollback_description: string?;        // How rollback works (if can_rollback=true)
  workflow_id: string;                  // UUID for entire workflow
  previous_steps_summary: string?;      // Summary of completed steps (optional)
}

enum RiskLevel: byte {
  LOW = 0,        // Safe operation, minimal risk
  MEDIUM = 1,     // Moderate risk, user should understand consequences
  HIGH = 2,       // Dangerous operation, explicit warning required
}

// Step-by-step approval response (sent by user to agent)
table StepByStepResponse {
  step_id: string;                      // Which step this approves/rejects
  action: StepAction;                   // What user decided
  rollback_option: RollbackOption?;     // If action=REJECT, what to rollback
  timestamp: uint64;                    // Unix timestamp (ms)
}

enum StepAction: byte {
  APPROVE = 0,    // "Yes" - proceed with this step
  REJECT = 1,     // "No" - don't execute this step
  CANCEL = 2,     // "Cancel" - abort entire workflow
  PAUSE = 3,      // "Pause" - suspend workflow (resume later)
}

enum RollbackOption: byte {
  ROLLBACK_ALL = 0,        // Undo all previous steps
  ROLLBACK_PREVIOUS = 1,   // Undo only previous step
  KEEP_PROGRESS = 2,       // Keep all previous steps, abort remaining
  CANCEL_WORKFLOW = 3,     // Cancel without rollback
}

// Workflow state (persisted to K0 after each step)
table WorkflowState {
  workflow_id: string;                  // UUID for workflow
  session_id: string;                   // K1 session
  total_steps: uint16;                  // Total steps in workflow
  completed_steps: uint16;              // Steps successfully executed
  current_step_id: string?;             // Currently awaiting approval
  status: WorkflowStatus;               // RUNNING | PAUSED | COMPLETED | ABORTED
  started_at: uint64;                   // Unix timestamp (ms)
  last_checkpoint_at: uint64;           // Last state save timestamp
  step_history: [StepHistoryItem];      // History of all steps
}

enum WorkflowStatus: byte {
  RUNNING = 0,      // Actively executing
  PAUSED = 1,       // User paused (can resume)
  COMPLETED = 2,    // All steps successful
  ABORTED = 3,      // User cancelled
  FAILED = 4,       // Step execution failed
}

table StepHistoryItem {
  step_id: string;                      // UUID for step
  step_number: uint16;                  // 1-based index
  description: string;                  // What step did
  status: StepStatus;                   // APPROVED | REJECTED | EXECUTED | FAILED | ROLLED_BACK
  approved_at: uint64?;                 // When user approved (if applicable)
  executed_at: uint64?;                 // When agent executed (if applicable)
  duration_ms: uint32?;                 // Execution time (if executed)
  error_message: string?;               // If failed
}

enum StepStatus: byte {
  PENDING = 0,          // Awaiting approval
  APPROVED = 1,         // User approved, not yet executed
  REJECTED = 2,         // User rejected
  EXECUTING = 3,        // Currently executing
  EXECUTED = 4,         // Successfully executed
  FAILED = 5,           // Execution failed
  ROLLED_BACK = 6,      // Compensating transaction executed
}
```

### 3. Integration with Planner 4-Stage Pipeline

**Reference:** ADR-0007 (4-Stage Planning Pipeline)

**Planner Stages:**
1. **Sketch** (LLM generates plan)
2. **Expand** (Deterministic expansion)
3. **Validate** (Safety + Arbiter check)
4. **Commit** (Execute plan)

**Step-by-Step Approval Injection Point:**

```python
# BEFORE (without step-by-step approval)
async def execute_plan(plan: Plan) -> Result:
    sketch = await llm_sketch(plan)
    expanded = expand_deterministic(sketch)
    validated = await arbiter_validate(expanded)
    result = await commit_execute(validated)  # Execute entire plan
    return result

# AFTER (with step-by-step approval - ADR-0052a)
async def execute_plan_with_approval(plan: Plan) -> Result:
    sketch = await llm_sketch(plan)
    expanded = expand_deterministic(sketch)
    validated = await arbiter_validate(expanded)

    # NEW: Decompose into steps
    steps = decompose_into_steps(validated)

    workflow = WorkflowState(
        workflow_id=uuid4(),
        total_steps=len(steps),
        status=WorkflowStatus.RUNNING,
    )

    for i, step in enumerate(steps):
        # Pause and wait for user approval
        approval = await request_step_approval(step, i+1, len(steps), workflow)

        if approval.action == StepAction.APPROVE:
            # Execute this step
            result = await execute_single_step(step)
            workflow.completed_steps += 1

            # Checkpoint state to K0 (persistent)
            await checkpoint_workflow_state(workflow)

        elif approval.action == StepAction.REJECT:
            # User rejected step - handle rollback
            if approval.rollback_option == RollbackOption.ROLLBACK_ALL:
                await rollback_saga(workflow)
            elif approval.rollback_option == RollbackOption.ROLLBACK_PREVIOUS:
                await rollback_previous_step(workflow)
            elif approval.rollback_option == RollbackOption.KEEP_PROGRESS:
                break  # Abort remaining steps, keep progress

            workflow.status = WorkflowStatus.ABORTED
            return WorkflowAborted(workflow)

        elif approval.action == StepAction.CANCEL:
            # User cancelled entire workflow
            await rollback_saga(workflow)
            workflow.status = WorkflowStatus.ABORTED
            return WorkflowCancelled(workflow)

        elif approval.action == StepAction.PAUSE:
            # User paused workflow
            workflow.status = WorkflowStatus.PAUSED
            await checkpoint_workflow_state(workflow)
            return WorkflowPaused(workflow)

    workflow.status = WorkflowStatus.COMPLETED
    return WorkflowSuccess(workflow)
```

### 4. Saga Pattern Rollback Integration

**Reference:** ADR-0008 (Saga Pattern for Error Recovery)

**Compensating Transactions per Step:**

```python
class Step:
    """Single step in multi-step workflow"""
    step_id: str
    description: str
    execute_fn: Callable[[], Result]           # Forward action
    compensate_fn: Callable[[], Result]        # Rollback action
    risk_level: RiskLevel
    estimated_duration_sec: int

# Example: Family vacation planning workflow
vacation_workflow = [
    Step(
        step_id="book-flights",
        description="Book round-trip flights to Hawaii (4 people)",
        execute_fn=lambda: book_flights("SFO", "HNL", passengers=4),
        compensate_fn=lambda: cancel_flights(fee_per_person=200),  # $200 cancellation fee
        risk_level=RiskLevel.MEDIUM,
        estimated_duration_sec=120,
    ),
    Step(
        step_id="reserve-hotel",
        description="Reserve Ocean View Suite at Hilton Waikiki",
        execute_fn=lambda: reserve_hotel("Hilton Waikiki", nights=7),
        compensate_fn=lambda: cancel_hotel(free_cancellation=True),  # Free cancellation
        risk_level=RiskLevel.LOW,
        estimated_duration_sec=60,
    ),
    Step(
        step_id="rent-car",
        description="Rent SUV (Toyota Highlander) for 7 days",
        execute_fn=lambda: rent_car("SUV", days=7),
        compensate_fn=lambda: cancel_car_rental(free_cancellation=True),
        risk_level=RiskLevel.LOW,
        estimated_duration_sec=60,
    ),
    Step(
        step_id="book-activities",
        description="Book snorkeling tour and luau dinner",
        execute_fn=lambda: book_activities(["snorkeling", "luau"]),
        compensate_fn=lambda: cancel_activities(refund_percent=50),  # 50% refund
        risk_level=RiskLevel.LOW,
        estimated_duration_sec=90,
    ),
]

# Rollback execution (Saga Pattern)
async def rollback_saga(workflow: WorkflowState):
    """
    Execute compensating transactions in REVERSE order
    Example: If steps 1,2,3 executed → rollback 3,2,1
    """
    for step in reversed(workflow.step_history):
        if step.status == StepStatus.EXECUTED:
            logger.info("rollback_step", step_id=step.step_id)
            await step.compensate_fn()
            step.status = StepStatus.ROLLED_BACK

    await checkpoint_workflow_state(workflow)
```

### 5. K0 WAL Checkpoint Integration

**Reference:** ADR-0007d (Planner K0 WAL Integration)

**Checkpoint after each step:**

```python
async def checkpoint_workflow_state(workflow: WorkflowState):
    """
    Persist workflow state to K0 WAL after each step
    Target: <10ms P95 latency
    """
    # Serialize to FlatBuffers
    fb_bytes = serialize_workflow_state(workflow)

    # Write to K0 WAL (durable, append-only)
    await k0_client.append_wal(
        session_id=workflow.session_id,
        event_type="workflow_checkpoint",
        payload=fb_bytes,
        retention_sec=86400,  # 24 hours (ephemeral workflow state)
    )

    workflow.last_checkpoint_at = time_ms()
```

**Resume workflow after pause:**

```python
async def resume_workflow(workflow_id: str) -> WorkflowState:
    """
    Restore workflow state from K0 WAL
    User can resume paused workflow later
    """
    # Query K0 WAL for latest checkpoint
    events = await k0_client.query_wal(
        session_id=session_id,
        event_type="workflow_checkpoint",
        limit=1,
        order="desc",
    )

    if not events:
        raise WorkflowNotFound(workflow_id)

    # Deserialize from FlatBuffers
    workflow = deserialize_workflow_state(events[0].payload)

    if workflow.status != WorkflowStatus.PAUSED:
        raise WorkflowNotPaused(workflow_id)

    workflow.status = WorkflowStatus.RUNNING
    return workflow
```

### 6. User Experience Flow

**Agent-to-User Message (Step Approval Request):**

```json
{
  "type": "ClarificationRequest",
  "clarification_type": "STEP_BY_STEP",
  "step_by_step": {
    "step_id": "step-789abc",
    "current_step": 3,
    "total_steps": 5,
    "step_description": "Deploy v2.1.3 to prod-01 (3 instances)",
    "risk_level": "MEDIUM",
    "estimated_duration_sec": 180,
    "can_rollback": true,
    "rollback_description": "Redeploy previous version (v2.1.2)",
    "workflow_id": "workflow-123def",
    "previous_steps_summary": "✅ Tests passed (5m 23s)\n✅ Backup created (2m 11s)"
  },
  "timeout_sec": 300
}
```

**User-to-Agent Response (Approval):**

```json
{
  "type": "ClarificationResponse",
  "step_id": "step-789abc",
  "action": "APPROVE"
}
```

**User-to-Agent Response (Rejection with Rollback):**

```json
{
  "type": "ClarificationResponse",
  "step_id": "step-789abc",
  "action": "REJECT",
  "rollback_option": "KEEP_PROGRESS"
}
```

**UI Wireframe (Text-Based):**

```
┌─────────────────────────────────────────────────────┐
│ 🤖 K1 Family Assistant                              │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 🏖️ Hawaii Vacation Planning (Step 3/5)             │
│                                                     │
│ Previous Steps:                                     │
│ ✅ Step 1: Flights booked ($2,400) - 2m 15s        │
│ ✅ Step 2: Hotel reserved ($1,750) - 1m 05s        │
│                                                     │
│ ▶️ Step 3: Rent car (SUV for 7 days)               │
│    - Vehicle: Toyota Highlander                     │
│    - Cost: $490 ($70/day)                           │
│    - Duration: ~1 minute                            │
│    - Risk: LOW                                      │
│    - Rollback: Free cancellation anytime            │
│                                                     │
│ Total spent so far: $4,150                          │
│                                                     │
│ Proceed with step 3?                                │
│                                                     │
│ [Yes]  [No]  [Cancel]  [Pause]                     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**If User Clicks "No" (Rejection):**

```
┌─────────────────────────────────────────────────────┐
│ 🤖 K1 Family Assistant                              │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ❓ Step 3 not approved (Car rental skipped)         │
│                                                     │
│ What would you like to do?                          │
│                                                     │
│ A) Rollback all previous steps                     │
│    (Cancel flights + hotel)                         │
│    Cost: $800 cancellation fee                      │
│                                                     │
│ B) Keep progress, skip remaining steps             │
│    (Keep flights + hotel, no car/activities)       │
│    Current bookings: $4,150                         │
│                                                     │
│ C) Cancel entire vacation                           │
│    (Refund what we can)                             │
│    Refund: ~$1,750 (hotel only)                     │
│                                                     │
│ Your choice: [A] [B] [C]                            │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 7. Configuration & Constraints

**File:** `k1/config/step_by_step_approval.yml`

```yaml
step_by_step_approval:
  # Workflow constraints
  max_steps_per_workflow: 10                # Hard limit (prevent approval fatigue)
  max_concurrent_workflows: 3               # Per session

  # Timeout (longer than basic clarification)
  approval_timeout_sec: 300                 # 5 minutes per step (vs 30s clarification)
  workflow_timeout_sec: 3600                # 1 hour total workflow

  # Checkpoint settings
  checkpoint_after_each_step: true          # Always save state to K0
  checkpoint_retention_sec: 86400           # 24 hours (ephemeral)

  # Pause/resume
  allow_pause: true                         # User can pause workflow
  max_pause_duration_sec: 3600              # 1 hour max pause
  auto_abort_if_paused_too_long: true       # Abort if paused >1 hour

  # Rollback behavior
  default_rollback_option: "KEEP_PROGRESS"  # If user doesn't specify
  allow_partial_rollback: true              # Can rollback 1 step vs all

  # UI preferences
  show_previous_steps_summary: true         # Show completed steps
  show_estimated_duration: true             # Show ~3 minutes
  show_risk_level: true                     # Show LOW/MEDIUM/HIGH
  show_rollback_description: true           # Explain how to undo
```

### 8. Error Handling

**Timeout Behavior:**

```python
async def handle_step_timeout(step: Step, workflow: WorkflowState):
    """
    If user doesn't respond within 5 minutes
    Default: KEEP_PROGRESS (abort remaining steps)
    """
    logger.warning("step_approval_timeout",
                   step_id=step.step_id,
                   workflow_id=workflow.workflow_id)

    # Default action: Keep progress, abort remaining
    workflow.status = WorkflowStatus.ABORTED
    await checkpoint_workflow_state(workflow)

    # Notify user
    await send_notification(
        f"Workflow timed out at step {workflow.completed_steps + 1}. "
        f"Progress saved: {workflow.completed_steps}/{workflow.total_steps} steps completed."
    )
```

**Step Execution Failure:**

```python
async def handle_step_failure(step: Step, error: Exception, workflow: WorkflowState):
    """
    If step execution fails after approval
    Offer rollback options to user
    """
    logger.error("step_execution_failed",
                 step_id=step.step_id,
                 error=str(error))

    # Update step history
    step_history_item = workflow.step_history[-1]
    step_history_item.status = StepStatus.FAILED
    step_history_item.error_message = str(error)

    # Ask user what to do
    response = await ask_clarification(
        f"❌ Step {workflow.completed_steps + 1} failed: {error}\n\n"
        f"What would you like to do?\n"
        f"A) Retry this step\n"
        f"B) Rollback all previous steps\n"
        f"C) Keep progress, abort remaining\n"
        f"Your choice: ___"
    )

    if response == "A":
        # Retry
        await execute_single_step(step)
    elif response == "B":
        # Rollback all
        await rollback_saga(workflow)
    elif response == "C":
        # Keep progress
        workflow.status = WorkflowStatus.ABORTED
```

**Network Interruption (Connection Lost):**

```python
async def handle_connection_lost(workflow: WorkflowState):
    """
    If WebSocket disconnects during workflow
    Pause workflow, wait for reconnection
    """
    workflow.status = WorkflowStatus.PAUSED
    await checkpoint_workflow_state(workflow)

    # When user reconnects:
    await send_notification(
        f"⏸️ Workflow paused due to connection loss.\n"
        f"Progress: {workflow.completed_steps}/{workflow.total_steps} steps completed.\n"
        f"Type 'resume workflow' to continue."
    )
```

---

## Consequences

### Positive Consequences

**1. Enhanced User Control:**
- ✅ **Incremental approval** prevents runaway automation (user can stop at any step)
- ✅ **Rollback capability** allows users to undo mistakes (Saga Pattern)
- ✅ **Pause/resume** supports interrupted workflows (state persisted to K0)
- ✅ **Progress visibility** shows what's been done (Step 3/5)

**2. Reduced Risk:**
- ✅ **Per-step risk assessment** (LOW/MEDIUM/HIGH labeling)
- ✅ **Early abort** if user detects error before executing all steps
- ✅ **Compensating transactions** ensure clean rollback (Saga Pattern)
- ✅ **Checkpoint/restart** enables recovery from failures

**3. Better User Experience:**
- ✅ **Progressive disclosure** reduces cognitive load (1 step at a time)
- ✅ **Clear feedback** shows estimated duration and risk
- ✅ **Flexible decisions** (user can rollback, keep progress, or cancel)
- ✅ **Long timeouts** (5 min/step) accommodate user thinking time

**4. Production-Ready:**
- ✅ **State persistence** to K0 WAL (<10ms checkpoint)
- ✅ **Max 10 steps** prevents approval fatigue
- ✅ **Comprehensive error handling** (timeout, failure, network loss)
- ✅ **Observability** (Prometheus metrics for workflow completion rate)

### Negative Consequences & Mitigations

**1. Increased Latency for Multi-Step Tasks:**
- ⚠️ **Problem:** 5-minute timeout per step → 25 minutes for 5-step workflow (waiting for approvals)
- ✅ **Mitigation:** Only use step-by-step for HIGH-RISK workflows (e.g., production deployments)
- ✅ **Trade-off:** Intentional slowdown for safety (prevents accidental harm)

**2. Approval Fatigue:**
- ⚠️ **Problem:** User gets tired of approving 10 steps
- ✅ **Mitigation:** Hard limit of 10 steps per workflow (force agent to batch operations)
- ✅ **Configuration:** Allow power users to disable step-by-step for trusted workflows

**3. Workflow State Storage:**
- ⚠️ **Problem:** Storing workflow state in K0 increases memory usage
- ✅ **Mitigation:** 24-hour retention (ephemeral, not long-term storage)
- ✅ **Size estimate:** ~2KB per workflow × 3 concurrent workflows = 6KB per session

**4. Rollback Complexity:**
- ⚠️ **Problem:** Compensating transactions may fail (e.g., can't delete snapshot if already in use)
- ✅ **Mitigation:** Saga Pattern handles rollback failures (ADR-0008)
- ✅ **Logging:** Full audit trail of rollback attempts for debugging

**5. UI Complexity (Mobile):**
- ⚠️ **Problem:** Step-by-step UI may be cluttered on small screens
- ✅ **Mitigation:** Responsive UI design (collapse previous steps on mobile)
- ✅ **Alternative:** Voice mode with simplified prompts ("Proceed with step 3? Yes or No")

### Trade-Offs

| Aspect | Before ADR-0052a | After ADR-0052a | Trade-Off |
|--------|------------------|-----------------|-----------|
| **User Control** | Single approve/reject upfront | Per-step approval | ✅ Higher control, ⚠️ More interruptions |
| **Latency** | Execute entire workflow | Wait for approval each step | ⚠️ Higher latency for safety |
| **Error Recovery** | Rollback entire workflow | Rollback per step | ✅ Granular recovery, ⚠️ Complex logic |
| **State Management** | Stateless execution | Persistent workflow state | ⚠️ Higher memory usage |
| **UX Simplicity** | One decision | 5-10 decisions | ⚠️ Approval fatigue risk |

---

## Performance Budgets

**ADR-0052a Performance Targets (P95):**

| Operation | Target Latency | Memory Budget | Notes |
|-----------|----------------|---------------|-------|
| **Step Approval UI Render** | <100ms | N/A | User clicks "Yes" → agent proceeds |
| **State Checkpoint to K0** | <10ms | 2KB per workflow | After each approved step |
| **Rollback Single Step** | <500ms | N/A | Depends on compensating transaction |
| **Rollback All Steps** | <2s | N/A | N steps × 500ms each |
| **Resume Workflow from K0** | <50ms | N/A | Deserialize FlatBuffers, restore state |
| **Workflow Timeout Handling** | <100ms | N/A | Abort and notify user |

**Memory Budget per Session:**
- Workflow state: 2KB × 3 concurrent workflows = 6KB
- Step history: 10 steps × 200 bytes = 2KB
- Total: ~8KB per session (negligible)

---

## Security & Privacy Considerations

**1. Workflow State Encryption:**
- ✅ **At rest:** Workflow state encrypted in K0 WAL (AES-256-GCM)
- ✅ **In transit:** TLS 1.3 for WebSocket messages
- ✅ **Access control:** Only session owner can resume workflow

**2. Audit Trail:**
- ✅ **Log all approvals:** Who approved, when, which step
- ✅ **Log all rollbacks:** Which steps were undone, why
- ✅ **7-year retention:** Compliance requirement (SOC2)

**3. Malicious Workflow Prevention:**
- ✅ **Max 10 steps:** Prevents infinite approval loops
- ✅ **Max 3 concurrent:** Prevents workflow spam
- ✅ **Timeout enforcement:** Auto-abort if user doesn't respond (5 min/step)

**4. Compensating Transaction Safety:**
- ✅ **Idempotent rollbacks:** Can retry if first attempt fails
- ✅ **No cascading failures:** Rollback failure doesn't affect other workflows
- ✅ **Explicit logging:** Record rollback success/failure for debugging

---

## Metrics & Observability

**Success Metrics:**

| Metric | Target | Measurement |
|--------|--------|-------------|
| **% Workflows Completed** | >70% | Users finish all steps |
| **% Workflows Aborted (User)** | <20% | Users change mind mid-flow |
| **% Workflows Failed (Execution)** | <5% | Step execution errors |
| **Average Steps per Workflow** | 3-5 | Most workflows are 3-5 steps |
| **Rollback Rate** | <10% | Users rarely need to undo |
| **Pause/Resume Rate** | <5% | Few workflows interrupted |
| **Timeout Rate** | <10% | Users respond within 5 min |

**Prometheus Metrics:**

```yaml
# Workflow metrics
workflow_started_total:
  type: counter
  labels: [workflow_type, session_id]
  description: "Total workflows started"

workflow_completed_total:
  type: counter
  labels: [workflow_type, status]
  description: "Total workflows completed (COMPLETED | ABORTED | FAILED)"

workflow_step_approval_latency_seconds:
  type: histogram
  buckets: [10, 30, 60, 120, 300]
  labels: [workflow_type, step_number]
  description: "Time user takes to approve each step"

workflow_execution_duration_seconds:
  type: histogram
  buckets: [60, 300, 600, 1800, 3600]
  labels: [workflow_type]
  description: "Total workflow duration (all steps)"

workflow_rollback_total:
  type: counter
  labels: [workflow_type, rollback_option]
  description: "Total rollbacks by type (ALL | PREVIOUS | KEEP_PROGRESS)"

workflow_state_checkpoint_latency_ms:
  type: histogram
  buckets: [1, 5, 10, 20, 50]
  description: "K0 WAL checkpoint latency"
```

**Structured Logging:**

```python
logger.info("workflow_step_approved",
            workflow_id=workflow.workflow_id,
            step_id=step.step_id,
            step_number=step.current_step,
            total_steps=step.total_steps,
            risk_level=step.risk_level,
            user_approval_latency_sec=latency)

logger.info("workflow_step_executed",
            workflow_id=workflow.workflow_id,
            step_id=step.step_id,
            execution_duration_sec=duration,
            status="SUCCESS")

logger.warning("workflow_rollback_initiated",
               workflow_id=workflow.workflow_id,
               rollback_option=option,
               steps_to_rollback=count)
```

---

## Testing Strategy

### Unit Tests (WARD)

```python
from ward import test, fixture

@test("step-by-step approval: user approves all steps")
async def _():
    workflow = create_test_workflow(steps=3)

    # Step 1: Approve
    approval_1 = await request_step_approval(workflow.steps[0])
    assert approval_1.action == StepAction.APPROVE
    await execute_single_step(workflow.steps[0])

    # Step 2: Approve
    approval_2 = await request_step_approval(workflow.steps[1])
    assert approval_2.action == StepAction.APPROVE
    await execute_single_step(workflow.steps[1])

    # Step 3: Approve
    approval_3 = await request_step_approval(workflow.steps[2])
    assert approval_3.action == StepAction.APPROVE
    await execute_single_step(workflow.steps[2])

    assert workflow.status == WorkflowStatus.COMPLETED
    assert workflow.completed_steps == 3

@test("step-by-step approval: user rejects step, keeps progress")
async def _():
    workflow = create_test_workflow(steps=3)

    # Step 1: Approve
    await approve_and_execute(workflow.steps[0])

    # Step 2: Approve
    await approve_and_execute(workflow.steps[1])

    # Step 3: REJECT (keep progress)
    approval_3 = StepByStepResponse(
        step_id=workflow.steps[2].step_id,
        action=StepAction.REJECT,
        rollback_option=RollbackOption.KEEP_PROGRESS
    )

    result = await handle_step_rejection(approval_3, workflow)

    assert workflow.status == WorkflowStatus.ABORTED
    assert workflow.completed_steps == 2  # Steps 1,2 kept
    assert workflow.step_history[2].status == StepStatus.REJECTED

@test("step-by-step approval: rollback all steps")
async def _():
    workflow = create_test_workflow(steps=3)

    # Execute steps 1,2,3
    await approve_and_execute(workflow.steps[0])
    await approve_and_execute(workflow.steps[1])
    await approve_and_execute(workflow.steps[2])

    # Rollback all
    await rollback_saga(workflow)

    assert all(s.status == StepStatus.ROLLED_BACK for s in workflow.step_history)
    assert workflow.status == WorkflowStatus.ABORTED
```

### Integration Tests

```python
@test("step-by-step approval: K0 checkpoint persistence")
async def _():
    workflow = create_test_workflow(steps=3)

    # Execute step 1, checkpoint
    await approve_and_execute(workflow.steps[0])
    await checkpoint_workflow_state(workflow)

    # Simulate crash/restart
    workflow = None

    # Resume from K0
    restored_workflow = await resume_workflow(workflow_id)

    assert restored_workflow.completed_steps == 1
    assert restored_workflow.status == WorkflowStatus.RUNNING

@test("step-by-step approval: timeout handling")
async def _():
    workflow = create_test_workflow(steps=2)

    # Step 1: Approve
    await approve_and_execute(workflow.steps[0])

    # Step 2: Timeout (user doesn't respond)
    with timeout(5.5):  # 5 min + 0.5s buffer
        approval_2 = await request_step_approval(workflow.steps[1])

    # Should timeout and abort
    assert workflow.status == WorkflowStatus.ABORTED
    assert workflow.completed_steps == 1
```

---

## Implementation Checklist

**Phase 1: Schema & Data Structures (Week 1)**
- [ ] Add `STEP_BY_STEP` enum to `ClarificationType`
- [ ] Define FlatBuffers schema for `StepByStepRequest/Response`
- [ ] Create `WorkflowState` data structure
- [ ] Add `StepHistoryItem` for tracking

**Phase 2: Planner Integration (Week 2)**
- [ ] Implement `decompose_into_steps()` in Planner
- [ ] Add pause point after Validate stage (ADR-0007)
- [ ] Integrate with `execute_plan_with_approval()`
- [ ] Add progress tracking to SessionState Scoreboard

**Phase 3: Saga Pattern Rollback (Week 3)**
- [ ] Define compensating transactions per step type
- [ ] Implement `rollback_saga()` with reverse execution
- [ ] Add rollback error handling
- [ ] Test idempotent rollback operations

**Phase 4: K0 WAL Checkpoint (Week 4)**
- [ ] Implement `checkpoint_workflow_state()` (ADR-0007d)
- [ ] Add `resume_workflow()` deserialization
- [ ] Test checkpoint latency (<10ms P95)
- [ ] Implement 24-hour retention policy

**Phase 5: WebSocket Protocol (Week 5)**
- [ ] Add `StepByStepRequest` message to WebSocket
- [ ] Add `StepByStepResponse` message handling
- [ ] Implement UI wireframes (text + visual)
- [ ] Test multi-step approval flow end-to-end

**Phase 6: Error Handling & Observability (Week 6)**
- [ ] Add timeout handling (5 min/step)
- [ ] Add step execution failure handling
- [ ] Add Prometheus metrics
- [ ] Add structured logging
- [ ] WARD integration tests

---

## Related Work & Research Evidence

**1. Progressive Disclosure (Nielsen Norman Group, 2006)**
- **Source:** https://www.nngroup.com/articles/progressive-disclosure/
- **Application:** Show 1 step at a time, not entire workflow upfront

**2. Saga Pattern (Garcia-Molina & Salem, 1987)**
- **Paper:** "Sagas" - ACM SIGMOD 1987
- **Application:** Compensating transactions for rollback

**3. Human Error Theory (Reason, 1990)**
- **Book:** "Human Error" - Cambridge University Press
- **Application:** Step-by-step approval reduces error impact

**4. Checkpoint-Restart (Chandy & Lamport, 1985)**
- **Paper:** "Distributed Snapshots" - ACM TOCS 1985
- **Application:** Workflow state persistence to K0

**5. CHI Conversational AI Guidelines (2019)**
- **Source:** CHI 2019 Workshop
- **Application:** Progress indicators, rollback support

---

## References

**ADRs:**
- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md)
- [ADR-0007: 4-Stage Planning Pipeline](0007-4stage-planning-pipeline.md)
- [ADR-0008: Saga Pattern](0008-saga-pattern-error-recovery.md)
- [ADR-0007d: Planner K0 WAL Integration](0007d-planner-k0-wal-integration.md)
- [ADR-0017b: SessionState Scoreboard](0017b-sessionstate-scoreboard-qud-belief.md)

**Source Documents:**
- [HITL_MESSAGE_FLOW_ANALYSIS.md](../../HITL_MESSAGE_FLOW_ANALYSIS.md) - Gap 1 (Step-by-Step Approval)
- [whiteboard.md](../../whiteboard.md) - Planner 4-stage pipeline

---

**Document Status:** ✅ **ACCEPTED** (2025-10-14)

**Next Steps:**
1. Implement FlatBuffers schema (Week 1)
2. Integrate with Planner 4-stage pipeline (Week 2)
3. Add Saga Pattern rollback (Week 3)
4. K0 WAL checkpoint integration (Week 4)
5. WebSocket protocol implementation (Week 5)
6. WARD integration tests (Week 6)

---

**END OF ADR-0052a**
