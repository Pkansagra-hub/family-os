# Planner — Formal API Mapping

> Generated: 2026-04-12 · Scope: Inputs, Outputs, Processing for every Planner boundary

---

## 1. Entry Points (What Goes IN)

### 1.1 Mailbox — Single Inbound Channel

All work enters via `IMailboxPort.dequeue()` in PlannerAgent's `_run_loop()`.

| Message Type | Fields | Enqueued By | Priority |
|---|---|---|---|
| `PlanRequest` | `intent: str`, `trace_id: str`, `context: Optional[SessionSnapshot]`, `request_id: str` (uuid4), `constraints: Dict[str, Any]`, `timeout_ms: int` (45000) | Orchestrator via `PlannerAdapter.enqueue(PlanRequest)` | FIFO (asyncio.Queue) |
| `MicroReplanRequest` | `original_plan_id: str`, `completed_results: Dict[str, StepResult]`, `remaining_steps: List[PlanStep]`, `trace_id: str`, `request_id: str` (uuid4), `discoveries: List[Discovery]`, `failure_context: Optional[FailureContext]` | Orchestrator via `PlannerAdapter.micro_replan(MicroReplanRequest)` | Direct (bypasses queue, synchronous await) |
| Cancel signal | `request_id: str` | Orchestrator via `IMailboxPort.send_cancel(request_id)` | Out-of-band cancellation |

### 1.2 Event Subscriptions (Async Inbound)

Registered at `init()` via `IEventPort.subscribe()`:

| Topic | Handler | Payload Shape | Effect |
|---|---|---|---|
| `k1.planner.plan.request.v1` | `_on_plan_request` | `PlanRequest` dict | Deserialize → `PlanRequest`, enqueue to mailbox |
| `k1.planner.plan.cancel.v1` | `_on_plan_cancel` | `{"request_id": str}` | Call `IMailboxPort.send_cancel(request_id)` |
| `k1.hil.clarification_response.v1` | `_on_hil_clarification` | TBD (V1 stub) | Future: resolve pending HIL clarification |
| `k1.hil.approval_response.v1` | `_on_hil_approval` | TBD (V1 stub) | Future: resolve pending HIL approval |

### 1.3 Direct Invocation (Micro-Replan)

`IMailboxPort.micro_replan(MicroReplanRequest) → CommittedPlan` is a **synchronous request-response** path that bypasses the mailbox queue. Called by Orchestrator's DAGExecutor when mid-execution replan is needed (max 1 per DAG, 10s timeout).

---

## 2. Exit Points (What Goes OUT)

### 2.1 Port Calls — What the Planner Sends

#### ILLMPort (→ ModelHub via LLMGatewayAdapter)

| Method | When Called | Input | Output |
|---|---|---|---|
| `execute(request)` | SketchService, ExpandService, ValidateService (arbiter) | `PlannerLLMRequest(messages: List[Dict], model: str, temperature: float, mode: str, tools: Optional[List], response_format: Optional[Dict], max_tokens: Optional[int], trace_id: str)` | `PlannerLLMResponse(content: str, tool_calls: Optional[List[Dict]], usage: TokenUsageRecord, model: str, finish_reason: str)` |

**LLM Call Profiles per Stage:**

| Stage | Mode | Temperature | Tools | Purpose |
|---|---|---|---|---|
| SketchService | `CHAT` | 0.7 | 4 tools (fabric_search, state_read, bridge_recall, budget_check) | Creative rough plan generation |
| ExpandService | `CHAT` | 0.3 | 4 tools (same set) | Precise step expansion |
| ValidateService | `STRUCTURED` | 0.0 | None | Deterministic arbiter for edge cases |

#### IFabricRetrievalPort (→ Fabric via FabricRetrievalAdapter)

