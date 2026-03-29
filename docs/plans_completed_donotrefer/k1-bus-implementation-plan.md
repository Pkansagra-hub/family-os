# K1 Bus Core -- Implementation Plan (v2 FINALIZED)

> **Status**: DRAFT -- Pre-implementation design (v2 rewrite)
> **Scope**: IBus (unified pub/sub) + IMailboxRouter (point-to-point) in `k1/bus/`
> **Philosophy**: The bus IS the OS kernel backbone. All K1 modules connect through it.
> Bus is BLIND -- payload = opaque bytes. Bus reads ONLY the FlatBuffers envelope header.
> True hexagonal port architecture -- bus defines canonical interfaces, modules adapt.

---

## The Problem (3 Belts, 0 Crankshaft)

Today K1 has **three incompatible event systems** and **no shared backbone**:

| Component | Interface | Base | Handler Signature | Where |
|-----------|-----------|------|-------------------|-------|
| Fabric | `IEventPort` | Protocol | `handler(topic, payload: Dict)` | `k1/fabric/ports/event_port.py` |
| SessionState | `IEventPort` | ABC | `handler(payload: Any)` -- no topic! | `k1/sessionstate/ports/events.py` |
| Bus README | `EventBus` | planned | `handler(FlatBuffersMessage)` -- async | `k1/bus/README.md` (ZERO code) |

Each module has its own `LocalEventAdapter`. They cannot talk to each other.
The Orchestrator plan references `IEventPort` and `IDeltaBusPort` from Fabric --
but those are Fabric-internal adapters, not shared infrastructure.

**Result**: When kernel.py tries to wire Concierge + Orchestrator + Fabric + Planner +
SessionState together, there is no bus to thread them onto.

---

## The Solution (One Timing Belt, Blind to Payload)

Build `k1/bus/` as the **central nervous system** with TWO components:

- **IBus** -- Unified pub/sub for events AND deltas (same pipe, topic prefix split)
- **IMailboxRouter** -- Point-to-point actor messaging (separate delivery contract)

Why 2, not 3? Events and deltas are BOTH fire-and-forget pub/sub with fan-out.
They differ only in topic prefix (`k1.capability.*` vs `k1.agent.*.delta.v1`).
Mailbox is fundamentally different: at-least-once, backpressure, per-actor queues.

```text
k1/bus/
  __init__.py           # Exports: IBus, IMailbox, IMailboxRouter, BusFactory
  ports/
    __init__.py
    bus.py              # IBus Protocol + SubscriptionHandle
    mailbox.py          # IMailbox Protocol + IMailboxRouter Protocol + MailboxConfig
  envelope/
    __init__.py
    schema.fbs          # FlatBuffers envelope schema
    envelope.py         # Envelope dataclass + builder + parser
  impl/
    __init__.py
    local_bus.py        # In-process IBus (V1): trie routing + WFQ + sequence gen
    local_mailbox.py    # In-process Mailbox + MailboxRouter (V1): bounded WFQ queues
  timing/
    __init__.py
    timing_chain.py     # Causal ordering (parent_id) + sequence gap detection
    timing_config.py    # Per-topic-prefix delivery modes (STRICT/RELAXED/BEST_EFFORT)
  middleware/
    __init__.py
    tracing.py          # OpenTelemetry span injection (envelope header only)
    metrics.py          # Prometheus counters: envelopes/sec, p99 latency, gaps, drops
    topic_validation.py # TopicRegistry validation (envelope header only)
  factory.py            # BusFactory: create_local(), create_for_testing()
  adapters/
    __init__.py
    fabric_adapter.py   # IBus(bytes) <-> Fabric IEventPort(Dict): serialize/deserialize
    session_adapter.py  # IBus(bytes) <-> SessionState IEventPort(Any): strips topic
```

Total: ~15 files, ~2000-2500 lines estimated.

---

## Design Decisions (Immutable Unless ADR Supersedes)

### 1. Bus is BLIND

Payload = opaque `bytes`. Bus NEVER reads, parses, or validates payload contents.
Bus reads ONLY the FlatBuffers envelope header for routing and timing decisions.

