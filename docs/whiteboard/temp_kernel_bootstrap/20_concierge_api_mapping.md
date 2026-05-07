# Concierge — Formal API Mapping

> Generated: 2026-04-12 · Scope: Inputs, Outputs, Processing for every Concierge boundary

---

## 1. Entry Points (What Goes IN)

### 1.1 User Input — IInputPort

Primary external entry. User messages arrive via bus subscription, dequeued by the mailbox consumer.

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `receive()` | — | `Envelope` | Mailbox consumer loop |
| `has_buffered()` | — | `bool` | Mailbox consumer (poll check) |

**Production adapter**: `BusInputAdapter` — subscribes to `TOPIC_USER_INPUT`, enqueues into internal buffer.

### 1.2 Bus Topic Subscriptions (Async Inbound)

The FSM (`ConciergeController`) subscribes to 20 topics at construction. Front actor and Back actor receive envelopes via mailbox routing.

| Topic | Handler | Payload Shape | Effect |
| --- | --- | --- | --- |
| `k1.user.input.v1` | Front mailbox → `front_handler` | User text + metadata | Phase1 → FSM transition → Front 10-step |
| `k1.orchestration.task.complete.v1` | FSM `_on_task_complete` | `TaskComplete` (task_id, final_answer, results, artifacts_created) | FSM → DELIVERING → Front weave/present |
| `k1.orchestration.task.failed.v1` | FSM `_on_task_failed` | `TaskFailed` (task_id, reason, error_code, tool_history) | FSM → ERROR mode |
| `k1.orchestration.task.suspended.v1` | FSM `_on_task_suspended` | HITL request (hil_type, question, options) | FSM → CLARIFYING_WORKER → Front HITL relay |
| `k1.orchestration.task.resumed.v1` | FSM `_on_task_resumed` | Resume payload (task_id, user_response) | FSM → PROGRESSING → Back resume |
| `k1.orchestration.task.dispatch.v1` | FSM `_on_task_dispatch` | `TaskDispatch` serialized | Route by tier: LOW→Back, MED→Stub, HIGH→Orch |
| `k1.orchestration.task.progress.v1` | FSM `_on_task_progress` | Progress update (task_id, pct, message) | Update task_state in SS |
| `k1.orchestration.task.cancelled.v1` | FSM `_on_task_cancelled` | Cancel confirmation (task_id) | FSM → LISTENING |
| `k1.orchestration.dag.completed.v1` | FSM | DAG completion (AggregatedResult) | Process multi-step results |
| `k1.concierge.hitl.requested.v1` | HILCoordinator | HILRequest (task_id, question, options) | Start HITL cycle |
| `k1.concierge.hitl.resolved.v1` | HILCoordinator | HILResponse (task_id, user_answer) | Resume suspended task |
| `k1.concierge.hitl.timeout.v1` | HILCoordinator | Timeout (task_id) | Auto-cancel suspended task |
| `k1.concierge.weave.candidate.v1` | WeaveBatcher | Weave candidate (task_id, result_snippet) | Buffer for batched weave |
| `k1.concierge.weave.flush.v1` | WeaveBatcher | Flush trigger | Emit buffered weave to Front |
| `k1.concierge.proactive.wake.v1` | FSM | Wake trigger (source, context) | FSM → PROACTIVE_WAKE |
| `k1.concierge.cancel.request.v1` | CancellationHandler | Cancel request (task_id) | FSM → CANCELLING |
| `k1.concierge.interrupt.v1` | FSM | Interrupt (priority, context) | FSM → INTERRUPT_HANDLING |
| `k1.concierge.dead_letter.v1` | DeadLetterConsumer | Unroutable envelope | Log + metrics |
| `k1.delta.mutation.v1` | DeltaAggregator | Mutation event | Aggregate for turn summary |
| `k1.concierge.pool.event.v1` | BackPool | Pool lifecycle (spawn/retire/health) | Manage back actor pool |

### 1.3 Phase1 Classification — IClassificationPort

Runs immediately after user input receipt, before FSM transition.

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `classify(text)` | `str` (raw user text) | `Phase1Result` | ConciergeController (pre-FSM) |

**Phase1Result** (13 slots):

| Field | Type | Purpose |
| --- | --- | --- |
| `intent` | `str` | Classified intent label |
| `domain` | `str` | Domain classification (family, health, education, etc.) |
| `urgency` | `str` | LOW / NORMAL / HIGH / CRISIS |
| `safety_band` | `str` | GREEN / AMBER / RED |
| `complexity` | `ComplexityTier` | LOW / MEDIUM / HIGH |
| `sentiment` | `float` | -1.0 to 1.0 |
| `confidence` | `float` | 0.0 to 1.0 |
| `entities` | `list[dict]` | Extracted named entities |
| `language` | `str` | Detected language code |
| `is_follow_up` | `bool` | Whether this continues prior thread |
| `requires_clarification` | `bool` | Whether ambiguity detected |
| `topic_shift` | `bool` | Whether topic changed from prior turn |
| `raw_scores` | `dict` | Model confidence per class |

**Production adapter**: `UltraBERTAdapter` (local BERT model for sub-5ms classification).

### 1.4 Lifecycle — ConciergeRuntime

| Method | Input | Output | Effect |
| --- | --- | --- | --- |
| `start()` | — | — | Creates mailbox consumer asyncio task |
| `stop()` | — | — | Cancels consumer, flushes ledger/delta/dead-letter, FSM teardown, closes SS + model |

---

## 2. Exit Points (What Goes OUT)

### 2.1 User Response — IOutputPort

Final user-facing response emission.

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `send(envelope)` | `Envelope` | `None` | Front handler (step 10, post-ReAct) |

**Production adapter**: `BusOutputAdapter` — publishes to bus for downstream delivery.

### 2.2 Bus Emissions (Front Actor — 6 categories)

