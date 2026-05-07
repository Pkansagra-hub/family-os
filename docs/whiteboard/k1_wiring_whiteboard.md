# K1 Concierge → Factory Wiring Whiteboard

> **Status:** CROSS-REFERENCE COMPLETE — 15 GAPS MAPPED — UNIFIED DIAGRAM CREATED — FAMILY MODEL DESIGNED — 16 DECISIONS LOCKED — READY FOR C1
> **Date:** 2026-04-01
> **Unified Diagram:** `k1/concierge/concierge_unified.mmd` (1335 lines, merged from POC 908 + K1 1112)
> **Goal:** Refactor the `k1/concierge/kernel/bootstrap.py` monolith into a hexagonal `ConciergeFactory.create_with_ports()` that matches the kernel.md Section 4.5 contract.

---

## 1. WHAT EXISTS TODAY (The Monolith)

### 1.1 Current bootstrap.py (~1,150 lines)

`k1/concierge/kernel/bootstrap.py` is a monolithic `start_kernel()` function that:

- **Creates its OWN infrastructure** (Bus, Router, Mailboxes, SessionState, Fabric)
- **Wires ~20 internal subsystems** into a `KernelRuntime` dataclass
- **Runs its own event loop** via `_mailbox_consumer()`
- **Still imports from POC**: `from poc.k1_poc.main import boot`

### 1.2 What start_kernel() Currently Creates (17 steps)

| Step | What | Source | Problem |
|------|------|--------|---------|
| 1 | IBus + IMailboxRouter + Mailboxes | `poc.k1_poc.main.boot()` | Creates own Bus — should receive from kernel |
| 2 | IModelHubPort (Gemini or Test) | `k1.concierge.llm` | Creates own — should receive via ILLMPort |
| 3 | SessionStateManager | `k1.sessionstate.factory` | Creates own — should receive via IStatePort |
| 4 | CapabilityRegistry (40 caps) | `k1.concierge.fabric` | Creates own — should receive via IDispatchPort |
| 5 | K1 Fabric + POCMockBridgeAdapter | `k1.fabric.factory` | Creates own — should receive via IDispatchPort |
| 6 | LedgerWriter + InMemoryLedgerStore | `k1.concierge.ledger` | INTERNAL — stays inside factory |
| 7 | ConciergeController (FSM) | `k1.concierge.fsm.controller` | INTERNAL — stays inside factory |
| 8 | ToolContext (11 fields) | `k1.concierge.tools` | INTERNAL — stays inside factory |
| 9 | ToolDispatchers (front + back) | `k1.concierge.tools.dispatcher` | INTERNAL — stays inside factory |
| 10 | ExperienceLayer (6 components) | `k1.concierge.experience` | INTERNAL — stays inside factory |
| 11 | DeltaAggregator + DeltaApplicator | `k1.concierge.delta` | INTERNAL — but flush path goes through IDeltaPort |
| 12 | HILCoordinator + SuspensionManager | `k1.concierge.protocols` | INTERNAL — stays inside factory |
| 13 | WeaveBatcher + WeavePolicy + UserActivityTracker | `k1.concierge.protocols` | INTERNAL — stays inside factory |
| 14 | OrchestratorStub + 3 inline adapters | `k1.concierge.orchestrator` | INTERNAL — but adapters wrap IDispatchPort |
| 15 | BackPool + BackTopicRouter | `k1.concierge.actors` | INTERNAL — stays inside factory |
| 16 | DeadLetterConsumer | `k1.concierge.fsm` | INTERNAL — stays inside factory |
| 17 | Bus subscriptions + consumer task | event loop | INTERNAL — stays inside factory |

### 1.3 The 3 Inline Adapters in bootstrap.py

These are the "glue" code that bridges external resources to internal ports:

```
_FabricGatewayAdapter   → wraps POC bridge     → IFabricGatewayPort  (used by OrchestratorStub)
_StateReadAdapter       → wraps session_state   → IStateReadPort      (used by OrchestratorStub)
_DeltaEmitAdapter       → wraps aggregator+bus  → IDeltaEmitPort      (used by OrchestratorStub)
```

---

## 2. WHAT kernel.md SAYS THE FACTORY SHOULD LOOK LIKE

### 2.1 The 8 Concierge Ports (from kernel.md Section 4.5)

| # | Port | Direction | What kernel injects | What Concierge uses it for |
|---|------|-----------|--------------------|-----------------------------|
| 1 | `IInputPort` | Inbound | `WebSocketInputAdapter(ws)` / `TestInputAdapter` | Receive user messages |
| 2 | `IOutputPort` | Outbound | `SSEOutputAdapter(sse)` / `TestOutputAdapter` | Send responses to user (stream, final, progress) |
| 3 | `IClassificationPort` | Outbound | `UltraBERTv4Adapter()` / `MockClassificationAdapter` | Phase 1 deterministic pre-LLM classification |
| 4 | `ILLMPort` | Outbound | `ModelGatewayAdapter(model_hub)` | LLM calls (chat, tool_call, structured, reason) |
| 5 | `IStatePort` | Both | `SessionKernelAdapter(session_manager)` | Read/write SessionState (Concierge is ONLY writer) |
| 6 | `IDispatchPort` | Outbound | `FabricOrchestratorAdapter(fabric, orchestrator)` | Route tasks by tier: LOW→Fabric, MED/HIGH→Orchestrator |
| 7 | `IDeltaPort` | Both | `DeltaBusAdapter(fabric_bus, bus)` | Emit events + subscribe deltas |
| 8 | `IMemoryPort` | Outbound | `BridgeRecallAdapter(bridge_client)` | K0 long-term memory recall |

### 2.2 The Factory Signature (from kernel.md Section 3 + Phase 6)

```python
concierge = await ConciergeFactory.create_with_ports(
    input_port=...,          # IInputPort
    output_port=...,         # IOutputPort
    classification_port=..., # IClassificationPort
    llm_port=...,            # ILLMPort
    state_port=...,          # IStatePort
    dispatch_port=...,       # IDispatchPort
    delta_port=...,          # IDeltaPort
    memory_port=...,         # IMemoryPort
    config=ConciergeConfig,
)
```

### 2.3 What the Factory Internally Creates (from kernel.md comments)

```
ConciergeController (FSM, 12 states)
Front/Back actors with ToolDispatchers (10 Front + 6 Back tools)
ExperienceLayer (6 components: EP, AM, NW, AR, PS, RC)
DeltaAggregator (500ms batch window → FSM.apply_deltas())
HILCoordinator (3 variants: clarification, approval, selection)
WeaveBatcher (async result batching for natural delivery)
OppPipeline (8 primitives, 9 lifecycle hooks)
DynamicPromptBuilder (10 prompt modes, 128K context window)
MutationGuard (3-tier validation for SS writes)
FrontLock (concurrency gate, priority queue)
front/back mailboxes via MailboxRouter
```

---

## 3. THE GAP: WHAT NEEDS TO CHANGE

### 3.1 Files That MOVE OUT (infrastructure the kernel provides)

| What bootstrap creates | Becomes | Injected via port |
|------------------------|---------|-------------------|
| `boot()` → Bus, Router, Mailboxes | Kernel creates Bus | IDeltaPort (for events), IInputPort (for mailbox) |
| `_create_model()` → Gemini/Test adapter | Kernel creates ModelHub | ILLMPort |
| `_create_session_state()` → SS factory | Kernel creates SessionState | IStatePort |
| `_create_capability_registry()` | Kernel creates Fabric | IDispatchPort |
| `_create_fabric()` → Fabric factory + POC bridge | Kernel creates Fabric | IDispatchPort |
| `_build_recall_fn()` → keyword scorer | Kernel provides Bridge | IMemoryPort |

### 3.2 Files That STAY INSIDE (Concierge-internal wiring)

These ~40,000 lines are ALL internal to the factory. The factory creates them, wires them together, and nobody outside needs to know:

| Internal Subsystem | Folder | Key Class | Wired To |
|-------------------|--------|-----------|----------|
| FSM (state machine) | fsm/ | ConciergeController | Everything (the brain) |
| Front Actor | actors/front.py | front_handler() | ILLMPort, IStatePort, ToolDispatcher |
| Back Actor | actors/back.py | back_handler() | ILLMPort, ToolDispatcher |
| BackPool | actors/back_pool.py | BackPool | Back Actor, CancellationTokens |
| BackTopicRouter | actors/back_router.py | BackTopicRouter | BackPool, back handlers |
| ReadyQueue | actors/ready_queue.py | ReadyQueue | Dependency ordering |
| Front ToolDispatcher | tools/dispatcher.py | create_front_dispatcher() | IStatePort (via ToolContext) |
| Back ToolDispatcher | tools/dispatcher.py | create_back_dispatcher() | IDispatchPort (via ToolContext) |
| 16 Tool Implementations | tools/implementations.py | ToolContext(11 fields) | IStatePort, IDispatchPort, IMemoryPort |
| DynamicPromptBuilder | prompt/builder.py | DynamicPromptBuilder | IStatePort (reads SS sections) |
| ReAct Loop | react/loop.py | react_loop() | ILLMPort, ToolDispatcher |
| ExperienceLayer | experience/layer.py | ExperienceLayer | IStatePort (reads), IDeltaPort (emits) |
| DeltaAggregator | delta/aggregator.py | DeltaAggregator | IDeltaPort (flush output) |
| DeltaApplicator | delta/applicator.py | DeltaApplicator | IStatePort (writes) |
| HILCoordinator | protocols/hitl_coordinator.py | HILCoordinator | IDeltaPort (emit events) |
| SuspensionManager | protocols/suspension_manager.py | SuspensionManager | IDeltaPort (emit events) |
| CancellationHandler | protocols/cancel_handler.py | CancellationHandler | Internal (tokens) |
| WeaveBatcher | protocols/weave_batcher.py | WeaveBatcher | IDeltaPort (emit weave) |
| WeavePolicy | protocols/weave_policy.py | WeavePolicy | IStatePort (reads state) |
| OppPipeline | protocols/opp_pipeline.py | OppPipeline | All optional primitives |
| TrustAccumulator | protocols/trust_accumulator.py | TrustAccumulator | Internal counters |
| OrchestratorStub | orchestrator/stub.py | OrchestratorStub | IDispatchPort (via adapters) |
| LedgerWriter | ledger/writer.py | LedgerWriter | Internal storage |
| CrashRecovery | ledger/recovery.py | CrashRecoveryOrchestrator | Ledger + FSM |
| DeadLetterConsumer | fsm/dead_letter_consumer.py | DeadLetterConsumer | IDeltaPort (bus) |
| MetricsCollector | obs/metrics.py | MetricsCollector | IDeltaPort (emit metrics) |
| EpisodicCompressor | compression/ | EpisodicCompressor | Internal heuristic |
| DynamicIdentity | identity/ | DynamicIdentityContext | Internal per-turn |
| ProactiveScheduler | scheduler/ | ProactiveScheduler | Internal timing |
| 27 Canonical Events | events/ | CanonicalEventMeta + 27 types | IDeltaPort (emit) |
| 45 Envelope Builders | bus/builders.py | build_*() functions | IDeltaPort (emit) |
| 44 Topic Definitions | bus/topics.py | TOPIC_* constants | Internal routing |
| Config | config/ | get_config() | Internal settings |

### 3.3 New Files That Need to Be Created

