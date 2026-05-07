# K1 Wiring Whiteboard - Complete Extraction

**Source:** `D:\familyos\docs\whiteboard\k1_wiring_whiteboard.md` (~996 lines, 90KB)
**Date:** 2026-04-01
**Status:** Cross-reference complete, 15 gaps mapped, unified diagram created, 16 decisions locked

---

## 1. WHAT EXISTS TODAY (The 1150-line Monolith)

### bootstrap.py Current State
- **Location:** `k1/concierge/kernel/bootstrap.py` (~1,150 lines)
- **Function:** `start_kernel()` creates own infrastructure (Bus, Router, Mailboxes, SessionState, Fabric)
- **Problem:** Monolithic, creates ~17 dependencies, imports from `poc.k1_poc.main.boot()`
- **Goal:** Refactor into hexagonal `ConciergeFactory.create_with_ports()` matching kernel.md §4.5

### 17 Steps Currently Inside bootstrap.py
1. IBus + IMailboxRouter + Mailboxes (should come from kernel)
2. IModelHubPort (Gemini/Test) → from kernel via ILLMPort
3. SessionStateManager → from kernel via IStatePort
4. CapabilityRegistry (40 caps) → from kernel via IDispatchPort
5. K1 Fabric + POCMockBridgeAdapter → from kernel via IDispatchPort
6. LedgerWriter + InMemoryLedgerStore (INTERNAL, stays)
7. ConciergeController FSM (INTERNAL, stays)
8. ToolContext 11 fields (INTERNAL, stays)
9. ToolDispatchers front + back (INTERNAL, stays)
10. ExperienceLayer 6 components (INTERNAL, stays)
11. DeltaAggregator + DeltaApplicator (INTERNAL, stays)
12. HILCoordinator + SuspensionManager (INTERNAL, stays)
13. WeaveBatcher + WeavePolicy + UserActivityTracker (INTERNAL, stays)
14. OrchestratorStub + 3 inline adapters (INTERNAL, stays)
15. BackPool + BackTopicRouter (INTERNAL, stays)
16. DeadLetterConsumer (INTERNAL, stays)
17. Bus subscriptions + consumer task (INTERNAL, stays)

### 3 Inline Adapters in bootstrap.py
- `_FabricGatewayAdapter` → wraps POC bridge → IFabricGatewayPort
- `_StateReadAdapter` → wraps session_state → IStateReadPort
- `_DeltaEmitAdapter` → wraps aggregator+bus → IDeltaEmitPort

---

## 2. THE 8 HEXAGONAL PORTS (kernel.md §4.5)

| # | Port | Direction | Kernel Injects | Used For |
| --- | --- | --- | --- | --- |
| 1 | IInputPort | Inbound | WebSocketInputAdapter/TestInputAdapter | Receive user messages |
| 2 | IOutputPort | Outbound | SSEOutputAdapter/TestOutputAdapter | Send responses |
| 3 | IClassificationPort | Outbound | UltraBERTv4Adapter/MockClassificationAdapter | Phase 1 classification |
| 4 | ILLMPort | Outbound | ModelGatewayAdapter | LLM calls |
| 5 | IStatePort | Both | SessionKernelAdapter | Read/write SessionState |
| 6 | IDispatchPort | Outbound | FabricOrchestratorAdapter | Route tasks |
| 7 | IDeltaPort | Both | DeltaBusAdapter | Emit events + subscribe deltas |
| 8 | IMemoryPort | Outbound | BridgeRecallAdapter | K0 memory recall |

### Factory Signature
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

---

## 3. INTERNAL ARCHITECTURE (40K lines, ~130 files — stays inside factory)