| Topic | Payload | When |
| --- | --- | --- |
| `k1.orchestration.task.dispatch.v1` | `TaskDispatch` serialized | Front dispatch_task tool called |
| `k1.concierge.cancel.dispatch.v1` | Cancel request (task_id) | Front ReAct decides to cancel |
| `k1.concierge.response.final.v1` | Final response text + metadata | Post-ReAct final emission |
| `k1.delta.mutation.v1` | Mutation event (section, op, data) | Each cognitive tool write |
| `k1.concierge.turn.complete.v1` | Turn summary (trace_id, duration, token_count) | End of front handler |
| `k1.concierge.hitl.relay.v1` | HITL relay to user (question, options) | Front HITL_RELAY mode |

### 2.3 Bus Emissions (Back Actor — 8 categories)

| Topic | Payload | When |
| --- | --- | --- |
| `k1.orchestration.task.complete.v1` | `TaskComplete` (task_id, final_answer, results, artifacts) | Back submit_result(complete) |
| `k1.orchestration.task.failed.v1` | `TaskFailed` (task_id, reason, error_code, tool_history) | Back ReAct failure / budget exceeded |
| `k1.orchestration.task.suspended.v1` | HITL request (task_id, question, options) | Back submit_result(needs_human) |
| `k1.orchestration.task.progress.v1` | Progress (task_id, pct, message) | Mid-execution progress |
| `k1.orchestration.task.cancelled.v1` | Cancel confirm (task_id) | CancellationToken triggered |
| `k1.concierge.pool.event.v1` | Pool lifecycle event | BackPool management |
| `k1.delta.mutation.v1` | Mutation event | Back tool writes (rare) |
| `k1.concierge.back.heartbeat.v1` | Heartbeat (task_id, iteration) | Long-running task keep-alive |

### 2.4 Dispatch Outbound — IDispatchPort

Bridges to Fabric and Orchestrator.

| Method | Target | Input | Output | When |
| --- | --- | --- | --- | --- |
| `dispatch_direct(request)` | Fabric | `CapabilityRequest` (K1 types) | `CapabilityResult` | Back tools: invoke_capability, batch_invoke |
| `dispatch_envelope(envelope)` | Orchestrator | `TaskEnvelope` (POC types) | `AggregatedResult` | MEDIUM/HIGH tier routing |

**Production adapter**: `FabricDispatchAdapter`
- `dispatch_direct` → `self._fabric.execute(request)` (IFabricPort)
- `dispatch_envelope` → `self._orchestrator.handle_task(envelope)` (OrchestratorStub)
- Raises `RuntimeError` if orchestrator is `None`

### 2.5 Memory Recall — IMemoryPort

| Method | Input | Output | Target |
| --- | --- | --- | --- |
| `recall(query, memory_types, max_results)` | `str`, `list[str]`, `int` | `list[dict]` | K0 Memory (via BridgeRecallAdapter) |

### 2.6 LLM Calls — ILLMPort / IModelHubPort

| Method | Input | Output | Target |
| --- | --- | --- | --- |
| `execute(request)` | `HubRequest` | `HubResponse` | ModelHub (via ModelHubPOCBridge) |
| `stream_execute(request)` | `HubRequest` | `AsyncIterator[HubChunk]` | ModelHub streaming |

### 2.7 State Reads — IStatePort

| Method | Input | Output | Target |
| --- | --- | --- | --- |
| `get_section(name)` | `str` | `Any` | SessionState (via SSMStateAdapter) |
| `get_snapshot()` | — | `dict` | SessionState full snapshot |

---

## 3. Processing Pipelines

### 3.1 User Input Pipeline (Front Actor — 10 Steps)

```text
User Input → IInputPort.receive()
  → Phase1Pipeline.classify(text) → Phase1Result
    → ConciergeController.transition(phase1)
      → FSM state resolved (LISTENING/COMPANIONING/CLARIFYING_USER/...)
        → Front Handler (10-step):
          1. Guard (skip observability-only topics)
          2. Resolve FSM state → determine processing path
          3. Determine PromptMode (10 modes from FSM state + context)
          4. Compute AffectBand (crisis/elevated/neutral/positive/low)
          5. Extract domain from Phase1 + beliefs
          6. Build scenario data (templates per domain)
          7. Build chat history (from SS history_active, max 10 turns)
          8. Assemble prompt (DynamicPromptBuilder 9-stage pipeline)
          9. Run ReAct loop (LLM + tools, budget-limited)
         10. Post-loop emission:
             a. Cancel dispatches (if any) → bus
             b. Normal dispatches (dispatch_task results) → bus
             c. Final response → IOutputPort.send()
             d. HITL auto-resume check
```

### 3.2 Task Dispatch Pipeline (Front → Back)

```text
Front dispatch_task tool
  → classify_intents(intents) → SINGLE / BUNDLED / CHAINED
    → build_dispatches(intents, tier, ...) → list[TaskDispatch]
      → For each TaskDispatch:
          → dispatch_to_envelope(task_dispatch) → Envelope
            → bus.publish("k1.orchestration.task.dispatch.v1", envelope)

FSM receives dispatch:
  → route_task_sync(task, tier) → DispatchRecord
    → LOW:    DispatchRecord(topic=dispatch_topic, payload=task)
              → bus publish → Back handler directly
    → MEDIUM: DispatchRecord(envelope=TaskEnvelope(budget=Budget(max_fabric=2)))
              → dispatch_envelope → OrchestratorStub.handle_task()
    → HIGH:   DispatchRecord(envelope=TaskEnvelope(budget=Budget(max_fabric=10, planner_tokens=3500)))
              → dispatch_envelope → Orchestrator + Planner (interface-only in POC)
```

### 3.3 Task Execution Pipeline (Back Actor — 7 Steps)

