# 11 — Diagram Scan: Concierge Unified Architecture

> **Source files scanned:**
> - `k1/concierge/concierge_unified.mmd` — 1334 lines (MAIN, merged 2026-04-01)
> - `k1/concierge/docs/concierge_poc_architecture.mmd` — 1086 lines (POC, created 2026-02-19)
>
> The unified diagram is the **single source of truth**, merged from the POC diagram and the original `concierge.mmd` (1112 lines, hexagonal + services + lifecycle).

---

## 1. Subgraph / Component Blocks (Complete Inventory)

### 1.1 Unified Diagram — Top-Level Subgraphs

The entire diagram is a `flowchart TB` with layout engine `elk`. Everything inside the `CONCIERGE` subgraph is Concierge-owned. Everything outside is in the `TOUCHPOINTS` subgraph.

| # | Subgraph ID | Label | Parent | Purpose |
|---|------------|-------|--------|---------|
| 1 | `CONCIERGE` | 🧠 Concierge — Conversation Conductor | root | Entire Concierge boundary |
| 2 | `PORTS` | 🔌 Ports (8 Boundary Contracts) | CONCIERGE | Hexagonal port definitions |
| 3 | `ADAPTERS` | 🔧 Adapters (Infrastructure Bindings) | CONCIERGE | Adapter layer |
| 4 | `ADAPTERS_PROD` | Production Adapters | ADAPTERS | 8 real adapters |
| 5 | `ADAPTERS_TEST` | Test Adapters | ADAPTERS | 8 mock adapters |
| 6 | `FSM` | 🔄 Concierge FSM (State Machine Controller) | CONCIERGE | FSM core |
| 7 | `FSM_CORE_STATES` | Core Loop States | FSM | 5 main states |
| 8 | `FSM_INTERRUPT_STATES` | Interrupt / Special States | FSM | 6 interrupt states |
| 9 | `GUARD_MODEL` | Guard Model (5 Actions) | FSM | TRANSITION/PASSTHROUGH/OBSERVE/QUEUE/DEAD_LETTER |
| 10 | `FSM_TURN_STATE` | FSMTurnState | FSM | pending_results, cancelled_tasks, cancel_flag |
| 11 | `FRONT_LOCK` | FrontLock (Concurrency Gate) | FSM | busy, event_queue, priority |
| 12 | `ACKING_CORE` | ⚡ ACKING Core (Phase 1: UltraBERT) | CONCIERGE | Pre-LLM classification |
| 13 | `ULTRABERT_ENGINE` | UltraBERT v4 | ACKING_CORE | 149M param engine |
| 14 | `ULTRABERT_HEADS` | Classification Heads (7) | ULTRABERT_ENGINE | Intent, Ingress, Safety, Emotions, Sentiment, NER, Relations |
| 15 | `SAFETY_GATE` | Safety Gate | ACKING_CORE | Crisis Detector + Safety Override |
| 16 | `COMPLEXITY_ROUTER` | Complexity Router V2 | ACKING_CORE | Multi-factor + 4 tiers |
| 17 | `HYPOTHESIS_PIPELINE` | Hypothesis & Gap Detection | ACKING_CORE | Generator + Contract/Signal gaps |
| 18 | `TIME_RESOLUTION` | Temporal Resolution Engine | ACKING_CORE | Parser + Resolver + TZ + Anchor |
| 19 | `SPATIAL_RESOLUTION` | Spatial Context Engine (ADR-0085/0085a) | ACKING_CORE | Location + Place Registry + Motion |
| 20 | `CONTEXT_INFERENCE` | Context Inference & Validation | ACKING_CORE | CTX Inference + Tiny Sanity Arbiter |
| 21 | `UNCERTAINTY_ROUTING` | Uncertainty Estimation & Clarification | ACKING_CORE | Estimator + Entropy Question Planner |
| 22 | `OPP2_RECENCY` | OPP-2: Recency Bias Decay | ACKING_CORE | Arbiter + decay + short-input penalty |
| 23 | `WRITE_ELISION` | Write Elision Gate | ACKING_CORE | Signal significance scoring |
| 24 | `FRONT_ACTOR` | FRONT LLM ACTOR (The Concierge Voice) | CONCIERGE | Front LLM boundary |
| 25 | `FRONT_SUBSCRIBES` | Subscribes To (5 topics) | FRONT_ACTOR | Input + Complete/Failed/Findings/Suspended |
| 26 | `FRONT_EMITS` | Emits (6 topics) | FRONT_ACTOR | Ack + Dispatch + Cancel + Resume + ClarifyRsp + Final |
| 27 | `FRONT_TOOLS` | Front Tools (10 total) | FRONT_ACTOR | Signal(1) + Cognitive(6) + Read(2) + Control(1) |
| 28 | `FT_SIGNAL` | Signal (1) | FRONT_TOOLS | acknowledge_request() |
| 29 | `FT_COGNITIVE` | Cognitive (6) | FRONT_TOOLS | beliefs, scoreboard, clarify, narrative, affect, promote |
| 30 | `FT_READ` | Read (2) | FRONT_TOOLS | recall_memory, summarize_context |
| 31 | `FT_CONTROL` | Control (1) | FRONT_TOOLS | dispatch_task() |
| 32 | `FRONT_REACT` | ReAct Loop | FRONT_ACTOR | Shared react_loop(actor='front') |
| 33 | `BACK_ACTOR` | BACK LLM ACTOR (The Worker) | CONCIERGE | Back LLM boundary |
| 34 | `BACK_SUBSCRIBES` | Subscribes To (4 topics) | BACK_ACTOR | Dispatch + Cancel + Resume + ClarifyRsp |
| 35 | `BACK_EMITS` | Emits (8 topics) | BACK_ACTOR | tool_start/done + complete/failed/suspended/findings + booking/artifact |
| 36 | `BACK_TOOLS` | Back Tools (7 total) | BACK_ACTOR | Read(2) + Action(4) + Control(1) |
| 37 | `BT_READ` | Read (2) | BACK_TOOLS | recall_memory, discover_capabilities |
| 38 | `BT_ACTION` | Action (4) | BACK_TOOLS | invoke_capability, batch_invoke, spawn_via_fabric, execute_workflow |
| 39 | `BT_CONTROL` | Control (1) | BACK_TOOLS | submit_result() |
| 40 | `BACK_REACT` | ReAct Loop | BACK_ACTOR | react_loop(actor='back') |
| 41 | `REACT_SYSTEM` | ReAct Loop System | CONCIERGE | Recovery + Scratchpad |
| 42 | `REACT_RECOVERY` | Recovery / Nudge Patterns | REACT_SYSTEM | 4 guards + 5 recovery patterns |
| 43 | `SCRATCHPAD` | 💭 ReactLoopScratchpad (ADR-0098) | REACT_SYSTEM | Ephemeral per-dispatch scratchpad |
| 44 | `SESSION_STATE` | SESSION STATE (HOT 52KB + WARM 48KB) | CONCIERGE | Shared memory |
| 45 | `SS_COGNITIVE` | Cognitive Sections | SESSION_STATE | 5 sections, Front writes |
| 46 | `SS_SYSTEM` | System Sections | SESSION_STATE | 3 sections, FSM/Phase1 writes |
| 47 | `SS_TASK` | Task Sections | SESSION_STATE | 2 sections, FSM via DeltaAggregator |
| 48 | `SS_STATIC` | Static Section | SESSION_STATE | persona (immutable) |
| 49 | `SS_WARM` | WARM Tier (48KB) | SESSION_STATE | 4 warm sections |
| 50 | `SS_MUTATION` | MutationGuard (3-Tier Validation) | SESSION_STATE | Section → Tier → Total + Emergency |
| 51 | `K1_BUS` | K1 EVENT BUS | CONCIERGE | Central communication |
| 52 | `BUS_CORE` | Bus Infrastructure | K1_BUS | LocalBus + TimingChain + MailboxRouter |
| 53 | `BUS_TOPICS` | Topic Taxonomy | K1_BUS | All topics organized by category |
| 54 | `TOPICS_SESSION` | Session Events (3) | BUS_TOPICS | user.input, booking.confirmed, artifact.created |
| 55 | `TOPICS_RESPONSE` | Response Events (3) | BUS_TOPICS | ack, final, clarification |
| 56 | `TOPICS_ORCH` | Orchestration Events (10) | BUS_TOPICS | dispatch/complete/failed/cancel/suspended/resume/findings/accepted/delta/dag.completed |
| 57 | `TOPICS_TOOL` | Tool Events (2) | BUS_TOPICS | started, completed |
| 58 | `TOPICS_CLARIFY` | Clarification Events (2) | BUS_TOPICS | request, response |
| 59 | `TOPICS_INTERNAL` | Internal / Relaxed Topics (5+) | BUS_TOPICS | affect, proactive, weave_batch, hil_req/rsp, turn_complete |
| 60 | `BUS_CAUSAL` | Causal Chain | K1_BUS | parent_id enforcement tree |
| 61 | `BUS_DELTA` | Delta Aggregation | K1_BUS | 500ms batch, LWW dedup |
| 62 | `PROMPT_ARCH` | 📝 Dynamic Prompt Architecture (10 Modes) | CONCIERGE | Mode-driven prompt assembly |
| 63 | `PROMPT_MODES` | PromptMode Enum | PROMPT_ARCH | 10 modes with tool counts + token budgets |
| 64 | `PROMPT_COMPONENTS` | Composable Sections (10) | PROMPT_ARCH | Identity, React, State, Cognitive, Dispatch, Emotion, Safety, Weave, Anti, Examples |
| 65 | `AFFECT_MODULATION` | Affect Modulation (5 Bands) | PROMPT_ARCH | CRISIS/LOW/NEUTRAL/POSITIVE/ELEVATED |
| 66 | `OPP7_IDENTITY` | OPP-7: Dynamic Identity | PROMPT_ARCH | EXPERT/PEER/GUIDE/SUPPORTER/EXECUTOR |
| 67 | `DOMAIN_RULES` | Domain Rule Injection (8 Domains) | PROMPT_ARCH | health/finance/elder/children/emergency/legal/travel/productivity |
| 68 | `SERVICES` | 🏗️ Internal Services (9 Components) | CONCIERGE | ~585 tests total |
| 69 | `PROTOCOLS` | 📋 Protocols (19 Files) | CONCIERGE | HITL, Weave, OPP, Cancel, Suspend |
| 70 | `HITL` | HITL Protocol | PROTOCOLS | 3 variants + L2 enforcer |
| 71 | `WEAVE_SYSTEM` | Weave & Batching Protocol | PROTOCOLS | WeaveBatcher + OPP-1 + OPP-8 |
| 72 | `CANCEL_SUSPEND` | Cancellation + Suspension | PROTOCOLS | CancellationHandler + SuspensionManager |
| 73 | `OPP_PIPELINE` | OPP Pipeline (8 Primitives, 9 Hooks) | PROTOCOLS | Wiring layer for all OPP primitives |
| 74 | `EXPERIENCE` | 🌟 Experience Layer (6 Components) | CONCIERGE | 3 real + 3 stubs |
| 75 | `STREAMING` | 📡 Streaming Infrastructure (~150 Tests) | CONCIERGE | 8 streaming components |
| 76 | `TIERS` | Complexity Tiers & Task Model | CONCIERGE | LOW/MED/HIGH paths + degradation |
| 77 | `CONTEXT_ASSEMBLY` | Context Assembly | CONCIERGE | OPP-6 + SessionTrajectory + ChatHistory |
| 78 | `SAFETY_BANDS` | Safety Band Enforcement | CONCIERGE | GREEN/AMBER/RED |
| 79 | `LLM_INTERNAL` | LLM Internal | CONCIERGE | IConciergeModelPort wraps ILLMPort |
| 80 | `LIFECYCLE` | 🔄 Lifecycle (6 Phases) | CONCIERGE | init/turn_start/turn_end/abbreviated/shutdown/crash_recovery |
| 81 | `INVARIANTS` | ⚖️ Invariants (21 Rules, 6 Categories) | CONCIERGE | Ownership/Safety/Rate/Timing/Structural/Token |
| 82 | `PERF` | ⏱️ Performance Baselines | CONCIERGE | P99 targets + budget envelopes |
| 83 | `ERROR_RECOVERY` | Error Recovery (3 Severity Levels) | CONCIERGE | RECOVERABLE/DEGRADED/TERMINAL |