| Subsystem | Folder | Key Class | Wired To |
| --- | --- | --- | --- |
| FSM | fsm/ | ConciergeController | Everything (12 states) |
| Front Actor | actors/ | front_handler() | ILLMPort, IStatePort, ToolDispatcher |
| Back Actor | actors/ | back_handler() | ILLMPort, ToolDispatcher |
| BackPool | actors/ | BackPool | Back Actor, CancellationTokens |
| ReadyQueue | actors/ | ReadyQueue | Dependency ordering |
| Front ToolDispatcher | tools/ | create_front_dispatcher() | IStatePort via ToolContext |
| Back ToolDispatcher | tools/ | create_back_dispatcher() | IDispatchPort via ToolContext |
| 16 Tool Implementations | tools/ | ToolContext(11 fields) | IStatePort, IDispatchPort, IMemoryPort |
| DynamicPromptBuilder | prompt/ | DynamicPromptBuilder | IStatePort (reads SS sections) |
| ReAct Loop | react/ | react_loop() | ILLMPort, ToolDispatcher |
| ExperienceLayer | experience/ | ExperienceLayer | IStatePort (reads), IDeltaPort (emits) |
| DeltaAggregator | delta/ | DeltaAggregator | IDeltaPort (flush output) |
| DeltaApplicator | delta/ | DeltaApplicator | IStatePort (writes) |
| HILCoordinator | protocols/ | HILCoordinator | IDeltaPort (emit events) |
| SuspensionManager | protocols/ | SuspensionManager | IDeltaPort (emit events) |
| OrchestratorStub | orchestrator/ | OrchestratorStub | IDispatchPort (via adapters) |
| LedgerWriter | ledger/ | LedgerWriter | Internal storage |
| CrashRecovery | ledger/ | CrashRecoveryOrchestrator | Ledger + FSM |
| DeadLetterConsumer | fsm/ | DeadLetterConsumer | IDeltaPort (bus) |
| MetricsCollector | obs/ | MetricsCollector | IDeltaPort (emit metrics) |

---

## 4. PORT-TO-INTERNAL WIRING

### IInputPort → receives user messages
```
IInputPort.receive() → FrontLock.try_deliver(envelope) → ConciergeController dispatches to front_handler
```

### IOutputPort → sends responses
```
front_handler produces text → bus.publish(response.stream/final) → IOutputPort.send(OutputEvent)
```

### IClassificationPort → Phase 1 classification
```
User message → IClassificationPort.classify(text) → ClassificationResult
→ ConciergeController uses for FSM transition + tier routing
```

### ILLMPort → LLM calls
```
react_loop → ILLMPort.execute(HubRequest) → HubResponse (text, tool_calls, tokens)
```

### IStatePort → SessionState read/write
```
READS: DynamicPromptBuilder, front_handler, WeavePolicy
WRITES: Front tools via ToolContext.writer_port, DeltaApplicator
```

### IDispatchPort → task execution
```
dispatch_task tool → TaskEnvelope by tier:
  LOW → Fabric direct (CapabilityRequest → CapabilityResult)
  MED → OrchestratorStub (max 2 Fabric calls)
  HIGH → Orchestrator (future)
Back tools: invoke_capability, spawn_via_fabric → IDispatchPort.dispatch_direct()
```

### IDeltaPort → events & deltas
```
EMIT: DeltaAggregator.flush() → publish(envelope)
      HILCoordinator, MetricsCollector → publish events
      45 envelope builders route through IDeltaPort
SUBSCRIBE: ConciergeController subscribes to 30+ SUBSCRIBED_TOPICS
           DeadLetterConsumer subscribes to dead-letter topic
```

### IMemoryPort → K0 recall
```
execute_recall_memory tool → IMemoryPort.recall(query, types, max_results) → list[dict]
```

---

## 5. EXISTING INTERNAL PORTS (NOT the 8 hexagonal ports)

| Port File | Protocol | Used By | Maps To |
| --- | --- | --- | --- |
| orchestrator/ports.py | IFabricGatewayPort | OrchestratorStub | Internal (wraps IDispatchPort) |
| orchestrator/ports.py | IStateReadPort | OrchestratorStub | Internal (wraps IStatePort) |
| orchestrator/ports.py | IDeltaEmitPort | OrchestratorStub | Internal (wraps IDeltaPort) |
| llm/ports.py | IConciergeModelPort | GeminiConciergeAdapter | Internal (wraps ILLMPort) |
| fabric/ports.py | IFabricPort | Back tools, OrchestratorStub | Internal (wraps IDispatchPort) |

