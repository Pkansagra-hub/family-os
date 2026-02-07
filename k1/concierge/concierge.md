# Concierge Diagram Gaps

**Purpose**: Tracks structural gaps in `concierge.mmd` that must be resolved before the diagram is implementation-ready.
Each gap is an **epic**. Epics are addressed incrementally — one at a time — with diagram updates after each.

**Benchmark**: `sessionstate_internal.mmd` — the gold standard for implementation-ready diagrams in this codebase.

**Current state of concierge.mmd**: Rich behavioral flows (FSM, UltraBERT pipeline, complexity routing, tool dispatch, output system, delta aggregation, signal tools, experience layer) but **zero implementation scaffolding**.

---

## Epic 1 — Hexagonal Architecture (Ports and Adapters)

**Priority**: CRITICAL

**Gap**: No port/adapter boundaries. All external dependencies (LLM, SessionState, Bus, Bridge, Storage) are wired directly into behavioral nodes. This makes the diagram untestable and couples implementation to specific infrastructure.

**Reference**: SessionState has 5 ports and 6 adapters. Bridge has 6 ports for 5 responsibilities. Concierge crosses 8 real boundaries — each with different protocols, failure modes, offline behaviors, and adapter implementations.

### Design Decisions

#### D1: UltraBERT — OUTSIDE Concierge (behind IClassificationPort)

UltraBERT is an ML model with its own training, versioning, and deployment lifecycle. The 12-head output format IS the contract — the port defines that contract, the adapter wraps UltraBERT.

- Bridge puts every external system behind a port — even deeply coupled ones
- Concrete benefit: test FSMController, ComplexityRouter, TurnProcessor without loading a 149M param model
- `MockClassificationAdapter` returns scripted `ClassificationResult{intents, domains, safety_band, emotions, sentiment, entities, relations}`

#### D2: IMemoryPort — KEEP SEPARATE from IDispatchPort

Bridge architecture makes this unambiguous. Bridge has separate ports per operation type:

| Aspect | `recall_memory()` | `invoke_capability()` |
|---|---|---|
| Bridge port | `IKernelQueryPort` | `IConnectorGatewayPort` (via Fabric) |
| Pattern | Request/Response | Fire-and-forget or async |
| Offline behavior | Falls back to LOCAL COLD (K1 SQLite) | Depends on capability |
| Security | Query envelope + band enforcement | Capability token + rate limiting |

Zero shared code between these paths. Merging them would force one adapter to do two unrelated jobs.

#### D3: IInputPort — KEEP

L0_EXTERNAL is "intentionally detached — we don't know UI/API interface yet" (skeleton diagram). That's exactly why we need a port — it decouples Concierge from the not-yet-designed transport layer. Without it, the first test has to mock WebSocket internals or spin up a real server. With IInputPort: `test_adapter.inject(UserMessage("plan a birthday party"))`.

#### D4: EventBus — NO dedicated port. Merge into IDeltaPort

Traced every EventBus edge touching Concierge:

- `EVENT_BUS → CONCIERGE_MAILBOX` — one edge, errors only
- `EVENT_BUS → CURIOSITY_AGENT` — external, not inside Concierge
- `EVENT_BUS → PROACTIVE_DECISION` — external, not inside Concierge

Proactive agents and curiosity agents are in TOUCHPOINTS, not inside Concierge. Concierge only receives error events from EventBus. Errors are just another async inbound message — same as deltas. IDeltaPort subscribes to both delta topics and error topics. One port, one mock, one subscription mechanism.

#### D5: IDispatchPort — SINGLE port with two methods (not separate Fabric + Orchestrator ports)

From Concierge's perspective the routing decision (direct vs envelope) is its own business logic. The port just provides two execution paths:

- `dispatch_direct(CapabilityRequest) → CapabilityResult` — LOW tier, Fabric direct
- `dispatch_envelope(TaskEnvelope) → void` — MED/HIGH tier, async to Orchestrator

One port, one mock. Concierge picks the method based on tier.

### Final Port Design: 8 Ports

Derived from Concierge's processing pipeline, NOT copied from SessionState:

```
IN → [Classify] → [Think] → [Route/Recall] → [Aggregate] → OUT
                                                    ↕
                                              [State R/W]
```

| # | Port | Direction | Protocol |
|---|---|---|---|
| 1 | `IInputPort` | Inbound | `receive() → UserMessage` |
| 2 | `IOutputPort` | Outbound | `send(OutputEvent) → DeliveryReceipt` |
| 3 | `IClassificationPort` | Outbound | `classify(text) → ClassificationResult` |
| 4 | `ILLMPort` | Outbound | `complete(prompt, tools[], budget) → LLMResponse` |
| 5 | `IStatePort` | Both | `read(sections[]) → Snapshot`; `write(section, op, data) → WriteResult` |
| 6 | `IDispatchPort` | Outbound | `dispatch_direct(CapReq) → CapResult`; `dispatch_envelope(TaskEnv) → void` |
| 7 | `IDeltaPort` | Inbound | `subscribe(topics[]) → DeltaStream`; `errors() → ErrorStream` |
| 8 | `IMemoryPort` | Outbound | `recall(query, selectors[]) → MemoryResult` |

### What each port abstracts (current diagram wiring)

| Port | Replaces in current diagram |
|---|---|
| `IInputPort` | Implicit `k1.concierge.user_input` arrival at LISTENING |
| `IOutputPort` | `OUTPUT_CHANNEL → SSE/WS/REST` (implicit protocol) |
| `IClassificationPort` | Direct UltraBERT calls inside ACKING_CORE |
| `ILLMPort` | `LLM_REQUEST_BUS → PROMPT_SYSTEM → MODEL_GATEWAY` chain in TP_LLM |
| `IStatePort` | 15+ direct edges to `SS_*` nodes + `SS_MUTATION_GUARD` in TP_SESSIONSTATE |
| `IDispatchPort` | `DISPATCHING → CAPABILITY_FABRIC` (LOW) + `DISPATCHING → ORCHESTRATOR_MAILBOX` (MED/HIGH) |
| `IDeltaPort` | `DELTA_BUS → AGGREGATION_WINDOW` + `EVENT_BUS → CONCIERGE_MAILBOX` (error routing) |
| `IMemoryPort` | `TOOL_RECALL_MEMORY → BRIDGE_CLIENT` in TP_BRIDGE |

### Adapter Mapping

| Port | Production Adapter | Test Adapter |
|---|---|---|
| `IInputPort` | `WebSocketInputAdapter`, `RESTInputAdapter` | `TestInputAdapter` (inject messages programmatically) |
| `IOutputPort` | `SSEOutputAdapter`, `WebSocketOutputAdapter` | `TestOutputAdapter` (capture + assert on messages) |
| `IClassificationPort` | `UltraBERTv4Adapter` (12 heads, 22ms) | `MockClassificationAdapter` (scripted results) |
| `ILLMPort` | `ModelGatewayAdapter` (Model Hub) | `MockLLMAdapter` (scripted responses + tool calls) |
| `IStatePort` | `SessionKernelAdapter` (MutationGuard inside) | `InMemoryStateAdapter` (dict-based, tracks writes) |
| `IDispatchPort` | `FabricOrchestratorAdapter` (routes by tier) | `MockDispatchAdapter` (captures envelopes + requests) |
| `IDeltaPort` | `DeltaBusAdapter` (real subscription + error routing) | `TestDeltaAdapter` (emit test deltas on demand) |
| `IMemoryPort` | `BridgeRecallAdapter` (QueryPort + offline fallback to LOCAL COLD) | `MockMemoryAdapter` (canned recall results) |

### How Concierge differs from SessionState

| Aspect | SessionState (5 ports) | Concierge (8 ports) |
|---|---|---|
| System type | Passive store | Active conductor |
| ML ports | 0 | 2 (`IClassificationPort`, `ILLMPort`) |
| I/O ports | 0 (no user-facing) | 2 (`IInputPort`, `IOutputPort`) |
| Bidirectional | 1 (`IStoragePort`) | 1 (`IStatePort`) |
| Async inbound | 0 | 1 (`IDeltaPort` — deltas + errors) |
| Cross-kernel | 1 (`IK0SyncPort`) | 1 (`IMemoryPort` — Bridge recall) |
| Execution | 0 | 1 (`IDispatchPort` — Fabric/Orchestrator) |

### Diagram changes needed

1. Add `PORTS` subgraph inside `CONCIERGE` with 8 port nodes
2. Add `ADAPTERS` subgraph below PORTS with production + test adapters
3. Reroute all boundary-crossing edges: internal services → ports → adapters → touchpoints
4. TOUCHPOINTS stays as-is (they represent external systems, not our adapters)
5. **Remove `TP_EMPATHY` touchpoint** (Tension C Resolution): The skeleton's `L3_EMPATHY` layer (Theory of Mind, Mental Model, Predictive Completion) overlaps with Concierge's internal ENGINES subgraph. Per Epic 4 D3, the 5 experience layer engines (Persona, Style, Affective Mirroring, Anticipation, Narrative) are sub-components of FSMController. The `TP_EMPATHY` touchpoint in the diagram is misleading — it implies an external component, but these are internal heuristic engines. Remove `TP_EMPATHY` subgraph and its edges (`ACKING --> THEORY_OF_MIND`, `MENTAL_MODEL_MGMT --> CONCIERGE_FSM`). The internal `ENGINES` subgraph already covers this. If future design introduces a truly external cognitive empathy service (separate process, separate lifecycle), it would re-enter as a touchpoint behind a new `IEmpathyPort`.
6. **Clarify TIER_MEDIUM/HIGH routing** (Tension B Resolution): In the current diagram, `TIER_MEDIUM` and `TIER_HIGH` route through `LLM_REQUEST_BUS` BEFORE `DISPATCHING`. This conflicts with the whiteboard S4 where the LLM call happens IN DISPATCHING (as a preliminary ack). The diagram should be updated: `TIER_MEDIUM` and `TIER_HIGH` route DIRECTLY to `DISPATCHING` (same as `TIER_LOW`). The LLM reasoning/ack call happens as part of the DISPATCHING phase logic, not as a pre-dispatch gate. The current `TIER_MEDIUM -->|"llm.reasoning (2K tokens)"| LLM_REQUEST_BUS` and `TIER_HIGH -->|"llm.planning (8K tokens)"| LLM_REQUEST_BUS` edges should become `TIER_MEDIUM --> DISPATCHING` and `TIER_HIGH --> DISPATCHING`. Inside DISPATCHING, the LLM call is orchestrated by TurnProcessor.

---

## Epic 2 — Invariants (Non-Negotiable Rules)

**Priority**: CRITICAL

**Gap**: No codified invariants. Timing ceilings, rate limits, and behavioral constraints are implied but never declared. Without invariants, tests have no acceptance criteria.

**Reference**: SessionState declares 5 invariants: `HOT <= 48KB`, `WARM <= 48KB`, `TOTAL <= 96KB (Hard Reject)`, `control never evicted`, `history <= 40 turns`. Each has a hard number and a rejection behavior.

**Design principle**: An invariant is a rule where **violation = rejection or override**. If it's a target you'd like to hit but degradation is acceptable, it belongs in Epic 3 (Performance Baselines), not here.

### How we derived every invariant

Traced every hard number and constraint across three sources:

- `concierge.mmd` — 748 lines of behavioral flows with embedded numbers
- `whiteboard_concierge_orchestrator_planner_fabric.md` — 1052 lines of locked decisions
- `sessionstate_internal.mmd` — invariant pattern reference

### Category 1: Ownership Invariants

These protect the Single Writer Pattern (ADR-0017). Break any of these and SessionState integrity is compromised.

| ID | Rule | On violation | Source |
| --- | --- | --- | --- |
| INV-01 | Only Concierge writes to SessionState | Reject write, log violation | ADR-0017, whiteboard S1 |
| INV-02 | Every cognitive tool write passes through `MutationGuard.preflight()` | Reject write | whiteboard S2, diagram |
| INV-03 | Two-Phase Write sequence: Phase 1 (UltraBERT) completes before Phase 2 (LLM tools) starts | Abort turn, re-enter ACKING | whiteboard S2 |
| INV-04 | Orchestrator, Planner, Spawned Agents NEVER write SessionState directly | Hard architectural constraint — no code path exists | whiteboard S1 |

**INV-01 through INV-04 rationale**: The Single Writer Pattern is the foundational constraint of the entire K1 architecture. Without it, concurrent writes corrupt state. Every other component emits deltas to DeltaBus, which Concierge aggregates and writes as the sole writer. This is not negotiable.

### Category 2: Safety Invariants

These protect users from harm. Break any of these and safety is compromised.

| ID | Rule | On violation | Source |
| --- | --- | --- | --- |
| INV-05 | Safety Gate evaluates FIRST, before any complexity routing | Override — skip all routing, direct to Safety Agent | diagram: Safety Gate, whiteboard S4 |
| INV-06 | CRISIS band = immediate protocol, bypasses all other FSM states | CRISIS overrides any current state including mid-turn | diagram: SAFETY_OVERRIDE, TIER_CRISIS |
| INV-07 | `control.safety_band` written to SessionState BEFORE any routing decision | Phase 1 write ordering is: safety_band first, then intents, then domains | whiteboard S2 Phase 1 table |

**INV-05 through INV-07 rationale**: A user in crisis ("I want to hurt myself") must never be routed through complexity classification, tool dispatch, or planning. The safety gate is the first thing that fires after UltraBERT. The rest of the pipeline only runs if safety_band != CRISIS.

### Category 3: Rate Limit Invariants

These prevent runaway behavior — infinite loops, resource exhaustion, or unresponsive states.

