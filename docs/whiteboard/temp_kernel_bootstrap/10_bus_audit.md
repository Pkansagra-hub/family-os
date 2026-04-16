# Epic 1.1: Bus Audit — Complete Findings

**Date:** 2026-04-11
**Status:** ✅ COMPLETE — All 6 issues audited
**Verdict:** Bus is **PRODUCTION READY** — zero stubs, full dual-backend (Python+Rust), rich middleware, causal ordering

---

## Summary Verdict

| Aspect | Status | Notes |
|--------|--------|-------|
| Port definitions | ✅ COMPLETE | 3 protocols, all `@runtime_checkable`, well-typed |
| Envelope types | ✅ COMPLETE | 12-field frozen dataclass, V1 JSON + V2 FlatBuffers |
| Factory | ✅ COMPLETE | 4 methods, Python/Rust auto-selection, env override |
| Impl (LocalBus) | ✅ COMPLETE | ~610 LOC, TopicTrie, RWLock, middleware chain |
| Impl (Mailbox) | ✅ COMPLETE | ~475 LOC, WFQ priority queuing, bounded |
| Impl (Rust) | ✅ COMPLETE | RustBusAdapter + RustMailboxRouterAdapter via PyO3 |
| Adapters | ✅ COMPLETE | SessionBusAdapter + FabricBusAdapter, real logic |
| Middleware | ✅ COMPLETE | Tracing + Metrics + TopicValidation, all real |
| Timing | ✅ COMPLETE | ~990 LOC, causal ordering + gap buffering |
| Config | ✅ COMPLETE | YAML loader with defaults |
| Docs | ✅ COMPLETE | ARCHITECTURE.md + README.md + Mermaid diagram |

**Total LOC:** ~3,500+ across bus package
**Stubs found:** ZERO — every file is real, production implementation

---

## Issue 1.1.1: Port Definitions — IBus, IMailbox, IMailboxRouter ✅

### IBus (`k1/bus/ports/bus.py`)

```
Type:     Protocol, @runtime_checkable
Alias:    BusHandler = Callable[[Envelope], None]
```

| Method | Signature | Return |
|--------|-----------|--------|
| `publish` | `(self, envelope: Envelope) -> None` | None |
| `subscribe` | `(self, pattern: str, handler: BusHandler) -> SubscriptionHandle` | SubscriptionHandle |
| `unsubscribe` | `(self, handle: SubscriptionHandle) -> bool` | bool |

**SubscriptionHandle** (frozen dataclass): `subscription_id: str`, `pattern: str`

**Topic model:** Dot-separated hierarchical strings (e.g. `k1.capability.completed.v1`). Supports exact match, `*` (single-segment wildcard), `>` (greedy trailing wildcard) via TopicTrie.

### IMailbox (`k1/bus/ports/mailbox.py`)

```
Type:     Protocol, @runtime_checkable
```

| Method | Signature | Return |
|--------|-----------|--------|
| `receive` | `(self, timeout_ms: int = 0) -> Optional[Envelope]` | Optional[Envelope] |
| `pending` | `(self) -> int` | int |

No `send` or `peek`. Send-side is `IMailboxRouter.deliver()`.

### IMailboxRouter (`k1/bus/ports/mailbox.py`)

```
Type:     Protocol, @runtime_checkable
```

| Method | Signature | Return |
|--------|-----------|--------|
| `deliver` | `(self, actor_id: str, envelope: Envelope) -> None` | None (raises BackpressureError, UnknownActorError) |
| `register` | `(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IMailbox` | IMailbox |
| `unregister` | `(self, actor_id: str) -> bool` | bool |
| `registered_actors` | `(self) -> list[str]` | list[str] |

**MailboxConfig** (frozen dataclass): `capacity: int = 256`, `priority_wfq: bool = True`

**Verdict 1.1.1:** ✅ All three port protocols are clean, minimal, `@runtime_checkable`. No issues found.

---

## Issue 1.1.2: BusFactory ✅

### BusFactory (`k1/bus/factory.py`)

```
Type:     Static factory (no state, all @staticmethod)
Backend:  "auto" | "rust" | "python" — env K1_BUS_BACKEND overrides
```