---

## 6. PORT LAYER ARCHITECTURE

```
KERNEL (creates adapters)
  ├── IInputPort, IOutputPort, IClassificationPort
  ├── ILLMPort, IStatePort, IDispatchPort
  ├── IDeltaPort, IMemoryPort
        ↓
    FACTORY WIRING (internal)
        ↓
  INTERNAL SUBSYSTEMS
  ├── FSM (ConciergeController)
  ├── Front/Back Actor, ToolContext
  ├── OrchestratorStub (uses 3 internal ports)
  ├── DeltaAggregator → flush → IDeltaPort
  ├── ExperienceLayer → IDeltaPort
  └── ...
```

---

## 7. DECISION LOG (D-1 to D-16)

- **D-1:** IInputPort — Higher-level push API, internal receive() via FrontLock
- **D-2:** IOutputPort — Dedicated port with polymorphic send(OutputEvent) → DeliveryReceipt
- **D-3:** UltraBERT — New IClassificationPort (swappable classifiers)
- **D-4:** Consumer loop — Concierge owns start()/stop(), kernel spawns via asyncio.create_task()
- **D-5:** Config — Standalone ConciergeConfig (frozen dataclass, from_legacy(), with_overrides())
- **D-6:** BackPool — Concierge owns via registered background tasks pattern
- **D-7:** IOutputPort signature (G-9) — kernel.md wins, single polymorphic send()
- **D-8:** IInputPort signature (G-10) — Two layers: Port=pull receive(), Adapter=push send_user_message()
- **D-9:** Invariant enforcement — 21 invariants (INV-01..21), factory validates at creation
- **D-10:** Circuit breaker ownership — Concierge owns all 7 CBs
- **D-11:** Lifecycle phases — 6 phases: init, turn_start, turn_end, turn_end_abbreviated, shutdown, crash_recovery
- **D-12:** Error recovery — 3 levels: RECOVERABLE, DEGRADED, TERMINAL
- **D-13:** Internal services — ConciergeServices dataclass (typed registry)
- **D-14:** Family Profile — Thin (identity, safety, access, device, governance only)
- **D-15:** K1 family context — Boot-time hydrate, never per-turn K0 calls
- **D-16:** K0 deep-query — Via IMemoryPort.recall() for deep patterns

---

## 8. FAMILY SELF-MODEL & DATA OWNERSHIP

### Separation Principle: Profile knows WHO. Tools know WHAT. K0 knows WHY/WHEN/HOW.

| Category | Owner | Storage | Changes |
| --- | --- | --- | --- |
| Identity & Safety | Family Profile | K1 local (hydrated from K0) | Rarely |
| Operational Data | M11 MCP Tools (44 contracts) | Per-tool SQLite | Daily |
| Learned Knowledge | K0 Memory Layers | K0 PostgreSQL | Continuously |
| Session Persona | K1 PersonaSection | SessionState WARM | Per-session |

### Thin Family Profile Schema
- **Per Member:** member_id, display_name, nicknames, DOB, gender, pronouns, role, languages, photo_ref, allergies, chronic_conditions, blood_type, emergency_contact, access_level, interface_preference, content_filtering, notification_tolerance, timezone, preferred_language
- **Per Device:** device_id, owner_member_id, device_type, label, access_level_override, is_shared
- **Per Household:** household_id, family_name, address, timezone, governance (rules, authorities, sharing_policy)

---

## 9. THE 15 GAPS (All Resolved)

### CRITICAL: G-9 (IOutputPort signature), G-10 (IInputPort clarification) — RESOLVED
### HIGH: G-1 (21 Invariants), G-2 (7 CBs), G-4 (6 Lifecycle Phases), G-8 (Error Recovery), G-15 (Port bridging) — RESOLVED
### MEDIUM: G-3 (Internal Services), G-6 (Performance), G-7 (ReactLoopScratchpad) — RESOLVED
### LOW: G-5, G-11, G-12, G-13, G-14 — DEFERRED or OK