| Method | When Called | Input | Output |
|---|---|---|---|
| `discover_capabilities(domain, intent, safety_band, session_context, top_k)` | ToolCallRouter (fabric_search tool) | `domain: str`, `intent: str`, `safety_band: str`, `session_context: Optional[Dict]`, `top_k: int` | `RetrievalResult(capabilities: List[CapabilityInfo], prompt_templates: List[PromptTemplate], scores: Dict[str, float])` |
| `find_relevant_prompts(intent, domain, safety_band, top_k)` | ToolCallRouter (fabric_search tool) | `intent: str`, `domain: str`, `safety_band: str`, `top_k: int` | `RetrievalResult(...)` |

**Adapter Details:** Wraps `Fabric.retrieval` service. 50ms timeout per call, 1 retry on transient failure.

#### IStateReadPort (→ SessionState via SessionStateReadAdapter)

| Method | When Called | Input | Output |
|---|---|---|---|
| `read_sections(sections, trace_id)` | ToolCallRouter (state_read tool) | `sections: List[str]`, `trace_id: str` | `SessionSnapshot(sections: Dict[str, Any], timestamp: float)` |

**Adapter Details:** Wraps `ISessionStateReader`, pre-binds `session_id` at construction. **⚠ KNOWN GAP: `reader=None` placeholder in S6 kernel wiring** — `PlannerStateAdapter(reader=None, session_id="__shared__")`.

#### IBridgePort (→ Bridge / K0 via PlannerBridgeAdapter)

| Method | When Called | Input | Output |
|---|---|---|---|
| `recall(query, selectors, trace_id)` | ToolCallRouter (bridge_recall tool) | `query: str`, `selectors: Dict[str, Any]`, `trace_id: str` | `RecallResponse(memories: List[Dict], scores: List[float], total: int)` |
| `persist_plan(committed_plan, trace_id)` | CommitService (after plan committed) | `committed_plan: CommittedPlan`, `trace_id: str` | `None` |

#### IDeltaEmitPort (→ DeltaBus via PlannerDeltaBusAdapter)

| Method | When Called | Input | Output |
|---|---|---|---|
| `emit(payload)` | PipelineController (after each stage) | `DeltaPayload(stage: str, status: str, progress: float, detail: Optional[Dict], trace_id: str)` | `None` (fire-and-forget) |

#### IEventPort (→ EventBus via PlannerEventBusAdapter)

| Method | When Called | Input | Output |
|---|---|---|---|
| `emit(topic, payload)` | PlannerAgent on plan completion/failure/cancel | topic + payload dict (see §4) | `None` |
| `subscribe(topic, handler)` | PlannerAgent at `init()` | topic pattern, async handler | `SubscriptionHandle` |
| `unsubscribe(handle)` | PlannerAgent at `shutdown()` | `SubscriptionHandle` | `bool` |

---

## 3. Processing Pipelines (What Gets Processed and How)

### 3.1 Full Plan Pipeline (PlanRequest → CommittedPlan)

