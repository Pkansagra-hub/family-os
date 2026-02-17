# Concierge Production Implementation Plan V2

**Document Type**: Full Production Build Plan
**Version**: 2.2
**Updated**: 2026-02-17
**Created**: 2025-01-24
**Target**: K1 Concierge Module - Complete Implementation (Full System)
**Sources**:

- `k1/concierge/concierge.md` (11,993 lines, 36 sections)
- `k1/concierge/concierge_fsm_flows.md` (2,508 lines, 32 flows)
- `k1/concierge/concierge.mmd` (1,272 lines)
- `k1/concierge/README.md` (11 meta-intents, ConciergeAgent)
- `k1/concierge/tools/README.md` (ToolRegistry spec)
**Approach**: Full system implementation - no MVP/sprint divisions

---

## Executive Summary

The Concierge is Layer 1 (L1) of K1 - the **primary user-facing intelligence** that governs ALL conversation flow. It serves as the "brain" that mediates between users and the entire K1 subsystem (Orchestrator, Planner, Fabric, agents).

**Core Architecture Insight**: The FSM provides **rails** (8 states, 14 transitions, guards, budgets), while the **LLM drives** the conversation within those rails. The 32 documented flows are emergent behaviors, not hardcoded paths.

**Hard Constraints:**

- Single Writer Pattern (ADR-0017g): Only Concierge writes to SessionState
- 22 Hard Invariants (CONC-01 through CONC-22) - zero violations
- 96KB SessionState budget (48KB HOT + 48KB WARM)
- ~1110 tests required for production quality (including performance/chaos/invariant tests)
- Edge-First architecture (K0 is optional, LOCAL COLD always works)
- LLM Minimum: Frontier-class model with native function calling, 128K context, >90% instruction compliance (Section 6.11)

**Future Phase (NOT V1 Scope):**

- **FG/BG Turn Split** (Section 23.2.1): Marked as "Design Proposal - needs ADR-0097". Will be implemented after V1 stabilizes.
- **Advanced Adaptive Scheduling**: Dynamic tier adjustment based on system load patterns.

---

## Part 1: Complete Component Inventory

### 1.1 Core Services (11 Services)

| Service | Primary Responsibility | Test Target | Source Section |
|---------|----------------------|-------------|----------------|
| **FSMController** | 8-state machine, 14 transitions, 4 experience triggers | ~60 | Section 17 |
| **TurnProcessor** | Turn lifecycle, Phase 1+2 coordination, lock management | ~90 | Section 5 |
| **IntentProcessor** | SafetyGate, hypothesis, gap detection, Phase 1 pipeline | ~110 | Section 12 |
| **ComplexityRouter** | 5-factor tier scoring (LOW/MED/HIGH) | ~45 | Section 7 |
| **ToolDispatcher** | ReAct loop, 13 tools, allowlist, budget enforcement | ~80 | Section 10 |
| **OutputManager** | 9 event types, 3 priorities, queue management | ~55 | Section 16 |
| **DeltaAggregator** | 500ms batching, LWW merge, delta emission | ~50 | Section 25 |
| **ClarificationTracker** | Max 3 rounds, HIL tracking, PENDING_CLARIFICATIONS | ~40 | Section 8 |
| **ContextAssembler** | Token budget management, 6 context profiles | ~55 | Section 13 |
| **ProactiveAgent** | K0 gap injection, warmth messages, attention budget | ~40 | Section 36 |
| **FeedbackProcessor** | 5 detectors, aggregation, K0 bridge | ~45 | Section 36 |

### 1.2 LLM Infrastructure (7 Components - Section 6)

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **DynamicPromptBuilder** | 9-section system prompt assembly per turn | ~30 |
| **ToolBundleValidator** | ACK-first, pairing rules, budget enforcement | ~35 |
| **ReActLoopController** | MAX_TOOL_ITERATIONS=10, iteration management, scratchpad lifecycle | ~25 |
| **ReactLoopScratchpad** | Ephemeral working memory per ReAct loop (ADR-0098) — structured tool/agent results, budget tracking, cognitive write audit, iteration snapshots | ~30 |
| **LLMCapabilityRouter** | Route to CHAT/TOOL_CALL/STRUCTURED/VISION/REASON models | ~20 |
| **ToolResultInjector** | Feed tool results back to LLM context | ~15 |
| **SelfCorrectionTracker** | Track validation failures, enforce recovery budget | ~15 |

### 1.3 Tools Infrastructure (5 Components - tools/README.md)

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **ToolRegistry** | Centralized tool registry, O(1) lookup by tool_id | ~25 |
| **CapabilityMatcher** | Agent capability to tool requirement matching | ~20 |
| **SchemaValidator** | JSON schema validation for tool inputs/outputs | ~25 |
| **ToolCallOrchestrator** | Batch tool calls, ADR-0078 tiered parallelism (Phase A: ack seq, Phase B: reads+actions parallel, Phase C: cognitive seq) | ~25 |
| **PromptMatcher** | Match planning descriptions to prompt templates | ~15 |

### 1.4 Resolution Engines (4 Components - Section 11)

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **TemporalResolutionEngine** | NER temporal entities -> absolute times (DATE_ABS, DATE_REL, TIME, DURATION, FREQUENCY, AGE) | ~25 |
| **SpatialResolutionEngine** | GPS/BLE/Wi-Fi -> semantic place (Place, room, motion classification) | ~20 |
| **PersonaEngine** | Persona hints, communication style adaptation | ~15 |
| **ReferenceResolver** | Pronoun/reference resolution against scoreboard.referents and beliefs_active | ~20 |

### 1.5 Meta-Intent System (3 Components - README.md)

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **MetaIntentClassifier** | Classify 11 meta-intents (specialized layer above UltraBERT) | ~25 |
| **RoutingDecisionEngine** | Route to orchestrator vs direct handling | ~20 |
| **MetaIntentHandler** | Handle each of 11 meta-intent patterns | ~30 |

**11 Meta-Intents:**

1. ACKNOWLEDGMENT - Simple acknowledgment
2. STATUS_CHECK - "What's happening with X?"
3. CANCELLATION - "Cancel that"
4. RETRY - "Try again"
5. CORRECTION - "No, I meant X"
6. RAPID_BATCH - Multiple quick requests
7. AMENDMENT - "Also, add X"
8. REFINEMENT - "Make it more specific"
9. TOPIC_CHANGE - Abrupt topic switch
10. AMBIGUOUS_QUERY - Unclear input
11. SMALL_TALK - Social chat

### 1.6 K0 Active Learning System (Section 36)

#### 1.5.1 System 1: Gap Resolution (Proactive)

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **CuriosityIntentProcessor** | Process K0 curiosity intents | ~20 |
| **ProactiveDecisionEngine** | Decide whether to ask proactive questions | ~25 |
| **AttentionBudgetGate** | Enforce max 1 proactive question per turn | ~15 |
| **GapPrioritizer** | Rank 10 gap types by urgency | ~20 |
| **WarmthMessageGenerator** | Generate warmth messages when no K0 gaps | ~15 |
| **ProactiveQuestionPhraser** | Transform gap blueprints to natural conversation | ~20 |

**10 GAP_TYPES:**

