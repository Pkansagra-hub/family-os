# K1 Wiring Simulation - Complete Extraction

**Source:** `D:\familyos\docs\whiteboard\k1_wiring_simulation.md` (~4820 lines, 382KB)
**Date:** 2026-04-02
**Companion Docs:** `k1_wiring_whiteboard.md` (audit + milestones), `kernel.md` (spec)

---

## EXECUTIVE SUMMARY

Production kernel wiring simulation covering 10 steps. Discovered **56 gaps, 26 flags, and 40+ design decisions** through iterative code audit and verification.

**Key Finding:** The kernel requires a **two-tier bootstrap architecture** (startup tier for shared components + session tier for per-session components), departing from single-session pseudocode in kernel.md §7.

**Simulation Result: WIRING ACHIEVABLE** — Zero architectural blockers, all dependencies verified acyclic.

---

## GROUND RULES

1. Every step reads real code before deciding anything
2. Missing components stated with gap ID (SIM-GAP-xx)
3. Existing code integration difficulties flagged (SIM-FLAG-xx)
4. Design decisions recorded (SIM-D-xx)
5. Problems are NOT skipped — surfaced explicitly
6. Each step ends with VERDICT: proceed / blocked / needs-decision

---

## STEP 1: KERNEL SERVICE WRAPPER

### KernelService Architecture

```
KernelService
  ├── shared (created once at service boot):
  │    ├── fabric: Fabric
  │    ├── model_hub: ModelHub
  │    ├── orchestrator: Orchestrator
  │    ├── planner: Planner
  │    ├── bridge: BridgeClient
  │    ├── household: HouseholdProjection (frozen, delta-updated)
  │    ├── capability_registry: CapabilityRegistry
  │    ├── ultrabert: UltraBERTModel
  │    ├── back_pool: BackPool (global, session-aware limits)
  │    └── system_bus: IBus (admin/health events only)
  │
  ├── sessions: dict[str, SessionInstance]
  │    └── SessionInstance
  │         ├── session_id, member_id
  │         ├── bus: IBus (isolated per-session)
  │         ├── router: IMailboxRouter
  │         ├── session_state: SessionStateManager
  │         ├── concierge: Concierge (from ConciergeFactory)
  │         ├── ledger: LedgerWriter
  │         ├── created_at, last_active: datetime
  │
  └── lifecycle:
       ├── create_session(device_id) → session_id
       ├── get_session(session_id) → SessionInstance
       ├── destroy_session(session_id) → None
       ├── evict_idle_sessions(timeout_minutes) → list[str]
       └── health_check() → HealthReport
```

### Session States
CREATE → ACTIVE → IDLE → TIMEOUT → DESTROY

### Component Sharing (SIM-D-04)

| Component | Scope | Why |
| --- | --- | --- |
| Bus | Per-session | Isolation (no topic collision) |
| SessionState | Per-session | Each user's state is independent |
| FSM (ConciergeController) | Per-session | One state machine per conversation |
| LedgerWriter | Per-session | Audit trail per session |
| DeltaAggregator | Per-session | Mutations scoped to session's SS |
| ExperienceLayer | Per-session | Affect/rhythm per conversation |
| BackPool | **Shared** | Global pool limits total compute |
| Fabric | **Shared** (V1) / Per-session (V2) | Stateless except SSM reader |
| ModelHub | **Shared** | LLM providers, connection pooling |
| Orchestrator | **Shared** | Stateless dispatch engine |
| Planner | **Shared** | Stateless planning engine |
| Bridge | **Shared** | One K0 connection |
| HouseholdProjection | **Shared** | All sessions see same household |
| CapabilityRegistry | **Shared** | Tools don't change per session |
| UltraBERT model | **Shared** | One instance, thread-safe |

### Decisions (SIM-D-01 to SIM-D-05)

- **SIM-D-01:** Per-session Bus (Option B) — isolated LocalBus per session
- **SIM-D-02:** KernelService + SessionInstance model
- **SIM-D-03:** cognitive_trace_id per-turn, propagated end-to-end
- **SIM-D-04:** Component sharing table (9 shared, 8 per-session)
- **SIM-D-05:** Single asyncio event loop per process, multi-process for scale

