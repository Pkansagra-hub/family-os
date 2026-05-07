# MemoryWriter — Cross-Reference with K1 Actors & K0 Bridge

> Generated: 2026-04-14 · Scope: How MemoryWriter bridges K0↔K1 and connects to every actor

---

## 1. Architecture Diagram Context

Source: `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd`

**Memory Writer System** (lines 1133–1140):

```text
MEMORY_WRITER_SYSTEM subgraph:
  MEMORY_WRITER_AGENTS  — "LLM-Based Memory Writers, Observe LLM Conversations,
                           Prepare K0 Command Envelopes"
  STATE_DELTA_EMITTER   — "Batch Window: 250ms"
  DELTA_AGGREGATOR      — "Time-Window Batching"
```

**Data flow** (lines 1710–1720):

```text
DELTA_BUS → "Session Deltas" → MEMORY_WRITER_AGENTS
MEMORY_WRITER_AGENTS → "Agent Deltas" → DELTA_AGGREGATOR
DELTA_AGGREGATOR → "batch to K0" → K0_CMD
K0_CMD → submit_command() → PORT_CMD → BUS_DISPATCH → P02 → k0.episodic.written
```

---

## 2. The K0↔K1 Bridge — How Memory Flows

### 2.1 WRITE Path: K1 → K0 (MemoryWriter)

```text
Conversation Turn
  → Concierge emits turn.complete.v1
    → TurnDispatcher picks up event
      → 5-stage MW pipeline
        → Stage 3: LLM extracts MemoryAtoms (max 6, max 50 words each)
        → Stage 4: EnvelopeBuilder packs atoms into K0 command envelopes
        → Stage 5: BatchEmitter.emit()
          → IBridgeCommandPort.submit_batch(envelopes)
            → BridgeCommandAdapter → Bridge.KernelCommandPort.submit_command_batch()
              → Bridge serializes → K0 Command Port
                → K0 Bus Dispatch → topic match → P02 Episodic Pipeline
                  → UltraBERT validation (MW-11: NOT in K1)
                  → WAL write → k0.episodic.written
                  → P03 consolidation → k0.memory.consolidated
                  → SSE → Bridge SSE → K1 EventBus
```

**Topic**: `memory.delta`
**Schema**: `schema://memory.delta` (maps to `memory_atom.v2.schema.json`)
**Actor**: `k1.memory_writer`
**Band**: From `control_context.safety_band` (GREEN/AMBER/RED)

### 2.2 READ Path: K0 → K1 (recall_memory)

```text
Concierge Front/Back Actor (tool call)
  → recall_memory(query, memory_types, max_results)
    → IMemoryPort.recall(query, memory_types, max_results)
      → RecallMemoryAdapter wraps recall_fn closure
        → _recall_memory(query, memory_types, max_results) [built by bootstrap._build_recall_fn()]
          → Bridge.query("memory.recall", {...})
            → K0 Query Port → FAISS vector search + WAL episodic scan
              → Returns list[dict] of matching memories
```

**Current wiring gap**: `memory=None` in `PortBundle` → `_null_recall` returns empty list. `RecallMemoryAdapter` exists but `_build_recall_fn()` not yet integrated.

### 2.3 The Symmetry

| Direction | K1 Actor | Interface | Bridge Method | K0 Pipeline | Storage |
| --- | --- | --- | --- | --- | --- |
| **WRITE** (K1→K0) | MemoryWriter | `IBridgeCommandPort.submit_batch()` | `submit_command_batch()` | P02 → P03 | WAL + FAISS |
| **READ** (K0→K1) | Concierge tools | `IMemoryPort.recall()` | `query("memory.recall")` | Vector search + WAL scan | WAL + FAISS |

MemoryWriter **writes** what the user said. `recall_memory` **reads** what was written. They are the two halves of the K0↔K1 memory loop.

---

## 3. Consumer × MemoryWriter Integration Map