1. STALE_ANCHOR - Entity info outdated
2. MISSING_CLOSURE - No outcome recorded
3. UNRESOLVED_PRONOUN - Pronoun without referent
4. TEMPORAL_DRIFT - Time-sensitive info stale
5. RELATIONSHIP_GAP - Missing connection info
6. PREFERENCE_UNKNOWN - Unknown user preference
7. ROUTINE_UNCERTAINTY - Unclear routine pattern
8. LOCATION_UNKNOWN - Unknown location context
9. MOOD_INFERENCE - Uncertain emotional state
10. GOAL_AMBIGUITY - Unclear user objective

#### 1.5.2 System 2: Model Refinement (Feedback Loop)

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **CorrectionDetector** | Detect explicit user corrections | ~15 |
| **ConfirmationDetector** | Detect confirmations and affirmations | ~15 |
| **AbandonmentDetector** | Detect topic abandonment | ~15 |
| **ModificationDetector** | Detect mid-task modifications | ~15 |
| **SatisfactionDetector** | Detect satisfaction signals | ~15 |
| **FeedbackRouter** | Route detected signals to appropriate handlers | ~20 |
| **FeedbackAggregator** | Aggregate feedback signals | ~15 |
| **BatchWindowManager** | Manage 500ms feedback batching | ~10 |
| **HorizontalFeedbackBridge** | Emit feedback to K0 for model refinement | ~15 |

### 1.7 Interrupt & Recovery System (Sections 18, 23)

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **InterruptDetector** | Detect buffered messages during turn | ~20 |
| **InterruptHandler** | Handle interrupts by state (interruptible vs not) | ~25 |
| **PartialResultPreserver** | Preserve partial results from PROGRESSING state | ~15 |
| **CheckpointManager** | LOCAL COLD checkpoint at every turn_end() | ~20 |
| **RecoveryService** | Restore from checkpoint on crash | ~20 |
| **OutboxDrainer** | Drain outbox on recovery | ~10 |
| **RetryManager** | Coordinate retry logic per CB, track retry counts/backoff | ~20 |
| **DegradationOrchestrator** | Coordinate tier degradation (HIGH->MED->LOW) on CB trips | ~20 |

### 1.8 HIL (Human-in-the-Loop) Components (Sections 19-20, 26.2-26.3, 27)

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **HILCoordinator** | Central coordinator for all HIL flows (Planner/Orchestrator/sub-agents) | ~25 |
| **HILRequestFormatter** | Format machine HIL requests as natural conversation | ~15 |
| **HILResponseParser** | Parse user responses to HIL requests | ~15 |
| **HILTimeoutManager** | Track 120s HIL timeout (CONC-15), escalation policy | ~15 |
| **PendingHILTracker** | Track pending HIL requests keyed by {request_id, originator, agent_id} | ~20 |
| **SubAgentHILBridge** | Route HIL events from sub-agents via K1 Bus delta lane | ~15 |
| **HILResponseDetector** | Detect if user message is response to pending HIL vs new intent | ~15 |

### 1.9 Streaming Infrastructure (Model Hub Integration)

**Integration Point**: Model Hub provides `stream_execute(HubRequest) -> AsyncIterator[HubChunk]`

The Concierge must consume Model Hub streams and deliver real-time UX. This is the **largest missing component**.

| Component | Responsibility | Test Target |
|-----------|---------------|-------------|
| **StreamConsumer** | Consume Model Hub `AsyncIterator[HubChunk]`, manage backpressure | ~25 |
| **ChunkRouter** | Route chunks by type: text, tool_call, thinking, error | ~20 |
| **TextChunkAggregator** | Aggregate text chunks, trigger SSE delivery at word boundaries | ~15 |
| **ToolCallStreamHandler** | Parse partial tool_call JSON, emit when complete | ~25 |
| **ThinkingTraceHandler** | Capture REASON capability thinking traces for display | ~15 |
| **StreamingSSEEmitter** | Emit `streaming_chunk` events to OutputManager | ~20 |
| **StreamCancellationGuard** | Handle user interrupts during streaming, cancel upstream | ~15 |
| **PartialResponseBuffer** | Buffer partial responses for FSM state transitions | ~15 |

**Streaming Event Types (via OutputManager):**

| Event Type | Priority | Use Case |
|------------|----------|----------|
| `streaming_chunk` | REALTIME | Incremental text tokens |
| `tool_call_start` | REALTIME | Tool call begins (show spinner) |
| `tool_call_progress` | REALTIME | Tool call parameters streaming |
| `tool_call_complete` | REALTIME | Tool call finished (show result) |
| `thinking_chunk` | INTERACTIVE | REASON capability thinking trace |
| `typing_indicator` | REALTIME | Before first chunk arrives |

**HubChunk Types (from Model Hub):**

```python
# k1/model_hub/types.py (Model Hub owns these)
@dataclass
class HubChunk:
    chunk_type: Literal["text", "tool_call", "tool_call_delta",
                         "thinking", "error", "usage", "done"]
    content: Optional[str]           # For text/thinking
    tool_call: Optional[ToolCallDelta]  # For tool_call_delta
    usage: Optional[UsageInfo]       # For usage chunks
    finish_reason: Optional[str]     # For done chunks
    trace_id: str
```

**Streaming Flow (ReAct Loop with Streaming):**

```
1. DynamicPromptBuilder assembles prompt
2. ILLMPort.stream_execute(HubRequest) called
3. StreamConsumer receives AsyncIterator[HubChunk]
4. For each chunk:
   - ChunkRouter routes by chunk_type
   - text -> TextChunkAggregator -> StreamingSSEEmitter -> OutputManager
   - tool_call_delta -> ToolCallStreamHandler (accumulate)
   - tool_call complete -> ToolDispatcher.execute_tool()
   - thinking -> ThinkingTraceHandler -> StreamingSSEEmitter
   - error -> ErrorRoutedEvent + fallback
   - done -> finalize response, release buffer
5. ToolResultInjector feeds tool results back
6. Loop continues until no more tool_calls
7. Final text content delivered
```

**Why This Matters:**

- **User sees response immediately** (not waiting 5-30s for full response)
- **Tool calls visible in real-time** ("Searching for restaurants...")
- **Thinking traces show reasoning** (for REASON capability)
- **Interrupts can cancel mid-stream** (StreamCancellationGuard)
- **Model Hub MH-10**: chunk validation happens here

### 1.10 FSM States (8 Core + 4 Experience)

**Core States:**

```
LISTENING -> ACKING -> CLARIFYING -> DISPATCHING -> COMPANIONING -> PROGRESSING -> DELIVERING -> INTERRUPT_HANDLING
```

**Interruptibility:**

| State | Interruptible | Rationale |
|-------|--------------|-----------|
| LISTENING | No | Atomic (waiting for input) |
| ACKING | No | Phase 1 (22ms) - safety classification must complete |
| CLARIFYING | Yes | Can abandon clarification |
| DISPATCHING | Yes | Can cancel dispatch |
| COMPANIONING | Yes | Can cancel in-flight work |
| PROGRESSING | Yes | Can preserve partial results |
| DELIVERING | No | Atomic (final response + cognitive writes) |
| INTERRUPT_HANDLING | No | Meta-state (handling interrupt) |

**Experience States (modular, tick-based):**

- NARRATIVE_WEAVING (turn % 20)
- EMOTIONAL_PROCESSING (turn % 25)
- ANTICIPATORY_RESPONSE (turn % 30)
- AFFECTIVE_MIRRORING (on-demand)