### 1.2 External Touchpoints Subgraphs (Outside Concierge Boundary)

| # | Subgraph ID | Label | Contents |
|---|------------|-------|----------|
| 84 | `TOUCHPOINTS` | 🔗 External Touchpoints | All items below |
| 85 | `TP_ORCHESTRATOR` | Orchestrator | OrchestratorActor + TopologicalWalker + StepRetry |
| 86 | `TP_PLANNER` | Planner (4-Stage) | PlannerAgent + HIL + 4 discovery tools |
| 87 | `TP_FABRIC` | Capability Fabric | CapabilityFabric + Registry + 9-Step Pipeline + AgentFactory |
| 88 | `TP_MODEL_HUB` | Model Hub | Capability routing + OutputValidation (T1→T2→T3) |
| 89 | `TP_BRIDGE` | Cross-Kernel Bridge | BridgeClient + SSEReceiver |
| 90 | `TP_OUTPUT` | Output System | OUTPUT_CHANNEL + OutputQueue (3 priorities) |
| 91 | `TP_PROACTIVE` | Proactive Agent System | DecisionEngine + CuriosityAgent + BudgetGate (3/day) |
| 92 | `TP_MEMORY_WRITER` | Memory Writer + Learning | MW (0-3 memories/turn) + LearningLoop (5 detectors) |
| 93 | `TP_SUBAGENTS` | Spawned Agents | Dynamic + Safety agents |
| 94 | `TP_CIRCUIT_BREAKERS` | Circuit Breakers (7) | CB_MODEL/ORCH/PLANNER/FABRIC/MCP/SS/SSE |

---

## 2. FSM State Machine (Complete)

### 2.1 States (11 coded + 1 proposed)

**Core Loop States (5):**
| State | Entry Condition | Key Behavior |
|-------|----------------|--------------|
| `LISTENING` | Session start or DELIVERING complete | Idle, awaiting user input |
| `DISPATCHING` | user.input received | Phase 1 + Front LLM: classify, cognitive, dispatch |
| `COMPANIONING` | task.dispatch emitted | Front idle, Back working; can accept new input |
| `PROGRESSING` | Back streaming deltas | Progress narration to user |
| `DELIVERING` | task.complete received | Final results + next steps LLM call |

