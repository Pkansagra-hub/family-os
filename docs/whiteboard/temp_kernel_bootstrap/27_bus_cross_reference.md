# Bus — Cross-Reference with All K1 Components

> Generated: 2025-07-12 · Scope: How the Bus connects to every K1 component; wiring patterns; topic flow analysis

---

## 1. Architecture Summary

The Bus is K1's nervous system — three communication lanes serving all components:

| Lane | Protocol | Semantics | Use Case |
| --- | --- | --- | --- |
| **Event Bus** (pub/sub) | `IBus` / `IAsyncBus` | At-most-once, multicast | Lifecycle events, observability, cross-component signals |
| **Mailbox Router** (actor) | `IMailboxRouter` / `IAsyncMailboxRouter` | At-least-once, unicast | Front↔Back actor communication, per-actor queues |
| **Delta Bus** | `FabricBusAdapter.emit_delta()` | Fire-and-forget, `Priority.REALTIME` | Agent state deltas (`k1.agent.{id}.delta.v1`) |

**Two bus scopes in the kernel:**

| Scope | Created By | Lifetime | Used By |
| --- | --- | --- | --- |
| **System bus** | `KernelService.__init__` | Application lifetime | Cross-session components (Learning, ModelHub telemetry) |
| **Session bus** | `KernelService` per-session | Session lifetime | Concierge, Fabric, SessionState, MemoryWriter, Orchestrator, Planner |

---

## 2. Kernel Wiring

### 2.1 System Bus

```
KernelConfig.system_bus_enabled = True (default)
  → system_bus = BusFactory.create_local(...)
  → async_bus  = AsyncBusBridge(system_bus)
```

- `KernelService` stores both `_bus` (sync) and `_async_bus` (async bridge)
- System bus is used for application-level telemetry and cross-session events

### 2.2 Per-Session Bus + Router

```
session_bus     = BusFactory.create_local_ordered(capture=False)
session_router  = BusFactory.create_mailbox_router()
```

- Created fresh for each session via kernel session factory
- Session bus uses `create_local_ordered` → Python backend with `TimingChain` (STRICT delivery for session-critical topics)
- Session router provides Front/Back actor mailboxes

### 2.3 Adapter Injection Pattern

The kernel creates typed adapters that wrap the session bus for each component:

```
session_bus: LocalBus
  ├── FabricBusAdapter(session_bus)    → injected into Fabric
  ├── SessionBusAdapter(session_bus)   → injected into SessionState
  └── raw session_bus                  → injected into Concierge, Orchestrator, Planner
session_router: LocalMailboxRouter
  └── register("front"), register("back") → Front/Back actor mailboxes
```

---

## 3. Per-Component Cross-Reference

### 3.1 Concierge ↔ Bus

**Role**: Primary topic definer (defines ~50 topic constants); Front/Back actor mailbox consumer; FSM event publisher/subscriber.

**Bus injection**: Raw `session_bus` + `session_router` (Front/Back mailboxes)

**Topics PUBLISHED by Concierge** (17):

| Topic | Publisher Within Concierge | Purpose |
| --- | --- | --- |
| `k1.session.user.input.v1` | Transport layer | User message entry |
| `k1.session.turn.started.v1` | FSM Controller | Turn lifecycle |
| `k1.session.turn.completed.v1` | FSM Controller (`_emit_turn_completed`) | Triggers MemoryWriter |
| `k1.session.artifact.created.v1` | Back Actor | Artifact production |
| `k1.session.state.updated.v1` | DeltaAggregator/Applicator | State change notification |
| `k1.session.task.state.v1` | Back Actor | Task state changes |
| `k1.response.stream.v1` | Front Actor | Streaming response chunks |
| `k1.response.final.v1` | Front Actor | Final response |
| `k1.response.clarification.v1` | Front Actor | Clarification output |
| `k1.orchestration.task.dispatch.v1` | FSM / dispatch_task tool | Task dispatch to Back |
| `k1.orchestration.task.cancel.v1` | FSM Controller | Cancel running task |
| `k1.orchestration.task.resume.v1` | FSM Controller | Resume suspended task |
| `k1.orchestration.task.modify.v1` | FSM Controller | Modify running task |
| `k1.orchestration.clarification.response.v1` | Concierge Front | Response to Orch clarification |
| `k1.affect.update.v1` | Session module | Emotional state update |
| `k1.proactive.fill.v1` | Session module | Proactive content |
| `k1.ui.typing.v1` | Transport | Typing indicator |