### 1.11 Hexagonal Ports (8 Protocols)

| Port | Direction | Purpose | Production Adapter | Test Adapter |
|------|-----------|---------|-------------------|--------------|
| `IInputPort` | Inbound | User message reception | WebSocketInputAdapter | TestInputAdapter |
| `IOutputPort` | Outbound | SSE response delivery | SSEOutputAdapter | TestOutputAdapter |
| `IClassificationPort` | Outbound | UltraBERT classification | UltraBERTAdapter | MockClassificationAdapter |
| `ILLMPort` | Outbound | LLM execution | ModelGatewayAdapter | MockLLMAdapter |
| `IStatePort` | Both | SessionState read/write | SessionKernelAdapter | InMemoryStateAdapter |
| `IDispatchPort` | Outbound | Orchestrator/Fabric dispatch | FabricOrchestratorAdapter | MockDispatchAdapter |
| `IDeltaPort` | Both | Delta stream pub/sub | DeltaBusAdapter | TestDeltaAdapter |
| `IMemoryPort` | Outbound | K0 memory queries | BridgeRecallAdapter | MockMemoryAdapter |

### 1.12 Circuit Breakers (7 CBs)

| CB Name | Target | Timeout | Failure Threshold | Recovery | Fallback |
|---------|--------|---------|-------------------|----------|----------|
| CB_CLASSIFICATION | UltraBERT | 40ms | 5 failures/60s | 30s half-open | 5-rule heuristic |
| CB_MODEL | LLM | 30s | 5 failures/60s | 30s half-open | 3-tier cascade -> templates |
| CB_SESSIONSTATE | SessionState | 100ms | 5 failures/60s | 30s half-open | Stale read, skip write |
| CB_ORCHESTRATOR | Orchestrator | 60s | 3 failures/60s | 30s half-open | Tier degradation to LOW |
| CB_PLANNER | Planner | 45s | 2 failures/min | 30s half-open | Skip planning, direct exec |
| CB_FABRIC | Fabric | 30s | 3 failures/60s | 30s half-open | Capability unavailable |
| CB_SSE | SSE delivery | 5s | 5 failures | 5s reconnect | Buffer 5 messages, flush |

### 1.13 LLM Tools (13 Tools)

**Signal Tools (1):**

| Tool | Purpose | SessionState Writes |
|------|---------|---------------------|
| `acknowledge()` | Immediate user acknowledgment | None (output only) |

**Cognitive Tools (6):**

| Tool | Purpose | SessionState Target |
|------|---------|---------------------|
| `update_scoreboard()` | QUD stack, referents, salience | `scoreboard` (HOT) |
| `update_beliefs()` | Turn-specific facts | `beliefs_active` (HOT) |
| `update_clarifications()` | Pending questions | `clarifications` (HOT) |
| `update_narrative()` | Thread tracking, arc | `narrative_active` (HOT) |
| `refine_affect()` | Emotional state refinement | `affective_now` (HOT) |
| `promote_belief()` | Long-term memory promotion | HOT + K0 via IMemoryPort |

**Read Tools (3):**

| Tool | Purpose | Data Source |
|------|---------|-------------|
| `recall_memory()` | K0 long-term recall | IMemoryPort |
| `discover_capabilities()` | Fabric registry search | IDispatchPort |
| `summarize_context()` | Context assembly | IStatePort (read-only) |

**Action Tools (3):**

| Tool | Purpose | Target |
|------|---------|--------|
| `invoke_capability()` | Execute single capability | IDispatchPort (Fabric) |
| `spawn_via_fabric()` | Create sub-agent | IDispatchPort (Fabric) |
| `execute_workflow()` | Run predefined workflow | IDispatchPort (Fabric) |

**Tool Allowlist by Tier:**

| Tier | Allowed Tools |
|------|---------------|
| LOW | acknowledge, update_scoreboard, update_beliefs, refine_affect, recall_memory, summarize_context, invoke_capability, discover_capabilities |
| MEDIUM | ALL LOW + update_clarifications, update_narrative, spawn_via_fabric |
| HIGH | ALL MEDIUM + execute_workflow, promote_belief |

### 1.14 UltraBERT v4 Engine

**Model Specification:**

- Base: ModernBERT-base
- Parameters: 149M
- Latency: 22ms P50, 25ms P99
- Precision: FP16 inference

**12 Classification Heads:**

| Head | Output | HOT Section Target |
|------|--------|-------------------|
| `safety_familyos` | SafetyBand (GREEN/AMBER/RED/CRISIS) | `control.safety_band` |
| `intent` | Intent class (37 categories) | `control.intents` |
| `ingress` | Domain tags (multi-label) | `control.domains` |
| `emotions` | Emotion detection | `affective_now.current_emotion` |
| `sentiment` | Valence score | `affective_now.valence` |
| `temporal` | Time span NER | `beliefs_active.mentioned_time` |
| `ner_general` | General entity NER | `beliefs_active.mentioned_entities` |
| `ner_family` | Family entity NER | `beliefs_active.mentioned_entities` |
| `complexity` | Complexity score (0-1) | ComplexityRouter input |
| `urgency` | Urgency level | Tier adjustment |
| `topic` | Topic classification | Context assembly |
| `style` | Communication style | Persona hints |

---

## Part 2: FSM Flow Implementation Guide (32 Flows)

The 32 documented flows in `concierge_fsm_flows.md` are **emergent behaviors** of the LLM operating within the rail system, not hardcoded paths. This section describes how each flow class is implemented.

### 2.1 Flow Classification

| Flow Class | Flows | Implementation Pattern |
|------------|-------|----------------------|
| **Normal Turns** | 1-3 | LLM drives ReAct loop with tier-appropriate tools |
| **Clarification** | 4-5 | FSM tracks CLARIFYING state, LLM asks naturally |
| **Interrupts** | 6-11, 28 | InterruptDetector + FSM transition to INTERRUPT_HANDLING |
| **Safety** | 12-14 | SafetyGate + tier override + tool restriction |
| **Timeout/Degradation** | 15-16, 24-27 | CBs + watchdog + tier cascade |
| **Batch** | 17-18 | ContextAssembler accumulates, LLM processes naturally |
| **HIL (Planner)** | 19-20 | HILRequestFormatter + CLARIFYING state |
| **Proactive** | 21-22 | ProactiveAgent during COMPANIONING idle |
| **Recovery** | 23 | CheckpointManager + RecoveryService |
| **HIL (Orchestrator)** | 30 | Same as Planner HIL, different source |
| **User Override** | 31 | InterruptHandler + partial cancellation |
| **Clarification Timeout** | 32 | ClarificationTracker + 5-minute timeout |

### 2.2 What Rails Enforce (Not LLM)

```
+--------------------------------------------------------------------+
|                      WHAT IS HARDCODED (Rails)                     |
+--------------------------------------------------------------------+
| - 8 FSM states and 14 valid transitions                           |
| - Phase 1 UltraBERT classification (22ms, deterministic)          |
| - Safety bands (GREEN/AMBER/RED/CRISIS)                           |
| - Tier routing (LOW/MEDIUM/HIGH complexity thresholds)            |
| - Tool budget limits per tier (6/12/20 calls)                     |
| - Clarification round limit (3 max, CONC-08)                      |
| - Watchdog timer (120s, CONC-15)                                  |
| - Circuit breaker thresholds and fallback chains                  |
| - CRISIS static response (zero dependencies)                      |
| - MutationGuard size limits (HOT 48KB, sections budgeted)         |
| - ACK-first tool bundle validation                                |
| - Interruptibility matrix (which states allow interrupt)          |
+--------------------------------------------------------------------+
```