Why: Rust portability (no Python-specific types cross the bus boundary), zero-copy
path for FlatBuffers, modules own their serialization format.

### 2. FlatBuffers Envelope

Every message through IBus or IMailboxRouter carries this envelope:

```text
table BusEnvelope {
  topic:             string;    // e.g. "k1.capability.completed.v1"
  priority:          uint8;     // 0=URGENT, 1=REALTIME, 2=INTERACTIVE, 3=BACKGROUND
  envelope_id:       uint64;    // Global monotonic, bus-assigned
  sequence:          uint64;    // Per-topic monotonic, bus-assigned
  cognitive_trace_id:string;    // Trace correlation across K0+K1
  session_id:        string;    // Session scope
  request_id:        string;    // Request scope within session
  parent_id:         uint64;    // Causal parent envelope_id (0 = root)
  created_ns:        uint64;    // Monotonic clock, bus-assigned
  payload_len:       uint32;    // Payload byte count
  payload:           [ubyte];   // OPAQUE -- bus never reads this
}
```

NO `deadline_ns`. NO `ttl`. Modules handle their own timeouts.
Proven toxic by: F46 (saga recovery), F69 (delta aggregation), F10 (parallel ack).

### 3. Trie-Based Topic Matching

O(topic_length) matching. Pre-compiled at subscribe time. Hierarchical wildcards.
Same data structure works in Rust (future PyO3 rewrite).

Example: subscriber `k1.agent.*.delta.*` matches `k1.agent.abc.delta.v1`

### 4. Timing Chain (Deadline-Agnostic)

Three mechanisms replace deadlines:

**a) Causal ordering via parent_id**

- Child envelope waits for parent to deliver before being dispatched
- Covers: F10 (ack before progress), F06 (HIGH tier chain), F46 (saga compensation)

**b) Per-topic sequence counters**

- Each topic gets monotonic uint64 sequence, bus-assigned
- Gap detection: if consumer sees seq 5 then 7, it buffers 7 and waits for 6
- Covers: F68 (per-agent delta ordering)

**c) Central timing config (per topic prefix)**

- `STRICT` -- ordered delivery, buffer on gap, causal wait
- `RELAXED` -- deliver as-is, log reorder (monitoring only)
- `BEST_EFFORT` -- drop OK under pressure, no ordering guarantee
- Changeable WITHOUT code changes (config file / env var)

**Topic prefix -> delivery mode mapping:**

| Mode | Topic Prefixes |
| --- | --- |
| STRICT | `k1.capability.*`, `k1.orchestration.*`, `k1.planner.*`, `k1.hil.*`, `k1.agent.*.delta.*`, `k1.response.*`, `k1.session.*` |
| RELAXED | `k1.affect.*`, `k1.constraint.*`, `k1.proactive.*`, `k1.workflow.*` |
| BEST_EFFORT | `k1.k0.sse.*`, `k1.fabric.learning.*` |

### 5. WFQ Priority Scheduling (from F136)

| Priority | Value | Weight | Latency Target |
| --- | --- | --- | --- |
| URGENT | 0 | 4x | < 5ms |
| REALTIME | 1 | 3x | < 10ms |
| INTERACTIVE | 2 | 2x | < 50ms |
| BACKGROUND | 3 | 1x | < 500ms |

### 6. Middleware Chain (K0 Pattern)

Middleware sees envelope HEADER only, never payload:

1. **tracing** -- OpenTelemetry span creation from `cognitive_trace_id`
2. **metrics** -- Prometheus counters (envelopes/sec, p99 latency, gaps, drops)
3. **topic_validation** -- TopicRegistry check (rejects unknown topics)

---

## Canonical Port Interfaces

### IBus (unified pub/sub -- events AND deltas)