| ID | Rule | Hard cap | On violation | Source |
| --- | --- | --- | --- | --- |
| INV-08 | Tool calls per turn | 20 | Reject additional tool calls, force DELIVERING with partial results | Design decision (prevents LLM runaway) |
| INV-09 | Clarification rounds per intent | 3 | Escalate to best-effort execution or abandon with explanation | diagram: CLARIFYING "1-2 Qs", design margin |
| INV-10 | Output queue depth | 50 | Drop BACKGROUND priority events, log warning | diagram: OUTPUT_QUEUE |
| INV-11 | Workflow execution depth | 3 | Reject `execute_workflow()`, return cycle detection error | diagram: TOOL_EXECUTE_WORKFLOW "Max depth: 3" |
| INV-12 | Concurrent active turns per session | 1 | Queue incoming message, do not interleave turns | Single Writer + FSM design |

**INV-08 rationale**: LLMs can hallucinate tool calls in a loop. 20 is generous — typical turns use 0-6 cognitive tools + 0-3 action tools. At 20 we're well past reasonable and something is wrong.

**INV-09 rationale**: The diagram says "1-2 Qs" for progressive disclosure. 3 rounds means we've asked the user 3 times and still can't proceed. At that point, either execute best-effort or tell the user we can't do it. Never ask a 4th time.

**INV-12 rationale**: Concierge is the Single Writer. It processes one turn at a time. If a new message arrives mid-turn, it goes to INTERRUPT_HANDLING (topic change) or queues (same topic). Two concurrent turns would break Single Writer because both would try to write SessionState.

### Category 4: Timing Invariants

These are hard ceilings where exceeding the value means the architecture is broken (not just slow).

| ID | Rule | Ceiling | On violation | Source |
| --- | --- | --- | --- | --- |
| INV-13 | FSM state transition (no I/O allowed in transitions) | 1ms | Architecture violation — means I/O leaked into transition logic | Design decision |
| INV-14 | Delta aggregation window | 500ms fixed | Not configurable per turn — flush at window boundary regardless | diagram: AGGREGATION_WINDOW, whiteboard S10 |

**INV-13 rationale**: FSM transitions are guard evaluation + state assignment. Pure computation. If a transition takes >1ms, it means someone put a network call or disk I/O inside a guard — that's a bug, not a performance issue. All I/O happens inside states (ACKING, DISPATCHING, etc.), never during transitions between them.

**INV-14 rationale**: The 500ms aggregation window is a design decision, not a performance target. It determines how long Concierge batches incoming deltas before applying them. Making it dynamic would add complexity with no real benefit — 500ms is the agreed fixed cadence.

### Category 5: Structural Invariants

These are architecture rules that shape implementation. They don't have a "violation" at runtime — they're constraints that must be true in the code.

| ID | Rule | Rationale | Source |
| --- | --- | --- | --- |
| INV-15 | All user-facing output goes through OUTPUT_CHANNEL — no component bypasses it | Single delivery path = single place to enforce ordering, priority, delivery confirmation | diagram: OUTPUT_SYSTEM |
| INV-16 | Internal services call ports, never external systems directly | Testability + swappability. Without this, Epic 1 ports are decorative | Epic 1 D5 |
| INV-17 | FSM is the single state machine — no secondary FSMs inside engines or tools | One FSM = one source of truth for "what state is the conversation in." Nested FSMs create state synchronization bugs | Design decision |

### Category 6: Token Budget Invariants

These are hard caps from the whiteboard that determine prompt construction. Exceeding them means the LLM call fails or produces garbage.

| ID | Rule | Hard cap | On violation | Source |
| --- | --- | --- | --- | --- |
| INV-18 | LLM context window per call | 128K tokens | Trigger `summarize_context()` before the call, never exceed | whiteboard S7, diagram: CONTEXT_BUILDER |
| INV-19 | Intent acknowledgement (acknowledge_request) | 150 tokens | Truncate, do not expand | diagram: TOOL_ACKNOWLEDGE_REQUEST "~100-150 tokens" |
| INV-20 | Preliminary ack (MED/HIGH) | 200 tokens | Truncate, do not expand | whiteboard S4 |
| INV-21 | Clarification question | 300 tokens | Truncate, keep to 1-2 questions | whiteboard S4 |

**INV-18 rationale**: 128K is the model's physical limit. This is not a soft target — exceeding it means the API call is rejected or the model hallucinates from truncated input. `summarize_context()` exists specifically to compress before hitting this wall.

**INV-19 through INV-21 rationale**: These are output budgets, not input. They keep responses snappy. An ack that's 500 tokens defeats the purpose of a fast acknowledgement. Truncation is the correct response — the full response comes later in DELIVERING.

### What is NOT an invariant (belongs in Epic 3)

These numbers appear in the diagram and whiteboard but are **performance targets, not architectural rules**:

| Metric | Value | Why not an invariant |
| --- | --- | --- |
| UltraBERT classification latency | 25ms | If it takes 30ms, the system degraded but not broken. Fallback exists. |
| Intent ack end-to-end latency | 50ms | If it takes 80ms, user still gets ack — just slower. SLO, not invariant. |
| LOW tier end-to-end | <2s | Performance target. If it takes 3s, the result is still correct. |
| MEDIUM tier end-to-end | 2-10s | Same — timing is a quality metric, not a correctness rule. |
| HIGH tier end-to-end | 10-60s | Same. |
| MutationGuard preflight latency | 0.2ms | If it takes 1ms, the write still succeeds. |
| LOW response budget | ~500 tokens | Guideline for prompt design, not a hard reject. |
| MED response budget | ~2K tokens | Same. |
| HIGH response budget | ~8K tokens | Same. |

### Summary: 21 Invariants across 6 categories

| Category | Count | IDs |
| --- | --- | --- |
| Ownership | 4 | INV-01 to INV-04 |
| Safety | 3 | INV-05 to INV-07 |
| Rate Limits | 5 | INV-08 to INV-12 |
| Timing | 2 | INV-13, INV-14 |
| Structural | 3 | INV-15 to INV-17 |
| Token Budget | 4 | INV-18 to INV-21 |

### Diagram changes needed

Add `INVARIANTS` subgraph inside `CONCIERGE` with nodes for each category:

```text
INV_OWNERSHIP["Ownership: Single Writer, MutationGuard preflight, Two-Phase sequence"]
INV_SAFETY["Safety: Gate first, CRISIS override, safety_band before routing"]
INV_RATE["Rate Limits: 20 tools/turn, 3 clarifications, 50 output queue, depth 3, 1 turn/session"]
INV_TIMING["Timing: FSM transition <= 1ms, delta window = 500ms"]
INV_STRUCTURAL["Structural: OUTPUT_CHANNEL only, ports only, single FSM"]
INV_TOKEN["Token: 128K context, 150 ack, 200 prelim ack, 300 clarification"]
```

---

## Epic 3 — Performance Baselines

**Priority**: CRITICAL

**Gap**: No P95/P99 latency targets. Cannot write performance tests or set SLOs without baselines.

**Reference**: SessionState declares baselines in header comments (HOT Read P99: 0.20us, Write P99: 18.8us, etc.).

### Design principle: We own the rails, not the train

FamilyOS is BYOLLM — Bring Your Own LLM. We do not control:

- LLM inference latency (varies by provider, model size, quantization, hardware)
- Time-to-first-token (provider-specific streaming implementation)
- Token generation speed (provider-specific)
- Model-specific quirks (speculative decoding, batching, queueing)

We DO control:

- Everything that happens BEFORE the LLM call (classification, routing, state reads)
- Everything that happens AFTER the LLM call (state writes, delta aggregation, output delivery)
- The BUDGET ENVELOPES we hand to the LLM (token limits, timeouts)
- The CIRCUIT BREAKERS that kill runaway calls

This means baselines split into two categories:

1. **System-owned latencies** — code we write, hardware we control, numbers we can test and guarantee
2. **Budget envelopes** — timeouts and token caps we enforce on external providers. These are not performance targets — they are the guardrails. The LLM provider sees "you have X seconds and Y tokens, deliver or get cut off."

### Category 1: System-Owned Latencies

These are components Concierge owns. We write this code, we benchmark it, we set SLOs on it.

| Metric | What it measures | P95 | P99 | Why this number |
| --- | --- | --- | --- | --- |
| UltraBERT classification | Local ML model inference (12 heads) | 20ms | 25ms | Local GPU/CPU inference, no network. 149M params. Measured in PoC. |
| Intent ack delivery | `acknowledge_request()` signal tool LLM generation + SSE push to client | 40ms | 50ms | Measures SSE delivery latency AFTER LLM generates ~150 token ack text. LLM generation time is separate (provider-dependent, covered by budget envelopes). See Tension A Resolution in Epic 4. |
| FSM state transition | Guard evaluation + state assignment | 0.5ms | 1ms | Pure computation, no I/O. INV-13 hard ceiling. |
| MutationGuard preflight | Section permission + size check | 0.1ms | 0.2ms | In-memory dict lookup + size comparison. |
| Delta aggregation flush | Batch deltas → DeltaBus publish | 400ms | 500ms | Timer-driven (INV-14 = 500ms window). Flush itself is ~1ms. |
| Phase 1 write (deterministic) | safety_band + intents + domains to SessionState | 0.01ms | 0.02ms | 3 small writes to in-memory HOT store. No LLM. |
| Phase 2 write (post-LLM) | response + history + context to SessionState | 0.05ms | 0.1ms | 3-5 writes to in-memory HOT store. Data already assembled. |
| Complexity routing decision | Tier selection from UltraBERT output | 0.1ms | 0.2ms | Threshold comparison on classification scores. Pure math. |
| Output queue → SSE delivery | Formatted event → client receives first byte | 3ms | 5ms | Queue dequeue + SSE serialize + network push. |
| Orchestrator envelope dispatch | Build TaskEnvelope + publish to Orchestrator mailbox | 1ms | 2ms | Serialization + message bus publish. |
| Fabric direct dispatch | Build CapabilityRequest + invoke Fabric | 1ms | 2ms | Same as envelope dispatch — just different target. |

**Total system overhead per turn (excluding LLM)**:

- Classification + routing + Phase 1 write + dispatch overhead + Phase 2 write + output delivery
- Sum: ~25ms + ~0.2ms + ~0.02ms + ~2ms + ~0.1ms + ~5ms = **~32ms system overhead**
- Everything else in a turn's wall clock time is LLM provider time

### Category 2: Budget Envelopes (Rails for LLM Providers)

These are NOT performance targets for us. They are the timeout and budget constraints we enforce. If the provider exceeds them, we cut the call and fall back.

| Envelope | Budget | On exceeded | Linked circuit breaker |
| --- | --- | --- | --- |
| Single LLM call timeout | 30s | Kill call, trigger Model Gateway CB | CB: Model Gateway (30s timeout, 3min recovery) |
| LOW tier total timeout | 2s | Force deliver partial or error response | Whiteboard S4: LOW < 2s |
| MEDIUM tier total timeout | 10s | Force deliver with progress so far | Whiteboard S4: MED 2-10s |
| HIGH tier total timeout | 45s | Force deliver with progress so far | Design decision: 15s headroom before Orchestrator CB (60s) |
| CRISIS tier total timeout | 5s | Hard override to Safety Agent | Safety invariant INV-06 |
| Planner stage timeout (per stage) | 10s | Abort stage, use best result from prior stage | Whiteboard: Planner CB 45s total / 4 stages |
| Token budget: LOW response | 500 tokens | Truncate at budget | Whiteboard S4 |
| Token budget: MED response | 2K tokens | Truncate at budget | Whiteboard S4 |
| Token budget: HIGH response | 8K tokens | Truncate at budget | Whiteboard S4 |
| Token budget: preliminary ack | 200 tokens | Truncate (INV-20) | Invariant |
| Token budget: intent ack | 150 tokens | Truncate (INV-19) | Invariant |
| Token budget: clarification | 300 tokens | Truncate (INV-21) | Invariant |
| Context window per call | 128K tokens | Trigger `summarize_context()` before call (INV-18) | Invariant |

### Why HIGH P99 is 45s, not 60s

The Orchestrator circuit breaker fires at 60s. If our P99 is 60s, then 1% of requests are hitting the breaker as normal operation — that's a system design failure, not an exceptional case. 45s P99 gives 15s headroom (25%) for the breaker to only trip on genuinely broken calls.

```
HIGH tier budget:  |=====45s P99======|===15s headroom===|
Orchestrator CB:   |==================60s================|→ TRIP
```

### What LLM companies see when they integrate

A provider plugging into `ILLMPort` gets these constraints from Concierge:

```
complete(prompt, tools[], budget) → LLMResponse

budget = {
    max_tokens: 500 | 2000 | 8000,     // per tier
    timeout_ms: 30000,                   // per-call hard kill
    context_window: 128000,              // already enforced by us
}
```

They don't need to know about our FSM, tiers, or internal routing. They see a budget, they deliver within it, or they get cut off. That's the rail.

### What we DON'T baseline (and why)

| Metric | Why excluded |
| --- | --- |
| LLM inference latency | Provider-specific. Ranges from 200ms (local quantized) to 5s (cloud GPT-4 class). |
| Time-to-first-token | Provider-specific streaming implementation. Some providers don't stream at all. |
| Token generation speed | Provider-specific. 20 tok/s (cloud) to 100+ tok/s (local optimized). |
| Total tier end-to-end P95/P99 | Dominated by LLM time which we don't control. We set the timeout envelope instead. |

### How Concierge differs from SessionState baselines

| Aspect | SessionState | Concierge |
| --- | --- | --- |
| All metrics system-owned? | Yes — pure in-memory store | No — depends on external LLM providers |
| Baseline type | P95/P99 for every operation | Split: system-owned P95/P99 + external budget envelopes |
| Dominant cost | Memory operations (microseconds) | LLM calls (seconds) |
| Testable in isolation? | Yes — no external dependencies | System-owned: yes. Envelopes: only with mock LLM adapter. |

