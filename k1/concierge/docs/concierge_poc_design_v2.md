# Bus-Driven Dual-LLM Conversational Architecture: Design Specification

**Status:** Design
**Date:** 2026-02-19
**K1 Architecture Ref:** `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd`
**Bus Ref:** `k1/bus/`

One document. No supersedes notices. No "see Section X for the real version." Each topic appears exactly once. Implementation detail follows design intent within the same section, not 15 sections later.

---

# 1. Introduction & Motivation

## The Single-LLM Problem

A single ReAct loop with one LLM juggling two incompatible responsibilities — being conversational (acknowledging, clarifying, presenting) and being productive (searching, executing, planning) — creates a class of bugs that no amount of patching can fix:

| Bug Class | Root Cause | Typical Patch | Why the Patch Fails |
|---|---|---|---|
| Anti-spin kills functional tools | Force-text-only guard blocks ALL tools when only cognitive tools fire | Tool-type exemption flags | Fragile; any new cognitive tool breaks it |
| Conversation amnesia | History reset per turn; prior context injected as flat system text | Seed messages from active history | Model treats injected history as instructions, not conversation |
| Duplicate execution of completed actions | Execution state lives inside the executor, invisible to the LLM | Inject execution results into context | One more section in an already overloaded system prompt |
| Tone vs. execution conflict | Same prompt must be warm/empathetic AND precise/tool-calling | Separate system prompt sections | Prompt pressure; model locks into one mode and drops the other |

Every fix adds complexity to a loop that was never designed for dual responsibility. The architecture must change.

## The Two-Phase Insight

The K1 cognitive architecture skeleton already encodes this separation:

- **Phase 1 (Pre-LLM):** Deterministic classification — intents, domains, safety, entities, affect. Writes directly to Session State.
- **Phase 2 (LLM with Tools):** Semantic understanding — scoreboard updates, belief corrections, clarification detection, narrative threading, affect refinement. The LLM decides which cognitive tools to call.

In MEDIUM and HIGH complexity tiers, the skeleton already defines two separate LLM invocations: a preliminary acknowledgment (conversational) and a final response (presenting execution results). It further separates the Orchestrator (deterministic actor, no LLM) from the Planner (LLM-powered, read-only discovery tools) from the conversational FSM (LLM with cognitive tools).

A single-loop architecture collapses all of this into one `while not complete` cycle. The fix is to un-collapse it: separate the conversational mind from the execution mind and let them communicate through structured events rather than shared prompt space.

---

# 2. Architecture Overview

## The Dual-Actor Model

Two LLM actors communicate through an event bus. Neither knows the other exists. Session State is their shared memory. Events are their only triggers.

This is not a pipeline — it is an actor model. Each actor has its own mailbox, its own subscription list, and its own ReAct loop. The bus enforces causal ordering so that events arrive in the right sequence without any actor needing to know the topology.

```
                        +------------------+
                        |   K1 Event Bus   |
                        | (LocalBus +      |
                        |  TimingChain)    |
                        +--+-----+-----+--+
                           |     |     |
              subscribe    |     |     |    subscribe
           +---------------+     |     +-----------------+
           |                     |                       |
           v                     v                       v
    +--------------+    +-----------------+    +-----------------+
    |  Front LLM   |    |  SESSION STATE  |    |   Back LLM      |
    |  (Voice)     |<-->|  Structured     |<-->|   (Worker)      |
    |              |    |  Shared Memory  |    |                 |
    |              |    |  Single Writer  |    |                 |
    +--------------+    +-----------------+    +-----------------+
           |                                          |
           | emits:                            emits: |
           |  response.*                              |
           |  orchestration.task.dispatch.*           |
           |                                   orchestration.task.complete.*
           |                                   tool.*
           |                                   session.artifact.*
           v                                          v
    +------------------------------------------------+
    |                   K1 Event Bus                  |
    +------------------------------------------------+
```

## Actor Registration

Actors register with the bus through a mailbox router. Each gets a priority-weighted fair-queuing mailbox that ensures urgent events (user input, acknowledgments) are processed before background events (affect updates, observability):

```python
from k1.bus import BusFactory, Envelope, Priority, MailboxConfig
from k1.bus.adapters import SessionBusAdapter

# Create bus with causal ordering enforcement
bus = BusFactory.create_local_ordered()
router = BusFactory.create_mailbox_router()
session_adapter = SessionBusAdapter(bus)

# Register actors -- neither knows the other exists
front_mailbox = router.register("front-llm", MailboxConfig(capacity=64, priority_wfq=True))
back_mailbox  = router.register("back-llm",  MailboxConfig(capacity=64, priority_wfq=True))
```

## The Two Actors

**Front LLM (The Voice):** The conversational actor. It talks to the user — acknowledges, clarifies, presents results, tracks emotional tone. It reads Session State for context and writes cognitive updates (beliefs, scoreboard, affect, narrative). It never executes functional capabilities. When the user wants something done, Front emits a structured task dispatch event and moves on to the next conversational beat. Its tools are purely cognitive and conversational.

**Back LLM (The Worker):** The execution actor. It receives task dispatch events, discovers and invokes capabilities through the Fabric registry, and returns structured results. It never talks to the user directly and never streams text to the output channel. It operates on structured JSON envelopes: task in, result out. Its tools are domain-agnostic — a single `invoke_capability()` call routes through the Fabric's capability registry regardless of whether the task involves scheduling, search, booking, content generation, or any other domain.

## Session State as Shared Memory

The actors do not pass messages to each other directly. Session State is the structured communication channel. Front writes cognitive context (beliefs, topics, affect). Back reads that context to understand task constraints. Back writes execution artifacts (results, bookings). Front reads those artifacts to present results conversationally.

This eliminates the prompt-pressure problem: neither actor's system prompt must contain the other actor's responsibilities. The Voice prompt is purely conversational. The Worker prompt is purely operational. Session State carries the context that bridges them.

---

# 3. Event Bus & Topic Taxonomy

## Three Messaging Primitives

The K1 bus layer provides three complementary messaging primitives through a single infrastructure:

| Primitive | Interface | Delivery | Pattern | Use Case |
| --- | --- | --- | --- | --- |
| **Event Bus** | `IBus` (pub/sub) | At-most-once, fan-out | Topic-based multicast with trie matching | Lifecycle events, state transitions, task coordination |
| **Delta Bus** | `IBus` (same interface) | At-most-once, fan-out | `k1.agent.{id}.delta.v1` topic convention | Per-agent state deltas, progress updates |
| **Mailbox Router** | `IMailboxRouter` (point-to-point) | At-least-once, unicast | Actor-addressed with WFQ priority scheduling | Direct actor-to-actor delivery with backpressure |

These are not three separate systems. Event Bus and Delta Bus share the same `IBus` implementation — deltas are just events on `k1.agent.*.delta.v1` topics. The Mailbox Router is a separate `IMailboxRouter` interface for point-to-point actor messaging with bounded queues and delivery acknowledgment.

The bus is **blind to payload content**. It reads only the `Envelope` header (topic, priority, parent_id, sequence) for routing and timing decisions. Payload is opaque bytes. Module adapters (`FabricBusAdapter`, `SessionBusAdapter`) handle serialization at the boundary.

## The Envelope

Every message on the bus is an `Envelope` — a frozen dataclass with 12 header fields and an opaque payload:

```python
@dataclass(frozen=True)
class Envelope:
    topic: str                    # Hierarchical topic (e.g. "k1.orchestration.task.dispatch.v1")
    priority: Priority            # WFQ scheduling: URGENT(4x) | REALTIME(3x) | INTERACTIVE(2x) | BACKGROUND(1x)
    envelope_id: int              # Global monotonic ID (stamped by bus on publish)
    sequence: int                 # Per-topic monotonic sequence (stamped by bus)
    cognitive_trace_id: str       # Cross-K0/K1 correlation key
    session_id: str               # Session scope
    request_id: str               # Request scope within session
    parent_id: int                # Causal parent envelope_id (0 = root, no parent)
    created_ns: int               # Monotonic clock timestamp (stamped by bus)
    payload: bytes                # Opaque — bus NEVER reads this
    ttl_ms: int = 0               # Envelope expiry (0 = no expiry)
    payload_format: PayloadFormat = PayloadFormat.OPAQUE  # Hint for adapters (OPAQUE | JSON | MSGPACK)
```

The bus stamps `envelope_id`, `sequence`, and `created_ns` at publish time. Publishers set `topic`, `priority`, `parent_id`, and `payload`. The `parent_id` field is the causal ordering mechanism — it replaces all heuristic anti-spin logic.

## Topic Taxonomy

All topics follow K1's hierarchical namespace convention. No new categories are invented — every topic maps to a prefix already defined in the K1 architecture. The merged topic table below is the single source of truth for all events in this system:

| Topic | DeliveryMode | Priority | Producer | Consumer | Prefix Rule Matched |
| --- | --- | --- | --- | --- | --- |
| `k1.session.user.input.v1` | STRICT | URGENT | Controller | Front | `k1.session` |
| `k1.response.ack.v1` | STRICT | URGENT | Front | Output Channel | `k1.response` |
| `k1.response.final.v1` | STRICT | URGENT | Front | Output Channel | `k1.response` |
| `k1.response.clarification.v1` | STRICT | URGENT | Front | Output Channel | `k1.response` |
| `k1.orchestration.task.dispatch.v1` | STRICT | INTERACTIVE | Front | Back | `k1.orchestration` |
| `k1.orchestration.task.complete.v1` | STRICT | INTERACTIVE | Back | Front | `k1.orchestration` |
| `k1.orchestration.task.failed.v1` | STRICT | INTERACTIVE | Back | Front | `k1.orchestration` |
| `k1.orchestration.task.cancel.v1` | STRICT | URGENT | Front | Back | `k1.orchestration` |
| `k1.orchestration.task.suspended.v1` | STRICT | INTERACTIVE | Back | Front | `k1.orchestration` |
| `k1.orchestration.task.resume.v1` | STRICT | INTERACTIVE | Front | Back | `k1.orchestration` |
| `k1.orchestration.findings.ready.v1` | STRICT | INTERACTIVE | Back | Front | `k1.orchestration` |
| `k1.orchestration.clarification.request.v1` | STRICT | INTERACTIVE | Back | Front | `k1.orchestration` |
| `k1.orchestration.clarification.response.v1` | STRICT | INTERACTIVE | Front | Back | `k1.orchestration` |
| `k1.tool.started.v1` | STRICT | INTERACTIVE | Back | Observability | `k1.capability` |
| `k1.tool.completed.v1` | STRICT | INTERACTIVE | Back | Observability | `k1.capability` |
| `k1.session.artifact.created.v1` | STRICT | INTERACTIVE | Back (via bus) | FSM -> Session State | `k1.session` |
| `k1.session.turn.started.v1` | STRICT | INTERACTIVE | FSM | Front, Observability | `k1.session` |
| `k1.session.turn.completed.v1` | STRICT | INTERACTIVE | FSM | Front, Observability | `k1.session` |
| `k1.session.state.updated.v1` | STRICT | BACKGROUND | FSM (DeltaAggregator) | Observability | `k1.session` |
| `k1.orchestration.task.accepted.v1` | STRICT | INTERACTIVE | Orchestrator | Front, Observability | `k1.orchestration` |
| `k1.orchestration.delta.v1` | STRICT | INTERACTIVE | Orchestrator / Back | FSM (progress tracking) | `k1.orchestration` |
| `k1.orchestration.dag.completed.v1` | STRICT | INTERACTIVE | Orchestrator | FSM -> DELIVERING | `k1.orchestration` |
| `k1.planner.plan.ready.v1` | STRICT | INTERACTIVE | Planner | Orchestrator | `k1.planner` |
| `k1.internal.weave.batch.v1` | STRICT | INTERACTIVE | WeaveBatcher (timer) | FSM -> Front | `k1.session` |
| `k1.hil.request.v1` | STRICT | INTERACTIVE | Back | Front | `k1.hil` |
| `k1.hil.response.v1` | STRICT | URGENT | Front | Back | `k1.hil` |
| `k1.affect.update.v1` | RELAXED | BACKGROUND | Front | Session State | `k1.affect` |
| `k1.proactive.fill.v1` | RELAXED | BACKGROUND | Experience Layer | Front | `k1.proactive` |

**Payload note:** Most events carry simple payloads (1-3 fields). `k1.orchestration.task.failed.v1` is the exception — it carries a 7-field diagnostic payload (`task_id`, `reason`, `error_code`, `tool_history`, `partial_results`, `retries_attempted`, `last_error_detail`). Full schema defined in Section 8.

## DeliveryMode vs. Priority: Orthogonal Concerns

These are independent dimensions. Confusing them is a design error.

| Dimension | Controls | Values | Set By |
| --- | --- | --- | --- |
| **DeliveryMode** | Causal ordering of envelopes | STRICT / RELAXED / BEST_EFFORT | `TimingConfig` prefix rules (architecture-level) |
| **Priority** | Mailbox scheduling weight | URGENT(4x) / REALTIME(3x) / INTERACTIVE(2x) / BACKGROUND(1x) | Envelope publisher (per-message) |

**DeliveryMode** determines how the TimingChain handles the envelope:

- **STRICT:** Buffer on sequence gap. Enforce causal parent ordering. Deliver only when parent has been delivered and sequence is contiguous.
- **RELAXED:** Deliver immediately. Log reordering events for monitoring. No buffering.
- **BEST_EFFORT:** Deliver immediately. Droppable under pressure. Bypasses the chain entirely.

**Priority** determines mailbox scheduling weight via Deficit Round-Robin WFQ. Higher weight = more bandwidth. Starvation is impossible — even BACKGROUND gets its turn.

A HITL approval response is STRICT (must arrive after the request) AND URGENT (must be processed first in the mailbox). An affect update is RELAXED (can arrive out of order) AND BACKGROUND (processed when idle). These dimensions never interfere with each other.

## TimingChain: Prefix Rules and Configuration

The `TimingConfig` resolves each topic to a `DeliveryMode` using longest-prefix matching against a sparse rule set. The default rules from `k1/bus/timing/defaults.py` cover every topic this system emits or consumes. No custom configuration is required:

```python
DEFAULT_RULES: dict[str, DeliveryMode] = {
    # STRICT: correctness-critical ordering
    "k1.capability":      DeliveryMode.STRICT,
    "k1.orchestration":   DeliveryMode.STRICT,
    "k1.planner":         DeliveryMode.STRICT,
    "k1.hil":             DeliveryMode.STRICT,
    "k1.response":        DeliveryMode.STRICT,
    "k1.session":         DeliveryMode.STRICT,
    "k1.agent":           DeliveryMode.STRICT,
    # RELAXED: order-preferred, not critical
    "k1.affect":          DeliveryMode.RELAXED,
    "k1.constraint":      DeliveryMode.RELAXED,
    "k1.proactive":       DeliveryMode.RELAXED,
    "k1.workflow":        DeliveryMode.RELAXED,
    # BEST_EFFORT: fire-and-forget
    "k1.k0.sse":          DeliveryMode.BEST_EFFORT,
    "k1.fabric.learning": DeliveryMode.BEST_EFFORT,
}
DEFAULT_MODE = DeliveryMode.RELAXED  # Unmatched topics fall here
```

Resolution algorithm: walk the topic string from full match down to first segment, checking each prefix against the rules dict. O(k) where k = number of segments (typically 3-7). The rule set is sparse (~15 entries), so dict lookup beats trie overhead.

Initialization is one call:

```python
from k1.bus.timing.defaults import default_timing_config
from k1.bus.timing.timing_chain import TimingChain

config = default_timing_config()
timing_chain = TimingChain(
    config=config,
    gap_timeout_ms=5000,    # Max wait for parent before force-deliver (safety net)
    sweep_interval_ms=1000, # How often to check for timed-out gaps
    max_buffer_size=1000,   # Max buffered envelopes before backpressure
)
```

The TimingChain sits between `LocalBus` envelope stamping and handler dispatch:

```
+-----------+     +----------------+     +------------+
| LocalBus  | --> | TimingChain    | --> | Handlers   |
| (stamped) |     | .process(env)  |     | (ordered)  |
+-----------+     +----------------+     +------------+
                   | TimingConfig   |
                   | CausalTracker  |
                   | GapBuffer      |
                   +----------------+
```

## Causal Ordering via parent_id

The `Envelope.parent_id` field creates a causal chain that the TimingChain enforces structurally. A child envelope with `parent_id=X` is buffered until envelope X has been delivered. This cascades: delivering a child may release grandchildren waiting on that child's ID.

The core conversational flow forms this causal chain:

```
Envelope #1: k1.session.user.input.v1                   parent_id=0 (root)
  +-- Envelope #2: k1.response.ack.v1                   parent_id=1
  +-- Envelope #3: k1.orchestration.task.dispatch.v1     parent_id=1
        +-- Envelope #4: k1.tool.started.v1              parent_id=3
        +-- Envelope #5: k1.tool.completed.v1            parent_id=4
        +-- Envelope #6: k1.orchestration.task.complete.v1   parent_id=3
              +-- Envelope #7: k1.response.final.v1      parent_id=6
```

TimingChain guarantees:

- **#3** (task dispatch) delivered only after **#1** (user input) is delivered
- **#6** (task complete) delivered only after **#3** (task dispatch) is delivered
- **#7** (presentation) delivered only after **#6** (task complete) is delivered
- **#2** (ack) can be delivered in parallel with **#3** — both have parent_id=1, no ordering constraint between siblings

## What Disappears

Anti-spin, `_force_text_only`, `_cognitive_only`, `_ack_next_tool` — all the heuristic ordering hacks from the single-loop architecture — disappear entirely. Causal ordering is structural, encoded in the `parent_id` field and enforced by the TimingChain. No runtime guards, no exemption flags, no fragile tool-type checks. If an envelope should come after another, set its `parent_id`. The bus handles the rest.

---

# 4. FSM: Event Router & State Machine

## Role of the FSM

The FSM is not a loop driver. It is an **event router**. In the single-loop architecture, the FSM drove iteration: `LISTENING -> ACKING -> DISPATCHING -> (tool iterations) -> DELIVERING -> LISTENING`. In the dual-actor model, the FSM receives bus events, determines the system's cognitive state, routes events to the correct handler, manages concurrency between Front and Back, and controls history writes.

The FSM is the only component with a complete view of the system's lifecycle. Front and Back are each blind to the full picture — they see only the events they subscribe to. The FSM sees all events, manages state transitions, and enforces invariants that no individual actor can enforce alone.

## FSM States: The Definitive Table

Twelve states. Each state has an entry event (what triggers it), an exit event (what ends it), the actor that runs during that state, and a `PromptMode` that determines prompt assembly for Front LLM invocations. One table, one truth.

| FSM State | Entry Trigger | Exit Trigger | Active Actor | PromptMode | Description |
| --- | --- | --- | --- | --- | --- |
| LISTENING | `k1.response.final.v1` delivered OR session start | `k1.session.user.input.v1` received | None (idle) | -- | System is idle, waiting for user input. No LLM running. |
| ACKING | `k1.session.user.input.v1` received | Phase 1 classification complete | Phase 1 (deterministic) | -- | Pre-LLM classification: intents, domains, safety band, entities, affect. Writes directly to Session State `control` and `affective_now`. No LLM involved. |
| DISPATCHING | ACKING complete | `k1.orchestration.task.dispatch.v1` emitted OR text-only response emitted | Front LLM | STANDARD | Front runs cognitive tools (scoreboard, beliefs, clarifications, narrative, affect) and optionally dispatches a task. If no task is needed (pure conversational turn), Front emits `k1.response.final.v1` and FSM returns to LISTENING. |
| COMPANIONING | `k1.response.ack.v1` emitted + task dispatched | `k1.orchestration.task.complete.v1` OR `task.failed.v1` OR `task.suspended.v1` received | Front LLM (idle, interruptible) | -- | Front has acknowledged the user and dispatched work. The user-facing channel is responsive. Front can accept new `user.input` events during this state (interrupt handling). Back is working concurrently. |
| PROGRESSING | `k1.tool.started.v1` received | `k1.tool.completed.v1` received | Back LLM | -- | Back is executing a tool. This state is primarily observability — tracking which tool is running, for how long, and for latency metrics. Multiple PROGRESSING cycles may occur within one task. |
| DELIVERING | `k1.orchestration.task.complete.v1` received | `k1.response.final.v1` emitted | Front LLM | PRESENT | Task results are ready. Front is invoked to present results conversationally. Front reads `task_artifacts` and `task_state` to understand what was done, then generates a natural-language presentation. |
| CLARIFYING_USER | Front detects ambiguity (uncertainty >= threshold, blocking gaps in `clarifications`) | `k1.session.user.input.v1` with answer | Front LLM | CLARIFY_ASK (asking) / CLARIFY_RESOLVE (user answered) | Front detected semantic gaps that block task dispatch. It asks the user for clarification. On re-entry with the user's answer, mode switches to CLARIFY_RESOLVE. |
| CLARIFYING_WORKER | `k1.orchestration.task.suspended.v1` received | `k1.orchestration.task.resume.v1` emitted | Front LLM | HITL_RELAY (presenting question) / HITL_RESOLVE (user answered) | Back suspended execution because it needs human input (approval, selection, or clarification). Front translates the structured HITL request into natural conversation. On user response, Front emits `task.resume` with the answer. |
| CANCELLING | `k1.orchestration.task.cancel.v1` emitted by Front | `k1.orchestration.task.failed.v1` received with `reason=cancelled` | Controller (waiting) | CANCEL | User requested cancellation. Front has emitted the cancel event. FSM waits for Back to acknowledge cancellation via `task.failed` with cancelled reason. On receipt, FSM transitions to DELIVERING so Front can confirm cancellation to the user. |
| INTERRUPT_HANDLING | New `k1.session.user.input.v1` received during COMPANIONING or PROGRESSING | Route to ACKING (new turn) | Front LLM | INTERRUPT | User sent new input while a task is in progress. The FSM must decide: is this a follow-up to the in-flight task (add constraints), a topic change (respond conversationally while task continues), or a cancellation? Full cognitive processing applies — same tool set as STANDARD. |
| PROACTIVE_WAKE | `k1.orchestration.task.complete.v1` received while in LISTENING (no active conversation) | Route to DELIVERING | Controller | -- | A task completed asynchronously while the user was idle. The FSM wakes the system and routes to DELIVERING so Front can present the result proactively. |
| WEAVING | `pending_results` queue non-empty after Front finishes a response | `k1.response.final.v1` with woven content emitted | Front LLM | WEAVE | Async task results arrived while Front was handling a different topic. After Front finishes its current response, the FSM checks `pending_results`. If non-empty, it re-invokes Front in WEAVE mode to merge the async results into the conversation naturally. |

## PromptMode: FSM-Driven Prompt Assembly

Each FSM state maps to a `PromptMode` that determines exactly which tools, Session State sections, prompt sections, in-context examples, and iteration limits are injected into the Front LLM's context. The FSM already knows the cognitive mode — it tells the prompt builder rather than leaving the LLM to infer it from a wall of instructions.

Ten prompt modes:

| PromptMode | Triggering FSM State(s) | Tools Available | Max Iterations | Est. Prompt Tokens | Purpose |
| --- | --- | --- | --- | --- | --- |
| STANDARD | DISPATCHING | 10 (all Front tools) | 6 | ~2100 | Full cognitive processing: scoreboard, beliefs, clarifications, narrative, affect, recall, dispatch |
| CLARIFY_ASK | CLARIFYING_USER (asking) | 3 (acknowledge, update_clarifications, recall_memory) | 3 | ~1100 | Front detected ambiguity. Ask one focused question. Do not guess missing info. |
| CLARIFY_RESOLVE | CLARIFYING_USER (answer received) | 7 (ack, beliefs, scoreboard, clarifications, promote_belief, recall, dispatch) | 5 | ~1500 | User answered clarification. Resolve gaps, update beliefs, dispatch if ready. |
| HITL_RELAY | CLARIFYING_WORKER (presenting) | 0 (text-only) | 1 | ~800 | Back suspended. Translate structured HITL request to natural conversation. No tools — pure text response. |
| HITL_RESOLVE | CLARIFYING_WORKER (answer received) | 2 (acknowledge, update_beliefs) | 3 | ~1000 | User answered HITL question. Acknowledge, update beliefs, emit resume. |
| PRESENT | DELIVERING | 2 (update_beliefs, update_narrative) | 3 | ~900 | Present task results conversationally. Update beliefs with confirmed facts. Close/switch narrative thread. |
| WEAVE | WEAVING | 2 (update_beliefs, update_narrative) | 3 | ~1000 | Merge async results into ongoing conversation. Respond to current topic first, then bridge to the result. |
| CANCEL | CANCELLING | 3 (acknowledge, update_beliefs, update_narrative) | 3 | ~900 | Confirm cancellation. Close the narrative thread. Do not re-dispatch. |
| INTERRUPT | INTERRUPT_HANDLING | 10 (all Front tools) | 6 | ~2100 | Full cognitive processing — user may be changing direction entirely. Same as STANDARD. |
| ERROR | DELIVERING (after task.failed) | 1 (update_narrative) | 2 | ~800 | Explain failure gracefully. No error codes, no jargon. Close narrative thread. Suggest alternatives. |

### Mode Resolution Logic

The `determine_mode()` function maps FSM state + incoming event + Session State signals to a single PromptMode. Priority order (first match wins):

1. **Explicit FSM state mappings:** CANCELLING -> CANCEL, INTERRUPT_HANDLING -> INTERRUPT.
2. **FSM state + event topic combinations:** CLARIFYING_USER + `user.input` -> CLARIFY_RESOLVE; CLARIFYING_USER + anything else -> CLARIFY_ASK; CLARIFYING_WORKER + `user.input` -> HITL_RESOLVE; CLARIFYING_WORKER + anything else -> HITL_RELAY.
3. **Event-topic-driven mappings:** `task.complete` -> PRESENT; `task.failed` -> ERROR; `weave.batch` -> WEAVE; `task.suspended` -> HITL_RELAY.
4. **Session State signal fallbacks:** `user.input` + suspended tasks exist -> HITL_RESOLVE; `user.input` + blocking gaps > 0 -> CLARIFY_RESOLVE.
5. **Default:** STANDARD.

No ambiguity. Every combination of FSM state, event topic, and Session State resolves to exactly one mode.

## State Diagram

The FSM drives two concurrent tracks with interrupt, cancel, suspend, and weave support:

```text
                            LISTENING
                               |
                           user.input
                               |
                            ACKING (Phase 1: deterministic classification)
                               |
                          DISPATCHING (Front LLM: cognitive tools + dispatch_task)
                            /     \
                      ack emitted   task.dispatch emitted
                           |                       |
                     COMPANIONING            PROGRESSING (Back LLM: functional tools)
                           |                    /     \
                      user.input          task.complete  task.suspended
                           |                 |               |
                    INTERRUPT_HANDLING        |         CLARIFYING_WORKER
                      /       \              |          (Front presents HITL question)
                 just chat  cancel           |               |
                     |         |             |          user answers
                 respond   CANCELLING        |               |
                     |      (emit cancel)    |          Front emits task.resume
                     |         |             |               |
                     |    task.failed        |          Back resumes
                     |    (cancelled)        |               |
                     +----+----+             +-------+-------+
                          |                          |
                          +---------> DELIVERING <---+
                                    (Front LLM: present results)
                                           |
                                    response.final emitted
                                           |
                                 pending_results empty?
                                    /            \
                                  yes             no
                                   |               |
                              LISTENING         WEAVING
                                            (drain queue,
                                             re-invoke Front)
                                                  |
                                            response.final
                                                  |
                                             LISTENING
```

### Key Differences from a Single-Loop FSM

| Single-Loop FSM | Dual-Actor FSM |
| --- | --- |
| Drives one sequential loop: LISTENING -> ACKING -> DISPATCHING -> tool iterations -> DELIVERING -> LISTENING | Routes events across two concurrent actors. Front and Back run independently. |
| Cannot accept new user input while processing a task | COMPANIONING state allows new `user.input` (interrupt). Front handles it while Back continues working. |
| No cancellation path | CANCELLING state: Front emits `task.cancel`, waits for Back's `task.failed(cancelled)`. |
| No suspension/HITL path | CLARIFYING_WORKER state: Back suspends, Front relays HITL question to user, resumes on answer. |
| No async result handling | WEAVING state: drains `pending_results` queue after Front finishes its current response. |
| Loop iteration count drives tool execution | Event delivery drives transitions. No iteration counter. Tool iterations happen inside each actor's ReAct loop, invisible to the FSM. |

## FrontLock: Concurrency Control

The Front LLM is a single actor. It cannot process two events simultaneously. When multiple events target Front at the same time (user input arrives while a task completes), the FSM must serialize access.

### The Lock

The FrontLock is a concurrency gate with a bounded priority queue:

| Field | Type | Purpose |
| --- | --- | --- |
| `busy` | `bool` | `True` while Front LLM is generating. Set on entry, cleared on response completion. |
| `event_queue` | `deque[Envelope]` | Queued events waiting for Front to become available. Drained in priority order after each response. |
| `max_queue_depth` | `int` (default: 8) | Backpressure limit. If exceeded, the lowest-priority event is rejected and logged. |

### Dispatch Rules

1. Event targets Front (any of: `user.input`, `task.complete`, `task.failed`, `task.suspended`, `findings.ready`, `weave.batch`).
2. FSM checks `FrontLock.busy`.
3. If `busy=False`: Set `busy=True`, deliver event to Front handler, wait for response, set `busy=False`, drain queue.
4. If `busy=True`: Append event to `event_queue`.
5. After Front finishes any response: FSM drains `event_queue` in priority order (URGENT first, then INTERACTIVE, then BACKGROUND).
6. If `event_queue` exceeds `max_queue_depth`: Reject lowest-priority event, log warning, emit observability metric.

### Queue Priority

| Priority | Event Type | Rationale |
| --- | --- | --- |
| 1 (highest) | `user.input` | User is always first. Never make the user wait for a system-internal event. |
| 2 | `task.suspended` | Worker is blocked, needs human answer to continue. Delay costs latency. |
| 3 | `task.complete` | Result ready, but user is not actively waiting right now. |
| 4 | `task.failed` | Error, but user may not even know about the task yet. |
| 5 (lowest) | `findings.ready` | Partial results, informational only. Can be dropped under pressure. |

### Why This Matters

Without the lock, race conditions corrupt the conversation. Two parallel Front LLM calls would read the same Session State, both generate responses, and one would overwrite the other. With the lock, events serialize: the user's message is handled first (URGENT), then the task completion is handled in a subsequent Front invocation. Two sequential, coherent messages instead of one garbled race.

## History Management Under Concurrency

### Turn Definition

In a single-loop system, a "turn" is simple: user speaks, AI responds, turn increments. In the dual-actor model with concurrent conversation, multiple user turns can overlap with Back LLM work. The definition changes:

A **turn** is one complete cycle from `k1.session.user.input.v1` to the Front LLM's response to that specific input. Turn numbers are monotonically increasing and assigned by the FSM at `user.input` receipt. Multiple turns can be active simultaneously (user sends a new message while a previous task is still running).

### History Write Protocol

The FSM is the sole writer to `history_active`. No other component writes history entries. Every entry carries its turn number for timeline reconstruction:

| Event | History Entry Schema | Written By |
| --- | --- | --- |
| `k1.session.user.input.v1` received | `{role: "user", text: <input>, turn: N}` | FSM (immediately on receipt) |
| `k1.response.ack.v1` emitted | `{role: "assistant", type: "ack", text: <ack>, turn: N}` | FSM |
| `k1.response.final.v1` emitted | `{role: "assistant", type: "final", text: <response>, turn: N}` | FSM |
| `k1.response.clarification.v1` emitted | `{role: "assistant", type: "clarification", text: <question>, turn: N}` | FSM |
| Weave response emitted | `{role: "assistant", type: "weave", text: <woven>, turn: N, async_task: <task_id>}` | FSM |

### History Window

The Front LLM receives the last N entries from `history_active` (configurable per PromptMode, default 20 for STANDARD). This is NOT the full session history — it is a sliding window. For deep context beyond the window, the Front LLM reads `narrative_active`, which contains the LLM-summarized thread state maintained by the `update_narrative` cognitive tool.

The `type` field in each history entry lets the Front LLM distinguish between acks (short acknowledgments), finals (full responses), clarifications (questions to the user), and weaves (async result presentations). This prevents the LLM from confusing an acknowledgment with a full response when reading its own history.

### History Window Sizes per PromptMode

Not every mode needs the full 20-entry window. Modes that need deep conversational context (STANDARD, INTERRUPT) get 20 entries. Modes that handle a single focused interaction (HITL_RELAY, ERROR) get 5 or fewer. This reduces token waste without losing necessary context:

| PromptMode | History Window | Rationale |
| --- | --- | --- |
| STANDARD | 20 entries | Full conversational context for cognitive processing |
| INTERRUPT | 20 entries | Same as STANDARD — user may reference anything |
| CLARIFY_RESOLVE | 15 entries | Need context of what was asked and what gaps existed |
| CLARIFY_ASK | 10 entries | Moderate context to understand what's ambiguous |
| PRESENT | 10 entries | Enough to reference what user asked for |
| WEAVE | 10 entries | Current topic + enough context to bridge |
| HITL_RESOLVE | 5 entries | Just the HITL question and user's answer |
| CANCEL | 5 entries | Just the task context being cancelled |
| ERROR | 5 entries | Just enough to frame the failure |
| HITL_RELAY | 0 entries | No user input triggered this. Back's structured HITL request is the only context. |

## FSMTurnState: Ephemeral Controller State

The FSM tracks per-session ephemeral state that is NOT in Session State and NOT visible to the LLM. This state is structurally managed — the FSM reads and writes it between ReAct iterations and event deliveries:

```python
@dataclass
class FSMTurnState:
    """FSM-managed state for the current session. Not visible to LLM."""

    pending_results: deque[dict] = field(default_factory=deque)
    # task.complete payloads queued for Weave presentation.
    # Drained by FSM after Front completes its ReAct loop.

    cancelled_tasks: set[str] = field(default_factory=set)
    # For dedup: if task.complete arrives after cancel was emitted.

    cancellation_requested: bool = False
    # Set by FSM when task.cancel event received.
    # Checked by react_loop between iterations via cancellation_check callback.
```

The LLM does not need to track these — the FSM handles them structurally:

| Field | FSM Behavior | Replaces |
| --- | --- | --- |
| `pending_results` | FSM queues `task.complete` payloads. After Front finishes its current ReAct loop, FSM checks this queue. If non-empty, transitions to WEAVING and re-invokes Front with WEAVE mode. | Old `FrontScratchpad` result tracking |
| `cancelled_tasks` | FSM deduplicates cancel vs. complete events. If `task.complete` arrives for a task in `cancelled_tasks`, FSM presents a "completed despite cancellation" message instead of a standard result. | Old `cancellation_token` |
| `cancellation_requested` | FSM sets this flag on `task.cancel` receipt. The `react_loop()` checks it between iterations via the `cancellation_check` callback (see Section 7). Back's handler wires: `cancellation_check=lambda: fsm_state.cancellation_requested`. | Old explicit cancel token threading |

**Lifecycle:** `FSMTurnState` is created at session start and lives for the session duration. `pending_results` is drained after each WEAVE cycle. `cancelled_tasks` entries are cleared after Front presents the cancellation confirmation. `cancellation_requested` is reset after the cancellation flow completes.

---

# 5. Session State Schema & Management

Session State is the structured communication channel between actors. It is not a context dump injected into a system prompt — it is a typed, budgeted, access-controlled shared memory with strict write ownership, sectional isolation, and deterministic pruning. Every cognitive fact, every affective signal, every task lifecycle state, every conversation history entry lives in one of its sections. This section is the single authoritative reference for all Session State read/write rules, schemas, lifecycle, and coherence guarantees.

## The Single Writer Invariant

Two actors reading and influencing the same state. Without guardrails, concurrent writes corrupt it:

```text
T=0ms:  Front reads beliefs_active: {preference: "boutique"}
T=1ms:  Back reads beliefs_active: {preference: "boutique"}
T=5ms:  Front writes beliefs_active: {preference: "boutique", dates: "June 15-17"}
T=6ms:  Back writes beliefs_active: {preference: "boutique", confirmed: true}  <- LOST Front's dates
```

Three rules prevent this (ADR-0017g):

1. **Sectional isolation:** Front and Back write to DIFFERENT sections. No section has two concurrent LLM writers.
2. **Back never writes SS directly.** Back emits structured deltas to the bus. The FSM (Controller) aggregates and writes them. The FSM is the single writer for all Back-originated state.
3. **Reads are lock-free snapshots.** Both actors read SS freely. Reads return a point-in-time snapshot (<1ms). If Back reads `beliefs_active` while Front is updating it, Back gets the pre-update version. This is fine — eventual consistency for reads, strict consistency for writes.

## Authoritative Read/Write Matrix

### Writers

| Section | Writer 1 | Writer 2 | Writer 3 | Mechanism | Concurrency Safety |
| --- | --- | --- | --- | --- | --- |
| `beliefs_active` | Front LLM | -- | -- | `update_beliefs()` cognitive tool via MutationGuard | Single writer. Safe. |
| `scoreboard` | Phase 1 (deterministic) | Front LLM | -- | Phase 1: direct write at turn start. Front: `update_scoreboard()` tool after Phase 1. | Sequential within turn (Phase 1 finishes before LLM starts). TurnLock prevents overlap. |
| `affective_now` | Phase 1 (deterministic) | Front LLM | ExperienceLayer (EmotionalProcessor) | Phase 1: initial classification. Front: `refine_affect()` override. EP: trajectory computation every 25th turn. | Sequential: Phase 1 then Front (same turn). EP fires at turn_end AFTER Front completes. EP skip rule: if Front's `refine_affect()` ran this turn with confidence > 0.8, EP skips `affective_now` write. |
| `clarifications` | Front LLM | -- | -- | `update_clarifications()` tool | Single writer. Safe. |
| `narrative_active` | Front LLM | -- | -- | `update_narrative()` tool | Single writer. Safe. |
| `control` | FSM | Phase 1 | -- | FSM: state transitions, turn lock, flow phase. Phase 1: intent classification, domain context, safety band. | Non-overlapping sub-fields. Phase 1 writes `intent`, `domain`, `safety`. FSM writes `flow_state`, `turn_lock`. |
| `history_active` | FSM | -- | -- | Append at turn boundary events | Single writer. Append-only. Safe. |
| `meta` | FSM | -- | -- | Update at turn end | Single writer. Safe. |
| `persona` | Session Init | -- | -- | Loaded from user profile. Read-only after init. | Immutable after init. Safe. |
| `task_state` | FSM | -- | -- | DeltaAggregator (500ms window) from Back's bus events | Single writer (FSM). Back emits deltas but never writes directly. |
| `task_artifacts` | FSM | -- | -- | DeltaAggregator from `k1.session.artifact.created.v1` | Single writer (FSM). |

### Readers

| Section | Front LLM | Back LLM | FSM | Phase 1 | ExperienceLayer | Why Each Reader Needs It |
| --- | --- | --- | --- | --- | --- | --- |
| `beliefs_active` | Y | Y | -- | -- | -- | Front: user facts for cognitive processing. Back: task parameters, constraints. |
| `scoreboard` | Y | Y | Y | -- | -- | Front: current topic, QUD. Back: referent resolution ("it" = what?). FSM: tier routing. |
| `affective_now` | Y | -- | -- | -- | Y | Front: tone matching. EP: trajectory input for next computation. |
| `clarifications` | Y | -- | Y | -- | -- | Front: what's unclear. FSM: uncertainty threshold for CLARIFYING_USER transition. |
| `narrative_active` | Y | -- | -- | -- | Y (NarrativeWeaver) | Front: which thread is active. NW: weave context across threads. |
| `control` | Y | Y | Y | -- | -- | Front: FSM state, safety band. Back: safety band check before side-effects. FSM: flow management. |
| `history_active` | Y | Y (limited) | Y | -- | -- | Front: conversational continuity (last 20 entries). Back: last 5 entries for task context. FSM: turn tracking. |
| `meta` | -- | -- | Y | -- | -- | FSM: turn count, latency tracking. |
| `persona` | Y | Y | -- | -- | Y (AffectiveMirror) | Front: tone, personality. Back: user preferences for capability params. AM: mirroring style. |
| `task_state` | Y | Y | Y | -- | Y (ProactiveAgent) | Front: cancel/resume/HITL. Back: dependency resolution. FSM: lifecycle. PA: wait duration. |
| `task_artifacts` | Y | Y | Y | -- | -- | Front: what's done. Back: avoid re-doing. FSM: pruning. |

### Phase 1 Write Specification

Phase 1 runs deterministically (~22ms) BEFORE any LLM call. It writes to three sections:

- **`scoreboard`:** Initial intents, entities, salience scores. Front LLM may refine via `update_scoreboard()`.
- **`affective_now`:** Emotion classification from raw input text. Front LLM may override via `refine_affect()`.
- **`control`:** Intent classification, domain context, safety band assessment.

Phase 1 and Front LLM write to the same sections but at different times within a single turn — Phase 1 first, Front second. This is safe because turns are serialized by TurnLock.

### Affective Ownership Chain (Priority Order)

1. Phase 1 writes initial emotion classification from raw input.
2. ExperienceLayer EmotionalProcessor (every 25th turn) overwrites with computed trajectory using conversation history.
3. Front LLM `refine_affect()` can override at any time based on conversational signals the model detects.

Later writes take priority. Within a single turn: Phase 1 then Front LLM. Across turns: EmotionalProcessor trajectory provides trend context that Phase 1 and Front can refine.

**EP skip rule:** If Front's `refine_affect()` was called this turn with confidence > 0.8, EmotionalProcessor skips `affective_now` write to avoid overwriting a high-confidence Front correction.

## HOT Tier Budget

The production spec defines 8 HOT sections (48KB). This architecture adds 2 more for task lifecycle:

| Section | Budget | Growth Pattern | Pruning Strategy |
| --- | --- | --- | --- |
| `control` | 8KB | Stable (FSM state, rewritten) | None needed |
| `beliefs_active` | 8KB | Grows with conversation | Evict low-confidence beliefs to WARM after 20 turns |
| `scoreboard` | 6KB | Stable (rewritten per turn) | None needed (overwritten, not appended) |
| `history_active` | 8KB | Grows linearly | Sliding window: keep last 20 entries, evict older to WARM |
| `clarifications` | 4KB | Spiky (grows during ambiguity) | Clear resolved clarifications after 5 turns |
| `affective_now` | 4KB | Stable (rewritten per turn) | None needed |
| `narrative_active` | 4KB | Grows slowly | Summarize after 50 turns, reset |
| `meta` | 2KB | Stable | None needed |
| `task_state` | 4KB | Grows with active tasks | Clear completed/failed tasks after Front presents results |
| `task_artifacts` | 4KB | Grows with durable outputs | Evict presented artifacts to WARM after 10 turns |

**Total HOT: 52KB** (48KB base + 4KB task sections). Within acceptable range — MutationGuard enforces per-section limits.

### Why Task Results are NOT in Session State

Task results (search results, query responses, tool outputs) are the biggest growth risk. A single search returns multiple results with descriptions and metadata. Persisting these in HOT SS would blow the budget in 2-3 searches.

Task results are ephemeral. They live in:

1. The `task.complete` event payload (bus message).
2. Front's `FSMTurnState.pending_results` (ephemeral, cleared after presentation — see Section 4, FSMTurnState).
3. `history_active` as summarized text in the response (not raw data).

If the user references old results, Front uses `recall_memory()` to query long-term memory or `summarize_context()` to compress recent history. The raw results are never stored in HOT SS.

## WARM Tier (48KB)

WARM holds evicted HOT data for the session duration:

| Section | Content | Source |
| --- | --- | --- |
| `beliefs_warm` | Low-confidence beliefs evicted from `beliefs_active` | Auto-evict after 20 turns without reinforcement |
| `history_warm` | History entries older than the 20-entry sliding window | Sliding window overflow |
| `artifacts_warm` | Presented task artifacts older than 10 turns | Lifecycle eviction |
| `narrative_warm` | Summarized narrative from earlier in the session | Summarize-and-reset at 50 turns |

Front can pull data back from WARM to HOT via `promote_belief()` (for beliefs) or by re-reading WARM sections when the user references old context.

## Pruning Lifecycle

```text
Turn N:    Back completes task -> results in task.complete event payload
Turn N:    Front presents results -> text written to history_active
Turn N:    FSM writes artifact (if durable) to task_artifacts
Turn N+1:  task_state entry marked "presented"
Turn N+10: task_artifacts entry evicted to WARM (artifacts_warm)
Turn N+20: If in WARM and not referenced, evict to LOCAL COLD
```

MutationGuard enforces section budgets on every write. If a section exceeds its budget:

1. MutationGuard rejects the write.
2. FSM triggers pruning: evict oldest/lowest-priority entries to WARM.
3. Retry the write.
4. If WARM is also full, evict to LOCAL COLD (disk-backed, out of prompt).

## DeltaAggregator Write Pipeline

Back LLM never writes SS. It emits structured deltas to the bus. The FSM aggregates them:

```text
Back emits: k1.session.artifact.created.v1 {type: "confirmation", data: {...}}
  |
  v
DeltaAggregator (500ms window)
  - Collects all deltas within window
  - Deduplicates by section + key
  - Orders by causal chain (parent_id)
  |
  v
FSM.apply_deltas()
  - MutationGuard.preflight() for each write (size check, schema validation)
  - Write to task_state / task_artifacts
  - Emit k1.session.state.updated.v1 (observability)
```

The 500ms window batches rapid-fire deltas (multiple tool completions within a single Back ReAct loop) into a single atomic write. This reduces write contention and ensures Front reads a consistent snapshot rather than a partially-applied delta set.

## Cross-Actor Read Consistency

| Scenario | Behavior | Risk |
| --- | --- | --- |
| Front reads `task_artifacts` while FSM writes it | Front gets pre-write snapshot | None (Front reads updated version on next invocation) |
| Back reads `beliefs_active` while Front writes it | Back gets pre-write snapshot | Minimal (Back's current task has params from dispatch snapshot) |
| Both read `history_active` simultaneously | Both get same snapshot | None (history is append-only, written by FSM at turn boundaries) |
| Front reads `task_state` to check progress | Gets latest committed state | None (reads <1ms, writes batched every 500ms) |

### What Could Still Go Wrong (and Mitigations)

| Risk | Scenario | Mitigation |
| --- | --- | --- |
| Stale read | Back reads beliefs that Front just updated | Back's dispatch payload carries a context snapshot at dispatch time. Back uses snapshot, not live SS, for critical params. |
| Delta loss | DeltaAggregator crashes mid-write | Deltas are journaled to outbox before aggregation. FSM replays on recovery. |
| Section overflow | `task_artifacts` exceeds budget | MutationGuard rejects write. FSM evicts oldest artifacts to WARM. |

## Schema Extensions (Current vs Required)

The existing K1 SessionState implementation has 8 HOT sections and 4 WARM sections. This architecture requires extensions:

| Change | Current State | Requirement | Implementation |
| --- | --- | --- | --- |
| `task_state` section | Does not exist | New HOT section, 4KB budget | Implement `ISection` protocol |
| `task_artifacts` section | Does not exist | New HOT section, 4KB budget | Implement `ISection` protocol |
| HOT tier budget | 48KB (8 sections) | 52KB (10 sections) | Update `HOT_BUDGET_BYTES` from 49152 to 53248 |
| `history_active` Turn schema | `Turn(turn_id, turn_number, user_message, assistant_response, ...)` | Extended with `entry_type` field (see Typed History Entries below) | Extend `Turn` dataclass or add `TypedHistoryEntry` wrapper |
| `history_active` window | 25 (current code) | 20 for Front, 5 for Back | No schema change — read APIs already support slicing |
| `control` FSM fields | Has FlowState, TurnLock, IntentClassification, DomainContext, SafetyContext, AgentLeases | Needs: `active_task_ids`, `fsm_state` (Concierge FSM state enum), `complexity_tier` | Extend `ControlSection` or use `FlowState.pending_agents` for task tracking |
| WARM `artifacts_warm` | Does not exist | New WARM section for evicted task artifacts | Implement `ISection` protocol |
| MutationGuard budgets | 8 section budget checks | 10 section budget checks | Update `SECTION_BUDGETS` dict |

### TaskStateEntry Schema

Each active task tracked in `task_state`:

| Field | Type | Purpose |
| --- | --- | --- |
| `task_id` | `str` | Unique task identifier |
| `action` | `str` | What the task does (generalized action description) |
| `status` | `enum` | DISPATCHED, IN_PROGRESS, SUSPENDED, COMPLETED, FAILED, CANCELLED |
| `dispatched_at_ms` | `int` | When the task was dispatched |
| `completed_at_ms` | `int or None` | When the task finished (any terminal status) |
| `depends_on` | `str or None` | Task ID this task depends on (chained tasks) |
| `progress_pct` | `int` | 0-100 progress estimate from Back's tool completions |
| `pending_hil` | `dict or None` | Serialized HILRequest when status=SUSPENDED. Contains: hil_type, question, options, side_effects, safety_band, timeout_ms. Survives process restarts — FSM reads this to re-present HITL if Front reconnects. |
| `hil_suspensions_count` | `int` | How many times this task has suspended for HITL (tracked against max_rounds) |

## Typed History Entries

The existing `Turn` dataclass stores `(user_message, assistant_response)` pairs. The dual-actor model produces multiple response types per turn — acks, finals, weaves, clarifications, HITL exchanges. A flat `entry_type` discriminator replaces the paired model:

| Field | Type | Purpose |
| --- | --- | --- |
| `turn_number` | `int` | Monotonically increasing, assigned by FSM at `user.input` receipt |
| `entry_type` | `enum` | user, ack, final, weave, clarification, hitl_request, hitl_response, error, proactive |
| `text` | `str` | The actual content |
| `timestamp_ms` | `int` | When this entry was created |
| `source` | `enum` | user, front, back, system |
| `task_id` | `str or None` | Associated task (for weave, hitl, error entries) |
| `metadata` | `dict` | Machine-readable context: emotion (from Phase 1), intent (from Phase 1), tool_calls_summary (for ack entries), artifact_id (for weave entries) |

### Turn Lifecycle: What Gets Written When

A single user turn produces multiple history entries:

```text
Turn 10:
  [0] {type: "user",  text: "Do it!", turn: 10}                      <- FSM writes on user.input
  [1] {type: "ack",   text: "On it!", turn: 10}                      <- FSM writes on ack.v1
  [2] {type: "final", text: "Done. Confirmation XYZ-123...", turn: 10, task_id: "task-42"}
                                                                       <- FSM writes on response.final.v1

Turn 11 (interleaved):
  [3] {type: "user",  text: "Also check the weather", turn: 11}
  [4] {type: "ack",   text: "Checking!", turn: 11}
  [5] {type: "weave", text: "Weather looks good! And your task is confirmed...", turn: 11, task_id: "task-43"}
                                                                       <- Weave merges async result

Turn 12 (HITL):
  [6] {type: "user",      text: "Find a restaurant", turn: 12}
  [7] {type: "ack",       text: "Looking into restaurants!", turn: 12}
  [8] {type: "hitl_request", text: "I found 3 options. Which one?", turn: 12, task_id: "task-44"}
  [9] {type: "hitl_response", text: "The second one", turn: 12, task_id: "task-44"}
  [10] {type: "final",    text: "Great choice, on it!", turn: 12, task_id: "task-44"}
```

### What Each Actor Sees from History

**Front LLM** receives the last 20 entries formatted as alternating user/assistant messages. The `entry_type` discrimination is invisible to the LLM — it sees a continuous conversation. But `metadata` on each entry provides machine-readable context that `DynamicPromptBuilder` uses to construct the Session Trajectory.

**Back LLM** receives the last 5 entries, filtered to only decision-relevant types: `user`, `final`, `hitl_response`. Back does not need ack text, weave bridges, or proactive fills. 5 entries is enough to resolve references ("do IT" — what from which turn?) without consuming unnecessary prompt tokens.

### Compatibility with Existing Turn Schema

The existing `Turn` dataclass has `user_message` and `assistant_response` as separate fields within one object. `TypedHistoryEntry` is a flat sequence. Reconciliation:

- **Implementation approach:** Use `TypedHistoryEntry` as a wrapper. Each `Turn` object is decomposed into multiple `TypedHistoryEntry` objects when written. Adjacent user + assistant entries can be re-composed into a `Turn` for backward compatibility.
- **Storage:** `history_active` internal storage still uses `Turn` objects (for FlatBuffer compatibility). The read API exposes `TypedHistoryEntry` for LLM context builders.
- **Future:** Extend `Turn` with a `sub_entries: list[TypedHistoryEntry]` field, keeping the outer Turn as a grouping container.

## Session Trajectory (Assembled View)

The Session Trajectory is NOT a new SS section. It is a **computed view** assembled by `DynamicPromptBuilder` from multiple SS sections at each Front LLM invocation. It gives the model a bird's-eye orientation before it reads the detailed cognitive state:

| Trajectory Field | Derived From | Example |
| --- | --- | --- |
| `session_goal` | `narrative_active` active threads + `beliefs_active` high-salience beliefs | "Planning a family trip, mid-June" |
| `completed_items` | `task_artifacts` (all durable outputs) | "Hotel confirmed (ref XYZ-123)" |
| `active_items` | `task_state` entries with status IN_PROGRESS or DISPATCHED | "Restaurant search in progress" |
| `open_items` | `beliefs_active` expressed intents with no matching task in `task_state` | "Activities not yet explored" |
| `emotional_arc` | `affective_now` current state + trajectory if EP has run | "Started excited, frustrated during ambiguity, now relieved" |
| `turn_count` | `meta.turn_count` | 12 |
| `session_duration` | `meta` | 45 minutes |
| `tasks_completed` | `task_state` count(COMPLETED) | 1 |
| `tasks_failed` | `task_state` count(FAILED) | 0 |

Prompt injection format (appears after identity, before cognitive state sections):

```text
SESSION TRAJECTORY:
Goal: Planning a family trip, mid-June
Completed: Hotel confirmed (ref XYZ-123)
In Progress: Restaurant search
Still Open: Activities, transportation
Emotional Arc: Started excited, frustrated during ambiguity, now relieved
Session: Turn 12 of 45-minute session. 1 task completed, 0 failed.
```

This block gives the model immediate orientation — what's done, what's pending, how the user feels — before it reads the detailed cognitive state sections. Approximately 200 tokens.

## Context Assembly per Actor

### Front LLM Context (Per Invocation)

The Front LLM's context is assembled by `DynamicPromptBuilder` based on the current `PromptMode` (determined by the FSM — see Section 4). Assembly order (token budget priority):

1. **Identity + Response Rules** (~500 tokens)
2. **Session Trajectory** (assembled view, ~200 tokens)
3. **User Input / Scenario Data** (variable)
4. **History** (last N entries per mode, ~2000 tokens max for STANDARD)
5. **Cognitive State:** scoreboard, beliefs, clarifications, narrative, affect (~1500 tokens)
6. **Task Context:** task_state + task_artifacts (~500 tokens)
7. **Persona** (~200 tokens)
8. **Tool definitions** (~800 tokens)

Total budget: ~6000 tokens for STANDARD mode. If over context window limit: `summarize_context()` compresses sections 5 and 6.

The `PromptMode` controls which SS sections are included (FULL, SLIM, or omitted) and how many history entries are injected. See Section 4's PromptMode table for per-mode configuration.

### Back LLM Context (Per Invocation)

The Back LLM gets a DIFFERENT context from Front. It is task-focused, not conversation-focused:

| Context Component | Content | Source |
| --- | --- | --- |
| System prompt | Worker identity, tool instructions | Static |
| Task specification | task_id, intents, tier, budget_hint | `task.dispatch` event payload |
| User facts and constraints | Beliefs relevant to the task | `beliefs_active` (snapshot at dispatch time) |
| Referent resolution | What "it", "there", etc. refer to | `scoreboard` referents |
| Task dependencies | Other active/completed tasks | `task_state` |
| Prior completions | What's already done (avoid re-doing) | `task_artifacts` |
| Safety constraints | What actions are allowed | `control.safety.band` |
| Conversation context | Last 5 entries (user, final, hitl_response only) | `history_active` (filtered, limited) |
| User preferences | Relevant preference fields | `persona` |
| Available tools | Functional tool definitions | Static (6 tools) |

**Why Back gets history:** Without history, Back cannot resolve references. "Do it" — do what? History shows the preceding discussion. "The cheaper one" — cheaper than what? History shows the comparison. 5 entries is enough for immediate task context without overloading with emotional/conversational detail.

**Why Back does NOT re-read SS per iteration:** Back's task is scoped by the dispatch envelope. Mid-task SS changes (Front updating beliefs) should not cause Back to change course. The dispatch snapshot is the contract. If beliefs change so significantly that the task is invalid, Front should emit `task.cancel`.

### Resume Context (After HITL Suspension)

When a suspended task resumes, Back receives its original dispatch context PLUS:

| Field | Content |
| --- | --- |
| `original_task` | The original dispatch specification |
| `findings_so_far` | ReAct message history before suspension |
| `tool_history` | Tools already called (to avoid re-execution) |
| `last_iteration` | Which ReAct iteration Back was on when it suspended |
| `resolution` | The user's answer to the HITL question |
| `resume_instruction` | "Resume from where you left off. Do NOT re-execute tools that already succeeded. Use findings_so_far as your starting state." |

## Persona Initialization

The `persona` section is immutable after session start. It is loaded from the user/family profile:

| Persona Field | Source | Purpose |
| --- | --- | --- |
| `tone` | Session config (default: "warm") | How the Front LLM should sound |
| `formality` | Session config (default: "casual") | Formal vs informal register |
| `verbosity` | Session config (default: "concise") | Response length preference |
| `family_name` | User profile | Address the family |
| `members` | User profile | List of {name, relation, age, preferences} |
| `payment_method` | User profile | Default payment for transactions |
| `dietary` | User profile | Dietary restrictions for task constraints |
| `accessibility` | User profile | Accessibility needs for task constraints |
| `language` | User profile (default: "en") | Preferred language |
| `timezone` | User profile (default: "UTC") | Local time reference |

Persona is read by Front (tone, personality), Back (user preferences for capability parameters), and ExperienceLayer's AffectiveMirror (mirroring style). It is never written after initialization.

---

# 6. The Two Actors: Front & Back

This section is the authoritative specification for both LLM actors. Everything about an actor — identity, bus subscriptions, bus emissions, tool set with full JSON schemas, production system prompt, ReAct rhythm, termination signal, context assembly, and SS read configs per PromptMode — lives here. No other section defines actor behavior. Sections 4 (FSM) and 7 (ReAct loop) define the infrastructure that invokes these actors; this section defines what each actor IS.

Two sub-sections follow the preamble: 6.1 Front LLM and 6.2 Back LLM. Each is self-contained. A developer reading only 6.1 has everything needed to implement Front. A developer reading only 6.2 has everything needed to implement Back.

## 6.0 Tool Split Rationale

The dual-actor model exists because a single LLM cannot simultaneously be warm-and-empathetic (conversational) and precise-and-tool-calling (execution) without one responsibility degrading the other (Section 1). The tool split operationalizes this separation. It determines which tools each actor receives and, consequently, what each actor can do.

### The Principle: Voice vs. Hands

**Front owns the voice.** It talks to the user — acknowledges, clarifies, presents results, tracks emotional tone, maintains conversational continuity. Its tools shape HOW the AI understands and responds. They read and write the cognitive model (beliefs, scoreboard, clarifications, narrative, affect). They never change the external world.

**Back owns the hands.** It executes tasks — discovers capabilities, invokes them, spawns agents, runs workflows. Its tools change the external world. They never talk to the user. They produce structured results that Front presents conversationally.

This maps directly to the K1 cognitive architecture skeleton's tool taxonomy:

### Tool Categories (K1 Taxonomy)

The K1 skeleton defines five tool categories. The dual-actor model assigns them by a single rule: categories that shape understanding go to Front; categories that change the world go to Back; categories that only read go to both.

| Category | Definition | Actor | Rationale |
| --- | --- | --- | --- |
| **Signal** | User-facing acknowledgment. Immediate delivery. | Front | Back never talks to the user. ACK is a conversational act. |
| **Cognitive** | Session State mutation through conversational understanding. The LLM calls these when it detects something worth updating — a fact, a correction, a topic shift, an emotional nuance. | Front | These are instruments of understanding, not execution. "Actually Thursday not Wednesday" triggers `update_beliefs()`. "ok cool" triggers zero tool calls. The LLM decides based on conversational judgment. |
| **Read** | Context retrieval with no mutations. Lock-free, parallel-safe. | Both | Front reads for conversational context ("didn't we talk about..."). Back reads for task context ("what did they prefer last time?"). Same tools, different semantic purpose (see Section 7, Shared Tools with Actor-Specific Usage). |
| **Action** | External side effects via the Fabric capability registry. Domain-agnostic — the same `invoke_capability()` routes to any registered capability. | Back | Actions change the world. Front dispatches intent; Back resolves HOW and executes. Front never invokes capabilities directly. |
| **Control** | Task lifecycle signals: dispatch (Front) and completion/suspension (Back). These are LLM tool calls intercepted by the FSM and converted to bus events. | Split | Front: `dispatch_task()` — intercepted by FSM, emitted as `k1.orchestration.task.dispatch.v1`. Back: `submit_result()` — the ONLY way to end a task (complete or suspend for HITL). |

### The Complete Tool Distribution

14 tools total. Front: 10 (Signal 1 + Cognitive 6 + Read 2 + Control 1). Back: 6 (Read 2 + Action 3 + Control 1). `recall_memory` appears in both sets with different semantics.

| Tool | Category | Actor | Purpose |
| --- | --- | --- | --- |
| `acknowledge()` | Signal | **Front** | Immediate user-facing ACK. MUST be the first tool called on every user turn. Produces the message shown to the user within 200ms. |
| `update_scoreboard()` | Cognitive | **Front** | Pronoun resolution, Question Under Discussion (QUD), salience scoring, topic shift detection. Updates conversational tracking, not task state. |
| `update_beliefs()` | Cognitive | **Front** | Create or correct factual beliefs from dialogue. Subject-predicate-object triples with confidence. Facts come from conversation, not from task execution. |
| `update_clarifications()` | Cognitive | **Front** | Semantic gaps detected in user intent. Only the LLM can determine what's unclear — Phase 1 handles syntax, the LLM handles meaning. |
| `update_narrative()` | Cognitive | **Front** | Thread switching and resumption tracking. Maintains the conversational narrative structure across topic changes. |
| `refine_affect()` | Cognitive | **Front** | Override Phase 1 emotion classification when the LLM detects nuance (sarcasm, mixed signals, contextual shifts) that deterministic classification missed. |
| `promote_belief()` | Cognitive | **Front** | WARM-to-HOT belief promotion. Requires conversational judgment to decide when an old fact becomes relevant again. MEDIUM/HIGH tiers only. |
| `summarize_context()` | Read | **Front** | Token budget management. Compresses SS sections when context exceeds the prompt window. Front-only because it manages Front's own prompt. |
| `recall_memory()` | Read | **Both** | K0 long-term memory retrieval. Front: conversational context before dispatch. Back: task context before capability invocation. (See Section 7 for dual-use semantics.) |
| `dispatch_task()` | Control | **Front** | Dispatch structured intents to the worker. FSM intercepts this tool call and emits `k1.orchestration.task.dispatch.v1` on the bus. The LLM never sees the bus event — it calls a tool with JSON Schema validation, parameter constraints, and in-context examples. |
| `discover_capabilities()` | Read | **Back** | Semantic search across the Fabric capability registry. Back resolves HOW to execute — Front only dispatches WHAT to execute. |
| `invoke_capability()` | Action | **Back** | The universal executor. ALL Fabric capabilities route through this single tool. Domain-agnostic — same tool for scheduling, search, content generation, commerce, or any other registered capability. |
| `spawn_via_fabric()` | Action | **Back** | Dynamic specialist agent creation via Fabric. MEDIUM/HIGH tiers only. |
| `execute_workflow()` | Action | **Back** | Multi-step Orchestrator workflow execution (DAG). MEDIUM/HIGH tiers only. |
| `submit_result()` | Control | **Back** | The ONLY way to end a task. Two modes: `result_type="complete"` (task done, structured results) or `result_type="needs_human"` (suspend for HITL, emit `task.suspended`). |

### Why Control Tools Are LLM Tools (Not Structured Output)

Both `dispatch_task()` and `submit_result()` could theoretically be structured output fields. They are tools instead because:

1. **JSON Schema contract.** The LLM gets parameter validation, type constraints, and `required` fields. A structured output field is a loose text blob that needs post-hoc parsing.
2. **In-context examples.** Tool calls have a native example format in the chat API. Structured output requires custom prompt engineering for each provider.
3. **ReAct consistency.** Both actors use the same ReAct loop (Section 7). Making lifecycle signals tool calls means the loop handles them identically to any other tool — same observation, same message history format, same termination logic.
4. **FSM interception is clean.** The FSM checks `if tc.name == "dispatch_task"` in the ReAct loop (Section 7). This is a single conditional, not a parser. Same for `submit_result` as Back's termination signal.

### The `invoke_capability()` Universal Executor Pattern

The Back LLM does NOT have domain-specific tools. It has ONE universal tool that routes through the Fabric capability registry. Any capability the system needs can be registered in Fabric and immediately becomes accessible — no code changes to the Concierge:

```python
# Any domain, same tool:
invoke_capability("tool.execute.hotel_search", {"city": "Napa", "dates": "June 15-17"})
invoke_capability("tool.execute.appointment_schedule", {"provider": "Dr. Smith", "date": "March 5"})
invoke_capability("tool.execute.calendar_create", {"title": "Team standup", "recurrence": "daily"})
invoke_capability("tool.execute.essay_draft", {"topic": "Climate change", "style": "argumentative"})
invoke_capability("tool.execute.product_search", {"query": "laptop under $1000", "sort": "rating"})
```

The Fabric capability registry is the catalog. The Back LLM is the cursor. `discover_capabilities()` finds what's available; `invoke_capability()` executes it. This separation means the Concierge architecture is domain-invariant — adding a new domain is a Fabric registration, not a Concierge code change.

### Tool Allowlists by Actor and Tier

Not every tool is available at every complexity tier. LOW tier is lightweight (fewer tools, fewer iterations). MEDIUM/HIGH unlock discovery, spawning, and workflow execution.

**Front Allowlist:**

| Tool | LOW | MEDIUM | HIGH | CRISIS |
| --- | --- | --- | --- | --- |
| `acknowledge()` | Y | Y | Y | -- |
| `update_scoreboard()` | Y | Y | Y | -- |
| `update_beliefs()` | Y | Y | Y | -- |
| `update_clarifications()` | Y | Y | Y | -- |
| `update_narrative()` | Y | Y | Y | -- |
| `refine_affect()` | Y | Y | Y | -- |
| `promote_belief()` | -- | Y | Y | -- |
| `recall_memory()` | Y | Y | Y | -- |
| `summarize_context()` | Y | Y | Y | -- |
| `dispatch_task()` | Y | Y | Y | -- |

**Back Allowlist:**

| Tool | LOW | MEDIUM | HIGH |
| --- | --- | --- | --- |
| `recall_memory()` | Y | Y | Y |
| `discover_capabilities()` | -- | Y | Y |
| `invoke_capability()` | Y | Y | Y |
| `spawn_via_fabric()` | -- | Y | Y |
| `execute_workflow()` | -- | Y | Y |
| `submit_result()` | Y | Y | Y |

LOW tier Back has only 3 tools (`recall_memory` + `invoke_capability` + `submit_result`) because the capability is already resolved by Front's dispatch. No discovery or spawning needed.

**Conditional tool inclusion (PromptMode-level):** Beyond tier-based filtering, some tools are conditionally included based on Session State signals at prompt assembly time (see Section 6.1 for details):

- `refine_affect()` is NOT in STANDARD mode by default — only added if `affect_confidence < 0.6` (Phase 1 was uncertain).
- `promote_belief()` is NOT in STANDARD mode by default — only added if `tier != "LOW"` (WARM-to-HOT promotion is unnecessary for simple turns).

These conditionals reduce prompt token overhead per invocation without losing capability when the signals indicate need.

### Why This Split is Not Custom

The tool sets are NOT POC-specific inventions. They are the real K1 production tools from the cognitive architecture skeleton, partitioned by actor. The categories (Signal, Cognitive, Read, Action, Control) are the skeleton's own taxonomy. The `ToolSchema` dataclass carries the category field explicitly:

```python
@dataclass(frozen=True)
class ToolSchema:
    """Provider-agnostic tool definition."""
    name: str
    description: str
    parameters: dict          # JSON Schema object
    returns: dict             # JSON Schema describing return value
    actor: str                # "front" | "back" | "both"
    category: str             # "signal" | "cognitive" | "read" | "action" | "control"
    side_effects: bool        # Does this tool mutate state?
```

No POC-only tools that would need to be refactored later. The split is the production split. Implementation changes the adapter (Section 10) and the Fabric registration; the tool taxonomy and actor assignment are final.

### What Mixing Tools in One Prompt Creates

This is the empirical motivation for the split — what happens when you DON'T separate:

| Failure Mode | Root Cause | How the Split Fixes It |
| --- | --- | --- |
| Tone collapse | LLM switches to terse tool-calling mode after `invoke_capability()` and stays there for the conversational response. | Front never sees `invoke_capability`. It receives structured results and applies its full conversational personality. |
| Cognitive tool starvation | With 16 tools in one prompt, the LLM gravitates toward action tools (they "do something") and skips cognitive tools (they "just update state"). Beliefs go stale. | Front has only cognitive + signal + read tools. It cannot skip cognition in favor of execution — there is no execution to skip to. |
| Anti-spin false positives | Guard logic detects "too many tool calls without text" and forces text output. But cognitive tools (scoreboard, beliefs, clarifications) naturally fire in sequence without text. Guard kills cognitive processing. | Each actor has its own iteration limit and termination signal. Front terminates on text-without-tools. Back terminates on `submit_result`. No cross-purpose guards needed. |
| Context window pressure | 16 tool schemas in the prompt consume ~1600 tokens. Adding per-tool instructions and examples pushes past 2500 tokens just for tools. | Front: ~800 tokens for 10 tools. Back: ~400 tokens for 6 tools. Neither approaches the pressure threshold. |
| Error attribution | When a single loop calls cognitive tools AND action tools AND produces text, a failure could be in understanding, execution, or presentation. Debugging requires tracing through all three. | Front failures are always conversational. Back failures are always execution. The bus event trail shows exactly which actor failed and at which step. |

## 6.1 Front LLM (The Concierge Voice)

### Identity

The personality. Warm, empathetic, family-aware. Talks to the user. Never executes functional tools. From the user's perspective, the Front LLM IS the entire system — it acknowledges, clarifies, presents results, tracks emotional tone, maintains conversational continuity, and dispatches work. It never mentions internal systems, workers, buses, or execution paths.

The Front is a cognitive reasoner and a dispatcher. It understands intent, emotion, context, and nuance. When the user needs something done, Front describes the task via `dispatch_task()` and the FSM routes it to Back. Front never sees how tasks execute — it receives structured results and presents them conversationally.

The Front handles ANY topic the user brings up — travel, health, education, finance, creative work, daily planning, family coordination, IoT, communication. Its cognitive tools let it track beliefs, emotions, topics, and gaps across all domains simultaneously. Domain-specific rules are injected into the prompt based on Phase 1 classification (see Domain Rule Injection below).

### Bus Subscriptions

| Event | Priority | Purpose |
| --- | --- | --- |
| `k1.session.user.input.v1` | URGENT | New user message. Triggers ACKING -> DISPATCHING flow. |
| `k1.orchestration.task.complete.v1` | INTERACTIVE | Worker finished. Triggers DELIVERING flow. |
| `k1.orchestration.task.failed.v1` | INTERACTIVE | Worker failed. Triggers ERROR mode presentation. |
| `k1.orchestration.task.suspended.v1` | INTERACTIVE | Worker needs human input. Triggers HITL_RELAY mode. |
| `k1.orchestration.findings.ready.v1` | INTERACTIVE | Partial results available (streaming). |
| `k1.internal.weave.batch.v1` | INTERACTIVE | Async results queued for weave presentation. |

### Bus Emissions

| Event | Priority | Trigger |
| --- | --- | --- |
| `k1.response.ack.v1` | URGENT | `acknowledge()` tool call in ReAct iteration 1. |
| `k1.response.final.v1` | URGENT | Text response with no tool calls (ReAct termination). |
| `k1.response.clarification.v1` | URGENT | Text response in CLARIFY_ASK mode. |
| `k1.orchestration.task.dispatch.v1` | INTERACTIVE | FSM intercepts `dispatch_task()` tool call and emits. |
| `k1.orchestration.task.cancel.v1` | URGENT | User requests cancellation during INTERRUPT_HANDLING. |
| `k1.orchestration.task.resume.v1` | INTERACTIVE | Front relays user's HITL answer to Back. |
| `k1.orchestration.clarification.response.v1` | INTERACTIVE | Front answers Back's clarification question. |

### Tool Schemas (Full JSON)

10 tools: Signal 1 + Cognitive 6 + Read 2 + Control 1. Every schema includes `name`, `description`, `parameters` (JSON Schema), `returns` (JSON Schema), `actor`, `category`, and `side_effects`.

```python
FRONT_TOOL_SCHEMAS = [

    # ---- SIGNAL (1) ----

    ToolSchema(
        name="acknowledge",
        description=(
            "Acknowledge the user's input immediately. MUST be the first tool called "
            "on every user turn. Produces the ACK message shown to user within 200ms. "
            "Call EXACTLY ONCE per turn. Do NOT call on task.complete or weave triggers."
        ),
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Short acknowledgment text for the user (1-2 sentences max)."
                },
            },
            "required": ["message"],
        },
        returns={
            "type": "object",
            "properties": {
                "delivered": {"type": "boolean"},
                "timestamp_ms": {"type": "integer"},
            },
        },
        actor="front",
        category="signal",
        side_effects=False,
    ),

    # ---- COGNITIVE (6) ----

    ToolSchema(
        name="update_beliefs",
        description=(
            "Create or correct factual beliefs from the conversation. Call when user "
            "states facts, preferences, constraints, or corrections. Each belief is a "
            "subject-predicate-object triple with confidence. Examples: "
            "('user', 'prefers', 'Italian food', 0.9), "
            "('trip', 'has_dates', 'June 15-17', 1.0), "
            "('budget', 'is', 'under $600/night', 0.8)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "beliefs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "predicate": {"type": "string"},
                            "object": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["subject", "predicate", "object", "confidence"],
                    },
                    "minItems": 1,
                    "description": "One or more belief triples to store."
                },
            },
            "required": ["beliefs"],
        },
        returns={
            "type": "object",
            "properties": {
                "stored": {"type": "integer", "description": "Number of beliefs stored"},
                "updated": {"type": "integer", "description": "Number of existing beliefs updated"},
            },
        },
        actor="front",
        category="cognitive",
        side_effects=True,
    ),

    ToolSchema(
        name="update_scoreboard",
        description=(
            "Update the conversational scoreboard: Question Under Discussion (QUD), "
            "referent resolution, salience map, and topic shifts. Call when the user "
            "changes topic, uses pronouns that need resolution, or asks a new question. "
            "Phase 1 (UltraBERT) sets initial intents and entities; this tool REFINES them."
        ),
        parameters={
            "type": "object",
            "properties": {
                "qud_push": {
                    "type": "string",
                    "description": "New Question Under Discussion to push on stack. Null if no new question.",
                },
                "qud_pop": {
                    "type": "boolean",
                    "description": "Pop the current QUD (question answered). Default false.",
                    "default": False,
                },
                "referent_updates": {
                    "type": "object",
                    "description": "Map of pronoun/reference -> resolved entity. E.g. {'it': 'Vineyard Inn', 'there': 'Napa Valley'}.",
                    "additionalProperties": {"type": "string"},
                },
                "topic_shift": {
                    "type": "string",
                    "description": "New topic if user shifted conversation. Null if same topic.",
                },
            },
            "required": [],
        },
        returns={
            "type": "object",
            "properties": {
                "qud_depth": {"type": "integer"},
                "active_referents": {"type": "integer"},
            },
        },
        actor="front",
        category="cognitive",
        side_effects=True,
    ),

    ToolSchema(
        name="update_clarifications",
        description=(
            "Record semantic gaps detected in user intent. Call when user's request "
            "is ambiguous, underspecified, or contradicts existing beliefs. "
            "Each gap has a field (what's missing), a question (what to ask), "
            "and severity (how blocking it is)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string", "description": "What information is missing"},
                            "question": {"type": "string", "description": "Natural language question to resolve it"},
                            "severity": {"type": "string", "enum": ["blocking", "helpful", "minor"]},
                        },
                        "required": ["field", "question", "severity"],
                    },
                },
                "resolved_gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Field names of previously recorded gaps that are now resolved.",
                },
            },
            "required": [],
        },
        returns={
            "type": "object",
            "properties": {
                "open_gaps": {"type": "integer"},
                "blocking_gaps": {"type": "integer"},
            },
        },
        actor="front",
        category="cognitive",
        side_effects=True,
    ),

    ToolSchema(
        name="update_narrative",
        description=(
            "Track conversation thread switches and resumptions. Call when user "
            "changes topic (switch), returns to a previous topic (resume), "
            "or finishes a topic (close). Maintains narrative_active section."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["switch", "resume", "close"],
                    "description": "What happened to the narrative thread.",
                },
                "thread_id": {
                    "type": "string",
                    "description": "Identifier for the thread (e.g. 'hotel_booking', 'gym_discussion', 'weather').",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of thread state at switch/close point.",
                },
            },
            "required": ["action", "thread_id"],
        },
        returns={
            "type": "object",
            "properties": {
                "active_thread": {"type": "string"},
                "total_threads": {"type": "integer"},
            },
        },
        actor="front",
        category="cognitive",
        side_effects=True,
    ),

    ToolSchema(
        name="refine_affect",
        description=(
            "Override Phase 1 (UltraBERT) emotion classification with LLM's "
            "assessment. Call when you detect emotional signals that the "
            "deterministic classifier missed: sarcasm, irony, mixed emotions, "
            "subtle frustration, excitement masked as calm, etc."
        ),
        parameters={
            "type": "object",
            "properties": {
                "emotion": {"type": "string", "description": "Primary emotion label (joy, frustration, anxiety, excitement, calm, etc.)"},
                "valence": {"type": "number", "minimum": -1.0, "maximum": 1.0, "description": "-1.0 negative to +1.0 positive"},
                "arousal": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "0.0 calm to 1.0 excited"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "How confident in this override"},
                "reason": {"type": "string", "description": "Why you're overriding Phase 1's classification"},
            },
            "required": ["emotion", "valence", "arousal", "confidence"],
        },
        returns={
            "type": "object",
            "properties": {
                "previous_emotion": {"type": "string"},
                "updated": {"type": "boolean"},
            },
        },
        actor="front",
        category="cognitive",
        side_effects=True,
    ),

    ToolSchema(
        name="promote_belief",
        description=(
            "Promote a low-confidence or WARM-tier belief to HOT/high-confidence. "
            "Call when conversation confirms a previously uncertain belief. "
            "MEDIUM and HIGH tier only."
        ),
        parameters={
            "type": "object",
            "properties": {
                "belief_id": {"type": "string", "description": "ID of the belief to promote"},
                "new_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "reason": {"type": "string", "description": "Why this belief is now confirmed"},
            },
            "required": ["belief_id", "new_confidence"],
        },
        returns={
            "type": "object",
            "properties": {
                "promoted": {"type": "boolean"},
                "from_tier": {"type": "string"},
            },
        },
        actor="front",
        category="cognitive",
        side_effects=True,
    ),

    # ---- READ (2) ----

    ToolSchema(
        name="recall_memory",
        description=(
            "Query K0 long-term memory for relevant context. Returns past experiences, "
            "preferences, and facts from previous sessions. Use for: "
            "'didn't we stay at...', 'what restaurant did we like...', 'last time we...'. "
            "Front uses for conversational context. Back uses for task-specific history."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language memory query"},
                "memory_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["episodic", "semantic", "procedural"]},
                    "description": "Which memory stores to search. Default: all.",
                },
                "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
        returns={
            "type": "object",
            "properties": {
                "memories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "type": {"type": "string"},
                            "relevance": {"type": "number"},
                            "timestamp": {"type": "string"},
                        },
                    },
                },
                "count": {"type": "integer"},
            },
        },
        actor="both",
        category="read",
        side_effects=False,
    ),

    ToolSchema(
        name="summarize_context",
        description=(
            "Compress Session State sections to fit within token budget. "
            "Call when the system prompt is too large. Returns compressed version "
            "of specified sections. This is a token management tool, not a user-facing tool."
        ),
        parameters={
            "type": "object",
            "properties": {
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "SS section names to compress (e.g. ['beliefs_active', 'history_active'])",
                },
                "target_tokens": {"type": "integer", "description": "Target token count for compressed output"},
            },
            "required": ["sections", "target_tokens"],
        },
        returns={
            "type": "object",
            "properties": {
                "compressed": {"type": "string", "description": "Compressed text representation"},
                "original_tokens": {"type": "integer"},
                "compressed_tokens": {"type": "integer"},
            },
        },
        actor="front",
        category="read",
        side_effects=False,
    ),

    # ---- CONTROL (1) ----

    ToolSchema(
        name="dispatch_task",
        description=(
            "Dispatch a task to the background worker for execution. Use when the user "
            "wants something DONE (search, book, create, schedule, send, draft, etc.). "
            "Do NOT call for pure conversation, emotional support, or clarification. "
            "The FSM intercepts this tool call and emits k1.orchestration.task.dispatch.v1 "
            "on the bus. The tool itself returns immediately with {queued: true}. "
            "For multi-intent messages, call dispatch_task ONCE with multiple intents "
            "in the intents array, OR call it multiple times for chained tasks with depends_on."
        ),
        parameters={
            "type": "object",
            "properties": {
                "intents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "description": "What to do (natural language or capability name)"},
                            "params": {"type": "object", "description": "Structured parameters extracted from conversation and beliefs"},
                            "domain": {"type": "string", "description": "Domain hint: travel, health, productivity, finance, creative, shopping, family, etc."},
                        },
                        "required": ["action"],
                    },
                    "minItems": 1,
                    "description": "One or more intents to execute. Independent intents are bundled. Sequential intents use depends_on.",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["normal", "urgent", "background"],
                    "default": "normal",
                },
                "reference_context": {
                    "type": "object",
                    "description": (
                        "Resolved references for the Back worker. Front resolves pronouns and "
                        "references using its 20-entry history view and passes resolved values here. "
                        "E.g. {'the hotel': 'Vineyard Inn', 'it': 'restaurant search', 'the cheaper one': 'Marriott $185/night'}."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "depends_on": {
                    "type": "string",
                    "description": "Task ID this dispatch depends on (for chained tasks). Omit for independent tasks.",
                },
            },
            "required": ["intents"],
        },
        returns={
            "type": "object",
            "properties": {
                "queued": {"type": "boolean"},
                "task_id": {"type": "string"},
            },
        },
        actor="front",
        category="control",
        side_effects=False,  # The tool itself does not mutate -- FSM emits the event
    ),
]
```

### Prompt Architecture: Mode-Driven Assembly

The monolithic system prompt approach — delivering ~2100 words of instructions on EVERY invocation regardless of FSM state — wastes tokens and dilutes focus. A CLARIFYING_USER invocation does not need DISPATCH RULES, WEAVE PROTOCOL, or 5 standard-mode examples. The mode-driven architecture replaces the monolithic approach: the FSM state determines a `PromptMode`, and the `PromptMode` determines exactly which tools, SS sections, prompt sections, examples, affect modifiers, and domain rules are injected. Nothing more.

**Design principle:** The FSM already KNOWS the cognitive mode. It TELLS the prompt builder rather than leaving the LLM to infer it from a wall of instructions.

#### PromptMode Enum

```python
from enum import Enum

class PromptMode(Enum):
    """Cognitive mode for Front LLM prompt assembly.
    Each mode selects a specific subset of tools, SS sections,
    prompt sections, examples, and modulation rules.
    """
    STANDARD        = "standard"         # Normal user input, full cognitive processing
    CLARIFY_ASK     = "clarify_ask"      # Front detected ambiguity, asking user
    CLARIFY_RESOLVE = "clarify_resolve"  # User answered a clarification question
    HITL_RELAY      = "hitl_relay"       # Back suspended, present question to user
    HITL_RESOLVE    = "hitl_resolve"     # User answered HITL question
    PRESENT         = "present"          # Delivering task results
    WEAVE           = "weave"            # Presenting async results mid-conversation
    CANCEL          = "cancel"           # Confirming/handling cancellation
    INTERRUPT       = "interrupt"        # New user input while task in progress
    ERROR           = "error"            # Task failed, explaining gracefully
```

#### Mode Resolution: `determine_mode()`

Maps FSM state + incoming event + Session State signals to exactly one `PromptMode`. Priority order (first match wins). No ambiguity — every combination resolves to exactly one mode. Defined in Section 4 (FSM state table + mode resolution logic). Cross-referenced here for completeness:

1. **Explicit FSM state:** CANCELLING -> CANCEL, INTERRUPT_HANDLING -> INTERRUPT.
2. **FSM state + event topic:** CLARIFYING_USER + `user.input` -> CLARIFY_RESOLVE; CLARIFYING_USER -> CLARIFY_ASK; CLARIFYING_WORKER + `user.input` -> HITL_RESOLVE; CLARIFYING_WORKER -> HITL_RELAY.
3. **Event-topic-driven:** `task.complete` -> PRESENT; `task.failed` -> ERROR; `weave.batch` -> WEAVE; `task.suspended` -> HITL_RELAY.
4. **SS-signal fallbacks:** `user.input` + suspended tasks exist -> HITL_RESOLVE; `user.input` + blocking_gaps > 0 -> CLARIFY_RESOLVE.
5. **Default:** STANDARD.

Full `determine_mode()` implementation:

```python
def determine_mode(
    fsm_state: str,
    envelope: Envelope,
    clarification_state: dict,
    task_state: dict,
    affect: dict,
) -> PromptMode:
    topic = envelope.topic

    # --- Explicit FSM state mappings ---
    if fsm_state == "CANCELLING":
        return PromptMode.CANCEL
    if fsm_state == "INTERRUPT_HANDLING":
        return PromptMode.INTERRUPT
    if fsm_state == "CLARIFYING_USER":
        if topic == "k1.session.user.input.v1":
            return PromptMode.CLARIFY_RESOLVE
        return PromptMode.CLARIFY_ASK
    if fsm_state == "CLARIFYING_WORKER":
        if topic == "k1.session.user.input.v1":
            return PromptMode.HITL_RESOLVE
        return PromptMode.HITL_RELAY

    # --- Topic-driven mappings ---
    if topic == "k1.orchestration.task.complete.v1":
        return PromptMode.PRESENT
    if topic == "k1.orchestration.task.failed.v1":
        return PromptMode.ERROR
    if topic == "k1.internal.weave.batch.v1":
        return PromptMode.WEAVE
    if topic == "k1.orchestration.task.suspended.v1":
        return PromptMode.HITL_RELAY

    # --- SS-signal-driven fallbacks ---
    if topic == "k1.session.user.input.v1":
        suspended = [t for t in task_state.get("tasks", [])
                     if t.get("status") == "SUSPENDED"]
        if suspended:
            return PromptMode.HITL_RESOLVE
        if clarification_state.get("blocking_gaps", 0) > 0:
            return PromptMode.CLARIFY_RESOLVE

    # --- Default ---
    return PromptMode.STANDARD
```

### Tool Allowlist per Mode

Each mode activates a specific subset of the 10 Front tools. This is the authoritative tool allowlist — `DynamicPromptBuilder` uses it to filter `FRONT_TOOL_SCHEMAS` per invocation.

| Tool | STANDARD | CLARIFY_ASK | CLARIFY_RESOLVE | HITL_RELAY | HITL_RESOLVE | PRESENT | WEAVE | CANCEL | INTERRUPT | ERROR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `acknowledge` | Y | Y | Y | - | Y | - | - | Y | Y | - |
| `update_beliefs` | Y | - | Y | - | Y | Y | Y | Y | Y | - |
| `update_scoreboard` | Y | - | Y | - | - | - | - | - | Y | - |
| `update_clarifications` | Y | Y | Y | - | - | - | - | - | Y | - |
| `update_narrative` | Y | - | - | - | - | Y | Y | Y | Y | Y |
| `refine_affect` | cond. | - | - | - | - | - | - | - | Y | - |
| `promote_belief` | cond. | - | Y | - | - | - | - | - | Y | - |
| `recall_memory` | Y | Y | Y | - | - | - | - | - | Y | - |
| `summarize_context` | Y | - | - | - | - | - | - | - | Y | - |
| `dispatch_task` | Y | - | Y | - | - | - | - | - | Y | - |
| **Total** | **8+cond** | **3** | **7** | **0** | **2** | **2** | **2** | **3** | **10** | **1** |

**Key decisions:**

- **HITL_RELAY = 0 tools:** No user input triggered this. Back suspended. Front just translates structured HITL to natural text. Pure text-only response, single iteration.
- **CLARIFY_ASK = 3 tools:** Only acknowledge (user said something), update_clarifications (track the gap), recall_memory (might resolve from past context).
- **INTERRUPT = 10 tools:** User may be changing direction entirely. Full cognitive processing — same as STANDARD.
- **PRESENT / WEAVE = 2 tools:** Only update_beliefs (results may confirm facts) and update_narrative (close/switch thread). No ack (no user input), no dispatch (not dispatching from results).

**Conditional tool inclusion (ITEM #11):**

```python
TOOL_ALLOWLIST: dict[PromptMode, list[str]] = {
    PromptMode.STANDARD: [
        "acknowledge", "update_beliefs", "update_scoreboard",
        "update_clarifications", "update_narrative",
        "recall_memory", "summarize_context", "dispatch_task",
        # NOTE: refine_affect and promote_belief are NOT in STANDARD by default.
        # They are added conditionally at prompt assembly time:
        #   refine_affect:  add if affect_confidence < 0.6 (Phase 1 was uncertain)
        #   promote_belief: add if tier != "LOW" (WARM-to-HOT only for MEDIUM/HIGH)
    ],
    PromptMode.CLARIFY_ASK: [
        "acknowledge", "update_clarifications", "recall_memory",
    ],
    PromptMode.CLARIFY_RESOLVE: [
        "acknowledge", "update_beliefs", "update_scoreboard",
        "update_clarifications", "promote_belief", "recall_memory", "dispatch_task",
    ],
    PromptMode.HITL_RELAY: [],  # Pure text-only
    PromptMode.HITL_RESOLVE: [
        "acknowledge", "update_beliefs",
    ],
    PromptMode.PRESENT: [
        "update_beliefs", "update_narrative",
    ],
    PromptMode.WEAVE: [
        "update_beliefs", "update_narrative",
    ],
    PromptMode.CANCEL: [
        "acknowledge", "update_beliefs", "update_narrative",
    ],
    PromptMode.INTERRUPT: [
        "acknowledge", "update_beliefs", "update_scoreboard",
        "update_clarifications", "update_narrative", "refine_affect",
        "promote_belief", "recall_memory", "summarize_context", "dispatch_task",
    ],
    PromptMode.ERROR: [
        "update_narrative",
    ],
}
```

The conditional inclusion logic runs inside `DynamicPromptBuilder.build()`:

```python
# After selecting base tool names from TOOL_ALLOWLIST[mode]:
if mode == PromptMode.STANDARD:
    affect_conf = ss.affective_now.get_confidence()
    if affect_conf < 0.6:
        tool_names.append("refine_affect")
    tier = ss.control.get_complexity_tier()
    if tier != "LOW":
        tool_names.append("promote_belief")
```

This means STANDARD mode has 8 tools by default, 9 if Phase 1 affect is uncertain, 10 if also MEDIUM/HIGH tier. INTERRUPT always gets all 10 because the user may be changing direction entirely.

### Max Iterations per Mode

Budget awareness per mode prevents wasted LLM calls. Each mode has a default and a crisis override (applied when `affect_band == "crisis"`):

| Mode | Default | Crisis | Rationale |
| --- | --- | --- | --- |
| STANDARD | 6 | 4 | Full cognitive processing, possible multi-tool + dispatch |
| CLARIFY_ASK | 3 | 2 | Ack + clarification tool + text. Short turn. |
| CLARIFY_RESOLVE | 5 | 4 | Ack + beliefs + resolve gap + possible dispatch + text |
| HITL_RELAY | 1 | 1 | Pure text-only. No tools. Single iteration. |
| HITL_RESOLVE | 3 | 2 | Ack + beliefs + text |
| PRESENT | 3 | 2 | Beliefs update + narrative close + text |
| WEAVE | 3 | 2 | Beliefs update + narrative + text |
| CANCEL | 3 | 2 | Ack + narrative close + text |
| INTERRUPT | 6 | 4 | Same as STANDARD — full cognitive processing |
| ERROR | 2 | 2 | Narrative close + text. Keep it brief. |

```python
MAX_ITERATIONS_TABLE: dict[PromptMode, int] = {
    PromptMode.STANDARD: 6, PromptMode.CLARIFY_ASK: 3, PromptMode.CLARIFY_RESOLVE: 5,
    PromptMode.HITL_RELAY: 1, PromptMode.HITL_RESOLVE: 3, PromptMode.PRESENT: 3,
    PromptMode.WEAVE: 3, PromptMode.CANCEL: 3, PromptMode.INTERRUPT: 6, PromptMode.ERROR: 2,
}

CRISIS_ITERATIONS_TABLE: dict[PromptMode, int] = {
    PromptMode.STANDARD: 4, PromptMode.CLARIFY_ASK: 2, PromptMode.CLARIFY_RESOLVE: 4,
    PromptMode.HITL_RELAY: 1, PromptMode.HITL_RESOLVE: 2, PromptMode.PRESENT: 2,
    PromptMode.WEAVE: 2, PromptMode.CANCEL: 2, PromptMode.INTERRUPT: 4, PromptMode.ERROR: 2,
}
```

### Session State Read Configuration per Mode

Each mode reads a different subset of SS sections with different depth (FULL, SLIM, or skipped). This is the authoritative SS read matrix — `DynamicPromptBuilder` uses it to control what cognitive context reaches the LLM.

| SS Section | STANDARD | CLARIFY_ASK | CLARIFY_RESOLVE | HITL_RELAY | HITL_RESOLVE | PRESENT | WEAVE | CANCEL | INTERRUPT | ERROR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `beliefs_active` | FULL | SLIM | FULL | - | SLIM | SLIM | SLIM | SLIM | FULL | - |
| `scoreboard` | FULL | SLIM | FULL | - | SLIM | - | - | - | FULL | - |
| `affective_now` | FULL | FULL | FULL | FULL | FULL | FULL | FULL | FULL | FULL | FULL |
| `clarifications` | FULL | FULL | FULL | - | - | - | - | - | FULL | - |
| `narrative_active` | FULL | - | SLIM | - | - | SLIM | FULL | SLIM | FULL | SLIM |
| `control` | FULL | SLIM | SLIM | SLIM | SLIM | SLIM | SLIM | SLIM | FULL | SLIM |
| `history_active` | 20 entries | 10 entries | 15 entries | 0 entries | 5 entries | 10 entries | 10 entries | 5 entries | 20 entries | 5 entries |
| `meta` | - | - | - | - | - | - | - | - | - | - |
| `persona` | FULL | FULL | FULL | FULL | FULL | FULL | FULL | FULL | FULL | FULL |
| `task_state` | FULL | - | SLIM | FULL | FULL | FULL | FULL | FULL | FULL | FULL |
| `task_artifacts` | FULL | - | - | - | - | FULL | FULL | - | FULL | SLIM |
| **Est. tokens** | **~5500** | **~2200** | **~3800** | **~1200** | **~2000** | **~3000** | **~3200** | **~2000** | **~5500** | **~1800** |

**SLIM definitions:**

| Section | SLIM means |
| --- | --- |
| `beliefs_active` | High-confidence only (confidence >= 0.7) |
| `scoreboard` | QUD + active referents only, no salience map |
| `narrative_active` | Active thread name + status only, no history |
| `control` | FSM state + safety band only |
| `task_state` | Status summary per task, no detailed fields |
| `task_artifacts` | Type + summary only, no data payloads |

```python
@dataclass
class SSReadConfig:
    """Specifies how to read each SS section for a given mode."""
    section: str
    read_mode: Literal["full", "slim", "skip"]
    history_window: int = 20          # Only for history_active

SS_READ_CONFIGS: dict[PromptMode, list[SSReadConfig]] = {
    PromptMode.STANDARD: [
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "full"),
        SSReadConfig("history_active", "full", history_window=20),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
    ],
    PromptMode.CLARIFY_ASK: [
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("scoreboard", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
    ],
    PromptMode.CLARIFY_RESOLVE: [
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=15),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "slim"),
    ],
    PromptMode.HITL_RELAY: [
        SSReadConfig("affective_now", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.HITL_RESOLVE: [
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("scoreboard", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.PRESENT: [
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
        SSReadConfig("beliefs_active", "slim"),
    ],
    PromptMode.WEAVE: [
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
        SSReadConfig("beliefs_active", "slim"),
    ],
    PromptMode.CANCEL: [
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.INTERRUPT: [
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "full"),
        SSReadConfig("history_active", "full", history_window=20),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
    ],
    PromptMode.ERROR: [
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "slim"),
    ],
}
```

### Prompt Sections (Full Production Text)

The monolithic prompt is decomposed into named sections. Each `PromptMode` selects a subset via `MODE_SECTIONS`. The builder concatenates only the selected sections.

```python
PROMPT_SECTIONS: dict[str, str] = {

    # ================================================================
    # IDENTITY -- Included in ALL modes. ~150 tokens.
    # ================================================================
    "IDENTITY": """
== IDENTITY ==
You are the Concierge -- the family's trusted advisor and conversational partner.

What you ARE:
- The only voice the user hears. Every response passes through you.
- A cognitive reasoner: you understand intent, emotion, context, and nuance.
- A dispatcher: when the user needs something DONE, you describe the task
  and the system handles execution.

What you are NOT:
- An executor. You never search, book, create, send, or modify anything directly.
- A relay. You don't parrot results -- you interpret, contextualize, and present
  them in your own voice.

What you can SEE:
- Session State (in this prompt): beliefs, scoreboard, affect, narrative threads,
  task status, completed artifacts, persona preferences.
- Chat history (in the messages below): last 2-3 conversational turns.
- K0 long-term memory (via the recall_memory tool).

What you CANNOT see:
- How tasks are executed. You dispatch; the system delivers results.
- Other users' private data (cross-member privacy boundary).
- Future tool availability. Don't promise specific capabilities.

Your relationship to the user:
- Trusted advisor, not servant. You anticipate, suggest, and protect.
- You match the user's emotional register (see EMOTIONAL CALIBRATION below).
- You respect boundaries: DND rules, no-interrupt windows, privacy flags.
- From the user's perspective, YOU are doing everything. Never mention
  "the system", "the worker", "the back", or "the bus".
""",

    # ================================================================
    # REACT_RHYTHM -- Full version. STANDARD, CLARIFY_RESOLVE, INTERRUPT.
    # ~200 tokens.
    # ================================================================
    "REACT_RHYTHM": """
== REACT RHYTHM ==
You operate in a Think-Act-Observe loop. Each iteration you:
  1. THINK: Assess what you know and what you still need.
  2. ACT: Call ONE tool.
  3. OBSERVE: Read the tool result. It appears in your next iteration.

Iteration guidelines:
  - Iteration 1: ALWAYS call acknowledge() first. Non-negotiable.
  - Iteration 2+: Call tools based on what you learned from observations.
    If recall_memory returned relevant context, use it in update_beliefs.
    If beliefs show a gap, call update_clarifications.
    If user wants action, call dispatch_task.
  - Final iteration: Generate your text response to the user with NO tool calls.
    This ends your turn. The text becomes the user-facing message.

Typical turn (3-5 iterations):
  1. acknowledge()
  2. recall_memory() -- if past context needed
  3. update_beliefs() or update_scoreboard() -- if new facts or topic shift
  4. dispatch_task() -- if user wants something done
  5. Text response (no tools) -- present to user

Short turn (2 iterations):
  1. acknowledge()
  2. Text response -- for greetings, simple answers, emotional support

Budget: Maximum {max_iterations} iterations per turn.
If you reach the limit without generating text, the system forces a text-only
response. Plan accordingly.

On task_complete / weave / hitl triggers:
  You are re-invoked with results in your context (see scenario block below).
  Do NOT call acknowledge() on these triggers -- there is no user input to ack.
  Go directly to cognitive tools or text response.
""",

    # ================================================================
    # REACT_RHYTHM_REDUCED -- Short version. CLARIFY_ASK, HITL_RESOLVE,
    # CANCEL. ~80 tokens.
    # ================================================================
    "REACT_RHYTHM_REDUCED": """
== REACT RHYTHM ==
Short turn. Follow this pattern:
  1. acknowledge() -- if this was triggered by user input.
  2. 0-1 cognitive tools -- only if genuinely needed.
  3. Text response with NO tool calls -- ends your turn.

Budget: Maximum {max_iterations} iterations. Keep it brief and focused.
Do NOT call acknowledge() on task_complete, weave, or hitl triggers.
""",

    # ================================================================
    # STATE_INTERP -- Full version. STANDARD, CLARIFY_RESOLVE, INTERRUPT.
    # ~200 tokens.
    # ================================================================
    "STATE_INTERP": """
== STATE INTERPRETATION GUIDE ==
You receive Session State context below. Here is how to READ it:

affective_now:
  valence < -0.5 AND arousal > 0.7: User in distress (panic, anger, frustration).
    -> Calm, structured, decisive. Reduce options. Lead with action.
  valence < -0.3 AND arousal < 0.4: User is low (sad, tired, defeated).
    -> Gentle, brief. Don't force cheerfulness. Offer practical help.
  valence > 0.5 AND arousal > 0.6: User is excited or happy.
    -> Match energy. Celebrate. Be enthusiastic.
  valence near 0, arousal near 0.5: Neutral or calm.
    -> Efficient, informative, light personality.

beliefs_active:
  confidence >= 0.8: Treat as fact. Act on it.
  confidence 0.5-0.8: Likely true. Mention but don't commit.
  confidence < 0.5: Uncertain. Confirm before acting.

task_state:
  DISPATCHED or IN_PROGRESS: Task running. Tell user it's in progress if relevant.
  SUSPENDED: Task paused for user input. Prioritize addressing this.
  COMPLETED: Results available. Present them.
  CANCELLED: Confirm cancellation to user.
  FAILED: Explain gracefully. Suggest alternatives.

clarifications:
  blocking_gaps > 0: You MUST ask the user before dispatching a task.
  helpful/minor gaps: Dispatch anyway, note the gap in reference_context.
""",

    # ================================================================
    # STATE_INTERP_CLARIFY -- Focused for CLARIFY_ASK. ~60 tokens.
    # ================================================================
    "STATE_INTERP_CLARIFY": """
== STATE INTERPRETATION ==
clarifications:
  blocking_gaps > 0 means you MUST ask the user before dispatching.
  Focus on the highest-severity gap first. One question at a time.
  Open gaps: {open_gaps_list}
""",

    # ================================================================
    # STATE_INTERP_TASK -- Focused for HITL_RESOLVE. ~60 tokens.
    # ================================================================
    "STATE_INTERP_TASK": """
== STATE INTERPRETATION ==
task_state:
  SUSPENDED = a task is paused waiting for user input. This is your TOP priority.
  Read the pending_hil to determine what kind of input is needed.
  Parse the user's answer and confirm before relaying resolution.
""",

    # ================================================================
    # STATE_INTERP_PRESENT -- Focused for PRESENT mode. ~60 tokens.
    # ================================================================
    "STATE_INTERP_PRESENT": """
== STATE INTERPRETATION ==
task_state:
  COMPLETED = results are available below. Present them naturally in your voice.
  Don't list raw data -- interpret, contextualize, highlight what matters.
task_artifacts:
  Durable outputs (bookings, appointments, documents). Mention confirmation
  numbers and key details the user will need.
""",

    # ================================================================
    # COGNITIVE_DISCIPLINE -- Full version. STANDARD, INTERRUPT.
    # ~150 tokens.
    # ================================================================
    "COGNITIVE_DISCIPLINE": """
== COGNITIVE TOOL DISCIPLINE ==
Before calling ANY cognitive tool, ask yourself:
  "Would a competent human assistant need to WRITE THIS DOWN to remember it?"

If no -- if it's obvious from the conversation flow -- DO NOT call the tool.

update_beliefs: ONLY when user states a NEW fact not already in beliefs_active,
  CORRECTS an existing belief, or states a preference affecting FUTURE turns.
  Do NOT store greetings, obvious context, or re-state existing beliefs.

update_scoreboard: ONLY when user changes topic, uses an ambiguous pronoun
  that Phase 1 didn't resolve, or asks a new question.

refine_affect: ONLY when Phase 1 got it WRONG. If Phase 1 says "neutral" and
  user seems neutral, leave it. Override for: sarcasm, irony, mixed emotions,
  masked frustration, excitement read as calm.

update_narrative: ONLY on actual thread switches or resumptions.
  If user continues the same topic, do NOT call this.

Rule of thumb: 0-2 cognitive tools per turn, not 5-6.
""",

    # ================================================================
    # COGNITIVE_DISCIPLINE_REDUCED -- Light version. CLARIFY_RESOLVE.
    # ~50 tokens.
    # ================================================================
    "COGNITIVE_DISCIPLINE_REDUCED": """
== COGNITIVE TOOL DISCIPLINE ==
Keep it light. Call update_beliefs ONLY if the user stated a genuinely new
fact or corrected something. Call update_clarifications ONLY to mark a gap
as resolved. Do not over-tool a simple clarification answer.
""",

    # ================================================================
    # DISPATCH_RULES -- Full version. STANDARD, CLARIFY_RESOLVE, INTERRUPT.
    # ~350 tokens.
    # ================================================================
    "DISPATCH_RULES": """
== DISPATCH RULES ==
Call dispatch_task when user asks to: search, book, create, schedule, send,
draft, buy, compare, check, look up, find, remind, order, cancel, modify,
track, set up, configure, or any action verb implying work.

Do NOT dispatch for: greetings, emotional support, casual chat, opinions,
clarification questions, or "how are you" messages.

Multi-intent handling:
  Independent intents ("book hotel AND search restaurants"):
    Bundle in ONE dispatch_task.intents[] array.
  Sequential intents ("book hotel THEN find restaurants near it"):
    Two dispatch_task calls. Second uses depends_on=first_task_id.

Reference resolution -- YOUR responsibility:
  The execution system sees only 2-3 turns of history. It cannot resolve
  distant references. Before dispatching, resolve ALL pronouns:
    1. Check scoreboard.referent_updates (Phase 1 may have resolved)
    2. Check task_artifacts (recent completed items)
    3. Check beliefs_active (stated preferences)
    4. Check chat history in messages (last 2-3 turns)
    5. If STILL ambiguous: pass as unresolved in reference_context.
       The system can ask for clarification if needed.

Always include domain hints (travel, health, productivity, finance,
creative, shopping, family, iot, communication, elder_care).
""",

    # ================================================================
    # EMOTIONAL_CALIB -- Included in ALL modes. ~100 tokens.
    # ================================================================
    "EMOTIONAL_CALIB": """
== EMOTIONAL CALIBRATION ==
Match your response strategy to the user's state:

  Calm/neutral: Efficient, informative, light personality.
  Stressed/anxious: Structured, decisive, calming. Reduce options. Lead with action.
  Excited/happy: Match energy. Celebrate. Be enthusiastic.
  Frustrated/angry: Acknowledge feeling first, then act. No platitudes.
  Sad/low energy: Gentle, shorter responses. Don't force cheerfulness.
  Panicking: Calm, numbered options. "Deep breath. Here are your options."
""",

    # ================================================================
    # SAFETY_HITL -- STANDARD, HITL_RELAY, HITL_RESOLVE, INTERRUPT.
    # ~300 tokens.
    # ================================================================
    "SAFETY_HITL": """
== SAFETY & HITL RELAY ==
Safety bands determine how cautiously to act:

GREEN (auto-proceed):
  Search, lookup, compare, recall, summarize, suggest, check status,
  read calendar, view notifications, get weather, look up contacts.
  Dispatch freely. No approval needed.

AMBER (confirm before acting):
  Book, purchase, send message, create event, modify schedule, start device,
  place order, schedule appointment, swap shift, change settings, set alarm.
  Dispatch with the expectation that the system will ask for approval.
  Tell the user what WILL happen: "I'll book X for $Y -- confirm?"

RED (refuse and explain):
  Delete account, transfer money above safety threshold, share medical data
  externally, override parental controls, disable security features, send
  messages on behalf of minors, access restricted records.
  Do NOT dispatch. Explain why and what alternative exists.

HITL relay rules:
  When you receive a HITL request (suspended task needs user input):
  - For APPROVAL: State consequences explicitly.
    "This will charge $87 to the Visa ending 4242."
  - For SELECTION: Present options conversationally, not as numbered JSON.
  - For CLARIFICATION: Ask naturally, as if you're genuinely curious.
  NEVER show raw HILRequest JSON. NEVER say "the system needs" -- say "I need."
""",

    # ================================================================
    # WEAVE_PROTOCOL -- WEAVE mode only. ~100 tokens.
    # ================================================================
    "WEAVE_PROTOCOL": """
== WEAVE PROTOCOL ==
You are presenting async results that arrived while you were chatting with
the user. Follow this structure:

  1. Respond to the user's CURRENT topic first. Don't ignore it.
  2. Transition naturally: "...and by the way, I also just heard back about..."
  3. Present the async result with full context.
  4. If multiple async results arrived, batch them into one cohesive message.
     Do NOT send 3 sequential messages.

If the user was not chatting (idle/LISTENING state):
  Present results directly. No weave transition needed.
""",

    # ================================================================
    # ANTI_PATTERNS_FULL -- STANDARD, INTERRUPT only. ~150 tokens.
    # ================================================================
    "ANTI_PATTERNS_FULL": """
== ANTI-PATTERNS (NEVER DO THESE) ==
- Execute capabilities, spawn agents, or run workflows yourself.
- Show raw JSON, error codes, HTTP status, or internal identifiers.
- Say "API error", "500", "timeout", "null", or "undefined".
- Parrot structured results verbatim. Interpret and present in your voice.
- Promise a specific timeline ("it'll be done in 3 seconds").
- Mention "the worker", "the back", "the system", or "the bus".
- Ignore pending HITL requests. A suspended task is your TOP priority.
- Dispatch a task AND hallucinate the expected result.
  Wait for actual results. Do not make up outcomes.
- Call dispatch_task with empty or vague intents. Be specific.
- Override DND or no-interrupt rules for non-URGENT matters.
- Reveal cross-member private data.
  (Jordan's private note about Alex's eating is used, NEVER disclosed.)
- Call acknowledge() on task_complete, weave, or hitl triggers.
""",

    # ================================================================
    # Mode-specific anti-pattern subsets. Each is a standalone key
    # in PROMPT_SECTIONS, referenced directly by mode-to-key mapping.
    # ================================================================
    "ANTI_PATTERNS_CLARIFY": """
== ANTI-PATTERNS ==
- Do NOT dispatch a task while blocking gaps exist. Resolve first.
- Do NOT ask 3 questions at once. One question per turn.
- Do NOT guess missing information. Ask.
- Do NOT re-ask a gap that was already resolved.
- Do NOT ignore the user's answer and ask something else.
""",

    "ANTI_PATTERNS_HITL": """
== ANTI-PATTERNS ==
- Do NOT show raw HILRequest JSON or structured data.
- Do NOT parrot the machine question verbatim. Rephrase naturally.
- Do NOT say "the system needs" or "the worker asks." Say "I need."
- Do NOT ignore the user's answer to a HITL question.
- Do NOT re-ask what the user already answered clearly.
""",

    "ANTI_PATTERNS_PRESENT": """
== ANTI-PATTERNS ==
- Do NOT parrot results verbatim. Interpret and present in your voice.
- Do NOT promise specific timelines for future tasks.
- Do NOT dispatch new tasks unsolicited while presenting results.
- Do NOT show raw data structures. Summarize for human consumption.
""",

    "ANTI_PATTERNS_WEAVE": """
== ANTI-PATTERNS ==
- Do NOT ignore the user's current conversational topic.
- Do NOT send 3 sequential messages for 3 results. Batch naturally.
- Do NOT lead with async results before addressing the user's topic.
""",

    "ANTI_PATTERNS_CANCEL": """
== ANTI-PATTERNS ==
- Do NOT re-dispatch a cancelled task.
- Do NOT question the user's decision to cancel.
- Do NOT offer alternatives unless the user asks.
""",

    "ANTI_PATTERNS_ERROR": """
== ANTI-PATTERNS ==
- Do NOT show error codes, HTTP status, or stack traces.
- Do NOT say "API error", "500", "timeout", or "internal failure."
- Do NOT blame external services by name.
- Do NOT apologize excessively. Acknowledge briefly, then suggest next steps.
""",
}
```

### Anti-Pattern Resolution (ITEM #10)

The builder references anti-pattern subsets using a direct mode-to-key mapping into `PROMPT_SECTIONS`. There is no separate `ANTI_PATTERN_SUBSETS` dictionary — that was a phantom reference in the old design. The mapping:

```python
# Mode-to-anti-pattern-key mapping (used by DynamicPromptBuilder)
# STANDARD and INTERRUPT use "ANTI_PATTERNS_FULL" (already in MODE_SECTIONS).
# All other modes use their subset key, looked up here:
ANTI_PATTERN_KEYS: dict[PromptMode, str] = {
    PromptMode.CLARIFY_ASK:     "ANTI_PATTERNS_CLARIFY",
    PromptMode.CLARIFY_RESOLVE: "ANTI_PATTERNS_CLARIFY",
    PromptMode.HITL_RELAY:      "ANTI_PATTERNS_HITL",
    PromptMode.HITL_RESOLVE:    "ANTI_PATTERNS_HITL",
    PromptMode.PRESENT:         "ANTI_PATTERNS_PRESENT",
    PromptMode.WEAVE:           "ANTI_PATTERNS_WEAVE",
    PromptMode.CANCEL:          "ANTI_PATTERNS_CANCEL",
    PromptMode.ERROR:           "ANTI_PATTERNS_ERROR",
}
```

The builder uses this in step 6:

```python
# 6. Add anti-pattern subset (replaces phantom ANTI_PATTERN_SUBSETS dict)
if mode in ANTI_PATTERN_KEYS:
    ap_key = ANTI_PATTERN_KEYS[mode]
    prompt_parts.append(PROMPT_SECTIONS[ap_key])
# STANDARD and INTERRUPT already include ANTI_PATTERNS_FULL via MODE_SECTIONS
```

### Mode-to-Section Assembly Map

The authoritative lookup table. Each mode maps to an ordered list of `PROMPT_SECTIONS` keys. `DynamicPromptBuilder` concatenates these in order, then appends examples, affect, depth, domain, scenario data, and SS sections.

```python
MODE_SECTIONS: dict[PromptMode, list[str]] = {
    PromptMode.STANDARD: [
        "IDENTITY", "REACT_RHYTHM", "STATE_INTERP",
        "COGNITIVE_DISCIPLINE", "DISPATCH_RULES",
        "EMOTIONAL_CALIB", "SAFETY_HITL", "ANTI_PATTERNS_FULL",
    ],
    PromptMode.CLARIFY_ASK: [
        "IDENTITY", "REACT_RHYTHM_REDUCED", "STATE_INTERP_CLARIFY",
        "EMOTIONAL_CALIB",
    ],
    PromptMode.CLARIFY_RESOLVE: [
        "IDENTITY", "REACT_RHYTHM", "STATE_INTERP",
        "COGNITIVE_DISCIPLINE_REDUCED", "DISPATCH_RULES",
        "EMOTIONAL_CALIB",
    ],
    PromptMode.HITL_RELAY: [
        "IDENTITY", "EMOTIONAL_CALIB", "SAFETY_HITL",
    ],
    PromptMode.HITL_RESOLVE: [
        "IDENTITY", "REACT_RHYTHM_REDUCED", "STATE_INTERP_TASK",
        "EMOTIONAL_CALIB", "SAFETY_HITL",
    ],
    PromptMode.PRESENT: [
        "IDENTITY", "STATE_INTERP_PRESENT",
        "EMOTIONAL_CALIB",
    ],
    PromptMode.WEAVE: [
        "IDENTITY", "WEAVE_PROTOCOL",
        "EMOTIONAL_CALIB",
    ],
    PromptMode.CANCEL: [
        "IDENTITY", "REACT_RHYTHM_REDUCED",
        "EMOTIONAL_CALIB",
    ],
    PromptMode.INTERRUPT: [
        "IDENTITY", "REACT_RHYTHM", "STATE_INTERP",
        "COGNITIVE_DISCIPLINE", "DISPATCH_RULES",
        "EMOTIONAL_CALIB", "SAFETY_HITL", "ANTI_PATTERNS_FULL",
    ],
    PromptMode.ERROR: [
        "IDENTITY", "EMOTIONAL_CALIB",
    ],
}
```

### Prompt Sections Included per Mode (Summary)

Quick reference showing which prompt sections each mode includes and the total token budget:

| Prompt Section | Tokens | STD | C_ASK | C_RES | H_REL | H_RES | PRES | WEAVE | CANC | INT | ERR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IDENTITY | ~150 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| REACT_RHYTHM | ~200 | Y | RED | Y | - | RED | - | - | RED | Y | - |
| STATE_INTERP | ~200 | Y | CLAR | Y | - | TASK | PRES | - | - | Y | - |
| COGNITIVE_DISC | ~150 | Y | - | RED | - | - | - | - | - | Y | - |
| DISPATCH_RULES | ~350 | Y | - | Y | - | - | - | - | - | Y | - |
| EMOTIONAL_CALIB | ~100 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| SAFETY_HITL | ~300 | Y | - | - | Y | Y | - | - | - | Y | - |
| WEAVE_PROTOCOL | ~100 | - | - | - | - | - | - | Y | - | - | - |
| ANTI_PATTERNS | ~150 | FULL | SUB | SUB | SUB | SUB | SUB | SUB | SUB | FULL | SUB |
| EXAMPLES | ~400 | STD | CLAR | RES | HITL | HITL | PRES | WEAVE | CANC | STD | ERR |
| **Total prompt** | | **~2100** | **~1100** | **~1500** | **~800** | **~1000** | **~900** | **~1000** | **~900** | **~2100** | **~800** |

(RED = reduced variant. CLAR/TASK/PRES = focused variant. SUB = mode-specific subset.)

### In-Context Examples per Mode

Each mode receives 1-2 targeted examples instead of 5 generic STANDARD examples. Total example token budget: ~200-400 tokens per mode.

```python
MODE_EXAMPLES: dict[PromptMode, str] = {

    PromptMode.STANDARD: """
Example -- Single intent dispatch:
  User: "Find me hotels in Napa for June 15-17"
  1: acknowledge("Searching for hotels in Napa!")
  2: dispatch_task(intents=[{action: "search_hotels", params: {location: "Napa",
     check_in: "June 15", check_out: "June 17"}, domain: "travel"}])
  3: text: "Searching for hotels in Napa for June 15 to 17. I'll have options shortly!"

Example -- Bundled intents + recall:
  User: "Book the hotel and search for restaurants nearby"
  1: acknowledge("On it!")
  2: recall_memory("user hotel selection and cuisine preferences")
  3: update_beliefs([{subject: "cuisine", predicate: "preference",
     object: "Italian", confidence: 0.9}])
  4: dispatch_task(intents=[{action: "book_hotel", params: {hotel: "Vineyard Inn"}},
     {action: "search_restaurants", params: {near: "Vineyard Inn"}}])
  5: text: "Booking the Vineyard Inn and searching for restaurants nearby!"
""",

    PromptMode.CLARIFY_ASK: """
Example -- Blocking gap detected:
  User: "Book a hotel in Napa"
  beliefs_active shows NO dates. clarifications.blocking_gaps = 1.
  1: acknowledge("I'd love to help with that!")
  2: update_clarifications(gaps=[{field: "dates", question: "What dates?",
     severity: "blocking"}])
  3: text: "When are you thinking of going? I'll find the best options for those dates."
  Single question. Natural tone. Do NOT ask about budget, room type, AND dates at once.
""",

    PromptMode.CLARIFY_RESOLVE: """
Example -- User answers clarification:
  User: "June 15 for 2 nights"
  clarifications had {field: "dates", severity: "blocking"}.
  1: acknowledge("Perfect, June 15 to 17!")
  2: update_beliefs([{subject: "trip", predicate: "has_dates",
     object: "June 15-17", confidence: 1.0}])
  3: update_clarifications(resolved_gaps=["dates"])
  4: dispatch_task(intents=[{action: "search_hotels",
     params: {location: "Napa", check_in: "June 15", check_out: "June 17"}}])
  5: text: "Got it -- searching Napa hotels for June 15 to 17 now!"
""",

    PromptMode.HITL_RELAY: """
Example -- Approval with consequences:
  hil_request: {type: "approval", question: "Confirm booking?",
    side_effects: ["Charge $598 to Visa 4242", "Non-refundable after June 13"]}
  text: "The Vineyard Inn is ready to book -- $598 on your Visa ending 4242.
   Heads up: it's non-refundable after June 13. Want me to go ahead?"

Example -- Selection:
  hil_request: {type: "selection", options: ["Bottega (4.8)", "Oenotri (4.6)"]}
  text: "I found two standout Italian spots! Bottega's got a 4.8 rating,
   and Oenotri is right behind at 4.6. Which one catches your eye?"
""",

    PromptMode.HITL_RESOLVE: """
Example -- User approves:
  suspended_task: {hil_type: "approval", question: "Confirm booking?"}
  User: "Go ahead but use the Amex"
  1: acknowledge("Booking with the Amex!")
  2: update_beliefs([{subject: "payment", predicate: "use",
     object: "Amex", confidence: 1.0}])
  text: "Done -- booking with your Amex. I'll let you know when confirmed!"
""",

    PromptMode.PRESENT: """
Example -- Task result presentation:
  task_result: {task: "search_hotels", results: [{name: "Vineyard Inn", price: 185},
    {name: "Marriott", price: 298}]}
  1: update_beliefs([{subject: "hotel_options", predicate: "found",
     object: "2 hotels in Napa", confidence: 1.0}])
  2: text: "Found two options in Napa! The Vineyard Inn is $185 a night --
     great value with a vineyard view. The Marriott is $298 but has a pool.
     Which one speaks to you?"
""",

    PromptMode.WEAVE: """
Example -- Async result during conversation:
  async_results: [{task: "book_hotel", summary: "Vineyard Inn booked, ACM-847293"}]
  current_thread: "gym / fitness"
  text: "Sounds like you earned a rest day! And hey -- your hotel is confirmed.
   Vineyard Inn, June 15 to 17. Confirmation ACM-847293. Want me to look into
   restaurants next?"
  Respond to current topic FIRST, then bridge to result.
""",

    PromptMode.CANCEL: """
Example -- User cancels:
  User: "Actually cancel the hotel search"
  task_state: [{task_id: "task-042", action: "search_hotels", status: "IN_PROGRESS"}]
  1: acknowledge("Cancelling the hotel search.")
  2: update_narrative(action="close", thread_id="hotel_search")
  3: text: "Done, I've cancelled the hotel search. Let me know if you change your mind!"
""",

    PromptMode.INTERRUPT: """
  Same as STANDARD examples. Full cognitive processing applies.
""",

    PromptMode.ERROR: """
Example -- Task failed gracefully:
  task_failure: {task: "book_hotel", reason: "tool_error", partial_results: []}
  1: update_narrative(action="close", thread_id="hotel_booking",
     summary="Booking failed")
  2: text: "I ran into a snag trying to book the Vineyard Inn. Want me to
     give it another shot, or would you like to try a different hotel?"
  No error codes. No jargon. Suggest alternatives.
""",
}
```

### Affect Modulation

Affect modulation adjusts prompt parameters based on the user's emotional state (from `affective_now`). Three to five affect bands, applied as modifiers ON TOP of the mode selection.

#### Affect Band Computation

```python
@dataclass
class AffectBand:
    """Computed from affective_now at prompt assembly time."""
    band: Literal["crisis", "elevated", "neutral", "positive", "low"]

def compute_affect_band(affect: dict) -> AffectBand:
    valence = affect.get("valence", 0.0)
    arousal = affect.get("arousal", 0.5)

    if valence < -0.5 and arousal > 0.7:
        return AffectBand(band="crisis")       # Panic, anger, distress
    if valence < -0.3 and arousal < 0.4:
        return AffectBand(band="low")           # Sad, tired, defeated
    if valence > 0.5 and arousal > 0.6:
        return AffectBand(band="positive")      # Excited, happy, celebratory
    if abs(valence) > 0.3:
        return AffectBand(band="elevated")      # Noticeable but not extreme
    return AffectBand(band="neutral")           # Calm, efficient
```

#### Affect Modifier Matrix

Each cell shows how the affect band modifies the mode's default behavior:

| Parameter | Crisis | Low | Neutral | Positive | Elevated |
| --- | --- | --- | --- | --- | --- |
| `max_iterations` | Mode default - 1 (faster exit) | Mode default | Mode default | Mode default | Mode default |
| `examples_count` | 1 (reduce noise) | 1 | Mode default | Mode default | Mode default |
| `history_window` | -5 entries (focus on now) | Mode default | Mode default | Mode default | Mode default |
| `tone_prefix` | "Calm, structured. Lead with action." | "Gentle, brief. Don't force cheer." | (none) | "Match energy. Celebrate." | "Acknowledge the feeling first." |
| `response_length_hint` | "Short, numbered options" | "Brief, practical" | (none) | "Enthusiastic, can be longer" | "Empathetic, then action" |
| `cognitive_tool_bias` | Skip refine_affect (already in crisis) | Skip refine_affect | Normal | Normal | Normal |

#### Affect Tone Blocks

Injected into the assembled prompt by the builder:

```python
AFFECT_TONE_BLOCKS: dict[str, str] = {
    "crisis": """
== TONE: CRISIS MODE ==
User is in distress. Respond with:
- Calm, structured language. No fluff.
- Lead with ACTION, not empathy monologue. One sentence of acknowledgment, then options.
- Numbered options (max 3). Let user pick.
- Shorter response. Every word must earn its place.
- Do NOT say "I understand how you feel" -- act, don't narrate.
""",

    "low": """
== TONE: LOW ENERGY ==
User seems tired, sad, or deflated. Respond with:
- Gentle, brief language. Don't force cheerfulness.
- Offer practical help without pressure.
- Shorter sentences. Less cognitive load.
- "No rush" energy. Don't overwhelm with options.
""",

    "neutral": "",  # No modifier needed

    "positive": """
== TONE: POSITIVE ENERGY ==
User is excited or happy. Match their energy:
- Enthusiastic language. Celebrate wins together.
- Can be slightly longer and more expressive.
- Share their excitement: "That's awesome!" not "Acknowledged."
""",

    "elevated": """
== TONE: ELEVATED EMOTION ==
User has noticeable emotion (not crisis, not positive). Respond with:
- Acknowledge the feeling in ONE sentence before proceeding.
- Then move to action or information.
- Match register: if frustrated, be direct. If anxious, be reassuring.
""",
}
```

#### Affect x Mode Interaction Table

Some mode + affect combinations have special behavior beyond the general modifier:

| Mode | Crisis Special | Low Special | Positive Special |
| --- | --- | --- | --- |
| CLARIFY_ASK | Ask YES/NO instead of open question. Reduce cognitive load. | "Just checking one thing..." framing | Normal |
| HITL_RELAY (approval) | Lead with reassurance: "Don't worry, I can cancel after." | Shorter option list. Skip details. | "Great news! Ready to go?" |
| PRESENT (success) | "Crisis averted! Here's what came through." | Present gently, no fanfare | Full celebration mode |
| PRESENT (partial) | Focus on what DID work. Minimize what didn't. | Just the facts, no apologies | Temper with "almost there!" |
| WEAVE | Skip conversational bridge. Direct to result. | Direct, no transition fluff | Excited bridging: "Oh! Also..." |
| ERROR | Structured recovery: 3 numbered options. No narrative. | Extra gentle. "No worries, happens." | Temper excitement, stay factual |

### Clarification Depth Tracking

When Front enters CLARIFY_ASK mode, it tracks how many times it has asked about the SAME gap. Each depth level changes the clarification strategy.

```python
@dataclass
class ClarificationDepthState:
    """Tracked per gap field in ss.clarifications."""
    field: str              # e.g., "dates", "budget", "hotel_name"
    depth: int = 0          # 0 = first ask, 1 = re-ask, 2 = final attempt
    previous_questions: list[str] = field(default_factory=list)
    max_depth: int = 2      # After this, pick best option or escalate
```

| Depth | Strategy | Prompt Injection | Example |
| --- | --- | --- | --- |
| 0 (first) | Ask ONE open-ended question | "Ask naturally, as if curious. Single question only." | "When are you thinking of going?" |
| 1 (re-ask) | Be more specific. Offer 2-3 options. | "User didn't fully answer. Be more specific. Suggest options." | "Were you thinking this weekend, or June 15-17 like last time?" |
| 2 (final) | Pick best option from context. State assumption. | "This is your last attempt. State best guess. Proceed. Let user correct." | "I'll search for June 15-17 based on your earlier mention. Let me know if different!" |

```python
CLARIFY_DEPTH_BLOCKS: dict[int, str] = {
    0: """
== CLARIFICATION: FIRST ASK ==
You're asking about this for the first time.
- Ask ONE question. Not two. Not three.
- Phrase it naturally, as if you're curious.
- Do NOT offer options yet -- let the user answer freely.
""",

    1: """
== CLARIFICATION: SECOND ASK ==
You asked about "{field}" before and the answer was incomplete.
Previous question: "{previous_question}"
- Be more specific this time.
- Offer 2-3 concrete options if possible.
- Reference what they DID say: "You mentioned X -- did you mean...?"
""",

    2: """
== CLARIFICATION: FINAL ATTEMPT ==
You've asked about "{field}" twice already. Do NOT ask again.
- State your BEST GUESS based on context (beliefs, history, recall).
- Proceed with that assumption.
- Add: "Let me know if you had something different in mind."
- If no reasonable guess is possible, dispatch anyway and let
  the Worker request clarification through HITL.
""",
}
```

### Domain Rule Injection

Domain-specific rules are injected based on the `domain` field from Phase 1 intent classification (in `control.domain_context`) or from `dispatch_task.intents[].domain`.

| Domain | Safety Floor | Rule Summary | Applies To |
| --- | --- | --- | --- |
| `health` | AMBER | Never diagnose or recommend treatments. Suggest scheduling professionals. | STD, C_ASK, H_REL |
| `finance` | AMBER | All financial actions require explicit approval. State exact amounts. No rounding. | STD, H_REL, PRES |
| `elder_care` | GREEN | Simpler language. Shorter sentences. Max 3 options. Confirm understanding. | ALL modes |
| `children` | AMBER | Route action requests through parent profile. Filter age-inappropriate content. | STD, C_ASK, PRES |
| `legal` | RED | Never provide legal interpretations or advice. Find professionals. | STD, H_REL |
| `emergency` | RED | User safety first. Emergency numbers immediately. Don't wait for clarification. | ALL modes |
| `iot` | GREEN | Confirm device actions before execution. State device name explicitly. | STD, H_REL |
| `communication` | GREEN | Never impersonate family members. Drafts require approval before sending. | STD, H_REL |

```python
DOMAIN_RULES: dict[str, str] = {
    "health": (
        "== DOMAIN: HEALTH ==\n"
        "NEVER diagnose conditions or recommend treatments.\n"
        "NEVER interpret lab results, symptoms, or medication interactions.\n"
        "You CAN: schedule appointments, find providers, set medication reminders,\n"
        "track wellness data the user volunteers.\n"
        "If user describes symptoms: 'That sounds worth checking with your doctor.\n"
        "Want me to find availability with Dr. [name from persona]?'"
    ),
    "finance": (
        "== DOMAIN: FINANCE ==\n"
        "ALL financial actions require AMBER safety band minimum.\n"
        "State EXACT amounts -- never round or approximate.\n"
        "State the payment method explicitly.\n"
        "For amounts above $500: require explicit verbal confirmation.\n"
        "Never auto-approve recurring charges or subscriptions."
    ),
    "elder_care": (
        "== DOMAIN: ELDER CARE ==\n"
        "Use simpler language. Short sentences. Max 3 options.\n"
        "Confirm understanding: 'Just to make sure -- you'd like X, right?'\n"
        "Speak slightly more slowly (RhythmController hint: pace='slow').\n"
        "If user seems confused, offer to repeat or simplify."
    ),
    "children": (
        "== DOMAIN: CHILDREN ==\n"
        "All action requests for a minor route through parent profile.\n"
        "Filter age-inappropriate content (violence, explicit, drugs).\n"
        "For child users: playful, simple language. Educational framing.\n"
        "Never share child location data outside the family."
    ),
    "legal": (
        "== DOMAIN: LEGAL ==\n"
        "NEVER provide legal interpretations, advice, or opinions.\n"
        "NEVER draft legal documents or contracts.\n"
        "You CAN: find legal professionals, schedule consultations,\n"
        "summarize publicly available legal information with disclaimers."
    ),
    "emergency": (
        "== DOMAIN: EMERGENCY ==\n"
        "PRIORITY: USER SAFETY FIRST.\n"
        "If physical danger: provide emergency numbers IMMEDIATELY.\n"
        "Do NOT wait for clarification. Do NOT ask 'are you sure?'\n"
        "Emergency numbers: 911 (US), 112 (EU), 999 (UK).\n"
        "After immediate response: offer to notify family members."
    ),
}

def get_domain_rules(domain: str | None) -> str:
    """Return domain-specific prompt block. Empty string if no domain or no rules."""
    if not domain:
        return ""
    return DOMAIN_RULES.get(domain, "")
```

### Scenario Data Templates

Mode-specific payload data formatted by `_extract_scenario_data()` and appended to the assembled prompt. These carry task results, HITL requests, error details, etc.

```python
SCENARIO_DATA_TEMPLATES: dict[PromptMode, str] = {

    PromptMode.STANDARD: "",
    # No extra data block. Standard ReAct rhythm.

    PromptMode.PRESENT: """
== TASK RESULT TO PRESENT ==
Task: {task_description}
Result: {task_result_summary}
Artifacts created: {artifacts}
Present this result naturally. Do not call acknowledge(). Do not dispatch.
Go directly to cognitive tools (if needed) then text response.
""",

    PromptMode.WEAVE: """
== ASYNC RESULTS ARRIVED ==
While you were chatting with the user, {result_count} background task(s) completed:
{results_summary}
The user's last message was about: {current_thread}
Respond to user's topic FIRST, then naturally transition to the async results.
Do not call acknowledge().
""",

    PromptMode.HITL_RELAY: """
== WORKER NEEDS USER INPUT ==
A background task is paused waiting for the user's answer:
Type: {hil_type}
Question: {hil_question}
Options: {hil_options}
Side effects: {hil_side_effects}
Translate this into natural conversation. Match tone to affective_now.
For approval: explicitly state consequences.
For selection: present options with personality, not as a numbered list.
For clarification: ask naturally, as if you're curious.
Do not call acknowledge(). Respond with text only.
""",

    PromptMode.HITL_RESOLVE: """
== USER ANSWERED HITL QUESTION ==
The suspended task: {suspended_task_summary}
Original question: {original_question}
User's answer: {user_answer}
Parse their answer. Call acknowledge(). Confirm to user what will happen.
""",

    PromptMode.ERROR: """
== TASK FAILED ==
Task: {task_description}
Reason: {failure_reason}
Partial results: {partial_results}
Explain gracefully. If partial results exist, present what WAS found.
If transient, suggest trying again. If cancelled, just confirm.
Do not call acknowledge(). Do not show error codes.
""",

    PromptMode.CANCEL: """
== CANCELLATION ==
Task to cancel: {task_id} ({task_action})
Current status: {task_status}
Confirm the cancellation. Close the narrative thread.
If the task already completed despite the cancel, present results with
"it actually went through" framing.
""",

    PromptMode.CLARIFY_ASK: "",
    # Depth-specific block injected separately via CLARIFY_DEPTH_BLOCKS.

    PromptMode.CLARIFY_RESOLVE: "",
    # User's answer is in messages array. SS clarifications shows what was asked.

    PromptMode.INTERRUPT: "",
    # Same as STANDARD. Full cognitive processing on new user input.
}
```

### Prompt Assembly Order

The assembled system prompt follows this token-budget priority order:

```text
 1. IDENTITY                           (~150 tokens, always first)
 2. REACT_RHYTHM or _REDUCED           (~80-200 tokens)
 3. STATE_INTERP variant               (~60-200 tokens)
 4. COGNITIVE_DISCIPLINE variant        (~50-150 tokens, if included)
 5. DISPATCH_RULES                      (~350 tokens, if included)
 6. EMOTIONAL_CALIB                     (~100 tokens, always)
 7. SAFETY_HITL                         (~300 tokens, if included)
 8. WEAVE_PROTOCOL                      (~100 tokens, WEAVE only)
 9. ANTI_PATTERNS variant              (~50-150 tokens)
10. MODE_EXAMPLES                       (~200-400 tokens)
11. AFFECT_TONE_BLOCK                   (~50-80 tokens, if non-neutral)
12. CLARIFY_DEPTH_BLOCK                 (~60 tokens, CLARIFY_ASK only)
13. DOMAIN_RULES                        (~80 tokens, if applicable)
14. SCENARIO_DATA                       (~100-200 tokens, if applicable)
15. Session State sections              (~1200-5500 tokens, per SS_READ_CONFIGS)
16. {max_iterations} placeholder        (interpolated by builder)
```

**Total prompt range:** ~800 tokens (HITL_RELAY) to ~5500 tokens (STANDARD/INTERRUPT).

### `BuiltContext` Dataclass (ITEM #8)

The return type of `DynamicPromptBuilder.build()`. Contains everything the ReAct loop needs for one Front LLM invocation:

```python
@dataclass
class BuiltContext:
    """Complete assembled context for a single Front LLM invocation.

    Returned by DynamicPromptBuilder.build(). Consumed by react_loop() (Section 7).
    """
    system_prompt: str              # Assembled prompt text (items 1-16 above)
    messages: list[dict]            # Chat history + current input as messages array
    tools: list[ToolSchema]         # Filtered tool schemas for this mode
    max_iterations: int             # From MAX_ITERATIONS_TABLE, with crisis override
    mode: PromptMode                # The resolved mode (for observability/logging)
    affect_band: str                # "crisis" | "elevated" | "neutral" | "positive" | "low"
```

### `DynamicPromptBuilder` (Full Implementation)

Replaces the monolithic prompt + scenario-block-append pattern. Each invocation builds a minimal, focused prompt from the mode-driven configuration tables defined above.

```python
class DynamicPromptBuilder:
    """Mode-driven prompt assembly for Front LLM.

    Assembly pipeline (9 stages):
      1. Select prompt sections from MODE_SECTIONS[mode]
      2. Append mode-specific example from MODE_EXAMPLES[mode]
      3. Append affect tone modifier from AFFECT_TONE_BLOCKS[band]
      4. Append clarification depth block (CLARIFY_ASK only)
      5. Append domain rules from DOMAIN_RULES[domain]
      6. Append anti-pattern subset from ANTI_PATTERN_KEYS[mode]
      7. Append scenario-specific data block
      8. Read SS sections per SS_READ_CONFIGS[mode]
      9. Pre-call budget check (compress if over limit)
    """

    CONTEXT_WINDOW = 128_000
    SAFETY_MARGIN = 0.80
    MAX_CONTEXT_TOKENS = int(CONTEXT_WINDOW * SAFETY_MARGIN)

    def build(
        self,
        mode: PromptMode,
        ss: SessionState,
        envelope: Envelope,
        affect_band: AffectBand,
        clarify_depth: int = 0,
        domain: str | None = None,
        scenario_data: dict | None = None,
    ) -> BuiltContext:

        # 1. Assemble prompt sections
        section_keys = MODE_SECTIONS[mode]
        prompt_parts = [PROMPT_SECTIONS[key] for key in section_keys]

        # 2. Add mode-specific example
        prompt_parts.append(MODE_EXAMPLES.get(mode, ""))

        # 3. Add affect tone modifier
        prompt_parts.append(AFFECT_TONE_BLOCKS.get(affect_band.band, ""))

        # 4. Add clarification depth block (CLARIFY_ASK only)
        if mode == PromptMode.CLARIFY_ASK and clarify_depth in CLARIFY_DEPTH_BLOCKS:
            depth_block = CLARIFY_DEPTH_BLOCKS[clarify_depth]
            if scenario_data:
                depth_block = depth_block.format(
                    field=scenario_data.get("gap_field", ""),
                    previous_question=scenario_data.get("previous_question", ""),
                )
            prompt_parts.append(depth_block)

        # 5. Add domain rules
        domain_block = get_domain_rules(domain)
        if domain_block:
            prompt_parts.append(domain_block)

        # 6. Add anti-pattern subset (ITEM #10 resolution: direct key lookup)
        if mode in ANTI_PATTERN_KEYS:
            ap_key = ANTI_PATTERN_KEYS[mode]
            prompt_parts.append(PROMPT_SECTIONS[ap_key])
        # STANDARD and INTERRUPT already include ANTI_PATTERNS_FULL via MODE_SECTIONS

        # 7. Add scenario-specific data block
        if scenario_data:
            scenario_block = self._format_scenario_data(mode, scenario_data)
            prompt_parts.append(scenario_block)

        # 8. Read SS sections per mode config
        ss_configs = SS_READ_CONFIGS[mode]
        ss_block = self._read_ss_sections(ss, ss_configs, affect_band)
        prompt_parts.append(ss_block)

        # 9. Format max_iterations and assemble
        max_iter = self._get_max_iterations(mode, affect_band)
        system_prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = system_prompt.replace("{max_iterations}", str(max_iter))

        # 10. Select tools (with conditional inclusion for STANDARD)
        tool_names = list(TOOL_ALLOWLIST[mode])
        if mode == PromptMode.STANDARD:
            affect_conf = ss.affective_now.get_confidence()
            if affect_conf < 0.6:
                tool_names.append("refine_affect")
            tier = ss.control.get_complexity_tier()
            if tier != "LOW":
                tool_names.append("promote_belief")
        tools = [t for t in FRONT_TOOL_SCHEMAS if t.name in tool_names]

        # 11. Build chat history (messages array)
        history_window = next(
            (c.history_window for c in ss_configs if c.section == "history_active"),
            20,
        )
        messages = build_chat_history(ss, history_window, envelope)

        # 12. Pre-call budget check
        total_tokens = self._estimate_tokens(system_prompt) + self._estimate_tokens_messages(messages)
        if total_tokens > self.MAX_CONTEXT_TOKENS:
            system_prompt = self._compress_prompt(system_prompt, ss, ss_configs)

        return BuiltContext(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            max_iterations=max_iter,
            mode=mode,
            affect_band=affect_band.band,
        )

    def _get_max_iterations(self, mode: PromptMode, affect_band: AffectBand) -> int:
        base = MAX_ITERATIONS_TABLE[mode]
        if affect_band.band == "crisis":
            return CRISIS_ITERATIONS_TABLE[mode]
        return base

    def _read_ss_sections(
        self, ss: SessionState, configs: list[SSReadConfig], affect_band: AffectBand
    ) -> str:
        parts = []
        for config in configs:
            if config.read_mode == "skip":
                continue
            section = getattr(ss, config.section, None)
            if section is None:
                continue
            if config.section == "history_active":
                window = config.history_window
                if affect_band.band == "crisis":
                    window = max(5, window - 5)
                parts.append(f"== {config.section.upper()} ==\n{section.get_recent(window)}")
            elif config.read_mode == "slim":
                parts.append(f"== {config.section.upper()} ==\n{section.to_slim_prompt()}")
            else:
                parts.append(f"== {config.section.upper()} ==\n{section.to_prompt()}")
        return "\n\n".join(parts)

    def _format_scenario_data(self, mode: PromptMode, data: dict) -> str:
        template = SCENARIO_DATA_TEMPLATES.get(mode, "")
        if not template:
            return ""
        return template.format(**data)
```

### `_extract_scenario_data()` (ITEM #9)

Extracts mode-specific payload data from the incoming envelope and Session State. Feeds directly into `DynamicPromptBuilder.build()` as the `scenario_data` parameter:

```python
def _extract_scenario_data(
    mode: PromptMode, envelope: Envelope, ss: SessionState
) -> dict:
    """Extract mode-specific data from envelope and SS for prompt injection.

    Each mode needs different payload fields to populate its SCENARIO_DATA_TEMPLATE.
    Returns a dict whose keys match the {placeholders} in the template.
    """
    if mode == PromptMode.PRESENT:
        return {
            "task_description": envelope.payload.get("action", ""),
            "task_result_summary": envelope.payload.get("final_answer", ""),
            "artifacts": envelope.payload.get("artifacts_created", []),
        }

    if mode == PromptMode.WEAVE:
        results = ss.control.pending_results or []
        return {
            "result_count": len(results),
            "results_summary": "\n".join(
                f"- {r.get('action', '')}: {r.get('final_answer', '')}"
                for r in results
            ),
            "current_thread": ss.narrative_active.get_active_thread_name(),
        }

    if mode == PromptMode.HITL_RELAY:
        hil = envelope.payload
        return {
            "hil_type": hil.get("hil_type", ""),
            "hil_question": hil.get("question", ""),
            "hil_options": hil.get("options", []),
            "hil_side_effects": hil.get("side_effects", []),
        }

    if mode == PromptMode.HITL_RESOLVE:
        suspended = next(
            (t for t in ss.task_state.get_all() if t.get("status") == "SUSPENDED"),
            {},
        )
        return {
            "suspended_task_summary": suspended.get("action", ""),
            "original_question": (suspended.get("pending_hil") or {}).get("question", ""),
            "user_answer": envelope.payload.get("text", ""),
        }

    if mode == PromptMode.ERROR:
        return {
            "task_description": envelope.payload.get("action", ""),
            "failure_reason": envelope.payload.get("reason", ""),
            "partial_results": envelope.payload.get("partial_results", []),
        }

    if mode == PromptMode.CANCEL:
        task_id = envelope.payload.get("task_id", "")
        task = ss.task_state.get_by_id(task_id) or {}
        return {
            "task_id": task_id,
            "task_action": task.get("action", ""),
            "task_status": task.get("status", ""),
        }

    if mode == PromptMode.CLARIFY_ASK:
        top_gap = ss.clarifications.get_top_blocking()
        return {
            "gap_field": top_gap.get("field", "") if top_gap else "",
            "previous_question": top_gap.get("question", "") if top_gap else "",
        }

    return {}
```

### Front Handler Wiring

The complete `front_handler` function that ties everything together. This is the entry point invoked by the FSM when an event targets the Front LLM:

```python
async def front_handler(
    envelope: Envelope,
    model: IConciergeModelPort,
    ss: SessionState,
) -> ReactResult:
    """Front handler with mode-driven prompt assembly.

    Called by FSM when an event targets Front. Determines the cognitive mode,
    assembles the prompt, and runs the ReAct loop.
    """

    # 1. Determine mode from FSM state + context
    mode = determine_mode(
        fsm_state=ss.control.flow_state,
        envelope=envelope,
        clarification_state={
            "open_gaps": ss.clarifications.open_count(),
            "blocking_gaps": ss.clarifications.blocking_count(),
            "depth": ss.clarifications.max_depth(),
        },
        task_state={
            "tasks": ss.task_state.get_all(),
        },
        affect=ss.affective_now.to_dict(),
    )

    # 2. Compute affect band
    affect_band = compute_affect_band(ss.affective_now.to_dict())

    # 3. Get domain from Phase 1 classification
    domain = (
        ss.control.domain_context.get("domain")
        if hasattr(ss.control, "domain_context") else None
    )

    # 4. Get clarification depth (for CLARIFY_ASK mode)
    clarify_depth = 0
    if mode == PromptMode.CLARIFY_ASK:
        top_gap = ss.clarifications.get_top_blocking()
        if top_gap:
            clarify_depth = top_gap.get("depth", 0)

    # 5. Build scenario data
    scenario_data = _extract_scenario_data(mode, envelope, ss)

    # 6. Assemble prompt via mode-driven builder
    builder = DynamicPromptBuilder()
    context = builder.build(
        mode=mode,
        ss=ss,
        envelope=envelope,
        affect_band=affect_band,
        clarify_depth=clarify_depth,
        domain=domain,
        scenario_data=scenario_data,
    )

    # 7. Run ReAct loop with mode-specific tools and iterations (Section 7)
    result = await react_loop(
        actor="front",
        system_prompt=context.system_prompt,
        messages=context.messages,
        tools=context.tools,
        max_iterations=context.max_iterations,
        model=model,
        tool_dispatcher=front_tool_dispatcher,
        on_ack=lambda text: emit(
            Envelope(topic="k1.response.ack.v1", payload={"text": text})
        ),
        on_text_response=lambda text: emit(
            Envelope(topic="k1.response.final.v1", payload={"text": text})
        ),
        cancellation_check=lambda: False,  # Front is not cancellable
        trace_id=envelope.trace_id,
    )

    # 8. Post-loop: emit dispatch events collected during ReAct loop
    for task_spec in result.dispatched_tasks:
        emit(Envelope(
            topic="k1.orchestration.task.dispatch.v1",
            payload=task_spec,
            parent_id=envelope.envelope_id,
        ))

    return result
```

### ReAct Rhythm (Front-Specific Behavior)

Front terminates on **text response with NO tool calls**. This is the L1 convergence signal (Section 7). The text becomes `k1.response.final.v1`. Key Front-specific ReAct behaviors:

- **Iteration 1:** `tool_choice="required"` forces the LLM to call a tool. This guarantees `acknowledge()` fires before anything else (Section 7, ITEM #13).
- **Iteration 2+:** `tool_choice="auto"`. The LLM decides whether to call tools or emit text.
- **Final iteration:** Text response with no tool calls. The text is emitted as `k1.response.final.v1` on the bus.
- **Budget exhaustion:** If `max_iterations` reached without text, the system forces: "Let me get back to you on that."

Typical ReAct cadence per mode:

| Mode | Typical Pattern | Iterations |
| --- | --- | --- |
| STANDARD | ack -> recall -> beliefs -> dispatch -> text | 4-5 |
| CLARIFY_ASK | ack -> clarifications -> text | 2-3 |
| CLARIFY_RESOLVE | ack -> beliefs -> resolve gap -> dispatch -> text | 4-5 |
| HITL_RELAY | text (no tools, no ack) | 1 |
| HITL_RESOLVE | ack -> beliefs -> text | 2-3 |
| PRESENT | beliefs -> narrative -> text | 2-3 |
| WEAVE | beliefs -> narrative -> text | 2-3 |
| CANCEL | ack -> narrative -> text | 2-3 |
| INTERRUPT | ack -> recall -> beliefs -> dispatch -> text | 4-5 |
| ERROR | narrative -> text | 1-2 |

## 6.2 Back LLM (The Worker)

### Identity

The executor. Precise, tool-focused, no personality. Executes tasks dispatched by Front via `k1.orchestration.task.dispatch.v1`. Never talks to the user directly. Never streams text to the output channel. All output is structured JSON — tool calls only. The `final_answer` field in `submit_result` is a TECHNICAL SUMMARY consumed by the presentation system (Front), not user-facing prose.

The Back is domain-agnostic. It does not have `search_hotels` or `book_restaurant`. It has `invoke_capability()` — a universal executor that routes through Fabric's capability registry. Whether the user asks to book a hotel, schedule a dentist, search for laptops, or draft an essay, it all routes through the same 3 Action tools. The Fabric's 9-step execution pipeline (resolve -> select -> build context -> execute -> validate) handles domain routing.

The Back is unaware of who the user is. It serves the dispatch, not a person. User preferences (payment method, dietary restrictions, accessibility needs) arrive in the dispatch's session context — Back reads them as constraints, not as personality.

### Bus Subscriptions

| Event | Priority | Purpose |
| --- | --- | --- |
| `k1.orchestration.task.dispatch.v1` | INTERACTIVE | New task from Front. Triggers full ReAct execution. |
| `k1.orchestration.task.cancel.v1` | URGENT | Cancel current task. Abort between tool calls via cancellation callback. |
| `k1.orchestration.task.resume.v1` | INTERACTIVE | Resume SUSPENDED task with user's answer to HITL question. |
| `k1.orchestration.clarification.response.v1` | INTERACTIVE | Answer to a question Back asked (alternative resume path). |

### Bus Emissions

| Event | Priority | Trigger |
| --- | --- | --- |
| `k1.tool.started.v1` | BACKGROUND | Before `invoke_capability()` execution (observability). |
| `k1.tool.completed.v1` | BACKGROUND | After tool execution (observability + metrics). |
| `k1.orchestration.task.complete.v1` | INTERACTIVE | `submit_result(result_type="complete")` tool call. |
| `k1.orchestration.task.failed.v1` | INTERACTIVE | Budget exhaustion, cancellation, or unrecoverable error. |
| `k1.orchestration.task.suspended.v1` | INTERACTIVE | `submit_result(result_type="needs_human")` tool call. |
| `k1.orchestration.findings.ready.v1` | BACKGROUND | Partial results available (streaming/progress). |
| `k1.session.booking.confirmed.v1` | INTERACTIVE | Booking artifact written to Session State. |

### Tool Schemas (Full JSON)

6 tools: Read 2 + Action 3 + Control 1. `recall_memory` is shared with Front (defined in Section 6.1, `actor="both"`). The remaining 5 are Back-exclusive.

```python
BACK_TOOL_SCHEMAS = [

    # ---- READ (2) ----
    # recall_memory -- same schema as Front (Section 6.1, actor="both")

    ToolSchema(
        name="discover_capabilities",
        description=(
            "Search the Fabric capability registry for tools, agents, or workflows "
            "that can execute the task intent. Returns matching capabilities with "
            "their contracts (required inputs, outputs, side effects, cost). "
            "Call BEFORE invoke_capability when the capability name is unknown. "
            "For LOW tier tasks where capability is already known, skip this and "
            "call invoke_capability directly."
        ),
        parameters={
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "What needs to be done (natural language)",
                },
                "domain": {
                    "type": "string",
                    "description": "Domain hint to narrow search (travel, health, productivity, etc.)",
                },
                "constraints": {
                    "type": "object",
                    "description": "Execution constraints: budget, time, safety_band, etc.",
                },
            },
            "required": ["intent"],
        },
        returns={
            "type": "object",
            "properties": {
                "capabilities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "required_inputs": {"type": "array", "items": {"type": "string"}},
                            "has_side_effects": {"type": "boolean"},
                            "estimated_cost": {"type": "string"},
                        },
                    },
                },
                "count": {"type": "integer"},
            },
        },
        actor="back",
        category="read",
        side_effects=False,
    ),

    # ---- ACTION (3) ----

    ToolSchema(
        name="invoke_capability",
        description=(
            "Execute ANY registered Fabric capability. This is the universal executor. "
            "Pass the capability name (from discover_capabilities or from dispatch intent) "
            "and its parameters. Fabric handles domain routing, provider selection, "
            "input validation, execution, and output normalization. "
            "Examples: 'tool.execute.hotel_booking', 'tool.execute.calendar_create', "
            "'tool.execute.web_search', 'tool.execute.email_draft'. "
            "If the capability has side_effects=true, the system will require user approval "
            "BEFORE this call executes. Call submit_result with hil_type='approval' first."
        ),
        parameters={
            "type": "object",
            "properties": {
                "capability_name": {
                    "type": "string",
                    "description": "Fully qualified capability name from Fabric registry",
                },
                "params": {
                    "type": "object",
                    "description": "Capability-specific parameters. Must satisfy the capability's required_inputs.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Current session ID for context",
                },
            },
            "required": ["capability_name", "params"],
        },
        returns={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {"type": "object", "description": "Capability-specific result data"},
                "artifact_type": {
                    "type": "string",
                    "description": "If a durable artifact was created: 'booking', 'appointment', 'document', etc. Null if no artifact.",
                },
                "error": {"type": "string", "description": "Error message if success=false"},
                "duration_ms": {"type": "integer"},
            },
        },
        actor="back",
        category="action",
        side_effects=True,
    ),

    ToolSchema(
        name="spawn_via_fabric",
        description=(
            "Create a dynamic specialist agent for complex sub-tasks that need "
            "multiple coordinated capability calls. MEDIUM and HIGH tier only. "
            "The spawned agent executes independently and reports back. "
            "Spawned agents use the same submit_result contract for termination."
        ),
        parameters={
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "description": "Type of specialist agent",
                },
                "task": {
                    "type": "string",
                    "description": "Task description for the agent",
                },
                "constraints": {
                    "type": "object",
                    "description": "Budget, timeout, safety constraints",
                },
                "capabilities_needed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Fabric capabilities the agent will need",
                },
            },
            "required": ["agent_type", "task"],
        },
        returns={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "status": {"type": "string", "enum": ["spawned", "failed"]},
                "result": {"type": "object", "description": "Agent result when complete"},
            },
        },
        actor="back",
        category="action",
        side_effects=True,
    ),

    ToolSchema(
        name="execute_workflow",
        description=(
            "Run a multi-step Orchestrator workflow (DAG execution). "
            "MEDIUM and HIGH tier only. For tasks that require coordinated "
            "sequential/parallel capability calls with dependency management."
        ),
        parameters={
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Registered workflow ID",
                },
                "params": {
                    "type": "object",
                    "description": "Workflow input parameters",
                },
                "timeout_ms": {
                    "type": "integer",
                    "default": 30000,
                },
            },
            "required": ["workflow_id", "params"],
        },
        returns={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "steps_completed": {"type": "integer"},
                "steps_failed": {"type": "integer"},
                "results": {"type": "array", "items": {"type": "object"}},
                "artifacts": {"type": "array", "items": {"type": "object"}},
            },
        },
        actor="back",
        category="action",
        side_effects=True,
    ),

    # ---- CONTROL (1) ----

    ToolSchema(
        name="submit_result",
        description=(
            "Signal task completion or request human-in-the-loop intervention. "
            "This is the ONLY way to end a task. Every Back task MUST terminate "
            "with a submit_result call. Two modes: "
            "(1) result_type='complete': Task done, provide final answer and results. "
            "(2) result_type='needs_human': Suspend task, ask user for clarification, "
            "approval, or selection via HITL protocol."
        ),
        parameters={
            "type": "object",
            "properties": {
                "result_type": {
                    "type": "string",
                    "enum": ["complete", "needs_human"],
                    "description": "'complete' = task done. 'needs_human' = suspend for user input.",
                },

                # -- For result_type='complete' --
                "final_answer": {
                    "type": "string",
                    "description": (
                        "Technical summary of what was accomplished. Required for 'complete'. "
                        "Factual, no personality. The presentation system decides tone. "
                        "GOOD: 'Found 3 Italian restaurants in Sonoma with outdoor seating. "
                        "Top match: Oenotri, 4.6 stars, $$$, available June 15.' "
                        "BAD: 'Great news! I found some amazing restaurants you will love!'"
                    ),
                },
                "results": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Structured result data for Front to present.",
                },
                "artifacts_created": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "summary": {"type": "string"},
                            "data": {"type": "object"},
                        },
                    },
                    "description": "Durable artifacts: bookings, appointments, documents created.",
                },

                # -- For result_type='needs_human' --
                "hil_type": {
                    "type": "string",
                    "enum": ["clarification", "approval", "selection"],
                    "description": "Type of human input needed. Required for 'needs_human'.",
                },
                "question": {
                    "type": "string",
                    "description": "Question to present to the user.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Options for selection/approval.",
                },
                "side_effects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For approval: what will happen if user approves.",
                },
            },
            "required": ["result_type"],
        },
        returns={
            "type": "object",
            "properties": {
                "accepted": {"type": "boolean"},
                "task_status": {"type": "string"},
            },
        },
        actor="back",
        category="control",
        side_effects=False,
    ),
]
```

### Tool Allowlist by Tier

Back's tools are gated by complexity tier. LOW tier gets 2 tools (capability already resolved by Front). MEDIUM/HIGH unlock discovery and multi-step orchestration:

| Tool | LOW | MEDIUM | HIGH |
| --- | --- | --- | --- |
| `recall_memory` | Y | Y | Y |
| `discover_capabilities` | - | Y | Y |
| `invoke_capability` | Y | Y | Y |
| `spawn_via_fabric` | - | Y | Y |
| `execute_workflow` | - | Y | Y |
| `submit_result` | Y | Y | Y |
| **Total** | **3** | **6** | **6** |

**LOW tier Back has only 3 tools** (`recall_memory` + `invoke_capability` + `submit_result`) because the capability is already resolved by Front's dispatch. No discovery or spawning needed. This keeps LOW-tier invocations fast (2-3 iterations).

```python
BACK_TOOL_ALLOWLIST: dict[str, list[str]] = {
    "LOW": ["recall_memory", "invoke_capability", "submit_result"],
    "MEDIUM": [
        "recall_memory", "discover_capabilities", "invoke_capability",
        "spawn_via_fabric", "execute_workflow", "submit_result",
    ],
    "HIGH": [
        "recall_memory", "discover_capabilities", "invoke_capability",
        "spawn_via_fabric", "execute_workflow", "submit_result",
    ],
}
```

### The `invoke_capability()` Universal Executor Pattern

The key design insight: the Back LLM does NOT have domain-specific tools. It has ONE universal tool that can execute anything registered in Fabric's capability registry:

```python
# Travel domain
invoke_capability("tool.execute.hotel_search", {"city": "Napa", "dates": "June 15-17"})
invoke_capability("tool.execute.hotel_booking", {"hotel_id": "vineyard-inn", "guests": 2})

# Health domain
invoke_capability("tool.execute.appointment_schedule", {"provider": "Dr. Smith", "date": "March 5"})
invoke_capability("tool.execute.medication_reminder", {"med": "Vitamin D", "time": "08:00"})

# Productivity domain
invoke_capability("tool.execute.calendar_create", {"title": "Team standup", "recurrence": "daily"})
invoke_capability("tool.execute.email_draft", {"to": "boss@company.com", "subject": "Q3 report"})

# Creative domain
invoke_capability("tool.execute.essay_draft", {"topic": "Climate change", "style": "argumentative"})
invoke_capability("tool.execute.image_generate", {"prompt": "sunset over mountains", "style": "watercolor"})

# Shopping domain
invoke_capability("tool.execute.product_search", {"query": "laptop under $1000", "sort": "rating"})
invoke_capability("tool.execute.price_compare", {"product_ids": ["abc", "def", "ghi"]})
```

Any capability the family needs can be registered in Fabric and immediately accessible through `invoke_capability()` — no code changes to the Concierge. The Fabric capability registry is the catalog. The Back LLM is the cursor.

### System Prompt (Full Production Text)

The Back prompt has a constant identity section (~1500 tokens) plus a dynamic task block injected per dispatch. Gemini JSON-only mode is enforced: all output must be tool calls, never free-form text.

```python
BACK_SYSTEM_PROMPT = """
== IDENTITY ==
You are the Worker. You receive structured task dispatches and produce
structured JSON results. You are a pure executor.

What you ARE:
- A task executor with access to a universal capability registry.
- A planner for multi-step execution within a single task.
- A quality gate: you validate results before submitting.

What you are NOT:
- A conversationalist. You NEVER produce text for human consumption.
  Your final_answer is a TECHNICAL SUMMARY for the presentation system.
- A decision-maker on user preferences. Those are in the dispatch.
- Aware of who the user is. You serve the dispatch, not a person.

What you produce:
- Tool calls only. Each iteration: exactly ONE tool call.
- NOTHING else. No greetings, no opinions, no personality.

final_answer format (in submit_result):
  GOOD: "Found 3 Italian restaurants in Sonoma with outdoor seating.
         Top match: Oenotri, 4.6 stars, $$$, available June 15."
  BAD:  "Great news! I found some amazing restaurants you'll love!"
  The presenter decides tone. You provide data.


== REACT EXECUTION PROTOCOL ==
You operate in a Think-Act-Observe loop. Each iteration:
  1. THINK: What do I know? What do I need? What's next?
  2. ACT: Call ONE tool.
  3. OBSERVE: Read the result. Decide next step.

Follow this mandatory sequence. Do not skip steps.

STEP 1 -- ORIENT:
  Read the task dispatch below: intents, params, reference_context.
  Read beliefs_summary and task_artifacts in session context.
  If the dispatch includes reference_context, use it to resolve pronouns.
  VERIFY reference_context: cross-check reference_context against
    beliefs_summary and task_artifacts. If reference_context contradicts
    a high-confidence belief (>= 0.8), prefer the belief. If reference_context
    refers to an entity not found in beliefs or artifacts, call recall_memory()
    to verify before proceeding.
  If task needs historical context the dispatch doesn't provide:
    -> call recall_memory() as your first tool call.

STEP 2 -- CHECK EXISTING WORK:
  Has this work already been done? Check task_artifacts.
  If a booking already exists for the same item, do NOT re-book.
  If search results already exist, build on them, don't re-search.

STEP 3 -- ASSESS CAPABILITY KNOWLEDGE:
  Do you know the exact capability name for this task?
  YES (LOW tier or obvious): -> Skip to STEP 5.
  NO (unknown capability):   -> Go to STEP 4.

STEP 4 -- DISCOVER:
  Call discover_capabilities(intent=<action>, domain=<domain>).
  OBSERVE the result. Read each returned capability:
    - name: the exact string for invoke_capability
    - required_params: what inputs it needs
    - side_effects: does it modify external state?
  Select the best match. If none match:
    -> call submit_result(needs_human, clarification,
       "No capability found for: <intent>").

STEP 5 -- SAFETY CHECK:
  Before calling invoke_capability, check the capability's side_effects flag:

  GREEN (side_effects=false): Execute freely.
    Examples: search, lookup, compare, recall, summarize, get status,
    read calendar, check weather, query inventory, list options.

  AMBER (side_effects=true): Request approval FIRST.
    Call submit_result(result_type="needs_human", hil_type="approval")
    with explicit consequences in side_effects[].
    WAIT for approval before executing.
    Examples: book accommodation, place order, send message, create event,
    turn on smart oven, lock door, modify calendar, transfer money.

  RED (safety_band="RED" in dispatch constraints): Refuse.
    Call submit_result(needs_human, clarification,
      "This action requires elevated authorization: <reason>.")
    NEVER execute RED capabilities.

  If discover_capabilities returned a capability with side_effects=true
  and safety_band is not specified: treat as AMBER by default.

STEP 6 -- INVOKE:
  Call invoke_capability(capability=<name>, params=<params>).
  OBSERVE the result.
  If it failed: check if a retry makes sense (different params, not same).
  Max 1 retry per capability (2 total attempts: original + 1 retry).

STEP 7 -- EVALUATE:
  Are the results sufficient to answer the task?
  YES -> Go to STEP 8.
  NO, need more data -> Return to STEP 3 for the next sub-task.
  NO, ambiguous results -> submit_result(needs_human, selection, options).

STEP 8 -- SUBMIT:
  Call submit_result(result_type="complete") with:
    - final_answer: technical summary (1-3 sentences, factual, no personality)
    - results: structured data array with ALL relevant fields
    - artifacts_created: durable outputs (bookings, appointments, documents)


== TOOL SELECTION RULES ==
You have 6 tools. Here is when to use each:

recall_memory(query):
  WHEN: Task needs historical context the dispatch doesn't provide.
    "What hotel did they stay at last time?"
    "Any past issues with this restaurant?"
  WHEN NOT: The dispatch already includes the information in params or
    reference_context. Don't recall what you already have.
  CALL: Early (STEP 1), before capability calls.

discover_capabilities(intent, domain):
  WHEN: You don't know the capability name.
  WHEN NOT: Capability is obvious (e.g., "tool.execute.hotel_search").
  CALL: STEP 4. Once per unique intent. Don't re-discover.

invoke_capability(capability, params):
  WHEN: You know the capability and have the params.
  CALL: STEP 6. One at a time. Observe result before next call.

spawn_via_fabric(spec):
  WHEN: Task requires a specialist agent (MEDIUM/HIGH tier only).
  WHEN NOT: A single invoke_capability can handle it.

execute_workflow(workflow_id, params):
  WHEN: Task has a registered workflow (MEDIUM/HIGH tier only).
  WHEN NOT: Ad-hoc tasks without pre-defined workflows.

submit_result(result_type, ...):
  WHEN: Task is done OR you need human input.
  CALL: ALWAYS at the end. This is the ONLY exit. No exceptions.


== RESULT FORMAT ==
submit_result(result_type="complete") must include:

final_answer (string): Technical summary. Factual. No personality.
  "Booked Vineyard Inn, Sonoma. 2 nights, June 15-17. $598 total.
   Confirmation ACM-847293. Cancellation policy: free until June 13."

results (array of objects): Structured data the presenter needs.
  Each object: consistent keys within the result set.
  Include ALL relevant data fields. The presenter decides what to show.

artifacts_created (array): Durable outputs that persist in session state.
  [{type: "booking", summary: "Hotel: Vineyard Inn, June 15-17",
    data: {confirmation: "ACM-847293", property: "Vineyard Inn", total: 598}}]

Do NOT include:
  - User-facing prose or greetings
  - Markdown formatting
  - Suggestions about what to do next (presenter's job)


== AMBIGUITY HANDLING ==
Multiple matching results (e.g., 3 hotels named "Vineyard Inn"):
  Call submit_result(needs_human, selection) with all options.
  Include: name, distinguishing details, price.
  Do NOT pick randomly. Do NOT pick the first one.

Missing required parameters:
  Check reference_context first. Check beliefs_summary.
  If still missing: submit_result(needs_human, clarification).

Maximum suspensions: 2 per task.
  On third ambiguity: pick the best option, note reasoning in final_answer.


== ANTI-PATTERNS (NEVER DO THESE) ==
- Generate user-facing text. Your output is consumed by a system, not a human.
- Re-execute work already in task_artifacts. Check before invoking.
- Call invoke_capability without first checking side_effects.
- Call the same capability with the same params after it failed.
  Change params or try a different capability.
- Invent capability names. If discover_capabilities returns nothing,
  submit_result with needs_human.
- Leave a task without calling submit_result.
- Call submit_result(complete) with empty results.


== BUDGET ==
You have {max_tool_calls} tool calls remaining (including submit_result).
Track your usage:
  At 2 remaining: submit what you have. Do NOT try another capability.
  At 1 remaining: call submit_result immediately with partial results.

Budget-aware strategy:
  LOW tier (budget ~4):  invoke directly, submit.
  MEDIUM tier (budget ~8): discover + 2-3 invokes + submit.
  HIGH tier (budget ~12): discover + workflow/spawn + submit.


== IN-CONTEXT EXAMPLES ==

Example 1 -- LOW tier, direct invoke:
  Dispatch: {intents: [{action: "search_hotels", params: {location: "Napa"}, domain: "travel"}]}
  Iteration 1: invoke_capability("tool.execute.hotel_search",
    {location: "Napa", dates: "June 15-17"})
    -> observe: {success: true, data: [{name: "Vineyard Inn", price: 185}, ...]}
  Iteration 2: submit_result(result_type="complete",
    final_answer="Found 2 hotels in Napa for June 15-17.",
    results=[{name: "Vineyard Inn", price: 185}, {name: "Marriott", price: 298}])

Example 2 -- AMBER, approval before side-effect:
  Dispatch: {intents: [{action: "book_hotel", params: {hotel: "Vineyard Inn"}}]}
  Iteration 1: submit_result(result_type="needs_human", hil_type="approval",
    question="Confirm booking?",
    options=["Vineyard Inn, Sonoma, 2 nights, $598"],
    side_effects=["Charge $598 to Visa ending 4242", "Non-refundable after June 13"])
  -- [SUSPENDED. Resumed with approval.] --
  Iteration 2: invoke_capability("tool.execute.hotel_booking",
    {hotel: "Vineyard Inn", check_in: "June 15", nights: 2})
    -> observe: {success: true, confirmation: "ACM-847293"}
  Iteration 3: submit_result(result_type="complete",
    final_answer="Booked Vineyard Inn. Confirmation ACM-847293. $598.",
    results=[{confirmation: "ACM-847293", hotel: "Vineyard Inn", total: 598}],
    artifacts_created=[{type: "booking", summary: "Vineyard Inn, June 15-17",
      data: {confirmation: "ACM-847293"}}])

Example 3 -- Unknown capability, discover first:
  Dispatch: {intents: [{action: "find dinosaur diorama supplies", domain: "shopping"}]}
  Iteration 1: discover_capabilities(
    intent="find craft supplies for dinosaur diorama", domain="shopping")
    -> observe: {capabilities: [{name: "tool.execute.product_search",
       side_effects: false, required_params: ["query"]}]}
  Iteration 2: invoke_capability("tool.execute.product_search",
    {query: "dinosaur diorama kit children", sort: "rating"})
    -> observe: {success: true, data: [{name: "Diorama Kit", price: 24.99}, ...]}
  Iteration 3: submit_result(result_type="complete",
    final_answer="Found 5 dinosaur diorama kits. Top rated: $24.99.",
    results=[...])

Example 4 -- Ambiguity, selection HITL:
  Dispatch: {intents: [{action: "book_hotel", params: {hotel: "Vineyard Inn"}}]}
  Iteration 1: invoke_capability("tool.execute.hotel_search",
    {name: "Vineyard Inn"})
    -> observe: {data: [{name: "Vineyard Inn, Napa", price: 298},
       {name: "Vineyard Inn, Sonoma", price: 185},
       {name: "Vineyard Inn & Spa, St. Helena", price: 420}]}
  Iteration 2: submit_result(result_type="needs_human", hil_type="selection",
    question="Multiple Vineyard Inn properties found",
    options=["Napa ($298/night)", "Sonoma ($185/night)", "St. Helena ($420/night)"])


== TASK DISPATCH ==
{task_json}

== SESSION CONTEXT ==
Beliefs: {beliefs_summary}
Active tasks: {task_state_summary}
Completed artifacts: {artifacts_summary}
Safety band: {safety_band}
User preferences: {persona_prefs}
"""
```

### Max Iterations per Tier

Back's budget is tier-driven (not mode-driven like Front):

| Tier | Max Iterations | Max Tool Calls | Rationale |
| --- | --- | --- | --- |
| LOW | 4 | 4 | Capability known. invoke -> submit. 2-3 iterations typical. |
| MEDIUM | 8 | 8 | discover + 2-3 invokes + submit. May spawn agent. |
| HIGH | 12 | 12 | discover + workflow/spawn + multiple invokes + submit. |

```python
BACK_MAX_ITERATIONS: dict[str, int] = {
    "LOW": 4,
    "MEDIUM": 8,
    "HIGH": 12,
}
```

### Context Assembly (Per Invocation Scenario)

Back gets a DIFFERENT context from Front. It is task-focused, not conversation-focused. Three distinct assembly scenarios depending on the trigger:

#### Scenario 1: Task Dispatch (New Task)

**Trigger:** `k1.orchestration.task.dispatch.v1` arrives.

```python
BackContext_TaskDispatch = {
    # --- IDENTITY (static) ---
    "system_prompt": BACK_SYSTEM_PROMPT,                # ~1500 tokens, constant

    # --- TASK SPECIFICATION ---
    "task": {
        "task_id": dispatch.task_id,
        "intents": dispatch.intents,                    # What to do
        "tier": dispatch.tier,                          # LOW | MEDIUM | HIGH
        "budget_hint": dispatch.budget_hint,            # Max tool calls
    },

    # --- SESSION CONTEXT (selective read from SS) ---
    "beliefs_active": ss.beliefs_active.to_prompt(),    # User facts, constraints
    "scoreboard_referents": ss.scoreboard.get_referents(),  # What "it", "there" means
    "task_state": ss.task_state.to_prompt(),             # Dependency info, other active tasks
    "task_artifacts": ss.task_artifacts.to_prompt(),     # What's already done (avoid re-doing)
    "safety_band": ss.control.safety.band,              # Safety constraint

    # --- CONVERSATION CONTEXT (limited history) ---
    "history_summary": ss.history_active.get_recent(5), # Last 5 entries only

    # --- USER PREFERENCES (from persona) ---
    "persona_prefs": {
        "preferred_payment": ss.persona.get("payment_method"),
        "dietary_restrictions": ss.persona.get("dietary"),
        "accessibility_needs": ss.persona.get("accessibility"),
    },

    # --- AVAILABLE TOOLS ---
    "tools": BACK_TOOL_ALLOWLIST[dispatch.tier],        # 3 (LOW) or 6 (MEDIUM/HIGH)
}
```

**Why Back gets 5 history entries (not 20 like Front):** Back needs enough history to understand what the user originally asked (may be 2-3 turns ago), what Front already acknowledged, and what constraints were mentioned. It does NOT need full 20-turn history or emotional context. The `reference_context` in the dispatch resolves distant references that 5 entries cannot reach (see Reference Context Enrichment below).

#### Scenario 2: Task Resume (After HITL)

**Trigger:** `k1.orchestration.task.resume.v1` arrives for a SUSPENDED task.

```python
BackContext_TaskResume = {
    # Same as TaskDispatch PLUS:
    "resume_context": {
        "original_task": dispatch.task_spec,              # Original dispatch (from FSMTurnState)
        "findings_so_far": prior_messages,                # ReAct message history before suspend
        "tool_history": [m for m in prior_messages if m.role == "tool"],
        "last_iteration": len([m for m in prior_messages if m.role == "assistant"]),
        "resolution": resume.resolution,                 # User's answer to HITL question
    },
    "resume_instruction": """
        You previously suspended this task for clarification.
        The user has provided their answer (in resolution).
        Resume from where you left off. Do NOT re-execute tools
        that already succeeded. Use findings_so_far as your starting state.
    """,
}
```

**ReAct history preservation:** When a task suspends, the FSM stores the complete ReAct message history (all iterations before the `submit_result(needs_human)` call) in `FSMTurnState`. On resume, this history is restored as `findings_so_far` so Back can continue exactly where it left off without repeating work.

#### Scenario 3: ReAct Iteration (Mid-Task Reasoning)

**Trigger:** Back's ReAct loop enters iteration N > 0.

```python
BackContext_ReActIteration = {
    # Same base as TaskDispatch PLUS:
    "iteration": iteration,
    "tool_history": [m for m in messages if m.role == "tool"],
    "findings": [m.content for m in messages if m.role == "tool"],
    "remaining_budget": max_iterations - iteration,
    # NOTE: Back does NOT re-read SS on every iteration.
    # SS context is captured at task start and stays fixed.
    # Exception: if Back calls recall_memory(), it reads K0
    # long-term memory (not SS) for additional context.
}
```

**Why Back does NOT re-read SS per iteration:** Back's task is scoped by the dispatch envelope. Mid-task SS changes (Front updating beliefs from a concurrent conversation) should not cause Back to change course mid-execution. The dispatch snapshot is the contract. If beliefs change so significantly that the task is invalid, Front should emit `k1.orchestration.task.cancel.v1` instead.

### Session State Read Configuration

Back reads a fixed subset of SS at task start. No mode-driven variation — the same sections for every invocation, regardless of trigger:

| SS Section | Read Mode | Purpose |
| --- | --- | --- |
| `beliefs_active` | FULL | User facts, constraints, preferences for task params |
| `scoreboard` | Referents only | What "it", "there", "the hotel" resolves to |
| `task_state` | FULL | Dependency info, other active tasks, avoid duplicates |
| `task_artifacts` | FULL | What's already done (avoid re-doing work) |
| `control` | Safety band only | GREEN/AMBER/RED safety constraint |
| `history_active` | 5 entries | Immediate conversational context |
| `persona` | Preferences only | Payment, dietary, accessibility |
| `affective_now` | Skip | Back does not need emotional context |
| `clarifications` | Skip | Front's concern, not Back's |
| `narrative_active` | Skip | Thread tracking is Front's concern |
| `meta` | Skip | Not relevant to task execution |
| **Est. tokens** | **~2000** | Lean context leaves room for tool results |

### Reference Context Enrichment

Back gets only 5 history entries. This is intentional (token efficiency). But it creates reference resolution failures for distant context. The solution is NOT to widen the window — it's to have Front resolve references at dispatch time.

The `dispatch_task` tool (Section 6.1) includes `reference_context`:

```python
dispatch_task(
    intents=[{action: "book hotel", params: {hotel: "Vineyard Inn"}}],
    reference_context={
        "the hotel": "Vineyard Inn, Sonoma",
        "it": "Vineyard Inn, Sonoma",
        "those dates": "June 15-17, 2026",
        "the cheaper one": "Vineyard Inn Sonoma ($185/night, not Napa $298/night)",
    },
)
```

Back reads `reference_context` in STEP 1 (ORIENT) before executing. If the task says "book it" and `reference_context` says `{"it": "Vineyard Inn, Sonoma"}`, Back knows what "it" means without needing 20 turns of history.

**Reference resolution is Front's responsibility.** Front has 20 entries of history. Front does the cognitive work (reference resolution = understanding). Back does the execution work (booking = doing). This matches the voice/hands split. If Front fails to resolve a reference, Back can still call `submit_result(needs_human, clarification)` as a fallback.

Front's prompt (Section 6.1, DISPATCH_RULES) instructs reference resolution with this priority:

1. Check `scoreboard.referent_updates` (Phase 1 may have resolved)
2. Check `task_artifacts` (recent completed items)
3. Check `beliefs_active` (stated preferences)
4. Check chat history in messages (last 2-3 turns)
5. If STILL ambiguous: pass as unresolved in `reference_context` — Back can request HITL clarification

Back's prompt (STEP 1, ORIENT) instructs reference verification:

> VERIFY reference_context: cross-check against beliefs_summary and task_artifacts. If reference_context contradicts a high-confidence belief (>= 0.8), prefer the belief.

### Back Handler Wiring (ITEM #14)

The complete `back_handler` function. Key difference from `front_handler` (Section 6.1): no mode resolution, no affect modulation, no prompt builder pipeline. Back gets a static prompt + dynamic task block. The critical detail is the `cancellation_check` callback wiring — this connects the FSM's cancellation flag (Section 4, `FSMTurnState.cancellation_requested`) through to `react_loop()`'s cancellation parameter (Section 7).

```python
async def back_handler(
    envelope: Envelope,
    model: IConciergeModelPort,
    ss: SessionState,
    fsm_state: FSMTurnState,
) -> ReactResult:
    """Back handler: ReAct agent for task execution.

    Called by FSM when a task.dispatch arrives. Builds task-focused
    context and runs the ReAct loop with tier-based budget.
    """

    task = envelope.payload

    # 1. Determine tier and budget
    tier = task.get("tier", "LOW")
    max_iterations = BACK_MAX_ITERATIONS[tier]

    # 2. Build system prompt with task context + SS snapshot
    system_prompt = build_back_prompt(
        task=task,
        beliefs=ss.beliefs_active.to_prompt(),
        referents=ss.scoreboard.get_referents(),
        task_state=ss.task_state.to_prompt(),
        task_artifacts=ss.task_artifacts.to_prompt(),
        safety_band=ss.control.safety.band,
        persona_prefs={
            "preferred_payment": ss.persona.get("payment_method"),
            "dietary_restrictions": ss.persona.get("dietary"),
            "accessibility_needs": ss.persona.get("accessibility"),
        },
        max_tool_calls=max_iterations,
    )

    # 3. Build messages: last 5 turns for reference context
    messages = build_chat_history(ss.history_active, window=5)
    # Add the task dispatch as the "current input" for Back
    messages.append(ModelMessage(
        role="user",
        content=json.dumps(task, indent=2),
    ))

    # 4. Select tools by tier
    tool_names = BACK_TOOL_ALLOWLIST[tier]
    tools = [t for t in BACK_TOOL_SCHEMAS if t.name in tool_names]
    # recall_memory is shared — add from FRONT_TOOL_SCHEMAS
    if "recall_memory" in tool_names:
        recall = next(t for t in FRONT_TOOL_SCHEMAS if t.name == "recall_memory")
        tools.append(recall)

    # 5. Run ReAct loop with cancellation callback (ITEM #14)
    #    cancellation_check wires FSMTurnState.cancellation_requested
    #    (defined in Section 4) through to react_loop() (Section 7).
    #    When Front emits k1.orchestration.task.cancel.v1, the FSM sets
    #    fsm_state.cancellation_requested = True. The ReAct loop checks
    #    this flag BETWEEN iterations and exits cleanly if set.
    result = await react_loop(
        actor="back",
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        max_iterations=max_iterations,
        model=model,
        tool_dispatcher=back_tool_dispatcher,
        on_ack=None,                 # Back never acks
        on_text_response=lambda _: None,  # Back text = "thinking aloud", ignored
        cancellation_check=lambda: fsm_state.cancellation_requested,
        trace_id=envelope.trace_id,
    )

    # 6. Emit result to bus based on exit status
    if result.status == "complete":
        emit(Envelope(
            topic="k1.orchestration.task.complete.v1",
            payload={"task_id": task["task_id"], **result.data},
            parent_id=envelope.envelope_id,
        ))
    elif result.status == "suspended":
        emit(Envelope(
            topic="k1.orchestration.task.suspended.v1",
            payload={"task_id": task["task_id"], **result.data},
            parent_id=envelope.envelope_id,
        ))
    elif result.status in ("cancelled", "budget_exhausted"):
        emit(Envelope(
            topic="k1.orchestration.task.failed.v1",
            payload={
                "task_id": task["task_id"],
                "reason": result.status,
                "partial_results": result.data.get("partial_results", []),
                "tool_history": result.data.get("tool_history", []),
            },
            parent_id=envelope.envelope_id,
        ))

    return result
```

**Cancellation callback chain (ITEM #14):**

```text
User says "cancel"
  -> Front emits k1.orchestration.task.cancel.v1
    -> FSM receives, sets fsm_state.cancellation_requested = True
      -> react_loop() checks cancellation_check() BETWEEN iterations
        -> Returns ReactResult(status="cancelled")
          -> back_handler emits k1.orchestration.task.failed.v1 with reason="cancelled"
```

### `build_back_prompt()` Helper

Assembles the static Back prompt with dynamic task and context sections:

```python
def build_back_prompt(
    task: dict,
    beliefs: str,
    referents: dict,
    task_state: str,
    task_artifacts: str,
    safety_band: str,
    persona_prefs: dict,
    max_tool_calls: int,
) -> str:
    """Build Back system prompt with task-specific context injection.

    Unlike Front's DynamicPromptBuilder (mode-driven, 9-stage pipeline),
    Back uses simple template substitution. The prompt structure is constant
    across all invocations -- only the task block and SS sections change.
    """
    return BACK_SYSTEM_PROMPT.format(
        task_json=json.dumps(task, indent=2),
        beliefs_summary=beliefs,
        task_state_summary=task_state,
        artifacts_summary=task_artifacts,
        safety_band=safety_band,
        persona_prefs=json.dumps(persona_prefs, indent=2),
        max_tool_calls=max_tool_calls,
    )
```

### ReAct Rhythm (Back-Specific Behavior)

Back terminates on **`submit_result()` tool call**. This is the L2 convergence signal (Section 7). Key Back-specific ReAct behaviors that differ from Front:

- **Text without tool calls is NOT terminal.** When Back generates text without tool calls, this is "thinking aloud" — the loop continues to the next iteration. Only `submit_result()` ends a task. This is the critical L2 convergence difference from Front (see Section 7, ITEM #19).
- **No `tool_choice` forcing.** Back does not need `tool_choice="required"` on iteration 1 — it has no `acknowledge()` to guarantee.
- **`tool_choice="auto"` on ALL iterations.** Back decides freely what tool to call next based on observations.
- **Cancellation is checked BETWEEN iterations.** If `cancellation_check()` returns `True`, the loop exits with `ReactResult(status="cancelled")` before the next LLM call.
- **Budget exhaustion:** If `max_iterations` reached without `submit_result`, the loop emits `task.failed` with `reason="budget_exhausted"` and includes `partial_results` from any tool results accumulated so far.

Typical ReAct cadence per tier:

| Tier | Typical Pattern | Iterations |
| --- | --- | --- |
| LOW | invoke -> submit | 2 |
| LOW (with recall) | recall -> invoke -> submit | 3 |
| LOW (AMBER) | submit(approval) -> [suspend/resume] -> invoke -> submit | 3 (across 2 sessions) |
| MEDIUM | discover -> invoke -> invoke -> submit | 4-5 |
| MEDIUM (with agent) | discover -> spawn -> submit | 3-4 |
| HIGH | discover -> execute_workflow -> submit | 3-4 |
| HIGH (complex) | discover -> invoke -> spawn -> invoke -> submit | 5-8 |

### Front vs. Back: Architecture Comparison

| Dimension | Front (Section 6.1) | Back (Section 6.2) |
| --- | --- | --- |
| **Identity** | Warm, empathetic, conversational | Cold, precise, structured JSON only |
| **User contact** | Direct — IS the voice | None — never talks to user |
| **Tools** | 10 (Signal 1 + Cognitive 6 + Read 2 + Control 1) | 6 (Read 2 + Action 3 + Control 1) |
| **Tool gating** | Mode-driven (10 modes) | Tier-driven (LOW/MEDIUM/HIGH) |
| **Prompt architecture** | Mode-driven, 9-stage DynamicPromptBuilder | Static template + task block substitution |
| **Prompt size** | ~800-5500 tokens (varies by mode) | ~1500 tokens constant + ~2000 SS = ~3500 |
| **SS read depth** | 10 sections, mode-variable (FULL/SLIM/skip) | 7 sections, fixed (same every time) |
| **History window** | 5-20 entries (mode-variable) | 5 entries (fixed) |
| **Affect modulation** | 5 bands, tone blocks, modifier matrix | None — emotional context irrelevant |
| **Domain rules** | 8 domains injected by mode | None — safety band is the only constraint |
| **Termination** | Text without tool calls (L1 signal) | `submit_result()` tool call (L2 signal) |
| **Text output meaning** | User-facing response | "Thinking aloud" — ignored, loop continues |
| **Max iterations** | 1-6 (mode + affect) | 4-12 (tier) |
| **Cancellable** | No | Yes (via `cancellation_check` callback) |

---

# 7. ReAct Loop: Shared Implementation

Both Front and Back are standard ReAct (Reason-Act-Observe) agents sharing a single `react_loop()` implementation. This section defines the shared loop, the context model that feeds it, the convergence signals that terminate it, and the parallel-execution strategy for production scaling.

**Cross-references:**

- `FSMTurnState` is defined in Section 4. The `cancellation_requested` flag lives there.
- Front's handler wiring (`front_handler`) is in Section 6.1.
- Back's handler wiring (`back_handler`) is in Section 6.2.
- Per-actor tool allowlists are in Sections 6.1 and 6.2. This section defines the shared parallelism constants.

---

## 7.1 Why Both Actors Use ReAct

The original architecture made Front single-pass (one LLM call, multiple tool calls returned at once) and Back ReAct. This was architecturally dishonest. A single-pass Front expected the LLM to return 4-5 tool calls in ONE response with no observation between them. `recall_memory` results should inform `update_beliefs`. `update_beliefs` should inform `dispatch_task`. Without observation, the LLM guesses.

**Problem with single-pass Front:**

- Parallel tool execution meant the LLM never saw `recall_memory` results before deciding what to dispatch.
- `acknowledge()` could not fire first -- it competed with other tool calls in the same response.
- The LLM had to pre-plan the entire turn without feedback. Cognitive tool outputs (beliefs update confirmation, recall results) were invisible until after all tools ran.

**Why ReAct Front is better:**

- Each decision is informed by the previous observation. `recall_memory` returns relevant history -> LLM decides to offer a proactive reminder. That reasoning chain is impossible in single-pass.
- `acknowledge()` fires on iteration 1 (user sees ACK in ~200ms). Remaining iterations happen while user waits.
- Each iteration generates ONE tool call (small output = fast generation). Total latency is comparable to single-pass generating 5 tool calls.
- **One loop implementation, two actors.** Simpler code, fewer bugs, easier testing.

### Property Comparison Table

| Property | Front | Back |
| --- | --- | --- |
| Loop type | ReAct | ReAct |
| Max iterations | 1-6 (mode + affect driven, Section 6.1) | 4-12 (tier driven, Section 6.2) |
| Tool calls per iteration | 1 (POC), N (production parallel, Section 7.8) | 1 (POC), N (production parallel, Section 7.8) |
| Observation between iterations | Yes | Yes |
| State between iterations | ReAct message history (in messages array) | ReAct message history (in messages array) |
| Termination signal | Text response with NO tool calls (L1) | `submit_result()` tool call (L2) |
| Text-without-tools meaning | Final user-facing response | "Thinking aloud" -- loop continues (ITEM #19) |
| Chat history injected | 5-20 turns from `history_active` (mode-variable) | 5 turns from `history_active` (fixed) |
| Long-horizon context | Session State in system prompt (mode-variable depth) | Session State in system prompt (fixed 7-section read) |
| `tool_choice` on iteration 1 | `"required"` (forces `acknowledge`, ITEM #13) | `"auto"` (no forced first tool) |
| Cancellation support | No (`cancellation_check=lambda: False`) | Yes (`cancellation_check=lambda: fsm_state.cancellation_requested`) |

---

## 7.2 Design Principle: No Scratchpads

Both actors use the ReAct loop's own message history as working memory. Each iteration appends the tool call and its result as messages. The LLM sees its own prior tool calls and observations natively through the message array.

```python
# Iteration 1: LLM calls acknowledge()
{"role": "assistant", "tool_calls": [{"name": "acknowledge", "args": {"message": "On it!"}}]}
{"role": "tool", "content": '{"delivered": true, "timestamp_ms": 1708300800000}', "tool_call_id": "tc_1"}

# Iteration 2: LLM calls recall_memory() -- informed by iteration 1 observation
{"role": "assistant", "tool_calls": [{"name": "recall_memory", "args": {"query": "prior context"}}]}
{"role": "tool", "content": '{"memories": [{"content": "Last Tuesday..."}], "count": 1}', "tool_call_id": "tc_2"}

# Iteration 3: LLM updates beliefs based on recall_memory result
{"role": "assistant", "tool_calls": [{"name": "update_beliefs", "args": {...}}]}
{"role": "tool", "content": '{"stored": 1, "updated": 0}', "tool_call_id": "tc_3"}

# ... continues until termination signal
```

No `FrontScratchpad`. No `BackScratchpad`. No ephemeral state containers. The LLM sees its own prior tool calls and observations natively through the message array. This is how every production ReAct agent works.

What previously lived in scratchpads now lives in two places:

| Old scratchpad field | New home |
| --- | --- |
| `ack_delivered` flag | ReAct: LLM sees it already called `acknowledge` in message history |
| `tool_history` list | ReAct: tool calls are in the message array |
| `findings` list | ReAct: tool results are in the message array |
| `cancellation_token` | `FSMTurnState.cancellation_requested` checked between iterations (Section 4) |
| `suspension_context` | On resume: FSM replays the task dispatch + prior tool history as messages |
| `execution_budget` | `max_iterations` param on the shared `react_loop()` function |
| Phase A/B/C/D ordering | ReAct iteration order (prompt teaches the rhythm, Sections 6.1/6.2) |

The `FSMTurnState` (Section 4) holds the state that the FSM tracks but the LLM never sees: `pending_results` (task completions queued for Weave), `cancelled_tasks` (dedup set), `cancellation_requested` (flag for mid-loop abort). These are structural concerns, not cognitive ones.

---

## 7.3 Two-Tier Context Model

The LLM receives context from two sources with fundamentally different horizons:

| Source | Horizon | Content | Purpose |
| --- | --- | --- | --- |
| **Chat history (messages array)** | Last N turns (5-20 Front, 5 Back) | Real user/assistant messages from `history_active` | Immediate conversational continuity |
| **Session State (system prompt)** | Full session | beliefs, scoreboard, affect, narrative, task_state, artifacts, persona | Deep context, long-horizon memory |

```python
messages = [
    # ---- System prompt: Session State for long horizon ----
    {"role": "system", "content": system_prompt_with_ss_context},

    # ---- Chat history: last N turns for immediate context ----
    {"role": "user", "content": "Book the Vineyard Inn"},
    {"role": "assistant", "content": "Booking the Vineyard Inn for you!"},
    {"role": "user", "content": "And find restaurants nearby"},
    {"role": "assistant", "content": "On it -- searching for restaurants!"},

    # ---- Current turn input ----
    {"role": "user", "content": "What's today look like?"},

    # ---- ReAct iterations (accumulated during this turn) ----
    # iteration 1: acknowledge
    {"role": "assistant", "tool_calls": [{"name": "acknowledge", ...}]},
    {"role": "tool", "content": '{"delivered": true}', "tool_call_id": "tc_1"},
    # iteration 2: recall_memory
    {"role": "assistant", "tool_calls": [{"name": "recall_memory", ...}]},
    {"role": "tool", "content": '{"memories": [...]}', "tool_call_id": "tc_2"},
    # ... more iterations until termination
]
```

**Why N turns, not the entire history:** The LLM needs recent conversational flow in native message format for natural continuation. It does NOT need the entire conversation crammed into messages -- that wastes context window. For anything beyond the chat history window, the LLM reads Session State: `beliefs_active` for stated facts, `narrative_active` for thread history, `task_artifacts` for completed work, `scoreboard` for topic tracking.

**Why this is faster:** Each ReAct iteration generates ONE tool call (small output). The LLM reasons about ONE observation at a time. Total token generation is comparable to single-pass (which generated 5 tool calls in one shot), but each decision is informed by the previous result.

**Front vs. Back context depth:** Front's SS read depth is mode-variable (Section 6.1, `SS_READ_CONFIGS`). Back's SS read depth is fixed (Section 6.2, 7 sections every time). This reflects their different cognitive demands: Front needs emotional context, thread tracking, and clarification state that vary by mode. Back needs task parameters, constraints, and safety band -- the same set regardless of what the task is.

---

## 7.4 `ReactResult` Dataclass

The return value from `react_loop()`. Both actors produce this; the handler (Section 6.1 `front_handler`, Section 6.2 `back_handler`) interprets it and emits appropriate bus events.

```python
@dataclass
class ReactResult:
    """Return value from react_loop()."""

    status: str
    # "complete"          -- Normal termination.
    #                        Front: text response generated. Back: submit_result(complete) called.
    # "suspended"         -- Back only. submit_result(needs_human) called. Task awaits HITL.
    # "cancelled"         -- Back only. cancellation_check() returned True between iterations.
    # "budget_exhausted"  -- Max iterations reached without termination signal.

    text: str | None = None
    # Front: the final response text (from text-without-tools termination).
    # Back: None (Back never produces user-facing text).

    data: dict | None = None
    # Front: None.
    # Back: the submit_result() arguments (result_type, final_answer, results, artifacts_created).

    dispatched_tasks: list[dict] = field(default_factory=list)
    # Front: dispatch_task() calls collected during the loop.
    #        Handler emits these as k1.orchestration.task.dispatch.v1 events post-loop.
    # Back: empty (Back does not dispatch tasks).
```

**Why `dispatched_tasks` is collected in-loop but emitted post-loop:** Front's `dispatch_task` tool does NOT directly emit bus events. It returns a success confirmation to the LLM so the loop can continue (the LLM may dispatch multiple tasks in a single turn). The handler (Section 6.1) iterates `result.dispatched_tasks` after the loop exits and emits each as a bus event. This keeps the ReAct loop pure (no side effects except tool execution) and gives the handler control over emission timing and priority.

---

## 7.5 The Shared `react_loop()` Implementation

One implementation. Both actors. The differences are:

1. **Termination condition** -- Front: text-without-tools (L1). Back: `submit_result()` (L2).
2. **`tool_choice` on iteration 1** -- Front: `"required"` (ITEM #13). Back: `"auto"`.
3. **Text-without-tools behavior** -- Front: terminal (user response). Back: "thinking aloud", loop continues (ITEM #19).
4. **Cancellation** -- Front: always returns `False`. Back: checks `FSMTurnState.cancellation_requested` (ITEM #14).

```python
async def react_loop(
    actor: str,                    # "front" | "back"
    system_prompt: str,            # Front: built by DynamicPromptBuilder (Section 6.1)
                                   # Back: built by build_back_prompt (Section 6.2)
    messages: list[ModelMessage],  # Chat history + current input
    tools: list[ToolSchema],       # Actor-specific tool set (Sections 6.1/6.2)
    max_iterations: int,           # Front: mode+affect driven. Back: tier driven.
    model: IConciergeModelPort,    # LLM adapter (Section 10)
    tool_dispatcher: ToolDispatcher,  # Validates + executes tool calls
    on_ack: Callable | None,       # Front only: emit ACK to user immediately
    on_text_response: Callable,    # Front: emit response.final. Back: unused (lambda _: None).
    cancellation_check: Callable,  # ITEM #14: FSM provides this callback.
                                   # Front wires: lambda: False (never cancelled).
                                   # Back wires: lambda: fsm_state.cancellation_requested
                                   #   (Section 6.2 back_handler, referencing Section 4 FSMTurnState).
) -> ReactResult:
    """Shared ReAct loop for both Front and Back actors.

    Termination:
      Front (L1): generates text response with NO tool calls -> text becomes response.final
      Back (L2):  calls submit_result() -> structured result emitted to bus
                  (text-without-tool-calls from Back = "thinking aloud", loop continues)

    ITEM #13 -- tool_choice forcing:
      On iteration 0, if actor == "front" and tools are available, tool_choice is set to
      "required". This guarantees acknowledge() fires before any other processing. Without
      this, the LLM might generate a text response immediately (skipping ACK), or call a
      cognitive tool before acknowledging the user.

    ITEM #14 -- cancellation_check:
      Checked at the TOP of each iteration (before the LLM call). If True, the loop
      exits immediately with ReactResult(status="cancelled"). The callback is wired by
      the handler: Front passes lambda: False (Front is never cancelled). Back passes
      lambda: fsm_state.cancellation_requested, connecting to the FSMTurnState flag
      set by the FSM when a k1.orchestration.task.cancel.v1 event arrives.

    ITEM #19 -- Back "thinking aloud":
      When Back generates text WITHOUT tool calls, this is NOT terminal. The text is
      appended as an assistant message and the loop continues. Only submit_result()
      terminates Back. This prevents accidental termination from conversational reasoning
      the LLM produces while working through a multi-step task.
    """

    dispatched_tasks: list[dict] = []  # Collect dispatch_task calls during loop

    for iteration in range(max_iterations):

        # ---- CANCELLATION CHECK (ITEM #14) ----
        # Checked BETWEEN iterations, before the next LLM call.
        # For Back: connected to FSMTurnState.cancellation_requested (Section 4).
        # For Front: always False.
        if await cancellation_check():
            return ReactResult(status="cancelled", dispatched_tasks=dispatched_tasks)

        # ---- LLM CALL ----
        response = await model.generate(ConciergeModelRequest(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            # ITEM #13: Force tool_choice="required" on Front iteration 0.
            # This guarantees acknowledge() fires first. Without this, the LLM
            # might skip straight to a text response or call cognitive tools
            # before the user sees an ACK.
            # Back always uses "auto" -- no forced first tool.
            tool_choice="required" if iteration == 0 and actor == "front" and tools else "auto",
            max_tokens=2048,
            actor=actor,
        ))

        # ---- TEXT WITHOUT TOOL CALLS ----
        if response.text and not response.tool_calls:

            # FRONT (L1 termination): text-without-tools = final user response.
            if actor == "front":
                await on_text_response(response.text)
                return ReactResult(
                    status="complete",
                    text=response.text,
                    dispatched_tasks=dispatched_tasks,
                )

            # BACK (ITEM #19): text-without-tools = "thinking aloud".
            # NOT terminal. Append as assistant message and continue.
            # Only submit_result() terminates Back (L2 signal).
            messages.append(ModelMessage(role="assistant", content=response.text))
            continue

        # ---- DEGENERATE RESPONSE: no text AND no tool calls ----
        if not response.text and not response.tool_calls:
            if actor == "front":
                fallback = "Let me think about that for a moment."
                await on_text_response(fallback)
                return ReactResult(
                    status="complete",
                    text=fallback,
                    dispatched_tasks=dispatched_tasks,
                )
            # Back degenerate: treat as thinking aloud, continue.
            continue

        # ---- PROCESS TOOL CALLS ----
        for tc in response.tool_calls:

            # BACK TERMINATION (L2): submit_result is the ONLY exit for Back.
            if tc.name == "submit_result":
                result = await tool_dispatcher.execute(tc)
                return ReactResult(
                    status="complete" if tc.arguments.get("result_type") == "complete" else "suspended",
                    data=tc.arguments,
                    dispatched_tasks=dispatched_tasks,
                )

            # Execute tool and get observation
            result = await tool_dispatcher.execute(tc)

            # Collect dispatch_task calls (Front only, emitted post-loop by handler)
            if tc.name == "dispatch_task":
                dispatched_tasks.append(tc.arguments)

            # Front-specific: if acknowledge(), emit ACK to user immediately
            if tc.name == "acknowledge" and on_ack:
                await on_ack(tc.arguments.get("message", ""))

            # Emit durable artifacts to SS via delta bus (Back: invoke_capability results)
            if tc.name == "invoke_capability" and result.get("success"):
                if result.get("artifact_type"):
                    emit(Envelope(
                        topic="k1.session.artifact.created.v1",
                        payload=result,
                    ))

            # Append tool call + result as messages (ReAct observation)
            messages.append(ModelMessage(
                role="assistant",
                tool_calls=[tc],
            ))
            messages.append(tool_result_to_message(tc, result))

    # ---- BUDGET EXHAUSTED ----
    # Max iterations reached without termination signal.
    if actor == "front":
        fallback = "Let me get back to you on that."
        await on_text_response(fallback)
        return ReactResult(
            status="budget_exhausted",
            text=fallback,
            dispatched_tasks=dispatched_tasks,
        )

    # Back budget exhaustion: emit task.failed with partial results.
    return ReactResult(status="budget_exhausted", dispatched_tasks=dispatched_tasks)
```

### Key Implementation Notes

1. **Sequential tool processing (POC).** The `for tc in response.tool_calls` loop processes tools one at a time. Production parallel batching is defined in Section 7.8 but not implemented in the POC loop.

2. **`tool_result_to_message()` is defined in Section 10** (LLM Adapter). It converts a tool call + result pair into the provider-specific message format for the next LLM call.

3. **`emit()` calls within the loop** are limited to two cases: artifact creation (durable side effect) and ACK delivery (latency-critical). All other bus emissions happen in the handler after the loop exits.

4. **Message array growth.** Each iteration adds 2 messages (assistant tool call + tool result). For a 6-iteration Front loop, this is 12 messages. For a 12-iteration Back loop, this is 24 messages. Combined with chat history (5-20 entries) and system prompt, this fits well within standard context windows (~128K tokens).

---

## 7.6 Convergence and Termination Signals

The two actors use fundamentally different termination signals. This is the most critical behavioral difference in the shared loop.

### L1 Signal: Front Termination (Text Without Tool Calls)

Front terminates when the LLM generates a text response with NO tool calls. This is the natural ReAct exit:

1. Iteration N: LLM returns `response.text` AND `response.tool_calls` is empty.
2. `react_loop()` detects this -> calls `on_text_response(text)`.
3. `front_handler` (Section 6.1) emits `k1.response.final.v1` with the text.
4. Loop exits with `ReactResult(status="complete", text=response.text)`.

The LLM decides when it has enough information to respond. The prompt teaches the rhythm (Section 6.1, `REACT_RHYTHM`): acknowledge first, then cognitive processing, then respond. The LLM naturally converges to a text response after its reasoning chain completes.

**Degenerate case:** If the LLM produces NO text and NO tool calls, `react_loop()` treats this as a text response with fallback content. This should be rare with proper prompting but must be handled.

### L2 Signal: Back Termination (`submit_result()` Tool Call)

Back terminates ONLY when it calls `submit_result()`. This is explicit -- no guessing.

1. Iteration N: LLM calls `submit_result(result_type=..., ...)`.
2. `react_loop()` detects the tool name -> executes it -> exits.
3. `back_handler` (Section 6.2) emits `k1.orchestration.task.complete.v1` or `k1.orchestration.task.suspended.v1`.
4. Loop exits with `ReactResult(status="complete"|"suspended", data=tc.arguments)`.

**Why `submit_result` is better than "no tool calls = done" for Back:**

1. Back can "think aloud" in text without accidentally terminating (ITEM #19).
2. HITL suspension uses the same tool (`result_type="needs_human"`) -- no separate mechanism.
3. The FSM knows EXACTLY when Back is done (tool call event, not absence of tool calls).
4. Back must explicitly state its final answer -- no accidental empty responses treated as completion.

### ITEM #19: Back "Thinking Aloud" Rule

This is the critical L1/L2 divergence. When Back generates text WITHOUT tool calls:

- This is **NOT terminal**. The text is "thinking aloud."
- The loop appends the text as an `assistant` message and continues to the next iteration.
- The LLM may reason in natural language ("The user wants a hotel near the coast. Let me check availability.") before its next tool call.
- Only `submit_result()` ends the loop.

This behavior is hardcoded in `react_loop()` (Section 7.5, the `if actor != "front"` branch under text-without-tools). It is NOT a prompt instruction -- it is a structural loop behavior. The Back system prompt (Section 6.2) reinforces this by never mentioning text-as-terminal, but the enforcement is in code.

**Why this matters:** Without this rule, Back could accidentally terminate by producing a reasoning step as text. The LLM would "think" its way through a problem, and the loop would interpret the first text-only response as completion. The user would get an incomplete result.

### Cancellation Signal (Back Only)

Back can be cancelled between iterations via the `cancellation_check` callback (ITEM #14). The chain:

```text
User says "cancel"
  -> Front emits k1.orchestration.task.cancel.v1
  -> FSM sets FSMTurnState.cancellation_requested = True (Section 4)
  -> react_loop() checks cancellation_check() at top of next iteration
  -> Returns ReactResult(status="cancelled")
  -> back_handler emits k1.orchestration.task.failed.v1 with reason="cancelled"
```

Front is never cancelled (`cancellation_check=lambda: False`). If the user sends a new message while Front is mid-loop, the FSM queues it. Front finishes its current loop, then processes the new message.

### Budget Exhaustion Signal (Both Actors)

If `max_iterations` is reached without a termination signal:

- **Front:** Emits a fallback text response ("Let me get back to you on that.") and returns `ReactResult(status="budget_exhausted")`.
- **Back:** Returns `ReactResult(status="budget_exhausted")`. The handler emits `k1.orchestration.task.failed.v1` with `reason="budget_exhausted"` and includes any `partial_results` from tool calls accumulated so far.

Budget exhaustion should be rare with properly calibrated iteration limits (Section 6.1 `MAX_ITERATIONS`, Section 6.2 `BACK_MAX_ITERATIONS`).

### Termination Summary Table

| Signal | Actor | Trigger | `ReactResult.status` | Handler Action |
| --- | --- | --- | --- | --- |
| L1 (text-no-tools) | Front | LLM returns text, no tool calls | `"complete"` | Emit `k1.response.final.v1` |
| L2 (`submit_result`) | Back | LLM calls `submit_result(complete)` | `"complete"` | Emit `k1.orchestration.task.complete.v1` |
| L2 (`submit_result`) | Back | LLM calls `submit_result(needs_human)` | `"suspended"` | Emit `k1.orchestration.task.suspended.v1` |
| Cancellation | Back | `cancellation_check()` returns True | `"cancelled"` | Emit `k1.orchestration.task.failed.v1` |
| Budget exhaustion | Front | `iteration == max_iterations` | `"budget_exhausted"` | Emit fallback text response |
| Budget exhaustion | Back | `iteration == max_iterations` | `"budget_exhausted"` | Emit `k1.orchestration.task.failed.v1` |
| Thinking aloud | Back | LLM returns text, no tool calls | _(not terminal)_ | Append to messages, continue loop |
| Degenerate | Front | LLM returns nothing | `"complete"` | Emit fallback text response |
| Degenerate | Back | LLM returns nothing | _(not terminal)_ | Continue loop |

---

## 7.7 `build_chat_history()` Helper

Extracts the last N user/assistant turns from `history_active` as real chat messages. Only includes user messages and final responses (not acks, weaves, or tool-call details). This gives the LLM natural conversational flow without bloating the context with internal mechanics.

```python
def build_chat_history(
    history_active: list[TypedHistoryEntry],
    window: int = 3,
) -> list[ModelMessage]:
    """Extract last N user/assistant turns as real chat messages.

    Only includes user messages and final responses (not acks, weaves, or
    tool-call details). This gives the LLM natural conversational flow
    without bloating the context with internal mechanics.

    For anything beyond this window, the LLM reads Session State:
      - beliefs_active for stated facts
      - narrative_active for thread history
      - task_artifacts for completed work
      - scoreboard for topic tracking

    Args:
        history_active: Typed history entries from Session State.
        window: Number of conversational turns (user+assistant pairs) to include.
                Front: varies by mode (SS_READ_CONFIGS, Section 6.1).
                Back: fixed at 5 entries (Section 6.2).

    Returns:
        List of ModelMessage with role="user" or role="assistant".
    """
    messages = []
    recent = [e for e in history_active if e.type in ("user", "final")]
    for entry in recent[-(window * 2):]:
        role = "user" if entry.type == "user" else "assistant"
        messages.append(ModelMessage(role=role, content=entry.text))
    return messages
```

**Why `type in ("user", "final")` only:**

- `"ack"` entries are internal (the user already saw them, they are not conversational turns).
- `"weave"` entries are async result presentations -- they belong in `task_artifacts`, not chat history.
- `"tool_call"` entries are ReAct internals from prior turns -- they would confuse the LLM by mixing old tool calls with the current turn's ReAct history.
- Only `"user"` and `"final"` represent the natural conversational flow the LLM should continue.

**Window sizing rationale:**

| Actor | Window | Why |
| --- | --- | --- |
| Front | 5-20 (mode-variable) | STANDARD needs full conversational context for cognitive processing. PRESENT needs minimal (just show results). CLARIFY_ASK needs recent context to formulate the right question. See `SS_READ_CONFIGS` in Section 6.1. |
| Back | 5 (fixed) | Back needs enough to understand what the user originally asked and what Front acknowledged. It does NOT need full conversation -- the `reference_context` in the dispatch envelope (Section 6.2) resolves distant references. |

---

## 7.8 Parallel vs. Sequential Tool Calling (ITEM #3)

The POC `react_loop()` (Section 7.5) processes tools sequentially -- one per iteration. However, some LLM providers support parallel tool calling where the model returns multiple tool calls in a single response. This section defines the safety classification and production batching strategy.

### Tool Parallelism Classification

Per-actor tool details are in Sections 6.1 and 6.2. This table classifies ALL tools by parallel safety:

| Tool | Actor(s) | Parallel-Safe | Reason |
| --- | --- | --- | --- |
| **Signal** | | | |
| `acknowledge()` | Front | NO (must be first) | Must fire before any other tool. Sequential by design (ITEM #13). |
| **Cognitive (SS writers)** | | | |
| `update_beliefs()` | Front | YES (with other SS writers and reads) | Writes `beliefs_active`. Different SS section from other cognitive tools. |
| `update_scoreboard()` | Front | YES (with other SS writers and reads) | Writes `scoreboard`. Different SS section. |
| `update_clarifications()` | Front | YES (with other SS writers and reads) | Writes `clarifications`. Different SS section. |
| `update_narrative()` | Front | YES (with other SS writers and reads) | Writes `narrative_active`. Different SS section. |
| `refine_affect()` | Front | YES (with other SS writers and reads) | Writes `affective_now`. Different SS section. |
| `promote_belief()` | Front | NO | Depends on `recall_memory` result (need observation before promoting). |
| **Read** | | | |
| `recall_memory()` | Front, Back | YES | Pure read from long-term memory. No side effects. Safe with anything. |
| `summarize_context()` | Front | YES | Pure read + compression. No side effects. |
| `discover_capabilities()` | Back | YES | Pure read from capability registry. No side effects. |
| **Action** | | | |
| `invoke_capability()` | Back | NO | Has side effects. Must observe result before next call. |
| `spawn_via_fabric()` | Back | NO | Creates agents. Must observe result. |
| `execute_workflow()` | Back | NO | Orchestrates multi-step. Must observe result. |
| **Control** | | | |
| `dispatch_task()` | Front | NO | Depends on cognitive state (beliefs, scoreboard) being current. Must come after cognitive tools. |
| `submit_result()` | Back | NO (terminal) | Ends the loop. Must be last. |

### Parallel Batching Rules

When the model returns multiple tool calls in one response, classify and batch:

1. **All reads together:** `recall_memory` + `summarize_context` + `discover_capabilities` can run in parallel via `asyncio.gather()`.
2. **Cognitive writes together:** Multiple cognitive writes (`update_beliefs` + `update_scoreboard` + `update_narrative` + `update_clarifications` + `refine_affect`) can run in parallel because they write to different SS sections. No write conflicts.
3. **Never parallel:** `acknowledge` (must be first), `promote_belief` (depends on `recall_memory` observation), `dispatch_task` (depends on prior cognitive state), `invoke_capability` (side effects), `spawn_via_fabric` (side effects), `execute_workflow` (side effects), `submit_result` (terminal).

### Shared Constants

```python
PARALLEL_SAFE_GROUPS: dict[str, set[str]] = {
    "reads": {"recall_memory", "summarize_context", "discover_capabilities"},
    "cognitive_writes": {
        "update_beliefs", "update_scoreboard", "update_clarifications",
        "update_narrative", "refine_affect",
    },
}

ALWAYS_SEQUENTIAL: set[str] = {
    "acknowledge",       # Must be iteration 1 (ITEM #13, tool_choice="required")
    "promote_belief",    # Depends on recall_memory observation
    "dispatch_task",     # Depends on cognitive state being up-to-date
    "invoke_capability", # Side effects -- must observe before next call
    "spawn_via_fabric",  # Side effects -- creates agents
    "execute_workflow",  # Side effects -- orchestrates multi-step
    "submit_result",     # Terminal -- ends the loop
}
```

### Implementation Strategy (POC vs. Production)

**POC:** `react_loop()` processes tools sequentially (one per iteration, as shown in Section 7.5). The LLM returns one tool call per iteration because `tool_choice` combined with the ReAct rhythm prompt naturally produces single-tool responses. No parallel batching logic needed.

**Production:** When parallel tool calling is enabled:

1. If the model returns N tool calls, classify each against `PARALLEL_SAFE_GROUPS` and `ALWAYS_SEQUENTIAL`.
2. Run all `reads` tools in parallel via `asyncio.gather()`.
3. Await read results. Append all observations to messages.
4. Run all `cognitive_writes` tools in parallel via `asyncio.gather()`.
5. Await write results. Append all observations to messages.
6. Run sequential tools one at a time, appending each observation.
7. Feed all accumulated observations to the LLM in the next iteration.

This preserves the ReAct observe-then-decide principle while reducing latency for independent operations. The classification constants live here (shared concern) while the per-actor tool allowlists live in Sections 6.1 and 6.2 (actor-specific concern).

```python
async def execute_tool_batch(
    tool_calls: list[ToolCall],
    tool_dispatcher: ToolDispatcher,
) -> list[tuple[ToolCall, dict]]:
    """Production: execute parallel-safe tool calls concurrently.

    Groups tool calls by PARALLEL_SAFE_GROUPS, runs each group
    via asyncio.gather(), then runs ALWAYS_SEQUENTIAL tools one at a time.
    Returns (tool_call, result) pairs in execution order.
    """
    results: list[tuple[ToolCall, dict]] = []

    # Classify
    reads = [tc for tc in tool_calls if tc.name in PARALLEL_SAFE_GROUPS["reads"]]
    writes = [tc for tc in tool_calls if tc.name in PARALLEL_SAFE_GROUPS["cognitive_writes"]]
    sequential = [tc for tc in tool_calls if tc.name in ALWAYS_SEQUENTIAL]

    # Phase 1: parallel reads
    if reads:
        read_results = await asyncio.gather(
            *[tool_dispatcher.execute(tc) for tc in reads]
        )
        results.extend(zip(reads, read_results))

    # Phase 2: parallel cognitive writes
    if writes:
        write_results = await asyncio.gather(
            *[tool_dispatcher.execute(tc) for tc in writes]
        )
        results.extend(zip(writes, write_results))

    # Phase 3: sequential (side effects, terminal)
    for tc in sequential:
        result = await tool_dispatcher.execute(tc)
        results.append((tc, result))

    return results
```

---

## 7.9 Shared Tools with Actor-Specific Usage (ITEM #5)

One tool -- `recall_memory` -- is used by both actors but with different semantics, different timing, and different purposes. This dual-use pattern is a property of the shared loop, not of either actor individually.

### `recall_memory` Dual-Use Contract

| Dimension | Front (Section 6.1) | Back (Section 6.2) |
| --- | --- | --- |
| **Purpose** | Conversational enrichment + dispatch parameter resolution | Task-critical detail lookup for capability invocation |
| **When called** | Iteration 2 (after acknowledge, before cognitive tools and dispatch) | STEP 1 of Back protocol (ORIENT, before capability invocation) |
| **What it queries** | Past conversations, user history, long-term preferences | Specific task-relevant details (loyalty numbers, prior bookings, medical records) |
| **What it informs** | `update_beliefs` (iteration 3), `dispatch_task` reference_context (iteration 4+) | `invoke_capability` params (STEP 6) |
| **Example query** | "hotel booking history" (to resolve "same hotel as last time") | "Marriott loyalty number" (to pass to booking capability) |
| **Failure mode** | Dispatch proceeds without enrichment. Back can still recall if needed. | `submit_result(needs_human, clarification)` -- ask Front to ask user. |

### Why Not Two Separate Tools?

The tool schema is identical for both actors: `recall_memory(query: str) -> {memories: [...], count: int}`. The underlying retrieval system (K0 long-term memory) is the same. Creating `front_recall_memory` and `back_recall_memory` would:

1. Double the tool catalog surface for no behavioral difference.
2. Require the LLM to learn two tool names for the same operation.
3. Create a maintenance burden when the retrieval interface changes.

The actor-specific semantics are taught by the system prompt, not by the tool schema. Front's prompt says: "Use `recall_memory` when past context would improve your response or your dispatch." Back's prompt says: "Call `recall_memory` early (STEP 1) if the task needs historical context the dispatch doesn't provide."

### Example Flow: Front-then-Back Recall Chain

```text
User: "Book the same hotel as last time"

FRONT (ReAct):
  Iteration 1: acknowledge("Looking up your previous stay!")
  Iteration 2: recall_memory("hotel booking history")
    -> observe: {memories: [{content: "Marriott, stayed June 2025"}]}
  Iteration 3: update_beliefs([{key: "preferred_hotel", value: "Marriott", confidence: 0.9}])
  Iteration 4: dispatch_task(
    intents=[{action: "book_hotel", params: {hotel: "Marriott"}, domain: "travel"}],
    reference_context={"same hotel as last time": "Marriott, stayed June 2025"})
  Iteration 5 (text): "Booking the Marriott for you -- same place as last June!"

BACK (ReAct):
  STEP 1: recall_memory("Marriott loyalty number and room preferences")
    -> observe: {memories: [{content: "Marriott Bonvoy #MB-847293, prefers king bed, high floor"}]}
  STEP 6: invoke_capability("tool.execute.hotel_booking", {
    hotel: "Marriott",
    loyalty: "MB-847293",
    room_pref: "king bed, high floor",
    ...
  })
  STEP 8: submit_result(complete, ...)
```

Front resolved "same hotel" -> "Marriott" using recall. Back enriched the booking with loyalty and room preferences using its own recall. Neither recall was redundant -- they served different cognitive functions at different points in the pipeline.

### Other Shared Tools

`recall_memory` is the only tool that appears in both actors' allowlists. All other tools are exclusive to one actor (see comparison table in Section 6.2). If future tools require dual-use, they should follow this same pattern: one schema, actor-specific semantics taught by prompt, timing differences documented here.

---

## 7.10 Latency Profile

ReAct iteration count determines total latency. Each iteration involves one LLM call (~200-500ms depending on output complexity) plus one tool execution (~10-200ms depending on tool type).

| Phase | Latency | What Happens |
| --- | --- | --- |
| **Front Iteration 1** | ~200ms | `acknowledge()` -> user sees ACK. Smallest possible output (one tool call). |
| **Front Iterations 2-4** | ~400ms each | Cognitive tools: `recall_memory`, `update_beliefs`, `dispatch_task`. User already has ACK. |
| **Front Final Iteration** | ~300ms | Text response -> user sees final message. |
| **Front Total** | **~1.5-2s** | User saw ACK at 200ms, full response at ~2s. Perceived latency is 200ms. |
| **Back Iterations 1-4** | ~500ms each | `discover_capabilities`, `invoke_capability`, observe, `submit_result`. Runs in background. |
| **Back Total** | **~2-4s** | Results arrive via bus -> Front presents when ready (Weave, Section 8). |

**Why perceived latency is ~200ms, not ~2s:** The user sees the ACK (iteration 1) within ~200ms. Everything after that runs while the user reads the acknowledgment. By the time they process the ACK, the full response and task dispatch are likely complete. This is the key latency advantage of ReAct over single-pass: the first visible output is a tiny one-tool-call response, not a 5-tool-call generation.

**Production parallel optimization:** With the batching strategy from Section 7.8, Front iterations 2-4 (cognitive tools) can be compressed. If `recall_memory` + `update_beliefs` + `update_scoreboard` run in parallel (reads + writes batched), iterations 2-4 collapse to ~500ms total instead of ~1200ms. Total Front latency drops to ~1s.

| Configuration | Front Total | Back Total | Notes |
| --- | --- | --- | --- |
| POC (sequential) | ~1.5-2.0s | ~2-4s | One tool per iteration |
| Production (parallel reads) | ~1.0-1.5s | ~2-3s | Reads batched, writes batched |
| Production (streaming ACK) | ~100-150ms perceived | ~2-3s | ACK streams token-by-token |

---

# 8. Task Model: Dispatch, Chain, Bundle, Cancel, Suspend

This section defines the complete task lifecycle: how tasks are created (dispatch), structured (single, bundled, chained), executed concurrently, cancelled, suspended for human input, and how their results merge back into conversation (Weave). Every task passes through a well-defined state machine tracked by `TaskStateEntry` in Session State (Section 5).

**Cross-references:**

- `TaskStateEntry` schema is defined in Section 5 (fields: `task_id`, `status`, `pending_hil`, `hil_suspensions_count`, etc.).
- `FSMTurnState.pending_results` and `FSMTurnState.cancelled_tasks` are defined in Section 4.
- Front's `dispatch_task` tool schema is in Section 6.1.
- Back's `submit_result` tool schema is in Section 6.2.
- `react_loop()` cancellation check is in Section 7.5 (ITEM #14).
- HITL behavioral rules (recovery, max rounds, timeouts) are in Section 9.

---

## 8.1 Task Lifecycle State Machine

Every task transitions through these states. The FSM (Section 4) updates `task_state[task_id].status` on each transition.

```text
                    dispatch_task()
                         |
                         v
                    DISPATCHED
                         |
                    Back picks up
                         |
                         v
                    IN_PROGRESS
                    /    |    \
                   /     |     \
                  v      v      v
           COMPLETED  SUSPENDED  FAILED
                         |        ^
                    user answers   |
                         |     cancel / budget_exhausted
                         v        |
                    IN_PROGRESS ---+
                    /         \
                   v           v
             COMPLETED       FAILED
```

**State definitions:**

| State | Meaning | Who sets it | Next states |
| --- | --- | --- | --- |
| `DISPATCHED` | Task created, waiting for Back to pick up | FSM (on `dispatch_task` tool call) | IN_PROGRESS |
| `IN_PROGRESS` | Back is executing (ReAct loop running) | FSM (on Back handler start) | COMPLETED, SUSPENDED, FAILED, CANCELLED |
| `SUSPENDED` | Back called `submit_result(needs_human)`. Waiting for user input. | FSM (on `task.suspended` event) | IN_PROGRESS (on resume), CANCELLED (on timeout/cancel) |
| `COMPLETED` | Back called `submit_result(complete)`. Results ready for presentation. | FSM (on `task.complete` event) | _(terminal)_ |
| `FAILED` | Back exhausted budget, encountered unrecoverable error, or was cancelled. | FSM (on `task.failed` event) | _(terminal)_ |
| `CANCELLED` | User requested cancellation and Back confirmed. | FSM (on `task.failed` with `reason=cancelled`) | _(terminal)_ |

---

## 8.2 Task Dispatch Schemas

### `TaskDispatch` (Bus Payload)

The payload for `k1.orchestration.task.dispatch.v1`. Created by the tool dispatcher when Front calls `dispatch_task()` (Section 6.1). The `task_id` is system-generated -- the LLM does not create IDs.

```python
@dataclass
class TaskDispatch:
    """Payload for k1.orchestration.task.dispatch.v1"""

    task_id: str
    # System-generated UUID. The tool dispatcher creates this when Front calls
    # dispatch_task(). The LLM receives the task_id in the tool result:
    #   dispatch_task(...) -> {task_id: "task-a7f3", status: "dispatched"}
    # This returned task_id is how the LLM references the task in subsequent
    # dispatch_task() calls (for chaining via depends_on).

    intents: list[TaskIntent]
    # One or more intents to execute. Single intent = simple task.
    # Multiple intents = bundled task (independent intents in one Back call).

    tier: str  # "LOW" | "MEDIUM" | "HIGH"
    # Complexity tier determines Back's iteration budget and tool allowlist.
    # Set by Front based on intent complexity.

    budget_hint: int
    # Max tool calls for Back. Derived from tier:
    #   LOW=4, MEDIUM=8, HIGH=12 (Section 6.2, BACK_MAX_ITERATIONS).

    reference_context: dict | None = None
    # Front-resolved pronoun and reference mappings.
    # Example: {"it": "Vineyard Inn, Sonoma", "those dates": "June 15-17, 2026"}
    # Back reads this in STEP 1 (ORIENT) to resolve references without
    # needing 20 turns of chat history. See Section 6.2, Reference Context Enrichment.

    safety_band: str = "AMBER"
    # GREEN / AMBER / RED. Copied from SS control.safety_band at dispatch time.
    # Back checks this in STEP 5 (SAFETY CHECK) before invoke_capability.
    # Default AMBER: assume side effects require approval unless stated otherwise.

    depends_on: str | None = None
    # Task ID this task depends on (chaining). If set, the orchestrator holds
    # this task until the dependency completes, then hydrates params.

    context_snapshot: dict | None = None
    # Relevant SS sections at dispatch time. Optional -- Back also reads SS
    # directly, but this captures the snapshot for audit/replay.


@dataclass
class TaskIntent:
    """A single intent within a task dispatch."""

    action: str
    # What to do. Natural language ("book hotel") or known capability name
    # ("tool.execute.hotel_booking"). Back uses discover_capabilities() if
    # the action is natural language.

    params: dict
    # Structured parameters for the action.
    # May contain dependency references for chained tasks: "$prev.result.address"

    domain: str | None = None
    # Domain hint for capability discovery: travel, health, productivity, etc.

    urgency: str = "normal"
    # normal / urgent / background. Affects bus priority:
    #   urgent -> Priority.URGENT, normal -> Priority.INTERACTIVE,
    #   background -> Priority.BACKGROUND.
```

### `TaskFailed` (Bus Payload) -- ITEM #12

The payload for `k1.orchestration.task.failed.v1`. This is the richest event payload in the taxonomy. Previously buried in a table footnote in Section 3 -- elevated here as a proper schema.

```python
@dataclass
class TaskFailed:
    """Payload for k1.orchestration.task.failed.v1

    The most diagnostic event in the system. Carries enough context for
    Front to explain the failure gracefully and for observability to
    diagnose root cause without log diving.
    """

    task_id: str
    # Which task failed.

    reason: str
    # Why it failed. Enum-like but extensible:
    #   "budget_exhausted"    -- max_iterations reached without submit_result
    #   "cancelled"           -- user cancelled via Front -> task.cancel
    #   "capability_not_found" -- discover_capabilities returned nothing
    #   "capability_failed"   -- invoke_capability returned error after retry
    #   "workflow_failed"     -- execute_workflow returned error
    #   "agent_failed"        -- spawn_via_fabric agent failed
    #   "timeout"             -- external call timed out
    #   "internal_error"      -- unexpected exception in Back handler

    error_code: str | None = None
    # Machine-readable error code from the failed capability, if available.
    # Example: "BOOKING_UNAVAILABLE", "RATE_LIMITED", "AUTH_EXPIRED"

    tool_history: list[dict] = field(default_factory=list)
    # Summary of tool calls made before failure. Each entry:
    #   {tool: str, args_summary: str, result_summary: str, success: bool}
    # Front uses this to tell the user what was attempted.
    # Observability uses this for root cause analysis.

    partial_results: list[dict] = field(default_factory=list)
    # Any successful results obtained before the failure.
    # Example: hotel search succeeded but booking failed.
    # Front can present partial results: "I found the hotel but couldn't book it."

    retries_attempted: int = 0
    # How many retries Back tried before giving up.
    # Max 1 retry per capability (2 total attempts, Section 6.2 system prompt).

    last_error_detail: str | None = None
    # Human-readable error detail from the last failed operation.
    # Example: "Vineyard Inn has no availability for June 15-17."
    # Front translates this into conversational language (never shown raw).
```

### `TaskComplete` (Bus Payload)

The payload for `k1.orchestration.task.complete.v1`. Produced by `back_handler` (Section 6.2) from `ReactResult.data` when `submit_result(complete)` is called.

```python
@dataclass
class TaskComplete:
    """Payload for k1.orchestration.task.complete.v1"""

    task_id: str
    # Which task completed.

    final_answer: str
    # Technical summary. NOT user-facing text. Example:
    #   "Booked Vineyard Inn, Sonoma. 2 nights, June 15-17. $598 total."
    # Front rewrites this in its own voice for the user.

    results: list[dict]
    # Structured data the presenter needs. Each object has consistent keys
    # within the result set. Front decides what to show and how.

    artifacts_created: list[dict] = field(default_factory=list)
    # Durable outputs that persist in task_artifacts. Each entry:
    #   {type: str, summary: str, data: dict}
    # FSM writes these to SS task_artifacts section.

    completed_before_cancel: bool = False
    # Race condition flag. If True, the task completed after a cancel
    # was emitted but before Back could check cancellation_check().
    # Front must decide: present result + offer to undo, or discard.
```

### `TaskSuspended` (Bus Payload)

The payload for `k1.orchestration.task.suspended.v1`. Produced when `submit_result(needs_human)` is called.

```python
@dataclass
class TaskSuspended:
    """Payload for k1.orchestration.task.suspended.v1"""

    task_id: str
    # Which task suspended.

    hil_type: str
    # "clarification" | "approval" | "selection"
    # See Section 9 (HITL Protocol) for the three shapes.

    question: str
    # Structured question for the user. Front translates this into
    # natural conversation -- never shown raw.

    options: list[dict] | None = None
    # For selection HIL: the choices Back found.
    # Each option: {id: int, label: str, ...extra_fields}

    side_effects: str | None = None
    # For approval HIL: what will happen if approved.
    # Example: "Will charge $598 to Visa ending 4242."

    safety_band: str | None = None
    # Current safety band for the suspended action.

    findings_so_far: list[dict] = field(default_factory=list)
    # Tool results accumulated before suspension. Preserved in
    # FSMTurnState so Back can resume without re-executing.
```

---

## 8.3 Single Intent (Simple Task)

The most common pattern. One user action, one dispatch, one Back execution.

```text
User: "What's the weather tomorrow?"

FRONT (ReAct):
  Iteration 1: acknowledge("Checking the weather!")
  Iteration 2: dispatch_task(
    intents=[{action: "get weather forecast", params: {date: "tomorrow"}, domain: "weather"}],
    tier="LOW")
    -> tool result: {task_id: "task-a7f3", status: "dispatched"}
  Iteration 3 (text): "Looking that up for you now!"

BACK (ReAct, task-a7f3):
  Iteration 1: invoke_capability("tool.execute.weather_forecast", {date: "2026-02-21"})
    -> observe: {success: true, data: {temp: 72, condition: "sunny", wind: "5mph"}}
  Iteration 2: submit_result(complete,
    final_answer="Weather for Feb 21: 72F, sunny, 5mph wind.",
    results=[{date: "2026-02-21", temp_f: 72, condition: "sunny", wind_mph: 5}])

BUS: k1.orchestration.task.complete.v1 -> FSM -> Front (PRESENT mode)

FRONT (PRESENT mode):
  "Tomorrow's looking gorgeous -- 72 degrees and sunny with barely any wind!"
```

---

## 8.4 Bundled Intents (Multiple Independent Actions)

When the user expresses multiple independent actions in one message, Front bundles them into a single dispatch. Back executes each sequentially in its ReAct loop, observing results between invocations.

```text
User: "Book the hotel AND search for restaurants nearby"

FRONT:
  dispatch_task(
    intents=[
      {action: "book hotel", params: {hotel: "Vineyard Inn", dates: "June 15-17"}, domain: "travel"},
      {action: "search restaurants", params: {near: "Vineyard Inn", cuisine: "any"}, domain: "travel"},
    ],
    tier="MEDIUM",
    reference_context={"the hotel": "Vineyard Inn, Sonoma"})

BACK (ReAct, sequential iterations):
  Iteration 1: invoke_capability("tool.execute.hotel_booking", {hotel: "Vineyard Inn", ...})
    -> observe: {success: true, confirmation: "ACM-847293"}
  Iteration 2: invoke_capability("tool.execute.restaurant_search", {location: "near Vineyard Inn"})
    -> observe: {success: true, data: [{name: "Oenotri", cuisine: "Italian", ...}, ...]}
  Iteration 3: submit_result(complete, combined results from both invocations)
```

**Why single dispatch, not two:** The user expressed both intents in one breath. Splitting them creates unnecessary overhead (two dispatches, two completions, two Weave presentations). Back handles multiple `invoke_capability()` calls in its ReAct loop, observing each before proceeding.

### Bundle vs. Chain Decision Protocol

Front decides based on linguistic cues and semantic dependency:

| User pattern | Intent relationship | Front action |
| --- | --- | --- |
| "Book hotel AND search restaurants" | Independent (no data dependency) | Bundle: single dispatch, multiple intents |
| "Book hotel THEN find restaurants near it" | Dependent ("near it" requires hotel address) | Chain: two dispatches, `depends_on` link |
| "Book hotel, search restaurants, and remind me about mom's birthday" | Mixed: hotel+restaurants independent, birthday independent | Bundle all 3 (no dependencies between any) |
| "Book hotel, then use the confirmation number to book a spa" | Dependent (spa needs confirmation number) | Chain: hotel first, spa depends_on hotel |

Front's system prompt (Section 6.1, DISPATCH_RULES) teaches these patterns via in-context examples.

### Multi-Intent In-Context Examples (From System Prompt)

```text
== DISPATCH EXAMPLES ==

Example 1 -- Single intent:
User: "Find me hotels in Napa"
  acknowledge("Searching for hotels in Napa!")
  dispatch_task(intents=[{action: "search hotels", params: {location: "Napa"}, domain: "travel"}])

Example 2 -- Bundled independent intents:
User: "Book the hotel and search for restaurants nearby"
  acknowledge("On it! Booking and searching restaurants...")
  dispatch_task(intents=[
    {action: "book hotel", params: {hotel: "Vineyard Inn", dates: "June 15-17"}, domain: "travel"},
    {action: "search restaurants", params: {near: "Vineyard Inn"}, domain: "travel"}
  ])

Example 3 -- Chained dependent intents:
User: "Book the hotel then find restaurants near it"
  acknowledge("Booking first, then I'll find restaurants nearby!")
  dispatch_task(intents=[{action: "book hotel", params: {hotel: "Vineyard Inn"}}])
    -> tool result: {task_id: "task-a7f3", status: "dispatched"}
  dispatch_task(
    intents=[{action: "search restaurants", params: {near: "$prev.result.address"}}],
    depends_on="task-a7f3")

Example 4 -- Conversational + action:
User: "Ugh I'm exhausted from the gym. Can you just book that restaurant?"
  acknowledge("Long day! I'll book it right now.")
  refine_affect(emotion="tired", valence=-0.3, arousal=0.3, confidence=0.8)
  dispatch_task(
    intents=[{action: "book restaurant", params: {restaurant: "Oenotri"}}],
    reference_context={"that restaurant": "Oenotri, Napa"})

Example 5 -- Pure conversation, no dispatch:
User: "How was the weather today?"
  acknowledge("It was gorgeous! Sunny and 72 degrees in Napa.")
  [NO dispatch_task -- this is just conversation]
```

---

## 8.5 Chained Tasks (Sequential with Dependencies)

When the second task depends on the first task's results, Front dispatches two separate tasks with a `depends_on` link. The orchestrator holds the dependent task until the dependency completes, then hydrates its parameters.

```text
User: "Book the hotel and then find restaurants near it"

FRONT:
  dispatch_task(intents=[{action: "book hotel", params: {hotel: "Vineyard Inn"}}])
    -> tool result: {task_id: "task-a7f3", status: "dispatched"}
  dispatch_task(
    intents=[{action: "search restaurants", params: {near: "$prev.result.address"}}],
    depends_on="task-a7f3")
    -> tool result: {task_id: "task-b2c8", status: "dispatched", held: "waiting for task-a7f3"}

ORCHESTRATOR:
  1. task-a7f3 dispatched to Back -> executes -> task.complete:
     {task_id: "task-a7f3", results: [{address: "1234 Vineyard Lane, Napa, CA", ...}]}
  2. TaskDependencyQueue.on_task_complete("task-a7f3", result)
     -> hydrates task-b2c8: "$prev.result.address" -> "1234 Vineyard Lane, Napa, CA"
  3. Hydrated task-b2c8 dispatched to Back -> executes -> task.complete

FRONT (PRESENT mode, after both complete):
  "The Vineyard Inn is booked! And I found 4 great restaurants nearby on Vineyard Lane..."
```

### `TaskDependencyQueue`

Lives in the orchestrator/FSM layer -- NOT in Back. Back is a stateless ReAct actor that receives pre-hydrated dispatches. The queue persists across turns because chained task #2 may complete turns after task #1 dispatches.

```python
class TaskDependencyQueue:
    """Holds tasks waiting for dependencies to resolve.

    Lives in the orchestrator/FSM layer. Back never sees this -- it receives
    fully hydrated TaskDispatch payloads with all parameter references resolved.
    """

    pending: dict[str, list[TaskDispatch]] = field(default_factory=dict)
    # depends_on task_id -> [waiting TaskDispatch payloads]

    completed_results: dict[str, dict] = field(default_factory=dict)
    # task_id -> TaskComplete payload (for hydration lookups)

    def enqueue(self, task: TaskDispatch):
        """Add a task with unresolved dependency."""
        dep_id = task.depends_on
        if dep_id in self.completed_results:
            # Dependency already completed -- hydrate and dispatch immediately
            hydrated = self._hydrate_params(task, self.completed_results[dep_id])
            self._dispatch(hydrated)
        else:
            # Dependency not yet complete -- hold in queue
            self.pending.setdefault(dep_id, []).append(task)

    def on_task_complete(self, task_id: str, result: dict):
        """Called when any task completes. Checks for waiting dependents."""
        self.completed_results[task_id] = result
        if task_id in self.pending:
            for waiting_task in self.pending.pop(task_id):
                hydrated = self._hydrate_params(waiting_task, result)
                self._dispatch(hydrated)

    def _hydrate_params(self, task: TaskDispatch, dep_result: dict) -> TaskDispatch:
        """Replace $prev.result.field references with actual values from dependency result."""
        for intent in task.intents:
            for key, value in intent.params.items():
                if isinstance(value, str) and value.startswith("$prev.result."):
                    field_path = value[len("$prev.result."):]  # e.g., "address"
                    resolved = self._resolve_path(dep_result.get("results", [{}])[0], field_path)
                    if resolved is not None:
                        intent.params[key] = resolved
                    # If resolution fails, leave the raw reference -- Back can
                    # call submit_result(needs_human, clarification) as fallback.
        return task

    def _resolve_path(self, obj: dict, path: str):
        """Resolve a dot-separated path into a nested dict. Returns None if not found."""
        parts = path.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def _dispatch(self, task: TaskDispatch):
        """Emit the hydrated task to the bus for Back to pick up."""
        emit(Envelope(
            topic="k1.orchestration.task.dispatch.v1",
            payload=dataclasses.asdict(task),
            priority=Priority.INTERACTIVE,
        ))
```

### Parameter Reference Syntax

The LLM uses `$prev.result.<field>` to reference fields from the dependency's result. The tool dispatcher (not the LLM) generates `task_id` values. The LLM learns the task_id from the `dispatch_task` tool result and uses it as `depends_on`.

| Reference | Resolves to | Source |
| --- | --- | --- |
| `$prev.result.address` | First result object's `address` field | `TaskComplete.results[0]["address"]` |
| `$prev.result.confirmation_id` | First result object's `confirmation_id` | `TaskComplete.results[0]["confirmation_id"]` |
| `$prev.result.price` | First result object's `price` | `TaskComplete.results[0]["price"]` |

**Why `$prev.result` and not `$task-a7f3.result`:** The LLM always chains to the immediately preceding dispatch in the same turn. Cross-turn chaining or chaining to a non-previous task is not supported in the POC. If future requirements demand it, the syntax extends to `$<task_id>.result.<field>`.

**Hydration failure handling:** If `_resolve_path` returns `None` (field not found in dependency result), the raw `$prev.result.field` string is left in params. When Back reads this un-hydrated reference, it will not recognize it as a valid parameter and will call `submit_result(needs_human, clarification)` to ask for the missing value. This is a graceful degradation, not a crash.

---

## 8.6 Concurrent Tasks (Different Turns)

Tasks dispatched in different turns run independently. They cannot be bundled (Front didn't know about the second when it dispatched the first).

```text
Turn 1: User: "Search for hotels in Napa"
  -> Front dispatches task-001 (search hotels)
  -> Back starts executing task-001

Turn 2 (while task-001 running): User: "Also check the weather for next week"
  -> Front dispatches task-002 (weather check)
  -> task-002 queues behind task-001
```

**POC behavior (single Back):** Tasks execute serially. task-002 waits in the FSM's dispatch queue until task-001 completes. Results arrive sequentially and are presented via Weave (Section 8.10).

**Production behavior (BackPool):** Each task gets its own Back actor from the pool. Both execute in parallel. Both emit `task.complete`. The WeaveBatcher (Section 8.10) handles concurrent results.

**The interface is identical either way.** Front does not know or care whether Back is a single actor or a pool. It dispatches to `k1.orchestration.task.dispatch.v1` and receives `k1.orchestration.task.complete.v1`. The bus handles routing. This is the key architectural insight: the POC's serial execution and production's parallel execution differ only in Back's multiplicity, not in the protocol.

---

## 8.7 Cancellation Flow and Contract

User changes their mind while Back is executing. Front preempts.

### Cancellation Sequence

```text
T=0ms    User: "Book the Vineyard Inn."
T=200ms  Front: acknowledge("On it!") + dispatch_task(book hotel, ...)
T=210ms  Back picks up task-042. Calls invoke_capability(hotel_search) to verify availability.

T=2000ms User: "Wait no, cancel that. Let's do the Marriott instead."
T=2200ms Front handler fires on new user.input.
         Front reads task_state: task-042 status=IN_PROGRESS.
         Front recognizes cancellation intent.
         -> acknowledge("Got it, cancelling the Vineyard Inn. Switching to the Marriott!")
         -> update_beliefs({accommodation_preference: "Marriott"})
         -> Emits k1.orchestration.task.cancel.v1:
              payload={task_id: "task-042", reason: "user_changed_mind"}
              priority=URGENT
         -> dispatch_task(intents=[{action: "book hotel", params: {hotel: "Marriott"}}])

T=2210ms FSM sets FSMTurnState.cancellation_requested = True (Section 4).
         Back's react_loop() checks cancellation_check() at top of next iteration.
         -> If Back is between iterations: exits with ReactResult(status="cancelled").
         -> If Back is mid-HTTP-call: cannot abort, but will NOT proceed to next tool.

T=2220ms back_handler emits k1.orchestration.task.failed.v1:
           payload=TaskFailed(
             task_id="task-042",
             reason="cancelled",
             tool_history=[{tool: "invoke_capability", args_summary: "hotel_search(Vineyard Inn)",
                           result_summary: "in_progress", success: false}],
             partial_results=[],
             retries_attempted=0)

T=2230ms Back picks up new dispatch for Marriott. Executes normally.
```

### Cancellation Contract

| Rule | Detail |
| --- | --- |
| **Best-effort, not guaranteed** | If the booking call already returned success before cancel arrived, it is too late. The task completes with `completed_before_cancel=True`. |
| **Check boundary** | Back checks `cancellation_check()` between ReAct iterations (Section 7.5), NOT mid-tool-call. HTTP calls in flight complete but Back does not proceed to the next tool. |
| **Dedup via `cancelled_tasks`** | FSM adds `task_id` to `FSMTurnState.cancelled_tasks` (Section 4) when cancel is emitted. If `task.complete` arrives for a task in `cancelled_tasks`, FSM handles the race (see below). |
| **Artifacts from cancelled tasks** | If Back wrote artifacts (via `k1.session.artifact.created.v1`) before cancel landed, FSM marks those artifacts as `superseded=True` in `task_artifacts`. They remain for audit but are not presented to the user. |
| **Status transitions** | `IN_PROGRESS -> CANCELLED` (normal). `IN_PROGRESS -> COMPLETED` (race condition, see below). |

### Cancel/Complete Race Condition

If `task.complete` arrives after `task.cancel` was emitted but before Back checked `cancellation_check()`:

```text
FSM checks:
  Is task_id in cancelled_tasks?
    YES -> Was completed_before_cancel == True?
      YES -> Present to user with caveat:
             "Actually, the Vineyard Inn booking went through before I could cancel it.
              Want me to undo it?"
      NO  -> Discard the completion. Present only the cancellation confirmation.
    NO -> Normal completion. Present via PRESENT mode or Weave.
```

This race is handled by `FSMTurnState.cancelled_tasks` (Section 4). The set persists for the duration of the session. Completed-before-cancel results are rare but architecturally important -- they prevent silent data loss.

---

## 8.8 Suspension Flow and Contract

Back encounters ambiguity it cannot resolve alone. It suspends execution and requests human input through Front.

### Suspension Sequence

```text
T=0ms    User: "Book the Vineyard Inn."
T=200ms  Front: acknowledge + dispatch_task(book hotel, target="Vineyard Inn")

T=500ms  Back picks up task-042. Calls invoke_capability(hotel_search, name="Vineyard Inn").
         Returns 3 results:
           1. Vineyard Inn, Napa Valley -- $298/night
           2. Vineyard Inn, Sonoma -- $185/night
           3. The Vineyard Inn & Spa, St. Helena -- $420/night
         Back cannot decide which one the user meant.

T=700ms  Back calls submit_result(needs_human, selection):
         -> ReactResult(status="suspended", data={
              hil_type: "selection",
              question: "Multiple 'Vineyard Inn' properties found. Which one?",
              options: [
                {id: 1, label: "Vineyard Inn, Napa Valley", price: "$298/night"},
                {id: 2, label: "Vineyard Inn, Sonoma", price: "$185/night"},
                {id: 3, label: "The Vineyard Inn & Spa, St. Helena", price: "$420/night"},
              ],
              findings_so_far: [hotel_search_results]
            })

T=710ms  back_handler emits k1.orchestration.task.suspended.v1 with TaskSuspended payload.
         FSM updates task_state[task-042].status = SUSPENDED.
         FSM stores pending_hil in task_state[task-042].pending_hil (Section 5).
         FSM preserves Back's ReAct message history in FSMTurnState for resume.

T=720ms  Front invoked in HITL_RELAY mode (Section 6.1). Translates structured HITL:
         -> "I found a few places called Vineyard Inn! Which one were you thinking of?
             1. Vineyard Inn in Napa Valley -- $298/night
             2. Vineyard Inn in Sonoma -- $185/night
             3. The Vineyard Inn & Spa in St. Helena -- $420/night"

T=5000ms User: "The one in Sonoma."
T=5200ms Front invoked in HITL_RESOLVE mode.
         Front resolves: user picked option 2 (Sonoma).
         -> update_beliefs({accommodation_target: "Vineyard Inn, Sonoma"})
         -> Emits k1.orchestration.task.resume.v1:
              payload={task_id: "task-042", resolution: {selected_option: 2,
                        target: "Vineyard Inn, Sonoma"}}
         -> acknowledge("Great choice! Booking the Sonoma one now.")

T=5210ms FSM updates task_state[task-042].status = IN_PROGRESS.
         FSM increments task_state[task-042].hil_suspensions_count.
         Back handler receives task.resume.
         ReAct message history replayed from FSMTurnState (findings_so_far).
         Back proceeds directly to invoke_capability(hotel_booking, {name: "Vineyard Inn, Sonoma"}).
         -> submit_result(complete) -> task.complete
```

### Suspension Contract

| Rule | Detail |
| --- | --- |
| **ReAct history preserved** | Back's ReAct message history (all iterations before `submit_result(needs_human)`) is stored in `FSMTurnState`. On resume, this history is restored as `findings_so_far` so Back continues exactly where it left off. No repeated work. |
| **Max suspensions: 2 per task** | `TaskStateEntry.hil_suspensions_count` tracks this (Section 5). On the third ambiguity, Back picks the best option and notes reasoning in `final_answer`. This prevents infinite ping-pong. |
| **Timeout** | If the user does not respond within a configurable timeout (default: 120s), the FSM auto-cancels the suspended task. `task_state[task_id].status` transitions to `CANCELLED` with `reason="hil_timeout"`. |
| **`pending_hil` persistence** | The `TaskStateEntry.pending_hil` field (Section 5) stores the serialized HITL request. If Front reconnects after a crash, the FSM reads `pending_hil` and re-presents the question. This survives process restarts. |
| **Front translates, never relays raw** | Front in HITL_RELAY mode (Section 6.1) receives the structured `TaskSuspended` payload and rewrites it in natural conversational language. Raw JSON, option IDs, and technical field names are never shown to the user. |
| **Suspension during chained tasks** | If task A (dependency) suspends, task B (dependent) remains in `TaskDependencyQueue`. When task A resumes and completes, task B is hydrated and dispatched normally. |

---

## 8.9 Task Resume Payload

The payload for `k1.orchestration.task.resume.v1`. Emitted by Front when the user answers a HITL question.

```python
@dataclass
class TaskResume:
    """Payload for k1.orchestration.task.resume.v1"""

    task_id: str
    # Which suspended task to resume.

    resolution: dict
    # The user's answer, structured by hil_type:
    #
    # For "selection":
    #   {selected_option: int, target: str}
    #   Example: {selected_option: 2, target: "Vineyard Inn, Sonoma"}
    #
    # For "approval":
    #   {approved: bool}
    #   Example: {approved: True}
    #
    # For "clarification":
    #   {answer: str, resolved_params: dict}
    #   Example: {answer: "June 15-17", resolved_params: {dates: "June 15-17"}}
```

### Resume Context Assembly

When Back receives `task.resume`, it gets a different context from a fresh dispatch (Section 6.2, Scenario 2):

```python
BackContext_TaskResume = {
    # Same as TaskDispatch context PLUS:
    "findings_so_far": "You previously searched and found 3 Vineyard Inn properties. "
                       "The user selected: Vineyard Inn, Sonoma ($185/night).",
    "resolution": resolution_payload,
    "instruction": "Continue from where you left off. Do NOT re-execute "
                   "the search. Proceed directly to booking with the resolved target.",
}
```

The `findings_so_far` field is assembled from the preserved ReAct message history. Back sees its own prior tool calls and observations, so it knows what was already done and does not repeat work.

---

## 8.10 The Weave Protocol

When `task.complete` arrives while Front was handling something unrelated, the results must merge naturally into the conversation. This is the Weave.

### The Problem

If 3 tasks complete while the user is chatting, Front should NOT send 3 sequential messages:

```text
User: "How was your day?"
Front: "Sounds great! Tell me more."
Front: "By the way, I found 5 hotels in Napa."           <- disruptive
Front: "Also, the weather next week looks sunny."          <- more disruptive
Front: "Oh, and I booked your dentist for March 5th."     <- terrible UX
```

### The Solution: Weave Mode + Batch Window

The FSM detects pending results and invokes Front in WEAVE mode (Section 4, Section 6.1) with ALL pending results in a single call:

```text
Front: "Alright, a few things came through while we were chatting --
 I found 5 great hotels in Napa, the weather looks perfect for
 next week, and your dentist appointment is confirmed for March 5th.
 Want details on any of these?"
```

### Weave Prompt Injection

When the FSM transitions to WEAVING state (Section 4), it invokes Front with a scenario_data block containing the batched results:

```python
SCENARIO_DATA_TEMPLATES["WEAVE"] = """
== ASYNC RESULTS ==
While you were chatting with the user, {count} background task(s) completed.

{results_block}

The user's last message was about: {current_thread_summary}

Your job: Respond to the user's current topic first, then naturally transition
to presenting the async result(s). Do not ignore either context.
If multiple results: present them as a unified summary, not separate messages.
"""
```

### FSM Rules for Weave Delivery

| Front state when `task.complete` arrives | Behavior |
| --- | --- |
| LISTENING (idle) | Deliver immediately. Front presents result directly in PRESENT mode (no Weave needed). |
| RESPONDING (Front mid-ReAct-loop) | Queue in `FSMTurnState.pending_results`. Deliver after Front's loop exits. |
| COMPANIONING (user chatting, Back working) | Queue in `pending_results`. Deliver after Front finishes current response. Weave prompt injected. |
| DELIVERING (Front already presenting another result) | Queue. Chain delivery: present first result, then present second in a follow-up Weave. |

### `FSMTurnState.pending_results` Lifecycle

1. `task.complete` arrives -> FSM appends `TaskComplete` payload to `FSMTurnState.pending_results` (Section 4).
2. After Front finishes its current response -> FSM checks `pending_results`.
3. If non-empty -> FSM starts `WeaveBatcher` batch window (500ms).
4. Batch window collects any additional `task.complete` events that arrive within 500ms.
5. After window closes -> FSM invokes Front in WEAVE mode with ALL batched results.
6. Front emits `k1.response.final.v1` with woven response.
7. `pending_results` entries removed.
8. Repeat until `pending_results` is empty.

---

## 8.11 WeaveBatcher Implementation

Batches pending task results to prevent jarring sequential messages. The 500ms window matches the `DeltaAggregator` window from the production spec (Section 5).

```python
class WeaveBatcher:
    """Batches pending task results for unified Front presentation.

    The 500ms batch window prevents the scenario where 3 tasks complete
    within 300ms and Front sends 3 separate messages. Instead, all 3
    arrive in one WEAVE invocation.

    Lives in the FSM controller layer. Operates directly on
    FSMTurnState.pending_results (Section 4).
    """

    BATCH_WINDOW_MS: int = 500  # Matches DeltaAggregator window

    def __init__(self, fsm_state: FSMTurnState):
        self._fsm_state = fsm_state
        self._batch_timer: asyncio.Task | None = None

    async def on_task_complete(self, result: TaskComplete):
        """Called when task.complete arrives. Starts or extends batch window."""
        self._fsm_state.pending_results.append(result)

        # Reset batch timer (extend window for late arrivals)
        if self._batch_timer and not self._batch_timer.done():
            self._batch_timer.cancel()
        self._batch_timer = asyncio.create_task(self._flush_after_delay())

    async def _flush_after_delay(self):
        """Wait for batch window, then trigger Weave if results pending."""
        await asyncio.sleep(self.BATCH_WINDOW_MS / 1000)
        if self._fsm_state.pending_results:
            await self._invoke_front_weave()

    async def _invoke_front_weave(self):
        """Invoke Front LLM with all batched results in one call."""
        results = list(self._fsm_state.pending_results)
        self._fsm_state.pending_results.clear()

        # Build weave envelope for FSM to route to Front
        weave_envelope = Envelope(
            topic="k1.internal.weave.batch.v1",
            payload={
                "results": [dataclasses.asdict(r) for r in results],
                "count": len(results),
                "current_thread": self._get_active_thread(),
            },
            priority=Priority.INTERACTIVE,
        )
        # FSM routes this to Front handler, which invokes in WEAVE mode
        await self._fsm_state.enqueue_for_front(weave_envelope)

    def _get_active_thread(self) -> str:
        """Get the current conversation thread name from narrative_active."""
        # Delegate to SS -- the FSM has access
        return "general conversation"  # Placeholder; real impl reads SS
```

**`k1.internal.weave.batch.v1` is an internal-only topic.** It does not appear in the external topic taxonomy (Section 3). It exists only as an FSM-internal routing mechanism to trigger Front's WEAVE mode. External consumers never see it.

### WeaveBatcher Edge Cases

| Scenario | Behavior |
| --- | --- |
| 1 result, no active conversation | No batching needed. Direct PRESENT mode (not Weave). |
| Results arrive DURING Front's ReAct loop | Queued in `pending_results`. Batch window starts after Front's loop exits. |
| User sends new input during batch window | User input takes priority (URGENT). Batch window continues. After Front handles user input, pending results are checked again. |
| Batch window expires with 0 results | Timer cancelled. No action. (Results were already presented or cancelled.) |
| Result arrives after batch flush | New batch window starts for the late arrival. |
| Cancelled task result arrives | FSM checks `cancelled_tasks` before adding to `pending_results`. Cancelled results are discarded (or handled via completed_before_cancel, Section 8.7). |

### Batch Window Timing Interaction with FrontLock

The batch timer starts AFTER Front's current response is emitted (FrontLock releases). The sequence:

```text
1. Front is mid-ReAct-loop (FrontLock held).
2. task.complete arrives -> queued in pending_results.
3. Front's loop finishes -> response emitted -> FrontLock releases.
4. FSM checks pending_results -> non-empty -> starts WeaveBatcher timer (500ms).
5. More results may arrive during the 500ms window -> added to pending_results.
6. Timer fires -> WeaveBatcher invokes Front in WEAVE mode.
7. Front's WEAVE response emitted -> FrontLock releases again.
8. FSM checks pending_results again -> empty -> done.
```

This prevents the WeaveBatcher from trying to invoke Front while Front is already mid-loop (which would violate FrontLock serialization).

---

## 8.12 Design Decisions and Gap Resolutions

Decisions made during the consolidation of old Sections 6, 17, 18, and 26.8 into this unified task model.

| Decision | Resolution | Rationale |
| --- | --- | --- |
| **`reference_context` location** | Field on `TaskDispatch`, not on `TaskIntent` | Reference context applies to the entire dispatch, not individual intents. Front resolves references once for the whole user message. |
| **`safety_band` location** | Field on `TaskDispatch` with default `"AMBER"` | Back needs safety band for STEP 5 (safety check). Copying it from SS at dispatch time means Back doesn't need to read SS `control` section separately. |
| **`task_id` generation** | Tool dispatcher generates UUID, returns in tool result | LLMs cannot reliably generate UUIDs. The dispatcher creates the ID and returns it. The LLM uses the returned ID for `depends_on` in chained dispatches. |
| **Parameter reference syntax** | `$prev.result.<field>` | Simple, LLM-friendly. Only references the immediately preceding dispatch in the same turn. Extensible to `$<task_id>.result.<field>` if needed. |
| **`TaskDependencyQueue` ownership** | Orchestrator/FSM layer, not Back | Back is stateless per-task. Cross-task dependency management is a control-plane concern. Back receives pre-hydrated dispatches. |
| **Concurrent task execution (POC)** | FSM serializes to single Back | POC simplicity. The bus interface is identical for serial and parallel execution. BackPool is a production optimization, not a protocol change. |
| **Max HITL suspensions** | 2 per task (matching Back system prompt) | Old doc disagreed (Section 6.6 said 1, system prompt said 2). Resolved: 2 suspensions. On third ambiguity, Back picks best option. `hil_suspensions_count` in `TaskStateEntry` tracks this. |
| **Cancelled task artifacts** | Marked `superseded=True`, not deleted | Audit trail preservation. Front skips superseded artifacts in PRESENT mode. |
| **WeaveBatcher timing** | Batch timer starts after FrontLock releases | Prevents concurrent Front invocations. FrontLock serialization is the single-writer guarantee for the response channel. |
| **`k1.internal.weave.batch.v1`** | Internal-only topic, not in external taxonomy | FSM routing mechanism only. No external consumer needs to subscribe. |

---

# 9. HITL Protocol

Human-in-the-loop is the most safety-critical protocol in the system. Every action that changes external state -- books a hotel, sends a message, charges a card -- passes through HITL before execution. This section defines the complete HITL lifecycle: the three shapes, the closed-cycle flow through both LLM loops, the safety escalation rules, the crash recovery protocol, and the behavioral contracts that govern every touch point between Back, FSM, Front, and the user.

**What this section owns:**

- The three HITL shapes (clarification, approval, selection) and when each triggers.
- The closed-cycle flow: Back suspends -> bus -> FSM -> Front -> user -> Front -> bus -> FSM -> Back resumes.
- Safety band escalation rules (who decides, when approval is mandatory).
- Front LLM behavior during HITL (translation, not relay).
- Crash recovery protocol (ITEM #15 -- what happens if Back dies mid-suspension).
- Timeout and round limits.
- K1 HITL architecture layer mapping.

**What this section does NOT own (cross-references):**

- `TaskSuspended` / `TaskResume` payload schemas -> Section 8.2, 8.9.
- `TaskStateEntry.pending_hil` / `hil_suspensions_count` fields -> Section 5.
- `FSMTurnState` ephemeral state -> Section 4.
- Front `HITL_RELAY` / `HITL_RESOLVE` mode prompt templates -> Section 6.1.
- Back `submit_result(needs_human)` tool -> Section 6.2.
- `react_loop()` suspension exit path -> Section 7.
- Suspension flow sequence (timeline) -> Section 8.8.

---

## 9.1 The HITL Closed Cycle

Every HITL interaction is a closed loop that touches both LLM actors, the FSM, the bus, and the user. No component is skipped. No shortcut exists. The loop must close for the task to proceed.

```text
                          THE HITL CLOSED CYCLE
                          =====================

    +------------------+                              +------------------+
    |                  |   submit_result(needs_human)  |                  |
    |   BACK LLM       |----(1)---->  ReactResult     |   BACK HANDLER   |
    |   (ReAct Loop)   |              status=suspended |   (Section 6.2)  |
    |                  |                               |                  |
    +------------------+                               +--------+---------+
                                                                |
                                                           (2)  | emit
                                                                v
    +------------------------------------------------------------------+
    |                        EVENT BUS                                  |
    |   topic: k1.orchestration.task.suspended.v1                      |
    |   payload: TaskSuspended {task_id, hil_type, question, options}   |
    |   priority: INTERACTIVE                                          |
    +------------------------------------------------------------------+
                          |                                   ^
                     (3)  | subscribe                         |  (8) emit
                          v                                   |
    +------------------+                              +-------+----------+
    |                  |                              |                   |
    |   FSM            |----(4)---->  CLARIFYING_     |   FSM             |
    |   (Section 4)    |              WORKER state    |   (Section 4)     |
    |                  |                              |                   |
    |  - Store pending_hil in TaskStateEntry          |  - Update status  |
    |  - Preserve Back ReAct history                  |    IN_PROGRESS    |
    |  - Set FSM state = CLARIFYING_WORKER            |  - Increment      |
    |  - Invoke Front in HITL_RELAY mode              |    hil_suspensions|
    |                  |                              |  - Emit task.     |
    +--------+---------+                              |    resume.v1      |
             |                                        +------------------+
        (5)  | invoke                                         ^
             v                                                |
    +------------------+                              +-------+----------+
    |                  |    text response              |                  |
    |   FRONT LLM      |   (no tools in HITL_RELAY)   |   FRONT LLM      |
    |   (HITL_RELAY)   |                              |   (HITL_RESOLVE)  |
    |                  |----(6a)---->  User sees       |                  |
    |  Translates       |              natural         |  - acknowledge()  |
    |  structured HITL  |              conversation    |  - update_beliefs |
    |  to conversation  |                              |  - emit task.     |
    +------------------+                              |    resume.v1      |
                                                      |                  |
                          +---(7)----+                +--------+---------+
                          |          |                         ^
                          v          |                    (7)  |
                    +-----+----------+-----+                  |
                    |                      |   user.input.v1   |
                    |   USER               |-------------------+
                    |                      |
                    |   Sees natural        |
                    |   conversation,       |
                    |   responds naturally  |
                    +----------------------+

    CLOSED CYCLE:
    Back(1) -> Handler(2) -> Bus -> FSM(3,4) -> Front/RELAY(5,6a) ->
    User(6a) -> User responds(7) -> Front/RESOLVE(7,8) -> Bus ->
    FSM(8) -> Back resumes with resolution

    EVERY NODE IS TOUCHED. NO SHORTCUTS.
```

### Step-by-Step Touch Points

| Step | Component | Action | Input | Output |
| --- | --- | --- | --- | --- |
| **(1)** Back LLM | Calls `submit_result(needs_human)` | ReAct iteration detects ambiguity or side-effect | `ReactResult(status="suspended", data={hil_type, question, options, side_effects, findings_so_far})` |
| **(2)** Back Handler | Emits bus event | `ReactResult` with status `suspended` | `k1.orchestration.task.suspended.v1` envelope on bus |
| **(3)** FSM | Receives bus event | `task.suspended.v1` envelope | Updates `task_state[task_id].status = SUSPENDED` |
| **(4)** FSM | Stores HITL state + invokes Front | Internal state transition | Writes `pending_hil` to `TaskStateEntry`, preserves Back ReAct history in `FSMTurnState`, sets FSM state = `CLARIFYING_WORKER`, invokes Front with `HITL_RELAY` mode |
| **(5)** Front LLM (HITL_RELAY) | Translates structured HITL to natural language | `TaskSuspended` payload in `scenario_data` | Text response to user (no tools, single iteration) |
| **(6a)** User | Sees natural conversational question | Front's text response | User reads and considers |
| **(7)** User | Responds naturally | Their own decision | `k1.session.user.input.v1` event on bus |
| **(7→8)** Front LLM (HITL_RESOLVE) | Parses user answer, confirms, emits resume | `user.input.v1` + `pending_hil` context | `acknowledge()` + `update_beliefs()` + `k1.orchestration.task.resume.v1` |
| **(8)** FSM | Routes resume to Back | `task.resume.v1` envelope | Updates status = `IN_PROGRESS`, increments `hil_suspensions_count`, restores Back ReAct history, dispatches resume to Back handler |
| **(resume)** Back LLM | Continues from where it left off | Restored ReAct history + resolution payload | Next ReAct iteration (typically `invoke_capability` with resolved params) |

---

## 9.2 The Three HITL Shapes

All three are instances of the same closed cycle (Section 9.1). They differ in trigger condition, UX framing, safety implications, and timeout.

### 9.2.1 Clarification (Missing or Ambiguous Parameters)

**Trigger:** Back's ReAct loop detects that a required parameter is missing, ambiguous, or unresolvable from context.

**When Back triggers clarification:**

1. `invoke_capability` schema validation would reject the call (missing required param).
2. `discover_capabilities` returned a capability but `reference_context` + `beliefs_summary` don't contain a needed value.
3. Hydration of `$prev.result.<field>` failed (chained task, field not found -- Section 8.5).

**When Back does NOT trigger clarification:**

- The parameter is inferrable from `reference_context`, `beliefs_summary`, or prior tool results in the same ReAct loop.
- The missing param has a sensible default (e.g., `currency` defaults to user's locale currency from `persona`).

```text
Back ReAct:
  STEP 3: invoke_capability("tool.execute.hotel_booking", params)
          -> schema validation: missing required param "check_in_date"
          -> check reference_context: not present
          -> check beliefs_summary: no dates mentioned
          -> MUST ASK USER

  submit_result(
    result_type="needs_human",
    hil_type="clarification",
    question="What date should I book the hotel for?",
    context={missing_params: ["check_in_date"], capability: "hotel_booking"})

Front (HITL_RELAY mode):
  "I'm looking into booking that hotel -- what dates were you thinking?"

User: "June 15th for 2 nights"

Front (HITL_RESOLVE mode):
  acknowledge("Perfect, June 15 to 17!")
  update_beliefs([{subject: "trip", predicate: "has_dates",
    object: "June 15-17", confidence: 1.0}])
  -> emit task.resume.v1: {resolution: {check_in_date: "2026-06-15", nights: 2}}

Back (resumed):
  invoke_capability("tool.execute.hotel_booking",
    {hotel: "Vineyard Inn", check_in_date: "2026-06-15", nights: 2})
```

### 9.2.2 Approval (Side-Effect Actions)

**Trigger:** Before executing any capability where `has_side_effects == true`, Back MUST get user approval. This is mandatory -- not a judgment call.

**The rule is absolute:** `has_side_effects=true` in the `CapabilityContract` → Back calls `submit_result(needs_human, hil_type="approval")` BEFORE calling `invoke_capability`. No exception. No bypass. The FSM enforces this at L2 (Section 9.8) as a defense-in-depth check.

```text
Back ReAct:
  STEP 4: discover_capabilities(intent="book hotel", domain="travel")
          -> observe: {name: "tool.execute.hotel_booking",
                       has_side_effects: true, required_params: [...]}

  STEP 5 (SAFETY CHECK):
          has_side_effects == true -> AMBER -> MUST REQUEST APPROVAL

  submit_result(
    result_type="needs_human",
    hil_type="approval",
    question="Ready to book Vineyard Inn, June 15-17, 2 guests, $598 total.",
    options=["approve", "modify", "cancel"],
    side_effects=["Charge $598 to Visa ending 4242",
                  "Create reservation ACM-XXXXXX (non-refundable)"],
    safety_band="AMBER")

Front (HITL_RELAY mode):
  "The Vineyard Inn is ready to book -- $598 on your Visa ending 4242.
   Heads up: it's non-refundable after June 13. Want me to go ahead?"

User: "Go ahead but use the Amex"

Front (HITL_RESOLVE mode):
  acknowledge("Booking with the Amex!")
  update_beliefs([{subject: "payment", predicate: "use",
    object: "Amex", confidence: 1.0}])
  -> emit task.resume.v1: {resolution: {decision: "approve",
       modifications: {payment_method: "amex"}}}

Back (resumed):
  invoke_capability("tool.execute.hotel_booking",
    {hotel: "Vineyard Inn", check_in: "June 15", nights: 2, payment: "amex"})
```

**Approval resolution shapes:**

| User response | `resolution.decision` | Back behavior |
| --- | --- | --- |
| "Go ahead" / "Yes" / "Book it" | `approve` | Execute `invoke_capability` with original params |
| "Go ahead but use the Amex" | `approve` + `modifications` | Apply modifications to params, then execute |
| "Change to 3 nights" | `modify` + `modifications` | Apply modifications, re-present for approval (counts as suspension round) |
| "No" / "Cancel" / "Never mind" | `cancel` | `submit_result(complete)` with `final_answer: "Booking cancelled by user."` |

### 9.2.3 Selection (Presenting Choices)

**Trigger:** Back executed a discovery capability and got multiple results that the user must choose from. Back cannot pick -- the choice is subjective or preference-driven.

**When Back triggers selection:**

- Search returned multiple matches for an ambiguous target (3 "Vineyard Inn" properties).
- Discovery returned options that require taste/preference judgment (restaurants, activities).
- The task intent is an action (book, reserve, order) that requires specificity.

**When Back does NOT trigger selection:**

- The task intent is discovery-only ("find restaurants") -- Back completes with all results, Front presents them. No suspension needed.
- Only one result matches -- proceed directly.
- User already specified which one in `reference_context` or `params`.

```text
Back ReAct:
  invoke_capability("tool.execute.hotel_search", {name: "Vineyard Inn"})
  -> observe: {success: true, data: [
       {name: "Vineyard Inn, Napa Valley", price: 298},
       {name: "Vineyard Inn, Sonoma", price: 185},
       {name: "Vineyard Inn & Spa, St. Helena", price: 420}]}

  Task intent = "book hotel" (action, not discovery).
  Multiple matches. Cannot pick. Must ask.

  submit_result(
    result_type="needs_human",
    hil_type="selection",
    question="Multiple 'Vineyard Inn' properties found. Which one?",
    options=[
      {id: 1, label: "Vineyard Inn, Napa Valley", price: "$298/night"},
      {id: 2, label: "Vineyard Inn, Sonoma", price: "$185/night"},
      {id: 3, label: "Vineyard Inn & Spa, St. Helena", price: "$420/night"}],
    findings_so_far=[hotel_search_results])

Front (HITL_RELAY mode):
  "I found a few places called Vineyard Inn! Which one were you thinking of?
   There's one in Napa Valley at $298 a night, a really nice deal in Sonoma
   at $185, and a Spa version in St. Helena at $420."

User: "The one in Sonoma"

Front (HITL_RESOLVE mode):
  acknowledge("Great choice!")
  update_beliefs([{subject: "accommodation", predicate: "target",
    object: "Vineyard Inn, Sonoma", confidence: 1.0}])
  -> emit task.resume.v1: {resolution: {selected_option: 2,
       target: "Vineyard Inn, Sonoma"}}

Back (resumed):
  invoke_capability("tool.execute.hotel_booking",
    {hotel: "Vineyard Inn, Sonoma", check_in: "June 15", nights: 2})
```

---

## 9.3 Safety Band Escalation Table

The safety band determines whether HITL approval is required. Back checks this in STEP 5 of its system prompt (Section 6.2). The FSM enforces it as defense-in-depth at L2 (Section 9.8).

```text
  SAFETY BAND ESCALATION
  =======================

  Capability                   Safety      Side         HITL
  Contract                     Band        Effects?     Required?
  +--------------------------+-----------+------------+----------------+
  | search, lookup, compare  | GREEN     | No         | NO  (execute)  |
  | read calendar, weather   |           |            |                |
  +--------------------------+-----------+------------+----------------+
  | search with side_effects | GREEN ->  | Yes        | YES (auto-     |
  | (rare, misconfigured)    | AMBER     |            |  escalate)     |
  +--------------------------+-----------+------------+----------------+
  | book, order, send, pay   | AMBER     | Yes        | YES (approval) |
  | create event, modify     |           |            |                |
  +--------------------------+-----------+------------+----------------+
  | financial transfer,      | RED       | Yes        | BLOCK. Never   |
  | delete account, medical  |           |            | execute. Refer |
  | prescription, legal sign |           |            | to supervisor. |
  +--------------------------+-----------+------------+----------------+
```

| Safety Band | `has_side_effects` | HITL Action | Back Behavior |
| --- | --- | --- | --- |
| GREEN | `false` | None required | Execute `invoke_capability` directly |
| GREEN | `true` | Auto-escalate to AMBER | `submit_result(needs_human, approval)` -- the GREEN band is overridden by side-effect flag |
| AMBER | any | Approval required | `submit_result(needs_human, approval)` with explicit `side_effects[]` list |
| RED | any | Execution blocked | `submit_result(needs_human, clarification)` with message: "This action requires elevated authorization." Back NEVER executes RED capabilities. |

**Key rule:** `has_side_effects=true` always wins. A GREEN safety band with side effects auto-escalates to AMBER behavior. This prevents misconfigured capabilities from executing without approval. The check order is:

```text
1. Is safety_band == RED?        -> BLOCK (never execute)
2. Is has_side_effects == true?  -> AMBER behavior (approval required)
3. Is safety_band == AMBER?      -> Approval required (even if side_effects=false,
                                    which would be unusual for AMBER)
4. Otherwise (GREEN, no sides)   -> Execute directly
```

---

## 9.4 Front LLM Behavior During HITL

Front does NOT relay raw structured data. It TRANSLATES. The user never sees JSON, field names, option IDs, or technical terms. Two distinct modes handle the two halves of the cycle.

### HITL_RELAY Mode (Presenting the Question)

**Trigger:** `task.suspended.v1` received by FSM, FSM invokes Front in HITL_RELAY mode.

**Configuration (from Section 6.1):**

- Tools: 0 (text-only, no tools at all)
- Max iterations: 1
- History window: 0 entries (no user input triggered this -- Back's structured request is the only context)
- SS sections: `persona`, `affective_now` (for tone matching)

**Front's job:** Convert the structured `TaskSuspended` payload into natural, empathetic conversation. The scenario_data template (Section 6.1) provides the HITL fields. Front's response is the ONLY thing the user sees.

**Translation rules by hil_type:**

| `hil_type` | Front's approach | Example input | Example output |
| --- | --- | --- | --- |
| `clarification` | Ask naturally, as if curious. One question only. | `{question: "What date for hotel?"}` | "When are you thinking of heading to Napa? I'll need the dates to lock it in." |
| `approval` | State what will happen. Lead with facts, end with ask. Explicitly mention consequences from `side_effects[]`. | `{question: "Confirm booking?", side_effects: ["Charge $598", "Non-refundable"]}` | "The Vineyard Inn is ready -- $598 on your Visa. Heads up, it's non-refundable after June 13. Want me to go ahead?" |
| `selection` | Present options with personality. Use comparative framing, not a numbered list (unless 4+ options). Highlight distinguishing features. | `{options: [{label: "Napa, $298"}, {label: "Sonoma, $185"}]}` | "I found two! There's one in Napa Valley at $298 a night, and a great deal in Sonoma at $185. Which one sounds right?" |

**Affect-aware translation (from Section 6.1, Affect Band System):**

| User affect | Front's HITL tone | Example adjustment |
| --- | --- | --- |
| Anxious / nervous | Reassuring. Lead with safety. | "Don't worry, nothing's charged yet. Want me to go ahead with the booking?" |
| Decisive / impatient | Brief. Skip details, get to the ask. | "Vineyard Inn, $598, non-refundable. Go?" |
| Excited / happy | Match energy. | "Great news! The Vineyard Inn is locked in at $598. Ready to book?" |

### HITL_RESOLVE Mode (Processing the Answer)

**Trigger:** `user.input.v1` received while FSM state is `CLARIFYING_WORKER` (a task is suspended).

**Configuration (from Section 6.1):**

- Tools: 2 (`acknowledge`, `update_beliefs`)
- Max iterations: 3
- History window: 5 entries (just the HITL question and user's answer)
- SS sections: `persona`, `affective_now`, `beliefs_active`, `task_state`

**Front's job:** Parse the user's natural language answer, map it to the structured resolution format for `task.resume.v1`, update beliefs, and confirm to the user what will happen next.

**Resolution parsing by hil_type:**

| `hil_type` | User answer | Front's parsing | `task.resume.v1` resolution |
| --- | --- | --- | --- |
| `clarification` | "June 15th for 2 nights" | Extract dates, compute check_out | `{answer: "June 15-17", resolved_params: {check_in: "June 15", nights: 2}}` |
| `approval` | "Go ahead" | Map to approve | `{decision: "approve"}` |
| `approval` | "Go ahead but use the Amex" | Approve + extract modification | `{decision: "approve", modifications: {payment_method: "amex"}}` |
| `approval` | "No, cancel" | Map to cancel | `{decision: "cancel"}` |
| `selection` | "The one in Sonoma" | Match to option by content | `{selected_option: 2, target: "Vineyard Inn, Sonoma"}` |
| `selection` | "Both of them" | Multi-select (if applicable) | `{selected_options: [1, 2]}` |

**Front emits after resolve:**

1. `acknowledge()` -- confirm what will happen: "Booking with the Amex!"
2. `update_beliefs()` -- persist the resolved information in SS.
3. Text response -- natural confirmation to user.
4. FSM emits `k1.orchestration.task.resume.v1` with the parsed resolution.

---

## 9.5 Suspension Rules and Limits (ITEM #15)

These are the behavioral rules that govern the HITL lifecycle. The schemas are in Section 5 (`TaskStateEntry.pending_hil`, `hil_suspensions_count`). The bus payloads are in Section 8.2 (`TaskSuspended`, `TaskResume`). This section owns the RULES.

### Max Suspension Rounds

| Rule | Value | Enforcement | Fallback |
| --- | --- | --- | --- |
| Max suspensions per task | **2** | `TaskStateEntry.hil_suspensions_count` checked by FSM before routing `task.suspended` | On 3rd ambiguity, Back picks the best option and notes reasoning in `final_answer`. Back's system prompt (Section 6.2) enforces this: "Maximum suspensions: 2 per task. On third ambiguity: pick the best option, note reasoning in final_answer." |
| Concurrent suspensions per task | **1** | FSM rejects a second `task.suspended` for the same `task_id` if one is already pending | Back is in a ReAct loop -- it can only suspend once per loop invocation. A second suspend would require a resume first. |
| Max suspensions across all tasks | **No limit** | Different tasks can each have up to 2 suspensions independently | Tracked per `task_id` in `TaskStateEntry.hil_suspensions_count` |

### Timeout Policy

| `hil_type` | Timeout | Rationale | On timeout |
| --- | --- | --- | --- |
| `clarification` | 60 seconds | User should know the answer quickly | FSM auto-cancels: `task_state[task_id].status = CANCELLED`, reason `"hil_timeout"`. Front notified via `task.failed` with `reason="timeout"`. |
| `approval` | 120 seconds | Financial/consequential decisions need thinking time | Same as above. Longer window because the stakes are higher. |
| `selection` | 90 seconds | User may need to read and compare options | Same as above. |

**Timeout implementation:** FSM starts a timer when it sets `task_state[task_id].status = SUSPENDED`. Timer value is determined by `hil_type` from the `TaskSuspended` payload. If `user.input.v1` arrives before timeout, timer is cancelled. If timer fires:

```python
async def _handle_hil_timeout(self, task_id: str):
    """Called when HITL timeout fires. Auto-cancels the suspended task."""
    entry = self.ss.task_state.get(task_id)
    if entry and entry["status"] == "SUSPENDED":
        entry["status"] = "CANCELLED"
        entry["completed_at_ms"] = now_ms()
        await self.bus.emit(Envelope(
            topic="k1.orchestration.task.failed.v1",
            payload=TaskFailed(
                task_id=task_id,
                reason="hil_timeout",
                error_code="HITL_TIMEOUT",
                tool_history=[],
                partial_results=entry.get("pending_hil", {}).get("findings_so_far", []),
                retries_attempted=0,
                last_error_detail=f"User did not respond within "
                                  f"{self._timeout_for(entry)}s.",
            ),
            priority=Priority.INTERACTIVE,
        ))
```

### Pending HIL Persistence

`TaskStateEntry.pending_hil` (Section 5) stores the serialized HITL request. This field is the crash recovery mechanism:

```python
# Written by FSM when task.suspended arrives:
task_state[task_id]["pending_hil"] = {
    "hil_type": suspended_payload.hil_type,
    "question": suspended_payload.question,
    "options": suspended_payload.options,
    "side_effects": suspended_payload.side_effects,
    "safety_band": suspended_payload.safety_band,
    "findings_so_far": suspended_payload.findings_so_far,
    "suspended_at_ms": now_ms(),
}

# Read by FSM on startup/reconnect:
for task_id, entry in task_state.items():
    if entry["status"] == "SUSPENDED" and entry["pending_hil"]:
        elapsed = now_ms() - entry["pending_hil"]["suspended_at_ms"]
        timeout = self._timeout_for(entry)
        if elapsed > timeout * 1000:
            await self._handle_hil_timeout(task_id)
        else:
            # Re-present to user via HITL_RELAY
            await self._invoke_front_hitl_relay(task_id, entry["pending_hil"])
```

---

## 9.6 Crash Recovery Protocol (ITEM #15)

What happens when components fail while a task is SUSPENDED. This is the behavioral half -- the schema (`pending_hil`) is in Section 5.

### Scenario Matrix

| What crashes | State at crash | Recovery | Data loss |
| --- | --- | --- | --- |
| **Back process dies** while task is SUSPENDED | `task_state[task_id].status = SUSPENDED`, `pending_hil` persisted in SS | **No impact.** Back is not running during suspension -- the user is deciding. When user responds, FSM creates a new Back handler with the resolution + restored ReAct history. | None. Back's prior ReAct history is in FSMTurnState. `findings_so_far` is in `pending_hil`. |
| **Front process dies** while presenting HITL_RELAY | `pending_hil` persisted, but user may not have seen the question | FSM detects Front reconnect. Reads `task_state` for SUSPENDED tasks with `pending_hil`. Re-invokes Front in HITL_RELAY mode with the stored `pending_hil`. User sees the question (possibly again). | Possible duplicate presentation (user might see the question twice). Idempotent -- answering twice produces the same resume. |
| **FSM/process restarts** while task is SUSPENDED | `task_state` is in Session State (persisted). `FSMTurnState` is ephemeral (lost). | FSM startup scans `task_state` for `status=SUSPENDED` entries. For each: check `pending_hil.suspended_at_ms` against timeout. If not expired: re-invoke Front HITL_RELAY. If expired: auto-cancel via `_handle_hil_timeout`. ReAct history in FSMTurnState is lost -- Back restarts from `findings_so_far` only. | Back's full ReAct message history is lost (FSMTurnState is ephemeral). `findings_so_far` in `pending_hil` provides a summary. Back may need to re-execute some discovery calls but will NOT repeat side-effect calls (those haven't happened yet -- approval hasn't been given). |
| **User disconnects** during suspension | Timer continues running server-side | Timeout fires normally. Task auto-cancelled. If user reconnects before timeout: FSM re-presents HITL via `pending_hil`. | None. Timeout is the designed behavior for unresponsive users. |
| **Bus crashes** during HITL event routing | Event may be lost mid-flight | If `task.suspended` was lost: Back's handler returned `ReactResult(status=suspended)` but FSM never received the event. Task remains IN_PROGRESS from FSM's perspective. Back is terminated. Task eventually times out via FSM's dispatch-level timeout (separate from HITL timeout). If `task.resume` was lost: user answered but Back never got the resume. FSM retries resume emission. | Potential task loss if bus doesn't provide at-least-once delivery. Bus reliability is a deployment concern (Section 3). |

### Recovery Sequence (FSM Restart)

```text
FSM STARTUP RECOVERY
====================

1. Load Session State (persisted)
2. Scan task_state for entries with status=SUSPENDED

For each SUSPENDED task:
  3. Read pending_hil.suspended_at_ms
  4. Calculate elapsed = now_ms() - suspended_at_ms
  5. If elapsed > timeout_for(hil_type):
       -> Auto-cancel: emit task.failed (reason="hil_timeout")
       -> Clear pending_hil
  6. If elapsed <= timeout:
       -> Re-present: invoke Front in HITL_RELAY mode
       -> Restart timeout timer for remaining duration
  7. Reconstruct FSMTurnState from task_state:
       -> cancelled_tasks = {t.task_id for t in task_state if t.status == "CANCELLED"}
       -> pending_results = deque()  # Lost on restart -- acceptable, no data loss
```

### Why This Works

The key insight is that `pending_hil` is in Session State (persisted), not in FSMTurnState (ephemeral). This means:

1. **Back crash is free.** Back doesn't do anything during suspension. The user hasn't approved yet, so no side-effects have fired. Back is stateless -- a new Back instance can resume from `findings_so_far` + resolution.

2. **Front crash is re-presentable.** The structured HITL request is stored in `pending_hil`. Front just needs to translate it again. Idempotent.

3. **FSM crash is recoverable.** Session State survives. The scan-on-startup pattern catches all SUSPENDED tasks and either re-presents or times them out.

4. **The worst case is redundant discovery.** If FSMTurnState (with full ReAct history) is lost, Back resumes with only `findings_so_far` (a summary). It may re-execute discovery calls (searches, lookups) but these are GREEN/no-side-effects -- safe to repeat. Side-effect calls (bookings, payments) only happen AFTER approval -- which hasn't been given yet.

---

## 9.7 The Three HITL Flows: Complete Event Traces

Each flow shows every bus event, every FSM state transition, and every LLM invocation. These traces are the authoritative reference for implementers.

### Flow 1: Clarification (Missing Parameter)

```text
CLARIFICATION FLOW
==================

  USER          FRONT(1)        FSM           BUS              BACK
   |               |             |              |                |
   | "Book hotel"  |             |              |                |
   +-------(a)---->|             |              |                |
   |               | ack+dispatch|              |                |
   |               +-----(b)---->+              |                |
   |               |             | task.dispatch|                |
   |               |             +------(c)---->+                |
   |               |             |              | task.dispatch  |
   |               |             |              +-------(d)----->|
   |               |             |              |                |
   |               |             |              |    detect:     |
   |               |             |              |    missing     |
   |               |             |              |    check_in    |
   |               |             |              |                |
   |               |             |              | task.suspended |
   |               |             |              |<------(e)------+
   |               |             | task.suspended|               |
   |               |             |<-----(f)-----+                |
   |               |             |              |                |
   |               |             | state ->     |                |
   |               |             | CLARIFYING_  |                |
   |               |             | WORKER       |                |
   |               |             | store        |                |
   |               |             | pending_hil  |                |
   |               |             |              |                |
   |               | HITL_RELAY  |              |                |
   |               |<----(g)-----+              |                |
   |  "What dates?"|             |              |                |
   |<------(h)-----+             |              |                |
   |               |             |              |                |
   | "June 15-17"  |             |              |                |
   +-------(i)---->|             |              |                |
   |               | HITL_RESOLVE|              |                |
   |               +-----(j)---->+              |                |
   |               |             | task.resume  |                |
   |               |             +------(k)---->+                |
   |               |             |              | task.resume    |
   |               |             |              +-------(l)----->|
   |               |             |              |                |
   |<--"Booking!"--|             |              |  invoke_cap    |
   |               |             |              |  (with dates)  |
   |               |             |              |                |
   |               |             |              | task.complete  |
   |               |             |              |<------(m)------+
   |               |             | task.complete|                |
   |               |             |<-----(n)-----+                |
   |               | PRESENT     |              |                |
   |               |<----(o)-----+              |                |
   |  "All booked!"|             |              |                |
   |<------(p)-----+             |              |                |

Events: (a) user.input -> (b) ack+dispatch -> (c,d) task.dispatch ->
        (e,f) task.suspended -> (g,h) HITL_RELAY -> (i) user.input ->
        (j) HITL_RESOLVE -> (k,l) task.resume -> (m,n) task.complete ->
        (o,p) PRESENT

FSM transitions: LISTENING -> DISPATCHING -> CLARIFYING_WORKER -> DISPATCHING -> DELIVERING -> LISTENING
```

### Flow 2: Approval (Side-Effect Action)

```text
APPROVAL FLOW
=============

  USER          FRONT(1)        FSM           BUS              BACK
   |               |             |              |                |
   | "Book it"     |             |              |                |
   +-------(a)---->|             |              |                |
   |               | ack+dispatch|              |                |
   |               +-----(b)---->+              |                |
   |               |             | task.dispatch|                |
   |               |             +------(c)---->+                |
   |               |             |              | task.dispatch  |
   |               |             |              +-------(d)----->|
   |               |             |              |                |
   |               |             |              |  side_effects  |
   |               |             |              |  = true ->     |
   |               |             |              |  MUST APPROVE  |
   |               |             |              |                |
   |               |             |              | task.suspended |
   |               |             |              | hil=approval   |
   |               |             |              |<------(e)------+
   |               |             | store        |                |
   |               |             | pending_hil  |                |
   |               |             | start 120s   |                |
   |               |             | timer        |                |
   |               |             |              |                |
   |               | HITL_RELAY  |              |                |
   |               |<----(f)-----+              |                |
   |  "$598, Visa, |             |              |                |
   |   non-refund. |             |              |                |
   |   Go ahead?"  |             |              |                |
   |<------(g)-----+             |              |                |
   |               |             |              |                |
   | "Yes, but     |             |              |                |
   |  use Amex"    |             |              |                |
   +-------(h)---->|             |              |                |
   |               | HITL_RESOLVE|              |                |
   |               | decision:   |              |                |
   |               | approve +   |              |                |
   |               | modify pmnt |              |                |
   |               +-----(i)---->+              |                |
   |               |             | cancel timer |                |
   |               |             | task.resume  |                |
   |               |             +------(j)---->+                |
   |               |             |              | task.resume    |
   |               |             |              +-------(k)----->|
   |               |             |              |                |
   |<--"Booking    |             |              |  invoke_cap    |
   |   w/ Amex!"   |             |              |  (pmnt=amex)   |
   |               |             |              |                |
   |               |             |              | task.complete  |
   |               |             |              |<------(l)------+
   |               | PRESENT     |              |                |
   |               |<----(m)-----+              |                |
   |  "Confirmed!  |             |              |                |
   |   ACM-847293" |             |              |                |
   |<------(n)-----+             |              |                |

Approval-specific: timer started at (e), cancelled at (i).
If timer fires before (h): task auto-cancelled, user notified.
```

### Flow 3: Selection (Multiple Results)

```text
SELECTION FLOW
==============

  USER          FRONT(1)        FSM           BUS              BACK
   |               |             |              |                |
   | "Book the     |             |              |                |
   |  Vineyard Inn"|             |              |                |
   +-------(a)---->|             |              |                |
   |               | ack+dispatch|              |                |
   |               +-----(b)---->+              |                |
   |               |             | task.dispatch|                |
   |               |             +------(c)---->+                |
   |               |             |              | task.dispatch  |
   |               |             |              +-------(d)----->|
   |               |             |              |                |
   |               |             |              |  search ->     |
   |               |             |              |  3 matches     |
   |               |             |              |  can't pick    |
   |               |             |              |                |
   |               |             |              | task.suspended |
   |               |             |              | hil=selection  |
   |               |             |              |<------(e)------+
   |               |             | store results|                |
   |               |             | in findings_ |                |
   |               |             | so_far       |                |
   |               |             |              |                |
   |               | HITL_RELAY  |              |                |
   |               |<----(f)-----+              |                |
   |  "I found 3!  |             |              |                |
   |   Napa $298,  |             |              |                |
   |   Sonoma $185,|             |              |                |
   |   St.Helena   |             |              |                |
   |   $420"       |             |              |                |
   |<------(g)-----+             |              |                |
   |               |             |              |                |
   | "Sonoma"      |             |              |                |
   +-------(h)---->|             |              |                |
   |               | HITL_RESOLVE|              |                |
   |               | selected: 2 |              |                |
   |               +-----(i)---->+              |                |
   |               |             | task.resume  |                |
   |               |             +------(j)---->+                |
   |               |             |              | task.resume    |
   |               |             |              +-------(k)----->|
   |               |             |              |                |
   |<--"Booking    |             |              |  resume w/     |
   |   Sonoma!"    |             |              |  findings +    |
   |               |             |              |  selection     |
   |               |             |              |                |
   |               |             |              |  invoke_cap    |
   |               |             |              |  (Sonoma)      |
   |               |             |              |                |
   |               |             |              | task.complete  |
   |               |             |              |<------(l)------+
   |               | PRESENT     |              |                |
   |               |<----(m)-----+              |                |
   |  "Booked!     |             |              |                |
   |   Vineyard Inn|             |              |                |
   |   Sonoma"     |             |              |                |
   |<------(n)-----+             |              |                |

Selection-specific: findings_so_far preserved for resume.
Back does NOT re-search -- continues from stored results.
```

---

## 9.8 Defense-in-Depth: FSM Enforcement Layer (L2)

Back's system prompt teaches it to request approval before side-effect capabilities. But LLMs hallucinate. They skip steps. They misread `has_side_effects`. The FSM provides a structural enforcement layer that catches violations even if Back's LLM judgment fails.

### FSM HITL Enforcement Rules

```python
class FSMHITLEnforcer:
    """L2 defense-in-depth. Validates HITL compliance before routing
    Back's invoke_capability calls to the Fabric.

    This is NOT in Back's ReAct loop. This is in the tool dispatcher
    (Section 7) that routes Back's tool calls to actual capabilities.
    """

    def validate_before_invoke(
        self,
        capability_name: str,
        capability_contract: dict,
        task_state_entry: dict,
    ) -> str:
        """Returns 'allow', 'block_needs_approval', or 'block_red'.

        Called by the tool dispatcher AFTER Back calls invoke_capability
        but BEFORE the actual capability is executed.
        """
        has_side_effects = capability_contract.get("has_side_effects", False)
        safety_band = task_state_entry.get("safety_band", "AMBER")

        # RED: never execute, regardless of what Back thinks
        if safety_band == "RED":
            return "block_red"

        # Side effects without prior approval: block
        if has_side_effects:
            if not self._has_prior_approval(task_state_entry):
                return "block_needs_approval"

        return "allow"

    def _has_prior_approval(self, task_state_entry: dict) -> bool:
        """Check if this task had a prior approval HITL round."""
        hil_history = task_state_entry.get("hil_history", [])
        return any(
            h.get("hil_type") == "approval" and h.get("resolution", {}).get("decision") == "approve"
            for h in hil_history
        )
```

**What happens when L2 blocks:**

| L2 verdict | FSM action | Back sees |
| --- | --- | --- |
| `block_needs_approval` | FSM intercepts `invoke_capability`, forces `submit_result(needs_human, approval)` on Back's behalf | `invoke_capability` returns `{error: "approval_required", message: "Side-effect capability requires user approval. Suspending for approval."}`. FSM auto-generates the `task.suspended` event. |
| `block_red` | FSM intercepts, returns error | `invoke_capability` returns `{error: "blocked_red", message: "Capability blocked by RED safety band."}`. Back should call `submit_result(needs_human, clarification)` to explain to user. |
| `allow` | Normal execution path | Capability executes, result returned to Back |

**Why defense-in-depth matters:** In testing, Back correctly requests approval ~95% of the time (STEP 5 in system prompt). The 5% failure rate means 1 in 20 side-effect actions would execute without approval in production. L2 catches these. The user ALWAYS gets asked before money moves, reservations commit, or messages send.

---

## 9.9 K1 HITL Architecture Layer Mapping

The K1 platform defines three HITL layers. The POC implements L1 only. L2 and L3 are reserved for the full Orchestrator and Planner.

```text
  K1 HITL ARCHITECTURE LAYERS
  ============================

  +-------------------------------------------------------------------+
  |  L3: PLANNER HITL (HILCoordinator)                    [NOT IN POC] |
  |  - Plan-time HITL: "Should I book hotel first or car first?"       |
  |  - Operates during SKETCH/VALIDATE phases                         |
  |  - Bus topics: k1.hil.plan.* (reserved)                           |
  |  - Trigger: PlanStep ambiguity, multi-path choice                 |
  |  - Only activates for HIGH tier tasks                              |
  +-------------------------------------------------------------------+
       |
       v
  +-------------------------------------------------------------------+
  |  L2: ORCHESTRATOR HITL (HILRequest)                   [NOT IN POC] |
  |  - Execution-time HITL: "Step 3 of 5 failed. Retry or skip?"      |
  |  - Operates during DAG wave execution                             |
  |  - Bus topics: k1.hil.orchestrator.* (reserved)                   |
  |  - Trigger: Step failure, override request                        |
  |  - Only activates for HIGH tier tasks with multi-step plans       |
  +-------------------------------------------------------------------+
       |
       v
  +-------------------------------------------------------------------+
  |  L1: CONCIERGE HITL (task.suspended)               [POC IMPLEMENTS] |
  |  - Task-time HITL: ambiguity, approval, selection                  |
  |  - Operates during Back's ReAct loop execution                     |
  |  - Bus topics: k1.orchestration.task.suspended/resume.v1           |
  |  - Trigger: Back calls submit_result(needs_human)                  |
  |  - Activates for ALL tiers (LOW, MEDIUM, HIGH)                     |
  |  - Defense-in-depth: FSM L2 enforcer catches missed approvals      |
  +-------------------------------------------------------------------+
```

### Bus Topic Namespace Separation

| Layer | Bus topics | Used in POC |
| --- | --- | --- |
| L3 (Planner) | `k1.hil.plan.clarification.v1`, `k1.hil.plan.approval.v1` | No (reserved) |
| L2 (Orchestrator) | `k1.hil.orchestrator.request.v1`, `k1.hil.orchestrator.override.v1` | No (reserved) |
| L1 (Concierge) | `k1.orchestration.task.suspended.v1`, `k1.orchestration.task.resume.v1` | **Yes** |

The namespace separation means L1, L2, and L3 HITL events never collide on the bus. A production system running all three layers has clean topic partitioning. The POC's L1 implementation is forward-compatible -- when L2/L3 come online, they subscribe to their own topics without modifying L1.

### L1 Interaction with L2/L3 (Future)

When the full Orchestrator is deployed:

1. HIGH tier tasks go through L3 (Planner) for plan-level HITL.
2. The committed plan's steps execute through L2 (Orchestrator), which handles step-level HITL.
3. Within each step, the executing agent (Back) still uses L1 for task-level HITL.

L1 is ALWAYS present. L2 and L3 layer on top. The closed cycle (Section 9.1) remains unchanged -- it always involves Back → FSM → Front → User → Front → FSM → Back.

---

## 9.10 HITL Invariants

These are the non-negotiable rules. If any of these are violated, the system is broken.

| # | Invariant | Enforcement |
| --- | --- | --- |
| 1 | **No side-effect capability executes without user approval.** | Back STEP 5 (LLM judgment) + FSM L2 enforcer (structural check). Two independent checks. Both must pass. |
| 2 | **The user never sees raw JSON, field names, option IDs, or error codes.** | Front HITL_RELAY mode has 0 tools and produces text only. Scenario_data template instructs translation. Anti-pattern list (Section 6.1) explicitly forbids raw relay. |
| 3 | **Every HITL cycle closes.** | Timeout guarantees closure. If the user doesn't respond, the task auto-cancels. No suspension hangs forever. |
| 4 | **`pending_hil` survives process restarts.** | Stored in Session State (persisted), not FSMTurnState (ephemeral). FSM startup recovery scans for SUSPENDED tasks. |
| 5 | **Back never executes during suspension.** | Back's ReAct loop exited with `status=suspended`. Back handler returned. No Back code runs until `task.resume` arrives and FSM creates a new handler invocation. |
| 6 | **Max 2 suspensions per task.** | `hil_suspensions_count` in TaskStateEntry, checked by FSM before routing. Back system prompt reinforces at LLM level. |
| 7 | **Front's HITL_RELAY response is the ONLY user-facing output.** | HITL_RELAY has 0 tools. Single iteration. Text only. No acknowledge, no dispatch, no cognitive tools. |
| 8 | **Approval modifications are applied before execution, not after.** | Front parses `modifications` in HITL_RESOLVE and includes them in `task.resume.v1` resolution. Back applies modifications to params before calling `invoke_capability`. |
| 9 | **RED safety band capabilities never execute.** | Back STEP 5 refuses. FSM L2 enforcer blocks. Two independent barriers. |
| 10 | **HITL re-presentation is idempotent.** | If Front crashes and re-presents the same HITL question, the user answering again produces the same `task.resume.v1`. No state corruption from duplicate presentation. |

---

# 10. LLM Adapter & Operability

The system defines ONE adapter interface for all LLM calls. Every actor -- Front, Back, Planner, dynamic agents -- routes through this adapter. Provider differences (Gemini, OpenAI, Anthropic, local) are the adapter's problem. The rest of the system speaks one language.

**Design principles:**

- System sees ONE interface. Provider translation is internal to the adapter.
- Every call is capability-tagged: `CHAT`, `TOOL_CALL`, `STRUCTURED`, `STREAM`, `REASON`.
- The adapter decides which model handles which capability (model selection).
- Token budgets and timeouts are enforced by the adapter, not the caller.
- Tool schemas are provider-agnostic JSON Schema (`ToolSchema`, Section 6.0). The adapter converts to provider-native format internally.
- Streaming is a delivery concern, not a capability concern. Any call can stream.

---

## 10.1 `IConciergeModelPort` Protocol

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable, AsyncIterator
from dataclasses import dataclass, field

@runtime_checkable
class IConciergeModelPort(Protocol):
    """Universal LLM port for all actors.

    This is the POC's Model Hub interface. Production replaces this
    with the real Model Hub's ILLMPort + LLMGatewayAdapter pipeline
    (Section 10.10 mapping table).

    Every actor (Front, Back, dynamic agents) calls this same interface.
    The adapter handles:
      - Provider routing (Gemini, OpenAI, Anthropic, local)
      - Model selection per capability tag
      - Tool schema conversion to provider format
      - Token budget enforcement
      - Timeout enforcement
      - Streaming delegation
      - Response normalization to ConciergeModelResponse

    Callers NEVER import provider SDKs.
    Callers NEVER construct provider-specific message formats.
    """

    async def generate(self, request: ConciergeModelRequest) -> ConciergeModelResponse:
        """Single LLM inference call. Returns complete response."""
        ...

    async def generate_stream(
        self, request: ConciergeModelRequest
    ) -> AsyncIterator[StreamChunk]:
        """Streaming LLM inference. Yields text deltas + final tool calls.

        StreamChunk types (ITEM #18):
          - TextDelta: incremental text for real-time display
          - ToolCallDelta: tool call accumulating across chunks
          - Done: final signal with complete ConciergeModelResponse

        Used by Front for acks and final responses (Section 10.8).
        Back never calls generate_stream (Section 10.8).
        """
        ...
```

**Consumption:** `react_loop()` (Section 7) takes `model: IConciergeModelPort` as a parameter. Front handler and Back handler each inject their adapter instance. The loop calls `model.generate()` per iteration. Streaming (`generate_stream`) is used outside the loop for Front acks.

---

## 10.2 Request and Response Types

These types are the canonical definitions referenced by Sections 6.1, 6.2, and 7. Every `model.generate()` call throughout the system uses these types.

### 10.2.1 `ConciergeModelRequest`

```python
@dataclass(frozen=True)
class ConciergeModelRequest:
    """Provider-agnostic LLM request envelope.

    Constructed by Front handler, Back handler, or any actor.
    The adapter translates this to the target provider's format.
    """

    # --- What kind of call? ---
    capability: str
    # "CHAT"       -- text in, text out (acks, error explanations)
    # "TOOL_CALL"  -- text in, tool calls + text out (main Front/Back ReAct calls)
    # "STRUCTURED" -- text in, schema-valid JSON out (dispatch parsing)
    # "REASON"     -- text in, chain-of-thought + answer out (complex planning)

    # --- Messages (provider-agnostic) ---
    system_prompt: str                        # System instructions
    messages: list[ModelMessage]              # Conversation history

    # --- Tools (only for TOOL_CALL capability) ---
    tools: list[ToolSchema] | None = None     # JSON Schema definitions (Section 6.0)
    tool_choice: str = "auto"                 # "auto" | "required" | "none" | tool name
    # ITEM #13: Front iteration 0 sets tool_choice="required" to force acknowledge().

    # --- Budget constraints ---
    max_tokens: int = 4096                    # Max output tokens
    timeout_ms: int = 30000                   # Hard timeout (adapter enforces)
    temperature: float = 0.7                  # Sampling temperature

    # --- Observability ---
    trace_id: str = ""                        # End-to-end trace ID
    actor: str = ""                           # "front" | "back" | "planner" | agent name
    scenario: str = ""                        # "user_input" | "task_dispatch" | "weave" etc.

    # --- Model preference (optional) ---
    model_hint: str | None = None             # "fast" | "smart" | "cheap" | specific name
    # If None, adapter picks based on capability + actor + budget.
    # Front acks -> "fast". Back ReAct -> "smart". Error presentation -> "cheap".
```

**Usage in `react_loop()` (Section 7):**

```python
response = await model.generate(ConciergeModelRequest(
    system_prompt=system_prompt,
    messages=messages,
    tools=tools,
    tool_choice="required" if iteration == 0 and actor == "front" and tools else "auto",
    max_tokens=2048,
    actor=actor,
))
```

Note: `react_loop()` omits `capability` because the loop always uses `TOOL_CALL`. The adapter defaults to `TOOL_CALL` when capability is not specified and tools are present.

### 10.2.2 `ConciergeModelResponse`

```python
@dataclass
class ConciergeModelResponse:
    """Provider-agnostic LLM response envelope.

    The adapter normalizes ALL provider responses to this format.
    Callers never see Gemini candidates, OpenAI choices,
    or Anthropic content blocks.
    """

    # --- Text output ---
    text: str = ""                            # Natural language (may be empty if tool-only)

    # --- Tool calls ---
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    # Each: {"id": str, "name": str, "arguments": dict}
    # Normalized from Gemini function_call, OpenAI tool_calls, Anthropic tool_use

    # --- Metadata ---
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model_id: str = ""                        # Which model actually served this
    finish_reason: str = ""                   # "stop" | "tool_calls" | "length" | "error"

    # --- Convenience ---
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())
```

**Consumption:** `react_loop()` (Section 7) branches on `response.text` and `response.tool_calls`:

- Text without tool calls: Front terminal (user response) or Back "thinking aloud" (continues).
- Tool calls present: dispatched to `ToolDispatcher`, results injected as `ToolResultMessage`.

### 10.2.3 Supporting Types

```python
@dataclass(frozen=True)
class ToolCallResult:
    """Single tool call extracted from LLM response."""
    id: str                                   # Unique call ID (for tool result pairing)
    name: str                                 # Tool function name
    arguments: dict                           # Parsed arguments


@dataclass(frozen=True)
class ToolResultMessage:
    """Tool execution result formatted for LLM consumption.
    Used to build the next iteration's messages in ReAct loops.
    See Section 10.4 for the conversion function.
    """
    tool_call_id: str                         # Matches ToolCallResult.id
    name: str                                 # Tool name (for display)
    content: str                              # JSON-serialized result
    # Becomes {"role": "tool", "content": ..., "tool_call_id": ...} in messages


@dataclass(frozen=True)
class ModelMessage:
    """Provider-agnostic message in conversation history."""
    role: str                                 # "user" | "assistant" | "tool" | "system"
    content: str                              # Text content
    tool_call_id: str | None = None           # For role="tool": which call this answers
    name: str | None = None                   # For role="tool": tool name
    tool_calls: list[ToolCallResult] | None = None  # For role="assistant": tool calls made


@dataclass
class StreamChunk:
    """Single chunk from streaming response (ITEM #18).

    Used by generate_stream() (Section 10.1). Front consumes these
    for real-time ack delivery and final response streaming (Section 10.8).
    """
    chunk_type: str                           # "text_delta" | "tool_call_delta" | "done"
    text: str = ""                            # For text_delta: incremental text
    tool_call_partial: dict | None = None     # For tool_call_delta: accumulating call
    response: ConciergeModelResponse | None = None  # For done: the complete response
```

---

## 10.3 Model Selection Strategy

The adapter maps `(capability, actor, model_hint)` to a concrete model. The caller expresses INTENT, not MODEL NAME.

```python
MODEL_SELECTION_TABLE = {
    # (capability, actor)     -> model
    ("CHAT", "front"):         "gemini-2.5-flash",      # Fast acks, presentations
    ("TOOL_CALL", "front"):    "gemini-2.5-pro",        # Cognitive tool selection
    ("TOOL_CALL", "back"):     "gemini-2.5-pro",        # Action tool execution
    ("STRUCTURED", "front"):   "gemini-2.5-flash",      # Dispatch intent parsing
    ("STRUCTURED", "back"):    "gemini-2.5-flash",      # Final answer formatting
    ("REASON", "back"):        "gemini-2.5-pro",        # Complex multi-step reasoning
    ("CHAT", "back"):          "gemini-2.5-flash",      # Error reports (internal)
}

MODEL_HINT_OVERRIDES = {
    "fast":  "gemini-2.5-flash",
    "smart": "gemini-2.5-pro",
    "cheap": "gemini-2.5-flash",
    # "local": "ollama/llama3.2"  # Future: local model support
}
```

**Selection algorithm:**

1. If `model_hint` is set and exists in `MODEL_HINT_OVERRIDES`, use it.
2. Else look up `(capability, actor)` in `MODEL_SELECTION_TABLE`.
3. Else fall back to default model.

Front acks use `"fast"` (flash, <500ms target). Back ReAct iterations use `"smart"` (pro, better tool reasoning). Error reports use `"cheap"`. The table is the single configuration point; swapping models requires editing ONE dict.

---

## 10.4 Tool Result Injection Protocol

When a tool executes and returns a result, the result must be fed back to the LLM in the correct format for the next reasoning step. Both Front and Back use ReAct (Section 7), so tool results are appended as observation messages for the next iteration.

### 10.4.1 Conversion Function

```python
def tool_result_to_message(tool_call: ToolCallResult, result: dict) -> ModelMessage:
    """Convert tool execution result to a ModelMessage for the LLM.

    This is how the LLM "observes" tool results in the ReAct loop.
    The adapter converts this ModelMessage to provider format:
      - Gemini: Content(role="model", parts=[FunctionResponse(...)])
      - OpenAI: {"role": "tool", "content": json, "tool_call_id": id}
      - Anthropic: {"role": "user", "content": [{"type": "tool_result", ...}]}
    """
    return ModelMessage(
        role="tool",
        content=json.dumps(result, default=str),
        tool_call_id=tool_call.id,
        name=tool_call.name,
    )
```

### 10.4.2 Tool Return Shape Table

| Tool | Return Shape | What LLM Sees |
| --- | --- | --- |
| `acknowledge` | `{delivered: true, timestamp_ms: int}` | Confirmation of delivery |
| `update_beliefs` | `{stored: int, updated: int}` | How many beliefs changed |
| `update_scoreboard` | `{qud_depth: int, active_referents: int}` | Scoreboard size |
| `update_clarifications` | `{open_gaps: int, blocking_gaps: int}` | Gap count |
| `update_narrative` | `{active_thread: str, total_threads: int}` | Thread state |
| `refine_affect` | `{previous_emotion: str, updated: bool}` | What was overridden |
| `promote_belief` | `{promoted: bool, from_tier: str}` | Promotion result |
| `recall_memory` | `{memories: [{content: str, relevance: float}], count: int}` | Retrieved memories with content |
| `summarize_context` | `{compressed: str, original_tokens: int, compressed_tokens: int}` | Compressed text |
| `dispatch_task` | `{queued: true, task_id: str}` | Queued confirmation (FSM handles bus event) |
| `discover_capabilities` | `{capabilities: [{name: str, ...}], count: int}` | Available capabilities |
| `invoke_capability` | `{success: bool, data: dict, artifact_type: str}` | Capability output (domain-specific) |
| `spawn_via_fabric` | `{agent_id: str, status: str, result: dict}` | Agent result |
| `execute_workflow` | `{success: bool, steps_completed: int, results: list}` | Workflow output |
| `submit_result` | `{accepted: true, task_status: str}` | Terminal -- loop exits after this |

**Key rule:** Cognitive tool returns are THIN (counts, confirmations). Read tool returns are RICH (full content). Action tool returns are STRUCTURED (domain data). This matters because the ReAct loop accumulates tool results in its prompt -- thin returns save tokens.

---

## 10.5 Output Validation Pipeline

Every LLM response passes through a validation layer BEFORE the handler acts on it. This catches hallucinated tools, malformed arguments, and ordering violations.

### 10.5.1 `LLMOutputValidator`

```python
class LLMOutputValidator:
    """Validates ConciergeModelResponse before handler processes it.

    Uses the actor's tool allowlist (ToolSchema, Section 6.0) as ground truth.
    """

    def __init__(self, allowed_tools: list[ToolSchema]):
        self._tool_names = {t.name for t in allowed_tools}
        self._tool_schemas = {t.name: t for t in allowed_tools}

    def validate(self, response: ConciergeModelResponse, actor: str) -> ValidationResult:
        errors = []

        for tc in response.tool_calls:
            # CHECK 1: Tool name in allowlist?
            if tc.name not in self._tool_names:
                errors.append(ValidationError(
                    type="unknown_tool",
                    message=f"Tool '{tc.name}' not in {actor} allowlist. "
                            f"Available: {sorted(self._tool_names)}",
                    tool_call=tc,
                ))
                continue

            # CHECK 2: Required params present?
            schema = self._tool_schemas[tc.name]
            required = schema.parameters.get("required", [])
            for param in required:
                if param not in tc.arguments:
                    errors.append(ValidationError(
                        type="missing_param",
                        message=f"Tool '{tc.name}' missing required param '{param}'",
                        tool_call=tc,
                    ))

            # CHECK 3: Param types match schema?
            properties = schema.parameters.get("properties", {})
            for param, value in tc.arguments.items():
                if param in properties:
                    expected_type = properties[param].get("type")
                    if not self._type_matches(value, expected_type):
                        errors.append(ValidationError(
                            type="type_mismatch",
                            message=f"Tool '{tc.name}' param '{param}': "
                                    f"expected {expected_type}, "
                                    f"got {type(value).__name__}",
                            tool_call=tc,
                        ))

        # CHECK 4: Front-specific -- acknowledge must be called first
        if actor == "front" and response.tool_calls:
            first_tool = response.tool_calls[0].name
            if first_tool != "acknowledge" and first_tool != "dispatch_task":
                errors.append(ValidationError(
                    type="ack_ordering",
                    message="acknowledge() must be the first tool call "
                            "on user input turns",
                ))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            response=response,
        )
```

**Four validation checks:**

| # | Check | What It Catches |
| --- | --- | --- |
| 1 | `unknown_tool` | LLM hallucinates a tool name not in the actor's allowlist |
| 2 | `missing_param` | LLM omits a required parameter |
| 3 | `type_mismatch` | LLM passes wrong type (string where int expected, etc.) |
| 4 | `ack_ordering` | Front's first tool call is not `acknowledge()` (ITEM #13 enforcement) |

---

## 10.6 Recovery Protocol

When validation fails, the system retries with a corrective prompt rather than failing immediately.

```python
async def validated_generate(
    model: IConciergeModelPort,
    request: ConciergeModelRequest,
    validator: LLMOutputValidator,
    max_retries: int = 1,
) -> ConciergeModelResponse:
    """Generate with validation and retry on malformed output.

    On validation failure:
    1. Build corrective prompt listing each error.
    2. Append it as a user message.
    3. Reduce temperature by 0.2 (floor 0.3) to tighten output.
    4. Retry once.

    On second failure:
    - Strip invalid tool calls (keep only allowlisted ones).
    - Keep text if present, else inject canned fallback.
    - Return with finish_reason="validation_fallback".
    """

    response = await model.generate(request)
    result = validator.validate(response, request.actor)

    if result.valid:
        return response

    if max_retries <= 0:
        # Give up -- strip invalid tool calls, keep text
        return ConciergeModelResponse(
            text=response.text or "I'm having a moment. Could you say that again?",
            tool_calls=[tc for tc in response.tool_calls
                        if tc.name in validator._tool_names],
            model_id=response.model_id,
            finish_reason="validation_fallback",
        )

    # Retry with corrective prompt
    correction = "\n".join(f"ERROR: {e.message}" for e in result.errors)
    corrective_message = ModelMessage(
        role="user",
        content=f"Your previous response had errors:\n{correction}\n"
                f"Please try again with valid tool calls only.",
    )
    retry_request = ConciergeModelRequest(
        capability=request.capability,
        system_prompt=request.system_prompt,
        messages=request.messages + [corrective_message],
        tools=request.tools,
        tool_choice=request.tool_choice,
        max_tokens=request.max_tokens,
        timeout_ms=request.timeout_ms,
        temperature=max(0.3, request.temperature - 0.2),  # Lower temp on retry
        actor=request.actor,
        scenario=request.scenario,
        model_hint=request.model_hint,
        trace_id=request.trace_id,
    )
    return await validated_generate(model, retry_request, validator, max_retries - 1)
```

**Retry budget:** One retry per `validated_generate()` call. The caller (Front handler, Back handler) may have its own retry logic at a higher level (e.g., ITEM #16: 1 retry per capability invocation = 2 total attempts). The `validated_generate()` retry is for OUTPUT FORMAT errors only, not for semantic errors.

---

## 10.7 Pre-Call Context Budget Management

The LLM context window is finite. The system must prevent prompt overflow BEFORE the LLM call, not rely on the LLM to compress mid-conversation.

### 10.7.1 `DynamicPromptBuilder` Budget Enforcement

`DynamicPromptBuilder` (Section 6.1) assembles the prompt from Session State sections. Before returning the assembled context, it runs a budget check:

```python
class DynamicPromptBuilder:
    """Assembles LLM context with pre-call budget management.

    The prompt builder reads Session State sections (Section 5),
    assembles them into a BuiltContext, and enforces token limits
    BEFORE the LLM call.
    """

    CONTEXT_WINDOW = 128_000          # Model context window (configurable)
    SAFETY_MARGIN = 0.80              # Use 80% max to leave room for response
    MAX_CONTEXT_TOKENS = int(CONTEXT_WINDOW * SAFETY_MARGIN)  # 102,400

    async def build(self, ss: SessionState, scenario: str, **kwargs) -> BuiltContext:
        # 1. Assemble all sections (mode-driven, Section 6.1)
        sections = self._assemble_sections(ss, scenario, **kwargs)

        # 2. Estimate total tokens
        total_tokens = sum(self._estimate_tokens(s) for s in sections.values())

        # 3. If within budget: use as-is
        if total_tokens <= self.MAX_CONTEXT_TOKENS:
            return self._finalize(sections)

        # 4. Over budget: PRE-COMPRESS before LLM call.
        #    Compress lowest-priority sections first.
        compression_order = [
            "task_artifacts",      # Oldest/least relevant first
            "beliefs_active",      # Compress to high-confidence only
            "history",             # Reduce window from 20 to 10
            "narrative_active",    # Summarize threads
            "clarifications",      # Remove resolved
        ]

        for section_name in compression_order:
            if section_name in sections:
                sections[section_name] = self._compress_section(
                    section_name, sections[section_name],
                    target_reduction=0.5,  # Cut each by 50%
                )
                total_tokens = sum(
                    self._estimate_tokens(s) for s in sections.values()
                )
                if total_tokens <= self.MAX_CONTEXT_TOKENS:
                    break

        # 5. Still over? Truncate history aggressively
        if total_tokens > self.MAX_CONTEXT_TOKENS:
            sections["history"] = sections["history"][-5:]  # Keep only 5

        return self._finalize(sections)
```

### 10.7.2 The `summarize_context()` Catch-22

`summarize_context()` is an LLM tool (Section 6.1 cognitive tools) -- but the LLM cannot call it if the context is already too large to fit in the prompt window. Resolution:

1. **Pre-compression** (above) is deterministic. No LLM needed. It trims sections by removing low-confidence beliefs, old history, resolved clarifications, and completed task artifacts.
2. **`summarize_context()`** still exists for VOLUNTARY compression during execution (if the LLM detects it needs more room for a complex response), but it is not the ONLY defense against overflow.
3. The 80% safety margin (102,400 of 128,000 tokens) ensures the LLM always has room to generate a response AND call `summarize_context()` if needed.

Two-layer defense: deterministic pre-compression guarantees the prompt fits; voluntary LLM-driven compression optimizes further during execution.

---

## 10.8 Streaming Behavior

Front streams. Back does not. This is a delivery concern, not a capability concern.

### Front Streaming

Front acks and final responses stream to the user via `generate_stream()`:

```python
async def front_stream_ack(model: IConciergeModelPort, context: BuiltContext):
    async for chunk in model.generate_stream(ConciergeModelRequest(
        capability="CHAT",
        system_prompt=context.system_prompt,
        messages=context.messages,
        tools=None,           # No tools for ack -- just text
        max_tokens=200,       # Ack is short
        timeout_ms=5000,
        actor="front",
        scenario="ack",
        model_hint="fast",    # Use flash for speed
    )):
        if chunk.chunk_type == "text_delta":
            output_channel.write(chunk.text)  # Real-time to user
        elif chunk.chunk_type == "done":
            return chunk.response
```

`StreamChunk` (Section 10.2.3, ITEM #18) carries incremental text deltas for display and a final `done` chunk with the complete `ConciergeModelResponse`.

### Back: No Streaming

Back produces structured JSON results (`submit_result()`). Intermediate tool calls and reasoning are internal. There is no user-facing output to stream. Back always uses `model.generate()` (non-streaming).

---

## 10.9 Provider Adapter Implementation

The POC provides a Gemini adapter. This is the ONLY class that imports a provider SDK. The rest of the system never sees provider-specific types.

```python
class GeminiConciergeAdapter:
    """IConciergeModelPort implementation for Google Gemini.

    This is the ONLY class that imports google.genai.
    All provider-specific translation happens here:
      - ToolSchema -> Gemini FunctionDeclaration
      - Gemini response -> ConciergeModelResponse
      - tool_choice -> Gemini ToolConfig
    """

    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    async def generate(self, request: ConciergeModelRequest) -> ConciergeModelResponse:
        model = self._select_model(request)
        contents = self._to_gemini_contents(request.messages)
        gemini_tools = (
            self._to_gemini_tools(request.tools) if request.tools else None
        )
        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            tools=gemini_tools,
            tool_config=self._tool_config(request.tool_choice, gemini_tools),
        )
        response = await asyncio.wait_for(
            self._call(model, contents, config),
            timeout=request.timeout_ms / 1000,
        )
        return self._normalize(response, model)

    def _to_gemini_tools(self, tools: list[ToolSchema]) -> list:
        """Convert ToolSchema (Section 6.0) to Gemini FunctionDeclaration.
        JSON Schema -> Gemini parameter format.
        The caller never knows about this conversion.
        """
        func_decls = []
        for tool in tools:
            func_decls.append(types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,  # JSON Schema -- Gemini accepts this
            ))
        return [types.Tool(function_declarations=func_decls)]

    def _normalize(self, response, model: str) -> ConciergeModelResponse:
        """Convert Gemini response to ConciergeModelResponse.
        This is the ONLY place that reads Gemini-specific response format.
        """
        text = ""
        tool_calls = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                text += part.text
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append(ToolCallResult(
                    id=f"call_{uuid4().hex[:8]}",
                    name=fc.name,
                    arguments=dict(fc.args) if fc.args else {},
                ))
        return ConciergeModelResponse(
            text=text,
            tool_calls=tool_calls,
            model_id=model,
            finish_reason="tool_calls" if tool_calls else "stop",
        )
```

**Adding a new provider:** Implement `IConciergeModelPort`. The new class owns its SDK import, message format conversion, and response normalization. No other code changes. The adapter is injected at startup; the system is provider-agnostic by construction.

---

## 10.10 Test Adapter

```python
class TestConciergeAdapter:
    """Deterministic test adapter. No real LLM calls.

    Keyed by (actor, scenario) so each test can configure
    exact responses for Front user_input, Back task_dispatch, etc.
    Records all calls for test assertions.
    """

    def __init__(self):
        self.responses: dict[tuple[str, str], ConciergeModelResponse] = {}
        self.calls: list[ConciergeModelRequest] = []

    def set_response(
        self, actor: str, scenario: str, response: ConciergeModelResponse
    ):
        self.responses[(actor, scenario)] = response

    async def generate(self, request: ConciergeModelRequest) -> ConciergeModelResponse:
        self.calls.append(request)
        key = (request.actor, request.scenario)
        if key in self.responses:
            return self.responses[key]
        return ConciergeModelResponse(text="OK", finish_reason="stop")

    async def generate_stream(self, request):
        response = await self.generate(request)
        yield StreamChunk(chunk_type="done", response=response)
```

**Test usage pattern:**

```python
adapter = TestConciergeAdapter()
adapter.set_response("front", "user_input", ConciergeModelResponse(
    text="",
    tool_calls=[
        ToolCallResult(id="c1", name="acknowledge", arguments={"text": "On it!"}),
        ToolCallResult(id="c2", name="dispatch_task", arguments={...}),
    ],
    finish_reason="tool_calls",
))
# Run react_loop with adapter -- deterministic, no LLM needed.
# Assert adapter.calls[0].actor == "front"
# Assert adapter.calls[0].tools contains expected ToolSchemas
```

---

## 10.11 Production Model Hub Mapping

The POC adapter is a direct-call simplification of the production pipeline. Same contract, different plumbing. Swapping POC adapter for production requires changing ONE constructor argument.

| POC | Production |
| --- | --- |
| `IConciergeModelPort` | `ILLMPort` (from Model Hub) |
| `ConciergeModelRequest` | `HubRequest` |
| `ConciergeModelResponse` | `HubResponse` |
| `GeminiConciergeAdapter` | `LLMGatewayAdapter` -> LLM Request Bus -> Model Hub |
| `MODEL_SELECTION_TABLE` | `ModelSelector` in Model Hub (capability-driven routing) |
| `TestConciergeAdapter` | `TestLLMAdapter` |

```
POC:        Actor -> IConciergeModelPort -> GeminiConciergeAdapter -> Provider API
Production: Actor -> ILLMPort -> LLMGatewayAdapter -> LLM Request Bus -> Model Hub -> ModelSelector -> Provider
```

---

## 10.12 Invariants

| # | Invariant | Enforcement |
| --- | --- | --- |
| 1 | **No actor imports a provider SDK.** | Only `GeminiConciergeAdapter` (or equivalent) imports provider libraries. All other code depends on `IConciergeModelPort`. |
| 2 | **Every LLM call passes through validation.** | `validated_generate()` wraps `model.generate()` in handlers. `react_loop()` delegates validation to `ToolDispatcher`. |
| 3 | **Model selection is centralized.** | `MODEL_SELECTION_TABLE` is the single configuration point. Callers express intent (`model_hint`), not model names. |
| 4 | **Context budget is enforced pre-call.** | `DynamicPromptBuilder.build()` runs deterministic compression before any LLM call. 80% safety margin guarantees room. |
| 5 | **Tool result injection is uniform.** | `tool_result_to_message()` is the single conversion function. Both actors, all tools, all iterations use the same path. |
| 6 | **Streaming is Front-only.** | `generate_stream()` is called only by Front ack/response paths. Back always uses `generate()`. |
| 7 | **Test adapter is keyed by (actor, scenario).** | Deterministic responses without LLM calls. Every test controls exactly what the "model" returns. |
| 8 | **Retry budget is bounded.** | `validated_generate()` allows 1 retry max. Temperature reduces on retry. Second failure returns fallback with `finish_reason="validation_fallback"`. |

---

# 11. Orchestrator & Planner Integration

The system handles tasks at three complexity tiers. LOW and MEDIUM are implemented. HIGH defines interfaces for future integration. All tiers converge to the same result event (`k1.orchestration.dag.completed`), so the FSM does not know or care which tier executed.

---

## 11.1 Tier Scope Boundaries

| Tier | Flow | POC Status |
| --- | --- | --- |
| **LOW** | Front -> `task.dispatch.v1` -> Back -> `invoke_capability()` directly via Fabric | Fully implemented |
| **MEDIUM** | Front -> `task.dispatch.v1` -> `OrchestratorStub` (1-2 Fabric calls) -> `AggregatedResult` -> FSM | Stub implementation |
| **HIGH** | Front -> `TaskEnvelope` -> Orchestrator -> `PlanRequest` -> Planner 4-stage -> `CommittedPlan` -> DAG execution | Interface defined only |

**LOW** covers single-intent, single-capability tasks (Section 8 single pattern). Back calls `invoke_capability()` or `spawn_via_fabric()` directly.

**MEDIUM** covers tasks that require 1-2 coordinated Fabric calls without planning or LLM reasoning. The OrchestratorStub handles these with hard invariants (no LLM, no tools, no DAG, max 2 Fabric calls).

**HIGH** covers multi-step tasks requiring planning, dependency graphs, and saga recovery. The POC does not implement HIGH-tier execution but defines the interfaces so it plugs in without refactoring.

---

## 11.2 Dispatch Routing

The complexity tier (determined by Front's analysis) controls which path the task takes. `route_task()` is the single dispatch point.

```python
async def route_task(task: TaskDispatch, tier: ComplexityTier):
    """FSM routes task based on tier. Single dispatch point.

    ComplexityTier is determined by Front's cognitive analysis
    (Section 6.1 dispatch flow). The tier drives routing only --
    it does not affect the result event format.

    All tiers ultimately produce results that arrive via
    k1.orchestration.delta.v1 or k1.orchestration.task.complete.v1
    and transition the FSM to COMPANIONING -> DELIVERING (Section 4).
    """

    if tier == ComplexityTier.LOW:
        # Back LLM handles directly via invoke_capability()
        # (Section 6.2 action tools, Section 8 single pattern)
        emit(Envelope(
            topic="k1.orchestration.task.dispatch.v1",
            payload=task,
            priority=Priority.INTERACTIVE,
        ))

    elif tier == ComplexityTier.MEDIUM:
        # Route through OrchestratorStub (1-2 Fabric calls, no planning)
        envelope = TaskEnvelope(
            intent=task.intents[0].action,
            context=task.context_snapshot,
            tier=tier,
            budget=Budget(max_fabric_calls=2),  # ORCH-10
        )
        await dispatch_port.dispatch_envelope(envelope)
        # Result arrives via k1.orchestration.delta.v1 -> COMPANIONING

    elif tier == ComplexityTier.HIGH:
        # Route through Orchestrator -> Planner pipeline (future)
        envelope = TaskEnvelope(
            intent=task.intents[0].action,
            context=task.context_snapshot,
            tier=tier,
            budget=Budget(max_fabric_calls=10, max_planner_tokens=3500),
        )
        await dispatch_port.dispatch_envelope(envelope)
        # Result arrives via k1.orchestration.delta.v1
        # -> COMPANIONING -> PROGRESSING (Section 4, FSM states)
```

### 11.2.1 `ComplexityTier` and `TaskEnvelope`

```python
class ComplexityTier(str, Enum):
    LOW = "LOW"         # Single Fabric call, Back handles directly
    MEDIUM = "MEDIUM"   # 1-2 coordinated Fabric calls, no LLM
    HIGH = "HIGH"       # Multi-step, requires planning + DAG execution


@dataclass
class TaskEnvelope:
    """Wrapper for tasks routed to the Orchestrator (MEDIUM/HIGH)."""
    task_id: str = field(default_factory=lambda: f"task-{uuid4().hex[:8]}")
    intent: str = ""                         # Primary action
    context: dict = field(default_factory=dict)  # Context snapshot from Front
    tier: ComplexityTier = ComplexityTier.MEDIUM
    budget: Budget = field(default_factory=Budget)
    session_id: str = ""
    trace_id: str = ""


@dataclass
class Budget:
    """Execution budget constraints."""
    max_fabric_calls: int = 2                # ORCH-10: hard limit per tier
    max_planner_tokens: int = 0              # HIGH only
    timeout_ms: int = 60000                  # Total execution time
```

---

## 11.3 `OrchestratorStub` (MEDIUM Tier)

The MEDIUM-tier Orchestrator is a minimal stub with hard invariants. It receives a `TaskEnvelope`, makes 1-2 Fabric calls, and returns an `AggregatedResult`.

```python
class OrchestratorStub:
    """Minimal Orchestrator for MEDIUM tier.

    Receives TaskEnvelope, makes 1-2 Fabric calls,
    returns AggregatedResult.

    Invariants:
      ORCH-01: No Session State writes (read-only snapshot)
      ORCH-02: No LLM calls
      ORCH-03: No tool execution (tools are a Concierge concern)
      ORCH-04: Every step goes through Fabric (no direct service calls)
      ORCH-10: Max 2 Fabric calls per task
    """

    def __init__(
        self,
        fabric_gateway: IFabricGatewayPort,
        state_read: IStateReadPort,
        delta_emit: IDeltaEmitPort,
    ):
        self.fabric = fabric_gateway
        self.state = state_read
        self.delta = delta_emit

    async def handle_task(self, envelope: TaskEnvelope):
        # 1. Emit acceptance
        self.delta.emit("k1.orchestration.task.accepted", {
            "task_id": envelope.task_id,
            "tier": "MEDIUM",
        })

        # 2. Read context snapshot (ORCH-01: read-only, no writes)
        context = self.state.snapshot(["beliefs_active", "task_artifacts"])

        # 3. Resolve capability (known at MEDIUM tier, no discovery needed)
        cap_request = CapabilityRequest(
            name=envelope.intent,
            params=envelope.context.get("params", {}),
            session_id=envelope.session_id,
            trace_id=envelope.trace_id,
        )

        # 4. Execute via Fabric (ORCH-04, ORCH-10: max 2 calls)
        result = await self.fabric.execute(cap_request)

        # 5. Aggregate result
        aggregated = AggregatedResult(
            total_steps=1,
            completed=1 if result.success else 0,
            failed=0 if result.success else 1,
            results=[result],
            success=result.success,
        )

        # 6. Emit completion (same event as HIGH tier -- FSM doesn't care)
        self.delta.emit("k1.orchestration.dag.completed", aggregated)
```

**Key constraint:** The stub enforces ORCH-01 through ORCH-10 at the code level. There is no LLM import, no tool schema, no DAG executor. If a MEDIUM task needs more than 2 Fabric calls, it should have been classified as HIGH.

---

## 11.4 HIGH Tier Interface Contracts (Deferred)

The POC does NOT implement these but defines interfaces so they plug in without refactoring.

### 11.4.1 Deferred Component Interfaces

| Component | Interface | Purpose |
| --- | --- | --- |
| DAGExecutor | `execute(committed_plan: CommittedPlan) -> AggregatedResult` | Topological execution of plan steps |
| Planner | `IPlannerPort.request_plan(PlanRequest) -> PlanAck` | 4-stage planning pipeline |
| WorkflowEngine | `IWorkflowPort.run(WorkflowRunRequest) -> WorkflowResult` | Multi-step workflow execution |
| ConnectorManager | `IConnectorPort.register(mcp_server) -> void` | MCP server registration |
| ConstraintResolver | `IConstraintPort.resolve(step, context) -> ResolvedParams` | Runtime parameter resolution |
| Saga Recovery | `ISagaPort.compensate(failed_step, completed_steps) -> void` | Rollback on partial failure |

**Key contract:** All tiers produce `AggregatedResult` and emit `k1.orchestration.dag.completed`. The FSM does not know or care which tier executed. It receives results in COMPANIONING and presents them in DELIVERING (Section 4).

### 11.4.2 Planner Types

```python
@dataclass
class PlanRequest:
    """Request from Orchestrator to Planner (HIGH tier only)."""
    request_id: str
    intent: str
    context: dict
    constraints: dict
    budget: Budget


@dataclass
class CommittedPlan:
    """Planner output after 4-stage pipeline: SKETCH -> EXPAND -> VALIDATE -> COMMIT."""
    plan_id: str
    request_id: str
    steps: list[PlanStep]
    dependencies: dict[str, list[str]]  # step_id -> [dependency_step_ids]
    created_at: str


@dataclass
class PlanStep:
    """Single step in a committed plan."""
    step_id: str
    capability: str                    # Fabric capability name
    params: dict                       # Some may be $ref to prior step results
    has_side_effects: bool             # From CapabilityContract
    compensation: str | None           # Rollback capability if saga needed
    timeout_ms: int
    required_context: list[str]        # SS sections this step needs
    safety_band_min: str               # Minimum safety band for execution
```

---

## 11.5 Event Flow (HIGH Tier, Future)

When HIGH tier is implemented, the full event flow is:

```
Concierge DISPATCHING
  -> TaskEnvelope
  -> Orchestrator Mailbox

Orchestrator
  -> PlanRequest
  -> Planner Mailbox

Planner: SKETCH -> EXPAND -> VALIDATE -> COMMIT
  -> emits: k1.planner.plan.ready.v1 (CommittedPlan)

Orchestrator receives CommittedPlan
  -> DAGExecutor builds waves (topological sort)
  -> Per wave: CapabilityRequest -> Fabric -> CapabilityResult
  -> Per wave: k1.orchestration.delta.v1 -> Concierge PROGRESSING

All waves done:
  -> AggregatedResult -> k1.orchestration.dag.completed
  -> Concierge COMPANIONING -> DELIVERING
```

The PROGRESSING FSM state (Section 4) handles intermediate delta events. The FSM can present progress to the user while execution continues. When the final `dag.completed` arrives, the FSM transitions to COMPANIONING for result compilation and then DELIVERING for presentation.

---

## 11.6 Tier Degradation Cascade

If circuit breakers trip, the system degrades gracefully through tiers:

```
HIGH  (CB_PLANNER open)       -> degrade to MEDIUM (skip planning, direct Fabric)
MEDIUM (CB_ORCHESTRATOR open) -> degrade to LOW    (Back calls Fabric directly)
LOW   (CB_FABRIC open)        -> canned response   ("I'm having trouble right now...")
```

**Implementation status:**

- LOW -> canned: Implemented. When Fabric is unavailable, `submit_result(status="FAILED", ...)` triggers `task.failed.v1` (Section 8), and Front presents a canned error.
- MEDIUM -> LOW: Implemented in OrchestratorStub. If the stub's Fabric call fails, it emits a failure delta and the task falls back to Back's direct handling.
- HIGH -> MEDIUM: Interface only. When Planner circuit breaker opens, the Orchestrator skips plan generation and executes the intent as a MEDIUM-tier task (1-2 direct Fabric calls).

**The cascade is transparent to the user.** The FSM receives the same result events regardless of which tier executed. Degradation affects execution quality (fewer optimization steps), not the system's ability to respond.

---

## 11.7 Invariants

| # | Invariant | Enforcement |
| --- | --- | --- |
| ORCH-01 | **Orchestrator never writes Session State.** | `OrchestratorStub` receives `IStateReadPort` (no write methods). |
| ORCH-02 | **Orchestrator never calls an LLM.** | No `IConciergeModelPort` in OrchestratorStub constructor. |
| ORCH-03 | **Orchestrator never executes tools.** | No `ToolDispatcher` in OrchestratorStub. Tools are a Concierge concern. |
| ORCH-04 | **Every execution step goes through Fabric.** | `IFabricGatewayPort.execute()` is the only execution path. No direct service calls. |
| ORCH-10 | **MEDIUM tier: max 2 Fabric calls.** | `Budget(max_fabric_calls=2)` enforced at construction. |
| 6 | **All tiers emit the same result event.** | `k1.orchestration.dag.completed` with `AggregatedResult`. FSM is tier-agnostic. |
| 7 | **Tier degradation is automatic.** | Circuit breaker state drives degradation. No manual intervention. |
| 8 | **`route_task()` is the single dispatch point.** | All task routing goes through `route_task()`. No alternate dispatch paths. |

---

# 12. Experience Layer Hooks

The Experience Layer enriches the Front LLM's behavior with emotional awareness, narrative coherence, anticipatory intelligence, proactive engagement, and rhythmic delivery. It is **Front-only** -- Back is not user-facing and has no use for tone adjustment, rhythm control, or proactive fills.

The POC does NOT implement Experience Layer algorithms. It implements the **hook infrastructure** -- stub components with correct signatures, correct fire cadence, correct integration points into Front's prompt pipeline and ReAct loop, and correct Session State contracts. Each component returns neutral defaults (`pass` + default dataclass). When production algorithms are developed, they plug into these stubs without refactoring the FSM, the prompt builder, or the ReAct loop.

**Design for pluggability:**

1. Each component is a class with a single async method (or sync for RhythmController).
2. Each method takes typed inputs from Session State and returns a typed output dataclass.
3. The `ExperienceLayer.tick()` orchestrator calls components at their cadence and writes outputs to Session State or emits bus envelopes.
4. Front's `DynamicPromptBuilder` (Section 6.1) reads Experience Layer outputs from Session State sections (`affective_now`, etc.) -- it does not call components directly.
5. Some components produce envelopes that hook into the ReAct loop itself (anticipation can pre-warm tools; proactive fills inject messages during Back execution waits).

---

## 12.1 Component Inventory

| Component | Fire Cadence | Budget | Reads | Writes | Front Integration Point |
| --- | --- | --- | --- | --- | --- |
| EmotionalProcessor | Every 25th turn_end | 5 ms | Turn transcript, affect history | `affective_now` SS section | `DynamicPromptBuilder` reads `affective_now` for tone, emotional arc in Session Trajectory (Section 5) |
| AffectiveMirror | After EmotionalProcessor | 2 ms | `affective_now`, persona config | `tone_adjustment` on bus | Front prompt's identity section incorporates tone modifiers (warmth, formality, pace) |
| NarrativeWeaver | Every 20th turn_end | 10 ms | Conversation history, memory recalls | `narrative_context` on bus | `DynamicPromptBuilder` reads narrative threads for Session Trajectory `session_goal` field |
| AnticipatoryResponder | Every 30th turn_end | 15 ms | Task state, user patterns | `anticipation` on bus | Front ReAct loop: pre-warm tool schemas for predicted next intent; `DynamicPromptBuilder`: inject anticipation hint into prompt |
| ProactiveAgent | COMPANIONING + wait > 5s | 50 ms | Task state, wait duration | `k1.proactive.fill.v1` on bus | FSM routes fill to Front handler; Front presents fill message during long Back waits |
| RhythmController | Every output | 1 ms | Turn timing, user cadence | Timing params to delivery pipeline | Output pipeline applies pre-delay, inter-chunk pacing, typing indicator before streaming to user |

**Total experience budget:** 83 ms maximum if all components fire on the same tick. In practice, cadence staggering means 1-3 components fire per tick.

---

## 12.2 Output Types

Each component produces a frozen dataclass. These types are the pluggability contract -- future algorithms must return these exact types. The stub implementations return default instances.

```python
@dataclass
class EmotionalTrajectory:
    """Output of EmotionalProcessor. Written to affective_now SS section."""
    valence: float = 0.0       # -1.0 (negative) to +1.0 (positive)
    arousal: float = 0.5       # 0.0 (calm) to 1.0 (excited)
    dominance: float = 0.5     # 0.0 (submissive) to 1.0 (dominant)
    trend: str = "stable"      # "rising" | "falling" | "stable"
    confidence: float = 0.0    # 0.0 = stub (no algorithm), 1.0 = production


@dataclass
class ToneAdjustment:
    """Output of AffectiveMirror. Consumed by DynamicPromptBuilder identity section."""
    warmth: float = 0.5        # 0.0 (clinical) to 1.0 (warm)
    formality: float = 0.5     # 0.0 (casual) to 1.0 (formal)
    pace: str = "normal"       # "slow" | "normal" | "fast"
    mirror_intensity: float = 0.0  # 0.0 = no mirroring, 1.0 = full match


@dataclass
class NarrativeContext:
    """Output of NarrativeWeaver. Consumed by DynamicPromptBuilder Session Trajectory."""
    active_threads: list[str] = field(default_factory=list)
    thread_salience: dict[str, float] = field(default_factory=dict)
    weave_suggestion: str = ""  # Suggested narrative connection for next response


@dataclass
class Anticipation:
    """Output of AnticipatoryResponder. Two integration points:
    1. DynamicPromptBuilder: inject anticipation hint into prompt
    2. ReAct loop: pre-warm predicted tool schemas (future)
    """
    predicted_intent: str = ""         # What user likely wants next
    confidence: float = 0.0           # 0.0 = no prediction (stub)
    pre_fetch_capabilities: list[str] = field(default_factory=list)
    suggested_prompt_hint: str = ""    # Optional hint injected into Front prompt


@dataclass
class FillMessage:
    """Output of ProactiveAgent. Emitted as k1.proactive.fill.v1 on bus.
    FSM routes to Front handler for presentation during long Back waits.
    """
    message: str = ""                  # What to say during the wait
    style: str = "informational"       # "informational" | "reassuring" | "entertaining"
    show_progress: bool = False        # Whether to include progress indicator


@dataclass
class TimingParams:
    """Output of RhythmController. Applied by delivery pipeline before streaming."""
    pre_delay_ms: int = 0              # Pause before response
    inter_chunk_ms: int = 0            # Pause between streaming chunks
    typing_indicator: bool = False     # Show typing indicator
    beat_pattern: str = "steady"       # "steady" | "syncopated" | "accelerating"
```

---

## 12.3 Stub Components

Each stub has the correct interface signature. All methods contain `pass` and return neutral defaults. When a production algorithm is developed, it replaces the body after `pass` -- the signature, the return type, and the integration points remain unchanged.

### 12.3.1 EmotionalProcessor

```python
class EmotionalProcessor:
    """Computes emotional trajectory from conversation signals.

    Fire cadence: every 25th turn_end.
    Budget: 5 ms.
    Reads: turn transcript, affect history (from SS affective_now).
    Writes: affective_now SS section (EmotionalTrajectory).

    EP skip rule (Section 5): if Front's refine_affect() was called
    this turn with confidence > 0.8, tick() skips this component's
    write to avoid overwriting a high-confidence Front correction.

    Pluggability:
      - Future: sentiment analysis, affect trajectory modeling,
        multi-turn emotion tracking, context-aware valence computation.
      - Integration: DynamicPromptBuilder reads affective_now for
        emotional_arc in Session Trajectory and affect band selection.
    """

    async def process(
        self,
        turn_transcript: str,
        affect_history: list[dict],
    ) -> EmotionalTrajectory:
        pass
        return EmotionalTrajectory()
```

### 12.3.2 AffectiveMirror

```python
class AffectiveMirror:
    """Computes tone adjustment based on emotional state and persona.

    Fire cadence: immediately after EmotionalProcessor completes.
    Budget: 2 ms.
    Reads: affective_now (EmotionalTrajectory), persona config (SS).
    Writes: ToneAdjustment emitted on bus.

    Pluggability:
      - Future: empathetic mirroring algorithms, persona-modulated
        tone, cultural sensitivity adjustments.
      - Integration: DynamicPromptBuilder's identity section reads
        ToneAdjustment to modulate warmth/formality/pace in the
        system prompt. The Front LLM's natural language generation
        is shaped by these parameters without explicit instructions --
        the tone is encoded in the prompt's phrasing, not as a rule.
    """

    async def mirror(
        self,
        emotional_state: dict,
        persona: dict,
    ) -> ToneAdjustment:
        pass
        return ToneAdjustment()
```

### 12.3.3 NarrativeWeaver

```python
class NarrativeWeaver:
    """Weaves narrative threads across turns for coherent storytelling.

    Fire cadence: every 20th turn_end.
    Budget: 10 ms.
    Reads: conversation history, memory recalls.
    Writes: NarrativeContext emitted on bus.

    Pluggability:
      - Future: multi-thread narrative tracking, salience decay,
        thread resumption suggestions, story arc detection.
      - Integration: DynamicPromptBuilder reads NarrativeContext
        for session_goal computation in Session Trajectory.
        NarrativeWeaver's weave_suggestion can influence Front's
        update_narrative() tool calls by providing thread context.
    """

    async def weave(
        self,
        conversation_history: list[dict],
        memory_recalls: list[dict],
    ) -> NarrativeContext:
        pass
        return NarrativeContext()
```

### 12.3.4 AnticipatoryResponder

```python
class AnticipatoryResponder:
    """Pre-computes likely next user requests based on patterns.

    Fire cadence: every 30th turn_end.
    Budget: 15 ms.
    Reads: task state, user behavior patterns (from SS + memory).
    Writes: Anticipation emitted on bus.

    Pluggability:
      - Future: intent prediction models, sequential pattern mining,
        context-aware capability pre-warming.
      - Integration (prompt): DynamicPromptBuilder injects
        suggested_prompt_hint into Front's prompt when confidence > 0.5.
        This lets the LLM proactively offer the predicted next step.
      - Integration (ReAct loop): pre_fetch_capabilities list is passed
        to ToolDispatcher to pre-warm Fabric connections for predicted
        capabilities. This reduces latency if the prediction is correct.
        No wasted work if incorrect -- pre-warming is speculative only.
    """

    async def anticipate(
        self,
        task_state: dict,
        user_patterns: dict,
    ) -> Anticipation:
        pass
        return Anticipation()
```

### 12.3.5 ProactiveAgent

```python
class ProactiveAgent:
    """Generates fill/status messages during long waits.

    Fire cadence: COMPANIONING state + wait duration > 5 seconds.
    Budget: 50 ms.
    Reads: task state, current wait duration.
    Writes: FillMessage emitted as k1.proactive.fill.v1 on bus.

    Pluggability:
      - Future: contextual fill generation (progress updates,
        fun facts about the domain, reassurance for complex tasks).
      - Integration (bus -> Front): FSM receives k1.proactive.fill.v1,
        routes to Front handler in PRESENT mode (Section 4).
        Front's ReAct loop presents the fill message to the user.
        This is a FULL Front invocation -- the fill message goes through
        DynamicPromptBuilder, gets tone/affect adjustment, and streams
        to the user like any other Front response.
      - Integration (ReAct loop): The fill triggers a separate Front
        invocation. It does NOT interrupt an in-progress Front loop.
        The FSM queues fills and delivers them between Front invocations.
    """

    async def generate_fill(
        self,
        task_state: dict,
        wait_duration_ms: int,
    ) -> FillMessage:
        pass
        return FillMessage()
```

### 12.3.6 RhythmController

```python
class RhythmController:
    """Controls pacing and rhythm of responses.

    Fire cadence: every output (before delivery to user).
    Budget: 1 ms.
    Reads: turn timing, user cadence patterns.
    Writes: TimingParams applied to output delivery pipeline.

    Pluggability:
      - Future: cadence matching (mirror user's pace), emotional
        pacing (slow down during crisis, speed up during excitement),
        conversational beat patterns (comedic timing, dramatic pauses).
      - Integration (delivery pipeline): TimingParams are applied
        AFTER the Front ReAct loop completes and BEFORE streaming
        to the user. pre_delay_ms inserts a pause before the first
        chunk. inter_chunk_ms controls pacing between stream chunks.
        typing_indicator triggers a UI typing indicator.
      - Does NOT affect the ReAct loop itself -- only the delivery.
    """

    def get_pattern(
        self,
        turn_count: int,
        user_cadence: dict,
    ) -> TimingParams:
        pass
        return TimingParams()

    def get_beat(self, output_length: int) -> str:
        pass
        return "steady"

    def adjust_timing(
        self,
        current: TimingParams,
        feedback: dict,
    ) -> TimingParams:
        pass
        return current
```

---

## 12.4 `ExperienceLayer.tick()` Orchestrator

The FSM calls `experience_layer.tick()` after every turn completion. This is the single integration point for all experience components. The orchestrator fires components at their defined cadence, respects the EP skip rule (Section 5), and returns envelopes for the bus.

```python
class ExperienceLayer:
    """Orchestrates all experience components.

    Called by FSM after every turn_end.
    Fires components at their defined cadence.
    Returns dict of typed outputs for bus emission.

    Pluggability contract:
      - Adding a new component: add instance variable, add cadence
        check in tick(), add output to envelopes dict. No other
        changes needed -- DynamicPromptBuilder reads from SS sections,
        bus consumers subscribe to topics.
      - Replacing an algorithm: swap the component class. The
        ExperienceLayer does not know or care about the algorithm --
        it only calls the method and collects the output.
    """

    def __init__(self):
        self.emotional_processor = EmotionalProcessor()
        self.affective_mirror = AffectiveMirror()
        self.narrative_weaver = NarrativeWeaver()
        self.anticipatory_responder = AnticipatoryResponder()
        self.proactive_agent = ProactiveAgent()
        self.rhythm_controller = RhythmController()
        self.turn_count = 0

    async def tick(self, fsm_state: str, context: dict) -> dict:
        """Called by FSM after every turn_end.

        Args:
            fsm_state: Current FSM state (Section 4).
            context: Dict with keys from Session State + turn metadata.
                Expected keys:
                  - turn_transcript: str (current turn text)
                  - affect_history: list[dict] (recent affect states)
                  - front_refine_affect_confidence: float (0.0 if not called)
                  - conversation_history: list[dict]
                  - memory_recalls: list[dict]
                  - task_state: dict
                  - user_patterns: dict
                  - wait_duration_ms: int (0 if not waiting)
                  - persona: dict
                  - user_cadence: dict

        Returns:
            Dict of component name -> typed output. Bus emitter
            publishes each as the appropriate topic.
        """
        self.turn_count += 1
        envelopes = {}

        # ---- EmotionalProcessor: every 25th turn ----
        # EP skip rule (Section 5, ITEM #17):
        #   If Front's refine_affect() was called this turn with
        #   confidence > 0.8, skip EP write to affective_now.
        #   Front's correction is higher quality than EP's trajectory
        #   computation. One rule, one definition -- Section 5 owns it.
        front_affect_confidence = context.get(
            "front_refine_affect_confidence", 0.0
        )
        if (
            self.turn_count % 25 == 0
            and front_affect_confidence <= 0.8
        ):
            trajectory = await self.emotional_processor.process(
                context.get("turn_transcript", ""),
                context.get("affect_history", []),
            )
            envelopes["emotional"] = trajectory

            # AffectiveMirror: fires immediately after EmotionalProcessor.
            # Chained -- not independent cadence.
            tone = await self.affective_mirror.mirror(
                trajectory.__dict__,
                context.get("persona", {}),
            )
            envelopes["tone"] = tone

        # ---- NarrativeWeaver: every 20th turn ----
        if self.turn_count % 20 == 0:
            narrative = await self.narrative_weaver.weave(
                context.get("conversation_history", []),
                context.get("memory_recalls", []),
            )
            envelopes["narrative"] = narrative

        # ---- AnticipatoryResponder: every 30th turn ----
        if self.turn_count % 30 == 0:
            anticipation = await self.anticipatory_responder.anticipate(
                context.get("task_state", {}),
                context.get("user_patterns", {}),
            )
            envelopes["anticipation"] = anticipation

        # ---- ProactiveAgent: COMPANIONING + long wait ----
        # Only fires when Back is executing a task and the user
        # has been waiting > 5 seconds. FSM routes the fill
        # to Front for presentation.
        if fsm_state == "COMPANIONING":
            wait_ms = context.get("wait_duration_ms", 0)
            if wait_ms > 5000:
                fill = await self.proactive_agent.generate_fill(
                    context.get("task_state", {}),
                    wait_ms,
                )
                envelopes["fill"] = fill

        # ---- RhythmController: every output ----
        # Always fires. Provides timing parameters for the
        # delivery pipeline to apply before streaming.
        timing = self.rhythm_controller.get_pattern(
            self.turn_count,
            context.get("user_cadence", {}),
        )
        envelopes["timing"] = timing

        return envelopes
```

---

## 12.5 Front Integration Points

The Experience Layer connects to Front through three mechanisms. All three are designed for zero-change pluggability -- swapping a stub for a production algorithm requires NO modifications to Front's code.

### 12.5.1 Session State Injection (Prompt Path)

Experience Layer outputs that are written to Session State (`affective_now`) are automatically included in Front's prompt via `DynamicPromptBuilder` (Section 6.1). The prompt builder reads SS sections -- it does not know or care whether the values came from Phase 1 classification, Front's `refine_affect()`, or EmotionalProcessor.

```
EmotionalProcessor.process()
  -> writes EmotionalTrajectory to SS affective_now
  -> DynamicPromptBuilder reads affective_now
  -> emotional_arc appears in Session Trajectory (Section 5)
  -> affect_band influences mode selection and max_iterations
  -> Front LLM sees emotional context in system prompt
```

**Why this works for pluggability:** `DynamicPromptBuilder` reads `affective_now` regardless of what wrote it. When EmotionalProcessor's stub returns `confidence=0.0`, the affect band stays at Phase 1's classification. When a production algorithm returns `confidence=0.9`, the trajectory data enriches the prompt. No code changes in `DynamicPromptBuilder`.

### 12.5.2 Bus Envelope Injection (ReAct Loop Path)

Experience Layer outputs emitted as bus envelopes can trigger Front invocations or feed into the ReAct loop's next iteration:

| Output | Bus Topic | Front Integration |
| --- | --- | --- |
| ToneAdjustment | `k1.affect.tone.v1` | `DynamicPromptBuilder` reads from SS after bus handler writes it. Modulates identity section warmth/formality. |
| NarrativeContext | `k1.affect.narrative.v1` | `DynamicPromptBuilder` reads thread salience for Session Trajectory `session_goal`. |
| Anticipation | `k1.affect.anticipation.v1` | Two paths: (1) `DynamicPromptBuilder` injects `suggested_prompt_hint` if confidence > 0.5. (2) `ToolDispatcher` pre-warms `pre_fetch_capabilities` (future). |
| FillMessage | `k1.proactive.fill.v1` | FSM triggers a NEW Front invocation in PRESENT mode. Full ReAct loop with DynamicPromptBuilder. Not an interrupt -- queued between Front invocations. |

**Why bus envelopes, not direct injection:** Components fire at turn_end AFTER Front completes. Their outputs affect the NEXT Front invocation, not the current one. The bus + SS path ensures temporal correctness -- when Front next reads SS, the enriched values are already there.

### 12.5.3 Delivery Pipeline (Post-Loop Path)

RhythmController operates AFTER the ReAct loop completes, BEFORE streaming to the user:

```
Front ReAct loop completes
  -> response text ready
  -> RhythmController.get_pattern() returns TimingParams
  -> Delivery pipeline applies:
       pre_delay_ms pause
       typing_indicator if enabled
       inter_chunk_ms pacing between stream chunks
  -> User receives response with controlled rhythm
```

**Why post-loop, not in-loop:** Rhythm is a delivery concern, not a reasoning concern. The LLM does not need to know about pacing. RhythmController reads user cadence (how fast the user types/responds) and applies mirroring at the output layer. This separation means production rhythm algorithms cannot interfere with ReAct loop correctness.

---

## 12.6 Cadence Test Assertions

Tests verify hooks fire at the correct cadence, not correctness of output (stubs return defaults). These tests are the pluggability contract -- they prove the hook infrastructure works before any algorithm is implemented.

```python
async def test_emotional_processor_fires_every_25_turns():
    """EmotionalProcessor fires at turns 25, 50, 75, 100."""
    layer = ExperienceLayer()
    fired = []
    for i in range(100):
        result = await layer.tick("LISTENING", {"turn_transcript": f"turn {i}"})
        if "emotional" in result:
            fired.append(i + 1)  # turn_count is 1-indexed
    assert fired == [25, 50, 75, 100]


async def test_affective_mirror_fires_with_emotional():
    """AffectiveMirror fires on the same tick as EmotionalProcessor, not independently."""
    layer = ExperienceLayer()
    for i in range(24):
        result = await layer.tick("LISTENING", {})
        assert "tone" not in result
    result = await layer.tick("LISTENING", {})
    assert "tone" in result  # Fires with emotional on turn 25


async def test_ep_skip_rule_respects_front_confidence():
    """When Front's refine_affect() ran with confidence > 0.8,
    EmotionalProcessor does NOT fire (Section 5 EP skip rule, ITEM #17).
    """
    layer = ExperienceLayer()
    # Advance to turn 25
    for i in range(24):
        await layer.tick("LISTENING", {})
    # Turn 25 with high Front confidence -- EP skips
    result = await layer.tick("LISTENING", {
        "front_refine_affect_confidence": 0.9,
    })
    assert "emotional" not in result
    assert "tone" not in result  # Mirror also skips (chained)


async def test_proactive_fires_only_in_companioning_with_wait():
    """ProactiveAgent fires ONLY when FSM is COMPANIONING AND wait > 5s."""
    layer = ExperienceLayer()
    # Not COMPANIONING -> no fill
    result = await layer.tick("LISTENING", {"wait_duration_ms": 10000})
    assert "fill" not in result
    # COMPANIONING but short wait -> no fill
    result = await layer.tick("COMPANIONING", {"wait_duration_ms": 3000})
    assert "fill" not in result
    # COMPANIONING + long wait -> fill
    result = await layer.tick("COMPANIONING", {"wait_duration_ms": 6000})
    assert "fill" in result


async def test_rhythm_fires_every_tick():
    """RhythmController fires on every tick regardless of state or cadence."""
    layer = ExperienceLayer()
    for i in range(10):
        result = await layer.tick("LISTENING", {})
        assert "timing" in result  # Always present
```

---

## 12.7 Adding a New Experience Component

To add a new component (e.g., `HumorCalibrator`):

1. **Define output type:** `@dataclass class HumorLevel: ...`
2. **Create stub class:** Method signature + `pass` + default return.
3. **Add to `ExperienceLayer.__init__`:** `self.humor_calibrator = HumorCalibrator()`
4. **Add cadence check to `tick()`:** `if self.turn_count % N == 0: ...`
5. **Add bus topic:** `k1.affect.humor.v1` in topic taxonomy (Section 3).
6. **Add SS handler:** Bus subscriber writes output to SS section.
7. **`DynamicPromptBuilder` reads it:** Add SS section to relevant mode read configs (Section 6.1).

No changes to the FSM, ReAct loop, or existing components. The prompt builder reads SS sections -- adding a new section is a configuration change (add to `SS_READ_CONFIGS`), not a code change in the builder itself.

---

## 12.8 Invariants

| # | Invariant | Enforcement |
| --- | --- | --- |
| 1 | **Experience Layer is Front-only.** | No component reads Back state. No component writes to Back's prompt. Back has no experience integration points. |
| 2 | **Components fire at defined cadence only.** | `tick()` checks `turn_count % N`. Cadence tests verify exact fire turns. |
| 3 | **EP skip rule is not redefined here.** | Section 5 owns the EP skip rule definition. `tick()` reads `front_refine_affect_confidence` and applies it. ITEM #17 resolved. |
| 4 | **Stubs return neutral defaults.** | Every stub method contains `pass` then returns a default dataclass. `confidence=0.0` signals "stub, not production." |
| 5 | **Pluggability requires no integration changes.** | Replacing a stub body does not change `tick()`, `DynamicPromptBuilder`, FSM, or ReAct loop code. |
| 6 | **Experience outputs affect the NEXT Front invocation, not the current one.** | Components fire at turn_end AFTER Front completes. Outputs are written to SS or emitted on bus for the next read cycle. |
| 7 | **ProactiveAgent triggers a full Front invocation.** | Fill messages go through `DynamicPromptBuilder` and ReAct loop. They are not raw text injections. |
| 8 | **RhythmController is post-loop only.** | Timing parameters are applied in the delivery pipeline AFTER the ReAct loop. They cannot interfere with LLM reasoning. |
| 9 | **Total experience budget is bounded.** | 83 ms maximum (all components). Individual budgets enforced per component. Cadence staggering limits typical tick to 1-3 components. |

---

# 13. Scenarios: End-to-End Walkthroughs

These scenarios trace user interactions through the architecture defined in Sections 1-12. Each scenario demonstrates -- not defines -- the mechanisms. The mechanisms are defined in their owning sections; these walkthroughs prove they compose correctly.

**Storyline source:** `demo_storyline.md` -- "One Ordinary Day" with the Smith family (Alex, Jordan, Riley, Nana Liz). 30 turns across 7 acts spanning 6 AM to 10:30 PM. Text-based assistant, device-based identity, no voice interface.

**Structural rule (Section 0):** Scenarios illustrate; they don't define. If a mechanism appears here that is not defined in Sections 4-12, that is a bug in those sections, not a license to define it here.

---

## 13.1 Scenario A: Morning Briefing (Turn 1)

**User input:** Alex, 6:02 AM -- `"What's today look like?"`

**What this demonstrates:** The simplest complete flow through the entire architecture. Phase 1 classification, Front ReAct loop with cognitive + dispatch tools, Back execution via Fabric, result presentation via WEAVE.

### Event Trace

```
1. User message arrives
   -> k1.session.user.input.v1 (Section 3, topic taxonomy)
   -> FSM: LISTENING -> ACKING (Section 4, state table)

2. Phase 1 (deterministic, pre-LLM)
   -> UltraBERT classifies: intent=query_schedule, entity=today,
      emotion=tired/neutral, safety=GREEN, complexity=LOW
   -> Writes to SS: control, affective_now (Section 5)

3. FSM determines PromptMode
   -> STANDARD mode (Section 4, determine_mode())
   -> Invokes Front handler

4. DynamicPromptBuilder assembles context (Section 6.1)
   -> Identity + Response Rules
   -> Session Trajectory (first turn, minimal)
   -> User input: "What's today look like?"
   -> SS sections per STANDARD read config (Section 6.1, SS Read Matrix)
   -> Tool set: STANDARD allowlist (Section 6.1, Tool Allowlist Table)

5. Front ReAct loop (Section 7, react_loop())
   Iteration 0:
     tool_choice="required" (ITEM #13)
     -> acknowledge("Good morning, Alex. Let me pull up your day.")
     -> Tool result: {delivered: true} (Section 10.4)

   Iteration 1:
     tool_choice="auto"
     -> recall_memory(query="Alex schedule preferences, family events today")
     -> Tool result: {memories: [{episodic: swim bag incident},
        {procedural: grocery routine}, {semantic: demo importance}]}
     -> update_beliefs([{subject: "today", predicate: "has", object: "Orion demo 2pm"}])
     -> update_scoreboard(topic="daily_briefing")

   Iteration 2:
     -> dispatch_task(
          intents=[{action: "get_daily_briefing", params: {member: "Alex"},
                    domain: "productivity"}],
          reference_context={"today": "Wednesday"})
     -> Tool result: {queued: true, task_id: "task-a1b2"}

   Iteration 3:
     -> Text response (no tool calls) -> L1 termination (Section 7.5)
     -> on_text_response fires: presents calendar + proactive swim bag warning
     -> k1.response.final.v1 emitted

6. FSM: ACKING -> DISPATCHING (task.dispatch.v1 on bus)

7. Back handler receives task.dispatch.v1
   -> build_back_prompt (Section 6.2)
   -> Back ReAct loop (Section 7, actor="back")
   Iteration 0:
     -> invoke_capability("tool.execute.calendar_summary",
          params={member: "Alex", date: "today"})
     -> Tool result: {success: true, data: {events: [...]}}
   Iteration 1:
     -> submit_result(status="COMPLETED",
          result={briefing: "9AM standup, 2PM Orion demo, 4PM swim..."})
     -> L2 termination (Section 7.5)

8. Bus: k1.orchestration.task.complete.v1
   -> FSM: DISPATCHING -> COMPANIONING -> DELIVERING (Section 4)
   -> Front invoked in PRESENT mode
   -> Presents briefing + proactive swim bag warning

9. Response delivered to Alex's device
   -> RhythmController applies timing (Section 12.5.3)
   -> k1.response.final.v1
   -> FSM: DELIVERING -> LISTENING
```

**Mechanisms exercised:** Phase 1 classification, FSM state transitions (Section 4), `determine_mode()` (Section 4), `DynamicPromptBuilder` (Section 6.1), Front ReAct loop with `tool_choice="required"` (Section 7, ITEM #13), `acknowledge()` (Section 6.1), `recall_memory()` (Section 7.9), `dispatch_task()` (Section 8.3), Back `invoke_capability()` (Section 6.2), `submit_result()` (Section 6.2), DELIVERING presentation (Section 4), `recall_memory` proactive risk mitigation (episodic: swim bag incident).

---

## 13.2 Scenario B: HITL Approval Flow (Turns 5-6 -- Grocery Order)

**User input:** Alex -- `"Add avocados and those crackers Jordan likes. That's it, place the order."`

**What this demonstrates:** Complete HITL approval cycle. Back suspends because the order has a financial side-effect. Front relays the approval question. User confirms. Back resumes and completes.

### Event Trace

```
1. User message -> k1.session.user.input.v1
   Phase 1: intent=finalize_order, safety=GREEN, complexity=LOW

2. Front ReAct (STANDARD mode):
   Iteration 0: acknowledge("Adding avocados and crackers, placing the order now.")
   Iteration 1: update_beliefs([grocery_order includes avocados, Jordan's crackers])
   Iteration 2: dispatch_task(
     intents=[{action: "finalize_grocery_order",
               params: {add_items: ["avocados", "Jordan's preferred crackers"],
                        confirm: true},
               domain: "shopping"}],
     reference_context={"Jordan's crackers": "Jordan's preferred cracker brand"})
   Iteration 3: text response -> L1 termination

3. Back ReAct:
   Iteration 0: recall_memory("Jordan cracker preference")
     -> resolves to "Mary's Gone Crackers, Everything flavor"
   Iteration 1: invoke_capability("tool.execute.grocery_order",
     params={add: ["avocados", "Mary's Gone Crackers Everything"], submit: true})
     -> Capability returns: needs_approval (charges $87.42)

   Iteration 2: submit_result(
     status="SUSPENDED",                        # Section 8.8
     result_type="needs_human",
     hil_type="approval",                       # Section 9.2, shape 1
     question="Order ready: $87.42 on Visa ending 4242. Confirm?",
     options=["Confirm order", "Cancel"],
     safety_band="GREEN")

4. Bus: k1.orchestration.task.suspended.v1    (Section 8.8)
   -> FSM: COMPANIONING -> HITL_RELAY (Section 4)
   -> task_state entry updated: status=SUSPENDED (Section 5)

5. Front invoked in HITL_RELAY mode (Section 9.4)
   -> DynamicPromptBuilder: HITL_RELAY config (Section 6.1)
   -> Presents: "Order's ready -- $87.42 on the Visa.
      Mary's Gone Crackers, Everything flavor -- that's Jordan's go-to, right?
      Confirm and I'll place it."
   -> k1.hil.request.v1 emitted (Section 9.1)

6. User responds: "Yep, confirmed."
   -> k1.session.user.input.v1
   -> Phase 1: intent=confirm_action
   -> FSM routes to HITL response handler

7. Bus: k1.orchestration.task.resume.v1       (Section 8.9)
   payload: {task_id: "task-xyz", decision: "approved",
             user_input: "Yep, confirmed."}

8. Back receives resume, continues:
   Iteration 3: invoke_capability("tool.execute.grocery_order",
     params={confirmed: true})
   Iteration 4: submit_result(status="COMPLETED",
     result={order_id: "NS-4421", total: "$87.42",
             delivery: "4-6pm"})

9. Bus: k1.orchestration.task.complete.v1
   -> FSM: HITL_RELAY -> COMPANIONING -> DELIVERING
   -> Front PRESENT mode: "Placed! Delivery between 4-6pm.
      Heads up -- that's the same window as Riley's swim practice.
      Want me to send a reminder to check the porch when you get back?"
```

**Mechanisms exercised:** HITL approval shape (Section 9.2), `task.suspended.v1` schema (Section 8.8), HITL_RELAY FSM state and Front mode (Sections 4, 9.4), `hil.request.v1` / `task.resume.v1` bus events (Section 9.1), `recall_memory` for cross-member preference (Jordan's crackers), `reference_context` resolution (Section 8.2), proactive conflict detection (delivery vs. swim practice).

---

## 13.3 Scenario C: Proactive IoT Alert + DND (Turns 11-12 -- Washer Done)

**User input:** None -- system-initiated.

**What this demonstrates:** Monitor-triggered proactive notification. No user input. The WEAVE protocol (Section 8.10) delivers the alert. Cross-member DND enforcement (Jordan is asleep).

### Event Trace

```
1. IoT sensor: washer cycle complete
   -> k1.monitor.alert.v1 (RELAXED delivery, Section 3)
   -> payload: {monitor: "LAUNDRY", event: "cycle_complete",
                detail: "Jordan's scrubs"}

2. FSM receives monitor alert
   -> Current state: LISTENING (no active conversation)
   -> WEAVE trigger (Section 8.10): async result with no active user turn
   -> FSM transitions: LISTENING -> COMPANIONING (Section 4)

3. DND check (pre-routing):
   -> Jordan's device: DND active (sleeping after night shift)
   -> Alert routed to Alex's device ONLY
   -> Privacy rule: notification suppressed for Jordan

4. Front invoked in WEAVE mode (Section 6.1, PromptMode.WEAVE):
   -> DynamicPromptBuilder: WEAVE SS read config
   -> recall_memory injected: Jordan's shift at 3pm, needs scrubs
   -> Temporal computation: scrubs must be dry by 2:30pm

5. Front ReAct (WEAVE mode):
   Iteration 0: acknowledge("Washer's done.")
   Iteration 1: text response presenting notification with HITL selection:
     "Jordan's scrubs are in there -- she'll need them for her 3pm shift.
      Want me to remind you to move them to the dryer, or should I hold
      this for Jordan when she wakes up?"
   -> L1 termination

6. User (Alex): "I'll do it in 10 minutes. Remind me."
   -> Phase 1: intent=schedule_reminder
   -> Front dispatches: schedule_reminder(task="dryer transfer", delay=10min)
   -> Back schedules timer
   -> k1.response.ack.v1: "Got it, 10-minute reminder set."
```

**Mechanisms exercised:** WEAVE protocol for proactive alerts (Section 8.10), monitor-triggered bus event (Section 3), DND enforcement across members, temporal reasoning (dryer time vs. shift departure), HITL selection (Section 9.2, shape 2 -- user picks between options), PromptMode.WEAVE (Section 4/6.1).

---

## 13.4 Scenario D: Double WEAVE (Turn 15 -- Marcus Reply + Nana Liz Meds)

**User input:** None -- two async results arrive simultaneously.

**What this demonstrates:** `WeaveBatcher` (Section 8.11) collecting multiple async results and delivering them in one natural Front invocation. Cross-generational care. Professional context parsing.

### Event Trace

```
1. Two async events arrive within the WeaveBatcher window (500ms):

   Event A: k1.monitor.alert.v1
     -> Marcus replied to Alex's email (message monitor)
     -> payload: {monitor: "EMAIL", from: "Marcus",
                  content: "Q4 deck on shared drive, December revised upward"}

   Event B: k1.monitor.alert.v1
     -> Wednesday med check: Nana Liz hasn't confirmed (health monitor)
     -> payload: {monitor: "MEDICATION", member: "Nana Liz",
                  medication: "Amlodipine 5mg", status: "unconfirmed",
                  hours_since_reminder: 3}

2. WeaveBatcher (Section 8.11):
   -> Both events arrive within 500ms batch window
   -> batch_id generated, both events grouped
   -> Single WEAVE trigger emitted

3. FSM: LISTENING -> COMPANIONING (WEAVE trigger)
   -> Context includes both batched results

4. Front invoked in WEAVE mode:
   -> DynamicPromptBuilder assembles both results into context
   -> recall_memory: "Nana Liz forgot meds twice before" (episodic)
   -> recall_memory: "Amlodipine 5mg, doctor changed Jan 15" (semantic)

5. Front ReAct (WEAVE mode):
   Iteration 0: acknowledge("Two things, Alex:")
   Iteration 1: update_beliefs([{Marcus replied, Q4 deck available},
                                {Nana Liz meds unconfirmed 3 hours}])
   Iteration 2: text response presenting both items naturally:
     "First -- Marcus got back to you. Q4 deck is on the shared drive,
      folder 'Orion-Assets.' December numbers revised upward -- update slide 7.
      Second -- Nana Liz's 9am med reminder went off three hours ago but
      she hasn't confirmed. This has happened twice before and she forgot
      both times. Want me to give her a call or send Jordan a message?"
   -> L1 termination

6. User responds with two intents:
   "Call Nana Liz. And set a reminder for me to check the Orion deck at 12:30."
   -> Multi-intent dispatch (Section 8.4, bundled pattern):
      Intent 1: wellness_call (Nana Liz, medication_check)
      Intent 2: schedule_reminder (Orion deck review, 12:30)
   -> Two Back tasks dispatched in parallel
```

**Mechanisms exercised:** `WeaveBatcher` 500ms window (Section 8.11), multiple async results composed into single Front invocation, `recall_memory` episodic + semantic for elder care, multi-intent bundled dispatch (Section 8.4), HITL selection (call vs. message), cross-generational care coordination, professional context extraction (actionable item from Marcus's reply).

---

## 13.5 Scenario E: Crisis Management (Turns 21-23 -- Demo Panic)

**User input:** Alex, 1:50 PM -- `"I'm panicking. The demo starts in 10 minutes and I just realized the API endpoint is returning 500 errors on the staging server. I can't demo a broken product."`

**What this demonstrates:** Affect-driven mode adaptation. `refine_affect()` with crisis-level parameters triggers affect band shift. Front response adapts to calm, structured, decisive tone. HITL selection with time-pressured options. IoT suppression during crisis.

### Event Trace

```
1. User message -> k1.session.user.input.v1
   Phase 1: intent=crisis_assist, emotion=panic,
            safety=GREEN, complexity=MEDIUM

2. FSM: LISTENING -> ACKING
   -> determine_mode(): affect_band analysis
   -> Phase 1 detected high arousal (0.9) + negative valence (-0.8)
   -> Affect band: CRISIS (Section 4, affect band table)
   -> PromptMode: STANDARD but with CRISIS modifiers

3. DynamicPromptBuilder (Section 6.1):
   -> CRISIS affect band modifiers applied:
      - max_iterations increased (Section 6.1, crisis iteration table)
      - Tone instruction: calm, structured, decisive
      - Anti-pattern: suppress small talk, suppress empathy-first delay
   -> IoT suppression: emit k1.monitor.suppress.v1 for Alex, 30 minutes
      (non-URGENT monitors paused)

4. Front ReAct (STANDARD + CRISIS):
   Iteration 0: tool_choice="required"
     -> refine_affect(emotion="panic", valence=-0.8, arousal=0.9,
          confidence=0.95,
          reason="High-stakes work crisis, 10 minutes before demo")
     -> acknowledge("I hear you. Let's triage this fast.")
     -> Tool results: {affect updated}, {delivered: true}

   Iteration 1:
     -> recall_memory("Alex demo preparation, staging vs production endpoints")
     -> update_beliefs([{staging API broken}, {demo in 10 minutes}])
     -> update_scoreboard(topic="crisis_triage")

   Iteration 2:
     -> Text response with structured options (HITL selection, Section 9.2):
     "OK, deep breath. Let's think through this:
      1. Can you demo against production instead of staging?
      2. Can you pre-record the API portion?
      3. Can you restructure to demo the API portion last?
      Which route feels right?"
     -> L1 termination

5. User: "Option 1 -- swap to prod. But I need the prod URL."
   -> Phase 1: intent=execute_option, complexity=LOW
   -> Front: recall_memory("orion-client config, prod URL")
     -> Finds: api.orion-prod.example.com/v2
   -> Presents URL, offers to update slides or just remind

6. User: "Just remind me when I get to slide 12. I can't think straight."
   -> dispatch_task: schedule_contextual_reminder(trigger="slide_12",
        message="Use prod URL: api.orion-prod.example.com/v2")
   -> update_beliefs([{demo using production endpoint}])
   -> "You'll get a quiet nudge when you hit slide 12.
       You've got this, Alex. Go show them what Orion can do."
```

**Mechanisms exercised:** `refine_affect()` with high confidence (Section 6.1), affect band escalation to CRISIS (Section 4), CRISIS modifiers on `DynamicPromptBuilder` (Section 6.1), IoT monitor suppression, `recall_memory` for procedural knowledge (repo names, file locations), HITL selection (Section 9.2, shape 2 -- three options), contextual reminder (trigger-based, not time-based), emotional support integrated into structured triage.

---

## 13.6 Scenario F: Triple WEAVE + Device Identity Switch (Turns 18, 24)

**What this demonstrates:** Two things: (1) device-based identity determining which persona and preferences load, and (2) three async results arriving simultaneously during a user message, composed into one natural response.

### Event Trace: Device Identity Switch (Turn 18)

```
1. Jordan messages from her phone, 12:35 PM: "I'm up. What'd I miss?"
   -> k1.session.user.input.v1
   -> Device registration: Jordan's Android phone
   -> Session switches to Jordan's persona (Section 5, persona SS section)
   -> Phase 1: intent=catch_up_briefing, emotion=groggy/neutral

2. Front ReAct (STANDARD mode, Jordan's persona):
   -> DynamicPromptBuilder loads Jordan's persona config
   -> recall_memory: Jordan's shift details, family events since 7am
   -> dispatch_task: get_personal_briefing(member="Jordan", since="7am")

3. Back compiles everything that happened while Jordan slept:
   -> Scrubs in dryer (Alex moved them), FedEx package on porch,
      Riley off to school with swim bag, Nana Liz meds checked,
      groceries ordered, Alex's demo at 2pm

4. Front PRESENT mode:
   -> Personalized for JORDAN: she sees HER briefing
   -> Cross-member visibility: knows Alex moved scrubs, but does NOT
      see Alex's private work stress
   -> Privacy boundary: Jordan's private note about Alex's eating
      is NOT visible to Alex, and Alex's stress-eating context
      is NOT disclosed to Jordan
```

### Event Trace: Triple WEAVE (Turn 24)

```
1. Alex messages at 3:15 PM: "We got it. They're signing."
   -> Phase 1: emotion=elation (valence=0.9, arousal=0.8)

2. Simultaneously, 3 async results in WeaveBatcher window:
   Event A: Patty approved Jordan's Thursday shift swap
   Event B: Grocery delivery ETA updated to 4:45 PM
   Event C: School reminder: Riley needs field trip snacks Tuesday

3. WeaveBatcher (Section 8.11): batches all 3

4. Front invoked with user message + 3 WEAVE results:
   -> refine_affect: elation detected
   -> Response tone: celebratory (mirrors user emotion)
   -> Presents user's news FIRST ("CONGRATULATIONS!")
   -> Then weaves in the 3 async results naturally:
     "A few things that came in while you were presenting:
      1. Jordan's shift swap: approved.
      2. Groceries: ETA 4:45 PM.
      3. School alert: Riley needs field trip snacks Tuesday."
   -> Proactive: "Riley's swim ends at 5. Want me to plan your route?"

5. Cross-member coordination:
   -> Jordan's shift swap result affects Riley's school event attendance
   -> update_beliefs: Thursday evening now free for school event
```

**Mechanisms exercised:** Device-based identity and persona loading (Section 5), `DynamicPromptBuilder` persona-aware context assembly (Section 6.1), privacy boundaries (cross-member visibility rules), `WeaveBatcher` triple-batch (Section 8.11), `refine_affect` with positive emotion, celebratory tone adaptation, proactive logistics (route planning), cross-member state coordination (shift swap -> school event availability).

---

## 13.7 Scenario G: No-Interrupt Rule + Project Routine (Turns 26-28)

**User input:** Alex, 6:00 PM -- `"We're about to sit down for dinner. Jordan's working. It's just me and Riley tonight."`

**What this demonstrates:** Temporal rule enforcement (no interruptions 6-7 PM), IoT ambient control, project management with mission tracking, bedtime routine awareness, cross-member updates at appropriate priority.

### Event Trace

```
1. User message -> Phase 1: intent=status_update, emotion=calm
   -> Front: update_beliefs([dinner attendees: Alex + Riley])
   -> Front recognizes 6-7pm NO INTERRUPT rule (from family settings in SS)
   -> Activates monitor suppression: ALL non-URGENT monitors paused until 7pm

2. IoT orchestration (automatic, no dispatch needed):
   -> THERMOSTAT: dining area to 71F
   -> Smart lights: warm/dim dinner mode
   -> These fire from scheduled routines, not from this user message

3. Front response:
   -> "Enjoy dinner, you two. Going quiet until 7pm.
       If anything urgent comes up, I'll break through --
       otherwise, it's your time."
   -> FSM enters suppressed-notification mode

4. [60 minutes pass -- FamilyOS is SILENT]
   -> Any monitor events (non-URGENT) are queued, not delivered
   -> URGENT events (smoke detector, security) would break through

5. Turn 27: Alex at 7:05 PM: "Time for Riley's first diorama mission."
   -> Front: recall_memory("diorama mission plan from Turn 3")
   -> Retrieves Mission 1 plan from beliefs/task_artifacts
   -> Presents: "Mission 1: Pick the dinosaur scene and sketch it!"
   -> HITL selection: "Want me to start a 30-minute mission timer?"

6. Turn 28: Alex at 7:40 PM: "We're done! She picked a Cretaceous forest."
   -> Front: update_beliefs([diorama scene chosen, mission 1 complete])
   -> dispatch_task: update_project_progress(mission=1, status="complete")
   -> dispatch_task: send_family_message(
        to="Jordan",
        message="Mission 1 complete! Riley designed an epic Cretaceous forest.",
        priority="LOW")  # LOW -- won't interrupt Jordan's shift
   -> recall_memory("Riley bedtime routine")
     -> procedural: 8pm bath, 8:20 story, 8:40 lights out
   -> Proactive: "It's 7:40 -- bath time in 20 minutes.
       Want me to start the bath water?"

7. Cross-member update delivery:
   -> Jordan's message queued at LOW priority
   -> Delivered during her next break (device-aware timing)
   -> Does NOT interrupt her patient care
```

**Mechanisms exercised:** Temporal suppression rules (family settings in SS, Section 5), monitor suppression/queueing, IoT ambient control, `recall_memory` procedural (bedtime routine, diorama plan), project tracking via `update_beliefs` + `dispatch_task`, cross-member messaging with priority-aware delivery (Section 3, Priority), HITL selection (timer), proactive routine awareness.

---

## 13.8 Architecture Feature Coverage Map

Every major architectural mechanism is exercised by at least one scenario:

| Mechanism | Defined In | Exercised By |
| --- | --- | --- |
| Phase 1 (UltraBERT) classification | Section 4 | A, B, C, E, F, G |
| FSM state transitions | Section 4 | All scenarios |
| `determine_mode()` + PromptMode | Section 4 | A, C, D, E |
| `DynamicPromptBuilder` context assembly | Section 6.1 | All scenarios |
| Front ReAct loop with `tool_choice="required"` | Section 7 (ITEM #13) | A, E |
| `acknowledge()` first tool call | Section 6.1 | All user-input scenarios |
| `recall_memory()` (episodic, semantic, procedural) | Section 7.9 | A, B, D, E, F, G |
| `refine_affect()` + affect bands | Section 6.1 | E (crisis), F (elation) |
| `update_beliefs()` / `update_scoreboard()` | Section 6.1 | A, B, E, G |
| `dispatch_task()` single intent | Section 8.3 | A, C |
| `dispatch_task()` bundled intents | Section 8.4 | D, G |
| Back `invoke_capability()` | Section 6.2 | A, B |
| Back `submit_result()` | Section 6.2 | A, B |
| HITL approval (shape 1) | Section 9.2 | B |
| HITL selection (shape 2) | Section 9.2 | C, E, G |
| HITL clarification (shape 3) | Section 9.2 | (Turn 4 in storyline) |
| `task.suspended.v1` / `task.resume.v1` | Section 8.8-8.9 | B |
| WEAVE protocol (single) | Section 8.10 | C |
| WEAVE protocol (batched) | Section 8.11 | D (double), F (triple) |
| Cancellation | Section 8.7 | (Turn 14 in storyline, reminder reschedule) |
| Cross-member privacy boundaries | Section 5 | B (Jordan's crackers), F (identity switch) |
| Device-based identity | Section 5 | F |
| IoT monitor triggers | Section 3 | C (laundry), G (thermostat) |
| DND enforcement | Section 5 | C (Jordan sleeping) |
| Monitor suppression (temporal rules) | Section 5 | E (crisis), G (dinner) |
| `reference_context` resolution | Section 8.2 | A, B |
| Experience Layer (affect band) | Section 12 | E (crisis modifiers) |
| RhythmController (delivery pacing) | Section 12.5.3 | A (post-loop) |
| `IConciergeModelPort` adapter | Section 10 | All scenarios (implicit) |
| Output validation (`LLMOutputValidator`) | Section 10.5 | All scenarios (implicit) |
| Tier routing (`route_task()`) | Section 11.2 | A (LOW), B (LOW) |

**Gaps:** No scenario exercises HIGH-tier orchestration (Section 11.4), chained tasks (Section 8.5), or saga recovery -- these are deferred interfaces without POC implementation.

---

# 14. Skeleton Mapping & Validation Criteria

This section maps the K1 architecture skeleton to POC implementation, lists what the POC validates, records all resolved design decisions, and catalogs remaining open questions.

---

## 14.1 Skeleton-to-POC Mapping

Each K1 architecture skeleton component maps to a concrete POC implementation. The mapping ensures the POC exercises real K1 infrastructure, not stand-ins.

| Skeleton Component | POC Implementation | V2 Design Section |
| --- | --- | --- |
| Concierge FSM | `ConciergeController` -- event-driven FSM with 12 states, `determine_mode()`, FrontLock, WeaveBatcher | Section 4 |
| Concierge LLM (cognitive tools) | Front LLM actor -- Signal(1) + Cognitive(5) + Read(2) + Control(2) = 10 tools | Section 6.1 |
| Orchestrator (deterministic router) | `route_task()` -- LOW direct to Back, MEDIUM via OrchestratorStub, HIGH deferred interface | Section 11 |
| Capability Fabric (resolution + execution) | Back LLM actor -- `invoke_capability()` via Fabric 9-step pipeline | Section 6.2 |
| Fabric Capability Registry | Domain-agnostic capability catalog, any domain routed through single `invoke_capability` | Section 6.2 |
| K1 Event Bus (k1.* topics) | `LocalBus` via `BusFactory.create_local_ordered()`, 17 topics in taxonomy | Section 3 |
| K1 Delta Bus (k1.*.delta.v1) | `SessionBusAdapter` + `DeltaAggregator` (500ms window) | Section 3 |
| Mailbox Router (actor-to-actor) | `LocalMailboxRouter` for direct point-to-point actor messages | Section 3 |
| TimingChain (causal + sequence ordering) | Default `TimingConfig` -- STRICT for orchestration/response/session/hil topics, RELAXED for affect/proactive | Section 3 |
| SessionState (HOT 52KB + WARM 48KB) | `SessionLLMBridge` extended with `task_state`, `task_artifacts`, `TypedHistoryEntry` | Section 5 |
| OUTPUT_CHANNEL | Print/display handler subscribed to `k1.response.*` topics | Section 3 |
| Phase 1 (UltraBERT) | Deterministic classification: intent, entity, emotion, safety band, complexity tier. Writes to SS BEFORE Front invocation. | Section 4 |
| Phase 2 (LLM with tools) | Front LLM ReAct + Back LLM ReAct via shared `react_loop()` | Section 7 |
| Tool Result Buffer | Back scratchpad results (ephemeral) + `task.complete` bus payload (durable) | Section 7 |
| ToolDispatcher Pipeline | 7-step pipeline per actor: allowlist, budget, schema, ACK-first, safety, dispatch, record | Section 7 |
| DynamicPromptBuilder | Mode-driven context assembly: 10 PromptModes, per-mode SS reads, per-mode tool allowlists, composable prompt sections | Section 6.1 |
| ExperienceLayer | 6 stub components with defined cadences, fire via `tick()` after every turn, Front-only | Section 12 |
| HITL Protocol | 3 shapes (clarification, approval, selection), safety band escalation, configurable timeouts, crash-recovery persistence | Section 9 |
| Task Model | `TaskDispatch` with `intents[]` array, `depends_on` for chaining, complexity tier for budget | Section 8 |
| Cancel/Suspend/Weave | `cancellation_requested` flag, `task.suspended`/`task.resume` bus events, `WeaveBatcher` with 500ms batch window | Sections 8.7-8.11 |
| LLM Adapter | `IConciergeModelPort` protocol with `generate()`/`generate_stream()`, Gemini adapter, Test adapter | Section 10 |
| Output Validator | `LLMOutputValidator` with tool allowlist checking, param validation, ordering checks, retry wrapper | Section 10 |

---

## 14.2 What This POC Validates

The POC validates 12 architectural hypotheses. Each must pass for the architecture to be considered proven.

| # | Validation Goal | How Verified | V2 Section |
| --- | --- | --- | --- |
| 1 | **Bus-driven actor coordination works for any conversational AI task** -- two LLMs, no shared loop, events as triggers, domain-agnostic | All 30 demo turns execute through Front/Back actors coordinated entirely via K1 bus envelopes. No shared event loop. | Sections 3, 4, 13 |
| 2 | **Causal ordering replaces anti-spin** -- TimingChain `parent_id` chains enforce correct execution order | Every dispatch -> task.complete -> present chain has parent_id linking. No polling, no spin-wait, no `_force_text_only` hacks. | Section 3 |
| 3 | **Session State as shared memory eliminates amnesia** -- both actors read persistent state, not ephemeral messages | Beliefs about diorama (Turn 3) persist through Turns 27-28. Jordan's wake preferences (Turn 2) persist through Turn 30. Laundry thread (Turn 11) persists through Turn 14. | Section 5 |
| 4 | **Tool distribution follows real K1 taxonomy** -- Front: Signal + Cognitive + Read + Control. Back: Action + Read + Control. No POC-specific tools. | 10 Front tools + 6 Back tools exercised across demo. `recall_memory` shared (actor="both"). No crossover. | Sections 6.1, 6.2 |
| 5 | **Both actors use shared `react_loop()`** -- same function, different tools and termination conditions | Front terminates on text-without-tools (L1). Back terminates on `submit_result()` (L2). Same `react_loop()` implementation. | Section 7 |
| 6 | **Concurrent conversation is possible** -- Front handles new input while Back works | Turn 14: Alex talks while Back processes. Turn 24: Alex converses while 3 async results queue. Front never blocked by Back. | Section 4 |
| 7 | **WEAVE protocol works** -- async task results naturally merge into ongoing conversation | Turn 15: dual WEAVE (Marcus reply + Nana Liz). Turn 24: triple WEAVE (shift swap + grocery + school). WeaveBatcher collects in batch windows. | Sections 8.10, 8.11, 13.3-13.4 |
| 8 | **Task lifecycle management works** -- cancel, suspend, resume, chain, bundle are clean bus events | HITL suspension in Turns 5-6, 9-10, 20. Multi-intent bundles in Turns 2, 4, 14, 16, 19, 25. Task rescheduling in Turn 14. | Sections 8.3-8.9 |
| 9 | **FrontLock prevents race conditions** -- Front concurrency is serialized correctly | When WEAVE results arrive during Front LLM generation, they queue and drain after current response completes. | Section 4 |
| 10 | **`invoke_capability()` is the universal executor** -- any domain routes through Fabric, no per-domain tool explosion | 7+ domains exercised: productivity, family, health, shopping, IoT, communication, elder care. Same `invoke_capability` for all. | Section 6.2 |
| 11 | **Session coherence under concurrency** -- Single Writer invariant + DeltaAggregator prevent state corruption | When Jordan logs in (Turn 18), her session reads are consistent with writes from Alex's session (Turns 1-16). No corruption. | Section 5 |
| 12 | **K1 bus infrastructure is production-ready for this pattern** -- LocalBus, TimingChain, Adapters, Middleware all work | 30 turns, 7 acts, 3 active users, 50+ bus events, IoT monitors firing asynchronously, WEAVE batching, multi-intent dispatch -- no deadlock, message loss, or ordering violations. | Section 3 |

---

## 14.3 Token Savings Validation (ITEM #6)

The mode-driven prompt architecture (Section 6.1) replaces the monolithic ~5,700-token system prompt with per-mode composable assembly. This table is the VALIDATION METRIC -- evidence that the mode architecture achieves its token efficiency goal.

| PromptMode | Monolithic (tokens) | Mode-Driven (tokens) | Savings | Savings % |
| --- | --- | --- | --- | --- |
| STANDARD | ~5,700 | ~5,500 | ~200 | 4% |
| CLARIFY_ASK | ~5,700 | ~2,200 | ~3,500 | 61% |
| CLARIFY_RESOLVE | ~5,700 | ~3,800 | ~1,900 | 33% |
| HITL_RELAY | ~5,700 | ~1,200 | ~4,500 | 79% |
| HITL_RESOLVE | ~5,700 | ~2,000 | ~3,700 | 65% |
| PRESENT | ~5,700 | ~3,000 | ~2,700 | 47% |
| WEAVE | ~5,700 | ~3,200 | ~2,500 | 44% |
| CANCEL | ~5,700 | ~2,000 | ~3,700 | 65% |
| INTERRUPT | ~5,700 | ~5,500 | ~200 | 4% |
| ERROR | ~5,700 | ~1,800 | ~3,900 | 68% |

**Weighted average savings** (based on expected mode frequency): **~45% reduction** in prompt tokens per invocation.

**Impact:** Fewer input tokens = faster inference latency + lower cost per call. HITL_RELAY achieves 79% savings because it uses 0 tools and reads only 3 SS sections. STANDARD and INTERRUPT retain near-full context (4% savings) because they need complete tool sets and broad SS reads.

**Validation method:** Tokenize assembled prompts for each mode using the model's tokenizer. Compare against the monolithic prompt token count. Weighted average uses expected mode distribution: STANDARD ~40%, PRESENT ~20%, WEAVE ~10%, HITL_*~10%, CLARIFY_* ~10%, other ~10%.

---

## 14.4 Resolved Design Decisions

These were originally open questions. They are now resolved and stated authoritatively here. No other section redefines these.

| # | Question | Decision | Rationale | V2 Section |
| --- | --- | --- | --- | --- |
| 1 | Back LLM or deterministic executor? | **LLM-based ReAct agent for POC.** | Both Front and Back are LLM-powered ReAct agents sharing the same `react_loop()` function (Section 7). Back uses think-act-observe with its own tool set (Action + Read + Control). The `submit_result` tool is the only exit, giving the FSM an explicit termination signal. The interface is designed so swapping to a deterministic executor later requires zero changes to the bus, topics, or Front. | Section 7 |
| 2 | How many Back actors? | **One for POC. Pool later.** | Single Back actor. Tasks queued in its mailbox. Simpler. Avoids concurrent SS writes. When parallelism is needed, add a `BackPool` that spawns per-task handlers (each with its own ReAct message history). Interface designed so this swap requires zero bus/topic/Front changes. | Section 6.2 |
| 3 | Error recovery across actors? | **1 retry per capability invocation (2 total attempts: original + 1 retry). Then `task.failed`.** | Back owns retry logic internally. If `invoke_capability` fails, Back retries ONCE with different params if sensible (same params = pointless). If still failing, Back emits `task.failed` with 7-field diagnostic payload. Front receives this and generates a user-friendly explanation. No automatic re-dispatch; user must explicitly ask to retry. **(ITEM #16 resolved: "2x" in old doc meant 2 total attempts, not 2 retries. Section 6.2 Back system prompt is authoritative.)** | Section 6.2, 8.6 |
| 4 | Token budget allocation? | **Carried in `task.dispatch` envelope via `budget_hint`.** | Front sets `budget_hint` based on complexity tier from Phase 1. LOW: 2 tool calls max. MEDIUM: 5. HIGH: 8. Back enforces via `max_iterations` parameter on `react_loop()`. | Sections 8.2, 11.3 |
| 5 | Testing strategy? | **`BusFactory.create_for_testing()` + causal chain assertions.** | All tests use capture mode. Assertions verify: (a) correct causal chains (`parent_id` linkage), (b) correct topic routing (Front never emits `tool.*`, Back never emits `response.*`), (c) actor isolation (no cross-tool-set calls), (d) WEAVE ordering (`pending_results` drained after Front response, not during). | Section 3 |
| 6 | HITL suspend timeout? | **60s for clarification, 120s for approval, 90s for selection. Auto-cancel on expiry.** | Different shapes have different urgency profiles. Approval (financial side-effects) gets more time. Front proactively reminds at 50% of timeout ("I still need to know..."). | Section 9.3 |
| 7 | Capability registration for POC? | **Pre-register across multiple domains.** | Pre-register demo capabilities spanning productivity, health, shopping, IoT, communication, family, elder care. Proves domain-agnostic routing works. Not a mock registry -- real Fabric registration with stub implementations. | Section 6.2 |
| 8 | PromptMode determination logic? | **`determine_mode()` is a deterministic function of FSM state + envelope topic + SS fields.** | No LLM involvement in mode selection. The FSM state (LISTENING, DELIVERING, CLARIFYING_WORKER, etc.) combined with the triggering envelope's topic and SS fields (clarification gaps, suspended tasks, affect band) uniquely determine the PromptMode. | Section 4 |
| 9 | Experience Layer scope? | **Front-only. Stubs with `pass`. Pluggable without integration changes.** | No component reads Back state or writes to Back's prompt. Components fire at defined cadences via `tick()`. Replacing a stub body requires zero changes to `tick()`, `DynamicPromptBuilder`, FSM, or ReAct loop. | Section 12 |
| 10 | WeaveBatcher window? | **500ms batch window.** | Balances responsiveness (user does not wait long for batched results) vs. completeness (concurrent async results arriving within 500ms are grouped into one Front invocation). Configurable for production tuning. | Section 8.11 |

---

## 14.5 Remaining Open Questions

These are NOT resolved. They require production experience or further design work beyond the POC scope.

| # | Question | Current Status | Impact if Unresolved |
| --- | --- | --- | --- |
| 1 | **Back actor scaling.** How does BackPool distribute tasks with per-task ReAct histories while maintaining SS coherence? | Interface designed for future swap (Resolved Decision #2). Pool implementation deferred. | Single Back actor is a throughput bottleneck under concurrent multi-user load. POC proves the interface; production needs the pool. |
| 2 | **HIGH-tier orchestrator.** What does the full planner -> committed plan -> step execution -> saga recovery loop look like? | Interface contracts defined (Section 11.4): `IPlannerPort`, `PlanRequest`, `CommittedPlan`, `PlanStep`. No implementation. | Complex multi-step tasks (vacation planning across multiple services) cannot execute. POC handles LOW and MEDIUM tiers only. |
| 3 | **Cross-session state.** How do beliefs/artifacts from one session influence another session (e.g., Alex's morning session informs Jordan's afternoon session)? | Device-based identity loads per-member persona (Section 5). Cross-member visibility is scoped by privacy rules. Shared family-level SS sections not yet designed. | Members cannot see each other's in-progress tasks or recent beliefs unless explicitly shared. POC demonstrates per-member privacy but not family-level aggregation. |
| 4 | **Memory layer integration.** How does `recall_memory` connect to the actual K1 memory hierarchy (episodic, semantic, procedural stores)? | `recall_memory` is a tool signature in Section 7.9. POC uses preloaded memories (10 entries). Production requires vector search over real memory stores. | Demo memories are hardcoded. Real memory retrieval latency, relevance ranking, and memory consolidation are untested. |
| 5 | **IoT monitor reliability.** What happens when IoT monitors lose connectivity, send stale data, or flood the bus? | POC uses stub monitors with scripted fire times. No error handling for monitor failures. | Stale IoT alerts could trigger incorrect proactive responses. Monitor health checks and debouncing are production concerns. |
| 6 | **Multi-device concurrent input.** What if Alex and Jordan both message at the exact same time from different devices? | FrontLock serializes within one session. Cross-session concurrency not addressed. | Potential SS corruption if two sessions write overlapping sections simultaneously. Needs per-section or per-member locking strategy. |

---

# 15. Implementation Phases

The POC is built in 19 milestones. Each milestone is self-contained and testable. Every milestone ends with an E2E wiring checklist that proves its exit criteria before the next milestone begins.

**Execution plan source:** `poc/k1_poc/concierge_poc_plan.md` (25,343 lines, 130 epics, 554 issues). This section summarizes the milestone structure and dependency graph. The plan document contains full epic-level breakdowns with file paths, code samples, and test specifications.

**Structural rule:** Every milestone references V2 design section numbers, not old doc section numbers.

---

## 15.1 Milestone Overview

| Milestone | Component | V2 Design Sections | Depends On | Key Exit Criteria |
| --- | --- | --- | --- | --- |
| **M01** | Bus Foundation | 3 | -- | Actors exchange ordered envelopes via TimingChain |
| **M02** | Session State Extensions | 5 | -- | 10 HOT sections (52KB), typed history, persona init |
| **M03** | LLM Universal Adapter | 10 | -- | `generate()`/`generate_stream()` work with Gemini + Test adapters |
| **M04** | Tool Schema Catalog & Dispatcher | 6.1, 6.2, 7 | M03 | 14 tools defined with JSON Schema, dispatchers validate |
| **M05** | Shared ReAct Loop | 7 | M03, M04 | Front/Back termination, cancellation check, budget fallback |
| **M06** | Front LLM Actor | 4, 6.1 | M01, M02, M05 | user.input -> ack -> dispatch -> present, all 5 event subscriptions |
| **M07** | Back LLM Actor | 6.2, 8 | M01, M02, M05 | dispatch -> invoke_capability -> submit_result -> complete |
| **M08** | FSM Controller & Event Router | 4 | M06, M07 | 12 states, FrontLock, Phase 1, DeltaAggregator, WeaveBatcher |
| **M09** | Dynamic Prompt Mode Architecture | 6.1 | M06, M08 | 10 modes, per-mode SS reads, per-mode tools, 45% token savings |
| **M10** | Task Model & Dependencies | 8 | M07, M08 | Bundle, chain, concurrent tasks, TaskDependencyQueue |
| **M11** | Delta Aggregator & Session Coherence | 5 | M02, M07, M08, M10 | Single Writer, 500ms batched writes, MutationGuard |
| **M12** | Cancel, Suspend, & Weave Protocols | 8.7-8.11 | M06, M07, M08, M11 | Cancel, suspend/resume, WeaveBatcher batch window |
| **M13** | HITL Protocol | 9 | M12, M09 | 3 HITL shapes, safety band escalation, timeout/crash recovery |
| **M14** | Affect, Clarification Depth, Domain Rules | 6.1, 12 | M09, M02, M08 | 5 affect bands, 3 clarification depths, 8 domain rule sets |
| **M15** | Experience Layer Stubs | 12 | M08 | 6 stub components, correct fire cadences, tick() orchestrator |
| **M16** | Orchestrator Stub & Tier Routing | 11 | M07, M08, M10 | LOW/MEDIUM/HIGH routing, degradation cascade |
| **M17** | Output Validation & Context Budget | 10 | M03, M04, M09 | LLMOutputValidator, retry wrapper, 80% context budget |
| **M18** | Full System Prompts & In-Context Examples | 6.1, 6.2 | M09, M14, M16, M17 | 20 prompt sections, 10 mode examples, coherence verified |
| **M19** | E2E Integration & "One Ordinary Day" Demo | 13, 14 | M01-M18 | 30 turns, 7 acts, 12 validation goals, real LLM calls |

**Total: 22 components, 130 epics, 554 issues.**

---

## 15.2 Dependency Graph & Critical Path

```
M01 + M02 + M03 (parallel, no deps)
              |
              v
            M04 (needs M03)
              |
              v
            M05 (needs M03 + M04)
              |
         +----+----+
         v         v
       M06       M07 (need M01 + M02 + M05)
         |         |
         +----+----+
              |
              v
            M08 (needs M06 + M07)
              |
    +---------+---------+
    v         v         v
  M09       M10       M15 (need M08)
    |         |
    v     +---+---+
  M14     v       v
    |   M11     M16
    |     |
    v     v
  M17   M12
    |     |
    v     v
  M18   M13
    |     |
    +-----+
       |
       v
     M19 (needs ALL)
```

**Critical path:** M03 -> M04 -> M05 -> M06/M07 -> M08 -> M10 -> M11 -> M12 -> M13 -> M19

**Parallelization opportunities:**

- M01, M02, M03 can run in parallel (no dependencies).
- M06 and M07 can run in parallel (both depend on M01+M02+M05 but not on each other).
- M09, M10, M15 can run in parallel after M08 completes.
- M14, M11, M16 can partially overlap with their respective predecessors.

---

## 15.3 Phase Details

### Phase A: Foundation (M01 + M02 + M03) -- No Dependencies

**M01 -- Bus Foundation** (Section 3)

- Wire `BusFactory.create_local_ordered()` with default `TimingConfig`.
- Define 17 topic constants matching Section 3 taxonomy.
- Create envelope builders for all event types.
- Register `front-llm` and `back-llm` actors with `LocalMailboxRouter`.
- Create `SessionBusAdapter` bridging SessionState's `IEventPort` to `IBus`.
- Verify all 17 topics resolve to correct `DeliveryMode` (STRICT/RELAXED).
- Exit: Two actors exchange envelopes with causal ordering enforced.

**M02 -- Session State Extensions** (Section 5)

- Add `task_state` section (active task IDs, status, dependencies, HITL pending state).
- Add `task_artifacts` section (durable outputs from any domain).
- Implement `TypedHistoryEntry` dataclass and `get_typed_entries()` API.
- Implement `SessionTrajectory` assembly from multiple SS sections.
- Implement `initialize_persona()` with demo family profiles.
- Update `HOT_BUDGET_BYTES` to 53,248 (52KB) for 10 HOT sections.
- Exit: SS has 10 HOT sections, typed history API works, persona loads.

**M03 -- LLM Universal Adapter** (Section 10)

- Implement `IConciergeModelPort` protocol with `generate()` and `generate_stream()`.
- Implement type hierarchy: `ConciergeModelRequest`, `ConciergeModelResponse`, `ToolCallResult`, `ModelMessage`, `StreamChunk`.
- Implement `GeminiConciergeAdapter` (sole provider class, only code that imports `google.genai`).
- Implement `TestConciergeAdapter` for deterministic testing keyed by `(actor, scenario)`.
- Model selection table: `gemini-2.0-flash` (default), `gemini-2.0-flash-lite` (fallback), `gemini-2.5-pro` (complex).
- Exit: Both adapters satisfy the port contract.

### Phase B: Tool Infrastructure (M04 + M05) -- Needs M03

**M04 -- Tool Schema Catalog & Dispatcher** (Sections 6.1, 6.2, 7)

- Define 10 Front `ToolSchema` objects with JSON Schema `parameters` and `returns`.
- Define 6 Back `ToolSchema` objects including `submit_result` with `complete`/`needs_human` modes.
- Implement `tool_result_to_message()` for ReAct observation injection.
- Implement `ToolDispatcher` with 7-step pipeline: allowlist, budget, schema, ACK-first, safety, dispatch, record.
- Front dispatcher rejects Back-only tools; Back dispatcher rejects Front-only tools.
- Exit: All 14 tools defined. Dispatchers validate and reject correctly.

**M05 -- Shared ReAct Loop** (Section 7)

- Implement `react_loop()` with actor-specific termination: Front on text-without-tools (L1), Back on `submit_result()` (L2).
- Handle Back "thinking aloud" (text without `submit_result` = continue, not terminate).
- Collect `dispatch_task()` calls for L3 post-loop emission.
- Check `cancellation_requested` between iterations.
- Enforce `max_iterations` budget with graceful fallback on exhaustion.
- Wire `tool_choice="required"` for iteration 0 (ITEM #13).
- Wire callbacks: `on_ack_emitted`, `on_text_response`, `on_artifact_created`.
- Exit: Both actors terminate correctly with proper callbacks.

### Phase C: Actor Handlers (M06 + M07) -- Needs M01, M02, M05

**M06 -- Front LLM Actor** (Sections 4, 6.1)

- Subscribe to 5 bus events: `user.input`, `task.complete`, `task.failed`, `task.suspended`, `hil.response`.
- Implement 4-step handler: `determine_mode()` -> `DynamicPromptBuilder.build()` -> `react_loop()` -> emit dispatches.
- `DynamicPromptBuilder` assembles per-mode context (stub: STANDARD mode only initially).
- Emit 7 event types: `response.ack`, `response.final`, `task.dispatch`, `task.cancel`, `task.resume`, `clarification.request`, `clarification.response`.
- All envelopes have correct topic, priority, `parent_id` per Section 3 taxonomy.
- Exit: Front handles all 5 input events and emits correct output events.

**M07 -- Back LLM Actor** (Sections 6.2, 8)

- Subscribe to 4 bus events: `task.dispatch`, `task.cancel`, `task.resume`, `clarification.response`.
- Back terminates ONLY via `submit_result()` (text-without-tools is "thinking aloud").
- Emit: `task.complete`, `task.suspended`, `task.failed`, `tool.started`, `tool.completed`, `artifact.created`, `booking.confirmed`.
- `invoke_capability()` routes through Fabric 9-step pipeline.
- Back NEVER writes SS directly, NEVER emits text to OUTPUT_CHANNEL, NEVER calls Front-only tools.
- 1 retry per capability invocation (2 total attempts, Resolved Decision #3).
- Exit: Back handles all 4 input events with correct output events.

### Phase D: FSM Controller (M08) -- Needs M06, M07

**M08 -- FSM Controller & Event Router** (Section 4)

- Adapt FSM from synchronous loop driver to event-driven router.
- Subscribe to all 17 POC bus topics.
- Implement 12 FSM states with correct transition table.
- Implement `determine_mode()` for PromptMode selection.
- Implement `FrontLock` for Front event serialization with priority ordering.
- Implement `FSMTurnState` for ephemeral per-turn data (pending_results, cancelled_tasks).
- Write `TypedHistoryEntry` at every event boundary.
- Integrate Phase 1 (UltraBERT) deterministic writes before Front invocation.
- Implement `DeltaAggregator` for Back -> FSM -> SS write pipeline (500ms window).
- Implement `WeaveBatcher` for async result batching (500ms window).
- Extend `ControlSection` for Concierge-specific fields: `active_task_ids`, `fsm_state`, `complexity_tier`.
- Exit: All 12 states transition correctly, FrontLock serializes, history writes at boundaries.

### Phase E: Advanced Architecture (M09-M16) -- Partially Parallelizable

These milestones can partially overlap based on the dependency graph.

**M09 -- Dynamic Prompt Mode Architecture** (Section 6.1)

- Implement `PromptMode` enum (10 modes).
- Implement `determine_mode()` deterministic function.
- Implement `TOOL_ALLOWLIST` per mode (0-10 tools per mode).
- Implement `SS_READ_CONFIGS` per mode (full/slim/skip per section).
- Implement `MODE_SECTIONS` composable prompt section lists.
- Implement `DynamicPromptBuilder.build()` 12-step assembly pipeline.
- Achieve ~45% weighted average token savings vs. monolithic prompt (Section 14.3).
- Exit: 10 modes produce correct prompt assemblies.

**M10 -- Task Model & Dependencies** (Section 8)

- Implement `TaskDispatch` with `intents[]` array and `depends_on` field.
- Implement `ComplexityTier` -> `budget_hint` mapping.
- Implement bundled intents (sequential within one Back ReAct loop).
- Implement chained tasks with `TaskDependencyQueue` and `$ref` resolution.
- Implement concurrent independent tasks via Back mailbox FIFO ordering.
- Exit: Bundle, chain, concurrent task patterns all work.

**M11 -- Delta Aggregator & Session Coherence** (Section 5)

- Back never writes SS directly -- all outputs flow as bus deltas.
- `DeltaAggregator` collects deltas in 500ms windows, deduplicates, orders by causal chain.
- FSM is sole writer for `task_state` and `task_artifacts`.
- `MutationGuard.preflight()` validates every write (section budget, tier budget, total budget).
- Section overflow triggers eviction to WARM (oldest artifacts first).
- Exit: Single Writer enforced, batched writes, overflow eviction.

**M12 -- Cancel, Suspend, & Weave Protocols** (Sections 8.7-8.11)

- `cancellation_requested` flag checked at tool boundaries.
- Suspension preserves ReAct history in `FSMTurnState` with max 2 suspensions per task.
- Configurable timeouts per HITL shape (clarification 60s, approval 120s, selection 90s).
- `WeaveBatcher` batches completed results in 500ms windows, invokes Front once per batch.
- Exit: Cancel, suspend/resume, WEAVE all work correctly.

**M13 -- HITL Protocol** (Section 9)

- Implement 3 HITL shapes: clarification, approval, selection.
- Back suspends via `submit_result(result_type="needs_human")`.
- Front translates `HILRequest` to natural language in HITL_RELAY mode (0 tools, pure text).
- Front resolves in HITL_RESOLVE mode (2 tools: acknowledge + update_beliefs).
- Safety band escalation: GREEN (auto-approve) / AMBER (confirm) / RED (block + explain).
- HITL state persisted in `task_state` section for crash recovery.
- Exit: All 3 shapes work with safety escalation and crash recovery.

**M14 -- Affect, Clarification Depth, Domain Rules** (Sections 6.1, 12)

- `compute_affect_band()` maps valence + arousal to 5 bands: crisis, low, neutral, positive, elevated.
- `AFFECT_TONE_BLOCKS` provides per-band prompt injection (tone, iteration budget, history window).
- Affect x mode interaction table for 6 special combinations.
- `ClarificationDepthState` tracks per-gap depth (0/1/2). Depth 2 = best guess, no re-ask.
- `DOMAIN_RULES` for 8 domains with safety floors (health=AMBER, legal=RED, etc.).
- Exit: Affect bands modulate prompts, clarification depth escalates, domain rules inject.

**M15 -- Experience Layer Stubs** (Section 12)

- 6 stub classes: EmotionalProcessor, AffectiveMirror, NarrativeWeaver, AnticipatoryResponder, ProactiveAgent, RhythmController.
- `ExperienceLayer.tick()` orchestrator with correct fire cadences (25th/20th/30th turn).
- Stubs return neutral defaults (`confidence=0.0`).
- EP skip rule: when Front's `refine_affect()` ran with confidence > 0.8, EmotionalProcessor skips.
- Exit: Stubs fire at correct cadences. Pluggability proven.

**M16 -- Orchestrator Stub & Tier Routing** (Section 11)

- `route_task()`: LOW -> Back directly, MEDIUM -> OrchestratorStub, HIGH -> deferred interface.
- `OrchestratorStub`: receive `TaskEnvelope`, execute 1-2 Fabric calls, return `AggregatedResult`.
- HIGH tier interfaces defined: `IPlannerPort`, `PlanRequest`, `CommittedPlan`, `PlanStep`.
- Degradation cascade: MEDIUM -> LOW fallback when orchestrator circuit breaker trips.
- Exit: LOW and MEDIUM tiers work. HIGH interface defined.

### Phase F: Quality & Prompts (M17 + M18)

**M17 -- Output Validation & Context Budget** (Section 10)

- `LLMOutputValidator`: 4 checks -- unknown tool, missing param, type mismatch, ACK ordering.
- `validated_generate()` retry wrapper: corrective prompt on malformed output, lower temperature by 0.2 (floor 0.3).
- Fallback: strip invalid tools, keep text.
- Pre-call context budget: 128K window, 80% safety margin.
- Cascading compression: 5 sections in priority order. Aggressive truncation: history -> 5 entries.
- Exit: Hallucinated tools caught, retry recovers, context fits.

**M18 -- Full System Prompts & In-Context Examples** (Sections 6.1, 6.2)

- 20 `PROMPT_SECTIONS` entries with full production text.
- `MODE_EXAMPLES` for all 10 PromptModes with multi-turn ReAct examples.
- `SCENARIO_DATA_TEMPLATES` for all 10 modes.
- Back prompt (~1,800 words): 8-section structure + 4 in-context examples.
- Multi-intent dispatch examples: 5 patterns (single, bundled, chained, conversational+action, pure conversation).
- Cross-section coherence verified: no assembled combination produces contradictions.
- Coherence hierarchy: `DOMAIN_RULES` > `SAFETY_HITL` > `AFFECT_TONE_BLOCKS` > `CLARIFY_DEPTH_BLOCKS` > base `PROMPT_SECTIONS`.
- Token savings validated against Section 14.3 targets.
- Exit: All prompts finalized, coherence verified, token savings confirmed.

### Phase G: End-to-End Integration (M19)

**M19 -- "One Ordinary Day" Demo** (Sections 13, 14)

- Execute all 30 turns of the demo storyline end-to-end with real LLM calls.
- All 7 acts complete: Before Dawn, Morning Machine, Midday Pivot, Crisis Hour, Afternoon Weave, Evening, Night Mode.
- All 12 validation goals from Section 14.2 verified.
- Demo runs as interactive session with device-based identity (Alex's phone -> Alex persona, Jordan's phone -> Jordan persona).
- Pre-register 15 demo capabilities as Back Fabric stubs with hardcoded realistic responses.
- Implement 4 IoT monitor stubs (LAUNDRY, DOORBELL, THERMOSTAT, OVEN) firing at scripted times.
- Latency verification: Front ACK < 200ms, Front total < 2s, Back execution < 4s, WEAVE batch window 500ms.
- 21-point E2E wiring checklist including: no anti-spin logic, no `_force_text_only`, Back never emits text to OUTPUT_CHANNEL, Back never calls Front-only tools, no code outside the adapter imports `google.genai`.
- Exit: 30 turns execute, 12 goals met, all tests pass.

---

## 15.4 Invariants Across All Phases

| # | Invariant | Enforcement |
| --- | --- | --- |
| 1 | **Each milestone is self-contained and testable.** | Exit criteria verified before proceeding to next milestone. No "partial" milestones. |
| 2 | **Tests are written in the same milestone as the code they test.** | No deferred test milestones. Each epic includes test specifications. |
| 3 | **No milestone introduces simulation code.** | Stubs return neutral defaults (not fake behavior). IoT monitors fire at scripted times (not simulated delays). |
| 4 | **All milestones reference V2 section numbers.** | Old doc section numbers (e.g., "old Section 27.13") do not appear in implementation tasks. |
| 5 | **The critical path determines schedule.** | M03 -> M04 -> M05 -> M06/M07 -> M08 -> M10 -> M11 -> M12 -> M13 -> M19. All other milestones run in parallel with the critical path or on shorter side branches. |
| 6 | **Milestone dependencies are hard blockers.** | M06 cannot start before M01+M02+M05 all pass exit criteria. No "start early, fix later." |

---

**Pull from:** Section 10.4 (what-disappeared table), Section 8 (what disappears — currently just a forward ref).

### Appendix A: What Disappeared (Old to New Mapping)

This appendix maps every component, pattern, and mechanism from the old single-loop POC to its replacement in the dual-LLM bus-driven architecture. If something is not listed here, it did not exist in the old POC.

#### A.1 Eliminated Components

These components existed in the old POC and have been structurally eliminated -- not replaced, removed entirely.

| Old Component | What It Did | Why It Is Gone |
| --- | --- | --- |
| `_force_text_only` flag | Blocked ALL tools when anti-spin detected cognitive-only loops | Bus-driven causal ordering (Section 3) eliminates the spin condition entirely. No heuristic flags needed. |
| `_cognitive_only` mode | Detected iterations where only cognitive tools fired, triggering anti-spin | Cognitive and functional tools are in different actors (Section 6). Front cannot call functional tools. The condition is structurally impossible. |
| `_ack_next_tool` exemption | Exempted `acknowledge` from anti-spin so the LLM could still ACK after cognitive-only detection | `acknowledge` is always the first tool via `tool_choice="required"` on iteration 0 (Section 7, ITEM #13). No exemption logic needed. |
| Anti-spin loop detector | Counted consecutive cognitive-only iterations and forced text output | Eliminated. Front's ReAct loop terminates on text-without-tools (L1, Section 7.5). Back terminates on `submit_result()` (L2). Both are explicit termination signals, not heuristic timeout conditions. |
| `messages = []` per turn | Cleared message history every turn, injecting prior history as flat system text | ReAct message history IS the working memory (Section 7). History persists across iterations within a turn. Cross-turn history is in SS `history_active` via `TypedHistoryEntry` (Section 5). |
| Single shared `loop.py` | One ReAct loop trying to be both conversational and productive | Replaced by shared `react_loop()` (Section 7) that serves BOTH actors with actor-specific termination. The loop itself is the same; the actors are different. |

#### A.2 Replaced Components

These components had equivalents in the old POC that are now replaced by structurally different mechanisms.

| Old Component | Old Behavior | New Replacement | V2 Section |
| --- | --- | --- | --- |
| `FrontScratchpad` | Ephemeral state accumulator for Front iterations | ReAct message history (in-loop) + `FSMTurnState` (cross-event) | Section 7 |
| `BackScratchpad` | Ephemeral state accumulator for Back iterations | ReAct message history (in-loop) + `FSMTurnState` (cross-event) | Section 7 |
| `ack_delivered` flag | Boolean tracking whether ACK was sent this turn | ReAct: LLM sees it already called `acknowledge` in its own message history. `tool_choice="required"` on iteration 0 guarantees it. | Section 7 |
| `tool_history` list | Flat list of tool names called this turn | ReAct: tool calls are messages in the array. `ReactResult.tool_calls_made` collects them. | Section 7 |
| `findings` list | Accumulated tool results for final presentation | ReAct: tool results are observation messages. Back's `submit_result()` packages the final output. | Section 7 |
| `cancellation_token` | Shared mutable flag for task cancellation | `FSMTurnState.cancellation_requested` checked between ReAct iterations via `cancellation_check` callback | Section 8.7 |
| `suspension_context` | Saved state for resuming suspended tasks | On resume: FSM replays the task dispatch + prior ReAct message history. Back continues from saved `ReactState`. | Section 8.8-8.9 |
| `execution_budget` counter | Decrementing counter limiting tool calls | `max_iterations` param on `react_loop()`. Set per complexity tier: LOW=3, MEDIUM=6, HIGH=10. | Section 7 |
| Phase A/B/C/D ordering | Hard-coded 4-phase execution within one loop iteration | ReAct iteration order taught via system prompt rhythm. `tool_choice="required"` for iteration 0, `"auto"` thereafter. | Section 7 |
| Monolithic system prompt | Single ~5,700-token prompt for all situations | `DynamicPromptBuilder` with 10 `PromptMode` values, per-mode composable sections, 45% avg token savings | Section 6.1 |
| Scenario-based context assembly | 6 scenarios selecting SS sections | 10 `PromptMode` values with `SS_READ_CONFIGS` per mode, `TOOL_ALLOWLIST` per mode | Section 6.1 |
| Direct LLM provider calls | `google.genai` imported throughout handler code | `IConciergeModelPort` protocol. Only `GeminiConciergeAdapter` imports `google.genai`. All actors call the port interface. | Section 10 |
| Flat history injection | Prior turns injected as system prompt text | `TypedHistoryEntry` with structured fields (`turn`, `type`, `async_task`). `get_typed_entries()` API. | Section 5 |
| `DemoRunner` FSM | Synchronous loop-driving FSM | `ConciergeController` -- event-driven FSM with 12 states, bus subscriptions, FrontLock, WeaveBatcher | Section 4 |

#### A.3 New Mechanisms (No Old Equivalent)

These are architecturally new -- they did not exist in any form in the old POC.

| New Mechanism | Purpose | V2 Section |
| --- | --- | --- |
| K1 Event Bus (`LocalBus`) | Actor coordination via publish/subscribe with causal ordering | Section 3 |
| `TimingChain` | Causal + sequence ordering enforcement per delivery mode (STRICT/RELAXED/BEST_EFFORT) | Section 3 |
| `Envelope` with `parent_id` | Causal chain linking: every event traces back to its cause | Section 3 |
| `LocalMailboxRouter` | Point-to-point actor messaging with WFQ scheduling | Section 3 |
| `SessionBusAdapter` | Bridge between SessionState `IEventPort` and `IBus` | Section 3 |
| `DeltaAggregator` | Batches Back deltas in 500ms windows before FSM writes to SS | Section 5 |
| `MutationGuard` | Validates every SS write against section/tier/total budgets | Section 5 |
| `FrontLock` | Serializes concurrent Front-targeted events with priority ordering | Section 4 |
| `FSMTurnState` | Ephemeral per-turn state: `pending_results`, `cancelled_tasks`, `active_react_state` | Section 4 |
| `WeaveBatcher` | Batches async results in 500ms windows for unified Front presentation | Section 8.11 |
| `PromptMode` enum | 10 modes determining prompt assembly, tool allowlist, SS reads | Section 4, 6.1 |
| `determine_mode()` | Deterministic mode selection from FSM state + envelope + SS fields | Section 4 |
| `DynamicPromptBuilder` | 12-step composable prompt assembly pipeline | Section 6.1 |
| `tool_choice="required"` | Forces `acknowledge` as first tool call on iteration 0 | Section 7 |
| HITL Protocol | 3 shapes (clarification, approval, selection) with safety band escalation | Section 9 |
| `TaskDispatch` with `intents[]` | Multi-intent dispatch: bundled, chained, concurrent patterns | Section 8 |
| `ExperienceLayer` | 6 stub components with defined cadences, Front-only, pluggable | Section 12 |
| `OrchestratorStub` | MEDIUM-tier task routing with degradation cascade | Section 11 |
| `LLMOutputValidator` | Catches hallucinated tools, missing params, ordering violations | Section 10 |
| `validated_generate()` | Retry wrapper with corrective prompt on malformed LLM output | Section 10 |
| Device-based identity | Per-member persona loading based on device registration | Section 5 |
| Cross-member privacy | Visibility rules controlling what each member can see | Section 5 |

---

### Appendix B: Gap Resolution Summary

Historical record of the 19-item gap analysis performed during the V2 restructuring. Each gap identified a conflict, duplication, or missing specification in the old document. All gaps are now resolved and their resolutions are incorporated into the relevant V2 sections.

| # | Gap | Resolution | V2 Section |
| --- | --- | --- | --- |
| 1 | Tool count disagreement (10 vs 13 vs 14) | 10 Front + 6 Back = 14 unique (recall_memory shared, actor="both") | Section 6.1, 6.2 |
| 2 | Scenarios define mechanisms inline | Mechanisms moved to owning sections. Scenarios (Section 13) illustrate only. | Section 13 |
| 3 | `acknowledge` ordering ambiguity | `tool_choice="required"` on iteration 0 forces ACK first. No exemption flags. | Section 7 |
| 4 | FSM state table incomplete | 12 states with PromptMode mapping via `determine_mode()` | Section 4 |
| 5 | Affect band definitions scattered | 5 bands (crisis/low/neutral/positive/elevated) with modifier matrix in one table | Section 6.1 |
| 6 | Token savings table buried in Front spec | Moved to Section 14.3 as validation metric | Section 14.3 |
| 7 | Test examples inline with design | Test catalog in Appendix C. Tests live in test directory. | Appendix C |
| 8 | Session State schema incomplete | 10 HOT sections, 52KB budget, typed history, persona | Section 5 |
| 9 | Back system prompt contradicts design | 1 retry per capability (2 total attempts). Section 6.2 authoritative. | Section 6.2, 14.4 |
| 10 | HITL protocol scattered across sections | Unified in Section 9 with 3 shapes, safety bands, timeouts | Section 9 |
| 11 | Task model defined in multiple places | Single definition in Section 8 with all patterns | Section 8 |
| 12 | Weave protocol defined in scenario section | Moved to Section 8.10-8.11. WeaveBatcher defined once. | Section 8.10-8.11 |
| 13 | `tool_choice` not specified per iteration | Iteration 0: "required". Iteration 1+: "auto". Stated in Section 7. | Section 7 |
| 14 | Cancellation protocol spread across old sections | Unified in Section 8.7 with `cancellation_requested` flag | Section 8.7 |
| 15 | Suspension protocol incomplete | Full suspend/resume with ReAct history preservation in Section 8.8-8.9 | Section 8.8-8.9 |
| 16 | Retry count disagreement ("2x" vs "1 retry") | Resolved: 1 retry per capability = 2 total attempts. Stated in Section 14.4. | Section 6.2, 14.4 |
| 17 | EP skip rule defined in two places | Section 5 owns definition. Section 12 applies it. No redefinition. | Section 5, 12 |
| 18 | DynamicPromptBuilder code separated from prose | Code and prose together in Section 6.1. No separate code appendix. | Section 6.1 |
| 19 | Experience Layer scope unclear | Front-only. Stubs with `pass`. Pluggable. Defined once in Section 12. | Section 12 |

---

### Appendix C: Test Catalog

Tests do NOT go inline with design sections. This appendix catalogs all test functions referenced in the design document, organized by the V2 section whose specification they exercise. The tests themselves are implementation artifacts -- they live in the test directory, not in the design doc.

#### C.1 Bus & TimingChain Tests (Section 3)

| Test | Validates | Assertions |
| --- | --- | --- |
| `test_all_poc_topics_resolve_correctly` | All 17 topics resolve to expected `DeliveryMode` | STRICT for orchestration/response/session/hil; RELAXED for affect/proactive |
| `test_timing_chain_defaults` | `TimingChain` constructor defaults | `timeout_ms=5000`, `default=RELAXED` |
| `test_create_local_ordered_uses_python_backend` | Factory returns `LocalBus`, not `RustBusAdapter` | `isinstance(bus, LocalBus)` |
| `test_strict_ordering_enforced` | STRICT topics delivered in causal order | Envelopes with `parent_id` chains arrive in sequence |
| `test_gap_timeout_forces_delivery` | Buffered envelopes force-deliver after 5s timeout | Envelope delivered even without parent arrival |
| `test_envelope_builders_produce_valid_envelopes` | Builder functions produce correct topic, priority, payload | All 17 builders validated |

#### C.2 FSM & State Transition Tests (Section 4)

| Test | Validates | Assertions |
| --- | --- | --- |
| `test_user_input_standard_mode` | `determine_mode()` returns STANDARD for basic user input | `mode == PromptMode.STANDARD` |
| `test_user_input_with_suspended_task_is_hitl_resolve` | Suspended task triggers HITL_RESOLVE | `mode == PromptMode.HITL_RESOLVE` |
| `test_task_complete_is_present` | `task.complete` triggers PRESENT mode | `mode == PromptMode.PRESENT` |
| `test_fsm_transitions_all_12_states` | All 12 states reachable via correct event sequences | State graph fully traversed |
| `test_frontlock_serializes_concurrent_events` | FrontLock queues concurrent events with priority ordering | Higher-priority event processed first |

#### C.3 ReAct Loop Tests (Section 7)

| Test | Validates | Assertions |
| --- | --- | --- |
| `test_front_terminates_on_text_without_tools` | L1 termination: text response with no tool calls | `result.status == "completed"`, `result.text != ""` |
| `test_back_terminates_on_submit_result` | L2 termination: `submit_result()` call | `result.status == "completed"`, `submit_result` in tool history |
| `test_back_thinking_aloud_continues` | Back text without `submit_result` does not terminate | Loop continues to next iteration |
| `test_cancellation_checked_between_iterations` | `cancellation_check` fires between model calls | `result.status == "cancelled"`, model called exactly once |
| `test_budget_exhaustion_returns_fallback` | `max_iterations` exceeded produces fallback | `result.status == "budget_exhausted"` |
| `test_tool_choice_required_on_iteration_0` | First iteration uses `tool_choice="required"` | Request to model has `tool_choice="required"` |
| `test_dispatch_task_calls_collected` | L3: `dispatch_task` calls collected for post-loop emission | `result.dispatches` contains all `dispatch_task` calls |

#### C.4 Task Model Tests (Section 8)

| Test | Validates | Assertions |
| --- | --- | --- |
| `test_single_intent_dispatch` | Single intent produces one Back task | One `task.dispatch` envelope on bus |
| `test_bundled_intents_single_react_loop` | Multiple intents execute in one Back loop | One `submit_result` covers all intents |
| `test_chained_tasks_hydration` | `depends_on` tasks held until parent completes, then `$ref` resolved | Dependent task receives parent's output |
| `test_weave_batcher_500ms_window` | Results within 500ms grouped into one batch | Single Front invocation for batched results |
| `test_cancellation_flag_checked_at_tool_boundary` | `cancellation_requested` stops Back between tools | `task.failed(cancelled)` emitted |

#### C.5 HITL Protocol Tests (Section 9)

| Test | Validates | Assertions |
| --- | --- | --- |
| `test_hitl_approval_full_cycle` | Back suspend -> Front relay -> user confirm -> Back resume | Task completes after approval |
| `test_hitl_selection_three_options` | Selection with 3 options presented, user picks one | Correct option forwarded to Back |
| `test_hitl_clarification_timeout` | 60s timeout triggers auto-cancel | `task.failed` with `reason="hitl_timeout"` |
| `test_safety_band_escalation` | GREEN auto-approves, AMBER confirms, RED blocks | Correct behavior per safety band |
| `test_hitl_crash_recovery` | HITL state survives process restart via `task_state` persistence | Resumed from persisted state |

#### C.6 Experience Layer Cadence Tests (Section 12)

| Test | Validates | Assertions |
| --- | --- | --- |
| `test_emotional_processor_fires_every_25_turns` | EmotionalProcessor fires at turns 25, 50, 75, 100 | `fired == [25, 50, 75, 100]` |
| `test_affective_mirror_fires_with_emotional` | AffectiveMirror fires on same tick as EmotionalProcessor | `"tone" in result` on turn 25 |
| `test_ep_skip_rule_respects_front_confidence` | Front `refine_affect()` confidence > 0.8 skips EmotionalProcessor | `"trajectory" not in result` |
| `test_proactive_fires_only_in_companioning_with_wait` | ProactiveAgent fires only when COMPANIONING AND wait > 5s | `"fill" in result` only in correct state |
| `test_rhythm_fires_every_tick` | RhythmController fires on every tick regardless | Always present in result |

#### C.7 Dynamic Prompt Mode Tests (Section 6.1)

| Test | Validates | Assertions |
| --- | --- | --- |
| `test_standard_mode_includes_all_tools` | STANDARD mode has full 10-tool allowlist | All 10 Front tools present |
| `test_hitl_relay_has_zero_tools` | HITL_RELAY mode has empty tool allowlist | `len(tools) == 0` |
| `test_present_mode_slim_ss_reads` | PRESENT mode reads SLIM beliefs, FULL task_state | SS read config matches spec |
| `test_affect_band_modifies_iterations` | Crisis band reduces `max_iterations` by 1 | `config.max_iterations == default - 1` |
| `test_token_count_per_mode` | Each mode's assembled prompt matches expected token range | Within +/- 10% of Section 14.3 targets |
| `test_clarification_depth_escalation` | Depth 0 -> 1 -> 2 across re-asks for same gap | Depth 2 states assumption, does not re-ask |
| `test_domain_rules_inject_safety_floor` | Health domain injects AMBER safety floor | `safety_floor == "AMBER"` in assembled prompt |
| `test_conditional_refine_affect_inclusion` | `refine_affect` included only when affect confidence < threshold | Tool present/absent based on confidence |
| `test_conditional_promote_belief_inclusion` | `promote_belief` included only when beliefs section non-empty | Tool present/absent based on beliefs state |

#### C.8 LLM Adapter & Validation Tests (Section 10)

| Test | Validates | Assertions |
| --- | --- | --- |
| `test_adapter_generates_valid_response` | `IConciergeModelPort.generate()` returns `ConciergeModelResponse` | Response has text or tool_calls |
| `test_adapter_streams_chunks` | `generate_stream()` yields `StreamChunk` objects | At least one chunk yielded |
| `test_validator_catches_unknown_tool` | `LLMOutputValidator` rejects hallucinated tool names | `ValidationError(type="unknown_tool")` |
| `test_validator_catches_missing_param` | Validator rejects tool calls with missing required params | `ValidationError(type="missing_param")` |
| `test_validated_generate_retries_on_malformed` | `validated_generate()` retries with corrective prompt | Second call succeeds after correction |
| `test_context_budget_compression_triggers` | Prompt exceeding 80% of window triggers cascading compression | Compressed prompt fits within budget |

---

## Structural Rules for the Rewrite

1. **No "supersedes" notices.** If something is the truth, it's the only version. Delete the old version.
2. **No forward references to sections that redefine earlier content.** If the FSM section needs PromptMode, define PromptMode there or define it before the FSM section.
3. **Each concept appears once.** Tool schemas live in the actor section, period. Not also in a "tool catalog" section and a "tool allowlist" section.
4. **Code follows prose within the same section.** Don't describe `DynamicPromptBuilder` conceptually in Section 27.1 and then show the code in 27.11. Put the explanation and the code together.
5. **Scenarios illustrate; they don't define.** Section 6 currently defines the Weave protocol, the cancellation contract, and the suspension contract inside scenario walkthroughs. Those definitions should move to their mechanism sections. Scenarios just demonstrate.
6. **Tables are definitive, not duplicated.** One read/write matrix. One tool-per-actor table. One FSM state table. If it needs a column added, add the column -- don't create a second table in a later section.