### 3.1 Concierge → MemoryWriter (Trigger)

| Aspect | Detail |
| --- | --- |
| **Trigger** | Concierge emits `turn.complete.v1` after every conversation turn |
| **Payload** | `TurnCompletePayload` with user_message, assistant_response, turn metadata, temporal/spatial parse results |
| **Direction** | Concierge → K1 Bus → TurnDispatcher → MW Pipeline |
| **Latency** | Background (BACKGROUND priority), non-blocking to user |
| **Wiring** | Concierge publishes via session bus; MW subscribes via `EventSubscriptionAdapter` wrapping `FabricBusAdapter(session_bus)` |

### 3.2 SessionState → MemoryWriter (Context Read)

| Aspect | Detail |
| --- | --- |
| **Interface** | `ISessionReadPort.snapshot_all(exclude=skip_sections)` |
| **Direction** | MW reads 13 SS sections (read-only, MW-01) |
| **Latency** | <1ms P99 (MW-02) |
| **Sections** | history_active, beliefs_active, affective_now, affective_baseline, scoreboard, task_state, control, persona, ifl, narrative_active, meta |
| **Wiring** | `SessionReadAdapter(manager=ssm)` — wraps per-session `SessionStateManager` |
| **Race fix** | Payload-first for temporal/spatial fields (fixes T7 where Concierge clears SS before MW reads) |

### 3.3 ModelHub → MemoryWriter (LLM Extraction)

| Aspect | Detail |
| --- | --- |
| **Interface** | MW's `IModelHubPort.chat(messages, budget_tokens=2000, model_hint="cheapest")` |
| **Anti-corruption** | `ModelHubAdapter` translates `chat()` → `execute(HubRequest{CHAT, BACKGROUND, 60s timeout})` |
| **Token budget** | 2000 (MW-06) — ~1K in / ~1K out per architecture diagram |
| **Priority** | `BACKGROUND` (60s timeout, lowest priority) |
| **Consumer ID** | `"memory_writer"` |
| **Circuit breaker** | 3 failures → OPEN for 30s; separate from ModelHub's own CB |
| **Wiring** | `ModelHubAdapter(hub=self._model_hub)` — wraps kernel's shared `_model_hub` reference |

### 3.4 Bridge → MemoryWriter (K0 Output)

| Aspect | Detail |
| --- | --- |
| **Interface** | `IBridgeCommandPort.submit_batch(envelopes)` |
| **Invariant** | MW-03: Bridge is the ONLY K0 output path. No direct DB, no HTTP, no other port |
| **Topic** | `memory.delta` → K0 P02 Episodic Pipeline |
| **Envelope** | 34+ field body, headers with `cognitive_trace_id` (MW-10) |
| **Privacy** | PrivacyEnforcer strips/generalizes fields based on safety band |
| **Wiring** | `BridgeCommandAdapter(command_port=self._bridge.get_client())` |

### 3.5 Fabric → MemoryWriter (Registration)

| Aspect | Detail |
| --- | --- |
| **Interface** | `MemoryWriterFabricRegistration.create_for_session()` |
| **Purpose** | Fabric can create MW instances for agent-scoped memory extraction |
| **Current wiring** | Kernel service.py creates MW directly (P5 phase), NOT via Fabric registration |

### 3.6 Orchestrator → MemoryWriter (Indirect)

| Aspect | Detail |
| --- | --- |
| **Relationship** | Orchestrator does NOT call MW directly |
| **Indirect path** | Orchestrator manages tasks → tasks produce turns → Concierge emits `turn.complete.v1` → MW activates |

### 3.7 Planner → MemoryWriter (None)

| Aspect | Detail |
| --- | --- |
| **Relationship** | No direct dependency. Planner does not emit `turn.complete.v1` |
| **Future possibility** | Planner's planning turns could trigger MW extraction if planner emitted turn events |

---

## 4. Kernel Bootstrap Wiring (service.py)