**Topics CONSUMED by Concierge** (8):

| Topic | Consumed By | From |
| --- | --- | --- |
| `k1.orchestration.task.complete.v1` | FSM Controller | Orchestrator |
| `k1.orchestration.task.failed.v1` | FSM Controller | Orchestrator |
| `k1.orchestration.task.accepted.v1` | FSM Controller | Orchestrator |
| `k1.orchestration.findings.ready.v1` | Front Actor | Orchestrator |
| `k1.orchestration.clarification.request.v1` | Front Actor | Orchestrator |
| `k1.orchestration.delta.v1` | Delta processing | Orchestrator |
| `k1.orchestration.dag.completed.v1` | FSM Controller | Orchestrator |
| `k1.hil.clarification.v1` | Front Actor | Planner HIL |

**Mailbox usage**:
- Front Actor: `session_router.register("front")` → receives orchestration results, user input
- Back Actor: `session_router.register("back")` → receives task dispatch, HIL responses

**Weave subsystem**:
- `k1.internal.weave.batch.v1` — WeaveBatcher → Front Actor
- `k1.conversation.weave.decided.v1` — WeavePolicy → Obs
- `k1.metrics.weave.v1` — WeavePolicy → Obs

### 3.2 Orchestrator ↔ Bus

**Role**: Heaviest publisher (~31 orchestration topics); DAG lifecycle; step execution; workflow scheduling.

**Bus injection**: Raw `session_bus`

**Topics PUBLISHED by Orchestrator** (26):

| Category | Topics | Count |
| --- | --- | --- |
| Task lifecycle | `task.accepted`, `task.complete`, `task.failed`, `task.suspended` | 4 |
| DAG lifecycle | `dag.started`, `dag.completed`, `dag.micro_replan` | 3 |
| Step lifecycle | `step.started/completed/failed/cancelled/skipped/retrying/schema_retry` | 7 |
| Plan coordination | `plan.requested` (→Planner), `findings.ready`, `clarification.request` | 3 |
| Delta/Error | `delta.v1`, `error.routed`, `saga.compensating` | 3 |
| Workflow | `workflow.triggered/completed/saved` | 3 |
| MCP | `mcp.tool_registered` | 1 |
| Cross-component | `clarification.request` (→Concierge), `step.execute` (→Fabric) | 2 |

**Topics CONSUMED by Orchestrator** (12):

| Topic | From | Purpose |
| --- | --- | --- |
| `k1.orchestration.task.dispatch.v1` | Concierge | Receive new tasks |
| `k1.orchestration.task.cancel.v1` | Concierge | Cancel requests |
| `k1.orchestration.task.resume.v1` | Concierge | Resume suspended |
| `k1.orchestration.task.modify.v1` | Concierge | Modify in-flight |
| `k1.orchestration.clarification.response.v1` | Concierge | Clarification answers |
| `k1.orchestration.workflow.trigger_due.v1` | Workflow Scheduler | Self-consumed trigger |
| `k1.planner.plan.ready.v1` | Planner | Plan ready for execution |
| `k1.planner.plan.failed.v1` | Planner | Planning failure |
| `k1.planner.plan.cancelled.v1` | Planner | Planning cancelled |
| `k1.planner.micro_replan.ready.v1` | Planner | Micro-replan result |
| `k1.capability.completed.v1` | Fabric | Step execution result |
| `k1.capability.failed.v1` | Fabric | Step execution failure |