```
PlanRequest
  │
  ▼
┌─────────────────────────────────────────────────┐
│ SKETCH STAGE (SketchService)                    │
│ Input:  PlanRequest.intent + context            │
│ LLM:    CHAT mode, temp 0.7, 4 tools            │
│ Tools:  fabric_search, state_read,              │
│         bridge_recall, budget_check             │
│ Output: SketchResult(rough_steps: List[RoughStep],│
│         reasoning: str, tool_calls_made: int)    │
│ Budget: max 6 tool calls enforced               │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ EXPAND STAGE (ExpandService)                    │
│ Input:  SketchResult + PlanRequest              │
│ LLM:    CHAT mode, temp 0.3, 4 tools            │
│ Output: ExpandedPlan(steps: List[PlanStep],     │
│         dependencies: Dict[str, List[str]],     │
│         estimated_duration_ms: int)              │
│ Budget: max 6 tool calls enforced               │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ VALIDATE STAGE (ValidateService)                │
│ Input:  ExpandedPlan + PlanRequest.constraints   │
│ Check:  Deterministic checks FIRST              │
│   - Step ID uniqueness                           │
│   - Dependency DAG acyclicity (Kahn's)          │
│   - safety_band compliance                       │
│   - timeout bounds                               │
│ Arbiter: LLM STRUCTURED mode if edge cases      │
│ Output: ValidationVerdict(valid: bool,          │
│         issues: List[ValidationIssue],          │
│         suggestion: Optional[str])               │
│                                                  │
│ If verdict.valid == False AND revise_count < 1:  │
│   → LOOP BACK to EXPAND with issues             │
│ If verdict.valid == False AND revise_count >= 1: │
│   → FAIL with PLAN-VALIDATE-EXHAUSTED           │
└─────────────────────────────────────────────────┘
  │ (valid == True)
  ▼
┌─────────────────────────────────────────────────┐
│ COMMIT STAGE (CommitService)                    │
│ Input:  ExpandedPlan (validated)                │
│ LLM:    NONE                                     │
│ Policy: PLAN-03 (commit policy)                 │
│ Steps:  1. Generate plan_id (uuid4)             │
│         2. Freeze steps + dependencies          │
│         3. Set created_at timestamp             │
│         4. Create CommittedPlan                  │
│         5. Persist via IBridgePort.persist_plan()│
│ Output: CommittedPlan (frozen dataclass)        │
└─────────────────────────────────────────────────┘
  │
  ▼
Event: k1.planner.plan.ready.v1 → CommittedPlan.to_dict()
```

### 3.2 Micro-Replan Pipeline (MicroReplanRequest → CommittedPlan)

```
MicroReplanRequest
  │ (synchronous, bypasses mailbox)
  ▼
┌─────────────────────────────────────────────────┐
│ MICRO-REPLAN (abbreviated pipeline)             │
│ Input:  remaining_steps + completed_results +   │
│         discoveries + failure_context            │
│ Stages: SKETCH → EXPAND → VALIDATE → COMMIT    │
│         (same pipeline, constrained scope)       │
│ Limit:  Max 1 micro-replan per DAG execution    │
│ Timeout: 10s (from Orchestrator side)            │
│ Output: CommittedPlan (replacement plan)        │
└─────────────────────────────────────────────────┘
  │
  ▼
Return directly to caller (no event emission)
Event: k1.planner.micro_replan.ready.v1 → optional notification
```

### 3.3 FSM State Machine (11 States)

```
IDLE → RECEIVING → SKETCHING → EXPANDING → VALIDATING
  ↑                                            │
  │                    ┌───────────────────────┘
  │                    │ (revise loop, max 1)
  │                    ▼
  │               REVISING → EXPANDING (re-enter)
  │
  ├── COMMITTING → PUBLISHING → IDLE
  │
  ├── CANCELLING → IDLE
  │
  └── FAILING → IDLE
```

**State transitions emit `DeltaPayload` via IDeltaEmitPort** for real-time progress tracking.

---

## 4. Events Published (What Gets Emitted)

| Topic | When | Payload Shape | Consumer |
|---|---|---|---|
| `k1.planner.plan.ready.v1` | CommitService succeeds | `CommittedPlan.to_dict()` → `{"plan_id", "request_id", "intent", "steps": [...], "dependencies": {...}, "estimated_duration_ms", "created_at", "trace_id"}` | Orchestrator `_on_plan_ready` |
| `k1.planner.plan.failed.v1` | Pipeline fails | `PlanFailedPayload` → `{"request_id", "reason": str, "error_detail": Optional[str], "trace_id"}` | Orchestrator `_on_plan_failed` |
| `k1.planner.plan.cancelled.v1` | Cancel signal received | `PlanCancelledPayload` → `{"request_id", "trace_id"}` | Orchestrator `_on_plan_cancelled` |
| `k1.planner.micro_replan.ready.v1` | Micro-replan completes | `CommittedPlan.to_dict()` | Orchestrator (notification only) |
| `k1.planner.delta.v1` | After each pipeline stage | `DeltaPayload` → `{"stage", "status", "progress", "detail", "trace_id"}` | UI / telemetry |