### 4.1 Per-Session MW Creation (P5 Phase)

From [k1/kernel/service.py](k1/kernel/service.py#L1245):

```python
# P5: MemoryWriter (per-session)
mw_config = MWConfig()
mw_session_read = SessionReadAdapter(manager=ssm)           # wraps per-session SSM
mw_model_hub = self._create_memory_writer_hub_adapter()      # ModelHubAdapter(hub=self._model_hub)
mw_bridge = BridgeCommandAdapter(command_port=self._bridge.get_client())
mw_bus_adapter = FabricBusAdapter(session_bus)
mw_events = MWEventSubscriptionAdapter(bus_adapter=mw_bus_adapter)
mw_cb = MWCircuitBreaker(
    failure_threshold=mw_config.circuit_breaker_failure_threshold,
    recovery_probe_seconds=mw_config.circuit_breaker_recovery_probe_seconds,
)
mw_health = HealthAdapter(
    circuit_breaker=mw_cb,
    get_pending_count=lambda: 0,
    get_started=lambda: False,      # BUG: always False, not updated after start
)
session_memory_writer = MemoryWriterFactory.create(
    session_read_port=mw_session_read,
    model_hub_port=mw_model_hub,
    bridge_command_port=mw_bridge,
    event_subscription_port=mw_events,
    health_port=mw_health,
    config=mw_config,
)
await session_memory_writer.start()
```

### 4.2 Adapter Chain (anti-corruption layer)

```text
MemoryWriterAgent
  → MW.IModelHubPort.chat(messages, budget=2000, hint="cheapest")
    → ModelHubAdapter.chat()
      → Translate: messages → K1 Message[], build ChatPayload, HubRequest
      → K1.IModelHubPort.execute(HubRequest{CHAT, BACKGROUND, 60s})
        → ModelHub 9-step pipeline → LLM provider
      → Translate: HubResponse → ChatResponse
    → return ChatResponse
```

This anti-corruption layer is critical: MW defines its OWN `IModelHubPort` (with `chat()` method) that is **different** from K1 ModelHub's `IModelHubPort` (with `execute()` method). The `ModelHubAdapter` bridges the two.

### 4.3 Session Lifecycle

| Phase | Action | Method |
| --- | --- | --- |
| Create (P5) | Wire all adapters → `MemoryWriterFactory.create()` → `service.start()` | `_create_session_tier2()` |
| Run | TurnDispatcher subscribes to `turn.complete.v1`, processes turns | Event-driven |
| Destroy | `session.memory_writer.stop()` (reverse P5, before P4/P3/P2/P1) | `destroy_session()` |

Destruction order: P7 → P6 → **P5 MW** → P4 Concierge → P3 Fabric → P2 SSM → P1 Bus

---

## 5. recall_memory Tool — The Read Side

### 5.1 Tool Definition

From architecture diagram (line 541):

```text
TOOL_RECALL_MEMORY["recall_memory()<br/>K0 Long-Term Memory Query"]
```

Used by: Concierge Front Actor, Concierge Back Actor, Fabric agents (via IKernelQueryPort)

### 5.2 Interface

**IMemoryPort Protocol** (Concierge-side):

| Method | Signature | Returns |
| --- | --- | --- |
| `recall` | `async (query: str, memory_types: list[str] \| None, max_results: int = 5) → list[dict]` | Memory results from K0 |

**RecallMemoryAdapter** (production):

```python
class RecallMemoryAdapter:
    def __init__(self, recall_fn: Callable[..., Any]) -> None
    async def recall(self, query, memory_types=None, max_results=5) -> list[dict]:
        return await self._recall_fn(query, memory_types=memory_types, max_results=max_results)
```

### 5.3 Data Flow

```text
recall_memory() tool
  → IMemoryPort.recall(query, types, max)
    → RecallMemoryAdapter → _recall_memory closure
      → Bridge.query("memory.recall", {query, types, max})
        → K0: WAL_DRIVER (episodic) + VECTOR_DRIVER (semantic FAISS)
          → Returns recall bundle
  → CAPABILITY_CONTEXT_BUILDER → inject into LLM context
```

### 5.4 Current Wiring Status

```python
# k1/kernel/service.py — P4 Concierge wiring
port_bundle = PortBundle(
    ...
    memory=None,  # NOT WIRED — _null_recall returns []
)
```

The `RecallMemoryAdapter` class exists and is production-ready. The `_build_recall_fn()` closure exists in backup bootstrap files. The gap is wiring them together in the current kernel service.

---

## 6. The Full Memory Loop

```text
┌──────────────────────────────────────────────────────────────────┐
│                         K1 (Cognitive)                           │
│                                                                  │
│   User speaks → Concierge processes → emits turn.complete.v1     │
│                    │                         │                   │
│                    │                         ▼                   │
│                    │              MemoryWriter Pipeline           │
│                    │              (5 stages, LLM extraction)      │
│                    │                         │                   │
│                    │                         ▼                   │
│                    │              IBridgeCommandPort              │
│                    │              submit_batch(envelopes)         │
│                    │                         │                   │
│                    ▼                         │                   │
│           recall_memory() tool               │                   │
│           IMemoryPort.recall()               │                   │
│                    │                         │                   │
└────────────────────┼─────────────────────────┼───────────────────┘
                     │                         │
                     │        BRIDGE           │
                     │                         │
┌────────────────────┼─────────────────────────┼───────────────────┐
│                    │         K0 (Storage)     │                   │
│                    │                         ▼                   │
│                    │              P02 Episodic Pipeline           │
│                    │              UltraBERT validation            │
│                    │              WAL write                       │
│                    │              P03 Consolidation               │
│                    │              FAISS indexing                   │
│                    │                         │                   │
│                    ▼                         │                   │
│           WAL + FAISS vector search ◄────────┘                   │
│           (query port)                                           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

Write: K1 → Bridge → K0 P02 → WAL + FAISS
Read:  K0 WAL + FAISS → Bridge → K1 recall_memory
```

---

## 7. Bus Topic Dependencies

### 7.1 Topics MemoryWriter CONSUMES (1)

| Topic | Publisher | Handler |
| --- | --- | --- |
| `turn.complete.v1` | Concierge (after each turn) | `TurnDispatcher._on_turn_complete()` |

### 7.2 Topics MemoryWriter PRODUCES (5)

| Topic | Consumer(s) |
| --- | --- |
| `k1.mw.filter.decision.v1` | Telemetry, debugging |
| `k1.mw.extraction.complete.v1` | Telemetry, cost tracking |
| `k1.mw.batch.submitted.v1` | Telemetry, Bridge monitoring |
| `k1.mw.pipeline.error.v1` | Supervision, Alerts |
| `k1.mw.circuit.open.v1` | Supervision, Health dashboard |

### 7.3 K0 Topics (via Bridge)

| Topic | Direction | Pipeline |
| --- | --- | --- |
| `memory.delta` | K1 → K0 | MW envelope → Bridge → P02 Episodic → WAL |
| `k0.episodic.written` | K0 → K1 (SSE) | P02 completion event |
| `k0.memory.consolidated` | K0 → K1 (SSE) | P03 consolidation event |

---

## 8. Cross-Reference with Prior Doc Series

| Doc | Component | Relationship to MemoryWriter |
| --- | --- | --- |
| 14–15 | **Orchestrator** | No direct dependency — orchestrates actors that produce turns triggering MW |
| 15_planner | **Planner** | No direct dependency — planner turns don't trigger MW |
| 16–17 | **Fabric** | `MemoryWriterFabricRegistration` for agent-scoped MW; `FabricBusAdapter` used for MW event subscription |
| 18–19 | **SessionState** | MW reads 13 sections (MW-01 read-only, MW-02 <1ms). SS provides context for LLM extraction |
| 20–21 | **Concierge** | PRIMARY trigger — emits `turn.complete.v1`. Also owns `recall_memory` tool (read side) |
| 22–23 | **ModelHub** | MW is a BACKGROUND consumer via `ModelHubAdapter` anti-corruption layer. 2000 token budget, cheapest model |

---

## 9. Adapter Integration Matrix

| MW Adapter | External System | Direction | Port |
| --- | --- | --- | --- |
| `SessionReadAdapter` | **SessionState** (per-session SSM) | IN (read) | `ISessionReadPort` |
| `ModelHubAdapter` | **ModelHub** (kernel shared) | IN (LLM calls) | MW `IModelHubPort` → K1 `IModelHubPort` |
| `BridgeCommandAdapter` | **Bridge** → K0 | OUT (write) | `IBridgeCommandPort` |
| `EventSubscriptionAdapter` | **K1 Bus** (per-session) | IN (subscribe) + OUT (publish) | `IEventSubscriptionPort` |
| `HealthAdapter` | **Internal** (CB + state) | OUT (health) | `IHealthPort` |

---

## 10. Dual-Path Analysis: Write vs Read

| Aspect | Write Path (MemoryWriter) | Read Path (recall_memory) |
| --- | --- | --- |
| **K1 Owner** | MemoryWriter module | Concierge (tool) |
| **Trigger** | `turn.complete.v1` event | LLM tool call |
| **Processing** | 5-stage pipeline + LLM extraction | Direct Bridge query |
| **K0 Entry** | `submit_command_batch()` → P02 | `query("memory.recall")` |
| **K0 Pipeline** | P02 → UltraBERT → WAL → P03 → FAISS | WAL scan + FAISS vector search |
| **Latency** | Background (async, 250ms batch window) | Synchronous (tool call blocks) |
| **LLM Cost** | 2000 tokens per turn (MW-06) | Zero (K0 does the search) |
| **Wiring Status** | ✅ Fully wired in kernel P5 | ❌ `memory=None` → `_null_recall` returns `[]` |

---

## 11. Gaps & Migration Priorities

| # | Gap | Severity | Impact | Resolution |
| --- | --- | --- | --- | --- |
| 1 | **recall_memory not wired** | P1 | Concierge cannot recall memories from K0. The write path works but the read path returns `[]` | Wire `RecallMemoryAdapter(_build_recall_fn(bridge))` into `PortBundle.memory` |
| 2 | **HealthAdapter get_started lambda** | P3 | `get_started=lambda: False` in kernel — never reflects actual MW state | Use forward-reference pattern from `FabricRegistration` |
| 3 | **Accumulation Gate missing** | P3 | Architecture diagram shows Stage 1B with 6 triggers (T1-T6) for batching turns before extraction. Currently each turn dispatched individually | Implement accumulation gate for multi-turn context windows |
| 4 | **PlaceResolver empty** | P3 | `PlaceResolver([])` — no location entities. All place resolution returns `None` | Load entities from SS or Bridge at session start |
| 5 | **UltraBERT in K0 only** | Info | MW-11 enforced: validation happens in K0 P02, not K1. MW sends raw atoms — K0 validates | Design is correct, no action needed |

---

## 12. Summary

MemoryWriter is the **write half** of the K0↔K1 memory bridge. It observes every conversation turn, uses a budget-constrained LLM to extract structured MemoryAtoms (max 6 per turn, max 50 words each), and submits them to K0 via the Bridge's command port. K0's P02 pipeline validates with UltraBERT and stores in WAL + FAISS.

The **read half** is the `recall_memory` tool owned by Concierge, which queries K0 via Bridge. Both paths exist in code but only the write path is fully wired — the read path returns `[]` because `memory=None` in the kernel's `PortBundle`.

**Priority**: Wire `recall_memory` to close the memory loop. Without it, the system writes memories but can never read them back.