| Factory Method | Key Params | Returns |
|---------------|------------|---------|
| `create_local` | `capture, timing_chain, middleware, backend="auto"` | `LocalBus \| RustBusAdapter` |
| `create_local_ordered` | `config, timeout_ms=5000, capture, middleware, backend="python"` | `LocalBus` (always Python — TimingChain requires it) |
| `create_for_testing` | `ordered, middleware, backend="auto"` | `LocalBus \| RustBusAdapter` |
| `create_mailbox_router` | `backend="auto"` | `LocalMailboxRouter \| RustMailboxRouterAdapter` |

**Key observations:**

- `create_local_ordered` defaults to Python-only because TimingChain is Python-side
- Auto-detection: tries `import k1_bus_core` → Rust if available, else Python
- `_to_chain()` helper normalizes `list[Middleware]` → `MiddlewareChain`
- No async — all synchronous construction

**Verdict 1.1.2:** ✅ Factory is complete. 4 methods cover all bus creation scenarios. Backend selection is clean.

---

## Issue 1.1.3: SessionBusAdapter ✅

### SessionBusAdapter (`k1/bus/adapters/session_adapter.py`, ~235 LOC)

```
Inherits:  IEventPort (ABC from k1.sessionstate.ports.events)
Injects:   bus: LocalBus (concrete type, NOT IBus protocol)
Purpose:   Adapts LocalBus → SessionState's IEventPort interface
```

| Method | Signature | Notes |
|--------|-----------|-------|
| `emit` | `(self, event_type: str, payload: Any) -> None` | Maps `event_type` → `"k1.session.{event_type}"` topic |
| `subscribe` | `(self, event_type: str, handler: Callable[[Any], None]) -> str` | Returns `str` subscription_id (not Handle) |
| `unsubscribe` | `(self, subscription_id: str) -> bool` | Looks up internal handle dict |
| `is_connected` | `@property -> bool` | `not self._bus.closed` |
| `bus` | `@property -> LocalBus` | Exposes underlying bus |
| `active_subscriptions` | `@property -> int` | Count |

**Translation layer:**

- `event_type` string → `"k1.session.{event_type}"` bus topic
- `Any` payload → JSON `{"payload": value}` → bytes
- Reverse on subscribe: bytes → JSON → unwrap `"payload"` key → handler

**Important:** Does NOT create a per-session bus — wraps the SINGLE shared bus. Session isolation is via topic prefix `k1.session.`.

**Verdict 1.1.3:** ✅ Real implementation. Correctly adapts bytes-based bus to SessionState's `IEventPort`. One concern: takes `LocalBus` concrete type, not `IBus` protocol — tight coupling but acceptable since factory controls creation.

---

## Issue 1.1.4: FabricBusAdapter ✅

### FabricBusAdapter (`k1/bus/adapters/fabric_adapter.py`, ~245 LOC)

```
Inherits:  Nothing (structural subtyping)
Injects:   bus: LocalBus (concrete type)
Purpose:   DUAL-ROLE — satisfies both IEventPort AND IDeltaBusPort for Fabric
```

| Method | Signature | Port Satisfied |
|--------|-----------|----------------|
| `emit` | `(self, topic: str, payload: Dict[str, Any]) -> None` | IEventPort |
| `subscribe` | `(self, topic: str, handler: Callable[[str, Dict[str, Any]], None]) -> FabricSubscriptionHandle` | IEventPort |
| `unsubscribe` | `(self, handle: FabricSubscriptionHandle) -> bool` | IEventPort |
| `emit_delta` | `(self, agent_id: str, delta_type: str, section: str, data: Dict[str, Any]) -> None` | IDeltaBusPort |
| `bus` | `@property -> LocalBus` | — |

**Dual-role details:**

- **IEventPort side:** General Fabric event pub/sub, `Dict[str, Any]` ↔ JSON bytes
- **IDeltaBusPort side:** `emit_delta()` publishes to `k1.agent.{agent_id}.delta.v1` with `Priority.REALTIME`
- Preserves `cognitive_trace_id` from payload dict into Envelope header

**Imports from Fabric:**