**Interrupt / Special States (6):**
| State | Entry Condition | Key Behavior |
|-------|----------------|--------------|
| `CLARIFYING_USER` | Front detected ambiguity (uncertainty ≥ 0.2) | Progressive disclosure |
| `CLARIFYING_WORKER` | Back suspended, needs user input | HITL relay/resolve |
| `CANCELLING` | Cancel intent detected | Cooperative cancel tokens |
| `INTERRUPT_HANDLING` | New user.input during COMPANIONING | Reset routing, re-ACKING |
| `PROACTIVE_WAKE` | task.complete while LISTENING | Idle delivery |
| `WEAVING` | pending_results queue non-empty after DELIVERING | Drain WeaveBatcher |

**Proposed (not coded):** `BACKGROUND_WORKING` — needs ADR-0097.

### 2.2 State Transitions (All Edges)

```
LISTENING →[user.input]→ DISPATCHING
DISPATCHING →[response.final (no dispatch)]→ LISTENING
DISPATCHING →[task.dispatch]→ COMPANIONING
DISPATCHING →[uncertainty ≥ 0.2]→ CLARIFYING_USER
CLARIFYING_USER →[user_response]→ DISPATCHING
COMPANIONING →[task.complete]→ DELIVERING
COMPANIONING →[new user.input]→ INTERRUPT_HANDLING
COMPANIONING →[cancel intent]→ CANCELLING
DELIVERING →[response.final]→ LISTENING
DELIVERING →[pending_results?]→ WEAVING
DELIVERING →[user.ack]→ LISTENING
WEAVING →[queue drained]→ LISTENING
LISTENING →[task.complete (idle)]→ PROACTIVE_WAKE
INTERRUPT_HANDLING →[re-classify]→ DISPATCHING
```

### 2.3 Guard Model (5 Actions)

| Action | Behavior |
|--------|----------|
| `TRANSITION` | Validate + change state |
| `PASSTHROUGH` | Forward, no state change |
| `OBSERVE` | Log only, no routing |
| `QUEUE` | Hold in FrontLock or pending_results |
| `DEAD_LETTER` | Reject as invalid |

### 2.4 FSMTurnState (Internal, Not LLM-Visible)

- `pending_results: deque` — task.complete payloads queued for Weave
- `cancelled_tasks: set` — Dedup for cancel vs complete race
- `cancellation_requested` — Checked by react_loop between iterations

### 2.5 FrontLock (Concurrency Gate)

- `busy: bool` — True while Front LLM generating
- `event_queue: deque` — Events queued when Front busy
- Priority order: user.input (URGENT) > task.suspended > task.complete > task.failed > findings.ready

---

## 3. All Data Flow Arrows (Categorized)

### 3.1 Port → Adapter Wiring (16 edges, 8 prod + 8 test)

| Port | Production Adapter | Test Adapter |
|------|-------------------|--------------|
| `IInputPort` | WebSocketInputAdapter, RESTInputAdapter | TestInputAdapter |
| `IOutputPort` | SSEOutputAdapter, WebSocketOutputAdapter (CB_SSE) | TestOutputAdapter |
| `IClassificationPort` | UltraBERTv4Adapter (CB_MODEL) | MockClassificationAdapter |
| `ILLMPort` | ModelGatewayAdapter (CB_MODEL) | MockLLMAdapter |
| `IStatePort` | SessionKernelAdapter (CB_SESSIONSTATE, MutationGuard) | InMemoryStateAdapter |
| `IDispatchPort` | FabricOrchestratorAdapter (CB_ORCH+PLANNER+FABRIC+MCP) | MockDispatchAdapter |
| `IDeltaPort` | DeltaBusAdapter | TestDeltaAdapter |
| `IMemoryPort` | BridgeRecallAdapter | MockMemoryAdapter |

### 3.2 Adapter → External Touchpoint (8 edges)

```
SSEOutputAdapter → OUTPUT_CHANNEL
UltraBERTv4Adapter → ULTRABERT_CORE
ModelGatewayAdapter → MODEL_HUB
SessionKernelAdapter → SESSION_STATE
FabricOrchestratorAdapter → CAPABILITY_FABRIC
FabricOrchestratorAdapter → ORCHESTRATOR_ACTOR
DeltaBusAdapter → K1_BUS
BridgeRecallAdapter → BRIDGE_CLIENT
```

### 3.3 User Input → FSM → Phase 1 → Bus

```
IInputPort →[receive()]→ ConciergeController
ConciergeController →[classify]→ IClassificationPort
IClassificationPort →[ClassificationResult]→ ConciergeController
WriteElisionGate →[WRITE safety_band (ALWAYS)]→ IStatePort
WriteElisionGate →[WRITE control, intents (if significant)]→ IStatePort
WriteElisionGate →[WRITE beliefs, affect (if detected)]→ IStatePort
WriteElisionGate →[ELIDE: carry forward]→ ConciergeController
ConciergeController →[emit user.input.v1]→ IDeltaPort
```

### 3.4 ACKING Internal Flow

```
ConciergeController → ULTRABERT_CORE → 12 heads parallel → ULTRABERT_HEADS
Safety Head → Crisis Detector → Safety Override → CRISIS tier → IOutputPort (hardcoded)
Intent Head → Multi-Intent Scorer → Complexity Classifier → LOW/MED/HIGH
Ingress Head → Cross-Domain Detector → Complexity Classifier
Intent Head + Ingress Head → Hypothesis Generator → Contract/Signal Gaps → Signal Library
NER (TIME/DATE) → Time Parser → Time Resolver → TZ Context / Temporal Anchor → Context Inference
NER (LOC) → Location Resolver → Place Registry / Spatial Anchor
NER (entities) + Relations Head → Context Inference → Tiny Sanity Arbiter
Tiny Sanity Arbiter → Uncertainty Estimator → Entropy Question Planner → CLARIFYING_USER state

All Phase 1 outputs → Write Elision Gate (per-section significance scoring)
UltraBERT Core →[classify()]→ OPP-2 Arbiter →[decayed scores]→ ConciergeController
```

### 3.5 Bus → Actor Subscriptions

**Front subscribes to (5):** user.input, task.complete, task.failed, findings.ready, task.suspended
**Back subscribes to (4):** task.dispatch, task.cancel, task.resume, clarification.response

### 3.6 Actor → Bus Emissions

**Front emits (6):** response.ack, task.dispatch, task.cancel, task.resume, clarification.response, response.final
**Back emits (8):** tool.started, tool.completed, task.complete, task.failed, task.suspended, findings.ready, booking.confirmed, artifact.created

### 3.7 Bus → Output Channel

```
response.ack →[stream]→ OUTPUT_CHANNEL
response.final →[display]→ OUTPUT_CHANNEL
response.clarification →[display]→ OUTPUT_CHANNEL
```

### 3.8 Front Tools → SessionState (via IStatePort + MutationGuard)

```
update_beliefs() →[MutationGuard]→ beliefs_active
update_scoreboard() →[MutationGuard]→ scoreboard
update_clarifications() →[MutationGuard]→ clarifications
update_narrative() →[MutationGuard]→ narrative_active
refine_affect() →[MutationGuard]→ affective_now
promote_belief() →[MutationGuard]→ beliefs_active
```

