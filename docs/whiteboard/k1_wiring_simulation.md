# K1 Kernel Wiring Simulation Plan

> **Purpose:** Step-by-step simulation of building a production kernel, grounded in real codebase.
> **Method:** Each step → read real code → discover gaps → flag blockers → decide → move forward.
> **Date:** 2026-04-02
> **Companion:** `k1_wiring_whiteboard.md` (audit + milestones), `kernel.md` (spec)

---

## GROUND RULES

1. Every step reads real code before deciding anything
2. If something is missing we STATE it with a gap ID (SIM-GAP-xx)
3. If existing code makes integration hard we FLAG it (SIM-FLAG-xx)
4. If a design decision is needed we RECORD it (SIM-D-xx)
5. We do NOT skip problems — we surface them
6. Each step ends with a VERDICT: proceed / blocked / needs-decision

---

## SIMULATION STEPS

### STEP 1 — Kernel Service Wrapper (Multi-Session, HA, Threading)

> **Status:** SIMULATED — 5 decisions made, 5 gaps found, 2 flags raised
> **Date:** 2026-04-02

**Question:** The kernel today is `start_kernel() → one KernelRuntime → one session`. Production needs: multiple concurrent sessions, session lifecycle (create/timeout/evict), thread safety, health checks. How do we design the `KernelService` wrapper?

#### 1.1 What We Read

- `k1/concierge/kernel/bootstrap.py` — current single-session monolith
- `k1/bus/factory.py` — is Bus shared or per-session?
- `k1/bus/envelope/envelope.py` — envelope header fields (session_id, cognitive_trace_id, request_id)
- `k1/bus/middleware/tracing.py` — OTel span creation per envelope
- `k1/concierge/actors/back_pool.py` — already has `max_concurrent_per_session` (anticipates multi-session)
- `k1/concierge/bus/builders.py` — envelope builder functions
- `k1/sessionstate/factory.py` — creates per-call (good for per-session)
- `k1/concierge/delta/session_delta.py` — delta pipeline structure
- `k1/concierge/ledger/writer.py` — session-scoped ledger
- `k1/concierge/obs/metrics.py` — custom MetricsCollector (not OTel)
- `k1/memory_writer/` — MW-10 invariant (cognitive_trace_id on every bridge envelope)
- `k0/obs/tracing.py` — K0 OTel stack with TracerFactory + cognitive_trace_id baggage
- `bridge/core/envelope_builder.py` — trace_id field on bridge envelopes
- kernel.md Q-02 (session ownership), Q-06 (shared bus)

#### 1.2 What the Code Says TODAY

**Single-session reality:**

- `start_kernel()` creates ONE of everything — 1 Bus, 1 FSM, 1 SessionState, 1 LedgerWriter, 1 DeltaAggregator
- Session ID generated at boot: `k-{uuid4_hex[:8]}`
- No session registry, no session pool, no HTTP/WS server

**But multi-session is ANTICIPATED in two places:**

- `BackPool.max_concurrent_per_session = 2` — already tracks `session_id` per worker slot
- SessionState S-11: "96KB is per-session. Multiple sessions each get full 96KB"

**The envelope already carries what we need (first-class header fields):**

```
Envelope (frozen dataclass, k1/bus/envelope/envelope.py):
  ├── session_id           ← session routing key
  ├── cognitive_trace_id   ← cross-K0/K1 correlation
  ├── request_id           ← request scope within session
  ├── parent_id            ← causal chain (envelope_id of parent)
  ├── envelope_id          ← monotonic, bus-stamped
  ├── sequence             ← per-topic monotonic counter
  ├── created_ns           ← monotonic clock (ns)
  ├── payload              ← opaque bytes (bus never reads)
  ├── ttl_ms               ← time-to-live
  └── payload_format       ← hint (JSON/MSGPACK/OPAQUE)
```

**Tracing foundation already exists:**

- K0: Full OTel with `TracerFactory`, `cognitive_trace_id` in baggage, OTLP export
- K1 Bus: `TracingMiddleware` creates OTel span per envelope with `bus.session_id` + `bus.cognitive_trace_id` attributes
- Bridge: `EnvelopeBuilder` carries `trace_id` — but NO span creation (trace chain breaks at bridge)
- Memory Writer: MW-10 invariant says every bridge envelope MUST carry `cognitive_trace_id`
- `ToolContext` carries `cognitive_trace_id` — threaded into every tool invocation

#### 1.3 SIM-D-01: Per-Session Bus (Option B)

**Question:** Shared Bus with topic namespacing, or per-session Bus?

**Option A — Single shared Bus, topic namespacing:**

```
Topic: k1.{session_id}.user.input.v1
Topic: k1.{session_id}.turn.complete.v1
```

- Pro: One Bus instance, one RWLock, simpler lifecycle
- Pro: Cross-session events possible (admin broadcast)
- Con: Topic explosion — every session × every topic type
- Con: `TopicTrie` RWLock becomes contention point under high sessions
- Con: ALL current topic constants are bare (`k1.user.input.v1`) — every publisher needs refactoring

**Option B — Bus-per-session (CHOSEN):**

```
KernelService
  ├── system_bus (admin/health events only)
  └── sessions: dict[session_id, SessionInstance]
       └── SessionInstance.bus (isolated LocalBus)
```

- Pro: Total isolation — no topic collision possible
- Pro: Zero refactoring of existing topic constants
- Pro: Session eviction = destroy the Bus (clean teardown)
- Con: More memory per session (each Bus has TopicTrie, middleware chain)
- Con: Cross-session communication needs system_bus

**Decision: OPTION B.** LocalBus is lightweight. Isolation prevents session A's delta hitting session B's aggregator. Existing bare topic names (`k1.user.input.v1`) work unchanged. BackPool already tracks session_id per worker.

#### 1.4 SIM-D-02: Session Lifecycle

**Session states:**

```
CREATE  → allocate SessionInstance (Bus, SS, FSM, Ledger, Delta, ToolContext...)
ACTIVE  → processing turns, BackPool workers assigned
IDLE    → no turns in X minutes, experience tick still running
TIMEOUT → evict after configurable idle timeout (e.g., 30 min)
DESTROY → drain in-flight turns, flush deltas, checkpoint SS, release memory
```

**What creates a session?** New WebSocket connection with `device_id` → resolve `member_id` from HouseholdProjection cache → look up or create session.

**What destroys it?** Idle timeout OR explicit disconnect OR admin eviction OR max-session limit reached.

**ConciergeFactory (from MS-1) becomes the per-session factory:**

```python
class KernelService:
    async def create_session(self, device_id: str) -> str:
        member_id = self._household.resolve_member(device_id)
        session_id = f"s-{uuid4().hex[:12]}"
        bus = BusFactory.create_local()
        router = BusFactory.create_mailbox_router(bus)
        ss = SessionStateFactory.create_with_ports(...)
        concierge = ConciergeFactory.create_with_ports(
            ports={
                "input": WebSocketInputAdapter(ws_connection),
                "output": SSEOutputAdapter(sse_connection),
                "classification": self._shared.ultrabert_adapter,
                "llm": self._shared.model_gateway_adapter,
                "state": SessionKernelAdapter(ss),
                "dispatch": FabricOrchestratorAdapter(
                    self._shared.fabric, self._shared.orchestrator
                ),
                "delta": DeltaBusAdapter(bus),
                "memory": BridgeRecallAdapter(self._shared.bridge),
            },
            config=ConciergeConfig(session_id=session_id, member_id=member_id),
        )
        self._sessions[session_id] = SessionInstance(
            session_id=session_id,
            member_id=member_id,
            bus=bus, router=router, ss=ss, concierge=concierge,
            ledger=LedgerWriter(store, session_id=session_id),
            created_at=utcnow(), last_active=utcnow(),
        )
        await concierge.start()
        return session_id
```

#### 1.5 SIM-D-03: cognitive_trace_id Per-Turn Propagation

**Problem found:** Bootstrap creates TWO static trace IDs at boot — `k-front-{uuid}` and `k-back-{uuid}` — shared across ALL turns. This is wrong for production. Every turn should get a fresh trace.

**Also found:** Builder functions in `bus/builders.py` use `_build()` which creates `Envelope(...)` but does NOT set `session_id` or `cognitive_trace_id`. Most internal bus traffic flows with empty trace fields.

**Also found:** `SessionDelta` does NOT carry `session_id` or `cognitive_trace_id`. Delta mutations lose audit lineage.

**Design:**

```
Turn arrives (WebSocket message):
  │
  ├── cognitive_trace_id = generate_trace_id()  ← NEW per turn
  ├── session_id = from SessionInstance
  ├── request_id = unique per turn (within session)
  │
  ├── Envelope header: {session_id, cognitive_trace_id, request_id}
  │    ↓ flows through entire bus pipeline
  │
  ├── FSM receives → reads trace from envelope → threads to all subsystems
  ├── Front actor → carries trace → ToolContext.cognitive_trace_id
  ├── Back actor(s) → each inherits trace → tool invocations tagged
  ├── Delta pipeline → DeltaAggregator carries trace (FIX needed)
  ├── Memory Writer → MW-10: trace on every bridge envelope ✓ (already works)
  ├── Bridge → K0: trace_id in envelope header ✓ (already works)
  └── K0 → st_epi.cognitive_trace_id = same value
       → OTel span chain: K1 Bus span → Bridge span (FIX needed) → K0 span
```

**Multi-turn correlation:** `session_id` groups turns. Each turn gets its own `cognitive_trace_id`. Envelope `parent_id` creates causal chains within a session.

#### 1.6 SIM-D-04: Component Sharing — Per-Session vs Shared

| Component | Scope | Why |
|---|---|---|
| **Bus** | Per-session | Isolation (SIM-D-01) |
| **SessionState** | Per-session | Each user's state is independent |
| **FSM (ConciergeController)** | Per-session | One state machine per conversation |
| **LedgerWriter** | Per-session | Audit trail per session |
| **DeltaAggregator** | Per-session | Mutations scoped to session's SS |
| **ExperienceLayer** | Per-session | Affect/rhythm per conversation |
| **BackPool** | **Shared** | Already has `max_concurrent_per_session`. Global pool limits total compute. |
| **Fabric** | **Shared** | Stateless capability execution engine. Thread-safe. |
| **ModelHub** | **Shared** | LLM providers stateless, expensive to instantiate. Connection pooling. |
| **Orchestrator** | **Shared** | Stateless dispatch engine. |
| **Planner** | **Shared** | Stateless planning engine. |
| **Bridge** | **Shared** | One connection to K0, shared outbox. |
| **HouseholdProjection** | **Shared** | One family, all sessions see same household data. |
| **CapabilityRegistry** | **Shared** | Tools don't change per session. |
| **UltraBERT model** | **Shared** | GPU/CPU model, one instance, thread-safe inference. |

**KernelService architecture:**

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
  │         ├── session_id: str
  │         ├── member_id: str
  │         ├── bus: IBus (isolated per-session)
  │         ├── router: IMailboxRouter
  │         ├── session_state: SessionStateManager
  │         ├── concierge: Concierge (from ConciergeFactory)
  │         ├── ledger: LedgerWriter
  │         ├── created_at: datetime
  │         └── last_active: datetime
  │
  └── lifecycle:
       ├── create_session(device_id) → session_id
       ├── get_session(session_id) → SessionInstance
       ├── destroy_session(session_id) → None
       ├── evict_idle_sessions(timeout_minutes) → list[str]
       └── health_check() → HealthReport
```

#### 1.7 SIM-D-05: Threading Model

**Current codebase is asyncio-first:**

- Bootstrap, FSM, actors, tools, experience, delta — all `async/await`
- Bus internals use `threading.Lock` (synchronous dispatch, safe with asyncio)
- SessionState checkpoint uses a daemon timer thread (S-08 gotcha)
- BackPool workers are `asyncio.Task` instances

**Decision:** Single asyncio event loop per process. `KernelService` manages sessions as `asyncio.Task` groups. No additional threading beyond what Bus/SS already use internally.

**For HA/scale:** Multiple processes behind a load balancer. Session affinity via `session_id` cookie/header. Sticky sessions — a session's lifetime is one process. If process dies, session is lost (acceptable — K1 is edge-first, SS checkpoints to local SQLite for recovery).

#### 1.8 Gaps Found

| ID | Description | Severity |
|----|-------------|----------|
| **SIM-GAP-01** | Builder functions in `bus/builders.py` don't set `session_id` / `cognitive_trace_id` on Envelope headers — most published envelopes flow with empty trace fields | MEDIUM |
| **SIM-GAP-02** | `SessionDelta` dataclass lacks `session_id` and `cognitive_trace_id` — delta mutations lose audit lineage | LOW |
| **SIM-GAP-03** | `device_id → member_id` resolution not implemented — `device_id` is stored in MetaSection but no member lookup code exists | MEDIUM |
| **SIM-GAP-04** | Bootstrap creates static `k-front-{uuid}` / `k-back-{uuid}` trace IDs once at boot, not per-turn — wrong for production | MEDIUM |
| **SIM-GAP-05** | Bridge has no OTel span creation — trace chain breaks at K1↔K0 boundary. K0 has `inject(headers)`, K1 bus has spans, Bridge has neither. | HIGH |

#### 1.9 Flags (Existing Code Making Integration Hard)

| ID | File | Problem | Impact |
|----|------|---------|--------|
| **SIM-FLAG-01** | `k1/concierge/kernel/bootstrap.py` | Imports `poc.k1_poc.main.boot` — POC coupling prevents standalone boot | Must be eliminated before KernelService can call component factories directly |
| **SIM-FLAG-02** | `k1/concierge/obs/metrics.py` | Custom `MetricsCollector` is parallel to OTel, not integrated. Session-scoped metrics use custom `MetricEnvelope` not OTel metrics. | Two separate metrics systems. Low priority but tech debt. |

#### 1.10 VERDICT

**PROCEED.** The design is clean:

- Per-session Bus (SIM-D-01) — zero refactoring of topic constants
- `KernelService` with shared infrastructure + per-session `SessionInstance` (SIM-D-04)
- `cognitive_trace_id` per-turn, propagated end-to-end through envelope headers (SIM-D-03)
- Single asyncio event loop, multi-process for scale (SIM-D-05)
- 5 gaps identified — SIM-GAP-01/02/04 are fixable during integration, SIM-GAP-03/05 are MS-2 scope

**Next: Step 2 — Concierge Ports**

---

### STEP 2 — Concierge Ports (Define the Hexagonal Boundary)

> **Status:** SIMULATED — 3 decisions made, 4 gaps found, 3 flags raised
> **Date:** 2026-04-02

**Question:** Before wiring anything, define the Concierge's external contract (8 hexagonal ports). Do the existing scattered internal ports conflict? What types do we need? What happens to the internal ports?

#### 2.1 What We Read

- `k1/concierge/llm/ports.py` — `IConciergeModelPort` (1 Protocol: `generate`, `generate_stream`)
- `k1/concierge/orchestrator/ports.py` — 9 Protocols (3 core: `IFabricGatewayPort`, `IStateReadPort`, `IDeltaEmitPort` + 6 HIGH-tier deferred)
- `k1/concierge/orchestrator/interfaces.py` — 6 ABCs mirroring the HIGH-tier Protocols
- `k1/concierge/fabric/ports.py` — `IFabricPort` (4 methods: `execute`, `execute_batch`, `discover_capabilities`, `find_relevant_prompts`)
- `k1/concierge/fsm/phase1.py` — `Phase1Pipeline` Protocol (`classify(text) → Phase1Result`)
- `k1/concierge/fsm/ultrabert_adapter.py` — `UltraBERTAdapter` Protocol (`analyze`, `is_available`, `get_metrics`)
- `k1/concierge/ledger/store.py` — `ILedgerStore` Protocol (`append`, `read`, `read_by_type`, `exists`)
- `k1/concierge/fsm/controller.py` — `ConciergeController.__init__(bus: IBus, router: IMailboxRouter)`
- `k1/concierge/actors/front.py` — `front_handler(envelope, model: IModelHubPort, ss, bus, tool_dispatcher, ...)`
- `k1/concierge/actors/back.py` — `back_handler(envelope, model: IModelHubPort, ss, bus, tool_dispatcher, ...)`
- `k1/concierge/tools/dispatcher.py` — `ToolDispatcher.__init__(actor, allowlist, tool_schemas, ctx: ToolContext, tier, bus)`
- `k1/concierge/experience/layer.py` — `ExperienceLayer.__init__()` — ZERO parameters, fully hardcoded
- `k1/concierge/delta/aggregator.py` — `DeltaAggregator.__init__(flush_fn: Callable, batch_window_ms)`
- kernel.md §89 — canonical 8-port definitions (IInputPort through IMemoryPort)
- Whiteboard §4 — port-to-internal wiring map
- Whiteboard §5 — existing code mapping

#### 2.2 Critical Discovery: Two-Layer Port Architecture

The codebase has TWO port layers that must NOT be confused:

```
LAYER 1: EXTERNAL PORTS (kernel.md §89) — NEW, to be created
  ├── IInputPort, IOutputPort                    ← don't exist anywhere
  ├── IClassificationPort                        ← don't exist anywhere
  ├── ILLMPort                                   ← don't exist anywhere
  ├── IStatePort, IDispatchPort, IDeltaPort      ← don't exist anywhere
  └── IMemoryPort                                ← don't exist anywhere

LAYER 2: INTERNAL PORTS (already exist) — STAY UNTOUCHED
  ├── IConciergeModelPort  (llm/ports.py)        ← used by GeminiAdapter, TestAdapter
  ├── IFabricGatewayPort   (orchestrator/ports.py) ← used by OrchestratorStub
  ├── IStateReadPort       (orchestrator/ports.py)  ← used by OrchestratorStub
  ├── IDeltaEmitPort       (orchestrator/ports.py)  ← used by OrchestratorStub
  ├── IFabricPort          (fabric/ports.py)        ← used by Back tools
  ├── Phase1Pipeline       (fsm/phase1.py)          ← used by FSM
  ├── UltraBERTAdapter     (fsm/ultrabert_adapter.py) ← used by Phase1Pipeline
  └── ILedgerStore         (ledger/store.py)        ← used by LedgerWriter
```

**The factory bridges External → Internal.** External ports are what the kernel injects. Internal ports are what subsystems consume. The factory wires them:

```
ILLMPort (external)
  → factory creates wrapper → feeds IModelHubPort to front_handler/back_handler
  → factory creates wrapper → feeds IConciergeModelPort to GeminiAdapter bridge

IDispatchPort (external)
  → factory creates wrapper → feeds IFabricGatewayPort to OrchestratorStub
  → factory creates wrapper → feeds IFabricPort to Back tools

IStatePort (external)
  → factory creates wrapper → feeds IStateReadPort to OrchestratorStub
  → factory passes raw → ss parameter to front_handler/back_handler (duck-typed Any)
```

#### 2.3 SIM-D-06: External Port Signatures (kernel.md §89 wins)

The kernel.md §89 signatures are canonical and consistent across all 5 locations in the spec. No contradictions found.

**Port 1: IInputPort**

```python
@runtime_checkable
class IInputPort(Protocol):
    async def receive(self) -> UserMessage: ...
```

- Concierge consumer loop calls `receive()` — pull interface
- Adapter's push side: `send_user_message(text, session_id, metadata)` → internal async queue
- Per SIM-D-01: session-scoped (each session gets its own IInputPort adapter)
- Per SIM-D-03: adapter generates `cognitive_trace_id` per message

**Port 2: IOutputPort**

```python
@runtime_checkable
class IOutputPort(Protocol):
    async def send(self, event: OutputEvent) -> DeliveryReceipt: ...
```

- `OutputEvent` is a union type: `StreamChunkEvent | FinalResponseEvent | ProgressEvent | IntentAckEvent | ClarificationEvent | ErrorEvent`
- Per whiteboard D-7: kernel.md's single polymorphic `send()` replaces D-2's original 3 methods
- CB_SSE inside adapter (D-10)

**Port 3: IClassificationPort**

```python
@runtime_checkable
class IClassificationPort(Protocol):
    async def classify(self, text: str) -> ClassificationResult: ...
```

- `ClassificationResult` has: `tier` (LOW/MED/HIGH), `domain`, `safety` (GREEN/AMBER/RED/CRISIS), `intents`
- CB_MODEL; heuristic fallback <1ms on CB open
- **Compatibility note:** Existing `Phase1Pipeline.classify(text) → Phase1Result` is similar but different return type. Factory bridges: `IClassificationPort.classify()` → convert `ClassificationResult` → `Phase1Result` for FSM consumption.

**Port 4: ILLMPort**

```python
@runtime_checkable
class ILLMPort(Protocol):
    async def execute(self, request: HubRequest) -> HubResponse: ...
    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]: ...
```

- **Compatibility issue found (SIM-FLAG-03):** Front/Back actors import `IModelHubPort` from `k1.model_hub.ports` (NOT `IConciergeModelPort` from `k1.concierge.llm.ports`). So `ILLMPort` must be compatible with `IModelHubPort` which has `execute(HubRequest) → HubResponse`. This is structurally identical — `ILLMPort` IS `IModelHubPort` with `stream_execute` added.
- `IConciergeModelPort` (with `generate`/`generate_stream`) is a DIFFERENT interface used only by `GeminiConciergeAdapter`. It's a legacy wrapper, not the actor-facing port.

**Port 5: IStatePort**

```python
@runtime_checkable
class IStatePort(Protocol):
    async def read(self, sections: list[str]) -> Snapshot: ...
    async def write(self, section: str, op: str, data: Any) -> WriteResult: ...
```

- CB_SESSIONSTATE; stale cache on timeout
- MutationGuard inside adapter (ADR-0017: Concierge is the ONLY writer)
- **Compatibility note:** Actors receive `ss` as `Any` (duck-typed). They call `ss.get_section()`, `ss.read_section()`, etc. The `IStatePort` adapter must expose these same method names OR the factory wraps IStatePort into an object that matches SessionStateManager's duck-type interface.

**Port 6: IDispatchPort**

```python
@runtime_checkable
class IDispatchPort(Protocol):
    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult: ...
    async def dispatch_envelope(self, envelope: TaskEnvelope) -> None: ...
```

- **Type collision found (SIM-GAP-06):** `IFabricPort` (concierge/fabric/) imports `CapabilityRequest`/`CapabilityResult` from `k1.fabric.types`. `IFabricGatewayPort` (concierge/orchestrator/) imports same-named types from `k1.concierge.orchestrator.types`. DIFFERENT MODULES, same names. Factory must handle conversion.
- Tier degradation cascade: HIGH→MED→LOW→canned (CB_PLANNER, CB_ORCHESTRATOR, CB_FABRIC, CB_MCP)

**Port 7: IDeltaPort**

```python
@runtime_checkable
class IDeltaPort(Protocol):
    async def subscribe(self, topics: list[str]) -> DeltaStream: ...
    async def publish(self, event: Any) -> None: ...
    async def errors(self) -> ErrorStream: ...
```

- Per SIM-D-01: wraps the per-session Bus
- **Compatibility note:** `DeltaAggregator` takes `flush_fn: Callable[[DeltaBatch], Awaitable[None]]` — not a port. Factory creates a closure: `flush_fn = lambda batch: delta_port.publish(batch)`
- 45 existing envelope builders call `bus.publish()` directly. Factory provides the per-session bus to these builders via the bus reference inside IDeltaPort adapter.

**Port 8: IMemoryPort**

```python
@runtime_checkable
class IMemoryPort(Protocol):
    async def recall(self, query: str, selectors: list[str]) -> MemoryResult: ...
```

- Timeout: skip memory (RECOVERABLE, never TERMINAL)
- Current POC: `recall_fn` closure that keyword-scores seed memories
- Per SIM-D-04: wraps shared BridgeClient

#### 2.4 SIM-D-07: Internal Ports Stay Untouched

**Decision:** ALL existing internal ports (`IConciergeModelPort`, `IFabricGatewayPort`, `IStateReadPort`, `IDeltaEmitPort`, `IFabricPort`, `Phase1Pipeline`, `UltraBERTAdapter`, `ILedgerStore`) remain unchanged. Zero modifications to existing files.

**Rationale:**

1. Internal ports serve internal subsystem contracts. They work. 63 tests pass against them.
2. External ports are a DIFFERENT layer. The factory bridges external → internal.
3. Changing internal ports would cascade into 20+ internal files — massive risk for zero benefit.

#### 2.5 SIM-D-08: Type Bridging Strategy

The factory must bridge types between external ports and internal consumers:

| External Port | External Type | Internal Consumer | Internal Type | Bridge |
|---|---|---|---|---|
| `ILLMPort` | `HubRequest/HubResponse` | `front_handler`, `back_handler` | `IModelHubPort` (same types) | **Direct passthrough** — ILLMPort IS structurally compatible with IModelHubPort |
| `IClassificationPort` | `ClassificationResult` | FSM `Phase1Pipeline` | `Phase1Result` | **Adapter converts** ClassificationResult → Phase1Result |
| `IStatePort` | `Snapshot/WriteResult` | actors (`ss: Any`) | duck-typed `.get_section()`, `.read_section()` | **Wrapper object** that delegates IStatePort methods to match SS duck-type |
| `IDispatchPort` | `CapabilityRequest` (kernel.md) | `IFabricPort` | `CapabilityRequest` (k1.fabric.types) | **Type alias or converter** — same-named types from different modules |
| `IDispatchPort` | `CapabilityRequest` (kernel.md) | `IFabricGatewayPort` | `CapabilityRequest` (k1.concierge.orchestrator.types) | **Type converter** needed |
| `IDeltaPort` | `publish(event)` | `DeltaAggregator` | `flush_fn: Callable` | **Closure wrapping** `delta_port.publish` |
| `IDeltaPort` | `publish(event)` | 45 envelope builders | `bus.publish(envelope)` | **Bus ref exposed** from adapter |
| `IMemoryPort` | `MemoryResult` | `ToolContext.recall_fn` | `Callable → list[dict]` | **Closure wrapping** `memory_port.recall` |

#### 2.6 Gaps Found

| ID | Description | Severity |
|----|-------------|----------|
| **SIM-GAP-06** | `CapabilityRequest`/`CapabilityResult` type collision — same names in `k1.fabric.types` vs `k1.concierge.orchestrator.types`. Factory adapter must convert between them. | MEDIUM |
| **SIM-GAP-07** | Actors receive `ss: Any` (duck-typed). No Protocol contract for what SessionState methods actors actually call. Need to audit exact method calls to ensure IStatePort wrapper is compatible. | MEDIUM |
| **SIM-GAP-08** | `ExperienceLayer.__init__()` takes ZERO parameters. Fully hardcoded. Cannot inject IStatePort or IDeltaPort via constructor — needs post-init wiring or refactor. | MEDIUM |
| **SIM-GAP-09** | `ConciergeController.__init__(bus, router)` takes only IBus + IMailboxRouter. Everything else (orchestrator, SS, ledger, weave, etc.) is late-wired via `Any`-typed attributes. No type safety on controller wiring. | LOW |

#### 2.7 Flags (Existing Code Making Integration Hard)

| ID | File | Problem | Impact |
|----|------|---------|--------|
| **SIM-FLAG-03** | `k1/concierge/actors/front.py`, `back.py` | Actors import `IModelHubPort` from `k1.model_hub.ports`, NOT from concierge local ports. External `ILLMPort` must be structurally compatible with `IModelHubPort`. | ILLMPort design must match IModelHubPort signature (it does — `execute(HubRequest) → HubResponse`) |
| **SIM-FLAG-04** | `k1/concierge/orchestrator/types.py` | Defines its own `CapabilityRequest`/`CapabilityResult` that shadow `k1.fabric.types` versions. Two type universes coexist. | Factory adapter layer must convert between them |
| **SIM-FLAG-05** | `k1/concierge/fsm/controller.py` | Controller uses `Any`-typed late-wired attributes for 10+ dependencies. No compile-time safety. | Factory must wire all attributes correctly — runtime errors only if wrong |

#### 2.8 VERDICT

**PROCEED.** The 8 external ports are well-defined (kernel.md §89 is consistent, no contradictions). Key insights:

1. **Two-layer architecture is correct** — external ports (new) bridge to internal ports (unchanged)
2. **ILLMPort ≈ IModelHubPort** — structurally compatible, direct passthrough
3. **IClassificationPort → Phase1Result** needs a type converter (small, well-scoped)
4. **IStatePort needs a wrapper** that matches SessionState duck-type interface
5. **CapabilityRequest type collision** (SIM-GAP-06) needs a converter in the IDispatchPort adapter
6. **ExperienceLayer hardcoded** (SIM-GAP-08) — needs investigation in Step 3 (factory wiring)

**Internal ports are NOT touched. 63 tests keep passing. Zero modifications to existing files.**

**Next: Step 3 — Test Adapters + Factory Skeleton**

---

### STEP 3 — Test Adapters + Factory Skeleton (Concierge boots with fakes)

**Question:** Can we create `ConciergeFactory.create_with_ports()` that wires all 20+ internal subsystems using 8 injected ports + test adapters, and get a `Concierge` object that starts/stops cleanly?

**Assumption:** Steps 1–2 are implemented. Per-session Bus exists (SIM-D-01). 8 external ports defined per kernel.md §89 (SIM-D-06). Internal ports untouched (SIM-D-07). Type bridging strategy decided (SIM-D-08).

**What we read:**

| File | What we learned |
|------|----------------|
| `k1/concierge/kernel/bootstrap.py` (full 530 lines) | 32-step wiring sequence in `start_kernel()`, `stop_kernel()` teardown sequence, `_mailbox_consumer()` polling loop, 6 helper functions, 3 adapter classes |
| `k1/concierge/tools/implementations.py` | `ToolContext` dataclass — 11 fields, the universal dependency bag |
| `k1/concierge/tools/dispatcher.py` | `ToolDispatcher.__init__()`, `create_front_dispatcher()`, `create_back_dispatcher()` factory functions |
| `k1/concierge/protocols/hitl_coordinator.py` | `HILCoordinator.__init__()` — 6 callback params, internally creates `SuspensionManager` |
| `k1/concierge/protocols/suspension_manager.py` | `SuspensionManager.__init__()` — 3 params (callbacks + optional ledger) |
| `k1/concierge/protocols/weave_batcher.py` | `WeaveBatcher.__init__()` — flush callback + config values |
| `k1/concierge/protocols/weave_policy.py` | Module defines `UserActivityTracker` (zero deps) + `WeaveSignal` (pure data) — no managed singleton |
| `k1/concierge/protocols/opp_pipeline.py` | `OppPipelineConfig` — 8 boolean enable flags, all optional |
| `k1/concierge/protocols/trust_accumulator.py` | `TrustAccumulator.__init__()` — zero deps, config optional |
| `k1/concierge/actors/back_pool.py` | `BackPool.__init__()` — config + optional callbacks. Pure pool. |
| `k1/concierge/actors/back_router.py` | `BackTopicRouter.__init__(back_pool)` — needs BackPool |
| `k1/concierge/actors/ready_queue.py` | `ReadyQueue` — zero constructor params, dataclass defaults |
| `k1/concierge/delta/applicator.py` | `DeltaApplicator.__init__()` — 4 callback params (preflight/write/evict/notify) |
| `k1/concierge/fsm/dead_letter_consumer.py` | `DeadLetterConsumer.__init__(bus)` — subscribes to `TOPIC_DEAD_LETTER` immediately in `__init__` |
| `k1/concierge/fsm/controller.py` | `ConciergeController.__init__(bus, router)` — 9 late-wired setters for everything else |
| `k1/concierge/ledger/writer.py` | `LedgerWriter.__init__(store, session_id)` — needs ILedgerStore |
| `k1/concierge/ledger/store.py` | `InMemoryLedgerStore` — zero deps, leaf node |
| `k1/concierge/prompt/builder.py` | `DynamicPromptBuilder` — stateless, zero constructor deps, `build()` takes all args |
| `k1/concierge/react/loop.py` | `react_loop()` — free async function, needs IModelHubPort + ToolDispatcher + callbacks |
| `k1/concierge/experience/layer.py` | `ExperienceLayer.__init__()` — zero params, hardcodes 6 internal components |

---

#### 3.1 Discovery: Current `start_kernel()` Is a 32-Step Monolith

The existing bootstrap performs **32 ordered steps** in a single function. This is our factory's blueprint:

```
Step  1: Load KernelConfig (defaults or injected)
Step  2: boot() → bus, router, adapter, front_mailbox, back_mailbox    ← POC COUPLING (SIM-FLAG-01)
Step  3: _create_model(cfg) → TestModelHubBridge or GeminiAdapter       ← REPLACED BY ILLMPort
Step  4: _create_session_state(cfg) → SessionStateFactory               ← REPLACED BY IStatePort
Step  5: _create_capability_registry() → create_demo_registry()         ← REPLACED BY IDispatchPort
Step  6: _create_fabric(registry) → FabricFactory.create_with_ports()   ← REPLACED BY IDispatchPort
Step  7: LedgerWriter + InMemoryLedgerStore (conditional)
Step  8: ConciergeController(bus, router)                               ← Needs IBus (from Step 2)
Step  9: Phase1 pipeline → fsm._phase1_pipeline (conditional)           ← REPLACED BY IClassifyPort
Step 10: fsm.set_ledger(writer)                                         ← Late-wire
Step 11: fsm.set_history_sink(ss.get_section("history_active"))          ← Late-wire
Step 12: fsm.set_session_state(ss)                                       ← Late-wire
Step 13: Extract _writer_port from session_state                         ← Internal port
Step 14: Build recall_fn closure over cfg.seed_memories                  ← REPLACED BY IMemoryPort.recall()
Step 15: Front ToolContext(ss, trace_id, recall_fn, fabric, writer_port) ← Dep bag
Step 16: Back ToolContext(ss, trace_id, recall_fn, fabric, writer_port)  ← Dep bag
Step 17: create_front_dispatcher(tier, ctx, bus)
Step 18: create_back_dispatcher(tier, ctx, bus)
Step 19: Assemble KernelRuntime dataclass (14 required fields)
Step 20: ExperienceLayer() → runtime.experience_layer (conditional)
Step 21: DeltaApplicator + DeltaAggregator (conditional)
Step 22: HILCoordinator(callbacks) + fsm.set_hitl_coordinator() (conditional)
Step 23: WeaveBatcher + fsm.set_weave_batcher() (conditional)
Step 24: WeavePolicy + fsm.set_weave_policy() (conditional)
Step 25: UserActivityTracker + fsm.set_activity_tracker() (conditional)
Step 26: DeadLetterConsumer(bus) (conditional)
Step 27: OrchestratorStub(fabric_gateway, state_read, delta_emit) + fsm.set_orchestrator()
Step 28: Create routing closures for bus → mailbox
Step 29: subscribe_front_events(bus, route_fn) → front subscriptions
Step 30: back_subscriptions = [] (FSM is sole back-route authority)
Step 31: asyncio.create_task(_mailbox_consumer(runtime))
Step 32: runtime.started = True
```

**Steps replaced by external ports:** 2 (partially — bus creation stays, POC boot goes), 3, 4, 5, 6, 9, 14.
**Steps that remain internal:** 7, 8, 10–13, 15–32.

---

#### 3.2 Discovery: Init Order Dependency Graph (6 Layers)

Every subsystem constructor was audited. The dependency graph is clean — **no circular imports detected**:

```
Layer 0 — Leaf nodes (zero deps):
    InMemoryLedgerStore, ReadyQueue, TrustAccumulator, BackPoolConfig,
    DynamicPromptBuilder, UserActivityTracker, OppPipelineConfig,
    ExperienceLayer, WeavePolicy (stateless signal collector)

Layer 1 — Needs Layer 0:
    LedgerWriter              ← ILedgerStore (Layer 0)
    BackPool                  ← BackPoolConfig (Layer 0)
    IBus                      ← (external, injected per SIM-D-01)

Layer 2 — Needs Layer 1:
    ConciergeController       ← IBus, IMailboxRouter (Layer 1)
    DeadLetterConsumer        ← IBus (Layer 1)  ⚠ subscribes in __init__!
    BackTopicRouter           ← BackPool (Layer 1)
    SuspensionManager         ← LedgerWriter optional (Layer 1)
    WeaveBatcher              ← flush callback (needs LLM pipeline to exist)

Layer 3 — Needs Layer 2 + external ports:
    HILCoordinator            ← callbacks (bus closures), LedgerWriter optional
                                 Creates SuspensionManager internally
    DeltaApplicator           ← SS callbacks (preflight/write/evict), bus callback

Layer 4 — Needs Layer 3 + ports:
    ToolContext                ← SessionState, IWriterPort, IFabricPort, HILCoordinator
    DeltaAggregator           ← DeltaApplicator.apply (flush target)

Layer 5 — Needs Layer 4:
    ToolDispatcher             ← ToolContext, IBus

Layer 6 — Needs Layer 5:
    react_loop()               ← IModelHubPort, ToolDispatcher, callbacks (not a managed object)
```

**Key insight:** No subsystem at Layer N depends on something at Layer N+1. No circular deps. The factory can wire top-to-bottom in a single pass. The 32-step bootstrap sequence already follows this order.

---

#### 3.3 Discovery: ConciergeController Has 9 Late-Wired Setters

The FSM (`ConciergeController`) takes only `(bus, router)` in its constructor, then gets everything else bolted on via setters:

| Setter | What | Bootstrap Step | Required for boot? |
|--------|------|---------------|-------------------|
| `fsm._phase1_pipeline = ...` | UltraBERT Phase1 pipeline | 9 | No — falls back to regex |
| `fsm.set_ledger(writer)` | LedgerWriter | 10 | No — conditional on `enable_ledger` |
| `fsm.set_history_sink(section)` | History section from SS | 11 | No — skips if section missing |
| `fsm.set_session_state(ss)` | SessionStateManager | 12 | **YES** — FSM reads SS during turns |
| `fsm.set_hitl_coordinator(hil)` | HILCoordinator | 22 | No — L2 checks disabled if absent |
| `fsm.set_weave_batcher(wb)` | WeaveBatcher | 23 | No — weave disabled if absent |
| `fsm.set_weave_policy(wp)` | WeavePolicy | 24 | No — weave policy disabled if absent |
| `fsm.set_activity_tracker(at)` | UserActivityTracker | 25 | No — activity tracking disabled if absent |
| `fsm.set_orchestrator(orch)` | OrchestratorStub | 27 | No — orchestrator disabled if absent |

**Only `set_session_state()` is required for FSM to function.** All others degrade gracefully. This means our factory can boot a minimal Concierge with just: Bus + Router + SessionState + FSM.

---

#### 3.4 Discovery: ToolContext Is the Universal Dependency Bag

`ToolContext` is a dataclass with 11 fields that gets injected into every tool function. Two instances are created: one for Front actor, one for Back actor.

| ToolContext Field | Source in Factory | External Port? |
|-------------------|-------------------|----------------|
| `session_manager` | IStatePort adapter → SessionState | YES (IStatePort) |
| `cognitive_trace_id` | Generated per-turn per SIM-D-03 | Generated |
| `actor` | `"front"` or `"back"` | Literal |
| `writer_port` | `session_state._writer_port` (internal) | NO — internal SS detail |
| `bundle_idempotency_cache` | `{}` (fresh per session) | Generated |
| `active_device_id` | From envelope meta / IInputPort | Passed per-turn |
| `hil_coordinator` | HILCoordinator instance | Internal |
| `active_task_id` | Set per-turn during L2 tasks | Passed per-turn |
| `fabric_port` | IDispatchPort adapter → IFabricPort | YES (IDispatchPort) |
| `recall_fn` | IMemoryPort.recall() closure | YES (IMemoryPort) |
| `capability_cache` | `{}` (fresh per session) | Generated |

**ToolContext bridges 3 of 8 external ports**: IStatePort, IDispatchPort, IMemoryPort.
**ToolContext does NOT bridge**: ILLMPort (goes to react_loop), IBusPort (goes to FSM/subscriptions), IClassifyPort (goes to FSM._phase1_pipeline), IObsPort (goes to telemetry), IInputPort (goes to kernel entry point).

---

#### 3.5 Discovery: `stop_kernel()` Teardown Is 7 Steps (All Guarded)

```
1. Cancel consumer_task (asyncio task)
2. Log ledger entry count
3. Log dead-letter summary
4. Flush delta_aggregator
5. FSM.teardown()
6. SessionState.close() (if has close method)
7. Model.close() (if has close method)
8. runtime.started = False
```

**Every step is try/except guarded.** No step depends on another step succeeding. The factory's `stop()` can replicate this exactly — reverse order of `start()`, all guarded. No hidden cleanup interdependencies.

---

#### 3.6 Discovery: `boot()` POC Coupling (SIM-FLAG-01 Resolution)

The `boot()` function from `poc.k1_poc.main` creates: Bus + Router + Adapter + front_mailbox + back_mailbox. In the new factory:

- **Bus**: Created by `BusFactory.create_local()` — already exists in `k1/bus/factory.py`
- **Router**: Created by `BusFactory.create_mailbox_router()` — already exists
- **Adapter**: POC-specific LLM adapter → **REPLACED by ILLMPort**
- **Mailboxes**: Created by `router.create_mailbox("front_half")` / `router.create_mailbox("back_half")`

**Resolution:** `boot()` import is eliminated. Factory calls `BusFactory` directly. Zero POC dependency.

---

#### 3.7 Discovery: ExperienceLayer Resolution (SIM-GAP-08)

`ExperienceLayer.__init__()` hardcodes 6 internal components (EmotionalProcessor, AffectiveMirror, NarrativeWeaver, AnticipatoryResponder, ProactiveAgent, RhythmController). It takes zero params.

**However:** `ExperienceLayer.tick(fsm_state, context)` receives its inputs via the `context` dict (built by `_build_experience_context(runtime)` which reads from SessionState). It does NOT import or hold references to any external port. The 6 internal components are self-contained algorithms that process the context dict.

**The `_tick_experience()` helper** reads `runtime.experience_layer`, calls `tick()`, then writes results back to SessionState and publishes bus events. All external interaction is in the **caller**, not the layer itself.

**Resolution:** ExperienceLayer stays zero-param. It's a pure algorithm orchestrator. The factory creates it as `ExperienceLayer()`, exactly as today. The external port bridging happens in the caller (`_tick_experience` equivalent in the new consumer loop). **SIM-GAP-08 is resolved — no refactor needed.**

---

#### 3.8 Discovery: Three Bootstrap-Internal Adapter Classes

`bootstrap.py` defines 3 private adapter classes for the Orchestrator:

| Adapter | Wraps | Purpose |
|---------|-------|---------|
| `_FabricGatewayAdapter` | `fabric_instance` | Translates POC `CapabilityRequest` ↔ K1 `CapabilityRequest/Result` |
| `_StateReadAdapter` | `session_state` | Provides `snapshot()` and `read_section()` |
| `_DeltaEmitAdapter` | `delta_aggregator` + `bus` | Routes deltas to aggregator, non-deltas to bus |

In the new factory, these adapters still exist but wrap the **port adapters** instead of concrete instances. The Orchestrator doesn't know the difference — it calls the same interface. No Orchestrator code changes.

---

#### 3.9 SIM-D-09: Factory Structure — ConciergeFactory.create_with_ports()

**Decision:** The factory is a single `create_with_ports()` classmethod that accepts the 8 external ports + a config, and returns a `ConciergeSession` wrapper around `KernelRuntime`.

**Factory signature:**

```python
class ConciergeFactory:
    @classmethod
    async def create_with_ports(
        cls,
        bus: IBus,
        router: IMailboxRouter,
        ports: ExternalPorts,        # dataclass with 8 port fields
        config: KernelConfig | None = None,
        session_id: str | None = None,
    ) -> ConciergeSession:
```

**`ExternalPorts` dataclass:**

```python
@dataclass
class ExternalPorts:
    llm: ILLMPort
    state: IStatePort
    dispatch: IDispatchPort
    classify: IClassifyPort
    memory: IMemoryPort
    obs: IObsPort
    input_port: IInputPort       # For per-turn trace_id generation
    bus_port: IBusPort           # For cross-session bus bridging (future)
```

**Rationale:**

- Bus + Router are infrastructure created by KernelService (per SIM-D-01), not a "port"
- The 8 ports are the hexagonal boundary from kernel.md §89
- Config controls feature flags (enable_ledger, enable_hitl, etc.)
- Returns `ConciergeSession` which wraps `KernelRuntime` with clean start/stop

---

#### 3.10 SIM-D-10: Factory Wiring Sequence (32 Steps → 26 Steps)

The factory replicates bootstrap's 32 steps but **eliminates 6 POC-coupled steps**:

```
FACTORY WIRING SEQUENCE (26 steps):
─────────────────────────────────────

Phase A: Infrastructure (from KernelService, NOT created by factory)
  ✓ Bus — received as param (per-session, SIM-D-01)
  ✓ Router — received as param
  ✓ Mailboxes — created from router: front_half, back_half

Phase B: Leaf nodes (Layer 0)
  F1:  InMemoryLedgerStore() [if enable_ledger]
  F2:  BackPool(config)
  F3:  ReadyQueue()
  F4:  UserActivityTracker()
  F5:  ExperienceLayer()
  F6:  DynamicPromptBuilder()  [stateless, create on demand]

Phase C: Layer 1-2 subsystems
  F7:  LedgerWriter(store=F1, session_id)
  F8:  BackTopicRouter(back_pool=F2)
  F9:  ConciergeController(bus, router)

Phase D: Port adaptation (external → internal)
  F10: session_state = ports.state → IStatePort adapter (wraps to SSM duck-type)
  F11: recall_fn = lambda q: ports.memory.recall(q)  [closure over IMemoryPort]
  F12: fabric_port = ports.dispatch → IFabricPort adapter (type bridging per SIM-D-08)
  F13: writer_port = session_state._writer_port  [internal extraction]
  F14: phase1_adapter = ports.classify → Phase1Pipeline adapter (ClassificationResult → Phase1Result)

Phase E: Wire FSM (9 late-wired setters)
  F15: fsm.set_session_state(session_state)       [REQUIRED]
  F16: fsm.set_ledger(F7)                         [if enable_ledger]
  F17: fsm.set_history_sink(ss.get_section("history_active"))
  F18: fsm._phase1_pipeline = F14                 [if classify port available]

Phase F: Build ToolContexts + Dispatchers
  F19: front_ctx = ToolContext(ss, trace_id, recall_fn, fabric_port, writer_port, ...)
  F20: back_ctx  = ToolContext(ss, trace_id, recall_fn, fabric_port, writer_port, ...)
  F21: front_dispatcher = create_front_dispatcher(tier, front_ctx, bus)
  F22: back_dispatcher  = create_back_dispatcher(tier, back_ctx, bus)

Phase G: Higher-layer subsystems
  F23: DeltaApplicator(preflight_fn, write_fn, evict_fn, notify_fn) [closures over SS + bus]
       DeltaAggregator(flush_fn=applicator.apply)
  F24: HILCoordinator(on_emit_suspended, on_emit_resume, on_timeout) [closures over bus]
       fsm.set_hitl_coordinator(hil)
  F25: WeaveBatcher(flush_fn) + fsm.set_weave_batcher()
       WeavePolicy() + fsm.set_weave_policy()
       fsm.set_activity_tracker(F4)
  F26: OrchestratorStub(fabric_gateway, state_read, delta_emit)
       fsm.set_orchestrator(orch)

Phase H: Subscriptions + Consumer
  F27: DeadLetterConsumer(bus)  [if enabled — subscribes in __init__!]
  F28: subscribe_front_events(bus, route_fn)
  F29: asyncio.create_task(_mailbox_consumer(runtime))
  F30: runtime.started = True → return ConciergeSession(runtime)
```

**6 eliminated steps:** `boot()` call (replaced by Bus param), `_create_model()` (replaced by ILLMPort), `_create_session_state()` (replaced by IStatePort), `_create_capability_registry()` (replaced by IDispatchPort), `_create_fabric()` (replaced by IDispatchPort), `_build_recall_fn()` (replaced by IMemoryPort).

---

#### 3.11 SIM-D-11: Test Adapter Design

For the factory to boot with fakes, each of the 8 external ports needs a test adapter:

| Port | Test Adapter | Complexity | Notes |
|------|-------------|------------|-------|
| `ILLMPort` | `FakeLLMPort` — returns canned `HubResponse` | LOW | `execute()` returns fixed response, `stream_execute()` yields one chunk |
| `IStatePort` | `FakeStatePort` — wraps `SessionStateFactory.create_for_testing()` | LOW | Existing factory already exists for tests |
| `IDispatchPort` | `FakeDispatchPort` — returns empty `CapabilityResult` | LOW | `discover()` returns [], `invoke()` returns success |
| `IClassifyPort` | `FakeClassifyPort` — returns `Phase1Result(intent="general")` | LOW | Single-method port |
| `IMemoryPort` | `FakeMemoryPort` — `recall()` returns `[]`, `store()` is no-op | LOW | Two methods |
| `IObsPort` | `FakeObsPort` — all methods are no-ops | LOW | Pure telemetry sink |
| `IInputPort` | `FakeInputPort` — generates trace_id, passes through | LOW | Wraps input text |
| `IBusPort` | `FakeBusPort` — no-op cross-session bridge | LOW | Not used in single-session mode |

**All 8 test adapters are < 30 lines each.** None require external dependencies. They can live in `k1/concierge/kernel/test_adapters.py`.

---

#### 3.12 SIM-D-12: ConciergeSession Wrapper

The factory returns `ConciergeSession`, not raw `KernelRuntime`:

```python
class ConciergeSession:
    """Clean interface over KernelRuntime for a single session."""

    def __init__(self, runtime: KernelRuntime):
        self._runtime = runtime

    async def start(self) -> None:
        """Start mailbox consumer. Called after factory wiring."""
        # F29: create consumer task
        # F30: set started flag

    async def stop(self) -> None:
        """Graceful shutdown — mirrors stop_kernel() 7-step teardown."""
        # 1. Cancel consumer task
        # 2. Flush delta aggregator
        # 3. FSM teardown
        # 4. SessionState close
        # 5. Model close (via ILLMPort.close() if exists)
        # 6. Log ledger + dead-letter summaries
        # 7. Set started = False

    @property
    def bus(self) -> IBus: ...
    @property
    def fsm(self) -> ConciergeController: ...
    @property
    def session_state(self) -> Any: ...
    @property
    def is_running(self) -> bool: ...
```

**Rationale:** `KernelRuntime` is a flat dataclass with 25+ fields. `ConciergeSession` provides a clean lifecycle API (start/stop) and hides internal wiring. Tests call `session = await ConciergeFactory.create_with_ports(...)` then `await session.start()`.

---

#### 3.13 Blocked Imports Analysis

With the factory design above, the **only** import from POC that remains is:

| Import | Used By | Status |
|--------|---------|--------|
| `from poc.k1_poc.main import boot` | `start_kernel()` | **ELIMINATED** — factory receives Bus + Router as params |
| `from k1.concierge.config import get_config` | Multiple subsystems | **KEPT** — internal config, not POC |
| `from k1.concierge.bus.builders import build_*` | HILCoordinator callbacks, experience tick | **KEPT** — internal bus envelope builders |
| `from k1.concierge.actors.front import front_handler, subscribe_front_events` | Consumer loop | **KEPT** — internal actor code |
| `from k1.concierge.actors.back import route_back_envelope` | Consumer loop | **KEPT** — internal actor code |

**Zero POC imports in the factory.** All remaining imports are from `k1.*` — clean internal code.

**No circular imports detected.** The dependency graph is strictly layered (Layer 0→6). No subsystem at a lower layer imports from a higher layer.

---

#### 3.14 New Gaps

| ID | Description | Severity |
|----|-------------|----------|
| **SIM-GAP-10** | `ToolContext.cognitive_trace_id` is set once at construction (static per session). Per SIM-D-03, it should be per-turn. Factory must update `ctx.cognitive_trace_id` at the start of each turn in the consumer loop. | MEDIUM |
| **SIM-GAP-11** | `ToolContext.hil_coordinator` is wired AFTER ToolContext creation in current bootstrap (HIL is Step 22, ToolContext is Step 15). Factory must either: (a) create ToolContext with `hil_coordinator=None` and set it later, or (b) reorder to create HILCoordinator before ToolContext. Option (b) is possible — HILCoordinator is Layer 3, ToolContext is Layer 4. | LOW |
| **SIM-GAP-12** | `DeadLetterConsumer.__init__(bus)` subscribes to `TOPIC_DEAD_LETTER` **immediately** in the constructor. If created too early, it may receive events before the consumer loop starts. Factory must create it as one of the LAST steps (after subscriptions are wired). | LOW |
| **SIM-GAP-13** | `_build_experience_context(runtime)` reads from `runtime.session_state`, `runtime.fsm`, `runtime.model` — it's a closure over the entire runtime. The ConciergeSession wrapper must expose these internals to the experience tick helper. | LOW |

#### 3.15 New Flags

| ID | File | Problem | Impact |
|----|------|---------|--------|
| **SIM-FLAG-06** | `k1/concierge/kernel/bootstrap.py` lines 191–206 | `ToolContext.cognitive_trace_id` hardcoded to `f"k-front-{uuid}"` / `f"k-back-{uuid}"` at boot — not per-turn | Factory consumer loop must override per-turn (same as SIM-GAP-04 + SIM-GAP-10) |
| **SIM-FLAG-07** | `k1/concierge/kernel/bootstrap.py` lines 327–337 | `OrchestratorStub` wraps 3 private adapter classes (`_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`) defined inside bootstrap.py. Factory needs these adapters but they're private to the file. | Extract to `k1/concierge/kernel/adapters.py` or duplicate in factory |

#### 3.16 New Decisions

| ID | Question | Decision | Rationale |
|----|----------|----------|-----------|
| **SIM-D-09** | Factory return type? | **`ConciergeSession` wrapper** over `KernelRuntime` | Clean lifecycle API (start/stop). Hides 25+ field flat dataclass. Tests get simple interface. |
| **SIM-D-10** | Factory wiring sequence? | **26-step sequence (Phases A–H)**, eliminating 6 POC-coupled steps | Follows proven bootstrap order. Dependency layers enforced. No circular deps. |
| **SIM-D-11** | Where do test adapters live? | **`k1/concierge/kernel/test_adapters.py`** — all 8 fakes in one file | All < 30 lines each. Co-located with factory. No external deps. |
| **SIM-D-12** | Where do orchestrator adapter classes live? | **Extract to `k1/concierge/kernel/adapters.py`** | Currently private to bootstrap.py. Factory needs them. Shared module avoids duplication. |

---

#### 3.17 Step 3 Verdict

**✅ YES — ConciergeFactory.create_with_ports() is feasible.**

Evidence:

1. **No circular imports** — dependency graph is strictly layered (6 layers, top-to-bottom)
2. **No hidden concrete deps** — all subsystem constructors use callbacks/closures, not concrete types
3. **FSM late-wiring is graceful** — only `set_session_state()` is required, 8 others degrade gracefully
4. **ExperienceLayer stays zero-param** — SIM-GAP-08 resolved, no refactor needed
5. **All 8 test adapters are trivial** — < 30 lines each, no external deps
6. **stop() teardown is clean** — 7 guarded steps, no interdependencies
7. **Zero POC imports** in factory — `boot()` eliminated, all remaining imports are `k1.*`

**Blockers for implementation:**

1. Extract 3 private adapter classes from bootstrap.py → `adapters.py` (SIM-D-12 / SIM-FLAG-07)
2. Per-turn `cognitive_trace_id` update in consumer loop (SIM-GAP-10 / SIM-FLAG-06)
3. `DeadLetterConsumer` creation ordering — must be last (SIM-GAP-12)

**None of these are architectural blockers.** All are < 1 hour fixes each.

**Next: Step 4 — Bus Integration**

---

### STEP 4 — Integrate Bus into KernelService → Concierge

**Question:** Wire real `BusFactory.create_local()` into the `KernelService`. Does the Bus support the multi-session model from Step 1? Can Concierge's internal bus subscriptions coexist with kernel-level subscriptions?

**Assumption:** Steps 1–3 are implemented. Per-session Bus decided (SIM-D-01). ConciergeFactory accepts Bus + Router as params (SIM-D-09/D-10). 8 external ports defined. Factory wiring sequence is 26 steps (Phases A–H).

**What we read:**

| File | What we learned |
|------|----------------|
| `k1/bus/factory.py` (full) | 4 factory methods: `create_local()`, `create_local_ordered()`, `create_for_testing()`, `create_mailbox_router()`. Supports Python and Rust backends. |
| `k1/bus/core/local_bus.py` (full) | 11 internal slots, RWLock (readers=publish, writers=subscribe), TopicTrie matching, synchronous dispatch, `close()` + `sweep()` lifecycle |
| `k1/bus/core/mailbox_router.py` (full) | RLock-protected registry, WFQ 4-level priority mailboxes, `register()`/`deliver()`/`unregister()`/`close()` lifecycle |
| `k1/bus/core/envelope.py` (full) | Frozen dataclass: 12 fields including `session_id`, `cognitive_trace_id`, `request_id`, `parent_id`. FlatBuffers V2 serialization. |
| `k1/concierge/bus/topics.py` (full) | **43 topic constants**, 5 classification sets (STRICT/RELAXED/URGENT/FSM_ROUTED), priority mapping function |
| `k1/concierge/bus/builders.py` (full) | **43 builder functions** — all `build_<topic>(payload, parent_id)`, JSON-serialize + priority-stamp |
| `k1/concierge/fsm/controller.py` (subscriptions) | FSM subscribes to **20 topics** via `_subscribe_all()`, stores handles in `_subscription_handles`, cleans up in `teardown()` |
| `k1/concierge/actors/front.py` (full) | `front_handler()` publishes 5 topics. `subscribe_front_events()` subscribes to 4 topics (TASK_ACCEPTED, ORCHESTRATION_DELTA, HIL_REQUEST, PLAN_READY) |
| `k1/concierge/actors/back.py` (full) | `back_handler()`/`back_resume_handler()`/`back_cancel_handler()` publish 6 topics. Back receives ZERO direct subscriptions — FSM routes via MailboxRouter |
| `k1/concierge/fsm/dead_letter_consumer.py` | Subscribes to `TOPIC_DEAD_LETTER` in `__init__()` |
| `k1/concierge/kernel/bootstrap.py` L430–490 | `_mailbox_consumer()` — async polling loop with `receive(timeout_ms=0)` + dedup + `asyncio.sleep()` |
| `k1/bus/timing/timing_chain.py` | TimingChain: deadline-agnostic ordering. BEST_EFFORT/RELAXED/STRICT modes. Causal + sequence ordering. `sweep()` for timeout release. |

---

#### 4.1 Discovery: Bus Is Purely Synchronous — No asyncio Anywhere

`LocalBus` contains **zero** `async def`, `await`, or `asyncio` references. All operations are synchronous:

- `publish()` — synchronous, dispatches handlers on publisher's thread
- `subscribe()` — synchronous, returns `SubscriptionHandle`
- `unsubscribe()` — synchronous, returns bool
- `close()` — synchronous, sets `_closed=True`

**The asyncio boundary is in the consumer loop** (`_mailbox_consumer()`), which:

1. Calls `mailbox.receive(timeout_ms=0)` — **non-blocking** synchronous call
2. Awaits `front_handler()` / `route_back_envelope()` — async actor processing
3. Calls `asyncio.sleep(poll_interval)` — yields to event loop

**Threading safety analysis for asyncio:**

- `threading.Lock` inside `LocalBus` is **safe** in asyncio — it never blocks the event loop because:
  - `publish()` READ lock hold time: microseconds (trie walk + handler invoke)
  - `subscribe()`/`unsubscribe()` WRITE lock hold time: microseconds (trie insert/remove)
  - No I/O under lock, no async under lock, no long computation under lock
- `threading.Condition` in `LocalMailbox.receive(timeout_ms=0)` — **non-blocking** when timeout_ms=0 (immediate return if empty)

**Verdict:** Bus threading model is compatible with single asyncio event loop (SIM-D-05). No changes needed.

---

#### 4.2 Discovery: Topics Are 100% Static — No Session IDs in Topic Names

All 43 topic constants are **static strings** defined in `k1/concierge/bus/topics.py`:

```
k1.session.user.input.v1
k1.session.turn.started.v1
k1.orchestration.task.dispatch.v1
k1.orchestration.task.complete.v1
k1.response.final.v1
... (43 total)
```

**No topic contains session_id, task_id, or any runtime data.** Session scoping is achieved via `envelope.session_id` field.

**Impact on per-session Bus (SIM-D-01):** Since each session gets its own Bus instance, topic collision is **impossible by design**. Session A's `TOPIC_USER_INPUT` publishes go to Session A's bus subscribers only. No topic namespacing needed.

**If we later move to shared Bus:** Would need either:

- (a) Topic prefix per session: `sessions.{sid}.k1.session.user.input.v1` — requires builder changes
- (b) Middleware filter: handler checks `envelope.session_id` before processing
- Per SIM-D-01, we chose per-session Bus. This question is deferred.

---

#### 4.3 Discovery: Complete Subscription/Publication Map (25 subscribers, 44 publication points)

**Subscribers (25 total):**

| Component | Topics Subscribed | Count | Mechanism |
|-----------|-------------------|-------|-----------|
| FSM (`_subscribe_all()`) | USER_INPUT, FINAL_RESPONSE, TASK_DISPATCH, DAG_COMPLETED, TASK_COMPLETE, TASK_FAILED, TASK_CANCEL, TASK_SUSPENDED, TASK_RESUME, FINDINGS_READY, CLARIFICATION_REQUEST, CLARIFICATION_RESPONSE, ARTIFACT_CREATED, AFFECT_UPDATE, PROACTIVE_FILL, TOOL_STARTED, TOOL_COMPLETED, WEAVE_BATCH, UI_TYPING, + lifecycle | **20** | Direct `bus.subscribe()` |
| Front Events (`subscribe_front_events()`) | TASK_ACCEPTED, ORCHESTRATION_DELTA, HIL_REQUEST, PLAN_READY | **4** | Via routing closure → `router.deliver("front_half", env)` |
| DeadLetterConsumer | DEAD_LETTER | **1** | Direct `bus.subscribe()` in `__init__` |
| Back Actor | **(none)** | **0** | FSM sole routing authority — delivers via `router.deliver("back_half", env)` |

**Publication points: 28 distinct topics** published by FSM + actors + experience layer.

**Event flow for one turn (~12–18 bus events):**

```
user.input → turn.started → [arbiter.intent] → task.dispatch → state.updated
→ tool.started → tool.completed → task.complete → weave.decided
→ [response.stream × N] → response.final → turn.completed → state.updated
```

---

#### 4.4 Discovery: Bus Lifecycle Is Clean — Matches Per-Session Model

| Operation | LocalBus | LocalMailboxRouter |
|-----------|----------|--------------------|
| **Create** | `BusFactory.create_local()` or `create_local_ordered()` | `BusFactory.create_mailbox_router()` |
| **Wire** | `bus.subscribe(pattern, handler)` → handle | `router.register("actor_id")` → mailbox |
| **Steady state** | `bus.publish(envelope)` — sync, fan-out to all matching | `router.deliver("actor_id", env)` → mailbox |
| **Teardown** | `bus.close()` — prevents further publishes | `router.close()` — closes all mailboxes |
| **Cleanup** | Subscription handles remain (GC'd with bus) | `router.unregister("actor_id")` — drainable after |

**Per-session lifecycle:**

```
Session START:
  bus = BusFactory.create_local_ordered(capture=cfg.capture_bus)
  router = BusFactory.create_mailbox_router()
  front_mb = router.register("front_half")
  back_mb = router.register("back_half")
  → pass to ConciergeFactory.create_with_ports(bus, router, ...)

Session STOP:
  → ConciergeSession.stop() calls:
    1. Cancel consumer task
    2. FSM.teardown() → unsubscribes all 20 handles
    3. bus.close() → prevents further publishes
    4. router.close() → closes mailboxes
  → Bus + Router become GC-eligible (per-session, no shared refs)
```

**No state leaks across sessions:** Each session gets fresh Bus + Router. Sequence counters, envelope IDs, subscriptions — all scoped to the Bus instance. When the session stops and Bus is GC'd, everything is released.

---

#### 4.5 Discovery: TimingChain Ordering — Per-Session, Not Global

`BusFactory.create_local_ordered()` creates a Bus with `TimingChain` pre-wired. The chain enforces:

| Mode | Behavior | Used for |
|------|----------|----------|
| **STRICT** | Causal ordering (parent_id check) + sequence ordering (per-topic monotonic) + buffering if out of order | Session/orchestration/response topics (33 topics) |
| **RELAXED** | Deliver immediately, log if out of order | Affect, proactive, UI typing, weave, metrics (10 topics) |
| **BEST_EFFORT** | Deliver immediately, no tracking | (none currently) |

**Per-session TimingChain** means each session has its own causal ordering context. No cross-session dependency tracking. This is correct — a `parent_id` from Session A is meaningless in Session B.

**`sweep()` requirement:** The consumer loop should call `bus.sweep()` periodically to release timed-out buffered envelopes. Current bootstrap does NOT call sweep. This is a gap.

---

#### 4.6 Discovery: Mailbox WFQ Priority — 4 Levels

Mailboxes support Weighted Fair Queuing with 4 priority levels:

| Priority | Value | Topics | Latency Target |
|----------|-------|--------|----------------|
| URGENT | 0 | USER_INPUT, RESPONSE_STREAM, FINAL_RESPONSE, CLARIFICATION_OUT, TASK_CANCEL, HIL_RESPONSE | <5ms |
| REALTIME | 1 | (reserved, no current topics) | <10ms |
| INTERACTIVE | 2 | All others (default) | <50ms |
| BACKGROUND | 3 | STATE_UPDATED, AFFECT_*, PROACTIVE_*, DEAD_LETTER, BACKPOOL_*, WEAVE_*, METRIC_* | <500ms |

**Builders set priority automatically** via `get_priority(topic)` mapping. Consumer loop doesn't need to know about priority — `mailbox.receive()` returns highest-priority envelope first.

**WFQ interaction with per-session Bus:** Each session's mailboxes have independent priority queues. No cross-session priority contention. URGENT topics in Session A don't preempt URGENT topics in Session B.

---

#### 4.7 Discovery: Backpressure Model — Bounded Mailboxes, Unbounded Bus

| Layer | Bounded? | Backpressure? | Overflow behavior |
|-------|----------|---------------|-------------------|
| Bus publish | No | No | Publishes always succeed (unless closed) |
| Trie matching | No | No | All matching handlers invoked synchronously |
| Handler invocation | No | **Implicit** — slow handler blocks publisher | Publisher thread blocks until handler returns |
| Mailbox deliver | **Yes** | `BackpressureError` | Envelope rejected if mailbox at capacity |
| Mailbox receive | Yes | Blocking/timeout | `None` if timeout or non-blocking empty |

**Risk in asyncio context:** Bus `publish()` is synchronous. If a handler (e.g., FSM subscription callback) is slow, it blocks the publisher. In the consumer loop, this is fine — the loop is single-threaded, the FSM handler runs synchronously, then the loop continues.

**But:** If something else publishes on the same Bus from a different thread (e.g., a background timer), the handler runs on THAT thread. Since all FSM state mutations are non-threadsafe, this is a problem.

**Current mitigation:** All bus publishes in Concierge happen on the same async task (consumer loop → actor → tool → bus.publish). No background thread publishes exist. TimingChain `sweep()` does dispatch, but only for buffered envelopes — it calls the same handlers.

---

#### 4.8 SIM-D-13: Bus Creation Responsibility — KernelService Creates, ConciergeFactory Receives

**Decision:** KernelService creates Bus + Router per session, passes them to ConciergeFactory.

```python
# In KernelService.create_session():
bus = BusFactory.create_local_ordered(
    capture=config.capture_bus,
    middleware=self._build_middleware(session_id),   # tracing, metrics
)
router = BusFactory.create_mailbox_router()
front_mb = router.register("front_half")
back_mb = router.register("back_half")

session = await ConciergeFactory.create_with_ports(
    bus=bus, router=router,
    front_mailbox=front_mb, back_mailbox=back_mb,
    ports=ports, config=config,
)
```

**Rationale:**

1. Bus is infrastructure, not a Concierge concern — KernelService manages infrastructure
2. KernelService can inject middleware (tracing, metrics, circuit breaker) before Concierge sees the Bus
3. KernelService owns lifecycle: create on session start, close on session stop
4. Factory is simpler — receives Bus, wires subscriptions, doesn't worry about creation
5. Mailbox names (`front_half`, `back_half`) are Concierge-internal knowledge, but KernelService delegates naming to a constant

---

#### 4.9 SIM-D-14: Ordered Bus for Production, Unordered for Tests

**Decision:** Production sessions use `create_local_ordered()`. Test sessions use `create_for_testing()`.

| Mode | Factory | TimingChain | Capture | Use |
|------|---------|-------------|---------|-----|
| Production | `create_local_ordered()` | YES — STRICT topics enforced | NO | Real sessions |
| Testing | `create_for_testing()` | NO — immediate delivery | YES — all envelopes recorded | Unit/integration tests |

**Rationale:** TimingChain enforces causal ordering in production (prevents race conditions in FSM). Tests want deterministic immediate delivery + envelope recording for assertions.

---

#### 4.10 SIM-D-15: Middleware Injection Point — KernelService Level

**Decision:** Bus middleware is injected by KernelService, not ConciergeFactory.

Middleware chain for production:

```python
middleware = [
    TracingMiddleware(session_id=sid),        # Stamps cognitive_trace_id on every envelope
    MetricsMiddleware(obs_port=obs_port),     # Emits bus-level metrics via IObsPort
]
```

**Rationale:**

1. `TracingMiddleware` can auto-stamp `session_id` and `cognitive_trace_id` on every envelope — solving SIM-GAP-01 (builders don't set trace fields)
2. `MetricsMiddleware` bridges bus observability to IObsPort — no custom MetricsCollector needed (addresses SIM-FLAG-02)
3. Middleware runs inside `publish()`, before trie match — every envelope gets enriched regardless of which component published it

**Impact on SIM-GAP-01:** Resolved. TracingMiddleware enriches all envelopes automatically. Builders don't need to be modified.

---

#### 4.11 Discovery: FSM `teardown()` Properly Cleans Up Subscriptions

```python
def teardown(self):
    for handle in self._subscription_handles:
        self._bus.unsubscribe(handle)
    self._subscription_handles.clear()
```

FSM stores all subscription handles from `_subscribe_all()` and unsubscribes them in `teardown()`. This is clean — no leaked subscriptions after session stop.

**Front subscriptions** (from `subscribe_front_events()`) return a list of handles stored in `runtime.front_subscriptions`. The `stop_kernel()` function does NOT currently unsubscribe them — they're cleaned up implicitly when Bus is GC'd.

**For ConciergeSession.stop():** Should explicitly unsubscribe front subscriptions too (defense in depth), then close Bus.

---

#### 4.12 Discovery: Consumer Loop Threading Safety Analysis

The `_mailbox_consumer()` is an `asyncio.Task` that:

1. Calls `mailbox.receive(timeout_ms=0)` — synchronous, non-blocking, acquires `threading.Lock` for ~microseconds
2. Awaits `front_handler()` / `route_back_envelope()` — async, single-threaded (asyncio event loop)
3. Inside handlers: calls `bus.publish()` — synchronous, acquires `READ lock` for ~microseconds

**All Bus interaction happens on the asyncio event loop thread.** No other thread touches the Bus (unless background sweep is added). This means:

- READ lock contention: zero (single thread)
- WRITE lock contention: only during `subscribe()`/`unsubscribe()` which happen at boot/teardown, not during turns
- Mailbox lock contention: only between `deliver()` (from bus handler → routing closure) and `receive()` (from consumer loop) — both on same thread, sequential

**Verdict:** No threading issues. The locks are unnecessary in single-threaded asyncio, but they don't hurt (sub-microsecond overhead). If we later add background threads (e.g., HITL timeout watcher), the locks protect us.

---

#### 4.13 Discovery: `sweep()` Not Called — Buffered Envelopes Could Hang

Current bootstrap's `_mailbox_consumer()` loop does NOT call `bus.sweep()`. If a STRICT-mode envelope is buffered (waiting for parent or sequence predecessor), and the predecessor is lost (e.g., handler error), the envelope will remain buffered **forever** until the sweep timeout.

**Without sweep:** No safety net. A lost envelope in a STRICT topic could stall all subsequent envelopes on that topic.

**With sweep:** Periodically release timed-out envelopes with a configurable timeout (default 5000ms).

---

#### 4.14 New Gaps

| ID | Description | Severity |
|----|-------------|----------|
| **SIM-GAP-14** | `_mailbox_consumer()` does not call `bus.sweep()`. STRICT-mode envelopes buffered by TimingChain have no safety-net release. A lost envelope could stall a topic. | MEDIUM |
| **SIM-GAP-15** | `stop_kernel()` does not unsubscribe front event subscriptions (`runtime.front_subscriptions`). They're cleaned up by Bus GC, but explicit cleanup is better for per-session Bus teardown. | LOW |
| **SIM-GAP-16** | Bus handler dispatch is synchronous on publisher's thread. If FSM subscription handler is slow (e.g., triggers LLM call), it blocks the publisher. Currently safe (single-threaded asyncio), but fragile if background threads are added. | LOW |

#### 4.15 New Flags

| ID | File | Problem | Impact |
|----|------|---------|--------|
| **SIM-FLAG-08** | `k1/bus/core/local_bus.py` | `publish()` is synchronous — handler exceptions are caught/logged but the handler runs on the publisher's thread. No async handler support. | Handlers must be fast (< 1ms). Async work must be deferred to asyncio task via `loop.call_soon()` or queued. |
| **SIM-FLAG-09** | `k1/concierge/bus/builders.py` | All 43 builders accept `payload: dict` and `parent_id: int` only. No `session_id`, `cognitive_trace_id`, or `request_id` parameter. These trace fields are never set on the Envelope. | Middleware injection (SIM-D-15) solves this — TracingMiddleware auto-stamps trace fields. |

#### 4.16 New Decisions

| ID | Question | Decision | Rationale |
|----|----------|----------|-----------|
| **SIM-D-13** | Who creates the Bus? | **KernelService creates, ConciergeFactory receives** | Bus is infrastructure. KernelService injects middleware (tracing, metrics). Factory wires subscriptions only. |
| **SIM-D-14** | Ordered or unordered Bus? | **Ordered (TimingChain) for production, unordered for tests** | STRICT topics enforce causal ordering in production. Tests want deterministic immediate delivery + capture. |
| **SIM-D-15** | Where to inject tracing/metrics on Bus? | **TracingMiddleware at KernelService level** | Auto-stamps session_id + cognitive_trace_id on EVERY envelope. Solves SIM-GAP-01 without modifying 43 builders. |
| **SIM-D-16** | How to handle TimingChain sweep? | **Consumer loop calls `bus.sweep()` every iteration when `did_work=False`** | Minimal overhead (no-op when no buffered envelopes). Releases timed-out STRICT envelopes as safety net. |

---

#### 4.17 Step 4 Verdict

**✅ YES — Bus integrates cleanly into per-session KernelService → ConciergeFactory model.**

Evidence:

1. **Per-session Bus works perfectly** — all 43 topics are static strings, no session IDs in topic names, no cross-session state
2. **Threading model is safe** — `threading.Lock` in Bus is compatible with asyncio (sub-microsecond hold, never blocks event loop)
3. **Lifecycle is clean** — create → wire → use → teardown → GC, no leaked state
4. **FSM subscription cleanup works** — `teardown()` unsubscribes all 20 handles
5. **TimingChain is per-session** — causal ordering context scoped to Bus instance
6. **WFQ mailbox priority is per-session** — no cross-session priority contention
7. **Middleware solves trace field gap** — SIM-GAP-01 resolved by TracingMiddleware
8. **No code changes needed in Bus or Concierge** — KernelService creates Bus, passes to factory, done

**Blockers for implementation:**

1. Add `bus.sweep()` call to consumer loop (SIM-GAP-14 / SIM-D-16) — 1 line
2. Add explicit front subscription unsubscribe in `ConciergeSession.stop()` (SIM-GAP-15) — 3 lines
3. Write `TracingMiddleware` that auto-stamps trace fields (SIM-D-15) — ~30 lines

**None are architectural blockers. All are < 30 minutes each.**

**Resolved from prior steps:** SIM-GAP-01 (trace fields on envelopes) — resolved by TracingMiddleware (SIM-D-15).

**Next: Step 5 — SessionState Integration**

---

### STEP 5 — Integrate SessionState

**Question:** Wire `SessionStateFactory.create_with_ports()` into kernel, inject into Concierge via `IStatePort` adapter. Does the 5-port SS factory align with what Concierge actually needs?

**Assumption:** Steps 1–4 implemented. Per-session Bus with TimingChain (SIM-D-14). KernelService creates Bus (SIM-D-13). TracingMiddleware auto-stamps trace fields (SIM-D-15). Factory wiring sequence established (SIM-D-10).

**What we read:**

| File | What we learned |
|------|----------------|
| `k1/sessionstate/factory.py` (full 400 lines) | 3 factory modes: `create_standalone()`, `create_for_testing()`, `create_with_ports()`. Production mode takes 5 ports (IStoragePort, IEventPort, IWriterPort, ILifecyclePort, IK0SyncPort optional) |
| `k1/sessionstate/manager.py` (full 1240 lines) | `SessionStateManager.__init__()` takes 6 params. Has `start()/stop()` lifecycle, `get_section()` for reads, `mutate()` for writes, `get_snapshot()` for diagnostics. RLock for writes, lock-free reads. |
| `k1/sessionstate/ports/__init__.py` | 5 port interfaces exported: IStoragePort, IEventPort, IWriterPort, ILifecyclePort, IK0SyncPort |
| `k1/sessionstate/ports/storage.py` | `IStoragePort` — archive, restore, checkpoint persistence (SQLite or in-memory) |
| `k1/sessionstate/ports/writer.py` | `IWriterPort` — `request_mutation()`, `batch_mutations()`. MutationPriority enum, MutationStatus lifecycle, RejectionCategory |
| `k1/sessionstate/ports/events.py` | `IEventPort` — `emit(event_type, payload)`, `subscribe(event_type, handler)`. Fire-and-forget events |
| `k1/sessionstate/ports/lifecycle.py` | `ILifecyclePort` — state machine (CREATED→STARTING→RUNNING→STOPPING→STOPPED→ERROR). CheckpointTrigger variants |
| `k1/sessionstate/sizetracker.py` | 15 sections total: 10 HOT (52KB) + 5 WARM (48KB). `ALL_SECTIONS`, `HOT_SECTIONS`, `WARM_SECTIONS` frozen sets. Per-section budgets. |
| `k1/sessionstate/sections/` (16 files) | One class per section: control, beliefs_active, scoreboard, history_active, clarifications, affective_now, narrative_active, meta, task_state, task_artifacts, beliefs_history, history_recent, persona, telemetry, artifacts_warm, temporal_context |
| All Concierge SS access patterns | 100+ `get_section()` calls across FSM, actors, tools, prompt builder, delta, experience |

---

#### 5.1 Discovery: SessionState Has 5 Ports — Concierge Uses 2 Directly

The SS factory accepts 5 ports. Analysis of how Concierge interacts with SS:

| SS Port | What it does | Concierge usage | Who provides in production |
|---------|-------------|-----------------|---------------------------|
| **IStoragePort** | Persistence (archive/restore/checkpoint to SQLite) | **NOT directly** — SSM handles internally | KernelService (SQLiteStorageAdapter) |
| **IEventPort** | SS event emission (mutation approved, eviction, emergency) | **NOT directly** — SSM emits internally | KernelService (LocalEventAdapter or BusEventAdapter) |
| **IWriterPort** | Mutation routing (request_mutation, batch_mutations) | **YES** — `ToolContext.writer_port` = this | ConciergeFactory (DirectWriterAdapter wrapping SSM) |
| **ILifecyclePort** | start/stop/checkpoint state machine | **NOT directly** — KernelService calls start/stop | KernelService (StandaloneLifecycle) |
| **IK0SyncPort** | Optional K0 cloud sync | **NOT used** — future scope | None (optional) |

**Key insight:** Concierge only touches 2 of 5 SS ports:

1. **IWriterPort** — exposed as `ToolContext.writer_port` for tool mutations
2. **SSM.get_section()** — the read API (not a port, it's on the manager itself)

The other 3 ports (storage, events, lifecycle) are infrastructure that KernelService manages.

---

#### 5.2 Discovery: Complete Section Inventory — 15 Sections, All Aligned

| Section | Tier | Budget | Concierge Uses? | Access Pattern |
|---------|------|--------|-----------------|----------------|
| **control** | HOT | 8KB | YES | Read: `get_metadata()`, `.fsm_overlay`. Write: FSM direct |
| **beliefs_active** | HOT | 8KB | YES | Read: `find_by_subject()`, `list_facts()`. Write: via writer_port |
| **scoreboard** | HOT | 6KB | YES | Read: `get_primary_topic()`, `list_referents()`. Write: via writer_port |
| **history_active** | HOT | 8KB | YES | Read: `format_for_prompt(n)`. Write: `.add_turn()` (FSM history sink) |
| **clarifications** | HOT | 4KB | YES | Read: `list_pending()`, `get_blocking()`. Write: via writer_port |
| **affective_now** | HOT | 4KB | YES | Read: `.current_emotion`, `.intensity`. Write: via writer_port + **DIRECT** (`._tone_adjustment`, `._response_style`) |
| **narrative_active** | HOT | 4KB | YES | Read: `get_thread()`, `._primary_thread`. Write: via writer_port |
| **meta** | HOT | 2KB | YES | Read: generic attribute access |
| **task_state** | HOT | 4KB | YES | Read: `.to_prompt()`. Write: FSM direct binding |
| **task_artifacts** | HOT | 4KB | YES | Read: `.to_prompt()`. Write: FSM direct binding |
| **beliefs_history** | WARM | 12KB | NO | Demote target for beliefs_active eviction |
| **history_recent** | WARM | 20KB | NO | Demote target for history_active eviction |
| **persona** | WARM | 8KB | YES | Read-only: `get_all_preferences()` |
| **telemetry** | WARM | 8KB | NO | Internal metrics (first to evict) |
| **artifacts_warm** | WARM | 8KB | NO | Demote target for task_artifacts eviction |

**All 12 section names used by Concierge exist in `k1/sessionstate/sections/`. Zero mismatches.**

**temporal_context** appears in PromptBuilder but maps to a virtual view of the `control` section — not a separate section.

---

#### 5.3 Discovery: SSM Duck-Type Interface — What Concierge Actually Calls

Concierge code accesses SSM via the `ss` parameter (typed as `Any`). The complete duck-type interface:

**Methods called on SSM:**

| Method | Called from | Frequency |
|--------|-----------|-----------|
| `get_section(name: str) → Any` | Everywhere (100+ calls) | Every turn, multiple times |
| `guard.preflight(section, op, size)` | DeltaApplicator, tool implementations | Per mutation |
| `close()` (actually `stop()`) | `stop_kernel()` via `hasattr` guard | Once at session end |

**Methods called on sections (returned by `get_section()`):**

| Section | Methods/Attributes | Pattern |
|---------|-------------------|---------|
| beliefs_active | `find_by_subject()`, `get_fact()`, `list_facts()`, `get_fact_count()`, `get_pinned_fact_ids()` | Read API |
| scoreboard | `get_primary_topic()`, `get_open_commitments()`, `list_referents()`, `get_referents()` | Read API |
| clarifications | `list_pending()`, `get_pending()`, `get_blocking()` | Read API |
| narrative_active | `get_thread()`, `get_active_thread_name()`, `._primary_thread`, `._thread_index` | Read + private attrs |
| affective_now | `.current_emotion`, `.intensity`, `.valence`, `.arousal`, `._tone_adjustment =`, `._response_style =` | Read + **DIRECT WRITE** |
| history_active | `format_for_prompt(n=window)`, `.add_turn()` | Read + write sink |
| task_state | `.to_prompt()`, `.to_slim_prompt()` | Read API |
| task_artifacts | `.to_prompt()`, `.to_slim_prompt()` | Read API |
| persona | `get_all_preferences()` | Read-only |
| control | `get_metadata()`, `.fsm_overlay` | Read + FSM binding |
| meta | Generic attribute access | Read-only |

---

#### 5.4 Discovery: IStatePort Adapter Is NOT a Wrapper Around SSM — It IS the SSM

**Critical realization:** The `IStatePort` from kernel.md §89 was designed to abstract SessionState. But Concierge code calls **100+ methods on 12 different section objects**, each with unique method signatures (`find_by_subject()`, `format_for_prompt()`, `to_prompt()`, etc.).

An `IStatePort` wrapper would need to proxy **every section method** — creating a massive, fragile wrapper that duplicates the entire SSM API. This violates SIM-D-07 (internal ports stay untouched).

**The correct approach:** IStatePort IS the SessionStateManager. The "port" is not a new wrapper — it's the SSM instance itself, created by KernelService using `SessionStateFactory.create_with_ports()` and passed to ConciergeFactory.

This aligns with how the current bootstrap works: `session_state` is created, then passed directly to every subsystem that needs it.

---

#### 5.5 SIM-D-17: IStatePort ≡ SessionStateManager (No Wrapper)

**Decision:** IStatePort in the kernel wiring is the `SessionStateManager` instance itself. No adapter/wrapper needed.

**Factory flow:**

```python
# KernelService creates SSM with production ports:
ssm = SessionStateFactory.create_with_ports(
    session_id=session_id,
    storage=SQLiteStorageAdapter(db_path),
    events=BusEventAdapter(bus),             # Bridges SS events → Bus
    writer=DirectWriterAdapter(manager=ssm, guard=ssm.mutation_guard),
    lifecycle=StandaloneLifecycle(manager=ssm),
)
ssm.start()

# ConciergeFactory receives SSM directly:
session = await ConciergeFactory.create_with_ports(
    bus=bus, router=router,
    ports=ExternalPorts(state=ssm, ...),   # SSM IS the state port
    config=config,
)
```

**Rationale:**

1. SSM already has the exact API Concierge needs (`get_section()`, `guard`, properties)
2. Wrapping would create a massive proxy (100+ methods across 12 sections)
3. SSM is per-session (SIM-D-04), so passing it directly is clean
4. The 5 SS ports (storage/events/writer/lifecycle/k0_sync) are **SSM's** ports, not Concierge's
5. KernelService wires SSM's ports. ConciergeFactory receives the assembled SSM.

---

#### 5.6 SIM-D-18: SSM Lifecycle Ownership — KernelService Manages

**Decision:** KernelService calls `ssm.start()` before creating ConciergeSession, and `ssm.stop()` after ConciergeSession.stop().

| Operation | Who | When |
|-----------|-----|------|
| `SessionStateFactory.create_with_ports()` | KernelService | Session creation |
| `ssm.start()` | KernelService | Before ConciergeFactory.create_with_ports() |
| Pass `ssm` to ConciergeFactory | KernelService | During session creation |
| Concierge reads/writes via `ssm.get_section()` / `writer_port` | ConciergeSession | During turns |
| `ssm.stop()` (final checkpoint + cleanup) | KernelService | After ConciergeSession.stop() |

**Rationale:** SSM has its own lifecycle state machine (CREATED→STARTING→RUNNING→STOPPING→STOPPED). KernelService manages this lifecycle, ensuring SSM is RUNNING before any Concierge code touches it.

---

#### 5.7 Discovery: WriterPort Circular Reference — Factory Must Handle

The `DirectWriterAdapter` constructor requires a reference to the SSM it wraps:

```python
writer_adapter = DirectWriterAdapter(
    manager=manager,           # ← needs SSM
    guard=manager.mutation_guard,
    writer_id="direct",
)
```

But `SessionStateFactory.create_with_ports()` requires the writer port as a parameter:

```python
manager = SessionStateFactory.create_with_ports(
    ...,
    writer=writer_adapter,     # ← needs writer, which needs manager
    ...
)
```

**Current resolution in `create_standalone()`:** Creates SSM first with `writer_port=None`, then creates DirectWriterAdapter with SSM reference, then injects via `manager._writer_port = writer_adapter`.

**For production:** Same pattern. KernelService creates SSM with `writer_port=None`, creates DirectWriterAdapter, then injects. OR uses `create_standalone()` / `create_for_testing()` which handle this internally.

---

#### 5.8 Discovery: Two Direct-Write Violations on affective_now

Bootstrap writes directly to `affective_now` section attributes, bypassing `writer_port`:

```python
# bootstrap.py L513 — ExperienceLayer result
section._tone_adjustment = tone_dict

# bootstrap.py L525 — RhythmController result
section._response_style = style.__dict__
```

These are set by ExperienceLayer tick, read by PromptBuilder next turn. They bypass MutationGuard — no size tracking, no capacity check.

**Impact:** Minor. These are small dicts (<100 bytes). The `_tone_adjustment` and `_response_style` are transient per-turn values, not persisted data. They're effectively "scratch space" on the section object.

**For the factory:** Replicate this pattern exactly. The experience tick helper writes directly to the section. No change needed.

---

#### 5.9 Discovery: Prompt Builder Section Access — 11 Sections, Mode-Dependent

PromptBuilder reads different subsets of sections depending on the conversation mode:

| Mode | Sections Read | Count |
|------|---------------|-------|
| STANDARD | All HOT + persona | 11 |
| HITL_RELAY | Minimal: temporal_context, affective_now, control, persona, task_state | 5 |
| CLARIFY_ASK | Excludes scoreboard, narrative_active, task_state, task_artifacts | 8 |
| PRESENT | Excludes scoreboard, clarifications | 9 |
| ERROR | Minimal: excludes beliefs, scoreboard, clarifications | 8 |

**All reads are defensive** — `hasattr()` guards on every attribute, returns empty string if missing. Never raises exceptions.

**Impact on IStatePort:** None. PromptBuilder calls `ss.get_section(name)` and then reads attributes on the returned section object. The section objects are the same regardless of how SSM was created.

---

#### 5.10 Discovery: DeltaApplicator — Closure-Based SS Access

`DeltaApplicator.__init__()` takes 4 callback params (from Step 3 audit):

```python
DeltaApplicator(
    preflight_fn=lambda section, op, size: ssm.guard.preflight(section, op, size),
    write_fn=lambda section, op, key, data: ssm.get_section(section).apply(op, key, data),
    evict_fn=lambda section, limit: ssm.eviction_engine.evict(section, limit),
    notify_fn=lambda section, seq: bus.publish(build_state_updated(...)),
)
```

**Impact:** DeltaApplicator never holds a direct reference to SSM. It uses closures. The factory creates these closures over the SSM instance. Clean — no coupling.

---

#### 5.11 Discovery: SSM Threading Model — Compatible with Asyncio

SSM uses `threading.RLock` for write serialization and lock-free reads:

| Operation | Locking | Thread Safety |
|-----------|---------|---------------|
| `get_section()` | Lock-free | Multi-reader safe |
| `mutate()` | RLock | Serialized writes |
| `get_snapshot()` | Lock-free | Uses SizeTracker snapshot |
| `start()/stop()` | State machine guards | Single-caller expected |

**Asyncio compatibility:** Same analysis as Bus (Step 4). RLock hold time is sub-millisecond (in-memory operations). Never blocks event loop. Reads are completely lock-free (<1ms guaranteed).

---

#### 5.12 New Gaps

| ID | Description | Severity |
|----|-------------|----------|
| **SIM-GAP-17** | `bootstrap.py` calls `session_state.close()` but SSM has `stop()`, not `close()`. Current code uses `hasattr(ss, "close")` guard — works because SSM doesn't have `close()`, so it's skipped. Factory should call `ssm.stop()` explicitly. | LOW |
| **SIM-GAP-18** | `affective_now` section has 2 direct attribute writes (`_tone_adjustment`, `_response_style`) that bypass MutationGuard and SizeTracker. Small impact (~100 bytes) but violates single-writer pattern. | LOW |
| **SIM-GAP-19** | `SessionStateFactory.create_with_ports()` has circular reference: DirectWriterAdapter needs SSM, but SSM constructor needs writer_port. Current workaround: create with `writer_port=None`, then inject. This pattern must be documented for KernelService. | LOW |

#### 5.13 New Flags

| ID | File | Problem | Impact |
|----|------|---------|--------|
| **SIM-FLAG-10** | `k1/sessionstate/factory.py` L45 | `from poc.k1_poc.config import get_config` — SS factory imports POC config | Must be changed to `from k1.concierge.config import get_config` or config injection. Same POC coupling as SIM-FLAG-01. |

#### 5.14 New Decisions

| ID | Question | Decision | Rationale |
|----|----------|----------|-----------|
| **SIM-D-17** | Is IStatePort a wrapper around SSM? | **NO — IStatePort IS the SSM instance. No wrapper needed.** | Concierge calls 100+ methods across 12 section objects. Wrapping would create massive fragile proxy. SSM already has the exact API. |
| **SIM-D-18** | Who manages SSM lifecycle (start/stop)? | **KernelService** — calls `start()` before ConciergeFactory, `stop()` after ConciergeSession.stop() | SSM has its own lifecycle state machine. KernelService ensures RUNNING state before Concierge touches it. |
| **SIM-D-19** | Which SS factory mode for production? | **`create_standalone()` initially, `create_with_ports()` when Bridge adapters exist** | Standalone mode works fully offline (SQLite LOCAL COLD). Production ports (BridgeStorage, DeltaBusAdapter) are future scope. |

---

#### 5.15 Step 5 Verdict

**✅ YES — SessionState integrates cleanly. No wrapper needed.**

Evidence:

1. **All 12 section names used by Concierge exist in SSM** — zero mismatches
2. **SSM IS the IStatePort** — no wrapper needed (SIM-D-17), eliminating the biggest risk from Step 2 (SIM-GAP-07)
3. **SSM has per-session lifecycle** — `start()`/`stop()` with checkpoint. Matches per-session model (SIM-D-04)
4. **Thread-safe reads** — lock-free `get_section()` < 1ms, compatible with asyncio
5. **DeltaApplicator uses closures** — no direct SSM coupling, factory creates closures cleanly
6. **Writer port pattern works** — `DirectWriterAdapter` is created with SSM reference, injected after construction
7. **Section duck-type is stable** — PromptBuilder uses `hasattr()` guards, never raises on missing attributes
8. **Only 1 POC import** — `factory.py` imports `poc.k1_poc.config` (SIM-FLAG-10), same pattern as bootstrap

**Resolved from prior steps:**

- **SIM-GAP-07** (actors receive `ss: Any`, no Protocol contract) — RESOLVED. SSM is passed directly, no adapter needed. The 100+ method calls all work because they call real SSM methods.
- **SIM-GAP-08** was already resolved in Step 3 (ExperienceLayer zero-param is fine)

**Blockers:** None. SSM integration is the cleanest of all components — it's already designed for this exact usage pattern.

**Next: Step 6 — Fabric + ModelHub Integration**

---

### STEP 6 — Integrate Fabric + ModelHub

**Question:** Wire `FabricFactory.create_with_ports()` and `ModelHubFactory.create_standalone()` into kernel, inject into Concierge via `IFabricPort` and `IModelHubPort` (≈ `ILLMPort`). The current bootstrap passes TEST adapters to Fabric — what real adapters do we need?

**Assumption:** Steps 1–5 implemented. SSM IS the IStatePort (SIM-D-17). KernelService manages SSM lifecycle (SIM-D-18). Per-session Bus with TracingMiddleware (SIM-D-15).

**What we read:**

| File | What we learned |
| ---- | --------------- |
| `k1/fabric/factory.py` (full 730 lines) | 3 factory modes. `create_with_ports()` takes 6 ports + optional `embedding_port`. 20-step dependency-safe construction. Returns `Fabric` container with `execute()`, `discover_capabilities()` delegates. |
| `k1/fabric/ports/` (6 port ABCs) | ISessionStateReader, IEventPort, IBridgePort, IModelGatewayPort, IPromptSystemPort, IDeltaBusPort — all `@runtime_checkable Protocol` |
| `k1/fabric/fabric.py` — `Fabric` class | Container with convenience delegates: `execute()`, `execute_batch()`, `discover_capabilities()`, `find_relevant_prompts()`, `register()`, `unregister()`, `shutdown()` |
| `k1/fabric/adapters/` (12 files) | 6 test adapters + 2 auto-discovery (MCP/WASM) + `sessionstate_reader.py` (production SSM adapter) + `bridge_connection.py` |
| `k1/model_hub/factory.py` (full 460 lines) | 3 factory modes. `create_standalone()` needs NO external ports (self-contained). `create_with_ports()` takes `{"credential_port": ...}` dict. Returns `_HubCore` implementing `IModelHubPort`. |
| `k1/model_hub/ports/` (7 port ABCs) | IModelHubPort, IEventPort, IStateReadPort, IMetricsPort, IConfigPort, ICredentialPort, IHealthPort |
| `k1/model_hub/ports/hub_port.py` | `IModelHubPort`: `execute(HubRequest)→HubResponse`, `stream_execute(HubRequest)→AsyncIterator[HubChunk]`, `discover_capabilities()`, `discover_models()`, `health()` |
| `k1/concierge/fabric/ports.py` | `IFabricPort` Protocol: `execute()`, `execute_batch()`, `discover_capabilities()`, `find_relevant_prompts()` — uses K1 Fabric types directly |
| `k1/concierge/kernel/bootstrap.py` | Fabric: `FabricFactory.create_with_ports(bridge=POCMockBridge, ...5 test adapters)`. ModelHub: `ModelHubPOCBridge(GeminiConciergeAdapter)` — NO ModelHubFactory used |
| `k1/concierge/tools/implementations.py` | Tools call `ctx.fabric_port.execute(CapabilityRequest)` and `ctx.fabric_port.discover_capabilities(intent=...)` — uses K1 Fabric types |
| `k1/concierge/react/loop.py` | react_loop calls `model.execute(HubRequest)` and `model.stream_execute(HubRequest)` — uses K1 ModelHub types |
| `k1/concierge/orchestrator/types.py` | POC-local `CapabilityRequest(name=...)` / `CapabilityResult(error: str)` — different from K1 Fabric `CapabilityRequest(capability_name=...)` / `CapabilityResult(error: ErrorInfo)` |
| `k1/concierge/orchestrator/stub.py` | `OrchestratorStub(fabric_gateway, state_read, delta_emit)` — 3 ports. `_FabricGatewayAdapter` translates POC types ↔ K1 Fabric types at boundary |
| `k1/concierge/llm/model_hub_bridge.py` | `ModelHubPOCBridge` implements `IModelHubPort`, wraps `GeminiConciergeAdapter` |

---

#### 6.1 Discovery: Fabric Has 6 Ports — Adapter Inventory

| Fabric Port | Purpose | Bootstrap Today | Production Adapter Exists? | What KernelService Provides |
| ----------- | ------- | --------------- | -------------------------- | --------------------------- |
| **ISessionStateReader** | Read-only SS access (FAB-01) | `TestSessionStateReaderAdapter` | **YES** — `k1/fabric/adapters/sessionstate_reader.py` wraps real SSM | `SessionStateReaderAdapter(ssm)` — wraps SSM from Step 5 |
| **IEventPort** | Fabric event emission | `LocalEventAdapter(capture=True)` | **YES** — `LocalEventAdapter` works for both modes | `LocalEventAdapter(capture=False)` or `BusBridgeEventAdapter(bus)` |
| **IBridgePort** | K0 access via Bridge | `POCMockBridgeAdapter(registry)` | **PARTIAL** — `bridge_connection.py` exists but is stub-like | `POCMockBridgeAdapter` until real Bridge (Step 8) |
| **IModelGatewayPort** | LLM for Agent Factory | `TestModelGatewayAdapter` | **NO** — needs adapter wrapping ModelHub | `ModelHubGatewayAdapter(model_hub)` — NEW, wraps IModelHubPort |
| **IPromptSystemPort** | Prompt templates | `TestPromptSystemAdapter` | **NO** — needs production adapter | `TestPromptSystemAdapter` initially — prompt system is future scope |
| **IDeltaBusPort** | Agent delta emission | `TestDeltaBusAdapter` | **NO** — needs adapter bridging to Bus | `BusDeltaAdapter(bus)` — NEW, publishes deltas as Bus envelopes |

**Summary:** 2 of 6 production adapters exist. 2 need creation. 2 can use test adapters initially.

---

#### 6.2 Discovery: Fabric Container Satisfies IFabricPort Structurally

The `Fabric` class exposes:

- `execute(request: CapabilityRequest) → CapabilityResult`
- `execute_batch(requests, strategy) → List[CapabilityResult]`
- `discover_capabilities(domain, intent, ...) → RetrievalResult`
- `find_relevant_prompts(intent, domain, ...) → RetrievalResult`

The `IFabricPort` Protocol expects exactly these 4 methods with the same types. **Fabric IS the IFabricPort — no adapter needed.**

This matches the SIM-D-17 pattern (SSM IS the IStatePort). The Fabric container is injected directly into `ToolContext.fabric_port`.

---

#### 6.3 SIM-D-20: Fabric Injection = Fabric Container Directly

**Decision:** The `Fabric` instance returned by `FabricFactory` IS the `IFabricPort`. Pass it directly to ConciergeFactory.

**Factory flow:**

```python
# KernelService creates Fabric with production adapters:
fabric = FabricFactory.create_with_ports(
    state_reader=SessionStateReaderAdapter(ssm),   # ← wraps SSM (Step 5)
    event_port=LocalEventAdapter(capture_mode=False),
    bridge=poc_bridge,                              # ← POCMockBridge until Step 8
    model_gateway=ModelHubGatewayAdapter(model_hub), # ← wraps ModelHub
    prompt_system=TestPromptSystemAdapter(),         # ← test until prompt system built
    delta_bus=BusDeltaAdapter(bus),                  # ← bridges to per-session Bus
    production_mode=True,
)

# Register capabilities (40 POC caps → CapabilityContract)
for contract in convert_all_poc_capabilities():
    fabric.register(contract)

# ConciergeFactory receives Fabric directly:
session = await ConciergeFactory.create_with_ports(
    bus=bus, router=router,
    ports=ExternalPorts(
        state=ssm,           # SSM directly (SIM-D-17)
        fabric=fabric,       # Fabric directly (SIM-D-20)
        llm=model_hub,       # ModelHub directly (SIM-D-21)
        ...
    ),
    config=config,
)
```

**Rationale:**

1. Fabric container's `execute()` / `discover_capabilities()` match `IFabricPort` exactly
2. Tools already use K1 Fabric types (`CapabilityRequest`, `CapabilityResult`) — no translation needed
3. Zero-change swap from POC bridge → real capabilities when contracts mature

---

#### 6.4 Discovery: ModelHub Is Self-Contained — Minimal Integration

ModelHub has its own factory with 3 modes. Key findings:

| Aspect | Detail |
| ------ | ------ |
| **create_standalone()** | Takes ZERO external ports. Creates all internal services. Returns `_HubCore` implementing `IModelHubPort`. |
| **create_with_ports()** | Only REQUIRED port: `credential_port`. All others optional. |
| **IModelHubPort** | 5 methods: `execute()`, `stream_execute()`, `discover_capabilities()`, `discover_models()`, `health()` |
| **Concierge usage** | react_loop calls `model.execute(HubRequest)` and `model.stream_execute(HubRequest)` — 2 of 5 methods |
| **Current wiring** | Bootstrap uses `ModelHubPOCBridge(GeminiConciergeAdapter)` — bypasses factory entirely |
| **Provider registration** | ModelHub has its own `ProviderRegistry` + plugin system — separate from Fabric's capability registry |

---

#### 6.5 SIM-D-21: ModelHub Via Factory, Not POC Bridge

**Decision:** Use `ModelHubFactory.create_standalone()` for the `ILLMPort` / `IModelHubPort`. Retire `ModelHubPOCBridge`.

**Factory flow:**

```python
# KernelService creates ModelHub:
model_hub = ModelHubFactory.create_standalone(
    config=ModelHubConfig(
        rate_limit_headroom_pct=10,
        # ... provider-specific config
    ),
    plugins={"gemini": GeminiPlugin(api_key=os.getenv("GOOGLE_API_KEY"))},
)

# Pass to ConciergeFactory as ILLMPort:
# react_loop receives model_hub and calls execute()/stream_execute()
```

**Rationale:**

1. `create_standalone()` wires 11 internal services correctly (circuit breaker, rate limiter, cost tracker, cache, etc.)
2. `ModelHubPOCBridge` duplicates this wiring poorly — no circuit breaker, no rate limiting, no cost tracking
3. Hub is **shared across sessions** (SIM-D-04) — stateless request-reply pattern, thread-safe
4. Plugin system allows Gemini/local model registration without code changes

---

#### 6.6 Discovery: Two Type Universes — Tools vs Orchestrator

A critical finding: there are **two parallel type systems** for capability requests:

| Consumer | Types Used | Where Defined | Translation Layer |
| -------- | ---------- | ------------- | ----------------- |
| **Tools** (implementations.py) | K1 `CapabilityRequest(capability_name=...)`, `CapabilityResult(error: ErrorInfo)` | `k1.fabric.types` | **NONE** — uses K1 types directly on Fabric |
| **OrchestratorStub** | POC `CapabilityRequest(name=...)`, `CapabilityResult(error: str)` | `k1.concierge.orchestrator.types` | `_FabricGatewayAdapter` translates at boundary |

| Field | POC Orchestrator | K1 Fabric | Impact |
| ----- | ---------------- | --------- | ------ |
| Request name field | `name` | `capability_name` | `_FabricGatewayAdapter.execute()` maps `name → capability_name` |
| Result error type | `str` | `Optional[ErrorInfo]` with `.code`, `.message`, `.retriable` | Adapter extracts `.message`, loses `.code` and `.retriable` |
| Routing fields | absent | `tier`, `wfq_priority`, `safety_band`, `timeout_ms` | Fabric defaults used (MEDIUM tier, INTERACTIVE priority) |
| Timing fields | `duration_ms` only | `duration_ms` + `retrieval_time_ms` + `resolution_time_ms` + `execution_time_ms` | 3 timing fields lost in translation |

**The `_FabricGatewayAdapter` in bootstrap.py handles this translation.** It's defined as an inner class of bootstrap (SIM-FLAG-07). Per SIM-D-12, it moves to `k1/concierge/kernel/adapters.py`.

---

#### 6.7 Discovery: Fabric's IModelGatewayPort ≠ ModelHub's IModelHubPort

These are two DIFFERENT port interfaces for LLM access:

| Port | Module | Methods | Purpose |
| ---- | ------ | ------- | ------- |
| `IModelGatewayPort` | `k1.fabric.ports` | `create_handle()`, `release_handle()`, `query()` | Agent Factory grants LLM handles to spawned agents |
| `IModelHubPort` | `k1.model_hub.ports` | `execute()`, `stream_execute()`, `discover_capabilities()` | Direct request-reply LLM access |

**Concierge uses IModelHubPort** (via react_loop → `model.execute(HubRequest)`).
**Fabric uses IModelGatewayPort** (for Agent Factory → spawned agent LLM access).

**They serve different roles:**

- `IModelHubPort` is the **kernel-level** LLM port (≈ `ILLMPort` from kernel.md §89). KernelService creates it, passes to ConciergeFactory, react_loop uses it.
- `IModelGatewayPort` is **Fabric-internal**. Only used by Fabric's Agent Provider to grant LLM to spawned capability agents. Concierge never touches it.

---

#### 6.8 SIM-D-22: ModelHub Shared, Fabric Per-Session

**Decision:** ModelHub is shared across sessions. Fabric is per-session.

| Component | Instance Model | Rationale |
| --------- | -------------- | --------- |
| **ModelHub** | Shared (one per process) | Stateless request-reply. Rate limiter + circuit breaker are per-provider (global). Cost tracker is global. |
| **Fabric** | Per-session | Fabric's ISessionStateReader is bound to one SSM (per-session). Fabric's PolicyEngine reads session-specific affective/cognitive state. |

This means:

1. KernelService creates ModelHub at startup (once)
2. KernelService creates Fabric per session (with session-specific SSM adapter)
3. Both Fabric and ModelHub are injected into ConciergeFactory per session

---

#### 6.9 Discovery: Fabric Requires 40 Capability Registrations Post-Construction

After `FabricFactory.create_with_ports()`, bootstrap calls:

```python
for contract in convert_all_poc_capabilities():
    fabric.register(contract)
```

This registers 40 POC capabilities (family, web, demo) as `CapabilityContract` objects. The factory then calls `_auto_register_providers()` to wire contract → provider mappings.

**KernelService must do the same.** This is a post-factory step that loads the capability catalog.

**Future:** Capabilities loaded from `k1/contracts/` directory via `ModuleLoader.start()` (already part of factory's step 20). Once real contracts exist on disk, the manual registration loop disappears.

---

#### 6.10 Discovery: Fabric's Bridge Port — POCMockBridgeAdapter Stays Until Step 8

The `IBridgePort` interface expects:

- `send_command(operation, payload, *, trace_id, timeout_ms) → BridgeCommandResult`
- `query(operation, selectors, *, trace_id, timeout_ms) → BridgeCommandResult`
- `route_ifl(route: IFLRoute, payload, *, trace_id) → BridgeCommandResult`
- `is_available() → bool`
- `get_health() → BridgeHealth`

`POCMockBridgeAdapter` satisfies this structurally. It routes commands through the in-memory `CapabilityRegistry` (mock execution). The real Bridge adapter (Step 8) will replace this.

---

#### 6.11 New Adapters Required (2)

**1. ModelHubGatewayAdapter** — Bridges `IModelGatewayPort` → `IModelHubPort`

```python
class ModelHubGatewayAdapter:
    """Wraps IModelHubPort to satisfy IModelGatewayPort for Fabric's Agent Provider."""

    def __init__(self, hub: IModelHubPort) -> None:
        self._hub = hub

    async def create_handle(self, *, capabilities, max_tokens, trace_id) -> ILLMHandle:
        # Returns a handle that delegates to hub.execute()
        ...

    async def release_handle(self, handle: ILLMHandle) -> None:
        # No-op (hub manages lifecycle internally)
        ...
```

~30 lines. Bridges the handle-based Fabric Agent API → request-reply ModelHub API.

**2. BusDeltaAdapter** — Bridges `IDeltaBusPort` → per-session Bus

```python
class BusDeltaAdapter:
    """Wraps LocalBus to satisfy IDeltaBusPort for Fabric's Agent Provider."""

    def __init__(self, bus: LocalBus) -> None:
        self._bus = bus

    async def emit_delta(self, payload: DeltaPayload) -> None:
        envelope = build_agent_delta_emitted(
            agent_id=payload.agent_id,
            delta_type=payload.delta_type,
            data=payload.data,
        )
        self._bus.publish(envelope)
```

~20 lines. Bridges Fabric agent deltas → Bus envelopes.

---

#### 6.12 New Gaps

| ID | Description | Severity |
| -- | ----------- | -------- |
| **SIM-GAP-20** | `ModelHubGatewayAdapter` (IModelGatewayPort → IModelHubPort bridge) does not exist yet. Needed for Fabric's Agent Provider to grant LLM access to spawned agents. | MEDIUM |
| **SIM-GAP-21** | `BusDeltaAdapter` (IDeltaBusPort → Bus bridge) does not exist yet. Needed for Fabric agents to emit deltas via per-session Bus. | MEDIUM |
| **SIM-GAP-22** | `IPromptSystemPort` has no production adapter. `TestPromptSystemAdapter` returns empty templates. Capability context building will be degraded until prompt system built. | LOW |
| **SIM-GAP-23** | Bootstrap uses `_FabricGatewayAdapter` (inner class) to translate POC orchestrator types ↔ K1 Fabric types. This adapter must be extracted to `adapters.py` (SIM-D-12) and maintained until POC types are retired. | LOW |

#### 6.13 New Flags

| ID | Step | File | Problem | Impact |
| -- | ---- | ---- | ------- | ------ |
| **SIM-FLAG-11** | 6 | `k1/concierge/kernel/bootstrap.py` L647-665 | `_create_model()` bypasses `ModelHubFactory` entirely — creates `ModelHubPOCBridge(GeminiConciergeAdapter)` directly | Must switch to `ModelHubFactory.create_standalone()` with plugin registration |
| **SIM-FLAG-12** | 6 | `k1/concierge/kernel/bootstrap.py` L687-726 | `_create_fabric()` passes 5 test adapters to `create_with_ports()` — only bridge is real (`POCMockBridgeAdapter`) | Must replace `TestSessionStateReaderAdapter` with `SessionStateReaderAdapter(ssm)` and inject production ModelGateway/DeltaBus adapters |
| **SIM-FLAG-13** | 6 | `k1/concierge/kernel/bootstrap.py` L897-939 | `_FabricGatewayAdapter` defined as private inner class — cannot be imported by factory | Extract to `k1/concierge/kernel/adapters.py` per SIM-D-12 |

#### 6.14 New Decisions

| ID | Step | Question | Decision | Rationale |
| -- | ---- | -------- | -------- | --------- |
| **SIM-D-20** | 6 | Is IFabricPort a wrapper around Fabric? | **NO — Fabric container IS the IFabricPort. Pass directly.** | Fabric.execute() / discover_capabilities() match IFabricPort Protocol exactly. Same pattern as SIM-D-17 (SSM). |
| **SIM-D-21** | 6 | Use ModelHubFactory or POC bridge? | **ModelHubFactory.create_standalone()** — retire ModelHubPOCBridge | Factory wires 11 internal services (circuit breaker, rate limiter, cost tracker, etc.). POC bridge has none. |
| **SIM-D-22** | 6 | ModelHub shared or per-session? Fabric? | **ModelHub: shared (one per process). Fabric: per-session.** | ModelHub is stateless. Fabric binds to session-specific SSM via ISessionStateReader. |
| **SIM-D-23** | 6 | How to handle POC orchestrator types vs K1 Fabric types? | **Keep `_FabricGatewayAdapter` as type translator. Extract to adapters.py.** | Two type systems coexist until POC types retired. Adapter is 40 lines, clean boundary. |

---

#### 6.15 Step 6 Verdict

**✅ YES — Fabric and ModelHub integrate cleanly. Two small adapters needed.**

Evidence:

1. **Fabric IS IFabricPort** — container delegates match Protocol exactly (SIM-D-20). Same pattern as SSM (SIM-D-17).
2. **ModelHub is self-contained** — `create_standalone()` needs ZERO external ports. Returns `IModelHubPort` ready to use.
3. **SessionStateReaderAdapter already exists** — production adapter wrapping SSM → Fabric read-only view. Zero new code.
4. **Two new adapters needed** (SIM-GAP-20, SIM-GAP-21) — `ModelHubGatewayAdapter` (~30 lines) and `BusDeltaAdapter` (~20 lines). Both are trivial bridges.
5. **Type translation contained** — `_FabricGatewayAdapter` handles POC ↔ K1 types. Stays until POC types retired.
6. **Fabric per-session, ModelHub shared** (SIM-D-22) — clean ownership model matching SIM-D-04.
7. **40 capability registrations** — post-factory step. Will disappear when ModuleLoader reads real contract files from disk.

**Resolved from prior steps:**

- **SIM-GAP-06** (CapabilityRequest/Result type collision) — CONFIRMED. Two type systems coexist. `_FabricGatewayAdapter` translates at boundary (SIM-D-23). Not a blocker.
- **SIM-FLAG-04** (Concierge orchestrator types shadow Fabric types) — CONFIRMED. Handled by adapter extraction (SIM-D-12, SIM-D-23).

**Blockers:** None. The 2 missing adapters are trivial (<50 lines total).

**Next: Step 7 — Orchestrator + Planner Integration**

---

### STEP 7 — Integrate Orchestrator + Planner

**Question:** Wire `OrchestratorFactory.create_production()` and `PlannerFactory.create_production()` into kernel. The Concierge currently uses `OrchestratorStub` — what breaks when we swap to real?

**Assumption:** Steps 1–6 are corrected and running. Per-session Bus (SIM-D-01), KernelService (SIM-D-02), SSM IS IStatePort (SIM-D-17), Fabric IS IFabricPort (SIM-D-20), ModelHub via factory (SIM-D-21), Fabric per-session / ModelHub shared (SIM-D-22).

---

#### 7.1 What We Read

| File / Area | Lines | Key Discovery |
|---|---|---|
| `k1/orchestrator/factory.py` | full | 4 modes. `create_production(config, *, mailbox, fabric, planner, state, delta, bridge, event, storage)` — **8 named ports**. 15-step internal wiring. Returns OrchestratorService. |
| `k1/orchestrator/types.py` | full | **50+ types** across 7 layers. `TaskEnvelope(frozen)`: `intent, trace_id, caller_id, envelope_id, context, tier, capabilities, params, constraints, timeout_ms`. Shared with Planner: `PlanRequest`, `CommittedPlan`, `PlanStep`, `PlanAck`, `MicroReplanRequest`. |
| `k1/orchestrator/orchestration/orchestrator_service.py` | full | 15 keyword-only constructor deps (7 collaborators + 6 ports + config + metrics). Mailbox-based `process()` → `_process_one()` → isinstance dispatch: TaskEnvelope / CommittedPlan / WorkflowRunRequest / InterruptRequest. |
| `k1/orchestrator/ports/` | 9 files | IMailboxPort, IFabricGatewayPort, IPlannerPort, IStateReadPort, IDeltaEmitPort, IBridgeWritePort, IEventSubscriptionPort, IWorkflowStoragePort, IAdminPort |
| `k1/orchestrator/adapters/` | 18 files | 8 production + 8 test/mock + 2 misc. ALL production adapters already exist. |
| `k1/planner/factory.py` | full | 4 modes. `create_production(*, llm_port, fabric_port, state_port, bridge_port, delta_port, event_port, mailbox_port, config?)` — **7 named ports**. 10-step wiring. Returns PlannerAgent. |
| `k1/planner/types.py` | full | Internal: `RoughStep`, `SketchResult`, `ExpandedPlan`, `ValidationVerdict`, `ValidationFailure`. Shared with Orchestrator: re-exports from `k1.orchestrator.types`. |
| `k1/planner/stages/` | 4 files | SketchService (agentic LLM, 4 tools, max 6 rounds, 2K tokens), ExpandService (agentic LLM, 4 tools, 1K tokens), ValidateService (deterministic + LLM arbiter, 512 tokens), CommitService (deterministic, zero LLM). |
| `k1/planner/pipeline_controller.py` | full | FSM: 11 states, 23 edges. IDLE → SKETCHING → EXPANDING → VALIDATING → COMMITTING → COMPLETED. Micro-replan: abbreviated MICRO_SKETCH → MICRO_EXPAND → MICRO_VALIDATE → COMMIT (10s timeout). |
| `k1/planner/planner_agent.py` | full | PlannerAgent: `start()` blocks (dequeue loop), `stop()` drains mailbox, `get_mailbox()` returns IMailboxPort for Orchestrator adapter wiring. 4 event subscriptions. |
| `k1/concierge/orchestrator/stub.py` | full | OrchestratorStub: 3 ports (fabric_gateway, state_read, delta_emit). `handle_task(envelope)→AggregatedResult`, `handle_multi_step(envelope)→AggregatedResult`. MEDIUM tier only, max 2 Fabric calls. |
| `k1/concierge/orchestrator/types.py` | full | POC TaskEnvelope: `intent, task_id, context, tier(ComplexityTier enum), budget(Budget), session_id, trace_id`. Budget: `max_fabric_calls, max_planner_tokens, timeout_ms`. POC-local — does NOT import from `k1.orchestrator`. |
| `k1/concierge/orchestrator/routing.py` | full | `route_task_sync()`: LOW→Back directly, MEDIUM→OrchestratorStub.handle_task(), HIGH→downgraded to MEDIUM (PassthroughPlannerStub). |
| `k1/concierge/fsm/controller.py` | `_on_task_dispatch`, `_route_via_orchestrator`, `_run_medium_orchestration` | FSM calls `orchestrator.handle_task(envelope)` directly. Synchronous call, blocks until result. |
| `k1/concierge/kernel/bootstrap.py` | L327-337, L897-939 | 3 private adapter classes: `_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`. |
| `k1/kernel/kernel.md` | Phase 4 (L431+), Phase 5, Phase 5b | Phase 4: Orchestrator with MockPlannerAdapter. Phase 5: PlannerFactory.create_production(). Phase 5b: hot-swap `orchestrator._planner_port = PlannerAdapter(planner_mailbox, cb_planner)`. |
| `k1/concierge/concierge.md` | §4.2, §15.2.6, §88.2 | IDispatchPort Protocol: `dispatch_direct()`, `dispatch_envelope()`, `cancel_dispatch()`. FabricOrchestratorAdapter: takes `(fabric, orchestrator_mailbox, cb_orch, cb_fabric, cb_mcp)`. Tier routing via 3 circuit breakers. |

---

#### 7.2 Architecture Discovery: Two Orchestrator Interfaces

The Concierge orchestrator integration has a **three-layer architecture** that changes across POC → Production:

```
POC (current):
  Concierge FSM → route_task_sync() → OrchestratorStub.handle_task(envelope) → AggregatedResult
  - Synchronous call. Blocks FSM until done.
  - MEDIUM only. HIGH downgraded via PassthroughPlannerStub.
  - POC TaskEnvelope (Budget dataclass, ComplexityTier enum, task_id field)
  - 3 ports total.

Production (target per concierge.md §15.2.6):
  Concierge FSM → IDispatchPort.dispatch_envelope(envelope) → DispatchReceipt
  - Async fire-and-forget. Orchestrator mailbox processes independently.
  - Result arrives via Bus event subscription (k1.orchestration.task.complete.v1)
  - Production TaskEnvelope (capabilities list, str tier, trace_id/caller_id fields)
  - FabricOrchestratorAdapter wraps: fabric + orchestrator_mailbox + 3 circuit breakers

Production (target per kernel.md §6):
  Concierge → FabricOrchestratorAdapter(fabric, orchestrator) → dispatch_port
  - FabricOrchestratorAdapter.dispatch_envelope() → enqueues to Orchestrator mailbox
  - Orchestrator dequeues → routes MEDIUM/HIGH → emits results via Bus
  - Concierge receives results via IDeltaPort event subscription
```

**Key interface mismatch #1: Entry point**

| | OrchestratorStub (POC) | OrchestratorService (Production) |
|---|---|---|
| Entry | `handle_task(envelope) → AggregatedResult` | `process(MailboxMessage) → ProcessResult` (via mailbox dequeue loop) |
| Call pattern | Synchronous, blocking, direct return | Async mailbox enqueue, result via event bus |
| Caller | FSM directly | FabricOrchestratorAdapter wraps as IDispatchPort |
| Result delivery | Direct return value | Bus event: `k1.orchestration.task.complete.v1` |

**Verdict**: The OrchestratorStub interface is **NOT compatible** with OrchestratorService. They have fundamentally different interaction patterns (sync request-response vs async mailbox-event). However, the Concierge production spec (concierge.md §4.2) already defines `IDispatchPort` as the abstraction layer. The `FabricOrchestratorAdapter` wraps the production Orchestrator's mailbox interface behind IDispatchPort. **The swap happens at the adapter level, not the Orchestrator level.**

**Key interface mismatch #2: TaskEnvelope types**

| Field | POC `concierge.orchestrator.types.TaskEnvelope` | Production `orchestrator.types.TaskEnvelope` |
|---|---|---|
| `intent` | ✅ str (required) | ✅ str (required) |
| `tier` | `ComplexityTier` enum (MEDIUM/HIGH) | `str` ("MEDIUM"/"HIGH") |
| `context` | `dict` | `Dict[str, Any]` |
| `timeout_ms` | Via `Budget.timeout_ms` | Direct field: `timeout_ms: int = 30_000` |
| `budget` | `Budget(max_fabric_calls, max_planner_tokens, timeout_ms)` | ❌ No Budget. Uses `constraints: Dict` + `timeout_ms` |
| `capabilities` | ❌ None | `List[str]` (required for MEDIUM) |
| `params` | ❌ None | `Dict[str, Dict[str, Any]]` keyed by capability_name |
| `constraints` | ❌ None | `Dict[str, Any]` |
| `task_id` | `str` (auto-generated "task-xxxx") | ❌ Uses `envelope_id` (UUID) |
| `trace_id` | `str` (auto-generated "trace-xxxx") | Uses `trace_id` (required, non-empty) |
| `session_id` | `str` (optional) | ❌ None (context carries session info) |
| `caller_id` | ❌ None | `str = "concierge"` |
| `cognitive_trace_id` | ❌ None | ❌ None (concierge.md spec uses it, but production type uses `trace_id`) |

**Verdict**: The two TaskEnvelope types are **structurally incompatible**. Production has `capabilities` + `params` (required for MEDIUM), POC has `Budget`. The Concierge production spec (concierge.md §4.3) defines the **canonical** TaskEnvelope matching the production `k1/orchestrator/types.py` structure — with `capabilities`, `params`, `constraints`, `caller_id`. The POC version must be retired.

---

#### 7.3 Orchestrator Factory Wiring (15 Steps)

```
OrchestratorFactory.create_production(config, *, mailbox, fabric, planner, state, delta, bridge, event, storage):

  Step 1:  Validate config (OrchestratorConfig)
  Step 2:  ErrorRouter (classify errors → RETRY/DEGRADE/ABORT)
  Step 3:  ConcurrencyGuard (max 5 parallel steps, backpressure)
  Step 4:  StepRunner (single step executor with retry/timeout)
  Step 5:  Schema guard (validate CapabilityRequest schemas)
  Step 6:  Quality guard (validate CapabilityResult quality scores)
  Step 7:  DAGExecutor (topological sort + parallel execution + cycle detection)
  Step 8:  ConstraintResolver (budget, permissions, temporal constraints)
  Step 9:  WorkflowStateMachine (INIT→RUNNING→PAUSED→COMPLETED/FAILED)
  Step 10: TriggerService (scheduled/event/conditional triggers)
  Step 11: WorkflowScheduler (cron-like scheduling, SQLite persistence)
  Step 12: WorkflowSubsystem (facade: StateMachine + Trigger + Scheduler)
  Step 13: ConnectorSubsystem (MCP connector discovery + registration)
  Step 14: OrchestratorService (14 kwargs constructor) + lazy init
  Step 15: AdminHTTP server (optional, health/metrics/debug)
```

**Port mapping (what kernel provides → what factory needs):**

| Factory Port | Production Adapter | Constructor Args | Source (from kernel) |
|---|---|---|---|
| `mailbox` | `MailboxAdapter` | `(max_depth=100)` | New instance (per-Orchestrator) |
| `fabric` | `FabricGatewayAdapter` | `(fabric)` | Fabric facade from Step 6 (SIM-D-20) |
| `planner` | `MockPlannerAdapter` → `PlannerAdapter` | `(planner_mailbox, circuit_breaker)` | Phase 5b hot-swap after Planner created |
| `state` | `StateReadAdapter` | `(state_reader)` | SessionStateReaderAdapter from Step 5 |
| `delta` | `DeltaEmitAdapter` | `(fabric_bus, fabric_bus)` | FabricBusAdapter from Step 4 (dual-path) |
| `bridge` | `MockBridgeAdapter` → `BridgeWriteAdapter` | `(bridge_client)` | Bridge from Step 8 (future) |
| `event` | `EventSubscriptionAdapter` | `(fabric_bus)` | FabricBusAdapter from Step 4 |
| `storage` | `WorkflowStorageAdapter(SQLiteWorkflowAdapter)` | `(db_path)` | Config-provided path |

---

#### 7.4 Planner Factory Wiring (10 Steps)

```
PlannerFactory.create_production(*, llm_port, fabric_port, state_port, bridge_port, delta_port, event_port, mailbox_port, config?):

  Step 1:  Validate config (PlannerConfig — defaults: 45s timeout, 3.5K tokens, 6 max tool calls)
  Step 2:  ToolCallRouter (routes LLM tool_use → registered tool handlers)
  Step 3:  HILCoordinator (human-in-the-loop: clarification, approval, selection)
  Step 4:  SketchService (agentic LLM, 4 tools, max 6 rounds, 2K token budget)
  Step 5:  ExpandService (agentic LLM, 4 tools, 1K token budget)
  Step 6:  ValidateService (deterministic + LLM arbiter for conflicts, 512 tokens)
  Step 7:  CommitService (deterministic, zero LLM — freeze plan, assign IDs, emit)
  Step 8:  PipelineController (FSM: 11 states, 23 edges, orchestrates 4 stages)
  Step 9:  PlannerAgent (mailbox dequeue loop, start/stop lifecycle)
  Step 10: Wire event subscriptions (plan.request, plan.cancel, hil.response, micro.replan)
```

**Port mapping (what kernel provides → what factory needs):**

| Factory Port | Production Adapter | Constructor Args | Source (from kernel) |
|---|---|---|---|
| `llm_port` | `LLMGatewayAdapter` | `(llm_request_bus, consumer_id="planner")` | Model Hub (SIM-D-21) via ILLMRequestBus |
| `fabric_port` | `FabricRetrievalAdapter` | `(fabric_retrieval, timeout_ms=50)` | Fabric retrieval API from Step 6 |
| `state_port` | `SessionStateReadAdapter` | `(reader, session_id)` | SSM from Step 5 — read-only view |
| `bridge_port` | `BridgeAdapter` | `(bridge_port)` | Bridge from Step 8 (or TestBridgeAdapter) |
| `delta_port` | `DeltaBusAdapter` | `(delta_bus, agent_id="planner")` | Bus from Step 4 |
| `event_port` | `EventBusAdapter` | `(event_port)` | Bus from Step 4 |
| `mailbox_port` | `PlannerMailboxAdapter` | `(max_depth=5)` | New instance (Planner-internal) |

---

#### 7.5 Orchestrator ↔ Planner Cross-Wiring (Phase 5b)

The Orchestrator and Planner have an **async 2-phase relationship**:

```
Phase 1: Orchestrator created with MockPlannerAdapter
         └── HIGH tier tasks return "not supported" error

Phase 2: Planner created independently (needs 7 ports)
         └── PlannerAgent returned but NOT started (start() blocks)

Phase 3: Cross-wire via hot-swap
         planner_mailbox = planner.get_mailbox()           # extract IMailboxPort
         cb_planner = CircuitBreaker("CB_PLANNER", ...)    # failure threshold + timeout
         planner_adapter = PlannerAdapter(planner_mailbox, cb_planner)
         orchestrator._planner_port = planner_adapter      # hot-swap Mock → real

Phase 4: Start Planner background task
         planner_task = asyncio.create_task(planner.start())  # enters dequeue loop
```

**Runtime flow for HIGH tier task:**

```
Concierge → IDispatchPort.dispatch_envelope(TaskEnvelope{tier=HIGH})
  → FabricOrchestratorAdapter.dispatch_envelope()
    → Orchestrator mailbox.enqueue(envelope)
      → OrchestratorService._process_one(envelope)
        → _route_task(envelope) → tier=HIGH → _dispatch_high()
          → PlannerAdapter.request_plan(PlanRequest)
            → planner_mailbox.enqueue(PlanRequest)
              → PlannerAgent._dequeue_one()
                → PipelineController.execute(plan_request)
                  → SKETCH → EXPAND → VALIDATE → COMMIT
                    → CommitService: emit CommittedPlan via event_port
                      → Bus → Orchestrator event subscription
                        → OrchestratorService._receive_plan(CommittedPlan)
                          → DAGExecutor.execute(committed_plan)
                            → parallel step execution via Fabric
                              → AggregatedResult → Bus event
                                → Concierge IDeltaPort subscription
```

**Critical observation**: The Orchestrator→Planner interaction is **fully async via mailbox + event bus**. No direct method calls. The PlannerAdapter wraps this: `request_plan()` enqueues to Planner mailbox, `CommittedPlan` arrives via event subscription. This means the cross-wiring is a **data flow** wiring, not a call-stack wiring.

---

#### 7.6 Concierge Integration: POC → Production Migration

**Current POC path (what must change):**

```
k1/concierge/fsm/controller.py:
  _on_task_dispatch()
    → _route_via_orchestrator()
      → routing.route_task_sync(orchestrator, envelope)
        → orchestrator.handle_task(poc_envelope) → AggregatedResult
        → synchronous, blocking, POC types

Must become:
  _on_task_dispatch()
    → IDispatchPort.dispatch_envelope(production_envelope) → DispatchReceipt
    → async, non-blocking, result arrives via IDeltaPort subscription
```

**What breaks when swapping OrchestratorStub → OrchestratorService:**

1. **Interface incompatibility (SIM-GAP-24)**: OrchestratorStub exposes `handle_task(envelope) → AggregatedResult`. OrchestratorService has no such method — it uses mailbox-based `process()`. The FSM code that calls `orchestrator.handle_task()` directly cannot call OrchestratorService.

2. **TaskEnvelope type mismatch (SIM-GAP-25)**: POC `TaskEnvelope` has `Budget` dataclass + `ComplexityTier` enum + `task_id`. Production `TaskEnvelope` has `capabilities` list + `params` dict + `constraints` dict + `caller_id`. Fields are structurally incompatible.

3. **Sync → Async execution model (SIM-GAP-26)**: POC blocks FSM until `AggregatedResult` returned. Production enqueues and returns `DispatchReceipt` immediately — result comes later via event bus. FSM state machine must support the DISPATCHING → WAITING_RESULT → RESULT_RECEIVED flow.

4. **HIGH tier routing (SIM-GAP-27)**: POC downgrades HIGH → MEDIUM via `PassthroughPlannerStub`. Production routes HIGH to real Planner via 2-phase async (PlanRequest → CommittedPlan → DAGExecutor). The Concierge FSM must not downgrade HIGH when production Orchestrator is present.

5. **Result delivery path (SIM-GAP-28)**: POC gets result as direct return value. Production result arrives via Bus event `k1.orchestration.task.complete.v1` → Concierge IDeltaPort subscription → FSM event handler. The IDeltaPort subscription + FSM handler must be wired.

**What does NOT break:**

1. **LOW tier routing** — Unchanged. Goes through Fabric directly via `dispatch_direct()`.
2. **FSM states** — `DISPATCHING` state already exists. Just needs async result handling.
3. **Concierge ports 1-5, 7-8** — Unaffected. Only port 6 (IDispatchPort) changes.
4. **Internal Orchestrator wiring** — All 15 internal steps are self-contained in factory.
5. **Internal Planner wiring** — All 10 internal steps are self-contained in factory.

---

#### 7.7 FabricOrchestratorAdapter: The Bridge

The production Concierge spec (concierge.md §15.2.6) already defines the adapter that bridges the gap:

```python
class FabricOrchestratorAdapter:  # implements IDispatchPort
    __slots__ = ("_fabric", "_mailbox", "_cb_orch", "_cb_fabric", "_cb_mcp", "_inflight")

    def __init__(self, fabric, orchestrator_mailbox, cb_orchestrator, cb_fabric, cb_mcp):
        ...

    async def dispatch_direct(self, capability_id, params) -> ExecutionResult:
        # LOW tier: Fabric.execute() directly, guarded by CB_FABRIC
        ...

    async def dispatch_envelope(self, envelope: TaskEnvelope) -> DispatchReceipt:
        # MEDIUM/HIGH: mailbox.enqueue(envelope), guarded by CB_ORCHESTRATOR
        # CB_PLANNER OPEN → degrade HIGH to MEDIUM
        # MailboxFull → retry 100ms, then degrade to LOW
        ...

    async def cancel_dispatch(self, envelope_id) -> CancelResult:
        # Cancel in-flight dispatch (idempotent)
        ...
```

**Constructor needs**: `fabric` (Fabric facade from Step 6), `orchestrator_mailbox` (from `OrchestratorService.get_mailbox()` or the `MailboxAdapter` injected into factory), `cb_orchestrator`, `cb_fabric`, `cb_mcp` (3 CircuitBreaker instances).

**Decision (SIM-D-24): FabricOrchestratorAdapter replaces the entire POC routing stack.** The current `routing.py` → `route_task_sync()` → `OrchestratorStub.handle_task()` chain is retired. FabricOrchestratorAdapter implements IDispatchPort, which the Concierge FSM already uses in production spec. The 3 private bootstrap adapter classes (`_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`) are also retired — they were POC plumbing for OrchestratorStub.

---

#### 7.8 Shared vs Per-Session Analysis

**Decision (SIM-D-25): Orchestrator and Planner are SHARED across sessions.**

| Component | Shared? | Rationale |
|---|---|---|
| OrchestratorService | **Shared** | Stateless task processor. TaskEnvelope carries session context. Mailbox handles concurrent envelopes from multiple sessions. WAL + workflows are cross-session (household-level). |
| PlannerAgent | **Shared** | Stateless plan generator. PlanRequest carries session context + beliefs snapshot. Single `_plan_lock` means V1 serializes plans (one at a time across sessions). |
| FabricOrchestratorAdapter | **Per-session** (in Concierge) | Concierge is per-session. Each ConciergeSession gets its own FabricOrchestratorAdapter with its own `_inflight` tracking map. But the underlying Orchestrator mailbox is shared. |

**Consequence**: KernelService creates Orchestrator + Planner ONCE at startup (not per-session). ConciergeFactory receives the Orchestrator's mailbox reference to wire into FabricOrchestratorAdapter.

This is consistent with SIM-D-04 update: `Orchestrator/Planner/ModelHub/Bridge = shared. Bus/SS/Fabric/Concierge = per-session.`

---

#### 7.9 Dependency Graph (Phase 4 + 5 + 5b)

```
Phase 4 inputs:                          Phase 5 inputs:
  Bus (Step 4) ─────┐                     ModelHub (Step 6) ─────┐
  Fabric (Step 6) ──┤                     Fabric (Step 6) ──────┤
  SSM (Step 5) ─────┤                     SSM (Step 5) ─────────┤
  Config ───────────┤                     Bus (Step 4) ─────────┤
                    ▼                     Config ───────────────┤
          ┌─────────────────┐                                   ▼
          │  OrchestratorFactory  │           ┌─────────────────────┐
          │  .create_production() │           │  PlannerFactory     │
          │  8 ports → 15 steps   │           │  .create_production()│
          └────────┬────────┘           │  7 ports → 10 steps  │
                   │                          └────────┬────────┘
                   │                                   │
                   │  Phase 5b:                        │
                   │  planner.get_mailbox() ───────────┘
                   │  PlannerAdapter(mailbox, CB) ──→ orchestrator._planner_port
                   │
                   ▼
          Orchestrator ready (MEDIUM + HIGH)
```

**Ordering constraint**: Orchestrator MUST be created before Planner (needs MockPlannerAdapter placeholder). Planner MUST be created before cross-wiring. Cross-wiring MUST happen before Orchestrator processes any HIGH tier tasks. Planner `start()` MUST be after cross-wiring.

---

#### 7.10 kernel.md Alignment Check

| kernel.md Spec | Code Reality | Status |
|---|---|---|
| Phase 4: `OrchestratorFactory.create_production()` with 8 ports | Factory signature matches exactly. All 8 adapter imports exist. | ✅ ALIGNED |
| Phase 4: `MockPlannerAdapter()` as initial planner | `k1/orchestrator/adapters/mock_planner_adapter.py` exists | ✅ ALIGNED |
| Phase 5: `PlannerFactory.create_production()` with 7 ports | Factory signature matches. All 7 adapter imports exist. | ✅ ALIGNED |
| Phase 5: `TestLLMAdapter` as initial LLM port (Phase 1) | Test adapter exists. Phase 2: `LLMGatewayAdapter(model_hub)` | ✅ ALIGNED |
| Phase 5b: `planner.get_mailbox()` → `PlannerAdapter` → hot-swap | PlannerAgent has `get_mailbox()`. PlannerAdapter constructor takes `(mailbox, cb)`. | ✅ ALIGNED |
| Phase 5b: `orchestrator._planner_port = planner_adapter` | Direct attribute assignment. OrchestratorService stores planner as `_planner_port`. | ⚠️ FRAGILE — private attr assignment. No setter API. |
| Phase 6: `FabricOrchestratorAdapter(fabric, orchestrator)` | concierge.md spec: `FabricOrchestratorAdapter(fabric, orch_mailbox, cb_orch, cb_fabric, cb_mcp)`. kernel.md simplified. | ⚠️ MISMATCH — kernel.md omits 3 circuit breaker args |
| W-29: hot-swap verification | Test exists in kernel.md wiring table | ✅ TESTABLE |
| W-37: IDispatchPort MED routes to Orchestrator | Test exists in kernel.md wiring table | ✅ TESTABLE |
| MH-G01: Model Hub created BEFORE Planner | kernel.md Phase 3 (ModelHub) before Phase 5 (Planner) | ✅ ALIGNED |

---

#### 7.11 Gaps Found

| ID | Description | Severity |
|---|---|---|
| **SIM-GAP-24** | OrchestratorStub `handle_task()` interface incompatible with OrchestratorService mailbox-based `process()`. Concierge FSM calls `orchestrator.handle_task()` directly — this method doesn't exist on production Orchestrator. | **HIGH** |
| **SIM-GAP-25** | POC `TaskEnvelope` (Budget, ComplexityTier enum, task_id) vs Production `TaskEnvelope` (capabilities, params, constraints, caller_id). Structurally incompatible. POC code constructs POC envelopes. | **HIGH** |
| **SIM-GAP-26** | POC orchestrator call is synchronous (blocks FSM). Production is async (enqueue + event bus result). FSM must support DISPATCHING → async wait → RESULT_RECEIVED pattern. | **HIGH** |
| **SIM-GAP-27** | HIGH tier downgraded to MEDIUM in POC via PassthroughPlannerStub. Must be removed when real Planner is available. | **MEDIUM** |
| **SIM-GAP-28** | Result delivery changes from direct return value to Bus event `k1.orchestration.task.complete.v1`. Concierge IDeltaPort must subscribe + FSM must handle result event. | **MEDIUM** |
| **SIM-GAP-29** | `orchestrator._planner_port = planner_adapter` — hot-swap via private attribute. No public `set_planner_port()` API. Fragile across refactors. | **LOW** |
| **SIM-GAP-30** | kernel.md Phase 6 shows `FabricOrchestratorAdapter(fabric, orchestrator)` but concierge.md spec requires `(fabric, orch_mailbox, cb_orch, cb_fabric, cb_mcp)`. 3 circuit breaker args missing from kernel.md. | **LOW** |
| **SIM-GAP-31** | Planner V1 has `_plan_lock` (asyncio.Lock) — serializes ALL plans across ALL sessions. Under multi-session load, HIGH tier tasks queue behind each other. | **MEDIUM** |
| **SIM-GAP-32** | `LLMGatewayAdapter` needs `ILLMRequestBus` — not a direct ModelHub reference. An intermediary bus/adapter between ModelHub and Planner LLM port must exist or be created. | **MEDIUM** |

---

#### 7.12 Flags Found

| ID | File | Problem | Impact |
|---|---|---|---|
| **SIM-FLAG-14** | `k1/concierge/orchestrator/routing.py` | `route_task_sync()` is synchronous. Production needs async `dispatch_envelope()`. Entire routing module becomes dead code. | Must retire routing.py + OrchestratorStub when FabricOrchestratorAdapter is wired |
| **SIM-FLAG-15** | `k1/concierge/orchestrator/types.py` | POC TaskEnvelope, Budget, CapabilityRequest, CapabilityResult all become dead code. Production types come from `k1.orchestrator.types`. | Must retire concierge.orchestrator.types module |
| **SIM-FLAG-16** | `k1/concierge/fsm/controller.py` | FSM calls `orchestrator.handle_task()` — direct coupling to OrchestratorStub interface. Must be changed to call `dispatch_port.dispatch_envelope()`. | FSM dispatch path must be rewritten for production |
| **SIM-FLAG-17** | `k1/planner/planner_agent.py` | `_plan_lock` is a process-wide asyncio.Lock. V1 serializes plans across sessions. Performance bottleneck for multi-session. | Accept for V1 — documented limitation. V2: per-session plan isolation. |

---

#### 7.13 Decisions

| ID | Question | Decision | Rationale |
|---|---|---|---|
| **SIM-D-24** | How does Concierge talk to production Orchestrator? | **FabricOrchestratorAdapter replaces entire POC routing stack.** Implements IDispatchPort. Takes orchestrator_mailbox + 3 CBs. Retires OrchestratorStub, route_task_sync(), 3 private bootstrap adapters. | concierge.md §15.2.6 already specifies this adapter. Clean port-based boundary. |
| **SIM-D-25** | Orchestrator and Planner shared or per-session? | **Shared (one per process).** Created at KernelService startup, not per ConciergeFactory call. | Stateless task/plan processors. TaskEnvelope/PlanRequest carry session context. Expensive to duplicate (WAL, MCP connectors, workflow scheduler, LLM pipelines). |
| **SIM-D-26** | How to handle the Orchestrator→Planner bootstrap ordering? | **Phased approach per kernel.md: Phase 4 (Orch + MockPlanner) → Phase 5 (Planner) → Phase 5b (hot-swap).** | Avoids circular dependency. Orchestrator functional for MEDIUM immediately. HIGH available after hot-swap. |
| **SIM-D-27** | What happens to POC orchestrator code after production wiring? | **Dead code. Mark for removal.** `routing.py`, `stub.py`, `concierge/orchestrator/types.py`, 3 private bootstrap adapters — all retired when FabricOrchestratorAdapter wired. | Clean separation. POC served its purpose. Production has its own adapter stack. |
| **SIM-D-28** | How does Planner get LLM access? | **`LLMGatewayAdapter(llm_request_bus)` where `llm_request_bus` wraps ModelHub.** If `ILLMRequestBus` doesn't exist yet, create thin adapter (~20 lines) that maps `ILLMPort.execute()` → `ModelHub.execute()`. | kernel.md shows `TestLLMAdapter` for Phase 1, `LLMGatewayAdapter(model_hub)` for Phase 2. The bus intermediary may be optional if adapter can take ModelHub directly. |

---

#### 7.14 Step 7 Verdict

**Wiring: ACHIEVABLE but with significant POC→Production migration work.**

Both `OrchestratorFactory.create_production()` and `PlannerFactory.create_production()` are well-specified with all production adapters already written. The factories are self-contained (15 steps / 10 steps internally). kernel.md Phase 4/5/5b wiring is **fully aligned** with factory signatures.

**The hard part is NOT wiring Orchestrator + Planner — it's retiring the POC orchestrator integration in Concierge.** Five gaps (SIM-GAP-24 through SIM-GAP-28) are all consequences of the POC using a synchronous stub with incompatible types. The production path is already specified (concierge.md §4.2, §15.2.6) — it uses IDispatchPort + FabricOrchestratorAdapter + async event bus results.

**Summary of work required:**

1. **Zero new code for Orchestrator internals** — factory + 8 adapters exist
2. **Zero new code for Planner internals** — factory + 7 adapters exist
3. **~30 lines: LLMRequestBus adapter** (SIM-GAP-32) — bridge ModelHub → ILLMPort if intermediary bus needed
4. **~80 lines: FabricOrchestratorAdapter** (SIM-D-24) — already spec'd in concierge.md, implements IDispatchPort
5. **~50 lines: FSM dispatch path rewrite** (SIM-FLAG-16) — change from `orchestrator.handle_task()` to `dispatch_port.dispatch_envelope()` + async result handler
6. **~20 lines: Result event subscription** (SIM-GAP-28) — wire IDeltaPort to receive `task.complete` events
7. **Delete ~300 lines: POC dead code** (SIM-D-27) — routing.py, stub.py, POC types, private adapters

**Blockers:** None. All production adapters exist. All factory signatures verified. kernel.md and concierge.md specs are consistent (minor kernel.md simplification in Phase 6 CB args — SIM-GAP-30). The phased bootstrap (Phase 4 → 5 → 5b) avoids circular deps.

**Resolved from prior steps:**

- **SIM-GAP-06** (type collision) — CONFIRMED still applies. POC types (SIM-FLAG-15) must be retired. Production types from `k1.orchestrator.types` are canonical.
- **SIM-FLAG-07** (3 private bootstrap adapters) — CONFIRMED dead code. Replaced by FabricOrchestratorAdapter (SIM-D-24).
- **SIM-D-04** (shared vs per-session) — CONFIRMED: Orchestrator + Planner are shared (SIM-D-25).

**Next: Step 8 — Bridge Client + HouseholdProjection**

---

### STEP 8 — Integrate Bridge Client + HouseholdProjection

**Question:** Wire `BridgeClient` for K0 connectivity. Nothing exists here — this is net-new. How does it fit into the kernel lifecycle?

**Assumption:** Steps 1–7 are corrected and running. Per-session Bus (SIM-D-01), KernelService (SIM-D-02), SSM IS IStatePort (SIM-D-17), Fabric IS IFabricPort (SIM-D-20), ModelHub shared (SIM-D-21/22), Orchestrator+Planner shared (SIM-D-25), phased Orch→Planner cross-wire (SIM-D-26).

---

#### 8.1 What We Read

| File / Area | Scope | Key Discovery |
|---|---|---|
| `bridge/` root directory | Full recursive listing | **5 responsibilities**: Kernel Transport, Connector Security, Device Sync, IFL, Offline Awareness. Lives at root level (NOT inside K0 or K1). |
| `bridge/core/envelope_builder.py` | Full | `BridgeConfig(frozen)`: tenant_id, space_id, device_id, actor, policy_version, default_band. `CommandEnvelope`: topic, body, schema_uri, band, trace_id. `EnvelopeBuilder(config, signer)`: builds 18-field K0 envelopes with BLAKE3 idem_key, SHA-256 integrity, crypto signature. |
| `bridge/core/signing.py` | Full | `SigningBackend(Protocol)`: algorithm, key_id, sign(). Two implementations: `HmacSigning` (min 16-byte secret), `Ed25519Signing` (PyNaCl). Both produce base64url signatures. |
| `bridge/core/transport.py` | Full | `HttpTransport`: async httpx client. `post_command(envelope_json) → HttpResult`. `check_health() → bool`. `TransportConfig`: base_url, timeouts, TLS, connection pool. Paths: `/k0/command.submit`, `/k0/health`. |
| `bridge/kernel/command_port.py` | Full | `KernelCommandPort(transport, builder, outbox?)`: `submit(topic, body, *, schema_uri?, band?, trace_id?) → None` (fire-and-forget). `submit_batch(envelopes, max=50, concurrency=3)`. Error handling: 200=OK, 409=idempotent-OK, 400=ContractViolationError, 403=PolicyDeniedError, 429/5xx=enqueue to LocalOutbox. |
| `bridge/sync/local_outbox.py` | Full | `LocalOutbox(db_path)`: SQLite-backed offline queue. `enqueue()`, `drain(transport)`, `mark_failed()`. MAX_QUEUE=10K, MAX_ATTEMPTS=10, WAL mode, priority ordering. |
| `bridge/contracts/` | Full | `command_port.protocol.yaml`: formal IKernelCommandPort contract. `command_envelope.json`: JSON Schema (draft 2020-12), 18 required fields, topic pattern regex, band enum. |
| `bridge/connector/` | Stub | Empty `__init__.py` — IConnectorGatewayPort NOT implemented. |
| `bridge/adapters/` | Stub | Empty `__init__.py` — HTTP/gRPC/TCP adapters NOT implemented. |
| `bridge/codecs/` | Stub | Empty `__init__.py` — JSON/FlatBuffer codecs NOT implemented. |
| `bridge/sync/` | Partial | Only `LocalOutbox`. ISyncPort, CRDTMerge, DeviceDiscovery, E2EEncryption, CertificateManager — all `None` at runtime. |
| `architecture_diagrams/bridge/bridge_architecture.mmd` | Full (~600 nodes) | 5 responsibilities. 4 K0 ports (CMD, QRY, SSE, OBS). Edge-first design. Command topics (7). Query selectors (6). SSE events (7). Offline modes (ONLINE/OFFLINE/DEGRADED). IFL architecture (manifests, adapters, WASM sandbox). |
| `architecture_diagrams/bridge/interkernel_fabric_layer.mmd` | Full (~400 nodes) | IFL 5-layer architecture. ManifestTranslator auto-registers IFL capabilities as Fabric tools. Company-hosted (HTTPS/2) and WASM-sandboxed adapters. OAuth connection flow (6 steps). Event taxonomy: `ifl.{category}.{adapter}.{event}`. |
| `bridge/README.md` | Full (~750 lines) | Source-of-truth design doc. 3 primary responsibilities + IFL + Security Core. All planned port interfaces. No BridgeClient/BridgeFactory class exists. |
| `k1/kernel/kernel.md` Phase 5.5 | L500-520 | `BridgeClient.connect(bridge_config)`: Phase 1 = None/TestBridgeClient. bridge_client implements query(), send_command(), subscribe(), close(). If K0 unreachable: bridge_client = None → adapters fall back to offline stubs. |
| `k1/kernel/kernel.md` Phase 6.5 | L559-575 | `bridge_client.query("household.projection.v1")` → `concierge.hydrate_household()`. `bridge_client.subscribe("household.delta.v1")` → live deltas. Offline: `hydrate_household_from_local_cold()`. |
| `k1/kernel/kernel.md` §126 | L7516-7660 | HouseholdProjection(frozen): members, devices, governance, version, stale. Boot: query→cache+LOCAL COLD. Per-turn: in-memory only (0ms). NOT SessionState — separate frozen projection. |
| `k1/concierge/concierge.md` §14.9 | IMemoryPort spec | `recall(query, selectors) → MemoryResult`, `store(item) → StoreResult`, `prefetch(hints) → None`. **SPEC ONLY** — no Python file. |
| `k1/concierge/concierge.md` §15.2.8 | BridgeRecallAdapter spec | Wraps Bridge query port + LOCAL COLD fallback. **SPEC ONLY** — not implemented. |
| `k1/orchestrator/ports/bridge_write_port.py` | Full | `IBridgeWritePort(Protocol)`: `submit_audit()`, `write_wal()`, `read_wal()`, `list_wal_ids()`, `submit_deferred_result()`. Used by DAGExecutor, crash recovery, WorkflowScheduler. |
| `k1/orchestrator/adapters/bridge_write_adapter.py` | Full | `BridgeWriteAdapter(bridge_client: IBridgeClient)`. Defines `IBridgeClient(Protocol)`: `write(channel, payload, *, trace_id)`, `read(channel, key)`. Fire-and-forget writes, raise on read failures. |
| `k1/planner/ports/bridge_port.py` | Full | `IBridgePort(Protocol)`: `recall(query, selectors, *, trace_id) → RecallResponse`, `persist_plan(plan, *, trace_id) → None`. Used by ToolCallRouter (SKETCH) and CommitService (COMMIT). |
| `k1/planner/adapters/bridge_adapter.py` | Full | `BridgeAdapter(bridge_port)`: wraps Fabric IBridgePort. `recall → bridge.query("memory.recall")`. `persist_plan → bridge.send_command("memory.store")`. Offline: empty recall, drop persist. |
| `k1/memory_writer/ports/bridge_command_port.py` | Full | `IBridgeCommandPort(Protocol)`: `submit(topic, schema_uri, body)`, `submit_batch(envelopes)`. MW-03: ONLY output path to K0. MW-09: MUST queue locally when offline. |
| `k1/sessionstate/ports/k0_sync.py` | Full | `IK0SyncPort(ABC)`: sync_to_k0, restore_from_k0. Currently `NullSyncPort()` — no Bridge sync yet. |
| `k1/concierge/kernel/bootstrap.py` | Bridge refs | `POCMockBridgeAdapter(registry)` as Fabric bridge port. `_build_recall_fn()` = in-memory word-overlap scorer. No real `bridge_client` variable. No offline detection. |
| `k1/concierge/fabric/poc_bridge_adapter.py` | Full | `POCMockBridgeAdapter`: send_command, query, route_ifl, is_available (always True). Routes to CapabilityRegistry handlers. |

---

#### 8.2 Implementation Maturity Assessment

```
Bridge Module Status:
┌─────────────────────────────┬──────────────┬─────────────────────────────────────────┐
│ Module                      │ Status       │ What Exists                             │
├─────────────────────────────┼──────────────┼─────────────────────────────────────────┤
│ bridge/core/                │ ✅ COMPLETE   │ BridgeConfig, EnvelopeBuilder, Signing, │
│                             │              │ HttpTransport (3/3 files)               │
│ bridge/kernel/              │ ⚠️ PARTIAL   │ KernelCommandPort only (1/4 ports)      │
│ bridge/sync/                │ ⚠️ PARTIAL   │ LocalOutbox only (1/7 planned)          │
│ bridge/contracts/           │ ⚠️ PARTIAL   │ command_port contract + JSON schema     │
│ bridge/connector/           │ ❌ STUB      │ Empty __init__.py                       │
│ bridge/adapters/            │ ❌ STUB      │ Empty __init__.py                       │
│ bridge/codecs/              │ ❌ STUB      │ Empty __init__.py                       │
│ BridgeClient facade         │ ❌ MISSING   │ Not built (README describes planned)    │
│ IKernelQueryPort            │ ❌ MISSING   │ Spec only in README                    │
│ IKernelSSEPort              │ ❌ MISSING   │ Spec only in README                    │
│ IKernelObsPort              │ ❌ MISSING   │ Spec only in README                    │
│ IConnectorGatewayPort       │ ❌ MISSING   │ Spec only in README                    │
│ ISyncPort                   │ ❌ MISSING   │ Spec only in README                    │
├─────────────────────────────┼──────────────┼─────────────────────────────────────────┤
│ Tests (bridge/)             │ ✅ SOLID     │ 5 unit + 1 integration. Zero mocks.     │
│                             │              │ Real crypto, real SQLite, httpx mock.    │
└─────────────────────────────┴──────────────┴─────────────────────────────────────────┘
```

---

#### 8.3 Who Needs Bridge — 6 Consumers

The Bridge has **6 distinct consumers** in K1, each needing a different port/facade:

| # | Consumer | Port Needed | K0 Path | Methods Called | Current State |
|---|---|---|---|---|---|
| 1 | **Concierge** (IMemoryPort) | Query + Command | PORT_QRY + PORT_CMD | `recall(query, selectors)`, `store(item)`, `prefetch(hints)` | POC: `recall_fn` closure (word-overlap). BridgeRecallAdapter spec only. |
| 2 | **Orchestrator** (IBridgeWritePort) | Command + Query | PORT_CMD (writes), PORT_QRY (WAL reads) | `submit_audit()`, `write_wal()`, `read_wal()`, `submit_deferred_result()` | `MockBridgeAdapter` (in-memory). `BridgeWriteAdapter` implemented but needs `IBridgeClient`. |
| 3 | **Planner** (IBridgePort) | Query + Command | PORT_QRY (recall), PORT_CMD (persist) | `recall(query, selectors)`, `persist_plan(plan)` | `TestBridgeAdapter`. `BridgeAdapter` implemented, wraps Fabric IBridgePort. |
| 4 | **Fabric** (IBridgePort) | Command + Query + IFL | PORT_CMD + PORT_QRY + IFL Gateway | `send_command()`, `query()`, `route_ifl()` | `POCMockBridgeAdapter` (registry-backed). `TestBridgeAdapter` in tests. |
| 5 | **Memory Writer** (IBridgeCommandPort) | Command only | PORT_CMD | `submit(topic, schema_uri, body)`, `submit_batch(envelopes)` | Not built. MW spec only. |
| 6 | **SessionState** (IK0SyncPort) | Command + Query | PORT_CMD (archive), PORT_QRY (restore) | `sync_to_k0()`, `restore_from_k0()` | `NullSyncPort()` — no-op. |

**Plus HouseholdProjection** (Phase 6.5):

| Consumer | Method | K0 Path | Current State |
|---|---|---|---|
| Concierge (hydration) | `bridge_client.query("household.projection.v1")` | PORT_QRY | Spec only (kernel.md §126) |
| Concierge (live deltas) | `bridge_client.subscribe("household.delta.v1")` | PORT_SSE | Spec only (kernel.md §126) |

---

#### 8.4 What's Wirable Today vs What's Missing

**Wirable TODAY (PORT_CMD path complete):**

```
K1 Component
  → KernelCommandPort.submit(topic, body, trace_id=...)
    → EnvelopeBuilder.build() (18-field envelope with crypto signing)
      → HttpTransport.post_command(envelope_json)
        → POST /k0/command.submit
        → 429/5xx/offline → LocalOutbox.enqueue() (SQLite WAL, 10K max)
```

This covers: `memory.write`, `session.snapshot`, `beliefs.archive`, `history.archive`, `plan.committed`, `ifl.*`, `sync.delta` — ALL fire-and-forget command topics.

**Missing for full kernel wiring:**

| Missing Piece | Needed By | Complexity | Priority |
|---|---|---|---|
| `IKernelQueryPort` (PORT_QRY) | Concierge recall, Orchestrator WAL read, Planner recall, SS restore, Household hydration | **HIGH** (~150 lines: QueryEnvelope, QueryBuilder, response parsing) | P1 — blocks recall |
| `IKernelSSEPort` (PORT_SSE) | Household live deltas, memory.formed events, learning advisories, proactive signals | **MEDIUM** (~100 lines: SSE receiver, cursor management, backpressure) | P2 — blocks live updates |
| `BridgeClient` facade | All consumers (unified API) | **MEDIUM** (~80 lines: wraps CommandPort + QueryPort + SSEPort + health check) | P1 — kernel needs single entry point |
| `IKernelObsPort` (PORT_OBS) | Telemetry, feedback signals | **LOW** (~50 lines: batch emissions, kind routing) | P3 — non-functional requirement |
| `IConnectorGatewayPort` | IFL/external tool execution | **HIGH** (~200 lines: security pipeline, routing) | P2 — blocks real device integration |
| `BridgeRecallAdapter` (Concierge) | IMemoryPort implementation | **LOW** (~40 lines: wraps query + LOCAL COLD fallback) | P1 — blocks Concierge recall |
| `HouseholdProjection` | Family identity, safety | **MEDIUM** (~60 lines: dataclass + hydration + LOCAL COLD) | P2 — blocks family-aware responses |
| `BridgeCommandAdapter` (MW) | Memory Writer → K0 | **LOW** (~30 lines: wraps KernelCommandPort) | P2 — blocks memory persistence |

---

#### 8.5 Bridge Architecture: Edge-First Design

```
                     K1 (Self-Sufficient)              Bridge (Gateway)         K0 (Optional Cloud)
                     ──────────────────────             ────────────────          ──────────────────
Concierge ─────┐                                   ┌── PORT_CMD ──────── /k0/command.submit
Orchestrator ──┤                                   │   (fire-and-forget)
Planner ───────┤── K1-side adapters ──► BridgeClient ─┤── PORT_QRY ──────── /k0/query.recall
Memory Writer ─┤   (per-component)      (shared)    │   (request-response)
SessionState ──┤                                   ├── PORT_SSE ──────── /k0/sse.subscribe
Fabric ────────┘                                   │   (K0→K1 streaming)
                                                   └── PORT_OBS ──────── /k0/obs.emit
                                                       (metrics/feedback)
                                        │
                                   LocalOutbox (SQLite)
                                   K0 offline? Queue commands.
                                   K0 returns? Drain queue.
```

**Key design principle: K1 is self-sufficient.** K0 is the enhancement layer.

- Offline: K1 works with reduced functionality (no recall, no household deltas)
- All adapters have offline fallback behavior (empty recall, drop persist, stale cache)
- `bridge_client = None` is a VALID state — kernel.md Phase 5.5 explicitly handles it

---

#### 8.6 BridgeClient: What Kernel Needs

kernel.md Phase 5.5 describes the interface the kernel expects:

```python
# Per kernel.md:
bridge_client = await BridgeClient.connect(bridge_config)
# bridge_client implements:
#   query(selector, params) → response          # PORT_QRY
#   send_command(topic, body, ...) → None        # PORT_CMD (fire-and-forget)
#   subscribe(topic, handler) → subscription     # PORT_SSE
#   close() → None                               # shutdown
# If K0 unreachable: bridge_client = None
```

**Decision (SIM-D-29): BridgeClient is a thin facade wrapping 3 ports.**

```python
class BridgeClient:
    """Unified Bridge facade for kernel wiring."""

    def __init__(self, command_port, query_port, sse_port, health_checker):
        self._cmd = command_port        # KernelCommandPort (exists)
        self._qry = query_port          # KernelQueryPort (NOT built)
        self._sse = sse_port            # KernelSSEPort (NOT built)
        self._health = health_checker   # HttpTransport.check_health()

    @classmethod
    async def connect(cls, config: BridgeConfig) -> "BridgeClient | None":
        transport = HttpTransport(TransportConfig.from_bridge_config(config))
        await transport.open()
        if not await transport.check_health():
            return None  # K0 unreachable → offline mode
        signer = Ed25519Signing(config.signing_key, config.key_id)
        builder = EnvelopeBuilder(config, signer)
        outbox = LocalOutbox(config.outbox_db_path)
        cmd = KernelCommandPort(transport, builder, outbox)
        qry = KernelQueryPort(transport, builder)        # NEEDS BUILDING
        sse = KernelSSEPort(transport, config.sse_topics) # NEEDS BUILDING
        return cls(cmd, qry, sse, transport)

    async def query(self, selector, params=None) -> dict: ...
    async def send_command(self, topic, body, **kw) -> None: ...
    async def subscribe(self, topic, handler) -> Subscription: ...
    async def close(self) -> None: ...
```

---

#### 8.7 How Each K1 Component Connects to Bridge

**Decision (SIM-D-30): BridgeClient is SHARED (one per process), K1 adapters are per-component.**

Each K1 component has its own adapter that wraps BridgeClient through component-specific port protocols:

```
BridgeClient (shared, created at kernel startup)
  │
  ├── Concierge: BridgeRecallAdapter(bridge_client) → IMemoryPort
  │     recall → bridge_client.query("memory.recall", {query, selectors})
  │     store → bridge_client.send_command("memory.write", item)
  │     Offline: empty recall from LOCAL COLD
  │
  ├── Orchestrator: BridgeWriteAdapter(bridge_client) → IBridgeWritePort
  │     submit_audit → bridge_client.send_command("orchestrator.audit", manifest)
  │     write_wal → bridge_client.send_command("orchestrator.wal", entry)
  │     read_wal → bridge_client.query("orchestrator.wal.read", {dag_id})
  │     Offline: writes queued (LocalOutbox), reads raise DEGRADED
  │
  ├── Planner: BridgeAdapter(fabric_bridge_port) → IBridgePort
  │     recall → fabric.query("memory.recall", {query, selectors})
  │     persist_plan → fabric.send_command("memory.store", plan)
  │     Offline: empty recall, drop persist
  │
  ├── Fabric: BridgeConnectionAdapter(bridge_client) → IBridgePort
  │     send_command → bridge_client.send_command(topic, body)
  │     query → bridge_client.query(selector, params)
  │     route_ifl → bridge_client IFL path (via ConnectorGateway)
  │     Offline: is_available() → False, all calls degraded
  │
  ├── Memory Writer: BridgeCommandAdapter(bridge_client) → IBridgeCommandPort
  │     submit → bridge_client.send_command(topic, body)
  │     submit_batch → bridge_client batched submission
  │     Offline: queued via LocalOutbox (MW-09)
  │
  └── SessionState: BridgeSyncAdapter(bridge_client) → IK0SyncPort
        sync_to_k0 → bridge_client.send_command("session.snapshot", data)
        restore_from_k0 → bridge_client.query("session.restore", {session_id})
        Offline: NullSyncPort behavior (LOCAL COLD only)
```

---

#### 8.8 HouseholdProjection Integration (Phase 6.5)

```
Phase 6.5 (After Concierge created, before lifecycle start):

  if bridge_client is not None:
    ┌─── bridge_client.query("household.projection.v1", {session_id})
    │    Returns: {members[], devices[], governance{}, version}
    │
    ├─── concierge.hydrate_household(snapshot)
    │    Creates HouseholdProjection(frozen) in-memory
    │    Persists to LOCAL COLD (SQLite) for offline use
    │
    └─── bridge_client.subscribe("household.delta.v1", handler=concierge.apply_household_delta)
         Live updates: member added/removed, governance changed, device registered

  else (offline):
    ┌─── concierge.hydrate_household_from_local_cold()
    │    Loads last-known-good from K1 SQLite
    │    projection.stale = True
    └─── Warning on safety-sensitive ops (allergies, permissions)
```

**Decision (SIM-D-31): HouseholdProjection is NOT SessionState.** It's a frozen in-memory projection cached inside Concierge. Per-turn access is 0ms (no K0 round-trip). Members, devices, governance, allergies — all family-level identity data that does NOT change per-conversation.

**Dependency**: HouseholdProjection requires `IKernelQueryPort` (for initial hydration) and `IKernelSSEPort` (for live deltas). Both are NOT built yet (SIM-GAP-34, SIM-GAP-35).

---

#### 8.9 Offline-First Architecture Analysis

Bridge has a clean **3-mode degradation model**:

| Mode | Condition | Behavior |
|---|---|---|
| **ONLINE** | `transport.check_health() == True` | Full K0 access. All ports functional. |
| **OFFLINE** | `bridge_client = None` or health fails | Commands queued to LocalOutbox. Queries return empty/stale. SSE disconnected. HouseholdProjection stale. |
| **DEGRADED** | K0 slow or partially available | Commands succeed but slow. Queries may timeout. SSE lagging (backpressure: throttle/shed). |

**What works offline:**

- LOW tier tasks (Fabric direct, IFL WASM adapters)
- MEDIUM tier tasks (Orchestrator, no WAL persistence)
- SessionState (LOCAL COLD tier fully local SQLite)
- Conversation (Concierge FSM, Front/Back actors, ModelHub)

**What degrades offline:**

- Memory recall (empty results from LOCAL COLD fallback)
- Plan persistence (dropped, fire-and-forget)
- Household data (stale, safety warnings)
- IFL company-hosted adapters (unavailable)
- Cross-device sync (queued)

**What the kernel does**: `bridge_client = None` → all adapters receive None or NullBridge → each adapter has offline fallback behavior built in. This is already the kernel.md Phase 1 approach (all bridge ports start as test stubs).

---

#### 8.10 Bridge ↔ K0 Port Mapping

| Bridge Port | K0 Endpoint | Direction | Protocol | Implemented? |
|---|---|---|---|---|
| `KernelCommandPort` (PORT_CMD) | `/k0/command.submit` | K1 → K0 (fire-and-forget) | POST JSON | ✅ YES — fully working |
| `KernelQueryPort` (PORT_QRY) | `/k0/query.recall` | K1 → K0 → K1 (request-response) | POST JSON → JSON response | ❌ NO — spec only |
| `KernelSSEPort` (PORT_SSE) | `/k0/sse.subscribe` | K0 → K1 (streaming) | GET SSE stream | ❌ NO — spec only |
| `KernelObsPort` (PORT_OBS) | `/k0/obs.emit` | K1 → K0 (fire-and-forget) | POST JSON | ❌ NO — spec only |
| `ConnectorGateway` (IFL) | External adapters | Bidirectional | HTTPS/2 or WASM | ❌ NO — stub only |

---

#### 8.11 Dependency Graph (Bridge in kernel bootstrap)

```
Phase 1: Config → TransportConfig, BridgeConfig
Phase 2: HttpTransport.open() → check_health()
Phase 3: EnvelopeBuilder(config, signer)
Phase 4: LocalOutbox(db_path)
Phase 5: KernelCommandPort(transport, builder, outbox)
Phase 6: KernelQueryPort(transport, builder)             ← NOT BUILT
Phase 7: KernelSSEPort(transport, sse_topics)             ← NOT BUILT
Phase 8: BridgeClient(cmd, qry, sse, health_checker)      ← NOT BUILT

           BridgeClient
             │
    ┌────────┼────────┬────────────┬──────────────┬────────────┐
    ▼        ▼        ▼            ▼              ▼            ▼
  Fabric  Orchestrator Planner  Concierge  Memory Writer  SessionState
  (IBridgePort) (IBridgeWritePort) (IBridgePort) (IMemoryPort) (IBridgeCmdPort) (IK0SyncPort)
```

**Ordering constraint**: BridgeClient MUST be created BEFORE Orchestrator (Phase 4 needs bridge port), Planner (Phase 5 needs bridge port), and Concierge (Phase 6 needs memory port + Phase 6.5 needs household query).

kernel.md places Bridge at **Phase 5.5** (after Planner, before Concierge). But Orchestrator Phase 4 already passes `MockBridgeAdapter()` and Planner Phase 5 passes `TestBridgeAdapter()` — so Bridge can be created any time, with hot-swap later if needed.

**Decision (SIM-D-32): Bridge created early (Phase 2.5), consumed late.**

```
Phase 2.5: BridgeClient.connect(config) → bridge_client (or None if offline)
Phase 4:   Orchestrator bridge=BridgeWriteAdapter(bridge_client) if bridge_client else MockBridgeAdapter()
Phase 5:   Planner bridge_port=BridgeAdapter(fabric_bridge) — routes through Fabric
Phase 6:   Concierge memory_port=BridgeRecallAdapter(bridge_client) if bridge_client else MockMemoryAdapter()
Phase 6.5: HouseholdProjection hydration (if bridge_client not None)
```

---

#### 8.12 Gaps Found

| ID | Description | Severity |
|---|---|---|
| **SIM-GAP-33** | `BridgeClient` facade class does not exist. Kernel needs single entry point wrapping CommandPort + QueryPort + SSEPort. | **HIGH** |
| **SIM-GAP-34** | `IKernelQueryPort` (PORT_QRY) not implemented. Blocks: Concierge recall, Orchestrator WAL read, Planner recall, SS restore, Household hydration. | **HIGH** |
| **SIM-GAP-35** | `IKernelSSEPort` (PORT_SSE) not implemented. Blocks: Household live deltas, memory.formed events, proactive signals, learning advisories. | **HIGH** |
| **SIM-GAP-36** | `BridgeRecallAdapter` (Concierge IMemoryPort) not implemented. Spec exists in concierge.md §15.2.8 but no Python file. ~40 lines. | **MEDIUM** |
| **SIM-GAP-37** | `HouseholdProjection` dataclass + hydration protocol not implemented. Spec exists in kernel.md §126 but no Python file. ~60 lines. | **MEDIUM** |
| **SIM-GAP-38** | `IMemoryPort` Protocol not implemented as Python file. Defined in concierge.md §14.9 only. ~15 lines. | **MEDIUM** |
| **SIM-GAP-39** | `BridgeCommandAdapter` (Memory Writer → K0) not implemented. MW has port protocol but no adapter. ~30 lines. | **MEDIUM** |
| **SIM-GAP-40** | `BridgeSyncAdapter` (SessionState → K0) not implemented. IK0SyncPort exists but only NullSyncPort wired. | **LOW** |
| **SIM-GAP-41** | `IKernelObsPort` (PORT_OBS) not implemented. Blocks telemetry/feedback export to K0. Non-functional but important for production. | **LOW** |
| **SIM-GAP-42** | `IConnectorGatewayPort` not implemented. Blocks IFL/external device integration. Entire connector/ module is stub. | **LOW** (Phase 2+) |
| **SIM-GAP-43** | Bridge has zero imports from K0/K1 (clean boundary) but K1's `BridgeWriteAdapter` defines its own `IBridgeClient(Protocol)` — not aligned with any Bridge export. No shared interface contract. | **MEDIUM** |

---

#### 8.13 Flags Found

| ID | File | Problem | Impact |
|---|---|---|---|
| **SIM-FLAG-18** | `k1/concierge/kernel/bootstrap.py` L189 | `_build_recall_fn()` returns in-memory word-overlap scorer. Not a real Bridge adapter. Must be replaced with `BridgeRecallAdapter` or test stub implementing IMemoryPort. | POC recall has zero K0 integration |
| **SIM-FLAG-19** | `k1/concierge/fabric/poc_bridge_adapter.py` | `POCMockBridgeAdapter` routes to CapabilityRegistry handlers. Production needs `BridgeConnectionAdapter` wrapping real `BridgeClient`. | Dead code when real Bridge wired |
| **SIM-FLAG-20** | `k1/orchestrator/adapters/bridge_write_adapter.py` L72 | `IBridgeClient` Protocol defined locally inside adapter file. Should align with BridgeClient facade or be extracted to shared contract. | Interface mismatch risk |
| **SIM-FLAG-21** | `bridge/connector/__init__.py` | Entire connector module is empty stub. IFL/external device integration blocked until implemented. | No real tool execution via Bridge |

---

#### 8.14 Decisions

| ID | Question | Decision | Rationale |
|---|---|---|---|
| **SIM-D-29** | What is BridgeClient? | **Thin facade wrapping 3 ports** (CommandPort + QueryPort + SSEPort). Factory method `BridgeClient.connect(config) → BridgeClient or None`. | kernel.md expects query/send_command/subscribe/close. Facade delegates to specialized ports. |
| **SIM-D-30** | BridgeClient shared or per-session? | **Shared (one per process).** All K1 adapters receive same BridgeClient. | Bridge is infrastructure. Transport connection pool shared. LocalOutbox shared. |
| **SIM-D-31** | Is HouseholdProjection part of SessionState? | **NO.** Frozen in-memory projection cached in Concierge. Separate from SS. Per-turn: 0ms (no K0). | Family identity (names, allergies, governance) is household-level, not conversation-level. Changes rarely. |
| **SIM-D-32** | When to create BridgeClient in bootstrap? | **Phase 2.5 (early).** Created before Orchestrator/Planner/Concierge. `None` if offline — adapters receive None and use offline fallback. | All consumers need bridge reference. Phased stub approach (Phase 1: mock, Phase 2: real) matches kernel.md pattern. |
| **SIM-D-33** | How to handle bridge_client = None? | **Each adapter has built-in offline fallback.** No special kernel-level offline handling needed. | BridgeWriteAdapter: fire-and-forget (drop). BridgeAdapter: empty recall. BridgeRecallAdapter: LOCAL COLD. MockBridgeAdapter: in-memory. Pattern already established in all adapter implementations. |

---

#### 8.15 Step 8 Verdict

**Wiring: PARTIALLY achievable. PORT_CMD path is production-ready. PORT_QRY and PORT_SSE are NOT built.**

The Bridge component has a clean, well-tested command path: `KernelCommandPort → EnvelopeBuilder → HttpTransport → LocalOutbox`. This covers ALL fire-and-forget writes (memory.write, session.snapshot, plan.committed, etc.). The architecture is edge-first with robust offline handling (SQLite queue, 10K max, WAL mode, priority ordering).

**However, 3 of 4 K0 ports are missing:**

1. **PORT_QRY (IKernelQueryPort)** — Blocks ALL recall operations (Concierge, Orchestrator WAL, Planner, Household). This is the **biggest gap** for production. ~150 lines.
2. **PORT_SSE (IKernelSSEPort)** — Blocks live updates (Household deltas, memory events, proactive signals). ~100 lines.
3. **PORT_OBS (IKernelObsPort)** — Blocks telemetry export. ~50 lines. Non-critical for V1.

**The BridgeClient facade (~80 lines) is also needed** as the unified entry point for kernel wiring.

**For V1 kernel boot (Phase 1 per kernel.md):**

- `bridge_client = None` (offline mode) — ALL adapters use test stubs / offline fallbacks
- Command path works immediately when K0 available
- Recall, household, and live updates deferred to Phase 2 (when PORT_QRY + PORT_SSE built)

**Summary of work required:**

1. **Zero new code for V1 offline boot** — `bridge_client = None`, all adapters fall back
2. **~80 lines: BridgeClient facade** (SIM-GAP-33) — wraps 3 ports, connect() factory
3. **~150 lines: KernelQueryPort** (SIM-GAP-34) — PORT_QRY implementation (P1 for Phase 2)
4. **~100 lines: KernelSSEPort** (SIM-GAP-35) — PORT_SSE implementation (P2)
5. **~40 lines: BridgeRecallAdapter** (SIM-GAP-36) — Concierge IMemoryPort (P1 for Phase 2)
6. **~60 lines: HouseholdProjection** (SIM-GAP-37) — dataclass + hydration (P2)
7. **~15 lines: IMemoryPort Protocol** (SIM-GAP-38) — Python file from spec
8. **~30 lines: BridgeCommandAdapter** (SIM-GAP-39) — Memory Writer adapter (P2)

**Blockers for V1 boot: NONE** (offline mode is the designed V1 behavior per kernel.md Phase 1).
**Blockers for Phase 2 (K0-connected): PORT_QRY and BridgeClient facade** (~230 lines total).

**Resolved from prior steps:**

- **SIM-D-04** (shared vs per-session) — CONFIRMED: Bridge is shared (SIM-D-30). Same pattern as ModelHub (SIM-D-22), Orchestrator, Planner (SIM-D-25).
- **SIM-GAP-05** (Bridge has no OTel spans) — CONFIRMED still open. No tracing in Bridge core.
- **SIM-FLAG-01** (bootstrap imports POC) — Bridge wiring will replace `POCMockBridgeAdapter` with real adapters (SIM-FLAG-19).

**Next: Step 8.5 — Cross-Component Dependency Audit**

---

### STEP 8.5 — Cross-Component Dependency Audit

**Question:** Steps 4–8 wired each component in isolation. But ModelHub is consumed by Concierge, Planner, Fabric, AND Memory Writer. Fabric is consumed by Orchestrator, Planner, AND Concierge. Did we verify that the **same shared instance** can serve multiple consumers simultaneously? Do the port interfaces actually match?

**Assumption:** Steps 1–8 complete. ModelHub shared (SIM-D-22), Fabric per-session (SIM-D-22), Orchestrator+Planner shared (SIM-D-25). Bridge shared (SIM-D-30).

---

#### 8.5.1 What We Read

| File / Area | Scope | Key Discovery |
|---|---|---|
| `k1/model_hub/ports/hub_port.py` | Full | `IModelHubPort`: execute(HubRequest)→HubResponse, stream_execute, discover_capabilities, discover_models, health. Canonical 5-method protocol. |
| `k1/model_hub/adapters/llm_request_bus_adapter.py` | Full | `LLMRequestBusAdapter(inner: IModelHubPort)`: delegates to inner. Used by Planner's bus chain. |
| `k1/planner/ports/llm_port.py` | Full | `ILLMPort`: execute(HubRequest)→HubResponse. **Single method only** — subset of IModelHubPort. No stream_execute. |
| `k1/planner/adapters/llm_gateway_adapter.py` | Full | `LLMGatewayAdapter(bus: ILLMRequestBus, consumer_id: str)`: stamps consumer_id, delegates to bus. Stateless. |
| `k1/fabric/ports/model_gateway.py` | Full | `IModelGatewayPort`: create_handle(budget_tokens, model_preference?, capabilities?, trace_id)→ILLMHandle. **Completely different pattern** — handle-factory, not request-reply. |
| `k1/fabric/adapters/test_model_gateway.py` | Full | `TestModelGatewayAdapter`: test only. **No production adapter exists.** |
| `k1/memory_writer/ports/model_hub_port.py` | Full | `IModelHubPort`: chat(messages, budget_tokens, model_hint)→ChatResponse. **NAME COLLISION** — same protocol name, different module, different method signature. |
| `k1/orchestrator/ports/fabric_gateway_port.py` | Full | `IFabricGatewayPort`: execute, execute_batch, query_registry, query_registry_by_category. 4 methods. |
| `k1/orchestrator/adapters/fabric_gateway_adapter.py` | Full | `FabricGatewayAdapter(fabric: Fabric)`: wraps full container. Translates registry queries. Stateless. |
| `k1/planner/ports/fabric_retrieval_port.py` | Full | `IFabricRetrievalPort`: discover_capabilities, find_relevant_prompts. **2 methods only** — read-only, no execute(). |
| `k1/planner/adapters/fabric_retrieval_adapter.py` | Full | `FabricRetrievalAdapter(fabric_retrieval, timeout_ms=50)`: wraps `FabricRetrieval` object (NOT full Fabric container). Stateless. |
| `k1/fabric/adapters/sessionstate_reader.py` | Full | `SessionStateReaderAdapter(manager, session_id)`: **bound to single session at construction**. If caller passes different session_id, returns None. |
| `k1/concierge/fabric/ports.py` | Full | `IFabricPort`: execute, execute_batch, discover_capabilities, find_relevant_prompts. 4 methods — matches Fabric container API. |

---

#### 8.5.2 ModelHub Consumer Map — 4 Consumers, 4 Different Port Interfaces

```
                         ModelHub (shared singleton)
                         ┌────────────────────────────────┐
                         │  IModelHubPort (canonical)      │
                         │  execute(HubRequest)→HubResponse│
                         │  stream_execute(HubRequest)     │
                         │  discover_capabilities()        │
                         │  discover_models()              │
                         │  health()                       │
                         └───────┬────────┬────────┬───────┘
                                 │        │        │
                    ┌────────────┤        │        ├──────────────┐
                    ▼            ▼        ▼        ▼              ▼
              Concierge     Planner    Fabric   Memory Writer  Orchestrator
              IModelHubPort  ILLMPort  IModelGWPort IModelHubPort  (NONE)
              (canonical)   (subset)   (handle)    (collision!)

Consumer #1: Concierge (Front + Back + ReAct Loop)
  Port: IModelHubPort (from k1.model_hub.ports) — CANONICAL
  Adapter: ModelHubPOCBridge (wraps GeminiConciergeAdapter)
  Methods used: execute(), stream_execute()
  Stateless: ✅  Interface match: ✅

Consumer #2: Planner (Sketch + Expand + Validate + HIL)
  Port: ILLMPort (from k1.planner.ports) — DIFFERENT, SUBSET
  Methods: execute(HubRequest) → HubResponse only
  Adapter chain: ILLMPort → LLMGatewayAdapter → ILLMRequestBus → LLMRequestBusAdapter → IModelHubPort
  4-hop chain. Bus exists in k1/model_hub/adapters/llm_request_bus_adapter.py.
  Stateless: ✅  Interface match: SUBSET (no stream_execute, no discover)

Consumer #3: Fabric (Agent Factory → spawned agents)
  Port: IModelGatewayPort (from k1.fabric.ports) — COMPLETELY DIFFERENT
  Methods: create_handle(budget_tokens, ...) → ILLMHandle
  Sub-protocol: ILLMHandle.generate(prompt, params) → str
  Adapter: TestModelGatewayAdapter only — NO PRODUCTION ADAPTER
  Pattern: Handle-factory (budget-scoped, per-agent) vs request-reply
  Stateless: Port=✅, Handle=❌ (per-agent stateful budget)
  Interface match: ❌ COMPLETELY DIFFERENT PATTERN

Consumer #4: Memory Writer (WriterAgent extraction)
  Port: IModelHubPort (from k1.memory_writer.ports) — NAME COLLISION
  Methods: chat(messages, budget_tokens, model_hint) → ChatResponse
  Adapter: NOT BUILT (adapters/ directory doesn't exist)
  Interface match: ❌ SAME NAME, DIFFERENT METHODS
  MW-06: Always 2000 token budget. MW-07: Filter has NO LLM dep.

Consumer #5: Orchestrator
  Port: NONE — Orchestrator is pure deterministic. NO LLM access.
  Docstring: "Pure deterministic actor: NO LLM, NO tools, NEVER writes SessionState"
  Indirect LLM: Orchestrator → Fabric.execute(CapReq) → AgentProvider → LLM handle
```

**Finding MH-01: 4 different port interfaces for the same ModelHub.** Each consumer defines its own Protocol with different method signatures. Only Concierge uses the canonical `IModelHubPort`. This is NOT a bug — it's deliberate port-based isolation:

- Planner's `ILLMPort` is intentionally narrower (PLAN-06 principle: restrict what Planner can do)
- Fabric's `IModelGatewayPort` is intentionally handle-based (agent budget isolation)
- Memory Writer's `IModelHubPort` is intentionally chat-oriented (MW-06: 2000 token budget)

**Finding MH-02: Production adapters missing for 2 of 4 consumers.**

| Consumer | Production Adapter | Status | Effort |
|---|---|---|---|
| Concierge | `ModelHubPOCBridge` | ✅ Exists (swap at M7) | 0 lines |
| Planner | `LLMGatewayAdapter` → `LLMRequestBusAdapter` | ✅ Both exist | 0 lines |
| Fabric | `ModelHubGatewayAdapter` | ❌ NOT BUILT (SIM-GAP-20) | ~30 lines |
| Memory Writer | `ModelHubChatAdapter` | ❌ NOT BUILT | ~25 lines |

**Finding MH-03: Orchestrator has NO direct ModelHub dependency.** This was incorrectly stated in the original question. Orchestrator gets LLM access indirectly through Fabric capability execution — agents spawned by Fabric's AgentProvider receive LLM handles, but Orchestrator itself never touches ModelHub.

**Finding MH-04: Memory Writer `IModelHubPort` name collision.** `k1.memory_writer.ports.model_hub_port.IModelHubPort` has `chat()` method. `k1.model_hub.ports.hub_port.IModelHubPort` has `execute()` method. Same protocol name, different module path, completely different interface. Will cause import confusion. Needs a `chat() → execute(HubRequest)` adapter (~25 lines).

---

#### 8.5.3 Fabric Consumer Map — 3 Consumers, 3 Different Port Interfaces

```
                           Fabric (per-session — SIM-D-22)
                           ┌──────────────────────────────────────┐
                           │  Facade: execute, execute_batch,     │
                           │  discover_capabilities,              │
                           │  find_relevant_prompts, register,    │
                           │  unregister, lookup, health          │
                           │                                      │
                           │  Internal: FabricRetrieval (Role 1)  │
                           │  Internal: RegistryAPI               │
                           │  Bound: SessionStateReaderAdapter    │
                           │         (one SSM, one session)       │
                           └───────┬────────┬────────┬────────────┘
                                   │        │        │
                      ┌────────────┤        │        ├────────────┐
                      ▼            ▼                 ▼
               Orchestrator     Planner          Concierge
               IFabricGatewayPort  IFabricRetrievalPort   IFabricPort
               (4 methods)     (2 methods)       (4 methods)
               wraps FULL      wraps FabricRetrieval  IS Fabric container
               container       (Role 1 only)         directly

Consumer #1: Orchestrator (DAGExecutor → step execution)
  Port: IFabricGatewayPort (from k1.orchestrator.ports)
  Methods: execute, execute_batch, query_registry, query_registry_by_category
  Adapter: FabricGatewayAdapter(fabric: Fabric) — wraps FULL container
  Translation: query_registry maps CapabilityContract → RegistryEntry
  Translation: execute_batch hardcodes BatchStrategy.PARALLEL
  Stateless: ✅

Consumer #2: Planner (Sketch + Expand discovery)
  Port: IFabricRetrievalPort (from k1.planner.ports)
  Methods: discover_capabilities, find_relevant_prompts — READ ONLY
  Adapter: FabricRetrievalAdapter(fabric_retrieval: Any, timeout_ms=50)
  Wraps: FabricRetrieval object (NOT full Fabric container)
  Access via: fabric.retrieval (inner component)
  Stateless: ✅  PLAN-06: No execute() — structurally impossible

Consumer #3: Concierge (Tool implementations)
  Port: IFabricPort (from k1.concierge.fabric.ports)
  Methods: execute, execute_batch, discover_capabilities, find_relevant_prompts
  Adapter: NONE — Fabric container passed directly (SIM-D-20)
  Note: execute_batch(strategy="PARALLEL") vs Fabric(strategy=BatchStrategy.PARALLEL)
        BatchStrategy(str, Enum) so string works at runtime, type checker warns
```

---

#### 8.5.4 CRITICAL FINDING: Shared Orchestrator vs Per-Session Fabric Conflict

**The Problem:**

| Component | Lifecycle | Needs Fabric? | Fabric Instance |
|---|---|---|---|
| Orchestrator | **SHARED** (SIM-D-25) | YES — FabricGatewayAdapter wraps full Fabric | Needs shared or session-resolved Fabric |
| Planner | **SHARED** (SIM-D-25) | YES — FabricRetrievalAdapter wraps FabricRetrieval | Needs shared or session-resolved Fabric |
| Concierge | **PER-SESSION** | YES — ToolContext.fabric_port = Fabric | Gets per-session Fabric (SIM-D-22) |

**Why Fabric is per-session (SIM-D-22):** `SessionStateReaderAdapter` is bound to ONE SSM at construction time. It's baked into 3 Fabric internals:

- `ContextBuilder` — reads session state for every `execute()` call
- `AffectiveRouting` — reads affect state for policy routing
- `CognitiveLoadRouting` — reads cognitive load for policy decisions

**The Conflict:** Orchestrator is a shared singleton processing tasks for ALL sessions. But `FabricGatewayAdapter(fabric)` holds ONE Fabric instance bound to ONE session's SSM. If Session A's task runs through the shared Orchestrator, the Fabric reads Session B's state (whichever SSM was bound at construction).

**Analysis of Resolution Paths:**

**Path 1: `CapabilityRequest.session_id` dynamic resolution** ← MOST LIKELY INTENDED
The `CapabilityRequest` already carries a `session_id` field. `ContextBuilder.build()` takes `session_id` as a parameter. If the `SessionStateReaderAdapter.read_section()` checks `session_id` against its bound ID (it does — returns None on mismatch), then:

- Orchestrator passes session-specific context via `CapabilityRequest.session_id`
- Fabric's ContextBuilder calls `state_reader.read_section(session_id, section)`
- If session_id doesn't match the bound SSM → returns None → context is empty
- Fabric still executes the capability but without session context enrichment

This works for V1 but means Orchestrator tasks execute **without session context** (beliefs, affect, cognitive load). For MEDIUM tier tasks (simple capability calls), this is acceptable. For complex workflows that need session-aware routing, it's degraded.

**Path 2: Fabric pool / session-resolved factory** ← CLEAN BUT EXPENSIVE
Create a `FabricSessionPool` that KernelService maintains. When Orchestrator needs to execute for session X, it requests `pool.get_fabric(session_id)` which returns the per-session Fabric instance. Requires Orchestrator to be pool-aware.

**Path 3: Orchestrator gets its own Fabric with NullStateReader** ← SIMPLEST V1
Create a shared Fabric with `NullSessionStateReaderAdapter()` (returns empty for all reads). Orchestrator executes capabilities without session context. This is already what happens in Path 1 when session_id doesn't match.

**Decision (SIM-D-34): V1 — Orchestrator gets Fabric with NullStateReader. Session context is NOT available during orchestrated task execution.**

Rationale:

1. ContextBuilder reads session state for prompt enrichment — capabilities still execute without it
2. AffectiveRouting degrades to default routing (GREEN band, neutral affect)
3. CognitiveLoadRouting degrades to default load assessment
4. Orchestrator's primary job is DAG execution + step coordination — session context is nice-to-have, not critical
5. Planner also gets NullStateReader Fabric (discovery doesn't need session context)
6. V2: Implement session-resolved Fabric pool when session-aware orchestration is needed

**Consequence for factory wiring:**

```
KernelService startup (shared components):
  shared_fabric = FabricFactory.create_with_ports(
    state_reader=NullSessionStateReaderAdapter(),  # No session context
    event_port=LocalEventAdapter(),
    bridge=bridge_or_mock,
    model_gateway=ModelHubGatewayAdapter(model_hub),
    prompt_system=TestPromptSystemAdapter(),
    delta_bus=NullDeltaBusAdapter(),  # Shared Fabric has no per-session bus
  )
  orchestrator = OrchestratorFactory.create_production(
    fabric=FabricGatewayAdapter(shared_fabric), ...
  )
  planner = PlannerFactory.create_production(
    fabric_port=FabricRetrievalAdapter(shared_fabric.retrieval), ...
  )

KernelService per-session (per-session components):
  session_fabric = FabricFactory.create_with_ports(
    state_reader=SessionStateReaderAdapter(ssm, session_id),  # Session-bound
    event_port=BusBridgeEventAdapter(bus),
    bridge=bridge_or_mock,
    model_gateway=ModelHubGatewayAdapter(model_hub),
    prompt_system=TestPromptSystemAdapter(),
    delta_bus=BusDeltaAdapter(bus),  # Per-session bus
  )
  concierge = ConciergeFactory.create_with_ports(
    ports=ExternalPorts(fabric=session_fabric, ...),
  )
```

**This means there are TWO Fabric instances:** One shared (for Orchestrator + Planner) with NullStateReader, and one per-session (for Concierge) with real SessionStateReader. This is a significant amendment to SIM-D-22.

**Decision (SIM-D-35): TWO Fabric instances — shared (NullState) + per-session (real State).**

---

#### 8.5.5 Planner's Fabric Access — Clean, No Issues

Planner uses `IFabricRetrievalPort` (2 read-only methods). The adapter wraps `FabricRetrieval` (Fabric Role 1), NOT the full container. `FabricRetrieval` does NOT read session state for discovery operations — it uses the embedding index and registry.

Planner can use EITHER the shared Fabric's retrieval (`shared_fabric.retrieval`) or a per-session Fabric's retrieval. Since discovery doesn't need session context, shared is correct.

**No issues found.** Planner→Fabric path is clean.

---

#### 8.5.6 Planner ↔ Orchestrator (Already Covered)

Step 7 fully covered this via Phase 5b cross-wiring. Orchestrator's `IPlannerPort` → `PlannerAdapter(planner_mailbox, cb)` → async mailbox. No new findings.

---

#### 8.5.7 ModelHub → Planner Wiring Chain Verification

The 4-hop chain: `ILLMPort → LLMGatewayAdapter → ILLMRequestBus → LLMRequestBusAdapter → IModelHubPort`

| Hop | Class | Exists? | Stateless? |
|---|---|---|---|
| 1 | `ILLMPort` (Protocol) | ✅ `k1/planner/ports/llm_port.py` | N/A (interface) |
| 2 | `LLMGatewayAdapter` | ✅ `k1/planner/adapters/llm_gateway_adapter.py` | ✅ (stamps consumer_id only) |
| 3 | `ILLMRequestBus` (Protocol) | ✅ Defined in `llm_gateway_adapter.py` | N/A (interface) |
| 4 | `LLMRequestBusAdapter` | ✅ `k1/model_hub/adapters/llm_request_bus_adapter.py` | ✅ (delegates to inner) |

**All 4 hops exist.** The chain is complete. SIM-GAP-32 (Planner LLM bus intermediary) is **RESOLVED** — both sides of the bus exist. The bus itself is an in-process protocol (direct method call), not an actual message bus.

**Wiring in kernel bootstrap:**

```python
# Hub side:
bus_adapter = LLMRequestBusAdapter(inner=model_hub)  # wraps shared ModelHub

# Planner side:
llm_port = LLMGatewayAdapter(bus=bus_adapter, consumer_id="planner")

# Pass to factory:
planner = PlannerFactory.create_production(llm_port=llm_port, ...)
```

---

#### 8.5.8 Memory Writer LLM — Name Collision + Missing Adapter

| Aspect | Detail |
|---|---|
| Protocol | `k1.memory_writer.ports.model_hub_port.IModelHubPort` — **collides** with `k1.model_hub.ports.hub_port.IModelHubPort` |
| MW method | `chat(messages: List[Dict], budget_tokens: int, model_hint: str) → ChatResponse` |
| Hub method | `execute(request: HubRequest) → HubResponse` |
| Adapter needed | `ModelHubChatAdapter`: converts `chat(messages, budget, hint) → HubRequest(messages, constraints={max_tokens=budget}, model_hint=hint) → hub.execute() → extract text → ChatResponse` |
| Effort | ~25 lines |
| MW constraint | MW-06: budget_tokens=2000 always. MW-07: Filter has no LLM dep. |

This adapter is straightforward but doesn't exist yet.

---

#### 8.5.9 Cross-Dependency Summary Matrix

```
                    CONSUMES →
                    ModelHub    Fabric      Planner     Bridge      Bus(session)   SSM
COMPONENT ↓         (shared)   (sh/session) (shared)   (shared)    (per-session)  (per-session)
─────────────────────────────────────────────────────────────────────────────────────────────
Orchestrator        ❌ NONE     ✅ SHARED    ✅ Phase5b  ✅ Step8    ❌ NONE        ❌ NONE
Planner             ✅ via bus  ✅ SHARED    N/A (self)  ✅ Step8    ❌ NONE        ❌ NONE
Fabric (shared)     ✅ GW port  N/A (self)  ❌ NONE     ✅ Step8    ❌ NullDelta   ❌ NullState
Fabric (session)    ✅ GW port  N/A (self)  ❌ NONE     ✅ Step8    ✅ BusDelta    ✅ SSM Reader
Concierge           ✅ direct   ✅ SESSION   ❌ NONE     ✅ Step8    ✅ direct      ✅ direct
Memory Writer       ✅ chat     ❌ NONE      ❌ NONE     ✅ Step8    ❌ NONE        ❌ NONE
```

---

#### 8.5.10 Gaps Found

| ID | Description | Severity |
|---|---|---|
| **SIM-GAP-44** | Shared Orchestrator uses per-session Fabric (SIM-D-22). SessionStateReaderAdapter bound to one SSM at construction. Orchestrator would read wrong session's state. Requires TWO Fabric instances (shared with NullState + per-session with real State). | **HIGH** |
| **SIM-GAP-45** | `IModelGatewayPort` production adapter (Fabric→ModelHub) not built. TestModelGatewayAdapter exists for tests. Need `ModelHubGatewayAdapter` that wraps `IModelHubPort.execute()` into handle-factory pattern. ~30 lines. (Same as SIM-GAP-20, now confirmed cross-cutting.) | **MEDIUM** |
| **SIM-GAP-46** | Memory Writer `IModelHubPort` name collision with canonical `k1.model_hub.ports.hub_port.IModelHubPort`. Different method signatures (`chat()` vs `execute()`). Will cause import confusion. Needs `ModelHubChatAdapter` (~25 lines). | **MEDIUM** |
| **SIM-GAP-47** | Shared Fabric needs `NullSessionStateReaderAdapter` and `NullDeltaBusAdapter` — neither exists. Each is ~10 lines (return empty/no-op). | **LOW** |
| **SIM-GAP-48** | Two Fabric instances means two `CapabilityRegistry` instances. Capability registration must happen on BOTH (shared + per-session), or registrations from shared must propagate to per-session instances. | **MEDIUM** |

---

#### 8.5.11 Flags Found

| ID | File | Problem | Impact |
|---|---|---|---|
| **SIM-FLAG-22** | `k1/fabric/adapters/sessionstate_reader.py` L66-67 | `__init__(self, manager, session_id)` — adapter permanently bound to one session. Cannot serve cross-session Orchestrator. | Forces TWO Fabric instances or session-resolved pool. |
| **SIM-FLAG-23** | `k1/memory_writer/ports/model_hub_port.py` L37 | `class IModelHubPort(Protocol)` — name collision with `k1.model_hub.ports.hub_port.IModelHubPort`. Different interface. | Import confusion. Should rename to `IMemoryWriterLLMPort` or similar. |
| **SIM-FLAG-24** | `k1/concierge/fabric/ports.py` | `IFabricPort.execute_batch(strategy="PARALLEL")` — string arg. `Fabric.execute_batch(strategy=BatchStrategy.PARALLEL)` — enum arg. `BatchStrategy(str, Enum)` so runtime OK, type checker warns. | Minor type mismatch. Works at runtime. |

---

#### 8.5.12 Decisions

| ID | Question | Decision | Rationale |
|---|---|---|---|
| **SIM-D-34** | How does shared Orchestrator access Fabric when Fabric is per-session? | **V1: Orchestrator gets Fabric with NullStateReader.** Capabilities execute without session context. AffectiveRouting/CognitiveLoadRouting degrade to defaults. | Session context is nice-to-have for orchestrated tasks, not critical. V2: session-resolved Fabric pool. |
| **SIM-D-35** | How many Fabric instances? | **TWO: shared Fabric (NullState, for Orch+Planner) + per-session Fabric (real SSM, for Concierge).** | SessionStateReaderAdapter is bound at construction. Cannot serve multiple sessions. Shared Fabric works without session context. Per-session Fabric gets full context. |
| **SIM-D-36** | How does shared Fabric get capabilities? | **Register capabilities on shared Fabric. Per-session Fabric copies registry at session creation time OR shares a reference to the same CapabilityRegistry.** | Capabilities don't change per session. Registry is thread-safe. Sharing the registry object avoids double-registration. |
| **SIM-D-37** | How does Memory Writer get LLM access? | **`ModelHubChatAdapter` (~25 lines): converts `chat(messages, budget, hint) → HubRequest → hub.execute() → ChatResponse`.** MW never touches ModelHub directly. | MW-06 enforces 2000 token budget. Adapter maps MW's chat interface to Hub's execute interface. |

---

#### 8.5.13 Amendments to Prior Decisions

| Original Decision | Amendment | Reason |
|---|---|---|
| **SIM-D-22** (Fabric per-session) | **AMENDED: Fabric has TWO instances — shared + per-session.** Shared Fabric (NullState) for Orchestrator + Planner. Per-session Fabric (real SSM) for Concierge. | SessionStateReaderAdapter bound at construction. Shared Orchestrator can't use per-session Fabric. |
| **SIM-D-04** (component sharing table) | **ADD: Fabric (shared) for Orch+Planner. Fabric (per-session) for Concierge.** | Cross-component audit revealed the shared/per-session conflict. |
| **SIM-GAP-32** (Planner LLM bus intermediary) | **RESOLVED.** Both sides exist: `LLMGatewayAdapter` + `LLMRequestBusAdapter`. 4-hop chain complete. | Audit found all 4 hops implemented and compatible. |

---

#### 8.5.14 Step 8.5 Verdict

**3 cross-component issues discovered that Steps 4–8 missed:**

1. **HIGH: Shared Orchestrator ↔ per-session Fabric conflict (SIM-GAP-44).** The most significant finding. Requires TWO Fabric instances. SIM-D-22 amended. ~20 lines of NullAdapters + factory wiring change.

2. **MEDIUM: Memory Writer IModelHubPort name collision (SIM-GAP-46).** Two protocols with same name, different interfaces. Needs rename or adapter. ~25 lines.

3. **MEDIUM: Capability registry sharing (SIM-GAP-48).** Two Fabric instances means registry must be shared or synchronized. Solvable by passing same CapabilityRegistry object to both Fabric instances.

**Planner→ModelHub chain CONFIRMED complete** (SIM-GAP-32 resolved). Planner→Fabric chain CONFIRMED clean. Orchestrator→Planner chain was already covered (Step 7).

**Running totals after Step 8.5: 48 gaps, 24 flags, 37 decisions.**

**Next: Step 9 — 8-Phase Bootstrap Assembly**

---

### STEP 9 — 8-Phase Bootstrap Assembly

**Question:** Wire all components from Steps 4–8 into the `k1/kernel/bootstrap.py` 8-phase sequence. Does the init order work? Any circular dependencies?

**What we read:**

- kernel.md §7 (Bootstrap Sequence, L~400–600) — canonical pseudocode
- kernel.md §8 (Shutdown Sequence, L~650–680) — 10-step teardown
- kernel.md §3 (Dependency Graph, L42–135) — full wiring tree
- kernel.md §4 (Port Wiring Matrix, L136–250) — all adapter signatures
- All 37 decisions from Steps 1–8.5
- All 48 gaps, 24 flags
- Real factory signatures from subagent audits

**What we discover:**

1. **NEW GAP: Planner's SessionStateReadAdapter is session-locked (SIM-GAP-49, HIGH)**
2. **NEW GAP: DAGExecutor hardcodes session_id="default" (SIM-GAP-50, MEDIUM)**
3. kernel.md's Phase 3 creates ONE Fabric but simulation requires TWO (SIM-D-35 amendment)
4. kernel.md's Phase 5 creates Planner with session-locked `SessionStateReadAdapter(state_reader, session_id)` but Planner is shared (SIM-D-25) — contradiction
5. Orchestrator is session-safe (StateReadAdapter takes session_id per-call) — confirmed clean
6. No circular dependencies in the final wiring order
7. Bootstrap splits into TWO tiers: **Startup tier** (shared components, once) + **Session tier** (per-session components, on session create)

---

#### 9.1 Key Discovery: Planner's State Port is Session-Locked

This was missed in Steps 6–8.5 because the focus was on Fabric's SessionStateReaderAdapter.

**Orchestrator StateReadAdapter** — every method takes `session_id` explicitly:

```python
# k1/orchestrator/adapters/state_read_adapter.py
def __init__(self, state_reader: ISessionStateReader) -> None:
    self._reader = state_reader

async def read_section(self, session_id: str, section: str):  # session_id per-call ✅
async def get_snapshot(self, session_id: str):                 # session_id per-call ✅
```

Orchestrator passes `session_id` from TaskEnvelope at every call site. **Session-safe.**

**Planner SessionStateReadAdapter** — session_id baked in at construction:

```python
# k1/planner/adapters/session_state_adapter.py
def __init__(self, reader: Any, session_id: str) -> None:
    self._reader = reader
    self._session_id: str = session_id  # LOCKED at construction

async def read_sections(self, sections: List[str], trace_id: str = ""):
    return self._reader.read_sections(self._session_id, sections)  # uses pre-bound session_id
```

Planner's port docstring explicitly states: *"Session ID is NOT a parameter — the adapter knows the active session."*

**If Planner is shared (SIM-D-25) and its state adapter is constructed with ONE session_id, all plans read one session's cognitive context.** Session B's plan gets Session A's beliefs.

**However:** Planner's other 6 adapters are ALL session-safe:

| Adapter | Session-locked? |
|---|---|
| MailboxAdapter | ✅ Session-safe (pure queue) |
| LLMGatewayAdapter | ✅ Session-safe (consumer_id stamped, not session-bound) |
| FabricRetrievalAdapter | ✅ Session-safe (session_context passed per-call) |
| BridgeAdapter | ✅ Session-safe (no session binding) |
| DeltaBusAdapter | ✅ Session-safe (agent_id stamped, not session-bound) |
| EventBusAdapter | ✅ Session-safe (pure passthrough) |
| **SessionStateReadAdapter** | **🔒 SESSION-LOCKED** |

**Fix options:**

- **A: Refactor Planner IStateReadPort to accept session_id per-call** (match Orchestrator pattern). Cleanest. ~20 lines refactor + 4 call sites.
- **B: Inject per-session SessionStateReadAdapter at plan-request time** (adapter pool). Complex. Requires thread-safe adapter swap.
- **C: Copy session snapshot into PlanRequest** (Orchestrator already puts SessionSnapshot in PlanRequest.context). Planner reads from snapshot, not live state. Simplest.

**Decision needed: SIM-D-38.**

---

#### 9.2 Discovery: DAGExecutor Hardcoded session_id

```python
# k1/orchestrator/orchestration/dag_executor.py L989-993
band_data = await self._state_port.read_section(
    session_id="default",    # ⚠️ HARDCODED
    section="control.safety_band",
)
```

DAGExecutor hardcodes `"default"` for safety band reads. Even though `StateReadAdapter` accepts `session_id` per-call, DAGExecutor doesn't pass the real one from the task envelope. Safety band checks always hit the wrong session.

**Fix:** Pass `session_id` from `self._context.session_id` or `self._envelope.context["session_id"]`. ~1-line fix.

---

#### 9.3 kernel.md vs Simulation: Phase Conflict Analysis

kernel.md §7 defines a **single-session** bootstrap (creates one of everything). Simulation (SIM-D-02, SIM-D-25) requires a **two-tier** bootstrap: shared startup + per-session creation.

| kernel.md Phase | kernel.md Assumption | Simulation Reality | Conflict? |
|---|---|---|---|
| Phase 1: Bus | One bus | Per-session bus (SIM-D-01) | **YES** — Bus moves to session tier |
| Phase 2: SessionState | One SSM | Per-session SSM (SIM-D-04) | **YES** — SSM moves to session tier |
| Phase 3: Fabric | One Fabric | TWO Fabrics (SIM-D-35) | **YES** — Shared at startup, per-session at session create |
| Phase 3.5: ModelHub | One hub | One hub, shared (SIM-D-21) | ✅ No conflict |
| Phase 4: Orchestrator | One orch | One orch, shared (SIM-D-25) | ✅ No conflict (but uses shared Fabric) |
| Phase 5: Planner | One planner | One planner, shared (SIM-D-25) | ⚠️ State adapter conflict (SIM-GAP-49) |
| Phase 5.5: Bridge | One bridge | One bridge, shared (SIM-D-30) | ✅ No conflict |
| Phase 6: Concierge | One concierge | Per-session concierge (SIM-D-02) | **YES** — Concierge moves to session tier |
| Phase 6.5: Household | Post-concierge hydration | Per-session hydration | **YES** — moves to session tier |
| Phase 7: Start lifecycle | session_manager.start() | Per-session | **YES** — moves to session tier |
| Phase 8: Expose API | KernelRuntime return | KernelRuntime = shared + session registry | ⚠️ Structural change |

**6 of 10 phases have conflicts.** The bootstrap must be restructured.

---

#### 9.4 Revised Bootstrap: Two-Tier Architecture

**Tier 1: KernelService.startup()** — runs once at process start.
**Tier 2: KernelService.create_session(session_id)** — runs per session.

```
TIER 1 — STARTUP (once per process)
═══════════════════════════════════
Phase S1: Shared Config
Phase S2: ModelHub (shared, stateless)
Phase S3: Shared Fabric (NullState, for Orch+Planner)
Phase S4: BridgeClient (shared, None if offline)
Phase S5: Orchestrator (shared, with MockPlanner)
Phase S6: Planner (shared, with snapshot-based state)
Phase S6b: Cross-wire Orch↔Planner (hot-swap)
Phase S7: Expose KernelRuntime (shared components)

TIER 2 — SESSION CREATE (per session)
══════════════════════════════════════
Phase P1: Per-session Bus
Phase P2: Per-session SessionState
Phase P3: Per-session Fabric (real SSM, shared CapabilityRegistry)
Phase P4: Per-session Concierge (wired to shared Orch + per-session Fabric + SSM)
Phase P5: Household hydration
Phase P6: Start session lifecycle
Phase P7: Register SessionInstance in KernelService
```

---

#### 9.5 Final Bootstrap Pseudocode — Tier 1 (Startup)

```python
async def startup(config: KernelConfig) -> KernelRuntime:
    """TIER 1: Create shared components. Runs once per process."""

    # ─── Phase S1: Configuration ───────────────────────────────
    model_hub_config = ModelHubConfig.from_dict(config.model_hub)
    orch_config = OrchestratorConfig.from_dict(config.orchestrator)
    planner_config = PlannerConfig.from_dict(config.planner)
    bridge_config = BridgeConfig.from_dict(config.bridge)
    fabric_config = config.fabric  # contracts_dir, capability registry

    # ─── Phase S2: ModelHub (SIM-D-21: factory, SIM-D-22: shared) ──
    model_hub = ModelHubFactory.create_standalone(
        config=model_hub_config,
        plugins=_load_plugins(config),  # OpenAI, Anthropic, Google, etc.
    )
    # Shared across all sessions. Stateless w.r.t. kernel. (MH-01)

    # ─── Phase S3: Shared Fabric (SIM-D-35: NullState instance) ────
    #     For Orchestrator + Planner. No session context.
    shared_capability_registry = CapabilityRegistry()  # (SIM-D-36: shared registry)
    null_state_reader = NullSessionStateReaderAdapter()  # (SIM-GAP-47: to be built, ~10 lines)
    null_event_port = NullEventPortAdapter()             # no bus at startup tier
    null_delta_bus = NullDeltaBusAdapter()               # (SIM-GAP-47: to be built, ~10 lines)

    shared_fabric = FabricFactory.create_with_ports(
        state_reader=null_state_reader,
        event_port=null_event_port,
        delta_bus=null_delta_bus,
        bridge=TestBridgeAdapter(),              # Phase 1 stub; Phase 2: BridgeAdapter(bridge_client)
        model_gateway=ModelHubGatewayAdapter(model_hub),  # (SIM-GAP-20/45: to be built, ~30 lines)
        prompt_system=TestPromptSystemAdapter(),  # (SIM-GAP-22: future scope)
        capability_registry=shared_capability_registry,  # (SIM-D-36: injected, not created internally)
        production_mode=True,
        contracts_dir=str(fabric_config.contracts_dir),
    )

    # ─── Phase S4: BridgeClient (SIM-D-29/30/32: shared, early) ───
    bridge_client = await BridgeClient.connect(bridge_config)  # None if offline (SIM-D-33)
    # If bridge_client is not None, upgrade shared_fabric bridge adapters:
    if bridge_client is not None:
        shared_fabric.bridge = BridgeConnectionAdapter(bridge_client)
        # Also set production model gateway if not already done

    # ─── Phase S5: Orchestrator (SIM-D-25: shared, SIM-D-26: mock planner) ──
    orchestrator = await OrchestratorFactory.create_production(
        orch_config,
        mailbox=MailboxAdapter(max_depth=orch_config.mailbox_capacity),
        fabric=FabricGatewayAdapter(shared_fabric),           # shared Fabric (NullState)
        planner=MockPlannerAdapter(),                          # hot-swapped in Phase S6b
        state=StateReadAdapter(null_state_reader),             # shared reader — session_id per-call ✅
        delta=DeltaEmitAdapter(null_event_port, null_delta_bus),
        bridge=MockBridgeAdapter() if bridge_client is None
               else BridgeWriteAdapter(bridge_client),
        event=EventSubscriptionAdapter(null_event_port),
        storage=WorkflowStorageAdapter(SQLiteWorkflowAdapter(orch_config.workflow_db_path)),
    )

    # ─── Phase S6: Planner (SIM-D-25: shared, SIM-D-38: snapshot state) ──
    llm_request_bus = LLMRequestBusAdapter(inner=model_hub)   # (SIM-GAP-32: resolved, 4-hop chain)
    planner = await PlannerFactory.create_production(
        llm_port=LLMGatewayAdapter(bus=llm_request_bus, consumer_id="planner"),
        fabric_port=FabricRetrievalAdapter(shared_fabric),     # shared Fabric retrieval ✅
        state_port=SnapshotStateReadAdapter(),                  # (SIM-D-38: reads from PlanRequest.context snapshot)
        bridge_port=TestBridgeAdapter() if bridge_client is None
                    else BridgeAdapter(bridge_client),
        delta_port=DeltaBusAdapter(null_delta_bus),
        event_port=EventBusAdapter(null_event_port),
        mailbox_port=PlannerMailbox(max_depth=planner_config.mailbox_max_depth),
        config=planner_config,
    )
    planner_task = asyncio.create_task(planner.start())

    # ─── Phase S6b: Cross-wire Orch↔Planner (SIM-D-26: hot-swap) ──
    planner_mailbox = planner.get_mailbox()
    cb_planner = CircuitBreaker("CB_PLANNER",
        failure_threshold=orch_config.cb_planner_failure_threshold,
        reset_timeout_s=orch_config.cb_planner_reset_timeout_ms / 1000)
    planner_adapter = PlannerAdapter(planner_mailbox, cb_planner)
    orchestrator._planner_port = planner_adapter  # (SIM-GAP-29: private attr, V1 accept)

    # ─── Phase S7: Expose shared runtime ────────────────────────
    return KernelRuntime(
        model_hub=model_hub,
        shared_fabric=shared_fabric,
        shared_capability_registry=shared_capability_registry,
        bridge_client=bridge_client,
        orchestrator=orchestrator,
        planner=planner,
        planner_task=planner_task,
        config=config,
        sessions={},  # populated by create_session()
    )
```

---

#### 9.6 Final Bootstrap Pseudocode — Tier 2 (Session Create)

```python
async def create_session(runtime: KernelRuntime, session_id: str) -> SessionInstance:
    """TIER 2: Create per-session components. Runs for each new session."""
    config = runtime.config

    # ─── Phase P1: Per-session Bus (SIM-D-01: per-session, SIM-D-13: KernelService creates) ──
    bus = BusFactory.create_local(backend="auto")
    mailbox_router = BusFactory.create_mailbox_router(backend="auto")
    # (SIM-D-15: TracingMiddleware auto-stamps session_id + cognitive_trace_id)
    bus.add_middleware(TracingMiddleware(session_id=session_id))

    # ─── Phase P2: Per-session SessionState (SIM-D-18/19) ─────
    session_events = SessionBusAdapter(bus)
    session_manager = SessionStateFactory.create_with_ports(
        session_id=session_id,
        storage=SQLiteStorageAdapter(db_path=config.session_db_path(session_id)),
        events=session_events,
        writer=DirectWriterAdapter(),
        lifecycle=StandaloneLifecycle(
            config=LifecycleConfig(checkpoint_interval_s=config.checkpoint_s)),
        k0_sync=NullSyncPort(),  # V1: no cloud sync (SIM-GAP-40)
    )
    # (SIM-D-18: KernelService calls start() — done in Phase P6)

    # ─── Phase P3: Per-session Fabric (SIM-D-35: real SSM) ────
    fabric_bus = FabricBusAdapter(bus)
    state_reader = SessionStateReaderAdapter(session_manager)
    session_fabric = FabricFactory.create_with_ports(
        state_reader=state_reader,
        event_port=fabric_bus,
        delta_bus=fabric_bus,                    # same instance
        bridge=TestBridgeAdapter() if runtime.bridge_client is None
               else BridgeConnectionAdapter(runtime.bridge_client),
        model_gateway=ModelHubGatewayAdapter(runtime.model_hub),  # shared ModelHub
        prompt_system=TestPromptSystemAdapter(),  # Phase 1 stub
        capability_registry=runtime.shared_capability_registry,   # (SIM-D-36: SHARED registry)
        production_mode=True,
        contracts_dir=str(config.fabric.contracts_dir),
    )

    # ─── Phase P4: Per-session Concierge (SIM-D-02/09/20/24) ──
    concierge_config = ConciergeConfig.from_dict(config.concierge)
    concierge = await ConciergeFactory.create_with_ports(
        input_port=TestInputAdapter(),           # Phase 1 stub; Phase 2: WebSocketInputAdapter(ws)
        output_port=TestOutputAdapter(),         # Phase 1 stub; Phase 2: SSEOutputAdapter(sse)
        classification_port=MockClassificationAdapter(),  # Phase 1 stub; Phase 2: UltraBERTv4Adapter()
        llm_port=ModelGatewayAdapter(runtime.model_hub),  # shared ModelHub (SIM-D-21)
        state_port=session_manager,              # (SIM-D-17: SSM IS the IStatePort — no wrapper)
        dispatch_port=FabricOrchestratorAdapter(  # (SIM-D-24: replaces OrchestratorStub)
            fabric=session_fabric,                # per-session Fabric for LOW tier
            orchestrator=runtime.orchestrator,    # shared Orchestrator for MED/HIGH tier
            cb_orch=CircuitBreaker("CB_ORCH", ...),
            cb_fabric=CircuitBreaker("CB_FABRIC", ...),
            cb_mcp=CircuitBreaker("CB_MCP", ...),
        ),
        delta_port=ConciergeDeltaBusAdapter(fabric_bus, bus),  # per-session bus
        memory_port=BridgeRecallAdapter(runtime.bridge_client) if runtime.bridge_client
                    else TestBridgeAdapter(),     # (SIM-GAP-36: to be built)
        config=concierge_config,
    )
    concierge_task = asyncio.create_task(concierge.start())

    # ─── Phase P5: Household hydration (SIM-D-31: not SS, frozen projection) ──
    if runtime.bridge_client is not None:
        household_snapshot = await runtime.bridge_client.query(
            "household.projection.v1",
            params={"session_id": session_id},
        )
        await concierge.hydrate_household(household_snapshot)
        await runtime.bridge_client.subscribe(
            "household.delta.v1",
            handler=concierge.apply_household_delta,
        )
    else:
        await concierge.hydrate_household_from_local_cold()  # edge-first (SIM-D-31)

    # ─── Phase P6: Start session lifecycle ─────────────────────
    session_manager.start()  # (SIM-D-18: KernelService starts SSM)

    # ─── Phase P7: Register SessionInstance ────────────────────
    instance = SessionInstance(
        session_id=session_id,
        bus=bus,
        mailbox_router=mailbox_router,
        session_manager=session_manager,
        fabric=session_fabric,
        concierge=concierge,
        concierge_task=concierge_task,
        state="ACTIVE",
    )
    runtime.sessions[session_id] = instance
    return instance
```

---

#### 9.7 Circular Dependency Analysis

Checking all `Phase X needs Phase Y` edges for cycles:

```
S1 (Config)         → nothing
S2 (ModelHub)       → S1
S3 (Shared Fabric)  → S1, S2 (for ModelHubGatewayAdapter)
S4 (Bridge)         → S1
S5 (Orchestrator)   → S1, S3 (FabricGatewayAdapter), S4 (BridgeWriteAdapter)
S6 (Planner)        → S1, S2 (LLMGatewayAdapter), S3 (FabricRetrievalAdapter), S4 (BridgeAdapter)
S6b (Cross-wire)    → S5 (Orchestrator), S6 (Planner)
S7 (Expose)         → S2, S3, S4, S5, S6

P1 (Bus)            → nothing (pure infrastructure)
P2 (SSM)            → P1 (SessionBusAdapter)
P3 (Session Fabric) → P1 (FabricBusAdapter), P2 (SessionStateReaderAdapter), S2 (ModelHub), S3 (shared registry)
P4 (Concierge)      → P1 (bus), P2 (SSM), P3 (session Fabric), S2 (ModelHub), S5 (Orchestrator)
P5 (Household)      → P4 (Concierge), S4 (Bridge)
P6 (Start SSM)      → P2 (SSM)
P7 (Register)       → all above
```

**Dependency graph is a DAG.** No circular dependencies. All edges point forward (higher-numbered phases depend on lower-numbered phases).

The only tricky edge is **S6b** (cross-wire), which requires BOTH S5 (Orchestrator) and S6 (Planner) to be created. Since Orchestrator starts with MockPlannerAdapter, there's no cycle — S5 is fully created before S6, then S6b connects them.

**Verdict: No circular dependencies.** ✅

---

#### 9.8 Config Schema

Each phase needs specific configuration. Unified under `KernelConfig`:

```python
@dataclass
class KernelConfig:
    """Unified configuration for KernelService startup + session creation."""

    # ── Phase S1: General ──────────────────────────────────────
    log_level: str = "INFO"
    session_db_base_dir: str = "./data/sessions"
    contracts_dir: str = "./contracts"

    # ── Phase S2: ModelHub (SIM-D-21) ──────────────────────────
    model_hub: Dict[str, Any] = field(default_factory=dict)
    #   Keys: default_model, fallback_model, daily_budget_usd (default $5),
    #         rate_limit_rpm, provider_configs (per-provider API keys + endpoints),
    #         circuit_breaker (failure_threshold, reset_timeout_ms),
    #         cache_enabled, cache_ttl_s

    # ── Phase S3/P3: Fabric ────────────────────────────────────
    fabric: Dict[str, Any] = field(default_factory=dict)
    #   Keys: contracts_dir, capability_scan_dirs, production_mode,
    #         execution_timeout_s (default 30), max_batch_size (default 10)

    # ── Phase S4: Bridge ───────────────────────────────────────
    bridge: Dict[str, Any] = field(default_factory=dict)
    #   Keys: host, port, timeout_s, retry_max, retry_delay_s,
    #         sse_reconnect_s, command_timeout_s, query_timeout_s

    # ── Phase S5: Orchestrator ─────────────────────────────────
    orchestrator: Dict[str, Any] = field(default_factory=dict)
    #   Keys: mailbox_capacity (default 100), workflow_db_path,
    #         cb_planner_failure_threshold (default 5),
    #         cb_planner_reset_timeout_ms (default 30000),
    #         dag_max_concurrent_steps (default 5),
    #         dag_step_timeout_s (default 60),
    #         admin_enabled (default False for tests), admin_port (default 8081),
    #         scheduler_tick_s (default 1.0)

    # ── Phase S6: Planner ──────────────────────────────────────
    planner: Dict[str, Any] = field(default_factory=dict)
    #   Keys: mailbox_max_depth (default 5), pipeline_timeout_s (default 120),
    #         sketch_model, expand_model, validate_model,
    #         hil_timeout_s (default 300), max_retries (default 2)

    # ── Phase P2: SessionState ─────────────────────────────────
    checkpoint_s: int = 300  # checkpoint interval
    session_storage_backend: str = "sqlite"  # V1: sqlite only

    # ── Phase P4: Concierge ────────────────────────────────────
    concierge: Dict[str, Any] = field(default_factory=dict)
    #   Keys: front_model, back_model, classification_model,
    #         delta_batch_window_ms (default 500),
    #         front_lock_timeout_s (default 30),
    #         weave_batch_size (default 5),
    #         max_react_iterations (default 10),
    #         affect_tick_s (default 60)

    def session_db_path(self, session_id: str) -> str:
        return f"{self.session_db_base_dir}/{session_id}.db"
```

---

#### 9.9 Error Handling: Phase Failure Recovery

**Principle:** Infrastructure phases (S1–S4) are fatal — if they fail, abort startup. Component phases (S5–S6) can degrade. Session phases (P1–P7) fail only that session.

| Phase | Failure | Recovery |
|---|---|---|
| **S1: Config** | Invalid config | **FATAL.** Raise `KernelConfigError`. Process cannot start. |
| **S2: ModelHub** | Plugin init fails | **DEGRADED.** Log warning. ModelHub works with remaining plugins. If ALL fail → FATAL. |
| **S3: Shared Fabric** | Registry scan fails | **DEGRADED.** Log warning. Empty capability registry. Orchestrator can't dispatch. |
| **S4: Bridge** | K0 unreachable | **OFFLINE.** `bridge_client = None`. All adapters fall back to offline stubs (SIM-D-33). Normal operation. |
| **S5: Orchestrator** | Factory fails | **FATAL.** Orchestrator is mandatory. Cannot route MED/HIGH tasks. |
| **S6: Planner** | Factory fails | **DEGRADED.** CB_PLANNER opens permanently. HIGH → MED tier degradation. Log warning. |
| **S6b: Cross-wire** | Planner has no mailbox | **DEGRADED.** MockPlannerAdapter remains. HIGH → MED. |
| **P1: Bus** | Bus create fails | **SESSION FATAL.** Cannot create session. Return error to caller. |
| **P2: SSM** | SQLite create fails | **SESSION FATAL.** No state → no session. |
| **P3: Session Fabric** | Fabric create fails | **SESSION FATAL.** No Fabric → no capability execution. |
| **P4: Concierge** | Factory fails | **SESSION FATAL.** No Concierge → no conversation. |
| **P5: Household** | Bridge query fails | **SESSION DEGRADED.** Load from LOCAL COLD. `projection_stale = True`. |
| **P6: SSM start** | Lifecycle fails | **SESSION DEGRADED.** Checkpointing disabled. Data in-memory only. |

**Rollback on session failure:** If any session phase fails, tear down all already-created session components in reverse order:

```python
async def _rollback_session(partial: Dict[str, Any]):
    """Tear down partially-created session components."""
    if "concierge" in partial:
        await partial["concierge"].stop()
    if "session_fabric" in partial:
        await partial["session_fabric"].shutdown()
    if "session_manager" in partial:
        partial["session_manager"].stop()
    if "bus" in partial:
        await partial["bus"].close()
```

---

#### 9.10 Graceful Shutdown Sequence

Two tiers, each in reverse order:

**Session Shutdown** (per session, called on session eviction or process stop):

```
PS1. concierge.stop()           — flush DeltaAggregator, cancel FrontLock, teardown FSM, unsubscribe bus
PS2. concierge_task.cancel()    — cancel background asyncio task
PS3. session_fabric.shutdown()  — drain pending executions
PS4. session_manager.stop()     — final checkpoint, flush events (SIM-D-18)
PS5. bus.close()                — drain subscribers, close ring buffer
PS6. mailbox_router.close()     — drain all mailboxes
PS7. Remove SessionInstance from runtime.sessions
```

**Startup Shutdown** (once, on process stop — AFTER all sessions stopped):

```
SS1. Stop all sessions first    — iterate runtime.sessions, call session_shutdown for each
SS2. orchestrator.shutdown()    — drain active DAGs (30s grace), stop scheduler, stop admin HTTP
SS3. planner.stop()             — drain mailbox, cancel in-flight plan, unsubscribe events
SS4. planner_task.cancel()      — cancel background asyncio task
SS5. model_hub.close()          — close all provider plugins, flush metrics, clear cache
SS6. shared_fabric.shutdown()   — drain pending executions
SS7. bridge_client.close()      — close transport, flush outbox (if not None)
```

**Order matters:** Consumers before infrastructure. Sessions before shared. Matches kernel.md §8 but split across two tiers.

---

#### 9.11 Decision Map: All 37+3 Decisions → Bootstrap Phases

```
Phase S1 (Config):      SIM-D-05 (asyncio model)
Phase S2 (ModelHub):    SIM-D-21 (factory), SIM-D-22 (shared)
Phase S3 (Shared Fab):  SIM-D-34 (NullState), SIM-D-35 (two instances), SIM-D-36 (shared registry),
                        SIM-D-20 (Fabric IS IFabricPort)
Phase S4 (Bridge):      SIM-D-29 (BridgeClient facade), SIM-D-30 (shared), SIM-D-32 (Phase 2.5→S4),
                        SIM-D-33 (None if offline)
Phase S5 (Orchestrator):SIM-D-25 (shared), SIM-D-26 (phased mock→real), SIM-D-06 (port sigs canonical)
Phase S6 (Planner):     SIM-D-25 (shared), SIM-D-28 (LLMGateway→ModelHub), SIM-D-38 (snapshot state) [NEW]
Phase S6b (Cross-wire): SIM-D-26 (hot-swap)
Phase P1 (Bus):         SIM-D-01 (per-session), SIM-D-13 (KernelService creates), SIM-D-14 (ordered),
                        SIM-D-15 (TracingMiddleware), SIM-D-16 (sweep)
Phase P2 (SSM):         SIM-D-18 (KernelService lifecycle), SIM-D-19 (standalone mode), SIM-D-17 (SSM IS IStatePort)
Phase P3 (Session Fab): SIM-D-35 (per-session with real SSM), SIM-D-36 (shared registry)
Phase P4 (Concierge):   SIM-D-02 (KernelService+SessionInstance), SIM-D-09 (ConciergeSession wrapper),
                        SIM-D-10 (26-step factory), SIM-D-11 (test adapters), SIM-D-12 (adapters.py),
                        SIM-D-17 (SSM IS IStatePort), SIM-D-20 (Fabric IS IFabricPort),
                        SIM-D-24 (FabricOrchestratorAdapter), SIM-D-27 (retire POC orch)
Phase P5 (Household):   SIM-D-31 (not SS), SIM-D-33 (None=offline)
Unphased:               SIM-D-03 (per-turn trace ID — runtime, not bootstrap),
                        SIM-D-04 (shared/per-session table — implemented across phases),
                        SIM-D-07 (internal ports untouched), SIM-D-08 (type bridging — adapter code),
                        SIM-D-23 (FabricGatewayAdapter translator — adapter code),
                        SIM-D-37 (MW ChatAdapter — MW bootstrap, separate from kernel)
```

---

#### 9.12 Orchestrator State Read: Session-Resolved Dispatch

**Why Orchestrator is clean but needs attention:**

Orchestrator's `StateReadAdapter.read_section(session_id, section)` takes `session_id` per-call. The Orchestrator extracts `session_id` from `TaskEnvelope.context["session_id"]` at every call site. This is correct.

But `StateReadAdapter` wraps an `ISessionStateReader` bound to ONE SSM. In the shared Fabric (NullState) case, it wraps `NullSessionStateReaderAdapter` which returns empty/default for any session_id.

**In Tier 1 (startup):** Orchestrator gets `StateReadAdapter(null_state_reader)`. State reads return empty → safety band check returns None → proceeds (degraded). This is acceptable for V1 because:

- Orchestrator state reads are optional (snapshot for DAG planning context)
- Safety band check degrades to "proceed anyway" on read failure
- Session context flows through TaskEnvelope, not through SSM reads

**In V2:** Orchestrator could get a `SessionResolvedStateReader(session_registry)` that looks up the correct SSM from the session registry at call time. But V1 NullState is fine.

**SIM-GAP-50 (DAGExecutor `session_id="default"`)** must still be fixed — the hardcoded value means even with a real state reader, it reads the wrong session.

---

#### 9.13 Planner State Resolution: SIM-D-38

The Planner's `SessionStateReadAdapter(reader, session_id)` is session-locked. Three fix options were identified in §9.1. Analysis:

| Option | Approach | Lines Changed | Risk |
|---|---|---|---|
| **A: Refactor IStateReadPort** | Add `session_id` param to every method (match Orchestrator pattern) | ~20 lines + 4 call sites in stages | Medium — changes Planner port contract |
| **B: Per-request adapter swap** | Create `SessionStateReadAdapter` per PlanRequest, inject before pipeline starts | ~15 lines in PlannerAgent._run_loop() | Low — no port contract change, but adapter lifecycle is tricky |
| **C: Read from PlanRequest.context** | Planner reads `SessionSnapshot` from `PlanRequest.context` instead of live state | ~10 lines — SnapshotStateReadAdapter returns snapshot fields | Lowest — snapshot already exists in PlanRequest |

**Decision SIM-D-38: Option C — SnapshotStateReadAdapter.**

Rationale:

- `PlanRequest.context: Optional[SessionSnapshot]` already carries session state
- Orchestrator already populates this snapshot before enqueuing the plan request
- Planner stages already access `request.context` for session info (SketchService L713)
- A `SnapshotStateReadAdapter` returns sections from the cached snapshot (~15 lines)
- No live SSM reads needed — planning uses a point-in-time snapshot, not live state
- Matches the existing Orchestrator pattern: `get_snapshot(session_id)` → `PlanRequest.context`

```python
class SnapshotStateReadAdapter:
    """IStateReadPort that reads from a PlanRequest's snapshot instead of live SSM."""

    def __init__(self):
        self._snapshot: Optional[SessionSnapshot] = None

    def bind(self, snapshot: SessionSnapshot):
        """Called by PlannerAgent before each pipeline run."""
        self._snapshot = snapshot

    async def read_sections(self, sections: List[str], trace_id: str = "") -> SessionSnapshot:
        if self._snapshot is None:
            return SessionSnapshot.empty()
        return self._snapshot.filter(sections)

    async def get_snapshot(self, trace_id: str = "") -> SessionSnapshot:
        return self._snapshot or SessionSnapshot.empty()
```

PlannerAgent calls `state_adapter.bind(request.context)` before each `PipelineController.execute()`.

---

#### 9.14 Gaps Found

| ID | Description | Severity |
|---|---|---|
| **SIM-GAP-49** | Planner's `SessionStateReadAdapter(reader, session_id)` is session-locked at construction. Shared Planner (SIM-D-25) can only read ONE session's state. All plans get one session's cognitive context. | **HIGH** |
| **SIM-GAP-50** | DAGExecutor `read_section(session_id="default", section="control.safety_band")` hardcodes `"default"` session_id. Safety band check always hits wrong session. | **MEDIUM** |
| **SIM-GAP-51** | `NullEventPortAdapter` (for shared Fabric and Orchestrator event port at startup tier) does not exist. ~10 lines no-op. | **LOW** |
| **SIM-GAP-52** | `SnapshotStateReadAdapter` (for Planner) does not exist. ~15 lines wrapping PlanRequest.context. | **MEDIUM** |
| **SIM-GAP-53** | `FabricFactory.create_with_ports()` does not accept external `capability_registry` param — creates its own internally. Must add optional param OR post-inject via `fabric._registry = shared_registry`. | **MEDIUM** |
| **SIM-GAP-54** | kernel.md §7 pseudocode is single-session. Must be updated to reflect two-tier bootstrap (SIM-D-02 + SIM-D-25). Documentation gap. | **LOW** |

---

#### 9.15 Flags Found

| ID | File | Problem | Impact |
|---|---|---|---|
| **SIM-FLAG-25** | `k1/planner/adapters/session_state_adapter.py` L51 | Constructor takes `session_id: str` — permanently binds to one session. Incompatible with shared Planner (SIM-D-25). | Forces SnapshotStateReadAdapter or refactor. |
| **SIM-FLAG-26** | `k1/orchestrator/orchestration/dag_executor.py` L990 | `session_id="default"` hardcoded in safety band read. | Safety band check silently reads wrong session. |

---

#### 9.16 Decisions

| ID | Question | Decision | Rationale |
|---|---|---|---|
| **SIM-D-38** | How does shared Planner read session state? | **SnapshotStateReadAdapter** — reads from `PlanRequest.context` snapshot instead of live SSM. PlannerAgent calls `bind(snapshot)` before each pipeline run. | PlanRequest already carries SessionSnapshot. Planning uses point-in-time data. No live reads needed. ~15 lines. Zero port contract changes. |
| **SIM-D-39** | Two-tier or single-tier bootstrap? | **Two-tier: Startup (shared, once) + Session (per-session, on demand).** kernel.md §7 restructured. | SIM-D-01 (per-session bus), SIM-D-02 (session registry), SIM-D-25 (shared Orch+Planner) require structural split. Single-session pseudocode is a simplification. |
| **SIM-D-40** | What happens when a startup-tier component fails? | **ModelHub/Fabric: degraded. Bridge: offline. Orchestrator: fatal. Planner: degraded (HIGH→MED).** Session-tier failures are per-session only. | Edge-first principle: degrade don't crash. Only Orchestrator is truly mandatory (routes all MED/HIGH work). |

---

#### 9.17 Step 9 Verdict

**The bootstrap works — with 3 structural changes from kernel.md's original design:**

1. **Two-tier split (SIM-D-39).** kernel.md §7 assumed single-session. Reality: shared components at startup + per-session components on demand. 7 startup phases + 7 session phases.

2. **Planner state adapter replacement (SIM-D-38, SIM-GAP-49).** Planner's `SessionStateReadAdapter` is session-locked, incompatible with shared Planner. Fix: `SnapshotStateReadAdapter` reads from `PlanRequest.context`. ~15 lines.

3. **DAGExecutor session_id fix (SIM-GAP-50).** Hardcoded `"default"` → extract from task envelope. ~1 line.

**No circular dependencies.** Dependency graph is a clean DAG in both tiers. The Orchestrator↔Planner cycle is broken by Phase S5/S6/S6b (mock→create→hot-swap).

**Orchestrator is session-safe.** Its `StateReadAdapter` takes `session_id` per-call. No V1 issue. V2 could add `SessionResolvedStateReader` for live reads instead of NullState.

**New adapters needed (4 total, ~50 lines):**

- `NullEventPortAdapter` (~10 lines) — SIM-GAP-51
- `SnapshotStateReadAdapter` (~15 lines) — SIM-GAP-52
- `NullSessionStateReaderAdapter` (~10 lines) — SIM-GAP-47 (from Step 8.5)
- `NullDeltaBusAdapter` (~10 lines) — SIM-GAP-47 (from Step 8.5)

*Plus* the adapters from prior steps (SIM-GAP-20, 21, 33, 36, 37, 38, 39, 45, 46) totaling ~400 lines.

**Running totals after Step 9: 54 gaps, 26 flags, 40 decisions.**

**Next: Step 10 — Integration Smoke Test**

---

**Next: Step 10 — Integration Smoke Test**

---

### STEP 10 — Integration Smoke Test

**Question:** Can we send a message through the full stack? WebSocket → IInputPort → FSM → Classification → Dispatch → Fabric/Orchestrator → LLM → IOutputPort → SSE. What's the happy-path call chain?

**What we read:**

- Full wired kernel from Step 9
- `k1/concierge/fsm/controller.py` — event routing (11 states, 3600+ lines)
- `k1/concierge/fsm/states.py` — 11 FSM states
- `k1/concierge/fsm/phase1.py` — StubPhase1Pipeline / UltraBERTPhase1Pipeline
- `k1/concierge/fsm/arbiter.py` — ConversationArbiter
- `k1/concierge/actors/front.py` — Front actor (ReAct loop, prompt building, tool dispatch)
- `k1/concierge/actors/back.py` — Back actor (capability execution, result submission)
- `k1/concierge/react/loop.py` — ReAct loop core
- `k1/concierge/tools/implementations.py` — Tool implementations (dispatch_task, invoke_capability, submit_result, etc.)
- `k1/concierge/tools/dispatcher.py` — ToolDispatcher 7-step pipeline
- `k1/bus/envelope/envelope.py` — Bus Envelope (16 fields)
- `k1/orchestrator/types.py` — Production TaskEnvelope, PlanRequest
- `k1/concierge/orchestrator/types.py` — POC TaskEnvelope, CapabilityRequest
- `k1/fabric/types.py` — Fabric CapabilityRequest (14 fields)
- `k1/concierge/bus/builders.py` — 43 envelope builder functions

**What we discover:**

1. **Port abstractions (IInputPort, IOutputPort, IClassificationPort) are NOT called in the FSM.** The real mechanisms are bus pub/sub and pipeline objects. The ports exist in spec only.
2. **Production TaskEnvelope is missing `session_id` (SIM-GAP-55, HIGH).** Session context lost at Concierge→Orchestrator handoff.
3. **THREE different tool call budget tables exist — conflicting numbers (SIM-GAP-56).**
4. **Same-turn completion suppression** means LOW-tier tasks may not deliver results immediately.
5. **7 type mismatches** between POC and production types across components.

---

#### 10.1 The 11 FSM States

| # | State | Entry Trigger | Active Actor |
|---|---|---|---|
| 1 | `LISTENING` | `response.final` or session start | None (idle) |
| 2 | `DISPATCHING` | `user.input` + Phase 1 complete | Front LLM |
| 3 | `COMPANIONING` | ack emitted + task dispatched | Front (idle) |
| 4 | `PROGRESSING` | `tool.started` received | Back LLM |
| 5 | `DELIVERING` | `task.complete` received | Front LLM |
| 6 | `CLARIFYING_USER` | uncertainty ≥ threshold | Front LLM |
| 7 | `CLARIFYING_WORKER` | `task.suspended` received | Front LLM |
| 8 | `CANCELLING` | `task.cancel` emitted by Front | Controller |
| 9 | `INTERRUPT_HANDLING` | `user.input` during COMPANIONING/PROGRESSING | Front LLM |
| 10 | `PROACTIVE_WAKE` | `task.complete` while LISTENING | Controller |
| 11 | `WEAVING` | `pending_results` non-empty after final | Front LLM |

---

#### 10.2 LOW Tier: Complete Call Chain — "What's the weather?"

**Entry: User message arrives on bus**

```
WebSocket transport adapter
  → bus.publish(Envelope(topic="k1.session.user.input.v1",
                         payload={"text": "What's the weather?"},
                         session_id=sid, cognitive_trace_id=ctid))
```

> **Critical finding:** `IInputPort.receive()` is **never called**. The FSM subscribes to `TOPIC_USER_INPUT` via `bus.subscribe()`. The transport adapter publishes directly to the bus. The `IInputPort` Protocol exists in concierge.md spec but is unused.

**Step 1: FSM `_on_user_input()` — LISTENING → DISPATCHING**

```
controller.py L1091
  → IdempotencyLedger.check_and_mark(envelope_id)
  → _guard_dispatch(envelope) → GuardAction.TRANSITION
  → turn_number += 1
  → _write_history("user", text="What's the weather?")
  → FSM transition: LISTENING → DISPATCHING [≤1ms — no I/O]
  → emit turn.started envelope
  → _run_phase1_with_arbiter(envelope, text)
```

**Step 2: Phase 1 Classification — `_run_phase1_with_arbiter()`**

```
controller.py L1820
  → TurnLock.acquire("phase1")
  → StubPhase1Pipeline.classify(text)              [≤22ms target]
      → returns Phase1Result(tier=LOW, intent=weather, safety=GREEN,
                             domain=weather, entities=[...], emotions=[...])
  → _write_phase1_to_ss():
      → SS.scoreboard: intents, entities, salience_map
      → SS.affective_now: primary_emotion, confidence, valence, arousal
      → SS.control: intent_classification, domain_context, safety_band, complexity_tier
  → ConversationArbiter.classify(text, phase1, inflight=[])
      → returns ArbiterResult(action=PARALLEL_NEW)   [LISTENING: always PARALLEL_NEW]
  → TurnLock.release()
  → emit intent.arbitrated envelope
  → _enrich_envelope_with_arbiter(arbiter_decision, routing_metadata, tier, safety_band)
  → FrontLock.try_deliver(enriched) → True
  → _deliver_to_front(enriched) → router.deliver(ACTOR_FRONT, enriched)
```

> **Critical finding:** `IClassificationPort.classify()` is **never called**. Phase 1 uses `StubPhase1Pipeline.classify()` directly — a pipeline object, not a port. The `IClassificationPort` Protocol exists in spec but is unused. Production would use `UltraBERTPhase1Pipeline` — also a pipeline, not via the port.

**Step 3: Front Actor — STANDARD mode (acknowledge + dispatch)**

```
front.py L663
  → determine_mode(fsm_state="DISPATCHING", topic="user.input") → PromptMode.STANDARD
  → compute_affect_band(affect_dict) → affect context
  → build_chat_history(history_active, window=N) → messages
  → DynamicPromptBuilder().build(mode=STANDARD, ...) → PromptContext
  → react_loop(tools=[10 Front tools], max_iterations=6):

    Iteration 0 (tool_choice="required"):
      → model.execute(request)                       [LLM call: ≤30s timeout]
      → LLM returns tool_call: recall_memory({query: "weather preferences"})
      → ToolDispatcher.dispatch("recall_memory") → execute → MemoryResult

    Iteration 1:
      → LLM returns tool_call: dispatch_task({tier: "LOW", intents: [{action: "check weather"}]})
      → ToolDispatcher.dispatch("dispatch_task") → builds TaskDispatch
      → returns ToolResult(data={"queued": True, "task_id": "task-xxx"})

    Iteration 2 (L1 termination):
      → LLM returns text: "Let me check the weather for you."
      → No tool calls → loop terminates

  → Post-loop:
      → Emit build_task_dispatch(task_id, tier=LOW, intents=[...])  → bus
      → Emit build_final_response(text="Let me check...")           → bus
```

**Step 4: FSM `_on_task_dispatch()` — DISPATCHING → COMPANIONING**

```
controller.py L2032
  → _task_dispatch_from_payload() → TaskDispatch(task_id, tier=LOW, intents=[...])
  → _active_task_ids.add(task_id)
  → _cancel_handler.register_task(task_id)
  → FSM transition: DISPATCHING → COMPANIONING
  → _route_via_orchestrator(envelope, dispatch):
      → route_task_sync(dispatch, LOW) → DispatchRecord(tier=LOW, envelope=None)
      → LOW: _deliver_to_back(canonical_env) → router.deliver(ACTOR_BACK, env)
```

> **Note:** LOW tier goes to Back **directly**. No Orchestrator involvement. `IDispatchPort.dispatch_direct()` is NOT called for LOW. Instead, Back's `invoke_capability` tool calls `ctx.fabric_port.execute()` (IFabricPort) directly.

**Step 5: Back Actor — Execute capability**

```
back.py L430
  → _read_ss_snapshot(ss) → beliefs, scoreboard, control, history, persona
  → build_back_prompt(task, beliefs, referents) → system prompt
  → _filter_back_tools("LOW") → [recall_memory, discover_capabilities, invoke_capability, submit_result]
  → react_loop(tools=4, max_iterations=4):

    Iteration 0:
      → LLM returns tool_call: discover_capabilities({intent: "check weather"})
      → ctx.fabric_port.discover_capabilities({...}) → [weather_lookup: 0.95]

    Iteration 1:
      → LLM returns tool_call: invoke_capability({name: "weather_lookup", params: {location: "..."}})
      → ctx.fabric_port.execute(CapabilityRequest(...)) → CapabilityResult(data={temp: "72°F"})

    Iteration 2:
      → LLM returns tool_call: submit_result({result_type: "complete", final_answer: "72°F and sunny"})
      → L2 termination: react_loop detects submit_result → terminates

  → _emit_back_result() → build_task_complete({task_id, final_answer, results})  → bus
```

**Step 6: FSM `_on_task_complete()` — COMPANIONING → DELIVERING**

```
controller.py L2277
  → Topic guard + idempotency check
  → Cancel dedup: not cancelled
  → Same-turn check: ⚠️ if dispatch_turn == current_turn → DEFERRED (see §10.5)
  → Otherwise: COMPANIONING → DELIVERING on TOPIC_TASK_COMPLETE
  → FrontLock.try_deliver(envelope) → True
  → _deliver_to_front(task_complete_envelope)
```

**Step 7: Front Actor — PRESENT mode (deliver result)**

```
front.py L663
  → determine_mode(fsm_state="DELIVERING", topic="task.complete") → PromptMode.PRESENT
  → Extract task_result_summary, artifacts from payload
  → react_loop(max_iterations=3):

    Iteration 0 (L1 termination):
      → LLM returns text: "It's currently 72°F and sunny in your area."
      → No tool calls → loop terminates

  → Emit build_final_response(text="It's currently 72°F and sunny...") → bus
```

**Step 8: FSM `_on_response_final()` — DELIVERING → LISTENING**

```
controller.py L3255
  → decide_response_final(DELIVERING, has_pending=False, has_active=False)
      → ResponseFinalAction.TRANSITION_AND_FINALIZE
  → _write_history("assistant_response", text="It's currently 72°F and sunny...")
  → _history_sink.add_turn(user_message, assistant_response) → SS.history_active
  → WeaveBatcher.front_busy = False
  → FSM transition: DELIVERING → LISTENING
  → FrontLock.release()
  → _finalize_turn(envelope) → emit turn.completed
```

> **Critical finding:** `IOutputPort.send()` is **never called**. Front emits `build_final_response()` on the bus. An SSE relay consumer (not yet built) must subscribe to `TOPIC_FINAL_RESPONSE` and relay to the actual SSE/WebSocket transport.

**Step 9: SSE delivery (not yet wired)**

```
SSE relay consumer (to be built)
  → subscribes to TOPIC_FINAL_RESPONSE on bus
  → extracts text from payload
  → SSEOutputAdapter.send(OutputEvent(text="It's currently 72°F and sunny..."))
  → Client receives SSE event
```

---

#### 10.3 FSM State Transition Summary

```
LOW:     LISTENING → DISPATCHING → COMPANIONING → DELIVERING → LISTENING
MEDIUM:  LISTENING → DISPATCHING → COMPANIONING → DELIVERING → LISTENING
HIGH:    LISTENING → DISPATCHING → COMPANIONING → DELIVERING → LISTENING

All three follow the same FSM path. The difference is HOW tasks are dispatched:
  LOW:    Back directly → ctx.fabric_port.execute()
  MEDIUM: OrchestratorStub → Fabric (sequential capabilities)
  HIGH:   PassthroughPlannerStub → downgrades to MEDIUM → same as MEDIUM
```

---

#### 10.4 MEDIUM Tier Delta from LOW

| Aspect | LOW | MEDIUM |
|---|---|---|
| Task routing | `_deliver_to_back()` directly | `_run_medium_orchestration()` → OrchestratorStub |
| Who calls Fabric | Back `invoke_capability` tool | OrchestratorStub → Fabric sequential |
| Result source | `TOPIC_TASK_COMPLETE` from Back | `TOPIC_DAG_COMPLETED` → normalized → `TOPIC_TASK_COMPLETE` |
| Budget | 1 Fabric call, 500 tokens | 2 Fabric calls, 2K tokens |
| Back involvement | YES (full ReAct loop) | NO (Orchestrator handles) |
| LLM calls | Front×2 + Back×3 | Front×2 + 0 (Orchestrator is deterministic) |

**For production:** MEDIUM should use `FabricOrchestratorAdapter.dispatch_envelope()` (SIM-D-24) instead of OrchestratorStub. The result flows back via `k1.orchestration.dag.completed.v1` bus topic → `_on_dag_completed()` → normalized → `_on_task_complete()`.

---

#### 10.5 HIGH Tier Delta from MEDIUM

| Aspect | MEDIUM | HIGH (current POC) | HIGH (production target) |
|---|---|---|---|
| Planner | None | PassthroughPlannerStub (1-step plan) | Real Planner (4-stage pipeline) |
| DAG execution | Sequential (≤2 Fabric calls) | Same as MEDIUM (downgraded) | Multi-wave DAG (≤10 Fabric calls) |
| Budget | 2 Fabric / 2K tokens | 10 Fabric / 3.5K planner tokens | 10 Fabric / 8K tokens |
| HIL | None | None | Yes (clarification + approval) |

**For production:** Remove `PassthroughPlannerStub` (SIM-GAP-27). Route HIGH through real Orchestrator → Planner → DAG → Fabric chain.

---

#### 10.6 Critical Finding: Ports vs. Reality

The Step 9 bootstrap wires 8 external ports per concierge.md spec. But the FSM **does not call 3 of them**:

| Port | Step 9 Wires | FSM Calls | Actual Mechanism |
|---|---|---|---|
| `IInputPort` | WebSocketInputAdapter | **NO** | Bus `TOPIC_USER_INPUT` subscription |
| `IOutputPort` | SSEOutputAdapter | **NO** | Bus `build_final_response()` → topic |
| `IClassificationPort` | UltraBERTv4Adapter | **NO** | StubPhase1Pipeline.classify() directly |
| `ILLMPort` | ModelGatewayAdapter | **YES** | model.execute() in ReAct loop |
| `IStatePort` | SessionManager (SIM-D-17) | **YES** | ss.* section reads/writes throughout |
| `IDispatchPort` | FabricOrchestratorAdapter | **Partial** | MED/HIGH only; LOW bypasses |
| `IDeltaPort` | ConciergeDeltaBusAdapter | **YES** | DeltaAggregator subscribe/publish |
| `IMemoryPort` | BridgeRecallAdapter | **YES** | recall_memory tool → port.recall() |

**SIM-GAP-57 (HIGH): IInputPort, IOutputPort, IClassificationPort are spec-only — never called by FSM code.** The transport layer publishes/subscribes bus topics directly. Phase1Pipeline is a pipeline object, not a port call.

**Decision needed:** Either:

- **A: Accept bus-based I/O.** Keep IInputPort/IOutputPort as future hooks. Transport adapters publish to bus, SSE relay subscribes. Phase1Pipeline stays as-is. Ports exist for testing only.
- **B: Wire ports into FSM.** Refactor `_on_user_input()` to call `IInputPort.receive()`, add SSE relay calling `IOutputPort.send()`, refactor Phase 1 to call `IClassificationPort.classify()`. Significant FSM rewrite.

---

#### 10.7 Envelope Compatibility Matrix

Across the full stack, different components use different envelope types:

| Type | Module | `session_id` | `cognitive_trace_id` | `capabilities` | `budget` |
|---|---|---|---|---|---|
| Bus `Envelope` | `k1.bus.envelope` | ✅ str | ✅ str | ❌ | ❌ |
| POC `TaskEnvelope` | `k1.concierge.orchestrator.types` | ✅ str | via `trace_id` | ❌ | ✅ Budget |
| Prod `TaskEnvelope` | `k1.orchestrator.types` | **❌ MISSING** | via `trace_id` | ✅ List[str] | ❌ (timeout_ms only) |
| POC `PlanRequest` | `k1.concierge.orchestrator.types` | **❌ MISSING** | via `trace_id` | ❌ | ✅ Budget |
| Prod `PlanRequest` | `k1.orchestrator.types` | **❌ MISSING** | via `trace_id` | ❌ | ❌ (timeout_ms) |
| POC `CapabilityRequest` | `k1.concierge.orchestrator.types` | ✅ str | ✅ trace_id | ❌ (single `name`) | ❌ |
| Prod `CapabilityRequest` | `k1.fabric.types` | ✅ str | ✅ trace_id | ❌ (`capability_name`) | ❌ (timeout_ms) |

**SIM-GAP-55 (HIGH): Production `TaskEnvelope` has NO `session_id` field.** Orchestrator extracts it from `TaskEnvelope.context["session_id"]` (checked in Step 9), but `context` is `Dict[str, Any]` — no type safety, no validation, no guarantee the caller sets it.

**SIM-GAP-58 (MEDIUM): POC `CapabilityRequest.name` vs Prod `CapabilityRequest.capability_name` — different field names for the same concept.** Already tracked as SIM-GAP-06 but now confirmed with exact field names. The `FabricOrchestratorAdapter` must translate.

---

#### 10.8 Type Mismatch Summary

| # | Mismatch | Severity | Bridge Required |
|---|---|---|---|
| 1 | Prod `TaskEnvelope` missing `session_id` | HIGH | `FabricOrchestratorAdapter` must inject `session_id` into `context` dict |
| 2 | Prod `PlanRequest` missing `session_id` | HIGH | Orchestrator must copy `session_id` from `TaskEnvelope.context` to `PlanRequest.context` |
| 3 | POC `CapReq.name` vs Prod `CapReq.capability_name` | MEDIUM | `FabricOrchestratorAdapter.dispatch_direct()` translates field names |
| 4 | POC `CapReq` has 4 fields vs Prod 14 fields | MEDIUM | Adapter fills defaults for missing fields (`wfq_priority`, `safety_band`, `timeout_ms`, etc.) |
| 5 | Prod `TaskEnvelope.envelope_id` is `str` vs Bus `Envelope.envelope_id` is `int` | LOW | Different namespaces, no confusion if not compared |
| 6 | Prod `TaskEnvelope` requires `capabilities` list for MEDIUM | MEDIUM | `FabricOrchestratorAdapter` must extract capability names from intents |
| 7 | `Budget` dataclass is POC-only | LOW | Production uses `timeout_ms` directly; adapter translates |

---

#### 10.9 Latency Budget: End-to-End

**LOW tier "What's the weather?" — system-owned time:**

| Hop | What | Target P99 | Notes |
|---|---|---|---|
| H0 | WebSocket → Bus publish | ≤5ms | Transport adapter overhead |
| H1 | Bus deliver → `_on_user_input()` | ≤1ms | Synchronous handler dispatch |
| H2 | Phase 1 classification | ≤22ms | UltraBERT (25ms P99), stub is <1ms |
| H3 | Phase 1 SS writes (3 sections) | ≤0.5ms | SQLite + in-memory |
| H4 | Arbiter classify | ≤0.5ms | Deterministic rules |
| H5 | FSM transition LISTENING→DISPATCHING | ≤1ms | No I/O |
| H6 | FrontLock + deliver to Front | ≤1ms | Queue enqueue |
| H7 | Front prompt build | ≤5ms | DynamicPromptBuilder + history fetch |
| **H8** | **Front LLM call #1 (recall_memory)** | **≤30s** | **LLM-owned. Usually 1-3s.** |
| H9 | recall_memory tool execution | ≤50ms | IMemoryPort.recall() or in-memory |
| **H10** | **Front LLM call #2 (dispatch_task)** | **≤30s** | **LLM-owned. Usually 1-3s.** |
| H11 | dispatch_task tool execution | ≤1ms | Build TaskDispatch, return queued |
| **H12** | **Front LLM call #3 (text response)** | **≤30s** | **LLM-owned. Usually 0.5-2s.** |
| H13 | FSM DISPATCHING→COMPANIONING | ≤1ms | |
| H14 | Route to Back (LOW: direct) | ≤1ms | router.deliver() |
| H15 | Back prompt build + SS snapshot | ≤5ms | |
| **H16** | **Back LLM call #1 (discover_capabilities)** | **≤30s** | **LLM-owned.** |
| H17 | discover_capabilities execution | ≤50ms | Fabric registry scan |
| **H18** | **Back LLM call #2 (invoke_capability)** | **≤30s** | **LLM-owned.** |
| H19 | Fabric.execute(weather_lookup) | ≤300ms | INTERACTIVE WFQ priority |
| **H20** | **Back LLM call #3 (submit_result)** | **≤30s** | **LLM-owned.** |
| H21 | Bus deliver task.complete → FSM | ≤1ms | |
| H22 | FSM COMPANIONING→DELIVERING | ≤1ms | |
| H23 | Deliver to Front (PRESENT mode) | ≤1ms | |
| **H24** | **Front LLM call (present result)** | **≤30s** | **LLM-owned.** |
| H25 | Bus deliver response.final → FSM | ≤1ms | |
| H26 | FSM DELIVERING→LISTENING + finalize | ≤1ms | |
| H27 | SSE relay → client | ≤5ms | |
| | | | |
| **TOTAL system-owned** | | **~100ms** | Excluding LLM + Fabric tool |
| **TOTAL LLM-owned** | 7 LLM calls | **~7-21s typical** | 1-3s each |
| **TOTAL Fabric-owned** | 1 Fabric call | **~300ms** | Weather API |
| **E2E typical** | | **~8-22s** | LOW budget: 2s is aspirational |

> **SIM-GAP-59 (MEDIUM): LOW tier latency budget is 2s, but a typical turn makes 7 LLM calls (Front: 3, Back: 3, Front PRESENT: 1).** Even at 1s per LLM call, that's 7s minimum. The 2s budget is only achievable with streaming (first token in <2s) or if Front skips recall_memory and combines dispatch + ack into one tool call.

---

#### 10.10 Tool Budget Discrepancy

Three sources give different tool call limits:

| Source | LOW | MEDIUM | HIGH |
|---|---|---|---|
| `tools/dispatcher.py` BUDGET_LIMITS | 5 | 10 | 20 |
| `obs/actor_metrics.py` TIER_BUDGET_LIMITS | 4 | 8 | 12 |
| concierge.md §2.3 canonical | 6 | 12 | 20 |

**SIM-GAP-56 (MEDIUM): Three conflicting budget tables.** Must consolidate to one canonical source. `dispatcher.py` enforces at runtime — that's the one that matters.

---

#### 10.11 Gaps Found

| ID | Description | Severity |
|---|---|---|
| **SIM-GAP-55** | Production `TaskEnvelope` (`k1.orchestrator.types`) has NO `session_id` field. Orchestrator reads it from `context["session_id"]` — untyped, no validation. | **HIGH** |
| **SIM-GAP-56** | Three conflicting tool call budget tables: dispatcher.py (5/10/20), obs metrics (4/8/12), concierge.md (6/12/20). | **MEDIUM** |
| **SIM-GAP-57** | `IInputPort`, `IOutputPort`, `IClassificationPort` are never called by FSM code. Transport uses bus pub/sub. Phase1Pipeline is a pipeline object, not a port call. Spec-only abstractions. | **HIGH** |
| **SIM-GAP-58** | POC `CapabilityRequest.name` vs Prod `CapabilityRequest.capability_name` — different field names for same concept. Adapter must translate. (Confirms SIM-GAP-06 with exact fields.) | **MEDIUM** |
| **SIM-GAP-59** | LOW tier latency budget (2s) incompatible with 7 LLM calls per turn. Minimum ~7s even at 1s/call. Budget only achievable with streaming first-token. | **MEDIUM** |
| **SIM-GAP-60** | SSE relay consumer (bus `TOPIC_FINAL_RESPONSE` → SSEOutputAdapter) does not exist. Needed to bridge bus-based output to actual SSE transport. ~30 lines. | **MEDIUM** |
| **SIM-GAP-61** | Input relay adapter (WebSocket → bus `TOPIC_USER_INPUT`) does not exist as a formal adapter. Transport must publish Envelope directly. ~20 lines. | **MEDIUM** |

---

#### 10.12 Flags Found

| ID | File | Problem | Impact |
|---|---|---|---|
| **SIM-FLAG-27** | `k1/concierge/fsm/controller.py` L2277 | Same-turn completion suppression: if Back completes in same turn as dispatch, result is deferred to proactive delivery (2s timer). | Smoke test may not see immediate result for fast LOW-tier tasks. |
| **SIM-FLAG-28** | `k1/concierge/tools/dispatcher.py` L51 | BUDGET_LIMITS differs from concierge.md §2.3 and obs/actor_metrics.py. Three conflicting budget sources. | Runtime enforcement uses dispatcher.py — others are stale. |
| **SIM-FLAG-29** | `k1/concierge/fsm/controller.py` L2113 | PassthroughPlannerStub inline in controller.py — downgrades HIGH to MEDIUM. Dead code when real Planner wired. | Must remove for production HIGH tier. |

---

#### 10.13 Decisions

| ID | Question | Decision | Rationale |
|---|---|---|---|
| **SIM-D-41** | How to handle 3 unused port abstractions? | **V1: Accept bus-based I/O (Option A).** IInputPort/IOutputPort/IClassificationPort exist for future testing hooks. Transport adapters publish/subscribe bus topics directly. Build SSE relay consumer (~30 lines) and input relay adapter (~20 lines) as bus-to-transport bridges. | Rewiring FSM to call ports (Option B) is a major rewrite. Bus-based I/O works and is consistent with the existing 3600+ line FSM implementation. |
| **SIM-D-42** | Which tool budget table is canonical? | **`dispatcher.py` BUDGET_LIMITS is canonical** (runtime enforcement). Update concierge.md §2.3 and obs/actor_metrics.py to match. | dispatcher.py is the enforcer — it actually rejects tool calls over budget. Others are documentation/observability. |
| **SIM-D-43** | How to handle LOW tier 2s latency target with 7 LLM calls? | **Measure first-token latency, not total.** The 2s budget applies to user-perceived responsiveness (streaming ack), not total turn time. Ack arrives in <2s (Front iteration 0). Full result arrives in 8-22s. | Edge-first UX: acknowledge immediately, deliver results as they complete. Streaming makes 2s achievable for first visible response. |

---

#### 10.14 End-to-End Sequence Diagram

```
User        Transport    Bus        FSM           Phase1     Front      Back       Fabric      LLM
 │            │           │          │              │          │          │          │           │
 ├─message──→│            │          │              │          │          │          │           │
 │            ├─publish──→│          │              │          │          │          │           │
 │            │  user.input│         │              │          │          │          │           │
 │            │           ├─deliver→│              │          │          │          │           │
 │            │           │  [LISTENING→DISPATCHING]│          │          │          │           │
 │            │           │          ├─classify()──→│          │          │          │           │
 │            │           │          │←─Phase1Result│          │          │          │           │
 │            │           │          ├─write SS─────┤          │          │          │           │
 │            │           │          ├─deliver──────┤→────────→│          │          │           │
 │            │           │          │              │          │          │          │           │
 │            │           │          │              │  recall_memory      │          │           │
 │            │           │          │              │          ├──────────┤──────────┤──execute→│
 │            │           │          │              │          │←─result──┤──────────┤←─────────│
 │            │           │          │              │  dispatch_task      │          │           │
 │            │           │          │              │          ├─build────┤          │           │
 │            │           │          │              │  text: "Let me check..."      │           │
 │            │           │          │              │          ├──────────┤──────────┤──execute→│
 │            │           │          │              │          │←─text────┤──────────┤←─────────│
 │            │           │          │              │          │          │          │           │
 │            │           │          │              │          ├─publish task.dispatch→│         │
 │            │           ├←────────┤──────────────┤──────────┤          │          │           │
 │            │           │  [DISPATCHING→COMPANIONING]       │          │          │           │
 │            │           ├─deliver─┤──────────────┤──────────┤─────────→│          │           │
 │            │           │          │              │          │  discover_capabilities          │
 │            │           │          │              │          │          ├──────────┤──execute→│
 │            │           │          │              │          │          │←─caps────┤←─────────│
 │            │           │          │              │          │  invoke_capability   │          │
 │            │           │          │              │          │          ├─execute──→│          │
 │            │           │          │              │          │          │←─result──┤          │
 │            │           │          │              │          │  submit_result       │          │
 │            │           │          │              │          │          ├──────────┤──execute→│
 │            │           │          │              │          │          │←─text────┤←─────────│
 │            │           │          │              │          │          │          │           │
 │            │           │          │              │          │          ├─publish task.complete│
 │            │           ├←────────┤──────────────┤──────────┤──────────┤          │           │
 │            │           │  [COMPANIONING→DELIVERING]        │          │          │           │
 │            │           ├─deliver─┤──────────────┤──────────→│ (PRESENT mode)     │           │
 │            │           │          │              │          ├──────────┤──────────┤──execute→│
 │            │           │          │              │          │←─text────┤──────────┤←─────────│
 │            │           │          │              │          │          │          │           │
 │            │           │          │              │          ├─publish response.final          │
 │            │           ├←────────┤──────────────┤──────────┤          │          │           │
 │            │           │  [DELIVERING→LISTENING]  │         │          │          │           │
 │            ├←─relay───┤          │              │          │          │          │           │
 │←──SSE─────│            │          │              │          │          │          │           │
```

---

#### 10.15 Minimal "Hello World" Test

To verify the full stack boots and processes one message, a test needs:

```python
async def test_hello_world_turn():
    """Minimal smoke test: boot kernel, send message, verify response."""

    # Tier 1: Startup (shared components)
    config = KernelConfig.test_defaults()  # SQLite in-memory, test stubs, no bridge
    runtime = await startup(config)

    # Tier 2: Create session
    session = await create_session(runtime, session_id="test-session-1")

    # Inject a user message via bus
    session.bus.publish(Envelope(
        topic="k1.session.user.input.v1",
        payload=json.dumps({"text": "Hello"}).encode(),
        session_id="test-session-1",
        cognitive_trace_id="trace-001",
    ))

    # Wait for response.final on bus
    response = await wait_for_topic(session.bus, "k1.response.final.v1", timeout=30.0)
    assert response is not None
    payload = json.loads(response.payload)
    assert "text" in payload
    assert len(payload["text"]) > 0

    # Verify FSM back in LISTENING
    assert session.concierge.fsm_state == "LISTENING"

    # Verify SS was written
    control = session.session_manager.read_section("test-session-1", "control")
    assert control is not None
    assert "intent_classification" in control

    # Verify turn completed
    history = session.session_manager.read_section("test-session-1", "history_active")
    assert len(history["turns"]) >= 1

    # Teardown
    await session_shutdown(session)
    await startup_shutdown(runtime)
```

**Prerequisites for this test to pass:**

1. All test adapters wired (TestInputAdapter, TestOutputAdapter, MockClassificationAdapter, TestLLMAdapter, TestBridgeAdapter)
2. TestLLMAdapter must return valid tool calls + text (scripted responses)
3. StubPhase1Pipeline must return LOW tier classification
4. Fabric must have at least one registered capability (or TestFabric returns canned result)
5. Bus must deliver synchronously in test mode (SIM-D-14: unordered for tests)

---

#### 10.16 Step 10 Verdict

**Can we send a message through the full stack? YES — with caveats.**

**The happy path works.** The FSM's 11-state machine, Front/Back dual-actor ReAct loops, bus pub/sub, and capability execution form a complete end-to-end chain. The call sequence is:

```
Transport → Bus → FSM → Phase1 → Front(STANDARD) → [recall + dispatch + ack]
→ FSM → Back → [discover + invoke + submit] → FSM → Front(PRESENT) → [deliver]
→ FSM → Bus → Transport
```

**7 LLM calls per LOW turn, ~100ms system overhead, ~8-22s total.**

**But 4 structural issues must be resolved:**

1. **3 ports are spec-only (SIM-GAP-57).** IInputPort/IOutputPort/IClassificationPort are never called. The real mechanism is bus pub/sub + pipeline objects. Accept as bus-based I/O (SIM-D-41) and build relay adapters.

2. **`session_id` missing from production TaskEnvelope (SIM-GAP-55).** Must flow through `context` dict or add typed field. Orchestrator already reads from `context["session_id"]` — works but untyped.

3. **SSE relay consumer doesn't exist (SIM-GAP-60).** Bus `response.final` → SSE transport bridge needed. ~30 lines.

4. **Same-turn completion suppression (SIM-FLAG-27).** Fast LOW tasks get deferred instead of delivered immediately. By design for UX, but surprising for testing.

**Running totals after Step 10: 61 gaps, 29 flags, 43 decisions.**

---

## SIMULATION COMPLETE

### Final Summary

**10 steps. 61 gaps. 29 flags. 43 decisions.**

| Step | Focus | Gaps | Flags | Decisions | Key Finding |
|---|---|---|---|---|---|
| 1 | Observability + Sessions | 5 | 2 | 5 | Per-session Bus (SIM-D-01), KernelService model (SIM-D-02) |
| 2 | External Port Audit | 4 | 3 | 3 | Port signatures canonical, internal ports untouched |
| 3 | ConciergeFactory | 4 | 2 | 4 | 26-step factory sequence, ConciergeSession wrapper |
| 4 | Bus Wiring | 3 | 2 | 4 | TracingMiddleware stamps all envelopes (SIM-D-15) |
| 5 | SessionState | 3 | 1 | 3 | SSM IS the IStatePort — no wrapper (SIM-D-17) |
| 6 | Fabric + ModelHub | 4 | 3 | 4 | Fabric IS IFabricPort, ModelHub shared (SIM-D-20/21) |
| 7 | Orchestrator + Planner | 8 | 4 | 5 | FabricOrchestratorAdapter replaces POC stack (SIM-D-24) |
| 8 | Bridge | 11 | 4 | 5 | BridgeClient facade, Phase 2.5, None if offline |
| 8.5 | Cross-Component Audit | 5 | 3 | 4 | TWO Fabric instances (SIM-D-35), shared CapabilityRegistry |
| 9 | Bootstrap Assembly | 6 | 2 | 3 | Two-tier bootstrap, Planner snapshot state (SIM-D-38/39) |
| 10 | Integration Smoke Test | 7 | 3 | 3 | 3 ports are spec-only, 7 LLM calls/turn, session_id missing |
| **Total** | | **61** | **29** | **43** | |

### Severity Breakdown

| Severity | Count | Examples |
|---|---|---|
| **HIGH** | 12 | SIM-GAP-05 (Bridge OTel), 24-26 (POC Orch), 33-35 (Bridge ports), 44 (Fabric session), 49 (Planner session), 55 (TaskEnvelope session_id), 57 (3 unused ports) |
| **MEDIUM** | 30 | Type mismatches, missing adapters, budget conflicts, envelope compat |
| **LOW** | 19 | Documentation gaps, minor lifecycle issues, naming collisions |

### Adapter Build Inventory

New adapters discovered across all 10 steps, needed before production wiring:

| Adapter | Lines | Gap | Purpose |
|---|---|---|---|
| `ModelHubGatewayAdapter` | ~30 | SIM-GAP-20/45 | Fabric→ModelHub IModelGatewayPort bridge |
| `BusDeltaAdapter` | ~20 | SIM-GAP-21 | Fabric IDeltaBusPort → Bus bridge |
| `BridgeClient` facade | ~80 | SIM-GAP-33 | CommandPort + QueryPort + SSEPort wrapper |
| `IKernelQueryPort` | ~150 | SIM-GAP-34 | K0 query operations via Bridge |
| `IKernelSSEPort` | ~100 | SIM-GAP-35 | K0 SSE receiver via Bridge |
| `BridgeRecallAdapter` | ~40 | SIM-GAP-36 | Concierge IMemoryPort → Bridge query |
| `HouseholdProjection` | ~60 | SIM-GAP-37 | Frozen household dataclass + hydration |
| `IMemoryPort` Protocol | ~15 | SIM-GAP-38 | Concierge memory port Python file |
| `BridgeCommandAdapter` | ~30 | SIM-GAP-39 | Memory Writer → K0 commands |
| `ModelHubChatAdapter` | ~25 | SIM-GAP-46 | MW chat() → Hub execute() bridge |
| `NullSessionStateReaderAdapter` | ~10 | SIM-GAP-47 | Shared Fabric null state reader |
| `NullDeltaBusAdapter` | ~10 | SIM-GAP-47 | Shared Fabric null delta bus |
| `NullEventPortAdapter` | ~10 | SIM-GAP-51 | Shared Fabric/Orch null event port |
| `SnapshotStateReadAdapter` | ~15 | SIM-GAP-52 | Planner reads from PlanRequest.context |
| `FabricOrchestratorAdapter` | ~60 | SIM-D-24 | Concierge IDispatchPort → Fabric + Orch |
| `SSE relay consumer` | ~30 | SIM-GAP-60 | Bus response.final → SSE transport |
| `Input relay adapter` | ~20 | SIM-GAP-61 | WebSocket → Bus user.input |
| **Total** | **~705** | | |

### Top 5 Architectural Decisions

1. **SIM-D-39: Two-tier bootstrap.** Startup tier (shared: ModelHub, Orch, Planner, Bridge, shared Fabric) + Session tier (per-session: Bus, SSM, session Fabric, Concierge). Fundamental restructuring from kernel.md's single-session model.

2. **SIM-D-35: Two Fabric instances.** Shared Fabric (NullState) for Orchestrator+Planner + per-session Fabric (real SSM) for Concierge. Forced by SessionStateReaderAdapter being bound at construction.

3. **SIM-D-17: SSM IS the IStatePort.** No wrapper. 100+ method calls across 12 section objects work because Concierge calls real SSM methods directly. Same for SIM-D-20 (Fabric IS IFabricPort).

4. **SIM-D-24: FabricOrchestratorAdapter replaces entire POC routing stack.** Retires OrchestratorStub, route_task_sync(), 3 private adapters, POC TaskEnvelope, POC CapabilityRequest.

5. **SIM-D-41: Accept bus-based I/O.** IInputPort/IOutputPort/IClassificationPort are spec-only. Transport adapters work via bus pub/sub. Build relay bridges instead of rewiring FSM.

### Implementation Priority

**P0 (Blocks any production wiring):**

- Fix DAGExecutor hardcoded `session_id="default"` (1 line)
- Build `FabricOrchestratorAdapter` (SIM-D-24, ~60 lines)
- Build `NullSessionStateReaderAdapter` + `NullDeltaBusAdapter` + `NullEventPortAdapter` (~30 lines)
- Build `SnapshotStateReadAdapter` for Planner (SIM-D-38, ~15 lines)
- Retire POC OrchestratorStub + PassthroughPlannerStub

**P1 (Blocks multi-session):**

- Implement two-tier bootstrap (SIM-D-39)
- Build SSE relay consumer + Input relay adapter (~50 lines)
- Add `session_id` to production `TaskEnvelope` or enforce `context["session_id"]` validation

**P2 (Blocks Bridge integration):**

- Build `BridgeClient` facade (~80 lines)
- Build `IKernelQueryPort` (~150 lines) + `IKernelSSEPort` (~100 lines)
- Build Bridge adapters (BridgeRecallAdapter, BridgeCommandAdapter, etc.)

**P3 (Quality / completeness):**

- Consolidate tool budget tables
- Build `ModelHubGatewayAdapter`, `BusDeltaAdapter`, `ModelHubChatAdapter`
- Build `HouseholdProjection` + hydration protocol
- Update kernel.md §7 to reflect two-tier bootstrap

---

## GAP REGISTRY (populated during simulation)

| ID | Step | Description | Severity | Resolution |
|----|------|-------------|----------|------------|
| SIM-GAP-01 | 1 | Builder functions in `bus/builders.py` don't set `session_id`/`cognitive_trace_id` on Envelope headers | MEDIUM | Fix builders to accept + propagate trace context |
| SIM-GAP-02 | 1 | `SessionDelta` lacks `session_id` and `cognitive_trace_id` — delta audit lineage lost | LOW | Add fields to `SessionDelta` dataclass |
| SIM-GAP-03 | 1 | `device_id → member_id` resolution not implemented — device_id stored but no member lookup | MEDIUM | Implement via HouseholdProjection cache (MS-2) |
| SIM-GAP-04 | 1 | Bootstrap creates static trace IDs at boot (`k-front-{uuid}`), not per-turn | MEDIUM | Generate `cognitive_trace_id` per turn at IInputPort |
| SIM-GAP-05 | 1 | Bridge has no OTel span creation — trace chain breaks at K1↔K0 boundary | HIGH | Add span propagation to Bridge transport (MS-2) |
| SIM-GAP-06 | 2 | `CapabilityRequest`/`CapabilityResult` type collision — same names in `k1.fabric.types` vs `k1.concierge.orchestrator.types` | MEDIUM | Factory adapter converts between the two type sets |
| SIM-GAP-07 | 2 | Actors receive `ss: Any` (duck-typed). No Protocol contract for what SS methods actors call. | MEDIUM | **RESOLVED (Step 5):** SSM IS the IStatePort — no wrapper needed. 100+ method calls work because they call real SSM methods directly (SIM-D-17). |
| SIM-GAP-08 | 2 | `ExperienceLayer.__init__()` takes ZERO params. Fully hardcoded. Cannot inject ports. | MEDIUM | Investigate in Step 3 — post-init wiring or minor refactor |
| SIM-GAP-09 | 2 | `ConciergeController.__init__(bus, router)` — everything else late-wired via `Any`-typed attrs | LOW | Factory sets attributes after construction — works but no type safety |
| SIM-GAP-10 | 3 | `ToolContext.cognitive_trace_id` set once at construction (static per session). Should be per-turn (SIM-D-03). Consumer loop must update before each turn. | MEDIUM | Override `ctx.cognitive_trace_id` at start of each turn in consumer loop |
| SIM-GAP-11 | 3 | `ToolContext.hil_coordinator` wired AFTER ToolContext in bootstrap (HIL=Step 22, TC=Step 15). Factory can reorder since HIL is Layer 3, TC is Layer 4. | LOW | Create HILCoordinator before ToolContext in factory sequence |
| SIM-GAP-12 | 3 | `DeadLetterConsumer.__init__(bus)` subscribes to `TOPIC_DEAD_LETTER` immediately in constructor. May receive events before consumer loop starts. | LOW | Create DeadLetterConsumer as one of the LAST factory steps |
| SIM-GAP-13 | 3 | `_build_experience_context(runtime)` reads from entire runtime object. ConciergeSession must expose internals to experience tick helper. | LOW | ConciergeSession exposes read-only properties for experience context builder |
| SIM-GAP-14 | 4 | `_mailbox_consumer()` does not call `bus.sweep()`. STRICT-mode envelopes buffered by TimingChain have no safety-net release. Lost envelope could stall topic. | MEDIUM | Consumer loop calls `bus.sweep()` when idle (SIM-D-16) |
| SIM-GAP-15 | 4 | `stop_kernel()` does not unsubscribe front event subscriptions (`runtime.front_subscriptions`). Cleaned by Bus GC but explicit cleanup is better. | LOW | `ConciergeSession.stop()` explicitly unsubscribes front handles before Bus.close() |
| SIM-GAP-16 | 4 | Bus handler dispatch is synchronous on publisher's thread. If FSM handler is slow it blocks publisher. Safe in single-threaded asyncio but fragile if background threads added. | LOW | Document constraint: all bus.publish() must happen on asyncio event loop thread |
| SIM-GAP-17 | 5 | `bootstrap.py` calls `session_state.close()` but SSM has `stop()`, not `close()`. Skipped via `hasattr` guard. Factory must call `ssm.stop()` explicitly. | LOW | KernelService calls `ssm.stop()` in session teardown (SIM-D-18) |
| SIM-GAP-18 | 5 | `affective_now` has 2 direct attribute writes (`._tone_adjustment`, `._response_style`) bypassing MutationGuard and SizeTracker | LOW | Accept as-is — transient per-turn values (~100 bytes), not persisted data |
| SIM-GAP-19 | 5 | `DirectWriterAdapter` needs SSM reference, but SSM constructor needs writer_port — circular dependency. Current workaround: create with `writer_port=None`, inject after. | LOW | Document pattern for KernelService; use existing factory modes that handle this internally |
| SIM-GAP-20 | 6 | `ModelHubGatewayAdapter` (IModelGatewayPort → IModelHubPort bridge) does not exist. Needed for Fabric's Agent Provider to grant LLM access to spawned agents. | MEDIUM | Create ~30-line adapter in `k1/fabric/adapters/model_hub_gateway.py` |
| SIM-GAP-21 | 6 | `BusDeltaAdapter` (IDeltaBusPort → Bus bridge) does not exist. Needed for Fabric agents to emit deltas via per-session Bus. | MEDIUM | Create ~20-line adapter in `k1/fabric/adapters/bus_delta.py` |
| SIM-GAP-22 | 6 | `IPromptSystemPort` has no production adapter. `TestPromptSystemAdapter` returns empty templates. Capability context building degraded. | LOW | Use TestPromptSystemAdapter initially — prompt system is future scope |
| SIM-GAP-23 | 6 | `_FabricGatewayAdapter` translates POC orchestrator types ↔ K1 Fabric types. Defined as inner class in bootstrap.py (SIM-FLAG-13). | LOW | Extract to `k1/concierge/kernel/adapters.py` per SIM-D-12 |
| SIM-GAP-24 | 7 | OrchestratorStub `handle_task()` interface incompatible with OrchestratorService mailbox-based `process()`. FSM calls `orchestrator.handle_task()` directly — method doesn't exist on production Orchestrator. | HIGH | Retire OrchestratorStub. Wire FabricOrchestratorAdapter as IDispatchPort (SIM-D-24). |
| SIM-GAP-25 | 7 | POC `TaskEnvelope` (Budget, ComplexityTier enum, task_id) vs Production `TaskEnvelope` (capabilities, params, constraints, caller_id). Structurally incompatible. | HIGH | Retire POC TaskEnvelope. Use production `k1.orchestrator.types.TaskEnvelope` exclusively. |
| SIM-GAP-26 | 7 | POC orchestrator call is synchronous (blocks FSM). Production is async (enqueue + event bus result). FSM must support DISPATCHING → async wait → RESULT_RECEIVED flow. | HIGH | FSM dispatch path rewritten to use `dispatch_port.dispatch_envelope()` + IDeltaPort result subscription. |
| SIM-GAP-27 | 7 | HIGH tier downgraded to MEDIUM in POC via PassthroughPlannerStub. Must be removed when real Planner present. | MEDIUM | Remove PassthroughPlannerStub. Production Orchestrator routes HIGH to real Planner. |
| SIM-GAP-28 | 7 | Result delivery changes from direct return to Bus event `k1.orchestration.task.complete.v1`. Concierge IDeltaPort must subscribe + FSM must handle result event. | MEDIUM | Wire IDeltaPort subscription in ConciergeFactory. FSM event handler already spec'd. |
| SIM-GAP-29 | 7 | `orchestrator._planner_port = planner_adapter` — hot-swap via private attribute. No public setter API. Fragile across refactors. | LOW | Accept for V1. Consider adding `set_planner_port()` method to OrchestratorService. |
| SIM-GAP-30 | 7 | kernel.md Phase 6 shows `FabricOrchestratorAdapter(fabric, orchestrator)` but concierge.md spec requires `(fabric, orch_mailbox, cb_orch, cb_fabric, cb_mcp)`. 3 CB args missing. | LOW | kernel.md simplified. concierge.md is canonical. Use 5-arg constructor. |
| SIM-GAP-31 | 7 | Planner V1 `_plan_lock` (asyncio.Lock) serializes ALL plans across ALL sessions. Multi-session HIGH tier tasks queue. | MEDIUM | Accept for V1 — documented limitation. V2: per-session plan isolation or concurrent planning. |
| SIM-GAP-32 | 7 | `LLMGatewayAdapter` needs `ILLMRequestBus`. Intermediary between ModelHub and Planner LLM port may not exist yet. | MEDIUM | Create ~20-line adapter or verify ILLMRequestBus exists wrapping ModelHub. |
| SIM-GAP-33 | 8 | `BridgeClient` facade class does not exist. Kernel needs single entry point wrapping CommandPort + QueryPort + SSEPort. ~80 lines. | HIGH | Build `BridgeClient` with `connect()` factory method. Returns None if K0 unreachable. |
| SIM-GAP-34 | 8 | `IKernelQueryPort` (PORT_QRY) not implemented. Blocks Concierge recall, Orchestrator WAL read, Planner recall, SS restore, Household hydration. ~150 lines. | HIGH | Build KernelQueryPort (QueryEnvelope, QueryBuilder, response parsing). P1 for Phase 2. |
| SIM-GAP-35 | 8 | `IKernelSSEPort` (PORT_SSE) not implemented. Blocks Household live deltas, memory.formed events, proactive signals, learning advisories. ~100 lines. | HIGH | Build KernelSSEPort (SSE receiver, cursor management, backpressure). P2. |
| SIM-GAP-36 | 8 | `BridgeRecallAdapter` (Concierge IMemoryPort) not implemented. Spec in concierge.md §15.2.8 but no Python file. ~40 lines. | MEDIUM | Build adapter wrapping query + LOCAL COLD fallback. |
| SIM-GAP-37 | 8 | `HouseholdProjection` dataclass + hydration protocol not implemented. Spec in kernel.md §126 but no Python file. ~60 lines. | MEDIUM | Build frozen dataclass + hydrate/apply_delta methods. |
| SIM-GAP-38 | 8 | `IMemoryPort` Protocol not implemented as Python file. Defined in concierge.md §14.9 only. ~15 lines. | MEDIUM | Create Python Protocol file from spec. |
| SIM-GAP-39 | 8 | `BridgeCommandAdapter` (Memory Writer → K0) not implemented. MW has port protocol but no adapter. ~30 lines. | MEDIUM | Build adapter wrapping KernelCommandPort. |
| SIM-GAP-40 | 8 | `BridgeSyncAdapter` (SessionState → K0) not implemented. IK0SyncPort exists but only NullSyncPort wired. | LOW | Future scope. NullSyncPort fine for V1. |
| SIM-GAP-41 | 8 | `IKernelObsPort` (PORT_OBS) not implemented. Blocks telemetry/feedback export to K0. ~50 lines. | LOW | Future scope (non-functional requirement). |
| SIM-GAP-42 | 8 | `IConnectorGatewayPort` not implemented. Entire bridge/connector/ is stub. Blocks real device integration via IFL. | LOW | Phase 2+. IFL is future scope. |
| SIM-GAP-43 | 8 | `BridgeWriteAdapter` defines its own `IBridgeClient(Protocol)` locally — not aligned with BridgeClient facade export. No shared interface contract. | MEDIUM | Align IBridgeClient with BridgeClient facade or extract to shared contract. |
| SIM-GAP-44 | 8.5 | Shared Orchestrator uses per-session Fabric (SIM-D-22). SessionStateReaderAdapter bound to one SSM at construction. Orchestrator reads wrong session's state. Requires TWO Fabric instances. | HIGH | V1: Orchestrator gets Fabric with NullStateReader. Per-session Fabric for Concierge. (SIM-D-34/D-35) |
| SIM-GAP-45 | 8.5 | `IModelGatewayPort` production adapter (Fabric→ModelHub) not built. Need `ModelHubGatewayAdapter` wrapping `IModelHubPort.execute()` into handle-factory pattern. ~30 lines. (Confirms SIM-GAP-20) | MEDIUM | Build `ModelHubGatewayAdapter` in `k1/fabric/adapters/model_hub_gateway.py` |
| SIM-GAP-46 | 8.5 | Memory Writer `IModelHubPort` name collision with canonical `k1.model_hub.ports.hub_port.IModelHubPort`. Different methods (`chat()` vs `execute()`). | MEDIUM | Build `ModelHubChatAdapter` (~25 lines). Consider renaming MW port to `IMemoryWriterLLMPort`. |
| SIM-GAP-47 | 8.5 | Shared Fabric needs `NullSessionStateReaderAdapter` and `NullDeltaBusAdapter` — neither exists. Each ~10 lines. | LOW | Build two Null adapters for shared Fabric construction. |
| SIM-GAP-48 | 8.5 | Two Fabric instances means two `CapabilityRegistry` instances. Must share registry or synchronize registrations. | MEDIUM | Share same CapabilityRegistry object between both Fabric instances (SIM-D-36). |
| SIM-GAP-49 | 9 | Planner's `SessionStateReadAdapter(reader, session_id)` is session-locked at construction. Shared Planner (SIM-D-25) can only read ONE session's state. All plans get one session's cognitive context. | HIGH | SnapshotStateReadAdapter reads from PlanRequest.context snapshot (SIM-D-38). |
| SIM-GAP-50 | 9 | DAGExecutor `read_section(session_id="default", section="control.safety_band")` hardcodes `"default"` session_id. Safety band check always hits wrong session. | MEDIUM | Fix: extract session_id from task envelope context. ~1 line. |
| SIM-GAP-51 | 9 | `NullEventPortAdapter` (for shared Fabric and Orchestrator event port at startup tier) does not exist. ~10 lines no-op. | LOW | Build null adapter for startup tier construction. |
| SIM-GAP-52 | 9 | `SnapshotStateReadAdapter` (for Planner) does not exist. ~15 lines wrapping PlanRequest.context. | MEDIUM | Build adapter that reads from bound SessionSnapshot instead of live SSM. |
| SIM-GAP-53 | 9 | `FabricFactory.create_with_ports()` does not accept external `capability_registry` param — creates its own internally. Must add optional param OR post-inject. | MEDIUM | Add optional `capability_registry` param to factory, or post-inject via `fabric._registry = shared_registry`. |
| SIM-GAP-54 | 9 | kernel.md §7 pseudocode is single-session. Must be updated to reflect two-tier bootstrap (SIM-D-02 + SIM-D-25). Documentation gap. | LOW | Update kernel.md §7 to show Tier 1 (startup) + Tier 2 (session create) structure. |
| SIM-GAP-55 | 10 | Production `TaskEnvelope` (`k1.orchestrator.types`) has NO `session_id` field. Orchestrator reads it from `context["session_id"]` — untyped, no validation. | HIGH | Add typed `session_id: str` field to production TaskEnvelope, or add validation guard on `context["session_id"]` access. |
| SIM-GAP-56 | 10 | Three conflicting tool call budget tables: `dispatcher.py` (5/10/20), `obs/actor_metrics.py` (4/8/12), `concierge.md` (6/12/20). | MEDIUM | Canonicalize on `dispatcher.py` BUDGET_LIMITS (runtime enforcer). Update docs and metrics to match. |
| SIM-GAP-57 | 10 | `IInputPort`, `IOutputPort`, `IClassificationPort` are never called by FSM code. Transport uses bus pub/sub. Phase1Pipeline is a pipeline object, not a port call. Spec-only abstractions. | HIGH | Accept bus-based I/O as canonical. Build relay adapters (~50 lines total) instead of rewiring 3600-line FSM. |
| SIM-GAP-58 | 10 | POC `CapabilityRequest.name` vs Prod `CapabilityRequest.capability_name` — different field names for same concept. Confirms SIM-GAP-06. | MEDIUM | Standardize on `capability_name` (production). Update POC types or add alias property. |
| SIM-GAP-59 | 10 | LOW tier latency budget (2s) incompatible with 7 LLM calls per turn. Minimum ~7s at 1s/call. | MEDIUM | Redefine 2s budget as first-token latency (streaming ack), not total turn time. |
| SIM-GAP-60 | 10 | SSE relay consumer (bus `TOPIC_FINAL_RESPONSE` → SSEOutputAdapter) does not exist. ~30 lines needed. | MEDIUM | Build SSE relay consumer as part of transport adapter layer. |
| SIM-GAP-61 | 10 | Input relay adapter (WebSocket → bus `TOPIC_USER_INPUT`) does not exist as formal adapter. ~20 lines needed. | MEDIUM | Build input relay adapter as part of transport adapter layer. |

## FLAG REGISTRY (existing code making integration hard)

| ID | Step | File | Problem | Impact |
|----|------|------|---------|--------|
| SIM-FLAG-01 | 1 | `k1/concierge/kernel/bootstrap.py` | Imports `poc.k1_poc.main.boot` — POC coupling | Must eliminate before KernelService can call factories directly |
| SIM-FLAG-02 | 1 | `k1/concierge/obs/metrics.py` | Custom MetricsCollector parallel to OTel, not integrated | Two metrics systems — tech debt, low priority |
| SIM-FLAG-03 | 2 | `k1/concierge/actors/front.py`, `back.py` | Actors import `IModelHubPort` from `k1.model_hub.ports`, not concierge-local ports | ILLMPort must be structurally compatible with IModelHubPort (it is) |
| SIM-FLAG-04 | 2 | `k1/concierge/orchestrator/types.py` | Defines own `CapabilityRequest`/`CapabilityResult` shadowing `k1.fabric.types` | Factory adapter must convert between two type universes |
| SIM-FLAG-05 | 2 | `k1/concierge/fsm/controller.py` | Controller uses `Any`-typed late-wired attributes for 10+ deps | Runtime errors only if factory wires wrong — no compile-time safety |
| SIM-FLAG-06 | 3 | `k1/concierge/kernel/bootstrap.py` L191–206 | `ToolContext.cognitive_trace_id` hardcoded to `k-front-{uuid}` / `k-back-{uuid}` at boot — not per-turn | Factory consumer loop must override per-turn (SIM-GAP-10) |
| SIM-FLAG-07 | 3 | `k1/concierge/kernel/bootstrap.py` L327–337 | `OrchestratorStub` wraps 3 private adapter classes defined inside bootstrap.py — factory can't import them | Extract to `k1/concierge/kernel/adapters.py` (SIM-D-12) |
| SIM-FLAG-08 | 4 | `k1/bus/core/local_bus.py` | `publish()` is synchronous — handler runs on publisher's thread. No async handler support. | Handlers must be fast (<1ms). Async work deferred via `loop.call_soon()` or queued. |
| SIM-FLAG-09 | 4 | `k1/concierge/bus/builders.py` | All 43 builders lack `session_id`/`cognitive_trace_id`/`request_id` params — trace fields never set on Envelope | TracingMiddleware (SIM-D-15) auto-stamps trace fields — builders don't need modification |
| SIM-FLAG-10 | 5 | `k1/sessionstate/factory.py` L45 | `from poc.k1_poc.config import get_config` — SS factory imports POC config | Must change to config injection or `k1.concierge.config` import. Same pattern as SIM-FLAG-01 |
| SIM-FLAG-11 | 6 | `k1/concierge/kernel/bootstrap.py` L647-665 | `_create_model()` bypasses `ModelHubFactory` — creates `ModelHubPOCBridge(GeminiConciergeAdapter)` directly | Must switch to `ModelHubFactory.create_standalone()` with plugin registration |
| SIM-FLAG-12 | 6 | `k1/concierge/kernel/bootstrap.py` L687-726 | `_create_fabric()` passes 5 test adapters to `create_with_ports()` — only bridge is real | Must replace test adapters with production: SessionStateReaderAdapter(ssm), ModelHubGatewayAdapter, BusDeltaAdapter |
| SIM-FLAG-13 | 6 | `k1/concierge/kernel/bootstrap.py` L897-939 | `_FabricGatewayAdapter` defined as private inner class — cannot be imported by factory | Extract to `k1/concierge/kernel/adapters.py` per SIM-D-12 |
| SIM-FLAG-14 | 7 | `k1/concierge/orchestrator/routing.py` | `route_task_sync()` is synchronous. Production needs async `dispatch_envelope()`. Entire routing module becomes dead code. | Retire routing.py + OrchestratorStub when FabricOrchestratorAdapter wired |
| SIM-FLAG-15 | 7 | `k1/concierge/orchestrator/types.py` | POC TaskEnvelope, Budget, CapabilityRequest, CapabilityResult all become dead code. Production types from `k1.orchestrator.types`. | Retire concierge.orchestrator.types module |
| SIM-FLAG-16 | 7 | `k1/concierge/fsm/controller.py` | FSM calls `orchestrator.handle_task()` — direct coupling to OrchestratorStub. Must change to `dispatch_port.dispatch_envelope()`. | FSM dispatch path rewrite required |
| SIM-FLAG-17 | 7 | `k1/planner/planner_agent.py` | `_plan_lock` is process-wide asyncio.Lock. V1 serializes plans across all sessions. Performance bottleneck. | Accept for V1 — V2: per-session plan isolation |
| SIM-FLAG-18 | 8 | `k1/concierge/kernel/bootstrap.py` L189 | `_build_recall_fn()` returns in-memory word-overlap scorer. Not a real Bridge adapter. Must be replaced with BridgeRecallAdapter or test stub implementing IMemoryPort. | POC recall has zero K0 integration |
| SIM-FLAG-19 | 8 | `k1/concierge/fabric/poc_bridge_adapter.py` | `POCMockBridgeAdapter` routes to CapabilityRegistry handlers. Production needs `BridgeConnectionAdapter` wrapping real `BridgeClient`. | Dead code when real Bridge wired |
| SIM-FLAG-20 | 8 | `k1/orchestrator/adapters/bridge_write_adapter.py` L72 | `IBridgeClient` Protocol defined locally inside adapter file. Should align with BridgeClient facade or extracted shared contract. | Interface mismatch risk |
| SIM-FLAG-21 | 8 | `bridge/connector/__init__.py` | Entire connector module is empty stub. IFL/external device integration blocked. | No real tool execution via Bridge |
| SIM-FLAG-22 | 8.5 | `k1/fabric/adapters/sessionstate_reader.py` L66-67 | `__init__(manager, session_id)` — adapter permanently bound to one session. Cannot serve cross-session Orchestrator. | Forces TWO Fabric instances or session-resolved pool. |
| SIM-FLAG-23 | 8.5 | `k1/memory_writer/ports/model_hub_port.py` L37 | `class IModelHubPort(Protocol)` — name collision with `k1.model_hub.ports.hub_port.IModelHubPort`. Different interface. | Import confusion. Should rename to `IMemoryWriterLLMPort`. |
| SIM-FLAG-24 | 8.5 | `k1/concierge/fabric/ports.py` | `IFabricPort.execute_batch(strategy="PARALLEL")` string arg vs `Fabric(strategy=BatchStrategy.PARALLEL)` enum arg. | Runtime OK (`BatchStrategy(str, Enum)`), type checker warns. |
| SIM-FLAG-25 | 9 | `k1/planner/adapters/session_state_adapter.py` L51 | Constructor takes `session_id: str` — permanently binds to one session. Incompatible with shared Planner (SIM-D-25). | Forces SnapshotStateReadAdapter or refactor. |
| SIM-FLAG-26 | 9 | `k1/orchestrator/orchestration/dag_executor.py` L990 | `session_id="default"` hardcoded in safety band read. | Safety band check silently reads wrong session. |
| SIM-FLAG-27 | 10 | `k1/concierge/fsm/controller.py` L2277 | Same-turn completion suppression: if Back completes in same turn as dispatch, result is deferred. | Smoke test may not see immediate result for fast LOW-tier tasks. |
| SIM-FLAG-28 | 10 | `k1/concierge/tools/dispatcher.py` L51 | BUDGET_LIMITS differs from `concierge.md` §2.3 and `obs/actor_metrics.py`. | Runtime enforcement uses dispatcher.py — others are stale docs. |
| SIM-FLAG-29 | 10 | `k1/concierge/fsm/controller.py` L2113 | PassthroughPlannerStub inline in controller.py — downgrades HIGH to MEDIUM. | Must remove for production HIGH tier path. |

## DECISION REGISTRY (design decisions needed during simulation)

| ID | Step | Question | Decision | Rationale |
|----|------|----------|----------|-----------|
| SIM-D-01 | 1 | Shared Bus or per-session Bus? | **Per-session Bus** (Option B) | Isolation, zero topic refactoring, clean teardown on eviction |
| SIM-D-02 | 1 | Session lifecycle model? | **KernelService with SessionInstance registry** | CREATE/ACTIVE/IDLE/TIMEOUT/DESTROY states. ConciergeFactory per session. |
| SIM-D-03 | 1 | cognitive_trace_id scope? | **Per-turn, generated at IInputPort** | Flows end-to-end: envelope → FSM → actors → tools → delta → MW → bridge → K0 |
| SIM-D-04 | 1 | Which components shared vs per-session? | **Bus/SS/FSM/Ledger/Delta/Experience/Fabric per-session. BackPool/ModelHub/Orch/Planner/Bridge/Household shared.** | Stateful = per-session. Stateless/expensive = shared. Fabric per-session because ISessionStateReader is session-bound (SIM-D-22). |
| SIM-D-05 | 1 | Threading model? | **Single asyncio event loop per process, multi-process for scale** | Codebase is asyncio-first. Bus threading.Lock is safe. HA via process-level replication + sticky sessions. |
| SIM-D-06 | 2 | External port signatures? | **kernel.md §89 is canonical, no changes** | Consistent across all 5 spec locations. No contradictions. ILLMPort ≈ IModelHubPort structurally. |
| SIM-D-07 | 2 | What happens to internal ports? | **Stay untouched. Zero modifications.** | Internal ports serve internal contracts. 63 tests pass. Factory bridges external → internal. |
| SIM-D-08 | 2 | How to bridge external types to internal types? | **Direct passthrough where compatible (ILLMPort→IModelHubPort), type converter where not (ClassificationResult→Phase1Result, CapabilityRequest cross-module), closure wrapping for callbacks (flush_fn, recall_fn)** | Minimal glue. Each bridge is <20 lines. |
| SIM-D-09 | 3 | Factory return type? | **`ConciergeSession` wrapper** over `KernelRuntime` | Clean lifecycle API (start/stop). Hides 25+ field flat dataclass. Tests get simple interface. |
| SIM-D-10 | 3 | Factory wiring sequence? | **26-step sequence (Phases A–H)**, eliminating 6 POC-coupled steps | Follows proven bootstrap order. Dependency layers enforced. No circular deps. |
| SIM-D-11 | 3 | Where do test adapters live? | **`k1/concierge/kernel/test_adapters.py`** — all 8 fakes in one file | All <30 lines each. Co-located with factory. No external deps. |
| SIM-D-12 | 3 | Where do orchestrator adapter classes live? | **Extract to `k1/concierge/kernel/adapters.py`** | Currently private to bootstrap.py. Factory needs them. Shared module avoids duplication. |
| SIM-D-13 | 4 | Who creates the Bus? | **KernelService creates, ConciergeFactory receives** | Bus is infrastructure. KernelService injects middleware (tracing, metrics). Factory wires subscriptions only. |
| SIM-D-14 | 4 | Ordered or unordered Bus? | **Ordered (TimingChain) for production, unordered for tests** | STRICT topics enforce causal ordering. Tests want immediate delivery + capture. |
| SIM-D-15 | 4 | Where to inject tracing/metrics on Bus? | **TracingMiddleware at KernelService level** | Auto-stamps session_id + cognitive_trace_id on EVERY envelope. Solves SIM-GAP-01 without modifying 43 builders. |
| SIM-D-16 | 4 | How to handle TimingChain sweep? | **Consumer loop calls `bus.sweep()` every iteration when idle** | Minimal overhead (no-op when empty). Releases timed-out STRICT envelopes as safety net. |
| SIM-D-17 | 5 | Is IStatePort a wrapper around SSM? | **NO — IStatePort IS the SSM instance. No wrapper needed.** | Concierge calls 100+ methods across 12 section objects. Wrapping would create massive fragile proxy. SSM already has the exact API. |
| SIM-D-18 | 5 | Who manages SSM lifecycle (start/stop)? | **KernelService** — calls `start()` before ConciergeFactory, `stop()` after ConciergeSession.stop() | SSM has its own lifecycle state machine. KernelService ensures RUNNING state before Concierge touches it. |
| SIM-D-19 | 5 | Which SS factory mode for production? | **`create_standalone()` initially, `create_with_ports()` when Bridge adapters exist** | Standalone mode works fully offline (SQLite). Production ports (BridgeStorage, DeltaBusAdapter) are future scope. |
| SIM-D-20 | 6 | Is IFabricPort a wrapper around Fabric? | **NO — Fabric container IS the IFabricPort. Pass directly.** | Fabric.execute()/discover_capabilities() match IFabricPort Protocol exactly. Same pattern as SIM-D-17 (SSM). |
| SIM-D-21 | 6 | Use ModelHubFactory or POC bridge? | **ModelHubFactory.create_standalone()** — retire ModelHubPOCBridge | Factory wires 11 internal services (circuit breaker, rate limiter, cost tracker, etc.). POC bridge has none. |
| SIM-D-22 | 6 | ModelHub shared or per-session? Fabric? | **ModelHub: shared (one per process). Fabric: per-session.** | ModelHub stateless. Fabric binds to session-specific SSM via ISessionStateReader. |
| SIM-D-23 | 6 | How to handle POC orchestrator types vs K1 Fabric types? | **Keep `_FabricGatewayAdapter` as translator. Extract to adapters.py.** | Two type systems coexist until POC types retired. Adapter is 40 lines, clean boundary. |
| SIM-D-24 | 7 | How does Concierge talk to production Orchestrator? | **FabricOrchestratorAdapter replaces entire POC routing stack.** Implements IDispatchPort. Takes orchestrator_mailbox + 3 CBs. Retires OrchestratorStub + route_task_sync() + 3 private adapters. | concierge.md §15.2.6 already specifies this adapter. Clean port-based boundary. |
| SIM-D-25 | 7 | Orchestrator and Planner shared or per-session? | **Shared (one per process).** Created at KernelService startup. ConciergeFactory receives mailbox reference. | Stateless processors. TaskEnvelope/PlanRequest carry session context. Expensive to duplicate. |
| SIM-D-26 | 7 | How to handle Orchestrator→Planner bootstrap ordering? | **Phased: Phase 4 (Orch + MockPlanner) → Phase 5 (Planner) → Phase 5b (hot-swap).** | Avoids circular dependency. MEDIUM works immediately. HIGH available after hot-swap. |
| SIM-D-27 | 7 | What happens to POC orchestrator code? | **Dead code. Mark for removal.** routing.py, stub.py, concierge/orchestrator/types.py, 3 private bootstrap adapters — all retired. | Clean separation. POC served its purpose. Production has own adapter stack. |
| SIM-D-28 | 7 | How does Planner get LLM access? | **`LLMGatewayAdapter(llm_request_bus)` where bus wraps ModelHub.** Create thin adapter (~20 lines) if ILLMRequestBus doesn't exist. | kernel.md Phase 2 target. ModelHub is the canonical LLM provider per SIM-D-21. |
| SIM-D-29 | 8 | What is BridgeClient? | **Thin facade wrapping 3 ports** (CommandPort + QueryPort + SSEPort). Factory `BridgeClient.connect(config) → BridgeClient or None`. | kernel.md expects query/send_command/subscribe/close. Facade delegates to specialized ports. |
| SIM-D-30 | 8 | BridgeClient shared or per-session? | **Shared (one per process).** All K1 adapters receive same BridgeClient reference. | Bridge is infrastructure. Transport connection pool shared. LocalOutbox shared. Same pattern as ModelHub (SIM-D-22). |
| SIM-D-31 | 8 | Is HouseholdProjection part of SessionState? | **NO.** Frozen in-memory projection cached in Concierge. Per-turn: 0ms. Not SS. | Family identity (names, allergies, governance) is household-level, not conversation-level. |
| SIM-D-32 | 8 | When to create BridgeClient in bootstrap? | **Phase 2.5 (early).** Created before Orch/Planner/Concierge. `None` if offline. | All consumers need bridge reference. Phased stub approach matches kernel.md pattern. |
| SIM-D-33 | 8 | How to handle bridge_client = None? | **Each adapter has built-in offline fallback.** No special kernel-level handling. | BridgeWriteAdapter: drop. BridgeAdapter: empty recall. BridgeRecallAdapter: LOCAL COLD. Pattern in all adapters. |
| SIM-D-34 | 8.5 | How does shared Orchestrator access Fabric when Fabric is per-session? | **V1: Orchestrator gets Fabric with NullStateReader.** Capabilities execute without session context. AffectiveRouting/CognitiveLoadRouting degrade to defaults. V2: session-resolved Fabric pool. | Session context is nice-to-have for orchestrated tasks, not critical. Simplest V1 approach. |
| SIM-D-35 | 8.5 | How many Fabric instances? | **TWO: shared Fabric (NullState, for Orch+Planner) + per-session Fabric (real SSM, for Concierge).** Amends SIM-D-22. | SessionStateReaderAdapter bound at construction. Cannot serve multiple sessions. |
| SIM-D-36 | 8.5 | How does shared Fabric get capabilities? | **Share same CapabilityRegistry object between shared + per-session Fabric instances.** Register once on shared, reference from per-session. | Capabilities don't change per session. Registry is thread-safe. Avoids double-registration. |
| SIM-D-37 | 8.5 | How does Memory Writer get LLM access? | **`ModelHubChatAdapter` (~25 lines): converts `chat(messages, budget, hint) → HubRequest → hub.execute() → ChatResponse`.** | MW-06 enforces 2000 token budget. Adapter maps MW chat interface to Hub execute interface. |
| SIM-D-38 | 9 | How does shared Planner read session state? | **SnapshotStateReadAdapter** — reads from `PlanRequest.context` snapshot instead of live SSM. PlannerAgent calls `bind(snapshot)` before each pipeline run. | PlanRequest already carries SessionSnapshot. Planning uses point-in-time data. No live reads needed. ~15 lines. Zero port contract changes. |
| SIM-D-39 | 9 | Two-tier or single-tier bootstrap? | **Two-tier: Startup (shared, once) + Session (per-session, on demand).** kernel.md §7 restructured. | SIM-D-01 (per-session bus), SIM-D-02 (session registry), SIM-D-25 (shared Orch+Planner) require structural split. |
| SIM-D-40 | 9 | What happens when a startup-tier component fails? | **ModelHub/Fabric: degraded. Bridge: offline. Orchestrator: fatal. Planner: degraded (HIGH→MED).** Session-tier failures are per-session only. | Edge-first principle: degrade don't crash. Only Orchestrator is truly mandatory. |
| SIM-D-41 | 10 | How to handle 3 unused port abstractions (IInputPort, IOutputPort, IClassificationPort)? | **V1: Accept bus-based I/O. Build relay adapters (~50 lines).** Do NOT rewire FSM. | Rewiring 3600-line FSM is major rewrite. Bus-based I/O works. Relay adapters bridge the gap cleanly. |
| SIM-D-42 | 10 | Which tool budget table is canonical? | **`dispatcher.py` BUDGET_LIMITS is canonical** (LOW:5, MED:10, HIGH:20). Update docs and metrics to match. | dispatcher.py is the runtime enforcer. Other tables are documentation/metrics artifacts. |
| SIM-D-43 | 10 | How to handle LOW tier 2s latency target with 7 LLM calls? | **Measure first-token latency, not total.** 2s applies to streaming ack, not turn completion. | Edge-first UX: acknowledge immediately, stream results progressively. |

---

> **How we proceed:** We execute Step 1 first. We read real code. We discover real problems. We make real decisions. Then Step 2. No skipping.

---
---

# PHASE 1: PORT PROTOCOLS + TEST ADAPTERS — IMPLEMENTATION PLAN (v2 — CODE-GROUNDED)

> **Milestone:** Concierge Hexagonal Ports (Phase C1)
> **Source of truth:** CODEBASE — every signature below was traced from actual call sites
> **Goal:** Define 8 Concierge port Protocols that wrap what the code ALREADY does, + test adapters + unit tests. Zero changes to existing code.
> **Estimated new code:** ~500 lines (ports + types) + ~300 lines (test adapters) + ~400 lines (tests)

---

## WHAT THE CODE ACTUALLY DOES (audit summary)

Before defining ports, here's what the codebase audits revealed. Every claim below is backed by file:line.

### Input: Bus-based, not port-based

- Transport calls `build_user_input({"text": ..., "device_id": ...})` → `Envelope`
- `IBus.publish(envelope)` → bus routes to FSM
- `ConciergeController._on_user_input(envelope: Envelope)` → dedup, guard, payload extraction
- Payload: `json.loads(envelope.payload)` → `dict` with keys `text`, `device_id`
- FSM routes to front_handler via mailbox, NOT via any IInputPort
- **Source:** `k1/concierge/fsm/controller.py` L1104, `k1/concierge/bus/builders.py` L214

### Output: Bus-based, not port-based

- `front.py` calls `build_final_response({"text": ..., "trace_id": ...})` → `Envelope`
- `bus.publish(envelope)` on topics: `k1.response.final.v1`, `k1.response.stream.v1`, `k1.response.clarification.v1`
- FSM subscribes to `TOPIC_FINAL_RESPONSE` via `_on_response_final()`
- No OutputEvent, no DeliveryReceipt, no StreamReceipt types exist in code
- **Source:** `k1/concierge/actors/front.py` L927, `k1/concierge/bus/builders.py` L244

### Classification: Phase1Pipeline Protocol (already exists)

- `Phase1Pipeline` Protocol ALREADY defined in `k1/concierge/fsm/phase1.py` L75
- Single method: `classify(text: str) -> Phase1Result`
- `Phase1Result` ALREADY defined with 14 `__slots__` fields (L24)
- `StubPhase1Pipeline` ALREADY exists (L102) — default test stub
- `UltraBERTPhase1Pipeline` ALREADY exists in `ultrabert_phase1.py` (L25) — production impl
- FSM calls: `self._phase1_pipeline.classify(text)` at L1264, L1786, L1851
- **Source:** `k1/concierge/fsm/phase1.py`, `k1/concierge/fsm/controller.py`

### LLM: IModelHubPort (already exists)

- `IModelHubPort` Protocol ALREADY defined in `k1/model_hub/ports/hub_port.py` L15
- Methods: `execute(HubRequest) -> HubResponse`, `stream_execute(HubRequest) -> AsyncIterator[HubChunk]`, `discover_capabilities()`, `discover_models()`, `health()`
- `HubRequest`, `HubResponse`, `HubChunk` ALREADY defined in `k1/model_hub/types.py`
- `front_handler()` annotates `model: IModelHubPort` at `front.py` L26
- ReAct loop calls `model.execute(request)` at `loop.py` L292, L298, L481
- `ModelHubPOCBridge` ALREADY wraps `TestConciergeAdapter` → `IModelHubPort`
- **Source:** `k1/model_hub/ports/hub_port.py`, `k1/concierge/react/loop.py`

### SessionState: Duck-typed as `Any`

- Type annotation: `ss: Any` EVERYWHERE (front.py, back.py, controller.py, implementations.py)
- Read methods: `ss.get_section(name)`, `section.to_prompt()`, `section.to_slim_prompt()`, `section.get_typed_entries()`, `section.find_by_subject()`, `section.get_all()`
- Write path: `ctx.writer_port` (MutationRequest-based), NOT direct `ss.write()`
- Controller: `self._ss.get_section("control")`, etc. — pure reads
- Writes go through: `ctx.writer_port.write(MutationRequest(...))` (M4 E4.2.1)
- **Source:** `k1/concierge/tools/implementations.py` L57, `k1/concierge/actors/front.py`

### Dispatch: IFabricPort + OrchestratorStub (already exist)

- `IFabricPort` Protocol ALREADY defined in `k1/concierge/fabric/ports.py`
- Methods: `execute(CapabilityRequest) -> CapabilityResult`, `execute_batch()`, `discover_capabilities()`, `find_relevant_prompts()`
- ToolContext.fabric_port typed as `IFabricPort | None`
- `invoke_capability` tool calls: `ctx.fabric_port.execute(CapabilityRequest(...))`
- `dispatch_task` tool returns `ToolResult(data={"_dispatch": payload})` — FSM intercepts, NOT direct bus emit
- `OrchestratorStub.handle_task(TaskEnvelope) -> AggregatedResult` at `orchestrator/stub.py`
- **Source:** `k1/concierge/fabric/ports.py`, `k1/concierge/tools/implementations.py` L803

### Delta/Bus: IBus Protocol (already exists)

- `IBus` Protocol ALREADY defined in `k1/bus/ports/bus.py` L67
- Methods: `publish(Envelope)`, `subscribe(pattern, handler) -> SubscriptionHandle`, `unsubscribe(handle)`
- 20+ `self._bus.publish()` calls in controller.py
- `DeltaAggregator` uses `flush_fn: Callable[[DeltaBatch], Awaitable[None]]`
- 28+ topic constants in `k1/concierge/bus/topics.py`
- **Source:** `k1/bus/ports/bus.py`, `k1/concierge/fsm/controller.py`

### Memory: Untyped closure

- `recall_fn: Callable | None` in ToolContext — no Protocol, no port
- Signature: `async (query: str, memory_types: list, max_results: int) -> list[dict]`
- `_build_recall_fn()` in bootstrap.py L726 returns a keyword-scoring closure over seed memories
- **Source:** `k1/concierge/tools/implementations.py` L553, `k1/concierge/kernel/bootstrap.py` L726

---

## KEY INSIGHT: 4 PORTS ALREADY EXIST, 4 DON'T

| Port | Status | What exists | What's needed |
|------|--------|-------------|---------------|
| IInputPort | **DOES NOT EXIST** | Bus pub/sub + FSM handler | Relay adapter (bus ← transport) |
| IOutputPort | **DOES NOT EXIST** | Bus pub/sub + builder fns | Relay adapter (bus → transport) |
| IClassificationPort | **ALREADY EXISTS** | `Phase1Pipeline` Protocol + `Phase1Result` + `StubPhase1Pipeline` | Just re-export as IClassificationPort alias |
| ILLMPort | **ALREADY EXISTS** | `IModelHubPort` Protocol + all types + `ModelHubPOCBridge` | Just re-export as ILLMPort alias |
| IStatePort | **DOES NOT EXIST** | `ss: Any` everywhere, duck-typed | Protocol wrapping actual SSM methods |
| IDispatchPort | **PARTIALLY EXISTS** | `IFabricPort` + `OrchestratorStub` | Combine into unified dispatch port |
| IDeltaPort | **ALREADY EXISTS** | `IBus` Protocol + `Envelope` + 28 topics | Just re-export as IDeltaPort alias |
| IMemoryPort | **DOES NOT EXIST** | `recall_fn: Callable` closure | Protocol wrapping the recall signature |

**This changes the plan dramatically.** We don't invent fantasy types — we create thin Protocol wrappers around what already works.

---

## MILESTONE: `C1 — Concierge Hexagonal Port Foundation`

**Acceptance criteria:**

1. 8 port Protocols defined — each wrapping ACTUAL code interfaces
2. Test adapters for the 4 ports that don't already have test implementations
3. Re-exports for the 4 ports that already exist
4. Unit tests proving Protocol compliance
5. Zero imports from concierge internals in the ports file (only from bus, model_hub, fabric, sessionstate)
6. Zero modifications to any existing file
7. All existing tests still pass

---

## EPIC 1: Port Protocol Definitions

### Issue 1.1: Create `k1/concierge/ports.py` — 8 Protocols grounded in real code

**The 8 Protocols — every signature traced from actual call sites:**

```python
# --- 1. IInputPort ---
# Reality: FSM._on_user_input(envelope: Envelope) receives from bus
# This port abstracts the transport→bus bridge
class IInputPort(Protocol):
    async def receive(self) -> Envelope: ...
    def has_buffered(self) -> bool: ...

# --- 2. IOutputPort ---
# Reality: front.py calls bus.publish(build_final_response({...}))
# This port abstracts the bus→transport bridge
class IOutputPort(Protocol):
    async def send(self, envelope: Envelope) -> None: ...

# --- 3. IClassificationPort ---
# Reality: ALREADY Phase1Pipeline Protocol in k1/concierge/fsm/phase1.py
# Method: classify(text: str) -> Phase1Result
# Re-export. Don't reinvent.
IClassificationPort = Phase1Pipeline  # type alias

# --- 4. ILLMPort ---
# Reality: ALREADY IModelHubPort in k1/model_hub/ports/hub_port.py
# Methods: execute(HubRequest)->HubResponse, stream_execute()->AsyncIterator[HubChunk]
# Re-export. Don't reinvent.
ILLMPort = IModelHubPort  # type alias

# --- 5. IStatePort ---
# Reality: ss is duck-typed as Any. Actual methods called:
#   ss.get_section(name: str) -> section object
#   section.to_prompt() -> str
#   section.to_slim_prompt() -> str
#   section.find_by_subject(s) -> ...
#   section.get_all() -> ...
#   section.get_typed_entries() -> ...
# Write path: ctx.writer_port.write(MutationRequest)
# This port wraps the SSM's read surface + writer_port write surface
class IStatePort(Protocol):
    def get_section(self, name: str) -> Any: ...
    def get_snapshot(self) -> dict[str, Any]: ...

# --- 6. IDispatchPort ---
# Reality: Two mechanisms:
#   a) ctx.fabric_port.execute(CapabilityRequest) -> CapabilityResult (LOW tier)
#   b) OrchestratorStub.handle_task(TaskEnvelope) -> AggregatedResult (MED/HIGH)
# This port unifies both behind one interface
class IDispatchPort(Protocol):
    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult: ...
    async def dispatch_envelope(self, envelope: TaskEnvelope) -> AggregatedResult: ...

# --- 7. IDeltaPort ---
# Reality: ALREADY IBus in k1/bus/ports/bus.py
# Methods: publish(Envelope), subscribe(pattern, handler)->SubscriptionHandle, unsubscribe(handle)
# Re-export. Don't reinvent.
IDeltaPort = IBus  # type alias

# --- 8. IMemoryPort ---
# Reality: recall_fn: Callable | None in ToolContext
# Signature: async (query: str, memory_types: list, max_results: int) -> list[dict]
class IMemoryPort(Protocol):
    async def recall(
        self, query: str, memory_types: list[str] | None = None, max_results: int = 5
    ) -> list[dict[str, Any]]: ...
```

**Import chain:**

- `Phase1Pipeline`, `Phase1Result` from `k1.concierge.fsm.phase1`
- `IModelHubPort` from `k1.model_hub.ports`
- `HubRequest`, `HubResponse`, `HubChunk` from `k1.model_hub.types`
- `IBus`, `SubscriptionHandle` from `k1.bus.ports`
- `Envelope` from `k1.bus.envelope`
- `IFabricPort` from `k1.concierge.fabric.ports`
- `CapabilityRequest`, `CapabilityResult` from `k1.fabric.types`
- `TaskEnvelope`, `AggregatedResult` from `k1.concierge.orchestrator.types`

**NO NEW TYPES NEEDED** for the ports file. Every type already exists in the codebase.

### Issue 1.2: Create `k1/concierge/types/__init__.py` — Re-export hub for existing types

Single file that re-exports types from their canonical locations:

```python
# Re-exports from existing codebase — NOTHING invented here
from k1.model_hub.types import HubRequest, HubResponse, HubChunk
from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.concierge.orchestrator.types import TaskEnvelope, AggregatedResult
from k1.concierge.fsm.phase1 import Phase1Result
from k1.bus.envelope import Envelope
from k1.bus.ports import IBus, SubscriptionHandle
```

---

## EPIC 2: Test Adapters (only for the 4 ports that LACK test implementations)

The 4 re-exported ports already have test implementations:

| Port | Existing test impl | Location |
|------|-------------------|----------|
| IClassificationPort | `StubPhase1Pipeline` | `k1/concierge/fsm/phase1.py` L102 |
| ILLMPort | `TestModelHubBridge(TestConciergeAdapter)` | `k1/concierge/llm/test_model_hub_bridge.py` |
| IDeltaPort | `LocalBus` (in-process, synchronous) | `k1/bus/local/local_bus.py` |
| IDispatchPort (partial) | `FabricPOCBridge` | `k1/concierge/fabric/bridge.py` |

We only need NEW test adapters for: **IInputPort, IOutputPort, IStatePort, IMemoryPort**.

### Issue 2.1: Create `k1/concierge/adapters/__init__.py` — package init

### Issue 2.2: `TestInputAdapter` (IInputPort)

```python
class TestInputAdapter:
    """Test adapter for IInputPort — injects Envelopes into the system."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Envelope] = asyncio.Queue()

    async def receive(self) -> Envelope:
        return await self._queue.get()

    def has_buffered(self) -> bool:
        return not self._queue.empty()

    # -- Test helpers --
    def inject(self, envelope: Envelope) -> None:
        self._queue.put_nowait(envelope)

    def inject_text(self, text: str, session_id: str = "test") -> None:
        from k1.concierge.bus.builders import build_user_input
        env = build_user_input({"text": text, "device_id": "test"})
        self._queue.put_nowait(env)
```

~20 lines.

### Issue 2.3: `TestOutputAdapter` (IOutputPort)

```python
class TestOutputAdapter:
    """Test adapter for IOutputPort — captures all emitted Envelopes."""

    def __init__(self) -> None:
        self.sent: list[Envelope] = []

    async def send(self, envelope: Envelope) -> None:
        self.sent.append(envelope)

    # -- Test helpers --
    def get_sent(self, topic: str | None = None) -> list[Envelope]:
        if topic is None:
            return list(self.sent)
        return [e for e in self.sent if e.topic == topic]

    def last(self) -> Envelope | None:
        return self.sent[-1] if self.sent else None

    def clear(self) -> None:
        self.sent.clear()
```

~20 lines.

### Issue 2.4: `InMemoryStateAdapter` (IStatePort)

```python
class InMemoryStateAdapter:
    """Test adapter for IStatePort — in-memory section store.

    Mirrors SessionStateManager's actual API as used by Concierge:
      - get_section(name) returns section-like objects
      - get_snapshot() returns all sections
    """

    def __init__(self) -> None:
        self._sections: dict[str, Any] = {}

    def get_section(self, name: str) -> Any:
        return self._sections.get(name)

    def get_snapshot(self) -> dict[str, Any]:
        return dict(self._sections)

    # -- Test helpers --
    def seed(self, name: str, section: Any) -> None:
        self._sections[name] = section

    def seed_dict(self, name: str, data: dict) -> None:
        """Seed with a SimpleNamespace so .attr access works."""
        import types
        self._sections[name] = types.SimpleNamespace(**data)
```

~25 lines.

### Issue 2.5: `MockMemoryAdapter` (IMemoryPort)

```python
class MockMemoryAdapter:
    """Test adapter for IMemoryPort — scripted recall results."""

    def __init__(self, memories: list[dict] | None = None) -> None:
        self._memories = memories or []
        self.recall_calls: list[tuple[str, list[str] | None, int]] = []

    async def recall(
        self, query: str, memory_types: list[str] | None = None, max_results: int = 5
    ) -> list[dict[str, Any]]:
        self.recall_calls.append((query, memory_types, max_results))
        return self._memories[:max_results]

    # -- Test helpers --
    def seed(self, memories: list[dict]) -> None:
        self._memories = memories
```

~15 lines.

### Issue 2.6: `MockDispatchAdapter` (IDispatchPort)

```python
class MockDispatchAdapter:
    """Test adapter for IDispatchPort — returns scripted results."""

    def __init__(self) -> None:
        self._direct_results: list[CapabilityResult] = []
        self._envelope_results: list[AggregatedResult] = []
        self.direct_calls: list[CapabilityRequest] = []
        self.envelope_calls: list[TaskEnvelope] = []

    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult:
        self.direct_calls.append(request)
        if self._direct_results:
            return self._direct_results.pop(0)
        return CapabilityResult(status="success", result={})

    async def dispatch_envelope(self, envelope: TaskEnvelope) -> AggregatedResult:
        self.envelope_calls.append(envelope)
        if self._envelope_results:
            return self._envelope_results.pop(0)
        return AggregatedResult(results=[], summary="mock")

    # -- Test helpers --
    def script_direct(self, results: list[CapabilityResult]) -> None:
        self._direct_results = list(results)

    def script_envelope(self, results: list[AggregatedResult]) -> None:
        self._envelope_results = list(results)
```

~25 lines.

---

## EPIC 3: Unit Tests

### Issue 3.1: Create `tests/k1/concierge/ports/test_port_protocols.py`

**8 Protocol compliance tests:**

```
test_test_input_adapter_satisfies_iinputport
test_test_output_adapter_satisfies_ioutputport
test_stub_phase1_satisfies_iclassificationport      # existing StubPhase1Pipeline
test_model_hub_bridge_satisfies_illmport             # existing ModelHubPOCBridge
test_in_memory_state_satisfies_istateport
test_mock_dispatch_satisfies_idispatchport
test_local_bus_satisfies_ideltaport                   # existing LocalBus
test_mock_memory_satisfies_imemoryport
```

Each test: `assert isinstance(adapter, PortProtocol)` + verify all methods callable.

### Issue 3.2: Create `tests/k1/concierge/ports/test_input_adapter.py`

```
test_receive_from_injected_envelope
test_receive_waits_when_empty
test_has_buffered_empty_false
test_has_buffered_after_inject_true
test_inject_text_creates_valid_envelope
test_fifo_ordering
```

### Issue 3.3: Create `tests/k1/concierge/ports/test_output_adapter.py`

```
test_send_captures_envelope
test_get_sent_no_filter
test_get_sent_with_topic_filter
test_last_returns_most_recent
test_clear_resets
```

### Issue 3.4: Create `tests/k1/concierge/ports/test_state_adapter.py`

```
test_get_section_returns_none_missing
test_get_section_returns_seeded
test_get_snapshot_all_sections
test_seed_dict_allows_attr_access
```

### Issue 3.5: Create `tests/k1/concierge/ports/test_dispatch_adapter.py`

```
test_dispatch_direct_returns_default
test_dispatch_direct_returns_scripted
test_dispatch_envelope_returns_default
test_calls_recorded
```

### Issue 3.6: Create `tests/k1/concierge/ports/test_memory_adapter.py`

```
test_recall_returns_seeded
test_recall_respects_max_results
test_recall_records_calls
test_recall_empty_returns_empty
```

### Issue 3.7: Run regression gate — full `pytest tests/`

All existing 63+ tests must pass. Zero modifications to existing files.

---

## EXECUTION ORDER

```
Issue 1.2  →  types/__init__.py (re-export hub, ~15 lines)
Issue 1.1  →  ports.py (8 Protocols, 4 aliases + 4 new, ~80 lines)
      ↓
Issue 2.1  →  adapters/__init__.py
Issue 2.2  →  TestInputAdapter (~20 lines)
Issue 2.3  →  TestOutputAdapter (~20 lines)
Issue 2.4  →  InMemoryStateAdapter (~25 lines)
Issue 2.5  →  MockMemoryAdapter (~15 lines)
Issue 2.6  →  MockDispatchAdapter (~25 lines)
      ↓
Issue 3.1  →  Protocol compliance tests (8 tests)
Issue 3.2  →  Input adapter tests (6 tests)
Issue 3.3  →  Output adapter tests (5 tests)
Issue 3.4  →  State adapter tests (4 tests)
Issue 3.5  →  Dispatch adapter tests (4 tests)
Issue 3.6  →  Memory adapter tests (4 tests)
      ↓
Issue 3.7  →  Regression gate
```

**Total: 3 epics, 14 issues, ~31 test cases, ~500 lines of new code, 0 existing file changes.**

---

## FILE TREE (Phase 1 deliverables)

```
k1/concierge/
├── ports.py                          # NEW — 8 Protocols (~80 lines)
├── types/
│   └── __init__.py                   # NEW — re-exports (~15 lines)
├── adapters/
│   ├── __init__.py                   # NEW — re-exports
│   ├── test_input.py                 # NEW — TestInputAdapter (~20 lines)
│   ├── test_output.py                # NEW — TestOutputAdapter (~20 lines)
│   ├── test_state.py                 # NEW — InMemoryStateAdapter (~25 lines)
│   ├── test_dispatch.py              # NEW — MockDispatchAdapter (~25 lines)
│   └── test_memory.py               # NEW — MockMemoryAdapter (~15 lines)

tests/k1/concierge/ports/
├── __init__.py
├── test_port_protocols.py            # NEW — 8 compliance tests
├── test_input_adapter.py             # NEW — 6 tests
├── test_output_adapter.py            # NEW — 5 tests
├── test_state_adapter.py             # NEW — 4 tests
├── test_dispatch_adapter.py          # NEW — 4 tests
└── test_memory_adapter.py            # NEW — 4 tests
```

**14 new files. 0 modified files. 0 deleted files. ~500 lines total.**

---

## WHAT CHANGED FROM v1 PLAN

| v1 (spec-based) | v2 (code-grounded) | Why |
|---|---|---|
| 8 new Protocol defs | 4 new + 4 re-exports | IModelHubPort, Phase1Pipeline, IBus, IFabricPort ALREADY EXIST |
| ~25 new type defs (UserMessage, OutputEvent, etc.) | 0 new types | Every type already exists in codebase (Envelope, HubRequest, Phase1Result, CapabilityRequest, etc.) |
| `k1/concierge/types/` with 7 files | `k1/concierge/types/` with 1 re-export file | No new types to define |
| 8 test adapters | 5 test adapters (3 already exist) | StubPhase1Pipeline, TestModelHubBridge, LocalBus already work |
| concierge.md §14 signatures | Actual call-site signatures | `ss.get_section()` not `ss.read()`. `Envelope` not `UserMessage`. `recall_fn(query, types, max)` not `recall(MemoryQuery, selectors)` |
| ~1000 lines new code | ~500 lines new code | Half the work because half already exists |
| 29 new files | 14 new files | Less than half |

---
---

# PHASE 2: P0 ADAPTERS — IMPLEMENTATION PLAN (v1 — CODE-GROUNDED)

> **Milestone:** Concierge P0 Adapters (Phase C2-prep)
> **Source of truth:** CODEBASE — every signature below was traced from actual files
> **Goal:** Build the ~130 lines of structurally mandatory adapters that block the two-tier bootstrap (SIM-D-39). Without these, shared Orchestrator/Planner cannot be wired.
> **Estimated new code:** ~130 lines (adapters) + ~200 lines (tests)

---

## WHAT THE CODE ACTUALLY NEEDS (audit summary)

### The Two-Tier Bootstrap Problem (SIM-D-39)

The simulation proved that Orchestrator and Planner are **shared** (SIM-D-25) — created once at startup, not per session. But several of their port dependencies are **per-session** (SSM, Bus, Fabric). This creates a structural gap: how do you construct shared components that need per-session dependencies?

The answer from SIM-D-34/D-35/D-38: **Null adapters for the startup tier.** Shared components get no-op implementations of session-bound ports. They degrade gracefully (empty state reads, silent delta drops) rather than crashing.

### Three Families of Null Adapters Needed

**Family 1: Fabric Null Adapters (SIM-GAP-47)**

Shared Fabric (for Orchestrator + Planner) needs `ISessionStateReader` and `IDeltaBusPort` at construction. But real adapters are per-session. The simulation says: build Null versions that return empty/no-op.

- `ISessionStateReader` Protocol (Fabric's): `k1/fabric/ports/state_reader.py` L94
  - `read_section(session_id, section) -> Optional[Dict]`
  - `read_sections(session_id, names) -> Dict`
  - `get_snapshot(session_id) -> SessionSnapshot`
- `IDeltaBusPort` Protocol (Fabric's): `k1/fabric/ports/delta_bus.py` L96
  - `emit_delta(agent_id, delta_type, section, data) -> None`

Both Fabric test adapters exist (`TestSessionStateReaderAdapter` at `k1/fabric/adapters/test_state_reader.py`, `TestDeltaBusAdapter` at `k1/fabric/adapters/test_delta_bus.py`), but they store state and are designed for test assertions. Null adapters are simpler — pure no-ops with zero storage.

**Family 2: Event Null Adapter (SIM-GAP-51)**

Shared Fabric and Orchestrator both need event ports at construction. Fabric uses `IEventPort` (`k1/fabric/ports/event_port.py` L78), Orchestrator uses `IEventSubscriptionPort` (`k1/orchestrator/ports/event_subscription_port.py` L55). These are structurally similar but **separate Protocols** (different modules, slightly different payload typing).

At startup tier, no events need to be routed — we just need no-ops that absorb `emit()` calls and return dummy handles from `subscribe()`.

The existing `LocalEventAdapter` (`k1/fabric/adapters/local_event.py`) is a full in-memory event bus with routing and capture mode. Overkill for null use. But it already works and satisfies `IEventPort`. For **Orchestrator's** `IEventSubscriptionPort`, we need a null adapter.

**Decision:** Use existing `LocalEventAdapter(capture_mode=False)` for shared Fabric's `IEventPort`. Build `NullEventSubscriptionAdapter` ONLY for Orchestrator's `IEventSubscriptionPort`.

**Family 3: Planner Snapshot Adapter (SIM-D-38/SIM-GAP-49)**

Shared Planner needs `IStateReadPort` (Planner version: `k1/planner/ports/state_read_port.py` L43). The real adapter (`SessionStateReadAdapter`) is session-locked at construction. Shared Planner serves ALL sessions.

Fix: `SnapshotStateReadAdapter` reads from `PlanRequest.context` (which is `Optional[SessionSnapshot]`). PlannerAgent calls `adapter.bind(request.context)` before each pipeline run.

- Planner's `IStateReadPort`: single method `async read_sections(sections: List[str], trace_id: str = "") -> SessionSnapshot`
- `PlanRequest.context: Optional[SessionSnapshot]` at `k1/orchestrator/types.py` L811
- `SessionSnapshot` at `k1/fabric/ports/state_reader.py` L48 — frozen dataclass with `session_id`, `sections`, `timestamp_ms`, `section_names`, `has_section()`, `get_section()`
- **NOTE:** `SessionSnapshot.empty()` and `SessionSnapshot.filter()` do NOT exist in codebase. Must use `SessionSnapshot()` (default empty) and filter manually.

---

## KEY INSIGHT: 5 ADAPTERS, 3 PROTOCOLS

| Adapter | Protocol it satisfies | Lines | Source Gap |
|---------|----------------------|-------|------------|
| `NullSessionStateReaderAdapter` | `ISessionStateReader` (Fabric) | ~15 | SIM-GAP-47 |
| `NullDeltaBusAdapter` | `IDeltaBusPort` (Fabric) | ~8 | SIM-GAP-47 |
| `NullEventSubscriptionAdapter` | `IEventSubscriptionPort` (Orchestrator) | ~20 | SIM-GAP-51 |
| `NullBridgeWriteAdapter` | `IBridgeWritePort` (Orchestrator) | ~25 | SIM-GAP-47 implied |
| `SnapshotStateReadAdapter` | `IStateReadPort` (Planner) | ~25 | SIM-D-38 |

**Wait — the simulation also references `IBridgeWritePort`.** OrchestratorService constructor requires `bridge_port: IBridgeWritePort`. At startup tier, Bridge may not be connected (SIM-D-33: `bridge_client = None` → each adapter has built-in offline fallback). We need a `NullBridgeWriteAdapter` for the Orchestrator startup tier.

`IBridgeWritePort` Protocol at `k1/orchestrator/ports/bridge_write_port.py` L47:

- `async submit_audit(run_manifest, trace_id) -> None`
- `async write_wal(dag_id, entry_type, payload, trace_id) -> None`
- `async read_wal(dag_id) -> Optional[List[Dict]]`
- `async list_wal_ids() -> List[str]`
- `async submit_deferred_result(result, workflow_id, trace_id) -> None`

All fire-and-forget except `read_wal` and `list_wal_ids`. Null adapter returns empty for reads, no-ops for writes.

---

## WHAT ALREADY EXISTS (no work needed)

| Component | Exists? | Location | Notes |
|-----------|---------|----------|-------|
| `TestSessionStateReaderAdapter` | YES | `k1/fabric/adapters/test_state_reader.py` | Full test adapter with load/query. Overkill for null. |
| `TestDeltaBusAdapter` | YES | `k1/fabric/adapters/test_delta_bus.py` | Full capture adapter. Overkill for null. |
| `LocalEventAdapter` | YES | `k1/fabric/adapters/local_event.py` | In-memory event bus. Works for shared Fabric IEventPort. |
| `SessionSnapshot` | YES | `k1/fabric/ports/state_reader.py` L48 | Frozen dataclass. `SessionSnapshot()` = empty. |
| `PlanRequest.context` | YES | `k1/orchestrator/types.py` L811 | `Optional[SessionSnapshot]`. Already populated by Orchestrator. |
| `FabricDispatchAdapter` | YES | `k1/concierge/adapters/fabric_dispatch.py` | Phase 1 adapter. Wraps IFabricPort + OrchestratorStub. |

---

## MILESTONE: `C2-prep — P0 Adapters for Two-Tier Bootstrap`

**Acceptance criteria:**

1. 5 null/snapshot adapters implemented
2. Each adapter satisfies its Protocol (isinstance checks pass)
3. Each adapter's no-op/fallback behaviour tested
4. Zero modifications to any existing file
5. All existing tests still pass
6. Adapters importable without triggering heavy dependency chains

---

## EPIC 1: Null Adapters for Shared Fabric

### Issue 1.1: Create `k1/concierge/adapters/null_state_reader.py` — NullSessionStateReaderAdapter

Satisfies `ISessionStateReader` from `k1.fabric.ports.state_reader`.

```python
class NullSessionStateReaderAdapter:
    """Null ISessionStateReader for shared Fabric (startup tier).

    All reads return empty. No session state available at startup.
    Used by shared Fabric (SIM-D-34/D-35) when Orchestrator/Planner
    execute capabilities without session context.
    """

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        return None

    def read_sections(self, session_id: str, names: List[str]) -> Dict[str, Any]:
        return {}

    def get_snapshot(self, session_id: str) -> SessionSnapshot:
        return SessionSnapshot(session_id=session_id)
```

~15 lines. Imports only from `k1.fabric.ports.state_reader`.

### Issue 1.2: Create `k1/concierge/adapters/null_delta_bus.py` — NullDeltaBusAdapter

Satisfies `IDeltaBusPort` from `k1.fabric.ports.delta_bus`.

```python
class NullDeltaBusAdapter:
    """Null IDeltaBusPort for shared Fabric (startup tier).

    Silently drops all deltas. No bus routing at startup tier.
    """

    def emit_delta(
        self, agent_id: str, delta_type: str, section: str, data: Dict[str, Any]
    ) -> None:
        pass  # Silent drop
```

~8 lines. Imports nothing external.

---

## EPIC 2: Null Adapters for Shared Orchestrator

### Issue 2.1: Create `k1/concierge/adapters/null_event_subscription.py` — NullEventSubscriptionAdapter

Satisfies `IEventSubscriptionPort` from `k1.orchestrator.ports.event_subscription_port`.

```python
class NullEventSubscriptionAdapter:
    """Null IEventSubscriptionPort for shared Orchestrator (startup tier).

    Absorbs all emit() calls. Returns dummy handles from subscribe().
    Does not route events. Startup tier has no event consumers.
    """

    def subscribe(self, topic: str, handler: Callable) -> SubscriptionHandle:
        return SubscriptionHandle(subscription_id="null", topic=topic)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        return False  # Nothing to remove

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        pass  # Silent drop
```

~20 lines. Imports `SubscriptionHandle` from `k1.fabric.ports.event_port` (shared type).

### Issue 2.2: Create `k1/concierge/adapters/null_bridge_write.py` — NullBridgeWriteAdapter

Satisfies `IBridgeWritePort` from `k1.orchestrator.ports.bridge_write_port`.

```python
class NullBridgeWriteAdapter:
    """Null IBridgeWritePort for shared Orchestrator when Bridge is offline.

    All writes are silently dropped. Reads return empty.
    Matches SIM-D-33: bridge_client = None → offline fallback.
    """

    async def submit_audit(self, run_manifest: Dict, trace_id: str) -> None:
        pass

    async def write_wal(self, dag_id: str, entry_type: str, payload: Dict, trace_id: str) -> None:
        pass

    async def read_wal(self, dag_id: str) -> Optional[List[Dict]]:
        return None

    async def list_wal_ids(self) -> List[str]:
        return []

    async def submit_deferred_result(self, result: Dict, workflow_id: str, trace_id: str) -> None:
        pass
```

~25 lines. No external imports beyond typing.

---

## EPIC 3: Snapshot Adapter for Shared Planner

### Issue 3.1: Create `k1/concierge/adapters/snapshot_state_read.py` — SnapshotStateReadAdapter

Satisfies `IStateReadPort` from `k1.planner.ports.state_read_port`.

```python
class SnapshotStateReadAdapter:
    """IStateReadPort that reads from a bound SessionSnapshot.

    Shared Planner (SIM-D-25) serves ALL sessions. The real
    SessionStateReadAdapter is session-locked at construction (SIM-GAP-49).

    Fix (SIM-D-38): Before each pipeline run, PlannerAgent calls
    adapter.bind(request.context) to set the active snapshot.
    read_sections() then returns filtered sections from that snapshot.
    """

    def __init__(self) -> None:
        self._snapshot: Optional[SessionSnapshot] = None

    def bind(self, snapshot: Optional[SessionSnapshot]) -> None:
        """Set the active snapshot. Called before each pipeline run."""
        self._snapshot = snapshot

    async def read_sections(
        self, sections: List[str], trace_id: str = ""
    ) -> SessionSnapshot:
        if self._snapshot is None:
            return SessionSnapshot()
        # Filter to requested sections only
        filtered = {
            name: data
            for name, data in self._snapshot.sections.items()
            if name in sections
        }
        return SessionSnapshot(
            session_id=self._snapshot.session_id,
            sections=filtered,
            timestamp_ms=self._snapshot.timestamp_ms,
        )
```

~25 lines. Imports from `k1.fabric.ports.state_reader` (SessionSnapshot).

**Critical detail:** `SessionSnapshot` is frozen (`@dataclass(frozen=True)`), so we construct a new one with filtered sections rather than mutating. The `sections` field is `Dict[str, Dict[str, Any]]` with `default_factory=dict`.

---

## EPIC 4: Unit Tests

### Issue 4.1: Create `tests/k1/concierge/adapters/test_null_state_reader.py`

```
test_satisfies_isessionstatereader          # isinstance check
test_read_section_returns_none              # always None
test_read_sections_returns_empty_dict       # always {}
test_get_snapshot_returns_empty_snapshot     # SessionSnapshot with session_id only
test_get_snapshot_preserves_session_id      # session_id passes through
```

### Issue 4.2: Create `tests/k1/concierge/adapters/test_null_delta_bus.py`

```
test_satisfies_ideltabusport               # isinstance check
test_emit_delta_does_not_raise             # silent no-op
test_emit_delta_accepts_any_args           # various arg combos don't crash
```

### Issue 4.3: Create `tests/k1/concierge/adapters/test_null_event_subscription.py`

```
test_satisfies_ieventsubscriptionport      # isinstance check
test_subscribe_returns_handle              # SubscriptionHandle with topic
test_unsubscribe_returns_false             # nothing to remove
test_emit_does_not_raise                   # silent no-op
test_emit_does_not_call_handler            # subscribe handler never invoked
```

### Issue 4.4: Create `tests/k1/concierge/adapters/test_null_bridge_write.py`

```
test_satisfies_ibridgewriteport            # isinstance check
test_submit_audit_no_op                    # async no-op
test_write_wal_no_op                       # async no-op
test_read_wal_returns_none                 # always None
test_list_wal_ids_returns_empty            # always []
test_submit_deferred_result_no_op          # async no-op
```

### Issue 4.5: Create `tests/k1/concierge/adapters/test_snapshot_state_read.py`

```
test_satisfies_istatereadport              # isinstance check (Planner version)
test_read_sections_unbound_returns_empty   # no bind() called → empty snapshot
test_bind_then_read_returns_filtered       # bind snapshot, read subset
test_bind_then_read_all_sections           # bind snapshot, read all
test_bind_preserves_session_id             # session_id passes through
test_bind_none_resets_to_empty             # bind(None) → empty reads
test_rebind_overwrites_previous            # second bind() replaces first
```

### Issue 4.6: Run regression gate

All existing tests must pass. Zero modifications to existing files.

---

## EXECUTION ORDER

```
Issue 1.1  →  null_state_reader.py (~15 lines)
Issue 1.2  →  null_delta_bus.py (~8 lines)
Issue 2.1  →  null_event_subscription.py (~20 lines)
Issue 2.2  →  null_bridge_write.py (~25 lines)
Issue 3.1  →  snapshot_state_read.py (~25 lines)
      ↓
Issue 4.1  →  test_null_state_reader.py (5 tests)
Issue 4.2  →  test_null_delta_bus.py (3 tests)
Issue 4.3  →  test_null_event_subscription.py (5 tests)
Issue 4.4  →  test_null_bridge_write.py (6 tests)
Issue 4.5  →  test_snapshot_state_read.py (7 tests)
      ↓
Issue 4.6  →  Regression gate
```

**Total: 4 epics, 11 issues, ~26 test cases, ~330 lines of new code, 0 existing file changes.**

---

## FILE TREE (Phase 2 deliverables)

```
k1/concierge/adapters/
├── null_state_reader.py              # NEW — NullSessionStateReaderAdapter (~15 lines)
├── null_delta_bus.py                 # NEW — NullDeltaBusAdapter (~8 lines)
├── null_event_subscription.py        # NEW — NullEventSubscriptionAdapter (~20 lines)
├── null_bridge_write.py              # NEW — NullBridgeWriteAdapter (~25 lines)
└── snapshot_state_read.py            # NEW — SnapshotStateReadAdapter (~25 lines)

tests/k1/concierge/adapters/
├── __init__.py
├── test_null_state_reader.py         # NEW — 5 tests
├── test_null_delta_bus.py            # NEW — 3 tests
├── test_null_event_subscription.py   # NEW — 5 tests
├── test_null_bridge_write.py         # NEW — 6 tests
└── test_snapshot_state_read.py       # NEW — 7 tests
```

**11 new files. 0 modified files. 0 deleted files. ~330 lines total.**

---

## WHY THESE 5 ADAPTERS ARE P0

The simulation's two-tier bootstrap (SIM-D-39) requires building shared components BEFORE any session exists. Each shared component has port dependencies that normally come from session-bound resources:

```
STARTUP TIER (shared, once):
  ┌─────────────────────────────────────────────────────────┐
  │  ModelHub        → no session deps (already standalone) │
  │  Shared Fabric   → needs ISessionStateReader + IDeltaBusPort + IEventPort  │
  │                    ↳ NullSessionStateReaderAdapter (Issue 1.1)              │
  │                    ↳ NullDeltaBusAdapter (Issue 1.2)                        │
  │                    ↳ LocalEventAdapter (ALREADY EXISTS)                     │
  │  Orchestrator    → needs IEventSubscriptionPort + IBridgeWritePort          │
  │                    ↳ NullEventSubscriptionAdapter (Issue 2.1)               │
  │                    ↳ NullBridgeWriteAdapter (Issue 2.2)                     │
  │  Planner         → needs IStateReadPort                                     │
  │                    ↳ SnapshotStateReadAdapter (Issue 3.1)                   │
  └─────────────────────────────────────────────────────────┘
                           ↓
SESSION TIER (per-session, on demand):
  ┌─────────────────────────────────────────────────────────┐
  │  Bus             → per-session, created fresh                               │
  │  SSM             → per-session, created fresh                               │
  │  Session Fabric  → real SessionStateReaderAdapter + real DeltaBusAdapter     │
  │  Concierge       → wired to all 8 ports (Phase 1)                          │
  └─────────────────────────────────────────────────────────┘
```

Without these 5 adapters, the startup tier constructor calls FAIL — you literally cannot call `FabricFactory.create_with_ports()` or `OrchestratorFactory.create_production()` because they require port instances that don't exist yet.

---

## RELATIONSHIP TO FabricDispatchAdapter (Phase 1)

Phase 1 already created `FabricDispatchAdapter` (`k1/concierge/adapters/fabric_dispatch.py`) which wraps IFabricPort + orchestrator into IDispatchPort. That adapter is the **Concierge's** dispatch boundary.

Phase 2's adapters are the **infrastructure's** null boundaries — they go inside shared Fabric/Orchestrator/Planner, NOT inside Concierge. But we store them in `k1/concierge/adapters/` because:

1. They're created BY the Concierge bootstrap (ConciergeFactory or KernelService)
2. They're Concierge-specific null implementations (the real adapters live in k1/fabric/adapters/ and k1/orchestrator/adapters/)
3. Co-location with Phase 1 adapters keeps all Concierge wiring adapters in one directory

---

## DECISIONS APPLIED

| SIM Decision | How it's applied |
|-------------|------------------|
| SIM-D-25 | Orchestrator + Planner are shared → need null adapters for session ports |
| SIM-D-33 | Bridge offline fallback → NullBridgeWriteAdapter |
| SIM-D-34 | Shared Fabric with NullStateReader → NullSessionStateReaderAdapter |
| SIM-D-35 | Two Fabric instances → null adapters for shared, real adapters for session |
| SIM-D-38 | SnapshotStateReadAdapter reads from PlanRequest.context |
| SIM-D-39 | Two-tier bootstrap → startup tier needs these adapters to construct |

## GAPS RESOLVED

| SIM Gap | Resolution |
|---------|------------|
| SIM-GAP-47 | NullSessionStateReaderAdapter + NullDeltaBusAdapter (Issues 1.1, 1.2) |
| SIM-GAP-49 | SnapshotStateReadAdapter (Issue 3.1) |
| SIM-GAP-51 | NullEventSubscriptionAdapter (Issue 2.1) |

---

# PHASE 3: CONCIERGE FACTORY — IMPLEMENTATION PLAN (v1 — CODE-GROUNDED)

> **Milestone:** ConciergeFactory skeleton — port-injected session wiring
> **Depends on:** Phase 1 (8 ports + 16 adapters) ✅, Phase 2 (5 null adapters) ✅
> **Delivers:** `ConciergeFactory.create_session()` that wires a ConciergeController + all subsystems using injected ports, replacing the monolithic `start_kernel()`.

## AUDIT SUMMARY — What the Code Actually Does

### Current Bootstrap (`k1/concierge/kernel/bootstrap.py`) — 1050+ lines

The monolithic `start_kernel()` does everything inline with zero port injection:

```
start_kernel(config) → KernelRuntime
  1. boot()                      → bus, router, adapter, front_mailbox, back_mailbox
  2. _create_model(cfg)          → IModelHubPort (TestModelHubBridge or ModelHubPOCBridge)
  3. _create_session_state(cfg)  → SessionStateManager
  4. _create_capability_registry() → CapabilityRegistry
  5. _create_fabric(registry)    → Fabric (real K1 Fabric with POC mock handlers)
  6. Create LedgerWriter + InMemoryLedgerStore (optional)
  7. ConciergeController(bus=bus, router=router)       ← FSM constructor
  8. Wire Phase1 pipeline into FSM: fsm._phase1_pipeline = UltraBERTPhase1Pipeline(...)
  9. fsm.set_ledger(_ledger_writer)
  10. fsm.set_history_sink(session_state.get_section("history_active"))
  11. fsm.set_session_state(session_state)
  12. Create recall_fn via _build_recall_fn(cfg)
  13. Create ToolContext (front + back) with session_manager, recall_fn, fabric_port, writer_port
  14. create_front_dispatcher(tier, ctx, bus) + create_back_dispatcher(tier, ctx, bus)
  15. Build KernelRuntime dataclass
  16. ExperienceLayer() (optional)
  17. DeltaAggregator + _build_delta_applicator(ss, bus) (optional)
  18. HILCoordinator with 3 callbacks (on_suspended, on_resume, on_timeout) (optional)
  19. fsm.set_hitl_coordinator(coordinator)
  20. WeaveBatcher + fsm.set_weave_batcher(batcher)
  21. WeavePolicy + UserActivityTracker + fsm.set_weave_policy/set_activity_tracker
  22. DeadLetterConsumer(bus=bus) (optional)
  23. OrchestratorStub(fabric_gateway=_FabricGatewayAdapter, state_read=_StateReadAdapter, delta_emit=_DeltaEmitAdapter)
  24. fsm.set_orchestrator(orchestrator)
  25. subscribe_front_events(bus, route_fn)
  26. asyncio.create_task(_mailbox_consumer(runtime))
```

### ConciergeController Constructor (`k1/concierge/fsm/controller.py`)

```python
ConciergeController.__init__(self, bus: IBus, router: IMailboxRouter) -> None
```

Takes ONLY bus + router. Everything else is wired via setters:

- `fsm._phase1_pipeline = ...`     (direct attribute set)
- `fsm.set_ledger(writer)`
- `fsm.set_history_sink(section)`
- `fsm.set_session_state(ss)`
- `fsm.set_orchestrator(orch)`
- `fsm.set_hitl_coordinator(coord)`
- `fsm.set_weave_batcher(batcher)`
- `fsm.set_weave_policy(policy)`
- `fsm.set_activity_tracker(tracker)`

Internally creates: FrontLock, CancelHandler, SuspensionManager, ControlExtension, TaskBridge, StubPhase1Pipeline, TurnLock, InterruptClassifier, ConversationArbiter, ProactiveWakeHandler, IdempotencyLedger, WeaveFallbackHandler.

Calls `_subscribe_all()` which subscribes to 20 bus topics.

### Private Adapters to Retire (3 classes, ~80 lines)

The current bootstrap defines 3 private adapter classes that bridge between subsystems:

1. **`_FabricGatewayAdapter`** (line 896) — Wraps FabricPOCBridge for OrchestratorStub. Translates POC CapabilityRequest → K1 CapabilityRequest → bridge.execute() → POC CapabilityResult.
2. **`_StateReadAdapter`** (line 944) — Wraps SessionStateManager for OrchestratorStub. Implements `snapshot(sections)` and `read_section(session_id, section)`.
3. **`_DeltaEmitAdapter`** (defined somewhere below) — Wraps DeltaAggregator + bus for OrchestratorStub delta emission.

These will be replaced by proper adapters in the factory (or reused as-is if trivial).

### POC Bootstrap (`poc/k1_poc/kernel/bootstrap.py`) — Mirror

Near-identical to production bootstrap. Key difference: uses `FabricPOCBridge(capability_registry)` directly instead of `_create_fabric()` which calls `FabricFactory.create_with_ports()`.

### Actor Signatures (what the consumer passes)

```python
# Front handler:
await front_handler(
    envelope=front_env,
    model=runtime.model,                    # IModelHubPort — our ILLMPort
    ss=runtime.session_state,               # SessionStateManager — our IStatePort
    bus=runtime.bus,                         # IBus — our IDeltaPort
    tool_dispatcher=runtime.front_dispatcher, # ToolDispatcher
    all_tool_schemas=FRONT_TOOL_SCHEMAS,
    fsm_state=runtime.fsm.state.name,
)

# Back handler (via route_back_envelope):
await route_back_envelope(
    envelope=back_env,
    model=runtime.model,                    # IModelHubPort
    ss=runtime.session_state,               # SessionStateManager
    bus=runtime.bus,                         # IBus
    tool_dispatcher=runtime.back_dispatcher, # ToolDispatcher
    fsm_state=runtime.fsm,                  # ConciergeController itself (not state name)
)
```

### OrchestratorStub — Exactly 3 Ports

```python
OrchestratorStub(
    fabric_gateway: IFabricGatewayPort,  # execute(CapabilityRequest) → CapabilityResult
    state_read: IStateReadPort,          # snapshot(sections) → dict
    delta_emit: IDeltaEmitPort,          # emit(delta) → None
)
```

---

## DESIGN DECISIONS FOR PHASE 3

### D-FACTORY-01: Factory is a plain class, NOT async

`ConciergeFactory` is a regular class. `create_session()` is a regular method that returns a `ConciergeSession` synchronously. The only async part is the mailbox consumer task, which is created lazily on `session.start()`.

**Rationale:** The current `start_kernel()` is async only because of `asyncio.create_task()` at the end. All actual wiring is synchronous. Separating creation from starting matches SIM-D-09 (ConciergeSession lifecycle).

### D-FACTORY-02: Factory does NOT create Bus, SSM, Fabric, ModelHub, Orchestrator

The factory receives already-created shared components as constructor args. It only wires the Concierge-specific subsystem graph (FSM, actors, tools, experience, delta, HITL, weave).

**Rationale:** SIM-D-39 two-tier bootstrap — Bus/SSM/Fabric/ModelHub/Orchestrator are created by the startup tier (KernelService). The factory is the SESSION tier — it receives them and wires Concierge.

### D-FACTORY-03: Factory accepts 8 Concierge ports as `create_session()` kwargs

```python
factory.create_session(
    input_port: IInputPort,           # bus → FSM user input relay
    output_port: IOutputPort,         # front → bus output emission
    classification_port: IClassificationPort,  # Phase1Pipeline
    llm_port: ILLMPort,              # IModelHubPort
    state_port: IStatePort,          # SessionStateManager
    dispatch_port: IDispatchPort,    # IFabricPort + orchestrator
    delta_port: IDeltaPort,          # IBus
    memory_port: IMemoryPort,        # recall_fn wrapper
) -> ConciergeSession
```

Internal dependencies (Bus, Router, Orchestrator, etc.) are passed to the factory constructor. The 8 ports are passed to `create_session()` because they're per-session.

### D-FACTORY-04: ConciergeSession wraps KernelRuntime lifecycle

`ConciergeSession` replaces the raw `KernelRuntime` dataclass. It exposes:

- `start()` → begins mailbox consumer
- `stop()` → cancels consumer, flushes delta, tears down FSM
- `inject(envelope)` → publishes to bus (the "Hello World" entry point)
- `state` → current FSM state
- Properties for all internal components (for testing)

### D-FACTORY-05: Wire existing subsystems, do NOT rewrite them

The factory calls the exact same setter methods the current bootstrap uses. No FSM changes. No actor changes. The factory is a thin wiring layer.

```python
# Factory wiring sequence (mirrors start_kernel steps 7-26):
fsm = ConciergeController(bus=bus, router=router)
fsm._phase1_pipeline = classification_port   # IClassificationPort IS Phase1Pipeline
fsm.set_ledger(ledger)
fsm.set_history_sink(state_port.get_section("history_active"))
fsm.set_session_state(state_port)            # IStatePort IS SessionStateManager
# ... etc
```

### D-FACTORY-06: Private adapters stay as private helpers (for now)

`_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter` are ~80 lines total. Phase 3 keeps them as private classes inside `factory.py`. Phase 4+ may promote them to proper adapters if reuse warrants it.

**Rationale:** Don't over-engineer. These adapt between Concierge internal types and orchestrator port types. They're implementation details of the factory.

---

## MILESTONE: `C3 — ConciergeFactory Skeleton`

**Definition of Done:**

1. `ConciergeFactory` class exists at `k1/concierge/factory.py`
2. `ConciergeSession` class exists at `k1/concierge/session.py`
3. `create_session()` accepts 8 ports + wires all subsystems
4. `ConciergeSession.start()` / `stop()` / `inject()` work
5. "Hello World" smoke test: factory creates session → inject user input → FSM transitions to FRONT_BUSY → output appears on bus
6. All existing tests still pass (zero regression)

---

## EPIC 1: ConciergeSession Wrapper

### Issue 1.1: Create `k1/concierge/session.py` — ConciergeSession class

**File:** `k1/concierge/session.py` (NEW, ~120 lines)

```python
class ConciergeSession:
    """Lifecycle wrapper for a single Concierge session.

    Owns: FSM, mailbox consumer, subscriptions, runtime teardown.
    Created by ConciergeFactory.create_session().
    """

    def __init__(
        self,
        *,
        bus: IBus,
        router: IMailboxRouter,
        front_mailbox: IMailbox,
        back_mailbox: IMailbox,
        fsm: ConciergeController,
        model: IModelHubPort,            # = ILLMPort
        session_state: Any,              # = IStatePort
        front_dispatcher: ToolDispatcher,
        back_dispatcher: ToolDispatcher,
        front_subscriptions: list[Any],
        experience_layer: Any | None,
        delta_aggregator: Any | None,
        hitl_coordinator: Any | None,
        orchestrator: Any | None,
        ledger: Any | None,
        dead_letter_consumer: Any | None,
    ):
        ...

    async def start(self) -> None:
        """Start the mailbox consumer task."""
        ...

    async def stop(self) -> None:
        """Stop consumer, flush delta, teardown FSM, close SS."""
        ...

    def inject(self, envelope: Envelope) -> None:
        """Publish an envelope to the session bus (entry point for user input)."""
        self._bus.publish(envelope)

    @property
    def state(self) -> str:
        """Current FSM state name."""
        return self._fsm.state.name

    @property
    def fsm(self) -> ConciergeController:
        return self._fsm
```

**Grounded in:** `KernelRuntime` dataclass (bootstrap.py lines 94-115) — same fields, but with lifecycle methods instead of bare `started: bool`. `stop_kernel()` logic (bootstrap.py lines 373-420) moves into `session.stop()`.

**Tests:** 5 tests in Issue 3.1.

### Issue 1.2: `start()` and `stop()` lifecycle

`start()` creates `asyncio.create_task(_mailbox_consumer(...))` — exact same logic as bootstrap.py line 362.

`stop()` is a direct extraction of `stop_kernel()` (bootstrap.py lines 373-420):

1. Cancel consumer task
2. Flush ledger
3. Log dead-letter summary
4. Flush delta aggregator
5. FSM teardown (unsubscribes all bus handles)
6. Close session state
7. Close model

**Tests:** Covered by Issue 3.1 lifecycle tests.

---

## EPIC 2: ConciergeFactory

### Issue 2.1: Create `k1/concierge/factory.py` — ConciergeFactory class

**File:** `k1/concierge/factory.py` (NEW, ~250 lines)

```python
class ConciergeFactory:
    """Factory that wires a ConciergeSession from injected ports.

    The factory is the SESSION TIER of the two-tier bootstrap (SIM-D-39).
    It receives shared components (Bus infrastructure, ModelHub, Fabric,
    Orchestrator) from the STARTUP TIER and wires the Concierge-specific
    subsystem graph using 8 hexagonal ports.
    """

    def __init__(
        self,
        *,
        # Infrastructure (from startup tier)
        bus: IBus,
        router: IMailboxRouter,
        front_mailbox: IMailbox,
        back_mailbox: IMailbox,
        # Config
        config: KernelConfig | None = None,
    ):
        self._bus = bus
        self._router = router
        self._front_mailbox = front_mailbox
        self._back_mailbox = back_mailbox
        self._config = config or KernelConfig()

    def create_session(
        self,
        *,
        input_port: IInputPort,
        output_port: IOutputPort,
        classification_port: IClassificationPort,
        llm_port: ILLMPort,
        state_port: IStatePort,
        dispatch_port: IDispatchPort,
        delta_port: IDeltaPort,
        memory_port: IMemoryPort,
    ) -> ConciergeSession:
        """Wire all Concierge subsystems and return a ConciergeSession.

        Wiring sequence (mirrors start_kernel steps 7-26):
        1. Create ConciergeController(bus, router)
        2. Wire Phase1 pipeline: fsm._phase1_pipeline = classification_port
        3. Wire ledger (if enabled)
        4. Wire history sink from state_port
        5. Wire session state: fsm.set_session_state(state_port)
        6. Build recall_fn from memory_port
        7. Create ToolContext (front + back)
        8. Create ToolDispatchers (front + back)
        9. Wire ExperienceLayer (if enabled)
        10. Wire DeltaAggregator + applicator (if enabled)
        11. Wire HILCoordinator (if enabled)
        12. Wire WeaveBatcher + WeavePolicy + ActivityTracker
        13. Wire DeadLetterConsumer (if enabled)
        14. Wire OrchestratorStub from dispatch_port internals
        15. Subscribe front events
        16. Return ConciergeSession
        """
        ...
```

**Grounded in:** `start_kernel()` (bootstrap.py lines 117-370). The 26-step sequence is a direct extraction. Each step maps to existing code that currently lives inline in `start_kernel()`.

### Issue 2.2: Wiring Step 1-5 — FSM creation and core wiring

Direct extraction from bootstrap.py:

```python
fsm = ConciergeController(bus=self._bus, router=self._router)

# Step 2: Phase1 pipeline — IClassificationPort IS Phase1Pipeline
# The FSM stores it as _phase1_pipeline. classification_port satisfies
# the Phase1Pipeline protocol (method: classify(text) → Phase1Result).
fsm._phase1_pipeline = classification_port

# Step 3: Ledger (conditional on config)
if self._config.enable_ledger:
    from k1.concierge.ledger.store import InMemoryLedgerStore
    from k1.concierge.ledger.writer import LedgerWriter
    session_id = self._config.session_id or f"k-{uuid.uuid4().hex[:8]}"
    ledger_store = InMemoryLedgerStore()
    ledger = LedgerWriter(store=ledger_store, session_id=session_id)
    fsm.set_ledger(ledger)

# Step 4: History sink from state_port
try:
    history_section = state_port.get_section("history_active")
    if history_section and hasattr(history_section, "add_turn"):
        fsm.set_history_sink(history_section)
except Exception:
    pass

# Step 5: Session state binding (M4 E4.1 rebinding)
fsm.set_session_state(state_port)
```

**Source lines:** bootstrap.py 149-188.

### Issue 2.3: Wiring Step 6-8 — Memory, ToolContext, Dispatchers

```python
# Step 6: recall_fn from memory_port
# IMemoryPort.recall(query, max_results) → list[dict]
# The current _build_recall_fn creates a closure. We wrap memory_port instead.
recall_fn = memory_port.recall

# Step 7: ToolContext for front + back
# Grounded in bootstrap.py lines 197-213
writer_port = getattr(state_port, "_writer_port", None)
front_ctx = ToolContext(
    session_manager=state_port,
    cognitive_trace_id=f"k-front-{uuid.uuid4().hex[:6]}",
    actor="front",
    recall_fn=recall_fn,
    fabric_port=dispatch_port,    # IDispatchPort wraps Fabric
    writer_port=writer_port,
)
back_ctx = ToolContext(
    session_manager=state_port,
    cognitive_trace_id=f"k-back-{uuid.uuid4().hex[:6]}",
    actor="back",
    recall_fn=recall_fn,
    fabric_port=dispatch_port,
    writer_port=writer_port,
)

# Step 8: Dispatchers
front_dispatcher = create_front_dispatcher(tier=self._config.tool_tier, ctx=front_ctx, bus=self._bus)
back_dispatcher = create_back_dispatcher(tier=self._config.tool_tier, ctx=back_ctx, bus=self._bus)
```

**Source lines:** bootstrap.py 190-218.

**NOTE:** `ToolContext.fabric_port` currently takes `Any`. The `dispatch_port: IDispatchPort` may need an unwrap to get the underlying Fabric instance. The current bootstrap passes the raw Fabric instance (or FabricPOCBridge). Phase 3 implementation must verify what ToolContext.fabric_port actually calls. If it calls `.execute(CapabilityRequest)`, then `IDispatchPort` (which has `.execute_task()` returning `AggregatedResult`) is NOT the right type — we'd pass the Fabric directly via `dispatch_port.fabric` or similar accessor.

**OPEN QUESTION (SIM-FLAG-P3-01):** Does `ToolContext.fabric_port` call Fabric's `.execute()` or the orchestrator's `.execute()`? Must verify before implementing. If it calls Fabric directly, the factory needs both `dispatch_port` AND the raw Fabric instance.

### Issue 2.4: Wiring Step 9-13 — Optional subsystems

Direct extraction from bootstrap.py lines 232-340:

```python
# Step 9: ExperienceLayer
experience = ExperienceLayer() if self._config.enable_experience else None

# Step 10: Delta
delta_aggregator = None
if self._config.enable_delta:
    applicator = _build_delta_applicator(state_port, self._bus)
    delta_aggregator = DeltaAggregator(
        flush_fn=applicator.apply,
        batch_window_ms=get_config().delta.batch_window_ms,
    )

# Step 11: HITL
hitl = None
if self._config.enable_hitl:
    hitl = HILCoordinator(
        on_emit_suspended=_make_suspended_cb(self._bus),
        on_emit_resume=_make_resume_cb(self._bus),
        on_timeout=_make_timeout_cb(self._bus),
    )
    fsm.set_hitl_coordinator(hitl)

# Step 12: Weave
if hasattr(fsm, "set_weave_batcher"):
    batcher = WeaveBatcher(flush_fn=_weave_flush)
    fsm.set_weave_batcher(batcher)
if hasattr(fsm, "set_weave_policy"):
    fsm.set_weave_policy(WeavePolicy())
if hasattr(fsm, "set_activity_tracker"):
    fsm.set_activity_tracker(UserActivityTracker())

# Step 13: Dead letter
dead_letter = None
if self._config.enable_dead_letter_consumer:
    if get_config().fsm.dead_letter_enabled:
        dead_letter = DeadLetterConsumer(bus=self._bus)
```

### Issue 2.5: Wiring Step 14 — Orchestrator wiring from dispatch_port

The current bootstrap creates OrchestratorStub with 3 private adapters. The factory must either:

**Option A:** Extract orchestrator from `dispatch_port` (if IDispatchPort wraps orchestrator)
**Option B:** Accept orchestrator as a separate constructor argument

Per Phase 1 design, `FabricDispatchAdapter` wraps `IFabricPort + orchestrator` into `IDispatchPort`. So the factory can do:

```python
# dispatch_port is FabricDispatchAdapter which holds ._fabric and ._orchestrator
# But we need the orchestrator instance for fsm.set_orchestrator()
if hasattr(dispatch_port, '_orchestrator') and dispatch_port._orchestrator is not None:
    fsm.set_orchestrator(dispatch_port._orchestrator)
```

**OPEN QUESTION (SIM-FLAG-P3-02):** This reaches into private attrs. Better option: add `orchestrator` property to `IDispatchPort` or pass orchestrator separately to factory. Decision deferred to implementation.

### Issue 2.6: Wiring Step 15-16 — Subscriptions and return

```python
# Step 15: Subscribe front events
def _route_front(envelope):
    self._router.deliver("front_half", envelope)

front_subs = subscribe_front_events(self._bus, _route_front)

# Step 16: Return ConciergeSession
return ConciergeSession(
    bus=self._bus,
    router=self._router,
    front_mailbox=self._front_mailbox,
    back_mailbox=self._back_mailbox,
    fsm=fsm,
    model=llm_port,
    session_state=state_port,
    front_dispatcher=front_dispatcher,
    back_dispatcher=back_dispatcher,
    front_subscriptions=front_subs,
    experience_layer=experience,
    delta_aggregator=delta_aggregator,
    hitl_coordinator=hitl,
    orchestrator=orchestrator,
    ledger=ledger,
    dead_letter_consumer=dead_letter,
)
```

**Source lines:** bootstrap.py 350-370.

### Issue 2.7: HITL callback helpers (private functions)

Extract the 3 HITL callbacks from `start_kernel()` (bootstrap.py lines 270-310) into module-level private functions:

```python
def _make_suspended_cb(bus: IBus):
    async def _on_suspended(request): ...
    return _on_suspended

def _make_resume_cb(bus: IBus):
    async def _on_resume(response): ...
    return _on_resume

def _make_timeout_cb(bus: IBus):
    async def _on_timeout(task_id: str): ...
    return _on_timeout
```

---

## EPIC 3: Smoke Tests

### Issue 3.1: ConciergeSession lifecycle tests

**File:** `tests/k1/concierge/test_session.py` (NEW, ~80 lines)

```python
# Test 1: ConciergeSession can be constructed
# Test 2: session.state starts as "LISTENING"
# Test 3: session.start() creates consumer task
# Test 4: session.stop() cancels consumer and tears down FSM
# Test 5: session.inject(envelope) publishes to bus
```

**Dependencies:** TestInputAdapter, TestOutputAdapter, TestStateAdapter, etc. from Phase 1.

### Issue 3.2: ConciergeFactory.create_session() smoke test

**File:** `tests/k1/concierge/test_factory.py` (NEW, ~100 lines)

```python
# Test 1: Factory creates a ConciergeSession with all 8 test adapters
# Test 2: Created session FSM is in LISTENING state
# Test 3: Created session has all subsystem references populated
# Test 4: Factory with real config (enable_* flags) wires optional subsystems
# Test 5: Factory with all optional subsystems disabled still creates valid session
```

### Issue 3.3: "Hello World" end-to-end test (SIM Step 10.15)

**File:** `tests/k1/concierge/test_factory_e2e.py` (NEW, ~60 lines)

The canonical smoke test from the simulation:

```python
async def test_hello_world_factory():
    """SIM Step 10.15: Factory creates session, user input triggers FSM transition."""
    # Arrange
    bus = BusFactory.create_local(capture=True)
    router = BusFactory.create_mailbox_router(backend="python")
    front_mb, back_mb = _register_actors(router)

    factory = ConciergeFactory(
        bus=bus, router=router,
        front_mailbox=front_mb, back_mailbox=back_mb,
        config=KernelConfig(test_mode=True, auto_start_consumer=False),
    )

    session = factory.create_session(
        input_port=TestInputAdapter(bus),
        output_port=TestOutputAdapter(bus),
        classification_port=StubPhase1Pipeline(),
        llm_port=TestModelHubBridge(),
        state_port=SessionStateFactory.create_for_testing(),
        dispatch_port=TestDispatchAdapter(),
        delta_port=bus,
        memory_port=TestMemoryAdapter(),
    )

    # Act
    from k1.concierge.bus.builders import build_user_input
    envelope = build_user_input(payload={"text": "Hello, world!"})
    session.inject(envelope)

    # Assert
    assert session.state != "LISTENING"  # FSM transitioned
    assert len(bus.captured) > 0         # Something was published
```

**Grounded in:** SIM Step 10.15 ("Hello World" test), POC runner.py pattern.

### Issue 3.4: Regression guard — existing tests still pass

Run full test suite after implementation. Zero regression is mandatory.

```bash
pytest tests/k1/concierge/ -x -q
```

---

## EPIC 4: _build_delta_applicator extraction

### Issue 4.1: Extract `_build_delta_applicator` into reusable helper

The function `_build_delta_applicator(session_state, bus)` at bootstrap.py line ~980 is ~60 lines. It builds closures for `_preflight`, `_write`, `_notify`. The factory needs this same logic.

**Options:**

- **A:** Import directly from `k1.concierge.kernel.bootstrap` (creates coupling to old module)
- **B:** Move to `k1.concierge.delta.applicator_factory` (clean but new file)
- **C:** Copy into `factory.py` as private function (duplicate but self-contained)

**Decision:** Option A for Phase 3 (import from bootstrap). Phase 4+ can extract if needed. The bootstrap isn't going away immediately — it's still the STARTUP TIER entry point.

---

## FILE TREE (Phase 3 deliverables)

```
k1/concierge/
├── factory.py                        # NEW — ConciergeFactory (~250 lines)
├── session.py                        # NEW — ConciergeSession (~120 lines)

tests/k1/concierge/
├── test_session.py                   # NEW — 5 lifecycle tests
├── test_factory.py                   # NEW — 5 factory tests
├── test_factory_e2e.py               # NEW — 1-2 e2e tests ("Hello World")
```

**2 new source files. 3 new test files. 0 modified files. ~640 lines total.**

---

## WIRING DEPENDENCY GRAPH

```
ConciergeFactory
  ├── constructor: bus, router, front_mailbox, back_mailbox, config
  └── create_session():
        ├── input_port: IInputPort ──────────────── (Phase 1: TestInputAdapter / BusInputAdapter)
        ├── output_port: IOutputPort ────────────── (Phase 1: TestOutputAdapter / BusOutputAdapter)
        ├── classification_port: IClassificationPort (Phase 1: StubPhase1Pipeline / UltraBERTPhase1Pipeline)
        ├── llm_port: ILLMPort ──────────────────── (Phase 1: TestModelHubBridge / ModelHubPOCBridge)
        ├── state_port: IStatePort ──────────────── (Phase 1: TestStateAdapter / SSMStateAdapter)
        ├── dispatch_port: IDispatchPort ────────── (Phase 1: TestDispatchAdapter / FabricDispatchAdapter)
        ├── delta_port: IDeltaPort ──────────────── (Phase 1: TestDeltaAdapter / bus)
        └── memory_port: IMemoryPort ────────────── (Phase 1: TestMemoryAdapter / RecallMemoryAdapter)
                │
                ▼
        ConciergeSession
          ├── fsm: ConciergeController(bus, router)
          ├── front_dispatcher: ToolDispatcher
          ├── back_dispatcher: ToolDispatcher
          ├── experience_layer: ExperienceLayer | None
          ├── delta_aggregator: DeltaAggregator | None
          ├── hitl_coordinator: HILCoordinator | None
          ├── orchestrator: OrchestratorStub | None
          ├── ledger: LedgerWriter | None
          └── dead_letter_consumer: DeadLetterConsumer | None
```

---

## OPEN FLAGS (must resolve during implementation)

| Flag | Question | Impact |
|------|----------|--------|
| SIM-FLAG-P3-01 | Does `ToolContext.fabric_port` call Fabric `.execute()` or orchestrator? | Determines whether factory passes dispatch_port or raw Fabric to ToolContext |
| SIM-FLAG-P3-02 | How to expose orchestrator from IDispatchPort? Property vs separate arg? | Affects factory constructor signature |
| SIM-FLAG-P3-03 | Should `_mailbox_consumer` live in session.py or be imported from bootstrap? | Extraction boundary question |
| SIM-FLAG-P3-04 | Does the factory need the `_build_recall_fn` closure or can it use `memory_port.recall` directly? | IMemoryPort.recall signature must match what ToolContext expects |

---

## DECISIONS APPLIED

| SIM Decision | How it's applied |
|-------------|------------------|
| SIM-D-01 | Per-session Bus → factory receives bus as constructor arg |
| SIM-D-02 | KernelService + SessionInstance → factory IS the session-tier creator |
| SIM-D-09 | ConciergeSession wrapper → Epic 1 (session.py) |
| SIM-D-10 | 26-step wiring sequence → Epic 2 mirrors all 26 steps |
| SIM-D-17 | SSM IS IStatePort → state_port passed directly to fsm.set_session_state() |
| SIM-D-20 | Fabric IS IFabricPort → dispatch_port wraps Fabric |
| SIM-D-39 | Two-tier bootstrap → factory is session tier, receives startup tier output |
| SIM-D-41 | Accept bus-based I/O → FSM still subscribes to bus topics, no FSM changes |

## GAPS ADDRESSED

| SIM Gap | How Phase 3 addresses it |
|---------|--------------------------|
| SIM-GAP-01 | ConciergeFactory replaces monolithic start_kernel for session creation |
| SIM-GAP-02 | ConciergeSession provides lifecycle (start/stop) with proper teardown |
| SIM-GAP-15 | Port injection enables testing with any adapter combination |

## RELATIONSHIP TO PHASE 4+

Phase 3 delivers the **skeleton** — it wires everything the current bootstrap wires, but through ports. Phase 4+ will:

- **Phase 4:** Replace `from poc.k1_poc.main import boot` with real Bus factory in startup tier
- **Phase 5:** Build KernelService (startup tier) that creates shared components + calls ConciergeFactory
- **Phase 6:** Wire Bridge adapters for K0 integration
- **Phase 7:** Wire production ModelHub, Fabric, Orchestrator
- **Phase 8:** Remove POC dependencies entirely