**Additional consumed** (monitoring):
- `k1.fabric.agent.tool_call.v1` — Fabric agent tool calls → ExecutionMonitor
- `k1.fabric.agent.llm_call.v1` — Fabric agent LLM calls → ExecutionMonitor
- `k1.fabric.capability.contract_updated.v1` — Contract changes → GapDetector
- `k1.hil.override_response.v1` — HIL override → Orchestrator
- `k1.hil.fallback_response.v1` — HIL fallback → Orchestrator

### 3.3 Planner ↔ Bus

**Role**: Plan lifecycle publisher; HIL coordination; consumes plan requests from Orchestrator.

**Bus injection**: Raw `session_bus`

**Topics PUBLISHED by Planner** (7):

| Topic | Publisher | Subscriber |
| --- | --- | --- |
| `k1.planner.plan.ready.v1` | CommitService | Orchestrator |
| `k1.planner.plan.failed.v1` | PipelineController | Orchestrator |
| `k1.planner.plan.cancelled.v1` | PipelineController | Orchestrator |
| `k1.planner.micro_replan.ready.v1` | PipelineController | Orchestrator |
| `k1.planner.delta.v1` | CommitService, Pipeline | Obs |
| `k1.hil.clarification.v1` | HIL Coordinator | Concierge |
| `k1.hil.approval_request.v1` | HIL Coordinator | Concierge |

**Topics CONSUMED by Planner** (4):

| Topic | From | Purpose |
| --- | --- | --- |
| `k1.planner.plan.request.v1` | Orchestrator | New plan request |
| `k1.planner.plan.cancel.v1` | Orchestrator | Cancel planning |
| `k1.hil.clarification_response.v1` | Concierge | HIL answer |
| `k1.hil.approval_response.v1` | Concierge | HIL approval |

### 3.4 Fabric ↔ Bus

**Role**: Capability lifecycle events; uses `FabricBusAdapter` for Dict-based emit/subscribe; agent delta emission; largest infrastructure topic surface.

**Bus injection**: `FabricBusAdapter(session_bus)` — wraps bus with JSON serialization

**Topics PUBLISHED by Fabric** (24):

| Category | Topics | Count |
| --- | --- | --- |
| Capability lifecycle | `capability.invoked/completed/failed` | 3 |
| Registry lifecycle | `capability.registered/unregistered`, `registry.reloaded` | 3 |
| Provider lifecycle | `provider.registered/unregistered`, `provider.health.changed` | 3 |
| Contract lifecycle | `contract.validation.failed`, `output.validation.failed`, `contract_updated`, `contract.hot_reloaded`, `contract.removed` | 5 |
| Agent lifecycle | `agent.created/expired`, `agent.tool_call/llm_call` | 4 |
| Pressure | `pressure.warning/shedding` | 2 |
| Infrastructure | `meta.operation.blocked`, `learning.signal`, `health.check_cycle`, `version.conflict` | 4 |

**Topics CONSUMED by Fabric** (3):

| Topic | From | Purpose |
| --- | --- | --- |
| `k1.orchestration.step.execute.v1` | Orchestrator | Execute capability step |
| `k1.planner.discovery.request.v1` | Planner | Capability discovery |
| `k1.fabric.provider.health.check.v1` | External | Health check trigger |

**Delta Bus**: `FabricBusAdapter.emit_delta(agent_id, delta_type, section, data)` → publishes to `k1.agent.{agent_id}.delta.v1` with `Priority.REALTIME`.

### 3.5 SessionState ↔ Bus

**Role**: Mutation lifecycle events; uses `SessionBusAdapter` which prefixes all topics with `k1.session.`.

**Bus injection**: `SessionBusAdapter(session_bus)` — wraps bus with `k1.session.` prefix

**Topics PUBLISHED by SessionState** (7, via `SessionBusAdapter.emit(event_type, payload)`):