### Diagram changes needed

Add `PERF_BASELINES` subgraph inside `CONCIERGE` with two sections:

```text
PERF_SYSTEM["System-Owned: UltraBERT 25ms, FSM 1ms, MutationGuard 0.2ms, Phase1 0.02ms, Phase2 0.1ms, Output 5ms"]
PERF_ENVELOPES["Budget Envelopes: LLM call 30s, LOW 2s, MED 10s, HIGH 45s, CRISIS 5s"]
PERF_TOKENS["Token Rails: LOW 500, MED 2K, HIGH 8K, ack 150, prelim 200, clarify 300, context 128K"]
```

---

## Epic 4 — Internal Services (Codeable Components)

**Priority**: CRITICAL

**Gap**: Behavioral flows exist but no named, bounded services. A developer cannot look at the diagram and know "I need to build class X with methods Y and Z."

**Reference**: SessionState defines 6 services with exact test counts (SizeTracker 62, MutationGuard 79, etc.).

### Design Decisions

#### D1: 9 services, derived from tracing every subgraph in concierge.mmd

Every subgraph (FSM, ACKING_CORE, CONCIERGE_TOOLS, OUTPUT_SYSTEM, MESSAGING, ENGINES) was traced to identify service boundaries. Services own behavioral flows, enforce invariants, and use ports from Epic 1.

#### D2: SafetyGate encapsulated inside IntentProcessor

INV-05 says "Safety Gate evaluates FIRST." Putting it inside IntentProcessor makes this impossible to violate — the method `process()` always runs safety check before any classification logic. A separate SafetyGate service would require every caller to remember to call it first. We don't add complexity to enforce discipline that encapsulation handles for free.

#### D3: 5 Experience Layer engines are sub-components of FSMController

Persona, Style, Affective Mirroring, Anticipation, and Narrative engines fire every 20-30 turns on heuristic cadence (no LLM). They are low-level sub-components — FSMController triggers them via `tick_experience(turn_count)`. Not promoted to top-level services.

#### D4: ContextAssembler defined here, algorithms in Epic 7

This epic defines the service boundary (class, methods, ports, invariants). Epic 7 (Token Budget Management) defines the algorithms (how budget allocation works, when summarization triggers, tracking across sequential tool calls). Clean "what" vs "how" separation.

### Service 1: `FSMController`

**Responsibility**: Manages the 8-state core loop + 4 experience layer states. Evaluates transition guards. Fires experience layer on cadence (turn % N). Handles interrupt routing.

**Methods**:

- `transition(target, context) -> TransitionResult` — evaluate guard, change state
- `current_state() -> FSMState`
- `on_interrupt(message) -> InterruptDecision` — route: re-ACKING or queue
- `tick_experience(turn_count) -> ExperienceActions` — fire if cadence hit (% 20/25/30)

**Sub-components**: PersonaEngine, StyleEngine, AffectiveMirroringEngine, AnticipationEngine, NarrativeEngine

**Ports used**: `IStatePort` (read state for guards)

**Invariants enforced**: INV-13 (transition <= 1ms, no I/O), INV-17 (single FSM)

**Maps to diagram**: FSM subgraph (FSM_CORE_LOOP + FSM_EXPERIENCE_LAYER)

**Estimated tests**: ~60 (8 valid transitions, guard failures, interrupt routing, experience cadence, edge cases)

### Service 2: `TurnProcessor`

**Responsibility**: Orchestrates a single turn from input to output. Sequence: start -> Phase 1 write -> dispatch -> Phase 2 write -> end. Enforces turn exclusivity (only 1 active turn per session).

**Methods**:

- `start_turn(message) -> TurnContext` — acquire Single Writer lock, read HOT snapshot
- `execute_phase1(classification) -> Phase1Result` — write safety_band FIRST, then intents, domains
- `route_dispatch(tier, intent) -> DispatchDecision` — LOW direct vs MED/HIGH envelope
- `execute_phase2(tool_results, llm_response) -> Phase2Result` — apply cognitive tool mutations
- `end_turn() -> TurnSummary` — flush deltas, release lock, append to history

**Ports used**: `IStatePort` (Phase 1 + Phase 2 writes), `IDispatchPort` (routing), `ILLMPort` (LLM calls)

**Invariants enforced**: INV-01 (Single Writer), INV-03 (Phase 1 before Phase 2), INV-07 (safety_band before routing), INV-12 (1 turn/session)

**Maps to diagram**: Turn lifecycle edges across all FSM states

**Estimated tests**: ~90 (turn boundaries, phase ordering, lock acquire/release, interrupt mid-turn, concurrent turn rejection, Phase 1 write ordering)

### Service 3: `IntentProcessor`

**Responsibility**: The ACKING pipeline. Takes raw `ClassificationResult` from `IClassificationPort`, runs SafetyGate FIRST (INV-05), enriches with hypothesis/time/context, estimates uncertainty. Returns `ProcessedIntent` or `CrisisOverride`.

**Methods**:

- `process(classification, snapshot) -> ProcessedIntent | CrisisOverride`

Internally runs this pipeline (order guaranteed):

1. SafetyGate — CRISIS band -> immediate CrisisOverride, stops here
2. HypothesisGenerator — multi-intent extraction from explicit head outputs
3. TimeResolver — NER TIME/DATE/DURATION -> absolute timestamps, detect ambiguity
4. ContextInference — SessionState fill + entity resolution
5. SanityArbiter — fast-path cached checks
6. UncertaintyEstimator — confidence scores -> uncertainty score, reasons

**Why SafetyGate is inside**: INV-05 ordering is encapsulated. Impossible to process an intent without checking safety first. No caller discipline required.

**Ports used**: `IStatePort` (read for context fill + entity resolution)

**Invariants enforced**: INV-05 (safety first), INV-07 (safety_band written before routing)

**Maps to diagram**: ACKING_CORE (Safety Gate, Hypothesis Pipeline, Time Resolution, Context Filling, Uncertainty Routing)

**Estimated tests**: ~110 (CRISIS override, temporal ambiguity, slot filling from 8 HOT sections, multi-intent hypothesis, entity resolution, uncertainty threshold boundary at 0.2, time zone resolution, pronoun conflicts, signal library coverage)

### Service 4: `ComplexityRouter`

**Responsibility**: Selects complexity tier from `ProcessedIntent`. Pure computation — no I/O, no ports.

**Methods**:

- `route(processed_intent) -> Tier` — evaluate 5 factors -> LOW/MED/HIGH/CRISIS

**5 routing factors** (from diagram):

1. Intent count + types -> intent_complexity (Multi-Intent Scorer)
2. Domain count > 1 -> domain_complexity (Cross-Domain Detector)
3. Safety band (AMBER+ bumps tier)
4. Emotion intensity (high intensity bumps tier)
5. Combined score -> tier threshold

**Ports used**: None (pure computation on ProcessedIntent data)

**Invariants enforced**: None directly (tier is deterministic from scores)

**Maps to diagram**: COMPLEXITY_ROUTER subgraph (MULTI_INTENT_SCORER, CROSS_DOMAIN_DETECTOR, COMPLEXITY_CLASSIFIER, TIER_LOW/MED/HIGH/CRISIS)

**Estimated tests**: ~45 (threshold boundaries per factor, all 4 tier outputs, combined scoring, safety band override to CRISIS, edge cases at boundaries)

### Service 5: `ToolDispatcher`

**Responsibility**: Routes tool calls across 4 categories (Cognitive, Read, Action, Signal). Executes via appropriate port. Buffers results. Enforces tool-per-turn limit.

**Methods**:

- `dispatch(tool_call) -> ToolResult` — route by category, execute, buffer
- `get_buffered_results() -> ToolResult[]` — drain for DELIVERING
- `clear_buffer()` — reset after turn completion
- `active_count() -> int` — for INV-08 enforcement

**Category routing**:

| Category | Tools | Port | Behavior |
| --- | --- | --- | --- |
| Cognitive (6) | update_scoreboard, update_beliefs, update_clarifications, update_narrative, refine_affect, promote_belief | `IStatePort` (via MutationGuard preflight) | Write SessionState per INV-02 |
| Read (3) | recall_memory, discover_capabilities, summarize_context | `IMemoryPort`, `IStatePort` | Read-only, no mutations |
| Action (3) | invoke_capability, spawn_via_fabric, execute_workflow | `IDispatchPort` | Execute capabilities |
| Signal (1) | acknowledge_request | `ILLMPort` (generate ~150 tokens) + `IOutputPort` (deliver) | LLM-generated intent restatement, no state mutation. See Tension A Resolution below |

**Ports used**: `IStatePort`, `IMemoryPort`, `IDispatchPort`, `IOutputPort`

**Invariants enforced**: INV-02 (MutationGuard preflight on cognitive), INV-08 (20 tools/turn hard cutoff), INV-11 (workflow depth 3)

**Maps to diagram**: CONCIERGE_TOOLS subgraph (COGNITIVE_TOOLS, READ_TOOLS, ACTION_TOOLS, SIGNAL_TOOLS) + TOOL_RESULT_BUFFER

**Estimated tests**: ~80 (per-category routing for all 13 tools, MutationGuard rejection, buffer drain/clear, 20-tool cutoff at boundary, workflow depth check, acknowledge_request fast path, concurrent tool isolation)

### Tension A Resolution: Two Distinct Acknowledgement Events

The architecture has **two separate acknowledgement events** that must not be conflated:

| Event | When | FSM State | Generated By | Tokens | Priority | Latency |
|---|---|---|---|---|---|---|
| `k1.response.intent_ack.v1` | After UltraBERT, BEFORE dispatch decision | ACKING | LLM via `acknowledge_request()` signal tool | ~100-150 (INV-19) | IMMEDIATE | ~50ms after input |
| `k1.response.ack.v1` | After dispatch decision, during delegation | COMPANIONING | LLM preliminary ack call (MED/HIGH only) | ~200 (INV-20) | REALTIME | ~200ms after dispatch |

**Intent ack** (`acknowledge_request()`): The LLM's FIRST tool call during ACKING. It generates a brief intent restatement + 1-line plan preview (~100-150 tokens). Fires in parallel with cognitive tools. Skipped on trivial turns ("ok cool" = 0 tool calls). The diagram correctly shows `ACKING --> TOOL_ACKNOWLEDGE_REQUEST --> LLM_REQUEST_BUS --> OUTPUT_CHANNEL`. This requires a lightweight LLM call, NOT zero LLM involvement. Epic 3 baseline "Intent ack delivery" (40ms P95 / 50ms P99) measures only the SSE delivery portion AFTER the LLM generates the ack text.

**Preliminary ack** (`k1.response.ack.v1`): Generated IN DISPATCHING for MED/HIGH tiers only. This is a separate LLM call (~200 tokens, INV-20) that says "I'll plan that birthday party! Let me work on it..." while Orchestrator processes in background. LOW tier skips this entirely (it goes straight to DELIVERING). The whiteboard S4 MED/HIGH flow describes THIS event, not `acknowledge_request()`.

These are independent, non-overlapping events. A HIGH-tier turn produces BOTH: intent ack first (~50ms), then preliminary ack later (~200ms after dispatch). A LOW-tier turn may produce only the intent ack. A trivial turn produces neither.

### Service 6: `OutputManager`

**Responsibility**: Formats output events, manages priority queue (REALTIME > PROGRESS > BACKGROUND), gates delivery timing via ConversationScheduler sub-component.

**Methods**:

- `enqueue(event, priority) -> QueuePosition`
- `deliver_next() -> DeliveryReceipt` — dequeue highest priority, send via IOutputPort
- `flush() -> DeliveryReceipt[]` — drain queue (for turn end)
- `depth() -> int` — for INV-10 check

**9 event types** (from diagram): intent_ack, final, ack, clarification, progress, proactive_question, proactive_message, hil_clarification, hil_approval

**Sub-components**: ConversationScheduler (rhythm-based delivery timing from TP_RHYTHM)

**Ports used**: `IOutputPort` (all delivery)

**Invariants enforced**: INV-10 (50 queue depth — drop BACKGROUND on overflow), INV-15 (all output through OUTPUT_CHANNEL)

**Maps to diagram**: OUTPUT_SYSTEM subgraph (OUTPUT_CHANNEL, OUTPUT_QUEUE, OUTPUT_EVENTS) + CONVERSATION_SCHEDULER

**Estimated tests**: ~55 (priority ordering across 3 levels, queue overflow with BACKGROUND drop, all 9 event type formatting, delivery confirmation, scheduler gating, flush correctness)

### Service 7: `DeltaAggregator`

**Responsibility**: Collects deltas from `IDeltaPort` in fixed 500ms window. Merges conflicts (last-writer-wins). Flushes batch to FSMController for state application. Routes error events from EventBus.

**Methods**:

- `start_window()` — begin 500ms timer
- `receive(delta)` — add to current batch
- `flush() -> AggregatedBatch` — merge conflicts (LWW), sort by priority, return batch
- `on_error(error)` — route error events to FSMController

**4 delta types** (from diagram): `k1.agent.{id}.delta.v1`, `k1.planner.delta.v1`, `k1.orchestration.delta.v1`, `k1.curiosity.delta.v1`

**Ports used**: `IDeltaPort` (subscription + error stream)

**Invariants enforced**: INV-14 (500ms fixed window — not configurable)

**Maps to diagram**: AGGREGATION_WINDOW node + CONCIERGE_MAILBOX (error routing path)

**Estimated tests**: ~50 (window timing boundaries, merge conflicts across 4 delta types, priority sort, error routing, empty window flush, rapid sequential deltas)

### Service 8: `ClarificationTracker`

**Responsibility**: Tracks clarification rounds per intent. Enforces max rounds. Manages pending sub-agent clarification requests from DeltaBus. Routes to INTERRUPT_HANDLING when sub-agents need user input.