| File | Purpose | Lines (est.) |
|------|---------|--------------|
| `k1/concierge/factory.py` | `ConciergeFactory.create_with_ports()` — replaces `start_kernel()` | ~400 |
| `k1/concierge/ports.py` | 8 Protocol definitions (IInputPort, IOutputPort, etc.) | ~200 |
| `k1/concierge/adapters/ws_input.py` | WebSocketInputAdapter (Phase 2, stub for now) | ~50 |
| `k1/concierge/adapters/sse_output.py` | SSEOutputAdapter (Phase 2, stub for now) | ~50 |
| `k1/concierge/adapters/ultrabert.py` | UltraBERTv4Adapter (Phase 2, stub for now) | ~50 |
| `k1/concierge/adapters/model_gateway.py` | ModelGatewayAdapter — wraps IModelHubPort | ~80 |
| `k1/concierge/adapters/session_kernel.py` | SessionKernelAdapter — wraps SessionStateManager | ~100 |
| `k1/concierge/adapters/fabric_orchestrator.py` | FabricOrchestratorAdapter — routes by tier | ~150 |
| `k1/concierge/adapters/delta_bus.py` | DeltaBusAdapter — emit events + subscribe | ~80 |
| `k1/concierge/adapters/bridge_recall.py` | BridgeRecallAdapter — K0 memory recall | ~60 |
| `k1/concierge/adapters/test_adapters.py` | All 8 test adapters for standalone testing | ~200 |

---

## 4. PORT-TO-INTERNAL WIRING MAP

How each of the 8 ports flows into the internal subsystems:

### Port 1: IInputPort → receives user messages

```
IInputPort.receive()
  → FrontLock.try_deliver(envelope)
    → ConciergeController (FSM) dispatches to front_handler
```

### Port 2: IOutputPort → sends responses

```
front_handler() produces text
  → bus.publish(response.stream / response.final)
    → IOutputPort.send(OutputEvent)
```

### Port 3: IClassificationPort → Phase 1 classification

```
User message arrives
  → IClassificationPort.classify(text)
    → returns ClassificationResult (intent, entities, safety, emotion, domain)
      → ConciergeController uses for FSM transition + tier routing
```

**Current POC equivalent:** `UltraBERTPhase1Pipeline.classify()` — this wraps the UltraBERT adapter directly. In the factory pattern, the Phase 1 pipeline remains internal but calls through the port.

### Port 4: ILLMPort → LLM calls

```
react_loop() needs LLM response
  → ILLMPort.execute(HubRequest)
    → returns HubResponse (text, tool_calls, tokens, etc.)
```

**Current POC equivalent:** `ModelHubPOCBridge(GeminiConciergeAdapter)` — already implements IModelHubPort. The adapter just wraps this.

### Port 5: IStatePort → SessionState read/write

```
READS: DynamicPromptBuilder reads SS sections per SS_READ_CONFIGS
       front_handler reads control, affective_now, history_active, etc.
       back_handler snapshots beliefs, task_state, task_artifacts, etc.
       WeavePolicy reads user activity, affect
WRITES: Front tools (update_beliefs, update_scoreboard, etc.) via ToolContext.writer_port
        DeltaApplicator applies batched deltas
```

**Current POC equivalent:** Direct `session_state.get_section()` calls + `MutationRequest` writes. The adapter wraps these with MutationGuard validation.

### Port 6: IDispatchPort → task execution

```
dispatch_task tool → TaskDispatch created
  → IDispatchPort.dispatch_envelope(TaskEnvelope) by tier:
      LOW  → Fabric direct (CapabilityRequest → CapabilityResult)
      MED  → OrchestratorStub (max 2 Fabric calls)
      HIGH → Orchestrator (future)
  → Back tools: invoke_capability, spawn_via_fabric, execute_workflow
    → IDispatchPort.dispatch_direct(CapabilityRequest)
```

**Current POC equivalent:** `ToolContext.fabric_port` (IFabricPort) + `OrchestratorStub` with 3 inline adapters.

### Port 7: IDeltaPort → events & deltas

```
EMIT: DeltaAggregator.flush() → IDeltaPort.publish(envelope)
      HILCoordinator → IDeltaPort.publish(hitl events)
      MetricsCollector → IDeltaPort.publish(metric events)
      Front/Back actors → IDeltaPort.publish(tool.started, tool.completed, etc.)
      45 envelope builders all route through IDeltaPort
SUBSCRIBE: ConciergeController subscribes to SUBSCRIBED_TOPICS (30+)
           DeadLetterConsumer subscribes to dead-letter topic
```

**Current POC equivalent:** Direct `bus.publish()` calls everywhere. The adapter wraps the bus.

### Port 8: IMemoryPort → K0 recall

```
execute_recall_memory tool → IMemoryPort.recall(query, types, max_results)
  → returns list[dict] (episodic, semantic, procedural memories)
```

**Current POC equivalent:** `recall_fn` closure that keyword-scores seed memories.

---

## 5. WHAT EXISTING CODE MAPS TO PORTS

### 5.1 Already-Existing Port Definitions (in Concierge codebase)

| Existing Port File | Protocol | Used By | Maps To kernel.md Port |
|-------------------|----------|---------|----------------------|
| `k1/concierge/orchestrator/ports.py` → IFabricGatewayPort | Protocol | OrchestratorStub | **Internal** (stays inside IDispatchPort) |
| `k1/concierge/orchestrator/ports.py` → IStateReadPort | Protocol | OrchestratorStub | **Internal** (wraps IStatePort) |
| `k1/concierge/orchestrator/ports.py` → IDeltaEmitPort | Protocol | OrchestratorStub | **Internal** (wraps IDeltaPort) |
| `k1/concierge/llm/ports.py` → IConciergeModelPort | Protocol | GeminiConciergeAdapter, TestAdapter | **Internal** (wraps ILLMPort) |
| `k1/concierge/fabric/ports.py` → IFabricPort | Protocol | Back tools, OrchestratorStub | **Internal** (wraps IDispatchPort) |

**KEY INSIGHT:** These existing ports are **INTERNAL** ports (between Concierge subsystems). The 8 kernel.md ports are **EXTERNAL** ports (between Concierge and the Kernel). The factory wires external→internal.

### 5.2 Port Layer Architecture

```
KERNEL (creates adapters)
  │
  ├── IInputPort ─────────→ ConciergeFactory receives
  ├── IOutputPort ────────→ ConciergeFactory receives
  ├── IClassificationPort → ConciergeFactory receives
  ├── ILLMPort ───────────→ ConciergeFactory receives
  ├── IStatePort ─────────→ ConciergeFactory receives
  ├── IDispatchPort ──────→ ConciergeFactory receives
  ├── IDeltaPort ─────────→ ConciergeFactory receives
  └── IMemoryPort ────────→ ConciergeFactory receives
                              │
                    ┌─────────┴──────────┐
                    │  FACTORY WIRING    │
                    │  (internal only)   │
                    └─────────┬──────────┘
                              │
  INTERNAL SUBSYSTEMS         │
  ├── FSM (ConciergeController)
  │     uses: IDeltaPort (emit), IStatePort (read control section)
  ├── Front Actor
  │     uses: ILLMPort, IStatePort, ToolDispatcher
  ├── Back Actor
  │     uses: ILLMPort, ToolDispatcher
  ├── ToolContext
  │     uses: IStatePort (writer_port), IDispatchPort (fabric_port), IMemoryPort (recall_fn)
  ├── OrchestratorStub
  │     uses: internal IFabricGatewayPort, IStateReadPort, IDeltaEmitPort
  │     (these 3 internal ports are satisfied by adapters wrapping external ports)
  ├── DeltaAggregator → flush → IDeltaPort
  ├── HILCoordinator → emit → IDeltaPort
  ├── WeaveBatcher → emit → IDeltaPort
  ├── ExperienceLayer → reads: IStatePort, emits: IDeltaPort
  ├── DynamicPromptBuilder → reads: IStatePort
  └── MetricsCollector → emit → IDeltaPort
```

---

## 6. PROPOSED BUILD ORDER

### Pre-C1 Gates (ALL COMPLETE)

- [x] Map every file in Concierge (~130 files, ~46K lines)
- [x] Read kernel.md §4.5, §89, Phase 6, CB ownership (7453 lines)
- [x] Read POC .mmd fully (908 lines) — battle-tested design
- [x] Read K1 .mmd fully (1112 lines) — hexagonal redesign
- [x] Cross-reference all 4 sources → 15 gaps identified
- [x] Resolve CRITICAL gaps G-9, G-10 → D-7, D-8
- [x] Lock 12 design decisions (D-1..D-12)
- [x] Create unified .mmd diagram (1335 lines, single source of truth)
- [x] Update whiteboard with gap analysis, invariants, lifecycle, services, streaming, error recovery, CBs

### Phase C1: Port Definitions + Test Adapters

- Create `k1/concierge/ports.py` — 8 Protocol definitions
- Create `k1/concierge/adapters/test_adapters.py` — 8 test adapters
- **0 code changes to existing files**

### Phase C2: Factory Skeleton

- Create `k1/concierge/factory.py` — `ConciergeFactory.create_with_ports()`
- Wires all internal subsystems using the 8 injected ports
- Replaces `start_kernel()` orchestration logic
- Returns a `Concierge` runtime object (like `KernelRuntime` but for Concierge)

### Phase C3: Production Adapters

- Create each adapter file:
  - `model_gateway.py` — wraps IModelHubPort → IConciergeModelPort bridge
  - `session_kernel.py` — wraps SessionStateManager + MutationGuard
  - `fabric_orchestrator.py` — wraps Fabric + Orchestrator, tier routing
  - `delta_bus.py` — wraps Bus for event emit/subscribe
  - `bridge_recall.py` — wraps Bridge client for K0 recall
  - `ws_input.py` — WebSocket input (stub initially)
  - `sse_output.py` — SSE output (stub initially)
  - `ultrabert.py` — UltraBERT adapter (stub initially)

### Phase C4: Bridge from Old to New

- `start_kernel()` calls `ConciergeFactory.create_with_ports()` instead of doing inline wiring
- Old bootstrap becomes a thin wrapper that creates adapters and calls factory
- All 63 existing tests keep passing (adapters provide same interface)

### Phase C5: Kernel Integration

- `k1/kernel/bootstrap.py` Phase 6 calls `ConciergeFactory.create_with_ports()`
- Concierge no longer creates its own Bus/SS/Fabric/ModelHub

---

## 7. OPEN QUESTIONS FOR DISCUSSION

1. **IInputPort vs Mailbox**: ✅ **RESOLVED → D-1** — Higher-level callback-based port. UI calls `send_user_message(text, session_id, metadata)` which enqueues internally. Concierge internally uses `receive()` to dequeue from its own FrontLock priority queue. This gives UI a clean push API while keeping the mailbox/priority machinery entirely internal. The mailbox, FrontLock, and dedup cache all stay inside the factory.
   > **⚠️ G-10 RECONCILIATION**: kernel.md §89 defines `IInputPort.receive() → UserMessage` as the **port protocol method**. The `send_user_message()` is the **adapter's inbound method** (what the WebSocketInputAdapter exposes to infra). The port itself is a pull interface — Concierge calls `receive()` from its consumer loop. Both views are correct at different layers.

2. **IOutputPort vs Bus publish**: ✅ **RESOLVED → D-2** — Dedicated `IOutputPort` with typed event variants.
   > **⚠️ G-9 RECONCILIATION (CRITICAL)**: kernel.md §89 defines `IOutputPort.send(event: OutputEvent) → DeliveryReceipt` as a **single polymorphic method**. D-2's original 3 methods (`send_stream_chunk()`, `send_final()`, `send_progress()`) are **REPLACED** by the kernel.md signature. `OutputEvent` is a union type with variants: `StreamChunkEvent`, `FinalResponseEvent`, `ProgressEvent`, `IntentAckEvent`, `ClarificationEvent`, etc. The adapter discriminates on variant type. This matches the unified diagram's `PORT_OUTPUT` definition.

3. **UltraBERT Phase 1 location**: ✅ **RESOLVED → D-3** — New `IClassificationPort` port. UltraBERT becomes an adapter (`UltraBERTv4Adapter`) behind the port. The `UltraBERTPhase1Pipeline` stays internal to Concierge's FSM layer but calls `classification_port.classify(text)` instead of directly importing UltraBERT. This matches kernel.md Section 4.5 which lists IClassificationPort as one of the 8 ports. Test adapter returns configurable canned classifications.