### Gaps (SIM-GAP-01 to SIM-GAP-05)

| ID | Description | Severity |
| --- | --- | --- |
| SIM-GAP-01 | Builder functions don't set session_id/cognitive_trace_id on Envelope headers | MEDIUM |
| SIM-GAP-02 | SessionDelta lacks session_id and cognitive_trace_id | LOW |
| SIM-GAP-03 | device_id → member_id resolution not implemented | MEDIUM |
| SIM-GAP-04 | Bootstrap creates static trace IDs once at boot, not per-turn | MEDIUM |
| SIM-GAP-05 | Bridge has no OTel span creation — trace chain breaks at K1↔K0 | HIGH |

---

## STEP 2: CONCIERGE PORTS

### Two-Layer Port Architecture

**LAYER 1: EXTERNAL PORTS (kernel.md §89) — NEW**
IInputPort, IOutputPort, IClassificationPort, ILLMPort, IStatePort, IDispatchPort, IDeltaPort, IMemoryPort

**LAYER 2: INTERNAL PORTS (already exist) — STAY UNTOUCHED**
IConciergeModelPort, IFabricGatewayPort, IStateReadPort, IDeltaEmitPort, IFabricPort, Phase1Pipeline, UltraBERTAdapter, ILedgerStore

### The 8 External Port Signatures

```python
class IInputPort(Protocol):
    async def receive(self) -> UserMessage: ...

class IOutputPort(Protocol):
    async def send(self, event: OutputEvent) -> DeliveryReceipt: ...
    # OutputEvent: StreamChunkEvent | FinalResponseEvent | ProgressEvent | IntentAckEvent | ClarificationEvent | ErrorEvent

class IClassificationPort(Protocol):
    async def classify(self, text: str) -> ClassificationResult: ...
    # ClassificationResult: tier (LOW/MED/HIGH), domain, safety (GREEN/AMBER/RED/CRISIS), intents

class ILLMPort(Protocol):
    async def execute(self, request: HubRequest) -> HubResponse: ...
    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]: ...

class IStatePort(Protocol):
    async def read(self, sections: list[str]) -> Snapshot: ...
    async def write(self, section: str, op: str, data: Any) -> WriteResult: ...

class IDispatchPort(Protocol):
    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult: ...
    async def dispatch_envelope(self, envelope: TaskEnvelope) -> None: ...

class IDeltaPort(Protocol):
    async def subscribe(self, topics: list[str]) -> DeltaStream: ...
    async def publish(self, event: Any) -> None: ...
    async def errors(self) -> ErrorStream: ...

class IMemoryPort(Protocol):
    async def recall(self, query: str, selectors: list[str]) -> MemoryResult: ...
```

### Type Bridging Strategy (SIM-D-08)

| External Port | External Type | Internal Type | Bridge |
| --- | --- | --- | --- |
| ILLMPort | HubRequest/HubResponse | IModelHubPort | Direct passthrough |
| IClassificationPort | ClassificationResult | Phase1Result | Adapter converts |
| IStatePort | Snapshot/WriteResult | duck-typed methods | Wrapper object |
| IDispatchPort | CapabilityRequest (kernel.md) | CapabilityRequest (k1.fabric.types) | Type converter |
| IDeltaPort | publish(event) | flush_fn: Callable | Closure wrapping |
| IMemoryPort | MemoryResult | Callable → list[dict] | Closure wrapping |

---

## STEP 3: TEST ADAPTERS + FACTORY SKELETON

### Current Bootstrap: 32-Step Monolith → 26-Step Factory

Factory wiring sequence (Phases A-H):
- **Phase A:** Infrastructure (Bus, Router, Mailboxes — received as params)
- **Phase B:** Leaf Nodes (InMemoryLedgerStore, BackPool, ReadyQueue, UserActivityTracker, ExperienceLayer, DynamicPromptBuilder)
- **Phase C:** Layer 1-2 (LedgerWriter, BackTopicRouter, ConciergeController)
- **Phase D:** Port Adaptation (state, recall, fabric, writer, phase1 adapters)
- **Phase E:** Wire FSM (9 setters)
- **Phase F:** Build ToolContexts + Dispatchers
- **Phase G:** Higher-layer Subsystems (DeltaApplicator, HILCoordinator, WeaveBatcher, Orchestrator)
- **Phase H:** Subscriptions + Consumer