### 3.9 Back Deltas → FSM → SessionState

```
artifact.created →[delta]→ DeltaAggregator
task.complete →[delta]→ DeltaAggregator
DeltaAggregator →[FSM.apply_deltas()]→ ConciergeController
ConciergeController → task_state, task_artifacts, history_active, meta
```

### 3.10 Back Tools → Fabric (via IDispatchPort)

```
invoke_capability() →[dispatch_direct]→ IDispatchPort → CAPABILITY_FABRIC
batch_invoke_capabilities() →[dispatch_direct (batch)]→ IDispatchPort
discover_capabilities() →[search]→ IDispatchPort
spawn_via_fabric() →[create agent]→ IDispatchPort
execute_workflow() →[run DAG]→ IDispatchPort
```

### 3.11 Memory Tools → IMemoryPort

```
recall_memory() (Front) → IMemoryPort → BRIDGE_CLIENT
recall_memory() (Back) → IMemoryPort → BRIDGE_CLIENT
```

### 3.12 Streaming Flow

```
ILLMPort →[stream_execute]→ StreamConsumer → ChunkRouter
ChunkRouter →[text]→ TextChunkAggregator → SSEEmitter → OutputQueue
ChunkRouter →[tool_call_delta]→ ToolCallStreamHandler → SSEEmitter
ChunkRouter →[thinking]→ ThinkingTraceHandler → SSEEmitter
StreamConsumer → PartialResponseBuffer
INTERRUPT_HANDLING →[cancel mid-stream]→ StreamCancellationGuard → StreamConsumer
```

### 3.13 Tier Routing (LOW/MED/HIGH)

```
LOW: DISPATCHING →[LLM tool loop]→ ILLMPort →[tool_call: invoke_capability]→ ToolDispatcher → IDispatchPort
MED/HIGH: DISPATCHING →[TaskEnvelope]→ IDispatchPort →[dispatch_envelope]→ OrchestratorActor
  OrchestratorActor →[task.accepted]→ ConciergeController
  OrchestratorActor →[MED: direct]→ CAPABILITY_FABRIC
  OrchestratorActor →[HIGH: PlanRequest]→ PlannerAgent →[CommittedPlan]→ OrchestratorActor
  OrchestratorActor →[execute DAG]→ TopologicalWalker →[per step]→ CAPABILITY_FABRIC
```

### 3.14 HITL Flow

```
submit_result(needs_human) →[task.suspended]→ FRONT_HANDLER
Front translates → response.clarification → OUTPUT_CHANNEL
User responds → Front parses → task.resume → BACK_HANDLER resumes
L2_ENFORCER →[validate before invoke]→ invoke_capability
OPP4_AUTO →[auto-approve gate]→ L2_ENFORCER
```

### 3.15 Weave Protocol

```
task.complete →[if Front busy]→ WeaveBatcher →[emit]→ weave.batch.v1 →[FSM routes]→ FRONT_HANDLER
OPP1_STRATEGY →[pacing]→ WeaveBatcher
```

### 3.16 Experience Layer

```
ConciergeController →[tick_experience()]→ EXPERIENCE
EmotionalProcessor →[trajectory]→ IStatePort
ProactiveScheduler →[fill message]→ proactive.fill.v1
```

### 3.17 OPP Pipeline Wiring

```
Controller →[set_opp_pipeline()]→ OppPipeline
OppPipeline →[on_task_complete]→ OPP-8 DeliveryStrategyEngine
OppPipeline →[on_weave_flush]→ OPP-1 PacingPlan
OppPipeline →[on_hitl_outcome]→ OPP-4 TrustAccumulator
OppPipeline →[on_pre_prompt_build]→ OPP-6 EpisodicCompressor + OPP-7 DynamicIdentity
OppPipeline →[on_pre_llm_call]→ OPP-3 AffectHardCaps
OppPipeline →[on_idle_tick]→ OPP-5 ProactiveScheduler
```

### 3.18 Delta Aggregation (Sub-Agents → Concierge)

```
Dynamic Agents → IDeltaPort (state deltas)
PlannerAgent → IDeltaPort (planning deltas)
OrchestratorActor → IDeltaPort (orchestration deltas)
IDeltaPort → DeltaAggregator
```

### 3.19 Circuit Breaker Protection

```
CB_MODEL ← MODEL_HUB
CB_ORCHESTRATOR ← OrchestratorActor (OPEN: degrade tier)
CB_PLANNER ← PlannerAgent (OPEN: skip planning, degrade tier)
CB_FABRIC ← CAPABILITY_FABRIC
CB_MCP ← CAPABILITY_FABRIC
CB_SESSIONSTATE ← SESSION_STATE
CB_SSE ← BridgeSSE
```

### 3.20 Error Recovery Edges

```
UltraBERTv4Adapter →[RECOVERABLE: heuristic fallback]→ IClassificationPort
ModelGatewayAdapter →[DEGRADED: canned response]→ CANNED_RESPONSES
SessionKernelAdapter →[DEGRADED: stale cache]→ IStatePort
FabricOrchestratorAdapter →[DEGRADED: tier degrade]→ TIER_DEGRADE
```

### 3.21 Lifecycle Edges

```
turn_end() →[emit turn.complete.v1]→ turn_complete topic
turn_end() →[checkpoint K0]→ BRIDGE_CLIENT
```

### 3.22 Memory Writer + Learning

```
turn.complete.v1 →[subscribe]→ MW_CONSUMER →[memories]→ BRIDGE_CLIENT
turn.complete.v1 →[subscribe]→ LL_FEEDBACK →[FeedbackEnvelope]→ BRIDGE_CLIENT
```

### 3.23 Scratchpad → SS Extraction

```
ReactLoopScratchpad →[extract_scoreboard_deltas()]→ IStatePort
ReactLoopScratchpad →[extract_belief_deltas()]→ IStatePort
ReactLoopScratchpad →[extract_narrative_deltas()]→ IStatePort
```

### 3.24 SessionState Eviction

```
beliefs_active → beliefs_warm
history_active → history_warm
task_artifacts → artifacts_warm
narrative_active → narrative_warm
```

---

## 4. Port Definitions and Adapter Wiring (Complete)

### 4.1 Eight Hexagonal Ports (kernel.md §4.5)

| Port | Direction | Interface Methods | Key Contract |
|------|-----------|-------------------|--------------|
| `IInputPort` | Inbound | `receive() → UserMessage` | Single entry point for user input |
| `IOutputPort` | Outbound | `send(OutputEvent) → DeliveryReceipt` | All output through this port only |
| `IClassificationPort` | Outbound | `classify(text) → ClassificationResult` | Phase 1 pre-LLM processing |
| `ILLMPort` | Outbound | `execute(HubRequest) → HubResponse`, `stream_execute(HubRequest) → AsyncIterator[HubChunk]` | 5 capabilities: CHAT, TOOL_CALL, STRUCTURED, VISION, REASON |
| `IStatePort` | Both | `read(sections[]) → Snapshot`, `write(section, op, data) → WriteResult` | ADR-0017: Concierge is ONLY writer |
| `IDispatchPort` | Outbound | `dispatch_direct(CapReq) → CapResult`, `dispatch_envelope(TaskEnv) → void` | Routes LOW direct, MED/HIGH via envelope |
| `IDeltaPort` | Both | `subscribe(topics[]) → DeltaStream`, `publish(event) → void`, `errors() → ErrorStream` | Bus interaction layer |
| `IMemoryPort` | Outbound | `recall(query, selectors[]) → MemoryResult` | K0 long-term memory access |