---

## 10. NEW FILES TO CREATE

### Phase C1: Port Definitions
- `k1/concierge/ports.py` — 8 Protocol definitions (~200 lines)

### Phase C2: Factory Skeleton
- `k1/concierge/factory.py` — ConciergeFactory.create_with_ports() (~400 lines)

### Phase C3: Production Adapters
- `k1/concierge/adapters/ws_input.py` (~50 lines)
- `k1/concierge/adapters/sse_output.py` (~50 lines)
- `k1/concierge/adapters/ultrabert.py` (~50 lines)
- `k1/concierge/adapters/model_gateway.py` (~80 lines)
- `k1/concierge/adapters/session_kernel.py` (~100 lines)
- `k1/concierge/adapters/fabric_orchestrator.py` (~150 lines)
- `k1/concierge/adapters/delta_bus.py` (~80 lines)
- `k1/concierge/adapters/bridge_recall.py` (~60 lines)
- `k1/concierge/adapters/test_adapters.py` (~200 lines)

### Phase C4: Bridge from Old to New
- `start_kernel()` calls `ConciergeFactory.create_with_ports()` internally

### Phase C5: Kernel Integration
- `k1/kernel/bootstrap.py` Phase 6 calls `ConciergeFactory.create_with_ports()`

---

## 11. 21 INVARIANTS (INV-01..21)

### Ownership (INV-01..04)
- Single Writer (ADR-0017), MutationGuard preflight, Phase 1 before Phase 2, Orch/Planner NEVER write SS

### Safety (INV-05..07)
- Safety Gate evaluates FIRST, CRISIS bypasses FSM, safety_band written before routing

### Rate Limits (INV-08..12)
- 20 tools/turn, 3 clarification rounds/intent, 50 output queue, 3 workflow depth, 1 concurrent turn

### Timing (INV-13..14)
- FSM transition ≤1ms (no I/O), delta aggregation = 500ms fixed

### Structural (INV-15..17)
- All output through OUTPUT_CHANNEL, internal services call ports (never external), single FSM

### Token Budget (INV-18..21)
- 128K context window, 150 tok intent ack, 200 tok prelim ack, 300 tok clarification

---

## 12. CIRCUIT BREAKERS (7 total)

| CB | Owner Adapter | Threshold | On OPEN |
| --- | --- | --- | --- |
| CB_SSE | SSEOutputAdapter | 5s reconnect, 3/min | Polling mode |
| CB_MODEL | UltraBERTv4Adapter + ModelGatewayAdapter | varies | Heuristic fallback / Canned |
| CB_SESSIONSTATE | SessionKernelAdapter | 100ms, 10/min | Stale cached read |
| CB_ORCHESTRATOR | FabricOrchestratorAdapter | 60s, 2/min | Degrade HIGH→MED |
| CB_PLANNER | FabricOrchestratorAdapter | 45s, 2/min | Skip planning |
| CB_FABRIC | FabricOrchestratorAdapter | 30s, 5/min | Tool unavailable |
| CB_MCP | FabricOrchestratorAdapter | 10s, 3/min | Tool offline |

---

## 13. LIFECYCLE PHASES (6)

| Phase | When | Key Actions |
| --- | --- | --- |
| init | Session start | Create 9 services, connect 8 ports, restore state, load persona, init 7 CBs, FSM→LISTENING |
| turn_start | User input | Acquire Single Writer lock, increment turn_seq, read HOT snapshot, allocate tier budget |
| turn_end | Normal completion | Flush OutputManager, append history, update telemetry, release lock, checkpoint, emit turn.complete |
| turn_end_abbreviated | Interrupt | Cancel in-flight, flush partial, record INTERRUPTED, release lock, checkpoint LOCAL COLD |
| shutdown | Graceful stop | Close IInputPort, wait active turn (30s), flush aggregators, disconnect ports LIFO |
| crash_recovery | Ungraceful restart | Bootstrap, detect via turn_lock, rollback, reconcile outbox, restore from LOCAL COLD |

---

## 14. INTERNAL SERVICES (~585 tests)