```text
Back Handler receives TaskDispatch envelope:
  1. Read SS snapshot ONCE (snapshot-at-start contract)
  2. Build system prompt (back_prompt.py)
  3. Build messages (system + task context + reference_context)
  4. Select tools by tier:
     - 2 read: recall_memory, discover_capabilities
     - 4 action: invoke_capability, batch_invoke, spawn_via_fabric, execute_workflow
     - 1 control: submit_result
  5. Build CancellationToken callback (cooperative cancel)
  6. Run ReAct loop (LLM + tools, budget = tier budget_hint)
  7. Emit result:
     - complete → TaskComplete → bus "k1.orchestration.task.complete.v1"
     - needs_human → suspend → bus "k1.orchestration.task.suspended.v1"
     - failure → TaskFailed → bus "k1.orchestration.task.failed.v1"
```

### 3.4 HITL Pipeline (Human-in-the-Loop)

```text
Back submit_result(needs_human) → _submission stashed in ToolResult.data
  → FSM intercept → bus "k1.orchestration.task.suspended.v1"
    → HILCoordinator.on_suspend(task_id, hil_request)
      → Start timeout timer (configurable, default 5min)
      → Front receives → CLARIFYING_WORKER state → HITL_RELAY PromptMode
        → Front relays question to user via IOutputPort

User responds → Phase1 classifies → FSM → HITL_RESOLVE PromptMode
  → Front extracts answer → bus "k1.concierge.hitl.resolved.v1"
    → HILCoordinator.on_resolve(task_id, user_answer)
      → Cancel timeout
      → bus "k1.orchestration.task.resumed.v1"
        → Back resume_handler (10-step) resumes from suspended state

Timeout path:
  → HILCoordinator timeout fires → bus "k1.concierge.hitl.timeout.v1"
    → Auto-cancel suspended task
```

### 3.5 Weave Pipeline (Multi-Result Composition)

```text
Multiple Back tasks complete → results arrive as pending_results (deque)
  → WeaveBatcher buffers results (500ms window)
    → Flush trigger → FSM → WEAVING state
      → Front handler in WEAVE PromptMode
        → DynamicPromptBuilder assembles all pending results
          → LLM composes single coherent response
            → IOutputPort.send(woven_response)
```

### 3.6 Cancel Pipeline

```text
User says "cancel" / "stop" → Phase1 classifies as cancel intent
  → FSM → CANCELLING state → Front handler in CANCEL PromptMode
    → Front emits cancel dispatches FIRST (strict ordering)
      → CancellationToken.cancel() → cooperative signal to Back
        → Back checks token each iteration → abort ReAct loop
          → Back emits TaskCancelled → bus
            → FSM → LISTENING
```

---

## 4. Type System

### 4.1 Core Types (k1.concierge.task)

**TaskIntent** (frozen):

| Field | Type | Purpose |
| --- | --- | --- |
| `action` | `str` | What to do |
| `params` | `dict` | Parameters for the action |
| `domain` | `str` | Domain classification |
| `urgency` | `str` | LOW / NORMAL / HIGH |

**TaskDispatch** (Front → Back):

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `intents` | `list[TaskIntent]` | — | One or more intents to execute |
| `tier` | `ComplexityTier` | — | LOW / MEDIUM / HIGH |
| `task_id` | `str` | `"task-<uuid8>"` | Unique task identifier |
| `budget_hint` | `int \| None` | auto from tier | Max ReAct iterations |
| `reference_context` | `dict \| None` | `None` | Context from front conversation |
| `safety_band` | `str` | — | GREEN / AMBER / RED |
| `depends_on` | `str \| None` | `None` | For chained tasks |
| `context_snapshot` | `dict \| None` | `None` | SS snapshot for back actor |

**TaskComplete** (Back → Front):

| Field | Type | Purpose |
| --- | --- | --- |
| `task_id` | `str` | Completed task identifier |
| `final_answer` | `str` | Human-readable answer |
| `results` | `list` | Structured results |
| `artifacts_created` | `list` | Created artifacts |

**TaskFailed** (Back → Front):

| Field | Type | Purpose |
| --- | --- | --- |
| `task_id` | `str` | Failed task identifier |
| `reason` | `str` | Failure reason |
| `error_code` | `str` | Error classification |
| `tool_history` | `list` | Tools attempted before failure |

**ComplexityTier** enum: `LOW`, `MEDIUM`, `HIGH`

**TIER_BUDGET** mapping: `LOW: 6`, `MEDIUM: 10`, `HIGH: 14` (max ReAct iterations)

### 4.2 Orchestrator Types (k1.concierge.orchestrator.types — POC-local)

> **Note**: These are deliberately separate from `k1.orchestrator.types` and `k1.fabric.types`.
> Field-level differences exist (e.g., `name` vs `capability_name`, `error: str` vs `Optional[ErrorInfo]`).
> Architecture note E-0.5.5 / I-0.5.5.1 documents this as intentional POC isolation.

**Budget** (frozen):

| Field | Type | Default |
| --- | --- | --- |
| `max_fabric_calls` | `int` | `2` |
| `max_planner_tokens` | `int` | `0` |
| `timeout_ms` | `int` | from config |

**TaskEnvelope** (frozen):

| Field | Type | Validation |
| --- | --- | --- |
| `intent` | `str` | Non-empty |
| `task_id` | `str` | — |
| `context` | `dict` | — |
| `tier` | `ComplexityTier` | Must be MEDIUM or HIGH |
| `budget` | `Budget` | — |
| `session_id` | `str` | — |
| `trace_id` | `str` | — |

**CapabilityRequest** (frozen, POC):

| Field | Type |
| --- | --- |
| `name` | `str` |
| `params` | `dict` |
| `session_id` | `str` |
| `trace_id` | `str` |

**CapabilityResult** (frozen, POC):

| Field | Type |
| --- | --- |
| `success` | `bool` |
| `data` | `dict` |
| `error` | `str` |
| `capability_name` | `str` |
| `duration_ms` | `int` |

**AggregatedResult** (frozen):