### 4.2 Production Adapter Details

| Adapter | Port | Circuit Breaker | Error Strategy |
|---------|------|----------------|----------------|
| `WebSocketInputAdapter` / `RESTInputAdapter` | IInputPort | — | — |
| `SSEOutputAdapter` / `WebSocketOutputAdapter` | IOutputPort | CB_SSE | REALTIME: 3 retries 100ms; PROGRESS: 1 retry; BACKGROUND: 0 retries; CB OPEN: buffer 5 msgs |
| `UltraBERTv4Adapter` | IClassificationPort | CB_MODEL | CB OPEN: HEURISTIC_FALLBACK (<1ms) with 5 keyword rules |
| `ModelGatewayAdapter` | ILLMPort | CB_MODEL | L1: RETRY → L2: CB HALF-OPEN 30s → L3: CANNED_RESPONSE |
| `SessionKernelAdapter` | IStatePort | CB_SESSIONSTATE | MutationGuard rejection: RECOVERABLE; Read timeout: DEGRADED; Emergency: ≥95KB |
| `FabricOrchestratorAdapter` | IDispatchPort | CB_ORCH + CB_PLANNER + CB_FABRIC + CB_MCP | Step failure: 2 retries; TIER_DEGRADATION: HIGH→MED→LOW→canned |
| `DeltaBusAdapter` | IDeltaPort | — | Emit failure: log + skip (RECOVERABLE, never TERMINAL) |
| `BridgeRecallAdapter` | IMemoryPort | — | Recall timeout: skip memory (RECOVERABLE, never TERMINAL) |

### 4.3 UltraBERT Heuristic Fallback (CB OPEN, <1ms)

1. CRISIS keywords: hardcoded scan
2. Question + <20 words → conversational/LOW
3. remind/schedule/set → task/MED
4. plan/help me with → planning/HIGH
5. Default → conversational/LOW

---

## 5. Cross-Component Connections

### 5.1 Concierge → External Systems

| From (Concierge) | To (External) | Via Port | Protocol |
|-------------------|---------------|----------|----------|
| Front/Back tools | Capability Fabric | IDispatchPort | dispatch_direct / dispatch_envelope |
| Front/Back recall | K0 (Bridge) | IMemoryPort | recall() |
| Front/Back LLM calls | Model Hub | ILLMPort | execute() / stream_execute() |
| FSM turn_end | Memory Writer | IDeltaPort (turn.complete) | Event subscription |
| FSM turn_end | Learning Loop | IDeltaPort (turn.complete) | Event subscription |
| FSM turn_end | K0 checkpoint | Bridge Client | fire-and-forget |
| Proactive | Decision Engine + Curiosity | IDeltaPort / direct | OPP-5 scheduler |
| MED/HIGH dispatch | Orchestrator | IDispatchPort | TaskEnvelope |
| HIGH planning | Planner | Orchestrator → Planner | PlanRequest |

### 5.2 External Systems → Concierge

| From (External) | To (Concierge) | Via Port | Protocol |
|-----------------|----------------|----------|----------|
| Orchestrator | FSM | IDeltaPort | task.accepted, delta, dag.completed |
| Planner | FSM | IDeltaPort | planning deltas |
| Sub-Agents | FSM | IDeltaPort | state deltas |
| K0 SSE | Bridge SSE Receiver | IDeltaPort | SSE events |
| Curiosity Agent | FSM | direct | question |

---

## 6. Layer Architecture

### 6.1 Concierge Internal Layers

The diagram doesn't use explicit L1/L2/L3/L4 labels but organizes into these functional layers:

| Layer | Components | Function |
|-------|-----------|----------|
| **Input/Output Boundary** | 8 Ports + 16 Adapters | Hexagonal boundary with circuit breakers |
| **Phase 1 (Deterministic, 22ms)** | ACKING_CORE: UltraBERT v4 (12 heads), Safety Gate, Complexity Router, Hypothesis Pipeline, Temporal/Spatial Resolution, Context Inference, Uncertainty Routing, OPP-2, Write Elision Gate | Pre-LLM classification and routing |
| **Phase 2 (LLM-Driven)** | Front Actor (10 tools), Back Actor (7 tools), ReactLoopScratchpad, ReAct Recovery | Dual-LLM conversation + task execution |
| **State Layer** | SessionState (HOT 52KB + WARM 48KB), MutationGuard | Shared memory with single-writer invariant |
| **Protocol Layer** | HITL, Weave, Cancel, Suspend, OPP Pipeline | Cross-cutting coordination protocols |
| **Experience Layer** | 6 components (3 real + 3 stubs) | Emotional processing, rhythm, narrative |
| **Streaming Layer** | 8 components (~150 tests) | Real-time output streaming |
| **Service Layer** | 9 internal services (~585 tests) | FSMController, TurnProcessor, IntentProcessor, ComplexityRouter, ToolDispatcher, OutputManager, DeltaAggregator, ClarificationTracker, ContextAssembler |
| **Lifecycle Layer** | 6 phases | init, turn_start, turn_end, abbreviated, shutdown, crash_recovery |

### 6.2 LLM Cascade (ModelGateway)

```
L1: RETRY (timeout/5xx, retry once) = RECOVERABLE
L2: CB HALF-OPEN probe (30s window) = wait
L3: CANNED_RESPONSE (CB OPEN) = DEGRADED
```

### 6.3 Output Validation Pipeline (Model Hub)

```
T1: FORMAT (<1ms) → T2: SAFETY (<5ms) → T3: BELIEF (<50ms)
```

---

## 7. Invariant Annotations (21 Rules, 6 Categories)

### OWNERSHIP (INV-01..04)
- **INV-01:** Only Concierge writes SessionState
- **INV-02:** Every cognitive write → MutationGuard.preflight()
- **INV-03:** Phase 1 completes before Phase 2
- **INV-04:** Orchestrator/Planner/Agents NEVER write SS

### SAFETY (INV-05..07)
- **INV-05:** Safety Gate evaluates FIRST
- **INV-06:** CRISIS = immediate protocol, bypasses FSM
- **INV-07:** safety_band written BEFORE any routing

### RATE LIMITS (INV-08..12)
- **INV-08:** Tool calls/turn: 20
- **INV-09:** Clarification rounds/intent: 3
- **INV-10:** Output queue depth: 50
- **INV-11:** Workflow depth: 3
- **INV-12:** Concurrent active turns/session: 1

### TIMING (INV-13..14)
- **INV-13:** FSM transition ≤ 1ms (no I/O)
- **INV-14:** Delta aggregation = 500ms fixed

### STRUCTURAL (INV-15..17)
- **INV-15:** All output through OUTPUT_CHANNEL
- **INV-16:** Internal services call ports, never external systems directly
- **INV-17:** Single FSM — no secondary FSMs

### TOKEN BUDGET (INV-18..21)
- **INV-18:** LLM context window: 128K tokens
- **INV-19:** Intent ack: 150 tokens
- **INV-20:** Preliminary ack: 200 tokens
- **INV-21:** Clarification: 300 tokens