### 2.3 What LLM Decides (Driver)

```
+--------------------------------------------------------------------+
|                      WHAT THE LLM DECIDES (Driver)                 |
+--------------------------------------------------------------------+
| - Whether to ask a clarifying question or proceed                 |
| - What to say in every response (tone, content, length)           |
| - Which tools to call and in what order                           |
| - Whether to acknowledge with "progress", "commit", or "closure"  |
| - What beliefs to write, update, or correct                       |
| - How to frame errors and partial results to the user             |
| - Whether to refine UltraBERT's emotion classification            |
| - When to shift narrative threads or push QUD                     |
| - How to phrase HIL approval requests from Planner naturally      |
| - How to handle user corrections (detect, apologize, fix)         |
| - What to do when a tool fails (retry differently, inform user)   |
| - Whether a user response is a clarification answer or interrupt  |
+--------------------------------------------------------------------+
```

---

## Part 3: Schema Definitions

### 3.1 Core Types (Concierge-Owned)

```python
# k1/concierge/types/messages.py
@dataclass(frozen=True)
class UserMessage:
    text: str
    session_id: str
    trace_id: str
    metadata: Dict[str, Any]
    timestamp_ms: int

@dataclass(frozen=True)
class OutputEvent:
    event_id: str
    event_type: Literal["acknowledge", "response", "clarification",
                         "progress", "completion", "error",
                         "streaming_chunk", "typing_indicator", "proactive"]
    content: str
    priority: Literal["REALTIME", "INTERACTIVE", "BACKGROUND"]
    trace_id: str
    timestamp_ms: int
    metadata: Optional[Dict[str, Any]] = None
```

### 3.2 Classification Types

```python
# k1/concierge/types/classification.py
@dataclass(frozen=True)
class ClassificationResult:
    safety_band: Literal["GREEN", "AMBER", "RED", "CRISIS"]
    intent: str
    intent_confidence: float
    domains: List[str]
    emotions: Dict[str, float]
    sentiment: float
    entities: List[EntitySpan]
    temporal_spans: List[TemporalSpan]
    complexity_score: float
    urgency_level: Literal["LOW", "NORMAL", "HIGH", "URGENT"]
    is_low_signal: bool
    raw_logits: Dict[str, List[float]]

@dataclass(frozen=True)
class Phase1Result:
    classification: ClassificationResult
    hypothesis: IntentHypothesis
    gaps: List[InformationGap]
    tier: Literal["LOW", "MEDIUM", "HIGH"]
    write_decisions: List[WriteDecision]
    meta_intent: Optional[MetaIntent]  # NEW: Meta-intent classification
    latency_ms: int

@dataclass(frozen=True)
class MetaIntent:
    meta_type: Literal["ACKNOWLEDGMENT", "STATUS_CHECK", "CANCELLATION",
                        "RETRY", "CORRECTION", "RAPID_BATCH", "AMENDMENT",
                        "REFINEMENT", "TOPIC_CHANGE", "AMBIGUOUS_QUERY", "SMALL_TALK"]
    confidence: float
    requires_orchestrator: bool
```

### 3.3 K0 Integration Types (Section 36)

```python
# k1/concierge/types/k0_integration.py
@dataclass(frozen=True)
class CuriosityIntent:
    gap_id: str
    gap_type: Literal["STALE_ANCHOR", "MISSING_CLOSURE", "UNRESOLVED_PRONOUN",
                       "TEMPORAL_DRIFT", "RELATIONSHIP_GAP", "PREFERENCE_UNKNOWN",
                       "ROUTINE_UNCERTAINTY", "LOCATION_UNKNOWN", "MOOD_INFERENCE",
                       "GOAL_AMBIGUITY"]
    subject: str
    attribute: str
    question_blueprint: str
    priority: int
    staleness_days: int
    source: Literal["k0.graph", "k0.temporal", "k0.relationship"]

@dataclass(frozen=True)
class FeedbackSignal:
    signal_type: Literal["CORRECTION", "CONFIRMATION", "ABANDONMENT",
                          "MODIFICATION", "SATISFACTION"]
    turn_id: str
    subject: Optional[str]
    attribute: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    confidence: float
    context: Dict[str, Any]

@dataclass(frozen=True)
class ProactiveDecision:
    should_ask: bool
    question: Optional[str]
    gap_id: Optional[str]
    fallback: Literal["warmth_message", "none"]
    attention_budget_remaining: int
```

### 3.4 Tool Registry Types (tools/README.md)

```python
# k1/concierge/tools/types.py
@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    returns_schema: Dict[str, Any]
    tier_allowlist: FrozenSet[Tier]
    category: Literal["signal", "cognitive", "read", "action"]
    requires_ack_first: bool

@dataclass(frozen=True)
class ToolBundle:
    calls: List[ToolCall]
    ack_present: bool
    total_count: int
    tier: Tier

@dataclass(frozen=True)
class ToolCall:
    call_id: str
    tool_id: str
    parameters: Dict[str, Any]
    sequence_number: int

@dataclass(frozen=True)
class BundleValidationResult:
    valid: bool
    errors: List[BundleError]
    warnings: List[str]
    ack_position_correct: bool
    budget_remaining: int
```

### 3.5 LLM Infrastructure Types (Section 6)