**Methods**:

- `track_round(intent_id) -> RoundCount` — increment counter
- `max_reached(intent_id) -> bool` — INV-09 check (>= 3 = hard stop)
- `escalate(intent_id) -> EscalationDecision` — best-effort execution or abandon with explanation
- `add_pending(sub_agent_request)` — from delta clarification events
- `get_pending() -> PendingClarification[]` — for INTERRUPT_HANDLING routing

**Ports used**: `IStatePort` (write SS_CLARIFICATIONS)

**Invariants enforced**: INV-09 (3 clarification rounds max — never ask a 4th time)

**Maps to diagram**: CLARIFYING state + PENDING_CLARIFICATIONS node + ENTROPY_MIN_QUESTION_PLANNER

**Estimated tests**: ~40 (round counting per intent, max enforcement at boundary, escalation decision types, sub-agent pending queue FIFO, pending -> interrupt routing, clear on turn end)

### Service 9: `ContextAssembler`

**Responsibility**: Builds LLM context from SessionState sections based on tier. Tracks per-turn token usage. Triggers `summarize_context()` when approaching 128K. Enforces output token budgets per call type.

**Methods**:

- `assemble(tier, intent, tool_results) -> LLMContext` — read sections, format, budget-check
- `track_usage(tokens_consumed)` — increment per-turn counter
- `remaining_budget() -> int` — tokens left for current tier
- `needs_summarization(context) -> bool` — approaching 128K?
- `summarize(context) -> CompressedContext` — compress via ILLMPort

**Why this service exists**: With hexagonal ports (Epic 1), Prompt System is external (TP_LLM). But the DECISION of what context to include is Concierge's responsibility. ContextAssembler reads SessionState via `IStatePort`, formats context, and hands the assembled prompt to `ILLMPort.complete()`. Without this service, INV-18 (128K context window) has no owner inside Concierge.

**Algorithms**: Defined in Epic 7 (Token Budget Management). This epic defines the service boundary only.

**Ports used**: `IStatePort` (read sections), `ILLMPort` (for summarization calls)

**Invariants enforced**: INV-18 (128K context window), INV-19 (150 token ack), INV-20 (200 token prelim ack), INV-21 (300 token clarification)

**Maps to diagram**: TOOL_SUMMARIZE_CONTEXT + prompt assembly edges (FSM -> PROMPT_SYSTEM -> SS_* lookups) + CONTEXT_BUILDER

**Estimated tests**: ~55 (tier-specific section selection, 128K boundary trigger, summarization invocation, token tracking across sequential tool calls, output cap enforcement per type, empty context handling)

### Service Dependency Graph

```text
FSMController ---------> TurnProcessor
                             |---> IntentProcessor ---> ComplexityRouter
                             |---> ToolDispatcher
                             |---> ContextAssembler
                             |---> OutputManager
DeltaAggregator ----------> FSMController (flush batches)
ClarificationTracker -----> FSMController (escalation)
```

No circular dependencies. FSMController is the top-level state manager. TurnProcessor is the per-turn orchestrator that calls the rest. DeltaAggregator and ClarificationTracker feed back into FSMController asynchronously.

### Invariant enforcement coverage

Every invariant from Epic 2 has exactly one enforcing service. No orphans:

| Invariant | Enforcing Service |
| --- | --- |
| INV-01 Single Writer | TurnProcessor |
| INV-02 MutationGuard preflight | ToolDispatcher |
| INV-03 Two-Phase ordering | TurnProcessor |
| INV-04 No direct writes | Structural (no code path exists) |
| INV-05 Safety first | IntentProcessor |
| INV-06 CRISIS override | IntentProcessor (returns CrisisOverride) |
| INV-07 safety_band before routing | TurnProcessor (Phase 1 write order) |
| INV-08 20 tools/turn | ToolDispatcher |
| INV-09 3 clarification rounds | ClarificationTracker |
| INV-10 50 output queue | OutputManager |
| INV-11 Workflow depth 3 | ToolDispatcher |
| INV-12 1 turn/session | TurnProcessor |
| INV-13 FSM transition <= 1ms | FSMController |
| INV-14 500ms delta window | DeltaAggregator |
| INV-15 OUTPUT_CHANNEL only | OutputManager |
| INV-16 Ports only | Structural (all services use ports) |
| INV-17 Single FSM | FSMController |
| INV-18 128K context window | ContextAssembler |
| INV-19 150 token ack | ContextAssembler |
| INV-20 200 token prelim ack | ContextAssembler |
| INV-21 300 token clarification | ContextAssembler |

### How Concierge differs from SessionState

| Aspect | SessionState (6 services, 455 tests) | Concierge (9 services, ~585 tests) |
| --- | --- | --- |
| Most complex service | MigrationEngine (102 tests) | IntentProcessor (~110 tests) |
| Services with no ports | 0 | 1 (ComplexityRouter — pure logic) |
| Services using ILLMPort | 0 | 2 (TurnProcessor, ContextAssembler) |
| Async services | 0 | 1 (DeltaAggregator — timer-driven) |
| Service hierarchy depth | 2 | 3 (FSM -> TurnProcessor -> IntentProcessor) |
| Sub-components | None | 6 (5 engines in FSMController + Scheduler in OutputManager) |

### Diagram changes needed

1. Add `SERVICES` subgraph inside `CONCIERGE` with 9 service nodes
2. Each service node shows name, method signatures, estimated test count
3. Add dependency edges between services (matching dependency graph above)
4. Link services to their enforced invariants (dashed edges to INVARIANTS subgraph)
5. Link services to their used ports (edges to PORTS subgraph)

---

## Epic 5 — Session and Turn Lifecycle

**Priority**: HIGH

**Gap**: No lifecycle flows. The diagram shows steady-state behavior but not initialization, turn boundaries, shutdown, or crash recovery.

**Sources traced**: concierge.mmd (748 lines — FSM states, Two-Phase Write, DeltaAggregator, OutputManager, 7 circuit breakers), skeleton (LLM Call Matrix, Internal Flow Matrix, Two-Phase Write documentation), bridge (session.checkpoint command topic, Edge-First restore, LOCAL COLD, LocalOutbox), sessionstate_internal.mmd (ILifecyclePort + StandaloneLifecycle adapter, ReconstructionSLA P95 < 50ms), Epic 4 (9 services with method signatures).

### Design Decisions

#### D1: Version-based lock, not TTL

The Single Writer lock (INV-01, INV-12) uses a monotonic `lock_version` counter in SS_CONTROL. On crash recovery, increment version — all old references are instantly stale. No waiting for TTL expiry. Single Concierge process per session guarantees no contention. TTL adds a stale-lock-wait window that version-based avoids entirely.

#### D2: Checkpoint every turn to LOCAL COLD

SQLite write < 1ms. Worst case on crash: lose 1 turn. K0 sync is fire-and-forget via Bridge — Bridge queues in LocalOutbox when K0 offline, drains on reconnect. This follows Bridge's Edge-First design: K1 works fully offline, K0 is optional enhancement.

#### D3: Never resume incomplete turns

LLM state is stateless (model does not remember previous call). Phase 1 (UltraBERT 22ms) is cheap to redo on the same input. Phase 2 cognitive tool state is lost. Resumption would require reconstructing partial LLM context — complex, fragile, and slow. Simpler: roll back the failed turn entirely. The client resends if desired.

#### D4: Experience layer is deferred, non-blocking

Experience states (EMOTIONAL_PROCESSING, NARRATIVE_WEAVING, ANTICIPATORY_RESPONSE) run as deferred tasks AFTER FSM returns to LISTENING. If the next user input arrives before experience processing completes, `turn_start()` preempts experience — the user always takes priority.

#### D5: DeltaAggregator timer is session-scoped

The 500ms window timer starts at `init()` and stops at `shutdown()`. It runs continuously across turns. `turn_end()` flushes the current window but does not stop the timer — deltas from sub-agents may arrive between turns (e.g., a late orchestrator result from a previous dispatch).

#### D6: Interrupted turns use abbreviated turn_end

When a user sends a new message mid-turn (DISPATCHING/COMPANIONING/PROGRESSING), the FSM enters INTERRUPT_HANDLING. This requires ending the current turn (INV-12: 1 turn/session) before starting the new one. The interrupted turn uses an **abbreviated turn_end**: skip history append (no final response was produced), skip telemetry (incomplete cost data), but still release lock, flush output queue, and checkpoint. The incomplete turn is recorded as `turn_status: INTERRUPTED` in SS_CONTROL for observability but does NOT consume a history slot. Rationale: an interrupted turn produced no user-visible response — there is nothing meaningful to persist as a conversation turn.

### Lifecycle Phase 1: `init(session_id)`

Order matters — dependencies flow downward. A step cannot succeed if the step above it has not completed.

| Step | Operation | Service / Port | Why this order |
|---|---|---|---|
| 1 | Create 9 service instances (no I/O) | FSMController, TurnProcessor, IntentProcessor, ComplexityRouter, ToolDispatcher, OutputManager, DeltaAggregator, ClarificationTracker, ContextAssembler | Services exist before ports bind |
| 2 | Connect 8 ports | IInputPort, IOutputPort, IClassificationPort, ILLMPort, IStatePort, IDispatchPort, IDeltaPort, IMemoryPort | Services need ports for step 3 |
| 3 | Restore session state (Edge-First) | `IStatePort.restore(session_id)` — LOCAL COLD first (K1 SQLite). K0 query via Bridge only if local checkpoint is stale/missing AND K0 status is ONLINE. Fresh session (empty 12 sections) if no checkpoint exists anywhere. ReconstructionSLA: P95 < 50ms | Must have state before anything reads it |
| 4 | Load persona | Read SS_PERSONA via IStatePort → configure PersonaEngine + ConversationalStyle | Persona drives all LLM prompt compilation |
| 5 | Initialize 7 circuit breakers → all CLOSED | CB_MODEL, CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP, CB_SESSIONSTATE, CB_SSE | Must be ready before any external call |
| 6 | Start subscriptions | `IDeltaPort.subscribe([k1.agent.*.delta.v1, k1.planner.delta.v1, k1.orchestration.delta.v1, k1.curiosity.delta.v1] + error stream)` + `DeltaAggregator.start_window()` (500ms timer begins) + Bridge SSE listener `subscribe(topics, cursor=last_acked_offset)` | Subscriptions last — system must be ready to process before events flow in |
| 7 | FSM → LISTENING | FSMController sets initial state | Terminal step — system is ready for input |

### Lifecycle Phase 2: `turn_start(message)`

Triggered by: LISTENING receives `k1.concierge.user_input` via IInputPort.

| Step | Operation | Service | Invariant |
|---|---|---|---|
| 1 | Acquire Single Writer lock | TurnProcessor — write `lock_version++` to SS_CONTROL via IStatePort. Reject with TurnActiveError if lock already held (INV-12) | INV-01, INV-12 |
| 2 | Increment turn_sequence_number | TurnProcessor — monotonic counter in SS_CONTROL. Used for crash detection: if lock is held but sequence does not match last completed, the previous turn crashed | Crash detection |
| 3 | Read HOT snapshot | `IStatePort.read(all_8_hot_sections) → Snapshot` — immutable copy for Phase 1 processing | Consistent reads across UltraBERT pipeline |
| 4 | Reset turn-scoped state | `ToolDispatcher.clear_buffer()` + `ClarificationTracker.reset_turn()` + `ContextAssembler.reset_budget()` | Clean slate per turn |
| 5 | Allocate turn timer | Budget envelope deadline from Epic 3 — initially set to tier-max (LOW: 2s, MED: 10s, HIGH: 45s, CRISIS: 5s). Narrowed after ComplexityRouter fires | Budget envelopes (Epic 3) |

After turn_start completes, FSM transitions LISTENING → ACKING and the UltraBERT pipeline (IntentProcessor) begins Phase 1.

### Lifecycle Phase 3: `turn_end()`

Triggered by: DELIVERING completes (final response sent to user + all cognitive tools applied).

| Step | Operation | Service / Port | Why this order |
|---|---|---|---|
| 1 | Flush OutputManager | `OutputManager.flush()` → deliver all queued events via IOutputPort | User must see all output before we release the lock |
| 2 | Append to history | `IStatePort.write(history_active, APPEND, Turn{user_msg, response, tool_calls[], tier, latency_ms})` via MutationGuard | Full turn record persisted. INV history <= 40 turns enforced by MutationGuard (evicts oldest) |
| 3 | Update telemetry | `IStatePort.write(telemetry, UPDATE, {tokens_used, cost, latency_ms, tier})` | Turn cost accounting for budget tracking |
| 4 | Release Single Writer lock | `IStatePort.write(control, UPDATE, {turn_lock: null, last_completed_sequence: turn_sequence_number})` | INV-01 released. Sequence number records clean completion |
| 5 | Checkpoint to LOCAL COLD | `IStatePort.checkpoint(session_id)` → K1 SQLite. All 12 sections (8 HOT + 4 WARM). Always succeeds (offline safe). < 1ms | Edge-First: LOCAL COLD before K0 |
| 6 | Checkpoint to K0 (fire-and-forget) | `IDeltaPort.emit(topic=session.checkpoint, envelope)` → Bridge → K0 command.submit. Does NOT wait for ack. If K0 OFFLINE: Bridge queues in LocalOutbox, drains on reconnect | K0 is enhancement, not dependency |
| 7 | Check experience triggers | `turn_count++`. If `% 25 == 0` → schedule EMOTIONAL_PROCESSING. If `% 20 == 0` → schedule NARRATIVE_WEAVING. If `% 30 == 0` → schedule ANTICIPATORY_RESPONSE | Deferred, non-blocking (D4) |
| 8 | FSM → LISTENING | Immediate transition. No blocking | Ready for next input |