4. **Config merging**: ✅ **RESOLVED → D-5** — Standalone `ConciergeConfig` (frozen dataclass, section sub-configs, `from_legacy()` bridge, `with_overrides()` for tests).

5. **Consumer loop ownership**: ✅ **RESOLVED → D-4** — Concierge owns `start()` / `stop()` lifecycle. The factory returns a `Concierge` runtime object. Kernel spawns `asyncio.create_task(concierge.start())` which enters the consumer poll loop (front_mailbox + back_mailbox + experience tick). `concierge.stop()` sets a cancellation flag and drains gracefully. This matches the Orchestrator/Planner pattern where factory returns the object and caller spawns it.

6. **BackPool lifecycle**: ✅ **RESOLVED → D-6** — Concierge owns BackPool via registered background tasks pattern. Factory creates `list[AsyncTask]`. `Concierge.start()` spawns all. `Concierge.stop()` cancels all with 30s drain.

---

## 8. MAPPING: bootstrap.py LINE → FACTORY LOCATION

| bootstrap.py function | Lines | Goes to |
|----------------------|-------|---------|
| `start_kernel()` steps 1-5 | ~200 | **DELETED** — kernel provides these via ports |
| `start_kernel()` steps 6-17 | ~400 | **factory.py** `ConciergeFactory.create_with_ports()` |
| `stop_kernel()` | ~80 | **factory.py** `Concierge.stop()` |
| `_mailbox_consumer()` | ~120 | **factory.py** internal — `Concierge.start()` |
| `_tick_experience()` | ~40 | **factory.py** internal — called from consumer loop |
| `_build_experience_context()` | ~30 | Stays in experience layer or factory helper |
| `_create_model()` | ~30 | **DELETED** — kernel injects via ILLMPort |
| `_create_session_state()` | ~20 | **DELETED** — kernel injects via IStatePort |
| `_create_capability_registry()` | ~10 | **DELETED** — kernel injects via IDispatchPort |
| `_create_fabric()` | ~50 | **DELETED** — kernel injects via IDispatchPort |
| `_build_recall_fn()` | ~40 | **DELETED** — kernel injects via IMemoryPort |
| `_build_delta_applicator()` | ~40 | **factory.py** internal — wires IStatePort + IDeltaPort |
| `_FabricGatewayAdapter` | ~30 | **factory.py** internal — wraps IDispatchPort |
| `_StateReadAdapter` | ~20 | **factory.py** internal — wraps IStatePort |
| `_DeltaEmitAdapter` | ~25 | **factory.py** internal — wraps IDeltaPort |
| `KernelConfig` | ~20 | → `ConciergeConfig` (standalone) |
| `KernelRuntime` | ~30 | → `Concierge` runtime class |
| `runner.py` | ~78 | **DELETED** — kernel runner replaces this |

---

## 9. DECISION LOG

| # | Question | Decision | Rationale | Status |
| --- | --- | --- | --- | --- |
| D-1 | IInputPort: mailbox or higher-level? | **Higher-level push API**: `send_user_message(text, session_id, metadata)` for UI; internal `receive()` via FrontLock priority queue | UI gets a clean `send_user_message()` call. Mailbox, FrontLock, dedup cache, priority queue all stay internal. Matches kernel.md "WebSocketInputAdapter" which implies a push-style API, not raw mailbox access. | **DECIDED** |
| D-2 | IOutputPort: dedicated or through IDeltaPort? | **Dedicated port** with `send_stream_chunk()`, `send_final()`, `send_progress()` | UI needs typed output events (stream chunks, final text, progress indicators). IDeltaPort is for internal bus events (tool.started, delta.flush). Mixing them leaks internal topology to UI. SSE/WebSocket/Test adapters each implement IOutputPort differently. | **DECIDED** |
| D-3 | UltraBERT: stays internal or new port? | **New IClassificationPort**. UltraBERT becomes adapter behind it. Phase1Pipeline stays internal, calls through port. | kernel.md Section 4.5 explicitly lists IClassificationPort as one of the 8 ports. Making it a port allows swapping classifiers (UltraBERT v4 → v5, mock for tests) without touching Concierge internals. Test adapter returns configurable canned classifications. | **DECIDED** |
| D-4 | Consumer loop: who owns start/stop? | **Concierge owns `start()`/`stop()`**. Kernel spawns via `asyncio.create_task(concierge.start())`. | Matches Orchestrator/Planner pattern: factory returns object, caller spawns. `start()` enters poll loop (front + back mailboxes + experience tick). `stop()` sets cancellation flag, drains gracefully. Keeps lifecycle ownership inside Concierge. | **DECIDED** |
| D-5 | Config merging | **Standalone `ConciergeConfig`**: frozen dataclass with section-level sub-configs (FSMConfig, LoopBudgetConfig, CBConfig, etc.). Defaults from `defaults.yaml`. `from_legacy(KernelConfig)` bridge for C4. `with_overrides(**kw)` for tests. | Config must be injectable and testable. Frozen = hashable + safe. Sub-configs = each service gets only its section. `from_legacy()` bridges C4 migration. `with_overrides()` avoids test boilerplate. | **DECIDED** |
| D-6 | BackPool lifecycle | **Concierge owns BackPool** via registered background tasks pattern. Factory creates `list[AsyncTask]` (BackPool lease watcher, experience tick, etc.). `Concierge.start()` spawns all. `Concierge.stop()` cancels all with 30s drain. | BackPool is a Concierge-internal concern. Kernel doesn't know about lease watchers. Registered tasks pattern = extensible (add new background work without changing lifecycle code). | **DECIDED** |
| D-7 | IOutputPort signature conflict (G-9) | **kernel.md wins**: `send(event: OutputEvent) → DeliveryReceipt`. D-2's 3 methods replaced by single polymorphic `send()`. `OutputEvent` is a union type with typed variants (StreamChunk, Final, Progress, IntentAck, Clarification, Error). Adapters discriminate on variant. | kernel.md §89 is the canonical contract. A single method with typed events is more extensible (add new event types without changing the port Protocol). Adapter layer handles transport specifics. | **DECIDED** |
| D-8 | IInputPort signature clarification (G-10) | **Two layers**: Port protocol = `receive() → UserMessage` (pull, Concierge consumer loop calls it). Adapter inbound = `send_user_message(text, session_id, metadata)` (push, infra/UI calls it). Both are correct at different layers. | kernel.md §89 defines the port as a pull interface. The adapter's push method is what external callers use. The adapter bridges push→pull via an internal async queue. FrontLock priority queue sits between adapter queue and consumer. | **DECIDED** |
| D-9 | Invariant enforcement strategy | **21 invariants from K1 .mmd are non-negotiable**. Factory MUST validate INV-01..21 at creation time (structural) and runtime (behavioral). Invariants documented in unified diagram Section 19. | Invariants catch architectural drift. INV-01 (single writer), INV-05 (safety first), INV-12 (1 concurrent turn), INV-13 (FSM ≤1ms) are load-bearing. | **DECIDED** |
| D-10 | Circuit breaker ownership | **Concierge owns all 7 CBs** (CB_SSE, CB_MODEL, CB_SESSIONSTATE, CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP). CBs live inside production adapters. kernel.md gotcha: Concierge owns CB_FABRIC and CB_MCP, NOT Orchestrator. | kernel.md lines 1868-1912 explicit. CB inside adapter = adapter controls retry/fallback/degradation. Unified diagram ADAPTERS_PROD section documents CB ownership per adapter. | **DECIDED** |
| D-11 | Lifecycle phases | **6 phases from K1 .mmd**: init, turn_start, turn_end, turn_end_abbreviated, shutdown, crash_recovery. Factory's `Concierge` runtime object exposes these. Lifecycle documented in unified diagram Section 18. | Lifecycle phases are the contract between Concierge and Kernel. init = Phase 6 bootstrap. turn_start/end = per-turn bookkeeping. shutdown/crash_recovery = graceful/ungraceful teardown. | **DECIDED** |
| D-12 | Error recovery severity model | **3 levels**: RECOVERABLE (retry/fallback same phase), DEGRADED (continue with partial), TERMINAL (error response to DELIVERING). Each adapter documents its error paths. Tier degradation cascade: HIGH→MED→LOW→canned. | Error paths MUST be explicit per adapter. "Fail silently" = bugs. Tier degradation is the last-resort safety net. CRISIS response is hardcoded constant with zero deps. | **DECIDED** |
| D-13 | Internal services abstraction (G-3) | **`ConciergeServices` dataclass** (typed registry, no base class). Factory creates all 9 services as named fields: `services.fsm`, `services.turn_processor`, `services.intent_processor`, etc. Injected into actors/tools that need them. | Named fields = IDE autocomplete + type checking. No service locator anti-pattern. No base class overhead. Test can override individual services. | **DECIDED** |
| D-14 | Family Profile: what belongs in profile vs tools vs K0 | **Thin Family Profile**: Only identity core, safety-critical health (allergies/conditions), access levels, device registry, household governance. All operational data (calendar, tasks, chores, medications, budget) lives in M11 MCP tools. All learned data (preferences, routines, relationships, goals) lives in K0 memory (st_sem, st_procedural, st_social). Profile knows WHO. Tools know WHAT. K0 knows WHY/WHEN/HOW. | M11 tools are swappable (local MCP → Google Calendar IFL → Apple Calendar IFL). Baking tool data into profile creates a god-object that breaks when providers swap. K0 memory is auto-learned, not manually entered. Profile is seed data you'd fill on a paper form. | **DECIDED** |
| D-15 | K1 family context hydration model | **Boot-time hydrate, never per-turn K0 calls**. K1 hydrates `HouseholdProjection` at session init from K0 via Bridge (bootstrap sync). K0 pushes deltas via SSE during session. Concierge NEVER calls K0 for family context during a turn. Per-turn: device→member lookup from local cache. Safety gate reads allergies/access from local cache. Tools serve operational data from their own SQLite. | Edge-first (bridge architecture): K1 must be self-sufficient. K0 round-trip adds 50-200ms latency per turn — unacceptable. Offline mode must work. LOCAL COLD tier (SQLite) survives K0 outage. | **DECIDED** |
| D-16 | K0 deep-query pattern | **K0 is for cross-session intelligence, not per-turn data**. K0 invoked via IMemoryPort.recall() when Concierge needs deep patterns: "feeling down for 5 days" → recall st_epi (mood trajectory) + st_procedural (missed gym routine) + st_sem (known coping strategies). This triggers Orchestrator/Planner → multi-agent workflow (health check, mood journal, gentle nudge). K0 is the brain's long-term memory; K1 is working memory. | K0 queries are expensive (embedding search, consolidation layers, multi-table joins). They're for understanding patterns across days/weeks/months — not for "what's Jordan's allergy" which is instant from local profile. Matches bridge architecture: K0 = enhancement layer, K1 = self-sufficient. | **DECIDED** |

---

*This whiteboard will be updated as design decisions are made.*

---

## 10. CROSS-REFERENCE GAP ANALYSIS (15 Gaps)

Sources cross-referenced: kernel.md §4.5/§89/Phase 6, POC .mmd (908 lines), K1 .mmd (1112 lines), actual code audit (~46K lines, ~130 files).

### 10.1 CRITICAL (Must resolve before C1)

| # | Gap | Source | Impact | Resolution |
|---|-----|--------|--------|------------|
| G-9 | **IOutputPort signature mismatch** | kernel.md §89 says `send(OutputEvent) → DeliveryReceipt`. Whiteboard D-2 said `send_stream_chunk()`, `send_final()`, `send_progress()` (3 methods). | Port Protocol definition wrong — breaks all adapters. | **→ D-7**: kernel.md wins. Single polymorphic `send()` with typed `OutputEvent` union variants. |
| G-10 | **IInputPort signature confusion** | kernel.md §89 says `receive() → UserMessage`. D-1 said `send_user_message(text, session_id, metadata)`. | Ambiguity: is the port push or pull? | **→ D-8**: Both correct at different layers. Port = pull (`receive()`). Adapter = push (`send_user_message()`). Adapter bridges push→pull via async queue. |