```python
# k1/concierge/llm/types.py
@dataclass(frozen=True)
class DynamicPrompt:
    identity: str
    session_context: str
    already_resolved: str
    classification: str
    plan_context: Optional[str]
    tools_available: List[ToolSpec]
    tool_calling_rules: str
    response_style: str
    constraints: str
    total_tokens: int

@dataclass(frozen=True)
class ReActIteration:
    iteration_number: int
    tool_calls: List[ToolCall]
    tool_results: List[ToolResult]
    validation_errors: List[str]
    final_content: Optional[str]

# NEW: ReactLoopScratchpad types (ADR-0098)
# Ephemeral working memory — created per ReAct loop, destroyed after.
# Replaces naive messages.append() with structured, budget-aware context.

@dataclass
class LoopBudget:
    """Tier-based budget limits for a single ReAct loop."""
    tier: Tier
    max_tools: int          # LOW=6, MED=10, HIGH=15
    timeout_ms: int         # LOW=2000, MED=10000, HIGH=45000
    max_tokens_out: int     # LOW=500, MED=2000, HIGH=8000
    tools_used: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_ms: int = 0
    exhausted: bool = field(init=False)  # computed property

@dataclass(frozen=True)
class ToolExecution:
    """Structured record of a single tool call + result pair."""
    call: ToolCall
    result: ToolResult
    duration_ms: int
    tokens_used: int
    iteration: int

@dataclass(frozen=True)
class AgentResult:
    """Structured record of a sub-agent or dynamic agent result."""
    agent_id: str
    agent_type: Literal["sub_agent", "dynamic"]
    snapshot_ref: Optional[str]
    findings: List[str]
    structured_output: Optional[Dict[str, Any]]
    confidence: float

@dataclass(frozen=True)
class CognitiveWrite:
    """Audit trail for a single cognitive tool write."""
    section: str            # e.g., "scoreboard", "beliefs_active"
    operation: str          # e.g., "upsert", "delete"
    key: str
    old_value: Optional[Any]
    new_value: Any
    iteration: int
    tool_call_id: str

@dataclass(frozen=True)
class IterationSnapshot:
    """Per-iteration record: thought, action, observation."""
    iteration: int
    thought: Optional[str]
    action: Optional[str]
    observation: Optional[str]
    tokens_used: int
    duration_ms: int
    success: bool
    error: Optional[str]

@dataclass
class ReactLoopScratchpad:
    """Ephemeral working memory for a single ReAct loop (ADR-0098).
    Created at dispatch start, destroyed at dispatch end.
    Never persisted. Never enters SessionState directly.
    Only final deltas extracted via extract_*_deltas() at turn_end()."""
    turn_id: str
    tier: Tier
    budget: LoopBudget
    iteration: int = 0
    final_content: Optional[str] = None
    _messages: List[Dict] = field(default_factory=list)
    tool_executions: List[ToolExecution] = field(default_factory=list)
    agent_results: List[AgentResult] = field(default_factory=list)
    cognitive_writes: List[CognitiveWrite] = field(default_factory=list)
    iteration_snapshots: List[IterationSnapshot] = field(default_factory=list)

    def to_llm_messages(self) -> List[Dict]: ...
    def compact_messages(self, keep_last_n: int = 3) -> None: ...
    def record_tool(self, call: ToolCall, result: ToolResult) -> None: ...
    def record_agent(self, result: AgentResult) -> None: ...
    def record_cognitive_write(self, write: CognitiveWrite) -> None: ...
    def snapshot_iteration(self, response: Any) -> None: ...
    def extract_scoreboard_deltas(self) -> Optional[Dict]: ...
    def extract_belief_deltas(self) -> Optional[Dict]: ...
    def extract_narrative_deltas(self) -> Optional[Dict]: ...
    def is_complete(self) -> bool: ...
    def elapsed_ms(self) -> int: ...

@dataclass(frozen=True)
class LLMCapability:
    capability: Literal["CHAT", "TOOL_CALL", "STRUCTURED", "VISION", "REASON"]
    model_id: str
    context_window: int
    supports_streaming: bool
```

---

## Part 4: Implementation Architecture

### 4.1 Directory Structure (UPDATED)

```
k1/concierge/
    __init__.py
    README.md
    concierge.md
    concierge.mmd
    concierge_fsm_flows.md

    core/
        __init__.py
        concierge.py                # Top-level class
        factory.py                  # ConciergeFactory
        fsm_controller.py           # FSMController
        turn_processor.py           # TurnProcessor
        states.py                   # FSMState enum
        transitions.py              # Transition table

    processing/
        __init__.py
        intent_processor.py         # IntentProcessor
        complexity_router.py        # ComplexityRouter
        hypothesis.py               # Hypothesis generation
        gap_detection.py            # Information gap detection
        write_elision.py            # Write Elision Gate
        safety_gate.py              # CRISIS detection

    engines/
        __init__.py
        ultrabert.py                # UltraBERT v4 inference
        temporal.py                 # TemporalResolutionEngine (Section 11.4)
        spatial.py                  # SpatialResolutionEngine (Section 11.5)
        persona.py                  # PersonaEngine
        reference_resolver.py       # ReferenceResolver (pronouns/refs against scoreboard)

    # UPDATED: tools/ structure per tools/README.md
    tools/
        __init__.py
        README.md                   # Existing spec
        registry.py                 # ToolRegistry (O(1) lookup)
        capability_matcher.py       # CapabilityMatcher
        schema_validator.py         # SchemaValidator
        orchestrator.py             # ToolCallOrchestrator
        prompt_matcher.py           # PromptMatcher
        dispatcher.py               # ToolDispatcher (ReAct loop)
        allowlist.py                # Per-state/tier/safety allowlist
        cognitive/
            __init__.py
            scoreboard.py           # update_scoreboard
            beliefs.py              # update_beliefs
            clarifications.py       # update_clarifications
            narrative.py            # update_narrative
            affect.py               # refine_affect
            promote.py              # promote_belief
        read/
            __init__.py
            memory.py               # recall_memory
            capabilities.py         # discover_capabilities
            context.py              # summarize_context
        action/
            __init__.py
            invoke.py               # invoke_capability
            spawn.py                # spawn_via_fabric
            workflow.py             # execute_workflow
        signal/
            __init__.py
            acknowledge.py          # acknowledge

    # NEW: LLM infrastructure (Section 6)
    llm/
        __init__.py
        dynamic_prompt_builder.py   # 9-section prompt assembly
        tool_bundle_validator.py    # ACK-first, pairing, budget
        react_loop_controller.py    # MAX_TOOL_ITERATIONS=10
        capability_router.py        # CHAT/TOOL_CALL/STRUCTURED/VISION/REASON
        result_injector.py          # Feed tool results back
        self_correction.py          # Track validation failures

    # NEW: Streaming Infrastructure (Model Hub Integration)
    streaming/
        __init__.py
        consumer.py                 # StreamConsumer (AsyncIterator[HubChunk])
        chunk_router.py             # ChunkRouter (text/tool_call/thinking/error)
        text_aggregator.py          # TextChunkAggregator (word boundary delivery)
        tool_call_handler.py        # ToolCallStreamHandler (partial JSON parsing)
        thinking_handler.py         # ThinkingTraceHandler (REASON traces)
        sse_emitter.py              # StreamingSSEEmitter -> OutputManager
        cancellation_guard.py       # StreamCancellationGuard (interrupt handling)
        partial_buffer.py           # PartialResponseBuffer (FSM state transitions)
        types.py                    # StreamingChunk, StreamState, etc.

    # NEW: Meta-intent system (README.md)
    meta_intent/
        __init__.py
        classifier.py               # MetaIntentClassifier (11 types)
        routing_engine.py           # RoutingDecisionEngine
        handlers/
            __init__.py
            acknowledgment.py
            status_check.py
            cancellation.py
            retry.py
            correction.py
            rapid_batch.py
            amendment.py
            refinement.py
            topic_change.py
            ambiguous_query.py
            small_talk.py

    # NEW: K0 Active Learning (Section 36)
    k0_integration/
        __init__.py
        # System 1: Gap Resolution
        curiosity_processor.py      # CuriosityIntentProcessor
        proactive_engine.py         # ProactiveDecisionEngine
        attention_budget.py         # AttentionBudgetGate
        gap_prioritizer.py          # GapPrioritizer
        warmth_generator.py         # WarmthMessageGenerator
        question_phraser.py         # ProactiveQuestionPhraser
        # System 2: Feedback Loop
        detectors/
            __init__.py
            correction.py           # CorrectionDetector
            confirmation.py         # ConfirmationDetector
            abandonment.py          # AbandonmentDetector
            modification.py         # ModificationDetector
            satisfaction.py         # SatisfactionDetector
        feedback_router.py          # FeedbackRouter
        feedback_aggregator.py      # FeedbackAggregator
        batch_window.py             # BatchWindowManager (500ms)
        horizontal_bridge.py        # HorizontalFeedbackBridge to K0
        conversation_context.py     # ConversationContext (Section 36.9 - K0 correlation tracking)

    # NEW: Interrupt & Recovery (Sections 18, 23)
    interrupt/
        __init__.py
        detector.py                 # InterruptDetector
        handler.py                  # InterruptHandler
        partial_preserver.py        # PartialResultPreserver

    recovery/
        __init__.py
        checkpoint.py               # CheckpointManager
        service.py                  # RecoveryService
        outbox_drainer.py           # OutboxDrainer
        retry_manager.py            # RetryManager (retry logic per CB)
        degradation_orchestrator.py # DegradationOrchestrator (tier cascade)

    # UPDATED: HIL Components (Sections 19-20, 26.2-26.3, 27)
    hil/
        __init__.py
        coordinator.py              # HILCoordinator (central coordinator)
        request_formatter.py        # HILRequestFormatter
        response_parser.py          # HILResponseParser
        timeout_manager.py          # HILTimeoutManager (120s + escalation)
        pending_tracker.py          # PendingHILTracker (keyed by request_id, originator, agent_id)
        subagent_bridge.py          # SubAgentHILBridge (K1 Bus delta lane routing)
        response_detector.py        # HILResponseDetector (user response vs new intent)

    output/
        __init__.py
        manager.py                  # OutputManager
        delta_aggregator.py         # DeltaAggregator
        events.py                   # OutputEvent dataclass
        scheduler.py                # ConversationScheduler

    state/
        __init__.py
        clarification.py            # ClarificationTracker
        context_assembler.py        # ContextAssembler
        hil_detector.py             # HILResponseDetector

    experience/
        __init__.py
        emotional.py                # Emotional processing
        narrative.py                # Narrative weaving
        anticipation.py             # Anticipatory response
        affective_mirror.py         # Affective mirroring

    # Existing skeleton directories
    affective/
        __init__.py
    empathy/
        __init__.py
    rhythm/
        __init__.py

    ports/
        __init__.py
        input.py                    # IInputPort
        output.py                   # IOutputPort
        classification.py           # IClassificationPort
        llm.py                      # ILLMPort
        state.py                    # IStatePort
        dispatch.py                 # IDispatchPort
        delta.py                    # IDeltaPort
        memory.py                   # IMemoryPort

    adapters/
        __init__.py
        production/
            __init__.py
            ws_input.py
            sse_output.py
            ultrabert.py
            model_gateway.py
            session_kernel.py
            fabric_orchestrator.py
            delta_bus.py
            bridge_recall.py
        test/
            __init__.py
            (8 test adapters)

    errors/
        __init__.py
        types.py
        router.py
        canned_responses.py

    circuit_breakers/
        __init__.py
        registry.py
        configs.py

    types/
        __init__.py
        messages.py
        classification.py
        state.py                    # ReactLoopScratchpad, LoopBudget, ToolExecution, AgentResult, CognitiveWrite, IterationSnapshot (ADR-0098)
        errors.py
        events.py
        enums.py
        k0_integration.py           # NEW
        tools.py                    # NEW

    contracts/
        concierge.yaml
        events.yaml
```