- `k1.fabric.ports.delta_bus.DeltaPayload`
- `k1.fabric.ports.event_port.SubscriptionHandle` (as `FabricSubscriptionHandle`)

**Verdict 1.1.4:** ✅ Real dual-role implementation. Confirmed both event and delta pathways. Clean JSON serialization at boundary.

---

## Issue 1.1.5: TracingMiddleware ✅

### TracingMiddleware (`k1/bus/middleware/tracing.py`, ~133 LOC)

```
Implements: Middleware protocol (structural)
Dependency: opentelemetry (optional, gracefully degrades)
```

| Method | Signature | Behavior |
|--------|-----------|----------|
| `process` | `(self, envelope: Envelope) -> Optional[Envelope]` | Always returns envelope (never drops) |

**What it does:** Creates an OpenTelemetry span named `"bus.publish {topic}"` with these attributes:

| Span Attribute | Source | Conditional? |
|----------------|--------|-------------|
| `bus.topic` | `envelope.topic` | Always |
| `bus.envelope_id` | `envelope.envelope_id` | Always |
| `bus.sequence` | `envelope.sequence` | Always |
| `bus.priority` | `envelope.priority` | Always |
| `bus.parent_id` | `envelope.parent_id` | Always |
| `bus.cognitive_trace_id` | `envelope.cognitive_trace_id` | Only if truthy |
| `bus.session_id` | `envelope.session_id` | Only if truthy |

**CRITICAL FINDING:** TracingMiddleware does **NOT stamp** `session_id` or `cognitive_trace_id` onto envelopes. It only **reads** them for tracing. The publisher must set these fields when creating the Envelope. This is correct — envelope is frozen (immutable), so middleware can't modify it.

**Verdict 1.1.5:** ✅ Real implementation with OpenTelemetry. Read-only tracing (correct for frozen envelopes). Graceful degradation when OTel not installed.

---

## Issue 1.1.6: MetricsMiddleware + TopicValidation ✅

### MetricsMiddleware (`k1/bus/middleware/metrics.py`, ~175 LOC)

```
Implements: Middleware protocol (structural)
Dependency: prometheus_client (optional, gracefully degrades)
```

| Metric | Type | Labels |
|--------|------|--------|
| `k1_bus_envelopes_total` | Counter | `topic_prefix`, `priority` |
| `k1_bus_envelope_latency_seconds` | Histogram | `topic_prefix` |

- **Topic prefix:** First 2 segments (e.g. `"k1.capability"`) to avoid cardinality explosion
- **Histogram buckets:** 100μs → 1s (9 buckets)
- **Priority labels:** urgent, realtime, interactive, background
- Always returns envelope (never drops)

### TopicValidationMiddleware (`k1/bus/middleware/topic_validation.py`, ~240 LOC)

```
Implements: Middleware protocol (structural)
Companion:  TopicRegistry
```

**TopicRegistry** — 3-tier topic validation:

1. **Exact:** `"k1.capability.completed.v1"`
2. **Prefix:** `"k1.agent."` (matches anything starting with prefix)
3. **Wildcard:** `"k1.agent.*.delta.*"` (fnmatch glob)

| Method | Signature |
|--------|-----------|
| `register` | `(self, topic: str) -> None` |
| `register_prefix` | `(self, prefix: str) -> None` |
| `is_known` | `(self, topic: str) -> bool` |
| `unregister` | `(self, topic: str) -> bool` |

**CRITICAL: SOFT validation only.** Unknown topics produce `logger.warning()` but are **NEVER dropped**. Envelope is always returned. This preserves bus liveness.

**Verdict 1.1.6:** ✅ Both are real, production implementations. MetricsMiddleware has proper Prometheus histograms. TopicValidation is deliberately soft (warn-only). Both gracefully degrade when deps missing.

---

## Envelope Details

### Envelope (`k1/bus/envelope/envelope.py`)