```python
@runtime_checkable
class IBus(Protocol):
    """Unified pub/sub bus. Blind to payload (bytes).
    Events and deltas are the same pipe, different topic prefixes."""

    def publish(self, topic: str, payload: bytes,
                priority: int = 2,
                parent_id: int = 0,
                cognitive_trace_id: str = "",
                session_id: str = "",
                request_id: str = "") -> int:
        """Publish bytes to topic. Returns envelope_id.
        Bus wraps in FlatBuffers envelope, assigns envelope_id + sequence.
        Fire-and-forget. At-most-once delivery."""
        ...

    def subscribe(self, pattern: str,
                  handler: Callable[['Envelope'], None]) -> SubscriptionHandle:
        """Subscribe to topic pattern (trie-matched).
        Exact: 'k1.capability.completed.v1'
        Wildcard: 'k1.agent.*.delta.*'
        Handler receives full Envelope (header + payload bytes)."""
        ...

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Remove subscription. Returns True if existed."""
        ...
```

Key decisions:

- ONE method for events AND deltas (both are `publish`)
- Payload is `bytes` -- bus is blind
- `parent_id` enables causal ordering (0 = root, no parent)
- Handler receives `Envelope` (typed wrapper around FlatBuffers)
- Pattern matching via trie (same method for exact and wildcard)

### IMailboxRouter + IMailbox (point-to-point actor messaging)

```python
@runtime_checkable
class IMailbox(Protocol):
    """Actor mailbox. Bounded, priority-aware, WFQ scheduled."""

    def send(self, envelope: bytes) -> None:
        """Enqueue envelope. Raises BackpressureError if full."""
        ...

    def receive(self, timeout_ms: int = 0) -> Optional[bytes]:
        """Dequeue next envelope (WFQ priority order). None if empty/timeout."""
        ...

    @property
    def depth(self) -> int:
        """Current queue depth."""
        ...

    def close(self) -> None:
        """Drain and close."""
        ...


@runtime_checkable
class IMailboxRouter(Protocol):
    """Routes envelopes to actor mailboxes by ID."""

    def register(self, actor_id: str, config: MailboxConfig) -> IMailbox:
        """Register actor, create mailbox with config (capacity, priority)."""
        ...

    def send_to(self, actor_id: str, envelope: bytes) -> None:
        """Send to actor's mailbox. Raises UnknownActorError if not registered."""
        ...

    def get_mailbox(self, actor_id: str) -> IMailbox:
        """Get actor's mailbox for direct receive()."""
        ...

    def unregister(self, actor_id: str) -> None:
        """Remove actor and close its mailbox."""
        ...
```

Key decisions:

- `bytes` payload everywhere -- same FlatBuffers envelope as IBus
- `register` returns the IMailbox so actors own their receive side
- Backpressure via bounded queues -- senders get `BackpressureError`
- `MailboxConfig` carries capacity + priority_class (URGENT/REALTIME/INTERACTIVE/BACKGROUND)
- Separate from IBus because: at-least-once (not fire-and-forget), backpressure to sender, per-actor WFQ

Why mailbox is NOT part of IBus (proven by 4 failure scenarios):

1. **Slow consumer**: IBus drops / skips. Mailbox MUST backpressure.
2. **Fan-out storm**: IBus broadcasts to N. Mailbox is 1-to-1.
3. **Poison message**: IBus skips on error. Mailbox must dead-letter.
4. **Backpressure direction**: IBus -> consumer problem. Mailbox -> sender problem.

---

## Envelope Data Class

```python
@dataclass(frozen=True)
class Envelope:
    """Typed wrapper around FlatBuffers BusEnvelope. Immutable."""
    topic: str
    priority: int           # 0=URGENT, 1=REALTIME, 2=INTERACTIVE, 3=BACKGROUND
    envelope_id: int        # Global monotonic (bus-assigned)
    sequence: int           # Per-topic monotonic (bus-assigned)
    cognitive_trace_id: str
    session_id: str
    request_id: str
    parent_id: int          # Causal parent envelope_id (0 = root)
    created_ns: int         # Monotonic clock (bus-assigned)
    payload: bytes          # OPAQUE -- bus never reads this

    @staticmethod
    def from_flatbuffers(buf: bytes) -> 'Envelope': ...

    def to_flatbuffers(self) -> bytes: ...
```

---

## Module Adapter Strategy

### Fabric (needs Dict <-> bytes serialization)