### 4.2 Test Structure (~1110 Tests)

```
tests/k1/concierge/
    __init__.py
    conftest.py

    unit/
        core/
            test_fsm_controller.py          # ~60
            test_turn_processor.py          # ~90
        processing/
            test_intent_processor.py        # ~110
            test_complexity_router.py       # ~45
        engines/
            test_temporal_engine.py         # ~25
            test_spatial_engine.py          # ~20
            test_persona_engine.py          # ~15
            test_reference_resolver.py      # ~20
        tools/
            test_registry.py                # ~25
            test_capability_matcher.py      # ~20
            test_schema_validator.py        # ~25
            test_orchestrator.py            # ~20
            test_dispatcher.py              # ~80
            test_cognitive_tools.py         # ~40
            test_read_tools.py              # ~20
            test_action_tools.py            # ~30
        llm/
            test_dynamic_prompt_builder.py  # ~30
            test_tool_bundle_validator.py   # ~35
            test_react_loop_controller.py   # ~25
            test_react_loop_scratchpad.py   # ~30 (ADR-0098: ephemeral working memory)
            test_capability_router.py       # ~20
        streaming/
            test_consumer.py                # ~25
            test_chunk_router.py            # ~20
            test_text_aggregator.py         # ~15
            test_tool_call_handler.py       # ~25
            test_thinking_handler.py        # ~15
            test_sse_emitter.py             # ~20
            test_cancellation_guard.py      # ~15
            test_partial_buffer.py          # ~15
        meta_intent/
            test_classifier.py              # ~25
            test_routing_engine.py          # ~20
            test_handlers.py                # ~30
        k0_integration/
            test_curiosity_processor.py     # ~20
            test_proactive_engine.py        # ~25
            test_gap_prioritizer.py         # ~20
            test_detectors.py               # ~75 (5 * 15)
            test_feedback_router.py         # ~20
            test_horizontal_bridge.py       # ~15
        interrupt/
            test_detector.py                # ~20
            test_handler.py                 # ~25
            test_partial_preserver.py       # ~15
        recovery/
            test_checkpoint.py              # ~20
            test_service.py                 # ~20
            test_retry_manager.py           # ~20
            test_degradation_orchestrator.py # ~20
        hil/
            test_coordinator.py             # ~25
            test_request_formatter.py       # ~15
            test_response_parser.py         # ~15
            test_timeout_manager.py         # ~15
            test_pending_tracker.py         # ~20
            test_subagent_bridge.py         # ~15
            test_response_detector.py       # ~15
        output/
            test_output_manager.py          # ~55
            test_delta_aggregator.py        # ~50
        state/
            test_clarification_tracker.py   # ~40
            test_context_assembler.py       # ~55
        experience/
            test_emotional.py               # ~15
            test_narrative.py               # ~15
            test_anticipation.py            # ~15
        errors/
            test_error_router.py            # ~30
            test_circuit_breaker.py         # ~20

    integration/
        test_turn_flow.py                   # E2E turn processing
        test_tier_routing.py                # LOW/MED/HIGH routing
        test_error_recovery.py              # CB trips, degradation
        test_lifecycle.py                   # init -> shutdown -> recovery
        test_hil_flow.py                    # Planner clarification
        test_interrupt.py                   # Mid-turn interrupt
        test_proactive_flow.py              # K0 gap injection
        test_feedback_flow.py               # Feedback detection to K0
        test_meta_intent_flow.py            # 11 meta-intent handling

    # NEW: Testing Infrastructure (verified gap)
    performance/
        test_phase1_latency.py              # 22ms P95 Phase 1 benchmark (~15)
        test_fsm_transition_latency.py      # <1ms FSM transitions (~10)
        test_turn_throughput.py             # End-to-end turn latency by tier (~20)
        test_memory_pressure.py             # 96KB SessionState budget compliance (~15)

    chaos/
        test_cb_cascade.py                  # All 7 CBs trip simultaneously (~15)
        test_partial_failures.py            # Individual component failures (~20)
        test_network_partition.py           # K0 Bridge disconnect scenarios (~15)
        test_timeout_storms.py              # Multiple concurrent timeouts (~15)

    invariants/
        test_invariant_monitors.py          # All 22 CONC-XX invariants runtime checks (~30)
        test_safety_invariants.py           # CRISIS detection, safety band enforcement (~15)
        test_ownership_invariants.py        # Single writer, turn lock, FSM ownership (~15)
```

---

## Part 5: Implementation Phases (16 Weeks)