### 10.2 HIGH (Must address in C1/C2)

| # | Gap | Source | Impact | Resolution |
|---|-----|--------|--------|------------|
| G-1 | **21 Invariants not in whiteboard** | K1 .mmd INVARIANTS section: INV-01..21 across 6 categories (Ownership, Safety, Rate, Timing, Structural, Token). | Factory MUST enforce these — they're non-negotiable. Tests must assert them. | **→ D-9**: All 21 invariants adopted. Structural invariants checked at factory creation. Behavioral invariants enforced at runtime via guards. |
| G-2 | **7 Circuit Breaker ownership unspecified** | K1 .mmd + kernel.md L1868-1912: CB_SSE, CB_MODEL, CB_SESSIONSTATE, CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP. kernel.md gotcha: Concierge owns CB_FABRIC + CB_MCP (NOT Orchestrator). | CBs must live inside production adapters with documented error paths. | **→ D-10**: All 7 CBs owned by Concierge, inside production adapters. |
| G-4 | **6-Phase Lifecycle not in whiteboard** | K1 .mmd LIFECYCLE section: init, turn_start, turn_end, turn_end_abbreviated, shutdown, crash_recovery. | Factory's `Concierge` runtime object needs these as public API. | **→ D-11**: All 6 phases adopted. `Concierge` exposes init/start/stop + turn_start/turn_end lifecycle. |
| G-8 | **Error Recovery Paths unspecified** | K1 .mmd ERROR_RECOVERY: 3 severity levels (RECOVERABLE/DEGRADED/TERMINAL). Each adapter has documented error paths. Tier degradation cascade. 7 canned responses by call_type. | Without explicit error paths, adapters fail silently or crash. | **→ D-12**: 3-level error model adopted. Each adapter documents its error paths. |
| G-15 | **External→internal port bridging undocumented** | Code audit: 5 internal ports (IFabricGatewayPort, IStateReadPort, IDeltaEmitPort, IConciergeModelPort, IFabricPort) bridge to external ports. Bootstrap.py has 3 inline adapters. | Factory must create bridge adapters that wrap external ports → internal ports. | Documented in Section 5.2. Factory creates these bridge adapters internally. |

### 10.3 MEDIUM (Address in C2/C3)

| # | Gap | Source | Impact | Resolution |
|---|-----|--------|--------|------------|
| G-3 | **9 Internal Services abstraction layer** | K1 .mmd SERVICES: FSMController(60t), TurnProcessor(90t), IntentProcessor(110t), ComplexityRouter(45t), ToolDispatcher(80t), OutputManager(55t), DeltaAggregator(50t), ClarificationTracker(40t), ContextAssembler(55t). ~585 tests. | Factory should create these as named services, not inline construction. | Add to factory.py as explicit service creation steps. |
| G-6 | **Performance Baselines missing** | K1 .mmd PERF_BASELINES: System overhead ~32ms/turn. UltraBERT 25ms P99, FSM 1ms, MutationGuard 0.2ms, Output→SSE 5ms, etc. | Tests should assert latency bounds. | Add perf assertions to integration tests in C4/C5. |
| G-7 | **ReactLoopScratchpad (ADR-0098) not in whiteboard** | K1 .mmd SCRATCHPAD: Ephemeral per-loop state (LoopBudget, tool_executions, cognitive_writes, iteration_snapshots). Created at dispatch start, destroyed at dispatch end. Never persisted. | react_loop() needs scratchpad. Factory doesn't create it (per-turn), but LoopBudget config comes from factory. | LoopBudget defaults in ConciergeConfig. Scratchpad created per-turn by TurnProcessor. |

### 10.4 LOW (Address in C3+ or defer)

| # | Gap | Source | Impact | Resolution |
|---|-----|--------|--------|------------|
| G-5 | Streaming infrastructure (8 components, ~150 tests) | K1 .mmd STREAMING section. POC: built into react loop. | Streaming is inside react loop currently. K1 .mmd proposes separate components. | Defer to C3. Current react loop works. Refactor streaming when needed. |
| G-11 | 3 empty directories (empathy/, affective/, rhythm/) | Code audit. | Dead code / future stubs. | Clean up in C5 or leave as-is. |
| G-12 | 3 Experience component stubs (NarrativeWeaver, AnticipatoryResponder, ProactiveAgent) | Code audit. | Stubs return passthrough values. No functional impact. | Leave stubs. Implement when needed. |
| G-13 | BACKGROUND_WORKING state (proposed) | K1 .mmd: only 11 states coded, BACKGROUND_WORKING is proposal. | Needs ADR-0097. Not blocking. | Defer. |
| G-14 | acknowledge_request() handled in actor not ToolDispatcher | Code audit. | Front actor calls ack tool directly. ToolDispatcher dispatches it but doesn't "handle" it. | Correct behavior. No change needed. |

---

## 11. UNIFIED ARCHITECTURE DIAGRAM

**File:** `k1/concierge/concierge_unified.mmd` (1335 lines)

**Merged from:**

- POC `poc/k1_poc/concierge_poc_architecture.mmd` (908 lines) — battle-tested design
- K1 `k1/concierge/concierge.mmd` (1112 lines) — hexagonal redesign

### 11.1 What the Unified Diagram Contains

| Section | Lines (approx) | Source |
|---------|------|--------|
| Header comments (design principles, actor model, FSM, OPP, etc.) | ~95 | Both |
| PORTS (8 hexagonal ports with kernel.md §89 signatures) | ~25 | K1 |
| ADAPTERS (7 production + 8 test, with CB ownership + error paths) | ~65 | K1 |
| FSM (11 states + guard model + FrontLock + FSMTurnState) | ~55 | Both |
| ACKING Core (UltraBERT + safety + complexity + hypothesis + temporal + spatial + uncertainty + OPP-2 + write elision) | ~95 | Both |
| FRONT ACTOR (subscriptions, emissions, 10 tools, react loop) | ~60 | POC |
| BACK ACTOR (subscriptions, emissions, 7 tools, react loop) | ~55 | POC |
| REACT SYSTEM (recovery patterns + scratchpad ADR-0098) | ~45 | Both |
| SESSION STATE (HOT 52KB/WARM 48KB + MutationGuard 3-tier) | ~50 | POC |
| K1 EVENT BUS (core + 30+ topics + causal chain + delta aggregation) | ~75 | POC |
| PROMPT ARCHITECTURE (10 modes + 10 sections + affect + OPP-7 + domains) | ~55 | POC |
| INTERNAL SERVICES (9 components, ~585 tests) | ~15 | K1 |
| PROTOCOLS (HITL 3-variant + Weave + OPP pipeline + Cancel + Suspend) | ~55 | Both |
| EXPERIENCE LAYER (6 components: 3 real + 3 stubs) | ~10 | Both |
| STREAMING (8 components, ~150 tests) | ~15 | K1 |
| TIERS + TASK MODEL (LOW/MED/HIGH paths + OrchestratorStub + degradation) | ~20 | Both |
| CONTEXT ASSEMBLY (OPP-6 compression + trajectory + history) | ~10 | POC |
| SAFETY BANDS (GREEN/AMBER/RED) | ~8 | POC |
| LLM INTERNAL (IConciergeModelPort + model selection + validation) | ~15 | Both |
| LIFECYCLE (6 phases: init through crash_recovery) | ~45 | K1 |
| INVARIANTS (21 rules, 6 categories) | ~25 | K1 |
| PERFORMANCE BASELINES | ~10 | K1 |
| ERROR RECOVERY (3 severity + canned responses) | ~15 | K1 |
| EXTERNAL TOUCHPOINTS (Orchestrator, Planner, Fabric, Model Hub, Bridge, etc.) | ~60 | K1 |
| DATA FLOWS (~120 edges) | ~180 | Both |
| CLASS DEFINITIONS (styling) | ~100 | Both |

### 11.2 Key Reconciliations Applied in Unified Diagram