---

## 5. Type Transformations (Format Conversions)

### 5.1 Inbound: Orchestrator → Planner

| Source Type | Transformation | Planner Internal Type |
|---|---|---|
| `PlanRequest` (k1.orchestrator.types) | **Direct pass-through** — Planner imports from `k1.orchestrator.types` | `PlanRequest` (same type) |
| `MicroReplanRequest` (k1.orchestrator.types) | **Direct pass-through** — same import | `MicroReplanRequest` (same type) |
| `CommittedPlan` event dict | `CommittedPlan.from_dict(payload)` | `CommittedPlan` (same type) |

### 5.2 Internal: Stage-to-Stage

| From | To | Transformation |
|---|---|---|
| `PlanRequest` | `StageContext` | `StageContext(intent=req.intent, trace_id=req.trace_id, constraints=PlannerConstraints.from_dict(req.constraints), context=req.context, request_id=req.request_id)` |
| `SketchResult` | ExpandService input | `SketchResult.rough_steps: List[RoughStep]` fed to LLM prompt with full context |
| `ExpandedPlan` | ValidateService input | Direct — `ExpandedPlan.steps`, `ExpandedPlan.dependencies` checked |
| `ExpandedPlan` (validated) | `CommittedPlan` | `CommittedPlan(plan_id=uuid4(), request_id=ctx.request_id, intent=ctx.intent, steps=plan.steps, trace_id=ctx.trace_id, dependencies=plan.dependencies, estimated_duration_ms=plan.estimated_duration_ms, created_at=time.time())` |

### 5.3 Outbound: Planner → Orchestrator

| Planner Type | Transformation | Wire Format |
|---|---|---|
| `CommittedPlan` | `.to_dict()` → event bus | `{"plan_id", "request_id", "intent", "steps": [PlanStep.to_dict()], "dependencies", "estimated_duration_ms", "created_at", "trace_id"}` |
| `PlanFailedPayload` | dataclass → dict | `{"request_id", "reason", "error_detail", "trace_id"}` |
| `PlanCancelledPayload` | dataclass → dict | `{"request_id", "trace_id"}` |

**⚠ Known Bug:** `PlanStep.to_dict()` omits `safety_band_min` (field 14). Round-trip via `to_dict()`/`from_dict()` loses this field. Orchestrator's DAGExecutor may never see `safety_band_min` for steps that had it set.

---

## 6. Adapter Translations (Port ↔ Infrastructure)

### 6.1 Production Adapters

| Adapter | Port | Wraps | Translation |
|---|---|---|---|
| `PlannerMailboxAdapter` | `IMailboxPort` | `asyncio.Queue` (FIFO) | `enqueue()` → `queue.put()`, `dequeue()` → `queue.get()`, `send_cancel()` → cancellation token, `drain()` → drain queue, `micro_replan()` → direct pipeline invoke |
| `LLMGatewayAdapter` | `ILLMPort` | `ILLMRequestBus` → `ModelHubRequestBus` → ModelHub | `PlannerLLMRequest` → `ModelHubRequest` (field mapping: messages, model, temperature, mode, tools, response_format, max_tokens, trace_id) → ModelHub router → LLM provider → `HubResponse` → `PlannerLLMResponse` (field mapping: content, tool_calls, usage→TokenUsageRecord, model, finish_reason) |
| `FabricRetrievalAdapter` | `IFabricRetrievalPort` | `Fabric.retrieval` service | Direct method proxy. 50ms timeout, 1 retry on transient failure. `discover_capabilities(...)` → `retrieval.discover(...)`, `find_relevant_prompts(...)` → `retrieval.find_prompts(...)` |
| `SessionStateReadAdapter` | `IStateReadPort` | `ISessionStateReader` | Pre-binds `session_id` at construction. `read_sections(sections, trace_id)` → `reader.read(session_id, sections)` → `SessionSnapshot`. **⚠ reader=None in S6** |
| `PlannerBridgeAdapter` | `IBridgePort` | Fabric `IBridgePort` | `recall(query, selectors, trace_id)` → bridge `query(query, selectors)` → `RecallResponse`. `persist_plan(plan, trace_id)` → bridge `send_command("persist_plan", plan.to_dict())` |
| `PlannerDeltaBusAdapter` | `IDeltaEmitPort` | `IDeltaBusPort` | `emit(DeltaPayload)` → `delta_bus.emit(payload.to_dict())`. Fire-and-forget. |
| `PlannerEventBusAdapter` | `IEventPort` | Fabric `IEventPort` | Thin passthrough. `emit(topic, payload)` → `event_port.emit(topic, payload)`. `subscribe/unsubscribe` → direct delegation. |