### Phase 1: Types Foundation (Week 1)

**Files:** `types/*.py`

**Deliverables:**

- All core types (messages, classification, state, events, enums)
- K0 integration types (CuriosityIntent, FeedbackSignal, ProactiveDecision)
- Tool registry types (ToolSpec, ToolBundle, ToolCall)
- LLM infrastructure types (DynamicPrompt, ReActIteration, LLMCapability)

**Tests:** ~40

---

### Phase 2: Port Protocols (Week 1)

**Files:** `ports/*.py`

**Deliverables:** 8 Protocol definitions

**Tests:** ~20

---

### Phase 3: Test Adapters (Week 2)

**Files:** `adapters/test/*.py`

**Deliverables:** 8 test adapters

**Tests:** ~40

---

### Phase 4: Error System (Week 2)

**Files:** `errors/*.py`, `circuit_breakers/*.py`

**Deliverables:** Error router, 7 CBs, canned responses

**Tests:** ~50

---

### Phase 5: FSM Core (Week 3)

**Files:** `core/states.py`, `core/transitions.py`, `core/fsm_controller.py`

**Deliverables:** 8 states + 4 experience, 14 transitions, FSMController

**Tests:** ~60

---

### Phase 6: UltraBERT Engine (Week 3-4)

**Files:** `engines/ultrabert.py`, `processing/safety_gate.py`, `processing/hypothesis.py`, `processing/gap_detection.py`

**Deliverables:** 12 classification heads, SafetyGate, hypothesis, gaps

**Tests:** ~70

---

### Phase 7: Tools Infrastructure (Week 4) - NEW

**Files:** `tools/registry.py`, `tools/capability_matcher.py`, `tools/schema_validator.py`, `tools/orchestrator.py`, `tools/prompt_matcher.py`

**Deliverables:** ToolRegistry, CapabilityMatcher, SchemaValidator, ToolCallOrchestrator, PromptMatcher

**Tests:** ~105

---

### Phase 8: LLM Infrastructure (Week 5) - NEW

**Files:** `llm/*.py`

**Deliverables:** DynamicPromptBuilder, ToolBundleValidator, ReActLoopController (with ReactLoopScratchpad lifecycle — ADR-0098), LLMCapabilityRouter, ReactLoopScratchpad + 5 supporting types (LoopBudget, ToolExecution, AgentResult, CognitiveWrite, IterationSnapshot)

**Tests:** ~170

---

### Phase 8.5: Streaming Infrastructure (Week 5-6) - NEW

**Files:** `streaming/*.py`

**Deliverables:**

- StreamConsumer (Model Hub AsyncIterator[HubChunk] consumer)
- ChunkRouter (text/tool_call/thinking/error routing)
- TextChunkAggregator (word boundary delivery)
- ToolCallStreamHandler (partial JSON parsing, tool_call events)
- ThinkingTraceHandler (REASON capability traces)
- StreamingSSEEmitter (-> OutputManager)
- StreamCancellationGuard (interrupt during stream)
- PartialResponseBuffer (FSM state management)

**Integration with Model Hub:**

- Consumes `IModelHubPort.stream_execute()` from Model Hub
- Does NOT duplicate Model Hub streaming logic
- Focuses on Concierge-specific UX (tool call visualization, thinking traces)

**Tests:** ~150

---

### Phase 9: Meta-Intent System (Week 6) - NEW

**Files:** `meta_intent/*.py`

**Deliverables:** MetaIntentClassifier, RoutingDecisionEngine, 11 handlers

**Tests:** ~75

---

### Phase 10: Tool Implementations (Week 6)

**Files:** `tools/cognitive/*.py`, `tools/read/*.py`, `tools/action/*.py`, `tools/signal/*.py`, `tools/dispatcher.py`

**Deliverables:** 13 tools + dispatcher

**Tests:** ~100

---

### Phase 11: K0 Active Learning (Week 7-8) - NEW

**Files:** `k0_integration/*.py`

**Deliverables:**

- System 1: CuriosityIntentProcessor, ProactiveDecisionEngine, AttentionBudgetGate, GapPrioritizer, WarmthMessageGenerator, ProactiveQuestionPhraser
- System 2: 5 detectors, FeedbackRouter, FeedbackAggregator, BatchWindowManager, HorizontalFeedbackBridge

**Tests:** ~185

---

### Phase 12: State Management (Week 8-9)

**Files:** `state/*.py`

**Deliverables:** ClarificationTracker, ContextAssembler, HILResponseDetector

**Tests:** ~95

---

### Phase 13: Interrupt & Recovery (Week 9) - NEW

**Files:** `interrupt/*.py`, `recovery/*.py`

**Deliverables:** InterruptDetector, InterruptHandler, PartialResultPreserver, CheckpointManager, RecoveryService, OutboxDrainer

**Tests:** ~110

---

### Phase 14: HIL Components (Week 10) - NEW

**Files:** `hil/*.py`

**Deliverables:** HILRequestFormatter, HILResponseParser, HILTimeoutManager, PendingHILTracker

**Tests:** ~55

---

### Phase 15: Output & Experience (Week 10-11)

**Files:** `output/*.py`, `experience/*.py`

**Deliverables:** OutputManager, DeltaAggregator, scheduler, 4 experience components

**Tests:** ~150

---

### Phase 16: Turn Processor & Factory (Week 11-12)

**Files:** `core/turn_processor.py`, `core/concierge.py`, `core/factory.py`

**Deliverables:** TurnProcessor, Concierge, ConciergeFactory

**Tests:** ~120

---

### Phase 17: Production Adapters (Week 13-14)

**Files:** `adapters/production/*.py`

**Deliverables:** 8 production adapters with CB integration

**Tests:** ~80

---

### Phase 18: Integration Tests (Week 15-16)

**Files:** `tests/k1/concierge/integration/*.py`

**Deliverables:** E2E flows, tier routing, error recovery, lifecycle, HIL, interrupt, proactive, feedback

**Tests:** ~60

---

## Part 6: Hard Invariants (22)

| ID | Category | Invariant | Enforcement |
|----|----------|-----------|-------------|
| CONC-01 | OWNERSHIP | Single writer to SessionState | MutationGuard validation |
| CONC-02 | OWNERSHIP | Output channel exclusivity | FSM transition guards |
| CONC-03 | OWNERSHIP | Single FSM per session | Factory enforcement |
| CONC-04 | OWNERSHIP | Turn lock serialization | lock_version in control |
| CONC-05 | SAFETY | CRISIS bypasses all gates | SafetyGate first check |
| CONC-06 | SAFETY | Safety first in Phase 1 | Pipeline ordering |
| CONC-07 | SAFETY | PII masking before output | OutputManager filter |
| CONC-08 | RATE LIMITS | Max 3 clarifications per intent | ClarificationTracker |
| CONC-09 | RATE LIMITS | Max 20 tool calls per turn | ToolDispatcher budget |
| CONC-10 | RATE LIMITS | 500ms batch window | DeltaAggregator timer |
| CONC-11 | RATE LIMITS | 120s absolute turn timeout | Watchdog timer |
| CONC-12 | RATE LIMITS | 50 output queue depth | OutputManager limit |
| CONC-13 | TIMING | Phase 1 < 22ms P95 | UltraBERT inference |
| CONC-14 | TIMING | FSM transition < 1ms | State machine simplicity |
| CONC-15 | TIMING | 1 concurrent turn per session | Turn lock |
| CONC-16 | TIMING | LLM timeout 30s | CB_MODEL config |
| CONC-17 | STRUCTURAL | Deterministic FSM | No random transitions |
| CONC-18 | STRUCTURAL | Protocol-typed ports | Structural subtyping |
| CONC-19 | STRUCTURAL | No circular imports | Dependency graph |
| CONC-20 | TOKEN BUDGET | HOT tier 48KB | SizeTracker |
| CONC-21 | TOKEN BUDGET | WARM tier 48KB | MigrationEngine |
| CONC-22 | TOKEN BUDGET | Context window 128K tokens | ContextAssembler |