### Lifecycle Phase 3a: `turn_end_abbreviated()` (Interrupt Path)

Triggered by: INTERRUPT_HANDLING needs to close current turn before re-ACKING with new input. Only invoked when user sends a new message during DISPATCHING, COMPANIONING, or PROGRESSING.

| Step | Operation | Notes |
|---|---|---|
| 1 | Cancel in-flight dispatches | Notify IDispatchPort to abandon pending CapabilityRequests. Sub-agents may still emit deltas — DeltaAggregator discards deltas tagged with the cancelled turn_sequence |
| 2 | Flush OutputManager | Deliver any queued events (partial progress messages the user should see) |
| 3 | Record interrupt | `IStatePort.write(control, UPDATE, {turn_status: INTERRUPTED, interrupted_at: now})` — observability only, does NOT append to history_active |
| 4 | Release Single Writer lock | `IStatePort.write(control, UPDATE, {turn_lock: null, last_completed_sequence: turn_sequence_number})` |
| 5 | Checkpoint to LOCAL COLD | Same as turn_end step 5 — write current state (pre-interrupt) to SQLite |
| 6 | Skip: history append | No final response produced — nothing meaningful to persist |
| 7 | Skip: telemetry update | Incomplete cost data — would pollute metrics |
| 8 | Skip: K0 checkpoint | No state change worth syncing — just an interrupted turn |
| 9 | Skip: experience triggers | Interrupted turns do not count toward experience scheduling |

After abbreviated turn_end completes, FSM immediately transitions to ACKING with the new user message. `turn_start()` fires for the new message.

### Lifecycle Phase 4: `shutdown()`

Graceful shutdown sequence. Called on process termination signal, session timeout, or explicit user session end.

| Step | Operation | Timeout | Notes |
|---|---|---|---|
| 1 | Stop accepting input | `IInputPort.close()` | Reject new user messages with SessionClosingError |
| 2 | Wait for active turn | 30s deadline | If mid-turn: let turn_end() complete naturally. If deadline exceeded: force turn_end_abbreviated() with turn_status: FORCE_CLOSED |
| 3 | Flush remaining async work | `DeltaAggregator.flush()` + `OutputManager.flush()` | Process any pending deltas and queued output |
| 4 | Final checkpoint | LOCAL COLD + Bridge checkpoint (wait up to 5s for K0 ack this time — best-effort sync on clean shutdown) | Last opportunity for K0 sync before process dies |
| 5 | Stop background processes | `DeltaAggregator.stop_window()` + `IDeltaPort.unsubscribe()` + Bridge SSE close | No more async events after this point |
| 6 | Disconnect ports (reverse of init) | IMemoryPort → IDeltaPort → IDispatchPort → IStatePort → ILLMPort → IClassificationPort → IOutputPort → IInputPort | LIFO teardown — last connected = first disconnected |

### Lifecycle Phase 5: `crash_recovery(session_id)`

Invoked on process restart after unclean termination. Design principle: never resume incomplete turns (D3).

| Step | Operation | Notes |
|---|---|---|
| 1 | Bootstrap | Create 9 service instances + connect 8 ports (same as init steps 1-2) |
| 2 | Detect incomplete turn | `IStatePort.read(control)` — check `turn_lock`. If set → previous turn crashed mid-execution. If null → clean shutdown occurred (proceed as normal init from step 5) |
| 3 | Rollback incomplete turn | Clear `turn_lock`. Increment `lock_version` (D1 — instant invalidation). Write `turn_status: ROLLED_BACK` + `rolled_back_sequence: <failed_turn_sequence>`. Record recovery event for observability |
| 4 | Reconcile Local Outbox | Check K1 SQLite outbox for pending Bridge commands queued before crash. If K0 ONLINE: drain queued commands. If K0 OFFLINE: leave queued (Bridge drains automatically on reconnect) |
| 5 | Restore from last checkpoint | Same as init step 3 — Edge-First restore from LOCAL COLD. Checkpoint reflects pre-crash state (last successful turn_end). At most 1 turn of data is lost (the crashed one) |
| 6 | Resume operations | Same as init steps 4-7: load persona, init circuit breakers (all reset to CLOSED), start subscriptions, FSM → LISTENING |
| 7 | Emit recovery telemetry | `IStatePort.write(telemetry, UPDATE, {crash_recovery_count++, last_recovery_at: now, rolled_back_turn: sequence})` |

**What is lost on crash**: Maximum 1 turn of conversation — the one that was executing when the crash occurred. The user's original input is gone from Concierge's perspective. The client layer (L0_EXTERNAL) must resend if desired. All previous turns are safe in LOCAL COLD.

### Service ownership map

Each lifecycle phase is owned by exactly one service that orchestrates the sequence:

| Phase | Owner | Delegates to |
|---|---|---|
| `init()` | FSMController | All 8 other services (construction), all 8 ports |
| `turn_start()` | TurnProcessor | ToolDispatcher (buffer clear), ClarificationTracker (reset), ContextAssembler (budget reset) |
| `turn_end()` | TurnProcessor | OutputManager (flush), IStatePort (writes), IDeltaPort (checkpoint emit) |
| `turn_end_abbreviated()` | TurnProcessor | OutputManager (flush), IStatePort (lock release + interrupt record), IDispatchPort (cancel) |
| `shutdown()` | FSMController | TurnProcessor (wait/force), DeltaAggregator (flush + stop), OutputManager (flush), all ports (disconnect) |
| `crash_recovery()` | FSMController | IStatePort (detect + rollback + restore), DeltaAggregator (start), all ports |

### State transitions diagram

```text
                    +---> [turn_start] ---> ACKING ---> ... ---> DELIVERING
                    |                                                 |
  init() ---> LISTENING <------------- [turn_end] <------------------+
                    |                                                 |
                    |         INTERRUPT_HANDLING <--- (user interrupt mid-turn)
                    |                |
                    |         [turn_end_abbreviated]
                    |                |
                    +<---------------+---> ACKING (new message)
                    |
              [shutdown] ---> (process exit)

  crash ---> [crash_recovery] ---> LISTENING
```

### Comparison with SessionState lifecycle

| Aspect | SessionState | Concierge |
|---|---|---|
| Lifecycle port | ILifecyclePort + StandaloneLifecycle adapter | FSMController owns lifecycle (no separate port — lifecycle IS the FSM) |
| Init complexity | Restore 12 sections from SQLite | Restore state + connect 8 ports + init 7 CBs + start subscriptions + 500ms timer |
| Checkpoint trigger | External (Concierge calls it) | Internal (turn_end fires checkpoint) |
| Recovery strategy | Partial hydration (P95 < 50ms) | Full restore from LOCAL COLD + turn rollback |
| Lock model | No locks (single writer is Concierge) | Version-based lock in SS_CONTROL |
| Interrupt handling | N/A (no turns) | Abbreviated turn_end (D6) |
| Background timers | None | DeltaAggregator 500ms window (session-scoped) |

### Diagram changes needed

1. Add `LIFECYCLE` subgraph inside `CONCIERGE` with 5 phase nodes (init, turn_start, turn_end, turn_end_abbreviated, shutdown, crash_recovery)
2. Each node shows step sequence and owning service
3. Add edges from lifecycle phases to services they invoke
4. Add edges from lifecycle phases to ports they use
5. Add `lock_version` and `turn_sequence_number` to SS_CONTROL node description

---

## Epic 6 — Concurrency Model

**Priority**: HIGH

**Gap**: No declared concurrency strategy. Is Concierge single-threaded? Actor-based? What happens when a new message arrives mid-turn?

### Design Decisions

**D1: Single-threaded async event loop (actor-based)**

One asyncio event loop per session. Cooperative multitasking via `await`. No multi-threading inside Concierge. This is the same actor pattern used by OrchestratorActor, PlannerAgent, and Fabric in the skeleton.

Why this model:

- No threading bugs — single thread rules out concurrent memory access
- INV-12 enforced by construction — cannot have 2 concurrent turns with 1 thread
- INV-17 enforced by construction — 1 loop = 1 FSM
- INV-13 compatible — FSM transitions are pure sync computation between awaits
- Consistent with K1 actor pattern — every major component uses mailbox + sequential processing

**D2: Session-per-task in shared process (not process-per-session)**

A single Python process hosts multiple Concierge instances, one per active session. Each session runs as its own asyncio Task with its own FSM, ports, services — logically isolated.

Why shared process:

- UltraBERT is 149M params — loading per-process wastes memory. Shared process loads once.
- Model Hub (LLM gateway) is shared infrastructure — connection pools reused across sessions.
- Lighter resource footprint per session (Task vs Process).
- Crash isolation: if a single Task fails, supervisor catches it and restarts only that session. LOCAL COLD persistence (Epic 5 D2) means the session restores from last checkpoint.
- Process-level crash (rare): all sessions restart from LOCAL COLD. Acceptable because crash_recovery phase is < 50ms P95.

Each Task owns: FSMController, TurnProcessor, all 9 services, all 8 port instances. Tasks do NOT share mutable state. All cross-session coordination goes through shared infrastructure (Model Hub, EventBus, Bridge) which is already thread-safe by design.

**D3: CONCIERGE_MAILBOX is the single entry point**

Everything enters as a message in the actor mailbox. Nothing bypasses it. The WFQ scheduler (ADR-0028) determines dequeue order.

| Source | Message Type | WFQ Priority | Rate |
|---|---|---|---|
| IInputPort | `UserInput` | REALTIME (3) | User typing speed |
| DeltaAggregator flush | `AggregatedBatch` | INTERACTIVE (2) | Every 500ms |
| EventBus errors | `ErrorEvent` | INTERACTIVE (2) | On failure |
| EventBus capability completion | `CapabilityComplete` | REALTIME (3) | Per dispatch |
| Proactive Decision | `ProactiveInterrupt` | BACKGROUND (1) | 3/day max |
| Bridge SSE events | `K0Event` | BACKGROUND (1) | Variable |
| ClarificationTracker escalation | `EscalationEvent` | INTERACTIVE (2) | On INV-09 breach |

REALTIME (user input, capability results) always dequeues before INTERACTIVE (deltas, errors) before BACKGROUND (proactive, K0 events).

**D4: All port I/O is awaited**

Within a turn, the FSM awaits every port call. This yields control to the event loop between I/O operations, enabling interrupt detection.

| Phase | Await Point | Typical Latency | What Happens |
|---|---|---|---|
| ACKING | `IClassificationPort.classify()` | ~22ms | UltraBERT inference |
| ACKING | `IStatePort.write()` (Phase 1) | ~0.02ms | Deterministic writes |
| ACKING | `ILLMPort.complete()` (ack + routing) | 200ms-2s | Signal tool + LLM call |
| DISPATCHING | `IDispatchPort.dispatch_direct()` | 500ms-2s | LOW tier Fabric call |
| DELIVERING | `ILLMPort.complete()` (final response) | 500ms-10s | Final response + cognitive tools |
| DELIVERING | `IStatePort.write()` (Phase 2) | ~0.1ms | Cognitive tool mutations |
| Any | `IMemoryPort.recall()` | 50ms-500ms | Bridge query (network) |

Between every `await`, the event loop runs — this is where interrupt detection happens (D5).

**D5: Interrupt detection at await boundaries**

When the FSM awaits any I/O, the event loop runs other callbacks (timer, I/O completions, mailbox receives). Before resuming the awaited continuation, the FSM checks CONCIERGE_MAILBOX for `UserInput` messages at REALTIME priority.

Interruptible vs non-interruptible states:

| State | Interruptible? | Reason |
|---|---|---|
| LISTENING | N/A | Waiting for input — not processing |
| ACKING | NO | Phase 1 writes in progress — interrupting violates INV-03 (Two-Phase ordering) |
| CLARIFYING | NO | Waiting for user answer — next input IS the answer, not an interrupt |
| DISPATCHING | YES | TaskEnvelope sent or Fabric call in-flight — can abort |
| COMPANIONING | YES | Waiting for tool results from Orchestrator — can abort |
| PROGRESSING | YES | Streaming progress — can abort |
| DELIVERING | NO | Near completion — queue interrupt for after turn_end() |
| INTERRUPT_HANDLING | NO | Already handling an interrupt — queue |

Interrupt detected in interruptible state:

1. FSM transitions to INTERRUPT_HANDLING
2. Execute `turn_end_abbreviated()` (Epic 5 Phase 3a — release lock, checkpoint, skip history append)
3. Execute `turn_start(new_message)` to begin new turn in ACKING

Interrupt detected in non-interruptible state:

1. Message stays in mailbox (or re-enqueued at REALTIME priority)
2. FSM continues current work uninterrupted
3. After `turn_end()`, next mailbox drain picks it up naturally

**D6: IInputPort bounded buffer — depth 3**

IInputPort buffers inbound user messages before they enter CONCIERGE_MAILBOX.

| Config | Value | Rationale |
|---|---|---|
| Max depth | 3 | Covers rapid typing (2-3 messages before first processes). More than 3 = broken or abusive. |
| On overflow | Reject with `BackpressureError` | Client layer (L0_EXTERNAL) shows "slow down" or queues locally. No silent drops. |
| Memory bound | ~12KB max | 3 messages at ~4KB each. Bounded by construction. |

Buffer sits BEFORE the mailbox. When drained, messages enter CONCIERGE_MAILBOX at REALTIME priority.

**D7: DeltaAggregator uses async timer, not a separate thread**

Consistent with Epic 5 D5 (session-scoped timer):

- `DeltaAggregator.start_window()` registers async timer callback (500ms interval) in the event loop
- IDeltaPort delivers deltas via async stream. `DeltaAggregator.receive()` buffers them in memory.
- Timer fires: `flush()` creates `AggregatedBatch`, enqueues in CONCIERGE_MAILBOX at INTERACTIVE priority
- FSM picks up the batch at next mailbox drain