| Event Type | Bus Topic (mapped) | Purpose |
| --- | --- | --- |
| `sessionstate.mutation.requested` | `k1.session.sessionstate.mutation.requested` | Write intent |
| `sessionstate.mutation.approved` | `k1.session.sessionstate.mutation.approved` | Policy approved |
| `sessionstate.mutation.rejected` | `k1.session.sessionstate.mutation.rejected` | Policy rejected |
| `sessionstate.eviction.triggered` | `k1.session.sessionstate.eviction.triggered` | Memory pressure |
| `sessionstate.eviction.completed` | `k1.session.sessionstate.eviction.completed` | Eviction done |
| `sessionstate.emergency.activated` | `k1.session.sessionstate.emergency.activated` | Emergency mode |
| `sessionstate.emergency.resolved` | `k1.session.sessionstate.emergency.resolved` | Emergency cleared |

**Topics CONSUMED**: SessionState is primarily a data store; it does not subscribe to external bus topics.

### 3.6 ModelHub ↔ Bus

**Role**: Request/response telemetry; `BusEnvelopeDeserializer` consumes execute requests via bus.

**Bus injection**: Raw `session_bus` (for telemetry); `BusEnvelopeDeserializer` subscribes to `k1.model_hub.execute.v1`

**Topics PUBLISHED by ModelHub** (12):

| Topic | Purpose |
| --- | --- |
| `k1.model_hub.request.received/routed/response.complete` | Request lifecycle |
| `k1.model_hub.cache.hit` | Cache hit notification |
| `k1.model_hub.provider.failure/fallback.triggered` | Error handling |
| `k1.model_hub.circuit.state/budget.alert` | Circuit breaker / budget |
| `k1.model_hub.provider.health/registered` | Provider lifecycle |
| `k1.model_hub.capability.available` | Capability discovery |
| `k1.model_hub.execute.response.v1` | Execute response (bus RPC reply) |

**Topics CONSUMED by ModelHub** (1):

| Topic | Consumer | Purpose |
| --- | --- | --- |
| `k1.model_hub.execute.v1` | `BusEnvelopeDeserializer` | Bus-based RPC: deserialize envelope → `RequestRouter.route()` → publish response |

### 3.7 MemoryWriter ↔ Bus

**Role**: Background processor triggered by turn completion; emits pipeline telemetry.

**Bus injection**: `EventSubscriptionAdapter` wrapping `FabricBusAdapter` (not raw bus)

**Topics CONSUMED by MemoryWriter** (1):

| Topic | Consumer | Purpose |
| --- | --- | --- |
| `turn.complete.v1` | `TurnDispatcher._on_turn_complete()` | Primary trigger — processes conversation turn for memory extraction |

**Topics PUBLISHED by MemoryWriter** (5):

| Topic | Purpose |
| --- | --- |
| `k1.mw.filter.decision.v1` | Filter stage decision |
| `k1.mw.extraction.complete.v1` | Extraction stage complete |
| `k1.mw.batch.submitted.v1` | Batch submitted to storage |
| `k1.mw.pipeline.error.v1` | Pipeline error |
| `k1.mw.circuit.open.v1` | Circuit breaker opened |

### 3.8 Bridge (K0↔K1) ↔ Bus

**Role**: SSE events from K0 bridged into K1 bus; memory deltas from K1 bridged back to K0.

**Inbound** (K0→K1): K0 SSE events → Bridge adapter → `k1.k0.sse.*` topics (BEST_EFFORT delivery)

**Outbound** (K1→K0): MemoryWriter → `k1.memory.delta.v1` / `memory.delta` → Bridge → K0 Command Port

### 3.9 Learning Loop ↔ Bus

**Topics CONSUMED** (2):

| Topic | Purpose |
| --- | --- |
| `k1.fabric.learning.signal.v1` | Learning signals from Fabric capability execution |
| `k1.orchestration.dag.completed.v1` | DAG completion for learning feedback |