### 6.2 Internal Services (Not Adapters, But Use Ports)

| Service | Ports Used | Purpose |
|---|---|---|
| `ToolCallRouter` | `IFabricRetrievalPort`, `IStateReadPort`, `IBridgePort` | Routes 4 tool calls (fabric_search, state_read, bridge_recall, budget_check) during SKETCH and EXPAND. Enforces max 6 tool calls per stage. |
| `HILCoordinator` | `ILLMPort`, `IEventPort` | Future V1: manages clarification/approval flows with user. Currently stub-level. |

---

## 7. Error Handling

### 7.1 Pipeline Failure Classification

| Error | Stage | Effect | Event |
|---|---|---|---|
| LLM timeout / rate limit | SKETCH, EXPAND, VALIDATE | Retry 1×, then FAIL | `plan.failed.v1` reason=`"LLM_TIMEOUT"` |
| LLM invalid response | SKETCH, EXPAND | Retry 1× with stricter prompt, then FAIL | `plan.failed.v1` reason=`"LLM_PARSE_ERROR"` |
| Validation failed (1st) | VALIDATE | Revise loop → re-EXPAND (max 1) | Delta: `stage=REVISING` |
| Validation failed (2nd) | VALIDATE | FAIL | `plan.failed.v1` reason=`"PLAN-VALIDATE-EXHAUSTED"` |
| Cancel received | Any stage | FSM → CANCELLING → IDLE | `plan.cancelled.v1` |
| Tool call budget exceeded | SKETCH, EXPAND | Hard stop at 6 calls, continue with partial | Delta: warning |
| Fabric retrieval timeout | ToolCallRouter | 50ms timeout, 1 retry, then empty result | Degraded plan quality |
| Bridge recall timeout | ToolCallRouter | Timeout → empty memories | Degraded plan quality |
| State read failure | ToolCallRouter | reader=None → no state context | **⚠ Always fails in current S6 wiring** |

### 7.2 Health Status

`PlannerAgent.health() → HealthStatus`:
- `HEALTHY`: pipeline idle, all ports responsive
- `DEGRADED`: recent failures but pipeline functional
- `UNHEALTHY`: pipeline stuck or repeated failures

---

## 8. Factory & Initialization

### 8.1 Factory Modes

| Mode | Method | Use | Ports |
|---|---|---|---|
| `create_standalone()` | Minimal, no external deps | Local testing | All mock/in-memory |
| `create_for_testing()` | Configurable mocks | Unit tests | Injected mocks |
| `create_with_ports()` | Full port injection | Integration tests | Any mix |
| `create_production()` | Production adapters | Kernel S6 wiring | All 7 real adapters |

### 8.2 create_production() — 10-Step Wiring Sequence