No thread. No mutex. Timer is another event in the loop. Consistent with INV-14 (500ms fixed window).

**D8: Fire-and-forget operations are non-blocking sends**

Operations that do not need a response use non-blocking enqueue (return immediately):

| Operation | Port | Pattern | Why Fire-and-Forget |
|---|---|---|---|
| `dispatch_envelope(TaskEnvelope)` | IDispatchPort | Enqueue in Orchestrator mailbox | MED/HIGH async — results return via DeltaBus |
| Checkpoint to K0 | IDeltaPort | `emit(session.checkpoint)` | Bridge handles retry/buffering (Edge-First) |
| Output delivery | IOutputPort | `send(OutputEvent)` | SSE push — non-blocking write. DeliveryReceipt arrives async. |
| Experience layer trigger | Internal | Schedule deferred task | Low priority, runs between turns |

These never block the turn. The `await` returns immediately after the message is enqueued.

### Async Boundary Map

Every operation classified by execution model:

```
AWAITED (blocks current phase, resumes on completion):
  IClassificationPort.classify()     -- 22ms
  ILLMPort.complete()                -- 200ms to 30s
  IDispatchPort.dispatch_direct()    -- 500ms to 2s (LOW tier only)
  IStatePort.read()                  -- <1ms
  IStatePort.write()                 -- <1ms
  IStatePort.checkpoint()            -- <1ms (SQLite)
  IMemoryPort.recall()               -- 50ms to 500ms

FIRE-AND-FORGET (enqueue + return immediately):
  IDispatchPort.dispatch_envelope()  -- MED/HIGH to Orchestrator
  IDeltaPort.emit()                  -- checkpoint, feedback
  IOutputPort.send()                 -- SSE/WS push

TIMER-DRIVEN (async event loop callback):
  DeltaAggregator 500ms flush        -- session-scoped
  ConversationScheduler rhythm        -- delivery timing

DEFERRED (scheduled as low-priority event):
  Experience layer processing         -- between turns
  Proactive agent processing          -- between turns
```

### Threading Model (Runtime)

```
[Shared Process]
  |
  +-- UltraBERT (loaded once, shared read-only)
  +-- Model Hub (shared connection pool)
  +-- EventBus (shared pub/sub)
  +-- Bridge (shared K0 connection)
  |
  +-- [asyncio Event Loop]
        |
        +-- Session Task A (owns: FSM, 9 services, 8 ports)
        |     +-- drain CONCIERGE_MAILBOX (WFQ order)
        |     +-- await port I/O (yields to event loop)
        |     +-- check interrupt between awaits
        |     +-- timers: DeltaAggregator 500ms, ConversationScheduler
        |
        +-- Session Task B (owns: FSM, 9 services, 8 ports)
        |     +-- (same structure, fully isolated)
        |
        +-- Session Task N ...
        |
        +-- Shared I/O callbacks
              +-- IInputPort: user message arrives, routes to correct session Task mailbox
              +-- Bridge SSE: K0 event arrives, routes to correct session Task via EventBus
              +-- Model Hub: LLM response arrives, routes to awaiting session Task
```

Each session Task is logically single-threaded. Tasks share the event loop but never share mutable state. Cross-session routing is handled by session_id on every message.

### Mailbox Drain Protocol

Each iteration of the FSM main loop:

1. Dequeue highest-priority message from CONCIERGE_MAILBOX (WFQ)
2. Match message type:
   - `UserInput`: if LISTENING, execute `turn_start()`. If mid-turn + interruptible state, transition to INTERRUPT_HANDLING. If mid-turn + non-interruptible, re-enqueue.
   - `AggregatedBatch`: if mid-turn, apply deltas to current turn context. If LISTENING, apply to state (late deltas from previous dispatch).
   - `CapabilityComplete`: if in COMPANIONING/PROGRESSING, stage in ToolResultBuffer. Check if all results received, if so transition to DELIVERING.
   - `ErrorEvent`: route to FSMController.on_error(). Recovery or DELIVERING with degraded result.
   - `ProactiveInterrupt`: if LISTENING, process proactive message. If mid-turn, re-enqueue at BACKGROUND.
   - `EscalationEvent`: route to ClarificationTracker.escalate().
3. Execute FSM phase until next `await` or phase completion
4. Repeat

### Cross-reference with previous epics

| Epic | Concurrency Implication | Resolved By |
|---|---|---|
| Epic 1 (Ports) | All port calls must be async | D4: every port operation is awaited |
| Epic 2 INV-12 | 1 turn/session | D1: single-threaded, impossible to have 2 |
| Epic 2 INV-13 | FSM transition <= 1ms | Transitions are sync computation between awaits |
| Epic 2 INV-14 | 500ms delta window | D7: async timer callback in event loop |
| Epic 2 INV-17 | Single FSM | D1: one event loop task = one FSM |
| Epic 4 DeltaAggregator | Async (timer-driven) | D7: async timer, no thread |
| Epic 5 D1 | Version-based lock | Single-threaded: lock is a field check, no contention within session |
| Epic 5 D4 | Experience layer deferred | Deferred task in event loop, preemptable by user input |
| Epic 5 D5 | DeltaAggregator session-scoped | D7: timer lifecycle managed by FSMController |
| Epic 5 D6 | Abbreviated turn_end for interrupts | D5: interrupt detection at await boundaries |

### Diagram changes needed

1. Add `CONCURRENCY_MODEL` annotation to CONCIERGE_MAILBOX: "Actor: async event loop, 1 task/session, WFQ drain"
2. Add `BOUNDED_BUFFER` annotation to IInputPort: "depth=3, overflow=BackpressureError"
3. Add interrupt detection edge: `CONCIERGE_MAILBOX --> interrupt check --> FSM` between every await-point arc
4. Add session-per-task label to top-level CONCIERGE subgraph: "Session Task (shared process, isolated state)"
5. Add `FIRE_AND_FORGET` label on edges for dispatch_envelope, emit(checkpoint), send(output)
6. Update AGGREGATION_WINDOW node to include: "Timer: async callback, not thread"

---

## Epic 7 — Token Budget Management

**Priority**: HIGH

**Gap**: No token budget tracking. The whiteboard mentions 128K context windows and `summarize_context()` but the diagram has no budget allocation, tracking, or overflow handling. Epic 4 Service 9 (ContextAssembler) defines the service boundary and defers algorithms here.

### Scope boundary: Concierge only

Two separate token budget concerns exist in the architecture:

1. **Concierge's ContextAssembler** (THIS EPIC) — builds the prompt for Concierge's OWN LLM calls (ACKING ack, DISPATCHING prelim ack, DELIVERING final response, CLARIFYING question). Concierge decides what SessionState sections to include and enforces INV-18 through INV-21.

2. **Fabric's Context Budget Manager** (NOT this epic) — builds the prompt for spawned AGENT LLM calls. Fabric reads `required_context` from agent/tool contracts, reads SessionState sections, applies 128K budget. This is Fabric's problem. Whiteboard S7 step 3: "Context Builder reads SessionState sections, applies token budget (128K), injects into provider context." Whiteboard S16 #6: "Agent Prompt Injection" is a separate design session.

Both follow the same architectural principle (declare which SessionState sections you need, read only those) but they are owned by different components.

### The two-tier budget model

**Tier A: INPUT budget (context window)** — How much context goes INTO the LLM call. This is INV-18 (128K hard cap). Concierge controls this by choosing what to include. `summarize_context()` compresses when near the limit.

**Tier B: OUTPUT budget (response tokens)** — How many tokens the LLM generates in response. This is the `max_tokens` field in `ILLMPort.complete(prompt, tools[], budget)`. The PROVIDER enforces this — Concierge just passes the number. LOW=500, MED=2K, HIGH=8K, ack=150, prelim=200, clarify=300.

Concierge truly "manages" Tier A. Tier B is a number we hand to the provider.

### Design Decisions

**D1: Token estimation via character ratio, not exact counting**

We cannot do exact token counting because BYOLLM means unknown tokenizer. Different LLM providers use different tokenizers (GPT, Llama, Mistral). Instead:

- Estimate tokens as `ceil(char_count / 3.5)` — conservative estimate that works across major tokenizer families (real ratio is typically 3.5-4.0 chars/token for English)
- This overestimates by ~10-15%, which is safe — better to leave headroom than overflow
- The provider's actual tokenizer does the real counting when the call executes
- If a provider rejects a call as too long, `ILLMPort` returns a `ContextOverflowError` and ContextAssembler retries with summarization

Why not load tiktoken or a specific tokenizer? We'd need a tokenizer per provider, keep them in sync, and handle provider tokenizer updates. The 3.5 ratio is good enough for pre-call budget planning. The provider is the source of truth.

**D2: Section inclusion via declared context profiles**

Each Concierge LLM call type has a **context profile** — a declared list of which SessionState sections to include. This mirrors the `required_context` pattern from whiteboard S15 where every tool/agent contract explicitly declares which sections it needs. Same principle: every LLM caller declares what it needs upfront. No dynamic reasoning about what to include.

| Call Type | Context Profile (Sections) | Output Budget | Rationale |
|---|---|---|---|
| `acknowledge_request()` | control, scoreboard, affective_now, narrative_active, meta | 150 tokens (INV-19) | Fast ack — conversational state only, no history |
| Preliminary ack (MED/HIGH) | control, scoreboard, affective_now, narrative_active | 200 tokens (INV-20) | Same as ack — just a "working on it" |
| Clarification question | control, scoreboard, clarifications, beliefs_active | 300 tokens (INV-21) | Needs to know what's missing |
| LOW DELIVERING | control, beliefs_active, scoreboard, affective_now, narrative_active, persona, history_active[last 3], tool_results[] | 500 tokens | Coherent short response with tool result |
| MED DELIVERING | control, beliefs_active, scoreboard, affective_now, narrative_active, persona, history_active[last 5], tool_results[] | 2,000 tokens | Longer response needs more history |
| HIGH DELIVERING | control, beliefs_active, beliefs_history, scoreboard, affective_now, narrative_active, persona, history_active[full 10], tool_results[] | 8,000 tokens | Complex task — full conversational history |

These profiles are static lookups selected by `(call_type, tier)`. Not dynamic calculations. ContextAssembler picks a profile, reads those sections via `IStatePort.read(profile.sections)`, assembles the prompt. Same interface Fabric's Context Builder uses — both are multi-readers under ADR-0017 (lock-free, <1ms read latency).

**D3: Summarization trigger at 80% of 128K**

- ContextAssembler calculates estimated token count after section assembly (D1)
- If estimated tokens > 102,400 (80% of 128K): trigger summarization
- `summarize()` compresses history_active and beliefs into a condensed summary via `ILLMPort` call
- After summarization, re-estimate. If still > 102,400: truncate oldest history turns until under budget
- The 80% threshold leaves ~25K tokens headroom for:
  - Tool definitions in the prompt (~2-5K tokens for 13 tools)
  - System prompt + persona instructions (~3-5K tokens)
  - The output generation budget (up to 8K for HIGH)
  - Estimation error margin from D1

Why 80% not 90%? Our estimation is conservative (D1 overestimates by 10-15%) and we need room for tool definitions and system prompts that are hard to estimate precisely. Being 10% too eager on summarization costs one extra LLM call (rare, acceptable). Being 10% too late means context overflow and a failed call.

In practice, only HIGH DELIVERING calls can approach 128K. LOW/MED calls include ~20-40K tokens max — they will never hit the ceiling. Summarization is a HIGH-tier concern.

**D4: Per-turn cumulative token tracking**

Within a single turn, multiple LLM calls may happen:

| Tier | LLM Calls Per Turn | Approximate Cumulative Tokens |
|---|---|---|
| LOW | 1-2 (ack + response) | ~1K input + 650 output |
| MED | 2-3 (ack + prelim ack + final response) | ~5K input + 2.4K output |
| HIGH | 2-3 (ack + prelim ack + final response) | ~20K input + 8.4K output |

ContextAssembler tracks per turn:

- `input_tokens_consumed`: cumulative input tokens across all LLM calls in this turn
- `output_tokens_consumed`: cumulative output tokens reported by provider in LLMResponse
- `llm_calls_count`: number of LLM calls this turn

Reset at `turn_start()` via `ContextAssembler.reset_budget()` (Epic 5). Written to SS_TELEMETRY at `turn_end()`.

The provider's `LLMResponse` includes actual token counts (input + output). ContextAssembler uses these actuals for tracking — the D1 estimate is only for pre-call budget planning.

**D5: Output budgets passed to the provider, not enforced by Concierge**

The `max_tokens` field in the budget object tells the provider to stop generating at that limit:

| Call Type | max_tokens | Source |
|---|---|---|
| `acknowledge_request()` | 150 | INV-19 |
| Preliminary ack (MED/HIGH) | 200 | INV-20 |
| Clarification question | 300 | INV-21 |
| LOW response | 500 | Epic 3 envelope |
| MED final response | 2,000 | Epic 3 envelope |
| HIGH final response | 8,000 | Epic 3 envelope |

Concierge does NOT count output tokens and truncate. The provider stops at `max_tokens`. If the provider ignores `max_tokens` (broken provider), the response is accepted anyway — it's a budget guideline, not a crash condition. The extra tokens are logged in telemetry for provider quality tracking.

**D6: `summarize_context()` dual identity — tool vs internal method**

Two paths, same compression logic, different triggers:

1. **As a Read Tool** (LLM-initiated): The LLM calls `summarize_context()` as a tool during DELIVERING when it detects context is too long. Routed by ToolDispatcher to ContextAssembler. Returns compressed context. This is the LLM asking for compression.

2. **As an internal pre-call check** (system-initiated): Before every `ILLMPort.complete()`, ContextAssembler runs `needs_summarization()`. If assembled context > 80% of 128K, it compresses internally. This is NOT a tool call — invisible to the LLM. Safety net.