### Init Order: 6 Dependency Layers (NO CIRCULAR DEPS)
Layer 0 (Leaf) → Layer 1 (Needs L0) → Layer 2 (Needs L1) → Layer 3 (Needs L2) → Layer 4 (Needs L3) → Layer 5 (Needs L4) → Layer 6 (Needs L5)

### ConciergeSession Wrapper (SIM-D-12)
```python
class ConciergeSession:
    async def start(self) -> None
    async def stop(self) -> None
    bus: IBus, fsm: ConciergeController, session_state: Any, is_running: bool
```

---

## STEP 4: BUS INTEGRATION

### Key Finding: LocalBus is PURELY SYNCHRONOUS
All operations sync: publish(), subscribe(), unsubscribe(), close(). threading.Lock safe with single asyncio event loop (sub-microsecond hold).

### 43 Static Topic Strings
No topic contains session_id, task_id, or runtime data. Session scoping via envelope.session_id field.

### Decisions
- **SIM-D-13:** KernelService creates Bus + Router. ConciergeFactory receives them.
- **SIM-D-14:** Ordered Bus (TimingChain) for production, unordered for tests
- **SIM-D-15:** TracingMiddleware stamps session_id + cognitive_trace_id on EVERY envelope
- **SIM-D-16:** Consumer loop calls bus.sweep() when idle

---

## STEP 5: SESSIONSTATE INTEGRATION

### Key Discovery: IStatePort ≡ SessionStateManager
SSM passed directly as IStatePort. No wrapper needed. Concierge calls 100+ methods across 12 section objects.

### All 15 Sections (12 used by Concierge, 3 unused)
All section names used by Concierge exist in k1/sessionstate/sections/. **Zero mismatches.**

### Decisions
- **SIM-D-17:** IStatePort IS the SessionStateManager. No wrapper.
- **SIM-D-18:** KernelService manages SSM lifecycle (start/stop)
- **SIM-D-19:** create_standalone() for V1, create_with_ports() for Phase 2

---

## STEP 6: FABRIC + MODELHUB INTEGRATION

### Fabric's 6 Ports (Production Status)

| Port | Production Adapter | Status |
| --- | --- | --- |
| ISessionStateReader | SessionStateReaderAdapter | YES |
| IEventPort | LocalEventAdapter | YES |
| IBridgePort | POCMockBridgeAdapter | PARTIAL |
| IModelGatewayPort | TestModelGatewayAdapter | TEST ONLY |
| IPromptSystemPort | TestPromptSystemAdapter | TEST ONLY |
| IDeltaBusPort | TestDeltaBusAdapter | TEST ONLY |

### ModelHub Consumer Map (4 Consumers, 4 Different Interfaces)

| Consumer | Port | Methods |
| --- | --- | --- |
| Concierge | IModelHubPort (canonical) | execute(), stream_execute() |
| Planner | ILLMPort (subset) | execute() only |
| Fabric | IModelGatewayPort (handle-factory) | create_handle(), release_handle() |
| Memory Writer | IModelHubPort (collision!) | chat(messages, budget, hint) |

### Decisions
- **SIM-D-20:** Fabric IS IFabricPort. Pass directly, no adapter.
- **SIM-D-21:** ModelHubFactory.create_standalone() for ILLMPort
- **SIM-D-22:** ModelHub shared. Fabric per-session (amended in Step 8.5).

---

## STEP 7: ORCHESTRATOR + PLANNER INTEGRATION

### Critical Finding: Two Different TaskEnvelope Types