---

## 8. Event Flow Paths (Complete Traces)

### 8.1 Happy Path — LOW Tier

```
User → IInputPort → FSM(LISTENING→DISPATCHING)
  → IClassificationPort(UltraBERT 22ms) → WriteElisionGate → IStatePort
  → IDeltaPort(user.input.v1) → Bus → Front(subscribe)
  → Front: react_loop → ack() → recall_memory() → update_beliefs()
  → dispatch_task() → Bus(task.dispatch.v1) → FSM(DISPATCHING→COMPANIONING)
  → Back(subscribe) → react_loop → invoke_capability() → IDispatchPort → Fabric
  → submit_result(complete) → Bus(task.complete.v1)
  → FSM(COMPANIONING→DELIVERING) → Front(subscribe)
  → Front: react_loop(PRESENT mode) → response.final → Bus → OUTPUT_CHANNEL
  → FSM(DELIVERING→LISTENING)
```

### 8.2 MED/HIGH Tier

```
... same as above through dispatch_task() ...
  → IDispatchPort(dispatch_envelope) → Orchestrator → task.accepted.v1
  → FSM stays COMPANIONING
  → Orchestrator → Fabric (MED: 1-2 calls) or Planner → DAG → Fabric (HIGH)
  → dag.completed.v1 → FSM(COMPANIONING→DELIVERING) → Front(PRESENT mode)
```

### 8.3 HITL Flow

```
... Back working, needs user input ...
  → submit_result(needs_human, hil_type=clarification) → task.suspended.v1
  → FSM(COMPANIONING→CLARIFYING_WORKER) → Front(subscribe, HITL_RELAY mode)
  → Front translates to natural language → response.clarification → OUTPUT_CHANNEL
  → User responds → user.input.v1 → Front(HITL_RESOLVE mode) → parses answer
  → task.resume.v1 → Back(resume from ReAct history) → continues execution
```

### 8.4 Interrupt Flow

```
... Front idle in COMPANIONING, Back working ...
  → New user.input → FSM(COMPANIONING→INTERRUPT_HANDLING)
  → turn_end_abbreviated() → re-classify → FSM(INTERRUPT→DISPATCHING)
```

### 8.5 Weave Flow

```
... task.complete arrives while Front busy (COMPANIONING) ...
  → Guard: QUEUE → WeaveBatcher(500ms window, reset on new)
  → Batch ready → emit weave.batch.v1 → FSM(DELIVERING→WEAVING)
  → Front(WEAVE mode) → response with woven async results
  → FSM(WEAVING→LISTENING) when queue drained
```

### 8.6 Proactive Flow

```
... LISTENING, task.complete arrives (idle) ...
  → FSM(LISTENING→PROACTIVE_WAKE)
  → ProactiveScheduler(OPP-5, idle 5000ms, cooldown 15000ms)
  → Front generates fill message → proactive.fill.v1 → OUTPUT_CHANNEL
```

### 8.7 Crisis Flow

```
User → IInputPort → UltraBERT → Safety Head → CRISIS band
  → Crisis Detector → Safety Override → BYPASSES FSM
  → CRISIS_STATIC (hardcoded string, zero deps) → IOutputPort → OUTPUT_CHANNEL
```

### 8.8 Cancellation Flow

```
... COMPANIONING, user cancels ...
  → FSM(COMPANIONING→CANCELLING)
  → CancellationHandler: cooperative tokens, dedup
  → task.cancel.v1 → Back(subscribe) → cancellation_requested flag
  → react_loop checks flag between iterations → abort
```

### 8.9 Causal Chain (parent_id Enforcement)

```
user.input (#1, parent=0)
  +-- ack (#2, parent=1)
  +-- task.dispatch (#3, parent=1)
        +-- tool.started (#4, parent=3)
        +-- tool.completed (#5, parent=4)
        +-- task.complete (#6, parent=3)
              +-- response.final (#7, parent=6)
```

---

## 9. Actor Model Relationships

### 9.1 Two Actors (Neither Knows the Other Exists)

| Actor | Role | Tools | Termination | ReAct Iterations |
|-------|------|-------|-------------|-----------------|
| **Front LLM** (Voice) | Warm, empathetic, family-aware. TALKS to user. | Signal(1) + Cognitive(6) + Read(2) + Control(1) = **10** | Text response with NO tool calls | Mode + affect driven |
| **Back LLM** (Worker) | Precise, tool-focused, no personality. EXECUTES tasks. | Read(2) + Action(4) + Control(1) = **7** | submit_result() tool call ONLY | LOW:4, MED:8, HIGH:12 |

### 9.2 Communication Channel

- **Shared Memory:** SessionState (Front writes cognitive, FSM writes task/system, Back NEVER writes SS directly)
- **Event Bus:** K1 Bus with TimingChain (causal ordering) + MailboxRouter (actor-to-actor, WFQ priority)
- **Invariant:** Back emits deltas → bus → DeltaAggregator → FSM applies to SS

### 9.3 Shared react_loop() Implementation

Both actors use the same `react_loop()` function with actor-specific configuration:
- **Front rhythm:** 1.ack → 2.recall → 3.beliefs → 4.dispatch → 5.text
- **Back protocol:** ORIENT → CHECK → ASSESS → DISCOVER → SAFETY → INVOKE → EVALUATE → SUBMIT
- **Recovery patterns (5):** DEGENERATE, MALFORMED, PSEUDO-CODE, TEXT-AFTER-TOOLS, LAST-ITERATION

### 9.4 External Actors

| Actor | Role | Communication |
|-------|------|---------------|
| **OrchestratorActor** | Blind DAG executor, NO LLM, NO tools | Receives TaskEnvelope, emits accepted/delta/dag.completed |
| **PlannerAgent** | LLM-powered 4-stage pipeline | Receives PlanRequest, emits CommittedPlan |
| **Dynamic Agents** | Ephemeral specialists (health, finance) | Spawned via Fabric, state deltas via bus, NEVER write SS |
| **Safety Agent** | CRISIS protocol handler | Direct emergency path |
| **Memory Writer** | 0-3 factual memories/turn | Subscribes to turn.complete.v1 |
| **Learning Loop** | 5 feedback detectors | Subscribes to turn.complete.v1 |
| **Curiosity Agent** | Gap questions from K0 | Direct to FSM |
| **Proactive Decision Engine** | LLM-based idle detection | Budget gate (3/day) |

---

## 10. POC Diagram vs. Unified Diagram — Key Differences

### 10.1 Structural Differences