Both produce the same result (compressed context). Difference is who initiates: the LLM (conscious decision via tool call) or the system (automatic pre-call guard). System-initiated fires even if the LLM forgets to call the tool. The tool and the method share the same compression pipeline but have different entry points.

**D7: No cross-session token budget sharing**

Each session's ContextAssembler tracks its own budget independently. Sessions in the shared process (Epic 6 D2) do not share token budgets. There is no global "tokens per minute" quota at the Concierge level — that belongs to Model Gateway / LLM_REQUEST_BUS (rate limiting, provider quota enforcement). Concierge only cares about per-session, per-turn budgets.

**D8: Same provider for summarization (not a separate model)**

When ContextAssembler needs to compress context (D3), it uses the same `ILLMPort` provider as the main response — not a separate cheaper/smaller model. Summarization should be rare (only when context > 80% of 128K, which means sessions with 20+ turns of rich content). Adding a second model configuration for a rare operation is not worth the complexity. If summarization latency becomes a problem in practice, a separate model can be configured behind `ILLMPort` via the adapter — no ContextAssembler changes needed.

### Context Assembly Pipeline

```
turn_start() -> ContextAssembler.reset_budget()

Before each ILLMPort.complete() call:
  1. Select context profile (D2) based on (call_type, tier)
  2. Read sections via IStatePort.read(profile.sections)
  3. Assemble: system_prompt + persona + sections + tool_results + tool_definitions
  4. Estimate tokens (D1): ceil(chars / 3.5)
  5. If estimate > 102,400 (D3):
     a. summarize(history + beliefs) via ILLMPort
     b. Replace full sections with summary
     c. Re-estimate. If still over: truncate oldest history turns
  6. Build budget object:
     {max_tokens: profile.output_budget, timeout_ms: 30000, context_window: 128000}
  7. Call ILLMPort.complete(assembled_prompt, tools, budget)
  8. On response: track_usage(response.input_tokens, response.output_tokens)

turn_end() -> write {input_tokens_consumed, output_tokens_consumed, llm_calls_count} to SS_TELEMETRY
```

### Cross-reference with previous epics

| Epic | Token Budget Implication | Resolved By |
|---|---|---|
| Epic 1 (ILLMPort) | `complete(prompt, tools[], budget)` — budget param exists | D5: budget object built by ContextAssembler |
| Epic 2 INV-18 | 128K hard cap per LLM call | D3: summarization at 80% threshold |
| Epic 2 INV-19/20/21 | Output token caps (150/200/300) | D5: passed to provider as max_tokens |
| Epic 3 envelopes | LOW/MED/HIGH output budgets (500/2K/8K) | D5: max_tokens per call type |
| Epic 3 | `complete(prompt, tools[], budget)` protocol | D5: ContextAssembler builds the budget object |
| Epic 4 Service 5 | ToolDispatcher routes `summarize_context()` as Read Tool | D6: tool path routed to ContextAssembler |
| Epic 4 Service 9 | ContextAssembler methods defined, algorithms deferred | D1-D8: algorithms for each method |
| Epic 5 | `reset_budget()` at turn_start, telemetry write at turn_end | D4: cumulative tracking, reset per turn |
| Epic 6 D2 | Session-per-task in shared process | D7: no cross-session budget sharing |

### Diagram changes needed

1. Add `CONTEXT_PROFILES` annotation inside ContextAssembler node: "6 static profiles by (call_type, tier)"
2. Add `TOKEN_ESTIMATOR` annotation: "ceil(chars / 3.5), conservative cross-tokenizer"
3. Add `SUMMARIZATION_TRIGGER` edge: ContextAssembler --> needs_summarization check --> ILLMPort (if > 80% of 128K)
4. Add `BUDGET_OBJECT` annotation on ILLMPort.complete() edges: "{max_tokens, timeout_ms, context_window}"
5. Add `PER_TURN_TRACKING` annotation to SS_TELEMETRY: "input_tokens, output_tokens, llm_calls per turn"
6. Label `TOOL_SUMMARIZE_CONTEXT` edge to ContextAssembler: "LLM-initiated path (Read Tool)"
7. Label ContextAssembler internal edge: "System-initiated path (pre-call guard)"

---

## Epic 8 — Error and Recovery Paths

**Priority**: MEDIUM

**Gap**: No error handling flows. Every path in the diagram is the happy path. Real systems fail. The skeleton defines 7 circuit breakers and a FAILURE_RECOVERY supervisor, the concierge diagram shows CB fallback edges, and the whiteboard resolves plan step failure in Q3 — but no epic has specified what Concierge does when a port call fails mid-turn, how errors are classified, or how severity determines recovery strategy.

### Scope: errors within a running turn

Epic 5 already handles crash recovery (session-level restart with last checkpoint). This epic handles errors that occur DURING a turn — when a port call fails, a tool times out, or output validation catches hallucinations. The goal: keep the turn alive when possible, degrade gracefully when not, and never leave the user without a response.

### What already exists (from previous epics)

- **Epic 5 D3**: `crash_recovery()` — restores from last checkpoint after process crash. Session-level, not turn-level.
- **Epic 6 D3**: `ErrorEvent` message type in CONCIERGE_MAILBOX — downstream errors route back to FSM.
- **Epic 7 D1**: `ContextOverflowError` from `ILLMPort` — triggers summarization retry.
- **Skeleton**: 7 CBs (CB_MODEL, CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP, CB_SESSIONSTATE, CB_SSE), FAILURE_RECOVERY supervisor (<2s detection, blacklist 3 crashes/10min), OUTPUT_VALIDATION pipeline (T1/T2/T3).
- **Whiteboard Q3**: Plan step failure — 2 retries, then graceful failure, partial results, user decides.

This epic fills the gap between "crash recovery" (Epic 5) and "happy path" (everything else): what happens when a single port call fails within a healthy, running turn.

### Design Decisions

**D1: Three error severity levels**

Every port error is classified into one of three severity levels. The severity determines recovery strategy:

| Severity | Meaning | Recovery | User Impact |
|---|---|---|---|
| RECOVERABLE | Transient failure, can retry or use fallback | Retry/fallback within the same phase, no state change | None — user never knows |
| DEGRADED | Capability lost but turn can complete with reduced quality | Skip failed capability, continue with what's available | User gets a response but it may be less complete |
| TERMINAL | Cannot produce any meaningful response for this turn | Transition to DELIVERING with error response | User gets an error message explaining what happened |

Key constraint: **errors converge on existing DELIVERING state**. No new FSM states needed. RECOVERABLE stays in current phase. DEGRADED continues to DELIVERING with partial results. TERMINAL jumps to DELIVERING with an error response. The FSM topology from Epic 5 is unchanged.

**Per-port severity classification:**

| Port | RECOVERABLE | DEGRADED | TERMINAL |
|---|---|---|---|
| IClassificationPort | timeout (use heuristic) | — | — |
| ILLMPort | timeout/5xx (retry once) | CB OPEN (canned response) | 3 consecutive failures in same turn |
| IStatePort | MutationGuard rejection (skip write) | read timeout (stale data warning) | — |
| IDispatchPort | step failure (retry per Q3) | orchestrator CB OPEN (tier degrade) | all degradation levels exhausted |
| IDeltaPort | emit failure (log + skip) | — | — |
| IMemoryPort | recall timeout (skip memory) | — | — |
| IOutputPort | send failure (retry) | SSE CB OPEN (buffer for reconnect) | — |

Note: **IMemoryPort, IOutputPort, and IDeltaPort can never be TERMINAL.** Edge-First design (whiteboard S1) guarantees the system works without K0 storage, without output delivery, and without delta emission. These are best-effort services. If memory recall fails, Concierge responds without memory context. If output delivery fails, responses are dead-lettered for client replay. If delta emission fails, the turn completes normally and the missing delta is logged.

**D2: IClassificationPort failure — heuristic keyword fallback**

When UltraBERT times out or fails:

1. CB_MODEL tracks failures (threshold: 3 failures/min, timeout: 30s per skeleton)
2. If CB_MODEL is CLOSED (normal): retry once with halved timeout (11ms)
3. If retry fails OR CB_MODEL is OPEN: use **heuristic keyword fallback**

Heuristic fallback rules (applied in order, <1ms execution):

| Pattern | Classification | Complexity |
|---|---|---|
| Contains crisis keywords (harm, suicide, emergency, danger) | CRISIS | — (bypasses complexity) |
| Contains question mark only, <20 words | conversational | LOW |
| Contains "remind", "schedule", "set", "add to" | task/command | MED |
| Contains "plan", "help me with", "figure out" | planning/analysis | HIGH |
| Default (no match) | conversational | LOW |

**CRISIS keyword detection is non-negotiable.** Even in total classification failure, the keyword scan runs. It is a hardcoded string match — no ML, no LLM, no external dependency. If the keyword list matches, the turn is treated as CRISIS regardless of any other failure state.

The heuristic defaults to LOW because the safest failure mode is to treat unknown input as simple conversation. Wrong classification at LOW means the user gets a basic response and can rephrase. Wrong classification at HIGH means wasted orchestration resources. Fail safe, not fail expensive.

**D3: ILLMPort failure — 3-level cascade**

LLM failures are the most impactful because Concierge's core job is generating responses. The cascade:

```
Level 1: RETRY
  - Timeout or 5xx from provider
  - Retry once with same prompt
  - If success: continue normally (RECOVERABLE)

Level 2: HALF-OPEN PROBE (CB_MODEL)
  - Level 1 failed, CB_MODEL trips to OPEN
  - Wait for CB half-open window (30s per skeleton)
  - Send probe request (minimal prompt: "respond with OK")
  - If probe succeeds: CB closes, retry original request
  - If probe fails: CB stays OPEN, fall to Level 3

Level 3: CANNED RESPONSE (CB_MODEL OPEN)
  - No LLM available
  - Select canned response by call type
  - Transition to DELIVERING with canned response
  - DEGRADED severity — user gets a response but not LLM-generated
```

**Canned response table:**

| Call Type | Canned Response | Rationale |
|---|---|---|
| acknowledge_request (ack) | "Got it, I'm working on this." | Generic ack, no personalization needed |
| Preliminary ack | "Still working on your request." | Status update, no content needed |
| Clarification question | "I need more information. Could you rephrase or add details?" | Generic clarification prompt |
| LOW DELIVERING | "I wasn't able to generate a full response right now. Please try again in a moment." | Honest failure disclosure |
| MED DELIVERING | "I'm having trouble processing this request. The system is experiencing temporary issues. Please try again shortly." | Slightly more detailed for complex requests |
| HIGH DELIVERING | "I'm unable to complete this complex request right now due to a temporary service issue. Your request has been noted and you can retry when the system recovers." | Acknowledges complexity, suggests retry |
| CRISIS | "If you or someone you know is in crisis, please contact emergency services (911) or the 988 Suicide and Crisis Lifeline." | **Static hardcoded string. Zero dependencies. No LLM, no template, no service call.** |

**The CRISIS canned response is a static string constant.** It does not go through any service, any template engine, or any LLM. It is a hardcoded string that is returned directly from the FSM's crisis handling path. This is the absolute last-resort safety net — it works even if every other system component is down. It is the ONE response that can never fail to deliver.

**D4: IStatePort failure — MutationGuard rejection and emergency mode**

Two failure modes for SessionState writes:

**MutationGuard rejection** (normal operation):

- MutationGuard rejects a write because: wrong phase for this section, version conflict, or section locked
- Severity: RECOVERABLE
- Action: log the rejected write, skip it, continue the turn
- The write was invalid according to the contract — skipping it is correct behavior
- No retry: if MutationGuard says no, the write should not have been attempted. Log as a bug indicator.

**Read timeout / emergency mode** (>=95KB SessionState, per skeleton):

- SessionState exceeds 95KB, approaching 100KB hard limit
- IStatePort enters emergency mode: wait 50ms for GC/compaction, retry read once
- If retry succeeds: continue with data (RECOVERABLE)
- If retry fails: continue with stale cached data + log warning (DEGRADED)
- Stale data means the response may reference slightly outdated context. Acceptable for one turn.

**IStatePort is never TERMINAL** because Concierge can always produce a response without fresh state. The ack, the LLM call, the output — none of them strictly require a successful state read to function. The response quality degrades but the turn completes.

**D5: IDispatchPort failure and tier degradation cascade**

When Orchestrator/Planner/Fabric fails to execute a dispatched plan:

**Plan step failure (whiteboard Q3 resolution):**

- Each plan step gets 2 retries
- After 2 retries: graceful failure for that step
- Partial results from successful steps are returned to Concierge
- Concierge presents partial results to user: "I completed X but couldn't finish Y. Would you like me to try Y again?"

**Tier degradation cascade:**
When the dispatched tier fails entirely (not just a step):

```
HIGH fails (CB_ORCHESTRATOR OPEN or plan execution fails completely)
  -> Degrade to MED: skip planning, use direct tool dispatch

MED fails (tool dispatch fails)
  -> Degrade to LOW: conversational response only, no tools

LOW fails (LLM fails)
  -> Canned response (D3 Level 3)
```

Each degradation level strips a capability layer but keeps the turn alive:

| Degradation | What's Lost | What Remains |
|---|---|---|
| HIGH -> MED | Multi-step planning, agent orchestration | Direct tool calls, LLM response |
| MED -> LOW | Tool execution, external integrations | Pure LLM conversational response |
| LOW -> canned | LLM generation | Static pre-written response |

The degradation is logged in SS_TELEMETRY with the original tier and the degraded tier. The user is informed when degradation occurs: "I wasn't able to fully process this as planned, but here's what I can offer." No silent quality reduction.

CB_ORCHESTRATOR (60s timeout, 2 failures/min per skeleton) controls the HIGH->MED transition. CB_PLANNER (45s, 2/min) also triggers MED fallback since planning is skipped. These CBs live in adapters (see CB ownership below).