| Field | POC | Production |
| --- | --- | --- |
| tier | ComplexityTier enum | str ("MEDIUM"/"HIGH") |
| capabilities | None | List[str] (required) |
| params | None | Dict[str, Dict] |
| budget | Budget dataclass | None |
| task_id | "task-xxxx" | (uses envelope_id) |
| cognitive_trace_id | None | None (spec says it, code doesn't) |

### Cross-Wiring Phase 5b
Phase 1: Orch created with MockPlannerAdapter → Phase 2: Planner created → Phase 3: Hot-swap planner.get_mailbox() → PlannerAdapter → orchestrator._planner_port → Phase 4: planner.start()

### Decisions
- **SIM-D-24:** FabricOrchestratorAdapter replaces POC routing stack
- **SIM-D-25:** Orchestrator and Planner shared (one per process)
- **SIM-D-26:** Phased bootstrap: Phase 4 (Orch+Mock) → Phase 5 (Planner) → Phase 5b (hot-swap)

---

## STEP 8: BRIDGE CLIENT + HOUSEHOLD PROJECTION

### Bridge Implementation Status

| Module | Status |
| --- | --- |
| bridge/core/ | ✅ COMPLETE (BridgeConfig, EnvelopeBuilder, Signing, HttpTransport) |
| bridge/kernel/ | ⚠️ PARTIAL (KernelCommandPort only, 1/4 ports) |
| bridge/sync/ | ⚠️ PARTIAL (LocalOutbox only) |
| bridge/connector/ | ❌ STUB |
| bridge/adapters/ | ❌ STUB |
| BridgeClient | ❌ MISSING |
| IKernelQueryPort | ❌ MISSING |
| IKernelSSEPort | ❌ MISSING |

### Bridge Consumer Map (7 Consumers)
1. Concierge (IMemoryPort) — Query + Command
2. Orchestrator (IBridgeWritePort) — Command + Query (WAL)
3. Planner (IBridgePort) — Query + Command
4. Fabric (IBridgePort) — Command + Query + IFL
5. Memory Writer (IBridgeCommandPort) — Command only
6. SessionState (IK0SyncPort) — Command + Query
7. Concierge Household — Query + SSE

### Edge-First Offline Architecture
- ONLINE: Full K0 access
- OFFLINE: Commands queued to LocalOutbox. Queries return empty/stale.
- DEGRADED: Commands slow. Queries may timeout.

### HouseholdProjection
- Frozen in-memory projection, NOT SessionState
- Per-turn access: 0ms (no K0 round-trip)
- Members, devices, governance, allergies — family-level identity data

### Decisions
- **SIM-D-29:** BridgeClient is thin facade wrapping 3 ports
- **SIM-D-30:** BridgeClient shared (one per process)
- **SIM-D-31:** HouseholdProjection NOT part of SessionState
- **SIM-D-32:** BridgeClient created early (Phase 2.5), consumed late
- **SIM-D-33:** Each adapter has built-in offline fallback

---

## STEP 8.5: CROSS-COMPONENT DEPENDENCY AUDIT

### Critical Finding: Shared Orchestrator ↔ Per-Session Fabric Conflict

Orchestrator (shared) needs Fabric but Fabric's SessionStateReaderAdapter is bound to ONE SSM.

### Solution: TWO Fabric Instances
- Shared Fabric for Orchestrator + Planner (NullStateReaderAdapter)
- Per-session Fabric for Concierge (real SessionStateReaderAdapter)

### Decisions
- **SIM-D-34:** V1: Orchestrator gets Fabric with NullStateReader
- **SIM-D-35:** TWO Fabric instances — shared + per-session
- **SIM-D-36:** Shared CapabilityRegistry

---

## STEP 9: 8-PHASE BOOTSTRAP ASSEMBLY (TWO-TIER)

### KEY FINDING: Two-Tier Bootstrap Architecture

kernel.md §7 assumes single-session. Reality requires split:

### Tier 1: KernelService.startup() — Shared Components

| Phase | Component | Config |
| --- | --- | --- |
| S1 | Configuration loading | KernelConfig |
| S2 | ModelHub (shared, stateless) | ModelHubFactory.create_standalone() |
| S3 | Shared Fabric (NullState) | FabricFactory with NullStateReaderAdapter |
| S4 | BridgeClient (shared, or None offline) | BridgeClient.connect(config) |
| S5 | Orchestrator (shared, MockPlanner) | OrchestratorFactory.create_production() |
| S6 | Planner (shared) | PlannerFactory.create_production() |
| S6b | Cross-wire Orch↔Planner | orchestrator._planner_port = PlannerAdapter(...) |
| S7 | Expose KernelRuntime | Return shared components registry |

### Tier 2: KernelService.create_session() — Per-Session Components

| Phase | Component | Config |
| --- | --- | --- |
| P1 | Per-session Bus | BusFactory.create_local_ordered() + TracingMiddleware |
| P2 | Per-session SessionState | SessionStateFactory.create_with_ports() |
| P3 | Per-session Fabric (real SSM) | FabricFactory with SessionStateReaderAdapter |
| P4 | Per-session Concierge | ConciergeFactory.create_with_ports() |
| P5 | Household hydration | bridge_client.query() or offline LOCAL COLD |
| P6 | Start session lifecycle | session_manager.start() |
| P7 | Register SessionInstance | runtime.sessions[session_id] |

### Dependency Graph (NO CIRCULAR DEPS — Clean DAG)
```
S1 → S2, S3, S4, S5, S6, S7
S2 → S3 (ModelHub for FabricGatewayAdapter)
S5 → S3, S4 (needs shared Fabric, Bridge)
S6 → S2, S3, S4 (needs ModelHub, Fabric, Bridge)
S6b → S5, S6

P1 → nothing
P2 → P1 (SessionBusAdapter)
P3 → P1, P2, S2, S3
P4 → P1, P2, P3, S2, S5
P5 → P4, S4
P6 → P2
P7 → all above
```

### Planner's State Port Fix
**SIM-D-38:** SnapshotStateReadAdapter reads from PlanRequest.context snapshot. No session-lock issue. ~15 lines.

### Error Handling: Phase Failure Recovery

| Phase | Failure | Recovery |
| --- | --- | --- |
| S1: Config | Invalid | FATAL |
| S2: ModelHub | Plugin fails | DEGRADED |
| S3: Shared Fabric | Registry scan fails | DEGRADED |
| S4: Bridge | K0 unreachable | OFFLINE (normal) |
| S5: Orchestrator | Factory fails | FATAL |
| S6: Planner | Factory fails | DEGRADED (CB_PLANNER opens) |
| P1-P4: Session | Any fails | SESSION FATAL, rollback |
| P5: Household | Bridge query fails | DEGRADED (LOCAL COLD) |

---

## STEP 10: INTEGRATION SMOKE TEST (PARTIAL)

### 11 FSM States
LISTENING, DISPATCHING, COMPANIONING, PROGRESSING, DELIVERING, CLARIFYING_USER, CLARIFYING_WORKER, CANCELLING, INTERRUPT_HANDLING, PROACTIVE_WAKE, WEAVING

### Complete Call Chain — "What's the weather?" (LOW Tier)
```
WebSocket → bus.publish(user.input)
  → FSM._on_user_input(LISTENING → DISPATCHING)
    → Phase 1.classify(text) → Phase1Result(tier=LOW)
    → FrontLock.try_deliver(...) → router.deliver(FRONT, enriched)
      → front_handler(envelope, model, ss, tools, ctx)
        → react_loop(tools=[10 Front tools], max_iterations=6):
          Iter 0: LLM → tool_call: recall_memory → MemoryResult
          Iter 1: LLM → tool_call: dispatch_task → TaskDispatch enqueued
          Iter 2: LLM → text: "Let me check..." (no tools, loop ends)
        → emit build_final_response → bus
      → bus.publish(response.final)
        → FSM._on_final_response(DISPATCHING → LISTENING)
          → emit turn.completed
          → IOutputPort.send(FinalResponseEvent) → client
```

### Critical Port Usage Findings
- **IInputPort.receive() is NEVER CALLED** — FSM subscribes to TOPIC_USER_INPUT. Transport publishes directly.
- **IClassificationPort.classify() is NEVER CALLED** — FSM uses Phase1Pipeline directly.
- **IOutputPort.send() NOT USED in main path** — Results flow via Bus events.

### 7 Type Mismatches Found
1. POC CapabilityRequest vs K1 CapabilityRequest
2. POC TaskEnvelope vs Production TaskEnvelope
3. Memory Writer IModelHubPort.chat() vs canonical execute()
4. FSM ComplexityTier enum vs Production str tier
5. POC CapabilityRequest.budget vs Production constraints dict
6. FSM calls orchestrator.handle_task() vs dispatch_port.dispatch_envelope()
7. Result delivery POC (direct return) vs Production (Bus event subscription)

---

## ALL GAPS SUMMARY (56 total)

**HIGH (13):** SIM-GAP-01, 03, 04, 05, 06, 24, 25, 26, 33, 34, 44, 49, 55
**MEDIUM (26):** SIM-GAP-02, 07, 08, 09, 14, 15, 21, 22, 27, 30, 31, 32, 36, 37, 38, 39, 43, 45, 46, 48, 50, 52, 53, 54, 56
**LOW (17):** SIM-GAP-10, 11, 12, 13, 16, 17, 18, 19, 20, 23, 28, 29, 35, 40, 41, 42, 47, 51

---

## ALL FLAGS SUMMARY (26 total)

Key flags:
- SIM-FLAG-01: POC bootstrap coupling (imports poc.k1_poc.main.boot)
- SIM-FLAG-02: Custom MetricsCollector parallel to OTel
- SIM-FLAG-03: IModelHubPort method mismatch
- SIM-FLAG-04: CapabilityRequest type collision
- SIM-FLAG-05: Any-typed wiring
- SIM-FLAG-07: Private adapters need extraction

---

## ALL DECISIONS SUMMARY (40 total)

| Range | Topic |
| --- | --- |
| SIM-D-01..05 | Architecture (per-session Bus, multi-session, trace IDs, sharing, threading) |
| SIM-D-06..08 | Ports (signatures match kernel.md, internal untouched, type bridging) |
| SIM-D-09..12 | Factory (ConciergeSession wrapper, 26-step sequence, test adapters, adapter extraction) |
| SIM-D-13..16 | Bus (creation ownership, ordered Bus, TracingMiddleware, sweep) |
| SIM-D-17..19 | SessionState (SSM IS IStatePort, lifecycle, factory mode) |
| SIM-D-20..22 | Fabric/ModelHub (Fabric IS IFabricPort, ModelHubFactory, shared ModelHub) |
| SIM-D-24..28 | Orchestrator/Planner (FabricOrchestratorAdapter, shared, phased bootstrap) |
| SIM-D-29..33 | Bridge (facade, shared, timing, offline fallbacks) |
| SIM-D-34..36 | Cross-Component (NullState, two Fabric instances, shared registry) |
| SIM-D-38..40 | Bootstrap Assembly (SnapshotStateAdapter, two-tier, failure strategy) |

---

## NEW ADAPTERS NEEDED (~550 lines total)

1. ModelHubGatewayAdapter (Fabric → ModelHub handle factory) — 30 lines
2. BusDeltaAdapter (Fabric agent deltas → Bus envelopes) — 20 lines
3. BridgeRecallAdapter (Concierge memory port) — 40 lines
4. BridgeCommandAdapter (Memory Writer) — 30 lines
5. ModelHubChatAdapter (Memory Writer collision fix) — 25 lines
6. BridgeClient facade — 80 lines
7. NullSessionStateReaderAdapter — 10 lines
8. NullDeltaBusAdapter — 10 lines
9. NullEventPortAdapter — 10 lines
10. SnapshotStateReadAdapter (Planner) — 15 lines
11. IMemoryPort Protocol — 15 lines
12. HouseholdProjection — 60 lines
13. FabricConnectionAdapter — 40 lines
14. TracingMiddleware (bus stamping) — 50 lines
15. SessionBusAdapter (per-session) — 30 lines

**Phase 2 (K0 integration):** IKernelQueryPort (~150 lines), IKernelSSEPort (~100 lines), bridging adapters (~100 lines)

---

## SHUTDOWN SEQUENCE (TWO-TIER)

### Session Shutdown (reverse order)
1. concierge.stop()
2. concierge_task.cancel()
3. session_fabric.shutdown()
4. session_manager.stop()
5. bus.close()
6. mailbox_router.close()
7. Remove SessionInstance

### Startup Shutdown (after all sessions)
1. Stop all sessions
2. orchestrator.shutdown()
3. planner.stop() + task.cancel()
4. model_hub.close()
5. shared_fabric.shutdown()
6. bridge_client.close()

---

## VALIDATION STATUS

**Aligned with:** kernel.md §7 (with two-tier amendment), §89 (ports), §3 (dependency graph)
**NOT aligned:** kernel.md §7 is single-session; IInputPort, IOutputPort, IClassificationPort unused in reality