---

## 4. Topic Flow Diagrams

### 4.1 Turn Lifecycle (happy path)

```
User Input → Transport
  → [k1.session.user.input.v1] → Front Actor FSM
    → [k1.session.turn.started.v1] → Obs
    → [k1.orchestration.task.dispatch.v1] → Orchestrator
      → [k1.orchestration.plan.requested.v1] → Planner
        → [k1.planner.plan.ready.v1] → Orchestrator
          → [k1.orchestration.step.execute.v1] → Fabric
            → [k1.capability.completed.v1] → Orchestrator
          → [k1.orchestration.dag.completed.v1] → Concierge, MW, Learning
            → [k1.orchestration.task.complete.v1] → FSM
              → [k1.response.final.v1] → Transport/SSE
              → [k1.session.turn.completed.v1] → Obs
                → [turn.complete.v1] → MemoryWriter
```

### 4.2 HIL Request Flow

```
Planner HIL Coordinator
  → [k1.hil.clarification.v1] → Concierge Front
    → [k1.response.clarification.v1] → Transport (shows to user)
      → User responds
        → [k1.hil.clarification_response.v1] → Planner (resumes planning)

Planner HIL Coordinator
  → [k1.hil.approval_request.v1] → Concierge Front
    → User approves/rejects
      → [k1.hil.approval_response.v1] → Planner
```

### 4.3 Agent Delta Flow

```
Fabric AgentProvider execution
  → FabricBusAdapter.emit_delta(agent_id, delta_type, section, data)
    → [k1.agent.{agent_id}.delta.v1] Priority.REALTIME
      → Wildcard subscribers (k1.agent.*.delta.v1)
        → DeltaAggregator → SessionState update
```

### 4.4 ModelHub Bus RPC

```
Caller (Concierge/Orchestrator)
  → publish Envelope(topic="k1.model_hub.execute.v1", payload=request_json)
    → BusEnvelopeDeserializer._on_request()
      → RequestRouter.route()
        → publish Envelope(topic="k1.model_hub.execute.response.v1", payload=response_json)
          → Caller receives response
```

---

## 5. Delivery Mode Impact by Component

| Component | Critical Topics | Delivery Mode | Impact of Loss |
| --- | --- | --- | --- |
| **Orchestrator** | `task.dispatch/complete/failed` | STRICT | Lost task = hung session |
| **Planner** | `plan.request/ready/failed` | STRICT | Lost plan = stalled DAG |
| **Concierge** | `session.turn.*`, `response.*` | STRICT | Lost turn = silent failure |
| **Fabric** | `capability.completed/failed` | STRICT | Lost result = hung step |
| **HIL** | `hil.*/hitl.*` | STRICT | Lost approval = blocked flow |
| **ModelHub** | Telemetry topics | Implicit STRICT (`k1.model_hub` has no rule → falls to default RELAXED) | Telemetry loss acceptable |
| **MemoryWriter** | `turn.complete.v1` | Implicit (no `turn` prefix in rules) | Missed memory write |
| **Affect/Metrics** | `k1.affect.*`, `k1.metrics.*` | RELAXED | Acceptable loss |
| **K0 SSE** | `k1.k0.sse.*` | BEST_EFFORT | Acceptable loss |
| **Fabric Learning** | `k1.fabric.learning.*` | BEST_EFFORT | Acceptable loss |

---

## 6. Adapter Boundary Summary