1. **IOutputPort**: Uses kernel.md §89 `send(OutputEvent) → DeliveryReceipt` (not D-2's 3 methods)
2. **IInputPort**: Uses kernel.md §89 `receive() → UserMessage` (adapter push method is separate layer)
3. **CB Ownership**: Concierge owns CB_FABRIC + CB_MCP per kernel.md L1868-1912
4. **Tool count**: 10 Front + 7 Back = 17 total (code audit confirmed, batch_invoke_capabilities added to Back)
5. **FSM States**: 11 coded + BACKGROUND_WORKING as proposal only
6. **Experience**: 3 real (EP, AM, RC) + 3 stubs (NW, AR, PA) — matches code audit

---

## 12. THINGS WHITEBOARD PREVIOUSLY LACKED (Now Covered)

These architectural elements were in the .mmd diagrams and kernel.md but were not in the original whiteboard. They are now documented in the unified diagram and referenced here for C1-C5 implementation.

### 12.1 Invariants (21 Rules — K1 .mmd)

| Category | Rules | Key Enforcement |
|----------|-------|-----------------|
| Ownership | INV-01..04 | Single Writer (ADR-0017), MutationGuard preflight, Phase 1 before Phase 2, Orch/Planner/Agents NEVER write SS |
| Safety | INV-05..07 | Safety Gate evaluates FIRST, CRISIS bypasses FSM, safety_band written before routing |
| Rate Limits | INV-08..12 | 20 tools/turn, 3 clarification rounds/intent, 50 output queue, 3 workflow depth, 1 concurrent turn |
| Timing | INV-13..14 | FSM transition ≤1ms (no I/O), delta aggregation = 500ms fixed |
| Structural | INV-15..17 | All output through OUTPUT_CHANNEL, internal services call ports never external, single FSM |
| Token Budget | INV-18..21 | 128K context window, 150 tok intent ack, 200 tok prelim ack, 300 tok clarification |

### 12.2 Circuit Breakers (7 — kernel.md + K1 .mmd)

| CB | Owner Adapter | Threshold | On OPEN |
|----|--------------|-----------|---------|
| CB_SSE | SSEOutputAdapter | 5s reconnect, 3/min | Polling mode |
| CB_MODEL | UltraBERTv4Adapter + ModelGatewayAdapter | varies | Heuristic fallback (UltraBERT) / Canned response (LLM) |
| CB_SESSIONSTATE | SessionKernelAdapter | 100ms, 10/min | Stale cached read |
| CB_ORCHESTRATOR | FabricOrchestratorAdapter | 60s, 2/min | Degrade HIGH→MED |
| CB_PLANNER | FabricOrchestratorAdapter | 45s, 2/min | Skip planning |
| CB_FABRIC | FabricOrchestratorAdapter | 30s, 5/min | Tool unavailable (Concierge owns, NOT Orchestrator) |
| CB_MCP | FabricOrchestratorAdapter | 10s, 3/min | Tool offline (Concierge owns, NOT Orchestrator) |

### 12.3 Lifecycle Phases (6 — K1 .mmd)

| Phase | When | Key Actions |
|-------|------|-------------|
| **init** | Session start | Create 9 services, connect 8 ports, restore state, load persona, init 7 CBs, start subscriptions, FSM→LISTENING |
| **turn_start** | User input | Acquire Single Writer lock, increment turn_seq, read HOT snapshot, reset services, allocate tier budget |
| **turn_end** | Normal completion | Flush OutputManager, append history, update telemetry, release lock, checkpoint LOCAL COLD + K0, check experience triggers, emit turn.complete.v1 |
| **turn_end_abbreviated** | Interrupt | Cancel in-flight, flush partial, record INTERRUPTED, release lock, checkpoint LOCAL COLD. SKIP: history, telemetry, K0, experience |
| **shutdown** | Graceful stop | Close IInputPort, wait active turn (30s), flush aggregators, final checkpoint, stop background, disconnect ports LIFO |
| **crash_recovery** | Ungraceful restart | Bootstrap, detect via turn_lock, rollback lock, reconcile outbox, restore from LOCAL COLD, resume. Max loss: 1 turn |

### 12.4 Internal Services (9 — K1 .mmd, ~585 Tests)

| Service | Tests | Responsibility |
|---------|-------|---------------|
| FSMController | ~60 | State transitions, experience ticks, interrupt routing |
| TurnProcessor | ~90 | start_turn(), execute_phase1(), route_dispatch(), execute_phase2(), end_turn() |
| IntentProcessor | ~110 | SafetyGate → Hypothesis → TimeResolver → ContextInference → SanityArbiter → UncertaintyEstimator |
| ComplexityRouter | ~45 | 5-factor scoring: intent_count, domain_count, safety_band, emotion, combined |
| ToolDispatcher | ~80 | dispatch(), get_buffered_results(). Enforces allowlist by state/tier/safety |
| OutputManager | ~55 | enqueue(), deliver_next(), flush(). 9 event types, 3 priority levels |
| DeltaAggregator | ~50 | 500ms window, LWW merge, dedup by section+key |
| ClarificationTracker | ~40 | track_round(), max_reached(), escalate(), INV-09 (3 rounds/intent) |
| ContextAssembler | ~55 | assemble(), track_usage(). CONTEXT_PROFILES, TOKEN_ESTIMATOR |

### 12.5 Streaming Components (8 — K1 .mmd, ~150 Tests)

| Component | Tests | Role |
|-----------|-------|------|
| StreamConsumer | ~25 | Consume AsyncIterator[HubChunk], backpressure, cancel |
| ChunkRouter | ~20 | Route by type: text/tool_call_delta/thinking/error/done |
| TextChunkAggregator | ~15 | Flush at word boundaries, ~5 tokens/SSE |
| ToolCallStreamHandler | ~25 | Accumulate JSON fragments, parse on complete |
| ThinkingTraceHandler | ~15 | Capture REASON capability traces |
| StreamingSSEEmitter | ~20 | Wrap chunks → OutputEvent → OutputManager REALTIME |
| StreamCancellationGuard | ~15 | User interrupts mid-stream |
| PartialResponseBuffer | ~15 | Buffer partial text for FSM state transitions |

### 12.6 Error Recovery Model (K1 .mmd)

| Severity | Behavior | Examples |
|----------|----------|----------|
| **RECOVERABLE** | Retry/fallback in same phase | MutationGuard reject → skip write. Delta emit fail → log + skip. Memory timeout → skip memory. |
| **DEGRADED** | Continue with partial results | LLM CB OPEN → canned response. SS read timeout → stale cache. Tier degradation → lower tier. |
| **TERMINAL** | Error response to DELIVERING | 3 consecutive LLM failures. All degradation exhausted. |

**Tier Degradation Cascade:** HIGH (CB_PLANNER open) → MEDIUM (CB_ORCH open) → LOW (CB_FABRIC open) → Canned response

**Canned Responses (7):** ack, prelim_ack, clarify, LOW, MED, HIGH + CRISIS (hardcoded constant, zero deps)

---

## 13. FAMILY SELF-MODEL & DATA OWNERSHIP (D-14, D-15, D-16)

### 13.1 Separation Principle

> **Profile knows WHO. Tools know WHAT. K0 knows WHY/WHEN/HOW.**

Data in FamilyOS falls into exactly three ownership categories. Mixing them creates a god-object that breaks when tools swap or memories evolve.

| Category | Owner | Storage | Changes | Swappable? |
|----------|-------|---------|---------|------------|
| **Identity & Safety** | Family Profile | K1 local (hydrated from K0 at boot) | Rarely (onboarding + manual) | No — core contract |
| **Operational Data** | M11 MCP Tools (44 contracts) | Per-tool SQLite (local, provider-swappable) | Daily | Yes — local MCP → IFL (Google/Apple/etc.) |
| **Learned Knowledge** | K0 Memory Layers | K0 PostgreSQL (st_sem, st_epi, st_procedural, st_social, st_kg) | Continuously (auto-consolidated) | No — canonical long-term memory |
| **Session Persona** | K1 PersonaSection (.fbs) | SessionState WARM tier | Per-session calibration | No — already exists |

### 13.2 Thin Family Profile Contract (D-14)

The profile contains ONLY what no tool owns and no memory layer learns. This is seed data — what you'd fill on a paper enrollment form.

```
FAMILY PROFILE SCHEMA
=====================

PER MEMBER (MemberProfile):
  Identity Core:
    - member_id: str          # stable UUID, maps to K0 actor_id
    - display_name: str       # "Alex"
    - nicknames: list[str]    # ["Al", "Dad"]
    - date_of_birth: str      # ISO 8601
    - gender: str             # freeform
    - pronouns: str           # "he/him", "she/her", "they/them"
    - role_in_family: str     # "parent", "child", "grandparent", "caretaker"
    - languages: list[str]    # ["en", "es"]
    - photo_ref: str | None   # for device/face identification

  Safety-Critical Health (available WITHOUT querying any tool or K0):
    - allergies: list[Allergy]
        - substance: str      # "shellfish", "penicillin", "pollen"
        - category: str       # "food", "drug", "environmental"
        - severity: str       # "life_threatening", "serious", "mild"
    - chronic_conditions: list[str]  # "hypertension", "asthma", "diabetes"
    - blood_type: str | None
    - emergency_contact: str | None  # if not another member

  Access & Interface:
    - access_level: str       # "full_adult", "supervised", "child", "limited", "guest"
    - interface_preference: str  # "standard", "simplified", "voice_first"
    - content_filtering: str  # "none", "moderate", "strict"
    - notification_tolerance: str  # "frequent", "normal", "minimal", "dnd_heavy"

  Locale:
    - timezone: str           # "America/Chicago"
    - preferred_language: str  # "en"

PER DEVICE (DeviceRegistration):
    - device_id: str          # maps to K0 device_id
    - owner_member_id: str    # who owns this device
    - device_type: str        # "iPhone", "iPad", "Hub"
    - label: str              # "Alex's phone (primary)"
    - access_level_override: str | None  # device-level override
    - is_shared: bool         # kitchen_hub = True

PER HOUSEHOLD (HouseholdProfile):
    - household_id: str       # maps to K0 tenant_id + space_id
    - family_name: str
    - address: str
    - timezone: str           # household default
    - governance:
        - screen_time_rules: dict[str, Any]  # per role/member
        - quiet_hours: str | None  # "22:00-07:00"
        - content_policies: dict[str, str]  # per access_level
        - financial_authority: list[str]  # member_ids who can authorize spending
        - data_sharing_policy: str  # "family_only", "extended", etc.
```

### 13.3 What Does NOT Belong in Profile (and Where It Lives)

| Data | NOT Profile Because | Actual Owner |
|------|-------------------|--------------|
| Medication schedules (name, dose, time) | Tool data; swappable to pharmacy app via IFL | **Health MCP** (E11.9) |
| Appointments, doctor info | Tool data | **Health MCP** (E11.9) |
| Calendar events, school schedule | Tool data; swappable to Google/Apple Calendar | **Calendar MCP** (E11.1), **School MCP** (E11.8) |
| Tasks, grocery lists | Tool data | **Tasks MCP** (E11.2) |
| Chores, streaks, points | Tool data | **Chores MCP** (E11.5) |
| Budget, allowance | Tool data; swappable to Mint/YNAB via IFL | **Budget MCP** (E11.7) |
| Carpool, pickup schedule | Tool data | **Transport MCP** (E11.10) |
| Reminders, timers | Tool data | **Reminders MCP** (E11.4) |
| Meal plans | Tool data | **Recipes MCP** (E11.6) |
| Favorite foods, hated foods | Learned from conversations | **K0 st_sem** (semantic memory) |
| Comfort foods, coffee preference | Learned from conversations | **K0 st_sem** |
| Morning/evening routines | Auto-detected patterns | **K0 st_procedural** (RoutineDetector) |
| Exercise routine, sleep patterns | Auto-detected patterns | **K0 st_procedural** |
| Music/movie/book preferences | Learned | **K0 st_sem** |
| Communication style, humor | Per-session calibration | **K1 PersonaSection** (.fbs) |
| Relationships, social dynamics | Auto-learned from episodes | **K0 st_social** (M07 family_graph_resolve) |
| Goals, aspirations | Expressed in conversations | **K0 st_sem** |
| Friends, extended family | Auto-learned | **K0 st_social + st_kg_edges** |
| Stress response, love language | Learned patterns | **K0 st_sem** |

### 13.4 K1 Hydration Model (D-15) — Boot-Time Sync, Never Per-Turn

```
SESSION BOOT (Kernel Phase 6 → Concierge init):
  ┌───────────────────────────────────────────────────────────┐
  │  1. Bridge.query(HouseholdProjection)                     │
  │     → K0 responds with versioned snapshot                 │
  │     → Members, devices, governance, allergies             │
  │     → Stored in K1 LOCAL COLD (SQLite)                    │
  │     → Cached in-memory as frozen HouseholdProjection      │
  │                                                           │
  │  2. If K0 unreachable (offline):                          │
  │     → Load from LOCAL COLD (last known good)              │
  │     → Flag: projection_stale = True                       │
  │     → Concierge works fine (edge-first)                   │
  │                                                           │
  │  3. Bridge.subscribe(household.delta.v1)                  │
  │     → K0 pushes member/device/governance changes via SSE  │
  │     → K1 applies deltas to local cache + LOCAL COLD       │
  │     → projection_version increments                       │
  └───────────────────────────────────────────────────────────┘

PER-TURN (fast, local only):
  ┌───────────────────────────────────────────────────────────┐
  │  turn_start:                                              │
  │    device_id (from WebSocket)                             │
  │      → local cache: device_registry[device_id]            │
  │      → member_id resolved (0ms, in-memory)                │
  │      → access_level → safety gate (0ms, in-memory)        │
  │      → allergies → safety context (0ms, in-memory)        │
  │                                                           │
  │  during turn (on-demand, tools serve themselves):         │
  │    "What's for dinner?"                                   │
  │      → Recipes MCP (meal plan from tool's SQLite)         │
  │      → profile.allergies (safety filter from cache)       │
  │      → K0 recall: st_sem food prefs (ONLY IF NEEDED)     │
  │                                                           │
  │  NEVER per-turn:                                          │
  │    ✗ Bridge.query(anything)                               │
  │    ✗ K0 round-trip for family context                     │
  │    ✗ Full HouseholdProjection reload                      │
  └───────────────────────────────────────────────────────────┘
```

### 13.5 K0 Deep-Query Pattern (D-16) — Cross-Session Intelligence

K0 is NOT for per-turn lookups. K0 is invoked via `IMemoryPort.recall()` when Concierge needs **deep cross-session patterns** that no single tool or profile field can answer.

**Example: "I've been feeling down for 5 days, can't concentrate, haven't gone to gym"**

```
CONCIERGE recognizes: multi-day pattern, health concern, behavioral change
  │
  ├─ Step 1: IMemoryPort.recall("mood trajectory last 7 days")
  │    → K0 st_epi: 5 recent episodes with negative affect_valence
  │    → K0 st_procedural: gym routine showing DECAYING lifecycle
  │    → K0 st_sem: known coping strategies ("journaling helps", "call Mom")
  │
  ├─ Step 2: ComplexityRouter scores HIGH (health + behavioral + multi-day)
  │    → Orchestrator dispatches to Planner
  │
  ├─ Step 3: Planner creates multi-agent workflow:
  │    ├─ Health Agent: "Any missed medications? Sleep pattern changes?"
  │    │    → Health MCP: medication_due(), check adherence
  │    │    → K0 recall: sleep routine regularity
  │    ├─ Wellness Agent: "Journaling prompt, gentle gym nudge"
  │    │    → K0 recall: what helped last time (st_sem)
  │    │    → Reminders MCP: create gentle reminder
  │    └─ Social Agent: "Should we suggest calling Mom?"
  │         → K0 st_social: relationship strength with "Mom"
  │         → K0 st_epi: last call with Mom (recency)
  │
  └─ Step 4: Concierge synthesizes: empathetic response + actionable suggestions
       → NOT "here's a list of things" but natural conversation
       → Respects PersonaSection communication style
       → Safety band: AMBER (monitors but doesn't escalate unless CRISIS)
```

**When K0 IS invoked (via IMemoryPort):**

| Trigger | K0 Query | What It Returns |
|---------|----------|-----------------|
| Multi-day mood pattern | `recall(mood, last_7d)` | Affect trajectory from st_epi |
| "Remember when we..." | `recall(event, semantic)` | Episodic + semantic matches |
| Behavioral change detected | `recall(routine, member)` | st_procedural lifecycle state |
| Relationship question | `recall(person, social)` | st_social relationship strength |
| Gift suggestion | `recall(preferences, member)` | st_sem learned preferences |
| Health concern escalation | `recall(health, patterns)` | Cross-session health signals |

**When K0 is NOT invoked:**

| Request | Served By | Why Not K0 |
|---------|-----------|------------|
| "What's Jordan's allergy?" | Profile (local cache, 0ms) | Safety-critical, always in memory |
| "What's on the calendar today?" | Calendar MCP (local SQLite) | Tool data, instant |
| "Add milk to grocery list" | Tasks MCP (local SQLite) | Tool data, instant |
| "Who's picking up Riley?" | Transport MCP (local SQLite) | Tool data, instant |
| "Remind Nana about medicine at 9" | Reminders + Health MCP | Tool data, instant |
| "How much allowance does Riley have?" | Budget MCP (local SQLite) | Tool data, instant |

### 13.6 Progressive Fill Pattern

The family profile is NOT filled on day one. It fills in layers:

```
ONBOARDING (Day 1):
  → Name, role, age for each member          (manual, required)
  → Allergies with severity                   (manual, safety-critical)
  → Device registration                       (auto from first connection)
  → Access levels                             (manual, parent sets)
  → Timezone, language                        (auto from device)

WEEK 1 (auto-learned → K0):
  → Routines emerge from conversation         (K0 st_procedural)
  → Food preferences from meal discussions    (K0 st_sem)
  → Relationship dynamics from mentions       (K0 st_social)

MONTH 1 (auto-learned → K0):
  → Entertainment preferences                 (K0 st_sem)
  → Stress patterns, comfort strategies       (K0 st_sem)
  → Communication style calibration           (K1 PersonaSection)

ONGOING (tools accumulate):
  → Calendar fills with events                (Calendar MCP)
  → Health records accumulate                 (Health MCP)
  → Budget history grows                      (Budget MCP)
  → Chore streaks and patterns emerge         (Chores MCP)
```

### 13.7 Tool Swappability (Why Profile Must Stay Thin)

M11 tools use `provider_type: MCP` (local SQLite) today. The **contract YAML stays the same** when providers swap:

```
TODAY:    tool.write.calendar_create_event → CalendarMCPServer (local SQLite)
FUTURE:   tool.write.calendar_create_event → GoogleCalendarIFLAdapter (Google API)
          tool.write.calendar_create_event → AppleCalendarIFLAdapter (iCloud API)

TODAY:    tool.write.health_add_medication → HealthMCPServer (local SQLite)
FUTURE:   tool.write.health_add_medication → MyChartIFLAdapter (Epic API)

TODAY:    tool.write.budget_add_transaction → BudgetMCPServer (local SQLite)
FUTURE:   tool.write.budget_add_transaction → YNABIFLAdapter (YNAB API)
```

Fabric's `AutoDiscoveryMCPTransport` handles discovery. If tool data were baked into the profile, swapping providers would mean migrating profile data — architectural violation.

---

## 14. UPDATED STATUS

**Status:** END-TO-END AUDIT COMPLETE — ALL 7 COMPONENTS AUDITED — 3 WORK STREAMS IDENTIFIED — MILESTONES/EPICS/ISSUES DEFINED

**Decisions locked:** D-1..D-16 (0 open)

**Open questions:** 0 (all resolved)

**Next step:** MS-1 / Epic E-1.1 / Issue I-1.1.1 — Create `k1/concierge/ports.py`

---

## 15. END-TO-END PRODUCTION KERNEL AUDIT (2026-04-02)

### 15.1 Audit Scope

Full readiness audit of all 7 K1 components + kernel bootstrap to answer: **What remains to boot a production kernel end-to-end?**

### 15.2 Component Readiness Matrix

| # | Component | Factory | Ports | Prod Adapters | Tests | Stubs in Prod | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **Bus** | `BusFactory` (4 methods) | 2 (`IBus`, `IMailboxRouter`) | 2 (`fabric_adapter`, `session_adapter`) | 22 files | 0 | ✅ PRODUCTION READY |
| 2 | **SessionState** | `SessionStateFactory` (3 methods incl. `create_with_ports`) | 5 | 5 (SQLite, Bus, DirectWriter, Lifecycle, NullSync) | 73 files | 0 | ✅ PRODUCTION READY |
| 3 | **Fabric** | `FabricFactory` (`create_with_ports`) | 6 | 5 | 4,595 tests | 0 | ✅ PRODUCTION READY |
| 4 | **ModelHub** | `ModelHubFactory` (3 methods) | 7 | 7 | 958 tests | 0 (7 empty adapter test files) | ✅ PRODUCTION READY |
| 5 | **Orchestrator** | `OrchestratorFactory` (`create_production`) | 9 | 9 + 4 mock | 1,914 tests | 2 M4 TODOs | ✅ PRODUCTION READY |
| 6 | **Planner** | `PlannerFactory` (`create_production`) | 7 | 7 | 1,923 tests | 0 (7 empty adapter test files) | ✅ PRODUCTION READY |
| 7 | **Concierge** | ❌ No factory | ❌ No centralized ports | ❌ 3 scattered + 3 inline | 63 files | POC monolith | ❌ NEEDS WORK |
| — | **Kernel Bootstrap** | N/A | N/A | N/A | 0 | All `pass` bodies | ❌ NEEDS WORK |

**Total existing tests across components 1-6: ~9,485. Total production stubs: 0.**

### 15.3 Concierge Internals — Already Production-Grade

The Concierge's **inside** is rich (~46K lines, ~130 files). These stay untouched:

| Subsystem | Key File | Status |
|---|---|---|
| FSM | `fsm/controller.py` — `ConciergeController` with state machine, interrupts, Phase 1 | ✅ Rich |
| Actors | `actors/front.py` + `back.py` — Front/Back handlers, ReAct loops, affect bands | ✅ Rich |
| Tools | `tools/dispatcher.py` — `ToolDispatcher` with 6-step validation pipeline | ✅ Rich |
| Experience | `experience/layer.py` — `ExperienceLayer` with 6 sub-processors | ✅ Rich |
| Delta | `delta/aggregator.py` + `applicator.py` — batch windows, causal ordering | ✅ Rich |
| Protocols | `protocols/hitl_coordinator.py`, `weave_batcher.py`, `opp_pipeline.py` + 15 files | ✅ Rich |
| Prompt | `prompt/builder.py` — `DynamicPromptBuilder`, mode-driven assembly | ✅ Rich |
| Tests | 63 test files spanning M00–M15 | ✅ Rich |
| Tech Debt | 4 M8-cleanup TODOs in `actors/back.py` + `react/loop.py` | Negligible |

### 15.4 Existing Concierge Ports (Scattered, Not Centralized)

| File | Ports Defined | Notes |
|---|---|---|
| `llm/ports.py` | `IConciergeModelPort` (1) | LLM only: `generate()`, `generate_stream()` |
| `orchestrator/ports.py` | `IFabricGatewayPort`, `IStateReadPort`, `IDeltaEmitPort` + 6 HIGH-tier deferred (9 total) | Internal ports for OrchestratorStub |
| `fabric/ports.py` | `IFabricPort` (1) | `execute()`, `execute_batch()`, `discover_capabilities()` |

**Missing from hexagonal boundary:** `IInputPort`, `IOutputPort`, `IClassificationPort`, `IMemoryPort`. Existing ports are domain-scoped, not hexagonal boundary ports.

### 15.5 Existing Concierge Adapters (Scattered, Not Factory-Managed)

| File | What It Does | Reusable? |
|---|---|---|
| `llm/gemini_adapter.py` | `GeminiConciergeAdapter` → `IConciergeModelPort` | ✅ Wrap into `model_gateway.py` |
| `llm/test_adapter.py` | `TestConciergeAdapter` → `IConciergeModelPort` | ✅ Move into `test_adapters.py` |
| `llm/model_hub_bridge.py` | `ModelHubPOCBridge` → bridges to ModelHub | ✅ Wrap into `model_gateway.py` |
| `fsm/ultrabert_adapter.py` | UltraBERT v4 classifier | ✅ Wrap into `ultrabert.py` |
| `fabric/poc_bridge_adapter.py` | POC Fabric bridge | ✅ Wrap into `fabric_orchestrator.py` |
| `kernel/bootstrap.py` (inline) | `_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter` | ✅ Extract into proper adapters |

### 15.6 Kernel Bootstrap — Code vs Spec Gap

The spec (kernel.md) describes an 8-phase bootstrap. The `k1/kernel/` directory is skeletal:

| File | Content |
|---|---|
| `k1/kernel/loader.py` | `ModuleLoader` — all methods `pass` |
| `k1/kernel/hot_reload.py` | `HotReloadEngine` — all methods `pass` |
| `k1/kernel/registries/` | Empty `agent_registry.py`, `prompt_registry.py`, `tool_registry.py` |

The **actual running kernel** is `k1/concierge/kernel/bootstrap.py` — a Concierge-era POC monolith that:

1. Delegates bus creation to `poc.k1_poc.main.boot()` instead of `BusFactory`
2. Uses `SessionStateFactory.create_standalone()` instead of full port injection
3. Passes **test adapters** to Fabric (not real bus-wired)
4. Skips ModelHub factory (uses POC `GeminiAdapter` wrapper)
5. Uses `OrchestratorStub` instead of `OrchestratorFactory.create_production()`
6. Has **no Planner** at all
7. Has **no Bridge client**, **no HouseholdProjection hydration**
8. Has **no ConciergeFactory** — all Concierge internals wired inline

| Kernel.md Phase | Factory Needed | Factory Exists? | Called in Bootstrap? |
|---|---|---|---|
| Phase 1: Config | `ConfigLoader` | Skeleton (`pass`) | ❌ |
| Phase 2: Bus | `BusFactory` | ✅ Ready | ❌ (uses `poc.k1_poc`) |
| Phase 3: SessionState | `SessionStateFactory` | ✅ Ready | Partial (`create_standalone()`) |
| Phase 4: Fabric + ModelHub | `FabricFactory` + `ModelHubFactory` | ✅ Both ready | Partial (test adapters) |
| Phase 5: Orch + Planner | `OrchestratorFactory` + `PlannerFactory` | ✅ Both ready | ❌ (uses `OrchestratorStub`) |
| Phase 5.5: Bridge | `BridgeClient` | ❌ Not written | ❌ |
| Phase 6: Concierge | `ConciergeFactory` | ❌ Not written | ❌ |
| Phase 6.5: Hydration | `HouseholdProjection` | ❌ Not written | ❌ |
| Phase 7: Cross-wire | Planner↔Orch hot-swap | ❌ Not written | ❌ |
| Phase 8: KernelRuntime | Assembly | Partial (incomplete dataclass) | Partial |

### 15.7 Three Work Streams

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                      WHAT'S LEFT TO BOOT PRODUCTION KERNEL                     │
│                                                                                │
│  WS-1: CONCIERGE HEXAGONAL SHELL                                              │
│  ├── C1: k1/concierge/ports.py (8 Protocol definitions)                       │
│  ├── C2: k1/concierge/factory.py (ConciergeFactory.create_with_ports)         │
│  └── C3: k1/concierge/adapters/ (8 prod adapters + test bundle)               │
│                                                                                │
│  WS-2: CENTRAL KERNEL BOOTSTRAP                                               │
│  ├── k1/kernel/bootstrap.py (8-phase production bootstrap)                    │
│  ├── k1/kernel/loader.py (real config loader)                                 │
│  └── k1/kernel/runtime.py (KernelRuntime dataclass)                           │
│                                                                                │
│  WS-3: BRIDGE CLIENT + HOUSEHOLD PROJECTION                                   │
│  ├── Bridge client interface + stub impl                                      │
│  ├── HouseholdProjection dataclass + hydration logic                          │
│  └── bridge_recall.py adapter (part of WS-1/C3 but depends on BridgeClient)  │
│                                                                                │
│  DEPENDENCY GRAPH:                                                             │
│                                                                                │
│    WS-1/C1 (ports) ──────────┐                                                │
│                               ├──► WS-1/C3 (adapters) ──► WS-1/C2 (factory)  │
│    WS-3 (BridgeClient) ──────┘         │                         │            │
│                                        │                         │            │
│                                        └──► WS-2 (kernel bootstrap) ◄────────┘│
│                                                                                │
│  TOTAL NEW CODE: ~2,050 lines across ~15 files                                │
│  EXISTING CODE CHANGED: 0 (all new files)                                     │
│  RISK: LOW (wrapping tested components, not rewriting them)                   │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 15.8 Adapter Build Strategy (C3 Detail)

| Adapter File | Port | Existing Code to Wrap | Build Type |
|---|---|---|---|
| `ws_input.py` | `IInputPort` | New WebSocket ingress | **NEW** |
| `sse_output.py` | `IOutputPort` | New SSE egress | **NEW** |
| `ultrabert.py` | `IClassificationPort` | `fsm/ultrabert_adapter.py` exists | **WRAP** existing |
| `model_gateway.py` | `ILLMPort` | `llm/gemini_adapter.py` + `llm/model_hub_bridge.py` | **WRAP** existing |
| `session_kernel.py` | `IStatePort` | `SessionStateFactory` returns full manager | **WRAP** existing |
| `fabric_orchestrator.py` | `IDispatchPort` | `OrchestratorFactory` + `FabricFactory` | **WRAP** existing |
| `delta_bus.py` | `IDeltaPort` | Bus production-ready + `delta/emitters.py` | **WRAP** existing |
| `bridge_recall.py` | `IMemoryPort` | New `BridgeClient` (WS-3) | **NEW** (depends WS-3) |
| `test_adapters.py` | All 8 | `llm/test_adapter.py` partial | **NEW** (test bundle) |

**3 truly new, 5 wrapping existing code, 1 test bundle.**

---

## 16. MILESTONE, EPIC & ISSUE BREAKDOWN

### 16.1 Overview

3 Milestones → 8 Epics → 33 Issues

```
MS-1: Concierge Hexagonal Shell          (WS-1: C1→C3)    ~950 lines
MS-2: Bridge Client & Household          (WS-3)           ~400 lines
MS-3: Central Kernel Bootstrap           (WS-2)           ~700 lines
                                                    TOTAL: ~2,050 lines
```

---

### 16.2 MS-1: CONCIERGE HEXAGONAL SHELL

> **Goal:** Extract the hexagonal boundary around the Concierge monolith — ports, factory, production adapters. Zero changes to existing internal code.
>
> **Depends on:** Nothing (can start immediately)
>
> **Blocks:** MS-3 (kernel bootstrap needs ConciergeFactory)

#### Epic E-1.1: Port Definitions (C1)

> Define the 8 hexagonal Protocol classes that form the Concierge's external contract.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-1.1.1** | Define `IInputPort` and `IOutputPort` Protocols | I/O boundary ports. `IInputPort.receive() → UserMessage`. `IOutputPort.send(OutputEvent) → DeliveryReceipt`. Include `OutputEvent` union type with variants: `StreamChunkEvent`, `FinalResponseEvent`, `ProgressEvent`, `IntentAckEvent`, `ClarificationEvent`, `ErrorEvent`. | `k1/concierge/ports.py` (start) | ~60 |
| **I-1.1.2** | Define `IClassificationPort` and `ILLMPort` Protocols | `IClassificationPort.classify(text) → ClassificationResult`. `ILLMPort.generate(prompt, config) → str`, `generate_stream(prompt, config) → AsyncIterator[str]`. | `k1/concierge/ports.py` (append) | ~30 |
| **I-1.1.3** | Define `IStatePort`, `IDispatchPort`, `IDeltaPort`, `IMemoryPort` Protocols | `IStatePort.read_section(name) → bytes`, `write_section(name, data)`. `IDispatchPort.dispatch(envelope) → DispatchResult`. `IDeltaPort.emit(delta) → None`, `flush() → FlushReceipt`. `IMemoryPort.recall(query, scope) → RecallResult`. | `k1/concierge/ports.py` (append) | ~60 |
| **I-1.1.4** | Add port validation helpers + `__all__` export | `validate_ports(ports: dict) → None` that runtime-checks all 8 are provided and satisfy `isinstance`. Export list. Docstrings with kernel.md section references. | `k1/concierge/ports.py` (finalize) | ~30 |

**Epic total: ~180 lines in 1 file. 4 issues.**

---

#### Epic E-1.2: Test Adapters

> In-memory test implementations of all 8 ports for unit testing without real infrastructure.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-1.2.1** | Create test adapters for `IInputPort`, `IOutputPort`, `IClassificationPort`, `ILLMPort` | `InMemoryInputAdapter` (async queue, push/pull). `InMemoryOutputAdapter` (captures events in list). `StubClassificationAdapter` (configurable canned result). `StubLLMAdapter` (configurable response, optional delay). | `k1/concierge/adapters/__init__.py`, `k1/concierge/adapters/test_adapters.py` (start) | ~120 |
| **I-1.2.2** | Create test adapters for `IStatePort`, `IDispatchPort`, `IDeltaPort`, `IMemoryPort` | `InMemoryStateAdapter` (dict-backed sections). `StubDispatchAdapter` (configurable result). `InMemoryDeltaAdapter` (captures emitted deltas). `StubMemoryAdapter` (configurable recall results). | `k1/concierge/adapters/test_adapters.py` (append) | ~100 |
| **I-1.2.3** | Create `test_adapters_conformance.py` — port compliance tests | Parametrized tests that verify every test adapter satisfies its Protocol. `isinstance()` checks + behavioral smoke tests (push→receive, emit→captured, etc.). | `tests/k1/concierge/test_adapters_conformance.py` | ~80 |

**Epic total: ~300 lines across 3 files. 3 issues.**

---

#### Epic E-1.3: Production Adapters (C3)

> Real adapters that wrap existing production components behind the 8 port Protocols.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-1.3.1** | Create `ws_input.py` — WebSocket → `IInputPort` | `WebSocketInputAdapter`: accepts `send_user_message(text, session_id, metadata)` push from infra, bridges to internal `receive()` via async queue. FrontLock-compatible. | `k1/concierge/adapters/ws_input.py` | ~60 |
| **I-1.3.2** | Create `sse_output.py` — `IOutputPort` → SSE | `SSEOutputAdapter`: `send(OutputEvent)` discriminates on variant type, serializes to SSE format, delivers via connection. `DeliveryReceipt` with ack tracking. CB_SSE per D-10. | `k1/concierge/adapters/sse_output.py` | ~70 |
| **I-1.3.3** | Create `ultrabert.py` — `IClassificationPort` adapter | `UltraBERTv4Adapter`: wraps existing `fsm/ultrabert_adapter.py` logic behind `IClassificationPort.classify()`. Maps UltraBERT output → `ClassificationResult`. | `k1/concierge/adapters/ultrabert.py` | ~40 |
| **I-1.3.4** | Create `model_gateway.py` — `ILLMPort` adapter | `ModelGatewayAdapter`: wraps `ModelHubFactory.create_standalone()` or `GeminiConciergeAdapter` behind `ILLMPort`. `generate()` + `generate_stream()`. CB_MODEL per D-10. | `k1/concierge/adapters/model_gateway.py` | ~50 |
| **I-1.3.5** | Create `session_kernel.py` — `IStatePort` adapter | `SessionKernelAdapter`: wraps `SessionStateManager` behind `IStatePort`. `read_section()` → FlatBuffer decode. `write_section()` → MutationGuard + FlatBuffer encode. CB_SESSIONSTATE per D-10. | `k1/concierge/adapters/session_kernel.py` | ~60 |
| **I-1.3.6** | Create `fabric_orchestrator.py` — `IDispatchPort` adapter | `FabricOrchestratorAdapter`: wraps `OrchestratorFactory.create_production()` + `FabricFactory.create_with_ports()` behind `IDispatchPort.dispatch()`. Tier routing (SIMPLE→Fabric, COMPLEX→Orchestrator→Planner). CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC per D-10. | `k1/concierge/adapters/fabric_orchestrator.py` | ~80 |
| **I-1.3.7** | Create `delta_bus.py` — `IDeltaPort` adapter | `DeltaBusAdapter`: wraps `IBus.publish()` behind `IDeltaPort.emit()` and `flush()`. Batch window passthrough to `DeltaAggregator`. Topic mapping from delta types to bus topics. | `k1/concierge/adapters/delta_bus.py` | ~50 |

**Epic total: ~410 lines across 7 files. 7 issues.**

> **Note:** `bridge_recall.py` (`IMemoryPort` adapter) is in MS-2/E-2.2 because it depends on `BridgeClient`.

---

#### Epic E-1.4: Concierge Factory (C2)

> The `ConciergeFactory.create_with_ports()` that replaces the `start_kernel()` monolith.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-1.4.1** | Create `ConciergeFactory` skeleton with port validation | `ConciergeFactory` class with `create_with_ports(ports: dict[str, Any], config: ConciergeConfig) → Concierge`. Validates 8 ports via `validate_ports()`. Creates `ConciergeConfig` (D-5). Returns `Concierge` runtime object with `start()` / `stop()` lifecycle (D-4). | `k1/concierge/factory.py` (start) | ~80 |
| **I-1.4.2** | Wire internal subsystems inside factory | Factory creates: FSM (`ConciergeController`), Actors (front/back handlers), Tools (`ToolDispatcher`), Experience (`ExperienceLayer`), Delta (`DeltaAggregator`+`DeltaApplicator`), Protocols (HITL, Weave, OPP), Prompt (`DynamicPromptBuilder`), BackPool, DeadLetterConsumer. All internal — mirrors `start_kernel()` steps 6-17. | `k1/concierge/factory.py` (append) | ~120 |
| **I-1.4.3** | Add `ConciergeConfig` dataclass + `from_legacy()` bridge | Frozen dataclass with section-level sub-configs: `FSMConfig`, `LoopBudgetConfig`, `CBConfig`, `ExperienceConfig`, `DeltaConfig`. `from_legacy(KernelConfig)` for C4 bridge. `with_overrides(**kw)` for tests. Defaults from `defaults.yaml`. | `k1/concierge/config.py` | ~60 |
| **I-1.4.4** | Integration test: factory + test adapters → Concierge boots | Create `Concierge` via factory with all 8 test adapters. Verify `start()` runs, send a message via `IInputPort`, receive output via `IOutputPort`, verify FSM transitions. `stop()` cleanly. | `tests/k1/concierge/test_factory_integration.py` | ~100 |

**Epic total: ~360 lines across 3-4 files. 4 issues.**

---

### 16.3 MS-2: BRIDGE CLIENT & HOUSEHOLD PROJECTION

> **Goal:** Implement the K1→K0 bridge connectivity layer and household hydration protocol (kernel.md §126, Phase 5.5, Phase 6.5).
>
> **Depends on:** Nothing for interface (can start parallel with MS-1). `bridge_recall.py` adapter depends on E-2.1.
>
> **Blocks:** MS-3 Phase 5.5 + Phase 6.5

#### Epic E-2.1: Bridge Client

> K1→K0 connector for identity/memory queries and delta subscriptions.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-2.1.1** | Define `IBridgeClient` Protocol + `BridgeQuery`/`BridgeResult` types | `IBridgeClient` Protocol: `connect()`, `disconnect()`, `query(schema_id) → BridgeResult`, `subscribe(topic) → AsyncIterator[BridgeDelta]`. Typed query/result envelopes. | `k1/bridge/connector/ports.py` | ~60 |
| **I-2.1.2** | Implement `StubBridgeClient` for offline/test mode | Returns configurable canned `HouseholdProjection`. Supports `subscribe()` with empty async iterator. Offline-first per D-15. | `k1/bridge/connector/stub_client.py` | ~50 |
| **I-2.1.3** | Implement `HttpBridgeClient` for production K0 connectivity | HTTP/SSE client: `query()` → HTTP GET to K0 endpoint. `subscribe()` → SSE stream. Connection retry with exponential backoff. Circuit breaker. | `k1/bridge/connector/http_client.py` | ~100 |

**Epic total: ~210 lines across 3 files. 3 issues.**

---

#### Epic E-2.2: Household Projection + Memory Adapter

> HouseholdProjection data model, hydration logic, and the Concierge `IMemoryPort` adapter.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-2.2.1** | Define `HouseholdProjection` dataclass + schema | Frozen dataclass: members (name, role, age, access_level), devices (device_id → member_id), governance (house rules), allergies (member → severity-tagged list), projection_version, projection_stale flag. Matches kernel.md §126 W-50..W-55. | `k1/bridge/connector/household.py` | ~60 |
| **I-2.2.2** | Implement `hydrate_household()` — boot-time + offline fallback | `hydrate_household(bridge: IBridgeClient, cache_path: Path) → HouseholdProjection`. Online: `bridge.query("household.projection.v1")` → cache to SQLite. Offline: load last-known-good from SQLite, set `projection_stale=True`. Subscribe to `household.delta.v1` for live updates. | `k1/bridge/connector/hydration.py` | ~80 |
| **I-2.2.3** | Create `bridge_recall.py` — `IMemoryPort` adapter | `BridgeRecallAdapter`: wraps `IBridgeClient.query()` behind `IMemoryPort.recall(query, scope)`. Maps recall scopes to K0 memory store queries (st_epi, st_sem, st_procedural, st_social). Per D-16 pattern. | `k1/concierge/adapters/bridge_recall.py` | ~50 |

**Epic total: ~190 lines across 3 files. 3 issues.**

---

### 16.4 MS-3: CENTRAL KERNEL BOOTSTRAP

> **Goal:** Write the production `k1/kernel/bootstrap.py` that calls all 7 component factories in the correct order (kernel.md Phases 1–8) and assembles a complete `KernelRuntime`.
>
> **Depends on:** MS-1 (ConciergeFactory), MS-2 (BridgeClient, HouseholdProjection)
>
> **Blocks:** Nothing — this is the final milestone

#### Epic E-3.1: Kernel Runtime & Config

> Core types and configuration for the kernel.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-3.1.1** | Define `KernelRuntime` dataclass | Holds all 8 components: `bus`, `session_state`, `fabric`, `model_hub`, `orchestrator`, `planner`, `concierge`, `bridge`. Lifecycle methods: `start()` (spawns all), `stop()` (drains all), `health_check()`. | `k1/kernel/runtime.py` | ~60 |
| **I-3.1.2** | Implement `ConfigLoader` — real config loading | Replace `pass` body in `loader.py`. Load from YAML + env vars. Validate required fields. Return typed `KernelConfig` with per-component sub-configs. | `k1/kernel/loader.py` (rewrite) | ~80 |

**Epic total: ~140 lines across 2 files. 2 issues.**

---

#### Epic E-3.2: 8-Phase Bootstrap

> The production bootstrap function that wires all components.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-3.2.1** | Implement Phases 1–3: Config → Bus → SessionState | `boot_kernel(config_path) → KernelRuntime`. Phase 1: `ConfigLoader.load()`. Phase 2: `BusFactory.create_local()` + `create_mailbox_router()`. Phase 3: `SessionStateFactory.create_with_ports(bus_adapter, writer_adapter, lifecycle_adapter, sync_adapter, storage_adapter)`. | `k1/kernel/bootstrap.py` (start) | ~80 |
| **I-3.2.2** | Implement Phases 4–5: Fabric + ModelHub → Orchestrator + Planner | Phase 4: `FabricFactory.create_with_ports(session_reader, event_adapter, delta_bus, model_gateway, prompt_system)` + `ModelHubFactory.create_standalone()`. Phase 5: `OrchestratorFactory.create_production(...)` + `PlannerFactory.create_production(...)`. Cross-wire Planner→Orchestrator (hot-swap mock → real). | `k1/kernel/bootstrap.py` (append) | ~80 |
| **I-3.2.3** | Implement Phase 5.5 + 6: Bridge → Concierge | Phase 5.5: `BridgeClient.connect()` (or `StubBridgeClient` for offline). Phase 6: Create 8 Concierge adapters → `ConciergeFactory.create_with_ports(adapters)`. | `k1/kernel/bootstrap.py` (append) | ~60 |
| **I-3.2.4** | Implement Phase 6.5 + 7 + 8: Hydration → Cross-wire → Assemble | Phase 6.5: `hydrate_household(bridge, cache_path)`. Phase 7: `session_manager.start()`, bus subscriptions. Phase 8: Assemble `KernelRuntime(bus, ss, fabric, model_hub, orch, planner, concierge, bridge)` and return. | `k1/kernel/bootstrap.py` (finalize) | ~60 |

**Epic total: ~280 lines in 1 file. 4 issues.**

---

#### Epic E-3.3: Kernel Integration Tests

> End-to-end tests proving the full 8-phase bootstrap works.

| Issue | Title | Scope | Files Created | Lines |
|---|---|---|---|---|
| **I-3.3.1** | Integration test: full kernel boots with test adapters | Call `boot_kernel()` with test config. All 7 components created. `KernelRuntime.start()` succeeds. Send message through Concierge `IInputPort` → receive output via `IOutputPort`. `KernelRuntime.stop()` drains cleanly. | `tests/k1/kernel/test_bootstrap_integration.py` | ~120 |
| **I-3.3.2** | Integration test: offline mode (no K0 bridge) | Boot with `StubBridgeClient`. `HouseholdProjection.projection_stale == True`. Concierge still processes turns. Tools still serve local data. K0 recall returns empty. Graceful degradation. | `tests/k1/kernel/test_bootstrap_offline.py` | ~80 |
| **I-3.3.3** | Regression: old `start_kernel()` → C4 bridge wrapper | Verify `k1/concierge/kernel/bootstrap.py` can be updated to call `ConciergeFactory.create_with_ports()` internally, maintaining backward compatibility for any code that calls `start_kernel()`. | `tests/k1/kernel/test_c4_bridge.py` | ~80 |

**Epic total: ~280 lines across 3 files. 3 issues.**

---

### 16.5 Complete Issue Index

| MS | Epic | Issue | Title | Status |
|---|---|---|---|---|
| **MS-1** | E-1.1 | I-1.1.1 | Define `IInputPort` and `IOutputPort` Protocols | NOT STARTED |
| | | I-1.1.2 | Define `IClassificationPort` and `ILLMPort` Protocols | NOT STARTED |
| | | I-1.1.3 | Define `IStatePort`, `IDispatchPort`, `IDeltaPort`, `IMemoryPort` Protocols | NOT STARTED |
| | | I-1.1.4 | Add port validation helpers + `__all__` export | NOT STARTED |
| | E-1.2 | I-1.2.1 | Test adapters for Input, Output, Classification, LLM | NOT STARTED |
| | | I-1.2.2 | Test adapters for State, Dispatch, Delta, Memory | NOT STARTED |
| | | I-1.2.3 | Port compliance conformance tests | NOT STARTED |
| | E-1.3 | I-1.3.1 | `ws_input.py` — WebSocket → `IInputPort` | NOT STARTED |
| | | I-1.3.2 | `sse_output.py` — `IOutputPort` → SSE | NOT STARTED |
| | | I-1.3.3 | `ultrabert.py` — `IClassificationPort` adapter | NOT STARTED |
| | | I-1.3.4 | `model_gateway.py` — `ILLMPort` adapter | NOT STARTED |
| | | I-1.3.5 | `session_kernel.py` — `IStatePort` adapter | NOT STARTED |
| | | I-1.3.6 | `fabric_orchestrator.py` — `IDispatchPort` adapter | NOT STARTED |
| | | I-1.3.7 | `delta_bus.py` — `IDeltaPort` adapter | NOT STARTED |
| | E-1.4 | I-1.4.1 | `ConciergeFactory` skeleton + port validation | NOT STARTED |
| | | I-1.4.2 | Wire internal subsystems inside factory | NOT STARTED |
| | | I-1.4.3 | `ConciergeConfig` dataclass + `from_legacy()` bridge | NOT STARTED |
| | | I-1.4.4 | Integration test: factory + test adapters → Concierge boots | NOT STARTED |
| **MS-2** | E-2.1 | I-2.1.1 | Define `IBridgeClient` Protocol + types | NOT STARTED |
| | | I-2.1.2 | `StubBridgeClient` for offline/test | NOT STARTED |
| | | I-2.1.3 | `HttpBridgeClient` for production K0 | NOT STARTED |
| | E-2.2 | I-2.2.1 | `HouseholdProjection` dataclass + schema | NOT STARTED |
| | | I-2.2.2 | `hydrate_household()` boot-time + offline fallback | NOT STARTED |
| | | I-2.2.3 | `bridge_recall.py` — `IMemoryPort` adapter | NOT STARTED |
| **MS-3** | E-3.1 | I-3.1.1 | `KernelRuntime` dataclass | NOT STARTED |
| | | I-3.1.2 | `ConfigLoader` real implementation | NOT STARTED |
| | E-3.2 | I-3.2.1 | Phases 1–3: Config → Bus → SessionState | NOT STARTED |
| | | I-3.2.2 | Phases 4–5: Fabric + ModelHub → Orch + Planner | NOT STARTED |
| | | I-3.2.3 | Phase 5.5 + 6: Bridge → Concierge | NOT STARTED |
| | | I-3.2.4 | Phase 6.5 + 7 + 8: Hydration → Cross-wire → Assemble | NOT STARTED |
| | E-3.3 | I-3.3.1 | Full kernel boot integration test | NOT STARTED |
| | | I-3.3.2 | Offline mode integration test | NOT STARTED |
| | | I-3.3.3 | C4 bridge regression test | NOT STARTED |

### 16.6 Parallelization Opportunities

```
WEEK 1 (parallel):
  ├── MS-1/E-1.1 (ports)         ← can start Day 1
  ├── MS-2/E-2.1 (BridgeClient)  ← can start Day 1, independent
  └── MS-1/E-1.2 (test adapters) ← starts after E-1.1 ports exist

WEEK 2 (parallel after Week 1):
  ├── MS-1/E-1.3 (prod adapters) ← depends on E-1.1 ports
  ├── MS-2/E-2.2 (Household)     ← depends on E-2.1 BridgeClient
  └── MS-1/E-1.4 (factory)       ← depends on E-1.1 ports + E-1.2 test adapters

WEEK 3 (sequential):
  └── MS-3 (kernel bootstrap)    ← depends on MS-1 + MS-2
       ├── E-3.1 (runtime + config)
       ├── E-3.2 (8-phase bootstrap)
       └── E-3.3 (integration tests)
```

### 16.7 Definition of Done — Production Kernel

- [ ] `boot_kernel(config_path)` creates all 7 components via their factories
- [ ] `KernelRuntime.start()` spawns all component tasks
- [ ] User message via WebSocket → `IInputPort` → FSM → classification → dispatch → response → `IOutputPort` → SSE
- [ ] HouseholdProjection hydrated at boot (online) or loaded from cache (offline)
- [ ] All 63 existing Concierge tests still pass
- [ ] All ~9,485 existing component tests still pass
- [ ] `KernelRuntime.stop()` drains all components within 30s
- [ ] Zero imports from `poc.k1_poc` in production path