| Field | Type | Purpose |
| --- | --- | --- |
| `total_steps` | `int` | Steps attempted |
| `completed` | `int` | Steps succeeded |
| `failed` | `int` | Steps failed |
| `results` | `list` | Per-step results |
| `success` | `bool` | Overall success |
| `step_results` | `list[StepResult]` | Detailed per-step |
| `duration_ms` | `int` | Total duration |
| `trace_id` | `str` | Trace propagation |
| `result_id` | `str` | Unique result ID |

Factory methods: `from_medium(cap_result)`, `from_multi_step(cap_results)`

**StepResult** (frozen):

| Field | Type | Values |
| --- | --- | --- |
| `step_id` | `str` | — |
| `capability_name` | `str` | — |
| `status` | `str` | COMPLETED / FAILED / CANCELLED / SKIPPED |
| `duration_ms` | `int` | — |
| `result` | `Any` | — |
| `error_detail` | `str \| None` | — |

### 4.3 Dispatch Record (Routing Output)

**DispatchRecord**:

| Field | Type | Purpose |
| --- | --- | --- |
| `tier` | `ComplexityTier` | Routing tier |
| `topic` | `str` | Bus topic (for LOW tier) |
| `envelope` | `TaskEnvelope \| None` | For MEDIUM/HIGH |
| `payload` | `Any` | For LOW tier |
| `priority` | `str` | Bus priority (INTERACTIVE / BACKGROUND) |

### 4.4 Envelope Bridge Functions

| Function | Input | Output | Direction |
| --- | --- | --- | --- |
| `dispatch_to_envelope(TaskDispatch)` | `TaskDispatch` | `Envelope` | Front → bus |
| `complete_to_envelope(TaskComplete)` | `TaskComplete` | `Envelope` | Back → bus |
| `failed_to_envelope(TaskFailed)` | `TaskFailed` | `Envelope` | Back → bus |

### 4.5 Intent Classification

**IntentClassification** enum: `SINGLE`, `BUNDLED`, `CHAINED`

| Classification | Meaning | Dispatch Behavior |
| --- | --- | --- |
| `SINGLE` | One intent | One TaskDispatch |
| `BUNDLED` | Multiple independent intents | Multiple parallel TaskDispatches |
| `CHAINED` | Sequential dependency chain | Multiple TaskDispatches with `depends_on` links |

---

## 5. FSM (Finite State Machine)

### 5.1 States

**ConciergeState** enum (11 values):

| State | Purpose | Entry Condition |
| --- | --- | --- |
| `LISTENING` | Idle, awaiting user input | Initial / task complete / cancel complete |
| `DISPATCHING` | Routing task to back actor or orchestrator | dispatch_task tool called |
| `COMPANIONING` | Conversational response (no task) | LOW complexity, no task needed |
| `PROGRESSING` | Task in progress, back actor working | Task dispatched, awaiting results |
| `DELIVERING` | Presenting task results to user | TaskComplete received |
| `CLARIFYING_USER` | Asking user for clarification | Ambiguity detected in Phase1 |
| `CLARIFYING_WORKER` | Relaying back actor HITL question | Back needs_human received |
| `CANCELLING` | Processing cancel request | User cancel or timeout |
| `INTERRUPT_HANDLING` | Processing high-priority interrupt | Interrupt event received |
| `PROACTIVE_WAKE` | System-initiated proactive message | Proactive trigger (rhythm, scheduler) |
| `WEAVING` | Composing multi-result response | Multiple pending_results ready |

### 5.2 Transition Table

11 states × triggers. Key transitions:

| From | Trigger | To | Guard |
| --- | --- | --- | --- |
| LISTENING | user_input | COMPANIONING / DISPATCHING | Phase1 complexity |
| LISTENING | proactive_wake | PROACTIVE_WAKE | — |
| DISPATCHING | task_dispatched | PROGRESSING | — |
| PROGRESSING | task_complete | DELIVERING / WEAVING | pending_results count |
| PROGRESSING | task_failed | DELIVERING (ERROR mode) | — |
| PROGRESSING | task_suspended | CLARIFYING_WORKER | — |
| CLARIFYING_WORKER | user_input | PROGRESSING | HITL resolve |
| CLARIFYING_USER | user_input | COMPANIONING / DISPATCHING | Phase1 re-classify |
| CANCELLING | cancel_confirmed | LISTENING | — |
| DELIVERING | delivered | LISTENING | — |
| WEAVING | woven | LISTENING | — |

### 5.3 Guard Table

FULL_GUARD_TABLE: 11 states × 30 events = 330 cells. 5 GuardActions:

| Action | Meaning |
| --- | --- |
| `ALLOW` | Transition permitted |
| `DENY` | Transition blocked |
| `QUEUE` | Event queued for later |
| `REDIRECT` | Event rerouted to different handler |
| `ABSORB` | Event acknowledged but no transition |

### 5.4 Conversation Arbiter

**ConversationArbiter** — decides when multiple signals compete.

4 `ArbiterDecision` values: `PROCESS`, `DEFER`, `MERGE`, `DROP`

---

## 6. Prompt System

### 6.1 PromptModes (10)

| Mode | FSM State | Purpose |
| --- | --- | --- |
| `STANDARD` | COMPANIONING | Normal conversational response |
| `CLARIFY_ASK` | CLARIFYING_USER | Ask user for missing info |
| `CLARIFY_RESOLVE` | CLARIFYING_USER (after answer) | Process user's clarification |
| `HITL_RELAY` | CLARIFYING_WORKER | Relay back actor question to user |
| `HITL_RESOLVE` | CLARIFYING_WORKER (after answer) | Process user's HITL answer |
| `PRESENT` | DELIVERING | Present single task result |
| `WEAVE` | WEAVING | Compose multi-task results |
| `CANCEL` | CANCELLING | Acknowledge cancellation |
| `INTERRUPT` | INTERRUPT_HANDLING | Handle priority interrupt |
| `ERROR` | DELIVERING (on failure) | Present error gracefully |