Frozen dataclass with **12 fields**:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `topic` | `str` | `""` | Dot-separated hierarchical topic |
| `priority` | `int` | `Priority.INTERACTIVE (2)` | 4 levels: URGENT/REALTIME/INTERACTIVE/BACKGROUND |
| `envelope_id` | `int` | `0` | Global monotonic ID (stamped by bus) |
| `sequence` | `int` | `0` | Per-topic monotonic sequence (stamped by bus) |
| `cognitive_trace_id` | `str` | `""` | Cross-component trace correlation |
| `session_id` | `str` | `""` | Session scope |
| `request_id` | `str` | `""` | Request correlation |
| `parent_id` | `int` | `0` | Causal parent envelope_id |
| `created_ns` | `int` | `0` | Nanosecond timestamp (stamped by bus) |
| `payload` | `bytes` | `b""` | Opaque payload (bus never reads) |
| `ttl_ms` | `int` | `0` | Time-to-live (0 = no expiry) |
| `payload_format` | `int` | `PayloadFormat.OPAQUE (0)` | JSON=1, MSGPACK=2 |

**Serialization:** V2 FlatBuffers (default) or V1 JSON (fallback). Env var `K1_ENVELOPE_FORMAT` selects.

### Priority Enum

| Level | Int | Weight (WFQ) |
|-------|-----|-------------|
| URGENT | 0 | 4× |
| REALTIME | 1 | 3× |
| INTERACTIVE | 2 | 2× |
| BACKGROUND | 3 | 1× |

### DeliveryMode Enum

| Mode | Int | Behavior |
|------|-----|----------|
| STRICT | 0 | Buffer on gap, enforce causal ordering |
| RELAXED | 1 | Deliver immediately, log reorders |
| BEST_EFFORT | 2 | Deliver immediately, droppable under pressure |

---

## Concrete Implementation Details

### LocalBus (`k1/bus/impl/local_bus.py`, ~610 LOC)

**Publish happy path:**

1. Validate envelope
2. Stamp: `envelope_id` (global monotonic), `sequence` (per-topic), `created_ns`
3. Run `MiddlewareChain.process()` — drop if returns None
4. Capture (if enabled)
5. TopicTrie match → collect handlers
6. Dispatch to handlers (error-isolated per handler)
7. Optional: TimingChain for ordering enforcement

**Concurrency:** `_ReadWriteLock` — publish = read lock, subscribe/unsubscribe = write lock. Zero contention between concurrent publishes.

### TopicTrie (`k1/bus/impl/topic_trie.py`, ~260 LOC)

Generic radix trie for O(k) topic matching where k = segment count.

- Supports: exact, `*` (single wildcard), `>` (greedy wildcard)
- O(1) removal by subscription_id via flat index
- Tombstoning with lazy compaction

### LocalMailbox + LocalMailboxRouter (`k1/bus/impl/local_mailbox.py`, ~475 LOC)

- Bounded queue per actor with optional WFQ (Weighted Fair Queuing across 4 priority sub-queues)
- `BackpressureError` on full, `UnknownActorError` on unregistered actor
- `Condition.wait(timeout)` for blocking receive

---

## Timing Subsystem

### TimingChain (`k1/bus/timing/timing_chain.py`, ~710 LOC)

Two ordering enforcement mechanisms:

1. **CausalTracker** — buffers envelopes whose `parent_id` hasn't been delivered yet
2. **GapBuffer** — buffers envelopes when per-topic sequence gaps detected

**Default rules** (16 topic prefixes):

- **STRICT (12):** `k1.capability`, `k1.orchestration`, `k1.planner`, `k1.hil`, `k1.hitl`, `k1.response`, `k1.session`, `k1.agent`, `k1.internal`, `k1.tool`, `k1.arbiter`, `k1.backpool`
- **RELAXED (4):** `k1.affect`, `k1.constraint`, `k1.proactive`, `k1.workflow`
- **BEST_EFFORT (2):** `k1.k0.sse`, `k1.fabric.learning`

Safety nets: 5000ms timeout sweep, buffer overflow (50K causal / 10K gap per-topic) → force-release oldest 10%.

---

## Bus Subscriber Map (from Architecture Diagram)