| Aspect | POC (`concierge_poc_architecture.mmd`) | Unified (`concierge_unified.mmd`) |
|--------|---------------------------------------|-----------------------------------|
| **Diagram type** | `graph TB` | `flowchart TB` with `elk` layout |
| **Line count** | 1086 lines | 1334 lines |
| **Created** | 2026-02-19 | 2026-04-01 (merged) |
| **Boundary model** | No explicit Concierge boundary subgraph | `CONCIERGE` + `TOUCHPOINTS` boundary separation |
| **Port/Adapter layer** | Not present — no hexagonal architecture | Full 8-port hexagonal with 16 adapters |
| **Back tools** | 6 tools (Action: 3) | 7 tools (Action: 4 — adds `batch_invoke_capabilities()`) |
| **OPP primitives** | 7 (OPP-1 through OPP-7) | 8 (adds OPP-8: Natural Flow Delivery) |
| **Experience Layer** | "6 Components, All Stubs" | "6 Components, 3 Real + 3 Stubs" |
| **Internal Services** | Not shown as separate section | 9 codeable components (~585 tests) |
| **Streaming** | Not present | 8 streaming components (~150 tests) |
| **Protocols** | Partial (HITL, Weave, OPP inline) | Consolidated "📋 Protocols (19 Files, All Real)" |
| **Lifecycle** | Not present | 6 lifecycle phases (init → crash_recovery) |
| **Invariants** | Not enumerated | 21 rules, 6 categories |
| **Performance** | Not present | Performance baselines section |
| **Error Recovery** | Not present as section | 3-severity error recovery model |
| **Scratchpad** | Not present | ReactLoopScratchpad (ADR-0098) |
| **Write Elision Gate** | Not present | Full signal-significance scoring gate |

### 10.2 FSM Differences

| Aspect | POC | Unified |
|--------|-----|---------|
| **FSM states** | Lists LISTENING, ACKING, DISPATCHING, COMPANIONING, DELIVERING + interrupts (12 total in header) | 11 coded + 1 proposed (BACKGROUND_WORKING). Removes ACKING as separate state — merged into DISPATCHING |
| **ACKING state** | Listed as separate FSM state | Absorbed into DISPATCHING phase (Phase 1 is sub-step) |
| **Proposed states** | None | BACKGROUND_WORKING (needs ADR-0097) |

### 10.3 Topic / Event Differences

| Aspect | POC | Unified |
|--------|-----|---------|
| **Topics** | Same core set | Adds `turn.complete.v1 (BACKGROUND)` — triggers Memory Writer + Learning Loop |
| **Orchestration events** | Same | Unified adds clearer priority annotations |

### 10.4 LLM Adapter Differences

| Aspect | POC | Unified |
|--------|-----|---------|
| **Port name** | `IConciergeModelPort` | Wraps `ILLMPort` (hexagonal port) via `IConciergeModelPort` internal |
| **Provider** | `GeminiConciergeAdapter` (sole provider) | Capability-driven routing via `ModelGatewayAdapter` → Model Hub |
| **Model selection** | Direct table in adapter | Same table, but via Model Hub capability tags |

### 10.5 POC-Only Elements (Not in Unified)

| Element | Notes |
|---------|-------|
| `determine_mode()` Logic subgraph | Explicit FSM-state→mode and topic→mode mapping. Unified omits this subgraph but the logic is implied by PromptModes. |
| Clarification Depth Tracking subgraph | Depth 0/1/2 progressive disclosure. Unified mentions ClarificationTracker service but omits the visual depth subgraph. |
| Task Model subgraph (explicit) | TaskDispatch + TaskIntent + 4 Task Patterns. Unified has TIERS subgraph that covers routing but lacks the explicit task patterns visual. |
| Output Channel & Streaming subgraph (POC) | Simpler streaming + delivery modes section. Unified has full 8-component streaming infra instead. |

### 10.6 Unified-Only Elements (Not in POC)

| Element | Significance |
|---------|-------------|
| Hexagonal Port/Adapter architecture | Complete boundary with 16 adapters, circuit breaker placement |
| ReactLoopScratchpad (ADR-0098) | Ephemeral per-dispatch working memory |
| Write Elision Gate | Signal-significance scoring for Phase 1 writes |
| 9 Internal Services with test counts | ~585 tests codified |
| 8 Streaming Infrastructure components | ~150 tests |
| 6-Phase Lifecycle | Full session + turn lifecycle including crash_recovery |
| 21 Invariants | Formalized non-negotiable rules |
| Performance Baselines | System P99 targets and budget envelopes |
| Error Recovery (3 Severities) | RECOVERABLE / DEGRADED / TERMINAL |
| External Touchpoints (formalized) | Orchestrator, Planner, Fabric, Model Hub, Bridge, Proactive, Memory Writer, Learning Loop, Sub-Agents, Circuit Breakers |

---

## 11. OPP Kernel Primitives (8 Total)

| OPP | Name | Hook | Key Parameters |
|-----|------|------|----------------|
| OPP-1 | Paced Delivery | `on_weave_flush` | Strategy: NONE/STAGGER/GROUP_BY_DOMAIN/PRIORITY_CASCADE |
| OPP-2 | Recency Bias Decay | `on_classify` | decay_per_turn=0.15, short_input<3 words = 50% penalty |
| OPP-3 | Affect Hard Caps | `on_pre_llm_call` | Per-band: CRISIS=512tok, LOW=1024, NEUTRAL=uncapped, POSITIVE=2048, ELEVATED=1536 |
| OPP-4 | Trust Accumulator | `on_hitl_outcome` + `on_pre_invoke` | initial=0.5, auto-approve ≥0.85 AND risk≤0.5 |
| OPP-5 | Proactive Scheduler | `on_idle_tick` | idle=5000ms, cooldown=15000ms, max=10/session |
| OPP-6 | Episodic Compression | `on_pre_prompt_build` | recent_window=10, episode_size=5, min_turns=15 |
| OPP-7 | Dynamic Identity | `on_pre_prompt_build` | Roles: EXPERT/PEER/GUIDE/SUPPORTER/EXECUTOR |
| OPP-8 | Natural Flow Delivery | `on_task_complete` + `on_natural_pause` | 13-rule table (D1-D13), 5 modes: DIRECT/WEAVE/INJECT/NOTIFY/DEFER |

---

## 12. Prompt Mode Architecture (10 Modes)

| Mode | Tools | Tokens | Trigger |
|------|-------|--------|---------|
| STANDARD | 10 | ~5500 | Default, full cognitive processing |
| CLARIFY_ASK | 3 | ~2200 | Front detected ambiguity |
| CLARIFY_RESOLVE | 7 | ~3800 | Resolve + possible dispatch |
| HITL_RELAY | 0 | ~1200 | Pure text translation |
| HITL_RESOLVE | 2 | ~2000 | Parse answer, confirm |
| PRESENT | 2 | ~3000 | Deliver task results |
| WEAVE | 2 | ~3200 | Bridge async results |
| CANCEL | 3 | ~2000 | Confirm cancellation |
| INTERRUPT | 10 | ~5500 | Full processing (new input during COMPANIONING) |
| ERROR | 1 | ~1800 | Graceful explanation |

**Composable Prompt Sections (10):** IDENTITY (~150), REACT_RHYTHM (~200), STATE_INTERP (~200), COGNITIVE_DISCIPLINE (~150), DISPATCH_RULES (~350), EMOTIONAL_CALIB (~100), SAFETY_HITL (~300), WEAVE_PROTOCOL (~100), ANTI_PATTERNS (~150), MODE_EXAMPLES (~200/mode)

---

## 13. Circuit Breakers (7)

