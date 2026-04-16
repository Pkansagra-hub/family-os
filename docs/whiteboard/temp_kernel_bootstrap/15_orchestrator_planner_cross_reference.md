# Orchestrator ↔ Planner — Cross-Reference & Gap Analysis

> Generated: 2026-04-12 · Companion docs: `15_orchestrator_api_mapping.md`, `16_planner_api_mapping.md`

---

## 1. Interface Contract: How Orchestrator Calls Planner

### 1.1 Orchestrator Side (IPlannerPort — what Orchestrator expects)

| Method | Input | Output | When Called |
|---|---|---|---|
| `request_plan(req)` | `PlanRequest` | `PlanAck` | TaskRouter for HIGH-tier tasks |
| `micro_replan(req)` | `MicroReplanRequest` | `CommittedPlan` | DAGExecutor mid-execution (max 1/DAG, 10s timeout) |
| `cancel(request_id)` | `str` | `None` | InterruptHandler |

### 1.2 Planner Side (IMailboxPort — what Planner provides)

| Method | Input | Output | Maps To Orch Method |
|---|---|---|---|
| `enqueue(req)` | `PlanRequest` | `None` (async) | `request_plan()` |
| `micro_replan(req)` | `MicroReplanRequest` | `CommittedPlan` | `micro_replan()` |
| `send_cancel(request_id)` | `str` | `None` | `cancel()` |

### 1.3 Adapter Bridge: PlannerAdapter (S6b cross-wire)

```python
# In kernel/service.py S6b:
orchestrator._planner_port = PlannerAdapter(
    planner_mailbox=planner.get_mailbox(),   # IMailboxPort
    cb_planner=CircuitBreaker("planner", ...),
)
```

**PlannerAdapter translates:**
- `request_plan(PlanRequest)` → `mailbox.enqueue(PlanRequest)` + return `PlanAck(request_id, "ACCEPTED")`
- `micro_replan(MicroReplanRequest)` → `mailbox.micro_replan(MicroReplanRequest)` → `CommittedPlan`
- `cancel(request_id)` → `mailbox.send_cancel(request_id)`

**Circuit breaker wraps all calls** — on CB OPEN, Orchestrator degrades HIGH→MEDIUM.

---

## 2. Shared Types — Contract Alignment

All shared types are canonically defined in `k1/orchestrator/types.py`. Planner imports from there — **no type duplication**.

### 2.1 PlanRequest

| Field | Type | Default | Orch Sets | Planner Reads |
|---|---|---|---|---|
| `intent` | `str` | *required* | ✅ from TaskEnvelope.intent | ✅ → SketchService prompt |
| `trace_id` | `str` | *required* | ✅ from TaskEnvelope.trace_id | ✅ → all port calls |
| `context` | `Optional[SessionSnapshot]` | `None` | ✅ from StateRead (IStateReadPort) | ✅ → ToolCallRouter context |
| `request_id` | `str` | uuid4() | ✅ auto-generated or from envelope | ✅ → tracks through pipeline |
| `constraints` | `Dict[str, Any]` | `{}` | ✅ from TaskEnvelope.params | ✅ → PlannerConstraints.from_dict() |
| `timeout_ms` | `int` | 45000 | ✅ from TaskEnvelope.timeout_ms | ✅ → pipeline deadline |

**✅ ALIGNED** — No field mismatches. Planner consumes all fields Orchestrator sets.

### 2.2 CommittedPlan

| Field | Type | Planner Sets | Orch Reads |
|---|---|---|---|
| `plan_id` | `str` | ✅ uuid4() in CommitService | ✅ DAGExecutor tracks |
| `request_id` | `str` | ✅ from PlanRequest.request_id | ✅ matches PendingPlanContext |
| `intent` | `str` | ✅ from PlanRequest.intent | ✅ logged |
| `steps` | `List[PlanStep]` | ✅ from ExpandedPlan | ✅ DAGExecutor iterates |
| `trace_id` | `str` | ✅ from PlanRequest.trace_id | ✅ propagated |
| `dependencies` | `Dict[str, List[str]]` | ✅ from ExpandedPlan | ✅ DAGExecutor dependency resolution |
| `estimated_duration_ms` | `Optional[int]` | ✅ from ExpandedPlan | ✅ timeout calculation |
| `created_at` | `float` | ✅ time.time() | ✅ logged |