| Adapter | Wraps | Interface Presented | Serialization | Priority |
| --- | --- | --- | --- | --- |
| `FabricBusAdapter` | `LocalBus` → `IEventPort(Dict) + IDeltaBusPort` | `emit(topic, Dict)`, `emit_delta(agent_id, ...)` | JSON (`json.dumps/loads`) | INTERACTIVE / REALTIME (delta) |
| `SessionBusAdapter` | `LocalBus` → `IEventPort` (ABC) | `emit(event_type, Any)`, `subscribe(event_type, handler)` | JSON (wrapped in `{"payload": ...}`) | INTERACTIVE |
| `AsyncBusBridge` | `IBus` → `IAsyncBus` | Async publish/subscribe/unsubscribe | Passthrough | Passthrough |
| `AsyncMailboxBridge` | `IMailbox` → `IAsyncMailbox` | Async receive, sync pending | Passthrough | Passthrough |
| `AsyncMailboxRouterBridge` | `IMailboxRouter` → `IAsyncMailboxRouter` | Async deliver/register/unregister | Passthrough | Passthrough |

---

## 7. Concurrency Model

### 7.1 Lock Hierarchy (LocalBus)

| Level | Lock | Scope | Held During |
| --- | --- | --- | --- |
| 1 | `_ReadWriteLock` (trie) | Subscription mutations (WRITE), topic match (READ) | subscribe/unsubscribe (W), publish trie-match (R) |
| 2 | `_SequenceGenerator._locks[topic]` | Per-topic sequence generation | publish stamping |
| 3 | `_EnvelopeIdGenerator._lock` | Global envelope ID generation | publish stamping |
| 4 | `MiddlewareChain` | Middleware processing | publish (after stamp) |

**Critical rule**: Dispatch (handler invocation) happens OUTSIDE all locks — prevents deadlock from handlers that publish.

### 7.2 Lock Hierarchy (LocalMailboxRouter)

| Level | Lock | Scope |
| --- | --- | --- |
| 1 | `LocalMailboxRouter._lock` (RLock) | Registry lookup |
| 2 | `LocalMailbox._lock` + `_not_empty` (Condition) | Per-mailbox queue ops |

**Critical rule**: Router acquires registry lock to look up mailbox, RELEASES before `_deliver()`.

---

## 8. Topic Naming Conventions

| Pattern | Example | Convention |
| --- | --- | --- |
| `k1.{component}.{noun}.{verb}.v{N}` | `k1.orchestration.task.dispatch.v1` | Standard lifecycle event |
| `k1.{component}.{noun}.v{N}` | `k1.planner.delta.v1` | Short-form (no verb) |
| `k1.agent.{id}.delta.v1` | `k1.agent.research_agent.delta.v1` | Dynamic per-agent topic |
| `k1.k0.sse.*` | `k1.k0.sse.memory.updated` | Bridge topics from K0 |
| `sessionstate.{noun}.{verb}` | `sessionstate.mutation.requested` | Internal SessionState (no `k1.` prefix, mapped by adapter) |
| `turn.complete.v1` | — | Legacy: no namespace prefix |

**Versioning**: All topics use `.v1` suffix for future schema evolution.

---

## 9. Gap Analysis

| # | Finding | Impact | Recommendation |
| --- | --- | --- | --- |
| 1 | `turn.complete.v1` lacks `k1.` namespace prefix | Inconsistent with all other topics | Rename to `k1.session.turn.complete.v1` |
| 2 | `k1.model_hub` has no timing rule → falls to `RELAXED` default | `k1.model_hub.execute.v1` (bus RPC) may deliver out-of-order | Add `k1.model_hub` → STRICT rule |
| 3 | SessionState events use `sessionstate.` prefix (no `k1.`) | After `SessionBusAdapter` mapping: `k1.session.sessionstate.mutation.requested` — double-nested | Flatten to `k1.sessionstate.mutation.requested.v1` |
| 4 | No dead-letter queue implementation | `k1.internal.dead_letter.v1` topic defined but no publisher found | Implement dead-letter middleware |
| 5 | `k1.mw` prefix has no timing rule → falls to RELAXED | Acceptable for telemetry | Confirm intentional |
| 6 | Rust adapter `receive(*, timeout_ms)` keyword-only mismatch | `TypeError` if called positionally with Rust backend | Fix to match `IMailbox` protocol |