### 6.2 Prompt Sections (20 composable)

Each PromptMode maps to a subset of 20 sections via `MODE_SECTIONS`:

| Section | Content |
| --- | --- |
| `system_identity` | Agent persona, role definition |
| `safety_rules` | Safety band constraints |
| `domain_rules` | Domain-specific instructions |
| `affect_modifier` | Emotion-aware tone adjustment |
| `beliefs_summary` | Current beliefs from SS |
| `scoreboard_summary` | Active questions, topics |
| `history_context` | Recent conversation turns |
| `narrative_context` | Active threads |
| `task_context` | Active/pending tasks |
| `task_results` | Completed task results (for PRESENT/WEAVE) |
| `clarification_context` | Pending clarifications |
| `hitl_context` | HITL relay context |
| `cancel_context` | Cancel acknowledgment |
| `interrupt_context` | Interrupt details |
| `proactive_context` | Proactive wake reason |
| `tool_instructions` | Available tools + schemas |
| `output_format` | Response format constraints |
| `weave_instructions` | Multi-result composition rules |
| `error_context` | Error details for graceful handling |
| `scenario_template` | Domain-specific scenario data |

### 6.3 DynamicPromptBuilder (9-stage pipeline)

```text
1. Resolve PromptMode → section list
2. Load system_identity
3. Apply affect_modifier (AffectBand → tone)
4. Inject domain_rules
5. Build context sections (beliefs, scoreboard, history, narrative)
6. Build task-specific sections (task_context, results, HITL, cancel, etc.)
7. Add tool_instructions with schemas
8. Apply output_format
9. Assemble final prompt string
```

### 6.4 AffectBand (5 bands)

| Band | Valence Range | Effect |
| --- | --- | --- |
| `CRISIS` | Very negative | Hardcoded empathetic response, no LLM call |
| `ELEVATED` | Negative | Increased empathy, reduced task focus |
| `NEUTRAL` | Mid-range | Standard processing |
| `POSITIVE` | Positive | Upbeat tone |
| `LOW` | Very low arousal | Gentle, patient tone |

---

## 7. Tool System

### 7.1 Front Tools (10)

**Cognitive tools (6)** — mutate SessionState:

| Tool | SS Section | Operation |
| --- | --- | --- |
| `update_beliefs` | `beliefs_active` | `add_fact` |
| `update_scoreboard` | `scoreboard` | `push_question` / `push_topic` |
| `update_clarifications` | `clarifications` | `push_question` |
| `update_narrative` | `narrative_active` | `create_thread` / `update_thread` |
| `refine_affect` | `affective_now` | `set` |
| `promote_belief` | `beliefs_active` | `update_confidence` |

**Bundle tool (1):**

| Tool | Purpose |
| --- | --- |
| `update_session_bundle` | Batched multi-section write (beliefs + scoreboard + narrative + affect in one call) |

**Read tools (2):**

| Tool | Port | Method |
| --- | --- | --- |
| `recall_memory` | IMemoryPort | `recall(query, memory_types, max_results)` |
| `summarize_context` | IStatePort | `get_snapshot()` → summarize |

**Control tool (1):**

| Tool | Effect |
| --- | --- |
| `dispatch_task` | Classify intents → build TaskDispatches → publish to bus |

### 7.2 Back Tools (7)

**Read tools (2):**

| Tool | Port | Method |
| --- | --- | --- |
| `recall_memory` | IMemoryPort | `recall(query, memory_types, max_results)` |
| `discover_capabilities` | IDispatchPort (→Fabric) | `discover_capabilities(domain, intent)` |

**Action tools (4):**

| Tool | Port | Method | Tier |
| --- | --- | --- | --- |
| `invoke_capability` | IDispatchPort | `dispatch_direct(CapabilityRequest)` | Single Fabric call |
| `batch_invoke` | IDispatchPort | `dispatch_direct` × N | Multiple parallel Fabric calls |
| `spawn_via_fabric` | IDispatchPort | `dispatch_direct` (spawn type) | Spawn sub-task |
| `execute_workflow` | IDispatchPort | `dispatch_direct` (workflow type) | Multi-step workflow |

**Control tool (1):**

| Tool | Effect |
| --- | --- |
| `submit_result` | Stash result in ToolResult.data → FSM intercepts → emit bus event |

`submit_result` payloads:

| result_type | Payload Fields | Bus Event |
| --- | --- | --- |
| `"complete"` | `final_answer`, `results`, `artifacts_created` | `k1.orchestration.task.complete.v1` |
| `"needs_human"` | `hil_type`, `question`, `options`, `side_effects` | `k1.orchestration.task.suspended.v1` |

### 7.3 ToolDispatcher (7-step pipeline)

```text
1. Allowlist check (tool name in permitted set for actor type)
2. Budget check (remaining iterations)
3. Schema validation (tool args against JSON schema)
4. Safety check (safety_band × tool risk matrix)
5. Dispatch (call tool implementation)
6. Bus event (publish tool execution event for observability)
7. Record (append to tool_history in ToolContext)
```

### 7.4 ToolContext

| Field | Type | Purpose |
| --- | --- | --- |
| `actor` | `str` | `"front"` or `"back"` |
| `session_id` | `str` | Current session |
| `trace_id` | `str` | Trace propagation |
| `cognitive_trace_id` | `str` | Per-turn trace |
| `fabric_port` | `Any` | IDispatchPort for back tools |
| `writer_port` | `Any` | IWriterPort for front cognitive tools |
| `recall_fn` | `Callable` | Memory recall closure |
| `hil_coordinator` | `Any` | HILCoordinator reference |
| `session_manager` | `Any` | SS manager reference |
| `bundle_idempotency_cache` | `set` | Dedup for bundle writes |
| `tool_history` | `list` | Execution log |

---

## 8. Protocols

### 8.1 Cancellation