**✅ ALIGNED** — All fields produced and consumed correctly.

### 2.3 PlanStep (14 fields)

| Field | Set By | Used By Orch DAGExecutor | Status |
|---|---|---|---|
| `id` | Planner ExpandService | ✅ step tracking | ✅ |
| `capability` | Planner ExpandService | ✅ Fabric execute() | ✅ |
| `params` | Planner ExpandService | ✅ Fabric execute() | ✅ |
| `deps` | Planner ExpandService | ✅ dependency resolution | ✅ |
| `prompt_template` | Planner ExpandService | ✅ Fabric execute() | ✅ |
| `tools_granted` | Planner ExpandService | ✅ Fabric execute() | ✅ |
| `output_schema` | Planner ExpandService | ✅ result validation | ✅ |
| `condition` | Planner ExpandService | ✅ ConditionEvaluator | ✅ |
| `is_optional` | Planner ExpandService | ✅ skip on failure | ✅ |
| `has_side_effects` | Planner ExpandService | ✅ compensation decision | ✅ |
| `compensation` | Planner ExpandService | ✅ CompensationEngine | ✅ |
| `timeout_ms` | Planner ExpandService | ✅ StepRunner deadline | ✅ |
| `required_context` | Planner ExpandService | ✅ context injection | ✅ |
| `safety_band_min` | Planner ExpandService | ✅ safety gate check | **⚠ BUG** |

**⚠ PLN-GAP-02 impact:** `PlanStep.to_dict()` omits `safety_band_min`. When CommittedPlan is serialized to event bus (`plan.ready.v1`), then deserialized by Orchestrator via `CommittedPlan.from_dict()`, `safety_band_min` is **lost**. Orchestrator's safety gate will see `None` instead of the Planner's intended safety constraint.

### 2.4 MicroReplanRequest

| Field | Orch Sets | Planner Reads | Status |
|---|---|---|---|
| `original_plan_id` | ✅ from DAGExecutor plan_id | ✅ context for replan | ✅ |
| `completed_results` | ✅ Dict[step_id → StepResult] | ✅ what's done | ✅ |
| `remaining_steps` | ✅ List[PlanStep] not yet run | ✅ what's left | ✅ |
| `trace_id` | ✅ from original trace | ✅ propagated | ✅ |
| `request_id` | ✅ auto uuid4() | ✅ tracking | ✅ |
| `discoveries` | ✅ List[Discovery] from steps | ✅ replan hints | ✅ |
| `failure_context` | ✅ Optional[FailureContext] | ✅ what failed | ✅ |

**✅ ALIGNED** — All fields match.

### 2.5 PlanAck

| Field | Planner Sets | Orch Reads | Status |
|---|---|---|---|
| `request_id` | ✅ from PlanRequest | ✅ correlation | ✅ |
| `status` | ✅ "ACCEPTED" or "REJECTED" | ✅ proceed/abort | ✅ |
| `estimated_duration_ms` | ✅ optional | ✅ timeout hint | ✅ |

**✅ ALIGNED** — PlannerAdapter generates PlanAck synchronously.

---

## 3. Event Bus Contract — Topic Alignment

### 3.1 Planner Publishes → Orchestrator Subscribes

| Topic | Planner Publisher | Orch Handler | Payload Match |
|---|---|---|---|
| `k1.planner.plan.ready.v1` | `PlannerAgent` → `event_port.emit(topic, CommittedPlan.to_dict())` | `_on_plan_ready(payload)` → `CommittedPlan.from_dict(payload)` | **✅ MATCH** (with PLN-GAP-02 caveat on safety_band_min) |
| `k1.planner.plan.failed.v1` | `PlannerAgent` → `event_port.emit(topic, PlanFailedPayload)` | `_on_plan_failed(payload)` → reads `request_id`, `reason`, `error_detail`, `trace_id` | **✅ MATCH** |
| `k1.planner.plan.cancelled.v1` | `PlannerAgent` → `event_port.emit(topic, PlanCancelledPayload)` | `_on_plan_cancelled(payload)` → reads `request_id`, `trace_id` | **✅ MATCH** |