---

## Part 7: Performance Baselines

| Metric | Target | Measurement Point |
|--------|--------|-------------------|
| Phase 1 latency | 22ms P50, 25ms P99 | UltraBERT inference end |
| FSM transition | < 1ms | State change completion |
| Turn lock acquire | < 0.1ms | control section update |
| HOT read all | < 0.2ms | read_all_hot() return |
| SessionState write | < 1ms | MutationGuard.preflight() + write |
| LOCAL COLD checkpoint | < 1ms P95 | SQLite transaction |
| SSE delivery | < 10ms P95 | Server to client RTT |
| DeltaAggregator flush | < 1ms | Batch publish |
| CB state check | < 0.01ms | In-memory check |
| LOW tier E2E | < 500ms P95 | Message in to response out |
| MEDIUM tier E2E | < 10s P95 | Via Orchestrator |
| HIGH tier E2E | < 60s P95 | Via Orchestrator + Planner |
| Proactive question | < 100ms | Gap to natural phrasing |
| Feedback detection | < 50ms | User input to signal emit |

---

## Part 8: Integration Contracts

### 8.1 K0 Active Learning Integration (Section 36)

**Inbound from K0 (SSE Events):**

| K0 Event | K1 Topic | Handler |
|----------|----------|---------|
| `curiosity.intent.v1` | `k1.k0.sse.curiosity.intent.v1` | CuriosityIntentProcessor |
| `k0.proactive.signal.v1` | `k1.k0.sse.proactive.signal.v1` | ProactiveDecisionEngine |
| `k0.gap.detected.v1` | `k1.k0.sse.gap.detected.v1` | GapPrioritizer |

**Outbound to K0 (Feedback Signals):**

| Feedback Type | K0 Topic | Payload |
|--------------|----------|---------|
| Correction | `k0.feedback.correction.v1` | CorrectionSignal |
| Confirmation | `k0.feedback.confirmation.v1` | ConfirmationSignal |
| Abandonment | `k0.feedback.abandonment.v1` | AbandonmentSignal |
| Modification | `k0.feedback.modification.v1` | ModificationSignal |
| Satisfaction | `k0.feedback.satisfaction.v1` | SatisfactionSignal |

### 8.2 Orchestrator Integration

**TaskEnvelope dispatch (unchanged):**

```python
TaskEnvelope:
    intent: str
    trace_id: str
    caller_id: str
    tier: "MEDIUM" | "HIGH"
    capabilities: List[str]
    params: Dict[str, Any]
    context: Dict[str, Any]
    timeout_ms: int
```

### 8.3 K1 Bus Integration

**Delta Lane (BEST_EFFORT):**

- 11 delta topics
- 500ms batching via DeltaAggregator

**Event Lane (STRICT/RELAXED):**

- 8 coordination events
- Immediate delivery

**Subscriptions (12 patterns - expanded):**

| Topic Pattern | Handler |
|--------------|---------|
| `k1.hil.clarification.v1` | FSMController |
| `k1.hil.approval_request.v1` | FSMController |
| `k1.hil.fallback.v1` | FSMController |
| `k1.hil.progress.v1` | DeltaAggregator |
| `k1.orchestration.dag.completed.v1` | TurnProcessor |
| `k1.orchestration.delta.v1` | DeltaAggregator |
| `k1.orchestration.step.completed.v1` | DeltaAggregator |
| `k1.agent.*.delta.v1` | DeltaAggregator |
| `k0.proactive.signal.v1` | ProactiveAgent |
| `k1.k0.sse.curiosity.intent.v1` | CuriosityIntentProcessor |
| `k1.k0.sse.gap.detected.v1` | GapPrioritizer |
| `k1.fabric.agent.expired.v1` | (log only) |

---

## Part 9: Governance Sync

### Before Implementation

```powershell
python -m governance.k0.scripts.sync --report
```

Must show SYNCED or only Planning drift.

### After Implementation

Update `governance/k0/k0_architecture_master.md`:

- Part 3.1 Module Master Registry (add Concierge)
- Part 4.1 Event Topics Registry (24 topics - expanded for K0 integration)
- Part 5.1 Global Contract Registry (concierge.yaml)
- Part 7.1 ADR Index (ADR-0093, ADR-0017g references)

---

## Appendix A: File Count Summary (UPDATED V2.2)

| Category | Count |
|----------|-------|
| Type files | 9 |
| Port protocols | 8 |
| Test adapters | 8 |
| Production adapters | 8 |
| Core services | 11 |
| **Resolution engines** | **4** |
| Processing engines | 7 |
| Tools infrastructure | 5 |
| Tool implementations | 14 |
| LLM infrastructure | 6 |
| **Streaming infrastructure** | **9** |
| Meta-intent system | 13 |
| K0 integration | 13 |
| Interrupt/Recovery | **8** |
| **HIL components** | **7** |
| Output | 4 |
| State management | 3 |
| Experience layer | 5 |
| Error handling | 5 |
| **Total implementation files** | **~143** |
| **Total test files** | **~48** |
| **Total tests** | **~1110** |

---

## Appendix B: Validation Checklist

- [ ] All 22 invariants enforced
- [ ] All 8 ports defined and implemented
- [ ] All 11 services implemented
- [ ] All 5 tools infrastructure components (ToolRegistry, CapabilityMatcher, SchemaValidator, ToolCallOrchestrator, PromptMatcher)
- [ ] All 6 LLM infrastructure components
- [ ] **All 9 streaming infrastructure components (StreamConsumer, ChunkRouter, etc.)**
- [ ] All 7 HIL components (HILCoordinator, formatters, parsers, bridges)
- [ ] All 4 resolution engines (TemporalResolutionEngine, SpatialResolutionEngine, PersonaEngine, ReferenceResolver)
- [ ] RetryManager and DegradationOrchestrator for error recovery
- [ ] Performance/Chaos/Invariant testing infrastructure (~185 tests)
- [ ] All 11 meta-intent handlers
- [ ] All 10 K0 gap types supported
- [ ] All 5 feedback detectors
- [ ] FSM 8 states + 14 transitions + 4 experience
- [ ] 32 FSM flows emergently supported
- [ ] Error recovery paths cover all error codes
- [ ] 7 circuit breakers configured
- [ ] 24 event topics registered (expanded)
- [ ] Directory structure matches spec
- [ ] ~900 tests passing
- [ ] All integrations verified (Orchestrator, Planner, Fabric, SessionState, K0, **Model Hub streaming**)
- [ ] K0 Active Learning bidirectional integration
- [ ] Model Hub stream consumption verified
- [ ] Governance sync shows SYNCED

---

*End of Production Implementation Plan V2*
