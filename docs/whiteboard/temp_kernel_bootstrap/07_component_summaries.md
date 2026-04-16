# Component-Level Summaries — K1 Kernel Bootstrap

**Source:** Synthesis from 01_kernel_md_extraction.md, 02_wiring_simulation_extraction.md, 03_wiring_whiteboard_extraction.md
**Date:** 2026-04-11

---

## Table of Contents

1. [KernelService (Kernel Runtime)](#1-kernelservice)
2. [Bus](#2-bus)
3. [SessionState (SessionStateManager)](#3-sessionstate)
4. [Fabric (CapabilityFabric)](#4-fabric)
5. [ModelHub](#5-modelhub)
6. [Orchestrator](#6-orchestrator)
7. [Planner](#7-planner)
8. [Concierge (ConciergeController)](#8-concierge)
9. [Bridge (BridgeClient)](#9-bridge)
10. [Memory Writer](#10-memory-writer)

---

## 1. KernelService

### Purpose

Top-level runtime that owns the lifecycle of ALL kernel components. KernelService is the single entry point for starting the kernel, creating sessions, and shutting everything down. It replaces the POC's `boot()` function with a proper lifecycle manager.

### Architecture

```
KernelService
├── startup()           → Tier-1 shared components
├── create_session()    → Tier-2 per-session components
├── destroy_session()   → Cleanup per-session
└── shutdown()          → Reverse-order teardown
```

### Two-Tier Bootstrap

**Tier 1 — Shared (once per process):**

1. ConfigLoader.load()
2. ModelHub.create() + connect()
3. SharedFabric.create()
4. BridgeClient.connect()
5. Orchestrator.create()
6. Planner.create()

**Tier 2 — Per-Session (once per session):**

1. Bus.create(session_id)
2. SessionStateManager.create(session_id)
3. Fabric.create(session_id, shared_fabric)
4. Concierge.create(bus, ssm, fabric, ...)
5. MemoryWriter.create(bus, ssm, model_hub)

### Shutdown

Reverse order of bootstrap. 10-step sequence with circuit breakers at each stage.

### Key Decisions

- SIM-D-01: Two-tier split confirmed
- SIM-D-06: Factory owns all wiring (not components)
- SIM-D-09: One event loop per process, multi-process for scale

### Open Questions

- Cross-session Fabric resolution (SIM-GAP-55)
- KernelQueryPort not yet built (SIM-GAP-34)
- KernelSSEPort not yet built (SIM-GAP-34)

### Readiness

**V1 READY** — Core bootstrap achievable. Query/SSE ports deferred to Phase 2.

---

## 2. Bus

### Purpose

Fire-and-forget async message bus. Per-session, ephemeral (no persistence). Delivers events between components without coupling them.

### Architecture (kernel.md Part D)

```
Bus
├── InMemoryBus (production: per-session)
├── NullBus (testing: no-op)
├── LoggingBus (debugging: logs all events)
├── 60+ topic strings
└── BusMiddleware chain
```

### Ports

| Port | Type | Direction |
| --- | --- | --- |
| IBusPort | Protocol | Publish/Subscribe interface |

### Key API

```python
async def publish(self, topic: str, event: Any) -> None: ...
async def subscribe(self, topic: str, handler: Callable) -> Subscription: ...
async def unsubscribe(self, subscription: Subscription) -> None: ...
```

### Topics (60+)

Core topics include:

- `user.input` — User message arrives
- `response.final` — Final response ready
- `response.stream` — Streaming chunk
- `delta.*` — State change deltas
- `task.*` — Task lifecycle events
- `memory.*` — Memory operations
- `error.*` — Error events

### Scope

Per-session. Each session gets its own Bus instance. No cross-session communication via Bus.

### Bootstrap Phase

Tier 2, Step 1 — First per-session component created.

### Dependencies

- Config (topic list)
- No other components

### Circuit Breakers

- Subscription leak detector (warns if >100 subscriptions per topic)
- Dead letter queue for unhandled events

### Gotchas

- Fire-and-forget means NO delivery guarantee
- Handlers must be async
- Bus does NOT persist — restart loses all state
- Circular subscription possible (A publishes → B handles → B publishes → A handles)

### Readiness

**PRODUCTION READY** — InMemoryBus is simple and well-tested. NullBus for tests.

---

## 3. SessionState (SessionStateManager)

### Purpose

Per-session state container. Tracks conversation history, user context, active tasks, emotional state, family model, and all turn-level state. 96KB budget per session.

### Architecture (kernel.md Part C)

```
SessionStateManager
├── 12 sections (history, user_context, active_tasks, ...)
├── IStoragePort (ABC) → InMemoryStorage / SQLiteStorage
├── IEventPort (ABC) → SessionBusAdapter
├── IWriterPort (ABC) → DirectWriter
├── ILifecyclePort (ABC) → SessionLifecycleAdapter
├── IK0SyncPort (ABC) → K0SyncAdapter / NullK0SyncPort
└── Delta tracking (every write emits delta event)
```

### Ports (5 Internal)

| Port | Type (ABC) | Adapters |
| --- | --- | --- |
| IStoragePort | ABC | InMemoryStorage, SQLiteStorage, NullStoragePort |
| IEventPort | ABC | SessionBusAdapter, NullEventPort |
| IWriterPort | ABC | DirectWriter |
| ILifecyclePort | ABC | SessionLifecycleAdapter |
| IK0SyncPort | ABC | K0SyncAdapter, NullK0SyncPort |

### 12 Sections

1. `history` — Conversation turns
2. `user_context` — User profile/preferences
3. `active_tasks` — In-flight tasks
4. `emotional_state` — Affect tracking
5. `family_model` — Household members
6. `session_meta` — Session metadata
7. `classification` — Last classification result
8. `plan` — Current plan
9. `tool_results` — Tool execution results
10. `memory_context` — Retrieved memories
11. `response_draft` — Draft response
12. `error_state` — Error context

### Key API

```python
async def read(self, sections: list[str]) -> Snapshot: ...
async def write(self, section: str, op: str, data: Any) -> WriteResult: ...
async def checkpoint(self) -> None: ...
async def rollback(self, checkpoint_id: str) -> None: ...
```

### Budget

96KB total per session. Sections have individual limits. Overflow triggers eviction (oldest turns first).

### Scope

Per-session. Each session gets its own SSM instance.

### Bootstrap Phase

Tier 2, Step 2 — After Bus, before Fabric.

### Dependencies

- Bus (for delta emission via SessionBusAdapter)
- Config (section limits, budget)

### Gotchas

- All ports are ABC (not Protocol) — must subclass, no structural typing
- IEventPort is ABC but Concierge's IDeltaPort is Protocol — adapter bridges
- 96KB budget is HARD limit — writes fail if exceeded
- Snapshot is immutable — mutations require write() call
- ss parameter in actors typed as `Any` (SIM-FLAG-05) — no type safety

### Readiness

**PRODUCTION READY** — Well-specified, clear budget model. ABC ports need explicit adapters.

---

## 4. Fabric (CapabilityFabric)

### Purpose

Capability discovery, routing, and execution container. Maps capability names to capability implementations. Handles LOW/MEDIUM/HIGH tier dispatch differently.

### Architecture (kernel.md Part B)

```
Fabric
├── 6 Internal Ports (all ABC)
│   ├── ISessionStateReader → SessionStateReaderAdapter(ssm, session_id)
│   ├── IEventPort → DeltaEmitAdapter(event_port, delta_bus)
│   ├── IBridgePort → BridgeCallAdapter / NullBridgePort
│   ├── IModelGatewayPort → ModelGatewayAdapter(model_hub)
│   ├── IPromptSystemPort → PromptSystemAdapter
│   └── IDeltaBusPort → DeltaBusAdapter(bus)
├── CapabilityRegistry → discovers and routes capabilities
├── ToolContext → runtime context injected into each capability
└── 12 production adapters + 6 null adapters
```

### Ports (6 Internal)

| Port | Type (ABC) | Production Adapter |
| --- | --- | --- |
| ISessionStateReader | ABC | SessionStateReaderAdapter(ssm, session_id) |
| IEventPort | ABC | DeltaEmitAdapter(event_port, delta_bus) |
| IBridgePort | ABC | BridgeCallAdapter(bridge_client) |
| IModelGatewayPort | ABC | ModelGatewayAdapter(model_hub) |
| IPromptSystemPort | ABC | PromptSystemAdapter() |
| IDeltaBusPort | ABC | DeltaBusAdapter(bus) |

### Dispatch Tiers

| Tier | Path | Description |
| --- | --- | --- |
| LOW | dispatch_direct() → CapabilityFabric.execute() | Synchronous, inline |
| MEDIUM | dispatch_envelope() → Orchestrator queue | Async, queued |
| HIGH | dispatch_envelope() → Planner → Orchestrator | Multi-step planning |

### Scope

Dual — SharedFabric (Tier 1, shared capabilities like model registry) + per-session Fabric (Tier 2, session-specific capabilities).

### Bootstrap Phase

Tier 1: SharedFabric.create() (Step 3)
Tier 2: Fabric.create(session_id, shared_fabric) (Step 3)

### Dependencies

- SessionStateManager (for ISessionStateReader)
- Bus (for IDeltaBusPort, IEventPort)
- ModelHub (for IModelGatewayPort)
- Bridge (for IBridgePort)

### Gotchas

- SessionStateReaderAdapter takes TWO args (ssm, session_id) — not just ssm (F-02, S-05)
- DeltaEmitAdapter takes TWO args (event_port, delta_bus) — not one (G-07)
- All ports are ABC (not Protocol)
- CapabilityRequest type collision between fabric and concierge (SIM-GAP-06)
- ToolContext.recall_fn is a closure over IMemoryPort — must be wired at factory time

### Readiness

**V1 READY** — Core dispatch works. Cross-session resolution (SIM-GAP-55) deferred.

---

## 5. ModelHub

### Purpose

LLM gateway. Abstracts model selection, routing, streaming, and budget enforcement. All LLM calls go through ModelHub.

### Architecture

```
ModelHub
├── IModelHubPort (Protocol)
│   ├── execute(HubRequest) → HubResponse
│   └── stream_execute(HubRequest) → AsyncIterator[HubChunk]
├── Model Registry (model configs, routing rules)
├── Budget Enforcer (token limits per request)
└── Adapters: OpenAI, Azure, Local, Mock
```

### Ports

| Port | Type | Direction |
| --- | --- | --- |
| IModelHubPort | Protocol | Execute / StreamExecute |

### Key API

```python
async def execute(self, request: HubRequest) -> HubResponse: ...
async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]: ...
```

### HubRequest Fields

- `messages: list[Message]` — Conversation messages
- `model_hint: str | None` — Preferred model
- `budget: Budget` — Token/time limits
- `tools: list[ToolDef] | None` — Available tools
- `stream: bool` — Whether to stream

### Scope

Shared (Tier 1). One ModelHub instance per process, shared across all sessions.

### Bootstrap Phase

Tier 1, Step 2 — After Config, before SharedFabric.

### Dependencies

- Config (model registry, API keys, routing rules)
- No other kernel components

### Gotchas

- Memory Writer expects `chat()` method, but canonical interface is `execute()` — needs ModelHubChatAdapter (SIM-FLAG-03, SIM-GAP deferred)
- HubRequest/HubResponse are structurally compatible with ILLMPort — direct passthrough works
- Budget enforcement is per-request, not per-session

### Readiness

**PRODUCTION READY** — Well-defined interface. ModelHubChatAdapter for Memory Writer deferred to Phase 2.

---

## 6. Orchestrator

### Purpose

Task orchestration for MEDIUM and HIGH tier requests. Manages task lifecycle, capability sequencing, and result aggregation. Receives TaskEnvelopes from Fabric dispatch.

### Architecture

```
Orchestrator
├── TaskQueue → ordered task processing
├── TaskExecutor → executes individual tasks
├── ResultAggregator → combines multi-step results
├── FabricOrchestratorAdapter → bridges types (SIM-D-24)
└── AdminHttpAdapter → admin API (post-injected, G-05)
```

### Ports

| Port | Type | Direction |
| --- | --- | --- |
| IDispatchPort (MED/HIGH) | Protocol | Receives TaskEnvelopes |

### Dispatch Flow

```
Fabric.dispatch_envelope(envelope)
  → if tier == MEDIUM: Orchestrator.execute(envelope)
  → if tier == HIGH: Planner.plan(envelope) → Orchestrator.execute_plan(plan)
```

### Scope

Shared (Tier 1). One Orchestrator per process.

### Bootstrap Phase

Tier 1, Step 5 — After BridgeClient, before Planner.

### Dependencies

- Fabric (for capability execution)
- ModelHub (for LLM calls during orchestration)
- Bridge (for cross-kernel calls)

### Gotchas

- FabricOrchestratorAdapter bridges POC CapabilityRequest ↔ Production CapabilityRequest (SIM-D-24)
- AdminHttpAdapter is post-injected via `orchestrator._admin = ...` — not constructor (G-05)
- ExecutionMonitor has circular dependency with Orchestrator (G-06)
- handle_task() vs dispatch_envelope() method name mismatch (Mismatch 6)
- TaskEnvelope POC/Production field mismatch (SIM-GAP-26)

### Readiness

**V1 READY** — POC types work for V1. Production type bridging needed for V2.

---

## 7. Planner

### Purpose

Multi-step planning for HIGH-tier requests. Decomposes complex requests into ordered capability sequences. Produces execution plans for Orchestrator.

### Architecture

```
Planner
├── PlanGenerator → LLM-powered plan creation
├── PlanValidator → validates plan feasibility
├── PlanOptimizer → reorders for efficiency
└── Plan → ordered list of steps with dependencies
```

### Ports

| Port | Type | Direction |
| --- | --- | --- |
| (internal) | — | Uses ModelHub for LLM, Fabric for capability lookup |

### Scope

Shared (Tier 1). One Planner per process.

### Bootstrap Phase

Tier 1, Step 6 — Last shared component.

### Dependencies

- ModelHub (for LLM-powered planning)
- Fabric (for capability registry lookup)

### Gotchas

- Planner is the least-specified component in the source documents
- Planning prompts and strategies not fully defined
- V1 may use simple sequential plans only

### Readiness

**V1 MINIMAL** — Basic sequential planning. Full DAG planning deferred.

---

## 8. Concierge (ConciergeController)

### Purpose

The user-facing agent. Manages the conversation FSM (Finite State Machine), classification, response generation, and turn lifecycle. The "brain" of each session.

### Architecture (k1_wiring_whiteboard.md)

```
ConciergeController
├── 8 External Ports (all Protocol)
│   ├── IInputPort → (unused in V1, bus subscription instead)
│   ├── IOutputPort → (unused in V1, bus events instead)
│   ├── IClassificationPort → Phase1Pipeline
│   ├── ILLMPort → ModelHub passthrough
│   ├── IStatePort → SessionStateManager direct
│   ├── IDispatchPort → FabricOrchestratorAdapter
│   ├── IDeltaPort → DeltaAggregator → Bus
│   └── IMemoryPort → ToolContext.recall_fn closure
├── FSM (ConciergeStateMachine)
│   ├── States: IDLE → CLASSIFYING → ROUTING → EXECUTING → RESPONDING → IDLE
│   └── 6 transitions with guards
├── Phase1Pipeline (classification)
├── ResponseGenerator (LLM-powered)
├── Front handlers (3: classify, route, respond)
└── Internal modules: 40K lines, 130 files (monolith)
```

### 8 External Ports

| Port | Protocol | Adapter | Status |
| --- | --- | --- | --- |
| IInputPort | Protocol | (none — bus subscription) | UNUSED V1 |
| IOutputPort | Protocol | (none — bus events) | UNUSED V1 |
| IClassificationPort | Protocol | Phase1PipelineAdapter | V1 READY |
| ILLMPort | Protocol | ModelHubPassthrough | V1 READY |
| IStatePort | Protocol | SSM direct | V1 READY |
| IDispatchPort | Protocol | FabricOrchestratorAdapter | V1 READY |
| IDeltaPort | Protocol | DeltaAggregatorAdapter | V1 READY |
| IMemoryPort | Protocol | ToolContextRecallAdapter | V1 READY |

### Internal Architecture (from whiteboard)

17-step monolith flow:

1. Input validation
2. Session state hydration
3. Classification (Phase1Pipeline)
4. Safety check
5. Intent extraction
6. Domain routing
7. Context assembly
8. Memory recall
9. Tool selection
10. LLM call
11. Response generation
12. Response validation
13. Delta emission
14. State update
15. Memory write trigger
16. Response delivery
17. Cleanup

### Scope

Per-session. Each session gets its own Concierge.

### Bootstrap Phase

Tier 2, Step 4 — After Bus, SSM, Fabric.

### Dependencies

ALL other components:

- Bus (for event subscription/publication)
- SessionState (for state management)
- Fabric (for capability dispatch)
- ModelHub (via ILLMPort)
- Bridge (via Fabric's IBridgePort)

### Gotchas

- 9 late-wired setters on ConciergeController (SIM-GAP-09) — constructor takes (bus, router), rest injected after
- ExperienceLayer takes ZERO parameters — fully hardcoded (SIM-GAP-08)
- 3 of 8 external ports are UNUSED in V1 (IInputPort, IOutputPort, partially IClassificationPort)
- 40K lines of internal monolith — hexagonal boundary exists but internals are tightly coupled
- FSM state transitions must be carefully ordered
- actors use `ss: Any` — no type safety for SessionState access (SIM-FLAG-05)

### Readiness

**V1 READY** — FSM works, 6/8 ports wired, 2 unused ports acceptable. Internal monolith is tech debt but functional.

---

## 9. Bridge (BridgeClient)

### Purpose

Cross-kernel communication (K1 ↔ K0). Enables K1 to call K0 capabilities (storage, sync, security) and receive events from K0.

### Architecture

```
BridgeClient (facade — ~80 lines, NOT YET BUILT)
├── IBridgePort → BridgeCallAdapter
├── HTTP/gRPC transport
├── Authentication (K0 API keys)
├── Circuit breaker (K0 unavailability)
└── Retry with exponential backoff
```

### Ports

| Port | Type | Direction |
| --- | --- | --- |
| IBridgePort | ABC (Fabric internal) | K1 → K0 calls |

### Status

**NOT YET BUILT.** Key gaps:

- SIM-GAP-33: BridgeClient facade not built (~80 lines needed)
- SIM-GAP-49: Production adapters for Bridge not built
- SIM-GAP-05: Bridge has no OTel span creation — trace chain breaks

### Scope

Shared (Tier 1). One BridgeClient per process.

### Bootstrap Phase

Tier 1, Step 4 — After SharedFabric, before Orchestrator.

### Dependencies

- Config (K0 endpoint, API keys)
- No other K1 components

### Gotchas

- BridgeClient is a facade over existing bridge/ module
- NullBridgePort available for testing without K0
- K0 availability is NOT guaranteed — circuit breaker essential
- Bridge failure should NOT crash kernel — graceful degradation

### Readiness

**NOT READY** — Facade not built. ~80 lines of code needed. NullBridgePort available for V1 testing.

---

## 10. Memory Writer

### Purpose

Asynchronous memory persistence. Listens for turn-complete events, extracts memories from conversation, and writes to long-term storage.

### Architecture

```
MemoryWriter
├── Bus subscription (turn.complete topic)
├── Memory extraction (LLM-powered)
├── IModelHubPort.chat() → needs ModelHubChatAdapter
└── Storage write (via K0 Bridge or local)
```

### Ports

| Port | Type | Direction |
| --- | --- | --- |
| IModelHubPort | Protocol (chat variant) | LLM calls for extraction |

### Method Mismatch

- Memory Writer expects: `model_hub.chat(messages, budget, hint)`
- Canonical interface: `model_hub.execute(HubRequest) → HubResponse`
- Resolution: ModelHubChatAdapter (~25 lines) — DEFERRED to Phase 2

### Scope

Per-session. Each session gets its own Memory Writer.

### Bootstrap Phase

Tier 2, Step 5 — Last per-session component.

### Dependencies

- Bus (for turn.complete subscription)
- SessionState (for conversation history)
- ModelHub (for LLM-powered extraction)
- Bridge/Storage (for persistence)

### Gotchas

- chat() vs execute() mismatch is the only deferred type mismatch
- Memory Writer is fire-and-forget — failure doesn't block response
- Runs AFTER response delivery — non-blocking

### Readiness

**V1 MINIMAL** — Can use ModelHub.execute() directly with manual HubRequest construction. ModelHubChatAdapter deferred.

---

## Cross-Component Summary

### Bootstrap Order (Full)

```
TIER 1 (shared, once per process):
  1. ConfigLoader.load()
  2. ModelHub.create() + connect()
  3. SharedFabric.create()
  4. BridgeClient.connect()     ← NOT YET BUILT
  5. Orchestrator.create()
  6. Planner.create()

TIER 2 (per-session):
  1. Bus.create(session_id)
  2. SessionStateManager.create(session_id)
  3. Fabric.create(session_id, shared_fabric)
  4. Concierge.create(bus, ssm, fabric, ...)
  5. MemoryWriter.create(bus, ssm, model_hub)
```

### Component Sharing Table

| Component | Scope | Shared Across Sessions? |
| --- | --- | --- |
| Config | Process | Yes |
| ModelHub | Process | Yes |
| SharedFabric | Process | Yes |
| BridgeClient | Process | Yes |
| Orchestrator | Process | Yes |
| Planner | Process | Yes |
| Bus | Session | No |
| SessionState | Session | No |
| Fabric | Session (+ shared) | No (links to shared) |
| Concierge | Session | No |
| MemoryWriter | Session | No |

### Port Type Summary

| Component | Port Style | Count |
| --- | --- | --- |
| Concierge (external) | Protocol | 8 |
| SessionState (internal) | ABC | 5 |
| Fabric (internal) | ABC | 6 |
| Bus | Protocol | 1 |
| ModelHub | Protocol | 1 |
| **Total** | | **21 unique ports** |

### Readiness Matrix

| Component | Readiness | Blocker |
| --- | --- | --- |
| KernelService | V1 READY | Query/SSE ports deferred |
| Bus | PRODUCTION READY | — |
| SessionState | PRODUCTION READY | — |
| Fabric | V1 READY | Cross-session resolution |
| ModelHub | PRODUCTION READY | — |
| Orchestrator | V1 READY | Type bridging V2 |
| Planner | V1 MINIMAL | Full DAG planning |
| Concierge | V1 READY | 2 unused ports, monolith debt |
| Bridge | NOT READY | ~80 lines facade needed |
| Memory Writer | V1 MINIMAL | chat() adapter deferred |

### Verdict

**BOOTSTRAP IS ACHIEVABLE.** 8/10 components are V1-ready or better. BridgeClient needs ~80 lines of facade code. Memory Writer can work without the ModelHubChatAdapter by constructing HubRequest manually.