Fabric's `IEventPort` expects `handler(topic: str, payload: Dict[str, Any])`.
Bus delivers `handler(Envelope)` with `payload: bytes`.

```python
class FabricBusAdapter:
    """Adapts IBus(bytes) <-> Fabric IEventPort(Dict).
    Serializes Dict -> FlatBuffers bytes on publish.
    Deserializes bytes -> Dict on subscribe callback."""

    def __init__(self, bus: IBus):
        self._bus = bus

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        raw = flatbuffers_serialize(payload)  # Dict -> bytes
        self._bus.publish(topic, raw)

    def subscribe(self, topic: str,
                  handler: Callable[[str, Dict], None]) -> SubscriptionHandle:
        def wrapper(env: Envelope):
            data = flatbuffers_deserialize(env.payload)  # bytes -> Dict
            handler(env.topic, data)
        return self._bus.subscribe(topic, wrapper)
```

### SessionState (needs topic stripping + bytes deserialization)

SessionState's `IEventPort` expects `handler(payload: Any)` -- no topic arg.

```python
class SessionBusAdapter:
    """Adapts IBus(bytes) <-> SessionState IEventPort(Any).
    Strips topic from handler callback.
    Maps event_type <-> topic prefix."""
    PREFIX = "k1.session."

    def emit(self, event_type: str, payload: Any) -> None:
        raw = flatbuffers_serialize({"payload": payload})
        self._bus.publish(f"{self.PREFIX}{event_type}", raw)

    def subscribe(self, event_type: str,
                  handler: Callable[[Any], None]) -> str:
        def wrapper(env: Envelope):
            data = flatbuffers_deserialize(env.payload)
            handler(data.get("payload", data))
        handle = self._bus.subscribe(f"{self.PREFIX}{event_type}", wrapper)
        return handle.subscription_id  # SS expects str
```

### Orchestrator, Planner, Concierge (new -- use IBus directly)

These modules use `IBus.publish(topic, bytes)` and `IBus.subscribe(pattern, handler)`
directly. kernel.py injects `IBus` + `IMailboxRouter` into constructors.
No adapters needed -- they are designed for the bus from day one.

---

## Flow-to-Topic Mapping (from K1_FLOWS.md)

| Flow | Topic(s) | Delivery | Bus Component |
| --- | --- | --- | --- |
| F01-F10: Core Conversation | `k1.response.*`, mailbox(concierge, orchestrator) | STRICT + mailbox | IBus + IMailboxRouter |
| F33-F42: Tool Execution | `k1.capability.invoked/completed/failed.v1` | STRICT | IBus |
| F43-F52: Orchestrator | `k1.orchestration.*`, `k1.constraint.*`, `k1.workflow.*` | STRICT/RELAXED | IBus |
| F53-F59: Planner + HIL | `k1.planner.*`, `k1.hil.*` | STRICT | IBus |
| F60-F65: Sub-Agents | `k1.agent.{id}.delta.v1`, mailbox(agent.{id}) | STRICT + mailbox | IBus + IMailboxRouter |
| F66-F77: SessionState | `k1.session.*` | STRICT | IBus |
| F78-F87: K0 Bridge | `k1.k0.sse.*` | BEST_EFFORT | IBus |
| F88-F94: Proactive | `k1.proactive.*` | RELAXED | IBus |
| F132-F137: Bus Coordination | WFQ scheduling, priority delivery | -- | Internal |

---

## Implementation Milestones (Detailed)

> **V1 serialization**: Plain Python (`struct.pack` + `json.dumps` for payload wrapping).
> FlatBuffers schema (`envelope.fbs`) written in M1 but codegen deferred to M1b.
> This lets us ship M1-M4 with ZERO new dependencies.

---

### M1: Envelope + Ports (~500 lines, 6 files, 0 external deps)

**Goal**: Define the canonical data types and Protocol interfaces that every
other milestone depends on. After M1, any developer can write code that
compiles against `IBus`, `IMailbox`, `IMailboxRouter`, and `Envelope`.

**Files created**:

| File | Purpose | Lines (est) |
| --- | --- | --- |
| `k1/bus/__init__.py` | Public API exports | ~30 |
| `k1/bus/ports/__init__.py` | Package init | ~5 |
| `k1/bus/ports/bus.py` | `IBus` Protocol, `SubscriptionHandle` | ~100 |
| `k1/bus/ports/mailbox.py` | `IMailbox`, `IMailboxRouter`, `MailboxConfig`, errors | ~120 |
| `k1/bus/envelope/__init__.py` | Package init | ~5 |
| `k1/bus/envelope/envelope.py` | `Envelope` frozen dataclass, `Priority` enum, `DeliveryMode` enum, builder, parser | ~150 |

**Test files**:

| File | What it tests |
| --- | --- |
| `tests/k1/bus/envelope/test_envelope.py` | Envelope creation, defaults, immutability, round-trip serialize/deserialize, invalid field rejection |
| `tests/k1/bus/ports/test_bus_protocol.py` | IBus protocol structural subtyping checks, SubscriptionHandle frozen semantics |
| `tests/k1/bus/ports/test_mailbox_protocol.py` | IMailbox/IMailboxRouter protocol checks, MailboxConfig validation, BackpressureError |

**Acceptance criteria**:

- `Envelope` is a frozen dataclass with all 10 fields from the FlatBuffers schema
- `Priority` enum has 4 levels: URGENT=0, REALTIME=1, INTERACTIVE=2, BACKGROUND=3
- `DeliveryMode` enum has 3 values: STRICT, RELAXED, BEST_EFFORT
- `Envelope.to_bytes()` and `Envelope.from_bytes()` round-trip losslessly
- `IBus` is `@runtime_checkable` Protocol with `publish()`, `subscribe()`, `unsubscribe()`
- `IMailbox` is `@runtime_checkable` Protocol with `send()`, `receive()`, `depth`, `close()`
- `IMailboxRouter` is `@runtime_checkable` Protocol with `register()`, `send_to()`, `get_mailbox()`, `unregister()`
- `SubscriptionHandle` is frozen dataclass (subscription_id + pattern)
- `MailboxConfig` validates capacity > 0, priority in range
- `BackpressureError` and `UnknownActorError` exception types defined
- All tests pass, zero external dependencies beyond stdlib

**NOT in M1**: No implementations (LocalBus, LocalMailbox). No FlatBuffers codegen.
No factory. No middleware. Ports only.

---

### M2: LocalBus + Trie (~600 lines, 4 files)

**Goal**: First working IBus implementation. Publish bytes, subscribe with
wildcards, receive Envelope in handler. Trie-based topic matching.
WFQ priority scheduling. Per-topic monotonic sequence numbers.

**Files created**:

| File | Purpose | Lines (est) |
| --- | --- | --- |
| `k1/bus/impl/__init__.py` | Package init | ~5 |
| `k1/bus/impl/local_bus.py` | `LocalBus(IBus)`: TopicTrie, WFQ, SequenceGenerator, EnvelopeBuilder | ~400 |
| `k1/bus/impl/topic_trie.py` | `TopicTrie`: insert(pattern, handler), match(topic) -> list[handler] | ~120 |
| `k1/bus/factory.py` | `BusFactory.create_local()`, `create_for_testing()` | ~60 |

**Test files**:

| File | What it tests |
| --- | --- |
| `tests/k1/bus/impl/test_topic_trie.py` | Exact match, single wildcard `*`, multi-level wildcard `>`, no match, overlapping patterns |
| `tests/k1/bus/impl/test_local_bus.py` | Publish/subscribe round-trip, wildcard delivery, WFQ priority ordering, sequence monotonicity, unsubscribe, handler error isolation, thread safety, create_for_testing capture mode |

**Acceptance criteria**:

- `TopicTrie.match("k1.agent.abc.delta.v1")` returns handlers subscribed to `k1.agent.*.delta.*`
- `LocalBus.publish()` returns monotonic `envelope_id`
- Per-topic `sequence` increments monotonically per topic
- WFQ delivers URGENT 4x more often than BACKGROUND under contention
- Handler exceptions logged, not propagated
- `BusFactory.create_for_testing()` returns bus with capture mode (drain all envelopes)
- Thread-safe: concurrent publish + subscribe from multiple threads