| Service | Tests | Responsibility |
| --- | --- | --- |
| FSMController | ~60 | State transitions, experience ticks, interrupt routing |
| TurnProcessor | ~90 | start_turn(), execute_phase1(), route_dispatch(), execute_phase2(), end_turn() |
| IntentProcessor | ~110 | Safety → Hypothesis → TimeResolver → ContextInference → SanityArbiter → Uncertainty |
| ComplexityRouter | ~45 | 5-factor scoring |
| ToolDispatcher | ~80 | dispatch(), get_buffered_results(). Enforces allowlist |
| OutputManager | ~55 | enqueue(), deliver_next(), flush(). 9 event types, 3 priorities |
| DeltaAggregator | ~50 | 500ms window, LWW merge, dedup |
| ClarificationTracker | ~40 | track_round(), max_reached(), escalate() |
| ContextAssembler | ~55 | assemble(), track_usage() |

---

## 15. ERROR RECOVERY MODEL

| Severity | Behavior | Examples |
| --- | --- | --- |
| RECOVERABLE | Retry/fallback in same phase | MutationGuard reject → skip write. Delta fail → log + skip. |
| DEGRADED | Continue with partial | LLM CB OPEN → canned response. SS timeout → stale cache. |
| TERMINAL | Error response | 3 consecutive LLM failures. All degradation exhausted. |

**Tier Degradation Cascade:** HIGH (CB_PLANNER open) → MED (CB_ORCH open) → LOW (CB_FABRIC open) → Canned

---

## 16. PRODUCTION READINESS AUDIT

| Component | Factory | Ports | Tests | Verdict |
| --- | --- | --- | --- | --- |
| Bus | ✅ | ✅ | 22 files | ✅ PRODUCTION READY |
| SessionState | ✅ | ✅ | 73 files | ✅ PRODUCTION READY |
| Fabric | ✅ | ✅ | 4,595 | ✅ PRODUCTION READY |
| ModelHub | ✅ | ✅ | 958 | ✅ PRODUCTION READY |
| Orchestrator | ✅ | ✅ | 1,914 | ✅ PRODUCTION READY |
| Planner | ✅ | ✅ | 1,923 | ✅ PRODUCTION READY |
| Concierge | ❌ | ❌ | 63 | ❌ NEEDS WORK |
| Kernel Bootstrap | N/A | N/A | 0 | ❌ NEEDS WORK |

**Total tests across 6 ready components:** ~9,485

---

## 17. THREE WORK STREAMS

**WS-1: CONCIERGE HEXAGONAL SHELL** (C1→C3) — ~950 lines
- C1: k1/concierge/ports.py (8 Protocols)
- C2: k1/concierge/factory.py
- C3: k1/concierge/adapters/ (8 prod + test bundle)

**WS-2: BRIDGE CLIENT & HOUSEHOLD** — ~400 lines
- IBridgeClient Protocol + StubBridgeClient + HttpBridgeClient
- HouseholdProjection + hydrate_household()
- bridge_recall.py adapter

**WS-3: CENTRAL KERNEL BOOTSTRAP** — ~700 lines
- KernelRuntime + KernelConfig + ConfigLoader
- 8-phase bootstrap (Phases 1-8)

**TOTAL: ~2,050 lines across ~15 files**

---

## 18. 33 ISSUES ACROSS 8 EPICS

### MS-1: Concierge Hexagonal Shell
- E-1.1: Port Definitions (4 issues)
- E-1.2: Test Adapters (3 issues)
- E-1.3: Production Adapters (7 issues)
- E-1.4: Concierge Factory (4 issues)

### MS-2: Bridge Client & Household
- E-2.1: Bridge Client (3 issues)
- E-2.2: Household Projection + Memory Adapter (3 issues)

### MS-3: Central Kernel Bootstrap
- E-3.1: Kernel Runtime & Config (2 issues)
- E-3.2: 8-Phase Bootstrap (4 issues)
- E-3.3: Kernel Integration Tests (3 issues)

**Total: 33 issues, 8 epics, 3 milestones**