| Component | Role |
| --- | --- |
| `CancellationToken` | Cooperative cancel signal — `cancel()`, `is_cancelled` property |
| `CancellationHandler` | FSM-side — receives cancel request, propagates token to active Back actor |

Back actor checks `token.is_cancelled` each ReAct iteration. If cancelled, aborts loop and emits `TaskCancelled`.

### 8.2 Suspension (HITL)

| Component | Role |
| --- | --- |
| `SuspensionManager` | Enforces max concurrent suspensions, timeout policy |
| `HILCoordinator` | 8-step closed cycle: suspend → relay → wait → resolve/timeout → resume |

**HILRequest**:

| Field | Type |
| --- | --- |
| `task_id` | `str` |
| `hil_type` | `str` (`provide_info`, `approve_action`, `choose_option`) |
| `question` | `str` |
| `options` | `list` |
| `side_effects` | `str` |

**HILResponse**:

| Field | Type |
| --- | --- |
| `task_id` | `str` |
| `user_answer` | `str` |

### 8.3 Weave

| Component | Role |
| --- | --- |
| `WeaveBatcher` | Buffers pending results with 500ms window, flushes on timer or count threshold |
| `WeavePolicy` | Adaptive: decides IMMEDIATE (1 result) vs BATCH (2+ results) vs DEFERRED (low priority) |

### 8.4 Delivery Strategy

Determines output format based on result complexity and user preference.

### 8.5 Trust Accumulator

Tracks trust score across conversation — affects safety band escalation/de-escalation.

### 8.6 Task Lease (OPP)

`TaskLease` — time-bounded ownership of a task by a Back actor. Prevents double-processing.

### 8.7 OPP Pipeline (8 primitives)

Ordered Processing Pipeline for deterministic event ordering.

---

## 9. Event System

### 9.1 Canonical Events (16 types)

**Conversation events:**

| Event | Emitted By | When |
| --- | --- | --- |
| `UserInputReceived` | FSM | User input arrives |
| `IntentArbitrated` | FSM | Phase1 + arbiter decision |
| `DeadLettered` | DeadLetterConsumer | Unroutable envelope |
| `ResponseFinalDecided` | Front | Final response chosen |
| `Phase1Classified` | Phase1Pipeline | Classification complete |
| `TaskRouted` | FSM | Task routed to tier |

**Task events:**

| Event | Emitted By | When |
| --- | --- | --- |
| `TaskCreated` | Front dispatch_task | New task created |
| `TaskLeased` | BackPool | Task assigned to Back actor |
| `TaskProgressed` | Back | Mid-execution progress |
| `TaskCompleted` | Back submit_result | Task succeeded |
| `TaskFailed` | Back | Task failed |
| `TaskCancelled` | Back | Task cancelled |

**HITL events:**

| Event | Emitted By | When |
| --- | --- | --- |
| `HILRequested` | Back submit_result(needs_human) | Human input needed |
| `HILResolved` | Front HITL_RESOLVE | User answered |
| `TaskSuspended` | SuspensionManager | Task paused for HITL |
| `TaskResumed` | HILCoordinator | Task resumed after HITL |

**Weave events:**

| Event | Emitted By | When |
| --- | --- | --- |
| `WeaveCandidateArrived` | WeaveBatcher | Result buffered |
| `WeaveDecisionMade` | WeavePolicy | Batch/immediate decided |
| `WeaveEmitted` | Front WEAVE mode | Woven response sent |
| `WeaveMetricsEvent` | WeaveBatcher | Performance metrics |

**Mutation events:**

| Event | Emitted By | When |
| --- | --- | --- |
| `TurnMutationSummary` | DeltaAggregator | End of turn — all mutations summarized |

**Pool events (7):** BackPool lifecycle (spawn, retire, health, reassign, etc.)

---

## 10. Internal Orchestrator (POC-local)

### 10.1 OrchestratorStub

Handles MEDIUM-tier tasks. Injected with exactly 3 ports (structural invariant enforcement).

| Constructor Arg | Type | Constraint |
| --- | --- | --- |
| `fabric_gateway` | `IFabricGatewayPort` | Execute capabilities |
| `state_read` | `IStateReadPort` | Read-only SS access |
| `delta_emit` | `IDeltaEmitPort` | Emit events to bus/aggregator |

**Structural invariants** (enforced by only having 3 ports):
- ORCH-01: No SS writes (IStateReadPort only)
- ORCH-02: No LLM calls (no model port)
- ORCH-03: No tool execution (no ToolDispatcher)
- ORCH-04: Everything through Fabric
- ORCH-10: Budget enforcement via `_check_budget()`

**`handle_task(envelope: TaskEnvelope) -> AggregatedResult`** — 6 steps:
1. Emit `k1.orchestration.task.accepted` (task_id, tier=MEDIUM)
2. Read context snapshot via `state_read.snapshot(["beliefs_active", "task_artifacts"])`
3. Build `CapabilityRequest(name=envelope.intent, params=envelope.context["params"])`
4. Execute via `fabric_gateway.execute(cap_request)` — budget-checked
5. Build `AggregatedResult.from_medium(capability_result)`
6. Emit `k1.orchestration.dag.completed` (aggregated + task_id)

**`handle_multi_step(envelope, capability_names) -> AggregatedResult`**:
- Max 2 Fabric calls (budget check)
- `AggregatedResult.from_multi_step(results)`

### 10.2 Orchestrator Ports (Interface-only for HIGH tier)

| Port | Methods | Status |
| --- | --- | --- |
| `IFabricGatewayPort` | `execute(CapReq) → CapResult`, `execute_batch(list) → list` | **LIVE** (MEDIUM) |
| `IStateReadPort` | `snapshot(sections) → dict`, `read_section(sid, section) → dict` | **LIVE** |
| `IDeltaEmitPort` | `emit(topic, payload, trace_id)` | **LIVE** |
| `IPlannerPort` | `create_plan(...)`, `refine_plan(...)` | **INTERFACE ONLY** |
| `IWorkflowPort` | `execute_workflow(...)` | **INTERFACE ONLY** |
| `IConnectorPort` | `connect(...)` | **INTERFACE ONLY** |
| `IConstraintPort` | `validate(...)` | **INTERFACE ONLY** |
| `ISagaPort` | `compensate(...)` | **INTERFACE ONLY** |