| CB | Target | Parameters | Fallback |
|----|--------|-----------|----------|
| CB_MODEL | UltraBERT + ModelGateway | — | Heuristic fallback / Canned response |
| CB_ORCHESTRATOR | OrchestratorActor | 60s, 2/min | Degrade to LOW |
| CB_PLANNER | PlannerAgent | 45s, 2/min | Skip planning |
| CB_FABRIC | CapabilityFabric | 30s, 5/min | Unavailable (Concierge owns) |
| CB_MCP | CapabilityFabric tools | 10s, 3/min | Tool offline |
| CB_SESSIONSTATE | SessionState | 100ms, 10/min | Stale read |
| CB_SSE | Bridge SSE | 5s reconnect, 3/min | Polling mode |

---

## 14. Performance Baselines

**System-Owned P99:**
- UltraBERT: 25ms
- Intent ack SSE: 50ms
- FSM transition: 1ms
- MutationGuard: 0.2ms
- Phase 1 write: 0.02ms
- Phase 2 write: 0.1ms
- Output → SSE: 5ms
- Orchestration dispatch: 2ms
- **Total overhead/turn: ~32ms** (excluding LLM)

**Budget Envelopes:**
- LOW: 2s, MED: 10s, HIGH: 45s, CRISIS: 5s
- Single LLM timeout: 30s
- Planner stage: 10s/stage

---

## 15. SessionState Architecture

### HOT Tier (52KB, 10 sections)

| Section | Size | Writer | Eviction |
|---------|------|--------|----------|
| beliefs_active | 8KB | Front LLM | Evict low-confidence to WARM after 20 turns |
| scoreboard | 6KB | Phase1 + Front | Rewritten per turn |
| affective_now | 4KB | Phase1 + Front + EP | Later write wins |
| clarifications | 4KB | Front LLM | Clear resolved after 5 turns |
| narrative_active | 4KB | Front LLM | Summarize after 50 turns |
| control | 8KB | FSM + Phase1 | FlowState, TurnLock, IntentClass, DomainCtx, SafetyCtx, lock_version, turn_sequence_number |
| history_active | 8KB | FSM | 9 entry types, sliding window 20 entries |
| meta | 2KB | FSM | Turn count, latency, telemetry |
| task_state | 4KB | FSM (via DeltaAggregator) | Per-task status tracking |
| task_artifacts | 4KB | FSM (via DeltaAggregator) | Evict to WARM after 10 turns |

### WARM Tier (48KB, 4 sections)

beliefs_warm, history_warm, artifacts_warm, narrative_warm

### Static Section

persona (immutable) — Tone, personality, family members, preferences

### MutationGuard (3-Tier Validation)

1. Section capacity
2. HOT/WARM budget
3. Overall limit
4. Emergency: >95% → ALL writes rejected

---

## 16. Complexity Tiers

| Tier | Latency | Path | Tool Budget | Token Budget |
|------|---------|------|-------------|-------------|
| LOW | <2s | Front → dispatch → Back → invoke_capability → submit | 4 calls | 500 tokens |
| MEDIUM | 2-10s | Front → dispatch → OrchestratorStub (1-2 Fabric calls) | 8 calls | 2K tokens |
| HIGH | 10-45s | Front → TaskEnvelope → Orchestrator → Planner 4-stage → DAG | 12 calls | 8K tokens |
| CRISIS | <5s | Safety Override → hardcoded string, zero deps | 0 | 0 |

**Tier Degradation Cascade:**
```
HIGH (CB_PLANNER open) → MEDIUM
MEDIUM (CB_ORCH open) → LOW
LOW (CB_FABRIC open) → canned response
```

**OrchestratorStub invariants:** ORCH-01 (no SS write), ORCH-02 (no LLM), ORCH-03 (no tools), ORCH-04 (every step via Fabric), ORCH-10 (max 2 calls)

---

## 17. Safety Band Enforcement

| Band | Action | Examples | Enforcement |
|------|--------|---------|-------------|
| GREEN | Auto-proceed | Search, lookup, recall, weather | side_effects=true → auto-escalate to AMBER |
| AMBER | Confirm first | Book, purchase, send, create event | Back STEP 5 check + FSM L2 enforce |
| RED | Refuse + explain | Delete account, share medical, override parental | Never execute |

---

## 18. Lifecycle (6 Phases)

| Phase | Key Steps |
|-------|-----------|
| **init(session_id)** | Create 9 services, connect 8 ports, restore state (LOCAL COLD first), load persona, init 7 CBs → CLOSED, start subscriptions + DeltaAggregator, FSM → LISTENING |
| **turn_start(message)** | Acquire Single Writer lock (lock_version++), increment turn_sequence_number, read HOT snapshot, reset ToolDispatcher/ClarificationTracker/ContextAssembler, allocate budget |
| **turn_end()** | Flush OutputManager, append history, update telemetry, release lock, checkpoint LOCAL COLD (<1ms), checkpoint K0 (fire-and-forget), check experience triggers, emit turn.complete.v1 |
| **turn_end_abbreviated()** | Cancel in-flight, flush partial, record INTERRUPTED, release lock, checkpoint LOCAL COLD. SKIP: history, telemetry, K0, experience |
| **shutdown()** | Close IInputPort, wait active turn 30s, flush aggregator + output, final checkpoint (LOCAL COLD + K0 5s wait), stop background, disconnect ports LIFO |
| **crash_recovery(session_id)** | Bootstrap, detect turn_lock, rollback, reconcile Local Outbox, restore from LOCAL COLD, resume LISTENING. Max loss: 1 turn |

---

## 19. Style Classes Defined

The unified diagram defines **70+ CSS classes** for visual differentiation. Key categories:
- **Ports:** blue (#4A90D9)
- **Adapters:** purple (#7B68EE), test adapters dashed
- **FSM:** green states (#4ECDC4), yellow interrupts (#FFD93D), red brain (#FF6B6B)
- **Front Actor:** blue (#3498DB)
- **Back Actor:** orange (#E67E22)
- **Tools:** signal=red, cognitive=green, read=blue, action=orange, control=purple
- **Bus:** purple (#9B59B6)
- **SessionState:** cognitive=blue, system=green, task=orange, static=gray, warm=beige
- **Safety:** green/amber/red bands
- **OPP:** purple (#AF7AC5)
- **Experience:** yellow (#F9E79F), stubs dashed

---

## 20. Key Architectural Annotations from Header Comments

### Unified Diagram Header (Lines 1-73)

These are **not visible in the rendered diagram** but serve as documentation:

- **Core Design Principles:** Two Minds, Hexagonal (8 Ports), Single Writer (ADR-0017)
- **Actor Model:** Front 10 tools, Back 7 tools, shared react_loop()
- **FSM States:** 11 coded + 1 proposed (BACKGROUND_WORKING, ADR-0097)
- **Prompt Modes:** 10 named modes
- **SessionState:** HOT 52KB (10 sections) + WARM 48KB (4 sections)
- **Complexity Tiers:** LOW/MEDIUM/HIGH with latency bounds
- **OPP Primitives:** 8 (OPP-1 through OPP-8) with descriptions
- **Causal Ordering:** TimingChain, STRICT topics
- **HITL Protocol:** 3 variants, max 2 suspensions, timeout values
- **Experience Layer:** 6 components (3 real + 3 stubs)
- **Invariants:** 21 rules, 6 categories
- **Circuit Breakers:** 7 named
- **Performance:** ~32ms/turn overhead
- **Lifecycle:** 6 phases
- **Internal Services:** 9 components (~585 tests)
- **Streaming:** 8 components (~150 tests)