**Depends on**: M1 (Envelope, IBus, SubscriptionHandle)

---

### M3: Timing Chain (~400 lines, 4 files)

**Goal**: Deadline-agnostic ordering enforcement. Causal chains via parent_id.
Sequence gap buffering. Central config for per-topic-prefix delivery modes.

**Files created**:

| File | Purpose | Lines (est) |
| --- | --- | --- |
| `k1/bus/timing/__init__.py` | Package init | ~5 |
| `k1/bus/timing/timing_chain.py` | `TimingChain`: causal wait (parent_id), gap buffer (sequence) | ~200 |
| `k1/bus/timing/timing_config.py` | `TimingConfig`: loads per-prefix delivery mode mapping, lookup by topic | ~100 |
| `k1/bus/timing/defaults.py` | Default STRICT/RELAXED/BEST_EFFORT prefix mapping | ~50 |

**Test files**:

| File | What it tests |
| --- | --- |
| `tests/k1/bus/timing/test_timing_chain.py` | Parent-before-child delivery, out-of-order buffering, gap fill, timeout release |
| `tests/k1/bus/timing/test_timing_config.py` | Prefix lookup, STRICT/RELAXED/BEST_EFFORT resolution, unknown prefix defaults to RELAXED |

**Acceptance criteria**:

- Envelope with `parent_id=X` is held until envelope X is delivered
- Sequence gap (5, then 7) buffers 7 until 6 arrives or timeout
- STRICT topics enforce both causal + sequence ordering
- RELAXED topics log reorder but deliver immediately
- BEST_EFFORT topics deliver immediately, drop under pressure
- Config changeable at runtime (reload from dict)

**Depends on**: M1 (Envelope, DeliveryMode), M2 (LocalBus integrates TimingChain)

---

### M4: MailboxRouter (~400 lines, 2 files)

**Goal**: Point-to-point actor messaging with bounded queues, WFQ priority
within each mailbox, backpressure to sender.

**Files created**:

| File | Purpose | Lines (est) |
| --- | --- | --- |
| `k1/bus/impl/local_mailbox.py` | `LocalMailbox(IMailbox)`, `LocalMailboxRouter(IMailboxRouter)` | ~300 |

**Test files**:

| File | What it tests |
| --- | --- |
| `tests/k1/bus/impl/test_local_mailbox.py` | register/unregister, send/receive FIFO, backpressure (BackpressureError at capacity), WFQ priority within mailbox, timeout on receive, close drains, UnknownActorError on unregistered send_to, depth tracking |

**Acceptance criteria**:

- `register("orchestrator", MailboxConfig(capacity=50, priority=REALTIME))` returns IMailbox
- `send_to("orchestrator", envelope_bytes)` enqueues; `mailbox.receive()` dequeues
- At capacity, `send()` raises `BackpressureError`
- URGENT envelopes dequeued before BACKGROUND within same mailbox
- `close()` prevents new sends, allows draining existing
- `unregister()` closes mailbox, subsequent `send_to()` raises `UnknownActorError`
- Thread-safe: concurrent send/receive across threads

**Depends on**: M1 (IMailbox, IMailboxRouter, MailboxConfig, errors)

---

### M5: Middleware + Infrastructure (~300 lines, 5 files)

**Goal**: Observability layer. Tracing, metrics, topic validation.
Middleware chain runs on envelope HEADER only -- never touches payload.

**Files created**:

| File | Purpose | Lines (est) |
| --- | --- | --- |
| `k1/bus/middleware/__init__.py` | Package init + `Middleware` Protocol | ~30 |
| `k1/bus/middleware/tracing.py` | OpenTelemetry span from `cognitive_trace_id` | ~80 |
| `k1/bus/middleware/metrics.py` | Prometheus counters (envelopes/sec, p99 latency) | ~80 |
| `k1/bus/middleware/topic_validation.py` | TopicRegistry: validate topic exists, log unknown | ~80 |

**Test files**:

| File | What it tests |
| --- | --- |
| `tests/k1/bus/middleware/test_tracing.py` | Span creation, trace_id propagation, missing trace_id handling |
| `tests/k1/bus/middleware/test_metrics.py` | Counter increments, latency histogram, labeled by topic prefix |
| `tests/k1/bus/middleware/test_topic_validation.py` | Known topic passes, unknown topic logged/rejected, wildcard registration |

**Acceptance criteria**:

- Middleware Protocol: `def process(envelope: Envelope) -> Optional[Envelope]` (None = drop)
- LocalBus runs middleware chain before dispatch
- Tracing creates OpenTelemetry span per publish (opt-in, no-op if OTel not configured)
- Metrics increment `k1_bus_envelopes_total{topic_prefix}` counter
- TopicValidation logs warning on unknown topic but does NOT drop (soft validation)

**Depends on**: M1 (Envelope), M2 (LocalBus middleware hook)

---

### M6: Module Adapters + Integration (~400 lines, 4 files)

**Goal**: Bridge existing Fabric and SessionState ports to IBus.
Integration tests proving cross-module communication works.

**Files created**:

| File | Purpose | Lines (est) |
| --- | --- | --- |
| `k1/bus/adapters/__init__.py` | Package init | ~5 |
| `k1/bus/adapters/fabric_adapter.py` | `FabricBusAdapter`: IBus(bytes) <-> Fabric IEventPort(Dict) + IDeltaBusPort | ~120 |
| `k1/bus/adapters/session_adapter.py` | `SessionBusAdapter`: IBus(bytes) <-> SessionState IEventPort(Any) | ~100 |

**Test files**:

| File | What it tests |
| --- | --- |
| `tests/k1/bus/adapters/test_fabric_adapter.py` | Dict -> bytes -> Dict round-trip, emit/subscribe mapping, delta_bus emit mapping, SubscriptionHandle compatibility |
| `tests/k1/bus/adapters/test_session_adapter.py` | event_type -> topic prefix mapping, topic stripping in handler, is_connected always True, subscription_id return type |
| `tests/k1/bus/integration/test_cross_module.py` | Fabric publish -> Orchestrator-like subscribe, delta aggregation via trie, mailbox point-to-point, full flow end-to-end, causal chain ordering |

**Acceptance criteria**:

- `FabricBusAdapter` satisfies Fabric `IEventPort` Protocol (structural subtype check)
- `FabricBusAdapter` satisfies Fabric `IDeltaBusPort` Protocol
- `SessionBusAdapter` satisfies SessionState `IEventPort` ABC (isinstance check)
- Cross-module: Fabric adapter emits -> raw IBus subscriber receives bytes -> decodes Dict
- Full flow test: mailbox dispatch -> bus publish -> trie fan-out -> adapter decode

**Depends on**: M1-M5 (all bus internals), existing Fabric ports, existing SessionState ports

---

## How kernel.py Wires Everything

```python
# k1/kernel/kernel.py (sketch)

class K1Kernel:
    def __init__(self):
        # 1. Create the bus backbone (2 components)
        ibus, mailbox_router = BusFactory.create_local()

        # 2. Register actor mailboxes
        concierge_mb = mailbox_router.register(
            "concierge", MailboxConfig(capacity=100, priority=REALTIME))
        orchestrator_mb = mailbox_router.register(
            "orchestrator", MailboxConfig(capacity=50, priority=REALTIME))
        planner_mb = mailbox_router.register(
            "planner", MailboxConfig(capacity=20, priority=INTERACTIVE))
        fabric_mb = mailbox_router.register(
            "fabric", MailboxConfig(capacity=200, priority=REALTIME))

        # 3. Create adapters for existing modules
        fabric_adapter = FabricBusAdapter(ibus)
        session_adapter = SessionBusAdapter(ibus)

        # 4. Wire Fabric (existing, needs adapter: Dict <-> bytes)
        self.fabric = FabricFactory.create_standalone(
            event_port=fabric_adapter,
            delta_bus=fabric_adapter,  # Same adapter handles both
        )

        # 5. Wire SessionState (existing, needs adapter: topic stripping)
        self.session_state = SessionStateFactory.create(
            event_port=session_adapter,
        )

        # 6. Wire Orchestrator (new, uses IBus directly)
        self.orchestrator = Orchestrator(
            mailbox=orchestrator_mb,
            bus=ibus,
            mailbox_router=mailbox_router,
            fabric_gateway=self.fabric,
            state_reader=self.session_state.reader(),
        )

        # 7. Wire Planner (new, uses IBus directly)
        self.planner = Planner(
            mailbox=planner_mb,
            bus=ibus,
        )

        # 8. Wire Concierge (new, uses IBus directly)
        self.concierge = Concierge(
            mailbox=concierge_mb,
            bus=ibus,
            mailbox_router=mailbox_router,
            session_state=self.session_state,
        )
```