### 10.3 Routing Configuration

| Tier | `max_fabric_calls` | `max_planner_tokens` | Path |
| --- | --- | --- | --- |
| LOW | 1 | 0 | Bus → Back directly |
| MEDIUM | 2 | 0 | TaskEnvelope → OrchestratorStub |
| HIGH | 10 | 3500 | TaskEnvelope → Orchestrator + Planner (interface-only) |

Budgets overridable via config.

---

## 11. Factory Wiring

### 11.1 PortBundle (8 hexagonal ports)

```python
@dataclass(frozen=True)
class PortBundle:
    delta: IDeltaPort           # = IBus
    input_: IInputPort
    output: IOutputPort
    state: IStatePort
    llm: ILLMPort               # = IModelHubPort
    classification: IClassificationPort | None = None   # = Phase1Pipeline
    dispatch: IDispatchPort | None = None
    memory: IMemoryPort | None = None
```

### 11.2 ConciergeFactory._construct_concierge() — 16 Steps

| Step | Action | Wires To |
| --- | --- | --- |
| 1 | Create `ConciergeController(bus, router)` | FSM |
| 2 | Wire Phase1Pipeline → FSM | IClassificationPort |
| 3 | Wire Ledger (optional) | LedgerWriter, InMemoryLedgerStore |
| 4 | Wire history sink from state port | HistoryWriter |
| 5 | Wire session state → FSM | IStatePort |
| 6 | Build `recall_fn` from `ports.memory.recall` or `_null_recall` | IMemoryPort |
| 7 | Create front + back `ToolContext` | ToolContext(actor="front"/"back") |
| 8 | Create front + back `ToolDispatcher` | — |
| 9 | Create `ExperienceLayer` (optional) | EmotionalProcessor, AffectiveMirror, etc. |
| 10 | Build `DeltaAggregator` + `DeltaApplicator` (optional) | — |
| 11 | Build `HILCoordinator` (optional) | — |
| 12 | Wire `WeaveBatcher`, `WeavePolicy`, `UserActivityTracker` | — |
| 13 | Build `DeadLetterConsumer` (optional) | — |
| **14** | **Orchestrator wiring** (see below) | OrchestratorStub |
| 15 | Subscribe front events (20 topics) | — |
| 16 | Build and return `ConciergeRuntime` | — |

### 11.3 Step 14 — Orchestrator Wiring (Critical Path)

```python
if orchestrator is not None:
    fsm.set_orchestrator(orchestrator)
elif fabric_port is not None and config.enable_orchestrator:
    orchestrator = OrchestratorStub(
        fabric_gateway=_FabricGatewayAdapter(fabric_port),
        state_read=_StateReadAdapter(ports.state),
        delta_emit=_DeltaEmitAdapter(aggregator, bus),
    )
    fsm.set_orchestrator(orchestrator)
```

**Three private bridge adapters**:

| Adapter | Converts | Target |
| --- | --- | --- |
| `_FabricGatewayAdapter(fabric_port)` | POC `CapabilityRequest(name=...)` → K1 `CapabilityRequest(capability_name=...)` | IFabricPort.execute() |
| `_StateReadAdapter(state_port)` | `snapshot(sections)` / `read_section(sid, section)` | IStatePort.get_section() |
| `_DeltaEmitAdapter(aggregator, bus)` | Routes delta events to aggregator or bus | DeltaAggregator / IBus |

---

## 12. Bus Topology

### 12.1 All 45 Topics

**STRICT mode (35)** — schema-validated, typed:

| # | Topic | Publisher | Subscriber |
| --- | --- | --- | --- |
| 1 | `k1.user.input.v1` | External (BusInputAdapter) | Front mailbox |
| 2 | `k1.orchestration.task.dispatch.v1` | Front (dispatch_task tool) | FSM (route by tier) |
| 3 | `k1.orchestration.task.complete.v1` | Back (submit_result) | FSM → Front DELIVERING |
| 4 | `k1.orchestration.task.failed.v1` | Back | FSM → Front ERROR |
| 5 | `k1.orchestration.task.suspended.v1` | Back (needs_human) | FSM → HILCoordinator |
| 6 | `k1.orchestration.task.resumed.v1` | HILCoordinator | FSM → Back resume |
| 7 | `k1.orchestration.task.progress.v1` | Back | FSM → SS update |
| 8 | `k1.orchestration.task.cancelled.v1` | Back | FSM → LISTENING |
| 9 | `k1.orchestration.task.accepted.v1` | OrchestratorStub | Observability |
| 10 | `k1.orchestration.dag.completed.v1` | OrchestratorStub | FSM |
| 11 | `k1.concierge.hitl.requested.v1` | Back | HILCoordinator |
| 12 | `k1.concierge.hitl.resolved.v1` | Front | HILCoordinator |
| 13 | `k1.concierge.hitl.timeout.v1` | HILCoordinator | Auto-cancel |
| 14 | `k1.concierge.weave.candidate.v1` | Back (result) | WeaveBatcher |
| 15 | `k1.concierge.weave.flush.v1` | WeaveBatcher (timer) | FSM → Front WEAVE |
| 16 | `k1.concierge.proactive.wake.v1` | Scheduler / RhythmController | FSM |
| 17 | `k1.concierge.cancel.request.v1` | Front / External | CancellationHandler |
| 18 | `k1.concierge.cancel.dispatch.v1` | Front | Active Back actors |
| 19 | `k1.concierge.interrupt.v1` | External | FSM |
| 20 | `k1.concierge.response.final.v1` | Front | Observability / Ledger |
| 21 | `k1.concierge.turn.complete.v1` | Front | Telemetry / Ledger |
| 22 | `k1.concierge.dead_letter.v1` | Bus router | DeadLetterConsumer |
| 23 | `k1.delta.mutation.v1` | Cognitive tools | DeltaAggregator |
| 24 | `k1.concierge.pool.event.v1` | BackPool | Pool management |
| 25 | `k1.concierge.back.heartbeat.v1` | Back | Timeout monitor |
| 26-35 | (additional strict topics) | Various | Various |