| Component | Publishes | Subscribes | Mailbox |
|-----------|-----------|------------|---------|
| **Concierge** | `k1.response.*`, `k1.affect.*` | `k1.capability.completed.*`, `k1.hil.*`, `k1.k0.sse.*`, `k1.agent.*.delta.*`, `k1.*.delta.*` | `concierge` |
| **Orchestrator** | `k1.orchestration.*`, `k1.constraint.*`, `k1.*.delta.*` | `k1.planner.plan.ready.*`, `k1.capability.completed.*` | `orchestrator` |
| **Fabric** | `k1.capability.*`, `k1.fabric.learning.signal.*`, `k1.agent.{id}.delta.*` | (via FabricBusAdapter) | `fabric` |
| **Planner** | `k1.planner.plan.ready.*`, `k1.hil.clarification.*`, `k1.planner.delta.*` | `k1.hil.*_response.*` | `planner` |
| **SessionState** | `k1.session.*` | `k1.session.mutation.*` | (via SessionBusAdapter) |
| **K0 Bridge** | `k1.k0.sse.received.*` | — | — |
| **Sub-Agents** | `k1.agent.{id}.delta.*` | — | `agent.{id}` |

---

## Concurrency Model

**Important discovery: Bus is fully synchronous/threaded. No asyncio anywhere.**

- `threading.Lock`, `threading.RLock`, `threading.Condition` throughout
- Handler dispatch is synchronous on publisher's thread
- `LocalMailbox.receive()` blocks via `Condition.wait(timeout)` — NOT `await`
- No `async def`, no `await`, no `asyncio` in any bus code

**Implication for kernel wiring:** If the rest of K1 is async (asyncio event loop), bus operations will need to be called from sync context or wrapped in `asyncio.to_thread()` / `run_in_executor()`. This is a design decision that needs attention during MS-2 wiring.

---

## Wiring Requirements for Kernel Bootstrap

Based on this audit, here's what the kernel needs to do with Bus:

### Tier-1 (Shared) — `KernelService.startup()`

1. **Create shared bus:** `BusFactory.create_local(middleware=chain)` where chain = `[TracingMiddleware(), MetricsMiddleware(), TopicValidationMiddleware(registry)]`
2. **Create mailbox router:** `BusFactory.create_mailbox_router()`
3. **Register shared actors:** `router.register("orchestrator")`, `router.register("planner")`, `router.register("fabric")`
4. **Populate TopicRegistry:** Register all known topic prefixes from the subscriber map above

### Tier-2 (Per-Session) — `KernelService.create_session()`

1. **Create per-session bus:** `BusFactory.create_local(middleware=chain)` (separate instance per session)
2. **Register session actors:** `router.register("concierge")`, `router.register(f"agent.{id}")` per dynamic agent
3. **Create SessionBusAdapter:** `SessionBusAdapter(session_bus)` → inject as `IEventPort` into SessionState
4. **Create FabricBusAdapter:** `FabricBusAdapter(shared_bus)` → inject as `IEventPort + IDeltaBusPort` into Fabric
5. **Wire bus subscriptions:** Each component subscribes to its topics per the subscriber map

### Open Questions for MS-2

| # | Question | Impact |
|---|----------|--------|
| Q1 | Shared bus vs per-session bus — or both? | Architecture decision |
| Q2 | Sync bus + async kernel — how to bridge? `asyncio.to_thread()`? | Performance + correctness |
| Q3 | Should `SessionBusAdapter` take `IBus` protocol instead of `LocalBus` concrete? | Testability |
| Q4 | Is one FabricBusAdapter shared or per-session? | Memory + isolation |
| Q5 | How does MailboxRouter relate to per-session scope? | Actor lifecycle |

---

## 09_wiring_plan.md Status Updates

| Issue | Status | Verdict |
|-------|--------|---------|
| 1.1.1 | ✅ | All 3 ports complete, `@runtime_checkable`, well-typed |
| 1.1.2 | ✅ | Factory complete, 4 methods, dual-backend |
| 1.1.3 | ✅ | SessionBusAdapter real (~235 LOC), adapts IEventPort |
| 1.1.4 | ✅ | FabricBusAdapter real (~245 LOC), dual-role IEventPort + IDeltaBusPort |
| 1.1.5 | ✅ | TracingMiddleware real (~133 LOC), OpenTelemetry, read-only (does NOT stamp) |
| 1.1.6 | ✅ | MetricsMiddleware real (~175 LOC), TopicValidation real (~240 LOC), soft validation |