**ONE bus instance. ALL modules connected. The timing belt turns everything.**

---

## Port Interface Reconciliation Summary

| Current Interface | Owner | Fate | Adapter |
| --- | --- | --- | --- |
| Fabric `IEventPort` | `k1/fabric/ports/event_port.py` | **KEPT** internally | `FabricBusAdapter` wraps IBus |
| Fabric `IDeltaBusPort` | `k1/fabric/ports/delta_bus.py` | **KEPT** internally | `FabricBusAdapter` wraps IBus (same adapter) |
| Fabric `IAgentMailbox` | `k1/fabric/providers/agent_provider.py` | **KEPT** internally | Router creates mailbox per agent |
| SessionState `IEventPort` | `k1/sessionstate/ports/events.py` | **KEPT** internally | `SessionBusAdapter` wraps IBus |
| Bus `IBus` | `k1/bus/ports/bus.py` | **NEW canonical** | -- |
| Bus `IMailbox` + `IMailboxRouter` | `k1/bus/ports/mailbox.py` | **NEW canonical** | -- |

**No existing code broken.** Fabric and SessionState keep their own port interfaces.
Bus adapters bridge the gap. New modules (Orchestrator, Planner, Concierge) use IBus directly.

---

## Performance Targets (V1 In-Process)

| Metric | Target | Notes |
| --- | --- | --- |
| Publish-to-handler | < 0.1ms | In-process, trie lookup |
| Trie pattern match | < 0.05ms | Pre-compiled at subscribe |
| Mailbox send-to-receive | < 0.1ms | Thread-safe bounded queue |
| Envelope build (FlatBuffers) | < 0.01ms | Zero-copy builder |
| Max envelopes/sec sustained | 10,000+ | Single process |
| Sequence gap detection | < 0.01ms | Per-topic counter lookup |
| Mailbox capacity | Configurable (default 100) | Backpressure on overflow |

V2 (Rust via PyO3) targets: same interface, < 0.01ms publish-to-handler, 100K+ envelopes/sec.

---

## What This Enables (The Timing Belt Effect)

1. **Cross-component debugging**: Every envelope carries `cognitive_trace_id` + `envelope_id`.
   Middleware logs every routing decision. "Why did Orchestrator not get the plan?"
   -- check bus trace by cognitive_trace_id.

2. **Timing diagnostics**: Causal chain via `parent_id`. Measure latency from Concierge
   dispatch -> Orchestrator ack -> Plan ready -> Fabric complete -> Concierge deliver.
   Find the slow gear by tracing the parent_id chain.

3. **Integration testing**: `BusFactory.create_for_testing()` captures all envelopes.
   Assert that `Fabric.execute(cap)` -> IBus has `k1.capability.completed.v1` ->
   Orchestrator handler received it. No mocks needed.

4. **Module isolation**: Each module only knows about `IBus` or `IMailboxRouter`.
   Swap implementations (local -> Rust PyO3) without touching any module code.

5. **Gradual build**: Build Orchestrator M1 -> it subscribes to IBus, receives from
   Mailbox, publishes bytes. Planner M1 -> same pattern. They naturally communicate
   through the bus without knowing about each other's internals.

6. **Race condition elimination**: Timing chain's causal ordering + sequence gaps
   prevent the exact failure modes documented in K1_FLOWS.md (F10, F46, F68-F69).
   No deadlines needed -- the bus structure itself prevents misordering.