### 3.2 Orchestrator Publishes → Planner Subscribes

| Topic | Orch Publisher | Planner Handler | Payload Match |
|---|---|---|---|
| `k1.planner.plan.request.v1` | (Not currently used — Orch calls PlannerAdapter directly) | `_on_plan_request` | **N/A** — event path exists in Planner but Orch uses direct call |
| `k1.planner.plan.cancel.v1` | (Not currently used — Orch calls PlannerAdapter directly) | `_on_plan_cancel` | **N/A** — event path exists in Planner but Orch uses direct call |

### 3.3 Event Bus vs Direct Call Matrix

| Operation | Current Path | Event Bus Path | Status |
|---|---|---|---|
| Request plan | Orch → PlannerAdapter.request_plan() → mailbox.enqueue() | Orch → event `plan.request.v1` → Planner handler → mailbox.enqueue() | **Direct call used** |
| Return plan | Planner → event `plan.ready.v1` → Orch handler | Same | **Event bus used** |
| Plan failed | Planner → event `plan.failed.v1` → Orch handler | Same | **Event bus used** |
| Plan cancel | Orch → PlannerAdapter.cancel() → mailbox.send_cancel() | Orch → event `plan.cancel.v1` → Planner handler | **Direct call used** |
| Micro-replan | Orch → PlannerAdapter.micro_replan() → direct pipeline | N/A (synchronous) | **Direct call (only option)** |

**Asymmetric pattern:** Orchestrator→Planner is **direct call** (through adapter). Planner→Orchestrator is **event bus** (asynchronous). This is correct — request is synchronous (need PlanAck), response is async (plan generation takes time).

---

## 4. Data Flow Trace — Full Plan Lifecycle

```
Orchestrator                           Planner
═══════════                            ═══════
                                       
1. TaskEnvelope(tier=HIGH) arrives     
   in Orch mailbox                     
                                       
2. TaskRouter identifies HIGH tier     
                                       
3. Build PlanRequest:                  
   intent = envelope.intent            
   trace_id = envelope.trace_id        
   context = state_read()              
   constraints = envelope.params        
   timeout_ms = envelope.timeout_ms    
                                       
4. IPlannerPort.request_plan(req) ──────► PlannerAdapter.request_plan()
                                          │
5. PlanAck(ACCEPTED) ◄──────────────────  ├─► mailbox.enqueue(PlanRequest)
                                          └─► return PlanAck
6. Store PendingPlanContext              
   (request_id → timeout watcher)      
                                       
                                       7. _run_loop dequeues PlanRequest
                                       
                                       8. SKETCH: LLM CHAT temp=0.7
                                          + 4 tools (fabric, state, bridge, budget)
                                          → SketchResult
                                       
                                       9. EXPAND: LLM CHAT temp=0.3
                                          + 4 tools
                                          → ExpandedPlan
                                       
                                       10. VALIDATE: deterministic checks
                                           + LLM STRUCTURED arbiter
                                           → ValidationVerdict
                                           (if fail: revise loop ×1)
                                       
                                       11. COMMIT: no LLM
                                           plan_id = uuid4()
                                           persist via IBridgePort
                                           → CommittedPlan
                                       
                                       12. event_port.emit(
                                           "k1.planner.plan.ready.v1",
                                           committed_plan.to_dict()
                                       ──────────────────────────────────►)
                                       
13. _on_plan_ready(payload):           
    plan = CommittedPlan.from_dict()   
    Pop PendingPlanContext             
    mailbox.enqueue(plan)              
                                       
14. Main loop dequeues CommittedPlan   
                                       
15. DAGExecutor.execute(plan):         
    Topological sort steps             
    Run steps via Fabric               
    Track completions                  
                                       
    ─── If replan needed ───           
16. IPlannerPort.micro_replan(         
      MicroReplanRequest               
    ) ─────────────────────────────────► mailbox.micro_replan()
                                          → abbreviated pipeline
17. replacement_plan ◄─────────────────  → CommittedPlan (sync return)
                                       
18. DAGExecutor continues with new plan
                                       
19. All steps complete →               
    emit task.completed event          
```

---

## 5. Gap Analysis — Integration Issues