```
Step 1:  ToolCallRouter(fabric_port, state_port, bridge_port)
Step 2:  HILCoordinator(llm_port, event_port)
Step 3:  SketchService(llm_port, tool_router)
Step 4:  ExpandService(llm_port, tool_router)
Step 5:  ValidateService(llm_port, tool_router)
Step 6:  CommitService(bridge_port)
Step 7:  PipelineController(sketch, expand, validate, commit, delta_port)
Step 8:  PlannerAgent(pipeline, mailbox_port, event_port, hil_coordinator)
Step 9:  Register event subscriptions
Step 10: Return PlannerAgent
```

### 8.3 Kernel S6 Wiring (from `k1/kernel/service.py`)

```python
planner = PlannerFactory.create_production(
    llm_port     = LLMGatewayAdapter(ModelHubRequestBus(model_hub)),
    fabric_port  = FabricRetrievalAdapter(shared_fabric.retrieval),
    state_port   = PlannerStateAdapter(reader=None, session_id="__shared__"),  # ⚠ PLACEHOLDER
    bridge_port  = PlannerBridgeAdapter(bridge_adapter),
    delta_port   = PlannerDeltaBusAdapter(delta_bus),
    event_port   = PlannerEventBusAdapter(event_port),
    mailbox_port = PlannerMailboxAdapter(),
)
```

**S6b Cross-Wire:**
```python
orchestrator._planner_port = PlannerAdapter(
    planner_mailbox=planner.get_mailbox(),
    cb_planner=CircuitBreaker("planner", ...),
)
```

### 8.4 Shutdown Sequence

```
PlannerAgent.shutdown():
  1. Cancel _run_loop task
  2. Drain mailbox (discard pending)
  3. Unsubscribe all event subscriptions
  4. Close ports (if closeable)
```

---

## 9. Configuration

| Field | Source | Default | Effect |
|---|---|---|---|
| `sketch_temperature` | PlannerConfig | `0.7` | SketchService LLM creativity |
| `expand_temperature` | PlannerConfig | `0.3` | ExpandService LLM precision |
| `max_revise_loops` | PlannerConfig | `1` | Max VALIDATE→EXPAND retries |
| `max_tool_calls_per_stage` | PlannerConfig | `6` | ToolCallRouter budget |
| `fabric_timeout_ms` | FabricRetrievalAdapter | `50` | Per-call timeout |
| `fabric_retries` | FabricRetrievalAdapter | `1` | Retry count |
| `micro_replan_timeout_ms` | (Orchestrator-side) | `10000` | Micro-replan deadline |

---

## 10. Flags & Known Gaps

| ID | Description | Severity | Impact |
|---|---|---|---|
| **PLN-GAP-01** | `PlannerStateAdapter(reader=None)` — state_port always returns None/empty | HIGH | ToolCallRouter's `state_read` tool non-functional. Plans generated without session context. |
| **PLN-GAP-02** | `PlanStep.to_dict()` omits `safety_band_min` (field 14) | MEDIUM | Round-trip serialization loses safety band. Orchestrator DAGExecutor may execute steps without safety constraints. |
| **PLN-GAP-03** | HIL clarification/approval handlers are V1 stubs | LOW | No human-in-the-loop flow operational yet. Planner cannot pause for user input. |
| **PLN-GAP-04** | `session_id="__shared__"` for state_port | LOW | When reader becomes real, all Planner instances share one session context. Per-request session_id not propagated. |
| **PLN-GAP-05** | No circuit breaker on Planner's LLM calls | MEDIUM | Unlike Orchestrator (CB on IPlannerPort), Planner has no CB protecting its own LLM/Fabric/Bridge calls. Relies on adapter-level timeouts only. |
| **PLN-GAP-06** | `MicroReplanRequest.to_dict()` exists but no `from_dict()` | LOW | Cannot deserialize micro-replan requests from event bus. Currently only used via direct method call (not event-driven). |
| **PLN-GAP-07** | `PlanRequest` has no `to_dict()`/`from_dict()` | LOW | Cannot serialize/deserialize plan requests via event bus. Currently passed as Python objects via direct method call. |