**RELAXED mode (10)** — unvalidated, extension points:

| # | Topic | Purpose |
| --- | --- | --- |
| 36-45 | `k1.concierge.ext.*` | Plugin / extension events |

---

## 13. Experience Layer

6 components for emotional intelligence:

| Component | Purpose | Key Method |
| --- | --- | --- |
| `EmotionalProcessor` | Process user emotional signals | `process(text, affect) → EmotionalAnalysis` |
| `AffectiveMirror` | Mirror appropriate emotional response | `mirror(analysis) → MirrorResponse` |
| `NarrativeWeaver` | Maintain conversation narrative coherence | `weave(turns, threads) → NarrativeContext` |
| `AnticipatoryResponder` | Predict user needs | `anticipate(context) → list[Anticipation]` |
| `ProactiveAgent` | Trigger proactive messages | `evaluate(context) → ProactiveAction \| None` |
| `RhythmController` | Manage conversation pacing | `pace(context) → PacingDecision` |

---

## 14. Ledger

### 14.1 Core Components

| Component | Purpose |
| --- | --- |
| `LedgerEntry` | Immutable event record (event_type, payload, trace_id, timestamp) |
| `ILedgerStore` | Storage interface |
| `InMemoryLedgerStore` | Default implementation |
| `LedgerWriter` | Writes entries on bus events |

### 14.2 Projections (read-only views)

| Projection | Input | Output |
| --- | --- | --- |
| `project_history(store)` | All entries | Conversation timeline |
| `project_cancel_state(store)` | Cancel entries | Active cancellations |
| `project_suspension_state(store)` | Suspension entries | Active suspensions |
| `project_hitl_state(store)` | HITL entries | HITL cycle status |
| `project_task_states(store)` | Task entries | Per-task state machine |
| `project_pending_results(store)` | Complete entries | Undelivered results |

### 14.3 Crash Recovery

`CrashRecoveryOrchestrator` — replays ledger entries to reconstruct FSM state after crash.

---

## 15. Configuration

### 15.1 Key Config Values

| Config Key | Default | Effect |
| --- | --- | --- |
| `enable_orchestrator` | `True` | Wire OrchestratorStub at Step 14 |
| `tier_fabric_budget.LOW` | `1` | Max Fabric calls for LOW tier |
| `tier_fabric_budget.MEDIUM` | `2` | Max Fabric calls for MEDIUM tier |
| `tier_fabric_budget.HIGH` | `10` | Max Fabric calls for HIGH tier |
| `tier_planner_token_budget.HIGH` | `3500` | Max planner tokens for HIGH tier |
| `tier_react_budget.LOW` | `6` | Max ReAct iterations LOW |
| `tier_react_budget.MEDIUM` | `10` | Max ReAct iterations MEDIUM |
| `tier_react_budget.HIGH` | `14` | Max ReAct iterations HIGH |
| `hitl_timeout_ms` | `300000` (5 min) | HITL response timeout |
| `weave_batch_ms` | `500` | Weave batching window |
| `max_concurrent_suspensions` | `3` | Max simultaneous HITL suspensions |
| `phase1_model` | `"ultrabert"` | Phase1 classification model |

Configuration delegates to `poc.k1_poc.config`.

---

## 16. Gaps & TODOs

| # | Gap | Severity | Detail |
| --- | --- | --- | --- |
| 1 | **HIGH tier is interface-only** | P2 | `route_task_sync` creates correct TaskEnvelope but full Orchestrator + Planner pipeline is not implemented. Comment: "POC: interface only." |
| 2 | **POC type divergence** | P3 | `orchestrator/types.py` CapabilityRequest uses `name` field; K1 Fabric uses `capability_name`. Bridge adapter (`_FabricGatewayAdapter`) converts between them. Intentional per E-0.5.5. |
| 3 | **FabricDispatchAdapter not wired by factory** | P3 | `PortBundle.dispatch: IDispatchPort` is defined, `FabricDispatchAdapter` implements it, but factory Step 14 wires orchestrator directly via `_FabricGatewayAdapter`. The `IDispatchPort` adapter in `adapters/fabric_dispatch.py` is available but not instantiated in factory. |
| 4 | **ToolContext uses `Any` extensively** | P4 | `session_manager`, `writer_port`, `hil_coordinator`, `fabric_port` typed as `Any` — avoids circular imports but loses compile-time safety. |
| 5 | **ConciergeRuntime uses `Any` for optional ports** | P4 | `model`, `session_state`, `front_dispatcher`, `back_dispatcher` are `Any`. |
| 6 | **Deferred HIGH-tier ports** | P2 | `IPlannerPort`, `IWorkflowPort`, `IConnectorPort`, `IConstraintPort`, `ISagaPort` defined as interface-only — not implemented in POC. |
| 7 | **submit_result event emission is indirect** | P4 | Tool stashes `_submission` in `ToolResult.data` for FSM intercept. Not a bug — by design — but the indirection makes the flow non-obvious. |

---

## 17. Test Coverage

- **548 test classes**, **2,679 test functions**, **38,286 test lines** across 75 test files
- Coverage areas: FSM transitions, tool dispatch, ReAct loop, HITL cycle, weave batching, cancellation, bus routing, Phase1 classification, prompt assembly, actor flows, ledger projections, crash recovery, experience layer