### 5.1 CRITICAL

| ID | Issue | Orch Impact | Planner Impact | Fix |
|---|---|---|---|---|
| **XREF-01** | `PlanStep.to_dict()` omits `safety_band_min` | DAGExecutor safety gate sees `None` for all steps | Planner sets it correctly but serialization drops it | Add `safety_band_min` to `PlanStep.to_dict()` in `k1/orchestrator/types.py` |
| **XREF-02** | `PlannerStateAdapter(reader=None)` | Orchestrator sends `context` in PlanRequest, but Planner also needs own state reads | Planner's ToolCallRouter `state_read` tool always returns empty | Wire real `ISessionStateReader` in S6 or share Orch's state adapter |

### 5.2 MEDIUM

| ID | Issue | Impact | Fix |
|---|---|---|---|
| **XREF-03** | `session_id="__shared__"` in PlannerStateAdapter | When state reader becomes real, Planner cannot distinguish per-session state | Propagate `session_id` from PlanRequest into adapter, or make adapter session-aware |
| **XREF-04** | No CB on Planner's internal LLM/Fabric calls | Orchestrator has CB on IPlannerPort (protects Orch from Planner), but Planner has no CB protecting itself from LLM failures | Add circuit breakers inside Planner's LLMGatewayAdapter and FabricRetrievalAdapter |
| **XREF-05** | `PlanRequest` has no `to_dict()`/`from_dict()` | Cannot use event bus path (`plan.request.v1`) — only direct call works | Add serialization if event-driven request path needed |

### 5.3 LOW

| ID | Issue | Impact | Fix |
|---|---|---|---|
| **XREF-06** | HIL stubs in Planner | Orchestrator has full HIL flow (override/fallback events); Planner has stub handlers for clarification/approval | Implement when HIL v2 required |
| **XREF-07** | Planner event subscriptions (request/cancel) unused | Planner subscribes to `plan.request.v1` and `plan.cancel.v1` but Orchestrator never publishes them (uses direct call) | No fix needed — defense-in-depth. Can enable event path for decoupled deployments |
| **XREF-08** | `MicroReplanRequest` has no `from_dict()` | Cannot receive micro-replan via event bus — only synchronous call | Add if event-driven micro-replan needed (unlikely — sync is correct pattern) |

---

## 6. Recommended Priority Fixes

### Before MS-4 Integration Testing

1. **XREF-01** — Fix `PlanStep.to_dict()` to include `safety_band_min` *(~1 line change in `k1/orchestrator/types.py`)*
2. **XREF-02** — Wire real state reader for Planner OR share Orchestrator's state adapter *(S6 wiring change)*

### Before Production

3. **XREF-04** — Add circuit breakers to Planner's internal adapters
4. **XREF-03** — Make PlannerStateAdapter session-aware
5. **XREF-05** — Add `PlanRequest.to_dict()`/`from_dict()` for observability and event-driven option

---

## 7. Compatibility Matrix

| Interface | Type Match | Serialization | Event Bus | Direct Call | Verdict |
|---|---|---|---|---|---|
| PlanRequest | ✅ Same type | ⚠ No to_dict/from_dict | ⚠ Can't use | ✅ Works | **FUNCTIONAL** |
| CommittedPlan | ✅ Same type | ✅ to_dict/from_dict | ✅ Works | N/A | **FUNCTIONAL** (PLN-GAP-02 caveat) |
| PlanStep | ✅ Same type | ⚠ safety_band_min lost | ⚠ Bug | N/A | **BUG** |
| MicroReplanRequest | ✅ Same type | ⚠ No from_dict | N/A | ✅ Works | **FUNCTIONAL** |
| PlanAck | ✅ Same type | N/A (in-process) | N/A | ✅ Works | **FUNCTIONAL** |
| PlanFailedPayload | ✅ Dict fields match | ✅ Dict | ✅ Works | N/A | **FUNCTIONAL** |
| PlanCancelledPayload | ✅ Dict fields match | ✅ Dict | ✅ Works | N/A | **FUNCTIONAL** |

**Overall: Orchestrator↔Planner integration is FUNCTIONAL with 2 required fixes (XREF-01, XREF-02) before full testing.**