**D6: Tool execution — per-category recovery**

Epic 4 defines 13 tools across 4 categories (locked in whiteboard S3). Each category has different failure characteristics:

| Category | Tools | Timeout | Retry | On Failure |
|---|---|---|---|---|
| Cognitive (6) | update_scoreboard, update_beliefs, update_clarifications, update_narrative, refine_affect, promote_belief | Per-tool (LLM-dependent, shares ILLMPort timeout) | 1 retry (same as ILLMPort D3) | Skip the cognitive update. Turn continues — the state section is not updated this turn but no user-visible impact. Log missed update for observability |
| Read (3) | recall_memory, discover_capabilities, summarize_context | Per-tool (recall: 50-500ms via IMemoryPort, discover: <100ms via IDispatchPort, summarize: LLM-dependent) | 1 retry | Skip tool, note in response context: "I couldn't access [X] right now." Response generated without that context |
| Action (3) | invoke_capability, spawn_via_fabric, execute_workflow | Per-tool (invoke: 500ms-2s via IDispatchPort, spawn: 1-5s, workflow: variable) | Per whiteboard Q3: 2 retries per plan step | Report partial results to user. Tier degradation cascade (D5) if all retries fail |
| Signal (1) | acknowledge_request | LLM generation (~150 tokens) + SSE delivery (~5ms) | 1 retry for LLM, 3 retries for delivery (D7) | Silent skip — user does not see intent ack but the turn continues normally. The final response in DELIVERING still arrives |

CB_MCP (10s timeout, 3 failures/min per skeleton) tracks tool-level failures. When CB_MCP opens for a specific tool, that tool is marked as `unavailable` in the tool manifest for subsequent turns. ToolDispatcher skips unavailable tools and reports them in the response context.

**INV-08 (tool timeout) is enforced even during retries.** A retry does not get a fresh timeout budget — it shares the original tool's time allocation. If a tool's budget is 200ms and the first attempt takes 150ms, the retry gets 50ms. This prevents retries from cascading into latency violations.

**D7: IOutputPort failure — retry policy and dead-letter**

Output delivery (SSE/WebSocket push) can fail due to client disconnect, network issues, or SSE channel problems.

| Output Type | Retry Policy | Dead-Letter |
|---|---|---|
| REALTIME (ack, response) | 3 retries, 100ms backoff | Yes — must reach user |
| PROGRESS (prelim ack, status) | 1 retry, no backoff | Yes — useful but not critical |
| BACKGROUND (delta notification) | 0 retries | No — ephemeral |

**Dead-letter queue:**

- Failed REALTIME and PROGRESS outputs are written to SS_TELEMETRY section as dead-letter entries
- Maximum 10 dead-letter entries per session (oldest evicted)
- When client reconnects (SSE reconnect or new WebSocket), client sends `last_event_id`
- Concierge replays dead-lettered events from SS_TELEMETRY that have event_id > last_event_id
- Dead-letter entries expire after session ends — no cross-session persistence

CB_SSE (5s timeout, 3 failures/min per skeleton) tracks output delivery. When CB_SSE opens:

- Output is buffered in memory (bounded: 5 messages max)
- When CB_SSE closes (client reconnects): flush buffer in order
- If buffer overflows: oldest non-CRISIS messages are dropped. CRISIS messages are never dropped from buffer.

**D8: Output validation — retry, repair, degrade**

The skeleton defines a T1/T2/T3 output validation pipeline. This is where hallucination handling lives:

**T1: Format validation (sync, <1ms)**

- Check: response is valid text, within max_tokens, contains no raw template markers
- On failure: retry LLM call once with same prompt (RECOVERABLE)
- 2 retries max. After 2: accept as-is with format warning in telemetry

**T2: Safety validation (sync, <5ms)**

- Check: no PII leakage, no prompt injection echoing, content policy compliance
- On failure: auto-repair by stripping flagged content
- If >50% of response stripped: regenerate with restricted prompt (add "avoid discussing [flagged topics]")
- If regeneration also fails T2: use canned response for the call type (D3)

**T3: Belief consistency (async, <50ms)**

- Check: response claims vs active beliefs in SessionState (beliefs_active section)
- Detect contradictions: response states X, beliefs say not-X
- On contradiction found:
  1. Strip contradicted claims from response
  2. If >50% of response contradicted: flag as hallucination
  3. Hallucination handling: retry once with reduced context (drop history_active, keep only beliefs_active + current input)
  4. If retry also hallucinates: accept the stripped version with a caveat appended: "Note: I may not have the most current information on this."
- T3 is best-effort. It catches obvious contradictions but cannot detect novel hallucinations (claims about things not in beliefs). That's acceptable — the belief system is the source of truth, and contradicting it is the most harmful hallucination type.

**Validation pipeline flow:**

```
LLM response
  -> T1 format check
     FAIL: retry(2) -> accept with warning
  -> T2 safety check
     FAIL: strip -> if >50% stripped: regenerate -> if still fails: canned response
  -> T3 belief consistency
     FAIL: strip contradictions -> if >50%: retry with reduced context -> if still fails: accept stripped + caveat
  -> PASS: deliver to user via IOutputPort
```

### Circuit Breaker ownership: adapters, not services

All 7 circuit breakers live inside their respective port adapters:

| CB | Adapter | Port |
|---|---|---|
| CB_MODEL | UltraBERTAdapter, LLMGatewayAdapter | IClassificationPort, ILLMPort |
| CB_ORCHESTRATOR | OrchestratorAdapter | IDispatchPort |
| CB_PLANNER | PlannerAdapter | IDispatchPort (planning sub-call) |
| CB_FABRIC | FabricAdapter | IDispatchPort (execution sub-call) |
| CB_MCP | MCPToolAdapter | IDispatchPort (tool execution) |
| CB_SESSIONSTATE | SessionStateAdapter | IStatePort |
| CB_SSE | SSEAdapter | IOutputPort |

**Why adapters, not services?** Hexagonal architecture (Epic 1). Services call port interfaces. They don't know or care about circuit breaker state. The adapter decides: "Is my CB open? If yes, return the CB-open error variant. If no, attempt the real call." Services see port errors (timeout, unavailable, rejected) — they never see CB state directly.

This means:

- FSMController never queries CB state. It receives errors through ports and applies severity classification (D1).
- ToolDispatcher never checks CB_MCP. It calls `IDispatchPort.execute_tool()` and gets either a result or a tool-unavailable error.
- ContextAssembler never checks CB_MODEL. It calls `ILLMPort.complete()` and gets either a response or an LLM-unavailable error.

The adapter is the boundary where infrastructure concerns (CB state, retry logic, timeout enforcement) meet domain logic (port interface). This is exactly where they belong.

### Error flow through the FSM

```
Any FSM phase (CLASSIFYING, ACKING, DISPATCHING, DELIVERING, CLARIFYING)
  |
  Port call fails
  |
  Classify severity (D1 table)
  |
  +-- RECOVERABLE: retry/fallback within same phase, continue
  |
  +-- DEGRADED: log degradation, adjust response context, continue to DELIVERING
  |
  +-- TERMINAL: log terminal error, select error response, transition to DELIVERING
  |
  DELIVERING phase:
    - Normal response (no error)
    - Degraded response (partial results, canned ack, reduced tier)
    - Error response (terminal — explain failure, suggest retry)
    |
    Output validation (D8: T1 -> T2 -> T3)
    |
    IOutputPort.send() with retry policy (D7)
    |
    turn_end() — write error telemetry to SS_TELEMETRY
```

No new FSM states. Errors resolve INTO the existing state machine, not around it.

### Cross-reference with previous epics

| Epic | Error Implication | Resolved By |
|---|---|---|
| Epic 1 (Ports) | Each port can fail — need per-port error handling | D1: severity table per port, CB in adapters |
| Epic 2 INV-05 | CRISIS override for safety | D2: keyword scan is non-negotiable, static CRISIS response |
| Epic 2 INV-08 | Tool timeout enforcement | D6: per-category timeout, retries share budget |
| Epic 3 envelopes | Latency budgets for each operation | D6: retry within remaining budget, not fresh budget |
| Epic 4 Services | Services call ports, receive errors | CB ownership: services see port errors, never CB state |
| Epic 4 OutputManager | Output delivery via IOutputPort | D7: retry policy by output type, dead-letter queue |
| Epic 4 ContextAssembler | ILLMPort.complete() can fail | D3: 3-level cascade, canned responses |
| Epic 5 crash_recovery | Session-level restart | This epic: turn-level recovery (different scope) |
| Epic 6 D3 ErrorEvent | Error routing via mailbox | D1: ErrorEvent carries severity, FSM classifies and acts |
| Epic 7 D1 ContextOverflowError | Provider rejects context | D3 Level 1: retry with summarization (already in Epic 7) |

### Diagram changes needed

1. Add `ERROR_SEVERITY` annotation to CONCIERGE_FSM: "RECOVERABLE / DEGRADED / TERMINAL"
2. Add error edges from each port adapter back to FSM with severity labels
3. Add `HEURISTIC_FALLBACK` node inside IClassificationPort adapter: "keyword scan, <1ms"
4. Add `CANNED_RESPONSES` data store: "7 static responses by call_type"
5. Add `TIER_DEGRADATION` edge: HIGH -> MED -> LOW -> canned, inside DISPATCHING phase
6. Add `DEAD_LETTER` annotation to SS_TELEMETRY: "max 10/session, replay on reconnect"
7. Add `OUTPUT_VALIDATION` pipeline: T1 -> T2 -> T3 between LLM response and IOutputPort.send()
8. Label all CB nodes with their owning adapter (not service)
9. Add `CRISIS_STATIC` annotation: "hardcoded string, zero dependencies" on crisis response path

### Tension E Resolution: Skeleton Residual Complexity

When the concierge.mmd diagram is updated with all 10 epics, the skeleton (`k1_cognitive_architecture_skeleton.mmd`) needs corresponding cleanup to avoid duplication and confusion:

| Skeleton Element | Issue | Resolution |
|---|---|---|
| `L3_EMPATHY` (Theory of Mind, Mental Model, Predictive Completion) | Partially duplicated by Concierge internal ENGINES subgraph | Keep in skeleton ONLY if it becomes a standalone external service with its own lifecycle. Currently these are FSMController sub-components (Epic 4 D3). Remove from skeleton's L3 and note "see concierge.mmd ENGINES subgraph" |
| `PROACTIVE_AGENT_FLOW` | Partially external (CuriosityAgent, ProactiveDecision) and partially managed via IDeltaPort inside Concierge | Keep in skeleton as external touchpoint. Concierge interacts via IDeltaPort (inbound deltas) and IOutputPort (proactive messages to user). No internal overlap |
| `RETENTION_LIFECYCLE` | K0 concern referenced in checkpoint flows | Keep in skeleton unchanged. Concierge touches retention only via Bridge checkpoint fire-and-forget (Epic 5 turn_end step 6). No internal overlap |
| `L1_CONCIERGE` in skeleton vs `CONCIERGE` in concierge.mmd | Skeleton has a summarized view; concierge.mmd has full detail | Skeleton should reference concierge.mmd for internals: "See k1/concierge/concierge.mmd for internal architecture." Skeleton keeps the L1 subgraph as a collapsed summary (FSM states, tool categories, output channel) without duplicating service/port/invariant detail |

This cleanup should happen AFTER all 10 concierge.mmd epics are implemented in the diagram, not before. Premature skeleton edits would create drift during the Epic 1-8 diagram update process.

---

## Epic 9 — Milestone and Status Tracking

**Priority**: MEDIUM

**Gap**: No implementation milestones. Cannot track progress or define "done" for Concierge.

**What to add**:

| Milestone | Scope | Status |
|---|---|---|
| M1 | FSM core + turn lifecycle | Not Started |
| M2 | UltraBERT integration + complexity routing | Not Started |
| M3 | Cognitive tools + read tools | Not Started |
| M4 | Tier routing (LOW/MEDIUM/HIGH) | Not Started |
| M5 | Output system + delivery | Not Started |
| M6 | Delta aggregation + DeltaBus | Not Started |
| M7 | Signal tools + acknowledge_request() | Not Started |
| M8 | Experience layer + heuristics | Not Started |

**Reference**: SessionState tracks M1-M4 with explicit status (ALL COMPLETE).

---

## Epic 10 — Testing Strategy

**Priority**: LOW (depends on Epics 1-4)

**Gap**: No test specifications. Without services and ports, there is nothing to test. Once Epics 1-4 land, testing strategy can be defined.

**What to add**:

- FSM state transition tests (valid transitions, guard failures, edge cases)
- Tool dispatch tests (category routing, timeout, result buffering)
- Tier routing tests (UltraBERT output mapping, threshold boundary conditions)
- Output ordering tests (event sequence, queue depth enforcement)
- Delta aggregation tests (window timing, flush correctness, type validation)
- Integration tests (full turn lifecycle with mock adapters)
- Contract tests (port/adapter compliance verification)

**Reference**: SessionState specifies 455+ tests across 6 services.

---

## Status

| Epic | Title | Priority | Status |
|---|---|---|---|
| 1 | Hexagonal Architecture | CRITICAL | Complete |
| 2 | Invariants | CRITICAL | Complete |
| 3 | Performance Baselines | CRITICAL | Complete |
| 4 | Internal Services | CRITICAL | Complete |
| 5 | Session/Turn Lifecycle | HIGH | Complete |
| 6 | Concurrency Model | HIGH | Complete |
| 7 | Token Budget Management | HIGH | Complete |
| 8 | Error/Recovery Paths | MEDIUM | Complete |
| 9 | Milestone Tracking | MEDIUM | Not Started |
| 10 | Testing Strategy | LOW | Not Started |
